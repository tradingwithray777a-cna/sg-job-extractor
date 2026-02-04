from __future__ import annotations

from typing import List
from urllib.parse import quote_plus, urljoin
import re

from bs4 import BeautifulSoup

from .base import BaseConnector, RawJob

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
    "Accept-Language": "en-SG,en;q=0.9",
}

def _slugify(q: str) -> str:
    q = (q or "").strip().lower()
    q = re.sub(r"[^\w\s-]", " ", q)
    q = re.sub(r"\s+", "-", q).strip("-")
    return q or "jobs"

class FastJobsConnector(BaseConnector):
    source_name = "FastJobs"

    def search(self, query: str, limit: int = 80) -> List[RawJob]:
        slug = _slugify(query)
        url = f"https://www.fastjobs.sg/singapore-jobs-search/{slug}/?source=search"

        status, final_url, html = self.http_get(url, headers=HEADERS, timeout=30)
        if status != 200 or not html:
            return []

        soup = BeautifulSoup(html, "html.parser")

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
