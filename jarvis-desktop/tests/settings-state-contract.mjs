/**
 * The state-drift contract: every Settings row whose state another writer can
 * move must have a refresh path (2026-11-19 audits).
 *
 *   node tests/settings-state-contract.mjs
 *
 * WHY THIS EXISTS. DESKTOP-STATE-DRIFT.md's section 4 is the structural
 * finding, not the row list: the row-contract suites only see
 * `<label class="toggle">` rows, so the measured Wi-Fi switch - one of exactly
 * four `<label class="mn-sync-row">` switches - had no test at all. Section 5
 * asks for one browser-free table test whose assertions each fail on today's
 * code:
 *
 *  - a carded ON switch whose Rust call can give up before the card does must
 *    re-read after the card is answered (`wifi-reconnect-switch`, `hf-enabled`);
 *  - a row with a second writer (a chat sentence, another window, the HUD's own
 *    menu, Windows' Task Manager) must not refresh "none";
 *  - a row backed by two stores must not paint from one of them.
 *
 * This file is that table, for the rows the audit proved wrong or fragile. It
 * is deliberately a SOURCE contract (what mechanism the row has), while the
 * behaviour suites (`read-aloud-settings.mjs`, `handsfree-late-card.mjs`,
 * `voice-one-moment.mjs`, `settings-supervise.mjs`) drive the real modules.
 * The last block is the blind-spot closer: every `mn-sync-row` id in the real
 * page must appear here with a stated reason, so a new one cannot slip in
 * unseen - which is how the Wi-Fi row shipped.
 *
 * Run by CI's frontend shards (`tests/*.mjs`); needs no browser.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const page = read("../src/settings.html");
const source = (name) => read(`../src/${name}`);

/** `wifi` etc. - the mechanism the audit's section 5 calls a refresh path. */
const LIVE = "liveRow (queue, the PC's event kind, visibility, bounded steady poll)";

/**
 * One row per control. `refresh` is what keeps the rendered value equal to the
 * state after another writer moves it; the assertion for each kind is below.
 *
 * `carded` - turning it ON raises an approval card whose wait can outlast the
 * Rust call (the audit's "carded ON" class).
 */
const ROWS = [
  {
    id: "wifi-reconnect-switch",
    module: "wifi-reconnect-settings.js",
    refresh: LIVE,
    kind: "live",
    carded: true,
    kinds: ["wifi_reconnect"],
    because: "the PC's value; a chat sentence moves it, and its card can be answered after the 20 s call (audit 3.4)",
  },
  {
    id: "hud-read-replies",
    module: "read-aloud-settings.js",
    refresh: LIVE,
    kind: "live",
    kinds: ["read_aloud"],
    because: "the PC's value; a chat/Live sentence writes the SAME switch (audit 3.3)",
  },
  {
    id: "hf-enabled",
    module: "handsfree-settings.js",
    refresh: LIVE + " + an unconfirmed tick while its card waits",
    kind: "live-waiting",
    carded: true,
    because: "the Rust call waits 20 s against the card's 900 s gate (audit 3.2)",
  },
  {
    id: "voice-one-moment",
    module: "settings.js",
    refresh: "one reader of BOTH stores (this window's localStorage AND the PC's voice-flow.json)",
    kind: "two-store",
    because: "the behaviour ANDs the two; the row painted one and claimed both (audit 3.1)",
  },
  {
    id: "supervise",
    module: "settings.js",
    refresh: "the tick is repainted from the PC's store on a supervision save, refused or not",
    kind: "failed-save",
    because: "a failed save left the tick over 'Jarvis Desktop is not managing Jarvis' (audit 3.5)",
  },
  {
    id: "sp-switch",
    module: "look-settings.js",
    refresh: LIVE,
    kind: "live",
    because: "a chat sentence changes Picture mode too; the page read once (audit 3.7)",
  },
  {
    id: "pc-switch",
    module: "pictures-settings.js",
    refresh: LIVE,
    kind: "live",
    because: "a chat sentence changes 'Making pictures'; the page read once (audit 3.7)",
  },
  {
    id: "ch-switch",
    module: "chat-history-settings.js",
    refresh: LIVE,
    kind: "live",
    because: "Brain -> History and the phone change the same switch; the page read once (audit 3.7)",
  },
  {
    id: "bc-switch",
    module: "big-coder-settings.js",
    refresh: LIVE,
    kind: "live",
    because: "a chat sentence changes it; the page read once (audit 3.7)",
  },
  {
    id: "hud-layout-list",
    module: "hud-window-settings.js",
    refresh: LIVE + " + the Rust store's own jarvis:hud-layout-changed event",
    kind: "live-layout",
    because: "the HUD's own Layouts menu writes the same store (audit 3.7)",
  },
  {
    id: "autostart",
    module: "settings.js",
    refresh: LIVE,
    kind: "live",
    because: "Windows' Task Manager changes the registry behind the page (audit 3.7)",
  },
  // The four mn-sync rows that are NOT our class, carrying the reason they are
  // not (the audit's own MATCH rows; this is what closes the blind spot).
  {
    id: "mn-sync",
    module: "manner-settings.js",
    refresh: "one PC store, read on load and re-read after every write; focus reload",
    kind: "single-reader",
  },
  {
    id: "hud-read-aloud-icons",
    module: "hud-window-settings.js",
    refresh: "a local store with one writer; the HUD listens for its storage event and applies it live",
    kind: "local-single-writer",
  },
];

const byId = new Map(ROWS.map((row) => [row.id, row]));

test("the four mn-sync-row switches in the real page are all in the table", () => {
  // The blind spot DESKTOP-STATE-DRIFT.md section 4 found: the row-contract
  // suites match only `<label class="toggle">`, and the measured Wi-Fi switch
  // is a `.mn-sync-row`. Every one of these must be a stated decision here.
  const ids = [...page.matchAll(/<label class="mn-sync-row">[\s\S]{0,300}?<input[^>]*\bid="([^"]+)"/g)]
    .map((match) => match[1]);
  assert.equal(ids.length, 4,
    `the page now has ${ids.length} mn-sync-row switches; the audit found exactly four`);
  for (const id of ids) {
    assert.ok(byId.has(id),
      `a mn-sync-row switch is not in this table, so nothing holds it to a state: ${id}`);
  }
});

test("a row with a second writer has a refresh path, never 'none'", () => {
  // The audit's rule, in one line: `secondWriter` -> `refresh` must not be
  // "none". Every row in this table has a second writer or a carded ON; all of
  // them must name a mechanism, and the mechanism must exist in the module.
  for (const row of ROWS) {
    assert.ok(row.refresh && row.refresh.length > 10,
      `${row.id} claims no refresh path`);
  }
});

test("every row the audit proved WRONG has the small fix it proved", () => {
  for (const row of ROWS) {
    const text = source(row.module);
    if (row.kind === "live" || row.kind === "live-waiting" || row.kind === "live-layout") {
      assert.match(
        text,
        /import\s*\{[^}]*\bliveRow\b[^}]*\}\s*from\s*"\.\/settings-live\.js"/,
        `${row.id}: ${row.module} does not use the ONE refresh rule`,
      );
      assert.match(
        text,
        /liveRow\(\{\s*(?:read\b|[\s\S]{0,120}?\bread:)/,
        `${row.id}: ${row.module} imports the rule but never arms it`,
      );
    }
    if (row.kind === "live" && row.kinds) {
      for (const kind of row.kinds) {
        assert.ok(text.includes(`"${kind}"`),
          `${row.id}: the PC's own ${kind} event is not listened for`);
      }
    }
    if (row.kind === "live-waiting") {
      // A carded ON whose Rust call can give up first: the timeout is a card
      // still waiting, not a failed save, and the tick is never a stale state.
      assert.match(text, /looksLikeATimeout/,
        `${row.id}: the 20 s timeout is still painted as a failed save`);
      assert.match(text, /indeterminate/,
        `${row.id}: a waiting card is drawn as a definite switch position`);
      assert.match(text, /Waiting for your approval/,
        `${row.id}: the waiting line is gone`);
    }
    if (row.kind === "live-layout") {
      assert.match(text, /jarvis:hud-layout-changed/,
        "the HUD's own layout event is not listened for");
    }
    if (row.kind === "two-store") {
      const flow = source("voice-flow.js");
      assert.match(flow, /export function readOneMoment\(/,
        "the ONE reader of the two ANDed stores is missing");
      assert.match(flow, /MOMENT_OFF_ON_THE_PC/,
        "the PC-half-off sentence is missing");
      assert.match(flow, /MOMENT_NOT_CONFIRMED/,
        "the PC-not-answered sentence is missing");
      assert.match(text, /readOneMoment\(loadMoment\(\), pcMomentStatus\)/,
        "the row does not paint from the two-store reader");
    }
    if (row.kind === "failed-save") {
      assert.match(text, /syncSwitch/,
        "the supervision tick is still only painted at boot");
      assert.match(text, /paintBackend\(\{ syncSwitch: true \}\)/,
        "a supervision save still does not repaint the tick from the store");
    }
  }
});

test("the row that started it all keeps the one-reader rule its lane landed", () => {
  // PR #1399 fixed the owner's own Wi-Fi row (tick and words from ONE reader).
  // This file must not quietly go back to two readers, and the late-card
  // half (audit 3.4) must stay attached to it.
  const wifi = source("wifi-reconnect-settings.js");
  assert.match(wifi, /export function readWifi\(/,
    "the Wi-Fi row no longer has ONE resolver for the PC's answer");
  assert.match(wifi, /box\.checked = usable && view\.on === true/,
    "the tick no longer comes from the same read as the words");
  assert.match(wifi, /liveRow\(\{ read: load, kinds: \["wifi_reconnect"\] \}\)/);
  assert.match(wifi, /looksLikeATimeout/);
});

test("the rule states its own numbers, and the 3 s waiting poll is bounded by the gate's window", () => {
  const live = source("settings-live.js");
  assert.match(live, /steadyMs:\s*20000/);
  assert.match(live, /pendingMs:\s*3000/);
  assert.match(live, /900000\s*\+\s*120000/,
    "the waiting poll is not bounded by the gate's 900 s approval window");
  assert.match(live, /export function liveRow\(/);
  assert.match(live, /onQueue\(soon\)/);
  assert.match(live, /visibilitychange/);
});
