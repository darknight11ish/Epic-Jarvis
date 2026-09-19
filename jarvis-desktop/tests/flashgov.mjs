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
let SEQ = [];
let calls = 0;
function resolve() {
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

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const BRIGHT = "#ffffff", DARK = "#000000";
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

check(`a ${MAX_PER_S + 1}th opposing transition within one second is held, not shown`, () => {
  SEQ = [DARK, BRIGHT]; calls = 0;
  const gov = newFlashGovernor();
  const seen = [];
  // t=0.0, 0.1, 0.2, ... - nine alternating candidates inside one second,
  // one more than the spec's own budget of three opposing transitions.
  for (let i = 0; i <= MAX_PER_S * 2 + 2; i++) {
    seen.push(governedResolve(gov, {}, i * 0.1, 0.0, 0).a);
  }
  const held = seen[seen.length - 1];
  const wouldHaveBeenShown = (MAX_PER_S * 2 + 2) % 2 === 0 ? DARK : BRIGHT;
  assert.notEqual(held, wouldHaveBeenShown,
    `the governor let a transition past its own ${MAX_PER_S}/s budget through`);
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

console.log(`\n${fails.length === 0 ? "all" : fails.length + " of " + (fails.length + 4)} checks ${fails.length === 0 ? "passed" : "failed"}`);
if (fails.length) {
  console.log("failed: " + fails.join(", "));
  process.exit(1);
}
