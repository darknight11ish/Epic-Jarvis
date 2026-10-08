/**
 * "Everything Jarvis can do" - the desktop page (docs/FEATURES-LIST-DESIGN.md,
 * the owner's request of 2026-10-08).
 *
 * The page reads `src/features.json` and draws it. The COMPLETENESS of that file
 * - every route section and menu id covered or in the checker's INTERNAL list,
 * every `covers` id still in the code - is proven by
 * `tools/check_feature_list.py`, run in CI through
 * `backend/run_suites.py test_feature_list.py`. What THIS suite proves is that
 * the page draws what the file says, and that there is a real button to open it
 * with:
 *
 *   - every group the file names is listed, in the file's own order, with the
 *     right number of features under it;
 *   - one row per entry and no more - the page's own count equals the file's,
 *     and no id is dropped or doubled;
 *   - within a group this PC's own features come first and the phone's carry
 *     the "on your phone" marker, which is the design note's own rule;
 *   - a row opens (by a real click, and then by every row in turn) and shows
 *     all four fields, word for word from the file;
 *   - a feature whose `limit` is empty draws NO limit line, rather than a line
 *     with nothing on it;
 *   - the settings row and the tray row both reach it, the command behind them
 *     is registered and permitted to Settings and nothing else, the page obeys
 *     the packaged CSP's rules, and the copy the page fetches is the source.
 *
 * The drawing checks use the shared harness (`tests/uikit.mjs`) and wait on the
 * page's own state with `K.until`, never a fixed sleep; the rest read the real
 * files and need no browser.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

/** The list itself - the same file the page fetches. */
const LIST = JSON.parse(read("src/features.json"));
const BY_ID = new Map(LIST.map((e) => [e.id, e]));
/** The groups, in the file's own order: the page must not re-order them. */
const GROUPS = [...new Set(LIST.map((e) => e.group))];
const fileIdsIn = (group) => LIST.filter((e) => e.group === group).map((e) => e.id);
/** A feature with no real limit, for the "no limit line" check. */
const NO_LIMIT = LIST.filter((e) => !e.limit).map((e) => e.id);
const WITH_LIMIT = LIST.filter((e) => e.limit).map((e) => e.id);

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** The page, with the whole list drawn. */
async function opened() {
  const page = await K.open(browser, base, "features.html", {}, { width: 900, height: 1200 });
  await K.until(page, `the feature list to draw all ${LIST.length} rows`, async () =>
    (await page.evaluate(() =>
      document.querySelectorAll("#features-list details.feat-item").length)) === LIST.length);
  return page;
}

/** Each group's drawing order, as the page has it. */
const drawnGroups = (page) => page.evaluate(() =>
  [...document.querySelectorAll("#features-list .features-group")].map((s) => ({
    group: s.dataset.group,
    heading: s.querySelector("h2").textContent,
    note: s.querySelector(".note").textContent,
    ids: [...s.querySelectorAll("details.feat-item")].map((d) => d.dataset.id),
  })));

await check("every group is listed, in the file's own order, with its own count", async () => {
  const page = await opened();
  const drawn = await drawnGroups(page);
  await page.close();
  assert.deepEqual(drawn.map((d) => d.group), GROUPS,
    "the groups are not the file's, in the file's order");
  for (const [i, g] of drawn.entries()) {
    assert.equal(g.heading, GROUPS[i], "the heading is not the group's name");
    const mine = fileIdsIn(GROUPS[i]).length;
    assert.equal(g.ids.length, mine, `${GROUPS[i]} draws ${g.ids.length} rows, the file has ${mine}`);
    assert.equal(g.note, mine === 1 ? "1 feature" : `${mine} features`, `${GROUPS[i]}'s count line`);
  }
});

await check("one row per entry, and the page's count equals the file's", async () => {
  const page = await opened();
  const ids = await page.evaluate(() =>
    [...document.querySelectorAll("#features-list details.feat-item")].map((d) => d.dataset.id));
  const sub = await page.evaluate(() => document.getElementById("features-sub").textContent);
  const status = await page.evaluate(() => document.getElementById("features-status").textContent);
  await page.close();
  assert.equal(ids.length, LIST.length, `the page draws ${ids.length} rows for ${LIST.length} features`);
  assert.deepEqual([...ids].sort(), LIST.map((e) => e.id).sort(),
    "the rows are not the file's entries");
  assert.equal(new Set(ids).size, ids.length, "a row is drawn twice");
  assert.match(sub, new RegExp(`^${LIST.length} features, in ${GROUPS.length} groups`),
    `the page's own count line reads "${sub}"`);
  const onPhone = LIST.filter((e) => e.surface === "phone").length;
  assert.match(status, new RegExp(`^${onPhone} of them`),
    `the page does not say how many are on the phone: "${status}"`);
});

await check("this PC's own features come first in a group, the phone's are marked", async () => {
  const page = await opened();
  const drawn = await drawnGroups(page);
  const tags = await page.evaluate(() =>
    [...document.querySelectorAll("#features-list details.feat-item")].map((d) => ({
      id: d.dataset.id,
      tag: (d.querySelector(".feat-tag") || {}).textContent || "",
    })));
  await page.close();

  // The same entries, and each half keeps the file's own relative order.
  const isThePhone = (id) => BY_ID.get(id).surface === "phone";
  for (const g of drawn) {
    const file = fileIdsIn(g.group);
    assert.deepEqual([...g.ids].sort(), [...file].sort(), `${g.group}: the rows are not the file's`);
    for (const pick of [(id) => !isThePhone(id), isThePhone]) {
      assert.deepEqual(g.ids.filter(pick), file.filter(pick),
        `${g.group}: one half's order changed`);
    }
    const firstPhone = g.ids.findIndex(isThePhone);
    const lastOwn = g.ids.map((id) => !isThePhone(id)).lastIndexOf(true);
    assert.ok(firstPhone === -1 || lastOwn === -1 || lastOwn < firstPhone,
      `${g.group}: a phone-only feature comes before this PC's own`);
  }

  // The marker: on the other app's rows, and on nothing else.
  const tagOf = new Map(tags.map((t) => [t.id, t.tag]));
  assert.equal(tagOf.size, LIST.length, "a row is missing from the tag list");
  for (const e of LIST) {
    assert.equal(tagOf.get(e.id), e.surface === "phone" ? "on your phone" : "",
      `${e.id} (${e.surface}) carries the wrong marker`);
  }
});

await check("a row opens on a real click and shows all four fields, word for word", async () => {
  const page = await opened();
  const first = LIST[0];
  await page.click(`#features-list details[data-id="${first.id}"] > summary`);
  const got = await page.evaluate((id) => {
    const item = document.querySelector(`#features-list details[data-id="${id}"]`);
    return {
      open: item.open,
      labels: [...item.querySelectorAll(".feat-field .feat-label")].map((n) => n.textContent),
      values: [...item.querySelectorAll(".feat-field .feat-value")].map((n) => n.textContent),
    };
  }, first.id);
  await page.close();
  assert.equal(got.open, true, "the row did not open on a click");
  assert.deepEqual(got.labels, ["What it does", "How to reach it", "Asks first", "One limit"],
    "the four fields are not the four labels");
  assert.deepEqual(got.values, [first.what, first.where, first.asks, first.limit],
    "the opened row does not say what the file says");
});

await check("every row opens, and says exactly what the file says", async () => {
  const page = await opened();
  const rows = await page.evaluate(() => {
    const out = [];
    for (const item of document.querySelectorAll("#features-list details.feat-item")) {
      // Each row is opened through its own summary, which is what a click does.
      if (!item.open) item.querySelector("summary").click();
      out.push({
        id: item.dataset.id,
        open: item.open,
        labels: [...item.querySelectorAll(".feat-field .feat-label")].map((n) => n.textContent),
        values: [...item.querySelectorAll(".feat-field .feat-value")].map((n) => n.textContent),
      });
    }
    return out;
  });
  await page.close();
  assert.equal(rows.length, LIST.length, "not every row was visited");
  for (const row of rows) {
    const entry = BY_ID.get(row.id);
    assert.ok(entry, `${row.id} is on the page but not in the file`);
    assert.equal(row.open, true, `${row.id} did not open`);
    const wantLabels = ["What it does", "How to reach it", "Asks first"];
    if (entry.limit) wantLabels.push("One limit");
    assert.deepEqual(row.labels, wantLabels, `${row.id}: the fields shown`);
    const wantValues = [entry.what, entry.where, entry.asks];
    if (entry.limit) wantValues.push(entry.limit);
    assert.deepEqual(row.values, wantValues, `${row.id}: the words shown`);
  }
});

await check("a feature with no limit draws no limit line at all", async () => {
  assert.ok(NO_LIMIT.length, "no entry in the file has an empty limit - this check would prove nothing");
  assert.ok(WITH_LIMIT.length, "every entry in the file has an empty limit - check the file");
  const page = await opened();
  const lines = (ids) => page.evaluate((wanted) => wanted.map((id) => {
    const item = document.querySelector(`#features-list details[data-id="${id}"]`);
    item.querySelector("summary").click();
    return {
      id,
      lines: item.querySelectorAll(".feat-field").length,
      labels: [...item.querySelectorAll(".feat-field .feat-label")].map((n) => n.textContent),
    };
  }), ids);
  const without = await lines(NO_LIMIT);
  const withLimit = await lines(WITH_LIMIT);
  await page.close();
  for (const row of without) {
    assert.equal(row.lines, 3, `${row.id} draws ${row.lines} field lines with no limit to show`);
    assert.ok(!row.labels.includes("One limit"), `${row.id} draws a limit line with nothing on it`);
  }
  for (const row of withLimit) {
    assert.equal(row.lines, 4, `${row.id} has a real limit and does not draw it`);
    assert.ok(row.labels.includes("One limit"), `${row.id} is missing its limit line`);
  }
});

/* ── the real button, and what is behind it (no browser) ─────────────────── */

await check("Settings has a real button, in the page's own style", () => {
  const html = read("src/settings.html");
  const inFaq = html.slice(html.indexOf('id="faq"'), html.indexOf("faq-list"));
  assert.match(inFaq, /<button class="btn" id="open-features" type="button">Everything Jarvis can do<\/button>/,
    "the button is not in the Help card, in the style every other row uses");
  assert.match(inFaq, /<span class="status" id="features-status" role="status">/,
    "the button has no live status line for a failure");
  assert.match(read("src/settings.js"),
    /\$\("open-features"\)\.addEventListener\("click", async \(\) => \{\s*try \{\s*await invoke\("open_features"\);/,
    "the button does not call open_features");
});

await check("the tray can open it too, and the command is wired end to end", () => {
  const tray = read("src-tauri/src/tray.rs");
  assert.match(tray, /const ID_SHOW_FEATURES: &str = "show-features"/);
  assert.match(tray, /ID_SHOW_FEATURES,[\s\S]{0,40}?"Everything Jarvis can do…"/, "no tray row");
  assert.match(tray, /ID_SHOW_FEATURES => \{[\s\S]*?windows::show_features\(app\)/,
    "the tray row does not open the window");
  assert.match(read("src-tauri/src/lib.rs"), /commands::open_features,/, "the command is not registered");
  assert.match(read("src-tauri/build.rs"), /"open_features",/, "the command has no permission file");
  assert.match(read("src-tauri/src/commands.rs"),
    /pub async fn open_features\(app: AppHandle\) -> Result<\(\), String> \{\s*crate::windows::show_features\(&app\)/,
    "the command is not async, which deadlocks when the window is built");
  assert.match(read("src-tauri/src/windows.rs"),
    /pub fn show_features\(app: &AppHandle\) -> Result<\(\), String>[\s\S]*?WebviewUrl::App\("features\.html"/,
    "show_features does not open features.html");
});

await check("CONTROL: only Settings may open it, and the window itself holds no command", () => {
  const surfaces = read("src-tauri/permissions/surfaces.toml");
  assert.equal((surfaces.match(/"allow-open-features"/g) || []).length, 1,
    "allowed on more than one surface");
  assert.match(surfaces, /identifier = "features-open"[\s\S]*?"allow-open-features"/);
  const settings = JSON.parse(read("src-tauri/capabilities/settings.json"));
  assert.ok(settings.permissions.includes("features-open"), "Settings cannot open it");
  for (const other of ["brain", "faces", "floating", "hud", "onboarding", "quickbar", "widget"]) {
    assert.ok(!read(`src-tauri/capabilities/${other}.json`).includes("features-open"),
      `${other} can open the feature list`);
  }
  const cap = JSON.parse(read("src-tauri/capabilities/features.json"));
  assert.deepEqual(cap.windows, ["features"]);
  for (const p of cap.permissions) {
    assert.ok(String(p).startsWith("core:"), `the window is granted ${p}, which is not a core call`);
  }
  assert.ok(!cap.permissions.includes("core:event:allow-listen"),
    "the window can listen to every event, including the approval queue");
});

await check("CONTROL: the page obeys the packaged CSP's own rules", () => {
  // Comments out first, the way tests/csp-inline.mjs reads every page: this
  // file's own header comment TALKS about the inline script it must not have.
  const html = read("src/features.html").replace(/<!--[\s\S]*?-->/g, "");
  assert.equal([...html.matchAll(/<script\b([^>]*)>/g)].filter((m) => !/\bsrc\s*=/.test(m[1])).length, 0,
    "features.html has an inline script, which tests/csp-inline.mjs allows no page to add");
  assert.deepEqual([...html.matchAll(/<[a-z][^>]*\s(on[a-z]+)\s*=/gi)].map((m) => m[1]), [],
    "features.html has an inline event handler");
  assert.ok(!/https?:\/\//.test(html), "the page references a remote URL, which nothing here may fetch");
  assert.ok(!/style\s*=/.test(html), "features.html carries a style=\"...\" attribute");
  const js = read("src/features.js");
  assert.ok(!/createElement\(\s*["'`]style["'`]\s*\)|setAttribute\(\s*["'`]style["'`]/.test(js),
    "features.js builds a stylesheet at run time, which the packaged CSP refuses");
  assert.match(js, /fetch\("features\.json"/, "the page does not fetch the list it draws");
  assert.match(js, /innerHTML = "";/, "the page no longer clears the list before drawing it");
});

await check("CONTROL: the desktop's copy of the list is the source, byte for byte", () => {
  assert.equal(read("src/features.json"), read("../features/features.json"),
    "src/features.json has drifted from features/features.json - copy it again");
});

await browser.close();
await close();
if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nall passed");
