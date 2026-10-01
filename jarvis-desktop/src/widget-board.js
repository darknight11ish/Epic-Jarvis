/**
 * "Widgets you describe" (the owner's choice of 2026-09-28, the SAFE
 * version; JARVIS-API.md section 86; backend jarvis_widgets.py; Rust
 * brain/widgets.rs).
 *
 * A widget is a small CHECKED DESCRIPTION the PC keeps - never code. This
 * file holds the words both apps use, and the one rule for drawing a widget
 * the PC filled in (`viewOf`, `hideView`) - the same rule as the phone's
 * net/JarvisWidgets.kt and tools/gen_widget_cases.py, held together by
 * tests/fixtures/widget-cases.json. It draws with DOM calls and
 * `textContent` only: nothing the PC or the model wrote is ever parsed as
 * HTML, and there is no style, colour, link or script to set.
 *
 * The apps check again what the PC already checked: a block type or button
 * this file does not know is left out, and a source it does not know is
 * treated as private.
 */

export const TITLE = "Widgets";
export const DETAIL =
  "Describe a small widget and Jarvis makes a preview: a heading, numbers, short lists, a bar " +
  "and up to four buttons, from a fixed menu. You see the preview first, and nothing is added " +
  "until you tap Add. Delete removes one at once.";
export const HINT =
  "For example: \"my next 3 reminders, my to-do count and a 10-minute timer button\". You can " +
  "also say \"make me a widget showing ...\" to Jarvis. Show one on your desktop from the " +
  "widget window's \"Your widget\" list, or on your phone's home screen as a Jarvis widget.";
export const EMPTY = "No widgets yet.";
export const MISSING =
  "Your PC's Jarvis cannot make widgets yet - run apply-patches.ps1 on the PC.";
export const PREVIEW_TITLE = "Preview - not added yet";
export const MAKE_LABEL = "Make a preview";
export const MAKING_LABEL = "Making…";
export const ADD_LABEL = "Add";
export const DISCARD_LABEL = "Discard";
export const DELETE_LABEL = "Delete";
export const PICK_LABEL = "Your widget";
export const FACE_OPTION = "Jarvis's face";
export const HIDDEN_WORDS = "Hidden - open Jarvis to see it.";
export const MAX_WORDS = 300;

/** The five buttons - the phone's Quick Settings tile actions, same words. */
export const ACTIONS = {
  focus: "Focus session",
  timer: "10-min timer",
  brief_me: "Brief me",
  stop_everything: "Stop everything",
  pc_play_pause: "Play/pause PC",
};
/** Under App lock, every other button opens the Jarvis bar instead of acting
 *  (the owner, 2026-09-28). brain/widgets.rs `LOCKED_OPENS_BAR`. */
export const LOCKED_OPENS_BAR =
  "App lock is on, so this opens the Jarvis bar instead. Unlock it, then ask Jarvis there.";
/** Buttons that still work on a stale link: they only stop, or only open. */
export const NEVER_HELD = ["stop_everything", "brief_me"];
export const PRIVATE_SOURCES = ["current_task", "now_playing", "reminders", "timers", "today", "todo"];
const KNOWN_SOURCES = [...PRIVATE_SOURCES, "disk_free", "email_count", "events_count", "focus",
  "reminders_count", "todo_count"];
export const LIMITS = { blocks: 8, items: 5, name: 40, text: 60, label: 40 };

/** Text as both apps draw it: control and format characters out, ASCII
 *  white space collapsed, at most `cap` characters (code points). */
export function text(v, cap) {
  if (typeof v !== "string") return "";
  const s = v
    .replace(/[\p{Cc}\p{Cf}]/gu, (c) => (" \t\n\r\f\v".includes(c) ? c : ""))
    .replace(/[ \t\n\r\f\v]+/g, " ")
    .replace(/^ +| +$/g, "");
  return Array.from(s).slice(0, cap).join("").replace(/ +$/, "");
}

const int = (v) => (Number.isInteger(v) && v >= 0 ? v : 0);

/** The blocks this app draws from one GET /api/widgets/show answer, or null. */
export function viewOf(ans) {
  if (!ans || typeof ans !== "object" || Array.isArray(ans) || ans.ok !== true) return null;
  const blocks = Array.isArray(ans.blocks) ? ans.blocks : [];
  const out = [];
  for (const b of blocks.slice(0, LIMITS.blocks)) {
    if (!b || typeof b !== "object" || Array.isArray(b)) continue;
    const t = b.type;
    if (t === "title") {
      const s = text(b.text, LIMITS.text);
      if (s) out.push({ type: "title", text: s });
    } else if (t === "button") {
      if (typeof b.action === "string" && Object.hasOwn(ACTIONS, b.action)) {
        out.push({ type: "button", action: b.action, label: ACTIONS[b.action] });
      }
    } else if (t === "number" || t === "list" || t === "progress") {
      const src = typeof b.source === "string" ? b.source : "";
      const priv = b.private !== false || !KNOWN_SOURCES.includes(src) || PRIVATE_SOURCES.includes(src);
      const v = { type: t, label: text(b.label, LIMITS.label), note: text(b.note, 120),
        private: priv, hidden: false };
      if (t === "number") {
        v.value = text(b.value, 20);
      } else if (t === "list") {
        const items = (Array.isArray(b.items) ? b.items : [])
          .filter((i) => i && typeof i === "object" && !Array.isArray(i));
        v.items = items.slice(0, LIMITS.items).map((i) => ({ text: text(i.text, 120),
          when: text(i.when, 40) }));
        v.more = int(b.more) + Math.max(0, items.length - LIMITS.items);
        v.empty = text(b.empty, 60);
      } else {
        const f = typeof b.fraction === "number" && Number.isFinite(b.fraction) ? b.fraction : 0;
        v.fraction = Math.min(1, Math.max(0, f));
        v.value = text(b.value, 60);
      }
      out.push(v);
    }
  }
  return { name: text(ans.name, LIMITS.name), blocks: out };
}

/** The same view while private words are hidden (App lock, or "Hide
 *  memory lists and chat history"): a private block keeps its label only. */
export function hideView(view) {
  if (!view) return null;
  return {
    name: view.name,
    blocks: view.blocks.map((b) => {
      if (!b.private) return { ...b };
      const h = { ...b, hidden: true, note: HIDDEN_WORDS };
      if (b.type === "number") h.value = "";
      if (b.type === "list") { h.items = []; h.more = 0; }
      if (b.type === "progress") { h.fraction = 0; h.value = ""; }
      return h;
    }),
  };
}

/** GET /api/widgets as the Brain reads it. */
export function readList(ans) {
  if (!ans || typeof ans !== "object") return null;
  if (ans.available === false) return { available: false, why: String(ans.why || MISSING) };
  const rows = (list) => (Array.isArray(list) ? list : [])
    .filter((w) => w && typeof w.id === "string")
    .map((w) => ({ id: w.id, name: text(w.name, LIMITS.name), said: text(w.said, 400),
      parts: (Array.isArray(w.parts) ? w.parts : []).slice(0, LIMITS.blocks)
        .map((p) => text(p, 160)).filter(Boolean) }));
  return { available: true, widgets: rows(ans.widgets), drafts: rows(ans.drafts),
    noCard: text(ans.no_card, 400), hidden: Boolean(ans.hidden) };
}

/** The description box's check before anything is sent. */
export function draftArgs(words, pasted) {
  const w = typeof words === "string" ? words.split(/\s+/).filter(Boolean).join(" ") : "";
  if (!w) return { error: "Say what the widget should show - for example, your next 3 reminders and a timer button." };
  if (Array.from(w).length > MAX_WORDS) {
    return { error: `That is too long for a widget. Keep it under ${MAX_WORDS} characters.` };
  }
  return { words: w, pasted: Boolean(pasted) };
}

/**
 * Draws a view into `box` with DOM calls only. `canPress(action)` says
 * whether a button may be pressed now (a stale link greys all but Stop
 * everything and Brief me); `onPress(action)` presses it.
 */
export function paint(box, view, { canPress = () => true, onPress = () => {} } = {}) {
  const doc = box.ownerDocument;
  const el = (tag, cls, words) => {
    const n = doc.createElement(tag);
    if (cls) n.className = cls;
    if (words !== undefined) n.textContent = words;
    return n;
  };
  const nodes = [];
  if (!view) {
    box.replaceChildren();
    return;
  }
  const buttons = el("div", "board-buttons");
  for (const b of view.blocks) {
    if (b.type === "title") {
      nodes.push(el("p", "board-title", b.text));
    } else if (b.type === "button") {
      const btn = el("button", "btn btn-quiet board-button", b.label);
      btn.type = "button";
      btn.dataset.action = b.action;
      btn.disabled = !canPress(b.action);
      btn.addEventListener("click", () => onPress(b.action, btn));
      buttons.append(btn);
    } else {
      const part = el("div", `board-part board-${b.type}`);
      if (b.hidden) part.dataset.hidden = "true";
      const head = el("div", "board-head");
      head.append(el("span", "board-label", b.label));
      if (b.type === "number" && b.value) head.append(el("span", "board-value mono", b.value));
      if (b.type === "progress" && b.value) head.append(el("span", "board-value", b.value));
      part.append(head);
      if (b.type === "progress") {
        const track = el("div", "meter-track");
        const bar = el("i");
        bar.style.transform = `scaleX(${b.fraction})`;
        track.append(bar);
        part.append(track);
      }
      if (b.type === "list") {
        if (b.items.length) {
          const ul = el("ul", "board-items");
          for (const i of b.items) {
            const li = el("li");
            li.append(el("span", "board-item", i.text));
            if (i.when) li.append(el("span", "board-when mono", i.when));
            ul.append(li);
          }
          part.append(ul);
          if (b.more) part.append(el("p", "board-note", `+${b.more} more`));
        } else if (!b.note && b.empty) {
          part.append(el("p", "board-note", b.empty));
        }
      }
      if (b.note) part.append(el("p", "board-note", b.note));
      nodes.push(part);
    }
  }
  if (buttons.childElementCount) nodes.push(buttons);
  box.replaceChildren(...nodes);
}
