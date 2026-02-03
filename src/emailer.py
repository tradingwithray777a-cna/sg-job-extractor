import smtplib
from email.message import EmailMessage
import streamlit as st

def send_email_with_attachment(recipient, subject, body_text, attachment_bytes, attachment_filename):
    sender = st.secrets.get("SENDER_GMAIL")
    app_pw = st.secrets.get("GMAIL_APP_PASSWORD")

    if not sender or not app_pw:
        raise ValueError("Missing email secrets. Set SENDER_GMAIL and GMAIL_APP_PASSWORD in Streamlit Secrets.")

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body_text)

    msg.add_attachment(
        attachment_bytes,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=attachment_filename
    )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, app_pw)
        smtp.send_message(msg)

