/**
 * Settings -> "How Jarvis talks" -> "Long answers" (2026-11-25;
 * jarvis_answer_style.py, GET/POST /api/answer-style).
 *
 * The owner's ask: "if atlas has a long response can it be put with bullet
 * points", and "make sure I can adjust it in the settings and adjust it
 * through chat if i want to". This is the Settings half - three choices, the
 * PC's own labels and reasons, cardless either way.
 *
 * TWO Rust commands (src-tauri/src/answer_style.rs), Settings window only:
 *  - get_answer_style: the three choices with the PC's own words, and the one
 *    in force;
 *  - set_answer_style {style}: ONE change.
 *
 * THE VALUE IS THE PC'S, NOT THIS WINDOW'S. It is not in localStorage and
 * there is no second copy: a chat sentence ("use bullet points", "no bullet
 * points", "plain paragraphs", "bullet points when it helps") changes the SAME
 * value this picker shows, and `jarvis_agent.py` puts the note in a TYPED
 * turn's request. A SPOKEN answer is never bulleted - it is read aloud.
 *
 * The state is painted from the PC's answer, never from the click: a save that
 * did not happen reads as not saved, and then the real state is read back so
 * the radio group never keeps a lie. It refreshes through the ONE rule in
 * `settings-live.js`; this setting publishes no event of its own, so that is
 * the approval queue, the window coming back into view and a bounded poll.
 *
 * @module answer-style-settings
 */

import { liveRow } from "./settings-live.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 400) {
    return "Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

function node(tag, cls, text) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text !== undefined) el.textContent = text;
  return el;
}

let busy = false;
let view = null;

function chosenLabel() {
  const row = ((view && view.choices) || []).find((c) => c.id === (view && view.style));
  return row ? row.label : "";
}

function paint(state, message, mood) {
  view = state;
  const box = $("as-choices");
  const line = $("as-status");
  const detail = $("as-detail");
  const title = $("as-title");
  if (title && state.title) title.textContent = state.title;
  if (detail && state.detail) detail.textContent = state.detail;
  if (box) {
    box.replaceChildren();
    if (state.available !== false) {
      for (const c of state.choices || []) {
        const row = node("label", "theme-row");
        row.dataset.choice = c.id;
        const radio = document.createElement("input");
        radio.type = "radio";
        radio.name = "as-style";
        radio.value = c.id;
        radio.checked = c.id === state.style;
        radio.disabled = busy;
        radio.dataset.live = "true";
        radio.addEventListener("change", () => {
          if (radio.checked) save(c.id);
        });
        const text = node("span", "theme-text");
        text.append(node("span", "theme-name", c.label), node("span", "theme-blurb", c.why));
        const tick = node("span", "theme-check", "✓");
        tick.setAttribute("aria-hidden", "true");
        row.append(radio, text, tick);
        box.append(row);
      }
    }
  }
  if (!line) return;
  if (state.available === false) {
    line.textContent = state.why || "The answer layout is not available on this PC.";
    line.dataset.mood = "bad";
    return;
  }
  line.textContent = message || chosenLabel();
  line.dataset.mood = mood || "ok";
}

async function load() {
  try {
    if (!IS_TAURI) throw new Error("no desktop backend");
    paint(await TAURI.core.invoke("get_answer_style"));
  } catch (error) {
    paint({ available: false, why: problemWords(error) });
  }
}

async function save(style) {
  if (busy) return;
  busy = true;
  paint(view || { available: true, choices: [], style: "" }, "Sending…");
  try {
    const out = await TAURI.core.invoke("set_answer_style", { style });
    paint(out, String((out && out.said) || "Done."), "ok");
  } catch (error) {
    paint(view || { available: true, choices: [], style: "" }, problemWords(error), "bad");
    try {
      paint(await TAURI.core.invoke("get_answer_style"));
    } catch (ignored) {
      paint({ available: false, why: problemWords(error) });
    }
  } finally {
    busy = false;
    if (view) paint(view);
  }
}

if ($("as-choices")) {
  // The ONE refresh rule (settings-live.js). This setting publishes no event of
  // its own; the queue, the window coming back into view and the bounded poll
  // still cover a change made by a chat sentence on the PC.
  liveRow({ read: load, kinds: null });
}
