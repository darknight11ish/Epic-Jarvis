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
  FirstRunChecklist,
  HeadingRef,
  NoteContext,
  RawAnswer,
  ReadOutcome,
  StatusKind,
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

/**
 * The first-run setup steps, in order. The third one is the check that proves
 * the address and the token, so the panel never has to guess.
 */
export const FIRST_RUN_STEPS: readonly string[] = [
  "Open Settings -> Jarvis notes bridge.",
  "Pick the Obsidian secret that holds your Jarvis token (preferred), or paste the token into the clearly-marked fallback field in a test vault.",
  "Press Test connection. It should say Connected.",
];

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

/**
 * The first-run checklist for the current connection state: the three steps,
 * and the ONE next thing to do. It disappears only when the backend is
 * connected, so the panel never leaves a beginner guessing where they are.
 */
export function firstRunChecklist(hasToken: boolean, status: StatusKind): FirstRunChecklist {
  const steps = [...FIRST_RUN_STEPS];
  if (!hasToken || status === "no-token") {
    return {
      heading: "First run",
      steps,
      next: "Start at step 1: this panel needs a Jarvis token before Ask, Capture or any edit can work.",
    };
  }
  if (status === "connected") {
    return { heading: "", steps: [], next: "" };
  }
  if (status === "unreachable") {
    return {
      heading: "First run",
      steps,
      next:
        "The token is set. Step 3 failed because nothing answered: is the Jarvis desktop app running on this PC? " +
        "Start it, then press Test connection again.",
    };
  }
  if (status === "token-refused") {
    return {
      heading: "First run",
      steps,
      next:
        "Step 3 failed because Jarvis refused the token: copy it again in full (about 43 characters), " +
        "then press Test connection.",
    };
  }
  if (status === "not-deployed") {
    return {
      heading: "First run",
      steps,
      next:
        "The address and token are fine, but this backend does not have the notes routes yet (HTTP 404). " +
        "That is not a mistake you made: they arrive with the notes-editor backend deploy. Ask and Capture work until then.",
    };
  }
  if (status === "http") {
    return {
      heading: "First run",
      steps,
      next:
        "Step 3 got an unexpected answer: open Settings -> Jarvis notes bridge and read the exact line " +
        "under Test connection.",
    };
  }
  return {
    heading: "First run",
    steps,
    next: "Jarvis is checking the connection now. Step 3 is the manual version of that check.",
  };
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
  if (status === 401) {
    return said
      ? "Jarvis refused the token (HTTP 401): " + said
      : "Jarvis refused the token (HTTP 401). Check the token in Settings -> Jarvis notes bridge.";
  }
  if (status === 403) {
    // 403 is NOT the token here: on this backend it is the protected-note
    // refusal (backend/jarvis_notes_edit.py). Blaming the token would send the
    // owner to fix the one thing that is working.
    return said
      ? "Jarvis refused the request (HTTP 403): " + said
      : "Jarvis refused the request (HTTP 403). The backend did not send a reason.";
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
    const message = said || WAITING_CARD_MESSAGE;
    // A card that cannot be followed is still a card: say so, do not pretend the
    // panel can report how it ended. Without an id there is nothing to poll.
    if (!text(data.id)) {
      return baseOutcome(
        "waiting",
        message +
          " Jarvis did not send a change id, so this panel cannot follow the card: " +
          "answer it in Jarvis, then reopen this panel to see the outcome.",
        status,
        data,
      );
    }
    return baseOutcome("waiting", message, status, data);
  }
  if (state === "conflict" || status === 409) {
    return baseOutcome(
      "conflict",
      said || "The note changed since this plugin read it, so nothing was written. Reopen the panel and try again.",
      status,
      data,
    );
  }
  // A card answered very fast (denied or failed before the first answer) comes
  // back from the write route itself, not from the status poll. Say what it is.
  if (state === "denied") {
    return baseOutcome("denied", said || "You said no, so nothing was changed.", status, data);
  }
  if (state === "failed") {
    return baseOutcome(
      "failed",
      said || "Jarvis could not make the change. Nothing was written.",
      status,
      data,
    );
  }
  if (status >= 200 && status < 300 && data.ok !== false) {
    if (state === "unchanged") {
      return baseOutcome("unchanged", said || "Nothing needed changing.", status, data);
    }
    if (state === "saved" || !state) {
      return baseOutcome(
        "saved",
        said || "Jarvis says it saved the change. You can undo it in Jarvis.",
        status,
        data,
      );
    }
    // A 2xx with a state word this plugin does not know must not be read as
    // "saved": only the two documented success states above can say that.
    return baseOutcome(
      "error",
      "Jarvis answered with the state \"" +
        state +
        "\", which this plugin does not know, so it cannot say the change was saved.",
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
  // A 2xx that says ok:false is a refusal, not an empty answer: keep the
  // backend's own reason instead of inventing "empty answer".
  if (data.ok === false) {
    return {
      kind: "error",
      answer: "",
      message:
        text(data.error) ||
        text(data.message) ||
        text(data.why) ||
        "Jarvis refused to answer this question.",
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
  // A non-2xx answer is an error BEFORE the `ok:false` branch below. A 404 for an
  // unknown capture id only means this PC has no record of that job (the backend
  // may have been restarted, and the words may even have been filed before that),
  // so reporting "not_filed" would claim something the plugin cannot know.
  if (status < 200 || status >= 300) {
    return {
      kind: "error",
      message: httpErrorMessage(status, data),
      jobId: text(data.id),
      httpStatus: status,
    };
  }
  if (status === 202 || state === "waiting") {
    const message = said || WAITING_CARD_MESSAGE;
    // No status id means this dialog cannot check how the capture ended; saying
    // so is honest, and it never labels an unchecked capture as filed.
    if (!text(data.id)) {
      return {
        kind: "waiting",
        message:
          message +
          " Jarvis did not send a status id, so this dialog cannot follow it: answer the card in Jarvis, then check today's note.",
        jobId: "",
        httpStatus: status,
      };
    }
    return {
      kind: "waiting",
      message,
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
  // Any other terminal state the backend reports means it was NOT filed. This
  // must come before the 2xx fallback: a `state:"failed"` answer is a failure,
  // not a success that merely lacks a known state word.
  if (state === "failed" || state === "denied" || state === "timed_out" || state === "not_filed") {
    return {
      kind: "not_filed",
      message: said || "Not captured: " + (text(data.error) || "Jarvis did not file it."),
      jobId: text(data.id),
      httpStatus: status,
    };
  }
  if (status >= 200 && status < 300) {
    // Only `filed` or an answer with no state word counts as filed (the live
    // capture route answers with a sentence only). Any other 2xx state word is
    // unknown, so it is reported as NOT filed rather than guessed as success.
    return {
      kind: "not_filed",
      message:
        said ||
        (state
          ? "Not captured: Jarvis reported the state \"" +
            state +
            "\", which this plugin does not know, so this is not counted as filed."
          : "Not captured: Jarvis did not say the capture was filed."),
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
  const listed: unknown = data.templates;
  if (listed !== undefined && listed !== null && !Array.isArray(listed)) {
    // A template list that is not a list must not read as "no templates": the
    // panel lists names, and guessing them from a malformed answer would be a lie.
    return {
      kind: "error",
      names: [],
      why: "",
      message:
        "Jarvis answered but its template list was not a list, so this plugin will not guess the template names.",
      httpStatus: status,
    };
  }
  const raw = Array.isArray(listed) ? listed : [];
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

/** True when a write outcome means the change did NOT happen (a refusal, not a result). */
export function isRefusalKind(kind: WriteKind | undefined): boolean {
  return kind === "error" || kind === "failed" || kind === "denied" || kind === "conflict";
}

/** True when an outcome means a card exists and its status should be polled. */
export function shouldPoll(outcome: WriteOutcome): boolean {
  return outcome.kind === "waiting" && outcome.jobId !== "";
}

/* ---------------------------------------------------------------------- */
/* The READ-ONLY direction: a link that opens a note in Obsidian           */
/* ---------------------------------------------------------------------- */

/**
 * The action part of an `obsidian://` URI, lowercased ("open" for a link that
 * only opens a note, "" when there is no action). Used by the tests and by the
 * safety test to prove the plugin builds OPEN links only.
 */
export function obsidianUriAction(uri: string): string {
  const match = /^obsidian:\/\/([A-Za-z]+)/.exec((uri ?? "").trim());
  return match ? match[1].toLowerCase() : "";
}

/**
 * Build the link that OPENS one note (optionally at a heading), for the
 * read-only direction "Jarvis sends the owner back to the exact note":
 *
 *   obsidian://open?vault=<vault name>&file=<vault-relative path>[#<heading>]
 *
 * Obsidian's URI scheme also has write actions (`new` with `prepend`/`append`,
 * `daily`, `unique`). This plugin deliberately builds ONLY `open`: a link is a
 * way to look at a note, never a way to change it. Every write in this project
 * goes through Jarvis's one-card routes, and a URI that writes instantly would
 * bypass the card, the File Guardian copy and Undo.
 */
export function obsidianOpenUri(vaultName: string, filePath: string, heading?: string): string {
  const vault = (vaultName ?? "").trim();
  const file = (filePath ?? "").trim().replace(/^\/+/, "");
  const at = (heading ?? "").trim();
  const target = at ? file + "#" + at : file;
  return (
    "obsidian://open?vault=" +
    encodeURIComponent(vault) +
    "&file=" +
    encodeURIComponent(target)
  );
}

/* ---------------------------------------------------------------------- */
/* Route request builders: the one place a request's shape is decided      */
/* ---------------------------------------------------------------------- */

/**
 * One outgoing request in plain data: which method, which route, which query
 * and which JSON body. `JarvisClient` builds every request through these pure
 * helpers, so the integration tests can exercise the real bodies against a
 * fake Jarvis without an Obsidian app in the loop.
 */
export interface RouteRequest {
  method: "GET" | "POST";
  route: string;
  query?: Record<string, string>;
  body?: unknown;
}

/** One note's text plus the sha256 of its bytes. */
export function readNoteRequest(path: string): RouteRequest {
  return { method: "GET", route: ROUTES.read, query: { path } };
}

/** The template names Jarvis knows (names only). */
export function templatesRequest(): RouteRequest {
  return { method: "GET", route: ROUTES.templates };
}

/** A read-only ask about the note or the selection. */
export function chatRequest(question: string, contextText: string, notePath: string): RouteRequest {
  const content =
    question.trim() + "\n\nRead-only context from " + notePath + ":\n" + contextText;
  return {
    method: "POST",
    route: ROUTES.chat,
    body: {
      messages: [{ role: "user", content, provenance: "pasted" }],
      stream: false,
      auto: false,
    },
  };
}

/** Capture to today's daily note (the existing capture route). */
export function captureRequest(text: string): RouteRequest {
  return {
    method: "POST",
    route: ROUTES.capture,
    body: { target: "obsidian", text: (text ?? "").trim() },
  };
}

/** How one capture ended. */
export function captureStatusRequest(jobId: string): RouteRequest {
  return { method: "GET", route: ROUTES.captureStatus, query: { id: jobId } };
}

/** Add one line under the named heading of one note. */
export function insertRequest(
  path: string,
  text: string,
  heading: string,
  expectedSha: string,
): RouteRequest {
  return {
    method: "POST",
    route: ROUTES.insert,
    body: { path, text, mode: "under_heading", target: heading, expected_sha256: expectedSha },
  };
}

/** Wrap one exact span in bold or italic. */
export function formatRequest(
  path: string,
  target: string,
  style: "bold" | "italic",
  action: "add" | "remove",
  expectedSha: string,
): RouteRequest {
  return {
    method: "POST",
    route: ROUTES.format,
    body: { path, target, style, action, expected_sha256: expectedSha },
  };
}

/** Replace one exact, whole-word occurrence. */
export function replaceRequest(
  path: string,
  oldText: string,
  newText: string,
  expectedSha: string,
): RouteRequest {
  return {
    method: "POST",
    route: ROUTES.replace,
    body: { path, old: oldText, new: newText, expected_sha256: expectedSha },
  };
}

/** Change one whole line's shape (this plugin uses it for "make it a checklist item"). */
export function customizeLineRequest(
  path: string,
  lineAction: "bullet" | "number" | "checklist" | "quote" | "plain" | "untick",
  targetLine: string,
  expectedSha: string,
): RouteRequest {
  return {
    method: "POST",
    route: ROUTES.customize,
    body: {
      path,
      action: "line",
      line_action: lineAction,
      target: targetLine,
      expected_sha256: expectedSha,
    },
  };
}

/** Add one tag to one note (frontmatter list when present, else a visible line). */
export function tagRequest(path: string, tag: string, expectedSha: string): RouteRequest {
  return {
    method: "POST",
    route: ROUTES.tag,
    body: { path, tag, action: "add", where: "auto", expected_sha256: expectedSha },
  };
}

/** Create ONE new note (one card; the backend refuses an existing path). */
export function createNoteRequest(path: string, text: string): RouteRequest {
  return { method: "POST", route: ROUTES.create, body: { path, text } };
}

/** How one write ended. */
export function changeStatusRequest(jobId: string): RouteRequest {
  return { method: "GET", route: ROUTES.change, query: { id: jobId } };
}
