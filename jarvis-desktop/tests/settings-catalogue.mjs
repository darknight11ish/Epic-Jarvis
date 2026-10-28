/**
 * settings-catalogue.mjs - holds the generated settings catalogue to BOTH the
 * shared fixture and the real Settings page.
 *
 * Runs on plain Node with no browser:
 *
 *     node tests/settings-catalogue.mjs
 *
 * WHY THIS EXISTS. `backend/jarvis_settings_registry.py`'s SETTINGS_ROWS is
 * the one table behind the desktop page's 26 switch rows, the fixture both
 * apps read, and the phone's SettingsCatalog.kt
 * (tools/gen_settings_cases.py). Until this file, nothing checked the page
 * against that table at row level, and **row ORDER was not protected at
 * all**: a switch that moved to another card, or was renamed, could ship
 * silently as long as some other string-level test happened to mention it.
 *
 * So this test reads src/settings.html as text, pulls every
 * `<label class="toggle">` row out of it in page order, and requires each one
 * to BE the catalogue's row for that position - ids, attributes, label, detail
 * span, the lot. Reordering two rows, renaming one, dropping one or adding one
 * all fail here.
 *
 * What it does NOT prove: that the switches WORK (that needs the app running),
 * or that a row's words are what the owner ends up reading. Eleven rows get
 * their visible words from the PC at read time; for those the fixture says
 * `fallback: true` and this file only requires the page to keep showing the
 * same fallback words.
 *
 * It DOES prove one thing the order alone could not: that each row is drawn
 * INSIDE the card its `section` names (2026-10-28, the settings audit's G3 -
 * `supervise` was drawn in the Pictures card while the registry, the generated
 * fixture and every checker said "Starting Jarvis for you").
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as C from "../src/settings-catalog.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const FIX = JSON.parse(read("tests/fixtures/settings-cases.json"));
const HTML = read("src/settings.html");

const fails = [];
const check = async (name, fn) => {
  try {
    await fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

/* ── Reading the page's toggle rows, as text ─────────────────────────────── */

const words = (s) => s.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();

/** The `<span ...>` opening at `at`, and the offset of its matching close.
 *
 * Depth matters: the label reads `<span><span id="...">words</span><span
 * class="toggle-detail">…</span></span>`, so a lazy regex stops at the INNER
 * close and reports the outer span as empty. Returns
 * `{ tag, body, end }`, where `end` is the offset just past the `</span>`. */
function spanAt(html, at) {
  const gt = html.indexOf(">", at);
  const tag = html.slice(at, gt + 1);
  let i = gt + 1;
  let depth = 1;
  while (depth > 0) {
    const open = html.indexOf("<span", i);
    const close = html.indexOf("</span>", i);
    if (close < 0) throw new Error("unbalanced <span>");
    if (open >= 0 && open < close) {
      depth += 1;
      i = open + 5;
    } else {
      depth -= 1;
      if (depth === 0) return { tag, body: html.slice(gt + 1, close), end: close + 7 };
      i = close + 7;
    }
  }
  throw new Error("unbalanced <span>");
}

/** Every `<label ... class="toggle ...">` row on the page, in page order. */
function pageRows() {
  const out = [];
  const open = /^([ \t]*)<label([^>]*\bclass="toggle[^"]*"[^>]*)>[ \t]*$/gm;
  let m;
  while ((m = open.exec(HTML)) !== null) {
    const indent = m[1].length;
    const labelAttrs = m[2];
    // A toggle row never nests another <label>, so the first </label> after
    // it closes it.
    const end = HTML.indexOf("</label>", m.index) + "</label>".length;
    const lineEnd = HTML.indexOf("\n", end);
    const body = HTML.slice(m.index, lineEnd < 0 ? HTML.length : lineEnd);
    const attrs = (s) => (s ? s.replace(/\s+/g, " ").trim() : "");
    const input = /<input\b[^>]*>/.exec(body);
    // The wrapper span is the first <span> AFTER the input.
    const inputEnd = input ? body.indexOf(input[0]) + input[0].length : 0;
    const wrapAt = body.indexOf("<span", inputEnd);
    const wrap = spanAt(body, wrapAt);
    // A child span of its own, if the wrapper holds one. The detail span is
    // NOT it: a row can read `<span>words<span class="toggle-detail">…`, and
    // taking that first `<span` would mistake the detail span for the label's.
    const detailAt = wrap.body.indexOf('<span class="toggle-detail"');
    const childAt = wrap.body.indexOf("<span");
    const child = childAt >= 0 && (detailAt < 0 || childAt < detailAt)
      ? spanAt(wrap.body, childAt) : null;
    const detail = detailAt >= 0 ? spanAt(wrap.body, detailAt) : null;
    const id = (s, re) => {
      const g = re.exec(s || "");
      return g ? g[1] : "";
    };
    out.push({
      indent,
      rowId: id(labelAttrs, /\bid="([^"]+)"/),
      hidden: /\bhidden\b/.test(labelAttrs),
      inputId: id(input ? input[0] : "", /\bid="([^"]+)"/),
      inputTag: attrs(input ? input[0] : ""),
      // The label's span: a child one when there is a child, otherwise the
      // wrapper itself (which is how `spd-accept` spells it).
      labelSpanId: child ? id(child.tag, /\bid="([^"]+)"/)
        : id(wrap.tag, /\bid="([^"]+)"/),
      label: words(child ? child.body
        : wrap.body.replace(/<span class="toggle-detail"[\s\S]*$/, "")),
      detailSpanId: detail ? id(detail.tag, /\bid="([^"]+)"/) : null,      detail: detail ? words(detail.body) : null,
      checked: /<input\b[^>]*\bchecked\b/.test(body),
      dataLive: /<input\b[^>]*data-live="true"/.test(body),
      body,
    });
  }
  return out;
}

const PAGE = pageRows();

/* ── 1. The catalogue and the fixture ────────────────────────────────────── */

await check("the catalogue is the fixture, row for row and in order", async () => {
  assert.equal(C.SCHEMA, FIX.schema);
  assert.deepEqual(C.MARKERS, FIX.markers);
  assert.equal(C.ROWS.length, FIX.rows.length);
  assert.deepEqual(C.COUNTS, FIX.counts);
  for (let i = 0; i < FIX.rows.length; i++) {
    assert.deepEqual(C.ROWS[i], FIX.rows[i], `row ${i + 1} (${FIX.rows[i].id})`);
  }
});

await check("the fixture says how many rows there are, and it is 31 desktop toggles", async () => {
  assert.equal(FIX.counts.desktop, 31);
  assert.equal(FIX.rows.filter((r) => r.owner === "desktop").length, 31);
  assert.equal(FIX.counts.phone, 3);
  assert.equal(FIX.counts.all, 34);
  // The number this whole feature was briefed with was wrong once already
  // ("all 19"): the 19 is the count of rows with a BARE `<label class="toggle">`,
  // and the seven rows that also carry a label id were left out of it.
  // "Click through to what is behind" (2026-10-10) is a bare one, so both
  // numbers moved by one together.
  // "Making pictures" (2026-10-11, JARVIS-API section 124) is a bare one too,
  // so both moved by one again - 20 to 21, 27 to 28.
  // "Data and maths sandbox" (LM-1C, 2026-10-18) is a bare one as well: 21 to
  // 22, 28 to 29 (and two phone rows to three).
  // The two Learning rows (2026-10-28, the settings audit's G1) are bare too:
  // 22 to 24, 29 to 31 (and three phone rows stay three).
  const bare = (HTML.match(/^[ \t]*<label class="toggle">[ \t]*$/gm) || []).length;
  assert.equal(bare, 24, "the bare-label count moved - re-read the 31 claim");
  assert.equal(FIX.counts.desktop, bare + 7);
});

await check("exactly one row is flagged as not being a setting", async () => {
  const notSettings = FIX.rows.filter((r) => !r.setting_row).map((r) => r.id);
  assert.deepEqual(notSettings, ["spd-accept"]);
  // ...and it is the spending screen's hidden accept-all control, not a switch.
  assert.equal(FIX.rows.find((r) => r.id === "spd-accept").hidden, true);
});

/* ── 2. The page really has those rows, in that order ────────────────────── */

await check("the page has one toggle row per catalogue row, in order", async () => {
  const want = FIX.rows.filter((r) => r.owner === "desktop").map((r) => r.id);
  assert.deepEqual(PAGE.map((r) => r.inputId), want);
});

/* ── 2b. The row really sits INSIDE the card its `section` names ─────────── */

/**
 * The ids of the `<section>`/`<details>` containers open at `at`, nearest
 * first. A row's `section` is a card id (`start-jarvis`) or the "More options"
 * drawer (`more-options`, which is a `<details>` holding cards of its own), so
 * walking every open container - not just the nearest - is what makes both
 * spellings checkable: `autostart` is inside `start-jarvis` INSIDE
 * `more-options`, and both are true.
 *
 * Nothing else checked this before: the fixture's `section` field was copied
 * from the registry into the catalogue, but a row could be drawn inside a
 * different card while the registry said otherwise - which is exactly how
 * `supervise` ("Let Jarvis Desktop start and stop Jarvis") came to live inside
 * the Pictures card while every checker agreed it was in "Starting Jarvis for
 * you", and the Pictures body being hidden could hide the switch (2026-10-28
 * settings audit, G3).
 */
function containerIds(html, at) {
  const re = /<(\/?)(section|details)\b([^>]*)>/g;
  const stack = [];
  let m;
  while ((m = re.exec(html)) && m.index < at) {
    if (m[1] === "/") {
      for (let i = stack.length - 1; i >= 0; i--) {
        if (stack[i].tag === m[2]) {
          stack.splice(i, 1);
          break;
        }
      }
    } else {
      const id = /\bid="([^"]+)"/.exec(m[3]);
      stack.push({ tag: m[2], id: id ? id[1] : "" });
    }
  }
  return stack.map((s) => s.id).filter(Boolean);
}

await check("every row is drawn inside the card its section names", async () => {
  for (const c of FIX.rows.filter((r) => r.owner === "desktop")) {
    const at = HTML.indexOf(`id="${c.input}"`);
    assert.ok(at > 0, `${c.id}: its <input> is not on the page`);
    const chain = containerIds(HTML, at);
    assert.ok(
      chain.includes(c.section),
      `${c.id} is not inside #${c.section} - it is inside ${chain.join(" < ") || "(no card)"}`,
    );
  }
});

/* ── 2c. The read-aloud feature names controls that really exist ─────────── */

/**
 * The 2026-10-28 settings audit's G2: `features/features.json` told the owner
 * "Settings, Voice, \"Read aloud\"" - a switch that does not exist. Read-aloud
 * is on by default and no switch turns it off; the Voice card's real controls
 * are two choices ("Answers that use what Jarvis remembers" / "Answers that
 * use sensitive saved facts"), and the HUD card's "Read-aloud buttons on
 * answers" row adds a speaker to a finished answer WITHOUT turning read-aloud
 * on or off.
 *
 * So this holds the prose to the page, not to another sentence: every quoted
 * control the row names must exist in settings.html, and the row must say what
 * the HUD row is not. A future rewrite that points at a control nobody built
 * fails here.
 */
await check("read-aloud names real Settings controls, and says what the HUD row is not", async () => {
  const FEATURES = JSON.parse(read("../features/features.json"));
  const row = FEATURES.find((f) => f.id === "read-aloud");
  assert.ok(row, "read-aloud is not in features/features.json");
  assert.ok(/Read-aloud buttons on answers/.test(row.where),
    "the HUD row's own words are not named");
  assert.ok(/does not turn read-aloud on or off/.test(row.where),
    "the row no longer says the HUD buttons are not the switch");
  assert.ok(!/Settings, Voice, "Read aloud"/.test(row.where),
    "the old claim (a Voice switch called \"Read aloud\") is back");
  const quoted = [...row.where.matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  assert.ok(quoted.length >= 3, `only ${quoted.length} control(s) named: ${quoted}`);
  for (const name of quoted) {
    assert.ok(HTML.includes(name), `settings.html has no control called "${name}"`);
  }
  // The HUD row is a real <input>, and it is not a read-aloud switch: its own
  // detail says it adds the speaker a finished answer can be read out from.
  assert.ok(HTML.includes('id="hud-read-aloud-icons"'), "the HUD read-aloud row is gone");
  assert.ok(/speaker/i.test(row.what), "the per-answer speaker is not mentioned");
});

await check("every row's id, span ids, label, detail and attributes match the page", async () => {
  const want = FIX.rows.filter((r) => r.owner === "desktop");
  for (let i = 0; i < want.length; i++) {
    const c = want[i];
    const p = PAGE[i];
    const at = `row ${c.order} (${c.id})`;
    assert.equal(p.inputId, c.input, `${at}: input id`);
    // The whole tag, built from the fixture's own flags - which is what makes
    // this catch a `checked` or `data-live` that drifted, not just the id.
    assert.equal(p.inputTag, c.input_open ||
      `<input id="${c.input}" type="checkbox"${c.checked ? " checked" : ""}` +
      `${c.data_live ? ' data-live="true"' : ""} />`, `${at}: <input> tag`);
    assert.equal(p.indent, c.indent, `${at}: indentation (it moved between cards)`);
    assert.equal(p.rowId, c.row_id || "", `${at}: <label> id`);
    assert.equal(p.labelSpanId, c.label_span || "", `${at}: label span id`);
    assert.equal(p.detailSpanId, c.detail_span, `${at}: detail span id`);
    assert.equal(p.label, words(c.label), `${at}: label words`);
    // The fixture keeps `detail` as a string for every row; the page has no
    // span at all on the five rows with no detail. Both mean "no words".
    assert.equal(p.detail || "", words(c.detail), `${at}: detail words`);
    assert.equal(p.checked, c.checked, `${at}: checked`);
    assert.equal(p.hidden, c.hidden, `${at}: hidden`);
    assert.equal(p.dataLive, c.data_live, `${at}: data-live`);
  }
});

/* ── 3. The rows the PC owns keep their words as a FALLBACK only ─────────── */

await check("ten rows are marked as PC-worded, and they are the right ten", async () => {
  const fallback = FIX.rows.filter((r) => r.fallback).map((r) => r.id);
  assert.deepEqual(fallback, [
    "sky-show", "voice-one-moment", "voice-heard-sound", "mn-humor", "coach-enabled",
    "sec-app-lock", "sec-private", "cv-face-switch", "ws-enabled", "ws-ask",
  ], "the fallback list moved");
  // TEN, and an earlier brief said twelve. The two it should not have counted:
  //
  //   * `cv-better-switch` - its detail is plain markup nothing rewrites
  //     (voice-panel.js touches `cv-better-lines`, `cv-better-why` and
  //     `cv-better-status`, never the detail span).
  //   * `spd-accept` - its span starts EMPTY and a local constant fills it
  //     (spending.js's BOX.acceptTick), so the PC never sends those words.
  //
  // If this fails with 12, someone has re-added one of them. The list is a
  // claim about which rows the PC words, so it is worth being exact about.
  assert.equal(fallback.length, 10);
  assert.ok(!fallback.includes("spd-accept"));
  assert.ok(!fallback.includes("cv-better-switch"));
});

await check("every fallback row still reads its words from the PC, not from here", async () => {
  // The catalogue is a FALLBACK for these rows, never a second owner of what
  // the owner reads. The proof that it is still a fallback is that the module
  // that paints the row is still there and still writes into the same element.
  const sources = {
    "follow-system": null,             // not a fallback row; kept for clarity
    "sky-show": "sky-settings.js",
    "voice-one-moment": "settings.js",
    "voice-heard-sound": "settings.js",
    "mn-humor": "manner-settings.js",
    "coach-enabled": "prompt-coach-settings.js",
    "sec-app-lock": "settings.js",
    "sec-private": "settings.js",
    "cv-face-switch": "voice-panel.js",
    "ws-enabled": "web-search-settings.js",
    "ws-ask": "web-search-settings.js",
  };
  for (const c of FIX.rows.filter((r) => r.fallback)) {
    const file = sources[c.id];
    assert.ok(file, `${c.id}: this test needs to know which module paints it`);
    const el = c.detail_span || c.label_span;
    assert.ok(read(`src/${file}`).includes(el),
      `${c.id}: ${file} no longer touches #${el} - if the PC stopped sending ` +
      `these words, say so in the registry rather than editing the fixture`);
  }
});

await check("a fallback row keeps the page's words even though the PC overwrites them", async () => {
  for (const c of FIX.rows.filter((r) => r.fallback)) {
    const p = PAGE.find((r) => r.inputId === c.id);
    assert.ok(p, `${c.id} is on the page`);
    assert.equal(p.label, c.label, `${c.id}: fallback label`);
  }
});

/* ── 4. The catalogue's own helpers ──────────────────────────────────────── */

await check("row(), SETTING_ROWS and FALLBACK_ROWS agree with the fixture", async () => {
  assert.equal(C.SETTING_ROWS.length, FIX.counts.setting);
  assert.equal(C.FALLBACK_ROWS.length, FIX.counts.fallback);
  assert.equal(C.row("follow-system").label, FIX.rows.find((r) => r.id === "follow-system").label);
  assert.equal(C.row("no-such-row"), undefined);
});

await check("the three phone rows carry their own words and their Settings key", async () => {
  const phone = FIX.rows.filter((r) => r.owner === "phone");
  assert.deepEqual(phone.map((r) => r.id), ["watch-notify", "phone-notify", "sandbox"]);
  for (const r of phone) {
    assert.equal(r.phone_key, r.id, `${r.id}: phone_key`);
    assert.ok(r.label.length > 0 && r.detail.length > 0, `${r.id}: words`);
    assert.ok(r.label_span === null && r.detail_span === null, `${r.id}: no desktop spans`);
    assert.ok(r.source, `${r.id}: names the Kotlin its words came from`);
  }
});

/* ── 5. The markers the generator splices between ────────────────────────── */

await check("the page carries both markers, and they are bare HTML comments", async () => {
  assert.ok(HTML.includes(FIX.markers.begin), "begin marker");
  assert.ok(HTML.includes(FIX.markers.end), "end marker");
  // BEGIN's text names the end marker's first word, so the count of the END
  // marker's own full text is what proves there are not two of them.
  assert.equal(HTML.split(FIX.markers.end).length - 1, 1, "exactly one end marker");
  assert.equal(HTML.split(FIX.markers.begin).length - 1, 1, "exactly one begin marker");
  // Bare at the first row's own indent: wrapping the rows in an element would
  // change what `.card > :not(h2)` matches in settings.css.
  const line = HTML.slice(HTML.indexOf(FIX.markers.begin)).split("\n")[0];
  assert.equal(line.trim(), FIX.markers.begin, "the begin marker owns its line");
});

await check("the markers bracket every toggle row, and only the rows", async () => {
  const begin = HTML.indexOf(FIX.markers.begin);
  const end = HTML.indexOf(FIX.markers.end, begin + FIX.markers.begin.length);
  assert.ok(begin < end, "begin comes before end");
  for (const c of FIX.rows.filter((r) => r.owner === "desktop")) {
    const at = HTML.indexOf(`id="${c.input}"`);
    assert.ok(begin < at && at < end, `${c.id} sits between the markers`);
  }
  // The rows are NOT one contiguous run - the page has other markup between
  // them (the theme radios between rows 1 and 2, "Thinking levels" between 7
  // and 8, and so on) - so the markers bracket the whole stretch the rows live
  // in, and the generator replaces each row in place. What this proves is that
  // no toggle row escaped the markers: the count of rows outside them is zero.
  const outside = pageRows().filter((r) => {
    const at = HTML.indexOf(`id="${r.inputId}"`);
    return at < begin || at > end;
  });
  assert.deepEqual(outside.map((r) => r.inputId), []);
});

/* ── Done ────────────────────────────────────────────────────────────────── */

console.log("");
if (fails.length) {
  console.log(`${fails.length} failed:`);
  for (const f of fails) console.log(`  - ${f}`);
  process.exit(1);
}
console.log(`all ok (${PAGE.length} toggle rows on the page)`);
