/**
 * The desktop FAQ, in the one Help place it lives in now.
 *
 * Until 2026-10-08 Help was in three places, and the Settings card "Help and
 * FAQ" held fifteen questions ONLY this app's program answers (Quiet against
 * Standby, Alt+Space, "I closed the window but Jarvis is still running", the
 * pairing token, a lost phone). The audit's first suggestion was to delete the
 * card; that was refused, because the questions are the page. So the owner
 * chose to fold it: the questions moved, word for word, to the Brain's own
 * "Tutorials and the FAQ" tab, and the card is gone.
 *
 * WHAT THIS SUITE HAS TO PROVE, and why each half is needed:
 *
 *   * NO ANSWER WAS LOST. `QUESTIONS` below is the fifteen, PINNED BY HAND, the
 *     way they appeared on the old card (this file's own history holds the card
 *     the list was read out of). Every one must be in `src/desktop-help.js`
 *     with a real answer, and every one must actually render in the Brain - data
 *     and page, not data alone, because a list nothing draws is not a help page.
 *   * THE SECOND WAY IN IS REALLY GONE. settings.html has no `#faq` card and no
 *     `.faq-item` left, and the dynamic spans that card drove (`#faq-update-off`
 *     / `#faq-update-on`) are gone from settings.js too - a card that vanished
 *     from the page while its wiring stayed would be a dangling control.
 *   * THE ONE HELP PLACE IS REACHABLE THE WAY THE APP SAYS. The palette's own
 *     Help row (`entry.help`) leaves "tutorials" for the Brain, and the Brain
 *     opens that view for it - the never-hideable entry that must keep working.
 *   * "EVERYTHING JARVIS CAN DO" MOVED WITH IT. The button is in the Brain's
 *     Tutorials tab, pressing it calls `open_features` (features.mjs holds the
 *     ACL side), and the page it opens is untouched.
 *
 * The question text and the answers still checked against the page's own words
 * (the approval sentence, the token line, the slow-model breadcrumb) are the
 * audit-3 checks this file already carried: they moved with the answers.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as K from "./uikit.mjs";
import { DESKTOP_FAQ, mergeQuestions, WORDS as HELP_WORDS } from "../src/desktop-help.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const src = (rel) => readFileSync(join(HERE, "..", rel), "utf8");

/**
 * THE PINNED LIST. The fifteen questions exactly as the Settings card "Help and
 * FAQ" asked them, in its order, read out of that card before it was removed
 * (2026-10-08). This is deliberately a hand-written list and NOT a second read
 * of `desktop-help.js`: a test that asks the module what it holds can only
 * prove the module agrees with itself, and the whole acceptance question here
 * is whether the questions the owner used to have are still there. Changing a
 * question means changing this list, in the same commit, on purpose.
 */
const QUESTIONS = [
  "Does anything I say to Jarvis leave this computer?",
  "Where do I approve or deny what Jarvis wants to do?",
  "What is Jarvis Live, and how do I end it?",
  "Why is there no \"approve everything\" button?",
  "My Alt+Space shortcut does not do anything.",
  "What can I say?",
  "Can my phone talk to Jarvis?",
  "How does talking to Jarvis work?",
  "Jarvis suddenly got slow. What happened?",
  "What is the difference between Quiet and Standby?",
  "Will Jarvis update itself without asking?",
  "I closed the window, but Jarvis is still running. Is that a bug?",
  "Is my pairing token safe?",
  "How do I update Jarvis?",
  "I lost my phone. What do I do?",
];

/** The fifteen answers' own ids, in the card's order - the module's own keys,
 *  which the backend and the drawer never see, so they are listed here only so
 *  a rename is a visible decision rather than a silent one. */
const IDS = [
  "leaves-this-computer", "approve-or-deny", "jarvis-live", "no-approve-everything",
  "alt-space", "what-can-i-say", "phone-talks", "talking-to-jarvis", "suddenly-slow",
  "quiet-and-standby", "updates-itself", "window-still-running", "pairing-token",
  "how-to-update", "lost-phone",
];

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const squash = (t) => String(t).replace(/\s+/g, " ").trim();
/** One rendered question's answer, as the page holds it. */
const answerOf = (page, question) =>
  page.locator(".tutorial-question", { hasText: question }).locator("p").first().textContent();

const { base, close } = await K.serve();
const browser = await K.launch();
const VIEW = { width: 1180, height: 900 };

/* ── 1. The data: nothing was lost, and nothing is empty ─────────────────── */

await check("the desktop's own questions are exactly the fifteen the card held", async () => {
  assert.deepEqual(DESKTOP_FAQ.map((q) => q.q), QUESTIONS,
    "desktop-help.js does not hold the old card's fifteen questions, in its order");
  assert.deepEqual(DESKTOP_FAQ.map((q) => q.id), IDS,
    "the questions' own ids changed - say so in this list, in the same commit");
});

await check("every one carries a real answer, and none is a bare question", async () => {
  for (const { q, a } of DESKTOP_FAQ) {
    assert.ok(q.length > 8, `a question was too short: "${q}"`);
    assert.ok(String(a).trim().length > 40, `an answer is too short for "${q}": "${a}"`);
    assert.notEqual(squash(a), squash(q), `"${q}" answers itself`);
  }
});

await check("the local half merges AFTER the backend's, so the page leads with the shared answers", async () => {
  const backend = { questions: [{ q: "Shared one", a: "From the PC" }] };
  const merged = mergeQuestions(backend);
  assert.equal(merged.length, backend.questions.length + DESKTOP_FAQ.length);
  assert.equal(merged[0].q, "Shared one", "the PC's own answers no longer come first");
  assert.deepEqual(merged.slice(1).map((q) => q.q), QUESTIONS);
  // A backend that is down, or one older than /api/faq, still leaves the
  // desktop's own fifteen - the half only this app can answer.
  assert.deepEqual(mergeQuestions(null).map((q) => q.q), QUESTIONS);
  assert.deepEqual(mergeQuestions(undefined).map((q) => q.q), QUESTIONS);
});

await check("the two halves are labelled, so the page does not pretend to be one list", async () => {
  assert.ok(HELP_WORDS.heading.length > 4, "the desktop half has no heading");
  assert.match(HELP_WORDS.note, /this computer/i,
    "the note does not say whose questions these are");
});

/* ── 2. The second way in is gone, and nothing dangles ───────────────────── */

await check("settings.html no longer has the Help and FAQ card at all", async () => {
  const html = src("src/settings.html");
  assert.doesNotMatch(html, /<section[^>]*id="faq"/, "the FAQ card is still a card on Settings");
  assert.doesNotMatch(html, /class="faq-item"/, "an FAQ item is still on Settings");
  assert.doesNotMatch(html, /href="#faq"/, "the jump list still links to the removed card");
  assert.doesNotMatch(html, /id="open-features"/, "the feature-list button is still in Settings");
  assert.doesNotMatch(html, /id="faq-update-(?:off|on)"/, "the card's own dynamic spans are still here");
});

await check("settings.js carries none of the removed card's wiring", async () => {
  const js = src("src/settings.js");
  for (const gone of ["faqUpdateOff", "faqUpdateOn", "faq-update-off", "faq-update-on",
                      '"open-features"', '"features-status"']) {
    assert.ok(!js.includes(gone), `settings.js still wires ${gone}, which no longer exists`);
  }
  assert.doesNotMatch(js, /invoke\("open_features"\)/,
    "the settings window still asks to open the feature list, which it no longer draws a button for");
});

/* ── 3. The page: the same questions, in the new place ───────────────────── */

/** The one shared question the harness stands in for the PC's answer with, so
 *  the page really has two halves (the backend's own twenty are held to the
 *  backend by tests/tutorials.mjs; what is under test here is the split). */
const SHARED_Q = "Does Jarvis send my things anywhere?";

/** The Brain, on the Tutorials and the FAQ tab. */
async function brainHelp() {
  const page = await K.open(browser, base, "brain.html", {
    pending: [],
    faq: { ok: true, count: 1,
           questions: [{ q: SHARED_Q, a: "Answered by the PC.", where: "" }] },
  }, VIEW);
  await page.locator("#tab-tutorials").click();
  await K.until(page, "the FAQ to draw", async () =>
    (await page.locator(".tutorial-question").count()) >= QUESTIONS.length + 1);
  return page;
}

await check("the Brain's Help tab draws every one of the fifteen", async () => {
  const page = await brainHelp();
  const drawn = await page.locator(".tutorial-question summary").allTextContents();
  const answers = await page.locator(".tutorial-question p").allTextContents();
  await page.close();
  for (const q of QUESTIONS) {
    assert.ok(drawn.includes(q), `the new place does not ask "${q}"`);
  }
  assert.ok(answers.filter((a) => a.trim().length > 40).length >= QUESTIONS.length,
    `only ${answers.filter((a) => a.trim().length > 40).length} of the fifteen have a real answer`);
});

await check("the desktop half is marked, and the questions start closed", async () => {
  const page = await brainHelp();
  const drawn = await page.evaluate(() => {
    const kids = [...document.querySelectorAll(".tutorial-answers > *")];
    return {
      sharedFirst: kids[0]?.textContent?.trim() || "",
      markAt: kids.findIndex((n) => n.classList.contains("tutorial-faq-local")),
      localAt: kids.findIndex((n) => n.classList.contains("tutorial-question")
        && n.textContent.includes("Does anything I say to Jarvis leave this computer?")),
      heading: (document.querySelector(".tutorial-faq-local h4") || {}).textContent || "",
      open: [...document.querySelectorAll(".tutorial-question")].map((n) => n.open),
    };
  });
  await page.close();
  assert.ok(squash(drawn.sharedFirst).startsWith(SHARED_Q),
    `the PC's own answer no longer comes first: "${drawn.sharedFirst}"`);
  assert.ok(drawn.markAt > 0, "the desktop half has no heading between the two halves");
  assert.ok(drawn.localAt > drawn.markAt,
    "the desktop's questions are not under their own heading");
  assert.equal(squash(drawn.heading), squash(HELP_WORDS.heading));
  assert.deepEqual(drawn.open, drawn.open.map(() => false), "an FAQ item started open");
});

await check("the search finds a word from a moved answer, and the question as well", async () => {
  const page = await brainHelp();
  await page.fill(".tutorial-search", "PowerToys");
  await K.until(page, "the search to filter to one answer", async () =>
    (await page.locator(".tutorial-question").count()) === 1);
  const only = await page.locator(".tutorial-question summary").textContent();
  await page.fill(".tutorial-search", "pairing token");
  const hits = await page.locator(".tutorial-question summary").allTextContents();
  await page.close();
  assert.equal(squash(only), "My Alt+Space shortcut does not do anything.");
  assert.ok(hits.includes("Is my pairing token safe?"), `the question itself did not match: ${hits}`);
});

await check("the fifteen are openable and closeable with a real click", async () => {
  const page = await brainHelp();
  const first = page.locator(".tutorial-question").first();
  assert.equal(await first.evaluate((el) => el.open), false);
  await first.locator("summary").click();
  assert.equal(await first.evaluate((el) => el.open), true, "the answer did not open");
  await first.locator("summary").click();
  assert.equal(await first.evaluate((el) => el.open), false, "the answer did not close");
  await page.close();
});

await check("no NEW page error while the Help tab renders", async () => {
  const page = await brainHelp();
  const errors = page.__errors.filter((e) => !/favicon/.test(e));
  await page.close();
  assert.deepEqual(errors, [], errors.join(" | "));
});

/* ── 4. "Everything Jarvis can do" moved with the FAQ ────────────────────── */

await check("the button is in the Help tab, and pressing it asks for the window", async () => {
  const page = await brainHelp();
  const label = squash(await page.locator("#open-features").textContent());
  await page.locator("#open-features").click();
  await page.waitForTimeout(150);
  const out = await page.evaluate(() => ({
    calls: window.__calls.filter((c) => c[0] === "open_features").length,
    status: document.getElementById("features-status").textContent,
  }));
  await page.close();
  assert.equal(label, "Everything Jarvis can do");
  assert.equal(out.calls, 1, "the button did not call open_features");
  assert.ok(out.status.trim().length > 0, "the button said nothing about what happened");
});

/* ── 5. Audit 3: what the help text says still has to be true ───────────── */

// F1: the token FAQ said "stored as plain text on disk" and "never shown
// again". It is in Windows Credential Manager, and Settings has a button that
// shows it for the phone - which is still exactly where the answer says.
await check("the token FAQ says Credential Manager and the Show button, not plain text or never shown", async () => {
  const page = await brainHelp();
  const answer = squash(await answerOf(page, "Is my pairing token safe?"));
  await page.close();
  const reveal = squash(src("src/settings.html").match(/id="reveal-token"[^>]*>([\s\S]*?)<\/button>/)[1]);
  assert.ok(reveal, "settings.html has no #reveal-token button any more");
  assert.doesNotMatch(answer, /plain text on disk/i);
  assert.doesNotMatch(answer, /never shown again/i);
  assert.match(answer, /Windows Credential Manager/);
  assert.ok(answer.includes(reveal), `the FAQ does not name the "${reveal}" button`);
  assert.match(answer, /no Copy button/);
});

// F3: one sentence for where a card is answered, on every desktop surface,
// and it names the phone. The FAQ's copy of it is a string in desktop-help.js
// now (it is drawn with textContent), so it is read from there and held to the
// same constant the other two surfaces use.
const WHERE = "in the Jarvis bar, on the widget, or on your phone's Home screen";
await check("every desktop surface says where to approve in the same words, phone included", async () => {
  assert.ok(src("src/jarvis-link.js").includes(`export const APPROVE_WHERE = "${WHERE}";`));
  const page = await brainHelp();
  const faq = squash(await answerOf(page, "Where do I approve"));
  await page.close();
  assert.ok(faq.includes(WHERE),
    `the answered-where sentence is not in the FAQ's answer any more: "${faq}"`);
  assert.equal(faq.split(WHERE).length - 1, 1, "the sentence is repeated in one answer");
  const onboarding = squash(src("src/onboarding.html").match(/<span class="approve-where">([\s\S]*?)<\/span>/)[1]);
  assert.equal(onboarding, WHERE);
  // The two wake-word sentences in Rust, where the constant cannot reach.
  const voice = src("src-tauri/src/voice.rs").replace(/\\\n\s*/g, "");
  assert.equal(voice.split(`approve the card ${WHERE}`).length - 1
             + voice.split(`Approve the card ${WHERE}`).length - 1, 2, "voice.rs lost the words");
  // And none of the old, partial versions are left anywhere on the desktop.
  // desktop-help.js is in this list now: it is where the FAQ's copy lives.
  for (const file of ["src/brain.js", "src/desktop-help.js", "src/settings.js", "src/wiki.js",
                      "src/settings.html", "src/brain.html", "src/onboarding.html",
                      "src-tauri/src/voice.rs"]) {
    const text = squash(src(file));
    assert.doesNotMatch(text, /in the Jarvis bar and on the widget/, file);
    assert.doesNotMatch(text, /You approve it in the Jarvis bar\./, file);
    assert.doesNotMatch(text, /in the Jarvis bar \(<kbd>Alt<\/kbd>\+<kbd>Space<\/kbd> opens it\) and on the widget/, file);
  }
});

// F6: the hotkey's handler files to Logseq only when the PC is set up for
// it, and otherwise to the first note app it is set up for.
await check("the quick-note hotkey is called Quick note, not Quick note to Logseq", async () => {
  const hotkeys = src("src-tauri/src/hotkeys.rs");
  assert.match(hotkeys, /id: "quick_note",[\s\S]*?label: "Quick note",/);
  assert.doesNotMatch(hotkeys, /Quick note to Logseq/);
  assert.match(src("src/main.js"), /const target = ready\.includes\(asked\) \|\| !ready\.length \? asked : ready\[0\];/,
    "the handler no longer picks the first set-up note app - the label may be wrong again");
});

// F8: Models is inside the Brain's Model tab (called Faculties until the
// ease-of-use audit's wording pass, 2026-09-27), and the answer that sends the
// owner there must still be drawn in the Help place.
await check("the slow-model FAQ points at Brain window → Model → Models, which exists", async () => {
  const page = await brainHelp();
  const answer = squash(await answerOf(page, "Jarvis suddenly got slow"));
  await page.close();
  assert.match(answer, /Brain window, then Model, then Models/);
  const brain = src("src/brain.html");
  assert.match(brain, /id="tab-faculties"[\s\S]*?<span class="rail-label">Model<\/span>/);
  const faculties = brain.slice(brain.indexOf('id="view-faculties"'));
  assert.ok(faculties.indexOf('id="models"') > -1 &&
    faculties.indexOf('id="models"') < faculties.indexOf("</section>"), "Models is not in the Model tab");
});

// The tag the whole move exists for: Help is one place, and the never-hideable
// palette row lands on it rather than on a Settings card that is gone. Held to
// the app's own catalogue and the palette's own `entryPlace`, never to a second
// reading of menu-catalog.js's JSON text.
await check("Help is the Brain's own place, and the palette's Help row names it", async () => {
  const { MENUS } = await import("../src/menu-visibility.js");
  const { entryPlace, placeFor } = await import("../src/palette.js");
  const help = MENUS.find((m) => m.id === "entry.help");
  assert.ok(help, "entry.help is not in the catalogue at all");
  const place = placeFor({ kind: help.kind, id: help.id, title: help.title, place: entryPlace(help) });
  assert.equal(place.window, "brain", `Help opens the ${place.window} window, not the Brain`);
  assert.equal(place.tab, "tutorials", `Help opens the "${place.tab}" view, not the Help tab`);
  assert.ok(!MENUS.some((m) => m.id === "settings.faq"),
    "the removed Settings card is still in the catalogue");
  const brain = src("src/brain.js");
  assert.match(brain, /TUTORIALS_PLACE/, "brain.js no longer names the Help place");
  assert.match(brain, /await showView\(place\)/, "the Brain no longer opens a place that is a view");
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nthe one Help place holds every answer");
process.exit(fails.length ? 1 : 0);
