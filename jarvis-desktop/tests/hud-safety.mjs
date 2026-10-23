/**
 * hud-safety.mjs — H4's pure half, and the pins that keep the safety rail
 * un-hideable. Node only; the page-level behaviour is in tests/hud.mjs.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  LOCK_WORDS,
  HIDDEN_WORDS,
  STALE_WORDS,
  OFFLINE_LEAD,
  TAINT_LEAD,
  TAINT_TAIL,
  FIXED_LABEL,
  LOCK_BEAT_MS,
  raisedOf,
  lockWords,
  linkWords,
  taintWords,
  safetyChips,
  approveHeld,
  applyApprovalControls,
} from "../src/hud-safety.js";
import {
  CARD_REGISTRY,
  DEFAULT_PRESET_ID,
  LAYOUT_VERSION,
  normalizeLayout,
  presetLayout,
} from "../src/hud-layout.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const DESK = join(HERE, "..");
const PAGE = readFileSync(join(SRC, "jarvis_hud.html"), "utf8");
const SAFETY_JS = readFileSync(join(SRC, "hud-safety.js"), "utf8");
// H4-2: this test reads ONLY tracked files. The design spec lives in a
// scratch folder outside the checkout, so CI does not have it - never read it.

let fails = 0;
function check(name, fn) {
  try {
    fn();
  } catch (err) {
    fails += 1;
    console.error(`FAIL  ${name}\n      ${err.message}`);
  }
}

check("the rail's words are the approved ones, and linked is silent", () => {
  assert.equal(lockWords({ appLock: true, privateAnswers: false }), LOCK_WORDS);
  assert.equal(lockWords({ appLock: false, privateAnswers: true }), HIDDEN_WORDS);
  assert.equal(lockWords({ appLock: false, privateAnswers: false }), "");
  assert.equal(lockWords(null), "");
  assert.equal(linkWords({ up: true, short: "linked", tone: "ok", words: "linked" }), null,
    "the rail duplicated the one status row when linked");
  assert.equal(linkWords({ up: null }), null);
  const stale = linkWords({ up: true, short: "reconnecting", tone: "warn", words: "stale — reconnecting" });
  assert.equal(stale.tone, "warn");
  assert.ok(stale.words.includes("Deny still works"), stale.words);
  assert.ok(stale.words === STALE_WORDS);
  const offline = linkWords({ up: false, short: "no link", tone: "bad", words: "offline · Jarvis is not answering." });
  assert.equal(offline.tone, "bad");
  assert.ok(offline.words.startsWith(OFFLINE_LEAD), offline.words);
  assert.ok(offline.words.includes("Jarvis is not answering."), offline.words);
});

check("the rush banner is queue-scoped and never overclaims the persistent latch", () => {
  const object = taintWords([{ id: 1, raised: { quote: "act now or lose it", source: "an email" } }]);
  assert.ok(object.words.includes("on the card that is waiting"), object.words);
  assert.ok(object.words.includes(TAINT_LEAD) && object.words.includes(TAINT_TAIL), object.words);
  assert.ok(object.words.includes("act now or lose it") && object.words.includes("an email"), object.words);
  assert.ok(!/latch|armed|current/i.test(object.words.replace(TAINT_TAIL, "")),
    `the banner claims more than a waiting card: ${object.words}`);
  // Every shape apprRaised handles.
  assert.deepEqual(raisedOf(JSON.stringify({ quote: "q" })), { quote: "q" });
  assert.deepEqual(raisedOf(true), {});
  assert.deepEqual(raisedOf("true"), {});
  assert.equal(raisedOf(null), null);
  assert.ok(taintWords([{ id: 1, raised: "true" }]).words.startsWith(TAINT_LEAD));
  assert.equal(taintWords([{ id: 1 }]), null);
  assert.equal(taintWords([]), null);
  // External text is shown, never run: the words stay plain text.
  const hostile = taintWords([{ raised: { quote: "<script>alert(1)</script>", source: "a web page" } }]);
  assert.ok(hostile.words.includes("<script>alert(1)</script>"), "the quote must be shown as words");
  assert.ok(!SAFETY_JS.includes("innerHTML"), "hud-safety.js must not use innerHTML");
});

check("safetyChips: lock, taint, link, in markup order; linked-only is empty", () => {
  assert.deepEqual(safetyChips({}), []);
  const chips = safetyChips({
    lock: { appLock: true },
    rows: [{ raised: { quote: "q", source: "s" } }],
    link: { up: true, short: "reconnecting", tone: "warn" },
  });
  assert.deepEqual(chips.map((c) => c.chip), ["lock", "taint", "link"]);
  assert.equal(chips[0].words, LOCK_WORDS);
  assert.equal(chips[1].role, "alert", "the rush evidence is the one prominent role");
  assert.equal(chips[2].words, STALE_WORDS);
});

check("Approve waits while catching up or before the shell has said; Deny is never held", () => {
  assert.equal(approveHeld({ up: false }), true);
  assert.equal(approveHeld({ up: true, short: "reconnecting", tone: "warn" }), true);
  assert.equal(approveHeld({ up: true, short: "linked", tone: "ok" }), false);
  // H4-LOW: before the shell's first push, an unknown link must not offer Approve.
  assert.equal(approveHeld(null), true);
  assert.equal(approveHeld({ up: null }), true);
  const yes = { disabled: false, title: "Confirm replace", dataset: {}, attrs: {},
    setAttribute(k, v) { this.attrs[k] = v; if (k === "aria-describedby") this["aria-describedby"] = v; },
    getAttribute(k) { return this.attrs[k] ?? null; },
    removeAttribute(k) { delete this.attrs[k]; if (k === "aria-describedby") delete this["aria-describedby"]; } };
  const no = { disabled: true };
  const card = { querySelector: (sel) => (sel === ".yes" ? yes : sel === ".no" ? no : null) };
  let out = applyApprovalControls(card, { held: true, descId: "hud-safety-link", words: STALE_WORDS });
  assert.deepEqual(out, { approveDisabled: true, denyEnabled: true });
  assert.equal(yes.title, STALE_WORDS);
  assert.equal(yes["aria-describedby"], "hud-safety-link");
  out = applyApprovalControls(card, { held: false });
  assert.deepEqual(out, { approveDisabled: false, denyEnabled: true });
  assert.equal(yes["aria-describedby"], undefined);
  // H4-LOW: the card's own words/title survive the rail's stale note.
  assert.equal(yes.title, "Confirm replace");
  // A card cut off before it reached the page stays unapprovable.
  const cut = { disabled: true, title: "", dataset: { cutoff: "1" }, setAttribute() {}, removeAttribute() {} };
  const cutCard = { querySelector: (sel) => (sel === ".yes" ? cut : { disabled: false }) };
  out = applyApprovalControls(cutCard, { held: false });
  assert.equal(out.approveDisabled, true, "a cut-off card became approvable");
});

check("the rail is outside the shell, the cards and every editable region", () => {
  const start = PAGE.indexOf('<div id="hud-safety"');
  const shell = PAGE.indexOf('<div id="shell">');
  assert.ok(start > 0, "the page has no #hud-safety markup");
  assert.ok(start < shell, "#hud-safety is inside the shell");
  const block = PAGE.slice(start, PAGE.indexOf("</div>", start) + 6);
  for (const bad of ["data-hud-card", "data-hud-region", "data-hud-id", "class=\"appr\"", "hud-card"]) {
    assert.ok(!block.includes(bad), `the rail carries ${bad}`);
  }
  assert.ok(!CARD_REGISTRY.some((card) => /safety|app_lock|taint/.test(card.id)),
    "a safety element entered CARD_REGISTRY (a layout could then move/hide it)");
  assert.ok(PAGE.includes('role="region" aria-label="Safety and connection"'));
  assert.ok(PAGE.includes(FIXED_LABEL), "the edit-mode 'always visible' line is missing");
  assert.ok(/body\[data-hud-edit="on"\] #hud-safety > span#hud-safety-fixed/.test(PAGE),
    "the 'always visible' line is not shown in edit mode");
});

check("no preset, import or hand-edited document can express the rail", () => {
  const hostile = presetLayout(DEFAULT_PRESET_ID);
  assert.equal(hostile.version, LAYOUT_VERSION);
  hostile.cards.push(
    { id: "safety", region: "header", order: 0, col_span: 12, row_span: 1, visible: false },
    { id: "app_lock", region: "header", order: 1, col_span: 12, row_span: 1, visible: false },
    { id: "taint", region: "header", order: 2, col_span: 12, row_span: 1, visible: false },
  );
  hostile.hidden = ["safety", "app_lock", "taint"];
  const normalized = normalizeLayout(hostile);
  const ids = normalized.cards.map((card) => card.id);
  for (const ghost of ["safety", "app_lock", "taint"]) {
    assert.ok(!ids.includes(ghost), `a hostile import created/hid ${ghost}`);
  }
  for (const protectedId of ["approvals", "emergency_stop", "voice_controls", "bar_launcher"]) {
    const card = normalized.cards.find((c) => c.id === protectedId);
    assert.ok(card && card.visible === true, `${protectedId} stopped being visible after a hostile import`);
  }
});

check("no new grant, no file/blob upload, inline-script count still 4", () => {
  const caps = JSON.parse(readFileSync(join(DESK, "src-tauri", "capabilities", "hud.json"), "utf8"));
  const perms = caps.permissions;
  assert.ok(perms.includes("hud-link"), "get_lock_flags lost its hud-link grant");
  assert.equal(new Set(perms).size, perms.length, "a duplicate permission appeared");
  const csp = readFileSync(join(HERE, "csp-inline.mjs"), "utf8");
  assert.ok(csp.includes('"jarvis_hud.html": 4'), "the inline-script count pin changed");
  // Scoped to H4's own additions: the page already has other features with
  // their own DOM; the safety rail and its module must add no upload path.
  const safetyStart = PAGE.indexOf('<div id="hud-safety"');
  const safetyBlock = PAGE.slice(safetyStart, PAGE.indexOf("</div>", safetyStart) + 6);
  assert.ok(!/type="file"|createObjectURL|blob:/.test(safetyBlock + SAFETY_JS),
    "the safety rail has a file/blob upload path");
  assert.ok(LOCK_BEAT_MS >= 5000, "the lock poll beat is too hot");
});

check("the rail is click-through, top-centre, and its tracked docs say the same", () => {
  // H4-1: v1 has no controls on the strip, so nothing under it may be blocked.
  assert.match(PAGE, /#hud-safety > span\{[^}]*pointer-events:none/);
  assert.match(PAGE, /#hud-safety\{[^}]*top:2px; left:50%; transform:translateX\(-50%\)/);
  // H4-3: the edit-mode label is hidden normally and shown while editing, with
  // enough specificity to beat the chip rule; healthy edit mode keeps the strip.
  assert.match(PAGE, /#hud-safety > span#hud-safety-fixed\{display:none/);
  assert.match(PAGE, /body\[data-hud-edit="on"\] #hud-safety > span#hud-safety-fixed\{display:block/);
  assert.match(PAGE, /body\[data-hud-edit="on"\] #hud-safety\{display:flex/);
  // H4-4: a first paint before the module mounts is stashed and repainted.
  assert.match(PAGE, /window\.__hudSafetyPending = list/);
  assert.match(PAGE, /if \(typeof apprPoll === "function"\) apprPoll\(\)/);
  assert.ok(SAFETY_JS.includes("window.__hudSafetyPending"), "the rail does not seed from the first paint");
  // H4-LOW: no timer outlives the page, and the strip repaints on edit-mode.
  assert.ok(SAFETY_JS.includes('window.addEventListener("pagehide", stop'), "no pagehide teardown");
  assert.ok(SAFETY_JS.includes("MutationObserver"), "edit-mode changes do not repaint the strip");
  // The honest limits live in tracked text (the module and the docs), never in a
  // scratch file the CI checkout does not have.
  for (const line of ["QUEUE-SCOPED", "latch", "no in-page locked overlay", "Deny stays enabled"]) {
    assert.ok(SAFETY_JS.includes(line), `hud-safety.js does not state ${line}`);
  }
  const arch = readFileSync(join(DESK, "..", "docs", "ARCHITECTURE.md"), "utf8");
  assert.ok(arch.includes("The HUD's safety rail is fixed and outside every editable region"),
    "ARCHITECTURE does not carry the tracked H4 note");
  // #742's real fixed Stop everything control is one of the protected controls the
  // geometry test keeps clear of the rail; the rail itself still has no controls,
  // and the stop button lives outside it (never inside the strip).
  const stopMarkup = 'id="hud-stop"';
  assert.ok(PAGE.includes(stopMarkup), "the page has no real Stop everything control");
  const railBlock = PAGE.slice(PAGE.indexOf('<div id="hud-safety"'),
    PAGE.indexOf("</div>", PAGE.indexOf('<div id="hud-safety"')) + 6);
  assert.ok(!railBlock.includes("hud-stop"), "the Stop control was put inside the safety rail");
  assert.ok(arch.includes("fixed Stop everything control"),
    "ARCHITECTURE does not name the real fixed Stop control");
  assert.ok(/hud-stop/.test(readFileSync(join(HERE, "hud.mjs"), "utf8")),
    "the H4 geometry list does not include the real Stop control");
  assert.ok(!/readFileSync\([^)]*DESIGN-H3-H4/.test(readFileSync(join(HERE, "hud-safety.mjs"), "utf8")),
    "the test reads the untracked design spec");
});

if (fails) {
  console.error(`\n${fails} failed`);
  process.exit(1);
}
console.log("ok: H4 safety rail — words, queue-scoped evidence, un-hideable pins");
