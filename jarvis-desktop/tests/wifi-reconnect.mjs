/**
 * The Wi-Fi reconnect switch in Settings: the tick and the sentence are the
 * SAME state (2026-11-18.
 *
 *   node tests/wifi-reconnect.mjs
 *
 * WHY THIS EXISTS. The owner reported the row saying it was ON - the line under
 * it read "The auto Wi-Fi reconnect is already on. Nothing was changed." after
 * he clicked it - over a checkbox that was UNTICKED. The state was on (the
 * shipped default), the answer was right, and the widget was wrong: it ticked
 * the box from a field called `on` that no PC answer carries, while it worded the
 * line from the PC's `words` field. Two readers of one answer, and they could
 * name different states. This file drives the REAL
 * `src/wifi-reconnect-settings.js` against a hand-made DOM and a fake PC - no
 * browser, no Playwright - and holds it to:
 *
 *   1. the PC says ON  -> the box is ticked AND the line says "On ...";
 *   2. the PC says OFF -> the box is unticked AND the line says "Off ...";
 *   3. after a change the PC reports as "already on" / "on now", the box is
 *      ticked and the line names the same state - the owner's exact report;
 *   4. the PC's `words` can never outvote its `enabled`: if the two disagree,
 *      the tick and the sentence follow `enabled`, together;
 *   5. an answer with no yes-or-no is UNKNOWN - never ticked, never clickable,
 *      never read as "off"; and a PC whose saved setting file is damaged says
 *      so rather than claiming a state;
 *   6. a waiting approval card leaves the box OFF and says a card is waiting;
 *   7. a refused change reads the real state back, shows the PC's refusal, and
 *      never leaves the box claiming the click happened;
 *   8. the page reads before it writes and never uses a second store.
 *
 * Run by CI's frontend shards (`jarvis-desktop/tests/*.mjs`); needs no browser.
 */
import assert from "node:assert/strict";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const MODULE = new URL("../src/wifi-reconnect-settings.js", import.meta.url).href;

/* ── The PC's real answers (`jarvis_wifi.state()` / `request_enabled()`) ─── */

const PC_ON = {
  ok: true, enabled: true, default: true, known: true, dry_run: false,
  words: "On. Every 2 hours while this PC has no internet, Jarvis tries the saved " +
    "password-protected Wi-Fi networks it already knows - the ones Windows has " +
    "connected to before - and tells you what happened.",
  last_words: "", last_at: null, last_class: "", last_check_at: null,
  next_check_at: null, attempts: 0,
};

const PC_OFF = {
  ok: true, enabled: false, default: true, known: true, dry_run: false,
  words: "Off. Jarvis never touches this PC's Wi-Fi choice. Turn it back on in " +
    "Settings or by saying \"turn on the auto Wi-Fi reconnect\".",
  last_words: "", last_at: null, last_class: "", last_check_at: null,
  next_check_at: null, attempts: 0,
};

/** The POST answer when the PC was already on: the owner's own sentence. */
const ALREADY_ON = {
  ok: true, enabled: true, changed: false,
  words: "The auto Wi-Fi reconnect is already on. Nothing was changed.",
  message: "The auto Wi-Fi reconnect is already on. Nothing was changed.",
};

/** The POST answer when turning it on raised its ONE approval card. */
const WAITING_CARD = {
  ok: false, enabled: false, changed: false, waiting: true,
  words: "A card is waiting in the Jarvis bar. The auto Wi-Fi reconnect stays " +
    "off until you approve it.",
};

/* ── A DOM just big enough, and a PC the page can talk to ────────────────── */

function makeNode(id) {
  return {
    id, checked: false, disabled: false, textContent: "", listeners: {},
    addEventListener(kind, fn) { (this.listeners[kind] ||= []).push(fn); },
    fire(kind) { for (const fn of this.listeners[kind] || []) fn(); },
  };
}

function fakeDom() {
  const ids = ["wifi-reconnect-switch", "wifi-reconnect-status"];
  const byId = new Map(ids.map((id) => [id, makeNode(id)]));
  return {
    byId,
    document: {
      readyState: "complete",
      getElementById: (id) => byId.get(id) || null,
      addEventListener() {},
    },
  };
}

const settle = async () => {
  // The page starts its read without blocking; a few macrotasks let the fake
  // bridge's promises and the page's own awaits finish.
  for (let i = 0; i < 4; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
};

/**
 * Load a fresh copy of the real module over a fake DOM and a fake bridge.
 * `get`/`set` are the PC's answers, or functions returning them (an Error in
 * place of an answer is a thrown bridge failure). The stub stays installed while
 * the page is driven, so the caller must `unload()`.
 */
async function loadWifi({ get, set }) {
  const dom = fakeDom();
  const calls = [];
  const previous = { document: globalThis.document, tauri: globalThis.__TAURI__ };

  const answer = (producer) => {
    const value = typeof producer === "function" ? producer() : producer;
    if (value instanceof Error) throw value;
    return structuredClone(value);
  };

  globalThis.document = dom.document;
  globalThis.__TAURI__ = {
    core: {
      invoke: async (command, args) => {
        calls.push([command, args]);
        if (command === "get_wifi_reconnect") return answer(get);
        if (command === "set_wifi_reconnect") return answer(set);
        throw new Error(`the page called an unexpected command: ${command}`);
      },
    },
  };

  try {
    // A query string so node imports a fresh copy each time: the page's module
    // state (the last answer, the busy latch) must not leak between checks.
    const module = await import(`${MODULE}?case=${Math.random()}`);
    await settle();
    const page = {
      module,
      calls,
      box: dom.byId.get("wifi-reconnect-switch"),
      line: dom.byId.get("wifi-reconnect-status"),
      /** The owner clicking the box: the browser toggles it, then fires. */
      async click() {
        this.box.checked = !this.box.checked;
        this.box.fire("change");
        await settle();
      },
      unload() {
        globalThis.document = previous.document;
        globalThis.__TAURI__ = previous.tauri;
      },
    };
    return page;
  } catch (error) {
    globalThis.document = previous.document;
    globalThis.__TAURI__ = previous.tauri;
    throw error;
  }
}

/* ── The checks ─────────────────────────────────────────────────────────── */

let passed = 0;
const fails = [];
async function check(name, fn) {
  try {
    await fn();
    passed += 1;
    console.log(`ok   ${name}`);
  } catch (error) {
    fails.push(name);
    console.log(`FAIL ${name}\n     ${error.message}`);
  }
}

await check("the state says ON: the box is ticked and the line says On", async () => {
  const page = await loadWifi({ get: PC_ON, set: PC_ON });
  try {
    assert.equal(page.box.checked, true,
      `the PC said enabled:true and the box was ${page.box.checked ? "ticked" : "unticked"}`);
    assert.equal(page.box.disabled, false, "a switch whose state was read is not clickable");
    assert.match(page.line.textContent, /^On\./,
      `the PC said ON and the line said "${page.line.textContent}"`);
    assert.deepEqual(page.calls.map((call) => call[0]), ["get_wifi_reconnect"],
      `the page wrote before the owner touched it: ${JSON.stringify(page.calls)}`);
  } finally {
    page.unload();
  }
});

await check("the state says OFF: the box is unticked and the line says Off", async () => {
  const page = await loadWifi({ get: PC_OFF, set: PC_OFF });
  try {
    assert.equal(page.box.checked, false,
      "the PC said enabled:false and the box was ticked");
    assert.equal(page.box.disabled, false, "a readable switch was not clickable");
    assert.match(page.line.textContent, /^Off\./,
      `the PC said OFF and the line said "${page.line.textContent}"`);
  } finally {
    page.unload();
  }
});

await check("a PC that answers 'already on' leaves the box ticked and the line naming ON", async () => {
  // The owner's exact report: he ticked an unticked box and the answer said
  // "The auto Wi-Fi reconnect is already on. Nothing was changed." over a tick
  // that never came. The POST answer says enabled:true, so that is the state.
  const page = await loadWifi({ get: PC_OFF, set: ALREADY_ON });
  try {
    assert.equal(page.box.checked, false, "the initial OFF read was not drawn off");
    await page.click();                                   // the owner ticks it
    assert.deepEqual(page.calls.at(-1), ["set_wifi_reconnect", { enabled: true }]);
    assert.equal(page.box.checked, true,
      "the PC answered enabled:true ('already on') and the box stayed unticked");
    assert.match(page.line.textContent, /^On\./,
      `the answer said already on and the line said "${page.line.textContent}"`);
  } finally {
    page.unload();
  }
});

await check("a change the PC reports as 'on now' is drawn on", async () => {
  const setReply = {
    ok: true, enabled: true, changed: true,
    words: "The auto Wi-Fi reconnect is on now - every 2 hours while this PC has " +
      "no internet, Jarvis will try the saved password-protected networks it " +
      "already knows.",
  };
  const page = await loadWifi({ get: PC_OFF, set: setReply });
  try {
    await page.click();
    assert.deepEqual(page.calls.at(-1), ["set_wifi_reconnect", { enabled: true }]);
    assert.equal(page.box.checked, true, "the PC said it was on now and the box stayed off");
    assert.match(page.line.textContent, /^On\./);
  } finally {
    page.unload();
  }
});

await check("a change the PC reports as 'off now' is drawn off", async () => {
  const setReply = {
    ok: true, enabled: false, changed: true,
    words: "The auto Wi-Fi reconnect is off now - I will not touch this PC's Wi-Fi choice.",
  };
  const page = await loadWifi({ get: PC_ON, set: setReply });
  try {
    assert.equal(page.box.checked, true, "the initial ON read was not drawn on");
    await page.click();                                   // the owner unticks it
    assert.deepEqual(page.calls.at(-1), ["set_wifi_reconnect", { enabled: false }]);
    assert.equal(page.box.checked, false, "the PC said it was off now and the box stayed ticked");
    assert.match(page.line.textContent, /^Off\./);
  } finally {
    page.unload();
  }
});

await check("one reader: the PC's own words cannot outvote its yes-or-no", async () => {
  // If a PC answer ever contradicted itself, the tick and the sentence must
  // still agree with each other AND with `enabled` - the field the answer lane
  // reads too. Two readers of one answer is the defect this file exists for.
  const saysOnInWords = { ...PC_ON, enabled: true, words: PC_OFF.words };
  let page = await loadWifi({ get: saysOnInWords, set: saysOnInWords });
  try {
    assert.equal(page.box.checked, true, "enabled:true was not drawn on");
    assert.match(page.line.textContent, /^On\./,
      `enabled:true and the words said OFF, so the line said "${page.line.textContent}"`);
  } finally {
    page.unload();
  }

  const saysOffInWords = { ...PC_OFF, enabled: false, words: PC_ON.words };
  page = await loadWifi({ get: saysOffInWords, set: saysOffInWords });
  try {
    assert.equal(page.box.checked, false, "enabled:false was drawn on");
    assert.match(page.line.textContent, /^Off\./,
      `enabled:false and the words said ON, so the line said "${page.line.textContent}"`);
  } finally {
    page.unload();
  }
});

await check("an answer with no yes-or-no is UNKNOWN: no tick, no click, never Off", async () => {
  const page = await loadWifi({ get: { ok: true, words: "maybe" }, set: { ok: true } });
  try {
    assert.equal(page.box.checked, false, "an unreadable answer ticked the box");
    assert.equal(page.box.disabled, true,
      "a state this app could not read left the box clickable");
    assert.match(page.line.textContent, /not in a way this app can read/,
      `the line claimed a state it did not have: "${page.line.textContent}"`);
    assert.ok(!/^Off\./.test(page.line.textContent), "an unreadable answer was read as off");
  } finally {
    page.unload();
  }
});

await check("a PC whose saved setting is damaged says so, not Off", async () => {
  const damaged = { ...PC_OFF, known: false };
  const page = await loadWifi({ get: damaged, set: damaged });
  try {
    assert.equal(page.box.checked, false);
    assert.equal(page.box.disabled, true, "a damaged setting left the box clickable");
    assert.match(page.line.textContent, /could not read its saved Wi-Fi reconnect setting/,
      `the line put words in the PC's mouth: "${page.line.textContent}"`);
  } finally {
    page.unload();
  }
});

await check("turning it on waits for its ONE card: the box stays off and says a card is waiting", async () => {
  const page = await loadWifi({ get: PC_OFF, set: WAITING_CARD });
  try {
    await page.click();
    assert.deepEqual(page.calls.at(-1), ["set_wifi_reconnect", { enabled: true }]);
    assert.equal(page.box.checked, false,
      "the box showed ON before the approval card was answered");
    assert.match(page.line.textContent, /card is waiting/,
      `the line did not say a card was waiting: "${page.line.textContent}"`);
  } finally {
    page.unload();
  }
});

await check("a refused change shows the PC's own refusal and reads the real state back", async () => {
  const refusal = new Error("The approval card was not approved, so the auto Wi-Fi " +
    "reconnect stayed off. Nothing was changed.");
  const page = await loadWifi({ get: PC_OFF, set: () => { throw refusal; } });
  try {
    await page.click();
    assert.equal(page.box.checked, false,
      "a refused change left the box claiming the click happened");
    assert.match(page.line.textContent, /not approved/,
      `the PC's refusal was lost: "${page.line.textContent}"`);
  } finally {
    page.unload();
  }
});

await check("a PC without the route is said in its own words, never as Off", async () => {
  const page = await loadWifi({
    get: { available: false,
      why: "Your PC's Jarvis has no Wi-Fi reconnect switch yet - run apply-patches.ps1 on the PC." },
    set: { available: false, why: "unsupported" },
  });
  try {
    assert.equal(page.box.checked, false);
    assert.equal(page.box.disabled, true, "a switch that does not exist was clickable");
    assert.match(page.line.textContent, /no Wi-Fi reconnect switch yet/,
      `the line said "${page.line.textContent}"`);
    assert.ok(!/^Off\./.test(page.line.textContent), "a missing switch was read as off");
  } finally {
    page.unload();
  }
});

await check("the resolver is the one reader: `enabled` decides, a stale `on` cannot", async () => {
  const page = await loadWifi({ get: PC_ON, set: PC_ON });
  try {
    const { readWifi, describe } = page.module;
    assert.equal(typeof readWifi, "function", "the page has no single reader");
    assert.equal(typeof describe, "function", "the page has no single sentence writer");
    const off = readWifi({ enabled: false, on: true, known: true, words: PC_ON.words });
    assert.equal(off.on, false, "a stale `on` field outvoted `enabled`");
    assert.match(describe(off), /^Off\./);
    const on = readWifi({ enabled: true, on: false, known: true, words: PC_OFF.words });
    assert.equal(on.on, true, "`enabled:true` was not read as on");
    assert.match(describe(on), /^On\./);
  } finally {
    page.unload();
  }
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join("; ")}`);
  process.exit(1);
}
console.log(`\nall ${passed} checks passed`);
