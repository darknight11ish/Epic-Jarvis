/**
 * Settings -> "Limits and frequency" (2026-10-08).
 *
 * One card, two Rust commands (src-tauri/src/limits.rs), Settings only:
 *  - get_limits:  GET  /api/limits          - the limits and their words, read
 *    from the owner's own settings file by the PC.
 *  - set_limit:   POST /api/limits/settings - ONE limit, one value.
 *
 * The page decides nothing. It sends a key and a value; the BACKEND compares
 * it with the number already in force, and a change that lets Jarvis do more is
 * a loosening it puts to the owner on an approval card before writing anything.
 * WHICH DIRECTION THAT IS, IS THE ROW'S OWN (corrected 2026-10-09): on most rows
 * a bigger number is the loosening, and on the voice check's bar a SMALLER one
 * is, so the line above the rows may not tell the owner that turning a number
 * down always applies at once - that was false for the row right under it. The
 * row's own `note`, written by the PC, says which way that row goes. The
 * sentence under the list is always the PC's own - `said` when it worked, its
 * refusal in the owner's words when it did not - never one made up here, which
 * is why nothing is drawn as changed until the PC answers.
 *
 * @module limits-settings
 */

import { onQueue } from "./jarvis-link.js";
import { normaliseLimits, stepped, valueFor, rowWords, problemWords } from "./limits.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

const el = {
  section: $("limits"),
  state: $("limits-state"),
  body: $("limits-body"),
  rows: $("limits-rows"),
  note: $("limits-note"),
};

function node(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

function button(label, description, enabled, onClick) {
  const b = node("button", "btn small", label);
  b.type = "button";
  b.disabled = !enabled;
  b.setAttribute("aria-label", description);
  if (enabled) b.addEventListener("click", onClick);
  return b;
}

async function send(limit, value) {
  el.note.textContent = "Saving…";
  let said;
  try {
    const out = await TAURI.core.invoke("set_limit", { key: limit.key, value: valueFor(limit, value) });
    said = String((out && out.said) || "Done.");
  } catch (error) {
    said = problemWords(error);
  }
  // The PC's own sentence stays on the page: the re-read below repaints the
  // card, and painting must not wipe the answer the owner just got. A stale
  // sentence is worse than none, so the next load that is NOT keeping an
  // answer puts the card's standing line back.
  el.note.textContent = said;
  await load({ keep: true });
}

function paint(reading, keep) {
  if (!el.section) return;
  if (!reading.available) {
    el.state.textContent = reading.why;
    el.body.hidden = true;
    return;
  }
  el.state.textContent = reading.rows.length ? "" : "There is nothing on this PC to change yet.";
  el.body.hidden = false;
  if (!keep) {
    // THE ONE LINE ABOVE THE ROWS may promise nothing about direction. It used
    // to read "Turning a number down changes at once. Turning one up asks you
    // first, on this PC." - and on the voice check's bar the loosening IS the
    // way down, so the line contradicted the row right under it. Which way asks
    // is the ROW's to say (`loosenUp` for up, the note for down); the list says
    // only what holds for all of them.
    el.note.textContent = reading.rows.length
      ? "Some of these take effect at once. Others ask you first, on this PC - the line under "
        + "each one says which."
      : "";
  }
  el.rows.replaceChildren(...reading.rows.map((limit) => {
    const li = node("li", "sc-gpu");
    li.dataset.limit = limit.key;
    li.dataset.kind = limit.kind;
    if (limit.pcOnly) li.dataset.role = "second";
    li.append(node("span", "sc-gpu-name", `${limit.title} - ${rowWords(limit)}`));
    if (limit.note) li.append(node("span", "sc-gpu-role", limit.note));

    const controls = node("span", "sc-gpu-controls");
    if (limit.kind === "bool") {
      controls.append(button(limit.value ? "Turn off" : "Turn on",
                             `${limit.title}: turn it ${limit.value ? "off" : "on"}`,
                             true, () => send(limit, !limit.value)));
    } else if (limit.choices.length) {
      for (const choice of [...limit.choices].sort((a, b) => a - b)) {
        const chosen = choice === limit.value;
        const label = `${choice}${limit.unit ? " " + limit.unit : ""}`;
        const b = button(label, `${limit.title}: ${label}`, !chosen, () => send(limit, choice));
        if (chosen) {
          b.disabled = true;
          b.dataset.state = "on";
        }
        controls.append(b);
      }
    } else {
      const down = stepped(limit, -1);
      const up = stepped(limit, 1);
      controls.append(button("−", `${limit.title}: less`, down !== null, () => send(limit, down)));
      controls.append(node("span", "sc-gpu-role", rowWords(limit)));
      controls.append(button("+", `${limit.title}: more`, up !== null, () => send(limit, up)));
    }
    li.append(controls);
    return li;
  }));
}

let loading = false;

async function load(opts) {
  if (!el.section || loading) return;
  if (!IS_TAURI) {
    el.state.textContent = "Open this in Jarvis Desktop to change these.";
    return;
  }
  loading = true;
  try {
    paint(normaliseLimits(await TAURI.core.invoke("get_limits")), Boolean(opts && opts.keep));
  } catch (error) {
    el.state.textContent = problemWords(error);
  } finally {
    loading = false;
  }
}

// A card answered, or another window changed something. onQueue also delivers
// the current queue at once, which is the first read.
onQueue(() => load());
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) load();
});
