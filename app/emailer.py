from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.config import Settings


def send_login_code(settings: Settings, *, email: str, code: str) -> None:
    if not settings.smtp_host:
        return

    message = EmailMessage()
    message["Subject"] = "Код входа TemichevVet"
    message["From"] = settings.smtp_from_email or settings.smtp_username
    message["To"] = email
    message.set_content(
        "Ваш код входа в TemichevVet:\n\n"
        f"{code}\n\n"
        "Код действует 10 минут. Если вы не запрашивали вход, просто игнорируйте письмо."
    )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
