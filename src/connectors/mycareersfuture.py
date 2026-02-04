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

class MyCareersFutureConnector(BaseConnector):
    source_name = "MyCareersFuture"

    def search(self, query: str, limit: int = 80) -> List[RawJob]:
        """
        Lightweight HTML scrape:
        - Collect job card links
        - Extract title + employer where visible
        Note: MCF layout can change; this aims to be resilient.
        """
        q = quote_plus(query.strip())
        # MCF search URL pattern (public)
        url = f"https://www.mycareersfuture.gov.sg/search?search={q}&sortBy=relevancy&page=0"

        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                return []
        except Exception:
            return []

        soup = BeautifulSoup(r.text, "html.parser")

        jobs: List[RawJob] = []

        # Strategy: find anchors that look like job pages
        # MCF job links usually contain "/job/" or "/job/"-like routes
        anchors = soup.find_all("a", href=True)

        for a in anchors:
            href = a.get("href") or ""
            if not href:
                continue

            # Heuristic: job detail pages include "/job/" in URL
            if "/job/" not in href:
                continue

            job_url = href if href.startswith("http") else urljoin("https://www.mycareersfuture.gov.sg", href)

            # title text from anchor or nearby h3/h2
            title = _clean(a.get_text(" ", strip=True))
            if not title or len(title) < 3:
                # look for header inside card
                h = a.find(["h1", "h2", "h3"])
                if h:
                    title = _clean(h.get_text(" ", strip=True))

            # employer: look at parent card for possible employer text
            employer = "Not stated"
            card = a
            for _ in range(4):
                if not card:
                    break
                card = card.parent
                if not card:
                    break
                txt = _clean(card.get_text(" ", strip=True))
                # Try to detect "Company:" patterns or common MCF card structure
                # This is best-effort; if uncertain keep Not stated.
                m = re.search(r"Company\s*[:\-]\s*([A-Za-z0-9&().,'\-/ ]{3,80})", txt, re.IGNORECASE)
                if m:
                    employer = _clean(m.group(1))
                    break

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

        # Dedup by URL (MCF can repeat anchors)
        seen = set()
        out = []
        for j in jobs:
            if j.url and j.url not in seen:
                out.append(j)
                seen.add(j.url)
        return out[:limit]

