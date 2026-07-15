"""
Service for sharing documents with external users via secure links.
"""

import os
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path
import sqlite3
from email_service import _send_email_message
from email.message import EmailMessage

# Database path - synced with database.py
DB_PATH = os.getenv("DATABASE_PATH", "sql_app.db")


def generate_share_token() -> str:
    """Generate a secure random token for sharing."""
    return secrets.token_urlsafe(32)


def hash_password(password: str) -> str:
    """Hash a password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def calculate_expiration(expiration_time: str) -> Optional[datetime]:
    """Calculate expiration datetime based on expiration_time setting."""
    if expiration_time == 'no-expiration':
        return None
    
    now = datetime.utcnow()
    if expiration_time == '24h':
        return now + timedelta(hours=24)
    elif expiration_time == '7d':
        return now + timedelta(days=7)
    elif expiration_time == '30d':
        return now + timedelta(days=30)
    
    return None


def create_shared_document(
    user_id: int,
    title: str,
    config: Dict[str, Any],
    file_paths: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Create a new shared document entry.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Generate unique share token (this is the base/anonymous token)
        share_token = generate_share_token()
        
        # Calculate expiration
        expires_at = calculate_expiration(config.get('expirationTime', 'no-expiration'))
        
        # Hash password if required
        password_hash = None
        if config.get('requirePassword') and config.get('password'):
            password_hash = hash_password(config['password'])
        
        # Insert shared document
        cursor.execute("""
            INSERT INTO shared_documents 
            (share_token, user_id, title, access_type, expiration_time, expires_at, require_password, password_hash, can_download, allow_anonymous)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            share_token,
            user_id,
            title,
            config.get('dashboardAccess', 'once'),
            config.get('expirationTime', 'no-expiration'),
            expires_at,
            1 if config.get('requirePassword') else 0,
            password_hash,
            1 if config.get('canDownload', True) else 0,
            1 if config.get('allowAnonymous', True) else 0
        ))
        
        share_id = cursor.lastrowid
        
        # Insert file records
        for file_info in file_paths:
            cursor.execute("""
                INSERT INTO shared_document_files
                (share_id, filename, original_filename, file_path, file_size, file_type)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                share_id,
                file_info['filename'],
                file_info['original_filename'],
                file_info['path'],
                file_info.get('size', 0),
                file_info.get('type', '')
            ))
        
        conn.commit()
        
        # Generate share URL
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
        share_url = f"{frontend_url}/shared/{share_token}"
        
        return {
            'share_token': share_token,
            'share_url': share_url,
            'share_id': share_id
        }
        
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def add_share_recipients(share_id: int, recipients: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Add recipient emails to a shared document with unique tokens.
    recipients is a list of dicts: {'email': str, 'access_level': str}
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    results = []
    
    try:
        for recipient in recipients:
            email = recipient.get('email', '').strip()
            if email:
                share_token = generate_share_token()
                access_level = recipient.get('access_level', 'view')
                
                cursor.execute("""
                    INSERT INTO shared_document_recipients (share_id, email, share_token, access_level)
                    VALUES (?, ?, ?, ?)
                """, (share_id, email, share_token, access_level))
                
                results.append({
                    'email': email,
                    'share_token': share_token,
                    'access_level': access_level
                })
        
        conn.commit()
        return results
    finally:
        conn.close()


def get_share_recipients(share_id: int) -> List[Dict[str, Any]]:
    """Get all recipients for a share with their tokens and access levels."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT email, share_token, access_level, notified_at
            FROM shared_document_recipients
            WHERE share_id = ?
        """, (share_id,))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def send_share_notification_emails(
    share_id: int,
    recipients_data: List[Dict[str, Any]],
    sender_name: str,
    document_count: int,
    config: Dict[str, Any]
):
    """Send individual email notifications to recipients with their unique links."""
    
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    
    for recipient in recipients_data:
        recipient_email = recipient.get('email', '')
        individual_token = recipient.get('share_token', '')
        individual_url = f"{frontend_url}/shared/{individual_token}"
        
        if not recipient_email or not individual_token:
            continue
        
        # Build expiration text
        expiration_text = "This link does not expire."
        expiration_time = config.get('expirationTime', 'no-expiration')
        if expiration_time == '24h':
            expiration_text = "This link will expire in 24 hours."
        elif expiration_time == '7d':
            expiration_text = "This link will expire in 7 days."
        elif expiration_time == '30d':
            expiration_text = "This link will expire in 30 days."
        
        # Build access text
        access_text = ""
        if config.get('dashboardAccess') == 'once':
            access_text = "⚠️ This link can only be accessed once."
        
        # Build password text
        password_text = ""
        if config.get('requirePassword'):
            password_text = f"<p style='margin: 10px 0 0; font-size: 14px; color: #FCD34D;'>🔐 Password required: <strong>{config.get('password', '')}</strong></p>"
        
        subject = f"{sender_name} shared documents with you - DSuite"
        
        html_body = f\"\"\"
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #0A0A0F; color: #ffffff;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #0A0A0F;">
                <tr>
                    <td align="center" style="padding: 40px 20px;">
                        <table width="600" cellpadding="0" cellspacing="0" style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-radius: 16px; overflow: hidden; box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);">
                            <!-- Header -->
                            <tr>
                                <td style="padding: 40px 40px 30px; text-align: center; background: linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%);">
                                    <h1 style="margin: 0; font-size: 28px; font-weight: 800; letter-spacing: -0.5px; color: #ffffff;">DSuite</h1>
                                    <p style="margin: 10px 0 0; font-size: 16px; color: rgba(255,255,255,0.8);">Secure Document Sharing</p>
                                </td>
                            </tr>
                            
                            <!-- Content -->
                            <tr>
                                <td style="padding: 40px;">
                                    <h2 style="margin: 0 0 20px; font-size: 20px; font-weight: 700; color: #ffffff;">Hello,</h2>
                                    <p style="margin: 0 0 20px; font-size: 16px; line-height: 1.6; color: #d1d5db;">
                                        <strong>{sender_name}</strong> has shared <strong>{document_count}</strong> document(s) with you via DSuite.
                                    </p>
                                    
                                    <div style="background: rgba(255,255,255,0.05); border-radius: 12px; padding: 25px; margin: 30px 0; border: 1px solid rgba(255,255,255,0.1);">
                                        <h3 style="margin: 0 0 15px; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; color: #9ca3af;">Access Details</h3>
                                        <table width="100%" cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td style="padding: 8px 0; color: #d1d5db; font-size: 14px;">📅 <strong>Expiry:</strong></td>
                                                <td style="padding: 8px 0; color: #ffffff; font-size: 14px; text-align: right;">{expiration_text}</td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0; color: #d1d5db; font-size: 14px;">📄 <strong>Documents:</strong></td>
                                                <td style="padding: 8px 0; color: #ffffff; font-size: 14px; text-align: right;">{document_count} files</td>
                                            </tr>
                                        </table>
                                        {password_text}
                                        {f"<p style='margin: 15px 0 0; font-size: 13px; color: #ef4444;'>{access_text}</p>" if access_text else ""}
                                    </div>
                                    
                                    <div style="text-align: center; margin: 40px 0;">
                                        <a href="{individual_url}" style="background: #8B5CF6; color: #ffffff; padding: 16px 32px; border-radius: 12px; text-decoration: none; font-weight: 700; font-size: 16px; display: inline-block; box-shadow: 0 10px 20px rgba(139, 92, 246, 0.3);">
                                            View Shared Documents
                                        </a>
                                        <p style="margin: 20px 0 0; font-size: 12px; color: #6b7280;">
                                            Or copy this link: <br>
                                            <a href="{individual_url}" style="color: #8B5CF6; text-decoration: none;">{individual_url}</a>
                                        </p>
                                    </div>
                                    
                                    <p style="margin: 30px 0 0; font-size: 14px; line-height: 1.6; color: #9ca3af; padding-top: 20px; border-top: 1px solid rgba(255,255,255,0.1);">
                                        If you didn't expect to receive this, you can safely ignore this email.
                                    </p>
                                </td>
                            </tr>
                            
                            <!-- Footer -->
                            <tr>
                                <td style="padding: 30px 40px; text-align: center; background: rgba(0,0,0,0.2); border-top: 1px solid rgba(255,255,255,0.05);">
                                    <p style="margin: 0 0 8px; font-size: 14px; color: #9ca3af;">
                                        Powered by DSuite
                                    </p>
                                    <p style="margin: 0; font-size: 12px; color: #6b7280;">
                                        © 2026 DSuite. All rights reserved.
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        \"\"\"
        
        try:
            # Create email message
            message = EmailMessage()
            message["Subject"] = subject
            message["From"] = "DSuite <noreply@dsuite.com>"
            message["To"] = recipient_email.strip()
            message.set_content("Please view this email in HTML format.")
            message.add_alternative(html_body, subtype="html")
            
            _send_email_message(message)
        except Exception as e:
            print(f"Failed to send email to {recipient_email}: {e}")


def get_shared_document(share_token: str) -> Optional[Dict[str, Any]]:
    """Retrieve shared document information by token (base or individual)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # First, try to find in shared_documents (base/anonymous token)
        cursor.execute("""
            SELECT * FROM shared_documents
            WHERE share_token = ?
        """, (share_token,))
        
        row = cursor.fetchone()
        recipient_email = None
        individual_access_level = None
        
        if not row:
            # If not found, try to find in recipients (individual token)
            cursor.execute("""
                SELECT r.*, s.*, s.id as share_id 
                FROM shared_document_recipients r
                JOIN shared_documents s ON r.share_id = s.id
                WHERE r.share_token = ?
            """, (share_token,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            recipient_email = row['email']
            individual_access_level = row['access_level']
        else:
            # Found base token - check if anonymous is allowed
            if not row['allow_anonymous']:
                return None
        
        share_data = dict(row)
        if 'share_id' in share_data: # If joined, use the correct share_id
            share_data['id'] = share_data['share_id']
            
        share_data['recipient_email'] = recipient_email
        share_data['individual_access_level'] = individual_access_level
        
        # Check if expired
        if share_data['expires_at']:
            try:
                expires_at = datetime.fromisoformat(share_data['expires_at'])
                if datetime.utcnow() > expires_at:
                    return None
            except:
                pass
        
        # Check if access limit reached (for 'once' access type)
        # Only check base access_count if it's not an individual token? 
        # Actually, for 'once', we usually mean once PER user if individual, or once TOTAL if anonymous.
        if share_data['access_type'] == 'once' and share_data['access_count'] > 0 and not recipient_email:
            return None
        
        # Get files
        cursor.execute("""
            SELECT * FROM shared_document_files
            WHERE share_id = ?
        """, (share_data['id'],))
        
        files = [dict(row) for row in cursor.fetchall()]
        share_data['files'] = files
        
        return share_data
        
    finally:
        conn.close()


def log_share_access(share_id: int, recipient_email: str = None, action: str = 'view', filename: str = None, ip_address: str = None, user_agent: str = None):
    """Log an access to a shared document."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Increment access count
        cursor.execute("""
            UPDATE shared_documents
            SET access_count = access_count + 1
            WHERE id = ?
        """, (share_id,))
        
        # Log access
        cursor.execute("""
            INSERT INTO shared_document_access_log
            (share_id, recipient_email, action, filename, ip_address, user_agent)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (share_id, recipient_email, action, filename, ip_address, user_agent))
        
        conn.commit()
    finally:
        conn.close()


def verify_share_password(share_id: int, password: str) -> bool:
    """Verify password for a password-protected share."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT password_hash FROM shared_documents
            WHERE id = ? AND require_password = 1
        """, (share_id,))
        
        row = cursor.fetchone()
        if not row or not row[0]:
            return False
        
        return hash_password(password) == row[0]
        
    finally:
        conn.close()
