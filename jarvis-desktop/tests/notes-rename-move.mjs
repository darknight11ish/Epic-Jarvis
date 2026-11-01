/**
 * Rename and move ONE note from the desktop Notes plate (wave 4, 2026-10-31).
 *
 * Gemini ruling 1: the chat grammar AND structured UI controls, both calling
 * the same backend routes. This is the UI half's proof for the parts a plain
 * Node process can hold:
 *
 *  * the two bodies are EXACTLY the wave-4 contract's - `{path, title}` for a
 *    rename, `{path, folder, create_folder}` for a move - and `create_folder`
 *    is a real boolean (false unless the owner ticked "create it");
 *  * the folder list is derived from the note list the editor already reads -
 *    no new read path - and includes the vault's top level;
 *  * a waiting card is followed with the module's own `notes_change_status`
 *    until `saved` / `denied` / `failed`, and only `saved` reads as changed
 *    (its sentence is the module's, including "You can undo it."), naming the
 *    new path so the page can open the note at its real name;
 *  * the page never saves, approves or calls a pending route itself: the only
 *    commands it uses here are the three notes commands, and the ONE card
 *    stays the PC's.
 *
 * The browser half (clicking the two chrome controls, the disabled state when
 * the note has no path, focus/aria) needs Playwright; it is NOT run here and
 * the frontend job is authority for it. No claim is made that a card was
 * answered or that any file was written: that is the backend suite's job.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  changeNote,
  describeChange,
  folderChoices,
  moveBody,
  moveNote,
  renameBody,
  renameNote,
  titleOf,
} from "../src/notes.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const src = (name) => fs.readFileSync(path.join(HERE, "..", "src", name), "utf8");
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── the bodies are the contract's, byte for byte ─────────────────────────── */

await check("a rename sends exactly {path, title}", async () => {
  assert.deepEqual(renameBody({ path: "Inbox/idea.md", title: "Better idea" }),
    { path: "Inbox/idea.md", title: "Better idea" });
  assert.deepEqual(renameBody({ path: "A.md", title: "  Keep me  " }), { path: "A.md", title: "Keep me" });
  assert.deepEqual(renameBody(), { path: "", title: "" });
});

await check("a move sends exactly {path, folder, create_folder} and create_folder is a real boolean", async () => {
  assert.deepEqual(moveBody({ path: "A.md", folder: "Archive" }),
    { path: "A.md", folder: "Archive", create_folder: false });
  assert.deepEqual(moveBody({ path: "A.md", folder: "New Folder", createFolder: true }),
    { path: "A.md", folder: "New Folder", create_folder: true });
  assert.deepEqual(moveBody({ path: "A.md", folder: "" }),
    { path: "A.md", folder: "", create_folder: false });
  assert.equal(moveBody({ path: "A.md", folder: "X", createFolder: "yes" }).create_folder, false);
});

/* ── the folder list comes from the note list already read ───────────────── */

await check("every folder the note list proves exists is offered, top level first", async () => {
  const choices = folderChoices([
    { path: "Inbox/idea.md" },
    { path: "Projects/2026/plan.md" },
    { path: "Top.md" },
    { path: "Inbox/second.md" },
  ]);
  assert.deepEqual(choices, ["", "Inbox", "Projects", "Projects/2026"]);
  assert.deepEqual(folderChoices(null), [""]);
  assert.deepEqual(folderChoices([]), [""]);
});

await check("a title is the filename without its extension", async () => {
  assert.equal(titleOf("Inbox/idea.md"), "idea");
  assert.equal(titleOf("plan.txt"), "plan");
  assert.equal(titleOf(""), "");
});

/* ── waiting is not a finish; only saved reads as changed ───────────────── */

await check("rename follows the ONE card and only saved is final, naming the new path", async () => {
  const calls = [];
  const said = [];
  const invoke = async (cmd, args) => {
    calls.push([cmd, args]);
    if (cmd === "notes_rename") {
      return { ok: true, state: "waiting", id: "nb_rename_1", target: "Better idea.md" };
    }
    if (cmd === "notes_change_status") {
      return {
        ok: true, state: "saved", kind: "rename", path: "Inbox/idea.md",
        target: "Inbox/Better idea.md", updates: 2, notes: 1,
        message: "This renames Inbox/idea.md to Inbox/Better idea.md and updates 2 "
          + "link(s) in 1 note(s). You can undo it.",
      };
    }
    throw new Error(`unexpected command ${cmd}`);
  };
  const last = await renameNote(invoke, { path: "Inbox/idea.md", title: "Better idea" },
    (s) => said.push(s), { pollMs: 1, giveUpMs: 1000 });
  assert.deepEqual(calls[0], ["notes_rename", { path: "Inbox/idea.md", title: "Better idea" }]);
  assert.deepEqual(calls[1], ["notes_change_status", { id: "nb_rename_1" }]);
  assert.equal(calls.length, 2);
  assert.equal(said[0].final, false);
  assert.equal(said[0].state, "waiting");
  assert.equal(last.final, true);
  assert.equal(last.state, "saved");
  assert.equal(last.tone, "ok");
  assert.equal(last.target, "Inbox/Better idea.md");
  assert.match(last.text, /You can undo it\./);
});

await check("move sends the folder and only the explicit create flag, then follows the same job", async () => {
  const calls = [];
  const invoke = async (cmd, args) => {
    calls.push([cmd, args]);
    if (cmd === "notes_move") return { ok: true, state: "waiting", id: "nb_move_1" };
    if (cmd === "notes_change_status") {
      return { ok: true, state: "saved", kind: "move", target: "Archive/A.md",
        message: "This moves A.md to Archive/A.md. You can undo it." };
    }
    throw new Error(`unexpected command ${cmd}`);
  };
  const last = await moveNote(invoke, { path: "A.md", folder: "Archive", createFolder: false },
    () => {}, { pollMs: 1, giveUpMs: 1000 });
  assert.deepEqual(calls[0], ["notes_move", { path: "A.md", folder: "Archive", create_folder: false }]);
  assert.equal(last.state, "saved");
  assert.equal(last.target, "Archive/A.md");
});

await check("a denied card reads as no change, with the module's own words", async () => {
  const invoke = async (cmd) => {
    if (cmd === "notes_rename") return { ok: true, state: "waiting", id: "nb2" };
    if (cmd === "notes_change_status") {
      return {
        ok: false, state: "denied",
        message: "You said no, so the note was not renamed and no link was changed.",
      };
    }
    throw new Error(`unexpected command ${cmd}`);
  };
  const last = await renameNote(invoke, { path: "A.md", title: "B" }, () => {},
    { pollMs: 1, giveUpMs: 1000 });
  assert.equal(last.final, true);
  assert.equal(last.state, "denied");
  assert.equal(last.tone, "bad");
  assert.match(last.text, /not renamed/);
  assert.equal(last.target, "");
});

await check("a failed change is final and claims no write", async () => {
  const last = describeChange({ ok: false, state: "failed", message: "The move failed (OSError), so nothing was changed." });
  assert.equal(last.final, true);
  assert.equal(last.tone, "bad");
  assert.match(last.text, /nothing was changed/);
  const unknown = describeChange({});
  assert.equal(unknown.final, true);
  assert.match(unknown.text, /did not say how the change went/);
  const waiting = describeChange({ state: "waiting", message: "This renames A.md to B.md." });
  assert.equal(waiting.final, false);
  assert.equal(waiting.text, "This renames A.md to B.md.");
});

/* ── the page uses the three notes commands only; the card stays the PC's ─ */

await check("the web page asks only the notes commands and never saves or approves", async () => {
  const page = src("notes.js");
  for (const command of ['invoke("notes_rename"', 'invoke("notes_move"', 'invoke("notes_change_status"']) {
    assert.ok(page.includes(command), `notes.js never calls ${command}`);
  }
  // The change helper itself must not reach a save or an approval route; the
  // plate's existing Save is a different control with its own card.
  const start = page.indexOf("export async function changeNote");
  const end = page.indexOf("Rename one note through the PC");
  const changeFn = start >= 0 && end > start ? page.slice(start, end) : "";
  for (const banned of ["notes_save", "/api/notes/save", "/api/pending", "approvePending",
                        "/api/approve", "saveNote("]) {
    assert.ok(!changeFn.includes(banned), `the change helper must not call ${banned}`);
  }
  assert.ok(page.includes("plate.onRename"), "the Rename control has no page action");
  assert.ok(page.includes("plate.onMove"), "the Move control has no page action");
  assert.ok(page.includes("Create it if it does not exist"),
    "the new-folder checkbox does not say what it does");
  assert.ok(page.includes("plate.onMove(folder, typed ? create.checked : false)"),
    "create_folder is not tied to the explicit checkbox");
  assert.ok(page.includes("const canChange = Boolean(open.path)"),
    "the controls are not disabled when the note has no path");
});

await check("the Brain window wires both controls to the shared one-card follow", async () => {
  const brain = src("brain.js");
  assert.ok(brain.includes("onRename: renameNotesNote"));
  assert.ok(brain.includes("onMove: moveNotesNote"));
  assert.ok(brain.includes("const run = kind === \"rename\" ? renameNote : moveNote"));
  assert.ok(brain.includes("linkDown: () => !currentLink().connected"),
    "the follow does not stop polling while the PC is unreachable");
  assert.ok(brain.includes("if (last.state === \"saved\" && last.target)"),
    "the page does not open the moved/renamed note after a saved change");
});

/* ── the Rust boundary carries exactly three commands for this UI ───────── */

await check("the Rust commands exist, are registered, and are granted to the Brain window", async () => {
  const commands = fs.readFileSync(
    path.join(HERE, "..", "src-tauri", "src", "commands.rs"), "utf8");
  for (const name of ["notes_rename", "notes_move", "notes_change_status"]) {
    assert.ok(commands.includes(`pub async fn ${name}(`), `commands.rs has no ${name}`);
  }
  assert.ok(commands.includes('"/api/notes/rename"'), "no rename route in Rust");
  assert.ok(commands.includes('"/api/notes/move"'), "no move route in Rust");
  assert.ok(commands.includes("/api/notes/change?id="), "no change-status route in Rust");
  const lib = fs.readFileSync(path.join(HERE, "..", "src-tauri", "src", "lib.rs"), "utf8");
  for (const name of ["commands::notes_rename", "commands::notes_move", "commands::notes_change_status"]) {
    assert.ok(lib.includes(name), `lib.rs does not register ${name}`);
  }
  const build = fs.readFileSync(path.join(HERE, "..", "src-tauri", "build.rs"), "utf8");
  for (const name of ["\"notes_rename\"", "\"notes_move\"", "\"notes_change_status\""]) {
    assert.ok(build.includes(name), `build.rs does not generate the permission for ${name}`);
  }
  const surfaces = fs.readFileSync(
    path.join(HERE, "..", "src-tauri", "permissions", "surfaces.toml"), "utf8");
  for (const name of ["allow-notes-rename", "allow-notes-move", "allow-notes-change-status"]) {
    assert.ok(surfaces.includes(`"${name}"`), `surfaces.toml does not grant ${name}`);
  }
});

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nthe Rename/Move controls ask the wave-4 routes, follow the ONE card, and claim no write");
process.exit(fails.length ? 1 : 0);
