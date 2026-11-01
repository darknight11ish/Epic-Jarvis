/**
 * The per-answer caret menu (the owner's request, 2026-10-31: "I don't want
 * the 'Was this answer right? Right/Wrong' option always showing; have a caret
 * menu button next to each Jarvis dialogue ... that includes things like 'was
 * the answer right?', 'read out loud', and the other options").
 *
 *   node tests/hud-answer-menu.mjs
 *
 * No browser needed: the answer menu is built by `src-tauri/src/hud_bootstrap.js`,
 * the script the desktop shell injects into the HUD page, so it is pinned here
 * by source (the real click path is the Playwright case in tests/hud.mjs, which
 * CI runs). The three things this suite exists to stop:
 *
 *   - the always-visible row coming back (it was a row of text under every
 *     answer; the owner asked for it gone);
 *   - the feedback path changing: Right/Wrong must still go through Rust's
 *     `mark_answer` with the same {turnId, mark} body, or the learning signal
 *     is lost;
 *   - an invented option: only real per-answer actions are listed, and
 *     "Read out loud" clicks the page's own `.speak-answer` button.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const TAURI = join(HERE, "..", "src-tauri", "src");
const BOOT = readFileSync(join(TAURI, "hud_bootstrap.js"), "utf8");
const CSS = readFileSync(join(HERE, "..", "src", "hud-link.css"), "utf8");

let passed = 0;
function check(name, fn) {
  fn();
  passed += 1;
  console.log(`ok   ${name}`);
}

/** Section 6 of the bootstrap, between its own header and the fonts section. */
const SECTION = BOOT.slice(
  BOOT.indexOf("6. The answer menu"),
  BOOT.indexOf("3. Fonts, served locally"));

check("the always-visible right/wrong row is gone", () => {
  assert.doesNotMatch(BOOT, /attachMark\b/,
    "hud_bootstrap.js still has the old attachMark row");
  assert.doesNotMatch(BOOT, /className = "jarvis-mark"/,
    "hud_bootstrap.js still creates the old visible mark row");
  assert.doesNotMatch(CSS, /\.jarvis-mark\b/,
    "hud-link.css still carries the old row's styles");
});

check("each Jarvis answer gets a small caret labelled Answer options", () => {
  assert.match(SECTION, /className = "jarvis-answer-tools"/);
  assert.match(SECTION, /className = "jarvis-answer-caret"/);
  assert.match(SECTION, /setAttribute\("aria-label", "Answer options"\)/);
  assert.match(SECTION, /setAttribute\("aria-haspopup", "menu"\)/);
  assert.match(SECTION, /setAttribute\("aria-expanded", "false"\)/);
  assert.match(SECTION, /caret\.textContent = "\\u25BE"/,
    "the caret glyph is not the quiet triangle the owner asked for");
});

check("the menu is a real menu, and it opens only when the caret is pressed", () => {
  assert.match(SECTION, /setAttribute\("role", "menu"\)/);
  assert.match(SECTION, /menu\.hidden = true/,
    "the menu is not hidden until opened - text must not show by itself");
  assert.match(SECTION, /caret\.addEventListener\("click"/);
  assert.match(SECTION, /openAnswerMenu\(tools\)/);
  assert.match(CSS, /\.jarvis-answer-menu\[hidden\]\s*\{\s*display: none !important;/,
    "the stylesheet does not keep a hidden menu hidden");
});

check("the menu lists only real per-answer actions", () => {
  assert.match(SECTION, /"Was this answer right\?"/);
  assert.match(SECTION, /item\("Right"/);
  assert.match(SECTION, /item\("Wrong"/);
  assert.match(SECTION, /item\("Read out loud"/);
  assert.match(SECTION, /item\("Copy answer"/);
  assert.match(SECTION, /menuitemradio/,
    "Right/Wrong are not exposed as radio items to a screen reader");
  assert.ok(!/Open in History|item\("History"/.test(SECTION),
    "the menu invented an Open in History door the HUD does not have");
});

check("Right/Wrong use the SAME shell feedback path as before", () => {
  const calls = SECTION.match(/shellInvoke\("mark_answer"/g) || [];
  assert.equal(calls.length, 1, `expected one mark_answer call path, got ${calls.length}`);
  assert.match(SECTION, /shellInvoke\("mark_answer", \{ turnId: turnId, mark: next \}\)/,
    "the feedback body changed - the recorded signal would change with it");
  assert.match(SECTION, /reply && reply\.available === false/,
    "an older PC without the route no longer removes the menu quietly");
});

check("Read out loud clicks the page's own speaker (no second voice path)", () => {
  assert.match(SECTION, /querySelector\("\.speak-answer"\)/,
    "Read out loud does not look for the page's own per-answer speaker");
  assert.match(SECTION, /speaker\.click\(\)/,
    "Read out loud does not use the page's own speaker path");
  assert.doesNotMatch(SECTION, /speechSynthesis|createElement\("audio"\)|new Audio\(/,
    "a second voice path was added where the page's own speaker already exists");
});

check("Copy answer uses the clipboard and confirms in place", () => {
  assert.match(SECTION, /navigator\.clipboard\.writeText\(answer\)/);
  assert.match(SECTION, /button\.textContent = "Copied\."/);
  assert.match(SECTION, /button\.textContent = "Copy answer"/,
    "Copied. never goes back to Copy answer");
});

check("one menu at a time; Esc closes and returns focus; outside click closes", () => {
  assert.match(BOOT, /var openAnswerTools = null;/);
  assert.match(SECTION, /function closeAnswerMenu\(focusCaret\)/);
  assert.match(SECTION, /if \(openAnswerTools === tools\)/,
    "the caret does not toggle its own menu closed");
  assert.match(SECTION, /closeAnswerMenu\(focusCaret\)/);
  assert.match(SECTION, /key === "Escape"/);
  assert.match(SECTION, /tools\.caret\.focus\(\)/,
    "Esc does not return the keyboard to the caret");
  assert.match(SECTION, /addEventListener\("click", function \(event\)/,
    "there is no outside-click close listener");
});

check("the menu only appears on a FINISHED answer, never on an interrupted one", () => {
  assert.match(SECTION, /st === "done"/);
  assert.match(SECTION, /st === "interrupted"/);
  assert.match(SECTION, /attributeFilter: \["data-state"\]/);
  assert.match(SECTION, /answer = String\(msg\.textContent \|\| ""\)\.replace/,
    "the answer's own words are not captured before the caret is appended");
});

console.log(`\n${passed} passed, 0 skipped, 0 failed`);
