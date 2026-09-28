/**
 * Jarvis Live on this PC (the owner's decision and answers of 2026-09-28;
 * docs/LIVE-DESIGN.md; live-rules.js, live.rs, main.js, live-badge.html).
 *
 * Part 1 holds live-rules.js to the table both apps share
 * (tests/fixtures/live-cases.json, written by tools/gen_live_cases.py from
 * backend/jarvis_live.py; the phone's LiveRulesTest reads the same file).
 * Part 2 reads the Rust and the pages for the wiring the rules depend on.
 * Part 3 drives the real Jarvis bar: the sign, a Live question marked as
 * such, a long answer after a tool call spoken to the end, side talk never
 * spoken, tap buttons sent as typed words, and the fixed lines.
 *
 * (Named jarvis-live.mjs: tests/live.mjs is the Brain's "Live" tab.)
 */
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as R from "../src/live-rules.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const T = JSON.parse(read("tests/fixtures/live-cases.json"));
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

await check("the fixed words are the PC's (title, lines, seen, pauses, interrupt)", () => {
  assert.equal(R.TITLE, T.title);
  assert.equal(R.DOT, T.dot);
  assert.equal(R.LINK_WORDS, T.link_words);
  assert.equal(R.SIDE_TALK_MARK, T.side_talk_mark);
  assert.deepEqual({ ...R.LINES }, T.lines);
  assert.deepEqual({ ...R.SEEN }, T.seen);
  assert.deepEqual([...R.VOICE_PAUSES], T.voice_pauses);
  assert.deepEqual([...R.CARD_PAUSES], T.card_pauses);
  assert.equal(R.INTERRUPT_TITLE, T.interrupt_title);
  assert.deepEqual(R.INTERRUPT.map((c) => ({ ...c })), T.interrupt);
  assert.equal(R.STOP_TALKING, T.stop_talking);
  assert.deepEqual({ askAfterMs: R.TURN.askAfterMs, maxPauseMs: R.TURN.maxPauseMs },
    { askAfterMs: T.turn.ask_after_ms, maxPauseMs: T.turn.max_pause_ms });
  assert.equal(R.DUCK_VOLUME, T.duck_volume);
  assert.equal(R.MAX_CHIPS, T.max_chips);
});

await check(`the sign: all ${T.sign.length} cases`, () => {
  for (const c of T.sign) {
    const got = R.liveSign(S[c.status], c.me, { stale: c.stale, thinking: c.thinking, short: c.short });
    const { carryOn, ...rest } = got;
    assert.deepEqual({ ...rest, carry_on: carryOn }, c.want, c.name);
  }
});

await check(`may it listen, and may the microphone be open: all ${T.listen.length} cases`, () => {
  for (const c of T.listen) {
    const got = R.liveListen(S[c.status], c.me, {
      stale: c.stale, cardShown: c.card_shown, answering: c.answering,
      appLocked: c.app_locked, interrupt: c.interrupt,
    });
    assert.deepEqual(got, c.want, c.name);
  }
});

/** The PC's reply as the desktop's HeardReply carries it (camelCase, and
 *  `isOwner` instead of `ok`/`owner`). */
function camel(h) {
  const out = {};
  for (const [k, v] of Object.entries(h)) {
    if (k === "ok" || k === "owner") continue;
    out[k.replace(/_([a-z])/g, (_, c) => c.toUpperCase())] = v;
  }
  out.isOwner = h.owner === true;
  return out;
}

await check(`what to do with the PC's answer: all ${T.reply.length} cases, both shapes`, () => {
  for (const c of T.reply) {
    assert.deepEqual(R.liveReply(c.heard), c.want, c.name);
    assert.deepEqual(R.liveReply(camel(c.heard)), c.want, `${c.name} (camelCase)`);
  }
});

await check(`the fixed line when the session changes by itself: all ${T.transition.length} cases`, () => {
  for (const c of T.transition) {
    assert.equal(R.liveTransition(S[c.before], S[c.after], c.me), c.want, c.name);
  }
});

await check(`tap buttons after a spoken question: all ${T.chips.length} cases`, () => {
  for (const c of T.chips) {
    assert.deepEqual(R.liveChips(c.answer, { cardShown: c.card_shown }), c.want, c.name);
  }
});

await check("side talk: the marker only, and speech waits while it could be it", () => {
  for (const c of T.side_talk) assert.equal(R.isSideTalk(c.answer), c.side_talk, c.name);
  for (const c of T.side_talk_partial) assert.equal(R.couldBeSideTalk(c.partial), c.hold, c.partial);
});

await check("interrupting ducks first, and a second thought joins the question", () => {
  for (const c of T.barge) assert.equal(R.liveBarge(c.event), c.want, c.event);
  for (const c of T.fold) assert.equal(R.liveFold(c.previous, c.new, c.sounded), c.want);
});

await check(`the camera switch: never on the PC, off until the PC says ready (${T.camera.length} cases)`, () => {
  for (const c of T.camera) assert.equal(R.cameraShown(S[c.status], c.me), c.want, c.name);
  assert.equal(R.cameraShown(S.desktop_camera_ready, "desktop"), false);
});

await check("the interrupt setting: stored per PC, default by voice, anything odd is by voice", () => {
  const box = new Map();
  const storage = { getItem: (k) => (box.has(k) ? box.get(k) : null), setItem: (k, v) => box.set(k, v) };
  assert.equal(R.loadInterrupt(storage), "voice");
  R.saveInterrupt("tap", storage);
  assert.equal(R.loadInterrupt(storage), "tap");
  R.saveInterrupt("loud", storage);
  assert.equal(R.loadInterrupt(storage), "voice");
  const broken = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
  assert.equal(R.loadInterrupt(broken), "voice");
  R.saveInterrupt("tap", broken);
});

/* ── 2. The wiring ───────────────────────────────────────────────────── */

await check("Rust: the utterance reply carries live_short and live_elsewhere", () => {
  const voice = read("src-tauri/src/voice.rs");
  for (const f of ["live_short: String", "live_elsewhere: String", "live_say: String", "live_ended: String"]) {
    assert.ok(voice.includes(`pub ${f}`), f);
  }
  assert.ok(voice.includes("crate::live::heard_note("), "the instant heard note");
  assert.ok(voice.includes('if live { "live" } else { "wake_word" }'), "source=live");
});

await check("Rust: the pauses that close the microphone are the table's card pauses", () => {
  const rs = read("src-tauri/src/live.rs");
  const m = rs.match(/pub\(crate\) const CARD_PAUSES: &\[&str\] = &\[([^\]]*)\]/);
  assert.ok(m, "CARD_PAUSES");
  assert.deepEqual(m[1].split(",").map((s) => s.trim().replace(/"/g, "")).filter(Boolean), T.card_pauses);
  // A voice pause keeps the microphone open (check-only): it is not there.
  for (const p of T.voice_pauses) assert.ok(!m[1].includes(p), p);
  // Stop is never held; start is (stale link, App lock).
  assert.ok(rs.includes("STALE_HELD") && rs.includes("APP_LOCK_HELD"));
  assert.ok(/pub\(crate\) const STARTS: &\[&str\] = &\["button", "tray", "hotkey"\]/.test(rs));
});

await check("the commands are registered, allowed and held by the bar and the badge only", () => {
  const lib = read("src-tauri/src/lib.rs");
  const build = read("src-tauri/build.rs");
  const cmds = ["live_status", "live_start", "live_stop", "live_act", "live_mute", "live_hold"];
  for (const c of cmds) {
    assert.ok(lib.includes(`live::${c},`), `lib.rs ${c}`);
    assert.ok(build.includes(`"${c}",`), `build.rs ${c}`);
  }
  const bar = JSON.parse(read("src-tauri/capabilities/quickbar.json"));
  assert.ok(bar.permissions.includes("live"));
  const badge = JSON.parse(read("src-tauri/capabilities/live-badge.json"));
  assert.deepEqual(badge.windows, ["live-badge"]);
  assert.ok(badge.permissions.includes("live"));
  assert.ok(!badge.permissions.includes("voice") && !badge.permissions.includes("approvals"));
  for (const f of ["brain.json", "settings.json", "widget.json", "hud.json", "floating.json", "faces.json"]) {
    const cap = JSON.parse(read(`src-tauri/capabilities/${f}`));
    assert.ok(!cap.permissions.includes("live"), f);
  }
});

await check("no clash with the Brain's \"Live\" tab: the bar's ids are jarvis-live-*", () => {
  const html = read("src/index.html");
  assert.ok(!/id="live[-"]/.test(html), "no id=\"live...\" in the bar");
  assert.ok(html.includes('id="jarvis-live-toggle"'));
  assert.ok(existsSync(join(HERE, "..", "src", "live-badge.html")));
  const badge = read("src/live-badge.html");
  assert.ok(!badge.includes("innerHTML"), "the badge shows fixed words only");
});

await check("Settings -> Voice: the Live trust setting's three choices, the same words as the phone's", async () => {
  const VT = await import("../src/voice-training.js");
  assert.deepEqual(VT.HANDS_FREE_LIVE.map((c) => c.id),
    ["live_trust_fully", "live_button_start_only", "live_like_hey_jarvis"]);
  assert.deepEqual(VT.HANDS_FREE_LIVE.map(VT.choiceText),
    ["Trust Live fully (default)", "Only when I start it with the button", "Be as careful as with Hey Jarvis"]);
  // Which way is looser depends on the choice now; unknown counts as the strictest.
  assert.equal(VT.loosens("hands_free_live", "live_button_start_only", "live_trust_fully"), false);
  assert.equal(VT.loosens("hands_free_live", "live_button_start_only", "live_like_hey_jarvis"), true);
  assert.equal(VT.loosens("hands_free_live", "live_trust_fully", "live_button_start_only"), true);
  assert.equal(VT.loosens("hands_free_live", "live_like_hey_jarvis", "live_trust_fully"), false);
  assert.equal(VT.loosens("hands_free_live", "live_button_start_only"), true);
  assert.equal(VT.loosens("hands_free_screen", "screen_aloud"), true, "the others unchanged");
  const kt = read("../jarvis-client/app/src/main/java/com/jarvis/client/voice/StrictVoice.kt")
    .replace(/"\s*\+\s*\n\s*"/g, "").replace(/\\"/g, '"');
  for (const c of VT.HANDS_FREE_LIVE) assert.ok(kt.includes(c.detail), c.detail);
  assert.ok(kt.includes(VT.LIVE_ONLY_WHEN_STRICT_NOTE));
  const html = read("src/settings.html");
  assert.ok(html.includes('id="vt-live"') && html.includes('id="vt-live-interrupt"'));
  // The interrupt setting's words are the phone's too.
  const rules = read("../jarvis-client/app/src/main/java/com/jarvis/client/voice/LiveRules.kt");
  for (const c of R.INTERRUPT) assert.ok(rules.includes(`"${c.label}"`) && rules.includes(c.detail.slice(0, 40)), c.id);
});

/* ── 3. The Jarvis bar ───────────────────────────────────────────────── */

let K;
try {
  K = await import("./uikit.mjs");
} catch (e) {
  console.log(`skip  the Jarvis bar (${e.message.split("\n")[0]})`);
}

if (K) {
  const { base, close } = await K.serve();
  const browser = await K.launch();
  const ON = S.desktop_on;
  const delta = (text) => JSON.stringify({ choices: [{ delta: { content: text } }] });
  const step = (data) => ({ emit: "jarvis-event", payload: { kind: "step", id: 90, data } });
  const HEARD = { ...K.HEARD_OWNER, source: "live", live: "on", privateAloud: false, questionPrivate: false };
  const speakCalls = (page) => page.evaluate(() =>
    (window.__voiceCalls || []).filter((c) => Array.isArray(c) && c[0] === "speak").map((c) => c[1]));
  const chats = (page) => page.evaluate(() =>
    (window.__calls || []).filter((c) => c[0] === "stream_chat").map((c) => c[1]));
  const bar = async (chatReplies) => {
    const page = await K.open(browser, base, "index.html", { chatReplies });
    await page.evaluate((st) => window.__emit("live-status", { status: st, stale: false }), ON);
    await page.waitForTimeout(50);
    return page;
  };
  const hear = (page, heard) => page.evaluate((h) => window.__emit("voice-heard", h), heard);

  await check("the sign in the bar: title, minutes, Stop and Mute; the Live button pressed", async () => {
    const page = await bar([]);
    assert.equal(await page.isHidden("#jarvis-live-strip"), false);
    assert.equal((await page.textContent("#jarvis-live-title")).trim(), "Jarvis Live · 30 min left");
    assert.equal((await page.textContent("#jarvis-live-end")).trim(), "Stop");
    assert.equal((await page.textContent("#jarvis-live-mute")).trim(), "Mute");
    assert.equal(await page.getAttribute("#jarvis-live-toggle", "aria-pressed"), "true");
    await page.click("#jarvis-live-end");
    await page.click("#jarvis-live-mute");
    const calls = await page.evaluate(() => (window.__calls || []).map((c) => c[0]));
    assert.ok(calls.includes("live_stop") && calls.includes("live_mute"));
    assert.deepEqual(page.__errors, []);
    await page.close();
  });

  await check("a Live sentence goes as a spoken question marked live, and a long answer after a tool is spoken to the end", async () => {
    const sentences = [
      "It is sunny in Lisbon today.", "The high is twenty-four degrees.", "Tomorrow looks much the same.",
      "There is a light wind from the west.", "Rain is not expected this week.", "The evenings stay warm.",
    ];
    const page = await bar([[
      step({ phase: "tool_started", tool: "web_search" }),
      ": jarvis-status working",
      step({ phase: "tool_finished", tool: "web_search", ok: true }),
      ...sentences.map((s) => delta(`${s} `)),
    ]]);
    await page.evaluate(() => window.__emit("jarvis-link", { connected: true, stale: false }));
    await hear(page, { ...HEARD, text: "what's the weather in Lisbon this week" });
    await page.waitForTimeout(900);
    const sent = await chats(page);
    assert.equal(sent.length, 1);
    const last = sent[0].messages[sent[0].messages.length - 1];
    assert.equal(last.provenance, "voice");
    assert.equal(last.live, true, "marked live");
    assert.deepEqual(await speakCalls(page), sentences);
    assert.deepEqual(page.__errors, []);
    await page.close();
  });

  await check("side talk: \"[not for me]\" is never spoken, shows (not for Jarvis), and is not kept", async () => {
    const page = await bar([[delta("[not "), delta("for me]")], [delta("Sure. ")]]);
    await hear(page, { ...HEARD, text: "no I said the blue one" });
    await page.waitForTimeout(500);
    assert.deepEqual(await speakCalls(page), []);
    assert.ok((await page.textContent("#answer")).includes(R.SEEN.not_for_me));
    await hear(page, { ...HEARD, text: "Jarvis, what time is it" });
    await page.waitForTimeout(500);
    const sent = await chats(page);
    assert.equal(sent.length, 2);
    const words = JSON.stringify(sent[1].messages);
    assert.ok(!words.includes("blue one") && !words.includes("not for me"), "side talk left out of the conversation");
    assert.deepEqual(page.__errors, []);
    await page.close();
  });

  await check("tap buttons after a spoken question; a tap is sent as TYPED words", async () => {
    const page = await bar([[delta("I found two timers. Do you want me to cancel both?")], [delta("Done.")]]);
    await hear(page, { ...HEARD, text: "what timers are running" });
    await page.waitForTimeout(600);
    assert.equal(await page.isHidden("#jarvis-live-chips"), false);
    const chips = await page.$$eval("#jarvis-live-chips button", (b) => b.map((x) => x.textContent));
    assert.deepEqual(chips, ["Yes", "No"]);
    await page.click("#jarvis-live-chips button:first-child");
    await page.waitForTimeout(400);
    const sent = await chats(page);
    const last = sent[1].messages[sent[1].messages.length - 1];
    assert.equal(last.content, "Yes");
    assert.equal(last.provenance, "typed");
    assert.equal(last.live, undefined, "a tap is not a Live voice turn");
    assert.equal(await page.isHidden("#jarvis-live-chips"), true);
    assert.deepEqual(page.__errors, []);
    await page.close();
  });

  await check("too short but probably the owner: the line once, and \"Didn't catch that\" on the sign", async () => {
    const page = await bar([]);
    await hear(page, { ...HEARD, isOwner: false, text: "", tooShort: true, liveShort: "owner", liveSay: R.LINES.short });
    await page.waitForTimeout(200);
    assert.deepEqual(await speakCalls(page), [R.LINES.short]);
    assert.equal((await page.textContent("#jarvis-live-detail")).trim(), R.SEEN.short);
    assert.equal((await chats(page)).length, 0, "nothing sent to the model");
    await page.close();
  });

  await check("someone else, or too short and someone else: nothing said, nothing sent", async () => {
    const page = await bar([]);
    await hear(page, { ...HEARD, isOwner: false, text: "" });
    await hear(page, { ...HEARD, isOwner: false, text: "", tooShort: true, liveShort: "other" });
    await page.waitForTimeout(200);
    assert.deepEqual(await speakCalls(page), []);
    assert.equal((await chats(page)).length, 0);
    await page.close();
  });

  await check("the fixed lines: the start line, two minutes left, and \"that's all\"", async () => {
    const page = await K.open(browser, base, "index.html", { chatReplies: [] });
    await page.evaluate((st) => window.__emit("live-status", { status: st, stale: false, say: "I'm listening." }), ON);
    await page.evaluate((st) => window.__emit("live-status", { status: st, stale: false }), { ...ON, ending_soon: true });
    await hear(page, { ...HEARD, text: "", live: "ended", liveEnded: "bye", liveSay: R.LINES.bye });
    await page.waitForTimeout(300);
    assert.deepEqual(await speakCalls(page), ["I'm listening.", R.LINES.warn, R.LINES.bye]);
    await page.close();
  });

  await check("hey Jarvis here while Live is on the phone: the offer to move it, one tap", async () => {
    const page = await K.open(browser, base, "index.html", { chatReplies: [] });
    await hear(page, { ...K.HEARD_OWNER, source: "wake_word", text: "", wakeHeard: false, liveElsewhere: "phone" });
    await page.waitForTimeout(100);
    assert.equal((await page.textContent("#jarvis-live-move")).trim(), "Live is on your phone - move it here?");
    await page.click("#jarvis-live-move");
    const calls = await page.evaluate(() => (window.__calls || []).filter((c) => c[0] === "live_start"));
    assert.deepEqual(calls[0][1], { by: "button" });
    assert.equal((await chats(page)).length, 0);
    await page.close();
  });

  await check("a card on screen: the microphone is held closed, speech waits, and it is let go after", async () => {
    const page = await K.open(browser, base, "index.html", { pending: [K.APPROVAL_PLAIN], chatReplies: [] });
    await page.evaluate((st) => window.__emit("live-status", { status: st, stale: false }), ON);
    await page.waitForTimeout(100);
    const holds = () => page.evaluate(() =>
      (window.__calls || []).filter((c) => c[0] === "live_hold").map((c) => `${c[1].what}:${c[1].on}`));
    assert.deepEqual(await holds(), ["card:true"]);
    // Cards are decided by tapping - here, Deny.
    await page.locator("#approval-deny").click();
    await page.waitForTimeout(200);
    await page.evaluate(() => window.__emit("approvals-changed", { count: 0, items: [] }));
    await page.waitForTimeout(300);
    assert.deepEqual(await holds(), ["card:true", "card:false"]);
    await page.close();
  });

  await browser.close();
  close();
}

console.log(`\nJarvis Live: ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
