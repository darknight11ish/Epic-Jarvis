/**
 * Brain -> Projects on the desktop (the owner's decision of 2026-09-28;
 * docs/PROJECTS-DESIGN.md build step 3; JARVIS-API.md section 88;
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
  APP_WORDS,
  appProjectBody,
  appTypeWords,
  benchBody,
  chartGeometry,
  chartScale,
  chartSummary,
  diffLineKind,
  mergeOffer,
  notesFrom,
  pasteBody,
  projectMeta,
  readApp,
  readBench,
  readList,
  readProject,
  readTask,
  taskChange,
  taskTitleBody,
  versionLines,
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
async function projectsTab({ list = C.list_two, projects = null, link = {}, answers = {}, tasks = {} } = {}) {
  const page = await K.open(browser, base, "brain.html", { link }, SIZE);
  page.on("dialog", (d) => (page.__confirm === false ? d.dismiss() : d.accept()));
  await page.evaluate(({ list, projects, answers, POSTS, benches, tasks }) => {
    const core = window.__TAURI__.core;
    const inner = core.invoke;
    window.__pj = { list, projects, answers, tasks, calls: [], revealed: false };
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
        if (args.task) {
          const t = pj.tasks[args.task];
          if (!t) throw "That task is gone.";
          return t;
        }
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
  }, { list, projects: projects || { [LIFE.id]: C.life, [CODING.id]: C.coding }, answers, POSTS, tasks,
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


/* ── An app Jarvis builds (docs/APPS-IN-PROJECTS-DESIGN.md sections 5 and 7.3) ──
 * There is no backend or shared fixture for this in this tree yet, so the
 * answers below are built by hand, exactly to the frozen shapes of section 7.1.
 * AFTER THE MERGE: re-point these at the shared fixture projects-cases.json
 * (its app cases and `words`), and delete the hand-made ones.
 */
const APP_ID = "0000000000000000000000000000ab01";
const T1 = "a1b2c3d4e5f6";
const T2 = "b1b2c3d4e5f6";
const OUTCOMES = {
  merged: "Added to your app.",
  denied: "Not added - you said no. The change is kept aside.",
  timed_out: "Not added - the card timed out. The change is kept aside.",
  stale: "Not added - the app or the change moved after the card was shown. Look at the new card.",
  unsaved: "Not added - the app's own folder has changes that are not saved in git.",
  conflict: "Not added - the change did not fit the app's newer version. Nothing was changed; discard it and ask again.",
  withdrawn: "Not added - the change was thrown away before you answered.",
  refused: "Not added. The gate said no.",
  failed: "Not added - something went wrong. Nothing was changed.",
};
const summary = (task, title, extra = {}) => ({
  task, title, started: 1759000000.0, source: "jarvis", files: 3, added: 41, removed: 2,
  older_main: false, waiting: false, ...extra });
const appObj = (over = {}) => ({
  name: "notes", type: "web", title: "Notes app", git_ok: true, said: "",
  main: { head: "a1b2c3d", subject: "Jarvis: Add a dark mode", at: 1759000000.0, versions: 7 },
  tasks: [summary(T1, "Add a search box"), summary(T2, "Rename the header",
    { files: 1, added: 1, removed: 1, older_main: true, source: "pasted" })],
  merge: { waiting: null, last: null }, ...over });
const appProject = (app, over = {}) => ({ ...JSON.parse(JSON.stringify(CODING)), name: "Notes app",
  id: APP_ID, folder: null, benchmarks: 0, benchmark_list: [], app, ...over });
const wrap = (project) => ({ ok: true, project });
const appList = (extra = {}) => ({ ...C.list_two, projects: [...C.list_two.projects,
  { ...C.list_two.projects[1], id: APP_ID, name: "Notes app", folder: null,
    app: { name: "notes", type: "web", tasks: 2, merge_waiting: false } }],
  unlinked_apps: [{ name: "old-game", type: "android", title: "Old game" }], ...extra });
// A change big enough to be near the design's 60,000-character cap.
const BIG_LINES = ["diff --git a/src/big.js b/src/big.js", "--- a/src/big.js", "+++ b/src/big.js",
  "@@ -1,2 +1,1400 @@"];
for (let i = 0; i < 1400; i++) {
  BIG_LINES.push(`${i % 5 === 0 ? "-" : "+"}const line${i} = "xxxx"; // <b>${i}</b>`);
}
BIG_LINES.push(" unchanged tail line");
const BIG = BIG_LINES.join("\n");
const detail = (task, over = {}) => ({ ok: true, task: { ...summary(task, "Add a search box"),
  list: [{ path: "src/big.js", added: "1120", removed: "280" }, { path: "src/App.tsx", added: "3", removed: "0" }],
  diff: BIG, too_big: false, refused: "", ...over } });
const appPage = async (app, opts = {}) => {
  const page = await projectsTab({ list: appList(), ...opts,
    projects: { [LIFE.id]: C.life, [CODING.id]: C.coding, [APP_ID]: wrap(appProject(app)) },
    tasks: opts.tasks || { [T1]: detail(T1),
      [T2]: detail(T2, { title: "Rename the header", source: "pasted", older_main: true, files: 1 }) } });
  await page.getByRole("button", { name: "Open Notes app" }).click();
  await page.waitForTimeout(400);
  return page;
};
const openTask = async (page, title = "Add a search box") => {
  await page.getByRole("button", { name: `${APP_WORDS.task_open}: ${title}` }).click();
  await page.waitForTimeout(400);
};

await check("app words and readers: shapes of section 7.1, plain sentences", async () => {
  assert.equal(APP_WORDS.merge_how, "Approve the card that appears - it needs Windows Hello.");
  assert.equal(APP_WORDS.merge_pasted, "You pasted this change in on your PC.");
  assert.equal(APP_WORDS.cant_run, "Jarvis cannot run this yet. Run it yourself and log the number.");
  assert.equal(APP_WORDS.only_here, "This app's files are only on this PC.");
  assert.equal(APP_WORDS.new_app, "An app Jarvis builds");
  assert.equal(APP_WORDS.adopt_title, "Add an app I already have");
  const a = readApp(appObj({ merge: { waiting: T1, last: { task: T2, outcome: "merged", message: OUTCOMES.merged, at: 1 } } }));
  assert.equal(a.full, true);
  assert.equal(a.tasks.length, 2);
  assert.equal(a.mergeWaiting, T1);
  assert.equal(a.last.outcome, "merged");
  assert.equal(a.tasks[1].olderMain, true);
  assert.equal(a.tasks[1].source, "pasted");
  const short = readApp({ name: "notes", type: "android", tasks: 3, merge_waiting: true });
  assert.equal(short.full, false);
  assert.equal(short.taskCount, 3);
  assert.equal(short.mergeWaiting, "yes");
  assert.equal(readApp(null), null);
  assert.equal(readProject(C.life.project).app, null, "a life project has no app");
  assert.equal(readProject(C.coding.project).app, null, "a folder project has no app");
  assert.equal(readApp(appObj({ merge: { waiting: null, last: { outcome: "odd", message: "x" } } })).last.outcome, "failed");
  const lines = versionLines(readApp(appObj()));
  assert.match(lines[0], /^Latest version: Jarvis: Add a dark mode, /);
  assert.equal(lines[1], "7 saved versions");
  assert.deepEqual(versionLines(readApp(appObj({ main: null }))), [APP_WORDS.no_versions]);
  const nogit = versionLines(readApp(appObj({ git_ok: false, said: "git is not installed on this PC ...", main: null, tasks: [] })));
  assert.deepEqual(nogit, ["git is not installed on this PC ..."]);
  assert.equal(taskChange(readApp(appObj()).tasks[0]), "3 files, +41 -2");
  assert.equal(taskChange(readApp(appObj()).tasks[1]), "1 file, +1 -1");
  assert.equal(taskChange({ files: 0 }), APP_WORDS.task_nothing);
  assert.equal(appTypeWords("android"), "Android app (native)");
  const t = readTask(detail(T1));
  assert.equal(t.diff, BIG, "the whole diff, never cut");
  assert.equal(t.list.length, 2);
  assert.equal(mergeOffer(a, a.tasks[0]).ok, false, "a waiting card greys Merge");
  const idle = readApp(appObj());
  assert.equal(mergeOffer(idle, idle.tasks[0]).ok, true);
  assert.equal(mergeOffer(idle, { ...t, refused: "This task has not changed anything yet." }).why,
    "This task has not changed anything yet.");
  assert.equal(diffLineKind("+added"), "add");
  assert.equal(diffLineKind("-gone"), "del");
  assert.equal(diffLineKind("+++ b/x"), "meta");
  assert.equal(diffLineKind("@@ -1 +1 @@"), "hunk");
  assert.equal(diffLineKind(" same"), "ctx");
  assert.deepEqual(taskTitleBody("  Dark mode ").body, { title: "Dark mode" });
  assert.ok(taskTitleBody(" ").error);
  assert.ok(taskTitleBody("x".repeat(121)).error);
  assert.ok(pasteBody("  ").error);
  assert.deepEqual(pasteBody("<<<FILE a>>>\nx\n<<<END>>>").body, { blocks: "<<<FILE a>>>\nx\n<<<END>>>" });
  assert.deepEqual(appProjectBody("Notes", "app-web"), { name: "Notes", kind: "coding", app: { type: "web" } });
  assert.deepEqual(appProjectBody("Game", "app-android"), { name: "Game", kind: "coding", app: { type: "android" } });
  assert.deepEqual(appProjectBody("", "adopt:old-game"), { kind: "coding", app: { adopt: "old-game" } });
  assert.equal(appProjectBody("x", "life"), null);
  assert.equal(readList(appList()).unlinked[0].name, "old-game");
  const meta = projectMeta(readList(appList()).projects[2]);
  assert.equal(meta[0], "App · 2 benchmarks");
  assert.equal(meta[1], "App · 2 open");
});

await check("app CONTROL: the four actions, held on a stale link, never logged, no URL on the page", async () => {
  const rs = read("src-tauri/src/brain/projects.rs");
  for (const a of ["app_task_start", "app_task_files", "app_task_merge", "app_task_discard"]) {
    assert.ok(rs.includes(`"${a}"`), a);
  }
  const prod = rs.slice(0, rs.indexOf("#[cfg(test)]"));
  for (const never of ["println!", "eprintln!", "dbg!", "log::", "tracing::"]) {
    assert.ok(!prod.includes(never), `projects.rs prints with ${never}`);
  }
  // The one address in the page is the SVG drawing namespace (an identifier, not a request).
  const panel = (read("src/projects-panel.js") + read("src/projects.js"))
    .replace("http://www.w3.org/2000/svg", "");
  assert.doesNotMatch(panel, /https?:\/\//, "the page names a URL");
  assert.doesNotMatch(panel, /["'`]\/api\//, "the page names a route");
  assert.doesNotMatch(panel, /console\.(log|info|warn|error|debug)/, "the page logs");
  assert.doesNotMatch(panel, /localStorage|sessionStorage|indexedDB/, "the page keeps the change");
  assert.doesNotMatch(panel, /invoke\("(approve|deny|decide|resolve)/, "the page answers a card");
  assert.doesNotMatch(panel, /\.innerHTML|insertAdjacentHTML|outerHTML/, "markup from the PC");
});

await check("the list: an app carries the App tag and open tasks; New project has the app choices", async () => {
  const page = await projectsTab({ list: appList() });
  const rows = await page.locator("#projects-root .pj-list .row-title").allInnerTexts();
  const meta = await page.locator("#projects-root .pj-list .row-meta").allInnerTexts();
  const tags = await page.locator("#projects-root .pj-list .row-tag").allTextContents();
  const options = await page.locator("#projects-new-kind option").allInnerTexts();
  await page.locator("#projects-new-name").fill("Recipe box");
  await page.locator("#projects-new-kind").selectOption("app-web");
  await page.getByRole("button", { name: WORDS.create }).click();
  await page.waitForTimeout(300);
  const sent = await calls(page);
  const errors = page.__errors;
  await page.close();
  // A created project opens, so the second choice is a fresh window.
  const second = await projectsTab({ list: appList() });
  await second.locator("#projects-new-name").fill("Star game");
  await second.locator("#projects-new-kind").selectOption("app-android");
  await second.getByRole("button", { name: WORDS.create }).click();
  await second.waitForTimeout(300);
  sent.push(...await calls(second));
  await second.close();
  assert.deepEqual(rows, ["Half marathon", "Jarvis Desktop", "Notes app"]);
  assert.deepEqual(tags, ["Life", "Coding", "App"]);
  assert.ok(meta.includes("App · 2 open"), meta.join(" | "));
  assert.deepEqual(options.slice(2), [APP_WORDS.new_app_web, APP_WORDS.new_app_android]);
  assert.deepEqual(sent, [
    ["projects_write", { action: "create", body: { name: "Recipe box", kind: "coding", app: { type: "web" } } }],
    ["projects_write", { action: "create", body: { name: "Star game", kind: "coding", app: { type: "android" } } }],
  ]);
  assert.deepEqual(errors, []);
});

await check("adopt: 'Add an app I already have' lists unlinked apps; Add sends ONE create", async () => {
  const page = await projectsTab({ list: appList(), projects: { [LIFE.id]: C.life, [CODING.id]: C.coding,
    [APP_ID]: wrap(appProject(appObj())) }, answers: { create: { status: 200, body: { ok: true,
    project: appProject(appObj(), { id: "0000000000000000000000000000ab02", name: "Old game" }) } } } });
  const text = await page.locator("#projects-root").textContent();
  await page.getByRole("button", { name: "Add Old game" }).click();
  await page.waitForTimeout(400);
  const sent = await calls(page);
  await page.close();
  assert.ok(text.includes(APP_WORDS.adopt_title) && text.includes("Old game") && text.includes(APP_WORDS.type_android));
  assert.deepEqual(sent, [["projects_write", { action: "create", body: { kind: "coding", app: { adopt: "old-game" } } }]]);
  const none = await projectsTab({ list: C.list_two });
  const t2 = await none.locator("#projects-root").textContent();
  await none.close();
  assert.ok(!t2.includes(APP_WORDS.adopt_title), "no unlinked apps, no offer");
});

await check("the App section: version, files kept here, open tasks, no folder picker", async () => {
  const page = await appPage(appObj());
  const text = await page.locator("#projects-root").innerText();
  const rows = await page.locator(".pj-tasks .row-item").evaluateAll((els) => els.map((e) => e.innerText));
  const folder = await page.getByRole("button", { name: WORDS.folder_choose }).count();
  await page.close();
  assert.match(text, /Web app - Notes app/);
  assert.match(text, /Latest version: Jarvis: Add a dark mode, /);
  assert.match(text, /7 saved versions/);
  assert.ok(text.includes(APP_WORDS.files_where) && text.includes(APP_WORDS.only_here));
  assert.equal(rows.length, 2);
  assert.match(rows[0], /Add a search box[\s\S]*3 files, \+41 -2/);
  assert.match(rows[1], /Rename the header[\s\S]*1 file, \+1 -1[\s\S]*made before another change - may not fit/);
  assert.equal(folder, 0, "an app project has no folder");
});

await check("app states: no git, and no tasks yet", async () => {
  const nogit = await appPage(appObj({ git_ok: false, said: "git is not installed on this PC - install it first.", main: null, tasks: [] }));
  const t1 = await nogit.locator("#projects-root").innerText();
  const start1 = await nogit.locator("#projects-task-title").count();
  await nogit.close();
  assert.match(t1, /git is not installed on this PC - install it first\./);
  assert.equal(start1, 0, "no Start a task without git");
  const none = await appPage(appObj({ tasks: [], main: { head: "", subject: "", at: null, versions: 0 } }));
  const t2 = await none.locator("#projects-root").innerText();
  await none.close();
  assert.ok(t2.includes(APP_WORDS.tasks_empty) && t2.includes(APP_WORDS.no_versions));
});

await check("Start a task sends ONE app_task_start and opens the task", async () => {
  const page = await appPage(appObj({ tasks: [] }), { answers: { app_task_start: { status: 200,
    body: { ok: true, task: summary(T1, "Add a search box") } } } });
  await page.locator("#projects-task-title").fill("  Add a search box ");
  await page.getByRole("button", { name: APP_WORDS.start_task }).click();
  await page.waitForTimeout(500);
  const heading = await page.locator("#projects-task-heading").textContent();
  const sent = await calls(page);
  await page.close();
  assert.deepEqual(sent, [["projects_write", { action: "app_task_start", project: APP_ID,
    body: { title: "Add a search box" } }]]);
  assert.equal(heading, "Add a search box");
});

await check("the Task view shows the WHOLE change as text, green and red; nothing becomes markup", async () => {
  assert.ok(BIG.length > 50000 && BIG.length < 60001, `test change is ${BIG.length} characters`);
  const page = await appPage(appObj());
  await openTask(page);
  const shown = await page.locator("#projects-diff").evaluate((p) => p.textContent);
  const spans = await page.locator("#projects-diff .pj-d").count();
  const adds = await page.locator("#projects-diff .pj-d-add").count();
  const dels = await page.locator("#projects-diff .pj-d-del").count();
  const markup = await page.locator("#projects-diff b").count();
  const files = await page.locator(".pj-task-files .row-item").allInnerTexts();
  const colours = await page.evaluate(() => ({
    add: getComputedStyle(document.querySelector(".pj-d-add")).backgroundColor,
    del: getComputedStyle(document.querySelector(".pj-d-del")).backgroundColor,
  }));
  const region = await page.locator("#projects-diff").getAttribute("role");
  const errors = page.__errors;
  await page.close();
  assert.equal(shown, BIG, "the diff on screen is not the whole diff");
  assert.equal(spans, BIG_LINES.length);
  assert.equal(adds, 1120, "added lines (the +++ header is not one)");
  assert.equal(dels, 280, "removed lines (the --- header is not one)");
  assert.equal(markup, 0, "a <b> in the change became markup");
  assert.equal(files.length, 2);
  assert.match(files[0], /src\/big\.js[\s\S]*\+1120 -280/);
  assert.notEqual(colours.add, colours.del, "added and removed look the same");
  assert.equal(region, "region");
  assert.deepEqual(errors, []);
});

await check("Merge sends ONE app_task_merge and shows the PC's words; the page never approves", async () => {
  const say = "A card is waiting for your yes. Approve it in the Jarvis bar.";
  const page = await appPage(appObj(), { answers: { app_task_merge: { status: 202,
    body: { ok: true, waiting: true, message: say } } } });
  await openTask(page);
  const how = await page.locator(".pj-task .note").allInnerTexts();
  await page.locator("#projects-task-merge").click();
  await page.waitForTimeout(400);
  const said = await page.locator("#projects-said").innerText();
  const sent = await calls(page);
  const approvers = await page.getByRole("button", { name: /approve/i }).count();
  await page.close();
  assert.ok(how.includes(APP_WORDS.merge_how));
  assert.deepEqual(sent, [["projects_write", { action: "app_task_merge", project: APP_ID, task: T1, body: {} }]]);
  assert.equal(said, say);
  assert.equal(approvers, 0, "this page has an Approve button");
});

await check("a pasted task says so; pasting sends the blocks", async () => {
  const page = await appPage(appObj());
  await openTask(page, "Rename the header");
  const text = await page.locator("#projects-root").innerText();
  const blocks = "<<<FILE src/App.tsx>>>\nexport const x = 1;\n<<<END>>>\n<<<DELETE old.txt>>>";
  await page.locator("#projects-paste").fill(blocks);
  await page.locator("#projects-paste-go").click();
  await page.waitForTimeout(400);
  await page.locator("#projects-paste").fill("   ");
  await page.locator("#projects-paste-go").click();
  await page.waitForTimeout(300);
  const said = await page.locator("#projects-said").innerText();
  const sent = await calls(page);
  await page.close();
  assert.ok(text.includes(APP_WORDS.merge_pasted));
  assert.deepEqual(sent, [["projects_write", { action: "app_task_files", project: APP_ID, task: T2,
    body: { blocks } }]]);
  assert.equal(said, APP_WORDS.paste_empty);
});

await check("after a pasted change goes through, the box is empty (a second press must not add it twice)", async () => {
  // Bug audit 2026-09-29: the repaint that follows every change redrew the
  // box with the same change still in it, because the text was dropped after.
  const page = await appPage(appObj());
  await openTask(page, "Rename the header");
  await page.locator("#projects-paste").fill("<<<FILE src/App.tsx>>>\nexport const x = 1;\n<<<END>>>");
  await page.locator("#projects-paste-go").click();
  await page.waitForTimeout(500);
  const left = await page.locator("#projects-paste").inputValue();
  await page.close();
  assert.equal(left, "");
});

await check("merge waiting: the task says so, Merge and paste are greyed, another task's Merge too", async () => {
  const app = appObj({ merge: { waiting: T1, last: null } });
  app.tasks[0].waiting = true;
  const page = await appPage(app, { tasks: { [T1]: detail(T1, { waiting: true }),
    [T2]: detail(T2, { title: "Rename the header" }) } });
  const list = await page.locator("#projects-root").innerText();
  await openTask(page);
  const merge = await page.locator("#projects-task-merge").isDisabled();
  const paste = await page.locator("#projects-paste-go").isDisabled();
  const discard = await page.locator("#projects-task-discard").isEnabled();
  const text = await page.locator("#projects-root").innerText();
  await page.getByRole("button", { name: `← ${APP_WORDS.back_project}` }).click();
  await page.waitForTimeout(300);
  await openTask(page, "Rename the header");
  const other = await page.locator("#projects-task-merge").isDisabled();
  const otherWhy = await page.locator(".pj-task .note").allInnerTexts();
  await page.close();
  assert.ok(list.includes(APP_WORDS.task_waiting) && list.includes(WORDS.waiting_card));
  assert.equal(merge, true);
  assert.equal(paste, true);
  assert.equal(discard, true, "Discard withdraws the card, so it stays");
  assert.ok(text.includes(WORDS.waiting_card));
  assert.equal(other, true);
  assert.ok(otherWhy.includes(APP_WORDS.merge_blocked_card));
});

await check("every merge outcome shows the PC's fixed sentence, in the project and in the task", async () => {
  for (const [outcome, message] of Object.entries(OUTCOMES)) {
    const app = appObj({ merge: { waiting: null, last: { task: T1, outcome, message, at: 1759000100.0 } } });
    const page = await appPage(app);
    const inProject = await page.locator(".pj-merge-last").innerText();
    const tag = await page.locator(".pj-merge-last").getAttribute("data-outcome");
    await openTask(page);
    const inTask = await page.locator(".pj-task .pj-merge-last").innerText();
    await page.close();
    assert.equal(inProject, message, outcome);
    assert.equal(tag, outcome);
    assert.equal(inTask, message, outcome);
  }
});

await check("a change that cannot be shown whole raises no card: Merge greyed with the reason", async () => {
  const why = "This change is too big to show on one card - ask Jarvis to split it into smaller steps.";
  const page = await appPage(appObj(), { tasks: { [T1]: detail(T1, { diff: "", too_big: true, refused: why }) } });
  await openTask(page);
  const merge = await page.locator("#projects-task-merge").isDisabled();
  const text = await page.locator("#projects-root").innerText();
  await page.close();
  assert.equal(merge, true);
  assert.ok(text.includes(why));
});

await check("a stale link greys Start, Merge, Discard, paste and Add; Open and Back still work", async () => {
  const page = await appPage(appObj(), { link: { stale: true } });
  const start = await page.getByRole("button", { name: APP_WORDS.start_task }).isDisabled();
  const open = await page.getByRole("button", { name: `${APP_WORDS.task_open}: Add a search box` }).isEnabled();
  await openTask(page);
  const merge = await page.locator("#projects-task-merge").isDisabled();
  const discard = await page.locator("#projects-task-discard").isDisabled();
  const paste = await page.locator("#projects-paste-go").isDisabled();
  const title = await page.locator("#projects-task-merge").getAttribute("title");
  const back = await page.getByRole("button", { name: `← ${APP_WORDS.back_project}` }).isEnabled();
  const sent = await calls(page);
  await page.close();
  assert.equal(start, true);
  assert.equal(open, true, "opening a task is a read");
  assert.equal(merge && discard && paste, true);
  assert.equal(title, WORDS.stale);
  assert.equal(back, true);
  assert.deepEqual(sent, []);
  const list = await projectsTab({ list: appList(), link: { stale: true } });
  const add = await list.getByRole("button", { name: "Add Old game" }).isDisabled();
  await list.close();
  assert.equal(add, true);
});

await check("Discard asks \"are you sure?\" first; No sends nothing; Yes sends ONE discard and goes back", async () => {
  const page = await appPage(appObj());
  await openTask(page);
  let question = "";
  page.on("dialog", (d) => { question = d.message(); });
  page.__confirm = false;
  await page.locator("#projects-task-discard").click();
  await page.waitForTimeout(300);
  const none = await calls(page);
  page.__confirm = true;
  await page.locator("#projects-task-discard").click();
  await page.waitForTimeout(500);
  const sent = await calls(page);
  const back = await page.locator("#projects-heading").count();
  await page.close();
  assert.equal(question, APP_WORDS.discard_q);
  assert.deepEqual(none, []);
  assert.deepEqual(sent, [["projects_write", { action: "app_task_discard", project: APP_ID, task: T1, body: {} }]]);
  assert.equal(back, 1, "not back on the project after discarding");
});

await check("Delete on an app project: the words say the files stay, and the answer is said", async () => {
  const page = await appPage(appObj(), { answers: { delete: { status: 200,
    body: { ok: true, deleted: true, app_kept: "notes" } } } });
  let question = "";
  page.on("dialog", (d) => { question = d.message(); });
  await page.getByRole("button", { name: WORDS.delete_project }).click();
  await page.waitForTimeout(500);
  const said = await page.locator("#projects-said").innerText();
  const sent = await calls(page);
  await page.close();
  assert.equal(question, APP_WORDS.delete_app_project_q.replace("{name}", "Notes app"));
  assert.match(question, /files stay on this PC and can be added back/);
  assert.deepEqual(sent, [["projects_write", { action: "delete", project: APP_ID }]]);
  assert.equal(said, APP_WORDS.deleted_app_kept);
});

await check("a command benchmark of an app project says Jarvis cannot run it yet", async () => {
  const p = appProject(appObj(), { benchmarks: 1, benchmark_list: [CODING.benchmark_list.find((b) => b.kind === "command")] });
  const page = await projectsTab({ list: appList(), projects: { [LIFE.id]: C.life, [CODING.id]: C.coding, [APP_ID]: wrap(p) },
    tasks: {} });
  await page.getByRole("button", { name: "Open Notes app" }).click();
  await page.waitForTimeout(400);
  const text = await page.locator("#projects-root").innerText();
  await page.close();
  assert.ok(text.includes(APP_WORDS.cant_run));
});

await check("hidden with the private lists: no app, no task, no change text on the page", async () => {
  const page = await projectsTab({ list: { ok: true, hidden: true, hidden_count: 3 } });
  const text = await page.locator("#projects-root").innerText();
  await page.close();
  assert.match(text, /3 projects, hidden until Windows Hello confirms it is you\./);
  assert.doesNotMatch(text, /Notes app|Add a search box|const line/);
  // A project read that comes back hidden while a task is open closes the task
  // view and shows only "Show" (Rust redacts the answer; see projects.rs tests).
  const open = await appPage(appObj());
  await openTask(open);
  await open.evaluate(() => {
    const core = window.__TAURI__.core;
    const inner = core.invoke;
    core.invoke = async (cmd, args) => (cmd === "projects_read" && args.project
      ? { ok: true, hidden: true } : inner(cmd, args));
  });
  await open.evaluate(() => window.__TAURI__.event && 0);
  await open.getByRole("button", { name: `← ${APP_WORDS.back_project}` }).click();
  await open.waitForTimeout(400);
  const after = await open.locator("#projects-root").innerText();
  await open.close();
  assert.doesNotMatch(after, /Add a search box|const line|Rename the header/);
});

await check("a11y: the Task view's controls are named, the change is a named region", async () => {
  const page = await appPage(appObj());
  await openTask(page);
  const bad = await page.evaluate(() => {
    const out = [];
    const rootEl = document.getElementById("projects-root");
    const nameOf = (e) => (e.getAttribute("aria-label") || (e.labels && e.labels[0]
      && e.labels[0].textContent) || e.textContent || e.title || "").trim();
    for (const e of rootEl.querySelectorAll("button, input, select, textarea, [role=region]")) {
      if (!nameOf(e)) out.push(e.outerHTML.slice(0, 80));
    }
    if (!document.getElementById("projects-task-heading")) out.push("no heading");
    return out;
  });
  const focused = await page.evaluate(() => document.activeElement && document.activeElement.id);
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(bad, []);
  assert.equal(focused, "projects-task-heading", "opening a task did not move focus to its heading");
  assert.deepEqual(errors, []);
});

await check("the sentences the PC shares about apps (projects-cases.json app_words) are the page's own", async () => {
  const W = CASES.app_words;
  assert.ok(W && W.outcomes, "the shared file has app_words");
  assert.equal(APP_WORDS.cant_run, W.cant_run);
  assert.equal(APP_WORDS.merge_blocked_card, W.card_waiting);
  assert.equal(APP_WORDS.merge_pasted, W.pasted_line);
  assert.equal(APP_WORDS.delete_app_project_q, W.delete_app_project_q);
  assert.equal(APP_WORDS.deleted_app_kept, W.deleted_app_kept);
  // The nine merge outcomes are the PC's to send; the page shows them as they come,
  // so the hand-made answers above must use the same ones ("refused" adds the gate's reason).
  assert.deepEqual(Object.keys(W.outcomes).sort(), Object.keys(OUTCOMES).sort());
  for (const k of Object.keys(OUTCOMES)) {
    if (k === "refused") assert.ok(OUTCOMES[k].startsWith(W.outcomes[k]), k);
    else assert.equal(OUTCOMES[k], W.outcomes[k], k);
  }
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed` : "\nall projects checks passed");
process.exit(fails.length ? 1 : 0);
