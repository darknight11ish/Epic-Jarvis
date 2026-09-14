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
  approvals: 0,
  error: null,
};

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
    approvals: Number(payload.approvals || 0),
    error: payload.error || null,
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
  const id = row.id === undefined || row.id === null ? "" : String(row.id);
  if (!id) return null;

  let detail = null;
  if (typeof row.detail === "string" && row.detail.trim()) {
    try {
      detail = JSON.parse(row.detail);
    } catch (error) {
      detail = row.detail;
    }
  } else if (row.detail && typeof row.detail === "object") {
    detail = row.detail;
  }

  const risk = row.risk && typeof row.risk === "object" ? row.risk : null;

  return {
    id,
    action: String(row.action || "run an action"),
    tier: String(row.tier || ""),
    prompt: typeof row.prompt === "string" ? row.prompt : "",
    created: Number(row.created || 0),
    detail,
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
  };
}

/** The link as last reported. */
export function currentLink() {
  return link;
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
 */
export async function decide(id, approved) {
  if (!IS_TAURI) throw new Error("no desktop backend to send the decision to");
  if (link.stale) {
    throw new Error(
      "the event stream is offline, so the approval queue cannot be confirmed live"
    );
  }
  return TAURI.core.invoke("decide_approval", { id: String(id), approved });
}

/** Asks the backend to reconnect its stream now rather than serve out a backoff. */
export function reconnect() {
  if (!IS_TAURI) return;
  TAURI.core.invoke("refresh_link").catch(() => {
    /* the stream reports itself soon enough */
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
