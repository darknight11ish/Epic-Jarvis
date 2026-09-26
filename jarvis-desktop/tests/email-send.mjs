/**
 * Sending email on the desktop (the owner's decision of 2026-09-25, after the
 * Muse audit; JARVIS-API.md section 24; src/email-sending.js,
 * src/email-sending-settings.js, src-tauri/src/email_sending.rs, commands.rs).
 *
 * What must hold:
 * - an email's card in the Jarvis bar shows every character of it as it
 *   will be sent: never Markdown (a `[words](link)` stays as written, with
 *   the link in view), every line, and a long one scrolls - nothing cut;
 * - the widget never approves an email: its line says to read it in the
 *   Jarvis bar, and its Approve opens the bar on the card instead of
 *   deciding; Deny still works there. Rust refuses the same (CONTROL);
 * - with App lock on, the widget shows only the notice's title - no
 *   recipient, subject or word of the email;
 * - Settings shows the PC's own line about sending (from which address,
 *   through which server), word for word, and never a password.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  approvalPlainText,
  EMAIL_APPROVE,
  EMAIL_DETAIL,
  isEmailCard,
  MISSING,
  readSending,
} from "../src/email-sending.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const readRepo = (p) => readFileSync(join(HERE, "..", "..", p), "utf8");
const CASES = K.EMAIL_SENDING;

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** One email's card, as /api/pending carries it: `detail` is the gate's
 *  JSON, `{"text": <the card>}`, and the notice built from the action alone. */
function emailCard(text = CASES.example_card, id = "e1") {
  return {
    id, action: "send_email", tier: "ask", created: 1,
    detail: JSON.stringify({ text }),
    prompt: "tool send_email {...}",
    risk: { reversible: "no", reach: "outbound", swipe_ok: false, classified: true,
            why: "sends the email shown on the card from your own account, to exactly the people it lists; once sent it cannot be taken back" },
    raised: null,
    notice: { title: "Jarvis wants to send email",
              body: "sends the email shown on the card from your own account, to exactly the people it lists; once sent it cannot be taken back. nothing has happened yet.",
              weight: "heavy", deny_ok: true, approve_ok: false },
  };
}

/* ── The words ────────────────────────────────────────────────────────── */

await check("readSending passes the PC's own line on, and a PC without it says so", async () => {
  for (const [name, view] of Object.entries(CASES.cases)) {
    const v = readSending(view);
    assert.equal(v.said, view.said, name);
    assert.equal(v.ready, view.ready === true, name);
  }
  assert.equal(readSending(CASES.missing.body).said, MISSING);
  assert.equal(readSending(null).available, false);
  assert.equal(readSending({ available: false, said: "Your PC's Jarvis cannot send email yet - run apply-patches.ps1 on the PC." }).said, MISSING);
  assert.equal(isEmailCard({ action: "send_email" }), true);
  // A draft's card shows the same whole-email shape (JARVIS-API.md section
  // 40) and needs the same never-Markdown, never-widget-approve treatment.
  assert.equal(isEmailCard({ action: "draft_email" }), true);
  assert.equal(isEmailCard({ action: "email_read" }), false);
  assert.equal(approvalPlainText({ detail: { text: "x\ny" } }), "x\ny");
});

/* ── The Jarvis bar: every character, nothing interpreted ─────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();

await check("the Jarvis bar shows the email word for word, never as Markdown", async () => {
  const page = await K.open(browser, base, "index.html", { pending: [emailCard()] });
  await page.waitForTimeout(600);
  const pre = page.locator("#approval-preview pre.approval-verbatim");
  const shown = await pre.textContent();
  const links = await page.locator("#approval-preview a").count();
  const strong = await page.locator("#approval-preview strong").count();
  const errors = page.__errors;
  await page.close();
  assert.equal(shown, CASES.example_card, "not every character of the card");
  assert.ok(shown.includes(CASES.example_body), "the email's text");
  assert.ok(shown.includes("[the menu](https://example.com/menu)"),
    "a markdown link must stay as written, with where it goes in view");
  assert.ok(shown.includes("**See you there.**"));
  assert.equal(links, 0, "no link made out of the email's text");
  assert.equal(strong, 0, "no formatting made out of the email's text");
  assert.deepEqual(errors || [], []);
});

await check("a long email is all there: the preview scrolls, nothing is cut", async () => {
  const body = Array.from({ length: 60 }, (_, i) => `Line ${i + 1} of the email.`).join("\n");
  const text = CASES.example_card.replace(CASES.example_body, body);
  const page = await K.open(browser, base, "index.html", { pending: [emailCard(text)] });
  await page.waitForTimeout(600);
  const got = await page.evaluate(() => {
    const p = document.getElementById("approval-preview");
    const pre = p.querySelector("pre");
    p.scrollTop = p.scrollHeight;
    return { text: pre.textContent, overflow: getComputedStyle(p).overflowY,
             scrolls: p.scrollHeight > p.clientHeight, atEnd: p.scrollTop > 0,
             wrap: getComputedStyle(pre).whiteSpace };
  });
  await page.close();
  assert.equal(got.text, text, "the whole email, every line");
  assert.ok(got.text.includes("Line 60 of the email."));
  assert.equal(got.overflow, "auto");
  assert.ok(got.scrolls && got.atEnd, "a long email scrolls to its last line");
  assert.equal(got.wrap, "pre-wrap", "long lines wrap rather than hide off to the side");
});

await check("CONTROL: any other card is still drawn as Markdown", async () => {
  const other = { ...emailCard("**bold** plan"), id: "o1", action: "run_shell_on_host" };
  const page = await K.open(browser, base, "index.html", { pending: [other] });
  await page.waitForTimeout(600);
  const verbatim = await page.locator("#approval-preview pre.approval-verbatim").count();
  const strong = await page.locator("#approval-preview strong").count();
  await page.close();
  assert.equal(verbatim, 0);
  assert.equal(strong, 1);
});

/* ── The widget: an email is approved in the Jarvis bar ───────────────── */

const widget = (data) => K.open(browser, base, "widget.html", data, { width: 320, height: 520 });

await check("the widget sends an email's Approve to the Jarvis bar, and decides nothing", async () => {
  const page = await widget({ pending: [emailCard()] });
  await page.waitForTimeout(600);
  const detail = await page.locator("#appr-detail").innerText();
  const label = await page.locator("#btn-appr-yes").innerText();
  const card = await page.locator("#approval-card").innerText();
  await page.locator("#btn-appr-yes").click();
  await page.waitForTimeout(300);
  const opened = await page.evaluate(() => window.__openedInBar || 0);
  const decides = await page.evaluate(() => window.__decides || []);
  await page.locator("#btn-appr-no").click();
  await page.waitForTimeout(300);
  const after = await page.evaluate(() => window.__decides || []);
  await page.close();
  assert.equal(detail, EMAIL_DETAIL);
  assert.equal(label, EMAIL_APPROVE);
  assert.ok(!card.includes("alex@example.com") && !card.includes("Friday at 7"),
    "the widget's one line never passes for the whole email");
  assert.equal(opened, 1, "Approve opened the Jarvis bar");
  assert.deepEqual(decides, [], "Approve decided nothing here");
  assert.deepEqual(after, [{ id: "e1", approved: false, optionId: undefined }],
    "Deny still works from the widget");
});

await check("App lock on: the widget shows the notice's title only - no recipient, no word", async () => {
  const page = await widget({ pending: [emailCard()], appLock: true });
  await page.waitForTimeout(600);
  const card = await page.locator("#approval-card").innerText();
  await page.close();
  assert.match(card, /Jarvis wants to send email/);
  for (const secret of ["alex@example.com", "sam@example.org", "Dinner on Friday", "Friday at 7"]) {
    assert.ok(!card.includes(secret), `the locked widget showed ${secret}`);
  }
});

/* ── Settings ─────────────────────────────────────────────────────────── */

await check("Settings shows the PC's line about sending, word for word, and no password", async () => {
  for (const name of ["ready", "tool_off", "not_set_up", "refused_auto"]) {
    const page = await K.open(browser, base, "settings.html",
      { emailSending: CASES.cases[name] }, { width: 820, height: 1800 });
    await page.waitForTimeout(700);
    const text = await page.locator("#email-sending").innerText();
    const errors = page.__errors;
    await page.close();
    assert.ok(text.includes(CASES.cases[name].said), `${name}: ${text}`);
    assert.match(text, /one card per email/);
    assert.ok(!/password\s*[:=]/i.test(text), name);
    assert.deepEqual(errors || [], []);
  }
  const page = await K.open(browser, base, "settings.html", { emailSending: CASES.missing.body },
    { width: 820, height: 1800 });
  await page.waitForTimeout(700);
  const text = await page.locator("#email-sending").innerText();
  await page.close();
  assert.ok(text.includes(MISSING), text);
});

await browser.close();
await close();

/* ── CONTROL: the Rust says the same ──────────────────────────────────── */

await check("CONTROL: Rust refuses an email's Approve from the widget, lock or not", async () => {
  const rs = read("src-tauri/src/commands.rs");
  const i = rs.indexOf("waiting_email(&app, id)");
  assert.ok(i > 0, "answer_approval checks for an email");
  const block = rs.slice(i - 400, i + 300);
  assert.match(block, /WIDGET_LABEL/);
  assert.match(block, /show_approval_in_quickbar/);
  assert.match(block, /EMAIL_APPROVES_IN_BAR/);
  assert.ok(rs.indexOf("waiting_email(&app, id)") < rs.indexOf("crate::lock::check_approval"),
    "refused before Windows Hello is asked");
});

await check("CONTROL: the Settings read sits with the Settings window only", async () => {
  const surfaces = read("src-tauri/permissions/surfaces.toml");
  const settings = surfaces.slice(surfaces.indexOf('identifier = "settings-surface"'));
  const next = settings.indexOf("[[set]]", 10);
  assert.ok(settings.slice(0, next > 0 ? next : undefined).includes('"allow-get-email-sending"'));
  const others = surfaces.slice(0, surfaces.indexOf('identifier = "settings-surface"'));
  assert.ok(!others.includes("allow-get-email-sending"));
});

await check("CONTROL: the phone reads the same route and shows the same line", async () => {
  const kt = readRepo("jarvis-client/app/src/main/java/com/jarvis/client/net/EmailSending.kt");
  assert.match(kt, /"\/api\/email\/sending"/);
  assert.ok(kt.includes(MISSING.replace(/'/g, "'")), "the same words for a PC without it");
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nSending email: every word on the card, approved in the Jarvis bar only, the PC's own line in Settings");
