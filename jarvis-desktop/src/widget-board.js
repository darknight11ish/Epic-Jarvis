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
 * HTML, and the only style it sets is the widget's own look, from this
 * file's closed lists (`applyLook`).
 *
 * The widget also carries one of four ARRANGEMENTS (`LAYOUTS`, 2026-10-30),
 * and `boardOf` is the one rule that turns a view into what is drawn: which
 * block is drawn large, in what order the rest go, and the buttons last. The
 * phone carries the same rule, held to it case for case by the same fixture.
 *
 * The apps check again what the PC already checked: a block type or button
 * this file does not know is left out, and a source it does not know is
 * treated as private.
 *
 * A widget also carries a LOOK (2026-11-14): an accent, a shade and a
 * contrast, all three CLOSED lists (`ACCENTS`, `SHADES`, `CONTRASTS` below,
 * the PC's jarvis_widgets.py and the phone's net/JarvisWidgets.kt, held
 * equal by tests/fixtures/widget-cases.json). It is a colour and an alpha,
 * not an arrangement: `boardOf` is untouched by it, and being see-through
 * never hides a block. `paint` hands it to `applyLook`, which sets colours
 * and alphas on the box and nothing else - no font, image, size or position,
 * and every value comes from this file's own lists, so nothing the PC wrote
 * ever becomes CSS.
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

/** The four arrangements a widget can be drawn in (2026-10-30): a CLOSED
 *  list. The PC's is jarvis_widgets.LAYOUTS and the phone's is
 *  net/JarvisWidgets.LAYOUTS; all three are held equal by
 *  tests/fixtures/widget-cases.json. A widget's look cannot be invented,
 *  because a RemoteViews layout is a resource compiled into the app. */
export const LAYOUTS = ["stack", "big", "list", "compact"];
export const LAYOUT_STACK = "stack";

/** The eight accents a widget may wear (2026-11-14): a CLOSED list of NAMED
 *  colours, the PC's `jarvis_widgets.ACCENTS` and the phone's
 *  `JarvisWidgets.ACCENTS`. The owner says a colour word, the PC's own model
 *  maps it to one of these names - never a hex, because a widget nobody can
 *  read is worse than one in the second-best colour. `cyan` is the default and
 *  the colour every widget drew in before the look existed. */
export const ACCENTS = {
  cyan: { label: "Cyan", hex: "#63F7FF" },
  sky: { label: "Sky", hex: "#8CC9FF" },
  violet: { label: "Violet", hex: "#BFA6FF" },
  pink: { label: "Pink", hex: "#FF93C7" },
  amber: { label: "Amber", hex: "#FFC661" },
  lime: { label: "Lime", hex: "#B9E86B" },
  orange: { label: "Orange", hex: "#FF9E5C" },
  mono: { label: "Mono", hex: "#E6EEF7" },
};

/** How see-through a widget is: the CARD's alpha and the PANEL's, as the
 *  PC's own 0-255 bytes (`jarvis_widgets.SHADES`; the same three numbers in
 *  widget-cases.json). Text never takes an alpha - a see-through widget still
 *  has to be readable. There is no blur, on either app. */
export const SHADES = {
  solid: { label: "Solid", alpha: 255, surfaceAlpha: 255 },
  half: { label: "Half see-through", alpha: 191, surfaceAlpha: 159 },
  clear: { label: "See-through", alpha: 128, surfaceAlpha: 102 },
};

/** The two palettes (`jarvis_widgets.CONTRASTS`). `normal` is what every
 *  widget has drawn in until now; `high` is white on black with a lighter
 *  panel and a lifted muted text, because half a widget is written in it.
 *  The four keys are the wire's own names, so the fixture compares directly. */
export const CONTRASTS = {
  normal: { label: "Normal",
    colors: { bg: "#04070C", surface: "#0E1822", text_hi: "#E6EEF7", text_muted: "#93A6BA" } },
  high: { label: "High contrast",
    colors: { bg: "#000000", surface: "#262626", text_hi: "#FFFFFF", text_muted: "#E0E0E0" } },
};

/** What a widget with no look key of its own draws in (`look_default`). */
export const LOOK_DEFAULT = { accent: "cyan", shade: "solid", contrast: "normal" };

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
/** Every source the PC's own menu can fill (jarvis_widgets.SOURCES), in that
 *  order. The phone carries the same list (net/JarvisWidgets.kt
 *  KNOWN_SOURCES), and a source that is NOT here is drawn as private - so a
 *  list that lags the PC hides a value the PC says is not private at all.
 *  The last three were on the PC's menu and in the phone's list and missing
 *  here, so "approvals waiting", "graphics memory" and "tokens a second" were
 *  each drawn as if they held the owner's own words. */
const KNOWN_SOURCES = [...PRIVATE_SOURCES, "approvals_count", "disk_free", "email_count",
  "events_count", "focus", "gpu_memory", "reminders_count", "todo_count", "tokens_per_second"];
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

/** The arrangement an app draws from one show answer: a value on the closed
 *  list, else "stack". A newer PC's word this app does not know must leave the
 *  widget drawable - exactly as an unknown source is treated as private. */
export function layoutOf(ans) {
  const got = ans && typeof ans === "object" ? ans.layout : undefined;
  return typeof got === "string" && LAYOUTS.includes(got) ? got : LAYOUT_STACK;
}

/** The look a widget draws in, from one show answer: each key on ITS closed
 *  list, else that list's default - so a newer PC's `shade: "frosted"` costs
 *  the shade and not the widget, exactly as `layoutOf` does for a layout. */
export function lookOf(ans) {
  const got = ans && typeof ans === "object" ? ans : {};
  const pick = (key, table) => {
    const value = got[key];
    return typeof value === "string" && Object.hasOwn(table, value) ? value : LOOK_DEFAULT[key];
  };
  return {
    accent: pick("accent", ACCENTS),
    shade: pick("shade", SHADES),
    contrast: pick("contrast", CONTRASTS),
  };
}

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
  return { name: text(ans.name, LIMITS.name), layout: layoutOf(ans), ...lookOf(ans), blocks: out };
}

/** The same view while private words are hidden (App lock, or "Hide
 *  memory lists and chat history"): a private block keeps its label only.
 *  The look goes with it untouched: hiding words never changes a colour. */
export function hideView(view) {
  if (!view) return null;
  return {
    name: view.name,
    layout: view.layout,
    ...lookOf(view),
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

/** GET /api/widgets as the Brain reads it. A row that carries its `blocks`
 *  (the PC sends them for a widget and for a preview) also carries the `view`
 *  the Brain draws its preview from: the draft's own shape and its own look,
 *  so the three pickers under it repaint the real widget rather than a
 *  mock-up. The list's blocks are the ones the PC validated, NOT filled in -
 *  only a show fills in live numbers - so the preview shows the shape, the
 *  labels and the colours, and the numbers arrive with the widget itself.
 *  A row without blocks (an older PC, or one hiding the private lists) has no
 *  view, and the Brain simply draws no preview. */
export function readList(ans) {
  if (!ans || typeof ans !== "object") return null;
  if (ans.available === false) return { available: false, why: String(ans.why || MISSING) };
  const rows = (list) => (Array.isArray(list) ? list : [])
    .filter((w) => w && typeof w.id === "string")
    .map((w) => ({ id: w.id, name: text(w.name, LIMITS.name), said: text(w.said, 400),
      parts: (Array.isArray(w.parts) ? w.parts : []).slice(0, LIMITS.blocks)
        .map((p) => text(p, 160)).filter(Boolean),
      view: Array.isArray(w.blocks) && w.blocks.length
        ? viewOf({ ok: true, name: w.name, layout: w.layout, accent: w.accent,
          shade: w.shade, contrast: w.contrast, blocks: w.blocks })
        : null }));
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
 * The widget arranged in its own `view.layout`: the block drawn LARGE
 * (`big`, or null), the blocks in draw order, and the buttons, always last.
 * The ONE rule both apps follow (tools/gen_widget_cases.py `arrange()`), so
 * "big", "list" and "compact" cannot mean two different things on the PC and
 * the phone.
 *
 * - `stack`: every non-button block, in the order given (today's shape);
 * - `big`: the FIRST number drawn large above the rest; with no number it is
 *   `stack`;
 * - `list`: heading, then lists, then numbers, then bars;
 * - `compact`: one heading (its own, else the widget's name) and ONE block, a
 *   list cut to its first item with the rest counted into `more`.
 *
 * Anything else is `stack`, the same fallback `layoutOf` makes.
 */
export function boardOf(view) {
  if (!view) return null;
  const buttons = view.blocks.filter((b) => b.type === "button");
  const body = view.blocks.filter((b) => b.type !== "button");
  if (view.layout === "big") {
    const big = body.find((b) => b.type === "number") || null;
    if (big) return { big, blocks: body.filter((b) => b !== big), buttons };
  } else if (view.layout === "list") {
    const order = { title: 0, list: 1, number: 2, progress: 3 };
    return { big: null, blocks: [...body].sort((a, b) => order[a.type] - order[b.type]), buttons };
  } else if (view.layout === "compact") {
    const title = body.find((b) => b.type === "title") || null;
    const head = title || (view.name ? { type: "title", text: view.name } : null);
    const rest = body.filter((b) => b !== title);
    const blocks = head ? [head] : [];
    const one = rest[0];
    if (one && one.type === "list") {
      blocks.push({ ...one, items: one.items.slice(0, 1),
        more: one.more + Math.max(0, one.items.length - 1) });
    } else if (one) {
      blocks.push({ ...one });
    }
    return { big: null, blocks, buttons };
  }
  return { big: null, blocks: body, buttons };
}

/**
 * Puts a widget's look on the box it is drawn in, as CSS custom properties:
 * the contrast's four colours, the accent's hex, and the shade's two alphas.
 * `board.css` reads them, with the app's own theme as the fallback, so a box
 * that has never been given a look draws exactly as it did.
 *
 * Nothing else is set. This is the only place in this file that touches a
 * style at all, and every value is one of the closed lists above: the PC's
 * answer only ever picks an ID, never a colour.
 */
export function applyLook(box, look) {
  const chosen = lookOf(look);
  const shade = SHADES[chosen.shade];
  const colors = CONTRASTS[chosen.contrast].colors;
  const set = (name, value) => box.style.setProperty(name, value);
  set("--board-bg", colors.bg);
  set("--board-surface", colors.surface);
  set("--board-text-hi", colors.text_hi);
  set("--board-text-muted", colors.text_muted);
  set("--board-accent", ACCENTS[chosen.accent].hex);
  set("--board-bg-a", cssAlpha(shade.alpha));
  set("--board-surface-a", cssAlpha(shade.surfaceAlpha));
}

/** A shade's 0-255 byte as the 0-1 number CSS takes (`color-mix`), to three
 *  places: 255 is "1", 191 is "0.749", 128 is "0.502". */
const cssAlpha = (byte) => String(Math.round((byte / 255) * 1000) / 1000);

/**
 * Draws a view into `box` with DOM calls only, in the arrangement
 * `boardOf` chose, in the view's own look (`applyLook`). `canPress(action)`
 * says whether a button may be pressed now (a stale link greys all but Stop
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
  // Both surfaces that draw a widget paint through here - the Brain's preview
  // and the widget window - so the look is applied in one place and neither
  // can show a colour the other does not. No view is the default look, so an
  // emptied preview goes back to it rather than keeping the last one.
  applyLook(box, view);
  const nodes = [];
  if (!view) {
    box.replaceChildren();
    return;
  }
  const part = (b, big) => {
    if (b.type === "title") return el("p", "board-title", b.text);
    const node = el("div", `board-part board-${b.type}${big ? " board-big" : ""}`);
    if (b.hidden) node.dataset.hidden = "true";
    const head = el("div", "board-head");
    head.append(el("span", "board-label", b.label));
    if (b.type === "number" && b.value) head.append(el("span", "board-value board-count mono", b.value));
    if (b.type === "progress" && b.value) head.append(el("span", "board-value", b.value));
    node.append(head);
    if (b.type === "progress") {
      const track = el("div", "meter-track");
      const bar = el("i");
      bar.style.transform = `scaleX(${b.fraction})`;
      track.append(bar);
      node.append(track);
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
        node.append(ul);
        if (b.more) node.append(el("p", "board-note board-more", `+${b.more} more`));
      } else if (!b.note && b.empty) {
        node.append(el("p", "board-note", b.empty));
      }
    }
    if (b.note) node.append(el("p", "board-note", b.note));
    return node;
  };
  const board = boardOf(view);
  if (board.big) nodes.push(part(board.big, true));
  for (const b of board.blocks) nodes.push(part(b, false));
  const buttons = el("div", "board-buttons");
  for (const b of board.buttons) {
    const btn = el("button", "btn btn-quiet board-button", b.label);
    btn.type = "button";
    btn.dataset.action = b.action;
    btn.disabled = !canPress(b.action);
    btn.addEventListener("click", () => onPress(b.action, btn));
    buttons.append(btn);
  }
  if (buttons.childElementCount) nodes.push(buttons);
  box.replaceChildren(...nodes);
}
