import { Link } from "expo-router";
import { FlatList, Text } from "react-native";

import { Row } from "@/components/Row";
import { booksWithSeries, type SeriesFilter } from "@/data/selectors";

import type { Library } from "@/types/library";

/** Books with series, optionally narrowed to a speaker/church. The filter is passed on to the book screen. */
export function BookList({ lib, filter = {} }: { lib: Library; filter?: SeriesFilter }) {
  return (
    <FlatList
      contentInsetAdjustmentBehavior="automatic"
      data={booksWithSeries(lib, filter)}
      keyExtractor={({ book }) => book.code}
      ListEmptyComponent={<Text style={{ padding: 16, color: "#666" }}>No book series yet.</Text>}
      renderItem={({ item: { book, count } }) => (
        <Link href={{ pathname: "/book/[code]", params: { code: book.code, ...filter } }} asChild>
          <Row
            title={book.name}
            subtitle={`${count} series · ${book.testament === "OT" ? "Old" : "New"} Testament`}
          />
        </Link>
      )}
    />
  );
}
