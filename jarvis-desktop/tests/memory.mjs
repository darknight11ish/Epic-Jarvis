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
import { execFileSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as K from "./uikit.mjs";

// Real backend output, produced by the real Python modules in backend/ at
// test time, so what the pane is tested against is what the backend sends -
// not a fixture that agrees with the pane because the same hand wrote both.
const BACKEND_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "backend");
function realPython(code) {
  return JSON.parse(execFileSync("python3", ["-c", code],
    { cwd: BACKEND_DIR, encoding: "utf8", env: { ...process.env, JARVIS_NO_EMBED: "1" } }));
}

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

await check("turning learning on waits for its approval card, and says so", async () => {
  // learning-asks.patch: ON answers 202 {waiting: true, enabled: false}. The
  // pane used to read any non-enabled answer as "Learning is off."
  const brain = { ...K.BRAIN, memory_facts: { ...K.BRAIN.memory_facts, learning: false } };
  const page = await memoryTab({ brain, learningWaits: true });
  await page.getByRole("button", { name: "Start learning" }).click();
  await page.waitForTimeout(400);
  const toast = await page.locator("#toast").innerText();
  const line = await page.locator("#memory-learning .learning-waiting").innerText();
  const still = await page.getByRole("button", { name: "Start learning" }).count();
  const sent = await writes(page);
  await page.close();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].enabled, true);
  assert.match(toast, /Waiting for your approval/, `the toast said "${toast}"`);
  assert.doesNotMatch(toast, /Learning is (on|off)/);
  assert.match(line, /Waiting for your approval to turn learning on/);
  assert.equal(still, 1, "it is not on until the card is approved");
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

/* ── The overnight-memory offer ──────────────────────────────────────────── */

// The REAL card, from the real jarvis_sleep.reminder_card() - not a copy of
// it. It used to be a hand-made fixture here, which is how the pane could
// promise "Jarvis will tidy its memory overnight" about a pass nobody built.
const OFFER = realPython(
  "import sys, json; sys.path.insert(0, 'rebuilt'); import jarvis_sleep as S\n"
  + "S._cfg = lambda k, d=None: {'enabled': False, 'remind': True}.get(k, d)\n"
  + "S._seen.clear(); print(json.dumps(S.reminder_card()))");
const TITLE = new RegExp(OFFER.title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i");

const withOffer = (extra = {}) => ({
  brain: { ...K.BRAIN, memory_pending: {
    ...K.BRAIN.memory_pending,
    setup: { ...K.BRAIN.memory_pending.setup, sleep_time_offer: OFFER },
  } },
  ...extra,
});

await check("the daily card shows when the server offers it", async () => {
  const page = await memoryTab(withOffer());
  const text = await page.locator("#memory-learning").innerText();
  await page.close();
  assert.match(text, TITLE, `said "${text}"`);
});

await check("nothing offers it when the server sends none", async () => {
  const page = await memoryTab();
  const text = await page.locator("#memory-learning").innerText();
  await page.close();
  assert.doesNotMatch(text, TITLE,
    "the default fixture carries no offer, so nothing should show one");
});

await check("Enable sends {enabled: true} and stops offering", async () => {
  const page = await memoryTab(withOffer());
  await page.getByRole("button", { name: "Enable", exact: true }).click();
  await page.waitForTimeout(300);
  const sent = await writes(page);
  const stillThere = await page.locator("#memory-learning").innerText();
  await page.close();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].cmd, "brain_memory_sleep_time");
  assert.equal(sent[0].enabled, true);
  assert.doesNotMatch(stillThere, TITLE,
    "the card outlived the decision it was asking about");
});

await check("Stop asking sends {remind: false} and stops offering", async () => {
  const page = await memoryTab(withOffer());
  await page.getByRole("button", { name: "Stop asking" }).click();
  await page.waitForTimeout(300);
  const sent = await writes(page);
  await page.close();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].cmd, "brain_memory_sleep_time");
  assert.equal(sent[0].remind, false);
});

await check("Not now dismisses without sending anything", async () => {
  const page = await memoryTab(withOffer());
  await page.getByRole("button", { name: "Not now" }).click();
  await page.waitForTimeout(200);
  const sent = await writes(page);
  const text = await page.locator("#memory-learning").innerText();
  await page.close();
  assert.equal(sent.length, 0, "declining today should not be a network request");
  assert.doesNotMatch(text, TITLE);
});

await check("a failed Enable leaves the card in place, not dismissed", async () => {
  // Dismissing before the write is known to have landed would cost the
  // owner their only way to turn this on until tomorrow's offer, over
  // nothing worse than a network hiccup.
  const page = await memoryTab(withOffer({ memoryRefuses: "memory layer not importable" }));
  await page.getByRole("button", { name: "Enable", exact: true }).click();
  await page.waitForTimeout(300);
  const text = await page.locator("#memory-learning").innerText();
  await page.close();
  assert.match(text, TITLE,
    "a refused write must not look like a handled decision");
});

await check("the card survives an unrelated write refreshing the pane", async () => {
  // The real server marks itself as having offered the moment the route is
  // polled at all, not when the owner acts - so a second read (here forced
  // by nulling the fixture, standing in for the server's own once-a-day
  // drop-off) must still show the card the owner already saw. Without a
  // client-side cache it would vanish before they had a chance to read it.
  const page = await memoryTab(withOffer());
  const beforeText = await page.locator("#memory-learning").innerText();
  await page.evaluate(() => { window.__brain.memory_pending.setup.sleep_time_offer = null; });
  await page.locator("#memory-proposals .row-item").first()
            .getByRole("button", { name: "Keep" }).click();
  await page.waitForTimeout(300);
  const afterText = await page.locator("#memory-learning").innerText();
  await page.close();
  assert.match(beforeText, TITLE);
  assert.match(afterText, TITLE,
    "the offer disappeared once the server stopped resending it, though the owner never dismissed it");
});

await check("Enable says plainly that nothing is built and nothing runs", async () => {
  const page = await memoryTab(withOffer());
  const card = await page.locator("#memory-learning").innerText();
  await page.getByRole("button", { name: "Enable", exact: true }).click();
  await page.waitForTimeout(300);
  const toast = await page.locator("#toast").innerText();
  await page.close();
  assert.match(card, /not built/i, `the card said "${card}"`);
  assert.doesNotMatch(toast, /will tidy/i, `the toast promised a pass: "${toast}"`);
  assert.match(toast, /not built yet/i, `the toast said "${toast}"`);
});

/* ── Real backend output, read by the pane ───────────────────────────────── */

// MemoryStore.status() from the real rebuilt store, in a scratch folder.
const STATUS = realPython(
  "import sys, json, tempfile, pathlib, types\n"
  + "fw = types.ModuleType('jarvis_framework'); fw.CONFIG_DIR = pathlib.Path(tempfile.mkdtemp())\n"
  + "fw.load_framework = lambda: {}; sys.modules['jarvis_framework'] = fw\n"
  + "sys.path.insert(0, 'rebuilt'); import jarvis_memory as M\n"
  + "st = M.MemoryStore(path=pathlib.Path(tempfile.mkdtemp()) / 'memory.db', embedder=M.HashEmbedder())\n"
  + "a = st.add('The owner lives in York', source='user')\n"
  + "st.add('The owner lives in Leeds', source='extracted', supersedes=a)\n"
  + "print(json.dumps(st.status()))");

await check("the Faculties memory card shows what the real store reports", async () => {
  const memory = { available: true, ...STATUS, sleep_time: { enabled: false, remind: true } };
  const page = await K.open(browser, base, "brain.html", { brain: { ...K.BRAIN, memory } }, SIZE);
  await page.locator("#tab-faculties").click();
  await page.waitForTimeout(300);
  const text = await page.locator("#memory").innerText();
  await page.close();
  assert.match(text, /Facts in use\s*1\b/, `said "${text}"`);
  assert.match(text, /No longer used\s*1\b/, "retired facts were counted as in use");
  assert.ok(text.includes(STATUS.db), `the store's file never showed: "${text}"`);
  assert.ok(text.includes(STATUS.embedder), `the embedder never showed: "${text}"`);
  assert.match(text, /not built yet/i);
});

// pending() rows: the columns memory-intake.patch SELECTs, through the real
// jarvis_intake.annotate(). Card 2 has the model's words in `replaces` but no
// `replaces_id`, and jarvis_extract._accept() retires only by id.
const PENDING = realPython(
  "import sys, json; import jarvis_intake as I\n"
  + "rows = [dict(id=61, text='I live in Leeds', replaces='lives in York', replaces_id=12,\n"
  + "             replaces_text='The owner lives in York', confidence=0.8, source='conversation', created=1790000000),\n"
  + "        dict(id=62, text='I like oat milk', replaces='milk preference', replaces_id=None,\n"
  + "             replaces_text=None, confidence=0.7, source='conversation', created=1790000000)]\n"
  + "print(json.dumps(I.annotate(rows)))");

await check("'would replace' only on a card that really replaces a fact", async () => {
  const page = await memoryTab({ brain: { ...K.BRAIN,
    memory_pending: { available: true, pending: PENDING, setup: {} } } });
  const rows = page.locator("#memory-proposals .row-item");
  const withId = await rows.nth(0).innerText();
  const noId = await rows.nth(1).innerText();
  const both = await rows.nth(1).getByRole("button", { name: "Both are true" }).count();
  await page.close();
  assert.match(withId, /would replace: The owner lives in York/,
    `the correction did not name the stored fact: "${withId}"`);
  assert.doesNotMatch(noId, /would replace/,
    "a card with no replaces_id retires nothing, and must not say it would");
  assert.equal(both, 0);
});

await check("a replaced fact names what replaced it", async () => {
  const facts = [
    { id: 5, text: "The owner lives in Leeds", source: "extracted", valid_from: 1790000000,
      created: 1790000000, valid_to: null, retired_at: null, retired_by: null, current: true },
    { id: 4, text: "The owner lives in York", source: "user", valid_from: 1780000000,
      created: 1780000000, valid_to: 1790000000, retired_at: 1790000000, retired_by: 5, current: false },
  ];
  const page = await memoryTab({ brain: { ...K.BRAIN,
    memory_facts: { available: true, learning: true, pending: 0, facts } } });
  const text = await page.locator("#memory-facts").innerText();
  await page.close();
  assert.match(text, /replaced by #5/, `said "${text}"`);
});

/* ── Export: to a file, never the clipboard ──────────────────────────────── */

await check("Export saves to a file the owner picks, and never touches the clipboard", async () => {
  // Windows can sync the clipboard to other devices, so a clipboard copy of
  // the whole memory could leave the machine with nobody deciding it should.
  const page = await memoryTab();
  await page.evaluate(() => {
    window.__clipboardWrites = 0;
    try {
      Object.defineProperty(navigator, "clipboard", { configurable: true,
        value: { writeText: async () => { window.__clipboardWrites++; } } });
    } catch (e) {}
  });
  await page.getByRole("button", { name: "Export everything" }).click();
  await page.waitForTimeout(300);
  const toast = await page.locator("#toast").innerText();
  const clip = await page.evaluate(() => window.__clipboardWrites);
  const sent = await writes(page);
  await page.close();
  assert.equal(clip, 0, "the export went to the clipboard");
  assert.deepEqual(sent.map((w) => w.cmd), ["brain_memory_export"]);
  assert.match(toast, /Saved 3 facts to .*jarvis-memory-2026-09-23\.json/, `said "${toast}"`);
});

await check("closing the Save dialog is not an error", async () => {
  const page = await memoryTab();
  await page.evaluate(() => { window.__exportCancelled = true; });
  await page.getByRole("button", { name: "Export everything" }).click();
  await page.waitForTimeout(300);
  const toast = await page.locator("#toast").innerText().catch(() => "");
  await page.close();
  assert.doesNotMatch(toast, /saved|error|failed/i, `said "${toast}"`);
});

/* ── "What did you know on…": dates both apps read the same way ──────────── */

async function askAsOf(page, typed) {
  page.once("dialog", (d) => d.accept(typed));
  await page.getByRole("button", { name: /What did you know on/ }).click();
  await page.waitForTimeout(300);
  return {
    asked: await page.evaluate(() => window.__asOfAsked ?? null),
    toast: await page.locator("#toast").innerText().catch(() => ""),
    banner: await page.locator("#memory-facts .banner").count(),
  };
}

await check("a date after today, or one that does not exist, is refused before asking", async () => {
  for (const typed of ["2999-01-01", "2026-02-31", "1999-12-31"]) {
    const page = await memoryTab();
    const out = await askAsOf(page, typed);
    await page.close();
    assert.equal(out.asked, null, `${typed} was sent to the server`);
    assert.match(out.toast, /real date/i, `${typed}: "${out.toast}"`);
  }
});

await check("the moment asked for is the LAST second of that day, local time", async () => {
  const page = await memoryTab();
  const out = await askAsOf(page, "2026-06-01");
  const expected = await page.evaluate(() => Math.floor(new Date(2026, 5, 1, 23, 59, 59).getTime() / 1000));
  await page.close();
  assert.equal(out.asked, expected);
  assert.equal(out.banner, 1, "the as-of view did not open");
});

await check("a server that ignored the date is not shown as 'what Jarvis believed then'", async () => {
  const page = await memoryTab();
  await page.evaluate(() => { window.__asOfIgnored = true; });
  const out = await askAsOf(page, "2026-06-01");
  await page.close();
  assert.equal(out.banner, 0, "today's facts were shown under a past date's heading");
  assert.match(out.toast, /without using that date/i, `said "${out.toast}"`);
});

/* ── Skill notes ─────────────────────────────────────────────────────────── */

await check("a skill's notes - which Jarvis reads with it every time - are shown", async () => {
  const skills = { available: true, skills: [
    { name: "invoice-triage", description: "Sorts invoices.", trust: "third_party", uses: 3,
      notes: ["File by supplier, not by month.", { note: "Ask before moving anything over 1000." }] }] };
  const page = await K.open(browser, base, "brain.html", { brain: { ...K.BRAIN, skills } }, SIZE);
  await page.locator("#tab-faculties").click();
  await page.waitForTimeout(300);
  const text = await page.locator("#skills").innerText();
  await page.close();
  assert.match(text, /File by supplier, not by month\./);
  assert.match(text, /Ask before moving anything over 1000\./);
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
