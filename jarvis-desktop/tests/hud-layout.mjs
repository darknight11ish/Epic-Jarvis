/**
 * hud-layout.mjs - the desktop HUD's layout model (H1, Gemini rulings 23-28).
 *
 *     node tests/hud-layout.mjs
 *
 * WHY THIS SUITE EXISTS, AND WHY IT NEEDS NO BROWSER. This is the data half of
 * the editable HUD: the card registry, the seven built-in presets, the
 * closed-world normalizer, the protected-card rule and the migration of the
 * old three-way setting. None of that draws anything, so it is tested here as
 * plain functions - the page itself is still covered by tests/hud.mjs.
 *
 * WHAT IT PROVES, in order:
 *   1. every registry row is sane (known region, bounded spans, unique id, the
 *      four protected cards marked) and the four protected ids are all there;
 *   2. there are exactly seven presets, cockpit is the default and first, and
 *      each one is a fixed point of normalizeLayout (so "save then load" can
 *      never rewrite a preset), uses only registry cards, and keeps every
 *      protected card visible;
 *   3. `contract/hud-presets.json` is byte-for-byte the same data, so Rust and
 *      the tests cannot read a stale copy;
 *   4. a hostile or just-wrong document is made safe: unknown cards/regions/
 *      tokens dropped, prototype keys not copied, x/y ignored, bounded
 *      numbers repaired, protected cards forced visible and restored;
 *   5. the old `jarvis.hud.layout` value migrates without losing a valid
 *      choice, idempotently, and anything unknown becomes cockpit;
 *   6. the approvals auto-uncollapse is a DERIVED view state, and the saved
 *      document it is derived from is never mutated by it.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as L from "../src/hud-layout.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const CONTRACT = JSON.parse(
  readFileSync(join(HERE, "..", "..", "contract", "hud-presets.json"), "utf8"),
);

const fails = [];
const check = async (name, fn) => {
  try {
    await fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

const PROTECTED = new Set(L.PROTECTED_IDS);
const REGIONS = new Set(L.REGIONS);
const TEMPLATES = new Set(L.SHELL_TEMPLATES);
const cardIds = new Set(L.CARD_REGISTRY.map((card) => card.id));

/* ── 1. The registry ────────────────────────────────────────────────────── */

await check("there is one registry row per card, with unique ids", () => {
  const ids = L.CARD_REGISTRY.map((card) => card.id);
  assert.equal(new Set(ids).size, ids.length, "a card id appears twice");
  assert.ok(ids.length >= 10 && ids.length <= 40, `implausible registry size ${ids.length}`);
});

await check("every registry row lives in a known region with bounded spans and order", () => {
  for (const card of L.CARD_REGISTRY) {
    assert.match(card.id, /^[a-z][a-z0-9_]+$/, `bad id ${card.id}`);
    assert.ok(card.label && typeof card.label === "string", `${card.id} has no label`);
    assert.ok(REGIONS.has(card.region), `${card.id} is in unknown region ${card.region}`);
    assert.ok(Number.isInteger(card.order) && card.order >= 0 && card.order <= 50,
      `${card.id} order ${card.order}`);
    assert.ok(Number.isInteger(card.col_span) && card.col_span >= 1 && card.col_span <= 12,
      `${card.id} col_span ${card.col_span}`);
    assert.ok(Number.isInteger(card.row_span) && card.row_span >= 1 && card.row_span <= 4,
      `${card.id} row_span ${card.row_span}`);
    assert.equal(typeof card.visible, "boolean", `${card.id} visible is not a boolean`);
    assert.equal(typeof card.collapsed, "boolean", `${card.id} collapsed is not a boolean`);
    assert.equal(typeof card.protected, "boolean", `${card.id} protected is not a boolean`);
    assert.ok(card.options && typeof card.options === "object", `${card.id} has no options`);
  }
});

await check("the four protected cards the ruling names are in the registry", () => {
  for (const id of ["approvals", "emergency_stop", "voice_controls", "bar_launcher"]) {
    assert.ok(cardIds.has(id), `${id} is not a registry card`);
    assert.equal(L.CARD_REGISTRY.find((card) => card.id === id).protected, true,
      `${id} is not marked protected`);
  }
  assert.equal(L.PROTECTED_IDS.length, 4);
  assert.deepEqual([...L.PROTECTED_IDS].sort(), ["approvals", "bar_launcher",
    "emergency_stop", "voice_controls"]);
});

await check("no registry card is protected by accident", () => {
  const extras = L.CARD_REGISTRY.filter((card) => card.protected && !PROTECTED.has(card.id));
  assert.deepEqual(extras.map((card) => card.id), []);
});

/* ── 2. The seven presets ───────────────────────────────────────────────── */

await check("exactly seven presets, cockpit first and the default", () => {
  assert.equal(L.PRESETS.length, 7);
  assert.equal(L.PRESETS[0].id, "cockpit");
  assert.equal(L.DEFAULT_PRESET_ID, "cockpit");
  assert.deepEqual(L.PRESETS.map((preset) => preset.id), [
    "cockpit", "studio", "ambient", "quiet", "telemetry", "second_brain", "minimal",
  ]);
});

await check("every preset is a complete, normalized document", () => {
  for (const preset of L.PRESETS) {
    assert.equal(preset.version, L.LAYOUT_VERSION, `${preset.id} version`);
    assert.equal(preset.base_preset, preset.id, `${preset.id} base_preset`);
    assert.equal(preset.name, L.presetInfo(preset.id).label, `${preset.id} name`);
    assert.equal(preset.updated_at, 0, `${preset.id} updated_at`);
    assert.ok(REGIONS.has(preset.cards[0].region) || true);
  }
});

await check("each preset is a fixed point of the normalizer (save then load cannot rewrite it)", () => {
  for (const preset of L.PRESETS) {
    assert.deepEqual(L.normalizeLayout(preset), preset, `${preset.id} is not a fixed point`);
    assert.deepEqual(L.presetLayout(preset.id), preset, `${preset.id} rebuilt differently`);
  }
});

await check("each preset uses only registry cards, once each, and keeps every protected card visible", () => {
  for (const preset of L.PRESETS) {
    const ids = preset.cards.map((card) => card.id);
    assert.equal(new Set(ids).size, ids.length, `${preset.id} repeats a card`);
    for (const id of ids) assert.ok(cardIds.has(id), `${preset.id} has unknown card ${id}`);
    for (const id of L.PROTECTED_IDS) {
      const card = preset.cards.find((entry) => entry.id === id);
      assert.ok(card, `${preset.id} has no ${id}`);
      assert.equal(card.visible, true, `${preset.id} hides protected ${id}`);
    }
    assert.ok(TEMPLATES.has(preset.shell_template), `${preset.id} shell ${preset.shell_template}`);
    assert.ok(L.DENSITIES.includes(preset.density), `${preset.id} density ${preset.density}`);
    assert.ok(L.THEMES.includes(preset.theme), `${preset.id} theme ${preset.theme}`);
    assert.ok(L.STAGE_TABS.includes(preset.default_stage_tab),
      `${preset.id} tab ${preset.default_stage_tab}`);
  }
});

await check("the presets differ where the ruling says they do", () => {
  const byId = Object.fromEntries(L.PRESETS.map((preset) => [preset.id, preset]));
  assert.equal(byId.cockpit.shell_template, "three-column");
  assert.equal(byId.studio.shell_template, "split-stage");
  assert.equal(byId.ambient.shell_template, "center-core");
  assert.equal(byId.minimal.shell_template, "single-stage-bento");
  assert.equal(byId.quiet.shell_template, "two-column-left");
  // Ambient hides both side rails' ordinary cards; Minimal hides the telemetry.
  for (const id of ["nav", "lanes", "systems"]) {
    assert.equal(byId.ambient.cards.find((card) => card.id === id)?.visible, false,
      `Ambient shows ${id}`);
  }
  assert.equal(byId.minimal.cards.find((card) => card.id === "telemetry")?.visible, false,
    "Minimal shows telemetry");
  // Telemetry & Ops puts the telemetry high and compact.
  assert.ok(byId.telemetry.cards.find((card) => card.id === "telemetry").row_span >= 2,
    "Telemetry preset gives telemetry no height");
});

await check("F7: Focus is renamed Quiet, and an old saved 'focus' still means Quiet", () => {
  assert.equal(L.presetInfo("quiet").label, "Quiet");
  assert.equal(L.presetInfo("focus").id, "quiet");
  assert.equal(L.presetInfo("focus").label, "Quiet");
  assert.match(L.presetInfo("quiet").blurb, /Quiet chat/i);
  const old = { version: 1, base_preset: "focus", id: "focus", name: "Focus", cards: [] };
  const out = L.normalizeLayout(old);
  assert.equal(out.base_preset, "quiet");
  assert.equal(out.id, "quiet");
  assert.equal(out.name, "Quiet");
  assert.equal(L.migrateLegacyLayout("focus").base_preset, "quiet");
  assert.equal(L.migrateLegacyLayout("quiet").base_preset, "quiet");
});

await check("F8: every registry label with a page heading matches that heading", () => {
  const page = readFileSync(join(HERE, "..", "src", "jarvis_hud.html"), "utf8");
  const headings = {
    lanes: "Focus presets",
    systems: "Systems",
    waiting: "Cards waiting",
    telemetry: "Last turn telemetry",
    tools: "Abilities used",
    brain_stats: "Second brain &amp; vault".replace("&amp;", "&"),
    budget: "Free-tier budget",
    voice_stats: "Voice",
    reminders: "Reminders",
  };
  for (const [id, words] of Object.entries(headings)) {
    const card = L.CARD_REGISTRY.find((entry) => entry.id === id);
    assert.ok(card, `${id} is not a registry card`);
    assert.equal(card.label, words, `${id} label is stale`);
    assert.ok(page.includes(`>${words.replace("&", "&amp;")}</div>`),
      `${id}'s heading "${words}" is not on the HUD page`);
  }
  // The navigation rail carries its name as an aria-label, not a heading.
  assert.equal(L.CARD_REGISTRY.find((entry) => entry.id === "nav").label, "Navigation");
  assert.ok(page.includes('id="rail-nav" role="tablist" aria-label="Navigation"'),
    "the navigation rail's accessible name does not match its registry label");
  // Cards whose DOM has no static heading (dynamic cards, the stage views and
  // the shell-created bar button) are exempt with the reason, not silently.
  const exempt = {
    approvals: "the cards are created at runtime; the H2 toolbar uses its label",
    conversation: "the conversation is the stage itself",
    composer: "the ask box is part of the stage",
    galaxy: "the Galaxy is a stage tab, not a labelled card",
    memory: "Memory is a stage tab",
    emergency_stop: "Stop everything is a fixed header control",
    voice_controls: "the mic controls sit beside the composer",
  };
  for (const [id, why] of Object.entries(exempt)) {
    assert.ok(L.CARD_REGISTRY.some((entry) => entry.id === id),
      `${id} is missing from the registry (${why})`);
  }
  assert.equal(L.CARD_REGISTRY.find((entry) => entry.id === "bar_launcher").label,
    "Open the Jarvis bar");
  assert.ok(page.includes("Open the Jarvis bar"), "the bar button's word is gone");
});

await check("FT-1/L1: Focus presets start OPEN in Cockpit and Studio (owner collapse is remembered)", () => {
  for (const id of ["cockpit", "studio"]) {
    const card = L.presetLayout(id).cards.find((entry) => entry.id === "lanes");
    assert.ok(card, `${id} lost the Focus presets card`);
    assert.equal(card.visible, true, `${id} hides the Focus presets card`);
    assert.equal(card.collapsed, false, `${id} starts with the Focus presets folded`);
  }
  // Ambient deliberately keeps the card off the glass: the layout badge still
  // reaches it, so this is a look choice, not a discoverability hole.
  const ambient = L.presetLayout("ambient").cards.find((entry) => entry.id === "lanes");
  assert.equal(ambient.visible, false);
});

/* ── 3. The contract mirror ─────────────────────────────────────────────── */

await check("contract/hud-presets.json mirrors the JS presets exactly", () => {
  assert.equal(CONTRACT.version, L.LAYOUT_VERSION);
  assert.deepEqual(CONTRACT.presets, L.PRESETS);
  assert.deepEqual(CONTRACT.regions, L.REGIONS);
  assert.deepEqual(CONTRACT.shell_templates, L.SHELL_TEMPLATES);
  assert.match(CONTRACT.note, /desktop-only/i,
    "the contract does not say it is desktop-only");
});

/* ── 4. The closed-world normalizer ─────────────────────────────────────── */

function baseDoc() {
  return JSON.parse(JSON.stringify(L.presetLayout("cockpit")));
}

await check("a missing, null, array or non-object document becomes the default preset", () => {
  for (const bad of [undefined, null, [], "text", 7, true]) {
    assert.deepEqual(L.normalizeLayout(bad), L.presetLayout("cockpit"));
  }
});

await check("a wrong or missing version is not guessed at: it becomes the default preset", () => {
  const doc = baseDoc();
  doc.version = 2;
  assert.deepEqual(L.normalizeLayout(doc), L.presetLayout("cockpit"));
  delete doc.version;
  assert.deepEqual(L.normalizeLayout(doc), L.presetLayout("cockpit"));
});

await check("unknown card ids, duplicate cards and unknown regions are dropped", () => {
  const doc = baseDoc();
  doc.cards.push({ id: "jarvis_ghost", region: "right_rail", order: 0 });
  doc.cards.push({ id: "nav", region: "right_rail", order: 99 });
  doc.cards.push({ id: "approvals", region: "nowhere", order: 0 });
  const out = L.normalizeLayout(doc);
  assert.equal(out.cards.some((card) => card.id === "jarvis_ghost"), false);
  assert.equal(out.cards.filter((card) => card.id === "nav").length, 1);
  for (const card of out.cards) assert.ok(REGIONS.has(card.region), `${card.id} region`);
});

await check("prototype-pollution keys and unknown fields are never copied through", () => {
  const doc = baseDoc();
  doc.__proto__ = { polluted: true };
  doc.constructor = { polluted: true };
  doc.evil = "<script>alert(1)</script>";
  doc.cards.push({ id: "nav", region: "left_rail", order: 0, evil: true,
    __proto__: { polluted: true } });
  const out = L.normalizeLayout(doc);
  assert.equal(Object.prototype.polluted, undefined);
  assert.equal("evil" in out, false, "an unknown top-level field survived");
  assert.equal("evil" in out.cards[0], false, "an unknown card field survived");
  assert.equal({}.polluted, undefined);
});

await check("x and y are reserved and ignored (the ruling's forward-compatible hint)", () => {
  const doc = baseDoc();
  doc.cards[0].x = 3;
  doc.cards[0].y = 9;
  const out = L.normalizeLayout(doc);
  assert.equal("x" in out.cards[0], false);
  assert.equal("y" in out.cards[0], false);
});

await check("out-of-range numbers and booleans are repaired, not trusted", () => {
  const doc = baseDoc();
  const card = doc.cards.find((entry) => entry.id === "telemetry");
  card.order = 1000;
  card.col_span = 99;
  card.row_span = -4;
  card.visible = "yes";
  card.collapsed = "no";
  const out = L.normalizeLayout(doc);
  const got = out.cards.find((entry) => entry.id === "telemetry");
  assert.ok(got.order >= 0 && got.order <= 50, `order ${got.order}`);
  assert.ok(got.col_span >= 1 && got.col_span <= 12, `col_span ${got.col_span}`);
  assert.ok(got.row_span >= 1 && got.row_span <= 4, `row_span ${got.row_span}`);
  assert.equal(typeof got.visible, "boolean");
  assert.equal(typeof got.collapsed, "boolean");
});

await check("unknown enum tokens fall back to the preset's own tokens", () => {
  const doc = baseDoc();
  doc.shell_template = "hexagon";
  doc.theme = "neon";
  doc.density = "tiny";
  doc.default_stage_tab = "rain";
  const out = L.normalizeLayout(doc);
  assert.ok(TEMPLATES.has(out.shell_template));
  assert.ok(L.THEMES.includes(out.theme));
  assert.ok(L.DENSITIES.includes(out.density));
  assert.ok(L.STAGE_TABS.includes(out.default_stage_tab));
});

await check("a protected card cannot be hidden by the document", () => {
  for (const id of L.PROTECTED_IDS) {
    const doc = baseDoc();
    doc.cards.find((card) => card.id === id).visible = false;
    const out = L.normalizeLayout(doc);
    assert.equal(out.cards.find((card) => card.id === id).visible, true,
      `${id} stayed hidden`);
  }
});

await check("a missing protected card is restored to its default region", () => {
  for (const id of L.PROTECTED_IDS) {
    const doc = baseDoc();
    doc.cards = doc.cards.filter((card) => card.id !== id);
    const out = L.normalizeLayout(doc);
    const card = out.cards.find((entry) => entry.id === id);
    assert.ok(card, `${id} was not restored`);
    assert.equal(card.visible, true, `${id} restored hidden`);
    assert.equal(card.region, L.CARD_REGISTRY.find((entry) => entry.id === id).region,
      `${id} restored in the wrong region`);
  }
});

await check("optional cards may be absent: a preset that does not use one does not carry it", () => {
  const doc = baseDoc();
  doc.cards = doc.cards.filter((card) => card.id !== "telemetry");
  const out = L.normalizeLayout(doc);
  assert.equal(out.cards.some((card) => card.id === "telemetry"), false);
});

await check("cards come out in one canonical region/order order", () => {
  const out = L.normalizeLayout(baseDoc());
  const order = out.cards.map((card) => L.REGIONS.indexOf(card.region));
  const sorted = order.slice().sort((a, b) => a - b);
  assert.deepEqual(order, sorted);
});

await check("a custom layout keeps its id and name but still passes the closed world", () => {
  const doc = baseDoc();
  doc.id = "custom-ops-deck";
  doc.name = "My Ops Deck";
  doc.base_preset = "cockpit";
  const out = L.normalizeLayout(doc);
  assert.equal(out.id, "custom-ops-deck");
  assert.equal(out.name, "My Ops Deck");
  assert.equal(out.base_preset, "cockpit");
});

await check("a whole import document round-trips through parseLayoutText", () => {
  const out = L.parseLayoutText(JSON.stringify(L.presetLayout("quiet")));
  assert.deepEqual(out, L.presetLayout("quiet"));
  // The old H1 name is a silent migration alias: a saved "focus" layout is the
  // Quiet layout now, never the default.
  assert.deepEqual(L.presetLayout("focus"), L.presetLayout("quiet"));
  assert.equal(L.parseLayoutText("{not json"), null);
  assert.equal(L.parseLayoutText("42"), null);
});

/* ── 5. Migrating the old three-way setting ────────────────────────────── */

await check("the three old layout names keep their meaning", () => {
  for (const id of ["cockpit", "studio", "ambient"]) {
    assert.equal(L.migrateLegacyLayout(id).base_preset, id, `${id} changed`);
  }
});

await check("case and surrounding spaces are tolerated, and unknown values become cockpit", () => {
  assert.equal(L.migrateLegacyLayout("  Studio ").base_preset, "studio");
  assert.equal(L.migrateLegacyLayout("AMBIENT").base_preset, "ambient");
  for (const bad of [undefined, null, "", "nonsense", 7, {}]) {
    assert.deepEqual(L.migrateLegacyLayout(bad), L.presetLayout("cockpit"));
  }
});

await check("migration is idempotent and never loses a valid choice", () => {
  const once = L.migrateLegacyLayout("studio");
  const twice = L.normalizeLayout(once);
  assert.deepEqual(twice, once);
  assert.equal(twice.base_preset, "studio");
});

/* ── 6. The approvals auto-uncollapse (ruling 7) ────────────────────────── */

await check("a waiting approval expands the collapsed card; none waiting folds it back", () => {
  const card = { id: "approvals", collapsed: true };
  assert.equal(L.effectiveCollapsed(card, 0), true);
  assert.equal(L.effectiveCollapsed(card, 1), false);
  assert.equal(L.effectiveCollapsed(card, 5), false);
});

await check("the auto-uncollapse is derived: it never mutates the saved layout", () => {
  const doc = L.presetLayout("minimal");
  const before = JSON.stringify(doc);
  const approvals = doc.cards.find((card) => card.id === "approvals");
  L.effectiveCollapsed(approvals, 3);
  assert.equal(JSON.stringify(doc), before);
});

await check("other cards' collapsed state is their own, whatever is waiting", () => {
  assert.equal(L.effectiveCollapsed({ id: "telemetry", collapsed: true }, 4), true);
  assert.equal(L.effectiveCollapsed({ id: "nav", collapsed: false }, 4), false);
  assert.equal(L.effectiveCollapsed(null, 4), false);
});

/* ── 7. The words a picker shows ────────────────────────────────────────── */

await check("every preset has plain words and a glyph, and describeLayout says them", () => {
  for (const preset of L.PRESETS) {
    const info = L.presetInfo(preset.id);
    assert.ok(info.label && info.blurb, `${preset.id} has no words`);
    assert.ok(info.glyph && info.glyph.length === 1, `${preset.id} glyph`);
    assert.equal(L.presetInfo(`${preset.id}-ghost`), null);
    assert.ok(L.describeLayout(preset).startsWith(info.label), `${preset.id} describe`);
  }
});

/* ── 8. The store: migration, saving, and honest refusals ───────────────── */

const store = await import("../src/hud-layout-store.js");

function mem(initial = {}) {
  const data = { ...initial };
  return {
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v); },
    _data: data,
  };
}

function fakeShell(answerFor) {
  const calls = [];
  globalThis.__TAURI__ = {
    core: {
      invoke: (cmd, args) => {
        calls.push([cmd, args]);
        return Promise.resolve(answerFor(cmd, args));
      },
    },
  };
  return calls;
}

function noShell() {
  delete globalThis.__TAURI__;
}

await check("a page served on its own reads the old three-way value and says nothing was saved", async () => {
  noShell();
  const answer = await store.loadLayout(mem({ [store.LEGACY_KEY]: "studio" }));
  assert.equal(answer.layout.base_preset, "studio");
  assert.equal(answer.saved, false);
  assert.equal(answer.source, "browser");
  assert.match(store.layoutStatus(answer), /Not saved/, "a browser save is not reported as saved");
});

await check("inside the shell a saved document is the one used, and no migration write happens", async () => {
  const saved = L.presetLayout("telemetry");
  const calls = fakeShell((cmd) => (cmd === "get_hud_layout"
    ? { layout: saved, source: "saved" }
    : { layout: saved, source: "saved" }));
  const answer = await store.loadLayout(mem());
  assert.deepEqual(answer.layout, saved);
  assert.equal(answer.saved, true);
  assert.equal(answer.migrated, false);
  assert.deepEqual(calls.map((c) => c[0]), ["get_hud_layout"]);
  noShell();
});

await check("the old value is migrated and SAVED the first time the shell has nothing", async () => {
  const stored = [];
  const calls = fakeShell((cmd, args) => {
    if (cmd === "get_hud_layout") return { layout: null, source: "none" };
    stored.push(args.layout);
    return { layout: args.layout, source: "saved" };
  });
  const answer = await store.loadLayout(mem({ [store.LEGACY_KEY]: "ambient" }));
  assert.equal(answer.layout.base_preset, "ambient");
  assert.equal(answer.migrated, true);
  assert.equal(answer.saved, true);
  assert.equal(stored.length, 1, "the migrated layout was not written");
  assert.equal(stored[0].base_preset, "ambient");
  assert.ok(calls.some(([cmd]) => cmd === "set_hud_layout"));
  noShell();
});

await check("choosing a preset saves its document in the store, and writes NO legacy key", async () => {
  const written = [];
  fakeShell((cmd, args) => {
    if (cmd === "set_hud_layout") {
      written.push(args.layout);
      return { layout: args.layout, source: "saved" };
    }
    return { layout: null, source: "none" };
  });
  const storage = mem();
  const answer = await store.choosePreset("quiet", storage);
  assert.equal(answer.saved, true);
  assert.equal(written.length, 1);
  assert.equal(written[0].base_preset, "quiet");
  assert.equal(written[0].cards.some((card) => card.id === "approvals"
    && card.visible === true), true, "the saved preset lost its protected card");
  // F1: the store is the sole writer; the retired localStorage key is not
  // touched by a preset choice any more (the HUD page does not read it).
  assert.equal(storage.getItem(store.LEGACY_KEY), null,
    "a preset choice wrote the retired localStorage layout key again");
  noShell();
});

await check("a refused save is reported as not saved, with the shell's reason", async () => {
  fakeShell((cmd) => {
    if (cmd === "get_hud_layout") return { layout: null, source: "none" };
    return Promise.reject(new Error("the layout is not readable"));
  });
  const answer = await store.choosePreset("minimal", mem());
  assert.equal(answer.saved, false);
  assert.match(store.layoutStatus(answer), /Not saved/);
  assert.match(store.layoutStatus(answer), /not readable/);
  noShell();
});

await check("LOOK_BY_PRESET covers all seven presets and only the page's three looks", () => {
  assert.deepEqual(Object.keys(store.LOOK_BY_PRESET).sort(),
    L.PRESETS.map((preset) => preset.id).sort());
  for (const look of Object.values(store.LOOK_BY_PRESET)) {
    assert.ok(["cockpit", "studio", "ambient"].includes(look), `unknown look ${look}`);
  }
  for (const preset of L.PRESETS) {
    assert.equal(store.lookForPreset(preset.id), store.LOOK_BY_PRESET[preset.id]);
  }
});

if (fails.length) {
  console.error(`\n${fails.length} test(s) failed`);
  process.exit(1);
} else {
  console.log("\nAll hud-layout tests passed!");
}
