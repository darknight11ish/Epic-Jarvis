/*
 * The one network door of the Jarvis notes bridge plugin.
 *
 * Every request goes out through Obsidian's `requestUrl`, which the official
 * docs describe as "similar to fetch(), without any CORS restrictions". That is
 * the right call for a plugin talking to `http://127.0.0.1:4719`: a plain
 * `fetch` from Electron would carry `app://obsidian.md` as Origin and meet the
 * backend's origin allowlist.
 *
 * SAFETY, in one place:
 *  - The token is read at request time by a callback and put ONLY in the
 *    `X-Jarvis-Token` header. It is never put in a URL, never printed, never
 *    returned by any method here.
 *  - Every request carries `X-Jarvis-Client: hud` and `X-Jarvis-Surface: desktop`.
 *  - The only routes called are `ROUTES` in `protocol.ts`. There is no
 *    `/api/approve`, no `/api/deny`, and no route that writes the vault outside
 *    the backend's own one-card flow.
 *  - This class never writes a note: the backend does, after its card.
 */
import { requestUrl } from "obsidian";
import {
  buildHeaders,
  buildUrl,
  interpretCaptureReply,
  interpretChatReply,
  interpretReadReply,
  interpretStatusReply,
  interpretTemplatesReply,
  interpretWriteReply,
  normalizeBackendUrl,
  parseJsonBody,
  POLL_MAX_ATTEMPTS,
  pollDelayMs,
  pollGaveUpMessage,
  ProtocolError,
  requireToken,
  ROUTES,
  shortError,
  UNREACHABLE_MESSAGE,
} from "./protocol";
import type {
  CaptureOutcome,
  ChatOutcome,
  RawAnswer,
  ReadOutcome,
  TemplateListOutcome,
  WriteOutcome,
} from "./types";

/** The signature of Obsidian's `requestUrl`, injectable so this file stays honest about its one door. */
export type RequestFn = typeof requestUrl;

/** How the plugin reaches one given note's current bytes hash before an edit. */
export interface HashReader {
  readNote(path: string): Promise<ReadOutcome>;
}

function sleep(ms: number): Promise<void> {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

export class JarvisClient {
  constructor(
    private readonly getBaseUrl: () => string,
    private readonly getToken: () => string,
    private readonly request: RequestFn = requestUrl,
  ) {}

  /**
   * One request. Returns the status and the parsed JSON body (an empty or
   * non-JSON body becomes a `ProtocolError` with the plugin's honest sentence).
   * A thrown `requestUrl` (backend not running) becomes the unreachable error.
   */
  private async send(
    method: "GET" | "POST",
    route: string,
    query?: Record<string, string>,
    payload?: unknown,
  ): Promise<{ status: number; body: Record<string, unknown> }> {
    const token = requireToken(this.getToken());
    const url = buildUrl(normalizeBackendUrl(this.getBaseUrl()), route, query);
    let status = 0;
    let json: unknown;
    let responseText = "";
    try {
      const response = await this.request({
        url,
        method,
        throw: false,
        headers: buildHeaders(token),
        body: payload === undefined ? undefined : JSON.stringify(payload),
      });
      status = response.status;
      try {
        json = response.json;
      } catch {
        json = undefined;
      }
      responseText = typeof response.text === "string" ? response.text : "";
    } catch (error) {
      throw new ProtocolError(UNREACHABLE_MESSAGE + " " + shortError(error));
    }
    const raw: RawAnswer = { status, json, text: responseText };
    return { status, body: parseJsonBody(raw) };
  }

  /* ------------------------------------------------------------------ */
  /* Read-only routes                                                    */
  /* ------------------------------------------------------------------ */

  /** One note's text plus the sha256 of its bytes (the hash an edit starts from). */
  async readNote(path: string): Promise<ReadOutcome> {
    const { status, body } = await this.send("GET", ROUTES.read, { path });
    return interpretReadReply(status, body);
  }

  /** A read-only ask about the note or the selection. No card is raised for an ask. */
  async askJarvis(question: string, contextText: string, notePath: string): Promise<ChatOutcome> {
    if (!(question ?? "").trim()) {
      throw new ProtocolError("Ask a question first.", "invalid");
    }
    const content =
      question.trim() +
      "\n\nRead-only context from " +
      notePath +
      ":\n" +
      contextText;
    const { status, body } = await this.send("POST", ROUTES.chat, undefined, {
      messages: [{ role: "user", content, provenance: "pasted" }],
      stream: false,
      auto: false,
    });
    return interpretChatReply(status, body);
  }

  /** Template names Jarvis knows (names only - the backend never returns template text). */
  async listTemplates(): Promise<TemplateListOutcome> {
    const { status, body } = await this.send("GET", ROUTES.templates);
    return interpretTemplatesReply(status, body);
  }

  /** The cheap read-only health check the status bar and "Test connection" use. */
  async testConnection(): Promise<TemplateListOutcome> {
    return this.listTemplates();
  }

  /* ------------------------------------------------------------------ */
  /* Write routes - every one raises Jarvis's own ONE card               */
  /* ------------------------------------------------------------------ */

  /** Capture to today's daily note through the existing capture route. */
  async captureToDaily(text: string): Promise<CaptureOutcome> {
    if (!(text ?? "").trim()) {
      throw new ProtocolError("Write what should be captured first.", "invalid");
    }
    const { status, body } = await this.send("POST", ROUTES.capture, undefined, {
      target: "obsidian",
      text: text.trim(),
    });
    return interpretCaptureReply(status, body);
  }

  /** How one capture ended (a card can be answered on the PC after the first answer). */
  async captureStatus(jobId: string): Promise<CaptureOutcome> {
    const { status, body } = await this.send("GET", ROUTES.captureStatus, { id: jobId });
    return interpretCaptureReply(status, body);
  }

  /** Add one line under the named heading of one note. */
  async insertUnderHeading(path: string, text: string, heading: string, expectedSha: string): Promise<WriteOutcome> {
    const { status, body } = await this.send("POST", ROUTES.insert, undefined, {
      path,
      text,
      mode: "under_heading",
      target: heading,
      expected_sha256: expectedSha,
    });
    return interpretWriteReply(status, body);
  }

  /** Wrap one exact selection in bold or italic. */
  async formatSpan(
    path: string,
    target: string,
    style: "bold" | "italic",
    action: "add" | "remove",
    expectedSha: string,
  ): Promise<WriteOutcome> {
    const { status, body } = await this.send("POST", ROUTES.format, undefined, {
      path,
      target,
      style,
      action,
      expected_sha256: expectedSha,
    });
    return interpretWriteReply(status, body);
  }

  /** Replace one exact, whole-word occurrence (the selection) with new words. */
  async replaceOnce(path: string, oldText: string, newText: string, expectedSha: string): Promise<WriteOutcome> {
    const { status, body } = await this.send("POST", ROUTES.replace, undefined, {
      path,
      old: oldText,
      new: newText,
      expected_sha256: expectedSha,
    });
    return interpretWriteReply(status, body);
  }

  /** Change one whole line's shape (this plugin uses it for "make it a checklist item"). */
  async customizeLine(
    path: string,
    lineAction: "bullet" | "number" | "checklist" | "quote" | "plain" | "untick",
    targetLine: string,
    expectedSha: string,
  ): Promise<WriteOutcome> {
    const { status, body } = await this.send("POST", ROUTES.customize, undefined, {
      path,
      action: "line",
      line_action: lineAction,
      target: targetLine,
      expected_sha256: expectedSha,
    });
    return interpretWriteReply(status, body);
  }

  /** Add one tag to one note (frontmatter list when the note has one, else a visible line). */
  async addTag(path: string, tag: string, expectedSha: string): Promise<WriteOutcome> {
    const clean = (tag ?? "").trim().replace(/^#+/, "");
    if (!clean) throw new ProtocolError("Type a tag name first.", "invalid");
    const { status, body } = await this.send("POST", ROUTES.tag, undefined, {
      path,
      tag: clean,
      action: "add",
      where: "auto",
      expected_sha256: expectedSha,
    });
    return interpretWriteReply(status, body);
  }

  /** Create ONE new note through the backend's create route (one card, collision refused). */
  async createNote(path: string, text: string): Promise<WriteOutcome> {
    const { status, body } = await this.send("POST", ROUTES.create, undefined, { path, text });
    return interpretWriteReply(status, body);
  }

  /** How one write ended: waiting / saved / denied / failed (409 conflict). */
  async changeStatus(jobId: string): Promise<WriteOutcome> {
    const { status, body } = await this.send("GET", ROUTES.change, { id: jobId });
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
  async pollChange(
    jobId: string,
    onUpdate?: (message: string) => void,
    shouldContinue?: () => boolean,
  ): Promise<WriteOutcome> {
    let last: WriteOutcome = {
      kind: "waiting",
      message: "Waiting for the card on the PC.",
      jobId,
      sha256: "",
      currentSha256: "",
      httpStatus: 0,
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
  async pollCapture(
    jobId: string,
    onUpdate?: (message: string) => void,
    shouldContinue?: () => boolean,
  ): Promise<CaptureOutcome> {
    let last: CaptureOutcome = {
      kind: "waiting",
      message: "Waiting for the card on the PC.",
      jobId,
      httpStatus: 0,
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
}
