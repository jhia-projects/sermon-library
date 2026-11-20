import { Link } from "expo-router";
import { FlatList } from "react-native";

import { LibraryGate } from "@/components/LibraryGate";
import { Row } from "@/components/Row";
import { seriesForSpeaker } from "@/data/selectors";

export default function SpeakersScreen() {
  return (
    <LibraryGate>
      {(lib) => (
        <FlatList
          contentInsetAdjustmentBehavior="automatic"
          data={[...lib.speakers].sort((a, b) => a.name.localeCompare(b.name))}
          keyExtractor={(s) => s.id}
          renderItem={({ item }) => (
            <Link href={{ pathname: "/speaker/[id]", params: { id: item.id } }} asChild>
              <Row title={item.name} subtitle={`${seriesForSpeaker(lib, item.id).length} series`} />
            </Link>
          )}
        />
      )}
    </LibraryGate>
  );
}
