/**
 * Settings -> "What Jarvis can reach" (the Muse audit, 2026-09-25;
 * JARVIS-API.md section 24; backend jarvis_reach.py, reach.patch).
 *
 * One Rust command (src-tauri/src/reach.rs), Settings only:
 *  - get_reach: GET /api/reach - every way Jarvis can reach something
 *    outside itself, whether each is on, where it goes (a host only),
 *    whether it asks first, and the tools the AI model is offered. Written
 *    by the PC from its settings, never by the model.
 *
 * Read only: there is nothing to change here, so nothing is held on a stale
 * link. Each setting is changed where it lives (Web search, Second graphics
 * card, ...) or on the PC. The phone's Mind shows the same list
 * (ReachPlate.kt), in the same words (net/Reach.kt).
 *
 * @module reach-settings
 */

import { onQueue } from "./jarvis-link.js";
import { readReach, rowLines } from "./reach.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

const el = {
  section: $("reach"),
  state: $("reach-state"),
  body: $("reach-body"),
  rows: $("reach-rows"),
  toolsTitle: $("reach-tools-title"),
  tools: $("reach-tools"),
  toolsNone: $("reach-tools-none"),
  rest: $("reach-rest"),
  refresh: $("reach-refresh"),
};

function node(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

/** An error in words, never a bridge error or JSON. */
function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 400) {
    return "Could not ask Jarvis. Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

function paint(v) {
  if (!el.section) return;
  if (!v.available) {
    el.state.textContent = v.why;
    el.body.hidden = true;
    return;
  }
  el.state.textContent = "";
  el.body.hidden = false;
  el.rows.replaceChildren(...v.rows.map((r) => {
    const li = node("li", "sc-gpu");
    li.dataset.reach = r.id;
    li.dataset.state = r.state;
    if (r.on) li.dataset.role = "second";
    li.append(node("span", "sc-gpu-name", `${r.name} - ${r.stateWords}`));
    for (const line of rowLines(r, v)) li.append(node("span", "sc-gpu-role", line));
    return li;
  }));
  el.toolsTitle.textContent = v.toolsTitle;
  el.tools.replaceChildren(...v.tools.map((t) => node("li", "", t.name)));
  el.tools.hidden = v.tools.length === 0;
  el.toolsNone.textContent = v.toolsNone;
  el.toolsNone.hidden = v.tools.length !== 0;
  el.rest.textContent = v.everythingElse;
}

let loading = false;

async function load() {
  if (!el.section || loading) return;
  if (!IS_TAURI) {
    el.state.textContent = "Open this in Jarvis Desktop to see what Jarvis can reach.";
    return;
  }
  loading = true;
  try {
    paint(readReach(await TAURI.core.invoke("get_reach")));
  } catch (error) {
    el.state.textContent = problemWords(error);
  } finally {
    loading = false;
  }
}

if (el.section) {
  if (el.refresh) el.refresh.addEventListener("click", load);
}
// A card answered (a setting may have changed). onQueue also delivers the
// current queue at once - the first read.
onQueue(() => load());
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) load();
});
