/**
 * first-run-settings.mjs - the "Set up Jarvis" card, and the one rule it must
 * not break.
 *
 *     node tests/first-run-settings.mjs
 *
 * WHAT THIS IS
 *
 * The owner's approved option 8A (2026-10-06): the handful of settings that
 * matter on the first run, in one place, in plain words, each raising its
 * approval card where the project's rules require one.
 *
 * The unacceptable outcome is named in the task: "a page that sets a setting
 * without its card would break the project's own rule 4". So the central
 * check here is not about layout - it is that every control this card draws
 * goes through the SAME Rust command that setting's own card already uses,
 * and that every one of those commands is already granted to the settings
 * window. A new command here would mean a new ACL entry, and this suite fails
 * rather than letting one arrive unnoticed.
 *
 * It reads files and runs the module against a small hand-made DOM. It needs
 * no browser, so it runs anywhere `node` does (the shape tests/onboarding.mjs
 * and tests/brain-settings-door.mjs use).
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const read = (f) => readFileSync(join(SRC, f), "utf8");

const HTML = read("settings.html");
const JS = read("first-run-settings.js");
const CSS = read("settings.css");
const SETTINGS_JS = read("settings.js");
const CAPABILITY = JSON.parse(
  readFileSync(join(HERE, "..", "src-tauri", "capabilities", "settings.json"), "utf8"));
const SURFACES = readFileSync(
  join(HERE, "..", "src-tauri", "permissions", "surfaces.toml"), "utf8");

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

/* ── The card is in the page, and it is the FIRST thing on it ────────────── */

/** The whole `<section … id="ID" …>…</section>` for one card. */
function section(id) {
  const open = new RegExp(`<section\\b[^>]*\\bid="${id}"[^>]*>`).exec(HTML);
  assert.ok(open, `no <section id="${id}"> in settings.html`);
  const end = HTML.indexOf("</section>", open.index);
  assert.ok(end > open.index, `the ${id} card is never closed`);
  return {
    tag: open[0],
    all: HTML.slice(open.index, end + "</section>".length),
    at: open.index,
  };
}

const card = section("first-run");

await check("the settings page has the card, before Connection", () => {
  // "In the order a person would do them" starts with where the card sits:
  // the first thing under the page's own heading, not buried in Rare.
  const connection = section("connection");
  assert.ok(card.at < connection.at, "the Set up Jarvis card is below Connection");
  assert.match(card.all, /<h2>Set up Jarvis<\/h2>/, "the card has no heading");
  // It is a plain card, like every other one in this window: no `hidden` in
  // its own markup, so it is on screen the moment Settings opens.
  assert.doesNotMatch(card.tag, /\bhidden\b/, "the card starts hidden");
});

await check("the jump list points at it first, under Everyday", () => {
  const nav = HTML.slice(HTML.indexOf('class="settings-jump"'), HTML.indexOf("</nav>"));
  const everyday = nav.slice(nav.indexOf("Everyday"));
  assert.match(everyday, /<a href="#first-run">Set up Jarvis<\/a>/,
    "the jump list has no Set up Jarvis row");
  const first = everyday.indexOf("<a href=");
  assert.equal(everyday.slice(first, first + 40).includes("#first-run"), true,
    "Set up Jarvis is not the first jump row under Everyday");
});

await check("the page loads the module as a real ES module", () => {
  // The defect fixed on 2026-10-06: a `settings.js` the browser could not
  // parse as a module killed every panel on the page at once. The gate for it
  // lives in ci.yml's frontend job (a bare `node --check` on a `.js` file
  // parses it as CommonJS and is not enough); this only asserts the page
  // really loads it that way, and before settings.js, so a failure in the new
  // module cannot take the whole page's own script down with it.
  assert.match(HTML, /<script type="module" src="first-run-settings\.js"><\/script>/,
    "the module is not loaded with type=\"module\"");
  assert.ok(HTML.indexOf('src="first-run-settings.js"') < HTML.indexOf('src="settings.js"'),
    "the new module loads after settings.js");
});

/* ── Every element the module reaches for really exists ──────────────────── */

await check("every id the module uses is an id the page has", () => {
  const ids = [...JS.matchAll(/\$\("([\w-]+)"\)/g)].map((m) => m[1]);
  assert.ok(ids.length >= 8, `only ${ids.length} ids read - is the module still wired up?`);
  for (const id of new Set(ids)) {
    assert.ok(HTML.includes(`id="${id}"`), `settings.html has no id="${id}"`);
  }
});

await check("the card's own three states are all in the markup", () => {
  // The asking state, the finished line, and the way back. A card that can be
  // dismissed must always say how to get it back.
  for (const id of ["fr-body-plain", "fr-body-full", "fr-rows", "fr-done", "fr-again", "fr-again-line"]) {
    assert.ok(card.all.includes(`id="${id}"`), `the card has no #${id}`);
  }
  assert.match(card.all, /id="fr-done"[^>]*type="button"/, "#fr-done is not a plain button");
  assert.match(card.all, /id="fr-again"[^>]*>Set up again</, "#fr-again does not say what it does");
});

await check("the module's own CSS is in the page's stylesheet", () => {
  for (const cls of [".fr-rows", ".fr-row"]) {
    assert.ok(CSS.includes(cls), `settings.css has no ${cls}`);
  }
});

/* ── Rule 4: nothing is written without its card ────────────────────────── */

/** Every command name a file invokes with a literal first argument. */
function invokedIn(text) {
  return new Set([...text.matchAll(/invoke\(\s*"([a-z0-9_]+)"/g)].map((m) => m[1]));
}

/** The `allow-*` names the settings window's capability can reach. */
function grantedToSettings() {
  const allowed = new Set();
  const sets = {};
  for (const m of SURFACES.matchAll(/\[\[set\]\]\s*identifier\s*=\s*"([^"]+)"(.*?)(?=\n\[\[set\]\]|\Z)/gs)) {
    sets[m[1]] = new Set([...m[2].matchAll(/"(allow-[a-z0-9-]+)"/g)].map((x) => x[1]));
  }
  for (const name of CAPABILITY.permissions) {
    if (name.startsWith("allow-")) allowed.add(name);
    if (sets[name]) for (const p of sets[name]) allowed.add(p);
  }
  return allowed;
}

await check("CONTROL: every command this card calls is already granted to Settings", () => {
  const granted = grantedToSettings();
  const mine = [...invokedIn(JS)];
  assert.ok(mine.length >= 6, `only ${mine.length} commands found - the module's calls changed shape`);
  const missing = mine.filter((c) => !granted.has(`allow-${c.replace(/_/g, "-")}`));
  assert.deepEqual(missing, [],
    `this card calls ${missing.join(", ")}, which the settings window is not granted - ` +
    "a new command here needs surfaces.toml, capabilities/settings.json and the full convention");
});

await check("all four settings reuse the SAME command their own card uses", () => {
  // Not "a command that changes the same thing": the identical one, so the
  // approval card is raised by the one code path in each case. Each pair is
  // (the command this card calls, the command the setting's own card calls).
  const pairs = [
    ["set_chat_card", "settings.js"],
    ["set_supervision", "settings.js"],
    ["set_api_settings", "settings.js"],
    ["set_voice_setting", "voice-panel.js"],
  ];
  for (const [command, owner] of pairs) {
    assert.ok(invokedIn(JS).has(command), `first-run-settings.js never calls ${command}`);
    const other = read(owner);
    assert.ok(invokedIn(other).has(command), `${owner} does not call ${command} - is it still the same path?`);
  }
  // And the two that raise a card are the ones that raise it on their own
  // page, so this card cannot have grown an approval of its own. Matched as
  // CALLS, not as words: the card legitimately says "Waiting for your
  // approval" in its status line.
  const code = JS.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/\/\/[^\n]*/g, " ");
  assert.ok(!/\b(decide|resolveApproval|approveCard|amend)\s*\(/.test(code),
    "the module decides an approval somewhere");
});

await check("the reads are the same reads those cards do, so nothing is guessed", () => {
  for (const [command, owner] of [
    ["get_second_card", "settings.js"],
    ["supervisor_status", "settings.js"],
    ["get_api_settings", "settings.js"],
    ["get_voice_status", "settings.js"],
  ]) {
    assert.ok(invokedIn(JS).has(command), `first-run-settings.js never reads ${command}`);
    assert.ok(invokedIn(read(owner)).has(command), `${owner} no longer reads ${command}`);
  }
});

await check("the read-aloud ids are the voice table's own two", () => {
  // `voice-training.js`'s MEMORY table. Writing a third id would be a setting
  // the backend does not have.
  const training = read("voice-training.js");
  const ids = [...training.matchAll(/id: "(memory_\w+)"/g)].map((m) => m[1]);
  const used = [...JS.matchAll(/"((?:memory)_\w+)"/g)].map((m) => m[1]);
  assert.ok(used.length >= 2, "the module never names the memory setting's values");
  for (const id of new Set(used)) {
    assert.ok(ids.includes(id), `"${id}" is not one of voice-training.js's MEMORY ids (${ids.join(", ")})`);
  }
});

/* ── The skip, and the way back ─────────────────────────────────────────── */

await check("the marker is a version, following ONBOARDING_VERSION", () => {
  // "Check how ONBOARDING_VERSION already records 'this person has seen it'
  // and follow that pattern rather than inventing a second one." A version
  // number, never a yes/no - the old `onboarding_seen` boolean is exactly
  // what commands.rs says could not tell an old walkthrough from a new one.
  assert.match(JS, /const SETUP_VERSION = \d+;/, "there is no version constant");
  assert.match(JS, /Number\(raw\) >= SETUP_VERSION/,
    "the stored marker is not read as a version");
  assert.match(JS, /localStorage\.setItem\(SETUP_SEEN_KEY, String\(SETUP_VERSION\)\)/,
    "the marker is not written as the current version");
  assert.ok(!/setup_seen["'\s]*,\s*(true|false)/.test(JS), "a plain yes/no marker appeared");
  // The key is namespaced the way this window's other key is.
  assert.match(JS, /const SETUP_SEEN_KEY = "jarvis\.[\w.]+"/, "the storage key is not namespaced");
});

await check("a browser that cannot store the marker keeps the card up", () => {
  // The safe way round: the card may never claim the owner has seen it.
  assert.match(JS, /catch \{[\s\S]{0,200}?return false;\s*\}/,
    "a storage failure does not fall back to 'not seen'");
});

/* ── The module runs, against a small hand-made DOM ─────────────────────── */

/**
 * A DOM just big enough for this module: real element objects, so the module's
 * own `box.querySelector(".fr-controls")` works and a mistake in the module
 * shows up here as a mistake rather than as a stub that quietly returned null.
 * Deliberately tiny - if the module grows a need this cannot meet, that is
 * worth knowing here rather than in the app.
 */
function makeNode(tag) {
  const node = {
    tag,
    className: "",
    textContent: "",
    hidden: false,
    dataset: {},
    children: [],
    value: "",
    checked: false,
    disabled: false,
    type: "",
    spellcheck: false,
    autocomplete: "",
    placeholder: "",
    listeners: {},
    attrs: {},
    append(...kids) { this.children.push(...kids); return this; },
    appendChild(kid) { this.children.push(kid); return kid; },
    replaceChildren(...kids) { this.children = kids; return this; },
    // Only the selectors this module actually uses: `#id`, `.class` and a
    // bare tag name.
    querySelector(sel) {
      const match = (kid) => {
        if (sel.startsWith("#")) return kid.id === sel.slice(1);
        if (sel.startsWith(".")) return String(kid.className || "").split(/\s+/).includes(sel.slice(1));
        return kid.tag === sel;
      };
      const found = [];
      const walk = (n) => {
        for (const kid of n.children || []) {
          if (match(kid)) found.push(kid);
          walk(kid);
        }
      };
      walk(this);
      return found[0] || null;
    },
    querySelectorAll(sel) {
      const all = [];
      const walk = (n) => {
        for (const kid of n.children || []) {
          all.push(kid);
          walk(kid);
        }
      };
      walk(this);
      if (sel.startsWith(".")) {
        const cls = sel.slice(1);
        return all.filter((n) => String(n.className || "").split(/\s+/).includes(cls));
      }
      if (sel.startsWith("#")) return all.filter((n) => n.id === sel.slice(1));
      return all.filter((n) => n.tag === sel);
    },
    addEventListener(kind, fn) { (this.listeners[kind] ||= []).push(fn); },
    setAttribute(name, value) { this.attrs[name] = value; },
    scrollIntoView() { this.scrolled = true; },
  };
  return node;
}

function fakeDom({ stored = null, refuseWrites = false } = {}) {
  const ids = ["first-run", "fr-body-plain", "fr-body-full", "fr-state", "fr-status",
    "fr-rows", "fr-done", "fr-again", "fr-again-line", "faq", "asks-first", "connection"];
  const byId = new Map();
  for (const id of ids) {
    const el = makeNode("div");
    el.id = id;
    byId.set(id, el);
  }
  let value = stored;
  return {
    els: byId,
    document: {
      readyState: "complete",
      getElementById: (id) => byId.get(id) || null,
      createElement: (tag) => makeNode(tag),
      addEventListener() {},
    },
    localStorage: {
      getItem: () => value,
      setItem(_key, next) {
        if (refuseWrites) throw new Error("this store refuses writes");
        value = String(next);
      },
      removeItem() { value = null; },
      /** What the module actually drew under a row, for the checks below. */
      _value: () => value,
    },
    pick(className) { return byId.get("fr-rows").querySelector(`.${className}`); },
  };
}

/**
 * Load a fresh copy of the module over a given stub, with no Tauri present.
 *
 * The stub stays installed - the module reads `document` again every time a
 * control is pressed, not only once at load - so the caller must put the real
 * globals back. `loadModule` returns the undo for exactly that.
 */
async function loadModule(stub) {
  const previous = { document: globalThis.document, localStorage: globalThis.localStorage };
  globalThis.document = stub.document;
  globalThis.localStorage = stub.localStorage;
  try {
    // A query string so node imports a fresh copy each time: module state
    // (the `painting` guard, the built rows) must not leak between checks.
    await import(`./../src/first-run-settings.js?case=${Math.random()}`);
    // `initFirstRunSettings` starts the read without awaiting it - the window
    // is not blocked on a backend that is not running - so let the pending
    // paint settle before anything is read back.
    await new Promise((resolve) => setTimeout(resolve, 0));
    return () => {
      globalThis.document = previous.document;
      globalThis.localStorage = previous.localStorage;
    };
  } catch (error) {
    globalThis.document = previous.document;
    globalThis.localStorage = previous.localStorage;
    throw error;
  }
}

await check("a fresh install meets the card; a finished one meets the line", async () => {
  const fresh = fakeDom({ stored: null });
  const unloadFresh = await loadModule(fresh);
  try {
    assert.equal(fresh.els.get("fr-body-full").hidden, false,
      "the questions are hidden on a fresh install");
    assert.equal(fresh.els.get("fr-done").hidden, false, "there is no way to finish the card");
    assert.equal(fresh.els.get("fr-again").hidden, true, "the way back is offered before it is needed");
  } finally {
    unloadFresh();
  }

  // Seen at the current version: the questions fold away, the way back shows.
  const after = fakeDom({ stored: "1" });
  const unloadAfter = await loadModule(after);
  try {
    assert.equal(after.els.get("fr-body-plain").hidden, true,
      "the card still asks on someone who has finished it");
    assert.equal(after.els.get("fr-rows").hidden, true, "the questions are still drawn");
    assert.equal(after.els.get("fr-again").hidden, false, "there is no way back to the card");
    assert.equal(after.els.get("fr-again-line").hidden, false, "the finished line is not shown");
  } finally {
    unloadAfter();
  }
});

await check("a newer version of the card is shown once more", async () => {
  // What the version number is FOR: raising SETUP_VERSION shows the card
  // again to someone who closed an older one.
  const older = fakeDom({ stored: "0" });
  const unload = await loadModule(older);
  try {
    assert.equal(older.els.get("fr-body-full").hidden, false,
      "an older stored version does not bring the card back");
  } finally {
    unload();
  }
});

await check("every switch really calls its own card's command, and nothing else", async () => {
  // The strongest form of the rule-4 check: press each control and read what
  // went over the bridge. A control that changed a setting any other way -
  // a write to a store, an endpoint, a third command - shows up here.
  const stub = fakeDom({ stored: null });
  const calls = [];
  globalThis.__TAURI__ = {
    core: {
      invoke: async (command, args) => {
        calls.push([command, args]);
        // The PC's own answers, shaped as the real commands send them.
        if (command === "get_second_card") {
          return { chat_card: { cards: [], chosen: "", where: { words: "On this PC." } } };
        }
        if (command === "supervisor_status") {
          return { supervise: false, configured: false, owned: false, backend: { program: "", args: [] } };
        }
        if (command === "get_api_settings") return { base: "", bindAddress: "", hasToken: true };
        if (command === "get_voice_status") {
          return { gate: { settings: { memory: "memory_on_screen" }, training: {} } };
        }
        return {};
      },
    },
  };
  let unload = () => {};
  try {
    unload = await loadModule(stub);
    // What the card read on the way in: exactly the four existing reads.
    const reads = calls.map((c) => c[0]).sort();
    assert.deepEqual(reads,
      ["get_api_settings", "get_second_card", "get_voice_status", "supervisor_status"],
      `the card read ${reads.join(", ")}`);

    // 1. Pinning a card. `paintChatCard` builds a radio per card, and this
    //    stub's backend reports none, so the "leave it to Ollama" one is the
    //    only control - which is itself the rollback path.
    const chat = stub.els.get("fr-rows").querySelector("#fr-chat");
    const chatRadio = chat.querySelector("input");
    assert.ok(chatRadio, "the chat row drew no control at all");
    calls.length = 0;
    chatRadio.checked = true;
    for (const fn of chatRadio.listeners.change) await fn();
    assert.deepEqual(calls.filter((c) => c[0] === "set_chat_card"),
      [["set_chat_card", { action: "leave" }]],
      "the chat row does not go through set_chat_card");

    // 2. Supervision, carrying the stored program through untouched.
    const supervise = stub.els.get("fr-rows").querySelector("#fr-supervise");
    const sw = supervise.querySelector("input");
    calls.length = 0;
    sw.checked = true;
    for (const fn of sw.listeners.change) await fn();
    const set = calls.find((c) => c[0] === "set_supervision");
    assert.ok(set, "the start-Jarvis switch does not go through set_supervision");
    assert.equal(set[1].supervise, true);
    assert.equal(set[1].backend.program, "", "the stored program was not carried through");

    // 3. The phone address.
    const phone = stub.els.get("fr-rows").querySelector("#fr-phone");
    const box = phone.querySelectorAll("input")[0];
    assert.ok(box, "the phone row drew no address box");
    box.value = "100.64.0.7";
    const save = phone.querySelectorAll("button");
    assert.ok(save.length >= 2, "the phone row has no Save/off pair");
    calls.length = 0;
    for (const fn of save[0].listeners.click) await fn();
    const api = calls.find((c) => c[0] === "set_api_settings");
    assert.ok(api, "the phone row does not go through set_api_settings");
    assert.equal(api[1].bindAddress, "100.64.0.7");
    assert.equal(api[1].token, null, "the card wrote a token - it must never touch one");
    assert.equal("base" in api[1], true, "the phone row stopped sending the fields set_api_settings needs");

    // 4. Read aloud, the one that raises a card, through the voice command.
    const aloud = stub.els.get("fr-rows").querySelector("#fr-read-aloud");
    const toggle = aloud.querySelector("input");
    calls.length = 0;
    toggle.checked = true;
    for (const fn of toggle.listeners.change) await fn();
    assert.deepEqual(calls.filter((c) => c[0] === "set_voice_setting"),
      [["set_voice_setting", { setting: "memory", value: "memory_aloud" }]],
      "read aloud does not go through set_voice_setting with the memory setting");
  } finally {
    unload();
    delete globalThis.__TAURI__;
  }
});

await check("a card waiting is said to be waiting, never as done", async () => {
  // Turning read aloud ON is the looser choice: `voice_training.rs` sends it
  // to the backend, the backend raises the card, and the status the card
  // reads back carries `pending`. The page must say so. A page that showed
  // "Read aloud" here would be telling the owner a change happened that has
  // not been approved - rule 4's whole point.
  const stub = fakeDom({ stored: null });
  globalThis.__TAURI__ = {
    core: {
      invoke: async (command) => {
        if (command === "get_voice_status") {
          // The shape the PC really sends while the card is waiting: the
          // setting already reads as the loose one, and the card is pending.
          return {
            gate: {
              settings: { memory: "memory_aloud" },
              training: { pending: true, kind: "setting", setting: { name: "memory", value: "memory_aloud" } },
            },
          };
        }
        if (command === "set_voice_setting") return {};
        if (command === "get_second_card") return { chat_card: { cards: [], chosen: "", where: { words: "" } } };
        if (command === "supervisor_status") return { supervise: false, backend: {} };
        if (command === "get_api_settings") return { bindAddress: "" };
        return {};
      },
    },
  };
  let unload = () => {};
  try {
    unload = await loadModule(stub);
    const aloud = stub.els.get("fr-rows").querySelector("#fr-read-aloud");
    const toggle = aloud.querySelector("input");
    toggle.checked = true;
    for (const fn of toggle.listeners.change) await fn();
    const words = aloud.querySelector(".status").textContent;
    assert.match(words, /Waiting for your approval/,
      "a card that is waiting is not said to be waiting");
    assert.match(words, /[Nn]othing changes until you approve it/,
      "the card does not say that nothing changes until it is approved");
  } finally {
    unload();
    delete globalThis.__TAURI__;
  }
});

await check("a held change says why, and the switch goes back", async () => {
  // The other answer `voice_training.rs` gives a loosening move: the link is
  // stale, so the move is held (HELD_STALE) and refused. That must not look
  // like a success either.
  const stub = fakeDom({ stored: null });
  globalThis.__TAURI__ = {
    core: {
      invoke: async (command) => {
        if (command === "get_voice_status") {
          return { gate: { settings: { memory: "memory_on_screen" }, training: {} } };
        }
        if (command === "set_voice_setting") {
          throw new Error("Held - the link to Jarvis is stale, so nothing that loosens a setting can change until it reconnects.");
        }
        if (command === "get_second_card") return { chat_card: { cards: [], chosen: "", where: { words: "" } } };
        if (command === "supervisor_status") return { supervise: false, backend: {} };
        if (command === "get_api_settings") return { bindAddress: "" };
        return {};
      },
    },
  };
  let unload = () => {};
  try {
    unload = await loadModule(stub);
    const aloud = stub.els.get("fr-rows").querySelector("#fr-read-aloud");
    const toggle = aloud.querySelector("input");
    toggle.checked = true;
    for (const fn of toggle.listeners.change) await fn();
    assert.match(aloud.querySelector(".status").textContent, /stale/,
      "a held change does not say why it was held");
    assert.equal(toggle.checked, false, "the switch stayed on after a refusal");
  } finally {
    unload();
    delete globalThis.__TAURI__;
  }
});

await check("nowhere in the module is a setting written by hand", () => {
  // The whole point: the page gathers existing settings and calls the existing
  // path. Nothing here may reach for a settings file, a store or an endpoint.
  const code = JS.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/\/\/[^\n]*/g, " ");
  for (const forbidden of ["/api/", "fetch(", "settings.toml", "store", "writeFile", "save_settings"]) {
    assert.ok(!code.includes(forbidden), `first-run-settings.js reaches for ${forbidden}`);
  }
});

await check("the words a beginner reads are plain", () => {
  // The card's own visible sentences, with the code stripped out.
  const visible = [
    ...HTML.slice(card.at, card.at + card.all.length).matchAll(/>([^<>{}]{40,})</g),
  ].map((m) => m[1]).join(" ");
  for (const jargon of ["Tauri", "IPC", "invoke", "JSON", "ACL", "endpoint", "localStorage"]) {
    assert.ok(!new RegExp(`\\b${jargon}\\b`).test(visible),
      `the card says "${jargon}" to a beginner`);
  }
  // And the honest note the owner asked for is really there: a bigger model
  // keeps more conversation.
  assert.match(card.all + JS, /more conversation/i,
    "the card never says a bigger model keeps more conversation");
});

await check("in a plain browser the card claims no connection", async () => {
  // jarvis-link.js's own state starts as its untouched default, which reads
  // as "Linked". A preview that printed that would be claiming a connection
  // that does not exist - the same class of claim the offline-models design
  // bans in the Brain.
  const stub = fakeDom({ stored: null });
  let unload = () => {};
  try {
    unload = await loadModule(stub);
    const state = stub.els.get("fr-state").textContent;
    assert.ok(!/Linked/i.test(state), `the card says "${state}" with no app behind it`);
  } finally {
    unload();
  }
});

await check("the model row says where the model is chosen, and does not pretend", () => {
  // The brief: "which model Jarvis uses". There is no model setting on the
  // desktop - the model list lives in the Brain (brain.js's Model view,
  // `brain_model`). The card must say that rather than grow a second picker,
  // and must never tell the owner the model is chosen in Settings.
  const code = JS.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/\/\/[^\n]*/g, " ");
  assert.match(code, /chosen in the Brain window/,
    "the model row does not say where the model is really chosen");
  assert.match(code, /no model list on this page/,
    "the model row does not say plainly why there is no model list here");
  // ...and the one model-shaped setting Settings does have is offered.
  assert.match(code, /get_second_card/, "the card no longer reads which card runs chat");
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("\nthe Set up Jarvis card gathers the first-run settings, and every one keeps its card.");
