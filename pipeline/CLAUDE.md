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
```
macOS note: if `ModuleNotFoundError: sermon_pipeline` appears, the venv's editable `.pth` was given the hidden flag (Python 3.14 skips hidden .pth files): `chflags nohidden .venv/lib/python*/site-packages/*.pth`.

## RSS first — enforced, not advisory (`src/sermon_pipeline/policy.py`)
1. **Config**: every `sources/*.toml` needs `[rss].url`, or `[rss].unavailable_reason` saying what was checked. A scraper alone is rejected.
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
  rss.py         generic podcast RSS reader (origin="rss")
  scrapers/      backfill scrapers (origin="scrape"); register in scrapers/__init__.py
  policy.py      the rules above
  scripture.py   "1 Thessalonians 4:15 – 5:11" -> OSIS book + passage
  normalize.py   title/series-label/duration helpers
  build.py       collect -> group into book series -> library dict
  validate.py    schema + referential integrity (gate before writing)
  http.py        PoliteFetcher: robots.txt, Crawl-delay (min 2s), https only
tests/fixtures/<church-id>/   saved feed + pages; tests never hit the network
```

## Series rules (build.py; re-checked in validate.py)
This is the app's core feature; read `../docs/series-derivation.md` before changing it.
- Grouped by series label after aliasing and case/punctuation folding. A label counts if it is explicit (`Series: X` or `X: subtitle`); a bare description only counts if it matches an explicit name.
- **Runs (1-year look-forward):** sermons sorted by date; one continues the run if the previous one is ≤365 days earlier. Otherwise a new series starts, so "Romans" 1985 and "Romans" 2012 stay separate.
- **3-year cap:** a run whose first and last sermons are more than 3 years apart is skipped and reported, not trimmed.
- **One book:** at least `min_book_share` (default and All Souls: 0.8; allowed 0.8–1.0) of sermons must have a reference in the most common book. A sermon counts if **any** of its references is in the book: the feed title's one (`passage_text`) or any the site lists (`listed_references`, e.g. `Psalm 22:1-21; Mark 15:16-32`). The published passage is the first in-book reference. The other sermons **stay in the series** in date order: an interlude gets its own `passage.book`, a sermon with no reference gets no `passage`. They're logged as `~ <series>: kept N sermon(s) outside its book`. With 2–4 sermons, 80% still means all of them.
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
