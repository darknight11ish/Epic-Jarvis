/**
 * "Spending summaries" (the owner's decision of 2026-09-30, queue item 2;
 * docs/FINANCE-DESIGN.md part A "Slice contract (frozen)"; JARVIS-API.md
 * section 100; backend jarvis_spending.py).
 *
 * Two halves, both plain code with no page state of their own here:
 *
 *  1. THE CHAT TABLE. The chat stream carries `: jarvis-table <32 hex>` right
 *     before the answer's sentence (a `stream: false` body carries a
 *     top-level `jarvis_table`). The Jarvis bar then asks the Rust command
 *     `chat_table` for the table and draws it under the sentence.
 *       - Every string is put in with textContent, never as markup: a cell is
 *         a bank file's own text ("=HYPERLINK(...)" stays that text).
 *       - Figures are drawn exactly as sent. This file never adds, rounds,
 *         sorts, re-formats or hides one, and never makes a percentage.
 *       - The table lives in this closure's memory only: not localStorage, not
 *         a file, no export, no copy-all button. It is dropped with the
 *         conversation (`clear`) and when the lists are hidden.
 *       - While "Hide memory lists and chat history" is on, or App lock has
 *         locked Jarvis, the words "Spending table hidden" are drawn instead
 *         (Rust does not even ask the PC; it answers `{hidden: true}`).
 *       - It is never read aloud (the tool is not on the read-aloud list and
 *         this file has no speech in it).
 *  2. THE SETTINGS BOX helpers: the "Check these columns" form state, the
 *     categories editor's list handling. spending-settings.js draws them.
 *
 * @module spending
 */

/** The words the contract fixes (spending-cases.json `words`; a test
 *  compares every one). The app shows the PC's `message` when it has one. */
export const WORDS = Object.freeze({
  TITLE: "Spending",
  DETAIL:
    "Drop a bank export (CSV or Excel) into a folder Jarvis may look in, then ask in chat, for example \"how much did I spend on food last month?\". Jarvis adds the numbers up with plain code and shows a small table on screen. The table is never read aloud, never remembered and never sent anywhere. Account and card numbers in the file are hidden.",
  PC_ONLY: "Set up on the PC: Settings, Spending. The columns of a new bank file are checked there, once.",
  NEEDS_SETUP_ON_PC:
    "Open Jarvis on the PC to check the columns of this bank file (Settings, Spending). It takes a minute and is remembered.",
  EMPTY_PROFILES: "No bank layouts saved yet.",
  STARTER_NOTE: "These are starter categories. Change the words to suit the shops you use.",
  HIDDEN_COLUMNS_NOTE: "A column that looks like an account or card number is not shown, and cannot be used.",
  TABLE_HIDDEN: "Spending table hidden",
  TABLE_GONE: "This table is no longer kept. Ask again to see it.",
});

/** Desktop-only words (contract section 5) and the few lines this app adds
 *  where the contract has none. */
export const BOX = Object.freeze({
  dialogTitle: "Check these columns",
  save: "Save these columns",
  cancel: "Cancel",
  forget: "Forget this layout",
  again: "Check the columns again",
  categories: "Categories",
  suggest: "Suggest categories",
  addRules: "Add these rules",
  reset: "Reset to the starter list",
  resetSure: "Put the starter categories back? Your own changes will go.",
  resetYes: "Yes, reset",
  resetNo: "No, keep mine",
  saveCategories: "Save categories",
  firstMatch: "The first category that matches a shop name wins, so the order matters.",
  wholeWord: "Words match whole words, in any case.",
  fromLine: "From: ",
  unreadable: "This table could not be shown.",
  checkColumns: "Check the columns",
  // (audit 2026-09-30) the picker, the counts and the "save it anyway" tick.
  chooseFile: "Choose a bank file…",
  noFileForLayout: "No bank file with this layout was found in your folders.",
  acceptTick: "This does not look right, but save it anyway",
  forgetSure: "Forget this layout? Files that use it will need their columns checked again.",
  forgetYes: "Yes, forget it",
  forgetNo: "No, keep it",
  checking: "Checking what these choices would count…",
  misfitPrefix: "This does not look right: ",
});

/** The most a category list may hold (JARVIS-API section 100.4). */
export const MAX_CATEGORIES = 40;
export const MAX_WORDS = 200;

/* ── The stream marker ───────────────────────────────────────────────── */

const MARK = /^:\s*jarvis-table\s+([0-9a-f]{32})\s*$/;

/** The id in a `: jarvis-table <id>` comment line, or null. */
export function tableIdFromLine(line) {
  if (typeof line !== "string") return null;
  const m = MARK.exec(line.trim());
  return m ? m[1] : null;
}

/** The id a `stream: false` body carries as a top-level `jarvis_table`. */
export function tableIdFromBody(body) {
  const id = body && typeof body === "object" ? body.jarvis_table : null;
  return typeof id === "string" && /^[0-9a-f]{32}$/.test(id) ? id : null;
}

/* ── Reading the block ───────────────────────────────────────────────── */

const isStr = (v) => typeof v === "string";
const strs = (a) => Array.isArray(a) && a.every(isStr);

function groupOf(list, width) {
  if (!Array.isArray(list)) return null;
  const out = [];
  for (const row of list) {
    if (!row || !isStr(row.kind) || !strs(row.cells) || row.cells.length !== width) return null;
    out.push({ kind: row.kind, cells: row.cells.slice() });
  }
  return out;
}

/**
 * The table block, checked against the contract (section 2): `kind`
 * "spending", `version` 1, columns with a key, label and align, and EVERY
 * `cells` list exactly one string per column. Returns a plain copy, or null
 * for anything else - a table that does not fit is not drawn half-way.
 */
export function readTable(raw) {
  if (!raw || typeof raw !== "object" || raw.kind !== "spending" || raw.version !== 1) return null;
  if (!isStr(raw.title) || !isStr(raw.period) || !strs(raw.sources) || !strs(raw.caveats)) return null;
  if (!Array.isArray(raw.columns) || !raw.columns.length || !Array.isArray(raw.sections)) return null;
  const columns = [];
  for (const c of raw.columns) {
    if (!c || !isStr(c.key) || !isStr(c.label) || (c.align !== "left" && c.align !== "right")) return null;
    columns.push({ key: c.key, label: c.label, align: c.align });
  }
  const sections = [];
  for (const s of raw.sections) {
    if (!s || !isStr(s.heading) || !isStr(s.currency)) return null;
    const rows = groupOf(s.rows, columns.length);
    const totals = groupOf(s.totals, columns.length);
    const also = groupOf(s.also, columns.length);
    if (!rows || !totals || !also) return null;
    sections.push({ heading: s.heading, currency: s.currency, rows, totals, also });
  }
  return {
    title: raw.title,
    period: raw.period,
    sources: raw.sources.slice(),
    columns,
    sections,
    caveats: raw.caveats.slice(),
    hiddenWords: raw.words && isStr(raw.words.hidden) ? raw.words.hidden : WORDS.TABLE_HIDDEN,
  };
}

/**
 * What a screen reader hears for one row (section 2): its cells joined by
 * commas with the column labels - "Food and groceries, Spent 70.40, Rows 2" -
 * and a totals row says "Total" first.
 */
export function rowSummary(columns, row, isTotal = false) {
  const parts = row.cells.map((cell, i) => (i === 0 ? cell : `${columns[i].label} ${cell}`));
  return (isTotal ? "Total, " : "") + parts.join(", ");
}

/** "From: a.csv, b.csv" - the sources on one muted line. */
export function sourcesLine(sources) {
  return sources.length ? BOX.fromLine + sources.join(", ") : "";
}

/* ── Drawing ─────────────────────────────────────────────────────────── */

function el(doc, tag, className, text) {
  const n = doc.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

function rowNode(doc, columns, row, group) {
  const tr = el(doc, "tr", `st-row st-${row.kind}`);
  tr.dataset.kind = row.kind;
  tr.setAttribute("aria-label", rowSummary(columns, row, group === "totals"));
  row.cells.forEach((cell, i) => {
    // The first cell names the row; the figures are the rest.
    const td = el(doc, i === 0 ? "th" : "td", `st-cell st-${columns[i].align}`, cell);
    if (i === 0) td.scope = "row";
    tr.append(td);
  });
  return tr;
}

/**
 * Draws a checked table (from `readTable`) into a new element. Every string
 * goes in with textContent. One real <table> per currency, with a caption,
 * column headers and row headers; the wrapper scrolls sideways (up to 13
 * columns) and can be reached from the keyboard.
 */
export function buildTable(doc, table) {
  const box = el(doc, "section", "spending-table");
  box.dataset.state = "shown";
  box.setAttribute("aria-label", table.title);
  box.append(el(doc, "p", "st-title", table.title));
  if (table.period) box.append(el(doc, "p", "st-period", table.period));
  table.sections.forEach((s) => {
    if (s.heading) box.append(el(doc, "p", "st-heading", s.heading));
    const scroll = el(doc, "div", "st-scroll");
    scroll.tabIndex = 0;
    scroll.setAttribute("role", "region");
    scroll.setAttribute(
      "aria-label",
      `${table.title}${s.heading ? `, ${s.heading}` : ""}${table.period ? `, ${table.period}` : ""}`
    );
    const t = el(doc, "table", "st-table");
    t.append(el(doc, "caption", "st-caption", `${table.title}${s.heading ? `, ${s.heading}` : ""}`));
    const head = el(doc, "thead");
    const hr = el(doc, "tr");
    table.columns.forEach((c) => {
      const th = el(doc, "th", `st-cell st-${c.align}`, c.label);
      th.scope = "col";
      hr.append(th);
    });
    head.append(hr);
    t.append(head);
    const body = el(doc, "tbody", "st-rows");
    s.rows.forEach((r) => body.append(rowNode(doc, table.columns, r, "rows")));
    t.append(body);
    if (s.totals.length) {
      const tot = el(doc, "tbody", "st-totals");
      s.totals.forEach((r) => tot.append(rowNode(doc, table.columns, r, "totals")));
      t.append(tot);
    }
    if (s.also.length) {
      const also = el(doc, "tbody", "st-also");
      s.also.forEach((r) => also.append(rowNode(doc, table.columns, r, "also")));
      t.append(also);
    }
    scroll.append(t);
    box.append(scroll);
  });
  if (table.caveats.length) {
    const ul = el(doc, "ul", "st-caveats");
    table.caveats.forEach((c) => ul.append(el(doc, "li", "", c)));
    box.append(ul);
  }
  const from = sourcesLine(table.sources);
  if (from) box.append(el(doc, "p", "st-sources", from));
  return box;
}

/** The place a hidden, gone or unreadable table is said in words. */
export function buildNote(doc, text, state) {
  const p = el(doc, "p", "spending-note", text);
  p.dataset.state = state;
  p.setAttribute("role", "status");
  return p;
}

/**
 * The table under the newest answer in the Jarvis bar.
 *
 *   const view = mountSpendingTable(box, { invoke, announce, onChange, doc });
 *   view.arrived(id)   // the stream announced a table
 *   view.recheck()     // the bar was shown again / focused: ask again
 *   view.hide()        // the private lists went hidden: draw the words now
 *   view.clear()       // a new question, or the conversation ended
 *
 * Kept in memory only: `id` and the drawn table live in this closure and
 * nowhere else. Hidden or gone, the table is dropped and only words remain.
 */
export function mountSpendingTable(box, { invoke, announce = () => {}, onChange = () => {}, doc } = {}) {
  const d = doc || box.ownerDocument;
  let id = null;
  let table = null;
  let ask = 0;

  function show(node, announceText) {
    box.replaceChildren(node);
    box.hidden = false;
    if (announceText) announce(announceText);
    onChange();
  }

  function drop() {
    table = null;
  }

  async function load(quiet) {
    if (!id) return;
    const mine = ++ask;
    const asked = id;
    let out;
    try {
      out = await invoke("chat_table", { id: asked });
    } catch (error) {
      if (mine !== ask) return;
      drop();
      const said = String((error && error.message) || error || "").trim();
      show(buildNote(d, said && said.length < 300 && !/[{}<>]/.test(said) ? said : BOX.unreadable, "error"));
      return;
    }
    // A newer question (or a newer table) has taken over: this answer is stale.
    if (mine !== ask || asked !== id) return;
    if (out && out.hidden === true) {
      drop();
      show(buildNote(d, WORDS.TABLE_HIDDEN, "hidden"), quiet ? "" : WORDS.TABLE_HIDDEN);
      return;
    }
    if (out && out.gone === true) {
      drop();
      show(buildNote(d, isStr(out.message) && out.message ? out.message : WORDS.TABLE_GONE, "gone"));
      return;
    }
    const read = readTable(out && out.table);
    if (!read) {
      drop();
      show(buildNote(d, BOX.unreadable, "error"));
      return;
    }
    table = read;
    show(buildTable(d, read), quiet ? "" : `${read.title}. Table shown.`);
  }

  return {
    arrived(newId) {
      id = newId;
      drop();
      return load(false);
    },
    recheck() {
      if (id) return load(true);
      return Promise.resolve();
    },
    hide() {
      if (!id) return;
      ask += 1;
      drop();
      show(buildNote(d, WORDS.TABLE_HIDDEN, "hidden"));
    },
    clear() {
      ask += 1;
      id = null;
      drop();
      box.replaceChildren();
      if (!box.hidden) {
        box.hidden = true;
        onChange();
      }
    },
    /** For the tests: what is held. */
    held() {
      return { id, drawn: Boolean(table) };
    },
  };
}

/* ── Settings: the "Check these columns" form ────────────────────────── */

export const MODES = Object.freeze({
  one: "One amount column",
  debit_credit: "Separate Debit and Credit columns",
  drcr: "An amount column and a Dr/Cr column",
});
export const SIGN_CHOICES = Object.freeze({
  negative_out: "Minus means money spent",
  positive_out: "Plus means money spent",
});
export const ORDER_CHOICES = Object.freeze({
  dmy: "Day first, like 25/03/2026",
  mdy: "Month first, like 03/25/2026",
});
export const ORDER_OWN = "The dates say their own order";
export const DECIMALS = Object.freeze({ ".": ".", ",": "," });

/** The amount mode a `sign` belongs to. */
export function modeOfSign(sign) {
  if (sign === "negative_out" || sign === "positive_out") return "one";
  if (sign === "debit_credit" || sign === "drcr") return sign;
  return null;
}

/** The `sign` value a mode + sign rule send. */
export function signOf(mode, sign1) {
  if (mode === "one") return sign1 === "negative_out" || sign1 === "positive_out" ? sign1 : null;
  return mode === "debit_credit" || mode === "drcr" ? mode : null;
}

function has(questions, q) {
  return Array.isArray(questions) && questions.includes(q);
}

/**
 * The column numbers a dropdown offers, with their names. Values are the
 * ORIGINAL column numbers (`header_index`), never positions in `header`.
 * With no usable header (`header_row` in `questions`) the columns are as wide
 * as the widest preview row, named "Column N".
 */
export function columnOptions(proposal) {
  const header = Array.isArray(proposal.header) ? proposal.header : [];
  const index = Array.isArray(proposal.header_index) ? proposal.header_index : [];
  if (header.length && index.length === header.length) {
    return index.map((n, i) => ({ value: n, label: `${n + 1}. ${header[i]}` }));
  }
  const width = Math.max(0, ...((proposal.preview || []).map((r) => (Array.isArray(r) ? r.length : 0))));
  return Array.from({ length: width }, (_, n) => ({ value: n, label: `Column ${n + 1}` }));
}

/**
 * The form's state for a proposal. Every field the file could not settle
 * (`questions`) starts with NO choice, and so does everything when
 * `header_row` is in `questions` (there is no usable guess then): the app
 * never fills in a guess the PC said it could not make.
 */
export function formFor(proposal, file) {
  const q = proposal.questions || [];
  const g = proposal.guess || null;
  const noHeader = has(q, "header_row") || !g;
  const cols = (g && g.columns) || {};
  const pick = (name, question) => (noHeader || has(q, question) || cols[name] == null ? null : cols[name]);
  const signUnsure = noHeader || has(q, "sign") || !g || !g.sign;
  const amountUnsure = has(q, "amount_column");
  const mode = signUnsure ? null : modeOfSign(g.sign);
  const ymd = Boolean(g) && g.date_order === "ymd" && !has(q, "date_order") && !noHeader;
  const tolerant = (name) => (noHeader || amountUnsure || cols[name] == null ? null : cols[name]);
  return {
    file,
    fingerprint: proposal.fingerprint || "",
    headerRow: noHeader ? null : g.header_row,
    askHeaderRow: noHeader,
    dateColumn: pick("date", "date_column"),
    descriptionColumn: pick("description", "description_column"),
    mode,
    sign1: signUnsure ? null : mode === "one" ? g.sign : null,
    amountColumn: tolerant("amount"),
    debitColumn: tolerant("debit"),
    creditColumn: tolerant("credit"),
    drcrColumn: tolerant("drcr"),
    dateOrder: ymd ? "ymd" : noHeader || has(q, "date_order") || !g.date_order ? null : g.date_order,
    ownOrder: ymd,
    decimal: noHeader || has(q, "decimal") || !g.decimal ? null : g.decimal,
    currency: g && isStr(g.currency) ? g.currency : "",
    label: g && isStr(g.label) ? g.label : "",
    // (audit) what the box asked, sent back as `answered`; an Excel column of
    // date serials keeps its flag.
    questions: q.filter(isStr),
    dateSerial: Boolean(g) && g.date_serial === true,
  };
}

/** True once every choice Save needs has been made. */
export function canSave(f) {
  if (!f || !f.file) return false;
  if (f.askHeaderRow && f.headerRow == null) return false;
  if (f.dateColumn == null || f.descriptionColumn == null) return false;
  if (f.dateOrder == null || f.decimal == null || f.mode == null) return false;
  if (f.mode === "one" && (f.amountColumn == null || signOf("one", f.sign1) == null)) return false;
  if (f.mode === "debit_credit" && (f.debitColumn == null || f.creditColumn == null)) return false;
  if (f.mode === "drcr" && (f.amountColumn == null || f.drcrColumn == null)) return false;
  if (f.currency.length > 6 || f.label.length > 60) return false;
  return true;
}

/** The body of the save call (Rust adds `confirm: true`). Null while
 *  `canSave` is false. `accept`: the owner ticked "save it anyway" after the
 *  PC said the choices do not fit the file. */
export function saveBody(f, { accept = false } = {}) {
  if (!canSave(f)) return null;
  const columns = { date: f.dateColumn, description: f.descriptionColumn };
  if (f.mode === "one") columns.amount = f.amountColumn;
  else if (f.mode === "debit_credit") {
    columns.debit = f.debitColumn;
    columns.credit = f.creditColumn;
  } else {
    columns.amount = f.amountColumn;
    columns.drcr = f.drcrColumn;
  }
  return {
    file: f.file,
    header_row: f.headerRow == null ? 0 : f.headerRow,
    columns,
    sign: signOf(f.mode, f.sign1),
    date_order: f.dateOrder,
    decimal: f.decimal,
    currency: f.currency.trim(),
    label: f.label.trim(),
    answered: (f.questions || []).slice(),
    date_serial: f.dateSerial === true,
    ...(accept ? { accept_warnings: true } : {}),
  };
}

/** The body of the "what would this count?" call: the same choices, `preview:
 *  true`, and (in Rust) no `confirm`. Null while `canSave` is false. */
export function previewBody(f) {
  const body = saveBody(f);
  return body ? { ...body, preview: true } : null;
}

/** Reading the PC's preview answer: `{line, warnings, problems}` (all empty
 *  for anything that is not a ready preview - the box then says nothing and
 *  the PC's own check on Save still applies). */
export function previewState(answer) {
  if (!answer || answer.ready !== true) return { line: "", warnings: [], problems: [] };
  const warnings = Array.isArray(answer.warnings) ? answer.warnings.filter(isStr) : [];
  const problems = Array.isArray(answer.problems) ? answer.problems.filter(isStr) : [];
  return { line: isStr(answer.line) ? answer.line : "", warnings, problems };
}

/** Save is allowed once the choices are complete and, if the PC said they do
 *  not fit the file, the owner ticked the box. */
export function canPress(f, state, accepted) {
  if (!canSave(f)) return false;
  return !(state && state.problems && state.problems.length) || accepted === true;
}

/* ── Settings: the bank file picker ──────────────────────────────────── */

/** The options of the Bank file picker: the files the PC found, by name. The
 *  value is the path (the PC sends a path only to itself). */
export function pickerOptions(view) {
  const files = view && Array.isArray(view.bank_files) ? view.bank_files : [];
  return files
    .filter((f) => f && isStr(f.path) && isStr(f.name))
    .map((f) => ({
      value: f.path,
      label: f.name + (f.waiting ? " (columns not checked yet)" : ""),
    }));
}

/** The files that use a saved layout (its `id` is their `layout_id`). */
export function filesForLayout(view, layoutId) {
  const files = view && Array.isArray(view.bank_files) ? view.bank_files : [];
  return files.filter((f) => f && isStr(f.path) && f.layout_id === layoutId).map((f) => f.path);
}

/** The file "Check the columns again" opens for a layout row: the picker's
 *  file when it uses that layout, else the first file that does; null when
 *  none is known. Never a free-typed path. */
export function fileForAgain(view, layoutId, picked) {
  const files = filesForLayout(view, layoutId);
  if (picked && files.includes(picked)) return picked;
  return files.length ? files[0] : null;
}

/** "Saved. 7 rows read, 1 left out." - the contract's line. */
export function savedLine(answer) {
  const read = Number(answer && answer.rows_read) || 0;
  const skipped = Number(answer && answer.rows_skipped) || 0;
  return `Saved. ${read} rows read, ${skipped} left out.`;
}

/* ── Settings: the categories editor ─────────────────────────────────── */

/** Comma- or line-separated text to the words the PC keeps: trimmed,
 *  lower-case, no empties, no repeats. */
export function parseWords(text) {
  const seen = new Set();
  const out = [];
  for (const raw of String(text || "").split(/[,\n]/)) {
    const w = raw.trim().toLowerCase();
    if (w && !seen.has(w)) {
      seen.add(w);
      out.push(w);
    }
  }
  return out;
}

export function wordsText(words) {
  return (words || []).join(", ");
}

/** A copy of the list moved one place (first match wins, so order matters). */
export function moved(list, from, to) {
  if (to < 0 || to >= list.length || from === to) return list.slice();
  const out = list.slice();
  const [item] = out.splice(from, 1);
  out.splice(to, 0, item);
  return out;
}

/**
 * The list with the ticked suggestions merged into their category's words
 * (lower-case, no repeats). A suggestion for a category that is not there is
 * left out - nothing new is invented. Nothing is added by the model on its
 * own: the owner ticks, then taps "Add these rules".
 */
export function mergeSuggestions(categories, ticked) {
  const out = categories.map((c) => ({ category: c.category, words: c.words.slice() }));
  for (const s of ticked) {
    const home = out.find((c) => c.category === s.category);
    const w = String(s.name || "").trim().toLowerCase();
    if (home && w && !home.words.includes(w) && home.words.length < MAX_WORDS) home.words.push(w);
  }
  return out;
}

/** The categories as the PC wants them: names and words only. */
export function categoriesBody(list) {
  return list.map((c) => ({ category: c.category, words: c.words.slice() }));
}
