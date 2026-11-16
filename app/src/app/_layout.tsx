import { Stack, useSegments } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { MiniPlayer } from "@/components/MiniPlayer";
import { LibraryProvider } from "@/data/LibraryProvider";
import { PlayerProvider } from "@/player/PlayerProvider";

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <LibraryProvider>
        <PlayerProvider>
          <RootStack />
          <StatusBar style="auto" />
        </PlayerProvider>
      </LibraryProvider>
    </SafeAreaProvider>
  );
}

function RootStack() {
  // Tab screens draw the mini player above their tab bar (see (tabs)/_layout.tsx); pushed screens get it here.
  const top = useSegments()[0];
  const bottomBar = top !== "(tabs)" && top !== "player";
  return (
    <View style={{ flex: 1 }}>
      <View style={{ flex: 1 }}>
        <Stack screenOptions={{ headerBackButtonDisplayMode: "minimal" }}>
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen name="speaker/[id]" options={{ title: "" }} />
          <Stack.Screen name="church/[id]" options={{ title: "" }} />
          <Stack.Screen name="book/[code]" options={{ title: "" }} />
          <Stack.Screen name="series/[id]" options={{ title: "" }} />
          <Stack.Screen name="player" options={{ presentation: "modal", headerShown: false }} />
        </Stack>
      </View>
      {bottomBar ? <MiniPlayer bottomInset /> : null}
    </View>
  );
}
