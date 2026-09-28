/**
 * "Photo to reminder" (the owner's choice, 2026-09-28; JARVIS-API.md
 * section 83; backend jarvis_photo_remind.py).
 *
 * A picture in, a PROPOSED reminder out. Two ways in on the PC:
 *  - the Jarvis bar: after a screen capture (Alt+Shift+S), "Find a date in
 *    it" on the capture's chip (main.js);
 *  - the Brain's Coming up: "Choose a picture..." for an image file
 *    (brain.js), shrunk here to the capture's own limits first.
 *
 * The PC reads the words with Windows' own text recognition and finds the
 * date, time and title with plain code (never the AI model). This page shows
 * what it found in boxes the owner can change, and nothing happens until the
 * owner taps "Add a Jarvis reminder": ONE `photo_add_reminder` - a one-off
 * reminder, no card, held on a stale link. There is no "Also on my phone"
 * here: that hands a reminder to the PHONE's own apps (ARCHITECTURE section
 * 8); the phone's proposal has it.
 *
 * OUTSIDE TEXT. The words came from a picture someone else made. They are
 * put on the page with textContent only (never as HTML), never sent to the
 * AI model from here, never learned, and dropped when the proposal closes -
 * nothing here stores them.
 *
 * The phone says the same words (net/PhotoReminder.kt);
 * backend/test_photo_remind.py checks both against the PC's.
 *
 * @module photo-reminder
 */

export const TITLE = "Photo to reminder";
export const FIND_LABEL = "Find a date in it";
export const CHOOSE_LABEL = "Choose a picture…";
export const OUTSIDE_NOTE =
  "Read from a picture on your PC, by plain code - not by the AI model. These words count " +
  "as outside text: Jarvis never acts on them, and nothing is kept once you close this.";
export const NOTHING_FOUND =
  "No date or time found in the picture. You can still type one in and add the reminder yourself.";
export const NO_WORDS = "No words could be read in the picture.";
export const FOUND_ONE = "Found a date. Check it, change anything, then tap to add it.";
export const foundMany = (n) =>
  `Found ${n} dates. Check the first, or pick another, then tap to add it.`;
export const NO_TIME = "No time found - 09:00 is filled in. Change it if you need to.";
export const PASSED = "That time has already passed - change the date or time.";
export const ADD_LABEL = "Add a Jarvis reminder";
export const CLOSE_LABEL = "Close";
export const READING = "Reading the words in the picture on your PC…";
export const WORDS_READ = "Words read from the picture";
export const WHAT_LABEL = "What";
export const DATE_LABEL = "Date";
export const TIME_LABEL = "Time";
export const WHAT_PLACEHOLDER = "What is it for?";
export const CHOOSE_NOTE =
  "Choose a photo or screenshot of a flyer, a ticket or a message. Your PC reads the words in " +
  "it and suggests a reminder; nothing is set up until you tap Add. In the Jarvis bar, " +
  "Alt+Shift+S then \"Find a date in it\" does the same for your screen.";
export const NOT_A_PICTURE = "That is not a picture Jarvis can read. Choose a JPEG or PNG.";

/** The capture's own limits (commands.rs MAX_CAPTURE_WIDTH, JPEG_QUALITY). */
export const MAX_LONG_EDGE = 1920;
export const JPEG_QUALITY = 0.82;

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const TIME_RE = /^([01]?\d|2[0-3]):[0-5]\d$/;

/**
 * The PC's answer, made safe to draw: at most three proposals, each with a
 * plain title, date and time; anything else dropped.
 */
export function readScan(out) {
  const o = out && typeof out === "object" ? out : {};
  const found = (Array.isArray(o.found) ? o.found : []).slice(0, 3).map((f) => ({
    title: typeof f?.title === "string" ? f.title.slice(0, 200) : "",
    date: typeof f?.date === "string" && DATE_RE.test(f.date) ? f.date : "",
    time: typeof f?.time === "string" && TIME_RE.test(f.time) ? f.time : "09:00",
    timeFound: f?.time_found === true,
    passed: f?.passed === true,
    when: typeof f?.when === "string" ? f.when : "",
  })).filter((f) => f.date);
  const text = typeof o.text === "string" ? o.text : "";
  let said;
  if (!text.trim()) said = NO_WORDS;
  else if (!found.length) said = NOTHING_FOUND;
  else said = found.length === 1 ? FOUND_ONE : foundMany(found.length);
  return { found, text, said, leftOut: Number(o.left_out) || 0 };
}

/** What the tap sends, or a sentence saying what is wrong. */
export function reminderArgs(what, date, time) {
  const text = String(what || "").trim();
  if (!DATE_RE.test(String(date || ""))) return { error: "A date looks like 2026-10-12." };
  if (!TIME_RE.test(String(time || ""))) return { error: "A time looks like 14:00." };
  if (!text) return { error: "A reminder needs some words: what should Jarvis remind you of?" };
  return { args: { date, time: time.length === 4 ? `0${time}` : time, text } };
}

function el(doc, tag, cls, text) {
  const n = doc.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

/**
 * Draws the proposal into `box`. `invoke` must reject on failure (Rust's
 * sentence); `canAct()` says whether the link is live; `onDone(said)` after
 * a reminder was added (the box then holds only the PC's sentence);
 * `onClose()` when closed. Returns {close, sync}.
 */
export function mountProposal(box, out, { invoke, canAct = () => true, onDone, onClose, say,
  buttonClass = "btn small" }) {
  const doc = box.ownerDocument;
  const view = readScan(out);
  const tell = say || (() => {});
  const wrap = el(doc, "div", "photo-proposal");
  wrap.setAttribute("role", "group");
  wrap.setAttribute("aria-label", TITLE);
  wrap.append(el(doc, "p", "photo-said", view.said));

  const first = view.found[0] || { title: "", date: "", time: "09:00", timeFound: false };
  const what = el(doc, "input", "photo-what");
  what.type = "text";
  what.maxLength = 200;
  what.placeholder = WHAT_PLACEHOLDER;
  what.value = first.title;
  const date = el(doc, "input", "photo-date");
  date.type = "date";
  date.value = first.date;
  const time = el(doc, "input", "photo-time");
  time.type = "time";
  time.value = first.time;
  const hint = el(doc, "p", "note photo-hint");
  const fill = (f) => {
    what.value = f.title;
    date.value = f.date;
    time.value = f.time;
    hint.textContent = [f.timeFound ? "" : NO_TIME, f.passed ? PASSED : ""].filter(Boolean).join(" ");
    hint.hidden = !hint.textContent;
  };
  fill(first);
  if (!view.found.length) hint.hidden = true;

  if (view.found.length > 1) {
    const picks = el(doc, "div", "photo-picks");
    view.found.forEach((f) => {
      const b = el(doc, "button", `${buttonClass} photo-pick`,
        `${f.when || `${f.date} ${f.time}`}${f.title ? ` - ${f.title}` : ""}`);
      b.type = "button";
      b.addEventListener("click", () => fill(f));
      picks.append(b);
    });
    wrap.append(picks);
  }

  const field = (label, input) => {
    const l = el(doc, "label", "photo-field");
    l.append(el(doc, "span", "photo-label", label), input);
    return l;
  };
  wrap.append(field(WHAT_LABEL, what), field(DATE_LABEL, date), field(TIME_LABEL, time), hint);

  const row = el(doc, "div", "photo-actions");
  const add = el(doc, "button", `${buttonClass} primary photo-add`, ADD_LABEL);
  add.type = "button";
  const shut = el(doc, "button", `${buttonClass} photo-close`, CLOSE_LABEL);
  shut.type = "button";
  row.append(add, shut);
  wrap.append(row);
  const err = el(doc, "p", "note photo-error");
  err.hidden = true;
  wrap.append(err);

  if (view.text.trim()) {
    const det = el(doc, "details", "photo-words");
    det.append(el(doc, "summary", "", WORDS_READ), el(doc, "pre", "photo-text", view.text));
    wrap.append(det);
  }
  wrap.append(el(doc, "p", "note photo-outside", OUTSIDE_NOTE));

  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    // Nothing of the picture's words is kept once this is closed.
    box.replaceChildren();
    box.hidden = true;
    if (onClose) onClose();
  };
  const sync = () => { add.disabled = !canAct(); };
  sync();
  add.addEventListener("click", async () => {
    sync();
    if (add.disabled) return;
    const got = reminderArgs(what.value, date.value, time.value);
    if (got.error) {
      err.textContent = got.error;
      err.hidden = false;
      return;
    }
    add.disabled = true;
    try {
      const answer = await invoke("photo_add_reminder", got.args);
      const said = String((answer && answer.said) || "Reminder set.");
      // The picture's words go; only the PC's own sentence stays.
      closed = true;
      box.replaceChildren(el(doc, "p", "photo-said photo-done", said));
      tell(said);
      if (onDone) onDone(said);
    } catch (error) {
      err.textContent = String(error && error.message ? error.message : error);
      err.hidden = false;
      add.disabled = false;
    }
  });
  shut.addEventListener("click", close);

  box.replaceChildren(wrap);
  box.hidden = false;
  return { close, sync };
}

/**
 * An image file as a JPEG data URI no bigger than a screen capture, or
 * throws NOT_A_PICTURE. Held in memory only; nothing is written.
 */
export async function shrinkPicture(file, win = globalThis) {
  if (!file || !/^image\/(jpeg|png|bmp|gif|webp|tiff)$/i.test(String(file.type || ""))) {
    throw new Error(NOT_A_PICTURE);
  }
  const url = win.URL.createObjectURL(file);
  try {
    const img = await new Promise((resolve, reject) => {
      const i = new win.Image();
      i.onload = () => resolve(i);
      i.onerror = () => reject(new Error(NOT_A_PICTURE));
      i.src = url;
    });
    const w = img.naturalWidth;
    const h = img.naturalHeight;
    if (!w || !h) throw new Error(NOT_A_PICTURE);
    const scale = Math.min(1, MAX_LONG_EDGE / Math.max(w, h));
    const canvas = win.document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(w * scale));
    canvas.height = Math.max(1, Math.round(h * scale));
    canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", JPEG_QUALITY);
  } finally {
    win.URL.revokeObjectURL(url);
  }
}
