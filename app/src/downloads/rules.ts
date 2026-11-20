/** Pure download rules (no React, no file system) so they can be unit tested. */
import { isPlayable, type SermonProgress } from "@/player/rules";
import type { Series } from "@/types/library";

/** "manual": you tapped download (kept until you remove it). "auto": fetched ahead while listening (removed once heard). */
export type DownloadOrigin = "manual" | "auto";

/** Saved per sermon.id once its file is complete. */
export interface DownloadMeta {
  seriesId: string;
  origin: DownloadOrigin;
  fileName: string;
  bytes: number;
  completedAt: string;
}

/** How many sermons after the one playing are fetched ahead automatically. */
export const AUTO_AHEAD = 2;

/**
 * What to fetch when a sermon starts: that sermon, then the next `ahead` playable sermons in preached
 * order that haven't been heard. Losing signal mid-series then doesn't stop the series.
 */
export function autoDownloadTargets(
  series: Series,
  sermonId: string,
  progress: Record<string, SermonProgress>,
  ahead = AUTO_AHEAD,
): string[] {
  const list = series.sermons;
  const i = list.findIndex((m) => m.id === sermonId);
  if (i < 0) return [];
  const out = isPlayable(list[i]!) ? [sermonId] : [];
  for (let j = i + 1; j < list.length && out.length < ahead + 1; j++) {
    const m = list[j]!;
    if (isPlayable(m) && !progress[m.id]?.finished) out.push(m.id);
  }
  return out;
}

const AUDIO_EXTENSIONS = new Set(["mp3", "m4a", "aac", "mp4", "wav"]);

/** On-device file name: the permanent sermon id plus the source's extension (ids are kebab-case slugs). */
export function downloadFileName(sermonId: string, audioUrl: string): string {
  let ext = "mp3";
  try {
    const m = /\.([a-z0-9]+)$/i.exec(new URL(audioUrl).pathname);
    if (m && AUDIO_EXTENSIONS.has(m[1]!.toLowerCase())) ext = m[1]!.toLowerCase();
  } catch {
    // keep mp3
  }
  return `${sermonId}.${ext}`;
}

/** Auto downloads are removed once heard; manual ones stay until you remove them. */
export function shouldAutoRemove(meta: DownloadMeta | undefined): boolean {
  return meta?.origin === "auto";
}

/** Downloaded / total playable sermons in a series, for the "Download series" button. */
export function seriesDownloadCount(series: Series, downloaded: (sermonId: string) => boolean): { done: number; total: number } {
  const playable = series.sermons.filter(isPlayable);
  return { done: playable.filter((m) => downloaded(m.id)).length, total: playable.length };
}

/** "28 MB", "1.2 GB". */
export function formatBytes(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  return `${Math.max(1, Math.round(bytes / 1e6))} MB`;
}
