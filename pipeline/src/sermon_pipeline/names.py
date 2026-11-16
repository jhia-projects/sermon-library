"""Systematic review of near-duplicate names (speakers, series): 'Ollie Lansdown' vs 'Ollie Lansdowne'.

Flags pairs a human should look at; it never merges anything itself. Each flagged pair is resolved
by either an alias in sources/<church>.toml (same person/series) or an entry in review.toml
(reviewed: genuinely different). `sermon-pipeline review-names` exits non-zero while any pair is
unresolved; `build` logs them as warnings.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path

from .normalize import series_key

REVIEW_PATH = Path(__file__).resolve().parents[2] / "review.toml"

_HONORIFICS = {"rev", "revd", "reverend", "dr", "canon", "bishop", "rt", "the", "prof", "mr", "mrs", "ms", "miss"}
MAX_EDIT_DISTANCE = 2
MIN_LEN_FOR_EDIT = 6  # short names ("Tim"/"Tom") differ by 1 edit and are not suspicious
MIN_RATIO = 0.88


@dataclass(frozen=True)
class NamePair:
    kind: str  # "speaker" | "series"
    a: str
    b: str
    reason: str

    def key(self) -> tuple[str, frozenset[str]]:
        return self.kind, frozenset((self.a, self.b))


def core(name: str) -> str:
    """Folded name without honorifics: 'Revd Dr John Stott' -> 'john stott'."""
    return " ".join(t for t in series_key(name).split() if t not in _HONORIFICS)


def levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def why_similar(a: str, b: str) -> str | None:
    ca, cb = core(a), core(b)
    if not ca or not cb:
        return None
    if ca == cb:
        return "same after removing case/punctuation/titles"
    d = levenshtein(ca, cb)
    if d <= MAX_EDIT_DISTANCE and min(len(ca), len(cb)) >= MIN_LEN_FOR_EDIT:
        return f"edit distance {d}"
    ta, tb = ca.split(), cb.split()
    # 'John Stott' vs 'John R W Stott': first and last names agree, one has extra middle tokens.
    if len(ta) >= 2 and len(tb) >= 2 and ta[0] == tb[0] and ta[-1] == tb[-1]:
        return "same first and last name"
    r = SequenceMatcher(None, ca, cb).ratio()
    if r >= MIN_RATIO:
        return f"similarity {r:.2f}"
    return None


def find_similar(kind: str, names: list[str]) -> list[NamePair]:
    uniq = sorted(set(names))
    out = []
    for a, b in combinations(uniq, 2):
        if reason := why_similar(a, b):
            out.append(NamePair(kind, a, b, reason))
    return out


def load_reviewed(path: Path = REVIEW_PATH) -> set[tuple[str, frozenset[str]]]:
    if not path.exists():
        return set()
    with path.open("rb") as f:
        data = tomllib.load(f)
    done = set()
    for kind in ("speaker", "series"):
        for entry in data.get(kind, {}).get("distinct", []):
            done.add((kind, frozenset(entry["names"])))
    return done


def review_library(lib: dict, reviewed: set[tuple[str, frozenset[str]]] | None = None) -> list[NamePair]:
    """Unresolved near-duplicate pairs in a built library."""
    reviewed = load_reviewed() if reviewed is None else reviewed
    pairs = find_similar("speaker", [s["name"] for s in lib["speakers"]])
    # Series names only clash within a book: 'Romans' vs 'Romans!' matters, 'Jonah' vs 'John' doesn't.
    by_book: dict[str, list[str]] = {}
    for se in lib["series"]:
        by_book.setdefault(se["book"], []).append(se["title"])
    for titles in by_book.values():
        pairs += find_similar("series", titles)
    return [p for p in pairs if p.key() not in reviewed]
