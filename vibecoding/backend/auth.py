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
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24
DB_PATH = os.path.join(os.path.dirname(__file__), "vibecoding_users.db")


# ─── Models ─────────────────────────────────────────────────────────────────────
class SignupRequest(BaseModel):
    username: str
    email: str
    password: str
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
def get_db():
    """Get a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Initialize the database schema."""
    conn = get_db()
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
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


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


# ─── Auth Functions ─────────────────────────────────────────────────────────────
def signup_user(request: SignupRequest) -> AuthResponse:
    """Register a new user."""
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
        if len(request.password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
        if len(request.username) < 3:
            raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
        if "@" not in request.email:
            raise HTTPException(status_code=400, detail="Invalid email address")
        
        # Hash password
        password_hash, salt = hash_password(request.password)
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
        
        # Create token
        token = create_jwt_token({
            "user_id": user_id,
            "email": request.email.lower(),
            "username": request.username.lower()
        })
        
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
            message="Account created successfully!"
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
