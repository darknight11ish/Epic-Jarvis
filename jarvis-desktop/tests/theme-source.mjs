/**
 * One source of truth for the theme colours, on BOTH clients.
 *
 *     node tests/theme-source.mjs
 *
 * WHY. `jarvis-desktop/src/theme.css` and the phone's
 * `ui/theme/Themes.kt` used to carry the same colours typed out twice, and
 * nothing could see them disagree: `tests/continuity.mjs` checks the theme NAMES
 * and blurbs, not the values. A measurement on 2026-10-09 found 36 of 51
 * same-role values had drifted apart (`docs/THEME-VALUE-PARITY-FINDINGS.md`).
 *
 * Both files are now GENERATED from `tokens/themes.tokens.json` by
 * `tools/tokens/build.mjs`, so drift is impossible rather than merely
 * detectable. This suite is the guard:
 *
 *   1. `build.mjs --check` - the committed files still match the token file.
 *      Editing either generated file by hand fails here, and in CI.
 *   2. The token file parses, every alias resolves, and no alias is a cycle.
 *   3. Every phone value that differs from the desktop's carries a WRITTEN
 *      REASON. This is the part worth having a test for: the whole point of the
 *      divergence list is that a difference is a decision, and an undeclared
 *      difference is exactly the bug that got here. A silent override is now a
 *      failing test.
 *   4. The two clients' theme ids still map the way `continuity.mjs` asserts.
 */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const TOKENS = join(ROOT, "tokens", "themes.tokens.json");
const KT = join(ROOT, "jarvis-client", "app", "src", "main", "java", "com", "jarvis", "client", "ui", "theme", "Themes.kt");

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const file = JSON.parse(readFileSync(TOKENS, "utf8"));

/** Every node carrying `$value`, by dotted path. */
const all = new Map();
(function walk(node, trail) {
  if (node === null || typeof node !== "object" || Array.isArray(node)) return;
  if ("$value" in node) { all.set(trail.join("."), node); return; }
  for (const [k, v] of Object.entries(node)) {
    if (k.startsWith("$")) continue;
    walk(v, [...trail, k]);
  }
})(file, []);
all.delete("");

/** Follows `{a.b.c}` to the value it names, refusing a cycle. */
function resolve(node, seen = []) {
  const raw = node.$value;
  if (typeof raw !== "string") return raw;
  const m = /^\{([^}]+)\}$/.exec(raw.trim());
  if (!m) return raw;
  const target = all.get(m[1]);
  assert.ok(target, `alias points at nothing: {${m[1]}}`);
  assert.ok(!seen.includes(m[1]), `alias cycle: ${[...seen, m[1]].join(" -> ")}`);
  return resolve(target, [...seen, m[1]]);
}

check("CONTROL: the generated theme files match the token file", () => {
  // The whole point. Run the real generator in check mode.
  const out = execFileSync(process.execPath, [join(ROOT, "tools", "tokens", "build.mjs"), "--check"], {
    cwd: ROOT,
    encoding: "utf8",
  });
  assert.match(out, /both match/, out.trim());
});

check("both clients' theme files are generated, and say so", () => {
  const css = readFileSync(join(ROOT, "jarvis-desktop", "src", "theme.css"), "utf8");
  const kt = readFileSync(KT, "utf8");
  assert.match(css, /GENERATED - DO NOT EDIT/);
  assert.match(css, /tokens\/themes\.tokens\.json/);
  assert.match(kt, /x-generated|x-generation|GENERATED/i, "Themes.kt does not say it is generated");
});

check("every token resolves: no alias is a cycle and none points at nothing", () => {
  let checked = 0;
  for (const [path, node] of all) {
    if (path.startsWith("meta.")) continue;
    resolve(node);
    checked++;
  }
  assert.ok(checked > 100, `only ${checked} tokens resolved`);
});

check("every phone value that differs from the desktop's carries a written reason", () => {
  // An override with no reason is an undeclared divergence - the bug this whole
  // mechanism exists to prevent. It is not enough that the numbers are stored.
  let overrides = 0;
  for (const [path, node] of all) {
    const phone = node.$extensions?.phone;
    if (!phone) continue;
    overrides++;
    assert.ok(typeof phone.reason === "string" && phone.reason.trim().length >= 20,
      `${path}: the phone override has no reason worth the name`);
    assert.ok(phone.$value !== undefined, `${path}: the phone override has no value`);
  }
  assert.ok(overrides >= 20, `expected the measured divergence list in the tokens, found ${overrides}`);
});

check("a declared override is genuinely different from the shared value", () => {
  // The other half: an override that matches the shared value is noise that
  // makes the divergence list unreadable, and hides a real one. The ONE
  // exception is the face's well: the phone owns it as a theme token and the
  // desktop's face ground is a spec constant, so the phone's value is stored
  // even where the two happen to be the same colour. It is named here on
  // purpose - a second exception should have to be added deliberately.
  const DELIBERATE = new Set(["themes.deep-space.well", "themes.paper.well"]);
  for (const [path, node] of all) {
    const phone = node.$extensions?.phone;
    if (!phone || typeof phone.$value !== "string") continue;
    if (DELIBERATE.has(path)) continue;
    const shared = String(resolve(node)).trim().toLowerCase();
    let declared = phone.$value.trim().toLowerCase();
    const m = /^\{([^}]+)\}$/.exec(declared);
    if (m) declared = String(resolve(all.get(m[1]))).trim().toLowerCase();
    const hex = (v) => {
      const rgb = /^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/.exec(v);
      if (rgb) return "#" + rgb.slice(1).map((n) => Number(n).toString(16).padStart(2, "0")).join("");
      return v;
    };
    assert.notEqual(hex(declared), hex(shared), `${path}: the phone override repeats the shared value`);
  }
});

check("the theme ids still map the way the two apps already agreed", () => {
  const desktop = file.meta.$themeIds.desktop.$value;
  const phone = file.meta.$themeIds.phone.$value;
  assert.deepEqual(desktop, ["deep-space", "paper", "high-contrast"]);
  assert.deepEqual(phone, ["reactor", "daylight", "contrast"]);
  for (const id of desktop) {
    assert.ok(file.themes[id], `${id} has no theme block`);
    assert.ok(file.themes[id].phoneId?.$value, `${id} names no phone theme`);
  }
  // The mapping itself, which continuity.mjs also holds: same order, so the
  // second desktop theme is the second phone theme.
  assert.deepEqual(desktop.map((d) => file.themes[d].phoneId.$value), phone);
});

console.log(fails.length
  ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nthe two clients' themes come from one file, and every difference is a written decision");
process.exit(fails.length ? 1 : 0);
