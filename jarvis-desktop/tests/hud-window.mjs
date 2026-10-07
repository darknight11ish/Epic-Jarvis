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
function runBootstrap({ saved = {}, shell = true, raw = null } = {}) {
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
  /** What is IN the page: a node the page removed is not found here, exactly
   *  as `document.getElementById` behaves - a detached node still sitting in
   *  a "created" list would make the removal untestable. */
  const inPage = (id) => created.find((n) => n.id === id && n.parentNode) || null;
  const document = {
    readyState: "complete",
    head,
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
    window.__invokes = invoked;
    window.__TAURI__ = {
      core: {
        Channel: class { constructor() { this.onmessage = null; } },
        invoke: (cmd, args) => { invoked.push([cmd, args]); return Promise.resolve(null); },
      },
    };
  }

  const source = BOOT.replace("__JARVIS_BASE__", JSON.stringify("http://127.0.0.1:4719"));
  // `console.info` is the only thing silenced: the bootstrap announces itself
  // once per run, and a real warning or error must still be visible.
  const quiet = Object.create(console);
  quiet.info = () => {};
  // eslint-disable-next-line no-new-func
  new Function("window", "document", "console", source)(window, document, quiet);

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
  assert.doesNotMatch(SETTINGS_JS, /invoke\s*\(/, "the card calls a Rust command");
  assert.doesNotMatch(SETTINGS_JS, /decide|approve|amend/, "the card decides something");
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

if (fails.length) {
  console.error(`\n${fails.length} test(s) failed`);
  process.exit(1);
} else {
  console.log("\nAll hud-window tests passed!");
}
