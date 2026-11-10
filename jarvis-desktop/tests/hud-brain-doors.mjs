/**
 * hud-brain-doors.mjs - the Brain WINDOW opens from the HUD, both ways the
 * owner asked for (Wave-9 Lane 2; Q5 ruling of 2026-11-07).
 *
 *     node tests/hud-brain-doors.mjs
 *
 * WHAT THIS PINS, with no browser and no window:
 *
 *   1. BOTH doors exist, in the places the owner named: a "Brain" word in the
 *      HUD's top menu bar (#stage-brain-window, beside Presets) and a "Brain"
 *      button in the left column rail (#rail-brain-window, in .rail-toolbar -
 *      the one rail block no shell hides). Neither is a tab and neither
 *      selects a panel.
 *   2. BOTH call the SAME opener: `openBrainAt`, which is the shell's existing
 *      `open_fix_place {place: "brain"}`. There is no second command, no new
 *      window and no second way to open it; Rust's open_fix_place maps "brain"
 *      to `windows::show_brain`, the same call the tray row uses.
 *   3. NOTHING IS REMOVED: the rail's own `data-view="brain"` (the Galaxy map),
 *      the five stage tabs, Prests and the settings gear all stay; the shell
 *      still relabels the rail's VIEW to "Galaxy", so "Brain" means one thing.
 *   4. A plain browser (no shell) shows neither door: both are page markup with
 *      `hidden`, revealed by the bootstrap only when a shell is there - the
 *      same rule #rail-faces and #rail-live already follow, because a page
 *      with no command must not offer a door that cannot open.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const TAURI = join(HERE, "..", "src-tauri");
const RUST = join(TAURI, "src");
const read = (p) => readFileSync(p, "utf8");

const HUD = read(join(SRC, "jarvis_hud.html"));
const BOOT = read(join(RUST, "hud_bootstrap.js"));
const PLAIN = read(join(RUST, "plain_errors.rs"));
const WINDOWS = read(join(RUST, "windows.rs"));

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

/** The text between two markers, both of which must exist. */
function between(source, start, end, span = 30000) {
  const at = source.indexOf(start);
  assert.notEqual(at, -1, `"${start}" is not in the file`);
  const stop = source.indexOf(end, at);
  assert.notEqual(stop, -1, `"${end}" does not follow "${start}"`);
  return source.slice(at, Math.min(stop, at + span));
}

/** One button's own markup, from its id to its closing tag. */
function buttonById(html, id) {
  const at = html.indexOf(`id="${id}"`);
  assert.notEqual(at, -1, `#${id} is gone from the HUD page`);
  const start = html.lastIndexOf("<button", at);
  assert.notEqual(start, -1, `#${id} is not inside a <button>`);
  const stop = html.indexOf("</button>", at);
  assert.notEqual(stop, -1, `#${id}'s button never closes`);
  return html.slice(start, stop + "</button>".length);
}

/* ── 1. The left column rail's door ─────────────────────────────────────── */

check("the rail's Brain button is in the left rail's own toolbar", () => {
  const railLeft = between(HUD, 'id="rail-left"', "</aside>", 40000);
  assert.match(railLeft, /id="rail-toolbar"/, "the rail lost its toolbar group");
  const toolbar = between(railLeft, 'id="rail-toolbar"', "</div>", 20000);
  assert.match(toolbar, /id="rail-brain-window"/,
    "no #rail-brain-window inside .rail-toolbar - a rail block a shell hides would not reach him");
  // The group sits where the other always-visible controls are, after the
  // Studio dock and before the Focus-presets section (the same rule
  // tests/hud-rail-tools.mjs holds for Presets).
  const dock = HUD.indexOf('id="studio-dock"');
  const tools = HUD.indexOf('id="rail-toolbar"');
  const lanes = HUD.indexOf('id="rail-lanes"');
  assert.ok(dock !== -1 && tools !== -1 && lanes !== -1, "a rail block is gone");
  assert.ok(dock < tools && tools < lanes, "the toolbar moved out of its place");
});

check("the rail button says 'Brain' and says what it opens", () => {
  const button = buttonById(HUD, "rail-brain-window");
  assert.match(button, />Brain</, "the visible word is not Brain");
  assert.match(button, /aria-label="Open the Brain window"/,
    "the accessible name does not say it opens the Brain WINDOW");
  assert.match(button, /title="Brain window: memory, models, skills, history and tutorials"/);
  assert.match(button, /class="rail-toolbar-btn"/, "it does not wear the rail's button class");
  assert.match(button, /<svg class="glyph"/, "it has no monochrome glyph like its neighbours");
});

/* ── 2. The top menu bar's word ──────────────────────────────────────────── */

check("the top menu bar carries a Brain word beside Presets, outside the tablist", () => {
  const words = between(HUD, 'id="stage-words"', "</div>", 6000);
  assert.match(words, /id="stage-brain-window"/, "no #stage-brain-window in the menu words");
  assert.match(words, /id="stage-presets"/, "the Presets word it sits beside is gone");
  assert.ok(HUD.indexOf('id="stage-presets"') < HUD.indexOf('id="stage-brain-window"'),
    "the Brain word must follow Presets (the owner's order: next to the words already there)");
  const word = buttonById(HUD, "stage-brain-window");
  assert.match(word, />Brain</, "the visible word is not Brain");
  assert.match(word, /class="stage-tab stage-word"/, "it is not drawn as a menu word");
  assert.match(word, /aria-label="Open the Brain window"/);
  assert.doesNotMatch(word, /role="tab"/,
    "it is a door, not a tab - a tab would promise a panel on this page");
});

check("the five stage tabs are the new plain-word header and none of them became the Brain door", () => {
  // Wave 15 (2026-11-10): the legacy #stage-tabs strip is retired; the ONE
  // stage header is #hud-stage-nav, five plain-word tabs (spec section 2.1).
  const navAt = HUD.indexOf('id="hud-stage-nav"');
  assert.ok(navAt > -1, "#hud-stage-nav is gone - the stage has no switcher");
  const tabs = HUD.slice(navAt, HUD.indexOf("</nav>", navAt));
  const choices = [...tabs.matchAll(/data-hud-nav="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(choices, ["talk", "galaxy", "today", "reminders", "telemetry"],
    "the stage's five tabs changed");
  assert.equal(HUD.includes('id="stage-tabs"'), false,
    "the retired #stage-tabs strip is back - the design keeps ONE navigation");
  assert.doesNotMatch(tabs, /brain-window/, "the Brain door was put inside the tab header");
});

/* ── 3. Both doors, one opener ───────────────────────────────────────────── */

check("both doors are page markup, hidden until a shell reveals them", () => {
  for (const id of ["rail-brain-window", "stage-brain-window"]) {
    const button = buttonById(HUD, id);
    assert.match(button, /\shidden(\s|>)/,
      `#${id} would draw in a plain browser with no command to send`);
  }
});

check("the bootstrap reveals BOTH ids and wires them to one handler", () => {
  assert.match(BOOT, /function wireBrainWindowDoors\(\)/,
    "the reveal/wire function is gone");
  assert.match(BOOT, /var ids = \["rail-brain-window", "stage-brain-window"\]/,
    "the two ids are not the two doors");
  assert.match(BOOT, /el\.hidden = false/, "the doors are never revealed");
  assert.match(BOOT, /el\.addEventListener\("click", openBrainWindowFromHud\)/,
    "the doors are not wired to the one click handler");
  assert.match(BOOT, /function openBrainWindowFromHud\(event\)[\s\S]{0,160}openBrainAt\("brain"\)/,
    "the handler does not call the existing opener with the Brain window's place");
});

check("there is exactly ONE Brain-window opener, and it is open_fix_place {place: brain}", () => {
  const calls = [...BOOT.matchAll(/openBrainAt\("brain"\)/g)];
  assert.equal(calls.length, 1, `the page calls the opener ${calls.length} times`);
  const opener = between(BOOT, "function openBrainAt(place)", "function openBrainWindowFromHud");
  const navCalls = [...opener.matchAll(/navInvoke\("([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(navCalls, ["open_fix_place"],
    "the Brain window is opened through a command other than the shell's open_fix_place");
  assert.match(opener, /place: named/, "the place is not passed through to the command");
});

check("Rust's open_fix_place really opens the Brain window for the place 'brain'", () => {
  const fn = between(PLAIN, "pub async fn open_fix_place", "\n}\n", 4000);
  assert.match(fn, /"brain" => crate::windows::show_brain\(&app\)/,
    "open_fix_place no longer maps 'brain' to show_brain");
  assert.match(WINDOWS, /fn show_brain\(/, "windows.rs has no show_brain");
});

check("nothing that already opened something was removed", () => {
  for (const id of ["rail-presets", "rail-live", "rail-faces", "rail-calendar-open",
                    "stage-presets", "stage-galaxy-options"]) {
    assert.match(HUD, new RegExp(`id="${id}"`), `#${id} is gone`);
  }
  // The settings gear is the SHELL's (never written into the vendored page), so
  // it is checked where it is made, not in the page markup.
  assert.match(BOOT, /hud-settings/, "the shell's settings gear is gone");
  assert.match(BOOT, /function settingsFromHud\(/, "the settings gear lost its own opener");
  assert.match(HUD, /data-view="brain"/, "the rail's own Brain VIEW (Galaxy map) was removed");
  // The shell still renames that view's label to Galaxy, so one HUD has one
  // "Brain": the window the two new doors open.
  const relabel = between(BOOT, "function relabelBrainTab()", "if (document.readyState");
  assert.match(relabel, /replace\("Brain", "Galaxy"\)/,
    "the shell stopped renaming the rail's VIEW to Galaxy - 'Brain' is ambiguous again");
});

check("no inline handler or new script was smuggled in with the doors", () => {
  for (const id of ["rail-brain-window", "stage-brain-window"]) {
    const button = buttonById(HUD, id);
    assert.doesNotMatch(button, /\son[a-z]+=/, `#${id} carries an inline event handler`);
  }
  assert.match(HUD, /id="stage-brain-window"[^>]*aria-label="Open the Brain window"[^>]*>/,
    "the top-menu word markup changed shape");
});

/* ── 4. The Galaxy map's one-click door (2026-11-09) ────────────────────── */

// The owner's IA recommendations: "honest Galaxy labels + a 1-click HUD->Brain
// map button". The new door is NOT a second Brain-window opener: it is the same
// `openBrainAt`, given the Brain's own "galaxy" place, which leaves the Brain
// place key first (the settings gear's own shape) and calls the same
// navigation-only `open_fix_place`.

check("the Galaxy map's door is in the rail's always-visible toolbar, after Brain", () => {
  const railLeft = between(HUD, 'id="rail-left"', "</aside>", 40000);
  const toolbar = between(railLeft, 'id="rail-toolbar"', "</div>", 20000);
  assert.match(toolbar, /id="rail-galaxy-map"/,
    "no #rail-galaxy-map inside .rail-toolbar - a rail block a shell hides would not reach him");
  assert.ok(toolbar.indexOf('id="rail-brain-window"') < toolbar.indexOf('id="rail-galaxy-map"'),
    "the memory-map door should follow the Brain window's own door");
});

check("the Galaxy map's door says the owner's words, and is a rail button like its neighbours", () => {
  const button = buttonById(HUD, "rail-galaxy-map");
  assert.match(button, /<span class="rt-label">Galaxy - everything at a glance<\/span>/,
    "the visible word is not the owner's own sentence");
  assert.match(button, /aria-label="Galaxy - everything at a glance"/,
    "a screen reader does not hear the same words");
  assert.match(button, /title="Galaxy: everything at a glance - the memory map, in the Brain window"/,
    "the title does not say what pressing it opens");
  assert.match(button, /class="rail-toolbar-btn"/, "it does not wear the rail's button class");
  assert.match(button, /<svg class="glyph"/, "it has no monochrome glyph like its neighbours");
  assert.match(button, /\shidden(\s|>)/,
    "it would draw in a plain browser with no command to send");
  assert.doesNotMatch(button, /\son[a-z]+=/, "it carries an inline event handler");
  // Its own row in the narrow rail: the page's own rule, not an inline style.
  const css = between(HUD, "<style>", "</style>", HUD.length);
  assert.match(css, /\.rail-toolbar #rail-galaxy-map\{flex:1 1 100%;\}/,
    "the long word does not take its own row in the rail");
  assert.match(css, /html\[data-hud-shell="split-stage"\] \.rail-toolbar #rail-galaxy-map\{flex:0 0 auto;\}/,
    "in the Studio column the button would stretch to the column's full height");
});

check("the bootstrap reveals the Galaxy door and wires it to the one opener", () => {
  assert.match(BOOT, /function wireGalaxyMapDoor\(\)/, "the reveal/wire function is gone");
  assert.match(BOOT, /var el = document\.getElementById\("rail-galaxy-map"\)/,
    "the bootstrap no longer looks for the Galaxy door's id");
  assert.match(BOOT, /el\.addEventListener\("click", openGalaxyMapFromHud\)/,
    "the door is not wired to its one handler");
  assert.match(BOOT, /function openGalaxyMapFromHud\(event\)[\s\S]{0,160}openBrainAt\("galaxy"\)/,
    "the handler does not call the existing opener with the Galaxy place");
});

check("the Galaxy door uses the SAME command, and leaves the Brain's own place key first", () => {
  const opener = between(BOOT, "function openBrainAt(place)", "function openBrainWindowFromHud");
  const navCalls = [...opener.matchAll(/navInvoke\("([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(navCalls, ["open_fix_place"],
    "the Galaxy place is opened through a command other than the shell's open_fix_place");
  assert.match(opener, /place: named/, "the place is not passed through to the command");
  // The gear's pattern: the place key first, then the one command. The key is
  // spelled in two files that cannot import each other - held equal here.
  assert.match(BOOT, /var BRAIN_PLACE_KEY = "jarvis\.brain\.place";/);
  const BRAIN = read(join(SRC, "forget-range.js"));
  assert.match(BRAIN, /export const BRAIN_PLACE_KEY = "jarvis\.brain\.place";/,
    "the Brain reads a different key from the one the HUD leaves");
  assert.match(opener, /localStorage\.setItem\(\s*BRAIN_PLACE_KEY,\s*JSON\.stringify\(\{ place: "galaxy", at: Date\.now\(\) \}\)/,
    "the Galaxy place is not left under the Brain's key");
});

check("the Brain accepts 'galaxy' as a place, opens Advanced, and shows its map", () => {
  const PANEL = read(join(SRC, "forget-range-panel.js"));
  assert.match(PANEL, /left\.place === "galaxy"/,
    "takeAnyPlace still drops the HUD's Galaxy place, so the press would land elsewhere");
  const BRAIN_JS = read(join(SRC, "brain.js"));
  assert.match(BRAIN_JS, /Object\.prototype\.hasOwnProperty\.call\(VIEWS, place\)/,
    "showPlace no longer opens one of the rail's own views by its key");
  assert.match(BRAIN_JS, /if \(ADVANCED_VIEWS\.includes\(place\) && !advancedOpen\) dom\.advancedToggle\?\.click\(\);/,
    "Galaxy is behind Advanced: the place must open the disclosure, or the selected tab is hidden");
  assert.match(BRAIN_JS, /galaxy: \{ title: "The memory map", sub: "what Jarvis remembers" \}/,
    "the view's plain-words title is gone");
});

console.log(`\n${fails.length ? fails.length + " failed" : "all checks passed"}: ` +
  `${fails.length ? fails.join(", ") : "the HUD's two Brain-window doors and the Galaxy map door hold"}`);
process.exit(fails.length ? 1 : 0);
