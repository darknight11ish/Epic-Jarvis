/**
 * Settings -> Appearance -> "Sun, moon and weather" (the owner's decisions of
 * 2026-09-28: "Sun and moon behind the animals" and "Weather in the animals'
 * scene" - both off by default; JARVIS-API.md section 59).
 *
 * Two Rust commands (src-tauri/src/sky.rs), Settings only:
 *  - get_sky: the settings and the weather now, with the PC's own words;
 *  - set_sky {change}: ONE change - show the sun and moon (at once, either
 *    way), the town (typed here, on the PC, only - found in a list the PC
 *    carries, never online), forget the town (at once), the weather source
 *    (off and "My Home Assistant" at once; "Open-Meteo (online)" raises ONE
 *    approval card, since it sends the rough position to the internet).
 *    Adding something is held on a stale link, here (greyed) and in Rust.
 *
 * Every answer is also kept for the face pages (sky-feed.js storeSky), so a
 * change shows on every face at once. The phone's Appearance -> "Sun, moon
 * and weather" (SkyPlate.kt) shows the same, in the same words (the PC's).
 *
 * @module sky-settings
 */

import { announce, currentLink, linkWords, onEvent, onLink } from "./jarvis-link.js";
import { startSkyFeed, storeSky } from "./sky-feed.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

async function invoke(command, args = {}) {
  if (!IS_TAURI) throw new Error("no desktop backend");
  return TAURI.core.invoke(command, args);
}

/** What an older PC is told. The same words as sky.rs SKY_MISSING. */
export const MISSING = "Your PC's Jarvis cannot show the sun, moon or weather yet - run "
  + "apply-patches.ps1 on the PC.";
const STALE = "Waiting for the link to catch up. Nothing can be sent until it does.";

const el = {
  box: $("sky"),
  state: $("sky-state"),
  body: $("sky-body"),
  title: $("sky-title"),
  show: $("sky-show"),
  showLabel: $("sky-show-label"),
  showDetail: $("sky-show-detail"),
  placeLabel: $("sky-place-label"),
  place: $("sky-place"),
  placeSet: $("sky-place-set"),
  placeForget: $("sky-place-forget"),
  placeDetail: $("sky-place-detail"),
  placeNow: $("sky-place-now"),
  today: $("sky-today"),
  weatherLabel: $("sky-weather-label"),
  weatherDetail: $("sky-weather-detail"),
  choices: $("sky-weather-choices"),
  weatherStatus: $("sky-weather-status"),
  status: $("sky-status"),
};

let view = null;
let busy = false;

function node(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

function say(target, text, tone) {
  if (!target) return;
  target.textContent = text || "";
  if (tone) target.dataset.tone = tone;
  else delete target.dataset.tone;
}

/** An error in words, never a bridge error or JSON. */
function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 600) {
    return "Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

const clock = (ms) => new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

/** "Sun rises 06:41, sets 19:02. Moon: ..." - sky.js todayWords, in this
 *  computer's clock. Empty without a town. */
export function todayLine(place, nowMs) {
  const S = globalThis.JarvisSky;
  if (!place || !S) return "";
  return S.todayWords(S.summary(nowMs, place.lat, place.lon), clock);
}

function syncButtons() {
  if (!el.box) return;
  const live = linkWords(currentLink()).canAct;
  // Adding something waits for the link; taking something away never does.
  for (const b of el.box.querySelectorAll("[data-adds]")) {
    const adds = b.dataset.adds === "true";
    b.disabled = busy || (adds && !live);
    b.title = adds && !live ? STALE : "";
  }
}

function paint() {
  if (!el.box || !view) return;
  if (view.available === false) {
    say(el.state, view.why || MISSING);
    el.body.hidden = true;
    return;
  }
  say(el.state, "");
  el.body.hidden = false;
  if (el.title && view.title) el.title.textContent = view.title;
  el.show.checked = view.show === true;
  el.show.dataset.adds = String(!view.show);
  say(el.showLabel, view.show_label);
  say(el.showDetail, view.show_detail);
  say(el.placeLabel, view.place_label);
  say(el.placeDetail, view.place_detail);
  const place = view.place;
  say(el.placeNow, place ? `Now: ${place.name} (${place.lat.toFixed(1)}, ${place.lon.toFixed(1)}).`
    : view.place_none);
  el.placeForget.hidden = !place;
  el.placeForget.textContent = view.forget_label || "Forget my town";
  el.placeForget.dataset.adds = "false";
  el.placeSet.dataset.adds = "true";
  el.place.disabled = view.can_set_place === false;
  el.placeSet.hidden = view.can_set_place === false;
  say(el.today, todayLine(place, Date.now()));

  const w = view.weather || {};
  say(el.weatherLabel, w.label);
  say(el.weatherDetail, w.detail);
  el.choices.replaceChildren();
  for (const c of w.choices || []) {
    const row = node("label", "theme-row");
    row.dataset.choice = c.id;
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "sky-weather";
    radio.value = c.id;
    radio.checked = c.id === w.source;
    radio.dataset.adds = String(c.id !== "off");
    radio.addEventListener("change", () => {
      if (radio.checked) change({ weather: c.id });
    });
    const text = node("span", "theme-text");
    text.append(node("span", "theme-name", c.label), node("span", "theme-blurb", c.why));
    const tick = node("span", "theme-check", "✓");
    tick.setAttribute("aria-hidden", "true");
    row.append(radio, text, tick);
    el.choices.append(row);
  }
  const lines = [w.status];
  if (w.last && w.last.message && !w.waiting) lines.push(w.last.message);
  say(el.weatherStatus, lines.filter(Boolean).join(" "));
  syncButtons();
}

async function load() {
  if (!el.box || !IS_TAURI) return;
  try {
    view = await invoke("get_sky");
    if (!view || typeof view !== "object") view = { available: false, why: MISSING };
  } catch (error) {
    say(el.state, `Could not read it: ${problemWords(error)}`, "bad");
    return;
  }
  storeSky(view);
  paint();
}

async function change(one) {
  if (busy) return;
  busy = true;
  syncButtons();
  say(el.status, "Sending…");
  try {
    const out = await invoke("set_sky", { change: one });
    const said = String((out && (out.said || out.error)) || "Done.");
    say(el.status, said, out && out.ok === false ? "bad" : "ok");
    announce(said);
    if (out && out.view) {
      view = out.view;
      storeSky(view);
    }
  } catch (error) {
    say(el.status, problemWords(error), "bad");
    announce(el.status.textContent, "assertive");
  } finally {
    busy = false;
  }
  await load();
}

if (el.box) {
  el.show.addEventListener("change", () => change({ show: el.show.checked }));
  el.placeSet.addEventListener("click", () => {
    const text = el.place.value.trim();
    if (text) change({ place: text });
  });
  el.place.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      el.placeSet.click();
    }
  });
  el.placeForget.addEventListener("click", () => change({ forget_place: true }));
  onLink(() => syncButtons());
  load();
  // While Settings is open it keeps the faces' copy fresh too, and re-reads
  // when it comes back into view (a card answered on the phone, say).
  startSkyFeed({ invoke });
  // The PC's `sky` doorbell (a change on the phone, or asked of Jarvis):
  // this section shows it at once.
  onEvent((frame) => { if (frame && frame.kind === "sky" && !busy) load(); });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) load();
  });
  // The rise and set line moves with the day.
  setInterval(() => { if (view && view.place) say(el.today, todayLine(view.place, Date.now())); }, 60000);
}
