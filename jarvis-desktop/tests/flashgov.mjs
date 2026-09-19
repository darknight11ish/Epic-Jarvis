/**
 * The flash governor - photosensitivity safety, not style.
 *
 * `jarvis-visual-spec.json`'s own `limits.flash.note` claims three
 * enforcement points, one of which is "a governor inside resolve() holds
 * the colour when a fourth opposing transition would land inside one
 * second." `docs/CROSS-CLIENT-CONTRACT-REPLY-2.md` recorded that governor
 * as built here and in `spec.rs`, but not fully wired: the state chips'
 * colour swatches (`swatchFor()`) called `resolve()` directly, bypassing
 * every governor on the page - exactly the gap `limits.flash.scope_why`
 * names by itself ("one window per SURFACE (and one for the UI swatches)").
 *
 * This drives the REAL `newFlashGovernor`/`governedResolve`/`relativeLuma`
 * lifted out of `src/faces.html` with `slice`, not retyped - the same
 * "verify against the actual file" rule the backend's `ast`-lifted Python
 * tests already follow. `resolve()` itself is not lifted: a governor test
 * should not depend on which pattern kinds exist or how they compute a
 * colour, only on how the governor treats a sequence of colours it is
 * handed - so a small deterministic double stands in for it, the same way
 * `test_ui_control.py` injects a fake `read`/`act` around the real `run()`.
 *
 * No browser: this needs nothing `voicecheck.mjs` doesn't already assume.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const html = readFileSync(join(SRC, "faces.html"), "utf8");
const spec = JSON.parse(readFileSync(join(SRC, "jarvis-visual-spec.json"), "utf8"));

// `through=true` includes the end marker's own text (for a function whose
// body IS the marker); `through=false` cuts right before it (for stopping
// at the next block's own header without swallowing that comment).
function slice(source, startMarker, endMarker, through) {
  const start = source.indexOf(startMarker);
  assert.notEqual(start, -1, `marker not found: ${startMarker}`);
  const end = source.indexOf(endMarker, start);
  assert.notEqual(end, -1, `end marker not found after start: ${endMarker}`);
  return source.slice(start, through ? end + endMarker.length : end);
}

// Exactly the source `parseCol` needs, and exactly the source `relativeLuma`
// through `governedResolve` - the real functions, not a paraphrase.
const colSource = slice(html, "const _COL_MEMO = new Map();",
  "function mix(h1, h2, t){\n  const [r1,g1,b1] = parseCol(h1), [r2,g2,b2] = parseCol(h2);\n  return `rgb(${Math.round(lerp(r1,r2,t))},${Math.round(lerp(g1,g2,t))},${Math.round(lerp(b1,b2,t))})`;\n}",
  true);
const governorSource = slice(html, "function relativeLuma(hex){",
  "\n\n/* ====================================================================== *\n * COLOUR OVERRIDE",
  false);

// `resolve()` is deliberately NOT lifted - see the module doc above. This
// double stands in its place: `SEQ[i % SEQ.length]` lets a test dictate the
// exact luma sequence a "surface" sees, independent of any real pattern.
//
// A binding carrying its own `hex` short-circuits the sequence and resolves
// to that colour every time. The swatch-strip test below needs eight
// bindings that each resolve to a FIXED, different colour - "which chip am I
// looking at" is the whole question there, and a call-order-driven double
// cannot ask it.
let SEQ = [];
let calls = 0;
function resolve(bind) {
  if (bind && bind.hex) return { a: bind.hex, b: bind.hex };
  const hex = SEQ[calls % SEQ.length];
  calls += 1;
  return { a: hex, b: hex };
}

const factory = new Function(
  "SPEC",
  "resolve",
  "lerp",
  `${colSource}\n${governorSource}\nreturn { newFlashGovernor, governedResolve, relativeLuma };`,
);
const { newFlashGovernor, governedResolve, relativeLuma } = factory(
  spec,
  (...args) => resolve(...args),
  (a, b, t) => a + (b - a) * t,
);

// The UI swatch strip, lifted the same way - `SWATCH_GOV` and the real
// `swatchFor()`. This is the part a governor-only test cannot reach, and a
// shipped regression lived in exactly this gap: the governor was correct and
// the CALL SITE shared one instance across all eight chips. `BIND` and
// `performance` are injected so a test can dictate both.
const SWATCH_BIND = {};
const swatchSource = slice(html, "const SWATCH_GOV = {};", "function buildPatterns(){", false);
const swatchFactory = new Function(
  "SPEC",
  "resolve",
  "lerp",
  "BIND",
  "performance",
  "document",
  `${colSource}\n${governorSource}\n${swatchSource}\nreturn { swatchFor, SWATCH_GOV };`,
);
// A monotonic clock the test advances by hand: `swatchFor` reads
// `performance.now()`, and a governor window is only meaningful against a
// clock the test controls.
let SWATCH_MS = 0;
const { swatchFor: realSwatchFor } = swatchFactory(
  spec,
  (...args) => resolve(...args),
  (a, b, t) => a + (b - a) * t,
  SWATCH_BIND,
  { now: () => SWATCH_MS },
  { getElementById: () => null },
);

const fails = [];
let ran = 0;
const check = (name, fn) => {
  ran += 1;
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const BRIGHT = "#ffffff", DARK = "#000000";

/**
 * The most opposing transitions that actually reached the screen inside any
 * one-second window, measured on REAL time.
 *
 * This is the limit as the spec states it, and asserting it directly is what
 * these checks do now. They used to assert on the single final frame instead
 * ("the last sample must not be the candidate") - which was equivalent only
 * for one exact drive length, and silently stopped meaning anything the
 * moment the governor's budget shifted by one. A count over a window cannot
 * be tuned that way: it is either over the limit or it is not.
 *
 * `samples` is [{ now, hex }] in the order shown. A repeat of the same colour
 * is not a transition, which is precisely why a held frame does not count.
 */
function worstWindow(samples) {
  let worst = 0, last = null;
  const win = [];
  for (const s of samples) {
    if (last === null) { last = s.hex; continue; }   // an appearance, not a transition
    if (s.hex === last) continue;
    win.push(s.now);
    while (win.length && s.now - win[0] >= 1.0) win.shift();
    worst = Math.max(worst, win.length);
    last = s.hex;
  }
  return worst;
}
// Real spec numbers, not hand-copied ones - the same reason voicecheck.mjs
// reads voice.js's constants from the spec rather than asserting a literal.
const { min_luma_delta: MIN_DELTA, max_transitions_per_s: MAX_PER_S } = spec.limits.flash;
assert.ok(relativeLuma(BRIGHT) - relativeLuma(DARK) > MIN_DELTA,
  "CONTROL: the test's own bright/dark pair must actually count as a transition");

check("the first call is never held - nothing to hold yet", () => {
  SEQ = [BRIGHT]; calls = 0;
  const gov = newFlashGovernor();
  const out = governedResolve(gov, {}, 0.0, 0.0, 0);
  assert.equal(out.a, BRIGHT);
});

check(`no more than ${MAX_PER_S} opposing transitions reach the screen in any second`, () => {
  SEQ = [DARK, BRIGHT]; calls = 0;
  const gov = newFlashGovernor();
  const seen = [];
  // A 10 Hz alternation across two real seconds - far over the budget if
  // nothing holds it.
  for (let i = 0; i < 40; i++) {
    const now = i * 0.05;
    seen.push({ now, hex: governedResolve(gov, {}, now, 0.0, 0).a });
  }
  const worst = worstWindow(seen);
  assert.ok(worst <= MAX_PER_S,
    `the governor let ${worst} transitions land inside one second; the spec's limit is ${MAX_PER_S}`);
  // CONTROL: the drive really was over the limit, so a no-op governor would
  // have failed the assertion above rather than coincidentally passing it.
  const ungoverned = seen.map((s, i) => ({ now: s.now, hex: i % 2 ? BRIGHT : DARK }));
  assert.ok(worstWindow(ungoverned) > MAX_PER_S,
    "CONTROL: this drive must be over the limit before the governor sees it");
});

check("once a second passes, the window forgets and a new transition is allowed", () => {
  SEQ = [DARK, BRIGHT]; calls = 0;
  const gov = newFlashGovernor();
  for (let i = 0; i <= MAX_PER_S * 2; i++) governedResolve(gov, {}, i * 0.1, 0.0, 0);
  // Held by now - the loop above already spent the budget. Jump two seconds
  // ahead: `gov.recent` filters to `t - at < 1.0`, so nothing survives.
  const out = governedResolve(gov, {}, 10.0, 0.0, 0);
  assert.equal(out.a, calls % 2 === 1 ? DARK : BRIGHT,
    "a transition long after the window emptied should not still be held");
});

check("a swing below min_luma_delta is never counted as a transition at all", () => {
  const barelyDifferent = "#000001"; // luma delta far under the spec's floor
  SEQ = [DARK, barelyDifferent]; calls = 0;
  const gov = newFlashGovernor();
  let lastHeld = null;
  for (let i = 0; i <= MAX_PER_S * 3; i++) {
    lastHeld = governedResolve(gov, {}, i * 0.1, 0.0, 0).a;
  }
  // Every call updates gov.held directly (the "not a real change" branch),
  // so the final candidate must be whatever SEQ produced last, unheld.
  assert.equal(lastHeld, SEQ[calls % SEQ.length === 0 ? SEQ.length - 1 : (calls - 1) % SEQ.length]);
});

check("CONTROL: a lone opposing transition, alone, is never held", () => {
  SEQ = [DARK, BRIGHT]; calls = 0;
  const gov = newFlashGovernor();
  governedResolve(gov, {}, 0.0, 0.0, 0);       // DARK, first call
  const out = governedResolve(gov, {}, 5.0, 0.0, 0); // BRIGHT, five seconds later
  assert.equal(out.a, BRIGHT, "CONTROL: a single well-spaced transition must pass through");
});

// --------------------------------------------------------------------------
// The one-second window is REAL seconds
//
// `governedResolve` takes two clocks: `t` drives the pattern and a speed
// control may scale it; `now` is unscaled wall time and is the only thing the
// window is measured in. They used to be one argument, and `faces.html`
// passed `s.clock` - which advances by `dt * speed`. At the top of a 6x
// speed slider one governor "second" was 1/6 of a real one, so up to 18
// opposing transitions per real second got through against a hard limit of 3.
// --------------------------------------------------------------------------

const SPEED = 6;  // spec speed.max reaches 6

check("the one-second window counts real seconds, not a speed-scaled face clock", () => {
  SEQ = [DARK, BRIGHT]; calls = 0;
  const gov = newFlashGovernor();
  const seen = [];
  // A face clock running 6x: the `t` values span twelve units while `now`
  // spans two real seconds. Only `now` may decide the window.
  for (let i = 0; i < 40; i++) {
    const now = i * 0.05;
    seen.push({ now, hex: governedResolve(gov, {}, now * SPEED, 0.0, 0, now).a });
  }
  const worst = worstWindow(seen);
  assert.ok(worst <= MAX_PER_S,
    `${worst} transitions landed inside one real second against a limit of ` +
    `${MAX_PER_S} - the window must not scale with animation speed`);
});

check("CONTROL: one scaled clock for both is what the bug looked like", () => {
  // The same drive with `now` left to default to `t` - the old, single-clock
  // call. This exists so the check above is known to bite: if this ever
  // starts passing, that one has stopped proving anything.
  SEQ = [DARK, BRIGHT]; calls = 0;
  const gov = newFlashGovernor();
  const seen = [];
  for (let i = 0; i < 40; i++) {
    const now = i * 0.05;
    seen.push({ now, hex: governedResolve(gov, {}, now * SPEED, 0.0, 0).a });
  }
  const worst = worstWindow(seen);
  assert.ok(worst > MAX_PER_S,
    "CONTROL: with one scaled clock the window empties between frames and " +
    `transitions get through - saw ${worst}, expected more than ${MAX_PER_S}`);
});

// --------------------------------------------------------------------------
// THE CALL SITE, not just the function
//
// Everything above drives `governedResolve` directly, and that is not enough.
// The photosensitivity bug was never IN the function - it was in what
// `drawSurface` handed it: `s.clock`, which advances by `dt * speed`, for
// both the pattern clock and the window clock. Reverting only that call site
// left every check above passing, which was measured, not assumed. A
// safety-critical fix guarded by a test that cannot see the code it guards
// is not guarded.
//
// So this reads the real call out of `faces.html` and asserts its shape. A
// source assertion is weaker than a behavioural one and is the right tool
// here: the alternative is standing up the whole render loop, and the thing
// that can silently regress is one argument.
// --------------------------------------------------------------------------

// Anchored on each CALL, never on the declaration. A looser pattern
// (`governedResolve\(gov,`) matched `function governedResolve(gov, bind, …)`
// first and then asserted things about the function body - a check that was
// red on correct code, which is worse than no check at all.
function callSite(pattern) {
  const m = html.match(pattern);
  assert.ok(m, `call site not found in faces.html: ${pattern}`);
  const text = m[0].replace(/\s+/g, " ");
  assert.doesNotMatch(text, /^function /,
    `matched the declaration instead of a call: ${text}`);
  return text;
}

check("the face renderer hands the governor a REAL-TIME clock, not s.clock", () => {
  const call = callSite(/governedResolve\(s\.flashGov,[^;]*\);/);
  // Six arguments: the sixth is the window clock.
  const args = call.slice(call.indexOf("(") + 1, call.lastIndexOf(")"));
  const depth = [];
  const top = [];
  let cur = "";
  for (const ch of args) {
    if (ch === "(") depth.push(ch);
    if (ch === ")") depth.pop();
    if (ch === "," && depth.length === 0) { top.push(cur.trim()); cur = ""; continue; }
    cur += ch;
  }
  top.push(cur.trim());
  assert.equal(top.length, 6,
    `expected 6 arguments so the window clock is passed explicitly, got ${top.length}: ${call}`);
  assert.match(top[5], /performance\.now\(\)/,
    `the 6th argument is the one-second window's clock and must be real time, got ${top[5]}`);
  assert.doesNotMatch(top[5], /s\.clock/,
    "the window clock must not be the speed-scaled face clock");
  // CONTROL: the pattern clock really is still the face's own, or the
  // animation would stop following the speed slider.
  assert.match(top[2], /s\.clock/,
    `the 3rd argument is the pattern clock and should stay s.clock, got ${top[2]}`);
});

check("the swatch strip's clock is real time too", () => {
  const call = callSite(/governedResolve\(gov, BIND\[sid\][^;]*\);/);
  assert.match(call, /performance\.now\(\)/, call);
});

// --------------------------------------------------------------------------
// The UI swatch strip - one governor per chip
//
// The regression this covers was shipped: a single `SWATCH_GOV` instance
// shared by all eight state chips. `syncUI()` loops every chip through
// `swatchFor()` in one pass at one timestamp, so the shared governor saw
// eight UNRELATED colours as one surface flashing between them, spent its
// three-transition budget on the first few, and handed the rest a previous
// chip's held colour: `approval` and `standby` rendered speaking's ice blue,
// `banked` rendered error's pink. It did not flicker; it lied, stably.
//
// `tests/flashgov.mjs` passed throughout, because every check above drives a
// SINGLE governor instance. That is the gap. The invariant below is the one
// that catches it, and it is the picker's entire contract: a chip whose bound
// colour never changes must never render another chip's colour.
// --------------------------------------------------------------------------

const CHIPS = ["thinking", "listening", "speaking", "idle",
               "approval", "standby", "banked", "error"];
// Alternating bright and dark, so consecutive chips are always an opposing
// transition to a governor foolish enough to compare them.
const CHIP_HEX = Object.fromEntries(
  CHIPS.map((id, i) => [id, i % 2 === 0 ? BRIGHT : DARK]));

check("every state chip shows its OWN colour, not the previous chip's", () => {
  CHIPS.forEach(id => { SWATCH_BIND[id] = { hex: CHIP_HEX[id] }; });
  SWATCH_MS = 0;
  const shown = Object.fromEntries(CHIPS.map(id => [id, realSwatchFor(id)]));
  const wrong = CHIPS.filter(id => shown[id] !== CHIP_HEX[id]);
  assert.deepEqual(wrong, [],
    `these chips rendered a colour that is not theirs: ` +
    wrong.map(id => `${id} bound ${CHIP_HEX[id]} but showed ${shown[id]}`).join("; "));
});

check("repeated syncUI passes never make a chip drift onto another's colour", () => {
  CHIPS.forEach(id => { SWATCH_BIND[id] = { hex: CHIP_HEX[id] }; });
  SWATCH_MS = 0;
  // Twelve full passes at 30ms apart - what clicking rapidly through the
  // pattern list does, and far more than the three-per-second budget a
  // shared instance would have to spend.
  for (let pass = 0; pass < 12; pass++) {
    SWATCH_MS += 30;
    for (const id of CHIPS) {
      assert.equal(realSwatchFor(id), CHIP_HEX[id],
        `chip ${id} drifted onto another chip's colour on pass ${pass}`);
    }
  }
});

check("a chip's own governor still holds a genuine fast flash on that chip", () => {
  // The per-chip split must not disable the governor - one chip whose own
  // binding oscillates is exactly what it is still there to catch.
  CHIPS.forEach(id => { delete SWATCH_BIND[id]; });
  SWATCH_BIND.thinking = {};        // no `hex`, so the SEQ double drives it
  SEQ = [DARK, BRIGHT]; calls = 0;
  SWATCH_MS = 0;
  const seen = [];
  for (let i = 0; i < 40; i++) {
    SWATCH_MS += 50;
    seen.push({ now: SWATCH_MS / 1000, hex: realSwatchFor("thinking") });
  }
  const worst = worstWindow(seen);
  assert.ok(worst <= MAX_PER_S,
    `one chip flashing on its own must still be governed - saw ${worst} ` +
    `transitions in a second against a limit of ${MAX_PER_S}`);
});

console.log(`\n${fails.length === 0 ? `all ${ran}` : `${fails.length} of ${ran}`} checks ` +
            `${fails.length === 0 ? "passed" : "failed"}`);
if (fails.length) {
  console.log("failed: " + fails.join(", "));
  process.exit(1);
}
