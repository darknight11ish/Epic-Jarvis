/**
 * palette-ui.js - the command palette's half that touches the page.
 *
 * The list, the search and the words come from palette.js (which is pure, so
 * node can test it); this module only draws them into the Jarvis bar and
 * moves the focus. It is loaded by index.html, beside the approval card and
 * the primer, because the bar is where the owner already types - Alt+Space
 * is the app's own front door, so the palette needs no new window, no new
 * hotkey and no new grant.
 *
 * WHAT WAS BUILT AND WHAT WAS DELIBERATELY NOT. It offers only what already
 * exists: the six named feature groups, every menu in the catalogue, and the
 * screens (Brain's own tabs). It has no cards of its own, turns nothing on,
 * approves nothing and adds no way out of the PC. Pressing Enter opens a
 * window the owner could already open by hand.
 *
 * KEYBOARD ONLY, AND THAT IS THE POINT. The bar is a keyboard surface: a
 * real focus trap (Tab cannot leave the palette while it is open), the
 * arrows move, Enter opens, Escape closes - and the list SAYS what changed
 * through a live region, so a screen reader hears "6 matches" rather than
 * nothing. Its own keydown runs in the capture phase so Escape closes the
 * palette instead of hiding the whole bar.
 *
 * @module palette-ui
 */

import {
  HINT_LABEL,
  HINT_KEY,
  ICONS,
  ICON_VIEWBOX,
  WORDS,
  buildPalette,
  describe,
  fill,
  headingOf,
  placeFor,
  search,
} from "./palette.js";
import { announce } from "./jarvis-link.js";

const $ = (id) => document.getElementById(id);

const state = {
  open: false,
  /** Every row, built once from the catalogue when the palette first opens. */
  items: [],
  /** The rows on screen now, best first; `current` indexes into this. */
  shown: [],
  current: -1,
  /** What to put the focus back on when the palette closes. */
  restoreTo: null,
  /** Built already? The catalogue cannot change while a window is open. */
  built: false,
};

let deps = null;
let dom = null;

/** True while the palette is on screen. */
export function isOpen() {
  return state.open;
}

/* ── Drawing ─────────────────────────────────────────────────────────────── */

const SVG_NS = "http://www.w3.org/2000/svg";

/**
 * One heading's glyph, built as real SVG elements from the shape data in
 * palette.js. Deliberately not `innerHTML`: the list is built from the
 * catalogue, and tests/html-sinks.mjs walks every HTML sink in `src/` - a
 * sink that happens to be fed a constant today is one more thing to justify
 * tomorrow.
 */
function paletteGlyph(heading) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", ICON_VIEWBOX);
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  for (const shape of ICONS[heading] || []) {
    if (shape.circle) {
      const circle = document.createElementNS(SVG_NS, "circle");
      for (const [k, v] of Object.entries(shape.circle)) circle.setAttribute(k, v);
      svg.append(circle);
    } else {
      const path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("d", shape.path);
      if (shape.opacity) path.setAttribute("opacity", shape.opacity);
      svg.append(path);
    }
  }
  return svg;
}

function rowFor(entry, index) {
  const item = entry.item;
  const li = document.createElement("li");
  li.className = "palette-row";
  li.id = `palette-row-${index}`;
  li.setAttribute("role", "option");
  li.setAttribute("aria-selected", "false");
  li.dataset.index = String(index);
  li.dataset.id = item.id;

  const head = document.createElement("span");
  head.className = "palette-row-head";

  const icon = document.createElement("span");
  icon.className = "palette-row-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.append(paletteGlyph(headingOf(item)));
  head.append(icon);

  const title = document.createElement("span");
  title.className = "palette-row-title";
  title.textContent = item.title;
  head.append(title);

  if (item.hidden) {
    const hidden = document.createElement("span");
    hidden.className = "palette-row-hidden";
    // The same fact the Settings card would show: hidden is cosmetic, and
    // this is the one place it is worth saying out loud.
    hidden.textContent = "hidden";
    head.append(hidden);
  }

  li.append(head);

  const about = describe(item);
  if (about) {
    const line = document.createElement("span");
    line.className = "palette-row-about";
    line.textContent = about;
    li.append(line);
  }

  li.addEventListener("mousedown", (event) => {
    // mousedown, not click: the search field must not lose the focus first,
    // or the row is gone before a click could land on it.
    event.preventDefault();
    choose(index);
  });
  return li;
}

/** Draws the rows for the current query, and says so out loud. */
function paint() {
  const query = dom.search.value;
  state.shown = search(state.items, query);
  state.current = state.shown.length ? 0 : -1;

  dom.list.textContent = "";
  if (!state.items.length) {
    dom.empty.hidden = false;
    dom.emptyTitle.textContent = WORDS.empty_title;
    dom.emptyBody.textContent = WORDS.empty_body;
    dom.list.hidden = true;
  } else if (!state.shown.length) {
    dom.empty.hidden = false;
    dom.emptyTitle.textContent = WORDS.none_title;
    dom.emptyBody.textContent = WORDS.none_body;
    dom.list.hidden = true;
  } else {
    dom.empty.hidden = true;
    dom.list.hidden = false;
    const fragment = document.createDocumentFragment();
    state.shown.forEach((entry, index) => fragment.append(rowFor(entry, index)));
    dom.list.append(fragment);
  }

  // The count line is also the screen reader's announcement. It lives outside
  // this panel (a live region inside a hidden box announces nothing) and is
  // written only once the panel is on screen - never while it is still
  // hidden, which is the bug tests/a11y.mjs exists for.
  dom.status.textContent = countLine(query);
  mark();
}

function countLine(query) {
  const n = state.shown.length;
  if (!state.items.length) return WORDS.opened_none;
  if (!query) {
    return n === 1 ? WORDS.all_one : fill(WORDS.all_many, { n });
  }
  if (!n) return WORDS.results_none;
  return n === 1 ? WORDS.results_one : fill(WORDS.results_many, { n });
}

/** Moves the tick to row `index`, and keeps it in view. */
function mark() {
  const rows = dom.list.querySelectorAll(".palette-row");
  rows.forEach((row, i) => {
    const on = i === state.current;
    row.setAttribute("aria-selected", String(on));
    row.classList.toggle("on", on);
  });
  if (state.current >= 0) {
    dom.search.setAttribute("aria-activedescendant", `palette-row-${state.current}`);
    rows[state.current]?.scrollIntoView({ block: "nearest" });
  } else {
    dom.search.removeAttribute("aria-activedescendant");
  }
}

function move(step) {
  if (!state.shown.length) return;
  const n = state.shown.length;
  state.current = (state.current + step + n) % n;
  mark();
}

/** Opens the row at `index`: asks the app to show the place, and closes. */
function choose(index) {
  const entry = state.shown[index];
  if (!entry) return;
  const item = entry.item;
  const place = placeFor(item);
  close();
  if (!place || !deps || typeof deps.openPlace !== "function") {
    // Nothing here silently does nothing: a row whose place the app cannot
    // open says so, in the bar, rather than closing and appearing to work.
    announce(`${item.title} cannot be opened from here yet.`, "assertive");
    return;
  }
  const said = deps.openPlace(place);
  if (said) announce(said);
}

/* ── Opening and closing ─────────────────────────────────────────────────── */

export function openPalette() {
  if (state.open) return;
  if (deps && typeof deps.canOpen === "function" && !deps.canOpen()) return;

  if (!state.built) {
    state.items = buildPalette({
      hiddenFor: (id) => Boolean(deps && deps.isHidden && deps.isHidden(id)),
    });
    state.built = true;
  }

  state.open = true;
  state.restoreTo = document.activeElement;
  dom.panel.hidden = false;
  dom.root.dataset.palette = "open";
  dom.search.value = "";
  dom.status.textContent = "";
  paint();
  announce(countLine(""));
  dom.search.focus();
}

export function close() {
  if (!state.open) return;
  state.open = false;
  dom.panel.hidden = true;
  delete dom.root.dataset.palette;
  dom.status.textContent = "";
  dom.search.setAttribute("aria-expanded", "false");
  const back = state.restoreTo;
  state.restoreTo = null;
  if (back && typeof back.focus === "function" && document.contains(back)) back.focus();
  if (deps && typeof deps.onClose === "function") deps.onClose();
}

/* ── Keys ────────────────────────────────────────────────────────────────── */

function onKeydown(event) {
  if (!state.open) {
    // "/" in an empty box opens it; the box has nothing to lose by it, and
    // the primer says so. Any other key is left entirely alone.
    if (event.key === "/" && !event.ctrlKey && !event.altKey && !event.metaKey
        && event.target === dom.prompt && !dom.prompt.value) {
      event.preventDefault();
      openPalette();
    }
    return;
  }

  switch (event.key) {
    case "Escape":
      // In the capture phase, so the bar's own Escape (park the gate, stop
      // the answer, hide the window) never sees it: the first Escape closes
      // the palette, exactly as the top layer should.
      event.preventDefault();
      event.stopPropagation();
      close();
      break;
    case "ArrowDown":
      event.preventDefault();
      move(1);
      break;
    case "ArrowUp":
      event.preventDefault();
      move(-1);
      break;
    case "Home":
      if (state.shown.length) {
        event.preventDefault();
        state.current = 0;
        mark();
      }
      break;
    case "End":
      if (state.shown.length) {
        event.preventDefault();
        state.current = state.shown.length - 1;
        mark();
      }
      break;
    case "Enter":
      event.preventDefault();
      choose(state.current);
      break;
    case "Tab": {
      // A real trap: the palette is the only thing the keyboard can reach
      // while it is open. Two stops only - the search field and the list -
      // so Tab and Shift+Tab both wrap here.
      event.preventDefault();
      const stops = [dom.search, ...dom.list.querySelectorAll(".palette-row")];
      const at = stops.indexOf(document.activeElement);
      const next = event.shiftKey
        ? (at <= 0 ? stops.length - 1 : at - 1)
        : (at === stops.length - 1 ? 0 : at + 1);
      const target = stops[next];
      if (target) target.focus();
      break;
    }
    default:
      break;
  }
}

/* ── Wiring ──────────────────────────────────────────────────────────────── */

/**
 * Wires the markup up. Called once from main.js.
 *
 * @param {object} options
 * @param {(place: object) => string} [options.openPlace] opens one row's
 *   place and returns the line to announce about it (main.js owns the two
 *   navigation mechanisms this uses).
 * @param {() => boolean} [options.canOpen] false while a gate is waiting:
 *   the card is the top surface then, and the palette must not cover it.
 * @param {(id: string) => boolean} [options.isHidden] "Show or hide menus".
 * @param {() => void} [options.onClose] to re-measure the bar afterwards.
 */
export function mountPalette(options = {}) {
  deps = options;
  dom = {
    root: document.documentElement,
    panel: $("palette"),
    search: $("palette-search"),
    list: $("palette-list"),
    status: $("palette-status"),
    empty: $("palette-empty"),
    emptyTitle: $("palette-empty-title"),
    emptyBody: $("palette-empty-body"),
    prompt: $("prompt"),
    opener: $("palette-open"),
  };
  if (!dom.panel || !dom.search || !dom.list) return null;

  dom.search.setAttribute("aria-expanded", "false");
  dom.list.setAttribute("role", "listbox");
  dom.list.setAttribute("aria-labelledby", "palette-title");

  dom.search.addEventListener("input", paint);
  // A keydown as well as `input`: Escape and the arrows arrive here, and the
  // capture phase is what keeps the bar's own handlers out of it.
  document.addEventListener("keydown", onKeydown, true);
  dom.opener?.addEventListener("click", () => openPalette());
  $("palette-close")?.addEventListener("click", () => {
    close();
    dom.prompt.focus();
  });

  // Keep the field's aria-expanded honest for a screen reader that asks.
  const observer = new MutationObserver(() => {
    dom.search.setAttribute("aria-expanded", String(state.open));
  });
  observer.observe(dom.panel, { attributes: true, attributeFilter: ["hidden"] });

  return { openPalette, close, isOpen };
}

/**
 * The bar's own way in, drawn into the primer so the palette is findable at
 * all: a button (not a bare key hint) because a keyboard user reaches it
 * with Tab, and because it does something on click.
 */
export function buildPaletteHint(onOpen) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "palette-hint";
  button.textContent = `${HINT_LABEL} ${HINT_KEY}`;
  // The visible text is a key hint; the accessible name says what it does.
  button.setAttribute("aria-label", WORDS.hint);
  button.addEventListener("click", () => onOpen());
  return button;
}
