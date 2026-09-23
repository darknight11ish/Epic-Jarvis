/**
 * A screen capture, and a local model that cannot see it.
 *
 * Alt+Shift+S attaches a picture. The backend keeps any turn with a picture
 * on this machine (jarvis_router.choose, gate "image"), and the local model
 * today (qwen3:8b) reads text only - sent a picture, it answers as if there
 * were none. So the quickbar asks first (vision.rs, `local_model_vision`)
 * and, unless the answer is a clear yes, sends nothing until the owner
 * chooses. These check the choosing, not the Rust (see tests/README.md).
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

const CAPTURE = {
  // Nothing here decodes the image, so any data URI will do.
  dataUri: "data:image/gif;base64,R0lGODlhAQABAAAAACw=",
  width: 1, height: 1, bytes: 634, elapsedMs: 12,
};

async function withCapture(data, text = "What am I looking at?") {
  const page = await K.open(browser, base, "index.html", data);
  await page.evaluate((payload) => window.__emit("screen-captured", payload), CAPTURE);
  await page.waitForTimeout(100);
  await page.fill("#prompt", text);
  await page.press("#prompt", "Enter");
  await page.waitForTimeout(300);
  return page;
}
const chats = (page) => page.evaluate(() =>
  window.__calls.filter(([c]) => c === "stream_chat").map(([, a]) => a));

await check("a text-only model: nothing is sent, and the notice says why in plain words", async () => {
  const page = await withCapture({});
  const sent = await chats(page);
  const out = await page.evaluate(() => ({
    notice: !document.getElementById("picture-notice").hidden,
    text: document.getElementById("picture-notice-text").textContent,
    anyway: !document.getElementById("picture-anyway").hidden,
    prompt: document.getElementById("prompt").value,
    capture: !document.getElementById("attachment-capture").hidden,
    asked: window.__calls.some(([c]) => c === "local_model_vision"),
  }));
  await page.close();
  assert.equal(out.asked, true, "the model was never asked whether it can see pictures");
  assert.equal(sent.length, 0, "the picture was sent to a model that cannot see it");
  assert.equal(out.notice, true);
  assert.match(out.text, /can't see pictures/);
  assert.match(out.text, /qwen3:8b/);
  assert.match(out.text, /qwen2\.5vl/);
  assert.match(out.text, /second graphics card/);
  assert.match(out.text, /never sent to an online model/);
  assert.equal(out.anyway, false, "no 'send it anyway' to a model known not to see pictures");
  assert.equal(out.prompt, "What am I looking at?", "the owner's words were lost");
  assert.equal(out.capture, true, "the picture was dropped without being asked");
});

await check("Send without the picture: the words go, as plain text, with no image", async () => {
  const page = await withCapture({});
  await page.locator("#picture-text-only").click();
  await page.waitForTimeout(300);
  const sent = await chats(page);
  const out = await page.evaluate(() => ({
    notice: !document.getElementById("picture-notice").hidden,
    capture: !document.getElementById("attachment-capture").hidden,
  }));
  await page.close();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].hasImage, false);
  assert.equal(sent[0].messages.at(-1).content, "What am I looking at?");
  assert.doesNotMatch(JSON.stringify(sent[0]), /image_url|data:image/);
  assert.equal(out.notice, false);
  assert.equal(out.capture, false);
});

await check("Not now: nothing is sent, the picture and the words stay", async () => {
  const page = await withCapture({});
  await page.locator("#picture-keep").click();
  await page.waitForTimeout(200);
  const sent = await chats(page);
  const out = await page.evaluate(() => ({
    notice: !document.getElementById("picture-notice").hidden,
    capture: !document.getElementById("attachment-capture").hidden,
    prompt: document.getElementById("prompt").value,
  }));
  await page.close();
  assert.equal(sent.length, 0);
  assert.equal(out.notice, false);
  assert.equal(out.capture, true);
  assert.equal(out.prompt, "What am I looking at?");
});

await check("could not tell: says so, and Send it anyway sends the picture once", async () => {
  const page = await withCapture({ vision: { model: "jarvis-primary", vision: null,
    reason: "This version of Ollama does not say whether jarvis-primary can see pictures." } });
  const text = await page.locator("#picture-notice-text").textContent();
  const anywayHidden = await page.locator("#picture-anyway").isHidden();
  await page.locator("#picture-anyway").click();
  await page.waitForTimeout(300);
  const sent = await chats(page);
  await page.close();
  assert.match(text, /could not check/);
  assert.equal(anywayHidden, false);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].hasImage, true);
  assert.match(JSON.stringify(sent[0].messages.at(-1).content), /image_url/);
});

await check("a model that can see pictures: sent straight away, no notice", async () => {
  const page = await withCapture({ vision: { model: "qwen2.5vl:7b", vision: true, reason: "" } });
  const sent = await chats(page);
  const noticeHidden = await page.locator("#picture-notice").isHidden();
  const errors = page.__errors;
  await page.close();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].hasImage, true);
  assert.equal(noticeHidden, true);
  assert.deepEqual(errors, []);
});

await check("CONTROL: with no picture, nothing is asked and the turn just goes", async () => {
  const page = await K.open(browser, base, "index.html", {});
  await page.fill("#prompt", "hello");
  await page.press("#prompt", "Enter");
  await page.waitForTimeout(300);
  const calls = await page.evaluate(() => window.__calls.map(([c]) => c));
  await page.close();
  assert.ok(!calls.includes("local_model_vision"));
  assert.ok(calls.includes("stream_chat"));
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\na picture goes only to a model that can see it");
process.exit(fails.length ? 1 : 0);
