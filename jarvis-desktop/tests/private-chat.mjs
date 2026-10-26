/**
 * Private chat in the desktop quickbar - owner-approved 2026-10-26.
 *
 * A private turn is a temporary chat PLUS a strict zero-write promise
 * (docs/JARVIS-API.md section 156): no memory, nothing learned or kept, no
 * tool, no card. What must hold:
 * - the mode is offered only on a PC whose /api/version advertises
 *   capabilities.private_chat; an older PC stays off and says why, and the
 *   Rust command refuses rather than sending an ordinary turn;
 * - every question of a private chat is sent with `private: true` and NEVER
 *   with `temporary: true` (the server implies the temporary half);
 * - it starts a new conversation when turned on or off, cannot be on at the
 *   same time as Incognito/Temporary, and resets when a chat ends;
 * - an answer the PC did not confirm as private says so plainly.
 *
 * Pure words first, then the quickbar in a real browser on the uikit mock.
 * Playwright's Chromium is headless: no visible window is opened.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  CONTINUED_PRIVATE_OFF,
  PRIVATE_ENDED,
  PRIVATE_LABEL,
  PRIVATE_LINE,
  PRIVATE_NOT_CONFIRMED,
  PRIVATE_STARTED,
  PRIVATE_UNAVAILABLE,
} from "../src/private-chat.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const route = (r) => "\u001fjarvis-route:" + JSON.stringify(r);
const LOCAL = { lane: "qwen3:8b", where: "local", gate: "complexity" };

/* ── The words ─────────────────────────────────────────────────────────── */

await check("the words say what a private chat promises", async () => {
  assert.equal(PRIVATE_LABEL, "Private");
  assert.match(PRIVATE_LINE, /won't use or learn from your memory/);
  assert.match(PRIVATE_LINE, /keeps nothing/);
  assert.match(PRIVATE_LINE, /won't run tools/);
  assert.match(PRIVATE_UNAVAILABLE, /isn't available on this PC's version of Jarvis/);
  assert.match(PRIVATE_UNAVAILABLE, /nothing was sent/);
  assert.match(PRIVATE_ENDED, /next question starts a normal chat/);
  assert.match(PRIVATE_STARTED, /won't use memory/);
  assert.match(PRIVATE_NOT_CONFIRMED, /did not confirm this was a private chat/);
  assert.match(CONTINUED_PRIVATE_OFF, /continued chat is kept/);
});

await check("the desktop sources carry the fail-closed and mutual-exclusion wiring", async () => {
  const main = read("src/main.js");
  assert.match(main, /private_chat_available/);
  assert.match(main, /onTurnOn: \(\) => privateChat\.offQuietly\(\)/);
  assert.match(main, /onTurnOn: \(\) => temporaryChat\.offQuietly\(\)/);
  assert.match(main, /private: privateChat\.on/);
  const rust = read("src-tauri/src/commands.rs");
  assert.match(rust, /PRIVATE_UNAVAILABLE/);
  assert.match(rust, /private_chat_in_version/);
  assert.match(rust, /add_chat_mode_flags\(body, temporary, private, cloud_yes\)/);
  assert.match(rust, /PRIVATE_UNAVAILABLE\.to_string\(\)/);
});

/* ── The quickbar ──────────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 520, height: 640 };

async function quickbar(data = {}, setup = {}) {
  const page = await K.open(browser, base, "index.html", data, SIZE);
  await page.evaluate((s) => Object.assign(window, s), setup);
  return page;
}
const submit = async (page, text) => {
  await page.locator("#prompt").fill(text);
  await page.locator("#prompt").press("Enter");
  await page.waitForTimeout(250);
};
const chats = (page) => page.evaluate(() =>
  window.__calls.filter((c) => c[0] === "stream_chat")
    .map((c) => ({ private: c[1].private, temporary: c[1].temporary,
                   conversationId: c[1].conversationId,
                   messages: c[1].messages.map((m) => m.content) })));
const strip = (page) => page.locator("#private-strip").innerText();

await check("an older PC: the mode stays off, says why, and sends no private turn", async () => {
  const page = await quickbar({ chatReplies: ["Hi."] }, { __privateOk: false, __temporaryOk: true });
  await page.locator("#private").click();
  await page.waitForTimeout(200);
  const pressed = await page.locator("#private").getAttribute("aria-pressed");
  const line = await strip(page);
  await submit(page, "hello");
  const sent = await chats(page);
  await page.close();
  assert.equal(pressed, "false", "an older PC must not enter the mode");
  assert.equal(line.trim(), PRIVATE_UNAVAILABLE);
  assert.notEqual(sent[0].private, true, "an ordinary turn was sent as private");
  assert.notEqual(sent[0].temporary, true, "the refused private turn became temporary");
});

await check("on: a marker for the whole chat, and every question carries ONLY private", async () => {
  const page = await quickbar({ chatReplies: ["Hello."] }, { __privateOk: true });
  await page.locator("#private").click();
  await page.waitForTimeout(200);
  const pressed = await page.locator("#private").getAttribute("aria-pressed");
  const empty = await strip(page);
  const marked = await page.locator("#shell").getAttribute("data-private");
  await submit(page, "secret question");
  const sent = await chats(page);
  await page.close();
  assert.equal(pressed, "true");
  assert.equal(marked, "true");
  assert.match(empty, new RegExp(`^${PRIVATE_LABEL}`));
  assert.ok(empty.includes(PRIVATE_LINE.replace(/^Private:\s*/, "")), empty);
  assert.equal(sent[0].private, true, "the question did not carry private: true");
  assert.notEqual(sent[0].temporary, true, "private and temporary were both sent");
});

await check("turning it on or off starts a new conversation", async () => {
  const page = await quickbar({ chatReplies: ["A."] }, { __privateOk: true });
  await submit(page, "normal question");
  await page.locator("#private").click();
  await page.waitForTimeout(200);
  await submit(page, "private question");
  await page.locator("#private").click();
  await page.waitForTimeout(200);
  const pressed = await page.locator("#private").getAttribute("aria-pressed");
  await submit(page, "normal again");
  const sent = await chats(page);
  await page.close();
  assert.deepEqual(sent.map((s) => s.messages),
    [["normal question"], ["private question"], ["normal again"]]);
  assert.deepEqual(sent.map((s) => s.private === true), [false, true, false]);
  assert.equal(new Set(sent.map((s) => s.conversationId)).size, 3, "a conversation id was reused");
  assert.equal(pressed, "false");
});

await check("Private and Incognito cannot both be on; each turns the other off", async () => {
  const page = await quickbar({ chatReplies: ["A."] }, { __privateOk: true, __temporaryOk: true });
  await page.locator("#temporary").click();
  await page.waitForTimeout(150);
  await page.locator("#private").click();
  await page.waitForTimeout(200);
  const tempPressed = await page.locator("#temporary").getAttribute("aria-pressed");
  const privatePressed = await page.locator("#private").getAttribute("aria-pressed");
  await page.locator("#temporary").click();
  await page.waitForTimeout(200);
  const tempAgain = await page.locator("#temporary").getAttribute("aria-pressed");
  const privateAgain = await page.locator("#private").getAttribute("aria-pressed");
  await page.close();
  assert.equal(privatePressed, "true");
  assert.equal(tempPressed, "false", "Incognito stayed on beside Private");
  assert.equal(tempAgain, "true");
  assert.equal(privateAgain, "false", "Private stayed on beside Incognito");
});

await check("new conversation resets Private to off and says the chat was private", async () => {
  const page = await quickbar({ chatReplies: ["Done."] }, { __privateOk: true });
  await page.locator("#private").click();
  await page.waitForTimeout(150);
  await submit(page, "secret");
  await page.locator("#new-conversation").click();
  await page.waitForTimeout(250);
  const pressed = await page.locator("#private").getAttribute("aria-pressed");
  const hidden = await page.locator("#private-strip").isHidden();
  const note = await page.locator("#chat-ended-note").innerText();
  await page.close();
  assert.equal(pressed, "false", "Private survived the end of its chat");
  assert.equal(hidden, true, "the private marker stayed after the chat ended");
  assert.equal(note.trim(), PRIVATE_ENDED);
});

await check("a PC that does not confirm a private turn is never pretended to have", async () => {
  const page = await quickbar({
    chatReplies: [[route({ ...LOCAL, temporary: true }), "An answer."]],
  }, { __privateOk: true });
  await page.locator("#private").click();
  await page.waitForTimeout(150);
  await submit(page, "private?");
  const note = await page.locator("#answer-memory-note").innerText();
  await page.close();
  assert.equal(note.trim(), PRIVATE_NOT_CONFIRMED,
    "a private turn without private:true in the route was not called out");
});

await check("a confirmed private turn says nothing about game mode or used memories", async () => {
  const page = await quickbar({
    chatReplies: [[route({ ...LOCAL, private: true, temporary: true, injected_facts: 0 }), "An answer."]],
  }, { __privateOk: true });
  await page.locator("#private").click();
  await page.waitForTimeout(150);
  await submit(page, "private?");
  const note = await page.locator("#answer-memory-note").innerText();
  const used = await page.locator("#answer-used").isVisible();
  await page.close();
  assert.equal(note.trim(), "", note);
  assert.equal(used, false);
});

await browser.close();
await close();
if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nprivate chat: all checks passed");
