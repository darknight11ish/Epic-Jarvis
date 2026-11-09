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
 *   check     -> POST /api/models/check               the public catalogue lookup
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
  "Not checked yet. Check for new models asks Jarvis to look through the public " +
  "model libraries (Hugging Face and Ollama's library) for models that fit your " +
  "graphics cards. Nothing downloads from the check.";

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
 * Why a model the owner might expect is not in the list: the public listing
 * gave no download size, so nothing could be judged. The PC sends the count in
 * `skipped_no_size`; silence there would look like the model was considered and
 * rejected, which would be a claim nobody made.
 */
export function notJudgedNote(payload) {
  const n = num(payload && payload.skipped_no_size);
  if (n === null || n <= 0) return "";
  return n === 1
    ? "1 model was left out because the public listing gave no download size for " +
        "it, so its fit was not judged."
    : `${n} models were left out because the public listing gave no download size ` +
        `for them, so their fits were not judged.`;
}

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

/**
 * Which public library a row's link goes to, in words that match the link.
 *
 * The 2026-10-28 field test found every row labelled "On Hugging Face" while
 * most linked to ollama.com. The host is the one fact that cannot drift from
 * the link, so it is read first; the PC's `provider` is used only for a row
 * with no address at all. A row may never say Hugging Face over an ollama.com
 * URL, whatever the answer claims.
 */
export function providerWords(row) {
  const url = text(row && row.sourceUrl);
  let host = "";
  try {
    host = new URL(url).hostname.toLowerCase();
  } catch {
    host = "";
  }
  if (host === "ollama.com" || host.endsWith(".ollama.com")) return "Ollama's library";
  if (host === "huggingface.co" || host.endsWith(".huggingface.co")) return "Hugging Face";
  if (host) return host;
  return text(row && row.provider) || "the public listing";
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
    provider: text(candidate.provider),
    fit: text(candidate.fit).toLowerCase(),
    fitLabel: fit.label,
    fitState: fit.state,
    why: text(candidate.why),
    sourceUrl: text(candidate.source_url),
    // The Brain's model filter fields (Q4, 2026-11-07). Each is the PC's own
    // number or word; absent when the PC did not send it, never defaulted.
    fitSingle: text(candidate.fit_single || candidate.fit).toLowerCase(),
    fitPooled: text(candidate.fit_pooled).toLowerCase(),
    vramNeedGb: num(candidate.vram_need_gb),
    pooledVramGb: num(candidate.pooled_vram_gb),
    capabilities: Array.isArray(candidate.capabilities)
      ? candidate.capabilities.filter((tag) => CAPABILITY_TAGS.includes(tag))
      : [],
    releasedAt: num(candidate.released_at),
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

/* ── The model filter bar (owner's Q4 ruling, 2026-11-07) ───────────────────
 *
 * The owner asked for a full filter set on Brain -> Models -> "Check for new
 * models": Hardware fit (fits one card / fits 2-3 cards pooled / all that fit,
 * the default / show non-fitting view-only), Size cap, Quantization, Context,
 * Licence, Capability tags, Parameter range, Source, and Sort.
 *
 * TWO RULES THIS BLOCK EXISTS TO KEEP, and each is proved in
 * `tests/model-filters.mjs` with no browser:
 *
 *   1. A NON-FITTING MODEL IS HIDDEN BY DEFAULT and is NEVER offered a working
 *      Download. A 36.7 GB model that cannot run here is not a suggestion; the
 *      owner's complaint was exactly that check offering one. "Show non-fitting"
 *      makes them VISIBLE, view-only, with the reason - `mayDownload()` is the
 *      one predicate brain.js asks before it draws a Download button.
 *   2. A FILTER NEVER INVENTS A FACT. A row whose pooled fit or release date
 *      was not reported is excluded from a filter that needs it, and sorted
 *      last - never treated as a zero or as fitting.
 *
 * Nothing here downloads, installs, benchmarks or applies anything: the block
 * is words and arithmetic over the PC's own answer.
 */

/** The owner's capability-tag vocabulary, in the order he listed it. */
export const CAPABILITY_TAGS = Object.freeze([
  "vision", "tools", "coding", "reasoning", "uncensored",
]);

/**
 * Hardware fit choices. The owner listed them in this order; the DEFAULT is
 * "all" (everything that fits this PC) - so a model that cannot run here is
 * never on screen unless he asks for it.
 */
export const FIT_MODES = Object.freeze([
  Object.freeze({ id: "one", label: "Fits 1 card (fast)" }),
  Object.freeze({ id: "pooled", label: "Fits 2-3 cards (pooled)" }),
  Object.freeze({ id: "all", label: "All that fit this PC" }),
  Object.freeze({ id: "nonfitting", label: "Show non-fitting (view-only)" }),
]);

/** Quantization choices: the owner's four, plus whatever the PC's rows carry. */
export const QUANT_SUGGESTIONS = Object.freeze([
  "Q4_K_M", "QAT", "UD-Q3_K_XL", "Q8_0",
]);

/** Minimum context windows, in tokens. 0 means "any". */
export const CONTEXT_OPTIONS = Object.freeze([
  Object.freeze({ value: 0, label: "Any context" }),
  Object.freeze({ value: 16384, label: "16K or more" }),
  Object.freeze({ value: 32768, label: "32K or more" }),
  Object.freeze({ value: 65536, label: "64K or more" }),
  Object.freeze({ value: 131072, label: "128K or more" }),
]);

/**
 * The owner's parameter ranges, as the boundaries he named. Only the named
 * bands are filters: a 40B model belongs to none of them and is never folded
 * into "70B+" to make the count look complete.
 */
export const PARAM_RANGES = Object.freeze([
  Object.freeze({ id: "1-4", label: "1B-4B", min: 1, max: 4 }),
  Object.freeze({ id: "7-14", label: "7B-14B", min: 7, max: 14 }),
  Object.freeze({ id: "24-35", label: "24B-35B", min: 24, max: 35 }),
  Object.freeze({ id: "70+", label: "70B+", min: 70, max: null }),
]);

/** Sort choices, in the order the owner listed them. */
export const SORT_MODES = Object.freeze([
  Object.freeze({ id: "fit", label: "Best fit" }),
  Object.freeze({ id: "speed", label: "Speed" }),
  Object.freeze({ id: "size", label: "Size" }),
  Object.freeze({ id: "newest", label: "Newest" }),
]);

/** The default view: everything that fits this PC, nothing filtered out. */
export const DEFAULT_FILTERS = Object.freeze({
  fit: "all",
  sizeCap: 0,
  quant: "",
  contextMin: 0,
  licence: "",
  capabilities: Object.freeze([]),
  params: "",
  source: "",
  sort: "fit",
});

/** A fresh mutable copy of the defaults (capabilities is a real array). */
export function freshFilters() {
  return {
    fit: DEFAULT_FILTERS.fit,
    sizeCap: DEFAULT_FILTERS.sizeCap,
    quant: DEFAULT_FILTERS.quant,
    contextMin: DEFAULT_FILTERS.contextMin,
    licence: DEFAULT_FILTERS.licence,
    capabilities: [],
    params: DEFAULT_FILTERS.params,
    source: DEFAULT_FILTERS.source,
    sort: DEFAULT_FILTERS.sort,
  };
}

/** Does this row fit on ONE measured card? Unknown stays unknown. */
export function fitsOneCard(row) {
  return row.fitSingle === "fits" || row.fitSingle === "tight";
}

/** Does this row fit across the cards together (and need more than one)? */
export function fitsPooled(row) {
  if (fitsOneCard(row)) return false;
  return row.fitPooled === "fits" || row.fitPooled === "tight";
}

/** Does this row fit anywhere on this PC? Unknown stays unknown. */
export function fitsThisPc(row) {
  return fitsOneCard(row) || fitsPooled(row);
}

/** "one" | "pooled" | "nonfitting" | "unknown" - the hardware-fit category. */
export function fitModeOf(row) {
  if (fitsOneCard(row)) return "one";
  if (fitsPooled(row)) return "pooled";
  if (row.fitSingle === "no" && row.fitPooled === "no") return "nonfitting";
  if (row.fitSingle === "no" && !row.fitPooled) return "nonfitting";
  return "unknown";
}

/**
 * THE ONE PREDICATE brain.js asks before drawing a Download button. False for
 * a row that does not fit this PC, and false for a row whose fit was not
 * reported at all - an unknown fit is not a licence to offer 36 GB.
 */
export function mayDownload(row) {
  return Boolean(row) && fitsThisPc(row);
}

/** The measured cards' memory in words for a pooled reason, or "". */
export function pooledWords(row) {
  if (typeof row.vramNeedGb !== "number" || typeof row.pooledVramGb !== "number") return "";
  return `It needs about ${row.vramNeedGb} GB of video memory; the measured cards hold ` +
    `${row.pooledVramGb} GB together, so it does not fit here.`;
}

/** Why a non-fitting row is shown view-only: the PC's numbers, or its words. */
export function nonFittingWhy(row) {
  const pooled = pooledWords(row);
  if (pooled) return pooled;
  if (row.why) return row.why;
  return "The PC did not report enough for a fit, so no fit is claimed here - and none is offered.";
}

/** The values this PC's rows really carry, for the three value filters. */
export function filterOptions(rows) {
  const quants = new Set();
  const licences = new Set();
  const sources = new Set();
  for (const row of rows || []) {
    const quant = String(row.quant || "").trim();
    if (quant) quants.add(quant);
    const licence = String(row.licence || "").trim();
    if (licence) licences.add(licence);
    const source = providerWords(row);
    if (source) sources.add(source);
  }
  const byText = (a, b) => a.toLowerCase().localeCompare(b.toLowerCase());
  const knownQuants = QUANT_SUGGESTIONS.filter((q) => quants.has(q));
  const otherQuants = [...quants].filter((q) => !QUANT_SUGGESTIONS.includes(q)).sort(byText);
  return {
    quants: [...knownQuants, ...otherQuants],
    licences: [...licences].sort(byText),
    sources: [...sources].sort(byText),
  };
}

/** Does the row match one selected quantisation? "QAT" matches the word anywhere. */
function quantMatches(row, wanted) {
  if (!wanted) return true;
  const hay = `${row.quant || ""} ${row.name || ""} ${row.family || ""}`.toLowerCase();
  return hay.includes(String(wanted).toLowerCase());
}

/** The named parameter band, or null for "Any". */
function paramRange(id) {
  return PARAM_RANGES.find((range) => range.id === id) || null;
}

/** Does the row pass the filters? Sort is NOT part of this. */
export function matchesFilters(row, filters) {
  const f = filters || DEFAULT_FILTERS;
  const mode = f.fit || "all";
  if (mode === "one" && fitModeOf(row) !== "one") return false;
  if (mode === "pooled" && fitModeOf(row) !== "pooled") return false;
  if (mode === "nonfitting" && fitModeOf(row) !== "nonfitting") return false;
  if (mode === "all" && fitModeOf(row) === "nonfitting") return false;
  const cap = Number(f.sizeCap) || 0;
  if (cap > 0 && !(typeof row.sizeGb === "number" && row.sizeGb <= cap)) return false;
  if (!quantMatches(row, f.quant)) return false;
  const wantContext = Number(f.contextMin) || 0;
  if (wantContext > 0 && !(typeof row.contextTokens === "number" && row.contextTokens >= wantContext)) {
    return false;
  }
  if (f.licence && row.licence !== f.licence) return false;
  const tags = Array.isArray(f.capabilities) ? f.capabilities : [];
  if (tags.length && !tags.every((tag) => row.capabilities.includes(tag))) return false;
  const range = paramRange(f.params);
  if (range) {
    const p = row.paramsB;
    if (typeof p !== "number") return false;
    if (!(p >= range.min && (range.max === null || p <= range.max))) return false;
  }
  if (f.source && providerWords(row) !== f.source) return false;
  return true;
}

/** The PC's measured speed for a row, or null. */
function measuredSpeed(row, benchmarked) {
  if (!benchmarked || typeof benchmarked !== "object") return null;
  const keys = Object.keys(benchmarked);
  const want = bareRef(row.ref);
  for (const key of keys) {
    if (bareRef(key) !== want) continue;
    const entry = benchmarked[key];
    const speed = entry && typeof entry === "object" ? entry.tokens_per_s : null;
    return typeof speed === "number" && Number.isFinite(speed) && speed > 0 ? speed : null;
  }
  return null;
}

/**
 * The rows, filtered by every filter and then ordered by the chosen sort.
 * "Best fit" keeps the PC's own fits-first order; every other sort is stable
 * and puts a row with no value for it LAST (never first, never invented).
 */
export function filterCandidates(rows, filters, benchmarked = null) {
  const list = (Array.isArray(rows) ? rows : []).filter((row) => matchesFilters(row, filters));
  const sort = (filters && filters.sort) || "fit";
  if (sort === "size") {
    return list
      .map((row, i) => ({ row, i }))
      .sort((a, b) => {
        const av = typeof a.row.sizeGb === "number" ? a.row.sizeGb : null;
        const bv = typeof b.row.sizeGb === "number" ? b.row.sizeGb : null;
        if (av === null && bv === null) return a.i - b.i;
        if (av === null) return 1;
        if (bv === null) return -1;
        return av - bv || a.i - b.i;
      })
      .map((pair) => pair.row);
  }
  if (sort === "speed") {
    return list
      .map((row, i) => ({ row, i, speed: measuredSpeed(row, benchmarked) }))
      .sort((a, b) => {
        if (a.speed === null && b.speed === null) return a.i - b.i;
        if (a.speed === null) return 1;
        if (b.speed === null) return -1;
        return b.speed - a.speed || a.i - b.i;
      })
      .map((pair) => pair.row);
  }
  if (sort === "newest") {
    return list
      .map((row, i) => ({ row, i }))
      .sort((a, b) => {
        const av = typeof a.row.releasedAt === "number" ? a.row.releasedAt : null;
        const bv = typeof b.row.releasedAt === "number" ? b.row.releasedAt : null;
        if (av === null && bv === null) return a.i - b.i;
        if (av === null) return 1;
        if (bv === null) return -1;
        return bv - av || a.i - b.i;
      })
      .map((pair) => pair.row);
  }
  return list;
}

/** How many non-default filters are on (for the summary line). */
export function activeFilterCount(filters) {
  const f = filters || DEFAULT_FILTERS;
  let n = 0;
  if ((f.fit || "all") !== "all") n += 1;
  if (Number(f.sizeCap) > 0) n += 1;
  if (f.quant) n += 1;
  if (Number(f.contextMin) > 0) n += 1;
  if (f.licence) n += 1;
  if (Array.isArray(f.capabilities) && f.capabilities.length) n += 1;
  if (f.params) n += 1;
  if (f.source) n += 1;
  if ((f.sort || "fit") !== "fit") n += 1;
  return n;
}

/**
 * The sentence under the filter bar: how many are shown, how many non-fitting
 * rows are hidden while the default view is on, and - in the view-only view -
 * that these rows cannot be offered for download.
 */
export function filterWords(filters, rows, shownRows) {
  const f = filters || DEFAULT_FILTERS;
  const total = Array.isArray(rows) ? rows.length : 0;
  const shown = Array.isArray(shownRows) ? shownRows.length : 0;
  const nonFitting = (Array.isArray(rows) ? rows : [])
    .filter((row) => fitModeOf(row) === "nonfitting").length;
  const pieces = [`Showing ${shown} of ${total} newer model${total === 1 ? "" : "s"}.`];
  if ((f.fit || "all") === "nonfitting") {
    pieces.push(
      "These do not fit on this PC, so they are view-only: no download is offered for a model that " +
        "cannot run here."
    );
  } else if (nonFitting > 0) {
    pieces.push(
      `${nonFitting} non-fitting model${nonFitting === 1 ? " is" : "s are"} hidden because ` +
        `${nonFitting === 1 ? "it does" : "they do"} not fit this PC - choose "Show non-fitting" ` +
        "to see them view-only."
    );
  }
  if (f.sort === "newest") {
    pieces.push(
      "Newest first, using the catalogue's own release date when it gives one; a row with no date is last."
    );
  }
  if (f.sort === "speed") {
    pieces.push("Speed uses only benchmarks measured on this PC; a model never measured is last.");
  }
  return pieces.join(" ");
}

/* ── The hardware-aware recommender section (Wave-9 Lane 2b, 2026-11-07) ────
 *
 * Lane 3's `jarvis_model_recommender.panel()` answers "what model should THIS
 * PC run?" with strict provenance labels (Q6: MEASURED ON THIS PC / MEASURED
 * ON DIFFERENT CARDS / ESTIMATED FIT). This block is the READING half of that
 * panel for the Brain: pure normalisation and words, no DOM, no fetch, no
 * clock. brain.js draws it through ONE render seam (advisorRecommenderSection),
 * beside the model filter bar, and nothing here downloads, applies, benchmarks
 * or changes a preset.
 *
 * THE PANEL IS OPTIONAL. A backend without `jarvis_model_recommender` omits the
 * `recommender` key from GET /api/models/recommendations (Lane 2b's backend
 * change), and `recommenderPanel()` then returns null - which brain.js draws as
 * NO section, never as an error and never as an invented table.
 *
 * Q4 STILL HOLDS HERE: a row that does not fit this PC is not drawn. Lane 3's
 * panel already leaves those out and counts them in `not_shown`, which is shown
 * as a line; this block filters `fit === "too_big"` anyway so a future shape
 * cannot smuggle one in.
 */

/** The section's own heading, shared by the page and its test. */
export const RECOMMENDER_TITLE = "What this PC should run";

/** The three provenance labels, short, in the order the owner's ruling names. */
export const PROVENANCE_LABELS = Object.freeze({
  measured_this_pc: "MEASURED ON THIS PC",
  measured_other_hardware: "MEASURED ON DIFFERENT CARDS",
  estimated_fit: "ESTIMATED FIT",
});

/** The tag state for each provenance (the page's own row-tag colours). */
export const PROVENANCE_STATES = Object.freeze({
  measured_this_pc: "ok",
  measured_other_hardware: "warn",
  estimated_fit: "",
});

const textOr = (v) => (typeof v === "string" ? v.trim() : "");

/** A catalogue date from a unix-seconds stamp, UTC and fixed width, or "". */
function isoDate(seconds) {
  const n = num(seconds);
  if (n === null || n <= 0) return "";
  try {
    return new Date(n * 1000).toISOString().slice(0, 10);
  } catch {
    return "";
  }
}

/**
 * One measured line: only the facts the PC really sent. "41.0 tok/s", "0%
 * spill" (or the real spill), the on-card percentage when reported, and the
 * run's date. Nothing is filled in for a missing number.
 */
export function recommenderMeasuredLine(row) {
  const measured = row && row.measured;
  if (!measured || typeof measured !== "object") return "";
  const bits = [];
  if (typeof measured.decode_tps === "number" && measured.decode_tps > 0) {
    bits.push(`${measured.decode_tps.toFixed(1)} tok/s`);
  }
  if (typeof measured.spill_bytes === "number") {
    bits.push(measured.spill_bytes === 0
      ? "0% spill"
      : `${Math.round(measured.spill_bytes / (1024 * 1024))} MiB spilled`);
  }
  if (typeof measured.on_card_percent === "number") {
    bits.push(`${measured.on_card_percent}% on card`);
  }
  const when = isoDate(measured.at);
  if (when) bits.push(when);
  return bits.join(" · ");
}

/** One row of the panel, as words brain.js can draw and a node test can read. */
export function recommenderRowView(row) {
  if (!row || typeof row !== "object") return null;
  const provenance = textOr(row.provenance);
  const label = PROVENANCE_LABELS[provenance] || textOr(row.provenance_label);
  if (!textOr(row.model) && !textOr(row.label)) return null;
  const meta = [];
  if (textOr(row.params)) meta.push(`${textOr(row.params)} parameters`);
  if (textOr(row.quant)) meta.push(`${textOr(row.quant)} quantization`);
  if (Array.isArray(row.capabilities) && row.capabilities.length) {
    meta.push(`capabilities: ${row.capabilities.join(", ")}`);
  }
  if (typeof row.vram_needed_gib === "number") {
    const ctx = typeof row.context_gib === "number"
      ? ` at ${row.context_gib.toLocaleString("en-US")} tokens` : "";
    meta.push(`needs about ${row.vram_needed_gib} GiB${ctx}`);
  }
  if (textOr(row.why)) meta.push(textOr(row.why));
  const measuredNote = textOr(row.measured_note);
  if (measuredNote) {
    // WAVE 11: a catalogue measurement and the fit estimate above it are two
    // different claims (MiniCPM-V "fits on one card" beside its "across three
    // cards" run), so the measurement is labelled as one - once, in one place.
    meta.push(measuredNote.startsWith("Separately measured on 2026-11-07:")
      ? measuredNote
      : `Separately measured on 2026-11-07: ${measuredNote}`);
  }
  return {
    model: textOr(row.model),
    label: textOr(row.label) || textOr(row.model) || "(unnamed)",
    fit: textOr(row.fit),
    provenance,
    provenanceLabel: label,
    provenanceState: PROVENANCE_STATES[provenance] || "",
    measuredLine: recommenderMeasuredLine(row),
    warning: textOr(row.downgrade_warning),
    why: textOr(row.why),
    meta,
  };
}

/**
 * The panel, normalised: the hardware sentence, the tier, the fitting rows,
 * the not-shown count and the module's own notes. null when the answer carries
 * no `recommender` at all (an older PC) - the caller then draws no section.
 */
export function recommenderPanel(payload) {
  const rec = payload && typeof payload === "object" ? payload.recommender : null;
  if (!rec || typeof rec !== "object") return null;
  const hardware = rec.hardware && typeof rec.hardware === "object" ? rec.hardware : {};
  const tier = rec.tier && typeof rec.tier === "object" ? rec.tier : {};
  const rows = (Array.isArray(rec.rows) ? rec.rows : [])
    .filter((row) => row && textOr(row.fit) !== "too_big")
    .map(recommenderRowView)
    .filter(Boolean);
  const notes = (Array.isArray(rec.notes) ? rec.notes : [])
    .map(textOr).filter(Boolean);
  const words = textOr(rec.words);
  const tierLabel = textOr(tier.label);
  const tierWords = textOr(tier.words);
  // WAVE 11: the PC's hardware sentence already ends "It is the <tier label>
  // tier: <tier words>." (jarvis_model_recommender.hardware_words), so the
  // tier must not be printed by anyone a second time. If an older panel's
  // sentence does not carry it, append it here - still exactly once.
  let hardwareWords = textOr(hardware.words);
  if (tierLabel && !hardwareWords.includes(tierLabel)) {
    const tierSentence = `${tierLabel}${tierWords ? `: ${tierWords}` : ""}`;
    hardwareWords = hardwareWords
      ? `${hardwareWords} It is the ${tierSentence}.`
      : `It is the ${tierSentence}.`;
  }
  if (!rows.length && !notes.length && !words && !hardwareWords && !tierLabel) {
    return null;
  }
  return {
    title: RECOMMENDER_TITLE,
    words,
    hardwareWords,
    tierLabel,
    tierWords,
    rows,
    notShown: Number.isInteger(rec.not_shown) && rec.not_shown > 0 ? rec.not_shown : 0,
    notes,
    generatedAt: num(rec.generated_at),
  };
}

/** "As of 2026-10-28", or "" when the panel carries no moment. */
export function recommenderWhen(panel) {
  const day = isoDate(panel && panel.generatedAt);
  return day ? `As of ${day}.` : "";
}

/** The not-shown line: Q4's rule said out loud, or "". */
export function recommenderNotShownLine(panel) {
  const n = panel && panel.notShown;
  if (!n) return "";
  return (
    `${n} more model${n === 1 ? "" : "s"} need more video memory than this PC has, ` +
    "so they are not offered here. The filter above can show them as not-fitting " +
    "and view-only."
  );
}

/**
 * The whole section as one readable string. brain.js draws the same facts as
 * rows; this is the node fixture's view (and the shape a future `feature_guide`
 * answer could reuse), so every label and warning is asserted without a browser.
 */
export function recommenderText(panel) {
  if (!panel) return "";
  const lines = [panel.title];
  // ONE hardware sentence, one tier: hardwareWords already carries the tier
  // when the panel has it (Wave 11 duplicate-paragraph fix).
  if (panel.hardwareWords) lines.push(panel.hardwareWords);
  else if (panel.tierLabel) {
    lines.push(`${panel.tierLabel}${panel.tierWords ? `: ${panel.tierWords}` : ""}`);
  }
  for (const row of panel.rows) {
    const bits = [row.provenanceLabel, row.label];
    if (row.measuredLine) bits.push(row.measuredLine);
    lines.push(bits.join(" - "));
    for (const meta of row.meta) lines.push(meta);
    if (row.warning) lines.push(`Warning: ${row.warning}`);
  }
  const notShown = recommenderNotShownLine(panel);
  if (notShown) lines.push(notShown);
  for (const note of panel.notes) lines.push(note);
  const when = recommenderWhen(panel);
  if (when) lines.push(when);
  return lines.join("\n");
}
