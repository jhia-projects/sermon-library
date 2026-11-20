import { BookList } from "@/components/BookList";
import { LibraryGate } from "@/components/LibraryGate";

/** Browse by book: the app's primary entry point. */
export default function BooksScreen() {
  return <LibraryGate>{(lib) => <BookList lib={lib} />}</LibraryGate>;
}
