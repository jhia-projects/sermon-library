"""A church's sermon archive: every sermon its scraper has seen, committed as JSON lines.

The archive is scraped data (origin "scrape"), so it is backfill only: the build merges it after
the feed with `policy.merge_prefer_rss`, and feed values win. It lets a build cover the church's
whole history without re-crawling the site: a one-off crawl seeds it, and each
`build --update-snapshot` adds the sermons that build's scrape saw (the newest listing page and
the series pages it links to).

Format: one JSON object per sermon (keys sorted; only fields with a value), in the order the scrape
saw them: the site's listing order, newest first, with sermons found only on series pages last. Order
matters: a series' display name is its most common spelling, and a tie goes to the first sermon read,
so the archive keeps the order a full crawl would read. New sermons land at the top.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .models import DATA_FIELDS, RawSermon, _has_value
from .policy import merge_prefer_rss


def to_row(s: RawSermon) -> dict[str, object]:
    row: dict[str, object] = {"source_key": s.source_key}
    for name in DATA_FIELDS:
        v = getattr(s, name)
        if _has_value(v):
            row[name] = v.isoformat() if isinstance(v, date) else v
    return row


def from_row(row: dict) -> RawSermon:
    r = dict(row)
    if "date" in r:
        r["date"] = date.fromisoformat(r["date"])
    return RawSermon(origin="scrape", **r)


def read_snapshot(path: Path) -> list[RawSermon]:
    if not path.exists():
        return []
    return [from_row(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_snapshot(path: Path, scraped: list[RawSermon]) -> int:
    """Write scraped records, one per source_key (the same first-wins, fill-gaps merge the build uses
    for scraped pages). Returns the number written."""
    merged, _ = merge_prefer_rss([], scraped)
    rows = [to_row(s) for s in merged]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows), encoding="utf-8"
    )
    tmp.replace(path)
    return len(rows)
