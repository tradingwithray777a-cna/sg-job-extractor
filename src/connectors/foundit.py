from __future__ import annotations

import re
from typing import List
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from .base import BaseConnector, RawJob

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
    "Accept-Language": "en-SG,en;q=0.9",
}

class FounditConnector(BaseConnector):
    source_name = "Foundit"

    def search(self, query: str, limit: int = 80) -> List[RawJob]:
        q = quote_plus(query.strip())
        url = f"https://www.foundit.sg/srp/results?query={q}&locations=Singapore"

        status, final_url, html = self.http_get(url, headers=HEADERS, timeout=30)
        if status != 200 or not html:
            return []

        soup = BeautifulSoup(html, "html.parser")

        links = []
        for a in soup.select("a[href*='/job/']"):
            href = a.get("href") or ""
            if not href:
                continue
            full = href if href.startswith("http") else urljoin("https://www.foundit.sg", href)
            if full not in links:
                links.append(full)
            if len(links) >= limit:
                break

        # fallback regex
        if not links:
            hits = re.findall(r'https://www\.foundit\.sg/job/[^"\'\s<]+', html)
            for h in hits[:limit]:
                if h not in links:
                    links.append(h)

        self._set_debug(found_links=len(links))

        jobs: List[RawJob] = []
        for job_url in links[:limit]:
            jobs.append(
                RawJob(
                    title="Not stated",
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
        return jobs
