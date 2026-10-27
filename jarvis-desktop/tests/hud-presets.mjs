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
 *   - a SUCCESSFUL apply re-renders the page's lanes without throwing (P1-3 of
 *     the 2026-10-27 HUD audit: the three old lane modes are gone, but
 *     renderLanes() is still called from the apply and #lanes must stay);
 *   - Coding, which the PC always refuses (heavy mode), is NOT a button: it is
 *     drawn with the phone's own sentence, and the stub refuses it as the real
 *     PC does (contract audit F1 - the old stub pinned a fiction);
 *   - the top-right model name is the door to the Current Models panel, and
 *     Ambient's pill is a second door to the same panel (HUD audit P1-1/P1-2);
 *   - the panel says plainly when the PC has nothing loaded or did not answer,
 *     and opening it reads exactly /api/models, /api/status and /api/presets -
 *     no POST, no card, no model switch;
 *   - the Cloud section: the row sits after the five, opens a provider
 *     submenu (no POST), picking a ready provider posts ONE apply with the
 *     provider id, a provider with no key is words and its PC command and posts
 *     nothing, and the mark comes from the refetched `cloud.provider`;
 *   - the escalate checkbox is drawn from the PC's `cloud.escalate.on`, never
 *     from the click; a click posts ONE boolean, a refused card leaves it
 *     unticked after the refetch, and the rest of the menu stays usable;
 *   - #lanes still exists and the three vendored copies of the page stay
 *     byte-identical.
 *   - the card decision really flows: while the apply waits, the PC's card
 *     appears in #approvals and Approve posts /api/approve, then the rail
 *     marks the applied preset;
 *   - the NEXT chat body is an ordinary routed turn: auto:true and no lane
 *     override (bar/phone send the same; the applied preset lives on the PC,
 *     which is why /api/presets' own chosen_preset/active_lane is the record) -
 *     and it carries `cloud_yes` ONLY while the PC's escalate switch is on;
 *   - Cloud routes the next message through the lane mechanism the rail
 *     always had: the next chat body carries lane:"jarvis-escalate",
 *     auto:false, and the button is marked active - only while
 *     /api/status says proxy:true;
 *   - with proxy:false, Cloud says plainly that the cloud lane is down, marks
 *     nothing, and the next chat body stays an ordinary local turn;
 *   - a PC without the presets route gets plain words, not invented presets.
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
// The ONE lane name the PC keeps (2026-10-27): escalate / critic / bulk are no
// longer modes, and only jarvis-escalate still exists for the Cloud button.
const CLOUD_LANES = ["jarvis-escalate"];
const PERSONALITIES = JSON.parse(
  readFileSync(join(HERE, "..", "..", "contract", "personalities.json"), "utf8"));

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
    // The Cloud section (2026-10-27): the shape the server is adding - one
    // chosen provider, the services it has keys for, and the PC's own
    // escalate switch. Two rows: one ready and one with no key, so the menu's
    // "not a button" rule is proved against a real answer.
    cloud: {
      provider: "",
      providers: [
        { id: "deepseek_api", short: "deepseek", name: "DeepSeek (API)",
          company: "DeepSeek", host: "api.deepseek.com", model: "deepseek-flash",
          key_saved: true, ready: true, why: "", chosen: false,
          money: { company: "DeepSeek", limit: "$10.00", left: "$9.10", spent: "$0.90",
            until: "2026-11-01", reached: false },
          key_line: "py -3 jarvis_chatbot_api.py key deepseek",
          key_where: "https://platform.deepseek.com/api_keys" },
        { id: "groq_api", short: "groq", name: "Groq (API)",
          company: "Groq", host: "api.groq.com", model: "llama-3.3-70b",
          key_saved: false, ready: false, why: "no key is saved on this PC", chosen: false,
          money: null, key_line: "py -3 jarvis_chatbot_api.py key groq",
          key_where: "https://console.groq.com/keys" },
      ],
      escalate: { on: false, why: "" },
    },
  };
}

/**
 * The PC's own manner answer (GET /api/manner), in the shape the HUD reads:
 * the nine personalities from the contract, the current one, and the owner's
 * own list. No card is involved anywhere in this stub - that is the point of
 * the personality half.
 */
function mannerPayload(current = PERSONALITIES.default, mine = []) {
  return {
    available: true,
    personality: current,
    personalities: [
      ...PERSONALITIES.personalities.map((p) => ({
        id: p.id, title: p.title, description: p.description, builtin: true,
      })),
      // The PC's own list already carries the saved ones too, marked
      // `builtin: false` (`jarvis_manner.py` `all_personalities`) - the menu
      // must split them out on that flag, not draw them twice.
      ...mine.map((row) => ({
        id: row.id, title: row.name, description: row.line || "", builtin: false,
      })),
    ],
    user_personalities: mine,
    custom_personalities: mine,
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
    manner: mannerPayload(options.personality || PERSONALITIES.default,
      options.userPersonalities || []),
    mannerAvailable: options.mannerAvailable !== false,
    mannerBody: null,
    mannerPosts: [],
    applyMode: options.applyMode || "ok",       // ok | hold | refuse
    applyBody: null,
    applyPosts: [],
    applyWait: null,                            // resolves when hold is released
    // The PC's own escalate switch (2026-10-27): its mode is how the synthetic
    // PC answers, never what the page may assume.
    escalateMode: options.escalateMode || "ok", // ok | refuse | waiting
    escalatePosts: [],
    pending: [],
    decisions: [],
    chats: [],
    lane: options.lane || "auto",
    // The Current Models panel's three reads (2026-10-26). `/api/models` is
    // answered like the real backend's body: `current`/`previous` plus the
    // `offload` block gpu-offload.patch puts on it. `reads` records every
    // /api/ request, so a test can prove the panel added no route and no write.
    models: options.models || {
      current: "qwen3.5:9b",
      previous: "qwen2.5:14b",
      installed: ["qwen3.5:9b"],
      offload: {
        available: true,
        status: "gpu",
        models: [{ name: "qwen3.5:9b", size_mb: 6100, vram_mb: 5900, on_gpu_percent: 97 }],
      },
    },
    modelsAvailable: options.modelsAvailable !== false,
    modelsEmpty: options.modelsEmpty === true,
    reads: [],
  };
  if (options.noCloud) delete state.payload.cloud;
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
      state.reads.push({ method: req.method(), path: url.pathname });
      if (url.pathname === "/api/models") {
        if (!state.modelsAvailable) return json(route, 404, { error: "not found" });
        const offload = state.modelsEmpty
          ? { available: true, status: "idle", models: [] }
          : state.models.offload;
        return json(route, 200, { ...state.models, offload });
      }
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
      if (url.pathname === "/api/manner") {
        if (!state.mannerAvailable) return json(route, 404, { error: "not found" });
        if (req.method() === "POST") {
          state.mannerBody = JSON.parse(req.postData() || "{}");
          state.mannerPosts.push(state.mannerBody);
          const all = state.manner.personalities.concat(state.manner.user_personalities);
          const row = all.find((p) => p.id === state.mannerBody.personality);
          if (!row) return json(route, 409, { ok: false, error: "I do not know that personality." });
          state.manner.personality = row.id;
          // The PC's own switch_ack, as jarvis_manner.py returns it in `said`.
          return json(route, 200, { ok: true, said: `Switched to ${row.title}.`,
            ...state.manner });
        }
        return json(route, 200, state.manner);
      }
      if (url.pathname === "/api/work/apply" && req.method() === "POST") {
        state.applyBody = JSON.parse(req.postData() || "{}");
        state.applyPosts.push(state.applyBody);
        const chosen = state.applyBody.preset;
        if (chosen === "cloud") {
          // The server's own refusal shape: a provider is required, and a
          // service with no key cannot be chosen.
          const provider = (state.payload.cloud.providers || [])
            .find((row) => row.id === state.applyBody.provider);
          if (!provider) {
            return json(route, 400, { ok: false, changed: false,
              error: "Name one of the API services this PC has: deepseek_api, groq_api." });
          }
          if (!provider.key_saved) {
            return json(route, 409, { ok: false, changed: false,
              error: "no key is saved on this PC for Groq (API); nothing was changed." });
          }
          state.payload.cloud.provider = provider.id;
          return json(route, 200, { ok: true, changed: true, preset: { id: "cloud" } });
        }
        if (state.applyMode === "refuse") {
          return json(route, 409, { ok: false, changed: false,
            error: "the Coding preset is being prepared; nothing was changed" });
        }
        // The REAL PC's refusal for a heavy preset (contract audit F1): both
        // cards as one pooled lane is not built, so `coding` always answers
        // 409. The stub must not pretend otherwise, or the suite pins a
        // fiction.
        if (chosen === "coding") {
          return json(route, 409, { ok: false, changed: false,
            error: "heavy mode needs the both-card lane, arriving later; nothing was changed." });
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
        state.payload = { ...state.payload, ...fixturePayload(chosen) };
        return json(route, 200, { ok: true, changed: true, preset: state.payload.presets.find((p) => p.id === chosen),
          lane: state.payload.lane, base_url: "http://127.0.0.1:11436",
          model: state.payload.chosen_model, previous_preset: null });
      }
      if (url.pathname === "/api/work/cloud-escalate" && req.method() === "POST") {
        // The PC's own escalate switch (2026-10-27): ONE boolean.
        const body = JSON.parse(req.postData() || "{}");
        state.escalatePosts.push(body);
        if (state.escalateMode === "refuse") {
          return json(route, 409, { ok: false, changed: false,
            error: "the approval card was refused; nothing was changed." });
        }
        if (state.escalateMode === "waiting") {
          // The card is still open on the PC: nothing written yet.
          return json(route, 200, { ok: false, waiting: true,
            said: "The PC is waiting for you to answer its card." });
        }
        state.payload.cloud.escalate.on = body.on === true;
        return json(route, 200, { ok: true, changed: true, on: body.on === true,
          said: body.on === true ? "Escalating when the work is complex is on." : "Escalating is off." });
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
  // A heavy preset cannot run, so its model line is the PC's own refusal
  // instead of a model it can never load (contract audit F1).
  assert.deepEqual(rows.map((r) => r.model),
    FIXTURE.presets.map((p) => (p.heavy_mode === true ? "needs both cards" : p.model)),
    "models drifted");
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
  await page.click('#presets .preset[data-preset="general"]');
  await page.waitForTimeout(700);
  const rows = await presetRows(page);
  const words = await page.evaluate(() => document.getElementById("preset-words").textContent);
  await page.close();
  assert.equal(state.applyBody && state.applyBody.preset, "general", "the apply body did not name the clicked preset");
  assert.deepEqual(rows.filter((r) => r.pressed === "true").map((r) => r.id), ["general"], "the rail did not mark the preset the PC now names chosen");
  assert.match(words, /Now using General/, words);
  assert.deepEqual(problems, []);
});

await check("Coding is drawn, but it cannot be applied: the PC always refuses heavy mode", async () => {
  // Contract audit F1: the PC answers 409 for `coding` (both cards as one
  // pooled lane is not built), so neither the rail nor the menu may offer the
  // click. The stub refuses it too, so nothing here can pin a fiction.
  const { page, state, problems } = await openHud(browser);
  const coding = await page.evaluate(() => {
    const b = document.querySelector('#presets .preset[data-preset="coding"]');
    return { disabled: b.disabled, title: b.title, label: b.getAttribute("aria-label"),
      model: b.querySelector(".preset-model").textContent };
  });
  await page.click('#presets .preset[data-preset="coding"]', { force: true }).catch(() => {});
  await page.waitForTimeout(400);
  await page.close();
  assert.equal(coding.disabled, true, "Coding is still a live apply button");
  assert.match(coding.title, /needs both cards at once as one pooled lane/,
    `Coding does not say why it cannot be used: ${coding.title}`);
  assert.match(coding.model, /needs both cards/, "Coding still advertises a model it cannot run");
  assert.equal(state.applyBody, null, "a disabled heavy preset still reached the PC");
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
  await page.click('#presets .preset[data-preset="general"]');
  await page.waitForTimeout(700);
  await sendChat(page, "what is this preset doing");
  const body = state.chats[state.chats.length - 1] || {};
  await page.close();
  assert.equal(state.applyBody && state.applyBody.preset, "general", "the apply never happened");
  assert.equal(body.auto, true, "the next turn is not a routed turn (auto:true)");
  assert.equal(body.lane, null, "the page kept its own lane override after applying a preset - it would override the PC's active lane");
  assert.equal(body.device, "hud");
  assert.equal(body.stream, true);
  assert.equal(body.cloud_yes, undefined,
    "the page sent a cloud yes while the PC's escalate switch is off");
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

/* ── The Current Models panel, opened by the model name itself (2026-10-27) ── */

/** Put the HUD in the Studio shell the way the shell's own event does. */
async function useStudio(page) {
  await page.evaluate(() => {
    window.dispatchEvent(new CustomEvent("jarvis:hud-shell", {
      detail: { shell_template: "split-stage", density: "comfortable", default_stage_tab: "galaxy" },
    }));
  });
  await page.waitForFunction(() =>
    document.body.getAttribute("data-hud-shell") === "split-stage", null, { timeout: 5000 });
  await page.waitForTimeout(150);
}

async function useAmbient(page) {
  await page.evaluate(() => {
    window.dispatchEvent(new CustomEvent("jarvis:hud-shell", {
      detail: { shell_template: "center-core", density: "comfortable", default_stage_tab: "talk" },
    }));
  });
  await page.waitForFunction(() =>
    document.body.getAttribute("data-hud-shell") === "center-core", null, { timeout: 5000 });
  await page.waitForTimeout(150);
}

async function openCurrentModels(page, door = "chip-model-door") {
  await page.click(`#${door}`);
  await page.waitForSelector("#current-models-panel:not([hidden])", { timeout: 5000 });
  await page.waitForTimeout(600);          // the three reads land, then the panel re-renders
}

async function modelsReport(page, door = "chip-model-door") {
  return page.evaluate((doorId) => {
    const box = document.getElementById("current-models-panel");
    const groups = [...box.querySelectorAll(".hud-presets-group")].map((group) => ({
      head: (group.querySelector(".hud-presets-head") || {}).textContent || "",
      lines: [...group.querySelectorAll(".hud-models-fact, .hud-presets-empty")]
        .map((p) => p.textContent),
      routes: [...group.querySelectorAll(".hud-models-route")].map((b) => ({
        lane: b.dataset.lane, pressed: b.getAttribute("aria-pressed"),
      })),
    }));
    const group = (head) => groups.find((g) => g.head === head) || { lines: [], routes: [] };
    return {
      title: (box.querySelector(".hud-presets-title") || {}).textContent || "",
      aria: box.getAttribute("aria-label"),
      heads: groups.map((g) => g.head),
      answering: group("Answering now").lines,
      loaded: group("Loaded right now").lines,
      focus: group("Chosen focus preset").lines,
      routes: group("Route the next message").routes,
      routesWords: group("Route the next message").lines,
      doorExpanded: document.getElementById(doorId).getAttribute("aria-expanded"),
    };
  }, door);
}

await check("the top-right model name IS the door, and it opens the PC's own model facts", async () => {
  const { page, state, problems } = await openHud(browser, { chosen: "general" });
  const door = await page.evaluate(() => {
    const b = document.getElementById("chip-model-door");
    return { text: b.textContent.trim(), label: b.getAttribute("aria-label"), title: b.title,
      expanded: b.getAttribute("aria-expanded"), shown: getComputedStyle(b).display !== "none",
      chipInside: Boolean(b.querySelector("#chip-model")) };
  });
  state.reads.length = 0;                  // only what the panel itself asks for
  await openCurrentModels(page);
  const panel = await modelsReport(page);
  const panelReads = [...state.reads];
  await page.close();
  assert.equal(door.shown, true, "the model name is not on screen in the Cockpit shell");
  assert.equal(door.chipInside, true, "the door does not hold the page's own #chip-model span");
  assert.equal(door.label, "Current Models: what Jarvis is using and has loaded", door.label);
  assert.equal(door.title, "Current Models: what Jarvis is using and has loaded", door.title);
  assert.equal(door.expanded, "false", "the door starts claiming the panel is open");
  assert.equal(panel.doorExpanded, "true", "opening the panel did not say so on the door");
  assert.equal(panel.title, "Current Models", "the panel's heading does not name it");
  assert.equal(panel.aria, "Current Models", "the panel's name for a screen reader is not Current Models");
  assert.deepEqual(panel.heads,
    ["Answering now", "Loaded right now", "Chosen focus preset", "Route the next message"],
    `the panel's sections are not the owner's four: ${JSON.stringify(panel.heads)}`);
  assert.deepEqual(panel.answering, ["qwen3.5:9b", "Before that: qwen2.5:14b"],
    `the answering section is not the PC's own: ${JSON.stringify(panel.answering)}`);
  assert.deepEqual(panel.loaded,
    ["qwen3.5:9b \u2014 6100 MB in memory, 5900 MB of that on the graphics card, 97% on the GPU"],
    `the loaded section is not the PC's own offload block: ${JSON.stringify(panel.loaded)}`);
  assert.deepEqual(panel.focus, ["Chosen focus preset: General (qwen3.5:9b)"],
    `the focus section is not the PC's own chosen preset: ${JSON.stringify(panel.focus)}`);
  for (const path of ["/api/models", "/api/status", "/api/presets"]) {
    const seen = panelReads.filter((r) => r.path === path);
    assert.ok(seen.length >= 1, `the panel never read ${path}: ${JSON.stringify(panelReads)}`);
    assert.equal(seen.length, 1, `the panel read ${path} ${seen.length} times`);
  }
  assert.deepEqual(panelReads.filter((r) => r.method !== "GET"), [],
    "the panel sent a write - it is a read");
  assert.deepEqual(problems, []);
});

await check("a successful apply keeps the chip door: no turn may overwrite the door", async () => {
  // P1-1: ten assignments write #chip-model's text/class/title. After a turn
  // and after a preset apply the door must still be the door.
  const { page, problems } = await openHud(browser, { chosen: "general" });
  await sendChat(page, "hello there");
  const afterTurn = await page.evaluate(() => {
    const door = document.getElementById("chip-model-door");
    const chip = document.getElementById("chip-model");
    return { cls: door.className, title: door.title, label: door.getAttribute("aria-label"),
      chipCls: chip.className, chipText: chip.textContent };
  });
  // A successful preset apply: the page repaints the chip and renders the
  // lanes - and must not throw (P1-3), with #lanes still in the document.
  await page.click('#presets .preset[data-preset="general"]');
  await page.waitForTimeout(900);
  const afterApply = await page.evaluate(() => {
    const lanes = document.getElementById("lanes");
    const door = document.getElementById("chip-model-door");
    return { laneButtons: lanes ? [...lanes.querySelectorAll(".lane")].map((b) => b.dataset.lane) : null,
      laneIds: lanes ? lanes.id : "",
      doorCls: door.className, doorTitle: door.title,
      words: document.getElementById("preset-words").textContent };
  });
  await page.close();
  assert.equal(afterTurn.cls, "chip-door", "a turn replaced the door's class");
  assert.equal(afterTurn.title, "Current Models: what Jarvis is using and has loaded",
    "a turn erased the door's tooltip");
  assert.equal(afterTurn.chipCls, "chip", `a turn replaced the chip's own class: ${afterTurn.chipCls}`);
  assert.equal(afterTurn.label, "Current Models: what Jarvis is using and has loaded",
    "a turn erased the door's accessible name");
  // The old three modes are gone from what #lanes draws; the element stays.
  assert.deepEqual(afterApply.laneButtons, ["auto", "local"],
    `#lanes draws more than the two real routes: ${JSON.stringify(afterApply.laneButtons)}`);
  assert.equal(afterApply.doorCls, "chip-door", "a successful preset apply replaced the door's class");
  assert.equal(afterApply.doorTitle, "Current Models: what Jarvis is using and has loaded",
    "a successful preset apply erased the door's tooltip");
  assert.match(afterApply.words, /Now using/, `the apply did not say what happened: ${afterApply.words}`);
  assert.deepEqual(problems, []);
});

await check("Ambient has its own door, and it opens the same panel", async () => {
  const { page, problems } = await openHud(browser);
  await useAmbient(page);
  const doors = await page.evaluate(() => ({
    bar: getComputedStyle(document.getElementById("chip-model-door")).display,
    pill: getComputedStyle(document.getElementById("chip-model-door-ambient")).display,
    label: document.getElementById("chip-model-door-ambient").getAttribute("aria-label"),
  }));
  await openCurrentModels(page, "chip-model-door-ambient");
  const panel = await modelsReport(page, "chip-model-door-ambient");
  await page.close();
  assert.equal(doors.bar, "none", "the stage bar's chip door is still drawn in Ambient");
  assert.notEqual(doors.pill, "none", "Ambient's pill door is not on screen");
  assert.equal(doors.label, "Current Models: what Jarvis is using and has loaded");
  assert.equal(panel.doorExpanded, "true", "Ambient's door does not say the panel is open");
  assert.ok(panel.heads.includes("Answering now"), "Ambient's door did not open the same panel");
  assert.deepEqual(problems, []);
});

await check("the panel's routes are the page's own lanes - only auto and the local model now", async () => {
  const { page, state, problems } = await openHud(browser);
  await openCurrentModels(page);
  const lanes = await page.evaluate(() => [...document.querySelectorAll("#lanes .lane")]
    .map((b) => b.dataset.lane));
  const panel = await modelsReport(page);
  const want = panel.routes[panel.routes.length - 1].lane;   // the local model
  await page.click(`#current-models-panel .hud-models-route[data-lane="${want}"]`);
  await page.waitForTimeout(300);
  const after = await page.evaluate(() => ({
    pageLane: S.lane,
    lanePressed: [...document.querySelectorAll("#lanes .lane")]
      .filter((b) => b.getAttribute("aria-pressed") === "true").map((b) => b.dataset.lane),
    panelPressed: [...document.querySelectorAll("#current-models-panel .hud-models-route")]
      .filter((b) => b.getAttribute("aria-pressed") === "true").map((b) => b.dataset.lane),
    chip: document.getElementById("chip-model").textContent,
    cloudButton: document.getElementById("preset-cloud").getAttribute("aria-pressed"),
  }));
  await sendChat(page, "route this one");
  const body = state.chats[state.chats.length - 1] || {};
  await page.close();
  assert.deepEqual(lanes, ["auto", "local"],
    `the page draws the old cloud modes again: ${JSON.stringify(lanes)}`);
  assert.deepEqual(panel.routes.map((r) => r.lane), lanes,
    "the panel's routes are not the page's own lane list");
  assert.deepEqual(panel.routes.filter((r) => r.pressed === "true").map((r) => r.lane), ["auto"],
    "the panel did not mark the page's starting lane");
  // The cloud is NOT one of these rows any more; the panel says where it is.
  assert.equal(panel.routes.some((r) => /jarvis-/.test(r.lane)), false,
    "a cloud lane is still drawn as a route");
  assert.match(panel.routesWords.join(" "), /Cloud button/,
    `the panel does not say where the cloud went: ${JSON.stringify(panel.routesWords)}`);
  assert.equal(after.pageLane, want, "the panel's route did not change the page's lane");
  assert.deepEqual(after.lanePressed, [want], "the page's own lane buttons did not follow");
  assert.deepEqual(after.panelPressed, [want], "the panel's mark did not follow the page's");
  assert.equal(after.chip, "qwen3.5:9b", `the chip did not follow the route: ${after.chip}`);
  assert.equal(after.cloudButton, "false", "the Cloud button is marked while the page routes locally");
  assert.equal(body.lane, "qwen3.5:9b", "the next chat body does not carry the lane the panel chose");
  assert.equal(body.auto, false, "a routed turn must not be auto");
  assert.equal(state.applyBody, null, "routing from the panel applied a preset");
  assert.deepEqual(state.mannerPosts, [], "routing from the panel switched a personality");
  assert.deepEqual(state.decisions, [], "routing from the panel approved something");
  assert.equal(state.pending.length, 0, "routing from the panel raised an approval card");
  assert.deepEqual(problems, []);
});

await check("the panel says plainly when nothing is loaded, or when the PC did not answer", async () => {
  const empty = await openHud(browser, { modelsEmpty: true });
  await openCurrentModels(empty.page);
  const emptyPanel = await modelsReport(empty.page);
  await empty.page.close();
  assert.deepEqual(emptyPanel.loaded, ["The PC did not say any model is in memory right now."],
    `an empty memory was filled in: ${JSON.stringify(emptyPanel.loaded)}`);
  assert.deepEqual(emptyPanel.answering, ["qwen3.5:9b", "Before that: qwen2.5:14b"],
    "an empty memory blanked the answering section");
  assert.deepEqual(emptyPanel.focus, ["No preset chosen yet \u2014 the PC routes on its own."],
    `a PC with no chosen preset was given one: ${JSON.stringify(emptyPanel.focus)}`);

  const missing = await openHud(browser, { modelsAvailable: false });
  await openCurrentModels(missing.page);
  const missingPanel = await modelsReport(missing.page);
  await missing.page.close();
  assert.deepEqual(missingPanel.answering,
    ["The PC did not answer when asked which model is answering."],
    `a failed /api/models read was filled in: ${JSON.stringify(missingPanel.answering)}`);
  assert.deepEqual(missingPanel.loaded, ["The PC did not answer when asked what is loaded."],
    `a failed /api/models read invented a loaded model: ${JSON.stringify(missingPanel.loaded)}`);
  // The other two reads still land, so their sections still tell the truth.
  assert.deepEqual(missingPanel.focus, ["No preset chosen yet \u2014 the PC routes on its own."]);
  assert.deepEqual(missing.problems, []);
  assert.deepEqual(empty.problems, []);
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

/* ── The PC's own presets in the menu (owner, 2026-10-27: "i also want the
 *    presets to include all the ideal local ai presets that are made (like
 *    coder, or general, etc) along with the different personalities of jarvis
 *    that i can select") ─────────────────────────────────────────────────── */

async function openPresetMenu(page) {
  await page.click("#rail-presets");
  await page.waitForSelector("#hud-presets-menu:not([hidden])", { timeout: 5000 });
  await page.waitForTimeout(700);          // both reads land, then the menu re-renders
}

async function menuReport(page) {
  return page.evaluate(() => {
    const menu = document.getElementById("hud-presets-menu");
    if (!menu) return null;
    const groups = [...menu.querySelectorAll(".hud-presets-group")].map((group) => ({
      heading: (group.querySelector(".hud-presets-head") || {}).textContent || "",
      items: [...group.querySelectorAll('[role="menuitem"]')].map((b) => ({
        text: b.textContent.trim(),
        chosen: b.getAttribute("aria-current") === "true",
        preset: b.dataset.preset || "",
        personality: b.dataset.personality || "",
        disabled: b.disabled === true,
      })),
      notes: [...group.querySelectorAll(".hud-presets-empty")].map((p) => p.textContent),
      // A heavy preset is drawn as words, not as a button (contract audit F1).
      blocked: [...group.querySelectorAll(".hud-presets-empty[data-preset]")]
        .map((p) => ({ preset: p.dataset.preset, text: p.textContent })),
    }));
    const rows = (heading) => (groups.find((g) => g.heading === heading) || { items: [] }).items;
    const blocked = (heading) => (groups.find((g) => g.heading === heading) || { blocked: [] }).blocked;
    const line = menu.querySelector(".hud-presets-line");
    const cloudBox = document.getElementById("hud-presets-cloud-menu");
    const cloudRow = menu.querySelector('[data-cloud-action="open"]');
    const checkbox = document.getElementById("hud-escalate-cloud");
    return {
      title: (menu.querySelector(".hud-presets-title") || {}).textContent || "",
      aria: menu.getAttribute("aria-label"),
      headings: groups.map((g) => g.heading),
      groups,
      model: rows("Focus presets").filter((row) => row.preset),
      blocked: blocked("Focus presets"),
      cloudRow: cloudRow ? {
        text: cloudRow.textContent.trim(),
        chosen: cloudRow.getAttribute("aria-current") === "true",
        expanded: cloudRow.getAttribute("aria-expanded"),
      } : null,
      providers: cloudBox ? [...cloudBox.querySelectorAll("[data-provider]")].map((b) => ({
        id: b.dataset.provider,
        text: b.textContent.trim(),
        chosen: b.getAttribute("aria-current") === "true",
        disabled: b.disabled === true,
      })) : [],
      providerNotes: cloudBox ? [...cloudBox.querySelectorAll(".hud-presets-empty")].map((p) => p.textContent) : [],
      keyLines: cloudBox ? [...cloudBox.querySelectorAll(".hud-presets-key")].map((p) => p.textContent) : [],
      submenuOpen: Boolean(cloudBox && !cloudBox.hidden),
      checkbox: checkbox ? {
        checked: checkbox.checked, disabled: checkbox.disabled,
        label: (checkbox.closest("label") || {}).textContent || "",
        describedBy: checkbox.getAttribute("aria-describedby"),
      } : null,
      why: (document.getElementById("hud-escalate-cloud-why") || {}).textContent || "",
      people: rows("Personality"),
      mine: rows("My personalities"),
      layouts: rows("Built-in layouts").length,
      line: line ? line.textContent : "",
    };
  });
}

await check("the menu is called Presets and lists the PC's focus presets and nine personalities", async () => {
  const { page, problems } = await openHud(browser, { chosen: "general" });
  await openPresetMenu(page);
  const menu = await menuReport(page);
  await page.close();
  assert.equal(menu.title, "Presets", "the menu did not take the owner's name for it");
  assert.equal(menu.aria, "Presets", "the menu's name for a screen reader is not Presets");
  // One name everywhere: the phone's title, Settings, the bar and JARVIS-API
  // all say "Focus presets" (contract audit F5).
  assert.deepEqual(menu.headings.slice(0, 3), ["Focus presets", "Personality", "Built-in layouts"],
    `the PC's own lists do not come before the layouts: ${JSON.stringify(menu.headings)}`);
  // Coding is drawn as the PC's refusal, not as a row that always 409s (F1).
  const live = FIXTURE.presets.filter((p) => p.heavy_mode !== true);
  assert.deepEqual(menu.model.map((r) => r.preset), live.map((p) => p.id),
    "the menu does not list the PC's applicable presets in its order");
  assert.deepEqual(menu.model.map((r) => r.text.replace(/ \(chosen\)$/, "")),
    live.map((p) => p.title), "the presets' titles are not the PC's own");
  assert.deepEqual(menu.blocked.map((r) => r.preset), ["coding"],
    `the heavy preset is not drawn as unavailable: ${JSON.stringify(menu.blocked)}`);
  assert.match(menu.blocked[0].text, /needs both cards at once as one pooled lane/,
    `the PC's own heavy-mode sentence is missing: ${menu.blocked[0].text}`);
  assert.deepEqual(menu.model.filter((r) => r.chosen).map((r) => r.preset), ["general"],
    "the chosen mark is not the PC's chosen_preset");
  assert.deepEqual(menu.people.map((r) => r.personality),
    PERSONALITIES.personalities.map((p) => p.id),
    "the menu does not list the PC's nine personalities in its order");
  assert.deepEqual(menu.people.map((r) => r.text.replace(/ \(current\)$/, "")),
    PERSONALITIES.personalities.map((p) => p.title),
    "the personalities' titles are not the PC's own");
  assert.equal(menu.mine.length, 0, "a My personalities section appeared with no saved ones");
  const modelRule = (menu.groups.find((g) => g.heading === "Focus presets") || { notes: [] }).notes.join(" ");
  assert.match(modelRule, /ONE approval card/i,
    `the menu does not say the model cards' rule: ${modelRule}`);
  assert.equal(menu.line, "", "the menu said something before any action ran");
  assert.deepEqual(problems, []);
});

await check("a model preset click asks the PC, and the chosen mark follows the REFETCHED contract", async () => {
  const { page, state, problems } = await openHud(browser);
  await openPresetMenu(page);
  await page.click('#hud-presets-menu [data-preset="general"]');
  await page.waitForTimeout(900);
  const menu = await menuReport(page);
  await page.close();
  assert.equal(state.applyBody && state.applyBody.preset, "general",
    "the model-preset click did not ask the PC to apply it");
  assert.deepEqual(menu.model.filter((r) => r.chosen).map((r) => r.preset), ["general"],
    "the menu did not mark the preset the PC's refetched contract now names chosen");
  assert.match(menu.line, /Now using General/, `the menu does not say what the PC did: ${menu.line}`);
  assert.deepEqual(problems, []);
});

await check("a refused model preset leaves nothing marked, and says why", async () => {
  const { page, state, problems } = await openHud(browser, { applyMode: "refuse" });
  await openPresetMenu(page);
  await page.click('#hud-presets-menu [data-preset="general"]');
  await page.waitForTimeout(900);
  const menu = await menuReport(page);
  await page.close();
  assert.equal(state.applyBody && state.applyBody.preset, "general", "the click never reached the PC");
  assert.equal(menu.model.filter((r) => r.chosen).length, 0,
    "a preset was marked chosen although the PC refused it");
  assert.match(menu.line, /did not work|prepared|nothing was changed/i,
    `the refusal is not said in plain words: ${menu.line}`);
  // A refused card must not leave the rows dead (P2-3).
  assert.equal(menu.model.some((r) => r.disabled), false,
    `a refused card left the presets disabled: ${JSON.stringify(menu.model)}`);
  assert.deepEqual(problems, []);
});

/* ── The Cloud section (the owner, 2026-10-27: a "Cloud" preset beside
 *    coder/general/fast, listing "the API providers the PC has connected",
 *    plus "Escalate to the cloud when the work is too complex") ──────────── */

await check("the Cloud row sits after the five and opens the PC's providers without posting", async () => {
  const { page, state, problems } = await openHud(browser);
  await openPresetMenu(page);
  const closed = await menuReport(page);
  await page.click('[data-cloud-action="open"]');
  await page.waitForTimeout(250);
  const open = await menuReport(page);
  await page.close();
  assert.ok(closed.cloudRow, "the menu has no Cloud row");
  assert.match(closed.cloudRow.text, /^Cloud/, closed.cloudRow.text);
  assert.equal(closed.cloudRow.expanded, "false", "the Cloud row starts saying the submenu is open");
  assert.equal(closed.submenuOpen, false, "the provider submenu is drawn before the row is pressed");
  assert.equal(open.submenuOpen, true, "pressing Cloud did not open the provider submenu");
  assert.equal(open.cloudRow.expanded, "true", "the Cloud row does not say the submenu is open");
  // Drawing the submenu is a READ: no write of any kind.
  assert.deepEqual(state.applyPosts, [], "opening the Cloud section posted an apply");
  assert.deepEqual(state.escalatePosts, [], "opening the Cloud section posted the escalate switch");
  assert.deepEqual(open.providers.map((p) => p.id), ["deepseek_api", "groq_api"],
    `the submenu does not list the PC's providers: ${JSON.stringify(open.providers)}`);
  assert.deepEqual(open.providers.filter((p) => p.chosen).map((p) => p.id), [],
    "a provider was marked chosen before the PC named one");
  assert.match(open.providerNotes.join(" "), /no key is saved on this PC/i,
    `the PC's own reason for the unusable service is missing: ${JSON.stringify(open.providerNotes)}`);
  assert.deepEqual(open.keyLines, ["py -3 jarvis_chatbot_api.py key groq"],
    "the PC's own command for adding a key is not shown");
  assert.match(open.providerNotes.join(" "), /Add the key on your PC/,
    "the submenu does not say a key is added on the PC");
  assert.deepEqual(problems, []);
});

await check("picking a provider is ONE apply with the provider id, marked from the refetched answer", async () => {
  const { page, state, problems } = await openHud(browser);
  await openPresetMenu(page);
  await page.click('[data-cloud-action="open"]');
  await page.waitForTimeout(200);
  await page.click('#hud-presets-cloud-menu .hud-presets-item[data-provider="deepseek_api"]');
  await page.waitForTimeout(900);
  const menu = await menuReport(page);
  await page.close();
  assert.deepEqual(state.applyPosts, [{ preset: "cloud", provider: "deepseek_api" }],
    `the provider click did not post exactly one cloud apply: ${JSON.stringify(state.applyPosts)}`);
  assert.deepEqual(menu.providers.filter((p) => p.chosen).map((p) => p.id), ["deepseek_api"],
    "the chosen provider is not the PC's refetched `cloud.provider`");
  assert.equal(menu.cloudRow.chosen, true, "the Cloud row is not marked from the PC's answer");
  assert.match(menu.cloudRow.text, /DeepSeek \(API\)/, menu.cloudRow.text);
  // It is an APPLY, so it asks for the PC's ONE card; the page approves nothing.
  assert.deepEqual(state.decisions, [], "the page approved the card itself");
  assert.deepEqual(problems, []);
});

await check("a provider with no key is not a button: the PC's command and no post", async () => {
  const { page, state, problems } = await openHud(browser);
  await openPresetMenu(page);
  await page.click('[data-cloud-action="open"]');
  await page.waitForTimeout(200);
  const groq = await page.evaluate(() => {
    const button = document.querySelector('#hud-presets-cloud-menu .hud-presets-item[data-provider="groq_api"]');
    const line = document.querySelector("#hud-presets-cloud-menu .hud-presets-key");
    return { button: Boolean(button), line: line ? line.textContent : "" };
  });
  await page.close();
  assert.equal(groq.button, false, "a service with no key is still an apply button");
  assert.match(groq.line, /jarvis_chatbot_api\.py key groq/, "the key command is not shown");
  assert.deepEqual(state.applyPosts, [], "the keyless row posted an apply");
  assert.deepEqual(problems, []);
});

await check("the escalate checkbox is drawn from the PC, and a click posts ONE boolean", async () => {
  const { page, state, problems } = await openHud(browser);
  await openPresetMenu(page);
  await page.click('[data-cloud-action="open"]');
  await page.waitForTimeout(200);
  const before = await menuReport(page);
  await page.click("#hud-escalate-cloud");
  await page.waitForTimeout(900);
  const after = await menuReport(page);
  await sendChat(page, "a hard one");
  const body = state.chats[state.chats.length - 1] || {};
  await page.close();
  assert.ok(before.checkbox, "the Cloud section has no escalate checkbox");
  assert.equal(before.checkbox.checked, false, "the box was ticked while the PC said off");
  assert.match(before.checkbox.label, /Escalate to the cloud when the work is too complex/,
    before.checkbox.label);
  assert.equal(before.checkbox.describedBy, "hud-escalate-cloud-why",
    "the checkbox does not point at its own explanation");
  assert.match(before.why, /When off, every question is answered on this PC first/,
    `the off state is not explained: ${before.why}`);
  assert.deepEqual(state.escalatePosts, [{ on: true }],
    `the click did not post exactly one boolean: ${JSON.stringify(state.escalatePosts)}`);
  assert.equal(after.checkbox.checked, true, "the refetched PC answer did not tick the box");
  assert.equal(after.checkbox.disabled, false, "the box is still disabled after the answer");
  assert.match(after.line, /Escalating when the work is complex is on/, after.line);
  // The chat body says yes ONLY because the PC's own answer now says on.
  assert.equal(body.cloud_yes, true, "the turn did not carry the PC-approved cloud yes");
  assert.deepEqual(problems, []);
});

await check("a refused escalate card leaves the box UNTICKED, says so, and keeps the menu usable", async () => {
  const { page, state, problems } = await openHud(browser, { escalateMode: "refuse" });
  await openPresetMenu(page);
  await page.click('[data-cloud-action="open"]');
  await page.waitForTimeout(200);
  await page.click("#hud-escalate-cloud");
  await page.waitForTimeout(900);
  const menu = await menuReport(page);
  await sendChat(page, "a hard one");
  const body = state.chats[state.chats.length - 1] || {};
  await page.close();
  assert.deepEqual(state.escalatePosts, [{ on: true }], "the click never reached the PC");
  assert.equal(menu.checkbox.checked, false,
    "a refused card left the box ticked - the tick must come from the PC");
  assert.equal(menu.checkbox.disabled, false, "a refused card left the box dead");
  assert.match(menu.line, /did not work|refused|nothing was changed/i,
    `the refusal is not said in plain words: ${menu.line}`);
  assert.deepEqual(menu.model.filter((r) => r.disabled), [],
    "a refused escalate card disabled the preset rows");
  assert.equal(body.cloud_yes, undefined,
    "the page sent a cloud yes although the PC's setting is still off");
  assert.deepEqual(problems, []);
});

await check("the Cloud row is only drawn when the PC sends one - never invented", async () => {
  const { page, problems } = await openHud(browser, { noCloud: true });
  await openPresetMenu(page);
  const menu = await menuReport(page);
  await page.close();
  assert.equal(menu.cloudRow, null, "a Cloud row appeared without the PC's own cloud answer");
  assert.equal(menu.model.length, 4, "the five presets changed when the cloud answer went missing");
  assert.deepEqual(problems, []);
});

await check("a personality click is immediate, asks for no card, and marks the PC's new current", async () => {
  const { page, state, problems } = await openHud(browser);
  await openPresetMenu(page);
  await page.click('#hud-presets-menu [data-personality="classic_butler"]');
  await page.waitForTimeout(700);
  const menu = await menuReport(page);
  await page.close();
  assert.deepEqual(state.mannerPosts, [{ personality: "classic_butler" }],
    "the personality click did not post ONE personality field");
  assert.deepEqual(state.decisions, [], "a personality switch asked for an approval decision");
  assert.equal(state.pending.length, 0, "a personality switch raised an approval card");
  assert.deepEqual(menu.people.filter((r) => r.chosen).map((r) => r.personality),
    ["classic_butler"], "the menu did not mark the personality the PC now names current");
  assert.match(menu.line, /Switched to Classic British Butler/,
    `the PC's own words are not shown: ${menu.line}`);
  assert.deepEqual(problems, []);
});

await check("My personalities appears only when the PC lists one", async () => {
  const { page, problems } = await openHud(browser, { userPersonalities: [
    { id: "mine-1", name: "Calm Helper", line: "calm and short" }] });
  await openPresetMenu(page);
  const menu = await menuReport(page);
  await page.close();
  assert.deepEqual(menu.headings.slice(0, 4),
    ["Focus presets", "Personality", "My personalities", "Built-in layouts"],
    `My personalities is missing or out of order: ${JSON.stringify(menu.headings)}`);
  assert.deepEqual(menu.mine.map((r) => r.text), ["Calm Helper"]);
  // The PC's own list already carries the saved one (builtin: false); it must
  // be drawn under My personalities only, never also under Personality.
  assert.deepEqual(menu.people.map((r) => r.personality),
    PERSONALITIES.personalities.map((p) => p.id),
    `a saved personality was drawn under Personality as well: ${JSON.stringify(menu.people.map((r) => r.personality))}`);
  assert.deepEqual(problems, []);
});

await check("a PC without the presets route gets honest words, and no invented presets", async () => {
  const { page, problems } = await openHud(browser, { presetsAvailable: false });
  await openPresetMenu(page);
  const menu = await menuReport(page);
  await page.close();
  assert.equal(menu.model.length, 0, "model presets appeared without the PC's contract");
  const group = menu.groups.find((g) => g.heading === "Focus presets") || { notes: [] };
  assert.match(group.notes.join(" "), /did not list/i,
    `no honest words for a backend without the route: ${JSON.stringify(group.notes)}`);
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
