from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple
import re
import requests


@dataclass
class RawJob:
    title: str
    employer: str
    url: str
    source: str
    posted_date: str
    closing_date: str
    requirements: str
    salary: str
    job_type: str


class BaseConnector:
    source_name: str = "Base"

    def __init__(self):
        self.last_debug: Dict[str, str] = {}

    def _set_debug(self, **kwargs):
        # store strings only (safe for Notes)
        for k, v in kwargs.items():
            self.last_debug[str(k)] = str(v)

    def http_get(self, url: str, headers: Optional[dict] = None, timeout: int = 30) -> Tuple[int, str, str]:
        """
        Returns: (status_code, final_url, text_or_error)
        Also records debug info into self.last_debug
        """
        self.last_debug = {}  # reset each request batch
        try:
            r = requests.get(url, headers=headers or {}, timeout=timeout, allow_redirects=True)
            status = r.status_code
            final_url = r.url
            text = r.text or ""

            # Extract <title> safely
            m = re.search(r"<title[^>]*>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
            page_title = re.sub(r"\s+", " ", (m.group(1).strip() if m else ""))[:120]

            snippet = re.sub(r"\s+", " ", text[:200]).strip()

            self._set_debug(
                status_code=status,
                final_url=final_url,
                page_title=page_title,
                html_len=len(text),
                html_snippet=snippet,
            )
            return status, final_url, text
        except Exception as e:
            self._set_debug(error=repr(e))
            return 0, url, repr(e)
