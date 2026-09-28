/**
 * Brain -> Projects on the desktop (the owner's decision of 2026-09-28;
 * docs/PROJECTS-DESIGN.md build step 3; JARVIS-API.md section 61;
 * src/projects.js, src/projects-panel.js, src/projects.css,
 * src-tauri/src/brain/projects.rs).
 *
 * What must hold:
 * - the words are the phone's, word for word (the contract file's `words`,
 *   made by tools/gen_projects_cases.py, and net/Projects.kt);
 * - numbers are written the way the PC writes them, and the chart's scale
 *   is the one reference both apps share;
 * - every real answer reads (fixtures/projects-cases.json, the real
 *   backend's answers);
 * - the page: the list, New project, a project's instructions and notes,
 *   the folder (coding, the picker only), Shareable (a card to turn on,
 *   instant off - and OFF allowed on a stale link), the work list,
 *   benchmarks with a chart (dated points and a target line), better or
 *   worse, "private - not read aloud", the private-mark button (a card for
 *   Jarvis's own mark, instant for the owner's), logging a number, and
 *   "are you sure?" before deleting;
 * - a private number is never put into anything spoken;
 * - hidden while the private lists are hidden, with Show;
 * - CONTROL: the three commands are the Brain's alone, every change is
 *   held on a stale link in Rust except Shareable OFF, and a folder is never
 *   typed;
 * - themes: the chart and the private label read in all three themes;
 * - a11y: the tab is on the rail's arrow keys, every control has a name,
 *   the chart is an image with words.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  benchBody,
  chartGeometry,
  chartScale,
  chartSummary,
  notesFrom,
  readBench,
  readList,
  readProject,
  unmarkOffer,
  valueFrom,
  withUnit,
  WORDS,
} from "../src/projects.js";
import { check as contrast, parseColor } from "./contrast.mjs";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const readRepo = (p) => readFileSync(join(HERE, "..", "..", p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/projects-cases.json"));
const C = CASES.cases;
const POSTS = CASES.posts;

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const LIFE = C.life.project;
const CODING = C.coding.project;
const benchNamed = (p, name) => p.benchmark_list.find((b) => b.name === name);

await check("the words are the contract's and the phone's, word for word", async () => {
  assert.deepEqual(WORDS, CASES.words);
  const kt = readRepo("jarvis-client/app/src/main/java/com/jarvis/client/net/Projects.kt")
    .replace(/"\s*\+\s*\n\s*"/g, "");
  for (const [key, words] of Object.entries(CASES.words)) {
    assert.ok(kt.includes(`"${key}" to "${words.replace(/"/g, "\\\"")}"`),
      `the phone does not say ${key}: ${words}`);
  }
  assert.ok(read("src-tauri/src/brain/projects.rs").includes(`"${WORDS.missing}"`));
  assert.ok(read("src/brain.html").includes('<span class="rail-label">Projects</span>'));
});

await check("numbers are written the PC's way, and the chart scale is the shared one", async () => {
  for (const n of CASES.numbers) assert.equal(withUnit(n.value, n.unit), n.text, JSON.stringify(n));
  for (const s of CASES.scales) {
    const got = chartScale(s.values, s.target);
    assert.ok(Math.abs(got[0] - s.scale[0]) < 1e-9 && Math.abs(got[1] - s.scale[1]) < 1e-9,
      `${JSON.stringify(s)} -> ${got}`);
  }
  const g = chartGeometry([{ at: 1, value: 10 }, { at: 3, value: 20 }], 25, 320, 120);
  assert.equal(g.points[0].x, 8);
  assert.equal(g.points[1].x, 312);
  assert.ok(g.points[1].y < g.points[0].y, "higher is up");
  assert.ok(g.target < g.points[1].y, "the target above the top point");
  const one = chartGeometry([{ at: 5, value: 3 }], null, 320, 120);
  assert.equal(one.points[0].x, 160, "one point sits in the middle");
  assert.equal(one.target, null);
  assert.equal(valueFrom("72,5"), 72.5);
  assert.equal(valueFrom("five"), null);
  assert.equal(valueFrom(""), null);
  assert.deepEqual(notesFrom("a\n\n b \r\nc"), ["a", "b", "c"]);
  assert.deepEqual(benchBody({ name: "  Long run ", unit: "km", better: "higher", target: "21,1" }).body,
    { name: "Long run", kind: "number", unit: "km", better: "higher", target: 21.1 });
  assert.ok(benchBody({ name: "" }).error);
  assert.ok(benchBody({ name: "x", target: "far" }).error);
  assert.ok(benchBody({ name: "tests", kind: "command", command: " " }).error);
});

await check("every real answer reads: list, project, benchmark, private marks", async () => {
  const two = readList(C.list_two);
  assert.equal(two.available, true);
  assert.deepEqual(two.projects.map((p) => p.name), ["Half marathon", "Jarvis Desktop"]);
  assert.equal(readList(C.list_empty).projects.length, 0);
  assert.equal(readList(C.list_empty).empty, "No projects yet.");
  const missing = readList({ available: false, why: WORDS.missing });
  assert.equal(missing.available, false);
  assert.equal(missing.why, WORDS.missing);
  assert.equal(readList(null).why, WORDS.missing);
  assert.equal(readList({ ok: true, hidden: true, hidden_count: 2 }).hiddenCount, 2);
  const life = readProject(LIFE);
  assert.equal(life.kind, "life");
  assert.deepEqual(life.notes, ["Long runs on Sundays", "Knee: stop if it hurts"]);
  assert.equal(life.workList.title, "Half marathon list");
  assert.equal(life.shareable, false);
  const offers = Object.fromEntries(life.benchList.map((b) => [b.name, unmarkOffer(b)]));
  assert.equal(offers["Long run"], null);
  assert.equal(offers.Weight.kind, "card");
  assert.equal(offers["5k time"].kind, "card");
  assert.equal(offers.Stretching.kind, "instant");
  assert.equal(offers["5k time"].why, WORDS.remove_mark_card);
  const coding = readProject(CODING);
  assert.equal(coding.folder.path, "C:\\Users\\owner\\Code\\jarvis-desktop");
  const cmd = coding.benchList.find((b) => b.kind === "command");
  assert.equal(cmd.command, "pytest -q");
  assert.equal(cmd.runnable, false);
  const run = readBench(C.bench_run.benchmark);
  assert.equal(run.points.length, 3);
  assert.equal(run.target, 21.1);
  assert.equal(chartSummary(run), "3 numbers. Latest: 12 km.");
  assert.equal(chartSummary(readBench(C.bench_empty.benchmark)), WORDS.chart_empty);
  const waiting = readProject(C.life_waiting.project);
  assert.equal(waiting.shareableWaiting, true);
  const five = waiting.benchList.find((b) => b.name === "5k time");
  assert.equal(five.unmarkWaiting, true);
  assert.equal(unmarkOffer(five), null, "no second card offered while one waits");
  const answered = readProject(C.life_answered.project);
  assert.match(answered.shareableLast, /you said no/);
  const five2 = answered.benchList.find((b) => b.name === "5k time");
  assert.equal(five2.keepOnScreen, false);
  assert.match(five2.unmarkLast, /may read these numbers aloud/);
});

await check("CONTROL: the Brain's three commands, held on a stale link except Shareable OFF", async () => {
  const rs = read("src-tauri/src/brain/projects.rs");
  const fn = (name) => {
    const f = rs.slice(rs.indexOf(`pub async fn ${name}(`));
    return f.slice(0, f.indexOf("\n}\n"));
  };
  const w = fn("projects_write");
  assert.ok(w.indexOf("held_on_stale(") >= 0 && w.indexOf("held_on_stale(") < w.indexOf("post("),
    "a change is sent before the stale check");
  assert.ok(w.indexOf("checked_body(") < w.indexOf("post("), "a typed folder is not refused first");
  assert.match(rs, /!\(action == "shareable" && body\.get\("on"\) == Some\(&serde_json::Value::Bool\(false\)\)\)/);
  const f = fn("projects_choose_folder");
  assert.ok(f.indexOf("stale(&app)") < f.indexOf("picker::pick"), "the picker opens on a stale link");
  assert.match(fn("projects_read"), /private_hidden\(&app\)[\s\S]*redact\(answer\)/);
  for (const cmd of ["projects_read", "projects_write", "projects_choose_folder"]) {
    assert.match(read("src-tauri/build.rs"), new RegExp(`"${cmd}"`));
    assert.match(read("src-tauri/src/lib.rs"), new RegExp(`brain::projects::${cmd},`));
  }
  const sets = read("src-tauri/permissions/surfaces.toml").split("[[set]]").slice(1);
  const holders = (cmd) => sets.filter((s) => s.includes(`"allow-${cmd.replace(/_/g, "-")}"`))
    .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
  for (const cmd of ["projects_read", "projects_write", "projects_choose_folder"]) {
    assert.deepEqual(holders(cmd), ["brain-projects"], cmd);
  }
  const caps = (win) => JSON.parse(read(`src-tauri/capabilities/${win}.json`)).permissions;
  assert.ok(caps("brain").includes("brain-projects"));
  for (const other of ["quickbar", "hud", "settings", "faces", "floating", "onboarding", "widget"]) {
    assert.ok(!caps(other).includes("brain-projects"), `${other} holds brain-projects`);
  }
  // Nothing on this page speaks, and it never approves anything.
  const panel = read("src/projects-panel.js");
  for (const never of ["speak_reply", "speak(", "innerHTML"]) {
    assert.ok(!panel.includes(never), `projects-panel.js mentions ${never}`);
  }
  assert.doesNotMatch(panel, /invoke\("(approve|deny|decide|resolve)/, "the page answers a card");
});

/* ── The window ───────────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 1000 };

/**
 * The Brain with a stand-in for brain/projects.rs: reads come from the
 * contract file, each change is written down in `window.__pj.calls` and
 * answered with the real backend's answer (an error as Rust hands it on).
 */
async function projectsTab({ list = C.list_two, projects = null, link = {}, answers = {} } = {}) {
  const page = await K.open(browser, base, "brain.html", { link }, SIZE);
  page.on("dialog", (d) => (page.__confirm === false ? d.dismiss() : d.accept()));
  await page.evaluate(({ list, projects, answers, POSTS, benches }) => {
    const core = window.__TAURI__.core;
    const inner = core.invoke;
    window.__pj = { list, projects, answers, calls: [], revealed: false };
    const ok = (p) => ({ ...p.body, http: p.status });
    const refuse = (p) => {
      const e = String(p.body.error || "");
      throw e.charAt(0).toUpperCase() + e.slice(1);
    };
    core.invoke = async (cmd, args) => {
      const pj = window.__pj;
      if (cmd === "reveal_private_answers") {
        pj.revealed = true;
        return null;
      }
      if (cmd === "projects_read") {
        if (!args.project) return pj.revealed && pj.list.hidden ? pj.full : pj.list;
        const got = pj.projects[args.project];
        if (!got) throw "No such project, benchmark or number";
        if (args.bench) return benches[args.bench] || { ok: true, benchmark:
          got.project.benchmark_list.find((b) => b.id === args.bench) };
        return got;
      }
      if (cmd === "projects_write" || cmd === "projects_choose_folder") {
        pj.calls.push([cmd, JSON.parse(JSON.stringify(args))]);
        const name = cmd === "projects_choose_folder" ? "choose_folder" : args.action;
        const a = pj.answers[name];
        if (a && a.status >= 400) refuse(a);
        if (a) return ok(a);
        const fallback = { create: POSTS.create_life, log: POSTS.log, unmark: POSTS.unmark_card,
          shareable: args.body && args.body.on ? POSTS.shareable_on : POSTS.shareable_off,
          delete: POSTS.delete, choose_folder: { status: 200, body: { cancelled: true } } }[name];
        return fallback ? ok(fallback) : { ok: true, http: 200 };
      }
      return inner(cmd, args);
    };
  }, { list, projects: projects || { [LIFE.id]: C.life, [CODING.id]: C.coding }, answers, POSTS,
       benches: { [benchNamed(LIFE, "Long run").id]: C.bench_run,
                  [benchNamed(LIFE, "Weight").id]: C.bench_weight } });
  await page.locator("#tab-projects").click();
  await page.waitForTimeout(400);
  return page;
}

const calls = (page) => page.evaluate(() => window.__pj.calls);
const openLife = async (page) => {
  await page.getByRole("button", { name: "Open Half marathon" }).click();
  await page.waitForTimeout(400);
};

await check("the list: both projects, Open, and New project sends ONE create", async () => {
  const page = await projectsTab();
  const title = await page.locator("#view-title").innerText();
  const rows = await page.locator("#projects-root .pj-list .row-title").allInnerTexts();
  const meta = await page.locator("#projects-root .pj-list .row-meta").allInnerTexts();
  await page.locator("#projects-new-name").fill("Learn Spanish");
  await page.locator("#projects-new-kind").selectOption("life");
  await page.getByRole("button", { name: WORDS.create }).click();
  await page.waitForTimeout(400);
  const sent = await calls(page);
  const errors = page.__errors;
  await page.close();
  assert.equal(title, "Projects");
  assert.deepEqual(rows, ["Half marathon", "Jarvis Desktop"]);
  assert.deepEqual(meta, ["Life · 4 benchmarks", "Coding · 2 benchmarks"]);
  assert.deepEqual(sent, [["projects_write",
    { action: "create", body: { name: "Learn Spanish", kind: "life" } }]]);
  assert.deepEqual(errors, []);
});

await check("a life project: instructions, notes, the work list, charts and private labels", async () => {
  const page = await projectsTab();
  await openLife(page);
  const heading = await page.locator("#projects-heading").textContent();
  const focused = await page.evaluate(() => document.activeElement && document.activeElement.id);
  const instructions = await page.locator("#projects-instructions").inputValue();
  const notes = await page.locator("#projects-notes").inputValue();
  const text = await page.locator("#projects-root").innerText();
  const benches = await page.locator(".pj-bench").evaluateAll((els) => els.map((e) => ({
    name: e.querySelector(".pj-bench-name").textContent,
    private: Boolean(e.querySelector(".pj-private")),
    dots: e.querySelectorAll(".pj-dot").length,
    target: Boolean(e.querySelector(".pj-target")),
    chart: e.querySelector(".pj-chart") ? e.querySelector(".pj-chart").getAttribute("aria-label") : "",
  })));
  const folderShown = await page.locator("text=" + WORDS.folder_choose).count();
  await page.close();
  assert.equal(heading, "Half marathon");
  assert.equal(focused, "projects-heading", "opening a project does not move focus to it");
  assert.equal(instructions, LIFE.instructions);
  assert.equal(notes, "Long runs on Sundays\nKnee: stop if it hurts");
  assert.match(text, /Half marathon list/);
  assert.match(text, /Latest: 12 km · Better than last time \(up 1\.5\)\./);
  assert.match(text, /Target: 21\.1 km/);
  assert.equal(folderShown, 0, "a life project offers a folder");
  const by = Object.fromEntries(benches.map((b) => [b.name, b]));
  assert.equal(by["Long run"].private, false);
  assert.equal(by["Long run"].dots, 3);
  assert.equal(by["Long run"].target, true);
  assert.equal(by["Long run"].chart, "Long run: 3 numbers. Latest: 12 km.");
  for (const name of ["Weight", "5k time", "Stretching"]) assert.equal(by[name].private, true, name);
  assert.equal(by.Weight.dots, 2);
  assert.match(text, new RegExp(WORDS.private_label));
});

await check("logging: ONE number; a private one is never put into anything spoken", async () => {
  const page = await projectsTab({ answers: { log: POSTS.log } });
  await openLife(page);
  await page.evaluate(() => {
    window.__spoken = [];
    for (const r of document.querySelectorAll("[aria-live], [role=status]")) {
      new MutationObserver(() => window.__spoken.push(r.textContent.trim()))
        .observe(r, { childList: true, characterData: true, subtree: true });
    }
  });
  const weight = page.locator(".pj-bench", { hasText: "Weight" });
  await weight.getByRole("textbox").fill("73,1");
  await weight.getByRole("button", { name: WORDS.log }).click();
  await page.waitForTimeout(500);
  const spokenPrivate = await page.evaluate(() => window.__spoken.join(" | "));
  const run = page.locator(".pj-bench", { hasText: "Long run" });
  await run.getByRole("textbox").fill("abc");
  await run.getByRole("button", { name: WORDS.log }).click();
  await page.waitForTimeout(300);
  const said = await page.locator("#projects-said").innerText();
  const sent = await calls(page);
  await page.close();
  const weightId = benchNamed(LIFE, "Weight").id;
  assert.deepEqual(sent, [["projects_write",
    { action: "log", project: LIFE.id, bench: weightId, body: { value: 73.1 } }]]);
  assert.match(spokenPrivate, /Logged\./);
  assert.doesNotMatch(spokenPrivate, /73|0\.75|26/, "a private number was spoken");
  assert.equal(said, "Type a number, like 5 or 72.5.");
});

await check("the private mark: a card for Jarvis's own, instant for yours, Mark private", async () => {
  const page = await projectsTab({ answers: { unmark: POSTS.unmark_card } });
  await openLife(page);
  const five = page.locator(".pj-bench", { hasText: "5k time" });
  const title = await five.getByRole("button", { name: WORDS.remove_mark }).getAttribute("title");
  const note = await five.locator(".note").allInnerTexts();
  await five.getByRole("button", { name: WORDS.remove_mark }).click();
  await page.waitForTimeout(400);
  const said = await page.locator("#projects-said").innerText();
  const mine = page.locator(".pj-bench", { hasText: "Stretching" });
  const mineNote = await mine.locator(".note").allInnerTexts();
  await mine.getByRole("button", { name: WORDS.remove_mark }).click();
  await page.waitForTimeout(300);
  await page.locator(".pj-bench", { hasText: "Long run" }).getByRole("button", { name: WORDS.mark_private }).click();
  await page.waitForTimeout(300);
  const sent = await calls(page);
  await page.close();
  assert.equal(title, WORDS.remove_mark_card);
  assert.ok(note.includes(WORDS.remove_mark_card));
  assert.ok(mineNote.includes(WORDS.remove_mark_yours));
  assert.match(said, /Waiting for your approval/);
  const ids = (n) => benchNamed(LIFE, n).id;
  assert.deepEqual(sent, [
    ["projects_write", { action: "unmark", project: LIFE.id, bench: ids("5k time"), body: {} }],
    ["projects_write", { action: "unmark", project: LIFE.id, bench: ids("Stretching"), body: {} }],
    ["projects_write", { action: "bench_update", project: LIFE.id, bench: ids("Long run"),
      body: { sensitive: true } }],
  ]);
});

await check("Shareable: ON sends one request (the PC raises the card); a waiting card greys it", async () => {
  const page = await projectsTab({ answers: { shareable: POSTS.shareable_on } });
  await openLife(page);
  const before = await page.locator("#projects-shareable").isChecked();
  await page.locator("#projects-shareable").click();
  await page.waitForTimeout(400);
  const sent = await calls(page);
  const said = await page.locator("#projects-said").innerText();
  await page.close();
  assert.equal(before, false);
  assert.deepEqual(sent, [["projects_write", { action: "shareable", project: LIFE.id, body: { on: true } }]]);
  assert.match(said, /Waiting for your approval\. Shareable stays off/);

  const waiting = await projectsTab({ projects: { [LIFE.id]: C.life_waiting } });
  await openLife(waiting);
  const disabled = await waiting.locator("#projects-shareable").isDisabled();
  const text = await waiting.locator("#projects-root").innerText();
  const fiveButtons = await waiting.locator(".pj-bench", { hasText: "5k time" })
    .getByRole("button", { name: WORDS.remove_mark }).count();
  await waiting.close();
  assert.equal(disabled, true);
  assert.ok(text.split(WORDS.waiting_card).length >= 3, "the waiting cards are not said");
  assert.equal(fiveButtons, 0, "a second card is offered while one waits");
});

await check("a stale link greys every change except turning Shareable OFF", async () => {
  const on = JSON.parse(JSON.stringify(C.life));
  on.project.shareable = true;
  const page = await projectsTab({ projects: { [LIFE.id]: on }, link: { stale: true } });
  await openLife(page);
  const offOk = await page.locator("#projects-shareable").isEnabled();
  const log = await page.locator(".pj-log button").first().isDisabled();
  const save = await page.getByRole("button", { name: WORDS.save }).isDisabled();
  const del = await page.getByRole("button", { name: WORDS.delete_project }).isDisabled();
  const back = await page.getByRole("button", { name: `← ${WORDS.back}` }).isEnabled();
  const title = await page.getByRole("button", { name: WORDS.save }).getAttribute("title");
  await page.locator("#projects-shareable").click();
  await page.waitForTimeout(300);
  const sent = await calls(page);
  await page.close();
  assert.equal(offOk, true, "Shareable OFF is held on a stale link");
  assert.equal(log && save && del, true);
  assert.equal(back, true, "going back to the list is a read");
  assert.equal(title, WORDS.stale);
  assert.deepEqual(sent, [["projects_write", { action: "shareable", project: LIFE.id, body: { on: false } }]]);
});

await check("deleting asks \"are you sure?\" first; No sends nothing", async () => {
  const page = await projectsTab();
  await openLife(page);
  let question = "";
  page.on("dialog", (d) => { question = d.message(); });
  page.__confirm = false;
  await page.getByRole("button", { name: WORDS.delete_project }).click();
  await page.waitForTimeout(300);
  const none = await calls(page);
  page.__confirm = true;
  await page.getByRole("button", { name: WORDS.delete_project }).click();
  await page.waitForTimeout(500);
  const sent = await calls(page);
  const back = await page.locator("#projects-root .pj-list").count();
  await page.close();
  assert.equal(question, WORDS.delete_project_q.replace("{name}", "Half marathon"));
  assert.deepEqual(none, []);
  assert.deepEqual(sent, [["projects_write", { action: "delete", project: LIFE.id }]]);
  assert.equal(back, 1, "not back on the list after deleting");
});

await check("a coding project: the folder by the picker only, the command kept as words", async () => {
  const page = await projectsTab();
  await page.getByRole("button", { name: "Open Jarvis Desktop" }).click();
  await page.waitForTimeout(400);
  const text = await page.locator("#projects-root").innerText();
  const tests = page.locator(".pj-bench", { hasText: "pytest -q" });
  const logForms = await tests.locator(".pj-log").count();
  await page.getByRole("button", { name: WORDS.folder_choose }).click();
  await page.waitForTimeout(300);
  await page.getByRole("button", { name: WORDS.folder_clear }).click();
  await page.waitForTimeout(300);
  await page.locator(".pj-add summary").click();
  await page.locator("#projects-bench-name").fill("lint");
  await page.locator("#projects-bench-kind").selectOption("command");
  await page.locator("#projects-bench-command").fill("ruff check .");
  const formText = await page.locator(".pj-add").innerText();
  await page.getByRole("button", { name: WORDS.add, exact: true }).click();
  await page.waitForTimeout(300);
  const sent = await calls(page);
  await page.close();
  assert.match(text, /C:\\Users\\owner\\Code\\jarvis-desktop/);
  assert.match(text, /pytest -q/);
  assert.match(text, /nothing runs yet/);
  assert.ok(formText.includes(WORDS.command_on_pc));
  assert.equal(logForms, 0, "a command benchmark offers Log");
  assert.deepEqual(sent, [
    ["projects_choose_folder", { project: CODING.id }],
    ["projects_write", { action: "update", project: CODING.id, body: { folder: null } }],
    ["projects_write", { action: "bench_add", project: CODING.id,
      body: { name: "lint", kind: "command", command: "ruff check ." } }],
  ]);
});

await check("a refusal is the PC's own sentence", async () => {
  const page = await projectsTab({ answers: { create: POSTS.name_twice } });
  await page.locator("#projects-new-name").fill("Half marathon");
  await page.getByRole("button", { name: WORDS.create }).click();
  await page.waitForTimeout(400);
  const said = await page.locator("#projects-said").innerText();
  await page.close();
  assert.equal(said, "There is already a project with that name.");
});

await check("hidden with the private lists: the count and Show only; a PC without Projects says so", async () => {
  const page = await projectsTab({ list: { ok: true, hidden: true, hidden_count: 2 } });
  await page.evaluate((full) => { window.__pj.full = full; }, C.list_two);
  const text = await page.locator("#projects-root").innerText();
  await page.getByRole("button", { name: "Show" }).click();
  await page.waitForTimeout(400);
  const after = await page.locator("#projects-root .pj-list .row-title").allInnerTexts();
  await page.close();
  assert.match(text, /2 projects, hidden until Windows Hello confirms it is you\./);
  assert.doesNotMatch(text, /Half marathon|Jarvis Desktop/);
  assert.deepEqual(after, ["Half marathon", "Jarvis Desktop"]);

  const missing = await projectsTab({ list: { available: false, why: WORDS.missing } });
  const m = await missing.locator("#projects-root").innerText();
  await missing.close();
  assert.match(m, new RegExp(WORDS.missing.replace(/[.']/g, ".")));
});

await check("themes: the chart, its target and the private label read in all three", async () => {
  const page = await projectsTab();
  await openLife(page);
  const out = {};
  for (const theme of ["deep-space", "paper", "high-contrast"]) {
    out[theme] = await page.evaluate((t) => {
      document.documentElement.setAttribute("data-theme", t);
      const cs = (sel, prop) => getComputedStyle(document.querySelector(sel))[prop];
      const probe = document.createElement("span");
      document.body.append(probe);
      probe.style.color = "var(--surface-1)";
      const card = getComputedStyle(probe).color;
      probe.remove();
      return {
        chartBg: cs(".pj-chart", "backgroundColor"),
        line: cs(".pj-line", "stroke"),
        dot: cs(".pj-dot", "fill"),
        target: cs(".pj-target", "stroke"),
        legend: cs(".pj-legend", "color"),
        privateInk: cs(".pj-private", "color"),
        card,
      };
    }, theme);
  }
  await page.close();
  for (const [theme, v] of Object.entries(out)) {
    for (const [name, ink, min] of [["line", v.line, 3], ["dot", v.dot, 3], ["target", v.target, 3],
      ["legend", v.legend, 4.5]]) {
      const got = contrast(ink, name === "legend" ? v.card : v.chartBg, min);
      assert.ok(got.ok, `${theme}: the chart's ${name} is ${got.worst}:1 (needs ${min})`);
    }
    const tag = contrast(v.privateInk, v.card, 4.5);
    assert.ok(tag.ok, `${theme}: "private - not read aloud" is ${tag.worst}:1`);
    assert.notDeepEqual(parseColor(v.line), parseColor(v.target), `${theme}: the target looks like the line`);
  }
  assert.notDeepEqual(out["deep-space"].chartBg, out.paper.chartBg, "the chart did not follow the theme");
});

await check("a11y: on the rail's arrow keys, every control named, the chart is an image with words", async () => {
  const page = await K.open(browser, base, "brain.html", {}, SIZE);
  await page.locator("#tab-work").click();
  await page.locator("#tab-work").focus();
  await page.keyboard.press("ArrowDown");
  await page.waitForTimeout(300);
  const selected = await page.locator("#tab-projects").getAttribute("aria-selected");
  const shown = await page.locator("#view-projects").isVisible();
  await page.close();
  assert.equal(selected, "true");
  assert.equal(shown, true);

  const tab = await projectsTab();
  await openLife(tab);
  await tab.locator(".pj-add summary").click();
  const bad = await tab.evaluate(() => {
    const out = [];
    const rootEl = document.getElementById("projects-root");
    const nameOf = (e) => (e.getAttribute("aria-label") || (e.labels && e.labels[0]
      && e.labels[0].textContent) || e.textContent || e.title || "").trim();
    for (const e of rootEl.querySelectorAll("button, input, select, textarea")) {
      if (!nameOf(e)) out.push(e.outerHTML.slice(0, 80));
    }
    for (const svg of rootEl.querySelectorAll("svg")) {
      if (svg.getAttribute("role") !== "img" || !svg.getAttribute("aria-label")) out.push("chart");
    }
    if (!rootEl.querySelector("[role=status]#projects-said")) out.push("no status line");
    const sw = document.getElementById("projects-shareable");
    if (!sw || sw.getAttribute("role") !== "switch") out.push("shareable is not a switch");
    return out;
  });
  const errors = tab.__errors;
  await tab.close();
  assert.deepEqual(bad, []);
  assert.deepEqual(errors, []);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed` : "\nall projects checks passed");
process.exit(fails.length ? 1 : 0);
