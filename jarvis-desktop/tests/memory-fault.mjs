/**
 * The ONE learning-fault banner, with "Retry now" (2026-11-09; the memory-card
 * research's measured finding; JARVIS-API.md section 213).
 *
 * WHAT MUST HOLD. When a batch check fails - a damaged auto-learning.json, no
 * local model, a cloud model name, a missing jarvis_intake.py - the PC records
 * one fault instead of writing the same reason onto every fact, and both apps
 * show ONE banner instead of up to 200 cards. This test proves the desktop
 * half:
 *
 *   * the banner renders the PC's OWN words (`headline`), as text, and adds
 *     only its button's "Retry now";
 *   * there is exactly one button, and it calls exactly one command
 *     (`brain_memory_fault_retry`) - it is never an approve, a bulk form or a
 *     card;
 *   * the PC's own `outcome` is shown after the press, and a retry that
 *     clears the fault leaves that sentence (not a silent disappearance);
 *   * a genuine per-fact card sent by the PC is still drawn beside the
 *     banner - this window hides nothing itself;
 *   * a fault read that failed does not hide the queue;
 *   * no fault means no banner at all.
 *
 * The browser half runs on the uikit mock; `brain_memory_fault_retry` is
 * stubbed there and `window.__faultRetry.calls` counts the presses.
 */
import assert from "node:assert/strict";
import {
  FAULT_RETRY_LABEL,
  FAULT_RETRY_TITLE,
  readFault,
} from "../src/auto-learn.js";
import * as K from "./uikit.mjs";

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const FAULT = {
  active: true,
  reason: "the learning model is not on this PC",
  headline: "Jarvis could not check the facts it was about to save: the learning " +
    "model is not on this PC. 2 facts are held back, unsaved, until that check " +
    "works again. This is the check failing, not your facts.",
  count: 2,
  since: 1_790_000_000,
  at: 1_790_000_100,
  tries: 0,
  last_try_at: null,
  last_result: "",
  recorded: true,
  why: "",
};

/* ── The pure reader ───────────────────────────────────────────────────── */

await check("the button says the approved words, and only those", async () => {
  assert.equal(FAULT_RETRY_LABEL, "Retry now");
  assert.match(FAULT_RETRY_TITLE, /approves nothing and saves nothing/);
});

await check("only an exactly-true active fault is a banner", async () => {
  assert.equal(readFault(null), null);
  assert.equal(readFault(undefined), null);
  assert.equal(readFault({}), null);
  assert.equal(readFault({ active: false, reason: "x", headline: "y" }), null);
  assert.equal(readFault({ active: "true", reason: "x", headline: "y" }), null);
  assert.equal(readFault({ active: 1, reason: "x", headline: "y" }), null);
  // A fault with no words of its own explains nothing, so it is not drawn.
  assert.equal(readFault({ active: true, reason: "  ", headline: "" }), null);
});

await check("the PC's own sentence and reason are passed on, untouched", async () => {
  const f = readFault(FAULT);
  assert.ok(f);
  assert.equal(f.headline, FAULT.headline);
  assert.equal(f.reason, FAULT.reason);
  assert.equal(f.count, 2);
  assert.equal(f.recorded, true);
  // An older PC that sends only a reason still gets a banner that explains.
  const older = readFault({ active: true, reason: "the learning model is not on this PC" });
  assert.equal(older.headline, "the learning model is not on this PC");
  // Junk counts never become a number on screen.
  assert.equal(readFault({ active: true, reason: "r", count: "9" }).count, 0);
});

/* ── The window ────────────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 900 };

/** The Memory tab, with `fault` as the PC's fault read and `pending` as the
 *  cards the PC returned (already filtered by the PC). */
async function memoryTab({ fault = FAULT, pending = [], faultRetry = {} } = {}) {
  const page = await K.open(browser, base, "brain.html", {
    brain: {
      ...K.BRAIN,
      memory_fault: fault,
      memory_pending: { ...K.BRAIN.memory_pending, pending },
    },
    faultRetry,
  }, SIZE);
  await page.locator("#tab-memory").click();
  await page.waitForTimeout(250);
  return page;
}

const ONE_CARD = {
  id: 41, text: "Prefers invoices filed by supplier, not by month.",
  source: "conversation", confidence: 0.82, created: 1_790_000_000,
  auto_reason: "about health, a sensitive topic",
};

await check("ONE banner, the PC's words, ONE button - and no 200 cards", async () => {
  const page = await memoryTab();
  const banner = page.locator("#memory-proposals .memory-fault");
  assert.equal(await banner.count(), 1, "exactly one fault banner");
  assert.equal(await banner.getAttribute("data-tone"), "warn");
  assert.equal(await banner.getAttribute("role"), "alert");
  const text = await banner.innerText();
  assert.ok(text.includes(FAULT.headline),
    `the banner must carry the PC's own sentence; got: ${text}`);
  const buttons = banner.locator("button");
  assert.equal(await buttons.count(), 1, "the banner carries exactly one button");
  assert.equal((await buttons.innerText()).trim(), "Retry now");
  // No per-fact card and no "nothing is waiting" line while it explains itself.
  assert.equal(await page.locator("#memory-proposals .row-item").count(), 0);
  const whole = await page.locator("#memory-proposals").innerText();
  assert.ok(!/Nothing is waiting/.test(whole), whole);
  const errors = await page.evaluate(() => window.__errors || []);
  assert.deepEqual(errors, []);
  await page.close();
});

await check("a genuine per-fact card is drawn BESIDE the banner, not hidden here", async () => {
  const page = await memoryTab({ pending: [ONE_CARD] });
  const banner = page.locator("#memory-proposals .memory-fault");
  assert.equal(await banner.count(), 1);
  assert.equal(await page.locator("#memory-proposals .row-item").count(), 1,
    "the PC sent this card, so it is shown");
  const rows = await page.locator("#memory-proposals .row-item").innerText();
  assert.ok(rows.includes("Prefers invoices filed by supplier"), rows);
  await page.close();
});

await check("the PC's words go in as TEXT, never as markup", async () => {
  const page = await memoryTab({
    fault: { ...FAULT, headline: "The check failed <b>badly</b> & <script>x</script>" },
  });
  const bold = await page.locator("#memory-proposals .memory-fault b").count();
  const script = await page.locator("#memory-proposals .memory-fault script").count();
  const text = await page.locator("#memory-proposals .memory-fault").innerText();
  assert.equal(bold, 0);
  assert.equal(script, 0);
  assert.ok(text.includes("<b>badly</b>"), text);
  await page.close();
});

await check("no fault: no banner, and the empty queue says so as before", async () => {
  const page = await memoryTab({ fault: { available: true, active: false } });
  assert.equal(await page.locator("#memory-proposals .memory-fault").count(), 0);
  const text = await page.locator("#memory-proposals").innerText();
  assert.ok(/Nothing is waiting/.test(text), text);
  await page.close();
});

await check("a fault read that failed hides nothing: the cards are the truth", async () => {
  const page = await memoryTab({
    fault: { available: false, error: "the memory layer is not importable" },
    pending: [ONE_CARD],
  });
  assert.equal(await page.locator("#memory-proposals .memory-fault").count(), 0);
  assert.equal(await page.locator("#memory-proposals .row-item").count(), 1);
  await page.close();
});

await check("Retry now calls the ONE command, once, and shows the PC's outcome", async () => {
  const still = {
    ...FAULT, tries: 1,
  };
  const page = await memoryTab({
    faultRetry: {
      answers: [{
        ok: true,
        cleared: false,
        fault: still,
        outcome: "The check still fails: the learning model is not on this PC. " +
          "Nothing was saved or approved.",
      }],
    },
  });
  await page.locator("#memory-proposals .memory-fault button").click();
  await page.waitForTimeout(400);
  const calls = await page.evaluate(() => window.__faultRetry.calls);
  assert.equal(calls, 1, `the one command is called once, not ${calls}`);
  const text = await page.locator("#memory-proposals .memory-fault").innerText();
  assert.ok(text.includes(FAULT.headline), text);
  assert.ok(text.includes("The check still fails"), `the PC's outcome is shown: ${text}`);
  assert.equal(await page.locator("#memory-proposals .memory-fault button").count(), 1,
    "a fault that still fails keeps the button");
  const errors = await page.evaluate(() => window.__errors || []);
  assert.deepEqual(errors, []);
  await page.close();
});

await check("a retry that clears the fault keeps the PC's sentence, without a button", async () => {
  const page = await memoryTab({
    faultRetry: {
      answers: [{
        ok: true,
        cleared: true,
        fault: { available: true, active: false, reason: "", headline: "", count: 0 },
        outcome: "The check works again, so the warning is cleared. Nothing was " +
          "saved or approved by this: your facts are still waiting where they were.",
      }],
    },
  });
  await page.locator("#memory-proposals .memory-fault button").click();
  await page.waitForTimeout(400);
  const banner = page.locator("#memory-proposals .memory-fault");
  assert.equal(await banner.count(), 1, "the answer is not a silent disappearance");
  assert.equal(await banner.getAttribute("data-tone"), "ok");
  const text = await banner.innerText();
  assert.ok(text.includes("The check works again"), text);
  assert.equal(await banner.locator("button").count(), 0,
    "cleared means nothing left to retry");
  await page.close();
});

await check("CONTROL: no page threw while any of this ran", async () => {
  const page = await memoryTab({ pending: [ONE_CARD] });
  const errors = await page.evaluate(() => window.__errors || []);
  await page.close();
  assert.deepEqual(errors, []);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nthe fault banner holds");
process.exit(fails.length ? 1 : 0);
