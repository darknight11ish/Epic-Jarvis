/**
 * Desktop and phone, saying and doing the same things.
 *
 * The desktop was brought into line with the phone (jarvis-client) on
 * 2026-09-23: the phone's three themes under the phone's names, Ember gone
 * with anyone on it landing on Reactor, "Follow the system", text size and the
 * face settings in Settings, one set of words for the state of the link, and
 * the approval cards saying why they are grey. This holds each of those.
 *
 * The first half needs no browser: it imports the shared modules and reads
 * the phone's own Themes.kt, so a renamed theme on either side fails here.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const link = await import("../src/jarvis-link.js");
const tuning = await import("../src/face-tuning.js");

/* ── Themes ──────────────────────────────────────────────────────────────── */

await check("the desktop ships the phone's three themes, and Ember is gone", async () => {
  assert.deepEqual(link.THEMES, ["deep-space", "paper", "high-contrast"]);
  const rust = read("src-tauri/src/commands.rs");
  assert.match(rust, /pub const THEMES: &\[&str\] = &\["deep-space", "paper", "high-contrast"\];/);
  assert.doesNotMatch(read("src/theme.css"), /\[data-theme="ember"\]/);
  for (const page of ["index.html", "settings.html", "brain.html", "widget.html", "onboarding.html"]) {
    const html = read(`src/${page}`);
    assert.match(html, /\["deep-space", "paper", "high-contrast"\]/, `${page}'s first-paint allowlist`);
    assert.doesNotMatch(html, /value="ember"|"ember"/, `${page} still offers or allows Ember`);
  }
});

await check("anyone whose saved theme is Ember lands on Reactor", async () => {
  assert.equal(link.normaliseTheme("ember"), "deep-space");
  assert.equal(link.normaliseTheme("nonsense"), "deep-space");
  assert.equal(link.normaliseTheme(undefined), "deep-space");
  assert.equal(link.normaliseTheme("paper"), "paper");
  // The Rust twin, checked by its unit test too; this holds the mapping's
  // shape where CI's cargo test is the only other place that runs it.
  assert.match(read("src-tauri/src/commands.rs"), /normalise_theme\(Some\("ember"\)\), "deep-space"/);
});

await check("names and one-line descriptions match the phone's Themes.kt", async () => {
  const kt = read("../jarvis-client/app/src/main/java/com/jarvis/client/ui/theme/Themes.kt");
  const phone = {};
  for (const m of kt.matchAll(/id = "(\w+)",\s*label = "([^"]+)",\s*blurb = "([^"]+)"/g)) {
    phone[m[1]] = { label: m[2], blurb: m[3] };
  }
  const pairs = { "deep-space": "reactor", paper: "daylight", "high-contrast": "contrast" };
  for (const [desk, ph] of Object.entries(pairs)) {
    assert.ok(phone[ph], `the phone has no ${ph} theme any more`);
    assert.equal(link.THEME_INFO[desk].label, phone[ph].label, `${desk}'s name`);
    assert.equal(link.THEME_INFO[desk].blurb, phone[ph].blurb, `${desk}'s description`);
  }
});

await check("Reactor's surfaces are the HUD's and the phone's blue-black", async () => {
  const css = read("src/theme.css");
  assert.match(css, /--surface-1: rgba\(10, 17, 25, 0\.9\);/);   // #0a1119
  assert.match(css, /--surface-2: rgba\(14, 24, 34, 0\.92\);/);  // #0e1822
});

await check("Match Windows reads Windows' own setting, not prefers-color-scheme", async () => {
  // Every window is built with a forced Dark theme, which WebView2 reports as
  // prefers-color-scheme: dark whatever Windows says - see system_theme.rs.
  const rs = read("src-tauri/src/system_theme.rs");
  assert.match(rs, /AppsUseLightTheme/);
  assert.match(rs, /fn resting\(approvals: usize, activity: &str\)/, "a switch is not held mid-approval");
});

/* ── The link, in one set of words ──────────────────────────────────────── */

await check("linkWords: offline, connecting, stale and linked", async () => {
  const off = link.linkWords({ connected: false, stale: true, error: "Jarvis is not running at http://127.0.0.1:4719. Start it." });
  assert.equal(off.tone, "bad");
  assert.equal(off.canAct, false);
  assert.match(off.text, /^Offline — Jarvis is not running at http:\/\/127\.0\.0\.1:4719\. Approving is blocked/);
  const raw = link.linkWords({ connected: false, stale: true, error: "connection refused. Is it up?" });
  assert.match(raw.text, /not answering: connection refused\./);
  const cold = link.linkWords({ connected: false, stale: true, error: null });
  assert.equal(cold.short, "Connecting…");
  assert.doesNotMatch(cold.text, /127\.0\.0\.1/, "names an address before anything has failed");
  const stale = link.linkWords({ connected: true, stale: true });
  assert.equal(stale.tone, "warn");
  assert.equal(stale.canAct, false);
  assert.match(stale.text, /^Catching up… Nothing can be approved/);
  assert.equal(link.linkWords({ connected: true, stale: false }).canAct, true);
  // One wording in both apps (ease-of-use audit 2026-09-27 #5): the phone's
  // Home line says the same two words.
  assert.equal(link.linkWords({ connected: true, stale: false }).text, "Connected");
  const home = readFileSync(new URL("../../jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/HomeScreen.kt", import.meta.url), "utf8");
  assert.ok(home.includes('"Catching up…"') && home.includes('"Connected"'), "the phone's words");
  assert.ok(!/"Linked|Stale — reconnecting/.test(home), "the phone's old words are gone");
});

/* ── The owner's colours in the chrome ───────────────────────────────────── */

await check("the accent walks the idle colour's own family until it is legible", async () => {
  // Violet, deep to mist. A deep step is unreadable on a dark window, so the
  // walk moves toward the pale end and never leaves violet.
  const violet = { hex: "#3a1c73", ramp: ["#3a1c73", "#5b33a8", "#8a5cf0", "#b08cff", "#d8c6ff"], step: 0 };
  const grounds = [[10, 17, 25], [24, 28, 33]];
  const props = link.appearanceProperties({ idle: violet }, { grounds, dark: true });
  assert.ok(props["--accent"], "no accent was set");
  const rgb = props["--accent"].match(/\d+/g).map(Number);
  const worst = Math.min(...grounds.map((g) => link.contrast(rgb, g)));
  assert.ok(worst >= 4.5, `accent ${props["--accent"]} is ${worst.toFixed(2)}:1`);
  assert.ok(violet.ramp.map(link.hexRgb).some((c) => c.join() === rgb.join()), "left the family");
  // Standby is theme.css's declared divergence and is never overridden.
  const withStandby = link.appearanceProperties({ standby: violet }, { grounds, dark: true });
  assert.equal(withStandby["--state-standby"], undefined);
});

/* ── The face on this computer ───────────────────────────────────────────── */

await check("face settings: slow-down only, and anything unreadable is the default", async () => {
  assert.deepEqual(tuning.normaliseFaceTuning(null), { quality: "high", frameRate: "auto", speed: 1, autoAdjust: true });
  assert.equal(tuning.normaliseFaceTuning({ speed: 3 }).speed, 1, "faster than 1x got through");
  assert.equal(tuning.normaliseFaceTuning({ speed: 0.01 }).speed, 0.25);
  assert.equal(tuning.normaliseFaceTuning({ speed: "x" }).speed, 1);
  assert.equal(tuning.normaliseFaceTuning({ quality: "ultra" }).quality, "high");
  assert.deepEqual(tuning.SPEEDS, [0.25, 0.5, 0.75, 1]);
  assert.equal(tuning.strideFor("60", 120), 2);
  assert.equal(tuning.strideFor("60", 144), 2);
  assert.equal(tuning.strideFor("auto", 144), 1);
  assert.equal(tuning.strideFor("120", 60), 1);
});

/* ── In the windows ──────────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();

await check("Settings: three named theme rows, and Daylight leaves the list while following Windows", async () => {
  const page = await K.open(browser, base, "settings.html", {}, { width: 760, height: 1400 });
  // The theme list only: the manner, web search and speaking-speed choices
  // reuse the same row style further down the page.
  const rows = await page.locator("#theme-list .theme-row .theme-name").allTextContents();
  assert.deepEqual(rows, ["Reactor", "Daylight", "High Contrast"]);
  // A row must not carry `data-theme`, or theme.css repaints it.
  assert.equal(await page.locator(".theme-row[data-theme]").count(), 0);
  await page.locator("#follow-system").check();
  await page.waitForTimeout(200);
  assert.equal(await page.locator("#theme-legend").textContent(), "Theme for dark mode");
  assert.equal(await page.locator('.theme-row[data-choice="paper"]').isVisible(), false);
  const calls = await page.evaluate(() => window.__calls.map((c) => c[0]));
  assert.ok(calls.includes("set_theme_follow_system"));
  assert.deepEqual(page.__errors, []);
  await page.close();
});

await check("Settings: text size buttons, the face section closed, and Open Faces", async () => {
  const page = await K.open(browser, base, "settings.html", {}, { width: 760, height: 1400 });
  assert.equal(await page.locator("#text-size .choice").count(), 5);
  await page.locator('#text-size .choice[data-zoom="1.3"]').click();
  assert.equal(await page.evaluate(() => localStorage.getItem("jarvis.zoom")), "1.3");
  assert.equal(await page.locator('#text-size .choice[data-zoom="1.3"]').getAttribute("aria-pressed"), "true");
  assert.equal(await page.locator("#face-tuning").evaluate((d) => d.open), false, "opens closed, like the phone's");
  await page.locator("#face-tuning > summary").click();
  await page.locator('#face-speed .choice[data-value="0.5"]').click();
  await page.locator('#face-quality .choice[data-value="low"]').click();
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem("jarvis.faceTuning")));
  assert.deepEqual(saved, { quality: "low", frameRate: "auto", speed: 0.5, autoAdjust: false },
    "picking a quality turns Auto adjust off, as on the phone");
  assert.equal(await page.locator("#more-options").evaluate((d) => d.open), false);
  await page.locator("#open-faces").click();
  const calls = await page.evaluate(() => window.__calls.map((c) => c[0]));
  assert.ok(calls.includes("open_faces"));
  assert.deepEqual(page.__errors, []);
  await page.close();
});

await check("Settings: the connection line and the FAQ say Meshnet, and the mic FAQ is current", async () => {
  const page = await K.open(browser, base, "settings.html", { link: { stale: true } }, { width: 760, height: 1400 });
  assert.match(await page.locator("#link-text").textContent(), /Catching up…/);
  const html = read("src/settings.html");
  assert.match(html, /NordVPN Meshnet/);
  assert.match(html, /\.nord/);
  assert.doesNotMatch(html, /microphone button do nothing/);
  assert.doesNotMatch(html, /Base URL|Global accelerators|AAA|terminates the process tree/);
  await page.close();
});

await check("the widget says why Approve and Deny are grey, and how many are waiting", async () => {
  const page = await K.open(browser, base, "widget.html",
    { pending: [K.APPROVAL_PLAIN, K.APPROVAL_RAISED], link: { stale: true }, prefs: { expanded: true } },
    { width: 320, height: 460 });
  assert.equal(await page.locator("#widget-offline").isVisible(), true, "stale showed no words");
  assert.equal(await page.locator("#widget-offline").getAttribute("data-tone"), "warn");
  assert.match(await page.locator("#appr-why").textContent(), /cannot be confirmed/);
  assert.equal(await page.locator("#appr-count").textContent(), "1 of 2");
  assert.equal(await page.locator("#btn-appr-yes").isDisabled(), true);
  assert.match(await page.locator(".appr-hint").textContent(), /Nothing runs until you decide/);
  await page.close();
});

await check("the widget wears the owner's face: it reads appearance and drives its frame", async () => {
  const page = await K.open(browser, base, "widget.html",
    { pending: [], prefs: { expanded: true }, appearance: { face: "orbit", bindings: {}, source: "local", shared: false } },
    { width: 320, height: 460 });
  const calls = await page.evaluate(() => window.__calls.map((c) => c[0]));
  assert.ok(calls.includes("get_appearance"), "never asked for the owner's face");
  assert.match(await page.locator("#face-frame").getAttribute("src"), /feed=parent/);
  const widgetCap = JSON.parse(read("src-tauri/capabilities/widget.json"));
  assert.ok(widgetCap.permissions.includes("appearance-read"), "the capability still has no appearance read");
  await page.close();
});

await check("a multi-option plan says in words, on the card, why Approve is missing", async () => {
  for (const [file, sel, vp] of [["widget.html", "#appr-options-why", { width: 320, height: 460 }],
                                 ["index.html", "#approval-options-why", undefined]]) {
    const page = await K.open(browser, base, file, { pending: [K.APPROVAL_WITH_OPTIONS], prefs: { expanded: true } }, vp);
    const text = await page.locator(sel).textContent();
    await page.close();
    assert.match(text, /ways to do this/, `${file}: "${text}"`);
    assert.doesNotMatch(text, /JARVIS-API/);
  }
});

await check("the quickbar shows stale in amber, and keeps saying nothing runs until you decide", async () => {
  const page = await K.open(browser, base, "index.html", { pending: [K.APPROVAL_PLAIN], link: { stale: true } });
  assert.equal(await page.locator("#offline").isVisible(), true);
  assert.equal(await page.locator("#offline").getAttribute("data-tone"), "warn");
  assert.match(await page.locator("#offline-text").textContent(), /Catching up…/);
  assert.match(await page.locator(".approval-reassure").textContent(), /Nothing runs until you decide/);
  assert.match(await page.locator("#mic-label").textContent(), /Space or Enter/);
  await page.close();
});

await check("Brain: a failed read is amber with a Retry, a missing module is grey without one", async () => {
  const brain = { ...K.BRAIN,
    memory_pending: { available: false, error: "HTTP 500", read: "failed" },
    memory_facts: { available: false, read: "absent", error: "/api/memory/facts answered HTTP 404" } };
  const page = await K.open(browser, base, "brain.html", { brain, link: { stale: true } }, { width: 1180, height: 780 });
  assert.equal(await page.locator("#memory-proposals .empty.failed").count(), 1);
  assert.equal(await page.locator("#memory-proposals .empty.failed button").textContent(), "Retry");
  assert.match(await page.locator("#memory-facts .empty").first().textContent(), /Not on this backend/);
  assert.equal(await page.locator("#memory-facts .empty button").count(), 0);
  // The rush latch is on every view now, not only behind Advanced > Trust.
  assert.equal(await page.locator("#rush-strip").isVisible(), true);
  assert.match(await page.locator("#link-text").textContent(), /Catching up…/);
  assert.match(await page.locator("#freshness").textContent(), /last known/);
  await page.close();
});

await check("the face frame honours this computer's face settings, and never goes faster", async () => {
  const page = await browser.newPage({ viewport: { width: 200, height: 200 } });
  await page.addInitScript(() => localStorage.setItem("jarvis.faceTuning",
    JSON.stringify({ quality: "low", frameRate: "60", speed: 4, autoAdjust: false })));
  await page.goto(`${base}/faces.html?mode=display&face=arc`);
  await page.waitForTimeout(800);
  const got = await page.evaluate(() => ({
    q: document.documentElement.getAttribute("data-face-quality"),
    s: document.documentElement.getAttribute("data-face-speed"),
  }));
  await page.close();
  assert.equal(got.q, "low");
  assert.equal(got.s, "1", "a stored 4x was not clamped to 1x");
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\ndesktop and phone agree");
process.exit(fails.length ? 1 : 0);
