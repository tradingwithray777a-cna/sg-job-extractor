from __future__ import annotations

from dataclasses import dataclass
import re
from typing import List, Dict


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


@dataclass
class KeywordSets:
    target_role: str
    core_keywords: List[str]
    adjacent_titles: List[str]
    nearby_titles: List[str]
    exclude_keywords: List[str]

    def as_dict(self) -> Dict[str, List[str]]:
        return {
            "core_keywords": self.core_keywords,
            "adjacent_titles": self.adjacent_titles,
            "nearby_titles": self.nearby_titles,
            "exclude_keywords": self.exclude_keywords,
        }


def build_keyword_sets(target_role: str) -> KeywordSets:
    """
    Rule-based keyword sets.
    Works for most job titles and includes special handling for a few common roles.
    """
    tr = (target_role or "").strip()
    tr_n = _norm(tr)

    # Core keywords = target + a few safe synonyms
    synonyms = {
        "officer": ["executive", "specialist", "coordinator"],
        "procurement": ["sourcing", "purchasing", "vendor management", "supplier management", "category management"],
        "receptionist": ["front desk", "front office", "guest services", "customer service"],
        "community": ["engagement", "outreach", "relations"],
        "partnership": ["alliances", "stakeholder", "collaboration", "partnerships"],
        "engineer": ["engineering"],
        "civil": ["construction", "infrastructure"],
    }

    words = [w for w in tr_n.split(" ") if w]
    core = [tr]
    for w in words:
        if w in synonyms:
            core.extend(synonyms[w])

    # De-dupe core
    seen = set()
    core_keywords: List[str] = []
    for k in core:
        kn = _norm(k)
        if kn and kn not in seen:
            core_keywords.append(k)
            seen.add(kn)

    # Adjacent and nearby titles (templates + role-specific)
    adjacent: List[str] = []
    nearby: List[str] = []
    exclude: List[str] = []

    if "procurement" in tr_n:
        adjacent = [
            "Procurement Executive",
            "Procurement Specialist",
            "Sourcing Specialist",
            "Purchasing Officer",
            "Purchasing Executive",
            "Buyer",
            "Senior Buyer",
            "Category Executive",
            "Vendor Management Executive",
            "Procurement Coordinator",
            "Strategic Sourcing Executive",
            "Supply Chain Procurement Executive",
        ]
        nearby = [
            "Supply Chain Executive",
            "Logistics Executive",
            "Operations Executive",
            "Inventory Planner",
            "Materials Planner",
            "Contracts Executive",
            "Contract Administrator",
            "Purchase-to-Pay (P2P) Executive",
            "Vendor Coordinator",
            "Demand Planner",
        ]
        exclude = ["sap developer", "software engineer", "developer"]

    elif "receptionist" in tr_n:
        adjacent = [
            "Front Desk Officer",
            "Front Office Executive",
            "Reception Executive",
            "Clinic Receptionist",
            "Hotel Receptionist",
            "Guest Service Officer",
            "Administrative Receptionist",
            "Office Receptionist",
            "Lobby Ambassador",
            "Concierge (Front Desk)",
        ]
        nearby = [
            "Administrative Assistant",
            "Office Administrator",
            "Customer Service Officer",
            "Guest Relations Officer",
            "Admin Coordinator",
            "Clinic Assistant",
            "Service Desk Officer",
            "Facilities Coordinator",
            "Call Centre Agent",
        ]
        exclude = ["telemarketer", "commission only"]

    elif ("community" in tr_n and "partnership" in tr_n) or ("community partnership" in tr_n):
        adjacent = [
            "Community Partnerships Executive",
            "Partnerships Executive",
            "Community Engagement Executive",
            "Stakeholder Management Executive",
            "Community Outreach Executive",
            "Partnerships Manager",
            "Strategic Partnerships Executive",
            "Partnership Development Executive",
            "Community Relations Executive",
            "Stakeholder Engagement Officer",
            "Partnership Officer",
        ]
        nearby = [
            "Programme Executive",
            "Programme Coordinator",
            "Corporate Relations Executive",
            "Business Development Executive",
            "Account Executive (Partnerships)",
            "CSR Executive",
            "Events Executive",
            "Community Development Executive",
            "Stakeholder Relations Officer",
        ]
        exclude = []

    elif "civil" in tr_n and "engineer" in tr_n:
        adjacent = [
            "Civil Engineer",
            "Site Engineer (Civil)",
            "Project Engineer (Civil)",
            "Resident Engineer (Civil)",
            "Civil & Structural Engineer",
            "Structural Engineer",
            "Geotechnical Engineer",
            "Construction Engineer",
            "Engineering Executive (Civil)",
        ]
        nearby = [
            "Project Engineer",
            "Site Engineer",
            "Quantity Surveyor",
            "Project Coordinator",
            "Construction Manager",
            "Project Manager (Construction)",
            "BIM Coordinator",
            "Safety Officer (Construction)",
        ]
        exclude = ["software engineer", "network engineer", "it engineer"]

    else:
        # Generic fallbacks
        adjacent = [
            f"{tr} Executive",
            f"{tr} Specialist",
            f"Senior {tr}",
            f"Assistant {tr}",
            f"{tr} Coordinator",
        ]
        nearby = [
            "Operations Executive",
            "Coordinator",
            "Executive",
            "Specialist",
        ]
        exclude = []

    def dedupe(lst: List[str]) -> List[str]:
        out: List[str] = []
        ss = set()
        for x in lst:
            xn = _norm(x)
            if xn and xn not in ss:
                out.append(x)
                ss.add(xn)
        return out

    return KeywordSets(
        target_role=tr,
        core_keywords=dedupe(core_keywords)[:10],
        adjacent_titles=dedupe(adjacent)[:20],
        nearby_titles=dedupe(nearby)[:20],
        exclude_keywords=dedupe(exclude)[:10],
    )
