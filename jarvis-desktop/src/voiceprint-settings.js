/**
 * Settings -> How Jarvis talks -> "Write like me" (NEW FILE; not mounted yet).
 *
 * The wiring (settings.html, settings.js, src-tauri/src/lib.rs) is deliberately
 * NOT touched until the Lead clears it; the exact hunks are in the PR body.
 *
 * The three Rust commands (src-tauri/src/voiceprint.rs): voiceprint_status,
 * voiceprint_add, voiceprint_forget, plus voiceprint_set_enabled. One tap is
 * one change. No card is raised anywhere - the switch and samples are local
 * settings, and the PC answers them on its loopback-only route.
 *
 * Safety rules this module keeps (tests/voiceprint-ui.mjs checks them):
 * - every invoke is bounded to 30 s and reports plain words on a timeout;
 * - every piece of text from the PC goes in with textContent, never innerHTML;
 * - Forget asks "are you sure?" first and sends `confirm: true` only after yes;
 * - nothing is auto-applied: a change happens only when the owner presses it.
 *
 * @module voiceprint-settings
 */

export const TITLE = "Write like me";
export const DETAIL =
  "Teach Jarvis how you write - sentence length, contractions, words you never use, " +
  "and examples of your own messages - so drafts sound like you, not a chatbot.";
export const SAMPLE_HINT =
  "Paste a message or email you wrote. Names, dates, amounts, links and numbers are " +
  "removed before it is kept.";
export const SWITCH_LABEL = "Write like me when drafting";
export const SWITCH_DETAIL =
  "Off by default. Adds a short style block to local drafts only; never to Temporary " +
  "chat or to an external chatbot.";
export const FORGET_LABEL = "Forget this sample";
export const EMPTY = "No samples yet. Paste one above to begin.";
export const BLOCKED =
  "Jarvis Desktop could not reach the PC's style engine. Nothing was changed.";
export const MAX_TEXT = 4000;
export const TIMEOUT_MS = 30_000;

/** One short line from the PC; never its raw error or JSON. */
export function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|undefined|null/i.test(said) || said.length > 300) return BLOCKED;
  return said;
}

/** `GET /api/voiceprint` in the shape this page renders. Never throws. */
export function parseStatus(body) {
  const b = body && typeof body === "object" ? body : {};
  const rows = Array.isArray(b.samples) ? b.samples : [];
  return {
    available: b.available !== false,
    enabled: b.enabled === true,
    samples: rows
      .filter((r) => r && typeof r === "object" && typeof r.id === "string")
      .map((r) => ({
        id: r.id,
        text: String(r.text || ""),
        kind: String(r.kind || "sample"),
        prompt: String(r.prompt || ""),
      })),
    count: Number.isFinite(b.count) ? b.count : rows.length,
    scrubber: b.scrubber !== false,
    message: typeof b.message === "string" ? b.message : Object.keys(rows).length ? "" : EMPTY,
  };
}

/** The one-line Forget question, in the owner's words (tests pin it). */
export function forgetAsk(sample) {
  const words = String((sample && sample.text) || "").trim().slice(0, 60);
  return `Forget this sample?${words ? `\n\n"${words}"` : ""}\n\nIt asks first because it cannot be undone.`;
}

/** A 30 s bound around any invoke; the timeout is plain words, not a stack. */
export function boundedInvoke(invoke, command, args, ms = TIMEOUT_MS) {
  if (typeof invoke !== "function") return Promise.reject(new Error(BLOCKED));
  let timer = null;
  const timeout = new Promise((_resolve, reject) => {
    timer = setTimeout(() => reject(new Error(
      "The PC did not answer within 30 seconds, so nothing was saved. Try again."
    )), ms);
  });
  return Promise.race([Promise.resolve().then(() => invoke(command, args)), timeout])
    .finally(() => { if (timer) clearTimeout(timer); });
}

export function sampleProblem(text) {
  const t = String(text || "").trim();
  if (!t) return "Write or paste something first.";
  if (t.length > MAX_TEXT) return `That is too long - at most ${MAX_TEXT} characters.`;
  return "";
}

function node(doc, tag, className, text) {
  const n = doc.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

/**
 * Build the section into `root`. `invoke` is the Tauri bridge, `confirm` the
 * browser's question function; both are injected so this is testable and so
 * the wiring file only has to call this once with the real ones.
 */
export function mount(root, { invoke, confirm, document: doc = globalThis.document } = {}) {
  if (!root || !doc) return null;
  root.textContent = "";
  const status = node(doc, "p", "vp-status", "Reading your style...");
  const toggle = node(doc, "input");
  toggle.type = "checkbox";
  toggle.id = "vp-enabled";
  const switchLine = node(doc, "label", "toggle");
  switchLine.append(node(doc, "span", "", SWITCH_LABEL), toggle);
  const detail = node(doc, "p", "quiet", SWITCH_DETAIL);
  const area = node(doc, "textarea");
  area.rows = 4;
  area.maxLength = MAX_TEXT;
  area.placeholder = SAMPLE_HINT;
  const add = node(doc, "button", "btn", "Keep this sample");
  const hint = node(doc, "p", "quiet", SAMPLE_HINT);
  const list = node(doc, "div", "vp-list");
  const said = node(doc, "p", "vp-said", "");

  let samples = [];
  const refresh = async () => {
    try {
      const body = await boundedInvoke(invoke, "voiceprint_status");
      const view = parseStatus(body);
      samples = view.samples;
      toggle.checked = view.enabled;
      list.textContent = "";
      if (!samples.length) list.append(node(doc, "p", "quiet", EMPTY));
      for (const s of samples) {
        const row = node(doc, "div", "vp-row");
        row.append(node(doc, "p", "", s.text));
        const forget = node(doc, "button", "btn small", FORGET_LABEL);
        forget.addEventListener("click", async () => {
          if (typeof confirm === "function" && !confirm(forgetAsk(s))) return;
          try {
            await boundedInvoke(invoke, "voiceprint_forget", { id: s.id, confirm: true });
            said.textContent = "That sample is gone.";
            await refresh();
          } catch (e) { said.textContent = problemWords(e); }
        });
        row.append(forget);
        list.append(row);
      }
      status.textContent = view.message || `${view.count} sample(s) kept on this PC.`;
    } catch (e) { status.textContent = problemWords(e); }
  };

  toggle.addEventListener("change", async () => {
    const want = toggle.checked;
    try {
      await boundedInvoke(invoke, "voiceprint_set_enabled", { enabled: want });
      said.textContent = want ? "Write like me is on." : "Write like me is off.";
    } catch (e) {
      toggle.checked = !want;
      said.textContent = problemWords(e);
    }
  });
  add.addEventListener("click", async () => {
    const problem = sampleProblem(area.value);
    if (problem) { said.textContent = problem; return; }
    try {
      await boundedInvoke(invoke, "voiceprint_add", { text: area.value });
      area.value = "";
      said.textContent = "Kept on this PC, with names and numbers removed.";
      await refresh();
    } catch (e) { said.textContent = problemWords(e); }
  });

  root.append(node(doc, "h3", "", TITLE), node(doc, "p", "quiet", DETAIL),
              switchLine, detail, area, add, hint, status, said, list);
  refresh();
  return { refresh, samples: () => samples };
}
