from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, date
from typing import List, Optional
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

def _today_sg() -> date:
    # good enough for SG; Streamlit cloud runs UTC but we just need dates
    return datetime.utcnow().date()

def _parse_iso_date(s: str) -> Optional[str]:
    """
    Return YYYY-MM-DD or None
    """
    if not s:
        return None
    s = s.strip()
    # common ISO forms
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            d = datetime.strptime(s[:len(fmt)], fmt).date()
            return d.strftime("%Y-%m-%d")
        except Exception:
            pass
    # fallback: try first 10 chars
    try:
        d = datetime.strptime(s[:10], "%Y-%m-%d").date()
        return d.strftime("%Y-%m-%d")
    except Exception:
        return None

def _parse_posted_relative(text: str) -> Optional[str]:
    """
    Convert 'Posted 5 days ago' into YYYY-MM-DD (SG-ish)
    """
    if not text:
        return None
    m = re.search(r"posted\s+(\d+)\s+day", text, re.IGNORECASE)
    if m:
        days = int(m.group(1))
        d = _today_sg() - timedelta(days=days)
        return d.strftime("%Y-%m-%d")

    m = re.search(r"posted\s+(\d+)\s+hour", text, re.IGNORECASE)
    if m:
        # treat hours as today
        return _today_sg().strftime("%Y-%m-%d")

    m = re.search(r"posted\s+yesterday", text, re.IGNORECASE)
    if m:
        d = _today_sg() - timedelta(days=1)
        return d.strftime("%Y-%m-%d")

    return None

def _extract_bullets_from_description(desc: str, max_bullets: int = 3) -> str:
    """
    Create 1–3 short bullet-style phrases (no long paragraphs).
    """
    if not desc:
        return "• Not stated"

    # strip html tags if any got in
    desc = re.sub(r"<[^>]+>", " ", desc)
    desc = re.sub(r"\s+", " ", desc).strip()

    # split into candidate phrases
    parts = re.split(r"[•\n\r]|(?:\.\s+)|(?:;\s+)", desc)

    cands = []
    for p in parts:
        p = _clean(p)
        if 8 <= len(p) <= 90:
            # avoid generic fluff
            if any(x in p.lower() for x in ["apply", "click", "privacy", "equal opportunity"]):
                continue
            cands.append(p)

    # dedupe while keeping order
    out = []
    seen = set()
    for c in cands:
        key = c.lower()
        if key not in seen:
            out.append(c)
            seen.add(key)
        if len(out) >= max_bullets:
            break

    if not out:
        # fallback: take first ~80 chars
        short = desc[:80].strip()
        return f"• {short}" if short else "• Not stated"

    return "\n".join([f"• {x}" for x in out])

def _salary_from_jobposting(jp: dict) -> Optional[str]:
    """
    Try to normalize baseSalary from JSON-LD JobPosting.
    """
    bs = jp.get("baseSalary")
    if not bs:
        return None

    # Sometimes it's a dict: {"@type":"MonetaryAmount","currency":"SGD","value":{"@type":"QuantitativeValue","minValue":...}}
    try:
        if isinstance(bs, dict):
            cur = bs.get("currency") or bs.get("value", {}).get("currency") or "SGD"
            val = bs.get("value")
            if isinstance(val, dict):
                mn = val.get("minValue")
                mx = val.get("maxValue")
                unit = val.get("unitText")
                if mn and mx:
                    return f"{cur} {mn}-{mx} {unit or ''}".strip()
                if mn:
                    return f"{cur} {mn} {unit or ''}".strip()
                if mx:
                    return f"{cur} {mx} {unit or ''}".strip()
            # sometimes 'value' is number/string
            if isinstance(val, (int, float, str)):
                return f"{cur} {val}".strip()
        # sometimes it's a string
        if isinstance(bs, str):
            return _clean(bs)
    except Exception:
        return None

    return None

def _jobtype_from_jobposting(jp: dict) -> Optional[str]:
    et = jp.get("employmentType")
    if not et:
        return None
    if isinstance(et, list):
        et = " / ".join([str(x) for x in et if x])
    et = _clean(str(et))
    if not et:
        return None

    # make it user-friendly
    lower = et.lower()
    if "full" in lower:
        return "Full-time"
    if "part" in lower:
        return "Part-time"
    if "contract" in lower or "temporary" in lower:
        return "Contract"
    return et

def _parse_jsonld_jobposting(soup: BeautifulSoup) -> Optional[dict]:
    scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    for sc in scripts:
        raw = sc.get_text(strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue

        # JSON-LD can be dict, list, or graph
        candidates = []
        if isinstance(data, dict):
            if "@graph" in data and isinstance(data["@graph"], list):
                candidates.extend(data["@graph"])
            else:
                candidates.append(data)
        elif isinstance(data, list):
            candidates.extend(data)

        for obj in candidates:
            if isinstance(obj, dict) and str(obj.get("@type", "")).lower() == "jobposting":
                return obj
    return None

class FounditConnector(BaseConnector):
    source_name = "Foundit"

    def search(self, query: str, limit: int = 80) -> List[RawJob]:
        """
        Foundit search page -> extract job links -> open each job page for details.
        """
        q = quote_plus(query.strip())
        # common search URL pattern
        url = f"https://www.foundit.sg/srp/results?query={q}&locations=Singapore"

        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                return []
        except Exception:
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        jobs: List[RawJob] = []

        # Foundit job links usually contain '/job/'
        # We'll collect unique job links first
        links = []
        for a in soup.select("a[href*='/job/']"):
            href = a.get("href") or ""
            if not href:
                continue
            full = href if href.startswith("http") else urljoin("https://www.foundit.sg", href)
            if "/job/" not in full:
                continue
            if full not in links:
                links.append(full)
            if len(links) >= limit * 2:
                break

        # Fetch details
        for job_url in links:
            detail = self._fetch_detail(job_url)
            if detail and detail.title:
                # keep query relevance modestly (avoid garbage)
                jobs.append(detail)
            if len(jobs) >= limit:
                break

        return jobs

    def _fetch_detail(self, job_url: str) -> RawJob:
        try:
            r = requests.get(job_url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                raise RuntimeError("Bad status")

            soup = BeautifulSoup(r.text, "html.parser")

            # title
            title = ""
            h1 = soup.select_one("h1")
            if h1:
                title = _clean(h1.get_text(" ", strip=True))[:200]

            # fallback title from meta
            if not title:
                mt = soup.select_one("meta[property='og:title']")
                if mt and mt.get("content"):
                    title = _clean(mt["content"])[:200]

            jp = _parse_jsonld_jobposting(soup)

            employer = "Not stated"
            posted = "Unverified"
            closing = "Not stated"
            salary = "Not stated"
            job_type = "Not stated"
            reqs = "• Not stated"

            # JSON-LD JobPosting extraction (best)
            if jp:
                # employer
                ho = jp.get("hiringOrganization")
                if isinstance(ho, dict):
                    nm = ho.get("name")
                    if nm:
                        employer = _clean(str(nm))

                # posted date
                dp = jp.get("datePosted")
                iso = _parse_iso_date(str(dp)) if dp else None
                if iso:
                    posted = iso

                # closing date
                vt = jp.get("validThrough")
                iso2 = _parse_iso_date(str(vt)) if vt else None
                if iso2:
                    closing = iso2

                # salary
                sal = _salary_from_jobposting(jp)
                if sal:
                    salary = sal

                # job type
                jt = _jobtype_from_jobposting(jp)
                if jt:
                    job_type = jt

                # requirements bullets from description
                desc = jp.get("description") or ""
                reqs = _extract_bullets_from_description(str(desc), max_bullets=3)

            # Try to detect 'Posted X days ago' if found on page
            if posted == "Unverified":
                page_text = soup.get_text(" ", strip=True)
                rel = _parse_posted_relative(page_text)
                if rel:
                    posted = rel

            # If still missing requirements, try some page sections
            if reqs.strip() == "• Not stated":
                # look for common sections
                blocks = []
                for sel in ["div", "section"]:
                    for el in soup.select(sel):
                        t = _clean(el.get_text(" ", strip=True))
                        if 40 <= len(t) <= 250 and any(k in t.lower() for k in ["responsibil", "require", "skill", "experience"]):
                            blocks.append(t)
                if blocks:
                    reqs = _extract_bullets_from_description(" ".join(blocks[:3]), max_bullets=3)

            return RawJob(
                title=title or "Not stated",
                employer=employer or "Not stated",
                url=job_url,
                source=self.source_name,
                posted_date=posted or "Unverified",
                closing_date=closing or "Not stated",
                requirements=reqs or "• Not stated",
                salary=salary or "Not stated",
                job_type=job_type or "Not stated",
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
