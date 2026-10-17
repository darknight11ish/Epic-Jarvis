/**
 * Deny is never held while the connection is catching up.
 *
 * The project's own words, on the "When the connection is catching up" page:
 * *"Nothing is decided while the stream is stale - refusing is never held,
 * approving can be."* Until 2026-10-17 both apps held BOTH answers, so while
 * the link caught up the owner could not say no - the one direction a person
 * most needs when the picture is uncertain.
 *
 * A stale deny is safe by construction: it is an explicit polarity (never a
 * toggle) and cannot approve anything; the card transitions once, so a deny for
 * a card that is still pending is the answer that was wanted; a late one is
 * refused by the server's own expired / duplicate / no-longer-pending arm (a
 * 409, which both pages already show as "already handled"), never silently
 * dropped; and denying never writes a standing rule.
 *
 * So this suite holds, per surface:
 *   - STALE: Deny is offered and pressing it sends `approved: false`;
 *   - STALE: Approve is held, and the words say what is waiting (and that Deny
 *     still works - the old line said "nothing can be answered", now false);
 *   - LIVE: both answers work exactly as before (the control);
 *   - LATE: a deny the server refuses with its 409 arm is said out loud, and
 *     the card is not silently closed as if it had been denied.
 *
 *   node tests/deny-on-stale.mjs      (needs Playwright, like the others)
 */
import assert from "node:assert/strict";
import * as K from "./uikit.mjs";

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try {
    await fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

const STALE = { connected: true, stale: true };
const LIVE = { connected: true, stale: false };

/** The Jarvis bar, opened on one waiting card. */
const openBar = (over = {}, vp = { width: 750, height: 900 }) =>
  K.open(browser, base, "index.html", {
    attention: K.ATTENTION_CLEAR,
    pending: [K.APPROVAL_PLAIN],
    ...over,
  }, vp);

/** The desktop's widget window, opened on the same card. */
const openWidget = (over = {}) =>
  K.open(browser, base, "widget.html", {
    prefs: { expanded: true },
    pending: [K.APPROVAL_PLAIN],
    ...over,
  }, { width: 340, height: 520 });

const press = (page, sel) => page.click(sel);
const decides = (page) => page.evaluate(() => window.__decides || []);
const isEnabled = (page, sel) =>
  page.evaluate((s) => {
    const el = document.querySelector(s);
    return Boolean(el) && !el.disabled;
  }, sel);
const says = (page, sel) => page.locator(sel).innerText();
const denied = { id: K.APPROVAL_PLAIN.id, approved: false, optionId: undefined };
const approved = { id: K.APPROVAL_PLAIN.id, approved: true, optionId: undefined };

/* ── The Jarvis bar ──────────────────────────────────────────────────────── */

await check("bar, STALE: Deny is offered, and pressing it sends a deny", async () => {
  const page = await openBar({ link: STALE });
  await page.waitForTimeout(500);
  assert.equal(await isEnabled(page, "#approval-deny"), true,
               "Deny is disabled while the stream is stale");
  await press(page, "#approval-deny");
  await page.waitForTimeout(300);
  assert.deepEqual(await decides(page), [denied]);
  await page.close();
});

await check("bar, STALE: Approve is held, and the words say Deny still works", async () => {
  const page = await openBar({ link: STALE });
  await page.waitForTimeout(500);
  assert.equal(await isEnabled(page, "#approval-approve"), false,
               "Approve must wait for a queue that can be confirmed");
  const hint = await says(page, "#approval-hint");
  assert.match(hint, /approving waits/i, `the hint must say what waits: "${hint}"`);
  assert.match(hint, /Deny still works/, `the hint must say Deny works: "${hint}"`);
  assert.doesNotMatch(hint, /nothing can be answered/,
                      `the old sentence is false now: "${hint}"`);
  await page.close();
});

await check("bar, CONTROL: on a live link both answers work", async () => {
  const page = await openBar({ link: LIVE });
  await page.waitForTimeout(500);
  assert.equal(await isEnabled(page, "#approval-approve"), true);
  assert.equal(await isEnabled(page, "#approval-deny"), true);
  await press(page, "#approval-approve");
  await page.waitForTimeout(300);
  assert.deepEqual(await decides(page), [approved]);
  await page.close();
});

await check("bar, LATE: a deny the server refuses is said, and the card is not silently closed", async () => {
  const page = await openBar({ link: STALE, decideFails: "HTTP 409: already decided" });
  await page.waitForTimeout(500);
  await press(page, "#approval-deny");
  await page.waitForTimeout(400);
  const hint = await says(page, "#approval-hint");
  assert.match(hint, /already handled/i,
               `the server's existing 409 arm must be shown, not swallowed: "${hint}"`);
  assert.equal(await page.locator("#approval").isVisible(), true,
               "the card vanished without being answered");
  await page.close();
});

/* ── The desktop widget (Alt+Shift+W) ────────────────────────────────────── */

await check("widget, STALE: Deny is offered, and pressing it sends a deny", async () => {
  const page = await openWidget({ link: STALE });
  await page.waitForTimeout(700);
  assert.equal(await isEnabled(page, "#btn-appr-no"), true,
               "the widget hid Deny while the stream was stale");
  await press(page, "#btn-appr-no");
  await page.waitForTimeout(300);
  assert.deepEqual(await decides(page), [denied]);
  await page.close();
});

await check("widget, STALE: Approve is held, and the card says Deny still works", async () => {
  const page = await openWidget({ link: STALE });
  await page.waitForTimeout(700);
  assert.equal(await isEnabled(page, "#btn-appr-yes"), false,
               "the widget's Approve must wait");
  const why = await says(page, "#appr-why");
  assert.match(why, /approving waits/i, `the why line must say what waits: "${why}"`);
  assert.match(why, /Deny still works/, `the why line must say Deny works: "${why}"`);
  await page.close();
});

await check("widget, CONTROL: on a live link Deny works as before", async () => {
  const page = await openWidget({ link: LIVE });
  await page.waitForTimeout(700);
  assert.equal(await isEnabled(page, "#btn-appr-no"), true);
  await press(page, "#btn-appr-no");
  await page.waitForTimeout(300);
  assert.deepEqual(await decides(page), [denied]);
  await page.close();
});

await check("widget, LATE: a refused deny says so instead of vanishing", async () => {
  const page = await openWidget({ link: STALE, decideFails: "HTTP 409: already decided" });
  await page.waitForTimeout(700);
  await press(page, "#btn-appr-no");
  await page.waitForTimeout(400);
  assert.match(await says(page, "#widget-flash"), /already handled/i);
  await page.close();
});

await browser.close();
close();
console.log(`\n${fails.length ? fails.length + " FAILED" : "Deny is never held on a stale link"}`);
process.exit(fails.length ? 1 : 0);
