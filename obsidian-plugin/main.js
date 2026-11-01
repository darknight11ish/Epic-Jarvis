/* Jarvis notes bridge - generated bundle. Source: obsidian-plugin/src/ */
"use strict";
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// src/main.ts
var main_exports = {};
__export(main_exports, {
  default: () => JarvisNotesPlugin
});
module.exports = __toCommonJS(main_exports);
var import_obsidian5 = require("obsidian");

// src/a11y.ts
function accessibleName(el, name) {
  const clean = (name != null ? name : "").trim();
  if (!clean) throw new Error("an accessible name must not be empty");
  el.setAttribute("aria-label", clean);
}
function liveRegion(el, politeness = "polite") {
  el.setAttribute("role", politeness === "assertive" ? "alert" : "status");
  el.setAttribute("aria-live", politeness);
  el.setAttribute("aria-atomic", "true");
}
function group(el, name) {
  const clean = (name != null ? name : "").trim();
  if (!clean) throw new Error("a group name must not be empty");
  el.setAttribute("role", "group");
  el.setAttribute("aria-label", clean);
}
function busy(el, isBusy) {
  el.setAttribute("aria-busy", isBusy ? "true" : "false");
}
function hint(el, text2) {
  const clean = (text2 != null ? text2 : "").trim();
  if (!clean) return;
  el.setAttribute("title", clean);
}

// src/client.ts
var import_obsidian = require("obsidian");

// src/protocol.ts
var DEFAULT_BACKEND = "http://127.0.0.1:4719";
var MAX_CONTEXT_CHARS = 12e3;
var MAX_SELECTION_CHARS = 12e3;
var MAX_HEADINGS = 80;
var MAX_LINKS = 80;
var MAX_FRONTMATTER_KEYS = 60;
var ROUTES = {
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
  change: "/api/notes/change"
};
var UNREACHABLE_MESSAGE = "Could not reach the local Jarvis. Is the desktop Jarvis running on this PC?";
var WAITING_CARD_MESSAGE = "A card is waiting on the PC. This plugin cannot approve cards: answer it in the Jarvis window on the PC.";
var POLL_MAX_ATTEMPTS = 240;
var FIRST_RUN_STEPS = [
  "Open Settings -> Jarvis notes bridge.",
  "Pick the Obsidian secret that holds your Jarvis token (preferred), or paste the token into the clearly-marked fallback field in a test vault.",
  "Press Test connection. It should say Connected."
];
var ProtocolError = class extends Error {
  constructor(message, kind = "unreadable") {
    super(message);
    this.name = "ProtocolError";
    this.kind = kind;
  }
};
function text(value) {
  return typeof value === "string" ? value : "";
}
function object(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}
function normalizeBackendUrl(raw) {
  const trimmed = (raw != null ? raw : "").trim();
  if (!trimmed) return DEFAULT_BACKEND;
  return trimmed.replace(/\/+$/, "");
}
function isLoopbackUrl(raw) {
  const match = /^https?:\/\/(\[[^\]]+\]|[^/:]+)/i.exec((raw != null ? raw : "").trim());
  if (!match) return false;
  const host = match[1].toLowerCase().replace(/^\[|\]$/g, "");
  return host === "127.0.0.1" || host === "localhost" || host === "::1";
}
function buildUrl(base, route, query) {
  const cleanBase = normalizeBackendUrl(base);
  const cleanRoute = route.startsWith("/") ? route : "/" + route;
  if (!query) return cleanBase + cleanRoute;
  const pairs = [];
  for (const key of Object.keys(query)) {
    const value = query[key];
    if (value === void 0 || value === null) continue;
    pairs.push(encodeURIComponent(key) + "=" + encodeURIComponent(value));
  }
  return pairs.length ? cleanBase + cleanRoute + "?" + pairs.join("&") : cleanBase + cleanRoute;
}
function buildHeaders(token) {
  return {
    "Content-Type": "application/json",
    "X-Jarvis-Token": token,
    "X-Jarvis-Client": "hud",
    "X-Jarvis-Surface": "desktop"
  };
}
function requireToken(token) {
  const value = (token != null ? token : "").trim();
  if (!value) {
    throw new ProtocolError(
      "No Jarvis token yet. Open Settings -> Jarvis notes bridge and either pick a SecretStorage secret or paste the token into the fallback field.",
      "no-token"
    );
  }
  return value;
}
function firstRunChecklist(hasToken, status) {
  const steps = [...FIRST_RUN_STEPS];
  if (!hasToken || status === "no-token") {
    return {
      heading: "First run",
      steps,
      next: "Start at step 1: this panel needs a Jarvis token before Ask, Capture or any edit can work."
    };
  }
  if (status === "connected") {
    return { heading: "", steps: [], next: "" };
  }
  if (status === "unreachable") {
    return {
      heading: "First run",
      steps,
      next: "The token is set. Step 3 failed because nothing answered: is the Jarvis desktop app running on this PC? Start it, then press Test connection again."
    };
  }
  if (status === "token-refused") {
    return {
      heading: "First run",
      steps,
      next: "Step 3 failed because Jarvis refused the token: copy it again in full (about 43 characters), then press Test connection."
    };
  }
  if (status === "not-deployed") {
    return {
      heading: "First run",
      steps,
      next: "The address and token are fine, but this backend does not have the notes routes yet (HTTP 404). That is not a mistake you made: they arrive with the notes-editor backend deploy. Ask and Capture work until then."
    };
  }
  if (status === "http") {
    return {
      heading: "First run",
      steps,
      next: "Step 3 got an unexpected answer: open Settings -> Jarvis notes bridge and read the exact line under Test connection."
    };
  }
  return {
    heading: "First run",
    steps,
    next: "Jarvis is checking the connection now. Step 3 is the manual version of that check."
  };
}
function tryParseJson(value) {
  try {
    const parsed = JSON.parse(value);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
    return parsed;
  } catch (e) {
    return null;
  }
}
function parseJsonBody(raw) {
  let fromGetter;
  try {
    fromGetter = raw.json;
  } catch (e) {
    fromGetter = void 0;
  }
  if (fromGetter !== void 0 && fromGetter !== null) {
    if (typeof fromGetter === "object" && !Array.isArray(fromGetter)) {
      return fromGetter;
    }
    throw new ProtocolError("Jarvis answered something this plugin could not read.");
  }
  const parsed = tryParseJson(typeof raw.text === "string" ? raw.text : "");
  if (parsed === null) {
    throw new ProtocolError("Jarvis answered something this plugin could not read.");
  }
  return parsed;
}
function shortError(error) {
  if (error instanceof Error) return error.message.slice(0, 240);
  return String(error).slice(0, 240);
}
function clip(value, max) {
  const said = (value != null ? value : "").replace(/\s+/g, " ").trim();
  if (said.length <= max) return said;
  return said.slice(0, Math.max(0, max - 1)) + "\u2026";
}
function boundedText(raw, max) {
  const value = raw != null ? raw : "";
  if (value.length <= max) return { text: value, truncated: false };
  return { text: value.slice(0, max), truncated: true };
}
function httpErrorMessage(status, body) {
  const data = object(body);
  const said = text(data.message) || text(data.error) || text(data.why);
  if (status === 401) {
    return said ? "Jarvis refused the token (HTTP 401): " + said : "Jarvis refused the token (HTTP 401). Check the token in Settings -> Jarvis notes bridge.";
  }
  if (status === 403) {
    return said ? "Jarvis refused the request (HTTP 403): " + said : "Jarvis refused the request (HTTP 403). The backend did not send a reason.";
  }
  if (status === 404) {
    return said || "Jarvis does not have this route yet (HTTP 404). The notes edit routes arrive with the notes-editor backend deploy.";
  }
  if (status === 409) {
    return said || "Jarvis refused it because the note changed since this plugin read it (HTTP 409). Nothing was written.";
  }
  if (status === 413) {
    return said || "Jarvis refused it because the note is bigger than its size limit (HTTP 413). Nothing was written.";
  }
  if (status === 429) {
    return said || "Jarvis is busy: too many changes are already waiting for a card (HTTP 429). Answer one in Jarvis first.";
  }
  if (status === 503) {
    return said || "Jarvis cannot reach your Obsidian vault right now (HTTP 503).";
  }
  return "Jarvis answered HTTP " + status + (said ? ": " + said : ".");
}
function baseOutcome(kind, message, status, body) {
  return {
    kind,
    message,
    jobId: text(body.id),
    sha256: text(body.sha256),
    currentSha256: text(body.current_sha256),
    httpStatus: status
  };
}
function interpretWriteReply(status, body) {
  const data = object(body);
  const said = text(data.message);
  const state = text(data.state).toLowerCase();
  if (status === 401 || status === 403) {
    return baseOutcome("error", httpErrorMessage(status, data), status, data);
  }
  if (state === "waiting" || status === 202) {
    const message = said || WAITING_CARD_MESSAGE;
    if (!text(data.id)) {
      return baseOutcome(
        "waiting",
        message + " Jarvis did not send a change id, so this panel cannot follow the card: answer it in Jarvis, then reopen this panel to see the outcome.",
        status,
        data
      );
    }
    return baseOutcome("waiting", message, status, data);
  }
  if (state === "conflict" || status === 409) {
    return baseOutcome(
      "conflict",
      said || "The note changed since this plugin read it, so nothing was written. Reopen the panel and try again.",
      status,
      data
    );
  }
  if (state === "denied") {
    return baseOutcome("denied", said || "You said no, so nothing was changed.", status, data);
  }
  if (state === "failed") {
    return baseOutcome(
      "failed",
      said || "Jarvis could not make the change. Nothing was written.",
      status,
      data
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
        data
      );
    }
    return baseOutcome(
      "error",
      'Jarvis answered with the state "' + state + '", which this plugin does not know, so it cannot say the change was saved.',
      status,
      data
    );
  }
  if (status >= 200 && status < 300) {
    return baseOutcome("error", said || text(data.error) || "Jarvis refused the change.", status, data);
  }
  return baseOutcome("error", httpErrorMessage(status, data), status, data);
}
function interpretStatusReply(status, body) {
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
      data
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
      data
    );
  }
  if (status >= 200 && status < 300) {
    return baseOutcome("error", "Jarvis answered without saying how the change ended.", status, data);
  }
  return baseOutcome("error", httpErrorMessage(status, data), status, data);
}
function interpretChatReply(status, body) {
  const data = object(body);
  if (status < 200 || status >= 300) {
    return {
      kind: "error",
      answer: "",
      message: httpErrorMessage(status, data)
    };
  }
  if (data.ok === false) {
    return {
      kind: "error",
      answer: "",
      message: text(data.error) || text(data.message) || text(data.why) || "Jarvis refused to answer this question."
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
      message: "Jarvis answered with an empty answer."
    };
  }
  return { kind: "ok", answer, message: "" };
}
function interpretReadReply(status, body) {
  const data = object(body);
  if (status < 200 || status >= 300 || data.ok === false) {
    return {
      kind: "error",
      path: text(data.path),
      sha256: "",
      text: "",
      message: httpErrorMessage(status, data)
    };
  }
  const sha256 = text(data.sha256);
  if (!sha256) {
    return {
      kind: "error",
      path: text(data.path),
      sha256: "",
      text: "",
      message: "Jarvis read the note but did not send its bytes hash, so a safe edit cannot be made."
    };
  }
  return {
    kind: "ok",
    path: text(data.path),
    sha256,
    text: text(data.text),
    message: ""
  };
}
function interpretCaptureReply(status, body) {
  const data = object(body);
  const said = text(data.message);
  const state = text(data.state).toLowerCase();
  if (status === 401 || status === 403) {
    return {
      kind: "error",
      message: httpErrorMessage(status, data),
      jobId: text(data.id),
      httpStatus: status
    };
  }
  if (status < 200 || status >= 300) {
    return {
      kind: "error",
      message: httpErrorMessage(status, data),
      jobId: text(data.id),
      httpStatus: status
    };
  }
  if (status === 202 || state === "waiting") {
    const message = said || WAITING_CARD_MESSAGE;
    if (!text(data.id)) {
      return {
        kind: "waiting",
        message: message + " Jarvis did not send a status id, so this dialog cannot follow it: answer the card in Jarvis, then check today's note.",
        jobId: "",
        httpStatus: status
      };
    }
    return {
      kind: "waiting",
      message,
      jobId: text(data.id),
      httpStatus: status
    };
  }
  if (state === "filed" || status >= 200 && status < 300 && data.ok !== false && !state) {
    return {
      kind: "filed",
      message: said || "Captured into today's note in your Obsidian vault.",
      jobId: text(data.id),
      httpStatus: status
    };
  }
  if (state === "not_filed" || data.ok === false) {
    return {
      kind: "not_filed",
      message: said || "Not captured: " + (text(data.error) || "Jarvis did not say why."),
      jobId: text(data.id),
      httpStatus: status
    };
  }
  if (state === "failed" || state === "denied" || state === "timed_out" || state === "not_filed") {
    return {
      kind: "not_filed",
      message: said || "Not captured: " + (text(data.error) || "Jarvis did not file it."),
      jobId: text(data.id),
      httpStatus: status
    };
  }
  if (status >= 200 && status < 300) {
    return {
      kind: "not_filed",
      message: said || (state ? 'Not captured: Jarvis reported the state "' + state + '", which this plugin does not know, so this is not counted as filed.' : "Not captured: Jarvis did not say the capture was filed."),
      jobId: text(data.id),
      httpStatus: status
    };
  }
  return {
    kind: "error",
    message: httpErrorMessage(status, data),
    jobId: text(data.id),
    httpStatus: status
  };
}
function interpretTemplatesReply(status, body) {
  const data = object(body);
  if (status < 200 || status >= 300 || data.ok === false) {
    return {
      kind: "error",
      names: [],
      why: "",
      message: httpErrorMessage(status, data),
      httpStatus: status
    };
  }
  const listed = data.templates;
  if (listed !== void 0 && listed !== null && !Array.isArray(listed)) {
    return {
      kind: "error",
      names: [],
      why: "",
      message: "Jarvis answered but its template list was not a list, so this plugin will not guess the template names.",
      httpStatus: status
    };
  }
  const raw = Array.isArray(listed) ? listed : [];
  const names = [];
  for (const item of raw) {
    if (typeof item === "string" && item.trim()) names.push(item.trim());
  }
  return { kind: "ok", names, why: text(data.why), message: "", httpStatus: status };
}
function headingLabel(heading) {
  return "#".repeat(Math.max(1, Math.min(6, heading.level))) + " " + heading.text;
}
function buildContextText(context) {
  const parts = [];
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
    const prefix = context.truncated ? "(note truncated to the first " + MAX_CONTEXT_CHARS + " characters)\n" : "";
    parts.push(prefix + context.text);
  }
  return parts.join("\n\n");
}
function pollDelayMs(attempt) {
  return attempt <= 1 ? 1500 : 2500;
}
function pollGaveUpMessage() {
  return "Still waiting for the card on the PC. This plugin stopped checking after 10 minutes; answer or dismiss the card in Jarvis, then reopen the Jarvis panel to see the outcome.";
}
function isRefusalKind(kind) {
  return kind === "error" || kind === "failed" || kind === "denied" || kind === "conflict";
}
function shouldPoll(outcome) {
  return outcome.kind === "waiting" && outcome.jobId !== "";
}
function obsidianOpenUri(vaultName, filePath, heading) {
  const vault = (vaultName != null ? vaultName : "").trim();
  const file = (filePath != null ? filePath : "").trim().replace(/^\/+/, "");
  const at = (heading != null ? heading : "").trim();
  const target = at ? file + "#" + at : file;
  return "obsidian://open?vault=" + encodeURIComponent(vault) + "&file=" + encodeURIComponent(target);
}
function readNoteRequest(path) {
  return { method: "GET", route: ROUTES.read, query: { path } };
}
function templatesRequest() {
  return { method: "GET", route: ROUTES.templates };
}
function chatRequest(question, contextText, notePath) {
  const content = question.trim() + "\n\nRead-only context from " + notePath + ":\n" + contextText;
  return {
    method: "POST",
    route: ROUTES.chat,
    body: {
      messages: [{ role: "user", content, provenance: "pasted" }],
      stream: false,
      auto: false
    }
  };
}
function captureRequest(text2) {
  return {
    method: "POST",
    route: ROUTES.capture,
    body: { target: "obsidian", text: (text2 != null ? text2 : "").trim() }
  };
}
function captureStatusRequest(jobId) {
  return { method: "GET", route: ROUTES.captureStatus, query: { id: jobId } };
}
function insertRequest(path, text2, heading, expectedSha) {
  return {
    method: "POST",
    route: ROUTES.insert,
    body: { path, text: text2, mode: "under_heading", target: heading, expected_sha256: expectedSha }
  };
}
function formatRequest(path, target, style, action, expectedSha) {
  return {
    method: "POST",
    route: ROUTES.format,
    body: { path, target, style, action, expected_sha256: expectedSha }
  };
}
function replaceRequest(path, oldText, newText, expectedSha) {
  return {
    method: "POST",
    route: ROUTES.replace,
    body: { path, old: oldText, new: newText, expected_sha256: expectedSha }
  };
}
function customizeLineRequest(path, lineAction, targetLine, expectedSha) {
  return {
    method: "POST",
    route: ROUTES.customize,
    body: {
      path,
      action: "line",
      line_action: lineAction,
      target: targetLine,
      expected_sha256: expectedSha
    }
  };
}
function tagRequest(path, tag, expectedSha) {
  return {
    method: "POST",
    route: ROUTES.tag,
    body: { path, tag, action: "add", where: "auto", expected_sha256: expectedSha }
  };
}
function createNoteRequest(path, text2) {
  return { method: "POST", route: ROUTES.create, body: { path, text: text2 } };
}
function changeStatusRequest(jobId) {
  return { method: "GET", route: ROUTES.change, query: { id: jobId } };
}

// src/client.ts
function sleep(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}
var JarvisClient = class {
  constructor(getBaseUrl, getToken, request = import_obsidian.requestUrl) {
    this.getBaseUrl = getBaseUrl;
    this.getToken = getToken;
    this.request = request;
  }
  /**
   * One request. Returns the status and the parsed JSON body (an empty or
   * non-JSON body becomes a `ProtocolError` with the plugin's honest sentence).
   * A thrown `requestUrl` (backend not running) becomes the unreachable error.
   */
  async send(method, route, query, payload) {
    const token = requireToken(this.getToken());
    const url = buildUrl(normalizeBackendUrl(this.getBaseUrl()), route, query);
    let status = 0;
    let json;
    let responseText = "";
    try {
      const response = await this.request({
        url,
        method,
        throw: false,
        headers: buildHeaders(token),
        body: payload === void 0 ? void 0 : JSON.stringify(payload)
      });
      status = response.status;
      try {
        json = response.json;
      } catch (e) {
        json = void 0;
      }
      responseText = typeof response.text === "string" ? response.text : "";
    } catch (error) {
      throw new ProtocolError(UNREACHABLE_MESSAGE + " " + shortError(error));
    }
    const raw = { status, json, text: responseText };
    return { status, body: parseJsonBody(raw) };
  }
  /* ------------------------------------------------------------------ */
  /* Read-only routes                                                    */
  /* ------------------------------------------------------------------ */
  /** One note's text plus the sha256 of its bytes (the hash an edit starts from). */
  async readNote(path) {
    const request = readNoteRequest(path);
    const { status, body } = await this.send(request.method, request.route, request.query);
    return interpretReadReply(status, body);
  }
  /** A read-only ask about the note or the selection. No card is raised for an ask. */
  async askJarvis(question, contextText, notePath) {
    if (!(question != null ? question : "").trim()) {
      throw new ProtocolError("Ask a question first.", "invalid");
    }
    const request = chatRequest(question, contextText, notePath);
    const { status, body } = await this.send(request.method, request.route, request.query, request.body);
    return interpretChatReply(status, body);
  }
  /** Template names Jarvis knows (names only - the backend never returns template text). */
  async listTemplates() {
    const request = templatesRequest();
    const { status, body } = await this.send(request.method, request.route);
    return interpretTemplatesReply(status, body);
  }
  /** The cheap read-only health check the status bar and "Test connection" use. */
  async testConnection() {
    return this.listTemplates();
  }
  /* ------------------------------------------------------------------ */
  /* Write routes - every one raises Jarvis's own ONE card               */
  /* ------------------------------------------------------------------ */
  /** Capture to today's daily note through the existing capture route. */
  async captureToDaily(text2) {
    if (!(text2 != null ? text2 : "").trim()) {
      throw new ProtocolError("Write what should be captured first.", "invalid");
    }
    const request = captureRequest(text2);
    const { status, body } = await this.send(request.method, request.route, void 0, request.body);
    return interpretCaptureReply(status, body);
  }
  /** How one capture ended (a card can be answered on the PC after the first answer). */
  async captureStatus(jobId) {
    const request = captureStatusRequest(jobId);
    const { status, body } = await this.send(request.method, request.route, request.query);
    return interpretCaptureReply(status, body);
  }
  /** Add one line under the named heading of one note. */
  async insertUnderHeading(path, text2, heading, expectedSha) {
    const request = insertRequest(path, text2, heading, expectedSha);
    const { status, body } = await this.send(request.method, request.route, void 0, request.body);
    return interpretWriteReply(status, body);
  }
  /** Wrap one exact selection in bold or italic. */
  async formatSpan(path, target, style, action, expectedSha) {
    const request = formatRequest(path, target, style, action, expectedSha);
    const { status, body } = await this.send(request.method, request.route, void 0, request.body);
    return interpretWriteReply(status, body);
  }
  /** Replace one exact, whole-word occurrence (the selection) with new words. */
  async replaceOnce(path, oldText, newText, expectedSha) {
    const request = replaceRequest(path, oldText, newText, expectedSha);
    const { status, body } = await this.send(request.method, request.route, void 0, request.body);
    return interpretWriteReply(status, body);
  }
  /** Change one whole line's shape (this plugin uses it for "make it a checklist item"). */
  async customizeLine(path, lineAction, targetLine, expectedSha) {
    const request = customizeLineRequest(path, lineAction, targetLine, expectedSha);
    const { status, body } = await this.send(request.method, request.route, void 0, request.body);
    return interpretWriteReply(status, body);
  }
  /** Add one tag to one note (frontmatter list when the note has one, else a visible line). */
  async addTag(path, tag, expectedSha) {
    const clean = (tag != null ? tag : "").trim().replace(/^#+/, "");
    if (!clean) throw new ProtocolError("Type a tag name first.", "invalid");
    const request = tagRequest(path, clean, expectedSha);
    const { status, body } = await this.send(request.method, request.route, void 0, request.body);
    return interpretWriteReply(status, body);
  }
  /** Create ONE new note through the backend's create route (one card, collision refused). */
  async createNote(path, text2) {
    const request = createNoteRequest(path, text2);
    const { status, body } = await this.send(request.method, request.route, void 0, request.body);
    return interpretWriteReply(status, body);
  }
  /** How one write ended: waiting / saved / denied / failed (409 conflict). */
  async changeStatus(jobId) {
    const request = changeStatusRequest(jobId);
    const { status, body } = await this.send(request.method, request.route, request.query);
    return interpretStatusReply(status, body);
  }
  /* ------------------------------------------------------------------ */
  /* Waiting for a card that was answered on the PC                      */
  /* ------------------------------------------------------------------ */
  /**
   * Poll one write job until it is no longer waiting. This is how the plugin
   * waits for a card the owner answers in the Jarvis window - it never answers
   * one, and never claims a write landed before the backend says so.
   */
  async pollChange(jobId, onUpdate, shouldContinue) {
    let last = {
      kind: "waiting",
      message: "Waiting for the card on the PC.",
      jobId,
      sha256: "",
      currentSha256: "",
      httpStatus: 0
    };
    for (let attempt = 1; attempt <= POLL_MAX_ATTEMPTS; attempt++) {
      if (shouldContinue && !shouldContinue()) {
        return { ...last, message: "Stopped checking because the Jarvis panel closed. The write may still have happened." };
      }
      await sleep(pollDelayMs(attempt));
      const { status, body } = await this.send("GET", ROUTES.change, { id: jobId });
      last = interpretStatusReply(status, body);
      if (last.kind !== "waiting") return last;
      if (onUpdate) onUpdate(last.message);
    }
    return { ...last, message: pollGaveUpMessage() };
  }
  /** Poll one capture job the same way (filed / waiting / not_filed). */
  async pollCapture(jobId, onUpdate, shouldContinue) {
    let last = {
      kind: "waiting",
      message: "Waiting for the card on the PC.",
      jobId,
      httpStatus: 0
    };
    for (let attempt = 1; attempt <= POLL_MAX_ATTEMPTS; attempt++) {
      if (shouldContinue && !shouldContinue()) {
        return { ...last, message: "Stopped checking because the window closed. The capture may still have happened." };
      }
      await sleep(pollDelayMs(attempt));
      last = await this.captureStatus(jobId);
      if (last.kind !== "waiting") return last;
      if (onUpdate) onUpdate(last.message);
    }
    return { ...last, message: pollGaveUpMessage() };
  }
};

// src/modals.ts
var import_obsidian2 = require("obsidian");
var CARD_HINT = "This plugin cannot approve cards. If a card appears, answer it in the Jarvis window on the PC - nothing is written before you do.";
var AskModal = class extends import_obsidian2.Modal {
  constructor(app, plugin, contextText, notePath, options) {
    super(app);
    this.plugin = plugin;
    this.contextText = contextText;
    this.notePath = notePath;
    this.question = options.prefill;
    this.heading = options.title;
  }
  onOpen() {
    this.setTitle(this.heading);
    const { contentEl } = this;
    contentEl.createEl("p", {
      cls: "jarvis-hint",
      text: "Read-only: Jarvis answers here. It cannot change, save or approve anything from this dialog."
    });
    new import_obsidian2.Setting(contentEl).setName("Question").addTextArea((text2) => {
      text2.setValue(this.question).onChange((value) => {
        this.question = value;
      });
      text2.inputEl.rows = 4;
      text2.inputEl.addClass("jarvis-question");
      accessibleName(text2.inputEl, "Question");
    });
    const answer = contentEl.createEl("div", { cls: "jarvis-answer" });
    liveRegion(answer);
    answer.setText("Ask when ready.");
    new import_obsidian2.Setting(contentEl).addButton(
      (button) => button.setButtonText("Ask Jarvis").setCta().onClick(async () => {
        button.setDisabled(true);
        busy(answer, true);
        answer.setText("Asking the local Jarvis\u2026");
        try {
          const outcome = await this.plugin.client.askJarvis(
            this.question,
            this.contextText,
            this.notePath
          );
          answer.setText(
            outcome.kind === "ok" ? outcome.answer : "Could not ask Jarvis: " + outcome.message
          );
          liveRegion(answer, outcome.kind === "ok" ? "polite" : "assertive");
        } catch (error) {
          answer.setText("Could not ask Jarvis: " + shortError(error));
          liveRegion(answer, "assertive");
        } finally {
          button.setDisabled(false);
          busy(answer, false);
          button.buttonEl.focus();
        }
      })
    );
  }
};
var CaptureModal = class extends import_obsidian2.Modal {
  constructor(app, plugin, prefill) {
    super(app);
    this.plugin = plugin;
    this.text = prefill;
  }
  onOpen() {
    this.setTitle("Capture to today's Obsidian note");
    const { contentEl } = this;
    contentEl.createEl("p", { cls: "jarvis-hint", text: CARD_HINT });
    new import_obsidian2.Setting(contentEl).setName("What to capture").addTextArea((area) => {
      area.setValue(this.text).onChange((value) => {
        this.text = value;
      });
      area.inputEl.rows = 6;
      accessibleName(area.inputEl, "What to capture");
    });
    const said = contentEl.createEl("div", { cls: "jarvis-answer" });
    liveRegion(said);
    new import_obsidian2.Setting(contentEl).addButton(
      (button) => button.setButtonText("Capture").setCta().onClick(async () => {
        button.setDisabled(true);
        busy(said, true);
        said.setText("Sending to the local Jarvis\u2026");
        try {
          const outcome = await this.plugin.client.captureToDaily(this.text);
          said.setText(outcome.message);
          liveRegion(said, outcome.kind === "filed" || outcome.kind === "waiting" ? "polite" : "assertive");
          if (outcome.kind === "waiting" && outcome.jobId) {
            busy(said, false);
            said.setText(outcome.message + " Checking\u2026");
            const final = await this.plugin.client.pollCapture(
              outcome.jobId,
              (message) => said.setText(message + " Checking\u2026")
            );
            said.setText(final.message);
            liveRegion(said, final.kind === "filed" ? "polite" : "assertive");
          }
        } catch (error) {
          said.setText("Not captured: " + shortError(error));
          liveRegion(said, "assertive");
        } finally {
          button.setDisabled(false);
          busy(said, false);
          button.buttonEl.focus();
        }
      })
    );
  }
};
var ReplaceModal = class extends import_obsidian2.Modal {
  constructor(app, plugin, selection, path) {
    super(app);
    this.plugin = plugin;
    this.selection = selection;
    this.path = path;
    this.newText = "";
    this.resultEl = null;
  }
  onOpen() {
    this.setTitle("Replace the selection through Jarvis");
    const { contentEl } = this;
    contentEl.createEl("p", { cls: "jarvis-hint", text: CARD_HINT });
    new import_obsidian2.Setting(contentEl).setName("Selected words").setDesc(this.replacePreviewDescription()).addTextArea((area) => {
      area.setValue(clip(this.selection, 400));
      area.inputEl.readOnly = true;
      area.inputEl.setAttribute("aria-readonly", "true");
      accessibleName(area.inputEl, "Selected words (read only)");
      area.inputEl.rows = 2;
    });
    new import_obsidian2.Setting(contentEl).setName("Replace it with").addTextArea((area) => {
      area.setValue(this.newText).onChange((value) => {
        this.newText = value;
      });
      area.inputEl.rows = 4;
      accessibleName(area.inputEl, "Replacement words");
    });
    this.resultEl = contentEl.createEl("div", { cls: "jarvis-answer" });
    liveRegion(this.resultEl);
    new import_obsidian2.Setting(contentEl).addButton(
      (button) => button.setButtonText("Ask Jarvis to replace it").setCta().onClick(async () => {
        if (!this.newText.trim()) {
          this.showResult("Type the replacement words first.", "error");
          return;
        }
        button.setDisabled(true);
        const show = (message, kind) => this.showResult(message, kind);
        try {
          await this.plugin.performWrite(
            "Asking Jarvis to replace the selection in " + this.path,
            (sha) => this.plugin.client.replaceOnce(this.path, this.selection, this.newText, sha),
            show,
            this.path
          );
        } finally {
          button.setDisabled(false);
          button.buttonEl.focus();
        }
      })
    );
  }
  /** Say truthfully whether the read-only preview is the whole target or its first 400 characters. */
  replacePreviewDescription() {
    return this.selection.length > 400 ? "The first 400 characters of the exact text Jarvis will replace (one whole-word occurrence)." : "This exact text is what Jarvis will replace (one whole-word occurrence).";
  }
  showResult(message, kind) {
    if (!this.resultEl) return;
    this.resultEl.setText(message);
    this.resultEl.setAttribute("data-kind", kind != null ? kind : "");
    liveRegion(this.resultEl, isRefusalKind(kind) ? "assertive" : "polite");
  }
};
var TagModal = class extends import_obsidian2.Modal {
  constructor(app, plugin, path) {
    super(app);
    this.plugin = plugin;
    this.path = path;
    this.tag = "";
    this.resultEl = null;
  }
  onOpen() {
    this.setTitle("Tag this note through Jarvis");
    const { contentEl } = this;
    contentEl.createEl("p", { cls: "jarvis-hint", text: CARD_HINT });
    new import_obsidian2.Setting(contentEl).setName("Tag").setDesc("One tag, without the #: letters, numbers, _ - or /; at least one letter.").addText((text2) => {
      accessibleName(text2.inputEl, "Tag name");
      return text2.setPlaceholder("recipes").onChange((value) => {
        this.tag = value;
      });
    });
    this.resultEl = contentEl.createEl("div", { cls: "jarvis-answer" });
    liveRegion(this.resultEl);
    new import_obsidian2.Setting(contentEl).addButton(
      (button) => button.setButtonText("Ask Jarvis to add the tag").setCta().onClick(async () => {
        if (!this.tag.trim()) {
          this.showResult("Type a tag name first.", "error");
          return;
        }
        button.setDisabled(true);
        try {
          await this.plugin.performWrite(
            "Asking Jarvis to tag " + this.path,
            (sha) => this.plugin.client.addTag(this.path, this.tag, sha),
            (message, kind) => this.showResult(message, kind),
            this.path
          );
        } finally {
          button.setDisabled(false);
          button.buttonEl.focus();
        }
      })
    );
  }
  showResult(message, kind) {
    if (!this.resultEl) return;
    this.resultEl.setText(message);
    this.resultEl.setAttribute("data-kind", kind != null ? kind : "");
    liveRegion(this.resultEl, isRefusalKind(kind) ? "assertive" : "polite");
  }
};

// src/panel.ts
var import_obsidian3 = require("obsidian");

// src/templates.ts
var DEFAULT_TEMPLATES_FOLDER = "Templates";
function normalizeTemplatesFolder(raw) {
  const trimmed = (raw != null ? raw : "").trim().replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
  return trimmed || DEFAULT_TEMPLATES_FOLDER;
}
function cleanName(raw) {
  return (raw != null ? raw : "").trim().replace(/\.md$/i, "");
}
function mergeTemplateChoices(backendNames, vaultNames) {
  const byKey = /* @__PURE__ */ new Map();
  for (const raw of backendNames != null ? backendNames : []) {
    const name = cleanName(raw);
    if (!name) continue;
    const key = name.toLowerCase();
    const existing = byKey.get(key);
    if (existing) {
      existing.source = "both";
    } else {
      byKey.set(key, { name, source: "jarvis" });
    }
  }
  for (const raw of vaultNames != null ? vaultNames : []) {
    const name = cleanName(raw);
    if (!name) continue;
    const key = name.toLowerCase();
    const existing = byKey.get(key);
    if (existing) {
      existing.name = name;
      existing.source = "both";
    } else {
      byKey.set(key, { name, source: "vault" });
    }
  }
  return [...byKey.values()].sort((a, b) => a.name.localeCompare(b.name));
}
function templateSourceLabel(source) {
  if (source === "both") return "vault + Jarvis";
  if (source === "vault") return "vault";
  return "Jarvis only - text not readable here";
}
function templateLabel(choice) {
  return choice.name + " (" + templateSourceLabel(choice.source) + ")";
}
function canCreateFromTemplate(choice) {
  return choice.source !== "jarvis";
}
function templateFilePath(folder, name) {
  const cleanFolder = normalizeTemplatesFolder(folder);
  const clean = cleanName(name).replace(/^\/+|\/+$/g, "");
  return cleanFolder + "/" + clean + ".md";
}
function templateNotePath(name, folder = "") {
  const clean = cleanName(name).replace(/^\/+|\/+$/g, "");
  const parent = normalizeTemplatesFolder(folder).replace(/[\\/]+$/, "");
  if (!folder.trim()) return clean + ".md";
  return parent + "/" + clean + ".md";
}
var TEMPLATE_PREVIEW_CHARS = 600;

// src/panel.ts
var VIEW_TYPE_JARVIS_PANEL = "jarvis-notes-panel";
var READY_MESSAGE = "Ready. Every edit below goes through Jarvis's own one card; this panel never writes the note.";
var JarvisPanel = class extends import_obsidian3.ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.plugin = plugin;
    this.bodyEl = null;
    this.resultEl = null;
    this.question = "";
    /**
     * The insert draft, its heading and the note it was typed for. They are kept
     * together so a line typed for one note can never be sent for another: when
     * the active note changes, this panel clears the draft instead of carrying it.
     */
    this.insertDraft = "";
    this.insertHeading = "";
    this.insertNotePath = "";
    /** The template picker's choice and the new-note path, kept across re-renders. */
    this.templateChoice = "";
    this.templateNotePathValue = "";
    this.templatePathTouched = false;
    /** The last read-only answer, kept across re-renders so the panel does not lose it. */
    this.askAnswer = "Read-only: Jarvis answers here.";
    /** The last write result, kept across re-renders so the PC's sentence is not wiped. */
    this.lastResultMessage = READY_MESSAGE;
    this.lastResultKind = void 0;
  }
  getViewType() {
    return VIEW_TYPE_JARVIS_PANEL;
  }
  getDisplayText() {
    return "Jarvis";
  }
  getIcon() {
    return "message-square";
  }
  async onOpen() {
    this.bodyEl = this.containerEl.children[1];
    await this.render();
  }
  async render() {
    const el = this.bodyEl;
    if (!el) return;
    if (el.contains(document.activeElement)) return;
    el.empty();
    el.addClass("jarvis-panel");
    this.resultEl = null;
    el.createEl("h4", { text: "Jarvis" });
    const statusLine = el.createEl("p", { cls: "jarvis-status", text: this.plugin.statusText() });
    liveRegion(statusLine);
    this.resultEl = el.createDiv({ cls: "jarvis-result" });
    liveRegion(this.resultEl);
    this.applyResult();
    const checklist = firstRunChecklist(this.plugin.hasToken(), this.plugin.statusKind());
    if (checklist.next) {
      el.createEl("h5", { text: checklist.heading });
      const steps = el.createEl("ol", { cls: "jarvis-checklist" });
      for (const step of checklist.steps) steps.createEl("li", { text: step });
      const next = el.createEl("p", { cls: "jarvis-warning", text: checklist.next });
      liveRegion(next);
    }
    const context = await this.plugin.readNoteContext();
    if (!context) {
      el.createEl("p", {
        cls: "jarvis-hint",
        text: "Open a note to see its context and to ask Jarvis about it."
      });
      return;
    }
    el.createEl("h4", { text: context.title });
    el.createEl("p", { cls: "jarvis-path", text: context.path });
    this.section(el, "Headings", context.headings.map((heading) => headingLabel(heading)), 30);
    this.section(el, "Links", context.links, 30);
    this.section(el, "Linked from", context.backlinks, 30);
    this.section(el, "Unresolved links", context.unresolved, 30);
    this.section(el, "Frontmatter keys", context.frontmatterKeys, 30);
    if (context.truncated) {
      el.createEl("p", {
        cls: "jarvis-hint",
        text: "A very long note: only its first 12,000 characters are sent when you ask."
      });
    }
    this.renderAskBox(el, context);
    this.renderEditControls(el, context);
    el.createEl("p", {
      cls: "jarvis-hint",
      text: "The structured edit routes arrive with the notes-editor backend deploy. Before that deploy the edit buttons answer honestly that this backend does not have the route yet. Ask and Capture work on the shipped backend."
    });
  }
  /* ------------------------------------------------------------------ */
  /* Small builders                                                      */
  /* ------------------------------------------------------------------ */
  section(el, title, items, cap) {
    if (!items.length) return;
    el.createEl("h5", { text: title + " (" + items.length + ")" });
    const list = el.createEl("ul", { cls: "jarvis-list" });
    for (const item of items.slice(0, cap)) list.createEl("li", { text: item });
    if (items.length > cap) {
      list.createEl("li", { text: "\u2026 and " + (items.length - cap) + " more, not shown" });
    }
  }
  currentSelection() {
    var _a, _b;
    const view = this.app.workspace.getActiveViewOfType(import_obsidian3.MarkdownView);
    return ((_b = (_a = view == null ? void 0 : view.editor) == null ? void 0 : _a.getSelection()) != null ? _b : "").trim();
  }
  /**
   * Put one sentence into the panel's live result line. Public because the
   * plugin entry point uses it to explain a command that could not start (for
   * example "Open a note first.") inside a live region, not only in a toast.
   */
  showResult(message, kind) {
    this.lastResultMessage = message;
    this.lastResultKind = kind;
    this.applyResult();
  }
  applyResult() {
    var _a;
    if (!this.resultEl) return;
    this.resultEl.setText(this.lastResultMessage);
    this.resultEl.setAttribute("data-kind", (_a = this.lastResultKind) != null ? _a : "");
    liveRegion(this.resultEl, isRefusalKind(this.lastResultKind) ? "assertive" : "polite");
  }
  /* ------------------------------------------------------------------ */
  /* Wave 1: ask and capture                                             */
  /* ------------------------------------------------------------------ */
  renderAskBox(el, context) {
    el.createEl("h5", { text: "Ask about this note" });
    const input = el.createEl("textarea", { cls: "jarvis-panel-question" });
    input.rows = 3;
    input.value = this.question;
    input.placeholder = "What is unclear here? What should I link?";
    accessibleName(input, "Ask a question about this note");
    input.addEventListener("input", () => {
      this.question = input.value;
    });
    const row = el.createDiv({ cls: "jarvis-row" });
    group(row, "Ask and capture");
    const ask = row.createEl("button", { text: "Ask", cls: "mod-cta" });
    const capture = row.createEl("button", { text: "Capture selection" });
    const answer = el.createDiv({ cls: "jarvis-answer" });
    liveRegion(answer);
    answer.setText(this.askAnswer);
    ask.addEventListener("click", () => {
      void (async () => {
        ask.disabled = true;
        busy(answer, true);
        answer.setText("Asking the local Jarvis\u2026");
        try {
          const selection = boundedText(this.currentSelection(), MAX_SELECTION_CHARS);
          const contextText = buildContextText(context) + (selection.text ? "\n\nSelected text:" + (selection.truncated ? " (first " + MAX_SELECTION_CHARS + " characters only)" : "") + "\n" + selection.text : "");
          const outcome = await this.plugin.client.askJarvis(
            this.question || "What is this note about, and what could be clearer?",
            contextText,
            context.path
          );
          this.askAnswer = outcome.kind === "ok" ? outcome.answer : "Could not ask Jarvis: " + outcome.message;
          answer.setText(this.askAnswer);
          liveRegion(answer, outcome.kind === "ok" ? "polite" : "assertive");
        } catch (error) {
          this.askAnswer = "Could not ask Jarvis: " + shortError(error);
          answer.setText(this.askAnswer);
          liveRegion(answer, "assertive");
        } finally {
          ask.disabled = false;
          busy(answer, false);
          if (ask.isConnected) ask.focus();
        }
      })();
    });
    capture.addEventListener("click", () => {
      this.plugin.openCapture(this.currentSelection());
    });
  }
  /* ------------------------------------------------------------------ */
  /* Wave 2: structured edits                                            */
  /* ------------------------------------------------------------------ */
  renderEditControls(el, context) {
    var _a;
    el.createEl("h5", { text: "Edit this note through Jarvis" });
    el.createEl("p", {
      cls: "jarvis-hint",
      text: "Each edit raises Jarvis's own one card. Answer it in the Jarvis window on the PC; this panel only waits and reports."
    });
    if (this.insertNotePath !== context.path) {
      this.insertNotePath = context.path;
      this.insertDraft = "";
      this.insertHeading = "";
    }
    el.createEl("p", { cls: "jarvis-label", text: "Insert under a heading" });
    const headingSelect = el.createEl("select", { cls: "dropdown jarvis-select" });
    accessibleName(headingSelect, "Insert under which heading");
    if (context.headings.length) {
      for (const heading of context.headings) {
        const option = document.createElement("option");
        option.value = heading.text;
        option.text = headingLabel(heading);
        headingSelect.appendChild(option);
      }
      const remembered = context.headings.some((heading) => heading.text === this.insertHeading);
      headingSelect.value = remembered ? this.insertHeading : context.headings[0].text;
      this.insertHeading = headingSelect.value;
      headingSelect.addEventListener("change", () => {
        this.insertHeading = headingSelect.value;
      });
    } else {
      const option = document.createElement("option");
      option.value = "";
      option.text = "This note has no headings";
      option.disabled = true;
      headingSelect.appendChild(option);
    }
    const insertInput = el.createEl("textarea", { cls: "jarvis-panel-question" });
    insertInput.rows = 2;
    insertInput.value = this.insertDraft;
    insertInput.placeholder = "One line to add at the end of that section";
    accessibleName(insertInput, "Line to insert under the heading");
    insertInput.addEventListener("input", () => {
      this.insertDraft = insertInput.value;
    });
    const insertRow = el.createDiv({ cls: "jarvis-row" });
    const insertButton = insertRow.createEl("button", { text: "Insert under heading", cls: "mod-cta" });
    insertButton.disabled = context.headings.length === 0;
    if (insertButton.disabled) hint(insertButton, "This note has no headings to insert under.");
    insertButton.addEventListener("click", () => {
      void this.insertUnderHeading(insertButton, headingSelect, insertInput);
    });
    const selection = this.currentSelection();
    const view = this.app.workspace.getActiveViewOfType(import_obsidian3.MarkdownView);
    const editor = (_a = view == null ? void 0 : view.editor) != null ? _a : null;
    el.createEl("p", {
      cls: "jarvis-label",
      text: selection ? "Selection: " + clip(selection, 160) : "Selection actions"
    });
    if (!selection) {
      el.createEl("p", {
        cls: "jarvis-hint",
        text: "Select text in the note to use Bold / Italic / Checklist / Replace. Set tag works on the whole note."
      });
    }
    const selectionRow = el.createDiv({ cls: "jarvis-row jarvis-row-wrap" });
    group(selectionRow, "Edit the selection through Jarvis");
    const bold = selectionRow.createEl("button", { text: "Bold" });
    const italic = selectionRow.createEl("button", { text: "Italic" });
    const checklist = selectionRow.createEl("button", { text: "Checklist" });
    const replace = selectionRow.createEl("button", { text: "Replace\u2026" });
    const tag = selectionRow.createEl("button", { text: "Set tag\u2026" });
    accessibleName(bold, "Make the selection bold through Jarvis");
    accessibleName(italic, "Make the selection italic through Jarvis");
    accessibleName(checklist, "Turn the selection's line into a checklist item through Jarvis");
    accessibleName(replace, "Replace the selection through Jarvis");
    accessibleName(tag, "Set a tag on this note through Jarvis");
    bold.addEventListener("click", () => void this.formatSelection(bold, "bold"));
    italic.addEventListener("click", () => void this.formatSelection(italic, "italic"));
    checklist.addEventListener("click", () => void this.checklistLine(checklist));
    replace.addEventListener("click", () => {
      if (!editor) {
        this.showResult("Open a note with an editor first.", "error");
        return;
      }
      this.plugin.openReplace(editor);
    });
    tag.addEventListener("click", () => this.plugin.openTag());
    el.createEl("h5", { text: "New note from a template" });
    el.createEl("p", {
      cls: "jarvis-hint",
      text: "Names come from Jarvis (read-only) and from the vault Templates folder. The note is created by Jarvis's create route, one card."
    });
    const templateSelect = el.createEl("select", { cls: "dropdown jarvis-select" });
    accessibleName(templateSelect, "Template for a new note");
    const templatePreview = el.createDiv({ cls: "jarvis-template-preview" });
    liveRegion(templatePreview);
    accessibleName(templatePreview, "Template preview (read only)");
    templatePreview.tabIndex = 0;
    const templatePath = document.createElement("input");
    templatePath.type = "text";
    templatePath.className = "jarvis-text";
    templatePath.placeholder = "New note path, vault-relative (for example project.md)";
    accessibleName(templatePath, "New note path in the vault");
    templatePath.value = this.templateNotePathValue;
    templatePath.addEventListener("input", () => {
      this.templateNotePathValue = templatePath.value;
      this.templatePathTouched = true;
    });
    el.appendChild(templatePath);
    const createRow = el.createDiv({ cls: "jarvis-row" });
    const createButton = createRow.createEl("button", { text: "Create note from template", cls: "mod-cta" });
    createButton.addEventListener("click", () => {
      void this.createFromTemplate(createButton, templateSelect, templatePath);
    });
    void this.fillTemplates(templateSelect, templatePreview, templatePath, createButton);
  }
  async insertUnderHeading(button, headingSelect, insertInput) {
    const text2 = insertInput.value.trim();
    const heading = headingSelect.value;
    const path = this.insertNotePath || this.plugin.activeFilePath();
    if (!text2) {
      this.showResult("Type the line to add first.", "error");
      return;
    }
    if (!heading || !path) {
      this.showResult("Pick a heading and open a note first.", "error");
      return;
    }
    if (this.plugin.activeFilePath() !== path) {
      this.showResult(
        "The active note changed, so nothing was sent. The line still belongs to " + path + " - open that note again and retry.",
        "error"
      );
      return;
    }
    button.disabled = true;
    try {
      await this.plugin.performWrite(
        'Asking Jarvis to add a line under "' + heading + '"',
        (sha) => this.plugin.client.insertUnderHeading(path, text2, heading, sha),
        (message, kind) => this.showResult(message, kind),
        path
      );
    } finally {
      button.disabled = false;
      if (button.isConnected) button.focus();
    }
  }
  async formatSelection(button, style) {
    const selection = this.currentSelection();
    const path = this.plugin.activeFilePath();
    if (!selection) {
      this.showResult("Select some text first.", "error");
      return;
    }
    if (!path) {
      this.showResult("Open a note first.", "error");
      return;
    }
    button.disabled = true;
    try {
      await this.plugin.performWrite(
        "Asking Jarvis to make the selection " + style,
        (sha) => this.plugin.client.formatSpan(path, selection, style, "add", sha),
        (message, kind) => this.showResult(message, kind),
        path
      );
    } finally {
      button.disabled = false;
      if (button.isConnected) button.focus();
    }
  }
  async checklistLine(button) {
    var _a, _b;
    const view = this.app.workspace.getActiveViewOfType(import_obsidian3.MarkdownView);
    const editor = (_a = view == null ? void 0 : view.editor) != null ? _a : null;
    const path = this.plugin.activeFilePath();
    const line = editor ? ((_b = editor.getLine(editor.getCursor("from").line)) != null ? _b : "").trim() : "";
    if (!line || !path) {
      this.showResult("Put the cursor on a line in a note first.", "error");
      return;
    }
    button.disabled = true;
    try {
      await this.plugin.performWrite(
        "Asking Jarvis to turn that line into a checklist item",
        (sha) => this.plugin.client.customizeLine(path, "checklist", line, sha),
        (message, kind) => this.showResult(message, kind),
        path
      );
    } finally {
      button.disabled = false;
      if (button.isConnected) button.focus();
    }
  }
  /* ------------------------------------------------------------------ */
  /* Templates (read-only outside the backend's create route)            */
  /* ------------------------------------------------------------------ */
  vaultTemplateNames() {
    const folder = normalizeTemplatesFolder(this.plugin.settings.templatesFolder).toLowerCase();
    return this.app.vault.getFiles().filter(
      (file) => {
        var _a, _b;
        return file.extension === "md" && ((_b = (_a = file.parent) == null ? void 0 : _a.path) != null ? _b : "").toLowerCase() === folder;
      }
    ).map((file) => file.basename);
  }
  async readVaultTemplate(filePath) {
    const file = this.app.vault.getAbstractFileByPath(filePath);
    if (!(file instanceof import_obsidian3.TFile)) {
      throw new Error("There is no template file at " + filePath + " in this vault.");
    }
    return await this.app.vault.cachedRead(file);
  }
  async fillTemplates(select, preview, pathInput, createButton) {
    if (!select.isConnected) return;
    let backendNames = [];
    let backendWhy = "";
    try {
      const answer = await this.plugin.client.listTemplates();
      if (answer.kind === "ok") {
        backendNames = answer.names;
        backendWhy = answer.why;
      }
    } catch (e) {
      backendNames = [];
    }
    if (!select.isConnected) return;
    const choices = mergeTemplateChoices(backendNames, this.vaultTemplateNames());
    select.replaceChildren();
    if (!choices.length) {
      const option = document.createElement("option");
      option.value = "";
      option.text = "No templates found (Jarvis has none, and the Templates folder is empty)";
      option.disabled = true;
      select.appendChild(option);
      preview.setText(backendWhy ? "Jarvis said: " + backendWhy : "");
      createButton.disabled = true;
      hint(createButton, "No template can be read from this vault yet, so there is nothing to create.");
      return;
    }
    for (const choice of choices) {
      const option = document.createElement("option");
      option.value = choice.name;
      option.text = templateLabel(choice);
      select.appendChild(option);
    }
    const firstUsable = choices.find((choice) => canCreateFromTemplate(choice));
    const remembered = choices.find(
      (choice) => choice.name === this.templateChoice && canCreateFromTemplate(choice)
    );
    const initial = remembered != null ? remembered : firstUsable;
    select.value = initial ? initial.name : "";
    if (initial) this.templateChoice = initial.name;
    createButton.disabled = select.value === "";
    const refresh = () => {
      void (async () => {
        const name = select.value;
        this.templateChoice = name;
        if (!name) {
          preview.setText("");
          createButton.disabled = true;
          hint(createButton, "Pick a template first.");
          return;
        }
        const choice = choices.find((candidate) => candidate.name === name);
        createButton.disabled = !choice || !canCreateFromTemplate(choice);
        hint(
          createButton,
          createButton.disabled ? "That template's text cannot be read from this vault, so this plugin will not invent a body." : "Create this note through Jarvis's one card."
        );
        const filePath = templateFilePath(this.plugin.settings.templatesFolder, name);
        try {
          const body = await this.readVaultTemplate(filePath);
          preview.setText("Preview (read-only):\n" + clip(body, TEMPLATE_PREVIEW_CHARS));
          if (!this.templatePathTouched) {
            pathInput.value = templateNotePath(name);
            this.templateNotePathValue = pathInput.value;
          }
        } catch (error) {
          preview.setText(
            "This template's text cannot be read from the vault (" + shortError(error) + "). Jarvis knows the name, but no route sends template text back, so this plugin will not invent a body."
          );
        }
      })();
    };
    select.onchange = refresh;
    refresh();
  }
  async createFromTemplate(button, select, pathInput) {
    const name = select.value;
    if (!name) {
      this.showResult("Pick a template first.", "error");
      return;
    }
    let body;
    try {
      body = await this.readVaultTemplate(
        templateFilePath(this.plugin.settings.templatesFolder, name)
      );
    } catch (error) {
      this.showResult("Cannot read that template: " + shortError(error), "error");
      return;
    }
    const target = pathInput.value.trim() || templateNotePath(name);
    button.disabled = true;
    try {
      await this.plugin.performWriteUnhashed(
        "Asking Jarvis to create " + target,
        () => this.plugin.client.createNote(target, body),
        (message, kind) => this.showResult(message, kind)
      );
    } finally {
      button.disabled = false;
      if (button.isConnected) button.focus();
    }
  }
};

// src/settings.ts
var import_obsidian4 = require("obsidian");
var JarvisSettingsTab = class extends import_obsidian4.PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.plugin = plugin;
  }
  display() {
    const { containerEl } = this;
    containerEl.empty();
    containerEl.createEl("p", {
      text: "The Jarvis notes bridge talks to the Jarvis backend running on this PC. It never writes a note itself and it never approves a card: every edit goes through Jarvis's own one-card routes."
    });
    new import_obsidian4.Setting(containerEl).setName("Jarvis backend URL").setDesc("The local backend only - usually http://127.0.0.1:4719.").addText((text2) => {
      accessibleName(text2.inputEl, "Jarvis backend URL");
      return text2.setPlaceholder(DEFAULT_BACKEND).setValue(this.plugin.settings.backendUrl).onChange(async (value) => {
        this.plugin.settings.backendUrl = value.trim();
        await this.plugin.saveSettings();
        refreshLoopbackWarning();
      });
    });
    const loopbackWarning = containerEl.createEl("p", { cls: "jarvis-warning" });
    liveRegion(loopbackWarning);
    const refreshLoopbackWarning = () => {
      const url = this.plugin.settings.backendUrl || DEFAULT_BACKEND;
      loopbackWarning.setText(
        isLoopbackUrl(url) ? "" : "This address is not on this PC. The Jarvis token would be sent to that host - only do this if you mean it."
      );
    };
    refreshLoopbackWarning();
    let pickerShown = false;
    try {
      new import_obsidian4.Setting(containerEl).setName("Token in SecretStorage (preferred)").setDesc(
        "Pick the Obsidian secret that holds the Jarvis pairing token. The token itself is not stored in this plugin's data.json."
      ).addComponent(
        (el) => new import_obsidian4.SecretComponent(this.app, el).setValue(this.plugin.settings.secretName).onChange(async (value) => {
          this.plugin.settings.secretName = value != null ? value : "";
          await this.plugin.saveSettings();
        })
      );
      pickerShown = true;
    } catch (e) {
      pickerShown = false;
    }
    if (!pickerShown) {
      containerEl.createEl("p", {
        cls: "jarvis-warning",
        text: "SecretStorage is not available in this Obsidian version; use the fallback token field below, or type the secret's name if your Obsidian stores secrets but cannot show the picker."
      });
      new import_obsidian4.Setting(containerEl).setName("Token in SecretStorage - the secret's name").setDesc("The name only (not the token). Leave empty to use the fallback token below.").addText((text2) => {
        accessibleName(text2.inputEl, "Token in SecretStorage - the secret's name");
        return text2.setPlaceholder("Jarvis token").setValue(this.plugin.settings.secretName).onChange(async (value) => {
          this.plugin.settings.secretName = value.trim();
          await this.plugin.saveSettings();
        });
      });
    }
    new import_obsidian4.Setting(containerEl).setName("Fallback token (stored on this PC, not encrypted by Obsidian)").setDesc(
      "Only when SecretStorage is not used. This value is saved in this plugin's data.json in the vault's .obsidian folder. Fine for a test vault; prefer SecretStorage for your real vault. Never paste this token into a note."
    ).addText((text2) => {
      text2.inputEl.type = "password";
      accessibleName(text2.inputEl, "Fallback token - stored on this PC, not encrypted by Obsidian");
      return text2.setPlaceholder("paste the Jarvis pairing token").setValue(this.plugin.settings.fallbackToken).onChange(async (value) => {
        this.plugin.settings.fallbackToken = value.trim();
        await this.plugin.saveSettings();
      });
    });
    new import_obsidian4.Setting(containerEl).setName("Templates folder").setDesc(
      "The vault folder this plugin lists templates from (read-only). Default: " + DEFAULT_TEMPLATES_FOLDER + "."
    ).addText((text2) => {
      accessibleName(text2.inputEl, "Templates folder");
      return text2.setPlaceholder(DEFAULT_TEMPLATES_FOLDER).setValue(this.plugin.settings.templatesFolder).onChange(async (value) => {
        this.plugin.settings.templatesFolder = value.trim();
        await this.plugin.saveSettings();
      });
    });
    containerEl.createEl("h3", { text: "Connection" });
    const result = containerEl.createEl("p", { cls: "jarvis-hint" });
    liveRegion(result);
    new import_obsidian4.Setting(containerEl).setName("Test connection").setDesc("Checks the token against a read-only Jarvis route (it does not call the model).").addButton(
      (button) => button.setButtonText("Test connection").onClick(async () => {
        result.setText("Testing\u2026");
        busy(result, true);
        button.setDisabled(true);
        try {
          const answer = await this.plugin.client.testConnection();
          if (answer.kind === "ok") {
            result.setText(
              "Connected. This Jarvis knows " + answer.names.length + " template name(s)." + (answer.why ? " It said: " + answer.why : "")
            );
          } else {
            result.setText("Not connected: " + answer.message);
          }
        } catch (error) {
          result.setText(
            "Not connected: " + (error instanceof Error ? error.message : String(error))
          );
        } finally {
          button.setDisabled(false);
          busy(result, false);
          button.buttonEl.focus();
          await this.plugin.refreshStatus();
        }
      })
    );
    containerEl.createEl("p", {
      cls: "jarvis-hint",
      text: "The token is read fresh from SecretStorage (or the fallback field) each time a request is sent. It is never written to a note, never put in a URL and never logged."
    });
  }
};

// src/main.ts
var DEFAULT_SETTINGS = {
  backendUrl: DEFAULT_BACKEND,
  secretName: "",
  fallbackToken: "",
  templatesFolder: DEFAULT_TEMPLATES_FOLDER
};
var JarvisNotesPlugin = class extends import_obsidian5.Plugin {
  constructor() {
    super(...arguments);
    this.settings = { ...DEFAULT_SETTINGS };
    this.statusEl = null;
    this.statusBusy = false;
    this.lastStatus = "Jarvis: checking\u2026";
    /** The same state as `lastStatus`, as a value the panel can act on. */
    this.lastStatusKind = "unknown";
    /** One write at a time: a second card while the first waits is only confusing. */
    this.writeBusy = false;
  }
  async onload() {
    await this.loadSettings();
    this.client = new JarvisClient(
      () => this.settings.backendUrl,
      () => this.getToken()
    );
    this.registerView(VIEW_TYPE_JARVIS_PANEL, (leaf) => new JarvisPanel(leaf, this));
    this.addSettingTab(new JarvisSettingsTab(this.app, this));
    this.addCommand({
      id: "ask-jarvis-about-this-note",
      name: "Ask Jarvis about this note",
      callback: () => void this.askAboutActiveNote()
    });
    this.addCommand({
      id: "ask-jarvis-about-selection",
      name: "Ask Jarvis about the selection",
      editorCallback: (editor) => this.askAboutSelection(editor)
    });
    this.addCommand({
      id: "capture-to-todays-note",
      name: "Capture to today's note",
      callback: () => {
        var _a, _b;
        const view = this.app.workspace.getActiveViewOfType(import_obsidian5.MarkdownView);
        this.openCapture((_b = (_a = view == null ? void 0 : view.editor) == null ? void 0 : _a.getSelection()) != null ? _b : "");
      }
    });
    this.addCommand({
      id: "open-jarvis-panel",
      name: "Open the Jarvis panel",
      callback: () => void this.activatePanel()
    });
    this.addCommand({
      id: "jarvis-make-selection-bold",
      name: "Through Jarvis: make the selection bold",
      editorCallback: (editor) => void this.formatSelection(editor, "bold")
    });
    this.addCommand({
      id: "jarvis-make-selection-italic",
      name: "Through Jarvis: make the selection italic",
      editorCallback: (editor) => void this.formatSelection(editor, "italic")
    });
    this.addCommand({
      id: "jarvis-checklist-selection-line",
      name: "Through Jarvis: turn the selection's line into a checklist item",
      editorCallback: (editor) => void this.checklistSelectionLine(editor)
    });
    this.addCommand({
      id: "jarvis-replace-selection",
      name: "Through Jarvis: replace the selection\u2026",
      editorCallback: (editor) => this.openReplace(editor)
    });
    this.addCommand({
      id: "jarvis-tag-this-note",
      name: "Through Jarvis: tag this note\u2026",
      callback: () => this.openTag()
    });
    this.addCommand({
      id: "copy-obsidian-link-to-this-note",
      name: "Copy an Obsidian link to this note (read-only)",
      callback: () => void this.copyObsidianLink()
    });
    this.addRibbonIcon("message-square", "Open the Jarvis panel", () => {
      void this.activatePanel();
    });
    this.statusEl = this.addStatusBarItem();
    this.statusEl.setText(this.lastStatus);
    liveRegion(this.statusEl);
    this.registerInterval(
      window.setInterval(() => void this.refreshStatus(), 6e4)
    );
    void this.refreshStatus();
    this.registerEvent(
      this.app.workspace.on("active-leaf-change", () => {
        this.refreshPanels();
        void this.refreshStatus();
      })
    );
    this.registerEvent(
      this.app.metadataCache.on("changed", (file) => {
        if (this.activeFilePath() === file.path) this.refreshPanels();
      })
    );
  }
  onunload() {
  }
  /* ------------------------------------------------------------------ */
  /* Settings and token                                                  */
  /* ------------------------------------------------------------------ */
  async loadSettings() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }
  async saveSettings() {
    await this.saveData(this.settings);
    await this.refreshStatus();
  }
  /**
   * The token, read fresh at request time.
   *
   * Preferred: Obsidian's SecretStorage (the plugin stores only the secret's
   * NAME in data.json). Fallback: the plain setting, which is stored in this
   * plugin's data.json on this PC - the settings tab warns about that.
   */
  getToken() {
    const store = this.app.secretStorage;
    if (this.settings.secretName && (store == null ? void 0 : store.getSecret)) {
      try {
        const value = store.getSecret(this.settings.secretName);
        if (value) return value;
      } catch (e) {
      }
    }
    return this.settings.fallbackToken;
  }
  hasToken() {
    var _a;
    return ((_a = this.getToken()) != null ? _a : "").trim().length > 0;
  }
  /* ------------------------------------------------------------------ */
  /* The active note's bounded, read-only context                        */
  /* ------------------------------------------------------------------ */
  activeFilePath() {
    var _a, _b, _c;
    return (_c = (_b = (_a = this.app.workspace.getActiveViewOfType(import_obsidian5.MarkdownView)) == null ? void 0 : _a.file) == null ? void 0 : _b.path) != null ? _c : "";
  }
  /**
   * A bounded read-only context pack, from Obsidian's own metadata cache plus
   * the editor's current text. Nothing here writes anything.
   */
  async readNoteContext() {
    var _a, _b, _c, _d, _e, _f, _g;
    const view = this.app.workspace.getActiveViewOfType(import_obsidian5.MarkdownView);
    const file = (_a = view == null ? void 0 : view.file) != null ? _a : null;
    if (!file) return null;
    const cache = this.app.metadataCache.getFileCache(file);
    const headings = (_c = (_b = cache == null ? void 0 : cache.headings) == null ? void 0 : _b.map((heading) => ({ level: heading.level, text: heading.heading })).slice(0, MAX_HEADINGS)) != null ? _c : [];
    const outgoing = [];
    const backlinks = [];
    const resolved = this.app.metadataCache.resolvedLinks;
    for (const [source, targets] of Object.entries(resolved)) {
      if (source === file.path) {
        for (const target of Object.keys(targets)) {
          if (outgoing.length < MAX_LINKS) outgoing.push(target);
        }
      }
      if (Object.prototype.hasOwnProperty.call(targets, file.path) && backlinks.length < MAX_LINKS) {
        backlinks.push(source);
      }
    }
    const unresolved = [];
    for (const link of (_d = cache == null ? void 0 : cache.links) != null ? _d : []) {
      if (unresolved.length >= MAX_LINKS) break;
      if (!this.app.metadataCache.getFirstLinkpathDest(link.link, file.path)) {
        unresolved.push(link.link);
      }
    }
    let text2 = "";
    let truncated = false;
    try {
      text2 = (_f = (_e = view == null ? void 0 : view.editor) == null ? void 0 : _e.getValue()) != null ? _f : await this.app.vault.cachedRead(file);
      if (text2.length > MAX_CONTEXT_CHARS) {
        text2 = text2.slice(0, MAX_CONTEXT_CHARS);
        truncated = true;
      }
    } catch (e) {
      text2 = "";
    }
    return {
      path: file.path,
      title: file.basename,
      headings,
      links: outgoing,
      backlinks,
      unresolved,
      frontmatterKeys: Object.keys((_g = cache == null ? void 0 : cache.frontmatter) != null ? _g : {}).slice(0, MAX_FRONTMATTER_KEYS),
      text: text2,
      truncated
    };
  }
  /* ------------------------------------------------------------------ */
  /* Read-only asks                                                      */
  /* ------------------------------------------------------------------ */
  async askAboutActiveNote() {
    var _a, _b, _c;
    const context = await this.readNoteContext();
    if (!context) {
      this.explain("Open a note first.");
      return;
    }
    const selection = (_c = (_b = (_a = this.app.workspace.getActiveViewOfType(import_obsidian5.MarkdownView)) == null ? void 0 : _a.editor) == null ? void 0 : _b.getSelection()) != null ? _c : "";
    const bounded = boundedText(selection.trim(), MAX_SELECTION_CHARS);
    const contextText = buildContextText(context) + (bounded.text ? "\n\nSelected text:" + (bounded.truncated ? " (first " + MAX_SELECTION_CHARS + " characters only)" : "") + "\n" + bounded.text : "");
    new AskModal(this.app, this, contextText, context.path, {
      prefill: bounded.text ? "Explain this part of the note and suggest a clearer version:\n" + clip(bounded.text, 2e3) : "What is this note about, and what could be clearer?",
      title: "Ask Jarvis about " + context.path
    }).open();
  }
  askAboutSelection(editor) {
    var _a;
    const selection = ((_a = editor.getSelection()) != null ? _a : "").trim();
    if (!selection) {
      this.explain("Select some text first.");
      return;
    }
    const path = this.activeFilePath() || "this note";
    const bounded = boundedText(selection, MAX_SELECTION_CHARS);
    new AskModal(
      this.app,
      this,
      "Selected text from " + path + (bounded.truncated ? " (first " + MAX_SELECTION_CHARS + " characters only)" : "") + ":\n" + bounded.text,
      path,
      {
        prefill: "Explain this and suggest a clearer version:",
        title: "Ask Jarvis about the selection"
      }
    ).open();
  }
  /* ------------------------------------------------------------------ */
  /* Capture                                                             */
  /* ------------------------------------------------------------------ */
  openCapture(prefill) {
    new CaptureModal(this.app, this, prefill).open();
  }
  /* ------------------------------------------------------------------ */
  /* Wave 2 structured edits                                             */
  /* ------------------------------------------------------------------ */
  openReplace(editor) {
    var _a;
    const selection = ((_a = editor.getSelection()) != null ? _a : "").trim();
    if (!selection) {
      this.explain("Select the exact words to replace first.");
      return;
    }
    const path = this.activeFilePath();
    if (!path) {
      this.explain("Open a note first.");
      return;
    }
    new ReplaceModal(this.app, this, selection, path).open();
  }
  openTag() {
    const path = this.activeFilePath();
    if (!path) {
      this.explain("Open a note first.");
      return;
    }
    new TagModal(this.app, this, path).open();
  }
  /* ------------------------------------------------------------------ */
  /* The read-only direction: an obsidian://open link to this note       */
  /* ------------------------------------------------------------------ */
  /**
   * Copy the read-only `obsidian://open` link for the active note, so it can be
   * pasted where a person (or Jarvis's own answer) can open that note.
   *
   * This builds an OPEN link only. It never builds `new`, `daily`, `unique` or
   * the `prepend`/`append` actions those take: those write a note immediately,
   * which would bypass Jarvis's one card, the File Guardian copy and Undo.
   */
  async copyObsidianLink() {
    const path = this.activeFilePath();
    if (!path) {
      this.explain("Open a note first.");
      return;
    }
    const uri = obsidianOpenUri(this.app.vault.getName(), path);
    try {
      await navigator.clipboard.writeText(uri);
      new import_obsidian5.Notice("Copied the Obsidian link: " + uri, 8e3);
    } catch (error) {
      new import_obsidian5.Notice(
        "Could not copy the link (" + shortError(error) + "). The link is: " + uri,
        12e3
      );
    }
  }
  async formatSelection(editor, style) {
    var _a;
    const selection = ((_a = editor.getSelection()) != null ? _a : "").trim();
    if (!selection) {
      this.explain("Select some text first.");
      return;
    }
    const path = this.activeFilePath();
    if (!path) {
      this.explain("Open a note first.");
      return;
    }
    await this.performWrite(
      "Asking Jarvis to make the selection " + style,
      (sha) => this.client.formatSpan(path, selection, style, "add", sha),
      (message, kind) => this.showFromCommand(message, kind),
      path
    );
  }
  async checklistSelectionLine(editor) {
    var _a;
    const line = ((_a = editor.getLine(editor.getCursor("from").line)) != null ? _a : "").trim();
    if (!line) {
      this.explain("Put the cursor on a line first.");
      return;
    }
    const path = this.activeFilePath();
    if (!path) {
      this.explain("Open a note first.");
      return;
    }
    await this.performWrite(
      "Asking Jarvis to turn that line into a checklist item",
      (sha) => this.client.customizeLine(path, "checklist", line, sha),
      (message, kind) => this.showFromCommand(message, kind),
      path
    );
  }
  /* ------------------------------------------------------------------ */
  /* One shared write flow: read the hash, call the route, wait honestly */
  /* ------------------------------------------------------------------ */
  /**
   * The ONE write flow every edit uses.
   *
   *  1. read the note's current sha256 from the backend (so the edit can carry
   *     the hash it started from, and the backend can refuse a raced edit);
   *  2. call the chosen route; the backend raises its OWN one card;
   *  3. show the backend's own sentence;
   *  4. if a card is waiting, poll GET /api/notes/change until the owner
   *     answers it on the PC, and show the backend's final sentence.
   *
   * `targetPath` is the note the edit was started for. Passing it means a note
   * switch between the button press and the confirm cannot make the flow read a
   * different note's hash; the Replace and Tag dialogs pass the path they
   * captured when they opened.
   *
   * Only ONE write runs at a time: a second card while the first is waiting is
   * confusing, so the next attempt is told to answer or dismiss the first card
   * (the backend would refuse the loser anyway, with its own hash check).
   *
   * This method never writes a note, never approves a card, and never turns an
   * error or a "waiting" into a "saved".
   */
  async performWrite(label, start, show, targetPath) {
    if (this.writeBusy) {
      show("Another Jarvis edit is already waiting. Answer or dismiss that card first.", "waiting");
      return;
    }
    this.writeBusy = true;
    try {
      show(label + "\u2026", "waiting");
      let outcome;
      try {
        const path = targetPath != null ? targetPath : this.activeFilePath();
        if (!path) throw new ProtocolError("Open a note first.", "invalid");
        const read = await this.client.readNote(path);
        if (read.kind !== "ok") throw new ProtocolError(read.message);
        outcome = await start(read.sha256);
      } catch (error) {
        show("Could not ask Jarvis: " + shortError(error), "error");
        return;
      }
      show(outcome.message, outcome.kind);
      if (!shouldPoll(outcome)) return;
      try {
        const final = await this.client.pollChange(
          outcome.jobId,
          (message) => show(message, "waiting")
        );
        show(final.message, final.kind);
      } catch (error) {
        show(
          "Lost contact with Jarvis while checking the card: " + shortError(error) + " The write may still have happened - check Jarvis on the PC, then reopen the panel.",
          "error"
        );
      }
    } finally {
      this.writeBusy = false;
    }
  }
  /**
   * The same honest flow for a write that needs no starting hash: creating ONE
   * new note from a template. Nothing is overwritten, so there is no hash to
   * carry; the backend still raises its own one card, keeps collision refusal
   * and records the Undo receipt.
   */
  async performWriteUnhashed(label, start, show) {
    if (this.writeBusy) {
      show("Another Jarvis edit is already waiting. Answer or dismiss that card first.", "waiting");
      return;
    }
    this.writeBusy = true;
    try {
      show(label + "\u2026", "waiting");
      let outcome;
      try {
        outcome = await start();
      } catch (error) {
        show("Could not ask Jarvis: " + shortError(error), "error");
        return;
      }
      show(outcome.message, outcome.kind);
      if (!shouldPoll(outcome)) return;
      try {
        const final = await this.client.pollChange(
          outcome.jobId,
          (message) => show(message, "waiting")
        );
        show(final.message, final.kind);
      } catch (error) {
        show(
          "Lost contact with Jarvis while checking the card: " + shortError(error) + " The write may still have happened - check Jarvis on the PC, then reopen the panel.",
          "error"
        );
      }
    } finally {
      this.writeBusy = false;
    }
  }
  /* ------------------------------------------------------------------ */
  /* Panel                                                               */
  /* ------------------------------------------------------------------ */
  async activatePanel() {
    var _a;
    let leaf = (_a = this.app.workspace.getLeavesOfType(VIEW_TYPE_JARVIS_PANEL)[0]) != null ? _a : null;
    if (!leaf) {
      leaf = this.app.workspace.getRightLeaf(false);
      if (!leaf) return;
      await leaf.setViewState({ type: VIEW_TYPE_JARVIS_PANEL, active: true });
    }
    this.app.workspace.revealLeaf(leaf);
    this.refreshPanels();
  }
  refreshPanels() {
    for (const leaf of this.app.workspace.getLeavesOfType(VIEW_TYPE_JARVIS_PANEL)) {
      const view = leaf.view;
      if (view instanceof JarvisPanel) void view.render();
    }
  }
  /**
   * Put one sentence into an open panel's live result line. Returns false when
   * no panel is open, so the caller can fall back to a Notice.
   *
   * WHY: a toast is not reliably announced, and it disappears. The panel's
   * result line is a live region, so a command that cannot start ("Open a note
   * first.") is both heard and still readable afterwards.
   */
  tellPanel(message, kind = "error") {
    let told = false;
    for (const leaf of this.app.workspace.getLeavesOfType(VIEW_TYPE_JARVIS_PANEL)) {
      const view = leaf.view;
      if (view instanceof JarvisPanel) {
        view.showResult(message, kind);
        told = true;
      }
    }
    return told;
  }
  /** Explain a failed command in the live panel line when one is open, else a Notice. */
  explain(message, kind = "error") {
    if (!this.tellPanel(message, kind)) new import_obsidian5.Notice(message);
  }
  /** One write update from a command: live panel line when open, else a Notice. */
  showFromCommand(message, kind) {
    if (!this.tellPanel(message, kind)) new import_obsidian5.Notice(message, 8e3);
  }
  /* ------------------------------------------------------------------ */
  /* Status bar + Test connection                                        */
  /* ------------------------------------------------------------------ */
  renderStatus() {
    if (this.statusEl) this.statusEl.setText(this.lastStatus);
  }
  /**
   * Publish one honest status sentence. When the STATE changes (not just the
   * wording), the open panel is re-rendered too, so its first-run checklist can
   * disappear as soon as Test connection says Connected - the owner does not
   * have to switch notes to see that they are done.
   */
  publishStatus(kind) {
    const changed = kind !== this.lastStatusKind;
    this.lastStatusKind = kind;
    this.renderStatus();
    if (changed) this.refreshPanels();
  }
  statusText() {
    return this.lastStatus;
  }
  /** The same honest state as the status sentence, for the panel's first-run checklist. */
  statusKind() {
    return this.lastStatusKind;
  }
  /**
   * The status bar is an honest health check: a read-only GET that exists on
   * the notes route family. It never calls a write route and never needs a model.
   */
  async refreshStatus() {
    if (this.statusBusy) return;
    this.statusBusy = true;
    try {
      if (!this.hasToken()) {
        this.lastStatus = "Jarvis: no token (Settings)";
        this.publishStatus("no-token");
        return;
      }
      try {
        const answer = await this.client.testConnection();
        if (answer.kind === "ok") {
          this.lastStatus = "Jarvis: connected";
          this.publishStatus("connected");
        } else if (answer.httpStatus === 401) {
          this.lastStatus = "Jarvis: token refused";
          this.publishStatus("token-refused");
        } else if (answer.httpStatus === 403) {
          this.lastStatus = "Jarvis: HTTP 403";
          this.publishStatus("http");
        } else if (answer.httpStatus === 404) {
          this.lastStatus = "Jarvis: notes routes not deployed";
          this.publishStatus("not-deployed");
        } else {
          this.lastStatus = "Jarvis: HTTP " + answer.httpStatus;
          this.publishStatus("http");
        }
      } catch (error) {
        const said = shortError(error);
        const unreachable = said.includes("Could not reach");
        this.lastStatus = unreachable ? "Jarvis: unreachable" : "Jarvis: " + said.slice(0, 60);
        this.publishStatus(unreachable ? "unreachable" : "http");
      }
    } finally {
      this.statusBusy = false;
    }
  }
};
