/**
 * The HUD's left rail: the owner's five focus presets + ONE Cloud button
 * (owner request 2026-10-21, replacing the "BRAIN IN USE" lane boxes).
 *
 *   node tests/hud-presets.mjs
 *
 * WHAT IS PROVEN, in the real page (jarvis_hud.html) with the PC stubbed:
 *
 *   - the rail lists the PC's five presets in the contract's order/titles
 *     (`backend/fixtures/work_presets.json`, generated from jarvis_presets.py),
 *     and marks the one `chosen_preset` names - never one before that;
 *   - a click posts /api/work/apply ONCE with {"preset": "<id>"} - the same
 *     route and body the bar's "Use this preset" sends - and after the PC
 *     answers the list is refetched and the highlight follows the contract;
 *   - the card decision really flows: while the apply waits, the PC's card
 *     appears in #approvals and Approve posts /api/approve, then the rail
 *     marks the applied preset;
 *   - the NEXT chat body is an ordinary routed turn: auto:true and no lane
 *     override (bar/phone send the same; the applied preset lives on the PC,
 *     which is why /api/presets' own chosen_preset/active_lane is the record);
 *   - Cloud routes the next message through the lane mechanism the rail
 *     always had: the next chat body carries lane:"jarvis-escalate",
 *     auto:false, and the button is marked active - only while
 *     /api/status says proxy:true;
 *   - with proxy:false, Cloud says plainly that the cloud lane is down, marks
 *     nothing, and the next chat body stays an ordinary local turn;
 *   - a PC without the presets route gets plain words, not invented presets;
 *   - #lanes and #lane-compact are still there and still work (the Studio
 *     dock's dropdown and the page's own lane tests drive them), and the
 *     three vendored copies of the page stay byte-identical.
 *
 * NOT here: the real desktop window and WebView2 painting (a rebuild+install
 * is needed after merge), and what the PC does with the card itself - that is
 * backend/jarvis_presets.py and its own suites.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { launch } from "./uikit.mjs";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const SRC = join(HERE, "..", "src");
const FIXTURE = JSON.parse(
  readFileSync(join(HERE, "..", "..", "backend", "fixtures", "work_presets.json"), "utf8"));
const CLOUD_LANES = ["jarvis-escalate", "jarvis-critic", "jarvis-bulk"];

let PASSED = 0, FAILED = 0;
async function check(name, fn) {
  try {
    await fn();
    PASSED += 1;
    console.log("ok   " + name);
  } catch (e) {
    FAILED += 1;
    console.log("FAIL " + name + "\n     " + (e && e.message ? e.message : e));
  }
}

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".woff2": "font/woff2", ".woff": "font/woff" };
const ORIGIN = "http://127.0.0.1:4719";

function fixturePayload(chosen = null) {
  const presets = JSON.parse(JSON.stringify(FIXTURE.presets));
  const chosenPreset = chosen ? presets.find((p) => p.id === chosen) || null : null;
  return {
    found: "5 focus presets",
    presets,
    chosen: chosen,
    chosen_preset: chosen,
    chosen_model: chosenPreset ? chosenPreset.model : null,
    active_lane: { key: chosenPreset ? chosenPreset.lane.key : null, base_url: "" },
    lane: chosenPreset
      ? { key: chosenPreset.lane.key, card: chosenPreset.lane.card, words: chosenPreset.lane.words,
          label: chosenPreset.lane.card + " · " + chosenPreset.lane.words, ready: true, why: "" }
      : { key: null, card: "", words: "", label: "", ready: false, why: "no preset has been applied on this PC yet" },
    lane_status: { ready: !!chosenPreset },
    apply_path: "/api/work/apply",
    switch_path: "/api/models/switch",
    auto: false,
  };
}

/**
 * The page, served as Tauri serves it (same-origin static files), with the PC
 * stubbed. Everything the page asks for is answered on this origin, so the
 * page's own JARVIS.url() base is "" - the same same-origin shape the plain
 * browser fallback uses.
 */
async function openHud(browser, options = {}) {
  const state = {
    proxy: options.proxy !== false,
    payload: fixturePayload(options.chosen || null),
    presetsAvailable: options.presetsAvailable !== false,
    applyMode: options.applyMode || "ok",       // ok | hold | refuse
    applyBody: null,
    applyWait: null,                            // resolves when hold is released
    pending: [],
    decisions: [],
    chats: [],
    lane: options.lane || "auto",
  };
  const problems = [];
  const page = await browser.newPage({ viewport: options.viewport || { width: 1280, height: 820 } });
  page.on("pageerror", (e) => problems.push(String(e)));
  page.on("console", (m) => {
    if (m.type() === "error" && /Content Security Policy|Refused to/.test(m.text())) problems.push(m.text());
  });
  const cors = { "Access-Control-Allow-Origin": ORIGIN, "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS" };
  const json = (route, status, body, extra = {}) =>
    route.fulfill({ status, headers: { ...cors, "Content-Type": "application/json", ...extra },
      body: JSON.stringify(body) });
  const file = (route, url) => {
    const path = join(SRC, decodeURIComponent(url.pathname));
    if (!path.startsWith(SRC)) return route.fulfill({ status: 404, body: "" });
    try {
      const body = readFileSync(path);
      return route.fulfill({ status: 200, headers: { "Content-Type": TYPES[path.slice(path.lastIndexOf("."))] || "application/octet-stream" }, body });
    } catch (e) {
      return route.fulfill({ status: 404, body: "" });
    }
  };
  await page.route("**/*", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    if (url.origin !== ORIGIN) return route.abort();
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
    if (url.pathname === "/jarvis_hud.html" || url.pathname === "/") return file(route, { pathname: "/jarvis_hud.html" });
    if (url.pathname.startsWith("/api/")) {
      if (url.pathname === "/api/status") {
        return json(route, 200, { ollama: true, proxy: state.proxy, lanes: CLOUD_LANES,
          default_model: "qwen3.5:9b", tools: 12, budget: null });
      }
      if (url.pathname === "/api/pending") {
        return json(route, 200, { available: true, pending: state.pending, history: [] });
      }
      if (url.pathname === "/api/presets" || url.pathname === "/api/work") {
        if (!state.presetsAvailable) return json(route, 404, { error: "not found" });
        return json(route, 200, state.payload);
      }
      if (url.pathname === "/api/work/apply" && req.method() === "POST") {
        state.applyBody = JSON.parse(req.postData() || "{}");
        const chosen = state.applyBody.preset;
        if (state.applyMode === "refuse") {
          return json(route, 409, { ok: false, changed: false,
            error: "the Coding preset is being prepared; nothing was changed" });
        }
        if (state.applyMode === "hold") {
          // The PC raises its ONE card and the POST waits for the owner. The
          // page's 30 s poll (and apprPoll on the event) paints it; the test
          // clicks Approve, which posts /api/approve - then this resolves.
          state.pending = [{ id: 42, action: "switch_model", raised: { text: "Switch the model for Coding?" },
            source: "the HUD", reversible: "yes", reach: "local" }];
          await new Promise((resolve) => { state.applyWait = resolve; });
          state.pending = [];
        }
        state.payload = fixturePayload(chosen);
        return json(route, 200, { ok: true, changed: true, preset: state.payload.presets.find((p) => p.id === chosen),
          lane: state.payload.lane, base_url: "http://127.0.0.1:11436",
          model: state.payload.chosen_model, previous_preset: null });
      }
      if ((url.pathname === "/api/approve" || url.pathname === "/api/deny") && req.method() === "POST") {
        state.decisions.push({ path: url.pathname, body: JSON.parse(req.postData() || "{}") });
        if (state.applyWait) { const done = state.applyWait; state.applyWait = null; done(); }
        return json(route, 200, { ok: true });
      }
      if (url.pathname === "/api/chat" && req.method() === "POST") {
        state.chats.push(JSON.parse(req.postData() || "{}"));
        return route.fulfill({ status: 200,
          headers: { ...cors, "Content-Type": "text/event-stream",
            "X-Jarvis-Route": JSON.stringify({ lane: state.lane, where: "local" }),
            "Access-Control-Expose-Headers": "X-Jarvis-Route" },
          body: 'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n' });
      }
      return json(route, 404, { error: "not in this test" });
    }
    return file(route, url);
  });
  await page.goto(`${ORIGIN}/jarvis_hud.html`);
  await page.waitForTimeout(900);
  return { page, state, problems };
}

async function presetRows(page) {
  return page.evaluate(() =>
    [...document.querySelectorAll("#presets .preset")].map((b) => ({
      id: b.dataset.preset,
      title: b.querySelector(".preset-name").textContent,
      model: b.querySelector(".preset-model").textContent,
      pressed: b.getAttribute("aria-pressed"),
    })));
}

async function sendChat(page, text = "hello there") {
  await page.evaluate((t) => {
    document.getElementById("input").value = t;
    window.send();
  }, text);
  await page.waitForTimeout(700);
}

const browser = await launch();

await check("the rail lists the PC's five presets in the contract's order, titles and models", async () => {
  const { page, problems } = await openHud(browser);
  const rows = await presetRows(page);
  await page.close();
  assert.equal(rows.length, 5, "the rail does not show five presets");
  assert.deepEqual(rows.map((r) => r.id), FIXTURE.presets.map((p) => p.id), "preset order drifted from the PC's contract");
  assert.deepEqual(rows.map((r) => r.title), FIXTURE.presets.map((p) => p.title), "preset titles drifted");
  assert.deepEqual(rows.map((r) => r.model), FIXTURE.presets.map((p) => p.model), "models drifted");
  assert.deepEqual(problems, []);
});

await check("no preset is marked chosen until the PC's contract says so", async () => {
  const { page, problems } = await openHud(browser);   // chosen: null
  const rows = await presetRows(page);
  const words = await page.evaluate(() => document.getElementById("preset-words").textContent);
  await page.close();
  assert.ok(rows.every((r) => r.pressed === "false"), "a preset was marked before the PC named it");
  assert.match(words, /No preset chosen yet/, words);
  assert.deepEqual(problems, []);
});

await check("the chosen preset is the highlighted one, with its model on the status line", async () => {
  const { page, problems } = await openHud(browser, { chosen: "coding" });
  const rows = await presetRows(page);
  const words = await page.evaluate(() => document.getElementById("preset-words").textContent);
  await page.close();
  assert.deepEqual(rows.filter((r) => r.pressed === "true").map((r) => r.id), ["coding"], "the chosen preset is not the pressed one");
  assert.match(words, /Chosen: Coding/, words);
  assert.deepEqual(problems, []);
});

await check("a click posts /api/work/apply once with the right preset id, then marks the PC's answer", async () => {
  const { page, state, problems } = await openHud(browser);
  await page.click('#presets .preset[data-preset="coding"]');
  await page.waitForTimeout(700);
  const rows = await presetRows(page);
  const words = await page.evaluate(() => document.getElementById("preset-words").textContent);
  await page.close();
  assert.equal(state.applyBody && state.applyBody.preset, "coding", "the apply body did not name the clicked preset");
  assert.deepEqual(rows.filter((r) => r.pressed === "true").map((r) => r.id), ["coding"], "the rail did not mark the preset the PC now names chosen");
  assert.match(words, /Now using Coding/, words);
  assert.deepEqual(problems, []);
});

await check("the PC's card really flows: it paints in #approvals, Approve decides, and the rail follows", async () => {
  const { page, state, problems } = await openHud(browser, { applyMode: "hold" });
  // H4 (2026-10-22): the safety rail holds Approve until the shell has said the
  // link is live (an unknown link is not offered an Approve). This harness serves
  // the page without the bootstrap, so push the same verdict the bootstrap sends
  // before touching the card - the behaviour under test is the preset flow, not
  // the boot hold.
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("jarvis-link-status", {
    detail: { up: true, words: "linked", short: "linked", tone: "ok" },
  })));
  await page.waitForTimeout(150);
  await page.click('#presets .preset[data-preset="general"]');
  // The apply POST is waiting on the PC's ONE change_own_config card. The page
  // paints cards from #approvals on the shell's `approval` event (and on its
  // 30 s beat) - with no shell in this harness, call the same poll the event
  // calls, exactly as the real page does when the card is raised.
  await page.waitForFunction(() => typeof window.apprPoll === "function");
  await page.evaluate(() => window.apprPoll());
  await page.waitForSelector("#approvals .appr", { timeout: 5000 });
  const card = await page.evaluate(() => {
    const el = document.querySelector("#approvals .appr");
    return { shown: getComputedStyle(document.getElementById("approvals")).display !== "none",
      text: el ? el.textContent : "" };
  });
  await page.click("#approvals .appr .yes");
  await page.waitForTimeout(900);
  const rows = await presetRows(page);
  await page.close();
  assert.equal(card.shown, true, "the approval queue stayed hidden while a card waited");
  assert.match(card.text, /Switch the model/, "the card's own words did not reach the queue");
  assert.deepEqual(state.decisions.map((d) => d.path), ["/api/approve"], "Approve did not post /api/approve");
  assert.deepEqual(rows.filter((r) => r.pressed === "true").map((r) => r.id), ["general"],
    "the rail did not mark the preset after the card was approved");
  assert.deepEqual(problems, []);
});

await check("the NEXT chat body is an ordinary routed turn (auto, no lane override), like the bar and phone", async () => {
  const { page, state, problems } = await openHud(browser);
  await page.click('#presets .preset[data-preset="coding"]');
  await page.waitForTimeout(700);
  await sendChat(page, "what is this preset doing");
  const body = state.chats[state.chats.length - 1] || {};
  await page.close();
  assert.equal(state.applyBody && state.applyBody.preset, "coding", "the apply never happened");
  assert.equal(body.auto, true, "the next turn is not a routed turn (auto:true)");
  assert.equal(body.lane, null, "the page kept its own lane override after applying a preset - it would override the PC's active lane");
  assert.equal(body.device, "hud");
  assert.equal(body.stream, true);
  assert.deepEqual(problems, []);
});

await check("Cloud routes the next message through the cloud lane, and the body carries it", async () => {
  const { page, state, problems } = await openHud(browser, { proxy: true });
  await page.click("#preset-cloud");
  await page.waitForTimeout(300);
  const cloud = await page.evaluate(() => ({
    pressed: document.getElementById("preset-cloud").getAttribute("aria-pressed"),
    down: document.getElementById("preset-cloud").classList.contains("down"),
    words: document.getElementById("preset-words").textContent,
    chip: document.getElementById("chip-model").textContent,
  }));
  await sendChat(page, "escalate this one");
  const body = state.chats[state.chats.length - 1] || {};
  await page.close();
  assert.equal(cloud.pressed, "true", "Cloud did not mark itself active while the proxy is up");
  assert.equal(cloud.down, false, "Cloud is drawn as down while the proxy is up");
  assert.match(cloud.words, /next message goes to the cloud/i, cloud.words);
  assert.match(cloud.chip, /^cloud/, cloud.chip);
  assert.equal(body.lane, "jarvis-escalate", "the next chat body does not carry the cloud lane");
  assert.equal(body.auto, false, "a routed cloud turn must not be auto");
  assert.deepEqual(problems, []);
});

await check("Cloud with the proxy DOWN says so plainly, marks nothing, and switches nothing", async () => {
  const { page, state, problems } = await openHud(browser, { proxy: false });
  await page.click("#preset-cloud");
  await page.waitForTimeout(300);
  const cloud = await page.evaluate(() => ({
    pressed: document.getElementById("preset-cloud").getAttribute("aria-pressed"),
    down: document.getElementById("preset-cloud").classList.contains("down"),
    title: document.getElementById("preset-cloud").title,
    words: document.getElementById("preset-words").textContent,
  }));
  await sendChat(page, "still local");
  const body = state.chats[state.chats.length - 1] || {};
  await page.close();
  assert.equal(cloud.pressed, "false", "Cloud marked itself active while the proxy is down");
  assert.equal(cloud.down, true, "Cloud does not show the down state");
  assert.match(cloud.title, /down/i, cloud.title);
  assert.match(cloud.words, /cloud lane is down/i, cloud.words);
  assert.equal(body.auto, true, "the down Cloud button changed the routing");
  assert.equal(body.lane, null, "the down Cloud button sent a lane");
  assert.deepEqual(problems, []);
});

await check("a PC without the presets route gets plain words, not invented presets", async () => {
  const { page, problems } = await openHud(browser, { presetsAvailable: false });
  const rail = await page.evaluate(() => ({
    presets: document.querySelectorAll("#presets .preset").length,
    words: document.getElementById("preset-words").textContent,
  }));
  await page.close();
  assert.equal(rail.presets, 0, "invented preset buttons appeared without the PC's contract");
  assert.match(rail.words, /did not list its focus presets/i, rail.words);
  assert.deepEqual(problems, []);
});

await check("the tested ids survive: #lanes is still there (hidden) and the Studio dropdown still drives it", async () => {
  const { page, problems } = await openHud(browser);
  const kept = await page.evaluate(() => {
    const lanes = document.getElementById("lanes");
    const buttons = [...document.querySelectorAll("#lanes .lane")];
    const select = document.getElementById("lane-compact");
    const before = buttons.filter((b) => b.getAttribute("aria-pressed") === "true").map((b) => b.dataset.lane);
    const want = select.options[select.options.length - 1].value;
    select.value = want;
    select.dispatchEvent(new Event("change", { bubbles: true }));
    const after = [...document.querySelectorAll("#lanes .lane")]
      .filter((b) => b.getAttribute("aria-pressed") === "true").map((b) => b.dataset.lane);
    return { lanes: !!lanes, hidden: lanes ? lanes.hidden : false,
      buttons: buttons.length, options: select.options.length, before, after, want };
  });
  await page.close();
  assert.equal(kept.lanes, true, "#lanes was removed");
  assert.equal(kept.hidden, true, "#lanes is visible again (the presets took the rail)");
  assert.ok(kept.buttons >= 2, "the lane buttons went away");
  assert.equal(kept.options, kept.buttons, "the Studio dropdown and the lane buttons disagree");
  assert.deepEqual(kept.after, [kept.want], "the Studio dropdown no longer chooses a lane");
  assert.deepEqual(problems, []);
});

await check("at 960x640 the cockpit rail does not overflow, and all three layouts still pick", async () => {
  const { page, problems } = await openHud(browser, { viewport: { width: 960, height: 640 } });
  const out = await page.evaluate(async () => {
    const pick = (name) => {
      const b = document.querySelector(`[data-hud-layout-choice="${name}"]`);
      if (b) b.click();
    };
    const res = {};
    for (const name of ["cockpit", "studio", "ambient"]) {
      pick(name);
      await new Promise((r) => setTimeout(r, 150));
      res[name] = { scroll: document.documentElement.scrollWidth, inner: window.innerWidth,
        presetShown: !!document.querySelector("#presets .preset") &&
          getComputedStyle(document.getElementById("presets")).display !== "none" };
    }
    pick("cockpit");
    return res;
  });
  await page.close();
  for (const name of ["cockpit", "studio", "ambient"]) {
    assert.ok(out[name].scroll <= out[name].inner + 1,
      `${name} overflows horizontally at 960 px (${out[name].scroll} > ${out[name].inner})`);
  }
  assert.equal(out.cockpit.presetShown, true, "the cockpit rail does not show the presets");
  assert.deepEqual(problems, []);
});

await check("the three vendored copies of the page stay byte-identical", async () => {
  const desk = readFileSync(join(HERE, "..", "src", "jarvis_hud.html"));
  const base = readFileSync(join(HERE, "..", "..", "jarvis-backend", "jarvis_hud.html"));
  const backend = readFileSync(join(HERE, "..", "..", "backend", "jarvis_hud.html"));
  assert.ok(desk.equals(base), "jarvis-desktop/src/jarvis_hud.html and jarvis-backend/jarvis_hud.html differ");
  assert.ok(desk.equals(backend), "jarvis-desktop/src/jarvis_hud.html and backend/jarvis_hud.html differ");
});

await browser.close();
console.log(`\n${PASSED} passed, 0 skipped, ${FAILED} failed`);
if (FAILED) process.exit(1);
