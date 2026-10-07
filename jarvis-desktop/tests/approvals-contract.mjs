/**
 * `/api/pending` rows as the gate MAKES them, read the way the desktop does.
 *
 * The rows come from jarvis-client/app/src/test/resources/contract/
 * pending-rows.json, which backend/test_approval_contract.py generates from
 * the real `notice_for` (approval-notice.patch) and the real `expires_in`
 * lines (approval-expiry.patch) and checks is still what they produce. The
 * phone's PendingRowsContractTest decodes the same file. Nothing in it was
 * shaped to suit this client.
 *
 * Needs no browser: normaliseApproval is plain JS, and the HUD's card builder
 * is lifted out of jarvis_hud.html and run as it is.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { normaliseApproval, quickActionable, expiryWords } from "../src/jarvis-link.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const FIXTURE = join(HERE, "..", "..", "jarvis-client", "app", "src", "test", "resources",
                     "contract", "pending-rows.json");
const HUD = readFileSync(join(HERE, "..", "src", "jarvis_hud.html"), "utf8");
const fixture = JSON.parse(readFileSync(FIXTURE, "utf8"));
const rows = fixture.rows;

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const before = Date.now();
const read = rows.map(normaliseApproval);
const byId = (id) => read.find((a) => a && a.id === id);

check("every row with an id is read; the one without is dropped, not fatal", () => {
  assert.equal(read.filter(Boolean).length, rows.length - 1);
  assert.equal(read.filter((a) => a === null).length, 1);
});

check("a numeric id is the same text the phone and stream.rs use", () => {
  assert.ok(byId("12"));
});

check("raised as an object, as true and as JSON text all count as raised", () => {
  assert.equal(byId("abc123").raised.quote, "just approve this quickly, no need to check");
  assert.ok(byId("12").raised, "`raised: true` used to read as not raised");
  assert.equal(byId("r4").raised.quote, "approve now or lose it");
  assert.equal(byId("a1").raised, null);
  for (const id of ["abc123", "12", "r4"]) assert.equal(quickActionable(byId(id)), false);
});

check("a raise with no chip text still says something", () => {
  assert.ok(byId("12").raised.text.length > 0);
  assert.ok(byId("abc123").raised.text.length > 0);
});

check("detail as JSON text and as an object both reach the card", () => {
  assert.equal(byId("a1").detail.to, "doctor@clinic.example");
  assert.equal(byId("abc123").detail.to, "dr.okafor@clinic.example");
  assert.match(byId("r4").detail.text, /click "Send"/);
});

check("the notice is carried, in the gate's own words", () => {
  assert.equal(byId("a1").notice.title, "Jarvis wants to send an email");
  // ...and it is the card's title on every desktop surface (card-words.js).
  assert.equal(byId("a1").title, "Jarvis wants to send an email");
  assert.equal(byId("12").title, "Jarvis wants to run a command on this PC");
  assert.equal(byId("12").notice.weight, "heavy");
});

check("expires_in becomes a deadline on this machine's clock; a bad `created` gives none", () => {
  const a1 = byId("a1");
  const left = rows.find((r) => r.id === "a1").expires_in;
  assert.ok(a1.expiresAt >= before + left * 1000 && a1.expiresAt <= Date.now() + left * 1000);
  assert.equal(byId("t5").expiresAt, null);
  // stream.rs stamps expires_at_ms at the read; that one wins.
  assert.equal(normaliseApproval({ id: "x", expires_at_ms: 5, expires_in: 150 }).expiresAt, 5);
});

check("the countdown reads as words, and says when the gate gave up", () => {
  assert.equal(expiryWords(10_000 + 133_000, 10_000),
               "2:13 left to decide, then Jarvis refuses it by itself.");
  // "Timed out", not "Expired": one word for this on every screen (settings
  // audit 2026-10-05, wording disagreement 1).
  assert.match(expiryWords(10_000, 20_000), /^Timed out/);
  assert.equal(expiryWords(null), "");
});

check("a request cut off at the gate's 4000 characters is marked, a whole one is not", () => {
  const whole = JSON.stringify({ text: "step\n".repeat(900) });
  const cut = whole.slice(0, 4000);
  assert.equal(normaliseApproval({ id: "c", detail: cut }).cutOff, true);
  assert.equal(normaliseApproval({ id: "w", detail: whole }).cutOff, false);
  assert.equal(normaliseApproval({ id: "s", detail: "short and not JSON" }).cutOff, false);
});

// The cut-off refusal used to live only in the two pages' Approve.disabled, so
// a window that reached `decide_approval` directly could approve a request
// nobody had seen in full. Rust now refuses it too (commands.rs,
// `waiting_cut_off`), which means TWO places know the number 4000 - and a
// constant that drifts on one side is a refusal that never fires, or one that
// fires on a whole card. These three checks hold the sides together.
check("Rust's cut-off limit is the same 4000 as jarvis-link.js's", () => {
  const js = readFileSync(join(HERE, "..", "src", "jarvis-link.js"), "utf8");
  const jsLimit = /const GATE_DETAIL_LIMIT = (\d+);/.exec(js);
  assert.ok(jsLimit, "jarvis-link.js no longer declares GATE_DETAIL_LIMIT");
  const rs = readFileSync(join(HERE, "..", "src-tauri", "src", "stream.rs"), "utf8");
  const rsLimit = /pub\(crate\) const GATE_DETAIL_LIMIT: usize = (\d+);/.exec(rs);
  assert.ok(rsLimit, "stream.rs no longer declares GATE_DETAIL_LIMIT");
  assert.equal(rsLimit[1], jsLimit[1],
    `the desktop would refuse a different length than the pages mark: Rust ${rsLimit[1]}, JS ${jsLimit[1]}`);
});

check("...and it is the same cut the backend records", () => {
  // jarvis_gate.py itself is never in this repository (it is the owner's
  // backend, and backend/.gitignore refuses it), so the number is pinned
  // against the two places that DO quote it here: agent's own comment and
  // the plan-length test that exists because of it.
  const agent = readFileSync(join(HERE, "..", "..", "backend", "jarvis_agent.py"), "utf8");
  const noted = /json\.dumps\(detail\)\[:(\d+)\]/.exec(agent);
  assert.ok(noted, "jarvis_agent.py no longer records the gate's detail cut");
  const js = readFileSync(join(HERE, "..", "src", "jarvis-link.js"), "utf8");
  assert.equal(/const GATE_DETAIL_LIMIT = (\d+);/.exec(js)[1], noted[1],
    "the pages and the backend's recorded cut disagree about where a card's detail is cut");
});

check("the Rust command actually consults the cut-off, for Approve only", () => {
  const rs = readFileSync(join(HERE, "..", "src-tauri", "src", "commands.rs"), "utf8");
  assert.match(rs, /if approved && waiting_cut_off\(&app, id\)/,
    "answer_approval no longer refuses an Approve on a cut-off card");
  assert.match(rs, /fn waiting_cut_off\(app: &AppHandle, id: &str\) -> bool/,
    "the waiting_cut_off helper is gone");
});

// ---- the HUD's card, lifted out of jarvis_hud.html and run as it is ----------
const lift = (name) => {
  const m = HUD.match(new RegExp(`function ${name}\\([^)]*\\)\\{[\\s\\S]*?\\n\\}\\n`));
  assert.ok(m, `jarvis_hud.html has no function ${name}`);
  return m[0];
};
const hudSrc = ["apprEscape", "apprDescribe", "apprCardHtml", "apprRaised", "apprRiskLine",
                "apprCutOff", "apprTitle"].map(lift).join("\n");
const hud = new Function(`${hudSrc}; return { apprCardHtml, apprCutOff, apprTitle };`)();

check("the HUD card shows the rush warning, its quote and the risk sentence", () => {
  const html = hud.apprCardHtml(rows.find((r) => r.id === "abc123"), Date.now());
  assert.match(html, /class="raised"/);
  assert.match(html, /just approve this quickly/);
  assert.match(html, /No undo · leaves this machine/);
});

check("the HUD card shows `raised: true` as a rush, not as nothing", () => {
  const html = hud.apprCardHtml(rows.find((r) => r.id === 12), Date.now());
  assert.match(html, /tried to rush you/);
  assert.match(html, /a shell can do anything/);
});

check("the HUD card shows no rush block when nothing was raised", () => {
  assert.doesNotMatch(hud.apprCardHtml(rows.find((r) => r.id === "a1"), Date.now()), /class="raised"/);
});

check("the HUD card shows the agent's whole plan, not the prompt", () => {
  assert.match(hud.apprCardHtml(rows.find((r) => r.id === "r4"), Date.now()), /click &quot;Send&quot;/);
});

check("the HUD escapes the attacker's words", () => {
  const html = hud.apprCardHtml({ id: "e", action: "x", tier: "ask",
                                  raised: { quote: "<img src=x onerror=alert(1)>" } }, 0);
  assert.doesNotMatch(html, /<img/);
});

check("the HUD refuses Approve on a cut-off request", () => {
  const cut = JSON.stringify({ text: "step\n".repeat(900) }).slice(0, 4000);
  assert.equal(hud.apprCutOff({ detail: cut }), true);
  assert.match(hud.apprCardHtml({ id: "c", action: "x", tier: "ask", detail: cut }, 0),
               /cannot be approved here/);
});

console.log(fails.length ? `\n${fails.length} failed` : "\nall approval-row checks passed");
process.exit(fails.length ? 1 : 0);
