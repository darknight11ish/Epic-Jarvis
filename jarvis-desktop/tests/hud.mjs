/**
 * The HUD window must actually run, under the policy the packaged app serves.
 *
 * Shipped broken: jarvis_hud.html declared no charset, WebView2 decoded it as
 * windows-1252, the 83 non-ASCII bytes in its main <script> changed, and that
 * script's text stopped matching the sha256 Tauri computes from the UTF-8
 * file at build time (tauri-codegen, `inject_script_hashes`). A hash in
 * script-src turns 'unsafe-inline' off, so the header CSP refused the whole
 * script: no Send, no status, nothing on screen to say why. Every other test
 * here serves pages from a plain static server with no CSP header, which is
 * why none of them could see it.
 *
 * Then, once it ran, it still would not chat: `S.online` required the
 * OpenJarvis agent on :8000, which this setup never runs, so the page stayed
 * on sample replies against a backend that could answer.
 *
 * So this serves the page as Tauri does - header CSP from tauri.conf.json
 * with every inline script hashed, the shell's bootstrap injected first, no
 * charset on the response - and drives a real send.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const CONF = JSON.parse(readFileSync(join(HERE, "..", "src-tauri", "tauri.conf.json"), "utf8"));
const BOOT = readFileSync(join(HERE, "..", "src-tauri", "src", "hud_bootstrap.js"), "utf8");
const ORIGIN = "http://tauri.localhost";
const BACKEND = "http://127.0.0.1:4719";

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── Every window declares its encoding (no browser needed) ──────────────── */

for (const file of readdirSync(SRC).filter((f) => f.endsWith(".html"))) {
  await check(`${file} declares UTF-8 in its first 1024 bytes`, async () => {
    const head = readFileSync(join(SRC, file)).subarray(0, 1024).toString("latin1");
    assert.match(head, /<meta\s+charset=["']?utf-8/i,
      "without it WebView2 guesses windows-1252 and any inline script with a " +
      "non-ASCII character fails Tauri's CSP hash");
  });
}

/* ── The HUD, served the way the packaged app serves it ──────────────────── */

/** Tauri's header CSP: the configured policy plus a sha256 per inline script. */
function tauriCsp(html) {
  // Comments out first: tauri-codegen hashes real <script> elements from a
  // parsed DOM, so the word inside a comment must not start a match here.
  const hashes = [...html.replace(/<!--[\s\S]*?-->/g, "").matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)]
    .map((m) => m[1])
    .filter((s) => s.length)
    .map((s) => `'sha256-${createHash("sha256").update(s.replace(/\r\n?/g, "\n"), "utf8").digest("base64")}'`);
  return CONF.app.security.csp.replace(/script-src ([^;]*)/, (_, v) => `script-src ${v} ${hashes.join(" ")}`);
}

const cors = {
  "Access-Control-Allow-Origin": ORIGIN,
  "Access-Control-Allow-Headers": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

async function openHud(browser, status) {
  const page = await browser.newPage();
  const problems = [];
  const chats = [];
  page.on("pageerror", (e) => problems.push(String(e)));
  page.on("console", (m) => {
    if (m.type() === "error" && /Content Security Policy|Refused to/.test(m.text())) problems.push(m.text());
  });
  await page.addInitScript(BOOT
    .replace("__JARVIS_BASE__", JSON.stringify(BACKEND))
    .replace("__JARVIS_TOKEN__", JSON.stringify("test-token")));
  const html = readFileSync(join(SRC, "jarvis_hud.html"), "utf8");
  await page.route("**/*", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    if (url.origin === ORIGIN && url.pathname === "/jarvis_hud.html") {
      return route.fulfill({
        status: 200,
        body: Buffer.from(html, "utf8"),
        // No charset: the page has to carry its own.
        headers: { "Content-Type": "text/html", "Content-Security-Policy": tauriCsp(html) },
      });
    }
    if (url.origin === BACKEND) {
      if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
      if (url.pathname === "/api/status") return route.fulfill({ status: 200, headers: cors, json: status });
      if (url.pathname === "/api/chat") {
        chats.push(JSON.parse(req.postData() || "{}"));
        return route.fulfill({
          status: 200, headers: cors,
          json: { model: "qwen3:8b", choices: [{ message: { role: "assistant", content: "Hello from the backend." } }] },
        });
      }
      return route.fulfill({ status: 404, headers: cors, json: { error: "not in this test" } });
    }
    return route.abort();
  });
  await page.goto(`${ORIGIN}/jarvis_hud.html`);
  await page.waitForTimeout(800);
  return { page, problems, chats };
}

async function send(page, text) {
  await page.fill("#input", text);
  await page.click("#send");
  await page.waitForTimeout(800);
  return page.evaluate(() => [...document.querySelectorAll("#log > *")].map((el) => ({
    who: el.querySelector(".who")?.textContent,
    body: el.querySelector(".body")?.textContent,
  })));
}

const browser = await K.launch();

await check("the HUD's main script runs under Tauri's header CSP", async () => {
  const { page, problems } = await openHud(browser, { jarvis: false, ollama: true, proxy: false });
  const ran = await page.evaluate(() => ({
    charset: document.characterSet,
    setView: typeof window.setView,
  }));
  await page.close();
  assert.equal(ran.charset, "UTF-8");
  assert.equal(ran.setView, "function", "the main <script> never ran");
  assert.deepEqual(problems, []);
});

await check("with Ollama up and no OpenJarvis, Send reaches /api/chat and shows the reply", async () => {
  const { page, problems, chats } = await openHud(browser, { jarvis: false, ollama: true, proxy: false });
  const log = await send(page, "hi");
  await page.close();
  assert.equal(chats.length, 1, "the page never POSTed /api/chat - still gated on :8000?");
  assert.equal(chats[0].messages.at(-1).content, "hi");
  assert.ok(log.some((m) => m.who === "you" && m.body === "hi"), JSON.stringify(log));
  assert.ok(log.some((m) => m.who === "jarvis" && m.body === "Hello from the backend."), JSON.stringify(log));
  assert.deepEqual(problems, []);
});

await check("with nothing up, Send still answers - from sample replies, and says why", async () => {
  const { page, chats } = await openHud(browser, { jarvis: false, ollama: false, proxy: false });
  const banner = await page.locator("#banner-text").textContent();
  const log = await send(page, "hi");
  await page.close();
  assert.equal(chats.length, 0, "offline must not POST a turn that cannot be answered");
  assert.ok(log.some((m) => m.who === "you" && m.body === "hi"), JSON.stringify(log));
  assert.match(banner, /Ollama/, "the banner should name what is actually missing");
  assert.doesNotMatch(banner, /jarvis serve/, "OpenJarvis is not part of this setup");
});

await browser.close();
if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nall passed");
