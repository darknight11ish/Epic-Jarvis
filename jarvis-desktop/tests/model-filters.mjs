/**
 * model-filters.mjs - the Brain's "Check for new models" filter bar: non-fitting
 * models hidden by default, no Download ever offered for one, and the full
 * filter set the owner chose (Wave-9 Lane 2; Q4 ruling of 2026-11-07).
 *
 *     node tests/model-filters.mjs
 *
 * WHY THIS SUITE EXISTS WITHOUT PLAYWRIGHT: the browser half of
 * `tests/model-advisor.mjs` needs the Playwright package, which is deliberately
 * not installed here. The filter logic is PURE (src/model-advisor.js holds no
 * DOM), so this file proves every rule it promises with no browser - and reads
 * brain.js for the wiring, the same pattern `tests/hud-rail-tools.mjs` uses.
 *
 * WHAT IT PINS:
 *   1. The default view is "All that fit this PC": a model whose measured risk
 *      is "does not fit" is NOT drawn, so "Check for new models" can never
 *      offer the 36.7 GB model the owner reported.
 *   2. `mayDownload` is the ONE predicate before a Download button, and it is
 *      false for a non-fitting row and for one whose fit was not reported.
 *   3. Every filter the owner named works: hardware fit (1 card / pooled /
 *      all / show non-fitting), size cap, quantization, context window,
 *      licence, capability tags, parameter range, source, and the four sorts.
 *   4. "Show non-fitting" is VIEW-ONLY: its rows carry the disabled Download
 *      and the PC's own pool numbers in brain.js.
 *   5. The fields come from the backend's real candidate contract, and the
 *      page draws the bar (source pins on brain.js, field pins on
 *      backend/jarvis_model_recommendations.py).
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

/* ── The PC's own four rows, in the shape the backend now sends ──────────── */

const ROWS = A.candidateRows({
  candidates: [
    { ref: "qwen3:8b", name: "Qwen3 8B", family: "qwen3", params_b: 8,
      quant: "Q4_K_M", size_gb: 5.1, context_tokens: 32768, licence: "apache-2.0",
      provider: "Hugging Face", fit: "fits", fit_pooled: "fits",
      vram_need_gb: 5.2, pooled_vram_gb: 20, capabilities: ["tools", "coding"],
      released_at: 1_780_000_000,
      source_url: "https://huggingface.co/Qwen/Qwen3-8B-GGUF" },
    { ref: "qwen3:14b", name: "Qwen3 14B", family: "qwen3", params_b: 14,
      quant: "Q4_K_M", size_gb: 8.9, context_tokens: 32768, licence: "apache-2.0",
      provider: "Hugging Face", fit: "no", fit_pooled: "fits",
      vram_need_gb: 16.6, pooled_vram_gb: 20, capabilities: ["vision"],
      released_at: 1_790_000_000,
      source_url: "https://huggingface.co/Qwen/Qwen3-14B-GGUF" },
    { ref: "llama4:17b", name: "Llama 4 17B", family: "llama", params_b: 17,
      quant: "Q8_0", size_gb: 11.4, context_tokens: 131072, licence: "llama4",
      fit: "no", fit_pooled: "no", vram_need_gb: 36.7, pooled_vram_gb: 20,
      capabilities: ["uncensored"], released_at: 1_800_000_000,
      source_url: "https://example.test/llama4" },
    { ref: "tiny:1b", name: "Tiny 1B", family: "tiny", params_b: 1,
      quant: "Q4_K_M", size_gb: 1.0, context_tokens: 8192, licence: "",
      fit: "fits", fit_pooled: "fits", vram_need_gb: 1.2, pooled_vram_gb: 20,
      capabilities: [], released_at: null,
      source_url: "https://ollama.com/library/tiny" },
  ],
});

const BENCH = { "qwen3:8b": { tokens_per_s: 18.4 }, "qwen3:14b": { tokens_per_s: 9.1 } };

/* ── 1. The default view hides what cannot run here ──────────────────────── */

check("the default view is 'All that fit this PC' and hides every non-fitting row", () => {
  assert.equal(A.DEFAULT_FILTERS.fit, "all", "the default hardware filter is not 'all'");
  const defaults = A.freshFilters();
  assert.equal(defaults.fit, "all");
  const shown = A.filterCandidates(ROWS, defaults);
  const refs = shown.map((row) => row.ref);
  assert.deepEqual(refs, ["qwen3:8b", "qwen3:14b", "tiny:1b"],
    "the default view is not every fitting row, in the PC's own order");
  assert.ok(!refs.includes("llama4:17b"), "a model that does not fit this PC is on screen by default");
});

check("a row with NO reported fit is not treated as fitting, and not offered", () => {
  const unknown = A.candidateRows({ candidates: [{ ref: "mystery:1b" }] })[0];
  assert.equal(A.fitModeOf(unknown), "unknown");
  assert.equal(A.mayDownload(unknown), false,
    "a row whose fit was never reported was offered for download");
});

/* ── 2. The one download predicate ──────────────────────────────────────── */

check("mayDownload is true only for a model that really fits this PC", () => {
  const byRef = Object.fromEntries(ROWS.map((row) => [row.ref, row]));
  assert.equal(A.mayDownload(byRef["qwen3:8b"]), true, "a card-fitting model lost its Download");
  assert.equal(A.mayDownload(byRef["qwen3:14b"]), true, "a pooled-fitting model lost its Download");
  assert.equal(A.mayDownload(byRef["llama4:17b"]), false,
    "a non-fitting model would be offered for download");
  assert.equal(A.mayDownload(null), false);
});

check("the non-fitting reason is the PC's own pool numbers", () => {
  const big = ROWS.find((row) => row.ref === "llama4:17b");
  assert.match(A.nonFittingWhy(big),
    /needs about 36\.7 GB of video memory; the measured cards hold 20 GB together/);
  const thin = A.candidateRows({ candidates: [{ ref: "x", fit: "no" }] })[0];
  assert.match(A.nonFittingWhy(thin), /did not report enough for a fit/,
    "a reason was invented for a row with no numbers");
});

/* ── 3. Every filter the owner chose ────────────────────────────────────── */

check("hardware fit: one card / pooled / all / show non-fitting", () => {
  const defaults = A.freshFilters();
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, fit: "one" }).map((r) => r.ref),
    ["qwen3:8b", "tiny:1b"]);
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, fit: "pooled" }).map((r) => r.ref),
    ["qwen3:14b"]);
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, fit: "nonfitting" }).map((r) => r.ref),
    ["llama4:17b"]);
  assert.equal(A.FIT_MODES.length, 4);
  assert.deepEqual(A.FIT_MODES.map((mode) => mode.label), [
    "Fits 1 card (fast)", "Fits 2-3 cards (pooled)",
    "All that fit this PC", "Show non-fitting (view-only)",
  ]);
});

check("size cap (GB): a row above the cap is not shown, and no size means no pass", () => {
  const defaults = A.freshFilters();
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, sizeCap: 6 }).map((r) => r.ref),
    ["qwen3:8b", "tiny:1b"]);
  const thin = A.candidateRows({ candidates: [{ ref: "x", fit: "fits" }] })[0];
  assert.equal(A.matchesFilters(thin, { ...defaults, sizeCap: 6 }), false,
    "a row with no reported size passed a size cap");
});

check("quantization: the owner's four values, plus what the PC's rows carry", () => {
  const defaults = A.freshFilters();
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, quant: "Q4_K_M" }).map((r) => r.ref),
    ["qwen3:8b", "qwen3:14b", "tiny:1b"]);
  // Q8_0 only matches the non-fitting row, so it shows in the view-only mode.
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, quant: "Q8_0" }).map((r) => r.ref), []);
  assert.deepEqual(A.filterCandidates(ROWS,
    { ...defaults, fit: "nonfitting", quant: "Q8_0" }).map((r) => r.ref), ["llama4:17b"]);
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, quant: "UD-Q3_K_XL" }).length, 0);
  // QAT is a family word, matched where a row really says it.
  const qat = A.candidateRows({ candidates: [{ ref: "x/Qwen3-8B-QAT-GGUF", fit: "fits" }] });
  assert.equal(A.filterCandidates(qat, { ...defaults, quant: "QAT" }).length, 1);
  assert.ok(A.QUANT_SUGGESTIONS.includes("UD-Q3_K_XL"));
});

check("context window: a minimum, and an unreported context never passes", () => {
  const defaults = A.freshFilters();
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, contextMin: 131072 }).map((r) => r.ref),
    [], "the only 128K row here does not fit, so it is hidden by default");
  assert.deepEqual(A.filterCandidates(ROWS,
    { ...defaults, fit: "nonfitting", contextMin: 131072 }).map((r) => r.ref), ["llama4:17b"]);
  assert.deepEqual(A.CONTEXT_OPTIONS.map((option) => option.value),
    [0, 16384, 32768, 65536, 131072]);
});

check("licence: an exact catalogue value, and only values the PC reported", () => {
  const defaults = A.freshFilters();
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, licence: "apache-2.0" })
    .map((r) => r.ref), ["qwen3:8b", "qwen3:14b"]);
  assert.deepEqual(A.filterOptions(ROWS).licences, ["apache-2.0", "llama4"]);
});

check("capability tags: vision / tools / coding / reasoning / uncensored", () => {
  assert.deepEqual([...A.CAPABILITY_TAGS], ["vision", "tools", "coding", "reasoning", "uncensored"]);
  const defaults = A.freshFilters();
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, capabilities: ["coding"] })
    .map((r) => r.ref), ["qwen3:8b"]);
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, capabilities: ["tools", "coding"] })
    .map((r) => r.ref), ["qwen3:8b"], "two tags must mean BOTH (AND), not either");
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, capabilities: ["vision"] })
    .map((r) => r.ref), ["qwen3:14b"]);
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, capabilities: ["reasoning"] }), []);
});

check("parameter range: the four named bands, and an unlisted range matches none", () => {
  const defaults = A.freshFilters();
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, params: "1-4" }).map((r) => r.ref),
    ["tiny:1b"]);
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, params: "7-14" }).map((r) => r.ref),
    ["qwen3:8b", "qwen3:14b"]);
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, params: "24-35" }), []);
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, params: "70+" }), []);
  const forty = A.candidateRows({ candidates: [{ ref: "x", fit: "fits", params_b: 40 }] });
  assert.deepEqual(A.filterCandidates(forty, { ...defaults, params: "70+" }), [],
    "a 40B model was folded into 70B+ to make a count look complete");
  assert.ok(A.PARAM_RANGES.some((range) => range.id === "70+" && range.max === null));
});

check("source: the host the row's link really goes to", () => {
  const defaults = A.freshFilters();
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, source: "Hugging Face" })
    .map((r) => r.ref), ["qwen3:8b", "qwen3:14b"]);
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, source: "Ollama's library" })
    .map((r) => r.ref), ["tiny:1b"]);
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, source: "example.test" })
    .map((r) => r.ref), [], "example.test is the non-fitting row, hidden by default");
  assert.deepEqual(A.filterCandidates(ROWS,
    { ...defaults, fit: "nonfitting", source: "example.test" }).map((r) => r.ref), ["llama4:17b"]);
});

check("sort: best fit keeps the PC's order; size, speed and newest are defined", () => {
  const defaults = A.freshFilters();
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, sort: "fit" }).map((r) => r.ref),
    ["qwen3:8b", "qwen3:14b", "tiny:1b"]);
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, sort: "size" }).map((r) => r.ref),
    ["tiny:1b", "qwen3:8b", "qwen3:14b"]);
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, sort: "speed", }, BENCH)
    .map((r) => r.ref), ["qwen3:8b", "qwen3:14b", "tiny:1b"],
    "speed must use only measured rates, measured rows first, the rest last");
  assert.deepEqual(A.filterCandidates(ROWS, { ...defaults, sort: "newest" }).map((r) => r.ref),
    ["qwen3:14b", "qwen3:8b", "tiny:1b"],
    "newest must order by the catalogue's date and put a row with no date LAST");
  assert.deepEqual(A.filterCandidates(ROWS,
    { ...defaults, fit: "nonfitting", sort: "newest" }).map((r) => r.ref),
    ["llama4:17b"], "the dated non-fitting row is still a row");
  assert.deepEqual(A.SORT_MODES.map((mode) => mode.id), ["fit", "speed", "size", "newest"]);
});

check("the summary says what is hidden, and that the hidden rows are view-only", () => {
  const defaults = A.freshFilters();
  const shown = A.filterCandidates(ROWS, defaults);
  const words = A.filterWords(defaults, ROWS, shown);
  assert.match(words, /Showing 3 of 4 newer models/);
  assert.match(words, /1 non-fitting model is hidden/);
  assert.match(words, /Show non-fitting/);
  const viewOnly = A.filterWords({ ...defaults, fit: "nonfitting" }, ROWS,
    A.filterCandidates(ROWS, { ...defaults, fit: "nonfitting" }));
  assert.match(viewOnly, /view-only/);
  assert.match(viewOnly, /no download is offered for a model that cannot run here/);
  assert.match(A.filterWords({ ...defaults, sort: "speed" }, ROWS, shown), /measured on this PC/);
  assert.match(A.filterWords({ ...defaults, sort: "newest" }, ROWS, shown), /release date/);
});

check("activeFilterCount counts what is really on", () => {
  assert.equal(A.activeFilterCount(A.freshFilters()), 0);
  const on = { ...A.freshFilters(), fit: "one", sizeCap: 6, capabilities: ["tools"],
               sort: "size", quant: "Q4_K_M" };
  assert.equal(A.activeFilterCount(on), 5);
});

/* ── 4. The page: the bar is drawn, and no Download reaches a bad row ────── */

check("brain.js draws every control the owner named", () => {
  for (const id of ["advisor-filter-fit", "advisor-filter-size", "advisor-filter-quant",
                    "advisor-filter-context", "advisor-filter-licence", "advisor-filter-params",
                    "advisor-filter-source", "advisor-filter-sort", "advisor-filter-clear"]) {
    assert.match(BRAIN, new RegExp(`"${id}"`), `the filter bar is missing ${id}`);
  }
  assert.match(BRAIN, /advisor-filter-tag-\$\{tag\}/, "the capability tag boxes are missing");
  assert.match(BRAIN, /"Hardware fit"/, "the fit control has no label");
  assert.match(BRAIN, /"Size cap \(GB\)"/);
  assert.match(BRAIN, /"Quantization"/);
  assert.match(BRAIN, /"Context window"/);
  assert.match(BRAIN, /"Licence"/);
  assert.match(BRAIN, /"Parameters"/);
  assert.match(BRAIN, /"Source"/);
  assert.match(BRAIN, /"Sort"/);
});

check("brain.js draws only the filtered rows and uses the one download predicate", () => {
  assert.match(BRAIN, /Advisor\.filterCandidates\(candidates, advisor\.filters, payload\.benchmarked\)/,
    "the panel does not filter the candidate list");
  assert.match(BRAIN, /for \(const candidate of shown\) list\.append\(advisorCandidateRow\(candidate\)\)/,
    "the panel draws the unfiltered list");
  assert.match(BRAIN, /advisor\.filters = Advisor\.freshFilters\(\)/,
    "filters cannot be reset to the default view");
  assert.match(BRAIN, /Advisor\.mayDownload\(candidate\)/,
    "the download button is not guarded by the fit predicate");
  assert.match(BRAIN, /denied\.disabled = true/, "the view-only Download is not visibly disabled");
  assert.match(BRAIN, /View-only: it does not fit this PC, so no download is offered\./,
    "a non-fitting row does not say it is view-only");
  assert.match(BRAIN, /Advisor\.nonFittingWhy\(candidate\)/,
    "a non-fitting row does not carry the PC's reason");
});

check("the default filter and the Check button are unchanged", () => {
  assert.match(BRAIN, /filters: Advisor\.freshFilters\(\)/, "the advisor has no default filters");
  assert.match(BRAIN, /button\("Check for new models", checkForModels/,
    "the owner's Check for new models button changed");
});

/* ── 5. The backend really sends the fields the bar reads ────────────────── */

check("the candidate contract carries the five filter fields", () => {
  for (const field of ["vram_need_gb", "fit_pooled", "pooled_vram_gb",
                       "capabilities", "released_at"]) {
    assert.ok(BACKEND.includes(`"${field}"`),
      `backend/jarvis_model_recommendations.py does not carry ${field}`);
  }
  assert.match(BACKEND, /CAPABILITY_KEYS = \("vision", "tools", "coding", "reasoning", "uncensored"\)/,
    "the capability vocabulary is not the owner's five, in order");
});

console.log(`\n${fails.length ? fails.length + " failed" : "all checks passed"}: ` +
  `${fails.length ? fails.join(", ") : "the model filter bar holds, and non-fitting models are never offered"}`);
process.exit(fails.length ? 1 : 0);
