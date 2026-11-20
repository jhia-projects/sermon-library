import { Link } from "expo-router";
import { FlatList } from "react-native";

import { LibraryGate } from "@/components/LibraryGate";
import { Row } from "@/components/Row";
import { seriesForChurch } from "@/data/selectors";

export default function ChurchesScreen() {
  return (
    <LibraryGate>
      {(lib) => (
        <FlatList
          contentInsetAdjustmentBehavior="automatic"
          data={lib.churches}
          keyExtractor={(c) => c.id}
          renderItem={({ item }) => (
            <Link href={{ pathname: "/church/[id]", params: { id: item.id } }} asChild>
              <Row
                title={item.name}
                subtitle={[item.location, `${seriesForChurch(lib, item.id).length} series`].filter(Boolean).join(" · ")}
              />
            </Link>
          )}
        />
      )}
    </LibraryGate>
  );
}
