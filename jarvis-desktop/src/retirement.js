/**
 * The retirement what-if on the Brain's Work tab (the owner's decision of
 * 2026-09-30, queue item 5; docs/FINANCE-DESIGN.md part B and its "Retirement
 * contract (frozen)"; JARVIS-API.md section 103; backend jarvis_retirement.py;
 * src-tauri/src/brain/retirement.rs).
 *
 * The owner types a few numbers about their own money; the PC plays out
 * 10,000 made-up futures and answers with ranges. This module holds the
 * reading of what the PC sends, the few words the app owns, and the card.
 * The labels, limits, help lines, made-up default figures, the disclaimer and
 * every sentence of the answer come from the PC and are shown exactly as sent:
 * this file never rounds, rewords or invents a figure.
 *
 * PRIVATE, SCREEN ONLY. The numbers the owner types are never written
 * anywhere: not localStorage or sessionStorage, not a draft, not a log, not a
 * widget, not chat history. They live in the boxes on screen and go when the
 * owner leaves the tab, the window is hidden (App lock hides it), the private
 * lists are hidden, or the card is asked to `clear`. The result is never
 * read aloud, has no copy or export button, and is never handed to a search,
 * a chatbot or Goals. Every string from the PC goes in with textContent.
 *
 * @module retirement
 */

/** The words the app owns (contract R5), and the two fixed by the contract. */
export const TITLE_FALLBACK = "Retirement what-if";
export const RUN_LABEL = "Work it out";
export const WORKING = "Working it out";
export const ASSUMED = "assumed";
export const USED_HEADING = "What I used";
/** Contract R4: shown alone while the private lists are hidden or App lock is on. */
export const HIDDEN_WORDS = "Retirement what-if hidden";
/** Only if a result somehow arrives without it: the disclaimer is shown every time. */
export const DISCLAIMER = "This is a simplified what-if, not financial advice.";
/** The desktop's own line for a PC that has no what-if yet (Rust says the same). */
export const MISSING =
  "Your PC's Jarvis cannot work out a retirement what-if yet - run apply-patches.ps1 on the PC.";
export const NO_FORM = "Could not read the what-if's form from your PC.";
export const NO_RESULT = "Jarvis answered, but not in a way this app can read.";
/** The link is stale: nothing new can be worked out (rule 4). */
export const STALE_LINE =
  "Waiting for the link to catch up. Nothing can be sent until it does.";

/** The eleven fields, in the order the form draws them (contract R2). */
export const FIELD_KEYS = Object.freeze([
  "current_age", "retirement_age", "plan_to_age", "savings", "yearly_saving",
  "yearly_spending", "other_income", "other_income_start_age",
  "expected_return_percent", "volatility_percent", "inflation_percent",
]);

/** The four states (contract R3). */
export const STATES = Object.freeze([
  "mixed", "never_runs_out", "always_runs_out", "not_enough_to_say",
]);

/** The longest text a box takes (Rust refuses longer). */
export const TEXT_MAX = 40;
/** How long to wait before trying again once when the PC is busy. */
export const RETRY_MS = 1000;

const isObj = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const str = (v) => (typeof v === "string" ? v : "");
const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** A limit as the form shows it: 1000000000 -> "1,000,000,000", -5 -> "-5". */
export function fmtLimit(n) {
  const v = num(n);
  if (v === null) return "";
  return v.toLocaleString("en-US", { maximumFractionDigits: 6 });
}

/** "years · 18 to 100" - the unit and the limits, from the PC's own values. */
export function limitLine(field) {
  const lo = fmtLimit(field.min);
  const hi = fmtLimit(field.max);
  const range = lo !== "" && hi !== "" ? `${lo} to ${hi}` : "";
  return [field.unit, range].filter(Boolean).join(" · ");
}

/** A default as text for a box: 7 -> "7", 2.5 -> "2.5", 95 -> "95". */
export function defaultText(value) {
  const v = num(value);
  return v === null ? "" : String(v);
}

/**
 * The box's starting text: only a made-up figure (a placeholder) starts filled;
 * the required boxes and the optional ones start empty.
 */
export function startText(field) {
  return field.placeholder ? defaultText(field.default) : "";
}

/** The hint inside an empty box: the PC's default, if it has one. */
export function hintText(field) {
  return field.placeholder ? "" : defaultText(field.default);
}

/** Reads one field of the form; null if it is not one of the contract's. */
export function readField(raw) {
  if (!isObj(raw) || !FIELD_KEYS.includes(raw.key)) return null;
  const label = str(raw.label).trim();
  if (!label) return null;
  return {
    key: raw.key,
    label,
    unit: str(raw.unit),
    kind: ["age", "money", "percent"].includes(raw.kind) ? raw.kind : "money",
    min: num(raw.min),
    max: num(raw.max),
    default: num(raw.default),
    required: raw.required === true,
    placeholder: raw.placeholder === true,
    help: str(raw.help),
  };
}

/**
 * The form from `GET /api/retirement/defaults`. A hidden answer comes back as
 * `{hidden: true, words}`; a bad shape as null.
 */
export function readForm(answer) {
  if (!isObj(answer)) return null;
  if (answer.hidden === true) {
    return { hidden: true, words: str(isObj(answer.words) ? answer.words.hidden : "") || HIDDEN_WORDS };
  }
  if (answer.ok !== true || !Array.isArray(answer.fields)) return null;
  const fields = answer.fields.map(readField).filter(Boolean);
  if (!fields.length) return null;
  const words = isObj(answer.words) ? answer.words : {};
  return {
    hidden: false,
    title: str(answer.title).trim() || TITLE_FALLBACK,
    detail: str(answer.detail),
    fields,
    disclaimer: str(answer.disclaimer) || DISCLAIMER,
    placeholderNote: str(answer.placeholder_note),
    todaysMoney: str(answer.todays_money),
    words: {
      hidden: str(words.hidden) || HIDDEN_WORDS,
      busy: str(words.busy),
      tooSlow: str(words.too_slow),
    },
  };
}

/**
 * What the boxes hold, as the body of a run: every box's text, trimmed, and
 * an empty box left out (the PC takes the default, or says which required
 * box is missing). Only the form's own keys go; nothing is checked here - the
 * PC's own words for a bad entry are what the owner reads.
 */
export function collectValues(fields, texts) {
  const out = {};
  for (const f of fields) {
    const t = str(texts && texts[f.key]).trim().slice(0, TEXT_MAX + 1);
    if (t) out[f.key] = t;
  }
  return out;
}

/**
 * Where an answer that is not a result belongs: beside a field of the form, or
 * in the line under the button. `retry` is true only for the PC's "busy".
 */
export function placement(answer, fields) {
  const a = isObj(answer) ? answer : {};
  const message = str(a.message).trim();
  const key = str(a.field);
  if (fields.some((f) => f.key === key)) {
    return { kind: "field", key, message: message || NO_RESULT, retry: false };
  }
  return { kind: "line", key: "", message: message || NO_RESULT, retry: a.error === "busy" };
}

const clamp100 = (n) => Math.min(100, Math.max(0, n));

function readShare(s) {
  if (!isObj(s)) return null;
  const per = num(s.per_100);
  const label = str(s.label);
  if (per === null || !label) return null;
  return { per_100: clamp100(per), label, all: s.all === true, none: s.none === true };
}

/**
 * The result of a run (contract R3) reduced to what is drawn, or null if it
 * is not a result. Nothing is added: a sentence, a label or a figure is
 * carried as the PC sent it.
 */
export function readResult(raw) {
  if (!isObj(raw) || raw.kind !== "retirement" || !STATES.includes(raw.state)) return null;
  const summary = Array.isArray(raw.summary)
    ? raw.summary.filter((s) => typeof s === "string" && s.trim()) : [];
  if (!summary.length) return null;
  const bands = isObj(raw.bands)
    ? { lower: readShare(raw.bands.lower), higher: readShare(raw.bands.higher) } : null;
  const used = (Array.isArray(raw.used) ? raw.used : [])
    .filter((u) => isObj(u) && str(u.label) && typeof u.value === "string")
    .map((u) => ({ key: str(u.key), label: u.label, value: u.value, assumed: u.assumed === true }));
  const words = isObj(raw.words) ? raw.words : {};
  return {
    state: raw.state,
    title: str(raw.title).trim() || TITLE_FALLBACK,
    summary,
    share: readShare(raw.share),
    bands: bands && bands.lower && bands.higher ? bands : null,
    used,
    disclaimer: str(raw.disclaimer) || DISCLAIMER,
    todaysMoney: str(raw.todays_money),
    placeholderNote: str(raw.placeholder_note),
    hidden: str(words.hidden) || HIDDEN_WORDS,
  };
}

/**
 * The share meter's geometry, from `share.per_100` and `bands.*.per_100` only.
 * Percent positions on a 0-100 track; null when there is nothing to draw
 * (the "not enough to say" state).
 */
export function meterGeometry(result) {
  if (!result || !result.share) return null;
  const at = result.share.per_100;
  const lo = result.bands ? result.bands.lower.per_100 : at;
  const hi = result.bands ? result.bands.higher.per_100 : at;
  const from = Math.min(lo, hi, at);
  const to = Math.max(lo, hi, at);
  return { from, to, at };
}

/** The meter's plain-words labels, lower / middle / higher, as the PC wrote them. */
export function meterLabels(result) {
  if (!result || !result.share) return [];
  return [result.bands && result.bands.lower.label, result.share.label,
    result.bands && result.bands.higher.label].filter(Boolean);
}

/* ── The card ─────────────────────────────────────────────────────────── */

const SVG_NS = "http://www.w3.org/2000/svg";

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function svgEl(tag, attrs) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  return node;
}

/** The hand-drawn share meter: a track, the band between the two shifted
 *  answers, and a tick at the share itself. Decoration only - the sentences
 *  carry the meaning, so it is hidden from a screen reader. */
export function drawMeter(result) {
  const g = meterGeometry(result);
  if (!g) return null;
  const box = el("div", "ret-meter");
  box.setAttribute("aria-hidden", "true");
  const svg = svgEl("svg", { viewBox: "0 0 100 8", class: "ret-meter-svg", preserveAspectRatio: "none" });
  svg.append(svgEl("rect", { class: "ret-meter-track", x: 0, y: 2, width: 100, height: 4, rx: 2 }));
  svg.append(svgEl("rect", {
    class: "ret-meter-band", x: g.from, y: 1, width: Math.max(g.to - g.from, 0.8), height: 6, rx: 1,
  }));
  svg.append(svgEl("rect", {
    class: "ret-meter-tick", x: Math.min(Math.max(g.at - 0.4, 0), 99.2), y: 0, width: 0.8, height: 8,
  }));
  box.append(svg);
  box.append(el("p", "ret-meter-labels", meterLabels(result).join(" · ")));
  return box;
}

/**
 * The card. `root` is the empty element inside the card; `deps` are the
 * window's own plumbing, passed in so this file stays free of brain.js:
 *
 *   invoke(cmd, args)      the Tauri call (null when there is no desktop app)
 *   isTauri                whether invoke can reach the PC
 *   canAct()               false while the link is stale (rule 4)
 *   live.add(b), live.sync(b)  the window's grey-out-while-stale for a button
 *   announce(text, mode)   the window's screen-reader line
 *   listen(name, fn)       Tauri event listen (may be null)
 *   titleEl                the card's <h2>
 *   view()                 which tab is showing ("work" is the card's)
 */
export function createRetirementCard(deps) {
  const { root, titleEl } = deps;
  const S = {
    form: null,         // readForm(...) once the form is drawn
    hidden: false,
    loading: false,
    running: false,
    gen: 0,             // bumped by every clear, so a late answer is dropped
    inputs: new Map(),  // key -> <input>
    errors: new Map(),  // key -> <p>
    result: null,
    line: "",
    note: "",
    focus: "",          // what should get the keyboard after the next paint
  };
  let staleNode = null;
  let runBtn = null;
  let lineNode = null;
  let resultBox = null;

  function say(text, mode) {
    if (deps.announce && text) deps.announce(text, mode || "polite");
  }

  /** Forgets every number: the boxes, the result and any message. */
  function clear() {
    S.gen += 1;
    S.form = null;
    S.hidden = false;
    S.loading = false;
    S.running = false;
    S.inputs.clear();
    S.errors.clear();
    S.result = null;
    S.line = "";
    S.note = "";
    S.focus = "";
    staleNode = runBtn = lineNode = resultBox = null;
    root.replaceChildren();
    if (titleEl) titleEl.textContent = TITLE_FALLBACK;
  }

  function texts() {
    const t = {};
    for (const [k, input] of S.inputs) t[k] = input.value;
    return t;
  }

  function paintHidden(words) {
    root.replaceChildren(el("p", "ret-hidden", words));
    S.hidden = true;
  }

  function paintNote(text) {
    root.replaceChildren(el("p", "note", text));
  }

  function fieldBlock(f, describedBy) {
    const wrap = el("div", "ret-field");
    wrap.dataset.key = f.key;
    const id = `ret-${f.key}`;
    const label = el("label", "ret-label", f.label);
    label.htmlFor = id;
    if (f.placeholder) label.append(" ", el("span", "ret-assumed", ASSUMED));
    wrap.append(label);
    const input = el("input", "field ret-input");
    input.id = id;
    input.type = "text";
    input.inputMode = f.kind === "age" ? "numeric" : "decimal";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.maxLength = TEXT_MAX;
    input.setAttribute("autocapitalize", "off");
    input.setAttribute("data-lpignore", "true");
    input.setAttribute("data-1p-ignore", "true");
    const hint = hintText(f);
    if (hint) input.placeholder = hint;
    input.value = startText(f);
    const ids = [`${id}-limit`];
    const limit = el("p", "ret-limit", limitLine(f));
    limit.id = ids[0];
    if (f.help) {
      const help = el("p", "ret-help", f.help);
      help.id = `${id}-help`;
      ids.push(help.id);
      wrap.append(input, limit, help);
    } else {
      wrap.append(input, limit);
    }
    const err = el("p", "ret-error", "");
    err.id = `${id}-error`;
    err.hidden = true;
    wrap.append(err);
    if (f.placeholder && describedBy) ids.push(describedBy);
    input.setAttribute("aria-describedby", ids.join(" "));
    input.addEventListener("input", () => {
      if (!err.hidden) {
        err.hidden = true;
        err.textContent = "";
        input.removeAttribute("aria-invalid");
      }
    });
    S.inputs.set(f.key, input);
    S.errors.set(f.key, err);
    return wrap;
  }

  function paintForm() {
    const form = S.form;
    S.inputs.clear();
    S.errors.clear();
    if (titleEl) titleEl.textContent = form.title;
    const frag = document.createDocumentFragment();
    if (form.detail) frag.append(el("p", "note ret-detail", form.detail));
    if (form.todaysMoney) frag.append(el("p", "note", form.todaysMoney));
    const formNode = el("form", "ret-form");
    formNode.autocomplete = "off";
    formNode.noValidate = true;
    formNode.setAttribute("aria-label", form.title);
    const grid = el("div", "ret-grid");
    const noteId = "ret-placeholder-note";
    for (const f of form.fields) grid.append(fieldBlock(f, form.placeholderNote ? noteId : ""));
    formNode.append(grid);
    if (form.placeholderNote) {
      const p = el("p", "note ret-placeholder-note", form.placeholderNote);
      p.id = noteId;
      formNode.append(p);
    }
    const actions = el("div", "goal-actions ret-actions");
    runBtn = el("button", "btn small", RUN_LABEL);
    runBtn.type = "submit";
    runBtn.dataset.title = "";
    if (deps.live) deps.live.add(runBtn);
    actions.append(runBtn);
    formNode.append(actions);
    lineNode = el("p", "ret-line");
    lineNode.setAttribute("role", "status");
    lineNode.hidden = true;
    formNode.append(lineNode);
    staleNode = el("p", "note ret-stale", STALE_LINE);
    staleNode.hidden = true;
    formNode.append(staleNode);
    formNode.addEventListener("submit", (event) => {
      event.preventDefault();
      run();
    });
    frag.append(formNode);
    resultBox = el("div", "ret-result-slot");
    frag.append(resultBox);
    root.replaceChildren(frag);
    paintLine();
    sync();
  }

  function paintLine() {
    if (!lineNode) return;
    lineNode.textContent = S.line;
    lineNode.hidden = !S.line;
  }

  function setBusy(on) {
    S.running = on;
    if (!runBtn) return;
    runBtn.dataset.busy = on ? "true" : "false";
    runBtn.textContent = on ? WORKING : RUN_LABEL;
    root.setAttribute("aria-busy", on ? "true" : "false");
    if (on) runBtn.disabled = true;
    else if (deps.live) deps.live.sync(runBtn);
    else runBtn.disabled = false;
  }

  function paintResult() {
    if (!resultBox) return;
    const r = S.result;
    if (!r) {
      resultBox.replaceChildren();
      return;
    }
    const region = el("section", "ret-result");
    region.dataset.state = r.state;
    region.setAttribute("aria-label", r.title);
    const [headline, ...rest] = r.summary;
    const head = el("p", "ret-headline", headline);
    head.id = "ret-headline";
    head.tabIndex = -1;
    region.append(head);
    if (rest.length) {
      const list = el("ul", "ret-summary");
      for (const s of rest) list.append(el("li", "", s));
      region.append(list);
    }
    // Right after the sentences, on its own line, never collapsible.
    region.append(el("p", "ret-disclaimer", r.disclaimer));
    const meter = drawMeter(r);
    if (meter) region.append(meter);
    if (r.used.length) {
      region.append(el("h3", "subhead ret-used-heading", USED_HEADING));
      const used = el("ul", "ret-used");
      for (const u of r.used) {
        const li = el("li", "ret-used-row");
        li.append(el("span", "ret-used-label", u.label), ": ", el("span", "ret-used-value", u.value));
        if (u.assumed) li.append(" ", el("span", "ret-assumed", ASSUMED));
        used.append(li);
      }
      region.append(used);
    }
    if (r.placeholderNote) region.append(el("p", "note", r.placeholderNote));
    if (r.todaysMoney) region.append(el("p", "note", r.todaysMoney));
    resultBox.replaceChildren(region);
  }

  function takeFocus() {
    const want = S.focus;
    S.focus = "";
    if (!want) return;
    const node = want === "result" ? root.querySelector("#ret-headline")
      : want === "line" ? lineNode : S.inputs.get(want);
    if (node && typeof node.focus === "function") {
      if (node === lineNode) node.tabIndex = -1;
      node.focus({ preventScroll: false });
    }
  }

  function showFieldError(key, message) {
    const err = S.errors.get(key);
    const input = S.inputs.get(key);
    if (!err || !input) return false;
    err.textContent = message;
    err.hidden = false;
    input.setAttribute("aria-invalid", "true");
    const ids = (input.getAttribute("aria-describedby") || "").split(" ").filter(Boolean);
    if (!ids.includes(err.id)) input.setAttribute("aria-describedby", [...ids, err.id].join(" "));
    return true;
  }

  function clearErrors() {
    for (const [k, err] of S.errors) {
      err.hidden = true;
      err.textContent = "";
      const input = S.inputs.get(k);
      if (input) input.removeAttribute("aria-invalid");
    }
  }

  async function ask(values) {
    return deps.invoke("brain_retirement_run", { values });
  }

  async function run() {
    if (S.running || !S.form || !deps.isTauri) return;
    if (deps.canAct && !deps.canAct()) return;
    const gen = S.gen;
    const form = S.form;
    const values = collectValues(form.fields, texts());
    clearErrors();
    S.line = "";
    S.result = null;
    paintLine();
    paintResult();
    setBusy(true);
    say(WORKING);
    let answer;
    try {
      answer = await ask(values);
      if (gen !== S.gen) return;
      if (isObj(answer) && answer.ok === false && answer.error === "busy") {
        // One run at a time on the PC: try once more after a second.
        await new Promise((resolve) => setTimeout(resolve, RETRY_MS));
        if (gen !== S.gen) return;
        answer = await ask(values);
      }
    } catch (error) {
      if (gen !== S.gen) return;
      S.line = String((error && error.message) || error);
      setBusy(false);
      paintLine();
      say(S.line, "assertive");
      return;
    }
    if (gen !== S.gen) return;
    setBusy(false);
    if (isObj(answer) && answer.hidden === true) {
      // Hidden or locked while it ran: nothing of what was typed stays.
      const words = isObj(answer.words) && answer.words.hidden ? answer.words.hidden : HIDDEN_WORDS;
      clear();
      paintHidden(words);
      return;
    }
    if (isObj(answer) && answer.ok === true) {
      const result = readResult(answer.result);
      if (!result) {
        S.line = NO_RESULT;
        paintLine();
        say(S.line, "assertive");
        return;
      }
      S.result = result;
      paintResult();
      S.focus = "result";
      takeFocus();
      return;
    }
    const where = placement(answer, form.fields);
    if (where.kind === "field" && showFieldError(where.key, where.message)) {
      S.focus = where.key;
      say(where.message, "assertive");
      takeFocus();
      return;
    }
    // busy twice, too slow, an unknown field: the PC's words under the button.
    S.line = where.message;
    paintLine();
    say(S.line, "assertive");
    S.focus = "line";
    takeFocus();
  }

  /** Reads the form from the PC (Rust decides whether it comes back hidden). */
  async function load() {
    if (S.loading) return;
    if (!deps.isTauri) {
      paintNote(NO_FORM);
      return;
    }
    S.loading = true;
    const gen = S.gen;
    if (!S.hidden) paintNote("Reading\u2026");
    let answer;
    try {
      answer = await deps.invoke("brain_retirement_defaults", {});
    } catch (error) {
      if (gen !== S.gen) return;
      S.loading = false;
      paintNote(String((error && error.message) || error));
      return;
    }
    if (gen !== S.gen) return;
    S.loading = false;
    const form = readForm(answer);
    if (!form) {
      paintNote(NO_FORM);
      return;
    }
    if (form.hidden) {
      paintHidden(form.words);
      return;
    }
    S.form = form;
    S.hidden = false;
    paintForm();
  }

  /** The tab is showing: read the form once; a drawn form keeps what is typed. */
  function enter() {
    // A hidden card asks again on every showing, so "Show" brings the form back.
    if (S.form || S.loading) return;
    load();
  }

  /** The tab, or the window, is going: nothing typed stays. */
  function leave() {
    if (!S.form && !S.hidden && !S.loading && !S.result) return;
    clear();
  }

  /** The private lists or App lock changed: forget it all and ask again. */
  function recheck() {
    clear();
    if (deps.view && deps.view() === "work") load();
  }

  /** The link changed: the button greys and the card says why (rule 4). */
  function sync() {
    if (runBtn && deps.live) deps.live.sync(runBtn);
    if (staleNode) staleNode.hidden = !deps.canAct || deps.canAct();
  }

  if (deps.listen) {
    deps.listen("security-changed", recheck);
    deps.listen("private-hidden", recheck);
  }
  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) leave();
      else if (deps.view && deps.view() === "work") enter();
    });
    window.addEventListener("pagehide", () => leave());
  }

  return { enter, leave, recheck, sync, clear, _state: S };
}
