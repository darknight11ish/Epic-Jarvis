/*
 * Pure protocol helpers for the Jarvis notes bridge plugin.
 *
 * Everything in this file is plain data in / plain data out: no `obsidian`
 * import, no network, no DOM. That is what makes it testable with plain
 * `node --test` (see `tests/protocol.test.mjs`), and it is the only place that
 * knows how a Jarvis answer maps to words on the screen.
 *
 * SAFETY: no function here ever logs, prints or returns the token. The token
 * only ever travels in the header built by `buildHeaders`.
 */
import type {
  CaptureOutcome,
  ChatOutcome,
  HeadingRef,
  NoteContext,
  RawAnswer,
  ReadOutcome,
  TemplateListOutcome,
  WriteKind,
  WriteOutcome,
} from "./types";

/** The local backend address. The plugin talks to this PC only by default. */
export const DEFAULT_BACKEND = "http://127.0.0.1:4719";

/** How much note text is sent with one read-only ask. */
export const MAX_CONTEXT_CHARS = 12000;

/** How much selected text is sent with one read-only ask (a second, separate bound). */
export const MAX_SELECTION_CHARS = 12000;

/** Bounds for the panel's context lists, so a huge vault cannot flood the panel. */
export const MAX_HEADINGS = 80;
export const MAX_LINKS = 80;
export const MAX_FRONTMATTER_KEYS = 60;

/** The route paths the plugin is allowed to call. Every write is a backend one-card route. */
export const ROUTES = {
  chat: "/api/chat",
  capture: "/api/notes/capture",
  captureStatus: "/api/notes/capture",
  read: "/api/notes/read",
  templates: "/api/notes/templates",
  insert: "/api/notes/insert",
  format: "/api/notes/format",
  replace: "/api/notes/replace",
  customize: "/api/notes/customize",
  tag: "/api/notes/tag",
  create: "/api/notes/create",
  change: "/api/notes/change",
} as const;

/** What the plugin says when the PC backend cannot be reached at all. */
export const UNREACHABLE_MESSAGE =
  "Could not reach the local Jarvis. Is the desktop Jarvis running on this PC?";

/** What the plugin says while a card waits: the card is never answered here. */
export const WAITING_CARD_MESSAGE =
  "A card is waiting on the PC. This plugin cannot approve cards: answer it in the Jarvis window on the PC.";

/** How long the panel keeps checking one waiting card before it stops (10 minutes). */
export const POLL_MAX_ATTEMPTS = 240;

/** A typed error with a stable kind, so the client can tell "unreadable" from "no token". */
export class ProtocolError extends Error {
  readonly kind: "unreadable" | "no-token" | "invalid";

  constructor(message: string, kind: "unreadable" | "no-token" | "invalid" = "unreadable") {
    super(message);
    this.name = "ProtocolError";
    this.kind = kind;
  }
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function object(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

/** Trim a backend URL and drop trailing slashes. Empty input means the local default. */
export function normalizeBackendUrl(raw: string): string {
  const trimmed = (raw ?? "").trim();
  if (!trimmed) return DEFAULT_BACKEND;
  return trimmed.replace(/\/+$/, "");
}

/** True when a URL points at this machine (the only default this plugin should use). */
export function isLoopbackUrl(raw: string): boolean {
  // Bracketed IPv6 hosts are matched whole (http://[::1]:4719), everything else
  // up to the first colon or slash.
  const match = /^https?:\/\/(\[[^\]]+\]|[^/:]+)/i.exec((raw ?? "").trim());
  if (!match) return false;
  const host = match[1].toLowerCase().replace(/^\[|\]$/g, "");
  return host === "127.0.0.1" || host === "localhost" || host === "::1";
}

/** Build one URL: base + route path + optional query. Values are URL-encoded. */
export function buildUrl(
  base: string,
  route: string,
  query?: Record<string, string>,
): string {
  const cleanBase = normalizeBackendUrl(base);
  const cleanRoute = route.startsWith("/") ? route : "/" + route;
  if (!query) return cleanBase + cleanRoute;
  const pairs: string[] = [];
  for (const key of Object.keys(query)) {
    const value = query[key];
    if (value === undefined || value === null) continue;
    pairs.push(encodeURIComponent(key) + "=" + encodeURIComponent(value));
  }
  return pairs.length ? cleanBase + cleanRoute + "?" + pairs.join("&") : cleanBase + cleanRoute;
}

/**
 * The four headers every request carries. `X-Jarvis-Client: hud` is the
 * project's standing rule, and `X-Jarvis-Surface: desktop` says which surface
 * asked. The token is a header value only - never a URL, never a log line.
 */
export function buildHeaders(token: string): Record<string, string> {
  return {
    "Content-Type": "application/json",
    "X-Jarvis-Token": token,
    "X-Jarvis-Client": "hud",
    "X-Jarvis-Surface": "desktop",
  };
}

/** Read a name out of the settings/secret pair, refusing a blank token early. */
export function requireToken(token: string): string {
  const value = (token ?? "").trim();
  if (!value) {
    throw new ProtocolError(
      "No Jarvis token yet. Open Settings -> Jarvis notes bridge and either pick a SecretStorage secret or paste the token into the fallback field.",
      "no-token",
    );
  }
  return value;
}

function tryParseJson(value: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(value);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
    return parsed as Record<string, unknown>;
  } catch {
    return null;
  }
}

/**
 * Get the JSON object out of an answer. `requestUrl`'s `json` getter throws on
 * bad JSON and returns `undefined` for an empty body, so the raw text is the
 * fallback. An answer that is not a JSON object is an `unreadable` error.
 */
export function parseJsonBody(raw: RawAnswer): Record<string, unknown> {
  let fromGetter: unknown;
  try {
    fromGetter = raw.json;
  } catch {
    fromGetter = undefined;
  }
  if (fromGetter !== undefined && fromGetter !== null) {
    if (typeof fromGetter === "object" && !Array.isArray(fromGetter)) {
      return fromGetter as Record<string, unknown>;
    }
    throw new ProtocolError("Jarvis answered something this plugin could not read.");
  }
  const parsed = tryParseJson(typeof raw.text === "string" ? raw.text : "");
  if (parsed === null) {
    throw new ProtocolError("Jarvis answered something this plugin could not read.");
  }
  return parsed;
}

/** A short, safe version of any thrown value for the screen (never a token). */
export function shortError(error: unknown): string {
  if (error instanceof Error) return error.message.slice(0, 240);
  return String(error).slice(0, 240);
}

/** Cut a text down to `max` characters for a card line or a preview. */
export function clip(value: string, max: number): string {
  const said = (value ?? "").replace(/\s+/g, " ").trim();
  if (said.length <= max) return said;
  return said.slice(0, Math.max(0, max - 1)) + "\u2026";
}

/**
 * Bound a text that is on its way to the backend (never the token, never a
 * write target - only read-only context). Says whether it was cut, so the ask
 * can tell Jarvis the context is partial instead of pretending it is whole.
 */
export function boundedText(raw: string, max: number): { text: string; truncated: boolean } {
  const value = raw ?? "";
  if (value.length <= max) return { text: value, truncated: false };
  return { text: value.slice(0, max), truncated: true };
}

/**
 * Map a failed HTTP answer to a plain sentence. The backend's own `message`
 * wins when it sent one; the fallbacks name the specific status in plain words.
 */
export function httpErrorMessage(status: number, body: Record<string, unknown>): string {
  const data = object(body);
  const said = text(data.message) || text(data.error) || text(data.why);
  if (status === 401 || status === 403) {
    return said
      ? "Jarvis refused the token (HTTP " + status + "): " + said
      : "Jarvis refused the request (HTTP " + status + "). Check the token in Settings -> Jarvis notes bridge.";
  }
  if (status === 404) {
    return (
      said ||
      "Jarvis does not have this route yet (HTTP 404). The notes edit routes arrive with the notes-editor backend deploy."
    );
  }
  if (status === 409) {
    return (
      said ||
      "Jarvis refused it because the note changed since this plugin read it (HTTP 409). Nothing was written."
    );
  }
  if (status === 413) {
    return said || "Jarvis refused it because the note is bigger than its size limit (HTTP 413). Nothing was written.";
  }
  if (status === 429) {
    return (
      said ||
      "Jarvis is busy: too many changes are already waiting for a card (HTTP 429). Answer one in Jarvis first."
    );
  }
  if (status === 503) {
    return said || "Jarvis cannot reach your Obsidian vault right now (HTTP 503).";
  }
  return "Jarvis answered HTTP " + status + (said ? ": " + said : ".");
}

function baseOutcome(
  kind: WriteKind,
  message: string,
  status: number,
  body: Record<string, unknown>,
): WriteOutcome {
  return {
    kind,
    message,
    jobId: text(body.id),
    sha256: text(body.sha256),
    currentSha256: text(body.current_sha256),
    httpStatus: status,
  };
}

/**
 * Map the answer of a write route (POST /api/notes/insert|format|replace|
 * customize|tag|create) to the panel's outcome.
 *
 *   202 waiting   -> kind "waiting", jobId set; the caller polls change status
 *   200 saved     -> kind "saved"
 *   200 unchanged -> kind "unchanged" (the backend decided nothing needed changing)
 *   409 conflict  -> kind "conflict", currentSha256 set
 *   anything else -> kind "error" with a plain sentence
 */
export function interpretWriteReply(status: number, body: Record<string, unknown>): WriteOutcome {
  const data = object(body);
  const said = text(data.message);
  const state = text(data.state).toLowerCase();
  if (status === 401 || status === 403) {
    return baseOutcome("error", httpErrorMessage(status, data), status, data);
  }
  if (state === "waiting" || status === 202) {
    return baseOutcome("waiting", said || WAITING_CARD_MESSAGE, status, data);
  }
  if (state === "conflict" || status === 409) {
    return baseOutcome(
      "conflict",
      said || "The note changed since this plugin read it, so nothing was written. Reopen the panel and try again.",
      status,
      data,
    );
  }
  if (status >= 200 && status < 300 && data.ok !== false) {
    if (state === "unchanged") {
      return baseOutcome("unchanged", said || "Nothing needed changing.", status, data);
    }
    return baseOutcome(
      "saved",
      said || "Jarvis says it saved the change. You can undo it in Jarvis.",
      status,
      data,
    );
  }
  if (status >= 200 && status < 300) {
    return baseOutcome("error", said || text(data.error) || "Jarvis refused the change.", status, data);
  }
  return baseOutcome("error", httpErrorMessage(status, data), status, data);
}

/**
 * Map the answer of GET /api/notes/change?id= (how one write ended) to the
 * same outcome shape. States: waiting, saved, unchanged, denied, failed.
 */
export function interpretStatusReply(status: number, body: Record<string, unknown>): WriteOutcome {
  const data = object(body);
  const said = text(data.message);
  const state = text(data.state).toLowerCase();
  if (status === 401 || status === 403) {
    return baseOutcome("error", httpErrorMessage(status, data), status, data);
  }
  if (state === "waiting") {
    return baseOutcome("waiting", said || WAITING_CARD_MESSAGE, status, data);
  }
  if (state === "saved") {
    return baseOutcome("saved", said || "Jarvis saved the change. You can undo it in Jarvis.", status, data);
  }
  if (state === "unchanged") {
    return baseOutcome("unchanged", said || "Nothing needed changing.", status, data);
  }
  if (state === "denied") {
    return baseOutcome(
      "denied",
      said || "You said no, so nothing was changed.",
      status,
      data,
    );
  }
  if (state === "failed") {
    return baseOutcome("failed", said || "Jarvis could not make the change. Nothing was written.", status, data);
  }
  if (state === "conflict") {
    return baseOutcome(
      "conflict",
      said || "The note changed while the card waited, so nothing was written.",
      status,
      data,
    );
  }
  if (status >= 200 && status < 300) {
    return baseOutcome("error", "Jarvis answered without saying how the change ended.", status, data);
  }
  return baseOutcome("error", httpErrorMessage(status, data), status, data);
}

/** Map the answer of POST /api/chat (a read-only ask) to an answer or an honest error. */
export function interpretChatReply(status: number, body: Record<string, unknown>): ChatOutcome {
  const data = object(body);
  if (status < 200 || status >= 300) {
    return {
      kind: "error",
      answer: "",
      message: httpErrorMessage(status, data),
    };
  }
  const choices = Array.isArray(data.choices) ? data.choices : [];
  const first = object(choices[0]);
  const message = object(first.message);
  const answer = (text(message.content) || text(data.reply) || text(data.text)).trim();
  if (!answer) {
    return {
      kind: "error",
      answer: "",
      message: "Jarvis answered with an empty answer.",
    };
  }
  return { kind: "ok", answer, message: "" };
}

/** Map the answer of GET /api/notes/read?path= to the note's bytes hash plus text. */
export function interpretReadReply(status: number, body: Record<string, unknown>): ReadOutcome {
  const data = object(body);
  if (status < 200 || status >= 300 || data.ok === false) {
    return {
      kind: "error",
      path: text(data.path),
      sha256: "",
      text: "",
      message: httpErrorMessage(status, data),
    };
  }
  const sha256 = text(data.sha256);
  if (!sha256) {
    return {
      kind: "error",
      path: text(data.path),
      sha256: "",
      text: "",
      message: "Jarvis read the note but did not send its bytes hash, so a safe edit cannot be made.",
    };
  }
  return {
    kind: "ok",
    path: text(data.path),
    sha256,
    text: text(data.text),
    message: "",
  };
}

/**
 * Map the answer of POST /api/notes/capture (capture to today's daily note).
 * States the backend uses: waiting (a card is up), filed (done), not_filed (why).
 */
export function interpretCaptureReply(status: number, body: Record<string, unknown>): CaptureOutcome {
  const data = object(body);
  const said = text(data.message);
  const state = text(data.state).toLowerCase();
  if (status === 401 || status === 403) {
    return {
      kind: "error",
      message: httpErrorMessage(status, data),
      jobId: text(data.id),
      httpStatus: status,
    };
  }
  if (status === 202 || state === "waiting") {
    return {
      kind: "waiting",
      message: said || WAITING_CARD_MESSAGE,
      jobId: text(data.id),
      httpStatus: status,
    };
  }
  if (state === "filed" || (status >= 200 && status < 300 && data.ok !== false && !state)) {
    return {
      kind: "filed",
      message: said || "Captured into today's note in your Obsidian vault.",
      jobId: text(data.id),
      httpStatus: status,
    };
  }
  if (state === "not_filed" || data.ok === false) {
    return {
      kind: "not_filed",
      message: said || "Not captured: " + (text(data.error) || "Jarvis did not say why."),
      jobId: text(data.id),
      httpStatus: status,
    };
  }
  if (status >= 200 && status < 300) {
    return {
      kind: "filed",
      message: said || "Captured into today's note in your Obsidian vault.",
      jobId: text(data.id),
      httpStatus: status,
    };
  }
  return {
    kind: "error",
    message: httpErrorMessage(status, data),
    jobId: text(data.id),
    httpStatus: status,
  };
}

/** Map the answer of GET /api/notes/templates to the names Jarvis knows. */
export function interpretTemplatesReply(status: number, body: Record<string, unknown>): TemplateListOutcome {
  const data = object(body);
  if (status < 200 || status >= 300 || data.ok === false) {
    return {
      kind: "error",
      names: [],
      why: "",
      message: httpErrorMessage(status, data),
      httpStatus: status,
    };
  }
  const raw = Array.isArray(data.templates) ? data.templates : [];
  const names: string[] = [];
  for (const item of raw) {
    if (typeof item === "string" && item.trim()) names.push(item.trim());
  }
  return { kind: "ok", names, why: text(data.why), message: "", httpStatus: status };
}

/** The display label for one heading, e.g. "## Session". */
export function headingLabel(heading: HeadingRef): string {
  return "#".repeat(Math.max(1, Math.min(6, heading.level))) + " " + heading.text;
}

/**
 * The note text a read-only ask carries: title, path, headings, links and keys
 * first, then the bounded note text. Pure, so the shape can be tested.
 */
export function buildContextText(context: NoteContext): string {
  const parts: string[] = [];
  parts.push("Note: " + context.title + " (" + context.path + ")");
  if (context.headings.length) {
    parts.push("Headings:\n" + context.headings.map((h) => "- " + headingLabel(h)).join("\n"));
  }
  if (context.links.length) {
    parts.push("Links:\n" + context.links.map((l) => "- " + l).join("\n"));
  }
  if (context.backlinks.length) {
    parts.push("Linked from:\n" + context.backlinks.map((l) => "- " + l).join("\n"));
  }
  if (context.unresolved.length) {
    parts.push("Unresolved links:\n" + context.unresolved.map((l) => "- " + l).join("\n"));
  }
  if (context.frontmatterKeys.length) {
    parts.push("Frontmatter keys: " + context.frontmatterKeys.join(", "));
  }
  if (context.text) {
    const prefix = context.truncated
      ? "(note truncated to the first " + MAX_CONTEXT_CHARS + " characters)\n"
      : "";
    parts.push(prefix + context.text);
  }
  return parts.join("\n\n");
}

/** The exact whole line a checklist action should target, given a selection. */
export function lineContaining(selection: string, noteText: string): string {
  const wanted = (selection ?? "").trim();
  if (!wanted) return "";
  for (const line of (noteText ?? "").split(/\r?\n/)) {
    if (line.includes(wanted)) return line;
  }
  return "";
}

/** How long to wait before the next card-status check (1.5 s, then 2.5 s). */
export function pollDelayMs(attempt: number): number {
  return attempt <= 1 ? 1500 : 2500;
}

/** After this many checks the panel stops polling and says so honestly. */
export function pollGaveUpMessage(): string {
  return (
    "Still waiting for the card on the PC. This plugin stopped checking after 10 minutes; " +
    "answer or dismiss the card in Jarvis, then reopen the Jarvis panel to see the outcome."
  );
}

/** True when an outcome means a card exists and its status should be polled. */
export function shouldPoll(outcome: WriteOutcome): boolean {
  return outcome.kind === "waiting" && outcome.jobId !== "";
}
