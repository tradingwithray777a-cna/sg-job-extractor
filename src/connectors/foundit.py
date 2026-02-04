from __future__ import annotations

import re
from typing import List
from urllib.parse import quote_plus

from .base import BaseConnector, RawJob

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
    "Accept-Language": "en-SG,en;q=0.9",
}

class FounditConnector(BaseConnector):
    source_name = "Foundit"

    def search(self, query: str, limit: int = 80) -> List[RawJob]:
        q = quote_plus((query or "").strip())
        url = f"https://www.foundit.sg/srp/results?query={q}&locations=Singapore"

        status, final_url, html = self.http_get(url, headers=HEADERS, timeout=30)
        if status != 200 or not html:
            return []

        html2 = html.replace("\\/", "/")

        links = []
        # match full URLs
        for m in re.findall(r"https?://www\.foundit\.sg/job/[^\"'\s<>]+", html2):
            if m not in links:
                links.append(m)
            if len(links) >= limit:
                break

        # fallback: relative job paths
        if not links:
            for p in re.findall(r"/job/[^\"'\s<>]+", html2):
                full = "https://www.foundit.sg" + p
                if full not in links:
                    links.append(full)
                if len(links) >= limit:
                    break

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
