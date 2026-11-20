# Sermon Library

A mobile app (iOS and Android) for listening to **complete sermon series that work through one book of the Bible**, from a curated set of churches.

Churches don't publish "a series through Romans" as data. The pipeline works it out from series labels, printed Bible references and dates, and publishes only the series it's confident about. The first church is [All Souls Langham Place](https://www.allsouls.org).

## How it fits together

```
church RSS feeds (primary)
 + site scraping (backfill only) ──► pipeline/ (Python) ──► library.json ──► app/ (Expo, TypeScript)
                                         validated against schema/library.schema.json
```

| Path | What it is |
| --- | --- |
| `schema/` | **The contract.** `library.schema.json` (the shape of `library.json`), `books.json` (the 66 books), and `library.example.json` (a sample that always validates). |
| `pipeline/` | Reads each church's feed (and scrapes its site only to backfill), groups sermons into book series, validates, and writes `library.json`. See [`pipeline/CLAUDE.md`](pipeline/CLAUDE.md). |
| `app/` | Expo (React Native) app: browse by book, speaker or church, and play a series in preached order. See [`app/CLAUDE.md`](app/CLAUDE.md). |
| `docs/` | [How series are derived](docs/series-derivation.md), and [ideas for scaling to more churches](docs/scaling-sources.md). |

## App features

- Browse series by **book**, **speaker** or **church**.
- Play a series in preached order. Each sermon follows the one before automatically, skipping any without audio.
- Mini player and full-screen player: scrubber, back 15 s and forward 30 s, previous/next sermon, and playback speed.
- Progress is saved per sermon on the device. "Continue" picks up at the first unfinished sermon.
- Lock-screen controls and background audio (development or production build only; see below).
- Audio streams from the church's own hosting, with a link back to its page for each sermon.

## Getting started

### Pipeline (Python 3.12+, [uv](https://docs.astral.sh/uv/))

```bash
cd pipeline
uv sync
uv run pytest -q                                      # offline tests
uv run sermon-pipeline check-sources                  # RSS-first config policy
uv run sermon-pipeline build --out out/library.json   # live build, validated before write
uv run sermon-pipeline review-names out/library.json  # flag near-duplicate names
```

`library.json` files are build output and are gitignored.

### App (Node: see `app/.nvmrc`)

```bash
cd app
npm install --legacy-peer-deps
npm start                    # Expo dev server; press i for the iOS simulator, a for Android
npm run typecheck && npm run lint && npm test
```

The app shows `schema/library.example.json` by default. To use a real pipeline build:

```bash
npm run library              # serves ../pipeline/out/library.json on port 8787
echo 'EXPO_PUBLIC_LIBRARY_URL=http://localhost:8787/library.json' > .env.local
npm start -- --clear         # the URL is baked in at bundle time, so restart Expo
```

On a physical phone, use the LAN address that `npm run library` prints. See `app/.env.example`.

Expo Go plays audio only while the app is open. For background audio and lock-screen controls, build the app once with `npx expo run:ios` (or `run:android`).

## Principles

- **Precision over recall.** Leaving out a real series is better than publishing a wrong one. Every skipped series is logged with a reason.
- **Never fabricate data.** Every title, date, passage and URL comes from the church's own source.
- **RSS first.** Scraping can only add sermons the feed lacks or fill empty fields, never override the feed.
- **Link, don't rehost.** Media plays from the church's own hosting, with attribution.
- **Schema first.** Any change to the data shape starts in `schema/library.schema.json`.
- **IDs are permanent.** Favourites and progress are keyed on them.

The full rules are in [`CLAUDE.md`](CLAUDE.md).

## Adding a church

Get the church's permission first. Then run the `/add-church` skill in Claude Code (`.claude/skills/add-church`), which sets up the source config, fixtures and tests.
