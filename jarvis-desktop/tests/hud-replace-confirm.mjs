/**
 * Review ruling 8.2 on the HUD WINDOW's injected bootstrap - the surface a
 * pre-merge audit showed could still approve a state-replacing card with ONE
 * click, because the bootstrap's capture listener stops the page's own
 * two-press and sends `decide_approval` itself.
 *
 *     node tests/hud-replace-confirm.mjs
 *
 * No browser HERE: the pure rule (`replacePressGuard`) is LIFTED out of
 * `src-tauri/src/hud_bootstrap.js` and driven with a fake clock, exactly the
 * way approvals-contract.mjs lifts the HUD page's card builder. The CLICK
 * wiring itself is executed by the Playwright case in `tests/hud.mjs` (which
 * CI runs), where a fake `/api/pending` returns a `replaces` card and the
 * first click is waited on and asserted to send nothing.
 *
 * THE THREE STATES the rule must tell apart (the audit's fail-safe finding):
 * `replaces: true` -> second press; `replaces: false` -> one click;
 * UNKNOWN (an absent field on an older PC, or a row missing from a successful
 * read, or a failed read) -> second press with the honest "I could not check"
 * words. Only an explicit `false` is treated as ordinary.
 *
 * The bite: with the guard removed from the bootstrap the lift fails and every
 * check here fails with it. With the wiring removed the wiring checks fail.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const TAURI = join(HERE, "..", "src-tauri", "src");
const BOOTSTRAP = readFileSync(join(TAURI, "hud_bootstrap.js"), "utf8");
const HUD_PAGE = readFileSync(join(HERE, "..", "src", "jarvis_hud.html"), "utf8");

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

/** One `function name(...)...` body, lifted as source text. */
const lift = (name) => {
  const m = BOOTSTRAP.match(new RegExp(
    `function ${name}\\([^)]*\\)\\s*\\{[\\s\\S]*?\\n  \\}\\n`));
  assert.ok(m, `hud_bootstrap.js has no function ${name}`);
  return m[0];
};
const liftConst = (name) => {
  const m = BOOTSTRAP.match(new RegExp(`var ${name} = \\d+;`));
  assert.ok(m, `hud_bootstrap.js has no var ${name}`);
  return m[0];
};

// The rule and its window, lifted together and built in node. The fake clock
// is injected the way the real handler's default `Date.now` behaves, so the
// EXPIRY case is measured rather than waited out.
function makeGuard(clock) {
  const src = `${liftConst("HUD_REPLACE_ARM_MS")}\n${lift("replacePressGuard")}`
    + " return function (opts) { return replacePressGuard(Object.assign("
    + "{ now: clock }, opts || {})); };";
  return new Function("clock", src)(clock)();
}

check("the HUD bootstrap carries the two-press rule and its own window", () => {
  assert.match(BOOTSTRAP, /var HUD_REPLACE_ARM_MS = \d{4,6};/);
  assert.match(BOOTSTRAP, /function replacePressGuard\(opts\)/);
});

check("(a) ONE click on a replacing card sends NOTHING - it only arms", () => {
  let t = 1000;
  const guard = makeGuard(() => t);
  let sends = 0;
  const click = (id, replaces) => {
    const verdict = guard.decide(id, replaces);
    if (verdict === "send") sends += 1;
    return verdict;
  };
  assert.equal(click("restore-1", true), "arm-replace");
  assert.equal(sends, 0, "the first click sent an approval");
  assert.equal(guard.isArmed("restore-1"), true);
});

check("(b) the SECOND deliberate press sends exactly ONE decision", () => {
  let t = 2000;
  const guard = makeGuard(() => t);
  let sends = 0;
  const click = (id, replaces) => {
    if (guard.decide(id, replaces) === "send") sends += 1;
  };
  click("restore-1", true);
  click("restore-1", true);
  assert.equal(sends, 1, "two presses must send exactly one decision");
  click("restore-1", true);          // a third press is a fresh first press
  assert.equal(sends, 1, "a third press sent a decision of its own");
});

check("(c) an EXPLICITLY ordinary card still sends on one click", () => {
  const guard = makeGuard(() => 5000);
  assert.equal(guard.decide("send-email-1", false), "send");
  assert.equal(guard.isArmed("send-email-1"), false);
});

check("(c2) UNKNOWN (absent field / missing row) requires the second press", () => {
  // The audit's fail-safe finding: during a partial deploy, or against an
  // older PC with no `replaces` field, or when a successful read does not
  // contain the card, ONE click must not approve a state-replacing action.
  const guard = makeGuard(() => 6000);
  assert.equal(guard.decide("restore-x", null), "arm-unknown");
  assert.equal(guard.isArmed("restore-x"), true);
  assert.equal(guard.decide("restore-x", null), "send");
  // An absent field is exactly `undefined`: unknown too, not "ordinary".
  assert.equal(guard.decide("restore-y", undefined), "arm-unknown");
});

check("(d) an arm expires, never leaks, and never covers another card", () => {
  let t = 10000;
  const guard = makeGuard(() => t);
  // Arm a replacing card.
  assert.equal(guard.decide("restore-A", true), "arm-replace");
  // Another replacing card does NOT inherit that arm: its first press arms.
  assert.equal(guard.decide("restore-B", true), "arm-replace");
  // ... and a different ordinary card still sends at once.
  assert.equal(guard.decide("email-C", false), "send");
  // An expired arm does not send: the press after the window arms again.
  assert.equal(guard.decide("restore-A", true), "arm-replace");
  t += 10001;
  assert.equal(guard.decide("restore-A", true), "arm-replace",
    "a press after the arm window must not send");
  assert.equal(guard.isArmed("restore-A"), true, "and it must re-arm");
});

check("(d2) expiry clears the arm unconditionally, whatever the clock says", () => {
  // The audit's NIT: a timer that fires a millisecond late used to re-check
  // the arm and return, leaving the label "Confirm replace" - whose next
  // press would silently send. `clearIf` must not look at the clock.
  const guard = makeGuard(() => 1000);
  assert.equal(guard.decide("restore-t", true), "arm-replace");
  assert.match(BOOTSTRAP, /clearIf: function \(id\)/);
  guard.clearIf("restore-t");
  assert.equal(guard.isArmed("restore-t"), false);
  // A clear for a different id leaves this card's arm alone.
  assert.equal(guard.decide("restore-u", true), "arm-replace");
  guard.clearIf("someone-else");
  assert.equal(guard.isArmed("restore-u"), true);
});

check("(e) the HUD click wiring cannot send an approve before the rule says so", () => {
  // The capture handler is where the HUD really decides, so the send must sit
  // AFTER the replace rule's answer. The CLICK itself is executed by the
  // Playwright case in tests/hud.mjs; this pins the ordering and the words.
  const at = BOOTSTRAP.indexOf("var card = button.closest(\".appr\");");
  assert.ok(at > 0, "the HUD capture handler is gone");
  const handler = BOOTSTRAP.slice(at, at + 8000);
  const firstPress = handler.indexOf("replaceArmBusy[id] = true;");
  assert.ok(firstPress > 0, "the handler has no first-press branch");
  const branch = handler.slice(firstPress, firstPress + 2000);
  const decideAt = branch.indexOf("replacePress.decide(id, replaces)");
  assert.ok(decideAt > 0, "the first press does not consult the two-press rule");
  assert.match(branch, /if \(verdict === "send"\)/);
  assert.match(branch, /armReplaceCard\(card, id, verdict\)/);
  // Deny is one press: it goes straight to the decision, before the rule.
  assert.match(handler, /button\.className\.indexOf\("yes"\) < 0/);
  // Both honest wordings exist, and they are not interchangeable: an UNKNOWN
  // card must say it could not be checked, never claim it replaces data.
  assert.match(BOOTSTRAP, /This REPLACES what is on your PC\./);
  assert.match(BOOTSTRAP, /I could not check what this will replace\./);
  // The expiry timer clears for its id unconditionally, and arming a new card
  // first clears the previous card's label (the audit's NIT 1 and NIT 2).
  const timer = BOOTSTRAP.slice(BOOTSTRAP.indexOf("replaceArmTimer = setTimeout"),
                                BOOTSTRAP.indexOf("}, HUD_REPLACE_ARM_MS);") + 25);
  assert.match(timer, /replacePress\.clearIf\(id\)/);
  assert.doesNotMatch(timer, /isArmed/,
    "the expiry timer re-checks the arm, so a late timer can leave the label on");
  const armFn = BOOTSTRAP.slice(BOOTSTRAP.indexOf("function armReplaceCard"),
                                BOOTSTRAP.indexOf("function pendingRowFor"));
  assert.match(armFn, /disarmReplaceCard\(\);/,
    "arming a card does not clear the previous card's label");
});

check("(f) the page's own two-press is still there for the browser case", () => {
  // The desktop HUD is the bootstrap's; the page's copy stays for a browser
  // tab with no bootstrap injected, and both must exist (one rule, two owners).
  assert.match(HUD_PAGE, /Confirm replace/);
  assert.match(HUD_PAGE, /apprReplace\(/);
});

console.log(fails.length ? `\n${fails.length} failed` : "\nall HUD replace-confirm checks passed");
process.exit(fails.length ? 1 : 0);
