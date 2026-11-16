/** On-device persistence for playback. Failures are swallowed: losing progress must never break playback. */
import AsyncStorage from "@react-native-async-storage/async-storage";

import type { SermonProgress } from "./rules";

const PROGRESS = "progress:v1:"; // + sermon.id
const LAST_PLAYED = "lastPlayed:v1";

export interface LastPlayed {
  seriesId: string;
  sermonId: string;
}

export async function loadAllProgress(): Promise<Record<string, SermonProgress>> {
  try {
    const keys = (await AsyncStorage.getAllKeys()).filter((k) => k.startsWith(PROGRESS));
    const out: Record<string, SermonProgress> = {};
    for (const [k, v] of await AsyncStorage.multiGet(keys)) if (v) out[k.slice(PROGRESS.length)] = JSON.parse(v);
    return out;
  } catch {
    return {};
  }
}

export async function saveProgress(sermonId: string, p: SermonProgress): Promise<void> {
  await AsyncStorage.setItem(PROGRESS + sermonId, JSON.stringify(p)).catch(() => {});
}

export async function loadLastPlayed(): Promise<LastPlayed | undefined> {
  try {
    const v = await AsyncStorage.getItem(LAST_PLAYED);
    return v ? (JSON.parse(v) as LastPlayed) : undefined;
  } catch {
    return undefined;
  }
}

export async function saveLastPlayed(v: LastPlayed): Promise<void> {
  await AsyncStorage.setItem(LAST_PLAYED, JSON.stringify(v)).catch(() => {});
}
