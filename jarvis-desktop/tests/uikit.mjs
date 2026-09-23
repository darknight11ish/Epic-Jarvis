/**
 * Shared harness: serve the real frontend, stub the Tauri bridge, drive a
 * surface into a named state, screenshot it.
 *
 * Every payload below is copied from what the backend actually returns —
 * jarvis_arbiter.status()/digest(), jarvis_gate.pending() with a
 * jarvis_content_risk chip, and the desktop's own DesktopTelemetry struct — so
 * a screenshot is a picture of real markup under real shapes, not a mockup.
 */
/**
 * Playwright is deliberately NOT a dependency of this package.
 *
 * It pulls several hundred megabytes of browsers, and the first thing anyone
 * does with this repo is `npm install && npm run build` on a Windows machine
 * to get the app running. Paying for a UI test harness at that moment is the
 * wrong trade, so it is loaded at run time and its absence is explained rather
 * than thrown.
 */
let chromium;
try {
  ({ chromium } = await import("playwright"));
} catch {
  console.error(
    "These UI tests need Playwright, which is not installed by default:\n" +
      "  npm i -D playwright && npx playwright install chromium\n" +
      "Nothing else in this repo needs it — see tests/README.md."
  );
  process.exit(2);
}
import http from "node:http";
import fs from "node:fs";
import fsSync from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Where the browser is.
 *
 * Playwright's own resolution is wrong in the container these were written in
 * — PLAYWRIGHT_BROWSERS_PATH holds a build it does not expect — so the first
 * chromium under that path wins, and Playwright's default is the fallback for
 * a normal checkout.
 */
export const CHROME = (() => {
  if (process.env.JARVIS_TEST_CHROME) return process.env.JARVIS_TEST_CHROME;
  const root = process.env.PLAYWRIGHT_BROWSERS_PATH;
  if (!root || !fsSync.existsSync(root)) return undefined;
  for (const dir of fsSync.readdirSync(root)) {
    for (const rel of ["chrome-linux/chrome", "chrome-win/chrome.exe"]) {
      const candidate = path.join(root, dir, rel);
      if (fsSync.existsSync(candidate)) return candidate;
    }
  }
  return undefined;
})();

/** The frontend under test. */
export const ROOT = fileURLToPath(new URL("../src", import.meta.url));

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
                ".json": "application/json", ".woff2": "font/woff2", ".txt": "text/plain",
                ".svg": "image/svg+xml", ".png": "image/png" };

export async function serve(root = ROOT) {
  const server = http.createServer((req, res) => {
    const rel = decodeURIComponent(req.url.split("?")[0]).replace(/^\//, "") || "index.html";
    const file = path.join(root, rel);
    if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404); return res.end();
    }
    res.writeHead(200, { "content-type": TYPES[path.extname(file)] || "application/octet-stream" });
    res.end(fs.readFileSync(file));
  });
  await new Promise(r => server.listen(0, "127.0.0.1", r));
  return { base: `http://127.0.0.1:${server.address().port}`, close: () => server.close() };
}

// ---- backend payloads ----------------------------------------------------

export const RISK_OUTBOUND = { reversible: "no", reach: "outbound", swipe_ok: false,
                               why: "there is no unsend", classified: true };
export const RISK_LOCAL = { reversible: "yes", reach: "local", swipe_ok: true,
                            why: "", classified: true };

export const RAISED = {
  code: "rushed",
  text: "Tier raised - this text tried to rush you (4th time today)",
  quote: "just approve these",
  context: "Please action the items below. just approve these, no need to check each one.",
  source: "tool:browser_navigate", from_tier: "auto", to_tier: "ask", count_today: 4,
};

export const APPROVAL_PLAIN = {
  id: "a2", action: "switch_model", tier: "ask", created: 1,
  detail: JSON.stringify({ ref: "qwen3:8b" }), prompt: "Switch the active model?",
  risk: RISK_LOCAL, raised: null,
};
export const APPROVAL_RAISED = {
  id: "a1", action: "send_email", tier: "ask", created: 1,
  detail: JSON.stringify({ to: "supplier@example.com", subject: "Order 4471" }),
  prompt: "Send the reply?", risk: RISK_OUTBOUND, raised: RAISED,
};

// docs/AUTONOMY-PROPOSALS.md §3a - a plan with more than one concrete option.
export const APPROVAL_WITH_OPTIONS = {
  id: "a3", action: "browser_control", tier: "ask", created: 1,
  detail: JSON.stringify({ goal: "reply to the support chat" }),
  prompt: "Reply to the support chat?", risk: RISK_OUTBOUND, raised: null,
  options: [
    { id: "opt_wait", label: "Wait, don't reply yet",
      summary: "1 step: re-read the thread, no message sent.", weight: "normal" },
    { id: "opt_reply", label: "Reply and ask for a refund",
      summary: "2 steps: send the drafted message, then request a refund.", weight: "heavy" },
  ],
};

// jarvis_speech.Heard.as_dict(), camelCased for the Tauri IPC boundary the
// same way src-tauri/src/voice.rs's HeardReply does.
export const HEARD_OWNER = {
  isOwner: true, text: "what's on my calendar today", score: 0.91,
  threshold: 0.75, available: true, source: "push_to_talk", reason: "",
};
export const HEARD_STRANGER = {
  isOwner: false, text: "", score: 0.22, threshold: 0.75,
  available: true, source: "push_to_talk", reason: "",
};
export const HEARD_UNAVAILABLE = {
  isOwner: false, text: "", score: 0, threshold: 0, available: false,
  source: "push_to_talk", reason: "no speech-to-text engine is configured",
};

export const ATTENTION_BANKED = {
  known: true, limit: 6, remaining: 0, spent: 6, muted: false,
  blocked_by: null, pending: 3, banked: true, digest_hour: 18, digest_due: true,
};
export const ATTENTION_CLEAR = {
  known: true, limit: 6, remaining: 4, spent: 2, muted: false,
  blocked_by: null, pending: 0, banked: false, digest_hour: 18, digest_due: false,
};

export const DIGEST = {
  available: true, count: 3, shown: 3, hour: 18,
  budget: { limit: 6, remaining: 0, spent: 6, muted: false, blocked_by: null },
  note: "Approvals open their own card. There is no approve-all, here or anywhere else.",
  items: [
    { id: "i1", kind: "approval", source: "gate", title: "send an email to the supplier",
      priority: "high", created: 1, ref: "a1", opens_card: true, body: "" },
    { id: "i2", kind: "job", source: "long-fuse", title: "index the archive finished",
      priority: "normal", created: 2, ref: "j9", opens_card: false,
      body: "4,182 documents, 3 skipped." },
    { id: "i3", kind: "finding", source: "watch", title: "two repos moved on your watchlist",
      priority: "low", created: 3, ref: "", opens_card: false, body: "" },
  ],
};

export const TELEMETRY = {
  cpuPercent: 34, vramUsedMb: 6248, vramTotalMb: 8192,
  gpuUtilPercent: 71, gpuTempC: 62, routeLane: "local",
};

/**
 * A graph shaped like `build_graph()` builds one: a single core, clusters that
 * anchor to it, and facts/documents/entities hanging off those. Sized at the
 * order the owner's store would realistically reach so the layout is judged
 * under load rather than on a toy.
 */
export function makeGraph(scale = 1) {
  const nodes = [{ id: "core", label: "J.A.R.V.I.S.", group: "core", weight: 6 }];
  const links = [];
  const push = (n) => { nodes.push(n); return n.id; };

  for (const m of ["qwen3:8b", "llama3.1:8b", "nomic-embed-text"]) {
    push({ id: `model:${m}`, label: m, group: "model", weight: 3 });
    links.push({ source: "core", target: `model:${m}`, kind: "runs" });
  }
  const clusters = ["Reasoning", "Web + Research", "Files", "Mail", "Calendar", "Shell"];
  for (const c of clusters) {
    const cid = `cluster:${c}`;
    push({ id: cid, label: c, group: "cluster", weight: 4 });
    links.push({ source: "core", target: cid, kind: "runs" });
    for (let i = 0; i < 4; i++) {
      const tid = `${cid}:tool${i}`;
      push({ id: tid, label: `${c.split(" ")[0].toLowerCase()}_${i}`, group: "tool", weight: 1 });
      links.push({ source: cid, target: tid, kind: "provides" });
    }
  }
  for (const s of ["invoice-triage", "release-notes", "meeting-digest"]) {
    push({ id: `skill:${s}`, label: s, group: "skill", weight: 2 });
    links.push({ source: "core", target: `skill:${s}`, kind: "runs" });
  }
  for (const pn of ["Concise", "Tutor"]) {
    push({ id: `persona:${pn}`, label: pn, group: "persona", weight: 2 });
    links.push({ source: "core", target: `persona:${pn}`, kind: "runs" });
  }
  const docSrc = "source:documents";
  push({ id: docSrc, label: "Documents", group: "source", weight: 4 });
  links.push({ source: "core", target: docSrc, kind: "runs" });
  const factSrc = "source:facts";
  push({ id: factSrc, label: "Facts", group: "source", weight: 4 });
  links.push({ source: "core", target: factSrc, kind: "runs" });

  const topics = ["reactor spec", "tauri acl", "interruption budget", "undo shelf",
                  "content risk", "ledger anchors", "watchlist", "sleep-time compute"];
  for (let i = 0; i < 60 * scale; i++) {
    const id = `fact:${i}`;
    push({ id, label: `${topics[i % topics.length]} — note ${i}`, group: "fact", weight: 1 });
    links.push({ source: factSrc, target: id, kind: "knows" });
    if (i % 5 === 0) links.push({ source: id, target: `cluster:${clusters[i % clusters.length]}`, kind: "mentions" });
  }
  for (let i = 0; i < 40 * scale; i++) {
    const id = `doc:${i}`;
    push({ id, label: `${topics[i % topics.length]}-${i}.md`, group: "document", weight: 1 });
    links.push({ source: docSrc, target: id, kind: "holds" });
  }
  for (let i = 0; i < 24 * scale; i++) {
    const id = `entity:${i}`;
    push({ id, label: `Entity ${i}`, group: "entity", weight: 1 });
    links.push({ source: `fact:${i % (60 * scale)}`, target: id, kind: "about" });
  }
  return { nodes, links, counts: {}, sources: {}, config_dir: "C:\\Users\\pcadmin\\.openjarvis" };
}

export const BRAIN = {
  graph: makeGraph(1),
  status: { available: true, lane: "local", model: "qwen3:8b", power: "active" },
  models: { available: true, current: "qwen3:8b", previous: "llama3.1:8b",
            installed: [{ ref: "qwen3:8b", size: 5_100_000_000, family: "qwen3" },
                        { ref: "llama3.1:8b", size: 4_900_000_000, family: "llama" },
                        { ref: "nomic-embed-text", size: 274_000_000, family: "nomic" }] },
  compute: { plan: "single-gpu", gpu: "RTX 4060 Ti", vram_used_mb: 6248, vram_total_mb: 8192,
             gpu_layers: 33, context: 8192,
             note: "8 GB with a compositor holding some of it, so a 7.5-9 GB adapter would spill." },
  skills: { available: true, skills: [
    { name: "invoice-triage", verdict: "clean", description: "Sorts supplier invoices into the ledger folders.", path: "skills/invoice-triage" },
    { name: "release-notes", verdict: "clean", description: "Turns merged PRs into a changelog." },
    { name: "meeting-digest", verdict: "flagged", description: "Summarises transcripts. Scanner noted an unpinned tool description." }] },
  memory: { available: true, facts: 612, documents: 148, chunks: 4102,
            path: "C:\\Users\\pcadmin\\.openjarvis\\memory.db",
            model: "nomic-embed-text", sleep_time: { enabled: true, remind: true } },
  memory_pending: { available: true, setup: { setup_complete: false, note:
      "extraction is a scaffold: review its proposals and tune the prompt against real conversations" },
    pending: [
    { id: 41, text: "Prefers invoices filed by supplier, not by month.", source: "conversation",
      confidence: 0.82, created: Date.now()/1000 - 3600 },
    { id: 42, text: "Standing desk arrives the week of the 22nd.", source: "conversation",
      confidence: 0.61, replaces: "Standing desk arrives in March.",
      created: Date.now()/1000 - 7200 }] },
  memory_facts: { available: true, learning: true, pending: 2, facts: [
    { id: 7, text: "Works in Europe/London.", source: "user",
      valid_from: Date.now()/1000 - 800000, valid_to: null },
    { id: 9, text: "Prefers explicit PowerShell cmdlets over aliases.", source: "extracted",
      valid_from: Date.now()/1000 - 90000, valid_to: null },
    { id: 4, text: "Standing desk arrives in March.", source: "extracted",
      valid_from: Date.now()/1000 - 900000, valid_to: Date.now()/1000 - 90000 }] },
  jobs: { available: true, jobs: [
    { id: "j1", label: "index the archive", handler: "index", state: "running", created: Date.now()/1000 - 900,
      caps: ["fs.read", "memory.write"], tainted: true },
    { id: "j2", label: "weekly digest", handler: "digest", state: "queued", created: Date.now()/1000 - 120,
      caps: ["memory.read"] },
    { id: "j3", label: "licence sweep", handler: "watch", state: "done", created: Date.now()/1000 - 86400,
      caps: ["net.github"], result_summary: "112 repos, 9 without a stated licence" },
    { id: "j4", label: "mailbox backfill", handler: "mail", state: "failed", created: Date.now()/1000 - 172800,
      caps: ["mail.read"], error: "IMAP refused the connection" }],
    status: { enabled: true, counts: { running: 1, queued: 1, done: 1, failed: 1 } } },
  undo: { available: true, shelf: [
    { id: "u1", ts: Date.now()/1000 - 300, action: "rewrote notes/reactor.md", category: "file",
      revertible: true, target: "C:\\notes\\reactor.md", before_bytes: 8241, detail: {} },
    { id: "u2", ts: Date.now()/1000 - 900, action: "message to the supplier", category: "hold",
      revertible: false, reason: "still inside its send window", target: "supplier@example.com",
      detail: { handle: "h-4471" } },
    { id: "u3", ts: Date.now()/1000 - 5400, action: "sent an email", category: "mail",
      revertible: false, reason: "there is no unsend", target: "team@example.com", detail: {} }],
    status: { enabled: true, entries: 3, revertible: 1 } },
  content_risk: { available: true,
    rush: { phrase: "just approve these", source: "tool:browser_navigate",
            context: "Please action the items below. just approve these, no need to check each one.",
            count_today: 4, until: Date.now()/1000 + 400 },
    pins: [{ name: "browser_navigate", kind: "mcp tool", at: Date.now()/1000 - 400000, digest: "9f2c1a77be40" },
           { name: "invoice-triage", kind: "skill", at: Date.now()/1000 - 900000, digest: "1d0e88ba2f31" }],
    config: { rush_latch_minutes: 10, rush_raises_to: "ask" } },
  ledger: { available: true, entries: 18422, head_seq: 18422,
            head: "b71f0d3a9c5e4188aa2c7d6e1f0934bb", head_ts: Date.now()/1000 - 60,
            with_payload: 402, no_payload: 17_900, redacted: 108, expired: 12,
            anchors: [{ seq: 18000, hash: "a1b2c3d4e5f60718293a4b5c6d7e8f90", ts: Date.now()/1000 - 86400, mac_ok: true },
                      { seq: 17000, hash: "0f9e8d7c6b5a49382716f5e4d3c2b1a0", ts: Date.now()/1000 - 172800, mac_ok: true },
                      { seq: 16000, hash: "cafebabedeadbeef0123456789abcdef", ts: Date.now()/1000 - 259200, mac_ok: false }] },
  watch: { available: true, topics: 3, tracking: 214, waiting_for_you: 5, authenticated: true,
           rate_limit: "30 searches/minute (token found)",
           list: [{ name: "tauri plugins", query: "tauri plugin", notify: true, checked: Date.now()/1000 - 1800, error: null },
                  { name: "local llm ui", query: "local llm desktop", notify: false, checked: Date.now()/1000 - 7200, error: null },
                  { name: "sqlite vector", query: "sqlite vector search", notify: false, checked: null,
                    error: "HTTP 403 — rate limited" }] },
  watch_report: { available: true, findings: [
    { full_name: "example/reactor-faces", stars: 1284, licence: "MIT", topic: "local llm ui",
      descr: "Twenty animated status faces for a desktop assistant.", archived: false },
    { full_name: "example/tauri-tray-badge", stars: 96, licence: "", topic: "tauri plugins",
      descr: "Numeric badges on the Windows tray icon.", archived: false,
      note: "description contained an invisible Unicode tag block; normalised before storing" },
    { full_name: "example/vec0", stars: 4102, licence: "Apache-2.0", topic: "sqlite vector",
      descr: "A vector search extension for SQLite.", archived: false }] },
  attention: { available: true, budget: { limit: 6, remaining: 0, spent: 6, muted: false, blocked_by: null },
               pending: 3, banked: true, digest_hour: 18, digest_due: true },
};

export const ANSWER_MD = `Three things changed in the reactor spec this week.

1. **Thinking** moved off the 360° rainbow to a narrow cool sweep — hue 217–275.
2. **Speaking** now brightens with Jarvis's own voice through \`setSpeechLevel()\`.
3. **Error** runs *backward*, and nothing else in the product ever does.

\`\`\`rust
pub fn face_state(activity: &str, banked: bool) -> &'static str {
    if activity == "idle" && banked { return "banked"; }
    activity
}
\`\`\`

The direction is the signal — colour alone fails for one man in twelve.`;

// ---- the stub bridge -----------------------------------------------------

export const HOTKEYS = [
  { id: "toggle_quickbar", label: "Summon Jarvis", hint: "Show or hide the spotlight bar from anywhere.",
    accelerator: "Alt+Space", default: "Alt+Space", registered: true, error: null },
  { id: "ingest_clipboard", label: "Attach the clipboard", hint: "Put whatever is on the clipboard into the bar as context.",
    accelerator: "Super+Shift+J", default: "Super+Shift+J", registered: true, error: null },
  { id: "capture_screen", label: "Attach a screen capture", hint: "Not Win+Shift+S — the Snipping Tool owns that at the shell level.",
    accelerator: "Alt+Shift+S", default: "Alt+Shift+S", registered: true, error: null },
  { id: "quick_note", label: "Quick note to Logseq", hint: "Summon the bar already prefixed with #log.",
    accelerator: "Alt+Shift+N", default: "Alt+Shift+N", registered: true, error: null },
  { id: "toggle_widget", label: "Show or hide the widget", hint: "The desktop pane with the meters and the gates.",
    accelerator: "Alt+Shift+W", default: "Alt+Shift+W", registered: true, error: null },
];

export const UPDATE_NONE = {
  current: "0.1.0", available: null, notes: null, date: null,
  error: null, supported: true, check_on_start: true,
};

export function bridge({ link, pending, attention, digest, telemetry, prefs, answer, brain, theme, hotkeys, refuse, update, found, installFails, restartFails, appearance, noRoute, decideFails, amendFails, appearanceFails, memoryRefuses, learningFloor, apiSettings, bindAddressRefuses, bindAddressRefusalMessage, chatReplies, heard, captureFails, speakFails, autoListenFails, speakDelayMs, taskActionFails, taskNoteFails, vision, noteJobs }) {
  const listeners = {};
  window.__calls = [];
  const state = {
    connected: true, stale: false, base: "http://127.0.0.1:4719", last_id: 7,
    power: "active", power_set_by: null, activity: "idle",
    approvals: pending.length, attention, error: null, ...link,
  };
  // Real Tauri serialises a Channel to an id the Rust side calls back into;
  // this mock never leaves JavaScript, so `args.onEvent` handed to `invoke`
  // below IS the live object a scenario can call `.onmessage(...)` on
  // directly. Its absence used to throw `TAURI.core.Channel is not a
  // constructor` at `new TAURI.core.Channel()` in streamViaBackend - before
  // the first `await`, so uncaught by that function's own try/catch - which
  // silently broke every scenario that drove a real `send()` on index.html
  // rather than posing the card mid-answer by hand.
  class MockChannel {
    constructor() {
      this.onmessage = null;
    }
  }

  window.__TAURI__ = {
    core: {
      Channel: MockChannel,
      invoke: async (cmd, args) => {
        window.__calls.push([cmd, args]);
        switch (cmd) {
          case "get_link_state": return state;
          case "get_pending_approvals":
            return { count: pending.length, items: pending, stale: state.stale };
          case "get_digest": return digest;
          case "mark_digest_seen": return { ok: true, marked: 3 };
          case "set_attention_muted": return { muted: args.muted };
          case "get_widget_prefs":
            return { expanded: true, always_on_top: true, x: null, y: null, ...prefs };
          case "check_server_health":
            return { services: [{ name: "ollama", online: true },
                                { name: "litellm", online: false }] };
          case "get_api_settings":
            return { base: window.__apiSettings.base, hasToken: window.__apiSettings.hasToken,
                     bindAddress: window.__apiSettings.bindAddress,
                     store: "C:\\Users\\pcadmin\\AppData\\Roaming\\jarvis-desktop.json" };
          case "set_api_settings": {
            window.__calls.push(["__savedApiSettings", args]);
            if (window.__bindAddressRefuses && "bindAddress" in args &&
                args.bindAddress && window.__bindAddressRefuses.includes(args.bindAddress)) {
              throw new Error(window.__bindAddressRefusalMessage || "refused");
            }
            if (args.base !== undefined) window.__apiSettings.base = args.base || "";
            if (args.token) window.__apiSettings.hasToken = true;
            if (args.token === "") window.__apiSettings.hasToken = false;
            if ("bindAddress" in args) window.__apiSettings.bindAddress = args.bindAddress || "";
            return null;
          }
          case "supervisor_status":
            return { supervise: true, owned: true, configured: true, pid: 24188,
                     uptime_seconds: 5127, launcher_exited: false,
                     base: "http://127.0.0.1:4719",
                     backend: { program: "C:\\Python312\\python.exe",
                                args: ["C:\\Jarvis\\jarvis_hud.py"],
                                cwd: "C:\\Jarvis" } };
          case "stream_chat": {
            // A scenario that cares what the answer actually SAYS (rather
            // than only that a turn completed) queues real text here; each
            // call consumes the next entry. A plain string is sent as one
            // chunk; an ARRAY of strings is sent as several, in order, one
            // real event-loop tick apart - the shape a scenario needs to
            // prove something reacts mid-stream (sentence-streaming TTS)
            // rather than only once the whole reply is in. Emitted as raw,
            // non-JSON chunks - `consumeLine` appends anything that does
            // not parse as JSON and is not an SSE control line verbatim, so
            // this is the real append path, not a shortcut around it.
            // Exhausted or unset, `stream_chat` resolves with nothing sent,
            // which `finishStream` already turns into its own honest
            // placeholder - still a real "done" turn, just with nothing
            // scripted to say.
            const reply = (window.__chatReplies || []).shift();
            const onmessage = args && args.onEvent && args.onEvent.onmessage;
            // The answer's id, sent ahead of the answer exactly as
            // commands.rs pump_chat does (TURN_LINE_PREFIX). A scenario
            // sets window.__turnId; unset, no id - an unpatched backend.
            if (window.__turnId && typeof onmessage === "function") {
              onmessage("\u001fjarvis-turn:" + window.__turnId);
            }
            if (reply && typeof onmessage === "function") {
              const chunks = Array.isArray(reply) ? reply : [reply];
              for (const chunk of chunks) {
                onmessage(chunk);
                await new Promise((r) => setTimeout(r, 0));
              }
            }
            return null;
          }
          case "get_theme": return theme || "deep-space";
          // "Match Windows light or dark mode" (commands.rs ThemePrefs). A
          // scenario sets window.__themePrefs; unset, the shell is treated as
          // not following, on the theme above.
          case "get_theme_prefs":
            return window.__themePrefs || {
              theme: theme || "deep-space", follow_system: false,
              dark_theme: "deep-space", system_light: false, effective: theme || "deep-space",
            };
          case "set_theme_follow_system": {
            const p = window.__themePrefs || { theme: theme || "deep-space", dark_theme: "deep-space", system_light: true };
            const follow = Boolean(args.follow);
            window.__themePrefs = { ...p, follow_system: follow,
              effective: follow && p.system_light ? "paper" : follow ? p.dark_theme : p.theme };
            return window.__themePrefs;
          }
          // From memory, never the network: what the widget's face and the
          // chrome colours read.
          case "appearance_snapshot":
            return { face: (window.__appearance || {}).face || null,
                     bindings: (window.__appearance || {}).bindings || {}, updated: 0 };
          case "appearance_colours": return window.__appearanceColours || {};
          case "open_faces": window.__calls.push(["__openedFaces"]); return null;
          // feedback.patch. `window.__markRoute = false` is a backend
          // without the route (commands.rs turns a 404 into this).
          case "mark_answer":
            window.__marks = window.__marks || [];
            window.__marks.push({ turnId: args.turnId, mark: args.mark });
            if (window.__markRoute === false) return { available: false, status: 404 };
            return { ok: true, turn_id: args.turnId, mark: args.mark };
          case "capture_note":
          case "capture_note_status": {
            window.__noteCalls.push({ cmd, ...args });
            if (window.__captureNoteFails) throw new Error(window.__captureNoteFails);
            const jobs = window.__noteJobs;
            return jobs.length > 1 ? jobs.shift() : jobs[0];
          }
          case "brain_memory_keep_both":
            window.__memoryWrites.push({ cmd, ...args });
            return { ok: true };
          case "get_hotkeys": return window.__hotkeys;
          // Matches commands.rs's get_autostart/set_autostart shape - falling
          // through to the bare `default: return null` below made
          // settings.js's `Boolean(info.enabled)` throw on `null.enabled`,
          // which the real command can never return (it has no error case).
          case "get_autostart":
            return { enabled: Boolean(window.__autostart), supported: true,
                     launchedAtLogin: false, note: "" };
          case "set_autostart":
            window.__autostart = Boolean(args.enabled);
            return { enabled: window.__autostart, supported: true };
          // Push-to-talk. A scenario sets window.__heard (a Heard-shaped
          // object, camelCase - isOwner/text/available/reason) for what
          // stop_voice_capture answers, window.__captureFails /
          // __speakFails to make either call reject, and reads
          // window.__voiceCalls afterwards to see what actually ran.
          case "start_voice_capture":
            window.__voiceCalls.push("start");
            if (window.__captureFails) throw new Error(window.__captureFails);
            return null;
          case "stop_voice_capture":
            window.__voiceCalls.push("stop");
            if (window.__captureFails) throw new Error(window.__captureFails);
            return window.__heard;
          case "cancel_voice_capture":
            window.__voiceCalls.push("cancel");
            return null;
          case "start_automatic_listening":
            window.__voiceCalls.push("auto-start");
            if (window.__autoListenFails) throw new Error(window.__autoListenFails);
            return null;
          case "stop_automatic_listening":
            window.__voiceCalls.push("auto-stop");
            return null;
          case "speak_reply":
            window.__voiceCalls.push(["speak", args.text]);
            if (window.__speakDelayMs) {
              await new Promise((r) => setTimeout(r, window.__speakDelayMs));
            }
            if (window.__speakFails) throw new Error(window.__speakFails);
            // A tiny, real, silent WAV - short enough to inline, valid
            // enough that `new Audio(dataUri).play()` does not reject on
            // the data URI itself being malformed.
            return "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";
          case "decide_approval":
            window.__decides = window.__decides || [];
            // `option_id` is undefined on every existing scenario's call —
            // recorded as-is rather than defaulted, so a test can assert
            // "no option was sent" for the zero/one-option path and "this
            // exact option was sent" for the multi-option one.
            window.__decides.push({ id: args.id, approved: args.approved, optionId: args.option_id });
            if (window.__decideFails) throw new Error(window.__decideFails);
            return { ok: true };
          // docs/AUTONOMY-PROPOSALS.md §3b - DRAFT route, unconfirmed
          // against the real jarvis_hud.py. Records the note; a scenario
          // that wants to see a follow-up proposal arrive still has to
          // `__emit("approvals-changed", ...)` itself, same as
          // `approval-resolved` already works in decide.mjs.
          case "amend_approval":
            window.__amends = window.__amends || [];
            window.__amends.push({ id: args.id, note: args.note });
            if (window.__amendFails) throw new Error(window.__amendFails);
            return { ok: true };
          // docs/AUTONOMY-PROPOSALS.md §3d - DRAFT routes, unconfirmed
          // against the real backend. Each just records that it was asked
          // for; there is no server-side "task" model here to actually
          // pause, resume, stop, or note.
          case "pause_task":
          case "resume_task":
          case "stop_task":
            window.__taskActions = window.__taskActions || [];
            window.__taskActions.push(cmd);
            if (window.__taskActionFails) throw new Error(window.__taskActionFails);
            return { ok: true };
          case "inject_task_note":
            window.__taskNotes = window.__taskNotes || [];
            window.__taskNotes.push(args.note);
            if (window.__taskNoteFails) throw new Error(window.__taskNoteFails);
            return { ok: true };
          case "get_appearance":
            if (window.__appearanceFails) throw new Error(window.__appearanceFails);
            return window.__appearance;
          case "set_appearance": {
            window.__calls.push(["__saved", args.appearance]);
            const shared = !window.__noRoute;
            return {
              ...args.appearance,
              updated: 1,
              source: shared ? "server" : "local",
              shared,
              note: shared ? undefined
                : "Saved on this machine. This backend has no /api/appearance, so the phone will not see it.",
            };
          }
          case "update_status": return window.__update;
          case "check_for_update":
            window.__calls.push(["__checked"]);
            window.__update = { ...window.__update, ...(window.__found || {}) };
            return window.__update;
          case "set_update_check_on_start":
            window.__update = { ...window.__update, check_on_start: args.enabled };
            return args.enabled;
          case "install_update":
            if (window.__installFails) throw new Error(window.__installFails);
            window.__calls.push(["__installed"]);
            return window.__update.available;
          case "restart_app":
            if (window.__restartFails) throw new Error(window.__restartFails);
            window.__calls.push(["__restarted"]);
            return null;
          case "reset_hotkeys":
            window.__hotkeys = window.__hotkeys.map((h) => ({
              ...h, accelerator: h.default, registered: true, error: null,
            }));
            return window.__hotkeys;
          case "set_hotkeys": {
            // Mirrors hotkeys.rs: validate the whole set BEFORE anything is
            // written, so a rejected save leaves the bindings untouched.
            const seen = new Map();
            for (const [id, accel] of Object.entries(args.bindings)) {
              const mods = String(accel).split("+").slice(0, -1);
              if (!mods.length) throw new Error(`${id}: \`${accel}\` has no modifier.`);
              const key = String(accel).toLowerCase();
              if (seen.has(key)) {
                throw new Error(`\`${accel}\` is on both ${seen.get(key)} and ${id}.`);
              }
              seen.set(key, id);
            }
            window.__hotkeys = window.__hotkeys.map((h) => ({
              ...h,
              accelerator: args.bindings[h.id] ?? h.accelerator,
              // The scenario decides which combinations the "OS" refuses.
              registered: !(window.__refuse || []).includes(args.bindings[h.id] ?? h.accelerator),
              error: (window.__refuse || []).includes(args.bindings[h.id] ?? h.accelerator)
                ? "HotKey already registered"
                : null,
            }));
            return window.__hotkeys;
          }
          // vision.rs: can the local model see the attached picture? A
          // scenario sets `vision`; unset, the model is the text-only one
          // this project actually runs.
          case "local_model_vision": return window.__vision;
          case "set_theme": return args.theme;
          case "brain_read": {
            const out = {};
            for (const name of args.sections) {
              out[name] = (brain && brain[name]) || { available: false, error: "not stubbed" };
            }
            return out;
          }
          case "brain_watch_add":
          case "brain_watch_remove":
          case "brain_watch_seen":
          case "brain_revert_undo":
          case "brain_cancel_job":
          case "brain_cancel_hold":
          case "brain_remove_skill":
          case "brain_model":
            return { ok: true };
          // Recorded rather than just acknowledged: the memory pane's whole
          // contract is ONE fact per call, so a test has to be able to count
          // the calls and read the ids, not merely see that nothing threw.
          case "brain_memory_decide":
          case "brain_memory_forget":
          case "brain_memory_edit":
          case "brain_memory_learning":
          case "brain_memory_sleep_time":
            window.__memoryWrites.push({ cmd, ...args });
            if (window.__memoryRefuses) {
              return { ok: false, error: String(window.__memoryRefuses) };
            }
            if (cmd === "brain_memory_learning") {
              // The server can answer 200 and still refuse, when
              // JARVIS_EXTRACT is off in the environment. Reproduce that,
              // because rendering the request instead of the reply is the
              // bug most likely to be written here.
              return window.__learningFloor
                ? { ok: true, enabled: false, floor: false,
                    note: "JARVIS_EXTRACT is off in the environment, which overrides this switch." }
                : { ok: true, enabled: args.enabled };
            }
            if (cmd === "brain_memory_sleep_time") {
              return { ok: true, enabled: args.enabled ?? true, remind: args.remind ?? true };
            }
            return { ok: true };
          case "brain_memory_export":
            window.__memoryWrites.push({ cmd });
            return { available: true, facts: [{ id: 1, text: "exported" }], pending: [] };
          default: return null;
        }
      },
    },
    event: {
      listen: async (name, fn) => { (listeners[name] ||= []).push(fn); return () => {}; },
      emit: async () => {},
    },
  };
  if (theme) {
    // The page's own inline bootstrap reads this and sets data-theme before
    // first paint — which is the path being tested, so the harness must not
    // shortcut it. `documentElement` may not exist yet at init-script time.
    try { localStorage.setItem("jarvis.theme", theme); } catch (e) {}
    if (document.documentElement) {
      document.documentElement.setAttribute("data-theme", theme);
    }
  }
  window.__hotkeys = JSON.parse(JSON.stringify(hotkeys));
  window.__update = JSON.parse(JSON.stringify(update));
  window.__appearance = JSON.parse(JSON.stringify(appearance));
  window.__noRoute = Boolean(noRoute);
  window.__decideFails = decideFails || null;
  window.__amendFails = amendFails || null;
  window.__taskActionFails = taskActionFails || null;
  window.__taskNoteFails = taskNoteFails || null;
  window.__taskActions = [];
  window.__taskNotes = [];
  // note-capture.patch: each capture_note / capture_note_status call answers
  // with the next job in this list (the last one repeats). Unset, a note is
  // filed at once - the common case, a tier that does not ask.
  window.__noteJobs = JSON.parse(JSON.stringify(noteJobs || [
    { id: "note_t", state: "filed", target: "logseq",
      message: "Filed in Logseq, journals/2026_09_23.md." },
  ]));
  window.__noteCalls = [];
  window.__appearanceFails = appearanceFails || null;
  window.__decides = [];
  window.__amends = [];
  window.__voiceCalls = [];
  window.__heard = heard || null;
  window.__captureFails = captureFails || null;
  window.__speakFails = speakFails || null;
  window.__autoListenFails = autoListenFails || null;
  window.__speakDelayMs = speakDelayMs || 0;
  window.__memoryWrites = [];
  window.__memoryRefuses = memoryRefuses || null;
  window.__chatReplies = [...(chatReplies || [])];
  window.__learningFloor = Boolean(learningFloor);
  window.__found = found || null;
  window.__installFails = installFails || null;
  window.__restartFails = restartFails || null;
  window.__refuse = refuse || [];
  window.__apiSettings = { base: "http://127.0.0.1:4719", hasToken: true, bindAddress: "",
                            ...(apiSettings || {}) };
  window.__bindAddressRefuses = bindAddressRefuses || null;
  window.__bindAddressRefusalMessage = bindAddressRefusalMessage || null;
  window.__vision = vision || { model: "qwen3:8b", vision: false,
    reason: "Ollama lists what qwen3:8b can do, and pictures are not on the list." };
  window.__emit = (n, p) => (listeners[n] || []).forEach(f => f({ payload: p }));
  window.__answer = answer;
  window.__brain = brain;
}

export async function launch() {
  // `executablePath: undefined` means "use Playwright's own", which is the
  // right answer on a normal checkout.
  return chromium.launch(CHROME ? { executablePath: CHROME } : {});
}

/** Opens a page with the bridge installed and the given scenario data. */
export async function open(browser, base, file, data, viewport) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 2 });
  const errors = [];
  page.on("pageerror", e => errors.push(String(e)));
  page.on("console", m => {
    const t = m.text();
    if (m.type() === "error" && !/favicon|Failed to load resource/.test(t)) errors.push(t);
  });
  // The harness's own static server has no favicon; that 404 is not the app's.
  page.on("response", r => {
    if (r.status() >= 400 && !/favicon/.test(r.url())) errors.push(`HTTP ${r.status()} ${r.url()}`);
  });
  page.on("requestfailed", r => { if (!/favicon/.test(r.url())) errors.push(`REQFAIL ${r.url()}`); });
  await page.addInitScript(bridge, {
    link: {}, pending: [], attention: ATTENTION_CLEAR, digest: DIGEST,
    telemetry: TELEMETRY, prefs: {}, answer: "", brain: BRAIN, theme: null,
    hotkeys: HOTKEYS, refuse: [], update: UPDATE_NONE, found: null,
    installFails: null, restartFails: null, noRoute: false, decideFails: null, amendFails: null, appearanceFails: null,
    taskActionFails: null, taskNoteFails: null, noteJobs: null,
    heard: null, captureFails: null, speakFails: null, autoListenFails: null, speakDelayMs: 0,
    memoryRefuses: null, learningFloor: false, apiSettings: null,
    bindAddressRefuses: null, bindAddressRefusalMessage: null, chatReplies: null,
    vision: null,
    appearance: { face: null, bindings: {}, updated: 0, source: "default", shared: false },
    ...data,
  });
  await page.goto(`${base}/${file}`);
  await page.waitForTimeout(500);
  page.__errors = errors;
  return page;
}
