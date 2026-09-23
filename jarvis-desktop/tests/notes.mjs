/**
 * Logseq / Joplin notes that are really filed - backend note-capture.patch.
 *
 * Before: `#log`, `#joplin`, Alt+Shift+N and the widget's capture field all
 * asked a MODEL to call `append_logseq_journal` / `create_joplin_note` -
 * tools that existed nowhere - and could only say "Sent". Now the owner's
 * own words go to `/api/notes/capture` with no model, and what the screen
 * says comes from the backend's answer: filed, waiting for approval, or not
 * filed and why.
 *
 * Two halves: the shared filer (`src/note-capture.js`) as plain logic, and
 * the two windows that use it, in a real browser.
 */
import assert from "node:assert/strict";
import { describeJob, fileNote } from "../src/note-capture.js";
import * as K from "./uikit.mjs";

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The filer, as logic ─────────────────────────────────────────────────── */

await check("filed is said only for state filed, in the server's words", async () => {
  const d = describeJob({ state: "filed", message: "Filed in Logseq, journals/2026_09_23.md." }, "logseq");
  assert.equal(d.text, "Filed in Logseq, journals/2026_09_23.md.");
  assert.equal(d.tone, "ok");
  assert.ok(d.final);
});

await check("waiting, not filed and failed never read as filed", async () => {
  for (const state of ["waiting", "not_filed", "failed", undefined, "weird"]) {
    const d = describeJob({ state, message: "Filed in Logseq." }, "logseq");
    if (state === "waiting") {
      assert.match(d.text, /Waiting for your approval/);
      assert.ok(!d.final);
    } else {
      assert.notEqual(d.tone, "ok", `state ${state} was shown as a success`);
    }
  }
});

await check("a waiting card is followed until it ends", async () => {
  const answers = [
    { id: "note_1", state: "waiting", message: "Waiting for your approval." },
    { id: "note_1", state: "waiting", message: "Waiting for your approval." },
    { id: "note_1", state: "not_filed", message: "You said no, so nothing was written." },
  ];
  const calls = [];
  const invoke = async (cmd, args) => { calls.push([cmd, args]); return answers.shift(); };
  const seen = [];
  const last = await fileNote(invoke, "logseq", "hello", (d) => seen.push(d), { pollMs: 1 });
  assert.deepEqual(calls.map((c) => c[0]), ["capture_note", "capture_note_status", "capture_note_status"]);
  assert.deepEqual(calls[0][1], { target: "logseq", text: "hello" });
  assert.equal(last.text, "You said no, so nothing was written.");
  assert.equal(last.tone, "bad");
  assert.match(seen[0].text, /Waiting/);
});

await check("it gives up saying nothing is filed, not that it was", async () => {
  const invoke = async () => ({ id: "note_2", state: "waiting" });
  const last = await fileNote(invoke, "joplin", "x", () => {}, { pollMs: 1, giveUpMs: 5 });
  assert.match(last.text, /Nothing is filed until you answer/);
});

/* ── The windows ─────────────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const widget = (data) => K.open(browser, base, "widget.html", data, { width: 320, height: 520 });

await check("widget: a filed note says where, in the PC's words", async () => {
  const page = await widget({});
  await page.fill("#capture-input", "buy milk");
  await page.press("#capture-input", "Enter");
  await page.waitForTimeout(250);
  const flash = await page.locator("#widget-flash").innerText();
  const calls = await page.evaluate(() => window.__noteCalls);
  const cleared = await page.locator("#capture-input").inputValue();
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(calls, [{ cmd: "capture_note", target: "logseq", text: "buy milk" }]);
  assert.match(flash, /Filed in Logseq, journals\/2026_09_23\.md/);
  assert.equal(cleared, "");
  assert.deepEqual(errors, [], JSON.stringify(errors));
});

await check("widget: a refused note says so, and is not shown as filed", async () => {
  const page = await widget({ noteJobs: [{ id: "n", state: "not_filed",
    message: "You said no, so nothing was written." }] });
  await page.fill("#capture-input", "private");
  await page.press("#capture-input", "Enter");
  await page.waitForTimeout(250);
  const flash = await page.locator("#widget-flash").innerText();
  const tone = await page.locator("#widget-flash").getAttribute("data-tone");
  await page.close();
  assert.match(flash, /You said no/);
  assert.equal(tone, "bad");
});

await check("widget: a backend without the route says so, and keeps the text", async () => {
  const page = await widget({});
  await page.evaluate(() => { window.__captureNoteFails =
    "this Jarvis backend cannot file notes yet - apply the backend patches (note-capture.patch) to turn it on. Nothing was filed."; });
  await page.fill("#capture-input", "keep me");
  await page.press("#capture-input", "Enter");
  await page.waitForTimeout(250);
  const flash = await page.locator("#widget-flash").innerText();
  const kept = await page.locator("#capture-input").inputValue();
  await page.close();
  assert.match(flash, /cannot file notes yet/);
  assert.equal(kept, "keep me", "a note that was not filed must not vanish from the field");
});

await check("quickbar: #log files the note directly, with no chat turn", async () => {
  const page = await K.open(browser, base, "index.html", {});
  await page.fill("#prompt", "#log call the plumber");
  await page.press("#prompt", "Enter");
  await page.waitForTimeout(300);
  const calls = await page.evaluate(() => window.__noteCalls);
  const chats = await page.evaluate(() => (window.__calls || []).filter((c) => c[0] === "stream_chat"));
  const answer = await page.locator("#answer").innerText();
  const status = await page.locator("#card-status-text").textContent();
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(calls, [{ cmd: "capture_note", target: "logseq", text: "call the plumber" }]);
  assert.equal(chats.length, 0, "a note still started a chat turn");
  assert.match(answer, /Filed in Logseq/);
  assert.equal(status, "Filed");
  assert.deepEqual(errors, [], JSON.stringify(errors));
});

await check("quickbar: #joplin waits for the card, then reports how it ended", async () => {
  const page = await K.open(browser, base, "index.html", { noteJobs: [
    { id: "n9", state: "waiting", message: "Waiting for your approval." },
    { id: "n9", state: "filed", message: "Filed in Joplin." },
  ] });
  await page.fill("#prompt", "#joplin dentist on Friday");
  await page.press("#prompt", "Enter");
  await page.waitForTimeout(300);
  const statusWaiting = await page.locator("#card-status-text").textContent();
  await page.waitForTimeout(2600);
  const statusAfter = await page.locator("#card-status-text").textContent();
  const answer = await page.locator("#answer").innerText();
  const calls = await page.evaluate(() => window.__noteCalls.map((c) => c.cmd));
  await page.close();
  assert.equal(statusWaiting, "Waiting for approval");
  assert.equal(statusAfter, "Filed");
  assert.match(answer, /Filed in Joplin/);
  assert.deepEqual(calls, ["capture_note", "capture_note_status"]);
});

await check("quickbar: an ordinary question is still a chat turn", async () => {
  const page = await K.open(browser, base, "index.html", {});
  await page.fill("#prompt", "what is the weather");
  await page.press("#prompt", "Enter");
  await page.waitForTimeout(300);
  const calls = await page.evaluate(() => window.__noteCalls);
  await page.close();
  assert.deepEqual(calls, [], "a question without a prefix was filed as a note");
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nnotes are filed by the PC, and the screen only repeats what the PC said");
process.exit(fails.length ? 1 : 0);
