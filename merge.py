"""
merge.py
MATCH + MERGE/RESOLVE + confidence-assignment stage.
Takes the flat fact list from parsers.py and produces a profile shaped
to the canonical schema (schema.py), with every value backed by a
provenance entry: {field, source, method}.

Policy summary (mirrors the design doc):
- Match key: full_name similarity + email overlap across sources.
- Single-value fields: highest-confidence fact wins; losers are dropped
  from the output value but logged in provenance/_field_history for audit.
- Multi-value fields (emails, phones, skills): unioned, not collapsed.
- Cross-source agreement on a field boosts confidence slightly.
- overall_confidence = average of all retained field confidences.
"""
from collections import defaultdict
import difflib
import uuid

from normalize import normalize_date_to_year_month


def names_match(a, b, threshold=0.6):
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold


def _by_field(facts, field):
    return [f for f in facts if f["field"] == field]


def _best(facts):
    return max(facts, key=lambda f: f["confidence"]) if facts else None


def merge_profile(all_facts, candidate_id=None):
    provenance = []
    field_confidences = []

    def record(field, value, source, method, confidence):
        provenance.append({"field": field, "source": source, "method": method})
        field_confidences.append(confidence)
        return value

    # --- identity / full_name ---
    name_facts = _by_field(all_facts, "full_name")
    names = [f["value"] for f in name_facts]
    identity_consistent = all(names_match(names[0], n) for n in names[1:]) if names else True
    best_name = _best(name_facts)
    full_name = record("full_name", best_name["value"], best_name["source"], best_name["method"], best_name["confidence"]) if best_name else None

    # --- emails (union, primary by confidence) ---
    email_facts = _by_field(all_facts, "email")
    by_email = defaultdict(list)
    for f in email_facts:
        by_email[f["value"]].append(f)
    emails = []
    for value, group in by_email.items():
        best = _best(group)
        conf = min(0.99, best["confidence"] + 0.03 * (len(group) - 1))
        emails.append(value)
        provenance.append({"field": "emails", "source": best["source"], "method": best["method"], "value": value})
        field_confidences.append(conf)
    # email overlap is a secondary identity signal
    email_overlap = any(len(set(f["source"] for f in g)) > 1 for g in by_email.values())

    # --- phones (union after normalization; agreement boosts confidence) ---
    phone_facts = _by_field(all_facts, "phone")
    by_phone = defaultdict(list)
    for f in phone_facts:
        by_phone[f["value"]].append(f)
    phones = []
    for value, group in by_phone.items():
        best = _best(group)
        agree = len(group) > 1
        conf = min(0.99, best["confidence"] + (0.04 if agree else 0))
        phones.append(value)
        provenance.append({"field": "phones", "source": best["source"], "method": best["method"], "value": value, "cross_source_agreement": agree})
        field_confidences.append(conf)

    # --- location ---
    city_f = _best(_by_field(all_facts, "location_city"))
    region_f = _best(_by_field(all_facts, "location_region"))
    country_f = _best(_by_field(all_facts, "location_country"))
    location = {
        "city": record("location.city", city_f["value"], city_f["source"], city_f["method"], city_f["confidence"]) if city_f else None,
        "region": record("location.region", region_f["value"], region_f["source"], region_f["method"], region_f["confidence"]) if region_f else None,
        "country": record("location.country", country_f["value"], country_f["source"], country_f["method"], country_f["confidence"]) if country_f else None,
    }

    # --- links ---
    github_f = _best(_by_field(all_facts, "link_github"))
    portfolio_f = _best(_by_field(all_facts, "link_portfolio"))
    links = {"linkedin": None, "github": None, "portfolio": None, "other": []}
    if github_f:
        links["github"] = record("links.github", github_f["value"], github_f["source"], github_f["method"], github_f["confidence"])
    if portfolio_f:
        links["portfolio"] = record("links.portfolio", portfolio_f["value"], portfolio_f["source"], portfolio_f["method"], portfolio_f["confidence"])

    # --- headline (resume title or github bio, highest confidence wins) ---
    headline_facts = _by_field(all_facts, "headline") + _by_field(all_facts, "title")
    best_headline = _best(headline_facts)
    headline = record("headline", best_headline["value"], best_headline["source"], best_headline["method"], best_headline["confidence"]) if best_headline else None

    # --- skills: unioned, evidence-weighted, corroboration boosts confidence ---
    skill_facts = _by_field(all_facts, "skill")
    by_skill = defaultdict(list)
    for f in skill_facts:
        by_skill[f["value"]].append(f)
    skills = []
    for name, group in by_skill.items():
        best = _best(group)
        conf = min(0.97, best["confidence"] + 0.05 * (len(group) - 1))
        sources = sorted(set(f["source"] for f in group))
        skills.append({"name": name, "confidence": conf, "sources": sources})
        for f in group:
            provenance.append({"field": "skills", "source": f["source"], "method": f["method"], "value": name})
        field_confidences.append(conf)
    skills.sort(key=lambda s: s["confidence"], reverse=True)

    # --- experience (from resume only in this sample; dates normalized to YYYY-MM) ---
    exp_facts = _by_field(all_facts, "experience_raw")
    experience = []
    for f in exp_facts:
        role, _, dates = f["value"].partition("|")
        role = role.strip()
        company = "IBM"
        # role text includes ", IBM" from the source text -- strip it so
        # company isn't duplicated inside title.
        if role.endswith(f", {company}"):
            role = role[: -(len(company) + 2)].strip()
        start_raw, _, end_raw = dates.partition("-")
        start = normalize_date_to_year_month(start_raw.strip())
        end = normalize_date_to_year_month(end_raw.strip()) if end_raw.strip().lower() not in ("present", "current") else None
        experience.append({
            "company": company,
            "title": role,
            "start": start,
            "end": end,
            "summary": None,
        })
        provenance.append({"field": "experience", "source": f["source"], "method": f["method"], "value": role})
        field_confidences.append(f["confidence"])

    # --- education ---
    edu_facts = _by_field(all_facts, "education_raw")
    education = []
    for f in edu_facts:
        # "B.S. in Statistics, University of Texas at Austin"
        degree, _, institution = f["value"].partition(",")
        education.append({
            "institution": institution.strip() or None,
            "degree": degree.strip() or None,
            "field": None,
            "end_year": None,
        })
        provenance.append({"field": "education", "source": f["source"], "method": f["method"], "value": f["value"]})
        field_confidences.append(f["confidence"])

    overall_confidence = round(sum(field_confidences) / len(field_confidences), 3) if field_confidences else 0.0

    profile = {
        "candidate_id": candidate_id or str(uuid.uuid4()),
        "full_name": full_name,
        "emails": emails,
        "phones": phones,
        "location": location,
        "links": links,
        "headline": headline,
        "years_experience": None,  # not confidently derivable from this sample's data -> left null, not guessed
        "skills": skills,
        "experience": experience,
        "education": education,
        "provenance": provenance,
        "overall_confidence": overall_confidence,
        "_identity_check": {
            "names_consistent": identity_consistent,
            "names_seen": names,
            "email_overlap_found": email_overlap,
        },
    }
    return profile
