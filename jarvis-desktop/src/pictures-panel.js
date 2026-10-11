/**
 * pictures-panel.js — "Ask for a picture, and keep it" on the PC
 * (the owner's decision of 2026-09-27; `docs/JARVIS-API.md` section 124;
 * backend `jarvis_pictures.py`, `brain/pictures.rs`).
 *
 * Four commands, all of them plain reads or one named change:
 *
 *   brain_pictures           GET  /api/pictures
 *   brain_pictures_file      GET  /api/pictures/file?id=<id>
 *   brain_pictures_make      POST /api/pictures
 *   brain_pictures_settings  POST /api/pictures/settings
 *   choose_pictures_folder   the Windows "Select folder" dialog, then that
 *                            settings change
 *
 * WHAT THE OWNER SEES, AND WHAT THEY DO
 * One box to type what the picture should show, a Make button, and the
 * gallery below it: each picture with the words that made it, its seed, and
 * when it was made, plus Make another (which asks for the same words again).
 *
 * NO APPROVAL CARD, and this comment is where that is written down on this
 * side: a picture is a new file in a folder on THIS PC, drawn by a program on
 * THIS PC, from words the owner typed. It opens no way out of the PC, changes
 * no account and loosens no rule — the same shape as a timer or a note, and
 * the same as the Progress pictures beside it. Sending that picture anywhere
 * WOULD be a new named way out, and nothing here does it: there is no email,
 * upload, chat attachment or search on this page.
 *
 * WHY NOTHING HERE IS LOADED UNTIL IT IS ASKED FOR
 * A picture's bytes are fetched only when an `<img>` for it scrolls into the
 * gallery's own list, one at a time, and never while the private lists are
 * hidden. That keeps a folder of 200 pictures from crossing the wire on open.
 *
 * THE HIDING RULE
 * The prompts are the owner's own words, so the gallery hides under "Hide
 * memory lists and chat history" (and while App lock is locked) — added to
 * that rule, not beside it. Rust takes the whole answer out before this file
 * ever sees it (`hide_private` in `brain/pictures.rs`), so there is nothing
 * here to hide: this file draws the PC's own one line and a Show button, and
 * fetches no bytes at all.
 *
 * WHY EVERY SENTENCE IS THE PC'S
 * Nothing here works out a word: the folder, the sizes, the programs to
 * install, the reason a drawing failed and the "drawn in N seconds" line all
 * come from `jarvis_pictures.py`. This file only puts them on the page.
 *
 * @module pictures-panel
 */

import { announce, currentLink, linkWords, onLink } from "./jarvis-link.js";

async function invoke(command, args = {}) {
  const core = globalThis.__TAURI__ && globalThis.__TAURI__.core;
  if (!core || !core.invoke) return null;
  return core.invoke(command, args);
}

function errorText(error) {
  return String((error && error.message) || error || "Something went wrong.");
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

/** The fixed labels this page draws; every other sentence is the PC's. */
export const WORDS = {
  title: "Pictures",
  under: "Ask for a picture in your own words. Jarvis draws it on this PC and keeps it here.",
  box_label: "What should the picture show?",
  placeholder: "a red panda reading in a library, warm light",
  make: "Make a picture",
  another: "Make another",
  off: "Making pictures is switched off.",
  on: "Making pictures",
  program: "The program that draws",
  none: "Nothing chosen yet",
  folder: "Kept in",
  choose: "Choose a folder",
  showing_for: "Showing",
  seed: "Seed",
  hidden_short: "Turn off Hide memory lists to see your pictures.",
  missing: "Your PC's Jarvis does not have pictures yet — run apply-patches.ps1 on the PC.",
  under_link: "A picture is never sent anywhere by Jarvis. It stays in the folder above.",
};

const state = {
  data: null,
  /** Both routes answered "no such route": the section is not shown at all. */
  missing: false,
  error: "",
  said: "",
  /** The prompt currently in the box. */
  prompt: "",
  making: false,
  reading: false,
  again: false,
  visible: true,
  /** ids whose bytes were already fetched, so a repaint does not re-fetch. */
  loaded: new Map(),
};

/** Controls that send a change: greyed while the link cannot be confirmed. */
const live = new Set();

function syncLive(node) {
  const link = currentLink();
  const stale = !link || link.stale;
  node.disabled = stale || node.dataset.busy === "true";
  node.title = stale ? linkWords() : node.dataset.title || "";
}

function button(label, onClick, { title = "", isLive = false, fkey = "" } = {}) {
  const b = el("button", "btn small", label);
  b.type = "button";
  b.dataset.title = title;
  if (title) b.title = title;
  if (fkey) b.dataset.fkey = fkey;
  if (isLive) {
    live.add(b);
    syncLive(b);
  }
  b.addEventListener("click", async () => {
    b.dataset.busy = "true";
    b.disabled = true;
    try {
      await onClick();
    } finally {
      b.dataset.busy = "false";
      if (b.isConnected) {
        if (isLive) syncLive(b);
        else b.disabled = false;
      }
    }
  });
  return b;
}

function say(message) {
  state.said = String(message || "");
  const line = document.getElementById("pictures-said");
  if (line) line.textContent = state.said;
  if (state.said) announce(state.said, "polite");
}

onLink(() => {
  for (const node of live) if (node.isConnected) syncLive(node);
});

/* ── Reading and drawing ─────────────────────────────────────────────── */

function unavailable(raw) {
  return raw === null || raw === undefined || (raw && raw.available === false);
}

/** Reads the gallery again and draws it. One line for any error. */
export async function refreshPictures() {
  if (state.reading) {
    state.again = true;
    return;
  }
  state.reading = true;
  try {
    const raw = await invoke("brain_pictures", {});
    if (unavailable(raw)) {
      state.missing = true;
      state.data = null;
      state.error = "";
    } else {
      state.missing = false;
      state.data = raw;
      state.error = "";
    }
  } catch (error) {
    state.error = errorText(error);
    state.data = null;
  } finally {
    state.reading = false;
  }
  paint();
  if (state.again) {
    state.again = false;
    await refreshPictures();
  }
}

async function makePicture(prompt) {
  const text = String(prompt || "").trim();
  if (!text) return;
  state.making = true;
  paint();
  say("");
  try {
    const out = await invoke("brain_pictures_make", { prompt: text });
    if (unavailable(out)) {
      say(WORDS.missing);
    } else {
      say((out && out.words) || "");
      // The new picture's bytes are not in hand yet; drop the cache so the
      // next paint fetches them, and read the folder back from the PC.
      state.loaded.clear();
    }
  } catch (error) {
    // The PC's own sentence, as sent - "start it on this PC", "switched off",
    // "no program set up yet" and so on.
    say(errorText(error));
  } finally {
    state.making = false;
    await refreshPictures();
  }
}

/** Fetches ONE picture's bytes, once, and hands back a data URL. */
async function loadBytes(id) {
  if (state.loaded.has(id)) return state.loaded.get(id);
  const out = await invoke("brain_pictures_file", { id });
  if (!out || out.available === false || out.hidden || !out.png) {
    throw new Error((out && out.hidden_words) || WORDS.missing);
  }
  const url = `data:image/png;base64,${out.png}`;
  state.loaded.set(id, url);
  return url;
}

/* ── Drawing ─────────────────────────────────────────────────────────── */

function hiddenBlock(words) {
  const wrap = el("div", "private-hidden pg-hidden");
  wrap.dataset.kind = "pictures";
  wrap.append(el("p", "empty", words || WORDS.hidden_short));
  wrap.append(
    button(
      "Show",
      async () => {
        try {
          await invoke("reveal_private_answers");
        } catch (error) {
          say(errorText(error));
          return;
        }
        await refreshPictures();
        if (state.data && state.data.hidden) say(WORDS.hidden_short);
      },
      { title: "Lift Hide memory lists for this window", fkey: "show:pictures" },
    ),
  );
  return wrap;
}

function askBlock(d, canAct) {
  const row = el("div", "row");
  const label = el("label", "", WORDS.box_label);
  const id = "pictures-prompt";
  label.setAttribute("for", id);
  const box = el("input");
  box.id = id;
  box.type = "text";
  box.maxLength = 2000;
  box.autocomplete = "off";
  box.spellcheck = false;
  box.placeholder = WORDS.placeholder;
  box.value = state.prompt;
  box.addEventListener("input", () => {
    state.prompt = box.value;
  });
  box.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !state.making) makePicture(box.value);
  });
  const make = button(WORDS.make, () => makePicture(box.value), {
    title: "Draw this picture on this PC and keep it",
    isLive: true,
    fkey: "make",
  });
  // `syncLive` above already greyed it when the link is stale; this adds the
  // one thing it cannot know - a drawing is already running.
  if (state.making) {
    make.disabled = true;
    make.textContent = "Drawing…";
  }
  row.append(label, box, make);
  const wrap = el("div", "pg-block");
  wrap.append(row);
  wrap.append(el("p", "note", WORDS.under_link));
  if (!canAct) wrap.append(el("p", "note", linkWords()));
  return wrap;
}

function settingsBlock(d) {
  // Read-only on this page: the switch, the drawing program and the folder are
  // "Making pictures" in Settings -> Pictures, which the backend accepts only
  // from this PC. What the owner needs here is the STATE, and one line telling
  // them where to change it - not a second set of controls that could disagree
  // with the first.
  const block = el("div", "pg-block pg-pictures-settings");
  const line = el("p", "note");
  line.textContent = [
    `${WORDS.on}: ${d.enabled ? "on" : "off"}`,
    d.runtime_plain ? `${WORDS.program}: ${d.runtime_plain}` : `${WORDS.program}: ${WORDS.none}`,
    `${WORDS.folder}: ${d.folder || ""}`,
  ]
    .filter(Boolean)
    .join(" · ");
  block.append(line);
  const size = el("p", "note");
  size.textContent = [
    `${d.count} ${d.count === 1 ? "picture" : "pictures"}`,
    d.size_words,
  ]
    .filter(Boolean)
    .join(" · ");
  block.append(size);
  block.append(el("p", "note", "Turn it on, choose the program and pick the folder in Settings, under Pictures."));
  block.append(el("p", "note", d.keep || ""));
  return block;
}

function pictureRow(p, canAct) {
  const card = el("figure", "pg-picture");
  card.dataset.id = p.id;
  const img = el("img");
  img.alt = p.prompt ? `A picture: ${p.prompt}` : "A picture Jarvis drew";
  img.loading = "lazy";
  img.width = 256;
  img.height = 256;
  const placeholder = el("div", "pg-picture-pending", "Loading…");
  card.append(placeholder);
  // One picture at a time, and only when it is on screen.
  const start = async () => {
    try {
      const url = await loadBytes(p.id);
      img.src = url;
      placeholder.replaceWith(img);
    } catch (error) {
      placeholder.textContent = errorText(error);
    }
  };
  if (typeof IntersectionObserver === "function") {
    const seen = new IntersectionObserver((entries, obs) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          obs.disconnect();
          start();
        }
      }
    });
    seen.observe(card);
  } else {
    start();
  }

  const caption = el("figcaption");
  caption.append(el("p", "pg-words", p.prompt || "This picture's note is missing."));
  const bits = [];
  if (p.made_at_words) bits.push(p.made_at_words);
  if (p.seed !== null && p.seed !== undefined) bits.push(`${WORDS.seed} ${p.seed}`);
  if (p.model) bits.push(p.model);
  if (bits.length) caption.append(el("p", "note", bits.join(" · ")));
  if (!p.record) {
    caption.append(el("p", "note", "The note beside this picture is gone, so what made it is not known."));
  }
  caption.append(
    button(
      WORDS.another,
      () => makePicture(p.prompt),
      { title: "Ask for this one again", isLive: true, fkey: `again:${p.id}` },
    ),
  );
  card.append(caption);
  return card;
}

function gallery(d, canAct) {
  const block = el("div", "pg-block");
  block.append(el("h3", "subhead", WORDS.showing_for));
  if (!d.pictures || !d.pictures.length) {
    block.append(el("p", "empty", "No pictures yet. Ask for one and it will appear here."));
    return block;
  }
  for (const p of d.pictures) block.append(pictureRow(p, canAct));
  return block;
}

function paint() {
  const box = document.getElementById("pictures-root");
  if (!box) return;
  if (!state.visible) {
    box.replaceChildren();
    return;
  }
  const card = el("section", "card card-wide pg-pictures");
  card.setAttribute("aria-label", WORDS.title);
  card.append(el("h2", "", WORDS.title));
  card.append(el("p", "note", state.data && state.data.under ? state.data.under : WORDS.under));

  if (state.missing) {
    card.append(el("p", "empty", WORDS.missing));
    box.replaceChildren(card);
    return;
  }
  if (state.error) {
    card.append(el("p", "empty", state.error));
    box.replaceChildren(card);
    return;
  }
  const d = state.data;
  if (!d) {
    card.append(el("p", "note", "Asking Jarvis…"));
    box.replaceChildren(card);
    return;
  }
  const canAct = !(currentLink() || {}).stale;
  if (d.hidden) {
    card.append(hiddenBlock(d.hidden_words));
    box.replaceChildren(card);
    return;
  }
  if (d.words) {
    // The one plain sentence when nothing is set up, or when the switch is
    // off: never an error banner, never a silent blank section.
    const line = el("p", d.enabled ? "note" : "empty", d.words);
    line.id = "pictures-words";
    card.append(line);
  }
  if (d.enabled) card.append(askBlock(d, canAct));
  card.append(settingsBlock(d));
  if (d.enabled) card.append(gallery(d, canAct));

  const said = el("p", "pg-said", state.said);
  said.id = "pictures-said";
  said.setAttribute("role", "status");
  card.append(said);
  box.replaceChildren(card);
  for (const node of live) if (node.isConnected) syncLive(node);
}

/** The Projects view calls this: the panel sits above the project list. */
export function setPicturesVisible(on) {
  state.visible = !!on;
  if (!state.visible) {
    const box = document.getElementById("pictures-root");
    if (box) box.replaceChildren();
  }
}
