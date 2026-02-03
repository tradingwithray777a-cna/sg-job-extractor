def relevance_score(target_role: str, title: str, employer: str, emp_type: str, adjacent_titles, nearby_titles):
    t = (title or "").lower()
    trg = (target_role or "").lower()

    # A) Title match (max 140)
    title_score = 0
    if trg and trg in t:
        title_score = 120
    else:
        main_words = [w for w in trg.split() if w]
        if main_words and all(w.lower() in t for w in main_words):
            title_score = 100
        elif any(a.lower() in t for a in adjacent_titles):
            title_score = 85
        elif any(n.lower() in t for n in nearby_titles):
            title_score = 60
        elif any(w.lower() in t for w in main_words):
            title_score = 30

    # B) Domain match (max 40) - heuristic
    e = (employer or "").lower()
    domain_score = 10
    if any(k in e for k in ["ngo", "foundation", "charity", "community", "public", "government", "hospital", "health"]):
        domain_score = 40
    elif any(k in e for k in ["institute", "association", "society", "group", "services"]):
        domain_score = 25

    # C) Employment type (max 20)
    et = (emp_type or "").lower()
    emp_score = 0
    if "full" in et:
        emp_score = 20
    elif "contract" in et or "temp" in et:
        emp_score = 15
    elif "part" in et:
        emp_score = 5

    return min(200, title_score + domain_score + emp_score)

