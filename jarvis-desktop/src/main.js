/**
 * Jarvis Desktop — spotlight frontend.
 *
 * Responsibilities:
 *   • bridge to the Rust backend (`invoke`) and its events (`listen`);
 *   • stream `POST /api/chat` from the local Jarvis server and render the
 *     tokens as markdown into the answer card;
 *   • keep the native window sized to the card as it grows;
 *   • handle the keyboard contract — Enter to send, Esc to dismiss.
 *
 * The page is loaded with `withGlobalTauri`, so the API arrives on
 * `window.__TAURI__` rather than through a bundler. Every call is guarded so
 * the same file also runs in a plain browser tab while iterating on styling.
 */

/* ==========================================================================
   Configuration
   ========================================================================== */

const JARVIS_SERVER = "http://127.0.0.1:4719";
const CHAT_ENDPOINT = `${JARVIS_SERVER}/api/chat`;

/** Route badge defaults, overridden by whatever the server reports. */
const DEFAULT_ROUTE = { tier: "local", label: "Local", model: "qwen3:8b" };
const CLOUD_ROUTE = { tier: "cloud", label: "Cloud", model: "jarvis-escalate" };

/**
 * Sent as `X-Jarvis-Client`. The Jarvis server accepts a request whose `Origin`
 * is not in its allow-list only when this header marks it as a first-party HUD
 * client, and a Tauri WebView's origin (`http://tauri.localhost`) is never in
 * that list.
 */
const JARVIS_CLIENT_HEADER = "hud";

/**
 * The shared secret is deliberately absent from this file. Chat requests are
 * made by the Rust backend, which reads `JARVIS_TOKEN` from the environment, so
 * the token never enters WebView2 memory where a script in the HUD could read
 * it. See `stream_chat` in `commands.rs`.
 */

/** Clipboard context longer than this is trimmed in the attachment chip. */
const CLIPBOARD_PREVIEW = 90;

/**
 * Quick-capture prefixes. Typing one at the head of the prompt pre-routes the
 * turn to a note store and shows a chip; the prefix itself is stripped before
 * the text is sent.
 */
const NOTE_PREFIXES = {
  "#log": { target: "logseq", label: "Logseq Journal" },
  "#logseq": { target: "logseq", label: "Logseq Journal" },
  "#journal": { target: "logseq", label: "Logseq Journal" },
  "#joplin": { target: "joplin", label: "Joplin Vault" },
  "#vault": { target: "joplin", label: "Joplin Vault" },
};

/**
 * Routing instruction sent as a system turn alongside `note_target`, so a
 * server that reads either mechanism lands in the same place.
 */
const NOTE_INSTRUCTIONS = {
  logseq:
    "Route this turn to the Logseq daily journal via append_logseq_journal. " +
    "Capture it verbatim unless asked to summarise.",
  joplin:
    "Route this turn to the Joplin personal vault via create_joplin_note, " +
    "or search_joplin when the user is asking a question rather than filing one.",
};

/**
 * Smallest gap between native window resizes, in milliseconds. Each resize is a
 * `SetWindowPos` on a transparent, Acrylic-backed window; firing one per token
 * makes DWM recomposite the blur dozens of times a second, which shows up as
 * border flicker and stutter. Coalescing to ~7 Hz is invisible to the reader
 * and costs DWM nothing.
 */
const RESIZE_INTERVAL_MS = 150;

/* ==========================================================================
   Tauri bridge
   ========================================================================== */

import {
  currentLink,
  decide as decideOnBackend,
  onLink,
  onQueue,
  riskLine,
  start as startLink,
} from "./jarvis-link.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);

/**
 * Calls a Rust command. Resolves to `null` (and warns) when the backend is
 * unavailable, so a failed IPC call never takes the UI down with it.
 */
async function invoke(command, args = {}) {
  if (!IS_TAURI) {
    console.info(`[jarvis] invoke("${command}") skipped - no Tauri backend`);
    return null;
  }
  try {
    return await TAURI.core.invoke(command, args);
  } catch (error) {
    console.error(`[jarvis] invoke("${command}") failed:`, error);
    return null;
  }
}

/**
 * Like [`invoke`], but propagates the rejection. Used where the caller needs to
 * see the failure — the chat stream reports its terminal state through the
 * promise, so swallowing it would leave the card spinning forever.
 */
async function invokeStrict(command, args = {}) {
  if (!IS_TAURI) throw new Error("no Tauri backend");
  return TAURI.core.invoke(command, args);
}

/** Subscribes to a backend event. No-ops outside Tauri. */
async function listen(event, handler) {
  if (!TAURI || !TAURI.event || !TAURI.event.listen) return () => {};
  try {
    return await TAURI.event.listen(event, handler);
  } catch (error) {
    console.error(`[jarvis] listen("${event}") failed:`, error);
    return () => {};
  }
}

/* ==========================================================================
   DOM handles
   ========================================================================== */

const $ = (id) => document.getElementById(id);

const dom = {
  root: document.documentElement,
  shell: $("shell"),
  prompt: $("prompt"),
  route: $("route"),
  routeTier: $("route-tier"),
  routeModel: $("route-model"),
  pin: $("pin"),
  submitHint: $("submit-hint"),
  noteChip: $("note-chip"),
  noteChipLabel: $("note-chip-label"),

  approval: $("approval"),
  approvalAction: $("approval-action"),
  approvalTarget: $("approval-target"),
  approvalPreview: $("approval-preview"),
  approvalHint: $("approval-hint"),
  approvalApprove: $("approval-approve"),
  approvalDeny: $("approval-deny"),

  attachments: $("attachments"),
  captureChip: $("attachment-capture"),
  captureThumb: $("capture-thumb"),
  captureMeta: $("capture-meta"),
  captureRemove: $("capture-remove"),
  clipboardChip: $("attachment-clipboard"),
  clipboardMeta: $("clipboard-meta"),
  clipboardRemove: $("clipboard-remove"),

  card: $("card"),
  cardStatusText: $("card-status-text"),
  cardStat: $("card-stat"),
  cardBody: $("card-body"),
  answer: $("answer"),
  cursor: $("cursor"),
  copy: $("copy"),
  stop: $("stop"),
  services: $("services"),
};

/* ==========================================================================
   State
   ========================================================================== */

const state = {
  /** `idle` | `streaming` | `done` | `error` */
  phase: "idle",
  /** Raw markdown accumulated from the stream. */
  buffer: "",
  /** Prompt currently in flight, kept for the retry path. */
  inFlight: null,
  /** Cancels whichever transport is streaming; null when idle. */
  abort: null,
  startedAt: 0,
  chunks: 0,
  pinned: false,
  /** Pending screen capture, as a JPEG data URI. */
  capture: null,
  /** Pending clipboard context. */
  clipboard: null,
  /** `null`, `"logseq"` or `"joplin"` — set by a prompt prefix. */
  noteTarget: null,
  /** The approval gate awaiting a decision, if any. */
  approval: null,
  /** True while a decision is in flight, so a double tap cannot send twice. */
  deciding: false,
  route: { ...DEFAULT_ROUTE },
};

/** `idle` | `streaming` | `done` | `error` | `approval`. */
function setPhase(phase) {
  state.phase = phase;
  dom.root.dataset.state = phase;
}

/* ==========================================================================
   Markdown
   --------------------------------------------------------------------------
   A compact, dependency-free renderer. The content security policy forbids
   remote scripts, and a streaming card only needs the commonmark subset a chat
   model actually emits. Everything is HTML-escaped before any markup is
   introduced, so model output can never inject nodes.
   ========================================================================== */

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Inline spans: code, bold, italic, strikethrough, links. */
function renderInline(text) {
  let out = escapeHtml(text);

  // Inline code is lifted out first so its contents survive the emphasis
  // passes untouched, then restored at the end.
  const codeSpans = [];
  out = out.replace(/`([^`\n]+)`/g, (_match, code) => {
    codeSpans.push(code);
    return `@@JARVISCODE${codeSpans.length - 1}@@`;
  });

  // Strong runs first and non-greedily, so `**bold *italic* tail**` keeps its
  // inner emphasis instead of failing to match on the nested asterisks. The
  // italic pass then only sees the leftover single delimiters. `(?!\s)` keeps
  // arithmetic like `a * b * c` from turning into emphasis.
  out = out
    .replace(/\*\*\*([\s\S]+?)\*\*\*/g, "<strong><em>$1</em></strong>")
    .replace(/\*\*([\s\S]+?)\*\*/g, "<strong>$1</strong>")
    .replace(/__([\s\S]+?)__/g, "<strong>$1</strong>")
    .replace(/(^|[^*\w])\*(?!\s)([^*\n]+?)\*/g, "$1<em>$2</em>")
    .replace(/~~([\s\S]+?)~~/g, "<s>$1</s>");

  // Only http(s) links are linkified; anything else stays plain text so model
  // output can never produce a `javascript:` or `file:` href.
  out = out
    .replace(
      /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" data-external="true">$1</a>'
    )
    .replace(
      /(^|[\s(])(https?:\/\/[^\s<)]+)/g,
      '$1<a href="$2" data-external="true">$2</a>'
    );

  out = out.replace(
    /@@JARVISCODE(\d+)@@/g,
    (_match, index) => `<code>${codeSpans[Number(index)]}</code>`
  );

  return out;
}

/** Block-level renderer: fences, headings, lists, quotes, rules, tables. */
function renderMarkdown(source) {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const html = [];

  let index = 0;
  while (index < lines.length) {
    const line = lines[index];

    // Fenced code - also handles the unterminated fence of a live stream.
    const fence = line.match(/^\s*```([\w+-]*)\s*$/);
    if (fence) {
      const language = fence[1]
        ? ` class="language-${escapeHtml(fence[1])}"`
        : "";
      const body = [];
      index += 1;
      while (index < lines.length && !/^\s*```\s*$/.test(lines[index])) {
        body.push(lines[index]);
        index += 1;
      }
      index += 1; // consume the closing fence, if it has arrived
      html.push(
        `<pre><code${language}>${escapeHtml(body.join("\n"))}</code></pre>`
      );
      continue;
    }

    // Blank line.
    if (!line.trim()) {
      index += 1;
      continue;
    }

    // Horizontal rule.
    if (/^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/.test(line)) {
      html.push("<hr />");
      index += 1;
      continue;
    }

    // Heading.
    const heading = line.match(/^\s*(#{1,4})\s+(.*)$/);
    if (heading) {
      const level = heading[1].length;
      html.push(`<h${level}>${renderInline(heading[2].trim())}</h${level}>`);
      index += 1;
      continue;
    }

    // Blockquote.
    if (/^\s*>\s?/.test(line)) {
      const body = [];
      while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
        body.push(lines[index].replace(/^\s*>\s?/, ""));
        index += 1;
      }
      html.push(`<blockquote>${renderMarkdown(body.join("\n"))}</blockquote>`);
      continue;
    }

    // Table: a header row followed by a delimiter row.
    const nextLine = lines[index + 1] || "";
    if (line.includes("|") && /^\s*\|?[\s:-]*-[\s:|-]*\|?\s*$/.test(nextLine)) {
      const cells = (row) =>
        row
          .trim()
          .replace(/^\||\|$/g, "")
          .split("|")
          .map((cell) => cell.trim());

      const head = cells(line);
      index += 2;
      const body = [];
      while (
        index < lines.length &&
        lines[index].includes("|") &&
        lines[index].trim()
      ) {
        body.push(cells(lines[index]));
        index += 1;
      }

      const headHtml = head
        .map((cell) => `<th>${renderInline(cell)}</th>`)
        .join("");
      const bodyHtml = body
        .map(
          (row) =>
            `<tr>${row.map((cell) => `<td>${renderInline(cell)}</td>`).join("")}</tr>`
        )
        .join("");

      html.push(
        `<table><thead><tr>${headHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>`
      );
      continue;
    }

    // Lists. Indentation-aware: an item owns every following line indented
    // past its marker, so nested lists, multi-paragraph items and fenced code
    // inside an item all survive by recursing through this same parser.
    const marker = line.match(/^(\s*)([-*+]|\d+[.)])\s+/);
    if (marker) {
      const baseIndent = marker[1].length;
      const ordered = /\d/.test(marker[2]);
      const items = [];

      while (index < lines.length) {
        const item = lines[index].match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
        // A marker at a different indent belongs to an enclosing or nested
        // list; a different kind starts a separate list.
        if (!item || item[1].length !== baseIndent) break;
        if (/\d/.test(item[2]) !== ordered) break;

        const head = item[3];
        const rest = [];
        index += 1;

        while (index < lines.length) {
          const next = lines[index];
          if (!next.trim()) {
            // A blank line only stays inside the item when indented content
            // follows it; otherwise the list has ended.
            const after = lines[index + 1] || "";
            const afterIndent = after.match(/^(\s*)/)[1].length;
            if (!after.trim() || afterIndent <= baseIndent) break;
            rest.push("");
            index += 1;
            continue;
          }
          if (next.match(/^(\s*)/)[1].length <= baseIndent) break;
          rest.push(next);
          index += 1;
        }

        // Dedent continuation lines by their own common indent so nested
        // fences keep their original relative shape.
        const indents = rest
          .filter((l) => l.trim())
          .map((l) => l.match(/^(\s*)/)[1].length);
        const strip = indents.length ? Math.min(...indents) : 0;
        items.push([head, ...rest.map((l) => l.slice(strip))]);
      }

      const tag = ordered ? "ol" : "ul";
      const itemsHtml = items
        .map((buffer) => {
          // A one-line item stays inline so plain lists are not padded with
          // paragraph margins; anything richer goes back through the block
          // parser, with its leading paragraph unwrapped.
          if (buffer.length === 1) return `<li>${renderInline(buffer[0])}</li>`;
          const body = renderMarkdown(buffer.join("\n")).replace(
            /^<p>([\s\S]*?)<\/p>/,
            "$1"
          );
          return `<li>${body}</li>`;
        })
        .join("");
      html.push(`<${tag}>${itemsHtml}</${tag}>`);
      continue;
    }

    // Paragraph - greedily absorb the following plain lines.
    const paragraph = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !/^\s*(#{1,4}\s|>|```|[-*+]\s|\d+[.)]\s)/.test(lines[index])
    ) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    html.push(`<p>${renderInline(paragraph.join(" "))}</p>`);
  }

  return html.join("");
}

/* ==========================================================================
   Card rendering and native window sizing
   ========================================================================== */

let paintQueued = false;

/** Repaints the card from the buffer, at most once per animation frame. */
function paint({ immediate = false } = {}) {
  if (paintQueued && !immediate) return;
  paintQueued = true;

  requestAnimationFrame(() => {
    paintQueued = false;

    dom.answer.innerHTML = renderMarkdown(state.buffer);
    const last = dom.answer.lastElementChild;
    if (last && state.phase === "streaming") last.classList.add("fresh");

    // Keep the newest tokens in view unless the user scrolled up to read.
    const body = dom.cardBody;
    const nearBottom =
      body.scrollHeight - body.scrollTop - body.clientHeight < 60;
    if (nearBottom) body.scrollTop = body.scrollHeight;

    syncWindowHeight();
  });
}

let lastReportedHeight = 0;
let pendingHeight = 0;
let lastResizeAt = 0;
let resizeTimer = null;

/**
 * Measures the shell and asks the backend to match it, at most once every
 * [`RESIZE_INTERVAL_MS`]. While an answer streams the window only ever grows:
 * a reflow that briefly reports a shorter shell would otherwise make the frame
 * jitter between two heights.
 */
function syncWindowHeight() {
  const height = Math.ceil(dom.shell.getBoundingClientRect().height);
  if (!height) return;
  if (state.phase === "streaming" && height < lastReportedHeight) return;

  pendingHeight = height;
  if (Math.abs(height - lastReportedHeight) < 2) return;

  const elapsed = performance.now() - lastResizeAt;
  if (elapsed >= RESIZE_INTERVAL_MS) {
    commitWindowHeight();
  } else if (resizeTimer === null) {
    resizeTimer = setTimeout(commitWindowHeight, RESIZE_INTERVAL_MS - elapsed);
  }
}

/** Sends the pending height to the backend and restarts the throttle window. */
function commitWindowHeight() {
  if (resizeTimer !== null) {
    clearTimeout(resizeTimer);
    resizeTimer = null;
  }
  if (!pendingHeight || Math.abs(pendingHeight - lastReportedHeight) < 2) return;
  lastReportedHeight = pendingHeight;
  lastResizeAt = performance.now();
  invoke("resize_quickbar", { height: pendingHeight });
}

if (typeof ResizeObserver !== "undefined") {
  new ResizeObserver(() => syncWindowHeight()).observe(dom.shell);
}

/** Shows the card and sets its status line. */
function openCard(statusText) {
  dom.card.hidden = false;
  dom.cardStatusText.textContent = statusText;
}

/** Collapses the card and clears everything it was showing. */
function closeCard() {
  dom.card.hidden = true;
  dom.answer.innerHTML = "";
  dom.cardStat.textContent = "";
  dom.cursor.hidden = true;
  state.buffer = "";
  setPhase("idle");
  paint({ immediate: true });
}

/** Renders a failure inside the card instead of silently doing nothing. */
function showError(message) {
  setPhase("error");
  openCard("Error");
  dom.cursor.hidden = true;
  state.buffer = `**Jarvis could not answer.**\n\n${message}`;
  paint({ immediate: true });
}

/* ==========================================================================
   Route badge and service health
   ========================================================================== */

function applyRoute(route) {
  state.route = { ...state.route, ...route };
  dom.route.dataset.route = state.route.tier;
  dom.routeTier.textContent = state.route.label;
  dom.routeModel.textContent = state.route.model;
  dom.route.title = `Serving from ${state.route.label.toLowerCase()} - ${state.route.model}`;
  // The widget shows the same lane; it has no stream to learn it from.
  invoke("set_route_lane", { lane: state.route.tier });
}

/**
 * Normalises the many shapes a server might use to describe the active route
 * into the two the badge understands.
 */
function routeFromPayload(payload) {
  if (!payload || typeof payload !== "object") return null;

  const meta = payload.meta || payload.metadata || payload;
  const rawTier = String(
    meta.route || meta.tier || meta.provider || ""
  ).toLowerCase();
  const model = meta.model || meta.model_name || payload.model;

  if (!rawTier && !model) return null;

  const isCloud = /cloud|remote|escalat|openai|anthropic|azure|litellm/.test(
    rawTier
  );
  const base = isCloud ? CLOUD_ROUTE : DEFAULT_ROUTE;

  return {
    tier: isCloud ? "cloud" : "local",
    label: isCloud ? "Cloud" : "Local",
    model: model || base.model,
  };
}

/** Paints the three health dots in the card footer. */
function applyHealth(report) {
  if (!report || !Array.isArray(report.services)) return;

  for (const service of report.services) {
    const dot = dom.services.querySelector(`[data-service="${service.id}"]`);
    if (!dot) continue;
    dot.dataset.online = String(Boolean(service.online));
    dot.title = `${service.name}: ${service.detail}`;
  }

  const core = report.services.find((service) => service.id === "jarvis");
  if (core && !core.online) {
    applyRoute({ tier: "offline", label: "Offline", model: "core unreachable" });
  } else if (state.route.tier === "offline") {
    applyRoute(DEFAULT_ROUTE);
  }
}

/**
 * Fire-and-forget probe of the three local services.
 *
 * Called when something has actually changed — the window is summoned, the
 * stream connects or drops, a request fails — and never on a timer. Ollama and
 * the LiteLLM proxy are not on the event bus, so their dots still need a probe;
 * Jarvis itself does not, because a live event stream *is* the proof that it is
 * up, and a better one than a request that succeeded a moment ago.
 */
async function refreshHealth() {
  const report = await invoke("check_server_health");
  if (report) applyHealth(report);
}

/* ==========================================================================
   Attachments
   ========================================================================== */

function syncAttachments() {
  dom.captureChip.hidden = !state.capture;
  dom.clipboardChip.hidden = !state.clipboard;
  dom.attachments.hidden = !state.capture && !state.clipboard;
  syncWindowHeight();
}

function attachCapture(payload) {
  state.capture = payload.dataUri;
  dom.captureThumb.src = payload.dataUri;
  dom.captureMeta.textContent = `${payload.width}x${payload.height} · ${Math.round(
    payload.bytes / 1024
  )} KB · ${payload.elapsedMs} ms`;
  syncAttachments();
}

function attachClipboard(text) {
  state.clipboard = text;
  const preview = text.replace(/\s+/g, " ").trim();
  dom.clipboardMeta.textContent =
    preview.length > CLIPBOARD_PREVIEW
      ? `${preview.slice(0, CLIPBOARD_PREVIEW)}…`
      : preview;
  syncAttachments();
}

/* ==========================================================================
   Quick capture — note prefixes
   ========================================================================== */

/**
 * Splits a leading `#log` / `#joplin` prefix off the prompt.
 * Returns the target (or null) and the text with the prefix removed.
 */
function parseNotePrefix(text) {
  const match = text.match(/^\s*(#[a-z]+)(\s+|$)/i);
  if (!match) return { target: null, label: null, body: text };
  const spec = NOTE_PREFIXES[match[1].toLowerCase()];
  if (!spec) return { target: null, label: null, body: text };
  return { ...spec, body: text.slice(match[0].length) };
}

/** Mirrors the prefix in the chip beside the reactor as the user types. */
function syncNoteChip() {
  const { target, label } = parseNotePrefix(dom.prompt.value);
  state.noteTarget = target;
  dom.noteChip.hidden = !target;
  if (target) {
    dom.noteChip.dataset.target = target;
    dom.noteChipLabel.textContent = label;
  }
  syncWindowHeight();
}

/* ==========================================================================
   Approval gates
   ========================================================================== */

/*
 * There used to be an `approvalFromChunk()` here that sniffed the chat stream
 * for anything that looked like a gate — `tier: "ask"`, `status:
 * "pending_approval"`, half a dozen id spellings — and opened a card from it.
 *
 * It is gone, and its absence is the point. `/api/pending` is the only place
 * that knows what is waiting, `jarvis_gate.pending()` is what fills it, and the
 * `risk` object that says what getting the answer wrong costs is derived there
 * at read time and exists nowhere else. A card built by guessing at chat chunks
 * had no risk to show and no way to know when something had already been
 * answered somewhere else.
 *
 * So the quickbar no longer decides what an approval is. Rust reads the queue
 * once, when the stream rings the bell, and every surface renders the same
 * list. This file's remaining job is to draw it.
 */

/**
 * Builds the markdown preview shown inside the approval card.
 *
 * `detail` is whatever the caller passed to `jarvis_gate.check()`, JSON-encoded
 * and truncated to 4000 characters by the gate — so it can arrive as an object,
 * as a string that no longer parses, or not at all. All three are drawn.
 */
function approvalPreview(approval) {
  const detail = approval.detail;

  if (typeof detail === "string") {
    return detail.trim()
      ? `\`\`\`\n${detail.trim()}\n\`\`\``
      : "_No detail was recorded for this action._";
  }
  if (detail && typeof detail === "object") {
    for (const [key, fence] of [
      ["diff", "diff"],
      ["command", "sh"],
      ["cmd", "sh"],
    ]) {
      if (typeof detail[key] === "string" && detail[key].trim()) {
        return `\`\`\`${fence}\n${detail[key].trim()}\n\`\`\``;
      }
    }
    for (const key of ["preview", "content", "body", "text", "summary"]) {
      if (typeof detail[key] === "string" && detail[key].trim()) return detail[key];
    }
    return `\`\`\`json\n${JSON.stringify(detail, null, 2)}\n\`\`\``;
  }
  if (approval.prompt.trim()) return approval.prompt.trim();
  return "_No detail was recorded for this action._";
}

/**
 * Colours a unified diff inside the preview.
 *
 * Operates on `textContent` and rebuilds the node from escaped pieces, so the
 * escape-first guarantee of the renderer still holds.
 */
function decorateDiff(container) {
  for (const code of container.querySelectorAll("pre code.language-diff")) {
    const html = code.textContent
      .split("\n")
      .map((line) => {
        const escaped = escapeHtml(line);
        if (/^(\+\+\+|---|@@|diff |index )/.test(line)) {
          return `<span class="diff-meta">${escaped || "&nbsp;"}</span>`;
        }
        if (line.startsWith("+")) {
          return `<span class="diff-add">${escaped || "&nbsp;"}</span>`;
        }
        if (line.startsWith("-")) {
          return `<span class="diff-remove">${escaped || "&nbsp;"}</span>`;
        }
        return `<span>${escaped || "&nbsp;"}</span>`;
      })
      .join("");
    code.innerHTML = html;
  }
}

/**
 * Renders the gate and hands the keyboard to it.
 *
 * Called only from the queue subscription — never from the chat stream.
 */
function openApproval(approval) {
  state.approval = approval;
  setPhase("approval");

  dom.approvalAction.textContent = approval.action;
  const target = approval.detail && typeof approval.detail === "object"
    ? approval.detail.target || approval.detail.note_target || approval.detail.to
    : null;
  dom.approvalTarget.hidden = !target;
  if (target) dom.approvalTarget.textContent = String(target);

  dom.approvalPreview.innerHTML = renderMarkdown(approvalPreview(approval));
  decorateDiff(dom.approvalPreview);

  // The risk line is the whole reason the gate is worth showing rather than
  // merely enforcing: `switch_model` and `send_email` are both tier `ask` and
  // arrive looking identical until this is on screen.
  dom.approvalHint.textContent = riskLine(approval.risk);
  dom.approvalHint.dataset.reversible = approval.risk
    ? approval.risk.reversible
    : "no";
  dom.approvalHint.dataset.reach = approval.risk ? approval.risk.reach : "outbound";

  syncApprovalButtons();
  dom.approval.hidden = false;

  if (!dom.card.hidden) dom.cardStatusText.textContent = "Paused for approval";

  setPinned(true, { silent: true });
  focusInput({ selectAll: false });
  dom.approvalApprove.focus();
  syncWindowHeight();
}

/** Clears the gate. Called when it leaves the queue, however it left. */
function closeApproval() {
  state.approval = null;
  dom.approval.hidden = true;
  dom.approvalPreview.innerHTML = "";
  syncWindowHeight();
}

/**
 * Enables or disables the two buttons from the link state.
 *
 * A stale stream means the queue cannot be confirmed live, and answering one
 * that cannot be confirmed is how the same action gets approved twice.
 */
function syncApprovalButtons() {
  const link = currentLink();
  const blocked = link.stale || state.deciding;
  dom.approvalApprove.disabled = blocked;
  dom.approvalDeny.disabled = blocked;
  if (link.stale && state.approval) {
    dom.approvalHint.textContent =
      "Offline — the approval queue cannot be confirmed, so nothing can be answered from here.";
  }
}

/**
 * Sends the decision and reports the outcome in the answer card.
 *
 * The decision itself goes to `decide_approval` in Rust — the one place that
 * talks to `/api/approve` and `/api/deny`, so the 409 that means "already
 * decided" is handled once rather than in each of three windows. The card
 * closes when the backend broadcasts the resolution, not when this returns,
 * so a decision taken in the widget closes the quickbar's copy the same way.
 */
async function decideApproval(approved) {
  const approval = state.approval;
  if (!approval || state.deciding) return;

  state.deciding = true;
  syncApprovalButtons();
  dom.approvalHint.textContent = approved ? "Approving…" : "Denying…";

  try {
    await decideOnBackend(approval.id, approved);
    state.buffer += `${state.buffer.trim() ? "\n\n" : ""}> ${
      approved ? "Approved" : "Denied"
    } \`${approval.action}\` from the desktop spotlight.`;
    openCard(approved ? "Approved" : "Denied");
    paint({ immediate: true });
  } catch (error) {
    const message = String(
      (error && error.message) || error || "the decision could not be sent"
    );
    // The server answers 409 when the id is unknown, expired, or already
    // decided. That is not a failure to report as one — someone answered it,
    // possibly on the phone — so say so and let the queue update close the card.
    dom.approvalHint.textContent = /409|already/i.test(message)
      ? "Already handled somewhere else."
      : message;
  } finally {
    state.deciding = false;
    syncApprovalButtons();
    await setPinned(false, { silent: true });
  }
}

/* ==========================================================================
   Streaming
   ========================================================================== */

/**
 * Pulls a text delta out of one decoded stream object, supporting the shapes
 * Jarvis, Ollama and OpenAI-compatible proxies each emit.
 */
function deltaFromChunk(chunk) {
  if (typeof chunk === "string") return chunk;
  if (!chunk || typeof chunk !== "object") return "";

  const choice = Array.isArray(chunk.choices) ? chunk.choices[0] : null;
  const fromChoice =
    choice &&
    ((choice.delta && choice.delta.content) ||
      (choice.message && choice.message.content) ||
      choice.text);
  const fromDelta =
    typeof chunk.delta === "string"
      ? chunk.delta
      : chunk.delta && chunk.delta.content;

  return (
    fromChoice ||
    (chunk.message && chunk.message.content) ||
    chunk.response ||
    fromDelta ||
    chunk.token ||
    chunk.content ||
    chunk.text ||
    ""
  );
}

/** True when a decoded object marks the end of the stream. */
function isTerminal(chunk) {
  if (!chunk || typeof chunk !== "object") return false;
  const choice = Array.isArray(chunk.choices) ? chunk.choices[0] : null;
  return (
    chunk.done === true ||
    chunk.finished === true ||
    chunk.event === "done" ||
    Boolean(choice && choice.finish_reason)
  );
}

/**
 * Consumes one line of the response body. Handles Server-Sent Events
 * (`data: {...}`), newline-delimited JSON, and bare text as a last resort.
 * Returns `true` when the stream should stop.
 */
function consumeLine(rawLine) {
  let line = rawLine.trim();
  if (!line) return false;

  // SSE comment / heartbeat.
  if (line.startsWith(":")) return false;

  // SSE fields other than `data:` carry nothing we render.
  if (/^(event|id|retry):/i.test(line)) return false;

  if (line.toLowerCase().startsWith("data:")) {
    line = line.slice(5).trim();
  }

  if (line === "[DONE]") return true;

  let chunk;
  try {
    chunk = JSON.parse(line);
  } catch {
    // Not JSON - treat it as a raw token, which is what a plain text stream
    // produces.
    appendDelta(line);
    return false;
  }

  if (chunk.error) {
    showError(String((chunk.error && chunk.error.message) || chunk.error));
    return true;
  }

  const route = routeFromPayload(chunk);
  if (route) applyRoute(route);

  appendDelta(deltaFromChunk(chunk));

  return isTerminal(chunk);
}

/** Appends text to the buffer and schedules a repaint. */
function appendDelta(text) {
  if (!text) return;
  state.buffer += text;
  state.chunks += 1;
  updateStat();
  paint();
}

function updateStat() {
  const seconds = (performance.now() - state.startedAt) / 1000;
  dom.cardStat.textContent = `${state.chunks} chunks · ${seconds.toFixed(1)}s`;
}

/** Cancels the stream in flight, if there is one. */
function abortStream() {
  const abort = state.abort;
  if (!abort) return;
  state.abort = null;
  abort();
}

/**
 * Streams through the Rust backend over a Tauri channel.
 *
 * The channel carries raw response lines; the promise carries the terminal
 * state. That split means the frontend never has to infer "the stream ended"
 * from silence, and a transport failure arrives as a rejection rather than a
 * card that spins forever.
 */
async function streamViaBackend(payload) {
  const channel = new TAURI.core.Channel();
  let settled = false;

  channel.onmessage = (line) => {
    if (settled || typeof line !== "string") return;
    // `consumeLine` returns true on the stream's own terminator, and on an
    // approval gate — both mean stop reading.
    if (consumeLine(line)) {
      settled = true;
      invoke("cancel_chat");
    }
  };

  state.abort = () => {
    settled = true;
    invoke("cancel_chat");
    finishStream("done", "Stopped");
  };

  try {
    await invokeStrict("stream_chat", { ...payload, onEvent: channel });
    if (settled) return;
    settled = true;
    finishStream(state.phase === "error" ? "error" : "done");
  } catch (error) {
    if (settled) return;
    settled = true;
    showError(String((error && error.message) || error));
    finishStream("error");
    refreshHealth();
  }
}

/**
 * Browser-preview transport: a plain streaming fetch, used only when the page
 * is opened outside Tauri (`npm run dev` in a browser tab, or the headless
 * screenshot harness). It is subject to CORS and carries no token.
 */
async function streamViaFetch(payload) {
  const controller = new AbortController();
  state.abort = () => controller.abort();

  try {
    const response = await fetch(CHAT_ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        "X-Jarvis-Client": JARVIS_CLIENT_HEADER,
      },
      body: JSON.stringify({
        messages: payload.messages,
        has_image: payload.hasImage,
        images: payload.images,
        stream: true,
        auto: payload.auto,
        ...(payload.noteTarget ? { note_target: payload.noteTarget } : {}),
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      const hint =
        response.status === 403
          ? " — the server rejected this origin."
          : response.status === 400
            ? " — the server rejected the request body."
            : "";
      throw new Error(
        `the server answered HTTP ${response.status} ${response.statusText}${hint}`
      );
    }

    dom.cardStatusText.textContent = "Streaming";

    if (!response.body) {
      consumeLine(await response.text());
      finishStream("done");
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = "";

    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;

      pending += decoder.decode(value, { stream: true });
      const lines = pending.split("\n");
      pending = lines.pop() || "";

      let stop = false;
      for (const line of lines) {
        if (consumeLine(line)) {
          stop = true;
          break;
        }
      }
      if (stop) {
        await reader.cancel().catch(() => {});
        break;
      }
    }

    if (pending.trim()) consumeLine(pending);
    finishStream(state.phase === "error" ? "error" : "done");
  } catch (error) {
    if (error && error.name === "AbortError") {
      finishStream("done", "Stopped");
      return;
    }
    const hint =
      error instanceof TypeError
        ? `Could not reach the Jarvis server at ${JARVIS_SERVER}. Is it running?`
        : String((error && error.message) || error);
    showError(hint);
    finishStream("error");
    refreshHealth();
  }
}

/** Sends the prompt and streams the answer into the card. */
async function send(promptText) {
  const message = promptText.trim();
  if (!message || state.phase === "streaming") return;

  state.inFlight = message;
  state.buffer = "";
  state.chunks = 0;
  state.startedAt = performance.now();

  setPhase("streaming");
  openCard("Thinking…");
  dom.cursor.hidden = false;
  dom.stop.hidden = false;
  dom.answer.innerHTML = "";
  dom.cardStat.textContent = "";

  // Stay open while the answer streams, even if focus wanders.
  await setPinned(true, { silent: true });

  // A `#log` / `#joplin` prefix pre-routes the turn: the prefix is stripped
  // from the text, declared as `note_target`, and restated as a system turn so
  // a server reading either mechanism lands in the same place.
  const { target: noteTarget, body } = parseNotePrefix(message);
  const text = noteTarget ? body.trim() : message;

  // Clipboard context rides as a system turn; the server validates an
  // OpenAI-shaped `messages` array and routes on `has_image`.
  const payload = {
    messages: [
      ...(noteTarget ? [{ role: "system", content: NOTE_INSTRUCTIONS[noteTarget] }] : []),
      ...(state.clipboard
        ? [{ role: "system", content: `Context:\n${state.clipboard}` }]
        : []),
      { role: "user", content: text },
    ],
    hasImage: Boolean(state.capture),
    images: state.capture ? [state.capture] : [],
    auto: true,
    noteTarget,
  };

  if (IS_TAURI) {
    dom.cardStatusText.textContent = "Streaming";
    await streamViaBackend(payload);
  } else {
    await streamViaFetch(payload);
  }
}

/** Common teardown for every way a stream can end. */
function finishStream(phase, statusText) {
  state.abort = null;
  dom.cursor.hidden = true;
  dom.stop.hidden = true;

  if (phase !== "error") {
    setPhase("done");
    dom.cardStatusText.textContent =
      statusText || (state.buffer.trim() ? "Complete" : "No content returned");
    if (!state.buffer.trim()) {
      state.buffer = "_The server closed the stream without sending content._";
    }
  }

  updateStat();
  paint({ immediate: true });
  // The stream is over, so settle the window on its final height immediately
  // rather than waiting out the throttle.
  commitWindowHeight();

  // Release the pin so clicking away dismisses the bar again.
  setPinned(false, { silent: true });
}

/* ==========================================================================
   Pin and dismiss
   ========================================================================== */

async function setPinned(pinned, { silent = false } = {}) {
  state.pinned = pinned;
  dom.pin.setAttribute("aria-pressed", String(pinned));
  if (!silent) {
    dom.pin.title = pinned
      ? "Unpin (auto-hide on focus loss)"
      : "Keep Jarvis open when it loses focus";
  }
  await invoke("set_quickbar_pinned", { pinned });
}

/** Clears the composer and hides the window. */
async function dismiss() {
  abortStream();
  closeApproval();
  dom.prompt.value = "";
  autoGrowPrompt();
  syncNoteChip();
  state.capture = null;
  state.clipboard = null;
  dom.captureThumb.removeAttribute("src");
  syncAttachments();
  closeCard();
  await setPinned(false, { silent: true });
  await invoke("hide_quickbar");
}

/* ==========================================================================
   Composer
   ========================================================================== */

/** Grows the textarea up to two lines before it starts scrolling. */
function autoGrowPrompt() {
  dom.prompt.style.height = "auto";
  dom.prompt.style.height = `${Math.min(dom.prompt.scrollHeight, 56)}px`;
  syncWindowHeight();
}

function focusInput({ selectAll = true } = {}) {
  dom.prompt.focus();
  if (selectAll) dom.prompt.select();
}

function submitCurrentPrompt() {
  // A pending gate owns Enter: the safe thing must be the deliberate thing.
  if (state.approval) {
    decideApproval(true);
    return;
  }
  const value = dom.prompt.value;
  if (!value.trim()) return;
  dom.prompt.value = "";
  autoGrowPrompt();
  send(value);
}

/* ==========================================================================
   Event wiring
   ========================================================================== */

dom.prompt.addEventListener("input", () => {
  autoGrowPrompt();
  syncNoteChip();
});

dom.prompt.addEventListener("keydown", (event) => {
  // Enter sends; Shift+Enter inserts a newline.
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    submitCurrentPrompt();
  }
});

// Esc is handled at the document level so it also works while focus sits on a
// button inside the card.
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    event.preventDefault();
    // A pending gate owns Esc, and denying is what closing it means.
    if (state.approval) {
      decideApproval(false);
      return;
    }
    // The first Esc stops a running stream; a second one dismisses the window.
    if (state.abort) {
      abortStream();
      return;
    }
    dismiss();
    return;
  }

  // Ctrl+Enter forces a send from anywhere in the window.
  if (event.key === "Enter" && event.ctrlKey) {
    event.preventDefault();
    submitCurrentPrompt();
  }
});

dom.stop.addEventListener("click", abortStream);

dom.copy.addEventListener("click", async () => {
  const text = state.buffer.trim();
  if (!text) return;
  await invoke("write_clipboard", { text });
  const original = dom.copy.textContent;
  dom.copy.textContent = "Copied";
  setTimeout(() => {
    dom.copy.textContent = original;
  }, 1200);
});

dom.pin.addEventListener("click", () => setPinned(!state.pinned));

dom.approvalApprove.addEventListener("click", () => decideApproval(true));
dom.approvalDeny.addEventListener("click", () => decideApproval(false));

dom.captureRemove.addEventListener("click", () => {
  state.capture = null;
  dom.captureThumb.removeAttribute("src");
  syncAttachments();
  focusInput({ selectAll: false });
});

dom.clipboardRemove.addEventListener("click", () => {
  state.clipboard = null;
  syncAttachments();
  focusInput({ selectAll: false });
});

// Links inside the answer open in the real browser, never inside the WebView.
dom.answer.addEventListener("click", (event) => {
  const anchor = event.target.closest("a[data-external]");
  if (!anchor) return;
  event.preventDefault();
  if (IS_TAURI) {
    // The backend validates the URL and hands it to the OS shell; a WebView
    // `window.open` would either be swallowed or open inside the app.
    invoke("open_external_url", { url: anchor.href });
  } else {
    window.open(anchor.href, "_blank", "noopener");
  }
});

/* ==========================================================================
   Backend events
   ========================================================================== */

listen("focus-input", () => {
  focusInput();
  refreshHealth();
});

listen("clipboard-inject", (event) => {
  const text = String(event.payload || "");
  if (!text.trim()) return;
  attachClipboard(text);
  // A short snippet is more useful in the box; a long one becomes context.
  if (text.length <= 200 && !dom.prompt.value.trim()) {
    dom.prompt.value = text;
    autoGrowPrompt();
  }
  focusInput({ selectAll: false });
});

listen("screen-captured", (event) => {
  const payload = event.payload;
  if (!payload || !payload.dataUri) return;
  attachCapture(payload);
  if (!dom.prompt.value.trim()) {
    dom.prompt.value = "What am I looking at?";
  }
  autoGrowPrompt();
  focusInput();
});

listen("quick-note-summon", (event) => {
  const target = String(event.payload || "logseq");
  const prefix = target === "joplin" ? "#joplin " : "#log ";
  // Keep whatever the user had already typed; just arm the destination.
  const existing = dom.prompt.value.trim();
  const { target: current, body } = parseNotePrefix(dom.prompt.value);
  dom.prompt.value = current
    ? `${prefix}${body.trim()}`
    : `${prefix}${existing}`;
  autoGrowPrompt();
  syncNoteChip();
  focusInput({ selectAll: false });
  // Put the caret after the prefix so typing continues the note.
  const caret = dom.prompt.value.length;
  dom.prompt.setSelectionRange(caret, caret);
});

listen("capture-failed", (event) => {
  showError(`Desktop capture failed: ${String(event.payload || "unknown error")}`);
});

listen("health-report", (event) => applyHealth(event.payload));

// `approval-resolved` fires the instant a decision is accepted, ahead of the
// queue re-read that follows it. Closing here as well as on the queue update
// means the card goes away when the button is pressed rather than one round
// trip later — and closing twice is harmless.
listen("approval-resolved", (event) => {
  const resolved = event.payload;
  if (!state.approval) return;
  if (resolved && resolved.id && String(resolved.id) !== state.approval.id) return;
  closeApproval();
  setPhase("done");
  paint({ immediate: true });
});

listen("pin-changed", (event) => {
  state.pinned = Boolean(event.payload);
  dom.pin.setAttribute("aria-pressed", String(state.pinned));
});

/* ==========================================================================
   Boot
   ========================================================================== */

applyRoute(DEFAULT_ROUTE);
syncNoteChip();
autoGrowPrompt();
syncWindowHeight();
refreshHealth();
focusInput();

// One stream, owned by Rust, fanned out to all three surfaces. This window
// subscribes; it does not connect, and it does not poll.
startLink();

let lastConnected = null;
onLink((link) => {
  // The Jarvis dot comes off the stream now. A held-open connection is a
  // stronger liveness signal than a probe that succeeded a moment ago, and it
  // costs nothing.
  const dot = dom.services.querySelector('[data-service="jarvis"]');
  if (dot) {
    dot.dataset.online = String(link.connected);
    dot.title = link.connected
      ? `Jarvis: event stream live${link.activity === "idle" ? "" : ` · ${link.activity}`}`
      : `Jarvis: ${link.error || "no event stream"}`;
  }
  if (!link.connected && state.route.tier !== "offline") {
    applyRoute({ tier: "offline", label: "Offline", model: "core unreachable" });
  } else if (link.connected && state.route.tier === "offline") {
    applyRoute(DEFAULT_ROUTE);
  }

  // Ollama and LiteLLM are not on the bus, so they are re-probed when the link
  // changes state — which is the moment their answer is most likely to differ.
  if (lastConnected !== null && lastConnected !== link.connected) refreshHealth();
  lastConnected = link.connected;

  syncApprovalButtons();
});

onQueue((queue) => {
  const open = queue.items[0] || null;
  if (!open) {
    if (state.approval) {
      // It left the queue: answered here, in the widget, on the phone, or it
      // expired. Either way there is nothing left to decide.
      closeApproval();
      setPhase(state.phase === "approval" ? "done" : state.phase);
      paint({ immediate: true });
    }
    return;
  }
  if (state.approval && state.approval.id === open.id) {
    // Same gate, re-read: `risk` is derived per read and must never be cached
    // against an id, so the card takes the new copy rather than keeping its own.
    openApproval(open);
    return;
  }
  openApproval(open);
});

console.info(
  `[jarvis] spotlight ready - backend ${IS_TAURI ? "connected" : "absent (browser preview)"}`
);
