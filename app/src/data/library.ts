import exampleLibrary from "../../../schema/library.example.json";

import type { Library } from "@/types/library";

/** Major versions of library.json this build can read (root CLAUDE.md rule 2). */
export const SUPPORTED_MAJOR_VERSIONS = [1] as const;

export class UnsupportedLibraryError extends Error {}

export function checkVersion(lib: Library): Library {
  const major = Number(lib.schemaVersion.split(".")[0]);
  if (!(SUPPORTED_MAJOR_VERSIONS as readonly number[]).includes(major)) {
    throw new UnsupportedLibraryError(
      `library.json schemaVersion ${lib.schemaVersion} is not supported; update the app`,
    );
  }
  return lib;
}

/**
 * Fetch the published library. With no EXPO_PUBLIC_LIBRARY_URL (development), use the bundled
 * example so screens can be built before the pipeline publishes anywhere.
 * TODO: cache the last good copy on device for offline use and ETag revalidation.
 */
export async function loadLibrary(url = process.env.EXPO_PUBLIC_LIBRARY_URL): Promise<Library> {
  if (!url) return checkVersion(exampleLibrary as Library);
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`library.json: HTTP ${res.status}`);
  return checkVersion((await res.json()) as Library);
}
