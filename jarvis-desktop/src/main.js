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
 * Optional shared secret. When the server is started with a token, put the same
 * value here and it travels as `X-Jarvis-Token`. Empty means the header is
 * omitted entirely.
 */
const JARVIS_TOKEN = "";

/** Clipboard context longer than this is trimmed in the attachment chip. */
const CLIPBOARD_PREVIEW = 90;

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
  controller: null,
  startedAt: 0,
  chunks: 0,
  pinned: false,
  /** Pending screen capture, as a JPEG data URI. */
  capture: null,
  /** Pending clipboard context. */
  clipboard: null,
  route: { ...DEFAULT_ROUTE },
};

/** Moves the whole UI into a phase; CSS keys most of its animation off this. */
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

/** Fire-and-forget health probe; the badge and dots update when it lands. */
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

/** Sends the prompt and streams the answer into the card. */
async function send(promptText) {
  const message = promptText.trim();
  if (!message || state.phase === "streaming") return;

  state.inFlight = message;
  state.buffer = "";
  state.chunks = 0;
  state.startedAt = performance.now();
  state.controller = new AbortController();

  setPhase("streaming");
  openCard("Thinking…");
  dom.cursor.hidden = false;
  dom.stop.hidden = false;
  dom.answer.innerHTML = "";
  dom.cardStat.textContent = "";

  // Stay open while the answer streams, even if focus wanders.
  await setPinned(true, { silent: true });

  // The server validates an OpenAI-shaped `messages` array and routes to its
  // vision lane on `has_image`, so clipboard context rides as a system turn
  // rather than a side-channel field.
  const body = {
    messages: [
      ...(state.clipboard
        ? [{ role: "system", content: `Context:\n${state.clipboard}` }]
        : []),
      { role: "user", content: message },
    ],
    has_image: Boolean(state.capture),
    images: state.capture ? [state.capture] : [],
    stream: true,
    auto: true,
    client: "jarvis-desktop",
  };

  const headers = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
    "X-Jarvis-Client": JARVIS_CLIENT_HEADER,
  };
  if (JARVIS_TOKEN) headers["X-Jarvis-Token"] = JARVIS_TOKEN;

  try {
    const response = await fetch(CHAT_ENDPOINT, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: state.controller.signal,
    });

    if (!response.ok) {
      // 400 and 403 are the two the Jarvis server returns for a malformed body
      // and a rejected origin; naming them saves a round trip to the log.
      const hint =
        response.status === 403
          ? " — the server rejected this origin. Add http://tauri.localhost to its ALLOWED_ORIGINS, or confirm X-Jarvis-Token."
          : response.status === 400
            ? " — the server rejected the request body."
            : "";
      throw new Error(
        `the server answered HTTP ${response.status} ${response.statusText}${hint}`
      );
    }

    dom.cardStatusText.textContent = "Streaming";

    // A server that ignores `stream: true` just returns one JSON document.
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

      // SSE frames are separated by a blank line, NDJSON by a single newline.
      // Splitting on newlines handles both, because `consumeLine` ignores the
      // blank separator.
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

/** Common teardown for every way a stream can end. */
function finishStream(phase, statusText) {
  state.controller = null;
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
  if (state.controller) {
    state.controller.abort();
    state.controller = null;
  }
  dom.prompt.value = "";
  autoGrowPrompt();
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
  const value = dom.prompt.value;
  if (!value.trim()) return;
  dom.prompt.value = "";
  autoGrowPrompt();
  send(value);
}

/* ==========================================================================
   Event wiring
   ========================================================================== */

dom.prompt.addEventListener("input", autoGrowPrompt);

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
    // The first Esc stops a running stream; a second one dismisses the window.
    if (state.controller) {
      state.controller.abort();
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

dom.stop.addEventListener("click", () => {
  if (state.controller) state.controller.abort();
});

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
  if (TAURI && TAURI.opener && TAURI.opener.openUrl) {
    TAURI.opener
      .openUrl(anchor.href)
      .catch((error) => console.error("[jarvis] unable to open link:", error));
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

listen("capture-failed", (event) => {
  showError(`Desktop capture failed: ${String(event.payload || "unknown error")}`);
});

listen("health-report", (event) => applyHealth(event.payload));

listen("pin-changed", (event) => {
  state.pinned = Boolean(event.payload);
  dom.pin.setAttribute("aria-pressed", String(state.pinned));
});

/* ==========================================================================
   Boot
   ========================================================================== */

applyRoute(DEFAULT_ROUTE);
autoGrowPrompt();
syncWindowHeight();
refreshHealth();
focusInput();

// Re-probe the services periodically so the footer dots stay honest while the
// window sits open.
setInterval(() => {
  if (state.phase !== "streaming") refreshHealth();
}, 30000);

console.info(
  `[jarvis] spotlight ready - backend ${IS_TAURI ? "connected" : "absent (browser preview)"}`
);
