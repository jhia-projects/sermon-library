import example from "../../../schema/library.example.json";

import { formatClock, formatMinutes } from "@/format";
import { adjacentPlayable, continueTarget, isFinished, nextRate, resumeFrom, type SermonProgress } from "@/player/rules";
import type { Library, Series } from "@/types/library";

const lib = example as Library;
const series = lib.series.find((s) => s.sermons.length >= 3)!;
const [a, b] = series.sermons as [Series["sermons"][0], Series["sermons"][0]];
const prog = (position: number, duration: number, finished = false): SermonProgress => ({
  position,
  duration,
  finished,
  updatedAt: "2026-01-01T00:00:00Z",
});

describe("player rules", () => {
  test("finished within the last 30 s, or last 5% of a short clip", () => {
    expect(isFinished(1800 - 31, 1800)).toBe(false);
    expect(isFinished(1800 - 29, 1800)).toBe(true);
    expect(isFinished(94, 100)).toBe(false);
    expect(isFinished(96, 100)).toBe(true);
    expect(isFinished(10, 0)).toBe(false); // unknown duration
  });

  test("resume backs off 3 s; finished or new sermons start from the top", () => {
    expect(resumeFrom(undefined)).toBe(0);
    expect(resumeFrom(prog(600, 1800))).toBe(597);
    expect(resumeFrom(prog(1, 1800))).toBe(0);
    expect(resumeFrom(prog(1790, 1800))).toBe(0);
  });

  test("next/previous follow array (preached) order and skip sermons without audio", () => {
    // In the example, sermon 3 (example-church-1003) is video-only.
    const [s1, s2, s3, s4] = series.sermons.map((m) => m.id);
    expect(adjacentPlayable(series, s1!, 1)?.id).toBe(s2);
    expect(adjacentPlayable(series, s1!, -1)).toBeUndefined();
    expect(series.sermons[2]!.media.audioUrl).toBeUndefined();
    expect(adjacentPlayable(series, s2!, 1)?.id).toBe(s4);
    expect(adjacentPlayable(series, s4!, -1)?.id).toBe(s2);
    expect(s3).toBeDefined();
  });

  test("continue from the first unfinished sermon, keyed on sermon.id", () => {
    expect(continueTarget(series, {})?.id).toBe(a.id);
    expect(continueTarget(series, { [a.id]: prog(0, 0, true) })?.id).toBe(b.id);
    const all = Object.fromEntries(series.sermons.map((m) => [m.id, prog(0, 0, true)]));
    expect(continueTarget(series, all)?.id).toBe(a.id);
  });

  test("speed cycles and wraps", () => {
    expect(nextRate(1)).toBe(1.25);
    expect(nextRate(0.75)).toBe(1);
  });

  test("clock and minutes formatting", () => {
    expect(formatClock(75)).toBe("1:15");
    expect(formatClock(3725)).toBe("1:02:05");
    expect(formatMinutes(1500)).toBe("25 min");
    expect(formatMinutes(10)).toBe("1 min");
  });
});
