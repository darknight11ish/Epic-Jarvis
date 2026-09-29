/**
 * The windowless browser (Obscura) setting on this PC (the owner's decision of
 * 2026-09-29; browser-engine-rules.js, browser-engine.js, browser_engine.rs,
 * settings.html; backend jarvis_browser_engine.py and jarvis_obscura.py).
 *
 * Part 1 holds browser-engine-rules.js to the table both apps share
 * (tests/fixtures/browser-engine-cases.json, written by
 * tools/gen_browser_cases.py from backend/jarvis_browser_engine.py; the
 * phone's BrowserEngineTest reads the same file). Part 2 reads the Rust and the
 * pages for the wiring, and for what must NOT be there: no proxy, no address
 * field, nothing that runs a browser or shows a word from a web page. No
 * browser is needed for either.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as R from "../src/browser-engine-rules.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const T = JSON.parse(read("tests/fixtures/browser-engine-cases.json"));

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

/* ── 1. The shared table ─────────────────────────────────────────────── */

await check("the fixed words are the PC's", () => {
  const w = T.words;
  assert.equal(R.BROWSER.title, w.title);
  assert.equal(R.BROWSER.detail, w.detail);
  assert.equal(R.BROWSER.switch, w.switch);
  assert.equal(R.BROWSER.modeTitle, w.mode_title);
  assert.equal(R.BROWSER.stealth, w.stealth);
  assert.equal(R.BROWSER.offLine, w.off_line);
  assert.equal(R.BROWSER.waitingLine, w.waiting_line);
  assert.equal(R.BROWSER.unread, w.unread);
  assert.equal(R.BROWSER.missing, w.missing);
  assert.equal(R.BROWSER.stepsTitle, w.steps_title);
  assert.equal(R.BROWSER.stepsNote, w.steps_note);
  assert.deepEqual(R.MODE_IDS, T.modes);
  for (const id of T.modes) {
    assert.equal(R.BROWSER.modes[id], w.modes[id], id);
    assert.equal(R.BROWSER.modeHelp[id], w.mode_help[id], id);
  }
  assert.equal(T.default_mode, "auto");
});

await check(`all ${T.panels.length} settings cases match the PC's rule`, () => {
  for (const c of T.panels) {
    const got = R.browserView(c.payload);
    assert.equal(got.available, c.want.available, c.name);
    assert.equal(got.obscura, c.want.obscura, c.name);
    assert.equal(got.waiting, c.want.waiting, c.name);
    assert.equal(got.checked, c.want.checked, c.name);
    assert.equal(got.mode, c.want.mode, c.name);
    assert.equal(got.line, c.want.line, c.name);
    assert.equal(got.status, c.want.status, c.name);
    assert.equal(got.installLine, c.want.install_line, c.name);
  }
});

await check("the words are honest: it pretends to be Chrome, can still be blocked, never signs in or solves a captcha, off is instant", () => {
  assert.match(R.BROWSER.stealth, /ordinary Chrome/);
  assert.match(R.BROWSER.stealth, /does not stop a site from blocking it/i);
  assert.match(R.BROWSER.stealth, /closing an account you sign in to/i);
  assert.match(R.BROWSER.stealth, /never types a password/i);
  assert.match(R.BROWSER.stealth, /never solves a captcha/i);
  assert.doesNotMatch(R.BROWSER.stealth, /never signs in/i);
  assert.match(R.BROWSER.stealth, /may not be spotted/i);
  assert.match(R.BROWSER.stepsNote, /does not run the program/i);
  assert.match(R.BROWSER.detail, /off until you turn it on/);
  assert.match(R.BROWSER.detail, /asks first/i);
  assert.match(R.BROWSER.detail, /outside text/i);
  assert.match(R.BROWSER.detail, /no proxy/i);
  assert.match(R.BROWSER.stepsNote, /never downloads it by itself/i);
  assert.match(R.BROWSER.askedCard, /stays off until you say yes/i);
});

await check("one name everywhere: the windowless browser and the visible browser, never 'headless' in the words", () => {
  const all = JSON.stringify(R.BROWSER).toLowerCase();
  assert.ok(!all.includes("headless browser"), "no 'headless browser' in the words");
  assert.equal(R.BROWSER.title, "Browser without a window (Obscura)");
  assert.equal(R.BROWSER.switch, "Let Jarvis use the windowless browser (Obscura)");
  assert.equal(R.BROWSER.modes.headless, "The windowless browser when it can run");
  assert.equal(R.BROWSER.waitingLink, "Waiting for the connection to your PC.");
  assert.equal(R.BROWSER.modeNote, "This does nothing until the switch above is on.");
});

await check("the page shows the reason on screen, the install steps only while not installed, and plain words for a failure", () => {
  const src = read("src/browser-engine.js");
  assert.match(src, /el\.linkNote\.textContent = held \? BROWSER\.waitingLink/);
  assert.match(src, /view\.needsInstall/);
  assert.match(src, /BROWSER\.couldNotTurnOn \+ refusedWords\(error\)/);
  assert.match(src, /\^HTTP 404/);
  const html = read("src/settings.html");
  const start = html.indexOf('id="browser-engine"');
  const card = html.slice(start, html.indexOf("</section>", start));
  assert.ok(card.includes('<textarea id="be-line-text"'), "the install line is a wrapped box");
  assert.ok(card.indexOf('id="be-install"') < card.indexOf('id="be-mode"'), "the steps sit under the switch, above the picker");
  assert.ok(card.includes('id="be-mode-note"'), "a note beside the picker");
});

await check("a failed read never shows the switch as OFF: it is shown as unknown (indeterminate) and cannot be pressed", () => {
  const src = read("src/browser-engine.js");
  const start = src.indexOf("} catch (error) {\n    // Either an older backend");
  const end = src.indexOf("el.body.hidden = false;\n  paint();");
  assert.ok(start > 0 && end > start, "the read's error branch is there");
  const branch = src.slice(start, end);
  assert.match(branch, /el\.sw\.indeterminate = true/);
  assert.match(branch, /el\.sw\.disabled = true/);
  assert.match(branch, /el\.mode\.disabled = true/);
  assert.doesNotMatch(branch, /el\.sw\.checked = false/);
  assert.match(src, /el\.sw\.indeterminate = false;\n\s+el\.sw\.checked = view\.checked;/);
});

/* ── 2. Wiring, and what must not be there ───────────────────────────── */

await check("the command is wired: registered, permitted, and only Settings holds it", () => {
  const lib = read("src-tauri/src/lib.rs");
  const build = read("src-tauri/build.rs");
  assert.ok(lib.includes("browser_engine::browser_engine,"), "lib.rs registers it");
  assert.ok(build.includes('"browser_engine",'), "build.rs lists it");
  const file = read("src-tauri/permissions/autogenerated/browser_engine.toml");
  assert.ok(file.includes("allow-browser-engine"), "permission file");
  assert.match(read("src-tauri/permissions/surfaces.toml"), /identifier = "browser-engine"[\s\S]*?"allow-browser-engine"/);
  const settings = JSON.parse(read("src-tauri/capabilities/settings.json"));
  assert.ok(settings.permissions.includes("browser-engine"));
  for (const f of ["quickbar", "watch-badge", "floating", "hud", "brain"]) {
    const cap = JSON.parse(read(`src-tauri/capabilities/${f}.json`));
    assert.ok(!cap.permissions.includes("browser-engine"), `${f} must not hold the headless browser's switch`);
  }
});

await check("turning it on and picking a mode are held on a stale link; turning it off never is", () => {
  const rs = read("src-tauri/src/browser_engine.rs");
  const body = rs.slice(rs.indexOf("pub async fn browser_engine("));
  assert.match(body.slice(0, 600), /\(action == "on" \|\| action == "mode"\) && look::stale\(&app\)/);
  assert.ok(!/action == "off" && look::stale/.test(body.slice(0, 900)), "OFF must never be held");
  assert.match(rs, /"on" => serde_json::json!\(\{ "obscura": true \}\)/);
  const js = read("src/browser-engine.js");
  assert.match(js, /action: on \? "on" : "off"/);
  assert.match(js, /action: "mode", mode/);
});

await check("no proxy, no address, no picture, no page: the page and the command carry only a switch and a mode", () => {
  for (const f of ["src/browser-engine.js", "src/browser-engine-rules.js", "src-tauri/src/browser_engine.rs"]) {
    const src = read(f).split("#[cfg(test)]")[0].replace(/\/\/!.*|\/\*[\s\S]*?\*\//g, "");
    assert.ok(!/\bproxy\b|--proxy|OBSCURA_|allow-private|storage-dir/i.test(src.replace(/no proxy/gi, "")), `${f} mentions a proxy or a flag`);
    assert.ok(!/base64|data:image|<img|canvas|innerHTML/i.test(src), `${f} handles a picture or markup`);
  }
  const html = read("src/settings.html");
  const start = html.indexOf('id="browser-engine"');
  const card = html.slice(start, html.indexOf("</section>", start));
  assert.ok(card.includes('id="be-switch"') && card.includes('id="be-mode"') && card.includes('id="be-line-text"'), "markup");
  assert.ok(!/type="(text|url|password)"(?![^>]*readonly)/.test(card), "the card has an editable text box");
  assert.ok(!/proxy|address/i.test(card.replace(/<!--[\s\S]*?-->/g, "").replace(/never downloads|Every page/gi, "")), "the card has a proxy or address field");
  assert.ok(html.includes('src="browser-engine.js"'), "the page loads the script");
  assert.ok(html.includes('href="#browser-engine"'), "the jump list has it");
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
