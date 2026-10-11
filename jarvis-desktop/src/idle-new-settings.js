/**
 * Settings -> "A new conversation starts after": the one timing the audit of
 * 2026-10-08 found the owner could not change anywhere.
 *
 * It is a CLIENT-SIDE choice, and this window is a client. The PC serves no
 * route for it - `backend/jarvis_limits.py` says so in its own words ("the
 * 'new conversation after 30 quiet minutes' window is CLIENT-SIDE ... nothing
 * in the backend reads or serves it, so a key here could not change it") - so
 * there is no Rust command, no HTTP request, no approval card and no
 * stale-link hold here. The choice is written to localStorage
 * (chat-history.js's `saveIdleNewChoice`) and read straight back by the
 * Jarvis bar when it decides whether a question starts a new conversation.
 * Nothing about it ever leaves this PC; the phone keeps its own choice of the
 * same five (ChatHistory.kt).
 *
 * The five choices and their words are chat-history.js's own
 * (`IDLE_NEW_CHOICES`, `IDLE_NEW_DETAIL`, `IDLE_NEW_TAIL`), so this file holds
 * only the page: the same `theme-row` radios the "How Jarvis talks" card uses,
 * one row per choice, the chosen one ticked.
 *
 * 30 minutes is the DEFAULT and stays the default: `storedIdleNewChoice()`
 * reads a missing, empty or unknown stored value as 30 minutes, never as
 * "Never".
 *
 * @module idle-new-settings
 */

import { announce } from "./jarvis-link.js";
import {
  IDLE_NEW_CHOICES,
  IDLE_NEW_DETAIL,
  IDLE_NEW_TAIL,
  IDLE_NEW_TITLE,
  saveIdleNewChoice,
  storedIdleNewChoice,
} from "./chat-history.js";

const $ = (id) => document.getElementById(id);

const el = {
  section: $("idle-new"),
  heading: $("in-heading"),
  detail: $("in-detail"),
  choices: $("in-choices"),
  tail: $("in-tail"),
  status: $("in-status"),
};

function node(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

/** The words for the choice just saved - the row's own wait, and what "Never"
 *  really means (a conversation then ends only when the owner starts one). */
export function chosenWords(choice) {
  if (!choice || choice.id === "never") {
    return "A new conversation now starts only when you start one. The last chat is in History.";
  }
  return `A new conversation now starts after ${choice.wait}. The last chat is in History.`;
}

function choose(id) {
  const saved = saveIdleNewChoice(id);
  const choice = IDLE_NEW_CHOICES.find((c) => c.id === saved) || IDLE_NEW_CHOICES[0];
  const said = chosenWords(choice);
  if (el.status) {
    el.status.textContent = said;
    el.status.dataset.tone = "ok";
  }
  announce(said);
  paint();
}

function paint() {
  if (!el.section) return;
  if (el.heading) el.heading.textContent = IDLE_NEW_TITLE;
  el.detail.textContent = IDLE_NEW_DETAIL;
  el.tail.textContent = IDLE_NEW_TAIL;
  const chosen = storedIdleNewChoice();
  el.choices.replaceChildren(...IDLE_NEW_CHOICES.map((c) => {
    const row = node("label", "theme-row");
    row.dataset.choice = c.id;
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "in-idle-new";
    radio.value = c.id;
    radio.checked = c.id === chosen;
    radio.addEventListener("change", () => {
      if (radio.checked) choose(c.id);
    });
    const text = node("span", "theme-text");
    text.append(node("span", "theme-name", c.label), node("span", "theme-blurb", c.why));
    const tick = node("span", "theme-check", "✓");
    tick.setAttribute("aria-hidden", "true");
    row.append(radio, text, tick);
    return row;
  }));
}

if (el.section) {
  paint();
  // The choice is read again whenever this window is looked at again, so a
  // change made by a spoken sentence or by another window is not missed.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) paint();
  });
}
