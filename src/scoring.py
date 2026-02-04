from __future__ import annotations

from datetime import date, datetime
import re
from typing import Dict, List


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _words(s: str) -> List[str]:
    s = _norm(s)
    toks = re.findall(r"[a-z0-9]+", s)
    stop = {"and", "or", "the", "a", "an", "of", "to", "in", "for", "with", "on"}
    toks = [t for t in toks if t not in stop and len(t) >= 3]
    return toks


def should_keep_title(title: str, target_role: str, adjacent_titles: List[str], nearby_titles: List[str]) -> bool:
    """
    Hard gate, but SAFE:
    - If title is missing/Not stated, keep it (so we don't end up with 0 rows).
    - Otherwise require at least 1 meaningful overlap with target/adjacent/nearby vocab.
    """
    t = _norm(title)
    if not t or t in {"not stated", "unknown"}:
        return True  # keep; portal likely blocked details

    vocab = set(_words(target_role))
    for a in (adjacent_titles or [])[:15]:
        vocab.update(_words(a))
    for n in (nearby_titles or [])[:15]:
        vocab.update(_words(n))

    title_tokens = set(_words(title))
    return len(vocab.intersection(title_tokens)) >= 1


def compute_relevance(row: Dict, target_role: str, adjacent_titles: List[str], nearby_titles: List[str]) -> int:
    title = row.get("Job title available", "") or ""
    employer = row.get("employer", "") or ""
    job_type = (row.get("job full-time or part-time") or "").lower()

    score = 0

    # A) Title match (max 140)
    if _norm(target_role) in _norm(title):
        score += 120
    else:
        tr_words = _words(target_role)
        if tr_words and all(w in _norm(title) for w in tr_words):
            score += 100
        else:
            if any(_norm(a) in _norm(title) for a in (adjacent_titles or [])):
                score += 85
            elif any(w in _norm(title) for w in _words(" ".join(nearby_titles or []))):
                score += 60
            elif any(w in _norm(title) for w in _words(target_role)):
                score += 30

    # B) Domain/industry match (max 40) — heuristic
    emp_n = _norm(employer)
    if any(k in emp_n for k in ["government", "agency", "community", "charity", "foundation", "association", "ngo", "service"]):
        score += 40
    elif employer and employer != "Not stated":
        score += 25
    else:
        score += 10

    # C) Employment type (max 20)
    if "full" in job_type:
        score += 20
    elif "contract" in job_type:
        score += 15
    elif "part" in job_type:
        score += 5

    return min(score, 200)


def closing_passed(closing_date_value: str, today: date | None = None) -> str:
    today = today or datetime.now().date()
    v = (closing_date_value or "").strip()
    if not v or v.lower() == "not stated":
        return "Unknown"

    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y"):
        try:
            d = datetime.strptime(v, fmt).date()
            return "Yes" if d < today else "No"
        except Exception:
            continue

    return "Unknown"
