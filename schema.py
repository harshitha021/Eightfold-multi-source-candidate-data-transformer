"""
schema.py
Canonical output schema (from the problem statement) + a lightweight
validator. No external schema libs — kept dependency-free and explicit
so it's easy to audit.
"""
import re

PHONE_RE = re.compile(r"^\+\d{8,15}$")
EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")
YEAR_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
ISO_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")

CANONICAL_FIELDS = {
    "candidate_id": str,
    "full_name": str,
    "emails": list,
    "phones": list,
    "location": dict,
    "links": dict,
    "headline": (str, type(None)),
    "years_experience": (int, float, type(None)),
    "skills": list,
    "experience": list,
    "education": list,
    "provenance": list,
    "overall_confidence": (int, float),
}


def validate_profile(profile):
    """Validate a profile dict against the canonical schema.
    Returns (is_valid, list_of_errors). Never raises -- callers decide
    whether to drop fields, null them, or fail the run."""
    errors = []

    for field, expected_type in CANONICAL_FIELDS.items():
        if field not in profile:
            errors.append(f"missing field: {field}")
            continue
        if not isinstance(profile[field], expected_type):
            errors.append(f"{field}: expected {expected_type}, got {type(profile[field])}")

    for email in profile.get("emails", []):
        if not EMAIL_RE.match(email):
            errors.append(f"emails: '{email}' does not match email format")

    for phone in profile.get("phones", []):
        if not PHONE_RE.match(phone):
            errors.append(f"phones: '{phone}' is not E.164 (+<digits>)")

    loc = profile.get("location", {})
    if loc and "country" in loc and loc["country"] and not ISO_COUNTRY_RE.match(loc["country"]):
        errors.append(f"location.country: '{loc['country']}' is not ISO-3166 alpha-2")

    for exp in profile.get("experience", []):
        for key in ("start", "end"):
            val = exp.get(key)
            if val and not YEAR_MONTH_RE.match(val):
                errors.append(f"experience.{key}: '{val}' is not YYYY-MM")

    for sk in profile.get("skills", []):
        if not (0.0 <= sk.get("confidence", -1) <= 1.0):
            errors.append(f"skills: confidence out of [0,1] for '{sk.get('name')}'")

    if not (0.0 <= profile.get("overall_confidence", -1) <= 1.0):
        errors.append("overall_confidence out of [0,1]")

    return (len(errors) == 0, errors)
