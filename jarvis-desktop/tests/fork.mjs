/**
 * "Fork from here" in History, on the desktop (docs/CHAT-TAGS-DESIGN.md "Fork
 * contract (frozen)"; JARVIS-API.md section 110; src/history-view.js,
 * brain.js "Fork from here", src-tauri/src/brain/history.rs).
 *
 * 1. PURE checks - plain node: the words, the error rule and the reading of
 *    the opened chat, held to tests/fixtures/history-cases.json; CONTROL
 *    checks that read the Rust, the permission files, the page and the CSS.
 * 2. BROWSER checks - the Brain window on the uikit mock. They need
 *    Playwright AND its Chromium; when either is missing they are SKIPPED,
 *    said out loud. They were NOT run when this file was written (the
 *    container cannot download Chromium).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { continueWindow } from "../src/chat-history.js";
import {
  FORK, FORK_BUSY, FORK_ERROR_FALLBACK, FORK_NO, FORK_TITLE, forkDoneWords, forkErrorWords, forkLabel,
  forkedRow, readConversation, withForkedRow,
} from "../src/history-view.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/history-cases.json"));
const W = CASES.words;

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

await check("the fork words are the fixture's, word for word", () => {
  assert.equal(FORK, W.fork);
  assert.equal(FORK_TITLE, W.fork_title);
  assert.equal(FORK_BUSY, W.fork_busy);
  assert.equal(FORK_NO, W.fork_no);
  assert.equal(FORK_ERROR_FALLBACK, W.fork_error_fallback);
  assert.equal(forkLabel("user"), W.fork_label_user);
  assert.equal(forkLabel("assistant"), W.fork_label_assistant);
  assert.deepEqual({ user: forkLabel("user"), assistant: forkLabel("assistant") }, CASES.fork_labels);
  for (const role of ["user", "assistant"]) {
    assert.ok(forkLabel(role).startsWith(FORK), "the accessible name starts with the visible text");
  }
  assert.equal(forkDoneWords("Fork of Boiler"), W.fork_done.replace("{title}", "Fork of Boiler"));
});

await check("the title is the PC's: the app never builds it, and knows the prefix and limit", () => {
  assert.equal(W.fork_title_of.replace("{title}", "X"), `${CASES.fork_prefix}X`);
  assert.ok(CASES.fork_title_max >= CASES.fork_prefix.length);
  const src = read("src/history-view.js") + read("src/brain.js");
  assert.ok(!/["'`]Fork of/.test(src), "no app builds the 'Fork of' title");
  // Whatever length the PC sent is shown as it came.
  const long = `${CASES.fork_prefix}${"a".repeat(CASES.fork_title_max)}`;
  assert.ok(forkDoneWords(long).includes(long));
  assert.equal(forkDoneWords(""), "Forked into a new chat.");
  assert.equal(forkDoneWords(undefined), "Forked into a new chat.");
});

await check("errors follow the fixture's rule", () => {
  for (const c of CASES.fork_error_cases) {
    assert.equal(forkErrorWords(c.answer), c.expect, JSON.stringify(c.answer));
  }
  assert.equal(forkErrorWords(null), W.fork_error_fallback);
  for (const [code, sentence] of Object.entries(W.fork_errors)) {
    if (code !== "bad_request") assert.equal(forkErrorWords({ ok: false, error: code }), sentence, code);
  }
  assert.equal(forkErrorWords({ ok: false, error: "bad_request" }), W.fork_errors.bad_request);
  assert.equal(forkErrorWords({ ok: false, error: "weird", message: "  Plain.  " }), "Plain.");
  assert.equal(forkErrorWords({ ok: false, error: "weird" }), W.fork_error_fallback);
});

await check("errors: the PC's message wins, then the code's sentence, then the fallback", () => {
  for (const [code, sentence] of Object.entries(W.fork_errors)) {
    assert.equal(forkErrorWords({ ok: false, error: code, message: "  The PC's own words.  " }),
      "The PC's own words.", `${code} with a message`);
    if (code !== "bad_request") assert.equal(forkErrorWords({ ok: false, error: code, message: "" }), sentence, code);
  }
  assert.equal(forkErrorWords({ ok: false, error: "weird", message: "   " }), W.fork_error_fallback);
});

await check("a forked chat's row is built from the answer and goes first, once", () => {
  const made = { ok: true, id: "fork-abc", title: "Fork of Boiler", turns: 4, tag_id: 3 };
  const src = { id: "conv-1", started: 100, updated: 200, device: "phone", tainted: true, project: "home", kind: "live" };
  const r = forkedRow(made, src, 5000);
  assert.deepEqual(r, { id: "fork-abc", title: "Fork of Boiler", started: 100, updated: 5000, turns: 4,
    device: "phone", hasVoice: false, tainted: true, kind: "chat", project: "home", tagId: 3 });
  const bare = forkedRow({ id: "f", title: "T", turns: 1, tag_id: null }, null, 7);
  assert.equal(bare.started, 7);
  assert.equal(bare.tagId, null);
  const rows = withForkedRow([{ id: "a" }, { id: "fork-abc" }, { id: "b" }], r);
  assert.deepEqual(rows.map((c) => c.id), ["fork-abc", "a", "b"]);
});

await check("CONTROL: after a fork the narrowing is cleared and a reread cannot close the new chat", () => {
  const brain = read("src/brain.js");
  const at = brain.indexOf("async function forkFrom(");
  const body = brain.slice(at, brain.indexOf("\n}\n", at));
  assert.match(body, /clearHistoryNarrowing\(\)/);
  assert.match(body, /chats\.forked = \{ id: made\.id, row \}/);
  const clear = brain.slice(brain.indexOf("function clearHistoryNarrowing"), brain.indexOf("/** Copy on an opened old answer"));
  for (const part of ['chats.kind = ""', 'chats.tag = ""', 's.query = ""']) assert.ok(clear.includes(part), part);
  assert.match(brain, /const justForked = /);
  assert.match(brain, /history-forked/, "the transcript is drawn above the list when its row is missing");
});

await check("a fork made at a user message continues cleanly: the unanswered question is left out, never re-sent", () => {
  const forked = [
    { role: "user", text: "first", provenance: "typed", answer_kept: true },
    { role: "assistant", text: "one" },
    { role: "user", text: "second", provenance: "typed", answer_kept: false },
  ];
  const got = continueWindow(forked);
  assert.deepEqual(got.window.map((p) => [p.question, p.answer]), [["first", "one"]]);
  assert.equal(got.skipped, 1);
  // ...and the next question after Continue follows an assistant turn: no two user messages in a row.
});

await check("the opened chat keeps idx, forkable and fork_why", () => {
  const conv = readConversation({
    id: "c1", kind: "chat", forkable: true, fork_why: "",
    turns: [{ role: "user", text: "hi", idx: 0 }, { role: "assistant", text: "yo", idx: 1 },
      { role: "user", text: "later", idx: 5 }],
  });
  assert.equal(conv.forkable, true);
  assert.equal(conv.forkWhy, "");
  assert.deepEqual(conv.turns.map((t) => t.idx), [0, 1, 5], "the PC's numbers, not array places");
  const no = readConversation({ id: "c2", kind: "support", forkable: false, fork_why: W.fork_why_kind, turns: [] });
  assert.equal(no.forkable, false);
  assert.equal(no.forkWhy, W.fork_why_kind);
  const crisis = readConversation({ id: "c3", forkable: false, fork_why: W.fork_why_crisis, turns: [] });
  assert.equal(crisis.forkWhy, W.fork_why_crisis);
  assert.equal(readConversation({ id: "c4", forkable: false, turns: [] }).forkWhy, W.fork_no);
  const old = readConversation({ id: "c5", turns: [{ role: "user", text: "x" }] });
  assert.equal(old.forkable, false, "an older PC offers nothing");
  assert.equal(old.forkWhy, "", "and says nothing");
  assert.equal(old.turns[0].idx, null);
  const bad = readConversation({ id: "c6", forkable: "yes", turns: [{ role: "user", text: "x", idx: -1 }, { role: "user", text: "y", idx: 1.5 }] });
  assert.equal(bad.forkable, false);
  assert.deepEqual(bad.turns.map((t) => t.idx), [null, null]);
});

await check("CONTROL: the fork command is registered and only the History set holds it", () => {
  const cmd = "brain_history_fork";
  const perm = "allow-brain-history-fork";
  const toml = read("src-tauri/permissions/surfaces.toml");
  const holders = toml.split("[[set]]").slice(1).filter((s) => s.includes(`"${perm}"`))
    .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
  assert.deepEqual(holders, ["brain-history"]);
  assert.match(read("src-tauri/build.rs"), new RegExp(`"${cmd}"`));
  assert.match(read("src-tauri/src/lib.rs"), new RegExp(`brain::history::${cmd},`));
  assert.match(read(`src-tauri/permissions/autogenerated/${cmd}.toml`), new RegExp(perm));
  for (const c of ["faces", "floating", "hud", "onboarding", "quickbar", "settings", "widget"]) {
    assert.ok(!read(`src-tauri/capabilities/${c}.json`).includes("brain_history_fork"), `${c} holds fork`);
  }
});

await check("CONTROL: the Rust asks the lock, is held on a stale link, sends the literal route and logs nothing", () => {
  const rust = read("src-tauri/src/brain/history.rs");
  const at = rust.indexOf("pub async fn brain_history_fork(");
  assert.ok(at > 0);
  const body = rust.slice(at, rust.indexOf("\n}\n", at));
  assert.ok(body.includes("private_hidden"));
  assert.ok(body.indexOf("private_hidden") < body.indexOf("post("));
  assert.ok(body.indexOf("require_link_live") > 0 && body.indexOf("require_link_live") < body.indexOf("post("));
  assert.ok(body.includes('"/api/history/fork"'));
  assert.ok(!/approv|card/i.test(body.replace(/\/\/.*$/gm, "")), "no card on a fork");
  assert.ok(!/println!|eprintln!|log::|tracing::|token/i.test(body.replace(/\/\/.*$/gm, "")));
  assert.match(rust, /"upto": upto/);
});

await check("CONTROL: the page is keyboard-operable, held on a stale link, hidden with the lists and has stable focus keys", () => {
  const view = read("src/history-view.js");
  assert.match(view, /el\("button", "btn ghost small history-fork"/, "a real button");
  assert.match(view, /fb\.dataset\.fkey = `fork:\$\{conv\.id\}:\$\{t\.idx\}`/);
  assert.match(view, /setAttribute\("aria-label", busyHere \? FORK_BUSY : forkLabel\(t\.role\)\)/);
  const brain = read("src/brain.js");
  assert.match(brain, /function forkHelpers\(conv\)/);
  assert.match(brain, /!conv\.forkable \|\| \(chats\.view && chats\.view\.hidden\)/, "no button while the lists are hidden");
  assert.match(brain, /decorate: \(b\) => \{ liveButtons\.add\(b\); syncLiveButton\(b\); \}/, "held on a stale link");
  assert.match(brain, /case "fork": return/, "focus falls back when the button is gone");
  assert.match(brain, /invoke\("brain_history_fork", \{ id, upto: idx \}\)/);
  assert.match(brain, /if \(chats\.forking \|\| !IS_TAURI\) return;/, "one at a time");
  assert.ok(!/history-fork[^}]*animation|history-fork[^}]*transition/s.test(read("src/brain.css")), "no motion of its own");
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
  const row = (id, title, kind = "chat") => ({ id, title, started: NOW - 300, updated: NOW - 60, turns: 3,
    device: "desktop", has_voice: false, tainted: false, kind });
  const turns = () => [
    { role: "user", text: "How do I bleed a radiator?", at: NOW - 200, idx: 0, provenance: "typed" },
    { role: "assistant", text: "Turn the valve a little.", at: NOW - 190, idx: 1 },
    { role: "user", text: "And then?", at: NOW - 100, idx: 2, provenance: "typed" },
  ];
  const conv = (id, title, extra = {}) => ({ id, title, kind: "chat", tainted: false, started: NOW - 300,
    updated: NOW - 60, continuable: true, forkable: true, fork_why: "", turns: turns(), ...extra });
  const tab = async (extra = {}, history = {}) => {
    const page = await K.open(browser, base, "brain.html", {
      history: {
        conversations: [row("conv-0001-aaaa", "Boiler service"), row("conv-0002-aaaa", "Support call", "support")],
        transcripts: {
          "conv-0001-aaaa": conv("conv-0001-aaaa", "Boiler service"),
          "conv-0002-aaaa": conv("conv-0002-aaaa", "Support call", { kind: "support", continuable: false,
            forkable: false, fork_why: CASES.words.fork_why_kind }),
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

  await check("browser: a button on each message, named for its role, starting with its visible text", async () => {
    const page = await tab();
    await openChat(page, "conv-0001-aaaa");
    const btns = page.locator(".history-fork");
    assert.equal(await btns.count(), 3);
    assert.deepEqual(await btns.evaluateAll((els) => els.map((e) => e.getAttribute("aria-label"))),
      [W.fork_label_user, W.fork_label_assistant, W.fork_label_user]);
    for (const t of await btns.allInnerTexts()) assert.equal(t.trim(), W.fork);
    assert.equal(await btns.first().evaluate((e) => e.tagName), "BUTTON");
    await page.close();
  });

  await check("browser: pressing it sends exactly id and upto, opens the new chat and says so", async () => {
    const page = await tab();
    await openChat(page, "conv-0001-aaaa");
    await page.locator(".history-fork").nth(1).click();
    await page.waitForTimeout(600);
    assert.deepEqual((await calls(page, "brain_history_fork")).at(-1), { id: "conv-0001-aaaa", upto: 1 });
    assert.ok((await page.locator("#history-list .row-title").allInnerTexts()).includes("Fork of Boiler service"));
    assert.equal(await page.locator('.row-item[data-id="conv-0001-aaaa-fork"]').count(), 1);
    assert.equal(await page.locator("#history-transcript .history-turn").count(), 2, "the fork's two turns");
    assert.equal(await page.locator("#toast").innerText(), W.fork_done.replace("{title}", "Fork of Boiler service"));
    await page.close();
  });

  await check("browser: forking from a Live-only list, with a tag chip and search words, still shows the new chat", async () => {
    const live = { ...row("conv-0003-aaaa", "Evening Live", "live"), tag_id: 1 };
    const page = await tab({}, {
      conversations: [row("conv-0001-aaaa", "Boiler service"), live],
      tags: [{ id: 1, name: "Home", colour: 0, icon: "folder", order: 0 }],
      transcripts: { "conv-0003-aaaa": conv("conv-0003-aaaa", "Evening Live", { kind: "live", tag_id: 1 }) },
    });
    await page.locator("#history-kind").selectOption("live");
    await page.waitForTimeout(400);
    await openChat(page, "conv-0003-aaaa");
    await page.locator("#history-filter").fill("Evening");
    await page.waitForTimeout(700);
    await page.locator(".history-fork").nth(1).click();
    await page.waitForTimeout(900);
    assert.equal(await page.locator("#history-kind").inputValue(), "", "the kind filter is cleared");
    assert.equal(await page.locator("#history-filter").inputValue(), "", "the search words are cleared");
    assert.equal(await page.locator("#history-transcript .history-turn").count(), 2, "the new chat's transcript is open");
    assert.ok((await page.locator("#history-list .row-title").allInnerTexts()).includes("Fork of Evening Live"));
    // A later re-read (as the 15-second one) must not close it.
    await page.evaluate(() => window.dispatchEvent(new Event("jarvis-history-changed")));
    await page.waitForTimeout(600);
    assert.equal(await page.locator("#history-transcript .history-turn").count(), 2, "still open after a re-read");
    await page.close();
  });

  await check("browser: a refusal leaves the original open and shows the PC's sentence", async () => {
    const page = await tab({}, { forkRefuse: CASES.fork_error_cases[3].answer });
    await openChat(page, "conv-0001-aaaa");
    await page.locator(".history-fork").first().click();
    await page.waitForTimeout(400);
    assert.equal(await page.locator("#toast").innerText(), CASES.fork_error_cases[3].expect);
    assert.equal(await page.locator("#history-transcript .history-turn").count(), 3);
    assert.equal(await page.locator(".history-fork").first().isEnabled(), true);
    await page.close();
  });

  await check("browser: a chat that cannot be forked shows the PC's why and no button", async () => {
    const page = await tab();
    await openChat(page, "conv-0002-aaaa");
    assert.equal(await page.locator(".history-fork").count(), 0);
    assert.equal(await page.locator(".history-fork-why").innerText(), CASES.words.fork_why_kind);
    await page.close();
  });

  await check("browser: held (greyed) on a stale link", async () => {
    const page = await tab({ link: { stale: true } });
    await openChat(page, "conv-0001-aaaa");
    assert.equal(await page.locator(".history-fork").first().isDisabled(), true);
    await page.locator(".history-fork").first().click({ force: true }).catch(() => {});
    assert.equal((await calls(page, "brain_history_fork")).length, 0);
    await page.close();
  });

  await check("browser: hidden lists show no fork button", async () => {
    const page = await tab({ security: { hidden: true } });
    assert.equal(await page.locator(".history-fork").count(), 0);
    await page.close();
  });

  await check("browser: the keyboard can reach and press it, and keeps its place", async () => {
    const page = await tab();
    await openChat(page, "conv-0001-aaaa");
    const b = page.locator(".history-fork").first();
    await b.focus();
    assert.equal(await b.getAttribute("data-fkey"), "fork:conv-0001-aaaa:0");
    await page.keyboard.press("Enter");
    await page.waitForTimeout(600);
    assert.equal((await calls(page, "brain_history_fork")).length, 1);
    await page.close();
  });

  await browser.close();
  close();
}

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nfork from here holds to the contract");
process.exit(fails.length ? 1 : 0);
