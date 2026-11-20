import { Stack, useLocalSearchParams } from "expo-router";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import { LibraryGate } from "@/components/LibraryGate";
import { Row } from "@/components/Row";
import { bookName } from "@/data/books";
import { findSeries, isInSeriesBook, speakerName } from "@/data/selectors";
import { countLabel, formatDate, formatMinutes } from "@/format";
import { usePlayer } from "@/player/PlayerProvider";
import { continueTarget, isPlayable, type SermonProgress } from "@/player/rules";
import type { Sermon } from "@/types/library";

/**
 * A series' sermons in preached order (the array order IS the order; see root CLAUDE.md rule 10).
 * "Part N" is derived from the index for display only. Never persist it: key state on sermon.id.
 * Tap a sermon to play it; playback then carries on through the series in order.
 * TODO: favourites.
 */
export default function SeriesScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { current, progress, play } = usePlayer();
  return (
    <LibraryGate>
      {(lib) => {
        const series = findSeries(lib, id);
        if (!series) return <Text style={{ padding: 16 }}>This series is no longer available.</Text>;
        const target = continueTarget(series, progress);
        const started = series.sermons.some((m) => progress[m.id]);
        const targetPart = target ? series.sermons.indexOf(target) + 1 : 0;
        return (
          <>
            <Stack.Screen options={{ title: series.title }} />
            <FlatList
              contentInsetAdjustmentBehavior="automatic"
              data={series.sermons}
              keyExtractor={(m) => m.id}
              extraData={[current?.sermon.id, progress]}
              ListHeaderComponent={
                <View style={styles.header}>
                  <Text style={styles.meta}>
                    {bookName(series.book)} · {countLabel(series.sermons.length, "sermon")}
                    {series.isComplete === false ? " · in progress" : ""}
                  </Text>
                  {target ? (
                    <Pressable style={styles.button} onPress={() => play(series, target)}>
                      <Text style={styles.buttonText}>
                        {started ? `▶ Continue: Part ${targetPart}` : "▶ Play from the start"}
                      </Text>
                    </Pressable>
                  ) : null}
                </View>
              }
              renderItem={({ item: m, index }) => {
                const playing = current?.sermon.id === m.id;
                return (
                  <Row
                    title={`${playing ? "♪ " : ""}${index + 1}. ${m.title}`}
                    subtitle={[
                      m.passage?.display ?? "No passage listed",
                      isInSeriesBook(series, m) || !m.passage ? null : "interlude",
                      speakerName(lib, m.speakerId),
                      formatDate(m.date),
                      listenState(m, progress[m.id]),
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                    disabled={!isPlayable(m)}
                    onPress={() => play(series, m)}
                    accessibilityHint="Plays this sermon"
                  />
                );
              }}
            />
          </>
        );
      }}
    </LibraryGate>
  );
}

function listenState(m: Sermon, p: SermonProgress | undefined): string | null {
  if (!isPlayable(m)) return "no audio";
  if (p?.finished) return "played ✓";
  if (p && p.position > 0 && p.duration > 0) return `${formatMinutes(p.duration - p.position)} left`;
  return m.durationSeconds ? formatMinutes(m.durationSeconds) : null;
}

const styles = StyleSheet.create({
  header: { padding: 16, gap: 12 },
  meta: { color: "#666" },
  button: { alignSelf: "flex-start", backgroundColor: "#007aff", paddingHorizontal: 16, paddingVertical: 10, borderRadius: 20 },
  buttonText: { color: "white", fontWeight: "600" },
});
