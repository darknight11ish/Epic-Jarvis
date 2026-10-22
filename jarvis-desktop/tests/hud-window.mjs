/**
 * hud-window.mjs - "The big HUD window": the switch that shows or hides the
 * "Open the Jarvis bar" button in the big "Jarvis" window (the owner's
 * request of 2026-10-06; src/hud-window.js, src/hud-window-settings.js and
 * src-tauri/src/hud_bootstrap.js).
 *
 *     node tests/hud-window.mjs
 *
 * WHY THIS SUITE EXISTS, AND WHY IT NEEDS NO BROWSER. The button is drawn by
 * `hud_bootstrap.js`, which the desktop shell injects into the vendored HUD
 * page; the check that drives the real page is tests/hud.mjs, and it needs
 * Playwright. Playwright is not a dependency of this app (tests/README.md says
 * why), so on a machine without it that check does not run - and a setting
 * whose ONLY test is that one would be an untested setting. This suite is the
 * browser-free half, and it is not a copy of the page test's assertions:
 *
 *   * it runs `src-tauri/src/hud_bootstrap.js` itself, in a hand-made DOM just
 *     big enough for it (the shape tests/first-run-settings.mjs uses), for
 *     every value the key can hold - so "is the button drawn?" is answered by
 *     the real injected code, not by a grep;
 *   * it proves the bootstrap obeys a change made while the window is open
 *     (the `storage` event), and the unrelated-key case that must change
 *     nothing;
 *   * it proves the bootstrap and src/hud-window.js cannot drift: the same key,
 *     and the same answer to every stored value, from the two implementations;
 *   * it proves the Settings card exists, that every id its module reaches for
 *     is really on the page, and that the page loads the module as a real ES
 *     module (the defect of 2026-10-06: a module that will not parse kills the
 *     whole page, and Settings' own script with it).
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as S from "../src/hud-window.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const BOOT = read("src-tauri/src/hud_bootstrap.js");
const SETTINGS_HTML = read("src/settings.html");
const SETTINGS_JS = read("src/hud-window-settings.js");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── 1. The setting itself ───────────────────────────────────────────────── */

/** A localStorage stand-in: `null` for a browser that has none, and a
 *  thrower for one that cannot be read (private mode, cleared site data). */
function mem(initial = {}) {
  const store = { ...initial };
  return {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
    _store: store,
  };
}

const THROWING = {
  getItem() { throw new Error("private mode"); },
  setItem() { throw new Error("private mode"); },
};

await check("the key is namespaced with this window's others, and is one key", () => {
  assert.match(S.OPEN_BAR_KEY, /^jarvis\.[\w.]+$/, `"${S.OPEN_BAR_KEY}" is not namespaced`);
  assert.equal(S.OPEN_BAR_KEY, "jarvis.hud.openBar");
});

await check("the default is ON - the state the owner approved on 2026-10-06", () => {
  // Nothing stored: the button shows. This is the whole point of the default.
  assert.equal(S.openBarShown(mem()), true);
  // ON wins, either spelling.
  assert.equal(S.openBarShown(mem({ [S.OPEN_BAR_KEY]: "true" })), true);
  assert.equal(S.openBarShown(mem({ [S.OPEN_BAR_KEY]: "on" })), true);
  // OFF: the one spelling this app writes.
  assert.equal(S.openBarShown(mem({ [S.OPEN_BAR_KEY]: "false" })), false);
  // Any other stored value is off, which is notifications-prefs.js's own
  // `loadBool` rule ("true"/"on" is on, anything else is not) - the value the
  // bootstrap's second copy of the reading is held to below.
  for (const v of ["off", "", "0", "no", "yes", "ON", "True", "banana"]) {
    assert.equal(S.openBarShown(mem({ [S.OPEN_BAR_KEY]: v })), false, `"${v}" should be off`);
  }
});

await check("storage that cannot be read or written leaves the approved default alone", () => {
  assert.equal(S.openBarShown(THROWING), true);
  assert.equal(S.openBarShown(null), true);
  assert.equal(S.saveOpenBarShown(false, THROWING), false);
  assert.equal(S.saveOpenBarShown(false, null), false);
});

await check("saving round-trips, and says it worked", () => {
  const store = mem();
  assert.equal(S.saveOpenBarShown(false, store), true);
  assert.equal(store.getItem(S.OPEN_BAR_KEY), "false");
  assert.equal(S.openBarShown(store), false);
  assert.equal(S.saveOpenBarShown(true, store), true);
  assert.equal(S.openBarShown(store), true);
});

await check("the one-line description follows the switch", () => {
  assert.match(S.describeOpenBar(true), /^Shown:/);
  assert.match(S.describeOpenBar(false), /^Hidden:/);
  assert.notEqual(S.describeOpenBar(true), S.describeOpenBar(false));
});

/* ── 2. The bootstrap reads the same key and the same rule ───────────────── */

/** A DOM just big enough for hud_bootstrap.js: the elements it looks up, real
 *  node objects with a parent and children, and a registry of what
 *  createElement made so getElementById can find the button it adds. Anything
 *  the bootstrap grows a need for that this cannot meet is worth knowing here
 *  rather than in the app - so nothing is stubbed silently: an unknown tag
 *  still yields a real node. */
function makeNode(tag = "") {
  const node = {
    tag,
    id: "",
    className: "",
    textContent: "",
    title: "",
    href: "",
    rel: "",
    type: "",
    value: "",
    hidden: false,
    tabIndex: 0,
    disabled: false,
    dataset: {},
    style: {},
    attrs: {},
    listeners: {},
    children: [],
    parentNode: null,
    setAttribute(k, v) {
      this.attrs[k] = String(v);
      if (k === "id") this.id = String(v);
      if (k === "aria-hidden") this.ariaHidden = String(v);
    },
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    removeAttribute(k) { delete this.attrs[k]; },
    addEventListener(type, fn) { (this.listeners[type] || (this.listeners[type] = [])).push(fn); },
    removeEventListener() {},
    appendChild(child) { child.parentNode = this; this.children.push(child); return child; },
    insertBefore(child, before) {
      child.parentNode = this;
      const at = this.children.indexOf(before);
      if (at === -1) this.children.push(child);
      else this.children.splice(at, 0, child);
      return child;
    },
    removeChild(child) {
      const at = this.children.indexOf(child);
      if (at >= 0) this.children.splice(at, 1);
      child.parentNode = null;
      return child;
    },
    querySelector() { return null; },
    closest() { return null; },
  };
  return node;
}

/**
 * Run the injected bootstrap exactly as the shell runs it.
 *
 * `base` replaces __JARVIS_BASE__ (the shell substitutes the real address),
 * `saved` is what this computer's localStorage holds, and `shell` is whether
 * window.__TAURI__ is there at all - false is the HUD page served on its own
 * in a plain browser, which has no Jarvis bar to open.
 *
 * Returns the fake page and everything the run created.
 */
function runBootstrap({ saved = {}, shell = true, raw = null, layout = null } = {}) {
  const created = [];
  const page = {
    input: makeNode("textarea"),
    send: makeNode("button"),
  };
  page.input.id = "input";
  page.send.id = "send";
  const composer = makeNode("div");
  composer.appendChild(page.input);
  composer.appendChild(page.send);

  const head = makeNode("head");
  const documentElement = makeNode("html");
  // The real page always has a <body> by the time the injected bootstrap runs;
  // the stand-in needs one too, because H3 puts the shell/density DOM contract
  // on it (and on <html>).
  const body = makeNode("body");
  documentElement.body = body;
  /** What is IN the page: a node the page removed is not found here, exactly
   *  as `document.getElementById` behaves - a detached node still sitting in
   *  a "created" list would make the removal untestable. */
  const inPage = (id) => created.find((n) => n.id === id && n.parentNode) || null;
  const document = {
    readyState: "complete",
    head,
    body,
    documentElement,
    listeners: {},
    getElementById(id) {
      if (id === "input") return page.input;
      if (id === "send") return page.send;
      return inPage(id);
    },
    createElement(tag) { const n = makeNode(tag); created.push(n); return n; },
    querySelector() { return null; },
    addEventListener(type, fn) { (this.listeners[type] || (this.listeners[type] = [])).push(fn); },
    removeEventListener() {},
  };

  const store = { ...saved };
  const window = {
    localStorage: raw || {
      getItem: (k) => (k in store ? store[k] : null),
      setItem: (k, v) => { store[k] = String(v); },
      removeItem: (k) => { delete store[k]; },
    },
    listeners: {},
    addEventListener(type, fn) { (this.listeners[type] || (this.listeners[type] = [])).push(fn); },
    removeEventListener() {},
    dispatchEvent(event) {
      for (const fn of this.listeners[event.type] || []) fn(event);
      return true;
    },
    location: { origin: "http://tauri.localhost", href: "http://tauri.localhost/jarvis_hud.html" },
  };
  if (shell) {
    const invoked = [];
    let layoutAsks = 0;
    window.__invokes = invoked;
    // The shell's own feed, in the form hud_bootstrap.js defines it. The
    // shell pushes by evaluating a call to it - `__jarvisFeed("bar", true)`
    // for the Jarvis bar coming on screen and `("bar", false)` for it going
    // (lib.rs `push_to_hud`). Anything else is deliberately not delivered.
    window.__jarvisFeed = function (channel, payload) {
      if (channel === "bar") window.__barFeed = payload;
    };
    window.__TAURI__ = {
      core: {
        Channel: class { constructor() { this.onmessage = null; } },
        // The saved HUD layout is a separate, later section of the bootstrap;
        // it is counted here and covered by its own test, and its call is not
        // mixed into the legacy `__invokes` lists the button tests compare.
        invoke: (cmd, args) => {
          if (cmd === "get_hud_layout") {
            layoutAsks += 1;
            return Promise.resolve({ layout, source: layout ? "saved" : "none" });
          }
          invoked.push([cmd, args]);
          return Promise.resolve(null);
        },
      },
    };
    window.__layoutAsks = () => layoutAsks;
  }

  const source = BOOT.replace("__JARVIS_BASE__", JSON.stringify("http://127.0.0.1:4719"));
  // `console.info` is the only thing silenced: the bootstrap announces itself
  // once per run, and a real warning or error must still be visible.
  const quiet = Object.create(console);
  quiet.info = () => {};
  // eslint-disable-next-line no-new-func
  new Function("window", "document", "console", source)(window, document, quiet);

  /* The bootstrap defines the feed itself (its section 2), as it does in the
   * real page: this is the function the shell pushes into, not a stand-in. */
  const feed = window.__jarvisFeed;

  return {
    window,
    document,
    created,
    store,
    /** The button as the page has it now: null once it has been taken off. */
    button: () => inPage("hud-open-bar"),
    composer,
    /** What a write in ANOTHER Jarvis window delivers to this one. */
    storageEvent(key) {
      window.dispatchEvent({ type: "storage", key, target: window });
    },
    /** What the shell's `push_to_hud(app, "bar", visible)` evaluates in this
     *  page (src-tauri/src/windows.rs `publish_bar_state`): whether the Jarvis
     *  bar is on screen. This is the state the label follows. */
    barState(visible) {
      feed("bar", visible);
    },
    /** A push on some other channel: nothing to do with this button. */
    otherChannel(channel, payload) {
      feed(channel, payload);
    },
  };
}

await check("the bootstrap names the module's own key, so the two cannot drift", () => {
  // The bootstrap is a plain injected script and cannot import hud-window.js,
  // so it spells the key again. This is the check that keeps the two spellings
  // honest: a rename on either side fails here.
  const at = BOOT.indexOf("var OPEN_BAR_KEY");
  assert.ok(at > 0, "the bootstrap no longer names the key at all");
  const line = BOOT.slice(at, BOOT.indexOf("\n", at));
  assert.ok(line.includes(`"${S.OPEN_BAR_KEY}"`),
    `the bootstrap reads ${line.trim()}, not hud-window.js's ${S.OPEN_BAR_KEY}`);
  assert.doesNotMatch(BOOT, /__JARVIS_TOKEN__/, "the token has no business in this file");
});

await check("with nothing saved, the button is drawn beside the box - the approved default", () => {
  const run = runBootstrap({ shell: true });
  const button = run.button();
  assert.ok(button, "no #hud-open-bar was created with nothing stored");
  assert.equal(button.textContent, "Open the Jarvis bar");
  assert.equal(button.type, "button");
  assert.equal(button.className, "act primary hud-open-bar");
  // Beside the box, before it, exactly as PR #85 left it.
  assert.equal(run.composer.children.indexOf(button), 0, "the button is not first in the composer");
  assert.equal(run.composer.children.indexOf(run.document.getElementById("input")), 1);
  // The box itself is untouched: shown, in the tab order.
  assert.equal(run.document.getElementById("input").hidden, false);
  assert.equal(run.document.getElementById("input").tabIndex, 0);
  assert.equal(run.document.getElementById("send").hidden, false);
});

await check("saved off: the button is not drawn, and the box is left exactly as it was", () => {
  const run = runBootstrap({ saved: { [S.OPEN_BAR_KEY]: "false" }, shell: true });
  assert.equal(run.button(), null, "the button was drawn with the setting off");
  assert.equal(run.created.some((n) => n.id === "hud-open-bar"), false);
  // The reason this is cosmetic: hiding a button changes nothing else.
  assert.equal(run.document.getElementById("input").hidden, false);
  assert.equal(run.document.getElementById("input").tabIndex, 0);
  assert.equal(run.document.getElementById("send").hidden, false);
  assert.equal(run.document.getElementById("send").tabIndex, 0);
});

await check("the bootstrap and the module answer every stored value the same way", () => {
  // The value-by-value agreement, run rather than read: the module's reading is
  // the fixture and the bootstrap's own code is what is on trial.
  for (const value of [null, "true", "on", "false", "off", "", "0", "no", "yes", "ON", "True", "banana"]) {
    const saved = value === null ? {} : { [S.OPEN_BAR_KEY]: value };
    const shown = runBootstrap({ saved }).button() !== null;
    assert.equal(shown, S.openBarShown(mem(saved)),
      `stored ${JSON.stringify(value)}: the bootstrap drew the button=${shown}`);
  }
});

await check("storage that cannot be read at all leaves the button showing", () => {
  const run = runBootstrap({ shell: true, raw: { getItem() { throw new Error("private mode"); } } });
  assert.ok(run.button(), "an unreadable store must leave the approved default alone");
});

await check("in a plain browser there is no button, whatever the setting says", () => {
  // Served on its own (no shell) there is no Jarvis bar to open, so the button
  // was never added; the page keeps its own composer. hud.mjs drives the same
  // case in the real browser.
  for (const saved of [{}, { [S.OPEN_BAR_KEY]: "true" }]) {
    const run = runBootstrap({ saved, shell: false });
    assert.equal(run.button(), null, "the button must not be added without the shell");
    assert.equal(run.document.getElementById("input").hidden, false);
  }
});

await check("pressing the button asks the shell to open the Jarvis bar, and sends nothing else", async () => {
  const run = runBootstrap({ shell: true });
  const button = run.button();
  const clicks = button.listeners.click || [];
  assert.equal(clicks.length, 1, "the button has no click handler");
  clicks[0]();
  await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual(run.window.__invokes.map((c) => c[0]), ["hud_open_bar"],
    "the button must ask the shell for hud_open_bar, and nothing else");
});

await check("the label follows the bar: Open while it is hidden, Hide while it is shown", () => {
  // THE OWNER'S ASK (2026-10-09, with a screenshot): the button beside the
  // HUD's chat box said "Open the Jarvis bar" whether the bar was open or
  // not. Whether it is on screen reaches this page from the shell, which
  // knows (src-tauri/src/windows.rs `publish_bar_state`, pushed on the feed's
  // own "bar" channel) - never guessed from a click.
  const run = runBootstrap({ shell: true });
  const button = run.button();

  // Nothing has said the bar is up: the label is the wording that was there.
  assert.equal(button.textContent, "Open the Jarvis bar");
  assert.equal(button.textContent, button.title, "the visible label and its tooltip disagree");

  run.barState(true);
  assert.equal(button.textContent, "Hide the Jarvis bar", "the label did not follow the bar being open");
  // A screen reader must not contradict the visible label (the same wording,
  // not the old "it opens now" line, which would be false here).
  assert.equal(button.title, button.textContent, "the tooltip contradicts the visible label");
  assert.doesNotMatch(button.title, /opens now/, "a bar already open is still announced as opening");

  run.barState(false);
  assert.equal(button.textContent, "Open the Jarvis bar", "the label did not follow the bar closing");
  assert.equal(button.title, button.textContent, "the tooltip contradicts the visible label");
});

await check("a push about something else leaves the label alone", () => {
  // The feed carries the whole event stream too (the shim's own `deliver`),
  // and only the bar channel is this button's business. The payload is a real
  // frame, so a handler that ran would really run.
  const run = runBootstrap({ shell: true });
  const before = run.button().textContent;
  run.otherChannel("event", { kind: "power", id: 1, data: { mode: "awake", by: "owner" } });
  assert.equal(run.button().textContent, before, "an unrelated push moved the label");
});

await check("clicking it is a real toggle: open when hidden, hide when shown", async () => {
  const run = runBootstrap({ shell: true });
  const click = async () => {
    const button = run.button();
    assert.ok(button, "the button is gone");
    button.listeners.click[0]();
    await new Promise((r) => setTimeout(r, 0));
  };

  // Hidden: one click opens the bar.
  await click();
  assert.deepEqual(run.window.__invokes.map((c) => c[0]), ["hud_open_bar"],
    "with the bar hidden, the button must ask the shell to open it");

  // The shell says it is up now: the same click must close it.
  run.barState(true);
  run.window.__invokes.length = 0;
  await click();
  assert.deepEqual(run.window.__invokes.map((c) => c[0]), ["hide_quickbar"],
    "with the bar shown, the button must ask the shell to hide it");

  // And back the other way, so it is a toggle and not a one-way door.
  run.barState(false);
  run.window.__invokes.length = 0;
  await click();
  assert.deepEqual(run.window.__invokes.map((c) => c[0]), ["hud_open_bar"],
    "the button must open the bar again once it is hidden");
});

await check("a change made in Settings while the window is open is obeyed at once", () => {
  // The button that was showing goes...
  const on = runBootstrap({ shell: true });
  assert.ok(on.button(), "the button should be there to begin with");
  on.store[S.OPEN_BAR_KEY] = "false";
  on.storageEvent(S.OPEN_BAR_KEY);
  assert.equal(on.button(), null, "the button stayed after the setting was turned off");
  assert.equal(on.document.getElementById("input").hidden, false, "the box must be untouched");

  // ...and one that was hidden comes back.
  const off = runBootstrap({ saved: { [S.OPEN_BAR_KEY]: "false" }, shell: true });
  off.store[S.OPEN_BAR_KEY] = "true";
  off.storageEvent(S.OPEN_BAR_KEY);
  assert.ok(off.button(), "the button did not come back when the setting was turned on");
  assert.equal(off.document.getElementById("hud-open-bar").textContent, "Open the Jarvis bar");
});

await check("another window's unrelated write changes nothing", () => {
  const run = runBootstrap({ saved: { [S.OPEN_BAR_KEY]: "false" }, shell: true });
  run.storageEvent("jarvis.theme");
  assert.equal(run.button(), null, "an unrelated key drew the button");
  const on = runBootstrap({ shell: true });
  on.storageEvent("jarvis.theme");
  assert.ok(on.button(), "an unrelated key removed the button");
  // A cleared store (`clear()`) reports key null: it must be re-read.
  on.store[S.OPEN_BAR_KEY] = "false";
  on.storageEvent(null);
  assert.equal(on.button(), null, "a cleared store was not re-read");
});

/* ── 3. The Settings card ────────────────────────────────────────────────── */

await check("the card is on the Settings page, with every id its module reaches for", () => {
  assert.match(SETTINGS_HTML, /<section class="card" id="hud-window">/,
    "no <section class=\"card\" id=\"hud-window\"> in settings.html");
  const at = SETTINGS_HTML.indexOf('id="hud-window"');
  const card = SETTINGS_HTML.slice(at, SETTINGS_HTML.indexOf("</section>", at));
  assert.match(card, /<h2>The big HUD window<\/h2>/, "the card has no heading");
  assert.doesNotMatch(card, /\bhidden\b/, "the card starts hidden");
  // The switch itself, and what it does, in the owner's own words.
  assert.match(card, /<input id="hud-open-bar-show" type="checkbox"/);
  assert.match(card, /Show the "Open the Jarvis bar" button/);
  assert.match(card, /changes at once|at once/);
  const ids = [...SETTINGS_JS.matchAll(/\$\("([\w-]+)"\)/g)].map((m) => m[1]);
  assert.ok(ids.length >= 2, `only ${ids.length} ids read - is the module still wired up?`);
  for (const id of new Set(ids)) {
    assert.ok(SETTINGS_HTML.includes(`id="${id}"`), `settings.html has no id="${id}"`);
  }
});

await check("the page loads the module as a real ES module", () => {
  assert.match(SETTINGS_HTML, /<script type="module" src="hud-window-settings\.js"><\/script>/,
    "the module is not loaded with type=\"module\"");
});

await check("the card raises nothing: no Rust command, no card, no held change", () => {
  // Cosmetic, so the whole card is localStorage and nothing else. A command
  // here would need surfaces.toml, capabilities/settings.json and an approval
  // path - the opposite of what this setting is.
  // H2 (2026-10-22) adds exactly ONE command to this card: `open_hud_edit`,
  // a navigation door that shows the HUD window in edit mode. It saves no
  // setting and raises no card; nothing else may appear here.
  const withoutNavigation = SETTINGS_JS.replace(/invoke\s*\(\s*"open_hud_edit"\s*\)/g, "");
  assert.doesNotMatch(withoutNavigation, /invoke\s*\(/,
    "the card calls a Rust command other than the one navigation door");
  assert.match(SETTINGS_JS, /invoke\s*\(\s*"open_hud_edit"\s*\)/,
    "the card lost its Edit HUD navigation button");
  // Words in comments describe what the card does NOT do ("raises no card",
  // "approves nothing"); the check is about the CODE.
  const code = SETTINGS_JS.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
  assert.doesNotMatch(code, /decide|approve|amend/, "the card decides something");
  assert.match(SETTINGS_JS, /import[\s\S]*from "\.\/hud-window\.js"/,
    "the card does not read its setting from hud-window.js");
});

await check("the module can be imported without a DOM, as the tests do", async () => {
  // No `window` and no `document` at import time - this is plain Node, so the
  // import itself is the proof: the module would throw here if it reached for
  // either. `document` really is absent, so its own readyState guard took the
  // branch that runs nothing.
  assert.equal(typeof globalThis.document, "undefined");
  const mod = await import("../src/hud-window-settings.js");
  assert.equal(typeof mod.initHudWindowSettings, "function");
});

/* ── 4. The HUD's three layouts (2026-10-20) ─────────────────────────────── *
 *  The setting half of the owner's "3 different UIs for the jarvis HUD":
 *  the key, the three ids, the reading and the saving are all in hud-window.js
 *  (the same module as the switch above, for the same reason: one key, read by
 *  the window that changes it and obeyed by the window that wears it). The
 *  page's own half is driven in tests/hud.mjs, which needs Playwright; this is
 *  the browser-free half, so the setting is never untested.
 * ------------------------------------------------------------------------ */

await check("the layout key is namespaced with this window's other keys, and is one key", () => {
  assert.match(S.HUD_LAYOUT_KEY, /^jarvis\.[\w.]+$/,
    `"${S.HUD_LAYOUT_KEY}" is not namespaced like the others`);
  assert.equal(S.HUD_LAYOUT_KEY, "jarvis.hud.layout");
  assert.notEqual(S.HUD_LAYOUT_KEY, S.OPEN_BAR_KEY, "two settings, one key");
});

await check("the three layouts, default first, each with a name, a glyph and one line", () => {
  assert.deepEqual(S.HUD_LAYOUTS, ["cockpit", "studio", "ambient"]);
  for (const id of S.HUD_LAYOUTS) {
    const info = S.HUD_LAYOUT_INFO[id];
    assert.ok(info, `${id} has no HUD_LAYOUT_INFO entry`);
    for (const field of ["label", "blurb", "glyph"]) {
      assert.equal(typeof info[field], "string", `${id}.${field} is not a string`);
      assert.ok(info[field].trim().length > 0, `${id}.${field} is empty`);
    }
    assert.doesNotMatch(info.blurb, /\n/, `${id}'s one line has a line break`);
  }
  // The work order's own three names, in the owner's words.
  assert.match(S.HUD_LAYOUT_INFO.cockpit.label, /Command Cockpit/);
  assert.match(S.HUD_LAYOUT_INFO.studio.label, /Studio/);
  assert.match(S.HUD_LAYOUT_INFO.ambient.label, /Ambient/);
});

await check("a stored layout is read as this build reads it - anything unknown is Cockpit", () => {
  assert.equal(S.normaliseHudLayout("cockpit"), "cockpit");
  assert.equal(S.normaliseHudLayout("studio"), "studio");
  assert.equal(S.normaliseHudLayout("ambient"), "ambient");
  for (const bad of [null, undefined, "", "STUDIO", "cockpit ", "not-a-layout", 3, {}, []]) {
    assert.equal(S.normaliseHudLayout(bad), "cockpit", `normaliseHudLayout(${JSON.stringify(bad)})`);
  }
});

await check("with nothing stored, or storage unreadable, the default is Cockpit", () => {
  // A fresh install: nothing stored at all.
  assert.equal(S.readHudLayout(mem()), "cockpit");
  // The one value this app writes for each layout.
  for (const id of S.HUD_LAYOUTS) {
    assert.equal(S.readHudLayout(mem({ [S.HUD_LAYOUT_KEY]: id })), id);
  }
  // An older or hand-edited value this build does not know.
  assert.equal(S.readHudLayout(mem({ [S.HUD_LAYOUT_KEY]: "ember" })), "cockpit");
  // Storage that refuses to be read (private mode, cleared site data): the
  // default, never a throw into the page.
  assert.equal(S.readHudLayout(THROWING), "cockpit");
  assert.equal(S.readHudLayout(null), "cockpit");
});

await check("saving writes the normalised id, and says whether it could write", () => {
  const store = mem();
  assert.equal(S.saveHudLayout("studio", store), true);
  assert.equal(store.getItem(S.HUD_LAYOUT_KEY), "studio");
  assert.equal(S.saveHudLayout("studio", store), true);
  assert.equal(S.saveHudLayout("bogus", store), true);
  assert.equal(store.getItem(S.HUD_LAYOUT_KEY), "cockpit",
    "an unknown layout was saved instead of the default");
  // A store that refuses (private mode): false, and no pretend success.
  assert.equal(S.saveHudLayout("ambient", THROWING), false);
  assert.equal(S.saveHudLayout("ambient", null), false);
});

await check("the card's status line names the chosen layout in words", () => {
  for (const id of S.HUD_LAYOUTS) {
    const line = S.describeHudLayout(id);
    assert.match(line, new RegExp(S.HUD_LAYOUT_INFO[id].label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
      `describeHudLayout(${id}) does not name it: ${line}`);
  }
  // An unknown id describes the default, exactly as the page would wear it.
  assert.match(S.describeHudLayout("bogus"), /Command Cockpit/);
});

await check("the Settings card offers the seven presets through the layout store", () => {
  const at = SETTINGS_HTML.indexOf('id="hud-window"');
  assert.ok(at > 0, "settings.html has no #hud-window card");
  const card = SETTINGS_HTML.slice(at, SETTINGS_HTML.indexOf("</section>", at));
  assert.match(card, /<fieldset class="theme-list" id="hud-layout-list">/,
    "the card has no layout picker fieldset");
  assert.match(card, /<legend class="label" id="hud-layout-legend">HUD layouts<\/legend>/);
  assert.match(card, /id="hud-layout-status"/, "the picker has no status line");
  // The rows are built from the preset table at run time (as the theme picker's
  // are from THEME_INFO), so the page cannot list a preset the module does not
  // know about. The persistence rides through the layout store, never a
  // direct `invoke` in this panel - the store is the one place that talks to
  // Rust, and it is what the HUD bootstrap reads too.
  assert.match(SETTINGS_JS, /presetRows/, "the card does not read the preset rows");
  assert.match(SETTINGS_JS, /choosePreset/, "the card does not save through the store");
  assert.match(SETTINGS_JS, /loadLayout/, "the card does not read the saved layout");
  // The picker’s persistence must still ride the layout store. H2’s one
  // navigation command (open_hud_edit) is allowed and is not a picker write.
  const picker = SETTINGS_JS.replace(/invoke\s*\(\s*"open_hud_edit"\s*\)/g, "")
    .replace(/globalThis\.__TAURI__/g, "");
  assert.doesNotMatch(picker, /invoke\s*\(/,
    "the layout picker talks to Rust itself instead of the layout store");
});

await check("H3: the page renders the store's shell; no legacy look control remains", () => {
  // F1 removed the three header pills and the localStorage road; H3 (Q5)
  // replaced the page's three looks with the preset's own shell/density.
  const HUD = read("src/jarvis_hud.html");
  const EDIT = read("src/hud-edit.js");
  assert.doesNotMatch(HUD,
    /localStorage\s*\.\s*(get|set|remove)Item\(\s*["']jarvis\.hud\.layout/,
    "the page still reads or writes the retired layout key");
  assert.ok(!HUD.includes("data-hud-layout-choice"),
    "the page still renders the legacy layout pills");
  assert.ok(!HUD.includes("data-hud-layout"),
    "the page still keys off the retired data-hud-layout look");
  assert.ok(!HUD.includes("jarvis:hud-look"),
    "the page still obeys the retired look event");
  assert.match(HUD, /body\.dataset\.hudShell/,
    "the page never sets body.dataset.hudShell");
  assert.match(HUD, /body\.dataset\.hudDensity/,
    "the page never sets body.dataset.hudDensity");
  assert.match(HUD, /jarvis:hud-shell/,
    "the page does not obey the bootstrap's saved-shell event");
  assert.match(HUD, /jarvis\.hud\.preview/,
    "the page never reads the first-paint preview mirror");
  assert.match(EDIT, /hud-layout-badge/, "no Layout badge beside Edit HUD");
  assert.match(EDIT, /Layout: \$\{name\}/, "the badge does not name the saved layout");
  assert.match(EDIT, /isUserLayout\(layout\)/, "the badge ignores the owner's own layout name");
  // The one-write rule survives H3: the layout library is saved through the
  // SAME command, so the capability files do not change.
  const CAP = read("src-tauri/capabilities/hud.json");
  assert.match(CAP, /"hud-layout-write"/);
  assert.equal((CAP.match(/"hud-[a-z-]+"/g) || []).filter((name) => name.endsWith('-write"')).length,
    1, "the HUD window holds more than one write entry");
});

await check("H3: the bootstrap renders the saved preset's shell, density and opening tab", async () => {
  const layout = {
    version: 1,
    id: "quiet",
    name: "Quiet",
    base_preset: "quiet",
    shell_template: "two-column-left",
    density: "comfortable",
    default_stage_tab: "talk",
    cards: [],
  };
  const run = runBootstrap({ shell: true, layout });
  assert.equal(run.window.__layoutAsks(), 1, "the bootstrap did not read the saved layout");
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(run.document.documentElement.getAttribute("data-hud-shell"),
    "two-column-left", "the preset's own shell was not rendered");
  assert.equal(run.document.documentElement.getAttribute("data-hud-density"),
    "comfortable", "the preset's own density was not rendered");
  assert.equal(run.document.body.dataset.hudShell, "two-column-left",
    "the body contract was not put in step");
  assert.deepEqual(run.window.__jarvisHudLayout.base_preset, "quiet",
    "the document was not left for the editor");
  // First-paint mirror: the same facts, clamped, for the next window.
  const preview = JSON.parse(run.window.localStorage.getItem("jarvis.hud.preview"));
  assert.deepEqual(preview, { shell_template: "two-column-left",
    density: "comfortable", default_stage_tab: "talk" });
  // The old alias map is gone: a shell value is passed through, not mapped.
  const studio = runBootstrap({ shell: true, layout: { ...layout, base_preset: "studio",
    id: "studio", name: "Studio", shell_template: "split-stage" } });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(studio.document.documentElement.getAttribute("data-hud-shell"), "split-stage");
});

await check("with no saved layout, or no shell, the page's own look is left alone", async () => {
  const none = runBootstrap({ shell: true, layout: null });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(none.document.documentElement.getAttribute("data-hud-shell"), null,
    "an empty store changed the page's look");
  const browser = runBootstrap({ shell: false, layout: null });
  assert.equal(browser.window.__layoutAsks, undefined,
    "a page served on its own has no shell command to ask");
});

if (fails.length) {
  console.error(`\n${fails.length} test(s) failed`);
  process.exit(1);
} else {
  console.log("\nAll hud-window tests passed!");
}
