"""sermon-pipeline {check-sources,build,validate,review-names,crawl-sthelens}."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from .build import build_church, build_library, collect
from .config import SOURCES_DIR, load_all_sources, load_source
from .http import PoliteFetcher
from .names import REVIEW_PATH, review_library
from .policy import PolicyError
from .validate import validate_library


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sermon-pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check-sources", help="load every sources/*.toml and enforce the RSS-first config policy")

    b = sub.add_parser("build", help="fetch, merge (RSS wins), group and write library.json")
    b.add_argument("--out", type=Path, default=Path("out/library.json"))
    b.add_argument("--source", type=Path, action="append", help="limit to these source files")
    b.add_argument("--no-scrape", action="store_true", help="RSS only (fast; no backfill)")
    b.add_argument(
        "--archive-pages", type=int, default=0, metavar="N",
        help="also crawl N archive listing pages beyond the first (backfill; ~10s per page)",
    )

    v = sub.add_parser("validate", help="validate a library.json against schema + integrity rules")
    v.add_argument("path", type=Path)

    r = sub.add_parser("review-names", help="flag near-duplicate speaker/series names for human review")
    r.add_argument("path", type=Path)

    c = sub.add_parser(
        "crawl-sthelens",
        help="St Helen's Bishopsgate: fetch sitemaps + talk pages (cached, resumable, 2-3s/request)",
    )
    c.add_argument("--out", type=Path, default=Path("out/st-helens-bishopsgate"))
    c.add_argument("--limit", type=int, default=5, help="new (uncached) talk pages to fetch (default 5)")
    c.add_argument("--newest", action="store_true", help="walk the sitemap newest id first (default oldest)")
    c.add_argument("--id", dest="ids", action="append", metavar="TALK_ID", help="fetch these talk ids instead")

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        if args.cmd == "check-sources":
            sources = load_all_sources()
            for s in sources:
                mode = "rss" + ("+scrape-backfill" if s.scraper else "") if s.rss_url else "scrape-only (justified)"
                print(f"ok  {s.church_id}: {mode}")
            print(f"{len(sources)} source(s) in {SOURCES_DIR}")
            return 0

        if args.cmd == "validate":
            problems = validate_library(json.loads(args.path.read_text(encoding="utf-8")))
            for prob in problems:
                print(prob, file=sys.stderr)
            print("valid" if not problems else f"{len(problems)} problem(s)")
            return 1 if problems else 0

        if args.cmd == "review-names":
            pairs = review_library(json.loads(args.path.read_text(encoding="utf-8")))
            for pair in pairs:
                print(f"{pair.kind}: {pair.a!r} ~ {pair.b!r} ({pair.reason})")
            if pairs:
                print(f"{len(pairs)} pair(s) to review: alias them in sources/<church>.toml "
                      f"if they are the same, or list them in {REVIEW_PATH.name} if not")
                return 1
            print("no unreviewed near-duplicate names")
            return 0

        if args.cmd == "crawl-sthelens":
            from .scrapers.sthelens import crawl

            summary = crawl(args.out, limit=args.limit, ids=args.ids, newest_first=args.newest)
            print(json.dumps(summary, ensure_ascii=False, indent=1))
            return 0

        # build
        sources = [load_source(s) for s in args.source] if args.source else load_all_sources()
        fetcher = PoliteFetcher()
        now = datetime.now(timezone.utc)
        churches = []
        for cfg in sources:
            sermons, _ = collect(cfg, fetcher, scrape=not args.no_scrape, archive_pages=args.archive_pages)
            church, report = build_church(cfg, sermons, now.date())
            for line in report.published_series:
                logging.info("  + %s", line)
            for name, why in sorted(report.skipped_series.items()):
                logging.info("  - %s: %s", name, why)
            for name, n in sorted(report.kept_off_book.items()):
                logging.info("  ~ %s: kept %d sermon(s) outside its book", name, n)
            if report.dropped_sermons:
                logging.info("  dropped sermons: %s", dict(report.dropped_sermons))
            churches.append(church)
        lib = build_library(churches, now)
        problems = validate_library(lib)
        if problems:
            for prob in problems:
                print(prob, file=sys.stderr)
            print("library failed validation; not written", file=sys.stderr)
            return 1
        for pair in review_library(lib):
            logging.warning("review name: %s %r ~ %r (%s)", pair.kind, pair.a, pair.b, pair.reason)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.out}: {len(lib['series'])} series, "
              f"{sum(len(s['sermons']) for s in lib['series'])} sermons")
        return 0
    except PolicyError as e:
        print(f"POLICY: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
