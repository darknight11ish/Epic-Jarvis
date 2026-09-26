/**
 * One card on every screen: the same words, the same button order, the same
 * spoken lines - held to tests/fixtures/card-words-cases.json, which
 * tools/gen_card_words_cases.py makes from backend/jarvis_card_words.py and
 * the real notice_for. The phone's CardWordsContractTest reads the same file.
 *
 *     node tests/card-words.mjs
 *
 * No browser: the pages are read as text, and the HUD's own functions are
 * lifted out of jarvis_hud.html and run as they are.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  CARD_BUTTONS,
  CARD_KICKER,
  CARD_NO_ACTION,
  CARD_VOICE,
  cardTitle,
  createCardVoice,
  fallbackTitle,
  isCardLine,
} from "../src/card-words.js";
import { normaliseApproval } from "../src/jarvis-link.js";
import { cardLinkView, OPEN_CARD } from "../src/card-link.js";
import * as BRIEF from "../src/briefing.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const CASES = JSON.parse(readFileSync(join(HERE, "fixtures", "card-words-cases.json"), "utf8"));
const page = (name) => readFileSync(join(SRC, name), "utf8");
const HUD = page("jarvis_hud.html");

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const lift = (name) => {
  const m = HUD.match(new RegExp(`function ${name}\\([^)]*\\)\\{[\\s\\S]*?\\n\\}\\n`));
  assert.ok(m, `jarvis_hud.html has no function ${name}`);
  return m[0];
};
const hud = new Function(
  `${["apprEscape", "apprDescribe", "apprCardHtml", "apprRaised", "apprRiskLine", "apprCutOff",
      "apprTitle"].map(lift).join("\n")}; return { apprCardHtml, apprTitle };`)();

check("the label, the button order and the no-action title are the PC's", () => {
  assert.equal(CARD_KICKER, CASES.kicker);
  assert.deepEqual([...CARD_BUTTONS], CASES.buttons);
  assert.equal(CARD_NO_ACTION, CASES.no_action);
});

check("the spoken card lines are the PC's, word for word", () => {
  assert.deepEqual({ ...CARD_VOICE }, CASES.voice);
  for (const line of Object.values(CASES.voice)) assert.ok(isCardLine(line), line);
  assert.equal(isCardLine("It's on your screen."), false);
});

check("every action's title, as the PC serves it, is what every surface shows", () => {
  for (const { action, title } of CASES.titles) {
    const row = { id: "x", action, notice: { title, body: "", weight: "normal" } };
    assert.equal(normaliseApproval(row).title, title, action);
    assert.equal(cardTitle(normaliseApproval(row)), title, action);
    assert.equal(hud.apprTitle(row), title, `HUD: ${action}`);
    assert.doesNotMatch(title, /_/, `a code name in ${title}`);
  }
});

check("a row with no notice gets the PC's own fallback, on every surface", () => {
  for (const { action, title } of CASES.fallback) {
    assert.equal(fallbackTitle(action), title, JSON.stringify(action));
    assert.equal(normaliseApproval({ id: "x", action }).title, title, JSON.stringify(action));
    assert.equal(hud.apprTitle({ id: "x", action }), title, `HUD: ${JSON.stringify(action)}`);
  }
  assert.equal(normaliseApproval({ id: "x" }).title, CARD_NO_ACTION);
});

check("a spoken question hears the same card lines as on the phone", () => {
  for (const { words, says } of CASES.voice_script) {
    const v = createCardVoice();
    const got = words.map((w) => v.onStatus(w)).filter(Boolean);
    assert.deepEqual(got, says, JSON.stringify(words));
  }
  const v = createCardVoice();
  v.onStatus("approval");
  v.reset();
  assert.equal(v.onStatus("approved"), null, "a new question starts with nothing waiting");
});

check("Deny is left of Approve on every desktop surface", () => {
  const bar = page("index.html");
  assert.ok(bar.indexOf('id="approval-deny"') < bar.indexOf('id="approval-approve"'), "Jarvis bar");
  const widget = page("widget.html");
  assert.ok(widget.indexOf('id="btn-appr-no"') < widget.indexOf('id="btn-appr-yes"'), "widget");
  const html = hud.apprCardHtml({ id: "h", action: "send_email", tier: "ask" }, 0);
  assert.ok(html.indexOf('class="no"') < html.indexOf('class="yes"'), "HUD");
  assert.deepEqual([...CARD_BUTTONS], ["Deny", "Approve"]);
});

check("the label is on every desktop surface, and the code name is not the heading", () => {
  assert.match(page("index.html"), />Needs your OK</);
  assert.match(page("widget.html"), />Needs your OK</);
  assert.doesNotMatch(page("widget.html"), /APPROVAL REQUIRED/);
  const html = hud.apprCardHtml({ id: "h", action: "switch_model", tier: "ask",
    notice: { title: "Jarvis wants to switch to a different AI model" } }, 0);
  assert.match(html, /Needs your OK/);
  assert.match(html, /Jarvis wants to switch to a different AI model/);
  assert.doesNotMatch(html, /switch_model|>ask</);
  assert.doesNotMatch(page("main.js"), /Approval required: \$\{approval\.action\}/);
  assert.doesNotMatch(page("widget.js"), /: approval\.action\}/);
});

check("\"Open the card\" names the newest card, says how many more, and opens by id", () => {
  assert.equal(cardLinkView([]), null);
  assert.equal(cardLinkView(null), null);
  const items = [normaliseApproval({ id: "old", action: "switch_model", created: 5,
    notice: { title: "Jarvis wants to switch to a different AI model" } }),
  normaliseApproval({ id: "new", action: "learning_auto_enable", created: 9,
    notice: { title: "Jarvis wants to turn on automatic learning" } })];
  const v = cardLinkView(items);
  assert.equal(v.id, "new");
  assert.equal(v.title, "Jarvis wants to turn on automatic learning");
  assert.equal(v.kicker, CARD_KICKER);
  assert.equal(v.more, "and 1 more waiting");
  assert.equal(v.button, OPEN_CARD);
  assert.equal(cardLinkView([items[0]]).more, "");
  for (const name of ["settings.html", "brain.html"]) {
    assert.match(page(name), /id="card-link"/, `${name} has the line`);
  }
});

check("no sentence invites a spoken \"yes\" for a card (the briefing's set-up words)", () => {
  assert.doesNotMatch(BRIEF.SETUP_DETAIL, /say yes/);
  assert.match(BRIEF.SETUP_DETAIL, /approve the card/);
  assert.doesNotMatch(page("settings.html"), /until you say yes/);
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("\nall card-word checks passed");
