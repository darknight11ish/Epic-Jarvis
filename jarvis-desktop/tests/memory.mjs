/**
 * The memory pane: one fact, one decision, and nothing that acts in bulk.
 *
 * The extractor now fills a review queue on its own — nobody asked for the
 * thing that is waiting. That makes this pane the only place the owner ever
 * sees what Jarvis wanted to remember about them, and the only place they can
 * say no. Two properties are worth a test rather than a comment:
 *
 *   * there is no control here that decides more than one fact. Not a
 *     select-all, not a "keep the rest", not a checkbox column.
 *   * forgetting is irreversible and the UI says so BEFORE it happens, not
 *     after.
 *
 * It also pins the failure that is easiest to write by accident: the learning
 * switch renders what the server ANSWERED, not what the button asked for.
 */
import assert from "node:assert/strict";
import * as K from "./uikit.mjs";

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const SIZE = { width: 1180, height: 820 };
const writes = (page) => page.evaluate(() => window.__memoryWrites || []);

async function memoryTab(data = {}) {
  const page = await K.open(browser, base, "brain.html", data, SIZE);
  await page.locator("#tab-memory").click();
  await page.waitForTimeout(250);
  return page;
}

/* ── It is reachable at all ──────────────────────────────────────────────── */

await check("the Memory tab exists and opens its own view", async () => {
  const page = await memoryTab();
  const shown = await page.locator("#view-memory").isVisible();
  const selected = await page.locator("#tab-memory").getAttribute("aria-selected");
  await page.close();
  assert.equal(shown, true, "the view did not appear");
  assert.equal(selected, "true");
});

await check("the rail badge counts what is waiting", async () => {
  const page = await memoryTab();
  const badge = await page.locator("#count-memory").innerText();
  await page.close();
  assert.equal(badge.trim(), "2",
    "nobody asked for the proposals, so the badge is the only thing that says they arrived");
});

/* ── One fact, one decision ──────────────────────────────────────────────── */

await check("keeping one proposal sends exactly one decision, with its id", async () => {
  const page = await memoryTab();
  await page.locator("#memory-proposals .row-item").first()
            .getByRole("button", { name: "Keep" }).click();
  await page.waitForTimeout(300);
  const sent = await writes(page);
  await page.close();
  assert.equal(sent.length, 1, `sent ${sent.length}: ${JSON.stringify(sent)}`);
  assert.equal(sent[0].cmd, "brain_memory_decide");
  assert.equal(sent[0].id, 41);
  assert.equal(sent[0].accept, true);
});

await check("discarding is the same shape, with accept false", async () => {
  const page = await memoryTab();
  await page.locator("#memory-proposals .row-item").first()
            .getByRole("button", { name: "Discard" }).click();
  await page.waitForTimeout(300);
  const sent = await writes(page);
  await page.close();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].accept, false);
});

await check("NOTHING on this pane acts on more than one fact", async () => {
  // The rule the whole product is arranged around. A select-all here would be
  // an approve-all by another name, and it would be the easiest thing in the
  // world to add for convenience.
  const page = await memoryTab();
  const labels = await page.locator("#view-memory button").allInnerTexts();
  const boxes = await page.locator("#view-memory input[type=checkbox]").count();
  await page.close();
  assert.equal(boxes, 0, "a checkbox column is how bulk actions start");
  const bulk = labels.filter((t) =>
    /\ball\b|\beverything\b|\bbulk\b|\brest\b|\bremaining\b/i.test(t)
    && !/export everything/i.test(t));
  assert.deepEqual(bulk, [], `bulk-looking controls: ${JSON.stringify(bulk)}`);
});

/* ── Forgetting is irreversible, and says so first ───────────────────────── */

await check("forgetting asks before it acts, and warns it cannot be undone", async () => {
  const page = await memoryTab();
  let asked = "";
  page.on("dialog", (d) => { asked = d.message(); d.dismiss(); });
  await page.locator("#memory-facts .row-item").first()
            .getByRole("button", { name: "Forget" }).click();
  await page.waitForTimeout(300);
  const sent = await writes(page);
  await page.close();
  assert.match(asked, /cannot be undone/i, `the confirm said "${asked}"`);
  assert.equal(sent.length, 0, "dismissing the confirm still sent the write");
});

await check("confirming it sends one forget for that id", async () => {
  const page = await memoryTab();
  page.on("dialog", (d) => d.accept());
  await page.locator("#memory-facts .row-item").first()
            .getByRole("button", { name: "Forget" }).click();
  await page.waitForTimeout(300);
  const sent = await writes(page);
  await page.close();
  assert.equal(sent.length, 1, JSON.stringify(sent));
  assert.equal(sent[0].cmd, "brain_memory_forget");
  assert.equal(sent[0].id, 7);
});

await check("a retired fact offers no Forget or Reword at all", async () => {
  // The fixture deliberately omits the server's `current` flag on this row and
  // gives only `valid_to`. The pane has to work that out for itself: a retired
  // fact shown as live is one the owner thinks Jarvis still uses, with a
  // Forget button that would do nothing.
  // It is already not recalled. Offering to forget it again would imply there
  // is something left to undo, and offering to reword it would create a live
  // fact from a dead one.
  const page = await memoryTab();
  const retired = page.locator("#memory-facts .row-item").nth(2);
  const tag = await retired.locator(".row-tag").innerText();
  const buttons = await retired.locator("button").count();
  await page.close();
  assert.equal(tag.trim().toLowerCase(), "retired");
  assert.equal(buttons, 0, "a retired fact should have no actions");
});

/* ── The switch renders the answer, not the request ──────────────────────── */

await check("the learning switch reflects what the server said", async () => {
  const page = await memoryTab();
  await page.getByRole("button", { name: "Stop learning" }).click();
  await page.waitForTimeout(300);
  const sent = await writes(page);
  await page.close();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].cmd, "brain_memory_learning");
  assert.equal(sent[0].enabled, false);
});

await check("when the environment overrides the switch, the toast says so", async () => {
  // JARVIS_EXTRACT=0 is a floor the pane cannot lift. The server answers 200
  // and still refuses, so a pane that rendered its own request would show
  // "off" while the learner kept running.
  const page = await memoryTab({ learningFloor: true });
  await page.getByRole("button", { name: "Stop learning" }).click();
  await page.waitForTimeout(400);
  const toast = await page.locator("#toast").innerText();
  await page.close();
  assert.match(toast, /JARVIS_EXTRACT/,
    `the toast said "${toast}" instead of relaying the server's refusal`);
});

await check("a refused write surfaces rather than looking like success", async () => {
  const page = await memoryTab({ memoryRefuses: "memory layer not importable" });
  await page.locator("#memory-proposals .row-item").first()
            .getByRole("button", { name: "Keep" }).click();
  await page.waitForTimeout(400);
  const toast = await page.locator("#toast").innerText();
  await page.close();
  assert.match(toast, /not importable/, `the toast said "${toast}"`);
});

/* ── Controls ────────────────────────────────────────────────────────────── */

await check("CONTROL: an empty queue says which of the two reasons it is", async () => {
  const page = await memoryTab({
    brain: { ...K.BRAIN, memory_pending: { available: true, pending: [] } },
  });
  const text = await page.locator("#memory-proposals").innerText();
  await page.close();
  assert.match(text, /learning is off/i,
    "an empty queue is ambiguous - nothing heard, or nothing listening");
});

await check("CONTROL: a missing backend says so instead of rendering empty", async () => {
  const page = await memoryTab({
    brain: { ...K.BRAIN, memory_facts: { available: false, error: "no memory layer" } },
  });
  const text = await page.locator("#memory-facts").innerText();
  await page.close();
  assert.ok(text.trim().length > 0, "a missing module and an empty store must not look alike");
});

await check("CONTROL: no page threw while any of this ran", async () => {
  const page = await memoryTab();
  const errors = await page.evaluate(() => window.__errors || []);
  await page.close();
  assert.deepEqual(errors, []);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nthe memory pane holds");
process.exit(fails.length ? 1 : 0);
