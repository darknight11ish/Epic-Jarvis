/**
 * The HUD's left rail, holding the two controls the owner asked for
 * (2026-10-26), in their own words:
 *
 *   "also, where are the presets on the jarvis hud in desktop? add a button in
 *    the left column. and move the settings from the top right to the left
 *    column"
 *
 * WHAT THIS PROVES, and why each check is here:
 *
 *   1. the Presets button is IN the left rail's own `.rail-toolbar` group, and
 *      that group is the one rail block no shell hides - the Studio shell
 *      (split-stage, the one the owner runs) hides `.rail-nav`, `.rail-lanes`
 *      and `.rail-systems` by CSS, so a control put in any of those is
 *      invisible to him however well it is written;
 *   2. clicking it opens the EXISTING Layouts menu: one door, not a second
 *      menu - the rail button dispatches the same `jarvis:hud-presets-open`
 *      event H2's "Layout:" badge dispatches, and hud-presets.js still creates
 *      exactly one `#hud-presets-menu`;
 *   3. the settings gear is the shell's, and it now goes into that same rail
 *      group: `#hud-settings` is never written into the vendored page, the
 *      bootstrap has no stage-bar path left, and its id check is what makes
 *      the window hold exactly ONE gear;
 *   4. a plain browser still gets no gear (no shell, no Settings window), and
 *      the Presets button needs no shell at all - it is page markup plus the
 *      page's own module.
 *
 * The behaviour is driven for real in a browser by tests/hud.mjs's "the
 * owner's two rail controls" check (the page, the injected bootstrap and the
 * real menu); this suite is the browser-free half, so the structural failure
 * is caught in a second on a machine with no Playwright. The page's inline
 * script count is NOT this file's business - tests/csp-inline.mjs pins it, and
 * this change adds no inline block.
 *
 *     node tests/hud-rail-tools.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const TAURI = join(HERE, "..", "src-tauri");

const read = (p) => readFileSync(p, "utf8");
const HUD = read(join(SRC, "jarvis_hud.html"));
const PRESETS = read(join(SRC, "hud-presets.js"));
const EDIT = read(join(SRC, "hud-edit.js"));
const BOOT = read(join(TAURI, "src", "hud_bootstrap.js"));

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** The text between two markers, both of which must exist. */
function between(source, start, end, span = 4000) {
  const at = source.indexOf(start);
  assert.notEqual(at, -1, `"${start}" is not in the file`);
  const stop = source.indexOf(end, at);
  assert.notEqual(stop, -1, `"${end}" does not follow "${start}"`);
  return source.slice(at, Math.min(stop, at + span));
}

/* ── 1. The button is in the rail, in the group no shell hides ───────────── */

check("the Presets button is in the left rail, in its own toolbar", () => {
  const rail = between(HUD, 'id="rail-left"', "</aside>", 6000);
  assert.match(rail, /id="rail-toolbar"/, "the rail has no #rail-toolbar group");
  assert.match(rail, /id="rail-presets"/, "the rail has no #rail-presets button");
  // The group sits with the controls, not among the sections a shell hides:
  // after the Studio dock, before the Focus-presets section.
  const dock = HUD.indexOf('id="studio-dock"');
  const tools = HUD.indexOf('id="rail-toolbar"');
  const lanes = HUD.indexOf('id="rail-lanes"');
  assert.ok(dock !== -1 && tools !== -1 && lanes !== -1, "the rail lost one of its blocks");
  assert.ok(dock < tools && tools < lanes,
    "the tools group must sit between the Studio dock and the Focus-presets section");
});

check("the button says what it does, in the page's own monochrome glyphs", () => {
  const button = between(HUD, 'id="rail-presets"', "</button>", 900);
  // Renamed 2026-10-27: the menu is the Presets menu now and lists the PC's
  // model presets and personalities as well as the HUD layouts, so the title
  // names all three (the owner's own words: "you didnt put presets, you put
  // hud layouts").
  assert.match(button, /title="Presets: model presets, personalities and HUD layouts"/,
    "the button needs a plain-words title that names what the menu now lists");
  assert.match(button, /aria-label="Presets: model presets, personalities and HUD layouts"/,
    "the button needs the same plain words for a screen reader");
  assert.match(button, /<span class="rt-label">Presets<\/span>/,
    "the visible word should be 'Presets' in the wide rails");
  assert.match(button, /<svg class="glyph"[\s\S]*stroke="currentColor"/,
    "the icon should be one of the page's currentColor glyphs, not a colour image");
  assert.match(button, /aria-haspopup="menu"/,
    "the button opens a menu; it must say so");
});

check("the rail toolbar is not hidden by the page's small-screen rule", () => {
  // .rail.left .hide-sm is display:none under 720px; the presets/systems
  // sections carry it. The tools group must NOT, or the owner's two controls
  // would vanish in a narrow window.
  const group = between(HUD, 'class="rail-toolbar"', ">", 200);
  assert.doesNotMatch(group, /hide-sm/,
    "the rail's tools group must stay visible at every width");
});

/* ── 2. Every shell keeps the group: read the CSS, all six shells ────────── */

check("no shell hides the rail's toolbar, in any of the six shells", () => {
  const css = between(HUD, "<style>", "</style>", HUD.length);
  const shells = ["three-column", "split-stage", "center-core",
    "two-column-left", "two-column-right", "single-stage-bento"];
  for (const shell of shells) {
    assert.match(HUD, new RegExp(`html\\[data-hud-shell="${shell}"\\]`),
      `the page has no CSS for the ${shell} shell at all`);
  }
  // Every rule that hides something under a shell attribute, one by one: none
  // of them may hide the TOOLBAR ITSELF. `.rail-toolbar-btn .rt-label` is a
  // different thing and is allowed - that is the Studio rail hiding the word
  // and keeping the icon, exactly as the Jarvis-bar pill does.
  const rules = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .map((m) => ({ selector: m[1].replace(/\s+/g, " ").trim(), body: m[2] }));
  const hiders = rules.filter((r) => /display\s*:\s*none/.test(r.body)
    && r.selector.includes("[data-hud-shell="));
  assert.ok(hiders.length > 0, "no shell rule hides anything - the parse found nothing");
  for (const rule of hiders) {
    assert.ok(!/(?:^|[\s,>+~])\.rail-toolbar(?![-_a-zA-Z0-9])/.test(rule.selector),
      `a shell hides the rail's toolbar: ${rule.selector}`);
  }
});

check("the Studio shell still hides the blocks the toolbar exists for", () => {
  // This is the REASON for the toolbar, and it must stay true: if split-stage
  // ever stopped hiding these, the comment and the toolbar's design would be
  // describing a page that no longer exists.
  const css = between(HUD, "<style>", "</style>", HUD.length);
  const rules = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .map((m) => ({ selector: m[1].replace(/\s+/g, " ").trim(), body: m[2] }));
  for (const block of [".rail-nav", ".rail-lanes", ".rail-systems"]) {
    const found = rules.some((r) => r.selector.includes("split-stage")
      && r.selector.includes(block) && /display\s*:\s*none/.test(r.body));
    assert.ok(found,
      `split-stage no longer hides ${block} - the rail tools group's reason is stale`);
  }
});

check("the drawer shells still carry the same rail, so the group travels with it", () => {
  // center-core, two-column-right and single-stage-bento slide the LEFT rail
  // in as a drawer. That is fine - the owner's controls only have to be IN it.
  // What must not happen is the rail being hidden outright, which is the bug
  // H3-PM-2 fixed on 2026-10-22.
  assert.match(HUD, /html\[data-hud-shell="center-core"\] \.rail\.left\{/,
    "the Ambient shell no longer draws the left rail as a drawer");
  assert.match(HUD, /html\[data-hud-shell="two-column-right"\] \.rail\.left\{/,
    "the two-column-right shell no longer draws the left rail as a drawer");
  assert.match(HUD, /html\[data-hud-shell="single-stage-bento"\] \.rail\.left\{/,
    "the bento shell no longer draws the left rail as a drawer");
  assert.match(HUD, /html\[data-hud-shell="three-column"\] #shell\{grid-template-columns:220px/,
    "the Cockpit shell no longer draws the left rail as a column");
  assert.match(HUD, /html\[data-hud-shell="split-stage"\] #shell\{grid-template-columns:60px/,
    "the Studio shell no longer draws its 60px icon rail");
});

/* ── 3. One door: the rail button opens the ONE Layouts menu ─────────────── */

check("the rail button dispatches the badge's own event, with itself as the anchor", () => {
  // The one-door rule: hud-edit.js's badge dispatches `jarvis:hud-presets-open`
  // and hud-presets.js listens for it. The rail button joins that path rather
  // than calling a second open path of its own.
  assert.match(EDIT, /dispatchEvent\(new CustomEvent\("jarvis:hud-presets-open"\)\)/,
    "H2's badge no longer dispatches the Layouts-menu event this test names");
  assert.match(PRESETS, /win\.addEventListener\("jarvis:hud-presets-open"/,
    "hud-presets.js no longer listens for the door event");
  const wiring = between(PRESETS, 'railDoor.dataset.hudPresets !== "1"', "});", 900);
  assert.match(wiring, /win\.dispatchEvent\(new CustomEvent\("jarvis:hud-presets-open"/,
    "the rail button must dispatch the same event the badge does");
  assert.match(wiring, /detail:\s*\{\s*anchor:\s*railDoor\s*\}/,
    "the rail button must carry itself as the anchor, so the menu opens beside it");
});

check("there is still exactly ONE Layouts menu, and the page holds none", () => {
  assert.equal((PRESETS.match(/menu\.id = MENU_ID/g) || []).length, 1,
    "hud-presets.js must create exactly one menu element");
  assert.doesNotMatch(HUD, /id="hud-presets-menu"/,
    "the vendored page must not declare a Layouts menu of its own");
  assert.doesNotMatch(BOOT, /hud-presets-menu/,
    "the shell must not build a Layouts menu - the page's module owns it");
  // One listener for the event, so a click cannot toggle twice.
  assert.equal((PRESETS.match(/win\.addEventListener\("jarvis:hud-presets-open"/g) || []).length, 1,
    "the door event must have exactly one listener");
});

check("a second click on the rail button closes the menu instead of reopening it", () => {
  // The menu dismisses on pointerdown anywhere outside it, and both DOORS have
  // to be exempt or the second click on a door becomes close-then-reopen.
  const outside = between(PRESETS, "doc.addEventListener(\"pointerdown\"", "}, true)", 900);
  assert.match(outside, /railDoor\.contains\(target\)/,
    "the rail button must be exempt from the menu's outside-click dismiss, as the badge is");
  assert.match(outside, /badge\.contains\(target\)/,
    "the badge must stay exempt too");
});

/* ── 4. The gear: the shell's, in the rail, and exactly one ──────────────── */

check("the page never carries a settings gear - the shell still adds the only one", () => {
  assert.doesNotMatch(HUD, /id="hud-settings"/,
    "jarvis_hud.html must stay byte-identical to its backend copies, and the gear is the shell's");
  assert.equal((BOOT.match(/id = "hud-settings"/g) || []).length, 1,
    "the bootstrap must create exactly one #hud-settings");
  assert.match(BOOT, /if \(!railToolbar \|\| document\.getElementById\("hud-settings"\)\) return;/,
    "the gear's one-only guard must stay: a second add attempt returns before creating anything");
});

check("the gear is added to the rail toolbar, and the stage-bar road is gone", () => {
  const gear = between(BOOT, "function addSettingsGear", "appendChild(gear)", 3000);
  assert.match(gear, /document\.querySelector\("\.rail-toolbar"\)/,
    "the gear must be added to the rail's toolbar");
  assert.doesNotMatch(gear, /stage-bar/,
    "the gear is back on the stage bar - the owner asked for the left column (2026-10-26)");
  assert.doesNotMatch(BOOT, /stage-bar/,
    "no part of the bootstrap should reach for the stage bar for the gear any more");
});

check("the gear keeps its name, its command, its rail box and its shell-only rule", () => {
  assert.match(BOOT, /var GEAR_SAID = "Jarvis settings";/,
    "the HUD's gear must keep the bar's and the widget's name");
  assert.match(BOOT, /gear\.setAttribute\("aria-label", GEAR_SAID\)/,
    "the gear needs a name for a screen reader");
  // 2026-10-27, the owner: "the spacing of the two new buttons is uneven" and
  // "i want the settings to be in a similar style of icon to the others". The
  // gear now wears the page's own rail-button class - so its padding, border
  // and height ARE the Presets button's rules, and the Studio rail draws both
  // as the same 42x38 box - and it draws the rail's stroke glyph instead of
  // the bar's filled one. The bar's and the widget's gears are untouched, and
  // the name for a screen reader is unchanged.
  assert.match(BOOT, /gear\.className = "rail-toolbar-btn hud-settings";/,
    "the gear must take the page's own rail-button class, or the pair is uneven again");
  assert.doesNotMatch(BOOT, /gear\.className = "ghost hud-settings"/,
    "the gear is back on the .ghost class the Presets button does not use");
  const gearBlock = between(BOOT, "function addSettingsGear", "appendChild(gear)", 3600);
  assert.doesNotMatch(gearBlock, /gear\.style\.width|gear\.style\.height|26px/,
    "the gear is being sized by hand again - the page's rail class owns its box");
  assert.match(gearBlock, /viewBox="0 0 24 24"/,
    "the gear is not on the rail's 24-unit grid");
  assert.match(gearBlock, /fill="none"/, "the gear is a filled icon again");
  assert.match(gearBlock, /stroke="currentColor"/,
    "the gear is not drawn with the rail's currentColor stroke");
  assert.match(gearBlock, /stroke-width="1\.8"/,
    "the gear does not use the rail's stroke width");
  assert.match(gearBlock, /class="glyph"/,
    "the gear is not sized by the page's .rail-toolbar-btn .glyph rule");
  assert.doesNotMatch(gearBlock, /M8 5\.6a2\.4/,
    "the gear draws the bar's filled glyph again");
  assert.match(BOOT, /invoke\("open_fix_place",\s*\{\s*place:\s*"settings"\s*\}\)/,
    "the gear must keep calling open_fix_place with place: settings");
  // Shell-only: the gate returns before addSettingsGear with no __TAURI__.
  const gate = between(BOOT, "function hudSettingsGear", "hudSettingsGear();", 700);
  assert.match(gate, /window\.__TAURI__/,
    "the gear's gate must be the shell's own __TAURI__ presence");
  assert.match(gate, /if \(!\(tauri && tauri\.core && typeof tauri\.core\.invoke === "function"\)\) return;/,
    "a page in a plain browser must be given no gear at all");
});

/* ── 5. The menu lists the PC's own presets (2026-10-27) ─────────────────── */

check("the menu is called Presets, and the PC's own lists come first", () => {
  assert.match(PRESETS, /menu\.setAttribute\("aria-label", "Presets"\)/,
    "the menu's own name is not Presets any more");
  assert.match(PRESETS, /el\(doc, "p", "hud-presets-title", "Presets"\)/,
    "the menu title is not the word Presets");
  assert.doesNotMatch(PRESETS, /"HUD layouts"\)/,
    "the menu still titles itself HUD layouts");
  // The owner's two new kinds sit above the layouts they used to be the only
  // content of; "My personalities" is conditional, so its section function
  // exists but is only appended when the PC lists one.
  const order = ["Model presets", "Personality", "My personalities", "Built-in layouts"];
  let at = -1;
  for (const heading of order) {
    const next = PRESETS.indexOf(`section("${heading}")`);
    assert.ok(next > at, `the menu's "${heading}" section is missing or out of order`);
    at = next;
  }
  assert.match(PRESETS, /const ownPersonalities = renderMyPersonalities\(\);/,
    "the My personalities section is not conditional on the PC listing any");
});

check("a model preset raises the PC's ONE card, and nothing is marked before the PC says so", () => {
  assert.match(PRESETS,
    /Applying one asks the PC for ONE approval card - nothing is chosen until you answer it\./,
    "the section does not say the card rule in words");
  assert.match(PRESETS, /await applyFocusPresetOnPc\(win, id\);/,
    "a model-preset click does not go through the apply road");
  // The mark comes from the REFETCHED contract's chosen_preset - never from
  // the click. Both halves are read from the code so a future edit that marks
  // optimistically fails here instead of looking finished.
  const afterApply = between(PRESETS, "await applyFocusPresetOnPc(win, id);",
    "} catch (error) {", 900);
  assert.match(afterApply, /await readFocusPresetsOnPc\(win\)/,
    "a preset is marked without refetching the PC's contract");
  assert.match(afterApply, /row && row\.chosen/,
    "the mark does not come from the PC's chosen_preset");
  assert.doesNotMatch(PRESETS, /chosen: true|\.chosen = true/,
    "the menu marks a preset chosen on its own");
});

check("a personality switch is immediate, shows the PC's own words, and asks for no card", () => {
  assert.match(PRESETS,
    /Switching is immediate: it changes how Jarvis talks and asks for no card\./,
    "the section does not say the no-card rule in words");
  assert.match(PRESETS, /await switchPersonalityOnPc\(win, id\);/,
    "a personality click does not go through the switch road");
  assert.match(PRESETS, /typeof answer\.said === "string"/,
    "the PC's own switch_ack (its `said`) is not shown");
  assert.match(PRESETS, /pcManner = await readPersonalitiesOnPc\(win\)/,
    "the new current personality is not read back from the PC");
});

check("the rail box rules the pair shares are the page's own", () => {
  // The page draws BOTH controls with one class; the gear adds no width/height
  // of its own, so the Studio rail's 42x38 rule (and the 14/16px glyph rule)
  // applies to it exactly as it does to the Presets button.
  assert.match(HUD, /\.rail-toolbar-btn \.glyph\{width:14px; height:14px;/,
    "the rail's own glyph size rule is gone");
  assert.match(HUD, /html\[data-hud-shell="split-stage"\] \.rail-toolbar-btn\{[^}]*width:42px; height:38px;/,
    "the Studio rail's square-button rule is gone");
  assert.match(HUD, /html\[data-hud-shell="split-stage"\] \.rail-toolbar-btn \.glyph\{width:16px; height:16px;\}/,
    "the Studio rail no longer sizes the pair's glyphs to one size");
});

check("the HUD window is granted the two commands the menu calls, and Settings is not broadened", () => {
  const capability = JSON.parse(read(join(TAURI, "capabilities", "hud.json")));
  assert.equal(capability.permissions.filter((name) => name === "hud-personalities").length, 1,
    "capabilities/hud.json does not grant exactly one hud-personalities set");
  const surfaces = read(join(TAURI, "permissions", "surfaces.toml"));
  const start = surfaces.indexOf('identifier = "hud-personalities"');
  assert.notEqual(start, -1, "surfaces.toml has no hud-personalities set");
  const set = surfaces.slice(start, start + 500);
  assert.match(set, /"allow-hud-personalities"/, "the set misses allow-hud-personalities");
  assert.match(set, /"allow-hud-switch-personality"/, "the set misses allow-hud-switch-personality");
  assert.doesNotMatch(set, /allow-set-manner|allow-get-manner/,
    "the HUD set was widened to the Settings window's whole manner commands");
  const build = read(join(TAURI, "build.rs"));
  const lib = read(join(TAURI, "src", "lib.rs"));
  for (const command of ["hud_personalities", "hud_switch_personality"]) {
    assert.ok(build.includes(`"${command}"`), `build.rs does not export ${command} to the ACL`);
    assert.ok(lib.includes(`plain_errors::${command}`), `lib.rs does not register ${command}`);
  }
});

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nall checks passed");
process.exit(fails.length ? 1 : 0);
