import os
import smtplib
from email.message import EmailMessage

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8501")
FROM_ADDR = os.getenv("FROM_EMAIL", "noreply@example.com")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587")) if os.getenv("SMTP_PORT") else None
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")


def send_verification_email(to_email: str, otp: str):
    subject = "Your verification code"
    body = f"Your verification code is: {otp}\n\nIt will expire in about 10 minutes.\n\nIf you didn't request this, ignore this message."

    # If SMTP settings are not provided, just log the URL (developer mode)
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        print(f"[EMAIL] To: {to_email}\nSubject: {subject}\n{body}")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = FROM_ADDR
    msg["To"] = to_email
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT or 587) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)


def send_reset_link_email(to_email: str, reset_token: str):
    reset_link = f"{FRONTEND_URL}/Reset?reset_token={reset_token}"
    subject = "Password reset link"
    body = (
        "Click the link below to reset your password:\n\n"
        f"{reset_link}\n\n"
        "If you didn't request this, ignore this message."
    )

    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        print(f"[EMAIL] To: {to_email}\nSubject: {subject}\n{body}")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = FROM_ADDR
    msg["To"] = to_email
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT or 587) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)


def send_reset_otp_email(to_email: str, otp: str):
    subject = "Your password reset code"
    body = f"Your password reset code is: {otp}\n\nIt will expire in about 10 minutes."

    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        print(f"[EMAIL] To: {to_email}\nSubject: {subject}\n{body}")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = FROM_ADDR
    msg["To"] = to_email
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT or 587) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
