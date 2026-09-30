/**
 * Settings -> "Spending" (the owner's decision of 2026-09-30, queue item 2;
 * docs/FINANCE-DESIGN.md part A "Slice contract (frozen)" section 5;
 * JARVIS-API.md section 100.4).
 *
 * The PC-only box: the columns of a new bank file are checked here once
 * ("Check these columns"), saved layouts can be forgotten, the category words
 * are edited, and the local model can suggest categories for shop names no
 * rule catches. The words come from spending.js (`WORDS`, `BOX`) or from the
 * PC's own answer; the logic (`formFor`, `canSave`, `saveBody`, the category
 * helpers) is in spending.js and is tested in tests/spending.mjs.
 *
 * Eight Rust commands (src-tauri/src/spending.rs), Settings only. No approval
 * card: the owner's own tap on their own file. Every write is PC-only on the
 * backend (403 `pc_only`; its message is shown as it is) and held on a stale
 * link. A bank file's rows never come here: the PC sends only a preview with
 * account and card numbers already hidden. Everything is drawn with
 * textContent - a file's header and rows are the bank's own text.
 *
 * This card (`#spending`) is a member of the Finance menu group
 * (docs/MENU-VISIBILITY-DESIGN.md): its id is the stable menu id.
 *
 * @module spending-settings
 */

import { announce, currentLink, linkWords, onLink, onQueue } from "./jarvis-link.js";
import {
  BOX,
  canPress,
  canSave,
  categoriesBody,
  columnOptions,
  DECIMALS,
  fileForAgain,
  formFor,
  MAX_CATEGORIES,
  MAX_WORDS,
  mergeSuggestions,
  MODES,
  moved,
  ORDER_CHOICES,
  ORDER_OWN,
  parseWords,
  pickerOptions,
  previewBody,
  previewState,
  saveBody,
  savedLine,
  SIGN_CHOICES,
  signOf,
  WORDS,
  wordsText,
} from "./spending.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

const el = {
  section: $("spending"),
  title: $("spd-title"),
  detail: $("spd-detail"),
  state: $("spd-state"),
  body: $("spd-body"),
  pcOnly: $("spd-pc-only"),
  waiting: $("spd-waiting"),
  waitingTitle: $("spd-waiting-title"),
  layouts: $("spd-layouts"),
  layoutsEmpty: $("spd-layouts-empty"),
  file: $("spd-file"),
  fileNote: $("spd-file-note"),
  counts: $("spd-counts"),
  warnings: $("spd-warnings"),
  acceptWrap: $("spd-accept-wrap"),
  accept: $("spd-accept"),
  acceptText: $("spd-accept-text"),
  check: $("spd-check"),
  checkTitle: $("spd-check-title"),
  checkHidden: $("spd-check-hidden"),
  previewWrap: $("spd-preview-wrap"),
  form: $("spd-form"),
  signSentence: $("spd-sign-sentence"),
  save: $("spd-save"),
  cancel: $("spd-cancel"),
  checkStatus: $("spd-check-status"),
  catTitle: $("spd-cat-title"),
  catNote: $("spd-cat-note"),
  catOrder: $("spd-cat-order"),
  cats: $("spd-cats"),
  catAdd: $("spd-cat-add"),
  catSave: $("spd-cat-save"),
  catReset: $("spd-cat-reset"),
  resetSure: $("spd-reset-sure"),
  resetLine: $("spd-reset-line"),
  resetYes: $("spd-reset-yes"),
  resetNo: $("spd-reset-no"),
  catStatus: $("spd-cat-status"),
  suggestTitle: $("spd-suggest-title"),
  suggestNote: $("spd-suggest-note"),
  suggest: $("spd-suggest"),
  suggestions: $("spd-suggestions"),
  suggestAdd: $("spd-suggest-add"),
  suggestStatus: $("spd-suggest-status"),
};

/** The PC's last `GET /api/spending`. */
let view = null;
/** The category list being edited (names and words). Held here only until
 *  saved or the page closes; it is the owner's own list, not bank data. */
let cats = [];
/** The proposal being checked and the form's state. */
let proposal = null;
let form = null;
/** The suggestions read from the PC: `{name, category, ticked}`. */
let found = [];
/** The bank file picked in the picker (a path the PC listed itself). */
let pickedFile = "";
/** The PC's last answer to "what would these choices count?" and whether the
 *  owner ticked "save it anyway". Counts only; never a row. */
let previewNow = { line: "", warnings: [], problems: [] };
let previewSeq = 0;
let previewTimer = null;
/** The layout whose "Forget this layout" is waiting for "are you sure?". */
let forgetAsk = "";
let busy = false;

function node(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

function live() {
  return linkWords(currentLink()).canAct;
}

const STALE = "The connection to Jarvis is catching up, so nothing can be sent until it does.";

/** An error in words, never a bridge error or JSON. */
function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 400) {
    return "Could not ask Jarvis. Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

function say(target, text, tone) {
  if (!target) return;
  target.textContent = text;
  if (tone) target.dataset.tone = tone;
  else delete target.dataset.tone;
}

function invoke(command, args) {
  return TAURI.core.invoke(command, args);
}

/* ── The lists ───────────────────────────────────────────────────────── */

function cleanFile() {
  return pickedFile;
}

/** The Bank file picker: the files the PC found in the folders Jarvis may
 *  look in (paths never typed by hand). */
function paintPicker() {
  const options = pickerOptions(view);
  const none = node("option", "", BOX.chooseFile);
  none.value = "";
  el.file.replaceChildren(none, ...options.map((o) => {
    const opt = node("option", "", o.label);
    opt.value = o.value;
    return opt;
  }));
  if (!options.some((o) => o.value === pickedFile)) pickedFile = "";
  el.file.value = pickedFile;
}

function paint() {
  if (!el.section || !view) return;
  if (view.available === false) {
    el.state.textContent = view.why;
    el.state.hidden = false;
    el.body.hidden = true;
    return;
  }
  el.state.hidden = true;
  el.body.hidden = false;
  el.title.textContent = view.title || WORDS.TITLE;
  el.detail.textContent = view.detail || WORDS.DETAIL;
  const canEdit = view.can_edit === true;
  el.pcOnly.hidden = canEdit;
  el.pcOnly.textContent = canEdit ? "" : view.pc_only || WORDS.PC_ONLY;

  const waiting = Array.isArray(view.waiting) ? view.waiting : [];
  el.waitingTitle.hidden = !waiting.length;
  el.waiting.replaceChildren(...waiting.map((w) => {
    const li = node("li", "sc-gpu");
    li.append(node("span", "sc-gpu-name", w.name));
    li.append(node("span", "sc-gpu-role", view.needs_setup || WORDS.NEEDS_SETUP_ON_PC));
    if (canEdit && w.path) {
      const b = node("button", "btn small", BOX.checkColumns);
      b.type = "button";
      b.disabled = busy;
      b.addEventListener("click", () => openCheck(w.path));
      li.append(b);
    }
    return li;
  }));

  const profiles = Array.isArray(view.profiles) ? view.profiles : [];
  el.layouts.replaceChildren(...profiles.map((p) => {
    const li = node("li", "sc-gpu");
    li.append(node("span", "sc-gpu-name", p.label || p.id));
    li.append(node("span", "sc-gpu-role", (p.columns || []).join(", ")));
    if (p.sign_sentence) li.append(node("span", "sc-gpu-role", p.sign_sentence));
    if (p.saved) li.append(node("span", "sc-gpu-role", p.saved));
    if (canEdit && forgetAsk === p.id) {
      // The only thing that deletes a layout asks first.
      li.append(node("span", "sc-gpu-role", BOX.forgetSure));
      const yes = node("button", "btn small", BOX.forgetYes);
      yes.type = "button";
      yes.disabled = busy;
      yes.addEventListener("click", () => forgetLayout(p.id));
      const no = node("button", "btn small", BOX.forgetNo);
      no.type = "button";
      no.addEventListener("click", () => { forgetAsk = ""; paint(); });
      li.append(yes, no);
    } else if (canEdit) {
      // "Check the columns again" uses THIS row's file (a file found in the
      // folders whose header has this layout), never whatever is picked, and
      // never deletes the layout: the same box opens with the saved choices.
      const file = fileForAgain(view, p.id, cleanFile());
      const again = node("button", "btn small", BOX.again);
      again.type = "button";
      again.disabled = busy || !file;
      again.addEventListener("click", () => openCheck(file, { again: true }));
      const forget = node("button", "btn small", BOX.forget);
      forget.type = "button";
      forget.disabled = busy;
      forget.addEventListener("click", () => { forgetAsk = p.id; paint(); });
      li.append(again, forget);
      if (!file) li.append(node("span", "sc-gpu-role", BOX.noFileForLayout));
    }
    return li;
  }));
  el.layoutsEmpty.hidden = profiles.length > 0;
  el.layoutsEmpty.textContent = view.empty_profiles || WORDS.EMPTY_PROFILES;

  el.file.disabled = !canEdit;
  el.fileNote.hidden = !canEdit;
  el.fileNote.textContent =
    "Used by \"" + BOX.suggest + "\": a bank file in a folder Jarvis may look in.";
  paintPicker();

  el.catTitle.textContent = BOX.categories;
  el.catNote.hidden = !view.categories_are_starter;
  el.catNote.textContent = view.categories_are_starter ? view.starter_note || WORDS.STARTER_NOTE : "";
  el.catOrder.textContent = `${BOX.firstMatch} ${BOX.wholeWord}`;
  for (const b of [el.catAdd, el.catSave, el.catReset]) b.disabled = busy || !canEdit;
  el.catAdd.disabled = el.catAdd.disabled || cats.length >= MAX_CATEGORIES;
  el.catSave.textContent = BOX.saveCategories;
  el.catReset.textContent = BOX.reset;
  paintCats(canEdit);

  el.suggestTitle.textContent = BOX.suggest;
  el.suggestNote.textContent = "Jarvis's local model proposes a category for shop names no rule catches. Nothing is saved until you tap \"" + BOX.addRules + "\".";
  el.suggest.textContent = BOX.suggest;
  el.suggest.disabled = busy || !canEdit || !cleanFile();
  paintSuggestions();
}

function paintCats(canEdit) {
  el.cats.replaceChildren(...cats.map((c, i) => {
    const li = node("li", "sc-gpu");
    const nameId = `spd-cat-name-${i}`;
    const wordsId = `spd-cat-words-${i}`;
    const nameLabel = node("label", "sc-gpu-role", "Category name");
    nameLabel.htmlFor = nameId;
    const name = node("input");
    name.id = nameId;
    name.type = "text";
    name.maxLength = 60;
    name.value = c.category;
    name.disabled = !canEdit;
    name.autocomplete = "off";
    name.addEventListener("input", () => { c.category = name.value; });
    const wordsLabel = node("label", "sc-gpu-role", "Words");
    wordsLabel.htmlFor = wordsId;
    const words = node("textarea");
    words.id = wordsId;
    words.rows = 2;
    words.spellcheck = false;
    words.value = wordsText(c.words);
    words.disabled = !canEdit;
    words.addEventListener("change", () => {
      c.words = parseWords(words.value).slice(0, MAX_WORDS);
      words.value = wordsText(c.words);
    });
    const row = node("div", "row");
    const mk = (text, fn, off) => {
      const b = node("button", "btn small", text);
      b.type = "button";
      b.disabled = !canEdit || busy || off;
      b.addEventListener("click", fn);
      return b;
    };
    row.append(
      mk("Move up", () => { cats = moved(cats, i, i - 1); paint(); focusCat(i - 1); }, i === 0),
      mk("Move down", () => { cats = moved(cats, i, i + 1); paint(); focusCat(i + 1); }, i === cats.length - 1),
      mk("Remove", () => { cats.splice(i, 1); paint(); }, false),
    );
    li.append(nameLabel, name, wordsLabel, words, row);
    return li;
  }));
}

function focusCat(i) {
  const n = document.getElementById(`spd-cat-name-${i}`);
  if (n) n.focus();
}

/* ── Load ────────────────────────────────────────────────────────────── */

async function load({ keepCats = false } = {}) {
  if (!el.section) return;
  if (!IS_TAURI) {
    el.state.textContent = "Open this in Jarvis Desktop to set up spending.";
    return;
  }
  try {
    view = await invoke("get_spending");
  } catch (error) {
    el.state.textContent = problemWords(error);
    el.state.hidden = false;
    return;
  }
  if (!keepCats || !cats.length) {
    cats = (Array.isArray(view.categories) ? view.categories : []).map((c) => ({
      category: String(c.category || ""),
      words: Array.isArray(c.words) ? c.words.map(String) : [],
    }));
  }
  paint();
}

async function act(command, args, target, working) {
  if (busy) return null;
  if (!live()) {
    say(target, STALE, "bad");
    return null;
  }
  busy = true;
  say(target, working);
  paint();
  try {
    return await invoke(command, args);
  } catch (error) {
    say(target, problemWords(error), "bad");
    return null;
  } finally {
    busy = false;
  }
}

/* ── Check these columns ─────────────────────────────────────────────── */

function closeCheck() {
  proposal = null;
  form = null;
  previewSeq += 1;
  if (previewTimer) clearTimeout(previewTimer);
  previewNow = { line: "", warnings: [], problems: [] };
  el.check.hidden = true;
  el.form.replaceChildren();
  el.previewWrap.replaceChildren();
  el.counts.textContent = "";
  el.warnings.hidden = true;
  el.acceptWrap.hidden = true;
  el.accept.checked = false;
  say(el.checkStatus, "");
}

function previewTable(p) {
  const rows = Array.isArray(p.preview) ? p.preview : [];
  if (!rows.length) return null;
  const t = node("table", "st-table spd-preview");
  t.append(node("caption", "st-caption", "The first rows of the file"));
  const header = Array.isArray(p.header) ? p.header : [];
  if (header.length) {
    const tr = node("tr");
    header.forEach((h) => {
      const th = node("th", "st-cell st-left", h);
      th.scope = "col";
      tr.append(th);
    });
    const head = node("thead");
    head.append(tr);
    t.append(head);
  }
  const body = node("tbody");
  rows.forEach((r) => {
    const tr = node("tr");
    (Array.isArray(r) ? r : []).forEach((cell) => tr.append(node("td", "st-cell st-left", String(cell))));
    body.append(tr);
  });
  t.append(body);
  return t;
}

/** A labelled dropdown whose first option is "Choose…" (no choice yet). */
function selectField(id, label, options, value, onPick) {
  const wrap = node("div", "row");
  const l = node("label", "", label);
  l.htmlFor = id;
  const sel = node("select");
  sel.id = id;
  const none = node("option", "", "Choose…");
  none.value = "";
  sel.append(none);
  options.forEach((o) => {
    const opt = node("option", "", o.label);
    opt.value = String(o.value);
    sel.append(opt);
  });
  sel.value = value == null ? "" : String(value);
  sel.addEventListener("change", () => {
    onPick(sel.value === "" ? null : sel.value);
    refreshForm();
  });
  wrap.append(l, sel);
  return wrap;
}

function radioGroup(name, legend, choices, value, onPick, rerender) {
  const fs = node("fieldset", "spd-radios");
  fs.append(node("legend", "", legend));
  Object.entries(choices).forEach(([key, text]) => {
    const l = node("label", "toggle");
    const r = node("input");
    r.type = "radio";
    r.name = name;
    r.value = key;
    r.checked = value === key;
    r.addEventListener("change", () => {
      onPick(key);
      if (rerender) renderForm();
      else refreshForm();
    });
    l.append(r, node("span", "", text));
    fs.append(l);
  });
  return fs;
}

function textField(id, label, max, value, onInput) {
  const wrap = node("div", "row");
  const l = node("label", "", label);
  l.htmlFor = id;
  const input = node("input");
  input.id = id;
  input.type = "text";
  input.maxLength = max;
  input.value = value;
  input.autocomplete = "off";
  input.addEventListener("input", () => {
    onInput(input.value);
    refreshForm();
  });
  wrap.append(l, input);
  return wrap;
}

const num = (v) => (v == null ? null : Number(v));

function renderForm() {
  if (!form || !proposal) return;
  const opts = columnOptions(proposal);
  const parts = [];
  if (form.askHeaderRow) {
    const rows = Array.isArray(proposal.preview) ? proposal.preview : [];
    parts.push(selectField(
      "spd-f-header", "Which row has the column names?",
      rows.map((_, i) => ({ value: i, label: `Row ${i + 1}` })),
      form.headerRow, (v) => { form.headerRow = num(v); }));
  }
  parts.push(selectField("spd-f-date", "Date column", opts, form.dateColumn, (v) => { form.dateColumn = num(v); }));
  parts.push(selectField("spd-f-desc", "Description column", opts, form.descriptionColumn, (v) => { form.descriptionColumn = num(v); }));
  parts.push(radioGroup("spd-mode", "How the amounts are written", MODES, form.mode,
    (k) => { form.mode = k; if (k !== "one") form.sign1 = null; }, true));
  if (form.mode === "one") {
    parts.push(selectField("spd-f-amount", "Amount column", opts, form.amountColumn, (v) => { form.amountColumn = num(v); }));
    parts.push(radioGroup("spd-sign", "Which sign means money spent?", SIGN_CHOICES, form.sign1,
      (k) => { form.sign1 = k; }, false));
  } else if (form.mode === "debit_credit") {
    parts.push(selectField("spd-f-debit", "Debit column", opts, form.debitColumn, (v) => { form.debitColumn = num(v); }));
    parts.push(selectField("spd-f-credit", "Credit column", opts, form.creditColumn, (v) => { form.creditColumn = num(v); }));
  } else if (form.mode === "drcr") {
    parts.push(selectField("spd-f-amount", "Amount column", opts, form.amountColumn, (v) => { form.amountColumn = num(v); }));
    parts.push(selectField("spd-f-drcr", "Dr/Cr column", opts, form.drcrColumn, (v) => { form.drcrColumn = num(v); }));
  }
  if (form.ownOrder) {
    parts.push(node("p", "note", ORDER_OWN));
  } else {
    parts.push(radioGroup("spd-order", "Date order", ORDER_CHOICES, form.dateOrder,
      (k) => { form.dateOrder = k; }, false));
  }
  parts.push(radioGroup("spd-decimal", "Decimal mark", DECIMALS, form.decimal,
    (k) => { form.decimal = k; }, false));
  parts.push(textField("spd-f-currency", "Currency (optional)", 6, form.currency, (v) => { form.currency = v; }));
  parts.push(textField("spd-f-label", "Name", 60, form.label, (v) => { form.label = v; }));
  el.form.replaceChildren(...parts);
  refreshForm();
}

/** Save on only when every question has an answer; the sign sentence under
 *  the sign choice follows the choice. */
function refreshForm() {
  if (!form) return;
  el.save.disabled = busy || !canPress(form, previewNow, el.accept.checked);
  const sign = signOf(form.mode, form.sign1);
  const sentences = (proposal && (proposal.sign_sentences || (proposal.sentences && { [sign]: proposal.sentences.sign }))) || {};
  el.signSentence.textContent = sign && sentences[sign] ? sentences[sign] : "";
  schedulePreview();
}

/** Show what the choices would count, from the PC (it reads the file), a
 *  moment after the owner stops choosing. A failed or missing answer just
 *  shows nothing: the PC checks again when Save is pressed. */
function schedulePreview() {
  if (previewTimer) clearTimeout(previewTimer);
  const body = form && previewBody(form);
  if (!body) {
    previewSeq += 1;
    paintPreview({ line: "", warnings: [], problems: [] });
    return;
  }
  previewTimer = setTimeout(async () => {
    const mine = ++previewSeq;
    el.counts.textContent = BOX.checking;
    let state = { line: "", warnings: [], problems: [] };
    try {
      state = previewState(await invoke("spending_profile_save", { choices: body }));
    } catch (error) {
      state = { line: "", warnings: [], problems: [] };
    }
    if (mine !== previewSeq || !form) return;
    paintPreview(state);
  }, 350);
}

function paintPreview(state) {
  previewNow = state;
  el.counts.textContent = state.line;
  const bad = state.problems.length > 0;
  el.warnings.hidden = !bad;
  el.warnings.textContent = bad ? BOX.misfitPrefix + state.warnings.join("; ") + "." : "";
  el.acceptWrap.hidden = !bad;
  if (!bad) el.accept.checked = false;
  el.acceptText.textContent = BOX.acceptTick;
  if (form) el.save.disabled = busy || !canPress(form, previewNow, el.accept.checked);
}

function showProposal(p, file) {
  proposal = p;
  form = formFor(p, file);
  el.check.hidden = false;
  el.checkTitle.textContent = BOX.dialogTitle;
  el.save.textContent = BOX.save;
  el.cancel.textContent = BOX.cancel;
  const hidden = Number(p.hidden_columns) > 0;
  el.checkHidden.hidden = !hidden;
  el.checkHidden.textContent = hidden ? p.hidden_note || WORDS.HIDDEN_COLUMNS_NOTE : "";
  const table = previewTable(p);
  el.previewWrap.replaceChildren(...(table ? [table] : []));
  el.previewWrap.hidden = !table;
  renderForm();
  say(el.checkStatus, "");
  el.checkTitle.focus();
}

async function readProposal(file, again = false) {
  return invoke("spending_profile_read", { file, again });
}

async function openCheck(file, { again = false } = {}) {
  if (busy) return;
  if (!file) {
    say(el.checkStatus, "Choose a bank file first.", "bad");
    return;
  }
  busy = true;
  paint();
  try {
    // "Check the columns again" asks the PC for a fresh reading of the file
    // with the saved choices filled in. NOTHING is deleted: Save writes over
    // the same layout, Cancel changes nothing, and "Forget this layout" is the
    // only thing that deletes (after "are you sure?").
    const out = await readProposal(file, again);
    if (out && out.known === true && !again) {
      say(el.fileNote, "This file already has a saved layout. Use \"" + BOX.again + "\" on its row to choose its columns again.", "ok");
      busy = false;
      paint();
      return;
    }
    showProposal(out, file);
    if (out && typeof out.misfit === "string" && out.misfit) say(el.checkStatus, out.misfit, "bad");
  } catch (error) {
    el.check.hidden = false;
    say(el.checkStatus, problemWords(error), "bad");
  } finally {
    busy = false;
  }
  await load({ keepCats: true });
}

async function saveColumns() {
  const body = form && saveBody(form, { accept: el.accept.checked });
  if (!body) return;
  const out = await act("spending_profile_save", { choices: body }, el.checkStatus, "Saving…");
  if (!out) {
    // The PC refused because the choices do not fit the file: show the box
    // to tick, so the owner can still decide to keep them.
    if (/does not fit|do not fit/i.test(el.checkStatus.textContent || "")) {
      previewNow = { ...previewNow, problems: previewNow.problems.length ? previewNow.problems : ["misfit"] };
      el.acceptWrap.hidden = false;
      el.acceptText.textContent = BOX.acceptTick;
      refreshForm();
    }
    return;
  }
  const said = savedLine(out);
  closeCheck();
  say(el.fileNote, said, "ok");
  announce(said);
  await load({ keepCats: true });
  el.fileNote.textContent = said;
}

async function forgetLayout(id) {
  forgetAsk = "";
  const out = await act("spending_profile_delete", { id }, el.fileNote, "Forgetting…");
  if (!out) return;
  announce(BOX.forget);
  await load({ keepCats: true });
}

/* ── Categories ──────────────────────────────────────────────────────── */

function categoryProblem() {
  const names = cats.map((c) => c.category.trim());
  if (names.some((n) => !n)) return "Every category needs a name.";
  if (new Set(names.map((n) => n.toLowerCase())).size !== names.length) return "Two categories have the same name.";
  return "";
}

async function saveCategories() {
  const problem = categoryProblem();
  if (problem) {
    say(el.catStatus, problem, "bad");
    return;
  }
  cats = cats.map((c) => ({ category: c.category.trim(), words: c.words }));
  const out = await act("spending_categories_save", { categories: categoriesBody(cats) }, el.catStatus, "Saving…");
  if (!out) return;
  say(el.catStatus, "Saved. The totals use these words from your next question.", "ok");
  announce("Categories saved.");
  await load();
  say(el.catStatus, "Saved. The totals use these words from your next question.", "ok");
}

function askReset() {
  el.resetSure.hidden = false;
  el.resetLine.textContent = BOX.resetSure;
  el.resetYes.textContent = BOX.resetYes;
  el.resetNo.textContent = BOX.resetNo;
  el.resetNo.focus();
}

async function doReset() {
  el.resetSure.hidden = true;
  const out = await act("spending_categories_reset", {}, el.catStatus, "Putting the starter list back…");
  if (!out) return;
  await load();
  say(el.catStatus, "The starter categories are back.", "ok");
  announce("The starter categories are back.");
}

/* ── Suggestions ─────────────────────────────────────────────────────── */

function paintSuggestions() {
  el.suggestions.replaceChildren(...found.map((s) => {
    const li = node("li", "sc-gpu");
    const l = node("label", "toggle");
    const box = node("input");
    box.type = "checkbox";
    box.checked = s.ticked;
    box.addEventListener("change", () => { s.ticked = box.checked; paintSuggestAdd(); });
    l.append(box, node("span", "", `${s.name} → ${s.category}`));
    li.append(l);
    return li;
  }));
  paintSuggestAdd();
}

function paintSuggestAdd() {
  const n = found.filter((s) => s.ticked).length;
  el.suggestAdd.hidden = !found.length;
  el.suggestAdd.textContent = BOX.addRules;
  el.suggestAdd.disabled = busy || n === 0 || !(view && view.can_edit);
}

async function askSuggestions() {
  const file = cleanFile();
  if (!file) return;
  const out = await act("spending_suggest", { file }, el.suggestStatus, "Asking the local model…");
  if (!out) return;
  const list = Array.isArray(out.suggestions) ? out.suggestions : [];
  found = list
    .filter((s) => s && typeof s.name === "string" && typeof s.category === "string")
    .map((s) => ({ name: s.name, category: s.category, ticked: true }));
  say(el.suggestStatus, found.length ? String(out.note || "") : "No suggestions this time.", found.length ? "" : "ok");
  paintSuggestions();
}

async function addRules() {
  const ticked = found.filter((s) => s.ticked);
  if (!ticked.length) return;
  const merged = mergeSuggestions(cats, ticked);
  const out = await act("spending_categories_save", { categories: categoriesBody(merged) }, el.suggestStatus, "Saving…");
  if (!out) return;
  found = [];
  await load();
  say(el.suggestStatus, "Added. The totals use these words from your next question.", "ok");
  paintSuggestions();
  announce("Rules added.");
}

/* ── Wiring ──────────────────────────────────────────────────────────── */

if (el.section) {
  el.save.addEventListener("click", saveColumns);
  el.cancel.addEventListener("click", closeCheck);
  el.file.addEventListener("change", () => { pickedFile = el.file.value; paint(); });
  el.accept.addEventListener("change", () => refreshForm());
  el.catAdd.addEventListener("click", () => {
    cats.push({ category: "", words: [] });
    paint();
    focusCat(cats.length - 1);
  });
  el.catSave.addEventListener("click", saveCategories);
  el.catReset.addEventListener("click", askReset);
  el.resetYes.addEventListener("click", doReset);
  el.resetNo.addEventListener("click", () => { el.resetSure.hidden = true; el.catReset.focus(); });
  el.suggest.addEventListener("click", askSuggestions);
  el.suggestAdd.addEventListener("click", addRules);
}
onLink(() => { if (view) paint(); });
// A card answered (or expired): read again. onQueue also delivers the first read.
onQueue(() => load({ keepCats: true }));
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) load({ keepCats: true });
});
