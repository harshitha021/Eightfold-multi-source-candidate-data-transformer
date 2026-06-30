"""
parsers.py
DETECT + EXTRACT stage. Each parser reads one raw source and returns a
list of "facts": {field, value, source, method, confidence}.
Facts are the only currency passed to merge.py -- nothing here writes
canonical-schema shapes directly, that happens later so source parsing
stays decoupled from the output contract.

Robustness: every parser is wrapped so a missing/garbled file degrades
to an empty fact list instead of crashing the run (see transform.py).
"""
import csv
import json
import re

from normalize import normalize_phone, normalize_email, normalize_skill, country_from_location_text

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


def parse_csv(path):
    """Structured source -> highest base trust for identity fields."""
    facts = []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            row = next(csv.DictReader(f), None)
        if not row:
            return facts
    except (FileNotFoundError, StopIteration, csv.Error):
        return facts

    if row.get("full_name"):
        facts.append(dict(field="full_name", value=row["full_name"].strip(),
                           source="recruiter_csv", method="structured_field", confidence=0.95))
    if row.get("title"):
        facts.append(dict(field="title", value=row["title"].strip(),
                           source="recruiter_csv", method="structured_field", confidence=0.85))
    if row.get("company"):
        facts.append(dict(field="company", value=row["company"].strip(),
                           source="recruiter_csv", method="structured_field", confidence=0.85))
    email = normalize_email(row.get("email"))
    if email:
        facts.append(dict(field="email", value=email,
                           source="recruiter_csv", method="structured_field", confidence=0.95))
    phone = normalize_phone(row.get("phone"))
    if phone:
        facts.append(dict(field="phone", value=phone,
                           source="recruiter_csv", method="structured_field", confidence=0.95))
    return facts


def parse_resume(path):
    """Unstructured PDF -> moderate trust; primary source of headline,
    skills, experience, education fields the CSV doesn't have."""
    facts = []
    if pdfplumber is None:
        return facts
    try:
        with pdfplumber.open(path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception:
        return facts
    if not text.strip():
        return facts

    lines = text.strip().splitlines()

    if lines:
        facts.append(dict(field="full_name", value=lines[0].strip(),
                           source="resume_pdf", method="text_extraction", confidence=0.7))
    if len(lines) > 1:
        facts.append(dict(field="headline", value=lines[1].strip(),
                           source="resume_pdf", method="text_extraction", confidence=0.7))

    phone_match = re.search(r"(\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})", text)
    if phone_match:
        norm = normalize_phone(phone_match.group(1))
        if norm:
            facts.append(dict(field="phone", value=norm,
                               source="resume_pdf", method="text_extraction", confidence=0.6))

    for email in set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)):
        facts.append(dict(field="email", value=normalize_email(email),
                           source="resume_pdf", method="text_extraction", confidence=0.6))

    loc_match = re.search(r"([A-Z][a-zA-Z]+,\s?(?:Texas|[A-Z]{2}))", text)
    if loc_match:
        loc_text = loc_match.group(1).strip()
        city, _, region = loc_text.partition(",")
        facts.append(dict(field="location_city", value=city.strip(),
                           source="resume_pdf", method="text_extraction", confidence=0.75))
        facts.append(dict(field="location_region", value=region.strip(),
                           source="resume_pdf", method="text_extraction", confidence=0.75))
        country = country_from_location_text(loc_text)
        if country:
            facts.append(dict(field="location_country", value=country,
                               source="resume_pdf", method="heuristic_inference", confidence=0.6))

    skills_match = re.search(r"Skills\s*\n(.+)", text)
    if skills_match:
        for sk in skills_match.group(1).split(","):
            norm = normalize_skill(sk)
            if norm:
                facts.append(dict(field="skill", value=norm,
                                   source="resume_pdf", method="resume_stated", confidence=0.7))

    edu_match = re.search(r"Education\s*\n(.+)", text)
    if edu_match:
        facts.append(dict(field="education_raw", value=edu_match.group(1).strip(),
                           source="resume_pdf", method="text_extraction", confidence=0.8))

    for role, dates in re.findall(r"([A-Za-z ]*(?:Data Analyst|Analyst)[A-Za-z, ]*)\s*\((\d{4}\s*-\s*[\w\s]+)\)", text):
        facts.append(dict(field="experience_raw", value=f"{role.strip()}|{dates.strip()}",
                           source="resume_pdf", method="text_extraction", confidence=0.75))

    return facts


def parse_github(path):
    """Unstructured JSON -> identity fields lower trust; strong signal
    for derived (not self-reported) skills via languages/topics."""
    facts = []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return facts
    if not isinstance(data, dict):
        return facts

    if data.get("name"):
        facts.append(dict(field="full_name", value=data["name"].strip(),
                           source="github_api", method="profile_field", confidence=0.5))
    email = normalize_email(data.get("email"))
    if email:
        facts.append(dict(field="email", value=email,
                           source="github_api", method="profile_field", confidence=0.8))
    if data.get("location"):
        loc_text = data["location"].strip()
        city, _, region = loc_text.partition(",")
        facts.append(dict(field="location_city", value=city.strip(),
                           source="github_api", method="profile_field", confidence=0.7))
        if region.strip():
            facts.append(dict(field="location_region", value=region.strip(),
                               source="github_api", method="profile_field", confidence=0.7))
        country = country_from_location_text(loc_text)
        if country:
            facts.append(dict(field="location_country", value=country,
                               source="github_api", method="heuristic_inference", confidence=0.55))
    if data.get("company"):
        facts.append(dict(field="company", value=data["company"].lstrip("@").strip(),
                           source="github_api", method="profile_field", confidence=0.55))
    if data.get("blog"):
        facts.append(dict(field="link_portfolio", value=data["blog"].strip(),
                           source="github_api", method="profile_field", confidence=0.85))
    if data.get("login"):
        facts.append(dict(field="link_github", value=f"https://github.com/{data['login']}",
                           source="github_api", method="profile_field", confidence=0.95))
    if data.get("bio"):
        facts.append(dict(field="headline", value=data["bio"].strip(),
                           source="github_api", method="profile_field", confidence=0.55))

    lang_breakdown = data.get("language_breakdown", {})
    for lang, share in lang_breakdown.items():
        norm = normalize_skill(lang)
        if not norm:
            continue
        conf = round(min(0.95, 0.5 + share), 2)
        facts.append(dict(field="skill", value=norm,
                           source="github_api", method="repo_language_derived", confidence=conf))

    topic_counts = {}
    for repo in data.get("repos", []):
        for topic in repo.get("topics", []):
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
    for topic, count in topic_counts.items():
        norm = normalize_skill(topic)
        if not norm:
            continue
        conf = round(min(0.9, 0.4 + 0.15 * count), 2)
        facts.append(dict(field="skill", value=norm,
                           source="github_api", method="repo_topic_derived", confidence=conf))

    return facts
