/**
 * Filing a note in Logseq, Joplin or Obsidian, and saying honestly how it
 * ended - and which of the three this PC is set up for.
 *
 * Shared by the widget's capture field and the quickbar's `#log` /
 * `#joplin` / `#obs` / Alt+Shift+N path. Both used to post a chat turn asking a model
 * to call tools that did not exist, and could only say "Sent" - the desktop
 * had no way to know whether a note landed.
 *
 * Now the owner's own words go to `/api/notes/capture` (backend
 * `note-capture.patch`) through the `capture_note` command, with no model
 * involved. The backend writes through the approval gate and answers with a
 * job whose `state` is one of:
 *
 *   filed       written, and read back   -> "Filed in Logseq, journals/…"
 *   waiting     an approval card is up   -> keep asking `capture_note_status`
 *   not_filed   said no / nobody answered / refused, with the reason
 *   failed      could not be written, with the reason
 *
 * Every sentence shown comes from the server's `message`. Nothing here
 * decides a note was filed on its own say-so.
 */

/** How often to ask while a card is waiting, and for how long in total. */
export const POLL_MS = 2000;
/** A little over the gate's own 180-second approval timeout. */
export const GIVE_UP_MS = 200000;

/**
 * The three note apps, in the backend's order. `setUp` is what to do on the
 * PC when one is not set up - plain words, pointing at docs/INSTALL.md.
 */
export const TARGETS = {
  logseq: {
    name: "Logseq",
    prefix: "#log",
    setUp: "Set [notes.logseq] graph_directory in jarvis-framework.toml (docs/INSTALL.md, Notes).",
  },
  joplin: {
    name: "Joplin",
    prefix: "#jop",
    setUp: "Put Joplin's Web Clipper token in JARVIS_JOPLIN_TOKEN (docs/INSTALL.md, Notes).",
  },
  obsidian: {
    name: "Obsidian",
    prefix: "#obs",
    setUp: "Set [notes.obsidian] vault_directory in jarvis-framework.toml (docs/INSTALL.md, Notes).",
  },
};

/** The display name of a target ("obsidian" -> "Obsidian"). */
export function targetName(target) {
  return (TARGETS[target] && TARGETS[target].name) || "Logseq";
}

/**
 * Reads the backend's answer to "which note apps are set up?" - the
 * `note_targets` command, `GET /api/notes/capture` with no id. Returns
 * `{ known: true, targets: [...] }`, keeping only names this app knows, or
 * `{ known: false, why }` when the answer is not that list. Never guesses a
 * list: a window that cannot tell shows no target, and says why.
 */
export function readTargets(answer) {
  const list = answer && Array.isArray(answer.targets) ? answer.targets : null;
  if (!list) {
    return {
      known: false,
      why: "the PC's answer did not say which note apps are set up",
    };
  }
  return { known: true, targets: Object.keys(TARGETS).filter((t) => list.includes(t)) };
}

/** Asks the PC. Resolves to `readTargets`' shape; a failed request is `known: false`. */
export async function loadTargets(invoke) {
  try {
    return readTargets(await invoke("note_targets"));
  } catch (error) {
    return { known: false, why: String((error && error.message) || error) };
  }
}

/** Said when a target the owner picked by hand is not set up on the PC. */
export function notSetUp(target) {
  const t = TARGETS[target];
  return `${targetName(target)} isn't set up on your PC, so nothing was filed. ${t ? t.setUp : ""}`.trim();
}

/** One line for when the list is unknown or empty - never "all of them". */
export function noTargetsLine(state) {
  if (!state || !state.known) {
    return `Couldn't check which note apps are set up on your PC: ${
      (state && state.why) || "no answer yet"}.`;
  }
  return "No note app is set up on your PC yet - see docs/INSTALL.md, Notes.";
}

/** Words for one job, as `{ text, tone, final }`. `tone` is "ok" | "bad" | null. */
export function describeJob(job, where) {
  const place = targetName(where);
  const state = job && job.state;
  const said = job && typeof job.message === "string" && job.message.trim();
  if (state === "filed") {
    return { text: said || `Filed in ${place}.`, tone: "ok", final: true };
  }
  if (state === "waiting") {
    return {
      text: `Waiting for your approval to file this in ${place}…`,
      tone: null,
      final: false,
    };
  }
  if (state === "not_filed" || state === "failed") {
    return { text: said || `Not filed in ${place}.`, tone: "bad", final: true };
  }
  return {
    text: `The PC answered, but did not say whether the note was filed. Check ${place}.`,
    tone: "bad",
    final: true,
  };
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Files one note and follows it to the end.
 *
 * `invoke(command, args)` is the Tauri bridge (rejecting on failure).
 * `onUpdate({ text, tone, final })` is called with every change - first the
 * immediate answer, then, if a card is waiting, each later answer until it is
 * final or GIVE_UP_MS passes. Resolves with the last description.
 */
export async function fileNote(invoke, target, text, onUpdate, opts = {}) {
  const pollMs = opts.pollMs ?? POLL_MS;
  const giveUpMs = opts.giveUpMs ?? GIVE_UP_MS;
  const where = TARGETS[target] ? target : "logseq";
  let job = await invoke("capture_note", { target: where, text });
  let said = describeJob(job, where);
  onUpdate(said);
  const started = Date.now();
  while (!said.final && job && job.id) {
    if (Date.now() - started > giveUpMs) {
      said = {
        text: "Still waiting for approval. Nothing is filed until you answer the card.",
        tone: null,
        final: true,
      };
      onUpdate(said);
      break;
    }
    await sleep(pollMs);
    try {
      job = await invoke("capture_note_status", { id: String(job.id) });
    } catch (error) {
      said = {
        text: `Lost track of the note (${String((error && error.message) || error)}). ` +
          "Check the approval card and your notes app.",
        tone: "bad",
        final: true,
      };
      onUpdate(said);
      break;
    }
    const next = describeJob(job, where);
    if (next.text !== said.text || next.final) onUpdate(next);
    said = next;
  }
  return said;
}
