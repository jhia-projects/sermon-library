import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import { ActivityIndicator, Image, Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { usePlayer, usePlayerStatus } from "@/player/PlayerProvider";

/**
 * The bar shown while a sermon is loaded: above the tab bar on tab screens, at the bottom elsewhere
 * (`bottomInset`). Tap opens the full player.
 */
export function MiniPlayer({ bottomInset = false }: { bottomInset?: boolean }) {
  const { current, progress, toggle } = usePlayer();
  const status = usePlayerStatus();
  const insets = useSafeAreaInsets();
  if (!current) return null;

  const { series, sermon } = current;
  const saved = progress[sermon.id];
  const loaded = status.duration > 0;
  const fraction = loaded
    ? status.currentTime / status.duration
    : saved && saved.duration > 0
      ? saved.position / saved.duration
      : 0;

  return (
    <View style={[styles.wrap, bottomInset && { paddingBottom: insets.bottom }]}>
      <View style={[styles.track]}>
        <View style={[styles.fill, { width: `${Math.min(100, fraction * 100)}%` }]} />
      </View>
      <Pressable style={styles.row} onPress={() => router.push("/player")} accessibilityLabel="Open player">
        {series.artworkUrl ? <Image source={{ uri: series.artworkUrl }} style={styles.art} /> : null}
        <View style={styles.text}>
          <Text numberOfLines={1} style={styles.title}>
            {sermon.title}
          </Text>
          <Text numberOfLines={1} style={styles.subtitle}>
            {series.title}
          </Text>
        </View>
        <Pressable onPress={toggle} hitSlop={12} accessibilityLabel={status.playing ? "Pause" : "Play"}>
          {status.isBuffering && status.playing ? (
            <ActivityIndicator style={styles.icon} />
          ) : (
            <Ionicons name={status.playing ? "pause" : "play"} size={28} style={styles.icon} />
          )}
        </Pressable>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { backgroundColor: "#fafafa", borderTopWidth: StyleSheet.hairlineWidth, borderColor: "#ccc" },
  track: { height: 2, backgroundColor: "#e5e5e5" },
  fill: { height: 2, backgroundColor: "#007aff" },
  row: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, paddingVertical: 8, gap: 10 },
  art: { width: 40, height: 40, borderRadius: 4, backgroundColor: "#ddd" },
  text: { flex: 1 },
  title: { fontSize: 15, fontWeight: "500" },
  subtitle: { fontSize: 13, color: "#666" },
  icon: { width: 32, textAlign: "center" },
});
