/**
 * Settings -> Jarvis's voice: custom voices, in words, with no page in them
 * (tests/custom-voices.mjs checks every sentence against the backend's real
 * GET /api/voice/voices and POST answers in tests/fixtures/
 * voice-training-cases.json).
 *
 * docs/JARVIS-API.md section 15. Jarvis can speak in a voice the owner
 * recorded: a sentence Jarvis shows, read aloud (the words ARE the shown
 * sentence - this app transcribes nothing), or a WAV file with its words
 * typed in. Adding a voice and switching to one each raise ONE approval
 * card; going back to the built-in voice and deleting a voice are
 * immediate. The better voice on the second graphics card is its own
 * switch: ON a card, OFF at once. A recording that sounds like the owner
 * is refused - Jarvis speaking in the owner's voice could pass its own "is
 * it the owner?" check.
 *
 * The server's sentences (`why`, `error`, `fallback`) are written for the
 * owner and are shown as they are, first letter raised.
 *
 * @module custom-voices
 */

const obj = (v) => (v && typeof v === "object" && !Array.isArray(v) ? v : {});
const yes = (v) => v === true;
const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : 0);

/** The server's own sentence, first letter up, one full stop. */
export function sentence(text) {
  const s = String(text || "").trim().replace(/[.\s]+$/, "");
  return s ? `${s.charAt(0).toUpperCase()}${s.slice(1)}.` : "";
}

/** What makes the sound, in words. */
export const ENGINES = Object.freeze({
  kokoro: "the built-in voice",
  zipvoice: "the chosen voice, made on this PC's processor",
  f5: "the better voice, made on the second graphics card",
  none: "nothing - no voice could speak",
});

/** Which voice Jarvis speaks in, and what makes the next sentence. */
export function speakingLine(status) {
  const st = obj(status);
  const name = String(st.active_name || "").trim() || "Built-in voice";
  const engine = ENGINES[st.speaking_with] || "";
  const who = st.active === "builtin" || !st.active ? "its built-in voice" : `"${name}"`;
  return `Jarvis speaks in ${who}.${engine && st.active !== "builtin" ? ` The next sentence is made with ${engine}.` : ""}`;
}

/** Why the built-in voice is used instead of the chosen one, or null. */
export function fallbackLine(status) {
  const why = String(obj(status).fallback || "").trim().replace(/\.$/, "");
  return why ? `Jarvis is using its built-in voice instead, because ${why}.` : null;
}

/** A card waiting to add a voice or switch to one, or null. */
export function pendingLine(status, approveWhere) {
  const p = obj(status).pending;
  if (!p || typeof p !== "object") return null;
  const name = String(p.name || p.voice || "").trim();
  if (p.kind === "create") {
    return `Waiting for your approval to add "${name}". Approve it ${approveWhere} — nothing is kept until you do.`;
  }
  return `Waiting for your approval to speak in "${name}". Approve it ${approveWhere} — nothing changes until you do.`;
}

/** How the last voice card ended - the server's own sentence - or null. */
export function lastLine(status) {
  const l = obj(status).last;
  if (!l || typeof l !== "object") return null;
  return sentence(l.why) || null;
}

/**
 * One row per voice for the list: `{id, name, detail, tone, builtin,
 * ready, active}`. A custom voice says how long its recording is; a voice
 * that cannot be used says why.
 */
export function voiceRows(status) {
  const st = obj(status);
  const rows = Array.isArray(st.voices) ? st.voices : [];
  return rows.filter((v) => v && typeof v.id === "string" && v.id).map((v) => {
    const builtin = yes(v.builtin) || v.id === "builtin";
    const ready = yes(v.ready);
    let detail;
    if (!ready) {
      detail = `Cannot be used: ${String(v.why || "it is not ready").trim().replace(/\.$/, "")}.`;
    } else if (builtin) {
      detail = "Jarvis's own voice. Always there to fall back on.";
    } else {
      detail = `A ${num(v.seconds).toFixed(1)}-second recording.`;
    }
    return {
      id: v.id,
      name: String(v.name || v.id),
      detail,
      tone: ready ? "" : "warn",
      builtin,
      ready,
      active: st.active === v.id,
    };
  });
}

/** The better voice's switch, in words: `{show, on, waiting, canTurnOn, lines}`. */
export function betterView(status, approveWhere) {
  const b = obj(obj(status).better_voice);
  if (!Object.keys(b).length) return { show: false, on: false, waiting: false, canTurnOn: false, lines: [] };
  const on = yes(b.enabled);
  const waiting = !on && yes(b.pending);
  const canTurnOn = yes(b.can_turn_on);
  const lines = [];
  if (waiting) {
    lines.push({ text: `Waiting for your approval to turn it on. Approve it ${approveWhere} — nothing changes until you do.`, tone: "waiting" });
  }
  if (b.why) lines.push({ text: sentence(b.why), tone: canTurnOn ? "" : "why" });
  if (on || waiting) {
    const state = { off: "Off", loading: "Loading", ready: "Ready", failed: "Failed" }[b.state] || "";
    if (state) lines.push({ text: `${state}: ${sentence(b.state_why) || "no reason given."}`, tone: b.state === "failed" ? "why" : "" });
    // The files' reason, unless the state line has just said it.
    if (b.files === false && b.files_why && String(b.state_why || "").trim() !== String(b.files_why).trim()) {
      lines.push({ text: sentence(b.files_why), tone: "why" });
    }
  }
  const last = obj(b.last);
  if (last.why) lines.push({ text: sentence(last.why), tone: "" });
  // The switch is offered only with a capable second card (the doc's
  // "offer the switch only when can_turn_on"), and while it is on or its
  // card waits, so it can always be turned off.
  return { show: canTurnOn || on || waiting, on, waiting, canTurnOn, lines };
}

/** One line per recent say() (`timings`, oldest first): newest first, at most `n`. */
export function timingLines(status, n = 5) {
  const rows = Array.isArray(obj(status).timings) ? obj(status).timings : [];
  return rows.slice(-n).reverse().map((t) => {
    const r = obj(t);
    if (r.engine === "none") {
      return `Nothing was said: ${String(r.failed || "no voice could speak").trim().replace(/\.$/, "")}.`;
    }
    const what = ENGINES[r.engine] || "a voice";
    let line = `${what.charAt(0).toUpperCase()}${what.slice(1)}: ${num(r.seconds).toFixed(1)} s to make ${num(r.audio_seconds).toFixed(1)} s of speech (${Math.round(num(r.chars))} characters).`;
    const fb = String(r.fallback || "").trim().replace(/\.$/, "");
    if (fb) line += ` The chosen voice was not used, because ${fb}.`;
    const note = String(r.note || "").trim();
    if (note) line += ` ${sentence(note)}`;
    return line;
  });
}

/** The sentence to show while recording, from the server's list. */
export function sentenceToRead(status, index) {
  const list = (Array.isArray(obj(status).sentences) ? obj(status).sentences : [])
    .filter((s) => typeof s === "string" && s.trim());
  if (!list.length) return "";
  const i = ((Number(index) || 0) % list.length + list.length) % list.length;
  return list[i];
}

/** The server's limits for a voice, with its own numbers when missing. */
export function voiceLimits(status) {
  const l = obj(obj(status).limits);
  return {
    minSeconds: num(l.min_seconds) || 3,
    maxSeconds: num(l.max_seconds) || 10,
    maxName: num(l.max_name_chars) || 40,
    maxWords: num(l.max_transcript_chars) || 300,
    maxBytes: num(l.max_clip_bytes) || 2900000,
    maxVoices: num(l.max_voices) || 20,
  };
}

/**
 * Why "Add this voice" cannot be pressed, or null. `way` is "record" or
 * "file"; `recording` is the held recording's `{seconds, peak}`; `file`
 * `{name, size}`. The server checks everything again.
 */
export function addBlocker({ way, name, words, recording, file, linkBlocker, status }) {
  const lim = voiceLimits(status);
  const n = String(name || "").trim();
  if (linkBlocker) return linkBlocker;
  if (!n) return "Give the voice a name.";
  if (n.length > lim.maxName) return `The name is ${n.length} characters; the most is ${lim.maxName}.`;
  if (way === "file") {
    if (!file) return "Choose a WAV file.";
    if (!/\.wav$/i.test(String(file.name || ""))) return "That is not a WAV file. Choose a file ending in .wav.";
    if (num(file.size) > lim.maxBytes) return `That file is too big; the most is ${(lim.maxBytes / 1e6).toFixed(1)} MB. Use a clip of ${lim.maxSeconds} seconds at most.`;
    const w = String(words || "").trim();
    if (!w) return "Type exactly what is said in the recording.";
    if (w.length > lim.maxWords) return `The words are ${w.length} characters; the most is ${lim.maxWords}.`;
    return null;
  }
  const r = obj(recording);
  if (!recording) return "Record the sentence first.";
  if (num(r.peak) < 0.02) return "That was silent. Check the microphone, then record it again.";
  if (num(r.seconds) < lim.minSeconds) return `That was too short. Read the whole sentence; it needs ${lim.minSeconds} to ${lim.maxSeconds} seconds.`;
  return null;
}

/** The plain sentence for a recording that sounds like the owner. */
export const OWNER_VOICE = "This sounds like you, so Jarvis won't copy it.";

/**
 * What the PC answered to adding, switching, deleting or the better voice,
 * in words: `{text, detail, tone, waiting}`. `detail` carries the server's
 * own sentence under a plain one.
 */
export function voiceReply(answer, approveWhere) {
  const a = obj(answer);
  if (a.refused === "owner_voice") {
    return { text: OWNER_VOICE, detail: sentence(a.error), tone: "bad", waiting: false };
  }
  if (a.refused === "owner_check_failed" || a.refused === "no_voice_check") {
    return {
      text: "Jarvis could not make sure this is not your own voice, so it won't copy it.",
      detail: sentence(a.error),
      tone: "bad",
      waiting: false,
    };
  }
  if (a.error) return { text: sentence(a.error), detail: "", tone: "bad", waiting: false };
  if (a.ok === true && a.pending === true) {
    return {
      text: `Waiting for your approval. Approve it ${approveWhere} — nothing changes until you do.`,
      detail: "",
      tone: "ok",
      waiting: true,
    };
  }
  if (a.ok === true && a.deleted) return { text: "Deleted.", detail: "", tone: "ok", waiting: false };
  if (a.ok === true) return { text: sentence(a.message) || "Done.", detail: "", tone: "ok", waiting: false };
  return { text: "Jarvis did not say whether it changed.", detail: "", tone: "bad", waiting: false };
}

/** The question asked before deleting a voice. */
export function deleteQuestion(row) {
  const r = obj(row);
  return `Delete the voice "${r.name}" for good? Its recording is deleted from your PC.${r.active ? " Jarvis goes back to its built-in voice." : ""}`;
}

/** Said beside "Add a voice", always. */
export const CONSENT =
  "Only add the voice of someone who has agreed to it. A recording that sounds like you is refused. The recording stays on your PC; nothing is sent anywhere else.";
