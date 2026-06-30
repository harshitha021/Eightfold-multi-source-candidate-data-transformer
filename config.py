"""
config.py
PROJECT-TO-OUTPUT stage. Takes the full canonical profile (always
computed in full by merge.py) and a runtime config, and produces a
reshaped view -- same engine, no code changes needed per caller.

Config shape (see design doc):
{
  "fields": [
    { "path": "full_name", "type": "string", "required": true },
    { "path": "primary_email", "from": "emails[0]", "type": "string", "required": true },
    { "path": "phone", "from": "phones[0]", "type": "string", "normalize": "E164" },
    { "path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical" }
  ],
  "include_confidence": true,
  "on_missing": "null"   # "null" | "omit" | "error"
}
"""
import re


class MissingRequiredFieldError(Exception):
    pass


def _resolve_path(profile, path):
    """Supports dotted paths, list indices like emails[0], and a simple
    'skills[].name' projection that maps a list of objects to a list of
    one field. Returns (value, found: bool)."""
    if "[]." in path:
        list_path, attr = path.split("[].", 1)
        items = profile.get(list_path)
        if not isinstance(items, list):
            return None, False
        return [item.get(attr) for item in items if attr in item], True

    list_index_dotted_match = re.match(r"^([a-zA-Z_]+)\[(\d+)\]\.(.+)$", path)
    if list_index_dotted_match:
        key, idx, rest = list_index_dotted_match.group(1), int(list_index_dotted_match.group(2)), list_index_dotted_match.group(3)
        items = profile.get(key)
        if isinstance(items, list) and len(items) > idx:
            return _resolve_path(items[idx], rest)
        return None, False

    list_index_match = re.match(r"^([a-zA-Z_]+)\[(\d+)\]$", path)
    if list_index_match:
        key, idx = list_index_match.group(1), int(list_index_match.group(2))
        items = profile.get(key)
        if isinstance(items, list) and len(items) > idx:
            return items[idx], True
        return None, False

    if "." in path:
        head, _, rest = path.partition(".")
        sub = profile.get(head)
        if isinstance(sub, dict):
            return _resolve_path(sub, rest)
        return None, False

    if path in profile:
        return profile[path], True
    return None, False


def apply_output_config(profile, config):
    """Returns (projected_dict, errors). Malformed/missing-required
    values are dropped or nulled per on_missing rather than invented."""
    on_missing = config.get("on_missing", "null")
    include_confidence = config.get("include_confidence", False)
    out = {}
    errors = []

    for field_cfg in config.get("fields", []):
        out_path = field_cfg["path"]
        src_path = field_cfg.get("from", out_path)
        required = field_cfg.get("required", False)

        value, found = _resolve_path(profile, src_path)

        if not found or value in (None, [], ""):
            if required and on_missing == "error":
                raise MissingRequiredFieldError(f"required field '{out_path}' missing")
            if on_missing == "omit":
                if required:
                    errors.append(f"omitted required field: {out_path}")
                continue
            value = None  # default: "null"

        out[out_path] = value
        if include_confidence:
            out[f"{out_path}_confidence"] = profile.get("overall_confidence")

    return out, errors
