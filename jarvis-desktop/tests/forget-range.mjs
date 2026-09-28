/**
 * Brain -> History -> "Forget a time frame" on the desktop (the owner's
 * decision of 2026-09-28; JARVIS-API.md section 64; src/forget-range.js,
 * src/forget-range-panel.js, src/forget-range.css,
 * src-tauri/src/brain/forget_range.rs).
 *
 * What must hold:
 * - the words are the PC's and the phone's, word for word (the contract
 *   file's `words`, made by tools/gen_forget_range_cases.py, and
 *   net/ForgetRange.kt);
 * - every real answer reads (fixtures/forget-range-cases.json);
 * - the page: the days, the ticked list, unticking, "Forget these" sends
 *   ONLY the ticked ids once (the PC raises the card - nothing here
 *   approves), the waiting line, the Undo banner and Undo;
 * - a stale link greys "Forget these" but never Undo;
 * - hidden with the private lists (counts only, Show);
 * - "forget what you learned last week" in the Jarvis bar opens the Brain
 *   here, with the days filled in (main.js -> brain.js);
 * - CONTROL: the two commands are the Brain's alone; Rust holds "forget" on
 *   a stale link and refuses it while the list is hidden; Undo is never held;
 * - a11y: every control has a name, the status line is a live region.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  allTicked,
  BRAIN_PLACE_KEY,
  forgetBody,
  forgetLabel,
  PLACE,
  PRESETS,
  readPreview,
  readStatus,
  undoLine,
  WORDS,
} from "../src/forget-range.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const readRepo = (p) => readFileSync(join(HERE, "..", "..", p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/forget-range-cases.json"));
const C = CASES.cases;

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

await check("the words are the contract's and the phone's, word for word", async () => {
  assert.deepEqual({ ...WORDS }, CASES.words);
  assert.deepEqual(PRESETS, CASES.presets);
  const kt = readRepo("jarvis-client/app/src/main/java/com/jarvis/client/net/ForgetRange.kt")
    .replace(/"\s*\+\s*\n\s*"/g, "");
  for (const [key, words] of Object.entries(CASES.words)) {
    assert.ok(kt.includes(`"${key}" to "${words.replace(/"/g, "\\\"")}"`),
      `the phone does not say ${key}: ${words}`);
  }
  assert.ok(read("src-tauri/src/brain/forget_range.rs").includes(`"${WORDS.missing}"`));
  const html = read("src/brain.html");
  assert.ok(html.includes(`<h2>${WORDS.title}</h2>`));
  assert.ok(html.includes(WORDS.under), "the card's note is not the shared words");
});

await check("every real answer reads", async () => {
  const fresh = readStatus(C.status_fresh.body);
  assert.equal(fresh.available, true);
  assert.equal(fresh.waiting, false);
  assert.equal(fresh.undo, null);
  assert.equal(fresh.maxItems, 200);
  assert.deepEqual(fresh.presets.map((p) => p.id), PRESETS.map((p) => p.id));
  assert.equal(readStatus(C.status_waiting.body).waiting, true);
  const undo = readStatus(C.status_undo.body).undo;
  assert.equal(undo.facts, 2);
  assert.equal(undo.chats, 2);
  assert.equal(undo.minutesLeft, 10);
  assert.equal(undoLine(undo),
    "Forgot 2 facts and deleted 2 chats from 1 to 15 September 2026. 10 min left to undo.");
  const asked = readStatus(C.status_asked.body).asked;
  assert.deepEqual([asked.from, asked.to, asked.kinds], ["2026-09-01", "2026-09-15", ["facts"]]);
  assert.equal(readStatus(C.status_denied.body).last.message, "Nothing was forgotten - you said no.");
  assert.equal(readStatus({ available: false, why: WORDS.missing }).why, WORDS.missing);
  assert.equal(readStatus(null).available, false);

  const p = readPreview(C.preview.body);
  assert.equal(p.frame.said, "1 to 15 September 2026");
  assert.deepEqual(p.facts.map((f) => f.text),
    ["The owner moved to Leeds in 2019", "The owner's sister likes jazz"]);
  assert.equal(p.facts[1].pinned, true);
  assert.equal(p.facts[1].betweenUs, true);
  assert.deepEqual(p.chats.map((c) => [c.title, c.spills]),
    [["Help me write a poem", true], ["Plan the trip to Rome", false]]);
  const many = readPreview(C.preview_too_many.body);
  assert.equal(many.tooMany, true);
  assert.equal(many.facts.length, 0);
  assert.equal(readPreview(C.preview_empty.body).empty, true);

  const ticked = allTicked(p);
  ticked.delete(`fact:${p.facts[0].id}`);
  ticked.delete("chat:conv-poem-00002");
  assert.deepEqual(forgetBody(p, ticked), { from: "2026-09-01", to: "2026-09-15",
    facts: [p.facts[1].id], chats: ["conv-trip-00001"] });
  assert.equal(forgetLabel(2), "Forget these (2)");
});

await check("CONTROL: the Brain's two commands; forget held and hidden-refused in Rust, Undo never", async () => {
  const rs = read("src-tauri/src/brain/forget_range.rs");
  const fn = (name) => {
    const f = rs.slice(rs.indexOf(`pub async fn ${name}(`));
    return f.slice(0, f.indexOf("\n}\n"));
  };
  const w = fn("forget_range_write");
  const forgetArm = w.slice(w.indexOf('"forget" =>'), w.indexOf('"undo" =>'));
  assert.match(forgetArm, /words_hidden\(&app\)[\s\S]*STILL_HIDDEN/);
  assert.match(forgetArm, /stale\(&app\)[\s\S]*STALE/);
  const undoArm = w.slice(w.indexOf('"undo" =>'), w.indexOf("other =>"));
  assert.doesNotMatch(undoArm, /stale|hidden/, "Undo is held or refused");
  assert.match(fn("forget_range_read"), /words_hidden\(&app\)[\s\S]*redact\(answer\)/);
  for (const cmd of ["forget_range_read", "forget_range_write"]) {
    assert.match(read("src-tauri/build.rs"), new RegExp(`"${cmd}"`));
    assert.match(read("src-tauri/src/lib.rs"), new RegExp(`brain::forget_range::${cmd},`));
  }
  const sets = read("src-tauri/permissions/surfaces.toml").split("[[set]]").slice(1);
  const holders = (cmd) => sets.filter((s) => s.includes(`"allow-${cmd.replace(/_/g, "-")}"`))
    .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
  for (const cmd of ["forget_range_read", "forget_range_write"]) {
    assert.deepEqual(holders(cmd), ["brain-forget-range"], cmd);
  }
  const caps = (win) => JSON.parse(read(`src-tauri/capabilities/${win}.json`)).permissions;
  assert.ok(caps("brain").includes("brain-forget-range"));
  for (const other of ["quickbar", "hud", "settings", "faces", "floating", "onboarding", "widget"]) {
    assert.ok(!caps(other).includes("brain-forget-range"), `${other} holds brain-forget-range`);
  }
  const panel = read("src/forget-range-panel.js");
  for (const never of ["speak_reply", "speak(", "innerHTML"]) {
    assert.ok(!panel.includes(never), `forget-range-panel.js mentions ${never}`);
  }
  assert.doesNotMatch(panel, /invoke\("(approve|deny|decide|resolve)/, "the page answers a card");
  // The Jarvis bar hands the place on, and only this one place.
  const main = read("src/main.js");
  assert.match(main, /route\.open_brain !== FORGET_RANGE_PLACE/);
  assert.match(main, /localStorage\.setItem\(BRAIN_PLACE_KEY/);
  assert.match(read("src-tauri/src/commands.rs"), /"open_brain",/);
  assert.equal(PLACE, "forget-range");
});

/* ── The window ───────────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 1100 };

/**
 * The Brain with a stand-in for brain/forget_range.rs: reads from the
 * contract file, each write written down in `window.__fr.calls` and
 * answered with the real backend's answer.
 */
async function historyTab({ status = C.status_fresh.body, preview = C.preview.body, link = {},
  forget = C.forget_waiting, afterForget = C.status_waiting.body, undo = C.undo,
  afterUndo = C.status_after_undo.body, hidden = false, place = false } = {}) {
  const page = await K.open(browser, base, "brain.html", { link }, SIZE);
  await page.evaluate(({ status, preview, forget, afterForget, undo, afterUndo, hidden }) => {
    const install = () => {
      const core = window.__TAURI__.core;
      const inner = core.invoke;
      window.__fr = { status, preview, calls: [], hidden, revealed: false };
      core.invoke = async (cmd, args) => {
        const fr = window.__fr;
        if (cmd === "reveal_private_answers") {
          fr.revealed = true;
          fr.hidden = false;
          return null;
        }
        if (cmd === "forget_range_read") {
          fr.calls.push([cmd, JSON.parse(JSON.stringify(args || {}))]);
          if (!args || !args.preview) return fr.status;
          if (fr.hidden) return { ...fr.preview, facts: [], chats: [], hidden: true };
          return fr.preview;
        }
        if (cmd === "forget_range_write") {
          fr.calls.push([cmd, JSON.parse(JSON.stringify(args || {}))]);
          const a = args.action === "undo" ? undo : forget;
          if (a.status >= 400) {
            const e = String(a.body.error || "");
            throw e.charAt(0).toUpperCase() + e.slice(1);
          }
          fr.status = args.action === "undo" ? afterUndo : afterForget;
          return { ...a.body, http: a.status };
        }
        return inner(cmd, args);
      };
    };
    install();
  }, { status, preview, forget, afterForget, undo, afterUndo, hidden });
  if (place) {
    // What main.js leaves after "forget what you learned last week", then
    // the Brain window coming forward (Rust's open_fix_place focuses it).
    await page.evaluate(([key, place]) => {
      localStorage.setItem(key, JSON.stringify({ place, at: Date.now() }));
      window.dispatchEvent(new Event("focus"));
    }, [BRAIN_PLACE_KEY, PLACE]);
  } else {
    await page.locator("#tab-history").click();
  }
  await page.waitForTimeout(500);
  return page;
}

const calls = (page) => page.evaluate(() => window.__fr.calls.filter(([c]) => c === "forget_range_write"));
const showList = async (page) => {
  await page.locator("#forget-range-show").click();
  await page.waitForTimeout(300);
};

await check("the days, the ticked list, unticking, and ONE forget with only the ticked ids", async () => {
  const page = await historyTab();
  const choice = await page.locator("#forget-range-choice").inputValue();
  const options = await page.locator("#forget-range-choice option").allInnerTexts();
  await showList(page);
  const reads = await page.evaluate(() => window.__fr.calls.filter(([c, a]) => a.preview));
  const text = await page.locator("#forget-range").innerText();
  const boxes = await page.locator("#forget-range .fr-item input").evaluateAll(
    (els) => els.map((e) => [e.dataset.key, e.checked]));
  const label0 = await page.locator("#forget-range-go").innerText();
  await page.locator("#forget-range .fr-item", { hasText: "Leeds" }).locator("input").uncheck();
  // Reading the list again keeps what was unticked.
  await showList(page);
  const stillOff = await page.locator("#forget-range .fr-item", { hasText: "Leeds" })
    .locator("input").isChecked();
  assert.equal(stillOff, false, "reading the list again ticked an unticked fact");
  const label1 = await page.locator("#forget-range-go").innerText();
  await page.locator("#forget-range-go").click();
  await page.waitForTimeout(500);
  const sent = await calls(page);
  const after = await page.locator("#forget-range").innerText();
  const errors = page.__errors;
  await page.close();
  assert.equal(choice, "last_week");
  assert.deepEqual(options, [...PRESETS.map((p) => p.label), WORDS.custom]);
  assert.deepEqual(reads[0][1], { preview: true, preset: "last_week", kinds: ["facts", "chats"] });
  assert.match(text, /2 facts and 2 chats from 1 to 15 September 2026\./);
  assert.match(text, new RegExp(`${WORDS.facts_head} \\(2\\)`));
  assert.match(text, /The owner moved to Leeds in 2019/);
  assert.match(text, /Saved 3 September/);
  assert.match(text, new RegExp(`${WORDS.pinned} · ${WORDS.between_us}`));
  assert.match(text, /Help me write a poem/);
  assert.ok(text.includes(WORDS.spills), "a chat that spills outside the days is not marked");
  assert.ok(text.includes(WORDS.erase_note));
  assert.ok(boxes.every(([, on]) => on), "not everything starts ticked");
  assert.equal(boxes.length, 4);
  assert.equal(label0, "Forget these (4)");
  assert.equal(label1, "Forget these (3)");
  const leeds = C.preview.body.facts[0].id;
  const jazz = C.preview.body.facts[1].id;
  assert.ok(boxes.some(([k]) => k === `fact:${leeds}`));
  assert.deepEqual(sent, [["forget_range_write", { action: "forget", body: {
    from: "2026-09-01", to: "2026-09-15", facts: [jazz],
    chats: ["conv-poem-00002", "conv-trip-00001"] } }]]);
  assert.ok(after.includes(WORDS.waiting), "the waiting line is not shown");
  assert.match(after, /Waiting for your approval\. Nothing is forgotten or deleted/);
  assert.deepEqual(errors, []);
});

await check("Undo: the banner says what was done and what is left, one tap, no card", async () => {
  const page = await historyTab({ status: C.status_undo.body });
  const banner = await page.locator(".fr-undo").innerText();
  await page.locator("#forget-range-undo").click();
  await page.waitForTimeout(400);
  const sent = await calls(page);
  const said = await page.locator("#forget-range-said").innerText();
  const gone = await page.locator(".fr-undo").count();
  await page.close();
  assert.match(banner, /Forgot 2 facts and deleted 2 chats from 1 to 15 September 2026\. 10 min left to undo\./);
  assert.deepEqual(sent, [["forget_range_write", { action: "undo" }]]);
  assert.equal(said, "Put back: 2 facts and 2 chats.");
  assert.equal(gone, 0);
});

await check("a stale link greys Forget these, never Undo", async () => {
  const page = await historyTab({ status: C.status_fresh.body, link: { stale: true } });
  await showList(page);
  const goDisabled = await page.locator("#forget-range-go").isDisabled();
  const title = await page.locator("#forget-range-go").getAttribute("title");
  const showOk = await page.locator("#forget-range-show").isEnabled();
  await page.close();
  assert.equal(goDisabled, true);
  assert.equal(title, WORDS.stale);
  assert.equal(showOk, true, "reading the list is held on a stale link");
  const undo = await historyTab({ status: C.status_undo.body, link: { stale: true } });
  const undoOk = await undo.locator("#forget-range-undo").isEnabled();
  await undo.close();
  assert.equal(undoOk, true, "Undo is held on a stale link");
});

await check("while a card waits or an Undo is open, Forget these is greyed; nothing ticked, too", async () => {
  const page = await historyTab({ status: C.status_waiting.body });
  await showList(page);
  const waiting = await page.locator("#forget-range-go").isDisabled();
  const text = await page.locator("#forget-range").innerText();
  await page.close();
  assert.equal(waiting, true);
  assert.ok(text.includes(WORDS.waiting));
  const none = await historyTab();
  await showList(none);
  for (const box of await none.locator("#forget-range .fr-item input").all()) await box.uncheck();
  const off = await none.locator("#forget-range-go").isDisabled();
  const label = await none.locator("#forget-range-go").innerText();
  await none.close();
  assert.equal(off, true);
  assert.equal(label, "Forget these (0)");
});

await check("typed dates: the custom choice sends the two dates", async () => {
  const page = await historyTab();
  await page.locator("#forget-range-choice").selectOption("custom");
  await page.locator("#forget-range-from").fill("2026-09-01");
  await page.locator("#forget-range-to").fill("2026-09-15");
  await page.locator("#forget-range-kind-facts").uncheck();
  await showList(page);
  const reads = await page.evaluate(() => window.__fr.calls.filter(([c, a]) => a.preview));
  await page.close();
  assert.deepEqual(reads.at(-1)[1], { preview: true, from: "2026-09-01", to: "2026-09-15",
    kinds: ["chats"] });
});

await check("too many, and nothing then: said, and no list", async () => {
  const page = await historyTab({ preview: C.preview_too_many.body });
  await showList(page);
  const text = await page.locator("#forget-range").innerText();
  const items = await page.locator("#forget-range .fr-item").count();
  const go = await page.locator("#forget-range-go").count();
  await page.close();
  assert.match(text, /more than 200 at once\. Choose fewer days\./);
  assert.equal(items, 0);
  assert.equal(go, 0);
});

await check("hidden with the private lists: counts and Show only", async () => {
  const page = await historyTab({ hidden: true });
  await showList(page);
  const text = await page.locator("#forget-range").innerText();
  const go = await page.locator("#forget-range-go").count();
  await page.locator("#forget-range").getByRole("button", { name: "Show", exact: true }).click();
  await page.waitForTimeout(400);
  const after = await page.locator("#forget-range .fr-item").count();
  await page.close();
  assert.match(text, /4 items, hidden until Windows Hello confirms it is you\./);
  assert.doesNotMatch(text, /Leeds|poem|Rome/);
  assert.equal(go, 0, "Forget these offered on a hidden list");
  assert.equal(after, 4);
});

await check("the Jarvis bar's request opens History here, with the days filled in", async () => {
  const page = await historyTab({ status: C.status_asked.body, place: true });
  const view = await page.locator("#view-history").isVisible();
  const asked = await page.locator(".fr-asked").innerText();
  const choice = await page.locator("#forget-range-choice").inputValue();
  const from = await page.locator("#forget-range-from").inputValue();
  const facts = await page.locator("#forget-range-kind-facts").isChecked();
  const chats = await page.locator("#forget-range-kind-chats").isChecked();
  const reads = await page.evaluate(() => window.__fr.calls.filter(([c, a]) => a.preview));
  const focused = await page.evaluate(() => document.activeElement && document.activeElement.textContent);
  const left = await page.evaluate((k) => localStorage.getItem(k), BRAIN_PLACE_KEY);
  const sent = await calls(page);
  await page.close();
  assert.equal(view, true);
  assert.equal(asked, fill(WORDS.asked, { said: "1 to 15 September 2026" }));
  assert.equal(choice, "custom");
  assert.equal(from, "2026-09-01");
  assert.deepEqual([facts, chats], [true, false]);
  assert.deepEqual(reads[0][1], { preview: true, from: "2026-09-01", to: "2026-09-15", kinds: ["facts"] });
  assert.equal(focused, WORDS.title);
  assert.equal(left, null, "the place is taken once");
  assert.deepEqual(sent, [], "opening the list removed something");
});

function fill(t, v) {
  return t.replace(/\{(\w+)\}/g, (m, k) => (k in v ? v[k] : m));
}

await check("a11y: every control named, the status line a live region", async () => {
  const page = await historyTab({ status: C.status_undo.body });
  await page.locator("#forget-range-choice").selectOption("custom");
  await showList(page);
  const bad = await page.evaluate(() => {
    const out = [];
    const rootEl = document.getElementById("forget-range");
    const nameOf = (e) => (e.getAttribute("aria-label") || (e.labels && e.labels[0]
      && e.labels[0].textContent) || e.textContent || e.title || "").trim();
    for (const e of rootEl.querySelectorAll("button, input, select")) {
      if (!nameOf(e)) out.push(e.outerHTML.slice(0, 80));
    }
    if (!rootEl.querySelector("[role=status]#forget-range-said")) out.push("no status line");
    return out;
  });
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(bad, []);
  assert.deepEqual(errors, []);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed` : "\nall forget-range checks passed");
process.exit(fails.length ? 1 : 0);
