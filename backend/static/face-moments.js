/**
 * What just happened, for the animal faces in the other windows (the new
 * behaviours, owner 2026-09-28; docs/CRITTERS.md "What each app feeds them").
 *
 * Three of the new behaviours answer something Jarvis did:
 *  - a small NOD when a fact is saved (the `memory_saved` event) - never
 *    while App lock or "Hide memory lists and chat history" is on (the
 *    owner's rule);
 *  - a GLOW when a long answer is ready (the `deep` event, `state: "done"`);
 *  - the FOCUS BUDDY while a focus session runs, and a stretch as it ends
 *    (the `focus` event: `started` / `changed` / `ended`).
 * Every face that shows them is a `faces.html?mode=display&feed=parent`
 * frame (the Widget's tray, the floating face, the HUD), and Tauri delivers
 * an event to a window's top-level page, never to a frame inside it - so,
 * exactly as face-voice.js does for the voice, each of those windows passes
 * the moment into its frame by postMessage.
 *
 * What is passed is the KIND of thing and nothing else: never a fact's id or
 * words, never the question, never what a focus session is on. The events
 * themselves carry no words either (docs/JARVIS-API.md section 3).
 *
 * @module face-moments
 */

/** The postMessage type faces.html's display frame listens for. */
export const FACE_MOMENT_MESSAGE = "jarvis-face-moment";
/** Every frame off the server's event bus (lib.rs `events::JARVIS_EVENT`). */
export const BUS_EVENT = "jarvis-event";
/** The Security settings changed (lib.rs `events::SECURITY_CHANGED`). */
export const SECURITY_EVENT = "security-changed";
/** The two yes/no lock answers before the first change (commands.rs). */
export const LOCK_COMMAND = "get_lock_flags";
/** How many saved fact ids are remembered, so a replayed event never nods twice. */
export const SEEN_MAX = 200;

/**
 * Whether a fact's nod must be held back: App lock or "Hide memory lists
 * and chat history" is on - or it is not known yet (fails closed).
 */
export function quietOf(lock) {
  if (!lock || typeof lock !== "object") return true;
  return lock.appLock !== false || lock.privateAnswers !== false;
}

/**
 * The moment one bus frame is, or null. `quiet`: facts do not nod. `seen`:
 * a Set of fact ids already nodded for (a reconnect may replay an event);
 * it is added to.
 */
export function momentOf(frame, quiet, seen) {
  if (!frame || typeof frame !== "object") return null;
  const d = frame.data && typeof frame.data === "object" ? frame.data : {};
  if (frame.kind === "memory_saved") {
    const ids = Array.isArray(d.ids) ? d.ids.filter((x) => typeof x === "number" || typeof x === "string") : [];
    let fresh = 0;
    for (const id of ids) {
      if (seen && seen.has(id)) continue;
      fresh += 1;
      if (seen) {
        seen.add(id);
        while (seen.size > SEEN_MAX) seen.delete(seen.values().next().value);
      }
    }
    return fresh > 0 && !quiet ? { kind: "fact" } : null;
  }
  if (frame.kind === "deep") return d.state === "done" ? { kind: "glow" } : null;
  if (frame.kind === "focus") {
    if (d.state === "started" || d.state === "changed") return { kind: "focus", on: true };
    if (d.state === "ended") return { kind: "focus", on: false };
  }
  return null;
}

/**
 * Passes the moments into one face frame, for a window that shows one.
 *
 * - `frame`  the `<iframe>` holding `faces.html?mode=display&feed=parent`.
 * - `listen` the window's own `(event, handler)` subscriber (Tauri's).
 * - `invoke` the window's Tauri `invoke`, to read the lock answers once;
 *            without one, facts do not nod until a `security-changed` says
 *            both switches are off.
 *
 * A frame that loads (the Widget loads its face only when expanded) is told
 * whether a focus session is on, as far as this window has heard.
 */
export function relayFaceMoments(frame, listen, invoke) {
  if (!frame || typeof listen !== "function") return;
  let lock = null;       // unknown: a saved fact does not nod
  let heard = false;     // a security-changed has arrived
  let focusOn = null;    // unknown until a focus event
  const seen = new Set();
  const post = (m) => {
    const w = frame.contentWindow;
    if (!w) return;
    try {
      // "/" = this page's own origin - the only sender faces.html accepts.
      w.postMessage({ type: FACE_MOMENT_MESSAGE, ...m }, "/");
    } catch (error) {
      /* the frame is mid-navigation; nothing is lost but one small nod */
    }
  };
  listen(SECURITY_EVENT, (event) => {
    const p = event && event.payload;
    if (p && typeof p === "object") {
      lock = { appLock: p.appLock === true, privateAnswers: p.privateAnswers === true };
      heard = true;
    }
  });
  if (typeof invoke === "function") {
    Promise.resolve()
      .then(() => invoke(LOCK_COMMAND))
      .then((v) => {
        if (!heard && v && typeof v === "object") {
          lock = { appLock: v.appLock === true, privateAnswers: v.privateAnswers === true };
        }
      })
      .catch(() => { /* an older app: facts stay quiet until the settings change */ });
  }
  listen(BUS_EVENT, (event) => {
    const m = momentOf(event && event.payload, quietOf(lock), seen);
    if (!m) return;
    if (m.kind === "focus") focusOn = m.on;
    post(m);
  });
  frame.addEventListener("load", () => {
    if (focusOn === true) post({ kind: "focus", on: true });
  });
}
