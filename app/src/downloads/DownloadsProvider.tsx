/**
 * Offline listening: downloads sermon audio to the device, one file at a time, and plays it from there.
 * Media stays linked to the church's own URL (root rule 7); a download is a private on-device copy, as in a podcast app.
 *
 * Two contexts, like the player: `useDownloadActions()` is stable (the player uses it without re-rendering on
 * progress); `useDownloads()` changes while a download runs, so read it only where download state is shown.
 */
import { File } from "expo-file-system";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { autoDownloadTargets, downloadFileName, shouldAutoRemove, type DownloadMeta, type DownloadOrigin } from "./rules";
import { audioDir, audioFile, loadDownloads, partialFile, removeDownload, saveDownload } from "./storage";

import type { SermonProgress } from "@/player/rules";
import type { Series, Sermon } from "@/types/library";

export interface ActiveDownload {
  status: "queued" | "downloading" | "failed";
  /** 0–1, or 0 while the size is unknown. */
  fraction: number;
}

interface DownloadsState {
  done: Record<string, DownloadMeta>;
  active: Record<string, ActiveDownload>;
}

interface DownloadActions {
  /** file:// URI of a complete download, or undefined (then stream). */
  localUri: (sermonId: string) => string | undefined;
  download: (series: Series, sermon: Sermon) => void;
  downloadSeries: (series: Series) => void;
  /** Stop a queued or running download (keeps finished ones). */
  cancel: (sermonId: string) => void;
  cancelSeries: (series: Series) => void;
  /** Cancel, and delete the file if it finished. */
  remove: (sermonId: string) => void;
  removeSeries: (series: Series) => void;
  /** A sermon started playing: fetch it and the next few unheard ones (removed again once heard). */
  fetchAhead: (series: Series, sermonId: string, progress: Record<string, SermonProgress>) => void;
  /** A sermon was heard to the end: drop it if it was only fetched ahead. */
  heard: (sermonId: string) => void;
}

interface Job {
  sermonId: string;
  seriesId: string;
  url: string;
  origin: DownloadOrigin;
}

const ActionsContext = createContext<DownloadActions | null>(null);
const StateContext = createContext<DownloadsState | null>(null);

export function DownloadsProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<DownloadsState>({ done: {}, active: {} });
  const done = useRef<Record<string, DownloadMeta>>({});
  const queue = useRef<Job[]>([]);
  const running = useRef<{ job: Job; abort: AbortController } | null>(null);
  /** Download tapped on a sermon already being fetched ahead: keep it once heard. */
  const manualWhileRunning = useRef(new Set<string>());

  const setDone = useCallback((next: Record<string, DownloadMeta>) => {
    done.current = next;
    setState((s) => ({ ...s, done: next }));
  }, []);

  const setActive = useCallback((sermonId: string, a: ActiveDownload | undefined) => {
    setState((s) => {
      const active = { ...s.active };
      if (a) active[sermonId] = a;
      else delete active[sermonId];
      return { ...s, active };
    });
  }, []);

  useEffect(() => {
    void loadDownloads().then((loaded) => setDone({ ...loaded, ...done.current }));
  }, [setDone]);

  /** Fetch one file to a .part name, then rename, so only complete files are ever played. */
  const fetchOne = useCallback(
    async (job: Job, abort: AbortController) => {
      const fileName = downloadFileName(job.sermonId, job.url);
      const part = partialFile(fileName);
      let shown = 0;
      try {
        audioDir().create({ idempotent: true, intermediates: true });
        await File.downloadFileAsync(job.url, part, {
          idempotent: true,
          signal: abort.signal,
          onProgress: ({ bytesWritten, totalBytes }) => {
            const fraction = totalBytes > 0 ? bytesWritten / totalBytes : 0;
            if (fraction - shown >= 0.02) {
              shown = fraction;
              setActive(job.sermonId, { status: "downloading", fraction });
            }
          },
        });
        const final = audioFile(fileName);
        if (final.exists) final.delete();
        await part.move(final);
        const meta: DownloadMeta = {
          seriesId: job.seriesId,
          origin: manualWhileRunning.current.has(job.sermonId) ? "manual" : job.origin,
          fileName,
          bytes: final.size ?? 0,
          completedAt: new Date().toISOString(),
        };
        await saveDownload(job.sermonId, meta);
        setDone({ ...done.current, [job.sermonId]: meta });
        setActive(job.sermonId, undefined);
      } catch {
        try {
          if (part.exists) part.delete();
        } catch {
          // left for loadDownloads to tidy
        }
        setActive(job.sermonId, abort.signal.aborted ? undefined : { status: "failed", fraction: 0 });
      }
    },
    [setActive, setDone],
  );

  /** Work through the queue one download at a time (a no-op if already running). */
  const drain = useCallback(async () => {
    if (running.current) return;
    for (let job = queue.current.shift(); job; job = queue.current.shift()) {
      const abort = new AbortController();
      running.current = { job, abort };
      manualWhileRunning.current.clear();
      setActive(job.sermonId, { status: "downloading", fraction: 0 });
      await fetchOne(job, abort);
    }
    running.current = null;
  }, [fetchOne, setActive]);

  const enqueue = useCallback(
    (series: Series, sermon: Sermon, origin: DownloadOrigin) => {
      const url = sermon.media.audioUrl;
      if (!url) return;
      const existing = done.current[sermon.id];
      if (existing) {
        // Tapping download on something fetched ahead keeps it after it's heard.
        if (origin === "manual" && existing.origin === "auto") {
          const meta = { ...existing, origin };
          void saveDownload(sermon.id, meta);
          setDone({ ...done.current, [sermon.id]: meta });
        }
        return;
      }
      if (running.current?.job.sermonId === sermon.id) {
        if (origin === "manual") manualWhileRunning.current.add(sermon.id);
        return;
      }
      if (queue.current.some((j) => j.sermonId === sermon.id)) {
        if (origin === "manual") {
          queue.current = queue.current.map((j) => (j.sermonId === sermon.id ? { ...j, origin } : j));
        }
        return;
      }
      queue.current.push({ sermonId: sermon.id, seriesId: series.id, url, origin });
      setActive(sermon.id, { status: "queued", fraction: 0 });
      void drain();
    },
    [drain, setActive, setDone],
  );

  const cancel = useCallback(
    (sermonId: string) => {
      queue.current = queue.current.filter((j) => j.sermonId !== sermonId);
      // A running download clears its own marker when the abort lands; this clears queued and failed ones.
      if (running.current?.job.sermonId === sermonId) running.current.abort.abort();
      else setActive(sermonId, undefined);
    },
    [setActive],
  );

  const remove = useCallback(
    (sermonId: string) => {
      cancel(sermonId);
      const meta = done.current[sermonId];
      if (!meta) return;
      const rest = { ...done.current };
      delete rest[sermonId];
      setDone(rest);
      void removeDownload(sermonId, meta);
    },
    [cancel, setDone],
  );

  const actions = useMemo<DownloadActions>(
    () => ({
      localUri: (id) => {
        const meta = done.current[id];
        return meta ? audioFile(meta.fileName).uri : undefined;
      },
      download: (series, sermon) => enqueue(series, sermon, "manual"),
      downloadSeries: (series) => series.sermons.forEach((m) => enqueue(series, m, "manual")),
      cancel,
      cancelSeries: (series) => series.sermons.forEach((m) => cancel(m.id)),
      remove,
      removeSeries: (series) => series.sermons.forEach((m) => remove(m.id)),
      fetchAhead: (series, sermonId, progress) => {
        for (const id of autoDownloadTargets(series, sermonId, progress)) {
          const m = series.sermons.find((s) => s.id === id);
          if (m) enqueue(series, m, "auto");
        }
      },
      heard: (id) => {
        if (shouldAutoRemove(done.current[id])) remove(id);
      },
    }),
    [cancel, enqueue, remove],
  );

  return (
    <ActionsContext.Provider value={actions}>
      <StateContext.Provider value={state}>{children}</StateContext.Provider>
    </ActionsContext.Provider>
  );
}

export function useDownloadActions(): DownloadActions {
  const v = useContext(ActionsContext);
  if (!v) throw new Error("useDownloadActions outside DownloadsProvider");
  return v;
}

export function useDownloads(): DownloadsState {
  const v = useContext(StateContext);
  if (!v) throw new Error("useDownloads outside DownloadsProvider");
  return v;
}
