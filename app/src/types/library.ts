/**
 * Types for library.json. Hand-mirrored from ../../../schema/library.schema.json — the schema is
 * the contract; change it first (root CLAUDE.md rule 1), then this file.
 */

export type BookCode = string; // OSIS code from schema/books.json, e.g. "Rom", "1Cor"

export interface Book {
  code: BookCode;
  name: string;
  testament: "OT" | "NT";
  order: number;
  aliases?: string[];
}

export interface Passage {
  /** Usually the series' book; an interlude sermon (e.g. a Psalm in a Mark series) has its own. */
  book: BookCode;
  startChapter: number;
  startVerse?: number;
  endChapter: number;
  endVerse?: number;
  /** As printed by the church, e.g. "Romans 1:1–17". */
  display: string;
}

export interface Media {
  audioUrl?: string;
  videoUrl?: string;
  youtubeId?: string;
}

export interface Sermon {
  id: string;
  title: string;
  date: string; // YYYY-MM-DD
  speakerId: string;
  /** Omitted when the church printed no reference. */
  passage?: Passage;
  durationSeconds?: number;
  sourceUrl?: string;
  media: Media;
}

export interface Series {
  id: string;
  title: string;
  description?: string;
  book: BookCode;
  churchId: string;
  speakerIds: string[];
  artworkUrl?: string;
  sourceUrl: string;
  startDate: string;
  endDate: string;
  isComplete?: boolean;
  /** Preached order. Play in array order; never store an index (key on sermon.id). */
  sermons: Sermon[];
}

export interface Church {
  id: string;
  name: string;
  location?: string;
  websiteUrl: string;
  logoUrl?: string;
}

export interface Speaker {
  id: string;
  name: string;
  photoUrl?: string;
}

export interface Library {
  schemaVersion: string;
  generatedAt: string;
  churches: Church[];
  speakers: Speaker[];
  series: Series[];
}
