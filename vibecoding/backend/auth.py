"""
Authentication module for VibeCoding platform.
Handles user registration, login, and JWT token management.
Uses SQLite for user storage and bcrypt-like hashing via hashlib+secrets.
"""

import os
import sqlite3
import hashlib
import secrets
import time
import json
from datetime import datetime, timedelta
from typing import Optional
from fastapi import HTTPException, Depends, Header
from pydantic import BaseModel, EmailStr

# ─── Configuration ──────────────────────────────────────────────────────────────
# Persistent JWT secret - stored in a file to survive server restarts
JWT_SECRET_FILE = os.path.join(os.path.dirname(__file__), ".jwt_secret")

def _get_or_create_jwt_secret():
    """Get JWT secret from file or create a new one if it doesn't exist."""
    # First check environment variable
    env_secret = os.getenv("JWT_SECRET")
    if env_secret:
        return env_secret
    
    # Try to read from file
    try:
        if os.path.exists(JWT_SECRET_FILE):
            with open(JWT_SECRET_FILE, 'r') as f:
                secret = f.read().strip()
                if secret:
                    return secret
    except Exception as e:
        print(f"⚠️ Failed to read JWT secret from file: {e}")
    
    # Generate new secret and save it
    new_secret = secrets.token_hex(32)
    try:
        with open(JWT_SECRET_FILE, 'w') as f:
            f.write(new_secret)
        print(f"✅ Generated new JWT secret and saved to {JWT_SECRET_FILE}")
    except Exception as e:
        print(f"⚠️ Failed to save JWT secret to file: {e}")
    
    return new_secret

JWT_SECRET = _get_or_create_jwt_secret()
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24
DB_PATH = os.path.join(os.path.dirname(__file__), "vibecoding_users.db")


# ─── Models ─────────────────────────────────────────────────────────────────────
class SignupRequest(BaseModel):
    username: str
    email: str
    password: Optional[str] = None  # Optional - will be auto-generated if not provided
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user: dict
    message: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str] = None
    created_at: str
    avatar_color: str


# ─── Database Setup ─────────────────────────────────────────────────────────────
def get_db(robust=True):
    """
    Get a database connection with automatic corruption recovery.
    """
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        # Attempt to set WAL mode - this often triggers 'malformed' error if DB is corrupt
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError as e:
            err_msg = str(e).lower()
            if robust and any(key in err_msg for key in ["malformed", "not a database", "corrupt", "disk i/o error"]):
                print(f"🚨 DATABASE CORRUPTED! Attempting recovery: {e}")
                conn.close()
                _recover_corrupt_db()
                return get_db(robust=False)
            raise
        return conn
    except sqlite3.DatabaseError as e:
        err_msg = str(e).lower()
        if robust and any(key in err_msg for key in ["malformed", "not a database", "corrupt", "disk i/o error"]):
            print(f"🚨 DATABASE CORRUPTED! Attempting recovery: {e}")
            _recover_corrupt_db()
            return get_db(robust=False)
        raise


def _recover_corrupt_db():
    """Backup corrupted DB and start clean."""
    import shutil
    timestamp = int(time.time())
    corrupt_backup = f"{DB_PATH}.corrupt.{timestamp}"
    
    # Close any active connections if possible (though we should be in a crash state here)
    if os.path.exists(DB_PATH):
        try:
            shutil.copy2(DB_PATH, corrupt_backup)
            print(f"📦 Corrupted database backed up to: {corrupt_backup}")
        except Exception as e:
            print(f"⚠️ Failed to backup corrupted DB: {e}")
            
        # Clean up all related files
        for suffix in ["", "-shm", "-wal", "-journal"]:
            f = f"{DB_PATH}{suffix}"
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception as e:
                    print(f"⚠️ Failed to remove {f}: {e}")
    
    print("✨ Database files cleared. App will recreate schema on next connection.")


def init_db():
    """Initialize the database schema."""
    try:
        conn = get_db()
    except Exception as e:
        print(f"❌ Critical DB failure: {e}")
        return

    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                full_name TEXT,
                avatar_color TEXT DEFAULT '#8B5CF6',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                reset_token TEXT,
                reset_token_expiry TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                container_id TEXT,
                role TEXT NOT NULL,
                content TEXT,
                code TEXT,
                version_id TEXT,
                timestamp TEXT NOT NULL,
                suggestions TEXT,
                tool_calls TEXT,
                image_paths TEXT,
                metadata TEXT,
                summary TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_project_id ON messages(project_id)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_logs (
                id TEXT PRIMARY KEY,
                username TEXT,
                project_id TEXT NOT NULL,
                prompt TEXT,
                response TEXT,
                prompt_tokens INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                feasibility TEXT,
                feasibility_reason TEXT,
                status TEXT,
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS enduser_logs (
                id TEXT PRIMARY KEY,
                username TEXT,
                project_id TEXT,
                action TEXT NOT NULL,
                details TEXT,
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_logs_project_id ON user_logs(project_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_enduser_logs_username ON enduser_logs(username)")
        conn.commit()

        # Add reset_token columns if they don't exist (migration for existing databases)
        try:
            conn.execute("ALTER TABLE users ADD COLUMN reset_token TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass
        
        try:
            conn.execute("ALTER TABLE users ADD COLUMN reset_token_expiry TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass
        
        try:
            conn.execute("ALTER TABLE messages ADD COLUMN summary TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    except Exception as e:
        print(f"⚠️ Schema initialization error: {e}")
    finally:
        try:
            conn.close()
        except:
            pass


# Initialize DB on module load
init_db()

# ─── Avatar Color Generator ────────────────────────────────────────────────────
AVATAR_COLORS = [
    "#8B5CF6",  # Purple
    "#EC4899",  # Pink
    "#3B82F6",  # Blue
    "#10B981",  # Emerald
    "#F59E0B",  # Amber
    "#EF4444",  # Red
    "#06B6D4",  # Cyan
    "#F97316",  # Orange
    "#6366F1",  # Indigo
    "#14B8A6",  # Teal
]


def generate_avatar_color(email: str) -> str:
    """Consistently generate an avatar color from email."""
    hash_val = int(hashlib.md5(email.encode()).hexdigest(), 16)
    return AVATAR_COLORS[hash_val % len(AVATAR_COLORS)]


# ─── Password Hashing ──────────────────────────────────────────────────────────
def hash_password(password: str, salt: Optional[str] = None) -> tuple:
    """Hash password with salt using PBKDF2."""
    if salt is None:
        salt = secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000  # iterations
    ).hex()
    return password_hash, salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    """Verify a password against its hash."""
    computed_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(computed_hash, password_hash)


# ─── JWT Token Management ──────────────────────────────────────────────────────
# Simple JWT implementation without external dependencies
import base64
import hmac


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')


def _base64url_decode(data: str) -> bytes:
    padding = 4 - len(data) % 4
    if padding != 4:
        data += '=' * padding
    return base64.urlsafe_b64decode(data)


def create_jwt_token(payload: dict) -> str:
    """Create a JWT token."""
    header = {"alg": "HS256", "typ": "JWT"}
    
    # Add expiration
    payload["exp"] = int(time.time()) + (JWT_EXPIRATION_HOURS * 3600)
    payload["iat"] = int(time.time())
    
    header_b64 = _base64url_encode(json.dumps(header).encode('utf-8'))
    payload_b64 = _base64url_encode(json.dumps(payload).encode('utf-8'))
    
    message = f"{header_b64}.{payload_b64}"
    signature = hmac.new(
        JWT_SECRET.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).digest()
    signature_b64 = _base64url_encode(signature)
    
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def verify_jwt_token(token: str) -> Optional[dict]:
    """Verify and decode a JWT token."""
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        
        header_b64, payload_b64, signature_b64 = parts
        
        # Verify signature
        message = f"{header_b64}.{payload_b64}"
        expected_signature = hmac.new(
            JWT_SECRET.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
        
        actual_signature = _base64url_decode(signature_b64)
        
        if not hmac.compare_digest(expected_signature, actual_signature):
            return None
        
        # Decode payload
        payload = json.loads(_base64url_decode(payload_b64))
        
        # Check expiration
        if payload.get("exp", 0) < int(time.time()):
            return None
        
        return payload
    except Exception:
        return None


def generate_random_password(length: int = 12) -> str:
    """Generate a secure random password."""
    import string
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    # Ensure at least one of each type
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*")
    ]
    # Fill the rest randomly
    password += [secrets.choice(alphabet) for _ in range(length - 4)]
    # Shuffle to avoid predictable pattern
    secrets.SystemRandom().shuffle(password)
    return ''.join(password)


# ─── Auth Functions ─────────────────────────────────────────────────────────────
def signup_user(request: SignupRequest) -> AuthResponse:
    """Register a new user."""
    from email_service import email_service
    
    conn = get_db()
    try:
        # Check if email already exists
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?", (request.email.lower(),)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Check if username already exists
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", (request.username.lower(),)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Username already taken")
        
        # Validate
        if len(request.username) < 3:
            raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
        if "@" not in request.email:
            raise HTTPException(status_code=400, detail="Invalid email address")
        
        # Generate password if not provided
        password_to_use = request.password
        generated_password = None
        
        if not password_to_use:
            # Passwordless signup - generate random password
            generated_password = generate_random_password()
            password_to_use = generated_password
        else:
            # User provided password - validate it
            if len(password_to_use) < 6:
                raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
        
        # Hash password
        password_hash, salt = hash_password(password_to_use)
        avatar_color = generate_avatar_color(request.email)
        now = datetime.utcnow().isoformat()
        
        # Insert user
        cursor = conn.execute(
            """INSERT INTO users (username, email, password_hash, salt, full_name, avatar_color, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (request.username.lower(), request.email.lower(), password_hash, salt,
             request.full_name or request.username, avatar_color, now, now)
        )
        conn.commit()
        
        user_id = cursor.lastrowid
        
        # Send welcome email with password if it was generated
        if generated_password:
            try:
                email_sent = email_service.send_welcome_email(
                    request.email.lower(),
                    request.username.lower(),
                    generated_password
                )
                if not email_sent:
                    # Log warning but don't fail signup
                    print(f"Warning: Failed to send welcome email to {request.email}")
            except Exception as e:
                print(f"Error sending welcome email: {e}")
        
        # Create token
        token = create_jwt_token({
            "user_id": user_id,
            "email": request.email.lower(),
            "username": request.username.lower()
        })
        
        # Log action
        log_enduser_action(request.username.lower(), None, "signup", f"Email: {request.email.lower()}")
        
        message = "Account created successfully!"
        if generated_password:
            message += " Check your email for your password."
        
        return AuthResponse(
            token=token,
            user={
                "id": user_id,
                "username": request.username.lower(),
                "email": request.email.lower(),
                "full_name": request.full_name or request.username,
                "avatar_color": avatar_color,
                "created_at": now
            },
            message=message
        )
    finally:
        conn.close()


def login_user(request: LoginRequest) -> AuthResponse:
    """Authenticate a user."""
    conn = get_db()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (request.email.lower(),)
        ).fetchone()
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        if not verify_password(request.password, user["password_hash"], user["salt"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Create token
        token = create_jwt_token({
            "user_id": user["id"],
            "email": user["email"],
            "username": user["username"]
        })
        
        # Log action
        log_enduser_action(user["username"], None, "login", f"Email: {user['email']}")
        
        return AuthResponse(
            token=token,
            user={
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "full_name": user["full_name"],
                "avatar_color": user["avatar_color"],
                "created_at": user["created_at"]
            },
            message="Login successful!"
        )
    finally:
        conn.close()


def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """Dependency to get the current authenticated user from the token."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Support "Bearer <token>" format
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    
    payload = verify_jwt_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Fetch user from DB
    conn = get_db()
    try:
        user = conn.execute(
            "SELECT id, username, email, full_name, avatar_color, created_at FROM users WHERE id = ?",
            (payload["user_id"],)
        ).fetchone()
        
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        return dict(user)
    finally:
        conn.close()



class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


def forgot_password(request: ForgotPasswordRequest) -> dict:
    """Generate password reset token and send reset link via email."""
    from email_service import email_service
    
    conn = get_db()
    try:
        # Find user by email
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (request.email.lower(),)
        ).fetchone()
        
        if not user:
            # Return clear error message that email is not registered
            raise HTTPException(
                status_code=404,
                detail="This email is not registered with us. Please check your email or sign up for a new account."
            )
        
        # Generate secure reset token (valid for 1 hour)
        reset_token = secrets.token_urlsafe(32)
        token_expiry = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        
        # Store reset token in database
        now = datetime.utcnow().isoformat()
        conn.execute(
            "UPDATE users SET reset_token = ?, reset_token_expiry = ?, updated_at = ? WHERE id = ?",
            (reset_token, token_expiry, now, user["id"])
        )
        conn.commit()
        
        # Generate reset URL
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
        reset_url = f"{frontend_url}/vibecoding/reset-password?token={reset_token}"
        
        # Send password reset email with link
        try:
            email_sent = email_service.send_password_reset_link(
                user["email"],
                user["username"],
                reset_url
            )
            if not email_sent:
                print(f"Warning: Failed to send password reset email to {user['email']}")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to send password reset email. Please try again later."
                )
        except HTTPException:
            raise
        except Exception as e:
            print(f"Error sending password reset email: {e}")
            raise HTTPException(
                status_code=500,
                detail="Failed to send password reset email. Please try again later."
            )
        
        return {"message": "Password reset link has been sent to your email. Please check your inbox."}
    finally:
        conn.close()


def reset_password(request: ResetPasswordRequest) -> dict:
    """Reset password using the token from email."""
    conn = get_db()
    try:
        # Find user by reset token
        user = conn.execute(
            "SELECT * FROM users WHERE reset_token = ?", (request.token,)
        ).fetchone()
        
        if not user:
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")
        
        # Check if token is expired
        token_expiry = datetime.fromisoformat(user["reset_token_expiry"])
        if datetime.utcnow() > token_expiry:
            raise HTTPException(status_code=400, detail="Reset token has expired. Please request a new one.")
        
        # Validate new password
        if len(request.new_password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters long")
        
        # Hash the new password
        password_hash, salt = hash_password(request.new_password)
        
        # Update user's password and clear reset token
        now = datetime.utcnow().isoformat()
        conn.execute(
            "UPDATE users SET password_hash = ?, salt = ?, reset_token = NULL, reset_token_expiry = NULL, updated_at = ? WHERE id = ?",
            (password_hash, salt, now, user["id"])
        )
        conn.commit()
        
        return {"message": "Password has been reset successfully. You can now login with your new password."}
    finally:
        conn.close()


def log_user_feasibility(project_id: str, username: str, prompt: str, response: str, prompt_tokens: int, completion_tokens: int, feasibility: str, feasibility_reason: str = None, status: str = "success"):
    """Log AI prompt, response, tokens and feasibility to SQLite user_logs table."""
    conn = get_db()
    try:
        import uuid
        import time
        from datetime import datetime
        log_id = f"log_{int(time.time())}_{uuid.uuid4().hex[:4]}"
        conn.execute(
            """INSERT INTO user_logs 
               (id, username, project_id, prompt, response, prompt_tokens, completion_tokens, total_tokens, feasibility, feasibility_reason, status, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (log_id, username, project_id, prompt, response, prompt_tokens, completion_tokens, 
             prompt_tokens + completion_tokens, feasibility, feasibility_reason, status, datetime.now().astimezone().isoformat())
        )
        conn.commit()
        print(f"Logged user feasibility: {log_id}")
    except Exception as e:
        print(f"Failed to log user feasibility: {e}")
    finally:
        conn.close()


def log_enduser_action(username: str, project_id: str, action: str, details: str = None):
    """Log an enduser action to SQLite enduser_logs table."""
    conn = get_db()
    try:
        import uuid
        import time
        from datetime import datetime
        log_id = f"act_{int(time.time())}_{uuid.uuid4().hex[:4]}"
        conn.execute(
            """INSERT INTO enduser_logs 
               (id, username, project_id, action, details, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (log_id, username, project_id, action, details, datetime.now().astimezone().isoformat())
        )
        conn.commit()
        print(f"Logged enduser action: {log_id}")
    except Exception as e:
        print(f"Failed to log enduser action: {e}")
    finally:
        conn.close()
