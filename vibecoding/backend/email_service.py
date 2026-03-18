"""
Email service using Microsoft Graph API for sending emails.
"""

import os
import requests
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Microsoft Graph API Configuration
MICROSOFT_TENANT_ID = os.getenv("MICROSOFT_TENANT_ID")
MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")
MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "noreply.dsuite@bourntec.com")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "VibeCoding")
SMTP_TIMEOUT_SECONDS = int(os.getenv("SMTP_TIMEOUT_SECONDS", "20"))


class EmailService:
    """Email service using Microsoft Graph API."""
    
    def __init__(self):
        self.tenant_id = MICROSOFT_TENANT_ID
        self.client_id = MICROSOFT_CLIENT_ID
        self.client_secret = MICROSOFT_CLIENT_SECRET
        self.from_email = SMTP_FROM_EMAIL
        self.from_name = SMTP_FROM_NAME
        self.timeout = SMTP_TIMEOUT_SECONDS
        self._access_token = None
        self._token_expiry = 0
    
    def _get_access_token(self) -> Optional[str]:
        """Get OAuth2 access token using client credentials flow."""
        import time
        
        # Return cached token if still valid
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token
        
        if not all([self.tenant_id, self.client_id, self.client_secret]):
            logger.error("Microsoft Graph API credentials not configured")
            return None
        
        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials"
        }
        
        try:
            response = requests.post(token_url, data=data, timeout=self.timeout)
            response.raise_for_status()
            token_data = response.json()
            
            self._access_token = token_data.get("access_token")
            # Cache token for 50 minutes (tokens are valid for 60 minutes)
            self._token_expiry = time.time() + 3000
            
            return self._access_token
        except Exception as e:
            logger.error(f"Failed to get access token: {e}")
            return None
    
    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None
    ) -> bool:
        """
        Send an email using Microsoft Graph API.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML email body
            text_body: Plain text email body (optional)
        
        Returns:
            True if email sent successfully, False otherwise
        """
        access_token = self._get_access_token()
        if not access_token:
            logger.error("Cannot send email: no access token")
            return False
        
        # Microsoft Graph API endpoint for sending mail
        send_mail_url = f"https://graph.microsoft.com/v1.0/users/{self.from_email}/sendMail"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Build email message
        message = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": html_body
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": to_email
                        }
                    }
                ],
                "from": {
                    "emailAddress": {
                        "address": self.from_email,
                        "name": self.from_name
                    }
                }
            },
            "saveToSentItems": "false"
        }
        
        try:
            response = requests.post(
                send_mail_url,
                headers=headers,
                json=message,
                timeout=self.timeout
            )
            response.raise_for_status()
            logger.info(f"Email sent successfully to {to_email}")
            return True
        except requests.exceptions.HTTPError as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            logger.error(f"Response: {e.response.text if e.response else 'No response'}")
            return False
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False
    
    def send_welcome_email(self, to_email: str, username: str, password: str) -> bool:
        """
        Send welcome email with generated password.
        
        Args:
            to_email: User's email address
            username: User's username
            password: Generated password
        
        Returns:
            True if email sent successfully, False otherwise
        """
        subject = f"Welcome to {self.from_name}!"
        
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
                                        Welcome to VibeCoding! 🎉
                                    </h1>
                                </td>
                            </tr>
                            
                            <!-- Body -->
                            <tr>
                                <td style="padding: 40px;">
                                    <p style="margin: 0 0 20px; font-size: 16px; line-height: 1.6; color: #e5e7eb;">
                                        Hi <strong style="color: #ffffff;">{username}</strong>,
                                    </p>
                                    
                                    <p style="margin: 0 0 20px; font-size: 16px; line-height: 1.6; color: #e5e7eb;">
                                        Your account has been created successfully! We've generated a secure password for you to get started.
                                    </p>
                                    
                                    <!-- Credentials Box -->
                                    <table width="100%" cellpadding="0" cellspacing="0" style="margin: 30px 0; background: rgba(139, 92, 246, 0.1); border: 2px solid #8B5CF6; border-radius: 12px; overflow: hidden;">
                                        <tr>
                                            <td style="padding: 24px;">
                                                <p style="margin: 0 0 12px; font-size: 14px; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.5px;">
                                                    Your Login Credentials
                                                </p>
                                                <p style="margin: 0 0 8px; font-size: 14px; color: #e5e7eb;">
                                                    <strong style="color: #8B5CF6;">Email:</strong> {to_email}
                                                </p>
                                                <p style="margin: 0 0 8px; font-size: 14px; color: #e5e7eb;">
                                                    <strong style="color: #8B5CF6;">Username:</strong> {username}
                                                </p>
                                                <p style="margin: 0; font-size: 14px; color: #e5e7eb;">
                                                    <strong style="color: #8B5CF6;">Password:</strong> 
                                                    <code style="background: rgba(0,0,0,0.3); padding: 4px 8px; border-radius: 4px; font-family: 'Courier New', monospace; color: #EC4899; font-size: 16px; font-weight: 600;">
                                                        {password}
                                                    </code>
                                                </p>
                                            </td>
                                        </tr>
                                    </table>
                                    
                                    <p style="margin: 0 0 20px; font-size: 16px; line-height: 1.6; color: #e5e7eb;">
                                        For security reasons, we recommend changing your password after your first login.
                                    </p>
                                    
                                    <!-- CTA Button -->
                                    <table width="100%" cellpadding="0" cellspacing="0" style="margin: 30px 0;">
                                        <tr>
                                            <td align="center">
                                                <a href="https://dsuite.bourntec.com/vibecoding/login" style="display: inline-block; padding: 14px 32px; background: linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%); color: #ffffff; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px; box-shadow: 0 4px 12px rgba(139, 92, 246, 0.4);">
                                                    Login to Your Account
                                                </a>
                                            </td>
                                        </tr>
                                    </table>
                                    
                                    <p style="margin: 30px 0 0; font-size: 14px; line-height: 1.6; color: #9ca3af; padding-top: 20px; border-top: 1px solid rgba(255,255,255,0.1);">
                                        If you didn't create this account, please ignore this email or contact our support team.
                                    </p>
                                </td>
                            </tr>
                            
                            <!-- Footer -->
                            <tr>
                                <td style="padding: 30px 40px; text-align: center; background: rgba(0,0,0,0.2); border-top: 1px solid rgba(255,255,255,0.05);">
                                    <p style="margin: 0 0 8px; font-size: 14px; color: #9ca3af;">
                                        Happy coding! 🚀
                                    </p>
                                    <p style="margin: 0; font-size: 12px; color: #6b7280;">
                                        © 2026 VibeCoding. All rights reserved.
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
        
        return self.send_email(to_email, subject, html_body)
    
    def send_password_reset_email(self, to_email: str, username: str, new_password: str) -> bool:
        """Send password reset email with new generated password."""
        subject = "Password Reset - VibeCoding"
        html_body = f"""<!DOCTYPE html><html><body style="margin:0;padding:0;font-family:Arial,sans-serif;background:#0A0A0F;color:#fff"><table width="100%" cellpadding="0" cellspacing="0" style="background:#0A0A0F"><tr><td align="center" style="padding:40px 20px"><table width="600" cellpadding="0" cellspacing="0" style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);border-radius:16px;overflow:hidden"><tr><td style="padding:40px;text-align:center;background:linear-gradient(135deg,#8B5CF6 0%,#EC4899 100%)"><h1 style="margin:0;font-size:32px;color:#fff">Password Reset 🔐</h1></td></tr><tr><td style="padding:40px"><p style="margin:0 0 20px;font-size:16px;color:#e5e7eb">Hi <strong>{username}</strong>,</p><p style="margin:0 0 20px;font-size:16px;color:#e5e7eb">We've generated a new secure password for you.</p><table width="100%" cellpadding="0" cellspacing="0" style="margin:30px 0;background:rgba(139,92,246,0.1);border:2px solid #8B5CF6;border-radius:12px"><tr><td style="padding:24px"><p style="margin:0 0 12px;font-size:14px;color:#9ca3af">Your New Password</p><p style="margin:0"><code style="background:rgba(0,0,0,0.3);padding:8px 12px;border-radius:4px;font-family:monospace;color:#EC4899;font-size:18px;font-weight:600">{new_password}</code></p></td></tr></table><p style="margin:0 0 20px;font-size:16px;color:#e5e7eb">You can now login with this new password.</p></td></tr></table></td></tr></table></body></html>"""
        return self.send_email(to_email, subject, html_body)


# Global email service instance
email_service = EmailService()
