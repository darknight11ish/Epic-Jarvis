/**
 * The composer: prompt history recall and the previous-answer scrollback.
 *
 * Both exist for the same complaint — asking two or three quick things back
 * to back used to mean retyping a fixed prompt and losing the answer to the
 * one before it, with no way back to either. Neither one is streaming-shaped
 * to test: the mock's `stream_chat` resolves with no chunks, which is exactly
 * the codepath `finishStream` already treats as a real completed turn (the
 * "server closed the stream without sending content" placeholder becomes the
 * buffer) — so a real "done" phase with real, non-empty buffer text is
 * reachable here without faking the streaming transport itself.
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

/* ── Prompt history ──────────────────────────────────────────────────────── */

await check("Up recalls the previous prompt, most recent first", async () => {
  const page = await open();
  await submit(page, "first prompt");
  await submit(page, "second prompt");
  await page.locator("#prompt").click();
  await page.locator("#prompt").press("ArrowUp");
  const first = await page.locator("#prompt").inputValue();
  await page.locator("#prompt").press("ArrowUp");
  const second = await page.locator("#prompt").inputValue();
  await page.close();
  assert.equal(first, "second prompt");
  assert.equal(second, "first prompt");
});

await check("Up at the oldest entry holds rather than wrapping", async () => {
  const page = await open();
  await submit(page, "only prompt");
  await page.locator("#prompt").click();
  await page.locator("#prompt").press("ArrowUp");
  await page.locator("#prompt").press("ArrowUp");
  await page.locator("#prompt").press("ArrowUp");
  const value = await page.locator("#prompt").inputValue();
  await page.close();
  assert.equal(value, "only prompt", "Up past the oldest entry moved off it");
});

await check("Down past the newest entry restores the draft, not a blank field", async () => {
  const page = await open();
  await submit(page, "first prompt");
  await page.locator("#prompt").fill("half-written thought");
  await page.locator("#prompt").press("ArrowUp");
  const recalled = await page.locator("#prompt").inputValue();
  await page.locator("#prompt").press("ArrowDown");
  const restored = await page.locator("#prompt").inputValue();
  await page.close();
  assert.equal(recalled, "first prompt");
  assert.equal(restored, "half-written thought", "the draft was lost, not restored");
});

await check("typing anything breaks out of history browsing", async () => {
  const page = await open();
  await submit(page, "first prompt");
  await submit(page, "second prompt");
  await page.locator("#prompt").click();
  await page.locator("#prompt").press("ArrowUp"); // now showing "second prompt"
  await page.locator("#prompt").type("x");
  // Editing broke the browse; Up now starts a fresh recall from the newest
  // entry rather than continuing to walk from where it left off.
  await page.locator("#prompt").press("ArrowUp");
  const value = await page.locator("#prompt").inputValue();
  await page.close();
  assert.equal(value, "second prompt",
    `expected a fresh recall of the newest entry, got "${value}"`);
});

await check("an immediate repeat is not stored twice", async () => {
  const page = await open();
  await submit(page, "repeat me");
  await submit(page, "repeat me");
  await page.locator("#prompt").click();
  await page.locator("#prompt").press("ArrowUp");
  await page.locator("#prompt").press("ArrowUp");
  const value = await page.locator("#prompt").inputValue();
  await page.close();
  assert.equal(value, "repeat me", "a second Up moved past the only distinct entry");
});

await check("Up/Down inside a multi-line prompt moves the caret, not history", async () => {
  const page = await open();
  await submit(page, "earlier prompt");
  await page.locator("#prompt").click();
  await page.keyboard.type("line one");
  await page.keyboard.press("Shift+Enter");
  await page.keyboard.type("line two");
  // Caret is at the end of "line two" — Home moves it to the START of that
  // line, which is still the middle of the field's full text, not position 0.
  await page.keyboard.press("Home");
  await page.locator("#prompt").press("ArrowUp");
  const value = await page.locator("#prompt").inputValue();
  await page.close();
  assert.equal(value, "line one\nline two",
    "Up recalled history instead of moving the caret up a line");
});

/* ── Previous-answer scrollback ──────────────────────────────────────────── */

await check("nothing to fold away after only one turn", async () => {
  const page = await open();
  await submit(page, "only question");
  const hidden = await page.locator("#previous-answer").isHidden();
  await page.close();
  assert.ok(hidden, "the scrollback strip appeared with no previous turn to show");
});

await check("a second turn folds the first one into scrollback, closed by default", async () => {
  const page = await open({ chatReplies: ["the first real answer", "the second real answer"] });
  await submit(page, "first question");
  await submit(page, "second question");
  const hidden = await page.locator("#previous-answer").isHidden();
  const open_ = await page.locator("#previous-answer").getAttribute("open");
  const summary = await page.locator("#previous-answer-summary").innerText();
  await page.close();
  assert.ok(!hidden, "the previous turn was not folded in");
  assert.equal(open_, null, "the strip opened itself instead of starting closed");
  assert.match(summary, /first question/);
});

await check("opening the strip shows the first turn's actual answer, not the second's", async () => {
  const page = await open({ chatReplies: ["the first real answer", "the second real answer"] });
  await submit(page, "first question");
  await submit(page, "second question");
  await page.locator("#previous-answer-summary").click();
  const body = await page.locator("#previous-answer-body").innerText();
  const current = await page.locator("#answer").innerText();
  await page.close();
  assert.match(body, /the first real answer/);
  assert.doesNotMatch(body, /the second real answer/,
    "scrollback showed the current answer instead of the previous one");
  assert.match(current, /the second real answer/);
});

await check("dismissing the window clears the scrollback for next time", async () => {
  const page = await open();
  await submit(page, "first question");
  await submit(page, "second question");
  await page.keyboard.press("Escape"); // dismiss(): nothing streaming, no gate open
  await page.waitForTimeout(150);
  const hidden = await page.locator("#previous-answer").isHidden();
  await page.close();
  assert.ok(hidden, "scrollback survived a dismiss, and would show a stale answer next open");
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nthe composer holds");
process.exit(fails.length ? 1 : 0);
