/**
 * The Brain — everything Jarvis knows and everything it can do.
 *
 * Six views over one Rust command. `brain_read` fans out across a fixed
 * allowlist of read-only endpoints in parallel and returns them keyed by
 * section; this window renders them. Nothing here opens a stream, polls an
 * endpoint or holds its own idea of the link state — it subscribes to the one
 * connection Rust owns, like every other surface.
 *
 * ## The rule about server text
 *
 * Almost everything rendered here was written by somebody else: repository
 * descriptions from GitHub, skill names from disk, job labels, model
 * identifiers, ledger hashes. All of it reaches the DOM through `textContent`
 * or through the `el()` helper, which uses `textContent`. There is no
 * `innerHTML` in this file that touches server data, and the markdown renderer
 * lives in the quickbar where the content is the model's own answer.
 *
 * @module brain
 */

import {
  announce,
  currentLink,
  followZoom,
  surfaceState,
  onEvent,
  onLink,
  start as startLink,
} from "./jarvis-link.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);

/** Every view, and what the topbar says about it. */
const VIEWS = {
  galaxy: { title: "Galaxy", sub: "what Jarvis knows" },
  live: { title: "Live", sub: "what Jarvis is doing" },
  faculties: { title: "Faculties", sub: "models, compute, skills, memory" },
  work: { title: "Work", sub: "jobs in flight and what can be put back" },
  trust: { title: "Trust", sub: "the audit chain and what outside text tried" },
  watch: { title: "Watch", sub: "the GitHub watchlist" },
};

/** Which sections each view needs, so a switch reads only what it will show. */
const VIEW_SECTIONS = {
  galaxy: ["graph"],
  live: ["attention", "status"],
  faculties: ["models", "compute", "skills", "memory", "memory_pending"],
  work: ["jobs", "undo"],
  trust: ["content_risk", "ledger"],
  watch: ["watch", "watch_report"],
};

const THEMES = ["deep-space", "ember", "paper", "high-contrast"];

const $ = (id) => document.getElementById(id);

const dom = {
  root: document.documentElement,
  title: $("view-title"),
  sub: $("view-sub"),
  banner: $("banner"),
  linkPill: $("link-pill"),
  linkText: $("link-text"),
  refresh: $("refresh"),
  toast: $("toast"),
  themePicker: $("theme-picker"),
  rail: $("rail-nav"),

  canvas: $("graph-canvas"),
  graphEmpty: $("graph-empty"),
  graphEmptyText: $("graph-empty-text"),
  graphStat: $("graph-stat"),
  graphSearch: $("graph-search"),
  graphRefit: $("graph-refit"),
  legend: $("legend"),
  inspector: $("inspector"),
  inspectorClose: $("inspector-close"),
  nodeKind: $("node-kind"),
  nodeLabel: $("node-label"),
  nodeFacts: $("node-facts"),
  nodeLinks: $("node-links"),

  nowFace: $("now-face"),
  nowActivity: $("now-activity"),
  nowPower: $("now-power"),
  nowKv: $("now-kv"),
  budget: $("budget"),
  budgetNote: $("budget-note"),
  trace: $("trace"),
  traceClear: $("trace-clear"),

  models: $("models"),
  compute: $("compute"),
  skills: $("skills"),
  memory: $("memory"),
  jobs: $("jobs"),
  undo: $("undo"),
  contentRisk: $("content-risk"),
  ledger: $("ledger"),
  watch: $("watch"),
  watchReport: $("watch-report"),

  watchForm: $("watch-form"),
  watchAddOpen: $("watch-add-open"),
  watchCancel: $("watch-cancel"),
  watchSeen: $("watch-seen"),
  countLive: $("count-live"),
  countWork: $("count-work"),
  countTrust: $("count-trust"),
  countWatch: $("count-watch"),
};

const state = {
  view: "galaxy",
  /** Section name → last body read. */
  data: {},
  /** True while a read is in flight, so a repaint cannot stack them. */
  loading: false,
  graph: null,
  trace: [],
};

/* ==========================================================================
   Plumbing
   ========================================================================== */

async function invoke(command, args = {}) {
  if (!IS_TAURI) {
    console.info(`[brain] invoke("${command}") skipped — no desktop backend`);
    return null;
  }
  return TAURI.core.invoke(command, args);
}

let toastTimer = null;
function toast(message, tone = "") {
  announce(String(message), tone === "bad" ? "assertive" : "polite");
  dom.toast.textContent = String(message);
  dom.toast.dataset.tone = tone;
  dom.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    dom.toast.hidden = true;
  }, tone === "bad" ? 9000 : 4200);
}

/** Builds an element. Text always goes in as text — see the module note. */
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function rows(container, items, render, emptyText) {
  container.replaceChildren();
  if (!items || !items.length) {
    container.append(el("p", "empty", emptyText));
    return;
  }
  const list = el("div", "rows");
  for (const item of items) list.append(render(item));
  container.append(list);
}

/** A row: a tag, a title with meta beneath it, and optional actions. */
function row({ tag, state: tagState, title, meta, actions }) {
  const item = el("div", "row-item");
  const t = el("span", "row-tag", tag || "");
  if (tagState) t.dataset.state = tagState;
  item.append(t);

  const main = el("div", "row-main");
  main.append(el("span", "row-title", title));
  for (const line of [].concat(meta || []).filter(Boolean)) {
    main.append(el("span", "row-meta", line));
  }
  item.append(main);

  const box = el("div", "row-actions");
  for (const action of actions || []) box.append(action);
  item.append(box);
  return item;
}

function button(label, onClick, { danger = false, title = "" } = {}) {
  const b = el("button", `btn small${danger ? " danger" : ""}`, label);
  b.type = "button";
  if (title) b.title = title;
  b.addEventListener("click", async () => {
    b.disabled = true;
    try {
      await onClick();
    } finally {
      b.disabled = false;
    }
  });
  return b;
}

/** Model files are gigabytes; "4863.7 MB" is a number nobody reads as 4.7 GB. */
const bytes = (n) => {
  const v = Number(n) || 0;
  if (v < 1024) return `${v} B`;
  if (v < 1024 ** 2) return `${(v / 1024).toFixed(1)} kB`;
  if (v < 1024 ** 3) return `${(v / 1024 ** 2).toFixed(1)} MB`;
  return `${(v / 1024 ** 3).toFixed(1)} GB`;
};

function ago(epochSeconds) {
  const t = Number(epochSeconds);
  if (!Number.isFinite(t) || t <= 0) return "";
  const s = Math.max(0, Math.round(Date.now() / 1000 - t));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

/** `{available:false}` means the module is absent, which is not an error. */
function unavailable(section) {
  const body = state.data[section];
  if (!body) return "not read yet";
  if (body.available === false) return body.error || "not available on this backend";
  return null;
}

/* ==========================================================================
   Reading
   ========================================================================== */

async function load(sections, { quiet = false } = {}) {
  if (!IS_TAURI) {
    dom.banner.hidden = false;
    dom.banner.textContent =
      "No desktop backend — this is a browser preview, so nothing is being read.";
    return;
  }
  if (state.loading) return;
  state.loading = true;
  dom.refresh.disabled = true;
  try {
    const body = await invoke("brain_read", { sections });
    Object.assign(state.data, body || {});
    // One banner for the window rather than an invented empty state per pane:
    // a pane that failed and a pane that is genuinely empty look identical
    // otherwise, and only one of them is worth the user's attention.
    const failed = sections.filter((s) => unavailable(s));
    dom.banner.hidden = failed.length === 0;
    if (failed.length) {
      dom.banner.textContent = failed
        .map((s) => `${s.replace(/_/g, " ")}: ${unavailable(s)}`)
        .join(" · ");
    }
  } catch (error) {
    dom.banner.hidden = false;
    dom.banner.textContent = String((error && error.message) || error);
    if (!quiet) toast(String((error && error.message) || error), "bad");
  } finally {
    state.loading = false;
    dom.refresh.disabled = false;
  }
}

async function showView(name, { reload = true } = {}) {
  if (!VIEWS[name]) return;
  state.view = name;
  dom.root.dataset.view = name;
  dom.title.textContent = VIEWS[name].title;
  dom.sub.textContent = VIEWS[name].sub;

  for (const key of Object.keys(VIEWS)) {
    const tab = $(`tab-${key}`);
    const view = $(`view-${key}`);
    if (tab) {
      tab.setAttribute("aria-selected", String(key === name));
      // Roving tabindex: exactly one tab is in the document's tab order, and
      // it is the selected one. Without this the six buttons are six stops.
      tab.tabIndex = key === name ? 0 : -1;
    }
    if (view) view.hidden = key !== name;
  }

  if (reload) await load(VIEW_SECTIONS[name]);
  render(name);
  if (name === "galaxy") fitCanvas();
}

/** Paints whichever view is showing from `state.data`. */
function render(name) {
  switch (name) {
    case "galaxy":
      renderGraph();
      break;
    case "live":
      renderLive();
      break;
    case "faculties":
      renderModels();
      renderCompute();
      renderSkills();
      renderMemory();
      break;
    case "work":
      renderJobs();
      renderUndo();
      break;
    case "trust":
      renderContentRisk();
      renderLedger();
      break;
    case "watch":
      renderWatch();
      renderWatchReport();
      break;
  }
  renderCounts();
}

function renderCounts() {
  const set = (node, n) => {
    node.hidden = !n;
    node.textContent = String(n || "");
  };
  const jobs = (state.data.jobs && state.data.jobs.jobs) || [];
  set(
    dom.countWork,
    jobs.filter((j) => j.state === "running" || j.state === "queued").length
  );
  const risk = state.data.content_risk;
  set(dom.countTrust, risk && risk.rush ? 1 : 0);
  const watch = state.data.watch;
  set(dom.countWatch, (watch && watch.waiting_for_you) || 0);
  const attention = currentLink().attention;
  set(dom.countLive, attention.known ? attention.pending : 0);
}

/* ==========================================================================
   Faculties
   ========================================================================== */

function renderModels() {
  const body = state.data.models || {};
  const why = unavailable("models");
  if (why) return rows(dom.models, [], null, why);

  const current = body.current || body.active || "";
  const previous = body.previous || "";
  const installed = Array.isArray(body.installed) ? body.installed : [];

  const items = installed.length
    ? installed.map((m) => (typeof m === "string" ? { ref: m } : m))
    : current
      ? [{ ref: current }]
      : [];

  rows(
    dom.models,
    items,
    (m) => {
      const ref = String(m.ref || m.name || m.model || "");
      const isCurrent = ref && ref === current;
      const actions = [];
      if (ref && !isCurrent) {
        actions.push(
          button("Use", () => modelAction("switch", ref), {
            title: "Switch the active model. Rollback is one tap and never waits.",
          })
        );
      }
      return row({
        tag: isCurrent ? "active" : "installed",
        state: isCurrent ? "present" : "",
        title: ref || "(unnamed)",
        meta: [
          m.size ? bytes(m.size) : "",
          m.family || "",
          ref && ref === previous ? "the previous model" : "",
        ],
        actions,
      });
    },
    "No models reported."
  );

  if (previous && previous !== current) {
    const back = el("div", "row-actions");
    back.style.paddingTop = "10px";
    back.append(
      button(`Roll back to ${previous}`, () => modelAction("rollback"), {
        title: "Tier auto on the server — rollback never waits for approval.",
      })
    );
    dom.models.append(back);
  }
}

async function modelAction(action, reference) {
  try {
    const out = await invoke("brain_model", { action, reference: reference || null });
    // Install answers 202 and reports progress as `model` events — "started",
    // not "done", and saying otherwise would be a lie the user acts on.
    toast(
      action === "install"
        ? "Download started — progress arrives on the event stream."
        : `Model ${action === "rollback" ? "rolled back" : "switched"}.`,
      "ok"
    );
    if (out) await load(["models"], { quiet: true });
    render("faculties");
  } catch (error) {
    toast(String((error && error.message) || error), "bad");
  }
}

function renderCompute() {
  const body = state.data.compute || {};
  const why = unavailable("compute");
  dom.compute.replaceChildren();
  if (why) return dom.compute.append(el("p", "empty", why));

  const dl = el("dl", "kv");
  const add = (k, v) => {
    if (v === undefined || v === null || v === "") return;
    dl.append(el("dt", "", k), el("dd", "", v));
  };
  add("Plan", body.plan || body.mode || body.strategy);
  add("GPU", body.gpu || body.device);
  add(
    "VRAM",
    body.vram_total_mb
      ? `${((body.vram_used_mb || 0) / 1024).toFixed(1)} / ${(body.vram_total_mb / 1024).toFixed(1)} GB`
      : body.vram
  );
  add("Layers on GPU", body.gpu_layers ?? body.n_gpu_layers);
  add("Context", body.context ?? body.n_ctx);
  add("Note", body.note || body.reason);
  if (!dl.childElementCount) {
    return dom.compute.append(el("p", "empty", "No compute plan reported."));
  }
  dom.compute.append(dl);
}

function renderSkills() {
  const body = state.data.skills || {};
  const why = unavailable("skills");
  if (why) return rows(dom.skills, [], null, why);
  const list = Array.isArray(body.skills) ? body.skills : Array.isArray(body) ? body : [];

  rows(
    dom.skills,
    list,
    (s) => {
      const name = String(s.name || s.id || "(unnamed)");
      const verdict = String(s.verdict || s.scan || (s.ok === false ? "flagged" : "clean"));
      return row({
        tag: verdict,
        state: /clean|ok|pass/i.test(verdict) ? "ok" : "warn",
        title: name,
        meta: [s.description || s.summary || "", s.path || ""],
        actions: [
          button(
            "Remove",
            async () => {
              // Removal is not undoable from here: there is deliberately no
              // route that installs a skill, because installing runs the
              // scanner and the gate. So it asks, in those words.
              if (
                !confirm(
                  `Remove the skill "${name}"?\n\n` +
                    "This cannot be undone from the desktop. There is no route " +
                    "that installs a skill — installing runs the scanner and " +
                    "the gate, and a client that bypassed both would be the " +
                    "whole attack. Putting it back means putting the file back " +
                    "on the machine."
                )
              ) {
                return;
              }
              try {
                await invoke("brain_remove_skill", { name });
                toast(`Removed ${name}.`, "ok");
                await load(["skills"], { quiet: true });
                render("faculties");
              } catch (error) {
                toast(String((error && error.message) || error), "bad");
              }
            },
            { danger: true }
          ),
        ],
      });
    },
    "No skills installed, or the scanner has quarantined them all."
  );
}

function renderMemory() {
  const body = state.data.memory || {};
  const pending = state.data.memory_pending || {};
  dom.memory.replaceChildren();
  const why = unavailable("memory");
  if (why) return dom.memory.append(el("p", "empty", why));

  const dl = el("dl", "kv");
  const add = (k, v) => {
    if (v === undefined || v === null || v === "") return;
    dl.append(el("dt", "", k), el("dd", "", v));
  };
  add("Facts", body.facts ?? body.count);
  add("Documents", body.documents);
  add("Chunks", body.chunks);
  add("Store", body.path || body.store);
  add("Embedding", body.model || body.embedding);
  if (body.sleep_time) {
    add("Sleep-time", body.sleep_time.enabled ? "on" : "off");
  }
  if (dl.childElementCount) dom.memory.append(dl);

  const proposed = Array.isArray(pending.pending) ? pending.pending : [];
  if (proposed.length) {
    dom.memory.append(el("h3", "inspector-sub", "Proposed facts"));
    const list = el("div", "rows");
    for (const p of proposed.slice(0, 12)) {
      list.append(
        row({
          tag: "proposed",
          state: "warn",
          // Decided in the quickbar's gate, not here. This pane says a
          // decision is waiting; it does not offer to make it.
          title: String(p.text || p.fact || p.summary || "(no text)"),
          meta: [p.source ? `from ${p.source}` : "", ago(p.at || p.ts)],
          actions: [],
        })
      );
    }
    dom.memory.append(list);
    dom.memory.append(
      el(
        "p",
        "note",
        "Proposed facts are decided in the approval gate, one at a time — not from here."
      )
    );
  }
  if (!dom.memory.childElementCount) {
    dom.memory.append(el("p", "empty", "The memory store reported nothing."));
  }
}

/* ==========================================================================
   Work
   ========================================================================== */

function renderJobs() {
  const body = state.data.jobs || {};
  const why = unavailable("jobs");
  if (why) return rows(dom.jobs, [], null, why);
  const list = Array.isArray(body.jobs) ? body.jobs : [];

  rows(
    dom.jobs,
    list,
    (j) => {
      const jobState = String(j.state || "queued");
      const live = jobState === "running" || jobState === "queued";
      const caps = Array.isArray(j.caps) ? j.caps : [];
      return row({
        tag: jobState,
        state: jobState,
        title: String(j.label || j.handler || j.id || "(job)"),
        meta: [
          // The frozen capability set, shown because it is the promise: it was
          // fixed when the job was created and it cannot grow.
          caps.length ? `frozen capabilities: ${caps.join(", ")}` : "no capabilities",
          j.tainted ? "tainted — this job read private data and stays local" : "",
          [ago(j.created), j.result_summary || j.error || ""].filter(Boolean).join(" · "),
        ],
        actions: live
          ? [
              button(
                "Cancel",
                async () => {
                  if (
                    !confirm(
                      `Cancel "${j.label || j.id}"?\n\n` +
                        "Cancelling works mid-step and a cancelled job is not " +
                        "resumable — it starts again from the beginning or not at all."
                    )
                  ) {
                    return;
                  }
                  try {
                    await invoke("brain_cancel_job", { id: String(j.id) });
                    toast("Cancelled.", "ok");
                    await load(["jobs"], { quiet: true });
                    render("work");
                  } catch (error) {
                    toast(String((error && error.message) || error), "bad");
                  }
                },
                { danger: true }
              ),
            ]
          : [],
      });
    },
    "No Long Fuse jobs."
  );
}

function renderUndo() {
  const body = state.data.undo || {};
  const why = unavailable("undo");
  if (why) return rows(dom.undo, [], null, why);
  const shelf = Array.isArray(body.shelf) ? body.shelf : [];

  rows(
    dom.undo,
    shelf,
    (e) => {
      const revertible = e.revertible === true;
      const actions = [];
      if (revertible) {
        actions.push(
          button("Put it back", async () => {
            try {
              await invoke("brain_revert_undo", { id: String(e.id) });
              toast("Reverted.", "ok");
              await load(["undo"], { quiet: true });
              render("work");
            } catch (error) {
              toast(String((error && error.message) || error), "bad");
            }
          })
        );
      }
      // A hold is a message inside its send window: cancellable now, gone in a
      // moment, and never unsendable afterwards.
      if (e.category === "hold" && e.detail && e.detail.handle) {
        actions.push(
          button(
            "Stop sending",
            async () => {
              try {
                await invoke("brain_cancel_hold", { handle: String(e.detail.handle) });
                toast("Stopped before it went.", "ok");
                await load(["undo"], { quiet: true });
                render("work");
              } catch (error) {
                const message = String((error && error.message) || error);
                toast(
                  /409/.test(message)
                    ? "That one has already gone — there is no unsend."
                    : message,
                  "bad"
                );
              }
            },
            { danger: true }
          )
        );
      }
      // A hold inside its send window is the one entry that is neither
      // revertible nor final: it has not happened yet. Tagging it "final" next
      // to a live "Stop sending" button made the tag contradict the action.
      const holding = e.category === "hold" && e.detail && e.detail.handle;
      return row({
        tag: holding ? "holding" : revertible ? "revertible" : "final",
        state: holding ? "warn" : revertible ? "ok" : "bad",
        title: String(e.action || e.kind || "(action)"),
        meta: [
          e.target || "",
          holding
            ? e.reason || "still inside its send window — it can still be stopped"
            : revertible
              ? ""
              : e.reason || "cannot be undone",
          [ago(e.ts), e.before_bytes ? `${bytes(e.before_bytes)} held` : ""]
            .filter(Boolean)
            .join(" · "),
        ],
        actions,
      });
    },
    "Nothing on the shelf."
  );
}

/* ==========================================================================
   Trust
   ========================================================================== */

function renderContentRisk() {
  const body = state.data.content_risk || {};
  const why = unavailable("content_risk");
  dom.contentRisk.replaceChildren();
  if (why) return dom.contentRisk.append(el("p", "empty", why));

  const rush = body.rush;
  const banner = el(
    "div",
    "row-item",
    ""
  );
  banner.replaceChildren();
  const tag = el("span", "row-tag", rush ? "latched" : "clear");
  tag.dataset.state = rush ? "bad" : "ok";
  banner.append(tag);
  const main = el("div", "row-main");
  if (rush) {
    main.append(
      el(
        "span",
        "row-title",
        "A rush latch is active — outside text tried to hurry a decision."
      )
    );
    // The attacker's own words, quoted, because showing them is the point.
    if (rush.phrase) main.append(el("span", "row-meta", `“${rush.phrase}”`));
    if (rush.source) main.append(el("span", "row-meta", `from ${rush.source}`));
    main.append(
      el(
        "span",
        "row-meta",
        "It expires on its own. There is deliberately no control here that clears it."
      )
    );
  } else {
    main.append(el("span", "row-title", "No rush latch active."));
  }
  banner.append(main, el("div", "row-actions"));
  const wrap = el("div", "rows");
  wrap.append(banner);
  dom.contentRisk.append(wrap);

  const pins = Array.isArray(body.pins) ? body.pins : [];
  dom.contentRisk.append(el("h3", "inspector-sub", "Pinned text"));
  const pinBox = el("div");
  rows(
    pinBox,
    pins,
    (p) =>
      row({
        tag: "pinned",
        state: "ok",
        title: String(p.name || p.source || "(pinned)"),
        meta: [p.kind || "", p.at ? ago(p.at) : "", p.digest ? `digest ${String(p.digest).slice(0, 12)}` : ""],
        actions: [],
      }),
    "Nothing pinned. A skill or MCP tool description is pinned when a person has read its full current text."
  );
  dom.contentRisk.append(pinBox);
}

function renderLedger() {
  const body = state.data.ledger || {};
  const why = unavailable("ledger");
  dom.ledger.replaceChildren();
  if (why) return dom.ledger.append(el("p", "empty", why));

  const dl = el("dl", "kv");
  const add = (k, v) => {
    if (v === undefined || v === null || v === "") return;
    dl.append(el("dt", "", k), el("dd", "", v));
  };
  add("Entries", body.entries);
  add("Head", body.head ? String(body.head).slice(0, 20) + "…" : "");
  add("Head sequence", body.head_seq);
  add("Last entry", body.head_ts ? ago(body.head_ts) : "");
  add("With payload", body.with_payload);
  add("Metadata only", body.no_payload);
  add("Redacted", body.redacted);
  add("Expired", body.expired);
  dom.ledger.append(dl);

  const anchors = Array.isArray(body.anchors) ? body.anchors : [];
  dom.ledger.append(el("h3", "inspector-sub", "Anchors"));
  const box = el("div");
  rows(
    box,
    anchors.slice(-8).reverse(),
    (a) =>
      row({
        tag: a.mac_ok ? "verified" : "unverified",
        state: a.mac_ok ? "ok" : "bad",
        title: `seq ${a.seq ?? "—"}`,
        meta: [a.hash ? String(a.hash).slice(0, 24) + "…" : "", a.ts ? ago(a.ts) : ""],
        actions: [],
      }),
    "No anchors written yet."
  );
  dom.ledger.append(box);
}

/* ==========================================================================
   Watch
   ========================================================================== */

function renderWatch() {
  const body = state.data.watch || {};
  const why = unavailable("watch");
  if (why) return rows(dom.watch, [], null, why);

  const head = el("p", "note");
  head.textContent = [
    `${body.topics ?? 0} topics · ${body.tracking ?? 0} repositories known`,
    body.rate_limit || "",
  ]
    .filter(Boolean)
    .join(" · ");

  const list = Array.isArray(body.list) ? body.list : [];
  const box = el("div");
  rows(
    box,
    list,
    (t) =>
      row({
        tag: t.error ? "error" : "watching",
        state: t.error ? "bad" : "ok",
        title: String(t.name || ""),
        meta: [
          t.query && t.query !== t.name ? `query: ${t.query}` : "",
          t.error ? String(t.error) : "",
          [t.checked ? `checked ${ago(t.checked)}` : "never checked",
           t.notify ? "notify on" : "notify off"].join(" · "),
        ],
        actions: [
          button(
            "Forget",
            async () => {
              if (
                !confirm(
                  `Forget "${t.name}"?\n\nEverything remembered about this topic ` +
                    "goes with it — which repositories were already seen, and what " +
                    "was already reported. Adding it back starts from nothing."
                )
              ) {
                return;
              }
              try {
                await invoke("brain_watch_remove", { name: String(t.name) });
                toast(`Forgot ${t.name}.`, "ok");
                await load(["watch", "watch_report"], { quiet: true });
                render("watch");
              } catch (error) {
                toast(String((error && error.message) || error), "bad");
              }
            },
            { danger: true }
          ),
        ],
      }),
    "No topics watched."
  );
  dom.watch.replaceChildren(head, box);
}

function renderWatchReport() {
  const body = state.data.watch_report || {};
  const why = unavailable("watch_report");
  if (why) return rows(dom.watchReport, [], null, why);
  const findings = Array.isArray(body.findings)
    ? body.findings
    : Array.isArray(body.items)
      ? body.items
      : [];

  dom.watchSeen.disabled = findings.length === 0;

  rows(
    dom.watchReport,
    findings,
    (f) => {
      // "none stated" means no permission, not "probably fine" — so an absent
      // licence is rendered as a warning, not as a blank.
      const licence = String(f.licence || f.license || "").trim();
      const stated = licence && !/^(none|unknown|null)$/i.test(licence);
      return row({
        tag: stated ? licence : "no licence",
        state: stated ? "ok" : "warn",
        title: String(f.full_name || f.name || "(repository)"),
        meta: [
          String(f.descr || f.description || ""),
          [
            f.stars !== undefined ? `★ ${f.stars}` : "",
            f.topic ? `topic: ${f.topic}` : "",
            f.archived ? "archived" : "",
            stated ? "" : "no licence stated — no permission to use it",
          ]
            .filter(Boolean)
            .join(" · "),
          f.note ? `scanner: ${f.note}` : "",
        ],
        actions: [],
      });
    },
    "Nothing new since you last marked the list read."
  );
}

/* ==========================================================================
   Live
   ========================================================================== */

function renderLive() {
  const link = currentLink();
  const attention = link.attention;

  // The same answer the tray paints, from the same function — including
  // `approval` and `standby`, which the arbiter's own `face_state` does not
  // compose because they are UI precedence rather than its business.
  const face = surfaceState(link);
  dom.nowFace.dataset.face = face;
  dom.nowActivity.textContent = face;
  dom.nowPower.textContent = link.connected
    ? `power: ${link.power}${link.powerSetBy ? ` · ${link.powerSetBy}` : ""}`
    : link.error || "offline";

  const status = state.data.status || {};
  dom.nowKv.replaceChildren();
  const add = (k, v) => {
    if (v === undefined || v === null || v === "") return;
    dom.nowKv.append(el("dt", "", k), el("dd", "", v));
  };
  add("Model", status.model || status.current_model);
  add("Lane", status.lane || status.route);
  add("Approvals waiting", link.approvals);
  add("Stream", link.connected ? (link.stale ? "connected, stale" : "live") : "down");
  add("Last event", link.lastId || "");

  // The budget as pips, one per interruption. Spent ones go flat; when the
  // budget is blocked outright — Quiet, Standby, a locked session, muted — the
  // remaining pips go grey too, because "four left" is not true then.
  dom.budget.replaceChildren();
  if (attention.known) {
    const blocked = Boolean(attention.blockedBy);
    dom.budget.dataset.blocked = String(blocked);
    for (let i = 0; i < Math.max(attention.limit, 1); i++) {
      const pip = el("span", "pip");
      pip.dataset.spent = String(i < attention.spent);
      dom.budget.append(pip);
    }
    dom.budgetNote.textContent = blocked
      ? `Silent — ${attention.blockedBy}. ${attention.pending} waiting to be told.`
      : `${attention.remaining} of ${attention.limit} spoken interruptions left today · ` +
        `${attention.pending} waiting to be told`;
  } else {
    dom.budgetNote.textContent = "The interruption budget has not been read yet.";
  }
}

function pushTrace(frame) {
  const now = new Date();
  const time =
    String(now.getHours()).padStart(2, "0") +
    ":" +
    String(now.getMinutes()).padStart(2, "0") +
    ":" +
    String(now.getSeconds()).padStart(2, "0");

  const kind = String((frame && frame.kind) || "event");
  let body = "";
  const data = (frame && frame.data) || {};
  if (kind === "activity") body = String(data.state || "");
  else if (kind === "attention") {
    body = `remaining ${data.remaining ?? "?"} · pending ${data.pending ?? "?"}` +
      (data.banked ? " · banked" : "") +
      (data.blocked_by ? ` · ${data.blocked_by}` : "");
  } else if (kind === "approval") body = `${data.count ?? "?"} waiting`;
  else if (kind === "hello") {
    body = `resumed from ${data.resumed_from ?? 0}${data.stale ? " · STALE" : ""}`;
  } else {
    const value = data.value !== undefined ? data.value : data.title || data.key;
    body = value === undefined ? JSON.stringify(data).slice(0, 120) : String(value);
  }

  state.trace.push({ time, kind, body });
  // Bounded: this window can be left open for a day, and an unbounded list of
  // DOM nodes is a leak with a nice name.
  if (state.trace.length > 300) state.trace.splice(0, state.trace.length - 300);

  if (state.view !== "live") return;
  const li = el("li");
  li.append(
    el("span", "trace-time", time),
    el("span", "trace-kind", kind),
    el("span", "trace-body", body)
  );
  dom.trace.append(li);
  while (dom.trace.childElementCount > 300) dom.trace.firstElementChild.remove();
  dom.trace.scrollTop = dom.trace.scrollHeight;
}

function repaintTrace() {
  dom.trace.replaceChildren();
  for (const t of state.trace) {
    const li = el("li");
    li.append(
      el("span", "trace-time", t.time),
      el("span", "trace-kind", t.kind),
      el("span", "trace-body", t.body)
    );
    dom.trace.append(li);
  }
  dom.trace.scrollTop = dom.trace.scrollHeight;
}

/* ==========================================================================
   The galaxy
   --------------------------------------------------------------------------
   A force-directed layout, simulated to a stop and then drawn statically.

   Two decisions worth stating. First, the layout runs for a bounded number of
   cooling ticks and then freezes: a graph that jiggles for ever is harder to
   read and burns a core on a window that may be left open all day. The
   assembly is visible while it settles, which is the one moment of spectacle
   this view gets.

   Second, repulsion uses a uniform grid rather than every-pair. The node count
   is set by how much the owner's memory store knows, not by anything the UI
   controls, so O(n²) is a cliff somebody eventually falls off.
   ========================================================================== */

/**
 * A group is a hue AND a form, because ten hues cannot encode ten categories.
 *
 * The old ten-colour map measured CIEDE2000 6.0 between `core` and `cluster`
 * in normal vision — under the visual spec's own "obviously different at arm's
 * length" line before any colour blindness — and 1.0 under deuteranopia, which
 * is the spec's own word for indistinguishable. High contrast gave the two the
 * same hex outright.
 *
 * Five hues each carry two groups, told apart by whether the node is a filled
 * disc or a hollow ring. The pairs are semantically adjacent, so a misread
 * costs the least: a cluster mistaken for the core is a smaller error than a
 * cluster mistaken for a document. Form is not a theme concern — it is a fact
 * about what the group is — so it lives here and not in theme.css.
 */
const GROUP_STYLE = {
  core: ["--node-h1", "disc"],
  cluster: ["--node-h1", "ring"],
  model: ["--node-h2", "disc"],
  source: ["--node-h2", "ring"],
  fact: ["--node-h3", "disc"],
  document: ["--node-h3", "ring"],
  tool: ["--node-h4", "disc"],
  skill: ["--node-h4", "ring"],
  persona: ["--node-h5", "disc"],
  entity: ["--node-h5", "ring"],
};

/** Unknown groups get the last hue as a ring, which reads as "other". */
function styleFor(group) {
  return GROUP_STYLE[group] || ["--node-h5", "ring"];
}

const view = { x: 0, y: 0, scale: 1 };
let sim = null;
let hovered = null;
let selected = null;
const hiddenGroups = new Set();

/**
 * Node colours, cached.
 *
 * This is called once per node inside `draw()`, and `draw()` can run many times
 * per displayed frame. `getComputedStyle` per node per frame was a style query,
 * a string allocation and a trim for every dot on screen. The cache is cleared
 * whenever the theme changes and whenever a new graph is loaded, which are the
 * only two moments the answer can move.
 */
const colourCache = new Map();
function colourFor(group) {
  let hit = colourCache.get(group);
  if (hit !== undefined) return hit;
  const token = styleFor(group)[0];
  hit = getComputedStyle(dom.root).getPropertyValue(token).trim() || "#888";
  colourCache.set(group, hit);
  return hit;
}

/** Draws one node in its group's form. A ring is stroked, a disc is filled. */
function drawNode(ctx, x, y, r, group, colour) {
  if (styleFor(group)[1] === "ring") {
    // Stroked inside the radius so a ring and a disc of the same group read as
    // the same size — otherwise the ring looks like a bigger node.
    ctx.strokeStyle = colour;
    ctx.lineWidth = Math.max(1.4, r * 0.42);
    ctx.beginPath();
    ctx.arc(x, y, Math.max(1, r - ctx.lineWidth / 2), 0, Math.PI * 2);
    ctx.stroke();
    ctx.lineWidth = 1;
    return;
  }
  ctx.fillStyle = colour;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fill();
}

/**
 * Coalesces redraws onto the frame.
 *
 * `pointermove` fires at the mouse's polling rate — 125Hz typically, 1000Hz on
 * a gaming mouse — and every handler used to call `draw()` directly, so the
 * renderer could be asked to draw sixteen times per displayed frame. Every
 * input path goes through here instead.
 */
let drawQueued = false;
function invalidate() {
  if (drawQueued) return;
  drawQueued = true;
  requestAnimationFrame(() => {
    drawQueued = false;
    draw();
  });
}

function renderGraph() {
  const body = state.data.graph || {};
  const why = unavailable("graph");
  if (why) {
    dom.graphEmpty.hidden = false;
    dom.graphEmptyText.textContent = why;
    dom.graphStat.textContent = "—";
    state.graph = null;
    return;
  }
  const nodes = Array.isArray(body.nodes) ? body.nodes : [];
  const links = Array.isArray(body.links) ? body.links : [];
  if (!nodes.length) {
    dom.graphEmpty.hidden = false;
    dom.graphEmptyText.textContent = "The graph is empty.";
    state.graph = null;
    return;
  }
  dom.graphEmpty.hidden = true;

  const byId = new Map();
  const N = nodes.map((n, i) => {
    // A deterministic ring start rather than random: the same graph lays out
    // the same way twice, so the picture the owner learns stays learnable.
    const a = (i / nodes.length) * Math.PI * 2;
    const r = 40 + (i % 9) * 26;
    const node = {
      id: String(n.id),
      label: String(n.label ?? n.id),
      group: String(n.group || "entity"),
      weight: Number(n.weight) || 1,
      extra: n,
      x: Math.cos(a) * r,
      y: Math.sin(a) * r,
      vx: 0,
      vy: 0,
      deg: 0,
    };
    byId.set(node.id, node);
    return node;
  });
  const L = [];
  for (const l of links) {
    const s = byId.get(String(l.source));
    const t = byId.get(String(l.target));
    if (!s || !t || s === t) continue;
    s.deg++;
    t.deg++;
    L.push({ s, t, kind: String(l.kind || "") });
  }

  colourCache.clear();
  // Same node set as last time? Keep the settled positions. Clicking Galaxy
  // used to replay 1.3s of assembly on every visit, which is charming once and
  // an obstacle by the tenth time. Refresh still re-lays it out, so the
  // spectacle is one click away and never imposed.
  const signature = nodes.map((n) => n.id).join("\u0000");
  const settled = state.graph && state.graph.signature === signature
    ? new Map(state.graph.nodes.map((n) => [n.id, n]))
    : null;
  if (settled) {
    for (const n of N) {
      const was = settled.get(n.id);
      if (was) { n.x = was.x; n.y = was.y; }
    }
  }

  state.graph = { nodes: N, links: L, byId, signature };
  selected = null;
  dom.inspector.hidden = true;
  buildLegend(body.counts || countGroups(N));
  dom.graphStat.textContent = `${N.length} nodes · ${L.length} links`;
  if (settled) {
    fitCanvas();
    draw();
  } else {
    startLayout();
  }
}

function countGroups(nodes) {
  const counts = {};
  for (const n of nodes) counts[n.group] = (counts[n.group] || 0) + 1;
  return counts;
}

function buildLegend(counts) {
  const present = countGroups(state.graph.nodes);
  dom.legend.replaceChildren();
  for (const group of Object.keys(present).sort()) {
    const item = el("button", "legend-item");
    item.type = "button";
    item.setAttribute("aria-pressed", String(!hiddenGroups.has(group)));
    const sw = el("span", "legend-swatch");
    const [, form] = styleFor(group);
    sw.dataset.form = form;
    if (form === "ring") {
      sw.style.background = "transparent";
      sw.style.borderColor = colourFor(group);
    } else {
      sw.style.background = colourFor(group);
      sw.style.borderColor = "transparent";
    }
    item.append(sw, el("span", "", group), el("span", "legend-count", present[group]));
    item.addEventListener("click", () => {
      if (hiddenGroups.has(group)) hiddenGroups.delete(group);
      else hiddenGroups.add(group);
      item.setAttribute("aria-pressed", String(!hiddenGroups.has(group)));
      draw();
    });
    dom.legend.append(item);
  }
  const missing = Object.keys(counts).filter((k) => !(k in present) && counts[k]);
  if (missing.length) {
    dom.legend.append(el("span", "legend-count", `(${missing.join(", ")} not in the graph)`));
  }
}

function startLayout() {
  if (sim) cancelAnimationFrame(sim);
  const g = state.graph;
  if (!g) return;

  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const total = 320;
  // Ticks are driven by elapsed time, not by frames. Four ticks per frame meant
  // 80 frames of assembly: 1.33s at 60Hz, 0.67s at 120Hz, 0.49s at 165Hz — the
  // animation ran at whatever speed the monitor happened to be. The visual spec
  // already wrote this bug report for the reactor (`state_transforms.phase`:
  // never multiply the clock by a rate, integrate it) and this is the
  // frame-count version of the same mistake.
  const SIM_HZ = 240;
  let tick = 0;
  let carried = 0;
  let last = 0;

  // Reduced motion means no visible ASSEMBLY. It does not mean no time.
  //
  // This used to run all 320 ticks in one synchronous `while` loop, which is
  // the same total work the animated path does — delivered as a frozen window.
  // The node count is set by how much the owner's memory store knows, so on a
  // large graph that is a multi-second hang, and the person who gets it is the
  // one who asked for less motion because motion makes them unwell.
  //
  // Same chunking, same yielding, nothing drawn until it has settled.
  if (reduced) {
    dom.graphEmpty.hidden = false;
    dom.graphEmptyText.textContent = "Laying out the graph…";
    const slice = () => {
      const until = performance.now() + 8;
      while (tick < total && performance.now() < until) {
        step(g, 1 - tick / total);
        tick++;
      }
      if (tick < total) {
        sim = requestAnimationFrame(slice);
        return;
      }
      sim = null;
      dom.graphEmpty.hidden = true;
      fitToContent();
      draw();
    };
    sim = requestAnimationFrame(slice);
    return;
  }

  const frame = (now) => {
    if (!last) last = now;
    // Clamped: a background tab or a stalled frame must not deliver a hundred
    // ticks at once and detonate the layout.
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    carried += dt * SIM_HZ;
    const steps = Math.min(8, Math.floor(carried));
    carried -= steps;
    for (let i = 0; i < steps && tick < total; i++, tick++) {
      step(g, 1 - tick / total);
    }

    // The camera follows the whole way and eases in, rather than tracking for
    // twelve frames and then teleporting to the final fit. `k` is derived from
    // dt so the glide is the same on any refresh rate.
    fitToContent({ ease: 1 - Math.exp(-dt / 0.35) });
    draw();

    if (tick < total) sim = requestAnimationFrame(frame);
    else {
      sim = null;
      fitToContent();
      // Labels are only placed once the nodes have stopped. Re-running the
      // collision test every frame made names flicker in and out as the
      // packing resolved differently each time — the ugliest part of the
      // assembly, and removing it is also cheaper.
      draw();
    }
  };
  sim = requestAnimationFrame(frame);
}

/** One cooling tick: repulsion by grid, springs along links, pull to centre. */
function step(g, heat) {
  const nodes = g.nodes;
  // Tuned away from a lattice. The first pass used uniform repulsion with a
  // short cutoff and a uniform spring rest length, and uniform forces reach a
  // uniform equilibrium: 165 nodes settled into a visible grid, which reads as
  // a diagram of nothing.
  //
  // Two changes break it. Repulsion is longer-range and weaker per pair, so it
  // separates whole clusters rather than spacing individual nodes; and the
  // springs are four times stronger, so anything linked clumps hard. What you
  // see then is the shape of the connections, which is the only thing this
  // view is for.
  const REPEL = 2600;
  // CELL must be at least the reach radius, or the 3x3 neighbourhood below
  // does not contain everything the force is supposed to touch. It used to be
  // 130 against a 286px reach, so repulsion was silently truncated AND
  // direction-dependent: whether a node 200px east pushed you depended on
  // where the cell boundaries happened to fall. The layout still looked
  // plausible, which is why it survived — but it was not the force field the
  // constants describe.
  const REACH_R = 286;
  const CELL = REACH_R;
  const REACH = REACH_R ** 2;
  const SPRING = 0.035;
  const REST = 42;
  const CENTRE = 0.0009;
  const DAMP = 0.86;

  // Bucket by cell so repulsion is over neighbours rather than everybody.
  // Integer keys, not template strings. The string form cost one allocation
  // and one hash per node to insert plus nine more to look up — ten per node
  // per tick, times 320 ticks. At a few hundred nodes the garbage collector
  // was the bottleneck long before the geometry was.
  const key = (cx, cy) => (cx + 4096) * 8192 + (cy + 4096);
  const grid = new Map();
  for (const n of nodes) {
    const k = key(Math.floor(n.x / CELL), Math.floor(n.y / CELL));
    let cell = grid.get(k);
    if (!cell) grid.set(k, (cell = []));
    cell.push(n);
  }
  for (const n of nodes) {
    const cx = Math.floor(n.x / CELL);
    const cy = Math.floor(n.y / CELL);
    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        const cell = grid.get(key(cx + dx, cy + dy));
        if (!cell) continue;
        for (const m of cell) {
          if (m === n) continue;
          let ex = n.x - m.x;
          let ey = n.y - m.y;
          let d2 = ex * ex + ey * ey;
          if (d2 > REACH) continue;
          if (d2 < 0.01) {
            // Two nodes exactly on top of each other have no direction to
            // separate along; nudge deterministically by id so the layout
            // stays reproducible.
            ex = (n.id.charCodeAt(0) % 7) - 3 || 1;
            ey = (n.id.charCodeAt(1 % n.id.length) % 7) - 3 || 1;
            d2 = ex * ex + ey * ey;
          }
          const f = (REPEL * (1 + m.deg * 0.12)) / d2;
          const d = Math.sqrt(d2);
          n.vx += (ex / d) * f;
          n.vy += (ey / d) * f;
        }
      }
    }
  }

  for (const l of g.links) {
    const ex = l.t.x - l.s.x;
    const ey = l.t.y - l.s.y;
    const d = Math.hypot(ex, ey) || 0.01;
    const f = (d - REST) * SPRING;
    const ux = (ex / d) * f;
    const uy = (ey / d) * f;
    l.s.vx += ux;
    l.s.vy += uy;
    l.t.vx -= ux;
    l.t.vy -= uy;
  }

  for (const n of nodes) {
    n.vx -= n.x * CENTRE;
    n.vy -= n.y * CENTRE;
    n.vx *= DAMP;
    n.vy *= DAMP;
    const cap = 30 * heat;
    n.x += Math.max(-cap, Math.min(cap, n.vx));
    n.y += Math.max(-cap, Math.min(cap, n.vy));
  }
}

function radiusOf(n) {
  return 3 + Math.min(9, Math.sqrt(n.weight * 2 + n.deg));
}

function visible(n) {
  return !hiddenGroups.has(n.group);
}

function fitCanvas() {
  const c = dom.canvas;
  const rect = c.getBoundingClientRect();
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  c.width = Math.max(1, Math.round(rect.width * dpr));
  c.height = Math.max(1, Math.round(rect.height * dpr));
  draw();
}

function fitToContent({ ease = 1 } = {}) {
  const g = state.graph;
  if (!g || !g.nodes.length) return;
  const shown = g.nodes.filter(visible);
  const list = shown.length ? shown : g.nodes;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const n of list) {
    minX = Math.min(minX, n.x);
    maxX = Math.max(maxX, n.x);
    minY = Math.min(minY, n.y);
    maxY = Math.max(maxY, n.y);
  }
  const rect = dom.canvas.getBoundingClientRect();
  const pad = 60;
  const sx = (rect.width - pad * 2) / Math.max(1, maxX - minX);
  const sy = (rect.height - pad * 2) / Math.max(1, maxY - minY);
  const scale = Math.max(0.12, Math.min(2.4, Math.min(sx, sy)));
  const x = rect.width / 2 - ((minX + maxX) / 2) * scale;
  const y = rect.height / 2 - ((minY + maxY) / 2) * scale;
  const k = Math.max(0, Math.min(1, ease));
  view.scale += (scale - view.scale) * k;
  view.x += (x - view.x) * k;
  view.y += (y - view.y) * k;
}

function draw() {
  const c = dom.canvas;
  const ctx = c.getContext("2d");
  if (!ctx) return;
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, c.width / dpr, c.height / dpr);

  const g = state.graph;
  if (!g) return;

  const css = getComputedStyle(dom.root);
  const edge = css.getPropertyValue("--edge").trim() || "rgba(140,165,190,0.22)";
  const edgeActive = css.getPropertyValue("--edge-active").trim() || edge;
  const text = css.getPropertyValue("--text").trim() || "#fff";
  const faint = css.getPropertyValue("--text-faint").trim() || "#888";

  const T = (n) => [n.x * view.scale + view.x, n.y * view.scale + view.y];
  const focus = selected || hovered;
  const near = new Set();
  if (focus) {
    near.add(focus.id);
    for (const l of g.links) {
      if (l.s === focus) near.add(l.t.id);
      if (l.t === focus) near.add(l.s.id);
    }
  }

  // Two passes, two paths, two strokes — not one path per link. Each
  // beginPath/stroke pair is a separate Skia draw call, and at a couple of
  // thousand links that was the single most expensive thing on the canvas.
  // Links only ever come in two appearances (lit, or not), so two batches
  // covers every case.
  ctx.lineWidth = 1;
  for (const lit of [false, true]) {
    if (lit && !focus) continue;
    ctx.strokeStyle = lit ? edgeActive : edge;
    ctx.globalAlpha = focus ? (lit ? 1 : 0.18) : 1;
    ctx.beginPath();
    let drew = false;
    for (const l of g.links) {
      if (!visible(l.s) || !visible(l.t)) continue;
      const isLit = Boolean(focus && (l.s === focus || l.t === focus));
      if (isLit !== lit) continue;
      const [x1, y1] = T(l.s);
      const [x2, y2] = T(l.t);
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      drew = true;
    }
    if (drew) ctx.stroke();
  }
  ctx.globalAlpha = 1;

  for (const n of g.nodes) {
    if (!visible(n)) continue;
    const [x, y] = T(n);
    const r = radiusOf(n) * Math.max(0.55, Math.min(1.6, view.scale));
    const dim = focus && !near.has(n.id);
    // 0.45, not 0.2. At 0.2 a dimmed node measured 1.11:1 against the canvas —
    // invisible, while `nodeAt` still hit-tested it, so you could click a node
    // you could not see. De-emphasis, not erasure.
    ctx.globalAlpha = dim ? 0.45 : 1;
    drawNode(ctx, x, y, r, n.group, colourFor(n.group));
    if (n === selected) {
      ctx.strokeStyle = text;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(x, y, r + 4, 0, Math.PI * 2);
      ctx.stroke();
      ctx.lineWidth = 1;
    }
  }
  ctx.globalAlpha = 1;

  // Labels only where they can be read: the core, the heavy nodes, and
  // whatever is focused. Every node labelled at any zoom is a grey smear.
  ctx.font = '11px "Segoe UI", system-ui, sans-serif';
  ctx.textAlign = "center";
  ctx.textBaseline = "top";

  // Drawn in importance order and skipped where one would land on another
  // already placed. Overlapping labels are worse than missing ones: two names
  // on top of each other are unreadable AND hide that there are two things.
  // Not while it is still settling: see the note in `startLayout`.
  if (sim) return;
  const placed = [];
  const ordered = g.nodes
    .filter(visible)
    .filter((n) => n.group === "core" || n.group === "cluster" || n.deg >= 6 || near.has(n.id))
    .sort((a, b) => {
      const rank = (n) =>
        (n === focus ? 4 : 0) + (near.has(n.id) ? 2 : 0) +
        (n.group === "core" ? 3 : n.group === "cluster" ? 1 : 0);
      return rank(b) - rank(a) || b.deg - a.deg;
    });

  for (const n of ordered) {
    if (view.scale < 0.35 && !near.has(n.id) && n.group !== "core") continue;
    const [x, y] = T(n);
    const label = n.label.length > 34 ? n.label.slice(0, 33) + "…" : n.label;
    const w = ctx.measureText(label).width;
    const top = y + radiusOf(n) * Math.max(0.55, Math.min(1.6, view.scale)) + 3;
    const box = { x1: x - w / 2 - 2, x2: x + w / 2 + 2, y1: top - 1, y2: top + 13 };
    if (placed.some((p) => box.x1 < p.x2 && box.x2 > p.x1 && box.y1 < p.y2 && box.y2 > p.y1)) {
      continue;
    }
    placed.push(box);
    ctx.fillStyle = near.has(n.id) || !focus ? text : faint;
    // 0.55, not 0.25: at 0.25 these measured 1.43:1 and simply vanished — and
    // they are the orientation landmarks, so they disappeared exactly when
    // someone was exploring.
    ctx.globalAlpha = focus && !near.has(n.id) ? 0.55 : 1;
    ctx.fillText(label, x, top);
  }
  ctx.globalAlpha = 1;
}

function nodeAt(clientX, clientY) {
  const g = state.graph;
  if (!g) return null;
  const rect = dom.canvas.getBoundingClientRect();
  const px = clientX - rect.left;
  const py = clientY - rect.top;
  let best = null;
  let bestD = Infinity;
  for (const n of g.nodes) {
    if (!visible(n)) continue;
    const x = n.x * view.scale + view.x;
    const y = n.y * view.scale + view.y;
    const r = radiusOf(n) * Math.max(0.55, Math.min(1.6, view.scale)) + 4;
    const d = (x - px) ** 2 + (y - py) ** 2;
    if (d <= r * r && d < bestD) {
      best = n;
      bestD = d;
    }
  }
  return best;
}

function select(node) {
  selected = node;
  if (!node) {
    dom.inspector.hidden = true;
    draw();
    return;
  }
  dom.nodeKind.textContent = node.group;
  dom.nodeLabel.textContent = node.label;

  dom.nodeFacts.replaceChildren();
  const add = (k, v) => {
    if (v === undefined || v === null || v === "") return;
    dom.nodeFacts.append(el("dt", "", k), el("dd", "", v));
  };
  add("id", node.id);
  add("connections", node.deg);
  for (const [k, v] of Object.entries(node.extra || {})) {
    if (["id", "label", "group", "weight"].includes(k)) continue;
    if (v === null || typeof v === "object") continue;
    add(k, v);
  }

  const g = state.graph;
  const neighbours = [];
  for (const l of g.links) {
    if (l.s === node) neighbours.push([l.t, l.kind]);
    else if (l.t === node) neighbours.push([l.s, l.kind]);
  }
  dom.nodeLinks.replaceChildren();
  if (!neighbours.length) {
    dom.nodeLinks.append(el("li", "empty", "Nothing connected."));
  }
  for (const [other, kind] of neighbours.slice(0, 60)) {
    const li = el("li");
    const b = el("button", "", `${other.label}${kind ? ` · ${kind}` : ""}`);
    b.type = "button";
    b.addEventListener("click", () => {
      select(other);
      centreOn(other);
      // `select` calls `replaceChildren` on this list, so the button that was
      // just activated is removed from the document while it holds focus and
      // focus falls to <body>. A keyboard user lost their place on every hop
      // and had to tab from the top of the window again.
      dom.nodeLabel.focus({ preventScroll: true });
    });
    li.append(b);
    dom.nodeLinks.append(li);
  }
  dom.inspector.hidden = false;
  // A canvas has no accessibility tree, so selecting a node is otherwise a
  // silent event. This is the only thing that tells a screen-reader user
  // anything happened.
  announce(
    `${node.label}, ${node.group}, ${node.deg} ` +
      `${node.deg === 1 ? "connection" : "connections"}.`
  );
  draw();
}

function centreOn(node) {
  const rect = dom.canvas.getBoundingClientRect();
  view.x = rect.width / 2 - node.x * view.scale;
  view.y = rect.height / 2 - node.y * view.scale;
  draw();
}

/* ---- Canvas interaction -------------------------------------------------- */

let dragging = null;

dom.canvas.addEventListener("pointerdown", (e) => {
  dom.canvas.setPointerCapture(e.pointerId);
  dragging = { x: e.clientX, y: e.clientY, moved: false };
});

dom.canvas.addEventListener("pointermove", (e) => {
  if (dragging) {
    const dx = e.clientX - dragging.x;
    const dy = e.clientY - dragging.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) dragging.moved = true;
    view.x += dx;
    view.y += dy;
    dragging.x = e.clientX;
    dragging.y = e.clientY;
    invalidate();
    return;
  }
  const hit = nodeAt(e.clientX, e.clientY);
  if (hit !== hovered) {
    hovered = hit;
    dom.canvas.style.cursor = hit ? "pointer" : "grab";
    invalidate();
  }
});

dom.canvas.addEventListener("pointerup", (e) => {
  const wasDrag = dragging && dragging.moved;
  dragging = null;
  if (wasDrag) return;
  select(nodeAt(e.clientX, e.clientY));
});

dom.canvas.addEventListener(
  "wheel",
  (e) => {
    e.preventDefault();
    const rect = dom.canvas.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    const factor = Math.exp(-e.deltaY * 0.0016);
    const next = Math.max(0.08, Math.min(4, view.scale * factor));
    // Zoom about the cursor rather than the origin, so the thing under the
    // pointer stays under the pointer.
    view.x = px - ((px - view.x) / view.scale) * next;
    view.y = py - ((py - view.y) / view.scale) * next;
    view.scale = next;
    invalidate();
  },
  { passive: false }
);

// The canvas is focusable, so the graph is pannable and zoomable without a
// mouse. Selecting a node without one goes through the search field, which is
// also what makes the view usable with a screen reader.
dom.canvas.addEventListener("keydown", (e) => {
  const stepPx = e.shiftKey ? 120 : 40;
  const keys = {
    ArrowLeft: () => (view.x += stepPx),
    ArrowRight: () => (view.x -= stepPx),
    ArrowUp: () => (view.y += stepPx),
    ArrowDown: () => (view.y -= stepPx),
    "+": () => (view.scale = Math.min(4, view.scale * 1.2)),
    "=": () => (view.scale = Math.min(4, view.scale * 1.2)),
    "-": () => (view.scale = Math.max(0.08, view.scale / 1.2)),
    "0": () => fitToContent(),
    Escape: () => select(null),
  };
  const fn = keys[e.key];
  if (!fn) return;
  e.preventDefault();
  fn();
  invalidate();
});

/* ==========================================================================
   Theme
   ========================================================================== */

function applyTheme(name, { persist = true } = {}) {
  const theme = THEMES.includes(name) ? name : THEMES[0];
  dom.root.setAttribute("data-theme", theme);
  dom.themePicker.value = theme;
  try {
    localStorage.setItem("jarvis.theme", theme);
  } catch (error) {
    /* the store below is the source of truth; this is only the anti-flash cache */
  }
  if (persist) {
    invoke("set_theme", { theme }).catch((error) =>
      console.error("[brain] could not persist the theme:", error)
    );
  }
  // The graph reads its colours from the computed style, so a theme change has
  // to repaint it — nothing else on the page needs telling.
  colourCache.clear();
  if (state.graph) draw();
}

/* ==========================================================================
   Wiring
   ========================================================================== */

const TAB_ORDER = Object.keys(VIEWS);

for (const key of TAB_ORDER) {
  const tab = $(`tab-${key}`);
  if (tab) tab.addEventListener("click", () => showView(key));
}

/**
 * The rail is a `tablist`, and a tablist is one Tab stop with the arrows moving
 * inside it. It shipped as six separate Tab stops, which is the pattern the
 * role explicitly is not: a screen reader announces "tab, 1 of 6" and then the
 * arrows do nothing, and a keyboard user has to press Tab six times to get past
 * the navigation to the thing they came for.
 *
 * Vertical rail, so Up/Down are the axis and Left/Right are accepted too —
 * costs nothing and saves the reader guessing which one this rail thinks it is.
 */
dom.rail?.addEventListener("keydown", (event) => {
  const STEP = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 };
  const here = TAB_ORDER.indexOf(state.view);
  let next = null;
  if (event.key in STEP) next = (here + STEP[event.key] + TAB_ORDER.length) % TAB_ORDER.length;
  else if (event.key === "Home") next = 0;
  else if (event.key === "End") next = TAB_ORDER.length - 1;
  if (next === null || here < 0) return;
  event.preventDefault();
  // Selection follows focus, which is the right choice for a tablist whose
  // panels are already loaded: it is what a reader expects, and the alternative
  // (arrow to move, Enter to open) makes them press two keys for every view.
  showView(TAB_ORDER[next]);
  $(`tab-${TAB_ORDER[next]}`)?.focus();
});

dom.refresh.addEventListener("click", async () => {
  // Drop the cached layout so a refresh really re-lays out — and note that
  // `render` calls `startLayout` itself, so calling it again here started the
  // simulation twice and cancelled the first one mid-flight.
  if (state.view === "galaxy") state.graph = null;
  await load(VIEW_SECTIONS[state.view]);
  render(state.view);
});

dom.graphRefit.addEventListener("click", () => {
  fitToContent();
  draw();
});

dom.inspectorClose.addEventListener("click", () => select(null));

dom.graphSearch.addEventListener("input", () => {
  const q = dom.graphSearch.value.trim().toLowerCase();
  if (!q || !state.graph) return;
  const hit = state.graph.nodes.find(
    (n) => visible(n) && n.label.toLowerCase().includes(q)
  );
  if (hit) {
    select(hit);
    centreOn(hit);
  }
});

dom.traceClear.addEventListener("click", () => {
  state.trace = [];
  dom.trace.replaceChildren();
});

dom.themePicker.addEventListener("change", () => applyTheme(dom.themePicker.value));

dom.watchAddOpen.addEventListener("click", () => {
  dom.watchForm.hidden = !dom.watchForm.hidden;
  if (!dom.watchForm.hidden) $("watch-name").focus();
});
dom.watchCancel.addEventListener("click", () => {
  dom.watchForm.hidden = true;
});

dom.watchForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = $("watch-name").value.trim();
  if (!name) return;
  const stars = $("watch-stars").value.trim();
  try {
    await invoke("brain_watch_add", {
      name,
      query: $("watch-query").value.trim() || null,
      minStars: stars ? Number(stars) : null,
      language: $("watch-language").value.trim() || null,
      notify: $("watch-notify").checked,
    });
    toast(`Watching ${name}.`, "ok");
    dom.watchForm.reset();
    dom.watchForm.hidden = true;
    await load(["watch", "watch_report"], { quiet: true });
    render("watch");
  } catch (error) {
    toast(String((error && error.message) || error), "bad");
  }
});

dom.watchSeen.addEventListener("click", async () => {
  try {
    await invoke("brain_watch_seen", { topic: null });
    toast("Marked read.", "ok");
    await load(["watch", "watch_report"], { quiet: true });
    render("watch");
  } catch (error) {
    toast(String((error && error.message) || error), "bad");
  }
});

window.addEventListener("resize", () => {
  if (state.view === "galaxy") fitCanvas();
});

// Toggling the OS setting used to have no effect until the next refresh,
// because `matchMedia` was read once inside `startLayout`.
matchMedia("(prefers-reduced-motion: reduce)").addEventListener("change", () => {
  if (state.view === "galaxy" && state.graph) startLayout();
});

// The canvas is sized in device pixels from its CSS box, so a zoom step has to
// re-measure it or the graph is drawn at the old scale inside the new box.
followZoom(() => {
  if (state.view === "galaxy") fitCanvas();
});

/* ---- The one stream ------------------------------------------------------ */

startLink();

onLink((link) => {
  dom.linkPill.dataset.connected = String(link.connected);
  dom.linkText.textContent = link.connected
    ? link.stale
      ? "stream live · stale"
      : "stream live"
    : link.error
      ? "offline"
      : "connecting…";
  dom.linkPill.title = link.error || `${link.base} · last event ${link.lastId}`;
  if (state.view === "live") renderLive();
  renderCounts();
});

onEvent((frame) => {
  pushTrace(frame);
  // A doorbell for the pane that is open. Reading everything on every frame
  // would put the graph's multi-second walk on the event path.
  const kind = String((frame && frame.kind) || "");
  const refreshes = {
    model: ["models"],
    finding: ["watch", "watch_report"],
    job: ["jobs"],
  };
  const sections = refreshes[kind];
  if (!sections) return;
  const showing = VIEW_SECTIONS[state.view] || [];
  if (!sections.some((s) => showing.includes(s))) return;
  load(sections, { quiet: true }).then(() => render(state.view));
});

/* ---- Boot ---------------------------------------------------------------- */

(async () => {
  // The inline bootstrap already painted from localStorage; this reconciles
  // with the store, which is what the other windows read.
  try {
    const stored = await invoke("get_theme");
    if (stored && stored !== dom.root.getAttribute("data-theme")) {
      applyTheme(stored, { persist: false });
    } else {
      dom.themePicker.value = dom.root.getAttribute("data-theme") || THEMES[0];
    }
  } catch (error) {
    dom.themePicker.value = dom.root.getAttribute("data-theme") || THEMES[0];
  }

  repaintTrace();
  await showView("galaxy");
})();

console.info(
  `[brain] ready — backend ${IS_TAURI ? "connected" : "absent (browser preview)"}`
);
