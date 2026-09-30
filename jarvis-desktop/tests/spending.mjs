/**
 * "Spending summaries" on the desktop (the owner's decision of 2026-09-30,
 * queue item 2; docs/FINANCE-DESIGN.md part A "Slice contract (frozen)";
 * JARVIS-API.md section 100; src/spending.js, src/spending-settings.js,
 * src/main.js, src/settings.html, src-tauri/src/spending.rs).
 *
 * What must hold:
 * - the words are the PC's and the phone's, word for word (the contract file
 *   `fixtures/spending-cases.json`, made by tools/gen_spending_cases.py);
 * - the stream's `: jarvis-table <32 hex>` line and a body's `jarvis_table`
 *   are read, and nothing else is taken for one;
 * - every one of the six real tables reads, and is drawn with every figure
 *   exactly as sent: one real <table> per currency, headers, a caption,
 *   totals apart from "also" rows, the caveats and "From: ..." under it;
 * - every string goes in as TEXT: a bank file's cell such as
 *   `=HYPERLINK(...)` or `<img onerror=...>` stays those characters, and no
 *   `innerHTML` is written by either file;
 * - the table is kept in memory only (no storage, no clipboard, no export),
 *   hidden means the words "Spending table hidden" and nothing else, gone
 *   means the PC's sentence, a newer table beats a slower older one;
 * - the "Check these columns" form: every field the file could not settle
 *   starts with NO choice and Save stays off until each has one; the body
 *   sent is the contract's; original column numbers, not positions;
 * - the categories editor's helpers (order, words, merging suggestions);
 * - CONTROL (wiring): the chat table is the Jarvis bar's alone and Settings'
 *   commands are Settings' alone; Rust asks the PC nothing while the words
 *   are hidden, validates the id, holds every write on a stale link and
 *   logs nothing; the settings card has a stable id and a jump link;
 * - with Playwright: the same, in the real Jarvis bar and Settings page.
 *
 * The first half needs no browser (a stand-in for the few DOM calls made);
 * the second half runs only where Playwright is installed.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  BOX,
  buildTable,
  canSave,
  categoriesBody,
  columnOptions,
  formFor,
  mergeSuggestions,
  modeOfSign,
  moved,
  mountSpendingTable,
  parseWords,
  readTable,
  rowSummary,
  saveBody,
  savedLine,
  signOf,
  sourcesLine,
  tableIdFromBody,
  tableIdFromLine,
  WORDS,
  wordsText,
} from "../src/spending.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/spending-cases.json"));
const TABLES = CASES.tables;
const ID = "3f9c0a5e1d7b4c2a8e6f01b2c3d4e5f6";
const ID2 = "00112233445566778899aabbccddeeff";

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── a stand-in for the few DOM calls the table makes ─────────────────── */

class El {
  constructor(tag, doc) {
    this.tag = tag; this.ownerDocument = doc; this.children = []; this.attrs = {};
    this.dataset = {}; this.hidden = false; this.className = ""; this._text = "";
    this.tabIndex = -1; this.scope = "";
  }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); }
  set textContent(v) { this._text = String(v); this.children = []; }
  get innerHTML() { return ""; }
  set innerHTML(_v) { throw new Error("innerHTML was written"); }
  append(...kids) { this.children.push(...kids); }
  replaceChildren(...kids) { this._text = ""; this.children = kids; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  all(pred, out = []) { for (const c of this.children) { if (pred(c)) out.push(c); c.all(pred, out); } return out; }
  byTag(tag) { return this.all((c) => c.tag === tag); }
  byClass(cls) { return this.all((c) => c.className.split(" ").includes(cls)); }
}
function makeDoc() {
  const doc = { made: [] };
  doc.createElement = (tag) => { doc.made.push(tag); return new El(tag, doc); };
  return doc;
}
const boxOf = (doc) => new El("section", doc);

/* ── the words ────────────────────────────────────────────────────────── */

await check("the words are the contract's, word for word", () => {
  for (const key of Object.keys(WORDS)) assert.equal(WORDS[key], CASES.words[key], key);
  assert.equal(TABLES.by_category.words.hidden, WORDS.TABLE_HIDDEN);
  assert.equal(CASES.words.STREAM_MARK, ": jarvis-table ");
  assert.equal(CASES.errors.pc_only, WORDS.PC_ONLY);
  assert.equal(CASES.errors.needs_setup, WORDS.NEEDS_SETUP_ON_PC);
  // The desktop-only words of the column check (contract section 5).
  assert.equal(BOX.dialogTitle, "Check these columns");
  assert.equal(BOX.save, "Save these columns");
  assert.equal(BOX.cancel, "Cancel");
  assert.equal(BOX.forget, "Forget this layout");
  assert.equal(BOX.again, "Check the columns again");
  for (const [k, w] of [["categories", "Categories"], ["suggest", "Suggest categories"],
    ["addRules", "Add these rules"], ["reset", "Reset to the starter list"],
    ["saveCategories", "Save categories"]]) assert.equal(BOX[k], w, k);
});

/* ── the stream marker ────────────────────────────────────────────────── */

await check("the stream's table line is read, and nothing else is taken for it", () => {
  assert.equal(tableIdFromLine(CASES.words.STREAM_MARK + ID), ID);
  assert.equal(tableIdFromLine(`: jarvis-table ${ID}\r`), ID);
  assert.equal(tableIdFromLine(`:jarvis-table   ${ID}  `), ID);
  for (const bad of [": jarvis-status working", `: jarvis-table ${ID.toUpperCase()}`,
    `: jarvis-table ${ID.slice(1)}`, `: jarvis-table ${ID}0`, `jarvis-table ${ID}`,
    `data: jarvis-table ${ID}`, `: jarvis-table ${ID} extra`, "", null, 5]) {
    assert.equal(tableIdFromLine(bad), null, String(bad));
  }
  assert.equal(tableIdFromBody({ jarvis_table: ID, choices: [] }), ID);
  assert.equal(tableIdFromBody({ jarvis_table: "nope" }), null);
  assert.equal(tableIdFromBody({}), null);
  assert.equal(tableIdFromBody(null), null);
});

/* ── reading and drawing the six real tables ──────────────────────────── */

await check("every real table reads, every cells list is one string per column", () => {
  const names = Object.keys(TABLES);
  assert.ok(names.length >= 6, names.join());
  for (const name of names) {
    const t = readTable(TABLES[name]);
    assert.ok(t, name);
    for (const s of t.sections) {
      for (const r of [...s.rows, ...s.totals, ...s.also]) {
        assert.equal(r.cells.length, t.columns.length, `${name}: ${r.cells}`);
      }
    }
    // Nothing added, sorted or re-formatted: same rows, same order, same strings.
    assert.deepEqual(t.sections.map((s) => s.rows.map((r) => r.cells)),
      TABLES[name].sections.map((s) => s.rows.map((r) => r.cells)), name);
  }
});

await check("a table that does not fit the contract is not drawn half-way", () => {
  const t = JSON.parse(JSON.stringify(TABLES.by_category));
  const bad = (edit) => { const c = JSON.parse(JSON.stringify(t)); edit(c); return readTable(c); };
  assert.equal(bad((c) => { c.sections[0].rows[0].cells.pop(); }), null);
  assert.equal(bad((c) => { c.sections[0].rows[0].cells[1] = 5; }), null);
  assert.equal(bad((c) => { c.kind = "other"; }), null);
  assert.equal(bad((c) => { c.version = 2; }), null);
  assert.equal(bad((c) => { c.columns[0].align = "center"; }), null);
  assert.equal(bad((c) => { delete c.sections[0].totals; }), null);
  assert.equal(bad((c) => { c.caveats = "x"; }), null);
  assert.equal(readTable(null), null);
  assert.equal(readTable("x"), null);
});

await check("a row is read as its cells with the column labels; a total says Total first", () => {
  const t = readTable(TABLES.by_category);
  const food = t.sections[0].rows.find((r) => r.cells[0] === "Food and groceries");
  assert.equal(rowSummary(t.columns, food), `Food and groceries, Spent ${food.cells[1]}, Rows ${food.cells[2]}`);
  const tot = t.sections[0].totals[0];
  assert.ok(rowSummary(t.columns, tot, true).startsWith("Total, Total spent, Spent "), rowSummary(t.columns, tot, true));
  assert.equal(sourcesLine(["a.csv", "b.csv"]), "From: a.csv, b.csv");
  assert.equal(sourcesLine([]), "");
});

await check("each real table is drawn: figures as sent, a real table per currency, caveats and sources", () => {
  for (const [name, raw] of Object.entries(TABLES)) {
    const doc = makeDoc();
    const t = readTable(raw);
    const box = buildTable(doc, t);
    assert.equal(box.byTag("table").length, raw.sections.length, name);
    assert.equal(box.byTag("caption").length, raw.sections.length, name);
    const texts = box.all((c) => c.tag === "td" || (c.tag === "th" && c.scope === "row")).map((c) => c.textContent);
    const want = raw.sections.flatMap((s) => [...s.rows, ...s.totals, ...s.also].flatMap((r) => r.cells));
    assert.deepEqual(texts, want, name);
    assert.deepEqual(box.byTag("th").filter((c) => c.scope === "col").map((c) => c.textContent),
      raw.sections.flatMap(() => raw.columns.map((c) => c.label)), name);
    assert.deepEqual(box.byTag("li").map((c) => c.textContent), raw.caveats, name);
    const from = box.byClass("st-sources");
    assert.equal(from.length, raw.sources.length ? 1 : 0, name);
    if (from.length) assert.equal(from[0].textContent, "From: " + raw.sources.join(", "), name);
    assert.equal(box.byClass("st-title")[0].textContent, raw.title, name);
    assert.equal(box.byClass("st-period")[0].textContent, raw.period, name);
    // Right-aligned figures, a left first column (the contract's `align`).
    const firstRow = box.byTag("tr").find((r) => r.dataset.kind);
    assert.ok(firstRow.children[0].className.includes("st-left"), name);
    assert.ok(firstRow.children[firstRow.children.length - 1].className.includes("st-right"), name);
    // The scroller can be reached with the keyboard.
    for (const sc of box.byClass("st-scroll")) {
      assert.equal(sc.tabIndex, 0); assert.equal(sc.attrs.role, "region"); assert.ok(sc.attrs["aria-label"]);
    }
    // Every row carries the screen-reader summary.
    for (const tr of box.byTag("tr").filter((r) => r.dataset.kind)) assert.ok(tr.attrs["aria-label"], name);
  }
});

await check("two currencies are two tables, each under its heading, never merged", () => {
  const doc = makeDoc();
  const box = buildTable(doc, readTable(TABLES.two_currencies));
  assert.equal(box.byTag("table").length, 2);
  assert.deepEqual(box.byClass("st-heading").map((h) => h.textContent), ["GBP", "EUR"]);
  const t = readTable(TABLES.by_category_and_month);
  assert.ok(t.columns.length >= 3);
});

await check("totals sit in their own group and 'also' rows apart from spending", () => {
  const doc = makeDoc();
  const raw = TABLES.two_currencies;
  const box = buildTable(doc, readTable(raw));
  const first = box.byTag("table")[0];
  assert.deepEqual(first.byClass("st-totals")[0].byTag("th").map((c) => c.textContent), ["Total spent"]);
  assert.deepEqual(first.byClass("st-also")[0].byTag("th").map((c) => c.textContent), ["Income and other money in"]);
  // "Uncategorised" is an ordinary row: no warning class, no icon.
  const unc = first.byTag("tr").find((r) => r.dataset.kind === "uncategorised");
  assert.ok(unc && !/warn|bad|error/.test(unc.className));
});

await check("a bank file's text stays text: formulas and markup are not run", () => {
  const raw = JSON.parse(JSON.stringify(TABLES.by_category));
  const evil = ["=HYPERLINK(\"http://x.example\",\"pay\")", "<img src=x onerror=alert(1)>",
    "@SUM(A1:A9)", "+1+1", "-2+3", "<script>alert(1)</script>", "&lt;b&gt;", "[hidden]"];
  while (raw.sections[0].rows.length < evil.length) raw.sections[0].rows.push(JSON.parse(JSON.stringify(raw.sections[0].rows[0])));
  evil.forEach((v, i) => { raw.sections[0].rows[i].cells[0] = v; });
  raw.caveats = ["=cmd|' /C calc'!A0"];
  raw.sources = ["<b>x</b>.csv"];
  raw.title = "<h1>t</h1>";
  const doc = makeDoc();
  const box = buildTable(doc, readTable(raw));
  const all = box.textContent;
  for (const v of ["=HYPERLINK(\"http://x.example\",\"pay\")", "<img src=x onerror=alert(1)>",
    "<script>alert(1)</script>", "=cmd|' /C calc'!A0", "<b>x</b>.csv", "<h1>t</h1>"]) {
    assert.ok(all.includes(v), v);
  }
  for (const banned of ["img", "script", "a", "iframe", "button", "input", "h1", "b"]) {
    assert.ok(!doc.made.includes(banned), `made a <${banned}>`);
  }
});

await check("neither file writes innerHTML, storage, the clipboard or a download", () => {
  for (const file of ["src/spending.js", "src/spending-settings.js"]) {
    const src = read(file).replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
    for (const banned of [/innerHTML/, /insertAdjacentHTML/, /outerHTML/, /document\.write/, /localStorage/,
      /sessionStorage/, /indexedDB/, /clipboard/i, /Blob\(/, /createObjectURL/, /\.download\b/,
      /speechSynthesis/, /\bspeak\w*\(/, /eval\(/, /new Function/, /console\./]) {
      assert.ok(!banned.test(src), `${file} has ${banned}`);
    }
  }
});

/* ── the table under the answer ───────────────────────────────────────── */

function mount(over = {}) {
  const doc = makeDoc();
  const box = boxOf(doc);
  box.hidden = true;
  const calls = [];
  const said = [];
  let changes = 0;
  const view = mountSpendingTable(box, {
    invoke: over.invoke || (async (command, args) => {
      calls.push([command, args]);
      return { table: TABLES.by_category };
    }),
    announce: (t) => said.push(t),
    onChange: () => { changes += 1; },
    doc,
  });
  return { box, view, calls, said, doc, changes: () => changes };
}

await check("the bar asks for the table by its id and draws it", async () => {
  const m = mount();
  await m.view.arrived(ID);
  assert.deepEqual(m.calls, [["chat_table", { id: ID }]]);
  assert.equal(m.box.hidden, false);
  assert.equal(m.box.byTag("table").length, 1);
  assert.ok(m.said.some((s) => s.includes(TABLES.by_category.title)), m.said.join());
  assert.deepEqual(m.view.held(), { id: ID, drawn: true });
  assert.ok(m.changes() >= 1, "the window was told to resize");
});

await check("hidden: only the words are drawn and nothing of the table is kept", async () => {
  const m = mount({ invoke: async () => ({ hidden: true, words: "Spending table hidden" }) });
  await m.view.arrived(ID);
  assert.equal(m.box.textContent, WORDS.TABLE_HIDDEN);
  assert.equal(m.box.byTag("table").length, 0);
  assert.deepEqual(m.view.held(), { id: ID, drawn: false });
});

await check("the private lists going hidden takes a drawn table off the screen at once", async () => {
  const m = mount();
  await m.view.arrived(ID);
  m.view.hide();
  assert.equal(m.box.textContent, WORDS.TABLE_HIDDEN);
  assert.equal(m.box.byTag("table").length, 0);
  assert.equal(m.view.held().drawn, false);
  // ...and it comes back on the next look once Rust says it may.
  await m.view.recheck();
  assert.equal(m.box.byTag("table").length, 1);
});

await check("gone: the PC's sentence, and a PC that sent none gets the contract's", async () => {
  let m = mount({ invoke: async () => ({ gone: true, message: CASES.words.TABLE_GONE }) });
  await m.view.arrived(ID);
  assert.equal(m.box.textContent, CASES.words.TABLE_GONE);
  m = mount({ invoke: async () => ({ gone: true }) });
  await m.view.arrived(ID);
  assert.equal(m.box.textContent, WORDS.TABLE_GONE);
});

await check("a failed ask says so in words, never a bridge error; an unreadable table is not drawn", async () => {
  let m = mount({ invoke: async () => { throw new Error("Jarvis is not answering."); } });
  await m.view.arrived(ID);
  assert.equal(m.box.textContent, "Jarvis is not answering.");
  m = mount({ invoke: async () => { throw new Error("{\"x\": 1} not allowed by ACL"); } });
  await m.view.arrived(ID);
  assert.equal(m.box.textContent, BOX.unreadable);
  m = mount({ invoke: async () => ({ table: { kind: "spending", version: 1 } }) });
  await m.view.arrived(ID);
  assert.equal(m.box.textContent, BOX.unreadable);
  assert.equal(m.view.held().drawn, false);
});

await check("a new question clears the table; a slower older answer does not overwrite a newer one", async () => {
  let release;
  const gate = new Promise((r) => { release = r; });
  const m = mount({
    invoke: async (_c, args) => {
      if (args.id === ID) { await gate; return { table: TABLES.by_month }; }
      return { table: TABLES.by_category };
    },
  });
  const first = m.view.arrived(ID);
  await m.view.arrived(ID2);
  release();
  await first;
  assert.equal(m.box.byClass("st-title")[0].textContent, TABLES.by_category.title);
  m.view.clear();
  assert.equal(m.box.hidden, true);
  assert.deepEqual(m.view.held(), { id: null, drawn: false });
  assert.equal(m.box.children.length, 0);
  // Nothing to look again at after a clear.
  const before = m.calls.length;
  await m.view.recheck();
  assert.equal(m.calls.length, before);
});

/* ── the "Check these columns" form ───────────────────────────────────── */

const UNSETTLED = CASES.proposal_date_order_unsettled;
const SETTLED = CASES.proposal_signed_amount;

await check("a settled file is ready to save; an unsettled question starts with no choice", () => {
  const ok = formFor(SETTLED, "C:\\bank\\a.csv");
  assert.equal(ok.ownOrder, true, "ymd: the dates say their own order");
  assert.equal(canSave(ok), true);
  const body = saveBody(ok);
  assert.deepEqual(body, {
    file: "C:\\bank\\a.csv", header_row: 0,
    columns: { date: 0, description: 1, amount: 2 },
    sign: "negative_out", date_order: "ymd", decimal: ".", currency: "", label: "a_signed.csv",
  });
  const f = formFor(UNSETTLED, "C:\\bank\\h.csv");
  assert.deepEqual(UNSETTLED.questions, ["date_order"]);
  assert.equal(f.dateOrder, null);
  assert.equal(f.ownOrder, false);
  assert.equal(canSave(f), false, "Save stays off until the date order is chosen");
  assert.equal(saveBody(f), null);
  f.dateOrder = "dmy";
  assert.equal(canSave(f), true);
  assert.equal(saveBody(f).date_order, "dmy");
});

await check("every question named makes its field start empty and gate Save", () => {
  const base = JSON.parse(JSON.stringify(SETTLED));
  const cases = {
    decimal: (f) => { f.decimal = ","; },
    sign: (f) => { f.mode = "one"; f.sign1 = "positive_out"; },
    date_column: (f) => { f.dateColumn = 0; },
    description_column: (f) => { f.descriptionColumn = 1; },
    amount_column: (f) => { f.amountColumn = 2; },
  };
  for (const [q, choose] of Object.entries(cases)) {
    const p = JSON.parse(JSON.stringify(base));
    p.questions = [q];
    const f = formFor(p, "x.csv");
    assert.equal(canSave(f), false, q);
    choose(f);
    if (q === "sign") f.mode = "one";
    assert.equal(canSave(f), true, `${q} answered`);
  }
  // The sign question: neither a mode nor a rule is pre-picked.
  const p = JSON.parse(JSON.stringify(base));
  p.questions = ["sign"];
  const f = formFor(p, "x.csv");
  assert.equal(f.mode, null);
  assert.equal(f.sign1, null);
});

await check("no usable header: no guess at all, the owner picks the header row and every column", () => {
  const p = {
    ok: true, known: false, fingerprint: "ab", header_row: null, header: [], header_index: [],
    hidden_columns: 0, hidden_note: "", preview: [["Statement", "", ""], ["Date", "Details", "Amount"], ["2026-03-01", "TESCO", "-4.00"]],
    guess: null, questions: ["header_row", "date_order", "decimal", "sign", "date_column", "description_column", "amount_column"],
    warnings: [], sentences: {}, sign_sentences: CASES.sign_sentences,
  };
  const f = formFor(p, "x.csv");
  assert.equal(f.askHeaderRow, true);
  for (const k of ["headerRow", "dateColumn", "descriptionColumn", "mode", "sign1", "amountColumn", "dateOrder", "decimal"]) {
    assert.equal(f[k], null, k);
  }
  assert.equal(canSave(f), false);
  assert.deepEqual(columnOptions(p).map((o) => o.value), [0, 1, 2]);
  Object.assign(f, { headerRow: 1, dateColumn: 0, descriptionColumn: 1, mode: "one", amountColumn: 2,
    sign1: "negative_out", dateOrder: "ymd", decimal: "." });
  assert.equal(canSave(f), true);
  const body = saveBody(f);
  assert.equal(body.header_row, 1, "the chosen header row is sent");
  assert.deepEqual(body.columns, { date: 0, description: 1, amount: 2 });
});

await check("dropdown values are ORIGINAL column numbers, never positions in the shown header", () => {
  const p = JSON.parse(JSON.stringify(SETTLED));
  p.header = ["Date", "Description", "Amount"];
  p.header_index = [0, 2, 4];
  p.hidden_columns = 2;
  const opts = columnOptions(p);
  assert.deepEqual(opts.map((o) => o.value), [0, 2, 4]);
  assert.deepEqual(opts.map((o) => o.label), ["1. Date", "3. Description", "5. Amount"]);
});

await check("the three ways amounts are written send the contract's columns and sign", () => {
  const base = { file: "x.csv", fingerprint: "", headerRow: 0, askHeaderRow: false, dateColumn: 0,
    descriptionColumn: 1, dateOrder: "dmy", ownOrder: false, decimal: ".", currency: " GBP ", label: " Bank " };
  const one = { ...base, mode: "one", sign1: "positive_out", amountColumn: 2 };
  assert.equal(saveBody(one).sign, "positive_out");
  assert.deepEqual(saveBody(one).columns, { date: 0, description: 1, amount: 2 });
  assert.equal(saveBody(one).currency, "GBP");
  assert.equal(saveBody(one).label, "Bank");
  const dc = { ...base, mode: "debit_credit", debitColumn: 2, creditColumn: 3 };
  assert.equal(saveBody(dc).sign, "debit_credit");
  assert.deepEqual(saveBody(dc).columns, { date: 0, description: 1, debit: 2, credit: 3 });
  assert.equal(saveBody({ ...dc, creditColumn: null }), null);
  const dr = { ...base, mode: "drcr", amountColumn: 2, drcrColumn: 3 };
  assert.equal(saveBody(dr).sign, "drcr");
  assert.deepEqual(saveBody(dr).columns, { date: 0, description: 1, amount: 2, drcr: 3 });
  assert.equal(saveBody({ ...one, sign1: null }), null, "a single amount column needs its sign rule");
  assert.equal(saveBody({ ...one, currency: "TOOLONG" }), null);
  assert.equal(saveBody({ ...one, label: "x".repeat(61) }), null);
  assert.equal(modeOfSign("drcr"), "drcr");
  assert.equal(modeOfSign("negative_out"), "one");
  assert.equal(modeOfSign(null), null);
  assert.equal(signOf("one", "x"), null);
  for (const [sign, sentence] of Object.entries(CASES.sign_sentences)) {
    assert.equal(SETTLED.sign_sentences[sign], sentence, sign);
  }
});

await check("the saved line is the contract's", () => {
  assert.equal(savedLine({ rows_read: 7, rows_skipped: 1 }), "Saved. 7 rows read, 1 left out.");
});

/* ── the categories editor ────────────────────────────────────────────── */

await check("category words: trimmed, lower-case, no repeats; order moves; suggestions merge", () => {
  assert.deepEqual(parseWords(" Tesco, ALDI\nlidl ,, tesco "), ["tesco", "aldi", "lidl"]);
  assert.equal(wordsText(["a", "b"]), "a, b");
  assert.deepEqual(moved(["a", "b", "c"], 0, 1), ["b", "a", "c"]);
  assert.deepEqual(moved(["a", "b", "c"], 0, -1), ["a", "b", "c"]);
  assert.deepEqual(moved(["a", "b", "c"], 2, 3), ["a", "b", "c"]);
  const list = CASES.view_pc_nothing_saved.categories.map((c) => ({ category: c.category, words: c.words.slice() }));
  const merged = mergeSuggestions(list, [
    { name: "Corner Kiosk", category: "Food and groceries" },
    { name: "tesco", category: "Food and groceries" },
    { name: "Nowhere", category: "No such category" },
  ]);
  const food = merged.find((c) => c.category === "Food and groceries");
  assert.ok(food.words.includes("corner kiosk"));
  assert.equal(food.words.filter((w) => w === "tesco").length, 1);
  assert.equal(merged.length, list.length, "no category is invented");
  assert.ok(!list.find((c) => c.category === "Food and groceries").words.includes("corner kiosk"), "the original is untouched");
  assert.deepEqual(categoriesBody(merged)[0], { category: merged[0].category, words: merged[0].words });
});

await check("the real views carry what the box draws", () => {
  for (const name of ["view_pc_nothing_saved", "view_pc_file_waiting", "view_pc_one_layout"]) {
    const v = CASES[name];
    assert.equal(v.can_edit, true, name);
    assert.ok(Array.isArray(v.categories) && v.categories.length, name);
  }
  assert.equal(CASES.view_phone_nothing_saved.can_edit, false);
  assert.ok(CASES.view_pc_file_waiting.waiting.some((w) => w.path), "the PC's waiting file names its path");
  assert.ok(CASES.view_phone_file_waiting.waiting.every((w) => !w.path), "the phone's does not");
});

/* ── CONTROL: the wiring ──────────────────────────────────────────────── */

const RS = read("src-tauri/src/spending.rs");
const BUILD = read("src-tauri/build.rs");
const LIB = read("src-tauri/src/lib.rs");
const TOML = read("src-tauri/permissions/surfaces.toml");
const QB = JSON.parse(read("src-tauri/capabilities/quickbar.json"));
const ST = JSON.parse(read("src-tauri/capabilities/settings.json"));
const HTML = read("src/settings.html");
const INDEX = read("src/index.html");
const MAIN = read("src/main.js");
const TABLE_CMDS = ["chat_table"];
const SETTINGS_CMDS = ["get_spending", "spending_profile_read", "spending_profile_save",
  "spending_profile_delete", "spending_categories_save", "spending_categories_reset", "spending_suggest"];

await check("CONTROL: the commands are registered, and each surface holds only its own", () => {
  for (const c of [...TABLE_CMDS, ...SETTINGS_CMDS]) {
    assert.ok(BUILD.includes(`"${c}"`), `build.rs: ${c}`);
    assert.ok(LIB.includes(`spending::${c},`), `lib.rs: ${c}`);
    assert.ok(RS.includes(`pub async fn ${c}(`), `spending.rs: ${c}`);
    assert.ok(TOML.includes(`"allow-${c.replaceAll("_", "-")}"`), `surfaces.toml: ${c}`);
  }
  const set = (id) => TOML.slice(TOML.indexOf(`identifier = "${id}"`)).split("[[set]]")[0];
  for (const c of TABLE_CMDS) assert.ok(set("spending-table").includes(`allow-${c.replaceAll("_", "-")}`));
  for (const c of SETTINGS_CMDS) {
    assert.ok(set("spending-settings").includes(`allow-${c.replaceAll("_", "-")}`), c);
    assert.ok(!set("spending-table").includes(`allow-${c.replaceAll("_", "-")}`), `${c} must not be the bar's`);
  }
  assert.ok(QB.permissions.includes("spending-table"));
  assert.ok(!QB.permissions.includes("spending-settings"));
  assert.ok(ST.permissions.includes("spending-settings"));
  assert.ok(!ST.permissions.includes("spending-table"));
  for (const other of ["brain", "widget", "hud", "floating", "faces", "live-badge", "watch-badge", "onboarding"]) {
    const cap = JSON.parse(read(`src-tauri/capabilities/${other}.json`));
    assert.ok(!cap.permissions.some((p) => p.startsWith("spending")), `${other} has a spending permission`);
  }
});

await check("CONTROL: Rust asks the PC nothing while hidden, checks the id, holds writes, logs nothing", () => {
  const fn = RS.slice(RS.indexOf("pub async fn chat_table("));
  const body = fn.slice(0, fn.indexOf("\n}\n"));
  assert.ok(body.indexOf("valid_table_id(&id)") >= 0 && body.indexOf("valid_table_id(&id)") < body.indexOf(".get(format!"));
  assert.ok(body.indexOf("table_hidden(&app)") < body.indexOf(".get(format!"),
    "hidden must be checked BEFORE the PC is asked");
  assert.match(RS, /private_hidden\(app\) \|\| crate::lock::app_locked\(app\)/);
  const post = RS.slice(RS.indexOf("async fn post("));
  assert.ok(post.slice(0, post.indexOf("\n}\n")).includes("if stale(app)"), "every write is held on a stale link");
  for (const w of ["spending_profile_save", "spending_profile_delete", "spending_categories_save",
    "spending_categories_reset", "spending_suggest"]) {
    const f = RS.slice(RS.indexOf(`pub async fn ${w}(`));
    assert.ok(f.slice(0, f.indexOf("\n}\n")).includes("post("), `${w} goes through the held post`);
  }
  const code = RS.slice(0, RS.indexOf("#[cfg(test)]"));
  assert.ok(!/println!|eprintln!|log::|tracing::|dbg!/.test(code), "nothing is logged");
  assert.ok(!/token/i.test(code.replace(/\/\/[^\n]*/g, "").replace(/never logged[^\n]*/g, "")) ||
    !/format!\([^)]*token/i.test(code), "the token is never formatted into a string");
  // Literal routes, so tools/check_parity.py sees them.
  for (const r of ["/api/chat/table", "/api/spending", "/api/spending/profile",
    "/api/spending/profile/delete", "/api/spending/categories", "/api/spending/suggest"]) {
    assert.ok(RS.includes(`"${r}"`), r);
  }
});

await check("CONTROL: the Settings card has a stable id, a jump link under Rare, and the bar a place for the table", () => {
  assert.match(HTML, /<section class="card" id="spending">/);
  const nav = HTML.slice(HTML.indexOf('id="settings-jump"'), HTML.indexOf("</nav>"));
  const rare = nav.slice(nav.indexOf(">Rare<"), nav.indexOf("What Jarvis does"));
  assert.ok(rare.includes('<a href="#spending">Spending</a>'), "the jump link is in the Rare group");
  assert.match(HTML, /src="spending-settings\.js"/);
  assert.match(INDEX, /<section class="spending-host" id="spending-table" hidden><\/section>/);
  assert.ok(MAIN.includes("tableIdFromLine(line)") && MAIN.includes("tableIdFromBody(chunk)"));
  assert.ok(MAIN.includes('spendingView.hide()'), "private-hidden takes the table off the screen");
  assert.ok(MAIN.includes("spendingView.clear()"), "a new question and a closed card drop the table");
  // The widget and the HUD page draw no chat answer text and so no table.
  for (const f of ["src/widget.js", "src/widget.html", "src/floating.js"]) {
    assert.ok(!/jarvis-table|chat_table|spending-table|spending\.js/i.test(read(f)), `${f} must not draw the table`);
  }
});

/* ── with Playwright: the real Jarvis bar and Settings page ───────────── */

let K = null;
try {
  await import("playwright");
  K = await import("./uikit.mjs");
} catch {
  console.log("skip  browser checks (Playwright is not installed here)");
}

if (K) {
  const { base, close } = await K.serve();
  const browser = await K.launch();
  const sentence = (text) => `data: {"choices":[{"delta":{"content":${JSON.stringify(text)}}}]}`;
  const NOTE = "Food and groceries came to 70.40.";

  async function ask(spending, lines, { second = null } = {}) {
    const replies = [lines];
    if (second) replies.push(second);
    const page = await K.open(browser, base, "index.html", { chatReplies: replies, spending },
      { width: 750, height: 700 });
    await page.locator("#prompt").fill("how much on food?");
    await page.locator("#prompt").press("Enter");
    await page.waitForTimeout(500);
    return page;
  }
  const bar = (page) => page.evaluate(() => ({
    hidden: document.getElementById("spending-table").hidden,
    text: document.getElementById("spending-table").textContent,
    tables: document.querySelectorAll("#spending-table table").length,
    imgs: document.querySelectorAll("#spending-table img, #spending-table a, #spending-table script").length,
    answer: document.getElementById("answer").textContent.trim(),
    calls: (window.__spending || { calls: [] }).calls.map((c) => c.cmd + ":" + JSON.stringify(c.args)),
  }));

  await check("browser: the bar draws the table under the sentence and asks once", async () => {
    const page = await ask({ tables: { [ID]: TABLES.by_category } },
      [`: jarvis-table ${ID}`, sentence(NOTE), "data: [DONE]"]);
    const got = await bar(page);
    assert.equal(got.answer, NOTE);
    assert.equal(got.hidden, false);
    assert.equal(got.tables, 1);
    assert.deepEqual(got.calls, [`chat_table:${JSON.stringify({ id: ID })}`]);
    for (const cell of TABLES.by_category.sections[0].rows.flatMap((r) => r.cells)) {
      assert.ok(got.text.includes(cell), cell);
    }
    // In memory only: nothing of it in any storage.
    const stored = await page.evaluate(() => JSON.stringify([{ ...localStorage }, { ...sessionStorage }]));
    assert.ok(!stored.includes("Food and groceries") && !stored.includes(ID), stored);
    await page.close();
  });

  await check("browser: a new question drops the old table", async () => {
    const page = await ask({ tables: { [ID]: TABLES.by_category } },
      [`: jarvis-table ${ID}`, sentence(NOTE), "data: [DONE]"],
      { second: [sentence("Hello."), "data: [DONE]"] });
    await page.waitForFunction(() => document.querySelectorAll("#spending-table table").length === 1);
    await page.locator("#prompt").fill("and hello?");
    await page.locator("#prompt").press("Enter");
    await page.waitForTimeout(500);
    const got = await bar(page);
    assert.equal(got.tables, 0);
    assert.equal(got.hidden, true);
    await page.close();
  });

  await check("browser: hidden draws the words and the table is drawn from nowhere", async () => {
    const page = await ask({ hidden: true, tables: { [ID]: TABLES.by_category } },
      [`: jarvis-table ${ID}`, sentence(NOTE), "data: [DONE]"]);
    const got = await bar(page);
    assert.equal(got.text, "Spending table hidden");
    assert.equal(got.tables, 0);
    assert.equal(got.answer, NOTE, "the checked sentence still shows");
    await page.close();
  });

  await check("browser: 'Hide memory lists' arriving later takes a drawn table away at once", async () => {
    const page = await ask({ tables: { [ID]: TABLES.by_category } },
      [`: jarvis-table ${ID}`, sentence(NOTE), "data: [DONE]"]);
    assert.equal((await bar(page)).tables, 1);
    await page.evaluate(() => window.__emit("private-hidden", null));
    await page.waitForTimeout(100);
    const got = await bar(page);
    assert.equal(got.tables, 0);
    assert.equal(got.text, "Spending table hidden");
    await page.close();
  });

  await check("browser: gone shows the PC's sentence", async () => {
    const page = await ask({ tables: {} }, [`: jarvis-table ${ID}`, sentence(NOTE), "data: [DONE]"]);
    const got = await bar(page);
    assert.equal(got.text, CASES.words.TABLE_GONE);
    await page.close();
  });

  await check("browser: a hostile cell is text, not markup or a link", async () => {
    const raw = JSON.parse(JSON.stringify(TABLES.by_category));
    raw.sections[0].rows[0].cells[0] = "<img src=x onerror=\"window.__pwned=1\">";
    raw.sections[0].rows[1].cells[0] = "=HYPERLINK(\"http://evil.example\",\"x\")";
    const page = await ask({ tables: { [ID]: raw } }, [`: jarvis-table ${ID}`, sentence(NOTE), "data: [DONE]"]);
    const got = await bar(page);
    assert.equal(got.imgs, 0);
    assert.ok(got.text.includes("<img src=x onerror=") && got.text.includes("=HYPERLINK("));
    assert.equal(await page.evaluate(() => window.__pwned || 0), 0);
    await page.close();
  });

  await check("browser: a real table with a scroller and captions, reachable by keyboard", async () => {
    const page = await ask({ tables: { [ID]: TABLES.by_category_and_month } },
      [`: jarvis-table ${ID}`, sentence(NOTE), "data: [DONE]"]);
    const got = await page.evaluate(() => {
      const sc = document.querySelector("#spending-table .st-scroll");
      sc.focus();
      return {
        focused: document.activeElement === sc,
        caption: document.querySelector("#spending-table caption").textContent,
        colHeads: document.querySelectorAll("#spending-table thead th[scope=col]").length,
        rowHeads: document.querySelectorAll("#spending-table tbody th[scope=row]").length,
        rowLabel: document.querySelector("#spending-table tbody tr").getAttribute("aria-label"),
      };
    });
    assert.equal(got.focused, true);
    assert.equal(got.caption, TABLES.by_category_and_month.title);
    assert.equal(got.colHeads, TABLES.by_category_and_month.columns.length);
    assert.ok(got.rowHeads >= 1);
    assert.ok(got.rowLabel.includes(", "));
    await page.close();
  });

  /* Settings */
  const openSettings = (spending, extra = {}) =>
    K.open(browser, base, "settings.html", { spending, ...extra }, { width: 900, height: 900 });
  const pcView = (over = {}) => ({ ...JSON.parse(JSON.stringify(CASES.view_pc_file_waiting)), ...over });

  await check("browser: Settings, Spending shows the layouts, the waiting file and the categories", async () => {
    const page = await openSettings({ view: pcView() });
    await page.waitForFunction(() => !document.getElementById("spd-body").hidden);
    const got = await page.evaluate(() => ({
      detail: document.getElementById("spd-detail").textContent,
      waiting: document.querySelectorAll("#spd-waiting li").length,
      cats: document.querySelectorAll("#spd-cats li").length,
      empty: document.getElementById("spd-layouts-empty").textContent,
      starter: document.getElementById("spd-cat-note").textContent,
      jump: !!document.querySelector('#settings-jump a[href="#spending"]'),
    }));
    assert.equal(got.detail, CASES.words.DETAIL);
    assert.equal(got.waiting, CASES.view_pc_file_waiting.waiting.length);
    assert.equal(got.cats, CASES.view_pc_file_waiting.categories.length);
    assert.equal(got.empty, CASES.words.EMPTY_PROFILES);
    assert.equal(got.jump, true);
    await page.close();
  });

  await check("browser: a request from another device sees the PC-only line and no edit control", async () => {
    const page = await openSettings({ view: JSON.parse(JSON.stringify(CASES.view_phone_file_waiting)) });
    await page.waitForFunction(() => !document.getElementById("spd-body").hidden);
    const got = await page.evaluate(() => ({
      pcOnly: document.getElementById("spd-pc-only").textContent,
      shown: !document.getElementById("spd-pc-only").hidden,
      save: document.getElementById("spd-cat-save").disabled,
      add: document.getElementById("spd-cat-add").disabled,
    }));
    assert.equal(got.shown, true);
    assert.equal(got.pcOnly, CASES.words.PC_ONLY);
    assert.equal(got.save, true);
    assert.equal(got.add, true);
    await page.close();
  });

  await check("browser: Check these columns keeps Save off until the date order is chosen, then saves", async () => {
    const waiting = pcView();
    waiting.waiting = [{ name: "h_ambiguous.csv", path: "C:\\bank\\h.csv" }];
    const page = await openSettings({ view: waiting, proposals: { "C:\\bank\\h.csv": UNSETTLED } });
    await page.waitForFunction(() => document.querySelectorAll("#spd-waiting button").length === 1);
    await page.locator("#spd-waiting button").click();
    await page.waitForFunction(() => !document.getElementById("spd-check").hidden);
    assert.equal(await page.locator("#spd-save").isDisabled(), true);
    assert.equal(await page.locator("#spd-check-title").textContent(), "Check these columns");
    await page.locator("input[name=spd-order][value=dmy]").check();
    await page.waitForFunction(() => !document.getElementById("spd-save").disabled);
    await page.locator("#spd-save").click();
    await page.waitForFunction(() => window.__spending.saved.length === 1);
    const sent = await page.evaluate(() => window.__spending.saved[0]);
    assert.equal(sent.file, "C:\\bank\\h.csv");
    assert.equal(sent.date_order, "dmy");
    assert.equal(sent.sign, "negative_out");
    await page.waitForFunction(() => document.getElementById("spd-check").hidden);
    await page.close();
  });

  await check("browser: the categories editor saves the whole list; reset asks first", async () => {
    const page = await openSettings({ view: pcView() });
    await page.waitForFunction(() => document.querySelectorAll("#spd-cats li").length > 2);
    await page.locator("#spd-cat-words-0").fill("Tesco, ALDI, corner kiosk");
    await page.locator("#spd-cat-words-0").dispatchEvent("change");
    await page.locator("#spd-cat-save").click();
    await page.waitForFunction(() => window.__spending.categoriesSaved.length === 1);
    const saved = await page.evaluate(() => window.__spending.categoriesSaved[0]);
    assert.deepEqual(saved[0].words, ["tesco", "aldi", "corner kiosk"]);
    assert.equal(saved.length, CASES.view_pc_file_waiting.categories.length);
    await page.locator("#spd-cat-reset").click();
    assert.equal(await page.locator("#spd-reset-sure").isHidden(), false);
    assert.equal(await page.evaluate(() => window.__spending.resets), 0, "nothing is reset before the yes");
    await page.locator("#spd-reset-no").click();
    assert.equal(await page.evaluate(() => window.__spending.resets), 0);
    await page.locator("#spd-cat-reset").click();
    await page.locator("#spd-reset-yes").click();
    await page.waitForFunction(() => window.__spending.resets === 1);
    await page.close();
  });

  await check("browser: a stale link holds every write", async () => {
    const page = await openSettings({ view: pcView() }, { link: { connected: false, stale: true } });
    await page.waitForFunction(() => document.querySelectorAll("#spd-cats li").length > 2);
    await page.locator("#spd-cat-save").click();
    await page.waitForTimeout(200);
    const got = await page.evaluate(() => ({
      writes: window.__spending.calls.filter((c) => c.cmd === "spending_categories_save").length,
      said: document.getElementById("spd-cat-status").textContent,
    }));
    assert.equal(got.writes, 0);
    assert.match(got.said, /catching up/);
    await page.close();
  });

  await browser.close();
  await close();
}

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("\nall spending checks passed");
