import { MaterialCommunityIcons } from "@expo/vector-icons";
import { Alert, Pressable, StyleSheet, Text } from "react-native";

import { useDownloadActions, useDownloads } from "@/downloads/DownloadsProvider";
import { formatBytes, seriesDownloadCount } from "@/downloads/rules";
import { isPlayable } from "@/player/rules";
import type { Series, Sermon } from "@/types/library";

const TINT = "#007aff";

/** Per-sermon download control: download, progress (tap to cancel), retry, or downloaded (tap to remove). */
export function DownloadButton({ series, sermon }: { series: Series; sermon: Sermon }) {
  const { done, active } = useDownloads();
  const { download, cancel, remove } = useDownloadActions();
  if (!isPlayable(sermon)) return null;

  const meta = done[sermon.id];
  const a = active[sermon.id];
  let label: string;
  let onPress: () => void;
  let content;
  if (meta) {
    label = "Downloaded. Remove download";
    onPress = () =>
      Alert.alert("Remove download?", `${sermon.title} (${formatBytes(meta.bytes)})`, [
        { text: "Cancel", style: "cancel" },
        { text: "Remove", style: "destructive", onPress: () => remove(sermon.id) },
      ]);
    content = <MaterialCommunityIcons name="check-circle" size={22} color={TINT} />;
  } else if (a?.status === "downloading") {
    label = "Downloading. Cancel";
    onPress = () => cancel(sermon.id);
    content = <Text style={styles.percent}>{Math.round(a.fraction * 100)}%</Text>;
  } else if (a?.status === "queued") {
    label = "Waiting to download. Cancel";
    onPress = () => cancel(sermon.id);
    content = <MaterialCommunityIcons name="clock-outline" size={22} color="#888" />;
  } else if (a?.status === "failed") {
    label = "Download failed. Retry";
    onPress = () => download(series, sermon);
    content = <MaterialCommunityIcons name="alert-circle-outline" size={22} color="#d33" />;
  } else {
    label = "Download for offline listening";
    onPress = () => download(series, sermon);
    content = <MaterialCommunityIcons name="download-outline" size={22} color={TINT} />;
  }
  return (
    <Pressable onPress={onPress} hitSlop={12} style={styles.button} accessibilityRole="button" accessibilityLabel={label}>
      {content}
    </Pressable>
  );
}

/** Series header control: download every sermon with audio, or remove them all. */
export function SeriesDownloadButton({ series }: { series: Series }) {
  const { done, active } = useDownloads();
  const { downloadSeries, cancelSeries, removeSeries } = useDownloadActions();
  const { done: n, total } = seriesDownloadCount(series, (id) => Boolean(done[id]));
  if (total === 0) return null;
  const busy = series.sermons.some((m) => active[m.id] && active[m.id]!.status !== "failed");
  const bytes = series.sermons.reduce((sum, m) => sum + (done[m.id]?.bytes ?? 0), 0);

  if (n === total) {
    return (
      <Pressable
        onPress={() =>
          Alert.alert("Remove downloads?", `${n} sermons (${formatBytes(bytes)}) from this series.`, [
            { text: "Cancel", style: "cancel" },
            { text: "Remove", style: "destructive", onPress: () => removeSeries(series) },
          ])
        }
      >
        <Text style={styles.link}>✓ Downloaded ({formatBytes(bytes)}) · Remove</Text>
      </Pressable>
    );
  }
  if (busy) {
    return (
      <Pressable onPress={() => cancelSeries(series)}>
        <Text style={styles.link}>Downloading {n} of {total}… · Cancel</Text>
      </Pressable>
    );
  }
  return (
    <Pressable onPress={() => downloadSeries(series)}>
      <Text style={styles.link}>
        ⬇ Download series{n > 0 ? ` (${total - n} more)` : ""}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: { width: 40, alignItems: "center", justifyContent: "center" },
  percent: { fontSize: 12, color: TINT, fontVariant: ["tabular-nums"] },
  link: { color: TINT, fontWeight: "500" },
});
