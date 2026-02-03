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

def slugify(q: str) -> str:
    s = q.strip().lower()
    s = re.sub(r"[^a-z0-9\s-]", " ", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    return s or "jobs"


class MyCareersFutureConnector(BaseConnector):
    source_name = "MyCareersFuture"

    def search(self, query: str, limit: int = 80) -> List[RawJob]:
        slug = slugify(query)
        url = f"https://www.mycareersfuture.gov.sg/search/{slug}-jobs"

        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "lxml")
        jobs: List[RawJob] = []

        for a in soup.select("a[href*='/job/']"):
            href = a.get("href") or ""
            if not href:
                continue
            full = href if href.startswith("http") else urljoin("https://www.mycareersfuture.gov.sg", href)

            title = _clean(a.get_text(" ", strip=True))
            if len(title) < 3:
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

            employer = "Not stated"
            salary = "Not stated"
            job_type = "Not stated"
            posted = "Unverified"
            closing = "Not stated"
            reqs = "• Not stated"

            text = soup.get_text("\n", strip=True)

            # salary patterns
            m_sal = re.search(r"\$\s?\d[\d,]*\s*-\s*\$\s?\d[\d,]*", text)
            if m_sal:
                salary = _clean(m_sal.group(0))

            if re.search(r"\bFull[- ]?time\b", text, re.IGNORECASE):
                job_type = "Full-time"
            elif re.search(r"\bPart[- ]?time\b", text, re.IGNORECASE):
                job_type = "Part-time"
            elif re.search(r"\bContract\b", text, re.IGNORECASE):
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
