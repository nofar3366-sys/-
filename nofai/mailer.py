"""New-inquiry e-mail notifications.

Without SMTP settings (local development) the notification is written to the log
instead. A failed send never loses the inquiry: it's already saved before this runs.
"""
import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app, url_for


def mail_configured() -> bool:
    cfg = current_app.config
    return bool(cfg["SMTP_HOST"] and cfg["NOTIFY_EMAIL"])


def send_inquiry_notification(inquiry) -> bool:
    """E-mail the owner about a new inquiry. Returns True when it was delivered."""
    cfg = current_app.config
    lines = [
        f"From: {inquiry.name}",
        f"Phone: {inquiry.phone or '-'}",
        f"Email: {inquiry.email or '-'}",
        f"Brand: {inquiry.company or '-'}",
        f"Interested in: {inquiry.service or '-'}",
        f"Language: {inquiry.language}",
        "",
        inquiry.message,
        "",
        "Open in the admin: " + url_for("admin.inquiry_detail", inquiry_id=inquiry.id, _external=True),
    ]
    body = "\n".join(lines)

    if not mail_configured():
        current_app.logger.info("New inquiry #%s (e-mail not configured):\n%s", inquiry.id, body)
        return False

    msg = EmailMessage()
    msg["Subject"] = f"NOFAI: new inquiry from {inquiry.name}"
    msg["From"] = cfg["MAIL_FROM"] or cfg["SMTP_USERNAME"]
    msg["To"] = cfg["NOTIFY_EMAIL"]
    if inquiry.email:
        msg["Reply-To"] = inquiry.email   # "Reply" in the mail client answers the visitor directly
    msg.set_content(body)
    try:
        with smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if cfg["SMTP_USERNAME"]:
                smtp.login(cfg["SMTP_USERNAME"], cfg["SMTP_PASSWORD"])
            smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        current_app.logger.warning("Could not e-mail inquiry #%s: %s", inquiry.id, exc)
        return False
