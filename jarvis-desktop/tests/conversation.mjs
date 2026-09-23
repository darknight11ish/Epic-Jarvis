/**
 * The quickbar's follow-ups carry the conversation so far, read off the real
 * `stream_chat` calls the page makes (src/chat-history.js for the limits;
 * tests/chat-history.mjs checks those without a browser).
 *
 * The quickbar used to send the newest question alone, so "and what about
 * Tuesday?" reached the model with nothing before it. The mock's
 * `stream_chat` sends each queued reply as raw text and resolves, which is a
 * real finished turn to `finishStream`.
 */
import assert from "node:assert/strict";
import * as K from "./uikit.mjs";

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

/** "role:content" for every message of every stream_chat call, in order. */
const sent = (page) => page.evaluate(() =>
  window.__calls.filter((c) => c[0] === "stream_chat")
    .map((c) => c[1].messages.map((m) =>
      `${m.role}:${typeof m.content === "string" ? m.content : "[parts]"}`)));

await check("the first question goes alone", async () => {
  const page = await open({ chatReplies: ["Tuesday at 3."] });
  await submit(page, "when is the dentist?");
  const calls = await sent(page);
  await page.close();
  assert.deepEqual(calls, [["user:when is the dentist?"]]);
});

await check("a follow-up carries the earlier question and its answer, oldest first", async () => {
  const page = await open({ chatReplies: ["Tuesday at 3.", "Yes, Wednesday is free."] });
  await submit(page, "when is the dentist?");
  await submit(page, "can I move it?");
  const calls = await sent(page);
  await page.close();
  assert.deepEqual(calls[1], [
    "user:when is the dentist?",
    "assistant:Tuesday at 3.",
    "user:can I move it?",
  ]);
});

await check("clipboard context stays with its own turn, after the history", async () => {
  const page = await open({ chatReplies: ["first answer", "second answer"] });
  await submit(page, "first question");
  await page.evaluate(() => window.__emit && window.__emit("clipboard-inject", "some pasted text"));
  await page.waitForTimeout(100);
  await submit(page, "what does this say?");
  const calls = await sent(page);
  await page.close();
  const second = calls[1];
  assert.equal(second[0], "user:first question", "the history must lead, so the prompt cache holds");
  assert.equal(second[1], "assistant:first answer");
  assert.equal(second[second.length - 1], "user:what does this say?");
  // The clipboard turn sits after the history, right before its question.
  const sys = second.findIndex((m) => m.startsWith("system:"));
  assert.equal(sys, 2, `system turn at ${sys}: ${JSON.stringify(second)}`);
  assert.equal(second.length, 4);
});

await check("an empty answer is not kept", async () => {
  // No reply queued: the stream ends with nothing, and the card shows its
  // own placeholder - which Jarvis never said.
  const page = await open({ chatReplies: [] });
  await submit(page, "first question");
  await submit(page, "second question");
  const calls = await sent(page);
  await page.close();
  assert.deepEqual(calls[1], ["user:second question"]);
});

await check("an SSE answer cut off before its end marker is not kept", async () => {
  const cut = ['data: {"choices":[{"delta":{"content":"half an ans"}}]}'];
  const page = await open({ chatReplies: [cut, "second answer"] });
  await submit(page, "first question");
  await submit(page, "second question");
  const calls = await sent(page);
  await page.close();
  assert.deepEqual(calls[1], ["user:second question"]);
});

await check("an SSE answer that says it finished is kept", async () => {
  const whole = ['data: {"choices":[{"delta":{"content":"whole answer"}}]}', "data: [DONE]"];
  const page = await open({ chatReplies: [whole, "second answer"] });
  await submit(page, "first question");
  await submit(page, "second question");
  const calls = await sent(page);
  await page.close();
  assert.deepEqual(calls[1], ["user:first question", "assistant:whole answer", "user:second question"]);
});

await check("New conversation appears after an answer and makes the next question start fresh", async () => {
  const page = await open({ chatReplies: ["first answer", "second answer"] });
  const before = await page.locator("#new-conversation").isHidden();
  await submit(page, "first question");
  const shown = await page.locator("#new-conversation").isVisible();
  await page.locator("#new-conversation").click();
  await page.waitForTimeout(100);
  const cardHidden = await page.locator("#card").isHidden();
  const buttonHidden = await page.locator("#new-conversation").isHidden();
  await submit(page, "second question");
  const calls = await sent(page);
  await page.close();
  assert.ok(before, "offered before there was any conversation");
  assert.ok(shown, "not offered after a finished answer");
  assert.ok(cardHidden, "the old answer stayed on screen after starting afresh");
  assert.ok(buttonHidden, "still offered with nothing left to forget");
  assert.deepEqual(calls[1], ["user:second question"]);
});

await check("Esc clears the conversation with the card", async () => {
  const page = await open({ chatReplies: ["first answer", "second answer"] });
  await submit(page, "first question");
  await page.keyboard.press("Escape");
  await page.waitForTimeout(150);
  await submit(page, "second question");
  const calls = await sent(page);
  await page.close();
  assert.deepEqual(calls[1], ["user:second question"]);
});

await check("the button sits on one line beside Copy at the quickbar's real width", async () => {
  // 750 logical px: QUICKBAR_WIDTH in src-tauri/src/windows.rs.
  const page = await K.open(browser, base, "index.html", { chatReplies: ["first answer"] },
    { width: 750, height: 500 });
  await submit(page, "first question");
  const box = await page.locator("#new-conversation").boundingBox();
  const copy = await page.locator("#copy").boundingBox();
  const card = await page.locator("#card").boundingBox();
  const errors = page.__errors;
  await page.close();
  assert.ok(box && copy && card, "no layout box");
  assert.ok(box.x >= card.x && box.x + box.width <= card.x + card.width + 0.5,
    `button ${JSON.stringify(box)} spills out of the card ${JSON.stringify(card)}`);
  assert.ok(Math.abs(box.height - copy.height) < 2,
    `wrapped onto two lines: ${box.height}px tall beside Copy's ${copy.height}px`);
  assert.deepEqual(errors, []);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nfollow-ups carry the conversation");
process.exit(fails.length ? 1 : 0);
