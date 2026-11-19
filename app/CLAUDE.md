# App (Expo + React Native + TypeScript)

Reads `library.json` (contract: `../schema/library.schema.json`) and lets people browse book series and play them in order.

## Layout
```
src/app/            expo-router routes (file = screen)
  (tabs)/           Books (index), Speakers, Churches
  book/[code].tsx   every series through one book (OSIS code)
  series/[id].tsx   one series' sermons in preached order; tap to play
  player.tsx        full-screen player (modal)
src/player/         playback: PlayerProvider (one expo-audio player), rules.ts (pure, tested), storage.ts
src/data/           loading + pure selectors (no React in selectors.ts)
src/types/library.ts hand-mirrored schema types: change the schema first, then this
src/components/     shared UI (placeholder styling until the design phase)
src/__tests__/      jest (jest-expo), runs against ../schema/library.example.json
```
`../schema/books.json` and `../schema/library.example.json` are imported directly (Metro watches `../schema`, see `metro.config.js`).

## Rules
- **Play `series.sermons` in array order.** It is preached order. Derive "Part N", prev/next from the index at render time; **never store an index**. Favourites, progress and resume key on `sermon.id` / `series.id` (they are permanent; positions shift when backfill inserts sermons).
- `passage` is optional, and `passage.book` can differ from `series.book` (an interlude). Use `isInSeriesBook` rather than assuming.
- Dates are `YYYY-MM-DD` with no time zone: format by splitting the string, don't `new Date()` them (UTC shifts the day).
- Check `schemaVersion` major before using a library (`checkVersion`). After release, the app must read both majors during a breaking change (root rule 2).
- Link, don't rehost: play the church's `audioUrl`/`videoUrl`/YouTube; show attribution (`sourceUrl`, church `websiteUrl`).
- Every scrolling list sets `contentInsetAdjustmentBehavior="automatic"`: the iOS header is translucent, and without it content starts underneath it.
- Keep screens thin: queries go in `src/data/selectors.ts` with a test.

## Commands
```bash
npm install --legacy-peer-deps   # Node version: .nvmrc
npx expo install --fix   # align native module versions with the Expo SDK
npm start                # Expo dev server (i = iOS simulator, a = Android)
npm run typecheck && npm run lint && npm test
```
The app ships `src/data/library.bundled.json` (gitignored; private, nothing fetched at launch). `npm run bundle-library` copies `../pipeline/out/library.json` there; `postinstall` creates it if missing (pipeline build, else the schema example). Rebuild the app to update it. Set `EXPO_PUBLIC_LIBRARY_URL` (see `.env.example`) to fetch a library instead (development).

## iOS build (private, ad hoc / EAS internal distribution)
Personal use only: installed from a link on registered devices; not on TestFlight or the App Store.
```bash
npx eas-cli device:create         # once per iPhone: register its UDID (before building)
npm run bundle-library            # after a pipeline build
npx eas-cli build -p ios --profile personal
```
Open the build's install link on the iPhone (Developer Mode must be on: Settings → Privacy & Security). A build runs only on devices registered when it was built; register a new phone, then rebuild. The provisioning profile lasts about a year.
EAS uploads per `../.easignore` (not .gitignore), which is how the bundled library reaches the cloud build.

## Playback
- One player for the app (`PlayerProvider`). `usePlayer()` = what's playing, saved progress, actions; `usePlayerStatus()` = live position (2×/s). Only read the status context where live position is shown, so lists don't re-render while audio plays.
- Progress is saved per `sermon.id` in AsyncStorage (`progress:v1:<id>`); resume backs off 3 s; "finished" is sticky and means within the last 30 s. The last-played sermon is restored (paused) on launch.
- At the end of a sermon, playback advances to the next sermon **with audio** in array order (`adjacentPlayable`).
- Lock-screen controls are seek −15/+30 (expo-audio has no remote next/previous for a single player). Background audio and lock-screen controls need a dev build (`npx expo run:ios`); Expo Go only covers foreground playback.

## Not built yet
Favourites, hosted library.json with on-device cache, downloads for offline listening, YouTube/video playback, search, design system.
