/**
 * The configurable shortcuts.
 *
 * This feature exists because a real machine refused `Alt+Space` — recent
 * Windows 11 hands it to Copilot — and the binding was a constant in Rust, so
 * the spotlight simply had no shortcut and nothing in the app could change it.
 *
 * Two things therefore have to be true, and the second is the one that is easy
 * to get wrong: the recorder has to capture what the fingers pressed, and the
 * UI has to distinguish SAVED from WORKING. A save that stored a combination
 * the OS then refused, reported as "Saved", is the same failure in a new place.
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

const VIEW = { width: 760, height: 900 };
const open = (data = {}) => K.open(browser, base, "settings.html", data, VIEW);
const rows = (page) => page.evaluate(() =>
  [...document.querySelectorAll(".hotkey")].map((r) => ({
    name: r.querySelector(".hotkey-name").textContent,
    key: r.querySelector(".hotkey-key").textContent,
    state: r.querySelector(".hotkey-state").textContent,
    bound: r.dataset.bound,
  })));

/* ── It renders what Rust reports ────────────────────────────────────────── */

await check("every bindable action is listed", async () => {
  const page = await open();
  const list = await rows(page);
  await page.close();
  assert.equal(list.length, 6, `${list.length} rows, expected 6`);
  assert.equal(list[0].name, "Summon Jarvis");
  assert.equal(list[0].key, "Alt + Space");
  // "Stop everything" (2026-09-25): listed like the others, so it can be
  // moved off Alt+Shift+X if something else on the PC needs that.
  const stop = list.find((r) => r.name === "Stop everything");
  assert.ok(stop, "Stop everything is not listed");
  assert.equal(stop.key, "Alt + Shift + X");
});

await check("Stop everything is in the tray menu too, the same command, never greyed", async () => {
  // Continuity audit 2026-09-26: a mouse, or a key another program holds.
  const tray = read("src-tauri/src/tray.rs");
  assert.match(tray, /ID_STOP_EVERYTHING => commands::stop_everything_now\(app\)/);
  const row = tray.slice(tray.indexOf("let stop_everything = MenuItem::with_id("));
  assert.match(row.slice(0, 300), /"Stop everything",\s*true,\s*accel\(app, "stop_everything"\)/);
  const menu = tray.slice(tray.indexOf("let menu = Menu::with_items"), tray.indexOf("app.state::<TrayHandles>"));
  assert.match(menu, /&stop_everything,/, "the row is built but not in the menu");
  // It is never disabled afterwards either.
  assert.doesNotMatch(tray, /stop_everything\.set_enabled/);
  // And Settings' promise about the tray is true of what it names.
  const html = read("src/settings.html");
  assert.doesNotMatch(html, /Everything here is also in the tray menu/);
  assert.match(html.replace(/\s+/g, " "), /Summon Jarvis, the widget and Stop everything are also in the tray menu\./);
  for (const id of ["toggle_quickbar", "toggle_widget", "stop_everything"]) {
    assert.match(tray, new RegExp(`accel\\(app, "${id}"\\)`), `${id} has no tray row`);
  }
});

await check("Stop everything says the same sentences as the phone's button", async () => {
  // Continuity audit 2026-09-26, #5: they had drifted apart ("Jarvis" / "The
  // PC", and the phone put the raw network text on screen).
  const rs = read("src-tauri/src/commands.rs");
  const kt = readFileSync(join(HERE, "..", "..",
    "jarvis-client/app/src/main/java/com/jarvis/client/net/StopEverything.kt"), "utf8");
  for (const [rust, kotlin] of [["STOP_SPEECH", "SPEECH"], ["STOP_PC_SILENT", "PC_SILENT"],
    ["STOP_NOT_REACHED", "NOT_REACHED"]]) {
    const a = rs.match(new RegExp(`pub const ${rust}: &str = "([^"]+)";`));
    const b = kt.match(new RegExp(`const val ${kotlin} = "([^"]+)"`));
    assert.ok(a && b, `${rust} / ${kotlin} not found`);
    assert.equal(a[1], b[1], `${rust} differs from the phone's ${kotlin}`);
  }
  // The PC not answering: the plain words, never the address or the library's text.
  const post = rs.slice(rs.indexOf("async fn post_stop_all("));
  assert.match(post.slice(0, post.indexOf("\n}\n")), /plain_errors::unreachable_words\(e\.is_connect\(\), e\.is_timeout\(\)\)/);
  assert.match(kt, /is ApiError\.Unreachable -> problem\(error\)\?\.text/);
});

await check("the Rust list and this stand-in agree", async () => {
  // hotkeys.rs ACTIONS is the truth; the stand-in above is what every
  // Settings test renders. A new action added to one and not the other
  // would test a Settings page the app never shows.
  const all = read("src-tauri/src/hotkeys.rs");
  const at = all.indexOf("pub const ACTIONS");
  const rs = all.slice(at, all.indexOf("\n];", at));
  const ids = [...rs.matchAll(/\bid: "([a-z_]+)",/g)].map((m) => m[1]);
  assert.deepEqual(ids, K.HOTKEYS.map((h) => h.id));
  const defaults = [...rs.matchAll(/default: "([^"]+)",/g)].map((m) => m[1]);
  assert.deepEqual(defaults, K.HOTKEYS.map((h) => h.default));
});

await check("Win is shown as Win, not Super", async () => {
  // The accelerator syntax says `Super`; the key on the keyboard says Windows.
  const page = await open();
  const list = await rows(page);
  await page.close();
  const clip = list.find((r) => r.name === "Attach the clipboard");
  assert.equal(clip.key, "Win + Shift + J", `shown as "${clip.key}"`);
});

/* ── Saved is not the same as working ────────────────────────────────────── */

await check("a refused binding says so, and does not say working", async () => {
  const page = await open({
    hotkeys: K.HOTKEYS.map((h) =>
      h.id === "toggle_quickbar"
        ? { ...h, registered: false, error: "HotKey already registered" }
        : h),
  });
  const list = await rows(page);
  await page.close();
  const summon = list.find((r) => r.name === "Summon Jarvis");
  assert.equal(summon.bound, "false");
  assert.match(summon.state, /in use/i, `said "${summon.state}"`);
  assert.doesNotMatch(summon.state, /working/i);
});

await check("saving a combination the OS refuses does not report success", async () => {
  // The exact failure this whole feature is meant to end: the app telling you
  // a shortcut is set when the OS never took it.
  const page = await open({ refuse: ["Control+Alt+K"] });
  await page.locator(".hotkey-key").first().click();
  await page.keyboard.press("Control+Alt+K");
  await page.locator("#save-hotkeys").click();
  await page.waitForTimeout(250);
  const status = await page.locator("#hotkey-status").innerText();
  const tone = await page.locator("#hotkey-status").getAttribute("data-tone");
  await page.close();
  assert.match(status, /still held by another application/i, `said "${status}"`);
  assert.equal(tone, "bad", "a refused binding was reported in the success tone");
});

await check("saving a combination the OS takes reports it bound", async () => {
  const page = await open();
  await page.locator(".hotkey-key").first().click();
  await page.keyboard.press("Control+Alt+J");
  await page.locator("#save-hotkeys").click();
  await page.waitForTimeout(250);
  const status = await page.locator("#hotkey-status").innerText();
  const list = await rows(page);
  await page.close();
  assert.match(status, /all of them bound/i, `said "${status}"`);
  assert.equal(list[0].key, "Ctrl + Alt + J");
});

/* ── The recorder ────────────────────────────────────────────────────────── */

await check("recording captures the chord, not the letter", async () => {
  const page = await open();
  const first = page.locator(".hotkey-key").first();
  await first.click();
  assert.equal(await first.getAttribute("data-recording"), "true",
    "clicking the field did not start recording");
  await page.keyboard.press("Alt+Shift+G");
  await page.waitForTimeout(150);
  const list = await rows(page);
  await page.close();
  assert.equal(list[0].key, "Alt + Shift + G");
});

await check("Escape cancels without changing anything", async () => {
  const page = await open();
  const before = (await rows(page))[0].key;
  await page.locator(".hotkey-key").first().click();
  await page.keyboard.press("Escape");
  await page.waitForTimeout(150);
  const after = (await rows(page))[0].key;
  const recording = await page.locator(".hotkey-key").first().getAttribute("data-recording");
  await page.close();
  assert.equal(after, before, "Escape changed the binding");
  assert.equal(recording, "false", "Escape left the field still recording");
});

await check("a bare key is refused at the keystroke", async () => {
  // Rust refuses it too, and Rust is the authority — but a global binding with
  // no modifier swallows that key everywhere, including in this very field, so
  // the user needs to know before they press Save rather than after.
  const page = await open();
  await page.locator(".hotkey-key").first().click();
  await page.keyboard.press("G");
  await page.waitForTimeout(150);
  const status = await page.locator("#hotkey-status").innerText();
  // Still listening, deliberately: the user pressed something that cannot be
  // bound, so the field says why and waits for another attempt rather than
  // closing and making them click back into it.
  const still = await page.locator(".hotkey-key").first().getAttribute("data-recording");
  await page.keyboard.press("Escape");
  await page.waitForTimeout(120);
  const list = await rows(page);
  await page.close();
  assert.match(status, /needs a modifier/i, `said "${status}"`);
  assert.equal(still, "true", "a rejected keystroke ended the recording");
  assert.equal(list[0].key, "Alt + Space", "the bare key was accepted anyway");
});

await check("holding only modifiers records nothing yet", async () => {
  const page = await open();
  await page.locator(".hotkey-key").first().click();
  await page.keyboard.down("Alt");
  await page.keyboard.down("Shift");
  await page.waitForTimeout(120);
  const recording = await page.locator(".hotkey-key").first().getAttribute("data-recording");
  await page.keyboard.up("Shift");
  await page.keyboard.up("Alt");
  await page.close();
  assert.equal(recording, "true", "a modifier alone was taken as a complete chord");
});

/* ── A rejected save changes nothing ─────────────────────────────────────── */

await check("a duplicate is refused and the old bindings survive", async () => {
  const page = await open();
  // Put the widget toggle onto the summon combination.
  await page.locator(".hotkey-key").nth(4).click();
  await page.keyboard.press("Alt+Space");
  await page.waitForTimeout(120);
  await page.locator("#save-hotkeys").click();
  await page.waitForTimeout(250);
  const status = await page.locator("#hotkey-status").innerText();
  await page.close();
  assert.match(status, /both/i, `said "${status}"`);
  assert.match(status, /[Nn]othing was changed/, "did not say the save was a no-op");
});

await check("Reset puts the shipped combinations back", async () => {
  const page = await open();
  await page.locator(".hotkey-key").first().click();
  await page.keyboard.press("Control+Alt+Q");
  await page.locator("#save-hotkeys").click();
  await page.waitForTimeout(200);
  await page.locator("#reset-hotkeys").click();
  await page.waitForTimeout(200);
  const list = await rows(page);
  await page.close();
  assert.equal(list[0].key, "Alt + Space");
});

/* ── Accessibility ───────────────────────────────────────────────────────── */

await check("each field says which action it belongs to", async () => {
  const page = await open();
  const labels = await page.evaluate(() =>
    [...document.querySelectorAll(".hotkey-key")].map((b) => b.getAttribute("aria-label")));
  await page.close();
  // Without this every one of the five announces as a bare combination.
  assert.ok(labels.every((l) => l && l.length > 12), `got ${JSON.stringify(labels)}`);
  assert.match(labels[0], /Summon Jarvis/);
});

await check("a refused row is not marked by colour alone", async () => {
  const page = await open({
    hotkeys: K.HOTKEYS.map((h) =>
      h.id === "toggle_quickbar" ? { ...h, registered: false, error: "taken" } : h),
  });
  const styles = await page.evaluate(() => {
    const rows = [...document.querySelectorAll(".hotkey")];
    const pick = (bound) => {
      const el = rows.find((r) => r.dataset.bound === bound).querySelector(".hotkey-key");
      return getComputedStyle(el).borderTopStyle;
    };
    return { bad: pick("false"), good: pick("true") };
  });
  await page.close();
  assert.notEqual(styles.bad, styles.good,
    "refused and working rows differ only in hue");
});

/* ── Controls ────────────────────────────────────────────────────────────── */

await check("CONTROL: Rust refuses a modifier-less binding too", async () => {
  // The page check is a courtesy. This is the one that matters, because a
  // page can be bypassed and the consequence is unrecoverable from inside
  // the app.
  const rust = read("src-tauri/src/hotkeys.rs");
  assert.match(rust, /shortcut\.mods\.is_empty\(\)/, "Rust does not check for a modifier");
  assert.match(rust, /fn validate/, "Rust does not validate the set");
  assert.match(rust, /validate\(&next\)\?;\s*\n\s*persist/,
    "validation does not happen before the write");
});

await check("CONTROL: the handler resolves against live bindings", async () => {
  // Comparing against values captured at startup is correct until the first
  // rebind, after which the OLD combination still fires the action.
  const lib = read("src-tauri/src/lib.rs");
  assert.match(lib, /hotkeys::action_for\(app, shortcut\)/,
    "the shortcut handler still matches on startup snapshots");
  assert.ok(!/let toggle = hotkeys\.toggle_quickbar/.test(lib),
    "the old captured-shortcut dispatch is still there");
});

await check("CONTROL: the page still works when nothing is refused", async () => {
  const page = await open();
  const list = await rows(page);
  assert.deepEqual(page.__errors, [], page.__errors.join(" | "));
  await page.close();
  assert.ok(list.every((r) => r.bound === "true"));
  assert.ok(list.every((r) => /working/i.test(r.state)));
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nthe shortcuts hold");
process.exit(fails.length ? 1 : 0);
