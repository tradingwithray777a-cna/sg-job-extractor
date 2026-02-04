from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple
import re

from src.scoring import compute_relevance, closing_passed, should_keep_title

from src.connectors.foundit import FounditConnector
from src.connectors.fastjobs import FastJobsConnector
from src.connectors.mycareersfuture import MyCareersFutureConnector
from src.connectors.grabjobs import GrabJobsConnector

try:
    from src.excel_writer import write_excel
except Exception:
    write_excel = None


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

    for row in range(2, ws.max_row + 1):
        cell = ws.cell(row=row, column=3)
        if isinstance(cell.value, str) and cell.value.startswith("http"):
            cell.hyperlink = cell.value
            cell.font = Font(color="0000EE", underline="single")

    end_col = get_column_letter(len(JOBS_COLS))
    end_row = ws.max_row
    tab = Table(displayName="JobsTable", ref=f"A1:{end_col}{end_row}")
    tab.tableStyleInfo = TableStyleInfo(name="TableStyleMedium9", showRowStripes=True)
    ws.add_table(tab)

    ws2 = wb.create_sheet("Notes")
    ws2.append(["Item", "Value"])
    ws2.freeze_panes = "A2"
    ws2.column_dimensions["A"].width = 42
    ws2.column_dimensions["B"].width = 120
    ws2["A1"].font = Font(bold=True)
    ws2["B1"].font = Font(bold=True)
    for k, v in (notes or {}).items():
        ws2.append([str(k), str(v)])

    wb.save(out_path)
    return out_path


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


@dataclass
class KeywordSets:
    target_role: str
    core_keywords: List[str]
    adjacent_titles: List[str]
    nearby_titles: List[str]
    exclude_keywords: List[str]


def build_keyword_sets(target_role: str) -> KeywordSets:
    tr = (target_role or "").strip()

    # Generic keyword sets (works for any role)
    core = [tr]
    adjacent = [
        f"{tr} Executive", f"{tr} Officer", f"{tr} Specialist",
        f"Senior {tr}", f"Assistant {tr}", f"{tr} Coordinator",
        f"{tr} Manager"
    ]
    nearby = ["Programme Executive", "Stakeholder Management", "Partnerships Executive", "Community Engagement"]
    exclude = []

    # small custom hints for common words
    trn = _norm(tr)
    if "community" in trn and "partnership" in trn:
        adjacent = [
            "Community Partnerships Executive", "Partnerships Executive", "Community Engagement Executive",
            "Stakeholder Management Executive", "Community Outreach Executive", "Partnership Officer",
            "Strategic Partnerships Executive", "Partnership Development Executive",
        ]
        nearby = [
            "Programme Executive", "Programme Coordinator", "Corporate Relations Executive",
            "Business Development Executive", "CSR Executive", "Events Executive",
            "Stakeholder Engagement Officer",
        ]

    def dedupe(lst: List[str], cap: int) -> List[str]:
        out, seen = [], set()
        for x in lst:
            xn = _norm(x)
            if xn and xn not in seen:
                out.append(x)
                seen.add(xn)
            if len(out) >= cap:
                break
        return out

    return KeywordSets(
        target_role=tr,
        core_keywords=dedupe(core, 10),
        adjacent_titles=dedupe(adjacent, 20),
        nearby_titles=dedupe(nearby, 20),
        exclude_keywords=dedupe(exclude, 10),
    )


CONNECTORS = {
    "Foundit": FounditConnector(),
    "FastJobs": FastJobsConnector(),
    "MyCareersFuture": MyCareersFutureConnector(),
    "GrabJobs": GrabJobsConnector(),
}


def build_queries(target_role: str, adjacent_titles: List[str], core_keywords: List[str]) -> List[Tuple[str, str]]:
    queries = [(target_role, "Exact")]
    for t in (adjacent_titles or [])[:3]:
        queries.append((t, "Adjacent"))
    # simple skill-based: target + 2 core terms if any
    cores = [c for c in (core_keywords or []) if _norm(c) != _norm(target_role)]
    if len(cores) >= 2:
        queries.append((f"{target_role} {cores[0]} {cores[1]}", "Skill-based"))
    else:
        queries.append((target_role, "Skill-based"))
    return queries[:3]


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
    portal_stats: Dict[str, Dict[str, int]] = {}
    dropped_gate = 0

    for portal in selected_portals:
        conn = CONNECTORS.get(portal)
        if not conn:
            portal_stats[portal] = {"returned": 0, "kept": 0}
            continue

        returned_total = 0
        kept_total = 0

        for q, qtype in queries:
            try:
                jobs = conn.search(q, limit=80)
            except Exception:
                jobs = []

            returned_total += len(jobs)

            for j in jobs:
                title = getattr(j, "title", "") or "Not stated"

                if not should_keep_title(title, ks.target_role, ks.adjacent_titles, ks.nearby_titles):
                    dropped_gate += 1
                    continue

                raw_rows.append({
                    "Job title available": title,
                    "employer": getattr(j, "employer", "") or "Not stated",
                    "job post url link": getattr(j, "url", "") or "",
                    "job post from what source": portal,
                    "date job post was posted": getattr(j, "posted_date", "") or "Unverified",
                    "application closing date": getattr(j, "closing_date", "") or "Not stated",
                    "key job requirement": getattr(j, "requirements", "") or "• Not stated",
                    "estimated salary": getattr(j, "salary", "") or "Not stated",
                    "job full-time or part-time": getattr(j, "job_type", "") or "Not stated",
                })
                kept_total += 1

                if len(raw_rows) >= raw_cap:
                    break

            if len(raw_rows) >= raw_cap:
                break

        portal_stats[portal] = {"returned": returned_total, "kept": kept_total}
        if len(raw_rows) >= raw_cap:
            break

    # Dedup
    def key(r): return (_norm(r["Job title available"]), _norm(r["employer"]))
    best = {}
    for r in raw_rows:
        k = key(r)
        if k not in best:
            best[k] = r
    deduped = list(best.values())

    today = datetime.now().date()
    for r in deduped:
        r["Relevance score"] = compute_relevance(r, ks.target_role, ks.adjacent_titles, ks.nearby_titles)
        r["Closing date passed? (Y/N)"] = closing_passed(r.get("application closing date", "Not stated"), today=today)

    # Sort: score desc, verified posted first
    def sort_key(r):
        ver = 0 if r.get("date job post was posted") == "Unverified" else 1
        return (-int(r.get("Relevance score", 0)), -ver)

    deduped.sort(key=sort_key)
    final = deduped[:max_final]

    # Notes debug
    notes = {
        "Search date/time (SG time)": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "TARGET_ROLE": ks.target_role,
        "Queries used": "; ".join([f"{qt}:{q}" for q, qt in queries]),
        "Portals selected": ", ".join(selected_portals),
        "Portal stats (returned vs kept)": "; ".join([f"{p}: {portal_stats[p]['returned']} returned, {portal_stats[p]['kept']} kept" for p in portal_stats]),
        "Dropped by title gate": str(dropped_gate),
        "Counts (raw kept → dedupe → final)": f"{len(raw_rows)} → {len(deduped)} → {len(final)}",
        "Why Excel can be empty": "If portals return 0 links (blocked/JS-rendered), or titles are missing and were filtered previously. This build keeps 'Not stated' titles to avoid 0 rows.",
    }

    if write_excel:
        return write_excel(final, notes, out_path)
    return _fallback_write_excel(final, notes, out_path)
