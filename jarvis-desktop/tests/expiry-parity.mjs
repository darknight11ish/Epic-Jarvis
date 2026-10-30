/**
 * An expired card is the same card on the PC and on the phone (2026-10-28).
 *
 * The owner's ruling - *"the cards on android should match the cards on
 * desktop"* - found this the hard way round: the PHONE had been right since
 * DEF-010 (2026-10-11). It draws no buttons once a card's deadline passes,
 * because a faded control captioned by a line the reader has not connected to
 * it does not read as "you cannot act". The three desktop surfaces (the Jarvis
 * bar, the widget and the HUD page) still drew live Approve and Deny, so the
 * same expired request could be pressed on the PC and not on the phone.
 *
 *     node tests/expiry-parity.mjs
 *
 * What this drives:
 *   1. the ONE rule, `cardHasExpired` in jarvis-link.js, on every shape a row
 *      can arrive in - including a card with NO deadline, which must never
 *      expire (jarvis_gate.APPROVAL_NEVER_EXPIRES);
 *   2. the ONE sentence, `CARD_TIMED_OUT`, and the countdown before it;
 *   3. the HUD page's own copy of the rule (`apprExpired`), lifted out of
 *      jarvis_hud.html and run as it is, against the same inputs;
 *   4. that the bar and the widget actually USE the rule to hide BOTH buttons,
 *      rather than keeping a dead control on the card.
 *
 * No browser. The phone's half is `ExpiredCardShowsNoButtonsTest` (Kotlin).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { CARD_TIMED_OUT, countdownWords } from "../src/card-words.js";
import { cardHasExpired, expiryWords } from "../src/jarvis-link.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const page = (name) => readFileSync(join(SRC, name), "utf8");
const HUD = page("jarvis_hud.html");

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const NOW = 1_800_000_000_000;

check("a card past its deadline is expired; before it, it is not", () => {
  assert.equal(cardHasExpired(NOW - 1, NOW), true);
  assert.equal(cardHasExpired(NOW, NOW), true, "the deadline itself is already too late");
  assert.equal(cardHasExpired(NOW + 1, NOW), false);
  assert.equal(cardHasExpired(NOW + 900_000, NOW), false);
});

check("a card with NO deadline never expires (pairing, key, restore)", () => {
  // jarvis_gate.APPROVAL_NEVER_EXPIRES sends no `expires_in` at all, and
  // `normaliseApproval` leaves `expiresAt` null for it. Null is not "a very
  // long time" - it is the absence of a deadline, so nothing may expire.
  for (const value of [null, undefined, NaN, Infinity]) {
    assert.equal(cardHasExpired(value, NOW), false, String(value));
    assert.equal(expiryWords(value, NOW), "", String(value));
  }
});

check("the countdown is words, and the deadline is the shared sentence", () => {
  assert.equal(expiryWords(NOW + 133_000, NOW), "2m 13s left");
  assert.equal(expiryWords(NOW, NOW), CARD_TIMED_OUT);
  assert.equal(expiryWords(NOW - 60_000, NOW), CARD_TIMED_OUT);
  assert.match(CARD_TIMED_OUT, /^Timed out/);
});

check("the owner's 2026-10-30 timer: plain words, and a warning under a minute", () => {
  // "if there is a card with a limited time of any kind, be sure to put the
  // timer on it" - and in plain words, so the number is read at a glance.
  assert.equal(countdownWords(900), "15m 0s left");
  assert.equal(countdownWords(899), "14m 59s left");
  assert.equal(countdownWords(60), "1m 0s left");
  assert.equal(countdownWords(59), "59s left \u2014 under a minute to decide.");
  assert.equal(countdownWords(1), "1s left \u2014 under a minute to decide.");
  // No timer, never a zero: an absent field, a ceremony card, a request that
  // has already ended, and anything unreadable all draw nothing at all.
  for (const nothing of [null, undefined, 0, -5, NaN, "soon", ""]) {
    assert.equal(countdownWords(nothing), "", String(nothing));
    assert.equal(expiryWords(null, NOW), "", String(nothing));
  }
  // A part-second left reads "1s", never "0s" - 0 is what both apps read as
  // "expired now", and the request is still there.
  assert.equal(expiryWords(NOW + 100, NOW), "1s left \u2014 under a minute to decide.");
});

check("the HUD page words the countdown the same as the module", () => {
  // The page cannot import card-words.js, so it carries its own copy of the
  // same rule; a second answer to one question is how two surfaces start
  // disagreeing (the apprExpired lesson above).
  const m = HUD.match(/function apprClockWords\([^)]*\)\{[\s\S]*?\n\}\n/);
  assert.ok(m, "jarvis_hud.html has no function apprClockWords");
  const apprClockWords = new Function(`${m[0]}; return apprClockWords;`)();
  for (const seconds of [null, undefined, 0, -5, NaN, 1, 42, 59, 60, 61, 899, 900, 3600]) {
    assert.equal(apprClockWords(seconds), countdownWords(seconds), String(seconds));
  }
  // ...and the page paints exactly that line, with the warning class under a
  // minute and NOT above it.
  assert.match(HUD, /line\.textContent = left <= 0 \? APPR_TIMED_OUT : apprClockWords\(left\);/);
  assert.match(HUD, /line\.classList\.toggle\("soon", left > 0 && left < 60\);/);
});

check("the HUD page's own copy of the rule answers the same as the shared one", () => {
  // The page cannot import the module, so it has its own `apprExpired` - and a
  // second answer to one question is how two surfaces start disagreeing.
  const m = HUD.match(/function apprExpired\([^)]*\)\{[\s\S]*?\n\}\n/);
  assert.ok(m, "jarvis_hud.html has no function apprExpired");
  const apprExpired = new Function(`${m[0]}; return apprExpired;`)();
  for (const value of [null, undefined, NaN, NOW - 1, NOW, NOW + 1, NOW + 900_000]) {
    assert.equal(
      apprExpired(value, NOW),
      cardHasExpired(value, NOW),
      `the HUD page and jarvis-link.js disagree about ${String(value)}`,
    );
  }
});

check("the bar hides BOTH buttons once the card is expired", () => {
  const src = page("main.js");
  assert.match(src, /import \{ CARD_KICKER, CARD_TIMED_OUT, cardTitle/);
  assert.match(src, /cardHasExpired/, "main.js no longer consults the one rule");
  // Hide, not merely disable: the phone taught this (DEF-010) - a faded
  // control is still a control, and the sentence above says what happened.
  const block = src.slice(src.indexOf("AN EXPIRED CARD SHOWS NO BUTTONS"),
                          src.indexOf("AN EXPIRED CARD SHOWS NO BUTTONS") + 1_600);
  assert.match(block, /dom\.approvalApprove\.hidden = multiple \|\| expiredCard;/);
  assert.match(block, /dom\.approvalDeny\.hidden = expiredCard;/);
  // ...and the decision itself refuses it too, so hiding is not the only guard.
  assert.match(src, /if \(cardHasExpired\(approval\.expiresAt\)\) \{/);
});

check("the widget hides BOTH buttons once the card is expired", () => {
  const src = page("widget.js");
  assert.match(src, /cardHasExpired/, "widget.js no longer consults the one rule");
  const block = src.slice(src.indexOf("AN EXPIRED CARD SHOWS NO BUTTONS"),
                          src.indexOf("AN EXPIRED CARD SHOWS NO BUTTONS") + 1_200);
  assert.match(block, /dom\.btnApprYes\.hidden = multiple \|\| expiredCard;/);
  assert.match(block, /dom\.btnApprNo\.hidden = expiredCard;/);
  // The click has the same guard: a card can expire between the paint and the
  // press, and a hidden button is not a refusal.
  assert.match(src, /if \(cardHasExpired\(target\.card\.expiresAt\)\) \{/);
});

check("the HUD page hangs its countdown on the one deadline it stamped", () => {
  // apprTick gives up on `el.dataset.deadline`, so a card with no deadline
  // (`data-deadline` absent) gets no countdown and no expiry on the page.
  const src = HUD;
  assert.match(src, /document\.querySelectorAll\("#approvals \.appr\[data-deadline\]"\)/);
  assert.match(src, /el\.dataset\.expired = "1";/);
  assert.match(src, /if\(yes\) yes\.hidden = true;/);
  assert.match(src, /if\(no\) no\.hidden = true;/);
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("\nall expiry-parity checks passed");
