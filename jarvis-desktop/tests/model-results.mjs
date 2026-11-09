/**
 * model-results.mjs - the Brain Model pane's "Measured results" card
 * (2026-11-09): the speed runs and five-suite scorecards ALREADY stored on this
 * PC, from the two stores `docs/JARVIS-API.md` section 205 uses.
 *
 *     node tests/model-results.mjs
 *
 * TWO HALVES, both needed:
 *
 *   1. The words are pure functions (`src/model-results.js`), so every honest
 *      case is proved with no browser and no GPU: a measured run, a spilled
 *      run, a failed run with and without its reason, a skipped suite, a row
 *      with no stored sentence, an empty store with the backend's own reason,
 *      and a backend that does not report results at all. The card must never
 *      invent a number or a score - a missing one stays missing.
 *
 *   2. The wiring is pinned by reading the REAL files: `brain.js` must import
 *      the module, ask for the `model_measured` section, and draw it in the
 *      Model pane; `brain.html` must carry the card with its plain label; the
 *      Rust read allowlist must map the section to the one route; and the
 *      backend must serve it as a GET on the already-installed PC-only wrapper,
 *      reading `jarvis_bench`'s own two stores and nothing else.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import * as R from "../src/model-results.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const RUST = join(HERE, "..", "src-tauri", "src");
const BACKEND = join(HERE, "..", "..", "backend");

let checks = 0;
function ok(what, cond, detail) {
  checks += 1;
  assert.ok(cond, `${what}${detail ? `\n        ${JSON.stringify(detail)}` : ""}`);
}

// A stored answer, shaped exactly like jarvis_model_resources.measured().
const PAYLOAD = {
  available: true,
  read_at: 1_760_000_000,
  read_at_words: "21:52:03",
  runs: [
    {
      kind: "speed run", model: "qwen3.5:9b", lane: "everyday", preset: "general",
      ok: true, spilled: false, at: 1_760_000_000, day: "2026-11-08",
      gen_median: 41.2, prefill_median: 900.5,
      words: "qwen3.5:9b on the everyday lane at 16,384 tokens: 41.2 tokens a "
        + "second decode, 900 tokens a second prompt, 5.4 GiB loaded, all of it "
        + "on the card, promotion-grade.",
    },
    {
      kind: "speed run", model: "qwen3-coder-30b-a3b-ud-q3-k-xl", lane: "pooled",
      ok: true, spilled: true, at: 1_759_000_000, day: "2026-11-07",
      on_card_percent: 74,
      words: "PARTIAL: only 74% of it was in the graphics card, so the rest ran "
        + "on the processor - these numbers are NOT comparable with a fully-on-card run.",
    },
    {
      kind: "speed run", model: "qwen3.5:4b", lane: "coding", ok: false,
      at: 1_758_000_000, day: "2026-11-06", why: "no repeat produced a number",
      words: "Nothing was measured: no repeat produced a number.",
    },
  ],
  scorecards: [
    {
      kind: "scorecard", model: "qwen3.5:9b", suite: "coding",
      suite_label: "Coding", skipped: false, passed: true,
      at: 1_760_000_000, day: "2026-11-08", score_pct: 83.33, items: 6,
      items_passed: 5, decode_tps: 41.2, ctx: 8192, quant: "Q4_K_M",
      words: "5 of 6 coding tasks passed, each checked by running its own test.",
    },
    {
      kind: "scorecard", model: "qwen3.5:4b", suite: "vision_ocr",
      suite_label: "Vision / OCR", skipped: true, at: 1_758_000_000,
      day: "2026-11-06", ctx: 8192,
      words: "Vision / OCR: not run - the model does not report vision.",
    },
  ],
  counts: { runs: 12, scorecards: 7 },
  stores: { speed: { name: "bench.jsonl", exists: true },
            scores: { name: "bench-scores.jsonl", exists: true } },
  empty: { runs: "", scorecards: "" },
  notes: ["Read-only: this answer only read the two benchmark stores."],
  words: [],
};

// ── 1. The words ────────────────────────────────────────────────────────────
ok("a stored date is plain words, not a slice of a timestamp",
  R.dayWords("2026-11-08") === "8 November 2026", R.dayWords("2026-11-08"));
ok("a row with no real date gets no date, never today's",
  R.dayWords("") === "" && R.dayWords(null) === "" && R.dayWords("yesterday") === "");

const speed = R.speedRow(PAYLOAD.runs[0]);
ok("a speed run names the model and its lane",
  speed.title === "qwen3.5:9b on the everyday lane", speed.title);
ok("... and the day it was measured", speed.meta.includes("measured 8 November 2026"),
  speed.meta);
ok("... and keeps the sentence the benchmark itself wrote, word for word",
  speed.words === PAYLOAD.runs[0].words, speed.words);
const spilled = R.speedRow(PAYLOAD.runs[1]);
ok("a spilled run says so, in the meta line as well as the stored sentence",
  spilled.meta.includes("spilled into system RAM")
  && spilled.words.startsWith("PARTIAL:"), spilled.meta);
const failed = R.speedRow(PAYLOAD.runs[2]);
ok("a failed run says it failed and keeps its own reason",
  failed.meta.includes("that run failed")
  && failed.words === "Nothing was measured: no repeat produced a number.",
  failed);
const noSentence = R.speedRow({ model: "m:1b", lane: "main", ok: false,
  why: "the lane did not answer", day: "2026-11-01" });
ok("a failed row with no stored sentence uses its own reason, not a made-up one",
  noSentence.words === "This run failed: the lane did not answer", noSentence.words);
const bare = R.speedRow({ model: "", day: "" });
ok("an empty row is described honestly and invents no number",
  bare.title === "a model" && bare.words === "No sentence was stored for this run."
  && !/\d/.test(bare.words + bare.meta), bare);

const coding = R.scoreRow(PAYLOAD.scorecards[0]);
ok("a scorecard names its suite and model",
  coding.title === "Coding on qwen3.5:9b", coding.title);
ok("... shows the stored score and task count, not a rounded-up claim",
  coding.meta.includes("83.3%") && coding.meta.includes("5 of 6 tasks"), coding.meta);
ok("... names the stored context and quantisation",
  coding.meta.includes("8,192 tokens of context") && coding.meta.includes("Q4_K_M"),
  coding.meta);
ok("... and keeps the store's sentence", coding.words === PAYLOAD.scorecards[0].words);
const skipped = R.scoreRow(PAYLOAD.scorecards[1]);
ok("a skipped suite says it was not run and carries no score",
  skipped.meta.includes("not run") && !skipped.meta.includes("%")
  && skipped.words.startsWith("Vision / OCR: not run"), skipped);
ok("a scorecard with no score shows no percentage anywhere",
  !R.scoreFigure({ items: 6, items_passed: 5 }).includes("%")
  && R.scoreFigure({ score_pct: 83.33, items: 6, items_passed: 5 }) === "83.3% 5 of 6 tasks",
  R.scoreFigure({ score_pct: 83.33, items: 6, items_passed: 5 }));
ok("a failed suite says it did not pass",
  R.scoreRow({ suite_label: "General", model: "m", passed: false, day: "2026-11-02" })
    .meta.includes("did not pass"));
ok("a scorecard with no stored sentence says so",
  R.scoreRow({ suite_label: "General", model: "m" }).words
    === "No sentence was stored for this scorecard.");

ok("the card says 'newest 3 of 12', never '3 measured'",
  R.countWords("speed runs", 3, 12) === "Showing the newest 3 of 12 speed runs on file.");
ok("... and the whole count when nothing is held back",
  R.countWords("scorecards", 7, 7) === "7 scorecards on file.");
ok("... and nothing at all when the store is empty", R.countWords("speed runs", 0, 0) === "");

const empty = R.emptyWords({ empty: {
  runs: "No speed run is on file yet: there is no bench.jsonl beside Jarvis's saved files.",
  scorecards: "No five-suite scorecard is on file yet: there is no bench-scores.jsonl.",
} });
ok("an empty list keeps the backend's own reason for being empty",
  empty.runs.includes("bench.jsonl") && empty.scorecards.includes("bench-scores.jsonl"),
  empty);
const defaultEmpty = R.emptyWords({});
ok("with no reason given, the empty state still says why - and invents nothing",
  /nothing measured to show/.test(defaultEmpty.runs)
  && /nothing measured to show/.test(defaultEmpty.scorecards), defaultEmpty);

const card = R.measuredModel(PAYLOAD);
ok("the card draws every stored row", card.runs.length === 3
  && card.scorecards.length === 2, card);
ok("the card reports what is stored, not only what it shows",
  card.counts.runs === 12 && card.counts.scorecards === 7
  && card.shown.runs === 3, card.counts);
ok("the read time comes from the backend's own read",
  card.readAt === "21:52:03", card.readAt);
ok("the card says where the rows came from and that it only read them",
  card.source.includes("bench.jsonl") && card.source.includes("bench-scores.jsonl")
  && card.source.includes("starts no run"), card.source);
ok("a populated card says every number was measured on this PC",
  card.note.includes("measured on this PC"), card.note);

const emptyCard = R.measuredModel({ available: true, runs: [], scorecards: [],
  counts: { runs: 0, scorecards: 0 }, stores: PAYLOAD.stores,
  empty: PAYLOAD.empty });
ok("an empty but healthy card keeps both honest empty states",
  emptyCard.runs.length === 0 && emptyCard.empty.runs.length > 0
  && emptyCard.empty.scorecards.length > 0 && emptyCard.note === "", emptyCard);

const absent = R.measuredModel({ available: false, why: "the measured read failed" });
ok("a backend with no measured answer says why and draws no row",
  absent.available === false && absent.runs.length === 0
  && absent.why === "the measured read failed" && absent.note === "", absent);
ok("a backend that never reported results gets an honest default",
  R.measuredModel({ available: false }).why === R.NEVER_REPORTED);

// The one thing the card must never do: put a number on screen that no store
// held. A payload with no numbers at all must draw no numeric figure.
const nothing = R.measuredModel({
  available: true, counts: { runs: 0, scorecards: 0 },
  runs: [{ model: "m", lane: "main" }],
  scorecards: [{ suite_label: "General", model: "m" }],
});
ok("a row with no numbers shows no 0 and no percentage",
  !/\d+\.\d+/.test(JSON.stringify(nothing)) && !/%/.test(JSON.stringify(nothing)),
  nothing);

// ── 2. The wiring, pinned in the real files ─────────────────────────────────
const brain = readFileSync(join(SRC, "brain.js"), "utf8");
const html = readFileSync(join(SRC, "brain.html"), "utf8");
const routes = readFileSync(join(RUST, "brain", "routes.rs"), "utf8");
const results = readFileSync(join(SRC, "model-results.js"), "utf8");
const resources = readFileSync(join(BACKEND, "jarvis_model_resources.py"), "utf8");
const recModule = readFileSync(join(BACKEND, "jarvis_model_recommendations.py"), "utf8");

ok("brain.js imports the module", brain.includes('from "./model-results.js"'));
ok("the Model pane asks for the model_measured read",
  /faculties:\s*\[[^\]]*"model_measured"/.test(brain));
ok("renderMeasured() exists and is drawn in the Faculties view",
  brain.includes("function renderMeasured()")
  && /case "faculties":[\s\S]{0,400}renderMeasured\(\)/.test(brain));
ok("renderMeasured is wired to the page element",
  /measured:\s*\$\(\s*"measured"\s*\)/.test(brain));
ok("the page has the Measured results card with its plain label",
  html.includes('id="measured-card"') && html.includes('id="measured"')
  && /<h2>Measured results<\/h2>/.test(html));
ok("the Rust Brain allowlist maps the section to the one route",
  routes.includes('("model_measured", "/api/models/measured")'));
ok("the backend serves it as a GET on the already-installed PC-only wrapper",
  recModule.includes('PATH_MEASURED = "/api/models/measured"')
  && /GET_PATHS\s*=\s*\(PATH_RECOMMENDATIONS,\s*PATH_RESOURCES,\s*\n?\s*PATH_MEASURED\)/
    .test(recModule));
ok("the read selects rows through jarvis_bench's own readers, not a file of its own",
  resources.includes("def measured(")
  && resources.includes(".runs(limit=0)")
  && resources.includes("score_history(")
  && !resources.includes("write_text"));
ok("the card's own module never re-words a measurement into a speed claim",
  !/tokens a second/.test(results) && !/score_pct\s*[+*]/.test(results));

console.log(`\nok   ${checks} checks passed - the stored rows, the honest states and the wiring`);
