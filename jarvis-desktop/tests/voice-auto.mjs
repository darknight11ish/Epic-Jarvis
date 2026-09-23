/**
 * Automatic (VAD) listening: the #voice-auto toggle, its mutual exclusion
 * with push-to-talk, and the voice-heard event it drives - all against the
 * mock, since none of this has run against a real microphone.
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

await check("toggling #voice-auto on starts automatic listening", async () => {
  const page = await quickbar({});
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  const pressed = await page.locator("#voice-auto").getAttribute("aria-pressed");
  const micAuto = await page.locator("#mic").getAttribute("data-auto");
  const voice = await calls(page);
  await page.close();
  assert.equal(pressed, "true");
  assert.equal(micAuto, "true");
  assert.ok(voice.includes("auto-start"), JSON.stringify(voice));
});

await check("toggling it off again stops automatic listening", async () => {
  const page = await quickbar({});
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  const pressed = await page.locator("#voice-auto").getAttribute("aria-pressed");
  const micAuto = await page.locator("#mic").getAttribute("data-auto");
  const voice = await calls(page);
  await page.close();
  assert.equal(pressed, "false");
  assert.equal(micAuto, null);
  assert.deepEqual(voice, ["auto-start", "auto-stop"]);
});

await check("a failed start leaves the toggle unpressed", async () => {
  const page = await quickbar({ autoListenFails: "no microphone was found" });
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  const pressed = await page.locator("#voice-auto").getAttribute("aria-pressed");
  const micAuto = await page.locator("#mic").getAttribute("data-auto");
  await page.close();
  assert.equal(pressed, "false");
  assert.equal(micAuto, null);
});

await check("while automatic listening is on, holding #mic does not start push-to-talk", async () => {
  const page = await quickbar({});
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  await page.hover("#mic");
  await page.mouse.down();
  await page.waitForTimeout(120);
  await page.mouse.up();
  await page.waitForTimeout(100);
  const voice = await calls(page);
  await page.close();
  assert.deepEqual(voice, ["auto-start"], "push-to-talk ran while automatic listening owned the mic");
});

await check("a voice-heard event from the owner sends a real chat turn", async () => {
  const page = await quickbar({});
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  await page.evaluate((heard) => window.__emit("voice-heard", heard), K.HEARD_OWNER);
  await page.waitForTimeout(200);
  const sent = await invokes(page);
  await page.close();
  const chat = sent.find(([cmd]) => cmd === "stream_chat");
  assert.ok(chat, "no stream_chat call was made");
  assert.ok(JSON.stringify(chat[1]).includes(K.HEARD_OWNER.text));
});

await check("a voice-heard event from a stranger sends nothing", async () => {
  const page = await quickbar({});
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  await page.evaluate((heard) => window.__emit("voice-heard", heard), K.HEARD_STRANGER);
  await page.waitForTimeout(200);
  const sent = await invokes(page);
  await page.close();
  assert.ok(!sent.some(([cmd]) => cmd === "stream_chat"), "ambient speech from someone else reached the chat turn");
});

await check('"hey Jarvis." on its own (awake) sends nothing and keeps listening', async () => {
  const page = await quickbar({});
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  await page.evaluate((heard) => window.__emit("voice-heard", heard),
    { ...K.HEARD_OWNER, text: "", wakeHeard: true, awake: true, awakeSeconds: 8 });
  await page.waitForTimeout(200);
  const pressed = await page.locator("#voice-auto").getAttribute("aria-pressed");
  const sent = await invokes(page);
  await page.close();
  assert.equal(pressed, "true");
  assert.ok(!sent.some(([cmd]) => cmd === "stream_chat"), "an empty wake-only clip reached the chat");
});

await check("the toggle names the wake word, not 'automatic'", async () => {
  const page = await quickbar({});
  const title = await page.locator("#voice-auto").getAttribute("title");
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  const micTitle = await page.locator("#mic").getAttribute("title");
  await page.close();
  assert.ok(title.includes("hey Jarvis"), title);
  assert.ok(micTitle.includes("hey Jarvis"), micTitle);
});

await check("an unavailable engine turns automatic listening off and sends nothing", async () => {
  const page = await quickbar({});
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  await page.evaluate((heard) => window.__emit("voice-heard", heard), K.HEARD_UNAVAILABLE);
  await page.waitForTimeout(200);
  const pressed = await page.locator("#voice-auto").getAttribute("aria-pressed");
  const voice = await calls(page);
  const sent = await invokes(page);
  await page.close();
  assert.equal(pressed, "false", "automatic listening should have turned itself off");
  assert.ok(voice.includes("auto-stop"), JSON.stringify(voice));
  assert.ok(!sent.some(([cmd]) => cmd === "stream_chat"));
});

await check("CONTROL: no page error from any of the above", async () => {
  const page = await quickbar({});
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  await page.evaluate((heard) => window.__emit("voice-heard", heard), K.HEARD_OWNER);
  await page.waitForTimeout(200);
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(errors, [], JSON.stringify(errors));
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nautomatic listening: on, off, mutually exclusive with push-to-talk, and honest about a broken engine");
process.exit(fails.length ? 1 : 0);
