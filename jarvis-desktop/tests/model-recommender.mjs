/**
 * model-recommender.mjs - the Brain's "What this PC should run" section, built
 * from Lane 3's hardware-aware recommender panel (Wave-9 Lane 2b, 2026-11-07;
 * the owner's Q6 ruling: measured vs estimated, labelled, never dressed up).
 *
 *     node tests/model-recommender.mjs
 *
 * NO BROWSER NEEDED: the words and normalisation are pure
 * (`src/model-advisor.js`), and the page's one render seam is held by source
 * pins on `src/brain.js`. Playwright is not installed here; CI's frontend job
 * drives the real page.
 *
 * WHAT IT PINS:
 *   1. The panel is OPTIONAL: an answer with no `recommender` key (a PC without
 *      the shipped module) produces NO section - not an error, not a guess.
 *   2. Every row keeps its provenance label, exactly: MEASURED ON THIS PC /
 *      MEASURED ON DIFFERENT CARDS / ESTIMATED FIT.
 *   3. A measured row shows its real tok/s, spill and date; a downgraded row
 *      shows its warning out loud, not in a title only.
 *   4. Q4's rule holds here too: a non-fitting row is not drawn, and the
 *      panel's own `not_shown` count explains what was left out.
 *   5. The page draws it through ONE seam, beside the model filter bar; the
 *      section carries no button that could download, apply or benchmark.
 *   6. The backend carries the panel lazily and omits it when the module is
 *      absent (Lane 2b's change to GET /api/models/recommendations).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import * as A from "../src/model-advisor.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const REPO = join(HERE, "..", "..");
const read = (p) => readFileSync(p, "utf8");

const BRAIN = read(join(SRC, "brain.js"));
const BACKEND = read(join(REPO, "backend", "jarvis_model_recommendations.py"));

const fails = [];
const check = (name, fn) => {
  try {
    fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

const MEASURED_AT = 1_761_700_000;
const MEASURED_DAY = new Date(MEASURED_AT * 1000).toISOString().slice(0, 10);

/** One panel exactly as `jarvis_model_recommender.panel()` documents it, for
 *  the owner's PC: three cards (RTX 2060 12 GB + two RTX 2080 SUPER 8 GB =
 *  28 GiB) - the hardware truth the 2026-11-08 screenshot got wrong. */
const HARDWARE_WORDS =
  "This PC has 3 NVIDIA cards with 28 GiB of video memory in total " +
  "(12 GB + 8 GB + 8 GB) and 32 GiB of RAM. It is the Two to three cards, " +
  "20-28 GB in total tier: a 20-28 GB pool: the everyday model on one card " +
  "plus the pooled coding lane across all of them is the arrangement this " +
  "pool was measured for.";
const PANEL = {
  hardware: {
    cards: [
      { name: "NVIDIA GeForce RTX 2080 SUPER", total_gib: 8.0, monitor: true },
      { name: "NVIDIA GeForce RTX 2060", total_gib: 12.0, monitor: false },
      { name: "NVIDIA GeForce RTX 2080 SUPER", total_gib: 8.0, monitor: false },
    ],
    card_count: 3,
    vram_total_gib: 28.0,
    largest_card_gib: 12.0,
    ram_gib: 32.0,
    cpu: "AMD Ryzen",
    detected: true,
    words: HARDWARE_WORDS,
  },
  tier: {
    id: "multi_gpu_20_28gb",
    label: "Two to three cards, 20-28 GB in total",
    words: "a 20-28 GB pool: the everyday model on one card plus the pooled " +
      "coding lane across all of them is the arrangement this pool was " +
      "measured for",
  },
  rows: [
    {
      model: "qwen3.5:9b", label: "Qwen 3.5 9B", params: "9B", quant: "Q4_K_M",
      capabilities: ["tools", "coding"], fit: "fits_1_card",
      vram_needed_gib: 9.3, context_gib: 196608,
      provenance: "measured_this_pc",
      provenance_label: `MEASURED ON THIS PC (41.0 tok/s, 0% spill, ${MEASURED_DAY})`,
      measured: { decode_tps: 41.0, spill_bytes: 0, on_card_percent: 100,
                  at: MEASURED_AT, suite: "speed" },
      downgrade_warning: "",
      why: "At that window it fits on one card on this PC.",
      measured_note:
        "Separately measured on 2026-11-07: 9.18 GiB at 196,608 on the " +
        "RTX 2060 alone (42.01 tok/s)",
    },
    {
      model: "gemma4:31b-it-qat", label: "Gemma 4 31B", params: "31B", quant: "QAT",
      capabilities: ["tools"], fit: "pooled",
      vram_needed_gib: 18.3, context_gib: 16384,
      provenance: "measured_other_hardware",
      provenance_label: "MEASURED ON DIFFERENT CARDS (run benchmark to verify)",
      measured: { decode_tps: 9.5, spill_bytes: 0, on_card_percent: 100,
                  at: MEASURED_AT, suite: "speed" },
      downgrade_warning: "measured on a different card set than the one this PC reports now - " +
        "run the benchmark here to verify",
      why: "At that window it fits across the pooled cards on this PC.",
      measured_note:
        "Separately measured on 2026-11-07: 18.25 GiB at 16,384 across " +
        "three cards (15.57 tok/s)",
    },
    {
      model: "minicpm-v4.6", label: "MiniCPM-V 4.6", params: "1.3B", quant: "Q4_K_M",
      capabilities: ["vision"], fit: "fits_1_card",
      vram_needed_gib: 1.4, context_gib: 16384,
      provenance: "estimated_fit",
      provenance_label: "ESTIMATED FIT (run benchmark to verify)",
      measured: null,
      downgrade_warning: "",
      why: "At that window it fits on one card on this PC.",
      measured_note:
        "Separately measured on 2026-11-07: 1.33 GiB at 16,384 across " +
        "three cards",
    },
    {
      model: "huge:70b", label: "Huge 70B", params: "70B", quant: "Q4_K_M",
      capabilities: [], fit: "too_big",
      vram_needed_gib: 44.0, context_gib: 8.0,
      provenance: "estimated_fit",
      provenance_label: "ESTIMATED FIT (run benchmark to verify)",
      measured: null, downgrade_warning: "", why: "It cannot fit this PC.",
      measured_note: "",
    },
  ],
  not_shown: 3,
  notes: ["nothing has been benchmarked on this PC yet, so every row is an ESTIMATED FIT; " +
          "run the benchmark to verify one."],
  generated_at: MEASURED_AT,
  words: HARDWARE_WORDS,
};

/* ── 1. Optional, and absent without a guess ─────────────────────────────── */

check("no recommender key means NO section - never an error, never a guess", () => {
  for (const payload of [null, undefined, {}, "recommender", { recommender: null },
                         { recommender: "junk" }, { recommender: [] }]) {
    assert.equal(A.recommenderPanel(payload), null, JSON.stringify(payload));
  }
  assert.equal(A.recommenderText(null), "");
});

check("a panel with no usable row but real notes still reads, and an empty one does not", () => {
  const notesOnly = A.recommenderPanel({
    recommender: { hardware: {}, tier: {}, rows: [], not_shown: 0,
                   notes: ["the hardware probe could not be read"], generated_at: 0 },
  });
  assert.equal(notesOnly.rows.length, 0);
  assert.equal(notesOnly.notes.length, 1);
  assert.match(A.recommenderText(notesOnly), /hardware probe could not be read/);
  assert.equal(A.recommenderPanel({ recommender: { hardware: {}, tier: {}, rows: [] } }), null);
});

/* ── 2. The panel's own facts ────────────────────────────────────────────── */

check("the hardware sentence carries the PC's real cards, and the tier ONCE", () => {
  const panel = A.recommenderPanel({ recommender: PANEL });
  assert.ok(panel, "a full panel was refused");
  assert.equal(panel.title, "What this PC should run");
  // The 2026-11-08 screenshot said one 8 GB card; the PC has 12 + 8 + 8 = 28.
  assert.match(panel.hardwareWords, /3 NVIDIA cards with 28 GiB of video memory/);
  assert.equal(panel.tierLabel, "Two to three cards, 20-28 GB in total");
  assert.match(panel.tierWords, /20-28 GB pool/);
  // ONE tier paragraph: the hardware sentence already ends with it.
  assert.equal(panel.hardwareWords.split(panel.tierLabel).length - 1, 1,
    "the hardware sentence does not name the tier exactly once");
  assert.equal(A.recommenderText(panel).split(panel.tierLabel).length - 1, 1,
    "the section prints the tier twice");
  assert.equal(panel.generatedAt, MEASURED_AT);
  assert.match(A.recommenderWhen(panel), new RegExp(`As of ${MEASURED_DAY}`));
});

check("only the rows that fit this PC are drawn (Q4's rule holds in this section too)", () => {
  const panel = A.recommenderPanel({ recommender: PANEL });
  assert.deepEqual(panel.rows.map((row) => row.label),
    ["Qwen 3.5 9B", "Gemma 4 31B", "MiniCPM-V 4.6"],
    "a too_big row was drawn, or a fitting row was lost");
  assert.equal(panel.notShown, 3);
});

/* ── 3. Provenance labels, measured facts, the warning ───────────────────── */

check("every row keeps its provenance label, in the owner's own words", () => {
  const text = A.recommenderText(A.recommenderPanel({ recommender: PANEL }));
  for (const label of ["MEASURED ON THIS PC", "MEASURED ON DIFFERENT CARDS", "ESTIMATED FIT"]) {
    assert.ok(text.includes(label), `the section never says ${label}`);
  }
  const panel = A.recommenderPanel({ recommender: PANEL });
  assert.deepEqual(panel.rows.map((row) => row.provenanceLabel), [
    "MEASURED ON THIS PC", "MEASURED ON DIFFERENT CARDS", "ESTIMATED FIT",
  ]);
});

check("a measured row shows its real tok/s, spill and date", () => {
  const panel = A.recommenderPanel({ recommender: PANEL });
  const measured = panel.rows[0];
  assert.match(measured.measuredLine, /41\.0 tok\/s/);
  assert.match(measured.measuredLine, /0% spill/);
  assert.ok(measured.measuredLine.includes(MEASURED_DAY),
    `the measured date is missing: ${measured.measuredLine}`);
  const text = A.recommenderText(panel);
  assert.match(text, /41\.0 tok\/s/);
  assert.match(text, /0% spill/);
});

check("a downgraded row shows its warning out loud", () => {
  const panel = A.recommenderPanel({ recommender: PANEL });
  const downgraded = panel.rows.find((row) => row.provenance === "measured_other_hardware");
  assert.match(downgraded.warning, /different card set/);
  assert.match(downgraded.warning, /run the benchmark here to verify/);
  assert.match(A.recommenderText(panel), /Warning: measured on a different card set/);
});

check("the row's own numbers and words are carried, not summarised away", () => {
  const panel = A.recommenderPanel({ recommender: PANEL });
  const row = panel.rows[0];
  assert.ok(row.meta.includes("9B parameters"));
  assert.ok(row.meta.includes("Q4_K_M quantization"));
  assert.ok(row.meta.includes("capabilities: tools, coding"));
  assert.ok(row.meta.some((line) => /needs about 9\.3 GiB at 196,608 tokens/.test(line)));
  assert.ok(row.meta.includes(row.why));
});

check("every row scopes its fit estimate and its separate measurement", () => {
  const panel = A.recommenderPanel({ recommender: PANEL });
  for (const row of panel.rows) {
    assert.ok(row.why.startsWith("At that window it "),
      `${row.label}: the fit sentence is not estimate-scoped: ${row.why}`);
    assert.ok(!row.why.includes("needs about"),
      `${row.label}: the requirement is repeated in the fit sentence`);
    const notes = row.meta.filter((line) => line.includes("Separately measured"));
    assert.equal(notes.length, 1,
      `${row.label}: the separate measurement is not labelled once: ${row.meta}`);
    assert.ok(notes[0].startsWith("Separately measured on 2026-11-07: "),
      `${row.label}: the measurement is not scoped: ${notes[0]}`);
  }
  // MiniCPM-V: an estimate that it CAN fit on one card, beside a measurement
  // that was RUN across three. Both are true; the words now say which is which.
  const mini = panel.rows.find((row) => row.label === "MiniCPM-V 4.6");
  assert.match(mini.why, /fits on one card/);
  assert.ok(mini.meta.some((line) => /Separately measured on 2026-11-07: 1\.33 GiB at 16,384 across three cards/.test(line)),
    `MiniCPM-V's measurement is not scoped: ${mini.meta}`);
  const text = A.recommenderText(panel);
  assert.match(text, /Separately measured on 2026-11-07: 1\.33 GiB/);
});

check("Q4's not-shown count is said, and the module's notes are lines of their own", () => {
  const panel = A.recommenderPanel({ recommender: PANEL });
  const notShown = A.recommenderNotShownLine(panel);
  assert.match(notShown, /3 more models need more video memory/);
  assert.match(notShown, /view-only/);
  const text = A.recommenderText(panel);
  assert.ok(text.includes(notShown), "the not-shown line is not drawn");
  assert.match(text, /nothing has been benchmarked on this PC yet/);
  assert.doesNotMatch(text, /Huge 70B/, "a non-fitting row was drawn");
});

/* ── 4. The page: one render seam, no action buttons ────────────────────── */

check("brain.js draws the section through its one recommender seam", () => {
  assert.match(BRAIN, /function advisorRecommenderPanel\(\)/,
    "the panel source function is gone");
  assert.match(BRAIN, /function advisorRecommenderSection\(panel\)/,
    "the one render seam is gone");
  assert.match(BRAIN, /wrap\.id = "model-recommender"/,
    "the section has no testable id");
  assert.match(BRAIN, /Advisor\.recommenderPanel\(/,
    "the page does not read the panel through the pure module");
  assert.match(BRAIN, /Advisor\.recommenderNotShownLine\(panel\)/,
    "the page does not draw the not-shown line");
  assert.match(BRAIN, /Advisor\.recommenderWhen\(panel\)/,
    "the page does not date the section");
  // Wave 11: the tier is printed exactly once, inside the hardware sentence.
  assert.doesNotMatch(BRAIN, /model-recommender-tier/,
    "the page draws a second tier paragraph again");
  assert.doesNotMatch(BRAIN, /panel\.tierLabel/,
    "the page draws the tier outside the hardware sentence");
  // Appended beside the advisor through the same models pane, and ONLY when
  // the answer carries a panel: an older PC draws nothing here.
  assert.match(BRAIN,
    /const recPanel = advisorRecommenderPanel\(\);\s*\n\s*if \(recPanel\) dom\.models\.append\(advisorRecommenderSection\(recPanel\)\);/,
    "the section is drawn without the optional-panel guard, or not at all");
});

check("the section offers no download, apply, benchmark or route of its own", () => {
  const start = BRAIN.indexOf("function advisorRecommenderSection(panel)");
  const end = BRAIN.indexOf("function renderSkills()");
  assert.ok(start > 0 && end > start, "the recommender block is gone from brain.js");
  const block = BRAIN.slice(start, end);
  for (const forbidden of ["modelAction(", "invoke(", "fetch(", "brain_model_recommend",
                           "install", "apply"]) {
    assert.ok(!block.includes(forbidden),
      `the recommender section can ${forbidden} - it must only draw`);
  }
  assert.ok(!/button\(/.test(block), "the section carries a button");
});

/* ── 5. The backend carries it lazily and honestly ──────────────────────── */

check("GET /api/models/recommendations carries the panel lazily, and omits it when absent", () => {
  assert.match(BACKEND, /def _recommender_panel\(loader=None\)/,
    "the lazy panel reader is gone");
  assert.match(BACKEND, /importlib\.import_module/, "the import is not the lazy standard-library door");
  assert.match(BACKEND, /load\("jarvis_model_recommender"\)/, "the wrong module is read");
  assert.match(BACKEND, /module\.panel\(\)/, "panel() is not the entry point");
  assert.match(BACKEND, /out\["recommender"\] = panel/, "the GET answer does not carry it");
  assert.match(BACKEND, /if panel is not None:/, "an absent panel is not guarded");
});

console.log(`\n${fails.length ? fails.length + " failed" : "all checks passed"}: ` +
  `${fails.length ? fails.join(", ") : "the What this PC should run section is measured, labelled and optional"}`);
process.exit(fails.length ? 1 : 0);
