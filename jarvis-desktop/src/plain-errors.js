/**
 * Plain words when something goes wrong, with the fix on the spot (the
 * creativity audit, 2026-09-25, item 5; JARVIS-API.md section 4, "When an
 * answer fails").
 *
 * One mapping from each kind of failure to a short sentence (`says`), one
 * thing to do (`fix`), and one button (`button`, `action`). The SAME words
 * as the phone's net/PlainErrors.kt: both are checked, word for word,
 * against tests/fixtures/plain-error-cases.json, which
 * tools/gen_plain_error_cases.py writes from the one list (tests/
 * plain-errors.mjs here, PlainErrorsTest.kt there). Change a word there,
 * regenerate, then change it here and on the phone.
 *
 * The technical detail is kept for a bug report behind "Details", scrubbed
 * first ([scrubDetails]) - no token, key, password, email address or
 * Windows user name, the same rules as the backend's log scrubber.
 *
 * Pure: no DOM, no Tauri. main.js draws it.
 *
 * @module plain-errors
 */

/** The buttons, by action. */
export const BUTTONS = Object.freeze({
  retry: "Try again",
  reconnect: "Reconnect",
  connection: "Check the connection settings",
  models: "Choose a model",
  none: "",
});

/** Every kind: [says, fix, action]. */
const TABLE = {
  pc_unreachable: [
    "Your PC isn't answering.",
    "It may be asleep or switched off, or Tailscale or NordVPN Meshnet may be off at one end. Wake the PC, check the private network on both, then try again.",
    "retry",
  ],
  jarvis_not_running: [
    "Jarvis isn't running on your PC.",
    "The PC is on, but Jarvis is not started. Start it from the desktop app (Settings, Start Jarvis), then try again.",
    "retry",
  ],
  name_not_found: [
    "This device can't find your PC by its name.",
    "Check that Tailscale or NordVPN Meshnet is on here, and that the PC's name in the connection settings is right.",
    "connection",
  ],
  device_offline: [
    "This device isn't connected to a network.",
    "Turn on Wi-Fi or mobile data, then try again.",
    "retry",
  ],
  connection_dropped: [
    "The connection to your PC dropped.",
    "Try again. If it keeps happening, check the private network is steady at both ends.",
    "retry",
  ],
  link_stale: [
    "The connection to your PC is catching up.",
    "Nothing can be sent until it does. Wait a moment, or reconnect.",
    "reconnect",
  ],
  token_wrong: [
    "Your PC didn't accept this app's pairing key.",
    "Enter the key again in the connection settings. The PC's desktop app shows it: Settings, \"Show the token for my phone\".",
    "connection",
  ],
  not_paired: [
    "This app isn't connected to a PC yet.",
    "Add your PC's name and pairing key in the connection settings.",
    "connection",
  ],
  not_jarvis: [
    "Something answered at that address, but it isn't Jarvis.",
    "Check the PC's name and port in the connection settings.",
    "connection",
  ],
  backend_too_old: [
    "Your PC's Jarvis is too old for this.",
    "Update it: on the PC, run apply-patches.ps1, then restart Jarvis.",
    "none",
  ],
  feature_off: [
    "That part of Jarvis isn't running on your PC right now.",
    "Restart Jarvis on the PC. If it stays off, run apply-patches.ps1 there to update it.",
    "none",
  ],
  server_error: [
    "Jarvis on your PC ran into a problem.",
    "Try again. If it keeps happening, restart Jarvis on the PC and send the Details with a bug report.",
    "retry",
  ],
  unreadable: [
    "Your PC answered in a way this app can't read.",
    "Update both: run apply-patches.ps1 on the PC, and install the latest app.",
    "none",
  ],
  timeout: [
    "Jarvis took too long to answer.",
    "Try again in a moment. If it keeps happening, restart Ollama on the PC.",
    "retry",
  ],
  model_missing: [
    "The AI model Jarvis uses isn't installed on your PC.",
    "Choose a model you have (Models, in the Brain on the PC or the phone), or install this one.",
    "models",
  ],
  model_not_running: [
    "The AI model isn't running on your PC.",
    "Open Ollama on the PC (or restart Jarvis), then try again.",
    "retry",
  ],
  model_stuck: [
    "The AI model stopped answering.",
    "Restart Ollama on the PC, then try again.",
    "retry",
  ],
  model_stopped: [
    "The AI model stopped in the middle of the answer.",
    "Try again. If it keeps happening, restart Ollama on the PC.",
    "retry",
  ],
  model_error: [
    "The AI model reported a problem.",
    "Try again. If it keeps happening, restart Ollama on the PC.",
    "retry",
  ],
  key_store_refused: [
    "Windows Credential Manager wouldn't save it.",
    "Nothing was written anywhere else. Try again; if it keeps failing, restart the PC and try once more.",
    "retry",
  ],
  // The PC said what is wrong in its own sentence: shown as it is.
  pc_said: ["", "", "none"],
};

/** kind -> { says, fix, action, button } */
export const KINDS = Object.freeze(
  Object.fromEntries(
    Object.entries(TABLE).map(([kind, [says, fix, action]]) => [
      kind,
      Object.freeze({ says, fix, action, button: BUTTONS[action] }),
    ])
  )
);

/** The waits. "loading" is the PC's word for a model not yet in memory. */
export const STATUSES = Object.freeze({
  thinking: "Thinking…",
  loading: "Waking up the model - the first answer after standby takes a little longer.",
  working: "Working…",
  approval: "Waiting for your approval…",
  answering: "Answering…",
});

/** The stream's error `code` (jarvis_agent.ERROR_CODES) -> a kind. */
export const CODES = Object.freeze({
  model_missing: "model_missing",
  model_not_running: "model_not_running",
  model_stuck: "model_stuck",
  model_stopped: "model_stopped",
  model_error: "model_error",
});

/** The Details are at most this long, after scrubbing. */
export const DETAILS_MAX = 600;

const NETWORK = Object.freeze({
  refused: "jarvis_not_running",
  connect_timeout: "pc_unreachable",
  no_route: "pc_unreachable",
  unknown_host: "name_not_found",
  no_network: "device_offline",
  read_timeout: "timeout",
  dropped: "connection_dropped",
});

const said = (input) => (typeof input.said === "string" ? input.said.trim() : "");

/**
 * The kind for one failure, described the way the contract file does:
 * `{network}`, `{http, said?, available?}`, `{code?, said}`, `{stale}`,
 * `{not_paired}`, `{malformed}`, `{not_jarvis}`, `{key_store}`.
 */
export function classify(input) {
  const i = input && typeof input === "object" ? input : {};
  if (i.not_paired) return "not_paired";
  if (i.stale) return "link_stale";
  if (i.key_store) return "key_store_refused";
  if (i.not_jarvis) return "not_jarvis";
  if (i.malformed) return "unreadable";
  if (typeof i.network === "string") return NETWORK[i.network] || "connection_dropped";
  if (typeof i.code === "string" && CODES[i.code]) return CODES[i.code];
  const http = Number.isInteger(i.http) ? i.http : null;
  if (http === 401 || http === 403) return "token_wrong";
  if (http === 501) return "backend_too_old";
  if (http === 503 && i.available === false) return "backend_too_old";
  if (said(i)) return "pc_said";
  if (http === 404) return "backend_too_old";
  if (http === 503) return "feature_off";
  if (http !== null) return "server_error";
  return "server_error";
}

/** First letter raised: the PC's sentences start in lower case. */
function sentence(text) {
  const t = String(text || "").trim();
  if (!t) return t;
  const s = t.charAt(0).toUpperCase() + t.slice(1);
  return /[.!?]$/.test(s) ? s : `${s}.`;
}

/**
 * What to show: `{kind, says, fix, button, action}`. For "pc_said" the
 * PC's own sentence is `says` and there is no fix and no button.
 */
export function shown(kind, pcSaid = "") {
  const k = KINDS[kind] || KINDS.server_error;
  if (kind === "pc_said") {
    return { kind, says: sentence(pcSaid) || KINDS.server_error.says, fix: "", button: "", action: "none" };
  }
  return { kind: KINDS[kind] ? kind : "server_error", says: k.says, fix: k.fix, button: k.button, action: k.action };
}

/* ── The Details scrubber ─────────────────────────────────────────────
   The backend's log scrubber's rules (backend/jarvis_scrub.py), for text
   an app shows: the token it holds, then shapes. IP addresses, ports,
   paths after the user name and status codes stay - a bug report needs
   them. */

const HIDDEN = "[hidden]";
const SHAPES = [
  // X-Jarvis-Token / Authorization headers, and Bearer/Basic values.
  [/(x-jarvis-token["']?\s*[:=]\s*["']?)[^\s"'&,;]+/gi, `$1${HIDDEN}`],
  [/\b(authorization\s*:\s*)(?:bearer|basic|token)?\s*[^\s"',;]+/gi, `$1${HIDDEN}`],
  [/\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}/gi, `$1 ${HIDDEN}`],
  // A password inside a URL: scheme://user:password@host
  [/\b([a-z][a-z0-9+.-]*:\/\/[^/\s:@]+:)[^/\s@]+(?=@)/gi, `$1${HIDDEN}`],
  // A secret in a query: ?token=..., &key=..., &api_key=..., &password=...
  [/([?&](?:access_|refresh_|id_|auth_)?(?:token|api[_-]?key|key|secret|password|passwd|sig|signature)=)[^&\s#"']+/gi, `$1${HIDDEN}`],
  // Labelled: password = x, token: x, api key = x, secret=x
  [/\b((?:api[ _-]?key|token|secret|password|passwd|pwd|passphrase)\s*[:=]\s*["']?)[^\s"',;&]+/gi, `$1${HIDDEN}`],
  // Key shapes (jarvis_router's table, and the search keys').
  [/-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|$)/g, HIDDEN],
  [/\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g, HIDDEN],
  [/\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{22,})/g, HIDDEN],
  [/\bglpat-[A-Za-z0-9_-]{20,}/g, HIDDEN],
  [/\b(?:sk|rk)_(?:test|live)_[A-Za-z0-9]{16,}/g, HIDDEN],
  [/\bsk-[A-Za-z0-9_-]{16,}/g, HIDDEN],
  [/\btvly-[A-Za-z0-9_-]{12,}/g, HIDDEN],
  [/\bya29\.[0-9A-Za-z_-]{20,}/g, HIDDEN],
  [/\bxox[baprs]-[A-Za-z0-9-]{10,}/g, HIDDEN],
  [/\bAIza[0-9A-Za-z_-]{30,}/g, HIDDEN],
  [/\bhf_[A-Za-z0-9]{30,}/g, HIDDEN],
  [/\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/g, HIDDEN],
  [/\/private-[0-9a-f]{16,}/gi, `/${HIDDEN}`],
  // A long run of letters AND digits with no spaces: a token with no prefix
  // (the pairing token is 43 of them). Hex ids of 32 and fewer stay.
  [/(?<![\w./-])(?=[A-Za-z0-9_-]*[A-Za-z])(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{33,}(?![\w-])/g, HIDDEN],
  // Email addresses, and the Windows (or Linux/macOS) user name.
  [/(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+/g, "[email]"],
  [/(\b[a-z]:[\\/]+users[\\/]+|(?<![\w.])\/home\/|(?<![\w.])\/Users\/)[^\\/\s]+/gi, "$1[user]"],
];

/**
 * `text` with every secret taken out, cut to DETAILS_MAX. `token` - the
 * pairing token this app holds, if it has it - goes first, whatever it
 * looks like.
 */
export function scrubDetails(text, token = "") {
  let out = String(text == null ? "" : text);
  if (typeof token === "string" && token.length >= 4) out = out.split(token).join(HIDDEN);
  for (const [rx, to] of SHAPES) out = out.replace(rx, to);
  out = out.replace(/\s+/g, " ").trim();
  return out.length > DETAILS_MAX ? `${out.slice(0, DETAILS_MAX - 1)}…` : out;
}

/* ── The desktop's own failures ────────────────────────────────────── */

/** stream_chat's marker for a failed chat (plain_errors.rs ERROR_LINE_PREFIX). */
export const ERROR_LINE_PREFIX = "\u001fjarvis-error:";

/**
 * A failed chat, as `stream_chat` rejects: a tagged line of facts, or (an
 * older build, or a failure before the request) a plain sentence.
 * Returns `{kind, says, fix, button, action, details}`.
 */
export function fromChatFailure(error) {
  const text = String((error && error.message) || error || "");
  if (text.startsWith(ERROR_LINE_PREFIX)) {
    let facts = {};
    try {
      facts = JSON.parse(text.slice(ERROR_LINE_PREFIX.length)) || {};
    } catch {
      facts = {};
    }
    const kind = classify(facts);
    const detail = [facts.http ? `HTTP ${facts.http}` : "", facts.network || "", facts.detail || ""]
      .filter(Boolean).join(" · ");
    return { ...shown(kind, facts.said), details: scrubDetails(`(${kind}) ${detail}`) };
  }
  // A sentence this app wrote itself: it is the plain words.
  return { ...shown("pc_said", text), details: scrubDetails(text) };
}

/**
 * An error the PC sent INSIDE the answer (`{"error": {"message", "code"}}`):
 * the plain words for its code, the PC's sentence behind Details. A code
 * this app does not know shows the PC's sentence as it is.
 */
export function fromStreamError(error) {
  const e = error && typeof error === "object" ? error : { message: String(error || "") };
  const message = String(e.message || "").trim();
  const kind = classify({ code: typeof e.code === "string" ? e.code : undefined, said: message });
  return { ...shown(kind, message), details: scrubDetails(`(${kind}) ${message}`) };
}
