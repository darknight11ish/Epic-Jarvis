/**
 * Settings -> Connection: "Show a QR code for my phone's browser" (2026-11-13,
 * landed 2026-11-25).
 *
 * The owner wants to open Atlas's own web page on his phone without typing the
 * private address into the browser. The picture is drawn in Rust
 * (`browser_qr.rs`) from THAT address and nothing else, and the page is handed
 * the finished SVG plus the address it points at, so the things worth driving
 * are:
 *
 * - the control is where he looks, with exactly the words written for it;
 * - the picture appears, and the address under it is the address the code
 *   carries - no token, no key, no query string (`?w=`), never a tunnel;
 * - it counts down from 60, "Hide now" takes it off, and the minute takes it
 *   off on its own;
 * - a blank or unreachable "Let my phone reach this" address draws nothing and
 *   shows the plain sentence instead;
 * - the copy promises only what the feature does: it opens the page, it does
 *   NOT sign the browser in, and the code carries no secret.
 *
 * The Rust unit tests prove the payload and the refusals at the source
 * (`browser_qr.rs`); this drives the page against the same sentences, and pins
 * the one call that draws the picture so the page can never start building a
 * code of its own.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const flat = (text) => text.replace(/\s+/g, " ").trim();

const NOTE = "Scan this with your phone's camera. It opens Atlas in the browser at " +
  "this computer's private address. The code carries no token or key, so a photo " +
  "of it signs nothing in. It hides itself after a minute.";
const BUTTON = "Show a QR code for my phone's browser";
const TOKEN = "pairing-token-0123456789abcdef";
const URL_ONLY = "http://100.64.0.5:4719/";
const SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4 4">` +
  `<rect width="4" height="4" fill="#ffffff"/></svg>`;

// The one sentence a call with nothing to reach shows - read out of the Rust
// so the page and the PC cannot drift apart on the owner's copy.
const RUST = read("src-tauri/src/browser_qr.rs");
const refusalMatch = RUST.match(/NO_PHONE_ADDRESS: &str =\s*"((?:[^"\\]|\\[\s\S])*)"/);
assert.ok(refusalMatch, "browser_qr.rs has no NO_PHONE_ADDRESS constant");
const REFUSAL = refusalMatch[1].replace(/\\\r?\n\s*/g, "");

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const VIEW = { width: 900, height: 1600 };
const open = (data = {}) => K.open(browser, base, "settings.html", data, VIEW);

/* ── Where the control is, and its words ─────────────────────────────────── */

await check("the control is in Connection, after the phone address and before Save", async () => {
  const page = await open();
  // textContent, not innerText: the label is styled uppercase, and the words
  // in the file are the ones this pins.
  const label = await page.locator("#browser-qr .label").textContent();
  const note = await page.locator("#browser-qr .note").first().innerText();
  const order = await page.evaluate(() => {
    const ids = ["bind-address", "browser-qr", "save-connection"];
    return ids.map((id) => {
      const el = document.getElementById(id);
      return el ? [...document.querySelectorAll("body *")].indexOf(el) : -1;
    });
  });
  await page.close();
  assert.equal(label, "Open Atlas in your phone's browser", "the label's words changed");
  assert.equal(flat(note), flat(NOTE), "the note under it changed");
  assert.ok(order[0] >= 0 && order[1] >= 0 && order[2] >= 0, `a control is missing: ${order}`);
  assert.ok(order[0] < order[1] && order[1] < order[2],
    `the control is not between the phone address and Save: ${order}`);
});

/* ── The picture, and the address it carries ─────────────────────────────── */

await check("a reachable address draws the picture and shows the address it carries", async () => {
  const page = await open({
    apiSettings: { bindAddress: "100.64.0.5" },
    browserQr: { svg: SVG, url: URL_ONLY },
  });
  await page.locator("#show-browser-qr").click();
  await page.waitForTimeout(250);
  const shown = await page.locator("#browser-qr-panel").isVisible();
  const src = await page.locator("#browser-qr-image").getAttribute("src");
  const url = await page.locator("#browser-qr-url").innerText();
  const countdown = await page.locator("#browser-qr-countdown").innerText();
  const text = await page.locator("body").innerText();
  const calls = await page.evaluate(() =>
    window.__calls.filter((call) => call[0] === "browser_qr"));
  await page.close();
  assert.ok(shown, "the picture did not appear");
  assert.ok(src && src.startsWith("data:image/svg+xml;base64,"), `not a data picture: ${src}`);
  const decoded = Buffer.from(src.split(",")[1], "base64").toString("utf8");
  assert.equal(decoded, SVG, "the page did not get the SVG Rust drew");
  assert.equal(url, URL_ONLY, "the address under it is not the one the code carries");
  assert.equal(countdown, "Hides in 60s", `the countdown did not start at a minute: "${countdown}"`);
  assert.equal(calls.length, 1, "the page did not ask for the picture exactly once");
  assert.deepEqual(calls[0][1], {}, "the page passed something to browser_qr");
  // The code and the words under it are the same string: what is drawn is what
  // the owner can read, and a scan adds nothing.
  assert.ok(text.includes(URL_ONLY), "the address is not on the page");
  assert.ok(!text.includes("?w="), "the sign-in query is on the page as text");
  assert.ok(!text.includes(TOKEN), "a token is on the page as text");
  assert.ok(!text.includes("jdk1"), "a pairing key is on the page as text");
});

await check("Hide now takes the picture off the page, not just out of sight", async () => {
  const page = await open({
    apiSettings: { bindAddress: "100.64.0.5" },
    browserQr: { svg: SVG, url: URL_ONLY },
  });
  await page.locator("#show-browser-qr").click();
  await page.waitForTimeout(250);
  await page.locator("#hide-browser-qr").click();
  const hidden = await page.locator("#browser-qr-panel").isHidden();
  const src = await page.locator("#browser-qr-image").getAttribute("src");
  const url = await page.locator("#browser-qr-url").innerText();
  await page.close();
  assert.ok(hidden, "the panel is still showing");
  assert.equal(src, null, "the picture is still in the page");
  assert.equal(url, "", "the address is still in the page");
});

await check("the countdown counts down while the picture is up", async () => {
  const page = await open({
    apiSettings: { bindAddress: "100.64.0.5" },
    browserQr: { svg: SVG, url: URL_ONLY },
  });
  await page.locator("#show-browser-qr").click();
  await page.waitForTimeout(1200);
  const countdown = await page.locator("#browser-qr-countdown").innerText();
  await page.close();
  assert.match(countdown, /^Hides in (59|58)s$/, `the minute did not tick: "${countdown}"`);
});

await check("the picture takes itself off after a minute", async () => {
  const page = await open({
    apiSettings: { bindAddress: "100.64.0.5" },
    browserQr: { svg: SVG, url: URL_ONLY },
  });
  await page.clock.install();
  await page.locator("#show-browser-qr").click();
  await page.waitForTimeout(250);
  assert.ok(await page.locator("#browser-qr-panel").isVisible(), "no picture to time");
  await page.clock.pauseAt(new Date(await page.evaluate(() => Date.now() + 500)));
  for (let i = 0; i < 60; i++) {
    await page.clock.runFor(1000);
    await page.waitForTimeout(1);
  }
  const hidden = await page.locator("#browser-qr-panel").isHidden();
  const src = await page.locator("#browser-qr-image").getAttribute("src");
  await page.close();
  assert.ok(hidden, "the picture is still up after its minute");
  assert.equal(src, null, "the picture is still in the page after its minute");
});

/* ── Nothing to reach ────────────────────────────────────────────────────── */

await check("a blank phone address shows the plain sentence and draws nothing", async () => {
  // No browserQr seed: the stub gives what the Rust gives - the refusal.
  const page = await open({ apiSettings: { bindAddress: "" } });
  await page.locator("#show-browser-qr").click();
  await page.waitForTimeout(250);
  const said = await page.locator("#browser-qr-note").innerText();
  const noteShown = await page.locator("#browser-qr-note").isVisible();
  const hidden = await page.locator("#browser-qr-panel").isHidden();
  const src = await page.locator("#browser-qr-image").getAttribute("src");
  const tone = await page.locator("#browser-qr-note").getAttribute("data-tone");
  const calls = await page.evaluate(() =>
    window.__calls.filter((call) => call[0] === "browser_qr").length);
  await page.close();
  assert.ok(noteShown, "the refusal is not shown");
  assert.equal(said, REFUSAL, "the plain sentence changed");
  assert.ok(hidden, "a picture was drawn anyway");
  assert.equal(src, null, "a picture source was left in the page");
  assert.equal(tone, "bad", "the refusal is not marked as one");
  assert.equal(calls, 1, "the refusal was not asked from Rust");
});

await check("a home-network or loopback address gets the same sentence, not a code", async () => {
  for (const addr of ["127.0.0.1", "192.168.1.20", "8.8.8.8"]) {
    const page = await open({
      apiSettings: { bindAddress: addr },
      browserQr: { throws: REFUSAL },
    });
    await page.locator("#show-browser-qr").click();
    await page.waitForTimeout(150);
    const said = await page.locator("#browser-qr-note").innerText();
    const hidden = await page.locator("#browser-qr-panel").isHidden();
    const src = await page.locator("#browser-qr-image").getAttribute("src");
    await page.close();
    assert.equal(said, REFUSAL, `${addr} got its own words`);
    assert.ok(hidden, `${addr} drew a picture`);
    assert.equal(src, null, `${addr} left a picture source in the page`);
  }
});

/* ── The copy says only what the feature does ────────────────────────────── */

await check("the copy promises no sign-in and no secret", async () => {
  const html = read("src/settings.html");
  const block = html.slice(html.indexOf('id="browser-qr"'), html.indexOf('id="save-connection"'));
  const words = flat(block.replace(/<[^>]+>/g, " "));
  // The old wording promised "already signed in" and called the code "as
  // powerful as your token". Neither is true of a QR of a private address, and
  // the recorded decision says so.
  assert.doesNotMatch(words, /already signed in|signs you in|as powerful|do not photograph/i,
    "the copy still promises a sign-in, or warns about a secret the code does not carry");
  assert.match(words, /carries no token or key/, "the copy does not say the code carries no secret");
  assert.match(words, /pair this browser/, "the copy does not say a browser may need pairing");
});

/* ── Controls: what the page and the PC must never do ────────────────────── */

await check("CONTROL: the page asks browser_qr with nothing, and builds no code itself", async () => {
  const js = read("src/settings.js");
  assert.match(js, /await invoke\("browser_qr"\)/, "the page does not ask browser_qr");
  assert.doesNotMatch(js, /invoke\("browser_qr",/, "the page passes arguments to browser_qr");
  const html = read("src/settings.html");
  const block = html.slice(html.indexOf('id="browser-qr"'), html.indexOf('id="save-connection"'));
  assert.doesNotMatch(block, /\?token=|\?w=|token=|jdk1|key=/, "the control's own markup carries a token or key");
  // The picture is made in Rust and crosses as SVG; the page never builds it.
  assert.match(js, /data:image\/svg\+xml;base64,\$\{btoa\(answer\.svg\)\}/,
    "the page no longer turns Rust's SVG into the picture");
  // Nothing about the answer may be written to the console - a key or token in
  // a log is the same leak as one on screen (CLAUDE.md rule 3).
  assert.doesNotMatch(js, /console\.\w+\([^)]*answer/,
    "the page logs the answer it was handed");
});

await check("CONTROL: Rust draws from ONE address string, returns only svg + url, logs nothing", async () => {
  assert.doesNotMatch(RUST, /\bprintln!|\beprintln!/, "the command logs");
  assert.match(RUST, /pub fn browser_qr\(app: AppHandle\)/, "the command now takes arguments from the page");
  assert.match(RUST, /"svg": answer\.svg/, "the answer no longer carries the picture");
  assert.match(RUST, /"url": answer\.url/, "the answer no longer carries the address");
  assert.doesNotMatch(RUST, /token"\s*:/, "the answer carries a token key");
  assert.doesNotMatch(RUST, /jarvis_token_for/, "the command reads the token");
  // The ONE place the picture's text is built is the address itself.
  assert.match(RUST, /qr_svg\(&browser_link\(bind, port\)\)/,
    "the picture is no longer drawn from the one link builder");
  assert.match(RUST, /fn browser_link\(bind: &str, port: u16\) -> String \{\s*browser_url\(bind, port\)/,
    "the link builder adds something to the address");
  assert.doesNotMatch(RUST, /fn browser_link\([^)]*key/, "the link builder takes a key");
  assert.doesNotMatch(RUST, /\?w=/, "the link carries a sign-in query");
  assert.doesNotMatch(RUST, /browser_key/, "a key producer is back");
});

await check("CONTROL: registered once, and granted to Settings and the HUD", async () => {
  const lib = read("src-tauri/src/lib.rs");
  const build = read("src-tauri/build.rs");
  const surfaces = read("src-tauri/permissions/surfaces.toml");
  assert.match(lib, /browser_qr::browser_qr,/, "not registered in lib.rs");
  assert.match(build, /"browser_qr",/, "build.rs exports no permission for it");
  assert.ok(read("src-tauri/permissions/autogenerated/browser_qr.toml").includes("browser_qr"),
    "no generated permission file");
  const sets = surfaces.split("[[set]]").slice(1);
  const holders = sets.filter((set) => set.includes('"allow-browser-qr"'))
    .map((set) => set.match(/identifier = "([^"]+)"/)[1]);
  assert.deepEqual(holders, ["settings-surface", "hud-browser-qr"],
    `browser_qr is granted to ${JSON.stringify(holders)}`);
  assert.match(read("src-tauri/capabilities/hud.json"), /"hud-browser-qr"/,
    "the HUD capability does not grant it");
  assert.match(read("src-tauri/capabilities/settings.json"), /"settings-surface"/,
    "the settings capability does not grant settings-surface");
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nThe phone-browser QR control holds");
process.exit(fails.length ? 1 : 0);
