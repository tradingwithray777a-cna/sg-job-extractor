from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Tuple
import re

from src.keywords import build_keyword_sets
from src.scoring import compute_relevance, closing_passed

from src.connectors.mycareersfuture import MyCareersFutureConnector
from src.connectors.grabjobs import GrabJobsConnector
from src.connectors.foundit import FounditConnector
from src.connectors.fastjobs import FastJobsConnector

# --------- SAFE IMPORT: Excel writer (prevents ImportError) ----------
try:
    from src.excel_writer import write_excel  # preferred if available
except Exception:
    write_excel = None  # fallback will be used

# --------- Fallback Excel writer (openpyxl-only) ----------
def _fallback_write_excel(jobs: List[Dict], notes: Dict, out_path: str) -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.table import Table, TableStyleInfo

    JOBS_COLS = [
        "Job title available",
        "employer",
        "job post url link",
        "job post from what source",
        "date job post was posted",
        "application closing date",
        "key job requirement",
        "estimated salary",
        "job full-time or part-time",
        "Relevance score",
        "Closing date passed? (Y/N)",
    ]

    wb = Workbook()
    ws = wb.active
    ws.title = "Jobs"

    ws.append(JOBS_COLS)
    ws.freeze_panes = "A2"

    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(color="FFFFFF", bold=True)
    for col in range(1, len(JOBS_COLS) + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font

    for r in jobs:
        ws.append([r.get(c, "") for c in JOBS_COLS])

    # Hyperlinks in URL column (3rd col)
    for row in range(2, ws.max_row + 1):
        cell = ws.cell(row=row, column=3)
        if isinstance(cell.value, str) and cell.value.startswith("http"):
            cell.hyperlink = cell.value
            cell.font = Font(color="0000EE", underline="single")

    # Excel table
    end_col = get_column_letter(len(JOBS_COLS))
    end_row = ws.max_row
    tab = Table(displayName="JobsTable", ref=f"A1:{end_col}{end_row}")
    tab.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showRowStripes=True,
        showColumnStripes=False
    )
    ws.add_table(tab)

    # Simple column width
    for col in range(1, len(JOBS_COLS) + 1):
        max_len = 10
        for rr in range(1, min(ws.max_row, 200) + 1):
            v = ws.cell(row=rr, column=col).value
            if v is None:
                continue
            max_len = max(max_len, len(str(v)))
        ws.column_dimensions[get_column_letter(col)].width = min(60, max_len + 2)

    # Notes sheet
    ws2 = wb.create_sheet("Notes")
    ws2.append(["Item", "Value"])
    ws2.freeze_panes = "A2"
    ws2.column_dimensions["A"].width = 38
    ws2.column_dimensions["B"].width = 120
    ws2["A1"].font = Font(bold=True)
    ws2["B1"].font = Font(bold=True)

    for k, v in (notes or {}).items():
        ws2.append([str(k), str(v)])

    wb.save(out_path)
    return out_path


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

    for t in (adjacent_titles or [])[:3]:
        queries.append((t, "Adjacent"))

    cores = [c for c in (core_keywords or []) if _norm(c) != _norm(target_role)]
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

        # enforce 3 query variations
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

    # Filter exclude keywords (title)
    filtered = []
    excl = [_norm(x) for x in ks.exclude_keywords]
    for r in raw_rows:
        title_n = _norm(r.get("Job title available", ""))
        if any(e and e in title_n for e in excl):
            continue
        filtered.append(r)
    after_filter = len(filtered)

    # Deduplicate by (title + employer) keeping "best completeness"
    def completeness_key(r: Dict):
        verifiable_posted = 1 if r.get("date job post was posted") not in ("Unverified", "", None) else 0
        closing_present = 1 if r.get("application closing date") not in ("Not stated", "", None) else 0
        salary_present = 1 if r.get("estimated salary") not in ("Not stated", "", None) else 0
        req_len = len((r.get("key job requirement") or "").strip())
        return (verifiable_posted, closing_present, salary_present, req_len)

    best = {}
    for r in filtered:
        k = (_norm(r.get("Job title available", "")), _norm(r.get("employer", "")))
        if k not in best:
            best[k] = r
        else:
            if completeness_key(r) > completeness_key(best[k]):
                best[k] = r

    deduped = list(best.values())
    after_dedupe = len(deduped)

    # Score + closing flag
    today = datetime.now().date()
    for r in deduped:
        r["Relevance score"] = compute_relevance(r, ks.target_role, ks.adjacent_titles, ks.nearby_titles)
        r["Closing date passed? (Y/N)"] = closing_passed(r.get("application closing date", "Not stated"), today=today)

    # Sort: relevance desc, verifiable posted date first, newest first
    def sort_key(r: Dict):
        ver = 0 if r.get("date job post was posted") == "Unverified" else 1
        try:
            d = datetime.strptime(r.get("date job post was posted", ""), "%Y-%m-%d").date()
        except Exception:
            d = datetime(1970, 1, 1).date()
        return (-int(r.get("Relevance score", 0)), -ver, -(d.toordinal()))

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
        "Excel writer mode": "src.excel_writer.write_excel used" if write_excel else "fallback writer used (openpyxl)",
    }

    # Write Excel using preferred writer if available; otherwise fallback
    if write_excel:
        return write_excel(final, notes, out_path)
    return _fallback_write_excel(final, notes, out_path)
