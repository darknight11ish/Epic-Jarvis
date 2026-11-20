/**
 * "Read replies out loud" - the row keeps asking (2026-11-19 state-drift.
 *
 *   node tests/read-aloud-settings.mjs
 *
 * WHY THIS EXISTS. DESKTOP-STATE-DRIFT.md section 3.3 (MISMATCH-WIDGET): the
 * PC holds this value (`GET/POST /api/read-aloud`; a chat or Live sentence
 * changes the SAME value), and the Settings row used to read it ONCE at module
 * load and never again. So the owner could say "stop reading your replies out
 * loud" while Settings was open, the quickbar obeyed at once - and the tick and
 * the sentence beside it still said On.
 *
 * This drives the REAL src/read-aloud-settings.js against a hand-made DOM, a
 * fake bridge and the real jarvis-link module (no browser, no Playwright):
 *
 *   1. the PC says OFF -> the box is unticked and the line says Off;
 *   2. a chat change arrives on the approval queue -> the row repaints from the
 *      NEW read (the old code had no path from here at all);
 *   3. the same change arrives as the PC's own `read_aloud` event - the exact
 *      path `jarvis_read_aloud._publish` uses for a chat/Live sentence - and
 *      the row repaints too;
 *   4. an unreadable PC answer is never drawn as Off.
 *
 * Run by CI's frontend shards (`tests/*.mjs`); needs no browser.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

const MODULE = new URL("../src/read-aloud-settings.js", import.meta.url).href;
const LINK = new URL("../src/jarvis-link.js", import.meta.url).href;

const settle = async () => {
  for (let i = 0; i < 6; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
};

function makeNode(id) {
  return {
    id, checked: false, disabled: false, textContent: "", listeners: {},
    addEventListener(kind, fn) { (this.listeners[kind] ||= []).push(fn); },
    fire(kind) { for (const fn of this.listeners[kind] || []) fn(); },
  };
}

/* ── One bridge for the whole file ────────────────────────────────────────
 *
 * jarvis-link reads `__TAURI__` at import time and registers its listeners in
 * `start()` ONCE, so the bridge has to be installed before the first import and
 * kept for the file's lifetime - exactly like the one Settings document the
 * real page has. Each check installs fresh row nodes and a fresh module copy,
 * and can change `pc` between reads: that is "the state changed while the page
 * was open". */

const nodes = new Map();
const handlers = {};
const calls = [];
const pc = { available: true, enabled: false, known: true, words: "" };
const previous = { document: globalThis.document, tauri: globalThis.__TAURI__ };

const byId = (id) => nodes.get(id) || null;

globalThis.document = {
  readyState: "complete",
  hidden: false,
  getElementById: byId,
  addEventListener() {},
  body: null,
  createElement: () => makeNode("x"),
};
globalThis.__TAURI__ = {
  core: {
    invoke: async (command) => {
      calls.push(command);
      if (command === "get_read_aloud") return { ...pc };
      if (command === "set_read_aloud") return { ...pc };
      if (command === "get_link_state") {
        return { connected: true, stale: false, base: "http://127.0.0.1:1", approvals: 0 };
      }
      if (command === "get_pending_approvals") return { count: 0, items: [] };
      throw new Error(`the page called an unexpected command: ${command}`);
    },
  },
  event: {
    listen: async (name, fn) => {
      (handlers[name] ||= []).push(fn);
      return () => {};
    },
  },
};

const link = await import(LINK);
link.start();

/** A fresh copy of the real row over the same bridge, with a fresh DOM. */
async function loadRow() {
  nodes.clear();
  for (const id of ["hud-read-replies", "hud-read-replies-status"]) nodes.set(id, makeNode(id));
  const module = await import(`${MODULE}?case=${Math.random()}`);
  await settle();
  return {
    module,
    box: byId("hud-read-replies"),
    line: byId("hud-read-replies-status"),
    setPc(next) { Object.assign(pc, next); },
    fire(name, payload) { for (const fn of handlers[name] || []) fn({ payload }); },
  };
}

/** Put the PC back to its initial shape at the start of every check. */
function resetPc() {
  pc.available = true;
  pc.enabled = false;
  pc.known = true;
  pc.words = "";
}

test("the PC says OFF: the box is unticked and the line says Off", async () => {
  resetPc();
  const row = await loadRow();
  assert.equal(row.box.checked, false, "the PC said off and the box was ticked");
  assert.match(row.line.textContent, /^Off[:.]/, `the line said "${row.line.textContent}"`);
});

test("a chat change reaches the row through the approval queue - not just at page load", async () => {
  resetPc();
  const row = await loadRow();
  assert.equal(row.box.checked, false);
  // The value moves: a chat sentence on the PC (or Jarvis Live).
  row.setPc({ enabled: true });
  row.fire("approvals-changed", { count: 1, items: [] });
  await settle();
  assert.equal(row.box.checked, true,
    "the PC is reading replies aloud now and the box still said off (the row is cached)");
  assert.match(row.line.textContent, /^On[:.]/, `the line said "${row.line.textContent}"`);
});

test("a chat/ Live sentence's own read_aloud event repaints the row too", async () => {
  resetPc();
  const row = await loadRow();
  assert.equal(row.box.checked, false);
  row.setPc({ enabled: true });
  // jarvis_read_aloud._publish sends exactly this frame after a chat change.
  row.fire("jarvis-event", { kind: "read_aloud", data: { enabled: true } });
  await settle();
  assert.equal(row.box.checked, true,
    "the PC's own read_aloud event did not move the box");
  // And back off again, through the same event.
  row.setPc({ enabled: false });
  row.fire("jarvis-event", { kind: "read_aloud", data: { enabled: false } });
  await settle();
  assert.equal(row.box.checked, false, "the PC's off event left the box ticked");
  assert.match(row.line.textContent, /^Off[:.]/);
});

test("a PC that cannot be read is never drawn as Off", async () => {
  resetPc();
  const row = await loadRow();
  row.setPc({ available: false, enabled: false, known: false, why: "the route is not there yet" });
  row.fire("approvals-changed", { count: 0, items: [] });
  await settle();
  assert.equal(row.box.checked, false);
  assert.match(row.line.textContent, /not there yet/,
    `an unreadable PC was drawn as a state: "${row.line.textContent}"`);
  assert.doesNotMatch(row.line.textContent, /^Off[:.]/);
});

test.after(() => {
  globalThis.document = previous.document;
  globalThis.__TAURI__ = previous.tauri;
});
