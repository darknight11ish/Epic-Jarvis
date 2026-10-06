/**
 * Settings -> "Set up Jarvis": the handful of choices that actually matter on
 * the first run, in one card, in the order a person would make them.
 *
 * The owner's approved option 8A (2026-10-06): "a first-run setup page: the
 * important settings in one place, in plain words, each raising its card
 * where the rule requires."
 *
 * WHAT THIS FILE DOES NOT DO
 *
 * It invents no setting and writes none by hand. Every control calls a Rust
 * command that already existed, and all five choices already live elsewhere in
 * this same window:
 *
 *   which card runs your everyday chat -> get_second_card / set_chat_card
 *     (the same pair the "Everyday chat runs on" radios use; pinning raises
 *     the chat_card_pin card and is held while the event stream is stale)
 *   start Jarvis for you              -> supervisor_status / set_supervision
 *     (the same pair the "Starting Jarvis for you" switch uses)
 *   let your phone reach this PC      -> get_api_settings / set_api_settings
 *     (the same pair the Connection card's save button uses)
 *   read aloud                        -> get_voice_status / set_voice_setting
 *     ("memory" -> memory_aloud; `voice_training.rs` raises the voice card)
 *   where to find help                -> the existing cards, by navigation
 *     only (the jump list's own behaviour, from a button - no command)
 *
 * THE ONE THING IT DOES NOT OFFER, AND SAYS SO
 *
 * "Which model Jarvis uses" has no setting on the desktop at all: the model
 * list lives in the Brain window's Model view (`brain_model`, brain.rs), and
 * the everyday model is `jarvis-primary` from the backend's own Modelfile.
 * Rather than build a second model picker here - which is the thing the
 * owner's brief forbids - the card's first row says where the model is chosen,
 * and offers the one model-shaped setting Settings really has: which graphics
 * card runs it.
 *
 * So a setting is never written directly: `set_chat_card` and
 * `set_voice_setting` call the backend, which raises the card, and
 * `set_supervision`/`set_api_settings` are the two privileged commands this
 * window already holds. Rule 4 - the app never auto-approves anything - holds
 * here exactly as it does on the cards' own pages.
 *
 * WHY A CARD AND NOT A WINDOW
 *
 * `onboarding.html` already exists: five static screens that TEACH what
 * Jarvis is, with no controls. `docs/CUTTING-EDGE-2026-09-26-round2-experience.md`
 * section 5 designed a first-run CHECKLIST with "Fix" buttons and did not
 * build it. This card is that idea, cut down to the five things the owner
 * chose, and it lives in the settings window because that is where all five
 * settings already live and where the ACL already grants them - so no second
 * page, no second window and no new Tauri command.
 *
 * HOW "SEEN" IS RECORDED
 *
 * `commands.rs`'s ONBOARDING_VERSION is the pattern this follows: a version
 * number, so a later, better card can be shown once more to someone who
 * already closed this one - never a plain yes/no (the old `onboarding_seen`
 * boolean could not tell an old walkthrough from a new one, which is exactly
 * why commands.rs replaced it). It is in localStorage because this page must
 * be able to read it in a plain browser too, and because the settings window
 * already keeps its other key there (`jarvis.settings.place`). A browser that
 * cannot store it shows the card, never hides it.
 *
 * @module first-run-settings
 */

import { currentLink, linkWords } from "./jarvis-link.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

async function invoke(command, args = {}) {
  if (!IS_TAURI) throw new Error("no desktop backend");
  return TAURI.core.invoke(command, args);
}

/**
 * The card's line at the top: what the link is doing, in the words every
 * window uses - or "" when this is not the app at all.
 *
 * The second case is a plain browser (the preview the tests and
 * `docs/ease-audit-2026-09-27/setup.md` render the pages in), where
 * `jarvis-link.js`'s state is its own untouched default and there is no Rust
 * to ask. Saying "Linked" there would be a claim about a connection that does
 * not exist, so the card goes quiet instead.
 */
function linkLine() {
  try {
    return IS_TAURI ? linkWords(currentLink()).text : "";
  } catch {
    return "";
  }
}

/**
 * Raise this by one when the card changes in a way the owner should see
 * again; everyone then meets it once more. The same idea, and the same
 * reason, as `commands.rs`'s ONBOARDING_VERSION.
 */
const SETUP_VERSION = 1;

/** Where "this card has been finished or skipped" is kept. */
const SETUP_SEEN_KEY = "jarvis.setup.seen";

/** The memory setting's two ids, from `voice-training.js`'s own MEMORY table. */
const READ_ALOUD = "memory_aloud";
const KEEP_ON_SCREEN = "memory_on_screen";

/** The words for "the card is waiting on you", shared with the other panels. */
const WAITING = "Waiting for your approval — approve it in the Jarvis bar, on the widget, or on your phone's Home screen.";

/**
 * What the read-aloud row says once the move went through. Turning it on is
 * the looser choice, so the PC raises one approval card and NOTHING has
 * changed yet - a page that said "Read aloud" there would be claiming a
 * change that has not been approved (rule 4). Turning it off is immediate.
 */
const READ_ALOUD_WAITING =
  "Waiting for your approval — approve it in the Jarvis bar, on the widget, or on your phone's Home screen. Nothing changes until you approve it.";

const READ_ALOUD_DONE = "Read aloud. If a card is waiting, nothing changes until you approve it.";
/** The row's own one-line reminder while nothing is waiting. */
const READ_ALOUD_HINT =
  "Turning this on is the looser choice, so it raises one approval card; turning it off is immediate.";

const dom = {
  section: $("first-run"),
  plain: $("fr-body-plain"),
  full: $("fr-body-full"),
  state: $("fr-state"),
  status: $("fr-status"),
  rows: $("fr-rows"),
  done: $("fr-done"),
  again: $("fr-again"),
  againLine: $("fr-again-line"),
};

/* ── A very small DOM helper, the shape every panel here uses ─────────────── */

function node(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined && text !== null) n.textContent = String(text);
  return n;
}

function button(text, onClick, { ghost = false, id } = {}) {
  const b = node("button", ghost ? "btn ghost small" : "btn small", text);
  b.type = "button";
  if (id) b.id = id;
  b.addEventListener("click", onClick);
  return b;
}

/** One row: a heading, one plain sentence, the controls, and its own status. */
function row(title, what, controls) {
  const box = node("div", "fr-row");
  box.append(node("h3", "subhead", title));
  box.append(node("p", "note", what));
  const rowEl = node("div", "fr-controls");
  for (const c of controls) rowEl.append(c);
  box.append(rowEl);
  const status = node("p", "status", "");
  status.setAttribute("role", "status");
  box.append(status);
  box._status = status;
  return box;
}

function say(box, text, tone) {
  const status = box && box._status;
  if (!status) return;
  status.textContent = text || "";
  if (tone) status.dataset.tone = tone;
  else delete status.dataset.tone;
}

/** The backend's own words, or a plain refusal - never a stack trace. */
function problemWords(error) {
  const text = String((error && error.message) || error || "").trim();
  return text || "Jarvis could not be asked about this just now.";
}

/**
 * A plain two-choice switch that says what it does in one line above it.
 * `onChange` gets the wanted boolean and must do the talking back through
 * `say(box, ...)`; nothing here decides anything by itself.
 */
function switchRow(label, detail, onChange) {
  const wrap = node("label", "toggle");
  const input = document.createElement("input");
  input.type = "checkbox";
  const text = node("span", "", label);
  if (detail) text.append(node("span", "toggle-detail", detail));
  wrap.append(input, text);
  input.addEventListener("change", () => onChange(input));
  wrap._input = input;
  return wrap;
}

/* ── Row 1: which graphics card runs your everyday chat ──────────────────── */

async function paintChatCard(box, note) {
  const status = await invoke("get_second_card");
  const chat = status && status.chat_card;
  const controls = box.querySelector(".fr-controls");
  controls.replaceChildren();
  if (!chat || typeof chat !== "object" || !Array.isArray(chat.cards)) {
    say(box, "This copy of Jarvis cannot read which card runs your everyday chat, so there is nothing to choose here yet. Update the backend with apply-patches.ps1.");
    return;
  }
  const chosen = typeof chat.chosen === "string" ? chat.chosen : "";
  const cards = chat.cards.filter((c) => c && typeof c.uuid === "string" && c.uuid);
  const list = node("div", "fr-choices");
  const add = (value, label, detail, checked) => {
    const wrap = node("label", "toggle");
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "fr-chat-card";
    input.value = value;
    input.checked = checked;
    const text = node("span", "", label);
    text.append(node("span", "toggle-detail", detail));
    wrap.append(input, text);
    input.addEventListener("change", () => chooseChatCard(box, input, value, label));
    list.append(wrap);
  };
  add("", "Let Ollama decide", "Jarvis pins nothing; Ollama picks a card by itself. Going back to this happens at once, with no card.", !chosen);
  for (const card of cards) {
    const size = card.total_mb ? ` (${Math.round(card.total_mb / 1024)} GB)` : "";
    add(card.uuid, `Always use the ${card.name}${size}`,
      `One approval card, because it changes where every answer runs. ${card.display === true ? "Your monitor is plugged into it." : "No monitor is plugged into it."}`,
      chosen === card.uuid);
  }
  controls.append(list);
  // What the PC really reads, never a guess - the backend's own sentence.
  const where = chat.where && typeof chat.where.words === "string" ? chat.where.words : "";
  const problem = typeof chat.problem === "string" ? chat.problem.trim() : "";
  const command = typeof chat.pin_command === "string" ? chat.pin_command.trim() : "";
  const lines = [where, problem, command ? `After pinning a card you must also run one PowerShell line; Settings, "Second graphics card", shows it.` : ""];
  // What the move just answered wins over the standing reading, so "waiting
  // for your approval" or a refusal is never overwritten by the re-read.
  if (note) say(box, note.text, note.tone);
  else say(box, lines.filter(Boolean).join(" "));
}

async function chooseChatCard(box, input, value, label) {
  for (const one of box.querySelectorAll("input")) one.disabled = true;
  const leaving = value === "";
  say(box, leaving ? "Going back to letting Ollama decide…" : `Asking to pin everyday chat to the ${label}…`);
  let note = null;
  try {
    const out = leaving
      ? await invoke("set_chat_card", { action: "leave" })
      : await invoke("set_chat_card", { action: "pin", card: value });
    if (out && out.pending === true) note = { text: WAITING, tone: "ok" };
    else if (out && typeof out.message === "string" && out.message) note = { text: out.message, tone: "ok" };
    else if (out && typeof out.words === "string" && out.words) note = { text: out.words, tone: "ok" };
    else note = {
      text: leaving
        ? "Jarvis leaves the card to Ollama again."
        : "Pinned. Quit Ollama and start it again for it to take effect.",
      tone: "ok",
    };
  } catch (error) {
    note = { text: problemWords(error), tone: "bad" };
  }
  await paintChatCard(box, note).catch((error) => say(box, problemWords(error), "bad"));
}

/* ── Row 2: whether Jarvis starts Jarvis for you ─────────────────────────── */

async function paintSupervise(box, note) {
  const status = await invoke("supervisor_status");
  const controls = box.querySelector(".fr-controls");
  controls.replaceChildren();
  const backend = (status && status.backend) || {};
  const sw = switchRow("Let Jarvis Desktop start and stop Jarvis",
    "With it on, opening this app starts Jarvis too. A Jarvis you started yourself is never taken over and never stopped.",
    (input) => setSupervise(box, input, status));
  sw._input.checked = Boolean(status && status.supervise);
  controls.append(sw);
  if (note) {
    say(box, note.text, note.tone);
  } else if (status && status.supervise && !status.configured) {
    say(box, "Turned on, but no program is set yet, so there is nothing to start. Set it under More options, \"Starting Jarvis for you\".");
  } else if (status && status.owned) {
    say(box, `On. Jarvis Desktop started Jarvis and it has been running for ${uptime(status.uptime_seconds)}.`, "ok");
  } else if (status && !status.supervise) {
    say(box, "Off. Jarvis Desktop will not start or stop Jarvis, so you start it yourself in PowerShell.");
  } else {
    say(box, "On. Jarvis is not running from here right now.", "ok");
  }
  // Kept for the write below: turning supervision on must not blank a program
  // the owner already set on the other card.
  box._backend = backend;
}

function uptime(seconds) {
  const s = Number(seconds || 0);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}

async function setSupervise(box, input, status) {
  const wanted = input.checked;
  input.disabled = true;
  const backend = (status && status.backend) || box._backend || {};
  say(box, wanted ? "Turning it on…" : "Turning it off…");
  let note = null;
  try {
    await invoke("set_supervision", {
      supervise: wanted,
      backend: {
        program: backend.program || "",
        args: Array.isArray(backend.args) ? backend.args : [],
        cwd: backend.cwd || null,
      },
    });
    // Nothing is started or stopped here on purpose: a preference change is
    // not the moment to take down a running process (settings.js says the
    // same on its own Save button).
    note = {
      text: wanted
        ? "Saved. Jarvis will be started for you next time this app opens."
        : "Saved. Jarvis Desktop will not start or stop Jarvis.",
      tone: "ok",
    };
  } catch (error) {
    note = { text: problemWords(error), tone: "bad" };
  }
  await paintSupervise(box, note).catch((error) => say(box, problemWords(error), "bad"));
}

/* ── Row 3: whether the phone can reach this PC ──────────────────────────── */

async function paintPhone(box, note) {
  const settings = await invoke("get_api_settings");
  const controls = box.querySelector(".fr-controls");
  controls.replaceChildren();
  const field = node("label", "field");
  field.append(node("span", "label", "This PC's address on Tailscale or NordVPN Meshnet"));
  const input = document.createElement("input");
  input.type = "text";
  input.spellcheck = false;
  input.autocomplete = "off";
  input.placeholder = "100.x.x.x";
  input.value = settings.bindAddress || "";
  input.setAttribute("aria-label", "This computer's address on your private network");
  field.append(input);
  const rowEl = node("div", "row");
  rowEl.append(button(settings.bindAddress ? "Save" : "Save and let my phone reach this", () => savePhone(box, input)));
  rowEl.append(button("Turn this off", () => clearPhone(box, input), { ghost: true }));
  controls.append(field, rowEl);
  if (note) {
    say(box, note.text, note.tone);
    return;
  }
  say(box, settings.bindAddress
    ? `On, at ${settings.bindAddress}. Only your own devices on that private network can reach Jarvis.`
    : "Off. Jarvis is reachable from this computer alone, which is the default and the safe choice.", settings.bindAddress ? "ok" : "");
}

async function savePhone(box, input) {
  const address = input.value.trim();
  if (!address) {
    say(box, "Type this computer's address on that private network first — it looks like 100.x.x.x, and the Tailscale or NordVPN app shows it.", "bad");
    return;
  }
  input.disabled = true;
  say(box, "Saving…");
  let note = null;
  try {
    // The same three fields the Connection card's save button sends. The token
    // is null, which means "keep the one already there" - this card never
    // touches it, and never shows it.
    await invoke("set_api_settings", { base: null, token: null, bindAddress: address });
    note = {
      text: "Saved. This works only while \"Let Jarvis Desktop start and stop Jarvis\" above is on — that is how the address reaches Jarvis.",
      tone: "ok",
    };
  } catch (error) {
    note = { text: problemWords(error), tone: "bad" };
  }
  await paintPhone(box, note).catch((error) => say(box, problemWords(error), "bad"));
}

async function clearPhone(box, input) {
  input.disabled = true;
  say(box, "Turning it off…");
  let note = null;
  try {
    await invoke("set_api_settings", { base: null, token: null, bindAddress: "" });
    note = { text: "Off. Jarvis is reachable from this computer alone again.", tone: "ok" };
  } catch (error) {
    note = { text: problemWords(error), tone: "bad" };
  }
  await paintPhone(box, note).catch((error) => say(box, problemWords(error), "bad"));
}

/* ── Row 4: read aloud ───────────────────────────────────────────────────── */

async function paintReadAloud(box, note) {
  const status = await invoke("get_voice_status");
  const controls = box.querySelector(".fr-controls");
  controls.replaceChildren();
  const view = readAloudView(status);
  if (!view) {
    say(box, "This PC's Jarvis does not report this setting yet, so it cannot be changed from here. Update the backend with apply-patches.ps1, or use Settings, Voice.");
    return;
  }
  controls.append(switchRow("Read remembered answers aloud",
    view.aloud
      ? "On. Answers that use what Jarvis remembers are spoken when you ask by voice. Health, money, passwords and other people's private details still stay on screen."
      : "Off. Those answers are shown, not read aloud.",
    (input) => setReadAloud(box, input, view.aloud)));
  controls.querySelector("input").checked = view.aloud;
  // What to say, in order of who knows best:
  //   the PC says a card is waiting AND the switch now reads on  -> the card
  //     is that move, still waiting: say so, never "Read aloud";
  //   otherwise the `note` from the move just made;
  //   otherwise the row's standing reminder.
  // The PC's word wins over the click, which is the whole point of asking it
  // again rather than rendering what was clicked.
  if (view.waiting && view.aloud) say(box, READ_ALOUD_WAITING);
  else if (note) say(box, note.text, note.tone);
  else say(box, READ_ALOUD_HINT);
}

/**
 * `gate.settings.memory` as `voice-training.js` reads it, read here rather
 * than imported so this module stays readable on its own. An older PC sends
 * neither the key nor the gate entry, and then there is nothing to offer.
 */
function readAloudView(status) {
  const gate = (status && status.gate) || {};
  const settings = gate.settings || {};
  const raw = settings.memory !== undefined ? settings.memory : gate.memory;
  if (raw !== READ_ALOUD && raw !== KEEP_ON_SCREEN) return null;
  const training = gate.training || {};
  const pending = training.pending === true && training.kind === "setting"
    ? training.setting || {} : null;
  return {
    aloud: raw === READ_ALOUD,
    waiting: Boolean(pending && pending.name === "memory"),
  };
}

async function setReadAloud(box, input, wasAloud) {
  const wanted = input.checked;
  input.disabled = true;
  say(box, wanted ? "Asking…" : "Changing it…");
  let note = null;
  try {
    await invoke("set_voice_setting", {
      setting: "memory",
      value: wanted ? READ_ALOUD : KEEP_ON_SCREEN,
    });
    note = { text: wanted ? READ_ALOUD_DONE : "Kept on screen. That happened at once, with no card.", tone: "ok" };
  } catch (error) {
    input.checked = wasAloud;
    note = { text: problemWords(error), tone: "bad" };
  }
  // The re-read repaints the switch and then puts this answer back, so what
  // the owner reads is what the PC said rather than the row's own reminder.
  await paintReadAloud(box, note).catch((error) => say(box, problemWords(error), "bad"));
}

/* ── Row 5: where to find help ───────────────────────────────────────────── */

function paintHelp(box) {
  const controls = box.querySelector(".fr-controls");
  const rowEl = node("div", "row");
  // Navigation only, and only inside this page: every card named here already
  // exists in this window, so this needs no command and no permission at all -
  // it is the jump list's own behaviour, from a button.
  rowEl.append(button("Read the FAQ", () => goToCard("faq")));
  rowEl.append(button("What asks first", () => goToCard("asks-first"), { ghost: true }));
  rowEl.append(button("Is Jarvis reachable?", () => goToCard("connection"), { ghost: true }));
  controls.append(rowEl);
  say(box, "The FAQ answers the commonest questions in plain words. \"What asks first\" lists every action and whether it waits for your yes.");
}

function goToCard(id) {
  const target = $(id);
  if (target) target.scrollIntoView({ block: "start" });
}

/* ── The card itself: the rows, and the skip ─────────────────────────────── */

let painting = false;

async function paint() {
  if (!dom.section || painting) return;
  painting = true;
  try {
    prepareRows();
    await Promise.all([
      safely(dom.rows.querySelector("#fr-chat")),
      safely(dom.rows.querySelector("#fr-supervise")),
      safely(dom.rows.querySelector("#fr-phone")),
      safely(dom.rows.querySelector("#fr-read-aloud")),
    ]);
    // Which of the two states is on screen, and only then the line at the top:
    // on someone who has already finished the card, the questions are hidden
    // and that line would be the only thing left of them.
    const seen = paintSeen();
    if (dom.state && !seen) {
      // The Connection card's own sentence: whether Jarvis can be asked at all
      // decides what every row below can say.
      dom.state.hidden = false;
      delete dom.state.dataset.tone;
      dom.state.textContent = linkLine() || "Reading this PC…";
    }
  } catch (error) {
    // Only `prepareRows` can throw here - every row paints through `safely`,
    // so one unreadable setting cannot take the card down.
    if (dom.state) {
      dom.state.hidden = false;
      dom.state.dataset.tone = "bad";
      dom.state.textContent = problemWords(error);
    }
  } finally {
    painting = false;
  }
}

async function safely(box) {
  if (!box || !box._paint) return;
  try {
    await box._paint(box);
  } catch (error) {
    say(box, `${problemWords(error)} This card will read it once Jarvis is running.`, "bad");
  }
}

function prepareRows() {
  if (!dom.rows || dom.rows.dataset.built === "1") return;
  const chat = row("Which graphics card runs your everyday chat",
    "Jarvis runs a model called jarvis-primary, and that is the model it uses. Which model is loaded is chosen in the Brain window, under Model — there is no model list on this page, on purpose. What you choose here is which graphics card that model runs on, and memory is the reason to care: the card with more memory holds more of the conversation before Jarvis has to forget the oldest part of it. The bigger the model, the more conversation it keeps and the slower each answer is.",
    []);
  chat.id = "fr-chat";
  chat._paint = paintChatCard;
  const supervise = row("Start Jarvis for you",
    "Off unless you turn it on. With it on, opening this app starts Jarvis too — unless Jarvis is already running, in which case this app uses that one instead of starting a second.",
    []);
  supervise.id = "fr-supervise";
  supervise._paint = paintSupervise;
  const phone = row("Let your phone reach this PC",
    "Only if you use Tailscale or NordVPN Meshnet and want your phone to talk to Jarvis too. It never opens Jarvis to the whole internet, or even to your home Wi-Fi — only to your own devices on that private network.",
    []);
  phone.id = "fr-phone";
  phone._paint = paintPhone;
  const aloud = row("Read aloud",
    "Whether answers that use what Jarvis remembers are spoken out loud when you ask by voice, or kept on screen. Health, money, passwords and other people's private details always stay on screen, whichever you pick here.",
    []);
  aloud.id = "fr-read-aloud";
  aloud._paint = paintReadAloud;
  const help = row("Where to find help",
    "Three cards in this page answer most first-day questions. Nothing opens a new window: each button just scrolls to the card.",
    []);
  help.id = "fr-help";
  paintHelp(help);
  dom.rows.replaceChildren(chat, supervise, phone, aloud, help);
  dom.rows.dataset.built = "1";
}

/**
 * The card's two states: asking, or finished (and how to get it back).
 * Returns whether it is the finished state, which is what decides the line at
 * the top of the card.
 */
function paintSeen() {
  const seen = setupSeen();
  if (dom.plain) dom.plain.hidden = seen;
  if (dom.full) dom.full.hidden = seen;
  if (dom.rows) dom.rows.hidden = seen;
  if (dom.done) dom.done.hidden = seen;
  if (dom.state) dom.state.hidden = seen;
  if (dom.again) dom.again.hidden = !seen;
  if (dom.againLine) dom.againLine.hidden = !seen;
  // Left alone when it already says something: `finish()` sets its own line
  // just before calling this, and a repaint must not wipe the answer the owner
  // is reading.
  if (dom.status && !dom.status.textContent) delete dom.status.dataset.tone;
  return seen;
}

function setupSeen() {
  try {
    const raw = localStorage.getItem(SETUP_SEEN_KEY);
    return raw !== null && Number(raw) >= SETUP_VERSION;
  } catch {
    // No localStorage (private mode, cleared site data): the card stays up,
    // which is the safe way round - it can never claim the owner has seen it.
    return false;
  }
}

function markSeen() {
  try {
    localStorage.setItem(SETUP_SEEN_KEY, String(SETUP_VERSION));
  } catch (error) {
    // A marker that cannot be written is said out loud rather than swallowed:
    // otherwise the card comes back next time and looks like it ignored the
    // press.
    if (dom.status) {
      dom.status.dataset.tone = "bad";
      dom.status.textContent = "This card could not remember that you are done, so it will open again next time. That is a browser storage problem, not a Jarvis one.";
    }
    return false;
  }
  return true;
}

function finish() {
  markSeen();
  paintSeen();
  if (dom.status && !dom.status.textContent) {
    dom.status.dataset.tone = "ok";
    dom.status.textContent = "Done. This card stays here, folded to this line, so you can open it again any time.";
  }
}

function reopen() {
  try {
    localStorage.removeItem(SETUP_SEEN_KEY);
  } catch {}
  paintSeen();
  void paint();
}

/* ── Boot ────────────────────────────────────────────────────────────────── */

export function initFirstRunSettings() {
  if (!dom.section) return;
  if (dom.done) dom.done.addEventListener("click", finish);
  if (dom.again) dom.again.addEventListener("click", reopen);
  void paint();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initFirstRunSettings, { once: true });
} else {
  initFirstRunSettings();
}
