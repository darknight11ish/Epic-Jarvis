/**
 * The desktop's Incognito mode - private chat, owner-approved 2026-10-26.
 * The owner's decision of 2026-10-27 made this the bar's ONE Incognito chip:
 * the old temporary-chat button left the DOM and its milder mode collapsed
 * into this stricter one. The capability, the server route and the
 * `private_chat` behaviour are untouched; only the words moved from
 * "Private chat" to "Incognito" so the chip, its title, its strip and its
 * announcements cannot say two different things.
 *
 * An Incognito turn is a temporary chat PLUS a strict zero-write promise
 * (backend/private-chat.patch, backend/jarvis_private_chat.py,
 * docs/JARVIS-API.md section 156): nothing is recalled or learned, nothing is
 * kept, every disk write is refused, and no tool runs at all - so no card, no
 * receipt and no action can come out of it. The PC must advertise
 * `capabilities.private_chat`; when it does not, the mode stays off and says
 * why rather than silently downgrading the turn to an ordinary chat.
 *
 * This module owns the mode's words and the toggle's state machine only.
 * main.js owns the conversation and the transport: `private.toggle()` from the
 * chip, `private.on` for the request's `private` flag, `private.paint(empty)`
 * whenever the conversation empties or fills, and `offQuietly()` when a kept
 * chat takes over.
 */

export const PRIVATE_LABEL = "Incognito";
export const PRIVATE_LINE =
  "Incognito: Jarvis won't use or learn from your memory, keeps nothing, and won't run tools or change anything.";
export const PRIVATE_ON_TITLE =
  "Start an incognito chat: Jarvis won't use memory, keep anything, or run tools";
export const PRIVATE_OFF_TITLE = "End the incognito chat and start a normal one";
export const PRIVATE_STARTED =
  "Incognito chat started. Jarvis won't use memory, keep anything, or run tools.";
export const PRIVATE_ENDED = "Incognito chat ended. Your next question starts a normal chat.";
export const PRIVATE_UNAVAILABLE =
  "Incognito isn't available on this PC's version of Jarvis, so nothing was sent. " +
  "Run apply-patches.ps1 on the PC to update it.";
export const PRIVATE_NOT_CONFIRMED =
  "Your PC did not confirm this was an incognito chat, so this answer may have used your " +
  "memory, kept something, or run a tool.";
export const CONTINUED_PRIVATE_OFF = "Incognito is off: a continued chat is kept.";

/** The strip already says "Incognito" beside the line, so the line does not repeat it. */
const PRIVATE_STRIP_LINE = PRIVATE_LINE.replace(/^Incognito:\s*/, "");

const errorText = (e) => String((e && e.message) || e || "It did not work.");

/**
 * The Private chip, its marker strip, and the PC's yes/no.
 *
 * `check()` resolves true only when the PC advertises private chat
 * (commands.rs private_chat_available); `restart()` starts a new conversation;
 * `onTurnOn()` turns the other mode (Temporary) off without a second restart;
 * `offQuietly()` turns this one off without announcing or restarting, for when
 * a kept chat or the other mode takes over.
 */
export function createPrivateToggle({
  button, strip, line, refused, root, check, restart, busy, announce, onChange, onTurnOn,
}) {
  const p = {
    on: false,
    checking: false,
    /** Turn off without a restart, an announcement or a chat-ended note. */
    offQuietly() {
      if (!p.on) return;
      p.on = false;
      refused.hidden = true;
      p.paint(true);
    },
    async toggle() {
      if (p.checking || busy()) return;
      if (p.on) {
        p.on = false;
        refused.hidden = true;
        restart();
        announce(PRIVATE_ENDED);
        p.paint(true);
        return;
      }
      p.checking = true;
      button.disabled = true;
      let ok = false;
      let why = PRIVATE_UNAVAILABLE;
      try {
        ok = (await check()) === true;
      } catch (error) {
        why = errorText(error);
      }
      p.checking = false;
      button.disabled = false;
      if (!ok) {
        // Never pretend: the mode stays off and says why in plain words.
        refused.textContent = why;
        refused.hidden = false;
        strip.hidden = false;
        strip.dataset.state = "refused";
        announce(why, "assertive");
        onChange();
        return;
      }
      onTurnOn?.();
      p.on = true;
      refused.hidden = true;
      restart();
      announce(PRIVATE_STARTED);
      p.paint(true);
    },
    /** `empty`: the conversation has nothing in it yet - the one line. */
    paint(empty) {
      // A refusal is said until the next question is asked.
      if (!empty) refused.hidden = true;
      button.setAttribute("aria-pressed", String(p.on));
      button.title = p.on ? PRIVATE_OFF_TITLE : PRIVATE_ON_TITLE;
      root.dataset.private = String(p.on);
      if (p.on) {
        strip.dataset.state = "on";
        strip.hidden = false;
        line.textContent = empty ? PRIVATE_STRIP_LINE : "";
        line.hidden = !empty;
      } else if (refused.hidden) {
        strip.hidden = true;
        line.textContent = "";
      }
      onChange();
    },
  };
  return p;
}
