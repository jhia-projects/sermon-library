# pipeline/

Python (3.12+, managed with `uv`). Builds `library.json` (contract: `../schema/library.schema.json`) from per-church sources.

## Commands
```bash
uv sync                                        # install
uv run pytest -q                               # tests (offline, fixtures only)
uv run sermon-pipeline check-sources           # enforce RSS-first config policy on sources/*.toml
uv run sermon-pipeline build --out out/library.json            # live: RSS + scrape backfill
uv run sermon-pipeline build --no-scrape --out out/library.json # live: RSS only
uv run sermon-pipeline build --archive-pages 5 --out out/library.json # + 5 archive pages (~10s each)
uv run sermon-pipeline validate out/library.json
uv run sermon-pipeline review-names out/library.json            # near-duplicate names
uv run sermon-pipeline crawl-sthelens --limit 5                 # St Helen's: sitemaps + 5 new talk pages (cached), rewrites the snapshot
uv run sermon-pipeline crawl-sthelens --newest --limit 300      # walk from the latest talk id instead
uv run sermon-pipeline crawl-sthelens --id 59581 --id 59476     # specific talk ids
```
macOS note: if `ModuleNotFoundError: sermon_pipeline` appears, the venv's editable `.pth` was given the hidden flag (Python 3.14 skips hidden .pth files): `chflags nohidden .venv/lib/python*/site-packages/*.pth`.

## RSS first — enforced, not advisory (`src/sermon_pipeline/policy.py`)
1. **Config**: every `sources/*.toml` needs `[rss].url` (or `[rss].urls` for several feeds, each required), or `[rss].unavailable_reason` saying what was checked. A scraper alone is rejected.
2. **No silent fallback**: if the feed errors or is empty the church's build fails. Never catch that and scrape instead.
3. **Feed discovery**: every page a scraper fetches goes through `Scraper.fetch_page`, which fails a scrape-only church if the page advertises a feed.
4. **Merge** (`merge_prefer_rss`): matched on `source_key` (the church's own media id). Scraping may only *backfill* sermons absent from the feed, or *enrich* fields the feed left empty. Conflicting scraped values are discarded and counted (`ignored_scrape_conflicts` in the log).
5. **Assertion** (`assert_rss_precedence`): runs on every build; fails if any feed value was lost or overwritten.

`tests/test_policy.py` pins all of this. If a policy test fails, fix the code, not the test.

## Layout
```
sources/<church-id>.toml      church config: feed, scraper, series rules, aliases
src/sermon_pipeline/
  models.py      RawSermon: source-agnostic record + per-field provenance
  rss.py         podcast RSS reader (origin="rss"); per-church item parser via `[rss].format` (FEED_FORMATS)
  scrapers/      backfill scrapers (origin="scrape"); register in scrapers/__init__.py
  policy.py      the rules above
  scripture.py   "1 Thessalonians 4:15 – 5:11" -> OSIS book + passage
  normalize.py   title/series-label/duration helpers
  build.py       collect -> group into book series -> library dict
  validate.py    schema + referential integrity (gate before writing)
  http.py        PoliteFetcher: robots.txt, Crawl-delay (min 2s, optional jitter), https only
  crawl.py       CachedCrawler: disk cache so no URL is fetched twice; re-run to resume
tests/fixtures/<church-id>/   saved feed + pages; tests never hit the network
```

## Series rules (build.py; re-checked in validate.py)
This is the app's core feature; read `../docs/series-derivation.md` before changing it.
- Grouped by series label after aliasing and case/punctuation folding. A label counts if it is explicit (`Series: X` or `X: subtitle`); a bare description only counts if it matches an explicit name.
- **Runs (1-year look-forward):** sermons sorted by date; one continues the run if the previous one is ≤365 days earlier. Otherwise a new series starts, so "Romans" 1985 and "Romans" 2012 stay separate.
- **3-year cap:** a run whose first and last sermons are more than 3 years apart is skipped and reported, not trimmed.
- **One book:** at least `min_book_share` (default and All Souls: 0.8; allowed 0.8–1.0) of sermons must have a reference in the most common book. A sermon counts if **any** of its references is in the book: the feed title's one (`passage_text`) or any the site lists (`listed_references`, e.g. `Psalm 22:1-21; Mark 15:16-32`). The published passage is the first in-book reference. The other sermons **stay in the series** in date order: an interlude gets its own `passage.book`, a sermon with no reference gets no `passage`. They're logged as `~ <series>: kept N sermon(s) outside its book`. With 2–4 sermons, 80% still means all of them.
- **Repeated services (opt-in, `one_per_service_half`):** a series keeps one copy per date per morning (<12pm) / evening (≥12pm) service: the earliest, then lowest id. Uses `service_time` (feed `(6pm)` or talk-page date line); without one, nothing is dropped. Also strips a trailing `(4pm)`/`(10am)` from series labels so per-service labels merge. Logged as `= <series>: dropped N repeated-service copies`.
- **Exclusions:** `exclude` (exact names) and `exclude_patterns` (case-insensitive substrings of the series name).
- Needs ≥2 sermons, unless it is explicitly labelled and in progress (last sermon ≤28 days ago).
- IDs: series `<church>-<book>-<startYear>-<slug(name)>` (a collision appends the start month); sermon `<church>-<source_key>`.
- Sermons without playable media, a title or a speaker are dropped and counted. Nothing is invented to fill a gap.
- Speakers are global (no `churchId`) and de-duplicated by id across churches.

## Name review (names.py)
`review-names` (and a warning during `build`) flags speaker pairs, and series pairs within the same book, that match the same name after removing titles (Revd/Dr/Canon…), are within edit distance 2 (names ≥6 chars), share first and last names, or have similarity ≥0.88. Resolve each pair either way: same → `[aliases.speaker]` / `[aliases.series]` in the source toml; different → `[[speaker.distinct]]` in `review.toml`.

## Adding a church
Use `/add-church`. In short: find the feed first (site `<link rel=alternate>`, podcast directories, `/rss`, `/feed`). Save fixtures. Write `sources/<id>.toml`. Add a scraper only if the feed lacks something needed, and only as a backfill. Add tests. Run `check-sources`, `pytest` and a live `build`.

## All Souls notes
- Feed: `https://www.allsouls.org/Media/rss.xml`, about 12 months / ~100 items. guid `m_<media_id>`.
- The scraper reads `/Media/AllMedia.aspx` page 1, the series pages it links to (`/Groups/<id>/<Name>.aspx`) and any listed in `series_pages`.
- Archive: ~646 listing pages back to the 1970s, paged by ASP.NET postback (POST the page's own form with `hidden_page=N`). Crawled only with `--archive-pages N`; at Crawl-delay 10s a full crawl takes about 2 hours. Not yet run in full: only page 600 (Nov 1977) was tested, and it's the `archive_page_600.html` fixture.
- The feed prints one reference per sermon (in the title); the listing's `References:` line can print several, and that's often where the in-book one is (e.g. a Psalm 22 sermon in a Mark series lists Mark 15:16-32). Series with OT "interludes" therefore usually need the listing rows, from page 1 or `--archive-pages`, to pass the 100% rule.
- Archive rows differ from recent ones: `Reference:` (singular); file title `MP3 Audio` with format `64Kbps 13.4MB`; duration only as `Length: 29 minutes` (not parsed); group links carry a catalogue code (`ZA008 Genesis`); quoted titles (`'Did God say?'`).
- robots.txt: `Crawl-delay: 10`. `/Media/` and `/Groups/` are allowed.
- Known data quirks: `.mp3` in titles, `No Favorites`/`No Favourites`, `Ollie Lansdown` → aliased to `Ollie Lansdowne` (confirmed).

## St Helen's Bishopsgate notes (build source; permission pending)
- `sources/st-helens-bishopsgate.toml`: **Sunday feed only** (`format = "sthelens"`) + scraper `sthelens` with `sunday_only = true`. Permission from the church is pending.
- Data = feed (latest 20) + a one-off crawl. `crawl-sthelens` caches talk pages in `out/st-helens-bishopsgate/cache/` (2–3s per request, resumable, `--limit` counts new pages, `--newest` walks from the latest id) and rewrites the committed snapshot `data/st-helens-bishopsgate/talks.jsonl` from every cached page. Each build reads the snapshot and fetches only the talk pages of feed talks missing from it, which is where their series label is printed. The merge keeps feed values; pages add series, page URL, series URL. Pipeline-wide UA is `sermonorganiser/0.1`.
- Build history (2026-11-19): RSS only: 0 series (all `no series`). Feed + 7-talk snapshot: 4 series / 20 sermons. Feed + 307-talk snapshot (Feb–Nov 2026): 16 series / 149 sermons without `one_per_service_half`, **15 / 81 with it** (78 copies dropped; "A defining moment" became a single sermon and is skipped). 1,307-talk snapshot (2023-07 on): 50 series / 382 sermons, 29 skipped. 2,307 talks (2021-01 on): 103 series / 698 sermons before stripping `(4pm)`-style label suffixes (17 overlapping same-book series pairs), 92 / 633 after + typo alias (6 pairs left: per-service series with different names, e.g. "Parables of the kingdom" 4pm / "The secrets of heaven" 6pm, both Matthew 13: not merged without a decision).
- Weekend-away sessions ("…: 4pm weekend", "Haggai - 10:30am weekend away") publish as 2-sermon Sunday-only fragments (Saturday sessions are filtered out). Pending decision: exclude `weekend`.
- Evening "copies" are often distinct talks: 4pm and 6pm run the same series with different speakers, and in 20 of 78 slots the title or passage differs (e.g. 2026-02-22: 1 Kings 21 at 4pm, 1 Kings 22 at 6pm). The rule keeps the earliest service consistently, so a series follows one congregation (9.30am, 4pm). Splitting by service into separate series is the alternative if the 6pm talks are wanted.
- **Repeated services:** the same series runs at several services (John at 9.30am + 11.15am, Luke at 4pm + 6pm, sometimes different speakers). `one_per_service_half = true` keeps the earliest morning and earliest evening copy per date. The feed prints `9am`/`11:15am`; pages print `9.30am`; feed wins on conflict.
- Feeds `https://api.st-helens.org.uk/v1.0/feeds/{sunday,midweek}.xml` (iTunes 282642731 / 285695591): last 20 items each, passage only in `itunes:subtitle` (`Psalm 110:1-3 - George Diwakar (6pm)`), **no series**. Read with `format = "sthelens"` (`rss._sthelens_item`); the generic reader mis-reads them (URL as source_key, description as series_name, no passage).
- The number in a feed enclosure (`podcast-download/59581/SA26-047.mp3`) is the talk page id (`/resources/talk/59581/`): use it as `source_key` for both.
- `/sitemap/talks` (11,207 talks, from 1971, ordered by id) and `/sitemap/series` (1,930). Talk pages print date+service time, passage (`<h2>`, empty on old talks), title (`<h3>`), speaker, `Series:` link, audio. No JSON-LD.
- robots.txt disallows `/resources/all/*` (speaker links on every talk page point there) and `/_util/login/*`; `NEVER_FETCH_PREFIXES` blocks them even if robots parsing fails. No Crawl-delay.
- Audio: store the `api.st-helens.org.uk/.../instant-download/<id>/<file>.mp3` URL. It 302s to a signed, expiring S3 URL that must never be stored.
- The Sunday feed mixes 4 services at once (e.g. John at 9am/11:15am, Luke at 4pm/6pm), and series names are often thematic ("Saving the world" = Genesis).
