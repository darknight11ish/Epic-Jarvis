/**
 * Every tray menu row is either handled or provably inert - nothing in between.
 *
 * WHY THIS EXISTS
 *
 * `tray.rs` builds ~26 rows and dispatches them with a `match` whose last arm is
 *
 *     other => eprintln!("[jarvis] tray: unhandled menu id `{other}`"),
 *
 * So a row wired into the menu but never added to the match COMPILES, appears in
 * the right-click menu, and does nothing at all when clicked. The only trace is
 * one line on stderr that nobody reads. That is the worst shape this bug could
 * have: it looks finished on screen, and the existing tray tests cannot see it,
 * because each of them asserts ONE named row (features.mjs on
 * `ID_SHOW_FEATURES`, look-rules.mjs on `ID_WATCH`, hotkeys.mjs on
 * `ID_STOP_EVERYTHING`) rather than all of them.
 *
 * This is a static check on the source. It needs no browser and no backend, which
 * matters because the tray is otherwise only testable by right-clicking it.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const tray = read("src-tauri/src/tray.rs");

/* Rows that REPORT and never act. Each must be built with `false` for enabled, or
 * it is a clickable row that does nothing - a bug rather than a status line.
 * Written out by name on purpose: adding a new inert row should be a deliberate
 * edit to this list, because this list is the claim. */
const INERT = [
  "ID_STATUS_ACTIVITY",
  "ID_STATUS_POWER",
  "ID_UPDATE",
];

/* Rows that carry state and are re-labelled in place, so they must be held in
 * `Rows`; a row that is rebuilt instead goes visually stale and no test sees it.
 *
 * `ID_STATUS_ACTIVITY` and `ID_STATUS_POWER` are deliberately NOT here: they are
 * built once from the link and then only ever disabled/enabled, never re-worded,
 * and the check below proved it - they are the only two the `Rows` literal does
 * not hold. `ID_UPDATE` IS here, because its version text and its enabled state
 * both move. */
const STATEFUL = [
  "ID_APPROVALS",
  "ID_WAITING",
  "ID_MUTE",
  "ID_LIVE",
  "ID_WATCH",
  "ID_BACKEND",
  "ID_UPDATE",
  "ID_STOP_EVERYTHING",
  "ID_TOGGLE_SPOTLIGHT",
  "ID_TOGGLE_WIDGET",
  "ID_TOGGLE_FLOATING",
];

/* ── the constants ──────────────────────────────────────────────────────── */
const consts = [];
for (const m of tray.matchAll(/^const (ID_[A-Z0-9_]+): &str = "([^"]+)";$/gm)) {
  consts.push({ name: m[1], id: m[2] });
}

check("tray.rs declares its menu ids", () => {
  assert.ok(consts.length >= 20, `found only ${consts.length}`);
});

/* ── the dispatch match, with comments stripped ─────────────────────────── */
const fnAt = tray.indexOf("fn handle_menu_event");
const body = fnAt === -1 ? "" : tray.slice(fnAt, tray.indexOf("\n}\n", fnAt));
const noComments = body.replace(/\/\/[^\n]*/g, "");

const dispatched = new Set();
for (const line of noComments.split("\n")) {
  const arm = line.match(/^\s*(ID_[A-Z0-9_]+(?:\s*\|\s*ID_[A-Z0-9_]+)*)\s*=>/);
  if (arm) for (const n of arm[1].split("|")) dispatched.add(n.trim());
}

check("handle_menu_event is present and dispatches most ids", () => {
  assert.notEqual(fnAt, -1, "handle_menu_event is gone from tray.rs");
  assert.ok(dispatched.size >= 18,
    `only ${dispatched.size} dispatched: ${[...dispatched].join(", ")}`);
});

/* ── 1. handled, or on the inert list ───────────────────────────────────── */
check("every menu id is handled by the match, or is on the INERT list", () => {
  const inertSet = new Set(INERT);
  const unhandled = consts
    .map((c) => c.name)
    .filter((n) => !inertSet.has(n) && !dispatched.has(n));
  assert.deepEqual(unhandled, [],
    `these rows exist in the menu and are dispatched by nothing, so clicking ` +
    `them does nothing: ${unhandled.join(", ")}`);
});

/* ── 2. no stale arm ────────────────────────────────────────────────────── */
check("every match arm names a constant that actually exists", () => {
  const known = new Set(consts.map((c) => c.name));
  const stale = [...dispatched].filter((n) => !known.has(n));
  assert.deepEqual(stale, [], `arms with no constant: ${stale.join(", ")}`);
});

/* ── 3. the INERT rows are really built disabled ────────────────────────── */
for (const name of INERT) {
  check(`${name} is built with enabled = false`, () => {
    const marker = tray.indexOf(`${name},`);
    assert.notEqual(marker, -1, `${name} is never used to build a row`);
    const slice = tray.slice(marker, marker + 400);
    assert.match(slice, /\n\s*false,\s*\n/,
      `${name} looks like a status row but is not built disabled, so it is a ` +
      `clickable row that does nothing`);
  });
}

/* ── 4. the STATEFUL rows are held in `Rows` ────────────────────────────── */
check("every stateful row is held in `Rows`, so it can be re-labelled in place", () => {
  const rowsAt = tray.indexOf("Rows {");
  assert.notEqual(rowsAt, -1, "the Rows struct literal is gone");
  const rowsBody = tray.slice(rowsAt, tray.indexOf("})", rowsAt));
  const fields = [...rowsBody.matchAll(/^\s*([a-z_]+),$/gm)].map((m) => m[1]);
  const missing = STATEFUL
    .map((n) => n.replace("ID_", "").toLowerCase())
    .filter((f) => !fields.includes(f));
  assert.deepEqual(missing, [],
    `not held in Rows: ${missing.join(", ")} (Rows holds: ${fields.join(", ")})`);
});

console.log(`\n${consts.length} tray ids, ${dispatched.size} dispatched, ` +
  `${INERT.length} declared inert, ${STATEFUL.length} stateful`);
console.log(fails.length ? `\n${fails.length} failed` : "\n0 failed");
process.exit(fails.length ? 1 : 0);
