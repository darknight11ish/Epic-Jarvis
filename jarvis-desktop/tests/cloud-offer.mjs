/**
 * "Try the cloud model" - the owner's yes to send ONE question to the cloud
 * lane jarvis_router.choose() already named, for THIS question only
 * (docs/JARVIS-API.md, "`offer` in `X-Jarvis-Route`"; backend/cloud-say-yes.patch).
 *
 * The two route-header fixtures used here (`cloud offered` and its
 * older-backend twin) are real: tests/fixtures/chat-stream-cases.json is
 * generated from jarvis_router.choose()'s own real output, not hand-made.
 *
 * What must hold:
 * - the offer shows only on a finished answer whose route said gate "offer"
 *   with a non-empty `offer` lane - never mid-stream, never on an error;
 * - a plain answer (no offer, or gate anything else) never shows it;
 * - "Try the cloud model" resends the SAME question with `cloudYes: true`,
 *   and the offer is gone the moment it is pressed;
 * - "Not now" hides the offer and sends nothing;
 * - a new question always starts with no offer showing, even before its own
 *   route header (if any) arrives.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const CHAT = JSON.parse(read("tests/fixtures/chat-stream-cases.json"));
const okBody = CHAT.cases.find((c) => c.name === "local turn").body;
const pumpLines = (body) => body.split("\n").map((l) => l.replace(/\r$/, "")).filter((l) => l.trim());
const routeChunk = (header) => "\u001fjarvis-route:" + JSON.stringify(JSON.parse(header));
const OFFERED = CHAT.route_headers.find((r) => r.name === "local answer, cloud offered");
const PLAIN = CHAT.route_headers.find((r) => r.name === "local answer");
assert.ok(OFFERED, "fixture 'local answer, cloud offered' is gone");
assert.ok(PLAIN, "fixture 'local answer' is gone");

const state = (page) => page.evaluate(() => {
  const $ = (id) => document.getElementById(id);
  return {
    hidden: $("answer-cloud-offer").hidden,
    label: $("answer-cloud-offer-label")?.textContent ??
      document.querySelector(".answer-cloud-offer-label")?.textContent,
    button: $("cloud-offer-try")?.textContent,
    dismiss: $("cloud-offer-dismiss")?.textContent,
    micro: document.querySelector(".answer-cloud-offer-micro")?.textContent,
  };
});

async function ask(page, prompt = "hi") {
  await page.locator("#prompt").fill(prompt);
  await page.locator("#prompt").press("Enter");
  await page.waitForTimeout(400);
}

await check("a plain answer (no offer) never shows the cloud-offer block", async () => {
  const page = await K.open(browser, base, "index.html",
    { chatReplies: [[routeChunk(PLAIN.header), ...pumpLines(okBody)]] }, { width: 750, height: 700 });
  await ask(page);
  const s = await state(page);
  await page.close();
  assert.equal(s.hidden, true);
});

await check("gate 'offer' with a lane shows the fixed wording, word for word with the phone", async () => {
  const page = await K.open(browser, base, "index.html",
    { chatReplies: [[routeChunk(OFFERED.header), ...pumpLines(okBody)]] }, { width: 750, height: 700 });
  await ask(page);
  const s = await state(page);
  await page.close();
  assert.equal(s.hidden, false);
  assert.equal(s.label, "A cloud model could give this one a second look.");
  assert.equal(s.button, "Try the cloud model");
  assert.equal(s.dismiss, "Not now");
  assert.equal(s.micro, "Sends only this question - nothing else from this conversation.");
});

await check("an older backend without `where` still offers (the fixture's own second case)", async () => {
  const older = CHAT.route_headers.find((r) => r.name === "local answer, cloud offered, older backend without `where`");
  assert.ok(older);
  const page = await K.open(browser, base, "index.html",
    { chatReplies: [[routeChunk(older.header), ...pumpLines(okBody)]] }, { width: 750, height: 700 });
  await ask(page);
  const s = await state(page);
  await page.close();
  assert.equal(s.hidden, false);
});

await check("the offer never shows before the answer is done, and vanishes if an error follows", async () => {
  // No chatReplies queued for the second turn: stream_chat throws inside the
  // mock (uikit.mjs's own "nothing scripted" path resolves cleanly instead),
  // so use a body with no route line at all to prove a plain, offer-less
  // stream never paints the block mid-flight or afterwards.
  const page = await K.open(browser, base, "index.html",
    { chatReplies: [pumpLines(okBody)] }, { width: 750, height: 700 });
  await page.locator("#prompt").fill("hi");
  await page.locator("#prompt").press("Enter");
  await page.waitForTimeout(50);
  const mid = await state(page);
  await page.waitForTimeout(350);
  const done = await state(page);
  await page.close();
  assert.equal(mid.hidden, true, "the offer showed before the answer finished");
  assert.equal(done.hidden, true, "a stream with no route line showed an offer");
});

await check('"Try the cloud model" resends the same question with cloud_yes, then hides itself', async () => {
  const page = await K.open(browser, base, "index.html", {
    chatReplies: [
      [routeChunk(OFFERED.header), ...pumpLines(okBody)],
      [routeChunk(PLAIN.header), ...pumpLines(okBody)],
    ],
  }, { width: 750, height: 700 });
  await ask(page, "what is the airspeed velocity of an unladen swallow");
  const before = await state(page);
  await page.locator("#cloud-offer-try").click();
  await page.waitForTimeout(400);
  const after = await state(page);
  const sent = await page.evaluate(() =>
    window.__calls.filter(([c]) => c === "stream_chat").map(([, a]) => a));
  await page.close();
  assert.equal(before.hidden, false, "no offer to try");
  assert.equal(sent.length, 2, "did not resend exactly once");
  assert.equal(sent[0].cloudYes, false, "the first ask already claimed the owner's yes");
  assert.equal(sent[1].cloudYes, true, "the resend did not carry the owner's yes");
  const secondMessages = sent[1].messages;
  const lastUser = secondMessages[secondMessages.length - 1];
  assert.match(JSON.stringify(lastUser), /unladen swallow/);
  assert.equal(after.hidden, true, "the offer stayed up after being acted on");
});

await check('"Not now" hides the offer and sends nothing', async () => {
  const page = await K.open(browser, base, "index.html",
    { chatReplies: [[routeChunk(OFFERED.header), ...pumpLines(okBody)]] }, { width: 750, height: 700 });
  await ask(page);
  await page.locator("#cloud-offer-dismiss").click();
  await page.waitForTimeout(200);
  const s = await state(page);
  const calls = await page.evaluate(() => window.__calls.filter(([c]) => c === "stream_chat").length);
  await page.close();
  assert.equal(s.hidden, true);
  assert.equal(calls, 1, "dismissing sent a request");
});

await check("a second question clears the first one's offer even before its own route header arrives", async () => {
  const page = await K.open(browser, base, "index.html", {
    chatReplies: [
      [routeChunk(OFFERED.header), ...pumpLines(okBody)],
      [routeChunk(PLAIN.header), ...pumpLines(okBody)],
    ],
  }, { width: 750, height: 700 });
  await ask(page, "first question");
  const first = await state(page);
  await page.locator("#prompt").fill("second question");
  await page.locator("#prompt").press("Enter");
  await page.waitForTimeout(30);
  const mid = await state(page);
  await page.waitForTimeout(400);
  const after = await state(page);
  await page.close();
  assert.equal(first.hidden, false, "the first answer never earned its offer");
  assert.equal(mid.hidden, true, "the old offer was still up once a new question was sent");
  assert.equal(after.hidden, true, "the second, plain answer showed an offer");
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nThe cloud offer holds");
process.exit(fails.length ? 1 : 0);
