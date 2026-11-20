import { Pressable, StyleSheet, Text, View, type PressableProps } from "react-native";

import type { ComponentRef, ReactNode, Ref } from "react";

type Props = PressableProps & {
  title: string;
  subtitle?: string;
  /** Trailing control (e.g. a download button); it handles its own presses. */
  accessory?: ReactNode;
  /** React 19 passes ref as a prop; <Link asChild> needs it. */
  ref?: Ref<ComponentRef<typeof Pressable>>;
};

/** Plain list row. Placeholder styling until the app design phase. */
export function Row({ title, subtitle, accessory, ...pressable }: Props) {
  return (
    <Pressable {...pressable}>
      {/* Styles live on the inner View: <Link asChild> drops a function-valued Pressable style. */}
      {({ pressed }) => (
        <View style={[styles.row, pressed && styles.pressed]}>
          <View style={styles.text}>
            <Text style={styles.title}>{title}</Text>
            {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
          </View>
          {accessory}
        </View>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: "#ccc" },
  pressed: { opacity: 0.6 },
  text: { flex: 1 },
  title: { fontSize: 16, fontWeight: "500" },
  subtitle: { fontSize: 13, color: "#666", marginTop: 2 },
});
