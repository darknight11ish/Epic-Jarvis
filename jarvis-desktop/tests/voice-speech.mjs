/**
 * Sentence-streaming TTS and barge-in: a voice-initiated reply is spoken
 * sentence by sentence rather than only once the whole thing has streamed
 * in, markdown is not read aloud literally, a typed reply stays silent, and
 * starting to talk again - on either listening mode - stops whatever is
 * still queued or playing.
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

const quickbar = (data) => K.open(browser, base, "index.html", data);
/** A real streamed chunk is JSON, not a bare string - `consumeLine` trims
 *  the raw SSE line, which would eat a bare string's own leading/trailing
 *  whitespace at a chunk boundary, but a JSON string's internal whitespace
 *  survives that trim untouched, same as it would from a real model. */
const delta = (text) => JSON.stringify({ choices: [{ delta: { content: text } }] });
const speakCalls = (page) => page.evaluate(() =>
  (window.__voiceCalls || []).filter((c) => Array.isArray(c) && c[0] === "speak").map((c) => c[1]));

async function holdAndRelease(page) {
  await page.hover("#mic");
  await page.mouse.down();
  await page.waitForTimeout(80);
  await page.mouse.up();
}

await check("a multi-sentence voice reply is spoken sentence by sentence, in order", async () => {
  const page = await quickbar({
    heard: K.HEARD_OWNER,
    chatReplies: [[delta("First sentence. "), delta("Second sentence. "), delta("Third, no trailing space")]],
  });
  await holdAndRelease(page);
  await page.waitForTimeout(500);
  const spoken = await speakCalls(page);
  await page.close();
  assert.deepEqual(spoken, ["First sentence.", "Second sentence.", "Third, no trailing space"],
    JSON.stringify(spoken));
});

await check("markdown is stripped before it reaches speech", async () => {
  const page = await quickbar({
    heard: K.HEARD_OWNER,
    chatReplies: [[delta("**Bold** and `code` and a [link](https://example.com). ")]],
  });
  await holdAndRelease(page);
  await page.waitForTimeout(400);
  const spoken = await speakCalls(page);
  await page.close();
  assert.deepEqual(spoken, ["Bold and code and a link."], JSON.stringify(spoken));
});

await check("a code block is dropped rather than read character by character", async () => {
  const page = await quickbar({
    heard: K.HEARD_OWNER,
    chatReplies: [[delta("Here you go: ```const x = 1;``` done. ")]],
  });
  await holdAndRelease(page);
  await page.waitForTimeout(400);
  const spoken = await speakCalls(page);
  await page.close();
  assert.equal(spoken.length, 1);
  assert.ok(!spoken[0].includes("const x"), spoken[0]);
});

await check("a typed reply, even multi-sentence, is never spoken", async () => {
  const page = await quickbar({
    chatReplies: [[delta("First. "), delta("Second. ")]],
  });
  await page.fill("#prompt", "typed, not spoken");
  await page.press("#prompt", "Enter");
  await page.waitForTimeout(400);
  const spoken = await speakCalls(page);
  await page.close();
  assert.deepEqual(spoken, []);
});

await check("CONTROL: with nothing to interrupt it, both sentences finish speaking", async () => {
  const page = await quickbar({
    heard: K.HEARD_OWNER,
    chatReplies: [[delta("One. "), delta("Two. ")]],
    speakDelayMs: 30,
  });
  await holdAndRelease(page);
  await page.waitForTimeout(600);
  const spoken = await speakCalls(page);
  await page.close();
  assert.deepEqual(spoken, ["One.", "Two."]);
});

await check("barge-in via push-to-talk stops a reply still queued or playing", async () => {
  const page = await quickbar({
    heard: K.HEARD_OWNER,
    chatReplies: [[delta("One. "), delta("Two. "), delta("Three. ")]],
    speakDelayMs: 150, // slow enough to hold "One." in flight when we interrupt
  });
  await holdAndRelease(page);
  await page.waitForTimeout(60); // "One." is now mid-flight (speak_reply called, not yet resolved)
  // Barge in: hold the mic again, as if starting a new utterance.
  await page.hover("#mic");
  await page.mouse.down();
  await page.waitForTimeout(400); // let everything that was going to happen, happen
  await page.mouse.up();
  const spoken = await speakCalls(page);
  await page.close();
  // "One." was already in flight when the barge-in landed, so it may still
  // have been spoken - the property that matters is that "Two." and
  // "Three.", still in the queue at that moment, never were.
  assert.ok(!spoken.includes("Two.") && !spoken.includes("Three."),
    `barge-in did not clear the queue: ${JSON.stringify(spoken)}`);
});

await check("barge-in via automatic listening's voice-speech-started stops a queued reply", async () => {
  const page = await quickbar({
    heard: K.HEARD_OWNER,
    chatReplies: [[delta("One. "), delta("Two. "), delta("Three. ")]],
    speakDelayMs: 150,
  });
  // Automatic mode must be on for this event to mean anything real, but the
  // event itself is what is under test here, emitted directly.
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(100);
  await page.evaluate((heard) => window.__emit("voice-heard", heard), K.HEARD_OWNER);
  await page.waitForTimeout(60);
  await page.evaluate(() => window.__emit("voice-speech-started", null));
  await page.waitForTimeout(400);
  const spoken = await speakCalls(page);
  await page.close();
  assert.ok(!spoken.includes("Two.") && !spoken.includes("Three."),
    `voice-speech-started did not clear the queue: ${JSON.stringify(spoken)}`);
});

// T1 (audit 3): "stop" used to silence only the sentence playing at that
// moment. The tests above queue every sentence BEFORE the barge-in, so they
// passed while the real case - the answer still streaming when the owner
// says "stop" - kept talking: the next sentence, and the tail, queued
// themselves again a moment later. These keep the stream open across the
// stop with a run of empty chunks (each one a real event-loop tick).
const filler = (n) => Array.from({ length: n }, () => delta(""));
const recordPlays = (page) => page.evaluate(() => {
  window.__played = 0;
  const play = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function (...args) {
    window.__played += 1;
    return play.apply(this, args);
  };
});

await check("\"stop\" while the answer is still streaming silences the REST of it, tail included", async () => {
  const page = await quickbar({
    heard: K.HEARD_OWNER,
    chatReplies: [[delta("One. "), ...filler(300), delta("Two. "), delta("Three, the tail")]],
    speakDelayMs: 20,
  });
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(100);
  await page.evaluate((heard) => window.__emit("voice-heard", heard), K.HEARD_OWNER);
  await page.waitForTimeout(80);
  const before = await speakCalls(page);
  const streaming = await page.evaluate(() => !document.querySelector("#stop").hidden);
  await page.evaluate(() => window.__emit("voice-speech-started", null));
  await page.waitForTimeout(2000);
  const spoken = await speakCalls(page);
  await page.close();
  assert.deepEqual(before, ["One."], `the scenario did not start speaking: ${JSON.stringify(before)}`);
  assert.ok(streaming, "the stream had already ended before the stop - this proves nothing");
  assert.deepEqual(spoken, ["One."], `sentences after "stop" were still spoken: ${JSON.stringify(spoken)}`);
});

await check("a clip still being made when \"stop\" lands is dropped, not played", async () => {
  const page = await quickbar({
    heard: K.HEARD_OWNER,
    chatReplies: [[delta("One. ")]],
    speakDelayMs: 250, // "One." is still at the backend when the stop arrives
  });
  await recordPlays(page);
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(100);
  await page.evaluate((heard) => window.__emit("voice-heard", heard), K.HEARD_OWNER);
  await page.waitForTimeout(60);
  const asked = await speakCalls(page);
  await page.evaluate(() => window.__emit("voice-speech-started", null));
  await page.waitForTimeout(600);
  const played = await page.evaluate(() => window.__played);
  await page.close();
  assert.deepEqual(asked, ["One."], "speak_reply was not in flight when the stop landed");
  assert.equal(played, 0, "the clip that came back after \"stop\" was played anyway");
});

await check("push-to-talk barge-in mutes the old answer even while it is still streaming", async () => {
  const page = await quickbar({
    heard: K.HEARD_OWNER,
    chatReplies: [[delta("One. "), ...filler(300), delta("Two. "), delta("Three, the tail")]],
    speakDelayMs: 20,
  });
  await holdAndRelease(page);
  await page.waitForTimeout(60);
  await page.hover("#mic");
  await page.mouse.down(); // barge in: hold the mic again
  await page.waitForTimeout(80);
  await page.mouse.up(); // the new question is refused while the old answer streams
  await page.waitForTimeout(2000);
  const spoken = await speakCalls(page);
  await page.close();
  assert.ok(!spoken.includes("Two.") && !spoken.includes("Three, the tail"),
    `the old answer kept talking after the barge-in: ${JSON.stringify(spoken)}`);
});

await check("CONTROL: after a \"stop\", the NEXT voice question is answered out loud again", async () => {
  const page = await quickbar({
    heard: K.HEARD_OWNER,
    chatReplies: [[delta("One. "), delta("Two. ")], [delta("Next answer. ")]],
    speakDelayMs: 20,
  });
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(100);
  await page.evaluate((heard) => window.__emit("voice-heard", heard), K.HEARD_OWNER);
  await page.waitForTimeout(10);
  await page.evaluate(() => window.__emit("voice-speech-started", null));
  await page.waitForTimeout(500);
  await page.evaluate((heard) => window.__emit("voice-heard", heard), K.HEARD_OWNER);
  await page.waitForTimeout(500);
  const spoken = await speakCalls(page);
  await page.close();
  assert.ok(spoken.includes("Next answer."), `the next turn stayed muted: ${JSON.stringify(spoken)}`);
});

await check("CONTROL: no page error from any of the above", async () => {
  const page = await quickbar({ heard: K.HEARD_OWNER, chatReplies: [[delta("Fine. ")]] });
  await holdAndRelease(page);
  await page.waitForTimeout(300);
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(errors, [], JSON.stringify(errors));
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nsentence by sentence, cleaned up, and interruptible");
process.exit(fails.length ? 1 : 0);
