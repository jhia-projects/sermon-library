import { ActivityIndicator, Button, StyleSheet, Text, View } from "react-native";

import { useLibraryState } from "@/data/LibraryProvider";

import type { Library } from "@/types/library";
import type { ReactNode } from "react";

/** Renders children only once library.json has loaded; handles loading and error states. */
export function LibraryGate({ children }: { children: (lib: Library) => ReactNode }) {
  const state = useLibraryState();
  if (state.status === "ready") return <>{children(state.library)}</>;
  return (
    <View style={styles.center}>
      {state.status === "loading" ? (
        <ActivityIndicator />
      ) : (
        <>
          <Text style={styles.error}>{state.error.message}</Text>
          <Button title="Try again" onPress={state.retry} />
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24, gap: 12 },
  error: { textAlign: "center" },
});
