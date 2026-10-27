/**
 * The owner's two asks of 2026-10-27, in his own words:
 *
 *   A. "a live mode button in the left column of the Jarvis HUD"
 *   B. "a read out loud button i can enable in the settings which will add a
 *       read out loud icon next to all chat boxes that i can click on and
 *       jarvis will speak out loud the chat box in his chosen current voice"
 *
 * WHAT THIS FILE PROVES, and why each check is here:
 *
 *   1. A. the Live button is IN the left column's `.rail-toolbar` - the one
 *      rail block no shell hides (the Studio shell hides `.rail-nav`,
 *      `.rail-lanes` and `.rail-systems` by CSS, so a control put in any of
 *      those is invisible however well it is written);
 *   2. A. clicking it sends the BAR'S commands with the BAR'S arguments -
 *      `live_start` with `by: "button"` and a new chat id, `live_stop` - and
 *      the button's name and on/off words are the bar's, so the two windows
 *      cannot drift into two ideas of Live. The shell it is given is the one
 *      `capabilities/hud.json` + `permissions/surfaces.toml` actually grant it:
 *      status/start/stop and NOT `live_act`/`live_mute`/`live_hold`;
 *   3. B. the switch is OFF with nothing saved, and with it off an answer gets
 *      no speaker - and the automatic read-aloud still happens untouched;
 *   4. B. with it ON, a finished Jarvis answer shows a speaker, and clicking it
 *      speaks THAT answer's words through the page's own `voice.speak`
 *      (checked with two different answers, so "that answer" is not assumed);
 *   5. B. THE SAFETY RULE: an answer the window is treating as private shows no
 *      speaker at all, and the shell still refuses to speak its words even when
 *      asked directly - so there is no path from that bubble to the room;
 *   6. B. turning the switch off takes every speaker away at once.
 *
 * The page is served the way the packaged app serves it (Tauri's header CSP with
 * a sha256 per inline script) and the shell's bootstrap is injected first,
 * exactly as in tests/hud.mjs - because the page's chat, and the shell's own
 * speech gate, both live in that bootstrap.
 *
 * Playwright is not a dependency of this package. The browser-free half still
 * runs without it, and says so rather than passing silently.
 *
 *     node tests/hud-live-read-aloud.mjs
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  READ_ALOUD_ICONS_KEY,
  describeReadAloudIcons,
  readAloudIconsOn,
  saveReadAloudIcons,
} from "../src/read-aloud-icons.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const TAURI = join(HERE, "..", "src-tauri");
const read = (p) => readFileSync(p, "utf8");
const HUD = read(join(SRC, "jarvis_hud.html"));
const BAR = read(join(SRC, "index.html"));
const CONF = JSON.parse(read(join(TAURI, "tauri.conf.json")));
const BOOT = read(join(TAURI, "src", "hud_bootstrap.js"));
const ORIGIN = "http://tauri.localhost";
const BACKEND = "http://127.0.0.1:4719";

const fails = [];
const check = async (name, fn) => {
  try {
    await fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

/** The text between two markers, both of which must exist. */
function between(source, start, end, span = 4000) {
  const at = source.indexOf(start);
  assert.notEqual(at, -1, `"${start}" is not in the file`);
  const stop = source.indexOf(end, at);
  assert.notEqual(stop, -1, `"${end}" does not follow "${start}"`);
  return source.slice(at, Math.min(stop, at + span));
}

/* ── A1. The Live button is in the left column, in the group no shell hides ─ */

await check("A: the Live button is in the left rail's own toolbar", () => {
  const rail = between(HUD, 'id="rail-left"', "</aside>", 12000);
  assert.match(rail, /id="rail-toolbar"/, "the rail has no #rail-toolbar group");
  assert.match(rail, /id="rail-live"/, "the left rail has no Live button");
  // In the TOOLBAR, not merely somewhere in the rail: that group is the block
  // no shell hides (tests/hud-rail-tools.mjs pins that from the CSS side).
  const tools = HUD.indexOf('id="rail-toolbar"');
  const live = HUD.indexOf('id="rail-live"');
  const lanes = HUD.indexOf('id="rail-lanes"');
  assert.ok(tools !== -1 && live !== -1 && lanes !== -1, "a rail block is missing");
  assert.ok(tools < live && live < lanes, "the Live button is outside the rail toolbar");
  const body = between(HUD, 'id="rail-live"', "</button>", 1400);
  assert.doesNotMatch(body, /hide-sm/, "the Live button vanishes in a narrow window");
  assert.match(body, /<span class="rt-label">Live<\/span>/,
    "the visible word should be 'Live', as the bar's own chip says");
  assert.match(body, /aria-pressed="false"/, "a switch must say it is off to start");
});

await check("A: the Live button carries the BAR's own name and on/off words", () => {
  // The bar's resting title, spelled in index.html, and its two words for the
  // two states as main.js writes them. The HUD must say the same things: one
  // control in two windows, not two vocabularies.
  assert.match(BAR, /title="Jarvis Live: talk back and forth, no &quot;Hey Jarvis&quot; needed"/,
    "the bar's own Live title has moved - read it again before changing the HUD's");
  const live = between(HUD, 'id="rail-live"', "</button>", 1400);
  assert.match(live, /aria-label="Jarvis Live"/,
    "the HUD's Live button must use the bar's name for a screen reader");
  assert.match(live, /title="Jarvis Live: talk back and forth, no &quot;Hey Jarvis&quot; needed"/,
    "the HUD's resting title must be the bar's, word for word");
  assert.match(HUD, /"Jarvis Live is on - click to end it"/,
    "the HUD must say what the bar says while Live is on");
});

/* ── A2. The capability is exactly the bar's three, and no more ──────────── */

await check("A: the HUD is granted status/start/stop and nothing else of Live", () => {
  const capability = JSON.parse(read(join(TAURI, "capabilities", "hud.json")));
  assert.equal(capability.permissions.filter((name) => name === "hud-live").length, 1,
    "capabilities/hud.json does not grant exactly one hud-live set");
  const surfaces = read(join(TAURI, "permissions", "surfaces.toml"));
  const at = surfaces.indexOf('identifier = "hud-live"');
  assert.notEqual(at, -1, "surfaces.toml has no hud-live set");
  const set = surfaces.slice(at, surfaces.indexOf("[[set]]", at) > 0
    ? surfaces.indexOf("[[set]]", at) : at + 900);
  assert.match(set, /"allow-live-status"/, "the set misses allow-live-status");
  assert.match(set, /"allow-live-start"/, "the set misses allow-live-start");
  assert.match(set, /"allow-live-stop"/, "the set misses allow-live-stop");
  // The bar's OTHER Live verbs stay the bar's: this window may start, stop and
  // read, and may not extend, mute or hold the microphone.
  for (const denied of ["allow-live-act", "allow-live-mute", "allow-live-hold"]) {
    assert.equal(set.includes(denied), false, `the HUD was granted ${denied}`);
  }
});

/* ── B1. The setting: OFF by default, and the page's copy agrees ─────────── */

await check("B: the read-aloud switch is OFF with nothing saved", () => {
  const store = (value) => ({ getItem: () => value });
  assert.equal(readAloudIconsOn(store(null)), false, "the switch starts ON");
  assert.equal(readAloudIconsOn(store("false")), false, "a saved 'false' reads as on");
  assert.equal(readAloudIconsOn(store("yes")), false, "only 'true'/'on' may mean on");
  assert.equal(readAloudIconsOn(null), false, "no storage at all must read as off");
  assert.equal(readAloudIconsOn(store("true")), true, "a saved 'true' does not read as on");
  assert.equal(readAloudIconsOn(store("on")), true, "a saved 'on' does not read as on");
  // Saving is the same store, and it answers for itself.
  const saved = new Map();
  const writable = { getItem: (k) => saved.get(k) ?? null, setItem: (k, v) => saved.set(k, v) };
  assert.equal(saveReadAloudIcons(true, writable), true, "the save said it failed");
  assert.equal(readAloudIconsOn(writable), true, "what was saved does not read back");
  assert.equal(readAloudIconsOn(store(null)), false, "an empty store reads as on");
  assert.equal(
    readAloudIconsOn({ getItem() { throw new Error("denied"); } }),
    false,
    "a storage that throws must read as OFF, never as on");
});

await check("B: the page's own copy of the rule is the module's, value by value", () => {
  // The page keeps its own copy because its main script is a CLASSIC script and
  // has to read the switch synchronously while drawing an answer - the same
  // arrangement hud_bootstrap.js has for OPEN_BAR_KEY. This is what stops the
  // two drifting.
  const key = HUD.match(/const READ_ALOUD_ICONS_KEY = "([^"]+)";/);
  assert.ok(key, "jarvis_hud.html no longer spells the switch's storage key");
  assert.equal(key[1], READ_ALOUD_ICONS_KEY, "the page and the module spell different keys");
  const fn = HUD.match(/function readAloudIconsOn\(\)\{([\s\S]*?)\n\}/);
  assert.ok(fn, "jarvis_hud.html no longer carries its own readAloudIconsOn");
  const body = fn[1].replace(/READ_ALOUD_ICONS_KEY/g, JSON.stringify(key[1]));
  // eslint-disable-next-line no-new-func
  const pageRule = new Function("localStorage", body);
  for (const value of [null, "true", "on", "false", "off", "yes", "", "1"]) {
    const store = () => ({ getItem: () => value });
    assert.equal(pageRule(store), readAloudIconsOn(store),
      `the page and the module disagree about ${JSON.stringify(value)}`);
  }
  assert.equal(pageRule({ getItem() { throw new Error("denied"); } }), false,
    "the page reads a storage that throws as ON");
});

await check("B: the switch is Settings' own card, with a plain-words line", () => {
  const card = between(read(join(SRC, "settings.html")), "<h2>The big HUD window</h2>",
    "</section>", 14000);
  assert.match(card, /<input id="hud-read-aloud-icons" type="checkbox" \/>/,
    "Settings has no read-aloud speaker switch");
  assert.doesNotMatch(card, /<input id="hud-read-aloud-icons" type="checkbox" checked/,
    "the switch starts checked - it must start OFF");
  assert.match(card, /id="hud-read-aloud-icons-status" role="status"/,
    "the card has no status line, so a refused save would be invisible");
  // The words a reader is promised: no speaker on an answer that stays on
  // screen, and OFF does not stop today's read-aloud.
  assert.match(card, /An answer\s+that has to stay on screen gets no speaker/,
    "the switch does not say that a kept-on-screen answer gets no speaker");
  assert.match(card, /still reads answers aloud\s+exactly as\s+it does today/,
    "the switch does not say that OFF leaves today's read-aloud alone");
  // Both states are described in the store's own words too.
  assert.equal(describeReadAloudIcons(false).startsWith("Off:"), true);
  assert.equal(describeReadAloudIcons(true).startsWith("On:"), true);
});

/* ── The browser half ────────────────────────────────────────────────────── */

let K = null;
try {
  await import("playwright");
  K = await import("./uikit.mjs");
} catch {
  console.log("\nNOT RUN  the browser half: Playwright is not installed here.");
  console.log("         Those five checks did NOT pass - install it to run them:");
  console.log("         npm i -D playwright && npx playwright install chromium");
}

/** Tauri's header CSP: the configured policy plus a sha256 per inline script. */
function tauriCsp(html) {
  const hashes = [...html.replace(/<!--[\s\S]*?-->/g, "")
    .matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)]
    .map((m) => m[1])
    .filter((s) => s.length)
    .map((s) => `'sha256-${createHash("sha256").update(s.replace(/\r\n?/g, "\n"), "utf8")
      .digest("base64")}'`);
  return CONF.app.security.csp.replace(/script-src ([^;]*)/, (_, v) => `script-src ${v} ${hashes.join(" ")}`);
}

/**
 * The HUD, served and shelled the way the app serves it.
 *
 * `scenario`:
 *   - `replies`: `[{ text, route }]`, handed out one per chat send, in order;
 *   - `iconsOn`: seed the switch ON before the page's first paint;
 *   - `noShell`: no `__TAURI__` at all, as a plain browser gets.
 *
 * The invoke stub answers only what `capabilities/hud.json` grants: the chat
 * shims, the layout read, stop, and the three `hud-live` commands. Anything
 * else is refused, which is what makes the HUD's own Live click meaningful.
 */
async function openHud(browser, scenario = {}) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 820 } });
  const problems = [];
  const chats = [];
  page.on("pageerror", (e) => problems.push(String(e)));
  page.on("console", (m) => {
    if (m.type() === "error" && /Content Security Policy|Refused to/.test(m.text())) {
      problems.push(m.text());
    }
  });
  // The voice list and the recorder go in BEFORE the bootstrap, as the real
  // objects do - the bootstrap wraps whatever `speak` it finds.
  await page.addInitScript(({ on }) => {
    window.__spoken = [];
    window.SpeechSynthesisUtterance = class {
      constructor(text) { this.text = text; this.voice = null; }
    };
    const synth = window.speechSynthesis;
    synth.getVoices = () => [{ name: "Daniel", lang: "en-GB", localService: true, default: true }];
    synth.speak = (u) => { window.__spoken.push(u.text); };
    synth.cancel = () => {};
    if (on) { try { localStorage.setItem("jarvis.hud.readAloudIcons", "true"); } catch (e) {} }
  }, { on: Boolean(scenario.iconsOn) });
  if (!scenario.noShell) {
    await page.addInitScript(({ replies, backend }) => {
      const origFetch = window.fetch.bind(window);
      const shellHeaders = { "X-Jarvis-Client": "hud", "X-Jarvis-Token": "test-token" };
      const queue = replies.slice();
      let live = { on: false };
      const liveListeners = [];
      window.__invokes = [];
      window.__liveEmit = (payload) => liveListeners.forEach((fn) => fn({ payload }));
      class Channel { constructor() { this.onmessage = null; } }
      window.__TAURI__ = {
        core: {
          Channel,
          invoke: async (cmd, args) => {
            window.__invokes.push([cmd, args]);
            switch (cmd) {
              case "live_status":
                return { status: live, stale: false, lockUnknown: false, callUnknown: false };
              case "live_start":
                live = { on: true, device: "desktop", by: args && args.by };
                return { status: live, stale: false, say: "I'm listening." };
              case "live_stop":
                live = { on: false };
                return { status: live, stale: false };
              case "get_hud_layout":
                return { layout: null, source: "none" };
              case "summon_push_to_talk":
              case "hud_open_bar":
              case "hide_quickbar":
              case "stop_everything":
                return null;
              case "get_lock_flags":
                return { appLock: false, privateAnswers: false };
              case "hud_get": {
                const r = await origFetch(backend + args.path, { headers: shellHeaders });
                return { status: r.status, contentType: r.headers.get("Content-Type") || "",
                  route: r.headers.get("X-Jarvis-Route"), body: await r.text() };
              }
              case "hud_chat": {
                const next = queue.length ? queue[0] : { text: "(no reply left)", route: {} };
                // Recorded in the PAGE (a Node variable is not visible here).
                window.__chats = window.__chats || [];
                window.__chats.push({ body: args.body, reply: next.text });
                const ch = args.onEvent;
                ch.onmessage(JSON.stringify({
                  kind: "head", status: 200, contentType: "application/json",
                  route: JSON.stringify(next.route || {}),
                }));
                ch.onmessage(JSON.stringify({
                  kind: "data",
                  text: JSON.stringify({ choices: [{ message: { content: next.text } }] }),
                }));
                ch.onmessage(JSON.stringify({ kind: "end" }));
                if (queue.length) queue.shift();
                return null;
              }
              case "hud_chat_cancel":
                return null;
              default:
                throw new Error(`Command ${cmd} not allowed by ACL`);
            }
          },
        },
        event: {
          listen: async (name, fn) => {
            if (name === "live-status") liveListeners.push(fn);
            return () => {};
          },
        },
      };
    }, { replies: scenario.replies || [], backend: BACKEND });
  }
  await page.addInitScript(BOOT.replace("__JARVIS_BASE__", JSON.stringify(BACKEND)));
  const html = readFileSync(join(SRC, "jarvis_hud.html"), "utf8");
  await page.route("**/*", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    if (url.origin === ORIGIN && url.pathname === "/jarvis_hud.html") {
      return route.fulfill({
        status: 200, body: html,
        headers: { "Content-Type": "text/html", "Content-Security-Policy": tauriCsp(html) },
      });
    }
    if (url.origin === ORIGIN) {
      const file = join(SRC, decodeURIComponent(url.pathname));
      try {
        const body = readFileSync(file);
        const headers = { "Content-Type": url.pathname.endsWith(".js") ? "text/javascript" : "text/plain" };
        if (url.pathname.endsWith(".html")) headers["Content-Security-Policy"] = tauriCsp(body.toString("utf8"));
        return route.fulfill({ status: 200, body, headers });
      } catch {
        return route.fulfill({ status: 404, body: "" });
      }
    }
    if (url.origin === BACKEND) {
      const cors = {
        "Access-Control-Allow-Origin": ORIGIN,
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      };
      if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
      if (url.pathname === "/api/status") {
        return route.fulfill({ status: 200, headers: cors,
          body: JSON.stringify({ jarvis: false, ollama: true, proxy: false }) });
      }
      return route.fulfill({ status: 404, headers: cors, body: JSON.stringify({ error: "not found" }) });
    }
    return route.continue();
  });
  await page.goto(`${ORIGIN}/jarvis_hud.html`);
  // The rail's Live button unhides when the module script has run.
  await page.waitForFunction(() => {
    const b = document.getElementById("rail-live");
    return !b || !b.hidden || window.__TAURI__ === undefined;
  }, null, { timeout: 8000 }).catch(() => {});
  return { page, problems, chats };
}

/** Send one message and wait for that answer to finish. */
async function send(page, text, expectCount) {
  await page.fill("#input", text);
  await page.click("#send");
  try {
    await page.waitForFunction(
      (n) => document.querySelectorAll("#log .msg.jarvis[data-state='done']").length >= n,
      expectCount, { timeout: 15000 });
  } catch (e) {
    const diag = await page.evaluate(() => ({
      invokes: (window.__invokes || []).map((c) => c[0]),
      log: (document.getElementById("log") || {}).textContent || "",
      online: Boolean(window.S && window.S.online),
      said: window.__spoken ? window.__spoken.slice() : null,
    })).catch(() => ({}));
    throw new Error(`${e.message}\n      diagnostics: ${JSON.stringify(diag)}`);
  }
}

if (K) {
  /* ── A3. Clicking it does what the bar's toggle does ───────────────────── */

  await check("A: the Live button is reachable, and sends the bar's own two commands", async () => {
    const browser = await K.launch();
    try {
      const { page, problems } = await openHud(browser, {});
      const seen = await page.evaluate(() => ({
        visible: (() => {
          const b = document.getElementById("rail-live");
          if (!b) return false;
          const r = b.getBoundingClientRect();
          return !b.hidden && r.width > 0 && r.height > 0;
        })(),
        inToolbar: (() => {
          const group = document.getElementById("rail-toolbar");
          return Boolean(group && group.contains(document.getElementById("rail-live")));
        })(),
        label: document.getElementById("rail-live").getAttribute("aria-label"),
        text: document.getElementById("rail-live").textContent.trim(),
        pressed: document.getElementById("rail-live").getAttribute("aria-pressed"),
      }));
      assert.deepEqual(problems.filter((p) => /Content Security Policy|Refused to/.test(p)), [],
        "the page refused one of its own scripts - the Live button would be dead");
      assert.equal(seen.visible, true, "the Live button is not reachable in the shell");
      assert.equal(seen.inToolbar, true, "the Live button is not in the left rail's toolbar");
      assert.equal(seen.label, "Jarvis Live", "the button does not use the bar's name");
      assert.equal(seen.text, "Live", "the button's visible word is not Live");
      assert.equal(seen.pressed, "false", "the button does not start unpressed");

      await page.click("#rail-live");
      await page.waitForFunction(() =>
        document.getElementById("rail-live").getAttribute("aria-pressed") === "true",
      null, { timeout: 5000 }).catch(() => {
        throw new Error("clicking the Live button did not start a session "
          + "(aria-pressed stayed false)");
      });
      const started = await page.evaluate(() => ({
        calls: window.__invokes.filter((c) => c[0].startsWith("live_")),
        title: document.getElementById("rail-live").title,
      }));
      const start = started.calls.find((c) => c[0] === "live_start");
      assert.ok(start, "the Live button did not send live_start");
      assert.equal(start[1].by, "button", "the start is not the bar's own (by: button)");
      assert.match(String(start[1].conversationId), /^[A-Za-z0-9_-]{8,64}$/,
        "the start carries no conversation id - a Live chat could not be named to the phone");
      assert.equal(started.title, "Jarvis Live is on - click to end it",
        "the on-state words are not the bar's");

      await page.click("#rail-live");
      await page.waitForFunction(() =>
        document.getElementById("rail-live").getAttribute("aria-pressed") === "false",
      null, { timeout: 5000 });
      const stopped = await page.evaluate(() =>
        window.__invokes.filter((c) => c[0] === "live_stop").length);
      assert.equal(stopped, 1, "a second click did not send live_stop");
      // And a shell event keeps it truthful while the window stays open: the
      // same `live-status` event the bar repaints from. The whole table is
      // driven, because this page keeps its own one-line copy of
      // `live-rules.js`'s `onHere` (the browser HUD is served from a CLOSED
      // asset whitelist, so the window cannot import the module) - the table is
      // what holds that copy to the rule.
      const table = [
        [{ on: true, device: "desktop" }, "true", "a session on this PC"],
        [{ on: true, device: "phone" }, "false", "a session on the PHONE"],
        [{ on: false, device: "desktop" }, "false", "an ended session"],
        [{ device: "desktop" }, "false", "a status with no 'on'"],
        [{ on: "true", device: "desktop" }, "false", "an 'on' that is a string"],
        [{ on: true, device: "tablet" }, "false", "another device entirely"],
        [null, "false", "no status at all"],
      ];
      for (const [state, want, why] of table) {
        await page.evaluate((s) => window.__liveEmit({ status: s }), state);
        await page.waitForFunction(
          (w) => document.getElementById("rail-live").getAttribute("aria-pressed") === w,
          want, { timeout: 5000 }).catch(() => {
          throw new Error(`the Live button did not read ${why} as pressed=${want}`);
        });
      }
      await page.close();
    } finally {
      await browser.close();
    }
  });

  await check("A: a plain browser gets no Live button at all", async () => {
    const browser = await K.launch();
    try {
      const { page } = await openHud(browser, { noShell: true });
      const hidden = await page.evaluate(() => document.getElementById("rail-live").hidden);
      assert.equal(hidden, true,
        "a page with no shell drew a Live button it cannot honour");
      await page.close();
    } finally {
      await browser.close();
    }
  });

  /* ── B2. OFF by default, and today's read-aloud is untouched ───────────── */

  await check("B: with the switch off no speaker shows, and read-aloud still works", async () => {
    const browser = await K.launch();
    try {
      const { page } = await openHud(browser, {
        replies: [{ text: "The first answer, spoken as it always was.", route: {} }],
      });
      await send(page, "a question", 1);
      // Wait for the turn to finish (the page speaks at the end of the send).
      await page.waitForFunction(() => window.__spoken.length > 0, null, { timeout: 8000 });
      const state = await page.evaluate(() => ({
        speakers: document.querySelectorAll("#log .msg.jarvis .speak-answer").length,
        spoken: window.__spoken.slice(),
      }));
      assert.equal(state.speakers, 0, "a speaker was drawn with the switch off");
      // The CONTROL that says the switch is not the read-aloud switch: the
      // answer was still read aloud, exactly as before this feature.
      assert.deepEqual(state.spoken, ["The first answer, spoken as it always was."],
        "the automatic read-aloud changed when the speaker switch was added");
      await page.close();
    } finally {
      await browser.close();
    }
  });

  /* ── B3. ON: one speaker per answer, and it speaks THAT answer ─────────── */

  await check("B: with the switch on, each answer gets a speaker that says its words", async () => {
    const browser = await K.launch();
    try {
      const { page } = await openHud(browser, {
        iconsOn: true,
        replies: [
          { text: "First answer: the kettle is on.", route: {} },
          { text: "Second answer: the door is locked.", route: {} },
        ],
      });
      await send(page, "first question", 1);
      await send(page, "second question", 2);
      await page.waitForFunction(
        () => document.querySelectorAll("#log .msg.jarvis .speak-answer").length >= 2,
        null, { timeout: 8000 });
      // Only Jarvis's ANSWERS carry one: the owner's own messages never do, and
      // neither does the canned hello the window opens with (it is not an
      // answer to anything, and this window has never read it aloud either -
      // the icon goes exactly where the automatic read-aloud would have been).
      const counts = await page.evaluate(() => {
        const bubbles = [...document.querySelectorAll("#log .msg.jarvis")];
        const answered = bubbles.filter((b) => b.dataset.state === "done");
        return {
          answered: answered.length,
          onAnswered: answered.filter((b) => b.querySelector(".speak-answer")).length,
          onRest: bubbles.filter((b) => b.dataset.state !== "done"
            && b.querySelector(".speak-answer")).length,
          user: document.querySelectorAll("#log .msg.user .speak-answer").length,
        };
      });
      assert.equal(counts.answered, 2, "the two answers did not both finish");
      assert.equal(counts.onAnswered, counts.answered, "not every finished answer got a speaker");
      assert.equal(counts.onRest, 0, "a speaker was drawn on a bubble that is not an answer");
      assert.equal(counts.user, 0, "the owner's own message was given a speaker");
      // Clear what the automatic read-aloud said, so the click is the only
      // thing that can be in the record.
      await page.evaluate(() => { window.__spoken = []; });
      // The FIRST answer's speaker, not the last: the words must be its own.
      // Clicked by its own index in the answer list, so a change in how many
      // elements the log holds cannot silently point this at another bubble.
      await page.evaluate(() => {
        document.querySelectorAll("#log .msg.jarvis .speak-answer")[0].click();
      });
      await page.waitForFunction(() => window.__spoken.length > 0, null, { timeout: 5000 });
      const spoken = await page.evaluate(() => window.__spoken.slice());
      assert.deepEqual(spoken, ["First answer: the kettle is on."],
        "clicking a speaker did not read THAT answer's words out loud");
      await page.close();
    } finally {
      await browser.close();
    }
  });

  /* ── B4. THE SAFETY RULE ───────────────────────────────────────────────── */

  await check("B: an answer that stays on screen shows no speaker, and is not spoken", async () => {
    const browser = await K.launch();
    try {
      const { page } = await openHud(browser, {
        iconsOn: true,
        // `gate: "private"` is private-speech.js's own refusal, the same one the
        // page's automatic read-aloud obeys and the shell's speak gate enforces.
        replies: [{ text: "Your test results came back, and here they are.", route: { gate: "private" } }],
      });
      await send(page, "what did my test results say", 1);
      // The shell draws its own line under an answer it keeps on screen.
      await page.waitForFunction(() => Boolean(document.querySelector("#log .jarvis-kept")),
        null, { timeout: 8000 });
      const state = await page.evaluate(() => ({
        speakers: document.querySelectorAll("#log .msg.jarvis .speak-answer").length,
        kept: document.querySelectorAll("#log .jarvis-kept").length,
        spoken: window.__spoken.slice(),
      }));
      assert.equal(state.speakers, 0,
        "a speaker was offered on an answer that has to stay on screen");
      assert.equal(state.kept, 1, "the shell did not draw its kept-on-screen line");
      assert.deepEqual(state.spoken, [],
        "an answer that has to stay on screen reached the room");
      // And there is no side door: a click can only reach voice.speak, which is
      // the shell's wrapped speechSynthesis.speak - so ask it directly with the
      // answer's own words and it must still refuse.
      await page.evaluate((words) => {
        window.speechSynthesis.speak(new window.SpeechSynthesisUtterance(words));
      }, "Your test results came back, and here they are.");
      const after = await page.evaluate(() => window.__spoken.slice());
      assert.deepEqual(after, [],
        "the shell spoke a kept-on-screen answer when it was asked directly");
      await page.close();
    } finally {
      await browser.close();
    }
  });

  await check("B: an answer that used a sensitive saved fact shows no speaker either", async () => {
    const browser = await K.launch();
    try {
      const { page } = await openHud(browser, {
        iconsOn: true,
        // The other half of the rule: a sensitive saved fact went into this
        // answer, so it stays on screen (decision 13, first line of mayReadAloud).
        replies: [{
          text: "The appointment you saved is on Thursday at nine.",
          route: { injected_facts: 1, injected_sensitive: 1 },
        }],
      });
      await send(page, "when is my appointment", 1);
      await page.waitForFunction(() => Boolean(document.querySelector("#log .jarvis-kept")),
        null, { timeout: 8000 });
      const state = await page.evaluate(() => ({
        speakers: document.querySelectorAll("#log .msg.jarvis .speak-answer").length,
        spoken: window.__spoken.slice(),
      }));
      assert.equal(state.speakers, 0,
        "a speaker was offered on an answer that used a sensitive saved fact");
      assert.deepEqual(state.spoken, [],
        "an answer that used a sensitive saved fact reached the room");
      await page.close();
    } finally {
      await browser.close();
    }
  });

  /* ── B5. Turning it off takes the speakers away ────────────────────────── */

  await check("B: turning the switch off removes every speaker at once", async () => {
    const browser = await K.launch();
    try {
      const { page } = await openHud(browser, {
        iconsOn: true,
        replies: [{ text: "An answer with a speaker beside it.", route: {} }],
      });
      await send(page, "a question", 1);
      await page.waitForFunction(
        () => document.querySelectorAll("#log .msg.jarvis .speak-answer").length === 1,
        null, { timeout: 8000 });
      // The owner flips the switch in the Settings window: another document of
      // the same origin writes the key, which is exactly a `storage` event.
      await page.evaluate((key) => {
        localStorage.setItem(key, "false");
        window.dispatchEvent(new StorageEvent("storage", { key, newValue: "false" }));
      }, READ_ALOUD_ICONS_KEY);
      await page.waitForFunction(
        () => document.querySelectorAll("#log .msg.jarvis .speak-answer").length === 0,
        null, { timeout: 5000 });
      await page.evaluate(() => { window.__spoken = []; });
      // ...and the switch being off is not a way to speak it: there is nothing
      // to click any more.
      await page.evaluate(() => {
        const b = document.querySelector("#log .msg.jarvis");
        if (b) b.click();
      });
      assert.deepEqual(await page.evaluate(() => window.__spoken.slice()), [],
        "clicking a switched-off answer spoke it anyway");
      await page.close();
    } finally {
      await browser.close();
    }
  });
}

/* ── Result ──────────────────────────────────────────────────────────────── */

if (fails.length) {
  console.log(`\n${fails.length} failed:`);
  for (const name of fails) console.log(`  - ${name}`);
  process.exit(1);
}
console.log("\nall checks passed");
