# Series derivation: the core feature

The app's value is answering one question well: **which sermons, in order, form a church's series through one book of the Bible?**
Churches don't publish that as data. We infer it from the series label, the printed references and the dates. Every mistake is visible to a listener:
- a sermon missing from a series;
- a series split in two;
- a topical series published as a book study.

This document covers the rules we use now (deterministic), how we validate them, and the planned LLM review step.

**Guiding principle: precision over recall.** Leaving out a real series is better than publishing a wrong one. A series we left out can be added later; a wrong one damages trust in the series we did get right.

---

## 1. Deterministic derivation (implemented: `pipeline/src/sermon_pipeline/build.py`)

1. **Collect.** The RSS feed comes first. Scraping only backfills missing sermons and fills empty fields (see `policy.py`).
2. **Group by series label.** Labels go through alias resolution and case/punctuation folding.
   - An explicit label (`Series: X`, or `X: subtitle`) counts.
   - A bare description counts only if it matches an explicit label.
   - A sermon with no label belongs to no series.
3. **Exclude** occasions by name (`exclude`) or by substring (`exclude_patterns`): World Mission Sunday, Christmas, carols, Advent.
3a. **Repeated services** (opt-in: `[series] one_per_service_half = true`; St Helen's only). One sermon preached at several services on the same day appears once per service, each with its own media id (St Helen's: 9.30am + 11.15am, 4pm + 6pm). Within a series, keep one copy per date per half-day (morning = before 12pm, evening = from 12pm): the earliest service, then the lowest id. Sermons without a date or a readable service time are never dropped. Dropped copies are logged on a `=` line and counted as `repeated service`.
4. **Split into runs with a 1-year look-forward.** Sort by date. A sermon continues the run if the previous one is ≤365 days earlier; otherwise it starts a new series. "Romans" in 1985 and "Romans" in 2012 are therefore two series.
5. **Book.**
   - Each sermon's references are its feed reference plus every reference the site lists. A sermon counts for a book if **any** of its references is in that book.
   - The series book is the most common one. It needs ≥ `min_book_share` of sermons: 0.8 by default, and validate.py enforces 0.8 as the floor.
   - The remaining sermons are **kept in place**. A sermon with no reference in the series book gets its own book's `passage` (an interlude); a sermon with no printed reference gets no `passage` (nothing is guessed).
   - Each kept sermon is logged on a `~` line.
6. **3-year cap.** If the first and last sermons are more than 3 years apart, the run is skipped. It is not trimmed.
7. **Size.** A series needs ≥2 sermons. The exception is an explicitly labelled series that is still in progress.
8. **Validate** (`validate.py`) before writing anything:
   - the JSON Schema;
   - referential integrity;
   - the ≥80% book share;
   - each `passage.book` matches its printed `display`;
   - no gap over 1 year and a span of at most 3 years;
   - preached order and unique ids, so a sermon is in at most one series.

**What 80% means for small series.** 2–4 sermons: all must be in the book (3/4 = 75%). 5–9 sermons: one may be off-book. 10–14 sermons: two may be off-book.

### Effect of the 80% rule (live, feed + listing page 1, 2026-11-16)
The build went from 11 to **13 series**. Two series are new:
- *To the Ends of the Earth* (Acts): keeps one sermon that is only in Isaiah.
- *Who Do You Say That I Am* (John): keeps one Psalm sermon.

*The King Who Chose to Die* is at 7/9 = 78% without the archive rows. With archive rows, which list the Mark reference for the Daniel and Psalm sermons, it passes at 100%. Topical series still fail correctly:
- *Finding Truth*: 33%;
- *Apostle Peter on Christian Growth*: 1 Peter and 2 Peter, 50%;
- *But I say to you*: 60%.

---

## 2. Known failure modes of the rules

| Failure | Example | Rule behaviour |
|---|---|---|
| Topical series that happens to draw mostly on one book | "Finding Contentment": 2 Luke + 1 Romans | Correctly fails at 67%. With 5 Luke + 1 Romans it would **pass** (83%): a false positive |
| Book series with many interludes | Mark series with Daniel/Psalm sermons | Fails unless the listing prints the in-book reference |
| Two-book series | 1 & 2 Peter | Fails, and it's out of scope by definition. Do we want a "letters of Peter" series? A product decision |
| Missing or garbled labels | sermon with no `Series:` line | Dropped as "no series", even though its date and passage clearly fit |
| Same label, two books in one year | "Summer Psalms" one year, then a different book under a reused name | Split only by book share, not by passage |
| Label covers more than one book study | a long "Gospel of Mark" label across two terms with a break of under a year | Kept as one series (correct), unless it spans more than 3 years (skipped, not split) |

The rules can't tell a **book study** (consecutive passages working through the text) from a **topical series** that cites one book. The LLM review in section 4 is aimed at that gap.

---

## 3. Deterministic signals to add next (cheap, no LLM)

These help a human (or the LLM) review a series; none of them publishes on its own.

1. **Progression score.** Rank correlation (Kendall τ) between date order and the start position (chapter, verse) of in-book passages. A book study is close to +1. A topical series jumps around. Log it per series; flag τ < 0.5.
2. **Coverage.** The distinct chapters covered as a fraction of the book's chapters, plus how contiguous they are. Useful for the "complete series" promise and for the app UI.
3. **The church's own series page** is the strongest membership signal. All Souls `/Groups/<id>/<Name>.aspx` lists exactly the sermons the church grouped. Compare our run to it: sermons we have that it lacks, and the reverse.
4. **Orphan rescue (report only).** An unlabelled sermon whose date falls inside a series' run, with a passage that fits the series book and sequence. Report it as a candidate and never add it automatically.
5. **Cadence.** A series that is mostly weekly but has one gap of 6 months or more is likely two series. Report it.
6. **Stability across builds.** Diff each build's series membership against the previous published `library.json`.
   - Flag any series that lost sermons or changed book.
   - Flag any id that disappeared. Ids are permanent and the app stores them.

---

## 4. LLM-assisted validation (designed, not built)

### Where it sits
```
deterministic candidates ──► LLM review (structured verdict) ──► decision policy ──► library.json
        ▲                              │                               │
  rules + signals (§3)          cached by input hash             review.toml (human)
```
The LLM only **reviews** candidates. It never reads raw feeds, never writes data fields and never publishes on its own.

### Inputs (one request per candidate series)
- **The candidate:** label, proposed book, and the rule outcome and reason (published / skipped with "78% Mark").
- **Each sermon:** our id, date, title, speaker, **every printed reference**, and the description. Include neighbours too: the same church's sermons within ±8 weeks that aren't in this run, so the model can propose trim or merge.
- **Signals from §3:** progression τ, coverage, gaps, series-page diff.
- **The rules:** the series rules from the root CLAUDE.md, plus 5–10 labelled examples (accept / topical / interlude / split). These go in the **cached system prompt**.

### Output (structured outputs, `output_config.format` / `client.messages.parse`)
```json
{
  "verdict": "accept | reject_topical | reject_occasion | trim | split | merge | needs_human",
  "book": "Mark",
  "isBookStudy": true,
  "members": [
    {"sermonId": "all-souls-langham-place-33187", "include": true,
     "role": "exposition | interlude | introduction | unrelated", "reason": "Psalm 22 read alongside Mark 15"}
  ],
  "splitBefore": ["<sermonId>"],
  "confidence": "high | medium | low",
  "rationale": "≤3 sentences"
}
```
**Code checks every response before using it:**
- every `sermonId` is one of the ids we sent;
- `book` is a code in `schema/books.json`;
- every sermon sent appears exactly once;
- the result still satisfies `validate.py`.

The model **selects and labels**; it never produces titles, passages, dates or URLs. That keeps CLAUDE.md rule 5 (never fabricate data) intact.

### Decision policy
| Rules | LLM | Outcome |
|---|---|---|
| pass | accept (high/medium) | publish |
| pass | reject / split / trim | keep the previously published state; add the series to the review queue |
| fail (near miss, e.g. ≥60%) | accept, confidence high | review queue with the proposed membership; a human approves it in `review.toml` |
| fail | reject | skip (as now) |
| anything | needs_human / low confidence | review queue |

`pipeline/review.toml` stays the single source of human decisions. Proposed sections:
- `[[series.approve]]`: id, membership, book;
- `[[series.reject]]`;
- `[[series.split]]`.

The build applies these decisions deterministically, so the published library never depends on a live model call.

### API choices (Claude API, Python `anthropic` SDK)
- **Model:** `claude-opus-5-5` with adaptive thinking (always on) and `effort: "medium"` to start. Moving to `claude-sonnet-5-5` or `claude-haiku-5-5` is a later decision: make it only after the eval (below) shows quality holds.
- **Message Batches API:** the weekly cron is asynchronous anyway, and batches cost 50% less. Results arrive in any order, so key them by `custom_id` (the series candidate id plus the input hash).
- **Prompt caching:** the system prompt (rules + examples) is frozen and byte-stable, with a `cache_control` breakpoint after it. The per-series JSON comes after the breakpoint. Serialize with `sort_keys=True`. Put no timestamps in the prompt.
- **Result cache:** `pipeline/series-reviews/<input-hash>.json` is committed. The hash covers the prompt version, model and inputs. A weekly run only calls the API for new or changed candidates, and CI builds stay reproducible offline.
- **Refusals / errors:** a `refusal`, `max_tokens` or schema failure becomes `needs_human`. It never counts as an accept.

### Cost (rough, Opus 5.5 at $4 / $20 per MTok, batch −50%)
Per series: about 3k tokens of cached system prompt, about 1.5–3k tokens of series input, and about 0.5–1.5k output tokens including thinking. That is roughly **$0.01–0.03 per series**.
- Weekly: a few changed candidates, so cents.
- One-off review of a full archive: roughly 500–800 candidate series, so roughly $10–25.

### Evaluation (before trusting it)
1. **Gold set.** Hand-label about 40 All Souls candidates, using the user's own review results:
   - clear book studies;
   - interlude series (The King Who Chose to Die);
   - topical series (Finding Truth, Finding Contentment);
   - occasions;
   - two-book series (1 & 2 Peter).
   Give each the correct membership.
2. **Metrics.** Series-level precision and recall, and per-sermon membership accuracy. Compare three variants: **rules alone**, **LLM alone** and **rules + LLM policy**.
3. **Re-run after changes.** Re-run the eval after any change to the prompt, the model or the rules. Store it under `pipeline/tests/fixtures/series-gold/`.
4. **Tooling.** `/claude-api build-eval` can scaffold it.

### Build order
1. The §3 signals (progression τ, series-page diff), logged per series.
2. The gold set plus an offline eval of the rules alone. This gives the baseline.
3. The LLM review command, `sermon-pipeline review-series out/library.json`. It is opt-in, writes proposals to the review queue and never changes the build.
4. Approval sections in `review.toml`, applied by the build.
5. The weekly cron runs the review on changed candidates only.
