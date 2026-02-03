from __future__ import annotations
from dataclasses import dataclass
from typing import List


@dataclass
class RawJob:
    title: str
    employer: str
    url: str
    source: str
    posted_date: str  # YYYY-MM-DD or "Unverified"
    closing_date: str  # YYYY-MM-DD or "Not stated"
    requirements: str  # 1–3 bullet-ish phrases
    salary: str  # or "Not stated"
    job_type: str  # Full-time / Part-time / Contract / Not stated


class BaseConnector:
    source_name: str = "Base"

    def search(self, query: str, limit: int = 80) -> List[RawJob]:
        raise NotImplementedError
