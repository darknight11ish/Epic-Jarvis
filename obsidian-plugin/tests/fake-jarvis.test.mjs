/*
 * Integration tests: the plugin's REAL request builders and REAL reply
 * interpreters against a FAKE Jarvis backend on 127.0.0.1.
 *
 * Why a fake backend instead of a real one: `src/client.ts` imports
 * `obsidian`, so Node cannot load it. The builders and interpreters it uses
 * live in `src/protocol.ts` (pure), so this suite drives exactly the JSON
 * body, the URL, the query and the four headers the plugin would send, and
 * maps every answer with exactly the code the panel uses. Nothing here is a
 * stub of plugin code: only the BACKEND is fake.
 *
 * The answers below are the notes-bridge contract in `docs/JARVIS-API.md`
 * sections 170.2 and 170.7-170.9 (handlers in `backend/jarvis_notes_edit.py`,
 * capture in `backend/jarvis_note_capture.py`): a write answers 202 waiting,
 * 200 saved/unchanged or 409 conflict, and how it ended comes from
 * `GET /api/notes/change?id=`.
 *
 * No external network: every socket is 127.0.0.1 on a port the OS picks, and
 * every server is closed in `afterEach` so the process exits.
 *
 * No build step: Node 22.18+ strips the TypeScript types, so this file imports
 * `src/protocol.ts` as-is.
 *
 * Run:  node --experimental-test-isolation=none --test tests/fake-jarvis.test.mjs
 *       (plain `node --test` fails in this sandbox: it forks a process per file.)
 */
import { afterEach, describe, test } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";

import * as protocol from "../src/protocol.ts";

// `RouteRequest` is a TypeScript interface: it has no runtime value to
// destructure. The transport below documents the shape it takes instead.
const {
  DEFAULT_BACKEND,
  FIRST_RUN_STEPS,
  ProtocolError,
  ROUTES,
  UNREACHABLE_MESSAGE,
  buildHeaders,
  buildUrl,
  captureRequest,
  captureStatusRequest,
  changeStatusRequest,
  chatRequest,
  createNoteRequest,
  customizeLineRequest,
  firstRunChecklist,
  formatRequest,
  httpErrorMessage,
  insertRequest,
  interpretCaptureReply,
  interpretChatReply,
  interpretReadReply,
  interpretStatusReply,
  interpretTemplatesReply,
  interpretWriteReply,
  isLoopbackUrl,
  normalizeBackendUrl,
  parseJsonBody,
  readNoteRequest,
  replaceRequest,
  requireToken,
  shortError,
  shouldPoll,
  tagRequest,
  templatesRequest,
} = protocol;

/* ---------------------------------------------------------------------- */
/* Fixture data                                                            */
/* ---------------------------------------------------------------------- */

/** The token this PC's backend expects. Never printed, never in a URL. */
const TOKEN = "test-token-2f6a9c";

/** 64 lowercase hex characters, the shape every surgical edit must carry. */
const SHA_64 = /^[0-9a-f]{64}$/;
const SHA_A = "a".repeat(64); // what GET /api/notes/read hands back
const SHA_B = "b".repeat(64); // the insert that landed
const SHA_C = "c".repeat(64); // somebody else wrote the note (409)
const SHA_D = "d".repeat(64); // the note the create route made
const SHA_E = "e".repeat(64); // the reformatted note
const SHA_F = "f".repeat(64); // the tagged note

const NOTE_PATH = "a.md";
const NOTE_TEXT = "# Note\n";

/** A call from this PC is a loopback call; anything else is a protocol violation. */
const LOOPBACK = new Set(["127.0.0.1", "::1", "::ffff:127.0.0.1"]);

/* ---------------------------------------------------------------------- */
/* The transport: what `JarvisClient.send` does, minus Obsidian             */
/* ---------------------------------------------------------------------- */

/**
 * One request, built exactly as `JarvisClient.send` builds it:
 *   buildUrl(normalizeBackendUrl(base), route, query)
 *   buildHeaders(token), JSON body only when there is one
 * and the answer parsed exactly as `send` parses it: the raw response text is
 * passed to `parseJsonBody`, so a body that is not JSON is exercised for real
 * (that is why the text is kept next to the parsed json).
 *
 * Returns `{ status, body, text }`. Rejects with whatever `node:http` rejected
 * with (a closed port is a rejected promise here, not a fake answer), and
 * rejects with a `ProtocolError` when the answer is unreadable - exactly the
 * layer under `client.send`'s unreachable-message wrap, which Node cannot load.
 */
function requestOnce({ baseUrl, token }, request) {
  const url = buildUrl(normalizeBackendUrl(baseUrl), request.route, request.query);
  const headers = buildHeaders(token);
  const payload = request.body === undefined ? undefined : JSON.stringify(request.body);
  if (payload !== undefined) headers["Content-Length"] = Buffer.byteLength(payload);

  return new Promise((resolve, reject) => {
    const req = http.request(
      url,
      // `agent: false` gives this one request its own connection, which is
      // closed after the answer, so `server.close()` cannot wait on keep-alive.
      { method: request.method, headers, agent: false },
      (res) => {
        const chunks = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => {
          const text = Buffer.concat(chunks).toString("utf8");
          let json;
          try {
            json = JSON.parse(text);
          } catch {
            json = undefined; // parseJsonBody falls back to `text` and refuses it
          }
          const status = res.statusCode;
          try {
            resolve({ status, body: parseJsonBody({ status, json, text }), text });
          } catch (error) {
            reject(error);
          }
        });
      },
    );
    req.on("error", reject);
    if (payload !== undefined) req.write(payload);
    req.end();
  });
}

/** `requestOnce` against a fake server, with an optional different token. */
function send(server, request, options = {}) {
  return requestOnce(
    { baseUrl: server.baseUrl, token: options.token ?? server.token },
    request,
  );
}

/* ---------------------------------------------------------------------- */
/* The fake Jarvis                                                         */
/* ---------------------------------------------------------------------- */

/** A body the real handler would refuse with 400 `{state:"refused"}`. */
class BadBody extends Error {}

function note(state, entry, reason) {
  state.violations.push({ reason, method: entry.method, url: entry.url });
}

function json(res, status, body) {
  const text = JSON.stringify(body);
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(text),
  });
  res.end(text);
}

function text(res, status, body) {
  res.writeHead(status, {
    "Content-Type": "text/html",
    "Content-Length": Buffer.byteLength(body),
  });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
  });
}

function wantString(body, key, { empty = false } = {}) {
  const value = body[key];
  if (typeof value !== "string" || (!empty && !value.trim())) {
    throw new BadBody('expected a non-empty string "' + key + '"');
  }
  return value;
}

function wantOneOf(body, key, allowed) {
  const value = body[key];
  if (!allowed.includes(value)) {
    throw new BadBody(
      '"' + key + '" must be one of ' + allowed.join("/") + ", got " + JSON.stringify(value),
    );
  }
  return value;
}

function wantSha(body, key = "expected_sha256") {
  const value = body[key];
  if (typeof value !== "string" || !SHA_64.test(value)) {
    throw new BadBody('"' + key + '" must be 64 lowercase hex characters, got ' + JSON.stringify(value));
  }
  return value;
}

/**
 * The two write jobs whose status is polled. `waitingPolls` is how many status
 * reads still say `waiting` before the answer is `saved`.
 */
function makeJobs() {
  return new Map([
    [
      "job-insert",
      {
        waitingPolls: 1,
        waiting: {
          state: "waiting",
          path: NOTE_PATH,
          message: "Waiting for your approval card.",
        },
        saved: {
          state: "saved",
          path: NOTE_PATH,
          sha256: SHA_B,
          message: 'Added under the "Session" heading in a.md. You can undo it.',
        },
      },
    ],
    [
      "job-create",
      {
        waitingPolls: 0, // a card answered fast: the first status read is final
        waiting: {
          state: "waiting",
          path: "Folder/New note.md",
          message: "Waiting for your approval card.",
        },
        saved: {
          state: "saved",
          path: "Folder/New note.md",
          sha256: SHA_D,
          receipt: "notes_create:1",
          message: "Created Folder/New note.md in your Obsidian vault. You can undo it.",
        },
      },
    ],
  ]);
}

/**
 * Every route the plugin is allowed to call, answered as the documented
 * backend answers it. Throws `BadBody` (400 + a recorded violation) when the
 * request is not the shape those handlers accept.
 */
function answer(state, entry, body) {
  const key = entry.method + " " + entry.pathname;

  if (key === "GET " + ROUTES.templates) {
    if (entry.query.length) throw new BadBody("GET templates must not carry a query");
    return { status: 200, body: { ok: true, count: 2, templates: ["daily", "project"], why: "" } };
  }

  if (key === "GET " + ROUTES.read) {
    if (entry.query.length !== 1 || !entry.params.path) {
      throw new BadBody("GET read must carry exactly one ?path=");
    }
    const path = entry.params.path;
    return {
      status: 200,
      body: {
        ok: true,
        path,
        text: NOTE_TEXT,
        sha256: SHA_A,
        size: Buffer.byteLength(NOTE_TEXT),
        mtime: 1761900000.0,
      },
    };
  }

  if (key === "GET " + ROUTES.change) {
    if (entry.query.length !== 1 || !entry.params.id) {
      throw new BadBody("GET change must carry exactly one ?id=");
    }
    const job = state.jobs.get(entry.params.id);
    if (!job) {
      return {
        status: 404,
        body: { ok: false, error: "There is no note save with that id on this PC." },
      };
    }
    job.polls = (job.polls || 0) + 1;
    const step = job.polls <= job.waitingPolls ? job.waiting : job.saved;
    return { status: 200, body: { ok: true, ...step } };
  }

  if (key === "GET " + ROUTES.captureStatus) {
    const id = entry.params.id || "";
    if (!id) {
      // The route's other shape: which note apps this PC is set up for.
      return { status: 200, body: { ok: true, targets: ["obsidian"] } };
    }
    if (id !== "job-capture") throw new BadBody('GET capture status was asked for an unknown id "' + id + '"');
    // The card was answered quickly, so the first status read is already final.
    return {
      status: 200,
      body: {
        ok: true,
        id,
        state: "filed",
        target: "obsidian",
        message: "Filed in today's Obsidian daily note.",
      },
    };
  }

  if (key === "POST " + ROUTES.insert) {
    wantString(body, "path");
    wantString(body, "text");
    wantOneOf(body, "mode", ["under_heading", "before", "after"]);
    wantString(body, "target");
    wantSha(body);
    return {
      status: 202,
      body: {
        ok: true,
        state: "waiting",
        id: "job-insert",
        path: body.path,
        message: "Waiting for your approval card.",
      },
    };
  }

  if (key === "POST " + ROUTES.format) {
    wantString(body, "path");
    wantString(body, "target");
    wantOneOf(body, "style", ["bold", "italic", "strike", "code"]);
    wantOneOf(body, "action", ["add", "remove"]);
    wantSha(body);
    return {
      status: 200,
      body: {
        ok: true,
        state: "saved",
        path: body.path,
        sha256: SHA_E,
        message:
          'Made "' + body.target + '" ' + body.style + " in " + body.path + ". You can undo it.",
      },
    };
  }

  if (key === "POST " + ROUTES.replace) {
    wantString(body, "path");
    wantString(body, "old");
    if (typeof body.new !== "string" || body.new === body.old) {
      throw new BadBody('"new" must be a different string from "old"');
    }
    wantSha(body);
    // The note moved since the read, so the handler refuses before any card.
    return {
      status: 409,
      body: {
        ok: false,
        state: "conflict",
        path: body.path,
        current_sha256: SHA_C,
        message: "The note changed since it was read, so nothing was written.",
      },
    };
  }

  if (key === "POST " + ROUTES.customize) {
    wantString(body, "path");
    wantOneOf(body, "action", ["line"]);
    wantOneOf(body, "line_action", ["bullet", "number", "checklist", "quote", "plain", "untick"]);
    wantString(body, "target");
    wantSha(body);
    return {
      status: 200,
      body: {
        ok: true,
        state: "unchanged",
        path: body.path,
        sha256: SHA_A,
        message: "That line is already a checklist item.",
      },
    };
  }

  if (key === "POST " + ROUTES.tag) {
    wantString(body, "path");
    wantString(body, "tag");
    wantOneOf(body, "action", ["add", "remove"]);
    wantOneOf(body, "where", ["auto", "frontmatter", "line"]);
    wantSha(body);
    return {
      status: 200,
      body: {
        ok: true,
        state: "saved",
        path: body.path,
        sha256: SHA_F,
        message: "Added the #" + body.tag + " tag to " + body.path + ". You can undo it.",
      },
    };
  }

  if (key === "POST " + ROUTES.create) {
    // A new note has no version to compare against, so NO expected_sha256.
    wantString(body, "path");
    wantString(body, "text", { empty: true });
    if ("expected_sha256" in body) {
      throw new BadBody("a create has no version to compare against, so it must not send expected_sha256");
    }
    return {
      status: 202,
      body: {
        ok: true,
        state: "waiting",
        id: "job-create",
        path: body.path,
        message: "Waiting for your approval card.",
      },
    };
  }

  if (key === "POST " + ROUTES.capture) {
    wantOneOf(body, "target", ["obsidian"]);
    wantString(body, "text");
    return {
      status: 202,
      body: {
        ok: true,
        state: "waiting",
        id: "job-capture",
        message: "Waiting for your approval.",
      },
    };
  }

  if (key === "POST " + ROUTES.chat) {
    if (!Array.isArray(body.messages) || body.messages.length !== 1) {
      throw new BadBody("a read-only ask sends exactly one message");
    }
    const message = body.messages[0];
    if (!message || message.role !== "user" || typeof message.content !== "string" || !message.content.trim()) {
      throw new BadBody("the ask must be one `user` message with words in it");
    }
    if (body.stream !== false || body.auto !== false) {
      throw new BadBody("a read-only ask must send stream:false and auto:false");
    }
    return {
      status: 200,
      body: { choices: [{ message: { content: "This note is about testing." } }] },
    };
  }

  note(state, entry, "the plugin called a route this fake does not serve: " + key);
  return { status: 404, body: { ok: false, error: "Not Found" } };
}

async function handle(state, req, res) {
  const rawUrl = req.url || "/";
  const url = new URL(rawUrl, "http://127.0.0.1");
  const entry = {
    method: req.method || "GET",
    url: rawUrl,
    pathname: url.pathname,
    params: Object.fromEntries(url.searchParams.entries()),
    query: [...url.searchParams.keys()],
    headers: req.headers,
    token: req.headers["x-jarvis-token"],
    body: undefined,
  };
  state.requests.push(entry);
  const before = state.violations.length;

  // Every request must be this PC calling a loopback address with the three
  // headers the project requires. A violation is recorded AND answered 400, so
  // a test that made the bad request fails on its own status assertion and on
  // the violation list in afterEach.
  const remote = req.socket.remoteAddress || "";
  if (!LOOPBACK.has(remote)) note(state, entry, "the request did not come from this PC (" + remote + ")");
  if (req.headers["x-jarvis-client"] !== "hud") note(state, entry, "X-Jarvis-Client was not hud");
  if (req.headers["x-jarvis-surface"] !== "desktop") note(state, entry, "X-Jarvis-Surface was not desktop");
  // The 401 fixture refuses EVERY request on purpose, so it cannot also demand a
  // matching token: refusing the token it was handed is the whole point. Every
  // other instance asserts the token on every single request.
  if (state.mode !== "unauthorized" && entry.token !== state.token) {
    note(state, entry, "X-Jarvis-Token did not match the token this PC expects");
  }
  if (state.violations.length > before) {
    return json(res, 400, { ok: false, error: "bad headers" });
  }

  const raw = await readBody(req);
  if (state.mode === "templates404") return json(res, 404, state.notFoundBody);
  if (state.mode === "unauthorized") {
    return json(res, 401, { ok: false, error: "bad or missing X-Jarvis-Token" });
  }
  if (state.mode === "badJson") return text(res, 200, "<html><body>this is not JSON</body></html>");

  if (raw.trim()) {
    try {
      entry.body = JSON.parse(raw);
    } catch {
      note(state, entry, "the request body was not JSON");
      return json(res, 400, { ok: false, error: "that is not a JSON body" });
    }
  }

  try {
    // `mode:"fixed"` gives one answer for every route: one request per instance,
    // so the one fixed answer is the one being mapped. The loopback/header/token
    // checks above and the body parse already ran, so this cannot hide a
    // malformed request - it only answers the shape the test is about.
    const reply = state.mode === "fixed" ? state.answer : answer(state, entry, entry.body);
    return json(res, reply.status, reply.body);
  } catch (error) {
    if (!(error instanceof BadBody)) throw error;
    note(state, entry, error.message);
    return json(res, 400, { ok: false, state: "refused", error: error.message });
  }
}

const liveServers = [];

/**
 * Start one fake Jarvis on 127.0.0.1:0 and return a handle.
 *
 * modes:
 *   "ok"           every documented route (the default)
 *   "templates404" every route is 404, the pre-deploy backend; `notFoundBody`
 *                  is the exact body (default: the one this suite was asked to
 *                  use, `{ok:false,error:"Not Found"}`)
 *   "unauthorized" every route is 401 `{ok:false,error:"bad or missing X-Jarvis-Token"}`
 *   "badJson"      every route answers 200 with a body that is not JSON
 *   "fixed"        every route answers `answer` (`{status, body}`) verbatim, for
 *                  the answers the "ok" server must never produce on a route:
 *                  one instance, one request, one answer to map. The middleware
 *                  checks and the body parse still run first, so a bad request is
 *                  still a 400 and still a recorded violation.
 */
async function startFakeJarvis(options = {}) {
  const state = {
    mode: options.mode ?? "ok",
    token: options.token ?? TOKEN,
    notFoundBody: options.notFoundBody ?? { ok: false, error: "Not Found" },
    answer: options.answer ?? null,
    requests: [],
    violations: [],
    jobs: makeJobs(),
  };
  if (state.mode === "fixed" && !state.answer) {
    throw new Error('the "fixed" mode needs an `answer` ({status, body}) to give');
  }
  const server = http.createServer((req, res) => {
    handle(state, req, res).catch((error) => {
      note(state, { method: req.method || "GET", url: req.url || "/" }, "the fake server threw: " + shortError(error));
      if (!res.headersSent) json(res, 500, { ok: false, error: "the fake server threw" });
      else res.end();
    });
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });

  let closing = null;
  const fake = {
    baseUrl: "http://127.0.0.1:" + server.address().port,
    token: state.token,
    mode: state.mode,
    requests: state.requests,
    violations: state.violations,
    state,
    // Closing is idempotent. The "lost contact" test closes one instance itself
    // and then afterEach closes every instance it recorded; a second
    // server.close() would call back with ERR_SERVER_NOT_RUNNING.
    close: () => {
      if (!closing) {
        closing = new Promise((resolve, reject) => {
          server.closeAllConnections();
          server.close((error) => (error ? reject(error) : resolve()));
        });
      }
      return closing;
    },
  };
  liveServers.push(fake);
  return fake;
}

// One place that closes every server and fails the test that left a violation
// behind. Nothing here is retried or ignored: a protocol violation is a bug in
// the plugin or in this suite, never a warning.
afterEach(async () => {
  const open = liveServers.splice(0);
  const problems = [];
  for (const fake of open) {
    for (const violation of fake.violations) {
      problems.push(violation.reason + " (" + violation.method + " " + violation.url + ")");
    }
    await fake.close();
  }
  assert.deepEqual(problems, [], "the fake Jarvis recorded protocol violations");
});

/* ---------------------------------------------------------------------- */
/* 1. First run: the settings, the headers, and the pre-deploy state       */
/* ---------------------------------------------------------------------- */

describe("first run, before the notes-editor backend deploy", () => {
  test("the default backend is this PC's Jarvis on the documented loopback port", () => {
    assert.equal(DEFAULT_BACKEND, "http://127.0.0.1:4719");
    assert.equal(isLoopbackUrl(DEFAULT_BACKEND), true);
    assert.equal(isLoopbackUrl("http://localhost:4719"), true);
    assert.equal(isLoopbackUrl("http://[::1]:4719"), true);
    assert.equal(isLoopbackUrl("http://192.168.1.20:4719"), false);
    assert.equal(isLoopbackUrl("http://example.com:4719"), false);
  });

  test("normalizeBackendUrl trims a pasted address and drops its trailing slashes", () => {
    assert.equal(normalizeBackendUrl("  http://127.0.0.1:4719//// "), "http://127.0.0.1:4719");
    assert.equal(normalizeBackendUrl(""), DEFAULT_BACKEND);
    assert.equal(
      buildUrl("  http://127.0.0.1:4719//// ", ROUTES.read, { path: "a.md" }),
      "http://127.0.0.1:4719/api/notes/read?path=a.md",
    );
  });

  test("requireToken refuses a blank token and says where the setting lives", () => {
    assert.throws(
      () => requireToken(""),
      (error) => {
        assert.ok(error instanceof ProtocolError, "expected a ProtocolError");
        assert.equal(error.kind, "no-token");
        assert.match(error.message, /Settings -> Jarvis notes bridge/);
        return true;
      },
    );
    assert.throws(() => requireToken("   "), (error) => error instanceof ProtocolError && error.kind === "no-token");
    assert.equal(requireToken("  tok  "), "tok");
  });

  test("every request carries hud/desktop in a header and the token never in the URL", async () => {
    const fake = await startFakeJarvis();
    const built = buildHeaders("tok");
    assert.equal(built["X-Jarvis-Client"], "hud");
    assert.equal(built["X-Jarvis-Surface"], "desktop");
    assert.equal(built["X-Jarvis-Token"], "tok");
    assert.equal(built["Content-Type"], "application/json");

    const { status } = await send(fake, templatesRequest());
    assert.equal(status, 200);
    const seen = fake.requests.at(-1);
    assert.equal(seen.headers["x-jarvis-client"], "hud");
    assert.equal(seen.headers["x-jarvis-surface"], "desktop");
    assert.equal(seen.token, fake.token);
    assert.ok(!seen.url.includes(fake.token), "the token must never travel in a URL");
  });

  test("a 404 from before the deploy says the routes arrive with that deploy", async () => {
    // FastAPI's own 404 body has no message/error/why key the plugin reads, which
    // is exactly the pre-deploy state: the plugin's own sentence has to say why.
    const fake = await startFakeJarvis({
      mode: "templates404",
      notFoundBody: { detail: "Not Found" },
    });
    const { status, body } = await send(fake, templatesRequest());
    assert.equal(status, 404);
    const outcome = interpretTemplatesReply(status, body);
    assert.equal(outcome.kind, "error");
    assert.match(outcome.message, /notes-editor backend deploy/);
    assert.deepEqual(outcome.names, []);
    assert.equal(outcome.httpStatus, 404);
  });

  test("a 404 that carries the backend's own error is shown in the backend's words", async () => {
    // The one thing this proves: httpErrorMessage prefers the backend's own
    // `error` to its fallback, so a body WITH an error sentence does NOT get the
    // deploy sentence. The fake's default 404 body is exactly that shape.
    const fake = await startFakeJarvis({ mode: "templates404" });
    const { status, body } = await send(fake, templatesRequest());
    const outcome = interpretTemplatesReply(status, body);
    assert.equal(outcome.kind, "error");
    assert.equal(outcome.message, "Not Found");
  });

  test("a connection to a closed port fails, and the transport says so", async () => {
    const probe = http.createServer((_req, res) => res.end("should never answer"));
    await new Promise((resolve) => probe.listen(0, "127.0.0.1", resolve));
    const closedUrl = "http://127.0.0.1:" + probe.address().port;
    await new Promise((resolve) => probe.close(resolve));

    const error = await requestOnce({ baseUrl: closedUrl, token: TOKEN }, templatesRequest()).then(
      () => {
        throw new Error("expected the connection to a closed port to fail");
      },
      (caught) => caught,
    );
    // The plugin's own "Could not reach the local Jarvis" wrap lives in
    // client.send, which imports `obsidian` and cannot be loaded here. What is
    // proven is the layer under it: the failure surfaces, with a non-empty
    // sentence, instead of an invented answer.
    assert.equal(typeof shortError(error), "string");
    assert.ok(shortError(error).length > 0);
    assert.ok(!shortError(error).includes(UNREACHABLE_MESSAGE));
  });

  test("the first-run checklist is three plain steps, and it is gone only when the connection is proven", () => {
    // A missing step is a dead end and a fourth step is a second thing to do at
    // once: the checklist is the whole beginner path. Step 3 is the check that
    // proves the address and the token, so it has to name the button.
    assert.equal(FIRST_RUN_STEPS.length, 3);
    for (const step of FIRST_RUN_STEPS) {
      assert.ok(step.trim().length > 0, "every step must have words in it");
    }
    assert.match(FIRST_RUN_STEPS[2], /Test connection/);

    // Once connected there is nothing left to do, so the panel shows no checklist.
    assert.deepEqual(firstRunChecklist(true, "connected"), { heading: "", steps: [], next: "" });

    // A missing token outranks "connected": without one, no status check can have
    // proven anything, so hiding the checklist here would leave a beginner stuck
    // on a panel whose buttons all refuse.
    const tokenless = firstRunChecklist(false, "connected");
    assert.equal(tokenless.heading, "First run");
    assert.equal(tokenless.steps.length, 3);
    assert.ok(tokenless.next.length > 0);

    // Setup guidance is the most likely place to print the token by accident, and
    // it must never offer to approve a card: cards are answered in Jarvis, never
    // in this plugin.
    for (const status of [
      "unknown",
      "no-token",
      "connected",
      "unreachable",
      "token-refused",
      "not-deployed",
      "http",
    ]) {
      for (const hasToken of [true, false]) {
        const checklist = firstRunChecklist(hasToken, status);
        const said = [checklist.next, ...checklist.steps].join("\n");
        assert.ok(!said.includes(TOKEN), status + " must not print the token");
        assert.ok(!said.includes("token-2f6a9c"), status + " must not print the token's tail either");
        assert.ok(!/approve/i.test(said), status + " must never offer to approve a card in the plugin");
      }
    }
  });

  test("every connection state says the ONE next thing to do", () => {
    // One status, one next action. These key phrases are what make each state
    // actionable; a state that says nothing, or says two things, is a dead end.
    const cases = [
      { status: "unknown", phrase: /checking/ },
      { status: "no-token", phrase: /step 1/ },
      { status: "unreachable", phrase: /desktop app running/ },
      { status: "token-refused", phrase: /refused the token/ },
      { status: "not-deployed", phrase: /notes-editor backend deploy/ },
      { status: "http", phrase: /Test connection/ },
    ];
    for (const item of cases) {
      const checklist = firstRunChecklist(true, item.status);
      assert.equal(checklist.heading, "First run", item.status + " still needs the checklist");
      assert.equal(checklist.steps.length, 3, item.status + " keeps all three steps");
      assert.match(checklist.next, item.phrase, item.status + " must name the one next action");
    }
    // The 404 is the pre-deploy state, and saying it is not the owner's fault is
    // the difference between a bug report and a five-minute wait for a deploy.
    assert.match(firstRunChecklist(true, "not-deployed").next, /not a mistake/);
    // No token at all is the FIRST thing to fix, whatever the last check said:
    // "no token" and "no token, and nothing answered" must not give two answers.
    assert.equal(firstRunChecklist(false, "unreachable").next, firstRunChecklist(true, "no-token").next);
  });

  test("the first-run guidance agrees with the plugin's own status words", () => {
    // The checklist must not invent a second vocabulary for a problem the plugin
    // already has an honest sentence about. The sentences are built here from the
    // same pure helpers the panel uses, so the test cross-references the plugin's
    // words instead of retyping them.
    const noTokenError = (() => {
      try {
        requireToken("");
        return "";
      } catch (error) {
        return error.message;
      }
    })();
    assert.match(noTokenError, /No Jarvis token yet/);
    assert.match(noTokenError, /Settings -> Jarvis notes bridge/);
    assert.match(firstRunChecklist(false, "no-token").next, /step 1/);
    assert.ok(
      FIRST_RUN_STEPS[0].includes("Settings -> Jarvis notes bridge"),
      "step 1 must send the owner to the same setting the token error names",
    );

    // "unreachable" is the plugin's own sentence about the desktop app: the
    // guidance has to send the owner to the same check, not a new one.
    assert.match(UNREACHABLE_MESSAGE, /Could not reach the local Jarvis/);
    assert.match(UNREACHABLE_MESSAGE, /running on this PC/);
    assert.match(firstRunChecklist(true, "unreachable").next, /running on this PC/);

    // "not-deployed" is the plugin's 404 mapping; both must name the same deploy.
    const notDeployed = httpErrorMessage(404, { ok: false });
    assert.match(notDeployed, /HTTP 404/);
    assert.match(notDeployed, /notes-editor backend deploy/);
    assert.match(firstRunChecklist(true, "not-deployed").next, /notes-editor backend deploy/);
    assert.match(firstRunChecklist(true, "not-deployed").next, /HTTP 404/);

    // "token-refused" is the plugin's 401 mapping; both must blame the token.
    assert.match(httpErrorMessage(401, { ok: false }), /token/i);
    assert.match(firstRunChecklist(true, "token-refused").next, /refused the token/);

    // And the checked states line up with the plugin's own "is a token set?",
    // decided by requireToken rather than by a boolean this test invents.
    const hasToken = (token) => {
      try {
        requireToken(token);
        return true;
      } catch {
        return false;
      }
    };
    assert.equal(hasToken(""), false);
    assert.equal(hasToken("tok"), true);
    for (const status of [
      "unknown",
      "no-token",
      "connected",
      "unreachable",
      "token-refused",
      "not-deployed",
      "http",
    ]) {
      const shown = firstRunChecklist(hasToken("tok"), status).heading !== "";
      assert.equal(shown, status !== "connected", status + " is hidden only when connected");
    }
  });
});

/* ---------------------------------------------------------------------- */
/* 2. The real wave-2 flow: read the note, then insert under its heading   */
/* ---------------------------------------------------------------------- */

describe("read a note, then insert under one of its headings", () => {
  test("the real read request gets the note and the hash of its bytes", async () => {
    const fake = await startFakeJarvis();
    const request = readNoteRequest(NOTE_PATH);
    assert.equal(request.method, "GET");
    assert.equal(request.route, ROUTES.read);

    const { status, body } = await send(fake, request);
    const read = interpretReadReply(status, body);
    assert.equal(read.kind, "ok");
    assert.equal(read.path, NOTE_PATH);
    assert.equal(read.text, NOTE_TEXT);
    assert.equal(read.sha256, SHA_A);
    assert.match(read.sha256, SHA_64);

    const seen = fake.requests.at(-1);
    assert.deepEqual(seen.query, ["path"], "the read carries only ?path=");
    assert.equal(seen.params.path, NOTE_PATH);
  });

  test("the real insert body is accepted and the card is waiting", async () => {
    const fake = await startFakeJarvis();
    const request = insertRequest(NOTE_PATH, "Bought milk", "Session", SHA_A);
    assert.equal(request.method, "POST");
    assert.equal(request.route, ROUTES.insert);

    const { status, body } = await send(fake, request);
    assert.equal(status, 202, "a card is up, so the write route answers 202");
    const outcome = interpretWriteReply(status, body);
    assert.equal(outcome.kind, "waiting");
    assert.equal(outcome.jobId, "job-insert");
    assert.equal(outcome.httpStatus, 202);
    assert.match(outcome.message, /approval card/);

    // The fake validated the body before answering, so a wrong key would have
    // been a 400 (and a recorded violation) instead of this 202.
    const sent = fake.requests.at(-1).body;
    assert.equal(sent.path, NOTE_PATH);
    assert.equal(sent.text, "Bought milk");
    assert.equal(sent.mode, "under_heading");
    assert.equal(sent.target, "Session");
    assert.equal(sent.expected_sha256, SHA_A);
  });

  test("the status poll waits once, then says the line was Added and the hash changed", async () => {
    const fake = await startFakeJarvis();
    await send(fake, insertRequest(NOTE_PATH, "Bought milk", "Session", SHA_A));

    const first = await send(fake, changeStatusRequest("job-insert"));
    assert.equal(first.status, 200);
    const waiting = interpretStatusReply(first.status, first.body);
    assert.equal(waiting.kind, "waiting");
    assert.match(waiting.message, /Waiting for your approval card/);

    const second = await send(fake, changeStatusRequest("job-insert"));
    const saved = interpretStatusReply(second.status, second.body);
    assert.equal(saved.kind, "saved");
    assert.match(saved.message, /Added/);
    assert.match(saved.message, /You can undo it/);
    assert.equal(saved.sha256, SHA_B);
    assert.notEqual(saved.sha256, SHA_A, "a saved write reports a new hash");
  });
});

/* ---------------------------------------------------------------------- */
/* 3. Every other route the panel drives                                   */
/* ---------------------------------------------------------------------- */

describe("the other routes answer with the states the panel maps", () => {
  test("format a span: saved, with the new hash", async () => {
    const fake = await startFakeJarvis();
    const { status, body } = await send(fake, formatRequest(NOTE_PATH, "spark", "bold", "add", SHA_A));
    assert.equal(status, 200);
    const outcome = interpretWriteReply(status, body);
    assert.equal(outcome.kind, "saved");
    assert.equal(outcome.sha256, SHA_E);
    assert.notEqual(outcome.sha256, SHA_A);
  });

  test("replace a word: 409 conflict, nothing written, the current hash named", async () => {
    const fake = await startFakeJarvis();
    const { status, body } = await send(fake, replaceRequest(NOTE_PATH, "old", "new", SHA_A));
    assert.equal(status, 409);
    const outcome = interpretWriteReply(status, body);
    assert.equal(outcome.kind, "conflict");
    assert.equal(outcome.currentSha256, SHA_C);
    assert.match(outcome.currentSha256, SHA_64);
    assert.match(outcome.message, /nothing was written/i);
    assert.equal(outcome.sha256, "", "a refused write never reports a new hash");
  });

  test("customize a line: unchanged, and no card was needed", async () => {
    const fake = await startFakeJarvis();
    const request = customizeLineRequest(NOTE_PATH, "checklist", "- buy milk", SHA_A);
    const { status, body } = await send(fake, request);
    assert.equal(status, 200);
    const outcome = interpretWriteReply(status, body);
    assert.equal(outcome.kind, "unchanged");
    assert.equal(outcome.sha256, SHA_A);
    assert.match(outcome.message, /already a checklist item/i);
  });

  test("tag a note: saved, with the new hash", async () => {
    const fake = await startFakeJarvis();
    const { status, body } = await send(fake, tagRequest(NOTE_PATH, "recipes", SHA_A));
    assert.equal(status, 200);
    const outcome = interpretWriteReply(status, body);
    assert.equal(outcome.kind, "saved");
    assert.equal(outcome.sha256, SHA_F);
  });

  test("create one note: waiting, then saved by its own status", async () => {
    const fake = await startFakeJarvis();
    const created = await send(fake, createNoteRequest("Folder/New note.md", "# New\n"));
    assert.equal(created.status, 202);
    const waiting = interpretWriteReply(created.status, created.body);
    assert.equal(waiting.kind, "waiting");
    assert.equal(waiting.jobId, "job-create");

    const later = await send(fake, changeStatusRequest("job-create"));
    const saved = interpretStatusReply(later.status, later.body);
    assert.equal(saved.kind, "saved");
    assert.equal(saved.sha256, SHA_D);
    assert.match(saved.message, /Created/);
  });

  test("capture to today's daily note: waiting, then filed", async () => {
    const fake = await startFakeJarvis();
    const request = captureRequest("Remember the milk");
    assert.deepEqual(request.body, { target: "obsidian", text: "Remember the milk" });

    const posted = await send(fake, request);
    assert.equal(posted.status, 202);
    const waiting = interpretCaptureReply(posted.status, posted.body);
    assert.equal(waiting.kind, "waiting");
    assert.equal(waiting.jobId, "job-capture");

    const later = await send(fake, captureStatusRequest("job-capture"));
    const filed = interpretCaptureReply(later.status, later.body);
    assert.equal(filed.kind, "filed");
    assert.match(filed.message, /Filed/);
  });

  test("a read-only ask gets the chat answer, with the question and context in the body", async () => {
    const fake = await startFakeJarvis();
    const request = chatRequest("What is this note about?", "Note: a.md (a.md)\n\n# Note\n", "a.md");
    const { status, body } = await send(fake, request);
    const answer = interpretChatReply(status, body);
    assert.equal(answer.kind, "ok");
    assert.equal(answer.answer, "This note is about testing.");

    const sent = fake.requests.at(-1);
    assert.deepEqual(sent.query, [], "an ask keeps everything in the body, not the URL");
    assert.match(sent.body.messages[0].content, /What is this note about\?/);
    assert.match(sent.body.messages[0].content, /Read-only context from a\.md/);
  });

  test("the template list comes back as names only", async () => {
    const fake = await startFakeJarvis();
    const { status, body } = await send(fake, templatesRequest());
    const list = interpretTemplatesReply(status, body);
    assert.equal(list.kind, "ok");
    assert.deepEqual(list.names, ["daily", "project"]);
    assert.equal(list.why, "");
    assert.equal(list.httpStatus, 200);
  });
});

/* ---------------------------------------------------------------------- */
/* 4. The request shape itself: the hash, the URL, the encoding            */
/* ---------------------------------------------------------------------- */

describe("the shape of every request", () => {
  test("every surgical body carries the 64-hex hash its edit started from", async () => {
    const fake = await startFakeJarvis();
    const surgical = [
      insertRequest(NOTE_PATH, "Bought milk", "Session", SHA_A),
      formatRequest(NOTE_PATH, "spark", "italic", "remove", SHA_A),
      replaceRequest(NOTE_PATH, "old", "new", SHA_A),
      customizeLineRequest(NOTE_PATH, "checklist", "- buy milk", SHA_A),
      tagRequest(NOTE_PATH, "recipes", SHA_A),
    ];
    for (const request of surgical) await send(fake, request);

    const posts = fake.requests.filter((entry) => entry.method === "POST");
    assert.equal(posts.length, surgical.length);
    for (const entry of posts) {
      assert.ok(entry.body, entry.pathname + " must send a JSON body");
      assert.equal(typeof entry.body.expected_sha256, "string", entry.pathname + " must carry expected_sha256");
      assert.match(entry.body.expected_sha256, SHA_64, entry.pathname + " must carry a 64-hex hash");
      assert.equal(entry.body.expected_sha256, SHA_A);
    }

    // A create is the one write with no version to compare against; the fake
    // refuses the request outright if the builder ever sends one.
    await send(fake, createNoteRequest("New.md", ""));
    const created = fake.requests.at(-1).body;
    assert.equal("expected_sha256" in created, false);
    assert.equal(created.text, "", "a new note may start empty");
  });

  test("no request puts the token or the note's words in its URL", async () => {
    const fake = await startFakeJarvis();
    const secretWords = "SENTINEL-NOTE-TEXT-4f8e";
    await send(fake, readNoteRequest("Folder/My Note & More.md"));
    await send(fake, insertRequest(NOTE_PATH, secretWords, "Session", SHA_A));
    await send(fake, changeStatusRequest("job-insert"));
    await send(fake, captureStatusRequest("job-capture"));
    await send(fake, templatesRequest());

    for (const entry of fake.requests) {
      assert.ok(!entry.url.includes(fake.token), "the token must never travel in a URL: " + entry.url);
      assert.ok(!entry.url.includes(secretWords), "note text must never travel in a URL: " + entry.url);
      for (const key of entry.query) {
        assert.ok(["path", "id"].includes(key), "unexpected query key: " + key + " in " + entry.url);
      }
    }
  });

  test("a note path with a space, an ampersand and non-ASCII round-trips", async () => {
    const fake = await startFakeJarvis();
    const notePath = "Folder/My Note & More \u00e9.md";
    const { status, body } = await send(fake, readNoteRequest(notePath));
    const read = interpretReadReply(status, body);
    assert.equal(read.kind, "ok");
    assert.equal(read.path, notePath, "the path must survive buildUrl and the server's URL parsing");
    assert.equal(body.text, NOTE_TEXT);

    const seen = fake.requests.at(-1);
    assert.equal(seen.params.path, notePath);
    assert.ok(seen.url.includes("%20"), "the space is percent-encoded");
    assert.ok(seen.url.includes("%26"), "the ampersand is percent-encoded");
    assert.ok(seen.url.includes("%C3%A9"), "non-ASCII is UTF-8, percent-encoded");
    assert.ok(!seen.url.includes("&More"), "a raw ampersand would have split the query");
  });
});

/* ---------------------------------------------------------------------- */
/* 5. Answers the plugin must refuse rather than believe                   */
/* ---------------------------------------------------------------------- */

describe("answers that are not a Jarvis answer", () => {
  test("a body that is not JSON is an unreadable-answer error, not an empty success", async () => {
    const fake = await startFakeJarvis({ mode: "badJson" });
    const error = await send(fake, templatesRequest()).then(
      () => {
        throw new Error("expected parseJsonBody to refuse a body that is not JSON");
      },
      (caught) => caught,
    );
    assert.ok(error instanceof ProtocolError);
    assert.equal(error.kind, "unreadable");
    assert.match(error.message, /could not read/);
  });

  test("a token the backend does not accept is a 401 that names the token", async () => {
    const fake = await startFakeJarvis({ mode: "unauthorized" });
    const wrongToken = "wrong-token-for-this-backend";
    const { status, body } = await send(fake, templatesRequest(), { token: wrongToken });
    assert.equal(status, 401);
    assert.equal(fake.requests.at(-1).token, wrongToken, "the plugin sent the token it was configured with");

    const listed = interpretTemplatesReply(status, body);
    assert.equal(listed.kind, "error");
    assert.match(listed.message, /HTTP 401/);
    assert.match(listed.message, /token/i);
    assert.match(listed.message, /bad or missing X-Jarvis-Token/);
    assert.ok(!listed.message.includes(wrongToken), "an error sentence must never contain the token itself");

    // A 401 with no sentence of its own still points at the setting that holds it.
    assert.match(httpErrorMessage(401, { ok: false }), /Settings -> Jarvis notes bridge/);
  });
});

/* ---------------------------------------------------------------------- */
/* 6. A write answer that is not a plain save: the card this panel cannot  */
/*    follow, the state word it does not know, and the refusals            */
/* ---------------------------------------------------------------------- */

describe("a write answer that is not a plain save", () => {
  test("202 waiting with no change id is still waiting, but the panel says it cannot follow the card", async () => {
    // A card that cannot be followed is still a card. Without an id there is
    // nothing to poll, so the panel must say that instead of starting a wait that
    // can never end - shouldPoll is the question the panel actually asks.
    const fake = await startFakeJarvis({
      mode: "fixed",
      answer: { status: 202, body: { ok: true, state: "waiting" } },
    });
    const { status, body } = await send(fake, insertRequest(NOTE_PATH, "Bought milk", "Session", SHA_A));
    assert.equal(status, 202);
    assert.equal(fake.requests.at(-1).body.path, NOTE_PATH, "the fixed answer is given to a real write request");

    const outcome = interpretWriteReply(status, body);
    assert.equal(outcome.kind, "waiting");
    assert.equal(outcome.jobId, "");
    assert.match(outcome.message, /cannot follow the card/);
    assert.equal(shouldPoll(outcome), false, "no id means there is nothing to check");
    assert.equal(outcome.sha256, "");
  });

  test("a 200 with a state word this plugin does not know is an error, never a save", async () => {
    // The dangerous shape: HTTP said fine, so a mapping that trusts the status
    // would call it saved. "applied" is not a word this plugin knows, so it has to
    // say what it cannot say instead of guessing.
    const fake = await startFakeJarvis({
      mode: "fixed",
      answer: { status: 200, body: { ok: true, state: "applied", path: NOTE_PATH } },
    });
    const { status, body } = await send(fake, formatRequest(NOTE_PATH, "spark", "bold", "add", SHA_A));
    assert.equal(status, 200);

    const outcome = interpretWriteReply(status, body);
    assert.equal(outcome.kind, "error");
    assert.notEqual(outcome.kind, "saved", "an unknown state word must never read as saved");
    assert.match(outcome.message, /state "applied"/);
    assert.match(outcome.message, /cannot say the change was saved/);
    assert.equal(outcome.sha256, "", "an unknown state word must not become a new hash");
  });

  test("a 409 conflict with no current hash is a conflict, and nothing is offered as one", async () => {
    // A create carries no version to compare against (createNoteRequest sends no
    // expected_sha256), so a conflict it reports has no current hash to hand back.
    // The panel must report the conflict it was given and must not invent a hash
    // for a note it never read.
    const fake = await startFakeJarvis({
      mode: "fixed",
      answer: {
        status: 409,
        body: {
          ok: false,
          state: "conflict",
          path: "Exists.md",
          message: "A note already exists at Exists.md, so nothing was created.",
        },
      },
    });
    const { status, body } = await send(fake, createNoteRequest("Exists.md", "# New\n"));
    assert.equal(status, 409);

    const outcome = interpretWriteReply(status, body);
    assert.equal(outcome.kind, "conflict");
    assert.equal(outcome.sha256, "", "nothing was written, so there is no new hash");
    assert.equal(outcome.currentSha256, "", "this refusal named no current hash to offer");
    assert.equal(outcome.message, "A note already exists at Exists.md, so nothing was created.");
  });

  test("a 400 refusal is an error in the backend's words, and never the word saved", async () => {
    // A refused body is a refusal, not a failed save: the reason is the useful
    // part, and a sentence claiming a save would send the owner looking for a
    // change that does not exist.
    const fake = await startFakeJarvis({
      mode: "fixed",
      answer: { status: 400, body: { ok: false, state: "refused", error: "the line is empty" } },
    });
    const { status, body } = await send(fake, insertRequest(NOTE_PATH, "", "Session", SHA_A));
    assert.equal(status, 400);
    assert.equal(fake.requests.at(-1).body.text, "", "the request the plugin really sent had an empty line");

    const outcome = interpretWriteReply(status, body);
    assert.equal(outcome.kind, "error");
    assert.match(outcome.message, /the line is empty/);
    assert.ok(!/saved/i.test(outcome.message), "a refusal must not read as a save");
    assert.equal(outcome.sha256, "");
  });

  test("an HTTP error on a write route is an error, in the backend's words when it sent any", async () => {
    // Each status is a different fix: 403 the note is protected, 413 the note is
    // too big, 429 a queue of cards is full, 503 the vault is unreachable, 500
    // something broke. Only 429 and 500 arrive with no sentence of their own, so
    // those two must fall back to the plugin's plain words.
    const cases = [
      {
        status: 403,
        body: { ok: false, error: "this note is protected from Jarvis" },
        keeps: "this note is protected from Jarvis",
      },
      {
        status: 413,
        body: {
          ok: false,
          message: "The new text is 900000 bytes, over the 262144 byte limit this editor saves.",
        },
        keeps: "over the 262144 byte limit",
      },
      { status: 429, body: {}, says: /busy/ },
      {
        status: 503,
        body: { ok: false, error: "No note was saved: the Obsidian vault is not set up." },
        keeps: "the Obsidian vault is not set up",
      },
      { status: 500, body: {}, says: /HTTP 500/ },
    ];
    for (const item of cases) {
      const fake = await startFakeJarvis({ mode: "fixed", answer: { status: item.status, body: item.body } });
      const { status, body } = await send(fake, insertRequest(NOTE_PATH, "Bought milk", "Session", SHA_A));
      assert.equal(status, item.status);
      const outcome = interpretWriteReply(status, body);
      const at = "HTTP " + item.status;
      assert.equal(outcome.kind, "error", at + " must be an error, not a result");
      assert.equal(outcome.httpStatus, item.status);
      assert.equal(outcome.sha256, "", at + " wrote nothing, so no new hash");
      if (item.keeps) {
        assert.ok(
          outcome.message.includes(item.keeps),
          at + " must keep the backend's own sentence: " + outcome.message,
        );
      }
      if (item.says) assert.match(outcome.message, item.says, at + " must fall back to the plugin's own words");
    }
  });

  test("a 401 on a write route names the token, and the sentence never contains it", async () => {
    // The existing 401 test covers the template list; a write is the route that
    // matters most, because a refused write must not look like a stored change.
    // The sentence may name the token; it must never print it.
    const fake = await startFakeJarvis({ mode: "unauthorized" });
    const wrongToken = "wrong-token-for-a-write-route";
    const { status, body } = await send(fake, insertRequest(NOTE_PATH, "Bought milk", "Session", SHA_A), {
      token: wrongToken,
    });
    assert.equal(status, 401);
    assert.equal(fake.requests.at(-1).token, wrongToken, "the plugin sent the token it was configured with");

    const outcome = interpretWriteReply(status, body);
    assert.equal(outcome.kind, "error");
    assert.match(outcome.message, /token/i);
    assert.match(outcome.message, /bad or missing X-Jarvis-Token/);
    assert.ok(!outcome.message.includes(wrongToken), "an error sentence must never contain the token itself");
    assert.equal(outcome.sha256, "");
  });
});

/* ---------------------------------------------------------------------- */
/* 7. The status poll: how one card ended, and what happens when it cannot */
/*    be asked at all                                                      */
/* ---------------------------------------------------------------------- */

describe("a status poll that cannot report a save", () => {
  test("denied, failed and conflict keep the backend's sentence and its own kind", async () => {
    // These are final answers from the PC, not guesses: the panel must keep the
    // backend's words verbatim and stop checking. A wrong kind here is the
    // difference between "you said no" and "Jarvis broke".
    const cases = [
      { state: "denied", message: "You said no, so nothing was changed." },
      { state: "failed", message: "Jarvis could not write a.md: the file is read-only." },
      { state: "conflict", message: "The note changed while the card waited, so nothing was written." },
    ];
    for (const item of cases) {
      const fake = await startFakeJarvis({
        mode: "fixed",
        answer: {
          status: 200,
          body: { ok: false, state: item.state, path: NOTE_PATH, message: item.message },
        },
      });
      const { status, body } = await send(fake, changeStatusRequest("job-insert"));
      assert.equal(status, 200);
      const outcome = interpretStatusReply(status, body);
      assert.equal(outcome.kind, item.state, item.state + " must keep its own kind");
      assert.equal(outcome.message, item.message, item.state + " must keep the backend's sentence");
      assert.equal(outcome.sha256, "", "a write that did not land reports no new hash");
      assert.equal(shouldPoll(outcome), false, item.state + " is final, so the checks stop");
    }
  });

  test("an id the backend does not know is an error with the backend's sentence, and the waiting stops", async () => {
    // The normal fake answers an id it never made with the documented 404. The
    // plugin must not keep waiting on it: a 404 can never turn into an answer.
    const fake = await startFakeJarvis();
    const { status, body } = await send(fake, changeStatusRequest("job-never-existed"));
    assert.equal(status, 404);
    const outcome = interpretStatusReply(status, body);
    assert.equal(outcome.kind, "error");
    assert.equal(outcome.message, "There is no note save with that id on this PC.");
    assert.equal(shouldPoll(outcome), false, "a 404 must stop the checks, not restart them");
  });

  test("a 2xx with no state at all is an error that says the change ended without saying how", async () => {
    // HTTP 200 is not an outcome: without a state word the plugin cannot report a
    // save, and saying nothing would leave the owner guessing.
    const fake = await startFakeJarvis({
      mode: "fixed",
      answer: { status: 200, body: { ok: true, path: NOTE_PATH } },
    });
    const { status, body } = await send(fake, changeStatusRequest("job-insert"));
    assert.equal(status, 200);
    const outcome = interpretStatusReply(status, body);
    assert.equal(outcome.kind, "error");
    assert.equal(outcome.message, "Jarvis answered without saying how the change ended.");
  });

  test("losing the server between the write and the status check rejects instead of inventing an answer", async () => {
    // The closest safe stand-in for "contact was lost while checking the card":
    // the same port stops answering. This is the transport layer under client.ts's
    // unreachable-message wrap and the panel's own "Lost contact" sentence (both
    // files import `obsidian` and cannot be loaded here), so what is proven is
    // that the failure REJECTS rather than resolving into an invented outcome, and
    // that no sentence about it says "saved".
    const fake = await startFakeJarvis();
    const posted = await send(fake, insertRequest(NOTE_PATH, "Bought milk", "Session", SHA_A));
    const waiting = interpretWriteReply(posted.status, posted.body);
    assert.equal(waiting.kind, "waiting");
    assert.equal(shouldPoll(waiting), true, "the normal answer names a job, so the panel would start checking");

    await fake.close();
    const error = await send(fake, changeStatusRequest(waiting.jobId)).then(
      () => {
        throw new Error("expected the status check to fail once its server was gone");
      },
      (caught) => caught,
    );
    const said = shortError(error);
    assert.equal(typeof said, "string");
    assert.ok(said.length > 0, "a lost connection must reach the screen with words in it");
    assert.ok(!/saved/i.test(said), "losing contact must never read as a saved write");
  });
});

/* ---------------------------------------------------------------------- */
/* 8. Capture: filed, or honestly not filed                                */
/* ---------------------------------------------------------------------- */

describe("a capture that was not filed", () => {
  test("denied, failed and timed_out are not_filed with the backend's own words", async () => {
    // A 2xx that names a terminal state is the dangerous shape: HTTP said fine,
    // the state says it did not happen. The capture status route sets ok:false for
    // every state it reports other than filed/waiting (the ok:false branch maps
    // those the same way), so this pins the words themselves - the part a shared
    // interpreter could get wrong - and none of them may become "filed".
    const cases = [
      { state: "denied", message: "You said no, so nothing was written." },
      { state: "failed", message: "Not filed: the Obsidian vault could not be opened." },
      { state: "timed_out", message: "Nobody answered the approval card in time, so nothing was written." },
    ];
    for (const item of cases) {
      const fake = await startFakeJarvis({
        mode: "fixed",
        answer: {
          status: 200,
          body: { ok: true, id: "job-capture", state: item.state, message: item.message },
        },
      });
      const { status, body } = await send(fake, captureStatusRequest("job-capture"));
      assert.equal(status, 200);
      const outcome = interpretCaptureReply(status, body);
      assert.equal(outcome.kind, "not_filed", item.state + " was not filed, whatever HTTP said");
      assert.equal(outcome.message, item.message, item.state + " must keep the backend's sentence");
    }
  });

  test("a 2xx with an unknown state word is not filed, and names the word it could not read", async () => {
    // "saved" is a write state, not a capture state. Guessing it means filed would
    // tell the owner their words are in today's note when nothing proved it, so the
    // plugin must say which word it did not understand.
    const fake = await startFakeJarvis({
      mode: "fixed",
      answer: { status: 200, body: { ok: true, state: "saved", id: "job-capture" } },
    });
    const { status, body } = await send(fake, captureStatusRequest("job-capture"));
    assert.equal(status, 200);
    const outcome = interpretCaptureReply(status, body);
    assert.notEqual(outcome.kind, "filed");
    assert.equal(outcome.kind, "not_filed");
    assert.match(outcome.message, /state "saved"/);
    assert.match(outcome.message, /does not know/);
    assert.ok(!/^Filed/.test(outcome.message), "the message must not open by saying it was filed");
  });

  test("a capture status 404 for an unknown id is an error with the route's sentence", async () => {
    // A 404 only means this PC has no record of that job: Jarvis may have been
    // restarted after filing, so claiming "not filed" would say something this
    // plugin cannot know. It must keep the route's sentence and stop checking.
    const fake = await startFakeJarvis({
      mode: "fixed",
      answer: { status: 404, body: { ok: false, error: "no note with that id on this PC" } },
    });
    const { status, body } = await send(fake, captureStatusRequest("job-capture"));
    assert.equal(status, 404);
    const outcome = interpretCaptureReply(status, body);
    assert.equal(outcome.kind, "error");
    assert.notEqual(outcome.kind, "not_filed", "an unknown id is not proof that nothing was filed");
    assert.equal(outcome.message, "no note with that id on this PC");
    assert.equal(outcome.httpStatus, 404);
    assert.equal(outcome.jobId, "");
  });

  test("capture waiting with no status id says it cannot follow it", async () => {
    // The same shape as a write route: a card with no id cannot be checked, so the
    // dialog must say that rather than reporting a filing it cannot see.
    const fake = await startFakeJarvis({
      mode: "fixed",
      answer: {
        status: 202,
        body: { ok: true, state: "waiting", message: "Waiting for your approval." },
      },
    });
    const { status, body } = await send(fake, captureRequest("Remember the milk"));
    assert.equal(status, 202);
    const outcome = interpretCaptureReply(status, body);
    assert.equal(outcome.kind, "waiting");
    assert.equal(outcome.jobId, "");
    assert.ok(outcome.message.includes("Waiting for your approval."));
    assert.match(outcome.message, /cannot follow it/);
    assert.notEqual(outcome.kind, "filed");
  });
});

/* ---------------------------------------------------------------------- */
/* 9. Chat, read and templates: the backend's words, or the plugin's own   */
/*    honest sentence                                                      */
/* ---------------------------------------------------------------------- */

describe("answers the panel must not round up into success", () => {
  test("chat keeps the backend's reason instead of inventing an empty answer", async () => {
    // A refusal and an empty answer are different things: "too long" tells the
    // owner what to do, "empty answer" sends them looking for a bug.
    const cases = [
      {
        status: 503,
        body: { ok: false, error: "the model is still loading" },
        keeps: "the model is still loading",
      },
      {
        status: 200,
        body: { ok: false, error: "that question is too long" },
        keeps: "that question is too long",
        notSays: "empty answer",
      },
      { status: 200, body: { choices: [] }, keeps: "empty answer" },
    ];
    for (const item of cases) {
      const fake = await startFakeJarvis({ mode: "fixed", answer: { status: item.status, body: item.body } });
      const { status, body } = await send(fake, chatRequest("What is this note about?", "Note: a.md", NOTE_PATH));
      const outcome = interpretChatReply(status, body);
      assert.equal(outcome.kind, "error", "HTTP " + item.status + " must not become an answer");
      assert.equal(outcome.answer, "", "an error carries no answer text");
      assert.ok(outcome.message.includes(item.keeps), "the message must say: " + item.keeps);
      if (item.notSays) {
        assert.ok(!outcome.message.includes(item.notSays), "a refusal must not read as an empty answer");
      }
    }
  });

  test("read keeps the backend's reason, and refuses an answer with no hash", async () => {
    // A read with no sha256 cannot safely start an edit: every surgical write
    // needs the hash it started from, so the panel must stop here instead of
    // offering buttons that would be refused as conflicts.
    const cases = [
      {
        status: 404,
        body: { ok: false, error: "no such note: Missing.md" },
        keeps: "no such note: Missing.md",
      },
      { status: 200, body: { ok: true, path: NOTE_PATH, text: NOTE_TEXT }, noHash: true },
      { status: 200, body: { ok: false, error: "the note is locked" }, keeps: "the note is locked" },
    ];
    for (const item of cases) {
      const fake = await startFakeJarvis({ mode: "fixed", answer: { status: item.status, body: item.body } });
      const { status, body } = await send(fake, readNoteRequest(NOTE_PATH));
      const outcome = interpretReadReply(status, body);
      assert.equal(outcome.kind, "error");
      assert.equal(outcome.sha256, "", "an error must never hand out a hash");
      if (item.keeps) {
        assert.ok(outcome.message.includes(item.keeps), "the message must keep: " + item.keeps);
      }
      if (item.noHash) {
        assert.match(outcome.message, /hash/);
        assert.match(outcome.message, /cannot be made/);
        assert.equal(outcome.text, "", "no text is offered for an edit that cannot be made");
      }
    }
  });

  test("templates: a list that is not a list, a refusal, and a 503 all become honest errors", async () => {
    // The panel lists names. A string where a list should be must not read as "no
    // templates" (the owner would think their vault is empty), and a 503 must name
    // the vault, because that is the part the owner can fix.
    const cases = [
      {
        status: 200,
        body: { ok: true, count: 1, templates: "daily" },
        says: /template list was not a list/,
      },
      {
        status: 200,
        body: { ok: false, message: "the templates folder is missing" },
        keeps: "the templates folder is missing",
      },
      { status: 503, body: {}, says: /HTTP 503/, vault: true },
    ];
    for (const item of cases) {
      const fake = await startFakeJarvis({ mode: "fixed", answer: { status: item.status, body: item.body } });
      const { status, body } = await send(fake, templatesRequest());
      const outcome = interpretTemplatesReply(status, body);
      assert.equal(outcome.kind, "error");
      assert.deepEqual(outcome.names, [], "an error never lists a guessed name");
      assert.equal(outcome.why, "");
      if (item.keeps) {
        assert.ok(outcome.message.includes(item.keeps), "the message must keep: " + item.keeps);
      }
      if (item.says) assert.match(outcome.message, item.says);
      if (item.vault) assert.match(outcome.message, /vault/);
    }
  });
});
