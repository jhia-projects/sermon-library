/**
 * Downloaded audio on the device: files in <documents>/audio/, metadata in AsyncStorage (download:v1:<sermon.id>).
 * The documents directory isn't cleared by iOS when storage runs low, so a download is there when you go underground.
 * Metadata is written only after a file is complete, so a half-finished download is never played.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Directory, File, Paths } from "expo-file-system";

import type { DownloadMeta } from "./rules";

const META = "download:v1:"; // + sermon.id
const PARTIAL = ".part";

export const audioDir = () => new Directory(Paths.document, "audio");
export const audioFile = (fileName: string) => new File(audioDir(), fileName);
export const partialFile = (fileName: string) => new File(audioDir(), fileName + PARTIAL);

/** Load metadata, dropping entries whose file is gone and deleting files nothing refers to (e.g. interrupted downloads). */
export async function loadDownloads(): Promise<Record<string, DownloadMeta>> {
  try {
    const dir = audioDir();
    dir.create({ idempotent: true, intermediates: true });
    const keys = (await AsyncStorage.getAllKeys()).filter((k) => k.startsWith(META));
    const out: Record<string, DownloadMeta> = {};
    const stale: string[] = [];
    for (const [k, v] of await AsyncStorage.multiGet(keys)) {
      const meta = v ? (JSON.parse(v) as DownloadMeta) : undefined;
      if (meta && audioFile(meta.fileName).exists) out[k.slice(META.length)] = meta;
      else stale.push(k);
    }
    if (stale.length) await AsyncStorage.multiRemove(stale);
    const known = new Set(Object.values(out).map((m) => m.fileName));
    for (const entry of dir.list()) {
      if (entry instanceof File && !known.has(entry.name)) entry.delete();
    }
    return out;
  } catch {
    return {};
  }
}

export async function saveDownload(sermonId: string, meta: DownloadMeta): Promise<void> {
  await AsyncStorage.setItem(META + sermonId, JSON.stringify(meta)).catch(() => {});
}

export async function removeDownload(sermonId: string, meta: DownloadMeta | undefined): Promise<void> {
  try {
    if (meta) {
      const f = audioFile(meta.fileName);
      if (f.exists) f.delete();
    }
  } catch {
    // a missing file is already removed
  }
  await AsyncStorage.removeItem(META + sermonId).catch(() => {});
}
