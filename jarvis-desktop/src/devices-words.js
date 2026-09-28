/**
 * Settings -> Devices: the words, with no page attached, so a plain node
 * test can check them (tests/devices.mjs). docs/PAIRING-DESIGN.md sections
 * 3, 6.1, 6.4 and 7.1 are the source of every sentence here; where the PC
 * sends its own sentence (a session's `message`, a refusal's `error`) that
 * sentence wins, and these are only what is said when it sends none.
 *
 * @module devices-words
 */

/** The session states in which a code or the four words are on screen. */
export const ACTIVE_STATES = ["waiting_for_phone", "waiting_for_card", "approved"];

/** What each state says when the PC's answer carries no `message`. */
export const SESSION_WORDS = {
  waiting_for_phone: "Waiting for your phone…",
  waiting_for_card: "Your phone asked. Check the card - the words must match:",
  approved: "Approved. Waiting for the phone to collect its key…",
  done: "{name} is connected.",
  denied: "You said no on the card. Nothing changed.",
  timed_out: "The card ran out of time. Press Pair a phone to start again.",
  expired: "This code ran out of time. Press Pair a phone to start again.",
  burnt: "Three wrong tries - this code no longer works. Start again.",
  cancelled: "Pairing was cancelled.",
  refused: "Your PC could not show the approval card. Start again.",
  none: "",
};

/** A session that is waiting, but whose code this page no longer holds
 * (the window was reloaded): the code is never read back from the PC. */
export const CODE_GONE = "A pairing is still waiting, but its code is no longer shown " +
  "here. Cancel it, or press Pair a phone for a new code.";

export const NEEDS_ADDRESS = "Type the name your phone reaches this PC at first - it ends " +
  "in .ts.net (Tailscale) or .nord (NordVPN Meshnet).";

export const STALE = "The connection to Jarvis is catching up, so nothing can be sent " +
  "until it does.";

/** Whether a session in `state` still shows a code or the words. */
export function isActive(state) {
  return ACTIVE_STATES.includes(state);
}

/** The four words, spaced for reading aloud: "tulip · anchor · mellow · crane". */
export function wordsLine(words) {
  return Array.isArray(words) ? words.filter((w) => typeof w === "string").join(" · ") : "";
}

/** The status line for one `GET /api/pair/session` answer. */
export function sessionLine(view) {
  if (!view || typeof view !== "object") return "";
  const said = typeof view.message === "string" ? view.message.trim() : "";
  if (said) return said;
  const words = SESSION_WORDS[view.state];
  if (words === undefined) return "";
  return words.replace("{name}", view.device_name || "Your phone");
}

/** "Works for 9:41 more", from seconds left. */
export function countdown(secondsLeft) {
  const s = Math.max(0, Math.floor(Number(secondsLeft) || 0));
  if (s === 0) return "This code has run out of time.";
  const m = Math.floor(s / 60);
  const r = String(s % 60).padStart(2, "0");
  return `Works for ${m}:${r} more`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct",
  "Nov", "Dec"];

/** "3 Sep" - the design's short date. Spelled out here rather than asked of
 * the browser, whose English month names differ by version ("Sept"). */
export function shortDate(seconds) {
  const d = new Date(seconds * 1000);
  return Number.isNaN(d.getTime()) ? "" : `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

/** "2 minutes ago", "3 days ago". */
export function ago(seconds, now = Date.now()) {
  const secs = Math.max(0, Math.floor(now / 1000 - seconds));
  if (secs < 90) return "just now";
  const mins = Math.floor(secs / 60);
  if (mins < 90) return `${mins} minute${mins === 1 ? "" : "s"} ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 36) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

/** Remove's "are you sure?" (design 7.1), like Forget's. */
export function removeQuestion(name) {
  return `Remove ${name}? It stops reaching Jarvis at once. To use it again, pair it ` +
    "again with the QR code.";
}

/** One device's second line: "Phone · paired 3 Sep · last used 2 minutes ago". */
export function deviceLine(d, now = Date.now()) {
  if (d.kind === "pc") return "This PC - it cannot be removed.";
  const bits = [d.kind === "phone" ? "Phone" : "Device"];
  if (typeof d.created === "number") bits.push(`paired ${shortDate(d.created)}`);
  bits.push(typeof d.last_seen === "number" ? `last used ${ago(d.last_seen, now)}` : "not used yet");
  return bits.join(" · ");
}

const THIRTY_DAYS = 30 * 24 * 3600;

/**
 * The old shared key's row (design 7.1), from `GET /api/devices`' `shared`:
 * `{ line, retire, retireQuestion, bringBack }` - the sentence, whether
 * Retire and Bring it back are offered, and the confirm Retire asks first
 * (only when another device used the key in the last 30 days).
 */
export function sharedView(shared, now = Date.now()) {
  const s = shared && typeof shared === "object" ? shared : {};
  if (s.retired) {
    const when = typeof s.retired_at === "number" ? ` on ${shortDate(s.retired_at)}` : "";
    return {
      line: `Retired${when} - it now works on this PC only.`,
      retire: false,
      retireQuestion: null,
      bringBack: s.can_bring_back_here === true,
    };
  }
  const seen = typeof s.last_other_seen === "number" ? s.last_other_seen : null;
  const recent = seen !== null && now / 1000 - seen <= THIRTY_DAYS;
  if (recent) {
    const where = s.last_other_address ? ` (${s.last_other_address})` : "";
    return {
      line: `Last used from another device${where} ${ago(seen, now)}. Pair that device first.`,
      retire: true,
      retireQuestion: "Retire the old shared key for other devices? The device" +
        `${where} that used it ${ago(seen, now)} will stop reaching Jarvis until it is ` +
        "paired with the QR code. This PC keeps working.",
      bringBack: false,
    };
  }
  return {
    line: seen === null
      ? "No other device has used it."
      : `No other device has used it since ${shortDate(seen)}.`,
    retire: true,
    retireQuestion: null,
    bringBack: false,
  };
}

/** The Brain-style "answer we can't read" guard: an error in words, never
 * a bridge error or JSON. */
export function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 400) {
    return "Could not ask Jarvis. Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}
