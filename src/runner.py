from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple
import re

from src.scoring import compute_relevance, closing_passed, should_keep_title

from src.connectors.mycareersfuture import MyCareersFutureConnector
from src.connectors.grabjobs import GrabJobsConnector
from src.connectors.foundit import FounditConnector
from src.connectors.fastjobs import FastJobsConnector

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


@dataclass
class KeywordSets:
    target_role: str
    core_keywords: List[str]
    adjacent_titles: List[str]
    nearby_titles: List[str]
    exclude_keywords: List[str]


def build_keyword_sets(target_role: str) -> KeywordSets:
    tr = (target_role or "").strip()
    tr_n = _norm(tr)

    synonyms = {
        "receptionist": ["front desk", "front office", "guest services"],
        "procurement": ["sourcing", "purchasing", "buyer"],
        "community": ["engagement", "outreach"],
        "partnership": ["stakeholder", "partnerships"],
    }

    words = [w for w in tr_n.split(" ") if w]
    core = [tr]
    for w in words:
        core.extend(synonyms.get(w, []))

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

    core_keywords = dedupe(core, 10)

    adjacent, nearby, exclude = [], [], []

    if "receptionist" in tr_n:
        adjacent = [
            "Front Desk Officer", "Front Office Executive", "Reception Executive",
            "Clinic Receptionist", "Hotel Receptionist", "Guest Service Officer",
            "Administrative Receptionist", "Office Receptionist",
        ]
        nearby = [
            "Administrative Assistant", "Office Administrator", "Customer Service Officer",
            "Guest Relations Officer", "Facilities Coordinator",
        ]
        exclude = ["packer", "warehouse", "sorter", "assembler"]

    return KeywordSets(
        target_role=tr,
        core_keywords=core_keywords,
        adjacent_titles=dedupe(adjacent, 20),
        nearby_titles=dedupe(nearby, 20),
        exclude_keywords=dedupe(exclude, 10),
    )


CONNECTORS = {
    "MyCareersFuture": MyCareersFutureConnector(),
    "GrabJobs": GrabJobsConnector(),
    "Foundit": FounditConnector(),
    "FastJobs": FastJobsConnector(),
}


def build_queries(target_role: str, adjacent_titles: List[str], core_keywords: List[str]) -> List[Tuple[str, str]]:
    queries = [(target_role, "Exact")]
    for t in (adjacent_titles or [])[:3]:
        queries.append((t, "Adjacent"))

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
    portal_raw_counts: Dict[str, int] = {}

    for portal in selected_portals:
        conn = CONNECTORS.get(portal)
        if not conn:
            portal_raw_counts[portal] = 0
            continue

        portal_hits = 0
        for q, _qt in queries:
            try:
                jobs = conn.search(q, limit=80)
            except Exception:
                jobs = []

            portal_hits += len(jobs)

            for j in jobs:
                title = getattr(j, "title", "") or "Not stated"

                # HARD GATE: drop irrelevant titles
                if not should_keep_title(title, ks.target_role, ks.adjacent_titles, ks.nearby_titles):
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
                if len(raw_rows) >= raw_cap:
                    break
            if len(raw_rows) >= raw_cap:
                break

        portal_raw_counts[portal] = portal_hits
        if len(raw_rows) >= raw_cap:
            break

    raw_count = len(raw_rows)

    # Deduplicate
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

    deduped.sort(key=lambda r: (-int(r.get("Relevance score", 0)), r.get("date job post was posted") == "Unverified"))
    final = deduped[:max_final]

    notes = {
        "Search date/time (SG time)": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "TARGET_ROLE": ks.target_role,
        "Portals searched (raw hits)": "; ".join([f"{p}: {portal_raw_counts.get(p,0)}" for p in selected_portals]),
        "Counts (raw → after dedupe → final)": f"{raw_count} → {len(deduped)} → {len(final)}",
        "Hard title gate": "Only keep jobs where title overlaps target/adjacent/nearby keywords (prevents irrelevant roles).",
    }

    if write_excel:
        return write_excel(final, notes, out_path)
    return _fallback_write_excel(final, notes, out_path)
