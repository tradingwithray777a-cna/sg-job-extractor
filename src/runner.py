from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Tuple
import re

from src.scoring import compute_relevance, closing_passed
from src.connectors.mycareersfuture import MyCareersFutureConnector
from src.connectors.fastjobs import FastJobsConnector
from src.connectors.foundit import FounditConnector

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


CONNECTORS = {
    "MyCareersFuture": MyCareersFutureConnector(),
    "FastJobs": FastJobsConnector(),
    "Foundit": FounditConnector(),
}


def build_queries(target_role: str) -> List[Tuple[str, str]]:
    return [
        (target_role, "Exact"),
        (f"{target_role} Executive", "Adjacent"),
        (target_role, "Skill-based"),
    ]


def run_search(
    target_role: str,
    posted_within_days: int,
    selected_portals: List[str],
    max_final: int = 100,
    raw_cap: int = 200,
    out_path: str = "output.xlsx",
) -> str:
    queries = build_queries(target_role)

    raw_rows: List[Dict] = []
    portal_stats: Dict[str, Dict[str, int]] = {}
    portal_debug_lines: List[str] = []

    min_relevance = 30

    for portal in selected_portals:
        conn = CONNECTORS.get(portal)
        if not conn:
            portal_stats[portal] = {"returned": 0, "kept": 0}
            continue

        returned_total = 0

        for q, qtype in queries:
            jobs = conn.search(q, limit=80)
            returned_total += len(jobs)

            for j in jobs:
                raw_rows.append({
                    "Job title available": getattr(j, "title", "") or "Not stated",
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

        portal_stats[portal] = {"returned": returned_total, "kept": 0}

        # Collect connector debug into Notes
        dbg = getattr(conn, "last_debug", {}) or {}
        # Keep it short & safe
        dbg_line = f"{portal} debug: status={dbg.get('status_code')}, final_url={dbg.get('final_url')}, title={dbg.get('page_title')}, links={dbg.get('found_links')}, len={dbg.get('html_len')}"
        portal_debug_lines.append(dbg_line)

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
        r["Relevance score"] = compute_relevance(r, target_role, [], [])
        r["Closing date passed? (Y/N)"] = closing_passed(r.get("application closing date", "Not stated"), today=today)

    kept = [r for r in deduped if int(r.get("Relevance score", 0)) >= min_relevance]

    for p in portal_stats:
        portal_stats[p]["kept"] = sum(1 for r in kept if r.get("job post from what source") == p)

    kept.sort(key=lambda r: -int(r.get("Relevance score", 0)))
    final = kept[:max_final]

    notes = {
        "Search date/time (SG time)": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "TARGET_ROLE": target_role,
        "Queries used": "; ".join([f"{qt}:{q}" for q, qt in queries]),
        "Portals selected": ", ".join(selected_portals),
        "Portal stats (returned vs kept_after_score)": "; ".join([f"{p}: {portal_stats[p]['returned']} returned, {portal_stats[p]['kept']} kept" for p in portal_stats]),
        "Counts (raw → dedupe → kept → final)": f"{len(raw_rows)} → {len(deduped)} → {len(kept)} → {len(final)}",
        "Relevance threshold used": str(min_relevance),
        "HTTP Debug (per portal)": " | ".join(portal_debug_lines),
        "Tip": "If status=403/429 or page_title mentions Access Denied/Captcha, scraping is being blocked from Streamlit Cloud.",
    }

    if write_excel:
        return write_excel(final, notes, out_path)
    return _fallback_write_excel(final, notes, out_path)
