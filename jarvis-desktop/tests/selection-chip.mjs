/**
 * selection-chip.js + the Jarvis bar's selection chip (Pillar 24-B;
 * src-tauri/src/selection.rs, GET /api/selection, backend
 * jarvis_ui_control.read_selection(); JARVIS-API section 141).
 *
 * Two halves, both here because they are one interaction:
 *
 * 1. THE PURE RULES, driven against the REAL 24-A payload shape: a refused or
 *    empty answer shows NO chip; a successful one shows the program's name and
 *    the first ~40 SCRUBBED characters; the attached text is the payload's own
 *    text exactly; a window title is never read from any field; the quick
 *    actions build their prompts locally; a dismissed selection stays
 *    dismissed.
 * 2. THE WIRING, read from the real files (the bar-chrome.mjs shape): the chip
 *    exists in the bar's attachment strip, main.js listens for the Rust event
 *    and puts the exact text in the box, and the command it rides on is
 *    granted to the quickbar and registered in the ACL.
 *
 * No model, no network and no browser: this runs in the frontend job with the
 * other node tests.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import * as C from "../src/selection-chip.js";
import { boxTagAfter, sentProvenance } from "../src/chat-history.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(p, "utf8");
const SRC = join(HERE, "..", "src");
const TAURI = join(HERE, "..", "src-tauri");
const indexHtml = read(join(SRC, "index.html"));
const mainJs = read(join(SRC, "main.js"));
const selectionRs = read(join(TAURI, "src", "selection.rs"));
const surfaces = read(join(TAURI, "permissions", "surfaces.toml"));
const quickbarCap = read(join(TAURI, "capabilities", "quickbar.json"));
const buildRs = read(join(TAURI, "build.rs"));
const libRs = read(join(TAURI, "src", "lib.rs"));

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

// The real backend shape (JARVIS-API section 141; the Python function's dict).
const GOOD = {
  ok: true, refused: false, why: "", text: "the selected words of a paragraph",
  app: "notepad", chars: 32, truncated: false, scrubbed: true,
  words: "Read the highlighted text from notepad.",
};
const SECRET_SCRUBBED = {
  ok: true, refused: false, why: "", text: "before [redacted: private key] after",
  app: "Code", chars: 40, truncated: true, scrubbed: true,
  words: "Read the highlighted text from Code. Only the first part was kept.",
};

/* ── 1. only a real selection draws a chip ─────────────────────────────── */

check("a refused answer draws NO chip (no fake empty chip)", () => {
  for (const why of ["no_selection", "never_look", "private_window", "scrubber",
                     "not_this_pc", "unavailable", "secret"]) {
    assert.deepEqual(C.chipFor({ ok: false, refused: true, why, text: "",
                                 app: "", chars: 0, truncated: false,
                                 scrubbed: false, words: "x" }),
                     { show: false }, why);
  }
  assert.deepEqual(C.chipFor(null), { show: false });
  assert.deepEqual(C.chipFor({ ok: true, text: "   " }), { show: false });
  assert.deepEqual(C.chipFor({ ok: true, text: 7 }), { show: false });
});

check("a real selection draws one chip: the app, then the scrubbed preview", () => {
  const chip = C.chipFor(GOOD);
  assert.equal(chip.show, true);
  assert.equal(chip.app, "notepad");
  assert.equal(chip.text, GOOD.text, "the attached text is the payload's own, exactly");
  assert.ok(chip.label.startsWith("📎 Attach selection from notepad — \""), chip.label);
  assert.ok(chip.label.includes("the selected words of a paragraph"), chip.label);
  assert.equal(chip.scrubbed, true);
  assert.equal(chip.truncated, false);
});

check("the preview is the first ~40 characters, flattened to one line", () => {
  const long = { ...GOOD, text: "one\n\n two   three " + "x".repeat(80) };
  const chip = C.chipFor(long);
  assert.ok(chip.preview.length <= C.PREVIEW_CHARS + 1, chip.preview);
  assert.ok(chip.preview.endsWith("…"), chip.preview);
  assert.ok(!chip.preview.includes("\n"));
});

check("the window TITLE is never read, even if a payload carried one", () => {
  const withTitle = { ...GOOD, title: "Private Bank - InPrivate — statement 9912" };
  const chip = C.chipFor(withTitle);
  assert.ok(!JSON.stringify(chip).includes("Private Bank"), JSON.stringify(chip));
  assert.ok(!chip.label.includes("statement"), chip.label);
  assert.ok(!("title" in chip));
});

check("a scrubbed + truncated selection is respected, not completed", () => {
  const chip = C.chipFor(SECRET_SCRUBBED);
  assert.equal(chip.text, SECRET_SCRUBBED.text);
  assert.equal(chip.scrubbed, true);
  assert.equal(chip.truncated, true);
  assert.ok(!chip.text.includes("BEGIN PRIVATE KEY"));
  assert.ok(C.attachPrompt("", chip.text) === SECRET_SCRUBBED.text);
});

/* ── 2. the quick actions are local prompts; × stays dismissed ─────────── */

check("Attach puts the exact scrubbed text in the box, with any question kept", () => {
  assert.equal(C.attachPrompt("", GOOD.text), GOOD.text);
  assert.equal(C.attachPrompt("what is this?", GOOD.text), `what is this?\n${GOOD.text}`);
  assert.equal(C.attachPrompt("what is this?", 42), "what is this?");
});

check("Explain and Summarize build their prompts locally - no backend call", () => {
  assert.equal(C.explainPrompt("these words"), "Explain this:\nthese words");
  assert.equal(C.summarizePrompt("these words"), "Summarize this:\nthese words");
});

check("× dismisses a selection, and the SAME one never comes back by itself", () => {
  const chip = C.chipFor(GOOD);
  assert.equal(C.dismissed(chip.fingerprint, ""), false);
  assert.equal(C.dismissed(chip.fingerprint, chip.fingerprint), true);
  assert.equal(C.dismissed(C.chipFor({ ...GOOD, text: "other" }).fingerprint,
                          chip.fingerprint), false);
  assert.ok(!chip.fingerprint.includes("\n"));
});

check("the label is bounded (a long preview cannot make a giant chip)", () => {
  const chip = C.chipFor({ ...GOOD, app: "A".repeat(200),
                           text: "long words ".repeat(40) });
  assert.ok(chip.label.length <= C.LABEL_CHARS, chip.label.length);
});

/* ── 2b. S-1: the chip's words are NOT the owner's own typing ─────────── */

check("R3's rule: text inserted from outside stays pasted until the box is emptied", () => {
  const tag = boxTagAfter("typed", "paste");
  assert.equal(tag, "pasted", "inserted text must be pasted, not typed");
  assert.equal(boxTagAfter(tag, "edit", "with a ? around it"), "pasted",
               "typing around it cannot make it the owner's own words");
  assert.equal(sentProvenance(tag, false), "pasted");
  assert.equal(sentProvenance(tag, true), "pasted",
               "a picture does not upgrade pasted text");
  assert.notEqual(sentProvenance(tag, false), "typed");
});

check("the chip attaches as PASTED, never as typed (S-1)", () => {
  const at = mainJs.indexOf("function useSelection(text)");
  assert.notEqual(at, -1, "no useSelection");
  const block = mainJs.slice(at, at + 900);
  assert.match(block, /boxTagAfter\(state\.boxTag, "paste"\)/, block);
  assert.doesNotMatch(block, /boxTagAfter\(state\.boxTag, "typed"\)/,
                      "the chip must not tag selection text as the owner's typing");
});

/* ── 3. the wiring in the real files ──────────────────────────────────── */

check("the bar's attachment strip holds the chip and its four controls", () => {
  for (const id of ["attachment-selection", "selection-attach", "selection-explain",
                    "selection-summarize", "selection-remove"]) {
    assert.match(indexHtml, new RegExp(`id="${id}"`), `no #${id}`);
  }
  // The deferred one is a hook, not a button the owner can press tonight.
  assert.match(indexHtml, /id="selection-remind" hidden/, "#selection-remind must be hidden");
});

check("main.js listens for the Rust read and only shows what it returns", () => {
  assert.match(mainJs, /listen\("selection-read"/);
  assert.match(mainJs, /showSelectionChip\(event && event\.payload\)/);
  assert.match(mainJs, /chipFor\(result\)/);
  assert.match(mainJs, /dismissed\(chip\.fingerprint, state\.selectionDismissed\)/);
});

check("Attach/Explain/Summarize put words in the box - nothing is sent", () => {
  assert.match(mainJs, /useSelection\(state\.selection\.text\)/);
  assert.match(mainJs, /useSelection\(explainPrompt\(state\.selection\.text\)\)/);
  assert.match(mainJs, /useSelection\(summarizePrompt\(state\.selection\.text\)\)/);
  assert.match(mainJs, /dom\.prompt\.value = attachPrompt\(dom\.prompt\.value, text\)/);
  assert.ok(!/selection-read[\s\S]{0,400}invoke\(/.test(mainJs),
            "the selection event must not be answered with a command call");
});

check("× records the dismissal, clears the chip and keeps focus", () => {
  const at = mainJs.indexOf('dom.selectionRemove.addEventListener');
  assert.notEqual(at, -1, "no × handler");
  const body = mainJs.slice(at, at + 420);
  assert.match(body, /state\.selectionDismissed = state\.selection\.fingerprint/);
  assert.match(body, /clearSelectionChip\(\)/);
});

check("the chip is hidden with the attachments when there is no selection", () => {
  assert.match(mainJs, /dom\.selectionChip\.hidden = !state\.selection;/);
  assert.match(mainJs,
    /dom\.attachments\.hidden = !state\.capture && !state\.clipboard && !state\.selection;/);
  assert.match(mainJs, /function clearSelectionChip\(\)/);
  const dismissAt = mainJs.indexOf("async function dismiss()");
  assert.notEqual(dismissAt, -1, "no dismiss()");
  assert.ok(mainJs.slice(dismissAt, dismissAt + 1400).includes("clearSelectionChip();"),
            "dismiss() must clear the chip too");
});

check("S-4 note: only the bar's own page listens for the selection event", () => {
  // The event is emitted with emit_to(bar) - but this Tauri's global listeners
  // receive an emit_to from any window (lib.rs's own comment). The guard is a
  // convention, so pin it: exactly one page registers the event.
  const src = join(HERE, "..", "src");
  const files = readdirSync(src, { recursive: true })
    .filter((f) => typeof f === "string" && f.endsWith(".js"))
    .map((f) => String(f));
  const listeners = files.filter((f) =>
    readFileSync(join(src, f), "utf8").includes('listen("selection-read"'));
  assert.deepEqual(listeners, ["main.js"], listeners);
});

check("the read happens before the bar takes focus, and is PC-read only", () => {
  // Rust: the bar-open path reads first; the page is handed the event.
  assert.match(selectionRs, /pub\(crate\) const SELECTION_PATH: &str = "\/api\/selection";/);
  assert.match(selectionRs, /pub\(crate\) fn selection_answer/);
  assert.match(read(join(TAURI, "src", "windows.rs")),
    /let got = crate::selection::read_selection_quiet\(&target\)\.await;/);
  assert.match(libRs, /pub const SELECTION_READ: &str = "selection-read";/);
  assert.match(libRs, /selection::read_selection,/);
});

check("the command is granted to the quickbar and registered in the ACL", () => {
  assert.match(buildRs, /"read_selection",/);
  assert.match(surfaces, /"allow-read-selection",/);
  assert.match(quickbarCap, /"quickbar-surface"/);
  const quickbar = surfaces.slice(surfaces.indexOf('identifier = "quickbar-surface"'));
  assert.ok(quickbar.slice(0, 6000).includes('"allow-read-selection"'),
            "allow-read-selection is not in the quickbar-surface set");
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nall selection-chip checks passed");
