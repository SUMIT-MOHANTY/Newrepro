import smtplib
import requests
import base64
import msal
from email.message import EmailMessage
from email.utils import formataddr
from typing import Optional

from config import settings


def ensure_email_delivery_configured() -> None:
    smtp_host = str(settings.smtp_host or "").strip()
    from_email = str(settings.smtp_from_email or "").strip()
    
    tenant_id = str(settings.microsoft_tenant_id or "").strip()
    client_id = str(settings.microsoft_client_id or "").strip()
    
    if (smtp_host and from_email) or (tenant_id and client_id and from_email):
        return
    raise RuntimeError(
        "Email delivery is not configured. Set SMTP_HOST or MICROSOFT_TENANT_ID/CLIENT_ID (and SMTP_FROM_EMAIL) before sending emails."
    )


def _from_header() -> str:
    display_name = str(settings.smtp_from_name or "").strip() or "DSuite"
    from_email = str(settings.smtp_from_email or "").strip()
    return formataddr((display_name, from_email))


def _build_registration_email(
    recipient_email: str,
    organization_name: str,
    generated_password: str,
    first_name: Optional[str] = None,
) -> EmailMessage:
    app_name = str(settings.smtp_from_name or "").strip() or "Dsuite"
    greeting_name = (first_name or "").strip() or "there"
    subject = f"Your {app_name} Admin Account for {organization_name}"
    
    text_body = (
        f"Hello {greeting_name},\n\n"
        f"Your {app_name} organization admin account for {organization_name} is ready.\n\n"
        f"Sign-in email: {recipient_email}\n"
        f"Password: {generated_password}\n\n"
        f"Use these credentials to sign in to {app_name}.\n\n"
        "Best regards,\n"
        f"The {app_name} Team"
    )

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>{subject}</title>
</head>
<body style="margin:0;padding:0;background-color:#0f1117;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">

  <!-- Outer wrapper -->
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#0f1117;padding:40px 16px;">
    <tr>
      <td align="center">

        <!-- Card -->
        <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;background-color:#16181f;border-radius:16px;overflow:hidden;border:1px solid #2a2d3a;">

          <!-- Hero header -->
          <tr>
            <td style="background:linear-gradient(135deg,#1a1f35 0%,#0f1117 60%,#0d1a2e 100%);padding:48px 40px 40px;text-align:center;border-bottom:1px solid #2a2d3a;position:relative;">
              <!-- Logo mark -->
              <table cellpadding="0" cellspacing="0" border="0" align="center" style="margin-bottom:20px;">
                <tr>
                  <td style="background:linear-gradient(135deg,#3b82f6,#1d4ed8);border-radius:14px;padding:12px 22px;">
                    <span style="color:#ffffff;font-size:20px;font-weight:800;letter-spacing:-0.5px;">{app_name}</span>
                  </td>
                </tr>
              </table>
              <h1 style="margin:0 0 8px;color:#f8fafc;font-size:26px;font-weight:700;letter-spacing:-0.5px;line-height:1.2;">Account Ready</h1>
              <p style="margin:0;color:#64748b;font-size:15px;">Your admin workspace is all set up</p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:40px 40px 32px;">
              <p style="margin:0 0 24px;color:#94a3b8;font-size:16px;line-height:1.7;">
                Hello <strong style="color:#e2e8f0;">{greeting_name}</strong>,
              </p>
              <p style="margin:0 0 32px;color:#94a3b8;font-size:15px;line-height:1.7;">
                Your admin account for <strong style="color:#e2e8f0;">{organization_name}</strong> has been created. Use the credentials below to sign in and start managing your workspace.
              </p>

              <!-- Credentials card -->
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#0f1117;border-radius:12px;border:1px solid #2a2d3a;overflow:hidden;margin-bottom:32px;">
                <!-- Card header stripe -->
                <tr>
                  <td colspan="2" style="background:linear-gradient(90deg,#1e3a5f,#1a2744);padding:10px 24px;">
                    <span style="color:#60a5fa;font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;">Sign-in Credentials</span>
                  </td>
                </tr>
                <!-- Email row -->
                <tr>
                  <td style="padding:18px 24px 0;width:40%;">
                    <span style="display:block;color:#475569;font-size:11px;font-weight:600;letter-spacing:1px;text-transform:uppercase;margin-bottom:5px;">Email Address</span>
                    <span style="display:block;color:#e2e8f0;font-size:15px;font-weight:500;font-family:'Courier New',Courier,monospace;">{recipient_email}</span>
                  </td>
                </tr>
                <!-- Divider -->
                <tr>
                  <td style="padding:16px 24px 0;">
                    <div style="height:1px;background-color:#1e2130;"></div>
                  </td>
                </tr>
                <!-- Password row -->
                <tr>
                  <td style="padding:16px 24px 20px;">
                    <span style="display:block;color:#475569;font-size:11px;font-weight:600;letter-spacing:1px;text-transform:uppercase;margin-bottom:5px;">Temporary Password</span>
                    <table cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td style="background-color:#1e2130;border-radius:6px;padding:8px 14px;border:1px solid #2d3548;">
                          <span style="color:#34d399;font-size:16px;font-weight:700;font-family:'Courier New',Courier,monospace;letter-spacing:1px;">{generated_password}</span>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <!-- Security notice -->
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#1a1f2e;border-left:3px solid #3b82f6;border-radius:0 8px 8px 0;margin-bottom:32px;">
                <tr>
                  <td style="padding:14px 18px;">
                    <p style="margin:0;color:#64748b;font-size:13px;line-height:1.6;">
                      &#128274;&nbsp; <strong style="color:#94a3b8;">Security tip:</strong> We recommend changing your password immediately after your first login.
                    </p>
                  </td>
                </tr>
              </table>

              <p style="margin:0;color:#94a3b8;font-size:14px;line-height:1.7;">
                Best regards,<br>
                <strong style="color:#e2e8f0;">The {app_name} Team</strong>
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:20px 40px;border-top:1px solid #1e2130;text-align:center;">
              <p style="margin:0 0 4px;color:#334155;font-size:12px;">&copy; 2026 {app_name}. All rights reserved.</p>
              <p style="margin:0;color:#1e293b;font-size:12px;">This is an automated message &mdash; please do not reply directly.</p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>

</body>
</html>"""

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = _from_header()
    message["To"] = recipient_email
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    return message


def _send_email_graph_api(message: EmailMessage, access_token: str, sender_email: str) -> None:
    endpoint = f"https://graph.microsoft.com/v1.0/users/{sender_email}/sendMail"
    
    subject = message["Subject"]
    to_recipient = message["To"]
    
    html_content = ""
    text_content = ""
    for part in message.walk():
        if part.get_content_type() == "text/html":
            html_content = part.get_content()
        elif part.get_content_type() == "text/plain":
            text_content = part.get_content()
    
    body_content = html_content if html_content else text_content
    body_type = "HTML" if html_content else "Text"

    payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": body_type,
                "content": body_content
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": to_recipient
                    }
                }
            ]
        },
        "saveToSentItems": "true"
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    response = requests.post(endpoint, json=payload, headers=headers)
    if not response.ok:
        raise RuntimeError(f"Microsoft Graph API failed: {response.status_code} {response.text}")


def _send_email_message(message: EmailMessage) -> None:
    sender_email = str(settings.smtp_from_email or "").strip()
    tenant_id = str(settings.microsoft_tenant_id or "").strip()
    client_id = str(settings.microsoft_client_id or "").strip()
    client_secret = str(settings.microsoft_client_secret or "").strip()

    if tenant_id and client_id:
        if not client_secret:
            raise RuntimeError("MICROSOFT_CLIENT_SECRET is missing. Please provide the client secret to use OAuth 2.0 Client Credentials.")
        
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        app = msal.ConfidentialClientApplication(
            client_id, authority=authority, client_credential=client_secret
        )
        
        scopes = ["https://graph.microsoft.com/.default"]
        result = app.acquire_token_silent(scopes, account=None)
        if not result:
            result = app.acquire_token_for_client(scopes=scopes)
        
        if "access_token" not in result:
            raise RuntimeError(f"Failed to acquire Microsoft OAuth token: {result.get('error')} - {result.get('error_description')}")
        
        access_token = result["access_token"]
        _send_email_graph_api(message, access_token, sender_email)
        return

    smtp_host = str(settings.smtp_host or "").strip()
    smtp_password = str(settings.smtp_password or "")
    timeout = max(int(settings.smtp_timeout_seconds or 20), 1)
    
    if not smtp_host:
        raise RuntimeError("No email delivery method configured (SMTP_HOST missing).")

    smtp_cls = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
    with smtp_cls(smtp_host, settings.smtp_port, timeout=timeout) as server:
        if not settings.smtp_use_ssl and settings.smtp_use_tls:
            server.ehlo()
            server.starttls()
            server.ehlo()
        if sender_email:
            server.login(sender_email, smtp_password)
        server.send_message(message)


def send_organization_registration_password_email(
    recipient_email: str,
    organization_name: str,
    generated_password: str,
    first_name: Optional[str] = None,
) -> None:
    ensure_email_delivery_configured()
    message = _build_registration_email(
        recipient_email=recipient_email,
        organization_name=organization_name,
        generated_password=generated_password,
        first_name=first_name,
    )
    _send_email_message(message)


def _build_invite_email(
    recipient_email: str,
    organization_name: str,
    role_name: str,
    invite_url: str,
) -> EmailMessage:
    app_name = str(settings.smtp_from_name or "").strip() or "Dsuite"
    subject = f"You're invited to join {organization_name} on {app_name}"
    
    text_body = (
        f"Hello,\n\n"
        f"You have been invited to join the {organization_name} organization on {app_name} as a {role_name}.\n\n"
        f"Accept your invitation here: {invite_url}\n\n"
        f"This link will expire soon.\n\n"
        f"Best regards,\n"
        f"The {app_name} Team"
    )

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
</head>
<body style="margin:0;padding:0;background-color:#0f1117;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">

  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#0f1117;padding:40px 16px;">
    <tr>
      <td align="center">

        <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;background-color:#16181f;border-radius:16px;overflow:hidden;border:1px solid #2a2d3a;">

          <tr>
            <td style="background:linear-gradient(135deg,#1a1f35 0%,#0f1117 60%,#0d1a2e 100%);padding:48px 40px 40px;text-align:center;border-bottom:1px solid #2a2d3a;">
              <table cellpadding="0" cellspacing="0" border="0" align="center" style="margin-bottom:20px;">
                <tr>
                  <td style="background:linear-gradient(135deg,#3b82f6,#1d4ed8);border-radius:14px;padding:12px 22px;">
                    <span style="color:#ffffff;font-size:20px;font-weight:800;letter-spacing:-0.5px;">{app_name}</span>
                  </td>
                </tr>
              </table>
              <h1 style="margin:0 0 8px;color:#f8fafc;font-size:26px;font-weight:700;letter-spacing:-0.5px;line-height:1.2;">You're Invited</h1>
              <p style="margin:0;color:#64748b;font-size:15px;">Join your team on the workspace</p>
            </td>
          </tr>

          <tr>
            <td style="padding:40px 40px 32px;">
              <p style="margin:0 0 24px;color:#94a3b8;font-size:16px;line-height:1.7;">
                Hello,
              </p>
              <p style="margin:0 0 32px;color:#94a3b8;font-size:15px;line-height:1.7;">
                You've been invited to join the <strong style="color:#e2e8f0;">{organization_name}</strong> organization as a <strong style="color:#e2e8f0;">{role_name}</strong>.
              </p>

              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:32px;">
                <tr>
                  <td align="center">
                    <a href="{invite_url}" style="background-color:#2563eb;color:#ffffff;padding:14px 28px;text-decoration:none;border-radius:10px;font-weight:700;font-size:16px;display:inline-block;">Accept Invitation</a>
                  </td>
                </tr>
              </table>

              <p style="margin:0;color:#64748b;font-size:13px;line-height:1.6;text-align:center;">
                If the button above doesn't work, copy and paste this link into your browser:<br>
                <a href="{invite_url}" style="color:#3b82f6;text-decoration:none;word-break:break-all;">{invite_url}</a>
              </p>

              <p style="margin:32px 0 0;color:#94a3b8;font-size:14px;line-height:1.7;">
                Best regards,<br>
                <strong style="color:#e2e8f0;">The {app_name} Team</strong>
              </p>
            </td>
          </tr>

          <tr>
            <td style="padding:20px 40px;border-top:1px solid #1e2130;text-align:center;">
              <p style="margin:0 0 4px;color:#334155;font-size:12px;">&copy; 2026 {app_name}. All rights reserved.</p>
              <p style="margin:0;color:#1e293b;font-size:12px;">This is an automated message &mdash; please do not reply.</p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>

</body>
</html>"""
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = _from_header()
    message["To"] = recipient_email
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    return message


def _build_admin_invite_notification(
    admin_email: str,
    organization_name: str,
    invitee_email: Optional[str],
    role_name: str,
    invite_url: str,
) -> EmailMessage:
    app_name = str(settings.smtp_from_name or "").strip() or "Dsuite"
    subject = f"Invite Link Created: {organization_name}"
    
    invite_type = invitee_email if invitee_email else "an Open Invite"
    
    text_body = (
        f"Hello Admin,\n\n"
        f"A new invite link has been created for the {organization_name} organization.\n\n"
        f"Role: {role_name}\n"
        f"Invited: {invite_type}\n"
        f"Invite Link: {invite_url}\n\n"
        f"You can forward this link to the intended recipient.\n\n"
        f"Best regards,\n"
        f"The {app_name} Team"
    )

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
</head>
<body style="margin:0;padding:0;background-color:#0f1117;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">

  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#0f1117;padding:40px 16px;">
    <tr>
      <td align="center">

        <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;background-color:#16181f;border-radius:16px;overflow:hidden;border:1px solid #2a2d3a;">

          <tr>
            <td style="background:linear-gradient(135deg,#1a1f35 0%,#0f1117 60%,#0d1a2e 100%);padding:40px 40px 32px;text-align:center;border-bottom:1px solid #2a2d3a;">
              <table cellpadding="0" cellspacing="0" border="0" align="center" style="margin-bottom:16px;">
                <tr>
                  <td style="background:linear-gradient(135deg,#3b82f6,#1d4ed8);border-radius:12px;padding:10px 20px;">
                    <span style="color:#ffffff;font-size:18px;font-weight:800;letter-spacing:-0.5px;">{app_name}</span>
                  </td>
                </tr>
              </table>
              <h1 style="margin:0;color:#f8fafc;font-size:22px;font-weight:700;letter-spacing:-0.5px;line-height:1.2;">Invite Created</h1>
            </td>
          </tr>

          <tr>
            <td style="padding:32px 40px;">
              <p style="margin:0 0 20px;color:#94a3b8;font-size:15px;line-height:1.6;">
                A new invite link has been generated. You can click the button below to share or preview it directly.
              </p>

              <div style="background-color:#0f1117;border-radius:12px;border:1px solid #2a2d3a;padding:24px;margin-bottom:24px;">
                <table width="100%" cellpadding="0" cellspacing="0" border="0">
                  <tr>
                    <td style="padding-bottom:12px;">
                      <span style="display:block;color:#475569;font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-bottom:4px;">Organization</span>
                      <span style="color:#e2e8f0;font-size:14px;font-weight:600;">{organization_name}</span>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding-bottom:12px;">
                      <span style="display:block;color:#475569;font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-bottom:4px;">Target Role</span>
                      <span style="color:#e2e8f0;font-size:14px;font-weight:600;">{role_name}</span>
                    </td>
                  </tr>
                  <tr>
                    <td>
                      <span style="display:block;color:#475569;font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-bottom:12px;">Invite Link</span>
                      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#1e2130;border-radius:10px;border:1px solid #2d3548;">
                        <tr>
                          <td align="center" style="padding:24px;">
                            <a href="{invite_url}" style="background-color:#2563eb;color:#ffffff;padding:14px 28px;text-decoration:none;border-radius:10px;font-weight:700;font-size:15px;display:inline-block;box-shadow:0 10px 15px -3px rgba(37, 99, 235, 0.2);">Open Invite Link</a>
                            <p style="margin:20px 0 0;color:#475569;font-size:11px;font-family:'Courier New',Courier,monospace;word-break:break-all;line-height:1.4;">
                              {invite_url}
                            </p>
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                </table>
              </div>

              <p style="margin:0;color:#94a3b8;font-size:14px;line-height:1.6;">
                Best regards,<br>
                <strong style="color:#e2e8f0;">The {app_name} Team</strong>
              </p>
            </td>
          </tr>

          <tr>
            <td style="padding:16px 40px;border-top:1px solid #1e2130;text-align:center;">
              <p style="margin:0;color:#334155;font-size:11px;">&copy; 2026 {app_name}. Automated Admin Notification.</p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>

</body>
</html>"""
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = _from_header()
    message["To"] = admin_email
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    return message


def _build_password_reset_email(
    recipient_email: str,
    reset_url: str,
) -> EmailMessage:
    app_name = str(settings.smtp_from_name or "").strip() or "Dsuite"
    subject = f"Reset Your {app_name} Password"
    
    text_body = (
        f"Hello,\n\n"
        f"We received a request to reset your password for your {app_name} account.\n\n"
        f"Click the link below to set a new password:\n"
        f"{reset_url}\n\n"
        f"If you did not request a password reset, please ignore this email.\n\n"
        f"Best regards,\n"
        f"The {app_name} Team"
    )

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
</head>
<body style="margin:0;padding:0;background-color:#0f1117;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">

  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#0f1117;padding:40px 16px;">
    <tr>
      <td align="center">

        <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;background-color:#16181f;border-radius:16px;overflow:hidden;border:1px solid #2a2d3a;">

          <tr>
            <td style="background:linear-gradient(135deg,#1a1f35 0%,#0f1117 60%,#0d1a2e 100%);padding:48px 40px 40px;text-align:center;border-bottom:1px solid #2a2d3a;">
              <table cellpadding="0" cellspacing="0" border="0" align="center" style="margin-bottom:20px;">
                <tr>
                  <td style="background:linear-gradient(135deg,#3b82f6,#1d4ed8);border-radius:14px;padding:12px 22px;">
                    <span style="color:#ffffff;font-size:20px;font-weight:800;letter-spacing:-0.5px;">{app_name}</span>
                  </td>
                </tr>
              </table>
              <h1 style="margin:0 0 8px;color:#f8fafc;font-size:26px;font-weight:700;letter-spacing:-0.5px;line-height:1.2;">Password Reset</h1>
              <p style="margin:0;color:#64748b;font-size:15px;">Securely update your account access</p>
            </td>
          </tr>

          <tr>
            <td style="padding:40px 40px 32px;">
              <p style="margin:0 0 24px;color:#94a3b8;font-size:16px;line-height:1.7;">
                Hello,
              </p>
              <p style="margin:0 0 32px;color:#94a3b8;font-size:15px;line-height:1.7;">
                We received a request to reset the password for your <strong style="color:#e2e8f0;">{app_name}</strong> account. Click the button below to choose a new password.
              </p>

              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:32px;">
                <tr>
                  <td align="center">
                    <a href="{reset_url}" style="background-color:#2563eb;color:#ffffff;padding:14px 28px;text-decoration:none;border-radius:10px;font-weight:700;font-size:16px;display:inline-block;box-shadow:0 10px 15px -3px rgba(37, 99, 235, 0.2);">Reset Password</a>
                  </td>
                </tr>
              </table>

              <p style="margin:0;color:#64748b;font-size:13px;line-height:1.6;text-align:center;">
                If you did not request a password reset, no further action is required. This link will expire in 1 hour.
              </p>

              <p style="margin:32px 0 0;color:#94a3b8;font-size:14px;line-height:1.7;">
                Best regards,<br>
                <strong style="color:#e2e8f0;">The {app_name} Team</strong>
              </p>
            </td>
          </tr>

          <tr>
            <td style="padding:20px 40px;border-top:1px solid #1e2130;text-align:center;">
              <p style="margin:0 0 4px;color:#334155;font-size:12px;">&copy; 2026 {app_name}. All rights reserved.</p>
              <p style="margin:0;color:#1e293b;font-size:12px;">This is an automated security message.</p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>

</body>
</html>"""
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = _from_header()
    message["To"] = recipient_email
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    return message


def send_password_reset_email(
    recipient_email: str,
    reset_url: str,
) -> None:
    ensure_email_delivery_configured()
    message = _build_password_reset_email(
        recipient_email=recipient_email,
        reset_url=reset_url,
    )
    _send_email_message(message)


def send_organization_invite_email(
    recipient_email: str,
    organization_name: str,
    role_name: str,
    invite_url: str,
) -> None:
    ensure_email_delivery_configured()
    message = _build_invite_email(
        recipient_email=recipient_email,
        organization_name=organization_name,
        role_name=role_name,
        invite_url=invite_url,
    )
    _send_email_message(message)


def send_invite_notification_to_admin(
    admin_email: str,
    organization_name: str,
    invitee_email: Optional[str],
    role_name: str,
    invite_url: str,
) -> None:
    ensure_email_delivery_configured()
    message = _build_admin_invite_notification(
        admin_email=admin_email,
        organization_name=organization_name,
        invitee_email=invitee_email,
        role_name=role_name,
        invite_url=invite_url,
    )
    _send_email_message(message)


def _build_access_request_email(
    recipient_email: str,
    requester_name: str,
    requester_email: str,
    organization_name: str,
    section_name: str,
) -> EmailMessage:
    app_name = str(settings.smtp_from_name or "").strip() or "Dsuite"
    subject = f"Access Request: {section_name} - {organization_name}"
    
    text_body = (
        f"Hello,\n\n"
        f"A user has requested access to the '{section_name}' section in the {organization_name} organization.\n\n"
        f"Requester Details:\n"
        f"Name: {requester_name}\n"
        f"Email: {requester_email}\n\n"
        f"Please review their access permissions in the Organization Admin panel.\n\n"
        f"Best regards,\n"
        f"The {app_name} Team"
    )

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
</head>
<body style="margin:0;padding:0;background-color:#0f1117;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#0f1117;padding:40px 16px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;background-color:#16181f;border-radius:16px;overflow:hidden;border:1px solid #2a2d3a;">
          <tr>
            <td style="background:linear-gradient(135deg,#1a1f35 0%,#0f1117 60%,#0d1a2e 100%);padding:40px 40px 32px;text-align:center;border-bottom:1px solid #2a2d3a;">
              <table cellpadding="0" cellspacing="0" border="0" align="center" style="margin-bottom:16px;">
                <tr>
                  <td style="background:linear-gradient(135deg,#3b82f6,#1d4ed8);border-radius:12px;padding:10px 20px;">
                    <span style="color:#ffffff;font-size:18px;font-weight:800;letter-spacing:-0.5px;">{app_name}</span>
                  </td>
                </tr>
              </table>
              <h1 style="margin:0;color:#f8fafc;font-size:22px;font-weight:700;letter-spacing:-0.5px;line-height:1.2;">Access Request</h1>
            </td>
          </tr>
          <tr>
            <td style="padding:32px 40px;">
              <p style="margin:0 0 20px;color:#94a3b8;font-size:15px;line-height:1.6;">
                A user has requested access to the <strong style="color:#e2e8f0;">{section_name}</strong> section.
              </p>
              <div style="background-color:#0f1117;border-radius:12px;border:1px solid #2a2d3a;padding:24px;margin-bottom:24px;">
                <table width="100%" cellpadding="0" cellspacing="0" border="0">
                  <tr>
                    <td style="padding-bottom:12px;">
                      <span style="display:block;color:#475569;font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-bottom:4px;">Organization</span>
                      <span style="color:#e2e8f0;font-size:14px;font-weight:600;">{organization_name}</span>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding-bottom:12px;">
                      <span style="display:block;color:#475569;font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-bottom:4px;">Requester Name</span>
                      <span style="color:#e2e8f0;font-size:14px;font-weight:600;">{requester_name}</span>
                    </td>
                  </tr>
                  <tr>
                    <td>
                      <span style="display:block;color:#475569;font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-bottom:4px;">Requester Email</span>
                      <span style="color:#e2e8f0;font-size:14px;font-weight:600;">{requester_email}</span>
                    </td>
                  </tr>
                </table>
              </div>
              <p style="margin:0;color:#94a3b8;font-size:14px;line-height:1.6;">
                Best regards,<br>
                <strong style="color:#e2e8f0;">The {app_name} Team</strong>
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = _from_header()
    message["To"] = recipient_email
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    return message


def send_access_request_email(
    recipient_email: str,
    requester_name: str,
    requester_email: str,
    organization_name: str,
    section_name: str,
) -> None:
    ensure_email_delivery_configured()
    message = _build_access_request_email(
        recipient_email=recipient_email,
        requester_name=requester_name,
        requester_email=requester_email,
        organization_name=organization_name,
        section_name=section_name,
    )
    _send_email_message(message)