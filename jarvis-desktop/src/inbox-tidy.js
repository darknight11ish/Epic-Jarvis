/**
 * "Inbox tidy by voice" - the Undo strip under the Jarvis bar's input (the
 * owner's decision of 2026-09-28; JARVIS-API.md section 92; backend
 * jarvis_inbox_tidy.py, inbox-tidy.patch; src-tauri/src/brain/inbox_tidy.rs).
 *
 * The owner says "archive the newsletters from last week" (or "mark all from
 * Sam as read", "move the promos to Trash"). Jarvis finds the emails on this
 * PC and raises ONE approval card that lists every email it will touch; the
 * card is an ordinary one, decided in the Jarvis bar - never by voice and
 * never from the widget's one line (email-sending.js `isEmailCard`). Approved,
 * the PC does it and keeps a record for 10 minutes, and this strip offers
 * Undo. There is no permanent delete: "delete" only ever means Trash.
 *
 * What this file does:
 *  - reads the PC's status (`inbox_tidy_read`: counts and the PC's own
 *    words, never a sender or a subject) and works out what the strip says -
 *    the rule both apps follow, checked against
 *    `tests/fixtures/inbox-tidy-cases.json` (made by
 *    tools/gen_inbox_tidy_cases.py from the real backend; the phone reads
 *    the same file, net/InboxTidy.kt);
 *  - draws the strip and sends the one tap (`inbox_tidy_undo`): no card, held
 *    on a stale link (the button is greyed and Rust refuses too), and while
 *    Jarvis is locked or the lists are hidden the strip says only that the
 *    inbox was tidied and Undo waits for the unlock.
 *
 * Every word of the emails stays on the PC: nothing here ever holds a sender
 * or a subject. The strip approves nothing and starts nothing.
 *
 * @module inbox-tidy
 */

/** The strip's own words, both apps, word for word (the contract's `words`). */
export const WORDS = Object.freeze({
  hidden: "Your inbox was tidied. You can undo it for a few minutes.",
  locked: "Unlock Jarvis to undo this.",
  missing: "Your PC's Jarvis cannot tidy your inbox yet - run apply-patches.ps1 on the PC.",
  stale: "The connection to Jarvis is catching up, so nothing can be sent until it does.",
  title: "Inbox tidy",
  undo: "Undo",
  undo_left: "{minutes} min left to undo",
  undone: "Put back. Everything is as it was before.",
});

/** How often the strip re-reads the PC while the bar is on screen. */
export const POLL_MS = 20000;

/** How long the PC's sentence about an Undo stays after it. */
export const NOTE_MS = 8000;

const asInt = (v) => (typeof v === "number" && Number.isFinite(v) ? Math.trunc(v) : null);
const asText = (v) => (typeof v === "string" && v.trim() ? v.trim() : null);

/**
 * `inbox_tidy_read`'s answer, read. A body that is not what the PC sends
 * reads as "nothing to undo". `hidden` is Rust's: the PC's words were taken
 * out because Jarvis is locked or the lists are hidden.
 */
export function readStatus(body) {
  if (!body || typeof body !== "object") return { available: false, hidden: false, undo: null };
  const u = body.undo && typeof body.undo === "object" ? body.undo : null;
  const said = u ? asText(u.said) : null;
  const minutes = u ? asInt(u.minutes_left) : null;
  const undo = said && minutes !== null
    ? {
      count: asInt(u.count) ?? 0,
      action: asText(u.action) || "",
      said,
      minutesLeft: minutes,
      secondsLeft: asInt(u.seconds_left) ?? 0,
      more: asInt(u.more) ?? 0,
    }
    : null;
  return { available: body.available !== false, hidden: body.hidden === true, undo };
}

/**
 * The status as it is `ageMs` after it was read: the seconds left run down
 * here, so a strip does not keep offering an Undo whose ten minutes are up
 * while the link is down. An Undo with no time left is gone.
 */
export function aged(status, ageMs) {
  if (!status || !status.undo) return status;
  const left = status.undo.secondsLeft - Math.floor(Math.max(0, ageMs) / 1000);
  if (left <= 0) return { ...status, undo: null };
  return {
    ...status,
    undo: { ...status.undo, secondsLeft: left, minutesLeft: Math.max(1, Math.ceil(left / 60)) },
  };
}

/** `{minutes}` filled in. */
export function leftWords(minutes) {
  return WORDS.undo_left.replace("{minutes}", String(minutes));
}

/**
 * What the strip says for `status`, or null when there is nothing to undo -
 * the rule both apps follow (the contract's `strip` rows):
 *  - `locked` (Jarvis is locked, or the lists are hidden): only that the
 *    inbox was tidied - no count, no action - and Undo waits for the unlock;
 *  - `stale`: Undo is held (rule 4) and the strip says why;
 *  - more than one tidy open: the newest is shown and the others counted.
 */
export function stripFor(status, { locked = false, stale = false } = {}) {
  const u = status && status.undo;
  if (!u) return null;
  let text;
  if (locked) {
    text = WORDS.hidden;
  } else if (u.more > 0) {
    text = `${u.said} (${u.more} earlier ${u.more === 1 ? "tidy" : "tidies"} can be undone after)`;
  } else {
    text = u.said;
  }
  return {
    text,
    left: leftWords(u.minutesLeft),
    can_undo: !locked && !stale,
    note: locked ? WORDS.locked : stale ? WORDS.stale : "",
  };
}

/**
 * Mounts the strip in `box`. `invoke(command, args)` is the strict Tauri call
 * (main.js `invokeStrict`); `isStale()` says whether the link is stale;
 * `announce(text)` speaks to a screen reader; `onChange()` lets the window
 * fit its height. Returns `{ refresh, close }`. Reads the PC every POLL_MS
 * while the page is visible, and on `refresh()`.
 */
export function mountInboxTidy(box, {
  invoke,
  isStale = () => false,
  announce = () => {},
  onChange = () => {},
  now = () => Date.now(),
  setTimer = (fn, ms) => setInterval(fn, ms),
  clearTimer = (id) => clearInterval(id),
  visible = () => !(typeof document !== "undefined" && document.hidden),
  later = (fn, ms) => setTimeout(fn, ms),
} = {}) {
  let held = null; // { status, at }
  let busy = false;
  let note = "";

  const text = document.createElement("p");
  text.className = "inbox-tidy-text";
  const row = document.createElement("div");
  row.className = "inbox-tidy-row";
  const left = document.createElement("span");
  left.className = "inbox-tidy-left";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "text-button inbox-tidy-undo";
  button.textContent = WORDS.undo;
  const line = document.createElement("p");
  line.className = "inbox-tidy-note";
  line.setAttribute("role", "status");
  row.append(left, button);
  box.replaceChildren(text, row, line);
  box.setAttribute("aria-label", WORDS.title);

  function paint() {
    const status = held ? aged(held.status, now() - held.at) : null;
    const strip = stripFor(status, {
      locked: Boolean(status && status.hidden),
      stale: isStale(),
    });
    if (!strip) {
      // Nothing open to Undo. Just after an Undo the PC's sentence ("Put back
      // 3 emails.") stays for a few seconds, alone, so the owner sees it.
      if (note) {
        text.textContent = note;
        row.hidden = true;
        line.textContent = "";
        if (box.hidden) {
          box.hidden = false;
          onChange();
        }
      } else if (!box.hidden) {
        box.hidden = true;
        onChange();
      }
      return;
    }
    row.hidden = false;
    text.textContent = strip.text;
    left.textContent = strip.left;
    button.disabled = !strip.can_undo || busy;
    line.textContent = note || strip.note;
    if (box.hidden) {
      box.hidden = false;
      onChange();
    }
  }

  async function refresh() {
    try {
      const body = await invoke("inbox_tidy_read");
      held = { status: readStatus(body), at: now() };
    } catch {
      // A failed read changes nothing: what was shown keeps aging.
    }
    paint();
  }

  button.addEventListener("click", async () => {
    if (busy || button.disabled) return;
    busy = true;
    note = "";
    paint();
    try {
      const out = await invoke("inbox_tidy_undo");
      const said = asText(out && out.message) || WORDS.undone;
      note = said;
      announce(said);
    } catch (error) {
      note = String(error && error.message ? error.message : error);
      announce(note);
    }
    busy = false;
    await refresh();
    // The sentence stays a few seconds, then goes (an older tidy, if there is
    // one, shows again under it).
    later(() => {
      note = "";
      paint();
    }, NOTE_MS);
  });

  const timer = setTimer(() => {
    if (visible()) refresh();
  }, POLL_MS);

  return {
    refresh,
    /** A few quick reads right after a tidy card was approved here, so the
     *  strip shows as soon as the PC has done it. */
    watchQuickly() {
      let n = 0;
      const id = setTimer(async () => {
        n += 1;
        await refresh();
        if (n >= 6) clearTimer(id);
      }, 3000);
    },
    close() {
      clearTimer(timer);
      box.replaceChildren();
      box.hidden = true;
    },
    /** For the tests: the strip as drawn now. */
    view() {
      return { hidden: box.hidden, text: text.textContent, left: left.textContent,
        disabled: button.disabled, note: line.textContent };
    },
  };
}
