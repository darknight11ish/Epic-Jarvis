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
 * The backend's real answers to "which note apps are set up?", written by
 * backend/test_obsidian_notes.py --write from jarvis_note_capture itself.
 * A window gets `NOTE_TARGETS.all` unless a test says otherwise.
 */
export const NOTE_TARGETS = JSON.parse(fsSync.readFileSync(path.join(
  path.dirname(fileURLToPath(import.meta.url)), "..", "..", "jarvis-client", "app", "src",
  "test", "resources", "contract", "note-targets.json"), "utf8"));

/**
 * The backend's real `GET /api/second-card` answers - jarvis_second_card.status(),
 * one per named case, written by tools/gen_second_card_cases.py. Never
 * hand-made: a test picks a case by name, e.g. `SECOND_CARD.capable_off`.
 */
export const SECOND_CARD = JSON.parse(fsSync.readFileSync(path.join(
  path.dirname(fileURLToPath(import.meta.url)), "fixtures", "second-card-cases.json"),
  "utf8")).cases;

/**
 * The backend's real `GET /api/hardware` answers and POST answers -
 * jarvis_hardware.status() and friends, one per named case, written by
 * tools/gen_hardware_cases.py. Never hand-made: pick a case by name, e.g.
 * `HARDWARE.today_one_card`.
 */
export const HARDWARE = JSON.parse(fsSync.readFileSync(path.join(
  path.dirname(fileURLToPath(import.meta.url)), "fixtures", "hardware-cases.json"),
  "utf8")).cases;

/**
 * The backend's real big-model answers - jarvis_big_model.status() (the
 * `status_*` cases), deep_status() (`deep_*`) and the POST answers
 * (`post_*`, `ask_*`, each `{status, body}`) - written by
 * tools/gen_big_model_cases.py. Never hand-made: pick a case by name, e.g.
 * `BIG_MODEL.status_ready_off`.
 */
export const BIG_MODEL = JSON.parse(fsSync.readFileSync(path.join(
  path.dirname(fileURLToPath(import.meta.url)), "fixtures", "big-model-cases.json"),
  "utf8")).cases;

/**
 * The backend's real `GET /api/voice/status` answers - jarvis_speech.status(),
 * one per named case (`VOICE.cases`) - and its real `POST /api/voice/wake`
 * answers (`VOICE.answers`), written by tools/gen_voice_status_cases.py.
 * Never hand-made: pick a case by name, e.g. `VOICE.cases.phone_trained`.
 */
/**
 * The backend's real answers for voice training, the voice-check settings,
 * the guided test and custom voices, written by
 * tools/gen_voice_training_cases.py: `statuses` (GET /api/voice/status),
 * `enroll` and `voice_posts` ({code, body} of each POST) and `voices`
 * (GET /api/voice/voices). `TRAINING.answer(x)` is what voice_training.rs
 * hands the page for one of those POSTs: the body with its code as `http`.
 */
export const TRAINING = JSON.parse(fsSync.readFileSync(path.join(
  path.dirname(fileURLToPath(import.meta.url)), "fixtures", "voice-training-cases.json"), "utf8"));
TRAINING.answer = (a) => ({ ...a.body, http: a.code });

export const VOICE = JSON.parse(fsSync.readFileSync(path.join(
  path.dirname(fileURLToPath(import.meta.url)), "fixtures", "voice-status-cases.json"),
  "utf8"));

/** GET /api/email/sending as the backend answers it, and one email's card
 *  (tools/gen_email_sending_cases.py). */
export const EMAIL_SENDING = JSON.parse(fsSync.readFileSync(path.join(
  path.dirname(fileURLToPath(import.meta.url)), "fixtures", "email-sending-cases.json"),
  "utf8"));

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

/**
 * The approval card's words, as the PC writes them (backend/jarvis_card_words.py,
 * through tools/gen_card_words_cases.py) - so the sample rows below carry the
 * same `notice.title` a real /api/pending row does.
 */
export const CARD_WORDS = JSON.parse(fsSync.readFileSync(path.join(
  path.dirname(fileURLToPath(import.meta.url)), "fixtures", "card-words-cases.json"), "utf8"));
/** The PC's title for a gate action. */
export const cardTitleFor = (action) =>
  CARD_WORDS.titles.find((t) => t.action === action).title;

export const APPROVAL_PLAIN = {
  id: "a2", action: "switch_model", tier: "ask", created: 1,
  detail: JSON.stringify({ ref: "qwen3:8b" }), prompt: "Switch the active model?",
  risk: RISK_LOCAL, raised: null,
  notice: { title: cardTitleFor("switch_model"), weight: "normal", deny_ok: true,
            approve_ok: false, body: "Nothing has happened yet." },
};
export const APPROVAL_RAISED = {
  id: "a1", action: "send_email", tier: "ask", created: 1,
  detail: JSON.stringify({ to: "supplier@example.com", subject: "Order 4471" }),
  prompt: "Send the reply?", risk: RISK_OUTBOUND, raised: RAISED,
  notice: { title: cardTitleFor("send_email"), weight: "heavy", deny_ok: true,
            approve_ok: false, body: "There is no unsend. Nothing has happened yet." },
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
  // jarvis_compute.Plan.as_dict() (backend/rebuilt/jarvis_compute.py), one card.
  compute: { text_model: "qwen3:8b", text_on: "cuda:0", vision_resident: false,
             tts_resident: false, simulated: false, prefer: "speed",
             devices: [{ index: 0, name: "NVIDIA GeForce RTX 2080 SUPER", total_mb: 8192, free_mb: 1944 }],
             why: "speed: text on the freest card; one card only, so vision and voice load on demand",
             total_mb: 8192 },
  skills: { available: true, skills: [
    { name: "invoice-triage", verdict: "clean", description: "Sorts supplier invoices into the ledger folders.", path: "skills/invoice-triage" },
    { name: "release-notes", verdict: "clean", description: "Turns merged PRs into a changelog." },
    { name: "meeting-digest", verdict: "flagged", description: "Summarises transcripts. Scanner noted an unpinned tool description." }] },
  // The field names jarvis_memory's MemoryStore.status() really sends, plus
  // the route's own `available` and `sleep_time`. backend/test_memory_honesty.py
  // fails if this fixture names a field the real status() does not send - it
  // used to invent documents/chunks/path/model, which hid that the pane read
  // fields that never arrive.
  memory: { available: true, db: "C:\\Users\\pcadmin\\.openjarvis\\memory.db",
            facts: 612, current: 590, retired: 22,
            embedder: "BAAI/bge-small-en-v1.5", semantic: true, vector_search: true,
            unembedded: 0, sleep_time: { enabled: false, remind: true } },
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
  { id: "quick_note", label: "Quick note", hint: "Summon the bar ready to file a note - to Logseq, or else the first note app this PC is set up for.",
    accelerator: "Alt+Shift+N", default: "Alt+Shift+N", registered: true, error: null },
  { id: "toggle_widget", label: "Show or hide the widget", hint: "The desktop pane with the meters and the gates.",
    accelerator: "Alt+Shift+W", default: "Alt+Shift+W", registered: true, error: null },
  { id: "stop_everything", label: "Stop everything", hint: "Stops Jarvis talking and anything it is doing on the screen or the phone, at once. Asks nothing first; approves nothing.",
    accelerator: "Alt+Shift+X", default: "Alt+Shift+X", registered: true, error: null },
];

export const UPDATE_NONE = {
  current: "0.1.0", available: null, notes: null, date: null,
  error: null, supported: true, check_on_start: true,
};

export function bridge({ link, pending, attention, digest, telemetry, prefs, answer, brain, theme, hotkeys, refuse, update, found, installFails, restartFails, appearance, noRoute, decideFails, amendFails, appearanceFails, memoryRefuses, learningFloor, learningWaits, apiSettings, tokenSaveRefuses, bindAddressRefuses, bindAddressRefusalMessage, chatReplies, heard, captureFails, speakFails, autoListenFails, speakDelayMs, taskActionFails, taskNoteFails, vision, noteJobs, noteTargets, secondCard, bigModel, deep, voice, caps, security, vt, history, auto, profile, appLock, hardware, schedule, briefing, emailSending }) {
  const listeners = {};
  window.__calls = [];
  window.__emailSending = emailSending || null;
  // App lock on or off, for get_app_lock (apps security audit M3).
  window.__appLock = Boolean(appLock);
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
          case "get_pending_approvals": {
            // A scenario whose queue changes mid-test (a card raised by a
            // click, then denied) sets window.__pendingNow; unset, the
            // scenario's fixed `pending`.
            const items = window.__pendingNow || pending;
            return { count: items.length, items, stale: state.stale };
          }
          case "get_digest": return digest;
          case "mark_digest_seen": return { ok: true, marked: 3 };
          case "set_attention_muted": return { muted: args.muted };
          case "get_widget_prefs":
            return { expanded: true, always_on_top: true, x: null, y: null, ...prefs };
          // commands.rs (apps security audit M3): whether App lock is on,
          // and the widget's "Approve in the Jarvis bar". A scenario sets
          // window.__appLock; unset, the lock is off.
          case "get_app_lock": return Boolean(window.__appLock);
          case "open_approval_in_quickbar":
            window.__openedInBar = (window.__openedInBar || 0) + 1;
            return null;
          case "check_server_health":
            return { services: [{ name: "ollama", online: true },
                                { name: "litellm", online: false, optional: true }] };
          case "get_api_settings": {
            // Mirrors commands.rs pick_token: typed (Credential Manager),
            // then the environment, then the backend's own token - its old
            // plain-text file first, else Credential Manager, the backend's
            // own order (pick_backend_token); empty is "not set" at every
            // step.
            const s = window.__apiSettings;
            const source = s.typedToken ? "credential-manager"
              : s.envToken ? "environment"
              : s.backendFileToken ? "backend-file"
              : s.backendCmToken ? "backend-credential-manager" : null;
            return { base: s.base, hasToken: s.hasToken === false ? false : Boolean(source),
                     tokenSource: s.hasToken === false ? null : source,
                     bindAddress: window.__apiSettings.bindAddress,
                     bindAddressProblem: window.__apiSettings.bindAddressProblem || null,
                     store: "C:\\Users\\pcadmin\\AppData\\Roaming\\jarvis-desktop.json" };
          }
          case "reveal_pairing_token": {
            const s = window.__apiSettings;
            const t = s.typedToken || s.envToken || s.backendFileToken || s.backendCmToken;
            if (!t) throw new Error("there is no token yet - start Jarvis once and it makes one for itself");
            return t;
          }
          case "set_api_settings": {
            window.__calls.push(["__savedApiSettings", args]);
            if (window.__bindAddressRefuses && "bindAddress" in args &&
                args.bindAddress && window.__bindAddressRefuses.includes(args.bindAddress)) {
              throw new Error(window.__bindAddressRefusalMessage || "refused");
            }
            // commands.rs refuses the whole save when Credential Manager
            // refuses the token - it never falls back to a plain-text copy.
            if (args.token && window.__tokenSaveRefuses) throw new Error(window.__tokenSaveRefuses);
            if (args.base !== undefined) window.__apiSettings.base = args.base || "";
            if (args.token) { window.__apiSettings.typedToken = args.token; delete window.__apiSettings.hasToken; }
            if (args.token === "") window.__apiSettings.typedToken = null;
            if ("bindAddress" in args) window.__apiSettings.bindAddress = args.bindAddress || "";
            return window.__apiSettings.saveNote || null;
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
            // A PC without a temporary chat refuses one here, as
            // commands.rs stream_chat does, before anything is sent.
            if (args && args.temporary === true && window.__temporaryOk !== true) {
              throw new Error("Temporary chat isn't available on this PC's version of Jarvis, " +
                "so nothing was sent. Run apply-patches.ps1 on the PC to update it.");
            }
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
                // `{emit, payload}` is not a chunk: it is a Tauri event sent
                // at that point in the answer - a `step` event on the bus,
                // say, or the link going stale - the other road into the
                // window, interleaved the way the real app sees them.
                if (chunk && typeof chunk === "object" && typeof chunk.emit === "string") {
                  window.__emit(chunk.emit, chunk.payload);
                } else {
                  onmessage(chunk);
                }
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
          // Which note apps the PC is set up for: one of the backend's real
          // answers (NOTE_TARGETS). A 2xx hands back its body, as
          // commands.rs note_targets_answer does; anything else is the
          // command failing with `error`, or with the Rust side's sentence.
          case "note_targets": {
            window.__noteTargetCalls = (window.__noteTargetCalls || 0) + 1;
            const t = window.__noteTargets || {};
            if (t.error) throw new Error(t.error);
            if (t.status >= 200 && t.status < 300 && t.body && Array.isArray(t.body.targets)) {
              return t.body;
            }
            throw new Error("this PC's Jarvis does not say which note apps are set up yet - " +
              "copy the new backend files in (run apply-patches.ps1)");
          }
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
            // voice.rs ListenInfo, when a scenario sets it; an older build's
            // nothing otherwise.
            return window.__listenInfo || null;
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
          // commands.rs get_second_card / set_second_card. `status` is a
          // real status() from SECOND_CARD; the Rust passes a 200 on as is.
          // `unavailable` is what it answers for a 404, or the 503
          // `{"available": false}` of a backend without the module; `getFails`
          // / `setFails` are the sentence it rejects with.
          case "get_second_card": {
            const sc = window.__secondCard;
            sc.reads += 1;
            if (sc.getFails) throw new Error(sc.getFails);
            if (sc.unavailable) {
              return { available: false, why: "This PC's Jarvis does not have the second graphics card part yet. Update the backend by running apply-patches.ps1, then open this again." };
            }
            return JSON.parse(JSON.stringify(sc.status));
          }
          case "set_second_card": {
            const sc = window.__secondCard;
            sc.changes.push({ feature: args.feature, enabled: args.enabled });
            if (sc.setFails) throw new Error(sc.setFails);
            // What jarvis_second_card.request_change does to status(): ON
            // puts the switch in `pending` (a card is up, NOTHING is on);
            // OFF clears it at once.
            const st = sc.status;
            const row = (st.features || []).find((f) => f.id === args.feature);
            if (args.enabled) {
              if (!st.pending.includes(args.feature)) st.pending.push(args.feature);
              return { ok: true, enabled: false, pending: true,
                       message: "Approve the card on your PC or phone to turn it on. Nothing changes until you do." };
            }
            if (args.feature === "master") st.enabled = false;
            else if (row) row.enabled = false;
            st.pending = st.pending.filter((p) => p !== args.feature);
            const label = args.feature === "master" ? "The second graphics card" : `"${row ? row.name : args.feature}"`;
            return { ok: true, enabled: false, pending: false, message: `${label} is off.` };
          }
          // voice.rs get_voice_status. `status` is a real status() from
          // VOICE; the Rust passes it on as is. `unavailable` is its answer
          // for a 404 or a server too old for the nested shape; `getFails`
          // is the sentence it rejects with.
          case "get_voice_status": {
            const vs = window.__voice;
            vs.reads += 1;
            if (vs.getFails) throw new Error(vs.getFails);
            if (vs.unavailable) {
              return { available: false, why: "This PC's Jarvis does not report its voice settings yet. Update the backend by running apply-patches.ps1, then open this again." };
            }
            return JSON.parse(JSON.stringify(vs.status));
          }
          // voice_training.rs: Settings' recordings, training, settings,
          // guided test and custom voices. Every answer a scenario gives is a
          // REAL backend answer (TRAINING, with its code as `http`, which is
          // what the Rust passes on); `fails` names commands that reject
          // with a sentence instead. `window.__vt.calls` records each call.
          case "start_voice_sample":
          case "voice_sample_level":
          case "stop_voice_sample":
          case "cancel_voice_sample":
          case "discard_voice_samples":
          case "send_voice_training":
          case "cancel_voice_training":
          case "measure_voice":
          case "set_voice_setting":
          case "check_voice_with_someone_else":
          case "propose_voice_threshold":
          case "get_custom_voices":
          case "create_custom_voice":
          case "set_active_voice":
          case "delete_custom_voice":
          case "set_better_voice": {
            const v = window.__vt;
            if (cmd !== "voice_sample_level") v.calls.push([cmd, JSON.parse(JSON.stringify(args || {}))]);
            if (v.fails[cmd]) throw new Error(v.fails[cmd]);
            switch (cmd) {
              case "start_voice_sample":
                v.recording = args.slot;
                return null;
              case "voice_sample_level":
                return v.level;
              case "stop_voice_sample": {
                const slot = v.recording;
                v.recording = null;
                const t = (v.takes && v.takes[slot]) || v.take;
                return { slot, seconds: t.seconds, peak: t.peak };
              }
              case "cancel_voice_sample":
                v.recording = null;
                return null;
              case "discard_voice_samples":
                return null;
              case "send_voice_training":
                return JSON.parse(JSON.stringify(v.sends.length > 1 ? v.sends.shift() : v.sends[0]));
              case "cancel_voice_training":
                return JSON.parse(JSON.stringify(v.cancel));
              case "measure_voice":
                return JSON.parse(JSON.stringify(v.measure));
              case "set_voice_setting":
                return JSON.parse(JSON.stringify(v.settings[args.value] || v.settings.default));
              // The "someone else" check and its threshold card: a scenario
              // gives the answers (`check`, `threshold`).
              case "check_voice_with_someone_else":
                return JSON.parse(JSON.stringify(v.check || null));
              case "propose_voice_threshold":
                return JSON.parse(JSON.stringify(v.threshold || null));
              case "get_custom_voices":
                v.reads += 1;
                if (v.voicesUnavailable) {
                  return { available: false, why: "This PC's Jarvis does not have custom voices yet. Update the backend by running apply-patches.ps1, then open this again." };
                }
                return JSON.parse(JSON.stringify(v.voices));
              case "create_custom_voice":
                return JSON.parse(JSON.stringify(v.create));
              case "set_active_voice":
                return JSON.parse(JSON.stringify(args.voice === "builtin" ? v.builtin : v.active));
              case "delete_custom_voice":
                return JSON.parse(JSON.stringify(v.del));
              case "set_better_voice":
                return JSON.parse(JSON.stringify(args.enabled ? v.betterOn : v.betterOff));
              default:
                return null;
            }
          }
          // commands.rs get_backend_capabilities: the NAMES the Rust makes
          // of /api/version's capabilities. `answer` is that; `fails` is the
          // sentence it rejects with.
          case "get_backend_capabilities": {
            const c = window.__caps;
            c.reads += 1;
            if (c.fails) throw new Error(c.fails);
            return JSON.parse(JSON.stringify(c.answer));
          }
          // voice.rs set_wake_word. What jarvis_speech.set_wake_enabled does
          // to status(): ON puts a card up (`pending`, NOTHING is on) and
          // answers the real `wake_on_pending`; OFF turns it off at once, and
          // withdraws a waiting card, with the real `wake_off`. `setFails` is
          // the sentence the Rust rejects with (the stale-link hold, say).
          case "set_wake_word": {
            const vs = window.__voice;
            vs.changes.push({ enabled: args.enabled });
            if (vs.setFails) throw new Error(vs.setFails);
            const st = vs.status;
            if (args.enabled) {
              st.listening.wake_word_pending = true;
              st.wake.pending = true;
              return JSON.parse(JSON.stringify(vs.onAnswer));
            }
            st.listening.wake_word = false;
            st.listening.wake_word_pending = false;
            st.wake.enabled = false;
            st.wake.pending = false;
            return JSON.parse(JSON.stringify(vs.offAnswer));
          }
          // hardware.rs. `status` is a real status() from HARDWARE; the
          // Rust passes a 200 on as is. `unavailable` is its answer for a
          // 404 or the 503 of a backend without jarvis_hardware.py. A step
          // is only ever asked for by its id (the Rust reads its route from
          // the backend), and the stub records exactly that.
          case "get_hardware": {
            const h = window.__hardware;
            h.reads += 1;
            if (h.getFails) throw new Error(h.getFails);
            if (h.unavailable) {
              return { available: false, why: "This PC's Jarvis does not have the hardware part yet. Update the backend by running apply-patches.ps1, then open this again." };
            }
            return JSON.parse(JSON.stringify(h.status));
          }
          case "apply_hardware": {
            const h = window.__hardware;
            h.applies.push(args.preset === undefined ? null : args.preset);
            if (h.applyFails) throw new Error(h.applyFails);
            if (h.afterApply) h.status = JSON.parse(JSON.stringify(h.afterApply));
            return JSON.parse(JSON.stringify(h.applyAnswer || { ok: true, chosen: args.preset ?? null,
              message: "Chosen. Nothing has changed yet: each step below is its own approval card, in order." }));
          }
          case "hardware_step": {
            const h = window.__hardware;
            h.steps.push(args.stepId);
            if (h.stepFails) throw new Error(h.stepFails);
            const st = h.status.applying && h.status.applying.steps.find((x) => x.id === args.stepId);
            // keepState: a PC that cannot see the card (a download's card
            // is the owner's file's to shape) still says "next".
            if (st && !h.keepState) st.state = "waiting";
            return { ok: true, pending: true, message: "Approve the card on your PC or phone to make it. Nothing is made until you do." };
          }
          case "measure_hardware": {
            const h = window.__hardware;
            h.measures += 1;
            if (h.measureFails) throw new Error(h.measureFails);
            return JSON.parse(JSON.stringify(h.measureAnswer));
          }
          // commands.rs get_big_model / set_big_model. `status` is a real
          // status() from BIG_MODEL; the Rust passes a 200 on as is.
          // `unavailable` is its answer for a 404, or the 503 `{"available":
          // false}` of a backend without jarvis_big_model.py; `getFails` /
          // `setFails` are the sentence it rejects with.
          case "get_big_model": {
            const bm = window.__bigModel;
            bm.reads += 1;
            if (bm.getFails) throw new Error(bm.getFails);
            if (bm.unavailable) {
              return { available: false, why: "This PC's Jarvis does not have the big model part yet. Update the backend by running apply-patches.ps1, then open this again." };
            }
            return JSON.parse(JSON.stringify(bm.status));
          }
          case "set_big_model": {
            const bm = window.__bigModel;
            bm.changes.push({ switch: args.switch, enabled: args.enabled });
            if (bm.setFails) throw new Error(bm.setFails);
            // What jarvis_big_model.request_change does to status(): ON puts
            // the switch in `pending` and answers the real
            // post_master_on_pending body (a card is up, NOTHING is on); OFF
            // clears it at once, with the backend's "<label> is off.".
            const st = bm.status;
            const row = (st.switches || []).find((s) => s.id === args.switch);
            if (args.enabled) {
              if (!st.pending.includes(args.switch)) st.pending.push(args.switch);
              return JSON.parse(JSON.stringify(bm.onAnswer));
            }
            if (args.switch === "master") st.enabled = false;
            else if (row) row.enabled = false;
            st.pending = st.pending.filter((p) => p !== args.switch);
            const label = args.switch === "master" ? "The big model" : `"${row ? row.name : args.switch}"`;
            return { ok: true, enabled: false, pending: false, message: `${label} is off.` };
          }
          // commands.rs get_deep / ask_deep. `status` is a real
          // deep_status(); `askAnswers` are real POST bodies (the 202 job, or
          // a refusal the Rust passes on as an answer), used in turn, the
          // last one repeating. `askFails` is the sentence it rejects with.
          case "get_deep": {
            const d = window.__deep;
            d.reads += 1;
            if (d.getFails) throw new Error(d.getFails);
            if (d.unavailable) {
              return { available: false, why: "This PC's Jarvis does not have the big model part yet. Update the backend by running apply-patches.ps1, then open this again." };
            }
            return JSON.parse(JSON.stringify(d.status));
          }
          case "ask_deep": {
            const d = window.__deep;
            d.asks.push(args.question);
            if (d.askFails) throw new Error(d.askFails);
            const next = d.askAnswers.length > 1 ? d.askAnswers.shift() : d.askAnswers[0];
            return JSON.parse(JSON.stringify(next));
          }
          case "set_theme": return args.theme;
          case "brain_read": {
            const out = {};
            const sec = window.__security;
            for (const name of args.sections) {
              let body = (brain && brain[name]) || { available: false, error: "not stubbed" };
              // lock.rs redact_private: while private answers are hidden the
              // two memory lists come back EMPTY, with how many there were.
              const key = { memory_facts: "facts", memory_pending: "pending",
                            memory_entities: "entities" }[name];
              if (key && sec.hidden && !sec.revealed && body.available !== false) {
                const count = Array.isArray(body[key]) ? body[key].length : 0;
                body = { ...body, [key]: [], hidden: true, hidden_count: count };
              }
              out[name] = body;
            }
            return out;
          }
          // lock.rs. `settings` is what is stored, `hello` this PC's Windows
          // Hello; `setFails` / `revealFails` are the sentences Rust rejects
          // with (Windows Hello said no, or is not set up).
          case "get_security_settings": {
            const sec = window.__security;
            sec.reads += 1;
            if (sec.getFails) throw new Error(sec.getFails);
            return { settings: { ...sec.settings }, hello: sec.hello };
          }
          case "set_security_settings": {
            const sec = window.__security;
            sec.changes.push(JSON.parse(JSON.stringify(args.settings)));
            if (sec.setFails) throw new Error(sec.setFails);
            sec.settings = { ...args.settings };
            return { ...sec.settings };
          }
          case "reveal_private_answers": {
            const sec = window.__security;
            sec.reveals += 1;
            if (sec.revealFails) throw new Error(sec.revealFails);
            sec.revealed = true;
            return true;
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
          case "brain_memory_erase":
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
              // Since learning-asks.patch, ON raises a card: 202 waiting,
              // still off. Rendering that as "on" or as "off" are both wrong.
              if (window.__learningWaits && args.enabled === true) {
                return { ok: true, waiting: true, enabled: false,
                         message: "Waiting for your approval. Learning turns on only if you approve the card, on your PC or phone." };
              }
              return window.__learningFloor
                ? { ok: true, enabled: false, floor: false,
                    note: "JARVIS_EXTRACT is off in the environment, which overrides this switch." }
                : { ok: true, enabled: args.enabled };
            }
            if (cmd === "brain_memory_sleep_time") {
              if (args.notNow === true) {
                return { ok: true, enabled: false, remind: true,
                         said: "Not now. It will not offer this again for 1 day." };
              }
              return { ok: true, enabled: args.enabled ?? true, remind: args.remind ?? true };
            }
            if (cmd === "brain_memory_forget" || cmd === "brain_memory_erase") {
              // A forgotten (or erased) fact is no longer current, so it leaves the
              // "Saved automatically" list the PC sends.
              // ...and memory_used then says so (brain/used.rs): the fact is
              // still on the PC, only no longer in use.
              const was = window.__auto.facts.find((f) => f.id === args.id);
              window.__usedFacts = window.__usedFacts || {};
              if (was && !window.__usedFacts[args.id]) {
                window.__usedFacts[args.id] = { id: args.id, text: was.text, current: true,
                                                pinned: false, erased_at: null };
              }
              window.__auto.facts = window.__auto.facts.filter((f) => f.id !== args.id);
              const used = window.__usedFacts[args.id];
              if (used) {
                used.current = false;
                used.pinned = false;
                if (cmd === "brain_memory_erase") {
                  used.text = "";
                  used.erased_at = 1790000000;
                }
              }
            }
            return { ok: true };
          case "brain_memory_export":
            // brain.rs saves the export to a file the owner picks in the
            // Windows "Save as" dialog and answers with where it went - or
            // with `cancelled` when the dialog was closed.
            window.__memoryWrites.push({ cmd });
            return window.__exportCancelled
              ? { cancelled: true }
              : { saved: "C:\\Users\\pcadmin\\Documents\\jarvis-memory-2026-09-23.json", facts: 3 };
          case "brain_memory_as_of":
            // The server echoes the moment it answered for; one that could
            // not use the date answers today's list with no `known_at`.
            window.__asOfAsked = args.when;
            return window.__asOfIgnored
              ? { available: true, facts: [{ id: 7, text: "Works in Europe/London.", valid_to: null }] }
              : { available: true, known_at: args.when,
                  facts: [{ id: 4, text: "Standing desk arrives in March.", valid_to: null }] };
          // Chat history (brain/history.rs, JARVIS-API.md section 18). The
          // mock answers the way the four Rust commands do: a page of
          // conversations newest first (`before` exclusive), the list
          // emptied while private answers are hidden, ON as a 202 card when
          // `waits`, and every write recorded in `window.__history`.
          // Automatic learning (brain/auto_learn.rs, JARVIS-API.md section
          // 19). The switches' state is GET /api/memory/learning (Rust says
          // `{available: false}` for a PC without it). The list answers the
          // way the Rust command does: a page of facts newest first
          // (`before` exclusive), with the two switches, emptied while
          // private answers are hidden; each switch's ON is a 202 card when
          // `waits` names it; every call recorded in `window.__auto`.
          // Temporary chat (commands.rs temporary_chat_available): a
          // scenario sets window.__temporaryOk; unset, an older PC.
          case "temporary_chat_available":
            return window.__temporaryOk === true;
          // "Used in this answer" (brain/used.rs memory_used): the facts a
          // scenario puts in window.__usedFacts, by id, in the order asked;
          // unknown ids are `missing`; emptied while the lists are hidden;
          // window.__usedMissingRoute is an older PC.
          case "memory_used": {
            (window.__usedReads = window.__usedReads || []).push([...(args.ids || [])]);
            if (window.__usedMissingRoute) {
              return { available: false,
                       why: "Your PC's Jarvis cannot show which facts these were yet - run apply-patches.ps1 on the PC to update it." };
            }
            const known = window.__usedFacts || {};
            // Unset for an id: the fact as "Saved automatically" lists it.
            const auto = (id) => {
              const f = (window.__auto.facts || []).find((x) => x.id === id);
              return f && { id, text: f.text, current: true, pinned: false, erased_at: null };
            };
            const facts = [];
            const missing = [];
            for (const id of args.ids || []) {
              const f = known[id] || auto(id);
              if (f) facts.push(JSON.parse(JSON.stringify(f)));
              else missing.push(id);
            }
            const out = { facts, missing };
            const sec = window.__security;
            if (sec.hidden && !sec.revealed) {
              out.hidden = true;
              out.hidden_count = out.facts.length;
              out.facts = [];
            }
            return out;
          }
          case "brain_memory_profile": {
            const p = window.__profile;
            if (!p) return null;
            p.reads += 1;
            const facts = JSON.parse(JSON.stringify(p.facts));
            const out = { facts, chars: facts.reduce((n, f) => n + f.text.length, 0), limit: p.limit };
            const sec = window.__security;
            if (sec.hidden && !sec.revealed) {
              out.hidden = true;
              out.hidden_count = out.facts.length;
              out.facts = [];
            }
            return out;
          }
          // brain/schedule.rs (Coming up). `window.__schedule` is null - a PC
          // without the scheduler, which Rust answers {available: false} for -
          // unless the scenario names `schedule: {jobs, todo}`. Words are
          // taken out while the private lists are hidden, as Rust does.
          case "brain_schedule": {
            const sc = window.__schedule;
            if (!sc) {
              return { available: false, why: "Your PC's Jarvis does not have timers and " +
                "reminders yet - run apply-patches.ps1 on the PC." };
            }
            sc.reads += 1;
            if (sc.fails) throw new Error(sc.fails);
            const out = JSON.parse(JSON.stringify({ available: true, jobs: sc.jobs, todo: sc.todo,
              ...(sc.went_off ? { went_off: sc.went_off } : {}),
              ...(sc.lists ? { lists: sc.lists } : {}) }));
            const sec = window.__security;
            if (sec.hidden && !sec.revealed) {
              // As Rust's redact_list: words out, list names replaced.
              const names = [];
              const standIn = (n) => {
                if (!n) return n;
                if (!names.includes(n)) names.push(n);
                return `hidden-${names.indexOf(n) + 1}`;
              };
              for (const l of out.lists || []) { l.name = standIn(l.name); l.title = ""; }
              for (const j of [...out.jobs, ...out.todo, ...(out.went_off || [])]) {
                j.text = ""; j.hidden = true;
                if (j.list) j.list = standIn(j.list);
              }
              out.hidden = true;
            }
            return out;
          }
          case "brain_schedule_act": {
            window.__scheduleCalls.push({ cmd, ...args });
            if (state.stale) throw new Error("the event stream is stale");
            const sc = window.__schedule;
            if (args.action === "snooze") {
              // jarvis_schedule.Scheduler.snooze: a one-off copy, the
              // original leaves "Just went off".
              const w = (sc.went_off || []).find((x) => x.id === args.id);
              if (!w) throw new Error("That is not on the list any more.");
              sc.went_off = sc.went_off.filter((x) => x.id !== args.id);
              const copy = { id: "s" + (0xc000000000 + sc.jobs.length).toString(16), kind: w.kind,
                text: w.text, state: "active", repeats: false, snoozed: true, when: "12:10 today",
                due: Math.floor(Date.now() / 1000) + args.seconds };
              sc.jobs.push(copy);
              return { ok: true, id: args.id, job: copy, said: "Snoozed for 10 minutes - until 12:10." };
            }
            const all = [...sc.jobs, ...sc.todo];
            const j = all.find((x) => x.id === args.id);
            if (!j) throw new Error("That is not on the list any more.");
            if (args.action === "delete" || args.action === "done") {
              sc.jobs = sc.jobs.filter((x) => x.id !== args.id);
              sc.todo = sc.todo.filter((x) => x.id !== args.id);
            } else if (args.action === "pause") j.state = "paused";
            else if (args.action === "resume") j.state = "active";
            return { ok: true, id: args.id, said: { delete: "Deleted.", done: "Marked done.",
              pause: "Paused.", resume: "Resumed." }[args.action] };
          }
          // The standby schedule: the PC raises one card and lists it as
          // waiting (jarvis_schedule.handle_add, 202).
          case "brain_schedule_add_standby": {
            window.__scheduleCalls.push({ cmd, ...args });
            if (state.stale) throw new Error("the event stream is stale");
            const sc = window.__schedule;
            const job = { id: "s" + (0xb000000000 + sc.jobs.length).toString(16), kind: "standby",
                          text: "", state: "waiting", repeats: true,
                          repeat: `every day from ${args.start} to ${args.end}` };
            sc.jobs.push(job);
            return { ok: true, waiting: true, job,
                     said: "It repeats, so it waits for your yes on the card." };
          }
          // brain/briefing.rs (the morning briefing). `window.__briefing` is
          // null - a PC without it, which Rust answers {available: false}
          // for - unless the scenario names `briefing: {...}`. Lines are
          // taken out while the private lists are hidden, as Rust does.
          case "brain_briefing":
          case "brain_briefing_now":
          case "get_briefing_setup": {
            window.__briefingCalls.push({ cmd, ...args });
            const br = window.__briefing;
            if (!br) {
              return { available: false, why: "Your PC's Jarvis does not have the morning " +
                "briefing yet - run apply-patches.ps1 on the PC." };
            }
            br.reads += 1;
            if (br.fails) throw new Error(br.fails);
            // "What did I miss?": the scenario's `missed` answer, or - a PC
            // from before it - an ordinary briefing, as that PC would send.
            if (cmd === "brain_briefing_now" && args.missed) {
              const m = JSON.parse(JSON.stringify(br.missed || br.now || br.briefing));
              const out = JSON.parse(JSON.stringify({ available: true, building: false, briefing: m,
                setups: br.setups, sources: br.sources, senders: br.senders }));
              const sec = window.__security;
              if (out.briefing && sec.hidden && !sec.revealed) {
                for (const s of out.briefing.sections || []) s.items = [];
                out.briefing.hidden = true;
                out.hidden = true;
              }
              return out;
            }
            if (cmd === "brain_briefing_now") br.briefing = JSON.parse(JSON.stringify(br.now || br.briefing));
            const out = JSON.parse(JSON.stringify({ available: true, building: false,
              briefing: br.briefing, setups: br.setups, sources: br.sources,
              senders: br.senders }));
            if (cmd === "get_briefing_setup") out.briefing = null;
            const sec = window.__security;
            if (out.briefing && sec.hidden && !sec.revealed) {
              out.briefing.text = "";
              for (const s of out.briefing.sections || []) s.items = [];
              out.briefing.hidden = true;
              out.hidden = true;
            }
            return out;
          }
          // "Show who new emails are from": OFF at once; ON is a card on
          // the PC (waiting), held on a stale link - as Rust holds it.
          case "set_briefing_senders": {
            window.__briefingCalls.push({ cmd, ...args });
            const br = window.__briefing;
            if (args.enabled && state.stale) throw new Error("the event stream is stale");
            if (!args.enabled) {
              br.senders = { on: false, waiting: false, last: null, why: "" };
              return { ok: true, waiting: false, senders: br.senders,
                       message: "Done - the briefing shows only how many new emails there are." };
            }
            br.senders = { ...(br.senders || {}), waiting: true };
            return { ok: true, waiting: true, senders: br.senders,
                     message: "Waiting for your approval. Names are shown only if you approve the card, on your PC or phone." };
          }
          case "set_briefing":
          case "stop_briefing": {
            window.__briefingCalls.push({ cmd, ...args });
            if (state.stale) throw new Error("the event stream is stale");
            const br = window.__briefing;
            if (cmd === "stop_briefing") {
              br.setups = br.setups.filter((j) => j.id !== args.id);
              return { ok: true, id: args.id, said: "Deleted." };
            }
            const rule = args.every === "week" ? `every ${args.days.length} chosen days at ${args.at}`
              : args.every === "day" ? `every day at ${args.at}`
                : `every weekday (Monday to Friday) at ${args.at}`;
            const job = { id: "s" + (0xb000000000 + br.setups.length).toString(16), kind: "briefing",
              state: "waiting", repeats: true, repeat: rule };
            br.setups.push(job);
            return { ok: true, waiting: true, job, said: "It repeats, so it waits for your yes on the card." };
          }
          case "brain_schedule_add_todo": {
            window.__scheduleCalls.push({ cmd, ...args });
            const sc = window.__schedule;
            const job = { id: "s" + (0xa000000000 + sc.todo.length).toString(16), kind: "todo",
                          text: args.text, list: args.list || "",
                          state: "active", repeats: false };
            sc.todo.push(job);
            if (args.list) {
              sc.lists = sc.lists || [];
              const l = sc.lists.find((x) => x.name === args.list);
              if (l) l.open += 1;
              else sc.lists.push({ name: args.list, title: args.list[0].toUpperCase() + args.list.slice(1) + " list", open: 1 });
            }
            return { ok: true, job };
          }
          // One NAMED list cleared - only when the count the page showed
          // is still right (jarvis_schedule.Scheduler.clear_list).
          case "brain_schedule_clear_list": {
            window.__scheduleCalls.push({ cmd, ...args });
            if (state.stale) throw new Error("the event stream is stale");
            const sc = window.__schedule;
            const items = sc.todo.filter((x) => x.list === args.list);
            if (items.length !== args.count) {
              return { ok: false, error: "The list changed since you looked. Look again before clearing it." };
            }
            sc.todo = sc.todo.filter((x) => x.list !== args.list);
            sc.lists = (sc.lists || []).filter((x) => x.name !== args.list);
            return { ok: true, cleared: items.length, said: `Cleared your ${args.list} list (${items.length} items).` };
          }
          case "brain_memory_pin": {
            window.__memoryWrites.push({ cmd, ...args });
            const p = window.__profile;
            if (!p) throw new Error("HTTP 404");
            if (args.pinned && p.refuse) throw new Error(String(p.refuse));
            p.facts = p.facts.filter((f) => f.id !== args.id);
            if (args.pinned) {
              const known = [...window.__auto.facts, ...((window.__brain.memory_facts || {}).facts || [])]
                .find((f) => f.id === args.id);
              p.facts.push({ id: args.id, text: known ? known.text : `fact ${args.id}`, added: Date.now() / 1000 });
            }
            return { ok: true, id: args.id, pinned: args.pinned, changed: true };
          }
          case "brain_memory_learning_status": {
            const a = window.__auto;
            a.statusReads += 1;
            if (a.statusFails) throw new Error(a.statusFails);
            if (a.statusMissing) return { available: false };
            return JSON.parse(JSON.stringify({ auto_last: null, sensitive_last: null, ...a.status }));
          }
          case "brain_memory_auto_list": {
            const a = window.__auto;
            a.reads.push({ before: args.before, limit: args.limit });
            if (a.listFails) throw new Error(a.listFails);
            if (a.missing) {
              return { available: false, why: "This PC's Jarvis does not learn automatically yet. " +
                "Update the backend by running apply-patches.ps1, then open this again." };
            }
            const all = [...a.facts].sort((x, y) => y.saved_at - x.saved_at);
            const older = args.before == null ? all : all.filter((f) => f.saved_at < args.before);
            const out = JSON.parse(JSON.stringify({ auto: a.status.auto, auto_sensitive: a.status.auto_sensitive,
                                                    facts: older.slice(0, args.limit || 30) }));
            const sec = window.__security;
            if (sec.hidden && !sec.revealed) {
              out.hidden = true;
              out.hidden_count = out.facts.length;
              out.facts = [];
            }
            return out;
          }
          case "brain_memory_learning_auto":
          case "brain_memory_learning_sensitive": {
            const a = window.__auto;
            const which = cmd === "brain_memory_learning_auto" ? "auto" : "sensitive";
            const field = which === "auto" ? "auto" : "auto_sensitive";
            a.switches.push({ which, enabled: args.enabled });
            if (a.switchFails) throw new Error(a.switchFails);
            if (args.enabled === true && a.waits.includes(which)) {
              a.status[`${which}_waiting`] = true;
              return { ok: true, waiting: true, [field]: false,
                       message: "Waiting for your approval. It turns on only if you approve the card, on your PC or phone." };
            }
            a.status[field] = args.enabled === true;
            a.status[`${which}_waiting`] = false;
            // OFF: the PC's own sentence (jarvis_auto_learn.request), unless
            // a scenario is an older PC that sent none (`offSilent`).
            if (args.enabled !== true && !a.offSilent) {
              return { ok: true, waiting: false, [field]: false, message: a.offMessage || (which === "auto"
                ? "\"Learn automatically\" is off. Every fact waits for your yes."
                : "Sensitive topics wait for your yes.") };
            }
            return { ok: true, [field]: args.enabled === true };
          }
          // Rust's count of `memory_saved` ids the owner has not looked at
          // (brain/auto_learn.rs): `unseen` in the scenario, every call kept.
          case "brain_memory_saved_unseen": {
            const a = window.__auto;
            a.unseenCalls.push(args.seen === true);
            const ids = [...a.unseen];
            if (args.seen === true) a.unseen = [];
            return { ids: args.seen === true ? [] : ids };
          }
          case "brain_history_list": {
            const h = window.__history;
            h.reads.push({ before: args.before, limit: args.limit });
            if (h.listFails) throw new Error(h.listFails);
            if (h.missing) {
              return { available: false, why: "This PC's Jarvis does not keep chat history yet. " +
                "Update the backend by running apply-patches.ps1, then open this again." };
            }
            const all = [...h.conversations].sort((a, b) => b.updated - a.updated);
            const older = args.before == null ? all : all.filter((c) => c.updated < args.before);
            const page = older.slice(0, args.limit || 30);
            const out = JSON.parse(JSON.stringify({ ...h.status, conversations: page }));
            const sec = window.__security;
            if (sec.hidden && !sec.revealed) {
              out.hidden = true;
              out.hidden_count = out.conversations.length;
              out.conversations = [];
            }
            return out;
          }
          case "brain_history_open": {
            const h = window.__history;
            h.opened.push(args.id);
            const sec = window.__security;
            if (sec.hidden && !sec.revealed) {
              throw new Error("Your chat history is hidden. Press Show on the Brain's History tab " +
                "and confirm it is you with Windows Hello first.");
            }
            const t = h.transcripts[args.id];
            if (!t) {
              throw new Error("That conversation is no longer kept on this PC. It was deleted, " +
                "or it was older than the keep setting.");
            }
            return JSON.parse(JSON.stringify(t));
          }
          case "brain_history_delete": {
            const h = window.__history;
            h.deleted.push(args.id);
            const had = h.conversations.some((c) => c.id === args.id);
            h.conversations = h.conversations.filter((c) => c.id !== args.id);
            return had ? { ok: true } : { ok: true, gone: true };
          }
          case "brain_history_settings": {
            const h = window.__history;
            h.settings.push({ enabled: args.enabled, keepDays: args.keepDays });
            if (h.settingsFails) throw new Error(h.settingsFails);
            if (args.enabled === true) {
              if (h.waits) {
                h.status.waiting = true;
                return { ok: true, waiting: true, enabled: false,
                         message: "Waiting for your approval. Chat history turns on only if you approve the card, on your PC or phone." };
              }
              Object.assign(h.status, { enabled: true, recording: true, why_not: "", waiting: false });
              return { ok: true, enabled: true };
            }
            if (args.enabled === false) {
              Object.assign(h.status, { enabled: false, recording: false, waiting: false,
                                        why_not: "Chat history is off." });
              return { ok: true, enabled: false };
            }
            h.status.keep_days = args.keepDays;
            return { ok: true, keep_days: args.keepDays, deleted: h.deletedByKeep || 0 };
          }
          // email_sending.rs: the Settings line for sending email.
          // `window.__emailSending` is the PC's answer (a scenario's, else
          // "set up, not offered to the model yet").
          case "get_email_sending":
            return JSON.parse(JSON.stringify(window.__emailSending));
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
  window.__noteTargets = JSON.parse(JSON.stringify(noteTargets || {}));
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
  window.__learningWaits = Boolean(learningWaits);
  window.__found = found || null;
  window.__installFails = installFails || null;
  window.__restartFails = restartFails || null;
  window.__refuse = refuse || [];
  window.__apiSettings = { base: "http://127.0.0.1:4719", bindAddress: "",
                            typedToken: null, envToken: null, backendFileToken: "backend-made-token",
                            ...(apiSettings || {}) };
  window.__bindAddressRefuses = bindAddressRefuses || null;
  window.__tokenSaveRefuses = tokenSaveRefuses || null;
  window.__bindAddressRefusalMessage = bindAddressRefusalMessage || null;
  // Unset, the PC as it is today: one graphics card (the real `one_card`).
  window.__secondCard = { reads: 0, changes: [], getFails: null, setFails: null,
                          unavailable: false, ...(secondCard || {}) };
  window.__secondCard.status = JSON.parse(JSON.stringify(window.__secondCard.status || null));
  // Unset, the PC as it is today: one card, jarvis-primary, nothing chosen
  // (the real `today_one_card`).
  window.__hardware = { reads: 0, applies: [], steps: [], measures: 0, getFails: null,
                        applyFails: null, stepFails: null, measureFails: null,
                        unavailable: false, ...(hardware || {}) };
  window.__hardware.status = JSON.parse(JSON.stringify(window.__hardware.status || null));
  // Unset, the PC as it is today: colibri not installed yet (the real
  // `status_not_installed`), and deep questions off (`deep_off`).
  window.__bigModel = { reads: 0, changes: [], getFails: null, setFails: null,
                        unavailable: false, ...(bigModel || {}) };
  window.__bigModel.status = JSON.parse(JSON.stringify(window.__bigModel.status || null));
  window.__deep = { reads: 0, asks: [], askAnswers: [], getFails: null, askFails: null,
                    unavailable: false, ...(deep || {}) };
  window.__deep.status = JSON.parse(JSON.stringify(window.__deep.status || null));
  window.__deep.askAnswers = JSON.parse(JSON.stringify(window.__deep.askAnswers));
  // Unset, the voice as most owners have it: trained on the phone, "hey
  // Jarvis" off (the real `phone_trained`).
  window.__voice = { reads: 0, changes: [], getFails: null, setFails: null,
                     unavailable: false, ...(voice || {}) };
  window.__voice.status = JSON.parse(JSON.stringify(window.__voice.status || null));
  // Settings' voice training and custom voices (voice_training.rs), with
  // the real answers open() fills in; a scenario names only what it changes.
  window.__vt = { calls: [], fails: {}, reads: 0, recording: null, level: 0.3,
                  take: { seconds: 2.6, peak: 0.42 }, takes: null, voicesUnavailable: false,
                  ...(vt || {}) };
  // Unset, what commands.rs makes of backend/rebuilt/jarvis_events.hello()
  // run with none of the owner's own modules (its Rust test pins the same).
  // Unset, lock.rs's defaults on a PC with Windows Hello set up, and the
  // Brain's memory lists shown.
  window.__security = { reads: 0, changes: [], reveals: 0, getFails: null, setFails: null,
                        revealFails: null, hidden: false, revealed: false, hello: "ready",
                        settings: { appLock: false, relockAfterSecs: 60, approvals: "risky",
                                    privateAnswers: false },
                        ...(security || {}) };
  window.__caps = { reads: 0, fails: null,
                    answer: { server: "jarvis-hud", api: 1, on: ["memory", "power", "voice"],
                              off: ["appearance", "approvals", "connectors", "models", "persona", "skills"] },
                    ...(caps || {}) };
  window.__vision = vision || { model: "qwen3:8b", vision: false,
    reason: "Ollama lists what qwen3:8b can do, and pictures are not on the list." };
  // Unset, history as the owner has it by default: on, recording, kept
  // until deleted, and nothing kept yet.
  window.__history = JSON.parse(JSON.stringify({
    missing: false, waits: false, listFails: null, settingsFails: null, deletedByKeep: 0,
    conversations: [], transcripts: {},
    ...(history || {}),
    status: { enabled: true, recording: true, why_not: "", waiting: false, keep_days: 0,
              encrypted: true, ...((history && history.status) || {}) },
  }));
  Object.assign(window.__history, { reads: [], opened: [], deleted: [], settings: [] });
  // Unset, automatic learning as the owner has it by default: learning on,
  // learning automatically on, sensitive topics off, nothing waiting, and
  // nothing saved yet. `missing` is a PC without the list, `statusMissing`
  // one without GET /api/memory/learning.
  window.__auto = JSON.parse(JSON.stringify({
    missing: false, statusMissing: false, waits: [], listFails: null, statusFails: null,
    switchFails: null, facts: [], unseen: [], offSilent: false,
    ...(auto || {}),
    status: { enabled: true, auto: true, auto_sensitive: false, auto_waiting: false,
              sensitive_waiting: false, ...((auto && auto.status) || {}) },
  }));
  Object.assign(window.__auto, { reads: [], statusReads: 0, switches: [], unseenCalls: [] });
  // "Always keep in mind" (brain/profile.rs). Unset, the command answers
  // null - as before the list existed - so a scenario that does not name it
  // draws no Pin buttons. `facts` is [{id, text, added}]; `refuse` is the
  // PC's sentence for a refused pin (Rust hands it on as the error).
  window.__profile = profile ? JSON.parse(JSON.stringify({
    facts: [], limit: 1200, refuse: null, reads: 0, ...profile })) : null;
  window.__schedule = schedule ? JSON.parse(JSON.stringify({
    jobs: [], todo: [], reads: 0, fails: null, ...schedule })) : null;
  window.__scheduleCalls = [];
  window.__briefing = briefing ? JSON.parse(JSON.stringify({
    briefing: null, setups: [], sources: {}, reads: 0, fails: null, ...briefing })) : null;
  window.__briefingCalls = [];
  window.__emit = (n, p) => (listeners[n] || []).forEach(f => f({ payload: p }));
  window.__answer = answer;
  window.__brain = brain;
}

export async function launch() {
  // `executablePath: undefined` means "use Playwright's own", which is the
  // right answer on a normal checkout.
  return chromium.launch(CHROME ? { executablePath: CHROME } : {});
}

/**
 * A speaker whose every clip lasts `playMs`, for the quickbar's spoken
 * replies (main.js drainSpeechQueue). Each clip `speak_reply` returns is
 * tagged with its sentence (a `#` fragment on the data URI), and "playing"
 * one writes `["play", text]` and, `playMs` later, `["end", text]` into
 * `window.__voiceCalls`, next to the `["speak", text]` of each request - so
 * a test can read what was asked for, what was played, and in what order.
 * `window.__mostAsking` is the most `speak_reply` requests ever in flight
 * at once.
 */
export function slowSpeaker(page, playMs) {
  return page.evaluate((ms) => {
    const core = window.__TAURI__.core;
    const invoke = core.invoke;
    let asking = 0;
    window.__mostAsking = 0;
    core.invoke = async (cmd, args) => {
      if (cmd !== "speak_reply") return invoke(cmd, args);
      asking += 1;
      window.__mostAsking = Math.max(window.__mostAsking, asking);
      try {
        const out = await invoke(cmd, args);
        return typeof out === "string" ? `${out}#${encodeURIComponent(args.text)}` : out;
      } finally {
        asking -= 1;
      }
    };
    HTMLMediaElement.prototype.play = function () {
      const text = decodeURIComponent(String(this.src).split("#")[1] || "");
      window.__voiceCalls.push(["play", text]);
      setTimeout(() => {
        window.__voiceCalls.push(["end", text]);
        this.dispatchEvent(new Event("ended"));
      }, ms);
      return Promise.resolve();
    };
  }, playMs);
}

/** What `slowSpeaker` wrote down: `"speak One."`, `"play One."`, `"end One."`, in order. */
export function speechLog(page) {
  return page.evaluate(() => (window.__voiceCalls || [])
    .filter((c) => Array.isArray(c) && ["speak", "play", "end"].includes(c[0]))
    .map((c) => `${c[0]} ${c[1]}`));
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
    noteTargets: NOTE_TARGETS.all,
    heard: null, captureFails: null, speakFails: null, autoListenFails: null, speakDelayMs: 0,
    memoryRefuses: null, learningFloor: false, learningWaits: false, apiSettings: null, tokenSaveRefuses: null,
    bindAddressRefuses: null, bindAddressRefusalMessage: null, chatReplies: null,
    vision: null,
    emailSending: EMAIL_SENDING.cases.tool_off,
    secondCard: { status: SECOND_CARD.one_card },
    appearance: { face: null, bindings: {}, updated: 0, source: "default", shared: false },
    ...data,
    // A scenario names only what it changes; the real POST answers stay.
    hardware: { status: HARDWARE.today_one_card,
                measureAnswer: HARDWARE.post_measure_started.body, ...(data && data.hardware) },
    bigModel: { status: BIG_MODEL.status_not_installed,
                onAnswer: BIG_MODEL.post_master_on_pending.body, ...(data && data.bigModel) },
    deep: { status: BIG_MODEL.deep_off, askAnswers: [BIG_MODEL.ask_accepted.body],
            ...(data && data.deep) },
    voice: { status: VOICE.cases.phone_trained, onAnswer: VOICE.answers.wake_on_pending,
             offAnswer: VOICE.answers.wake_off, ...(data && data.voice) },
    vt: {
      sends: [TRAINING.answer(TRAINING.enroll.round_held)],
      cancel: TRAINING.answer(TRAINING.enroll.cancel),
      measure: TRAINING.answer(TRAINING.enroll.measure),
      settings: {
        balanced: TRAINING.answer(TRAINING.enroll.loosen_strictness),
        voice_is_enough: TRAINING.answer(TRAINING.enroll.loosen_privacy),
        very_strict: TRAINING.answer(TRAINING.enroll.tighten_strictness),
        private_on_screen: TRAINING.answer(TRAINING.enroll.tighten_privacy),
        default: TRAINING.answer(TRAINING.enroll.tighten_already),
      },
      voices: TRAINING.voices.builtin_nothing_installed,
      create: TRAINING.answer(TRAINING.voice_posts.create_accepted),
      active: TRAINING.answer(TRAINING.voice_posts.switch_pending),
      builtin: TRAINING.answer(TRAINING.voice_posts.builtin),
      del: TRAINING.answer(TRAINING.voice_posts.delete),
      betterOn: TRAINING.answer(TRAINING.voice_posts.better_on_pending),
      betterOff: TRAINING.answer(TRAINING.voice_posts.better_off),
      ...(data && data.vt),
    },
  });
  await page.goto(`${base}/${file}`);
  await page.waitForTimeout(500);
  page.__errors = errors;
  return page;
}
