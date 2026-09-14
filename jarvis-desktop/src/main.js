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
  currentQueue,
  decide as decideOnBackend,
  fetchDigest,
  markDigestSeen,
  onLink,
  onQueue,
  riskLine,
  setMuted,
  followTheme,
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
  approvalCount: $("approval-count"),
  parked: $("parked"),
  parkedText: $("parked-text"),
  parkedShow: $("parked-show"),
  approvalRaised: $("approval-raised"),
  raisedChip: $("raised-chip"),
  raisedSource: $("raised-source"),
  raisedQuote: $("raised-quote"),
  raisedContextWrap: $("raised-context-wrap"),
  raisedContext: $("raised-context"),

  attention: $("attention"),
  attentionCount: $("attention-count"),
  attentionBudget: $("attention-budget"),
  attentionMute: $("attention-mute"),
  attentionClose: $("attention-close"),
  attentionNote: $("attention-note"),
  digest: $("digest"),
  digestSeen: $("digest-seen"),

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
  /** The id of the gate a decision was sent for, so it cannot be sent twice. */
  decided: null,
  /** Gate ids the user put away with Esc. Still pending; just not on screen. */
  parked: new Set(),
  /** The digest as last read, in the server's order. Never re-sorted. */
  digest: null,
  /**
   * Three states, not two. `null` is "the user has not said" — the panel
   * follows the count. `true` is "opened deliberately". `false` is "dismissed",
   * and it survives until the count goes UP.
   *
   * A boolean was the bug: `attentionOpen || pending > 0` re-showed the panel
   * within milliseconds of Close, because `same_link` includes `last_id` and
   * the stream republishes the link on every event that carries one. Close did
   * nothing, and the panel landed back on top of any gate opened from it.
   */
  attentionOpen: null,
  /** The pending count when the panel was dismissed, so a NEW item re-arms it. */
  attentionDismissedAt: 0,
  /** True while a digest read is in flight, so a repaint cannot stack them. */
  digestLoading: false,
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

  // Placeholders carry a per-call nonce. A fixed `@@JARVISCODE0@@` was
  // predictable, so model output containing that literal string was
  // substituted with an unrelated code span — or with `<code>undefined</code>`
  // when the index did not exist. Not an escape, but not what the model wrote.
  const nonce = Math.random().toString(36).slice(2, 10);

  // Inline code is lifted out first so its contents survive the emphasis
  // passes untouched, then restored at the end.
  const codeSpans = [];
  out = out.replace(/`([^`\n]+)`/g, (_match, code) => {
    codeSpans.push(code);
    return `@@C${nonce}${codeSpans.length - 1}@@`;
  });

  // URLs are lifted out for the same reason, and for a sharper one: `__` and
  // `*` inside a URL used to be rewritten as emphasis BEFORE linkification saw
  // them, so `https://x.com/a__b__c` yielded href="https://x.com/a" — a
  // different but perfectly valid URL. That href is what `open_external_url`
  // hands to the OS shell, so a link could point somewhere the text did not
  // say. Stashing the destination first makes the emphasis passes blind to it.
  const urls = [];
  const stash = (url) => {
    urls.push(url);
    return `@@U${nonce}${urls.length - 1}@@`;
  };
  out = out
    .replace(
      /(\[[^\]]*\]\()(https?:\/\/[^\s)]+)(\))/g,
      (_match, open, url, close) => open + stash(url) + close
    )
    .replace(
      /(^|[\s(])(https?:\/\/[^\s<)]+)/g,
      (_match, lead, url) => lead + stash(url)
    );

  // Strong runs first and non-greedily, so `**bold *italic* tail**` keeps its
  // inner emphasis instead of failing to match on the nested asterisks. The
  // italic pass then only sees the leftover single delimiters. `(?!\s)` keeps
  // arithmetic like `a * b * c` from turning into emphasis.
  out = out
    .replace(/\*\*\*([\s\S]+?)\*\*\*/g, "<strong><em>$1</em></strong>")
    .replace(/\*\*([\s\S]+?)\*\*/g, "<strong>$1</strong>")
    // `__` needs word boundaries or it eats identifiers: `user__name__id` used
    // to render as `user<strong>name</strong>id`.
    .replace(/(^|[^\w])__([\s\S]+?)__(?!\w)/g, "$1<strong>$2</strong>")
    .replace(/(^|[^*\w])\*(?!\s)([^*\n]+?)\*/g, "$1<em>$2</em>")
    .replace(/~~([\s\S]+?)~~/g, "<s>$1</s>");

  // Only http(s) links are linkified; anything else stays plain text so model
  // output can never produce a `javascript:` or `file:` href.
  const urlPattern = new RegExp(`@@U${nonce}(\\d+)@@`, "g");
  out = out
    .replace(
      new RegExp(`\\[([^\\]]+)\\]\\(@@U${nonce}(\\d+)@@\\)`, "g"),
      (_match, label, index) =>
        `<a href="${urls[Number(index)]}" data-external="true">${label}</a>`
    )
    .replace(urlPattern, (_match, index) => {
      const url = urls[Number(index)];
      return `<a href="${url}" data-external="true">${url}</a>`;
    });

  out = out.replace(
    new RegExp(`@@C${nonce}(\\d+)@@`, "g"),
    (_match, index) => `<code>${codeSpans[Number(index)]}</code>`
  );

  return out;
}


/** Block-level renderer: fences, headings, lists, quotes, rules, tables. */
function renderMarkdown(source) {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const html = [];

  let index = 0;
  // Every branch below must consume at least one line. This is the guarantee
  // that it does, rather than a promise that it does: an iteration that
  // consumes nothing is an infinite loop, and `renderMarkdown` runs on every
  // streamed token in a frameless always-on-top window. If a future edit ever
  // reintroduces a line that matches no branch, it is rendered as text and the
  // parser moves on.
  let previous = -1;
  while (index < lines.length) {
    if (index === previous) {
      html.push(`<p>${renderInline(lines[index].trim())}</p>`);
      index += 1;
      continue;
    }
    previous = index;

    const line = lines[index];

    // Fenced code - also handles the unterminated fence of a live stream.
    //
    // The opening fence accepts ANY info string, and three OR MORE markers of
    // either kind. It used to demand a bare `[\w+-]*` language and exactly
    // three backticks, which meant "```c#", "``` js", "````", "~~~" and
    // '```js title="a.js"' matched neither this branch nor the paragraph
    // branch below - whose guard excludes every line starting with a fence.
    // `index` then never advanced and the loop spun for ever, freezing a
    // window that has no titlebar and no taskbar entry. A model writing a C#
    // snippet was enough to trigger it, on every streamed token.
    const fence = line.match(/^\s*(`{3,}|~{3,})\s*([^`]*)$/);
    if (fence) {
      // Only the first word of the info string is the language; CommonMark
      // lets the rest be anything and highlighters ignore it.
      const info = (fence[2].trim().split(/\s+/)[0] || "").replace(
        /[^\w+#.-]/g,
        ""
      );
      const language = info ? ` class="language-${escapeHtml(info)}"` : "";
      // A fence closes only on the same marker, at least as long. Otherwise
      // "````" inside a ``` block would end it early.
      const marker = fence[1][0];
      const closer = new RegExp(`^\\s*${marker}{${fence[1].length},}\\s*$`);
      const body = [];
      index += 1;
      while (index < lines.length && !closer.test(lines[index])) {
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
      !/^\s*(#{1,4}\s|>|`{3,}|~{3,}|[-*+]\s|\d+[.)]\s)/.test(lines[index])
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
/**
 * How often the answer is re-rendered while tokens are arriving.
 *
 * Every paint re-parses the WHOLE buffer and rebuilds the whole answer subtree,
 * so the cost is quadratic in the length of the answer. At one paint per frame
 * a thirty-second reply parsed its own text about eighteen hundred times, and
 * the last of those frames were parsing tens of kilobytes each — in an
 * always-on-top transparent window that is also resizing itself.
 *
 * 100ms is under the ~150ms at which text stops feeling live, and it cuts the
 * parse count roughly sixfold. It also fixes the `.fresh` animation below,
 * which could never complete at frame rate.
 */
const STREAM_PAINT_MS = 100;
let lastPaintAt = 0;
/** How many blocks the answer had last paint, so `.fresh` fires once each. */
let paintedBlocks = 0;

function paint({ immediate = false } = {}) {
  if (paintQueued && !immediate) return;
  if (!immediate && state.phase === "streaming") {
    const now = performance.now();
    if (now - lastPaintAt < STREAM_PAINT_MS) return;
  }
  paintQueued = true;

  requestAnimationFrame(() => {
    paintQueued = false;
    lastPaintAt = performance.now();

    dom.answer.innerHTML = renderMarkdown(state.buffer);
    // `.fresh` marks a block that has just appeared. It used to be added to
    // `lastElementChild` on every paint — but `innerHTML` destroys and
    // recreates that element each time, so the 260ms animation restarted every
    // frame and never finished: the trailing paragraph sat permanently near
    // opacity 0, flickering. Marking only when the block COUNT rises means a
    // block animates once, when it first exists.
    const blocks = dom.answer.childElementCount;
    const last = dom.answer.lastElementChild;
    if (last && state.phase === "streaming" && blocks > paintedBlocks) {
      last.classList.add("fresh");
    }
    paintedBlocks = blocks;

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
  paintedBlocks = 0;
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
  refreshApproval(approval);
  setPhase("approval");

  if (!dom.card.hidden) dom.cardStatusText.textContent = "Paused for approval";

  // The window, yes. The keyboard, no.
  //
  // Focus stays where the user put it. Moving it onto Approve is what turned a
  // stray Enter into an approval, and there is no version of "helpfully focus
  // the destructive button" that is safe on a surface that appears by itself.
  // The gate is announced instead: `role="alertdialog"` with `aria-live` on the
  // section carries it to a screen reader without stealing anything.
  setPinned(true, { silent: true });
  if (!dom.prompt.value.trim() && document.activeElement !== dom.prompt) {
    // Nothing half-typed and the composer is not where the user is looking:
    // put focus on the gate itself, not on either button, so Tab reaches the
    // buttons and Enter does nothing.
    dom.approval.focus({ preventScroll: true });
  }
  syncWindowHeight();
}

/** Paints a gate's contents without touching focus, pinning or the phase. */
function refreshApproval(approval) {
  state.approval = approval;

  dom.approvalAction.textContent = approval.action;
  const target = approval.detail && typeof approval.detail === "object"
    ? approval.detail.target || approval.detail.note_target || approval.detail.to
    : null;
  dom.approvalTarget.hidden = !target;
  if (target) dom.approvalTarget.textContent = String(target);

  renderRaised(approval.raised);

  dom.approvalPreview.innerHTML = renderMarkdown(approvalPreview(approval));
  decorateDiff(dom.approvalPreview);

  // The risk line is the whole reason the gate is worth showing rather than
  // merely enforcing: `switch_model` and `send_email` are both tier `ask` and
  // arrive looking identical until this is on screen.
  // The risk line, plus what Esc does now — years of muscle memory say Esc
  // dismisses a window, and until this change it denied an action instead.
  dom.approvalHint.textContent = `${riskLine(approval.risk)} · Esc puts it aside`;
  dom.approvalHint.dataset.reversible = approval.risk
    ? approval.risk.reversible
    : "no";
  dom.approvalHint.dataset.reach = approval.risk ? approval.risk.reach : "outbound";

  const queue = currentQueue();
  const index = queue.items.findIndex((item) => item.id === approval.id);
  dom.approvalCount.hidden = queue.items.length < 2;
  if (queue.items.length > 1 && index >= 0) {
    dom.approvalCount.textContent = `${index + 1} of ${queue.items.length}`;
  }

  syncApprovalButtons();
  dom.approval.hidden = false;
  syncWindowHeight();
}

/* ==========================================================================
   Attention: the interruption budget and the daily brief
   --------------------------------------------------------------------------
   Two counts live near each other here and they must not be confused.

     link.approvals            things waiting for a DECISION — the gate queue
     link.attention.pending    things waiting to be TOLD to you — the digest

   The second is the tray badge and the notch count on the reactor's rim. A
   finished job adds to it and makes no sound, which is the whole point of the
   budget: the code path that finishes a job is not the code path that checks
   whether Jarvis may speak.
   ========================================================================== */

/** Paints the panel from the link, and opens or closes it as the count moves. */
function syncAttention() {
  const a = currentLink().attention;

  // Nothing has been read yet — say so rather than showing a confident zero
  // over a digest that was never fetched.
  if (!a.known) {
    dom.attention.hidden = true;
    return;
  }

  // Re-arm when something new arrives, so dismissing is not permanent.
  if (state.attentionOpen === false && a.pending > state.attentionDismissedAt) {
    state.attentionOpen = null;
  }
  const visible =
    state.attentionOpen === true ||
    (state.attentionOpen === null && a.pending > 0);
  const wasHidden = dom.attention.hidden;
  dom.attention.hidden = !visible;
  if (!visible) {
    state.digest = null;
    syncWindowHeight();
    return;
  }

  dom.attentionCount.textContent =
    a.pending === 0
      ? "Nothing waiting"
      : a.pending === 1
        ? "1 thing waiting to be told"
        : `${a.pending} things waiting to be told`;

  // Why nothing is being said out loud, when nothing is. `blockedBy` is the
  // server's own words — Quiet, Standby, a locked session, or muted — and it
  // outranks the count, because a budget with three left and a locked session
  // is still a budget of zero.
  dom.attentionBudget.textContent = a.blockedBy
    ? `Silent — ${a.blockedBy}`
    : `${a.remaining} of ${a.limit} spoken interruptions left today`;
  dom.attention.dataset.banked = String(a.banked);

  // Worded with its end date in both directions. There is no mute without one.
  dom.attentionMute.textContent = a.muted
    ? "Unmute"
    : "Mute until tomorrow";
  dom.attentionMute.title = a.muted
    ? "Let Jarvis speak again today"
    : "Jarvis stays silent until tomorrow. There is no mute without an end.";

  if (wasHidden || state.digest === null) loadDigest();
  syncWindowHeight();
}

/** Reads the brief. Called when the panel opens and when the count moves. */
async function loadDigest() {
  if (state.digestLoading) return;
  state.digestLoading = true;
  try {
    const brief = await fetchDigest();
    // `{"available": false}` means the arbiter is not installed. §7 says hide
    // the UI for a false capability rather than show an empty one.
    if (brief && brief.available === false) {
      state.digest = { items: [], unavailable: true };
    } else {
      state.digest = brief || { items: [] };
    }
  } catch (error) {
    console.error("[jarvis] digest unavailable:", error);
    state.digest = { items: [], error: String(error.message || error) };
  } finally {
    state.digestLoading = false;
    renderDigest();
  }
}

/**
 * Renders the brief in the order it arrived.
 *
 * **Nothing here sorts.** `jarvis_arbiter._rank` orders by what kind of thing
 * an item is and then by a priority its producer set — deliberately never by
 * urgency, because an item that could move itself up the list by saying it was
 * urgent would implement the attack `jarvis_content_risk` exists to catch. A
 * client that re-sorted would hand that ranking back to whoever wrote the text.
 */
function renderDigest() {
  const brief = state.digest;
  dom.digest.replaceChildren();

  if (!brief || brief.unavailable) {
    dom.attentionNote.textContent = brief
      ? "The digest is not available on this backend."
      : "Reading the brief…";
    dom.digestSeen.hidden = true;
    syncWindowHeight();
    return;
  }
  if (brief.error) {
    dom.attentionNote.textContent = brief.error;
    dom.digestSeen.hidden = true;
    syncWindowHeight();
    return;
  }

  const items = Array.isArray(brief.items) ? brief.items : [];
  for (const item of items) {
    dom.digest.append(digestRow(item));
  }

  const shown = items.length;
  const total = Number(brief.count || shown);
  dom.attentionNote.textContent =
    shown === 0
      ? "Nothing in the brief."
      : total > shown
        ? `Showing ${shown} of ${total}. Marking read approves nothing.`
        : "Marking read approves nothing.";
  dom.digestSeen.hidden = shown === 0;
  syncWindowHeight();
}

/**
 * One row of the brief.
 *
 * An approval row arrives with `opens_card: true` and an empty body — the
 * server deliberately does not send the detail here, and there is no route
 * that decides one from the digest. So the row is a link into the gate, not a
 * decision. This is also why there is no select-all, no bulk action and no
 * approve-all anywhere on this panel: if a decision is worth a gate, it is
 * worth one tap each, and batching is how a gesture stops being a decision.
 */
function digestRow(item) {
  const li = document.createElement("li");
  li.className = "digest-row";
  li.dataset.kind = String(item.kind || "note");
  li.dataset.priority = String(item.priority || "normal");

  const head = document.createElement("div");
  head.className = "digest-head";

  const kind = document.createElement("span");
  kind.className = "digest-kind";
  kind.textContent = String(item.kind || "note");
  head.append(kind);

  const title = document.createElement("span");
  title.className = "digest-title";
  title.textContent = String(item.title || "(untitled)");
  head.append(title);

  if (item.source) {
    const source = document.createElement("span");
    source.className = "digest-source";
    source.textContent = String(item.source);
    head.append(source);
  }
  li.append(head);

  if (item.opens_card) {
    // Not a decision — a way to reach the one place a decision can be made.
    const open = document.createElement("button");
    open.type = "button";
    open.className = "text-button digest-open";
    open.textContent = "Open the approval";
    open.addEventListener("click", () => openDigestApproval(item));
    li.append(open);
  } else if (item.body) {
    const body = document.createElement("p");
    body.className = "digest-body";
    body.textContent = String(item.body);
    li.append(body);
  }

  return li;
}

/**
 * Opens the gate for a digest row.
 *
 * The digest's `ref` is the approval id. The card is rendered from the *queue*
 * rather than from the digest row, because the queue is where `risk` and
 * `raised` live — the digest carries neither, on purpose. If the item is no
 * longer in the queue it has already been answered, and saying so is better
 * than opening an empty card.
 */
function openDigestApproval(item) {
  const id = String(item.ref || item.id || "");
  const match = currentQueue().items.find((row) => row.id === id);
  if (!match) {
    dom.attentionNote.textContent =
      "That one has already been answered — it will drop off the brief.";
    return;
  }
  // Same as Close: dismissed until the count rises, so the panel cannot land
  // back on top of the gate it just opened.
  state.attentionOpen = false;
  state.attentionDismissedAt = currentLink().attention.pending;
  dom.attention.hidden = true;
  openApproval(match);
}

/** Mutes or unmutes, then lets the refreshed link repaint the panel. */
async function toggleMute() {
  const a = currentLink().attention;
  dom.attentionMute.disabled = true;
  try {
    await setMuted(!a.muted);
  } catch (error) {
    console.error("[jarvis] mute failed:", error);
    dom.attentionNote.textContent = String(error.message || error);
  } finally {
    dom.attentionMute.disabled = false;
  }
}

/**
 * Marks the whole brief read.
 *
 * **This approves nothing**, and the button says so next to it. The server's
 * `mark_digest_delivered` stamps a delivery time; every approval in the brief
 * is still pending afterwards and still needs its own card.
 */
async function markBriefRead() {
  dom.digestSeen.disabled = true;
  try {
    await markDigestSeen([]);
    state.digest = null;
  } catch (error) {
    console.error("[jarvis] marking the digest read failed:", error);
    dom.attentionNote.textContent = String(error.message || error);
  } finally {
    dom.digestSeen.disabled = false;
  }
}

/**
 * Renders `raised` — the reason this is on screen at all.
 *
 * Four rules from JARVIS-API §4, and each one is a decision rather than a
 * style:
 *
 * - `text` is a chip. It already carries "(4th time today)" when the source has
 *   tripped this repeatedly; nothing here counts anything, because the count is
 *   the server's and a client that recounted would drift.
 * - `quote` goes inline, in quotation marks. Those are the attacker's words and
 *   showing them is the entire point — a card that said "this looked suspicious"
 *   teaches nothing.
 * - `context` is text from the page or document being judged, so it is never
 *   shown without the user asking. Hence a closed `<details>`, collapsed again
 *   on every render so the previous card's disclosure does not carry over.
 * - `source` is named, never quoted. It is an identifier the server chose, not
 *   content, and quoting it would suggest otherwise.
 *
 * All three strings go in through `textContent`. They are hostile text by
 * definition; the markdown renderer never sees them.
 *
 * There is deliberately no control here that clears the latch. It lasts ten
 * minutes, and the alternative is a button whose whole purpose is to undo a
 * safety rule under time pressure.
 */
function renderRaised(raised) {
  if (!raised) {
    dom.approvalRaised.hidden = true;
    dom.raisedChip.textContent = "";
    dom.raisedQuote.textContent = "";
    dom.raisedContext.textContent = "";
    return;
  }

  dom.raisedChip.textContent = raised.text || "This text tried to rush you";
  dom.raisedChip.dataset.code = raised.code || "rushed";

  dom.raisedSource.textContent = raised.source ? `from ${raised.source}` : "";
  dom.raisedSource.hidden = !raised.source;

  // Quoted with real quotation marks rather than a CSS pseudo-element, so the
  // words stay quoted when the card is copied or read by a screen reader.
  dom.raisedQuote.textContent = raised.quote ? `“${raised.quote}”` : "";
  dom.raisedQuote.hidden = !raised.quote;

  dom.raisedContext.textContent = raised.context || "";
  dom.raisedContextWrap.hidden = !raised.context;
  dom.raisedContextWrap.open = false;

  // The tier move, when the server reported one. It is the concrete fact —
  // "this would not have asked you at all" — and it is what makes the chip
  // more than a warning label.
  if (raised.fromTier && raised.toTier && raised.fromTier !== raised.toTier) {
    dom.approvalRaised.dataset.tiers = `${raised.fromTier} → ${raised.toTier}`;
  } else {
    delete dom.approvalRaised.dataset.tiers;
  }

  dom.approvalRaised.hidden = false;
}

/**
 * Puts the gate away without answering it.
 *
 * The item stays pending and stays counted; only this window stops showing it,
 * until the user asks for it back or a different one arrives. Without the
 * parked set the queue subscription would reopen it on the next event, which
 * is what made Esc feel like it did nothing.
 */
function parkApproval() {
  if (!state.approval) return;
  state.parked.add(state.approval.id);
  closeApproval();
  syncParkedBar();
  focusInput({ selectAll: false });
}

/**
 * The one-line reminder that something is still waiting after it was parked.
 *
 * Parking must not be a way to lose an approval. This is deliberately not a
 * decision surface — it is a way back to the card.
 */
function syncParkedBar() {
  const queue = currentQueue();
  const waiting = queue.items.filter((item) => state.parked.has(item.id));
  const hidden = Boolean(state.approval) || waiting.length === 0;
  dom.parked.hidden = hidden;
  if (hidden) {
    syncWindowHeight();
    return;
  }
  dom.parkedText.textContent =
    waiting.length === 1
      ? "1 approval is still waiting."
      : `${waiting.length} approvals are still waiting.`;
  syncWindowHeight();
}

/** Clears the gate. Called when it leaves the queue, however it left. */
function closeApproval() {
  state.approval = null;
  state.decided = null;
  dom.approval.hidden = true;
  dom.approvalPreview.innerHTML = "";
  renderRaised(null);
  // The pin was taken to hold the window open for the gate. Every path that
  // ends a gate has to give it back, not only the one where the user answered
  // here: an approval resolved on the phone used to leave a 750px always-on-top
  // window floating over everything until it was clicked and dismissed.
  if (!state.abort && !state.inFlight) setPinned(false, { silent: true });
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
  // `deciding` is released in `finally`, but the card only closes when the
  // backend broadcasts the resolution - so between those two moments a second
  // Ctrl+Enter used to send the same decision again. The id latch closes that
  // window; it is cleared when a different gate opens.
  if (state.decided === approval.id) return;

  state.decided = approval.id;
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
      // This used to stop here. Every `finishStream` call site is guarded by
      // `if (settled) return`, so a stream that ended with its own terminator
      // - which is every stream, the server proxies OpenAI-style
      // `data: [DONE]` - left the card in the `streaming` phase for ever: the
      // window never un-pinned, Escape aborted instead of dismissing, and the
      // re-entrancy guard in `send()` then silently discarded every prompt
      // after the first. Only the Stop button and a stream with no terminator
      // ever finished. `streamViaFetch` always did this correctly, which is
      // why browser preview never showed it.
      finishStream(state.phase === "error" ? "error" : "done");
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
        stream: true,
        auto: payload.auto,
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
  if (!message) return;
  // Guard on the live stream handle, not on the phase. The phase is moved to
  // `approval` and then `done` by the approval flow while the stream is still
  // open, so a phase check let a second `stream_chat` start alongside the
  // first - two channels writing into one buffer, and `state.abort` pointing
  // only at the newer one, so Stop could never reach the older.
  // `state.abort` is only assigned once the transport starts, and `send` has
  // an `await` before then, so the handle alone is not a synchronous latch.
  // `inFlight` is - it is set on the same tick as the guard, and cleared in
  // `finishStream`, which is the single funnel every ending passes through.
  if (state.abort || state.inFlight) return;
  state.inFlight = message;

  // An answered gate belongs to the turn that is ending, not the next one.
  if (state.approval) closeApproval();

  state.buffer = "";
  state.chunks = 0;
  // A new answer starts from no blocks, or the first paragraph of the second
  // reply never gets its entrance.
  paintedBlocks = 0;
  lastPaintAt = 0;
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
  // from the text and restated as a system turn. There used to be a
  // `note_target` field alongside it — the server has never read one, so the
  // system turn was always the only mechanism doing any work.
  const { target: noteTarget, body } = parseNotePrefix(message);
  const text = noteTarget ? body.trim() : message;

  // A capture rides INSIDE the user message, not as a sibling `images` array.
  // The server forwards `messages` verbatim to /v1/chat/completions and reads
  // no `images` field anywhere, so the old shape sent the screenshot into a
  // void while `has_image` still routed the turn to a vision model.
  const content = state.capture
    ? [
        { type: "text", text },
        { type: "image_url", image_url: { url: state.capture } },
      ]
    : text;

  // Clipboard context rides as a system turn; the server validates an
  // OpenAI-shaped `messages` array and routes on `has_image`.
  const payload = {
    messages: [
      ...(noteTarget ? [{ role: "system", content: NOTE_INSTRUCTIONS[noteTarget] }] : []),
      ...(state.clipboard
        ? [{ role: "system", content: `Context:\n${state.clipboard}` }]
        : []),
      { role: "user", content },
    ],
    hasImage: Boolean(state.capture),
    auto: true,
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
  state.inFlight = null;
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
  // Enter does NOT approve, and the comment that used to sit here claimed the
  // opposite of what the code did — "the safe thing must be the deliberate
  // thing" above a call to `decideApproval(true)`.
  //
  // The failure it caused: a gate arrives while you are mid-sentence, the old
  // `openApproval` moved focus onto Approve, and the Enter you were about to
  // press to send your prompt approved an action you had not read. Chromium
  // fires `click` on keydown for a focused button, so there was no gap to
  // notice it in.
  //
  // Approving now takes the Approve button — reachable by Tab, and Enter works
  // on it natively once it is focused, which is a deliberate act rather than a
  // reflex. `quickActionable()` in jarvis-link.js is the gate any faster path
  // must go through, and it refuses anything carrying `raised`.
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
    // Esc parks the gate; it does not deny it. In a spotlight overlay Esc means
    // "close this", and wiring the most reflexive key in the app to a decision
    // meant people answered a gate believing they had dismissed a window.
    //
    // Parking keeps the item in the queue — it is still pending, the tray still
    // counts it, and the bar below says so — but stops it reopening over
    // whatever the user does next. Denying takes the Deny button.
    if (state.approval) {
      parkApproval();
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

// Links open in the real browser, never inside the WebView.
//
// Bound to the shell rather than to `#answer`: the approval preview renders
// model-authored text through the same linkifier, and a click there was a real
// navigation that took the window off index.html with no way back - the app
// was gone until relaunch.
document.addEventListener("click", (event) => {
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
followTheme();
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
  syncAttention();
});

onQueue((queue) => {
  // Anything answered elsewhere stops being parked — the set must not grow for
  // ever, and an id that has left the queue is not waiting for anything.
  const live = new Set(queue.items.map((item) => item.id));
  for (const id of [...state.parked]) if (!live.has(id)) state.parked.delete(id);

  const open = queue.items.find((item) => !state.parked.has(item.id)) || null;
  syncParkedBar();
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
  // A re-read of the same gate must refresh it in place, not reopen it.
  // These two branches used to be the identical statement - the `if` was dead
  // code - so every queue re-read stole focus from the input mid-typing and
  // re-pinned the window, and a stale read that still carried an already
  // answered id put its card back with live buttons.
  const same = state.approval && state.approval.id === open.id;
  if (same) {
    // `risk` is derived per read and must never be cached against an id, so
    // the card takes the new copy - but quietly. `raised` is stored on the
    // row rather than derived, but it is re-read here for the same reason:
    // one source, every time.
    refreshApproval(open);
    return;
  }
  if (state.decided === open.id) {
    // Answered here; the resolution broadcast just has not landed yet.
    return;
  }
  openApproval(open);
});

dom.parkedShow.addEventListener("click", () => {
  const next = currentQueue().items.find((item) => state.parked.has(item.id));
  if (!next) return;
  state.parked.delete(next.id);
  openApproval(next);
  syncParkedBar();
});

dom.attentionMute.addEventListener("click", toggleMute);
dom.digestSeen.addEventListener("click", markBriefRead);
dom.attentionClose.addEventListener("click", () => {
  // Closing hides the panel until something new arrives or the tray asks for
  // it again. It does not mark anything read: those are different actions and
  // conflating them would silently clear a brief nobody looked at.
  state.attentionOpen = false;
  state.attentionDismissedAt = currentLink().attention.pending;
  dom.attention.hidden = true;
  syncWindowHeight();
});

// The tray's approvals row opens the gate here rather than in the HUD: this is
// the surface that renders the risk line and the `raised` block.
if (IS_TAURI) {
  TAURI.event.listen("show-approval", () => {
    const queue = currentQueue();
    const next = queue.items[0];
    if (!next) return;
    state.parked.delete(next.id);
    openApproval(next);
    syncParkedBar();
  });
}

// The tray's "N things waiting" row and the widget both open the brief here.
if (IS_TAURI) {
  TAURI.event.listen("show-digest", () => {
    state.attentionOpen = true;
    state.digest = null;
    syncAttention();
  });
}

console.info(
  `[jarvis] spotlight ready - backend ${IS_TAURI ? "connected" : "absent (browser preview)"}`
);
