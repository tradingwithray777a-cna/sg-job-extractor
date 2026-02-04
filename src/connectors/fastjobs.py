from __future__ import annotations

import re
from typing import List
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

from .base import BaseConnector, RawJob

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
    "Accept-Language": "en-SG,en;q=0.9",
}

def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def _looks_like_title(s: str) -> bool:
    if not s:
        return False
    s2 = s.lower()
    bad = ["last updated on", "s$", " / month", " / hour", "region", "featured ad", "work location", "job type"]
    if any(b in s2 for b in bad):
        return False
    # titles are typically 5–120 chars
    return 5 <= len(s) <= 140

def _pick_title_from_card_text(card_text: str) -> str:
    """
    FastJobs cards often concatenate everything. We pick the first plausible title-like segment.
    """
    txt = card_text.replace("Featured Ad", "\n")
    # split on newlines-ish separators
    parts = re.split(r"[\n\r]|(?:\s{2,})|(?:\s\|\s)|(?:\s·\s)", txt)
    parts = [_clean(p) for p in parts if _clean(p)]
    for p in parts:
        if _looks_like_title(p):
            return p[:200]
    # fallback: first 80 chars
    return (_clean(card_text)[:80] or "Not stated")

def _extract_employer(card_text: str) -> str:
    t = _clean(card_text)
    # sometimes appears twice: "COMPANY COMPANY"
    # try to find a duplicated company name near the end
    # common heuristic: last 2 identical chunks
    chunks = re.split(r"\s{2,}", t)
    chunks = [c for c in chunks if c]
    if len(chunks) >= 2 and chunks[-1] == chunks[-2] and 3 <= len(chunks[-1]) <= 80:
        return _clean(chunks[-1])

    # fallback: look for patterns like " PTE LTD" / " LTD" in the card
    m = re.search(r"([A-Za-z0-9&().,'\- ]{3,80}\b(?:PTE\.?\s*LTD\.?|LTD\.?|LIMITED|LLP|INC\.?)\b)", t, re.IGNORECASE)
    if m:
        return _clean(m.group(1))

    return "Not stated"

class FastJobsConnector(BaseConnector):
    source_name = "FastJobs"

    def search(self, query: str, limit: int = 80) -> List[RawJob]:
        q = quote_plus(query.strip())
        url = f"https://www.fastjobs.sg/singapore-jobs-search/{q}/?source=search"

        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                return []
        except Exception:
            return []

        soup = BeautifulSoup(r.text, "html.parser")

        # FastJobs job ad pages look like /singapore-job-ad/<id>/...
        links = []
        for a in soup.find_all("a", href=True):
            href = a.get("href") or ""
            if "/singapore-job-ad/" not in href:
                continue
            full = href if href.startswith("http") else urljoin("https://www.fastjobs.sg", href)
            if full not in links:
                links.append(full)
            if len(links) >= limit:
                break

        jobs: List[RawJob] = []
        for job_url in links:
            # Try to use the anchor's parent text as a "card blob"
            # This helps extract title/employer without fetching details.
            title = "Not stated"
            employer = "Not stated"

            # best-effort: find the anchor in soup again and climb to a container
            a = soup.find("a", href=lambda x: x and job_url.replace("https://www.fastjobs.sg", "") in x)
            card_text = ""
            if a:
                # climb to a likely card container
                node = a
                for _ in range(6):
                    if not node:
                        break
                    card_text = _clean(node.get_text(" ", strip=True))
                    # once it's sufficiently long, it's probably the whole card
                    if len(card_text) > 120:
                        break
                    node = node.parent

            if card_text:
                title = _pick_title_from_card_text(card_text)
                employer = _extract_employer(card_text)

            jobs.append(
                RawJob(
                    title=title or "Not stated",
                    employer=employer or "Not stated",
                    url=job_url,
                    source=self.source_name,
                    posted_date="Unverified",
                    closing_date="Not stated",
                    requirements="• Not stated",
                    salary="Not stated",
                    job_type="Not stated",
                )
            )

            if len(jobs) >= limit:
                break

        return jobs
