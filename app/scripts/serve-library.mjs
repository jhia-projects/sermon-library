// Dev only: serve a locally built library.json so the app loads real data the same way it will
// load the published file (fetch from EXPO_PUBLIC_LIBRARY_URL).
//   node scripts/serve-library.mjs [path]   default: ../pipeline/out/library.json
// Plain HTTP is fine here: this never ships, and the simulator reaches it on localhost.
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { networkInterfaces } from "node:os";
import { resolve } from "node:path";

const file = resolve(process.argv[2] ?? "../pipeline/out/library.json");
const port = Number(process.env.PORT ?? 8787);

createServer(async (req, res) => {
  if (req.url !== "/library.json") return res.writeHead(404).end();
  try {
    // Read per request, so a fresh pipeline build shows up on the app's next reload.
    const body = await readFile(file);
    res.writeHead(200, { "Content-Type": "application/json", "Cache-Control": "no-store" }).end(body);
  } catch (e) {
    res.writeHead(500).end(String(e));
  }
}).listen(port, () => {
  const lan = Object.values(networkInterfaces()).flat().find((i) => i?.family === "IPv4" && !i.internal)?.address;
  console.log(`Serving ${file}`);
  console.log(`  simulator: http://localhost:${port}/library.json`);
  if (lan) console.log(`  phone:     http://${lan}:${port}/library.json`);
});
