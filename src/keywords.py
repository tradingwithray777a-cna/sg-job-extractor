def build_keyword_sets(target_role: str):
    tr = target_role.strip()

    core = [
        tr.lower(),
        "community", "partnership", "partnerships", "stakeholder engagement",
        "outreach", "community engagement", "relationship management", "CSR",
        "fundraising", "volunteer management",
    ]

    adjacent = [
        f"{tr} Manager",
        f"{tr} Executive",
        "Community Partnerships Manager",
        "Community Partnership Manager",
        "Community Partnerships Executive",
        "Community Engagement & Partnerships",
        "Stakeholder Partnerships Executive",
        "Partnerships (Community) Manager",
        "Fundraising & Community Partnerships",
        "Corporate Partnerships Executive",
        "Community Outreach & Partnerships",
    ]

    nearby = [
        "Community Engagement Manager",
        "Stakeholder Engagement Manager",
        "Partnerships Manager",
        "Partnership Development Manager",
        "Relationship Manager",
        "CSR Manager",
        "Fundraising Executive",
        "Volunteer Management Executive",
        "Programme Manager (Community)",
        "Social Impact Manager",
        "Public Affairs Executive",
        "Business Development Executive",
    ]

    exclude = [
        "HR business partner",
        "legal partner",
        "audit partner",
        "equity partner",
        "business partner (HR)",
    ]

    # keep unique while preserving order
    def uniq(xs):
        seen = set()
        out = []
        for x in xs:
            x = x.strip()
            if x and x.lower() not in seen:
                seen.add(x.lower())
                out.append(x)
        return out

    return {
        "core_keywords": uniq(core)[:10],
        "adjacent_titles": uniq(adjacent)[:20],
        "nearby_titles": uniq(nearby)[:20],
        "exclude_keywords": uniq(exclude)[:10],
    }

