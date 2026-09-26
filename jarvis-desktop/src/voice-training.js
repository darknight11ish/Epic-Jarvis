/**
 * Settings -> Voice, training on this PC: the words and the rules, with no
 * page in them, so every sentence is tested against the backend's real
 * answers (tests/voice-training.mjs reads tests/fixtures/
 * voice-training-cases.json, made by tools/gen_voice_training_cases.py).
 *
 * What it covers (docs/JARVIS-API.md section 16):
 * - "Train my voice" on this PC's microphone: one round of 12 sentences at
 *   balanced, three rounds of the same 12 in different conditions at very
 *   strict, sent round by round with ONE approval card at the end; "Train
 *   more" adds instead of replacing; recordings the PC left out are
 *   recorded again. A PC too old for rounds gets today's single round.
 * - How strict the voice check is, and whether private answers may be read
 *   aloud: tightening at once, loosening only through a card.
 * - The guided test (20 sentences) and the "asked you to repeat" counts.
 * - Which voice-ID model very strict uses, and what to do when it is not
 *   the stronger one.
 *
 * The phone has the same screen (VoiceTraining.kt, VoiceTrainingScreen.kt);
 * where it has a sentence this uses it, with "tap" made "press" and "this
 * phone" made "this PC". The twelve sentences are the phone's, word for
 * word, so both microphones' prints are trained on the same words.
 *
 * Nothing here turns speech into text: the sentences are shown for the
 * owner to read, and nobody checks the words - only the voice.
 *
 * Every field is read defensively: anything missing reads as the refusing
 * answer, never as a guess.
 *
 * @module voice-training
 */

const obj = (v) => (v && typeof v === "object" && !Array.isArray(v) ? v : {});
const yes = (v) => v === true;
const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : 0);
const count = (v) => (Number.isInteger(v) && v > 0 ? v : 0);

/** The phone's twelve sentences (VoiceTraining.SENTENCES), word for word. */
export const SENTENCES = Object.freeze([
  "Hey Jarvis, what's on my calendar today?",
  "The quick brown fox jumps over the lazy dog.",
  "Please remind me to call my sister on Thursday.",
  "Hey Jarvis, turn the lights down a little.",
  "What is the weather going to be like this weekend?",
  "Six thick thistle sticks stood by the gate.",
  "Hey Jarvis, play some quiet music.",
  "I'd like a cup of tea with milk, no sugar.",
  "How long will it take to drive into town?",
  "Hey Jarvis, set a timer for ten minutes.",
  "My favourite colours are red, green and blue.",
  "Good morning, it's nice to hear your voice again.",
]);

/**
 * The guided test's twenty sentences: new ones, not the training's, so the
 * test measures how Jarvis hears the owner saying something it has not
 * learned. Each is a request of the kind the owner really makes, long
 * enough (about two to four seconds) to clear very strict's two seconds of
 * speech when read at an ordinary pace.
 *
 * THE ONE LIST (2026-09-24): the phone's `StrictVoice.MEASURE_SENTENCES`
 * is a copy of this, word for word, so both apps' results are about the
 * same sentences. Change it here and there together; tests/voice-training
 * .mjs compares the two files.
 */
export const TEST_SENTENCES = Object.freeze([
  "Hey Jarvis, what time is my first meeting tomorrow?",
  "Can you read me the last message from my brother?",
  "Add bread, eggs and coffee to the shopping list.",
  "Hey Jarvis, how long until the next train into town?",
  "Remind me to water the plants on Saturday morning.",
  "What did I say I wanted to do this weekend?",
  "Turn the heating down by two degrees, please.",
  "Hey Jarvis, set an alarm for half past six.",
  "Find the notes I wrote about the garden last month.",
  "How much rain is forecast for the afternoon?",
  "Hey Jarvis, pause the music for a moment.",
  "Put the dentist in my calendar for next Tuesday.",
  "What was the name of that film we talked about?",
  "Hey Jarvis, tell me the headlines in one minute.",
  "Send me a reminder when I get home tonight.",
  "Is there anything I need to do before Friday?",
  "Hey Jarvis, start a timer for the pasta, eleven minutes.",
  "Read my calendar for the rest of the week, please.",
  "How far is it to the nearest petrol station?",
  "Hey Jarvis, thank you, that is everything for now.",
]);

/** The PC's limits (`gate.training.limits`), with the phone's numbers when missing. */
export function limits(status) {
  const l = obj(obj(obj(status).gate).training).limits;
  const lim = obj(l);
  return {
    minSeconds: num(lim.min_seconds) || 1.0,
    maxSeconds: num(lim.max_seconds) || 10.0,
    maxTotal: num(lim.max_total_seconds) || 80.0,
    minClips: count(lim.min_clips) || 3,
    rounds: count(lim.rounds) || 3,
    measureMax: count(lim.measure_max_clips) || 20,
    sessionMinutes: Math.round((num(lim.session_seconds) || 900) / 60),
  };
}

/** What the PC understands (`gate.training`'s flags). All false from an older PC. */
export function understands(status) {
  const t = obj(obj(obj(status).gate).training);
  return {
    training: yes(t.available),
    rounds: yes(t.rounds),
    settings: yes(t.settings),
    measure: yes(t.measure),
  };
}

/** The strictness the PC reports: "very_strict", "balanced", or "" when not reported. */
export function strictnessOf(status) {
  const s = String(obj(obj(status).gate).strictness || "");
  return s === "very_strict" || s === "balanced" ? s : "";
}

/** The server's words for each round (`round_asks`), with its own words when missing. */
const ROUND_ASKS = {
  1: "normal, close to the microphone",
  2: "further away from the microphone, or quieter",
  3: "at another time of day, or in another room",
};
export function roundAsk(status, round) {
  const asks = obj(obj(obj(obj(status).gate).training).round_asks);
  const said = asks[String(round)];
  return typeof said === "string" && said.trim() ? said.trim() : ROUND_ASKS[round] || "";
}

/**
 * Why training cannot start on this PC now, in words, or null when it can.
 * Before anything is recorded, so the owner does not read 36 sentences to
 * be refused at the end.
 */
export function trainingBlocker(status) {
  const st = obj(status);
  const gate = obj(st.gate);
  const training = obj(gate.training);
  if (st.available === false) return "The voice part of Jarvis is not running on your PC.";
  if (!yes(training.available)) {
    return "This PC's Jarvis cannot train a voice yet. Update the backend by running apply-patches.ps1, then open this again.";
  }
  const models = gate.models && typeof gate.models === "object" ? obj(gate.models) : null;
  const mode = String(gate.mode || "").trim().toLowerCase();
  if (models && !models.very_strict_model && !yes(gate.speaker_model) && mode !== "broad") {
    return "No voice-ID model is installed on your PC, so training cannot help yet: every voice is refused until it is. Install it first (the link above says how).";
  }
  if (yes(training.pending)) {
    return "A voice card is already waiting. Answer it first.";
  }
  const session = training.session && typeof training.session === "object" ? obj(training.session) : null;
  if (session && session.mic && session.mic !== "desktop") {
    return "Your phone is in the middle of a training. Finish it or cancel it on your phone first.";
  }
  return null;
}

/**
 * The plan for a training: which rounds, which sentences in each, and
 * whether it adds to the print or replaces it.
 *
 * - An older PC (no `rounds`): one round of all twelve, sent the old way.
 * - Balanced: one round of twelve.
 * - Very strict: `limits.rounds` rounds (three) of the same twelve.
 * - `from`: rounds the PC already holds for this PC's microphone (carrying
 *   on after the window was closed) are left out.
 */
export function trainingPlan(status, { add = false, held = [] } = {}) {
  const can = understands(status);
  const all = SENTENCES.map((_, i) => i);
  if (!can.rounds) {
    return { add: false, legacy: true, again: false, total: 1, rounds: [{ round: 1, ask: "", items: all }] };
  }
  const n = strictnessOf(status) === "balanced" ? 1 : limits(status).rounds;
  const rounds = [];
  for (let r = 1; r <= n; r += 1) {
    if (held.includes(r)) continue;
    rounds.push({ round: r, ask: roundAsk(status, r), items: all.slice() });
  }
  return { add: Boolean(add), legacy: false, again: false, total: n, rounds };
}

/**
 * The plan for recording again the clips the PC left out (`outliers`,
 * `[{round, clip}]`, clip counted from 1 within its round). A round needs
 * at least `limits.min_clips` recordings, so a round with fewer left out
 * is topped up with the sentences that follow. Always `add: true`: the
 * print that was made stays, and these join it.
 */
export function outlierPlan(status, outliers) {
  const min = limits(status).minClips;
  const byRound = new Map();
  for (const o of Array.isArray(outliers) ? outliers : []) {
    const r = Number(o && o.round);
    const c = Number(o && o.clip);
    if (!Number.isInteger(r) || r < 1 || r > 3 || !Number.isInteger(c) || c < 1 || c > SENTENCES.length) continue;
    if (!byRound.has(r)) byRound.set(r, new Set());
    byRound.get(r).add(c - 1);
  }
  const rounds = [...byRound.keys()].sort((a, b) => a - b).map((r) => {
    const items = [...byRound.get(r)].sort((a, b) => a - b);
    for (let i = 0; items.length < min && i < SENTENCES.length * 2; i += 1) {
      const next = (items[items.length - 1] + 1 + i) % SENTENCES.length;
      if (!items.includes(next)) items.push(next);
    }
    return { round: r, ask: roundAsk(status, r), items };
  });
  return { add: true, legacy: false, again: true, total: 0, rounds };
}

/** How long a plan takes, in words, for its first screen. */
export function planLine(plan) {
  const p = obj(plan);
  const rounds = Array.isArray(p.rounds) ? p.rounds : [];
  const sentences = rounds.reduce((n, r) => n + (Array.isArray(r.items) ? r.items.length : 0), 0);
  if (rounds.length <= 1) {
    return `${sentences} sentences, in one go. It takes about two minutes.`;
  }
  return `${rounds.length} rounds, ${sentences} sentences in all. Each round takes about two minutes.`;
}

/** The first screen, in the phone's words where it has them. */
export function introLines(plan, status) {
  const p = obj(plan);
  const rounds = Array.isArray(p.rounds) ? p.rounds : [];
  const lines = [];
  if (p.again) {
    lines.push("Record again the sentences your PC left out, so it knows your voice in those conditions too. They are added to what it already knows; nothing it had is deleted.");
  } else if (p.add) {
    lines.push("Train more: these recordings are added to what Jarvis already knows about your voice on this PC. Nothing it had is deleted.");
  } else if (rounds.length > 1) {
    const minutes = limits(status).sessionMinutes;
    lines.push(`Jarvis only listens to your voice. Because the voice check is very strict, read the same 12 short sentences ${rounds.length} times, in different conditions, so it knows your voice close up, further away, and at another time or in another room. Your PC keeps each round in memory for ${minutes} minutes after the last one, and asks you to approve them all on one card at the end.`);
  } else {
    lines.push("Jarvis only listens to your voice. Read these 12 short sentences into this PC's microphone so it learns what you sound like, and how you say \"hey Jarvis\". It takes about two minutes.");
  }
  lines.push("Speak normally, at the distance you usually sit from the microphone. Jarvis then asks you to approve the change on an approval card - nothing changes until you do. The recordings are kept in memory only, never saved to a file, and deleted once the card is answered.");
  return lines;
}

/**
 * The line over a round's sentences: "Round 2 of 3: further away from the
 * microphone, or quieter." The PC's own round numbers, because the ones it
 * leaves out are named by them. "" for an older PC's single round.
 */
export function roundLine(plan, index) {
  const p = obj(plan);
  const r = obj((p.rounds || [])[index]);
  if (p.legacy || !r.round) return "";
  const ask = r.ask ? `: ${r.ask}.` : ".";
  if (p.again) return `Round ${r.round} again${ask}`;
  if (p.total > 1) return `Round ${r.round} of ${p.total}${ask}`;
  return r.ask ? `How to record: ${r.ask}.` : "";
}

/** "3.4 s" - always a dot, like the phone's `lengthLabel`. */
export function lengthLabel(seconds) {
  return `${num(seconds).toFixed(1)} s`;
}

/**
 * Why this recording must be made again, or null when it is fine. The
 * phone's `clipProblem`, and one more the desktop can see before sending:
 * a microphone that heard nothing (the PC refuses a silent clip).
 */
export function clipProblem(taken, status) {
  const t = obj(taken);
  const lim = limits(status);
  if (num(t.peak) < 0.01) {
    return "That was silent. Check the microphone is plugged in and switched on, then record it again.";
  }
  if (num(t.seconds) < lim.minSeconds) {
    return "That was too short. Press Record, read the whole sentence, then press Stop.";
  }
  if (num(t.seconds) > lim.maxSeconds) {
    return `That was too long. Keep it under ${Math.round(lim.maxSeconds)} seconds.`;
  }
  return null;
}

/**
 * Why a round cannot be sent yet, or null. The phone's `sendBlocker`: the
 * link first, because it is the standing rule for not acting.
 */
export function sendBlocker({ recorded, total, linkBlocker, totalSeconds, status }) {
  const lim = limits(status);
  if (linkBlocker) return linkBlocker;
  if (recorded < total) return `Record all ${total} sentences first (${recorded} done).`;
  if (totalSeconds > lim.maxTotal) {
    return `The recordings are ${Math.floor(totalSeconds)} seconds in all; the most is ${Math.round(lim.maxTotal)}. Redo the longest ones a little quicker.`;
  }
  return null;
}

/** The phone's `AFTER_SENDING`, with the desktop's approve-where words. */
export function afterSending(approveWhere) {
  return `Sent. A card is waiting to finish it. Approve it ${approveWhere}.`;
}

/** The server's own sentence, first letter up, one full stop. */
export function sentence(text) {
  const s = String(text || "").trim().replace(/[.\s]+$/, "");
  return s ? `${s.charAt(0).toUpperCase()}${s.slice(1)}.` : "";
}

/**
 * What the PC answered to a round or a training, in words: `{text, tone,
 * held, finished}`. `held`: the round is kept in memory and the next can
 * start. `finished`: a card is up.
 */
export function roundReply(answer, approveWhere) {
  const a = obj(answer);
  const http = Number(a.http) || 0;
  if (a.error) {
    const round = Number.isInteger(a.round) ? ` (round ${a.round})` : "";
    return { text: `${sentence(a.error)}${round ? ` That was in round ${a.round}.` : ""}`, tone: "bad", held: false, finished: false };
  }
  if (a.ok === true && (http === 202 || a.pending === true)) {
    return { text: afterSending(approveWhere), tone: "ok", held: false, finished: true };
  }
  if (a.ok === true && a.held) {
    return { text: sentence(a.message) || "Kept on your PC.", tone: "ok", held: true, finished: false };
  }
  if (a.ok === true && http === 202) {
    // Approved at once (a tier that did not wait): said by the status.
    return { text: "Sent. Your PC has answered already; see how it ended above.", tone: "ok", held: false, finished: true };
  }
  return { text: "Your PC did not say whether it got the recordings.", tone: "bad", held: false, finished: false };
}

/** "round 2, sentence 5" lists, joined in plain words. */
function listWords(items) {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join("; ")} and ${items[items.length - 1]}`;
}

/**
 * The recordings the PC left out (`last.outliers`) in words, or null.
 * `enrolled` with outliers: the print was made without them; `failed`
 * with outliers: most were like that, so nothing was saved.
 */
export function outlierLine(last) {
  const l = obj(last);
  const list = (Array.isArray(l.outliers) ? l.outliers : [])
    .filter((o) => o && Number.isInteger(o.round) && Number.isInteger(o.clip));
  if (!list.length) return null;
  if (l.outcome === "failed") {
    return "Most of those recordings did not sound like the same voice, so nothing was saved. Record them again somewhere quieter, sitting the same way each time.";
  }
  if (l.outcome !== "enrolled") return null;
  const where = listWords(list.map((o) => `round ${o.round}, sentence ${o.clip}`));
  const n = list.length === 1 ? "1 recording" : `${list.length} recordings`;
  return `Jarvis left out ${n} because ${list.length === 1 ? "it" : "they"} did not sound like the rest: ${where}. Record ${list.length === 1 ? "it" : "them"} again so it knows your voice in those conditions too.`;
}

/**
 * Rounds the PC holds for this PC's microphone (`gate.training.session`),
 * or null. `{rounds: [1], add, clips, minutes, line}`.
 */
export function heldSession(status) {
  const s = obj(obj(obj(status).gate).training).session;
  if (!s || typeof s !== "object" || s.mic !== "desktop") return null;
  const rounds = (Array.isArray(s.rounds) ? s.rounds : [])
    .map((r) => Number(r && r.round)).filter((r) => Number.isInteger(r));
  if (!rounds.length) return null;
  const minutes = Math.max(1, Math.ceil(num(s.expires_in) / 60));
  const which = rounds.length === 1 ? `round ${rounds[0]}` : `rounds ${listWords(rounds.map(String))}`;
  const clips = count(s.clips);
  return {
    rounds,
    add: yes(s.add),
    clips,
    line: `Your PC is keeping ${which} of a training from this PC (${clips === 1 ? "1 recording" : `${clips} recordings`}), in memory only, for about ${minutes} more minute${minutes === 1 ? "" : "s"}.`,
  };
}

/* ── How strict, and private answers ──────────────────────────────────── */

const SETTING_NAMES = {
  strictness: "how strict the voice check is",
  privacy: "private answers",
  memory: "answers that use what Jarvis remembers",
  sensitive_memory: "answers that use sensitive saved facts",
  hands_free: "how far \"Hey Jarvis\" is trusted",
};

/** The choices, in the order they are shown, with plain words for each. */
export const STRICTNESS = Object.freeze([
  {
    id: "very_strict",
    label: "Very strict",
    recommended: true,
    detail: "Needs about 2 seconds of speech and a close match. Best at turning other people away; now and then it may ask you to say it again. It tells your voice from other people's. It cannot tell your voice from a recording or a copy of it.",
  },
  {
    id: "balanced",
    label: "Balanced",
    detail: "Takes shorter commands (about 1.5 seconds) at a lower bar. You repeat yourself less, but someone whose voice is close to yours gets in more easily. Private answers then always stay on screen.",
  },
]);

export const PRIVACY = Object.freeze([
  {
    id: "private_on_screen",
    label: "Stay on screen",
    recommended: true,
    detail: "When you ask by voice, answers from your email, calendar or notes are shown on screen, not read aloud. Typing on your own PC or phone is not affected.",
  },
  {
    id: "voice_is_enough",
    label: "Voice check is enough",
    detail: "Jarvis reads those answers aloud when your voice passes the very strict check. Anyone near the speaker will hear them.",
  },
]);

/** The owner's choice of 2026-09-24: "looser now, with a setting to make it more strict". */
export const MEMORY = Object.freeze([
  {
    id: "memory_aloud",
    label: "Read aloud",
    recommended: true,
    detail: "When you ask by voice, answers that use what Jarvis remembers about you are read aloud. Anyone near the speaker will hear them. Questions about email, your calendar, notes, health or money still stay on screen.",
  },
  {
    id: "memory_on_screen",
    label: "Keep on screen",
    detail: "Those answers are shown, not read aloud, like email and notes.",
  },
]);

/**
 * The owner's decision 13 (2026-09-24): answers that use a SENSITIVE saved
 * fact - health, money, passwords, other people's private details - stay on screen by
 * default, even while "Answers that use what Jarvis remembers" reads the
 * rest aloud, and even with "Voice check is enough". Reading them aloud is
 * the looser choice: the voice card, and held on a stale link.
 */
export const SENSITIVE_MEMORY = Object.freeze([
  {
    id: "sensitive_on_screen",
    label: "Keep on screen",
    recommended: true,
    detail: "Answers that use a saved fact about your health, money, passwords or other people's private details are shown, not read aloud.",
  },
  {
    id: "sensitive_aloud",
    label: "Read aloud",
    detail: "Those answers are read aloud when your voice passes the check. Anyone near the speaker will hear them.",
  },
]);

/**
 * The owner's decision of 2026-09-24: a question started hands-free ("Hey
 * Jarvis") is as trusted as one where the talk button is pressed, by
 * default, with this setting to make it stricter. "Only trust the talk
 * button" applies at once; going back is the looser choice - the voice
 * card, and held on a stale link. The default is marked "(default)", not
 * "(recommended)": it is the owner's choice, not the safer one.
 */
export const HANDS_FREE = Object.freeze([
  {
    id: "same_as_button",
    label: "Same as the talk button",
    isDefault: true,
    detail: "A question started with \"Hey Jarvis\" is trusted like one where you press the button.",
  },
  {
    id: "button_only",
    label: "Only trust the talk button",
    detail: "Hey Jarvis still works, but it cannot teach Jarvis facts without a card, and memory or private answers stay on screen. Safer if a recording of your voice could be played near the microphone.",
  },
]);

function choiceWords(setting, value) {
  const list = setting === "strictness" ? STRICTNESS : setting === "privacy" ? PRIVACY
    : setting === "memory" ? MEMORY : setting === "sensitive_memory" ? SENSITIVE_MEMORY
      : setting === "hands_free" ? HANDS_FREE : [];
  return list.find((c) => c.id === value) || null;
}

/** "Balanced", "Stay on screen" - a choice's label, or "". */
export function settingLabel(setting, value) {
  const c = choiceWords(setting, value);
  return c ? c.label : "";
}

/** A choice as its button shows it: "Very strict (recommended)", "Same as
 *  the talk button (default)". Every sentence that names a choice uses the
 *  plain `label`. */
export function choiceText(c) {
  return c ? `${c.label}${c.recommended ? " (recommended)" : c.isDefault ? " (default)" : ""}` : "";
}

/** Under the privacy choices while the check is not very strict. */
export const VOICE_IS_ENOUGH_NOTE = "\"Voice check is enough\" can only be chosen while the check is very strict.";

/** Under the memory choices while "voice check is enough" is on: that
 *  already reads every private answer aloud, memory included (private-
 *  speech.js lets `private_aloud` through first), so neither choice here
 *  would change anything, and both are disabled. */
export const MEMORY_MOOT_NOTE =
  "\"Voice check is enough\" already reads these answers aloud. Choose \"Stay on screen\" above to use this setting.";

/** Whether the memory choices do nothing now (see MEMORY_MOOT_NOTE). */
export function memoryMoot(view) {
  return Boolean(view && view.privacy === "voice_is_enough");
}

/** Under the sensitive-facts choices while "Keep on screen" is chosen for
 *  what Jarvis remembers: every answer that uses a saved fact already stays
 *  on screen, the sensitive ones included (private-speech.js). The choices
 *  stay usable - this one takes over if the memory choice changes. */
export const SENSITIVE_COVERED_NOTE = "\"Keep on screen\" above already keeps these answers on screen.";

/** Whether the memory choice already keeps sensitive answers on screen
 *  (see SENSITIVE_COVERED_NOTE). Not under "Voice check is enough": that
 *  makes the memory choice moot, and then only this one holds them back. */
export function sensitiveCovered(view) {
  return Boolean(view && view.memory === "memory_on_screen" && !memoryMoot(view));
}

/** The value `setting` has now, by the PC's status, or "" when not said. */
export function currentSetting(status, setting) {
  const view = settingsView(status);
  if (!view) return "";
  return setting === "strictness" ? view.strictness : setting === "privacy" ? view.privacy
    : setting === "memory" ? view.memory : setting === "sensitive_memory" ? view.sensitiveMemory
      : setting === "hands_free" ? view.handsFree : "";
}

/** Whether choosing `value` for `setting` loosens it (a card), by the server's rule. */
export function loosens(setting, value) {
  return (setting === "strictness" && value === "balanced") || (setting === "privacy" && value === "voice_is_enough")
    || (setting === "memory" && value === "memory_aloud")
    || (setting === "sensitive_memory" && value === "sensitive_aloud")
    || (setting === "hands_free" && value === "same_as_button");
}

/**
 * The settings as the page shows them: what is chosen, whether "voice
 * check is enough" may be picked, and a card waiting to loosen one.
 * `null` from a PC that does not have them.
 */
export function settingsView(status) {
  const gate = obj(obj(status).gate);
  if (!understands(status).settings) return null;
  const s = obj(gate.settings);
  const strictness = s.strictness === "balanced" ? "balanced" : "very_strict";
  const privacy = s.privacy === "voice_is_enough" && strictness === "very_strict" ? "voice_is_enough" : "private_on_screen";
  const training = obj(gate.training);
  const waiting = yes(training.pending) && training.kind === "setting" ? obj(training.setting) : null;
  const min = num(s.min_command_seconds);
  // "" from a PC older than the memory setting: the page does not offer it.
  const memory = s.memory === "memory_aloud" || s.memory === "memory_on_screen" ? s.memory : "";
  // Decision 13's setting: `gate.settings.sensitive_memory` (or
  // `gate.sensitive_memory`). "" from a PC that does not have it, and the
  // page does not offer it then.
  const rawSensitive = s.sensitive_memory !== undefined ? s.sensitive_memory : gate.sensitive_memory;
  const sensitiveMemory = rawSensitive === "sensitive_on_screen" || rawSensitive === "sensitive_aloud"
    ? rawSensitive : "";
  // The fifth, how far "Hey Jarvis" is trusted: `gate.settings.hands_free`
  // (or `gate.hands_free`). "" from a PC that does not have it - not offered.
  const rawHandsFree = s.hands_free !== undefined ? s.hands_free : gate.hands_free;
  const handsFree = rawHandsFree === "same_as_button" || rawHandsFree === "button_only" ? rawHandsFree : "";
  return {
    strictness,
    privacy,
    memory,
    sensitiveMemory,
    handsFree,
    voiceIsEnoughAllowed: yes(s.voice_is_enough_allowed) && strictness === "very_strict",
    minSeconds: min,
    waiting: waiting && waiting.name ? { setting: String(waiting.name), value: String(waiting.value || "") } : null,
  };
}

/** The line under the choices while a card to loosen one waits. */
export function settingWaitingLine(waiting, approveWhere) {
  if (!waiting) return null;
  const words = choiceWords(waiting.setting, waiting.value);
  const what = words ? ` to change ${SETTING_NAMES[waiting.setting]} to "${words.label}"` : "";
  return `Waiting for your approval${what}. Approve it ${approveWhere} — nothing changes until you do.`;
}

/** What the PC answered to a setting change, in words: `{text, tone}`. */
export function settingReply(answer, approveWhere) {
  const a = obj(answer);
  if (a.error) return { text: sentence(a.error), tone: "bad" };
  if (a.ok === true && (a.pending === true || Number(a.http) === 202)) {
    return { text: `Waiting for your approval. Approve it ${approveWhere} — nothing changes until you do.`, tone: "ok" };
  }
  if (a.ok === true && a.changed === false) return { text: "It was already set that way.", tone: "ok" };
  if (a.ok === true) return { text: sentence(a.message) || "Done - that applies now.", tone: "ok" };
  return { text: "Your PC did not say whether it changed.", tone: "bad" };
}

/* ── How often Jarvis asks you to repeat ─────────────────────────────── */

/**
 * The PC's own counts (`gate.repeat`) in words: one line per setting that
 * has counted anything. "Jarvis asked you to repeat X of the last Y times"
 * - Y is how often it let you in, X how many of those came within 10
 * seconds of being turned away.
 */
export function repeatLines(status) {
  const rep = obj(obj(obj(status).gate).repeat);
  if (!Object.keys(rep).length) return [];
  const lines = [];
  for (const c of STRICTNESS) {
    const r = obj(rep[c.id]);
    const accepted = count(r.accepted);
    const again = count(r.refused_then_accepted);
    const refused = count(r.refused);
    const short = count(r.too_short);
    if (!accepted && !refused && !short) continue;
    let text;
    if (accepted) {
      text = `${c.label}: Jarvis asked you to repeat ${again} of the last ${accepted} times.`;
    } else {
      text = `${c.label}: Jarvis has not let a spoken command through yet.`;
    }
    const extra = [];
    if (refused) extra.push(`${refused} turned away`);
    if (short) extra.push(`${short} too short`);
    if (extra.length) text += ` (${extra.join(", ")}.)`;
    lines.push({ id: c.id, text, tone: accepted && again / accepted > 0.25 ? "warn" : "" });
  }
  if (!lines.length) {
    return [{ id: "none", text: "No spoken commands yet since Jarvis last started, so there is nothing to count.", tone: "" }];
  }
  return lines;
}

/** The note under those counts. */
export const REPEAT_NOTE =
  "Counted since Jarvis last started, for this PC and your phone together; nothing is kept on disk.";

/**
 * A guided test's result (`measure` answer, or `measure_last`) in words,
 * or null.
 */
export function measureLines(result) {
  const r = obj(result);
  const vs = obj(r.very_strict);
  const ba = obj(r.balanced);
  const n = count(vs.of) || count(r.clips);
  if (!n) return null;
  const p1 = count(vs.passed);
  const p2 = count(ba.passed);
  const lines = [`Very strict let ${p1} of ${n} through; balanced ${p2} of ${ba.of ? count(ba.of) : n}.`];
  lines.push(`So at very strict, Jarvis would have asked you to repeat ${n - p1} of ${n} sentences; at balanced, ${(count(ba.of) || n) - p2}.`);
  const short = count(vs.too_short);
  if (short) {
    lines.push(`${short} of them ${short === 1 ? "was" : "were"} too short for very strict, which needs about 2 seconds of speech. Saying a little more helps.`);
  }
  if (r.strong_model === false) {
    lines.push("This was measured with the small voice-ID model, because the stronger one is not installed.");
  }
  return lines;
}

/* ── The "someone else" check ────────────────────────────────────────── */

/**
 * Three sentences for another person to read, so the PC can see how close a
 * different voice gets. The phone's `VoiceTraining.OTHER_SENTENCES`, word
 * for word.
 */
export const OTHER_SENTENCES = Object.freeze([
  "Hey Jarvis, what time is it?",
  "Can you read me the news headlines?",
  "Turn the heating up a couple of degrees.",
]);

/** The phone's `CHECK_INTRO`, with "this phone" made "this PC's microphone". */
export const CHECK_INTRO =
  "Want to make sure Jarvis turns other people away? Ask someone else to read 3 sentences into this PC's microphone. Your PC compares them with your voice and suggests a setting. Nothing changes unless you approve it.";

/** Under the "use the stricter setting" button. */
export const CHECK_CARD_NOTE = "Nothing changes until you approve the card.";

/**
 * Whether the check may be offered: the PC says it understands it
 * (`gate.training.calibrate` - an older PC would read the other person's
 * clips as a TRAINING), and a voice print this microphone can be compared
 * with exists (this PC's own, or the phone's or the older one it falls back
 * to). The phone's `canCheck`.
 */
export function canCheck(status) {
  const s = obj(status);
  const gate = obj(s.gate);
  if (s.available === false || !yes(obj(gate.training).calibrate)) return false;
  const prints = obj(gate.prints);
  return ["desktop", "phone", "general"].some((k) => yes(obj(prints[k]).trained));
}

/** "0.52" - always two places, always a dot. */
export function score(v) {
  return num(v).toFixed(2);
}

/**
 * The PC's answer to the check, in words: `{ok, text, suggested, model}`.
 * The phone's `checkResult`; "would pass" is the PC's own verdict
 * (`passed_count`) when it sends one - with the stricter check a voice can
 * clear the bar and still be turned away - and the scores against the bar
 * otherwise. `suggested` is set only when it is stricter than now.
 */
export function checkResult(answer) {
  const c = obj(answer);
  if (typeof c.error === "string" && c.error.trim()) {
    return { ok: false, text: sentence(c.error), suggested: null, model: "" };
  }
  if (c.ok !== true) {
    return { ok: false, text: sentence(c.message) || "Your PC could not compare the voices.", suggested: null, model: "" };
  }
  const threshold = num(c.threshold);
  const theirs = (Array.isArray(c.scores) ? c.scores : []).filter((x) => typeof x === "number" && Number.isFinite(x));
  const passed = Number.isInteger(c.passed_count) && c.passed_count >= 0
    ? c.passed_count
    : theirs.filter((x) => x >= threshold).length;
  let head;
  if (!theirs.length) head = "None of the clips could be scored.";
  else if (passed === 0) head = `Good: none of their ${theirs.length} clips would pass as you now.`;
  else head = `${passed} of their ${theirs.length} clips would pass as you now.`;
  const sug = typeof c.suggested === "number" && Number.isFinite(c.suggested) ? c.suggested : null;
  let tail;
  if (sug !== null && sug > threshold + 0.005) {
    tail = ` A stricter setting, ${score(sug)} (now ${score(threshold)}), would turn them away and still let you in.`;
  } else if (sug !== null) {
    tail = " Your current setting already sits between you and them.";
  } else {
    tail = ` ${sentence(c.message) || "Their voice came too close to yours to suggest a stricter setting."}`;
  }
  const model = c.model === "strong" || c.model === "small" ? c.model : "";
  return { ok: true, text: head + tail, suggested: sug !== null && sug > threshold + 0.005 ? sug : null, model };
}

/** What the PC answered to the threshold card, in words: `{text, tone}`. */
export function thresholdReply(answer, approveWhere) {
  const a = obj(answer);
  if (typeof a.error === "string" && a.error.trim()) return { text: sentence(a.error), tone: "bad" };
  if (a.ok === true) {
    return { text: `Waiting for your approval. Approve it ${approveWhere} — nothing changes until you do.`, tone: "ok" };
  }
  return { text: "Your PC did not say whether it raised the card.", tone: "bad" };
}

/** The guided test's first screen. */
export const TEST_INTRO =
  "Read 20 sentences. Jarvis checks each one the way it checks a spoken command, at both settings, and tells you how many would have got through. Nothing is saved, no card is raised, and it does not count towards the numbers above.";

/** What the PC answered to the guided test, in words: `{lines, tone}`. */
export function measureReply(answer) {
  const a = obj(answer);
  if (a.error) return { lines: [sentence(a.error)], tone: "bad" };
  const lines = a.ok === true ? measureLines(a) : null;
  return lines ? { lines, tone: "ok" } : { lines: ["Your PC did not say how the test went."], tone: "bad" };
}

/* ── Which voice-ID model very strict uses ───────────────────────────── */

/** Where the backend README says how to install the models. */
export const README_STRONGER =
  "https://github.com/darknight11ish/Epic-Jarvis/blob/main/backend/README.md#the-stricter-voice-check-2026-09-24--only-your-voice-and-more-sure-of-it";
export const README_MODEL =
  "https://github.com/darknight11ish/Epic-Jarvis/blob/main/backend/README.md#install-the-better-voice-check-recommended";

/**
 * The voice-ID model line: `{text, tone, link, linkText}`, or null from a
 * PC that does not report its models (`gate.models`).
 */
export function modelLine(status) {
  const gate = obj(obj(status).gate);
  if (obj(status).available === false || !gate.models || typeof gate.models !== "object") return null;
  const m = obj(gate.models);
  const which = String(m.very_strict_model || "");
  if (which === "strong") {
    return { text: "Voice-ID model: the stronger one is installed, and very strict uses it.", tone: "ok", link: null, linkText: "" };
  }
  if (which === "small") {
    return {
      text: "Only the small voice-ID model is installed, so very strict will turn you away far more often. Install the stronger one: step 2 of \"The stricter voice check\" in the backend's README.",
      tone: "warn",
      link: README_STRONGER,
      linkText: "Open the README at that step",
    };
  }
  return {
    text: "No voice-ID model is installed, so Jarvis refuses every spoken command and training cannot help yet. Install it first: \"Install the better voice check\" in the backend's README.",
    tone: "warn",
    link: README_MODEL,
    linkText: "Open the README at that step",
  };
}

/** The PC's own note (`gate.note`), as sentences, or null. */
export function noteLine(status) {
  const note = String(obj(obj(status).gate).note || "").trim();
  if (!note) return null;
  return note.split(/\.\s+/).map((s) => sentence(s)).filter(Boolean).join(" ");
}
