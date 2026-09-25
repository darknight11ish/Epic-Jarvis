/**
 * Settings -> "Security", the Brain's hidden memory lists, and the Rust that
 * actually decides both (src-tauri/src/lock.rs).
 *
 * The page checks drive the real settings.html and brain.html with the
 * harness bridge. They can only show that the page paints what Rust answers
 * and asks Rust for every change - the deciding is in Rust, so the rest of
 * this file reads the Rust: the Windows Hello check sits inside the command
 * that sends an Approve, before the request; a notification can only deny;
 * the three locked windows ask before they open; the Brain's lists are
 * emptied before they reach any page; and only the settings window may
 * change these settings. lock.rs's own unit tests hold the rules themselves
 * (which approvals are risky, what counts as loosening) - `cargo test`,
 * Windows only.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";
import * as S from "../src/security-settings.js";
import { APPROVE_WHERE } from "../src/jarvis-link.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const LOCKED = { appLock: true, relockAfterSecs: 60, approvals: "risky", privateAnswers: false };

const settingsPage = (security) =>
  K.open(browser, base, "settings.html", security ? { security } : {}, { width: 760, height: 1400 });

const look = (page) => page.evaluate(() => {
  const $ = (id) => document.getElementById(id);
  const pressed = (id) => [...$(id).querySelectorAll("button")]
    .filter((b) => b.getAttribute("aria-pressed") === "true").map((b) => b.textContent);
  return {
    order: [...document.querySelectorAll("section.card h2")].map((h) => h.textContent.trim()),
    hello: $("sec-hello").innerText,
    appLock: $("sec-app-lock").checked,
    appLockOff: $("sec-app-lock").disabled,
    privateAnswers: $("sec-private").checked,
    relock: pressed("sec-relock"),
    relockAll: [...$("sec-relock").querySelectorAll("button")].map((b) => b.textContent),
    approvals: pressed("sec-approvals"),
    approvalsAll: [...$("sec-approvals").querySelectorAll("button")].map((b) => b.textContent),
    approvalsNote: $("sec-approvals-note").innerText,
    privateDetail: $("sec-private-detail").innerText,
    appLockDetail: $("sec-app-lock-detail").innerText,
    status: $("sec-status").innerText,
    all: $("security").innerText,
    changes: window.__security.changes,
  };
});

/* ── Settings: the section ───────────────────────────────────────────────── */

await check("the section sits after Shortcuts and paints the owner's defaults", async () => {
  const page = await settingsPage();
  const s = await look(page);
  const errors = page.__errors;
  await page.close();
  const at = s.order.indexOf("Shortcuts");
  assert.equal(s.order[at + 1], "Security");
  assert.equal(s.hello, "Windows Hello is set up on this PC.");
  assert.equal(s.appLock, false);
  assert.deepEqual(s.relock, ["1 min"]);
  assert.deepEqual(s.relockAll, ["Straight away", "1 min", "5 min", "15 min"]);
  assert.deepEqual(s.approvals, ["Risky only"]);
  assert.equal(s.privateAnswers, false);
  assert.deepEqual(s.changes, [], "opening Settings changed a setting");
  assert.deepEqual(errors, []);
});

await check("approvals: two choices and nothing below \"Risky only\"; the phone's rule and APPROVE_WHERE in words", async () => {
  const page = await settingsPage();
  const s = await look(page);
  await page.close();
  assert.deepEqual(s.approvalsAll, ["Risky only", "Every approval"]);
  assert.ok(s.approvalsNote.includes(S.RISKY_WORDS), "the risky rule is not spelled out");
  assert.ok(s.approvalsNote.includes(`approved ${APPROVE_WHERE}`), "not the one APPROVE_WHERE phrase");
  assert.match(s.approvalsNote, /Deny never asks/);
  assert.match(s.approvalsNote, /notification can deny but never approve/);
});

await check("what each lock covers is said plainly, gaps included", async () => {
  const page = await settingsPage();
  const s = await look(page);
  await page.close();
  assert.match(s.appLockDetail, /Jarvis bar, the Brain, Settings or the HUD window needs Windows Hello/);
  // The widget is not locked, and says what it does instead (audit M3).
  assert.match(s.appLockDetail, /only a short title for an approval/);
  assert.match(s.appLockDetail, /Approve opens the Jarvis bar/);
  assert.match(s.appLockDetail, /Deny still works from the widget/);
  assert.doesNotMatch(s.appLockDetail, /not locked/);
  assert.match(s.privateDetail, /memory lists/);
  assert.match(s.privateDetail, /Galaxy picture and answers in the Jarvis bar are not hidden/);
  // Named for what it hides (one wording, 2026-09-24), in its status lines too.
  assert.match(s.all, /Windows Hello for memory lists and chat history/);
  assert.doesNotMatch(s.all, /Windows Hello for private answers|private answers is on/);
  assert.match(S.relockNote(S.DEFAULTS),
    /It matters once App lock, or Windows Hello for memory lists and chat history, is on\.$/);
});

await check("tightening: one change sent, and the switch shows what Rust stored", async () => {
  const page = await settingsPage();
  await page.locator("#sec-app-lock").check();
  await page.waitForTimeout(150);
  await page.locator("#sec-approvals button", { hasText: "Every approval" }).click();
  await page.waitForTimeout(150);
  const s = await look(page);
  await page.close();
  assert.equal(s.changes.length, 2);
  assert.deepEqual(s.changes[0], { ...S.DEFAULTS, appLock: true });
  assert.deepEqual(s.changes[1], { ...S.DEFAULTS, appLock: true, approvals: "every" });
  assert.equal(s.appLock, true);
  assert.deepEqual(s.approvals, ["Every approval"]);
  assert.equal(s.status, "Every approval now asks Windows Hello.");
});

await check("a refused loosening puts the switch back and says so", async () => {
  const page = await settingsPage({
    settings: LOCKED,
    setFails: "Windows Hello did not confirm it was you",
  });
  // A click, not uncheck(): the refusal puts the tick straight back, which
  // is the point, and uncheck() would read that as a failed click.
  await page.locator("#sec-app-lock").click();
  await page.waitForTimeout(150);
  const s = await look(page);
  await page.close();
  assert.equal(s.changes.length, 1, "the change was never asked of Rust");
  assert.equal(s.changes[0].appLock, false);
  assert.equal(s.appLock, true, "the switch shows OFF while the lock is still on");
  assert.equal(s.status, "Windows Hello did not confirm it was you. Nothing changed.");
});

await check("a longer \"Lock again after\" is asked for, not assumed", async () => {
  const page = await settingsPage({ settings: LOCKED });
  await page.locator("#sec-relock button", { hasText: "15 min" }).click();
  await page.waitForTimeout(150);
  const s = await look(page);
  await page.close();
  assert.equal(s.changes.at(-1).relockAfterSecs, 900);
  assert.deepEqual(s.relock, ["15 min"]);
  assert.equal(s.status, "Jarvis locks again after 15 min away.");
});

await check("no Windows Hello: the line says what happens and what to do", async () => {
  let page = await settingsPage({ hello: "not-set-up" });
  let s = await look(page);
  await page.close();
  assert.match(s.hello, /not set up on this PC/);
  assert.match(s.hello, /approvals here go through without a check/);
  assert.match(s.hello, /a PIN is enough/);

  page = await settingsPage({ hello: "not-set-up", settings: LOCKED });
  s = await look(page);
  await page.close();
  assert.match(s.hello, /risky approvals here are refused/);
  assert.match(s.hello, /a PIN is enough/);
});

await check("settings that cannot be read cannot be changed", async () => {
  const page = await settingsPage({ getFails: "the settings file could not be opened: denied" });
  const s = await look(page);
  const errors = page.__errors;
  await page.close();
  assert.match(s.hello, /Could not read these settings/);
  assert.equal(s.appLockOff, true);
  assert.equal(s.appLock, false);
  assert.deepEqual(s.relock, [], "a choice is shown as picked when nothing was read");
  assert.deepEqual(errors, []);
});

/* ── The words, without a browser ────────────────────────────────────────── */

await check("\"Waiting for Windows Hello\" is shown exactly when lock.rs asks it", () => {
  const d = S.DEFAULTS;
  const on = { ...d, appLock: true };
  const every = { ...d, approvals: "every" };
  const priv = { ...d, privateAnswers: true };
  // Tightening, and anything with nothing on yet: instant.
  for (const next of [on, every, priv, { ...d, relockAfterSecs: 0 }, { ...d, relockAfterSecs: 900 }]) {
    assert.equal(S.needsHello(d, next), false, JSON.stringify(next));
  }
  // Loosening with something on.
  assert.equal(S.needsHello(on, d), true);
  assert.equal(S.needsHello(every, d), true);
  assert.equal(S.needsHello(priv, d), true);
  assert.equal(S.needsHello(on, { ...on, relockAfterSecs: 900 }), true);
  assert.equal(S.needsHello(on, { ...on, relockAfterSecs: 0 }), false);
});

await check("a value read back is read the way lock.rs reads its file", () => {
  assert.deepEqual(S.normalise(null), S.DEFAULTS);
  assert.equal(S.normalise({ approvals: "never" }).approvals, "risky");
  assert.equal(S.normalise({ relockAfterSecs: 7200 }).relockAfterSecs, 900);
  assert.equal(S.normalise({ relockAfterSecs: 200 }).relockAfterSecs, 60);
  assert.equal(S.normalise({ relockAfterSecs: 30 }).relockAfterSecs, 0);
});

/* ── The Brain: hidden memory lists ──────────────────────────────────────── */

async function memoryTab(security) {
  const page = await K.open(browser, base, "brain.html", security ? { security } : {},
    { width: 1180, height: 820 });
  await page.locator("#tab-memory").click();
  await page.waitForTimeout(250);
  return page;
}

await check("hidden: the lists say how many, offer Show, and hold no fact text", async () => {
  const page = await memoryTab({ hidden: true });
  const s = await page.evaluate(() => ({
    facts: document.getElementById("memory-facts").innerText,
    waiting: document.getElementById("memory-proposals").innerText,
    count: document.getElementById("count-memory").textContent,
    body: document.body.innerText,
  }));
  const errors = page.__errors;
  await page.close();
  const n = K.BRAIN.memory_facts.facts.length;
  assert.match(s.facts, new RegExp(`${n} facts?, hidden until Windows Hello confirms it is you`));
  assert.match(s.facts, /Show/);
  assert.match(s.waiting, /2 waiting, hidden/);
  assert.equal(s.count, "2", "the waiting badge went quiet while hidden");
  for (const f of K.BRAIN.memory_facts.facts) assert.ok(!s.body.includes(f.text), `shown: ${f.text}`);
  for (const p of K.BRAIN.memory_pending.pending) assert.ok(!s.body.includes(p.text), `shown: ${p.text}`);
  assert.deepEqual(errors, []);
});

await check("Show asks Rust, then the lists come back in full", async () => {
  const page = await memoryTab({ hidden: true });
  await page.locator("#memory-facts button", { hasText: "Show" }).click();
  await page.waitForTimeout(300);
  const s = await page.evaluate(() => ({
    reveals: window.__security.reveals,
    facts: document.getElementById("memory-facts").innerText,
  }));
  await page.close();
  assert.equal(s.reveals, 1);
  assert.ok(s.facts.includes(K.BRAIN.memory_facts.facts[0].text));
});

await check("a refused Show says why and keeps the lists hidden", async () => {
  const page = await memoryTab({ hidden: true, revealFails: "Windows Hello did not confirm it was you" });
  await page.locator("#memory-facts button", { hasText: "Show" }).click();
  await page.waitForTimeout(300);
  const s = await page.evaluate(() => ({
    toast: document.getElementById("toast").innerText,
    facts: document.getElementById("memory-facts").innerText,
  }));
  await page.close();
  assert.equal(s.toast, "Windows Hello did not confirm it was you");
  assert.ok(!s.facts.includes(K.BRAIN.memory_facts.facts[0].text));
});

await check("a Show that ends (the owner was away) hides the lists again without a click", async () => {
  const page = await memoryTab({ hidden: true, revealed: true });
  const before = await page.locator("#memory-facts").innerText();
  // lock.rs: the away time passed, so the next read comes back hidden and
  // the Brain is told to read again.
  await page.evaluate(() => {
    window.__security.revealed = false;
    window.__emit("private-hidden", null);
  });
  await page.waitForTimeout(300);
  const after = await page.locator("#memory-facts").innerText();
  await page.close();
  assert.ok(before.includes(K.BRAIN.memory_facts.facts[0].text), "the Show did not show");
  assert.ok(!after.includes(K.BRAIN.memory_facts.facts[0].text), "still shown after the Show ended");
  assert.match(after, /hidden until Windows Hello confirms it is you/);
});

await check("nothing hidden: the lists render as they always did, with no Show", async () => {
  const page = await memoryTab();
  const facts = await page.locator("#memory-facts").innerText();
  await page.close();
  assert.ok(facts.includes(K.BRAIN.memory_facts.facts[0].text));
  assert.doesNotMatch(facts, /hidden until Windows Hello/);
});

/* ── CONTROL: the Rust decides ───────────────────────────────────────────── */

const fnBody = (src, sig) => {
  const at = src.indexOf(sig);
  assert.ok(at >= 0, `no ${sig}`);
  const rest = src.slice(at);
  return rest.slice(0, rest.indexOf("\n}\n"));
};

await check("CONTROL (Rust): an Approve is checked inside the command, before the request; Deny never is", () => {
  const src = read("src-tauri/src/commands.rs");
  const cmd = fnBody(src, "pub async fn decide_approval(");
  assert.match(cmd, /window: tauri::WebviewWindow/, "the calling window is not Tauri's own");
  assert.match(cmd, /answer_approval\(/);
  const body = fnBody(src, "async fn answer_approval(");
  const gate = body.indexOf("crate::lock::check_approval(");
  const post = body.indexOf(".post(");
  assert.ok(gate > 0 && gate < post, "the Windows Hello check is not before the request");
  assert.match(body.slice(body.lastIndexOf("if approved {", gate), gate), /if approved \{/,
    "the check is not limited to Approve");
  assert.ok(body.indexOf(".stale", gate) > gate && body.indexOf(".stale", gate) < post,
    "the link is not checked again after the prompt");
});

await check("CONTROL (Rust): a notification can deny and never approve", () => {
  const cmd = read("src-tauri/src/commands.rs");
  const notify = fnBody(cmd, "pub async fn deny_from_notification(");
  assert.match(notify, /answer_approval\(app, AnsweredFrom::Notification, id, false, None\)/);
  const body = fnBody(cmd, "async fn answer_approval(");
  assert.match(body, /AnsweredFrom::Notification => \{\s*return Err\(/);
  const toast = read("src-tauri/src/winrt_toast.rs");
  assert.match(toast, /commands::deny_from_notification\(/);
  assert.doesNotMatch(toast.replace(/\/\/.*$/gm, ""), /commands::decide_approval\(/);
});

await check("CONTROL (Rust): the Jarvis bar, the Brain, Settings and the HUD ask before they open", () => {
  const src = read("src-tauri/src/windows.rs");
  for (const [fn, covered] of [["show_quickbar", "Quickbar"], ["show_brain", "Brain"], ["show_settings", "Settings"], ["show_hud", "Hud"]]) {
    const body = fnBody(src, `pub fn ${fn}(app: &AppHandle)`);
    assert.match(body, new RegExp(`if !crate::lock::may_open\\(app, crate::lock::Covered::${covered}\\) \\{\\s*return Ok\\(\\(\\)\\);`),
      `${fn} opens without asking`);
  }
  const lib = read("src-tauri/src/lib.rs");
  assert.match(lib, /\.on_window_event\(lock::on_window_event\)/, "coming back after being away is not checked");
});

await check("CONTROL (Rust): the Brain's lists are emptied before any page sees them", () => {
  const brain = read("src-tauri/src/brain.rs");
  const readFn = fnBody(brain, "pub async fn brain_read(");
  assert.match(readFn, /crate::lock::private_hidden\(&app\)/);
  assert.match(readFn, /crate::lock::redact_private\(/);
  for (const sig of ["pub async fn brain_memory_as_of(", "pub async fn brain_memory_export("]) {
    const body = fnBody(brain, sig);
    const gate = body.indexOf("crate::lock::require_private_shown(&app)?");
    assert.ok(gate > 0 && gate < body.indexOf("get_json("), `${sig} reads the facts while hidden`);
  }
});

await check("CONTROL: only Settings may change these, only the Brain may Show, and no window may write the store", () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  const setOf = (id) => {
    const at = toml.indexOf(`identifier = "${id}"`);
    const rest = toml.slice(at);
    const end = rest.indexOf("[[set]]", 1);
    return end > 0 ? rest.slice(0, end) : rest;
  };
  assert.match(setOf("settings-surface"), /"allow-set-security-settings"/);
  assert.match(setOf("settings-surface"), /"allow-get-security-settings"/);
  assert.match(setOf("private-reveal"), /"allow-reveal-private-answers"/);
  const holders = (perm) => [...toml.matchAll(/identifier = "([^"]+)"[\s\S]*?(?=\[\[set\]\]|$)/g)]
    .filter((m) => m[0].includes(`"${perm}"`)).map((m) => m[1]);
  assert.deepEqual(holders("allow-set-security-settings"), ["settings-surface"]);
  assert.deepEqual(holders("allow-reveal-private-answers"), ["private-reveal"]);
  const caps = ["brain", "faces", "hud", "onboarding", "quickbar", "settings", "widget"]
    .map((c) => [c, JSON.parse(read(`src-tauri/capabilities/${c}.json`)).permissions]);
  for (const [name, perms] of caps) {
    assert.ok(!perms.some((p) => String(p).startsWith("store:")), `${name} can write the store`);
    assert.equal(perms.includes("settings-surface"), name === "settings", `${name} holds settings-surface`);
    assert.equal(perms.includes("private-reveal"), name === "brain", `${name} holds private-reveal`);
  }
});

await check("no window can send events to the others (apps security audit M1)", () => {
  // `core:default` carries `core:event:default`, which allows `emit` and
  // `emit_to`. No page emits anything, and the quickbar trusts what it hears
  // (`voice-heard` with isOwner, the approval queue), so a script in any
  // window could have faked the owner's checked voice or an approval card.
  // Every window lists its core permissions by hand instead, without emit.
  const caps = ["brain", "faces", "hud", "onboarding", "quickbar", "settings", "widget"]
    .map((c) => [c, JSON.parse(read(`src-tauri/capabilities/${c}.json`)).permissions.map(String)]);
  for (const [name, perms] of caps) {
    for (const banned of ["core:default", "core:event:default", "core:event:allow-emit", "core:event:allow-emit-to"]) {
      assert.ok(!perms.includes(banned), `${name} holds ${banned}`);
    }
    assert.ok(perms.includes("core:event:allow-listen"), `${name} can no longer listen`);
  }
  // And no page tries to: an emit from a page would now be refused, so one
  // appearing here means a feature that silently does nothing.
  for (const f of readdirSync(join(HERE, "..", "src")).filter((f) => /\.(js|html)$/.test(f))) {
    const text = read(`src/${f}`);
    assert.doesNotMatch(text, /TAURI\??\.event\??\.emit|plugin:event\|emit/, `src/${f} emits an event`);
  }
});

await check("no HTTP client in the app follows a redirect (apps security audit L1)", () => {
  // reqwest drops Authorization and Cookie on a cross-host redirect but
  // keeps X-Jarvis-Token, so a redirect would hand the token to wherever it
  // pointed. Every client is built with redirects off, and uses no proxy.
  const dir = join(HERE, "..", "src-tauri", "src");
  const files = readdirSync(dir, { recursive: true }).filter((f) => String(f).endsWith(".rs"));
  let builders = 0;
  for (const f of files) {
    const text = read(`src-tauri/src/${f}`);
    let at = text.indexOf("Client::builder()");
    while (at !== -1) {
      builders++;
      const chain = text.slice(at, text.indexOf(".build()", at));
      assert.match(chain, /\.redirect\(reqwest::redirect::Policy::none\(\)\)/, `${f}: a client that follows redirects`);
      assert.match(chain, /\.no_proxy\(\)/, `${f}: a client that uses the system proxy`);
      at = text.indexOf("Client::builder()", at + 1);
    }
  }
  assert.ok(builders >= 13, `only ${builders} clients found - did the search break?`);
});

await check("adding a GitHub watch is held on a stale link, as on the phone (apps security audit L4)", () => {
  const rust = read("src-tauri/src/brain.rs");
  const body = rust.slice(rust.indexOf("pub async fn brain_watch_add"));
  const fn = body.slice(0, body.indexOf("\n}\n"));
  assert.ok(fn.indexOf("require_link_live(&app)?") > 0
    && fn.indexOf("require_link_live(&app)?") < fn.indexOf("post("), "brain_watch_add is not held on a stale link");
  const kt = readFileSync(join(HERE, "..", "..", "jarvis-client", "app", "src", "main", "java", "com", "jarvis",
    "client", "JarvisRuntime.kt"), "utf8");
  const add = kt.slice(kt.indexOf("suspend fun addWatch("));
  assert.ok(add.indexOf("actionBlocker()") > 0 && add.indexOf("actionBlocker()") < add.indexOf("api.watchAdd"),
    "the phone's addWatch stopped being held - the two apps disagree again");
});

await check("no page may connect to Ollama or LiteLLM directly (apps security audit L6)", () => {
  // Ollama has no login: a script allowed to reach it could pull or delete
  // models with no approval card. The health checks run in Rust, which the
  // page's content policy does not govern.
  const csp = JSON.parse(read("src-tauri/tauri.conf.json")).app.security.csp;
  const connect = /connect-src ([^;]*)/.exec(csp)[1];
  assert.doesNotMatch(connect, /:11434|:4000\b|\*/, `connect-src allows too much: ${connect}`);
});

await check("App lock covers the HUD on every way it is shown (apps security audit M3)", () => {
  const lock = read("src-tauri/src/lock.rs");
  assert.match(lock, /crate::HUD_LABEL => Some\(Self::Hud\)/, "the lock does not know the HUD");
  assert.match(lock, /Covered::Hud => crate::windows::show_hud_unlocked\(app\)/);
  // The away-watch and the focus check reach every covered window.
  assert.match(lock, /const ALL: \[Covered; 4\]/);
  assert.match(fnBody(lock, "pub fn spawn_watch("), /for which in Covered::ALL/);
  assert.match(fnBody(lock, "fn covered_focused("), /Covered::ALL/);
  const win = read("src-tauri/src/windows.rs");
  assert.match(fnBody(win, "pub fn toggle_hud("), /crate::lock::may_open\(app, crate::lock::Covered::Hud\)/,
    "toggling the HUD on skips the lock");
  // Only lock.rs shows it without asking.
  const rust = readdirSync(join(HERE, "..", "src-tauri", "src"), { recursive: true })
    .filter((f) => String(f).endsWith(".rs"));
  for (const f of rust) {
    const text = read(`src-tauri/src/${f}`).replace(/\/\/.*$/gm, "");
    if (f !== "lock.rs" && f !== "windows.rs") {
      assert.doesNotMatch(text, /show_hud_unlocked/, `${f} shows the HUD past the lock`);
    }
    assert.doesNotMatch(text, /get_webview_window\((crate::)?HUD_LABEL\)[^;]*\.show\(\)/, `${f} shows the HUD directly`);
  }
  // Second launch and a normal start go through the lock too.
  const lib = read("src-tauri/src/lib.rs");
  const single = lib.slice(lib.indexOf("tauri_plugin_single_instance::init"), lib.indexOf("tauri_plugin_clipboard_manager::init"));
  assert.match(single, /windows::show_hud\(app\)/, "a second launch shows the HUD without the lock");
  assert.doesNotMatch(single, /hud\.show\(\)/);
  const build = fnBody(lib, "fn build_hud_window(");
  assert.match(build, /let lock_first = !hidden && lock::current\(app\)\.app_lock;/);
  assert.match(build, /\.visible\(!hidden && !lock_first\)/, "a normal start shows the HUD while locked");
  assert.match(build, /if lock_first \{\s*if let Err\(err\) = windows::show_hud\(app\)/);
  const tray = read("src-tauri/src/tray.rs");
  assert.match(tray, /ID_SHOW_HUD => \{\s*if let Err\(err\) = windows::show_hud\(app\)/);
});

await check("App lock: the widget approves nothing, in Rust (apps security audit M3)", () => {
  const cmd = read("src-tauri/src/commands.rs");
  const answer = fnBody(cmd, "async fn answer_approval(");
  const gate = answer.indexOf("window.label() == windows::WIDGET_LABEL && crate::lock::current(&app).app_lock");
  assert.ok(gate > 0, "answer_approval does not refuse the widget's Approve under App lock");
  assert.ok(gate < answer.indexOf("crate::lock::check_approval"), "the widget refusal comes after Windows Hello");
  assert.ok(gate < answer.indexOf(".post("), "the widget refusal comes after the request");
  assert.match(answer.slice(gate, gate + 400), /show_approval_in_quickbar\(&app\);\s*return Err\(crate::lock::WIDGET_APPROVES_IN_BAR/);
  // Only Approve: Deny is not inside `if approved`.
  assert.match(answer.slice(0, gate), /if approved \{\s*if let AnsweredFrom::Window\(window\) = &from \{\s*if\s*$/);
  const rules = read("src-tauri/src/lock/rules.rs");
  const said = /WIDGET_APPROVES_IN_BAR: &str = "([\s\S]*?)";/.exec(rules)[1];
  // main.js and widget.js read "already" as "someone else answered it".
  assert.doesNotMatch(said, /already/i);
  // The two commands are the widget's, and read or decide nothing more.
  const toml = read("src-tauri/permissions/surfaces.toml");
  const set = toml.slice(toml.indexOf('identifier = "approvals"'));
  const perms = set.slice(set.indexOf("permissions = ["), set.indexOf("]") + 1);
  assert.match(perms, /"allow-get-app-lock"/);
  assert.match(perms, /"allow-open-approval-in-quickbar"/);
  assert.match(fnBody(cmd, "pub fn get_app_lock("), /^pub fn get_app_lock\(app: AppHandle\) -> bool \{\s*crate::lock::current\(&app\)\.app_lock\s*$/);
});

const LOCK_GATE = {
  ...K.APPROVAL_RAISED,
  notice: { title: "Send an email", body: "To supplier@example.com: Order 4471", weight: "heavy" },
  options: [
    { id: "o1", label: "Reply with the invoice attached", summary: "sends the invoice", weight: "heavy" },
    { id: "o2", label: "Wait", summary: "nothing sent", weight: "normal" },
  ],
};
const widgetCard = (page) => page.evaluate(() => {
  const $ = (id) => document.getElementById(id);
  const card = $("approval-card");
  return {
    shown: !card.hidden,
    text: card.innerText,
    action: $("appr-action").textContent,
    detail: $("appr-detail").textContent,
    approve: $("btn-appr-yes").textContent,
    approveHidden: $("btn-appr-yes").hidden,
    noteHidden: $("appr-note").closest(".appr-note-row").hidden,
  };
});

await check("App lock: the widget shows the notice title only, and Approve opens the Jarvis bar (M3)", async () => {
  const page = await K.open(browser, base, "widget.html", { pending: [LOCK_GATE], appLock: true }, { width: 320, height: 520 });
  await page.waitForTimeout(400);
  const w = await widgetCard(page);
  assert.ok(w.shown, "no card");
  assert.equal(w.action, "Send an email");
  assert.equal(w.approve, "Approve in the Jarvis bar");
  assert.equal(w.approveHidden, false, "the one Approve is hidden (options would hide it)");
  assert.ok(w.noteHidden, "the note field is offered while locked");
  for (const secret of ["supplier@example.com", "Order 4471", "send_email", "Send the reply", "invoice", "RAISED"]) {
    assert.ok(!w.text.includes(secret), `the locked widget shows "${secret}": ${w.text}`);
  }
  const quote = K.APPROVAL_RAISED.raised && K.APPROVAL_RAISED.raised.quote;
  if (quote) assert.ok(!w.text.includes(quote), "the rush quote is shown while locked");
  await page.locator("#btn-appr-yes").click();
  await page.waitForTimeout(250);
  const after = await page.evaluate(() => ({ bar: window.__openedInBar || 0, decides: window.__decides || [] }));
  assert.equal(after.bar, 1, "Approve did not open the Jarvis bar");
  assert.equal(after.decides.length, 0, `the widget sent a decision while locked: ${JSON.stringify(after.decides)}`);
  // Deny still decides from the widget, as on the phone.
  await page.locator("#btn-appr-no").click();
  await page.waitForTimeout(250);
  const denied = await page.evaluate(() => window.__decides || []);
  await page.close();
  assert.deepEqual(denied.map((d) => d.approved), [false], "Deny does not work from the locked widget");
});

await check("App lock: a card with no notice gets a plain title, and turning the lock off shows it all (M3)", async () => {
  const page = await K.open(browser, base, "widget.html", { pending: [{ ...K.APPROVAL_RAISED, notice: undefined }], appLock: true }, { width: 320, height: 520 });
  await page.waitForTimeout(400);
  const locked = await widgetCard(page);
  assert.equal(locked.action, "Jarvis is waiting for your approval");
  assert.ok(!locked.text.includes("supplier@example.com"));
  await page.evaluate(() => window.__emit("security-changed",
    { appLock: false, relockAfterSecs: 60, approvals: "risky", privateAnswers: false }));
  await page.waitForTimeout(250);
  const open = await widgetCard(page);
  // Unlocked, a row with no notice gets the PC's own fallback (card-words.js), not the code name.
  assert.equal(open.action, "Jarvis wants your OK for \"send email\"");
  assert.equal(open.approve, "Approve");
  assert.equal(open.noteHidden, false);
  await page.locator("#btn-appr-yes").click();
  await page.waitForTimeout(250);
  const sent = await page.evaluate(() => ({ bar: window.__openedInBar || 0, decides: window.__decides || [] }));
  // And back on: the card is cut down again at once.
  await page.evaluate(() => window.__emit("security-changed",
    { appLock: true, relockAfterSecs: 60, approvals: "risky", privateAnswers: false }));
  await page.waitForTimeout(250);
  const relocked = await widgetCard(page);
  await page.close();
  assert.equal(sent.bar, 0);
  assert.deepEqual(sent.decides.map((d) => d.approved), [true], "CONTROL: an unlocked widget cannot approve");
  assert.equal(relocked.action, "Jarvis is waiting for your approval");
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nWindows Hello decides in Rust, and the pages say so");
process.exit(fails.length ? 1 : 0);
