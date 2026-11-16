# Scaling to more churches: revisit after the MVP

All Souls works because it has an RSS feed plus one server-rendered site (Hubb CMS) with a hand-written backfill scraper. That doesn't scale to dozens of churches by hand. This file lists what to revisit **once the MVP app has shipped**. Each item says why it matters and what to check.

## Getting the data

1. **Platform adapters before per-church scrapers.** Most churches host sermons on a handful of platforms. Write one adapter per platform; a church's toml then just names the platform and its ids. Platforms to check:
   - SermonAudio (public API);
   - Subsplash;
   - WordPress Sermon Manager (`/wp-json/wp/v2/wpfc_sermon`);
   - Planning Center Publishing;
   - ChurchSuite;
   - Faithlife Sermons;
   - Squarespace podcast blocks;
   - Hubb (All Souls);
   - podcast hosts (Buzzsprout, Spotify for Podcasters, Captivate).
2. **Feed discovery at scale.** The Apple iTunes Search API and the Podcast Index API find a church's podcast feed by name. Use them in `/add-church` before looking at the site at all.
3. **YouTube as a source.** Some churches only publish to YouTube, and their playlists often map one-to-one to series.
   - Needs the YouTube Data API: a key and quota.
   - Check whether descriptions reliably print references.
   - Decide if YouTube-only churches count as having a "feed" under the RSS-first rule (YouTube does expose a channel RSS feed, but it is limited to 15 items).
4. **Playwright for JavaScript-rendered sites.** Use it where the archive only exists after the browser runs JavaScript, so a plain HTTP fetch sees nothing. Two separate uses:
   - **Playwright MCP, while *adding* a church:** Claude explores the site interactively in `/add-church`. It finds the feed, the archive pagination, the series pages and the request the page makes behind the scenes (often a JSON API that is easier than scraping). It also saves fixtures. This is a one-off and has no place in the weekly build.
   - **The Playwright Python library, in the *weekly pipeline*:** only for sites with no other route. It is heavier, slower and flakier than HTTP. Keep it behind the same `Scraper.fetch_page` gate so the feed-discovery check still applies, and prefer the JSON API it reveals.
5. **Declarative scrapers.** For simple listing pages, put CSS selectors in the toml instead of Python, so adding a church needs no code review of parsing logic. Fall back to code for anything with pagination postbacks like Hubb.
6. **LLM-assisted extraction (constrained).** Some sources only print the series and passage in free text ("Week 3 of our series in Mark, looking at chapter 4"). An LLM could extract them, but only as a proposal. Code checks the extracted reference appears verbatim in the source text (CLAUDE.md rule 5: never fabricate). This fits with the LLM series review in `series-derivation.md`.

## Running it at scale

7. **One church failing shouldn't sink the build.** Today a failing feed fails the whole build. Reconsider this with many churches: fail that church, keep its last good data, and alert. Keep "never fall back to scraping" either way.
8. **A persistent store of raw sermons.** Store raw sermons, and when each was crawled, in SQLite or similar, so the archive is crawled once and weekly runs are incremental. Use conditional requests (`ETag` / `If-Modified-Since`). This is a prerequisite for crawling the full All Souls archive (about 2 hours at Crawl-delay 10).
9. **Per-domain parallelism.** Crawl different churches in parallel while each domain keeps its own crawl delay. Watch GitHub Actions limits: 6 hours per job. Run one job per church, or use a matrix.
10. **Detecting scraper drift.** Sites change their HTML without notice. Track the parse rate per church (rows found, rows with a passage, rows with media) and alert when it drops. Refresh fixtures from live pages on a schedule.
11. **Link checking.** Media URLs rot. Run a periodic cheap HEAD check on audio and video URLs, and report broken ones per church.

## Data quality across churches

12. **Series label conventions differ.** "Series: X", "X: subtitle", tags, categories and playlists all occur. Make label parsing a per-source option, not one global heuristic.
13. **More robust scripture parsing.** Handle:
    - abbreviations (Jn, 1 Cor, Ps, Matt);
    - "vv." and "ff.";
    - several chapters ("Mark 4 & 5");
    - Bible version suffixes (ESV);
    - non-English book names, if non-UK/US churches are ever added.
    Grow the test table in `test_parsing.py` from real examples.
14. **Speaker identity across churches.** The same preacher appears under different spellings, and different people share a name. `review-names` already flags near-duplicates; later, decide if speakers need a disambiguator (for example, the church they're based at).
15. **Size of `library.json`.** One file for every church eventually gets large for a phone. Options: split by church or book, publish an index plus shards, and serve with ETags from a CDN. This needs a schema change, so it goes through Rule 1 (schema first).

## Process

16. **Permission and terms.** Get written permission from each church before adding it. Respect robots.txt and Crawl-delay. Record the permission in the church's toml.
17. **A fully worked `/add-church`.** Turn the steps into the skill:
    - discover (directories, Playwright MCP);
    - pick the platform adapter;
    - write the toml;
    - save fixtures;
    - generate tests;
    - run `check-sources`, `pytest` and a live build;
    - run `review-names` and read the series report.
