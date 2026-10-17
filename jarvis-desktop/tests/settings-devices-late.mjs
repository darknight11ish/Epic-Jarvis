/**
 * A Devices request that never answers must SAY so, and give the controls back.
 *
 * WHY THIS SUITE EXISTS (the owner's report, 2026-10-16): *"when i go into
 * settings in the jarvis hud, hit pair phone, the settings page freezes and no
 * longer works with me"*.
 *
 * The reported shape was not reproduced; the condition that produces it was.
 * Every command in `devices.js` went straight to `TAURI.core.invoke` with no
 * budget of any kind - `settings.js`'s 30 s budget lives in a private
 * `OPEN_READS` set that only its own `invoke()` consults, and `settings.js`
 * exports nothing. So a `pair_start` that never settled left `pairPhone`'s
 * `busy` true for ever, `paint()` kept every control disabled
 * (`el.pair.disabled = busy || ...`), and the section sat on "Asking your PC
 * for a code…" with nothing said at all. That is the same defect
 * `settings-open-budget.mjs` fixed for five reads on 2026-10-10 and did not fix
 * for these.
 *
 * WHAT IT DRIVES. The REAL `src/settings.html`, through the suite's own bridge
 * (`tests/uikit.mjs`), with `pair_start` wrapped so it NEVER settles. After a
 * real wait - longer than the 30 s budget - it asks the two questions the
 * owner's freeze answers wrongly: is the section still saying it is asking, and
 * are the controls still dead?
 *
 * TWO THINGS IT CHECKS ABOUT THE WORDS, because `pair_start` is a WRITE:
 *   - they must say it is NOT KNOWN whether it happened. Rust does not cancel a
 *     command, so the PC can make a pairing session a moment after the page
 *     gives up: "may be out of date" would understate that, and "it failed"
 *     would be a lie in the other direction;
 *   - they must SURVIVE `problemWords()`, or the ordinary error path replaces
 *     the honest sentence with "Could not ask Jarvis." and says nothing true.
 *
 * CONTROL: the same card with `pair_start` answering normally must not be
 * stuck, so this can never pass by the card being broken for an unrelated
 * reason. That is `settings-failures.mjs`'s lesson - a suite that only ever
 * sees one side cannot tell "the fix works" from "the card is broken".
 *
 * Run by hand - it waits out a real budget, so it is deliberately NOT in
 * `npm run test:ui`, like `settings-open-budget.mjs`:
 *
 *     node tests/settings-devices-late.mjs [budgetSeconds]
 *
 * BEFORE THE FIX this reported, after 40 s: `Pair a phone disabled: true`,
 * `#dv-pair-status: "Asking your PC for a code…"`, and nothing said about the
 * wait. The words module is imported DYNAMICALLY on purpose: reverted, this
 * suite must fail on the stuck line and the dead button, not on a missing
 * symbol at load time.
 */
import assert from "node:assert/strict";
import * as K from "./uikit.mjs";

/** Above `CALL_BUDGET_MS` (30 s) in src/devices.js, plus room to poll. */
const BUDGET_S = Number(process.argv[2] || 40);

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── the words, with no page attached ───────────────────────────────────── */

let W = null;

await check("the card has a sentence for a late ANSWER, and it is not the read one", async () => {
  W = await import("../src/devices-words.js");
  assert.ok(W.LATE_ACTION, "no LATE_ACTION: a late action still has nothing to say");
  assert.ok(W.LATE_READ, "no LATE_READ: a late read still has nothing to say");
  assert.notEqual(W.LATE_ACTION, W.LATE_READ,
    "a write and a read cannot say the same thing - a write may really have happened");
  assert.match(W.LATE_ACTION, /not known/i,
    "the action words must say it is not known, not that it failed");
  assert.match(W.LATE_READ, /out of date/i, "the read words must say the part is out of date");
});

await check("... and the honest sentence survives problemWords()", async () => {
  assert.ok(W && W.problemWords, "problemWords is gone from the words module");
  // The ordinary error path must pass it through unchanged: if the filter
  // swallows it, the owner is told "Could not ask Jarvis." instead of the truth.
  assert.equal(W.problemWords(new Error(W.LATE_ACTION)), W.LATE_ACTION,
    "problemWords() replaced the sentence that says what is actually true");
  assert.doesNotMatch(W.LATE_ACTION, /[{}<>]|::|not allowed|undefined|null/i, W.LATE_ACTION);
  assert.ok(W.LATE_ACTION.length <= 400, "too long for problemWords() to pass on");
});

/* ── the page, with pair_start never answering ──────────────────────────── */

/** The Devices card, with `pair_start` answering or never settling at all. */
async function open({ hang }) {
  const page = await K.open(browser, base, "settings.html", {}, { width: 900, height: 1200 });
  // The harness installs its bridge as an INIT script, so a wrapper added now
  // takes effect on the NEXT navigation - which is exactly where it is needed.
  await page.addInitScript((hang) => {
    const wrap = () => {
      const core = window.__TAURI__ && window.__TAURI__.core;
      if (!core) return false;
      const real = core.invoke.bind(core);
      window.__pairStartCalls = 0;
      core.invoke = (cmd, args) => {
        if (cmd === "devices_list") {
          return Promise.resolve({ devices: [], shared_retired: false, live: true });
        }
        if (cmd === "pair_phone_address") {
          return Promise.resolve({ address: "my-pc.tail1234.ts.net", known: true });
        }
        if (cmd === "pair_start") {
          window.__pairStartCalls += 1;
          if (hang) return new Promise(() => {}); // accepted, never answered
        }
        return real(cmd, args);
      };
      return true;
    };
    if (!wrap()) {
      const iv = setInterval(() => { if (wrap()) clearInterval(iv); }, 1);
    }
  }, hang);
  await page.reload();
  await page.waitForTimeout(2500);
  await page.evaluate(() => {
    for (const d of document.querySelectorAll("details")) d.open = true;
  });
  // Make the address known, so `pairPhone` does not stop at NEEDS_ADDRESS.
  await page.evaluate(() => {
    const el = document.querySelector("#dv-address");
    if (el) el.value = "my-pc.tail1234.ts.net";
  });
  const pair = page.locator("#dv-pair");
  await pair.scrollIntoViewIfNeeded();
  await pair.click({ force: true });
  return page;
}

const stateOf = (page) => page.evaluate(() => ({
  calls: window.__pairStartCalls,
  status: ((document.querySelector("#dv-pair-status") || {}).textContent || "").trim(),
  pairDisabled: Boolean(document.querySelector("#dv-pair").disabled),
  addressDisabled: Boolean(document.querySelector("#dv-address").disabled),
  cancelDisabled: Boolean(document.querySelector("#dv-cancel").disabled),
}));

const hung = await open({ hang: true });
await new Promise((r) => setTimeout(r, BUDGET_S * 1000));
const stuck = await stateOf(hung);
await hung.close();

await check(`after ${BUDGET_S}s with no answer, the section is not still saying it is asking`, async () => {
  assert.equal(stuck.calls, 1, "pair_start was never called - the click did not reach the card");
  assert.doesNotMatch(stuck.status, /Asking your PC for a code/,
    `still saying it is asking after ${BUDGET_S}s: ${stuck.status}`);
  assert.ok(stuck.status.length > 0, "the section said nothing at all about the wait");
});

await check("... and every control is live again", async () => {
  assert.equal(stuck.pairDisabled, false, "Pair a phone is still disabled - the section is dead");
  assert.equal(stuck.addressDisabled, false, "the address field is still disabled");
  assert.equal(stuck.cancelDisabled, false, "Cancel is still disabled");
});

await check("... and the words are the card's own, never a bridge error", async () => {
  assert.ok(W && W.LATE_ACTION, "the card has no late-action sentence at all");
  assert.equal(stuck.status, W.LATE_ACTION, `the card said something else: ${stuck.status}`);
  assert.doesNotMatch(stuck.status, /[{}<>]|::|undefined|null|Cannot read/, stuck.status);
});

/* ── the control ────────────────────────────────────────────────────────── */

const answered = await open({ hang: false });
await new Promise((r) => setTimeout(r, 3000));
const fine = await stateOf(answered);
await answered.close();

await check("CONTROL: the same card, with pair_start answering, is not stuck", async () => {
  assert.ok(fine.calls > 0, "CONTROL FAILED: the control never called pair_start");
  assert.equal(fine.pairDisabled, false,
    "CONTROL FAILED: the card is broken even when the PC answers, so this suite proves nothing");
});

await browser.close(); close();
console.log(fails.length
  ? `\n${fails.length} FAILED`
  : "\na pairing request that never answers says so, and the controls come back");
process.exit(fails.length ? 1 : 0);
