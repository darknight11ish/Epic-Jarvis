/**
 * quickbar-attach.mjs — a FILE the owner drops on the small Alt+Space bar
 * (the owner's decision of 2026-11-09, chosen on a clickable card: a dropped
 * file must work in the quick bar too, not only in the HUD and the chat
 * windows).
 *
 * JARVIS-API.md section 163.6 is the contract; this is its quickbar half. It
 * pins the things that would otherwise drift silently:
 *
 *   1. THE SAME RULES AND WORDS AS THE HUD — the eight kinds, 2,500,000
 *      bytes, a kind and a size checked BEFORE a byte is read, and the HUD's
 *      own refusal and "Read on your PC." sentences. The HUD's constants are
 *      READ OUT of src/jarvis_hud.html and compared with the bar's, so the two
 *      windows cannot come to two ways of saying one rule.
 *   2. THE ONE-FILE RULE — a drop carries a list; one file goes with a
 *      question, so the first file the bar can take is taken and the rest are
 *      named, and a second drop REPLACES the file already waiting (in the
 *      HUD's own "One file goes with a question, so …" words).
 *   3. NOTHING AUTO-SENDS — the rule block has no send, no invoke, no fetch
 *      and no listener; a file waits on the chip until Enter, and Remove
 *      takes it away.
 *   4. THE REQUEST SHAPE — the block `attachRide` really puts in the
 *      browser-preview body: `has_file: true` at the top level and the
 *      attachment on the NEWEST message only, as a copy. The Tauri path is
 *      pinned in Rust (`commands.rs`), and the source pins here prove the
 *      command carries the argument this page fills in.
 *
 * Node only, no browser, no Playwright: it reads the shipped files and runs
 * the shipped lines. What it cannot prove: that Windows really hands a
 * dropped file to this window (a real Explorer drag is NOT-TESTABLE at a
 * desk), and how the chip looks - tests/a11y.mjs and friends own the look.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const TAURI = join(HERE, "..", "src-tauri");

const indexHtml = readFileSync(join(SRC, "index.html"), "utf8");
const mainJs = readFileSync(join(SRC, "main.js"), "utf8");
const hudHtml = readFileSync(join(SRC, "jarvis_hud.html"), "utf8");
const commandsRs = readFileSync(join(TAURI, "src", "commands.rs"), "utf8");
const libRs = readFileSync(join(TAURI, "src", "lib.rs"), "utf8");
const tauriConf = JSON.parse(readFileSync(join(TAURI, "tauri.conf.json"), "utf8"));

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── the two halves of the page's own code ───────────────────────────────── */

const BLOCK_START = "/* ---- A file dropped on the bar";
const BLOCK_END = "/* ---- The bar's own listeners for it";

/** The whole attach rule, exactly the lines that ship. */
function attachBlock() {
  const start = mainJs.indexOf(BLOCK_START);
  const end = mainJs.indexOf(BLOCK_END, start);
  assert.ok(start > 0 && end > start, "the quickbar attach block is missing from main.js");
  return mainJs.slice(start, end);
}

/** The same block plus two readers, for the sandbox below. */
function attachCode() {
  return attachBlock()
    + "\n;globalThis.__attach = () => attachFile;"
    + "\n;globalThis.__consts = {max: ATTACH_MAX_BYTES, kinds: ATTACH_KINDS.slice(),"
    + " readOn: ATTACH_READ_ON_PC, outside: ATTACH_OUTSIDE, again: ATTACH_AGAIN,"
    + " refusedKind: ATTACH_REFUSED_KIND, refusedPicture: ATTACH_REFUSED_PICTURE,"
    + " oneFile: ATTACH_ONE_FILE};";
}

/** The gesture wiring, which is deliberately OUTSIDE the lifted rule block. */
function wiringBlock() {
  const start = mainJs.indexOf(BLOCK_END);
  assert.ok(start > 0, "the quickbar attach wiring is missing from main.js");
  return mainJs.slice(start, mainJs.indexOf("/**\n * Sends the prompt", start));
}

function fakePage() {
  const nodes = {};
  const listeners = {};
  const node = (id) => nodes[id] || (nodes[id] = {
    id, hidden: false, textContent: "",
    classList: {
      on: new Set(),
      toggle(c, v) { v ? this.on.add(c) : this.on.delete(c); },
      add(c) { this.on.add(c); },
      remove(c) { this.on.delete(c); },
      contains(c) { return this.on.has(c); },
    },
  });
  class FakeReader {
    // Synchronous on purpose: the rule is what is under test here, and a
    // deterministic sandbox keeps every check a plain assertion.
    readAsDataURL(file) {
      const b64 = Buffer.from(String(file.__bytes || "hello"), "utf8").toString("base64");
      this.result = `data:${file.type || "application/octet-stream"};base64,${b64}`;
      if (this.onload) this.onload();
    }
  }
  const sandbox = {
    dom: {
      attachChip: node("attach-chip"),
      attachName: node("attach-chip-name"),
      attachRemove: node("attach-chip-remove"),
      attachNote: node("attach-note"),
    },
    // The page's own hooks, stubbed to nothing: this suite tests the rule,
    // not the announcement or the window resize.
    announce: () => {},
    syncWindowHeight: () => {},
    FileReader: FakeReader,
    console,
    setTimeout,
    Buffer,
  };
  vm.createContext(sandbox);
  vm.runInContext(attachCode(), sandbox);
  return { sandbox, node, listeners };
}

const read = (file, name) => {
  const m = new RegExp(
    `const ${name} = "((?:[^"\\\\]|\\\\.)*)";`).exec(file);
  assert.ok(m, `${name} is gone`);
  return JSON.parse(`"${m[1]}"`);
};

/* ── 1. the same rules and the same words as the HUD ─────────────────────── */

check("the bar takes exactly the HUD's eight kinds", () => {
  const { sandbox } = fakePage();
  const hud = /const ATTACH_KINDS = \[([^\]]*)\];/.exec(hudHtml);
  assert.ok(hud, "the HUD's ATTACH_KINDS is gone");
  const listed = hud[1].split(",").map((s) => s.trim().replace(/"/g, ""));
  assert.deepEqual([...sandbox.__consts.kinds], listed,
    "the bar's kinds have drifted from the HUD's");
  assert.deepEqual(listed,
    [".pdf", ".docx", ".xlsx", ".pptx", ".md", ".markdown", ".txt", ".csv"]);
});

check("the cap is 2,500,000 bytes, the HUD's number", () => {
  const { sandbox } = fakePage();
  assert.equal(sandbox.__consts.max, 2500000);
  assert.match(hudHtml, /const ATTACH_MAX_BYTES = 2500000;/);
});

check("the sentences are the HUD's own, word for word", () => {
  const { sandbox } = fakePage();
  for (const [ours, theirs] of [
    ["readOn", "ATTACH_READ_ON_PC"],
    ["outside", "ATTACH_OUTSIDE"],
    ["again", "ATTACH_AGAIN"],
    ["refusedKind", "ATTACH_REFUSED_KIND"],
    ["refusedPicture", "ATTACH_REFUSED_PICTURE"],
  ]) {
    assert.equal(sandbox.__consts[ours], read(hudHtml, theirs),
      `${ours} has drifted from the HUD's ${theirs}`);
  }
  // The size refusal is one sentence with both sizes filled in, the same
  // shape the HUD writes: "That file is 4.4 MB. Files up to 2.5 MB …".
  assert.match(attachBlock(), /"That file is " \+ attachSize\(file\.size\)/);
  assert.match(attachBlock(), /Files up to "\s*\+\s*attachSize\(ATTACH_MAX_BYTES\)/);
  assert.match(attachBlock(), /folder Jarvis may look in/);
});

check("the size words are the HUD's: 1.2 MB, 640 KB, 12 bytes", () => {
  const { sandbox } = fakePage();
  assert.equal(sandbox.attachSize(1200000), "1.2 MB");
  assert.equal(sandbox.attachSize(2500000), "2.5 MB");
  assert.equal(sandbox.attachSize(640000), "640 KB");
  assert.equal(sandbox.attachSize(12), "12 bytes");
  assert.equal(sandbox.attachSize(1), "1 byte");
});

check("the extension is read off a name, case and all - and none is none", () => {
  const { sandbox } = fakePage();
  assert.equal(sandbox.attachExt("Tenancy.PDF"), ".pdf");
  assert.equal(sandbox.attachExt("notes.tar.gz"), ".gz");
  assert.equal(sandbox.attachExt("README"), "");
  assert.equal(sandbox.attachExt(".env"), "");
});

/* ── 2. refused before it is read, in the HUD's words ────────────────────── */

check("a kind Jarvis cannot read: refused in words, nothing attached", () => {
  const { sandbox, node } = fakePage();
  sandbox.attachTake({ name: "song.mp3", size: 4000, type: "audio/mpeg" });
  assert.equal(sandbox.__attach(), null, "something was attached anyway");
  assert.equal(node("attach-chip").hidden, true, "a name chip is showing with nothing attached");
  assert.equal(node("attach-note").hidden, false);
  assert.match(node("attach-note").textContent, /not a kind Jarvis reads/);
  assert.ok(node("attach-note").classList.contains("bad"), "the refusal is not marked as one");
  assert.equal(node("attach-chip-remove").hidden, true, "Remove is showing with nothing attached");
});

check("a picture is sent to the picture path, not read here", () => {
  const { sandbox, node } = fakePage();
  sandbox.attachTake({ name: "holiday.png", size: 4000, type: "image/png" });
  assert.equal(sandbox.__attach(), null);
  assert.match(node("attach-note").textContent, /picture button/);
});

check("an over-cap file is refused before it is read, and the sentence names both sizes", () => {
  const { sandbox, node } = fakePage();
  let readFlag = false;
  sandbox.attachTake({ name: "video.pdf", size: 4400000,
    get __bytes() { readFlag = true; return ""; } });
  assert.equal(readFlag, false, "the file was read before the size was checked");
  const text = node("attach-note").textContent;
  assert.match(text, /That file is 4\.4 MB/);
  assert.match(text, /Files up to 2\.5 MB can be attached/);
  assert.match(text, /folder Jarvis may look in/);
  assert.equal(sandbox.__attach(), null);
});

/* ── 3. accepted: one file, held for exactly one turn ────────────────────── */

check("an accepted file: the bytes are held, the chip names it, nothing is sent", () => {
  const { sandbox, node } = fakePage();
  sandbox.attachTake({ name: "tenancy.pdf", size: 1200000, type: "application/pdf",
                       __bytes: "the file's bytes" });
  const held = sandbox.__attach();
  assert.ok(held, "nothing was attached");
  assert.equal(held.name, "tenancy.pdf");
  assert.equal(held.mime, "application/pdf");
  assert.equal(held.size, 1200000);
  assert.equal(held.data, Buffer.from("the file's bytes", "utf8").toString("base64"));
  assert.equal(node("attach-chip").hidden, false);
  assert.equal(node("attach-chip-name").textContent, "tenancy.pdf");
  assert.equal(node("attach-chip-remove").hidden, false, "there is no way to remove it");
  const note = node("attach-note").textContent;
  assert.match(note, /tenancy\.pdf — 1\.2 MB Read on your PC\./);
  assert.match(note, /outside text/);
  assert.match(note, /again for another question/);
  assert.equal(node("attach-note").classList.contains("bad"), false);
});

check("a second drop REPLACES the file, in the HUD's one-file words", () => {
  const { sandbox, node } = fakePage();
  sandbox.attachTake({ name: "first.pdf", size: 10, type: "application/pdf", __bytes: "one" });
  sandbox.attachTake({ name: "second.txt", size: 20, type: "text/plain", __bytes: "two" });
  const held = sandbox.__attach();
  assert.equal(held.name, "second.txt", "a second file did not replace the first");
  assert.equal(node("attach-chip-name").textContent, "second.txt");
  assert.match(node("attach-note").textContent,
    /One file goes with a question, so the file dropped before it was replaced\./);
  // Still exactly one file: there is nowhere for a second to live.
  assert.equal(typeof held, "object");
  assert.deepEqual(Object.keys(held).sort(), ["data", "mime", "name", "size"]);
});

check("a drop of several files takes the first one Jarvis can read and names the rest", () => {
  const { sandbox, node } = fakePage();
  sandbox.attachDrop([
    { name: "song.mp3", size: 4000, type: "audio/mpeg" },
    { name: "tenancy.pdf", size: 12000, type: "application/pdf", __bytes: "x" },
    { name: "notes.txt", size: 40, type: "text/plain", __bytes: "hi" },
  ]);
  assert.equal(sandbox.__attach().name, "tenancy.pdf");
  assert.match(node("attach-note").textContent,
    /One file goes with a question, so the other 2 were not attached\./);
});

check("a batch with nothing Jarvis can read refuses and says none were attached", () => {
  const { sandbox, node } = fakePage();
  sandbox.attachDrop([{ name: "song.mp3", size: 4000 },
                      { name: "film.mp4", size: 90000 }]);
  assert.equal(sandbox.__attach(), null);
  assert.match(node("attach-note").textContent, /not a kind Jarvis reads/);
  assert.match(node("attach-note").textContent, /None of the 2 dropped files were attached\./);
});

check("Remove lets the file go, and the bar is quiet again", () => {
  const { sandbox, node } = fakePage();
  sandbox.attachClear();
  assert.equal(sandbox.__attach(), null);
  assert.equal(node("attach-chip").hidden, true);
  assert.equal(node("attach-chip-name").textContent, "");
  assert.equal(node("attach-chip-remove").hidden, true);
  assert.equal(node("attach-note").hidden, true);
  assert.equal(node("attach-note").textContent, "");
});

/* ── 4. nothing auto-sends ───────────────────────────────────────────────── */

check("the rule block sends nothing and listens for nothing", () => {
  // Comments may talk about `stream_chat`; only the code matters, so they are
  // taken out first - a rule that cannot be met by prose.
  const block = attachBlock()
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
  for (const forbidden of [/\bsend\s*\(/, /\binvoke/, /\bfetch\s*\(/, /stream_chat/,
                           /addEventListener/, /new FormData/]) {
    assert.doesNotMatch(block, forbidden,
      `the attach rule block does its own sending: ${forbidden}`);
  }
  // ...and it builds no HTML and sets no style attribute (the chip is text).
  assert.doesNotMatch(block, /innerHTML|outerHTML|insertAdjacentHTML|document\.write/);
  assert.doesNotMatch(block, /style=/);
});

check("the drop wiring only takes the gesture - the file waits for Enter", () => {
  const wiring = wiringBlock();
  assert.match(wiring, /dom\.shell\.addEventListener\("dragover"/);
  assert.match(wiring, /dom\.shell\.addEventListener\("drop"/);
  assert.match(wiring, /types\.indexOf\("Files"\) < 0\) return;/,
    "a text drag is swallowed as if it were a file");
  assert.match(wiring, /e\.preventDefault\(\)/, "the drop would navigate the page to the file");
  assert.match(wiring, /attachDragOn|classList\.add\("drag-over"\)/,
    "nothing highlights the bar while a file is held over it");
  assert.doesNotMatch(wiring, /\bsend\s*\(|\binvoke|stream_chat/,
    "the drop handler sends by itself");
  // A paste is NOT a door here: the owner's decision added a drop, and the
  // HUD's paste handler is not copied over.
  assert.doesNotMatch(wiring, /addEventListener\("paste"/);
});

/* ── 5. the request shape, and the command that carries it ───────────────── */

check("attachRide: has_file at the top, the attachment on the NEWEST message only", () => {
  const { sandbox } = fakePage();
  const file = { name: "tenancy.pdf", mime: "application/pdf", size: 12, data: "aGVsbG8=" };
  const body = {
    messages: [
      { role: "user", content: "earlier" },
      { role: "assistant", content: "an answer" },
      { role: "user", content: "what does this say?" },
    ],
    stream: true,
  };
  sandbox.attachRide(body, file);
  assert.equal(body.has_file, true, "has_file is not set beside the message");
  assert.equal(body.messages.length, 3, "a message was added or dropped");
  assert.equal(body.messages[2].attachment.data, "aGVsbG8=");
  for (const i of [0, 1]) {
    assert.equal(body.messages[i].attachment, undefined, `message ${i} carries the file too`);
  }
  assert.equal(body.messages[2].content, "what does this say?");
});

check("attachRide with no file changes nothing at all", () => {
  const { sandbox } = fakePage();
  const body = { messages: [{ role: "user", content: "hello" }], stream: true };
  const before = JSON.stringify(body);
  sandbox.attachRide(body, null);
  assert.equal(JSON.stringify(body), before);
  assert.equal(body.has_file, undefined);
});

check("the page hands the file to stream_chat's own argument, once", () => {
  // The payload gets `attachment`; Rust builds the body from it. The page
  // drops its copy at the same moment, so the next turn cannot re-send it.
  assert.match(mainJs, /payload\.attachment = attachFile;/);
  assert.match(mainJs, /invokeStrict\("stream_chat",\s*\{\s*\.\.\.payload,\s*onEvent: channel\s*\}\)/,
    "the quick bar's stream no longer passes its whole payload to stream_chat");
  assert.match(mainJs, /attachClear\(\);\s*\n\s*syncWindowHeight\(\);/,
    "the file is not let go when the question is sent");
  // ...and the same shape on the browser-preview path.
  assert.match(mainJs, /attachRide\(body, payload\.attachment\);/);
});

check("the Rust command carries the attachment and builds the body from it", () => {
  // The argument on the command itself.
  const sig = /pub async fn stream_chat\(([\s\S]*?)\) -> Result<\(\), String>/.exec(commandsRs);
  assert.ok(sig, "stream_chat is gone from commands.rs");
  assert.match(sig[1], /attachment: Option<ChatAttachment>/,
    "the Rust command has no attachment argument - a drop cannot ride the bar's chat");
  // The body builder: newest user message, has_file beside it.
  assert.match(commandsRs, /pub\(crate\) fn add_chat_attachment\(/);
  assert.match(commandsRs, /fields\.insert\(\s*"attachment"\.into\(\)/);
  assert.match(commandsRs, /fields\.insert\("has_file"\.into\(\), serde_json::json!\(true\)\)/);
  // The command really calls it before posting.
  assert.match(commandsRs, /if let Some\(file\) = attachment \{[\s\S]{0,400}add_chat_attachment\(&mut payload, file\)/,
    "stream_chat never puts the attachment into the body");
  // The same cap and the same kind sentence as the page, pinned in Rust.
  assert.match(commandsRs, /CHAT_ATTACH_MAX_BYTES: u64 = 2_500_000;/);
  const { sandbox } = fakePage();
  assert.ok(commandsRs.includes(sandbox.__consts.refusedKind),
    "the Rust refusal sentence has drifted from the page's");
  assert.ok(commandsRs.includes(sandbox.__consts.refusedPicture),
    "the Rust picture sentence has drifted from the page's");
  // One command, still the one this window already holds - no new permission.
  assert.equal((libRs.match(/commands::stream_chat,/g) || []).length, 1);
});

check("the quickbar window lets the drop through: Tauri's own handler is off", () => {
  // Tauri replaces WebView2's drag-drop handler on Windows when this is on,
  // so the page's `drop` event never fires. The quickbar is declared in
  // tauri.conf.json (not built in Rust), so this setting IS its off switch.
  const quickbar = tauriConf.app.windows.find((w) => w.label === "quickbar");
  assert.ok(quickbar, "no quickbar window in tauri.conf.json");
  assert.equal(quickbar.url, "index.html");
  assert.equal(quickbar.dragDropEnabled, false,
    "the quickbar leaves Tauri's drag-drop handler on, so a dropped file never reaches the page");
});

check("the bar has the chip, its Remove and the line under it", () => {
  assert.match(indexHtml, /id="attach-chip"/);
  assert.match(indexHtml, /id="attach-chip-name"/);
  assert.match(indexHtml, /id="attach-chip-remove"/);
  assert.match(indexHtml, /<span class="sr-only">Remove the file<\/span>/);
  assert.match(indexHtml, /id="attach-note"/);
  // The chip is inside the bar's own controls row, and the line is in the
  // stack below the bar (where the window can grow to show every word).
  const bar = indexHtml.indexOf('class="bar"');
  const chip = indexHtml.indexOf('id="attach-chip"');
  const meta = indexHtml.indexOf('class="bar-meta"');
  const stack = indexHtml.indexOf('class="stack"');
  const note = indexHtml.indexOf('id="attach-note"');
  assert.ok(meta > 0 && chip > meta && stack > chip && note > stack,
    "the chip is not beside the bar's controls, or the line is not under the bar");
});

/* ── the tally ───────────────────────────────────────────────────────────── */

console.log(fails.length
  ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nthe quickbar attach rules hold");
process.exit(fails.length ? 1 : 0);
