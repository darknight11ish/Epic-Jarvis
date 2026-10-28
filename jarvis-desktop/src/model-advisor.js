/**
 * model-advisor.js - "Check for new models", a benchmark measured here, and the
 * preset recommendation the owner can approve or argue with.
 *
 * THE OWNER'S ASK, verbatim (2026-10-28): *"can you give jarvis the ability to
 * recommend a change to presets (for the local ai models being used) with a one
 * click check for new models button and it will look on hugging face for newer
 * potentially better models, give me a card to approve a download and a bench
 * mark testing locally, then it will recommend changing the presets based on the
 * local gpus and what model goes where and i can approve or give my opinion and
 * jarvis can change the preset recommendations then i approve?"*
 *
 * WHAT THIS MODULE IS. The reading half of that feature: it turns the PC's four
 * answers into rows and into words, and it names the one bridge command and the
 * four action names. It holds no DOM, no token, no network call and no state -
 * `brain.js` draws it, so every sentence here can be proved by a node test
 * without a browser, and the page cannot grow a second copy of a sentence that
 * has to stay true.
 *
 * WHAT IT MUST NEVER SAY. A newer model is not a better model. Nothing here
 * calls a candidate "better", "faster" or "an upgrade" unless the PC's own
 * answer carried a measurement from this PC - a `why` the PC wrote, or a
 * benchmark this module parsed. The lede says the honest thing in that case, and
 * a benchmark line carries the words "measured on this PC" only when a speed
 * really came back.
 *
 * NOTHING DOWNLOADS AND NOTHING IS APPLIED HERE. The download is the EXISTING
 * carded `/api/models/install` (Brain `brain_model`), and applying a preset is
 * the EXISTING carded `/api/work/apply` (`focus-presets-bridge.js`). Both are
 * separate, both raise the PC's own one card, and this module never names either
 * route. A check only asks the PC to look.
 *
 * THE FOUR ACTIONS, and the routes they reach in Rust (`src-tauri/src/brain.rs`,
 * `model_recommend_request`; the window names an action, never a URL):
 *
 *   check     -> POST /api/models/check               the Hugging Face lookup
 *   benchmark -> POST /api/models/benchmark {ref}     a local measurement
 *   recommend -> POST /api/presets/recommend          preset changes only
 *   opinion   -> POST /api/presets/recommend/opinion {text}  revised changes
 *
 * The GET `/api/models/recommendations` (the last answer, when the view opens)
 * is the Brain's own read section, not this module's.
 *
 * @module model-advisor
 */

/** The one bridge command. Rust owns the routes. */
export const ADVISOR_COMMAND = "brain_model_recommend";

/** The four action names, exactly as Rust accepts them. */
export const ACTION_CHECK = "check";
export const ACTION_BENCHMARK = "benchmark";
export const ACTION_RECOMMEND = "recommend";
export const ACTION_OPINION = "opinion";

/**
 * How long the page waits, per action.
 *
 * Each is a little longer than Rust's own wait for the same action (check 120 s,
 * recommend 90 s, opinion 150 s, benchmark 540 s), so the PC's refusal or its
 * "did not answer in time" reaches the owner BEFORE the page gives up - the same
 * rule `invoke-budget.js` already states for the preset apply. `invoke-budget.js`
 * has one budget per command and this command has four different jobs, so the
 * advisor passes its own size through `call`'s optional budget.
 */
export const BUDGETS_MS = Object.freeze({
  [ACTION_CHECK]: 150_000,
  [ACTION_RECOMMEND]: 120_000,
  [ACTION_OPINION]: 180_000,
  [ACTION_BENCHMARK]: 600_000,
});

/** Rust's cap on an opinion note, repeated here so the box refuses first. */
export const OPINION_MAX_CHARS = 2_000;

/* ── The honest words ────────────────────────────────────────────────────── */

/** What the panel says before the owner has asked for anything. */
export const NOT_CHECKED_YET =
  "Not checked yet. Check for new models asks Jarvis to look on Hugging Face for " +
  "models that fit your graphics cards. Nothing downloads from the check.";

/** This PC's Jarvis has no advisor (a 404 or 503), which is a fact, not a fault. */
export const MISSING_MODULE =
  "This PC's Jarvis does not have the model advisor yet. Update the backend by " +
  "running apply-patches.ps1, then open this again.";

/** A lookup that worked and found nothing worth suggesting. */
export const NO_CANDIDATES =
  "The PC looked and found no newer model it would suggest for these graphics cards.";

/** An answer that is not the shape the contract promises. */
export const UNREADABLE =
  "The PC's answer about newer models could not be read, so nothing is shown " +
  "from it. Try again, and update the backend if this keeps happening.";

/** Said under the list whenever no measurement of any kind came back. */
export const NOT_MEASURED =
  "Nothing here has been measured on this PC yet. This is a list of models that " +
  "fit its graphics cards — not a claim that any of them is better.";

/** Said instead when the PC's answer says it has measurements. */
export const MEASURED_SOMEWHERE =
  "Some of these have been measured on this PC. Those numbers are the PC's own; " +
  "the rest are still only a fit.";

/**
 * Said once under the candidate list: the catalogue carries no file hash, so no
 * SHA-256 is shown. Saying it out loud is the honest alternative to inventing
 * one, and it is also why a downloaded file cannot be checked against a hash
 * here yet.
 */
export const NO_HASH =
  "No SHA-256 is shown: the catalogue Jarvis reads reports no file hash, so none " +
  "is invented here.";

/** Every download is the existing carded install: say so where the button is. */
export const DOWNLOAD_IS_CARDED =
  "Download asks the PC to install the model on its usual approval card. " +
  "Nothing downloads until you approve that card.";

/** The benchmark, in the owner's words, with the label the contract asks for. */
export const MEASURED_LABEL = "Measured on this PC";

/** A model that is not installed cannot be benchmarked - say why, not "failed". */
export const NOT_INSTALLED =
  "That model is not installed on this PC, so there is nothing to measure yet. " +
  "Download it first, and benchmark it once the install finishes.";

/** The PC answered a benchmark with no speed in it. */
export const NO_SPEED =
  "The PC answered, but it did not report a speed, so this is not a measurement.";

/* ── Small reading helpers (pure) ────────────────────────────────────────── */

const text = (v) => (typeof v === "string" ? v.trim() : "");
const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** Thousands separators without a locale, so a test reads the same number. */
function grouped(n) {
  const s = String(Math.round(n));
  return s.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/** A context length the way a person reads it: 32768 -> "32,768 tokens". */
export function contextWords(tokens) {
  const n = num(tokens);
  if (n === null || n <= 0) return "";
  return `${grouped(n)} tokens of context`;
}

/** A size in GB, one decimal - the unit the contract's `size_gb` is in. */
export function sizeWords(gb) {
  const n = num(gb);
  if (n === null || n <= 0) return "";
  return `${n.toFixed(1)} GB`;
}

/** Bytes (a benchmark may report `vram_mb`), shown as GB with one decimal. */
export function vramWords(result) {
  if (!result || typeof result !== "object") return "";
  const mb = num(result.vram_mb);
  if (mb !== null && mb > 0) return `${(mb / 1024).toFixed(1)} GB of graphics memory`;
  const gb = num(result.vram_gb);
  if (gb !== null && gb > 0) return `${gb.toFixed(1)} GB of graphics memory`;
  const bytes = num(result.vram_bytes);
  if (bytes !== null && bytes > 0) return `${(bytes / 1024 ** 3).toFixed(1)} GB of graphics memory`;
  return "";
}

/**
 * One candidate's fit, in the three words the contract allows plus one honest
 * non-answer. Never guesses: a missing or unknown fit says so.
 */
export function fitWords(fit) {
  const value = text(fit).toLowerCase();
  if (value === "fits") return { label: "fits", state: "ok" };
  if (value === "tight") return { label: "tight", state: "warn" };
  if (value === "no") return { label: "does not fit", state: "bad" };
  return { label: "fit not reported", state: "" };
}

/** The ref, without Ollama's implicit `:latest`, for comparing two names. */
export function bareRef(ref) {
  return text(ref).replace(/:latest$/i, "");
}

/**
 * One candidate, normalized. `null` when it has no usable name, because a row
 * with no name has no Download button that could mean anything.
 */
export function candidateRow(candidate) {
  if (!candidate || typeof candidate !== "object") return null;
  const ref = text(candidate.ref);
  if (!ref) return null;
  const fit = fitWords(candidate.fit);
  return {
    ref,
    name: text(candidate.name) || ref,
    family: text(candidate.family),
    paramsB: num(candidate.params_b),
    quant: text(candidate.quant),
    sizeGb: num(candidate.size_gb),
    contextTokens: num(candidate.context_tokens),
    licence: text(candidate.licence),
    fit: text(candidate.fit).toLowerCase(),
    fitLabel: fit.label,
    fitState: fit.state,
    why: text(candidate.why),
    sourceUrl: text(candidate.source_url),
  };
}

/** Every usable candidate in the PC's answer, in the PC's own order. */
export function candidateRows(payload) {
  const list = payload && Array.isArray(payload.candidates) ? payload.candidates : [];
  return list.map(candidateRow).filter(Boolean);
}

/**
 * The meta lines for one candidate: what it is and what it costs, in the PC's
 * numbers. Each is left out when the PC did not say it - no zeroes, no guesses.
 */
export function candidateMeta(row) {
  if (!row || typeof row !== "object") return [];
  const lines = [];
  if (row.sizeGb) lines.push(sizeWords(row.sizeGb));
  if (row.quant) lines.push(`${row.quant} quantization`);
  // The licence is shown when the catalogue reports one, and said plainly when
  // it does not - never guessed from the model's name or size.
  lines.push(row.licence ? `licence ${row.licence}` : "licence not reported by the catalogue");
  if (row.paramsB) lines.push(`${row.paramsB}B parameters`);
  if (row.family) lines.push(row.family);
  if (row.contextTokens) lines.push(contextWords(row.contextTokens));
  if (row.name && row.ref && row.name !== row.ref) lines.push(row.ref);
  if (row.why) lines.push(row.why);
  return lines;
}

/**
 * Does this answer carry ANY measurement? `benchmarked` is the PC's index
 * (ref -> measurement), so a non-empty object is the real signal; `true` is
 * accepted too for a body that only says "yes". Used to choose the honest note
 * under the list, never to promote a candidate that has no numbers of its own.
 */
export function anyMeasured(payload) {
  const bench = payload && payload.benchmarked;
  if (bench === true) return true;
  return Boolean(bench && typeof bench === "object" && Object.keys(bench).length);
}

/** The refs the PC already has installed, from the Models body. */
export function installedRefs(modelsBody) {
  const out = new Set();
  const list = modelsBody && Array.isArray(modelsBody.installed) ? modelsBody.installed : [];
  for (const entry of list) {
    const ref = bareRef(typeof entry === "string" ? entry : entry && (entry.ref || entry.name || entry.model));
    if (ref) out.add(ref);
  }
  return out;
}

/** Is this candidate already on this PC? (The same comparison `Use` uses.) */
export function isInstalled(ref, installed) {
  if (!installed) return false;
  const bare = bareRef(ref);
  if (!bare) return false;
  if (installed.has && installed.has(bare)) return true;
  if (Array.isArray(installed)) return installed.some((r) => bareRef(r) === bare);
  return false;
}

/* ── Benchmarks ──────────────────────────────────────────────────────────── */

/**
 * The PC's benchmark answer, as lines the owner can read, and whether it really
 * is a measurement.
 *
 * `measured` is true only when a finite, positive speed came back. VRAM and
 * context alone are facts about a run, not a measurement of one, so a body with
 * those and no speed says [`NO_SPEED`] rather than wearing the label.
 */
export function benchmarkWords(result) {
  const out = { measured: false, lines: [], why: "" };
  if (result === null || result === undefined) {
    out.why = "The PC did not answer with a measurement.";
    return out;
  }
  if (typeof result !== "object") {
    out.why = UNREADABLE;
    return out;
  }
  if (result.available === false) {
    out.why = text(result.why) || text(result.error) || "The PC has no benchmark for this model.";
    return out;
  }
  if (result.ok === false) {
    out.why = text(result.error) || text(result.why) || "The PC refused the benchmark.";
    return out;
  }
  const speed =
    num(result.tokens_per_s) ?? num(result.tokens_per_second) ?? num(result.tokensPerSecond) ?? num(result.tok_s);
  const vram = vramWords(result);
  const context = contextWords(result.context_tokens ?? result.context ?? result.n_ctx);
  if (speed !== null && speed > 0) {
    out.lines.push(`${speed.toFixed(1)} tokens a second`);
    out.measured = true;
  }
  if (vram) out.lines.push(vram);
  if (context) out.lines.push(context);
  if (!out.measured) out.why = out.lines.length ? NO_SPEED : "The PC's benchmark answer had no numbers in it.";
  return out;
}

/** The one benchmark sentence, label first: "Measured on this PC: …". */
export function benchmarkLine(result) {
  const words = benchmarkWords(result);
  if (!words.measured) return "";
  return `${MEASURED_LABEL}: ${words.lines.join(", ")}.`;
}

/* ── GPU and time labels ─────────────────────────────────────────────────── */

/**
 * The graphics cards the PC said it measured against. A string entry is shown as
 * it came; an object uses the field names this desktop already reads elsewhere
 * (`hardware.rs`: `name`, `total_mb`). Nothing is invented for a card the PC did
 * not describe.
 */
export function gpuWords(gpus) {
  if (!Array.isArray(gpus)) return [];
  const out = [];
  for (const gpu of gpus) {
    if (typeof gpu === "string") {
      if (gpu.trim()) out.push(gpu.trim());
      continue;
    }
    if (!gpu || typeof gpu !== "object") continue;
    const name = text(gpu.name) || text(gpu.gpu) || `graphics card ${gpu.index ?? ""}`.trim();
    const gb = num(gpu.vram_gb) ?? (num(gpu.total_mb) !== null ? num(gpu.total_mb) / 1024 : null);
    out.push(gb && gb > 0 ? `${name} (${gb.toFixed(1)} GB)` : name);
  }
  return out;
}

/**
 * When the PC last checked, in words. Accepts epoch seconds, epoch milliseconds
 * or an ISO date; returns "" when it does not say, so the caller can say that
 * instead of inventing "just now".
 */
export function checkedWords(value, now = Date.now()) {
  let at = null;
  if (typeof value === "number" && Number.isFinite(value) && value > 0) {
    at = value > 1e12 ? value : value * 1000;
  } else if (typeof value === "string" && value.trim()) {
    const parsed = Date.parse(value.trim());
    if (Number.isFinite(parsed)) at = parsed;
  }
  if (at === null) return "";
  if (at > now + 60_000) return ""; // a clock that far ahead is not a time we can trust
  try {
    return `Checked ${new Date(at).toLocaleString(undefined, {
      day: "numeric",
      month: "short",
      hour: "numeric",
      minute: "2-digit",
    })}`;
  } catch {
    return "";
  }
}

/* ── Preset recommendations ──────────────────────────────────────────────── */

/**
 * One recommended preset change, normalized. `preset` is the PC's own id and is
 * never rewritten: the page has no list of preset names here, and inventing one
 * would be the same class of bug as inventing a model name.
 */
export function recommendationRow(entry) {
  if (!entry || typeof entry !== "object") return null;
  const preset = text(entry.preset);
  if (!preset) return null;
  const changes = (Array.isArray(entry.changes) ? entry.changes : [])
    .filter((c) => c && typeof c === "object")
    .map((c) => ({
      row: text(c.row),
      from: text(c.from),
      to: text(c.to),
      why: text(c.why),
    }))
    .filter((c) => c.row || c.to || c.from);
  return {
    preset,
    changes,
    evidence: text(entry.evidence),
  };
}

/** Every usable recommendation in the PC's answer, in the PC's own order. */
export function recommendationRows(payload) {
  const list = payload && Array.isArray(payload.recommendations) ? payload.recommendations : [];
  return list.map(recommendationRow).filter(Boolean);
}

/**
 * The words for one change: `everyday: qwen3:8b -> qwen3:14b`, built only from
 * what the PC sent. A missing side is said as "not set" rather than left blank,
 * because a blank reads like "no change".
 */
export function changeWords(change) {
  if (!change || typeof change !== "object") return "";
  const from = text(change.from) || "not set";
  const to = text(change.to) || "not set";
  const row = text(change.row) || "a preset row";
  return `${row}: ${from} -> ${to}`;
}

/**
 * Is this answer the shape the contract promises? Used to say [`UNREADABLE`]
 * rather than draw an empty panel from a body that was never an answer.
 */
export function looksLikeAnswer(payload) {
  return Boolean(
    payload &&
      typeof payload === "object" &&
      (Array.isArray(payload.candidates) || Array.isArray(payload.recommendations))
  );
}

/* ── The requests ────────────────────────────────────────────────────────── */

/**
 * The bridge arguments for one action. Only the field that action needs is sent;
 * the rest are `null`, which is what a Tauri `Option` reads as absent.
 */
export function advisorArgs(action, { ref = "", text: opinion = "" } = {}) {
  return {
    action: String(action || ""),
    reference: action === ACTION_BENCHMARK ? text(ref) : null,
    text: action === ACTION_OPINION ? text(opinion) : null,
  };
}

/**
 * Why an opinion cannot be sent, or "" when it can. The page checks this before
 * it calls, so an empty box shows a sentence instead of a round trip.
 */
export function opinionProblem(opinion) {
  const words = text(opinion);
  if (!words) return "Type what you think first — an empty note changes nothing.";
  if (words.length > OPINION_MAX_CHARS) {
    return `That note is longer than ${OPINION_MAX_CHARS} characters — shorten it and try again.`;
  }
  return "";
}

/**
 * The PC's own failure, kept word for word. Rust hands back the backend's
 * sentence or its HTTP code; this must never be replaced with "Something went
 * wrong", because the two cases the owner needs to tell apart ("this backend has
 * no advisor" and "the lookup failed") are exactly what that would erase.
 */
export function advisorFailureWords(error) {
  if (typeof error === "string" && error.trim()) return error.trim();
  if (error && typeof error.message === "string" && error.message.trim()) {
    return error.message.trim();
  }
  return "Jarvis could not ask the PC about new models, and did not say why.";
}
