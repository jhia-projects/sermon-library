import { Link, Stack, useLocalSearchParams } from "expo-router";
import { FlatList, Text } from "react-native";

import { LibraryGate } from "@/components/LibraryGate";
import { Row } from "@/components/Row";
import { bookName } from "@/data/books";
import { churchName, seriesForBook, speakerName } from "@/data/selectors";
import { countLabel, formatYearRange } from "@/format";

/** Every series through one book, optionally narrowed to one speaker or church (there can be several, from different years or churches). */
export default function BookScreen() {
  // speakerId / churchId arrive when browsing from the Speakers or Churches tab.
  const { code, speakerId, churchId } = useLocalSearchParams<{ code: string; speakerId?: string; churchId?: string }>();
  return (
    <LibraryGate>
      {(lib) => (
        <>
          <Stack.Screen options={{ title: bookName(code) }} />
          <FlatList
            contentInsetAdjustmentBehavior="automatic"
            data={seriesForBook(lib, code, { speakerId, churchId })}
            ListHeaderComponent={
              speakerId || churchId ? (
                <Text style={{ paddingHorizontal: 16, paddingTop: 12, color: "#666" }}>
                  {speakerId ? `Preached by ${speakerName(lib, speakerId)}` : `At ${churchName(lib, churchId!)}`}
                </Text>
              ) : undefined
            }
            keyExtractor={(s) => s.id}
            renderItem={({ item: s }) => (
              <Link href={{ pathname: "/series/[id]", params: { id: s.id } }} asChild>
                <Row
                  title={s.title}
                  subtitle={[
                    churchName(lib, s.churchId),
                    s.speakerIds.map((id) => speakerName(lib, id)).join(", "),
                    `${countLabel(s.sermons.length, "sermon")} · ${formatYearRange(s.startDate, s.endDate)}`,
                  ].join("\n")}
                />
              </Link>
            )}
          />
        </>
      )}
    </LibraryGate>
  );
}
