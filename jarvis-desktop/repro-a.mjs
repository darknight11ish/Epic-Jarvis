import { serve, launch, open, APPROVAL_PLAIN, ATTENTION_CLEAR } from "./tests/uikit.mjs";

const srv = await serve();
const browser = await launch();

// ---------- A: typing while streaming silently discards the prompt ----------
{
  const page = await open(browser, srv.base, "index.html", { pending: [] });
  // Give the stub a Channel and a stream_chat that never resolves.
  await page.evaluate(() => {
    window.__lines = [];
    window.__TAURI__.core.Channel = class {
      constructor() { this.onmessage = null; window.__chan = this; }
    };
    const real = window.__TAURI__.core.invoke;
    window.__TAURI__.core.invoke = async (cmd, args) => {
      if (cmd === "stream_chat") return new Promise(() => {}); // hangs, like a live stream
      return real(cmd, args);
    };
  });
  await page.fill("#prompt", "first question");
  await page.press("#prompt", "Enter");
  await page.waitForTimeout(150);
  // feed a token so we are unambiguously mid-stream
  await page.evaluate(() => window.__chan.onmessage(JSON.stringify({ response: "hello " })));
  await page.waitForTimeout(150);
  const midPhase = await page.evaluate(() => document.documentElement.dataset.state);

  await page.fill("#prompt", "second question typed while it streams");
  await page.press("#prompt", "Enter");
  await page.waitForTimeout(150);
  const after = await page.evaluate(() => ({
    phase: document.documentElement.dataset.state,
    composer: document.getElementById("prompt").value,
    answer: document.getElementById("answer").textContent,
    streamCalls: window.__calls.filter(c => c[0] === "stream_chat").length,
  }));
  console.log("A. mid-stream phase:", midPhase);
  console.log("A. after 2nd Enter :", JSON.stringify(after));
  await page.close();
}

// ---------- B: a failed decision latches state.decided forever ----------
{
  const page = await open(browser, srv.base, "index.html", { pending: [APPROVAL_PLAIN] });
  await page.waitForTimeout(200);
  await page.evaluate(() => {
    const real = window.__TAURI__.core.invoke;
    window.__decideCalls = 0;
    window.__TAURI__.core.invoke = async (cmd, args) => {
      if (cmd === "decide_approval") {
        window.__decideCalls++;
        throw new Error("the Jarvis server did not answer");
      }
      return real(cmd, args);
    };
  });
  const open1 = await page.evaluate(() => !document.getElementById("approval").hidden);
  await page.click("#approval-approve");
  await page.waitForTimeout(200);
  const hint1 = await page.textContent("#approval-hint");
  const dis1 = await page.evaluate(() => document.getElementById("approval-approve").disabled);
  // now the "server" recovers
  await page.evaluate(() => {
    const real = window.__TAURI__.core.invoke;
    window.__TAURI__.core.invoke = async (cmd, args) => {
      if (cmd === "decide_approval") { window.__decideCalls++; return { ok: true }; }
      return real(cmd, args);
    };
  });
  await page.click("#approval-approve");
  await page.click("#approval-deny");
  await page.waitForTimeout(200);
  const res = await page.evaluate(() => ({
    decideCalls: window.__decideCalls,
    approveDisabled: document.getElementById("approval-approve").disabled,
    denyDisabled: document.getElementById("approval-deny").disabled,
    cardOpen: !document.getElementById("approval").hidden,
    hint: document.getElementById("approval-hint").textContent,
  }));
  console.log("B. gate opened:", open1, "| after failure, hint:", JSON.stringify(hint1), "disabled:", dis1);
  console.log("B. after recovery, 2 more clicks:", JSON.stringify(res));
  await page.close();
}

// ---------- C: voice never reports data-voice="listening" ----------
{
  const page = await open(browser, srv.base, "index.html", {});
  await page.waitForTimeout(200);
  await page.evaluate(() => window.__emit("jarvis-link", {
    connected: true, stale: false, base: "http://127.0.0.1:4719", last_id: 9,
    power: "active", activity: "listening", approvals: 0,
    attention: { known: true, limit: 6, remaining: 4, spent: 2, muted: false,
                 blocked_by: null, pending: 0, banked: false, digest_hour: 18, digest_due: false },
    error: null,
  }));
  await page.waitForTimeout(400);
  const listening = await page.evaluate(() => document.documentElement.dataset.voice);
  await page.evaluate(() => window.__emit("jarvis-link", {
    connected: true, stale: false, base: "x", last_id: 10, power: "active",
    activity: "speaking", approvals: 0,
    attention: { known: true, limit: 6, remaining: 4, spent: 2, muted: false,
                 blocked_by: null, pending: 0, banked: false, digest_hour: 18, digest_due: false },
    error: null,
  }));
  await page.waitForTimeout(400);
  const speaking = await page.evaluate(() => document.documentElement.dataset.voice);
  console.log("C. data-voice while activity=listening:", JSON.stringify(listening),
              "| while activity=speaking:", JSON.stringify(speaking));
  await page.close();
}

// ---------- F: the Copy button sticks on "Copied" ----------
{
  const page = await open(browser, srv.base, "index.html", {});
  await page.evaluate(() => { window.__state = null; });
  await page.evaluate(() => {
    window.__TAURI__.core.Channel = class { constructor(){ window.__chan = this; } };
  });
  await page.fill("#prompt", "q");
  await page.press("#prompt", "Enter");
  await page.waitForTimeout(300);
  await page.evaluate(() => { document.getElementById("card").hidden = false; });
  // force a buffer so copy has something
  await page.click("#copy");
  await page.waitForTimeout(300);
  await page.click("#copy");
  await page.waitForTimeout(1600);
  const label = await page.textContent("#copy");
  console.log("F. copy label 1.6s after the second click:", JSON.stringify(label));
  await page.close();
}

await browser.close();
srv.close();
