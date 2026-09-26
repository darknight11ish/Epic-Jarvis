/**
 * Settings' "Security" section: the words, and nothing that decides.
 *
 * Every decision is made in Rust (src-tauri/src/lock.rs): which approvals ask
 * Windows Hello, whether a window may open, whether the Brain's memory lists
 * come back hidden, and whether a change is a loosening that has to pass
 * Windows Hello first. The settings are stored by the app where no window can
 * write them. This file only says what each choice means, so a page that
 * got something wrong here could mislabel a switch - never lower one.
 *
 * Kept apart from settings.js, like voice-settings.js, so tests/security.mjs
 * can hold the words and the loosen rule without a browser.
 */

/** What lock.rs stores when nothing has been chosen: the owner's defaults. */
export const DEFAULTS = Object.freeze({
  appLock: false,
  relockAfterSecs: 60,
  approvals: "risky",
  privateAnswers: false,
});

/** "Lock again after" - the only four values lock.rs accepts. */
export const RELOCK_CHOICES = Object.freeze([
  { id: 0, label: "Straight away" },
  { id: 60, label: "1 min" },
  { id: 300, label: "5 min" },
  { id: 900, label: "15 min" },
]);

/** "Windows Hello for approvals". There is no third choice below "Risky only". */
export const APPROVAL_CHOICES = Object.freeze([
  { id: "risky", label: "Risky only" },
  { id: "every", label: "Every approval" },
]);

/**
 * The phone's rule (BiometricGate.required), in plain words: not classified,
 * leaves this machine, cannot be undone, or rushed.
 */
export const RISKY_WORDS =
  "approvals that cannot be undone, that send something off this PC, that " +
  "Jarvis has not sorted by risk, or that something tried to rush you into";

/**
 * A value as Rust sent it, read the way lock.rs reads its own file: anything
 * missing is the default, and an odd "Lock again after" becomes the longest
 * choice that is not longer than it (the stricter side).
 */
export function normalise(settings) {
  const s = settings && typeof settings === "object" ? settings : {};
  const secs = Number(s.relockAfterSecs);
  const relock = !Number.isFinite(secs) || s.relockAfterSecs === undefined
    ? DEFAULTS.relockAfterSecs
    : Math.max(0, ...RELOCK_CHOICES.map((c) => c.id).filter((id) => id <= secs));
  return {
    appLock: s.appLock === true,
    relockAfterSecs: relock,
    approvals: s.approvals === "every" ? "every" : "risky",
    privateAnswers: s.privateAnswers === true,
  };
}

/** Anything beyond the defaults - lock.rs `any_lock_on`. */
export function anyLockOn(s) {
  return s.appLock || s.privateAnswers || s.approvals === "every";
}

/**
 * True when going from `prev` to `next` will ask Windows Hello first -
 * lock.rs `change_needs_hello`, repeated here only to say "Waiting for
 * Windows Hello…" rather than "Saving…" while the prompt is up. Rust decides.
 */
export function needsHello(prev, next) {
  const loosens =
    (prev.appLock && !next.appLock) ||
    next.relockAfterSecs > prev.relockAfterSecs ||
    (prev.approvals === "every" && next.approvals === "risky") ||
    (prev.privateAnswers && !next.privateAnswers);
  return anyLockOn(prev) && loosens;
}

/** Where to set Windows Hello up, one way of saying it everywhere. */
export const SET_UP_HELLO =
  "Set it up in Windows Settings, Accounts, Sign-in options - a PIN is enough.";

/**
 * What this PC's Windows Hello is, from get_security_settings' `hello`.
 * With no Windows Hello, risky approvals are refused, lock or no lock (the
 * owner's "no lock, no risky approval", 2026-09-25; lock/rules.rs
 * NO_HELLO_NO_RISKY). They used to go through without a check.
 */
export function helloLine(hello, settings) {
  const s = normalise(settings);
  switch (hello) {
    case "ready":
      return "Windows Hello is set up on this PC.";
    case "not-set-up":
      return anyLockOn(s)
        ? "Windows Hello is not set up on this PC, and a lock is on, so risky " +
          "approvals here are refused and locked windows will not open. " + SET_UP_HELLO
        : "Windows Hello is not set up on this PC. Until it is, risky approvals " +
          "here are refused, and no lock can be turned on. " + SET_UP_HELLO;
    case "blocked":
      return "Windows Hello is switched off on this PC by a policy, so risky " +
        "approvals here are refused and no lock can be turned on.";
    case "busy":
      return "Windows Hello did not answer just now. It is asked again when you " +
        "change something here.";
    case "not-windows":
      return "Windows Hello is a Windows feature, and this copy of Jarvis is not " +
        "running on Windows.";
    default:
      return "Could not check Windows Hello on this PC.";
  }
}

export function appLockDetail() {
  return "Opening the Jarvis bar, the Brain, Settings or the HUD window needs " +
    "Windows Hello. The widget stays on the desktop, but while this is on it " +
    "shows only a short title for an approval, and its Approve opens the " +
    "Jarvis bar to approve there. Notes to Jarvis are added in the Jarvis bar " +
    "too. Deny still works from the widget.";
}

export function relockNote(settings) {
  const s = normalise(settings);
  const base = "How long you can be away from the Jarvis bar, the Brain, " +
    "Settings and the HUD window before Windows Hello is asked again.";
  return s.appLock || s.privateAnswers
    ? base
    : `${base} It matters once App lock, or Windows Hello for memory lists and chat history, is on.`;
}

/** `where` is APPROVE_WHERE (jarvis-link.js), the one phrase for it. */
export function approvalsNote(where) {
  return `Risky only asks for ${RISKY_WORDS} - the same rule as the phone's ` +
    "fingerprint check. Every approval asks every time. There is nothing below " +
    `Risky only. Cards are still approved ${where}; on this PC, Windows Hello ` +
    "checks it is you before an approval counts. For a risky one, an " +
    "up-to-date Jarvis backend asks itself, so you are asked once, and a " +
    "program that goes around this app is asked too. With no Windows Hello set up, risky " +
    "approvals are refused. Deny never asks, and a notification can deny but " +
    "never approve.";
}

export function privateDetail() {
  return "The Brain's memory lists - what Jarvis knows about you, and facts " +
    "waiting for you - and your chat history stay hidden until you press Show " +
    "and pass Windows Hello. " +
    "The Galaxy picture and answers in the Jarvis bar are not hidden.";
}

/** One sentence for what is now stored. */
export function savedLine(prev, next) {
  const a = normalise(prev);
  const b = normalise(next);
  if (a.appLock !== b.appLock) return b.appLock ? "App lock is on." : "App lock is off.";
  if (a.relockAfterSecs !== b.relockAfterSecs) {
    const choice = RELOCK_CHOICES.find((c) => c.id === b.relockAfterSecs);
    return b.relockAfterSecs === 0
      ? "Jarvis locks again as soon as you leave it."
      : `Jarvis locks again after ${choice.label} away.`;
  }
  if (a.approvals !== b.approvals) {
    return b.approvals === "every"
      ? "Every approval now asks Windows Hello."
      : "Only risky approvals ask Windows Hello now.";
  }
  if (a.privateAnswers !== b.privateAnswers) {
    return b.privateAnswers
      ? "The Brain's memory lists and chat history are hidden until you press Show."
      : "The Brain's memory lists and chat history are shown without asking.";
  }
  return "Nothing changed.";
}
