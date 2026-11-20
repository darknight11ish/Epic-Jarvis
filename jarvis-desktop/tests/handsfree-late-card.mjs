/**
 * Hands-free mode - a card answered after the Rust call gave up (2026-11-19
 * state-drift).
 *
 *   node tests/handsfree-late-card.mjs
 *
 * WHY THIS EXISTS. DESKTOP-STATE-DRIFT.md section 3.2 (MISMATCH-WIDGET): this
 * is the peer of the owner's measured Wi-Fi row. Turning the mode ON raises ONE
 * approval card that can wait 15 minutes (`jarvis_gate.py` APPROVAL_TIMEOUT =
 * 900 s), while the Rust command waits only 20 s (`handsfree.rs`
 * WRITE_TIMEOUT). When a person takes longer than that, the call fails - and
 * the page used to paint the bridge's "restart Ollama" sentence and leave the
 * tick exactly where the last read put it, with no re-read when the card was
 * finally approved. The PC ended up ON while the page said OFF.
 *
 * This drives the REAL src/handsfree-settings.js over a hand-made DOM, a fake
 * bridge and the real jarvis-link module (no browser, no Playwright):
 *
 *   1. the PC says OFF -> the box is unticked;
 *   2. the owner turns it ON and the call times out while the card waits -> the
 *      box is drawn UNCONFIRMED (indeterminate, never a state) and the line
 *      says the approval is still waiting - NOT the "restart Ollama" sentence;
 *   3. the card is then answered and the PC answers ON -> the row repaints by
 *      itself (approval queue) and the tick is a real ON, not the old value.
 *
 * Run by CI's frontend shards (`tests/*.mjs`); needs no browser.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

const MODULE = new URL("../src/handsfree-settings.js", import.meta.url).href;
const LINK = new URL("../src/jarvis-link.js", import.meta.url).href;

const settle = async () => {
  for (let i = 0; i < 8; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
};

const IDS = [
  "handsfree", "hf-state", "hf-body", "hf-enabled", "hf-enabled-label",
  "hf-enabled-detail", "hf-enabled-status", "hf-status", "hf-window", "hf-phone",
];

function makeNode(id) {
  const node = {
    id, checked: false, indeterminate: false, disabled: false, hidden: false,
    textContent: "", dataset: {}, listeners: {},
    addEventListener(kind, fn) { (this.listeners[kind] ||= []).push(fn); },
    fire(kind) { for (const fn of this.listeners[kind] || []) fn(); },
  };
  return node;
}

const nodes = new Map(IDS.map((id) => [id, makeNode(id)]));
const handlers = {};
const pc = { on: false, failing: true };
const previous = { document: globalThis.document, tauri: globalThis.__TAURI__ };

globalThis.document = {
  readyState: "complete",
  hidden: false,
  getElementById: (id) => nodes.get(id) || null,
  addEventListener() {},
  body: null,
  createElement: () => makeNode("x"),
};
globalThis.__TAURI__ = {
  core: {
    invoke: async (command) => {
      if (command === "get_handsfree") {
        return {
          available: true,
          enabled: pc.on,
          window_sec: 60,
          label: "Hands-free mode",
          detail: "the PC's own detail",
          heading: "Hands-free mode",
        };
      }
      if (command === "set_handsfree") {
        if (pc.failing) {
          // The bridge's own sentence when the 20 s call gives up while the
          // card's 15-minute gate is still open (plain_errors.rs).
          throw new Error(
            "Jarvis took too long to answer. Try again in a moment. " +
              "If it keeps happening, restart Ollama on the PC.",
          );
        }
        return { enabled: Boolean(true), changed: true, message: "Hands-free mode is on." };
      }
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

async function loadRow() {
  nodes.set("hf-enabled", makeNode("hf-enabled"));
  for (const id of IDS) {
    if (id !== "hf-enabled") nodes.set(id, makeNode(id));
  }
  const module = await import(`${MODULE}?case=${Math.random()}`);
  await settle();
  return {
    module,
    box: nodes.get("hf-enabled"),
    line: nodes.get("hf-enabled-status"),
  };
}

/** The owner flipping the switch: the browser toggles the box, then fires. */
function clickOn(row) {
  row.box.checked = true;
  row.box.fire("change");
}

test.after(() => {
  globalThis.document = previous.document;
  globalThis.__TAURI__ = previous.tauri;
});

test("the PC says OFF: the box is unticked", async () => {
  pc.on = false;
  pc.failing = true;
  const row = await loadRow();
  assert.equal(row.box.checked, false, "the PC said hands-free is off and the box was ticked");
});

test("a card still waiting after the 20 s call is WAITING and unconfirmed - never 'restart Ollama'", async () => {
  pc.on = false;
  pc.failing = true;
  const row = await loadRow();
  clickOn(row);
  await settle();
  assert.equal(row.box.indeterminate, true,
    "a card still waiting was drawn as a definite state");
  assert.match(row.line.textContent, /Waiting for your approval/,
    `the waiting card was drawn as: "${row.line.textContent}"`);
  assert.doesNotMatch(row.line.textContent, /restart Ollama/i,
    "the bridge's unrelated' restart Ollama' sentence was put on a card that is simply waiting");
});

test("when the card is answered the row repaints by itself - the PC's ON reaches the box", async () => {
  pc.on = false;
  pc.failing = true;
  const row = await loadRow();
  clickOn(row);
  await settle();
  assert.equal(row.box.indeterminate, true);

  // The person answers the card: the PC is really on now, and the approval
  // queue changes. The old row had no path from here at all.
  pc.on = true;
  for (const fn of handlers["approvals-changed"] || []) {
    fn({ payload: { count: 1, items: [] } });
  }
  await settle();
  assert.equal(row.box.checked, true,
    "the PC turned hands-free ON and the box still said off (the row is cached)");
  assert.equal(row.box.indeterminate, false,
    "the waiting marker stayed after the PC answered");
  assert.match(row.line.textContent, /Hands-free mode is on/,
    `the answered card was drawn as: "${row.line.textContent}"`);
});
