/**
 * Settings -> Learning (2026-10-28, the settings audit's G1).
 *
 * THE GAP THIS CLOSES. `background_learning` and `learn_sensitive_topics` are
 * real switches with a real route, a real spoken name and a real approval
 * card, and until now their ONLY control was Brain -> Memory -> Learning:
 * `SETTINGS_GAPS` recorded that no Settings row existed on either app, so the
 * feature list called them "Switchable" while the Settings menu could not
 * show them. This is that card's module.
 *
 * THE ONE PATH, THREE TIMES. Each control calls the SAME Rust command the
 * Brain's own switch calls - `brain_memory_learning` (POST
 * /api/memory/learning), `brain_memory_learning_sensitive` (POST
 * /api/memory/learning/sensitive), and `brain_memory_learning_status` (GET
 * /api/memory/learning) for the state - so this card, "turn on background
 * learning" and the phone's switch are one write path, one card, one rule.
 * Nothing here approves anything: ON raises the PC's ONE `learning_enable` /
 * `learning_sensitive_enable` card and changes nothing until a person answers
 * it; OFF is immediate and never held (rule 4 holds only what loosens).
 *
 * WHAT EACH ROW SHOWS. The switch position, and under it the row's own words -
 * plus the PC's own sentence when there is one (a waiting card, a damaged
 * settings file). While a card waits the switch is drawn ON so it can be taken
 * back - the same shape the data sandbox's card uses; the line under it says
 * "waiting", never that the switch is on.
 *
 * WHAT THIS CARD DOES NOT SHOW. No fact, no list, no count: the saved facts
 * and the "Learn automatically" switch live in the Brain, where the fact list
 * is (`auto-learn.js`, `brain.html`), and this page's module does not hold the
 * command that reads them. The card's own note says where they are.
 *
 * THE WORDS ARE THE BRAIN'S, word for word where the two surfaces show the
 * same switch (jarvis-desktop/src/auto-learn.js's SENSITIVE_LABEL/DETAIL and
 * brain.js's background-learning line); the settings page's other cards keep
 * their own copies the same way.
 *
 * @module learning-settings
 */

import {
  APPROVE_WHERE,
  currentLink,
  currentQueue,
  linkWords,
  onLink,
  onQueue,
} from "./jarvis-link.js";
import { call } from "./invoke-budget.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

const el = {
  state: $("learning-state"),
  body: $("learning-body"),
  background: $("learning-background"),
  backgroundLine: $("learning-background-line"),
  backgroundWaiting: $("learning-background-waiting"),
  sensitive: $("learning-sensitive"),
  sensitiveLine: $("learning-sensitive-line"),
  sensitiveWaiting: $("learning-sensitive-waiting"),
  said: $("learning-status"),
};

const ASKING = "Asking the PC…";
const WAITING_CARD =
  `Waiting for your approval card ${APPROVE_WHERE} - the switch stays off ` +
  "until it is approved.";
const WAITING_LINK =
  "The connection is catching up. Turning learning on asks for your approval, " +
  "so it waits for a live connection; turning it off works at once.";
const MISSING = "Your PC's Jarvis does not have automatic learning yet.";
const BACKGROUND_ON =
  "On. Jarvis reads your conversations for facts, and \"Learn automatically\" " +
  "(in the Brain) says whether it saves them without asking.";
const BACKGROUND_OFF =
  "Off. Nothing new is proposed, though a message that starts \"Remember:\" " +
  "still makes a card.";
const SENSITIVE_ON =
  "On. Health, money and private details about other people may be saved " +
  "without a card. Passwords, PINs, account and ID numbers, birthdays, phone " +
  "numbers and email addresses still wait for your yes.";
const SENSITIVE_OFF =
  "Off. Jarvis asks you first about health, money and private details about " +
  "other people.";
const SENSITIVE_NEEDS_BACKGROUND =
  "Background learning is off, so nothing is saved automatically. Turn " +
  "background learning on above to use this.";

/** The card the background switch's ON raises (jarvis_learning_switch.py). */
const BACKGROUND_ACTION = "learning_enable";

let view = null;
let busy = false;
let asked = false;          // false | "background" | "sensitive"
let sawSensitive = false;      // our own ON is waiting on a card
let sawCard = false;    // ...and the queue has shown that card since we asked
let poll = null;

function live() {
  return linkWords(currentLink()).canAct;
}

/** Is the background switch's ON card in the approval queue anywhere? */
function backgroundCardWaiting() {
  const items = (currentQueue() && currentQueue().items) || [];
  return items.some((item) => item && item.action === BACKGROUND_ACTION);
}

function say(text, tone) {
  if (!el.said) return;
  el.said.textContent = text;
  if (tone) el.said.dataset.tone = tone;
  else delete el.said.dataset.tone;
}

function paint() {
  if (!el.body) return;
  el.state.hidden = true;
  el.body.hidden = false;
  if (!view) {
    if (el.background) el.background.disabled = true;
    if (el.sensitive) el.sensitive.disabled = true;
    return;
  }
  const queued = backgroundCardWaiting();
  // The card appeared at least once, so its disappearance later means it was
  // answered (or expired) - not that it has not been raised yet.
  if (queued) sawCard = true;
  const backgroundWaiting = asked === "background" || queued;
  if (view.sensitive_waiting === true) sawSensitive = true;
  const sensitiveWaiting = view.sensitive_waiting === true || asked === "sensitive";
  // A waiting card is drawn ON so it can be taken back; the line under it says
  // it is only waiting, never that the switch is on.
  const backgroundOn = view.enabled === true || backgroundWaiting;
  const sensitiveOn = view.sensitive === true || sensitiveWaiting;
  // Turning either ON raises a card, so it needs a live link; OFF never waits.
  const held = !live();
  if (el.background) {
    el.background.disabled = busy || (held && !backgroundOn);
    el.background.checked = backgroundOn;
  }
  if (el.sensitive) {
    el.sensitive.disabled = busy || (held && !sensitiveOn) ||
      (view.enabled === false && !sensitiveOn);
    el.sensitive.checked = sensitiveOn;
  }
  if (el.backgroundLine) {
    el.backgroundLine.textContent = view.enabled === true
      ? (backgroundWaiting ? "" : BACKGROUND_ON)
      : BACKGROUND_OFF;
  }
  if (el.backgroundWaiting) {
    el.backgroundWaiting.textContent =
      backgroundWaiting ? WAITING_CARD : (held ? WAITING_LINK : "");
    el.backgroundWaiting.hidden = !el.backgroundWaiting.textContent;
  }
  if (el.sensitiveLine) {
    el.sensitiveLine.textContent = view.enabled === false
      ? SENSITIVE_NEEDS_BACKGROUND
      : (view.sensitive === true ? SENSITIVE_ON : SENSITIVE_OFF);
  }
  if (el.sensitiveWaiting) {
    el.sensitiveWaiting.textContent = sensitiveWaiting ? WAITING_CARD : "";
    el.sensitiveWaiting.hidden = !sensitiveWaiting;
  }
}

/** Read the PC's answer and paint it. True when the card can be drawn. */
async function read() {
  try {
    const raw = await call("brain_memory_learning_status", {}, "read");
    if (!raw || raw.available === false) {
      view = null;
      el.body.hidden = true;
      el.state.hidden = false;
      el.state.textContent = MISSING;
      return false;
    }
    view = {
      enabled: raw.enabled === true,
      sensitive: raw.auto_sensitive === true,
      sensitive_waiting: raw.sensitive_waiting === true,
      why: typeof raw.why === "string" ? raw.why.trim() : "",
    };
    // Our own ON: stop saying "waiting" once the switch is on, or once the
    // card we saw in the queue has left it (approved, denied or expired). The
    // read that follows says which of those really happened.
    if (asked === "background" &&
        (view.enabled || (sawCard && !backgroundCardWaiting()))) {
      asked = false;
      sawCard = false;
    }
    if (asked === "sensitive" &&
        (view.sensitive === true || (sawSensitive && !view.sensitive_waiting))) {
      asked = false;
      sawSensitive = false;
    }
    paint();
    // A damaged settings file is the PC's own sentence, shown as a warning.
    if (view.why) say(view.why, "warn");
    return true;
  } catch (error) {
    // Never show a switch as off when the PC could not be asked: that would
    // be a claim about a value this page did not read.
    view = null;
    el.body.hidden = true;
    el.state.hidden = false;
    el.state.textContent = String((error && error.message) || error ||
      "The PC could not be asked about learning.");
    return false;
  }
}

/** Read once, then keep reading while a card is waiting (bounded). */
async function load() {
  if (!el.body || !IS_TAURI) return;
  await read();
  watchWhileWaiting();
}

function watchWhileWaiting() {
  const waiting = asked || (view && view.sensitive_waiting) ||
    backgroundCardWaiting();
  if (!waiting) {
    if (poll) {
      clearInterval(poll);
      poll = null;
    }
    return;
  }
  if (poll) return;
  let tries = 0;
  poll = setInterval(async () => {
    tries += 1;
    await read();
    const still = asked || (view && view.sensitive_waiting) ||
      backgroundCardWaiting();
    if (tries >= 20 || !still) {
      clearInterval(poll);
      poll = null;
    }
  }, 3000);
}

async function setSwitch(which, on) {
  if (busy) return;
  busy = true;
  say(ASKING);
  asked = on ? which : false;
  paint();
  try {
    const command = which === "background"
      ? "brain_memory_learning"
      : "brain_memory_learning_sensitive";
    const out = await call(command, { enabled: on }, "action");
    if (out && out.waiting) {
      say((out && out.message) || WAITING_CARD, "warn");
    } else {
      asked = false;
      const said = out && typeof out.message === "string" ? out.message : "";
      say(said || (on ? "Changed." : "Off."), "ok");
    }
  } catch (error) {
    asked = false;
    say(String((error && error.message) || error), "warn");
  } finally {
    busy = false;
  }
  await load();
}

if (el.body) {
  el.state.hidden = false;
  el.background.addEventListener("change", (event) =>
    setSwitch("background", event.target.checked));
  el.sensitive.addEventListener("change", (event) =>
    setSwitch("sensitive", event.target.checked));
  onLink(() => paint());
  onQueue(() => paint());
  load();
}
