/**
 * pictures-panel.js — "Ask for a picture, and keep it" on the PC
 * (the owner's decision of 2026-09-27; `docs/JARVIS-API.md` section 129;
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
 * TWO STEPS WHEN THE CHAT IS HOLDING THE CARD (Image mode, 2026-10-24)
 * A drawing needs the 12 GB card, and the everyday chat is usually sitting on
 * it. So the first request carries the prompt alone. If the PC answers **409**
 * with `needs: "free_card"`, NOTHING WAS DRAWN: this page puts the PC's own
 * sentence on screen with one confirm button ("Set the chat aside and draw
 * (about 5 minutes)") and a Not now, and stops there. Only that click sends the
 * retry, with `free_card: true`; the PC steps the chat aside, draws, and loads
 * the chat back. Nothing is retried on its own - moving the chat out from under
 * the owner is their decision, not this page's.
 *
 * While the handshake runs the page says so and for how long, because a draw
 * takes MINUTES, not seconds (one measured on this PC at 274 s), and the Make
 * button stays greyed for the whole of it. A 409 with `needs: "card_none"` is
 * not a question at all - no way of making pictures is switched on - so its
 * `error` sentence is the whole answer. When a drawing does come back, the
 * gallery is read again from the PC and the PC's own success sentence is shown
 * ONCE: the backend already appends "stepped aside ... and is back" to `words`,
 * and `card.words` repeats that same sentence, so adding both would print it
 * twice. `card.words` is only the fallback for a PC whose `words` is empty.
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
  // The PC's own 409 question, and the owner's two answers to it. The button's
  // "(about N minutes)" is added from the PC's estimate; nothing here guesses
  // one.
  set_aside: "Set the chat aside and draw",
  set_aside_no: "Not now",
  set_aside_stopped: "Nothing was drawn - your everyday chat stays where it is.",
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
  /**
   * The PC's 409 question, waiting for the owner's yes or no:
   * `{ prompt, error, option, seconds }`, or null. It is NOT a retry that has
   * been queued - nothing is sent again until the confirm button is clicked.
   */
  pending: null,
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
  // A new request replaces any earlier question: only the newest prompt is
  // worth an answer, and the old one was never sent.
  state.pending = null;
  state.making = true;
  paint();
  say("");
  try {
    const out = await invoke("brain_pictures_make", { prompt: text });
    handleMakeAnswer(out, text);
  } catch (error) {
    // The PC's own sentence, as sent - "start it on this PC", "switched off",
    // "no program set up yet" and so on.
    say(errorText(error));
  } finally {
    state.making = false;
    await refreshPictures();
  }
}

/** A whole number of seconds the PC sent, or 0 - never NaN in a sentence. */
function secondsOf(value) {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

/** The minutes a sentence may say "about": at least one, never "about 0". */
function minutesOf(seconds) {
  const n = secondsOf(seconds);
  return n ? Math.max(1, Math.round(n / 60)) : 0;
}

function stretchWords(seconds) {
  const minutes = minutesOf(seconds);
  if (!minutes) return "a few minutes";
  return `about ${minutes} ${minutes === 1 ? "minute" : "minutes"}`;
}

/** The working state for a drawing: minutes, and where the chat went. */
function drawingWords(seconds) {
  return `Drawing - this takes ${stretchWords(seconds)}. ` +
    "Your everyday chat will come back when it is done.";
}

/** "Set the chat aside and draw (about 5 minutes)", from the PC's estimate. */
function setAsideLabel(seconds) {
  const minutes = minutesOf(seconds);
  if (!minutes) return WORDS.set_aside;
  return `${WORDS.set_aside} (about ${minutes} ${minutes === 1 ? "minute" : "minutes"})`;
}

/**
 * What the PC said to a drawing request. THREE ANSWERS, and they are not the
 * same thing:
 *
 *   * `needs: "free_card"` - NOTHING WAS DRAWN. The everyday chat is using the
 *     12 GB card and the PC is asking whether it may step the chat aside. The
 *     question is drawn, the owner answers it, and only then is anything sent
 *     again.
 *   * `needs: "card_none"` - no way of making pictures is switched on. The
 *     PC's own `error` sentence is the whole answer; there is nothing to
 *     confirm, so no button is drawn.
 *   * anything else - the PC's own `words`. After a handshake that sentence
 *     already ends with "stepped aside ... and is back" (the backend appends
 *     it), and `card.words` is that same sentence again - it is a fallback for
 *     a PC that answers without `words`, never something added on top.
 */
function handleMakeAnswer(out, prompt) {
  if (unavailable(out)) {
    say(WORDS.missing);
    return;
  }
  if (out.needs === "free_card") {
    askToSetAside(out, prompt);
    return;
  }
  if (out.needs) {
    // Any other need is a sentence, not a yes/no this page can offer.
    say(out.error || "");
    return;
  }
  if (out.ok === false) {
    say(out.error || "");
    return;
  }
  // ONE sentence, not two: the PC's `words` already carries the swap sentence
  // when the card was stepped aside, and `card.words` is that same sentence
  // again, so joining them printed the swap twice on every confirmed draw.
  // `card.words` is only reached when a PC answers without `words` at all.
  const made = String((out && out.words) || "");
  const cardWords = out && out.card ? String(out.card.words || "") : "";
  const said = made || cardWords;
  say(said);
  // The new picture's bytes are not in hand yet; drop the cache so the next
  // paint fetches them (the gallery itself is read back by the caller).
  state.loaded.clear();
}

/** The PC's 409, kept whole: this is a question, so it is drawn as one. */
function askToSetAside(out, prompt) {
  const estimate = (out && out.estimate) || {};
  state.pending = {
    prompt,
    error: String((out && out.error) || ""),
    option: String((out && out.option) || ""),
    seconds: secondsOf(estimate.chat_away_seconds) || secondsOf(estimate.draw_seconds),
  };
  say("");
  // The sentence is drawn in the question block; say it out loud as well, so
  // the owner knows a drawing stopped to ask them something.
  if (state.pending.error) announce(state.pending.error, "polite");
}

/** The owner said yes: the ONE place `free_card: true` is ever sent. */
async function setChatAsideAndDraw() {
  const pending = state.pending;
  if (!pending || state.making) return;
  // The question is answered, so it goes before the wait starts: what stays on
  // screen is the honest picture of what is happening.
  state.pending = null;
  state.making = true;
  say(drawingWords(pending.seconds));
  paint();
  try {
    const out = await invoke("brain_pictures_make", {
      prompt: pending.prompt,
      // Tauri's command arguments are camelCase by default, so this is the
      // Rust side's `free_card`. It is never sent on the first try.
      freeCard: true,
    });
    // The same question can come back (the chat grabbed the card again between
    // the yes and the draw). Ask again - never loop on its own.
    handleMakeAnswer(out, pending.prompt);
  } catch (error) {
    say(errorText(error));
  } finally {
    state.making = false;
    // Read the folder back from the PC: a picture that was drawn is on disk.
    await refreshPictures();
  }
}

/** The owner said no: nothing was sent, and nothing was drawn. */
function cancelPending() {
  if (!state.pending) return;
  state.pending = null;
  say(WORDS.set_aside_stopped);
  paint();
}

/** The PC's own question, with the owner's two answers under it. */
function pendingBlock() {
  const block = el("div", "pg-block pg-pictures-free-card");
  block.dataset.kind = "free-card";
  if (state.pending.error) block.append(el("p", "note", state.pending.error));
  const row = el("div", "row");
  row.append(
    button(setAsideLabel(state.pending.seconds), setChatAsideAndDraw, {
      title: "Step the everyday chat aside, draw the picture, and put the chat back",
      isLive: true,
      fkey: "pictures-set-aside",
    }),
    button(WORDS.set_aside_no, cancelPending, {
      title: "Leave the everyday chat where it is; nothing is drawn",
      fkey: "pictures-set-aside-no",
    }),
  );
  block.append(row);
  return block;
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
  // one thing it cannot know - a drawing is already running. `busy` is set as
  // well as `disabled`, because a link change repaints every live control and
  // syncLive would otherwise hand the button back mid-draw.
  if (state.making) {
    make.dataset.busy = "true";
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
  // The PC's own "may I set the chat aside?" question, above the gallery. It
  // is only ever drawn from a 409, and it holds no retry of its own: the
  // confirm button is the only thing that sends one.
  if (d.enabled && state.pending) card.append(pendingBlock());
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
