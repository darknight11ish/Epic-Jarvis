/**
 * Settings -> "Devices" (docs/PAIRING-DESIGN.md, phase 1, section 7.1):
 * pairing a phone by QR code, with a key per device.
 *
 * Seven Rust commands (src-tauri/src/devices.rs), Settings only:
 *  - pair_phone_address: the name to put in the QR code - remembered, else
 *    this PC's Tailscale name, else typed once here.
 *  - pair_start({address}): the QR code as a PICTURE (drawn in Rust - this
 *    page never holds the text inside it), the typed backup code, the
 *    countdown. Rust hides this window from screen capture before it
 *    answers. Held on a stale link (it ends in an approval card).
 *  - pair_session: read every 2 s for the first minute a pairing is open,
 *    then every 15 s (2026-10-08 cohesion audit, finding 1) - the state, the
 *    phone's name and the four words, and the PC's own sentence. See
 *    [`POLL_MS_HOT`] for why the first minute is not the whole session.
 *  - pair_cancel: ends it; never held.
 *  - devices_list / devices_remove({id}) / devices_shared({retired}):
 *    the list; Remove ONE device (immediate, after "are you sure?"); Retire
 *    the old shared key for other devices (immediate), or Bring it back
 *    (one card plus Windows Hello; held on a stale link).
 *
 * The approval card itself - "Jarvis wants to connect a new device" - is
 * never answered here. It shows in the Jarvis bar and the widget like every
 * other card, and the "Open the card" line at the top of this page links to
 * it (card-link.js).
 *
 * @module devices
 */

import { onLink, onEvent, currentLink, linkWords } from "./jarvis-link.js";
import { pairWaitMs } from "./devices-pair-poll.js";
import {
  CODE_GONE,
  LABEL_BUTTON,
  LABEL_PROMPT,
  NEEDS_ADDRESS,
  STALE,
  countdown,
  deviceLine,
  isActive,
  labelDone,
  problemWords,
  removeQuestion,
  sessionLine,
  sharedSignedLine,
  sharedView,
  signedLine,
  wordsLine,
} from "./devices-words.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

const el = {
  section: $("devices"),
  state: $("dv-state"),
  body: $("dv-body"),
  addressRow: $("dv-address-row"),
  address: $("dv-address"),
  addressKnown: $("dv-address-known"),
  addressShown: $("dv-address-shown"),
  addressChange: $("dv-address-change"),
  pair: $("dv-pair"),
  pairStatus: $("dv-pair-status"),
  pairWhy: $("dv-pair-why"),
  panel: $("dv-panel"),
  codeBox: $("dv-code-box"),
  qr: $("dv-qr"),
  code: $("dv-code"),
  countdown: $("dv-countdown"),
  words: $("dv-words"),
  session: $("dv-session"),
  wrongTries: $("dv-wrong-tries"),
  cancel: $("dv-cancel"),
  close: $("dv-close"),
  list: $("dv-list"),
  status: $("dv-status"),
  sharedLine: $("dv-shared-line"),
  sharedSigned: $("dv-shared-signed"),
  retire: $("dv-retire"),
  bringBack: $("dv-bring-back"),
  sharedStatus: $("dv-shared-status"),
  oldKeySlot: $("dv-old-key-slot"),
};

let view = null; // the last GET /api/devices answer
let address = { value: "", editing: true };
let busy = false;
let pollTimer = null;
let tickTimer = null;
let codeShownAt = 0; // when the code went on screen - see pairWaitMs
let secondsLeft = 0;
let showingCode = false;

function live() {
  return linkWords(currentLink()).canAct;
}

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

/* ── The old "Show the token for my phone" (design 7.1) ─────────────── */

// Where the Connection card's reveal lives until this page knows pairing is
// there. Moved (never copied - settings.js keeps its own listeners on the
// same elements) into the shared-key row while the old key still works for
// other devices, and hidden once it is retired. A PC without pairing keeps
// it where it always was.
const oldKey = {
  field: $("pairing"),
  home: null,
  label: null,
  button: $("reveal-token"),
  hide: $("hide-token"),
  labelWords: null,
  buttonWords: null,
};
if (oldKey.field) {
  oldKey.home = { parent: oldKey.field.parentNode, next: oldKey.field.nextSibling };
  oldKey.label = oldKey.field.querySelector(".label");
  oldKey.labelWords = oldKey.label ? oldKey.label.textContent : "";
  oldKey.buttonWords = oldKey.button ? oldKey.button.textContent : "";
}

function placeOldKey(where) {
  if (!oldKey.field) return;
  if (where === "home") {
    if (oldKey.field.parentNode !== oldKey.home.parent) {
      oldKey.home.parent.insertBefore(oldKey.field, oldKey.home.next);
    }
    oldKey.field.hidden = false;
    if (oldKey.label) oldKey.label.textContent = oldKey.labelWords;
    if (oldKey.button) oldKey.button.textContent = oldKey.buttonWords;
    return;
  }
  if (el.oldKeySlot && oldKey.field.parentNode !== el.oldKeySlot) {
    el.oldKeySlot.append(oldKey.field);
  }
  if (oldKey.label) oldKey.label.textContent = "The old shared key";
  if (oldKey.button) {
    oldKey.button.textContent = "Show the old shared key (not needed with QR pairing)";
  }
  if (where === "hidden") {
    // Put away a key that is on screen before hiding the row it is in.
    if (oldKey.hide && oldKey.button && oldKey.button.hidden) oldKey.hide.click();
    oldKey.field.hidden = true;
  } else {
    oldKey.field.hidden = false;
  }
}

/* ── The device list ─────────────────────────────────────────────────── */

/** Only when the backend says it has signed approvals (older: nothing extra). */
function signedOn() {
  return Boolean(view && view.signed_approvals === true);
}

function deviceRow(d) {
  const li = node("li", "sc-gpu dv-device");
  li.dataset.id = d.id;
  // The owner's label when he gave one, else the name the phone sent at
  // pairing. `shown` comes off the PC (jarvis_devices.row_shown), so the list
  // here and the list on the phone can never word one device differently.
  const name = node("span", "sc-gpu-name", d.shown || d.name || d.id);
  if (d.this_device) name.append(node("span", "hint", " (this app)"));
  li.append(name, node("span", "sc-gpu-role", deviceLine(d)));
  if (d.label && d.name && d.name !== d.label) {
    // The device's own name stays reachable, so the owner can see what he is
    // going back to by clearing the label. Never a key, and never on a row
    // whose label IS the name it sent (there it would say the same thing
    // twice).
    const source = node("span", "sc-gpu-role dv-source", `The phone calls itself ${d.name}.`);
    li.dataset.dvSource = d.name;
    li.append(source);
  }
  const signed = signedLine(d, signedOn());
  if (signed) {
    const line = node("span", "sc-gpu-role dv-signed", signed);
    line.dataset.approvalKey = String(d.approval_key === true ? "on" : d.approval_key === "waiting" ? "waiting" : "off");
    li.append(line);
  }
  if (d.removable) {
    const row = node("div", "row");
    // "Name this device…" (docs/MULTI-DEVICE-DESIGN.md, the first slice):
    // the name the owner types, beside the key. No card - it grants nothing
    // and revokes nothing - and it is never held on a stale link, exactly
    // like Remove beside it. A device's own key never appears here.
    const label = node("button", "btn ghost small dv-label", LABEL_BUTTON);
    label.type = "button";
    label.disabled = busy;
    label.title = d.label ? `Currently called ${d.label}` : "";
    label.addEventListener("click", () => labelDevice(d));
    const remove = node("button", "btn small dv-remove", "Remove…");
    remove.type = "button";
    remove.disabled = busy;
    remove.addEventListener("click", () => removeDevice(d));
    row.append(label, remove);
    li.append(row);
  }
  return li;
}

/** The freshest row for `id` off the PC's own list, or `d` itself. A row is
 * rebuilt from `GET /api/devices` after every change, so this is what the
 * owner is looking at right now - and reading the label from the CURRENT list
 * (never from the row that was on screen when the button was built) is what
 * keeps "press OK without changing anything" from sending a second rename. */
function freshRow(d) {
  const rows = view && Array.isArray(view.devices) ? view.devices : [];
  return rows.find((r) => r && r.id === d.id) || d;
}

function paint() {
  if (!el.section) return;
  if (!view || view.available === false) {
    say(el.state, (view && view.why) || "Asking Jarvis…");
    el.state.hidden = false;
    el.body.hidden = true;
    placeOldKey("home");
    return;
  }
  el.state.hidden = true;
  el.body.hidden = false;

  // Pairing: available, and the link is live (rule 4 - it ends in a card).
  const pairing = view.pairing || {};
  const why = pairing.available === false
    ? (pairing.why_not || "Pairing is not possible on this PC right now.")
    : "";
  el.pair.disabled = busy || Boolean(why) || !live() || showingCode;
  el.pairWhy.textContent = why || (!live() ? STALE : "");
  el.pairWhy.hidden = !el.pairWhy.textContent;

  el.addressRow.hidden = !address.editing;
  el.addressKnown.hidden = address.editing;
  el.addressShown.textContent = address.value;

  const devices = Array.isArray(view.devices) ? view.devices : [];
  el.list.replaceChildren(...devices.map(deviceRow));

  const shared = sharedView(view.shared);
  el.sharedLine.textContent = shared.line;
  const anySigned = devices.some((d) => d.approval_key === true);
  const sharedSigned = sharedSignedLine(view.shared, signedOn(), anySigned);
  el.sharedSigned.textContent = sharedSigned;
  el.sharedSigned.hidden = !sharedSigned;
  el.retire.hidden = !shared.retire;
  el.retire.disabled = busy;
  el.bringBack.hidden = !shared.bringBack;
  el.bringBack.disabled = busy || !live();
  // The old reveal ("Show the old shared key") is hidden once the shared key
  // works from this PC only - retired by the owner, or (2026-10-05) kept here
  // because a device holds a key of its own. It can no longer pair anything.
  const sharedGone = Boolean(view.shared && (view.shared.retired || view.shared.first_pair_only));
  placeOldKey(sharedGone ? "hidden" : "moved");
}

async function loadList() {
  if (!el.section || !IS_TAURI) return;
  try {
    view = await TAURI.core.invoke("devices_list");
  } catch (error) {
    view = { available: false, why: problemWords(error) };
  }
  paint();
}

async function loadAddress() {
  if (!IS_TAURI) return;
  try {
    const out = await TAURI.core.invoke("pair_phone_address");
    if (out && typeof out.address === "string" && out.address) {
      address = { value: out.address, editing: out.source !== "remembered" };
      el.address.value = out.address;
    }
  } catch {
    // Typed once instead.
  }
  paint();
}

async function removeDevice(d) {
  if (!window.confirm(removeQuestion(d.shown || d.name || d.id))) return;
  busy = true;
  say(el.status, "Removing…");
  paint();
  try {
    const out = await TAURI.core.invoke("devices_remove", { id: d.id });
    say(el.status, `${(out && out.name) || d.name} was removed.`, "ok");
  } catch (error) {
    say(el.status, problemWords(error), "bad");
  } finally {
    busy = false;
  }
  await loadList();
}

/**
 * Naming a device (docs/MULTI-DEVICE-DESIGN.md, the first slice): the owner's
 * own name for a device he already paired, kept beside its key on the PC.
 *
 * Immediate, no approval card, and never held on a stale link - the same
 * treatment Remove gets, for the opposite reason: a label grants nothing and
 * revokes nothing, it only changes what the list on the PC and the phone call
 * that device. A device can never approve another device from here; the
 * pairing card that does stays PC-only with Windows Hello.
 *
 * The box starts at the name the device is called NOW, so pressing OK
 * unchanged changes nothing, and clearing it goes back to the name the device
 * gave itself at pairing. A label the PC refuses (empty is fine; too long or
 * the wrong characters is not) says so in the PC's own words, above.
 */
async function labelDevice(d) {
  const row = freshRow(d);
  const now = String(row.label || "");
  const typed = window.prompt(LABEL_PROMPT, now);
  if (typed === null) return;                       // Cancel: nothing sent
  const next = typed.trim();
  if (next === now) return;                         // unchanged: nothing sent
  busy = true;
  say(el.status, "Naming…");
  paint();
  try {
    const out = await TAURI.core.invoke("devices_label", { id: d.id, label: next });
    say(el.status, labelDone((out && out.shown) || next || row.name || d.id), "ok");
  } catch (error) {
    say(el.status, problemWords(error), "bad");
  } finally {
    busy = false;
  }
  await loadList();
}

async function retire() {
  const shared = sharedView(view && view.shared);
  if (shared.retireQuestion && !window.confirm(shared.retireQuestion)) return;
  busy = true;
  say(el.sharedStatus, "Retiring…");
  paint();
  try {
    await TAURI.core.invoke("devices_shared", { retired: true });
    say(el.sharedStatus, "Retired. It now works on this PC only.", "ok");
  } catch (error) {
    say(el.sharedStatus, problemWords(error), "bad");
  } finally {
    busy = false;
  }
  await loadList();
}

async function bringBack() {
  if (!live()) {
    say(el.sharedStatus, STALE, "bad");
    return;
  }
  busy = true;
  say(el.sharedStatus, "Asking…");
  paint();
  try {
    const out = await TAURI.core.invoke("devices_shared", { retired: false });
    say(el.sharedStatus, out && out.waiting
      ? "Waiting for your approval on the card, with Windows Hello."
      : "Done.", "ok");
  } catch (error) {
    say(el.sharedStatus, problemWords(error), "bad");
  } finally {
    busy = false;
  }
  await loadList();
}

/* ── Pairing a phone ─────────────────────────────────────────────────── */

function stopTimers() {
  if (pollTimer) clearTimeout(pollTimer);
  if (tickTimer) clearInterval(tickTimer);
  pollTimer = null;
  tickTimer = null;
}

/** Takes the code and the QR picture off the page. */
function dropCode() {
  showingCode = false;
  el.qr.removeAttribute("src");
  el.code.textContent = "";
  el.countdown.textContent = "";
  el.codeBox.hidden = true;
}

function paintSession(s) {
  const state = (s && s.state) || "none";
  secondsLeft = typeof s.expires_in === "number" ? s.expires_in : secondsLeft;
  if (showingCode) el.countdown.textContent = countdown(secondsLeft);
  const words = wordsLine(s.words);
  el.words.textContent = words;
  el.words.hidden = !words || !isActive(state);
  const line = sessionLine(s);
  say(el.session, !showingCode && state === "waiting_for_phone" ? CODE_GONE : line,
    state === "done" ? "ok" : (isActive(state) ? "" : (state === "none" ? "" : "bad")));
  const wrong = Array.isArray(s.wrong_tries_from) ? s.wrong_tries_from : [];
  el.wrongTries.textContent = wrong.length
    ? `Wrong tries came from: ${wrong.join(", ")}.`
    : "";
  el.wrongTries.hidden = !wrong.length;
  if (!isActive(state)) {
    stopTimers();
    dropCode();
    el.cancel.hidden = true;
    el.close.hidden = false;
    if (state === "done") loadList();
  } else {
    el.cancel.hidden = false;
    el.close.hidden = true;
  }
  paint();
}

async function poll() {
  try {
    const s = await TAURI.core.invoke("pair_session");
    if (s && s.state === "none" && !showingCode && el.panel.hidden) return;
    el.panel.hidden = false;
    paintSession(s || { state: "none" });
  } catch (error) {
    // One missed read is not the end of the pairing; say so and keep going.
    say(el.session, problemWords(error), "bad");
  }
}

function startTimers() {
  stopTimers();
  codeShownAt = Date.now();
  armPoll();
  // The countdown under the code: 1 s while the code is on screen. It needs
  // no self-aligning tick, unlike the approval clocks - it is repainted by
  // the same second it counts, so it drifts by nothing a reader can see.
  tickTimer = setInterval(() => {
    if (!showingCode) return;
    secondsLeft = Math.max(0, secondsLeft - 1);
    el.countdown.textContent = countdown(secondsLeft);
  }, 1000);
}

/**
 * One read of the pairing state, then the next one at the wait
 * [`pairWaitMs`] asks for (2026-10-08 cohesion audit, finding 1). `setTimeout`
 * rather than a flat 2 s `setInterval`, so the wait can follow the session -
 * 2 s while the phone is still likely to be pointed at the code, 15 s after
 * that, which is the cadence `brain.js` polls its own panels at.
 *
 * The DEVICE LIST is not polled at all: it is re-read by the `devices` event
 * below (`loadList()` on every `devices` frame), which is the freshness this
 * page actually needs. This timer only carries the pairing panel, where the
 * phone's four words arrive with the PC's approval card.
 */
function armPoll() {
  pollTimer = setTimeout(runPoll, pairWaitMs(codeShownAt, Date.now()));
}

function runPoll() {
  pollTimer = null;
  poll().finally(armPoll);
}

async function pairPhone() {
  const typed = address.editing ? el.address.value.trim() : address.value;
  if (!typed) {
    say(el.pairStatus, NEEDS_ADDRESS, "bad");
    el.address.focus();
    return;
  }
  if (!live()) {
    say(el.pairStatus, STALE, "bad");
    return;
  }
  busy = true;
  say(el.pairStatus, "Asking your PC for a code…");
  paint();
  try {
    const out = await TAURI.core.invoke("pair_start", { address: typed });
    address = { value: typed, editing: false };
    say(el.pairStatus, "");
    el.qr.src = out.qr_svg;
    el.code.textContent = out.code;
    secondsLeft = out.expires_in;
    showingCode = true;
    el.codeBox.hidden = false;
    el.countdown.textContent = countdown(secondsLeft);
    el.panel.hidden = false;
    paintSession({ state: "waiting_for_phone", expires_in: out.expires_in,
                   tries_left: out.tries_left });
    startTimers();
  } catch (error) {
    say(el.pairStatus, problemWords(error), "bad");
  } finally {
    busy = false;
    paint();
  }
}

async function cancelPairing() {
  stopTimers();
  dropCode();
  el.panel.hidden = true;
  el.words.textContent = "";
  say(el.session, "");
  try {
    await TAURI.core.invoke("pair_cancel");
    say(el.pairStatus, "Pairing was cancelled.");
  } catch (error) {
    say(el.pairStatus, problemWords(error), "bad");
  }
  paint();
}

function closePanel() {
  stopTimers();
  dropCode();
  el.panel.hidden = true;
  el.words.textContent = "";
  say(el.session, "");
  paint();
}

if (el.section) {
  if (!IS_TAURI) {
    say(el.state, "Open this in Jarvis Desktop to pair a phone.");
  } else {
    el.pair.addEventListener("click", pairPhone);
    el.cancel.addEventListener("click", cancelPairing);
    el.close.addEventListener("click", closePanel);
    el.retire.addEventListener("click", retire);
    el.bringBack.addEventListener("click", bringBack);
    el.addressChange.addEventListener("click", () => {
      address = { ...address, editing: true };
      el.address.value = address.value;
      paint();
      el.address.focus();
    });
    loadList().then(async () => {
      if (!view || view.available === false) return;
      await loadAddress();
      // A pairing already open (this window was reloaded): its state and
      // words are shown, but never its code again.
      const s = await TAURI.core.invoke("pair_session").catch(() => null);
      if (s && isActive(s.state)) {
        el.panel.hidden = false;
        paintSession(s);
        startTimers();
      }
    });
    onLink(() => paint());
    // The other app removed or paired a device: re-read the list.
    onEvent((frame) => {
      if (frame && frame.kind === "devices") loadList();
    });
  }
}
