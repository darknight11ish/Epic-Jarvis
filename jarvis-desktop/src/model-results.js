/**
 * model-results.js - the Brain Model pane's "Measured results" card (2026-11-09).
 *
 * WHAT IT SHOWS. The benchmark results that are ALREADY stored on this PC, from
 * the two stores `docs/JARVIS-API.md` section 205 answers "what has been
 * measured" from: `jarvis_bench.BenchLog` (speed runs, `bench.jsonl`) and
 * `jarvis_bench.ScoreLog` (the five-suite scorecards, `bench-scores.jsonl`).
 * The backend copies rows out with `GET /api/models/measured`
 * (`jarvis_model_resources.measured()`); this module turns that answer into the
 * card's plain words, and `brain.js` draws it.
 *
 * WHAT IT MUST NEVER DO. Invent a number, a score or a result. Every figure on
 * the card is a stored field, and the sentence describing a measurement is the
 * store's OWN `words` field, word for word - `jarvis_bench` wrote it when it
 * measured the row, so a spilled run can never be re-worded as a fast one. A
 * row with no stored sentence says exactly that instead of being rewritten. An
 * empty list keeps the backend's own reason (which file is missing, which door
 * starts a run) rather than a generic "nothing here".
 *
 * It holds no DOM, no token, no network call and no state, so every sentence is
 * proved by `jarvis-desktop/tests/model-results.mjs` with no browser and no GPU.
 */
import { readTimeWords } from "./model-resources.js";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July",
  "August", "September", "October", "November", "December"];

/** What a card says when the backend did not report measured results at all. */
export const NEVER_REPORTED =
  "This backend does not report measured results, so this card has nothing to "
  + "show. Nothing here is guessed at.";

/** A stored number, or null - never 0 for a number the row does not hold. */
function storedNumber(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** `2026-11-08` -> "8 November 2026"; "" when the row carries no real date. */
export function dayWords(day) {
  const text = String(day || "").trim();
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
  if (!match) return "";
  const year = Number(match[1]);
  const month = Number(match[2]);
  const date = Number(match[3]);
  if (!year || month < 1 || month > 12 || date < 1 || date > 31) return "";
  return `${date} ${MONTHS[month - 1]} ${year}`;
}

/** A stored figure, as short plain text: `83.3`, not `83.333333`. */
function figureWords(value) {
  const number = storedNumber(value);
  if (number === null) return "";
  return Number.isInteger(number) ? String(number)
    : String(Math.round(number * 10) / 10);
}

/** The stored score as a short figure - "" when the row holds no score. */
export function scoreFigure(card) {
  if (!card || typeof card !== "object") return "";
  const bits = [];
  const percent = figureWords(card.score_pct);
  if (percent) bits.push(`${percent}%`);
  const items = figureWords(card.items);
  const passed = figureWords(card.items_passed);
  if (items && passed) bits.push(`${passed} of ${items} tasks`);
  return bits.join(" ");
}

/** One stored speed run, in the card's words. */
export function speedRow(run) {
  if (!run || typeof run !== "object") return null;
  const model = String(run.model || "").trim() || "a model";
  const lane = String(run.lane || "").trim();
  const title = lane ? `${model} on the ${lane} lane` : model;
  const meta = [];
  const day = dayWords(run.day);
  if (day) meta.push(`measured ${day}`);
  if (run.spilled) {
    meta.push("some layers spilled into system RAM, so this number is not "
      + "comparable with a fully-on-card run");
  }
  if (run.ok === false) meta.push("that run failed");
  const stored = String(run.words || "").trim();
  const why = String(run.why || "").trim();
  return {
    key: `run:${model}:${run.at == null ? "" : run.at}`,
    title,
    meta: meta.join("; "),
    words: stored || (why ? `This run failed: ${why}` : "No sentence was stored for this run."),
    failed: run.ok === false,
    spilled: Boolean(run.spilled),
  };
}

/** One stored five-suite scorecard, in the card's words. */
export function scoreRow(card) {
  if (!card || typeof card !== "object") return null;
  const suite = String(card.suite_label || card.suite || "").trim() || "a suite";
  const model = String(card.model || "").trim() || "a model";
  const meta = [];
  const day = dayWords(card.day);
  if (day) meta.push(`measured ${day}`);
  if (card.skipped) meta.push("this suite was not run on that model");
  else if (card.passed === false) meta.push("this suite did not pass");
  const figure = scoreFigure(card);
  if (figure) meta.push(figure);
  const context = storedNumber(card.ctx);
  if (context !== null && context > 0) {
    meta.push(`${Number(context).toLocaleString("en-US")} tokens of context`);
  }
  const quant = String(card.quant || "").trim();
  if (quant) meta.push(quant);
  const stored = String(card.words || "").trim();
  let words = stored;
  if (!words) {
    words = card.skipped
      ? "This suite was not run on that model, and the store kept no sentence for it."
      : "No sentence was stored for this scorecard.";
  }
  return {
    key: `score:${model}:${String(card.suite || "")}:${card.at == null ? "" : card.at}`,
    title: `${suite} on ${model}`,
    meta: meta.join("; "),
    words,
    skipped: Boolean(card.skipped),
    passed: card.passed,
  };
}

/** "Showing the newest 3 of 12 speed runs." - "" when there are none. */
export function countWords(kind, shown, total) {
  const have = storedNumber(total);
  const see = storedNumber(shown);
  if (have === null || see === null || have <= 0) return "";
  return see < have
    ? `Showing the newest ${see} of ${have} ${kind} on file.`
    : `${have} ${kind} on file.`;
}

/** Why a list is empty, in the backend's own words (or an honest default). */
export function emptyWords(payload) {
  const empty = (payload && payload.empty) || {};
  return {
    runs: String(empty.runs || "").trim()
      || "No speed run has been recorded on this PC yet, so there is nothing "
      + "measured to show. A speed run is what \"Benchmark on this PC\" on a "
      + "model starts.",
    scorecards: String(empty.scorecards || "").trim()
      || "No five-suite scorecard has been recorded on this PC yet, so there is "
      + "nothing measured to show. Asking Jarvis to \"start the benchmark "
      + "suites\" measures all five.",
  };
}

/** Where the rows came from, and what this card cannot do. */
export function sourceWords(payload) {
  const stores = (payload && payload.stores) || {};
  const speed = String((stores.speed || {}).name || "").trim();
  const scores = String((stores.scores || {}).name || "").trim();
  const where = speed && scores
    ? `Read from ${speed} (speed runs) and ${scores} (five-suite scorecards) on this PC.`
    : "Read from the two benchmark stores this PC keeps for speed runs and five-suite scorecards.";
  return `${where} Read-only: this card only read them - it starts no run and changes no number.`;
}

/** The whole card, as plain data `brain.js` draws without inventing a word. */
export function measuredModel(payload) {
  const body = payload || {};
  if (body.available === false) {
    return {
      available: false,
      why: String(body.why || "").trim() || NEVER_REPORTED,
      readAt: "",
      runs: [],
      scorecards: [],
      empty: { runs: "", scorecards: "" },
      counts: { runs: 0, scorecards: 0 },
      shown: { runs: 0, scorecards: 0 },
      note: "",
      source: "",
    };
  }
  const runs = (Array.isArray(body.runs) ? body.runs : []).map(speedRow).filter(Boolean);
  const scorecards = (Array.isArray(body.scorecards) ? body.scorecards : [])
    .map(scoreRow).filter(Boolean);
  const counts = body.counts || {};
  const totalRuns = storedNumber(counts.runs);
  const totalScores = storedNumber(counts.scorecards);
  const empty = emptyWords(body);
  return {
    available: true,
    why: "",
    readAt: readTimeWords(body),
    runs,
    scorecards,
    empty,
    counts: {
      runs: totalRuns === null ? runs.length : totalRuns,
      scorecards: totalScores === null ? scorecards.length : totalScores,
    },
    shown: { runs: runs.length, scorecards: scorecards.length },
    note: (runs.length || scorecards.length)
      ? "Every number on this card was measured on this PC and copied from its "
        + "benchmark store."
      : "",
    source: sourceWords(body),
  };
}
