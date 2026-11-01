/**
 * The Notes editor's formatting toolbar, shortcuts and template menu.
 *
 * Pure checks against src/notes.js (the same functions the buttons use), plus
 * source pins that the Brain wires them into the editor and that no button
 * adds a write path: Save is still the only write, through its ONE card.
 *
 * The real-browser half of the editor sits in notes-edit.mjs; Playwright is not
 * installed here, and this file deliberately needs only Node.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  BUILTIN_TEMPLATES, EDITOR_HELP, SHORTCUTS, TOOLBAR,
  applyMarkdownEdit, builtinTemplate, fillTemplate, formatDateTime,
  insertTextAtSelection, noteCounts, shortcutAction, vaultTemplateFiles,
} from "../src/notes.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const src = (name) => fs.readFileSync(path.join(HERE, "..", "src", name), "utf8");

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── Every formatting control, one concrete insertion each ──────────────── */

check("bold/italic/strikethrough/code wrap the selection in the exact markdown", () => {
  assert.deepEqual(applyMarkdownEdit("word", 0, 4, "bold"),
    { text: "**word**", selectionStart: 2, selectionEnd: 6 });
  assert.equal(applyMarkdownEdit("word", 0, 4, "italic").text, "_word_");
  assert.equal(applyMarkdownEdit("word", 0, 4, "strike").text, "~~word~~");
  assert.equal(applyMarkdownEdit("word", 0, 4, "code").text, "`word`");
});

check("bold with no selection inserts the placeholder and selects it", () => {
  const got = applyMarkdownEdit("ab", 1, 1, "bold");
  assert.equal(got.text, "a**bold**b");
  assert.equal(got.text.slice(got.selectionStart, got.selectionEnd), "bold");
});

check("quote/bullet/checklist prefix every selected line", () => {
  assert.equal(applyMarkdownEdit("a\nb", 0, 3, "quote").text, "> a\n> b");
  assert.equal(applyMarkdownEdit("a\nb", 0, 3, "bullet").text, "- a\n- b");
  assert.equal(applyMarkdownEdit("a\nb", 0, 3, "checklist").text, "- [ ] a\n- [ ] b");
});

check("numbered list numbers each line; a second press removes the numbers", () => {
  const once = applyMarkdownEdit("a\nb", 0, 3, "numbered");
  assert.equal(once.text, "1. a\n2. b");
  assert.equal(applyMarkdownEdit(once.text, 0, once.text.length, "numbered").text, "a\nb");
});

check("heading buttons put ## / ### at the line start", () => {
  assert.equal(applyMarkdownEdit("Title", 0, 5, "h2").text, "## Title");
  assert.equal(applyMarkdownEdit("Title", 0, 5, "h3").text, "### Title");
});

check("horizontal rule inserts --- on its own line", () => {
  const got = applyMarkdownEdit("x", 0, 0, "rule");
  assert.equal(got.text, "---\nx");
  assert.equal(applyMarkdownEdit("a", 1, 1, "rule").text, "a\n---\n");
});

check("wikilink wraps a selection, and inserts [[]] with the cursor inside otherwise", () => {
  assert.equal(applyMarkdownEdit("Note", 0, 4, "wikilink").text, "[[Note]]");
  const empty = applyMarkdownEdit("ab", 1, 1, "wikilink");
  assert.equal(empty.text, "a[[]]b");
  assert.equal(empty.selectionStart, 3);
});

check("tag inserts # before a selection or a bare # otherwise", () => {
  assert.equal(applyMarkdownEdit("home", 0, 4, "tag").text, "#home");
  assert.equal(applyMarkdownEdit("x", 1, 1, "tag").text, "x#");
});

check("date/time inserts the local timestamp", () => {
  const got = applyMarkdownEdit("", 0, 0, "datetime", {
    now: new Date(2026, 9, 31, 17, 58),
  });
  assert.equal(got.text, "2026-10-31 17:58");
  assert.equal(formatDateTime(new Date(2026, 0, 2, 3, 4)), "2026-01-02 03:04");
});

check("code fence wraps a selection, or opens an empty fence with the caret inside", () => {
  assert.equal(applyMarkdownEdit("x", 0, 1, "fence").text, "```\nx\n```");
  const empty = applyMarkdownEdit("", 0, 0, "fence");
  assert.equal(empty.text, "```\n\n```");
  assert.equal(empty.selectionStart, 4);
});

check("every toolbar action has a label, an accessible name and the exact-markdown title", () => {
  for (const action of ["bold", "italic", "strike", "code", "quote", "bullet",
    "numbered", "checklist", "h2", "h3", "rule", "wikilink", "tag", "datetime"]) {
    const spec = TOOLBAR.find((t) => t.action === action);
    assert.ok(spec, `${action} is missing from the toolbar`);
    assert.ok(spec.label && spec.aria && spec.title, `${action} has an empty label/aria/title`);
    assert.match(spec.title, /Ctrl\+|inserts|puts|numbers|wraps/i, `${action} title`);
  }
});

/* ── Shortcuts ──────────────────────────────────────────────────────────── */

check("the editor shortcuts map to the toolbar's own actions", () => {
  const ev = (key, extra = {}) => shortcutAction({ key, ctrlKey: true, ...extra });
  assert.equal(ev("b"), "bold");
  assert.equal(ev("i"), "italic");
  assert.equal(ev("k"), "wikilink");
  assert.equal(ev("e"), "code");
  assert.equal(ev("x", { shiftKey: true }), "strike");
  assert.equal(ev("q", { shiftKey: true }), "quote");
  assert.equal(ev("7", { shiftKey: true }), "numbered");
  assert.equal(ev("8", { shiftKey: true }), "bullet");
  assert.equal(ev("9", { shiftKey: true }), "checklist");
  assert.equal(ev("2"), "h2");
  assert.equal(ev("3"), "h3");
  assert.deepEqual(SHORTCUTS, {
    "ctrl+b": "bold", "ctrl+i": "italic", "ctrl+k": "wikilink",
    "ctrl+e": "code", "ctrl+shift+x": "strike", "ctrl+shift+q": "quote",
    "ctrl+shift+7": "numbered", "ctrl+shift+8": "bullet",
    "ctrl+shift+9": "checklist", "ctrl+2": "h2", "ctrl+3": "h3",
  });
});

check("a modifier we do not claim is left to the browser", () => {
  assert.equal(shortcutAction({ key: "p", ctrlKey: true, shiftKey: true }), "");
  assert.equal(shortcutAction({ key: "b" }), "");
  assert.equal(shortcutAction({ key: "b", ctrlKey: true, altKey: true }), "");
});

/* ── Counts and templates ───────────────────────────────────────────────── */

check("the counter carries words, characters and the selection count", () => {
  assert.deepEqual(noteCounts("one two", 0, 0),
    { chars: 7, words: 2, selectedChars: 0, selectedWords: 0 });
  const selected = noteCounts("one two", 0, 3);
  assert.equal(selected.selectedChars, 3);
  assert.equal(selected.selectedWords, 1);
});

check("the four built-in templates are named as the owner asked", () => {
  assert.deepEqual(BUILTIN_TEMPLATES.map((t) => t.label),
    ["Workout log", "Meeting notes", "Daily journal", "Project note"]);
  for (const t of BUILTIN_TEMPLATES) assert.ok(t.id && t.body, t.label);
});

check("templates fill {date} and {title} and leave unknown tokens alone", () => {
  const body = builtinTemplate("meeting-notes", { date: "2026-10-31 17:58", title: "Weekly" });
  assert.match(body, /^# Meeting notes - 2026-10-31 17:58/);
  assert.equal(fillTemplate("a {date} b {title} c {nope}", { date: "D", title: "T" }),
    "a D b T c {nope}");
  assert.equal(builtinTemplate("nope"), "");
});

check("the vault template list comes from the list the plate already read", () => {
  const notes = [
    { path: "Templates/Workout.md", title: "Workout" },
    { path: "templates/Meeting.md", title: "Meeting" },
    { path: "Inbox/idea.md", title: "idea" },
    { path: "Templates/Notes.txt", title: "Notes" },
    { path: "Templates/Workout.md", title: "Workout" },
  ];
  assert.deepEqual(vaultTemplateFiles(notes), [
    { path: "Templates/Workout.md", label: "Workout" },
    { path: "templates/Meeting.md", label: "Meeting" },
  ]);
  assert.deepEqual(vaultTemplateFiles(null), []);
});

check("template insertion puts the text at the caret and replaces no file", () => {
  const got = insertTextAtSelection("ab", 1, 1, "XYZ");
  assert.deepEqual(got, { text: "aXYZb", selectionStart: 4, selectionEnd: 4 });
  assert.equal(insertTextAtSelection("ab", 0, 2, "XYZ").text, "XYZ");
});

/* ── Wiring pins: the page has the controls, and only Save writes ──────── */

check("the editor renders the toolbar, template menu, help line and counter", () => {
  const js = src("notes.js");
  assert.match(js, /notes-toolbar/);
  assert.match(js, /role", "toolbar"/);
  assert.match(js, /aria-label", "Markdown formatting"/);
  assert.match(js, /aria-label", "Insert template"/);
  assert.match(js, /note-template/);
  assert.match(js, /EDITOR_HELP/);
  assert.match(js, /notes-count/);
  assert.match(js, /text\.addEventListener\("keydown"/);
  // The textarea is the only place shortcuts are read, so no app hotkey moves.
  assert.doesNotMatch(js, /document\.addEventListener\("keydown"/);
});

check("formatting edits call onDraft and never raise a save from the toolbar", () => {
  const js = src("notes.js");
  // Only the toolbar/template/handler block, not the untouched saveNote().
  const tools = js.slice(js.indexOf("function editorTools"),
    js.indexOf("/**\n * Paints the plate"));
  assert.ok(tools.length > 1000, "the editorTools block was not found");
  assert.match(tools, /plate\.onDraft\(text\.value\)/);
  assert.doesNotMatch(tools, /notes_save|saveNote\(|notes_list|notes_read/);
});

check("the Brain reads a vault template through the existing notes_read command", () => {
  const js = src("brain.js");
  assert.match(js, /async function readNotesTemplate/);
  assert.match(js, /invoke\("notes_read", \{ path \}\)/);
  assert.match(js, /readTemplate: readNotesTemplate/);
  assert.match(js, /onDraft: \(text\) =>/);
});

check("the card explains the toolbar and Save still needs one approval", () => {
  const html = src("brain.html");
  assert.match(html, /formatting toolbar, templates and shortcuts insert/);
  assert.match(html, /Every Save raises one\s+approval card/);
});

check("the toolbar styling is present and inherits the design system", () => {
  const css = src("brain.css");
  for (const cls of [".notes-toolbar", ".note-tool", ".note-template",
    ".notes-help", ".notes-count", ".notes-template-said"]) {
    assert.match(css, new RegExp(cls.replace(".", "\\.")));
  }
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nall checks passed");
