import example from "../../../schema/library.example.json";

import {
  autoDownloadTargets,
  downloadFileName,
  formatBytes,
  seriesDownloadCount,
  shouldAutoRemove,
  type DownloadMeta,
} from "@/downloads/rules";
import type { SermonProgress } from "@/player/rules";
import type { Library } from "@/types/library";

const lib = example as Library;
// Example series: 1001, 1002, 1003 (video only), 1004, 1005.
const series = lib.series[0]!;
const heard: SermonProgress = { position: 1800, duration: 1800, finished: true, updatedAt: "2026-01-01T00:00:00Z" };
const meta = (origin: DownloadMeta["origin"]): DownloadMeta => ({
  seriesId: series.id,
  origin,
  fileName: "x.mp3",
  bytes: 1,
  completedAt: "2026-01-01T00:00:00Z",
});

describe("download rules", () => {
  test("fetch ahead: the sermon playing plus the next two with audio, in preached order", () => {
    expect(autoDownloadTargets(series, "example-church-1001", {})).toEqual([
      "example-church-1001",
      "example-church-1002",
      "example-church-1004", // 1003 has no audio
    ]);
  });

  test("fetch ahead skips sermons already heard, and stops at the end of the series", () => {
    expect(autoDownloadTargets(series, "example-church-1001", { "example-church-1002": heard })).toEqual([
      "example-church-1001",
      "example-church-1004",
      "example-church-1005",
    ]);
    expect(autoDownloadTargets(series, "example-church-1005", {})).toEqual(["example-church-1005"]);
    expect(autoDownloadTargets(series, "not-in-series", {})).toEqual([]);
  });

  test("file name is the permanent sermon id plus the source's audio extension", () => {
    expect(downloadFileName("all-souls-123", "https://www.allsouls.org/Media/123.MP3")).toBe("all-souls-123.mp3");
    expect(downloadFileName("a", "https://cdn.example.com/x/talk.m4a?token=1")).toBe("a.m4a");
    expect(downloadFileName("a", "https://example.com/play.aspx?id=5")).toBe("a.mp3"); // not an audio extension
    expect(downloadFileName("a", "not a url")).toBe("a.mp3");
  });

  test("only fetched-ahead copies are removed once heard", () => {
    expect(shouldAutoRemove(meta("auto"))).toBe(true);
    expect(shouldAutoRemove(meta("manual"))).toBe(false);
    expect(shouldAutoRemove(undefined)).toBe(false);
  });

  test("series count covers sermons with audio only", () => {
    expect(seriesDownloadCount(series, (id) => id === "example-church-1001")).toEqual({ done: 1, total: 4 });
  });

  test("sizes", () => {
    expect(formatBytes(28_400_000)).toBe("28 MB");
    expect(formatBytes(200_000)).toBe("1 MB");
    expect(formatBytes(1_230_000_000)).toBe("1.2 GB");
  });
});
