/**
 * "Look at this" and "Watch with me" on this PC (the owner's decision of
 * 2026-09-28; docs/SCREEN-DESIGN.md; look-rules.js, look.rs, main.js,
 * watch-badge.html, look-settings.js).
 *
 * Part 1 holds look-rules.js to the table both apps share
 * (tests/fixtures/screen-cases.json, written by tools/gen_screen_cases.py
 * from backend/jarvis_screen.py; the phone's ScreenRulesTest reads the same
 * file). Part 2 reads the Rust and the pages for the wiring the rules depend
 * on, and for what must NOT be there: nothing on this side reads the screen,
 * keeps a picture, or shows a word from it. No browser is needed for either.
 * (The drive-the-real-window part is tests/look.mjs, which does need one.)
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as R from "../src/look-rules.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const T = JSON.parse(read("tests/fixtures/screen-cases.json"));
const S = T.statuses;

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
  assert.equal(R.TITLE, T.words.seen.title);
  assert.equal(R.PAUSED_TITLE, T.words.seen.paused_title);
  assert.equal(R.ENDED_TITLE, T.words.seen.ended_title);
  assert.equal(R.STOP, T.words.seen.stop);
  assert.equal(R.MORE, T.words.seen.more);
  assert.equal(R.DROP, T.words.seen.drop);
  assert.equal(R.DOT, T.words.dot);
  assert.equal(R.ENDED_SHOW_S, T.words.ended_show_s);
  assert.equal(R.SEEN.hint, T.words.seen.hint);
  assert.equal(R.SEEN.held, T.words.seen.held);
  assert.equal(R.SEEN.held_short, T.words.seen.held_short);
  assert.equal(R.SEEN.watching_note, T.words.seen.watching_note);
  assert.equal(R.SEEN.link, T.words.seen.link);
  assert.equal(R.MARK, "look");
  assert.ok(T.words.marks.includes(R.MARK), "the mark is one the PC knows");
});

await check(`the sign: all ${T.sign.length} cases`, () => {
  for (const c of T.sign) {
    const status = c.status ? S[c.status] : null;
    const got = R.watchSign(status, { stale: c.stale, endedAgo: c.ended_ago === null ? undefined : c.ended_ago });
    assert.deepEqual({ ...got }, c.want, c.name);
  }
});

await check(`the line after a look: all ${T.look_line.length} cases`, () => {
  for (const c of T.look_line) assert.deepEqual({ ...R.lookLine(c.payload) }, c.want, c.name);
});

await check(`the mark on a question: all ${T.mark.length} cases`, () => {
  for (const c of T.mark) {
    const status = c.status ? S[c.status] : null;
    assert.equal(R.screenMark(status) || "", c.want, c.name);
  }
});

await check("a marked message is the same message plus one field - and no words", () => {
  const msg = { role: "user", content: "what does this say?", provenance: "typed" };
  const held = R.markMessage(msg, S.look_held);
  assert.deepEqual(held, { ...msg, screen: "look" });
  assert.equal(R.markMessage(msg, S.watching), msg, "no held look: the very same object");
  assert.equal(R.markMessage(msg, null), msg);
  assert.equal(R.markMessage(null, S.look_held), null);
  assert.equal(msg.screen, undefined, "the original is not changed");
});

await check("the sign never says more than the fixed words and minutes", () => {
  for (const c of T.sign) {
    const status = c.status ? S[c.status] : null;
    const got = R.watchSign(status, { stale: c.stale, endedAgo: c.ended_ago === null ? undefined : c.ended_ago });
    const allowed = [got.title, got.stop, got.more,
      ...got.detail.split(T.words.dot).map((bit) => bit.replace(/^(Paused: |Ended: |Ending soon - )/, ""))];
    for (const bit of allowed.filter(Boolean)) {
      const fixed = bit === R.TITLE || bit === R.PAUSED_TITLE || bit === R.ENDED_TITLE || bit === R.STOP
        || bit === R.MORE || bit === R.SEEN.link || bit === "something private is in front"
        || bit === "almost done" || /^(under a minute|\d+ min) left$/.test(bit)
        || Object.values(T.words.pause_words).includes(bit) || Object.values(T.words.end_words).includes(bit);
      assert.ok(fixed, `${c.name}: "${bit}" is not a fixed word`);
    }
  }
});

await check("a refusal is plain words, never a bridge error", () => {
  assert.equal(R.refusedWords(new Error("The connection to Jarvis is catching up.")), "The connection to Jarvis is catching up.");
  assert.match(R.refusedWords(new Error("command screen_watch not allowed on window x")), /could not start/);
  assert.match(R.refusedWords({ message: "{\"error\":1}" }), /could not start/);
  assert.match(R.refusedWords(""), /could not start/);
  assert.match(R.refusedWords("x".repeat(500)), /could not start/);
});

await check("minutes left", () => {
  assert.equal(R.minutesLeft(1440), "24 min left");
  assert.equal(R.minutesLeft(60), "1 min left");
  assert.equal(R.minutesLeft(61), "2 min left");
  assert.equal(R.minutesLeft(45), "under a minute left");
  assert.equal(R.minutesLeft(-1), "");
  assert.equal(R.minutesLeft(null), "");
  assert.equal(R.heldLeft(S.look_held), 90);
  assert.equal(R.heldLeft(S.off), 0);
  assert.equal(R.stripShown(S.look_held, ""), true);
  assert.equal(R.stripShown(S.off, ""), false);
  assert.equal(R.stripShown(S.off, "Looked at: Chrome window"), true);
});

/* ── 2. The wiring ──────────────────────────────────────────────────── */

const lookRs = read("src-tauri/src/look.rs");
const lib = read("src-tauri/src/lib.rs");

await check("nothing on the desktop side reads the screen, keeps a picture or shows the screen's words", () => {
  // look.rs asks the PC; it never captures, decodes or stores an image.
  //
  // CHANGED 2026-10-07 (the owner's decision; SCREEN-ATTACH-DESIGN.md): the key
  // now hands the CLEANED picture of the look to the question box, so
  // "base64" and "data:image" are allowed in look.rs - but ONLY as the PC's own
  // cleaner's PNG, passed on whole. What stays banned is everything that would
  // make this app a second reader of the screen: the capture crate, a capture
  // of its own, the image crate, and the text reader. tests/screen-attach.mjs
  // and look.rs's own `only_the_pcs_own_cleaned_png_becomes_an_attachment` hold
  // the picture path itself to the PNG, the size cap and the signature.
  for (const banned of ["xcap", "capture_primary_display", "Monitor::", "image::",
    "read_text", "ocr"]) {
    assert.ok(!lookRs.toLowerCase().includes(banned.toLowerCase()), `look.rs mentions ${banned}`);
  }
  const images = lookRs.match(/data:image\/[a-z+]+/g) || [];
  assert.deepEqual([...new Set(images)], ["data:image/png"],
    "the only picture look.rs builds is the cleaner's PNG");
  assert.match(lookRs, /"mime"\)[\s\S]{0,80}!= Some\("image\/png"\)/,
    "a picture the PC did not call image/png must be refused");
  assert.match(lookRs, /starts_with\(PNG_SIG\)/, "the bytes must really be a PNG");
  // Nothing from the screen is read out of an answer: only the fixed keys.
  const line = lookRs.slice(lookRs.indexOf("pub(crate) fn look_line("));
  assert.ok(!/"part"/.test(line.slice(0, line.indexOf("\n}\n"))), "look_line reads a `part`");
  const rulesJs = read("src/look-rules.js");
  assert.ok(!/\.part\b/.test(rulesJs), "look-rules.js reads a `part`");
  // Files: the strip and badge pages hold no image and no words of their own.
  for (const f of ["src/watch-badge.html", "src/watch-badge.js", "src/look-rules.js"]) {
    assert.ok(!/<img|data:image|createImageBitmap|canvas/i.test(read(f)), `${f} handles a picture`);
  }
});

await check("the hotkeys: Look at this keeps its key, Watch with me is off until picked", () => {
  const hk = read("src-tauri/src/hotkeys.rs");
  assert.match(hk, /id: "capture_screen",\s*label: "Look at this",\s*default: "Alt\+Shift\+S"/);
  assert.match(hk, /id: "toggle_watch",\s*label: "Start or stop Watch with me",[\s\S]*?default: "",/);
  assert.match(lib, /"capture_screen" => look::look_from_hotkey\(app\)/);
  assert.match(lib, /"toggle_watch" => look::toggle\(app, "hotkey"\)/);
  assert.match(lib, /"toggle_quickbar" => match look::toggle_bar_with_look\(app\)/);
  assert.ok(!lib.includes("fn capture_desktop"), "the old attach-a-capture key handler is still there");
  // The old picture-sending path is not on the key any more.
  assert.ok(!/capture_desktop\(/.test(lib));
});

await check("Look at this looks BEFORE the bar comes up, and is held on a stale link and under App lock", () => {
  const then = lookRs.slice(lookRs.indexOf("async fn look_then_bar("), lookRs.indexOf("/// \"Watch with me\": a question is about to start"));
  // CHANGED 2026-10-07: the key asks for the CLEANED picture as well
  // (`attach_body`, which is `look_body` plus `want: "picture"`), so the picture
  // is in the question box by the time the bar appears. It is still ONE look,
  // taken before the bar comes up.
  const posted = then.indexOf("attach_body(false)");
  const shown = then.indexOf("show_quickbar(app)");
  assert.ok(posted > 0 && shown > posted, "the bar must come up after the look, not before");
  assert.match(then, /held\(app\)/);
  assert.match(then, /is_loopback_base/);
  const held = lookRs.slice(lookRs.indexOf("fn held("));
  assert.match(held.slice(0, 400), /stale\(app\)/);
  assert.match(held.slice(0, 400), /app_locked\(app\)/);
});

await check("stopping is never held; starting is; only this PC is looked at", () => {
  const run = lookRs.slice(lookRs.indexOf("pub(crate) async fn run_watch("), lookRs.indexOf("/// The Never look at list, for Settings"));
  assert.match(run, /"start" => \{[\s\S]*?is_loopback_base[\s\S]*?held\(app\)/);
  // "extend" is held on a stale link: either `"extend" => { if stale(app) ...` or the
  // collapsed match guard `"extend" if stale(app) => ...` (clippy asks for the latter).
  assert.match(run, /"extend"\s+if\s+stale\(app\)\s*=>|"extend"\s*=>\s*\{[\s\S]*?stale\(app\)/);
  // "stop" and "drop" fall through to the `_ => {}` arm: nothing holds them.
  assert.match(run, /_ => \{\}/);
  assert.ok(!/"stop"\s*=>/.test(run) && !/"drop"\s*=>/.test(run), "stop or drop has a hold");
});

await check("Watch with me's fresh look is taken when a question STARTS: the bar's key, and \"Hey Jarvis\" heard", () => {
  assert.match(lookRs, /pub\(crate\) async fn ask\(app: &AppHandle\)[\s\S]*?"do": "ask"/);
  const voice = read("src-tauri/src/voice.rs");
  const arm = voice.slice(voice.indexOf("Ok(reply) if reply.wake_heard => {"));
  assert.match(arm.slice(0, 1400), /if reply\.is_owner \{\s*crate::look::ask_blocking\(&app\);/, "a wake look also needs the owner flag");
  assert.ok(arm.indexOf("ask_blocking") < arm.indexOf("VOICE_HEARD"), "the look comes before the question is handed on");
  // Without a session there is no request at all.
  assert.match(lookRs, /pub\(crate\) fn ask_blocking\(app: &AppHandle\) \{\s*if !on_here\(\) \{\s*return;/);
});

await check("the bar closing throws away a held look", () => {
  const w = read("src-tauri/src/windows.rs");
  assert.equal((w.match(/crate::look::bar_closed\(/g) || []).length, 3, "hide, blur and close-request");
  assert.match(lookRs, /pub fn bar_closed[\s\S]*?"do": "drop"/);
});

await check("the PC's event drives the sign; the tray has its row and its eye", () => {
  const stream = read("src-tauri/src/stream.rs");
  assert.match(stream, /"screen_watch" => crate::look::on_event\(app, &event\.data\)/);
  const tray = read("src-tauri/src/tray.rs");
  assert.match(tray, /ID_WATCH => crate::look::toggle_from_tray\(app\)/);
  assert.match(tray, /fn mark_watching\(/);
  assert.match(tray, /"Start Watch with me"/);
  assert.match(tray, /"Stop Watch with me"/);
  assert.match(tray, /crate::look::on_here\(\),\s*\);/);
});

await check("the badge is hidden from screen captures, always on top, and never takes the keyboard", () => {
  const badge = lookRs.slice(lookRs.indexOf("pub fn show_badge("));
  for (const need of [".content_protected(true)", ".always_on_top(true)", ".focused(false)", ".skip_taskbar(true)"]) {
    assert.ok(badge.includes(need), `the badge lacks ${need}`);
  }
});

await check("the permissions: the bar and the badge hold Watch; only Settings holds the list", () => {
  const cmds = ["screen_status", "screen_watch", "screen_never"];
  const build = read("src-tauri/build.rs");
  for (const c of cmds) {
    assert.ok(lib.includes(`look::${c},`), `lib.rs ${c}`);
    assert.ok(build.includes(`"${c}",`), `build.rs ${c}`);
    const file = read(`src-tauri/permissions/autogenerated/${c}.toml`);
    assert.ok(file.includes(`allow-${c.replace(/_/g, "-")}`), `${c} permission file`);
  }
  const bar = JSON.parse(read("src-tauri/capabilities/quickbar.json"));
  assert.ok(bar.permissions.includes("screen-watch"));
  assert.ok(!bar.permissions.includes("screen-never-look"), "the bar must not hold the list");
  const badge = JSON.parse(read("src-tauri/capabilities/watch-badge.json"));
  assert.deepEqual(badge.windows, ["watch-badge"]);
  assert.ok(badge.permissions.includes("screen-watch"));
  assert.ok(!badge.permissions.includes("screen-never-look"));
  const settings = JSON.parse(read("src-tauri/capabilities/settings.json"));
  assert.ok(settings.permissions.includes("screen-never-look"));
  assert.ok(!settings.permissions.includes("screen-watch"), "Settings does not start or stop watching");
  const sets = read("src-tauri/permissions/surfaces.toml");
  assert.match(sets, /identifier = "screen-watch"[\s\S]*?"allow-screen-status",\s*"allow-screen-watch"/);
  assert.match(sets, /identifier = "screen-never-look"[\s\S]*?"allow-screen-never"/);
});

await check("the question carries the mark only through screenTag, and no picture is attached for it", () => {
  const main = read("src/main.js");
  assert.match(main, /liveTag\(withCutOff\(screenTag\(userMessage\(content, state\.turnProvenance\)\)\)\)/);
  const tag = main.slice(main.indexOf("function screenTag("));
  assert.match(tag.slice(0, 300), /markMessage\(message, screen\.status\)/);
  // The note comes from `screen-look`, the sign from `screen-status`; nothing else.
  assert.match(main, /listen\("screen-status"/);
  assert.match(main, /listen\("screen-look"/);
});

await check(`picture mode: the words are the PC's and all ${T.picture.panels.length} settings cases match`, () => {
  const w = T.picture.words;
  assert.equal(R.PICTURE.title, w.title);
  assert.equal(R.PICTURE.detail, w.detail);
  assert.equal(R.PICTURE.switch, w.switch);
  assert.equal(R.PICTURE.offLine, w.off_line);
  assert.equal(R.PICTURE.waitingLine, w.waiting_line);
  assert.equal(R.PICTURE.unread, w.unread);
  assert.equal(R.PICTURE.missing, w.missing);
  assert.equal(R.PICTURE.stepsTitle, w.steps_title);
  assert.equal(R.PICTURE.stepsNote, w.steps_note);
  for (const c of T.picture.panels) {
    const got = R.pictureView(c.payload);
    assert.equal(got.available, c.want.available, c.name);
    assert.equal(got.enabled, c.want.enabled, c.name);
    assert.equal(got.waiting, c.want.waiting, c.name);
    assert.equal(got.checked, c.want.checked, c.name);
    assert.equal(got.line, c.want.line, c.name);
    assert.equal(got.measured, c.want.measured, c.name);
    assert.equal(got.installLine, c.want.install_line, c.name);
  }
});

await check("picture mode never says it works, never guesses a speed, and turning it on is a card", () => {
  const words = Object.values(R.PICTURE).join(" ").toLowerCase();
  assert.ok(!/\bworks\b/.test(words.replace("what a chart", "")), "a fixed word says it works");
  assert.ok(!/\d+ seconds/.test(words), "a fixed word gives a speed");
  assert.match(R.PICTURE.askedCard, /card is waiting/i);
  assert.match(R.PICTURE.askedCard, /stays off until you say yes/i);
  assert.match(R.PICTURE.detail, /slow/i);
  assert.match(R.PICTURE.detail, /blacked out/i);
  assert.match(R.PICTURE.stepsNote, /never downloads the model by itself/i);
  const settingsJs = read("src/look-settings.js");
  assert.ok(!/base64|data:image|<img|canvas/i.test(settingsJs), "look-settings.js handles a picture");
  // The switch's ON goes through the one card command; there is no other path.
  assert.match(settingsJs, /action: on \? "on" : "off"/);
});

await check("picture mode is wired: the command, its permission, and only Settings holds it", () => {
  const build = read("src-tauri/build.rs");
  assert.ok(lib.includes("look::screen_picture,"), "lib.rs screen_picture");
  assert.ok(build.includes('"screen_picture",'), "build.rs screen_picture");
  const file = read("src-tauri/permissions/autogenerated/screen_picture.toml");
  assert.ok(file.includes("allow-screen-picture"), "screen_picture permission file");
  const sets = read("src-tauri/permissions/surfaces.toml");
  assert.match(sets, /identifier = "screen-picture"[\s\S]*?"allow-screen-picture"/);
  const settings = JSON.parse(read("src-tauri/capabilities/settings.json"));
  assert.ok(settings.permissions.includes("screen-picture"));
  for (const f of ["quickbar", "watch-badge", "floating", "hud", "brain"]) {
    const cap = JSON.parse(read(`src-tauri/capabilities/${f}.json`));
    assert.ok(!cap.permissions.includes("screen-picture"), `${f} must not hold picture mode's switch`);
  }
  // ON is held on a stale link; OFF never is.
  const body = lookRs.slice(lookRs.indexOf("pub async fn screen_picture("));
  assert.match(body.slice(0, 500), /action == "on" && stale\(&app\)/);
  assert.ok(!/action == "off" && stale/.test(body.slice(0, 900)), "OFF must never be held");
  assert.ok(/"screen-picture"/.test(read("src-tauri/permissions/surfaces.toml")));
  const html = read("src/settings.html");
  assert.ok(html.includes('id="sp-switch"') && html.includes('id="sp-line-text"'), "settings.html markup");
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
