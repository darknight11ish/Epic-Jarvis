/**
 * Focus sessions on the desktop (the owner's decision of 2026-09-25;
 * JARVIS-API.md section 31; src/focus.js, brain.js paintFocus, widget.js,
 * main.js playFocusCallout, src-tauri/src/brain/focus.rs, stream.rs).
 *
 * What must hold:
 * - the words are the PC's and the phone's, word for word;
 * - every real answer (fixtures/focus-cases.json, made by the real engine)
 *   reads: countdown, tone, buttons, the report card;
 * - the Brain's Work tab: Start when off (minutes, "on what"), the countdown
 *   and ONE thing per tap when on (Pause/Resume, +10 minutes, Stop), the
 *   report card after; Start, Resume and +10 greyed on a stale link, Pause
 *   and Stop not; a `focus` event reads it again;
 * - the widget: a countdown only while a session runs, tinted on a drift,
 *   Pause/Resume, Lock on, Stop;
 * - CONTROL: Rust holds resume/extend/lock/start on a stale link and not
 *   pause/stop; fetches the spoken line only from this PC, as sound; the
 *   Jarvis bar plays it only when Jarvis is not talking, and "stop" silences
 *   it; the commands are the Brain's and the widget's alone.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  actionsOf,
  clock,
  driftWords,
  FOCUS_DETAIL,
  FOCUS_MISSING,
  FOCUS_TITLE,
  HELD_WHEN_STALE,
  LABELS,
  leftNow,
  minutesOf,
  readFocus,
  toneOf,
} from "../src/focus.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const readRepo = (p) => readFileSync(join(HERE, "..", "..", p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/focus-cases.json"));

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

await check("the words are the PC's and the phone's, word for word", async () => {
  assert.equal(FOCUS_TITLE, CASES.words.title);
  assert.equal(FOCUS_DETAIL, CASES.words.detail);
  assert.equal(FOCUS_MISSING, CASES.words.missing);
  const kt = readRepo("jarvis-client/app/src/main/java/com/jarvis/client/net/Focus.kt")
    .replace(/"\s*\+\s*\n?\s*"/g, "");
  for (const words of [FOCUS_TITLE, FOCUS_DETAIL, FOCUS_MISSING, LABELS.pause, LABELS.resume,
    LABELS.extend, LABELS.stop]) {
    assert.ok(kt.includes(`"${words}"`), `the phone does not say: ${words}`);
  }
  const html = read("src/brain.html");
  assert.ok(html.includes(`<h2>${FOCUS_TITLE}</h2>`));
  assert.ok(html.includes(`>${FOCUS_DETAIL}</p>`));
  assert.ok(read("src-tauri/src/brain/focus.rs").includes(`"${FOCUS_MISSING}"`));
});

await check("every real answer reads: countdown, tone, buttons, report card", async () => {
  const off = readFocus(CASES.off_never);
  assert.equal(off.available, true);
  assert.equal(off.on, false);
  assert.deepEqual(actionsOf(off), []);
  assert.equal(toneOf(off), "off");
  const settling = readFocus(CASES.settling);
  assert.equal(toneOf(settling), "settling");
  assert.equal(settling.left, 1800);
  assert.equal(settling.intent, "the essay");
  const on = readFocus(CASES.locked_on_target);
  assert.equal(toneOf(on), "on");
  assert.deepEqual(actionsOf(on), ["pause", "extend", "stop"]);
  assert.deepEqual(actionsOf(on, "widget"), ["pause", "lock", "stop"]);
  const drift = readFocus(CASES.drifting);
  assert.equal(toneOf(drift), "drift");
  assert.equal(drift.drifts, 1);
  assert.equal(toneOf(readFocus(CASES.excused)), "on", "research tinted as a drift");
  const paused = readFocus(CASES.paused);
  assert.equal(toneOf(paused), "paused");
  assert.equal(leftNow(paused, 60000), paused.left);
  assert.equal(leftNow(on, 60000), on.left - 60);
  assert.deepEqual(actionsOf(paused), ["resume", "extend", "stop"]);
  const done = readFocus(CASES.off_with_report);
  assert.equal(done.report.title, "Focus session stopped early.");
  assert.ok(done.report.lines[0].startsWith("On target: "));
  assert.ok(readFocus(CASES.done_clean).report.clean);
  for (const nothing of [null, {}, { available: false }, "x"]) {
    const n = readFocus(nothing);
    assert.equal(n.available, false);
    assert.equal(n.why, FOCUS_MISSING);
  }
  assert.equal(clock(1445), "24:05");
  assert.equal(clock(3725), "1:02:05");
  assert.equal(minutesOf("25"), 25);
  assert.equal(minutesOf("0"), null);
  assert.equal(minutesOf("241"), null);
  assert.equal(driftWords(0), "No drifts so far.");
  assert.equal(driftWords(2), "2 drifts so far.");
  assert.ok(!HELD_WHEN_STALE.has("pause") && !HELD_WHEN_STALE.has("stop"));
});

await check("CONTROL: Rust holds what makes Jarvis watch, fetches the line as sound from this PC only", async () => {
  const rs = read("src-tauri/src/brain/focus.rs");
  const fn = (name) => {
    const f = rs.slice(rs.indexOf(`pub async fn ${name}(`));
    return f.slice(0, f.indexOf("\n}\n"));
  };
  const start = fn("focus_start");
  assert.ok(start.indexOf("require_link_live") >= 0 && start.indexOf("require_link_live") < start.indexOf("post("),
    "start is not held on a stale link");
  assert.match(fn("focus_act"), /HELD_WHEN_STALE\.contains\(&action\.as_str\(\)\)[\s\S]*require_link_live/);
  assert.match(rs, /pub\(crate\) const HELD_WHEN_STALE: &\[&str\] = &\["resume", "extend", "lock"\];/);
  assert.match(rs, /pub\(crate\) const ACTIONS: &\[&str\] = &\["pause", "resume", "extend", "stop", "lock"\];/);
  const play = fn("play_callout");
  assert.ok(play.indexOf("is_loopback_base(&base)") >= 0
    && play.indexOf("is_loopback_base(&base)") < play.indexOf(".send()"),
    "the line is asked for from a backend that is not this PC");
  assert.match(play, /b"RIFF"/, "anything but a WAV could be handed on");
  assert.match(play, /emit_quickbar\(/);
  // "Stop everything" while the sound was being made drops it (bug audit
  // 2026-09-26, #1): the count is taken before asking, checked before handing on.
  assert.ok(play.indexOf("stops_so_far()") < play.indexOf(".send()"), "the stop count is not noted first");
  assert.ok(play.indexOf("still_wanted(") < play.indexOf("emit_quickbar("), "a stopped line is handed on");
  const stopNow = read("src-tauri/src/commands.rs");
  const sn = stopNow.slice(stopNow.indexOf("pub fn stop_everything_now("));
  assert.match(sn.slice(0, sn.indexOf("\n}\n")), /brain::focus::note_stop_everything\(\)/);
  assert.match(read("src-tauri/src/stream.rs"),
    /"focus" if event\.data\["state"\]\.as_str\(\) == Some\("callout"\) => \{\s*tauri::async_runtime::spawn\(crate::brain::focus::play_callout\(/);
  const main = read("src/main.js");
  assert.match(main, /listen\("focus-callout", \(event\) => playFocusCallout\(event\.payload\)\);/);
  const pf = main.slice(main.indexOf("function playFocusCallout("));
  assert.match(pf.slice(0, pf.indexOf("\n}\n")), /if \(jarvisTalking\(\) \|\| focusAudio\) return;/);
  const stop = main.slice(main.indexOf("function stopSpeaking() {"));
  assert.match(stop.slice(0, 80), /stopFocusCallout\(\);/, "\"stop\" does not silence a callout");
  // The commands: Brain and widget only; starting one is the Brain's alone.
  for (const cmd of ["focus_status", "focus_start", "focus_act"]) {
    assert.match(read("src-tauri/build.rs"), new RegExp(`"${cmd}"`));
    assert.match(read("src-tauri/src/lib.rs"), new RegExp(`brain::focus::${cmd},`));
  }
  const sets = read("src-tauri/permissions/surfaces.toml").split("[[set]]").slice(1);
  const holders = (cmd) => sets.filter((s) => s.includes(`"allow-${cmd.replace(/_/g, "-")}"`))
    .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
  assert.deepEqual(holders("focus_status"), ["focus"]);
  assert.deepEqual(holders("focus_act"), ["focus"]);
  assert.deepEqual(holders("focus_start"), ["focus-start"]);
  const caps = (w) => JSON.parse(read(`src-tauri/capabilities/${w}.json`)).permissions;
  assert.ok(caps("brain").includes("focus") && caps("brain").includes("focus-start"));
  assert.ok(caps("widget").includes("focus") && !caps("widget").includes("focus-start"));
  for (const other of ["quickbar", "hud", "settings", "faces", "onboarding"]) {
    assert.ok(!caps(other).some((c) => c.startsWith("focus")), `${other} holds a focus set`);
  }
});

/* ── The windows ──────────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 900 };

async function workTab(data = {}) {
  const page = await K.open(browser, base, "brain.html", data, SIZE);
  await page.locator("#tab-work").click();
  await page.waitForTimeout(500);
  return page;
}

await check("Brain, off: the form to start one, and the last report card", async () => {
  const page = await workTab({ focus: { status: CASES.off_with_report } });
  const form = await page.locator("#focus-form").isVisible();
  const report = await page.locator("#focus-report").innerText();
  await page.locator("#focus-minutes").fill("45");
  await page.locator("#focus-on").fill("the essay");
  await page.locator("#focus-start").click();
  await page.waitForTimeout(500);
  const sent = await page.evaluate(() => window.__focusCalls);
  await page.close();
  assert.equal(form, true);
  assert.match(report, /Last session/i);
  assert.match(report, /Focus session stopped early\./);
  assert.deepEqual(sent, [{ cmd: "focus_start", minutes: 45, on: "the essay" }]);
});

await check("Brain, running: the countdown moves, and ONE thing per tap", async () => {
  const page = await workTab({ focus: { status: CASES.locked_on_target } });
  const first = await page.locator("#focus .focus-clock").innerText();
  await page.waitForTimeout(2200);
  const later = await page.locator("#focus .focus-clock").innerText();
  const buttons = await page.locator("#focus button").allInnerTexts();
  const hidden = await page.locator("#focus-form").isHidden();
  await page.getByRole("button", { name: "Pause" }).click();
  await page.waitForTimeout(500);
  const after = await page.locator("#focus button").allInnerTexts();
  const sent = await page.evaluate(() => window.__focusCalls);
  await page.close();
  assert.notEqual(first, later, `${first} did not move`);
  assert.deepEqual(buttons, ["Pause", "+10 minutes", "Stop"]);
  assert.equal(hidden, true, "the start form showed during a session");
  assert.deepEqual(sent, [{ cmd: "focus_act", action: "pause", minutes: null }]);
  assert.deepEqual(after, ["Resume", "+10 minutes", "Stop"]);
});

await check("Brain, drifting: tinted, with the PC's line and the count", async () => {
  const page = await workTab({ focus: { status: CASES.drifting } });
  const tone = await page.locator("#focus .focus-now").getAttribute("data-tone");
  const text = await page.locator("#focus").innerText();
  await page.close();
  assert.equal(tone, "drift");
  assert.match(text, /off target\./);
  assert.match(text, /One drift so far\./);
});

await check("Brain, stale link: Start, Resume and +10 wait; Pause and Stop do not", async () => {
  let page = await workTab({ focus: { status: CASES.paused }, link: { stale: true } });
  const states = await page.locator("#focus button").evaluateAll(
    (bs) => bs.map((b) => [b.textContent, b.disabled]));
  await page.close();
  assert.deepEqual(states, [["Resume", true], ["+10 minutes", true], ["Stop", false]]);
  page = await workTab({ focus: { status: CASES.off_never }, link: { stale: true } });
  const start = await page.locator("#focus-start").isDisabled();
  await page.close();
  assert.equal(start, true, "Start was offered on a stale link");
});

await check("Brain: a PC without focus sessions says so", async () => {
  const page = await workTab({});
  const text = await page.locator("#focus").innerText();
  const form = await page.locator("#focus-form").isHidden();
  await page.close();
  assert.equal(text.trim(), FOCUS_MISSING);
  assert.equal(form, true);
});

await check("Brain: a `focus` event reads it again", async () => {
  const page = await workTab({ focus: { status: CASES.locked_on_target } });
  const before = await page.evaluate(() => window.__focus.reads);
  await page.evaluate(() => window.__emit("jarvis-event",
    { kind: "focus", id: 3, data: { state: "changed" } }));
  await page.waitForTimeout(400);
  const after = await page.evaluate(() => window.__focus.reads);
  await page.close();
  assert.ok(after > before, `${before} -> ${after}`);
});

const widget = (data) => K.open(browser, base, "widget.html", data, { width: 320, height: 520 });

await check("widget: no strip with no session; a countdown that tints on a drift", async () => {
  let page = await widget({ focus: { status: CASES.off_never } });
  await page.waitForTimeout(400);
  const none = await page.locator("#focus-strip").isHidden();
  await page.close();
  assert.equal(none, true);
  page = await widget({ focus: { status: CASES.drifting } });
  await page.waitForTimeout(400);
  const shown = await page.locator("#focus-strip").isVisible();
  const tone = await page.locator("#focus-strip").getAttribute("data-tone");
  const word = await page.locator("#focus-word").innerText();
  const buttons = await page.locator("#focus-strip button").allInnerTexts();
  const clockText = await page.locator("#focus-clock").innerText();
  await page.locator("#focus-lock").click();
  await page.waitForTimeout(400);
  const sent = await page.evaluate(() => window.__focusCalls);
  await page.close();
  assert.equal(shown, true);
  assert.equal(tone, "drift");
  assert.equal(word, "off target");
  assert.deepEqual(buttons, ["Pause", "Lock on", "Stop"]);
  assert.match(clockText, /^\d+:\d\d$/);
  assert.deepEqual(sent, [{ cmd: "focus_act", action: "lock", minutes: null }]);
});

await check("widget, stale link: Resume and Lock on wait, Stop does not", async () => {
  const page = await widget({ focus: { status: CASES.paused }, link: { stale: true } });
  await page.waitForTimeout(400);
  const states = await page.locator("#focus-strip button").evaluateAll(
    (bs) => bs.map((b) => [b.textContent, b.disabled]));
  await page.close();
  assert.deepEqual(states, [["Resume", true], ["Lock on", true], ["Stop", false]]);
});

await check("Jarvis bar: a line that arrives just after Stop everything is not played", async () => {
  const page = await K.open(browser, base, "index.html", {});
  await page.evaluate(() => {
    window.__audios = [];
    const Real = window.Audio;
    window.Audio = function (src) { window.__audios.push(src); const a = new Real(); a.play = () => Promise.resolve(); return a; };
  });
  const wav = "data:audio/wav;base64,UklGRiQAAABXQVZF";
  await page.evaluate(() => window.__emit("stop-everything", null));
  await page.waitForTimeout(100);
  await page.evaluate((uri) => window.__emit("focus-callout", { uri }), wav);
  await page.waitForTimeout(200);
  const after = await page.evaluate(() => window.__audios.length);
  await page.close();
  assert.equal(after, 0, "a focus line played right after Stop everything");
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nFocus sessions: the PC's words, one thing per tap, held on a stale link, the line fetched as sound from this PC only");
process.exit(fails.length ? 1 : 0);
