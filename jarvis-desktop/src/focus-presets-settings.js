/**
 * Settings -> Focus presets.
 *
 * The same PC reading, the same words and the same one action as the command
 * bar (focus-presets-bar.js); this page only has more room for the
 * explanation. It never applies anything on open: the owner must select a
 * preset, then press "Use this preset", and the PC raises its one approval
 * card. The current preset is marked, and the action is disabled on it.
 *
 * No preset name, id, model or description is written here. If the PC has not
 * shipped the contract yet, the card says so instead of showing a catalogue.
 */
import {
  CURRENT_WORDS,
  normaliseReading,
  resultLine,
  settingsView,
} from "./focus-presets.js";
import { applyPreset, readPresets } from "./focus-presets-bridge.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);

function el(id) {
  return document.getElementById(id);
}

const card = el("focus-presets");
const heading = el("focus-presets-title");
const kicker = el("focus-presets-kicker");
const how = el("focus-presets-how");
const oneCard = el("focus-presets-one-card");
const note = el("focus-presets-note");
const lane = el("focus-presets-lane");
const list = el("focus-presets-list");
const apply = el("focus-presets-apply");
const applyWhy = el("focus-presets-apply-why");
const line = el("focus-presets-line");

if (card && list && apply && line) {
  let reading = null;
  let selected = "";
  let busy = false;
  let lineWords = "";

  function setLine(words) {
    lineWords = String(words || "");
    line.textContent = lineWords;
    line.hidden = !lineWords;
    line.dataset.tone = /did not|refus|stale|could not|no |not /i.test(lineWords) ? "bad" : "";
  }

  function detailNode(detail) {
    const span = document.createElement("span");
    span.className = "preset-settings-detail";
    const label = document.createElement("span");
    label.className = "preset-settings-detail-label";
    label.textContent = `${detail.label}: `;
    const value = document.createElement("span");
    value.textContent = detail.value;
    span.append(label, value);
    return span;
  }

  function itemNode(item) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "preset-settings-item";
    button.dataset.id = item.id;
    button.setAttribute("role", "radio");
    button.setAttribute("aria-checked", item.selected ? "true" : "false");
    button.addEventListener("click", () => {
      if (busy || !reading || !reading.available) return;
      selected = item.id;
      setLine("");
      render();
    });

    const head = document.createElement("span");
    head.className = "preset-settings-item-head";
    const name = document.createElement("span");
    name.className = "preset-settings-item-name";
    name.textContent = item.name;
    head.append(name);
    if (item.current) {
      const current = document.createElement("span");
      current.className = "preset-current";
      current.textContent = CURRENT_WORDS;
      head.append(current);
    }
    if (!item.ready) {
      const state = document.createElement("span");
      state.className = "preset-state";
      state.textContent = item.statusWords;
      head.append(state);
    }
    button.append(head);

    if (item.description) {
      const description = document.createElement("span");
      description.className = "preset-settings-description";
      description.textContent = item.description;
      button.append(description);
    }
    if (item.details.length) {
      const details = document.createElement("span");
      details.className = "preset-settings-details";
      for (const detail of item.details) details.append(detailNode(detail));
      button.append(details);
    }
    return button;
  }

  function render() {
    if (!reading) {
      heading.textContent = "Focus presets";
      kicker.textContent = "Reading the PC's presets...";
      list.replaceChildren();
      apply.disabled = true;
      return;
    }
    const view = settingsView(reading, selected, { busy, line: lineWords });
    heading.textContent = view.heading;
    kicker.textContent = view.kicker;
    how.textContent = view.howTo;
    oneCard.textContent = view.oneCard;
    if (view.note) {
      note.textContent = view.note;
      note.hidden = false;
    } else {
      note.hidden = true;
    }
    if (view.available) {
      if (view.lane && view.lane.label) {
        lane.textContent = view.lane.label;
        lane.hidden = false;
      } else {
        lane.hidden = true;
      }
      list.replaceChildren();
      for (const item of view.items) list.append(itemNode(item));
      apply.disabled = view.action.disabled;
      apply.textContent = view.action.label;
      applyWhy.textContent = view.action.why;
    } else {
      lane.hidden = true;
      list.replaceChildren();
      const reason = document.createElement("p");
      reason.className = "note";
      reason.textContent = view.reason;
      list.append(reason);
      apply.disabled = true;
      applyWhy.textContent = view.action.why;
    }
    setLine(view.line);
  }

  async function load() {
    const raw = await readPresets();
    reading = normaliseReading(raw);
    if (reading.available) {
      if (!reading.presets.some((p) => p.id === selected)) selected = reading.chosenId;
    } else {
      selected = "";
    }
    render();
  }

  async function useThisPreset() {
    if (busy || !reading || !reading.available) return;
    const view = settingsView(reading, selected, { busy });
    if (view.action.disabled) return;
    busy = true;
    setLine("Asking the PC...");
    render();
    try {
      const result = await applyPreset(selected);
      setLine(resultLine(result) || "Asked the PC.");
      await load();
    } catch (error) {
      setLine(resultLine(error) || "That did not work.");
    } finally {
      busy = false;
      render();
    }
  }

  apply.addEventListener("click", useThisPreset);
  if (IS_TAURI) load();
  else {
    reading = normaliseReading(
      "This desktop build has no preset bridge yet. Update the app and the backend.",
    );
    render();
  }
}
