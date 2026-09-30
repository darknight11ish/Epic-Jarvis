/**
 * Review decks and typed Spanish practice on the Brain's Work tab (the owner's
 * decision of 2026-09-30; docs/QUIZ-DECKS-DESIGN.md, "Slice contract (frozen)";
 * JARVIS-API.md section 102; src/decks.js, src/quiz.js, brain.js "My study
 * decks" and the Keep sheet, src-tauri/src/brain/decks.rs and quiz.rs).
 *
 * The first half needs no browser and runs anywhere (CI's backend job too):
 * - the shared words, word for word, against tests/fixtures/decks-cases.json (written by tools/gen_decks_cases.py, which
 *   the phone's DecksTest.kt and QuizTest.kt read as well);
 * - no streak, point, heart or lateness word in any string of the new screens
 *   (the contract's banned list, whole words, any case) - with a control that
 *   proves the scan does see one;
 * - the reading of what the PC sends, the Keep sheet's choices (ticks, the
 *   prefill only for a Got it, only `n` and `answer` sent), the review states,
 *   the Spanish helpers (accent insertion, the guess-label rule, the level line);
 * - CONTROL: the Rust/JS/permissions wiring agrees, on the Brain window only.
 *
 * The second half needs Playwright (see tests/README.md) and is unexecuted where
 * it is unavailable: the section and its buttons, delete asks first, review
 * (reveal before rating, the four buttons, the empty / enough / paused
 * screens), the Keep sheet end to end, the Spanish quiz page, hidden lists,
 * a stale link, focus staying put, and nothing stored.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const FIX = JSON.parse(readFileSync(join(HERE, "fixtures", "decks-cases.json"), "utf8"));
const W = FIX.words;

const D = await import("../src/decks.js");
const Q = await import("../src/quiz.js");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** The contract's banned words, whole words, any case. */
const banned = (str) => FIX.banned.filter((w) =>
  new RegExp(`(^|[^A-Za-z0-9])${w.replace(/ /g, "\\s+")}($|[^A-Za-z0-9])`, "i").test(str));

/** Every quoted string of a source, comments removed (a scan of what the owner reads). */
function literals(src) {
  const bare = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'\\])\/\/[^\n]*/g, "$1");
  const out = [];
  for (const m of bare.matchAll(/"((?:[^"\\\n]|\\.)*)"|'((?:[^'\\\n]|\\.)*)'|`((?:[^`\\]|\\.)*)`/g)) {
    out.push(m[1] ?? m[2] ?? m[3]);
  }
  return out;
}

/* ── The shared words ─────────────────────────────────────────────────── */

await check("the shared words are word for word what the contract says", async () => {
  const eq = (a, b, what) => assert.equal(a, b, what);
  eq(D.SECTION_TITLE, W.section_title);
  eq(Q.MODES[0].label, W.mode_text);
  eq(Q.MODES[1].label, W.mode_spanish);
  eq(Q.LEVEL_HEADING, W.level_heading);
  eq(Q.levelLine("B1"), W.level_label_b1);
  eq(Q.EXERCISES.map((e) => e.label).join("|"),
    [W.exercise_translate, W.exercise_blank, W.exercise_complete, W.exercise_mixed].join("|"));
  eq(Q.TOPIC_LABEL, W.topic_label);
  eq(Q.topicCount("").note, W.topic_counter);
  eq(Q.SPANISH_TEXT_PLACEHOLDER, W.spanish_placeholder);
  eq(Q.START_LABEL, W.start_button);
  eq(Q.KIND_LABELS.translate, W.kind_translate);
  eq(Q.KIND_LABELS.blank, W.kind_blank);
  eq(Q.KIND_LABELS.complete, W.kind_complete);
  eq(Q.markLines({ expected: "está" }, {}).answerLine, W.answer_line_example);
  eq(Q.SOURCE_LABEL, W.passage_from_text);
  eq(Q.EXAMPLE_HEADING, W.passage_example);
  eq(Q.GUESS_LABEL, W.guess_label);
  eq(D.KEEP_BUTTON, W.keep_button);
  eq(D.KEEP_FINISH, W.keep_finish);
  eq(D.KEEP_CANCEL, W.keep_cancel);
  eq(D.KEEP_BACK_PLACEHOLDER, W.keep_back_placeholder);
  eq(D.keptLine(3), W.kept_many);
  eq(D.keptLine(1), W.kept_one);
  eq(D.NEW_DECK, W.new_deck);
  eq(D.DECK_NAME, W.deck_name);
  eq(D.CHOOSE_DECK, W.choose_deck);
  eq(D.KEEP_HIDDEN, W.keep_hidden);
  eq(D.CARDS_READY_HEADING, W.cards_ready);
  eq(D.NOTHING_READY, W.nothing_ready);
  eq(D.NEW_PER_DAY_LABEL, W.new_per_day);
  eq(D.REVIEW, W.review);
  eq(D.PAUSE, W.pause);
  eq(D.RESUME, W.resume);
  eq(D.DELETE_DECK, W.delete_deck);
  eq(D.DELETE_CARD, W.delete_card);
  eq(D.EDIT, W.edit);
  eq(D.SAVE, W.save);
  eq(D.CARDS_LINK, W.cards_link);
  eq(D.cardsLabel(8), W.cards_many);
  eq(D.cardsLabel(1), W.cards_one);
  eq(D.readyLabel(3), W.ready_row);
  eq(D.DELETE_CONFIRM, W.delete_confirm);
  eq(D.DELETE, W.delete);
  eq(D.EMPTY_STATE, W.empty_state);
  eq(D.REVIEW_HIDDEN, W.review_hidden);
  eq(D.SHOW_ANSWER, W.show_answer);
  eq(D.TYPED_PLACEHOLDER, W.typed_placeholder);
  eq(D.RATINGS.map((r) => r.id).join(","), FIX.ratings.join(","));
  eq(D.RATINGS[0].label, W.rating_again);
  eq(D.RATINGS[1].label, W.rating_hard);
  eq(D.RATINGS[2].label, W.rating_good);
  eq(D.RATINGS[3].label, W.rating_easy);
  eq(D.ENOUGH, W.enough);
  eq(D.MORE, W.more);
  eq(D.STOP, W.stop);
  eq(D.BACK_HEADING, W.back_answer);
  eq(D.FROM_TEXT, W.passage_from_text);
  eq(D.EXAMPLE_SENTENCE, W.passage_example);
  eq(D.REVIEW_ALL, W.review_all);
  eq(D.PER_DECK_NOTE, W.per_deck_note);
  eq(Q.QUIZ_INTRO, W.quiz_intro);
  eq(Q.SPANISH_INTRO, W.spanish_intro);
  eq(Q.ERROR_WORDS.model_unavailable, W.model_unavailable);
  eq(Q.ACCENT_ROW_LABEL, W.accent_row_label);
  assert.deepEqual([...Q.ACCENTS], FIX.accents);
  assert.deepEqual([...Q.LEVEL_IDS], ["A1", "A2", "B1", "B2", "C1", "C2"]);
});

await check("the small rules give the worked examples' answers (the phone runs the same ones)", async () => {
  const E = FIX.examples;
  for (const [day, want] of E.format_day) assert.equal(D.formatDay(day), want, String(day));
  for (const [day, want] of E.next_ready_line) assert.equal(D.nextReadyLine(day), want, String(day));
  for (const [n, want] of E.cards_label) assert.equal(D.cardsLabel(n), want);
  for (const [n, want] of E.kept_line) assert.equal(D.keptLine(n), want);
  for (const [deck, available, hidden, want] of E.can_review) {
    assert.equal(D.canReview({ available, hidden }, deck), want, JSON.stringify([deck, available, hidden]));
  }
  for (const [ready, available, hidden, want] of E.can_review_all) {
    assert.equal(D.canReviewAll({ available, hidden, ready }), want, JSON.stringify([ready, available, hidden]));
  }
  for (const [each, total, want] of E.per_deck_note) {
    assert.equal(D.perDeckNoteShown({ ready: total, decks: each.map((ready) => ({ ready })) }), want,
      JSON.stringify([each, total]));
  }
  // The wording the PC sends is in the file for the tests only: the apps never copy it.
  assert.equal(FIX.pc_words.key_label_model, W.key_label_model);
});

await check("the sentence about a key written by the model comes from the PC, not from a copy here", async () => {
  // The label and the notice are the PC's words: nothing in either app's source
  // spells them out (the fixture holds the PC's wording for the tests only).
  for (const f of ["src/decks.js", "src/quiz.js"]) {
    const lit = literals(read(f));
    assert.ok(!lit.some((s) => s.includes(W.key_label_model)), `${f} copies the key label`);
    assert.ok(!lit.some((s) => /cannot recognise a crisis message/i.test(s)), `${f} copies the notice`);
  }
  const marks = Q.readMark({ level: "partly", key_label: W.key_label_model, marked_by: "code", expected: "x" });
  assert.equal(Q.markLines(marks, { keySource: "model" }).keyLabel, W.key_label_model);
});

/* ── No lateness, points or streaks ───────────────────────────────────── */

await check("no banned word in any string of the decks, review, Keep and Spanish screens", async () => {
  const html = read("src/brain.html");
  const chooser = html.slice(html.indexOf('<div class="quiz-mode"'), html.indexOf('<textarea id="quiz-text"'));
  const decksCard = html.slice(html.indexOf('id="decks-card"'), html.indexOf('id="briefing-card"'));
  assert.ok(chooser.length > 200 && decksCard.length > 50, "the HTML pieces were not found");
  const js = read("src/brain.js");
  const region = js.slice(js.indexOf("const qz = { quiz: null"), js.indexOf("function rereadDecks"));
  assert.ok(region.length > 5000, "the brain.js region was not found");
  const quizJs = read("src/quiz.js");
  const spanish = quizJs.slice(quizJs.indexOf("Spanish practice (docs/QUIZ-DECKS-DESIGN.md"),
    quizJs.indexOf("export function levelLabel"));
  assert.ok(spanish.length > 1000, "quiz.js's Spanish block was not found");
  const strings = [
    ...literals(read("src/decks.js")),
    ...literals(spanish),
    ...literals(region),
    ...chooser.replace(/<[^>]+>/g, "\n").split("\n"),
    ...(chooser.match(/(?:aria-label|placeholder|title)="[^"]*"/g) || []),
    ...decksCard.replace(/<[^>]+>/g, "\n").split("\n"),
    ...Object.values(W),
  ].filter((s) => s.trim());
  assert.ok(strings.length > 150, `only ${strings.length} strings were scanned`);
  const hits = strings.map((s) => [s, banned(s)]).filter(([, b]) => b.length);
  assert.deepEqual(hits, []);
});

await check("CONTROL: the scan does see a banned word, whole and in any case", async () => {
  assert.deepEqual(banned("Your streak is safe"), ["streak"]);
  assert.deepEqual(banned("You are BEHIND today"), ["behind"]);
  assert.deepEqual(banned("Cards you missed"), ["missed"]);
  assert.deepEqual(banned("Overdue!"), ["overdue"]);
  assert.deepEqual(banned("3 in a row"), ["in a row"]);
  assert.deepEqual(banned("Keep it up"), ["keep it up"]);
  assert.deepEqual(banned("Earn XP"), ["XP"]);
  assert.deepEqual(banned("Three hearts left"), ["hearts"]);
  assert.deepEqual(banned("Your progress is lost"), ["lost"]);
  assert.deepEqual(banned("Top of the leaderboard, in the league"), ["leaderboard", "league"]);
  // Whole words only.
  assert.deepEqual(banned("An expert is not an XP-free zone? Lostock, hearth, behinds"), ["XP"]);
  assert.deepEqual(banned("Nothing ready today. Next cards ready on 3 Oct 2026"), []);
});

/* ── Reading what the PC sends ────────────────────────────────────────── */

await check("the deck list is read with its counts and line; unavailable keeps its why word for word", async () => {
  const v = D.readDecks(FIX.samples.decks);
  assert.equal(v.available, true);
  assert.equal(v.decks.length, 2);
  assert.deepEqual(v.decks[0], { id: "d1a2b3c4d5e6", name: "Plants", cards: 8, ready: 3, paused: false, kind: "study" });
  assert.equal(v.decks[1].paused, true);
  assert.equal(v.line, "3 cards ready");
  assert.equal(v.newPerDay, 5);
  assert.equal(v.nextReadyDay, "2026-10-03");
  assert.equal(v.limits.name, 60);
  const off = D.readDecks(FIX.samples.decks_unavailable);
  assert.equal(off.available, false);
  assert.equal(off.decks.length, 0);
  assert.equal(off.why, FIX.samples.decks_unavailable.why);
  assert.equal(off.line, "2 cards ready");
  assert.equal(D.readDecks({ ok: true }), null);
  assert.equal(D.readDecks(null), null);
});

await check("a day is shown as the PC gave it, only formatted", async () => {
  assert.equal(D.formatDay("2026-10-03"), "3 Oct 2026");
  assert.equal(D.nextReadyLine("2026-10-03"), "Next cards ready on 3 Oct 2026");
  assert.equal(D.nextReadyLine(null), "");
  assert.equal(D.formatDay("nonsense"), "nonsense");
  assert.equal(D.formatDay("2026-13-40"), "2026-13-40");
});

await check("a review is read for a card, a rate (its `next`) and the other states", async () => {
  const r = D.readReview(FIX.samples.review_card);
  assert.equal(r.state, "card");
  assert.equal(r.card.front, "What absorbs sunlight?");
  assert.equal(r.card.deck, "d1a2b3c4d5e6");
  assert.deepEqual(r.run, { done: 0, limit: 20 });
  const rate = D.readReview(FIX.samples.rate);
  assert.equal(rate.card.front, "Second card");
  assert.equal(rate.comesBack, "2026-10-03");
  for (const state of ["empty", "enough", "paused", "no_decks"]) {
    assert.equal(D.readReview({ ok: true, state, ready: 0, line: "x", card: null, run: {} }).state, state);
  }
  assert.equal(D.readReview({ ok: true, state: "surprise" }), null);
  const back = D.readReveal(FIX.samples.reveal);
  assert.equal(back.answer, "Chlorophyll");
  assert.equal(back.keyLabel, null);
  assert.equal(D.readReveal({ ok: true, back: { answer: "x", passage: "" }, key_label: W.key_label_model }).keyLabel, W.key_label_model);
  assert.equal(D.readReveal({ ok: true }), null);
  assert.equal(D.isHiddenReview({ ok: true, hidden: true, message: W.review_hidden }), true);
  assert.equal(D.isHiddenReview(FIX.samples.review_card), false);
});

await check("what each review state shows", async () => {
  const s = (state, line = "") => D.reviewScreen({ state, line }, "2026-10-03");
  assert.equal(s("card").kind, "card");
  assert.equal(s("empty").title, W.nothing_ready);
  assert.equal(s("empty").note, "Next cards ready on 3 Oct 2026");
  assert.equal(D.reviewScreen({ state: "empty", line: "" }, null).note, "");
  assert.equal(s("enough").title, W.enough);
  assert.deepEqual(s("enough").actions, ["more", "stop"]);
  assert.equal(s("paused", "All decks paused").title, "All decks paused");
  assert.equal(s("paused", "This deck is paused").title, "This deck is paused");
  assert.equal(s("no_decks").kind, "leave");
  assert.equal(D.backPassageHeading({ keyLabel: null }), W.passage_from_text);
  assert.equal(D.backPassageHeading({ keyLabel: W.key_label_model }), W.passage_example);
});

await check("the section's top: the PC's line, or the empty state when there is no deck at all", async () => {
  const some = D.readDecks(FIX.samples.decks);
  assert.deepEqual(D.sectionTop(some), { line: "3 cards ready", empty: false });
  const none = D.readDecks({ ...FIX.samples.decks, decks: [], line: "", ready: 0 });
  assert.equal(D.sectionTop(none).empty, true);
  const off = D.readDecks(FIX.samples.decks_unavailable);
  assert.equal(D.sectionTop(off).empty, false, "an unavailable list is not an empty one");
  assert.equal(D.canReview(some, some.decks[0]), true);
  assert.equal(D.canReview({ ...some, hidden: true }, some.decks[0]), false);
  assert.equal(D.canReview(off, some.decks[0]), false);
  assert.equal(D.deckMeta(some.decks[0]), "8 cards · 3 ready");
});

/* ── The Keep sheet ───────────────────────────────────────────────────── */

const quizWith = (levels) => Q.readQuiz({
  id: "qz1", title: "Bread", grader_verified: false, answered: levels.filter(Boolean).length,
  questions: levels.map((level, i) => ({
    n: i + 1, kind: "recall", prompt: `Question ${i + 1}?`,
    mark: level ? { level, comment: "MODEL COMMENT", passage: `Passage ${i + 1}` } : null })),
});

await check("every answered question is a row; ticked for Partly and Not yet, not for Got it", async () => {
  const q = quizWith(["got_it", "partly", "not_yet", null]);
  const rows = D.keepRows(q, new Map([[1, "my words"], [2, "typed two"], [3, "typed three"]]));
  assert.deepEqual(rows.map((r) => r.n), [1, 2, 3], "an unanswered question is not offered");
  assert.deepEqual(rows.map((r) => r.tick), [false, true, true]);
  assert.equal(D.defaultTick("got_it"), false);
});

await check("the back is the owner's own words only for a Got it; the model's comment is never a back", async () => {
  const q = quizWith(["got_it", "partly", "not_yet"]);
  const rows = D.keepRows(q, new Map([[1, "my words"], [2, "typed two"], [3, "typed three"]]));
  assert.equal(rows[0].back, "my words");
  assert.equal(rows[1].back, "");
  assert.equal(rows[2].back, "");
  assert.ok(!JSON.stringify(rows).includes("MODEL COMMENT"));
  // An answer the app no longer holds (or never held: a crisis answer) is empty.
  assert.equal(D.keepRows(q, new Map())[0].back, "");
  assert.equal(D.keepRows(q, null)[0].back, "");
  assert.equal(rows[0].passage, "Passage 1");
});

await check("Keep sends only the number and the back of each ticked card", async () => {
  const rows = [
    { n: 1, prompt: "P1", passage: "SRC1", tick: false, back: "ignored" },
    { n: 2, prompt: "P2", passage: "SRC2", tick: true, back: "dos" },
    { n: 3, prompt: "P3", passage: "SRC3", tick: true, back: "" },
  ];
  const { keep } = D.keepPayload(rows, "d1a2b3c4d5e6", "");
  assert.deepEqual(keep, { deck: "d1a2b3c4d5e6", cards: [{ n: 2, answer: "dos" }, { n: 3, answer: "" }] });
  const s = JSON.stringify(keep);
  assert.ok(!/P2|SRC|prompt|passage|front/.test(s), "no question words go out");
  const fresh = D.keepPayload(rows, "", "  Plantas ").keep;
  assert.equal(fresh.deck, null);
  assert.equal(fresh.new_deck, "Plantas");
});

await check("Keep refuses in plain words: nothing ticked, no name, a name over 60, a back over 2,000", async () => {
  const none = [{ n: 1, tick: false, back: "" }];
  assert.match(D.keepPayload(none, "d1", "").error, /Tick at least one/);
  const one = [{ n: 1, tick: true, back: "" }];
  const noName = D.keepPayload(one, "", "   ");
  assert.match(noName.error, /1 to 60/);
  assert.equal(noName.nameProblem, true);
  assert.match(D.keepPayload(one, "", "x".repeat(61)).error, /1 to 60/);
  assert.ok(D.keepPayload(one, "", "ñ".repeat(60)).keep, "60 characters is fine");
  assert.match(D.keepPayload([{ n: 1, tick: true, back: "x".repeat(2001) }], "d1", "").error, /2,000/);
  assert.equal(D.backCount("12345").note, "5 / 2000 characters");
});

await check("a new deck is named after the quiz, cut to 60 characters", async () => {
  assert.equal(D.defaultDeckName("  Bread  "), "Bread");
  assert.equal(D.defaultDeckName("x".repeat(80)).length, 60);
  assert.equal(D.defaultDeckName(""), "");
  assert.equal(D.deckNameOk(""), false);
  assert.equal(D.deckNameOk(" a "), true);
});

await check("a refusal shows the PC's own message word for word", async () => {
  assert.equal(D.refusalWords({ ok: false, error: "duplicate_card", message: "Question 2 is already in that deck." }),
    "Question 2 is already in that deck.");
  assert.equal(D.refusalWords({ ok: false, error: "x" }), "Jarvis could not do that.");
  assert.equal(D.isRefusal({ ok: false }), true);
  assert.equal(D.isRefusal({ ok: true }), false);
});

/* ── Spanish practice: the quiz side ──────────────────────────────────── */

await check("a Spanish quiz is read with its level, key source and the PC's notice; an older PC has no mode", async () => {
  const q = Q.readQuiz(FIX.samples.spanish_quiz.quiz);
  assert.equal(q.mode, "spanish");
  assert.equal(q.level, "B1");
  assert.equal(q.keySource, "model");
  assert.equal(q.notice, FIX.samples.spanish_quiz.quiz.notice);
  assert.equal(q.questions[0].kind, "blank");
  assert.equal(q.questions[1].kind, "translate");
  const old = Q.readQuiz({ id: "q", title: "t", grader_verified: false, answered: 0, questions: [] });
  assert.equal(old.mode, "", "no mode means an older PC");
  assert.equal(old.level, null);
  assert.equal(old.notice, "");
  assert.equal(Q.readQuiz({ id: "q", mode: "klingon", questions: [] }).mode, "");
});

await check("a mark shows the key line, the label from the PC, and Jarvis's guess only for a model mark on an unverified quiz", async () => {
  const q = Q.readQuiz(FIX.samples.spanish_quiz.quiz);
  const code = q.questions[0].mark;
  assert.equal(code.markedBy, "code");
  const a = Q.markLines(code, q);
  assert.equal(a.answerLine, "Answer: está");
  assert.equal(a.keyLabel, W.key_label_model);
  assert.equal(a.passageHeading, W.passage_example);
  assert.equal(a.showGuess, false, "a code-marked mark never shows the guess");
  const model = Q.readMark({ level: "partly", comment: "c", passage: "p", marked_by: "model", expected: "hola", key_label: null });
  assert.equal(Q.markLines(model, q).showGuess, true);
  assert.equal(Q.markLines(model, { ...q, verified: true }).showGuess, false, "verified: no guess label");
  assert.equal(Q.markLines(model, { ...q, keySource: "text" }).passageHeading, W.passage_from_text);
  assert.equal(Q.markLines(model, { ...q, keySource: null }).passageHeading, W.passage_from_text, "Text mode");
  assert.equal(Q.markLines(model, q).keyLabel, "");
  // Text mode marks from an older PC carry no marked_by: still the model's, as before.
  const text = Q.readMark({ level: "got_it", comment: "c", passage: "p" });
  assert.equal(text.markedBy, "model");
  assert.equal(Q.markLines(text, { verified: false }).showGuess, true);
  assert.equal(Q.markLines(text, { verified: false }).answerLine, "");
});

await check("an accent goes in at the cursor, over a selection, and never past 2,000 characters", async () => {
  assert.deepEqual(Q.insertAtCursor("mao", 2, 2, "ñ"), { value: "maño", caret: 3 });
  assert.deepEqual(Q.insertAtCursor("abc", 1, 2, "é"), { value: "aéc", caret: 2 });
  assert.deepEqual(Q.insertAtCursor("", 0, 0, "¿"), { value: "¿", caret: 1 });
  assert.deepEqual(Q.insertAtCursor("ab", null, null, "¡"), { value: "ab¡", caret: 3 });
  const full = "x".repeat(2000);
  assert.deepEqual(Q.insertAtCursor(full, 5, 5, "á"), { value: full, caret: 5 });
});

await check("the Spanish start sends only what was chosen, and refuses a bad text or topic before sending", async () => {
  assert.deepEqual(Q.spanishStartArgs({ text: "", level: "B2", exercise: "blank", topic: "" }).args,
    { mode: "spanish", level: "B2", exercise: "blank" });
  assert.deepEqual(Q.spanishStartArgs({ text: "  ", level: "zz", exercise: "zz", topic: " food " }).args,
    { mode: "spanish", level: "A2", exercise: "mixed", topic: "food" });
  const withText = Q.spanishStartArgs({ text: "Hola. ".repeat(50), level: "A1", exercise: "mixed", topic: "" });
  assert.ok(withText.args.text);
  assert.match(Q.spanishStartArgs({ text: "corto", level: "A1", exercise: "mixed", topic: "" }).error, /too short/);
  assert.match(Q.spanishStartArgs({ text: "", level: "A1", exercise: "mixed", topic: "x".repeat(61) }).error, /60/);
  assert.equal(Q.topicCount("ñandú").note, "5 / 60");
});

/* ── Wiring ───────────────────────────────────────────────────────────── */

await check("CONTROL: the commands are held on a stale link, redact, are registered, and only the Brain window holds them", async () => {
  const rs = read("src-tauri/src/brain/decks.rs");
  const code = rs.split("#[cfg(test)]")[0];
  const writes = ["brain_decks_create", "brain_decks_settings", "brain_decks_act", "brain_decks_card_act",
    "brain_review_reveal", "brain_review_rate", "brain_review_more"];
  for (const cmd of writes) {
    const f = code.slice(code.indexOf(`pub async fn ${cmd}(`));
    const body = f.slice(0, f.indexOf("\n}\n"));
    assert.ok(body.includes("require_link_live(&app)?"), `${cmd} is not held on a stale link`);
    assert.ok(body.indexOf("require_link_live") < body.indexOf("post("), `${cmd} posts before the link check`);
  }
  for (const cmd of ["brain_decks", "brain_decks_cards", "brain_review"]) {
    const f = code.slice(code.indexOf(`pub async fn ${cmd}(`));
    const body = f.slice(0, f.indexOf("\n}\n"));
    assert.ok(!body.includes("require_link_live"), `${cmd} is a read and must not be held`);
  }
  assert.match(code, /crate::lock::private_hidden/);
  // Reviewing is not asked of the PC at all while the lists are hidden.
  for (const cmd of ["brain_review", "brain_review_reveal", "brain_review_rate", "brain_review_more"]) {
    const f = code.slice(code.indexOf(`pub async fn ${cmd}(`));
    const body = f.slice(0, f.indexOf("\n}\n"));
    assert.ok(body.includes("review_hidden_answer"), `${cmd} does not stop while hidden`);
  }
  // Nothing is logged: the words and the token never reach a log line.
  assert.doesNotMatch(code, /println!|eprintln!|tracing::|log::|dbg!/);
  // Literal route strings, so tools/check_parity.py sees every call.
  for (const route of ['"/api/decks"', '"/api/decks/settings"', "/api/decks/{id}/act", "/api/decks/{id}/cards\"",
    "/api/decks/{id}/cards/{cid}/act", '"/api/review"', '"/api/review/reveal"', '"/api/review/rate"', '"/api/review/more"']) {
    assert.ok(code.includes(route), `decks.rs does not spell out ${route}`);
  }
  const all = ["brain_decks", "brain_decks_create", "brain_decks_settings", "brain_decks_act", "brain_decks_cards",
    "brain_decks_card_act", "brain_review", "brain_review_reveal", "brain_review_rate", "brain_review_more"];
  const buildRs = read("src-tauri/build.rs");
  const libRs = read("src-tauri/src/lib.rs");
  const sets = read("src-tauri/permissions/surfaces.toml").split("[[set]]").slice(1);
  for (const cmd of all) {
    assert.match(buildRs, new RegExp(`"${cmd}"`), `${cmd} is not in build.rs`);
    assert.match(libRs, new RegExp(`brain::decks::${cmd},`), `${cmd} is not registered`);
    const holders = sets.filter((s) => s.includes(`"allow-${cmd.replace(/_/g, "-")}"`))
      .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
    assert.deepEqual(holders, ["brain-decks"], cmd);
    assert.ok(read(`src-tauri/permissions/autogenerated/${cmd}.toml`).includes(`commands.allow = ["${cmd}"]`), `${cmd}: no generated permission`);
  }
  assert.match(read("src-tauri/src/brain.rs"), /pub mod decks;/);
  const caps = JSON.parse(read("src-tauri/capabilities/brain.json")).permissions;
  assert.ok(caps.includes("brain-decks"));
  for (const other of ["quickbar", "widget", "hud", "settings", "faces", "floating", "onboarding"]) {
    assert.ok(!read(`src-tauri/capabilities/${other}.json`).includes("brain-decks"), `${other} holds brain-decks`);
  }
  // The quiz's start and finish grew the new fields, and the Keep body is rebuilt in Rust.
  const quizRs = read("src-tauri/src/brain/quiz.rs").split("#[cfg(test)]")[0];
  assert.match(quizRs, /mode: Option<String>/);
  assert.match(quizRs, /keep: Option<serde_json::Value>/);
  assert.match(quizRs, /fn keep_body/);
});

await check("nothing of a deck, a card or a typed answer is written to browser storage", async () => {
  const js = read("src/brain.js");
  const region = js.slice(js.indexOf("const qz = { quiz: null"), js.indexOf("function rereadDecks"));
  const bare = (t) => t.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'\\])\/\/[^\n]*/g, "$1");
  for (const src of [bare(read("src/decks.js")), bare(region), bare(read("src/quiz.js"))]) {
    assert.doesNotMatch(src, /localStorage|sessionStorage|indexedDB/i);
  }
});

/* ── The Brain window (needs Playwright) ──────────────────────────────── */

let K = null;
try {
  await import("playwright");
  K = await import("./uikit.mjs");
} catch {
  console.log("skip  the Brain window checks: Playwright is not installed (see tests/README.md)");
}

if (K) {
  const { base, close } = await K.serve();
  const browser = await K.launch();
  const SIZE = { width: 1180, height: 1000 };
  const PASTE = "Bread is made from flour, water, salt and yeast. ".repeat(6);

  const card = (id, front, back, extra = {}) => ({
    id, front, back, passage: `Passage for ${front}`, kind: "recall", level: null, due: true, new: true, ...extra });
  const PLANTS = () => ({
    id: "d1a2b3c4d5e6", name: "Plants", paused: false,
    cards: [card("c1a2b3c4d5e6", "What absorbs sunlight?", "Chlorophyll"),
            card("c2b3c4d5e6f7", "Where does it happen?", "In the leaves"),
            card("c3c4d5e6f7a8", "Which gas is taken in?", "Carbon dioxide", { due: false, new: false })],
  });
  const VERBOS = () => ({ id: "d2b3c4d5e6f7", name: "Verbos", paused: true, cards: [card("c9", "estar", "to be")] });
  const decksData = (over = {}) => ({ decks: { decks: [PLANTS(), VERBOS()], nextReadyDay: "2026-10-03", ...over } });

  async function workTab(data = {}) {
    const page = await K.open(browser, base, "brain.html", data, SIZE);
    await page.locator("#tab-work").click();
    await page.waitForTimeout(500);
    return page;
  }
  const dcalls = (page) => page.evaluate(() => window.__decks.calls);
  const qcalls = (page) => page.evaluate(() => window.__quiz.calls);
  const text = (page, sel) => page.locator(sel).innerText();
  const settle = (page, ms = 350) => page.waitForTimeout(ms);
  const fkey = (page, k) => page.locator(`#decks-card [data-fkey="${k}"]`);

  await check("the section shows its title, the PC's line, the deck rows and their buttons", async () => {
    const page = await workTab(decksData());
    const body = await text(page, "#decks-card");
    const title = (await page.locator("#decks-card h2").textContent()).trim();
    const heads = await page.locator("#decks-card h3").allInnerTexts();
    const perDay = await page.locator("#decks-per-day").inputValue();
    const first = await text(page, ".deck-row >> nth=0");
    const second = await text(page, ".deck-row >> nth=1");
    const btns1 = await page.locator(".deck-row >> nth=0").locator("button").allInnerTexts();
    const btns2 = await page.locator(".deck-row >> nth=1").locator("button").allInnerTexts();
    await page.close();
    assert.equal(title, W.section_title);
    assert.ok(heads.some((h) => h.toLowerCase() === W.cards_ready.toLowerCase()), `headings: ${heads}`);
    assert.match(body, /2 cards ready/);
    assert.equal(perDay, "5");
    assert.match(first, /Plants/);
    assert.match(first, /3 cards/);
    assert.match(first, /2 ready/);
    assert.match(second, /1 card\b/);
    assert.match(second, /Paused/i);
    assert.deepEqual(btns1, [W.review, W.pause, W.cards_link, W.edit, W.delete_deck]);
    assert.deepEqual(btns2, [W.review, W.resume, W.cards_link, W.edit, W.delete_deck]);
    assert.match(body, new RegExp(W.new_per_day));
    assert.match(body, new RegExp(W.new_deck));
    assert.equal(banned(body).length, 0, `banned words on the page: ${banned(body)}`);
  });

  await check("no decks at all: the empty state; a list that is unavailable shows the PC's why", async () => {
    const page = await workTab({ decks: { decks: [] } });
    const empty = await text(page, "#decks-card");
    await page.close();
    assert.match(empty, new RegExp(W.empty_state));
    assert.doesNotMatch(empty, /Nothing ready today/, "no line when there is no deck");
    const why = "Decks are not set up on this PC: the key does not open the file.";
    const off = await workTab({ decks: { decks: [], available: false, why } });
    const words = await text(off, "#decks-card");
    await off.close();
    assert.ok(words.includes(why));
    assert.doesNotMatch(words, new RegExp(W.empty_state), "unavailable is not empty");
    const none = await workTab({});
    const gone = await text(none, "#decks-card");
    await none.close();
    assert.match(gone, /does not have study decks yet/);
  });

  await check("New cards a day sends the number; a bad number is refused before anything is sent", async () => {
    const page = await workTab(decksData());
    await page.locator("#decks-per-day").fill("8");
    await page.locator("#decks-per-day").press("Enter");
    await settle(page);
    const sent = (await dcalls(page)).filter((c) => c.cmd === "brain_decks_settings");
    await page.locator("#decks-per-day").fill("99");
    await page.locator("#decks-per-day").press("Enter");
    await settle(page);
    const after = (await dcalls(page)).filter((c) => c.cmd === "brain_decks_settings");
    const words = await text(page, "#decks-card");
    await page.close();
    assert.deepEqual(sent.map((c) => c.newPerDay), [8]);
    assert.equal(after.length, 1, "99 was sent");
    assert.match(words, /whole number from 0 to 20/);
  });

  await check("Pause and Resume act, the row changes, and the keyboard stays on that button", async () => {
    const page = await workTab(decksData());
    await fkey(page, "pause:d1a2b3c4d5e6").focus();
    await page.keyboard.press("Enter");
    await settle(page, 500);
    const calls = (await dcalls(page)).filter((c) => c.cmd === "brain_decks_act");
    const row = await text(page, ".deck-row >> nth=0");
    const focused = await page.evaluate(() => document.activeElement && document.activeElement.dataset.fkey);
    await page.close();
    assert.deepEqual(calls.map((c) => [c.id, c.action]), [["d1a2b3c4d5e6", "pause"]]);
    assert.match(row, /Paused/i);
    assert.equal(focused, "pause:d1a2b3c4d5e6");
  });

  await check("Delete this deck asks first with the backup sentence; Cancel sends nothing; Delete deletes", async () => {
    const page = await workTab(decksData());
    await fkey(page, "delete:d1a2b3c4d5e6").click();
    await settle(page);
    const asked = await text(page, ".deck-row >> nth=0");
    const before = (await dcalls(page)).filter((c) => c.cmd === "brain_decks_act").length;
    await page.locator(".deck-confirm").getByRole("button", { name: W.keep_cancel }).click();
    await settle(page);
    const cancelled = (await dcalls(page)).filter((c) => c.cmd === "brain_decks_act").length;
    await fkey(page, "delete:d1a2b3c4d5e6").click();
    await page.locator(".deck-confirm").getByRole("button", { name: W.delete, exact: true }).click();
    await settle(page, 500);
    const calls = (await dcalls(page)).filter((c) => c.cmd === "brain_decks_act");
    const body = await text(page, "#decks-card");
    await page.close();
    assert.ok(asked.includes(W.delete_confirm));
    assert.equal(before, 0);
    assert.equal(cancelled, 0);
    assert.deepEqual(calls.map((c) => c.action), ["delete"]);
    assert.doesNotMatch(body, /Plants/);
  });

  await check("Cards lists a deck's cards; Edit saves the front and back; Delete this card asks first", async () => {
    const page = await workTab(decksData());
    await fkey(page, "cards:d1a2b3c4d5e6").click();
    await settle(page, 500);
    const list = await text(page, ".deck-cards");
    await fkey(page, "edit-card:c1a2b3c4d5e6").click();
    await settle(page);
    await page.locator('[data-fkey="front:c1a2b3c4d5e6"]').fill("New front");
    await page.locator('[data-fkey="back:c1a2b3c4d5e6"]').fill("New back");
    await fkey(page, "save:c1a2b3c4d5e6").click();
    await settle(page, 500);
    const edit = (await dcalls(page)).filter((c) => c.cmd === "brain_decks_card_act");
    const after = await text(page, ".deck-cards");
    await fkey(page, "delete-card:c2b3c4d5e6f7").click();
    await settle(page);
    const sure = await text(page, ".deck-cards");
    const beforeDelete = (await dcalls(page)).filter((c) => c.cmd === "brain_decks_card_act").length;
    await page.locator(".deck-confirm").getByRole("button", { name: W.delete, exact: true }).click();
    await settle(page, 500);
    const all = (await dcalls(page)).filter((c) => c.cmd === "brain_decks_card_act");
    await page.close();
    assert.match(list, /What absorbs sunlight\?/);
    assert.match(list, /Chlorophyll/);
    assert.deepEqual(edit.map((c) => [c.action, c.front, c.back]), [["edit", "New front", "New back"]]);
    assert.match(after, /New front/);
    assert.ok(sure.includes(W.delete_confirm));
    assert.equal(beforeDelete, 1, "the confirm did not wait");
    assert.equal(all[1].action, "delete");
  });

  await check("New deck makes an empty deck from a typed name", async () => {
    const page = await workTab(decksData());
    await fkey(page, "new-deck-open").click();
    await settle(page);
    const focusedOnName = await page.evaluate(() => document.activeElement && document.activeElement.dataset.fkey);
    await page.locator('[data-fkey="new-deck"]').fill("Cocina");
    await page.locator('[data-fkey="new-deck"]').press("Enter");
    await settle(page, 500);
    const calls = (await dcalls(page)).filter((c) => c.cmd === "brain_decks_create");
    const body = await text(page, "#decks-card");
    await page.close();
    assert.equal(focusedOnName, "new-deck");
    assert.deepEqual(calls.map((c) => c.name), ["Cocina"]);
    assert.match(body, /Cocina/);
  });

  await check("review: the card first, Show answer, then the four ratings in order; the typed words are never sent", async () => {
    const page = await workTab(decksData());
    await fkey(page, "review:d1a2b3c4d5e6").click();
    await settle(page, 500);
    const first = await text(page, "#decks-body");
    const ratingsBefore = await page.locator("[data-rating]").count();
    await page.locator(".review-typed").fill("MY PRIVATE GUESS");
    await page.getByRole("button", { name: W.show_answer }).click();
    await settle(page, 500);
    const shown = await text(page, "#decks-body");
    const labels = await page.locator("[data-rating]").allInnerTexts();
    const ids = await page.locator("[data-rating]").evaluateAll((n) => n.map((x) => x.dataset.rating));
    const focused = await page.evaluate(() => document.activeElement && document.activeElement.dataset.fkey);
    const calls = await dcalls(page);
    await page.close();
    assert.match(first, /What absorbs sunlight\?/);
    assert.ok(first.includes(W.show_answer));
    assert.equal(ratingsBefore, 0, "no rating before the answer is shown");
    assert.match(shown, /Chlorophyll/);
    assert.ok(shown.toLowerCase().includes(W.back_answer.toLowerCase()));
    assert.deepEqual(labels, [W.rating_again, W.rating_hard, W.rating_good, W.rating_easy]);
    assert.deepEqual(ids, ["again", "hard", "good", "easy"]);
    assert.equal(focused, "answer-heading");
    assert.equal(JSON.stringify(calls).includes("MY PRIVATE GUESS"), false, "the typed words were sent");
    const reveal = calls.filter((c) => c.cmd === "brain_review_reveal");
    assert.deepEqual(reveal.map((c) => Object.keys(c).sort()), [["card", "cmd"]]);
  });

  await check("rating sends the id for the button, shows the next card, and the last one ends on Nothing ready today", async () => {
    const page = await workTab(decksData());
    await fkey(page, "review:d1a2b3c4d5e6").click();
    await settle(page, 500);
    await page.getByRole("button", { name: W.show_answer }).click();
    await settle(page);
    await page.locator('[data-rating="good"]').click();
    await settle(page, 500);
    const next = await text(page, "#decks-body");
    const comes = next.includes("Comes back on 3 Oct 2026");
    await page.getByRole("button", { name: W.show_answer }).click();
    await settle(page);
    await page.locator('[data-rating="again"]').click();
    await settle(page, 600);
    const done = await text(page, "#decks-body");
    const calls = (await dcalls(page)).filter((c) => c.cmd === "brain_review_rate");
    await page.close();
    assert.match(next, /Where does it happen\?/);
    assert.ok(comes, `the date the PC gave is shown: ${next}`);
    assert.deepEqual(calls.map((c) => c.rating), ["good", "again"]);
    assert.ok(done.toLowerCase().includes(W.nothing_ready.toLowerCase()));
    assert.ok(done.includes("Next cards ready on 3 Oct 2026"), done);
    assert.equal(banned(done).length, 0);
  });

  await check("a run of 20 ends on That's enough for now; Do 10 more goes on; Stop leaves", async () => {
    const page = await workTab(decksData({ limit: 1 }));
    await fkey(page, "review:d1a2b3c4d5e6").click();
    await settle(page, 500);
    await page.getByRole("button", { name: W.show_answer }).click();
    await settle(page);
    await page.locator('[data-rating="easy"]').click();
    await settle(page, 600);
    const enough = await text(page, "#decks-body");
    await page.getByRole("button", { name: W.more }).click();
    await settle(page, 500);
    const more = await text(page, "#decks-body");
    await page.getByRole("button", { name: W.stop, exact: true }).click();
    await settle(page, 500);
    const back = await text(page, "#decks-card");
    const calls = (await dcalls(page)).filter((c) => c.cmd === "brain_review_more");
    await page.close();
    assert.ok(enough.toLowerCase().includes(W.enough.toLowerCase()));
    assert.ok(enough.includes(W.more) && enough.includes(W.stop));
    assert.match(more, /Where does it happen\?/);
    assert.equal(calls.length, 1);
    assert.ok(back.includes(W.cards_ready) || back.toLowerCase().includes(W.cards_ready.toLowerCase()));
    assert.match(back, /Plants/);
  });

  await check("Review is offered only for a deck with cards ready that is not paused; all decks paused: the PC's line, no Review", async () => {
    const page = await workTab(decksData());
    const paused = await fkey(page, "review:d2b3c4d5e6f7").isDisabled();
    const ready = await fkey(page, "review:d1a2b3c4d5e6").isDisabled();
    await page.close();
    assert.equal(paused, true);
    assert.equal(ready, false);
    const both = await workTab({ decks: { decks: [{ ...PLANTS(), paused: true }, VERBOS()] } });
    const all = await text(both, "#decks-body");
    const offs = await both.locator('#decks-card [data-fkey^="review"]').evaluateAll((els) => els.map((e) => e.disabled));
    await both.close();
    // (the test PC's stand-in says "Nothing ready today"; the real PC says "All decks paused")
    assert.match(all, /All decks paused|Nothing ready today/);
    assert.ok(offs.length > 0 && offs.every(Boolean), JSON.stringify(offs));
  });

  await check("Review all decks: one review over every deck; a rating names its scope (all = empty, a deck = its id)", async () => {
    const page = await workTab(decksData());
    await page.getByRole("button", { name: W.review_all }).click();
    await settle(page, 500);
    await page.getByRole("button", { name: W.show_answer }).click();
    await settle(page);
    await page.locator('[data-rating="good"]').click();
    await settle(page, 500);
    await fkey(page, "review-stop").click();
    await settle(page, 500);
    await fkey(page, "review:d1a2b3c4d5e6").click();
    await settle(page, 500);
    await page.getByRole("button", { name: W.show_answer }).click();
    await settle(page);
    await page.locator('[data-rating="good"]').click();
    await settle(page, 500);
    const calls = await dcalls(page);
    await page.close();
    const reviews = calls.filter((c) => c.cmd === "brain_review");
    const rates = calls.filter((c) => c.cmd === "brain_review_rate");
    assert.equal(reviews[0].deck ?? null, null, "the first review covers every deck");
    assert.equal(reviews[1].deck, "d1a2b3c4d5e6");
    assert.deepEqual(rates.map((c) => c.deck), ["", "d1a2b3c4d5e6"]);
  });

  await check("the PC no longer remembers the reveal (it restarted): the reveal is dropped and the card asked for again", async () => {
    const page = await workTab(decksData({}));
    await page.close();
    const p2 = await workTab({ ...decksData(), decks: { ...decksData().decks, refuse: { brain_review_rate: "not_revealed" } } });
    await fkey(p2, "review:d1a2b3c4d5e6").click();
    await settle(p2, 500);
    await p2.getByRole("button", { name: W.show_answer }).click();
    await settle(p2);
    await p2.locator('[data-rating="good"]').click();
    await settle(p2, 600);
    const reads = (await dcalls(p2)).filter((c) => c.cmd === "brain_review").length;
    const again = await p2.getByRole("button", { name: W.show_answer }).count();
    const rated = await p2.locator('[data-rating="good"]').count();
    await p2.close();
    assert.ok(reads >= 2, `the review was read ${reads} times`);
    assert.equal(again, 1, "Show answer is back");
    assert.equal(rated, 0, "the rating buttons are gone until the answer is shown again");
  });

  await check("a card that is gone: the review asks again instead of failing", async () => {
    const page = await workTab(decksData({ refuse: { brain_review_rate: "card_not_found" } }));
    await fkey(page, "review:d1a2b3c4d5e6").click();
    await settle(page, 500);
    await page.getByRole("button", { name: W.show_answer }).click();
    await settle(page);
    await page.locator('[data-rating="good"]').click();
    await settle(page, 600);
    const reads = (await dcalls(page)).filter((c) => c.cmd === "brain_review").length;
    await page.close();
    assert.ok(reads >= 2, `the review was read ${reads} times`);
  });

  await check("held on a stale link: every write is greyed, reads are not", async () => {
    const page = await workTab({ ...decksData(), link: { stale: true } });
    const grey = async (sel) => page.locator(sel).first().isDisabled();
    const out = {
      pause: await grey('[data-fkey^="pause:"]'),
      del: await grey('[data-fkey^="delete:"]'),
      add: await grey('[data-fkey="new-deck-open"]'),
      perDay: await page.locator("#decks-per-day").isDisabled(),
      review: await grey('[data-fkey^="review:"]'),
      cards: await grey('[data-fkey^="cards:"]'),
    };
    await page.close();
    assert.deepEqual(out, { pause: true, del: true, add: true, perDay: true, review: false, cards: false });
    const js = read("src/brain.js");
    const region = js.slice(js.indexOf("My study decks (the owner's decision"), js.indexOf("function rereadDecks"));
    for (const call of ["brain_review_reveal", "brain_review_rate", "brain_review_more"]) {
      const at = region.indexOf(`"${call}"`);
      assert.ok(region.slice(Math.max(0, at - 900), at).includes("canAct"), `${call}: no link check before it`);
    }
  });

  await check("hidden lists: names, cards and the review are out; counts and the line stay; Show brings them back", async () => {
    const page = await workTab({ ...decksData(), security: { hidden: true } });
    const hidden = await text(page, "#decks-card");
    const reviewButtons = await page.locator('#decks-card [data-fkey^="review:"]').count();
    const cardButtons = await page.locator('#decks-card [data-fkey^="cards:"]').count();
    const deleteButtons = await page.locator('#decks-card [data-fkey^="delete:"]').count();
    const reads = (await dcalls(page)).filter((c) => c.cmd === "brain_review").length;
    await page.evaluate(() => { window.__security.revealed = true; });
    await page.evaluate(() => window.__emit("security-changed", {}));
    await settle(page, 600);
    const shown = await text(page, "#decks-card");
    await page.close();
    assert.doesNotMatch(hidden, /Plants|Verbos/);
    assert.match(hidden, /2 cards ready/, "the line stays");
    assert.match(hidden, /3 cards/, "the counts stay");
    assert.ok(hidden.includes(W.review_hidden));
    assert.match(hidden, /Hidden until Windows Hello confirms it is you\./);
    assert.equal(reviewButtons + cardButtons + deleteButtons, 0);
    assert.equal(reads, 0, "review was asked of the PC while hidden");
    assert.match(shown, /Plants/);
  });

  await check("a review open when the lists are hidden closes, and no card word stays drawn", async () => {
    const page = await workTab(decksData());
    await fkey(page, "review:d1a2b3c4d5e6").click();
    await settle(page, 500);
    await page.evaluate(() => { window.__security.hidden = true; window.__security.revealed = false; });
    await page.evaluate(() => window.__emit("private-hidden", {}));
    await settle(page, 600);
    const body = await text(page, "#decks-card");
    await page.close();
    assert.doesNotMatch(body, /What absorbs sunlight/);
    assert.doesNotMatch(body, /Plants/);
  });

  await check("nothing of a deck, card or typed answer is stored in the browser", async () => {
    const page = await workTab(decksData());
    await fkey(page, "review:d1a2b3c4d5e6").click();
    await settle(page, 500);
    await page.locator(".review-typed").fill("SECRET TYPED WORDS");
    await page.getByRole("button", { name: W.show_answer }).click();
    await settle(page);
    const stored = await page.evaluate(() => JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage)]));
    await page.close();
    assert.doesNotMatch(stored, /SECRET TYPED|Plants|Chlorophyll|sunlight/);
  });

  /* Spanish practice and the Keep sheet, on the quiz page. */

  const answerAll = async (page, n, typed = (i) => `mi respuesta ${i}`) => {
    for (let i = 1; i <= n; i += 1) {
      await page.locator("#quiz-run textarea.quiz-answer").fill(typed(i));
      await page.locator("#quiz-run").getByRole("button", { name: Q.ANSWER_LABEL }).click();
      await settle(page, 400);
      const next = page.locator("#quiz-run").getByRole("button", { name: Q.NEXT_LABEL });
      if (i < n && await next.count()) { await next.click(); await settle(page, 250); }
    }
  };
  const startSpanish = async (page, opts = {}) => {
    await page.locator('input[name="quiz-mode"][value="spanish"]').check();
    if (opts.level) await page.locator("#quiz-level").selectOption(opts.level);
    if (opts.exercise) await page.locator("#quiz-exercise").selectOption(opts.exercise);
    if (opts.topic) await page.locator("#quiz-topic").fill(opts.topic);
    if (opts.text) await page.locator("#quiz-text").fill(opts.text);
    await page.locator("#quiz-start").click();
    await settle(page, 500);
  };

  await check("the mode chooser: Text and Spanish practice; Spanish shows level, exercise and topic in the shared words", async () => {
    const page = await workTab({ quiz: {} });
    const modes = await page.locator("#quiz-mode label").allInnerTexts();
    const hiddenBefore = await page.locator("#quiz-spanish").isHidden();
    await page.locator('input[name="quiz-mode"][value="spanish"]').check();
    await settle(page);
    const levels = await page.locator("#quiz-level option").allInnerTexts();
    const exercises = await page.locator("#quiz-exercise option").allInnerTexts();
    const levelLabel = (await page.locator('label[for="quiz-level"]').innerText()).trim();
    const topicLabel = (await page.locator('label[for="quiz-topic"]').innerText()).trim();
    const counter0 = (await text(page, "#quiz-topic-count")).trim();
    await page.locator("#quiz-topic").fill("food");
    const counter1 = (await text(page, "#quiz-topic-count")).trim();
    const placeholder = await page.locator("#quiz-text").getAttribute("placeholder");
    const startLabel = (await text(page, "#quiz-start")).trim();
    await page.locator('input[name="quiz-mode"][value="text"]').check();
    const back = await page.locator("#quiz-text").getAttribute("placeholder");
    await page.close();
    assert.deepEqual(modes.map((m) => m.trim()), [W.mode_text, W.mode_spanish]);
    assert.equal(hiddenBefore, true);
    assert.deepEqual(levels, ["A1", "A2", "B1", "B2", "C1", "C2"]);
    assert.deepEqual(exercises, [W.exercise_translate, W.exercise_blank, W.exercise_complete, W.exercise_mixed]);
    assert.equal(levelLabel, W.level_heading);
    assert.equal(topicLabel, W.topic_label);
    assert.equal(counter0, W.topic_counter);
    assert.equal(counter1, "4 / 60");
    assert.equal(placeholder, W.spanish_placeholder);
    assert.equal(startLabel, W.start_button);
    assert.equal(back, "Paste the text here");
  });

  await check("Spanish practice starts with no text, sends the choices, shows the level and the PC's notice above the answer box", async () => {
    const page = await workTab({ quiz: { notice: "THE PC'S OWN SPANISH NOTICE" } });
    await startSpanish(page, { level: "B1", exercise: "mixed", topic: "food" });
    const sent = (await qcalls(page)).filter((c) => c.cmd === "brain_quiz_start");
    const run = await text(page, "#quiz-run");
    const accents = await page.locator(".quiz-accents button").allInnerTexts();
    const kind = await text(page, "#quiz-run .row-tag >> nth=0");
    await page.close();
    assert.equal(sent.length, 1);
    assert.deepEqual({ mode: sent[0].mode, level: sent[0].level, exercise: sent[0].exercise, topic: sent[0].topic },
      { mode: "spanish", level: "B1", exercise: "mixed", topic: "food" });
    assert.equal("text" in sent[0], false, "no text was sent");
    assert.match(run, /Level B1 \(roughly\)/);
    assert.ok(run.includes("THE PC'S OWN SPANISH NOTICE"), "the notice is the PC's, above the answer box");
    assert.deepEqual(accents, FIX.accents);
    assert.equal(kind.toLowerCase(), W.kind_blank.toLowerCase());
  });

  await check("an accent button puts its letter at the cursor and the count line follows", async () => {
    const page = await workTab({ quiz: {} });
    await startSpanish(page, {});
    const box = page.locator("#quiz-run textarea.quiz-answer");
    await box.fill("mao");
    await box.evaluate((n) => n.setSelectionRange(2, 2));
    await page.locator(".quiz-accents").getByRole("button", { name: "Insert ñ" }).click();
    const value = await box.inputValue();
    const caret = await box.evaluate((n) => n.selectionStart);
    const count = await text(page, "#quiz-run .note >> nth=-1");
    await page.close();
    assert.equal(value, "maño");
    assert.equal(caret, 3);
    assert.ok(count.length > 0);
  });

  await check("a Spanish mark shows the answer, the PC's key label and the right heading; the guess only for a model mark", async () => {
    const page = await workTab({ quiz: {} });
    await startSpanish(page, { exercise: "mixed" });
    await answerAll(page, 1);
    const blank = await text(page, "#quiz-run");
    await page.locator("#quiz-run").getByRole("button", { name: Q.NEXT_LABEL }).click();
    await settle(page);
    await page.locator("#quiz-run textarea.quiz-answer").fill("the cat");
    await page.locator("#quiz-run").getByRole("button", { name: Q.ANSWER_LABEL }).click();
    await settle(page, 400);
    const translate = await text(page, "#quiz-run");
    await page.close();
    assert.match(blank, /Answer: está/);
    assert.ok(blank.includes(W.key_label_model));
    assert.ok(blank.includes(W.passage_example));
    assert.doesNotMatch(blank, /Jarvis's guess/i, "a code-marked mark shows no guess");
    assert.match(translate, /Jarvis's guess/i);
  });

  await check("a PC without Spanish practice says so, and Text mode is all that is offered afterwards", async () => {
    // Pasting Spanish text: the older PC answers with a quiz that has no mode.
    const withText = await workTab({ quiz: { noMode: true } });
    await startSpanish(withText, { text: PASTE });
    const run = await text(withText, "#quiz-run");
    const disabled = await withText.locator('input[name="quiz-mode"][value="spanish"]').isDisabled();
    const checked = await withText.locator('input[name="quiz-mode"][value="text"]').isChecked();
    const formShown = await withText.locator("#quiz-start-form").isVisible();
    const stopped = (await qcalls(withText)).some((c) => c.cmd === "brain_quiz_stop");
    await withText.close();
    assert.ok(run.includes(Q.OLD_PC_SPANISH));
    assert.equal(disabled, true);
    assert.equal(checked, true);
    assert.equal(formShown, true);
    assert.equal(stopped, true, "the quiz the older PC made was let go");
    // No text at all: the older PC says "too short", which a PC with Spanish never does.
    const none = await workTab({ quiz: { noMode: true } });
    await startSpanish(none, {});
    const words = await text(none, "#quiz-run");
    await none.close();
    assert.ok(words.includes(Q.OLD_PC_SPANISH), words);
  });

  await check("Keep: every answered question is a row, ticked for Partly and Not yet, the back prefilled only for Got it", async () => {
    const page = await workTab({ quiz: {}, decks: { decks: [PLANTS()] } });
    await page.locator("#quiz-text").fill(PASTE);
    await page.locator("#quiz-start").click();
    await settle(page, 500);
    const keepDisabledBefore = await page.locator("#quiz-run").getByRole("button", { name: W.keep_button }).isDisabled();
    await answerAll(page, 2, (i) => `my own words ${i}`);
    const keepEnabled = await page.locator("#quiz-run").getByRole("button", { name: W.keep_button }).isEnabled();
    await page.locator("#quiz-run").getByRole("button", { name: W.keep_button }).click();
    await settle(page, 600);
    const ticks = await page.locator(".keep-row input[type=checkbox]").evaluateAll((n) => n.map((x) => x.checked));
    const backs = await page.locator(".keep-back").evaluateAll((n) => n.map((x) => x.value));
    const rowsText = await text(page, "#quiz-run");
    const placeholder = await page.locator(".keep-back").first().getAttribute("placeholder");
    const options = await page.locator("#keep-deck option").allInnerTexts();
    const name = await page.locator("#keep-name").inputValue();
    const focused = await page.evaluate(() => document.activeElement && document.activeElement.dataset.fkey);
    await page.close();
    assert.equal(keepDisabledBefore, true, "Keep waits for an answered question");
    assert.equal(keepEnabled, true);
    assert.deepEqual(ticks, [false, true]);
    assert.deepEqual(backs, ["my own words 1", ""]);
    assert.match(rowsText, /Question text number 1\?/);
    assert.match(rowsText, /SOURCE PASSAGE 1/);
    assert.ok(rowsText.includes("0 / 2000") || rowsText.includes("/ 2000 characters"));
    assert.ok(rowsText.includes(W.from_text || W.passage_from_text));
    assert.ok(!rowsText.includes("The passage says otherwise"), "the model's comment is never a back");
    assert.equal(placeholder, W.keep_back_placeholder);
    assert.deepEqual(options, [W.new_deck, "Plants"]);
    assert.equal(name, "Bread", "a new deck is named after the quiz");
    assert.equal(focused, "tick:1");
  });

  await check("Keep and finish sends only n and the back, shows Kept N questions, and the decks section has the new deck", async () => {
    const page = await workTab({ quiz: {}, decks: { decks: [PLANTS()] } });
    await page.locator("#quiz-text").fill(PASTE);
    await page.locator("#quiz-start").click();
    await settle(page, 500);
    await answerAll(page, 3, (i) => `respuesta ${i}`);
    await page.locator("#quiz-run").getByRole("button", { name: W.keep_button }).click();
    await settle(page, 500);
    await page.locator(".keep-row input[type=checkbox]").first().check();
    await page.locator(".keep-back").nth(2).fill("written by me");
    await page.locator("#keep-name").fill("Panadería");
    await page.locator("#quiz-run").getByRole("button", { name: W.keep_finish }).click();
    await settle(page, 700);
    const finish = (await qcalls(page)).filter((c) => c.cmd === "brain_quiz_finish");
    const run = await text(page, "#quiz-run");
    const decks = await text(page, "#decks-card");
    const cardsBack = await page.evaluate(() => window.__decks.decks.find((d) => d.name === "Panadería").cards.map((c) => c.back));
    await page.close();
    assert.equal(finish.length, 1);
    assert.deepEqual(Object.keys(finish[0].keep).sort(), ["cards", "deck", "new_deck"]);
    assert.equal(finish[0].keep.deck, null);
    assert.equal(finish[0].keep.new_deck, "Panadería");
    assert.deepEqual(finish[0].keep.cards, [
      { n: 1, answer: "respuesta 1" }, { n: 2, answer: "" }, { n: 3, answer: "written by me" }]);
    assert.match(run, /Kept 3 questions/);
    assert.match(decks, /Panadería/);
    assert.deepEqual(cardsBack, ["respuesta 1", "", "written by me"]);
  });

  await check("Keep: a refusal keeps the sheet, its ticks and backs; the PC's message is shown word for word", async () => {
    const page = await workTab({ quiz: { keepRefuse: "duplicate_card" }, decks: { decks: [PLANTS()] } });
    await page.locator("#quiz-text").fill(PASTE);
    await page.locator("#quiz-start").click();
    await settle(page, 500);
    await answerAll(page, 2, (i) => `respuesta ${i}`);
    await page.locator("#quiz-run").getByRole("button", { name: W.keep_button }).click();
    await settle(page, 500);
    await page.locator(".keep-back").nth(1).fill("kept for retry");
    await page.locator("#quiz-run").getByRole("button", { name: W.keep_finish }).click();
    await settle(page, 600);
    const run = await text(page, "#quiz-run");
    const backs = await page.locator(".keep-back").evaluateAll((n) => n.map((x) => x.value));
    const ticks = await page.locator(".keep-row input[type=checkbox]").evaluateAll((n) => n.map((x) => x.checked));
    const quizStillOpen = await page.evaluate(() => window.__quiz.quiz !== null);
    await page.close();
    assert.ok(run.includes("the PC's own words for duplicate_card"));
    assert.deepEqual(backs, ["respuesta 1", "kept for retry"]);
    assert.deepEqual(ticks, [false, true]);
    assert.equal(quizStillOpen, true);
  });

  await check("Keep: a crisis phrase in a back shows the PC's words calmly, keeps nothing, and the sheet stays", async () => {
    const page = await workTab({ quiz: { crisisWord: "XXCRISISXX" }, decks: { decks: [PLANTS()] } });
    await page.locator("#quiz-text").fill(PASTE);
    await page.locator("#quiz-start").click();
    await settle(page, 500);
    await answerAll(page, 2, (i) => `respuesta ${i}`);
    await page.locator("#quiz-run").getByRole("button", { name: W.keep_button }).click();
    await settle(page, 500);
    await page.locator(".keep-back").nth(1).fill("something XXCRISISXX");
    await page.locator("#quiz-run").getByRole("button", { name: W.keep_finish }).click();
    await settle(page, 600);
    const run = await text(page, "#quiz-run");
    const decksAfter = await page.evaluate(() => window.__decks.decks.length);
    const sheet = await page.locator(".keep-row").count();
    await page.close();
    assert.match(run, /STAND-IN HELP WORDS/);
    assert.equal(decksAfter, 1, "nothing was kept");
    assert.equal(sheet, 2);
  });

  await check("Keep: not offered while the lists are hidden, and says why", async () => {
    const page = await workTab({ quiz: {}, decks: { decks: [PLANTS()] }, security: { hidden: true } });
    await page.locator("#quiz-text").fill(PASTE);
    await page.locator("#quiz-start").click();
    await settle(page, 500);
    const disabled = await page.locator("#quiz-run").getByRole("button", { name: W.keep_button }).isDisabled();
    const run = await text(page, "#quiz-run");
    await page.close();
    assert.equal(disabled, true);
    assert.ok(run.includes(W.keep_hidden));
  });

  await check("Keep: decks that are unavailable show the PC's why and Keep and finish cannot be pressed", async () => {
    const why = "Decks are not set up on this PC: no key in Credential Manager.";
    const page = await workTab({ quiz: {}, decks: { decks: [], available: false, why } });
    await page.locator("#quiz-text").fill(PASTE);
    await page.locator("#quiz-start").click();
    await settle(page, 500);
    await answerAll(page, 1);
    await page.locator("#quiz-run").getByRole("button", { name: W.keep_button }).click();
    await settle(page, 600);
    const run = await text(page, "#quiz-run");
    const disabled = await page.locator("#quiz-run").getByRole("button", { name: W.keep_finish }).isDisabled();
    const cancel = page.locator("#quiz-run").getByRole("button", { name: W.keep_cancel });
    await cancel.click();
    await settle(page);
    const back = await text(page, "#quiz-run");
    const sent = (await qcalls(page)).filter((c) => c.cmd === "brain_quiz_finish").length;
    await page.close();
    assert.ok(run.includes(why));
    assert.equal(disabled, true);
    assert.match(back, /Check my answer|Next question|Finish/);
    assert.equal(sent, 0, "Cancel sends nothing");
  });

  await check("Text mode still works: no mode sent, the crisis flow and the guess label unchanged", async () => {
    const page = await workTab({ quiz: { crisisWord: "XXCRISISXX" } });
    await page.locator("#quiz-text").fill(PASTE);
    await page.locator("#quiz-start").click();
    await settle(page, 500);
    const start = (await qcalls(page)).find((c) => c.cmd === "brain_quiz_start");
    await page.locator("#quiz-run textarea.quiz-answer").fill("XXCRISISXX now");
    await page.locator("#quiz-run").getByRole("button", { name: Q.ANSWER_LABEL }).click();
    await settle(page, 400);
    const run = await text(page, "#quiz-run");
    const boxAfter = await page.locator("#quiz-run textarea.quiz-answer").inputValue();
    await page.close();
    assert.equal("mode" in start, false);
    assert.deepEqual(Object.keys(start).sort(), ["cmd", "text"]);
    assert.match(run, /STAND-IN HELP WORDS/);
    assert.equal(boxAfter, "", "the typed words are let go");
  });

  await check("the crisis answer is never held for the Keep sheet", async () => {
    const page = await workTab({ quiz: { crisisWord: "XXCRISISXX", levels: ["got_it", "got_it", "got_it"] }, decks: { decks: [PLANTS()] } });
    await page.locator("#quiz-text").fill(PASTE);
    await page.locator("#quiz-start").click();
    await settle(page, 500);
    await page.locator("#quiz-run textarea.quiz-answer").fill("XXCRISISXX please");
    await page.locator("#quiz-run").getByRole("button", { name: Q.ANSWER_LABEL }).click();
    await settle(page, 400);
    await page.locator("#quiz-run textarea.quiz-answer").fill("a calm answer");
    await page.locator("#quiz-run").getByRole("button", { name: Q.ANSWER_LABEL }).click();
    await settle(page, 400);
    await page.locator("#quiz-run").getByRole("button", { name: W.keep_button }).click();
    await settle(page, 500);
    const backs = await page.locator(".keep-back").evaluateAll((n) => n.map((x) => x.value));
    await page.close();
    assert.deepEqual(backs, ["a calm answer"], "only the calm answer is a row, and it is the owner's own words");
  });

  await browser.close();
  close();
}

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nDecks: no card, nothing stored, no lateness words, hidden with the private lists, every write held on a stale link");
process.exit(fails.length ? 1 : 0);
