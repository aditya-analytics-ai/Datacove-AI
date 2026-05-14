"""
utils/email_sender.py - SMTP email utility for Datacove.

Reads configuration from environment variables (or .env via config.py):
  SMTP_HOST     - SMTP server hostname  (default: localhost)
  SMTP_PORT     - SMTP port            (default: 587 / STARTTLS)
  SMTP_USER     - SMTP login username
  SMTP_PASS     - SMTP login password (app password for Gmail)
  SMTP_FROM     - From address          (default: noreply@datacove.ai)
  SMTP_TLS      - "true"|"false"        (default: true)

If SMTP_HOST is not set, send_email() returns False and logs a warning -
the app continues working, it just won't send emails.

Quick setup examples
─────────────────────
Gmail:
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  SMTP_USER=you@gmail.com
  SMTP_PASS=xxxx-xxxx-xxxx-xxxx   # 16-char Google App Password
  SMTP_FROM=you@gmail.com

SendGrid:
  SMTP_HOST=smtp.sendgrid.net
  SMTP_PORT=587
  SMTP_USER=apikey
  SMTP_PASS=SG.xxxxxxxxxxxxxxxxxxxx
  SMTP_FROM=noreply@yourapp.com
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from utils.logger import logger

# ── Config from env ───────────────────────────────────────────────────────────
_HOST  = os.getenv("SMTP_HOST", "")
_PORT  = int(os.getenv("SMTP_PORT", "587"))
_USER  = os.getenv("SMTP_USER", "")
_PASS  = os.getenv("SMTP_PASS", "")
_FROM  = os.getenv("SMTP_FROM", "noreply@datacove.ai")
_TLS   = os.getenv("SMTP_TLS", "true").lower() != "false"

# Optional: base URL for reset links (set FRONTEND_URL in .env)
_FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")


def is_configured() -> bool:
    """True if SMTP credentials are set in the environment."""
    return bool(_HOST and _USER and _PASS)


def send_email(
    to: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
) -> bool:
    """
    Send an email. Returns True on success, False on failure.
    Does NOT raise - caller can decide how to handle failed sends.
    """
    if not is_configured():
        logger.warning(
            "Email: SMTP not configured (SMTP_HOST/SMTP_USER/SMTP_PASS missing). "
            "Email skipped. Set these env vars to enable email delivery."
        )
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = _FROM
    msg["To"]      = to

    if text_body:
        msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(_HOST, _PORT, timeout=15) as server:
            if _TLS:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
            if _USER:
                server.login(_USER, _PASS)
            server.sendmail(_FROM, [to], msg.as_string())
        logger.info(f"Email: sent '{subject}' → {to}")
        return True
    except Exception as exc:
        logger.error(f"Email: failed to send '{subject}' → {to}: {exc}")
        return False


def send_password_reset_email(to: str, username: str, token: str) -> bool:
    """Send a password reset email with a pre-built reset link."""
    reset_link = f"{_FRONTEND_URL}/reset-password?token={token}"

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family:Inter,Arial,sans-serif;background:#06080c;color:#f8fafc;padding:40px">
      <div style="max-width:480px;margin:0 auto;background:#0d1017;border:1px solid #222a3f;
                  border-radius:16px;padding:32px">
        <h2 style="color:#818cf8;margin-top:0">🔐 Reset your Datacove password</h2>
        <p>Hi <strong>{username}</strong>,</p>
        <p>We received a request to reset your password. Click the button below
           to set a new password. This link expires in <strong>1 hour</strong>.</p>
        <a href="{reset_link}"
           style="display:inline-block;margin:20px 0;padding:12px 28px;
                  background:linear-gradient(135deg,#6366f1,#c026d3);
                  color:#fff;border-radius:8px;text-decoration:none;
                  font-weight:700;font-size:14px">
          Reset Password
        </a>
        <p style="color:#808b9f;font-size:12px;margin-top:20px">
          If you didn't request this, you can safely ignore this email.
          Your password will not change.<br><br>
          Or copy this link into your browser:<br>
          <a href="{reset_link}" style="color:#818cf8">{reset_link}</a>
        </p>
        <hr style="border:none;border-top:1px solid #222a3f;margin:24px 0">
        <p style="color:#475569;font-size:11px;margin:0">Datacove AI · Data Cleaning Platform</p>
      </div>
    </body>
    </html>
    """

    text = (
        f"Hi {username},\n\n"
        f"Reset your Datacove password using this link (expires in 1 hour):\n"
        f"{reset_link}\n\n"
        f"If you didn't request this, ignore this email.\n"
    )

    return send_email(to, "Reset your Datacove password", html, text)
