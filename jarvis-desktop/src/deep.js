/**
 * Deep questions, in the Brain window - backend/big-model.patch and
 * backend/jarvis_big_model.py (JARVIS-API.md section 14).
 *
 * The owner asks one question they want a careful answer to. The big model
 * (colibri, on this PC's processor and SSD) answers it in the background,
 * with no tools, no internet and no memory of other conversations, and the
 * answer is kept on the PC. It is slow: minutes, not seconds.
 *
 * "Ask slowly" only queues it. There is no approval card per question - the
 * owner approved the "Deep questions" switch in Settings with one - and the
 * button is greyed while the event stream is stale (rule 4), as Rust's
 * `ask_deep` refuses then too. A job's `state`:
 *
 *   queued    waiting its turn
 *   loading   colibri is starting (can take minutes)
 *   thinking  the model is writing the answer
 *   done      answered: the answer, the time it took and the speed
 *   failed    not answered, and why
 *
 * When one finishes the event stream rings `deep` (`{id, state}` only - a
 * doorbell, never the question or the answer) and brain.js reads the list
 * again. Only while a job is still going does it also poll, gently.
 *
 * ## The answer is rendered, never injected
 *
 * The answer is model text. It goes through the one Markdown renderer the
 * quickbar uses (markdown.js), which HTML-escapes everything before it adds
 * any markup of its own - so nothing the model writes can become an element.
 * That escaped result is the only `innerHTML` here. Its links are then turned
 * back into plain text: the Brain cannot open a link in the real browser, and
 * following one inside this window would navigate it away. Every other string
 * (the question, each `why`) goes in as text.
 *
 * @module deep
 */

import { renderMarkdown } from "./markdown.js";

/** Asking again while one is going: at most this often. */
export const POLL_MS = 15000;

/** The backend's own limit, used until `limits.question_chars` says. */
export const QUESTION_CHARS = 4000;

/** A question's line while the private lists are hidden. */
export const QUESTION_HIDDEN = "Question hidden";

/** A job state, in words and a tag colour (brain.css `.row-tag`). */
export const STATES = {
  queued: { tag: "queued", tone: "present" },
  loading: { tag: "loading", tone: "warn" },
  thinking: { tag: "thinking", tone: "warn" },
  done: { tag: "done", tone: "ok" },
  failed: { tag: "failed", tone: "bad" },
};

/** The states that are still going. */
export const RUNNING = new Set(["queued", "loading", "thinking"]);

const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
const text = (v) => (typeof v === "string" ? v : "");

/**
 * `GET /api/deep`'s answer, read. `update` is true for an older backend
 * (Rust answers `{available: false, why}` with no `jobs` then).
 */
export function readDeep(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  const limits = a.limits && typeof a.limits === "object" ? a.limits : {};
  const jobs = Array.isArray(a.jobs) ? a.jobs : [];
  return {
    available: a.available === true,
    // "Hide memory lists and chat history" is on: Rust took the questions
    // and answers out (commands.rs redact_deep); the rows keep their state.
    hidden: a.hidden === true,
    why: text(a.why).trim(),
    enabled: a.enabled === true,
    update: !Array.isArray(a.jobs),
    questionChars: num(limits.question_chars) && limits.question_chars > 0
      ? limits.question_chars : QUESTION_CHARS,
    queue: num(limits.queue) && limits.queue > 0 ? limits.queue : 3,
    jobs: jobs.filter((j) => j && typeof j.id === "string").map((j) => ({
      id: j.id,
      question: text(j.question),
      state: text(j.state),
      why: text(j.why).trim(),
      seconds: num(j.seconds),
      wordsPerS: num(j.words_per_s),
      tokensPerS: num(j.tokens_per_s),
      queued: num(j.queued),
      answer: j.state === "done" ? text(j.answer) : "",
      hidden: j.hidden === true,
    })),
  };
}

/** How many of the listed jobs are still going. */
export function runningCount(view) {
  return view.jobs.filter((j) => RUNNING.has(j.state)).length;
}

/** "8 s", "12 min 5 s", "1 h 3 min". */
export function duration(seconds) {
  const s = Math.round(Number(seconds));
  if (!Number.isFinite(s) || s < 0) return "";
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min ${s % 60} s`;
  return `${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min`;
}

/** Time taken and words a second, for a job that is done. */
export function speedLine(job) {
  if (job.state !== "done") return "";
  const parts = [];
  if (job.seconds !== null) parts.push(`Took ${duration(job.seconds)}`);
  if (job.wordsPerS !== null) parts.push(`${job.wordsPerS} words a second`);
  return parts.length ? `${parts.join(", ")}.` : "";
}

/** The line above the box: whether a question can be asked, and why not. */
export function leadLine(view) {
  if (view.available) return view.why || "Ready.";
  if (view.update) return view.why;
  const why = view.why || "Deep questions cannot be asked right now.";
  return view.enabled ? why
    : `${why} To use it, open Settings, go to "Big model (slow)", and turn on "Use the big ` +
      `model" and then "Deep questions". Each asks you first, on an approval card.`;
}

/**
 * "Ask slowly": one question, one request. Resolves to `{ text, tone, queued }`
 * in the backend's own words - its `message` when queued, its `error` when
 * refused - or Rust's sentence when the request did not get that far.
 */
export async function askDeep(invoke, question) {
  const q = String(question || "").trim();
  if (!q) return { text: "Type a question first.", tone: "bad", queued: false };
  let out;
  try {
    out = await invoke("ask_deep", { question: q });
  } catch (error) {
    return { text: String((error && error.message) || error), tone: "bad", queued: false };
  }
  if (out && out.state === "queued" && out.ok === true) {
    return { text: text(out.message) || "Queued. The answer appears in the list when it is done.",
      tone: "ok", queued: true };
  }
  return { text: text(out && out.error) || "Jarvis did not take the question. Nothing was asked.",
    tone: "bad", queued: false };
}

/**
 * Renders the model's answer into `node`: the shared Markdown renderer's
 * escaped HTML, then every link made plain text (see the module note).
 */
export function renderAnswer(node, markdown) {
  node.innerHTML = renderMarkdown(String(markdown || ""));
  for (const a of node.querySelectorAll("a")) {
    const href = a.getAttribute("href") || "";
    const label = a.textContent || "";
    a.replaceWith(document.createTextNode(label === href || !href ? label : `${label} (${href})`));
  }
}

/**
 * Paints the list of recent questions into `container`.
 *
 * `plate` is `{ view, error, openId }`: the last read (from `readDeep`), why
 * the last read failed, and the job whose answer is open. `ui` is the Brain's
 * own `el` and `row` helpers.
 */
export function renderJobs(container, plate, { el, row, hiddenNode }) {
  container.replaceChildren();
  const v = plate.view;
  if (!v) {
    container.append(el("p", "empty", plate.error
      ? `Could not read the deep questions: ${plate.error}` : "Reading…"));
    return;
  }
  if (plate.error) container.append(el("p", "empty failed", `Could not read them again: ${plate.error}`));
  if (!v.jobs.length) {
    if (!v.update) container.append(el("p", "empty", "No deep questions yet."));
    return;
  }
  // Hidden with the memory lists: each row keeps its state and time, and a
  // Show button (the Brain's own, Windows Hello first) brings the words back.
  if (v.hidden && hiddenNode) container.append(hiddenNode(0, "words"));
  const list = el("div", "rows deep-jobs");
  const newestDone = v.jobs.find((j) => j.state === "done");
  for (const job of v.jobs) {
    const st = STATES[job.state] || { tag: job.state || "?", tone: "" };
    const item = row({ tag: st.tag, state: st.tone,
      title: job.hidden || v.hidden ? QUESTION_HIDDEN : job.question,
      meta: [job.why, speedLine(job)], actions: [] });
    item.dataset.id = job.id;
    item.dataset.state = job.state;
    if (job.state === "done" && job.answer) {
      const details = el("details", "deep-answer");
      const openId = plate.openId === undefined ? (newestDone && newestDone.id) : plate.openId;
      details.open = job.id === openId;
      details.append(el("summary", "", "The answer"));
      const body = el("div", "deep-answer-body");
      renderAnswer(body, job.answer);
      details.append(body);
      details.addEventListener("toggle", () => {
        if (plate.onToggle) plate.onToggle(job.id, details.open);
      });
      const main = item.querySelector(".row-main") || item;
      main.append(details);
    }
    list.append(item);
  }
  container.append(list);
}
