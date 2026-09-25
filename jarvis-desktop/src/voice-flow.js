/**
 * The voice flow on this PC (docs/JARVIS-API.md section 17): interrupting
 * Jarvis by talking, "One moment." when a tool starts, and a small "I heard
 * you" sound. The rules here are pure - no Tauri, no audio - so they are
 * tested (tests/voice-flow.mjs), and they are the phone's rules word for
 * word (jarvis-client voice/VoiceFlow.kt): both apps are held to one list of
 * cases, tests/fixtures/voice-flow-cases.json.
 *
 * INTERRUPTING BY TALKING - "pause first, decide second" (LiveKit agents'
 * shape, voice/agent_activity.py; the voice research of 2026-09-24,
 * recommendation 4). While Jarvis speaks and this PC listens for "hey
 * Jarvis", voice.rs tells the Jarvis bar when half a second of speech has
 * been heard (`voice-barge-onset`). The bar PAUSES the reply at once - it
 * does not keep talking over the owner for the two seconds the check needs -
 * and asks voice.rs to send about two seconds of that speech to the PC
 * (`source=barge_in`). The PC answers one question: was it the owner (or
 * the word "stop")? Yes: the reply stops for good, and a sentence already
 * made ahead is thrown away. No: the reply carries on from where it paused.
 * No answer within `WAIT_MAX_MS` of pausing: it carries on too.
 *
 * The first `GRACE_MS` of a reply are ignored: that is when the echo
 * canceller is still learning the room and Jarvis's own voice is most
 * likely to come back through the microphone (kyutai unmute waits 3 s for
 * the same reason). "Stop" is not affected by that: the stop word has its
 * own path (the PC answers `stop: true` to a short clip) and works from the
 * first word.
 *
 * "ONE MOMENT." Played when a tool starts (the `step` event with
 * `tool_started` - the same events the private-answer rule watches), at
 * most once per spoken question, and only before the reply has made any
 * sound: never over the reply, never after "stop". Not on a flat one-second
 * timer, which at today's speeds would fire on almost every spoken turn
 * (section 17, 3).
 *
 * "I HEARD YOU." A tiny two-note sound, made here from numbers (no file, no
 * new dependency), played when the owner's turn has been cut: on letting go
 * of the talk button, and when the PC says "hey Jarvis" was heard. The phone
 * makes the same sound from the same numbers.
 *
 * @module voice-flow
 */

/** The first part of a reply that talking over is ignored for (echo). */
export const GRACE_MS = 3000;
/** Speech heard before the reply is paused (voice.rs `BARGE_ONSET`). */
export const ONSET_MS = 500;
/** About this much speech goes to the PC (voice.rs `BARGE_CLIP`). */
export const CLIP_MS = 2000;
/** Paused and no answer from the PC this long: carry on talking. */
export const WAIT_MAX_MS = 4000;

export const NONE = "none";
export const PAUSE = "pause";
export const RESUME = "resume";
export const STOP = "stop";

/**
 * Interrupting by talking, as a small state machine. Every method takes the
 * time it happened at (`now`, milliseconds on one clock) and returns what
 * to do: `NONE`, `PAUSE`, `RESUME` or `STOP`.
 */
export function createInterruptFlow() {
  let replyStartedAt = null;
  let pausedAt = null;
  let asked = null;
  return {
    /** The reply made its first sound (the first clip started playing). */
    replyStarted(now) {
      if (replyStartedAt === null) replyStartedAt = now;
    },
    /** The reply is over, stopped, or a new question was asked. */
    replyEnded() {
      replyStartedAt = null;
      pausedAt = null;
      asked = null;
    },
    /** Paused, waiting for the PC's answer. */
    paused() {
      return pausedAt !== null;
    },
    /**
     * Half a second of speech was heard, clip `id`. `allowed`: the switch
     * is on, the PC says it can tell the owner's voice now, and the link is
     * not stale. PAUSE means: pause the reply and have that clip checked.
     */
    onset(now, id, allowed) {
      if (!allowed || pausedAt !== null || replyStartedAt === null) return NONE;
      if (now - replyStartedAt < GRACE_MS) return NONE;
      pausedAt = now;
      asked = id;
      return PAUSE;
    },
    /** The PC's answer for clip `id`: `stop` true when it was the owner or "stop". */
    verdict(id, stop) {
      if (asked === null || asked !== id) return NONE;
      asked = null;
      if (stop === true) {
        replyStartedAt = null;
        pausedAt = null;
        return STOP;
      }
      if (pausedAt === null) return NONE;
      pausedAt = null;
      return RESUME;
    },
    /** Time passing: paused too long with no answer means carry on. */
    tick(now) {
      if (pausedAt === null || now - pausedAt < WAIT_MAX_MS) return NONE;
      pausedAt = null;
      return RESUME;
    },
  };
}

/**
 * "One moment.", at most once per spoken question. `toolStarted` says
 * whether to play it now.
 */
export function createMomentFlow() {
  let active = false;
  let played = false;
  let replied = false;
  let stopped = false;
  return {
    /** A spoken question was sent. */
    turnStarted() {
      active = true;
      played = false;
      replied = false;
      stopped = false;
    },
    /** A typed question replaced it, or the turn is over. */
    turnEnded() {
      active = false;
    },
    /** The reply made its first sound. */
    replyStarted() {
      replied = true;
    },
    /** "Stop", or an interruption that stopped the reply. */
    stopped() {
      stopped = true;
    },
    /** A tool started. `enabled`: the owner's switch and the PC's; `ready`: the clip is here. */
    toolStarted(enabled, ready) {
      if (!active || played || replied || stopped || !enabled || !ready) return false;
      played = true;
      return true;
    },
  };
}

/**
 * Where the owner cut the last spoken answer off (section 17, 6): the
 * sentence they heard last, handed to the NEXT question - typed or spoken -
 * as `interrupted` on its user message, so the PC can tell its model the
 * answer was cut off there. Once only, and only within `CUT_OFF_KEEP_MS`.
 * The phone's `CutOff`.
 */
export const CUT_OFF_KEEP_MS = 120000;

export function createCutOff(keepMs = CUT_OFF_KEEP_MS) {
  let said = null;
  let at = 0;
  return {
    /** The owner stopped the answer while `sentence` was the last one heard. */
    cut(sentence, now) {
      const s = typeof sentence === "string" ? sentence.trim() : "";
      if (!s) return;
      said = s;
      at = now;
    },
    /** The sentence for the question being sent now, or null - forgotten either way. */
    take(now) {
      const s = said;
      said = null;
      return s !== null && now - at <= keepMs ? s : null;
    },
  };
}

/** Whether a `step` event's `data` says a tool is starting. */
export function isToolStart(data) {
  return Boolean(data && typeof data === "object" && data.phase === "tool_started");
}

/**
 * What the PC's `/api/voice/status` `flow` block allows, read defensively:
 * an older PC (no `flow`) allows nothing - never send `source=barge_in` to
 * it (section 17: an older PC would transcribe the clip).
 */
export function flowFromStatus(status) {
  const flow = status && typeof status === "object" && status.flow && typeof status.flow === "object"
    ? status.flow
    : null;
  const barge = flow && flow.barge_in && typeof flow.barge_in === "object" ? flow.barge_in : {};
  const moment = flow && flow.moment && typeof flow.moment === "object" ? flow.moment : {};
  const on = Boolean(flow && flow.available === true);
  return {
    bargeIn: on && barge.enabled === true && barge.available === true,
    bargeInWhy: typeof barge.why === "string" ? barge.why : "",
    moment: on && moment.enabled === true,
    momentReady: on && moment.enabled === true && moment.ready === true,
    momentKey: typeof moment.key === "string" ? moment.key : "",
    // 2026-09-25: the PC keeps listening after a question, and reads
    // `interrupted` and keeps it on the PC. Neither is sent to an older PC.
    afterQuestion: on && flow.after_question === true,
    cutOff: on && flow.cut_off === true,
  };
}

/* ── The "One moment." switch - this PC's own, like "Interrupt Jarvis while it talks" ── */

/** The localStorage key. */
export const MOMENT_KEY = "jarvis.voice.oneMoment";

/** The switch's name, the words JARVIS-API section 17 suggests - the phone's too. */
export const MOMENT_NAME = "Say \"One moment\" if I'm kept waiting";

/** The owner's setting, or ON when none was saved (or storage is unreadable). */
export function loadMoment(storage = globalThis.localStorage) {
  try {
    if (storage && storage.getItem(MOMENT_KEY) === "off") return false;
  } catch {
    /* private mode or cleared site data: the default */
  }
  return true;
}

/** Saves the setting. Returns whether it could be saved. */
export function saveMoment(on, storage = globalThis.localStorage) {
  try {
    if (!storage) return false;
    storage.setItem(MOMENT_KEY, on ? "on" : "off");
    return true;
  } catch {
    return false;
  }
}

/** The switch's line in Settings - the phone's `OneMoment.describe`, word for word. */
export function describeMoment(on) {
  // One literal each: the phone's VoiceFlowTest finds these very lines here.
  return on
    ? "On: when Jarvis has to look something up for a spoken question, it says \"One moment.\" first, once, in its own voice."
    : "Off: Jarvis stays quiet until its answer is ready.";
}

/* ── "I heard you" ── */

/** The sound's numbers, the phone's `HeardSound` numbers. */
export const HEARD_SOUND = Object.freeze({
  rate: 24000,
  tones: Object.freeze([Object.freeze({ hz: 660, ms: 55 }), Object.freeze({ hz: 990, ms: 75 })]),
  gapMs: 25,
  fadeMs: 10,
  gain: 0.16,
});

/** The sound as 16-bit samples: each note a sine with short fades, a gap between. */
export function heardSoundSamples(spec = HEARD_SOUND) {
  const rate = spec.rate;
  const fade = Math.round((rate * spec.fadeMs) / 1000);
  const gap = Math.round((rate * spec.gapMs) / 1000);
  const out = [];
  spec.tones.forEach((tone, i) => {
    if (i > 0) for (let k = 0; k < gap; k += 1) out.push(0);
    const n = Math.round((rate * tone.ms) / 1000);
    for (let k = 0; k < n; k += 1) {
      const edge = Math.min(1, k / fade, (n - 1 - k) / fade);
      const v = Math.sin((2 * Math.PI * tone.hz * k) / rate) * spec.gain * Math.max(0, edge);
      out.push(Math.round(v * 32767));
    }
  });
  return Int16Array.from(out);
}

/** A mono 16-bit WAV of `samples` at `rate`, as bytes. */
export function wavBytes(samples, rate) {
  const data = samples.length * 2;
  const buf = new ArrayBuffer(44 + data);
  const v = new DataView(buf);
  const text = (at, s) => [...s].forEach((c, i) => v.setUint8(at + i, c.charCodeAt(0)));
  text(0, "RIFF");
  v.setUint32(4, 36 + data, true);
  text(8, "WAVE");
  text(12, "fmt ");
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true);
  v.setUint16(22, 1, true);
  v.setUint32(24, rate, true);
  v.setUint32(28, rate * 2, true);
  v.setUint16(32, 2, true);
  v.setUint16(34, 16, true);
  text(36, "data");
  v.setUint32(40, data, true);
  samples.forEach((s, i) => v.setInt16(44 + i * 2, s, true));
  return new Uint8Array(buf);
}

/** The "I heard you" sound as a `data:audio/wav` URI, for `new Audio()`. */
export function heardSoundUri() {
  const bytes = wavBytes(heardSoundSamples(), HEARD_SOUND.rate);
  let bin = "";
  bytes.forEach((b) => {
    bin += String.fromCharCode(b);
  });
  return `data:audio/wav;base64,${btoa(bin)}`;
}
