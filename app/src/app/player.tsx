import { Ionicons, MaterialCommunityIcons } from "@expo/vector-icons";
import Slider from "@react-native-community/slider";
import { router } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, Image, Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { useLibraryState } from "@/data/LibraryProvider";
import { churchName, neighbours, speakerName } from "@/data/selectors";
import { formatClock, formatDate } from "@/format";
import { usePlayer, usePlayerStatus } from "@/player/PlayerProvider";

/** Full-screen player (modal). */
export default function PlayerScreen() {
  const lib = useLibraryState();
  const { current, rate, toggle, seekBy, seekTo, next, previous, cycleRate } = usePlayer();
  const status = usePlayerStatus();
  const [scrub, setScrub] = useState<number | null>(null); // position while dragging the slider

  if (!current || lib.status !== "ready") {
    return (
      <View style={styles.center}>
        <Text>Nothing playing.</Text>
      </View>
    );
  }
  const { series, sermon } = current;
  const { position, prev, next: nextSermon } = neighbours(series, sermon.id);
  const duration = status.duration || sermon.durationSeconds || 0;
  const time = scrub ?? status.currentTime;

  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Pressable onPress={() => router.back()} hitSlop={16} style={styles.close} accessibilityLabel="Close player">
        <Ionicons name="chevron-down" size={28} />
      </Pressable>

      {series.artworkUrl ? <Image source={{ uri: series.artworkUrl }} style={styles.art} /> : null}

      <Text style={styles.series}>
        {series.title} · Part {position} of {series.sermons.length}
      </Text>
      <Text style={styles.title}>{sermon.title}</Text>
      <Text style={styles.meta}>
        {[sermon.passage?.display, speakerName(lib.library, sermon.speakerId), formatDate(sermon.date)]
          .filter(Boolean)
          .join(" · ")}
      </Text>

      <Slider
        style={styles.slider}
        minimumValue={0}
        maximumValue={Math.max(duration, 1)}
        value={time}
        disabled={!status.isLoaded}
        onSlidingStart={setScrub}
        onValueChange={(v) => scrub !== null && setScrub(v)}
        onSlidingComplete={(v) => {
          seekTo(v);
          setScrub(null);
        }}
      />
      <View style={styles.times}>
        <Text style={styles.time}>{formatClock(time)}</Text>
        <Text style={styles.time}>-{formatClock(duration - time)}</Text>
      </View>

      <View style={styles.controls}>
        <Pressable onPress={previous} hitSlop={8} accessibilityLabel={prev ? "Previous sermon" : "Restart"}>
          <Ionicons name="play-skip-back" size={28} />
        </Pressable>
        <Pressable onPress={() => seekBy(-15)} hitSlop={8} accessibilityLabel="Back 15 seconds">
          <MaterialCommunityIcons name="rewind-15" size={36} />
        </Pressable>
        <Pressable onPress={toggle} accessibilityLabel={status.playing ? "Pause" : "Play"}>
          {status.isBuffering && status.playing ? (
            <ActivityIndicator size="large" style={{ width: 72, height: 72 }} />
          ) : (
            <Ionicons name={status.playing ? "pause-circle" : "play-circle"} size={72} color="#007aff" />
          )}
        </Pressable>
        <Pressable onPress={() => seekBy(30)} hitSlop={8} accessibilityLabel="Forward 30 seconds">
          <MaterialCommunityIcons name="fast-forward-30" size={36} />
        </Pressable>
        <Pressable
          onPress={next}
          disabled={!nextSermon}
          hitSlop={8}
          accessibilityLabel="Next sermon"
          style={{ opacity: nextSermon ? 1 : 0.3 }}
        >
          <Ionicons name="play-skip-forward" size={28} />
        </Pressable>
      </View>

      <Pressable onPress={cycleRate} style={styles.rate} accessibilityLabel="Playback speed">
        <Text style={styles.rateText}>{rate}×</Text>
      </Pressable>

      {status.error ? <Text style={styles.error}>Couldn’t play this sermon: {status.error}</Text> : null}

      {nextSermon ? <Text style={styles.upNext}>Up next: {nextSermon.title}</Text> : null}

      {/* Attribution: we link to the church's own hosting (root CLAUDE.md rule 7). */}
      {sermon.sourceUrl ? (
        <Pressable onPress={() => Linking.openURL(sermon.sourceUrl!)}>
          <Text style={styles.source}>From {churchName(lib.library, series.churchId)} ↗</Text>
        </Pressable>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  page: { padding: 24, paddingTop: 12, alignItems: "center", gap: 8 },
  close: { alignSelf: "flex-start" },
  art: { width: 260, height: 260, borderRadius: 12, backgroundColor: "#ddd", marginVertical: 16 },
  series: { fontSize: 14, color: "#666", textAlign: "center" },
  title: { fontSize: 22, fontWeight: "600", textAlign: "center" },
  meta: { fontSize: 14, color: "#666", textAlign: "center" },
  slider: { alignSelf: "stretch", marginTop: 16 },
  times: { alignSelf: "stretch", flexDirection: "row", justifyContent: "space-between" },
  time: { fontSize: 12, color: "#666", fontVariant: ["tabular-nums"] },
  controls: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", alignSelf: "stretch", marginTop: 8 },
  rate: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 14, backgroundColor: "#eee", marginTop: 8 },
  rateText: { fontWeight: "600", fontVariant: ["tabular-nums"] },
  error: { color: "#c00", textAlign: "center" },
  upNext: { fontSize: 13, color: "#666", marginTop: 16, textAlign: "center" },
  source: { fontSize: 13, color: "#007aff", marginTop: 8 },
});
