/**
 * model-resources.mjs - the Brain Model pane's "Loaded now / Resources" plate
 * and the COMPUTE panel's corrected lane/card words (owner's ask 2026-11-08).
 *
 *     node tests/model-resources.mjs
 *
 * TWO HALVES, both needed:
 *
 *   1. The words are pure functions (`src/model-resources.js`), so every honest
 *      state - the pooled three-card lane loaded at 0 spill, a spilled load, a
 *      lane that is not running, nothing loaded at all, a driver that does not
 *      report per-program video memory, an unreadable Jarvis process - is
 *      proved here with no browser, no GPU and no backend.
 *
 *   2. The wiring is pinned by reading the REAL files: `brain.js` must import
 *      the module, ask for the `model_resources` section, draw it in the Model
 *      pane and pass it to the COMPUTE panel; `brain.html` must have the card;
 *      the Rust Brain read allowlist must map the section to the one route; and
 *      the backend must serve that route as a GET on the already-installed
 *      PC-only wrapper. A pure function that is right and a panel that never
 *      calls it are the same thing to the owner.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import * as R from "../src/model-resources.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const RUST = join(HERE, "..", "src-tauri", "src");

const ZERO_SPILL = {
  available: true,
  read_at: 1_760_000_000,
  read_at_words: "21:52:03",
  active_lane: {
    url: "http://127.0.0.1:11450",
    preset: "coding",
    preset_title: "Coding",
    fallback: false,
    words: 'Chat is using the "Coding" preset\'s lane: the Coding preset\'s lane (all three cards).',
  },
  lanes: [
    {
      key: "main", label: "the everyday lane", state: "not_loaded", loaded: false,
      model: null, context_length: null, gpu_indices: [], words: "nothing loaded",
    },
    {
      key: "coding", label: "the Fast preset's lane", state: "unreachable",
      loaded: false, model: null, gpu_indices: [],
      words: "not running - nothing answers on port 11435",
    },
    {
      key: "pooled", label: "the Coding preset's lane (all three cards)",
      state: "loaded", loaded: true,
      model: "qwen3-coder-30b-a3b-ud-q3-k-xl:latest",
      context_length: 8192, size_bytes: 14_497_590_799,
      size_vram_bytes: 14_497_590_799, spill_bytes: 0, on_card_percent: 100,
      gpu_indices: [0, 1, 2],
    },
  ],
  gpus: [
    { index: 0, name: "NVIDIA GeForce RTX 2060", total_mb: 12288, used_mb: 6064,
      free_mb: 6224, jarvis_mb: null, other_mb: null },
    { index: 1, name: "NVIDIA GeForce RTX 2080 SUPER", total_mb: 8192, used_mb: 4131,
      free_mb: 4061, jarvis_mb: null, other_mb: null },
    { index: 2, name: "NVIDIA GeForce RTX 2080 SUPER", total_mb: 8192, used_mb: 5463,
      free_mb: 2729, jarvis_mb: null, other_mb: null },
  ],
  gpu_share: { known: false,
    why: "the graphics driver does not report how much video memory each program is using",
    loaded_vram_gib: 13.5, cards: [0, 1, 2] },
  jarvis: {
    available: true, rss_mb: 210.5, private_mb: 195.2, cpu_percent: 3.0,
    model_servers_rss_mb: 4800.0,
  },
  warnings: [],
  notes: ["Read-only: this answer only looked. Nothing was loaded, switched or started."],
  words: ["Loaded now: qwen3-coder-30b-a3b-ud-q3-k-xl on the Coding preset's lane"],
};

let checks = 0;
function ok(what, cond, detail) {
  checks += 1;
  assert.ok(cond, `${what}${detail ? `\n        ${JSON.stringify(detail)}` : ""}`);
}

// ── 1. The words ────────────────────────────────────────────────────────────
ok("three cards are named as the owner's three cards",
  R.cardsWords([2, 1, 0]) === "all three graphics cards (0, 1, 2)", R.cardsWords([2, 1, 0]));
ok("the pooled lane never says 'graphics card 2' as the whole truth",
  !R.cardsWords([0, 1, 2]).includes("graphics card 2"));
ok("one card is named as one card", R.cardsWords([2]) === "graphics card 2");
ok("two cards are named as two", R.cardsWords([0, 1]) === "graphics cards 0 and 1");
ok("no cards is a sentence, not a fake card 0",
  R.cardsWords([]).includes("no graphics card") && R.cardsWords([]) !== "graphics card 0");
ok("context size is thousands-separated",
  R.contextWords(8192) === "8,192 tokens of context", R.contextWords(8192));
ok("an unreported context size says so, never 0 tokens",
  R.contextWords(null) === "the context size was not reported"
  && !R.contextWords(null).includes("0 tokens"));
ok("gigabyte and gibibyte words are not swapped",
  R.gbWords(12288) === "12.0 GB" && R.gibWords(14_497_590_799) === "13.5 GiB");

const loaded = ZERO_SPILL.lanes[2];
const loadedWords = R.loadedLaneWords(loaded);
ok("a loaded lane names the model, the context and all three cards",
  loadedWords.includes("qwen3-coder") && loadedWords.includes("8,192 tokens")
  && loadedWords.includes("all three graphics cards (0, 1, 2)"), loadedWords);
ok("a zero-spill load says nothing spilled",
  loadedWords.includes("100% on the cards") && loadedWords.includes("nothing spilled"),
  loadedWords);
const spilled = R.loadedLaneWords({
  state: "loaded", loaded: true, model: "m:latest", context_length: 16384,
  gpu_indices: [0, 1], on_card_percent: 74, spill_bytes: 3_762_835_946,
});
ok("a spilled load reports the percent and the MiB, not silence",
  spilled.includes("74% on the cards")
  && spilled.includes("3,589 MiB spilled into system RAM"), spilled);
ok("a lane that does not answer says it is not running",
  R.loadedLaneWords({ state: "unreachable", loaded: false })
    === "not running - nothing answers on that lane");
ok("a lane with nothing loaded says nothing loaded, not 0 MB",
  R.loadedLaneWords({ state: "not_loaded", loaded: false }) === "nothing loaded");

const plate = R.plateModel(ZERO_SPILL);
ok("the plate names the read time", plate.readAt === "21:52:03");
ok("the plate shows every lane honestly",
  plate.lanes.length === 3
  && plate.lanes.some((l) => l.state === "unreachable")
  && plate.lanes.some((l) => l.state === "not_loaded")
  && plate.lanes.some((l) => l.state === "loaded"), plate.lanes);
ok("the plate says which cards and how much free memory",
  plate.gpus.length === 3 && plate.gpus[0].includes("6.1 GB free of 12.0 GB"),
  plate.gpus);
ok("a driver that does not report per-program memory is said, not guessed",
  plate.share.some((line) => line.includes("13.5 GiB"))
  && plate.share.some((line) => line.includes("does not report how much of each card")),
  plate.share);
ok("Jarvis's own RAM/CPU words carry the OS numbers",
  plate.jarvis.includes("211 MiB of RAM") && plate.jarvis.includes("3.0% of the processor"),
  plate.jarvis);
ok("Jarvis's model servers' RAM is named too",
  plate.jarvis.includes("4800 MiB more"), plate.jarvis);
ok("an absent answer says why, and invents no row",
  R.plateModel({ available: false, why: "no resources module" }).available === false
  && R.plateModel({ available: false }).lanes.length === 0);
ok("an unreadable Jarvis process is said in words",
  R.jarvisWords({ available: false }).includes("could not be read"),
  R.jarvisWords({ available: false }));
ok("a known per-card share is named per card",
  R.plateModel({ ...ZERO_SPILL,
    gpu_share: { known: true, cards: [0] },
    gpus: [{ index: 0, name: "NVIDIA GeForce RTX 2060", total_mb: 12288,
      used_mb: 6064, free_mb: 6224, jarvis_mb: 5700 }] }).share
      .some((line) => line.includes("Jarvis's models use 5.6 GB")),
  R.plateModel({ ...ZERO_SPILL, gpu_share: { known: true },
    gpus: [{ index: 0, total_mb: 12288, used_mb: 6064, free_mb: 6224,
      jarvis_mb: 5700 }] }).share);
ok("a read time with no words still comes from the epoch",
  R.readTimeWords({ read_at: 1_760_000_000 }) ===
    new Date(1_760_000_000 * 1000).toLocaleTimeString());
ok("no read time at all is empty, not the current clock",
  R.readTimeWords({}) === "");

// The COMPUTE panel, corrected.
const compute = R.computeModel(ZERO_SPILL);
ok("the COMPUTE panel names the loaded model on all three cards",
  compute.loaded.length === 1
  && compute.loaded[0].model.includes("qwen3-coder")
  && compute.loaded[0].cards === "all three graphics cards (0, 1, 2)", compute.loaded);
ok("the COMPUTE panel carries the real context size",
  compute.loaded[0].context === "8,192 tokens of context", compute.loaded);
ok("the COMPUTE panel's card rows come from the same fresh read",
  compute.gpus.length === 3 && compute.readAt === "21:52:03", compute.gpus);
ok("the COMPUTE panel shows the unreachable lane honestly",
  compute.rows.some((row) => row.value.includes("not running")), compute.rows);
ok("a backend with no resources answer draws no invented truth",
  R.computeModel({ available: false }).available === false
  && R.computeModel(null).available === false);

// ── 2. The wiring, pinned in the real files ─────────────────────────────────
const brain = readFileSync(join(SRC, "brain.js"), "utf8");
const html = readFileSync(join(SRC, "brain.html"), "utf8");
const routes = readFileSync(join(RUST, "brain", "routes.rs"), "utf8");
const rec = readFileSync(
  join(HERE, "..", "..", "backend", "jarvis_model_resources.py"), "utf8");
const recModule = readFileSync(
  join(HERE, "..", "..", "backend", "jarvis_model_recommendations.py"), "utf8");

ok("brain.js imports the module", brain.includes('from "./model-resources.js"'));
ok("the Model pane asks for the model_resources read",
  /faculties:\s*\[[^\]]*"model_resources"/.test(brain));
ok("renderResources() exists and is drawn in the Faculties view",
  brain.includes("function renderResources()")
  && /case "faculties":[\s\S]{0,400}renderResources\(\)/.test(brain));
ok("renderResources is wired to the page element",
  /resources:\s*\$\(\s*"resources"\s*\)/.test(brain));
ok("the COMPUTE panel reads the resources answer",
  /function renderCompute\(\)[\s\S]{0,2000}Resources\.computeModel/.test(brain));
ok("the page has the Loaded now / Resources card",
  html.includes('id="resources-card"') && html.includes('id="resources"'));
ok("the Rust Brain allowlist maps the section to the one route",
  routes.includes('("model_resources", "/api/models/resources")'));
ok("the backend serves it as a GET on the already-installed PC-only wrapper",
  recModule.includes('PATH_RESOURCES = "/api/models/resources"')
  && /GET_PATHS\s*=\s*\(PATH_RECOMMENDATIONS,\s*PATH_RESOURCES\)/.test(recModule));
ok("the backend read is the read-only collector, not a second HTTP stack",
  rec.includes("def collect(") && !rec.includes("/api/pull")
  && !rec.includes("requests."));

console.log(`\nok   ${checks} checks passed - the words, the honest states and the wiring`);
