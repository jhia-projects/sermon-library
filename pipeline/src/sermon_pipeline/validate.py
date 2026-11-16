"""Gate before publishing: JSON Schema + checks JSON Schema can't express."""

from __future__ import annotations

import json
from pathlib import Path

from datetime import date

from jsonschema import Draft202012Validator, FormatChecker

from .scripture import parse_reference

MAX_GAP_DAYS = 365
MAX_SPAN_DAYS = 3 * 365 + 1
MIN_BOOK_SHARE = 0.8  # floor for every church; a source may set a stricter min_book_share
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schema" / "library.schema.json"


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_library(lib: dict) -> list[str]:
    """Return a list of human-readable problems (empty = valid)."""
    validator = Draft202012Validator(load_schema(), format_checker=FormatChecker())
    errors = [
        f"schema: {'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
        for e in sorted(validator.iter_errors(lib), key=lambda e: list(e.absolute_path))
    ]
    if errors:
        return errors  # integrity checks assume a schema-valid shape

    church_ids = _unique(errors, "church", [c["id"] for c in lib["churches"]])
    speaker_ids = _unique(errors, "speaker", [s["id"] for s in lib["speakers"]])
    _unique(errors, "series", [s["id"] for s in lib["series"]])
    _unique(errors, "sermon", [m["id"] for s in lib["series"] for m in s["sermons"]])

    for se in lib["series"]:
        if se["churchId"] not in church_ids:
            errors.append(f"series {se['id']}: unknown churchId {se['churchId']}")
        for sid in se["speakerIds"]:
            if sid not in speaker_ids:
                errors.append(f"series {se['id']}: unknown speakerId {sid}")
        dates = [m["date"] for m in se["sermons"]]
        if dates != sorted(dates):
            errors.append(f"series {se['id']}: sermons not in preached order")
        ds = [date.fromisoformat(d) for d in dates]
        if (ds[-1] - ds[0]).days > MAX_SPAN_DAYS:
            errors.append(f"series {se['id']}: spans more than 3 years")
        if any((b - a).days > MAX_GAP_DAYS for a, b in zip(ds, ds[1:])):
            errors.append(f"series {se['id']}: gap of more than a year between sermons")
        if (se["startDate"], se["endDate"]) != (dates[0], dates[-1]):
            errors.append(f"series {se['id']}: startDate/endDate don't match its sermons")
        in_book = sum(1 for m in se["sermons"] if m.get("passage", {}).get("book") == se["book"])
        if in_book < MIN_BOOK_SHARE * len(se["sermons"]):
            errors.append(
                f"series {se['id']}: only {in_book}/{len(se['sermons'])} sermons in {se['book']} "
                f"(min {MIN_BOOK_SHARE:.0%})"
            )
        for m in se["sermons"]:
            if m["speakerId"] not in speaker_ids:
                errors.append(f"sermon {m['id']}: unknown speakerId {m['speakerId']}")
            p = m.get("passage")
            if p is not None:
                ref = parse_reference(p["display"])
                if ref is None or ref.book != p["book"]:
                    errors.append(f"sermon {m['id']}: passage {p['display']!r} is not in book {p['book']}")
            if m["speakerId"] not in se["speakerIds"]:
                errors.append(f"sermon {m['id']}: speaker {m['speakerId']} missing from series speakerIds")
    return errors


def _unique(errors: list[str], kind: str, ids: list[str]) -> set[str]:
    seen: set[str] = set()
    for i in ids:
        if i in seen:
            errors.append(f"duplicate {kind} id: {i}")
        seen.add(i)
    return seen
