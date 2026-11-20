/** Pure lookups over a Library. Keep screens thin: query here, render there. */
import { BOOKS } from "./books";

import type { Book, BookCode, Library, Sermon, Series, Speaker } from "@/types/library";

const newestFirst = (a: Series, b: Series) => b.endDate.localeCompare(a.endDate);

/** Narrow browsing to one speaker and/or church (the Speakers and Churches tabs). */
export interface SeriesFilter {
  speakerId?: string;
  churchId?: string;
}

function matches(s: Series, f: SeriesFilter): boolean {
  return (!f.speakerId || s.speakerIds.includes(f.speakerId)) && (!f.churchId || s.churchId === f.churchId);
}

/** Books that have at least one (matching) series, in canonical order, with their series count. */
export function booksWithSeries(lib: Library, filter: SeriesFilter = {}): { book: Book; count: number }[] {
  const counts = new Map<BookCode, number>();
  for (const s of lib.series) if (matches(s, filter)) counts.set(s.book, (counts.get(s.book) ?? 0) + 1);
  return BOOKS.filter((b) => counts.has(b.code)).map((book) => ({ book, count: counts.get(book.code)! }));
}

export function seriesForBook(lib: Library, code: BookCode, filter: SeriesFilter = {}): Series[] {
  return lib.series.filter((s) => s.book === code && matches(s, filter)).sort(newestFirst);
}

export function seriesForSpeaker(lib: Library, speakerId: string): Series[] {
  return lib.series.filter((s) => s.speakerIds.includes(speakerId)).sort(newestFirst);
}

export function seriesForChurch(lib: Library, churchId: string): Series[] {
  return lib.series.filter((s) => s.churchId === churchId).sort(newestFirst);
}

export function findSeries(lib: Library, id: string): Series | undefined {
  return lib.series.find((s) => s.id === id);
}

/** The series a sermon belongs to (each sermon is in at most one). */
export function seriesOfSermon(lib: Library, sermonId: string): Series | undefined {
  return lib.series.find((s) => s.sermons.some((m) => m.id === sermonId));
}

/** Previous/next by array order, which is preached order. Position is derived, never stored. */
export function neighbours(series: Series, sermonId: string): { prev?: Sermon; next?: Sermon; position: number } {
  const i = series.sermons.findIndex((m) => m.id === sermonId);
  return { prev: series.sermons[i - 1], next: series.sermons[i + 1], position: i + 1 };
}

/** False for an interlude (passage in another book) or a sermon with no printed reference. */
export function isInSeriesBook(series: Series, sermon: Sermon): boolean {
  return sermon.passage?.book === series.book;
}

export function speakerName(lib: Library, id: string): string {
  return lib.speakers.find((s) => s.id === id)?.name ?? id;
}

export function churchName(lib: Library, id: string): string {
  return lib.churches.find((c) => c.id === id)?.name ?? id;
}

const hasFullName = (name: string) => name.trim().split(/\s+/).length >= 2;

export type SpeakerRow = { speaker: Speaker; seriesCount: number };

/** Case- and accent-insensitive form for name search ("Jané" -> "jane"). */
const fold = (s: string) =>
  s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();

/**
 * Speakers tab rows, by name. With no query, only speakers with at least `minSeries` series and a full
 * name (a lone first name like "Luke" is ambiguous); with a query, every speaker whose name contains
 * each word, regardless of either rule.
 * A series with several speakers counts for each of them.
 */
export function speakerRows(lib: Library, query = "", minSeries = 5): SpeakerRow[] {
  const counts = new Map<string, number>();
  for (const s of lib.series) for (const id of s.speakerIds) counts.set(id, (counts.get(id) ?? 0) + 1);

  const words = fold(query).split(/\s+/).filter(Boolean);
  return lib.speakers
    .map((speaker) => ({ speaker, seriesCount: counts.get(speaker.id) ?? 0 }))
    .filter(({ speaker, seriesCount }) =>
      words.length === 0
        ? seriesCount >= minSeries && hasFullName(speaker.name)
        : words.every((w) => fold(speaker.name).includes(w)),
    )
    .sort((a, b) => a.speaker.name.localeCompare(b.speaker.name));
}
