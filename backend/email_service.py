import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from typing import Optional

from config import settings


def ensure_email_delivery_configured() -> None:
    smtp_host = str(settings.smtp_host or "").strip()
    from_email = str(settings.smtp_from_email or "").strip()
    if smtp_host and from_email:
        return
    raise RuntimeError(
        "Email delivery is not configured. Set SMTP_HOST and SMTP_FROM_EMAIL before registering organizations."
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
    greeting_name = (first_name or "").strip() or "there"
    subject = f"{organization_name} DSuite admin account password"
    text_body = (
        f"Hello {greeting_name},\n\n"
        f"Your DSuite organization admin account for {organization_name} is ready.\n\n"
        f"Sign-in email: {recipient_email}\n"
        f"Password: {generated_password}\n\n"
        "Use these credentials to sign in to DSuite.\n\n"
        "Regards,\n"
        f"{str(settings.smtp_from_name or '').strip() or 'DSuite'}\n"
    )
    html_body = (
        f"<p>Hello {greeting_name},</p>"
        f"<p>Your DSuite organization admin account for <strong>{organization_name}</strong> is ready.</p>"
        "<p>"
        f"<strong>Sign-in email:</strong> {recipient_email}<br />"
        f"<strong>Password:</strong> {generated_password}"
        "</p>"
        "<p>Use these credentials to sign in to DSuite.</p>"
        f"<p>Regards,<br />{str(settings.smtp_from_name or '').strip() or 'DSuite'}</p>"
    )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = _from_header()
    message["To"] = recipient_email
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    return message


def send_organization_registration_password_email(
    recipient_email: str,
    organization_name: str,
    generated_password: str,
    first_name: Optional[str] = None,
) -> None:
    ensure_email_delivery_configured()
    smtp_host = str(settings.smtp_host or "").strip()
    smtp_username = str(settings.smtp_username or "").strip()
    smtp_password = str(settings.smtp_password or "")
    timeout = max(int(settings.smtp_timeout_seconds or 20), 1)
    message = _build_registration_email(
        recipient_email=recipient_email,
        organization_name=organization_name,
        generated_password=generated_password,
        first_name=first_name,
    )

    smtp_cls = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
    with smtp_cls(smtp_host, settings.smtp_port, timeout=timeout) as server:
        if not settings.smtp_use_ssl and settings.smtp_use_tls:
            server.ehlo()
            server.starttls()
            server.ehlo()
        if smtp_username:
            server.login(smtp_username, smtp_password)
        server.send_message(message)
