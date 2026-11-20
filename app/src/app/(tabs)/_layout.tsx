import { MaterialCommunityIcons } from "@expo/vector-icons";
import { Tabs } from "expo-router";
import type { ColorValue } from "react-native";
import { BottomTabBar } from "expo-router/tabs";

import { MiniPlayer } from "@/components/MiniPlayer";

type IconName = keyof typeof MaterialCommunityIcons.glyphMap;

function TabIcon({ name, color, size }: { name: IconName; color: ColorValue; size: number }) {
  return <MaterialCommunityIcons name={name} color={color as string} size={size} />;
}

export default function TabsLayout() {
  return (
    <Tabs
      tabBar={(props) => (
        <>
          <MiniPlayer />
          <BottomTabBar {...props} />
        </>
      )}
    >
      <Tabs.Screen name="index" options={{ title: "Books", tabBarIcon: (p) => <TabIcon name="book-open-variant" {...p} /> }} />
      <Tabs.Screen name="speakers" options={{ title: "Speakers", tabBarIcon: (p) => <TabIcon name="account-voice" {...p} /> }} />
      <Tabs.Screen name="churches" options={{ title: "Churches", tabBarIcon: (p) => <TabIcon name="church" {...p} /> }} />
    </Tabs>
  );
}
