"""
Service for sharing BRD documents with external users via secure links.
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

# Database path
DB_PATH = os.getenv("DATABASE_PATH", "brd_analyzer.db")


# Tables are created via migration: add_share_brd_tables.py


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
    
    Args:
        user_id: ID of the user creating the share
        title: Title for the shared document collection
        config: Configuration dict with access_type, expiration_time, require_password, password
        file_paths: List of dicts with file information (filename, path, size, type)
    
    Returns:
        Dict with share_token and share_url
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Generate unique share token
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
            (share_token, user_id, title, access_type, expiration_time, expires_at, require_password, password_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            share_token,
            user_id,
            title,
            config.get('dashboardAccess', 'once'),
            config.get('expirationTime', 'no-expiration'),
            expires_at,
            1 if config.get('requirePassword') else 0,
            password_hash
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


def add_share_recipients(share_id: int, emails: List[str]):
    """Add recipient emails to a shared document."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        for email in emails:
            if email.strip():
                cursor.execute("""
                    INSERT INTO shared_document_recipients (share_id, email)
                    VALUES (?, ?)
                """, (share_id, email.strip()))
        
        conn.commit()
    finally:
        conn.close()


def send_share_notification_emails(
    share_url: str,
    recipients: List[str],
    sender_name: str,
    document_count: int,
    config: Dict[str, Any]
):
    """Send email notifications to recipients about shared documents."""
    
    for recipient_email in recipients:
        if not recipient_email.strip():
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
        
        html_body = f"""
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
                                    <h1 style="margin: 0; font-size: 32px; font-weight: 700; color: #ffffff; text-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                                        📄 Documents Shared With You
                                    </h1>
                                </td>
                            </tr>
                            
                            <!-- Body -->
                            <tr>
                                <td style="padding: 40px;">
                                    <p style="margin: 0 0 20px; font-size: 16px; line-height: 1.6; color: #e5e7eb;">
                                        Hi there,
                                    </p>
                                    
                                    <p style="margin: 0 0 20px; font-size: 16px; line-height: 1.6; color: #e5e7eb;">
                                        <strong style="color: #ffffff;">{sender_name}</strong> has shared <strong>{document_count}</strong> document{"s" if document_count != 1 else ""} with you via DSuite.
                                    </p>
                                    
                                    <!-- Info Box -->
                                    <table width="100%" cellpadding="0" cellspacing="0" style="margin: 30px 0; background: rgba(139, 92, 246, 0.1); border: 2px solid #8B5CF6; border-radius: 12px;">
                                        <tr>
                                            <td style="padding: 24px;">
                                                <p style="margin: 0 0 12px; font-size: 14px; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.5px;">
                                                    Access Details
                                                </p>
                                                <p style="margin: 0 0 8px; font-size: 14px; color: #e5e7eb;">
                                                    📅 {expiration_text}
                                                </p>
                                                {f'<p style="margin: 0; font-size: 14px; color: #FCD34D;">{access_text}</p>' if access_text else ''}
                                                {password_text}
                                            </td>
                                        </tr>
                                    </table>
                                    
                                    <!-- CTA Button -->
                                    <table width="100%" cellpadding="0" cellspacing="0" style="margin: 30px 0;">
                                        <tr>
                                            <td align="center">
                                                <a href="{share_url}?r={recipient_email.strip()}" style="display: inline-block; padding: 16px 40px; background: linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%); color: #ffffff; text-decoration: none; border-radius: 10px; font-weight: 600; font-size: 16px; box-shadow: 0 4px 12px rgba(139, 92, 246, 0.4);">
                                                    View Documents
                                                </a>
                                            </td>
                                        </tr>
                                    </table>
                                    
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
        """
        
        try:
            # Create email message
            message = EmailMessage()
            message["Subject"] = subject
            message["From"] = "DSuite <noreply@dsuite.com>"  # You may want to make this configurable
            message["To"] = recipient_email.strip()
            message.set_content("Please view this email in HTML format.")
            message.add_alternative(html_body, subtype="html")
            
            _send_email_message(message)
        except Exception as e:
            print(f"Failed to send email to {recipient_email}: {e}")


def get_shared_document(share_token: str) -> Optional[Dict[str, Any]]:
    """Retrieve shared document information by token."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT * FROM shared_documents
            WHERE share_token = ?
        """, (share_token,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        share_data = dict(row)
        
        # Check if expired
        if share_data['expires_at']:
            expires_at = datetime.fromisoformat(share_data['expires_at'])
            if datetime.utcnow() > expires_at:
                return None
        
        # Check if access limit reached (for 'once' access type)
        if share_data['access_type'] == 'once' and share_data['access_count'] > 0:
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


def log_share_access(share_id: int, ip_address: str = None, user_agent: str = None):
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
            (share_id, ip_address, user_agent)
            VALUES (?, ?, ?)
        """, (share_id, ip_address, user_agent))
        
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


# Database tables are managed via migrations
