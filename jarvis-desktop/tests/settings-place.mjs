/**
 * Where Settings was asked to open - the pure half, without a browser.
 *
 * The owner, 2026-10-27: "when i right click the jarvis tray icon, click on
 * update available, it only opens the settings page." The fix has two halves:
 * Rust names a place (`windows.rs`'s `show_settings_at`, the tray's Update row)
 * and the page moves to it (`settings.js`). The part worth testing on its own
 * is the READING of that place - the fragment of a new window, or the fresh
 * `{place, at}` record the quickbar and voice paths already leave behind -
 * because a URL fragment is outsider-controlled text that ends up in a lookup.
 *
 * What has to hold:
 *
 *   - a place is ONE existing element id and nothing else: no slash, dot,
 *     space, `#`, or anything that could reach out of the page;
 *   - a stored place is only good while fresh, so a place left hours ago
 *     cannot move the page when the owner next opens Settings himself;
 *   - unreadable stored text is "no place", never an error;
 *   - the event name Rust emits is the name the page listens for.
 *
 * The Rust half of the last one is pinned from both sides: this file reads
 * `windows.rs`, and that file's own test reads `settings-place.js`.
 *
 * No Playwright, no page - so this suite runs anywhere `node` does.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { PLACE_FRESH_MS } from "../src/plain-errors.js";
import {
  placeFromHash,
  placeFromStored,
  SETTINGS_PLACE_EVENT,
} from "../src/settings-place.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (path) => readFileSync(join(HERE, "..", path), "utf8");

const fails = [];
const check = (name, fn) => {
  try {
    fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

/* ── The fragment of a NEW window ───────────────────────────────────────── */

check("a fragment names the card it is, lower-cased", () => {
  assert.equal(placeFromHash("#updates"), "updates");
  assert.equal(placeFromHash("#Updates"), "updates", "a differently-cased id was refused");
  assert.equal(placeFromHash("updates"), "updates", "a fragment without the '#' was refused");
});

check("a fragment can never name anything but one element id", () => {
  for (const bad of [
    "",
    "#",
    "# updates",
    "#updates?x=1",
    "#../updates",
    "#updates/../secret",
    "#updates#more",
    "#a.b",
    "#1updates",
    `#${"a".repeat(100)}`,
    null,
    undefined,
  ]) {
    assert.equal(placeFromHash(bad), null, `accepted \`${bad}\` as a place`);
  }
});

/* ── The stored record the quickbar and voice already leave ─────────────── */

check("a fresh stored place is taken", () => {
  const now = 1_800_000_000_000;
  assert.equal(
    placeFromStored(JSON.stringify({ place: "updates", at: now - 1000 }), now),
    "updates",
  );
  assert.equal(
    placeFromStored(JSON.stringify({ place: "Updates", at: now }), now),
    "updates",
    "a stored id with different casing was refused",
  );
});

check("a stale stored place is not", () => {
  const now = 1_800_000_000_000;
  assert.equal(
    placeFromStored(JSON.stringify({ place: "updates", at: now - PLACE_FRESH_MS }), now),
    null,
    "a place exactly at the freshness limit was still applied",
  );
  assert.equal(
    placeFromStored(JSON.stringify({ place: "updates", at: now - PLACE_FRESH_MS - 1 }), now),
    null,
    "a stale place moved the page",
  );
  // A record with no time at all is not "fresh by accident".
  assert.equal(placeFromStored(JSON.stringify({ place: "updates" }), now), null);
});

check("an unreadable record is no place, never an error", () => {
  for (const bad of [
    null,
    undefined,
    "",
    "null",
    "{",
    "[]",
    '"updates"',
    JSON.stringify({ place: 5, at: Date.now() }),
    JSON.stringify({ place: "../updates", at: Date.now() }),
    JSON.stringify({ place: "a b", at: Date.now() }),
    JSON.stringify({ nope: true }),
  ]) {
    assert.equal(placeFromStored(bad), null, `accepted \`${bad}\``);
  }
});

/* ── The event name, in both languages ──────────────────────────────────── */

check("Rust and the page spell the event the same way", () => {
  assert.equal(SETTINGS_PLACE_EVENT, "settings-place");
  const rust = read("src-tauri/src/windows.rs");
  assert.match(
    rust,
    new RegExp(`SETTINGS_PLACE_EVENT: &str = "${SETTINGS_PLACE_EVENT}"`),
    "windows.rs does not emit the event this module listens for",
  );
  // The place and the page must still agree about where it lands.
  assert.match(rust, /SETTINGS_PLACES: \[&str; 1\] = \["updates"\]/,
    "windows.rs no longer names exactly the Updates place");
  const html = read("src/settings.html");
  assert.match(html, /<section class="card" id="updates">/,
    "there is no `updates` card for the place to land on");
});

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nsettings places are read safely");
process.exit(fails.length ? 1 : 0);
