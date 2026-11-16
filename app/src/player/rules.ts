/** Pure playback rules (no React, no storage) so they can be unit tested. */
import type { Series, Sermon } from "@/types/library";

/** Saved per sermon.id: never per position (positions shift when backfill inserts sermons). */
export interface SermonProgress {
  position: number; // seconds
  duration: number; // seconds, 0 if unknown
  /** Sticky: once heard to the end, a sermon stays heard even if replayed. */
  finished: boolean;
  updatedAt: string;
}

/** Heard to the end: within the last 30 s (or last 5% of a short clip). Sermons often end with silence or music. */
export function isFinished(position: number, duration: number): boolean {
  return duration > 0 && position >= duration - Math.min(30, duration * 0.05);
}

/** Where to start: from the top if never started or finished, otherwise a few seconds before where they stopped. */
export function resumeFrom(p: SermonProgress | undefined): number {
  if (!p || isFinished(p.position, p.duration)) return 0;
  return Math.max(0, p.position - 3);
}

export function isPlayable(sermon: Sermon): boolean {
  return Boolean(sermon.media.audioUrl);
}

/** The next/previous playable sermon in preached (array) order, skipping any without audio. */
export function adjacentPlayable(series: Series, sermonId: string, step: 1 | -1): Sermon | undefined {
  const list = series.sermons;
  for (let i = list.findIndex((m) => m.id === sermonId) + step; i >= 0 && i < list.length; i += step) {
    if (isPlayable(list[i]!)) return list[i];
  }
  return undefined;
}

/** "Continue" target: the first sermon in order that isn't finished (or the first, if all are). */
export function continueTarget(series: Series, progress: Record<string, SermonProgress>): Sermon | undefined {
  const playable = series.sermons.filter(isPlayable);
  return playable.find((m) => !progress[m.id]?.finished) ?? playable[0];
}

export const PLAYBACK_RATES = [1, 1.25, 1.5, 1.75, 2, 0.75] as const;

export function nextRate(rate: number): number {
  const i = PLAYBACK_RATES.indexOf(rate as (typeof PLAYBACK_RATES)[number]);
  return PLAYBACK_RATES[(i + 1) % PLAYBACK_RATES.length]!;
}
