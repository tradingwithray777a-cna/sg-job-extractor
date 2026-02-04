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
    return datetime.utcnow().date()

def _parse_iso_date(s: str) -> Optional[str]:
    if not s:
        return None
    s = s.strip()
    # try first 10 chars
    try:
        d = datetime.strptime(s[:10], "%Y-%m-%d").date()
        return d.strftime("%Y-%m-%d")
    except Exception:
        return None

def _parse_posted_relative(text: str) -> Optional[str]:
    if not text:
        return None
    m = re.search(r"posted\s+(\d+)\s+day", text, re.IGNORECASE)
    if m:
        days = int(m.group(1))
        d = _today_sg() - timedelta(days=days)
        return d.strftime("%Y-%m-%d")
    if re.search(r"posted\s+yesterday", text, re.IGNORECASE):
        d = _today_sg() - timedelta(days=1)
        return d.strftime("%Y-%m-%d")
    return None

def _extract_bullets(desc: str, max_bullets: int = 3) -> str:
    if not desc:
        return "• Not stated"
    desc = re.sub(r"<[^>]+>", " ", desc)
    desc = re.sub(r"\s+", " ", desc).strip()
    parts = re.split(r"[•\n\r]|(?:\.\s+)|(?:;\s+)", desc)

    cands = []
    for p in parts:
        p = _clean(p)
        if 8 <= len(p) <= 90:
            if any(x in p.lower() for x in ["apply", "privacy", "equal opportunity", "cookies"]):
                continue
            cands.append(p)

    out, seen = [], set()
    for c in cands:
        k = c.lower()
        if k not in seen:
            out.append(c)
            seen.add(k)
        if len(out) >= max_bullets:
            break

    if not out:
        short = desc[:80].strip()
        return f"• {short}" if short else "• Not stated"

    return "\n".join([f"• {x}" for x in out])

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

def _jobtype_from_jobposting(jp: dict) -> Optional[str]:
    et = jp.get("employmentType")
    if not et:
        return None
    if isinstance(et, list):
        et = " / ".join([str(x) for x in et if x])
    et = _clean(str(et))
    if not et:
        return None
    low = et.lower()
    if "full" in low:
        return "Full-time"
    if "part" in low:
        return "Part-time"
    if "contract" in low or "temporary" in low:
        return "Contract"
    return et

def _salary_from_jobposting(jp: dict) -> Optional[str]:
    bs = jp.get("baseSalary")
    if not bs:
        return None
    try:
        if isinstance(bs, dict):
            cur = bs.get("currency") or "SGD"
            val = bs.get("value")
            if isinstance(val, dict):
                mn = val.get("minValue")
                mx = val.get("maxValue")
                unit = val.get("unitText") or ""
                if mn and mx:
                    return f"{cur} {mn}-{mx} {unit}".strip()
                if mn:
                    return f"{cur} {mn} {unit}".strip()
            if isinstance(val, (int, float, str)):
                return f"{cur} {val}".strip()
        if isinstance(bs, str):
            return _clean(bs)
    except Exception:
        return None
    return None

class FounditConnector(BaseConnector):
    source_name = "Foundit"

    def search(self, query: str, limit: int = 80) -> List[RawJob]:
        q = quote_plus(query.strip())
        url = f"https://www.foundit.sg/srp/results?query={q}&locations=Singapore"

        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                return []
        except Exception:
            return []

        html = r.text
        soup = BeautifulSoup(html, "html.parser")

        # 1) Try normal anchors
        links = []
        for a in soup.select("a[href*='/job/']"):
            href = a.get("href") or ""
            if not href:
                continue
            full = href if href.startswith("http") else urljoin("https://www.foundit.sg", href)
            if "/job/" in full and full not in links:
                links.append(full)
            if len(links) >= limit * 2:
                break

        # 2) Fallback: regex from raw HTML (Foundit often embeds URLs in scripts)
        if not links:
            hits = re.findall(r'https://www\.foundit\.sg/job/[^"\'\s<]+', html)
            for h in hits:
                if h not in links:
                    links.append(h)
                if len(links) >= limit * 2:
                    break

        if not links:
            # last fallback: relative /job/...
            rel_hits = re.findall(r'"/job/[^"\'\s<]+"' , html)
            for rh in rel_hits:
                rh = rh.strip('"')
                full = urljoin("https://www.foundit.sg", rh)
                if full not in links:
                    links.append(full)
                if len(links) >= limit * 2:
                    break

        jobs: List[RawJob] = []
        for job_url in links:
            det = self._fetch_detail(job_url)
            if det and det.title and det.title != "Not stated":
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

            if jp:
                ho = jp.get("hiringOrganization")
                if isinstance(ho, dict) and ho.get("name"):
                    employer = _clean(str(ho["name"]))

                dp = jp.get("datePosted")
                iso = _parse_iso_date(str(dp)) if dp else None
                if iso:
                    posted = iso

                vt = jp.get("validThrough")
                iso2 = _parse_iso_date(str(vt)) if vt else None
                if iso2:
                    closing = iso2

                sal = _salary_from_jobposting(jp)
                if sal:
                    salary = sal

                jt = _jobtype_from_jobposting(jp)
                if jt:
                    job_type = jt

                desc = jp.get("description") or ""
                reqs = _extract_bullets(str(desc), max_bullets=3)

            if posted == "Unverified":
                page_text = soup.get_text(" ", strip=True)
                rel = _parse_posted_relative(page_text)
                if rel:
                    posted = rel

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
