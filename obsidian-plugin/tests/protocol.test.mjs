/*
 * Tests for the plugin's pure protocol layer (`src/protocol.ts`).
 *
 * Every answer shape here comes from the notes-bridge route contract: a write
 * route answers 202 (card waiting), 200 (saved or unchanged) or 409 (the note
 * changed). Nothing in this file touches the network, Obsidian, or the token
 * beyond proving it never leaks.
 *
 * No build step: Node (22.18+) strips the TypeScript types directly, so this
 * file imports `src/protocol.ts` as-is.
 * Run:          node --test tests/protocol.test.mjs
 */
import { describe, test } from "node:test";
import assert from "node:assert/strict";

import * as protocol from "../src/protocol.ts";

const {
  DEFAULT_BACKEND,
  MAX_CONTEXT_CHARS,
  ProtocolError,
  WAITING_CARD_MESSAGE,
  buildContextText,
  buildHeaders,
  buildUrl,
  clip,
  headingLabel,
  httpErrorMessage,
  interpretCaptureReply,
  interpretChatReply,
  interpretReadReply,
  interpretStatusReply,
  interpretTemplatesReply,
  interpretWriteReply,
  isLoopbackUrl,
  lineContaining,
  normalizeBackendUrl,
  obsidianOpenUri,
  obsidianUriAction,
  parseJsonBody,
  pollDelayMs,
  pollGaveUpMessage,
  requireToken,
  shortError,
  shouldPoll,
} = protocol;

/** A validator for `assert.throws`: a ProtocolError carrying the given kind. */
function protocolError(kind) {
  return (error) => {
    assert.ok(
      error instanceof ProtocolError,
      "expected a ProtocolError, got " + (error && error.name ? error.name : String(error)),
    );
    assert.equal(error.name, "ProtocolError");
    assert.equal(error.kind, kind, "ProtocolError kind");
    assert.equal(typeof error.message, "string");
    assert.ok(error.message.length > 0, "a ProtocolError must carry a sentence to show");
    return true;
  };
}

/** Build the four-field WriteOutcome shape a poll check needs. */
function outcome(kind, extra = {}) {
  return {
    kind,
    message: "",
    jobId: "",
    sha256: "",
    currentSha256: "",
    httpStatus: 200,
    ...extra,
  };
}

describe("normalizeBackendUrl", () => {
  test("blank input means the local default", () => {
    assert.equal(DEFAULT_BACKEND, "http://127.0.0.1:4719");
    assert.equal(normalizeBackendUrl(""), DEFAULT_BACKEND);
    assert.equal(normalizeBackendUrl("   "), DEFAULT_BACKEND);
    assert.equal(normalizeBackendUrl("\t\n "), DEFAULT_BACKEND);
    assert.equal(normalizeBackendUrl(undefined), DEFAULT_BACKEND);
  });

  test("trailing slashes are stripped", () => {
    assert.equal(normalizeBackendUrl("http://127.0.0.1:4719/"), DEFAULT_BACKEND);
    assert.equal(normalizeBackendUrl("http://127.0.0.1:4719///"), DEFAULT_BACKEND);
    assert.equal(normalizeBackendUrl("  http://127.0.0.1:4719/  "), DEFAULT_BACKEND);
    assert.equal(normalizeBackendUrl("http://192.168.1.10:4719/"), "http://192.168.1.10:4719");
  });

  test("keeps a pathless custom host and every slash that belongs to the scheme", () => {
    assert.equal(normalizeBackendUrl("http://192.168.1.10:4719"), "http://192.168.1.10:4719");
    assert.equal(normalizeBackendUrl("https://host"), "https://host");
    assert.equal(normalizeBackendUrl("https://host/"), "https://host");
  });

  test("keeps a path, dropping only its trailing slash", () => {
    assert.equal(normalizeBackendUrl("http://127.0.0.1:4719/jarvis/"), "http://127.0.0.1:4719/jarvis");
  });
});

describe("isLoopbackUrl", () => {
  test("this machine is loopback", () => {
    assert.equal(isLoopbackUrl("http://127.0.0.1:4719"), true);
    assert.equal(isLoopbackUrl("http://localhost:4719"), true);
    // The source's own comment says "True when a URL points at this machine";
    // its host regex (`[^/:]+`) stops at the first colon of a bracketed IPv6
    // literal, so [::1] is the case that must still hold.
    assert.equal(
      isLoopbackUrl("http://[::1]:4719"),
      true,
      "http://[::1]:4719 is this machine (IPv6 loopback); src/protocol.ts's host regex must accept the brackets",
    );
  });

  test("another machine is not loopback", () => {
    assert.equal(isLoopbackUrl("http://192.168.1.10:4719"), false);
    assert.equal(isLoopbackUrl("https://jarvis.example"), false);
    assert.equal(isLoopbackUrl("https://jarvis.example:4719"), false);
  });
});

describe("buildUrl", () => {
  test("joins base and route", () => {
    assert.equal(buildUrl("http://127.0.0.1:4719", "/api/chat"), "http://127.0.0.1:4719/api/chat");
    assert.equal(buildUrl("http://127.0.0.1:4719/", "/api/chat"), "http://127.0.0.1:4719/api/chat");
    assert.equal(buildUrl("http://127.0.0.1:4719", "api/chat"), "http://127.0.0.1:4719/api/chat");
    assert.equal(buildUrl("", "/api/chat"), DEFAULT_BACKEND + "/api/chat");
  });

  test("inserts the slash a route lacks", () => {
    assert.equal(buildUrl("http://127.0.0.1:4719", "api/chat"), "http://127.0.0.1:4719/api/chat");
    assert.equal(buildUrl("http://127.0.0.1:4719", "api/notes/read"), "http://127.0.0.1:4719/api/notes/read");
  });

  test("URL-encodes query values so spaces, & and # round-trip", () => {
    const path = "My Notes/Q3 & Q4 #1.md";
    const raw = buildUrl("http://127.0.0.1:4719", "/api/notes/read", { path });
    const url = new URL(raw);
    assert.equal(url.pathname, "/api/notes/read");
    assert.equal(url.searchParams.get("path"), path);
    assert.equal(url.hash, "", "a bare # in a query value would become a fragment");
    assert.equal(raw.split("&").length, 1, "a bare & in a query value would start a second parameter");
    assert.ok(raw.includes("%20"), "a space must be percent-encoded: " + raw);
    assert.ok(raw.includes("%26"), "& must be percent-encoded: " + raw);
    assert.ok(raw.includes("%23"), "# must be percent-encoded: " + raw);
  });

  test("omits undefined query values, and an empty query means no ?", () => {
    assert.equal(buildUrl("http://127.0.0.1:4719", "/api/chat", {}), "http://127.0.0.1:4719/api/chat");
    assert.equal(buildUrl("http://127.0.0.1:4719", "/api/chat"), "http://127.0.0.1:4719/api/chat");
    assert.equal(
      buildUrl("http://127.0.0.1:4719", "/api/chat", { a: undefined, b: undefined }),
      "http://127.0.0.1:4719/api/chat",
    );
    assert.equal(
      buildUrl("http://127.0.0.1:4719", "/api/notes/change", { id: "job-1", missing: undefined }),
      "http://127.0.0.1:4719/api/notes/change?id=job-1",
    );
  });
});

describe("buildHeaders", () => {
  test("exactly the four headers, client hud, surface desktop", () => {
    const headers = buildHeaders("tok-123");
    assert.deepEqual(Object.keys(headers).sort(), [
      "Content-Type",
      "X-Jarvis-Client",
      "X-Jarvis-Surface",
      "X-Jarvis-Token",
    ]);
    assert.deepEqual(headers, {
      "Content-Type": "application/json",
      "X-Jarvis-Token": "tok-123",
      "X-Jarvis-Client": "hud",
      "X-Jarvis-Surface": "desktop",
    });
    for (const value of Object.values(headers)) {
      assert.equal(typeof value, "string");
    }
  });

  test("the token is only the X-Jarvis-Token value, and never a URL", () => {
    const token = "tok-secret-abc";
    const headers = buildHeaders(token);
    assert.equal(headers["X-Jarvis-Token"], token);
    const serialized = JSON.stringify(headers);
    assert.equal(
      serialized.split(token).length - 1,
      1,
      "the token must appear exactly once in the headers: " + serialized,
    );
    for (const [name, value] of Object.entries(headers)) {
      if (name !== "X-Jarvis-Token") {
        assert.notEqual(value, token, name + " must not carry the token");
      }
    }
    const url = buildUrl("http://127.0.0.1:4719", "/api/notes/read", { path: "Notes/A.md" });
    assert.ok(!url.includes(token), "the token must never be in a URL: " + url);
    assert.ok(!url.toLowerCase().includes("token"), "no token field may be built into a URL: " + url);
  });
});

describe("requireToken", () => {
  test("blank is a no-token ProtocolError", () => {
    for (const blank of ["", "   ", "\t\n", undefined]) {
      assert.throws(() => requireToken(blank), protocolError("no-token"), JSON.stringify(blank));
    }
  });

  test("trims and returns a real token", () => {
    assert.equal(requireToken("  tok-abc  "), "tok-abc");
    assert.equal(requireToken("tok-abc"), "tok-abc");
  });
});

describe("parseJsonBody", () => {
  test("uses an already-parsed object", () => {
    assert.deepEqual(parseJsonBody({ status: 200, json: { ok: true }, text: '{"ok":false}' }), { ok: true });
    assert.deepEqual(parseJsonBody({ status: 200, json: {}, text: '{"ok":true}' }), {});
  });

  test("falls back to raw.text", () => {
    assert.deepEqual(parseJsonBody({ status: 200, text: '{"state":"saved","sha256":"abc"}' }), {
      state: "saved",
      sha256: "abc",
    });
  });

  test("garbage text is an unreadable ProtocolError", () => {
    for (const text of ["<html>nope</html>", "", "not json at all", "{broken"]) {
      assert.throws(
        () => parseJsonBody({ status: 200, text }),
        protocolError("unreadable"),
        "text: " + JSON.stringify(text),
      );
    }
  });

  test("a JSON array or scalar is unreadable, not an empty object", () => {
    // src/protocol.ts's own comment: "An answer that is not a JSON object is
    // an `unreadable` error." Right now the text path coerces these to {}.
    for (const text of ["[1,2,3]", "42", '"just a string"', "null"]) {
      assert.throws(
        () => parseJsonBody({ status: 200, text }),
        protocolError("unreadable"),
        "JSON " + text + " is not an object, so it must not be read as a successful answer",
      );
    }
    assert.throws(
      () => parseJsonBody({ status: 200, json: [1, 2], text: '{"ok":true}' }),
      protocolError("unreadable"),
      "an already-parsed JSON array is not an object either",
    );
  });

  test("a json getter that throws falls back to text", () => {
    const raw = { status: 200, text: '{"state":"filed"}' };
    Object.defineProperty(raw, "json", {
      get() {
        throw new Error("bad JSON");
      },
      enumerable: true,
      configurable: true,
    });
    assert.deepEqual(parseJsonBody(raw), { state: "filed" });
  });

  test("a json getter that throws with garbage text is still unreadable", () => {
    const raw = { status: 200, text: "<html>" };
    Object.defineProperty(raw, "json", {
      get() {
        throw new Error("bad JSON");
      },
      enumerable: true,
      configurable: true,
    });
    assert.throws(() => parseJsonBody(raw), protocolError("unreadable"));
  });
});

describe("httpErrorMessage", () => {
  test("401/403 name the token and prefer the backend's own sentence", () => {
    const expired = httpErrorMessage(401, { message: "token expired at 20:12" });
    assert.match(expired, /token/i);
    assert.match(expired, /token expired at 20:12/);
    assert.match(expired, /401/);

    const wrong = httpErrorMessage(403, { error: "wrong secret" });
    assert.match(wrong, /token/i);
    assert.match(wrong, /wrong secret/);

    assert.match(httpErrorMessage(401, {}), /token/i);
    assert.match(httpErrorMessage(403, {}), /token/i);
    assert.match(httpErrorMessage(401, { why: "header missing" }), /header missing/);
  });

  test("404 says the notes routes arrive with the notes-editor backend deploy", () => {
    const message = httpErrorMessage(404, {});
    assert.match(message, /404/);
    assert.match(message, /notes/i);
    assert.match(message, /notes-editor backend deploy/);
    assert.match(httpErrorMessage(404, { message: "no route /api/notes/insert" }), /no route \/api\/notes\/insert/);
  });

  test("409 says nothing was written and that the note changed", () => {
    const message = httpErrorMessage(409, {});
    assert.match(message, /409/);
    assert.match(message, /note changed/i);
    assert.match(message, /nothing was written/i);
  });

  test("413 is the size limit, 429 is busy, 503 is no vault", () => {
    assert.match(httpErrorMessage(413, {}), /size limit/i);
    assert.match(httpErrorMessage(413, {}), /nothing was written/i);
    assert.match(httpErrorMessage(429, {}), /busy/i);
    assert.match(httpErrorMessage(429, {}), /429/);
    assert.match(httpErrorMessage(503, {}), /vault/i);
    assert.match(httpErrorMessage(503, {}), /503/);
  });

  test("an unknown code says HTTP n", () => {
    assert.equal(httpErrorMessage(418, {}), "Jarvis answered HTTP 418.");
    assert.match(httpErrorMessage(500, { message: "boom" }), /HTTP 500/);
    assert.match(httpErrorMessage(500, { message: "boom" }), /boom/);
  });
});

describe("interpretWriteReply", () => {
  test("202 waiting keeps the job id and says the plugin cannot approve cards", () => {
    const waiting = interpretWriteReply(202, { id: "job-1", state: "waiting" });
    assert.equal(waiting.kind, "waiting");
    assert.equal(waiting.jobId, "job-1");
    assert.equal(waiting.httpStatus, 202);
    assert.match(waiting.message, /cannot approve cards/);
    assert.equal(waiting.message, WAITING_CARD_MESSAGE);
  });

  test("a 200 that says state waiting also waits", () => {
    const waiting = interpretWriteReply(200, { id: "job-2", state: "waiting" });
    assert.equal(waiting.kind, "waiting");
    assert.equal(waiting.jobId, "job-2");
  });

  test("the backend's own message wins while a card waits", () => {
    const waiting = interpretWriteReply(202, { id: "job-3", message: "a card is up in Jarvis" });
    assert.equal(waiting.message, "a card is up in Jarvis");
  });

  test("200 saved carries sha256", () => {
    const saved = interpretWriteReply(200, { ok: true, sha256: "abc123", state: "saved" });
    assert.equal(saved.kind, "saved");
    assert.equal(saved.sha256, "abc123");
    assert.equal(saved.httpStatus, 200);
    assert.ok(saved.message.length > 0);
  });

  test("200 unchanged is its own kind", () => {
    const unchanged = interpretWriteReply(200, { state: "unchanged" });
    assert.equal(unchanged.kind, "unchanged");
    assert.match(unchanged.message, /nothing needed changing/i);
  });

  test("409 is a conflict carrying currentSha256", () => {
    const conflict = interpretWriteReply(409, { current_sha256: "cur99", state: "conflict" });
    assert.equal(conflict.kind, "conflict");
    assert.equal(conflict.currentSha256, "cur99");
    assert.match(conflict.message, /changed/i);
    assert.match(conflict.message, /nothing was written/i);
  });

  test("400 with ok:false carries the backend's error text", () => {
    const refused = interpretWriteReply(400, { ok: false, error: "the note is empty" });
    assert.equal(refused.kind, "error");
    assert.match(refused.message, /the note is empty/);
  });

  test("429 is an error naming the busy backend", () => {
    const busy = interpretWriteReply(429, {});
    assert.equal(busy.kind, "error");
    assert.match(busy.message, /busy/i);
  });

  test("200 with ok:false is an error, not a save", () => {
    const refused = interpretWriteReply(200, { ok: false });
    assert.equal(refused.kind, "error");
    assert.ok(refused.message.length > 0, "an error must say something");
  });

  test("401 is an error naming the token", () => {
    const denied = interpretWriteReply(401, { message: "bad token" });
    assert.equal(denied.kind, "error");
    assert.match(denied.message, /token/i);
    assert.match(denied.message, /bad token/);
  });
});

describe("interpretStatusReply", () => {
  test("each state maps to its kind and keeps the backend's sentence", () => {
    const cases = [
      ["waiting", "waiting"],
      ["saved", "saved"],
      ["unchanged", "unchanged"],
      ["denied", "denied"],
      ["failed", "failed"],
      ["conflict", "conflict"],
    ];
    for (const [state, kind] of cases) {
      const status = interpretStatusReply(200, { state, id: "job-9", message: "backend said " + state });
      assert.equal(status.kind, kind, "state " + state);
      assert.equal(status.message, "backend said " + state);
      assert.equal(status.jobId, "job-9");
    }
  });

  test("denied keeps the backend's own sentence verbatim", () => {
    const sentence = "You denied this card at 20:12. Nothing was written to Session.md.";
    const denied = interpretStatusReply(200, { state: "denied", message: sentence });
    assert.equal(denied.kind, "denied");
    assert.equal(denied.message, sentence);
  });

  test("a 2xx that does not say how the change ended is an error", () => {
    const silent = interpretStatusReply(200, {});
    assert.equal(silent.kind, "error");
    assert.match(silent.message, /without saying how the change ended/);
  });

  test("401 is an error naming the token", () => {
    const refused = interpretStatusReply(401, { message: "bad token" });
    assert.equal(refused.kind, "error");
    assert.match(refused.message, /token/i);
  });
});

describe("interpretChatReply", () => {
  test("choices[0].message.content wins over reply and text", () => {
    const chat = interpretChatReply(200, {
      choices: [{ message: { content: "  The answer  " } }],
      reply: "from reply",
      text: "from text",
    });
    assert.equal(chat.kind, "ok");
    assert.equal(chat.answer, "The answer");
    assert.equal(chat.message, "");
  });

  test("falls back to reply, then text", () => {
    assert.equal(interpretChatReply(200, { reply: "from reply" }).answer, "from reply");
    assert.equal(interpretChatReply(200, { text: "from text" }).answer, "from text");
    assert.equal(
      interpretChatReply(200, { choices: [], reply: "", text: "only text" }).answer,
      "only text",
    );
  });

  test("an empty answer is an error", () => {
    const empty = interpretChatReply(200, { choices: [{ message: { content: "   " } }] });
    assert.equal(empty.kind, "error");
    assert.equal(empty.answer, "");
    assert.match(empty.message, /empty answer/);
  });

  test("a non-2xx answer is an error using httpErrorMessage", () => {
    const refused = interpretChatReply(401, { message: "bad token" });
    assert.equal(refused.kind, "error");
    assert.equal(refused.answer, "");
    assert.match(refused.message, /token/i);
    assert.match(refused.message, /bad token/);
  });
});

describe("interpretReadReply", () => {
  test("200 with a sha256 is ok", () => {
    const read = interpretReadReply(200, { path: "Notes/A.md", sha256: "abc", text: "# A" });
    assert.deepEqual(read, {
      kind: "ok",
      path: "Notes/A.md",
      sha256: "abc",
      text: "# A",
      message: "",
    });
  });

  test("a missing sha256 is an error about the bytes hash", () => {
    const read = interpretReadReply(200, { path: "Notes/A.md", text: "# A" });
    assert.equal(read.kind, "error");
    assert.equal(read.sha256, "");
    assert.equal(read.text, "");
    assert.match(read.message, /hash/);
  });

  test("404 mentions the backend's own sentence", () => {
    const missing = interpretReadReply(404, { message: "no such note: Notes/A.md" });
    assert.equal(missing.kind, "error");
    assert.match(missing.message, /no such note: Notes\/A\.md/);
  });
});

describe("interpretCaptureReply", () => {
  test("202 or state waiting means a waiting card with a job id", () => {
    const accepted = interpretCaptureReply(202, { id: "job-1", state: "waiting" });
    assert.equal(accepted.kind, "waiting");
    assert.equal(accepted.jobId, "job-1");
    assert.match(accepted.message, /cannot approve cards/);

    const stateOnly = interpretCaptureReply(200, { id: "job-2", state: "waiting" });
    assert.equal(stateOnly.kind, "waiting");
    assert.equal(stateOnly.jobId, "job-2");
  });

  test("state filed is filed", () => {
    const filed = interpretCaptureReply(200, { id: "job-3", state: "filed" });
    assert.equal(filed.kind, "filed");
    assert.equal(filed.jobId, "job-3");
    assert.match(filed.message, /today's note/i);
  });

  test("state not_filed carries its own message", () => {
    const notFiled = interpretCaptureReply(200, { state: "not_filed", message: "today's note is locked" });
    assert.equal(notFiled.kind, "not_filed");
    assert.equal(notFiled.message, "today's note is locked");

    const withError = interpretCaptureReply(200, { state: "not_filed", error: "no daily note folder" });
    assert.equal(withError.kind, "not_filed");
    assert.match(withError.message, /no daily note folder/);
  });

  test("200 with no state is filed", () => {
    const filed = interpretCaptureReply(200, { id: "job-4" });
    assert.equal(filed.kind, "filed");
    assert.equal(filed.jobId, "job-4");
  });

  test("401 is an error naming the token", () => {
    const refused = interpretCaptureReply(401, { message: "bad token" });
    assert.equal(refused.kind, "error");
    assert.match(refused.message, /token/i);
    assert.match(refused.message, /bad token/);
  });
});

describe("interpretTemplatesReply", () => {
  test("names are trimmed, non-strings and blanks dropped, why carried through", () => {
    const listed = interpretTemplatesReply(200, {
      templates: ["project", "  daily  ", "", "   ", 7, null, { name: "x" }, "a.md"],
      why: "read from Templates on the PC",
    });
    assert.equal(listed.kind, "ok");
    assert.deepEqual(listed.names, ["project", "daily", "a.md"]);
    assert.equal(listed.why, "read from Templates on the PC");
    assert.equal(listed.message, "");
  });

  test("a non-2xx answer is an error", () => {
    const refused = interpretTemplatesReply(503, {});
    assert.equal(refused.kind, "error");
    assert.deepEqual(refused.names, []);
    assert.equal(refused.why, "");
    assert.match(refused.message, /vault/i);
    assert.match(refused.message, /503/);
  });

  test("ok:false is an error carrying the backend's sentence", () => {
    const refused = interpretTemplatesReply(200, { ok: false, message: "the templates folder is missing" });
    assert.equal(refused.kind, "error");
    assert.match(refused.message, /the templates folder is missing/);
  });
});

describe("buildContextText", () => {
  const full = {
    path: "Projects/Alpha.md",
    title: "Alpha",
    headings: [
      { level: 2, text: "Session" },
      { level: 3, text: "Notes" },
    ],
    links: ["Beta", "Gamma"],
    backlinks: ["Delta"],
    unresolved: ["Missing"],
    frontmatterKeys: ["tags", "status"],
    text: "Some body text.",
    truncated: false,
  };

  test("includes title and path, headings as ## Session, links, backlinks, unresolved and keys", () => {
    const text = buildContextText(full);
    assert.match(text, /^Note: Alpha \(Projects\/Alpha\.md\)/);
    assert.match(text, /Headings:\n- ## Session\n- ### Notes/);
    assert.match(text, /Links:\n- Beta\n- Gamma/);
    assert.match(text, /Linked from:\n- Delta/);
    assert.match(text, /Unresolved links:\n- Missing/);
    assert.match(text, /Frontmatter keys: tags, status/);
    assert.match(text, /Some body text\.$/);
  });

  test("the truncation line appears only when truncated is true", () => {
    assert.equal(MAX_CONTEXT_CHARS, 12000);
    const truncated = buildContextText({ ...full, truncated: true });
    assert.ok(
      truncated.includes("truncated to the first 12000 characters"),
      "truncated context must say so: " + truncated,
    );
    assert.ok(!buildContextText(full).includes("truncated"));
  });

  test("a minimal context has no empty sections", () => {
    const minimal = buildContextText({
      path: "A.md",
      title: "A",
      headings: [],
      links: [],
      backlinks: [],
      unresolved: [],
      frontmatterKeys: [],
      text: "",
      truncated: false,
    });
    assert.equal(minimal, "Note: A (A.md)");
    for (const header of ["Headings:", "Links:", "Linked from:", "Unresolved links:", "Frontmatter keys:"]) {
      assert.ok(!minimal.includes(header), "empty section leaked: " + header);
    }
  });

  test("a truncated but empty note adds no truncation line", () => {
    const text = buildContextText({
      path: "A.md",
      title: "A",
      headings: [],
      links: [],
      backlinks: [],
      unresolved: [],
      frontmatterKeys: [],
      text: "",
      truncated: true,
    });
    assert.equal(text, "Note: A (A.md)");
  });
});

describe("headingLabel", () => {
  test("clamps levels to 1..6", () => {
    assert.equal(headingLabel({ level: 1, text: "One" }), "# One");
    assert.equal(headingLabel({ level: 2, text: "Session" }), "## Session");
    assert.equal(headingLabel({ level: 6, text: "Six" }), "###### Six");
    assert.equal(headingLabel({ level: 0, text: "Zero" }), "# Zero");
    assert.equal(headingLabel({ level: -3, text: "Negative" }), "# Negative");
    assert.equal(headingLabel({ level: 7, text: "Seven" }), "###### Seven");
    assert.equal(headingLabel({ level: 99, text: "Huge" }), "###### Huge");
  });
});

describe("lineContaining", () => {
  test("finds the whole line containing a selection, with LF and CRLF", () => {
    const lf = "first\nsecond with needle\nthird";
    assert.equal(lineContaining("needle", lf), "second with needle");
    const crlf = "first\r\nsecond with needle\r\nthird";
    assert.equal(lineContaining("needle", crlf), "second with needle");
    assert.equal(lineContaining("  needle  ", crlf), "second with needle");
    assert.equal(lineContaining("third", crlf), "third");
  });

  test("blank selection gives an empty string", () => {
    assert.equal(lineContaining("", "a\nb"), "");
    assert.equal(lineContaining("   ", "a\nb"), "");
    assert.equal(lineContaining(undefined, "a\nb"), "");
  });

  test("not found gives an empty string", () => {
    assert.equal(lineContaining("needle", "a\nb"), "");
    assert.equal(lineContaining("needle", ""), "");
  });
});

describe("polling helpers", () => {
  test("pollDelayMs is 1.5 s, then 2.5 s", () => {
    assert.equal(pollDelayMs(0), 1500);
    assert.equal(pollDelayMs(1), 1500);
    assert.equal(pollDelayMs(2), 2500);
    assert.equal(pollDelayMs(3), 2500);
    assert.equal(pollDelayMs(50), 2500);
  });

  test("pollGaveUpMessage says it stopped after 10 minutes and claims no success", () => {
    const message = pollGaveUpMessage();
    assert.match(message, /stopped checking after 10 minutes/);
    assert.match(message, /answer or dismiss/);
    assert.ok(!/saved|succeed|success|done/i.test(message), "giving up must not read as a success: " + message);
  });

  test("shouldPoll is true only for waiting with a job id", () => {
    assert.equal(shouldPoll(outcome("waiting", { jobId: "job-1" })), true);
    assert.equal(shouldPoll(outcome("waiting", { jobId: "" })), false);
    assert.equal(shouldPoll(outcome("saved", { jobId: "job-1" })), false);
    assert.equal(shouldPoll(outcome("unchanged", { jobId: "job-1" })), false);
    assert.equal(shouldPoll(outcome("conflict", { jobId: "job-1" })), false);
    assert.equal(shouldPoll(outcome("error", { jobId: "job-1" })), false);
  });
});

describe("clip and shortError", () => {
  test("clip collapses whitespace and shortens with an ellipsis", () => {
    assert.equal(clip("  hello   world\n\tagain  ", 100), "hello world again");
    assert.equal(clip("short", 10), "short");
    const clipped = clip("x".repeat(50), 10);
    assert.equal(clipped.length, 10);
    assert.ok(clipped.endsWith("\u2026"), "a shortened text must end with an ellipsis");
    assert.equal(clip("abcdef", 4), "abc\u2026");
  });

  test("shortError caps at 240 characters", () => {
    assert.equal(shortError(new Error("y".repeat(500))).length, 240);
    assert.equal(shortError("z".repeat(500)).length, 240);
    assert.equal(shortError(new Error("plain")), "plain");
    assert.equal(shortError("plain"), "plain");
  });
});

describe("the read-only Obsidian link (obsidian://open)", () => {
  test("builds an OPEN link with the vault name and the vault-relative path", () => {
    assert.equal(
      obsidianOpenUri("My Vault", "Projects/Jarvis.md"),
      "obsidian://open?vault=My%20Vault&file=Projects%2FJarvis.md",
    );
    assert.equal(obsidianUriAction(obsidianOpenUri("v", "a.md")), "open");
  });

  test("a heading becomes one encoded #heading after the file", () => {
    const uri = obsidianOpenUri("v", "a.md", "Session notes");
    assert.equal(uri, "obsidian://open?vault=v&file=a.md%23Session%20notes");
    assert.equal(decodeURIComponent(uri.split("file=")[1]), "a.md#Session notes");
  });

  test("strips one leading slash and trims the inputs", () => {
    assert.equal(
      obsidianOpenUri("  v  ", "/folder/a.md", "  Part 1  "),
      "obsidian://open?vault=v&file=folder%2Fa.md%23Part%201",
    );
  });

  test("an empty heading means no fragment", () => {
    assert.equal(
      obsidianOpenUri("v", "a.md", "   "),
      "obsidian://open?vault=v&file=a.md",
    );
  });

  test("only ever produces the open action, never a write action", () => {
    for (const uri of [
      obsidianOpenUri("v", "a.md"),
      obsidianOpenUri("v", "a.md", "H"),
      obsidianOpenUri("", ""),
    ]) {
      assert.equal(obsidianUriAction(uri), "open");
      assert.ok(!/obsidian:\/\/(new|daily|unique|append|prepend)/i.test(uri));
    }
    assert.equal(obsidianUriAction("obsidian://daily?vault=v"), "daily");
    assert.equal(obsidianUriAction("https://example.com"), "");
  });
});

describe("a card answered very fast is not an error", () => {
  test("a write answer that is already denied maps to denied, not error", () => {
    const outcome = interpretWriteReply(200, {
      ok: false,
      state: "denied",
      path: "a.md",
      message: "You said no, so nothing was changed.",
    });
    assert.equal(outcome.kind, "denied");
    assert.equal(outcome.message, "You said no, so nothing was changed.");
  });

  test("a write answer that is already failed maps to failed, not error", () => {
    const outcome = interpretWriteReply(200, {
      ok: false,
      state: "failed",
      path: "a.md",
      message: "The copy of the note could not be saved.",
    });
    assert.equal(outcome.kind, "failed");
    assert.equal(outcome.message, "The copy of the note could not be saved.");
  });

  test("a denied write answer without a sentence still says nothing was changed", () => {
    const outcome = interpretWriteReply(200, { ok: false, state: "denied" });
    assert.equal(outcome.kind, "denied");
    assert.match(outcome.message, /nothing was changed/i);
  });
});
