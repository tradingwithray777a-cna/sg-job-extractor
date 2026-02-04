import streamlit as st
from src.runner import run_search

st.set_page_config(page_title="SG Job Extractor", layout="wide")
st.title("SG Job Extractor (Web)")
st.caption("Search selected SG job portals, score relevance, and export Excel (Jobs + Notes).")

TARGET_ROLE = st.text_input("Job title keywords", value="Community Partnership")
days = st.number_input("Posted within (days)", min_value=1, max_value=365, value=30, step=1)

PORTALS_ALL = [
    "MyCareersFuture",
    "Foundit",
    "FastJobs",
]

default_portals = [
    "MyCareersFuture",
    "FastJobs",
]

selected_portals = st.multiselect(
    "Select job portals to extract from",
    options=PORTALS_ALL,
    default=default_portals
)

max_results = st.number_input("Max final unique jobs", min_value=10, max_value=100, value=100, step=10)

run_btn = st.button("Run search → generate Excel", type="primary")

if run_btn:
    if not TARGET_ROLE.strip():
        st.error("Please enter a job title / keyword.")
        st.stop()
    if not selected_portals:
        st.error("Please select at least 1 portal.")
        st.stop()

    out_name = f"SG_{TARGET_ROLE.strip().replace(' ','_')}_Jobs.xlsx"

    with st.spinner("Running extraction, scoring, dedupe & Excel generation..."):
        out_path = run_search(
            target_role=TARGET_ROLE.strip(),
            posted_within_days=int(days),
            selected_portals=selected_portals,
            max_final=int(max_results),
            raw_cap=200,
            out_path=out_name,
        )

    st.success("Done. Download your Excel below.")

    with open(out_path, "rb") as f:
        st.download_button(
            label="Download Excel (.xlsx)",
            data=f.read(),
            file_name=out_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    st.info("Tip: If you see 0 rows, check the Notes tab → Portal stats. Some portals may be blocked or return irrelevant roles for certain keywords.")
