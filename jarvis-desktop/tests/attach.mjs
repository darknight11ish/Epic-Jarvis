/**
 * attach.mjs — a FILE the owner attaches to the HUD chat (2026-10-29).
 *
 * JARVIS-API.md section 163 is the contract; this suite is the desktop half of
 * it. It pins the three things that would otherwise drift silently:
 *
 *   1. THE CAPS AND THE WORDING — 2,500,000 bytes, the seven kinds my_files
 *      already reads, "Read on your PC.", the outside-text sentence and the
 *      "attach it again" sentence. The backend owns the same words in
 *      jarvis_attached_file.py, and backend/test_attached_file.py checks the
 *      page carries them, so the two apps cannot say different things.
 *   2. THE BEHAVIOUR — the page's REAL functions are lifted out of
 *      src/jarvis_hud.html and run in a sandbox with a fake DOM and a fake
 *      FileReader: a refused kind, an over-cap file and an accepted one.
 *   3. THE REQUEST SHAPE — the block send() really builds is lifted the same
 *      way and run: `has_file: true` at the top level, the attachment on the
 *      NEWEST user message only, and the page's own history left alone (the
 *      next turn re-sends it, so a copy there would upload the file again).
 *
 * Node only, no browser, no Playwright: it reads the shipped page and runs the
 * shipped lines. The one thing it cannot prove is how the chip LOOKS — that is
 * `hud.mjs`'s job, in a real page.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const HUD = join(SRC, "jarvis_hud.html");
const html = readFileSync(HUD, "utf8");

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── 1. the caps and the wording ─────────────────────────────────────────── */

const at = (marker) => html.indexOf(marker);

check("the hidden file input exists, with the seven kinds and nothing else", () => {
  const tag = /<input[^>]*id="attach-file"[^>]*>/.exec(html);
  assert.ok(tag, "no <input id=\"attach-file\"> in the page");
  assert.match(tag[0], /type="file"/);
  assert.match(tag[0], /hidden/);
  const accept = /accept="([^"]*)"/.exec(tag[0]);
  assert.ok(accept, "the input has no accept list");
  assert.equal(accept[1],
    ".pdf,.docx,.xlsx,.pptx,.md,.markdown,.txt,.csv",
    `the accept list changed: ${accept[1]}`);
  // No Rust, no new command: the page reads the file itself.
  assert.doesNotMatch(html.slice(at("id=\"attach-file\"") - 1200,
                                 at("id=\"attach-file\"") + 1200), /invoke\(/);
});

check("the cap is 2,500,000 bytes, the same number the PC enforces", () => {
  assert.match(html, /const ATTACH_MAX_BYTES = 2500000;/);
  assert.match(html, /attachSize\(ATTACH_MAX_BYTES\)/,
    "the refusal no longer names the cap from the constant");
});

check("the seven kinds are one list, and .pdf and an unknown type cannot pass it", () => {
  const kinds = /const ATTACH_KINDS = \[([^\]]*)\];/.exec(html);
  assert.ok(kinds, "ATTACH_KINDS is gone");
  const listed = kinds[1].split(",").map((s) => s.trim().replace(/"/g, ""));
  assert.deepEqual(listed,
    [".pdf", ".docx", ".xlsx", ".pptx", ".md", ".markdown", ".txt", ".csv"]);
});

check("the chip's wording is the design's, sentence for sentence", () => {
  assert.match(html, /const ATTACH_READ_ON_PC = "Read on your PC\.";/);
  assert.match(html, /const ATTACH_OUTSIDE = "The words count as outside text, so a web search in this chat will still ask first\.";/);
  assert.match(html, /const ATTACH_AGAIN = "Attach it again for another question\.";/);
});

check("the refusal sentences say why, and a picture is sent to the picture path", () => {
  assert.match(html, /ATTACH_REFUSED_KIND = "Jarvis can read PDF, Word, Excel, PowerPoint, Markdown, text and CSV files in a chat/);
  assert.match(html, /ATTACH_REFUSED_PICTURE = "A picture goes in as a picture: attach it with the picture button/);
  assert.match(html, /folder Jarvis may look in/);
});

check("the chip is under #input, and there is one way in for each gesture", () => {
  const composer = at("class=\"composer\"");
  const bar = at("class=\"attach-bar\"");
  const input = at("<textarea id=\"input\"");
  assert.ok(composer > 0 && bar > composer && input > 0 && bar > input,
    "the attach bar is not after the composer");
  assert.ok(html.includes('id="attach-chip"') && html.includes('id="attach-clear"')
    && html.includes('id="attach-pick"'), "the chip, Remove or the picker is missing");
  assert.match(html, /window\.addEventListener\("dragover"/, "no drop guard");
  assert.match(html, /window\.addEventListener\("drop"/, "no drop handler");
  assert.match(html, /window\.addEventListener\("paste"/, "no paste handler");
  // A dropped file must not navigate the page to it.
  assert.match(html, /if\(types\.indexOf\("Files"\) >= 0\) e\.preventDefault\(\);/);
});

check("the chip uses textContent and classes, never an HTML sink or a style attribute", () => {
  // `let ATTACH = null;` is the first line of the JS block; the CSS comment
  // above it starts the same way, so the marker has to be the code.
  const start = at("let ATTACH = null;");
  const end = at('$("mic").addEventListener', start);
  const block = html.slice(start, end);
  assert.doesNotMatch(block, /innerHTML|outerHTML|insertAdjacentHTML|document\.write/,
    "the attach code builds HTML");
  assert.doesNotMatch(block, /style=/, "the attach code uses a style attribute");
  assert.match(block, /chip\.textContent = text;/, "the chip is not set by textContent");
  assert.match(block, /classList\.toggle\("bad"/, "the refusal is not a class");
});

/* ── 2. the page's own functions, run ───────────────────────────────────── */

/** The page's method, and no more: what runs inside this block is what ships. */
function attachCode() {
  // `let ATTACH = null;` is the first line of the JS block; the CSS comment
  // above it starts the same way, so the marker has to be the code.
  const start = at("let ATTACH = null;");
  const end = at('$("mic").addEventListener', start);
  assert.ok(start > 0 && end > start, "the attach block is missing from the page");
  return html.slice(start, end)
    // The top-level `let`/`const` are not on the context's global object, so
    // hand the suite a reader for them (and for ATTACH). Nothing else is added.
    + "\n;globalThis.__attach = () => ATTACH;"
    + "\n;globalThis.__consts = {max: ATTACH_MAX_BYTES, kinds: ATTACH_KINDS.slice(),"
    + " readOn: ATTACH_READ_ON_PC, again: ATTACH_AGAIN};";
}

function fakePage() {
  const nodes = {};
  const handlers = {};
  const listeners = (name) => (handlers[name] = handlers[name] || []);
  const node = (id) => nodes[id] || (nodes[id] = {
    id, hidden: false, textContent: "", listens: {},
    classList: { on: new Set(), toggle(c, v) { v ? this.on.add(c) : this.on.delete(c); },
                 remove(c) { this.on.delete(c); }, contains(c) { return this.on.has(c); } },
    addEventListener(name, fn) { this.listens[name] = fn; },
  });
  class FakeReader {
    readAsDataURL(file) {
      const b64 = Buffer.from(String(file.__bytes || "hello"), "utf8").toString("base64");
      this.result = `data:${file.type || "application/octet-stream"};base64,${b64}`;
      setTimeout(() => this.onload && this.onload(), 0);
    }
  }
  const sandbox = {
    $: node,
    window: { addEventListener: (name, fn) => listeners(name).push(fn) },
    FileReader: FakeReader,
    console,
    setTimeout,
    Buffer,
  };
  vm.createContext(sandbox);
  vm.runInContext(attachCode(), sandbox);
  return { sandbox, nodes, node, handlers, listeners };
}

check("the size words are the backend's: 1.2 MB, 640 KB, 12 bytes", () => {
  const { sandbox } = fakePage();
  assert.equal(sandbox.attachSize(1200000), "1.2 MB");
  assert.equal(sandbox.attachSize(2500000), "2.5 MB");
  assert.equal(sandbox.attachSize(640000), "640 KB");
  assert.equal(sandbox.attachSize(12), "12 bytes");
  assert.equal(sandbox.attachSize(1), "1 byte");
});

check("the extension is read off a name, case and all - and a file with none has none", () => {
  const { sandbox } = fakePage();
  assert.equal(sandbox.attachExt("Tenancy.PDF"), ".pdf");
  assert.equal(sandbox.attachExt("notes.tar.gz"), ".gz");
  assert.equal(sandbox.attachExt("README"), "");
  assert.equal(sandbox.attachExt(".env"), "");
});

check("a kind Jarvis cannot read: refused in words, nothing attached", () => {
  const { sandbox, node } = fakePage();
  sandbox.attachTake({ name: "song.mp3", size: 4000, type: "audio/mpeg" });
  const chip = node("attach-chip");
  assert.equal(sandbox.__attach(), null, "something was attached anyway");
  assert.equal(chip.hidden, false);
  assert.match(chip.textContent, /not a kind Jarvis reads/);
  assert.ok(chip.classList.contains("bad"), "the refusal is not marked as one");
});

check("a picture is sent to the picture path, not read here", () => {
  const { sandbox, node } = fakePage();
  sandbox.attachTake({ name: "holiday.png", size: 4000, type: "image/png" });
  assert.equal(sandbox.__attach(), null);
  assert.match(node("attach-chip").textContent, /picture button/);
});

check("an over-cap file is refused before it is read, and the sentence names both sizes", () => {
  const { sandbox, node } = fakePage();
  let read = false;
  sandbox.attachTake({ name: "video.pdf", size: 4400000, get __bytes() { read = true; return ""; } });
  assert.equal(read, false, "the file was read before the size was checked");
  const text = node("attach-chip").textContent;
  assert.match(text, /That file is 4.4 MB/);
  assert.match(text, /Files up to 2\.5 MB can be attached/);
  assert.match(text, /folder Jarvis may look in/);
  assert.equal(sandbox.__attach(), null);
});

check("an accepted file: the bytes are held as base64 and the chip says all three things", async () => {
  const { sandbox, node } = fakePage();
  sandbox.attachTake({ name: "tenancy.pdf", size: 1200000, type: "application/pdf",
                       __bytes: "the file's bytes" });
  await new Promise((r) => setTimeout(r, 5));
  const held = sandbox.__attach();
  assert.ok(held, "nothing was attached");
  assert.equal(held.name, "tenancy.pdf");
  assert.equal(held.mime, "application/pdf");
  assert.equal(held.size, 1200000);
  assert.equal(held.data, Buffer.from("the file's bytes", "utf8").toString("base64"),
    "the data is not the raw bytes base64-encoded");
  const chip = node("attach-chip");
  assert.match(chip.textContent, /tenancy\.pdf — 1\.2 MB Read on your PC\./);
  assert.match(chip.textContent, /outside text/);
  assert.match(chip.textContent, /again for another question/);
  assert.equal(chip.classList.contains("bad"), false);
  assert.equal(node("attach-pick").hidden, true, "the picker still shows while a file is attached");
  assert.equal(node("attach-clear").hidden, false, "there is no way to remove it");
});

check("Remove lets the file go, and the picker comes back", () => {
  const { sandbox, node } = fakePage();
  sandbox.attachClear();
  assert.equal(sandbox.__attach(), null);
  assert.equal(node("attach-chip").hidden, true);
  assert.equal(node("attach-chip").textContent, "");
  assert.equal(node("attach-pick").hidden, false);
});

check("a drop of a FILE is handled and does not navigate the page", () => {
  const { sandbox, handlers } = fakePage();
  const taken = [];
  sandbox.attachTake = (f) => taken.push(f);
  let prevented = false;
  handlers.drop[0]({
    preventDefault: () => { prevented = true; },
    dataTransfer: { files: [{ name: "tenancy.pdf", size: 10 }] },
  });
  assert.equal(prevented, true, "the page would navigate to the dropped file");
  assert.equal(taken.length, 1, "the dropped file never reached attachTake");
});

check("a drop of TEXT is left alone - no preventDefault, nothing attached", () => {
  const { sandbox, handlers } = fakePage();
  const taken = [];
  sandbox.attachTake = (f) => taken.push(f);
  let prevented = false;
  handlers.drop[0]({ preventDefault: () => { prevented = true; },
                     dataTransfer: { files: [] } });
  assert.equal(prevented, false, "dragging text around would now be swallowed");
  assert.equal(taken.length, 0);
});

check("a paste carrying a FILE is taken; a text paste never is", () => {
  const { sandbox, handlers } = fakePage();
  const taken = [];
  sandbox.attachTake = (f) => taken.push(f);
  handlers.paste[0]({ preventDefault() {}, clipboardData: { files: [{
    name: "notes.txt", size: 4 }] } });
  handlers.paste[0]({ preventDefault() {}, clipboardData: { files: [] } });
  handlers.paste[0]({ preventDefault() {}, clipboardData: null });
  assert.equal(taken.length, 1, "a text paste was taken as a file, or the file was missed");
  assert.equal(taken[0].name, "notes.txt");
});

/* ── 3. the request shape send() really builds ───────────────────────────── */

/** The block `if(ATTACH && body.messages ...)` out of send(), indent included. */
function sendBlock() {
  const start = at("if(ATTACH && body.messages && body.messages.length){");
  assert.ok(start > 0, "the attachment is not put in the request body at all");
  const end = html.indexOf("\n  }\n", start);
  assert.ok(end > start, "the attachment block does not close");
  return html.slice(start, end + 4);
}

check("the request carries has_file and the attachment on the NEWEST message only", () => {
  const sandbox = {
    ATTACH: { name: "tenancy.pdf", mime: "application/pdf", size: 12, data: "aGVsbG8=" },
    attachClear: () => { sandbox.cleared = true; },
    body: {
      messages: [
        { role: "user", content: "earlier" },
        { role: "assistant", content: "an answer" },
        { role: "user", content: "what does this say?" },
      ],
      conversation_id: "abc",
      device: "hud",
      stream: true,
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(sendBlock(), sandbox);
  assert.equal(sandbox.body.has_file, true, "has_file is not set beside has_image");
  assert.equal(sandbox.body.messages.length, 3, "a message was added or dropped");
  assert.equal(sandbox.body.messages[2].attachment.data, "aGVsbG8=",
    "the attachment is not on the newest user message");
  for (const i of [0, 1]) {
    assert.equal(sandbox.body.messages[i].attachment, undefined,
      `message ${i} carries the file too`);
  }
  assert.equal(sandbox.cleared, true, "the page kept the bytes after the send");
  // The last message is a COPY: nothing else may now carry the field.
  assert.equal(sandbox.body.messages[2].role, "user");
  assert.equal(sandbox.body.messages[2].content, "what does this say?");
});

check("with no file attached the request is exactly what it always was", () => {
  const sandbox = {
    ATTACH: null,
    attachClear: () => { throw new Error("attachClear ran with nothing attached"); },
    body: { messages: [{ role: "user", content: "hello" }], stream: true },
  };
  vm.createContext(sandbox);
  vm.runInContext(sendBlock(), sandbox);
  assert.equal(sandbox.body.has_file, undefined, "an ordinary turn claims a file");
  assert.equal(sandbox.body.messages[0].attachment, undefined);
});

check("the page's own history is never given the bytes", () => {
  // The copy above is the point: `S.messages` is re-sent with every later turn,
  // so an attachment stored there would be uploaded again and again.
  const start = at("const userNode = addMessage(\"user\", text);");
  const end = at("S.messages.push({role:\"user\", content:text, provenance});", start);
  assert.ok(start > 0 && end > start);
  const pushed = html.slice(start, end);
  assert.doesNotMatch(pushed, /attachment/,
    "the message pushed into the page's history carries the file");
});

/* ── 4. the three copies are one file ────────────────────────────────────── */

check("the page is byte-identical in the desktop, backend/ and the base", () => {
  const mine = readFileSync(HUD, "utf8");
  for (const other of [["..", "..", "backend", "jarvis_hud.html"],
                       ["..", "..", "jarvis-backend", "jarvis_hud.html"]]) {
    const p = join(HERE, ...other);
    assert.equal(readFileSync(p, "utf8"), mine, `${other} has drifted from src/jarvis_hud.html`);
  }
});

/* ── the tally ───────────────────────────────────────────────────────────── */

console.log(fails.length
  ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nthe attach half holds");
process.exit(fails.length ? 1 : 0);
