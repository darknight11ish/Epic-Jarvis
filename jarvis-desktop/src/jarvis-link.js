/**
 * The one place a desktop surface learns what Jarvis is doing.
 *
 * Rust holds a single `GET /api/events` open and fans every frame out to all
 * three windows. Nothing in here opens a connection, polls an endpoint, or
 * decides whether an approval is still open — it subscribes to what the backend
 * already knows and hands the decision straight back to `decide_approval`.
 *
 * Before this module the quickbar and the widget each ran a 30-second probe and
 * each kept its own idea of the approval queue. That is two lists, taken at two
 * moments, and two chances to offer a decision on something the other has
 * already answered — which is the same 409 race twice over. There is now one
 * list, read once, by the process that also sends the decision.
 *
 * @module jarvis-link
 */

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);

/** Event names, matching `crate::events` in the Rust side. */
const EV_LINK = "jarvis-link";
const EV_APPROVALS = "approvals-changed";
const EV_EVENT = "jarvis-event";
const EV_RESYNC = "jarvis-resync";

/**
 * The link as last reported. `stale: true` until the stream says otherwise:
 * before the first `hello` nothing is known, and a surface that enabled its
 * Approve button on load would be answering a queue nobody has read.
 */
let link = {
  connected: false,
  stale: true,
  base: "",
  lastId: 0,
  power: "active",
  powerSetBy: null,
  activity: "idle",
  // What `announce()` last said, if anything - docs/AUTONOMY-PROPOSALS.md
  // §3c. Purely additive: a backend that has not been patched to send
  // `activity_detail` yet leaves this "" forever, same as `activity` did
  // before this field existed, and nothing here changes for it.
  activityDetail: "",
  approvals: 0,
  attention: emptyAttention(),
  error: null,
};

/**
 * The interruption budget before anything has been read.
 *
 * `known: false` is the field that matters. Every count here is zero, and a
 * zero that means "not asked yet" would draw an empty digest and a cleared
 * badge over a queue nobody has looked at — so a surface renders "unknown"
 * until this flips.
 */
function emptyAttention() {
  return {
    known: false,
    limit: 0,
    remaining: 0,
    spent: 0,
    muted: false,
    blockedBy: null,
    pending: 0,
    banked: false,
    digestHour: 18,
    digestDue: false,
  };
}

/** The approval queue as the backend last read it. */
let queue = { count: 0, items: [] };

const linkSubs = new Set();
const queueSubs = new Set();
const eventSubs = new Set();

function fanout(subs, value) {
  for (const fn of subs) {
    try {
      fn(value);
    } catch (error) {
      console.error("[jarvis] link subscriber threw:", error);
    }
  }
}

/** Rust sends snake_case over IPC; the rest of the frontend reads camelCase. */
function normaliseLink(payload) {
  if (!payload || typeof payload !== "object") return link;
  return {
    connected: Boolean(payload.connected),
    stale: payload.stale !== false,
    base: String(payload.base || ""),
    lastId: Number(payload.last_id || 0),
    power: String(payload.power || "active"),
    powerSetBy: payload.power_set_by || null,
    activity: String(payload.activity || "idle"),
    // Capped defensively on the client too, even though the backend contract
    // in AUTONOMY-PROPOSALS.md already caps it - the same "don't trust a
    // single enforcement point" reasoning `_MAX_TOOL_CONTENT_CHARS` and
    // friends already use server-side.
    activityDetail: typeof payload.activity_detail === "string"
      ? payload.activity_detail.slice(0, 500) : "",
    approvals: Number(payload.approvals || 0),
    attention: normaliseAttention(payload.attention),
    error: payload.error || null,
  };
}

/** Rust's `Attention`, in the frontend's spelling. */
function normaliseAttention(raw) {
  if (!raw || typeof raw !== "object") return emptyAttention();
  return {
    known: raw.known === true,
    limit: Number(raw.limit || 0),
    remaining: Number(raw.remaining || 0),
    spent: Number(raw.spent || 0),
    muted: raw.muted === true,
    blockedBy: raw.blocked_by || null,
    pending: Number(raw.pending || 0),
    // Read, never derived. `remaining === 0 && pending > 0` is the server's
    // rule today and the server is the only thing allowed to change it.
    banked: raw.banked === true,
    digestHour: Number(raw.digest_hour ?? 18),
    digestDue: raw.digest_due === true,
  };
}

/**
 * Normalises one row of `/api/pending` into what a card needs.
 *
 * The row is whatever `jarvis_gate.pending()` selected — `id`, `action`,
 * `tier`, `detail`, `prompt`, `created` — plus the `risk` object the gate
 * derives at read time. Two details are worth the code:
 *
 * - `detail` is a JSON *string*, `json.dumps(detail)[:4000]`, so a large one
 *   arrives truncated and will not parse. Falling back to the raw text is the
 *   difference between showing something and showing nothing.
 * - `risk` is derived, never stored, and JARVIS-API §4 says not to cache it
 *   against an id. Nothing here does: it is read off each row, every time.
 */
export function normaliseApproval(row) {
  if (!row || typeof row !== "object") return null;
  const id = row.id === undefined || row.id === null ? "" : String(row.id).trim();
  if (!id) return null;

  let detail = null;
  // True when `detail` arrived as text that no longer parses AND is as long
  // as the gate's cut: the request was cut off before it reached this card,
  // so what is on screen is not the whole of what would run. Approve is then
  // refused on every surface (ARCHITECTURE §3: every command, in FULL).
  let cutOff = false;
  if (typeof row.detail === "string" && row.detail.trim()) {
    try {
      detail = JSON.parse(row.detail);
    } catch (error) {
      detail = row.detail;
      cutOff = row.detail.length >= GATE_DETAIL_LIMIT;
    }
  } else if (row.detail && typeof row.detail === "object") {
    detail = row.detail;
  }

  const risk = row.risk && typeof row.risk === "object" ? row.risk : null;
  const raised = raisedOf(row.raised);
  const notice = row.notice && typeof row.notice === "object" ? row.notice : null;
  // docs/AUTONOMY-PROPOSALS.md §3a. Zero or one entry means "behaves exactly
  // as today" - callers check `.length > 1`, never truthiness alone, so an
  // absent `options` and a one-item `options` render identically.
  const options = Array.isArray(row.options)
    ? row.options
        .map((o) => (o && typeof o === "object" ? {
          id: String(o.id ?? ""),
          label: String(o.label || "Approve"),
          summary: String(o.summary || ""),
          weight: String(o.weight || "normal"),
        } : null))
        .filter((o) => o && o.id)
    : [];

  return {
    id,
    cutOff,
    expiresAt: expiryOf(row),
    // The gate's own words for this item (jarvis_gate.notice_for): built from
    // the action name and its risk table, never from the payload.
    notice: notice
      ? {
          title: String(notice.title || ""),
          body: String(notice.body || ""),
          weight: String(notice.weight || "heavy"),
        }
      : null,
    action: String(row.action || "run an action"),
    tier: String(row.tier || ""),
    prompt: typeof row.prompt === "string" ? row.prompt : "",
    created: Number(row.created || 0),
    detail,
    options,
    risk: risk
      ? {
          reversible: String(risk.reversible || "no"),
          reach: String(risk.reach || "outbound"),
          // The only field to branch on for a gesture, and only ever as the
          // server sent it — never recomputed from the other two here.
          swipeOk: risk.swipe_ok === true,
          why: String(risk.why || ""),
          classified: risk.classified === true,
        }
      : null,
    // Why this is being asked about at all, when the tier table said
    // otherwise: outside text tried to rush the reader and the tier went up.
    // Usually null.
    //
    // Unlike `risk`, this IS stored on the row server-side, on purpose — the
    // rush latch expires after ten minutes but the reason the card exists does
    // not, and an item that loses its explanation while waiting is worse than
    // one that never had it.
    raised: raised
      ? {
          code: String(raised.code || "rushed"),
          // The chip. Already carries "(4th time today)" when the source has
          // tripped this more than once — `jarvis_content_risk.chip_from`
          // builds the ordinal, so nothing here counts anything. A raise that
          // arrived without one (a bare `true`, or an object with no `text`)
          // still gets a sentence: an empty chip reads as nothing at all.
          text: String(raised.text || "Tier raised — something Jarvis read tried to rush you"),
          // The attacker's words. Shown in quotation marks, inline, because
          // showing them is the entire point.
          quote: String(raised.quote || ""),
          // Text from the page or the document being judged, so it is never
          // shown until the user asks for it.
          context: String(raised.context || ""),
          // Named, never quoted.
          source: String(raised.source || ""),
          fromTier: String(raised.from_tier || ""),
          toTier: String(raised.to_tier || ""),
          countToday: Number(raised.count_today || 1),
        }
      : null,
  };
}

/** jarvis_gate stores `detail` as `json.dumps(detail)[:4000]`. */
const GATE_DETAIL_LIMIT = 4000;
/** Longer than this is a wrong unit, not a gate timeout (the shipped one is 180 s). */
const MAX_EXPIRES_IN_SECONDS = 24 * 3600;

/**
 * `raised`, in every shape the backend has used: an object, `true` (the
 * doorbell's boolean), or the JSON text of an object (how a database column
 * holds it). Anything truthy that is not a readable object becomes an empty
 * raise, never "not raised": the raise is what takes an item out of every
 * quick gesture, so an unreadable one must fail toward caution. This used to
 * accept an object only, so `true` quietly counted as not raised.
 */
function raisedOf(value) {
  if (value === null || value === undefined || value === false || value === 0) return null;
  if (typeof value === "string") {
    const text = value.trim();
    if (!text || /^(false|null|0)$/i.test(text)) return null;
    try {
      const parsed = JSON.parse(text);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed;
    } catch (error) {
      // Not JSON. Never shown as text: it may be the very words that tried
      // to rush the reader, and those belong in `quote`, in quotation marks.
    }
    return {};
  }
  if (Array.isArray(value)) return value.length ? {} : null;
  if (typeof value === "object") return value;
  return value ? {} : null;
}

/**
 * When the gate stops waiting for this card, in this machine's milliseconds,
 * or null when nobody said. `expires_at_ms` is stamped by stream.rs at the
 * moment of the read; `expires_in` (seconds left, approval-expiry.patch) is
 * the fallback for a row that did not come through it.
 */
function expiryOf(row) {
  const at = Number(row.expires_at_ms);
  if (row.expires_at_ms !== undefined && row.expires_at_ms !== null && Number.isFinite(at)) return at;
  const left = row.expires_in;
  if (typeof left === "number" && Number.isFinite(left) && left >= 0 && left <= MAX_EXPIRES_IN_SECONDS) {
    return Date.now() + left * 1000;
  }
  return null;
}

/**
 * How long a card has left, in words: "2:13 left", or "expired", or "" when
 * nobody said. The gate refuses the card by itself at the deadline, so this
 * is the difference between a decision and a card that silently vanishes.
 */
export function expiryWords(expiresAt, now = Date.now()) {
  if (expiresAt === null || expiresAt === undefined || !Number.isFinite(expiresAt)) return "";
  const left = Math.ceil((expiresAt - now) / 1000);
  if (left <= 0) return "Expired: Jarvis stopped waiting and refused it by itself.";
  const m = Math.floor(left / 60);
  const sec = String(left % 60).padStart(2, "0");
  return `${m}:${sec} left to decide, then Jarvis refuses it by itself.`;
}

/**
 * Whether an approval may be answered by a gesture rather than a decision.
 *
 * Two conditions, and both have to hold:
 *
 * 1. `risk.swipeOk`, exactly as the server computed it. JARVIS-API §5: branch
 *    on this field and nothing else, do not re-derive it from `reversible` and
 *    `reach`, do not add exceptions, do not cache it against an id.
 * 2. Nothing `raised` it. An item carrying `raised` is on the card *because*
 *    outside text tried to make the reader go faster, so the one response that
 *    must not be available is the fast one — whatever `swipe_ok` says.
 *
 * Exported rather than inlined so that a future swipe, a bulk selection or a
 * keyboard shortcut cannot each arrive at their own answer. There is no swipe
 * on the desktop today; this exists so the first one cannot get it wrong.
 */
export function quickActionable(approval) {
  if (!approval || !approval.risk) return false;
  if (approval.raised) return false;
  return approval.risk.swipeOk === true;
}

/**
 * Where an approval card can be answered, in the one sentence-part every
 * desktop surface uses (F3, audit 3). It used to be "the Jarvis bar" here,
 * "the Jarvis bar and the widget" there, and never the phone - where the
 * same card waits on the Home screen. voice.rs has the same words for its
 * two wake-word sentences; tests/faq.mjs holds the two together.
 */
export const APPROVE_WHERE = "in the Jarvis bar, on the widget, or on your phone's Home screen";

/** The link as last reported. */
export function currentLink() {
  return link;
}

/**
 * The one sentence every window uses to say what state the link is in.
 *
 * Four states, the phone's (HomeScreen's link line) plus the one before the
 * first answer:
 *
 * - not connected, with a reason: **Offline**, red, and the first sentence of
 *   the reason - which stream.rs now writes in plain words first.
 * - not connected, no reason yet: **Connecting…**. Before the first hello
 *   nothing has failed; the quickbar used to say "Jarvis is not answering on
 *   127.0.0.1:4719" here, naming an address that may not even be the one set.
 * - connected but stale: **Stale - reconnecting**, amber. The stream is up
 *   and `/api/pending` could not be read, so nothing can be approved; the
 *   quickbar and widget used to show no words at all for this, only two grey
 *   buttons.
 * - otherwise **Linked**.
 *
 * `canAct` is rule 4 in one boolean: false whenever the queue cannot be
 * confirmed live. `short` is for a pill or a tray-sized slot.
 */
export function linkWords(state = link) {
  const s = state || {};
  if (!s.connected) {
    if (s.error) {
      const first = String(s.error).trim().split(/(?<=[.!?])\s/)[0].replace(/[.;]$/, "");
      return {
        tone: "bad",
        short: "Offline",
        // stream.rs now starts its reasons with a plain sentence that names
        // Jarvis ("Jarvis is not running at ..."); an older or raw reason
        // gets the words around it.
        text: /^Jarvis\b/.test(first)
          ? `Offline — ${first}. Approving is blocked until it reconnects.`
          : `Offline — Jarvis is not answering: ${first}. Approving is blocked until it reconnects.`,
        canAct: false,
      };
    }
    return {
      tone: "warn",
      short: "Connecting…",
      text: "Connecting to Jarvis… Approving is blocked until it connects.",
      canAct: false,
    };
  }
  if (s.stale !== false) {
    return {
      tone: "warn",
      short: "Stale — reconnecting",
      text: "Stale — reconnecting. Nothing can be approved until it catches up.",
      canAct: false,
    };
  }
  return { tone: "ok", short: "Linked", text: "Linked", canAct: true };
}

/** The interruption budget as last reported. */
export function currentAttention() {
  return link.attention;
}

/**
 * What the reactor should show — the desktop's single copy of
 * `jarvis_arbiter.face_state`.
 *
 * JARVIS-API §5 says the server resolves this and warns that a client which
 * re-derives it "will disagree with the server the first time the two drift".
 * No route serves the resolved value, so composing it is unavoidable; what is
 * avoidable is composing it in three places. Rust has the same function for
 * the tray (`attention::face_state`) and this is the one for the windows.
 *
 * `banked` is taken from the server, never recomputed.
 */
export function faceState(state = link) {
  const activity = String((state && state.activity) || "idle");
  const banked = Boolean(state && state.attention && state.attention.banked);
  // Banked replaces a RESTING face only. Mid-sentence is foreground and keeps
  // its own state: the budget governs what Jarvis starts, not what it is in
  // the middle of.
  if (activity === "idle" && banked) return "banked";
  // `working` has no binding in the spec; the nearest bound state is
  // `thinking` — busy, and not talking. Anything the server adds later that
  // this build has never heard of falls to `idle` rather than being passed
  // through to a `resolve()` that would silently return the fallback colour.
  if (activity === "working") return "thinking";
  const BOUND = ["idle", "listening", "thinking", "speaking", "error"];
  return BOUND.includes(activity) ? activity : "idle";
}

/**
 * The fuller state a *surface* shows, as opposed to the face the arbiter
 * composes.
 *
 * `faceState()` above is `jarvis_arbiter.face_state` — activity, with `banked`
 * replacing a resting face. That is the right answer for the reactor. A window
 * or a tray icon answers a slightly bigger question, because it also has to
 * say "something is waiting for you" and "Jarvis is asleep", and the precedence
 * between those is a UI decision rather than the arbiter's.
 *
 * This is that precedence, and it is the same order `tray.rs::spec_state` uses:
 * an error outranks everything, then anything waiting on a human, then what
 * Jarvis is doing, then whether it is awake at all. Exported so the tray and
 * the windows cannot drift — before this the tray showed `approval` and
 * `standby` and the Brain had no way to render either.
 */
export function surfaceState(state = link) {
  const activity = String((state && state.activity) || "idle");
  if (activity === "error") return "error";
  if (Number((state && state.approvals) || 0) > 0) return "approval";
  const face = faceState(state);
  if (face !== "idle") return face;
  const power = String((state && state.power) || "active");
  return power === "standby" || power === "quiet" ? "standby" : "idle";
}

/**
 * Mutes or unmutes spoken interruptions until tomorrow.
 *
 * There is no "mute forever" — not here and not in the API. A mute with no end
 * is how a feature gets switched off once and never reconsidered.
 */
export async function setMuted(muted) {
  if (!IS_TAURI) throw new Error("no desktop backend to send that to");
  return TAURI.core.invoke("set_attention_muted", { muted: Boolean(muted) });
}

/**
 * The daily brief, ranked server-side by consequence.
 *
 * **Do not re-sort what comes back.** `jarvis_arbiter._rank` orders by what
 * kind of thing an item is and then by a priority its producer set — never by
 * urgency, because an item that could move itself up the list by saying it was
 * urgent would implement the attack the content-risk scanner exists to catch.
 */
export async function fetchDigest() {
  if (!IS_TAURI) throw new Error("no desktop backend to read the digest from");
  return TAURI.core.invoke("get_digest");
}

/**
 * Marks digest rows read. **This approves nothing.**
 *
 * `mark_digest_delivered` stamps a delivery time and nothing else. There is no
 * route in the API that decides an approval in bulk, and there is no control
 * anywhere in this app that offers to — each one opens its own gate card.
 *
 * An empty list means the whole brief.
 */
export async function markDigestSeen(ids = []) {
  if (!IS_TAURI) throw new Error("no desktop backend to mark the digest on");
  return TAURI.core.invoke("mark_digest_seen", {
    ids: Array.isArray(ids) ? ids.map(String) : [],
  });
}

/** The approval queue as last read, newest state first. */
export function currentQueue() {
  return queue;
}

/** Subscribes to link changes and immediately delivers the current one. */
export function onLink(fn) {
  linkSubs.add(fn);
  fn(link);
  return () => linkSubs.delete(fn);
}

/** Subscribes to queue changes and immediately delivers the current one. */
export function onQueue(fn) {
  queueSubs.add(fn);
  fn(queue);
  return () => queueSubs.delete(fn);
}

/**
 * Subscribes to the raw fanned-out bus frames — `{ kind, id, data }`.
 * For the kinds nothing here interprets: `finding`, `persona`, `model`,
 * `voice`. An event is a doorbell, so a subscriber re-reads what changed.
 */
export function onEvent(fn) {
  eventSubs.add(fn);
  return () => eventSubs.delete(fn);
}

/**
 * Answers an approval.
 *
 * Every surface calls this, and this calls the one Rust command, which is the
 * one place a decision is sent. Refuses while the stream is stale, because
 * approving against a queue that cannot be confirmed live is how something gets
 * approved twice — DESKTOP-BUILD's checklist asks for exactly this.
 *
 * `optionId`, added for docs/AUTONOMY-PROPOSALS.md §3a, names WHICH of a
 * plan's options is being approved when there is more than one - omitted for
 * every gate that has zero or one, which is every gate that exists in the
 * API today, so this stays backward compatible with the two-argument call
 * every existing caller already makes.
 */
export async function decide(id, approved, optionId = null) {
  if (!IS_TAURI) throw new Error("no desktop backend to send the decision to");
  if (link.stale) {
    throw new Error(
      "the event stream is offline, so the approval queue cannot be confirmed live"
    );
  }
  const args = { id: String(id), approved };
  if (optionId !== null && optionId !== undefined) args.option_id = String(optionId);
  return TAURI.core.invoke("decide_approval", args);
}

/**
 * Sends a note before the first decision - docs/AUTONOMY-PROPOSALS.md §3b.
 *
 * This is NOT a decision and approves nothing - `amend_approval` is a
 * distinct route from `decide_approval` on purpose, so a backend that has not
 * implemented it fails this call rather than approving or denying anything.
 *
 * Served by `backend/task-control.patch`. The server keeps the note WITH the
 * card - the card itself does not change - and hands it to the model
 * together with the owner's answer, whichever answer that is.
 */
export async function amend(id, note) {
  if (!IS_TAURI) throw new Error("no desktop backend to send the note to");
  if (link.stale) {
    throw new Error(
      "the event stream is offline, so the approval queue cannot be confirmed live"
    );
  }
  return TAURI.core.invoke("amend_approval", { id: String(id), note: String(note || "") });
}

/**
 * Pause, resume, stop, or add a note to whatever Jarvis is currently
 * doing - docs/AUTONOMY-PROPOSALS.md §3d.
 *
 * Distinct from a window's own `cancel_chat`/abort: that closes THIS
 * window's HTTP connection to a turn it started. `activity`/`activityDetail`
 * on `link` are server-wide - visible to every window regardless of which
 * one, if any, is still open on the request that started the work - so
 * stopping "whatever Jarvis is doing right now" needs its own signal to the
 * server, not a local abort that only this window can see the effect of.
 *
 * Served by `backend/task-control.patch` (see backend/README.md). A backend
 * without that patch answers 404, and the command says so rather than
 * silently doing nothing. Resume does not carry on by itself: the server
 * raises an approval card listing the steps left, and runs them only if
 * that card is approved.
 *
 * None of the four takes a task id: this project's own chat state already
 * treats "the current turn" as singular (`cancel_chat` takes none either),
 * and the design doc's own Section 1 - one action, one decision - means
 * there is never more than one thing running that a human approved to run.
 */
export async function pauseTask() {
  if (!IS_TAURI) throw new Error("no desktop backend to send that to");
  return TAURI.core.invoke("pause_task");
}

export async function resumeTask() {
  if (!IS_TAURI) throw new Error("no desktop backend to send that to");
  // The one task control that makes something GO again, so it is held to
  // rule 4 like a decision: not on a stream that cannot be confirmed live.
  // (It only raises an approval card - but that card should be answered by
  // someone looking at a live queue.) Pause, Stop and notes are not gated:
  // the moment you most want Stop is the moment the link is misbehaving.
  if (link.stale) {
    throw new Error(
      "the event stream is offline, so resuming is held until it reconnects - Stop still works"
    );
  }
  return TAURI.core.invoke("resume_task");
}

export async function stopTask() {
  if (!IS_TAURI) throw new Error("no desktop backend to send that to");
  return TAURI.core.invoke("stop_task");
}

export async function injectTaskNote(note) {
  if (!IS_TAURI) throw new Error("no desktop backend to send that to");
  return TAURI.core.invoke("inject_task_note", { note: String(note || "") });
}

/** Asks the backend to reconnect its stream now rather than serve out a backoff. */
export function reconnect() {
  if (!IS_TAURI) return;
  TAURI.core.invoke("refresh_link").catch(() => {
    /* the stream reports itself soon enough */
  });
}

/**
 * Every theme `theme.css` defines, in the order the picker lists them.
 *
 * The phone's three (`Themes.kt`'s `ALL`), under the phone's names - the ids
 * are the desktop's old ones so a saved choice keeps working. Ember was a
 * fourth and is gone, as it went on the phone; see `normaliseTheme`.
 */
export const THEMES = ["deep-space", "paper", "high-contrast"];

/**
 * What the pickers say about each theme. Names and one-line descriptions are
 * the phone's own (Themes.kt `label` / `blurb`), so the two apps read the
 * same. `dark` decides which way the accent walks and which themes can be
 * "the theme for dark mode".
 */
export const THEME_INFO = {
  "deep-space": {
    label: "Reactor",
    blurb: "The default. Cool near-black, built around the reactor's own light.",
    dark: true,
  },
  paper: {
    label: "Daylight",
    blurb: "Light chrome for reading outdoors. The reactor keeps its dark well.",
    dark: false,
  },
  "high-contrast": {
    label: "High Contrast",
    blurb: "Maximum legibility. Flat surfaces, strong borders, two text weights.",
    dark: true,
  },
};

/**
 * A stored theme id as this build reads it. Ember, removed to match the
 * phone, and anything else this build does not ship is Reactor - the phone's
 * `Themes.byId` does the same. commands.rs `normalise_theme` is the Rust twin.
 */
export function normaliseTheme(name) {
  return THEMES.includes(name) ? name : THEMES[0];
}

/**
 * Applies a theme to this window and remembers it for the next paint.
 *
 * Called on load, and again whenever another window changes it. `set_theme`
 * has always fanned a `theme-changed` event out to every window; until now
 * nothing listened, so choosing a theme in the Brain left the spotlight, the
 * widget and settings on the palette they shipped with. For someone who picked
 * high-contrast because they need it, the surface they use most ignored them.
 */
export function applyTheme(name) {
  const theme = normaliseTheme(name);
  document.documentElement.setAttribute("data-theme", theme);
  try {
    localStorage.setItem("jarvis.theme", theme);
  } catch (error) {
    /* the store is the source of truth; this is only the anti-flash cache */
  }
  // The accent is worked out against this theme's own surfaces, so it has to
  // be worked out again for the new one.
  paintAppearance();
  return theme;
}

/**
 * Subscribes this window to the theme, and reads the current one once.
 *
 * Safe to call from any surface. The inline bootstrap in each page has already
 * painted from localStorage, so this only corrects a disagreement. Also
 * subscribes the window to the owner's state colours - see followAppearance.
 */
export function followTheme(onChange) {
  if (!IS_TAURI) return;
  TAURI.event.listen("theme-changed", (event) => {
    const theme = applyTheme(event.payload);
    if (onChange) onChange(theme);
  });
  TAURI.core
    .invoke("get_theme")
    .then((stored) => {
      const theme = applyTheme(stored);
      if (onChange) onChange(theme);
    })
    .catch((error) => console.error("[jarvis] could not read the theme:", error));
  followAppearance();
}

/* ==========================================================================
   The owner's state colours in the chrome
   --------------------------------------------------------------------------
   The phone derives its accent from the idle state's bound colour
   (Chrome.kt `accentFor`), so re-rolling idle to violet turns the caret, the
   focus ring and the selected tab violet. Chrome.kt says the desktop does the
   same; until now it did not - `--accent` and every `--state-*` were fixed per
   theme, and only the tray icon followed the bindings. This is the port.

   Only states the owner has bound are applied (appearance_colours returns
   nothing for the rest), so an untouched install keeps the colours theme.css
   measured. `--state-standby` is never overridden: theme.css declares it as a
   deliberate divergence from the spec, for contrast.
   ========================================================================== */

/** WCAG relative luminance of `[r, g, b]` (0-255). */
function luminance([r, g, b]) {
  const lin = (c) => {
    const v = c / 255;
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

/** WCAG contrast ratio, 1..21. */
export function contrast(a, b) {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/** `#rrggbb` to `[r, g, b]`, or null. */
export function hexRgb(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || "").trim());
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** `rgb(...)`/`rgba(...)`/`#hex` to `[r, g, b, a]`, or null. */
function parseColour(text) {
  const hex = hexRgb(text);
  if (hex) return [...hex, 1];
  const m = /rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:[\s,/]+([\d.]+%?))?\s*\)/i.exec(
    String(text || "")
  );
  if (!m) return null;
  let a = m[4] === undefined ? 1 : parseFloat(m[4]);
  if (String(m[4] || "").endsWith("%")) a /= 100;
  return [Number(m[1]), Number(m[2]), Number(m[3]), a];
}

/** A translucent surface as it lands over a solid backdrop. */
function over([r, g, b, a], [br, bg, bb]) {
  return [r * a + br * (1 - a), g * a + bg * (1 - a), b * a + bb * (1 - a)];
}

/**
 * Walks a colour along its own palette family until it is legible.
 *
 * `grounds` are the surface as it composites over black AND over white,
 * because these windows are transparent (theme.css's contrast rule): a colour
 * has to clear `floor` against both. Dark themes walk toward the pale end,
 * light ones toward the deep end, exactly as Chrome.kt `accentFor` does, and
 * the walk never leaves the family - the hue is what the owner chose. A
 * colour outside the palette is nudged toward white or black instead.
 * Pure, so tests/theme-follow.mjs can check it without a browser.
 */
export function legibleColour(entry, grounds, { dark = true, floor = 4.5 } = {}) {
  const worst = (rgb) => Math.min(...grounds.map((g) => contrast(rgb, g)));
  const ramp = Array.isArray(entry && entry.ramp) ? entry.ramp.map(hexRgb).filter(Boolean) : [];
  const own = hexRgb(entry && entry.hex);
  if (ramp.length && Number.isInteger(entry.step)) {
    const start = Math.max(0, Math.min(ramp.length - 1, entry.step));
    const up = [];
    const down = [];
    for (let i = start; i < ramp.length; i += 1) up.push(i);
    for (let i = start - 1; i >= 0; i -= 1) down.push(i);
    const order = dark ? [...up, ...down] : [start, ...down, ...up.slice(1)];
    for (const i of order) {
      if (worst(ramp[i]) >= floor) return { rgb: ramp[i], index: i, ramp };
    }
    let best = start;
    for (let i = 0; i < ramp.length; i += 1) if (worst(ramp[i]) > worst(ramp[best])) best = i;
    return { rgb: ramp[best], index: best, ramp };
  }
  if (!own) return null;
  const toward = dark ? [255, 255, 255] : [0, 0, 0];
  let out = own;
  for (let k = 0; k <= 1.0001; k += 0.05) {
    out = own.map((c, i) => Math.round(c + (toward[i] - c) * k));
    if (worst(out) >= floor) break;
  }
  return { rgb: out, index: null, ramp: [] };
}

const css = ([r, g, b]) => `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`;
const cssA = ([r, g, b], a) => `rgba(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)}, ${a})`;

/**
 * The custom properties the owner's colours set on this window, given the
 * theme's surfaces. Pure: `colours` is appearance_colours' answer.
 */
export function appearanceProperties(colours, { grounds, dark = true, strict = false, textOnAccent = [] }) {
  const props = {};
  if (!colours || typeof colours !== "object") return props;
  for (const [state, entry] of Object.entries(colours)) {
    // The one declared divergence in theme.css - see its note.
    if (state === "standby") continue;
    // A status dot is non-text: 3:1, the same floor theme.css holds them to.
    const dot = legibleColour(entry, grounds, { dark, floor: 3 });
    if (dot) props[`--state-${state}`] = css(dot.rgb);
  }
  const idle = colours.idle;
  if (idle) {
    // High Contrast holds every text pair to 7:1, the others to 4.5:1.
    const accent = legibleColour(idle, grounds, { dark, floor: strict ? 7 : 4.5 });
    if (accent) {
      const a = accent.rgb;
      // One step further from the surface than the accent itself, for text.
      let bright = a;
      if (accent.ramp.length && accent.index !== null) {
        const next = dark ? accent.index + 1 : accent.index - 1;
        if (next >= 0 && next < accent.ramp.length) bright = accent.ramp[next];
      }
      props["--accent"] = css(a);
      props["--accent-rgb"] = `${Math.round(a[0])} ${Math.round(a[1])} ${Math.round(a[2])}`;
      props["--accent-bright"] = css(bright);
      props["--accent-text"] = css(bright);
      props["--accent-dim"] = cssA(a, 0.32);
      props["--accent-faint"] = cssA(a, dark ? 0.12 : 0.1);
      props["--border-accent"] = cssA(a, 0.34);
      props["--edge-active"] = cssA(a, 0.65);
      props["--focus-ring"] = css(bright);
      props["--glow-accent"] = `0 0 0 1px ${cssA(a, 0.32)}, 0 0 22px ${cssA(a, 0.18)}`;
      // Whichever reads best ON the accent: the theme's own ink, or plain
      // near-black / white.
      const inks = [...textOnAccent, [4, 7, 12], [255, 255, 255]];
      let ink = inks[0];
      for (const c of inks) if (contrast(c, a) > contrast(ink, a)) ink = c;
      props["--text-on-accent"] = css(ink);
    }
  }
  return props;
}

let appearanceColours = null;
let appearanceProps = [];
let appearanceFollowed = false;

/** Re-applies the last colours read, against the theme now showing. */
function paintAppearance() {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  // Back to the theme's own values first, so what theme.css says for THIS
  // theme is what gets measured.
  for (const name of appearanceProps) root.style.removeProperty(name);
  appearanceProps = [];
  if (!appearanceColours || !Object.keys(appearanceColours).length) return;
  const style = getComputedStyle(root);
  const surface = parseColour(style.getPropertyValue("--surface-1")) || [10, 17, 25, 1];
  const theme = root.getAttribute("data-theme") || THEMES[0];
  const info = THEME_INFO[theme] || THEME_INFO[THEMES[0]];
  const ink = parseColour(style.getPropertyValue("--text-on-accent"));
  const props = appearanceProperties(appearanceColours, {
    grounds: [over(surface, [0, 0, 0]), over(surface, [255, 255, 255])],
    dark: info.dark,
    strict: theme === "high-contrast",
    textOnAccent: ink ? [ink.slice(0, 3)] : [],
  });
  for (const [name, value] of Object.entries(props)) {
    root.style.setProperty(name, value);
    appearanceProps.push(name);
  }
}

function readAppearanceColours() {
  if (!IS_TAURI) return;
  TAURI.core
    .invoke("appearance_colours")
    .then((colours) => {
      appearanceColours = colours && typeof colours === "object" ? colours : null;
      paintAppearance();
    })
    .catch(() => {
      /* an older shell without the command: keep the theme's own colours */
    });
}

/**
 * Makes this window's accent and state dots follow the owner's state colours,
 * and keeps them following. Called by followTheme, so every window that
 * follows the theme follows these too. Reads from memory
 * (`appearance_colours`), never the network, so it is safe to re-read on every
 * `appearance-changed`.
 */
export function followAppearance() {
  if (!IS_TAURI || appearanceFollowed) return;
  appearanceFollowed = true;
  TAURI.event.listen("appearance-changed", () => readAppearanceColours());
  readAppearanceColours();
}

/* ==========================================================================
   Text size
   ========================================================================== */

/** The steps Ctrl+= and Ctrl+- walk, and the one Ctrl+0 returns to. */
export const ZOOM_STEPS = [0.8, 0.9, 1, 1.15, 1.3, 1.5, 1.75, 2, 2.5];
const ZOOM_KEY = "jarvis.zoom";

function storedZoom() {
  try {
    const value = Number(localStorage.getItem(ZOOM_KEY));
    return ZOOM_STEPS.includes(value) ? value : 1;
  } catch (error) {
    return 1;
  }
}

/**
 * Sets this window's zoom and remembers it.
 *
 * Every size in these stylesheets is in `px`, which is a decision that only
 * works if the reader has a way to scale the whole surface — and a Tauri
 * WebView2 window ships with none: there is no browser chrome, so Ctrl+= and
 * Ctrl+- reach nothing. Someone who needs 150% text had no control anywhere in
 * the app.
 *
 * This is that control. It scales layout with the text, which is the behaviour
 * a fixed-`px` design needs — a font-size-only scale would put 24px text in a
 * 22px row. The windows measure their own content and ask Rust to resize, so
 * the frames follow.
 */
export function setZoom(factor) {
  const zoom = ZOOM_STEPS.includes(factor) ? factor : 1;
  try {
    localStorage.setItem(ZOOM_KEY, String(zoom));
  } catch (error) {
    /* the zoom still applies for this session */
  }
  if (IS_TAURI && TAURI.webview) {
    try {
      TAURI.webview.getCurrentWebview().setZoom(zoom);
    } catch (error) {
      console.error("[jarvis] could not set the zoom:", error);
    }
  }
  return zoom;
}

/** The zoom this window is at. */
export function currentZoom() {
  return storedZoom();
}

/**
 * Restores the remembered zoom and binds Ctrl+= / Ctrl+- / Ctrl+0.
 *
 * `onChange` runs after each step so a surface that measures itself can
 * re-measure — the quickbar and the widget both size their native window to
 * their content, and neither notices a zoom on its own.
 */
export function followZoom(onChange) {
  const apply = (zoom) => {
    setZoom(zoom);
    // The zoom lands asynchronously in the webview, so a measurement taken now
    // is of the old layout. Two frames is enough for WebView2 to have relaid
    // out; measuring early is how the window ends up one step behind.
    if (onChange) requestAnimationFrame(() => requestAnimationFrame(() => onChange(zoom)));
  };
  apply(storedZoom());

  // Settings' Text size buttons write the same key from another window. The
  // `storage` event fires in every OTHER same-origin document when that
  // happens, which is exactly the set of windows that need to follow - the
  // one that wrote it has already applied it. (A browser-standard event; not
  // yet seen on the owner's machine, so the key is also re-read on load.)
  window.addEventListener("storage", (event) => {
    if (event.key !== ZOOM_KEY) return;
    apply(storedZoom());
  });

  window.addEventListener("keydown", (event) => {
    if (!event.ctrlKey || event.altKey || event.metaKey) return;
    // `=` and `+` are the same key; `NumpadAdd` is the other one. Matching on
    // `key` alone misses the numeric keypad, which is where a lot of people
    // who use zoom actually press it.
    const inKey = event.key;
    const code = event.code;
    let next = null;
    const at = ZOOM_STEPS.indexOf(storedZoom());
    if (inKey === "=" || inKey === "+" || code === "NumpadAdd") {
      next = ZOOM_STEPS[Math.min(ZOOM_STEPS.length - 1, at + 1)];
    } else if (inKey === "-" || inKey === "_" || code === "NumpadSubtract") {
      next = ZOOM_STEPS[Math.max(0, at - 1)];
    } else if (inKey === "0" || code === "Numpad0") {
      next = 1;
    }
    if (next === null) return;
    event.preventDefault();
    apply(next);
    announce(`Text size ${Math.round(next * 100)} percent.`);
  });
}

/**
 * The one live region a window speaks through.
 *
 * Two bugs made every announcement in this app unreliable, and both are
 * structural rather than a missing attribute.
 *
 * First: four regions were WRITTEN TO WHILE HIDDEN and then unhidden — the
 * approval gate in the quickbar and the widget, the Brain's toast, the Brain's
 * inspector. `[hidden] { display: none !important }` removes an element from
 * the accessibility tree, and a live region has to be present and observed
 * BEFORE its contents change for the change to be reported. Writing while
 * removed and then inserting the whole populated subtree is the canonical way
 * to get silence.
 *
 * Second: the streaming answer carried `aria-live="polite"` while `paint()`
 * reassigned its whole `innerHTML`. `aria-relevant` defaults to `additions
 * text`, so every repaint re-added the entire answer so far and queued it. A
 * long reply left a screen reader still speaking paragraph one after the
 * visual answer had finished, with no way to interrupt it into a coherent
 * state.
 *
 * So: one element, created at load, never hidden, off-screen. Everything that
 * needs to be spoken goes through `announce()`. The visual surfaces become
 * ordinary markup with no live semantics at all.
 */
let announcer = null;

/**
 * Builds the two regions, EAGERLY.
 *
 * Lazily was the same bug one level up: the first `announce()` would create
 * the element and write to it in the same tick, so the region was not present
 * and observed before its contents changed — which is the exact condition that
 * makes a live region silent. It has to exist before anything needs it.
 */
function buildAnnouncer() {
  if (announcer || !document.body) return;
  announcer = { polite: null, assertive: null };
  for (const level of ["polite", "assertive"]) {
    const node = document.createElement("div");
    node.className = "sr-only";
    node.setAttribute("aria-live", level);
    // `additions text` is the default, and it is what re-announced the whole
    // streaming answer on every repaint. Only additions are wanted here.
    node.setAttribute("aria-relevant", "additions");
    node.setAttribute("aria-atomic", "true");
    document.body.append(node);
    announcer[level] = node;
  }
}

if (typeof document !== "undefined") {
  if (document.body) buildAnnouncer();
  else document.addEventListener("DOMContentLoaded", buildAnnouncer, { once: true });
}

function announcerFor(politeness) {
  buildAnnouncer();
  if (!announcer) return null;
  return announcer[politeness === "assertive" ? "assertive" : "polite"];
}

/**
 * Says something once.
 *
 * `assertive` is for a decision that has stopped work — an approval gate — and
 * for nothing else. Everything else is polite, because an assertive region
 * interrupts whatever the user was reading.
 */
export function announce(message, politeness = "polite") {
  const text = String(message || "").trim();
  if (!text) return;
  const node = announcerFor(politeness);
  if (!node) return;
  // Re-setting identical text is not a mutation and would not be spoken, so a
  // repeated message needs the region cleared first.
  node.textContent = "";
  requestAnimationFrame(() => {
    node.textContent = text;
  });
}

let started = false;

/**
 * Subscribes to the backend and reads the current state once.
 *
 * The read is what makes a window that opens mid-conversation correct: the
 * stream only speaks when something changes, so a surface that only listened
 * would sit on its defaults until the next event — which for a quiet system is
 * a long time.
 */
export function start() {
  if (started || !IS_TAURI) {
    if (!IS_TAURI) {
      console.info("[jarvis] no desktop backend; the link stays offline");
    }
    return;
  }
  started = true;

  TAURI.event.listen(EV_LINK, (event) => {
    link = normaliseLink(event.payload);
    fanout(linkSubs, link);
  });

  TAURI.event.listen(EV_APPROVALS, (event) => {
    const payload = event.payload || {};
    const items = Array.isArray(payload.items) ? payload.items : [];
    queue = {
      count: Number(payload.count || items.length),
      items: items.map(normaliseApproval).filter(Boolean),
    };
    fanout(queueSubs, queue);
  });

  TAURI.event.listen(EV_EVENT, (event) => fanout(eventSubs, event.payload));

  // `hello.stale` said we fell off the back of the server's 512-event ring.
  // Nothing local is trustworthy; the backend has already re-read the queue, so
  // this only has to tell the surfaces to repaint from it rather than patch up
  // what they were showing.
  TAURI.event.listen(EV_RESYNC, () => {
    fanout(linkSubs, link);
    fanout(queueSubs, queue);
  });

  TAURI.core
    .invoke("get_link_state")
    .then((payload) => {
      link = normaliseLink(payload);
      fanout(linkSubs, link);
    })
    .catch((error) => console.error("[jarvis] get_link_state failed:", error));

  TAURI.core
    .invoke("get_pending_approvals")
    .then((payload) => {
      const items = Array.isArray(payload && payload.items) ? payload.items : [];
      queue = {
        count: Number((payload && payload.count) || items.length),
        items: items.map(normaliseApproval).filter(Boolean),
      };
      fanout(queueSubs, queue);
    })
    .catch((error) =>
      console.error("[jarvis] get_pending_approvals failed:", error)
    );
}

/**
 * One line describing the risk of getting an approval wrong, for the card.
 *
 * JARVIS-API §4: "`why` exists so the UI can explain rather than merely
 * enforce. A card that says 'no undo: there is no unsend' teaches the rule; one
 * that silently refuses a swipe does not."
 */
export function riskLine(risk) {
  if (!risk) return "This action is not classified, so treat it as irreversible.";
  const undo =
    risk.reversible === "yes"
      ? "Reversible"
      : risk.reversible === "hard"
        ? "Hard to undo"
        : "No undo";
  const reach = risk.reach === "local" ? "stays on this machine" : "leaves this machine";
  return risk.why ? `${undo} · ${reach} — ${risk.why}` : `${undo} · ${reach}`;
}
