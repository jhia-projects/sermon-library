import booksJson from "../../../schema/books.json";

import type { Book, BookCode } from "@/types/library";

/** The 66 books in canonical order (shared with the pipeline). */
export const BOOKS: readonly Book[] = (booksJson.books as Book[]).slice().sort((a, b) => a.order - b.order);

const BY_CODE = new Map(BOOKS.map((b) => [b.code, b]));

export function bookByCode(code: BookCode): Book | undefined {
  return BY_CODE.get(code);
}

export function bookName(code: BookCode): string {
  return BY_CODE.get(code)?.name ?? code;
}
