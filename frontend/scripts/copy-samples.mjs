// Copies the committed sample runs into public/samples so the UI works without the API.
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const out = join(root, "frontend", "public", "samples");
mkdirSync(out, { recursive: true });

const files = [
  ["runs/sample_mission/run.json", "sample_mission.json"],
  ["runs/decoy_storm/run.json", "decoy_storm.json"],
  ["runs/hand_drawn/run.json", "hand_drawn.json"],
  ["runs/benchmark.json", "benchmark.json"],
];
for (const [src, dest] of files) {
  const from = join(root, src);
  if (!existsSync(from)) {
    console.warn(`skip ${src} (not generated yet; run the backend CLI first)`);
    continue;
  }
  copyFileSync(from, join(out, dest));
}
console.log(`samples -> ${out}`);
