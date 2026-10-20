/**
 * Settings -> Voice, training on this PC: the words and the rules, with no
 * page in them, so every sentence is tested against the backend's real
 * answers (tests/voice-training.mjs and tests/voice-training-plan.mjs read
 * tests/fixtures/voice-training-cases.json, made by
 * tools/gen_voice_training_cases.py).
 *
 * What it covers (docs/JARVIS-API.md section 5.1):
 * - "Train my voice" on this PC's microphone, from the PC's OWN plan
 *   (`gate.training.training`, jarvis_voice_training.plan()): four listening
 *   conditions, twelve balanced read phrases and three free-speech prompts.
 *   This desktop build records the first three conditions (its Rust sender
 *   accepts rounds 1-3) and shows the fourth as not wired rather than
 *   pretending; ONE approval card at the end; "Train more" adds instead of
 *   replacing; recordings the PC left out are recorded again. A PC without
 *   the plan is not offered a training and says why.
 * - Live additions to the print: the PC's count and caps, the drift guard
 *   and re-anchoring, in the PC's own words. The backend's adapt-reset mode
 *   exists, but this build has no desktop command for it, so the count is
 *   wired here and the count is resettable.
 * - Held-out measurement: FRR, FAR and the EER point per condition, in the
 *   PC's own words, including "not enough measured rows" - never a number
 *   the PC did not send, and never a threshold applied by the page.
 * - How strict the voice check is, and whether private answers may be read
 *   aloud: tightening at once, loosening only through a card.
 * - The guided test (20 sentences) and the "asked you to repeat" counts.
 * - Which voice-ID model very strict uses, and what to do when it is not
 *   the stronger one.
 *
 * The settings screens' strictness/private-answer words are still the
 * phone's, word for word where it has them. The training material is now the
 * PC's plan instead: the phone reads the same payload in its own next slice.
 *
 * Nothing here turns speech into text: the phrases and prompts are shown for
 * the owner to read and speak, and nobody checks the words - only the voice.
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

/**
 * The four recording conditions, in the PC's training order
 * (`backend/jarvis_voice_training.py` CONDITIONS): close; on a table
 * two to three metres away; with the fan or the TV on; in another room or
 * at a different time of day.
 *
 * The PC sends this plan in `gate.training.training`. This copy is the
 * documented contract, used by the tests and by the page when it has to name
 * a condition before the PC has answered; it is never recorded against on a
 * PC that did not send the plan (`trainingPlan` says the plan is missing).
 */
export const CONDITIONS = Object.freeze([
  { id: "close", label: "Close", ask: "normal, close to the microphone" },
  { id: "table", label: "On a table, 2-3 m away", ask: "about two to three metres away, on a table" },
  { id: "noise", label: "With background noise", ask: "with the fan or the TV on, as it usually is" },
  { id: "room", label: "Another room or time", ask: "in another room, or at a different time of day" },
]);

/**
 * The PC plan's twelve balanced read phrases (`READ_PHRASES`): every English
 * vowel, the consonant clusters that matter for a microphone, and short,
 * medium and long sentences. The PC sends the real list; this is the
 * documented copy, held equal by tests/voice-training-plan.mjs.
 */
export const READ_PHRASES = Object.freeze([
  { id: "vowel-1", text: "The blue boat floats slowly over the cold deep water.", focus: ["vowels", "long"], words: 10 },
  { id: "vowel-2", text: "Please speak clearly about the meeting on Thursday.", focus: ["vowels", "consonants"], words: 7 },
  { id: "vowel-3", text: "My eyes see a bright fire by the white gate.", focus: ["vowels", "diphthongs"], words: 10 },
  { id: "consonant-1", text: "She sells fresh fish from the shelf by the shore.", focus: ["consonants", "fricatives"], words: 10 },
  { id: "consonant-2", text: "Six thick sticks stand beside the strong tree.", focus: ["consonants", "clusters"], words: 8 },
  { id: "consonant-3", text: "Judge the quick brown fox before the jazz band.", focus: ["consonants", "clusters", "short"], words: 9 },
  { id: "short-1", text: "Light the lamp.", focus: ["short", "consonants"], words: 3 },
  { id: "medium-1", text: "Rain falls on the roof while the kettle sings.", focus: ["medium", "vowels"], words: 9 },
  { id: "medium-2", text: "The train to town leaves at half past eight.", focus: ["medium", "diphthongs"], words: 9 },
  { id: "long-1", text: "On the way home I stopped at the market and bought apples, bread and a small paper bag of rice.", focus: ["long", "varied"], words: 15 },
  { id: "long-2", text: "Please remember to bring the green folder to my office before the morning meeting on Friday.", focus: ["long", "varied"], words: 13 },
  { id: "natural-1", text: "It was a cold morning, and the car would not start.", focus: ["natural", "varied"], words: 9 },
]);

/** The PC plan's three free-speech prompts (`FREE_SPEECH`), with their window. */
export const FREE_SPEECH = Object.freeze([
  { id: "introduce", text: "Introduce yourself in your own words: who you are, what you do, and something you like.", seconds: [10, 30], why: "natural rhythm and everyday words" },
  { id: "day", text: "Describe your day so far in your own words - what you did, what you saw, what you are planning next.", seconds: [10, 30], why: "connected speech, not one short sentence" },
  { id: "passage", text: "Read this aloud, slowly: The morning train was late again, so I stood at the window and watched the rain move across the empty platform.", seconds: [8, 25], why: "a varied passage with long and short sounds" },
]);

/** The fixed wake words: the detector's own words, never training material. */
export const WAKE_PHRASES = Object.freeze(["hey Jarvis"]);

/** The twelve texts only, for a caller that does not need the focus labels. */
export const SENTENCES = Object.freeze(READ_PHRASES.map((p) => p.text));

/**
 * How many condition rounds THIS desktop build can send to the PC.
 *
 * The PC understands all four (`state()["limits"]["rounds"]` is 4), but the
 * desktop's Rust sender accepts rounds 1-4
 * (`src-tauri/src/voice_training.rs`, `send_voice_training`). All four are
 * wired, so the page records every condition the PC's plan lists.
 */
export const DESKTOP_ROUND_LIMIT = 4;

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
    rounds: count(lim.rounds) || 4,
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
    // The redesigned plan itself: the phrases, free-speech prompts and four
    // conditions in `gate.training.training`. An older PC sends none of it,
    // and this page then says so instead of recording against a guess.
    plan: Boolean(planOf(status)),
    // The PC understands `{"mode": "clear"}` (2026-10-19, the owner's "clear
    // previous voice training"): one more mode on the existing enroll route.
    // An older PC answers 400 "unknown mode"; this page then offers no button
    // rather than sending a body it cannot read.
    clear: yes(t.clear),
  };
}

/* ── Clearing the saved voice training (2026-10-19) ─────────────────── */

/** The button's own words. */
export const CLEAR_LABEL = "Clear previous voice training";

/**
 * What the card deletes, in the owner's words. `describe_clear()` in
 * backend/jarvis_voice_enroll.py writes the card itself; this is the page's
 * summary beside the button, and it names only what the card names.
 */
export const CLEAR_WHAT_IT_DOES =
  "Deletes every saved voice print on your PC (one per microphone you trained), " +
  "the \"hey Jarvis\" check built from those recordings, and the small notes it " +
  "kept from learning your voice in Live. It does not delete your custom " +
  "speaking voices, your chat history or your phone pairing. ONE card approves " +
  "it: nothing is deleted until you say yes, and voice commands and Jarvis Live " +
  "are refused until you train your voice again.";

/** Said once the PC has cleared the training (the status's own outcome). */
export const CLEARED_LINE =
  "Your saved voice training is cleared. Train your voice again to use voice commands.";

/** The one card's sentence for the button's own state line. */
export function clearApproveLine(approveWhere) {
  return `Approve the card ${approveWhere}. Nothing is deleted until you do.`;
}

/**
 * Said when a voice card is already waiting: the clear button must not fire a
 * second time (the PC answers 409 for a second request), and this page shows
 * that waiting card in words instead.
 */
export function clearWaitingLine(status) {
  const t = obj(obj(obj(status).gate).training);
  if (t.pending !== true) return null;
  if (String(t.kind || "") === "clear") {
    return "A clear card is already waiting for your approval - approve or deny " +
      "it first. Nothing is deleted until you do, and a second clear cannot be " +
      "asked for while it waits.";
  }
  return "A voice card is already waiting for approval. Approve or deny that card " +
    "first; no second voice card can be raised while it waits.";
}

/**
 * What the PC answered to the clear request, in words for the page. Mirrors
 * backend/jarvis_voice_enroll.stage_clear()'s own answers:
 *  - 202 `pending: true` - ONE card is up, nothing deleted yet;
 *  - 200 `ok: true, cleared: false` - nothing saved, no card raised;
 *  - 409 `pending: true` - another voice card is already waiting;
 *  - 409 `pending: false` - the tier is not `ask`, so no card was raised;
 *  - anything else - a refusal's sentence, never a claim of success.
 */
export function clearReply(answer, approveWhere) {
  const a = obj(answer);
  const waiting = a.pending === true;
  if (typeof a.error === "string" && a.error.trim()) {
    return { text: sentence(a.error), tone: waiting ? "warn" : "bad", waiting };
  }
  if (waiting || Number(a.http) === 202) {
    const said = typeof a.message === "string" && a.message.trim()
      ? sentence(a.message)
      : clearApproveLine(approveWhere);
    return { text: said, tone: "ok", waiting: true };
  }
  if (a.ok === true && a.cleared === false) {
    const said = typeof a.message === "string" && a.message.trim()
      ? sentence(a.message)
      : "There is nothing to clear: no saved voice training was found on this PC.";
    return { text: said, tone: "note", waiting: false };
  }
  return {
    text: "Your PC did not say whether it cleared anything.",
    tone: "bad",
    waiting: false,
  };
}

/** A reason the PC gave, as a sentence fragment: ", because ..." or "". */
function clearReason(reason) {
  const said = String(reason || "").trim();
  return said ? `: ${sentence(said)}` : ".";
}

/**
 * How the clear ended, from the PC's status `last`, or null when the last
 * outcome was not a clear. Shows what happened in the PC's own terms - a
 * denied or timed-out card leaves every file where it was, and a failed
 * delete is never reported as cleared.
 */
export function clearOutcomeLine(last) {
  const l = obj(last);
  const outcome = String(l.outcome || "");
  if (outcome === "cleared") return { text: CLEARED_LINE, tone: "ok" };
  if (outcome === "denied") {
    return { text: "You said no, so every saved voice file stays and nothing changed.", tone: "warn" };
  }
  if (outcome === "timed_out") {
    return { text: "Nobody answered the clear card in time, so every saved voice file stays.", tone: "warn" };
  }
  if (outcome === "refused") {
    return { text: `Your PC refused the clear${clearReason(l.reason)}`, tone: "warn" };
  }
  if (outcome === "failed") {
    return {
      text: `The clear did not finish${clearReason(l.reason)} Nothing is reported as cleared while a saved file remains.`,
      tone: "bad",
    };
  }
  return null;
}

/**
 * Whether this PC can clear, and has something saved to clear. Any saved print
 * on any microphone counts: the card is deliberately global (one card clears
 * every microphone's print), so a phone-trained print is offered here too.
 */
export function clearAvailable(status) {
  if (!understands(status).clear) return false;
  const prints = obj(obj(obj(status).gate).prints);
  return Object.keys(prints).some((key) => obj(prints[key]).trained === true);
}

/** The strictness the PC reports: "very_strict", "balanced", or "" when not reported. */
export function strictnessOf(status) {
  const s = String(obj(obj(status).gate).strictness || "");
  return s === "very_strict" || s === "balanced" ? s : "";
}

/**
 * The redesigned plan the PC sent (`gate.training.training`, from
 * jarvis_voice_training.plan()): conditions, read phrases, free-speech
 * prompts and the caps. `null` from a PC older than the redesign - nothing
 * here is guessed, because recording against the wrong material would train
 * the owner's voice on words the PC does not expect.
 */
export function planOf(status) {
  const raw = obj(obj(obj(status).gate).training).training;
  if (!raw || typeof raw !== "object") return null;
  const conditions = (Array.isArray(raw.conditions) ? raw.conditions : [])
    .map((c) => ({
      id: String(obj(c).id || "").trim(),
      label: String(obj(c).label || "").trim(),
      ask: String(obj(c).ask || "").trim(),
    }))
    .filter((c) => c.id);
  const read = (Array.isArray(raw.read_phrases) ? raw.read_phrases : [])
    .map((p) => ({
      id: String(obj(p).id || "").trim(),
      text: String(obj(p).text || "").trim(),
      focus: Array.isArray(p && p.focus) ? [...p.focus] : [],
    }))
    .filter((p) => p.text);
  const free = (Array.isArray(raw.free_speech) ? raw.free_speech : [])
    .map((p) => ({
      id: String(obj(p).id || "").trim(),
      text: String(obj(p).text || "").trim(),
      why: String(obj(p).why || "").trim(),
      seconds: Array.isArray(p && p.seconds) ? [...p.seconds] : [],
    }))
    .filter((p) => p.text);
  if (!conditions.length || !read.length) return null;
  return {
    conditions: conditions.slice(0, 4),
    read,
    free: free.slice(0, 3),
    maxClips: count(raw.max_clips_per_round) || 12,
    minClips: count(raw.min_clips) || limits(status).minClips,
    words: String(raw.words || "").trim(),
  };
}

/** The server's words for each round (`round_asks`), with its own words when missing. */
const ROUND_ASKS = {
  1: "normal, close to the microphone",
  2: "about two to three metres away, on a table",
  3: "with the fan or the TV on, as it usually is",
  4: "in another room, or at a different time of day",
};
export function roundAsk(status, round) {
  const plan = planOf(status);
  const fromPlan = plan && plan.conditions[Number(round) - 1];
  if (fromPlan && fromPlan.ask) return fromPlan.ask.trim();
  const asks = obj(obj(obj(obj(status).gate).training).round_asks);
  const said = asks[String(round)];
  return typeof said === "string" && said.trim() ? said.trim() : ROUND_ASKS[round] || "";
}

/**
 * Why training cannot start on this PC now, in words, or null when it can.
 * Before anything is recorded, so the owner does not read all the phrases to
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
  if (!planOf(status)) {
    return "This PC has not sent the new four-condition training plan yet. Update the backend by running apply-patches.ps1, then open this again.";
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

/** The hint under a free-speech prompt: the PC's own 10-second clip limit. */
function freeHint(status, prompt) {
  const max = Math.round(limits(status).maxSeconds);
  const window = Array.isArray(prompt.seconds) && prompt.seconds.length === 2
    ? `The prompt suggests ${prompt.seconds[0]}-${prompt.seconds[1]} seconds. ` : "";
  return `${window}Your PC keeps at most ${max} seconds in one recording, so say as much as fits.`;
}

/**
 * The clips each condition round records, as `{kind, id, text, focus?,
 * why?, seconds?, hint?}`. Each round carries its share of the twelve phrases and
 * one free-speech prompt each; the fourth condition repeats the opening
 * phrases. That is every phrase and every prompt exactly once in the three
 * rounds this build records - see DESKTOP_ROUND_LIMIT.
 */
function buildRoundItems(plan, status) {
  const n = plan.conditions.length;
  const read = plan.read.length ? plan.read : READ_PHRASES;
  const free = plan.free.length ? plan.free : FREE_SPEECH;
  const readRounds = Math.min(3, n);
  const out = Array.from({ length: n }, () => []);
  read.forEach((p, i) => {
    const group = Math.min(readRounds - 1, Math.floor((i * readRounds) / read.length));
    out[group].push({ kind: "read", id: p.id, text: p.text, focus: p.focus });
  });
  for (let i = 0; i < Math.min(3, n); i += 1) {
    const p = free[i];
    if (!p) continue;
    out[i].push({
      kind: "free", id: p.id, text: p.text, why: p.why, seconds: p.seconds,
      hint: freeHint(status, p),
    });
  }
  if (n > 3) {
    // The fourth condition repeats the opening phrases: every phrase is
    // already covered in the three rounds this build records, and another
    // room still needs enough clips for a sub-print of its own.
    const wants = Math.max(plan.minClips, Math.min(4, read.length));
    out[3] = read.slice(0, wants).map((p) => ({ kind: "read", id: p.id, text: p.text, focus: p.focus }));
  }
  for (const items of out) {
    const have = new Set(items.map((it) => it.id));
    for (let k = 0; items.length < plan.minClips && k < read.length * 2; k += 1) {
      const p = read[k % read.length];
      if (have.has(p.id)) continue;
      have.add(p.id);
      items.push({ kind: "read", id: p.id, text: p.text, focus: p.focus });
    }
    if (items.length > plan.maxClips) items.length = plan.maxClips;
  }
  return out;
}

/**
 * The plan for a training, from the PC's own payload (`planOf`):
 *
 * - four condition rounds, in the PC's order, all `wired` - see
 *   DESKTOP_ROUND_LIMIT;
 * - each round's `items` are the phrases and prompts to record, not indexes;
 * - `held`: rounds the PC already holds for this PC's microphone (carrying on
 *   after the window was closed) are left out, as before;
 * - `missing: true` from a PC that has not sent the plan - the page offers no
 *   training then, rather than recording words the PC did not ask for.
 */
export function trainingPlan(status, { add = false, held = [] } = {}) {
  const plan = planOf(status);
  const heldSet = new Set((Array.isArray(held) ? held : []).map(Number));
  if (!plan) {
    return {
      add: Boolean(add), legacy: false, missing: true, again: false, total: 0,
      wiredTotal: 0, rounds: [], conditions: [], readCount: 0, freeCount: 0,
      perRound: [], minClips: limits(status).minClips,
    };
  }
  const total = plan.conditions.length;
  const wiredTotal = Math.min(total, DESKTOP_ROUND_LIMIT);
  const items = buildRoundItems(plan, status);
  const rounds = [];
  for (let i = 0; i < total; i += 1) {
    const round = i + 1;
    if (heldSet.has(round)) continue;
    const c = plan.conditions[i];
    rounds.push({
      round,
      condition: c.id,
      label: c.label,
      ask: c.ask || roundAsk(status, round),
      items: items[i],
      wired: round <= wiredTotal,
    });
  }
  return {
    add: Boolean(add), legacy: false, missing: false, again: false, total,
    wiredTotal, rounds, readCount: plan.read.length, freeCount: plan.free.length,
    perRound: items.map((x) => x.length), minClips: plan.minClips,
    conditions: plan.conditions.map((c, i) => ({
      round: i + 1, id: c.id, label: c.label, ask: c.ask, wired: i + 1 <= wiredTotal,
    })),
  };
}

/**
 * The plan for recording again the clips the PC left out (`outliers`,
 * `[{round, clip}]`, clip counted from 1 within its round). A round needs at
 * least the PC's `min_clips` recordings, so a round with fewer left out is
 * topped up from that round's own material. Always `add: true`: the print
 * that was made stays, and these join it. A left-out clip in the fourth
 * condition is not offered while the bridge cannot send that round.
 */
export function outlierPlan(status, outliers) {
  const full = trainingPlan(status, { add: true });
  if (full.missing) return { ...full, again: true };
  const byRound = new Map();
  for (const o of Array.isArray(outliers) ? outliers : []) {
    const r = Number(o && o.round);
    const c = Number(o && o.clip);
    if (!Number.isInteger(r) || r < 1 || r > full.total) continue;
    const src = full.rounds.find((x) => x.round === r);
    if (!src || !src.wired || !Number.isInteger(c) || c < 1 || c > src.items.length) continue;
    if (!byRound.has(r)) byRound.set(r, new Set());
    byRound.get(r).add(c - 1);
  }
  const rounds = [...byRound.keys()].sort((a, b) => a - b).map((r) => {
    const src = full.rounds.find((x) => x.round === r);
    const used = new Set(byRound.get(r));
    const items = [...used].sort((a, b) => a - b).map((i) => ({ ...src.items[i], clip: i }));
    let next = items.length ? (Math.max(...items.map((x) => x.clip)) + 1) % src.items.length : 0;
    for (let k = 0; items.length < full.minClips && k < src.items.length * 2; k += 1) {
      if (!used.has(next)) {
        used.add(next);
        items.push({ ...src.items[next], clip: next });
      }
      next = (next + 1) % src.items.length;
    }
    items.sort((a, b) => a.clip - b.clip);
    return { round: r, condition: src.condition, label: src.label, ask: src.ask, items, wired: src.wired };
  });
  return { ...full, add: true, again: true, rounds };
}

/** How many rounds and recordings, in words, for the first screen. */
export function planLine(plan) {
  const p = obj(plan);
  if (p.missing) return "The new training plan is not on this PC yet.";
  const rounds = (Array.isArray(p.rounds) ? p.rounds : []).filter((r) => r.wired !== false);
  const n = rounds.reduce((sum, r) => sum + (Array.isArray(r.items) ? r.items.length : 0), 0);
  if (!rounds.length) return "Nothing is left to record in the plan on this PC.";
  const extra = p.wiredTotal < p.total
    ? ` The plan has ${p.total} conditions; this desktop build records ${p.wiredTotal}.` : "";
  return `${rounds.length === 1 ? "1 round" : `${rounds.length} rounds`} on this PC, ${n} recordings in all.${extra} Each round takes about a minute.`;
}

/** The four conditions in one sentence, for the screen before recording. */
export function conditionsLine(plan) {
  const rows = conditionRows(plan);
  if (!rows.length) return "";
  return `The conditions: ${rows.map((r) => r.label).join("; ")}.`;
}

/** `[{round, label, ask, wired}]` for every condition in the PC's plan. */
export function conditionRows(plan) {
  const p = obj(plan);
  const list = Array.isArray(p.conditions) ? p.conditions : [];
  return list.map((c, i) => ({
    round: Number(c.round) || i + 1,
    label: String(c.label || ""),
    ask: String(c.ask || ""),
    wired: c.wired !== false,
  }));
}

/**
 * The honest lines about the fourth condition: shown in the intro and on the
 * page before recording. Empty when every condition is wired.
 */
export function planLimitLines(plan) {
  const p = obj(plan);
  if (p.missing || !p.total || p.wiredTotal >= p.total) return [];
  const rows = conditionRows(p);
  const wired = rows.filter((r) => r.wired).map((r) => r.label);
  const unwired = rows.filter((r) => !r.wired).map((r) => r.label);
  const which = unwired.length === 1
    ? `The fourth - ${unwired[0]} -`
    : `The other ${unwired.length} - ${unwired.join("; ")} -`;
  return [
    `This desktop build records the first ${p.wiredTotal} of the ${p.total} conditions: ${wired.join("; ")}.`,
    `${which} is in the plan your PC sent, but this app's recording bridge cannot send it yet. Training ends after round ${p.wiredTotal}, so this PC will not have a sub-print for it.`,
  ];
}

/** The first screen. */
export function introLines(plan, status) {
  const p = obj(plan);
  const lines = [];
  if (p.missing) {
    lines.push("This PC has not sent the new four-condition training plan yet. Update the backend by running apply-patches.ps1, then open this again.");
    return lines;
  }
  const first = (Array.isArray(p.rounds) ? p.rounds : [])[0];
  const readPer = first ? first.items.filter((it) => it.kind !== "free").length : 0;
  if (p.again) {
    lines.push("Record again the recordings your PC left out, so it knows your voice in those conditions too. They are added to what it already knows; nothing it had is deleted.");
  } else if (p.add) {
    lines.push("Train more: these recordings are added to what Jarvis already knows about your voice on this PC. Nothing it had is deleted.");
  } else {
    lines.push(`Jarvis only listens to your voice. This training records ${p.readCount} short phrases - chosen to cover the vowels, the hard consonant clusters, and short, medium and long sentences - and ${p.freeCount} prompts in your own words, across ${p.total} listening conditions.`);
    if (readPer) {
      const free = p.freeCount ? `, and the first ${Math.min(3, p.total)} also ask one prompt in your own words` : "";
      lines.push(`Each round records ${readPer} of the phrases${free}. The fourth condition repeats ${readPer} phrases for its own sub-print.`);
    }
  }
  lines.push(...planLimitLines(p));
  lines.push("Speak normally, at the distance you usually sit from the microphone. Jarvis then asks you to approve the change on an approval card - nothing changes until you do. The recordings are kept in memory only, never saved to a file, and deleted once the card is answered.");
  return lines;
}

/**
 * The line over a round's clips: "Round 2 of 4: about two to three metres
 * away, on a table." The PC's own round numbers, because the ones it leaves
 * out are named by them. "" for an older PC's single round.
 */
export function roundLine(plan, index) {
  const p = obj(plan);
  const r = obj((p.rounds || [])[index]);
  if (p.legacy || p.missing || !r.round) return "";
  const ask = r.ask ? `: ${r.ask}.` : ".";
  if (r.wired === false) return `Round ${r.round} of ${p.total}${ask} This desktop build cannot record this one yet.`;
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
 * a microphone that heard nothing (the PC refuses a silent clip). `kind:
 * "free"` is a free-speech prompt, not a sentence to read aloud.
 */
export function clipProblem(taken, status, kind = "read") {
  const t = obj(taken);
  const lim = limits(status);
  if (num(t.peak) < 0.01) {
    return "That was silent. Check the microphone is plugged in and switched on, then record it again.";
  }
  if (num(t.seconds) < lim.minSeconds) {
    return kind === "free"
      ? "That was too short. Press Record, speak for a few seconds in your own words, then press Stop."
      : "That was too short. Press Record, read the whole sentence, then press Stop.";
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
  if (recorded < total) return `Record all ${total} recordings first (${recorded} done).`;
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

/** "round 2, recording 5" lists, joined in plain words. */
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
  const where = listWords(list.map((o) => `round ${o.round}, recording ${o.clip}`));
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

/* ── Live additions: caps, the drift guard, re-anchoring ─────────────── */

/** "21 September 2026", or "" when the PC has no time to give. */
export function dateWords(seconds) {
  const n = num(seconds);
  if (!n) return "";
  const when = new Date(n * 1000);
  if (Number.isNaN(when.getTime())) return "";
  return when.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}

/** Shown when the PC has not sent `gate.training.adaptation` at all. */
export const ADAPT_MISSING =
  "This PC has not sent its Live additions yet. Update the backend by running apply-patches.ps1, then open this again.";

/** The drift guard, in the PC's contract's own words. */
export const DRIFT_NOTE =
  "A clip that sounds too different from your enrolled voice is refused before it is counted, so one noisy day cannot become the print.";

/** Which Live checks may add a clip. */
export const LIVE_RULES_NOTE =
  "Only a clean, high-confidence Live check can add one: never side talk, a refusal, a crisis turn, a short clip, or a score only just over the bar.";

/**
 * The backend route (`POST /api/voice/enroll {"mode": "adapt-reset"}`) and the
 * desktop command (voice_training.rs `reset_voice_adaptation`) both exist. It
 * only zeroes counters and drops the live sub-prints; it never changes the
 * enrolled voice, so it raises no card.
 */
export const ADAPT_RESET_WIRED = true;
export const ADAPT_RESET_NOTE =
  "Reset the count: this zeroes the PC's Live-additions counters and drops the live sub-prints it kept. It never changes the voice it learned from your training.";

/**
 * The PC's Live additions (`gate.training.adaptation`) as counts and caps, or
 * null from a PC that does not report them. Every number is the PC's; nothing
 * is estimated, and a missing count reads as zero.
 */
export function adaptationView(status) {
  const raw = obj(obj(obj(status).gate).training).adaptation;
  if (!raw || typeof raw !== "object" || raw.available === false) return null;
  const caps = obj(raw.caps);
  const perCondition = count(caps.per_condition) || 4;
  const totalCap = count(caps.total) || 12;
  const counts = obj(raw.counts);
  const rows = CONDITIONS.map((c) => ({
    id: c.id,
    label: c.label,
    count: count(counts[c.id]),
    cap: perCondition,
  }));
  const total = count(raw.count) || rows.reduce((sum, r) => sum + r.count, 0);
  return {
    available: true,
    words: sentence(raw.words) || (total ? `${total} Live additions.` : "No Live additions yet."),
    count: total,
    caps: { perCondition, total: totalCap },
    rows,
    reanchors: count(raw.reanchors),
    lastReanchor: num(raw.last_reanchor),
    resets: count(raw.resets),
    resetAt: num(raw.reset_at),
    lastAt: num(raw.last_at),
  };
}

/**
 * The Live-additions block, in the PC's own words first and then the rules
 * that produced them. Empty from a PC that does not report the block; the
 * page then shows ADAPT_MISSING.
 */
export function adaptationLines(status) {
  const v = adaptationView(status);
  if (!v) return [];
  const lines = [v.words];
  for (const r of v.rows) lines.push(`${r.label}: ${r.count} of ${r.cap} Live additions.`);
  lines.push(`The cap is ${v.caps.perCondition} for each condition and ${v.caps.total} in all.`);
  if (v.reanchors) {
    const last = dateWords(v.lastReanchor);
    lines.push(`Re-anchored to your original enrollment ${v.reanchors} time${v.reanchors === 1 ? "" : "s"}${last ? `, the last on ${last}` : ""}.`);
  } else {
    lines.push("Not re-anchored yet. The PC goes back to your original enrollment every so often, so a run of Live clips cannot drift away from it.");
  }
  lines.push(DRIFT_NOTE);
  lines.push(LIVE_RULES_NOTE);
  if (v.resets) {
    const last = dateWords(v.resetAt);
    lines.push(`The count has been reset ${v.resets} time${v.resets === 1 ? "" : "s"}${last ? `, the last on ${last}` : ""}.`);
  }
  return lines;
}

/* ── Held-out measurement: FRR, FAR and the EER point ────────────────── */

/** What FRR and FAR mean, before a single number. */
export const HELD_OUT_INTRO =
  "FRR is how often your own voice would be turned away. FAR is how often someone else's voice would get in. EER is the point where those two are equally likely. Your PC gives a number for a condition only with at least 10 of your clips and 10 other-voice clips; otherwise it says what is missing, and no threshold is chosen.";

/** Shown before any guided test has run. */
export const HELD_OUT_NONE =
  "No guided test has run yet. Run the test above; your PC will say whether it has enough held-out scores for a number, and if not, exactly what is missing.";

/** "4 in 100" - a fraction as the plain count an owner can read. */
export function in100(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${Math.round(value * 100)} in 100` : "no number";
}

/**
 * The held-out report in the PC's own words: the full `mode=measure`
 * answer's `held_out`, or the reduced `measure_last.held_out` the status
 * keeps. `null` when there is no report to read at all. `thresholds_applied`
 * is never true (the contract says a default changes only through the
 * owner's measured card), and it is repeated here when the answer carries it.
 */
export function heldOutLines(source) {
  const r = obj(source);
  const held = r.held_out && typeof r.held_out === "object"
    ? obj(r.held_out)
    : ("conditions" in r ? r : null);
  if (!held) return null;
  const conditions = obj(held.conditions);
  const lines = [];
  const words = String(held.words || "").trim();
  // The full answer's `words` is the PC's own sentence; the reduced
  // measure_last keeps no wording, so say what its shape means instead.
  lines.push(words ? sentence(words)
    : (held.available === false
      ? "Not enough held-out scores yet; no threshold was chosen."
      : "The held-out numbers are below."));
  for (const [id, raw] of Object.entries(conditions)) {
    const row = obj(raw);
    const label = (CONDITIONS.find((c) => c.id === id) || {}).label || id;
    if (row.available === true) {
      let line = `${label}: your own voice would be refused ${in100(row.frr)} (FRR); other voices would get in ${in100(row.far)} (FAR)`;
      if (typeof row.eer === "number") line += `; the two are equally likely at ${in100(row.eer)} (EER)`;
      lines.push(`${line}.`);
    } else {
      const why = String(row.why || "").trim();
      lines.push(`${label}: ${why ? sentence(why) : "not enough measured rows yet, so no number."}`);
    }
  }
  if (r.thresholds_applied === false) {
    lines.push("No threshold was changed. A measured bar only changes with your approval.");
  }
  return lines;
}

/* ── How strict, and private answers ──────────────────────────────────── */

const SETTING_NAMES = {
  strictness: "how strict the voice check is",
  privacy: "private answers",
  memory: "answers that use what Jarvis remembers",
  sensitive_memory: "answers that use sensitive saved facts",
  hands_free: "how far \"Hey Jarvis\" is trusted",
  hands_free_screen: "answers about your screen or the camera after \"Hey Jarvis\"",
  hands_free_live: "how far Jarvis Live is trusted",
  live_end: "when Jarvis Live ends on this PC",
  talk_to_type: "talk-to-type",
  wake_confirm: "the second \"hey Jarvis\" check",
  voice_id_model: "the voice-ID model",
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

/**
 * The owner's decision of 2026-09-28: under "Only trust the talk button",
 * an answer about the screen ("Look at this", "Watch with me") to a
 * question started with "Hey Jarvis" stays on screen, with this setting to
 * allow reading it aloud even then. Keeping it on screen is the default and
 * applies at once; "Read aloud" is the looser choice - the voice card, and
 * held on a stale link. Under "Same as the talk button" it changes nothing
 * (`SCREEN_ONLY_WHEN_STRICT_NOTE`).
 */
export const HANDS_FREE_SCREEN = Object.freeze([
  {
    id: "screen_on_screen",
    label: "Keep on screen",
    recommended: true,
    detail: "With \"Only trust the talk button\" chosen, a question about your screen or the camera that starts with \"Hey Jarvis\" gets a written answer only.",
  },
  {
    id: "screen_aloud",
    label: "Read aloud",
    detail: "Those answers are read aloud, even with \"Only trust the talk button\" chosen. Anyone near the speaker will hear them.",
  },
]);

/**
 * Jarvis Live under "Only trust the talk button" (the owner's answers of
 * 2026-09-28): a Live session is trusted like the talk button by default,
 * however it was started - the owner pressed Start, or said "Hey Jarvis,
 * let's talk". Two stricter choices apply at once; each looser one is the
 * voice card, held on a stale link. The phone's StrictVoice.HANDS_FREE_LIVE
 * has the same words. Under "Same as the talk button" it changes nothing
 * (`LIVE_ONLY_WHEN_STRICT_NOTE`).
 */
export const HANDS_FREE_LIVE = Object.freeze([
  {
    id: "live_trust_fully",
    label: "Trust Live fully",
    isDefault: true,
    detail: "What you say in Jarvis Live is trusted like the talk button, however you started Live.",
  },
  {
    id: "live_button_start_only",
    label: "Only when I start it with the button",
    detail: "A Live you start with the button is trusted like the talk button. One started by saying \"Hey Jarvis, let's talk\" gets the \"Hey Jarvis\" caution.",
  },
  {
    id: "live_like_hey_jarvis",
    label: "Be as careful as with \"Hey Jarvis\"",
    detail: "Everything said in Jarvis Live gets the \"Hey Jarvis\" caution: no facts learned without a card, and memory or private answers stay on screen.",
  },
]);

/**
 * When App lock ends Jarvis Live on this PC (the owner's decision of
 * 2026-09-28): by default when App lock would ask again ("Lock again
 * after", counted from when you last touched a Jarvis window - talking does
 * not count); the looser choice, only when Windows itself locks, is the
 * voice card, held on a stale link. A PC setting - the phone keeps App
 * lock's own rule (docs/ARCHITECTURE.md section 8).
 */
export const LIVE_END = Object.freeze([
  {
    id: "live_end_app_lock",
    label: "When App lock would ask again",
    recommended: true,
    detail: "With App lock on, Jarvis Live ends when App lock would ask for Windows Hello again (\"Lock again after\" in Security), counted from when you last touched a Jarvis window. Talking does not count.",
  },
  {
    id: "live_end_windows_lock",
    label: "Only when Windows locks",
    detail: "Jarvis Live keeps going until Windows itself locks, even after App lock would ask again. Someone who sits down at this PC before then could talk to Jarvis.",
  },
]);

/** Under the Live end choices: what they depend on. */
export const LIVE_END_NOTE = "This only matters while App lock is on (Settings, Security).";

/** Under the Live choices while "Same as the talk button" is chosen. */
export const LIVE_ONLY_WHEN_STRICT_NOTE =
  "This only matters when \"Only trust the talk button\" is chosen above. With \"Same as the talk button\", Jarvis Live is trusted like the talk button already.";

/** Whether the Live setting does nothing now (see LIVE_ONLY_WHEN_STRICT_NOTE). */
export function liveCovered(view) {
  return Boolean(view && view.handsFree === "same_as_button");
}

/** Under the screen choices while "Same as the talk button" is chosen:
 *  then answers about the screen are read aloud already, so this setting
 *  changes nothing. The choices stay usable - it takes over if the
 *  hands-free choice changes. */
export const SCREEN_ONLY_WHEN_STRICT_NOTE =
  "This only matters when \"Only trust the talk button\" is chosen above. With \"Same as the talk button\", answers about your screen or the camera are read aloud already.";

/** Whether the screen setting does nothing now (see SCREEN_ONLY_WHEN_STRICT_NOTE). */
export function screenCovered(view) {
  return Boolean(view && view.handsFree === "same_as_button");
}

/**
 * Talk-to-type on this PC (the owner's decision, 2026-09-27; talk_type.rs;
 * docs/JARVIS-API.md section 72). Off by default. On is the looser choice:
 * one approval card, then no card each time. Off is at once.
 */
export const TALK_TO_TYPE = Object.freeze([
  {
    id: "off",
    label: "Off",
    isDefault: true,
    detail: "Nothing listens for the talk-to-type key.",
  },
  {
    id: "on",
    label: "On",
    detail: "Hold the talk-to-type key (Alt+Shift+T unless you changed it under Shortcuts) and speak, then let go: Jarvis types what you said into the program in front. A quick tap keeps it listening until you tap again. Your voice is checked first and the words are made on this PC; they are not kept in chat history. It never types into a password box, or while Jarvis is locked.",
  },
]);

/**
 * "Better voice" (the owner's group, 2026-09-28; docs/JARVIS-API.md section
 * 80). A second "hey Jarvis" detector that must agree with the first. One
 * detector is the default (today's behaviour); two is the stricter choice
 * and applies at once; going back to one is the voice card. Two cannot be
 * chosen while the PC does not have the second detector (the PC's words
 * say why: `gate.settings.blocked.wake_confirm`).
 */
export const WAKE_CONFIRM = Object.freeze([
  {
    id: "one",
    label: "One detector",
    isDefault: true,
    detail: "One detector listens for \"hey Jarvis\", as before. Your voice is still checked every time before anything is written down or done.",
  },
  {
    id: "both",
    label: "Two detectors must agree",
    detail: "A second, differently built detector (microWakeWord) must also hear \"hey Jarvis\" within a second. Fewer false wake-ups; it may miss you a little more often. Measure it on your PC first (the backend README, \"Better voice\").",
  },
]);

/**
 * Which stronger voice-ID model tells the owner's voice from other people's
 * (the same day). The measured one is the default and applies at once; the
 * newer, unmeasured one is the voice card, and cannot be chosen until its
 * file is on the PC (`gate.settings.blocked.voice_id_model`). Nothing
 * switches by itself.
 */
export const VOICE_ID_MODEL = Object.freeze([
  {
    id: "titanet",
    label: "The stronger one (measured)",
    recommended: true,
    detail: "NVIDIA's TitaNet. Its bars were measured on real voices. It tells your voice from other people's. It cannot tell your voice from a recording or a copy of it.",
  },
  {
    id: "resnet221",
    label: "The newer one (not measured yet)",
    detail: "WeSpeaker's ResNet221. Not measured on real voices here, so Jarvis cannot say how well it keeps other people out; on computer-made voices it let in far more of them. It is slower, too. It cannot tell your voice from a recording or a copy of it either.",
  },
]);

function choiceWords(setting, value) {
  const list = setting === "strictness" ? STRICTNESS : setting === "privacy" ? PRIVACY
    : setting === "memory" ? MEMORY : setting === "sensitive_memory" ? SENSITIVE_MEMORY
      : setting === "hands_free" ? HANDS_FREE : setting === "hands_free_screen" ? HANDS_FREE_SCREEN
        : setting === "hands_free_live" ? HANDS_FREE_LIVE : setting === "live_end" ? LIVE_END
          : setting === "talk_to_type" ? TALK_TO_TYPE : setting === "wake_confirm" ? WAKE_CONFIRM
            : setting === "voice_id_model" ? VOICE_ID_MODEL : [];
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
      : setting === "hands_free" ? view.handsFree
        : setting === "hands_free_screen" ? view.handsFreeScreen
          : setting === "hands_free_live" ? view.handsFreeLive
            : setting === "live_end" ? view.liveEnd
              : setting === "talk_to_type" ? view.talkToType
                : setting === "wake_confirm" ? view.wakeConfirm
                  : setting === "voice_id_model" ? view.voiceIdModel : "";
}

/** Whether choosing `value` for `setting` loosens it (a card), by the server's rule.
 *  `current` matters for Jarvis Live's three choices only: a move towards
 *  "Trust Live fully" loosens; an unknown one counts as from the strictest. */
export function loosens(setting, value, current = "") {
  if (setting === "hands_free_live") {
    const order = HANDS_FREE_LIVE.map((c) => c.id);
    const v = order.indexOf(value);
    const c = order.indexOf(current);
    if (v < 0) return true;
    return v < (c < 0 ? order.length - 1 : c);
  }
  return (setting === "strictness" && value === "balanced") || (setting === "privacy" && value === "voice_is_enough")
    || (setting === "memory" && value === "memory_aloud")
    || (setting === "sensitive_memory" && value === "sensitive_aloud")
    || (setting === "hands_free" && value === "same_as_button")
    || (setting === "talk_to_type" && value === "on")
    || (setting === "wake_confirm" && value === "one")
    || (setting === "voice_id_model" && value === "resnet221")
    || (setting === "hands_free_screen" && value === "screen_aloud")
    || (setting === "live_end" && value === "live_end_windows_lock");
}

/** The choice of each "Better voice" setting that needs something installed. */
const NEEDS_INSTALL = Object.freeze({ wake_confirm: "both", voice_id_model: "resnet221" });

/**
 * Why `value` cannot be chosen for `setting` on this PC now - the PC's own
 * words (`gate.settings.blocked`), as a sentence - or "" when it can. Only
 * the two "Better voice" choices that need something installed; a choice
 * that is already on is never blocked (going back is always allowed).
 */
export function blockedWhy(status, setting, value) {
  if (NEEDS_INSTALL[setting] !== value) return "";
  if (currentSetting(status, setting) === value) return "";
  const blocked = obj(obj(obj(obj(status).gate).settings).blocked);
  return sentence(blocked[setting]);
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
  // The sixth, answers about the screen after "Hey Jarvis" (the owner's
  // decision of 2026-09-28): `gate.settings.hands_free_screen` (or
  // `gate.hands_free_screen`). "" from a PC that does not have it - not
  // offered.
  const rawScreen = s.hands_free_screen !== undefined ? s.hands_free_screen : gate.hands_free_screen;
  const handsFreeScreen = rawScreen === "screen_on_screen" || rawScreen === "screen_aloud" ? rawScreen : "";
  // The seventh, Jarvis Live (the owner's answers of 2026-09-28):
  // `gate.settings.hands_free_live` (or `gate.hands_free_live`). "" from a
  // PC that does not have it - not offered.
  const rawLive = s.hands_free_live !== undefined ? s.hands_free_live : gate.hands_free_live;
  const handsFreeLive = HANDS_FREE_LIVE.some((c) => c.id === rawLive) ? rawLive : "";
  // The eighth, when App lock ends Jarvis Live on this PC (the owner's
  // decision of 2026-09-28): `gate.settings.live_end` (or `gate.live_end`).
  // "" from a PC that does not have it - not offered.
  const rawEnd = s.live_end !== undefined ? s.live_end : gate.live_end;
  const liveEnd = LIVE_END.some((c) => c.id === rawEnd) ? rawEnd : "";
  // Talk-to-type (2026-09-28): `gate.settings.talk_to_type` (or
  // `gate.talk_to_type`). "" from a PC that does not have it - not offered.
  const rawTalk = s.talk_to_type !== undefined ? s.talk_to_type : gate.talk_to_type;
  const talkToType = rawTalk === "off" || rawTalk === "on" ? rawTalk : "";
  // "Better voice" (2026-09-28): "" from a PC that does not have them - not
  // offered. Any other value is read as the strict one, never the looser.
  const rawConfirm = s.wake_confirm !== undefined ? s.wake_confirm : gate.wake_confirm;
  const wakeConfirm = rawConfirm === undefined || rawConfirm === null || rawConfirm === ""
    ? "" : rawConfirm === "one" ? "one" : "both";
  const rawModel = s.voice_id_model !== undefined ? s.voice_id_model : gate.voice_id_model;
  const voiceIdModel = rawModel === undefined || rawModel === null || rawModel === ""
    ? "" : rawModel === "resnet221" ? "resnet221" : "titanet";
  return {
    wakeConfirm,
    voiceIdModel,
    strictness,
    privacy,
    memory,
    sensitiveMemory,
    handsFree,
    handsFreeScreen,
    handsFreeLive,
    liveEnd,
    talkToType,
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

/** What the PC answered to the guided test, in words: `{lines, heldOut, tone}`. */
export function measureReply(answer) {
  const a = obj(answer);
  if (a.error) return { lines: [sentence(a.error)], heldOut: [], tone: "bad" };
  const lines = a.ok === true ? measureLines(a) : null;
  const heldOut = a.ok === true ? (heldOutLines(a) || []) : [];
  return lines
    ? { lines, heldOut, tone: "ok" }
    : { lines: ["Your PC did not say how the test went."], heldOut: [], tone: "bad" };
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
