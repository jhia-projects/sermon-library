/**
 * One audio player for the whole app. Plays a sermon from its series, resumes from saved progress,
 * auto-advances in preached order and shows lock-screen controls. Plays a downloaded copy when there is one
 * (src/downloads), and fetches the next few sermons ahead so a series carries on without signal.
 *
 * Two contexts: `usePlayer()` (what's playing, saved progress, actions) changes rarely; `usePlayerStatus()`
 * (position, playing, buffering) updates twice a second. Only components that show live position should
 * read the second, so long lists don't re-render while audio plays.
 */
import { setAudioModeAsync, useAudioPlayer, useAudioPlayerStatus, type AudioStatus } from "expo-audio";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { adjacentPlayable, isFinished, nextRate, resumeFrom, type SermonProgress } from "./rules";
import { loadAllProgress, loadLastPlayed, saveLastPlayed, saveProgress } from "./storage";

import { useLibraryState } from "@/data/LibraryProvider";
import { useDownloadActions } from "@/downloads/DownloadsProvider";
import { findSeries, speakerName } from "@/data/selectors";
import type { Series, Sermon } from "@/types/library";

export interface NowPlaying {
  series: Series;
  sermon: Sermon;
}

interface PlayerApi {
  current?: NowPlaying;
  progress: Record<string, SermonProgress>;
  rate: number;
  /** Start (or resume) this sermon. Tapping the one already playing just keeps playing. */
  play: (series: Series, sermon: Sermon) => void;
  toggle: () => void;
  seekBy: (seconds: number) => void;
  seekTo: (seconds: number) => void;
  next: () => void;
  /** Back to the start of this sermon, or to the previous sermon if already near the start. */
  previous: () => void;
  cycleRate: () => void;
}

const SAVE_EVERY_SECONDS = 10;

const PlayerContext = createContext<PlayerApi | null>(null);
const StatusContext = createContext<AudioStatus | null>(null);

export function PlayerProvider({ children }: { children: ReactNode }) {
  const libState = useLibraryState();
  const lib = libState.status === "ready" ? libState.library : undefined;
  const downloads = useDownloadActions();

  const player = useAudioPlayer(null, { updateInterval: 500 });
  const status = useAudioPlayerStatus(player);

  const [current, setCurrent] = useState<NowPlaying>();
  const [progress, setProgress] = useState<Record<string, SermonProgress>>({});
  const [rate, setRate] = useState(1);

  const loadedId = useRef<string | null>(null); // sermon whose audio is in the player
  const pendingStart = useRef<number | null>(null); // seek here once the new source has loaded
  const lastSavedAt = useRef(0);

  useEffect(() => {
    // Plays with the silent switch on, keeps playing in the background (needs a dev/production build;
    // Expo Go may stop when backgrounded), and takes audio focus as lock-screen controls require.
    setAudioModeAsync({ playsInSilentMode: true, shouldPlayInBackground: true, interruptionMode: "doNotMix" }).catch(
      () => {},
    );
    loadAllProgress().then(setProgress);
  }, []);

  // Restore the last sermon (paused) once the library is available, so the mini player is there on launch.
  useEffect(() => {
    if (!lib || current) return;
    loadLastPlayed().then((last) => {
      const series = last && findSeries(lib, last.seriesId);
      const sermon = series?.sermons.find((m) => m.id === last?.sermonId);
      if (series && sermon) setCurrent((c) => c ?? { series, sermon });
    });
  }, [lib, current]);

  const record = useCallback((sermonId: string, position: number, duration: number) => {
    lastSavedAt.current = position;
    setProgress((prev) => {
      const p: SermonProgress = {
        position,
        duration,
        finished: Boolean(prev[sermonId]?.finished) || isFinished(position, duration),
        updatedAt: new Date().toISOString(),
      };
      void saveProgress(sermonId, p);
      return { ...prev, [sermonId]: p };
    });
  }, []);

  const saveCurrent = useCallback(() => {
    if (current && loadedId.current === current.sermon.id && player.duration > 0) {
      record(current.sermon.id, player.currentTime, player.duration);
    }
  }, [current, player, record]);

  const load = useCallback(
    (series: Series, sermon: Sermon) => {
      if (!sermon.media.audioUrl) return;
      const uri = downloads.localUri(sermon.id) ?? sermon.media.audioUrl;
      if (loadedId.current === sermon.id) {
        player.play();
        return;
      }
      saveCurrent();
      setCurrent({ series, sermon });
      void saveLastPlayed({ seriesId: series.id, sermonId: sermon.id });
      loadedId.current = sermon.id;
      const start = resumeFrom(progress[sermon.id]);
      pendingStart.current = start > 0 ? start : null;
      player.replace({ uri });
      if (start === 0) player.play();
      downloads.fetchAhead(series, sermon.id, progress);
      player.setActiveForLockScreen(
        true,
        {
          title: sermon.title,
          artist: lib ? speakerName(lib, sermon.speakerId) : undefined,
          albumTitle: series.title,
          artworkUrl: series.artworkUrl,
        },
        { showSeekBackward: true, showSeekForward: true, seekBackwardIntervalSeconds: 15, seekForwardIntervalSeconds: 30 },
      );
    },
    [downloads, lib, player, progress, saveCurrent],
  );

  // A resumed sermon: seek once its source has loaded, then play. (Keyed on duration too, since the
  // previous source was also "loaded".)
  useEffect(() => {
    const start = pendingStart.current;
    if (start === null || !status.isLoaded || status.duration <= 0) return;
    pendingStart.current = null;
    void player.seekTo(start).then(() => player.play());
  }, [player, status.isLoaded, status.duration]);

  useEffect(() => {
    if (status.isLoaded) player.setPlaybackRate(rate);
  }, [player, rate, status.isLoaded]);

  const next = useCallback(() => {
    if (!current) return;
    const n = adjacentPlayable(current.series, current.sermon.id, 1);
    if (n) load(current.series, n);
  }, [current, load]);

  // Latest values for the status listener below, which subscribes once.
  const latest = useRef({ current, next, record, heard: downloads.heard });
  useEffect(() => {
    latest.current = { current, next, record, heard: downloads.heard };
  });

  // Save progress while playing (every few seconds) and on pause; at the end of a sermon, mark it heard
  // and carry on through the series in preached order.
  useEffect(() => {
    let wasPlaying = false;
    const sub = player.addListener("playbackStatusUpdate", (s) => {
      const { current: cur, next: advance, record: save, heard } = latest.current;
      if (!cur || loadedId.current !== cur.sermon.id || s.duration <= 0) return;
      if (s.didJustFinish) {
        save(cur.sermon.id, s.duration, s.duration);
        advance();
        heard(cur.sermon.id); // after advancing: drop a fetched-ahead copy once heard
      } else if ((wasPlaying && !s.playing) || (s.playing && Math.abs(s.currentTime - lastSavedAt.current) >= SAVE_EVERY_SECONDS)) {
        save(cur.sermon.id, s.currentTime, s.duration);
      }
      wasPlaying = s.playing;
    });
    return () => sub.remove();
  }, [player]);

  const api = useMemo<PlayerApi>(
    () => ({
      current,
      progress,
      rate,
      play: load,
      toggle: () => {
        if (!current) return;
        if (loadedId.current !== current.sermon.id) return load(current.series, current.sermon); // restored on launch
        if (player.playing) {
          player.pause();
          saveCurrent();
        } else player.play();
      },
      seekBy: (s) => void player.seekTo(Math.max(0, Math.min(player.currentTime + s, player.duration || Infinity))),
      seekTo: (s) => void player.seekTo(s),
      next,
      previous: () => {
        if (!current) return;
        const p = adjacentPlayable(current.series, current.sermon.id, -1);
        if (player.currentTime > 5 || !p) void player.seekTo(0);
        else load(current.series, p);
      },
      cycleRate: () => setRate(nextRate),
    }),
    [current, progress, rate, load, next, player, saveCurrent],
  );

  return (
    <PlayerContext.Provider value={api}>
      <StatusContext.Provider value={status}>{children}</StatusContext.Provider>
    </PlayerContext.Provider>
  );
}

export function usePlayer(): PlayerApi {
  const v = useContext(PlayerContext);
  if (!v) throw new Error("usePlayer outside PlayerProvider");
  return v;
}

export function usePlayerStatus(): AudioStatus {
  const v = useContext(StatusContext);
  if (!v) throw new Error("usePlayerStatus outside PlayerProvider");
  return v;
}

/** Is this sermon the one loaded into the player (and so `usePlayerStatus` describes it)? */
export function useIsCurrent(sermonId: string): boolean {
  return usePlayer().current?.sermon.id === sermonId;
}
