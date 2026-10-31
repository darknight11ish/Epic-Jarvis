/**
 * Settings -> "Protected from Jarvis" on the desktop (the owner's request of
 * 2026-10-31; contract `.dsh-scratch/PROTECTED-ITEMS-2026-10-31/CONTRACT.md`;
 * src/protected.js, src/protected-settings.js, src-tauri/src/protected.rs).
 *
 * What must hold:
 * - the PC's words: every entry with its kind and its mode ("Blocked — no
 *   access" / "Read-only"), and a program's Read-only said as "see it, never
 *   act";
 * - adding is the owner's direct act and is ONE request after an explicit
 *   mode choice; the two Windows pickers run in Rust, so the page never gets
 *   a file system of its own;
 * - removing is ONE request, says it asks for a card, and is greyed on a
 *   stale link (rule 4);
 * - refusals are plain sentences, never JSON or a bridge error;
 * - the five commands sit with the Settings window only (surfaces.toml), are
 *   listed in build.rs too, and no raw JSON editing exists.
 *
 * Two halves, like folders.mjs: the plate's reading (src/protected.js) against
 * the contract's own answers, then the Settings page in a real browser.
 * Playwright is loaded on demand; without it the browser half says SKIPPED
 * (never a pass) and CI runs it.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  actions,
  describeAdd,
  KINDS,
  MISSING,
  modeHint,
  modeWords,
  MODE_BLOCKED,
  MODE_READONLY,
  readPick,
  readPrograms,
  readProtection,
  STALE,
  TITLE,
  WAITING_REMOVE,
} from "../src/protected.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CASES = JSON.parse(fs.readFileSync(path.join(HERE, "fixtures", "protection-cases.json"),
  "utf8")).cases;
const body = (name) => CASES[name].body;
const read = (p) => fs.readFileSync(path.join(HERE, "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The words and the reading ───────────────────────────────────────────── */

await check("the list is the PC's: kind, target and mode in its own words", async () => {
  const v = readProtection(body("view_list"));
  assert.equal(v.available, true);
  assert.equal(v.count, 3);
  assert.equal(v.items.length, 3);
  assert.equal(v.items[0].kindWords, KINDS.folder);
  assert.equal(v.items[0].modeWords, MODE_BLOCKED);
  assert.equal(v.items[0].target, "C:\\Users\\pcadmin\\Documents\\Taxes");
  assert.equal(v.items[1].modeWords, MODE_READONLY);
  assert.equal(v.items[2].kindWords, KINDS.program);
  assert.match(v.items[2].modeHint, /See it, never act/);
  assert.ok(v.changeCard.length > 0);
  const empty = readProtection(body("view_empty"));
  assert.deepEqual(empty.items, []);
  assert.equal(empty.count, 0);
});

await check("a PC without it says what to do, and never looks protected", async () => {
  const v = readProtection({ available: false, why: MISSING });
  assert.equal(v.available, false);
  assert.equal(v.why, MISSING);
  assert.deepEqual(v.items, []);
  const none = readProtection(null);
  assert.equal(none.available, false);
  assert.equal(none.why, MISSING);
});

await check("the two modes are the owner's words, and an unknown mode shows as it came", async () => {
  assert.equal(modeWords("blocked"), "Blocked — no access");
  assert.equal(modeWords("readonly"), "Read-only");
  assert.equal(modeWords("weird"), "weird");
  assert.equal(modeHint("blocked", "folder"), "Jarvis cannot read, write, search or open it at all.");
  assert.equal(modeHint("readonly", "program"),
    "See it, never act: Jarvis may read its window, but clicking, typing, opening or closing it is refused.");
});

await check("the running programs are names only, lower-cased, unique and sorted", async () => {
  const got = readPrograms({ ok: true, programs: ["notepad.exe", "Explorer.EXE", "notepad.exe", " cmd.exe "] });
  assert.deepEqual(got.programs, ["cmd.exe", "explorer.exe", "notepad.exe"]);
  assert.deepEqual(readPrograms(null).programs, []);
  assert.deepEqual(readPrograms({ programs: [3, null, "vlc.exe"] }).programs, ["vlc.exe"]);
});

await check("a picker answers a path or a cancelled dialog, never a file system", async () => {
  assert.equal(readPick({ ok: true, path: "C:\\Users\\pcadmin\\Documents\\Taxes" }),
    "C:\\Users\\pcadmin\\Documents\\Taxes");
  assert.equal(readPick({ cancelled: true }), "");
  assert.equal(readPick(null), "");
});

await check("an add says the PC's stored sentence; a refusal never claims it was stored", async () => {
  const good = describeAdd(body("add_ok"));
  assert.equal(good.tone, "ok");
  assert.equal(good.text, body("add_ok").message);
  const bad = describeAdd({ ok: false, error: "That path is relative - choose the whole path." });
  assert.equal(bad.tone, "bad");
  assert.match(bad.text, /relative/);
  assert.doesNotMatch(bad.text, /Protected/);
});

await check("adding is offered even on a stale link; removing is not (rule 4)", async () => {
  const v = readProtection(body("view_list"));
  const live = actions(v, true);
  const stale = actions(v, false);
  assert.equal(live.add, true);
  assert.equal(live.remove, true);
  assert.equal(stale.add, true);
  assert.equal(stale.remove, false);
  assert.equal(stale.removeWhy, STALE);
  const off = actions(readProtection({ available: false, why: MISSING }), true);
  assert.equal(off.add, false);
  assert.equal(off.remove, false);
  assert.equal(off.removeWhy, MISSING);
});

/* ── Wiring pins ────────────────────────────────────────────────────────── */

await check("Settings has the card, the three pickers, the two modes and the status", async () => {
  const html = read("src/settings.html");
  assert.match(html, /<section class="card" id="protection">/);
  assert.match(html, /<h2>Protected from Jarvis<\/h2>/);
  for (const id of ["pr-list", "pr-state", "pr-body", "pr-empty", "pr-add-folder",
                    "pr-add-file", "pr-add-program", "pr-choice", "pr-mode-blocked",
                    "pr-mode-readonly", "pr-add-confirm", "pr-choice-cancel", "pr-status"]) {
    assert.match(html, new RegExp(`id="${id}"`), id);
  }
  assert.match(html, /src="protected-settings\.js"/);
  assert.match(html, /<a href="#protection">Protected from Jarvis<\/a>/);
  // Blocked is the recommended, pre-checked mode.
  assert.match(html, /id="pr-mode-blocked"[^>]*checked/);
});

await check("the page only asks; the pickers and the file system are Rust's", async () => {
  const js = read("src/protected-settings.js");
  assert.match(js, /TAURI\.core\.invoke\("get_protection"\)/);
  assert.match(js, /TAURI\.core\.invoke\("protection_pick", \{ kind \}\)/);
  assert.match(js, /TAURI\.core\.invoke\("protection_programs"\)/);
  assert.match(js, /TAURI\.core\.invoke\("add_protection", \{ kind, target, mode \}\)/);
  assert.match(js, /TAURI\.core\.invoke\("remove_protection", \{ id: entry\.id \}\)/);
  assert.ok(!/fs\.|readDir|plugin-fs|dialog\.open/.test(js), "the page opens no files itself");
  const rs = read("src-tauri/src/protected.rs");
  assert.match(rs, /ProtectFolder/);
  assert.match(rs, /ProtectFile/);
  assert.match(rs, /pub async fn remove_protection[\s\S]{0,260}post\(&app, REMOVE_PATH/);
  assert.match(rs, /fn held_on_stale\(path: &str\) -> bool \{\s*path == REMOVE_PATH/);
  assert.match(rs, /"programs"/);
});

await check("CONTROL: the five commands sit with the Settings window only", async () => {
  const surfaces = read("src-tauri/permissions/surfaces.toml");
  const start = surfaces.indexOf('identifier = "settings-surface"');
  const settingsSet = surfaces.slice(start, surfaces.indexOf("[[set]]", start + 10));
  const others = surfaces.slice(0, start) + surfaces.slice(start + settingsSet.length);
  for (const c of ["allow-get-protection", "allow-protection-pick",
                   "allow-protection-programs", "allow-add-protection",
                   "allow-remove-protection"]) {
    assert.ok(settingsSet.includes(`"${c}"`), c);
    assert.ok(!others.includes(`"${c}"`), `${c} is elsewhere too`);
  }
  const build = read("src-tauri/build.rs");
  for (const c of ["get_protection", "protection_pick", "protection_programs",
                   "add_protection", "remove_protection"]) {
    assert.ok(build.includes(`"${c}"`), `${c} missing from build.rs's ACL export`);
  }
});

await check("the missed-sentence and waiting words are one place", async () => {
  assert.equal(TITLE, "Protected from Jarvis");
  assert.match(WAITING_REMOVE, /approval card/);
  assert.match(MISSING, /apply-patches/);
});

/* ── The Settings page, in a browser ─────────────────────────────────────── */

let K = null;
try {
  await import("playwright");
  K = await import("./uikit.mjs");
} catch {
  console.log("\nSKIPPED  the Settings page in a browser - Playwright is not installed here. "
    + "That half did NOT run and is NOT a pass; CI installs Playwright and runs it.");
}

if (K) {
  const { base, close } = await K.serve();
  const browser = await K.launch();
  const VIEW = { width: 980, height: 3000 };

  /**
   * Opens settings.html with the protection commands answering from the
   * fixture. `view` is the /api/protection body (or a queued array for
   * repeated reads); `add` resolves the POST; `pick` answers the picker;
   * `programs` the running-programs read; `remove` the removal POST. Every
   * other command falls through to uikit's bridge.
   */
  async function settings({ view = "view_list", add = "add_ok", pick = null,
                            programs = null, remove = null, missing = false,
                            data = {} } = {}) {
    const page = await K.open(browser, base, "settings.html", data, VIEW);
    await page.addInitScript(({ viewBody, addBody, pickBody, programsBody, removeBody }) => {
      const inner = window.__TAURI__.core.invoke;
      window.__protectionCalls = [];
      window.__TAURI__.core.invoke = async (cmd, args) => {
        const name = String(cmd);
        if (!name.startsWith("get_protection") && !name.startsWith("protection_")
            && name !== "add_protection" && name !== "remove_protection") {
          return inner(cmd, args);
        }
        window.__protectionCalls.push([name, args]);
        if (name === "get_protection") return viewBody;
        if (name === "protection_pick") return pickBody;
        if (name === "protection_programs") return programsBody;
        if (name === "add_protection") {
          if (addBody && addBody.error) throw new Error(addBody.error);
          return addBody;
        }
        if (name === "remove_protection") return removeBody;
        return null;
      };
    }, {
      viewBody: missing ? { available: false, why: MISSING, items: [] }
        : typeof view === "object" ? view : body(view),
      addBody: typeof add === "string" ? body(add) : add,
      pickBody: pick,
      programsBody: programs,
      removeBody: remove,
    });
    await page.reload();
    await page.waitForTimeout(700);
    return page;
  }

  await check("Settings: every entry, its kind, its mode and Remove", async () => {
    const page = await settings();
    const rows = await page.evaluate(() => [...document.querySelectorAll("#pr-list .sc-gpu")]
      .map((r) => [r.querySelector(".sc-gpu-name").textContent,
                   r.querySelector(".sc-gpu-role").textContent]));
    const text = await page.locator("#pr-list").innerText();
    const remove = await page.locator("#pr-list button").count();
    const errors = page.__errors;
    await page.close();
    assert.equal(rows.length, 3);
    assert.equal(rows[0][0], "C:\\Users\\pcadmin\\Documents\\Taxes");
    assert.match(rows[0][1], /Folder · Blocked — no access/);
    assert.match(rows[1][1], /File · Read-only/);
    assert.match(text, /See it, never act/);
    assert.equal(remove, 3);
    assert.deepEqual(errors, []);
  });

  await check("Settings: Add a folder asks the picker, then the mode, then ONE add", async () => {
    const page = await settings({ pick: { ok: true, path: "C:\\Users\\pcadmin\\Documents\\Taxes" } });
    await page.locator("#pr-add-folder").click();
    await page.waitForFunction(() =>
      document.querySelector("#pr-choice") && !document.querySelector("#pr-choice").hidden,
    null, { timeout: 5000 });
    const target = await page.locator("#pr-choice-target").innerText();
    await page.locator("#pr-mode-readonly").check();
    const hint = await page.locator("#pr-mode-hint").innerText();
    await page.locator("#pr-add-confirm").click();
    await page.waitForFunction(() => /Protected/.test(
      (document.querySelector("#pr-status") || {}).textContent || ""), null, { timeout: 5000 });
    const calls = await page.evaluate(() => window.__protectionCalls);
    await page.close();
    assert.equal(target, "C:\\Users\\pcadmin\\Documents\\Taxes");
    assert.match(hint, /writes|refused/);
    const pick = calls.find((c) => c[0] === "protection_pick");
    assert.deepEqual(pick[1], { kind: "folder" });
    const added = calls.find((c) => c[0] === "add_protection");
    assert.deepEqual(added[1], { kind: "folder", target: "C:\\Users\\pcadmin\\Documents\\Taxes",
                                 mode: "readonly" });
  });

  await check("Settings: Add a file defaults to Blocked (the recommended mode)", async () => {
    const page = await settings({ pick: { ok: true, path: "C:\\Users\\pcadmin\\notes\\budget.md" } });
    await page.locator("#pr-add-file").click();
    await page.waitForFunction(() =>
      document.querySelector("#pr-choice") && !document.querySelector("#pr-choice").hidden,
    null, { timeout: 5000 });
    const blockedChecked = await page.locator("#pr-mode-blocked").isChecked();
    await page.locator("#pr-add-confirm").click();
    await page.waitForFunction(() => /Protected/.test(
      (document.querySelector("#pr-status") || {}).textContent || ""), null, { timeout: 5000 });
    const added = await page.evaluate(() => window.__protectionCalls
      .find((c) => c[0] === "add_protection"));
    await page.close();
    assert.equal(blockedChecked, true);
    assert.deepEqual(added[1], { kind: "file", target: "C:\\Users\\pcadmin\\notes\\budget.md",
                                 mode: "blocked" });
  });

  await check("Settings: Add a program offers the programs running now", async () => {
    const page = await settings({
      programs: { ok: true, programs: ["explorer.exe", "notepad.exe", "vlc.exe"] },
    });
    await page.locator("#pr-add-program").click();
    await page.waitForFunction(() => document.querySelectorAll("#pr-programs button").length === 3,
      null, { timeout: 5000 });
    const names = await page.evaluate(() => [...document.querySelectorAll("#pr-programs button")]
      .map((b) => b.textContent));
    await page.locator("#pr-programs button", { hasText: "notepad.exe" }).click();
    const target = await page.locator("#pr-choice-target").innerText();
    await page.locator("#pr-add-confirm").click();
    await page.waitForFunction(() => /Protected/.test(
      (document.querySelector("#pr-status") || {}).textContent || ""), null, { timeout: 5000 });
    const added = await page.evaluate(() => window.__protectionCalls
      .find((c) => c[0] === "add_protection"));
    await page.close();
    assert.deepEqual(names, ["explorer.exe", "notepad.exe", "vlc.exe"]);
    assert.equal(target, "notepad.exe");
    assert.deepEqual(added[1], { kind: "program", target: "notepad.exe", mode: "blocked" });
  });

  await check("Settings: a refused add is a plain sentence and claims nothing", async () => {
    const page = await settings({
      pick: { ok: true, path: "relative\\notes" },
      add: { error: "That path is relative - choose the whole path, starting with the drive." },
    });
    await page.locator("#pr-add-folder").click();
    await page.waitForFunction(() =>
      document.querySelector("#pr-choice") && !document.querySelector("#pr-choice").hidden,
    null, { timeout: 5000 });
    await page.locator("#pr-add-confirm").click();
    await page.waitForFunction(() => /relative/.test(
      (document.querySelector("#pr-status") || {}).textContent || ""), null, { timeout: 5000 });
    const status = await page.locator("#pr-status").innerText();
    const tone = await page.locator("#pr-status").getAttribute("data-tone");
    await page.close();
    assert.match(status, /relative/);
    assert.equal(tone, "bad");
  });

  await check("Settings: Remove asks the PC for one card and says it is waiting", async () => {
    const page = await settings({ remove: { ok: true, state: "waiting", id: "prot-remove-1" } });
    await page.locator("#pr-list button").first().click();
    await page.waitForFunction(() => /approval card/.test(
      (document.querySelector("#pr-status") || {}).textContent || ""), null, { timeout: 5000 });
    const calls = await page.evaluate(() => window.__protectionCalls);
    const rows = await page.locator("#pr-list .sc-gpu").count();
    await page.close();
    const removed = calls.find((c) => c[0] === "remove_protection");
    assert.deepEqual(removed[1], { id: "prot_ab12cd34" });
    assert.equal(rows, 3, "the entry vanished before the card was answered");
  });

  await check("Settings: a stale link greys Remove, and only Remove", async () => {
    const page = await settings({ data: { link: { stale: true } } });
    const remove = await page.locator("#pr-list button").first().isDisabled();
    const add = await page.locator("#pr-add-folder").isDisabled();
    await page.close();
    assert.equal(remove, true);
    assert.equal(add, false);
  });

  await check("Settings: a PC without it says what to do", async () => {
    const page = await settings({ missing: true });
    const state = await page.locator("#pr-state").innerText();
    const hidden = await page.locator("#pr-body").isHidden();
    await page.close();
    assert.equal(state, MISSING);
    assert.equal(hidden, true);
  });

  await check("Settings: a protected path is text, never markup", async () => {
    const nasty = "C:\\Users\\pcadmin\\<img src=x onerror=alert(1)>";
    const view = JSON.parse(JSON.stringify(body("view_list")));
    view.items[0].target = nasty;
    const page = await settings({ view });
    const imgs = await page.locator("#pr-list img").count();
    const text = await page.locator("#pr-list").innerText();
    await page.close();
    assert.equal(imgs, 0);
    assert.ok(text.includes("<img src=x"), "the target was not drawn as text");
  });

  await browser.close();
  close();
}

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nProtected from Jarvis: the PC's list and words, one explicit mode, Remove asks for a card");
process.exit(fails.length ? 1 : 0);
