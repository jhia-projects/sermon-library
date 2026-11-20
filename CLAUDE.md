# Sermon Library

## Goal
A mobile app (iOS + Android) for listening to **complete sermon series that work through one book of the Bible**, from a curated set of churches/speakers. Starting with **one church**: All Souls Langham Place (`pipeline/sources/all-souls-langham-place.toml`). Adding more should be a routine task (`/add-church`).

## The core feature: deriving book series
**Deciding which sermons form a series through one book is what this app is for.** Churches don't publish "book series" as data: we infer them from series labels, printed references and dates, and every error is visible to listeners (a missing sermon, a series split in two, a topical series posing as a book study). So:
- Treat changes to `pipeline/src/sermon_pipeline/build.py` grouping, `validate.py` series checks and the `[series]` config as high-risk. Each rule change needs a test that pins the case that motivated it, and a before/after count of published and skipped series from a live build.
- Every skipped series has a logged reason, every kept off-book sermon is logged (`~` lines), and both should be read after a build.
- Precision beats recall: leaving out a real series is better than publishing a wrong one.
- Validation is layered: deterministic rules (now) → LLM review of candidates (designed, not built) → human approval for anything the rules didn't decide. See `docs/series-derivation.md`.

## Architecture
```
church RSS feeds (primary)
 + site scraping (backfill only) ──► pipeline/ (Python, weekly) ──► library.json ──► app/ (Expo, TypeScript)
                                         validated against schema/library.schema.json
```
- `schema/library.schema.json` — **the contract**. The pipeline writes it, the app reads it. Nothing else crosses the boundary.
- `schema/books.json` — the 66 books (OSIS code, name, testament, canonical order), shared by the schema enum, the pipeline and the app.
- `schema/library.example.json` — hand-written sample that must always validate. Use it for app development and tests.
- `pipeline/` — scrapers/feed readers per church → normalised `library.json`. See `pipeline/CLAUDE.md`.
- `app/` — Expo (React Native + TypeScript) app that fetches `library.json`. See `app/CLAUDE.md`.
- `.claude/skills/` — `/add-church` (new source end-to-end), `/release` (app release).
- `.github/workflows/` — `pipeline.yml` (weekly cron: build, validate, publish `library.json`), `app.yml` (lint/typecheck/test, EAS build).

## Rules
1. **Schema first.** Any change to the data shape starts in `schema/library.schema.json`, then update `library.example.json`, then pipeline, then app — in the same PR.
2. **Versioning.** `schemaVersion` is semver, currently `1.0.0` (unpublished: until the first release, breaking changes stay at 1.0.0). After release: adding optional fields = minor; removing, renaming or making a field required = major, and the app must handle both versions until the old one is out of circulation.
3. **IDs are permanent.** `id` fields are kebab-case slugs that never change once published, because the app stores them for favourites and playback progress. Series: `<church>-<book>-<startYear>-<slug(series name)>`. Sermons: `<church>-<source media id>`. Never derive an ID from a sermon's position in its series, because backfill can insert earlier sermons.
4. **One book per series** (full algorithm: `docs/series-derivation.md`). A series is a run of sermons under one series label that works through a single book (`book` = OSIS code from `schema/books.json`). At least **80%** (`min_book_share`, 0.8–1.0, floor enforced by `validate.py`) of its sermons must have a printed reference in that book. A sermon listing several references counts if **any** is in the book. The other ≤20% (an OT interlude, a reference missing from the feed) **stay in place** with their own `passage.book`, or no `passage`, so one odd sermon neither drops nor splits a series. Sermons belong to one run while each follows the previous within **1 year**; the whole series must fit in **3 years**. Each sermon belongs to at most one series. Topical and seasonal series (World Mission Sunday, Christmas/carols/Advent) are out of scope. Near-duplicate speaker and series names are flagged by `review-names` and resolved by an alias or `pipeline/review.toml`.
5. **Never fabricate data.** Every title, date, passage and URL comes from the source. If a field can't be found, omit it (only required fields are mandatory). Only take a passage from a title when the source itself prints a scripture reference there, e.g. `Title (Acts 12:1–19)`. Never infer one from a title's wording.
6. **RSS first, scraping is backfill only.** Enforced in `pipeline/src/sermon_pipeline/policy.py` and pinned by `pipeline/tests/test_policy.py`. Every church needs a feed, or a written reason it has none. A failing feed fails the build, with no fallback to scraping. Scraped data can add sermons the feed lacks or fill empty fields, never override feed values. Each church's scraped history is kept in a committed archive (`pipeline/data/<church>/`, see `snapshot.py`), so a build doesn't re-crawl the site; it is scraped data too, so the feed still wins.
7. **Link, don't rehost.** Media URLs point at the church's own hosting/YouTube. Always keep `sourceUrl` for attribution. Respect robots.txt and site terms; get permission before adding a church.
8. **Validate before publishing.** The pipeline must fail (not publish) if output doesn't validate against the schema or if referential integrity breaks (`churchId`, `speakerId`, `speakerIds` must resolve).
9. **HTTPS only** for all URLs.
10. Sermons are ordered as preached; `isComplete: false` marks a series still in progress.

## Commands
```bash
cd pipeline && uv sync && uv run pytest -q          # offline tests
uv run sermon-pipeline check-sources                # RSS-first config policy
uv run sermon-pipeline build --out out/library.json # live build (validated before write)
uv run sermon-pipeline build --update-snapshot --out out/library.json # + add new scraped sermons to pipeline/data/
uv run sermon-pipeline review-names out/library.json # flag near-duplicate names
```
```bash
cd app && npm install && npx expo install --fix
npm start                                          # Expo dev server
npm run typecheck && npm run lint && npm test
```
