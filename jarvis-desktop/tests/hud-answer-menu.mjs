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
const COMMANDS = readFileSync(join(TAURI, "commands.rs"), "utf8");
const CSS = readFileSync(join(HERE, "..", "src", "hud-link.css"), "utf8");
const BROWSER_TEST = readFileSync(join(HERE, "hud.mjs"), "utf8");

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

check("Right/Wrong still use the SAME shell feedback path", () => {
  const calls = SECTION.match(/shellInvoke\("mark_answer"/g) || [];
  assert.equal(calls.length, 1, `expected one mark_answer call path, got ${calls.length}`);
  // Wave 10: ONE call site, and the old body is still built exactly as before
  // when there are no sheet details - Right, take-back and "Just mark it
  // wrong" are byte-for-byte the request every earlier client sent.
  assert.match(SECTION, /var args = \{ turnId: turnId, mark: next \};/,
    "the old {turnId, mark} body is not built the way it always was");
  assert.match(SECTION, /shellInvoke\("mark_answer", args\)/);
  assert.match(SECTION, /reply && reply\.available === false/,
    "an older PC without the route no longer removes the menu quietly");
});

check("Read out loud is ALWAYS shown for a finished answer (owner, 2026-11-07)", () => {
  // Before this, the item was hidden unless the page's per-answer speaker
  // existed. The owner asked for it to be present on every answer, and able to
  // read THAT answer - so the page grew its own hook (below) and the item's
  // visibility depends only on the answer existing.
  assert.match(SECTION, /if \(readItem\) readItem\.hidden = !answer;/,
    "Read out loud is still conditional on the per-answer speaker existing");
  assert.doesNotMatch(SECTION, /readItem\.hidden = !\(speaker && answer\)/);
  assert.match(SECTION, /item\("Read out loud", function \(button\) \{/,
    "Read out loud does not take the item button, so it cannot show a receipt");
});

check("Read out loud uses the page's own speaker, else the page's own hook", () => {
  assert.match(SECTION, /querySelector\("\.speak-answer"\)/,
    "Read out loud does not look for the page's own per-answer speaker");
  assert.match(SECTION, /speaker\.click\(\)/,
    "Read out loud does not use the page's own speaker path");
  assert.match(SECTION, /window\.__jarvisReadAnswer/,
    "there is no fallback for an answer drawn without a speaker");
  assert.doesNotMatch(SECTION, /speechSynthesis|createElement\("audio"\)|new Audio\(/,
    "a second voice path was added where the page's own speaker already exists");
});

check("the page's __jarvisReadAnswer hook asks the privacy rule for THAT answer", () => {
  const HTML = readFileSync(join(HERE, "..", "src", "jarvis_hud.html"), "utf8");
  assert.match(HTML, /window\.__jarvisReadAnswer = function\(bubble\)/,
    "the HUD page provides no per-answer read hook");
  assert.match(HTML, /answerMayBeSpoken\(said\.route\)/,
    "the hook does not ask private-speech.js for this answer's own route");
  assert.match(HTML, /voice\.speak\(said\.text\)/,
    "an allowed answer is not read through the page's one voice path");
  assert.match(HTML, /ok: false, why:[\s\S]{0,200}It'?s on your screen/,
    "a refused answer does not come back with the rule's own line as the receipt");
});

check("Copy answer confirms in place, and Right/Wrong do too", () => {
  assert.match(SECTION, /navigator\.clipboard\.writeText\(answer\)/);
  assert.match(SECTION, /receipt\(button, "Copied\."\)/);
  assert.match(SECTION, /function receipt\(button, text\)/);
  assert.match(SECTION, /button\.dataset\.receiptLabel/,
    "the receipt never puts the item's own label back");
  assert.match(SECTION, /receipt\(next === "none" \? wrong : right,\s*next === "none" \? "Cleared\." : "Marked\."\);/,
    "Right/Wrong have no visible receipt after a mark is recorded");
  assert.match(SECTION, /receipt\(wrong, "Marked\."\)/,
    "a recorded Wrong mark has no visible receipt");
  assert.match(SECTION, /"Cleared\."/);
  assert.match(SECTION, /"Marked\."/);
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

check("the menu's first line is WHEN the answer was produced, read-only", () => {
  assert.match(SECTION, /function answerWhenWords\(unixSeconds\)/,
    "there is no timestamp formatter");
  assert.match(SECTION, /weekday: "short", day: "2-digit", month: "short",\s*hour: "2-digit", minute: "2-digit"/,
    "the timestamp is not the plain date AND time the owner asked for");
  assert.match(SECTION, /toLocaleString/,
    "the timestamp is not shown in the owner's local time");
  assert.match(SECTION, /menu\.insertBefore\(stamp, menu\.firstChild\)/,
    "the timestamp is not the first line of the menu");
  assert.match(SECTION, /stamp\.setAttribute\("role", "presentation"\)/,
    "the timestamp is not exposed as a read-only line");
  assert.ok(!/items\.push\(stamp\)/.test(SECTION),
    "the timestamp was put in the arrow-key/action list");
  assert.doesNotMatch(SECTION, /item\("Sat|item\(answerWhenWords/,
    "the timestamp was built as an action item");
});

check("the timestamp uses the turn's real time, not the time the menu opened", () => {
  assert.match(SECTION, /msg\.dataset \? msg\.dataset\.at : ""/,
    "the answer bubble's own PC timestamp is not read");
  assert.match(SECTION, /if \(!when\) when = Number\(answerAt\) \|\| 0;/,
    "there is no fallback to the answer's own arrival time");
  assert.match(SECTION, /awaitingAt = Math\.round\(Date\.now\(\) \/ 1000\);/,
    "the arrival time is not captured when the turn is asked");
  assert.doesNotMatch(SECTION, /Date\.now\(\) \/ 1000\);\s*var stamp|answerWhenWords\(Math\.round\(Date\.now\(\)/,
    "the timestamp is computed when the menu opens instead of from the turn");
});



/* ── Wave 10 (2026-11-08): the wrong-answer sheet in the same menu ────────── */

check("Wrong opens the reason sheet INSIDE the one menu, not a second overlay", () => {
  assert.match(SECTION, /function onWrongPicked\(\)/,
    "there is no single Wrong handler");
  assert.match(SECTION, /var wrong = item\("Wrong", onWrongPicked, "menuitemradio"\)/,
    "the Wrong item does not open the sheet");
  assert.match(SECTION, /if \(current === "wrong"\) \{\s*send\("wrong"\);/,
    "taking an existing wrong mark back no longer works as before");
  assert.match(SECTION, /function openWrongSheet\(\)/);
  assert.match(SECTION, /sheet\.className = "jarvis-answer-sheet"/);
  assert.match(SECTION, /menu\.appendChild\(sheet\)/,
    "the sheet is not inside the one answer menu");
  assert.match(SECTION, /sheet\.setAttribute\("role", "group"\)/);
  assert.match(SECTION, /menu\.classList\.add\("is-sheet"\)/);
  // No second overlay system: no dialog/top-layer/portal and no second menu.
  assert.doesNotMatch(SECTION, /showModal|role="dialog"|createPortal|showPopover/,
    "a second overlay was added where the existing menu mechanics were asked for");
});

check("the sheet names the owner's five reasons, and the correction box is bounded", () => {
  const reasons = [
    ["wrong_fact", "wrong fact"],
    ["outdated", "outdated"],
    ["misunderstood", "misunderstood"],
    ["too_long", "too long"],
    ["too_sensitive", "too sensitive"],
  ];
  for (const [id, label] of reasons) {
    assert.ok(SECTION.includes(`id: "${id}", label: "${label}"`),
      `the sheet is missing the "${label}" reason (${id})`);
  }
  assert.match(SECTION, /var CORRECTION_MAX = 500;/, "the 500-character bound is gone");
  assert.match(SECTION, /box\.maxLength = CORRECTION_MAX/,
    "the box does not enforce the 500-character bound");
  assert.match(SECTION, /What should I have said\? \(optional\)/,
    "the correction box has no plain label");
  assert.match(SECTION, /jarvis-answer-counter/, "there is no live character counter");
  assert.match(SECTION, /aria-pressed/, "the reason chips do not expose their state");
});

check("nothing is sent until Submit; Cancel and dismissal send nothing", () => {
  // A chip only records a local choice.
  const chip = SECTION.slice(SECTION.indexOf("chip.addEventListener"),
                            SECTION.indexOf("sheet.appendChild(reasons)"));
  assert.doesNotMatch(chip, /send\(|shellInvoke/, "a reason chip sends something");
  // Typing only moves the counter.
  const typing = SECTION.slice(SECTION.indexOf('box.addEventListener("input"'),
                              SECTION.indexOf("var actions"));
  assert.doesNotMatch(typing, /send\(|shellInvoke/, "typing in the correction box sends");
  // Cancel goes back; it never sends.
  const cancel = SECTION.slice(SECTION.indexOf('cancel.addEventListener("click"'),
                               SECTION.indexOf("sheetItems ="));
  assert.doesNotMatch(cancel, /send\(|shellInvoke/, "Cancel sends something");
  // Submit is the ONE sheet door that sends, and it sends the new fields.
  assert.match(SECTION, /send\("wrong", \{ reason: reason, correction: correction \}\)/,
    "Submit does not send the reason and correction through the same path");
  // "Just mark it wrong" keeps the old body (send with no details).
  assert.match(SECTION, /just\.textContent = "Just mark it wrong"/);
  assert.match(SECTION, /send\("wrong"\)\.then\(function \(reply\) \{/,
    "the 'Just mark it wrong' path does not send the old {turnId, mark} body");
  // Esc/outside click use the menu's own close, which resets the sheet first.
  assert.match(SECTION, /if \(tools\.closeSheet\) tools\.closeSheet\(\);/,
    "closing the menu does not reset an open sheet");
});

check("the PC's said sentence is the receipt, and card_raised approves nothing", () => {
  assert.match(SECTION, /reply\.said/, "the PC's returned receipt sentence is ignored");
  assert.match(SECTION, /jarvis-answer-said/, "the receipt has no place on screen");
  assert.match(SECTION, /"Marked wrong\."/,
    "an older PC with no said sentence has no honest fallback");
  // The flag may be NAMED in a comment (the contract says to tolerate it), but
  // no line of CODE may read it or approve anything: the reply's receipt
  // sentence is the only thing the sheet acts on.
  assert.doesNotMatch(SECTION, /(?:reply|out|answer)\s*\.\s*card_raised|\bcard_raised\b\s*[?:&|]/,
    "the page acts on card_raised - it must only tolerate the key");
  assert.doesNotMatch(SECTION, /decide_approval|approve[A-Za-z]*\s*\(|shellInvoke\("approve/,
    "the sheet can approve something - it must never approve anything");
});

check("Rust builds the old body or the v2 body in ONE tested place", () => {
  assert.match(COMMANDS, /pub\(crate\) fn mark_answer_body\(/,
    "there is no single body builder to test");
  assert.match(COMMANDS, /pub\(crate\) const MARK_REASONS: \[&str; 5\] = \[/,
    "the five reasons are not one Rust vocabulary");
  for (const reason of ["wrong_fact", "outdated", "misunderstood", "too_long", "too_sensitive"]) {
    assert.ok(COMMANDS.includes(`"${reason}"`), `Rust does not know the ${reason} reason`);
  }
  assert.match(COMMANDS, /pub\(crate\) const MARK_CORRECTION_MAX: usize = 500;/,
    "Rust does not bound the correction at 500 characters");
  assert.match(COMMANDS, /reason: Option<String>,\s*correction: Option<String>,/,
    "the command does not accept the optional Wave-10 fields");
  // The old keys are still the first two, and each new field only when sent.
  assert.match(COMMANDS, /body\.insert\("turn_id"\.into\(\)[\s\S]{0,200}body\.insert\("mark"\.into\(\)/,
    "the old body is no longer built first");
  assert.match(COMMANDS, /if let Some\(reason\) = reason \{/,
    "reason is not omitted when the caller did not send it");
  assert.match(COMMANDS, /if let Some\(correction\) = correction \{/,
    "correction is not omitted when the caller did not send it");
  // The tested half really exists.
  assert.match(COMMANDS, /fn a_plain_mark_is_exactly_the_old_body\(\)/);
  assert.match(COMMANDS, /fn the_sheet_body_carries_the_reason_and_correction\(\)/);
  assert.match(COMMANDS, /fn only_the_five_reasons_are_accepted\(\)/);
});

check("the sheet's styles use the HUD's own tokens, and the real page drives it", () => {
  for (const cls of [".jarvis-answer-menu.is-sheet", ".jarvis-answer-reason",
                     ".jarvis-answer-correction", ".jarvis-answer-said"]) {
    assert.ok(CSS.includes(cls), `hud-link.css has no ${cls}`);
  }
  const sheetCss = CSS.slice(CSS.indexOf(".jarvis-answer-menu.is-sheet"));
  assert.doesNotMatch(sheetCss, /#[0-9a-fA-F]{3,8}\b|rgba?\(\s*\d/,
    "a hard-coded colour reached the sheet instead of a HUD token");
  // The Playwright half (CI) is updated with it, so the real click path is not
  // left proving the old immediate-Wrong behaviour.
  assert.match(BROWSER_TEST, /Just mark it wrong/, "the browser suite has no sheet path");
  assert.match(BROWSER_TEST, /reason: "wrong_fact"/,
    "the browser suite never submits a reason and correction");
  assert.match(BROWSER_TEST, /said:/, "the browser suite's mark stub returns no receipt sentence");
});

console.log(`\n${passed} passed, 0 skipped, 0 failed`);
