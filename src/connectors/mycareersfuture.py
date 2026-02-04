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
        q = quote_plus(query.strip())
        url = f"https://www.mycareersfuture.gov.sg/search?search={q}&sortBy=new_posting_date&page=0"

        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                return []
        except Exception:
            return []

        html = r.text
        soup = BeautifulSoup(html, "html.parser")

        # Collect job links
        links = []
        for a in soup.find_all("a", href=True):
            href = a.get("href") or ""
            if not href:
                continue
            if "/job/" in href:
                full = href if href.startswith("http") else urljoin("https://www.mycareersfuture.gov.sg", href)
                if full not in links:
                    links.append(full)
            if len(links) >= limit * 2:
                break

        # Regex fallback if anchors fail
        if not links:
            hits = re.findall(r'"/job/[^"\s]+"' , html)
            for h in hits:
                h = h.strip('"')
                full = urljoin("https://www.mycareersfuture.gov.sg", h)
                if full not in links:
                    links.append(full)
                if len(links) >= limit * 2:
                    break

        jobs: List[RawJob] = []

        # Create minimal jobs (title extraction best-effort)
        for job_url in links[:limit]:
            title = "Not stated"

            # Try to find anchor node again to extract text
            rel = job_url.replace("https://www.mycareersfuture.gov.sg", "")
            a = soup.find("a", href=lambda x: x and rel in x)
            if a:
                # Look for h3/h2 around it
                h = a.find(["h1", "h2", "h3"])
                if h:
                    title = _clean(h.get_text(" ", strip=True))[:200]
                else:
                    t = _clean(a.get_text(" ", strip=True))
                    if t:
                        title = t[:200]

            jobs.append(
                RawJob(
                    title=title or "Not stated",
                    employer="Not stated",
                    url=job_url,
                    source=self.source_name,
                    posted_date="Unverified",
                    closing_date="Not stated",
                    requirements="• Not stated",
                    salary="Not stated",
                    job_type="Not stated",
                )
            )

        # Dedup by URL
        seen = set()
        out = []
        for j in jobs:
            if j.url and j.url not in seen:
                out.append(j)
                seen.add(j.url)
        return out[:limit]
