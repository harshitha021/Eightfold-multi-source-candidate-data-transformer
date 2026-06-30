# Multi-Source Candidate Data Transformer

Merges candidate data from multiple structured and unstructured sources
(recruiter CSV, resume PDF, GitHub API JSON) into one canonical profile,
with field-level provenance, confidence scoring, and a runtime-configurable
output projection layer.

See the accompanying one-page design doc (`YourFullName_YourEmail_Eightfold.pdf`)
for the full design rationale, schema, merge policy, and edge cases.

## Folder structure

```
code/
├── transform.py             CLI entrypoint — runs the full pipeline
├── parsers.py                DETECT + EXTRACT — reads CSV/PDF/JSON into "facts"
├── normalize.py               NORMALIZE — phone/date/skill normalization helpers
├── merge.py                   MATCH + MERGE/RESOLVE — builds the canonical profile
├── schema.py                  VALIDATE — canonical schema + validator
├── config.py                  PROJECT-TO-OUTPUT — runtime config/projection layer
│
├── config_example.json        sample config: name/email/phone/skills only
├── config_experience.json     sample config: company + work history
├── config_full_view.json      sample config: experience + links + education + provenance
│
├── data/                      sample input sources
│   ├── recruiter.csv               (structured)
│   ├── matthew_carpenter_resume.pdf (unstructured)
│   └── github_matthew_carpenter.json (unstructured)
│
└── output/                    generated results land here (gitignored if you prefer)
```

## Setup

Requires Python 3.9+.

```bash
pip install -r requirements.txt
```

(Only dependency is `pdfplumber`, used for resume PDF text extraction.)

## Usage

### Default canonical schema (full profile)
```bash
python transform.py \
  --csv data/recruiter.csv \
  --resume data/matthew_carpenter_resume.pdf \
  --github data/github_matthew_carpenter.json \
  --out output/profile.json
```
Produces the full canonical profile: candidate_id, full_name, emails[],
phones[], location, links, headline, years_experience, skills[], experience[],
education[], provenance[], overall_confidence.

### With a custom runtime output config (projection)
```bash
python transform.py \
  --csv data/recruiter.csv \
  --resume data/matthew_carpenter_resume.pdf \
  --github data/github_matthew_carpenter.json \
  --config config_experience.json \
  --out output/experience_view.json
```
The `--config` flag reshapes the output (field subset, renaming, per-field
normalization, missing-value behavior) **without any code changes** — same
engine, different view. Three example configs are included:

| Config | What it returns |
|---|---|
| `config_example.json` | name, primary email, phone, skills |
| `config_experience.json` | name, current company/title, full work history |
| `config_full_view.json` | work history, education, links, provenance |

You can write your own config following the same shape — see comments at
the top of `config.py` for the full field spec (`path`, `from`, `type`,
`normalize`, `required`, `include_confidence`, `on_missing`).

### Running against your own data
Swap the `--csv` / `--resume` / `--github` paths for your own files. You
need at least one structured source (CSV) and one unstructured source
(resume PDF or GitHub JSON) — the run will error out with a clear message
if neither group is represented.

## Output guarantees

- **No invented data.** A field with no supporting evidence is `null`
  (or omitted, per the config's `on_missing` setting) — never guessed.
- **Every value is traceable.** The `provenance` array logs which source
  and extraction method produced each field, so a recruiter can audit
  any value back to where it came from.
- **Conflicts are resolved, not hidden.** When sources disagree (e.g. job
  title), the highest-confidence value wins, but the losing value isn't
  thrown away — it stays in `provenance` for review.
- **Graceful degradation.** A missing or corrupted source file doesn't
  crash the run; that source just contributes zero facts and the
  pipeline proceeds with whatever data is available.

## Known limitations / scope cuts

- Resume/CSV field extraction uses layout-specific regex heuristics
  tuned to the sample inputs; a different resume format may need
  adjusted patterns.
- No OCR — assumes text-based (not scanned) PDFs.
- No nickname/alias name matching (e.g. "Matt" vs. a legal name) and no
  multi-candidate disambiguation when two different people share a name
  — the pipeline assumes one candidate per run.
- LinkedIn parsing isn't implemented (no public API access in this
  environment); the architecture supports adding it as another parser.
