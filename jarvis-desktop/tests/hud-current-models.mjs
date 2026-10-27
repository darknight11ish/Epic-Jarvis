/**
 * hud-current-models.mjs - the Studio dock's "Current Models" button and the
 * read-only panel it opens (the owner's ask, 2026-10-26, verbatim):
 *
 *   "under the button on the jarvis hud that says auto, theres several options
 *    including bulk, critic, escalate, can you just get rid of this button and
 *    replace it with a button that says "Current Models" and clicking it will
 *    show what models are being used and or loaded on jarvis?"
 *
 *     node tests/hud-current-models.mjs
 *
 * WHY THIS SUITE NEEDS NO BROWSER. The panel's words are pure functions in
 * `src/hud-presets.js` (`currentModelsWords`), and its three reads are pure
 * enough to drive with a fake window and a fake fetch. So every honest empty
 * state and every read is proved here, for real, without Playwright - which is
 * deliberately not installed on this machine. The page-level behaviour (the
 * button opening the panel, the lane buttons actually moving the next message)
 * is in tests/hud-presets.mjs, which does need Playwright.
 *
 * WHAT IT PROVES, in order:
 *   1. the old lane dropdown is GONE from the page (no `lane-compact`, no
 *      `<select>` in that slot) and the one control there is a button whose
 *      visible label, aria-label and title say Current Models;
 *   2. the panel is the page's own popover styling (the Presets menu's
 *      `hud-presets-*` classes) with a heading that always says Current Models,
 *      and it is mounted by the page's module block - not a second page;
 *   3. the three reads are exactly `/api/models`, `/api/status` and
 *      `/api/presets`, all GETs carrying `X-Jarvis-Client: hud`, and one
 *      failing read does not blank the other two;
 *   4. the words are the PC's own: current/previous, default_model only when it
 *      differs, offload rows with size/vram/GPU share, the chosen preset - and
 *      the owner's exact sentences when the PC said nothing. No value is ever
 *      invented (a model with no offload row, no name, no numbers);
 *   5. the lane routes are the PAGE's own `#lanes .lane` buttons, clicked, with
 *      the pressed mark read back off them - never a copied list of lane names,
 *      never marked from the click;
 *   6. it adds no route, no command, no card and no write: the panel's reads are
 *      the only `/api/` it names, there is no `invoke(`/POST in it, and Rust's
 *      fixed list gains `/api/models` while every model WRITE stays refused;
 *   7. the three served copies of the page and of hud-presets.js are
 *      byte-identical.
 *
 * NOT here: the real desktop window and WebView2 painting (a rebuild+install is
 * needed after merge), and the real PC's `/api/models` body - that is
 * backend/test_gpu_offload.py and the live read itself.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import * as P from "../src/hud-presets.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const SRC = join(HERE, "..", "src");
const read = (path) => readFileSync(path, "utf8");
const page = read(join(SRC, "jarvis_hud.html"));
const presetsSrc = read(join(SRC, "hud-presets.js"));
const rust = read(join(HERE, "..", "src-tauri", "src", "hud_proxy.rs"));
const bootstrap = read(join(HERE, "..", "src-tauri", "src", "hud_bootstrap.js"));

/** The Current Models section of hud-presets.js, for the source pins. */
const start = presetsSrc.indexOf("── 5. The Current Models panel");
const sectionEnd = presetsSrc.indexOf("export { MENU_ID, PANEL_ID, STATUS_ID };");
const section = presetsSrc.slice(start, sectionEnd);

let fails = 0;
let passed = 0;
function ok(name) { passed += 1; console.log(`ok    ${name}`); }
async function check(name, fn) {
  try {
    await fn();
    ok(name);
  } catch (error) {
    fails += 1;
    console.log(`FAIL  ${name}\n        ${error && error.message ? error.message : error}`);
  }
}

const ACCESSOR = (text) => text.replace(/\s+/g, " ").trim();

/* ── 1. The model name is the door (2026-10-27) ──────────────────────────── */

await check("the separate Current Models button is gone, and the model chip is the door", () => {
  assert.equal(page.includes("lane-compact"), false,
    "the old lane-compact selector is still in the page");
  assert.equal(/#current-models\b/.test(page), false,
    "the separate #current-models control is still in the page");
  assert.equal(page.includes('class="current-models"'), false,
    "the .current-models slot class is still in the page");
  const tag = /<button[^>]*id="chip-model-door"[^>]*>/.exec(page);
  assert.ok(tag, "the page has no #chip-model-door button");
  const button = ACCESSOR(tag[0]);
  assert.match(button, /type="button"/, "the door is not a plain button");
  assert.match(button, /class="chip-door"/, "the door does not take the chip-door class");
  assert.match(button, /aria-haspopup="dialog"/, "the door does not say it opens a dialog");
  assert.match(button, /aria-expanded="false"/, "the door starts claiming to be open");
  assert.match(button, /aria-label="Current Models: what Jarvis is using and has loaded"/,
    "the door's accessible name is not the owner's ask");
  assert.match(button, /title="Current Models: what Jarvis is using and has loaded"/,
    "the door's tooltip is not the owner's ask");
  // The chip stays a span INSIDE the door: ten assignments write its text and
  // class after a turn, and none of them may erase the door (HUD audit P1-1).
  assert.match(page, /<button[^>]*id="chip-model-door"[^>]*>\s*<span[^>]*class="chip"[^>]*id="chip-model"/,
    "the chip is not a span INSIDE the door");
  // No `className` write may ever reach the chip or the door again.
  assert.equal(/chip-model"\)\.className/.test(page), false,
    "a writer still assigns className on the chip (it must use classList)");
  assert.equal(/chip-model-door"\)\.className/.test(page), false,
    "a writer assigns className on the door");
});

await check("the chip door is the chip's own size, and Ambient has a door of its own", () => {
  assert.match(page, /\.chip-door\{[^}]*background:none;[^}]*border:0;/,
    "the door keeps the browser's button chrome instead of the chip's own look");
  assert.match(page, /\.chip-door:focus-visible\{outline:2px solid var\(--ice\)/,
    "the door has no visible focus ring");
  // Ambient (center-core) hides the stage bar's chip, so without a second door
  // that shell could not open the panel at all (HUD audit P1-2).
  assert.match(page, /html\[data-hud-shell="center-core"\] #chip-model-door,/,
    "the stage bar's door is not hidden by name in Ambient (an empty box would stay clickable)");
  assert.match(page, /<button[^>]*id="chip-model-door-ambient"[^>]*>[\s\S]*?<span id="as-model">/,
    "Ambient's pill has no door to the Current Models panel");
  const ambient = /<div id="ambient-status"[^>]*>/.exec(page);
  assert.ok(ambient, "the Ambient pill is gone");
  assert.equal(/aria-hidden="true"/.test(ambient[0]), false,
    "the Ambient pill is aria-hidden while it holds a real button");
  assert.match(page, /\.as-model-door\{[^}]*background:none;/,
    "Ambient's door keeps the browser's button chrome");
});

/* ── 2. The panel is the page's existing popover, and it is mounted ──────── */

await check("the panel reuses the Presets menu's popover classes, with its own heading", () => {
  assert.ok(section.includes('"hud-presets-menu hud-models-panel"'),
    "the panel does not wear the page's existing popover classes");
  assert.ok(section.includes('nodeOf(doc, "p", "hud-presets-title", "Current Models")'),
    "the panel's heading is not the panel's own name");
  for (const cls of ["hud-presets-group", "hud-presets-head", "hud-presets-scroll",
    "hud-presets-empty", "hud-presets-close", "hud-presets-small"]) {
    assert.ok(section.includes(`"${cls}"`), `the panel does not reuse ${cls}`);
  }
  assert.match(page, /\.hud-models-fact\{/, "the readout line has no style of its own");
  assert.match(page, /\.hud-models-route\[aria-pressed="true"\]\{/,
    "the chosen route has no pressed style (the page's own ice-pressed look)");
});

await check("the page mounts exactly one Current Models panel, from its module block", () => {
  const imports = page.match(/import \{ mountHudPresets, mountCurrentModels \} from "\.\/hud-presets\.js";/);
  assert.ok(imports, "the page does not import mountCurrentModels");
  assert.equal((page.match(/mountCurrentModels\(/g) || []).length, 1,
    "the page mounts the panel more than once (or never)");
  assert.ok(page.includes("\nmountCurrentModels();"),
    "the page does not call the mount at page level");
});

await check("both doors only open the one panel, and the panel listens for both", () => {
  // The doors are a loop over BOTH ids, so neither can be left un-wired.
  assert.ok(section.includes('const DOOR_IDS = ["chip-model-door", "chip-model-door-ambient"]'),
    "the panel does not name both doors");
  assert.match(section, /for \(const door of doors\) \{[\s\S]*?door\.addEventListener\("click"/,
    "the doors are not wired in one loop");
  const click = /door\.addEventListener\("click", \(\) => \{([\s\S]*?)\}\);/.exec(section);
  assert.ok(click, "the doors have no click handler");
  assert.ok(/close\(true\)/.test(click[1]) && /open\(door\)/.test(click[1]),
    "a door click does not toggle the panel under that door");
  assert.equal(/\.click\(\)/.test(click[1]), false,
    "a door itself clicks a lane - it must only open the panel");
  assert.equal(/invoke\(/.test(click[1]), false,
    "a door invokes a command of its own");
  // Escape is heard from the DOCUMENT, not the panel (P2-5).
  assert.match(section, /doc\.addEventListener\("keydown", \(event\) => \{[\s\S]*?event\.key !== "Escape"/,
    "the panel's Escape is not on the document");
  assert.equal(/panel\.addEventListener\("keydown"/.test(section), false,
    "the panel still owns a keydown Escape, which its own re-render makes dead");
  // Focus preserved across the re-render the open itself causes.
  assert.match(section, /const keepLane = active && scroll\.contains\(active\)/,
    "the panel does not remember the focused route across a re-render");
  assert.match(section, /if \(again && typeof again\.focus === "function"\)/,
    "the panel does not put focus back on the same route");
});

/* ── 3. The three reads ──────────────────────────────────────────────────── */

function fakeWindow(answers = {}) {
  const calls = [];
  const win = {
    JARVIS: {
      url: (path) => path,
      headers: (extra) => ({ "X-Jarvis-Client": "hud", ...extra }),
    },
    fetch: async (url, init) => {
      calls.push({ url, method: (init && init.method) || "GET", headers: (init && init.headers) || {} });
      const answer = Object.prototype.hasOwnProperty.call(answers, url) ? answers[url] : null;
      if (answer === null) return { ok: false, status: 404, json: async () => ({ error: "not found" }) };
      return { ok: true, status: 200, json: async () => answer };
    },
  };
  return { win, calls };
}

const MODELS = {
  current: "qwen3.5:9b",
  previous: "qwen2.5:14b",
  installed: ["qwen3.5:9b"],
  offload: {
    available: true,
    status: "gpu",
    models: [{ name: "qwen3.5:9b", size_mb: 6100, vram_mb: 5900, on_gpu_percent: 97 }],
  },
};
const STATUS = { ollama: true, default_model: "qwen3.5:9b", lanes: [] };
const PRESETS = {
  available: true,
  chosen_preset: "general",
  chosen_model: "qwen3.5:9b",
  presets: [{ id: "general", title: "General", model: "qwen3.5:9b" }],
};

await check("the panel reads exactly /api/models, /api/status and /api/presets, all GETs", async () => {
  assert.deepEqual(P.CURRENT_MODELS_READS, ["/api/models", "/api/status", "/api/presets"]);
  const { win, calls } = fakeWindow({ "/api/models": MODELS, "/api/status": STATUS, "/api/presets": PRESETS });
  const reads = await P.readCurrentModelsOnPc(win);
  assert.deepEqual(calls.map((c) => c.url), ["/api/models", "/api/status", "/api/presets"]);
  for (const call of calls) {
    assert.equal(call.method, "GET", `${call.url} was not a GET`);
    assert.equal(call.headers["X-Jarvis-Client"], "hud", `${call.url} did not say it came from the hud`);
  }
  assert.equal(reads.models.ok, true);
  assert.equal(reads.status.ok, true);
  assert.equal(reads.presets.ok, true);
});

await check("one read the PC cannot answer leaves the other two telling the truth", async () => {
  const { win } = fakeWindow({ "/api/status": STATUS, "/api/presets": PRESETS });
  const reads = await P.readCurrentModelsOnPc(win);
  assert.equal(reads.models.ok, false, "the failed /api/models read was counted as an answer");
  assert.equal(reads.status.ok, true);
  assert.equal(reads.presets.ok, true);
  const words = P.currentModelsWords(reads);
  assert.deepEqual(words.answering.map((l) => l.text),
    ["The PC did not answer when asked which model is answering."]);
  assert.deepEqual(words.loaded.map((l) => l.text),
    ["The PC did not answer when asked what is loaded."]);
  assert.equal(words.focus[0].text, "Chosen focus preset: General (qwen3.5:9b)");
});

/* ── 4. The words: the PC's own facts, and honest absences ───────────────── */

await check("answering now: current, previous as before-that, and the default only when it differs", () => {
  const words = P.currentModelsWords({ models: { ok: true, value: MODELS },
    status: { ok: true, value: STATUS }, presets: { ok: true, value: PRESETS } });
  assert.deepEqual(words.answering.map((l) => l.text),
    ["qwen3.5:9b", "Before that: qwen2.5:14b"]);
  const other = P.currentModelsWords({
    models: { ok: true, value: { ...MODELS, current: "qwen3.5:9b", previous: "qwen2.5:14b" } },
    status: { ok: true, value: { ...STATUS, default_model: "qwen2.5:14b" } },
    presets: { ok: true, value: PRESETS },
  });
  assert.deepEqual(other.answering.map((l) => l.text),
    ["qwen3.5:9b", "Before that: qwen2.5:14b", "The PC's default model is qwen2.5:14b."]);
});

await check("answering now: a body with no current model is said, never filled in", () => {
  const words = P.currentModelsWords({
    models: { ok: true, value: { installed: ["qwen3.5:9b"] } },
    status: { ok: true, value: STATUS }, presets: { ok: true, value: PRESETS },
  });
  assert.deepEqual(words.answering.map((l) => l.text),
    ["The PC did not name a model it is answering with."]);
  assert.equal(words.answering[0].dim, true);
});

await check("loaded right now: each model with its own size, graphics-card share and GPU percent", () => {
  const words = P.currentModelsWords({ models: { ok: true, value: MODELS },
    status: { ok: true, value: STATUS }, presets: { ok: true, value: PRESETS } });
  assert.deepEqual(words.loaded.map((l) => l.text),
    ["qwen3.5:9b \u2014 6100 MB in memory, 5900 MB of that on the graphics card, 97% on the GPU"]);
  assert.equal(words.loaded[0].dim, false);
});

await check("loaded right now: nothing loaded, or nothing available, says the owner's sentence", () => {
  const empty = P.currentModelsWords({
    models: { ok: true, value: { ...MODELS, offload: { available: true, status: "idle", models: [] } } },
    status: { ok: true, value: STATUS }, presets: { ok: true, value: PRESETS },
  });
  assert.deepEqual(empty.loaded.map((l) => l.text), ["The PC did not say any model is in memory right now."]);
  assert.equal(empty.loaded[0].dim, true);
  const unavailable = P.currentModelsWords({
    models: { ok: true, value: { current: "qwen3.5:9b" } },   // an older PC with no offload block
    status: { ok: true, value: STATUS }, presets: { ok: true, value: PRESETS },
  });
  assert.deepEqual(unavailable.loaded.map((l) => l.text),
    ["The PC did not say any model is in memory right now."],
    "a missing offload block was filled in as a loaded model");
  const refused = P.currentModelsWords({
    models: { ok: true, value: { ...MODELS, offload: { available: false, status: "unknown", models: [] } } },
    status: { ok: true, value: STATUS }, presets: { ok: true, value: PRESETS },
  });
  assert.deepEqual(refused.loaded.map((l) => l.text),
    ["The PC did not say any model is in memory right now."]);
});

await check("loaded right now: a row with no numbers is its name, never invented numbers", () => {
  const words = P.currentModelsWords({
    models: { ok: true, value: { ...MODELS,
      offload: { available: true, models: [{ name: "qwen3.5:9b" }, { size_mb: 10 }] } } },
    status: { ok: true, value: STATUS }, presets: { ok: true, value: PRESETS },
  });
  assert.deepEqual(words.loaded.map((l) => l.text),
    ["qwen3.5:9b", "(the PC did not name it) \u2014 10 MB in memory"]);
});

await check("chosen focus preset: the PC's choice and title, or the owner's no-choice sentence", () => {
  const chosen = P.currentModelsWords({ models: { ok: true, value: MODELS },
    status: { ok: true, value: STATUS }, presets: { ok: true, value: PRESETS } });
  assert.deepEqual(chosen.focus.map((l) => l.text), ["Chosen focus preset: General (qwen3.5:9b)"]);
  const none = P.currentModelsWords({ models: { ok: true, value: MODELS },
    status: { ok: true, value: STATUS }, presets: { ok: true, value: { ...PRESETS, chosen_preset: null, chosen_model: null } } });
  assert.deepEqual(none.focus.map((l) => l.text), ["No preset chosen yet \u2014 the PC routes on its own."]);
  const unknownTitle = P.currentModelsWords({ models: { ok: true, value: MODELS },
    status: { ok: true, value: STATUS }, presets: { ok: true, value: {
      available: true, chosen_preset: "custom-one", chosen_model: "m", presets: [] } } });
  assert.deepEqual(unknownTitle.focus.map((l) => l.text),
    ["Chosen focus preset: custom-one (m)"], "an unnamed chosen preset was blanked instead of named by its id");
  const noRoute = P.currentModelsWords({ models: { ok: true, value: MODELS },
    status: { ok: true, value: STATUS }, presets: { ok: false, error: "the PC answered 404" } });
  assert.deepEqual(noRoute.focus.map((l) => l.text),
    ["The PC did not answer when asked which focus preset is chosen."]);
});

/* ── 5. The route: the page's lanes, read back, never copied ─────────────── */

await check("the routes come from the page's own #lanes buttons and click them", () => {
  assert.ok(section.includes('box.querySelectorAll(".lane")'),
    "the panel does not read the page's #lanes buttons");
  assert.ok(section.includes("again.source.click();"),
    "a route does not click the page's own lane button");
  assert.match(section, /pressed: source\.getAttribute\("aria-pressed"\) === "true"/,
    "the pressed mark is not read off the page's own button");
  assert.equal((section.match(/setAttribute\("aria-pressed"/g) || []).length, 1,
    "the panel sets a pressed state anywhere other than from the page's own mark");
  assert.ok(section.includes('button.setAttribute("aria-pressed", row.pressed ? "true" : "false");'),
    "the pressed state is not the page's own");
  // The panel carries NO lane names: the only list is #lanes.
  for (const name of ["jarvis-escalate", "jarvis-critic", "jarvis-bulk", '"auto"', '"local"']) {
    assert.equal(section.includes(name), false,
      `the panel copied a lane into itself: ${name}`);
  }
  assert.ok(section.includes("The next message only: it raises no card and switches no model."),
    "the panel does not say the route is only a route");
});

await check("the route re-reads the page after the click, so it cannot mark a refused route", () => {
  const click = /again\.source\.click\(\);([\s\S]*?)\}\);/.exec(section);
  assert.ok(click, "the route click handler is missing");
  assert.ok(/render\(\);/.test(click[1]), "the panel does not repaint from the page after routing");
  assert.equal(/setAttribute/.test(click[1]), false,
    "the click handler writes a pressed state itself");
});

/* ── 6. No new route, command or card ────────────────────────────────────── */

await check("the panel names no route but its three reads, and sends no write", () => {
  const paths = [...section.matchAll(/"(\/api\/[^"]*)"/g)].map((m) => m[1]);
  assert.deepEqual([...new Set(paths)].sort(), ["/api/models", "/api/presets", "/api/status"]);
  assert.equal(/method:\s*"POST"/.test(section), false, "the panel sends a POST");
  assert.equal(/invoke\(/.test(section), false, "the panel invokes a Tauri command");
  assert.ok(section.includes("no approval card"), "the panel does not say it raises no card");
  assert.ok(section.includes("async function refresh()") && section.includes("readCurrentModelsOnPc(win)"),
    "Refresh does not re-read the same three reads");
});

await check("Rust's fixed read list gains /api/models and refuses every model write", () => {
  const list = /HUD_GET_PATHS: \[&str; \d+\] = \[([\s\S]*?)\];/.exec(rust)[1];
  const allowed = [...list.matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  assert.ok(allowed.includes("/api/models"), "/api/models is not on the HUD's fixed read list");
  for (const path of ["/api/models/switch", "/api/models/install", "/api/models/rollback",
    "/api/models?recommend=1", "/api/models/"]) {
    assert.equal(allowed.includes(path), false, `${path} is on the HUD's read list`);
    assert.ok(rust.includes(`"${path}",`), `the negative pin for ${path} is missing`);
  }
  assert.match(rust, /allowed_get\("\/api\/models"\)\.as_deref\(\), Some\("\/api\/models"\)/,
    "the positive pin for /api/models is missing");
  // The shell's own comment must not still claim the old, shorter list.
  assert.ok(bootstrap.includes("models, and /retrieve?q="),
    "hud_bootstrap.js's read-list comment was not updated");
});

/* ── 7. The served copies ────────────────────────────────────────────────── */

await check("the page and hud-presets.js are byte-identical in all three served copies", () => {
  const pairs = [
    ["jarvis_hud.html", ["jarvis-desktop/src", "backend", "jarvis-backend"]],
    ["hud-presets.js", ["jarvis-desktop/src", "backend/static", "jarvis-backend"]],
  ];
  for (const [name, places] of pairs) {
    const hashes = places.map((place) =>
      createHash("sha256").update(readFileSync(join(ROOT, place, name))).digest("hex"));
    assert.equal(new Set(hashes).size, 1,
      `${name} differs across ${places.join(", ")}: ${hashes.map((h) => h.slice(0, 8)).join(" ")}`);
  }
});

console.log(fails ? `\n${fails} failed` : `\nall ${passed} Current Models checks passed`);
process.exit(fails ? 1 : 0);
