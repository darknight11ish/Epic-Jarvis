/**
 * The Focus presets chip in the desktop command bar.
 *
 * The chip is the PC's chosen preset name, word for word. Clicking it opens
 * the list the PC sent; clicking a row only selects it. The one action -
 * "Use this preset" - calls the bridge and the backend raises its approval
 * card. Nothing applies on open, on a link reconnect or on a new reading.
 *
 * The link is jarvis-link.js's single link state: a stale link disables the
 * chip and the action, exactly like the approval buttons on the same bar.
 */
import {
  ACTION,
  CURRENT_WORDS,
  chipView,
  normaliseReading,
  pickerView,
  resultLine,
} from "./focus-presets.js";
import { applyPreset, readPresets } from "./focus-presets-bridge.js";
import { currentLink, onLink } from "./jarvis-link.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);

function el(id) {
  return document.getElementById(id);
}

const chip = el("preset-chip");
const chipLabel = el("preset-chip-label");
const picker = el("preset-picker");
const pickerTitle = el("preset-picker-title");
const pickerKicker = el("preset-picker-kicker");
const pickerHow = el("preset-picker-how");
const pickerLane = el("preset-picker-lane");
const list = el("preset-list");
const line = el("preset-picker-line");
const apply = el("preset-apply");
const applyWhy = el("preset-apply-why");
const close = el("preset-picker-close");

if (chip && picker && list && apply && line) {
  let reading = null;
  let loaded = false;
  let open = false;
  let busy = false;
  let selected = "";
  let lineWords = "";
  let lastStale = true;

  const stale = () => Boolean(currentLink().stale);

  function setLine(words) {
    lineWords = String(words || "");
    line.textContent = lineWords;
    line.hidden = !lineWords;
  }

  function renderChip() {
    const view = chipView(reading, { stale: stale(), busy });
    if (view.hidden) {
      chip.hidden = true;
      chip.disabled = true;
      return;
    }
    chip.hidden = false;
    chip.disabled = Boolean(view.disabled);
    chipLabel.textContent = view.label;
    chip.title = view.title;
    chip.setAttribute("aria-label", view.title);
    chip.dataset.stale = view.stale ? "true" : "false";
    chip.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function detailRow(detail) {
    const row = document.createElement("span");
    row.className = "preset-detail";
    const label = document.createElement("span");
    label.className = "preset-detail-label";
    label.textContent = `${detail.label}: `;
    const value = document.createElement("span");
    value.className = "preset-detail-value";
    value.textContent = detail.value;
    row.append(label, value);
    return row;
  }

  function renderItem(item) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "preset-item";
    button.dataset.id = item.id;
    button.setAttribute("role", "radio");
    button.setAttribute("aria-checked", item.selected ? "true" : "false");
    if (item.current) button.dataset.current = "true";
    button.addEventListener("click", () => {
      if (!reading || !reading.available || busy) return;
      selected = item.id;
      setLine("");
      renderPicker();
    });

    const head = document.createElement("span");
    head.className = "preset-item-head";
    const name = document.createElement("span");
    name.className = "preset-item-name";
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
      description.className = "preset-item-description";
      description.textContent = item.description;
      button.append(description);
    }
    if (item.details.length) {
      const details = document.createElement("span");
      details.className = "preset-item-details";
      for (const detail of item.details) details.append(detailRow(detail));
      button.append(details);
    }
    return button;
  }

  function renderPicker() {
    if (!open) {
      picker.hidden = true;
      return;
    }
    const view = pickerView(reading, selected, { stale: stale(), busy, line: lineWords });
    picker.hidden = false;
    if (!view.available) {
      pickerTitle.textContent = view.heading;
      pickerKicker.textContent = "";
      pickerHow.textContent = "";
      pickerLane.hidden = true;
      list.replaceChildren();
      const reason = document.createElement("p");
      reason.className = "preset-picker-reason";
      reason.textContent = view.reason;
      list.append(reason);
      apply.disabled = true;
      applyWhy.textContent = view.action.why;
      setLine(view.line);
      return;
    }
    pickerTitle.textContent = view.heading;
    pickerKicker.textContent = view.kicker;
    pickerHow.textContent = view.howTo;
    if (view.lane && view.lane.label) {
      pickerLane.textContent = view.lane.label;
      pickerLane.hidden = false;
    } else {
      pickerLane.hidden = true;
    }
    list.replaceChildren();
    for (const item of view.items) list.append(renderItem(item));
    apply.disabled = view.action.disabled;
    apply.textContent = view.action.label;
    applyWhy.textContent = view.action.why;
    setLine(view.line);
  }

  async function load() {
    const raw = await readPresets();
    reading = normaliseReading(raw);
    loaded = true;
    if (!reading.available) {
      chip.hidden = true;
      if (open) renderPicker();
      return;
    }
    if (!reading.presets.some((p) => p.id === selected)) selected = reading.chosenId;
    if (open && !reading.presets.some((p) => p.id === selected)) selected = "";
    renderChip();
    if (open) renderPicker();
  }

  function openPicker() {
    if (!reading || !reading.available || stale()) return;
    open = true;
    selected = reading.chosenId;
    lineWords = "";
    renderChip();
    renderPicker();
    picker.hidden = false;
    const first = list.querySelector(".preset-item[aria-checked='true']");
    if (first) first.focus({ preventScroll: true });
    else close.focus({ preventScroll: true });
  }

  function closePicker() {
    if (!open) return;
    open = false;
    picker.hidden = true;
    setLine("");
    renderChip();
    if (!chip.hidden) chip.focus({ preventScroll: true });
  }

  async function useThisPreset() {
    if (busy || stale() || !reading || !reading.available) return;
    const view = pickerView(reading, selected, { stale: stale(), busy });
    if (view.action.disabled) return;
    busy = true;
    setLine("Asking the PC...");
    renderChip();
    renderPicker();
    try {
      const result = await applyPreset(selected);
      setLine(resultLine(result) || "Asked the PC.");
      await load();
    } catch (error) {
      setLine(resultLine(error) || "That did not work.");
    } finally {
      busy = false;
      renderChip();
      if (open) renderPicker();
    }
  }

  chip.addEventListener("click", () => {
    if (open) closePicker();
    else openPicker();
  });
  close.addEventListener("click", closePicker);
  apply.addEventListener("click", useThisPreset);
  picker.addEventListener("click", (event) => {
    if (event.target === picker) closePicker();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && open) {
      event.preventDefault();
      event.stopPropagation();
      closePicker();
    }
  }, true);
  document.addEventListener("pointerdown", (event) => {
    if (!open) return;
    if (picker.contains(event.target) || chip.contains(event.target)) return;
    closePicker();
  });

  onLink((link) => {
    const nowStale = Boolean(link && link.stale);
    const nowConnected = Boolean(link && link.connected);
    const cameBack = lastStale && nowConnected && !nowStale;
    lastStale = nowStale;
    renderChip();
    if (open) renderPicker();
    if (cameBack || (!loaded && nowConnected && !nowStale)) load();
  });

  if (IS_TAURI) load();
}
