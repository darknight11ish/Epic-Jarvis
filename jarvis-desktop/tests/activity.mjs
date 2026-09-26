/**
 * "Activity" - past approvals, read-only (ease-of-use audit, 2026-09-27,
 * row 11; src/brain.js renderActivity, src/brain.html, src-tauri/src/
 * brain/routes.rs "gate_history"; docs/JARVIS-API.md section 3).
 *
 * What must hold:
 * - the Brain's Work tab, next to the Undo shelf, shows one row per past
 *   card: a title safe for a lock screen, Approved/Denied/Timed out, when,
 *   and which device - built from `gate_history`, the SAME `/api/pending`
 *   the stream already polls for the live queue, read again for its
 *   `history` half;
 * - it never shares a list with a waiting card, even when one is live;
 * - a row with a state this window does not recognise reads "Not
 *   reported", never a guess; a row naming no device says nothing about
 *   one rather than inventing "this PC";
 * - a title with no `notice.title` falls back to the same action-name
 *   wording a live card with no notice uses (card-words.js fallbackTitle),
 *   word for word the phone's own fallback;
 * - a PC without the module (`available: false`) says so, with no Retry;
 * - it is read-only: no button, no link, nothing here decides anything.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const readRepo = (p) => readFileSync(join(HERE, "..", "..", p), "utf8");

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 1100 };
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

async function workTab(brainOverrides = {}, data = {}) {
  const page = await K.open(browser, base, "brain.html",
    { ...data, brain: { ...K.BRAIN, ...brainOverrides } }, SIZE);
  await page.locator("#tab-work").click();
  await page.waitForTimeout(300);
  return page;
}

await check("one row per past card: title, outcome, when, device", async () => {
  const page = await workTab();
  const text = await page.locator("#activity").innerText();
  await page.close();
  assert.match(text, /Jarvis wants your OK for "send email"/);
  assert.match(text, /Approved/);
  assert.match(text, /this PC/);
  assert.match(text, /Jarvis wants your OK for "run shell on host"/);
  assert.match(text, /Denied/);
  assert.match(text, /another device/);
});

await check("an unrecognised state reads \"Not reported\", never a guess", async () => {
  const page = await workTab({
    gate_history: { available: true, pending: [], history: [
      { id: "x1", action: "web_research", created: 1_700_000_000, state: "something_new" },
    ] },
  });
  const text = await page.locator("#activity").innerText();
  await page.close();
  assert.match(text, /Not reported/);
  assert.ok(!/something_new/.test(text), "the raw, unrecognised state leaked to the screen");
});

await check("approvals.state's real values map correctly, expired included", async () => {
  const page = await workTab({
    gate_history: { available: true, pending: [], history: [
      { id: "e1", action: "web_research", created: 1_700_000_000, state: "expired" },
    ] },
  });
  const text = await page.locator("#activity").innerText();
  await page.close();
  assert.match(text, /Timed out/);
});

await check("a row naming no device says nothing about one - never a guessed \"this PC\"", async () => {
  const page = await workTab({
    gate_history: { available: true, pending: [], history: [
      { id: "h3", action: "web_research", created: 1_700_000_000, state: "expired" },
    ] },
  });
  const text = await page.locator("#activity").innerText();
  await page.close();
  assert.ok(!/this PC/.test(text) && !/another device/.test(text),
    "no device field was sent, so none should be shown");
});

await check("a title falls back to the same wording a live card with no notice uses", async () => {
  const page = await workTab({
    gate_history: { available: true, pending: [], history: [
      { id: "n1", action: "switch_model", created: 1_700_000_000, state: "denied" },
    ] },
  });
  const text = await page.locator("#activity").innerText();
  await page.close();
  assert.match(text, /Jarvis wants your OK for "switch model"/);
});

await check("never shares a list with a waiting card, even when one is live", async () => {
  // A live approval, exactly as `/api/pending`'s `pending` array would carry
  // it and jarvis-link.js's own queue (get_pending_approvals) reads it - a
  // DIFFERENT call than brain_read's "gate_history", and never rendered by
  // this pane, whatever the live queue holds.
  const page = await workTab({}, {
    pending: [{ id: "live1", action: "send_email", tier: "ask", created: Date.now() / 1000,
      detail: {}, prompt: "send a live email", notice: { title: "LIVE CARD, NOT PAST" } }],
  });
  const text = await page.locator("#activity").innerText();
  await page.close();
  assert.ok(!/live1/.test(text) && !/LIVE CARD/.test(text),
    "a waiting card's own words reached the read-only past-approvals pane");
  // Only the fixture's three PAST rows are on screen, never a fourth.
  assert.equal((text.match(/Jarvis wants your OK for/g) || []).length, 3);
});

await check("a PC without the module says so, with no Retry", async () => {
  const page = await workTab({ gate_history: { available: false } });
  const text = await page.locator("#activity").innerText();
  const retryVisible = await page.locator("#activity button", { hasText: "Retry" }).count();
  await page.close();
  assert.match(text, /Not on this backend/);
  assert.equal(retryVisible, 0);
});

await check("read-only: no button and no link anywhere in the pane", async () => {
  const page = await workTab();
  const buttons = await page.locator("#activity button").count();
  const links = await page.locator("#activity a").count();
  await page.close();
  assert.equal(buttons, 0);
  assert.equal(links, 0);
});

await check("gate_history is read through the Brain's fixed read allowlist, not a new endpoint", async () => {
  const routes = read("src-tauri/src/brain/routes.rs");
  assert.match(routes, /\("gate_history",\s*"\/api\/pending"\)/);
  // The same route the stream already classifies as `ported` in
  // tools/check_parity.py - not a second call that tool would need to learn.
  const parity = readRepo("tools/check_parity.py");
  assert.match(parity, /"\/api\/pending":\s*\("ported"/);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nActivity: past approvals, read-only, next to the Undo shelf, never sharing a list with a waiting card");
process.exit(fails.length ? 1 : 0);
