from __future__ import annotations

import re
from typing import List
from urllib.parse import quote_plus, urljoin

from .base import BaseConnector, RawJob

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
    "Accept-Language": "en-SG,en;q=0.9",
}

class MyCareersFutureConnector(BaseConnector):
    source_name = "MyCareersFuture"

    def search(self, query: str, limit: int = 80) -> List[RawJob]:
        q = quote_plus((query or "").strip())
        url = f"https://www.mycareersfuture.gov.sg/search?search={q}&sortBy=new_posting_date&page=0"

        status, final_url, html = self.http_get(url, headers=HEADERS, timeout=30)
        if status != 200 or not html:
            return []

        # handle escaped slashes in JSON/HTML
        html2 = html.replace("\\/", "/")

        # Grab lots of /job/... occurrences
        paths = re.findall(r"/job/[^\"'\s<>]+", html2)
        links = []
        for p in paths:
            full = urljoin("https://www.mycareersfuture.gov.sg", p)
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
