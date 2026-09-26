/**
 * Chat history on the PC, the quickbar's half (JARVIS-API.md section 18):
 * every /api/chat request carries a `conversation_id` and `device:
 * "desktop"`, and every user turn a `provenance` - where its words came
 * from - which is KEPT with the turn and sent again with it later.
 *
 * Read off the real `stream_chat` calls the page makes (uikit mock), the
 * same way tests/conversation.mjs reads the history. The rules themselves
 * are pinned without a browser in tests/chat-history.mjs; these prove the
 * page really follows them: the clipboard prefill, an edit, a paste, a drop,
 * a voice turn, a picture, and Up-arrow recall.
 *
 * The HUD page's half is in tests/hud.mjs; the Brain's History tab in
 * tests/history.mjs.
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

const open = (data = {}) => K.open(browser, base, "index.html", data, { width: 420, height: 500 });

const submit = async (page, text) => {
  await page.locator("#prompt").fill(text);
  await page.locator("#prompt").press("Enter");
  await page.waitForTimeout(200);
};
const pressEnter = async (page) => {
  await page.locator("#prompt").press("Enter");
  await page.waitForTimeout(200);
};

/** Every stream_chat call's arguments, in order. */
const calls = (page) => page.evaluate(() =>
  window.__calls.filter((c) => c[0] === "stream_chat").map((c) => c[1]));
/** "role:provenance" per message of one call; "-" where there is none. */
const tags = (call) => call.messages.map((m) => `${m.role}:${m.provenance || "-"}`);

/** A real paste or drop, as far as the page can tell: the event on the box,
 *  then the `input` event the browser follows it with. */
const insert = (page, kind, text) => page.evaluate(([kind, text]) => {
  const box = document.getElementById("prompt");
  box.focus();
  const ev = kind === "paste"
    ? new ClipboardEvent("paste", { bubbles: true, cancelable: true })
    : new DragEvent("drop", { bubbles: true, cancelable: true });
  box.dispatchEvent(ev);
  box.value += text;
  box.dispatchEvent(new InputEvent("input", {
    bubbles: true, inputType: kind === "paste" ? "insertFromPaste" : "insertFromDrop", data: text,
  }));
}, [kind, text]);

await check("every request carries one conversation id and device desktop, the same for a follow-up", async () => {
  const page = await open({ chatReplies: ["one", "two"] });
  await submit(page, "first question");
  await submit(page, "a follow-up");
  const sent = await calls(page);
  const errors = page.__errors;
  await page.close();
  assert.equal(sent.length, 2);
  assert.match(sent[0].conversationId, /^[A-Za-z0-9_-]{8,64}$/);
  assert.equal(sent[1].conversationId, sent[0].conversationId, "a follow-up started a new conversation");
  assert.deepEqual(sent.map((c) => c.device), ["desktop", "desktop"]);
  assert.deepEqual(errors, []);
});

await check("New conversation and Esc each start a new conversation id", async () => {
  const page = await open({ chatReplies: ["one", "two", "three"] });
  await submit(page, "first");
  await page.locator("#new-conversation").click();
  await page.waitForTimeout(100);
  await submit(page, "second");
  await page.keyboard.press("Escape");
  await page.waitForTimeout(150);
  await submit(page, "third");
  const ids = (await calls(page)).map((c) => c.conversationId);
  await page.close();
  assert.equal(new Set(ids).size, 3, `ids ${JSON.stringify(ids)}`);
});

await check("a typed question is typed, and each turn's tag is sent again with it", async () => {
  const page = await open({ chatReplies: ["a1", "a2", "a3"] });
  await submit(page, "typed by hand");
  await insert(page, "paste", "text from somewhere else");
  await pressEnter(page);
  await submit(page, "typed again");
  const sent = await calls(page);
  await page.close();
  assert.deepEqual(tags(sent[0]), ["user:typed"]);
  assert.deepEqual(tags(sent[1]), ["user:typed", "assistant:-", "user:pasted"]);
  // Two turns later the pasted turn is still pasted: the tag did not fall off.
  assert.deepEqual(tags(sent[2]),
    ["user:typed", "assistant:-", "user:pasted", "assistant:-", "user:typed"]);
  assert.equal(sent[2].messages[2].content, "text from somewhere else");
});

await check("pasted stays pasted while typing around it, until the box is emptied", async () => {
  const page = await open({ chatReplies: ["a1", "a2"] });
  await insert(page, "paste", "pasted words");
  await page.locator("#prompt").press("End");
  await page.keyboard.type(" and my own");
  await pressEnter(page);
  // Pasted, then deleted to nothing, then typed: typed.
  await insert(page, "paste", "gone again");
  await page.locator("#prompt").fill("");
  await page.keyboard.type("all mine");
  await pressEnter(page);
  const sent = await calls(page);
  await page.close();
  assert.equal(sent[0].messages.at(-1).provenance, "pasted");
  assert.equal(sent[1].messages.at(-1).provenance, "typed");
});

await check("a drop on the box tags the words pasted", async () => {
  const page = await open({ chatReplies: ["a1"] });
  await insert(page, "drop", "dragged in");
  await pressEnter(page);
  const sent = await calls(page);
  await page.close();
  assert.equal(sent[0].messages.at(-1).provenance, "pasted");
});

await check("the clipboard prefill is clipboard, edited or not, until the box is emptied", async () => {
  const page = await open({ chatReplies: ["a1", "a2"] });
  await page.evaluate(() => window.__emit("clipboard-inject", "short snippet"));
  await page.waitForTimeout(100);
  await pressEnter(page);
  await page.evaluate(() => window.__emit("clipboard-inject", "another snippet"));
  await page.waitForTimeout(100);
  await page.locator("#prompt").press("End");
  await page.keyboard.type("?");
  await pressEnter(page);
  const sent = await calls(page);
  await page.close();
  const first = sent[0].messages.at(-1);
  assert.equal(first.content, "short snippet");
  assert.equal(first.provenance, "clipboard", "sent unedited, the prefill is not the owner's typing");
  const second = sent[1].messages.at(-1);
  assert.equal(second.content, "another snippet?");
  assert.equal(second.provenance, "clipboard", "an edit made a clipboard snippet the owner's own words (R3)");
  // And the first turn keeps its tag in the second request's history.
  assert.equal(sent[1].messages[0].provenance, "clipboard");
});

await check("clipboard context is its own user turn tagged clipboard, never a system turn", async () => {
  // Security audit M1: sent as a system turn, it slipped past the PC's
  // outside-text rules, which read user turns. Now the same shape as the
  // phone's Share: its own user message, just before the question.
  const long = "x".repeat(250);   // too long for the box: it rides as context
  const page = await open({ chatReplies: ["a1"] });
  await page.evaluate((t) => window.__emit("clipboard-inject", t), long);
  await page.waitForTimeout(100);
  await submit(page, "what does this say?");
  const sent = await calls(page);
  await page.close();
  assert.deepEqual(tags(sent[0]), ["user:clipboard", "user:typed"]);
  assert.equal(sent[0].messages[0].content, `Context:\n${long}`);
  assert.ok(!sent[0].messages.some((m) => m.role === "system"), "a system turn was sent");
});

await check("a voice turn is voice", async () => {
  const page = await open({ chatReplies: ["a1"] });
  await page.evaluate(() => window.__emit("voice-heard",
    { available: true, isOwner: true, awake: false, text: "what's on today" }));
  await page.waitForTimeout(250);
  const sent = await calls(page);
  await page.close();
  assert.equal(sent.length, 1);
  assert.deepEqual(sent[0].messages.at(-1),
    { role: "user", content: "what's on today", provenance: "voice" });
});

await check("words sent with a picture are the picture's caption", async () => {
  const page = await open({ chatReplies: ["a1"], vision: { model: "qwen2.5vl:7b", vision: true, reason: "" } });
  await page.evaluate(() => window.__emit("screen-captured",
    { dataUri: "data:image/gif;base64,R0lGODlhAQABAAAAACw=", width: 1, height: 1, bytes: 634, elapsedMs: 12 }));
  await page.waitForTimeout(100);
  await submit(page, "what is this?");
  const sent = await calls(page);
  await page.close();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].messages.at(-1).provenance, "picture_caption");
});

await check("a pasted prompt recalled with Up is sent as pasted again", async () => {
  const page = await open({ chatReplies: ["a1", "a2"] });
  await insert(page, "paste", "pasted once");
  await pressEnter(page);
  await page.locator("#prompt").press("ArrowUp");
  await pressEnter(page);
  const sent = await calls(page);
  await page.close();
  assert.equal(sent[1].messages.at(-1).content, "pasted once");
  assert.equal(sent[1].messages.at(-1).provenance, "pasted");
});

await check("CONTROL: stream_chat takes the two fields and passes on only good ones", async () => {
  const rust = read("src-tauri/src/commands.rs");
  assert.match(rust, /pub async fn stream_chat\([\s\S]*?conversation_id: Option<String>,\s*device: Option<String>,/);
  assert.match(rust, /body\.extend\(chat_extras\(conversation_id\.as_deref\(\), device\.as_deref\(\)\)\)/);
  assert.match(rust, /matches!\(\*d, "desktop" \| "hud"\)/);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nevery turn says where its words came from");
process.exit(fails.length ? 1 : 0);
