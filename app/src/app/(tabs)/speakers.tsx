import { Link } from "expo-router";
import { useMemo, useState } from "react";
import { FlatList, StyleSheet, Text, TextInput } from "react-native";

import { LibraryGate } from "@/components/LibraryGate";
import { Row } from "@/components/Row";
import { speakerRows } from "@/data/selectors";

import type { Library } from "@/types/library";

/** Speakers with fewer series than this are hidden until searched for. */
const MIN_SERIES = 5;

export default function SpeakersScreen() {
  return <LibraryGate>{(lib) => <SpeakerList lib={lib} />}</LibraryGate>;
}

function SpeakerList({ lib }: { lib: Library }) {
  const [query, setQuery] = useState("");
  const rows = useMemo(() => speakerRows(lib, query, MIN_SERIES), [lib, query]);
  const searching = query.trim() !== "";

  return (
    <FlatList
      contentInsetAdjustmentBehavior="automatic"
      keyboardDismissMode="on-drag"
      keyboardShouldPersistTaps="handled"
      data={rows}
      keyExtractor={(r) => r.speaker.id}
      // An element, not a component: typing must not remount the input (it would drop the keyboard).
      ListHeaderComponent={
        <TextInput
          style={styles.search}
          value={query}
          onChangeText={setQuery}
          placeholder="Search speakers"
          placeholderTextColor="#888"
          clearButtonMode="while-editing"
          autoCorrect={false}
          autoCapitalize="none"
          returnKeyType="search"
        />
      }
      ListEmptyComponent={searching ? <Text style={styles.note}>No speakers match “{query.trim()}”.</Text> : undefined}
      ListFooterComponent={
        searching ? undefined : (
          <Text style={styles.note}>
            Showing speakers with {MIN_SERIES}+ series. Search to find all {lib.speakers.length}.
          </Text>
        )
      }
      renderItem={({ item }) => (
        <Link href={{ pathname: "/speaker/[id]", params: { id: item.speaker.id } }} asChild>
          <Row title={item.speaker.name} subtitle={`${item.seriesCount} series`} />
        </Link>
      )}
    />
  );
}

const styles = StyleSheet.create({
  search: {
    margin: 16,
    marginBottom: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 10,
    fontSize: 16,
    backgroundColor: "rgba(127,127,127,0.15)",
  },
  note: { padding: 16, fontSize: 13, color: "#888", textAlign: "center" },
});
