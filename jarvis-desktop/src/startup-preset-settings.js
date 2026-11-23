/**
 * Settings -> Startup preset (2026-11-22).
 *
 * THE OWNER'S ASK. The backend lane landed `startup-preset.json` and
 * `POST /api/work/startup-preset` (see `changelog.d/2026-11-22-startup-preset.md`),
 * and until this card the only way to set it was asking in chat. This is the
 * same setting, from the app: one select, one Save, one row.
 *
 * THE SAME SHAPE AS EVERY NEIGHBOUR. The reading comes through the desktop
 * bridge command that already reads `GET /api/work` (`get_focus_presets` in
 * `src-tauri/src/focus_presets.rs`, granted to this window by surfaces.toml's
 * `focus-presets` set), so this card knows no preset id or name of its own. The
 * ONE write is the narrow `set_startup_preset` command, granted by the
 * `startup-preset` set: it posts one preset id to `/api/work/startup-preset`
 * and nothing else, so this page cannot reach any other route and no page gets a
 * general "post anything" door.
 *
 * WHAT IT SAYS PLAINLY. Setting a preset is a standing change to what the PC does
 * on its own every time it starts, so the PC raises its ONE `change_own_config`
 * card and nothing is written before the yes; this card says so before the press
 * and repeats the PC's own sentence after it. Clearing ("No preset") is a
 * tightening and takes effect at once. The command is held on a stale link, like
 * every other write (rule 4).
 *
 * ONE HONEST LIMIT. A chat sentence ("load the General preset when you start")
 * writes the same setting. There is no event kind for it, so this row re-reads
 * when the card is opened and when a stale link comes back - not live while the
 * owner looks at it. The note under the row says that in plain words rather than
 * pretending the number is always fresh (`SAVED_ELSEWHERE`).
 *
 * @module startup-preset-settings
 */

import { APPROVE_WHERE, currentLink, onLink } from "./jarvis-link.js";
import { APPLY_BUDGET_MS, call } from "./invoke-budget.js";
import { readPresets } from "./focus-presets-bridge.js";
import {
  NO_PRESET,
  SAVED_ELSEWHERE,
  cardWords,
  currentWords,
  readStartupPreset,
  resultWords,
  saveArgs,
  savingWords,
  STALE,
} from "./startup-preset.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

const card = $("startup-preset");
const rule = $("sp-preset-card-note");
const now = $("sp-preset-current");
const why = $("sp-preset-why");
const choice = $("sp-preset-choice");
const save = $("sp-preset-save");
const said = $("sp-preset-line");

if (card && rule && now && why && choice && save && said) {
  let view = null;
  let read = false;
  let busy = false;
  let listKey = "";
  let lineWords = "";

  function stale() {
    try {
      const link = currentLink();
      return Boolean(link && link.stale);
    } catch {
      return false;
    }
  }

  function say(text, tone) {
    lineWords = String(text || "");
    said.textContent = lineWords;
    said.hidden = !lineWords;
    if (tone) said.dataset.tone = tone;
    else delete said.dataset.tone;
  }

  /** Rebuild the options ONLY when the PC's own list changed, so a re-read never
   *  undoes the choice the owner is about to save. */
  function renderChoices() {
    const list = view && view.available ? view.presets : [];
    const key = list.map((preset) => `${preset.id}\t${preset.name}`).join("\n");
    if (key === listKey) return;
    listKey = key;
    if (!list.length) {
      choice.replaceChildren();
      return;
    }
    const first = document.createElement("option");
    first.value = "";
    first.textContent = NO_PRESET;
    const nodes = [first];
    for (const preset of list) {
      const option = document.createElement("option");
      option.value = preset.id;
      option.textContent = preset.name;
      nodes.push(option);
    }
    choice.replaceChildren(...nodes);
  }

  function paint() {
    rule.textContent = cardWords(APPROVE_WHERE);
    const usable = Boolean(view && view.available);
    const held = stale();
    choice.disabled = !usable || busy;
    save.disabled = !usable || busy || held || choice.value === (view ? view.saved : "");
    now.textContent = read
      ? currentWords(view)
      : "Reading the PC's setting…";
    const note = view && view.available
      ? [view.note, SAVED_ELSEWHERE].filter(Boolean).join(" ")
      : "";
    why.textContent = note;
    why.hidden = !note;
    // A stale link is why Save is greyed out; say that, but never on top of a
    // result the PC has just given ("Saved." or the card's own words).
    if (held && !lineWords) say(STALE, "warn");
    else if (!held && lineWords === STALE) say("");
  }

  async function load() {
    const raw = await readPresets();
    view = readStartupPreset(raw);
    read = true;
    renderChoices();
    choice.value = view.available ? view.current : "";
    paint();
  }

  async function saveChoice() {
    if (busy || !view || !view.available || stale()) return;
    const id = choice.value;
    if (id === view.saved) return;
    busy = true;
    say(savingWords(id, APPROVE_WHERE), "");
    paint();
    try {
      // The PC's own answer, unchanged: a carded success, a Denied card and a
      // 400/409 refusal all arrive as JSON the PC wrote, and `resultWords` only
      // supplies the fallback when it said nothing.
      const out = await call("set_startup_preset", saveArgs(id), "action", APPLY_BUDGET_MS);
      say(resultWords(out) || "Done.", out && out.ok === false ? "warn" : "ok");
    } catch (error) {
      say(String((error && error.message) || error) || "That did not work.", "warn");
    } finally {
      busy = false;
    }
    await load();
  }

  choice.addEventListener("change", () => {
    // A fresh choice makes an old result line misleading.
    if (lineWords && lineWords !== STALE) say("");
    paint();
  });
  save.addEventListener("click", saveChoice);

  let wasStale = stale();
  onLink(() => {
    const held = stale();
    // A stale->live change is the one point where a setting written elsewhere
    // (a chat sentence, the PC's own file) can be picked up again cheaply.
    if (wasStale && !held) load();
    wasStale = held;
    paint();
  });

  if (IS_TAURI) load();
  else {
    read = true;
    view = {
      available: false,
      why:
        "This desktop build has no preset bridge yet. Update the app and the " +
        "backend, then open this again.",
      presets: [],
      saved: "",
      current: "",
      currentName: "",
      unknownCurrent: "",
      note: "",
    };
    renderChoices();
    paint();
  }
}
