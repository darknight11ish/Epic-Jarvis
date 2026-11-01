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
        body: { ok: false, error: "There is no note change with that id on this PC." },
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
    const reply = answer(state, entry, entry.body);
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
 */
async function startFakeJarvis(options = {}) {
  const state = {
    mode: options.mode ?? "ok",
    token: options.token ?? TOKEN,
    notFoundBody: options.notFoundBody ?? { ok: false, error: "Not Found" },
    requests: [],
    violations: [],
    jobs: makeJobs(),
  };
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

  const fake = {
    baseUrl: "http://127.0.0.1:" + server.address().port,
    token: state.token,
    mode: state.mode,
    requests: state.requests,
    violations: state.violations,
    state,
    close: () =>
      new Promise((resolve, reject) => {
        server.closeAllConnections();
        server.close((error) => (error ? reject(error) : resolve()));
      }),
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
