import pandas as pd
from datetime import datetime, timedelta, timezone, date
from src.keywords import build_keyword_sets
from src.scoring import relevance_score

from src.connectors.mycareersfuture import MyCareersFutureConnector
from src.connectors.careers_gov import CareersGovConnector
from src.connectors.fastjobs import FastJobsConnector
from src.connectors.grabjobs import GrabJobsConnector
from src.connectors.foundit import FounditConnector
from src.connectors.jobstreet import JobStreetConnector
from src.connectors.indeed import IndeedConnector
from src.connectors.glassdoor import GlassdoorConnector
from src.connectors.linkedin import LinkedInConnector

SG_TZ = timezone(timedelta(hours=8))

REQUIRED_COLS = [
    "Job title available","employer","job post url link","job post from what source",
    "date job post was posted","application closing date","key job requirement",
    "estimated salary","job full-time or part-time","Relevance score","Closing date passed? (Y/N)"
]

def closing_passed(closing):
    if isinstance(closing, date):
        return "Yes" if closing < datetime.now(SG_TZ).date() else "No"
    if isinstance(closing, str):
        try:
            cd = datetime.fromisoformat(closing).date()
            return "Yes" if cd < datetime.now(SG_TZ).date() else "No"
        except Exception:
            return "Unknown"
    return "Unknown"

def run_job_search(target_role, posted_within_days, selected_portals, max_final=100, prefer_fulltime=True):
    kw = build_keyword_sets(target_role)
    core = kw["core_keywords"]
    adjacent = kw["adjacent_titles"]
    nearby = kw["nearby_titles"]
    exclude = kw["exclude_keywords"]

    # Map portal -> connector
    connectors = {
        "MyCareersFuture": MyCareersFutureConnector(),
        "Careers.gov.sg": CareersGovConnector(),
        "FastJobs": FastJobsConnector(),
        "GrabJobs": GrabJobsConnector(),
        "Foundit": FounditConnector(),
        "JobStreet Singapore": JobStreetConnector(),
        "Indeed Singapore": IndeedConnector(),
        "Glassdoor Singapore": GlassdoorConnector(),
        "LinkedIn Jobs": LinkedInConnector(),
        # Others can be added later as connectors
    }

    # Build query variations
    exact = target_role
    adj_picks = adjacent[:3] if adjacent else [target_role]
    skill_based = f"{target_role} {core[0]} {core[1]}" if len(core) >= 2 else target_role

    queries = [
        ("Exact", exact),
        ("Adjacent", adj_picks[0]),
        ("Skill-based", skill_based),
    ]

    raw_rows = []
    portal_stats = {}

    for portal in selected_portals:
        conn = connectors.get(portal)
        if not conn:
            portal_stats[portal] = "No connector yet (not extracted)"
            continue

        portal_raw = []
        portal_notes = []
        for qtype, q in queries:
            try:
                items = conn.search(q, posted_within_days=posted_within_days)
                portal_raw.extend(items)
            except Exception as e:
                portal_notes.append(f"{qtype} failed: {e}")

        portal_stats[portal] = f"raw={len(portal_raw)}; " + ("; ".join(portal_notes) if portal_notes else "ok")

        raw_rows.extend(portal_raw)

    # Normalize to DataFrame
    df = pd.DataFrame(raw_rows)
    if df.empty:
        df = pd.DataFrame(columns=REQUIRED_COLS)

    # Ensure required columns exist
    for c in REQUIRED_COLS:
        if c not in df.columns:
            df[c] = ""

    # Apply exclude keywords (title-based)
    if exclude:
        ex = [e.lower() for e in exclude]
        df = df[~df["Job title available"].astype(str).str.lower().apply(lambda t: any(x in t for x in ex))]

    # Score
    df["Relevance score"] = df.apply(
        lambda r: relevance_score(target_role, r["Job title available"], r["employer"], r["job full-time or part-time"], adjacent, nearby),
        axis=1
    )

    # Closing status
    df["Closing date passed? (Y/N)"] = df["application closing date"].apply(closing_passed)

    # Prefer full-time (ranking bias, not exclusion)
    if prefer_fulltime:
        ft_boost = df["job full-time or part-time"].astype(str).str.lower().str.contains("full").astype(int) * 3
        df["Relevance score"] = (df["Relevance score"] + ft_boost).clip(upper=200)

    # Deduplicate by (title + employer) keeping best completeness
    def completeness_key(r):
        posted = 1 if str(r["date job post was posted"]) not in ("Unverified", "", "None") else 0
        closing = 1 if str(r["application closing date"]) not in ("Not stated", "", "None") else 0
        salary = 1 if str(r["estimated salary"]) not in ("Not stated", "", "None") else 0
        req_len = len(str(r["key job requirement"]).strip())
        return (posted, closing, salary, req_len, r["Relevance score"])

    df["_ck"] = df.apply(completeness_key, axis=1)
    df = df.sort_values(by=["_ck"], ascending=False).drop_duplicates(subset=["Job title available","employer"], keep="first").drop(columns=["_ck"])

    # Sorting logic: relevance desc, verifiable posted date newest, unverified bottom
    def posted_sort_key(x):
        if str(x) == "Unverified":
            return (0, date(1900,1,1))
        try:
            return (1, datetime.fromisoformat(str(x)).date())
        except Exception:
            return (0, date(1900,1,1))

    df["_pd"] = df["date job post was posted"].apply(posted_sort_key)
    df = df.sort_values(by=["Relevance score","_pd"], ascending=[False, False]).drop(columns=["_pd"])

    # Cap to max_final
    df = df.head(max_final)

    # Notes sheet content
    notes = {
        "Search date/time (Singapore time)": datetime.now(SG_TZ).strftime("%Y-%m-%d %H:%M:%S SGT"),
        "TARGET_ROLE": target_role,
        "Core keywords used": ", ".join(core),
        "Adjacent titles used": ", ".join(adjacent[:20]),
        "Exclude keywords used": ", ".join(exclude),
        "Portals selected": ", ".join(selected_portals),
        "Portals searched + raw notes": " | ".join([f"{k}: {v}" for k,v in portal_stats.items()]),
        "Counts: raw → after filter → after dedupe → final": f"{len(raw_rows)} → {len(raw_rows)} → {len(df)} → {len(df)}",
        "Unverified posted date rule": "If posted date not available, set to 'Unverified'. Exclude >30 days only when posted date is verifiable; keep Unverified but rank lower.",
        "MyCareersFuture note": "MCF pages may be JS-heavy and restrict automation. Connector will log inaccessible/limited extraction when blocked; we can add Playwright upgrade later.",
    }

    # Return in exact column order
    df = df[REQUIRED_COLS].copy()
    return {"jobs_df": df, "notes_dict": notes}

