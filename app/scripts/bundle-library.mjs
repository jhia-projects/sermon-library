// Copy a pipeline build into the app, so it ships inside the binary and nothing is fetched at launch.
//   npm run bundle-library              ../pipeline/out/library.json -> src/data/library.bundled.json
//   npm run bundle-library -- <path>    a different build
//   postinstall runs it with --if-missing: it keeps an existing bundled file (an EAS build uploads it
//   via ../.easignore), otherwise falls back to the pipeline build, then to the schema example, so a
//   fresh checkout and CI always have a file for Metro and tsc to import.
// The bundled file is gitignored: library data is never committed (root .gitignore).
import { copyFile, readFile, access } from "node:fs/promises";
import { resolve } from "node:path";

const SUPPORTED_MAJOR = 1; // keep in step with SUPPORTED_MAJOR_VERSIONS in src/data/library.ts
const target = resolve("src/data/library.bundled.json");
const args = process.argv.slice(2);
const ifMissing = args.includes("--if-missing");
const explicit = args.find((a) => !a.startsWith("--"));

const exists = (p) => access(p).then(() => true, () => false);

if (ifMissing && (await exists(target))) {
  console.log(`bundle-library: keeping existing ${target}`);
  process.exit(0);
}

const pipelineBuild = resolve("../pipeline/out/library.json");
const example = resolve("../schema/library.example.json");
const source = explicit ? resolve(explicit) : (await exists(pipelineBuild)) ? pipelineBuild : ifMissing ? example : null;
if (!source) {
  console.error(`bundle-library: ${pipelineBuild} not found. Run the pipeline build first, or pass a path.`);
  process.exit(1);
}

const lib = JSON.parse(await readFile(source, "utf8"));
const major = Number(String(lib.schemaVersion).split(".")[0]);
if (major !== SUPPORTED_MAJOR || !Array.isArray(lib.series)) {
  console.error(`bundle-library: ${source} has schemaVersion ${lib.schemaVersion}; this app reads ${SUPPORTED_MAJOR}.x`);
  process.exit(1);
}
await copyFile(source, target);
const sermons = lib.series.reduce((n, s) => n + s.sermons.length, 0);
console.log(`bundle-library: ${source} -> ${target} (${lib.series.length} series, ${sermons} sermons)`);
