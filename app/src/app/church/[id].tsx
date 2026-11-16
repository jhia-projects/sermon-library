import { Stack, useLocalSearchParams } from "expo-router";
import { Text } from "react-native";

import { BookList } from "@/components/BookList";
import { LibraryGate } from "@/components/LibraryGate";
import { churchName } from "@/data/selectors";

/** Books this church has a series through. TODO: link to the church's website (attribution). */
export default function ChurchScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return (
    <LibraryGate>
      {(lib) =>
        !lib.churches.some((x) => x.id === id) ? (
          // A stale link or saved id: this church is no longer in the library.
          <Text style={{ padding: 16 }}>
            This church is no longer available.
          </Text>
        ) : (
          <>
            <Stack.Screen options={{ title: churchName(lib, id) }} />
            <BookList lib={lib} filter={{ churchId: id }} />
          </>
        )
      }
    </LibraryGate>
  );
}
