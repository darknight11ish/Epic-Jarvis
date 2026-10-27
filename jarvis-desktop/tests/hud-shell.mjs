/**
 * hud-shell.mjs - H3 of the editable-HUD design (2026-10-22; Gemini ruling Q5):
 * the preset's shell, density and opening tab are RENDERED, the LOOKS alias map
 * and the inert contract fields are gone, and the owner's layout library is a
 * bounded, closed-world part of the same one saved document.
 *
 * WHAT IT PROVES, in order:
 *   1. every shell, density, region and stage-tab token the model can say has a
 *      real DOM target on the HUD page (the vocabulary -> DOM mapping test),
 *      and the page cannot say a token the model does not know (closed-world in
 *      both directions);
 *   2. the contract carries no colour theme and no spans on the seven fixed
 *      cards (Q5 item 2), and the Quiet naming is in place;
 *   3. the layout library helpers (duplicate / rename / delete / apply /
 *      export / import) are bounded, closed-world and never lose the four
 *      protected cards;
 *   4. the retired things stay retired (LOOKS, lookForPreset, data-hud-layout,
 *      jarvis:hud-look, the legacy localStorage road) - source pins;
 *   5. copy/paste JSON is the only move path: no file input, no blob:, no
 *      object URL, no network, no new capability/command, one write only.
 *
 * Pure node; no browser needed.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import * as L from "../src/hud-layout.js";
import * as store from "../src/hud-layout-store.js";
import * as P from "../src/hud-presets.js";
import { CARD_DOM, FIXED_IDS } from "../src/hud-edit.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const TAURI = join(HERE, "..", "src-tauri");

const ROOT = join(HERE, "..", "..");
const DESKTOP = join(ROOT, "jarvis-desktop");
/** Read a file under jarvis-desktop/ (the page and its modules). */
const read = (relative) => readFileSync(join(DESKTOP, relative), "utf8");
const page = read("src/jarvis_hud.html");
const bootstrap = read("src-tauri/src/hud_bootstrap.js");
const editSrc = read("src/hud-edit.js");
const storeSrc = read("src/hud-layout-store.js");
const modelSrc = read("src/hud-layout.js");
const presetsSrc = read("src/hud-presets.js");
const settings = read("src/settings.html");
const settingsModule = read("src/hud-window-settings.js");
const contract = JSON.parse(readFileSync(join(ROOT, "contract/hud-presets.json"), "utf8"));

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

const FIXED = new Set([
  "emergency_stop", "voice_controls", "conversation", "composer",
  "galaxy", "reminders", "memory",
]);

/* ── 1. Vocabulary -> DOM, both directions ──────────────────────────────── */

await check("H3: every shell has a real CSS block on the page, and no stray shell exists", () => {
  for (const shell of L.SHELL_TEMPLATES) {
    assert.ok(page.includes(`html[data-hud-shell="${shell}"]`),
      `shell "${shell}" has no CSS rule on the page`);
  }
  const found = new Set();
  for (const match of page.matchAll(/data-hud-shell="([a-z-]+)"/g)) found.add(match[1]);
  // The body also carries an initial value: every value on the page must be a
  // token the model knows.
  for (const token of found) {
    assert.ok(L.SHELL_TEMPLATES.includes(token), `the page says shell "${token}", a stranger`);
  }
});

await check("H3: every density has a CSS block and every page density is a known token", () => {
  for (const density of L.DENSITIES) {
    assert.ok(page.includes(`html[data-hud-density="${density}"]`),
      `density "${density}" has no CSS rule on the page`);
  }
  for (const match of page.matchAll(/data-hud-density="([a-z]+)"/g)) {
    assert.ok(L.DENSITIES.includes(match[1]), `the page says density "${match[1]}"`);
  }
});

await check("H3: every stage tab the model opens on has a page control (talk included)", () => {
  const targets = {
    talk: 'data-view="talk"',
    galaxy: 'data-view="brain"',
    today: 'data-hud-tab-choice="today"',
    reminders: 'data-hud-tab-choice="reminders"',
    memory: 'data-hud-tab-choice="memory"',
    telemetry: 'data-hud-tab-choice="telemetry"',
  };
  for (const tab of L.STAGE_TABS) {
    assert.ok(targets[tab], `no DOM expectation written for STAGE_TABS "${tab}"`);
    assert.ok(page.includes(targets[tab]), `tab "${tab}" has no page control (${targets[tab]})`);
  }
  // The page's mapping must exist and handle the view tabs, not only the five
  // inspector tabs (Q5: align STAGE_TABS "talk" with the page).
  assert.match(editSrc + page, /openDefaultTab/);
  assert.match(page, /function openDefaultTab/);
  assert.match(page, /jarvis:hud-shell/);
  assert.match(page, /previewFacts/);
});

await check("H3: every region a layout can name has a DOM home", () => {
  const homes = {
    header: 'class="stage-bar"',
    left_rail: 'id="rail-left"',
    stage_top: 'data-hud-region',
    stage_main: 'id="stage"',
    right_rail: 'id="rail-right"',
  };
  for (const region of L.REGIONS) {
    assert.ok(homes[region], `no DOM expectation written for region "${region}"`);
    assert.ok(page.includes(homes[region]) || editSrc.includes(homes[region]),
      `region "${region}" has no page home`);
  }
  // H2's editor creates one shell per editable region.
  assert.match(editSrc, /data-hud-region/);
});

await check("H3: every card either has a DOM selector or an explained fixed reason", () => {
  for (const card of L.CARD_REGISTRY) {
    const selectors = CARD_DOM[card.id];
    const fixed = FIXED_IDS[card.id];
    assert.ok(selectors || fixed, `card "${card.id}" has neither a DOM selector nor a reason`);
    for (const selector of selectors || []) {
      const ids = [...String(selector).matchAll(/#([\w-]+)/g)].map((m) => m[1]);
      for (const id of ids) {
        assert.ok(page.includes(`id="${id}"`) || bootstrap.includes(`id = "${id}"`)
          || bootstrap.includes(`"${id}"`), `card "${card.id}" points at #${id}, not on the page`);
      }
    }
  }
});

await check("F8: every registry label that has a page heading matches that heading", () => {
  const headings = {
    lanes: "Focus presets",
    systems: "Systems",
    waiting: "Cards waiting",
    telemetry: "Last turn telemetry",
    tools: "Abilities used",
    brain_stats: "Second brain & vault",
    budget: "Free-tier budget",
    voice_stats: "Voice",
    reminders: "Reminders",
  };
  for (const [id, words] of Object.entries(headings)) {
    const card = L.CARD_REGISTRY.find((entry) => entry.id === id);
    assert.ok(card, `${id} is not a registry card`);
    assert.equal(card.label, words, `${id} label is stale`);
    assert.ok(page.includes(words.replace("&", "&amp;")) || page.includes(words),
      `${id}'s heading "${words}" is missing from the page`);
  }
});

/* ── 2. The pruned contract and the Quiet naming ────────────────────────── */

await check("Q5: the contract has no colour theme and no inert fixed-card spans", () => {
  assert.equal(contract.presets.length, 7);
  const ids = contract.presets.map((preset) => preset.id);
  assert.deepEqual(ids, ["cockpit", "studio", "ambient", "quiet", "telemetry",
    "second_brain", "minimal"]);
  for (const preset of contract.presets) {
    assert.equal("theme" in preset, false, `${preset.id} still carries theme`);
    for (const card of preset.cards) {
      if (!FIXED.has(card.id)) continue;
      assert.equal("col_span" in card, false, `${preset.id}/${card.id} keeps a span`);
      assert.equal("row_span" in card, false, `${preset.id}/${card.id} keeps a span`);
    }
  }
  for (const preset of L.PRESETS) {
    assert.equal("theme" in preset, false, `${preset.id} still carries theme`);
    assert.ok(L.SHELL_TEMPLATES.includes(preset.shell_template));
    assert.ok(L.DENSITIES.includes(preset.density));
    assert.ok(L.STAGE_TABS.includes(preset.default_stage_tab));
  }
});

/* ── 3. The layout library: bounded, closed-world, protected ────────────── */

const base = () => L.presetLayout("cockpit");

await check("a first edit of a shipped layout becomes the owner's copy (Ruling 27)", () => {
  const copy = P.ensureCustomCopy(base());
  assert.equal(copy.id.startsWith("custom-"), true, copy.id);
  assert.equal(copy.name, "Cockpit (Custom)");
  assert.equal(copy.user_presets.length, 1);
  assert.equal(copy.user_presets[0].id, copy.id);
  assert.ok(L.isUserLayout(copy));
  // Applying the copy keeps its arrangement; editing it again does not fork.
  const again = P.ensureCustomCopy(copy);
  assert.equal(again.id, copy.id);
  assert.equal(again.user_presets.length, 1);
});

await check("duplicate / rename / delete / reset behave, and never lose the library", () => {
  const one = P.ensureCustomCopy(base());
  const two = P.duplicateLayout(one);
  assert.equal(two.refused, "");
  assert.equal(two.doc.user_presets.length, 2);
  assert.notEqual(two.doc.id, one.id);

  const renamed = P.renameActiveLayout(two.doc, "  Evening   plan ");
  assert.equal(renamed.refused, "");
  assert.equal(renamed.doc.name, "Evening plan");
  assert.equal(renamed.doc.user_presets.find((entry) => entry.id === renamed.doc.id).name,
    "Evening plan");
  assert.match(P.renameActiveLayout(base(), "Hack").refused, /Duplicate/);

  const applied = P.applyUserLayout(renamed.doc, one.id);
  assert.equal(applied.id, one.id);
  assert.equal(applied.user_presets.length, 2);

  const deleted = P.deleteUserLayout(applied, applied.id);
  assert.equal(deleted.id, "cockpit");
  assert.equal(deleted.user_presets.length, 1);
  // Reset keeps the owner's saved layouts and puts the shipped arrangement back.
  const reset = L.presetLayout(deleted.base_preset);
  assert.equal(reset.user_presets.length, 0);
});

await check("the library is capped at 20 and refuses a 21st with plain words", () => {
  let doc = base();
  for (let n = 1; n <= 20; n += 1) {
    const added = P.duplicateLayout(doc);
    assert.equal(added.refused, "", `duplicate ${n} was refused: ${added.refused}`);
    doc = added.doc;
  }
  assert.equal(doc.user_presets.length, 20);
  const over = P.duplicateLayout(doc);
  assert.equal(over.doc.user_presets.length, 20);
  assert.match(over.refused, /up to 20/);
  // A hand-edited document with 25 layouts is clamped, never trusted.
  const many = Array.from({ length: 25 }, (_, n) => ({ ...doc.user_presets[0],
    id: `custom-cockpit-${n + 1}`, name: `Copy ${n + 1}` }));
  const clamped = L.normalizeLayout({ ...base(), user_presets: many });
  assert.equal(clamped.user_presets.length, 20);
});

await check("export is explanation-free JSON; import repairs, refuses, and stays closed-world", () => {
  const mine = P.ensureCustomCopy(base());
  const text = P.exportLayoutJson(mine);
  assert.match(text, /"kind": "jarvis\.hud\.layout"/);
  assert.doesNotMatch(text, /token|password|chat|memory_/i);
  const back = P.importLayoutText(text);
  assert.equal(back.ok, true, back.error);
  assert.equal(back.doc.user_presets.length, 1);
  assert.equal(back.doc.name, mine.name);

  // Hostile: unknown card names, hidden protected cards, prototype keys,
  // 21 layouts, wrong version.
  const hostile = JSON.parse(text);
  hostile.cards.push({ id: "jarvis_ghost", region: "left_rail", order: 0 });
  assert.equal(P.importLayoutText(JSON.stringify(hostile)).ok, false);
  const hiddenProtected = JSON.parse(text);
  hiddenProtected.cards.find((card) => card.id === "approvals").visible = false;
  const repaired = P.importLayoutText(JSON.stringify(hiddenProtected));
  assert.equal(repaired.ok, true, repaired.error);
  assert.equal(repaired.doc.cards.find((card) => card.id === "approvals").visible, true,
    "an imported layout hid the approvals card");
  const proto = text.replace("}", ", \"__proto__\": {\"polluted\": true}}");
  assert.equal(P.importLayoutText(proto).ok, false);
  assert.equal({}.polluted, undefined);
  const wrongVersion = { ...JSON.parse(text), version: 9 };
  assert.equal(P.importLayoutText(JSON.stringify(wrongVersion)).ok, false);
  assert.equal(P.importLayoutText("not json").ok, false);
  assert.equal(P.importLayoutText("{}").ok, false);
  assert.equal(P.importLayoutText("").ok, false);
  // Importing makes it active AND keeps it in My layouts.
  const adopted = P.adoptImportedLayout(back.doc);
  assert.equal(adopted.refused, "");
  assert.equal(adopted.doc.id, adopted.doc.user_presets[adopted.doc.user_presets.length - 1].id);
});

await check("H3-1: an import ADDS to My layouts and never replaces it", () => {
  // The owner already keeps one custom layout; the imported JSON carries an
  // empty library (another PC, or a hand-written file).
  const current = P.ensureCustomCopy(base());
  const keeper = current.user_presets[0].id;
  const importedDoc = L.presetLayout("quiet");
  const imported = P.importLayoutText(P.exportLayoutJson(importedDoc));
  assert.equal(imported.ok, true, imported.error);
  const adopted = P.adoptImportedLayout(imported.doc, current);
  assert.equal(adopted.refused, "");
  const ids = adopted.doc.user_presets.map((entry) => entry.id);
  assert.ok(ids.includes(keeper), `import dropped the owner's layout ${keeper}: ${JSON.stringify(ids)}`);
  assert.equal(ids.length, 2, `import should add one layout, got ${JSON.stringify(ids)}`);
  assert.equal(adopted.doc.base_preset, "quiet", "the imported layout is not active");
  // The imported entry is in the library under its own name, not merged away.
  assert.ok(adopted.doc.user_presets.some((entry) => entry.name === "Quiet"));

  // Importing the owner's OWN full export must not duplicate the active entry
  // (which would burn a slot toward the 20 cap - review H3-1).
  const ownExport = P.importLayoutText(P.exportLayoutJson(current));
  assert.equal(ownExport.ok, true, ownExport.error);
  const again = P.adoptImportedLayout(ownExport.doc, current);
  assert.equal(again.refused, "");
  assert.equal(again.doc.user_presets.length, 1,
    `importing the owner's own export duplicated the layout: ${JSON.stringify(again.doc.user_presets.map((e) => e.id))}`);
  assert.equal(again.doc.id, keeper);
  assert.equal(again.doc.user_presets[0].id, keeper);
});

await check("H3-1/H3-2: the 20 cap refuses an import in words, never trims silently", () => {
  let full = base();
  for (let n = 1; n <= 20; n += 1) full = P.duplicateLayout(full).doc;
  assert.equal(full.user_presets.length, 20);
  const imported = P.importLayoutText(P.exportLayoutJson(L.presetLayout("quiet")));
  assert.equal(imported.ok, true, imported.error);
  const adopted = P.adoptImportedLayout(imported.doc, full);
  assert.equal(adopted.doc.user_presets.length, 20, "a refused import must not change the library");
  assert.match(adopted.refused, /up to 20/);
  assert.equal(adopted.doc.user_presets.length, userLayoutsOf(full).length);

  // A JSON that itself carries 21 layouts is refused at validation time, before
  // the normalizer could clamp it to 20 (review H3-2).
  const oversize = JSON.parse(P.exportLayoutJson(full));
  oversize.user_presets = Array.from({ length: 21 }, (_, n) => ({
    ...oversize.user_presets[0], id: `custom-cockpit-${n + 1}`, name: `Copy ${n + 1}`,
  }));
  const refused = P.importLayoutText(JSON.stringify(oversize));
  assert.equal(refused.ok, false);
  assert.match(refused.error, /more than 20/);
});

function userLayoutsOf(doc) {
  return L.userLayouts(doc);
}

await check("H3-4: the import size cap counts BYTES, the same unit the store uses", () => {
  // 40,000 two-byte characters: fewer than 64K UTF-16 units, more than 64K
  // bytes. The store's cap is bytes, so validation must refuse it here too.
  const multibyte = `{"pad":"${"é".repeat(40000)}"}`;
  assert.ok(multibyte.length < 64 * 1024);
  assert.ok(new TextEncoder().encode(multibyte).length > 64 * 1024);
  const refused = P.importLayoutText(multibyte);
  assert.equal(refused.ok, false);
  assert.match(refused.error, /too long/);
});

await check("H3-5: renaming a saved layout does not make it active", () => {
  const one = P.ensureCustomCopy(base());
  const two = P.duplicateLayout(one);
  assert.equal(two.doc.user_presets.length, 2);
  const other = two.doc.user_presets.find((entry) => entry.id !== two.doc.id);
  const beforeActive = two.doc.id;
  const renamed = P.renameUserLayout(two.doc, other.id, "Renamed elsewhere");
  assert.equal(renamed.refused, "");
  assert.equal(renamed.doc.id, beforeActive, "renaming a non-active layout switched to it");
  assert.equal(renamed.doc.user_presets.find((entry) => entry.id === other.id).name,
    "Renamed elsewhere");
  assert.equal(renamed.doc.name, two.doc.name, "the active layout's own name changed");
});

await check("H3-3: Rust's known-base-preset list matches the JS PRESETS (plus the focus alias)", () => {
  const rust = read("src-tauri/src/hud_layout.rs");
  const block = /pub const BUILT_IN_PRESETS: &\[&str\] = &\[([\s\S]*?)\];/.exec(rust);
  assert.ok(block, "hud_layout.rs no longer declares BUILT_IN_PRESETS");
  const rustIds = [...block[1].matchAll(/"([a-z_]+)"/g)].map((match) => match[1]);
  assert.deepEqual(rustIds, L.PRESETS.map((preset) => preset.id));
  assert.match(rust, /pub const PRESET_ALIASES: &\[&str\] = &\["focus"\]/);
});

await check("the document shape never carries a colour theme or a stray library id", () => {
  const doc = P.ensureCustomCopy(base());
  assert.equal("theme" in doc, false);
  const out = L.normalizeLayout({ ...doc, user_presets: doc.user_presets.concat([
    { id: "custom-cockpit-1", name: "duplicate id", base_preset: "cockpit", cards: doc.cards },
    { id: "Focus!", name: "bad id", base_preset: "cockpit", cards: doc.cards },
    { id: "custom-bad-9", name: "", base_preset: "cockpit", cards: doc.cards },
    { id: "custom-bad-10", name: "ok", base_preset: "nope", cards: doc.cards },
  ]) });
  assert.equal(out.user_presets.length, 1, JSON.stringify(out.user_presets.map((e) => e.id)));
});

/* ── 4. Retired things stay retired (source pins) ───────────────────────── */

await check("Q5: LOOKS, lookForPreset, data-hud-layout and jarvis:hud-look are gone", () => {
  for (const needle of ["var LOOKS", "jarvis:hud-look", "lookForPreset", "LOOK_BY_PRESET"]) {
    assert.equal(bootstrap.includes(needle), false, `bootstrap still has ${needle}`);
    assert.equal(page.includes(needle), false, `page still has ${needle}`);
  }
  assert.equal(page.includes("data-hud-layout"), false, "page still has data-hud-layout");
  assert.equal(storeSrc.includes("LOOK_BY_PRESET"), false, "store still has the look map");
  assert.equal(storeSrc.includes("lookForPreset"), false, "store still exports lookForPreset");
  assert.equal(modelSrc.includes("THEMES"), false, "model still exports THEMES");
  assert.equal(editSrc.includes("presetsPeek"), false, "editor still peeks at Focus presets");
  // The stale H1/H2 comments are rewritten, not left saying "until H2" - and
  // the broader pre-H3 descriptions are gone too (post-merge audit H3-PM-5).
  for (const source of [modelSrc, storeSrc, page, settingsModule, editSrc, presetsSrc]) {
    assert.equal(/until H2/.test(source), false, "a stale 'until H2' comment survived");
    assert.equal(source.includes("H2 draws the region grid"), false,
      "a stale 'H2 draws the region grid' comment survived");
    assert.equal(source.includes("three in-header pills"), false,
      "a stale 'three in-header pills' comment survived");
    assert.equal(source.includes("current three-way `data-hud-layout` look"), false,
      "a stale three-way data-hud-layout comment survived");
  }
});

await check("H3-PM-2: Ambient's left rail is a drawer, not an unreachable hidden rail", () => {
  // The old center-core block hid the left rail outright, so its cards (and
  // the protected Jarvis-bar card H2 renders there in edit mode) were
  // unreachable. It now uses the same drawer + [Navigation] toggle as
  // two-column-right and single-stage-bento.
  assert.equal(page.includes('html[data-hud-shell="center-core"] .rail.left{display:none;}'),
    false, "Ambient still hides the left rail outright");
  assert.match(page,
    /html\[data-hud-shell="center-core"\] \.rail\.left\{[^}]*transform:translateX\(-100%\)/,
    "Ambient has no off-canvas left drawer");
  assert.match(page,
    /html\[data-hud-shell="center-core"\] \.rail\.left\.open\{transform:none;\}/,
    "Ambient has no open left drawer");
  assert.match(page,
    /html\[data-hud-shell="center-core"\] \.left-toggle\{display:flex;\}/,
    "Ambient offers no [Navigation] toggle");
  assert.match(page, /two-column-right, single-stage-bento and center-core hide the left rail/,
    "the left-drawer comment does not list Ambient");
  // Gemini's PM-2 ruling: while Edit HUD is active, every hidden rail is
  // revealed (slide-over drawers home; split-stage's tab rail forced back), so
  // no protected control can sit behind a closed rail.
  assert.match(page, /body\[data-hud-edit="on"\] \.rail\.edit-reveal\{transform:none !important;\}/,
    "edit mode does not bring slide-over rails home");
  assert.match(page, /body\[data-hud-edit="on"\] \.rail\.edit-reveal\.right\{display:flex !important;/,
    "edit mode does not force the tab-revealed rail back on");
  assert.match(page, /body\[data-hud-edit="on"\] #hud-stop\{[^}]*z-index:60;?/,
    "edit mode does not keep the fixed Stop control above the auto-revealed rails");
  assert.match(editSrc, /revealRailsForEditing/, "the editor does not reveal hidden rails");
  assert.match(editSrc, /edit-reveal/, "the editor does not mark the revealed rails");
  // P0.5 D-UI-3/4 (2026-10-23): one edit banner, a non-overlapping right rail
  // in edit mode, and a full-width Ambient stage with a visible Controls pill.
  assert.match(editSrc, /hud-edit-banner/, "the edit bar has no .hud-edit-banner");
  assert.match(editSrc,
    /Editing the HUD — drag a card or use its buttons\. Press Esc when done\./,
    "the edit banner is not the single plain sentence");
  assert.match(page,
    /#rail-right \.hud-card\{[^}]*flex-shrink:0/,
    "edit-mode right-rail cards can shrink and overlap");
  assert.match(page, /grid-template-columns:0 minmax\(0,1fr\)/,
    "Ambient still reserves a column for the fixed left rail");
  assert.match(page, /html\[data-hud-shell="center-core"\] #stage\{[^}]*grid-column:1 \/ -1/,
    "Ambient's stage does not span the full width");
  assert.match(page, /aria-label="Open the Controls drawer"/,
    "the Ambient Controls pill has no accessible label");
  assert.match(page, />&#9776; Controls</, "the Controls pill has no visible label");
  // The HUD's fixed Stop everything control is real now (owner-approved
  // 2026-10-22): pinned in the page, the editor reason and both docs. The old
  // tracked-gap wording must be gone, and the page must actually carry the
  // button - a document-level `emergency_stop` alone is not a control.
  const ARCH = readFileSync(join(ROOT, "docs", "ARCHITECTURE.md"), "utf8");
  const DECISIONS = readFileSync(join(ROOT, "docs", "DECISIONS.md"), "utf8");
  assert.match(editSrc, /Stop everything is a fixed control in the header/,
    "the editor's emergency-stop reason does not describe the fixed header control");
  assert.match(editSrc, /Alt\+Shift\+X/,
    "the editor's emergency-stop reason does not name the real stop hotkey");
  assert.match(ARCH, /The fixed Stop everything control \(owner-approved 2026-10-22\)/,
    "ARCHITECTURE does not describe the fixed Stop everything control");
  assert.match(ARCH, /#hud-stop/, "ARCHITECTURE does not name the HUD stop control");
  assert.match(ARCH, /Alt\+Shift\+X/, "ARCHITECTURE does not name the real stop hotkey");
  assert.match(DECISIONS, /The fixed \*\*Stop everything\*\* control \(owner-approved/,
    "DECISIONS does not describe the fixed Stop everything control");
  assert.match(DECISIONS, /#hud-stop/, "DECISIONS does not name the HUD stop control");
  assert.match(DECISIONS, /Alt\+Shift\+X/, "DECISIONS does not name the real stop hotkey");
  assert.equal(/\*\*Tracked gap:\*\* the HUD page|no DOM and no clickable stop-all/.test(ARCH),
    false, "ARCHITECTURE still carries the old tracked-gap wording");
  assert.equal(/\*\*Tracked gap:\*\* the HUD has no clickable stop-all/.test(DECISIONS),
    false, "DECISIONS still carries the old tracked-gap wording");
  assert.match(page, /<button class="hud-stop" id="hud-stop"/,
    "the HUD page has no real #hud-stop button");
  assert.match(page, /invoke\("stop_everything"\)/,
    "the HUD page does not invoke the existing stop_everything command");
  const capability = JSON.parse(read("src-tauri/capabilities/hud.json"));
  assert.equal(capability.permissions.filter((name) => name === "hud-stop").length, 1,
    "the HUD capability does not grant exactly one hud-stop");
  assert.equal(capability.permissions.includes("task-control"), false,
    "the broad task-control set was granted to the HUD instead of hud-stop");
  const surfaces = read("src-tauri/permissions/surfaces.toml");
  assert.match(surfaces, /identifier = "hud-stop"/, "surfaces.toml has no hud-stop set");
  assert.match(surfaces, /permissions = \["allow-stop-everything"\]/,
    "hud-stop does not grant exactly allow-stop-everything");
});

await check("H3: the bootstrap renders shell/density/tab and writes the first-paint mirror", () => {
  assert.match(bootstrap, /jarvis\.hud\.preview/);
  assert.match(bootstrap, /data-hud-shell/);
  assert.match(bootstrap, /data-hud-density/);
  assert.match(bootstrap, /jarvis:hud-shell/);
  assert.match(bootstrap, /jarvis:hud-layout/);
  assert.match(page, /jarvis\.hud\.preview/);
  assert.match(page, /localStorage\.getItem\("jarvis\.hud\.preview"\)/);
});

/* ── 5. Copy/paste only: no file/blob/network, no new capability ────────── */

await check("copy/paste JSON is the only move path (no file, blob, object URL)", () => {
  const codeOnly = (source) => source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/[^\n]*/g, "");
  const presetsCode = codeOnly(presetsSrc);
  for (const forbidden of ["type=\"file\"", "showOpenFilePicker", "createObjectURL",
    "download=", "<input"]) {
    assert.equal(presetsCode.includes(forbidden), false,
      `hud-presets.js contains ${forbidden}`);
    if (forbidden === "<input") continue; // the page's own chat box is an <input>
    assert.equal(codeOnly(page).includes(forbidden), false, `the page contains ${forbidden}`);
  }
  assert.match(presetsSrc, /navigator\.clipboard/);
  assert.match(presetsSrc, /Press Ctrl\+C/);
  // The H3 move path adds no network of its own. The ONLY requests in this
  // module are the Presets menu's four PC calls (2026-10-27): two reads and two
  // writes on the two routes the page already uses, each on the shell bridge or
  // the browser road - never a bare fetch, never a third URL.
  const fetches = [...presetsSrc.matchAll(/(\w+)\.fetch\(/g)].map((m) => m[1]);
  assert.deepEqual([...new Set(fetches)], ["win"],
    `a request in hud-presets.js is not on the page's own window: ${JSON.stringify(fetches)}`);
  assert.equal(/(?<![.\w])fetch\s*\(/.test(codeOnly(presetsSrc)), false,
    "hud-presets.js calls a bare fetch outside the two windows' roads");
  const routes = new Set([...presetsSrc.matchAll(/apiUrlFor\(win, "([^"]+)"\)/g)].map((m) => m[1]));
  assert.deepEqual([...routes].sort(), ["/api/manner", "/api/presets", "/api/work/apply"],
    `the Presets menu reaches an unexpected route: ${JSON.stringify([...routes])}`);
});

await check("H3 added no WRITE capability of its own - and the HUD's writes stay named", () => {
  const capability = JSON.parse(read("src-tauri/capabilities/hud.json"));
  assert.ok(capability.permissions.includes("hud-layout-write"));
  assert.ok(capability.permissions.includes("hud-layout-read"));
  // 2026-10-27: the Presets menu's personality switch is a write, so the HUD
  // window now holds TWO write-capable sets and exactly these two: the layout
  // store (H2/H3) and the personalities set (wording only, no card, held on a
  // stale link). Nothing else may be added without this list changing.
  const writes = capability.permissions.filter((name) => /write/.test(name));
  assert.deepEqual(writes, ["hud-layout-write"],
    `the HUD window holds unexpected write grants: ${JSON.stringify(writes)}`);
  assert.equal(capability.permissions.filter((name) => name === "hud-personalities").length, 1,
    "the HUD's personality commands are granted by no set, or by more than one");
  // Same commands as H2: H3 added none.
  const lib = read("src-tauri/src/lib.rs");
  assert.match(lib, /hud_layout::get_hud_layout/);
  assert.match(lib, /hud_layout::set_hud_layout/);
  assert.equal((lib.match(/hud_layout::/g) || []).length >= 2, true);
  // Settings lists My layouts and one-click Reset, through the same module.
  assert.match(settings, /id="hud-layout-list"/);
  assert.match(settings, /HUD layouts/);
  assert.match(settings, /id="hud-reset-layout"/);
  assert.match(settingsModule, /userLayouts/);
  assert.match(settingsModule, /resetToCockpit/);
});

/* ── 6. The Presets menu's PC lists (2026-10-27) ─────────────────────────── */

await check("modelPresetRows reads the PC's chosen_preset - and nothing else marks a row", () => {
  const payload = {
    presets: [
      { id: "general", title: "General", focus: "everyday chat" },
      { id: "coding", title: "Coding", focus: "big code" },
    ],
    chosen_preset: "coding",
  };
  assert.deepEqual(P.modelPresetRows(payload), [
    { id: "general", title: "General", focus: "everyday chat", chosen: false },
    { id: "coding", title: "Coding", focus: "big code", chosen: true },
  ]);
  assert.equal(P.modelPresetRows({ available: false, why: "old backend" }).length, 0,
    "a backend without the route invents presets");
  assert.equal(P.modelPresetRows({ presets: [{ title: "no id" }] }).length, 0,
    "a preset with no id is drawn as an unclickable row");
  // A row is never chosen just because it exists - only chosen_preset says so.
  assert.equal(P.modelPresetRows({ presets: [{ id: "fast", title: "Fast" }] })[0].chosen, false);
});

await check("personalityRows reads the nine and the owner's own, and marks the PC's current", () => {
  const payload = {
    personality: "classic_butler",
    personalities: [
      { id: "warm_peer", title: "Warm Collaborator", description: "warm" },
      { id: "classic_butler", title: "Classic British Butler", description: "formal" },
    ],
    user_personalities: [
      { id: "mine-1", name: "Calm Helper", line: "calm" },
      { id: "bad-row" },
    ],
  };
  const { rows, current } = P.personalityRows(payload);
  assert.equal(current, "classic_butler");
  assert.deepEqual(rows.map((row) => [row.id, row.title, row.custom, row.current]), [
    ["warm_peer", "Warm Collaborator", false, false],
    ["classic_butler", "Classic British Butler", false, true],
    ["mine-1", "Calm Helper", true, false],
  ]);
  // The old spelling is read too, so an older backend still lists them.
  const older = P.personalityRows({ personalities: [], custom_personalities: [
    { id: "mine-2", name: "Old Name" }] });
  assert.equal(older.rows.length, 1, "a backend using custom_personalities lost the owner's own");
  assert.equal(older.rows[0].custom, true);
});

await check("the two click bodies carry ONE field each", () => {
  assert.deepEqual(P.personalitySwitchBody("classic_butler"), { personality: "classic_butler" });
  assert.deepEqual(P.modelApplyBody("coding"), { preset: "coding" });
  assert.deepEqual(P.personalitySwitchBody(""), { personality: "" });
});

await check("the shell road calls the four commands, and the browser road sends the right request", async () => {
  const calls = [];
  const win = { __TAURI__: { core: { invoke: (...args) => {
    calls.push(args); return Promise.resolve({ ok: true });
  } } } };
  await P.readFocusPresetsOnPc(win);
  await P.readPersonalitiesOnPc(win);
  await P.applyFocusPresetOnPc(win, "coding");
  await P.switchPersonalityOnPc(win, "classic_butler");
  assert.deepEqual(calls, [
    ["get_focus_presets"],
    ["hud_personalities"],
    ["apply_focus_preset", { preset: "coding" }],
    ["hud_switch_personality", { personality: "classic_butler" }],
  ]);
  const seen = [];
  const browser = {
    JARVIS: {
      headers: (extra) => ({ "X-Jarvis-Token": "a-token", "X-Jarvis-Client": "hud", ...extra }),
      url: (path) => `http://127.0.0.1:4719${path}`,
    },
    fetch: (url, init) => {
      seen.push({ url, init });
      return Promise.resolve({ ok: true, status: 200,
        json: () => Promise.resolve({ ok: true, said: "hello" }) });
    },
  };
  await P.readFocusPresetsOnPc(browser);
  await P.readPersonalitiesOnPc(browser);
  await P.applyFocusPresetOnPc(browser, "coding");
  await P.switchPersonalityOnPc(browser, "classic_butler");
  assert.deepEqual(seen.map((s) => [s.url, s.init.method || "GET", s.init.headers["X-Jarvis-Client"]]), [
    ["http://127.0.0.1:4719/api/presets", "GET", "hud"],
    ["http://127.0.0.1:4719/api/manner", "GET", "hud"],
    ["http://127.0.0.1:4719/api/work/apply", "POST", "hud"],
    ["http://127.0.0.1:4719/api/manner", "POST", "hud"],
  ]);
  assert.deepEqual(JSON.parse(seen[2].init.body), { preset: "coding" });
  assert.deepEqual(JSON.parse(seen[3].init.body), { personality: "classic_butler" });
  // A refusal on the browser road is thrown in the PC's own words.
  await assert.rejects(
    P.switchPersonalityOnPc({ fetch: () => Promise.resolve({ ok: false, status: 409,
      json: () => Promise.resolve({ error: "I do not know that personality." }) }) }, "nope"),
    /I do not know that personality\./);
});

if (fails) {
  console.error(`\n${fails} test(s) failed`);
  process.exit(1);
} else {
  console.log(`\nall ${passed} H3 model/renderer/library checks passed`);
}
