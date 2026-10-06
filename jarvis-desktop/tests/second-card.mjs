/**
 * Settings -> Second graphics card, and the two other places the desktop
 * meets the second card: the picture check and the model badge.
 *
 * Every status here is REAL: `K.SECOND_CARD` is
 * tests/fixtures/second-card-cases.json, jarvis_second_card.status() for six
 * cases, written by tools/gen_second_card_cases.py. Nothing is hand-made.
 *
 * What must hold (docs/SECOND-CARD.md, JARVIS-API.md section 12):
 * - every switch is visible, and none can be turned on without a capable
 *   second card - the reason is said in the backend's own words;
 * - turning a switch ON sends one request and raises a card; the switch
 *   stays off and says it is waiting until the card is decided;
 * - the page re-reads when the approval queue changes and, gently, while a
 *   card waits - there is no event for the decision;
 * - turning a switch OFF is immediate;
 * - an older backend, or no answer, is a sentence - never a code or JSON.
 *
 * The CONTROL checks read the Rust: the header and token, and that only the
 * settings window may call these commands.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const SC = K.SECOND_CARD;

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const VIEW = { width: 760, height: 1400 };
const open = (secondCard) => K.open(browser, base, "settings.html", { secondCard }, VIEW);

/** Everything the section shows, read off the page. */
const section = (page) => page.evaluate(() => {
  const $ = (id) => document.getElementById(id);
  const rows = [...document.querySelectorAll("#sc-switches .sc-switch")].map((row) => {
    const input = row.querySelector("input[type=checkbox]");
    return {
      id: row.dataset.id,
      state: row.dataset.state,
      checked: input.checked,
      disabled: input.disabled,
      text: row.innerText,
      describedBy: input.getAttribute("aria-describedby") || "",
    };
  });
  return {
    stateHidden: $("sc-state").hidden,
    state: $("sc-state").innerText,
    bodyHidden: $("sc-body").hidden,
    found: $("sc-found").innerText,
    cards: [...document.querySelectorAll("#sc-cards li")].map((li) => li.innerText),
    blockedHidden: $("sc-blocked").hidden,
    blocked: $("sc-blocked").innerText,
    rows,
    status: $("sc-status").innerText,
    lane: $("sc-lane").innerText,
    pinned: $("sc-pinned").innerText,
    chatWhere: $("sc-chat-where").innerText,
    chatChoices: [...document.querySelectorAll("#sc-chat-choices input[type=radio]")]
      .map((input) => ({ value: input.value, checked: input.checked, disabled: input.disabled,
                         text: input.closest("label").innerText })),
    analysisToggle: $("sc-analysis-toggle")?.innerText ?? "",
    analysisHidden: $("sc-analysis")?.hidden ?? true,
    analysisCards: [...document.querySelectorAll("#sc-analysis-cards .sc-analysis-card")]
      .map((d) => d.innerText),
    analysisSuggestion: $("sc-analysis-suggestion")?.innerText ?? "",
    pinProblemHidden: $("sc-pin-problem")?.hidden ?? true,
    pinProblem: $("sc-pin-problem-words")?.innerText ?? "",
    pinHidden: $("sc-pin").hidden,
    pinCommand: $("sc-pin-command").value,
    pinReadOnly: $("sc-pin-command").readOnly,
    all: $("second-card").innerText,
    reads: window.__secondCard.reads,
    changes: window.__secondCard.changes,
    suggestTitleHidden: $("sc-suggest-title").hidden,
    suggestDetail: $("sc-suggest-detail").innerText,
    suggestSignalsHidden: $("sc-suggest-signals").hidden,
    suggestRows: [...document.querySelectorAll("#sc-suggest-signals input[type=checkbox]")]
      .map((input) => ({ id: input.dataset.signal, checked: input.checked,
                         text: input.closest("label").innerText })),
    thirdSectionHidden: $("sc-third-section").hidden,
    thirdFound: $("sc-third-found").innerText,
    thirdSelectOptions: [...($("sc-third-select")?.options || [])].map((o) => o.value),
    thirdSelectValue: $("sc-third-select")?.value ?? null,
    thirdSelectDisabled: $("sc-third-select")?.disabled ?? null,
    thirdMoveDisabled: $("sc-third-move")?.disabled ?? null,
    thirdText: $("sc-third")?.innerText ?? "",
    thirdStatus: $("sc-third-status").innerText,
  };
});
const suggestRow = (s, id) => s.suggestRows.find((r) => r.id === id);
const row = (s, id) => s.rows.find((r) => r.id === id);
const noRaw = (text) => {
  assert.doesNotMatch(text, /[{}]|HTTP \d|"available"|null|undefined|\[object/,
    `raw data on the page: ${text}`);
};

/* ── What was found ─────────────────────────────────────────────────────── */

await check("one card (today's PC): found in words, every switch shown and none can be turned on", async () => {
  const page = await open({ status: SC.one_card });
  const s = await section(page);
  await page.close();
  assert.equal(s.bodyHidden, false);
  assert.match(s.found, /Only one graphics card found \(the NVIDIA GeForce RTX 2080 SUPER\)\./);
  assert.equal(s.cards.length, 1);
  assert.match(s.cards[0], /NVIDIA GeForce RTX 2080 SUPER \(8 GB\)/);
  // 2026-10-05: no longer "everyday chat runs here". With nothing pinned,
  // Jarvis must not say which card chat is on - the PC's own sentence says
  // only what the settings are made for.
  assert.match(s.cards[0], /The one chat runs on\. Jarvis's own settings are made for this card/);
  assert.match(s.cards[0], /you have not pinned a card, so Jarvis cannot say everyday chat is on it/);
  assert.equal(s.blockedHidden, false);
  assert.match(s.blocked, /8 GB or more\): only one graphics card found \(the NVIDIA GeForce RTX 2080 SUPER\)\. /);
  // The master switch and all seven features, in the backend's order.
  assert.deepEqual(s.rows.map((r) => r.id),
    ["master", ...SC.one_card.features.map((f) => f.id)]);
  for (const r of s.rows) {
    assert.equal(r.disabled, true, `${r.id} can be turned on with no capable card`);
    assert.equal(r.checked, false, `${r.id} is on`);
    assert.match(r.describedBy, /sc-blocked/, `${r.id} is not tied to the reason it is off`);
  }
  assert.match(row(s, "master").text, /Use the second graphics card/);
  for (const f of SC.one_card.features) {
    const r = row(s, f.id);
    assert.ok(r.text.includes(f.name), `${f.id}: no name`);
    assert.ok(r.text.includes(f.what), `${f.id}: no "what"`);
    assert.ok(r.text.includes(f.why), `${f.id}: no "why"`);
  }
  // No pin command with one card; the note says why.
  assert.equal(s.pinHidden, true);
  assert.match(s.pinned, /Only one graphics card, so there is nothing to keep apart yet\./);
  assert.match(s.lane, /^Off\. No capable second card/);  noRaw(s.all);
});

await check("an old second card: listed as not used, with the backend's reason", async () => {
  const page = await open({ status: SC.not_capable_old_card });
  const s = await section(page);
  await page.close();
  assert.equal(s.cards.length, 2);
  assert.match(s.cards[1], /NVIDIA GeForce GTX 1080 \(8 GB\)/);
  assert.match(s.cards[1], /Not used\. The NVIDIA GeForce GTX 1080 is older than Turing/);
  assert.match(s.blocked, /older than Turing/);
  assert.ok(s.rows.every((r) => r.disabled), "a switch can be turned on beside an old card");
  noRaw(s.all);
});

await check("a capable card, all off: only the main switch can be turned on, and the rest say why", async () => {
  const page = await open({ status: SC.capable_off });
  const s = await section(page);
  await page.close();
  assert.match(s.found, /The NVIDIA GeForce RTX 2060 \(12 GB\) can take the second-card features/);
  assert.match(s.cards[0], /The one chat runs on/);
  assert.match(s.cards[1], /NVIDIA GeForce RTX 2060 \(12 GB\)/);
  assert.match(s.cards[1], /The second card\. The second-card features would run here\./);
  assert.equal(s.blockedHidden, true);
  assert.equal(row(s, "master").disabled, false, "the main switch cannot be turned on");
  for (const f of SC.capable_off.features) {
    const r = row(s, f.id);
    assert.equal(r.disabled, true, `${f.id} can be turned on with the main switch off`);
    assert.match(r.text, /Turn on "Use the second graphics card" first\./);
  }
});

await check("each feature says its model, whether it is installed, the exact name to install, and its memory", async () => {
  const page = await open({ status: SC.capable_off });
  const s = await section(page);
  const switchesHtml = await page.$eval("#sc-switches", (el) => el.innerHTML);
  await page.close();
  const vision = row(s, "vision").text;
  assert.match(vision, /Model: qwen2\.5vl:7b, not installed yet\./);
  assert.match(vision, /open the Brain window, go to Model, then Models, type qwen2\.5vl:7b in the Install box/);
  assert.match(vision, /Uses about 7\.2 GB of the second card's memory\./);
  const long = row(s, "long_context").text;
  assert.match(long, /Model: qwen3:8b, installed\./);
  assert.match(long, /Uses about 7\.7 GB/);
  assert.doesNotMatch(long, /Install box/);
  // Browser control needs Longer conversations: the backend's own line says so.
  const browserText = row(s, "browser_control").text;
  assert.match(browserText, /Needs Longer conversations on first\./);
  assert.equal((browserText.match(/Needs/g) || []).length, 1, "the same need is said twice");
  // No catalogue: nothing in the switches themselves offers a MODEL to
  // choose from - scoped to #sc-switches, not the whole page, since the
  // third card's own <select> (2026-09-28) picks a FEATURE, never a
  // model, and legitimately lives in the same "sc-" naming convention
  // every element on this page already uses (#sc-third-section, below).
  assert.doesNotMatch(switchesHtml, /<select/, "a model picker appeared");
});

await check("Study helper and Referee suggestions: seven rows from features[], and Referee never mentions a model or memory (13.5 #2)", async () => {
  const ids = ["long_context", "vision", "learning", "browser_control", "wiki", "study", "referee"];
  for (const name of Object.keys(SC)) {
    assert.deepEqual(SC[name].features.map((f) => f.id), ids, `${name}: not the seven rows`);
  }
  // Capable PC, everything off: Study has its model line, Referee has none.
  const page = await open({ status: SC.capable_off });
  const s = await section(page);
  await page.close();
  assert.deepEqual(s.rows.map((r) => r.id), ["master", ...ids]);
  const study = row(s, "study").text;
  assert.match(study, /Study helper/);
  assert.match(study, /Model: qwen3:8b, installed\./);
  assert.match(study, /Uses about 7\.7 GB/);
  const ref = row(s, "referee").text;
  assert.match(ref, /Referee suggestions/);
  assert.ok(ref.includes(SC.capable_off.features.find((f) => f.id === "referee").what), "no 'what'");
  assert.doesNotMatch(ref, /chosen once a capable second card/, "the wrong 'model is chosen once...' line");
  assert.doesNotMatch(ref, /Model:|GB of the second card/, "a model or memory line under Referee");
  noRaw(ref);
});

await check("Referee suggestions on one card: the plain reason is shown, and still no model line; Study keeps the 'chosen once' line", async () => {
  const page = await open({ status: SC.one_card });
  const s = await section(page);
  await page.close();
  const ref = row(s, "referee");
  assert.equal(ref.disabled, true);
  assert.match(ref.text, /Needs a capable second graphics card: only one graphics card found/);
  // Not capable: the old wording stays for a model-using switch...
  assert.match(row(s, "study").text, /The model is chosen once a capable second card is found\./);
  // ...and a model-free switch never talks about a model (model_free, when the PC says it).
  const status = JSON.parse(JSON.stringify(SC.one_card));
  status.features.find((f) => f.id === "referee").model_free = true;
  const page2 = await open({ status });
  const s2 = await section(page2);
  await page2.close();
  assert.doesNotMatch(row(s2, "referee").text, /model is chosen|Model:|GB of the second/);
});

await check("Referee working: the backend's own 'Working' line, no model or memory line, and OFF is immediate", async () => {
  const status = JSON.parse(JSON.stringify(SC.capable_off));
  status.enabled = true;
  const f = status.features.find((x) => x.id === "referee");
  Object.assign(f, { enabled: true, active: true, available: true,
    why: "Working: it compares the numbers you log with your targets on this PC and loads no model, so it uses none of the card's memory yet." });
  const page = await open({ status });
  const s = await section(page);
  await page.close();
  const r = row(s, "referee");
  assert.equal(r.state, "on");
  assert.equal(r.disabled, false, "a working switch cannot be turned off");
  assert.ok(r.text.includes(f.why));
  assert.doesNotMatch(r.text, /Model:|chosen once|GB of the second card/);
});

await check("the pin command: exactly the backend's line, read-only, with Copy and what it does", async () => {
  const page = await open({ status: SC.capable_off });
  const s = await section(page);
  const copy = await page.locator("#sc-pin-copy").innerText();
  await page.locator("#sc-pin-copy").click();
  await page.waitForTimeout(200);
  const said = await page.locator("#sc-pin-status").innerText();
  await page.close();
  assert.equal(s.pinHidden, false);
  assert.equal(s.pinCommand, SC.capable_off.pin_command);
  assert.equal(s.pinReadOnly, true);
  assert.equal(copy, "Copy");
  assert.match(said, /Copied|Ctrl\+C/);
  assert.match(s.all, /sets two Windows settings for your user account/);
  assert.match(s.all, /Nothing is written to any file/);
  assert.match(s.pinned, /The everyday Ollama is not pinned/);
});

/* ── "Everyday chat runs on" (2026-10-05) ──────────────────────────────── */

await check("the two choices, where the model really is, and the analysis - the backend's own words", async () => {
  const page = await open({ status: SC.capable_off });
  const s = await section(page);
  // "Show the analysis" is closed until it is asked for.
  assert.equal(s.analysisHidden, true);
  assert.equal(s.analysisToggle, "Show the analysis");
  await page.locator("#sc-analysis-toggle").click();
  await page.waitForTimeout(100);
  const opened = await section(page);
  await page.close();
  // One choice per card, plus "Let Ollama decide" - which is the one ticked.
  assert.deepEqual(s.chatChoices.map((c) => c.value),
    ["leave", SC.capable_off.chat_card.cards[0].uuid, SC.capable_off.chat_card.cards[1].uuid]);
  assert.equal(s.chatChoices.filter((c) => c.checked).length, 1);
  assert.equal(s.chatChoices[0].checked, true);
  assert.match(s.chatChoices[0].text, /Let Ollama decide/);
  assert.match(s.chatChoices[0].text, /Ollama's own choice/);
  assert.match(s.chatChoices[1].text, /Always use the NVIDIA GeForce RTX 2080 SUPER \(8 GB\)/);
  assert.match(s.chatChoices[1].text, /One approval card/);
  // The line under them is the PC's reading, not a guess.
  assert.equal(s.chatWhere, SC.capable_off.chat_card.where.words);
  // Nothing claimed done that is not: the PC sends problem "" here.
  assert.equal(s.pinProblemHidden, true);
  // The analysis is every fact the PC reports, and the measured lines.
  assert.equal(opened.analysisHidden, false);
  assert.equal(opened.analysisToggle, "Hide the analysis");
  assert.equal(opened.analysisCards.length, SC.capable_off.chat_card.cards.length);
  for (const card of SC.capable_off.chat_card.cards) {
    const shown = opened.analysisCards.find((t) => t.includes(card.name));
    assert.ok(shown, `${card.name} is missing from the analysis`);
    for (const line of card.facts) assert.ok(shown.includes(line), `${card.name}: ${line}`);
    for (const line of card.measured) assert.ok(shown.includes(line), `${card.name}: ${line}`);
  }
  assert.equal(opened.analysisSuggestion, SC.capable_off.chat_card.suggestion.words);
  assert.match(opened.analysisSuggestion, /^Jarvis's suggestion:/);
  // Measured or silent: no speed claim anywhere on the page.
  assert.doesNotMatch(opened.all, /\d+ GB\/s|tokens per second|tok\/s|is faster than/);
});

await check("picking a card sends ONE pin request for that card's id, and nothing turns on by itself", async () => {
  const page = await open({ status: SC.capable_off });
  const card = SC.capable_off.chat_card.cards[1];
  await page.locator(`#sc-chat-pin-${card.index}`).click();
  await page.waitForTimeout(300);
  const s = await section(page);
  const calls = await page.evaluate(() => window.__calls.map(([c]) => c));
  await page.close();
  assert.deepEqual(s.changes, [{ feature: "chat_card", action: "pin", card: card.uuid }]);
  assert.ok(!calls.includes("decide_approval"), "the page answered its own card");
  assert.match(s.status, /Waiting for your approval/);
  // Shown as the PC last reported: still "leave", never the card just picked.
  assert.equal(s.chatChoices[0].checked, true);
});

await check("going back to Ollama's own choice is immediate and needs no card", async () => {
  const pinned = {
    ...SC.capable_off,
    chat_card: {
      ...SC.capable_off.chat_card,
      chosen: SC.capable_off.chat_card.cards[1].uuid,
      chosen_name: SC.capable_off.chat_card.cards[1].name,
      problem: "",
    },
  };
  const page = await open({ status: pinned });
  await page.locator("#sc-chat-leave").click();
  await page.waitForTimeout(300);
  const s = await section(page);
  await page.close();
  assert.deepEqual(s.changes, [{ feature: "chat_card", action: "leave", card: null }]);
  assert.match(s.chatChoices.find((c) => c.value === "leave").text, /Let Ollama decide/);
  assert.match(s.status, /Ollama/);
});

await check("a pin Ollama is not using is said plainly, never shown as done", async () => {
  const pinned = {
    ...SC.capable_off,
    chat_card: {
      ...SC.capable_off.chat_card,
      chosen: SC.capable_off.chat_card.cards[1].uuid,
      chosen_name: SC.capable_off.chat_card.cards[1].name,
      problem: "Ollama does not have this pin yet: quit Ollama and start it again after "
        + "Jarvis sets it, or run the line below yourself.",
      pin_command: SC.capable_off.pin_command,
    },
  };
  const page = await open({ status: pinned });
  const s = await section(page);
  await page.close();
  assert.equal(s.pinProblemHidden, false);
  assert.match(s.pinProblem, /does not have this pin yet/);
  assert.equal(s.pinHidden, false);
});

/* ── Switching ─────────────────────────────────────────────────────────── */

await check("turning the main switch ON sends one request, raises a card, and stays off while it waits", async () => {
  const page = await open({ status: SC.capable_off });
  // click(), not check(): the box must NOT stay ticked, and check() insists it does.
  await page.locator("#sc-switch-master").click();
  await page.waitForTimeout(300);
  const s = await section(page);
  const calls = await page.evaluate(() => window.__calls.map(([c]) => c));
  await page.close();
  assert.deepEqual(s.changes, [{ feature: "master", enabled: true }]);
  assert.ok(!calls.includes("decide_approval"), "the page answered its own card");
  const master = row(s, "master");
  assert.equal(master.checked, false, "shown as on before the card was approved");
  assert.equal(master.disabled, true, "a second card could be raised for the same switch");
  assert.equal(master.state, "waiting");
  assert.match(master.text, /Waiting for your approval\. Approve it in the Jarvis bar, on the widget, or on your phone's Home screen/);
  assert.match(s.status, /Waiting for your approval/);
  // The same words the Brain's model install uses while its card waits.
  assert.ok(read("src/brain.js").includes(
    "Approve it ${APPROVE_WHERE} — nothing changes until you do."));
});

await check("a card already waiting: that switch says so, and the others stay usable", async () => {
  const page = await open({ status: SC.capable_pending });
  const s = await section(page);
  await page.close();
  const long = row(s, "long_context");
  assert.equal(long.state, "waiting");
  assert.equal(long.disabled, true);
  assert.equal(long.checked, false);
  assert.match(long.text, /Waiting for your approval/);
  assert.equal(row(s, "master").checked, true);
  assert.equal(row(s, "vision").disabled, false, "Pictures cannot be asked for while another card waits");
  assert.equal(row(s, "browser_control").disabled, true);
  assert.match(row(s, "browser_control").text, /Needs Longer conversations on first/);
});

/* ── A third graphics card (2026-09-28) ───────────────────────────────────
 * jarvis_second_card.py's own status()["third"]: purely additive, so none
 * of the fixture's six named cases carry it - each check below clones a
 * real case and adds a "third" object in the exact shape the backend
 * really answers (checked against tools/gen_second_card_cases.py's own
 * output for backend/test_second_card.py). */

const withThird = (base, third) => ({ ...JSON.parse(JSON.stringify(base)), third });

const THIRD_CARD = { uuid: "GPU-3rd", index: 2, name: "NVIDIA GeForce RTX 2080 Ti",
  total_mb: 11264, compute_cap: 7.5 };

await check("no capable third card: the section stays hidden", async () => {
  const page = await open({ status: withThird(SC.capable_off,
    { capable: false, card: null, assigned: null, assignable: [], pending: false,
      lane: { state: "off", why: "no capable third graphics card" },
      model: null, context: null, memory_gib: null, model_installed: null,
      why: "No capable third graphics card is plugged in right now." }) });
  const s = await section(page);
  await page.close();
  assert.equal(s.thirdSectionHidden, true);
});

await check("a capable third card, nothing assigned: shown, 'Not used', no default winner", async () => {
  const page = await open({ status: withThird(SC.capable_off,
    { capable: true, card: THIRD_CARD, assigned: null, assignable: [], pending: false,
      lane: { state: "off", why: "no feature is assigned to the third card" },
      model: null, context: null, memory_gib: null, model_installed: null,
      why: "Not running anything. Assign one of the switches above to the "
          + "NVIDIA GeForce RTX 2080 Ti to use it." }) });
  const s = await section(page);
  await page.close();
  assert.equal(s.thirdSectionHidden, false);
  assert.match(s.thirdFound, /NVIDIA GeForce RTX 2080 Ti \(11 GB\)/);
  assert.deepEqual(s.thirdSelectOptions, [""], "an option was offered with nothing turned on");
  assert.equal(s.thirdSelectValue, "");
  assert.equal(s.thirdSelectDisabled, false);
  assert.match(s.thirdText, /Not running anything\. Assign/);
});

await check("only switches that are actually on can be moved here", async () => {
  const status = withThird(SC.capable_off,
    { capable: true, card: THIRD_CARD, assigned: null,
      assignable: ["long_context", "vision"], pending: false,
      lane: { state: "off", why: "no feature is assigned to the third card" },
      model: null, context: null, memory_gib: null, model_installed: null,
      why: "Not running anything. Assign one of the switches above to the "
          + "NVIDIA GeForce RTX 2080 Ti to use it." });
  const page = await open({ status });
  const s = await section(page);
  await page.close();
  assert.deepEqual(s.thirdSelectOptions.sort(), ["", "long_context", "vision"].sort());
  assert.ok(!s.thirdSelectOptions.includes("browser_control"),
    "an off switch was offered as an assignable option");
});

await check("moving a switch here sends assign, and waits for its own card", async () => {
  const status = withThird(SC.capable_off,
    { capable: true, card: THIRD_CARD, assigned: null,
      assignable: ["long_context"], pending: false,
      lane: { state: "off", why: "no feature is assigned to the third card" },
      model: null, context: null, memory_gib: null, model_installed: null, why: "Not running anything." });
  const page = await open({ status });
  await page.locator("#sc-third-select").selectOption("long_context");
  await page.locator("#sc-third-move").click();
  await page.waitForTimeout(300);
  const s = await section(page);
  await page.close();
  assert.deepEqual(s.changes, [{ assign: "long_context" }]);
  assert.match(s.thirdStatus, /Waiting for your approval/);
  assert.equal(s.thirdSelectDisabled, true);
});

await check("moving it back off (assign: null) is at once, no card", async () => {
  const status = withThird(SC.capable_off,
    { capable: true, card: THIRD_CARD, assigned: "vision",
      assignable: ["vision"], pending: false,
      lane: { state: "running", why: "running on 127.0.0.1:11436 (this PC only)" },
      model: "qwen2.5vl:7b", context: 16384, memory_gib: 7.15, model_installed: true,
      why: "Working: qwen2.5vl:7b on the NVIDIA GeForce RTX 2080 Ti, with room for "
          + "16,384 tokens - at the same time as the second card's own lane." });
  const page = await open({ status });
  const before = await section(page);
  assert.equal(before.thirdSelectValue, "vision");
  await page.locator("#sc-third-select").selectOption("");
  await page.locator("#sc-third-move").click();
  await page.waitForTimeout(300);
  const s = await section(page);
  await page.close();
  assert.deepEqual(s.changes, [{ assign: null }]);
  assert.match(s.thirdStatus, /not running anything/i);
});

await check("when the approval queue changes, the page re-reads and shows what the card decided", async () => {
  const page = await open({ status: SC.capable_pending });
  const before = await page.evaluate(() => window.__secondCard.reads);
  // The card was approved: the backend now reports the real running case.
  await page.evaluate((next) => {
    window.__secondCard.status = next;
    window.__emit("approvals-changed", { count: 0, items: [] });
  }, SC.running_long_context);
  await page.waitForTimeout(300);
  const s = await section(page);
  await page.close();
  assert.ok(s.reads > before, "the decision did not make the page read again");
  const long = row(s, "long_context");
  assert.equal(long.checked, true);
  assert.equal(long.state, "on");
  assert.match(long.text, /Working: qwen3:8b on the NVIDIA GeForce RTX 2060/);
  assert.match(s.status, /"Longer conversations" is on\./);
  assert.match(s.lane, /^Running\. Running on 127\.0\.0\.1:11435 \(this PC only\)/);
  assert.match(s.pinned, /Ollama is set to use only the NVIDIA GeForce RTX 2080 SUPER/);
});
await check("a denied card: the switch is still off, and the page says it was not turned on", async () => {
  const page = await open({ status: SC.capable_pending });
  await page.evaluate((next) => {
    window.__secondCard.status = next;
    window.__emit("approvals-changed", { count: 0, items: [] });
  }, { ...SC.capable_pending, pending: [] });
  await page.waitForTimeout(300);
  const s = await section(page);
  await page.close();
  assert.equal(row(s, "long_context").checked, false);
  assert.match(s.status, /"Longer conversations" was not turned on/);
});

// AP-6 (audit 3): the page always said "denied or ran out of time". A
// backend with status().last ({feature, outcome, why, at}) says what really
// happened; one without it keeps the old words. The fixture may not have
// `last` yet, so these add it to a real status.
const endedWith = async (last, feature = "long_context") => {
  const page = await open({ status: SC.capable_pending });
  await page.evaluate(({ next, last }) => {
    if (last) next.last = { ...last, at: last.at ?? Date.now() / 1000 };
    window.__secondCard.status = next;
    window.__emit("approvals-changed", { count: 0, items: [] });
  }, { next: { ...SC.capable_pending, pending: [] }, last: last && { feature, ...last } });
  await page.waitForTimeout(300);
  const s = await section(page);
  await page.close();
  return s.status;
};

await check("how a card ended comes from the backend's `last`: denied, expired, refused, failed, withdrawn", async () => {
  const L = '"Longer conversations"';
  assert.match(await endedWith({ outcome: "denied" }), new RegExp(`${L} was not turned on: the card was denied\\.$`));
  assert.match(await endedWith({ outcome: "expired" }), /ran out of time before anyone answered it/);
  assert.match(await endedWith({ outcome: "timed_out" }), /ran out of time before anyone answered it/);
  const refused = await endedWith({ outcome: "refused", why: "the second card is not capable" });
  assert.match(refused, /Jarvis refused it\. The second card is not capable\./);
  const failed = await endedWith({ outcome: "failed", why: "ollama did not start on the second card" });
  assert.match(failed, /was approved, but turning it on failed\. Ollama did not start on the second card\./);
  assert.match(await endedWith({ outcome: "withdrawn" }), /the card was withdrawn before it was answered/);
  for (const words of [await endedWith({ outcome: "denied" }), refused, failed]) {
    assert.doesNotMatch(words, /denied or ran out of time/);
  }
});

await check("CONTROL: with no `last` (an older backend), or one about another switch or an older card, the old words stay", async () => {
  const OLD = /"Longer conversations" was not turned on: the card was denied or ran out of time\./;
  assert.match(await endedWith(null), OLD);
  assert.match(await endedWith({ outcome: "denied" }, "vision"), OLD);
  assert.match(await endedWith({ outcome: "denied", at: Date.now() / 1000 - 3600 }), OLD);
  assert.match(await endedWith({ outcome: "something new" }), OLD);
});

await check("while a card waits and nothing else happens, the page re-reads gently on its own", async () => {
  const page = await open({ status: SC.capable_pending });
  const first = await page.evaluate(() => window.__secondCard.reads);
  await page.waitForTimeout(5600);
  const later = await page.evaluate(() => window.__secondCard.reads);
  await page.close();
  assert.ok(later > first, "no re-read while the card waited");
  assert.ok(later - first <= 2, `re-read ${later - first} times in under six seconds - not gentle`);
  // And with nothing waiting, it does not poll at all.
  const quiet = await open({ status: SC.capable_off });
  const a = await quiet.evaluate(() => window.__secondCard.reads);
  await quiet.waitForTimeout(5600);
  const b = await quiet.evaluate(() => window.__secondCard.reads);
  await quiet.close();
  assert.equal(b, a, "polled with no card waiting");
});

await check("turning a switch OFF is immediate", async () => {
  const page = await open({ status: SC.running_long_context });
  await page.locator("#sc-switch-long_context").click();
  await page.waitForTimeout(300);
  const s = await section(page);
  await page.close();
  assert.deepEqual(s.changes, [{ feature: "long_context", enabled: false }]);
  assert.equal(row(s, "long_context").checked, false);
  assert.equal(row(s, "long_context").state, "off");
  assert.match(s.status, /"Longer conversations" is off\./);
});

await check("pressing Space on a switch keeps keyboard focus in place (bug audit 2026-09-27 #5)", async () => {
  // Disabling the focused checkbox before the request (`scToggle`) blurs it
  // to <body> at once in Chromium; the redraw's focus-restore must not rely
  // on reading `document.activeElement` again after that has happened.
  const page = await open({ status: SC.running_long_context });
  await page.locator("#sc-switch-long_context").focus();
  await page.keyboard.press("Space");
  await page.waitForTimeout(300);
  const focused = await page.evaluate(() => document.activeElement.id);
  const s = await section(page);
  await page.close();
  assert.equal(row(s, "long_context").checked, false, "the switch itself did not toggle");
  assert.equal(focused, "sc-switch-long_context", "focus landed on <body> instead of staying on the switch");
});

await check("a toggle whose re-read FAILS does not yank focus back on a later, unrelated repaint (Opus 5.5 re-check, 2026-09-27)", async () => {
  // scToggle sets scRestoreFocusId, then awaits loadSecondCard() to re-read
  // the real state. When that re-read throws, it lands in scShowProblem,
  // not scPaint - and only scPaint used to clear scRestoreFocusId. Left
  // set, the NEXT successful repaint (here: the page's own visibilitychange
  // re-read) would steal focus back to this switch from wherever the owner
  // is by then, even though they left this failed attempt behind.
  const page = await open({ status: SC.running_long_context });
  await page.locator("#sc-switch-long_context").focus();
  await page.evaluate(() => { window.__secondCard.getFails = "boom"; });
  await page.keyboard.press("Space");
  await page.waitForTimeout(300);
  const afterFailure = await section(page);
  assert.equal(afterFailure.bodyHidden, true, "the failed re-read did not show the problem state");
  // The owner has moved on: nothing here is focused any more.
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  assert.equal(await page.evaluate(() => document.activeElement === document.body), true);
  // Now the read works again, and something else triggers a repaint - the
  // same event settings.js's own visibilitychange listener reacts to.
  await page.evaluate(() => { window.__secondCard.getFails = null; });
  await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
  await page.waitForTimeout(300);
  const focused = await page.evaluate(() => document.activeElement.id);
  await page.close();
  assert.notEqual(focused, "sc-switch-long_context",
    "the failed toggle's own switch stole focus back on a later, unrelated repaint");
});

/* ── "When to suggest the bigger model" (2026-09-27) ──────────────────────── */

await check("both suggestion signals show, on by default, with the backend's own words", async () => {
  const page = await open({ status: SC.capable_off });
  const s = await section(page);
  await page.close();
  assert.equal(s.suggestTitleHidden, false);
  assert.match(s.suggestDetail, /never switches it on by itself/);
  assert.equal(s.suggestSignalsHidden, false);
  assert.deepEqual(s.suggestRows.map((r) => r.id), ["struggle", "correction"]);
  for (const id of ["struggle", "correction"]) {
    const r = suggestRow(s, id);
    assert.equal(r.checked, true, `${id} is not on by default`);
  }
  assert.match(suggestRow(s, "struggle").text, /When Jarvis is visibly struggling/);
  assert.match(suggestRow(s, "correction").text, /When you correct an answer more than once/);
});

await check("turning a suggestion signal off sends one request, no card, and stays off", async () => {
  const page = await open({ status: SC.capable_off });
  await page.locator("#sc-suggest-struggle").click();
  await page.waitForTimeout(200);
  const s = await section(page);
  const said = await page.locator("#sc-suggest-status").innerText();
  await page.close();
  assert.deepEqual(s.changes, [{ signal: "struggle", enabled: false }]);
  assert.equal(suggestRow(s, "struggle").checked, false);
  assert.equal(suggestRow(s, "correction").checked, true, "the other signal was touched");
  assert.match(said, /Jarvis will not offer this on its own\./);
});

await check("pressing Space on a suggestion switch keeps keyboard focus in place (bug audit 2026-09-27 #5)", async () => {
  const page = await open({ status: SC.capable_off });
  await page.locator("#sc-suggest-struggle").focus();
  await page.keyboard.press("Space");
  await page.waitForTimeout(300);
  const focused = await page.evaluate(() => document.activeElement.id);
  const s = await section(page);
  await page.close();
  assert.equal(suggestRow(s, "struggle").checked, false, "the switch itself did not toggle");
  assert.equal(focused, "sc-suggest-struggle", "focus landed on <body> instead of staying on the switch");
});

await check("an older backend that sends no 'suggest' hides the whole subsection", async () => {
  const status = JSON.parse(JSON.stringify(SC.capable_off));
  delete status.suggest;
  const page = await open({ status });
  const s = await section(page);
  await page.close();
  assert.equal(s.suggestTitleHidden, true);
  assert.equal(s.suggestSignalsHidden, true);
  assert.equal(s.suggestRows.length, 0);
  assert.equal(s.bodyHidden, false, "the rest of the section still shows");
});

await check("a suggestion setting refused by the backend goes back to what it was", async () => {
  const page = await open({ status: SC.capable_off, setFails: "That is not one of the two suggestion settings." });
  await page.locator("#sc-suggest-correction").click();
  await page.waitForTimeout(200);
  const s = await section(page);
  const said = await page.locator("#sc-suggest-status").innerText();
  await page.close();
  assert.equal(suggestRow(s, "correction").checked, true, "stayed off after a refusal");
  assert.match(said, /That is not one of the two suggestion settings\./);
});

await check("a switch whose card has gone stays on-but-waiting, and can still be turned off", async () => {
  const page = await open({ status: SC.card_missing_but_enabled });
  const s = await section(page);
  await page.close();
  for (const id of ["long_context", "vision"]) {
    const r = row(s, id);
    assert.equal(r.checked, true, `${id} was flipped off`);
    assert.equal(r.disabled, false, `${id} cannot be turned off`);
    assert.match(r.text, /On, but it cannot run: only one graphics card found/);
  }
  assert.equal(row(s, "learning").disabled, true);
  assert.equal(row(s, "master").checked, true);
  assert.match(row(s, "master").text, /On, but it cannot run: only one graphics card found/);
  assert.equal(s.blockedHidden, false);
});

await check("a refusal is the backend's own sentence, and the switch goes back to what Jarvis says", async () => {
  const refusal = "A card to turn on \"Pictures\" is already waiting - approve or deny that one";
  const page = await open({ status: SC.capable_pending, setFails: refusal });
  await page.locator("#sc-switch-vision").click();
  await page.waitForTimeout(300);
  const s = await section(page);
  await page.close();
  assert.equal(s.status, refusal);
  assert.equal(row(s, "vision").checked, false);
});

/* ── When it cannot be read ────────────────────────────────────────────── */

await check("an older backend (404, or 503 with no module): says to run apply-patches.ps1", async () => {
  const page = await open({ status: SC.one_card, unavailable: true });
  const s = await section(page);
  await page.close();
  assert.equal(s.bodyHidden, true);
  assert.equal(s.stateHidden, false);
  assert.match(s.state, /Update the backend by running apply-patches\.ps1/);
  noRaw(s.state);
});

await check("Jarvis not answering: a sentence, never an error dump", async () => {
  const page = await open({ status: SC.one_card,
    getFails: "Jarvis is not answering at http://127.0.0.1:4719. Is it running?" });
  const s = await section(page);
  await page.close();
  assert.equal(s.bodyHidden, true);
  assert.match(s.state, /Jarvis could not be asked about your graphics cards\. Jarvis is not answering at http:\/\/127\.0\.0\.1:4719\. Is it running\?/);
});

await check("an error that is not a sentence is not shown as is", async () => {
  const page = await open({ status: SC.one_card,
    getFails: "{\"error\": \"Traceback (most recent call last)\"}" });
  const s = await section(page);
  await page.close();
  assert.doesNotMatch(s.state, /Traceback|\{/);
  assert.match(s.state, /Try again in a moment/);
});

await check("an answer that is not status() is not drawn", async () => {
  const page = await open({ status: { ok: true } });
  const s = await section(page);
  await page.close();
  assert.equal(s.bodyHidden, true);
  assert.match(s.state, /could not be read/);
  noRaw(s.state);
});

/* ── The model badge and the picture check ─────────────────────────────── */

const CHAT = JSON.parse(read("tests/fixtures/chat-stream-cases.json"));
/** The route line commands.rs route_line_from_header sends: lane, where, gate
 *  and second_card, each only when it is a string. */
const routeLine = (header) => {
  const h = JSON.parse(header);
  const out = {};
  for (const k of ["lane", "where", "gate", "second_card"]) if (typeof h[k] === "string") out[k] = h[k];
  return "\u001fjarvis-route:" + JSON.stringify(out);
};
/** The REAL local header, with exactly the two changes second-card.patch
 *  makes: `lane` = the model answering, `second_card` = the feature. */
const local = CHAT.route_headers.find((r) => r.expect.where === "local");
const secondHeader = (model, feature) =>
  JSON.stringify({ ...JSON.parse(local.header), lane: model, second_card: feature });
const okBody = CHAT.cases.find((c) => c.name === "local turn").body;
const pumpLines = (body) => body.split("\n").map((l) => l.replace(/\r$/, "")).filter((l) => l.trim());

async function badge(header) {
  const page = await K.open(browser, base, "index.html",
    { chatReplies: [[routeLine(header), ...pumpLines(okBody)]] }, { width: 750, height: 600 });
  await page.locator("#prompt").fill("hi");
  await page.locator("#prompt").press("Enter");
  await page.waitForTimeout(400);
  const got = await page.evaluate(() => ({
    tier: document.getElementById("route-tier").textContent,
    model: document.getElementById("route-model").textContent,
  }));
  await page.close();
  return got;
}

await check("the badge says 'on the second graphics card' when the second card answered, and is still Local", async () => {
  const long = await badge(secondHeader("qwen3:14b", "long_context"));
  assert.equal(long.tier, "Local");
  assert.equal(long.model, "qwen3:14b on the second graphics card");
  const pic = await badge(secondHeader("qwen2.5vl:7b", "vision"));
  assert.equal(pic.model, "qwen2.5vl:7b on the second graphics card");
  const plain = await badge(local.header);
  assert.equal(plain.model, local.expect.lane, "an ordinary turn gained the words");
});

await check("pictures on the second card: the check vision.rs returns sends the picture straight away", async () => {
  const page = await K.open(browser, base, "index.html", { vision: {
    model: "qwen2.5vl:7b", vision: true,
    reason: "Pictures go to qwen2.5vl:7b on the second graphics card." } });
  await page.evaluate(() => window.__emit("screen-captured", {
    dataUri: "data:image/gif;base64,R0lGODlhAQABAAAAACw=", width: 1, height: 1, bytes: 634, elapsedMs: 12 }));
  await page.waitForTimeout(100);
  await page.fill("#prompt", "What is this?");
  await page.press("#prompt", "Enter");
  await page.waitForTimeout(300);
  const sent = await page.evaluate(() => window.__calls.filter(([c]) => c === "stream_chat").map(([, a]) => a));
  const noticeHidden = await page.locator("#picture-notice").isHidden();
  await page.close();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].hasImage, true);
  assert.equal(noticeHidden, true);
});

/* ── Controls: the Rust ────────────────────────────────────────────────── */

const fnBody = (src, sig) => {
  const at = src.indexOf(sig);
  assert.ok(at > -1, `${sig} is gone`);
  const rest = src.slice(at);
  return rest.slice(0, rest.indexOf("\n}\n"));
};

await check("CONTROL: both commands send X-Jarvis-Client: hud and the token the usual way, and log nothing", async () => {
  const rust = read("src-tauri/src/commands.rs");
  assert.match(rust, /const JARVIS_CLIENT: &str = "hud";/);
  const headers = fnBody(rust, "pub fn jarvis_headers(");
  assert.match(headers, /"X-Jarvis-Client"/);
  assert.match(headers, /"X-Jarvis-Token"/);
  for (const sig of ["pub async fn get_second_card(", "pub async fn set_second_card("]) {
    const body = fnBody(rust, sig);
    assert.match(body, /\.headers\(jarvis_headers\(&app\)\?\)/, `${sig} does not send the usual headers`);
    // Only the configured backend: no other address can be reached.
    assert.match(body, /format!\("\{base\}\{SECOND_CARD_PATH\}"\)/, `${sig} builds its own URL`);
    assert.match(body, /let base = jarvis_base\(&app\);/);
    assert.doesNotMatch(body, /println!|eprintln!|log::|tracing::|dbg!/, `${sig} logs`);
    assert.doesNotMatch(body, /token/i, `${sig} touches the token itself`);
  }
  assert.match(rust, /pub\(crate\) const SECOND_CARD_PATH: &str = "\/api\/second-card";/);
  // Transport errors are sentences built here, never reqwest's text.
  const unreachable = fnBody(rust, "fn second_card_unreachable(");
  assert.doesNotMatch(unreachable, /\{err\}|\{e\}|err\.to_string/);
});

// AP-2 / CONN-4 (audit 3): the big model's ON was held on a stale link and
// the second card's was not, though both raise the same kind of card.
await check("CONTROL: ON is held on a stale link before anything is sent; OFF never is", async () => {
  const rust = read("src-tauri/src/commands.rs");
  const set = fnBody(rust, "pub async fn set_second_card(");
  const hold = set.indexOf("if enabled && app.state::<crate::stream::StreamState>().link().stale {");
  const post = set.indexOf(".post(");
  assert.ok(hold > -1, "set_second_card has no stale-link hold");
  assert.ok(hold < post, "the stale-link hold comes after the POST");
  // One direction only: the hold is conditioned on `enabled`, never on OFF.
  assert.doesNotMatch(set, /if !enabled && [^\n]*stale/);
  assert.match(set.slice(hold, post), /Turning things off still works\./);
});

await check("CONTROL: only the settings window may read or change the second card", async () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  const sets = toml.split("[[set]]").slice(1);
  for (const perm of ["allow-get-second-card", "allow-set-second-card", "allow-set-second-card-suggest",
                      "allow-set-third-card", "allow-set-chat-card"]) {
    const holders = sets.filter((s) => s.includes(`"${perm}"`))
      .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
    assert.deepEqual(holders, ["settings-surface"], `${perm} is held by ${holders}`);
  }
  assert.match(read("src-tauri/capabilities/settings.json"), /"settings-surface"/);
  for (const c of ["brain", "faces", "floating", "hud", "onboarding", "quickbar", "widget"]) {
    const json = read(`src-tauri/capabilities/${c}.json`);
    assert.ok(!json.includes("settings-surface"), `${c} holds settings-surface`);
    assert.ok(!json.includes("second-card"), `${c} can reach the second card`);
  }
  const build = read("src-tauri/build.rs");
  const lib = read("src-tauri/src/lib.rs");
  for (const cmd of ["get_second_card", "set_second_card", "set_second_card_suggest", "set_third_card",
                     "set_chat_card"]) {
    assert.ok(build.includes(`"${cmd}"`), `${cmd} is not in build.rs, so no window can call it`);
    assert.ok(lib.includes(`commands::${cmd},`), `${cmd} is not registered`);
    const gen = read(`src-tauri/permissions/autogenerated/${cmd}.toml`);
    assert.match(gen, new RegExp(`commands.allow = \\["${cmd}"\\]`));
  }
});

await check("CONTROL: moving a feature to the third card posts {feature: \"third\", assign}, held on a stale link", async () => {
  const rust = read("src-tauri/src/commands.rs");
  const body = fnBody(rust, "pub async fn set_third_card(");
  assert.match(body, /"feature": "third", "assign": assign/);
  assert.match(body, /format!\("\{base\}\{SECOND_CARD_PATH\}"\)/, "does not post to /api/second-card");
  const hold = body.indexOf("if assign.is_some() && app.state::<crate::stream::StreamState>().link().stale {");
  const post = body.indexOf(".post(");
  assert.ok(hold > -1, "set_third_card has no stale-link hold");
  assert.ok(hold < post, "the stale-link hold comes after the POST");
  // One direction only: the hold is conditioned on assigning, never on unassigning.
  assert.doesNotMatch(body, /if assign\.is_none\(\)[^\n]*stale/);
  assert.match(body, /jarvis_headers\(&app\)/);
  assert.doesNotMatch(body, /println!|eprintln!|log::|tracing::|dbg!/, "set_third_card logs");
});

await check("CONTROL: 'suggest the bigger model' is held on a stale link, and posts to /api/second-card/suggest", async () => {
  const rust = read("src-tauri/src/commands.rs");
  const fn = rust.slice(rust.indexOf("pub async fn set_second_card_suggest"));
  const body = fn.slice(0, fn.indexOf("\n}\n"));
  assert.match(body, /link\(\)\.stale/, "not held on a stale link");
  assert.match(body, /SECOND_CARD_SUGGEST_PATH/, "does not post to /api/second-card/suggest");
  assert.match(read("src-tauri/src/commands.rs"),
    /const SECOND_CARD_SUGGEST_PATH: &str = "\/api\/second-card\/suggest"/,
    "the route is not spelled out literally, so check_parity.py cannot see it");
});

await check("CONTROL: the picture check asks the second card first, and only a working Pictures switch says yes", async () => {
  const rust = read("src-tauri/src/vision.rs");
  const cmd = fnBody(rust, "pub async fn local_model_vision(");
  // Since 2026-09-26 the status is read once (it also says whether the PC
  // reads the words in a picture), and the picture model taken from it.
  const second = cmd.indexOf("read_second_card_status(");
  const picked = cmd.indexOf("and_then(second_card_picture_model)");
  const current = cmd.indexOf("read_current_model(");
  assert.ok(second > -1 && second < picked && picked < current,
    "the second card is not asked before the current model");
  const pick = fnBody(rust, "pub fn second_card_picture_model(");
  assert.match(pick, /Some\("vision"\)/);
  assert.match(pick, /get\("available"\)\.and_then\(\|a\| a\.as_bool\(\)\) != Some\(true\)/);
  assert.match(rust, /Pictures go to \{model\} on the second graphics card\./);
  // Same client (loopback Jarvis only) and the same headers as the rest.
  const reader = fnBody(rust, "async fn read_second_card_status(");
  assert.match(reader, /jarvis_base\(app\)/);
  assert.match(reader, /jarvis_headers\(app\)/);
});

await check("CONTROL: the route line passes second_card on, and nothing more", async () => {
  const rust = read("src-tauri/src/commands.rs");
  const fn = fnBody(rust, "pub fn route_line_from_header(");
  // `for key in [...]` is spread one key per line since `quick` and
  // `open_settings` joined it (fix: phone build/settings-registry drop),
  // so match the list body rather than one exact line and check its keys
  // regardless of the formatting around them.
  const list = /for key in \[([\s\S]*?)\]/.exec(fn);
  assert.ok(list, "no `for key in [...]` string list in route_line_from_header");
  // Comments inside the list (the "Forget a time frame" note quotes words)
  // are not keys: drop them before reading the quoted strings.
  const body = list[1].replace(/\/\/[^\n]*/g, "");
  const keys = [...body.matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(keys, ["lane", "where", "gate", "second_card", "quick", "open_settings", "face_tuning", "offer", "open_brain", "history_q"]);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nThe second graphics card holds");
process.exit(fails.length ? 1 : 0);
