import { Stack, useLocalSearchParams } from "expo-router";
import { Text } from "react-native";

import { BookList } from "@/components/BookList";
import { LibraryGate } from "@/components/LibraryGate";
import { speakerName } from "@/data/selectors";

/** Books this speaker has preached a series in. */
export default function SpeakerScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return (
    <LibraryGate>
      {(lib) =>
        !lib.speakers.some((x) => x.id === id) ? (
          // A stale link or saved id: this speaker is no longer in the library.
          <Text style={{ padding: 16 }}>
            This speaker is no longer available.
          </Text>
        ) : (
          <>
            <Stack.Screen options={{ title: speakerName(lib, id) }} />
            <BookList lib={lib} filter={{ speakerId: id }} />
          </>
        )
      }
    </LibraryGate>
  );
}
