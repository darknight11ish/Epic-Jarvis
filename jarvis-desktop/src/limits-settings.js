/**
 * Settings -> "Limits and frequency" (2026-10-08).
 *
 * One card, two Rust commands (src-tauri/src/limits.rs), Settings only:
 *  - get_limits:  GET  /api/limits          - the limits and their words, read
 *    from the owner's own settings file by the PC.
 *  - set_limit:   POST /api/limits/settings - ONE limit, one value.
 *
 * The page decides nothing. It sends a key and a value; the BACKEND compares
 * it with the number already in force, and turning one UP that lets Jarvis do
 * more is a loosening it puts to the owner on an approval card before writing
 * anything. The sentence under the list is always the PC's own - `said` when it
 * worked, its refusal in the owner's words when it did not - never one made up
 * here, which is why nothing is drawn as changed until the PC answers.
 *
 * @module limits-settings
 */

import { onQueue } from "./jarvis-link.js";
import { normaliseLimits, stepped, validTime, valueFor, rowWords, problemWords } from "./limits.js";

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
  const asked = reading.rows.some((r) => r.loosenUp);
  if (!keep) {
    el.note.textContent = asked
      ? "Turning a number down changes at once. Turning one up asks you first, on this PC."
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
    } else if (limit.kind === "time") {
      // A clock time is drawn as a clock - the same `<input type="time">` the
      // Notifications card has always used - not as "−/+" over a string that is
      // not a number. While the PC says quiet hours are off (`quiet_on`) the
      // hour decides nothing, so the control is disabled and says so rather
      // than being a clock that changes nothing.
      if (limit.quietOn) {
        const input = node("input", "sc-gpu-time");
        input.type = "time";
        input.value = validTime(limit.value) || "";
        input.setAttribute("aria-label", `${limit.title}: ${rowWords(limit)}`);
        input.addEventListener("change", () => {
          const t = validTime(input.value);
          // Only a real "HH:MM" is sent. An empty or half-typed box sends
          // nothing at all - it is never turned into a number of minutes.
          if (t) send(limit, t);
        });
        controls.append(input);
      } else {
        controls.append(node("span", "sc-gpu-role",
                             "Quiet hours are off, so this hour decides nothing."));
      }
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
