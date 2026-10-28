/**
 * model-advisor.mjs - "Check for new models", the carded download, a benchmark
 * measured on this PC, and a preset recommendation the owner can approve or
 * argue with (the owner's ask, 2026-10-28, quoted in full at the top of
 * `src/model-advisor.js`).
 *
 *     node tests/model-advisor.mjs
 *
 * TWO HALVES, and both are needed:
 *
 *   1. The reading and the words are pure functions (`src/model-advisor.js`), so
 *      every honest state - no answer, no candidates, an unreadable answer, a
 *      benchmark with no speed in it, an opinion box that is empty or too long -
 *      is proved here with no browser at all.
 *
 *   2. The REAL Brain page is then driven through the test harness
 *      (`tests/uikit.mjs`), because a pure function that is right and a panel that
 *      never calls it are the same thing to the owner. It goes: button ->
 *      progress -> candidates -> Download on the EXISTING carded install ->
 *      benchmark shown as measured -> preset advice -> Approve through the
 *      EXISTING preset card -> a note that revises the advice -> the two failure
 *      states, each in the PC's own words.
 *
 * WHY THE PAGE IS DRIVEN AT THE BRIDGE AND NOT THROUGH A STUBBED `fetch` (the
 * same question was asked of hud-presets.mjs, which does stub fetch): the Brain
 * window deliberately holds NO pairing token (apps security audit M2), so its
 * page has no `fetch` of its own to stub - every read and write arrives through
 * a Tauri command in Rust. The bridge IS this window's network boundary, so
 * stubbing it is the desktop equivalent of stubbing a response, and it is where
 * the real page's own code reads its answers. The exact routes behind each
 * action are pinned in the FIRST half against `src-tauri/src/brain.rs`, so a
 * route renamed on either side fails this suite even though the page never sees
 * a URL.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import * as A from "../src/model-advisor.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const RUST = join(HERE, "..", "src-tauri", "src");
const REPO = join(HERE, "..", "..");
const read = (path) => readFileSync(path, "utf8");

const pageSrc = read(join(SRC, "brain.js"));
const advisorSrc = read(join(SRC, "model-advisor.js"));
const brainRs = read(join(RUST, "brain.rs"));
const routesRs = read(join(RUST, "brain", "routes.rs"));
const buildRs = read(join(HERE, "..", "src-tauri", "build.rs"));
const libRs = read(join(RUST, "lib.rs"));
const caps = JSON.parse(read(join(HERE, "..", "src-tauri", "capabilities", "brain.json")));
const surfaces = read(join(HERE, "..", "src-tauri", "permissions", "surfaces.toml"));
const arch = read(join(REPO, "docs", "ARCHITECTURE.md"));
const parity = read(join(REPO, "tools", "check_parity.py"));

/** Comments stripped, so a route named in a docstring is not a call. */
function stripComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/[^\n]*/g, "$1");
}

/** The advisor's own block of brain.js: its state, its calls, and its panel. */
function advisorPageBlock() {
  const start = pageSrc.indexOf("The model advisor's own state");
  const stop = pageSrc.indexOf("The `speed` block of /api/models", start);
  assert.ok(start > 0 && stop > start, "the advisor block is gone from brain.js");
  return pageSrc.slice(start, stop);
}

const fails = [];
let passed = 0;
async function check(name, fn) {
  try {
    await fn();
    passed += 1;
    console.log(`ok    ${name}`);
  } catch (error) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${error && error.message ? error.message : error}`);
  }
}

/* ── 1. The contract: four actions, four routes, and no second way to write ── */

await check("the four actions are the contract's, and the page names an action, never a URL", async () => {
  assert.equal(A.ADVISOR_COMMAND, "brain_model_recommend");
  assert.deepEqual(
    [A.ACTION_CHECK, A.ACTION_BENCHMARK, A.ACTION_RECOMMEND, A.ACTION_OPINION],
    ["check", "benchmark", "recommend", "opinion"]
  );
  // Rust owns the route table. Each action must reach exactly its own path, and
  // the advice routes are the two POSTs the contract names.
  const expected = {
    check: "/api/models/check",
    benchmark: "/api/models/benchmark",
    recommend: "/api/presets/recommend",
    opinion: "/api/presets/recommend/opinion",
  };
  for (const [action, path] of Object.entries(expected)) {
    assert.ok(brainRs.includes(`"${path}"`), `brain.rs does not name ${path}`);
  }
  // ...and the action names sit beside them in the same match arm, so a swapped
  // pair is caught rather than merely present.
  assert.match(brainRs, /"check" => Ok\(\s*\(\s*"\/api\/models\/check"/,
    "check does not map to /api/models/check");
  assert.match(brainRs, /"benchmark" => \{[\s\S]{0,1500}?"\/api\/models\/benchmark"/,
    "benchmark does not map to /api/models/benchmark");
  assert.match(brainRs, /"recommend" => Ok\(\s*\(\s*"\/api\/presets\/recommend"/,
    "recommend does not map to /api/presets/recommend");
  assert.match(brainRs, /"opinion" => \{[\s\S]{0,1500}?"\/api\/presets\/recommend\/opinion"/,
    "opinion does not map to /api/presets/recommend/opinion");
  // The GET is the Brain's own read section, and it is on the read allowlist.
  assert.match(routesRs, /\("model_recommendations", "\/api\/models\/recommendations"\)/,
    "the recommendations read is not on the Brain's read allowlist");
  // The page holds no route at all: a route string in the window would be a
  // second place the contract could drift. Comments are stripped first - the
  // module's own docstring names the routes it reaches THROUGH Rust.
  for (const [name, text] of [["model-advisor.js", stripComments(advisorSrc)],
    ["brain.js's advisor block", stripComments(advisorPageBlock())]]) {
    assert.equal(/\/api\//.test(text), false, `${name} names a route in code`);
    assert.equal(/fetch\s*\(/.test(text), false, `${name} fetches something itself`);
  }
});

await check("the four questions are POSTs, so a read grant can never start one", async () => {
  for (const path of ["/api/models/check", "/api/models/benchmark", "/api/presets/recommend",
    "/api/presets/recommend/opinion"]) {
    assert.ok(routesRs.includes(`"${path}"`), `${path} is not named in the read allowlist test's WRITES`);
  }
  // The advisor adds no route that changes the machine: the download and the
  // apply stay the two EXISTING carded commands, and nothing here names them.
  for (const forbidden of ["/api/models/install", "/api/work/apply", "/api/models/switch"]) {
    assert.equal(stripComments(advisorSrc).includes(forbidden), false, `model-advisor.js names ${forbidden}`);
    assert.equal(stripComments(advisorPageBlock()).includes(forbidden), false,
      `brain.js's advisor names ${forbidden}`);
  }
});

await check("each request carries only its own field", async () => {
  assert.deepEqual(A.advisorArgs("check"), { action: "check", reference: null, text: null });
  assert.deepEqual(A.advisorArgs("recommend"), { action: "recommend", reference: null, text: null });
  assert.deepEqual(A.advisorArgs("benchmark", { ref: "  qwen3:8b ", text: "ignored" }),
    { action: "benchmark", reference: "qwen3:8b", text: null });
  assert.deepEqual(A.advisorArgs("opinion", { ref: "ignored", text: "  keep it small\n" }),
    { action: "opinion", reference: null, text: "keep it small" });
  // The page waits a little longer than Rust for every action, so the PC's own
  // refusal reaches the owner first. Rust: 120 / 540 / 90 / 150 s.
  for (const action of ["check", "benchmark", "recommend", "opinion"]) {
    assert.ok(A.BUDGETS_MS[action] > 0, `${action} has no budget`);
  }
  assert.ok(A.BUDGETS_MS.check > 120_000, "the lookup gives up before Rust does");
  assert.ok(A.BUDGETS_MS.benchmark > 540_000, "the benchmark gives up before Rust does");
  assert.ok(A.BUDGETS_MS.recommend > 90_000, "the recommendation gives up before Rust does");
  assert.ok(A.BUDGETS_MS.opinion > 150_000, "the opinion gives up before Rust does");
});

await check("what cannot be sent is refused with words, before a request is made", async () => {
  assert.match(A.opinionProblem(""), /Type what you think first/);
  assert.match(A.opinionProblem("   \n "), /Type what you think first/);
  assert.equal(A.opinionProblem("keep voice on the fast card"), "");
  assert.match(A.opinionProblem("x".repeat(A.OPINION_MAX_CHARS + 1)), /longer than 2000/);
  assert.equal(A.opinionProblem("x".repeat(A.OPINION_MAX_CHARS)), "");
  assert.equal(A.OPINION_MAX_CHARS, 2_000);
});

/* ── 2. The candidates: the PC's numbers, and no invented ones ────────────── */

const CANDIDATES = {
  checked_at: 1_790_000_000,
  gpus: [
    { name: "NVIDIA GeForce RTX 2060", vram_gb: 12 },
    { name: "NVIDIA GeForce RTX 2080 SUPER", vram_gb: 8 },
  ],
  candidates: [
    { ref: "qwen3:14b", name: "Qwen3 14B", family: "qwen3", params_b: 14, quant: "Q4_K_M",
      size_gb: 8.9, context_tokens: 32768, licence: "apache-2.0", fit: "tight",
      source_url: "https://huggingface.co/Qwen/Qwen3-14B-GGUF",
      why: "14B is the largest that still fits the 12 GB card at this context." },
    { ref: "qwen3:8b", name: "Qwen3 8B", family: "qwen3", params_b: 8, quant: "Q4_K_M",
      size_gb: 5.1, context_tokens: 32768, fit: "fits",
      source_url: "https://huggingface.co/Qwen/Qwen3-8B-GGUF",
      why: "Already installed here; kept as the measured baseline." },
    { ref: "llama4:17b", name: "Llama 4 17B", family: "llama", params_b: 17, quant: "Q4_0",
      size_gb: 11.4, context_tokens: 131072, fit: "no",
      source_url: "https://huggingface.co/meta-llama/Llama-4-17B-GGUF",
      why: "Needs more memory than both cards have free." },
  ],
  recommendations: [
    { preset: "daily",
      changes: [
        { row: "everyday", from: "qwen3:8b", to: "qwen3:14b",
          why: "the 12 GB card has room at 32K, so chat gets the larger model" },
        { row: "voice", from: "qwen3:8b", to: "qwen3:8b",
          why: "unchanged - voice stays on the fast card" },
      ],
      evidence: "qwen3:8b answered at 18.4 tokens a second on the 2060 when measured." },
  ],
  benchmarked: false,
};

const BENCHMARK = { ref: "qwen3:8b", tokens_per_s: 18.4, vram_mb: 7372, context_tokens: 32768 };

const REVISED = {
  ...CANDIDATES,
  checked_at: 1_790_000_060,
  recommendations: [
    { preset: "daily",
      changes: [{ row: "everyday", from: "qwen3:8b", to: "llama3.1:8b",
        why: "your note asked for the smaller model" }],
      evidence: "From your note: keep it small." },
  ],
};

await check("fit is the three words the contract allows, plus an honest non-answer", async () => {
  assert.deepEqual(A.fitWords("fits"), { label: "fits", state: "ok" });
  assert.deepEqual(A.fitWords("tight"), { label: "tight", state: "warn" });
  assert.deepEqual(A.fitWords("no"), { label: "does not fit", state: "bad" });
  assert.deepEqual(A.fitWords("probably"), { label: "fit not reported", state: "" });
  assert.deepEqual(A.fitWords(undefined), { label: "fit not reported", state: "" });
});

await check("a candidate's row is the PC's own numbers, and a nameless one is dropped", async () => {
  const rows = A.candidateRows(CANDIDATES);
  assert.equal(rows.length, 3);
  const fourteen = rows[0];
  assert.equal(fourteen.ref, "qwen3:14b");
  assert.equal(fourteen.fitLabel, "tight");
  assert.deepEqual(A.candidateMeta(fourteen), [
    "8.9 GB", "Q4_K_M quantization", "licence apache-2.0", "14B parameters", "qwen3",
    "32,768 tokens of context", "qwen3:14b",
    "14B is the largest that still fits the 12 GB card at this context.",
  ]);
  // Nothing is invented for a candidate that came with half a row: no size, no
  // quant, no licence - and the licence is SAID to be unreported, not guessed.
  const thin = A.candidateRows({ candidates: [{ ref: "mystery:1b" }] })[0];
  assert.equal(thin.fitLabel, "fit not reported");
  assert.equal(thin.licence, "");
  assert.deepEqual(A.candidateMeta(thin), ["licence not reported by the catalogue"]);
  assert.equal(A.candidateRows({ candidates: [{ name: "no ref" }, null, "junk"] }).length, 0);
});

await check("the hash is never invented: the catalogue has none, and the page says so", async () => {
  assert.match(A.NO_HASH, /No SHA-256/);
  assert.match(A.NO_HASH, /reports no file hash/);
  const rows = A.candidateRows(CANDIDATES);
  assert.equal(rows.filter((r) => "sha256" in r).length, 0, "no candidate row carries a hash");
  assert.equal(rows.filter((r) => "sha_256" in r).length, 0);
});

await check("the measured-note choice reads the PC's benchmark index, not a bare flag", async () => {
  assert.equal(A.anyMeasured({ benchmarked: { "qwen3:8b": { tokens_per_s: 18.4 } } }), true);
  assert.equal(A.anyMeasured({ benchmarked: {} }), false);
  assert.equal(A.anyMeasured({ benchmarked: false }), false);
  assert.equal(A.anyMeasured({}), false);
  assert.equal(A.anyMeasured(null), false);
  // The old bare flag is still honoured, so an older body cannot read as unmeasured.
  assert.equal(A.anyMeasured({ benchmarked: true }), true);
});

await check("a model already installed is recognised, with or without :latest", async () => {
  const installed = A.installedRefs({ installed: ["qwen3:8b", { ref: "llama3.1:latest" }] });
  assert.equal(A.isInstalled("qwen3:8b", installed), true);
  assert.equal(A.isInstalled("llama3.1", installed), true);
  assert.equal(A.isInstalled("qwen3:14b", installed), false);
  assert.equal(A.isInstalled("", installed), false);
});

await check("when the PC checked is shown, and never invented", async () => {
  assert.equal(A.checkedWords(0), "");
  assert.equal(A.checkedWords(undefined), "");
  assert.equal(A.checkedWords("not a date"), "");
  assert.equal(A.checkedWords(Date.now() + 10 * 60_000), "", "a clock far in the future is not trusted");
  assert.match(A.checkedWords(1_790_000_000), /^Checked /);
  assert.match(A.checkedWords(1_790_000_000_000), /^Checked /, "milliseconds are read as milliseconds");
  assert.match(A.checkedWords("2026-10-20T09:00:00Z"), /^Checked /);
});

await check("the graphics cards are the PC's own words, and an unknown card is not invented", async () => {
  assert.deepEqual(A.gpuWords(CANDIDATES.gpus), [
    "NVIDIA GeForce RTX 2060 (12.0 GB)",
    "NVIDIA GeForce RTX 2080 SUPER (8.0 GB)",
  ]);
  assert.deepEqual(A.gpuWords([{ name: "Some card" }]), ["Some card"]);
  assert.deepEqual(A.gpuWords([]), []);
  assert.deepEqual(A.gpuWords(undefined), []);
});

/* ── 3. The benchmark: a measurement, or the honest reason there is none ──── */

await check("a real benchmark reads as measured on this PC, with its own numbers", async () => {
  const words = A.benchmarkWords(BENCHMARK);
  assert.equal(words.measured, true);
  assert.deepEqual(words.lines, [
    "18.4 tokens a second",
    "7.2 GB of graphics memory",
    "32,768 tokens of context",
  ]);
  assert.equal(words.why, "");
  assert.equal(A.benchmarkLine(BENCHMARK),
    "Measured on this PC: 18.4 tokens a second, 7.2 GB of graphics memory, 32,768 tokens of context.");
});

await check("a benchmark with no speed in it is NOT a measurement", async () => {
  const words = A.benchmarkWords({ ref: "qwen3:8b", vram_mb: 7372, context_tokens: 32768 });
  assert.equal(words.measured, false, "a VRAM figure was treated as a benchmark");
  assert.equal(words.why, A.NO_SPEED);
  assert.equal(A.benchmarkLine({ ref: "qwen3:8b", vram_mb: 7372 }), "",
    "a line wearing the measured label without a measurement");
  assert.equal(A.benchmarkWords({ ref: "x" }).measured, false);
  assert.equal(A.benchmarkWords(null).measured, false);
});

await check("a benchmark the PC could not do says the PC's own reason", async () => {
  const words = A.benchmarkWords({ available: false, why: "that model is not installed on this PC" });
  assert.equal(words.measured, false);
  assert.equal(words.why, "that model is not installed on this PC");
  const refused = A.benchmarkWords({ ok: false, error: "the model is busy answering" });
  assert.equal(refused.measured, false);
  assert.equal(refused.why, "the model is busy answering");
});

/* ── 4. The preset recommendation, and the note that changes it ───────────── */

await check("a recommendation keeps its preset id, its rows and its evidence, word for word", async () => {
  const rows = A.recommendationRows(CANDIDATES);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].preset, "daily");
  assert.deepEqual(rows[0].changes[0], {
    row: "everyday", from: "qwen3:8b", to: "qwen3:14b",
    why: "the 12 GB card has room at 32K, so chat gets the larger model",
  });
  assert.equal(rows[0].evidence, CANDIDATES.recommendations[0].evidence);
  assert.equal(A.changeWords(rows[0].changes[0]), "everyday: qwen3:8b -> qwen3:14b");
  // A change with a missing side is said, not left blank.
  assert.equal(A.changeWords({ row: "voice", to: "qwen3:8b" }), "voice: not set -> qwen3:8b");
  // A recommendation with no preset id would have nothing to approve.
  assert.equal(A.recommendationRows({ recommendations: [{ changes: [] }, null] }).length, 0);
});

await check("an answer that is not an answer is told apart from an empty one", async () => {
  assert.equal(A.looksLikeAnswer(CANDIDATES), true);
  assert.equal(A.looksLikeAnswer({ available: true }), false);
  assert.equal(A.looksLikeAnswer(null), false);
  assert.equal(A.looksLikeAnswer("hi"), false);
  assert.equal(A.looksLikeAnswer({ candidates: [] }), true, "an empty list is still an answer");
});

/* ── 5. The window's half: one narrow command, one carded install, one card ── */

await check("the command is registered, granted and reachable from the Brain only", async () => {
  assert.ok(libRs.includes("brain::brain_model_recommend"), "lib.rs does not register the command");
  assert.ok(buildRs.includes('"brain_model_recommend"'), "build.rs has no ACL entry for the command");
  assert.ok(surfaces.includes('"allow-brain-model-recommend"'),
    "no permission set grants the advisor command");
  // The set that holds the model power holds it, so a window with the model
  // list is not given half a faculty.
  const set = /\[\[set\]\]\s*identifier = "brain-faculties"([\s\S]*?)\n\n/.exec(surfaces);
  assert.ok(set, "the brain-faculties set is gone");
  assert.match(set[1], /allow-brain-model-recommend/, "brain-faculties does not grant the advisor");
  // The Brain's own capability holds both sets it needs: the advisor, and the
  // EXISTING preset apply for "Approve changes".
  assert.ok(caps.windows.includes("brain"));
  assert.ok(caps.permissions.includes("brain-faculties"), "the Brain lost brain-faculties");
  assert.ok(caps.permissions.includes("focus-presets"),
    "the Brain cannot ask the PC to apply a preset, so Approve changes would be dead");
});

await check("nothing looks on Hugging Face by itself: the only call is the button's", async () => {
  // One reference to the check's own function, and one place it is handed to the
  // button. A third would be a second caller - and an automatic lookup on open
  // is exactly what this feature must not do.
  const calls = (pageSrc.match(/checkForModels/g) || []).length;
  assert.equal(calls, 2, `checkForModels is referenced ${calls} times, not just by its button`);
  assert.match(advisorPageBlock(), /button\("Check for new models", checkForModels/, 
    "the check is not behind the one button");
  // The GET is a read of the last answer; only a POST may start a lookup.
  const routesBlock = routesRs.slice(routesRs.indexOf("READ_ROUTES"), routesRs.indexOf("pub(super) fn route_for"));
  assert.match(routesBlock, /"model_recommendations", "\/api\/models\/recommendations"/);
  assert.equal(/models\/check/.test(routesBlock), false, "the check is on the read allowlist");
});

await check("the desktop-only decision is written down where the audit looks", async () => {
  // ARCHITECTURE section 8's one-sided table, and the parity classifier, are the
  // two places a one-sided feature has to appear. Without them the next audit
  // reads this as drift.
  assert.match(arch, /model advisor/i, "docs/ARCHITECTURE.md section 8 says nothing about the model advisor");
  assert.match(arch, /(do not build the model catalogue on the phone|keeps the model catalogue off the phone)/i,
    "ARCHITECTURE does not say why the phone has no half");
  for (const path of ["/api/models/check", "/api/models/benchmark", "/api/models/recommendations",
    "/api/presets/recommend", "/api/presets/recommend/opinion"]) {
    assert.ok(parity.includes(`"${path}"`), `tools/check_parity.py does not classify ${path}`);
  }
});

/* ── 6. The real page, against stubbed answers at the bridge ──────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();

const SIZE = { width: 1180, height: 900 };
const tab = async (brain, advisor) => {
  const p = await K.open(browser, base, "brain.html",
    { brain: { ...K.BRAIN, ...brain }, advisor }, SIZE);
  await p.locator("#tab-faculties").click();
  await p.waitForTimeout(250);
  return p;
};
const modelsText = (p) => p.locator("#models").innerText();
const advisorCalls = (p) => p.evaluate(() => window.__advisorCalls || []);
const candidateRow = (p, name) => p.locator("#models .advisor-candidate")
  .filter({ has: p.locator(".row-title", { hasText: name }) });

await check("the panel opens saying 'not checked yet', and looks nothing up on its own", async () => {
  const p = await tab({}, { answers: { check: CANDIDATES, benchmark: BENCHMARK, opinion: REVISED } });
  const text = await modelsText(p);
  const buttons = await p.locator("#model-check").count();
  const button = await p.locator("#model-check").innerText();
  const calls = await advisorCalls(p);
  await p.close();
  assert.match(text, /newer models/i);
  assert.equal(buttons, 1, "there is no Check for new models button");
  assert.match(button, /Check for new models/);
  assert.match(text, /Not checked yet/, "the panel claimed a check it never ran");
  assert.equal(calls.length, 0, "the page asked the PC something before the owner pressed anything");
});

await check("one click shows progress, then the candidates with size, quant, fit and why", async () => {
  const p = await tab({}, { answers: { check: CANDIDATES, benchmark: BENCHMARK, opinion: REVISED } });
  await p.evaluate(() => { window.__advisorHold = true; });
  await p.locator("#model-check").click();
  await K.until(p, "the check to be sent", async () => (await advisorCalls(p)).length === 1);
  assert.match(await modelsText(p), /Looking on Hugging Face/,
    "no progress was shown while the lookup was in flight");
  await p.evaluate(() => window.__advisorRelease());
  await K.until(p, "the candidates", async () => /Qwen3 14B/.test(await modelsText(p)));
  const text = await modelsText(p);
  const calls = await advisorCalls(p);
  await p.close();
  assert.deepEqual(calls, [{ action: "check", reference: null, text: null }],
    "the check sent more than its own action");
  assert.match(text, /Qwen3 14B/);
  assert.match(text, /8\.9 GB/, "the size the PC gave");
  assert.match(text, /Q4_K_M quantization/);
  assert.match(text, /32,768 tokens of context/);
  assert.match(text, /tight/i);
  assert.match(text, /does not fit/i, "the 'no' fit is not said in words");
  assert.match(text, /14B is the largest that still fits the 12 GB card/,
    "the PC's own why is missing");
  assert.match(text, /On Hugging Face: https:\/\/huggingface\.co\/Qwen\/Qwen3-14B-GGUF/);
  assert.match(text, /licence apache-2\.0/, "the licence the catalogue reported is missing");
  assert.match(text, /licence not reported by the catalogue/,
    "a row with no licence did not say so honestly");
  assert.match(text, /No SHA-256 is shown: the catalogue Jarvis reads reports no file hash/,
    "the missing hash was not said out loud");
  assert.match(text, /Nothing here has been measured on this PC yet/,
    "the panel let an unmeasured list read as an upgrade");
  assert.match(text, /Nothing downloads until you approve that card/);
});

await check("Download goes to the EXISTING carded install, and the advisor is not asked to install", async () => {
  const p = await tab({}, { answers: { check: CANDIDATES, benchmark: BENCHMARK, opinion: REVISED } });
  await p.locator("#model-check").click();
  await K.until(p, "the candidates", async () => /Qwen3 14B/.test(await modelsText(p)));
  await candidateRow(p, "Qwen3 14B").getByRole("button", { name: "Download" }).click();
  await p.waitForTimeout(300);
  const calls = await p.evaluate(() => window.__calls);
  const text = await modelsText(p);
  const advisorAsked = await advisorCalls(p);
  await p.close();
  const install = calls.filter((c) => c[0] === "brain_model");
  assert.equal(install.length, 1, "the download did not go to the carded install command");
  assert.deepEqual(install[0][1], { action: "install", reference: "qwen3:14b" });
  assert.match(text, /Waiting for your approval: installing qwen3:14b/,
    "the owner was not told a card is waiting");
  assert.match(text, /nothing downloads until you do/);
  assert.equal(advisorAsked.some((c) => c.action !== "check"), false,
    "the advisor was used as a second, uncarded way to download");
});

await check("Benchmark on this PC shows tokens/s, VRAM and context as measured here", async () => {
  const p = await tab({}, { answers: { check: CANDIDATES, benchmark: BENCHMARK, opinion: REVISED } });
  await p.locator("#model-check").click();
  await K.until(p, "the candidates", async () => /Qwen3 8B/.test(await modelsText(p)));
  // The installed candidate offers the benchmark; the missing one offers Download.
  assert.equal(await candidateRow(p, "Qwen3 8B").getByRole("button", { name: "Benchmark on this PC" }).count(), 1,
    "an installed candidate was not offered a benchmark");
  assert.equal(await candidateRow(p, "Qwen3 14B").getByRole("button", { name: "Benchmark on this PC" }).count(), 0,
    "a model this PC does not have was offered a benchmark");
  await candidateRow(p, "Qwen3 8B").getByRole("button", { name: "Benchmark on this PC" }).click();
  await K.until(p, "the measurement", async () => /Measured on this PC/.test(await modelsText(p)));
  const text = await modelsText(p);
  const calls = await advisorCalls(p);
  await p.close();
  const asked = calls.filter((c) => c.action === "benchmark");
  assert.equal(asked.length, 1);
  assert.deepEqual(asked[0], { action: "benchmark", reference: "qwen3:8b", text: null });
  assert.match(text, /Measured on this PC: 18\.4 tokens a second, 7\.2 GB of graphics memory, 32,768 tokens of context\./,
    "the measurement is not shown, or not labelled as this PC's");
  assert.match(text, /Some of these have been measured on this PC/,
    "the note under the list still claimed nothing was measured");
  assert.doesNotMatch(text, /Nothing here has been measured on this PC yet/,
    "the note contradicted the measured row above it");
});

await check("the preset recommendation shows its rows, its why and its evidence", async () => {
  const p = await tab({}, { answers: { check: CANDIDATES, benchmark: BENCHMARK, opinion: REVISED } });
  await p.locator("#model-check").click();
  await K.until(p, "the recommendation", async () => /Preset: daily/.test(await modelsText(p)));
  const text = await modelsText(p);
  await p.close();
  assert.match(text, /Preset: daily/);
  assert.match(text, /everyday: qwen3:8b -> qwen3:14b/);
  assert.match(text, /the 12 GB card has room at 32K, so chat gets the larger model/);
  assert.match(text, /voice: qwen3:8b -> qwen3:8b/);
  assert.match(text, /Evidence: qwen3:8b answered at 18\.4 tokens a second on the 2060 when measured\./);
  assert.match(text, /Approve changes to daily/);
});

await check("Approve changes asks the PC to apply the preset on its EXISTING card, and claims no success", async () => {
  const p = await tab({}, { answers: { check: CANDIDATES, benchmark: BENCHMARK, opinion: REVISED } });
  await p.locator("#model-check").click();
  await K.until(p, "the recommendation", async () => /Preset: daily/.test(await modelsText(p)));
  await p.getByRole("button", { name: "Approve changes to daily" }).click();
  await K.until(p, "the waiting line", async () => /Waiting for your approval: applying the daily preset/.test(await modelsText(p)));
  const calls = await p.evaluate(() => window.__calls);
  const text = await modelsText(p);
  const advisorAsked = await advisorCalls(p);
  await p.close();
  const applied = calls.filter((c) => c[0] === "apply_focus_preset");
  assert.equal(applied.length, 1, "Approve changes did not use the existing carded preset command");
  assert.deepEqual(applied[0][1], { preset: "daily" }, "the apply sent more than the one preset id");
  assert.match(text, /nothing changes until you do/);
  assert.equal(advisorAsked.some((c) => c.action !== "check"), false,
    "the advisor was used to apply a preset itself");
});

await check("a note revises the recommendation, and the note survives a re-render", async () => {
  const p = await tab({}, { answers: { check: CANDIDATES, benchmark: BENCHMARK, opinion: REVISED } });
  await p.locator("#model-check").click();
  await K.until(p, "the recommendation", async () => /Preset: daily/.test(await modelsText(p)));
  const note = "keep it small - the 8B is fast enough";
  await p.locator("#model-opinion-text").fill(note);
  // A benchmark in between re-draws the whole panel; the typed note must stay.
  await candidateRow(p, "Qwen3 8B").getByRole("button", { name: "Benchmark on this PC" }).click();
  await K.until(p, "the measurement", async () => /Measured on this PC/.test(await modelsText(p)));
  assert.equal(await p.locator("#model-opinion-text").inputValue(), note,
    "a re-render ate what the owner had typed");
  await p.locator("#model-opinion").click();
  await K.until(p, "the revised advice", async () => /Revised from what you said/.test(await modelsText(p)));
  const text = await modelsText(p);
  const calls = await advisorCalls(p);
  await p.close();
  const asked = calls.filter((c) => c.action === "opinion");
  assert.equal(asked.length, 1);
  assert.deepEqual(asked[0], { action: "opinion", reference: null, text: note });
  assert.match(text, /Revised from what you said: “keep it small - the 8B is fast enough”/);
  assert.match(text, /everyday: qwen3:8b -> llama3\.1:8b/, "the revised change is not the one shown");
  assert.match(text, /your note asked for the smaller model/);
  assert.doesNotMatch(text, /to: qwen3:14b|-> qwen3:14b/, "the old recommendation is still shown as current");
  assert.equal(calls.filter((c) => c[0] === "apply_focus_preset").length, 0,
    "revising the advice applied something");
});

await check("an opinion the PC would not take is said in the PC's own words", async () => {
  const p = await tab({}, {
    answers: { check: CANDIDATES, benchmark: BENCHMARK, opinion: REVISED },
    errors: { opinion: "the model did not answer the opinion request in time" },
  });
  await p.locator("#model-check").click();
  await K.until(p, "the recommendation", async () => /Preset: daily/.test(await modelsText(p)));
  await p.locator("#model-opinion-text").fill("use the smaller one");
  await p.locator("#model-opinion").click();
  await K.until(p, "the refusal", async () => /did not answer the opinion request/.test(await modelsText(p)));
  const text = await modelsText(p);
  await p.close();
  assert.match(text, /the model did not answer the opinion request in time/,
    "the PC's own sentence was replaced with something generic");
  assert.match(text, /Preset: daily/, "the last good recommendation was blown away by a refusal");
});

await check("a lookup that failed says so, in the PC's own words, and offers no candidates", async () => {
  const p = await tab({}, {
    answers: { benchmark: BENCHMARK },
    errors: { check: "the Hugging Face lookup failed: HTTP 503 from huggingface.co" },
  });
  await p.locator("#model-check").click();
  await K.until(p, "the failure", async () => /Hugging Face lookup failed/.test(await modelsText(p)));
  const text = await modelsText(p);
  await p.close();
  assert.match(text, /the Hugging Face lookup failed: HTTP 503 from huggingface\.co/,
    "the failure is not shown in the PC's own words");
  assert.doesNotMatch(text, /does not fit/, "a candidate from an earlier answer was left on the panel");
  assert.match(text, /newer models/i, "the panel vanished on a failure");
});

await check("a PC with no advisor says so, and never looks like an empty list", async () => {
  const p = await tab({ model_recommendations: { available: false } }, {});
  const text = await modelsText(p);
  await p.close();
  assert.match(text, /does not have the model advisor yet/);
  assert.match(text, /apply-patches\.ps1/);
  assert.doesNotMatch(text, /found no newer model/, "a missing module read as a finished lookup");
});

await check("a real lookup that found nothing says that, and offers the advice again", async () => {
  const p = await tab({}, {
    answers: {
      check: { checked_at: 1_790_000_000, gpus: [], candidates: [], recommendations: [], benchmarked: false },
      recommend: CANDIDATES,
    },
  });
  await p.locator("#model-check").click();
  await K.until(p, "the empty answer", async () => /found no newer model/.test(await modelsText(p)));
  const text = await modelsText(p);
  assert.equal(await p.locator("#model-recommend").count(), 1, "no way to ask for advice again");
  await p.locator("#model-recommend").click();
  await K.until(p, "the advice", async () => /Preset: daily/.test(await modelsText(p)));
  const after = await modelsText(p);
  await p.close();
  assert.match(text, /found no newer model it would suggest/);
  assert.match(after, /Preset: daily/, "the separate advice route did not reach the panel");
});

await check("a benchmark the PC cannot do is shown as its reason, never as a measurement", async () => {
  const p = await tab({}, {
    answers: {
      check: CANDIDATES,
      benchmark: { available: false, why: "qwen3:8b is answering right now, so it cannot be measured" },
    },
  });
  await p.locator("#model-check").click();
  await K.until(p, "the candidates", async () => /Qwen3 8B/.test(await modelsText(p)));
  await candidateRow(p, "Qwen3 8B").getByRole("button", { name: "Benchmark on this PC" }).click();
  await K.until(p, "the reason", async () => /answering right now, so it cannot be measured/.test(await modelsText(p)));
  const text = await modelsText(p);
  await p.close();
  assert.match(text, /qwen3:8b is answering right now, so it cannot be measured/);
  assert.doesNotMatch(text, /Measured on this PC/, "an unavailable benchmark wore the measured label");
});

await browser.close();
await close();

console.log(`\n${passed} passed, ${fails.length} failed`);
if (fails.length) {
  console.log(`failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("The model advisor: a check, a carded download, a measurement here, and advice you approve");
