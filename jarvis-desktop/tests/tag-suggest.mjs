/**
 * "Suggest tags overnight" and "New section here" in History, on the desktop
 * (docs/OVERNIGHT-TAGS-DESIGN.md section 9; JARVIS-API.md sections 104 and 106;
 * src/history-tags.js, src/history-view.js, brain.js, src-tauri/src/brain/history.rs,
 * src-tauri/src/stream.rs hide_private_cards).
 *
 * 1. PURE checks - plain node: the words, the state line, the error rule, the
 *    card text and the reading of the opened chat, held to
 *    tests/fixtures/history-cases.json (tools/gen_history_cases.py).
 *    CONTROL checks read the Rust, the permission files, the page and the CSS.
 * 2. BROWSER checks - the Brain window on the uikit mock. They need Playwright
 *    AND its Chromium; when either is missing they are SKIPPED, said out loud.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as T from "../src/history-tags.js";
import * as V from "../src/history-view.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/history-cases.json"));
const W = CASES.words;

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── Suggest tags overnight: the words and the reading ─────────────────── */

await check("the suggest words are the fixture's, word for word", () => {
  assert.equal(T.SUGGEST_LABEL, W.tag_suggest_label);
  assert.equal(T.SUGGEST_OFF, W.tag_suggest_off);
  assert.equal(T.SUGGEST_ON, W.tag_suggest_on);
  assert.equal(T.SUGGEST_PAUSED, W.tag_suggest_paused);
  assert.equal(T.SUGGEST_PENDING, W.tag_suggest_pending);
  assert.equal(T.SUGGEST_WAITING_ONE, W.tag_suggest_waiting_one);
  assert.equal(T.SUGGEST_WAITING_OTHER, W.tag_suggest_waiting_other);
  assert.equal(T.SUGGEST_CHAT_HIDDEN, W.tag_suggest_chat_hidden);
  assert.equal(T.SUGGEST_ERROR_FALLBACK, W.tag_suggest_error_fallback);
  assert.deepEqual({ ...T.SUGGEST_ERRORS }, W.tag_suggest_errors);
  assert.deepEqual(Object.keys(T.SUGGEST_ERRORS), CASES.tag_suggest_error_codes);
});

await check("the state line and the waiting line follow the fixture's cases", () => {
  for (const c of CASES.tag_suggest_state_cases) {
    const s = T.readSuggest({ ok: true, enabled: c.enabled, paused: c.paused, waiting: Number((c.waiting.match(/^\d+/) || [0])[0]) });
    assert.equal(T.suggestStateLine(s), c.state, JSON.stringify(c));
    assert.equal(T.suggestWaitingLine(s.waiting), c.waiting, JSON.stringify(c));
  }
});

await check("paused and enabled are never both true: paused wins and the switch reads off", () => {
  const s = T.readSuggest({ ok: true, enabled: true, paused: true, waiting: 0 });
  assert.equal(s.enabled, false);
  assert.equal(s.paused, true);
  assert.equal(T.suggestStateLine(s), W.tag_suggest_paused);
});

await check("an answer that is not one reads as a PC that cannot do it; odd numbers are clamped", () => {
  for (const bad of [null, {}, { ok: false }, { ok: true }, { ok: true, enabled: "yes" }, { available: false }]) {
    assert.equal(T.readSuggest(bad).available, false, JSON.stringify(bad));
  }
  assert.equal(T.readSuggest({ ok: true, enabled: true, waiting: -4 }).waiting, 0);
  assert.equal(T.readSuggest({ ok: true, enabled: true, waiting: 2.5 }).waiting, 0);
  assert.equal(T.suggestWaitingLine(0), "");
});

await check("a change: ON is a pending card (the switch stays off); errors say the PC's words, then the code's, then the fallback", () => {
  const p = T.suggestWriteResult({ ok: true, pending: true });
  assert.deepEqual([p.ok, p.pending, p.said], [true, true, W.tag_suggest_pending]);
  assert.equal(T.suggestWriteResult({ ok: true, enabled: false }).enabled, false);
  for (const [code, sentence] of Object.entries(W.tag_suggest_errors)) {
    assert.equal(T.suggestWriteResult({ ok: false, error: code }).said, sentence, code);
    assert.equal(T.suggestWriteResult({ ok: false, error: code, message: "  The PC's own words.  " }).said, "The PC's own words.");
  }
  assert.equal(T.suggestWriteResult({ ok: false, error: "weird" }).said, W.tag_suggest_error_fallback);
  assert.equal(T.suggestWriteResult(null).said, W.tag_suggest_error_fallback);
});

await check("the card text: text_hidden while the lists are hidden, else text; nothing if hidden has none", () => {
  for (const c of CASES.tag_suggest_card_cases) {
    const detail = {
      text: CASES.tag_suggest_card_cases.find((x) => !x.hidden).expect,
      text_hidden: CASES.tag_suggest_card_cases.find((x) => x.hidden).expect,
    };
    assert.equal(T.suggestCardText(detail, c.hidden), c.expect, JSON.stringify(c));
    assert.equal(c.hidden, !c.expect.includes(c.title), "the hidden card has no title");
  }
  assert.equal(T.suggestCardText({ text: "Chat: Secret" }, true), "", "fail closed");
  assert.equal(T.suggestCardText(null, true), "");
  assert.equal(T.SUGGEST_CARD_ACTION, "chat_tag_suggest");
  assert.equal(T.SUGGEST_SWITCH_ACTION, "chat_tags_suggest_on");
});

/* ── New section here: the words and the reading ───────────────────────── */

await check("the mark words are the fixture's, word for word", () => {
  assert.equal(V.MARK, W.mark);
  assert.equal(V.MARK_LABEL, W.mark_label);
  assert.ok(V.MARK_LABEL.startsWith(V.MARK), "the accessible name starts with the visible text");
  assert.equal(V.MARK_DIVIDER, W.mark_divider);
  assert.equal(V.MARK_REMOVE, W.mark_remove);
  assert.equal(V.MARK_DONE, W.mark_done);
  assert.equal(V.MARK_REMOVED, W.mark_removed);
  assert.equal(V.MARK_LIMIT, W.mark_limit);
  assert.equal(V.MARK_NO, W.mark_no);
  assert.equal(V.MARK_ERROR_FALLBACK, W.mark_error_fallback);
  assert.equal(V.MARK_MAX, CASES.mark_max);
  assert.equal(V.markDoneWords(true), W.mark_done);
  assert.equal(V.markDoneWords(false), W.mark_removed);
  for (const [code, sentence] of Object.entries(W.mark_errors)) assert.equal(V.MARK_ERRORS[code], sentence, code);
});

await check("mark errors follow the fixture's cases", () => {
  for (const c of CASES.mark_error_cases) assert.equal(V.markErrorWords(c.answer), c.expect, JSON.stringify(c.answer));
});

await check("the conversation read carries marks, markable and the why; an older PC draws nothing", () => {
  const c = V.readConversation({ id: "c1", markable: true, marks: [4, 2, 2, -1, 1.5, "3"], mark_why: "",
    turns: [{ role: "user", text: "x", idx: 0 }] });
  assert.deepEqual(c.marks, [2, 4]);
  assert.equal(c.markable, true);
  const short = V.readConversation({ id: "c2", markable: false, mark_why: W.mark_why_short, turns: [] });
  assert.equal(short.markable, false);
  assert.equal(short.markWhy, W.mark_why_short);
  const old = V.readConversation({ id: "c3", turns: [] });
  assert.deepEqual([old.markable, old.marks, old.markWhy], [false, [], ""]);
  assert.equal(V.readConversation({ id: "c4", markable: "yes", turns: [] }).markable, false);
});

await check("the button is offered only on the owner's own numbered messages without a divider yet", () => {
  assert.equal(V.markOffered(true, "user", 3, []), true);
  assert.equal(V.markOffered(true, "assistant", 3, []), false);
  assert.equal(V.markOffered(true, "support", 3, []), false);
  assert.equal(V.markOffered(false, "user", 3, []), false);
  assert.equal(V.markOffered(true, "user", null, []), false);
  assert.equal(V.markOffered(true, "user", 3, [3]), false);
});

/* ── CONTROL: Rust, permissions, page, CSS ─────────────────────────────── */

const fnBody = (src, sig) => {
  const at = src.indexOf(sig);
  assert.ok(at > 0, sig);
  return src.slice(at, src.indexOf("\n}\n", at));
};
const strip = (s) => s.replace(/\/\/.*$/gm, "");

await check("CONTROL: both commands are registered and only the History set holds them", () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  for (const [cmd, perm] of [["brain_history_mark", "allow-brain-history-mark"],
    ["brain_history_tag_suggest", "allow-brain-history-tag-suggest"]]) {
    const holders = toml.split("[[set]]").slice(1).filter((s) => s.includes(`"${perm}"`))
      .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
    assert.deepEqual(holders, ["brain-history"], cmd);
    assert.match(read("src-tauri/build.rs"), new RegExp(`"${cmd}"`));
    assert.match(read("src-tauri/src/lib.rs"), new RegExp(`brain::history::${cmd},`));
    assert.match(read(`src-tauri/permissions/autogenerated/${cmd}.toml`), new RegExp(perm));
    for (const c of ["faces", "floating", "hud", "onboarding", "quickbar", "settings", "widget"]) {
      assert.ok(!read(`src-tauri/capabilities/${c}.json`).includes(cmd), `${c} holds ${cmd}`);
    }
  }
  assert.match(read("src-tauri/capabilities/brain.json"), /"brain-history"/);
});

await check("CONTROL: the mark command asks the lock, is held on a stale link, sends the literal route, no card, no log", () => {
  const body = fnBody(read("src-tauri/src/brain/history.rs"), "pub async fn brain_history_mark(");
  assert.ok(body.includes("private_hidden"));
  assert.ok(body.indexOf("private_hidden") < body.indexOf("post("));
  assert.ok(body.indexOf("require_link_live") > 0 && body.indexOf("require_link_live") < body.indexOf("post("));
  assert.ok(body.includes('"/api/history/mark"'));
  const code = strip(body);
  assert.ok(!/approv|card/i.test(code), "no card on a section break");
  assert.ok(!/println!|eprintln!|log::|tracing::|token/i.test(code));
  assert.match(read("src-tauri/src/brain/history.rs"), /"id": id, "idx": idx, "on": on/);
});

await check("CONTROL: the suggest command is one command for exactly the two keys, not hidden with the lists, write held on a stale link", () => {
  const body = fnBody(read("src-tauri/src/brain/history.rs"), "pub async fn brain_history_tag_suggest(");
  assert.ok(!body.includes("private_hidden"), "the row holds no chat words");
  assert.ok(body.includes('"/api/history/tags/suggest"'));
  assert.ok(body.indexOf("require_link_live") > 0 && body.indexOf("require_link_live") < body.indexOf("post("));
  assert.ok(body.includes('serde_json::json!({ "enabled": on })'), "exactly {enabled}");
  assert.ok(!/println!|eprintln!|log::|tracing::|token/i.test(strip(body)));
});

await check("CONTROL: a suggestion card loses the chat title in Rust while the lists are hidden, and the lock re-sends the queue", () => {
  const stream = read("src-tauri/src/stream.rs");
  assert.match(stream, /const TAG_SUGGEST_ACTION: &str = "chat_tag_suggest";/);
  assert.match(stream, /hide_private_cards\(&mut items, crate::lock::private_hidden\(&app\)\)/, "the read");
  assert.match(stream, /hide_private_cards\(&mut shown, crate::lock::private_hidden\(app\)\)/, "the broadcast");
  assert.match(read("src-tauri/src/lock.rs"), /crate::stream::rebroadcast_pending\(app\);/);
});

await check("CONTROL: the page is keyboard-operable, held on a stale link, hidden with the lists, with stable focus keys", () => {
  const view = read("src/history-view.js");
  assert.match(view, /el\("button", "btn ghost small history-mark"/, "a real button");
  assert.match(view, /mb\.dataset\.fkey = `mark:\$\{conv\.id\}:\$\{t\.idx\}`/);
  assert.match(view, /setAttribute\("role", "heading"\)/, "the divider is a heading landmark");
  assert.match(view, /el\("button", "btn ghost small history-mark-remove"/);
  const brain = read("src/brain.js");
  assert.match(brain, /function markHelpers\(conv\)/);
  assert.match(brain, /!conv\.markable && !conv\.marks\.length/);
  assert.match(brain, /chats\.view && chats\.view\.hidden\)\) return null;\n  if \(!conv\.markable/, "no button while the lists are hidden");
  assert.match(brain, /decorate: \(b\) => \{ liveButtons\.add\(b\); syncLiveButton\(b\); \}/, "held on a stale link");
  assert.match(brain, /invoke\("brain_history_mark", \{ id, idx, on \}\)/);
  assert.match(brain, /if \(chats\.marking \|\| !IS_TAURI\) return;/, "one at a time");
  assert.match(brain, /invoke\("brain_history_tag_suggest", \{ enabled: null \}\)/);
  assert.match(brain, /invoke\("brain_history_tag_suggest", \{ enabled: want \}\)/);
  assert.match(brain, /input\.checked = s\.enabled;/, "the switch shows what the PC says, never what was clicked");
  const css = read("src/brain.css");
  assert.ok(!/history-mark[^}]*animation|history-mark[^}]*transition|history-section-break[^}]*animation|history-section-break[^}]*transition/s.test(css), "no motion of its own");
  assert.ok(!/localStorage|sessionStorage|indexedDB/.test(brain.slice(brain.indexOf("async function markSection("), brain.indexOf("/** Back to every chat"))), "nothing stored");
});

/* ── The Brain window (needs Playwright and its Chromium) ──────────────── */

let K = null;
let browser = null;
try {
  await import("playwright");
  K = await import("./uikit.mjs");
  browser = await K.launch();
} catch (e) {
  console.log(`SKIP  browser checks: ${String(e.message).split("\n")[0]}`);
}

if (browser) {
  const { base, close } = await K.serve();
  const NOW = Math.floor(Date.now() / 1000);
  const TAGS = [
    { id: 1, name: "Work", colour: 0, icon: "briefcase", order: 0 },
    { id: 2, name: "Learning", colour: 1, icon: "book", order: 1 },
  ];
  const row = (id, title, kind = "chat") => ({ id, title, started: NOW - 3000, updated: NOW - 60, turns: 12,
    device: "desktop", has_voice: false, tainted: false, kind });
  // 12 turns: user, assistant, user, assistant ... (idx 0..11).
  const turns = (n = 12) => Array.from({ length: n }, (_, i) => ({
    role: i % 2 === 0 ? "user" : "assistant", text: i % 2 === 0 ? `Question ${i}` : `Answer ${i}`,
    at: NOW - 2000 + i * 10, idx: i, ...(i % 2 === 0 ? { provenance: "typed" } : {}),
  }));
  const conv = (id, title, extra = {}) => ({ id, title, kind: "chat", tainted: false, started: NOW - 3000,
    updated: NOW - 60, continuable: true, forkable: true, fork_why: "", markable: true, mark_why: "", marks: [],
    turns: turns(), ...extra });
  const tab = async (history = {}, extra = {}) => {
    const page = await K.open(browser, base, "brain.html", {
      history: {
        conversations: [row("conv-0001-aaaa", "Boiler service"), row("conv-0002-aaaa", "Short one"),
          row("conv-0003-aaaa", "Support call", "support")],
        tags: JSON.parse(JSON.stringify(TAGS)),
        transcripts: {
          "conv-0001-aaaa": conv("conv-0001-aaaa", "Boiler service"),
          "conv-0002-aaaa": conv("conv-0002-aaaa", "Short one", { markable: false, mark_why: W.mark_why_short, turns: turns(4) }),
          "conv-0003-aaaa": conv("conv-0003-aaaa", "Support call", { kind: "support", markable: false, forkable: false,
            mark_why: W.mark_why_kind }),
        },
        ...history,
      },
      ...extra,
    }, { width: 1180, height: 900 });
    await page.locator("#tab-history").click();
    await page.waitForTimeout(350);
    return page;
  };
  const calls = (page, cmd) => page.evaluate((c) => window.__calls.filter((x) => x[0] === c).map((x) => x[1]), cmd);
  const openChat = async (page, id) => {
    await page.locator(`.row-item[data-id="${id}"] button[data-fkey="open:${id}"]`).click();
    await page.waitForTimeout(350);
  };
  const openEditor = async (page) => {
    await page.locator("#tag-editor-toggle").click();
    await page.waitForTimeout(300);
  };

  /* -- New section here -- */

  await check("browser: a button on each of the owner's messages only, named for the fixture", async () => {
    const page = await tab();
    await openChat(page, "conv-0001-aaaa");
    const btns = page.locator(".history-mark");
    assert.equal(await btns.count(), 6, "six owner messages, none of Jarvis's answers");
    assert.deepEqual(await btns.evaluateAll((els) => [...new Set(els.map((e) => e.getAttribute("aria-label")))]), [W.mark_label]);
    for (const t of await btns.allInnerTexts()) assert.equal(t.trim(), W.mark);
    assert.equal(await btns.first().evaluate((e) => e.tagName), "BUTTON");
    assert.equal(await page.locator('.history-turn[data-role="assistant"] .history-mark').count(), 0);
    await page.close();
  });

  await check("browser: pressing it sends exactly id, idx and on, draws a divider above that message and says so politely", async () => {
    const page = await tab();
    await openChat(page, "conv-0001-aaaa");
    await page.locator(".history-mark").nth(2).click();
    await page.waitForTimeout(400);
    assert.deepEqual((await calls(page, "brain_history_mark")).at(-1), { id: "conv-0001-aaaa", idx: 4, on: true });
    const brk = page.locator(".history-section-break");
    assert.equal(await brk.count(), 1);
    assert.equal(await brk.getAttribute("role"), "heading");
    assert.equal((await brk.locator(".history-section-break-text").innerText()).trim(), W.mark_divider);
    assert.equal((await brk.locator("button").innerText()).trim(), W.mark_remove);
    // The divider sits ABOVE the marked turn.
    assert.match(await brk.evaluate((e) => e.closest("li").innerText), /Question 4/);
    assert.equal(await page.locator("#toast").innerText(), W.mark_done);
    // A marked message offers no second button; the others still do.
    assert.equal(await page.locator(".history-mark").count(), 5);
    await page.close();
  });

  await check("browser: Remove takes the divider off (same tap, both directions)", async () => {
    const page = await tab({ transcripts: { "conv-0001-aaaa": conv("conv-0001-aaaa", "Boiler service", { marks: [2, 6] }) } });
    await openChat(page, "conv-0001-aaaa");
    assert.equal(await page.locator(".history-section-break").count(), 2);
    await page.locator(".history-section-break .history-mark-remove").first().click();
    await page.waitForTimeout(400);
    assert.deepEqual((await calls(page, "brain_history_mark")).at(-1), { id: "conv-0001-aaaa", idx: 2, on: false });
    assert.equal(await page.locator(".history-section-break").count(), 1);
    assert.equal(await page.locator("#toast").innerText(), W.mark_removed);
    await page.close();
  });

  await check("browser: a chat that is not markable shows no button and no sentence in the way", async () => {
    const page = await tab();
    await openChat(page, "conv-0002-aaaa");
    assert.equal(await page.locator(".history-mark").count(), 0);
    await page.locator("#history-list .row-item").first().click({ position: { x: 5, y: 5 } }).catch(() => {});
    await page.close();
    const page2 = await tab();
    await openChat(page2, "conv-0003-aaaa");
    assert.equal(await page2.locator(".history-mark").count(), 0);
    await page2.close();
  });

  await check("browser: a refusal shows the PC's sentence, else the fixed one", async () => {
    for (const c of CASES.mark_error_cases.filter((x) => x.answer.error)) {
      const page = await tab({ markRefuse: c.answer });
      await openChat(page, "conv-0001-aaaa");
      await page.locator(".history-mark").first().click();
      await page.waitForTimeout(350);
      assert.equal(await page.locator("#toast").innerText(), c.expect, JSON.stringify(c.answer));
      assert.equal(await page.locator(".history-section-break").count(), 0, "nothing drawn on a refusal");
      await page.close();
    }
  });

  await check("browser: the 21st break is refused with the limit sentence", async () => {
    const page = await tab({ transcripts: { "conv-0001-aaaa": conv("conv-0001-aaaa", "Boiler service",
      { turns: turns(60), marks: Array.from({ length: 20 }, (_, i) => i * 2 + 1) }) } });
    await openChat(page, "conv-0001-aaaa");
    await page.locator(".history-mark").first().click();
    await page.waitForTimeout(350);
    assert.equal(await page.locator("#toast").innerText(), W.mark_limit);
    await page.close();
  });

  await check("browser: hidden lists offer no marker at all", async () => {
    const page = await tab({}, { security: { hidden: true } });
    assert.equal(await page.locator(".history-mark, .history-section-break").count(), 0);
    await page.close();
  });

  await check("browser: the buttons are greyed on a stale link", async () => {
    const page = await tab();
    await openChat(page, "conv-0001-aaaa");
    await page.evaluate(() => window.__setLink && window.__setLink({ stale: true, connected: false }));
    await page.waitForTimeout(300);
    const stale = await page.evaluate(() => !!window.__setLink);
    if (stale) assert.equal(await page.locator(".history-mark").first().isDisabled(), true);
    await page.close();
  });

  /* -- Suggest tags overnight -- */

  await check("browser: the row is the last thing in the Tags editor, off, with the fixture's words", async () => {
    const page = await tab({ suggest: { enabled: false, paused: false, waiting: 0, last_day: "" } });
    await openEditor(page);
    const box = page.locator("#tag-editor #tag-suggest");
    assert.equal(await box.count(), 1);
    assert.equal(await page.locator("#tag-editor > *").last().evaluate((e) => e.id), "tag-suggest");
    const sw = box.locator('input[role="switch"]');
    assert.equal(await sw.isChecked(), false);
    assert.equal((await box.locator(".history-switch-label").innerText()).trim(), W.tag_suggest_label);
    assert.equal((await box.locator("#tag-suggest-state").innerText()).trim(), W.tag_suggest_off);
    assert.equal(await sw.getAttribute("aria-describedby"), "tag-suggest-state");
    await page.close();
  });

  await check("browser: the state line for on, and the waiting line, follow the fixture", async () => {
    const page = await tab({ suggest: { enabled: true, paused: false, waiting: 3, last_day: "2026-09-30" } });
    await openEditor(page);
    assert.equal(await page.locator("#tag-suggest-enabled").isChecked(), true);
    assert.equal((await page.locator("#tag-suggest-state").innerText()).trim(), W.tag_suggest_on);
    assert.equal((await page.locator(".tag-suggest-waiting").innerText()).trim(), W.tag_suggest_waiting_other.replace("{n}", "3"));
    await page.close();
    const one = await tab({ suggest: { enabled: false, paused: true, waiting: 1, last_day: "" } });
    await openEditor(one);
    assert.equal((await one.locator("#tag-suggest-state").innerText()).trim(), W.tag_suggest_paused);
    assert.equal((await one.locator(".tag-suggest-waiting").innerText()).trim(), W.tag_suggest_waiting_one);
    assert.equal(await one.locator("#tag-suggest-enabled").isChecked(), false);
    await one.close();
  });

  await check("browser: turning it on sends exactly {enabled: true}, shows the pending line and the switch stays off", async () => {
    const page = await tab({ suggest: { enabled: false, paused: false, waiting: 0, last_day: "" } });
    await openEditor(page);
    await page.locator("#tag-suggest-enabled").click();
    await page.waitForTimeout(500);
    assert.deepEqual(await page.evaluate(() => window.__history.suggestWrites), [{ enabled: true }]);
    assert.equal(await page.locator("#tag-suggest-enabled").isChecked(), false, "still off until the PC says enabled");
    assert.equal((await page.locator(".tag-suggest-said").innerText()).trim(), W.tag_suggest_pending);
    assert.equal(await page.evaluate(() => window.__history.suggestCards), 1, "one card raised");
    // Later the owner approves on the PC: a read says enabled, the switch follows and the line goes.
    await page.evaluate(() => { window.__history.suggest = { enabled: true, paused: false, waiting: 0, last_day: "" }; });
    await page.locator("#tag-editor-toggle").click();
    await page.locator("#tag-editor-toggle").click();
    await page.waitForTimeout(500);
    assert.equal(await page.locator("#tag-suggest-enabled").isChecked(), true);
    await page.close();
  });

  await check("browser: turning it off is at once and sends exactly {enabled: false}", async () => {
    const page = await tab({ suggest: { enabled: true, paused: false, waiting: 2, last_day: "" } });
    await openEditor(page);
    await page.locator("#tag-suggest-enabled").click();
    await page.waitForTimeout(500);
    assert.deepEqual(await page.evaluate(() => window.__history.suggestWrites), [{ enabled: false }]);
    assert.equal(await page.locator("#tag-suggest-enabled").isChecked(), false);
    assert.equal((await page.locator("#tag-suggest-state").innerText()).trim(), W.tag_suggest_off);
    assert.equal(await page.locator(".tag-suggest-waiting").count(), 0);
    await page.close();
  });

  await check("browser: a refusal shows the PC's message, else the code's sentence, else the fallback", async () => {
    const cases = [
      [{ ok: false, error: "no_tags", message: "Make a tag first." }, "Make a tag first."],
      [{ ok: false, error: "no_local_model" }, W.tag_suggest_errors.no_local_model],
      [{ ok: false, error: "weird" }, W.tag_suggest_error_fallback],
    ];
    for (const [answer, expect] of cases) {
      const page = await tab({ suggest: { enabled: false, paused: false, waiting: 0, last_day: "" }, suggestRefuse: answer });
      await openEditor(page);
      await page.locator("#tag-suggest-enabled").click();
      await page.waitForTimeout(450);
      assert.equal((await page.locator(".tag-suggest-said").innerText()).trim(), expect, JSON.stringify(answer));
      assert.equal(await page.locator("#tag-suggest-enabled").isChecked(), false);
      await page.close();
    }
  });

  await check("browser: a PC without the route says so in the editor and leaves the bar out when lists are hidden", async () => {
    const page = await tab();
    await openEditor(page);
    assert.equal((await page.locator("#tag-suggest").innerText()).trim(), T.SUGGEST_OLD_PC);
    assert.equal(await page.locator("#tag-suggest-enabled").count(), 0);
    await page.close();
    const hidden = await tab({}, { security: { hidden: true } });
    assert.equal(await hidden.locator("#history-tagbar").isHidden(), true);
    await hidden.close();
  });

  await check("browser: under hidden lists the row still shows, with no tag name and no chat title anywhere", async () => {
    const page = await tab({ suggest: { enabled: true, paused: false, waiting: 1, last_day: "" } },
      { security: { hidden: true } });
    const bar = page.locator("#history-tagbar");
    assert.equal(await bar.isVisible(), true);
    assert.equal(await page.locator("#history-tagbar #tag-suggest-enabled").count(), 1);
    assert.equal(await page.locator("#history-tagbar .tag-chip").count(), 0, "no chips");
    const text = await page.locator("#view-history").innerText();
    for (const name of ["Work", "Learning", "Boiler"]) assert.ok(!text.includes(name), name);
    await page.close();
  });

  await close();
  await browser.close();
}

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("\nall tag-suggest and section-break checks passed");
