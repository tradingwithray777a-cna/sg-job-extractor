from __future__ import annotations

import re
from datetime import datetime, date
from typing import Dict, List, Optional


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _contains_all_words(title: str, target: str) -> bool:
    t_words = [w for w in _norm(target).split(" ") if w]
    tt = _norm(title)
    return all(w in tt for w in t_words)


def title_score(job_title: str, target_role: str, adjacent_titles: List[str], nearby_titles: List[str]) -> int:
    jt = _norm(job_title)
    tr = _norm(target_role)

    # Exact phrase
    if tr and tr in jt:
        return 120

    # Contains all main words (any order)
    if _contains_all_words(job_title, target_role):
        return 100

    # Adjacent title strong match
    adj_norm = [_norm(x) for x in (adjacent_titles or [])]
    if any(a and a in jt for a in adj_norm):
        return 85

    # Nearby functional title match
    nb_norm = [_norm(x) for x in (nearby_titles or [])]
    if any(n and n in jt for n in nb_norm):
        return 60

    # Partial match
    tr_words = [w for w in tr.split(" ") if w]
    if any(w in jt for w in tr_words):
        return 30

    return 0


def domain_score(employer: str) -> int:
    """
    Generic heuristic for employer/sector.
    Safe default: tries to infer some sectors using name keywords.
    """
    e = _norm(employer)
    if not e:
        return 10

    strong = [
        "government", "ministry", "statutory", "agency",
        "hospital", "clinic", "health",
        "university", "polytechnic", "school",
        "foundation", "charity", "ngo",
        "engineering", "construction", "consultancy",
        "hotel"
    ]
    partial = ["pte", "ltd", "llp", "group", "holding", "services", "service"]

    if any(k in e for k in strong):
        return 40
    if any(k in e for k in partial):
        return 25
    return 10


def employment_score(job_type: str) -> int:
    jt = _norm(job_type)
    if "full" in jt:
        return 20
    if "contract" in jt or "temp" in jt:
        return 15
    if "part" in jt:
        return 5
    return 0


def compute_relevance(row: Dict, target_role: str, adjacent_titles: List[str], nearby_titles: List[str]) -> int:
    """
    Final relevance score 0–200:
      A) Title match max 140
      B) Domain match max 40
      C) Employment type max 20
    """
    a = title_score(row.get("Job title available", ""), target_role, adjacent_titles, nearby_titles)
    b = domain_score(row.get("employer", ""))
    c = employment_score(row.get("job full-time or part-time", ""))

    return min(200, a + b + c)


def closing_passed(closing_date: str, today: Optional[date] = None) -> str:
    """
    Return: Yes / No / Unknown
    closing_date expected YYYY-MM-DD or "Not stated"
    """
    if today is None:
        today = datetime.now().date()

    cd = (closing_date or "").strip()
    if cd in ("", "Not stated"):
        return "Unknown"

    try:
        d = datetime.strptime(cd, "%Y-%m-%d").date()
        return "Yes" if d < today else "No"
    except Exception:
        return "Unknown"
