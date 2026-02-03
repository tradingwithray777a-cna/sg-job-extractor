import streamlit as st
from src.runner import run_job_search
from src.excel_writer import build_excel_bytes
from src.emailer import send_email_with_attachment

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

# Default to a set that often has accessible pages
default_portals = [
    "MyCareersFuture",
    "Careers.gov.sg",
    "JobStreet Singapore",
    "Indeed Singapore",
    "Foundit",
    "GrabJobs",
    "FastJobs",
    "Glassdoor Singapore",
    "LinkedIn Jobs",
]

selected_portals = st.multiselect(
    "Select job portals to extract from",
    options=PORTALS_ALL,
    default=default_portals
)

gmail_only = st.checkbox("Restrict recipient to Gmail only", value=True)
recipient_email = st.text_input("Recipient email (to receive the Excel)", value="")

col1, col2, col3 = st.columns([1,1,2])
with col1:
    max_results = st.number_input("Max final unique jobs", min_value=10, max_value=100, value=100, step=10)
with col2:
    prefer_fulltime = st.checkbox("Prefer full-time", value=True)

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

    with st.spinner("Running extraction, scoring, dedupe & Excel generation..."):
        result = run_job_search(
            target_role=TARGET_ROLE.strip(),
            posted_within_days=int(days),
            selected_portals=selected_portals,
            max_final=int(max_results),
            prefer_fulltime=prefer_fulltime,
        )

        df_jobs = result["jobs_df"]
        notes = result["notes_dict"]

        excel_bytes = build_excel_bytes(df_jobs, notes)
        st.success(f"Done. Final unique jobs: {len(df_jobs)}")

        st.download_button(
            label="Download Excel (.xlsx)",
            data=excel_bytes,
            file_name=f"SG_{TARGET_ROLE.strip().replace(' ','_')}_Jobs.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.subheader("Preview (top 20)")
        st.dataframe(df_jobs.head(20), use_container_width=True)

        if recipient_email.strip():
            try:
                send_email_with_attachment(
                    recipient=recipient_email.strip(),
                    subject=f"SG Job Extractor: {TARGET_ROLE.strip()} (Top {len(df_jobs)})",
                    body_text="Attached is your curated Excel file (Jobs + Notes).",
                    attachment_bytes=excel_bytes,
                    attachment_filename=f"SG_{TARGET_ROLE.strip().replace(' ','_')}_Jobs.xlsx"
                )
                st.success(f"Emailed to {recipient_email.strip()}")
            except Exception as e:
                st.error(f"Email failed: {e}")
                st.info("You can still download via the button above.")

