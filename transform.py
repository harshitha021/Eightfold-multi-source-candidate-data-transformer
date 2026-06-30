"""
transform.py
CLI. Runs DETECT -> EXTRACT -> NORMALIZE -> MERGE -> VALIDATE, always
producing a full canonical profile, then optionally PROJECTs it through
a custom output config.

Usage (default canonical schema):
    python transform.py --csv data/recruiter.csv --resume data/matthew_carpenter_resume.pdf \\
        --github data/github_matthew_carpenter.json --out output/profile.json

Usage (custom output config):
    python transform.py --csv data/recruiter.csv --resume data/matthew_carpenter_resume.pdf \\
        --github data/github_matthew_carpenter.json --config config_example.json --out output/projected.json

Robustness: a missing/garbled source file does not crash the run --
each parser degrades to an empty fact list and the merge proceeds with
whatever facts are available (see parsers.py).
"""
import argparse
import json
import sys

from parsers import parse_csv, parse_resume, parse_github
from merge import merge_profile
from schema import validate_profile
from config import apply_output_config, MissingRequiredFieldError


def main():
    ap = argparse.ArgumentParser(description="Multi-source candidate data transformer")
    ap.add_argument("--csv", help="Path to recruiter CSV (structured source)")
    ap.add_argument("--github", help="Path to GitHub JSON (unstructured source)")
    ap.add_argument("--resume", help="Path to resume PDF (unstructured source)")
    ap.add_argument("--config", help="Optional runtime output config JSON (projection)")
    ap.add_argument("--out", default="output/profile.json", help="Output path")
    args = ap.parse_args()

    if not args.csv and not (args.github or args.resume):
        print("error: provide at least one structured source (--csv) and one unstructured source (--resume/--github)", file=sys.stderr)
        sys.exit(1)

    all_facts = []
    if args.csv:
        all_facts += parse_csv(args.csv)
    if args.resume:
        all_facts += parse_resume(args.resume)
    if args.github:
        all_facts += parse_github(args.github)

    if not all_facts:
        print("warning: no usable data extracted from any source; writing an empty-but-valid skeleton profile", file=sys.stderr)

    profile = merge_profile(all_facts)

    is_valid, errors = validate_profile(profile)
    if not is_valid:
        print("schema validation warnings (degrading gracefully, not failing the run):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)

    result = profile
    if args.config:
        with open(args.config, encoding="utf-8") as f:
            cfg = json.load(f)
        try:
            projected, proj_errors = apply_output_config(profile, cfg)
            for e in proj_errors:
                print(f"projection warning: {e}", file=sys.stderr)
            result = projected
        except MissingRequiredFieldError as e:
            print(f"error: {e}", file=sys.stderr)
            sys.exit(1)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"Wrote {args.out}")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
