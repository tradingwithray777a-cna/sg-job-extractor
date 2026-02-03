from __future__ import annotations

import re
from typing import List
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from .base import BaseConnector, RawJob

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept-Language": "en-SG,en;q=0.9",
}

def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


class GrabJobsConnector(BaseConnector):
    source_name = "GrabJobs"

    def search(self, query: str, limit: int = 80) -> List[RawJob]:
        url = f"https://grabjobs.co/singapore/jobs?q={quote_plus(query)}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                return []
        except Exception:
            return []

        soup = BeautifulSoup(r.text, "html.parser")  # ✅ no lxml dependency
        jobs: List[RawJob] = []

        # Try multiple patterns for job links
        link_selectors = [
            "a[href*='/singapore/job/']",
            "a[href*='/singapore/jobs/']",
            "a[href*='/job/']",
        ]

        links = []
        for sel in link_selectors:
            links.extend(soup.select(sel))

        for a in links:
            href = a.get("href") or ""
            if not href:
                continue
            if href.startswith("/"):
                href = "https://grabjobs.co" + href
            elif not href.startswith("http"):
                continue

            title = _clean(a.get_text(" ", strip=True))
            if len(title) < 3:
                continue

            if any(j.url == href for j in jobs):
                continue

            det = self._fetch_detail(href)
            if not det.title:
                det.title = title

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

            employer = "Not stated"
            salary = "Not stated"
            job_type = "Not stated"
            posted = "Unverified"
            closing = "Not stated"
            reqs = "• Not stated"

            text = soup.get_text("\n", strip=True)

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

            # salary
            m_sal = re.search(r"\$\s?\d[\d,]*\s*-\s*\$\s?\d[\d,]*", text)
            if m_sal:
                salary = _clean(m_sal.group(0))

            # employer heuristic
            # try meta / common labels
            for pat in [r"Company\s*:\s*(.+)", r"Employer\s*:\s*(.+)"]:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    employer = _clean(m.group(1))[:120]
                    break

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
