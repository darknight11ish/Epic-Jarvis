/**
 * Generate golden vectors for resolve(binding, t, amp, seed).
 *
 * WHY THIS EXISTS
 * `resolve` has three implementations — faces.html (JS), spec.rs (Rust) and
 * the Kotlin client — of a function the visual spec itself calls "the
 * contract". They agree today by discipline: somebody ported carefully and
 * somebody else read the port. Nothing detects the day one of them drifts,
 * and the failure mode is silent, because a slightly wrong colour still
 * renders.
 *
 * This runs the JS implementation, which is the original the other two are
 * ports of, over a fixed matrix of inputs and writes what it produced. The
 * other two can then assert against the same file.
 *
 * THE ONE THING THAT CANNOT BE PINNED, AND WHY IT IS MARKED RATHER THAN HIDDEN
 * `hash01(n)` is `sin(n * 127.1) * 43758.5453`, fractional part. The high bits
 * of that product are discarded, so the result amplifies the last bits of the
 * platform sine — which is not specified to be identical across libm, V8 and
 * Rust's std. spec.rs already says so in a comment: it is a noise source, and
 * its DISTRIBUTION is the contract, not its exact value.
 *
 * So vectors for the `flicker` kind carry `"exact": false`. A port should
 * assert those within a tolerance, or assert only that the output is a legal
 * colour. Pretending they are exact would produce a test that fails on a
 * correct implementation, which is worse than no test.
 *
 *     node scripts/build-resolve-vectors.mjs
 */
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "..", "jarvis-desktop", "src");

// The spec, exactly as the window gets it.
globalThis.window = {};
new Function(readFileSync(join(src, "faces-spec.js"), "utf8")).call(globalThis);
const SPEC = globalThis.window.JARVIS_SPEC;
if (!SPEC) throw new Error("faces-spec.js did not set window.JARVIS_SPEC");

// The pattern engine, lifted from faces.html by its own section markers rather
// than by line number — line numbers in that file have moved before.
const html = readFileSync(join(src, "faces.html"), "utf8");
const start = html.indexOf("const CMAP = {};");
const endMark = "\n/* ======================================================================";
const end = html.indexOf(endMark, html.indexOf("function resolve(bind, t, amp, seed)"));
if (start < 0 || end < 0) throw new Error("could not locate the pattern engine in faces.html");
const engine = html.slice(start, end);
if (!engine.includes("function resolve(")) throw new Error("the slice does not contain resolve()");

// Helpers resolve() reaches for that live outside the section markers. Pulled
// by name rather than by proximity, and the build fails loudly if one moves or
// is renamed — a silently missing helper would be a ReferenceError at generate
// time, but a silently WRONG one would poison every vector in the file.
const NEEDED = ["parseCol", "mix"];
const ARROWS = ["lerp"];        // one-liners, declared as consts
const helpers = [
  ...ARROWS.map((name) => {
    const m = html.match(new RegExp(`\\nconst ${name} = [^\\n]+`));
    if (!m) throw new Error(`could not find const ${name} in faces.html`);
    return m[0];
  }),
  ...NEEDED.map((name) => {
    const m = html.match(new RegExp(`\\nfunction ${name}\\([\\s\\S]*?\\n}`));
    if (!m) throw new Error(`could not find ${name}() in faces.html`);
    return m[0];
  }),
].join("\n");

const resolve = new Function("SPEC", `
  // parseCol memoises into a module-level Map added during the frame-rate work.
  const _COL_MEMO = new Map();
  ${helpers}
  ${engine}
  return resolve;
`)(SPEC);

/* -- the matrix ---------------------------------------------------------- */
// Times chosen to land on and off the period boundaries every cyclic kind
// has, so a port that is off by a half-phase fails rather than passing at
// t = 0 where most of them agree by accident.
const TIMES = [0, 0.37, 1.0, 2.5, 3.14159, 6.0, 11.7];
const AMPS = [0.0, 0.42, 1.0];
const SEEDS = [0.0, 7.0];

// A real palette id, taken from the spec rather than typed from memory.
const OVERRIDE_ID = (SPEC.palette.colors.find(c => c.family === "ember") || SPEC.palette.colors[1]).id;

/** Attach the invariant that stands in for equality when the value cannot be
 *  pinned. Applied centrally so a non-exact vector cannot be added without
 *  one — an unassertable vector with nothing to assert instead is dead weight
 *  that reads like coverage. */
function decorate(v, pattern) {
  if (v.exact) return v;
  const fam = v.bind.family || pattern?.params?.family || "ember";
  v.holds = {
    rule: "both colours are entries in the family ramp, and b is the entry two "
        + "steps below a, floored at the start of the ramp",
    family: fam,
    ramp: SPEC.palette.colors.filter(c => c.family === fam).map(c => c.hex),
  };
  return v;
}

const vectors = [];
for (const pattern of SPEC.patterns) {
  const exact = pattern.kind !== "flicker";
  for (const t of TIMES) {
    for (const amp of pattern.kind === "reactive" ? AMPS : [0.0]) {
      for (const seed of pattern.kind === "flicker" ? SEEDS : [0.0]) {
        const bind = { pattern: pattern.id, params: {} };
        vectors.push(decorate({ bind, t, amp, seed, kind: pattern.kind, exact,
                                expect: resolve(bind, t, amp, seed) }, pattern));
      }
    }
  }
  // A colour override, which is how one pattern serves several states, and
  // the branch a port is most likely to get wrong: `bind.color` beats the
  // pattern's own colour parameter everywhere it appears.
  //
  // It must be a REAL palette id. The first draft of this used "amber", which
  // is a family name and not a colour, and hexOf passes an unknown id through
  // verbatim - so the vector recorded `a: "amber"` and `b: "rgb(0,0,0)"` as
  // the expected output and would have pinned a port to reproduce garbage.
  const over = { pattern: pattern.id, color: OVERRIDE_ID, params: {} };
  vectors.push(decorate({ bind: over, t: 1.0, amp: 0.0, seed: 0.0, kind: pattern.kind,
                 exact,
                 note: pattern.kind === "flicker"
                     ? "flicker IGNORES bind.color and paints from the family ramp. "
                     + "A port that applies the override here is wrong."
                     : "bind.color overrides the pattern's own colour",
                 expect: resolve(over, 1.0, 0.0, 0.0) }, pattern));

  // And a literal hex, which hexOf supports on purpose: an id it does not know
  // is returned unchanged, so `bind.color = "#ff0000"` works. A port that
  // looks the id up and gives up on a miss breaks this.
  const lit = { pattern: pattern.id, color: "#ff0000", params: {} };
  vectors.push(decorate({ bind: lit, t: 1.0, amp: 0.0, seed: 0.0, kind: pattern.kind,
                 exact, note: "a literal hex passes through hexOf unchanged",
                 expect: resolve(lit, 1.0, 0.0, 0.0) }, pattern));
}

// An unknown pattern id must fall back to SPEC.patterns[0], not throw and not
// return the hardcoded cyan. Both ports have a separate branch for this.
const unknown = { pattern: "no-such-pattern-exists", params: {} };
vectors.push({ bind: unknown, t: 1.0, amp: 0.0, seed: 0.0,
               kind: "__unknown_id__", exact: SPEC.patterns[0].kind !== "flicker",
               note: "falls back to SPEC.patterns[0]. NOT DISCRIMINATING on this "
                   + "spec: patterns[0] is solid/ice-4 and ice-4 is #6fe3ff, which "
                   + "is also hexOf's own default - so a port that wrongly returns "
                   + "the hardcoded fallback passes this vector anyway. Kept because "
                   + "it still catches a throw, and flagged so nobody reads a pass "
                   + "as proof the fallback is right.",
               expect: resolve(unknown, 1.0, 0.0, 0.0) });

// A binding whose params override the pattern's defaults, key by key.
const pat = SPEC.patterns.find(p => p.params && Object.keys(p.params).length);
if (pat) {
  const key = Object.keys(pat.params).find(k => typeof pat.params[k] === "number");
  if (key) {
    const tuned = { pattern: pat.id, params: { [key]: pat.params[key] * 2 + 1 } };
    vectors.push({ bind: tuned, t: 1.0, amp: 0.0, seed: 0.0, kind: pat.kind,
                   exact: pat.kind !== "flicker", note: `params.${key} overridden`,
                   expect: resolve(tuned, 1.0, 0.0, 0.0) });
  }
}

// Self-check. The fixture is only worth anything if the rule it ships is true
// of the values it ships, and this is cheaper than finding out from a port.
for (const v of vectors) {
  if (v.exact || !v.holds) {
    if (!v.exact) throw new Error(`non-exact vector with no invariant: ${JSON.stringify(v.bind)}`);
    continue;
  }
  const { ramp } = v.holds;
  const i = ramp.indexOf(v.expect.a);
  if (i < 0 || v.expect.b !== ramp[Math.max(0, i - 2)]) {
    throw new Error(`the stated invariant does not hold for ${JSON.stringify(v)}`);
  }
}

const out = {
  generated_from: "jarvis-desktop/src/faces.html resolve(), the implementation the others are ports of",
  spec_version: SPEC.version,
  note: "Vectors with exact:false use hash01(), whose sin() fractional part is not "
      + "bit-portable across V8, libm and Rust std. DO NOT assert a tolerance on these: "
      + "flicker uses the hash to pick an INDEX into a family ramp, so the output is "
      + "discontinuous - a one-ulp difference either changes the colour completely or "
      + "not at all, and 'close' is not a meaningful relation between two ramp entries. "
      + "Assert the structural invariant given in `holds` instead. That invariant IS "
      + "portable and is the actual contract.",
  count: vectors.length,
  exact_count: vectors.filter(v => v.exact).length,
  vectors,
};
writeFileSync(join(here, "..", "jarvis-desktop", "src", "resolve-vectors.json"),
              JSON.stringify(out, null, 2) + "\n");
console.log(`${out.count} vectors (${out.exact_count} exact) across ${SPEC.patterns.length} patterns, spec version ${SPEC.version}`);
