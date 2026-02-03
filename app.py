import streamlit as st
from datetime import datetime

from src.runner import run_search
from src.emailer import send_gmail

st.set_page_config(page_title="SG Job Extractor", layout="wide")
st.title("Singapore Job Search Extractor (Web)")

st.caption("Generate a curated Excel of jobs across selected portals and email it to a Gmail address.")

TARGET_ROLE = st.text_input("Job title keywords", value="Community Partnership")
days = st.number_input("Posted within (days)", min_value=1, max_value=365, value=30, step=1)

PORTALS_ALL = [
    "MyCareersFuture",
    "Careers.gov.sg",
    "LinkedIn Jobs",
    "JobStreet Singapore",
    "Indeed Singapore",
    "Foundit",
    "Glints",
    "JobsDB",
    "STJobs",
    "FINDSG Jobs",
    "GrabJobs",
    "FastJobs",
    "CakeResume",
    "Glassdoor Singapore",
    "NUS TalentConnect",
    "JobsnProfiles",
]

# Only these 4 have working connectors in the current build
WORKING_PORTALS = ["MyCareersFuture", "GrabJobs", "Foundit", "FastJobs"]

default_portals = ["MyCareersFuture", "GrabJobs", "Foundit", "FastJobs"]

selected_portals = st.multiselect(
    "Select job portals to extract from (currently supported portals only)",
    options=WORKING_PORTALS,
    default=default_portals
)

gmail_only = st.checkbox("Restrict recipient to Gmail only", value=True)
recipient_email = st.text_input("Recipient email (to receive the Excel)", value="")

col1, col2 = st.columns([1, 1])
with col1:
    max_results = st.number_input("Max final unique jobs", min_value=10, max_value=100, value=100, step=10)
with col2:
    pass

run_btn = st.button("Run search → generate Excel", type="primary")


def is_valid_email(email: str) -> bool:
    return "@" in email and "." in email


def is_gmail(email: str) -> bool:
    e = (email or "").strip().lower()
    return e.endswith("@gmail.com") or e.endswith("@googlemail.com")


if run_btn:
    if not TARGET_ROLE.strip():
        st.error("Please enter a job title / keyword.")
        st.stop()

    if recipient_email.strip():
        if not is_valid_email(recipient_email):
            st.error("Please enter a valid email address.")
            st.stop()
        if gmail_only and not is_gmail(recipient_email):
            st.error("Gmail-only is enabled. Please use a @gmail.com address (or uncheck Gmail-only).")
            st.stop()

    out_name = f"SG_{TARGET_ROLE.strip().replace(' ', '_')}_Jobs_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.xlsx"

    with st.spinner("Running extraction, scoring, dedupe & Excel generation..."):
        out_path = run_search(
            target_role=TARGET_ROLE.strip(),
            posted_within_days=int(days),
            selected_portals=selected_portals,
            max_final=int(max_results),
            raw_cap=200,
            out_path=out_name,
        )

    st.success("Done. Excel generated.")

    with open(out_path, "rb") as f:
        st.download_button(
            label="Download Excel (.xlsx)",
            data=f,
            file_name=out_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    if recipient_email.strip():
        try:
            sender = st.secrets.get("SENDER_GMAIL", "")
            app_pw = st.secrets.get("GMAIL_APP_PASSWORD", "")
            if not sender or not app_pw:
                st.error("Missing Streamlit Secrets: SENDER_GMAIL / GMAIL_APP_PASSWORD")
            else:
                send_gmail(
                    sender_gmail=sender,
                    app_password=app_pw,
                    recipient=recipient_email.strip(),
                    subject=f"SG Job Extractor: {TARGET_ROLE.strip()}",
                    body="Attached is your curated Excel file (Jobs + Notes).",
                    attachment_path=out_path,
                )
                st.success(f"Emailed to {recipient_email.strip()}")
        except Exception as e:
            st.error(f"Email failed: {e}")
            st.info("You can still download via the button above.")
