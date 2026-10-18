/**
 * Clipboard history (Pillar 14B) — the drawer on the real Quickbar page.
 *
 * `tests/clipboard-time-machine.mjs` covers the drawer's own logic in plain
 * node. This file is the other half: it loads the real `src/index.html`,
 * mounts the real `src/main.js`, sends the real event the hotkey sends, and
 * drives the real DOM — because the parts that can only go wrong in the page
 * are the wiring (the event name, the command names and arguments, what is
 * drawn, what Esc and losing focus do to private words).
 *
 * The Tauri bridge is stubbed (there is no backend in a test), but only the six
 * clipboard commands are stubbed with a small in-memory ring; every other
 * command still answers exactly as `tests/uikit.mjs` answers it. That stub is
 * deliberately local to this file rather than added to the shared harness:
 * the shared harness is another piece of work's file right now
 * (tests/uikit.mjs), and this suite only needs its own six commands.
 *
 * THE PRIVACY PROMISES THIS PROVES, in the page's own behaviour:
 *   - the drawer opens saying Off, with no copy drawn, until the owner presses
 *     Turn on;
 *   - Esc closes the drawer and does NOT hide the bar, so its handler is the
 *     one that took the key;
 *   - losing focus clears every copied word out of the page;
 *   - a locked answer draws no row at all, even if a stale state held one.
 */
import assert from "node:assert/strict";
import * as K from "./uikit.mjs";

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try {
    await fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

/** The drawer's commands, stubbed against a copy of the Rust ring's shape. */
const CLIPBOARD_STUB = `
  (() => {
    const state = {
      enabled: false,
      locked: false,
      items: [],
      max_items: 25,
      max_item_chars: 32768,
    };
    window.__clipboardCalls = [];
    const answerFor = (kind, text) => {
      if (kind === "pretty_json") {
        if (text === "not json") {
          return { ok: false, kind, text: "", reason: "that is not valid JSON" };
        }
        return { ok: true, kind, text: '{\\n  "a": 1\\n}', reason: "" };
      }
      if (kind === "markdown_table") {
        return { ok: true, kind, text: "| a | b |\\n| --- | --- |\\n| 1 | 2 |\\n", reason: "" };
      }
      return { ok: true, kind, text: "https://example.com/page?id=42", reason: "" };
    };
    const original = window.__TAURI__.core.invoke;
    window.__TAURI__.core.invoke = async (cmd, args) => {
      window.__clipboardCalls.push([cmd, args]);
      switch (cmd) {
        case "clipboard_tm_state":
          return JSON.parse(JSON.stringify(state));
        case "clipboard_tm_enable":
          state.enabled = true;
          return JSON.parse(JSON.stringify(state));
        case "clipboard_tm_disable":
          state.enabled = false;
          return JSON.parse(JSON.stringify(state));
        case "clipboard_tm_clear":
          state.items = [];
          return JSON.parse(JSON.stringify(state));
        case "clipboard_tm_lock":
          state.enabled = false;
          state.items = [];
          return JSON.parse(JSON.stringify(state));
        case "clipboard_tm_transform": {
          const item = state.items[args.index];
          if (!item) throw new Error("that copy is no longer in the list");
          return answerFor(args.kind, item.text);
        }
        case "write_clipboard_private":
        case "write_clipboard":
          window.__copiedText = args.text;
          return null;
        default:
          return original(cmd, args);
      }
    };
    window.__setClipboardState = (next) => {
      Object.assign(state, next);
      window.__emit("clipboard-tm-open", null);
    };
    window.__emitClipboard = (event) => window.__emit(event, null);
  })();
`;

/** Opens the quickbar page and swaps in the six-command clipboard stub. */
async function open() {
  const page = await K.open(browser, base, "index.html", {});
  await page.evaluate(CLIPBOARD_STUB);
  return page;
}

const state = (page) =>
  page.evaluate(() => ({
    hidden: document.getElementById("clipboard-drawer").hidden,
    status: document.getElementById("clipboard-status").textContent,
    line: document.getElementById("clipboard-line").textContent,
    rows: [...document.querySelectorAll(".clipboard-row")].map((row) => ({
      preview: row.querySelector(".clipboard-row-preview").textContent,
      from: row.querySelector(".clipboard-row-from")?.textContent || "",
      buttons: [...row.querySelectorAll(".clipboard-transform")].map((b) => b.dataset.kind),
    })),
    enable: document.getElementById("clipboard-enable").hidden,
    disable: document.getElementById("clipboard-disable").hidden,
    forget: document.getElementById("clipboard-forget").hidden,
    calls: window.__clipboardCalls.map((c) => c[0]),
  }));

const emitted = (page, event, payload = null) =>
  page.evaluate(({ event, payload }) => window.__emit(event, payload), { event, payload });

/* ── Off by default: what the hotkey shows on a fresh launch ─────────────── */

await check("the hotkey opens the drawer saying Off, with nothing drawn", async () => {
  const page = await open();
  await emitted(page, "clipboard-tm-open");
  await page.waitForTimeout(150);
  const shown = await state(page);
  // textContent, not innerText: the title is styled uppercase on screen.
  const title = await page.locator("#clipboard-title").textContent();
  await page.close();
  assert.equal(shown.hidden, false, "the drawer did not open");
  assert.equal(title, "Clipboard history");
  assert.equal(shown.status, "Off");
  assert.match(shown.line, /Nothing you copy is being kept/i);
  assert.equal(shown.rows.length, 0, "a copy was drawn before the switch was on");
  assert.equal(shown.enable, false, "Turn on is not offered");
  assert.equal(shown.disable, true, "Turn off is offered while off");
  assert.equal(shown.forget, true, "Forget is offered with nothing to forget");
});

await check("turning it on is one press, and the words say memory only", async () => {
  const page = await open();
  await emitted(page, "clipboard-tm-open");
  await page.waitForTimeout(120);
  await page.locator("#clipboard-enable").click();
  await page.waitForTimeout(150);
  const justOn = await state(page);
  // A copy arriving while it is on: the line now states the promise in words.
  await page.evaluate(() => {
    window.__setClipboardState({
      items: [{ text: "a copied sentence", app: "Code.exe", title: "notes.py" }],
    });
    window.__emit("clipboard-tm-changed", null);
  });
  await page.waitForTimeout(200);
  const withCopy = await page.locator("#clipboard-line").textContent();
  await page.close();
  assert.equal(justOn.status, "On");
  assert.match(justOn.line, /Nothing kept yet/i);
  assert.ok(justOn.calls.includes("clipboard_tm_enable"), "Turn on did not call the command");
  assert.equal(justOn.disable, false, "Turn off is not offered while on");
  assert.match(withCopy, /memory only/i);
  assert.match(withCopy, /forgotten when Jarvis locks/i);
});

/* ── Copies: newest first, three transforms each, a dry run on click ────── */

await check("kept copies are drawn newest first with the three transforms each", async () => {
  const page = await open();
  await page.evaluate(() => window.__setClipboardState({
    enabled: true,
    items: [
      { text: "https://example.com/?utm_source=news", app: "firefox.exe", title: "News" },
      { text: "a,b\n1,2", app: "Code.exe", title: "table.csv" },
    ],
  }));
  await page.waitForTimeout(150);
  const shown = await state(page);
  await page.close();
  assert.deepEqual(shown.rows.map((r) => r.preview), [
    "https://example.com/?utm_source=news",
    "a,b 1,2",
  ]);
  assert.equal(shown.rows[0].from, "firefox.exe · News");
  assert.deepEqual(shown.rows[0].buttons, [
    "markdown_table",
    "pretty_json",
    "strip_tracking_params",
  ]);
});

await check("a transform runs on the right copy and shows the PC's answer", async () => {
  const page = await open();
  await page.evaluate(() => window.__setClipboardState({
    enabled: true,
    items: [{ text: "not json", app: "", title: "" }],
  }));
  await page.waitForTimeout(150);
  await page.locator('.clipboard-row [data-kind="pretty_json"]').click();
  await page.waitForTimeout(200);
  const result = await page.evaluate(() => ({
    hidden: document.getElementById("clipboard-result").hidden,
    kind: document.getElementById("clipboard-result-kind").textContent,
    line: document.getElementById("clipboard-result-line").textContent,
    text: document.getElementById("clipboard-result-text").textContent,
    copy: document.getElementById("clipboard-result-copy").hidden,
    calls: window.__clipboardCalls.map((c) => [c[0], c[1]]),
  }));
  await page.close();
  assert.equal(result.hidden, false, "the transform's answer did not appear");
  assert.match(result.kind, /Pretty JSON/);
  assert.equal(result.line, "that is not valid JSON", "the PC's refusal was rewritten");
  assert.equal(result.text, "", "a refusal put text in the answer");
  assert.equal(result.copy, true, "a refusal offered Copy");
  const call = result.calls.find((c) => c[0] === "clipboard_tm_transform");
  assert.deepEqual(call[1], { index: 0, kind: "pretty_json" });
});

await check("Copy takes the result as a private copy, not a plain one", async () => {
  const page = await open();
  await page.evaluate(() => window.__setClipboardState({
    enabled: true,
    items: [{ text: '{"a": 1}', app: "", title: "" }],
  }));
  await page.waitForTimeout(150);
  await page.locator('.clipboard-row [data-kind="pretty_json"]').click();
  await page.waitForTimeout(150);
  await page.locator("#clipboard-result-copy").click();
  await page.waitForTimeout(150);
  const result = await page.evaluate(() => ({
    copied: window.__copiedText,
    label: document.getElementById("clipboard-result-copy").textContent,
    calls: window.__clipboardCalls.map((c) => c[0]),
  }));
  await page.close();
  assert.equal(result.copied, '{\n  "a": 1\n}');
  assert.ok(result.calls.includes("write_clipboard_private"),
    "the result was copied without the private-copy exclusion");
  assert.equal(result.label, "Copied");
});

/* ── Esc closes the drawer, not the bar ─────────────────────────────────── */

await check("Esc closes the drawer and does not hide the bar", async () => {
  const page = await open();
  await page.evaluate(() => window.__setClipboardState({ enabled: true, items: [] }));
  await page.waitForTimeout(150);
  await page.keyboard.press("Escape");
  await page.waitForTimeout(150);
  const after = await page.evaluate(() => ({
    hidden: document.getElementById("clipboard-drawer").hidden,
    calls: window.__clipboardCalls.map((c) => c[0]),
    allCalls: window.__calls.map((c) => c[0]),
  }));
  await page.close();
  assert.equal(after.hidden, true, "Escape left the drawer open");
  assert.equal(after.allCalls.includes("hide_quickbar"), false,
    "Escape reached the bar's own dismiss as well");
});

/* ── Lost focus clears the page ─────────────────────────────────────────── */

await check("losing focus clears every copied word out of the page", async () => {
  const page = await open();
  await page.evaluate(() => window.__setClipboardState({
    enabled: true,
    items: [{ text: "a private sentence nobody should leave in a hidden page", app: "", title: "" }],
  }));
  await page.waitForTimeout(150);
  const before = await state(page);
  await page.evaluate(() => window.dispatchEvent(new Event("blur")));
  await page.waitForTimeout(150);
  const after = await page.evaluate(() => ({
    hidden: document.getElementById("clipboard-drawer").hidden,
    rows: document.querySelectorAll(".clipboard-row").length,
    page: document.body.textContent.includes("a private sentence"),
  }));
  await page.close();
  assert.equal(before.rows.length, 1, "the copy was not drawn to begin with");
  assert.equal(after.hidden, true, "the drawer stayed open after focus was lost");
  assert.equal(after.rows, 0, "a copied word stayed in the page after focus was lost");
  assert.equal(after.page, false, "a copied word is still in the page's text");
});

/* ── Locked fails closed ────────────────────────────────────────────────── */

await check("a locked state draws no copy, even if the answer still holds one", async () => {
  const page = await open();
  await page.evaluate(() => window.__setClipboardState({
    locked: true,
    enabled: true,
    items: [{ text: "kept before the lock", app: "", title: "" }],
  }));
  await page.waitForTimeout(150);
  const shown = await state(page);
  const line = await page.locator("#clipboard-line").innerText();
  await page.close();
  assert.equal(shown.rows.length, 0, "a locked drawer drew a kept copy");
  assert.match(line, /Jarvis is locked/i);
  assert.equal(shown.enable, true, "a locked drawer offered Turn on");
});

/* ── Forget everything ──────────────────────────────────────────────────── */

await check("Forget everything calls the command and empties the drawer", async () => {
  const page = await open();
  await page.evaluate(() => window.__setClipboardState({
    enabled: true,
    items: [{ text: "forget me", app: "", title: "" }],
  }));
  await page.waitForTimeout(150);
  await page.locator("#clipboard-forget").click();
  await page.waitForTimeout(150);
  const shown = await state(page);
  const line = await page.locator("#clipboard-line").innerText();
  await page.close();
  assert.ok(shown.calls.includes("clipboard_tm_clear"));
  assert.equal(shown.rows.length, 0);
  assert.match(line, /Nothing kept yet/i);
});

/* ── A changed state refreshes an open drawer ───────────────────────────── */

await check("a kept copy arriving while the drawer is open redraws it", async () => {
  const page = await open();
  await page.evaluate(() => window.__setClipboardState({ enabled: true, items: [] }));
  await page.waitForTimeout(150);
  await page.evaluate(() => {
    window.__setClipboardState({ items: [{ text: "just copied", app: "Code.exe", title: "x" }] });
    window.__emit("clipboard-tm-changed", null);
  });
  await page.waitForTimeout(200);
  const shown = await state(page);
  await page.close();
  assert.equal(shown.rows.length, 1, "the drawer did not re-read on the changed event");
  assert.equal(shown.rows[0].preview, "just copied");
});

if (fails.length) {
  console.error(`\n${fails.length} clipboard drawer page check(s) failed: ${fails.join(", ")}`);
  await close();
  await browser.close();
  process.exit(1);
}
await close();
await browser.close();
console.log("\nAll clipboard drawer page checks passed.");
