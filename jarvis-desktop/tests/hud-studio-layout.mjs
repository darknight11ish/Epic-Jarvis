/**
 * hud-studio-layout.mjs - Wave 10 (2026-11-08): the two confirmed Studio
 * layout faults, pinned so they cannot come back.
 *
 *   node tests/hud-studio-layout.mjs
 *
 * NO BROWSER NEEDED. The fixes are CSS in `src/hud-link.css` (the desktop
 * shell's own injected stylesheet) and a watcher in `src-tauri/src/hud_bootstrap.js`
 * (the script the shell injects), so their rules and their guard are pinned by
 * source here. The measured boxes are driven by the Playwright checks in
 * tests/hud.mjs ("Studio: ..."), which CI runs; the same geometry was proven
 * at the desk with a static headless-Edge render of the owner's 150% window.
 *
 * THE TWO FAULTS (owner's screenshot, 2026-11-08 15:18):
 *
 *   A. In the Studio (split-stage) layout `#stage` is a CSS grid. The two
 *      host-raised cards, `#secret-handoff` and `#connect-account`, had NO
 *      placement, so the grid auto-placed them into the face column, row 3,
 *      and pushed the conversation and the face down. The editor's Stage-top
 *      region - which OWNS the approvals queue, because hud-edit.js moves the
 *      queues into it on mount - was auto-placed too, so the first free cell
 *      beside it was the face column.
 *
 *   B. `#hud-safety` is the fixed safety strip at the top of the window. At the
 *      owner's 150% scaling the stage bar's model/state chips slid under it
 *      (his screenshot showed "DING BY" peeking out). H4 promises the strip is
 *      always visible AND covers no control, so the shell now reserves a band
 *      for it: hud_bootstrap.js watches the strip, sets
 *      `body[data-hud-safety-visible]` and `--hud-safety-band`, and hud-link.css
 *      pushes the Studio shell's content below it.
 *
 * WHY THE PAGE IS UNTOUCHED: `jarvis_hud.html` is a BESIDE-file - a change
 * there must be copied into `backend/jarvis_hud.html` and
 * `jarvis-backend/jarvis_hud.html` - so the fix lives in the two desktop-only
 * files the shell injects, and this suite proves the page did not move.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const TAURI = join(HERE, "..", "src-tauri", "src");
const CSS = readFileSync(join(SRC, "hud-link.css"), "utf8");
const BOOT = readFileSync(join(TAURI, "hud_bootstrap.js"), "utf8");
const PAGE = readFileSync(join(SRC, "jarvis_hud.html"), "utf8");

let passed = 0;
function check(name, fn) {
  fn();
  passed += 1;
  console.log(`ok   ${name}`);
}

/** The Wave-10 block this lane added to the shell's stylesheet, alone. */
const BLOCK = CSS.slice(CSS.indexOf("Wave 10 (2026-11-08)"));

/** The watcher this lane added to the injected bootstrap, alone. */
const WATCH = BOOT.slice(
  BOOT.indexOf("function watchSafetyBand()"),
  BOOT.indexOf('if (document.readyState === "loading") {\n    document.addEventListener("DOMContentLoaded", watchSafetyBand'),
);

check("the Studio grid is re-numbered so the two host cards own full-width rows", () => {
  // Non-edit: 9 explicit rows (1 bar | 2 menu | 3 main-screen strip |
  // 4 secret | 5 connect | 6 Stage-top region/approvals | 7 banner |
  // 8 model-warn | 9 conversation + face).
  assert.match(BLOCK,
    /html\[data-hud-shell="split-stage"\] #stage\{\s*grid-template-rows:auto auto auto auto auto auto auto auto minmax\(0, 1fr\);/,
    "the non-edit Studio grid is not the 9-row template");
  assert.match(BLOCK,
    /#stage > #secret-handoff\{\s*grid-column:1 \/ -1; grid-row:4; margin:10px 16px 0;/,
    "#secret-handoff has no deliberate full-width row");
  assert.match(BLOCK,
    /#stage > #connect-account\{\s*grid-column:1 \/ -1; grid-row:5; margin:10px 16px 0;/,
    "#connect-account has no deliberate full-width row");
  // The rows below the two new cards shift down with them.
  assert.match(BLOCK, /#stage > #banner\{grid-row:7;\}/,
    "the banner was not moved to row 7 below the raised cards");
  assert.match(BLOCK, /#stage > #model-warn\{grid-row:8;\}/,
    "the model warning was not moved to row 8");
  assert.match(BLOCK,
    /#stage > #talk,\s*html\[data-hud-shell="split-stage"\] #stage > #brain\{grid-row:9;\}/,
    "the conversation/face row was not moved below the raised cards");
  // The main-screen strip is a direct child too; it gets its own row rather
  // than being auto-placed (and never claims a cell on the Galaxy tab, where
  // the page hides it).
  assert.match(BLOCK, /#stage > #hud-home-cards\{\s*grid-column:1 \/ -1; grid-row:3;/,
    "the main-screen card strip is still auto-placed in the Studio grid");
});

check("the Stage-top region gets a row of its own - it owns the approvals queue", () => {
  // hud-edit.js MOVES #approvals/#initiative into this region on mount, so
  // hiding it (or leaving it auto-placed) would hide or mis-place the queue.
  assert.match(BLOCK,
    /#stage > \[data-hud-region="stage_top"\]\{\s*grid-column:1 \/ -1; grid-row:6; margin:10px 16px 0;/,
    "the editor's Stage-top region (which owns the approvals queue) is still auto-placed");
  assert.doesNotMatch(BLOCK,
    /#stage > \[data-hud-region="stage_top"\]\{display:none/,
    "the Stage-top region is hidden outside Edit HUD - that would hide the approvals queue");
  // Before the editor mounts, the two queues are direct children; they belong
  // in that same row.
  assert.match(BLOCK,
    /#stage > #approvals,\s*html\[data-hud-shell="split-stage"\] #stage > #initiative\{\s*grid-column:1 \/ -1; grid-row:6; margin:10px 16px 0;/,
    "the pre-mount approvals/initiative queues have no deliberate row");
});

check("a hidden stage card stops claiming a grid cell", () => {
  // The page's author display:flex beats the UA [hidden] rule. Scoped to the
  // GRID shell only: every other shell still lays the stage out as a flex
  // column, where the page's own display rules have never pushed anything.
  assert.match(BLOCK,
    /html\[data-hud-shell="split-stage"\] #stage > \[hidden\]\{display:none !important;\}/,
    "a hidden stage card can still claim a full-width grid cell");
});

check("the EDIT-MODE template keeps step, and the Stage-top region keeps row 3", () => {
  // Edit: 10 rows (1 bar | 2 editor banner | 3 Stage-top region | 4 secret |
  // 5 connect | 6 menu | 7 main-screen strip | 8 banner | 9 model-warn |
  // 10 conversation + face). Approvals/initiative are inside the region, so
  // they take no #stage row of their own.
  assert.match(BLOCK,
    /body\[data-hud-edit="on"\] #stage\{\s*grid-template-rows:auto auto auto auto auto auto auto auto auto minmax\(0, 1fr\);/,
    "the edit-mode Studio grid is not the 10-row template");
  assert.match(BLOCK,
    /body\[data-hud-edit="on"\] #stage > \[data-hud-region="stage_top"\]\{\s*grid-column:1 \/ -1; grid-row:3;/,
    "the editor's Stage-top region is not row 3");
  assert.match(BLOCK,
    /body\[data-hud-edit="on"\] #stage > #secret-handoff\{\s*grid-column:1 \/ -1; grid-row:4;/,
    "the secret card collides with the editor's Stage-top region in Edit HUD");
  assert.match(BLOCK,
    /body\[data-hud-edit="on"\] #stage > #connect-account\{\s*grid-column:1 \/ -1; grid-row:5;/,
    "the connect card has no own row in Edit HUD");
  for (const [id, row] of [["stage-menu", 6], ["hud-home-cards", 7],
                           ["banner", 8], ["model-warn", 9]]) {
    assert.match(BLOCK,
      new RegExp(`body\\[data-hud-edit="on"\\] #stage > #${id}\\{[^}]*grid-row:${row};`),
      `#${id} is not on edit row ${row}`);
  }
  assert.match(BLOCK,
    /body\[data-hud-edit="on"\] #stage > #talk,\s*\n?\s*html\[data-hud-shell="split-stage"\] body\[data-hud-edit="on"\] #stage > #brain\{\s*grid-row:10; grid-column:1 \/ -1;/,
    "the edit-mode conversation/face row is not below the new card rows");
});

/* ── Bug B: the safety strip's reserved band ─────────────────────────────── */

check("the shell reserves a band for the strip, scoped to the Studio shell", () => {
  assert.match(BLOCK,
    /html\[data-hud-shell="split-stage"\] body\[data-hud-safety-visible\] #shell\{\s*padding-top:var\(--hud-safety-band, 0px\);/,
    "no band rule reserves room for the fixed safety strip");
  // Scoped on purpose: the other layouts' geometry was measured clear in H4's
  // own tests, so only Studio's layout may move.
  assert.doesNotMatch(BLOCK, /(?:^|\n)body\[data-hud-safety-visible\] #shell\{/m,
    "the band is not scoped to the Studio shell");
  // The strip must not become a control or move inside a region/card.
  assert.doesNotMatch(BLOCK,
    /#hud-safety\{[^}]*position:static|#hud-safety\{[^}]*pointer-events:auto/,
    "the safety strip was moved into the layout or given a control path");
});

check("hud_bootstrap.js watches the strip's real height and shows/hides the band", () => {
  assert.match(BOOT, /function watchSafetyBand\(\)/,
    "the band watcher is gone from the shell's injected script");
  assert.match(WATCH, /getElementById\("hud-safety"\)/, "the watcher does not read the strip");
  assert.match(WATCH, /document\.body\.setAttribute\("data-hud-safety-visible", ""\)/,
    "the shell never marks the strip visible, so the CSS band cannot apply");
  assert.match(WATCH, /document\.body\.removeAttribute\("data-hud-safety-visible"\)/,
    "the band is never released when the strip hides");
  assert.match(WATCH, /document\.body\.style\.setProperty\("--hud-safety-band", band \+ "px"\)/,
    "the measured band height is not handed to the stylesheet");
  assert.match(WATCH, /document\.body\.style\.removeProperty\("--hud-safety-band"\)/,
    "the measured height is left behind when the strip hides");
  // The height comes from the strip's own box, never a guessed constant.
  assert.match(WATCH, /strip\.getBoundingClientRect\(\)\.bottom \+ 6/,
    "the band is not measured from the strip's own rectangle");
  assert.match(WATCH, /!strip\.hidden && strip\.getClientRects\(\)\.length > 0/,
    "the watcher does not check the strip is really on screen");
  // It follows content changes (a second chip wraps taller) and edit mode.
  assert.match(WATCH, /new MutationObserver\(applyBand\)/);
  assert.match(WATCH, /childList: true, subtree: true, characterData: true/,
    "the band does not follow the strip's own words wrapping taller");
  assert.match(WATCH,
    /attributes: true,\s*\n?\s*attributeFilter: \["data-hud-edit"\]/,
    "the band is not repainted when Edit HUD turns the strip on");
  assert.match(WATCH, /window\.addEventListener\("resize", applyBand\)/,
    "the band does not follow a window resize");
  assert.match(WATCH, /document\.fonts\.ready\.then\(applyBand\)/,
    "the band is not remeasured after the local fonts arrive");
  // It only reads: it must not move, restyle or hide the strip, and it adds
  // no control (H4's promise is that nothing can hide it).
  assert.doesNotMatch(WATCH,
    /appendChild\(strip\)|insertBefore\(strip|strip\.hidden = true/,
    "the band watcher moves or hides the safety strip");
  assert.doesNotMatch(WATCH,
    /createElement\("button"\)|addEventListener\("click"/,
    "the band watcher adds a control where H4 promises none");
  // And it really runs: DOMContentLoaded first, or immediately if already late.
  assert.match(BOOT,
    /if \(document\.readyState === "loading"\) \{\s*\n?\s*document\.addEventListener\("DOMContentLoaded", watchSafetyBand, \{ once: true \}\);\s*\n?\s*\} else \{\s*\n?\s*watchSafetyBand\(\);/,
    "the watcher is never started");
});

/* ── The page did not move (no backend beside-file copies) ───────────────── */

check("the fix lives in the injected desktop files, so jarvis_hud.html stays byte-identical", () => {
  // The page's own split-stage template is still the original seven rows -
  // the new rows exist only in the shell's stylesheet, so no BESIDE-file copy
  // (backend/jarvis_hud.html, jarvis-backend/jarvis_hud.html) is involved.
  assert.match(PAGE,
    /html\[data-hud-shell="split-stage"\] #stage\{\s*display:grid; min-height:0;\s*grid-template-columns:minmax\(0,1fr\) 45%;\s*grid-template-rows:auto auto auto auto auto auto minmax\(0,1fr\);/,
    "the vendored page's own Studio grid changed - the fix belongs in the shell's stylesheet");
  assert.doesNotMatch(PAGE, /Wave 10 \(2026-11-08\)/,
    "the Wave-10 layout fix was written into the vendored page");
  // The shell still serves the stylesheet it now relies on.
  assert.match(BOOT, /link\.href = "hud-link\.css"/,
    "the shell stopped loading the stylesheet the fix lives in");
});

check("the new rules use the HUD's own tokens, no welded colours", () => {
  assert.doesNotMatch(BLOCK, /#[0-9a-fA-F]{3,8}\b/,
    "a hard-coded hex colour reached the Studio layout block");
  assert.doesNotMatch(BLOCK, /rgba?\(\s*\d/,
    "a literal rgb/rgba colour reached the Studio layout block");
  assert.ok(/var\(--[a-z0-9-]+/.test(BLOCK), "the block does not use HUD tokens at all");
});

console.log(`\n${passed} passed, 0 skipped, 0 failed`);
