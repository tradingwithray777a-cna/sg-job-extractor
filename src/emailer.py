from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path


def send_gmail(
    sender_gmail: str,
    app_password: str,
    recipient: str,
    subject: str,
    body: str,
    attachment_path: str
) -> None:
    """
    Sends an email using Gmail SMTP with an App Password and attaches an Excel file.
    """
    sender_gmail = (sender_gmail or "").strip()
    app_password = (app_password or "").replace(" ", "").strip()
    recipient = (recipient or "").strip()

    if not sender_gmail or not app_password:
        raise ValueError("Missing sender Gmail or app password.")

    msg = EmailMessage()
    msg["From"] = sender_gmail
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)

    p = Path(attachment_path)
    data = p.read_bytes()
    msg.add_attachment(
        data,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=p.name
    )

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(sender_gmail, app_password)
        server.send_message(msg)
