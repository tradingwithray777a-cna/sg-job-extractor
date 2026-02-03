from __future__ import annotations

import re
from typing import List
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

from .base import BaseConnector, RawJob

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept-Language": "en-SG,en;q=0.9",
}

def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def _looks_like_ui(text: str) -> bool:
    t = (text or "").strip().lower()
    bad = [
        "what’s your preferred work location",
        "what's your preferred work location",
        "filter",
        "sort",
        "job alerts",
        "sign in",
        "login",
    ]
    return (len(t) < 4) or any(b in t for b in bad)

class FastJobsConnector(BaseConnector):
    source_name = "FastJobs"

    def search(self, query: str, limit: int = 80) -> List[RawJob]:
        # FastJobs search (keyword)
        # This URL pattern works commonly; if FastJobs changes it, we’ll adjust.
        q = quote_plus(query.strip())
        url = f"https://www.fastjobs.sg/singapore-jobs/en/search-jobs/{q}/"

        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                return []
        except Exception:
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        jobs: List[RawJob] = []

        # job ad links usually contain /singapore-job-ad/
        for a in soup.select("a[href*='/singapore-job-ad/']"):
            href = a.get("href") or ""
            if not href:
                continue
            full = href if href.startswith("http") else urljoin("https://www.fastjobs.sg", href)

            title = _clean(a.get_text(" ", strip=True))
            if _looks_like_ui(title):
                continue

            if any(j.url == full for j in jobs):
                continue

            det = self._fetch_detail(full)
            if not det.title:
                det.title = title

            # one more UI sanity check
            if _looks_like_ui(det.title):
                continue

            jobs.append(det)
            if len(jobs) >= limit:
                break

        return jobs

    def _fetch_detail(self, job_url: str) -> RawJob:
        try:
            r = requests.get(job_url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                raise RuntimeError("Bad status")

            soup = BeautifulSoup(r.text, "html.parser")
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

            # requirements: first 3 meaningful li items
            bullets = [_clean(li.get_text(" ", strip=True)) for li in soup.select("li")]
            bullets = [b for b in bullets if 6 <= len(b) <= 90][:3]
            if bullets:
                reqs = "\n".join([f"• {b}" for b in bullets])

            # job type detection
            if re.search(r"\bfull[- ]?time\b", text, re.IGNORECASE):
                job_type = "Full-time"
            elif re.search(r"\bpart[- ]?time\b", text, re.IGNORECASE):
                job_type = "Part-time"
            elif re.search(r"\bcontract\b", text, re.IGNORECASE):
                job_type = "Contract"

            # salary (basic heuristic)
            m_sal = re.search(r"S\$\s*[\d,]+(\s*-\s*[\d,]+)?", text, re.IGNORECASE)
            if m_sal:
                salary = _clean(m_sal.group(0))

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
