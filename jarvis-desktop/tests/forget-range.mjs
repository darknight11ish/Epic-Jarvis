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
 * - the extended feature (owner, 2026-11-04): the pinned chats are drawn as
 *   KEPT and can never be ticked or sent, the measured estimate is said
 *   before the owner is asked, and the second yes carries the held id and a
 *   literal `true` - with every 400/409 said in the PC's own words;
 * - a stale link greys "Forget these" and the second yes, never Undo;
 * - hidden with the private lists (counts only, Show) - and the PINNED
 *   chats' titles are hidden with the rest;
 * - "forget what you learned last week" in the Jarvis bar opens the Brain
 *   here, with the days filled in (main.js -> brain.js);
 * - CONTROL: the two commands are the Brain's alone; Rust holds "forget" and
 *   "confirm" on a stale link and refuses them while the list is hidden;
 *   Undo is never held; the pinned titles are redacted with the other words;
 * - a11y: every control has a name, the status line is a live region.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  allTicked,
  BRAIN_PLACE_KEY,
  confirmBody,
  EXTRA,
  forgetBody,
  forgetLabel,
  holdLeftLine,
  isHoldId,
  messagesLine,
  pinnedKeptLine,
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

/**
 * The words the contract's `words` map does not carry (the apps lane's half of
 * the 2026-11-04 feature): five of them are the PC's own constants, word for
 * word, and the sixth is this page's one line about how long the second yes
 * has left. Pinned to the backend source, the contract's `confirm_words`, and
 * the phone - so the two apps and the PC cannot drift apart.
 */
await check("the extra words are the PC's own and the phone's, word for word", async () => {
  const py = readRepo("backend/jarvis_forget_range.py").replace(/"\s*\n\s*"/g, "");
  const one = (name) => {
    const at = py.indexOf(`${name} = `);
    assert.ok(at > 0, `the backend has no ${name}`);
    return py.slice(at + name.length + 3).split("\n")[0].replace(/^\(?"|"\)?,?$/g, "");
  };
  assert.equal(EXTRA.pinned_one, one("PINNED_ONE"));
  assert.equal(EXTRA.pinned_many, one("PINNED_MANY"));
  assert.equal(EXTRA.pinned_why, one("PINNED_WHY"));
  assert.equal(EXTRA.confirm_text, one("CONFIRM_TEXT"));
  assert.deepEqual({ yes: EXTRA.confirm_yes, text: EXTRA.confirm_text }, CASES.confirm_words);
  assert.equal(pinnedKeptLine(1), "1 pinned chat is kept");
  assert.equal(pinnedKeptLine(3), "3 pinned chats are kept");
  assert.equal(messagesLine(1), "1 message");
  assert.equal(messagesLine(12), "12 messages");
  assert.equal(holdLeftLine({ expiresIn: 120 }), "2 min left to say yes");
  assert.equal(holdLeftLine({ expiresIn: 30 }), "1 min left to say yes");
  assert.equal(holdLeftLine({ expiresIn: 0 }), "1 min left to say yes");
  const kt = readRepo("jarvis-client/app/src/main/java/com/jarvis/client/net/ForgetRange.kt")
    .replace(/"\s*\+\s*\n\s*"/g, "");
  for (const [key, words] of Object.entries(EXTRA)) {
    assert.ok(kt.includes(`"${key}" to "${words}"`), `the phone does not say ${key}: ${words}`);
  }
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

/**
 * The extended feature's answers (owner, 2026-11-04): the pinned chats kept,
 * the measured estimate, and the held second yes. Nothing here is made up -
 * every one of these bodies is the real backend's.
 */
await check("the extended answers read: pinned kept, the estimate, the held second yes", async () => {
  // The pinned chats are kept: named in `pinned_kept`, counted, and NEVER on
  // the tickable list - so they can never be ticked, counted or sent.
  const pinned = readPreview(C.preview_pinned.body);
  assert.equal(pinned.pinnedKeptCount, 1);
  assert.deepEqual(pinned.pinnedKept, [
    { id: "conv-pinned-01", title: "Pinned planning", messages: 1 }]);
  assert.deepEqual(pinned.chats.map((c) => c.id), ["conv-poem-00002", "conv-trip-00001"]);
  const ticked = allTicked(pinned);
  assert.ok(!ticked.has("chat:conv-pinned-01"), "a pinned chat starts ticked");
  // Even if something ticked one, it is never sent: the PC would refuse it.
  assert.deepEqual(forgetBody(pinned,
    new Set([...ticked, "chat:conv-pinned-01", "chat:conv-poem-00002"])).chats,
  ["conv-poem-00002", "conv-trip-00001"]);
  assert.equal(pinnedKeptLine(pinned.pinnedKeptCount), "1 pinned chat is kept");

  // The measured estimate, said before the owner is asked.
  assert.deepEqual(pinned.estimate, C.preview_pinned.body.estimate);
  assert.equal(pinned.estimate.text,
    "About 1 second to forget 2 facts and delete 2 chats (3 messages).");
  assert.equal(readPreview(C.preview.body).estimate.seconds, 1);

  // The second yes: the held id and a literal `true`, and the PC's sentence.
  const held = readStatus(C.status_confirm.body);
  assert.equal(held.waiting, false);
  assert.deepEqual(held.confirm,
    { id: "hold-id", expiresIn: 120, text: EXTRA.confirm_text });
  assert.equal(held.confirm.text, CASES.confirm_words.text);
  assert.deepEqual(confirmBody(held.confirm.id), { id: "hold-id", yes: true });
  assert.equal(JSON.stringify(confirmBody(held.confirm.id)),
    '{"id":"hold-id","yes":true}', "the second yes is not a literal true");
  for (const bad of ["", "hold id", "a".repeat(129), null, 32]) {
    assert.equal(isHoldId(bad), false, `an id of ${bad} was accepted`);
  }
  assert.equal(isHoldId("0123456789abcdef0123456789abcdef"), true);
  // Nothing is held unless the PC says so: a mistyped block is not a second
  // yes, and no card waiting means none either.
  assert.equal(readStatus(C.status_confirm_expired.body).confirm, null);
  assert.equal(readStatus(C.status_fresh.body).confirm, null);
  assert.equal(readStatus(C.status_waiting.body).confirm, null);
  assert.equal(readStatus({ available: true, confirm: { id: 3 } }).confirm, null);
  // The timed-out hold is not an error state: the PC says what happened.
  assert.equal(readStatus(C.status_confirm_expired.body).last.message,
    "The second yes timed out. Nothing was forgotten or deleted.");
  // The status still says how many pinned chats are kept, and the preview of
  // a plain list carries none of them.
  assert.equal(readStatus(C.status_confirm.body).pinnedKeptCount, 0);
  assert.deepEqual(readPreview(C.preview.body).pinnedKept, []);
});

await check("CONTROL: the Brain's two commands; forget held and hidden-refused in Rust, Undo never", async () => {
  const rs = read("src-tauri/src/brain/forget_range.rs");
  const fn = (name) => {
    const f = rs.slice(rs.indexOf(`pub async fn ${name}(`));
    return f.slice(0, f.indexOf("\n}\n"));
  };
  const w = fn("forget_range_write");
  const forgetArm = w.slice(w.indexOf('"forget" =>'), w.indexOf('"confirm" =>'));
  const confirmArm = w.slice(w.indexOf('"confirm" =>'), w.indexOf('"undo" =>'));
  for (const [name, arm] of [["forget", forgetArm], ["confirm", confirmArm]]) {
    assert.match(arm, /words_hidden\(&app\)[\s\S]*STILL_HIDDEN/, `${name} is not refused on a hidden list`);
    assert.match(arm, /stale\(&app\)[\s\S]*STALE/, `${name} is not held on a stale link`);
  }
  const undoArm = w.slice(w.indexOf('"undo" =>'), w.indexOf("other =>"));
  assert.doesNotMatch(undoArm, /stale|hidden/, "Undo is held or refused");
  assert.match(fn("forget_range_read"), /words_hidden\(&app\)[\s\S]*redact\(answer\)/);
  // The PRIVACY FIX (the backend lane, 2026-11-04): `pinned_kept` carries chat
  // TITLES, so redact() must empty it with the other private lists.
  const redactFn = rs.slice(rs.indexOf("pub(crate) fn redact("));
  assert.match(redactFn.slice(0, 1200), /"pinned_kept"/,
    "redact() leaves the pinned chats' titles in a hidden list");
  // The routes are the contract's, not this app's.
  for (const [name, path] of [["STATUS_PATH", CASES.routes.status],
    ["PREVIEW_PATH", CASES.routes.preview], ["UNDO_PATH", CASES.routes.undo],
    ["CONFIRM_PATH", CASES.routes.confirm]]) {
    assert.ok(rs.includes(`${name}: &str = "${path}"`), `Rust's ${name} is not ${path}`);
  }
  // A body this app can build is only ever the held id and the literal true -
  // the same rule the PC's 400 enforces.
  assert.match(rs, /obj\.get\("yes"\) != Some\(&serde_json::Value::Bool\(true\)\)/,
    "Rust accepts a yes that is not the literal true");
  assert.match(rs, /Ok\(serde_json::json!\(\{ "id": id, "yes": true \}\)\)/,
    "Rust sends something other than the held id and a literal true");
  // The two refusals this app can say before any request is made are the PC's
  // own sentences (jarvis_forget_range.confirm), so a refusal reads the same
  // wherever it comes from.
  const py = readRepo("backend/jarvis_forget_range.py").replace(/"\s*\n\s*"/g, "");
  const rsFlat = rs.replace(/\\\s*\n\s*/g, "");
  for (const [name, words] of [
    ["SECOND_YES_GONE", "There is no second yes waiting - the 2 minutes are up, or it was " +
      "already answered. Nothing was forgotten or deleted."],
    ["SECOND_YES_NOT_LITERAL", 'This needs a literal yes: {"id": "<held id>", "yes": true}. ' +
      "Nothing was forgotten or deleted, and the list is still waiting."],
  ]) {
    const quoted = words.replace(/"/g, '\\"');
    assert.ok(py.includes(quoted), `the backend does not say ${name}: ${words}`);
    assert.ok(rsFlat.includes(quoted), `the desktop does not say ${name} in the PC's words`);
  }
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
 * answered with the real backend's answer. A refusal throws the PC's own
 * sentence with its first letter raised, exactly as `backend_refusal` does.
 *
 * `confirm`/`afterConfirm`: the second yes's answer and the status behind it.
 * A hidden list comes back like the real Rust `redact()`: every word, the
 * pinned chats' titles included, and only the counts left.
 */
async function historyTab({ status = C.status_fresh.body, preview = C.preview.body, link = {},
  forget = C.forget_waiting, afterForget = C.status_waiting.body, undo = C.undo,
  afterUndo = C.status_after_undo.body, confirm = C.confirm,
  afterConfirm = C.status_undo.body, hidden = false, place = false } = {}) {
  const page = await K.open(browser, base, "brain.html", { link }, SIZE);
  await page.evaluate(({ status, preview, forget, afterForget, undo, afterUndo, confirm,
    afterConfirm, hidden }) => {
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
          if (fr.hidden) {
            return { ...fr.preview, facts: [], chats: [], pinned_kept: [], hidden: true };
          }
          return fr.preview;
        }
        if (cmd === "forget_range_write") {
          fr.calls.push([cmd, JSON.parse(JSON.stringify(args || {}))]);
          const a = args.action === "undo" ? undo
            : args.action === "confirm" ? confirm : forget;
          if (a.status >= 400) {
            const e = String(a.body.error || "");
            throw e.charAt(0).toUpperCase() + e.slice(1);
          }
          fr.status = args.action === "undo" ? afterUndo
            : args.action === "confirm" ? afterConfirm : afterForget;
          return { ...a.body, http: a.status };
        }
        return inner(cmd, args);
      };
    };
    install();
  }, { status, preview, forget, afterForget, undo, afterUndo, confirm, afterConfirm, hidden });
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
  // The chat with messages from outside the days starts unticked; ticking it
  // is the owner's own choice, and is kept too (finding 10, 2026-09-28).
  await page.locator("#forget-range .fr-item", { hasText: "poem" }).locator("input").check();
  // Reading the list again keeps what was unticked.
  await showList(page);
  const stillOff = await page.locator("#forget-range .fr-item", { hasText: "Leeds" })
    .locator("input").isChecked();
  const poemOn = await page.locator("#forget-range .fr-item", { hasText: "poem" })
    .locator("input").isChecked();
  assert.equal(stillOff, false, "reading the list again ticked an unticked fact");
  assert.equal(poemOn, true, "reading the list again unticked what the owner ticked");
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
  assert.deepEqual(boxes.filter(([, on]) => !on).map(([k]) => k), ["chat:conv-poem-00002"],
    "only the chat that spills outside the days starts unticked");
  assert.equal(boxes.length, 4);
  assert.equal(label0, "Forget these (3)");
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
  // With a list on the page the answer is read again, and that re-read must
  // not wipe what the PC said (the same bug the second yes had).
  const withList = await historyTab({ status: C.status_undo.body });
  await showList(withList);
  await withList.locator("#forget-range-undo").click();
  await withList.waitForTimeout(400);
  const kept = await withList.locator("#forget-range-said").innerText();
  const listRead = await withList.evaluate(() => window.__fr.calls.filter(([c, a]) => a.preview).length);
  await withList.close();
  assert.equal(kept, "Put back: 2 facts and 2 chats.", "the Undo answer was wiped by the re-read");
  assert.ok(listRead >= 2, "the list under an Undo was not read again");
});

/* ── The extended feature (owner, 2026-11-04) ─────────────────────────── */

await check("the pinned chats are kept: drawn, never tickable, never sent - and the estimate is said", async () => {
  const page = await historyTab({ preview: C.preview_pinned.body });
  await showList(page);
  const text = await page.locator("#forget-range").innerText();
  const keptText = await page.locator("#forget-range .fr-kept").innerText();
  const keptBoxes = await page.locator("#forget-range .fr-kept input").count();
  const keys = await page.locator("#forget-range .fr-item input").evaluateAll(
    (els) => els.map((e) => e.dataset.key));
  const label = await page.locator("#forget-range-go").innerText();
  const errors = page.__errors;
  await page.locator("#forget-range-go").click();
  await page.waitForTimeout(400);
  const sent = await calls(page);
  await page.close();
  assert.ok(text.includes(pinnedKeptLine(1)), `the kept count is not said:\n${text}`);
  assert.ok(text.includes(EXTRA.pinned_why), "why the pinned chats are kept is not said");
  assert.match(keptText, /Pinned planning/);
  assert.match(keptText, /1 message/);
  assert.equal(keptBoxes, 0, "a pinned chat was given a tick box");
  assert.ok(!keys.includes("chat:conv-pinned-01"), "a pinned chat is on the tickable list");
  assert.equal(keys.length, 4, "the tickable list is not the facts and the unpinned chats");
  assert.match(text, /About 1 second to forget 2 facts and delete 2 chats \(3 messages\)\./,
    "the measured estimate is not said before asking");
  assert.equal(label, "Forget these (3)");
  assert.deepEqual(sent, [["forget_range_write", { action: "forget", body: {
    from: "2026-09-01", to: "2026-09-15", facts: [1, 2], chats: ["conv-trip-00001"] } }]]);
  assert.ok(!JSON.stringify(sent).includes("conv-pinned-01"), "a pinned chat was sent");
  assert.deepEqual(errors, []);
});

await check("the second yes: the held id and a literal true, then the Undo banner stays 10 minutes", async () => {
  const page = await historyTab({ status: C.status_confirm.body });
  const block = await page.locator(".fr-confirm").innerText();
  const label = await page.locator("#forget-range-confirm").innerText();
  const named = await page.getByRole("button", { name: EXTRA.confirm_yes, exact: true }).count();
  const readsBefore = await page.evaluate(
    () => window.__fr.calls.filter(([c, a]) => c === "forget_range_read" && !a.preview).length);
  await page.locator("#forget-range-confirm").click();
  await page.waitForTimeout(500);
  const sent = await calls(page);
  const after = await page.locator("#forget-range").innerText();
  const confirmGone = await page.locator(".fr-confirm").count();
  const banner = await page.locator(".fr-undo").innerText();
  const said = await page.locator("#forget-range-said").innerText();
  const readsAfter = await page.evaluate(
    () => window.__fr.calls.filter(([c, a]) => c === "forget_range_read" && !a.preview).length);
  const errors = page.__errors;
  await page.close();
  assert.ok(block.includes(EXTRA.confirm_text), `the PC's second-yes sentence is not shown:\n${block}`);
  assert.match(block, /2 min left to say yes/);
  assert.equal(label, EXTRA.confirm_yes);
  assert.equal(named, 1, "the second yes has no accessible name");
  // The literal `true`, and the id the PC is holding - nothing else at all.
  assert.equal(sent.length, 1);
  assert.deepEqual(sent[0], ["forget_range_write", { action: "confirm", body: { id: "hold-id", yes: true } }]);
  assert.equal(JSON.stringify(sent[0][1].body), '{"id":"hold-id","yes":true}');
  assert.equal(confirmGone, 0, "the second yes is still offered after it was answered");
  assert.match(banner, /10 min left to undo/, "the 10-minute Undo is not kept after the second yes");
  assert.equal(said, "Forgot 2 facts and deleted 2 chats. Undo is available for 10 minutes.");
  assert.ok(readsAfter > readsBefore, "the status was not read again after the second yes");
  assert.match(after, /Forgot 2 facts and deleted 2 chats from 1 to 15 September 2026\./);
  assert.deepEqual(errors, []);
});

await check("every refusal of the second yes is said in the PC's own words, never silently", async () => {
  // All of the PC's second-yes refusals: a `yes` that is not literally true
  // (400), a wrong id, an expired or missing hold, a card still waiting, an
  // Undo already open (409). Each one is a sentence on the page - and the
  // status is read again after it, because the card or the hold has moved on.
  const names = ["confirm_not_literal", "confirm_wrong_id", "confirm_twice",
    "confirm_while_card", "confirm_before_card", "confirm_no_hold", "confirm_expired"];
  for (const name of names) {
    const page = await historyTab({ status: C.status_confirm.body, confirm: C[name] });
    const readsBefore = await page.evaluate(
      () => window.__fr.calls.filter(([c, a]) => c === "forget_range_read" && !a.preview).length);
    await page.locator("#forget-range-confirm").click();
    await page.waitForTimeout(350);
    const said = await page.locator("#forget-range-said").innerText();
    const tone = await page.locator("#forget-range-said").getAttribute("data-tone");
    const readsAfter = await page.evaluate(
      () => window.__fr.calls.filter(([c, a]) => c === "forget_range_read" && !a.preview).length);
    const errors = page.__errors;
    await page.close();
    const words = String(C[name].body.error);
    assert.equal(said, words, `${name} was not said in the PC's own words`);
    assert.equal(tone, "bad", `${name} was not marked as a refusal`);
    assert.ok(readsAfter > readsBefore, `${name} did not read the status again`);
    assert.deepEqual(errors, [], `${name} threw out of the page`);
  }
  // The list on the page is read again after a refusal, not left as it was:
  // a 409 means something on it moved (the contract's own instruction is
  // "read the list again"). Only the reads are asserted - which sentence the
  // PC sends for "the items changed" is the backend's to say, and this
  // contract file has no confirm case for it, so none is invented here.
  const again = await historyTab({ status: C.status_confirm.body,
    confirm: C.confirm_wrong_id, preview: C.preview_pinned.body });
  await again.locator("#forget-range-show").click();
  await again.waitForTimeout(300);
  const listsBefore = await again.evaluate(
    () => window.__fr.calls.filter(([c, a]) => a.preview).length);
  await again.locator("#forget-range-confirm").click();
  await again.waitForTimeout(400);
  const listsAfter = await again.evaluate(
    () => window.__fr.calls.filter(([c, a]) => a.preview).length);
  const said = await again.locator("#forget-range-said").innerText();
  await again.close();
  assert.ok(listsAfter > listsBefore, "the list was not read again after a refusal");
  assert.match(said, /That is not the second yes waiting/);
});

await check("a stale link greys the second yes too, and a held second yes greys Forget these", async () => {
  const stale = await historyTab({ status: C.status_confirm.body, link: { stale: true } });
  const disabled = await stale.locator("#forget-range-confirm").isDisabled();
  const title = await stale.locator("#forget-range-confirm").getAttribute("title");
  await stale.close();
  assert.equal(disabled, true, "the second yes is offered on a stale link");
  assert.equal(title, WORDS.stale);
  // While the PC holds a second yes, "Forget these" cannot start another one.
  const held = await historyTab({ status: C.status_confirm.body, preview: C.preview_pinned.body });
  await showList(held);
  const goDisabled = await held.locator("#forget-range-go").isDisabled();
  await held.close();
  assert.equal(goDisabled, true, "Forget these is offered while a second yes is held");
});

await check("hidden with the private lists: the pinned chats' titles are hidden too", async () => {
  const page = await historyTab({ hidden: true, preview: C.preview_pinned.body });
  await showList(page);
  const text = await page.locator("#forget-range").innerText();
  const kept = await page.locator("#forget-range .fr-kept").count();
  const confirm = await page.locator("#forget-range-go").count();
  await page.close();
  assert.match(text, /4 items, hidden until Windows Hello confirms it is you\./);
  assert.doesNotMatch(text, /Pinned planning|conv-pinned-01/,
    "a hidden list still names the pinned chats");
  assert.equal(kept, 0);
  assert.equal(confirm, 0, "Forget these offered on a hidden list");
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
