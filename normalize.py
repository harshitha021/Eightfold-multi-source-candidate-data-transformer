"""
normalize.py
Pure normalization functions. Each returns None (never a guess) if it
can't confidently normalize the input -- "wrong but confident" is worse
than "honestly empty" per the problem statement.
"""
import re

# Minimal alias map so resume-stated and GitHub-derived skill names collapse
# to one canonical token (e.g. "Postgres" / "PostgreSQL" -> "postgresql").
SKILL_ALIASES = {
    "py": "python", "python3": "python", "python": "python",
    "js": "javascript", "javascript": "javascript",
    "sql": "sql", "postgres": "postgresql", "postgresql": "postgresql",
    "tableau": "tableau", "etl": "etl", "automation": "automation",
    "etl pipelines": "etl", "data pipelines": "etl",
    "statistics": "statistics", "ab-testing": "ab-testing", "cli": "cli",
    "reporting": "reporting", "shell": "shell", "react": "react",
    "finance": "finance", "a/b testing": "ab-testing",
    "data visualization": "data-visualization", "data-visualization": "data-visualization",
}


def normalize_phone(raw, default_country_digits="1"):
    """Best-effort -> E.164 (+<country><digits>). Returns None if the
    digit count is implausible rather than emitting a malformed value."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        digits = default_country_digits + digits
    if not (8 <= len(digits) <= 15):
        return None
    return "+" + digits


def normalize_email(raw):
    if not raw:
        return None
    return raw.strip().lower()


def normalize_skill(raw):
    if not raw:
        return None
    key = raw.strip().lower()
    return SKILL_ALIASES.get(key, key)


def normalize_date_to_year_month(raw):
    """Resumes/JSON give varying date granularity. Year-only inputs are
    normalized to YYYY-01 (documented assumption, not invented precision)."""
    if not raw:
        return None
    raw = raw.strip()
    if re.match(r"^\d{4}-\d{2}$", raw):
        return raw
    if re.match(r"^\d{4}$", raw):
        return f"{raw}-01"
    if raw.lower() in ("present", "current", "now"):
        return None  # open-ended; caller stores as null end date
    return None


def country_from_location_text(text):
    """Very small heuristic: US state names/abbreviations -> 'US'.
    Left null (not guessed) for anything not confidently recognized."""
    if not text:
        return None
    us_signals = ("texas", "california", "new york", ", tx", ", ca", ", ny", "usa", "united states")
    if any(sig in text.lower() for sig in us_signals):
        return "US"
    return None
