/**
 * The widget can no longer approve the wrong card
 * (docs/DEEP-AUDITS-2026-10-05.md §5, finding 1; docs/AUDIT-PASS-2026-10-05.md).
 *
 * The widget has one pair of Approve and Deny buttons and one card whose words
 * are replaced whenever the queue changes. A card decided elsewhere - the
 * phone, the Jarvis bar - left the queue, the next one slid into slot 0, and a
 * click aimed at the card the owner was reading decided the card that replaced
 * it: one they had never seen. `syncApprovalButtons` could not catch it (it
 * disables the buttons for a stale stream or a decision in flight), and nothing
 * looked the id up in the live queue the way `main.js`'s `openDigestApproval`
 * does.
 *
 * What must hold, and what this file checks:
 * - the id a decision is sent for is the card that was ON SCREEN when the
 *   buttons were pressed, never whichever card has repainted since;
 * - a pressed card that has left the queue is REFUSED, with one visible
 *   sentence, and never silently swapped for the card that replaced it;
 * - a pressed card that is still waiting is still decided, even when a
 *   different card is on screen by the time the click lands;
 * - Deny is refused the same way (the same wrong-card decision, opposite sign)
 *   and is still never disabled by a swap, and Approve still redirects to the
 *   Jarvis bar for a locked, email or heavy card;
 * - the row the decision is for is the queue's OWN row, so `risk` and `notice`
 *   are the ones every other surface reads;
 * - CONTROL: with nothing swapped, a click still decides the card on screen.
 *
 * Needs no browser: `widget.js` is a page script with no exports, so the rule
 * itself is imported from `src/approval-target.js` (where the widget gets it
 * from too) and the wiring is asserted against the widget's own source, the way
 * tests/inbox-tidy.mjs asserts the strip's.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { ApprovalTarget, GONE_DETAIL, GONE_LINE } from "../src/approval-target.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** One queue row, with the fields a decision reads. */
const row = (id, extra = {}) => ({ id, action: "write_note", risk: { reversible: "yes" }, ...extra });

/** The body of a top-level function in a page script, by its own opening line. */
function fnBody(src, opening) {
  const start = src.indexOf(opening);
  assert.ok(start > 0, `no ${opening} in that file`);
  const rest = src.slice(start);
  const end = rest.indexOf("\n}\n");
  assert.ok(end > 0, `${opening} has no end`);
  return rest.slice(0, end);
}

/** Comments out of the way, so "this code must not read state.approval" cannot
 *  be satisfied or broken by a comment that mentions it. */
const uncommented = (text) => text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");

/* ── the rule ─────────────────────────────────────────────────────────────── */

await check("CONTROL: with nothing swapped, the card on screen is decided", async () => {
  // Everything below is a refusal. Without this one, a build that can decide
  // nothing at all would pass the lot.
  const cards = new ApprovalTarget();
  cards.paint("a");
  const queue = { count: 1, items: [row("a")] };
  const target = cards.resolve(queue);
  assert.equal(target.gone, false);
  assert.equal(target.id, "a");
  assert.equal(target.card, queue.items[0]);
});

await check("a card answered elsewhere between the press and the click is refused", async () => {
  // The reported bug, exactly: the owner pressed Approve on `a`, the phone
  // answered `a`, the queue re-read put `b` in slot 0, and the click landed.
  const cards = new ApprovalTarget();
  cards.paint("a");
  cards.press();
  cards.paint("b");                       // the repaint under the finger
  const target = cards.resolve({ count: 1, items: [row("b")] });
  assert.equal(target.id, "a", "the decision moved to the card that slid into slot 0");
  assert.equal(target.card, null, "a card that is no longer waiting was decided");
  assert.equal(target.gone, true, "the refusal has nothing to say");
});

await check("a repaint under the finger never moves the decision to the new card", async () => {
  // `a` is still waiting, just not first. The owner pressed `a`: that is the
  // card the decision belongs to - not `b`, which they have not read.
  const cards = new ApprovalTarget();
  cards.paint("a");
  cards.press();
  cards.paint("b");
  const queue = { count: 2, items: [row("b"), row("a")] };
  const target = cards.resolve(queue);
  assert.equal(target.id, "a");
  assert.equal(target.card, queue.items[1]);
});

await check("the refused click does not pin the next one", async () => {
  // The pin is one press deep. A refused decision that left it behind would
  // refuse (or mis-answer) the next, unrelated click.
  const cards = new ApprovalTarget();
  cards.paint("a");
  cards.press();
  cards.paint("b");
  assert.equal(cards.resolve({ items: [row("b")] }).card, null);
  cards.forgetPress();                    // what decide() does with every press
  const next = cards.resolve({ items: [row("b")] });
  assert.equal(next.card.id, "b", "the next click could not decide the card on screen");
});

await check("a press that is cancelled, or a card that closes, is forgotten", async () => {
  const cards = new ApprovalTarget();
  cards.paint("a");
  cards.press();
  cards.forgetPress();                    // a dragged-away or cancelled pointer
  assert.equal(cards.resolve({ items: [row("b")] }).gone, true,
    "a cancelled press left a pin for a later click to spend");

  cards.paint("a");
  cards.press();
  cards.clear();                          // the card left the queue: closed
  const target = cards.resolve({ items: [row("b")] });
  assert.equal(target.id, null, "a closed card still had something to decide");
  assert.equal(target.gone, false, "a closed card is not a refusal to announce");
});

await check("a row id compares the way every other id check in the widget does", async () => {
  // The queue is JSON from the backend and an event's id is a string; the
  // widget compares them as strings everywhere else (the approval-resolved
  // listener). A decision must not be refused over a type.
  const cards = new ApprovalTarget();
  cards.paint(7);
  assert.equal(cards.resolve({ items: [row("7")] }).card.id, "7");
  const other = new ApprovalTarget();
  other.paint("7");
  assert.equal(other.resolve({ items: [row(7)] }).card.id, 7);
});

await check("nothing painted, nothing pressed: nothing to decide, nothing to say", async () => {
  const cards = new ApprovalTarget();
  const target = cards.resolve({ count: 0, items: [] });
  assert.deepEqual(target, { id: null, card: null, gone: false });
  assert.equal(cards.resolve(null).gone, false, "a missing queue is not a refusal");
});

await check("the refusal is one plain sentence, and says where the card went", async () => {
  assert.match(GONE_LINE, /answered elsewhere/);
  assert.match(GONE_LINE, /nothing was sent/);
  assert.match(GONE_DETAIL, /phone/);
  assert.match(GONE_DETAIL, /Jarvis bar/);
  assert.ok(GONE_LINE.length <= 60, `the widget's flash line is 320px: "${GONE_LINE}"`);
});

/* ── the widget's own wiring ──────────────────────────────────────────────── */

const widget = read("src/widget.js");

await check("the widget decides through the rule, against the live queue", async () => {
  assert.match(widget, /import \{ ApprovalTarget, GONE_DETAIL, GONE_LINE \} from "\.\/approval-target\.js"/);
  assert.match(widget, /cards: new ApprovalTarget\(\)/, "no pin is kept at all");
  assert.match(widget, /const target = state\.cards\.resolve\(currentQueue\(\)\)/,
    "the decision is not resolved against the live queue");
  const decide = uncommented(fnBody(widget, "async function decide(approved, optionId = null) {"));
  assert.match(decide, /await decideOnBackend\(approval\.id, approved, optionId\)/,
    "the decision is not sent for the resolved card's id");
  assert.doesNotMatch(decide, /decideOnBackend\(state\.approval\.id/,
    "the widget is back to deciding whatever is in state.approval");
  assert.doesNotMatch(decide, /state\.approval/,
    "decide() still reads state.approval, which a queue re-read replaces under the finger");
  assert.match(decide, /flash\(GONE_LINE, "bad", GONE_DETAIL\)/,
    "a refused decision says nothing on screen");
  assert.match(decide, /state\.cards\.forgetPress\(\)/, "the pin is not spent");
});

await check("the press, not the click, is where the card is fixed", async () => {
  // Without the pointerdown/keydown capture the pin is only ever taken after
  // the swap, which is the bug with an extra step.
  const events = widget.slice(widget.indexOf('dom.btnApprYes.addEventListener("click"'));
  const block = events.slice(0, events.indexOf("dom.btnApprNoteSend"));
  assert.match(block, /btn\.addEventListener\("pointerdown", \(\) => state\.cards\.press\(\)\)/);
  assert.match(block, /event\.key === "Enter" \|\| event\.key === " "\) state\.cards\.press\(\)/,
    "Enter or Space on a focused button does not pin the card it was pressed on");
  assert.match(block, /btn\.addEventListener\("pointercancel", \(\) => state\.cards\.forgetPress\(\)\)/);
  const paint = uncommented(fnBody(widget, "function openApproval(approval) {"));
  assert.match(paint, /state\.cards\.paint\(approval\.id\)/, "openApproval no longer records the paint");
  const close = uncommented(fnBody(widget, "function closeApproval() {"));
  assert.match(close, /state\.cards\.clear\(\)/, "a closed card leaves its pin behind");
});

await check("the buttons' rules are unchanged: Deny is never disabled by a swap, and a locked or heavy card still opens the bar", async () => {
  const decide = uncommented(fnBody(widget, "async function decide(approved, optionId = null) {"));
  assert.match(decide,
    /approved && \(state\.appLock \|\| isEmailCard\(approval\) \|\| isHeavy\(approval\)\)/,
    "the redirect to the Jarvis bar no longer covers lock, email and heavy cards");
  assert.match(decide, /await approveInBar\(\)/);
  const sync = uncommented(fnBody(widget, "function syncApprovalButtons() {"));
  assert.match(sync, /dom\.btnApprNo\.disabled = blocked;/, "Deny is no longer always available");
  assert.doesNotMatch(sync, /state\.cards/, "the swap guard was put in the disable rule instead of the decision");
});

await check("CONTROL: the card still shows slot 0, and the count is still a number only", async () => {
  // The fix is about which card a decision names, not about what the widget
  // displays: the queue is still read once and the first card shown.
  const start = widget.indexOf("onQueue((queue) => {");
  assert.ok(start > 0, "the queue subscription is gone");
  const queue = uncommented(widget.slice(start, widget.indexOf("\n  });", start)));
  assert.match(queue, /const open = queue\.items\[0\] \|\| null;/);
  assert.match(queue, /dom\.apprCount\.textContent = open && total > 1 \? `1 of \$\{total\}` : "";/);
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("\nnothing is approved that was not on screen");
