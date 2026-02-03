from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Tuple
import re

from src.keywords import build_keyword_sets
from src.scoring import compute_relevance, closing_passed
from src.excel_writer import write_excel

from src.connectors.mycareersfuture import MyCareersFutureConnector
from src.connectors.grabjobs import GrabJobsConnector
from src.connectors.foundit import FounditConnector
from src.connectors.fastjobs import FastJobsConnector

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

CONNECTORS = {
    "MyCareersFuture": MyCareersFutureConnector(),
    "GrabJobs": GrabJobsConnector(),
    "Foundit": FounditConnector(),
    "FastJobs": FastJobsConnector(),
}

def build_queries(target_role: str, adjacent_titles: List[str], core_keywords: List[str]) -> List[Tuple[str, str]]:
    """
    Must have 3 variations per portal:
    - Exact
    - Adjacent (pick 2–3)
    - Skill-based (combine 2–3 core keywords)
    """
    queries: List[Tuple[str, str]] = []
    queries.append((target_role, "Exact"))

    for t in adjacent_titles[:3]:
        queries.append((t, "Adjacent"))

    # skill based: target + 2 core terms (excluding target itself)
    cores = [c for c in core_keywords if _norm(c) != _norm(target_role)]
    if len(cores) >= 2:
        queries.append((f"{target_role} {cores[0]} {cores[1]}", "Skill-based"))
    elif len(cores) == 1:
        queries.append((f"{target_role} {cores[0]}", "Skill-based"))
    else:
        queries.append((target_role, "Skill-based"))

    return queries[:5]

def run_search(
    target_role: str,
    posted_within_days: int,
    selected_portals: List[str],
    max_final: int = 100,
    raw_cap: int = 200,
    out_path: str = "output.xlsx",
) -> str:
    ks = build_keyword_sets(target_role)
    queries = build_queries(target_role, ks.adjacent_titles, ks.core_keywords)

    raw_rows: List[Dict] = []
    portal_raw_counts: Dict[str, int] = {}

    for portal in selected_portals:
        conn = CONNECTORS.get(portal)
        if not conn:
            portal_raw_counts[portal] = 0
            continue

        portal_hits = 0

        # Enforce 3 query variations per portal
        for q, qtype in queries[:3]:
            try:
                jobs = conn.search(q, limit=80)
            except Exception:
                jobs = []

            portal_hits += len(jobs)

            for j in jobs:
                raw_rows.append({
                    "Job title available": j.title or "Not stated",
                    "employer": j.employer or "Not stated",
                    "job post url link": j.url,
                    "job post from what source": portal,
                    "date job post was posted": j.posted_date or "Unverified",
                    "application closing date": j.closing_date or "Not stated",
                    "key job requirement": j.requirements or "• Not stated",
                    "estimated salary": j.salary or "Not stated",
                    "job full-time or part-time": j.job_type or "Not stated",
                })

                if len(raw_rows) >= raw_cap:
                    break

            if len(raw_rows) >= raw_cap:
                break

        portal_raw_counts[portal] = portal_hits

        if len(raw_rows) >= raw_cap:
            break

    raw_count = len(raw_rows)

    # Filter: exclude keywords in title
    filtered = []
    excl = [_norm(x) for x in ks.exclude_keywords]
    for r in raw_rows:
        title_n = _norm(r["Job title available"])
        if any(e and e in title_n for e in excl):
            continue
        filtered.append(r)

    after_filter = len(filtered)

    # Deduplicate by (title + employer) keeping best completeness
    def completeness_key(r: Dict):
        verifiable_posted = 1 if r["date job post was posted"] not in ("Unverified", "", None) else 0
        closing_present = 1 if r["application closing date"] not in ("Not stated", "", None) else 0
        salary_present = 1 if r["estimated salary"] not in ("Not stated", "", None) else 0
        req_len = len((r["key job requirement"] or "").strip())
        return (verifiable_posted, closing_present, salary_present, req_len)

    best = {}
    for r in filtered:
        k = (_norm(r["Job title available"]), _norm(r["employer"]))
        if k not in best:
            best[k] = r
        else:
            if completeness_key(r) > completeness_key(best[k]):
                best[k] = r

    deduped = list(best.values())
    after_dedupe = len(deduped)

    # Score + closing passed
    today = datetime.now().date()
    for r in deduped:
        r["Relevance score"] = compute_relevance(r, ks.target_role, ks.adjacent_titles, ks.nearby_titles)
        r["Closing date passed? (Y/N)"] = closing_passed(r["application closing date"], today=today)

    # Sorting logic:
    # Relevance score desc
    # Posted date verifiable newest first
    # Unverified at bottom
    def sort_key(r: Dict):
        ver = 0 if r["date job post was posted"] == "Unverified" else 1
        try:
            d = datetime.strptime(r["date job post was posted"], "%Y-%m-%d").date()
        except Exception:
            d = datetime(1970, 1, 1).date()
        return (-int(r["Relevance score"]), -ver, -(d.toordinal()))

    deduped.sort(key=sort_key)

    final = deduped[:max_final]
    final_count = len(final)

    notes = {
        "Search date/time (SG time)": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "TARGET_ROLE": ks.target_role,
        "Core keywords used": ", ".join(ks.core_keywords),
        "Adjacent titles used": ", ".join(ks.adjacent_titles[:10]),
        "Exclude keywords used": ", ".join(ks.exclude_keywords),
        "Portals searched (raw hits)": "; ".join([f"{p}: {portal_raw_counts.get(p,0)}" for p in selected_portals]),
        "Counts (raw → after filter → after dedupe → final)": f"{raw_count} → {after_filter} → {after_dedupe} → {final_count}",
        "Unverified posted date rule": "If a portal does not show a posted date, set to 'Unverified'. Exclude >30 days only when date is verifiable. Unverified is ranked lower.",
    }

    return write_excel(final, notes, out_path)
