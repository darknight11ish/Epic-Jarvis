/**
 * "Folders Jarvis may look in" on the desktop (the owner's decisions of
 * 2026-09-26: asking about PDFs and Word files, and the Notion import;
 * JARVIS-API.md section 35; src/folders.js, src/folders-settings.js,
 * src-tauri/src/folders.rs).
 *
 * What must hold:
 * - the words are the PC's own (tests/fixtures/folders-cases.json, made by
 *   the real jarvis_documents.py), and the phone's net/Folders.kt says the
 *   same;
 * - Settings lists every folder the PC sends, with Remove on each; Remove is
 *   sent at once, even on a stale link;
 * - "Add a folder…" is offered only when the PC says this request may add,
 *   on a live link, with no card waiting; the Notion import likewise, and
 *   only into a folder that is on the list and on this PC;
 * - folder names are the owner's: shown as text, never as markup;
 * - "Send a file to your phone…" (2026-11-14, the SEND-TO-PHONE-2GB-DESIGN
 *   sections 6 and 8) sends ONE request with NO path - the owner's pick in the
 *   Windows dialog is the only one - is greyed while it waits and on a stale
 *   link, and shows the PC's sentence or its refusal;
 * - CONTROL: the five commands sit with the Settings window only, the
 *   pickers are Rust's (the page gets no file system), and adding, importing
 *   and sending are held on a stale link in Rust too.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  actions,
  folderLines,
  importLine,
  MISSING,
  NOT_HERE,
  readFolders,
  SEND_LABEL,
  sendWords,
  STALE,
  TITLE,
} from "../src/folders.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const readRepo = (p) => readFileSync(join(HERE, "..", "..", p), "utf8");
const CASES = K.FOLDERS;
const C = CASES.cases;

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The words and the reading ───────────────────────────────────────── */

await check("the words are the PC's", async () => {
  const v = readFolders(C.two_folders_pc);
  assert.equal(v.title, TITLE);
  assert.equal(C.two_folders_pc.title, TITLE);
  assert.ok(v.detail.includes("outside text"));
  assert.equal(v.folders.length, 2);
  assert.equal(v.folders[0].name, "Documents");
  const py = readRepo("backend/jarvis_documents.py");
  assert.ok(py.includes(`"${MISSING.slice(0, 40)}`), "MISSING is the PC's own");
  const kt = readRepo("jarvis-client/app/src/main/java/com/jarvis/client/net/Folders.kt");
  assert.ok(kt.includes(TITLE) && kt.includes(MISSING.slice(0, 40)), "the phone says the same");
});

await check("adding: the PC, a live link, no card waiting; removing: always", async () => {
  const pc = readFolders(C.two_folders_pc);
  assert.equal(actions(pc, true).add, true);
  assert.equal(actions(pc, false).add, false, "held on a stale link");
  assert.equal(actions(pc, false).addWhy, STALE);
  assert.equal(actions(pc, false).remove, true, "removing is never held");
  const phone = readFolders(C.two_folders_phone);
  assert.equal(actions(phone, true).add, false, "only the PC adds");
  assert.equal(actions(phone, true).addWhy, phone.phoneAdd);
  const waiting = readFolders(C.waiting);
  assert.equal(actions(waiting, true).add, false, "one card at a time");
  assert.ok(waiting.waiting.endsWith("Notion"));
});

await check("a folder gone from the PC says so; a PC without it says what to do", async () => {
  const v = readFolders(C.two_folders_pc);
  assert.deepEqual(folderLines({ ...v.folders[0], exists: false }), [v.folders[0].path, NOT_HERE]);
  assert.equal(readFolders(null).why, MISSING);
  assert.equal(readFolders({ available: false }).why, MISSING);
  assert.equal(readFolders(C.damaged).folders.length, 0);
  assert.ok(readFolders(C.damaged).why.includes("damaged"));
});

await check("Send a file: the PC's sentence, the PC's refusal, or the file it named", async () => {
  // folders.rs `send_file_answer`: `said` is the PC's own words, and the page
  // shows them as they are. It waits for a live link (it raises a card) and
  // for nothing else.
  const pc = readFolders(C.two_folders_pc);
  assert.equal(actions(pc, true).send, true);
  assert.equal(actions(pc, false).send, false, "held on a stale link");
  assert.equal(actions(readFolders(C.two_folders_phone), true).send, true,
    "the phone's view is not this button's business");
  assert.equal(sendWords({ ok: true, said: "Waiting for your yes on this PC." }),
    "Waiting for your yes on this PC.");
  assert.equal(sendWords({ ok: false, said: "That file is bigger than 2 GB." }),
    "That file is bigger than 2 GB.", "a refusal is the PC's sentence too");
  // No sentence at all: the name and size the command sent back, so the page
  // never says "Done." about a file it cannot name.
  assert.equal(sendWords({ ok: true, name: "report.pdf", size: 2411724 }),
    "report.pdf (2 MB)");
  assert.equal(sendWords({ ok: true, name: "notes.txt", size: 812 }), "notes.txt");
  assert.equal(sendWords(null), "");
});

/* ── Settings ─────────────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();

function exists(view) {
  const v = JSON.parse(JSON.stringify(view));
  for (const f of v.folders) f.exists = true;
  return v;
}

async function settings(folders, data = {}) {
  const page = await K.open(browser, base, "settings.html", { folders, ...data },
    { width: 820, height: 2400 });
  await page.waitForTimeout(700);
  return page;
}

const calls = (page) => page.evaluate(() => window.__calls
  .filter(([c]) => ["add_folder", "remove_folder", "import_notion",
                    "prepare_file_for_phone"].includes(c)));

await check("Settings: every folder, in the PC's words, with Remove", async () => {
  const page = await settings({ view: exists(C.two_folders_pc) });
  const text = await page.locator("#folders").innerText();
  const buttons = await page.locator("#fo-list button").count();
  const errors = page.__errors;
  await page.close();
  assert.ok(text.includes(C.two_folders_pc.detail));
  assert.ok(text.includes("C:\\Users\\owner\\Documents"));
  assert.ok(text.includes(C.two_folders_pc.documents.said));
  assert.equal(buttons, 2);
  assert.deepEqual(errors, []);
});

await check("Settings: Remove is sent at once, even on a stale link", async () => {
  const page = await settings({ view: exists(C.two_folders_pc) }, { link: { stale: true } });
  await page.locator("#fo-list button").first().click();
  await page.waitForTimeout(300);
  const got = await calls(page);
  await page.close();
  assert.deepEqual(got, [["remove_folder", { path: "C:\\Users\\owner\\Documents" }]]);
});

await check("Settings: Add is ONE request on a live link, greyed on a stale one", async () => {
  let page = await settings({ view: exists(C.two_folders_pc),
                              addAnswer: { ok: true, waiting: true, message: "Waiting." } });
  await page.locator("#fo-add").click();
  await page.waitForTimeout(300);
  let got = await calls(page);
  await page.close();
  assert.deepEqual(got, [["add_folder", {}]]);
  page = await settings({ view: exists(C.two_folders_pc) }, { link: { stale: true } });
  const held = await page.locator("#fo-add").isDisabled();
  const importHeld = await page.locator("#fo-notion-pick").isDisabled();
  await page.close();
  assert.equal(held, true);
  assert.equal(importHeld, true);
});

await check("Settings: the phone's view offers no Add and says where", async () => {
  const page = await settings({ view: exists(C.two_folders_phone) });
  const held = await page.locator("#fo-add").isDisabled();
  const text = await page.locator("#folders").innerText();
  await page.close();
  assert.equal(held, true);
  assert.ok(text.includes(C.two_folders_phone.phone_add));
});

await check("Settings: bring in a Notion export into a listed folder", async () => {
  const page = await settings({ view: exists(C.two_folders_pc),
                                importAnswer: { ok: true, said: "Brought in 3 files." } });
  const options = await page.locator("#fo-notion-into option").evaluateAll(
    (els) => els.map((e) => e.value));
  await page.locator("#fo-notion-pick").click();
  await page.waitForTimeout(300);
  const got = await calls(page);
  const status = await page.locator("#fo-status").innerText();
  await page.close();
  assert.deepEqual(options, C.two_folders_pc.folders.map((f) => f.path));
  assert.deepEqual(got, [["import_notion", { into: options[0] }]]);
  assert.equal(status, "Brought in 3 files.");
});

await check("Settings: the import shows the PC's REAL counts while it runs", async () => {
  // The PC's own live counts (jarvis_documents.importing(), carried by
  // GET /api/folders as `importing`). The command is held open for 1.5 s so the
  // page's one-second poll has to happen; the numbers are the backend's shape,
  // and the sentence is the page's, built from them.
  const view = exists(C.two_folders_pc);
  view.importing = { files: 4231, of_files: 12340, bytes: 1288490189,
                     of_bytes: 3649638400 };
  const page = await settings({ view, importDelayMs: 1500,
                                importAnswer: { ok: true, said: "Brought in 3 files." } });
  await page.locator("#fo-notion-pick").click();
  await page.waitForTimeout(1200);
  const during = await page.locator("#fo-status").innerText();
  await page.waitForTimeout(1200);
  const after = await page.locator("#fo-status").innerText();
  const polls = await page.evaluate(
    () => window.__calls.filter(([c]) => c === "get_folders").length);
  await page.close();
  assert.ok(during.includes("Unzipping the export:"), during);
  assert.ok(during.includes("4,231 of 12,340 files"), during);
  assert.ok(during.includes("1.2 GB of 3.4 GB"), during);
  assert.equal(after, "Brought in 3 files.");
  assert.ok(polls >= 2, `the page polled ${polls} time(s)`);
  assert.equal(importLine(null), "");
});

await check("Settings: Send a file to your phone… sends ONE request and NO path", async () => {
  // 2026-11-14 (SEND-TO-PHONE-2GB-DESIGN sections 6 and 8). The command takes
  // no argument at all: the owner's pick in the Windows dialog is the only
  // path, so the page must not (and cannot) send one. The recorded call is
  // the assertion.
  const page = await settings({ view: exists(C.two_folders_pc),
    sendAnswer: { ok: true, name: "report.pdf", size: 2411724,
                  said: "Waiting for your yes on this PC." } });
  const label = await page.locator("#fo-send").innerText();
  const note = await page.locator("#fo-send-note").innerText();
  await page.locator("#fo-send").click();
  await page.waitForTimeout(300);
  const got = await calls(page);
  const status = await page.locator("#fo-status").innerText();
  const tone = await page.locator("#fo-status").getAttribute("data-tone");
  await page.close();
  assert.equal(label, SEND_LABEL);
  assert.ok(note.includes("File from your PC"), note);
  assert.ok(note.includes("approval card"), note);
  assert.deepEqual(got, [["prepare_file_for_phone", {}]]);
  assert.equal(status, "Waiting for your yes on this PC.");
  assert.equal(tone, "ok");
});

await check("Settings: Send a file is greyed while it waits, and on a stale link", async () => {
  let page = await settings({ view: exists(C.two_folders_pc), sendDelayMs: 900,
                              sendAnswer: { ok: true, said: "Waiting for your yes on this PC." } });
  await page.locator("#fo-send").click();
  await page.waitForTimeout(250);
  const during = await page.locator("#fo-send").isDisabled();
  await page.waitForTimeout(1000);
  const after = await page.locator("#fo-send").isDisabled();
  await page.close();
  assert.equal(during, true, "the button stayed live while the request was in flight");
  assert.equal(after, false, "the button never came back after the answer");
  page = await settings({ view: exists(C.two_folders_pc) }, { link: { stale: true } });
  const held = await page.locator("#fo-send").isDisabled();
  await page.close();
  assert.equal(held, true, "a stale link left Send a file live");
});

await check("Settings: a refused file is the PC's own sentence; a closed dialog says nothing", async () => {
  let page = await settings({ view: exists(C.two_folders_pc),
    sendAnswer: { ok: false, said: "That file is bigger than 2 GB - pick a smaller one." } });
  await page.locator("#fo-send").click();
  await page.waitForTimeout(300);
  const status = await page.locator("#fo-status").innerText();
  const tone = await page.locator("#fo-status").getAttribute("data-tone");
  await page.close();
  assert.equal(status, "That file is bigger than 2 GB - pick a smaller one.");
  assert.equal(tone, "bad");
  // The owner closed the Windows dialog: nothing was sent, so the line clears.
  page = await settings({ view: exists(C.two_folders_pc), sendAnswer: { cancelled: true } });
  await page.locator("#fo-send").click();
  await page.waitForTimeout(300);
  const cleared = await page.locator("#fo-status").innerText();
  await page.close();
  assert.equal(cleared, "");
});

await check("Settings: a folder name is text, never markup", async () => {
  const v = exists(C.two_folders_pc);
  v.folders[0].name = "<img src=x onerror=alert(1)>";
  const page = await settings({ view: v });
  const imgs = await page.locator("#fo-list img").count();
  const text = await page.locator("#fo-list").innerText();
  await page.close();
  assert.equal(imgs, 0);
  assert.ok(text.includes("<img src=x"));
});

await check("Settings: a PC without it says what to do", async () => {
  const page = await settings(null);
  const state = await page.locator("#fo-state").innerText();
  const hidden = await page.locator("#fo-body").isHidden();
  await page.close();
  assert.equal(state, MISSING);
  assert.equal(hidden, true);
});

await browser.close();
close();

/* ── CONTROL ───────────────────────────────────────────────────────────── */

await check("CONTROL: the five commands sit with the Settings window only", async () => {
  const surfaces = read("src-tauri/permissions/surfaces.toml");
  const start = surfaces.indexOf('identifier = "settings-surface"');
  const settingsSet = surfaces.slice(start, surfaces.indexOf("[[set]]", start + 10));
  const others = surfaces.slice(0, start) + surfaces.slice(start + settingsSet.length);
  for (const c of ["allow-get-folders", "allow-add-folder", "allow-remove-folder",
                   "allow-import-notion", "allow-prepare-file-for-phone"]) {
    assert.ok(settingsSet.includes(`"${c}"`), c);
    assert.ok(!others.includes(`"${c}"`), `${c} is elsewhere too`);
  }
});

await check("CONTROL: the pickers are Rust's, and adding, importing and sending are held on a stale link", async () => {
  const rs = read("src-tauri/src/folders.rs");
  assert.match(rs, /FOS_PICKFOLDERS/);
  assert.match(rs, /pub async fn add_folder[\s\S]{0,200}if stale\(&app\)/);
  assert.match(rs, /pub async fn import_notion[\s\S]{0,260}if stale\(&app\)/);
  assert.match(rs, /pub async fn prepare_file_for_phone[\s\S]{0,220}if stale\(&app\)/);
  assert.match(rs, /fn held_on_stale\(path: &str\) -> bool \{\s*path != REMOVE_PATH/);
  // The send button is the ONE path outside the list, so it must be an
  // OPEN-FILE dialog (FOS_FILEMUSTEXIST), never a folder picker, and the
  // command must take no argument the page could put a path in.
  const armAt = rs.indexOf("What::SendFile => {");
  assert.ok(armAt > 0, "folders.rs has no SendFile dialog arm");
  const arm = rs.slice(armAt, armAt + 1200);
  assert.match(arm, /FOS_FILEMUSTEXIST/);
  assert.ok(!/SetOptions\([^)]*FOS_PICKFOLDERS/.test(arm),
    "the send button opens a folder picker");
  assert.match(rs, /pub async fn prepare_file_for_phone\(app: AppHandle\)/);
  const js = read("src/folders-settings.js");
  assert.ok(!/fs\.|readDir|plugin-fs|dialog\.open/.test(js), "the page opens no files itself");
  // No path is ever handed to the command: one literal call, an empty object.
  assert.match(js, /run\("prepare_file_for_phone", \{\}, /);
  assert.ok(!/prepare_file_for_phone", \{ *path/.test(js), "the page named a path");
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nFolders Jarvis may look in: the PC's words, Remove at once, Add and Send held on a stale link");
