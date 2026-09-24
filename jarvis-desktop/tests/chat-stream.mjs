/**
 * The quickbar reads the reply the backend REALLY sends.
 *
 * tests/fixtures/chat-stream-cases.json is written by running the backend's
 * producer (backend/test_chat_stream_contract.py): Ollama's real
 * /v1/chat/completions stream, relayed by both branches of /api/chat,
 * including the keepalive and `: jarvis-status approval` lines, an answer cut
 * short at the length limit, and the PC's own error sentences. Each case goes
 * through the page's real `consumeLine`, line by line the way
 * `commands.rs pump_chat` hands lines over (blank lines dropped, the
 * X-Jarvis-Route line first), and the card must show what the model said.
 *
 * Before this the quickbar's chat tests fed bare words and one hand-typed
 * `data:` line, and nothing held the reader to what the server sends.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const FIXTURE = JSON.parse(readFileSync(join(HERE, "fixtures", "chat-stream-cases.json"), "utf8"));

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** The lines pump_chat sends to the page for one response body: split on
 *  "\n", a trailing "\r" trimmed, blank lines dropped. */
const pumpLines = (body) => body.split("\n").map((l) => l.replace(/\r$/, "")).filter((l) => l.trim());

/** The route line pump_chat sends first (commands.rs route_line_from_header:
 *  lane, where and gate only - checked against this same fixture by the
 *  Rust test `the_route_line_is_built_from_the_real_header`). */
const routeLine = (header) => {
  const h = JSON.parse(header);
  const out = {};
  for (const k of ["lane", "where", "gate"]) if (typeof h[k] === "string") out[k] = h[k];
  return "\u001fjarvis-route:" + JSON.stringify(out);
};

const localRoute = FIXTURE.route_headers.find((r) => r.expect.where === "local");

async function ask(lines) {
  const page = await K.open(browser, base, "index.html", { chatReplies: [lines] },
    { width: 750, height: 600 });
  // Every status the card shows while the answer streams, in order.
  await page.evaluate(() => {
    window.__statuses = [];
    const el = document.getElementById("card-status-text");
    new MutationObserver(() => window.__statuses.push(el.textContent))
      .observe(el, { childList: true, characterData: true, subtree: true });
  });
  await page.locator("#prompt").fill("hi");
  await page.locator("#prompt").press("Enter");
  await page.waitForTimeout(400);
  const got = await page.evaluate(() => ({
    answer: document.getElementById("answer").textContent.trim(),
    status: document.getElementById("card-status-text").textContent,
    statuses: window.__statuses,
    tier: document.getElementById("route-tier").textContent,
    model: document.getElementById("route-model").textContent,
  }));
  await page.close();
  return got;
}

for (const c of FIXTURE.cases) {
  await check(`quickbar reads the real reply: ${c.name}`, async () => {
    const got = await ask([routeLine(localRoute.header), ...pumpLines(c.body)]);
    if (c.expect.error) {
      assert.match(got.answer, /Jarvis could not answer\./);
      // The card renders Markdown, so `ollama serve` shows as code, without
      // its backticks.
      const said = c.expect.error.replace(/`/g, "");
      assert.ok(got.answer.includes(said), `the PC's sentence is not shown: ${got.answer}`);
      return;
    }
    if (c.expect.length) {
      assert.ok(got.answer.startsWith(c.expect.text), got.answer);
      assert.match(got.answer, /Answer cut short/);
      assert.equal(got.status, "Cut short");
    } else {
      assert.equal(got.answer, c.expect.text);
      assert.equal(got.status, "Complete");
    }
    for (const word of c.expect.statuses) {
      if (word === "approval") {
        assert.ok(got.statuses.includes("Waiting for your approval…"),
          `the card never said it was waiting: ${JSON.stringify(got.statuses)}`);
      }
    }
  });
}

for (const r of FIXTURE.route_headers) {
  await check(`quickbar badge from the real X-Jarvis-Route: ${r.name}`, async () => {
    const ok = FIXTURE.cases.find((c) => c.name === "local turn");
    const got = await ask([routeLine(r.header), ...pumpLines(ok.body)]);
    assert.equal(got.tier, r.expect.where === "cloud" ? "Cloud" : "Local",
      "the badge must say where the answer was made, from the header, not the chunk's model");
    assert.equal(got.model, r.expect.lane);
  });
}

await browser.close();
await close();
if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nthe quickbar reads what the backend really sends");
