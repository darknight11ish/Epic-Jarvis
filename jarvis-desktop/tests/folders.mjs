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
 * - CONTROL: the four commands sit with the Settings window only, the
 *   pickers are Rust's (the page gets no file system), and adding and
 *   importing are held on a stale link in Rust too.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  actions,
  folderLines,
  MISSING,
  NOT_HERE,
  readFolders,
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
  .filter(([c]) => ["add_folder", "remove_folder", "import_notion"].includes(c)));

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

await check("CONTROL: the four commands sit with the Settings window only", async () => {
  const surfaces = read("src-tauri/permissions/surfaces.toml");
  const start = surfaces.indexOf('identifier = "settings-surface"');
  const settingsSet = surfaces.slice(start, surfaces.indexOf("[[set]]", start + 10));
  const others = surfaces.slice(0, start) + surfaces.slice(start + settingsSet.length);
  for (const c of ["allow-get-folders", "allow-add-folder", "allow-remove-folder",
                   "allow-import-notion"]) {
    assert.ok(settingsSet.includes(`"${c}"`), c);
    assert.ok(!others.includes(`"${c}"`), `${c} is elsewhere too`);
  }
});

await check("CONTROL: the pickers are Rust's, and adding and importing are held on a stale link", async () => {
  const rs = read("src-tauri/src/folders.rs");
  assert.match(rs, /FOS_PICKFOLDERS/);
  assert.match(rs, /pub async fn add_folder[\s\S]{0,200}if stale\(&app\)/);
  assert.match(rs, /pub async fn import_notion[\s\S]{0,260}if stale\(&app\)/);
  assert.match(rs, /fn held_on_stale\(path: &str\) -> bool \{\s*path != REMOVE_PATH/);
  const js = read("src/folders-settings.js");
  assert.ok(!/fs\.|readDir|plugin-fs|dialog\.open/.test(js), "the page opens no files itself");
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nFolders Jarvis may look in: the PC's words, Remove at once, Add held on a stale link");
