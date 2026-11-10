/**
 * Edit HUD, the owner's UI review of 2026-11-09 (Q6-Q9):
 * "the UI is clunky and overwhelming a lot, including in the edit hud menu".
 *
 *   node tests/hud-edit-tabs.mjs
 *
 * WHAT THIS PINS, without a browser (the real page is driven by the Playwright
 * cases in tests/hud-edit-fieldtest.mjs, tests/hud-edit-select.mjs and
 * tests/hud.mjs, which CI runs):
 *
 *   - the ribbon is DOCKED into the window grid (`grid-row:1; grid-column:1/-1`
 *     on `#shell`'s first child), not floating over the canvas it edits, and
 *     its hierarchy is the review's: `Editing Layout: <name>`, the two drawers,
 *     the quiet Undo / Reset to Default / Cancel, and ONE loud `✓ Done`;
 *   - the four whole-edit controls keep the ids and handlers they always had;
 *   - the Panels and Advanced tabs are RETIRED (Q7): no pane, no builder, no
 *     button - and their state lives in the Cards drawer as plain chips
 *     (`Shown ✓` / `Hidden` / `🔒 Required for Safety`);
 *   - every per-card toolbar is hidden in NORMAL use, and in Edit HUD only the
 *     card that was CLICKED draws its inspector, in plain words: `Move:` the
 *     four column/place buttons, `Size:` Compact / Normal / Wide / Tall (the
 *     stored keys are still S/M/L/T), `Visibility:` Hide this card - or the
 *     locked badge on a safety surface;
 *   - every DOM hook the old toolbar had is still built (`data-hud-edit-command`,
 *     `data-hud-edit-size`, `data-hud-edit-region`, `data-hud-edit-card`), so
 *     `hud.mjs` and the field test keep driving the same buttons;
 *   - the three `hud-edit.js` copies and the three HUD page copies stay
 *     byte-identical.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { SIZES } from "../src/hud-edit.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const ROOT = join(HERE, "..", "..");
const read = (file) => readFileSync(file, "utf8");
const readBytes = (file) => readFileSync(file);

const JS = read(join(SRC, "hud-edit.js"));
const HUD = read(join(SRC, "jarvis_hud.html"));

let passed = 0;
function check(name, fn) {
  fn();
  passed += 1;
  console.log(`ok   ${name}`);
}

check("the ribbon is docked in the window grid, not floating over the canvas", () => {
  // Q8: `grid-row: 1; grid-column: 1 / -1` on the window's own grid, so it
  // pushes the three columns down and covers 0px of the layout.
  assert.match(HUD, /\.hud-edit-bar\{\s*\n\s*grid-row:1; grid-column:1 \/ -1;/,
    "the ribbon is not the window grid's first, full-width row");
  assert.doesNotMatch(HUD, /\.hud-edit-bar\{[^}]*position:fixed/,
    "the ribbon is pinned over the page again");
  assert.match(JS, /const shell = byId\("shell"\);/,
    "the bar is not built into #shell");
  assert.match(JS, /shell\.insertBefore\(barEl, shell\.firstChild\);/,
    "the bar is not the window grid's first child");
  // The grid has a row for it and the columns sit in the row below.
  assert.match(HUD, /html body\[data-hud-edit="on"\] #shell\{[\s\S]*?grid-template-rows:auto minmax\(0, 1fr\);/,
    "the edit-mode grid was not given a row for the ribbon");
  for (const rule of [
    /html body\[data-hud-edit="on"\] \.rail\.left\{grid-column:1; grid-row:2;\}/,
    /html body\[data-hud-edit="on"\] \.rail\.right\{grid-column:3; grid-row:2;\}/,
    /html body\[data-hud-edit="on"\] #stage\{grid-column:2; grid-row:2; min-width:0;\}/,
  ]) {
    assert.match(HUD, rule, `a column is not in the row below the ribbon: ${rule}`);
  }
  // Studio's stage is a grid of its own; the ribbon left it, so its rows moved
  // up and no two children may share one.
  assert.doesNotMatch(HUD, /#stage > \.hud-edit-banner/,
    "Studio's stage still reserves a row for the banner that is no longer its child");
  assert.match(HUD, /html\[data-hud-shell="split-stage"\] body\[data-hud-edit="on"\] #stage > #hud-home-cards\{\s*\n\s*grid-row:6;/,
    "the home strip did not take the row the ribbon freed");
});

check("the ribbon's hierarchy is the review's, and the four ids are unchanged", () => {
  assert.match(JS, /heading\.textContent = "Editing Layout: "/,
    "the ribbon does not say what it is editing");
  assert.ok(JS.includes('barButton("hud-edit-add-cards", "cards", "+ Add / Show Cards")'),
    "the Add / Show Cards drawer button is gone");
  assert.ok(JS.includes('barButton("hud-edit-switch-preset", "presets", "Switch Layout Preset \\u25be")'),
    "the Switch Layout Preset button is gone");
  for (const id of ["hud-edit-undo", "hud-edit-reset", "hud-edit-discard", "hud-edit-done"]) {
    assert.ok(JS.includes("`hud-edit-${what}`") && JS.includes("button.id = `hud-edit-${what}`"),
      "a whole-edit control lost its id");
  }
  // Same four handlers, new words.
  for (const [what, text] of [["undo", "Undo"], ["reset", "Reset to Default"],
    ["discard", "Cancel"], ["done", "\\u2713 Done"]]) {
    assert.ok(JS.includes(`["${what}", "${text}",`), `the ${what} control's words changed: ${text}`);
  }
  assert.match(JS, /data-hud-edit-global/, "the whole-edit controls lost their one handler");
  // The layout's name and the hidden count are live, not hard-coded.
  assert.match(JS, /name\.textContent = currentLayoutName\(\);/,
    "the ribbon's layout name is not read from the document");
  assert.match(JS, /`\+ Add \/ Show Cards \(\$\{hidden\} hidden\)`/,
    "the Add / Show Cards button does not say how many cards are hidden");
  // The safety strip stays above everything (Q14): the ribbon steps down by the
  // measured overlap instead of painting under it.
  assert.match(JS, /doc\.body\.style\.setProperty\("--hud-edit-band", `\$\{band\}px`\)/,
    "the ribbon does not reserve the safety strip's band");
  assert.match(HUD, /margin-top:var\(--hud-edit-band, 0px\)/,
    "the stylesheet ignores the measured band");
});

check("Panels and Advanced are retired, and their state lives in the Cards drawer", () => {
  assert.doesNotMatch(JS, /function renderPanelsPane\(/, "the Panels pane is still built");
  assert.doesNotMatch(JS, /function renderAdvancedPane\(/, "the Advanced pane is still built");
  assert.doesNotMatch(JS, /hud-edit-tab-panels|hud-edit-tab-advanced/,
    "a retired tab button is still built");
  assert.doesNotMatch(JS, /data-hud-edit-advanced/, "the retired pane's handler survives");
  assert.match(JS, /const EDIT_TABS = Object\.freeze\(\[\s*\n\s*\["cards", "Cards"\], \["presets", "Presets"\],/,
    "the ribbon no longer offers exactly the two surfaces the review keeps");
  // A stale id (an old session attribute, a script) is answered with Cards.
  assert.match(JS, /const RETIRED_TABS = Object\.freeze\(\[\["panels", "cards"\], \["advanced", "cards"\]\]\);/,
    "the retired ids are not aliased to Cards");
  assert.match(JS, /const retired = RETIRED_TABS\.find\(\(\[id\]\) => id === name\);/,
    "setEditTab does not resolve a retired id");
  // The chips: Shown / Hidden / Required for Safety, and the switch is the
  // SAME setVisible action the card's own control sends.
  assert.match(JS, /paneButton\(card\.visible \? "Shown \\u2713" : "Hidden"/,
    "the Cards drawer has no Shown/Hidden chip");
  assert.match(JS, /"\\uD83D\\uDD12 Required for Safety"/,
    "the Cards drawer does not name a card that is required for safety");
  assert.match(JS, /"data-hud-edit-visible": card\.id/,
    "the Shown/Hidden chip is not a switch");
  assert.match(JS, /const stateChip = target\.closest\("\[data-hud-edit-visible\]"\);[\s\S]*?doAction\(\{ type: "setVisible"/,
    "the chip does not go through the one visibility action");
  // The drawers are opened by the ribbon's own buttons, one at a time.
  assert.match(JS, /button\.setAttribute\("aria-expanded", String\(drawerOpen === name\)\);/,
    "a drawer button does not say whether its drawer is open");
  assert.match(HUD, /\.hud-edit-pane\[hidden\]\{display:none !important;\}/,
    "a closed drawer can still be painted");
  assert.doesNotMatch(HUD, /\.hud-edit-tabs\{/, "the retired tab strip's rule survives");
});

check("NORMAL use draws zero per-card toolbars", () => {
  assert.match(HUD, /body:not\(\[data-hud-edit="on"\]\) \.hud-card \.hud-card-tools\{display:none;\}/,
    "jarvis_hud.html does not hide the card toolbars outside Edit HUD");
  assert.match(HUD, /\.hud-card-head\{display:none;\}/,
    "the card heads are still drawn outside Edit HUD");
  assert.match(HUD, /body\[data-hud-edit="on"\] \.hud-card-head\{\s*\n\s*display:flex;/,
    "the card heads are not drawn while editing");
});

check("in Edit HUD only the CLICKED card draws its inspector (Q6 click-to-select)", () => {
  // Every editable card keeps the dashed outline and the hover pill...
  assert.match(HUD, /body\[data-hud-edit="on"\] \.hud-card\{[\s\S]*?border:1px dashed/,
    "editable cards have no dashed outline in Edit HUD");
  assert.match(JS, /pill\.textContent = "Click to edit";/,
    "the Click to edit pill is gone");
  // ...but the 7-control row is drawn on the selected card alone.
  assert.match(HUD, /body\[data-hud-edit="on"\] \.hud-card \.hud-card-tools\{display:none;\}/,
    "every card still draws its toolbar in Edit HUD");
  assert.match(HUD, /body\[data-hud-edit="on"\] \.hud-card\[data-hud-edit-selected="true"\] \.hud-card-tools\{display:flex;\}/,
    "the selected card does not draw its inspector");
  // The selection is the page's own state, written on every render.
  assert.match(JS, /shell\.setAttribute\("data-hud-edit-selected",\s*\n\s*selectedCard && id === selectedCard \? "true" : "false"\);/,
    "the selected card is not marked for the stylesheet");
  // A click on a card selects it; the editor's own controls keep their click.
  assert.match(JS, /function onMainScreenClick\(/,
    "the capture-phase selection handler is gone");
});

check("the card inspector is plain words: Move, Size, Visibility", () => {
  for (const word of ["Move:", "Size:", "Visibility:"]) {
    assert.ok(JS.includes(`word("${word}")`), `the ${word} group label is missing`);
  }
  // Move: the four buttons, each one real.
  for (const command of ["left", "up", "down", "right"]) {
    assert.ok(JS.includes(`button("${command}", `), `the ${command} move button is missing`);
  }
  assert.ok(JS.includes('"\\u25c0 Left Column"'), "the left column button is not in plain words");
  assert.ok(JS.includes('"Right Column \\u25b6"'), "the right column button is not in plain words");
  assert.ok(JS.includes('"\\u25b2 Move Up"') && JS.includes('"\\u25bc Move Down"'),
    "the up/down buttons are not in plain words");
  // Size: plain words over the SAME four keys a saved layout stores.
  assert.deepEqual(SIZES.map((size) => size.label), ["Compact", "Normal", "Wide", "Tall"]);
  assert.deepEqual(SIZES.map((size) => size.key), ["S", "M", "L", "T"]);
  assert.match(JS, /const b = button\("size", size\.label, /,
    "the size pills do not use the plain-word label");
  assert.match(JS, /b\.setAttribute\("data-hud-edit-size", size\.key\);/,
    "the size pills lost the stored key");
  assert.match(JS, /pill\.setAttribute\("aria-pressed",\s*\n\s*String\(pill\.getAttribute\("data-hud-edit-size"\) === sizeNow\)\);/,
    "the size pills do not show which size the card is on");
  // Visibility: one control, both directions, and a locked badge for safety.
  assert.ok(JS.includes('"Hide this card"'), "the Hide control is not in plain words");
  assert.match(JS, /hideBtn\.textContent = locked\s*\n\s*\? "\\uD83D\\uDD12 Always visible for safety"/,
    "a protected card's control is not the locked badge");
  assert.match(JS, /hideBtn\.textContent = locked[\s\S]*?: \(hidden \? "Show this card" : "Hide this card"\);/,
    "the Hide control is not a real toggle any more");
  // The hover pill Q6 asks for, and the dashed outline the page already draws.
  assert.match(JS, /pill\.textContent = "Click to edit";/,
    "an editable card does not say what a click on it does");
  assert.match(HUD, /\.hud-card-edit-pill\{/, "the hover pill has no styling");
  assert.match(HUD, /\.hud-card\[data-hud-edit-selected="true"\]\{/,
    "the selected card has no outline");
});

check("every hook the old toolbar had is still built (the suites drive them)", () => {
  // hud.mjs counts four size buttons per card, requires a region selector per
  // card, and the field test clicks the hide/collapse commands by card id.
  assert.match(JS, /for \(const size of SIZES\) \{/, "the size loop is gone");
  assert.match(JS, /select\.setAttribute\("data-hud-edit-region", id\);/, "the region select is gone");
  assert.match(JS, /wrap\.classList\.add\("hud-tool-select hud-tool-under"\);|regionWrap\.className = "hud-tool-select hud-tool-under";/,
    "the region select is not marked as the undrawn legacy control");
  assert.match(HUD, /\.hud-tool-under\{display:none;\}/, "the legacy select is not hidden by CSS");
  for (const command of ["hide", "collapse"]) {
    assert.ok(JS.includes(`button("${command}", `), `the ${command} command is gone`);
  }
  assert.match(JS, /b\.setAttribute\("data-hud-edit-command", command\);/,
    "the one command attribute is gone");
  assert.match(JS, /b\.setAttribute\("data-hud-edit-card", id\);/,
    "a control no longer names its card");
  // The 2026-10-31 shape this replaced: a card's toolbar was MOVED into the
  // bar. It is no longer moved anywhere - one element, one place, one owner.
  assert.doesNotMatch(JS, /movedTools/, "the toolbar is still moved into the ribbon");
  assert.doesNotMatch(JS, /hud-edit-card-controls/, "the retired selected-card editor survives");
});

check("presets: the chosen row is `Current`, and Apply is the existing resetToPreset", () => {
  assert.match(JS, /"hud-edit-preset-name" \+ \(chosen \? " is-chosen" : ""\)/,
    "the chosen preset is not outlined with is-chosen");
  assert.match(JS, /data-hud-edit-preset/);
  assert.match(JS, /doAction\(\{ type: "resetToPreset", id: preset\.getAttribute\("data-hud-edit-preset"\) \}\)/,
    "Apply is not the existing reset-to-preset action");
  assert.match(JS, /Applying is one Undo away/);
  // Q9 (2026-11-09): one state, one word. The shared highlighted rectangle says
  // which preset is current, and the row says "Current" - not "chosen" beside
  // "Applied".
  assert.match(JS, /paneWords\("Current", "hud-edit-pane-tag"\)/,
    "the chosen preset is not named Current");
  assert.doesNotMatch(JS, /"Applied"/,
    "the Presets drawer still says `Applied` beside the chosen row");
  assert.doesNotMatch(JS, /paneWords\("chosen"/,
    "the Presets drawer still says `chosen` beside the chosen row");
});

check("behaviour is untouched: no network call here, the normalizer is not edited, Esc still exits", () => {
  assert.ok(!/new XMLHttpRequest|fetch\(/.test(JS),
    "the edit code calls the network - there is no new route in this change");
  assert.ok(!/normalizeLayout\s*=\s*function|function normalizeLayout\(/.test(JS),
    "the layout normalizer was redefined here");
  assert.match(JS, /key === "Escape"|"Escape"/,
    "Esc no longer exits edit mode");
  // The whole-edit semantics the field test drives, unchanged: Done closes,
  // Cancel restores the entry snapshot, Reset is the preset action.
  assert.match(JS, /what === "done"\) \{ setEditing\(false\); announce\("HUD editing finished\."\); \}/,
    "Done no longer leaves edit mode with the same words");
  assert.match(JS, /what === "discard" && entrySnapshot\) \{\s*\n\s*layout = entrySnapshot;/,
    "Cancel no longer restores the entry snapshot");
  assert.match(JS, /what === "reset"\) doAction\(\{ type: "resetToPreset", id: layout\.base_preset \}\)/,
    "Reset no longer resets to the base preset");
});

check("the three hud-edit.js copies and the three HUD page copies stay byte-identical", () => {
  const scripts = [
    join(SRC, "hud-edit.js"),
    join(ROOT, "jarvis-backend", "hud-edit.js"),
    join(ROOT, "backend", "static", "hud-edit.js"),
  ];
  const firstScript = readBytes(scripts[0]);
  for (const file of scripts.slice(1)) {
    assert.ok(firstScript.equals(readBytes(file)), `${scripts[0]} and ${file} differ`);
  }
  const pages = [
    join(SRC, "jarvis_hud.html"),
    join(ROOT, "jarvis-backend", "jarvis_hud.html"),
    join(ROOT, "backend", "jarvis_hud.html"),
  ];
  const firstPage = readBytes(pages[0]);
  for (const file of pages.slice(1)) {
    assert.ok(firstPage.equals(readBytes(file)), `${pages[0]} and ${file} differ`);
  }
});

console.log(`\n${passed} passed, 0 skipped, 0 failed`);
