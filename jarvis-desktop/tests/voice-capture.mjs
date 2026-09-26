/**
 * Push-to-talk on the quickbar: hold #mic, release, and either a real chat
 * turn gets sent or nothing does - never something in between (sending a
 * clip nobody asked to be sent, or answering as if a stranger's voice was
 * the owner's).
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
const calls = (page) => page.evaluate(() => window.__voiceCalls || []);
const invokes = (page) => page.evaluate(() => window.__calls || []);

async function holdAndRelease(page) {
  await page.hover("#mic");
  await page.mouse.down();
  await page.waitForTimeout(120);
  await page.mouse.up();
  await page.waitForTimeout(200);
}

await check("holding #mic starts capture, releasing stops and sends it", async () => {
  const page = await quickbar({ heard: K.HEARD_OWNER });
  await holdAndRelease(page);
  const voice = await calls(page);
  const sent = await invokes(page);
  await page.close();
  assert.deepEqual(voice.slice(0, 2), ["start", "stop"], JSON.stringify(voice));
  const chat = sent.find(([cmd]) => cmd === "stream_chat");
  assert.ok(chat, "no stream_chat call was made");
  assert.ok(JSON.stringify(chat[1]).includes(K.HEARD_OWNER.text),
    `the transcribed text never reached stream_chat: ${JSON.stringify(chat[1])}`);
});

await check("a voice not recognised as the owner sends nothing", async () => {
  const page = await quickbar({ heard: K.HEARD_STRANGER });
  await holdAndRelease(page);
  const sent = await invokes(page);
  await page.close();
  assert.ok(!sent.some(([cmd]) => cmd === "stream_chat"),
    "a stranger's voice reached the chat turn");
});

await check("an unavailable engine sends nothing", async () => {
  const page = await quickbar({ heard: K.HEARD_UNAVAILABLE });
  await holdAndRelease(page);
  const sent = await invokes(page);
  await page.close();
  assert.ok(!sent.some(([cmd]) => cmd === "stream_chat"),
    "an unavailable-engine reply still reached the chat turn");
});

await check("releasing the pointer outside the button cancels, never sends", async () => {
  const page = await quickbar({ heard: K.HEARD_OWNER });
  await page.hover("#mic");
  await page.mouse.down();
  await page.waitForTimeout(80);
  // Move away and release off the control - pointerleave, not pointerup on it.
  await page.mouse.move(5, 5);
  await page.waitForTimeout(150);
  await page.mouse.up();
  const voice = await calls(page);
  const sent = await invokes(page);
  await page.close();
  assert.ok(voice.includes("cancel"), JSON.stringify(voice));
  assert.ok(!voice.includes("stop"), "stop_voice_capture ran after the pointer left the button");
  assert.ok(!sent.some(([cmd]) => cmd === "stream_chat"), "a cancelled clip still got sent");
});

await check("a failed start leaves the button unpressed and sends nothing", async () => {
  const page = await quickbar({ captureFails: "no microphone was found" });
  await page.hover("#mic");
  await page.mouse.down();
  await page.waitForTimeout(150);
  const pressed = await page.locator("#mic").getAttribute("aria-pressed");
  await page.mouse.up();
  await page.waitForTimeout(100);
  const sent = await invokes(page);
  await page.close();
  assert.equal(pressed, "false", "the mic button looked armed after start_voice_capture failed");
  assert.ok(!sent.some(([cmd]) => cmd === "stream_chat"));
});

await check("a voice turn's reply is spoken; a typed turn's reply is not", async () => {
  const page = await quickbar({
    heard: K.HEARD_OWNER,
    chatReplies: [JSON.stringify({ choices: [{ delta: { content: "hello" } }] })],
  });
  await holdAndRelease(page);
  await page.waitForTimeout(400); // let finishStream and speak_reply settle
  const afterVoice = await calls(page);
  await page.close();
  assert.ok(afterVoice.some((c) => Array.isArray(c) && c[0] === "speak"),
    `a voice-initiated reply was never spoken: ${JSON.stringify(afterVoice)}`);

  const page2 = await quickbar({
    chatReplies: [JSON.stringify({ choices: [{ delta: { content: "hello" } }] })],
  });
  await page2.fill("#prompt", "typed, not spoken");
  await page2.press("#prompt", "Enter");
  await page2.waitForTimeout(400);
  const afterTyped = await calls(page2);
  await page2.close();
  assert.ok(!afterTyped.some((c) => Array.isArray(c) && c[0] === "speak"),
    `a TYPED reply was spoken anyway: ${JSON.stringify(afterTyped)}`);
});

await check("the HUD's mic (voice-summon) focuses #mic and says how, but records nothing", async () => {
  const page = await quickbar({ heard: K.HEARD_OWNER });
  await page.evaluate(() => window.__emit("voice-summon", null));
  await page.waitForTimeout(150);
  const out = await page.evaluate(() => ({
    focused: document.activeElement && document.activeElement.id,
    placeholder: document.getElementById("prompt").getAttribute("placeholder"),
  }));
  const voice = await calls(page);
  // And the hold still works from there, the ordinary way.
  await page.keyboard.down(" ");
  await page.waitForTimeout(100);
  await page.keyboard.up(" ");
  await page.waitForTimeout(250);
  const afterHold = await calls(page);
  await page.close();
  assert.equal(out.focused, "mic");
  assert.match(out.placeholder, /Hold the mic/);
  assert.deepEqual(voice, [], `summoning opened the microphone: ${JSON.stringify(voice)}`);
  assert.deepEqual(afterHold.slice(0, 2), ["start", "stop"], JSON.stringify(afterHold));
});

await check("CONTROL: no page error from any of the above", async () => {
  const page = await quickbar({ heard: K.HEARD_OWNER });
  await holdAndRelease(page);
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(errors, [], JSON.stringify(errors));
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\npush-to-talk: hold, release, and either a real turn or nothing");
process.exit(fails.length ? 1 : 0);
