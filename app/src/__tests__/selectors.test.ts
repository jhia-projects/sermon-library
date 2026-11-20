import exampleLibrary from "../../../schema/library.example.json";
import { BOOKS, bookName } from "../data/books";
import { checkVersion, UnsupportedLibraryError } from "../data/library";
import { booksWithSeries, findSeries, isInSeriesBook, neighbours, seriesForBook } from "../data/selectors";
import { formatDate, formatYearRange } from "../format";

import type { Library } from "../types/library";

const lib = exampleLibrary as Library;

test("books.json has the 66 books in canonical order", () => {
  expect(BOOKS).toHaveLength(66);
  expect(BOOKS[0]?.code).toBe("Gen");
  expect(BOOKS[65]?.code).toBe("Rev");
  expect(bookName("Rom")).toBe("Romans");
});

test("browse by book lists only books with series", () => {
  const codes = booksWithSeries(lib).map(({ book }) => book.code);
  expect(codes).toContain("Rom");
  expect(codes).not.toContain("Ps"); // the Psalm interlude does not make a Psalms series
  expect(seriesForBook(lib, "Rom").length).toBeGreaterThan(0);
});

test("sermons play in array (preached) order and are dated ascending", () => {
  for (const s of lib.series) {
    const dates = s.sermons.map((m) => m.date);
    expect([...dates].sort()).toEqual(dates);
  }
});

test("neighbours and position come from the array, keyed by sermon id", () => {
  const s = lib.series[0]!;
  const second = s.sermons[1]!;
  const n = neighbours(s, second.id);
  expect(n.position).toBe(2);
  expect(n.prev?.id).toBe(s.sermons[0]!.id);
  expect(n.next?.id).toBe(s.sermons[2]?.id);
});

test("an interlude sermon stays in the series but is marked off-book", () => {
  const s = findSeries(lib, lib.series[0]!.id)!;
  const interlude = s.sermons.find((m) => m.passage?.book === "Ps");
  expect(interlude).toBeDefined();
  expect(isInSeriesBook(s, interlude!)).toBe(false);
});

test("rejects an unsupported major schemaVersion", () => {
  expect(() => checkVersion({ ...lib, schemaVersion: "2.0.0" })).toThrow(UnsupportedLibraryError);
  expect(checkVersion(lib)).toBe(lib);
});

test("formatting", () => {
  expect(formatDate("2025-01-26")).toBe("26 Jan 2025");
  expect(formatYearRange("2024-09-01", "2025-02-02")).toBe("2024–2025");
  expect(formatYearRange("2025-01-05", "2025-02-02")).toBe("2025");
});

test("speaker and church filters narrow books and series", () => {
  const s = lib.series[0]!;
  const speakerId = s.speakerIds[0]!;
  expect(booksWithSeries(lib, { speakerId }).map(({ book }) => book.code)).toContain(s.book);
  expect(seriesForBook(lib, s.book, { churchId: s.churchId }).map((x) => x.id)).toContain(s.id);
  expect(booksWithSeries(lib, { speakerId: "nobody" })).toEqual([]);
  expect(seriesForBook(lib, s.book, { churchId: "other-church" })).toEqual([]);
});
