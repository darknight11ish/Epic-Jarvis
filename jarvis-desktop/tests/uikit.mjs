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

export function bridge({ link, pending, attention, digest, telemetry, prefs, answer, brain, theme, hotkeys, refuse, update, found, installFails, appearance, noRoute, decideFails, appearanceFails, memoryRefuses, learningFloor }) {
  const listeners = {};
  window.__calls = [];
  const state = {
    connected: true, stale: false, base: "http://127.0.0.1:4719", last_id: 7,
    power: "active", power_set_by: null, activity: "idle",
    approvals: pending.length, attention, error: null, ...link,
  };
  window.__TAURI__ = {
    core: {
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
            return { base: "http://127.0.0.1:4719", token_set: true,
                     store_path: "C:\\Users\\pcadmin\\AppData\\Roaming\\jarvis-desktop.json" };
          case "supervisor_status":
            return { supervise: true, owned: true, configured: true, pid: 24188,
                     uptime_seconds: 5127, launcher_exited: false,
                     base: "http://127.0.0.1:4719",
                     backend: { program: "C:\\Python312\\python.exe",
                                args: ["C:\\Jarvis\\jarvis_hud.py"],
                                cwd: "C:\\Jarvis" } };
          case "stream_chat": return null;
          case "get_theme": return theme || "deep-space";
          case "get_hotkeys": return window.__hotkeys;
          case "decide_approval":
            window.__decides = window.__decides || [];
            window.__decides.push({ id: args.id, approved: args.approved });
            if (window.__decideFails) throw new Error(window.__decideFails);
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
  window.__appearanceFails = appearanceFails || null;
  window.__decides = [];
  window.__memoryWrites = [];
  window.__memoryRefuses = memoryRefuses || null;
  window.__learningFloor = Boolean(learningFloor);
  window.__found = found || null;
  window.__installFails = installFails || null;
  window.__refuse = refuse || [];
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
    installFails: null, noRoute: false, decideFails: null, appearanceFails: null,
    memoryRefuses: null, learningFloor: false,
    appearance: { face: null, bindings: {}, updated: 0, source: "default", shared: false },
    ...data,
  });
  await page.goto(`${base}/${file}`);
  await page.waitForTimeout(500);
  page.__errors = errors;
  return page;
}
