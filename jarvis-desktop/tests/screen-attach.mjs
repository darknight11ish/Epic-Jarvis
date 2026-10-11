/**
 * "Look at this" hands the owner the picture (the owner's decision of
 * 2026-10-07; `.dsh-scratch/SCREEN-ATTACH-DESIGN.md`; look.rs, main.js,
 * JARVIS-API section 117) - the part that needs a browser.
 *
 * The Cleaner on the PC decides what that picture is: `jarvis_picture.clean`
 * has already painted every key, password, card number and Never-look window
 * SOLID BLACK, and a picture it could not verify is never handed back at all.
 * What this suite holds is the desktop half:
 * - the CLEANED picture the PC sends (`screen-captured`) becomes the
 *   attachment on the question box, with the thumbnail showing EXACTLY the
 *   bytes that will be sent and the size and shape beside it;
 * - the question then carries that same data URI as an image, and - while a
 *   look is held - the `screen: "look"` mark, so the PC adds the screen's
 *   words to that one question as outside text;
 * - the picture is that ONE question's: it is gone from the box once the
 *   question has gone, so it cannot ride on the next, unrelated one;
 * - `capture-failed` shows the PC's own plain reason in the watch strip,
 *   attaches nothing, and changes no answer on screen (it is NOT an error
 *   banner): the owner can still type their question without a picture;
 * - the wiring, read from the real Rust and JS: the key asks for the picture,
 *   only the cleaner's PNG is ever accepted (mime, signature, size cap), the
 *   reason is the PC's, and none of it is logged.
 * (tests/look.mjs drives the session itself; tests/picture.mjs drives what
 * happens when the local model cannot see a picture.)
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

let K;
try {
  // Playwright FIRST: tests/uikit.mjs exits while it loads when it is absent,
  // and no try/catch around that import can catch an exit (tests/README.md).
  await import("playwright");
  K = await import("./uikit.mjs");
} catch (e) {
  console.log(`skip  the real windows (${e.message.split("\n")[0]})`);
  process.exit(0);
}

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

let failed = 0;
let passed = 0;
const check = async (name, fn) => {
  try {
    await fn();
    passed += 1;
    console.log(`ok    ${name}`);
  } catch (e) {
    failed += 1;
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

/**
 * Waits until something observable is true in the page.
 *
 * `page.waitForTimeout` is not a test: it either wastes time or races. This is
 * the shape every check here uses - the same three arguments as the harness's
 * own waits - and it fails with the words of what it was waiting FOR, not with
 * Playwright's timeout sentence alone.
 */
const until = async (page, what, ready, timeout = 5000) => {
  try {
    await page.waitForFunction(ready, null, { timeout });
  } catch (e) {
    throw new Error(`waited ${timeout} ms for ${what}`);
  }
};

const STATUS = {
  state: "off", on: false, paused: null, pause_words: null, left_s: null, ending_soon: false,
  ended: null, ended_words: null, look_held: false, look_left_s: null, built: true,
  available: true, unavailable_why: "",
};
const HELD = { ...STATUS, look_held: true, look_left_s: 100 };
const NEVER = { entries: [], unreadable: false, last_removal: {}, pending: [] };
const delta = (text) => JSON.stringify({ choices: [{ delta: { content: text } }] });
/** A model that can see pictures, so a question with one is sent straight away. */
const SEES = { model: "qwen2.5vl:7b", vision: true, reason: "" };

/**
 * What the PC hands over: the CLEANER's own PNG, as base64, with its shape and
 * byte count. A 1x1 PNG - nothing here decodes it, and nothing in the app does
 * either.
 */
const CLEANED = {
  dataUri:
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8Dw" +
    "HwAFAAH/q842iQAAAABJRU5ErkJggg==",
  width: 1920, height: 1080, bytes: 4096, elapsedMs: 212,
};
const NO_PICTURE_WHY =
  "The picture could not be checked for passwords and keys, so it was not attached. " +
  "Nothing from it was sent. Your question can still be asked without it.";

const { base, close } = await K.serve();
const browser = await K.launch();
const bar = (extra = {}) => K.open(browser, base, "index.html",
  { chatReplies: [], screen: { status: STATUS, never: NEVER }, ...extra });
const emit = (page, name, payload) =>
  page.evaluate(([n, p]) => window.__emit(n, p), [name, payload]);
const chats = (page) => page.evaluate(() =>
  (window.__calls || []).filter((c) => c[0] === "stream_chat").map((c) => c[1]));
const chip = (page) => page.evaluate(() => {
  const el = document.getElementById("attachment-capture");
  return {
    shown: !el.hidden,
    thumb: document.getElementById("capture-thumb").getAttribute("src"),
    meta: document.getElementById("capture-meta").textContent,
    attachments: !document.getElementById("attachments").hidden,
  };
});

/* ── 1. The cleaned picture lands in the question box ────────────────────── */

await check("the PC's cleaned picture becomes the attachment, showing exactly what will be sent", async () => {
  const page = await bar({ vision: SEES, screen: { status: HELD, never: NEVER } });
  await emit(page, "screen-captured", CLEANED);
  await until(page, "the attachment chip to appear", () =>
    !document.getElementById("attachment-capture").hidden);
  const got = await chip(page);
  assert.equal(got.thumb, CLEANED.dataUri, "the thumbnail is not the bytes that will be sent");
  assert.match(got.meta, /1920x1080/);
  assert.match(got.meta, /4 KB/);
  assert.match(got.meta, /212 ms/);
  assert.equal(got.attachments, true, "the attachment row is not shown");
  assert.deepEqual(page.__errors, []);
  await page.close();
});

await check("an empty box is given the plain question; words already typed are left alone", async () => {
  const page = await bar({ vision: SEES });
  await emit(page, "screen-captured", CLEANED);
  await until(page, "the attachment chip", () =>
    !document.getElementById("attachment-capture").hidden);
  assert.equal(await page.inputValue("#prompt"), "What am I looking at?");
  await page.close();

  const kept = await bar({ vision: SEES });
  await kept.fill("#prompt", "why is this chart flat?");
  await emit(kept, "screen-captured", CLEANED);
  await until(kept, "the attachment chip", () =>
    !document.getElementById("attachment-capture").hidden);
  assert.equal(await kept.inputValue("#prompt"), "why is this chart flat?",
    "the owner's own words were replaced");
  await kept.close();
});

await check("the question carries the picture itself and the screen mark, and nothing else new", async () => {
  const page = await bar({
    vision: SEES, screen: { status: HELD, never: NEVER },
    chatReplies: [[delta("It is flat because nothing changed.")]],
  });
  await emit(page, "screen-captured", CLEANED);
  await until(page, "the attachment chip", () =>
    !document.getElementById("attachment-capture").hidden);
  await page.fill("#prompt", "why is this chart flat?");
  await page.press("#prompt", "Enter");
  await until(page, "the question to be sent", () =>
    (window.__calls || []).some((c) => c[0] === "stream_chat"));
  const sent = (await chats(page))[0];
  const newest = sent.messages[sent.messages.length - 1];
  const img = (newest.content || []).find((p) => p.type === "image_url");
  await page.close();
  assert.equal(sent.hasImage, true, "the turn was not marked as carrying a picture");
  assert.equal(newest.screen, "look", "the held look's words no longer ride on the question");
  assert.ok(img, "the picture did not ride on the question");
  assert.equal(img.image_url.url, CLEANED.dataUri, "a different picture was sent from the one shown");
  assert.equal((newest.content.find((p) => p.type === "text") || {}).text,
    "why is this chart flat?", "the owner's words were changed");
  const flat = JSON.stringify(sent);
  assert.doesNotMatch(flat, /Snorvel|words only/, "a word from the screen rode along");
});

await check("the picture is that ONE question's: it is gone from the box once the question has gone", async () => {
  const page = await bar({
    vision: SEES, screen: { status: HELD, never: NEVER },
    chatReplies: [[delta("It is flat.")], [delta("The kettle is on the left.")]],
  });
  await emit(page, "screen-captured", CLEANED);
  await until(page, "the attachment chip", () =>
    !document.getElementById("attachment-capture").hidden);
  await page.fill("#prompt", "why is this chart flat?");
  await page.press("#prompt", "Enter");
  await until(page, "the picture to leave the box", () =>
    document.getElementById("attachment-capture").hidden);
  const after = await chip(page);
  assert.equal(after.thumb, null, "the thumbnail still holds the picture");
  // The next, unrelated question must not carry it again.
  await emit(page, "screen-status", { status: STATUS, stale: false });
  await page.fill("#prompt", "where is the kettle?");
  await page.press("#prompt", "Enter");
  await until(page, "the second question to be sent", () =>
    (window.__calls || []).filter((c) => c[0] === "stream_chat").length > 1);
  const sent = (await chats(page))[1];
  await page.close();
  assert.equal(sent.hasImage, false, "the old screenshot rode on the next question");
  assert.doesNotMatch(JSON.stringify(sent), /image_url|data:image/);
});

await check("the owner can bin the picture before asking; nothing is sent and nothing stays", async () => {
  const page = await bar({ vision: SEES, screen: { status: HELD, never: NEVER } });
  await emit(page, "screen-captured", CLEANED);
  await until(page, "the attachment chip", () =>
    !document.getElementById("attachment-capture").hidden);
  await page.click("#capture-remove");
  await until(page, "the attachment to go", () =>
    document.getElementById("attachment-capture").hidden);
  assert.equal(await chip(page).then((c) => c.thumb), null);
  await page.close();
});

/* ── 2. No picture: the PC's own plain reason, and nothing attached ──────── */

await check("no picture to attach: the reason is said in the strip and no attachment appears", async () => {
  const page = await bar();
  await emit(page, "screen-look", { ok: true, note: "Looked at: Chrome window \u00b7 words only", said: "" });
  await emit(page, "capture-failed", NO_PICTURE_WHY);
  await until(page, "the reason in the watch strip",
    () => /could not be checked/.test(document.getElementById("watch-note").textContent));
  const got = await chip(page);
  const strip = await page.evaluate(() => ({
    hidden: document.getElementById("watch-strip").hidden,
    note: document.getElementById("watch-note").textContent,
    phase: document.body.dataset.phase || "",
  }));
  await page.close();
  assert.equal(got.shown, false, "a picture was attached though the PC refused one");
  assert.equal(strip.hidden, false, "the reason was not shown at all");
  assert.match(strip.note, /could not be checked/);
  // Not an error banner: the answer box and the owner's words are untouched.
  assert.notEqual(strip.phase, "error", "a missing picture was shown as an error");
});

await check("a refused look's own words are what the strip says, once", async () => {
  const page = await bar();
  const said = "There's a password box in front, so I'm not looking.";
  await emit(page, "screen-look", { ok: false, note: "", said });
  await emit(page, "capture-failed", said);
  await until(page, "the refusal", () =>
    document.getElementById("watch-note").textContent.includes("password box"));
  const note = await page.textContent("#watch-note");
  await page.close();
  assert.equal((note.match(/password box/g) || []).length, 1, `said twice: ${note}`);
});

await check("CONTROL: a picture with no data in it changes nothing at all", async () => {
  const page = await bar();
  const before = await page.innerHTML("#attachments");
  await emit(page, "screen-captured", { width: 10, height: 10, bytes: 1, elapsedMs: 1 });
  await page.waitForTimeout(120);
  const after = await page.innerHTML("#attachments");
  const errors = page.__errors;
  await page.close();
  assert.equal(after, before, "a payload with no picture changed the attachment row");
  assert.deepEqual(errors, []);
});

/* ── 3. The wiring: the key asks for it, only the cleaner's PNG is taken ─── */

const lookRs = read("src-tauri/src/look.rs");
const mainJs = read("src/main.js");

await check("the Look at this key asks the PC for the cleaned picture, in the one look it already took", () => {
  const then = lookRs.slice(lookRs.indexOf("async fn look_then_bar("));
  assert.match(then, /attach_body\(false\)/, "the look does not ask for a picture");
  assert.match(lookRs, /fn attach_body\(whole: bool\)[\s\S]{0,120}WANT_PICTURE/);
  assert.match(lookRs, /pub\(crate\) const WANT_PICTURE: &str = "picture";/);
  // One look, taken before the bar comes up - unchanged.
  assert.ok(then.indexOf("attach_body(false)") < then.indexOf("show_quickbar(app)"));
});

await check("only the PC's own cleaned PNG is ever taken: its type, its signature, its size", () => {
  const fn = lookRs.slice(lookRs.indexOf("pub(crate) fn capture_payload("),
    lookRs.indexOf("pub(crate) fn capture_why("));
  assert.match(fn, /!= Some\("image\/png"\)/, "a picture the PC did not call a PNG is taken");
  assert.match(fn, /starts_with\(PNG_SIG\)/, "the bytes are not checked to be a PNG");
  assert.match(fn, /raw\.len\(\) > MAX_ATTACH_BYTES/, "there is no size cap");
  assert.match(fn, /BASE64\.decode\(data\)\.ok\(\)\?/, "the size shown is not the real one");
  // ... and the data URI is built from the PC's own base64, unchanged.
  assert.match(fn, /format!\("data:image\/png;base64,\{data\}"\)/);
  const images = lookRs.match(/data:image\/[a-z+]+/g) || [];
  assert.deepEqual([...new Set(images)], ["data:image/png"], "another picture type is built");
});

await check("the reason shown is the PC's own, in the order the PC gives it", () => {
  const fn = lookRs.slice(lookRs.indexOf("pub(crate) fn capture_why("));
  assert.match(fn, /for key in \["picture_why", "said"\]/, "the PC's own words are not used first");
  assert.match(fn, /PICTURE_MISSING/, "a PC without the feature gets no plain sentence");
  assert.match(fn, /NO_PICTURE/);
});

await check("both events are produced here, and neither is ever logged", () => {
  const then = lookRs.slice(lookRs.indexOf("async fn look_then_bar("),
    lookRs.indexOf("/// \"Watch with me\": a question is about to start"));
  assert.match(then, /emit_quickbar\(app, crate::events::SCREEN_CAPTURED, capture\)/);
  assert.match(then, /emit_quickbar\(app, crate::events::CAPTURE_FAILED, capture_why\(&out\)\)/);
  // Sent after `screen-look`: a successful look's own handler clears the strip's
  // notice, so the other order would silently wipe this refusal.
  assert.ok(then.indexOf("SCREEN_LOOK") < then.indexOf("CAPTURE_FAILED"),
    "the refusal is sent before the look's own note, which wipes it");
  // Nothing of the picture or the reason reaches a log.
  for (const line of lookRs.split("\n").filter((l) => /eprintln!|println!|log::/.test(l))) {
    assert.doesNotMatch(line, /capture|picture|data|out\b/i, `a log line mentions the picture: ${line}`);
  }
});

await check("main.js shows the picture, shows the reason in the strip, and never as an error banner", () => {
  assert.match(mainJs, /listen\("screen-captured", \(event\) => \{[\s\S]{0,200}attachCapture\(payload\)/);
  const handler = mainJs.slice(mainJs.indexOf('listen("capture-failed"'));
  const body = handler.slice(0, handler.indexOf("\n});"));
  assert.match(body, /screenNotice\(/, "the reason is not said in the watch strip");
  assert.ok(!/showError|showProblem/.test(body), "a missing picture is shown as an error banner");
  assert.ok(!/Desktop capture failed/.test(mainJs), "the old capture-failed wording is still there");
  // The picture is one question's, cleared after the turn is built from it.
  const send = mainJs.slice(mainJs.indexOf("cloudYes,\n  };"));
  assert.match(send.slice(0, 1200), /if \(state\.capture\) \{\s*state\.capture = null;/,
    "the picture is not cleared once the question has gone");
});

await browser.close();
close();
console.log(`\nThe picture of a look: ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
