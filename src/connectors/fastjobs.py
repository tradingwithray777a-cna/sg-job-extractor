from __future__ import annotations

import re
from typing import List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .base import BaseConnector, RawJob

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
}

def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


class FastJobsConnector(BaseConnector):
    source_name = "FastJobs"

    def search(self, query: str, limit: int = 80) -> List[RawJob]:
        base = "https://www.fastjobs.sg/singapore-jobs/en/latest-jobs-jobs/"
        r = requests.get(base, headers=HEADERS, timeout=30)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "lxml")
        qn = query.strip().lower()

        jobs: List[RawJob] = []
        for a in soup.select("a[href*='/singapore-job-ad/']"):
            href = a.get("href") or ""
            if not href:
                continue
            full = href if href.startswith("http") else urljoin("https://www.fastjobs.sg", href)

            title = _clean(a.get_text(" ", strip=True))
            if len(title) < 3:
                continue

            # keyword filter (basic)
            if qn and qn not in title.lower():
                continue

            if any(j.url == full for j in jobs):
                continue

            det = self._fetch_detail(full)
            if not det.title:
                det.title = title

            jobs.append(det)
            if len(jobs) >= limit:
                break

        return jobs

    def _fetch_detail(self, job_url: str) -> RawJob:
        try:
            r = requests.get(job_url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "lxml")

            title = ""
            h1 = soup.select_one("h1")
            if h1:
                title = _clean(h1.get_text(" ", strip=True))[:200]

            text = soup.get_text("\n", strip=True)

            employer = "Not stated"
            salary = "Not stated"
            job_type = "Not stated"
            posted = "Unverified"
            closing = "Not stated"
            reqs = "• Not stated"

            m_sal = re.search(r"S\$\s*[\d,]+(\s*-\s*[\d,]+)?\s*/\s*(month|hour)", text, re.IGNORECASE)
            if m_sal:
                salary = _clean(m_sal.group(0))

            if "Full Time" in text or "Full-time" in text:
                job_type = "Full-time"
            elif "Part Time" in text or "Part-time" in text:
                job_type = "Part-time"
            elif "Contract" in text:
                job_type = "Contract"

            bullets = [_clean(li.get_text(" ", strip=True)) for li in soup.select("li")]
            bullets = [b for b in bullets if 6 <= len(b) <= 80][:3]
            if bullets:
                reqs = "\n".join([f"• {b}" for b in bullets])

            return RawJob(
                title=title,
                employer=employer,
                url=job_url,
                source=self.source_name,
                posted_date=posted,
                closing_date=closing,
                requirements=reqs,
                salary=salary,
                job_type=job_type,
            )
        except Exception:
            return RawJob(
                title="",
                employer="Not stated",
                url=job_url,
                source=self.source_name,
                posted_date="Unverified",
                closing_date="Not stated",
                requirements="• Not stated",
                salary="Not stated",
                job_type="Not stated",
            )
