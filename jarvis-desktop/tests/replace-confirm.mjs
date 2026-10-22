/**
 * Two mechanical guards against blind / stacked approvals (review ruling 8.2,
 * 2026-10-20) - the DESKTOP half.
 *
 *     node tests/replace-confirm.mjs
 *
 * The backend half is `backend/test_approval_guards.py`: the PC marks every
 * waiting card with `replaces` (`jarvis_gate.pending()`), and this file holds
 * the two desktop surfaces to that mark:
 *
 *   1. `replace-confirm.js` - `isReplaceCard`, the exact warning words, the
 *      two-press `ReplaceGate`, and the Approve label between the presses.
 *   2. The rows both windows read it from: `normaliseApproval` keeps
 *      `replaces` exactly as the PC sent it.
 *   3. The two places a fast path used to exist - a typed "approve"
 *      (`quickActionable`) and the 320x44 widget, which cannot show the
 *      heading - are refused/redirected for these cards.
 *
 * No browser: this is the decision logic, not the paint. The paint is held by
 * the suites that drive the real pages (uikit.mjs), which CI runs.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  REPLACES_WARNING,
  REPLACES_NOTE,
  REPLACE_HEADINGS,
  replacesHeading,
  replacesNote,
  ReplaceGate,
  approveLabel,
  isReplaceCard,
} from "../src/replace-confirm.js";
import { needsFullCard } from "../src/heavy-approve.js";
import { normaliseApproval, quickActionable } from "../src/jarvis-link.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, "..", "src");
//: The owner-approved set the client floor must hold (2026-10-21), the same
//: names the backend's `_REPLACES_ACTIONS` marks.
const REPLACE_FLOOR = [
  "restore_backup", "register_approval_key", "memory_forget_range",
  "delete_file", "delete_joplin_note", "delete_logseq_page",
  "edit_joplin_note", "edit_logseq_page", "modify_own_code",
  "app_merge_change",
];

const fails = [];

async function check(name, fn) {
  try {
    await fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.stack || e.message}`);
  }
}

/** A waiting row as `/api/pending` sends it, plus what normaliseApproval adds. */
function card(overrides = {}) {
  return normaliseApproval({
    id: "card-1",
    action: "send_email",
    tier: "ask",
    prompt: "Send this email?",
    detail: '{"to": "x@example.com"}',
    risk: { reversible: "yes", reach: "local", swipe_ok: true },
    ...overrides,
  });
}

async function main() {
  await check("the warning is plain WORDS, so it survives without colour", () => {
    assert.equal(REPLACES_WARNING, "REPLACES CURRENT DATA");
    assert.equal(typeof REPLACES_NOTE, "string");
    assert.ok(REPLACES_NOTE.length > 20, "the note must say what the second press does");
    assert.ok(!/^[#\d]/.test(REPLACES_WARNING), "not a colour token or a code");
  });

  await check("RULING 8.1: the PC's own category words are drawn unchanged", () => {
    // The backend sends the category and its honest words on the row; every
    // surface draws exactly those, so the wording cannot drift between them.
    const card = {
      id: "1", action: "edit_joplin_note", replaces: true,
      replacesKind: "overwrites_note",
      replacesHeading: "OVERWRITES EXISTING NOTE",
      replacesNote: "replaces the note's current text; Jarvis keeps no copy of the old version",
    };
    assert.equal(replacesHeading(card), "OVERWRITES EXISTING NOTE");
    assert.match(replacesNote(card), /keeps no copy/);
    assert.ok(!/DELETES/.test(replacesHeading(card)),
      "a note edit claimed a deletion");
  });

  await check("RULING 8.1: an older PC's marked row falls back by category", () => {
    // No words from the PC: the category still chooses the right heading, so a
    // delete card never says OVERWRITES EXISTING NOTE and vice versa.
    assert.equal(replacesHeading({ action: "delete_file", replaces: true,
                                   replacesKind: "deletes_data" }),
                 "DELETES OR REPLACES DATA");
    assert.equal(replacesHeading({ action: "restore_backup", replaces: true,
                                   replacesKind: "replaces_code_or_state" }),
                 "REPLACES LIVE CODE OR STATE");
    assert.equal(replacesHeading({ action: "send_email" }), "");
    assert.equal(replacesNote({ action: "send_email" }), "");
    // A card with the category missing keeps the one generic sentence, never a
    // made-up claim about a kept copy.
    assert.equal(replacesHeading({ action: "delete_file", replaces: true }),
                 REPLACES_WARNING);
    assert.equal(replacesHeading({ action: "delete_file", replaces: true,
                                   replacesKind: "not_a_category" }),
                 REPLACES_WARNING);
  });

  await check("RULING 8.1: the three headings are the ruling's own words", () => {
    assert.deepEqual(REPLACE_HEADINGS, {
      deletes_data: "DELETES OR REPLACES DATA",
      overwrites_note: "OVERWRITES EXISTING NOTE",
      replaces_code_or_state: "REPLACES LIVE CODE OR STATE",
    });
  });

  await check("isReplaceCard: the PC's own `replaces: true` is the answer", () => {
    assert.equal(isReplaceCard({ id: "a", replaces: true }), true);
    assert.equal(isReplaceCard({ id: "a", replaces: false }), false);
  });

  await check("isReplaceCard: the real action names are the older-PC floor", () => {
    // The owner extended the guard on 2026-10-21 ("Extend the two-press guard
    // to them") to every irreversible data-changing action; the client list is
    // the same set the backend marks, used when the PC's field cannot answer.
    for (const action of REPLACE_FLOOR) {
      assert.equal(isReplaceCard({ action }), true, action);
    }
    // The three names the review wrote do not all exist; a guard keyed on them
    // would never fire. Two of them are wrong in the review's own wording.
    assert.equal(isReplaceCard({ action: "backup_restore" }), false);
    assert.equal(isReplaceCard({ action: "forget_range" }), false);
  });

  await check("a SPOOFED/absent field cannot subtract the second press", () => {
    // The PC's field may ADD an action; the client floor may never be used to
    // remove one. An explicit false on a listed action still takes the second
    // press, and so does a row with no field at all.
    for (const action of REPLACE_FLOOR) {
      assert.equal(isReplaceCard({ action, replaces: false }), true,
                   `${action}: an explicit false removed the guard`);
      assert.equal(isReplaceCard({ action, replaces: null }), true, action);
    }
    assert.equal(isReplaceCard({ action: "send_email", replaces: false }), false);
  });

  await check("isReplaceCard: the voice-training clear needs the PC's mark, because its action is shared", () => {
    // change_own_config is the action of every voice-settings card too, so the
    // action name alone MUST NOT flag them - only the PC's `replaces`.
    assert.equal(isReplaceCard({ action: "change_own_config" }), false);
    assert.equal(isReplaceCard({ action: "change_own_config", replaces: true }), true);
  });

  await check("isReplaceCard: an unknown or missing card is ORDINARY, not guessed", () => {
    assert.equal(isReplaceCard(null), false);
    assert.equal(isReplaceCard({}), false);
    assert.equal(isReplaceCard({ action: "send_email" }), false);
  });

  await check("normaliseApproval keeps `replaces` AND the label words as sent", () => {
    assert.equal(card({ replaces: true }).replaces, true);
    assert.equal(card({ replaces: false }).replaces, false);
    assert.equal(card({}).replaces, false, "an older PC's row is ordinary");
  });

  await check("a new card starts unarmed; the first press sends NOTHING and arms it", () => {
    const gate = new ReplaceGate();
    gate.sync({ id: "card-1", action: "restore_backup" });
    assert.equal(gate.armed, false);
    assert.equal(gate.press(), false, "the first press must not send");
    assert.equal(gate.armed, true);
  });

  await check("the second press is the confirming one", () => {
    const gate = new ReplaceGate();
    gate.sync({ id: "card-1", action: "restore_backup" });
    gate.press();
    assert.equal(gate.press(), true, "the second press is what sends");
  });

  await check("a repaint of the SAME card keeps the arm (a queue resync cannot disarm it)", () => {
    const gate = new ReplaceGate();
    gate.sync({ id: "card-1", action: "restore_backup" });
    gate.press();
    const sameAgain = { id: "card-1", action: "restore_backup", replaces: true };
    gate.sync(sameAgain);
    assert.equal(gate.armed, true);
    assert.equal(approveLabel(sameAgain, gate.armed), "Confirm replace");
    assert.equal(gate.press(), true);
  });

  await check("a DIFFERENT card starts unarmed again, whatever the last one was", () => {
    const gate = new ReplaceGate();
    gate.sync({ id: "card-1", action: "restore_backup" });
    gate.press();
    gate.sync({ id: "card-2", action: "restore_backup" });
    assert.equal(gate.armed, false);
    assert.equal(gate.press(), false);
  });

  await check("reset() drops the arm (the card closed before the second press)", () => {
    const gate = new ReplaceGate();
    gate.sync({ id: "card-1", action: "memory_forget_range" });
    gate.press();
    gate.reset();
    assert.equal(gate.armed, false);
    assert.equal(gate.press(), false);
  });

  await check("the button says which press it is: Approve, then Confirm replace", () => {
    const replace = { id: "c", action: "restore_backup" };
    const ordinary = { id: "d", action: "send_email" };
    assert.equal(approveLabel(replace, false), "Approve");
    assert.equal(approveLabel(replace, true), "Confirm replace");
    assert.equal(approveLabel(ordinary, false), "Approve");
    assert.equal(approveLabel(ordinary, true), "Approve", "ordinary cards never change");
  });

  await check("a typed \"approve\" cannot skip the second press (quickActionable)", () => {
    // swipe_ok is true - local and reversible - so without the guard this is
    // exactly the card a fast path would have accepted.
    const restore = card({ action: "restore_backup", replaces: true });
    assert.equal(restore.risk.swipeOk, true);
    assert.equal(quickActionable(restore), false);
    const ordinary = card({ action: "send_email" });
    assert.equal(quickActionable(ordinary), true, "ordinary cards are unchanged");
  });

  await check("the widget cannot decide one on two clamped lines - it redirects to the bar", () => {
    const restore = card({ action: "restore_backup", replaces: true,
                           risk: { reversible: "yes", reach: "local", swipe_ok: true } });
    assert.equal(needsFullCard(restore), true);
    const ordinary = card({ action: "send_email" });
    assert.equal(needsFullCard(ordinary), false);
  });

  await check("the HUD fallback page carries the same words and the same two presses", () => {
    const hud = fs.readFileSync(path.join(SRC, "jarvis_hud.html"), "utf8");
    assert.ok(hud.includes(REPLACES_WARNING), "the HUD heading is missing");
    assert.ok(hud.includes("Confirm replace"), "the HUD has no second press");
    assert.ok(hud.includes("apprReplace("), "the HUD does not read the flag");
    // The published copy of the HUD page is the twin `jarvis-backend/` holds;
    // one edit to one and not the other is how the two surfaces drift apart.
    const twin = fs.readFileSync(
      path.join(SRC, "..", "..", "jarvis-backend", "jarvis_hud.html"), "utf8");
    assert.equal(hud, twin, "jarvis_hud.html and its jarvis-backend/ twin differ");
  });

  await check("the bar has a place for the heading (index.html)", () => {
    const index = fs.readFileSync(path.join(SRC, "index.html"), "utf8");
    assert.ok(index.includes('id="approval-replaces"'), "no heading element");
    assert.ok(index.includes(REPLACES_WARNING), "the bar heading words are missing");
  });

  console.log(fails.length ? `\n${fails.length} failed` : "\nall checks passed");
  if (fails.length) process.exit(1);
}

main();
