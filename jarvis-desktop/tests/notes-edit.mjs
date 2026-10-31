/**
 * The notes editor's plate in the Brain window - the whole Obsidian vault,
 * both apps (contract 2026-10-31: `.dsh-scratch/NOTES-EDITOR-2026-10-31/CONTRACT.md`).
 *
 * Two halves, like wiki.mjs: the plate's logic (src/notes.js) against the
 * contract's own answers, then the Brain window in a real browser with the
 * bridge from uikit.mjs and the four notes commands answering from the same
 * fixture. The fixture is `tests/fixtures/notes-edit-cases.json` - shared by
 * this file and the Rust reading tests next to the commands, so the two
 * halves cannot drift.
 *
 * What is NOT claimed here: that the PC writes anything. The card, the File
 * Guardian snapshot and the hash check are the backend lane's routes; this
 * file proves the desktop asks, follows the card, and never writes on its own.
 *
 * The browser half needs Playwright (`npm i -D playwright && npx playwright
 * install chromium`); CI installs it for the frontend job. Without it the
 * logic half still runs and the browser half says SKIPPED, which is not a
 * pass.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describeSave, readNote, readNotesList, saveNote } from "../src/notes.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CASES = JSON.parse(fs.readFileSync(path.join(HERE, "fixtures", "notes-edit-cases.json"),
  "utf8")).cases;
const body = (name) => CASES[name].body;
/** The src folder, read as text for the wiring pins below. */
const src = (name) => fs.readFileSync(path.join(HERE, "..", "src", name), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The plate's logic, against the contract's real answers ─────────────── */

await check("the list answer is read as the PC sent it, and never carries text", async () => {
  const v = readNotesList(body("list_ok"));
  assert.equal(v.root, "C:\\Users\\owner\\Vault");
  assert.equal(v.count, 2);
  assert.equal(v.truncated, false);
  assert.deepEqual(v.notes.map((n) => [n.path, n.title, n.size]), [
    ["Inbox/idea.md", "idea", 812],
    ["Projects/plan.txt", "plan", 12],
  ]);
  const empty = readNotesList(body("list_empty"));
  assert.deepEqual(empty.notes, []);
  const cut = readNotesList(body("list_truncated"));
  assert.equal(cut.truncated, true);
  const weird = readNotesList(null);
  assert.deepEqual(weird.notes, []);
  assert.equal(weird.count, 0);
});

await check("the read answer keeps the hash a save is checked against", async () => {
  const note = readNote(body("read_ok"));
  assert.equal(note.path, "Inbox/idea.md");
  assert.match(note.text, /notes editor/);
  assert.equal(note.sha256.length, 64);
  assert.equal(note.size, 812);
  const none = readNote({});
  assert.equal(none.text, "");
  assert.equal(none.sha256, "");
});

await check("waiting is not a finish; only saved reads as written", async () => {
  const waiting = describeSave(body("save_waiting"));
  assert.equal(waiting.state, "waiting");
  assert.equal(waiting.final, false);
  assert.equal(waiting.tone, null);
  assert.match(waiting.text, /Waiting for your approval/);

  const statusWaiting = describeSave(body("status_waiting"));
  assert.equal(statusWaiting.final, false);
  assert.equal(statusWaiting.text, body("status_waiting").message);

  const saved = describeSave(body("status_saved"));
  assert.equal(saved.final, true);
  assert.equal(saved.tone, "ok");
  assert.equal(saved.text, body("status_saved").message);

  for (const name of ["status_denied", "status_failed"]) {
    const d = describeSave(body(name));
    assert.equal(d.final, true, name);
    assert.equal(d.tone, "bad", name);
    assert.equal(d.text, body(name).message, name);
  }
});

await check("a conflict is final, keeps the current hash in the sentence, and claims no write", async () => {
  const d = describeSave(body("save_conflict"));
  assert.equal(d.state, "conflict");
  assert.equal(d.final, true);
  assert.equal(d.tone, "bad");
  assert.match(d.text, /nothing was overwritten/i);
  assert.match(d.text, /aaaaaaaaaaaa/);
  // Its own sentence is preferred when the PC sends one.
  const withWords = describeSave({ state: "conflict", message: "The note moved on. Nothing saved." });
  assert.equal(withWords.text, "The note moved on. Nothing saved.");
});

await check("every unknown state reads as not written, never as saved", async () => {
  for (const state of ["", undefined, "weird", "waiting-ish"]) {
    const d = describeSave({ state });
    assert.equal(d.final, true, String(state));
    assert.equal(d.tone, "bad", String(state));
    assert.doesNotMatch(d.text, /Saved/, String(state));
  }
});

await check("a save is followed: ask, then each status poll, then the last answer", async () => {
  const answers = [body("save_waiting"), body("status_waiting"), body("status_saved")];
  const calls = [];
  const invoke = async (cmd, args) => {
    calls.push([cmd, args]);
    return answers.shift();
  };
  const seen = [];
  const last = await saveNote(invoke,
    { path: "Inbox/idea.md", text: "new words", expectedSha256: "abc" },
    (d) => seen.push(d), { pollMs: 1 });
  assert.deepEqual(calls.map((c) => c[0]),
    ["notes_save", "notes_save_status", "notes_save_status"]);
  assert.deepEqual(calls[0][1], { path: "Inbox/idea.md", text: "new words", expectedSha256: "abc" });
  assert.deepEqual(calls[1][1], { id: body("save_waiting").id });
  assert.equal(last.state, "saved");
  assert.equal(last.tone, "ok");
  assert.match(seen[1].text, /Approve the card|Waiting for your approval/);
  assert.equal(seen[1].final, false);
});

await check("one or two failed polls are retried; the follow goes on to the end", async () => {
  const answers = [body("save_waiting"), new Error("timed out"), new Error("timed out"),
                   body("status_waiting"), new Error("reset"), body("status_saved")];
  const calls = [];
  const invoke = async (cmd) => {
    calls.push(cmd);
    const next = answers.shift();
    if (next instanceof Error) throw next;
    return next;
  };
  const seen = [];
  const last = await saveNote(invoke, { path: "x.md", text: "t", expectedSha256: "h" },
    (d) => seen.push(d), { pollMs: 1 });
  assert.equal(calls.length, 6, JSON.stringify(calls));
  assert.equal(last.state, "saved", last.text);
  const retry = seen.find((d) => /Trying again/.test(d.text));
  assert.ok(retry && retry.final === false && retry.tone !== "bad", JSON.stringify(seen));
});

await check("CONTROL: three failed polls in a row do end it, and never claim a save", async () => {
  const answers = [body("save_waiting"), new Error("a"), new Error("b"), new Error("c"),
                   body("status_saved")];
  const invoke = async () => {
    const next = answers.shift();
    if (next instanceof Error) throw next;
    return next;
  };
  const last = await saveNote(invoke, { path: "x.md", text: "t", expectedSha256: "h" },
    () => {}, { pollMs: 1 });
  assert.equal(last.final, true);
  assert.equal(last.tone, "bad");
  assert.match(last.text, /Lost track of the save/);
  assert.equal(answers.length, 1, "it kept polling after the third failure");
});

await check("while the link is down no poll is sent, nothing is counted, and the follow resumes", async () => {
  const answers = [body("save_waiting"), body("status_waiting"), body("status_saved")];
  const calls = [];
  const invoke = async (cmd) => { calls.push(cmd); return answers.shift(); };
  let ticks = 0;
  const linkDown = () => ++ticks <= 10;
  const seen = [];
  const last = await saveNote(invoke, { path: "x.md", text: "t", expectedSha256: "h" },
    (d) => seen.push(d), { pollMs: 1, linkDown });
  assert.deepEqual(calls, ["notes_save", "notes_save_status", "notes_save_status"],
    "a poll was sent while the link was down");
  assert.equal(last.state, "saved");
  assert.equal(seen.filter((d) => /link to the PC/.test(d.text)).length, 1);
});

await check("giving up says the card is still waiting, not that it was written", async () => {
  const answers = [body("save_waiting"), body("status_waiting")];
  const invoke = async () => (answers.length > 1 ? answers.shift() : answers[0]);
  const last = await saveNote(invoke, { path: "x.md", text: "t", expectedSha256: "h" },
    () => {}, { pollMs: 1, giveUpMs: 5 });
  assert.match(last.text, /Nothing is written until|Still waiting/);
  assert.notEqual(last.tone, "ok");
});

/* ── Wiring pins: the page asks, and never approves ─────────────────────── */

await check("the Brain has the Notes card and the search box outside the repainted plate", async () => {
  const html = src("brain.html");
  assert.match(html, /id="notes-card"/);
  assert.match(html, /id="notes-search"[^>]*type="search"/);
  assert.match(html, /id="notes"><\/div>/);
  // The plate is drawn by notes.js, and the card sits beside the wiki one.
  assert.ok(html.indexOf('id="notes-card"') > html.indexOf('id="wiki-card"'));
});

await check("brain.js reads and saves through the notes commands, and re-reads after a save", async () => {
  const js = src("brain.js");
  assert.match(js, /from "\.\/notes\.js"/);
  assert.match(js, /invoke\("notes_list"/);
  assert.match(js, /invoke\("notes_read"/);
  assert.match(js, /saveNote\(invoke/);
  assert.match(js, /renderNotesPlate\(\);/);
  // A repaint must not put the old words back over a draft being saved.
  assert.match(js, /notes\.open = \{ \.\.\.open, text: box\.value \}/);
  // The card is followed with the link state, exactly like the wiki's.
  assert.match(js, /linkDown: \(\) => !currentLink\(\)\.connected/);
});

await check("notes.js has no way to decide an approval: the page only asks", async () => {
  const js = src("notes.js");
  assert.doesNotMatch(js, /decide_approval/);
  assert.doesNotMatch(js, /approve_approval/);
  assert.doesNotMatch(js, /invoke\("(decide|approve)/);
  // The card's words come from jarvis-link.js's one list.
  assert.match(js, /APPROVE_WHERE/);
});

/* ── The Brain window, in a browser ─────────────────────────────────────── */

let K = null;
try {
  await import("playwright");
  K = await import("./uikit.mjs");
} catch {
  console.log("\nSKIPPED  the Brain in a browser - Playwright is not installed here. "
    + "That half did NOT run and is NOT a pass; CI installs Playwright and runs it.");
}

if (K) {
  const { base, close } = await K.serve();
  const browser = await K.launch();
  const SIZE = { width: 1180, height: 1400 };

  /**
   * Opens brain.html with the four notes commands answering from the fixture.
   * `readBodies` is the /api/notes/read queue (the first read, then any
   * re-read); `statusBodies` the save-status queue; `saveBody` the POST answer.
   * Registered after uikit's bridge and applied by a reload, so uikit.mjs is
   * untouched.
   */
  async function brain({ data = {}, saveBody = "save_waiting", readBodies = ["read_ok"],
                         statusBodies = [], listBody = "list_ok" } = {}) {
    const page = await K.open(browser, base, "brain.html", data, SIZE);
    await page.addInitScript(({ list, reads, save, statuses }) => {
      const inner = window.__TAURI__.core.invoke;
      const readQueue = [...reads];
      const statusQueue = [...statuses];
      window.__notesCalls = [];
      window.__TAURI__.core.invoke = async (cmd, args) => {
        if (!String(cmd).startsWith("notes_")) return inner(cmd, args);
        window.__notesCalls.push([cmd, args]);
        if (cmd === "notes_list") return list;
        if (cmd === "notes_read") return readQueue.length > 1 ? readQueue.shift() : readQueue[0];
        if (cmd === "notes_save") return save;
        return statusQueue.length > 1 ? statusQueue.shift() : statusQueue[0];
      };
    }, {
      list: body(listBody),
      reads: readBodies.map(body),
      save: body(saveBody),
      statuses: statusBodies.map(body),
    });
    await page.reload();
    await page.waitForTimeout(600);
    return page;
  }

  await check("the plate lists every note the PC sent, with the vault path and the truncation note", async () => {
    const page = await brain();
    const rows = await page.evaluate(() => [...document.querySelectorAll("#notes .row-item")]
      .map((r) => [r.querySelector(".row-title").textContent,
                   r.querySelector(".row-meta")?.textContent]));
    const root = await page.locator("#notes .notes-root").innerText();
    await page.close();
    assert.deepEqual(rows.map((r) => r[0]), ["idea", "plan"]);
    assert.match(rows[0][1], /Inbox\/idea\.md/);
    assert.match(root, /Vault: C:\\Users\\owner\\Vault/);
  });

  await check("the truncated list says it stops at 2,000", async () => {
    const page = await brain({ listBody: "list_truncated" });
    const text = await page.locator("#notes .notes-truncated").innerText();
    await page.close();
    assert.match(text, /2,000 notes/);
  });

  await check("opening a note reads it from the PC and puts its words in the box", async () => {
    const page = await brain();
    await page.locator("#notes .row-item", { hasText: "Inbox/idea.md" })
      .getByRole("button", { name: "Open" }).click();
    await page.waitForFunction(() => Boolean(document.querySelector("#notes-text")), null,
      { timeout: 8000 });
    const text = await page.locator("#notes-text").inputValue();
    const path_ = await page.locator("#notes .notes-path").innerText();
    const meta = await page.locator("#notes .notes-meta").innerText();
    const calls = await page.evaluate(() => window.__notesCalls.map((c) => c[0]));
    await page.close();
    assert.match(text, /notes editor/);
    assert.equal(path_, "Inbox/idea.md");
    assert.match(meta, /812 B/);
    assert.match(meta, /0123456789ab/);
    assert.ok(calls.includes("notes_read"), "notes_read was not called");
  });

  await check("Save raises the card, says waiting, then saved in the PC's words and re-reads", async () => {
    const page = await brain({
      readBodies: ["read_ok", "read_saved"],
      statusBodies: ["status_waiting", "status_saved"],
    });
    await page.locator("#notes .row-item", { hasText: "Inbox/idea.md" })
      .getByRole("button", { name: "Open" }).click();
    await page.waitForFunction(() => Boolean(document.querySelector("#notes-text")), null,
      { timeout: 8000 });
    await page.locator("#notes-text").fill("# idea\n\nA small idea. Edited and saved.");
    await page.locator("#notes").getByRole("button", { name: "Save", exact: true }).click();
    await page.waitForFunction(() => /Saved Inbox\/idea\.md/.test(
      (document.querySelector("#notes .notes-job") || {}).textContent || ""), null,
      { timeout: 20000 });
    const after = await page.locator("#notes-text").inputValue();
    const job = await page.locator("#notes .notes-job").innerText();
    const tone = await page.locator("#notes .notes-job").getAttribute("data-tone");
    const calls = await page.evaluate(() => window.__notesCalls);
    await page.close();
    assert.match(job, /Saved Inbox\/idea\.md/);
    assert.equal(tone, "ok");
    assert.match(after, /Edited and saved/);
    const save = calls.find((c) => c[0] === "notes_save");
    assert.equal(save[1].path, "Inbox/idea.md");
    assert.equal(save[1].expectedSha256,
      "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef");
    assert.match(save[1].text, /Edited and saved/);
    assert.equal(calls.filter((c) => c[0] === "notes_read").length, 2,
      "the note was not re-read after the save");
    assert.equal(calls.filter((c) => c[0] === "notes_list").length, 2,
      "the list was not re-read after the save");
  });

  await check("a denied card says so and the note keeps the owner's words, not the file's", async () => {
    const page = await brain({ statusBodies: ["status_denied"] });
    await page.locator("#notes .row-item", { hasText: "Inbox/idea.md" })
      .getByRole("button", { name: "Open" }).click();
    await page.waitForFunction(() => Boolean(document.querySelector("#notes-text")), null,
      { timeout: 8000 });
    await page.locator("#notes-text").fill("# idea\n\nWords the owner typed.");
    await page.locator("#notes").getByRole("button", { name: "Save", exact: true }).click();
    await page.waitForFunction(() => /said no|nothing was written/i.test(
      (document.querySelector("#notes .notes-job") || {}).textContent || ""), null,
      { timeout: 20000 });
    const after = await page.locator("#notes-text").inputValue();
    const job = await page.locator("#notes .notes-job").innerText();
    await page.close();
    assert.match(job, /You said no, so nothing was written\./);
    assert.match(after, /Words the owner typed/);
  });

  await check("a conflict says nothing was overwritten and keeps the draft in the box", async () => {
    const page = await brain({ saveBody: "save_conflict" });
    await page.locator("#notes .row-item", { hasText: "Inbox/idea.md" })
      .getByRole("button", { name: "Open" }).click();
    await page.waitForFunction(() => Boolean(document.querySelector("#notes-text")), null,
      { timeout: 8000 });
    await page.locator("#notes-text").fill("# idea\n\nMy words that must survive.");
    await page.locator("#notes").getByRole("button", { name: "Save", exact: true }).click();
    await page.waitForFunction(() => /nothing was overwritten/i.test(
      (document.querySelector("#notes .notes-job") || {}).textContent || ""), null,
      { timeout: 8000 });
    const after = await page.locator("#notes-text").inputValue();
    const calls = await page.evaluate(() => window.__notesCalls.map((c) => c[0]));
    await page.close();
    assert.match(after, /My words that must survive/);
    assert.equal(calls.filter((c) => c === "notes_read").length, 1,
      "a conflict must not re-read the note over the draft");
  });

  await check("the search box asks the PC with its words, after a short rest", async () => {
    const page = await brain();
    await page.locator("#notes-search").fill("idea");
    await page.waitForFunction(() => window.__notesCalls.some(
      (c) => c[0] === "notes_list" && c[1] && c[1].q === "idea"), null, { timeout: 5000 });
    const calls = await page.evaluate(() => window.__notesCalls
      .filter((c) => c[0] === "notes_list").map((c) => c[1]));
    await page.close();
    assert.ok(calls.some((a) => a && a.q === "idea"), JSON.stringify(calls));
  });

  await check("a stale link greys Save (rule 4)", async () => {
    const page = await brain({ data: { link: { stale: true } } });
    await page.locator("#notes .row-item", { hasText: "Inbox/idea.md" })
      .getByRole("button", { name: "Open" }).click();
    await page.waitForFunction(() => Boolean(document.querySelector("#notes-text")), null,
      { timeout: 8000 });
    const disabled = await page.locator("#notes").getByRole("button", { name: "Save", exact: true }).isDisabled();
    await page.close();
    assert.equal(disabled, true);
  });

  await browser.close();
  close();
}

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nthe notes plate asks, follows the card, and only a saved note is read back");
process.exit(fails.length ? 1 : 0);
