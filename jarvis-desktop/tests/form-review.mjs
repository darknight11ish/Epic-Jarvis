/**
 * The picture of a filled-in web form on the "submit this form" card
 * (docs/FORM-REVIEW-DESIGN.md, 2026-09-30; src/form-review.js,
 * src-tauri/src/brain/form_review.rs).
 *
 * What must hold:
 * - the picture is asked for only for a row whose detail carries `picture`,
 *   once per card, and never for any other card;
 * - it is held in memory only and dropped with the card (and an answer that
 *   arrives after the card went is dropped);
 * - if it cannot be loaded the card says one plain sentence; nothing here
 *   touches Approve or Deny;
 * - while App lock is on nothing is shown (Rust answers `locked`);
 * - neither the id nor the picture is ever logged or stored;
 * - CONTROL: the widget, the HUD page and toasts do not load it; Rust's
 *   command is the Jarvis bar's alone, refuses odd ids, checks App lock
 *   before asking the PC, and never logs.
 *
 * Needs no browser: a tiny stand-in for the few DOM calls it makes.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { mountFormReview, pictureId, WORDS } from "../src/form-review.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

class El {
  constructor(tag) {
    this.tag = tag; this.children = []; this.attrs = {}; this.listeners = {};
    this.hidden = false; this.className = ""; this._text = ""; this.parent = null;
  }
  get textContent() { return this._text; }
  set textContent(v) { this._text = String(v); }
  append(...kids) { for (const k of kids) { k.parent = this; this.children.push(k); } }
  replaceChildren(...kids) { this.children = []; this.append(...kids); }
  setAttribute(k, v) { this.attrs[k] = v; }
  removeAttribute(k) { delete this.attrs[k]; delete this[k]; }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this); this.parent = null; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  click() { for (const fn of this.listeners.click || []) fn(); }
}
const made = [];
globalThis.document = { createElement: (tag) => { const e = new El(tag); made.push(e); return e; }, hidden: false };

/* Nothing may be logged or stored: any console output or storage call fails. */
const logged = [];
for (const m of ["log", "info", "warn", "error", "debug"]) {
  const real = console[m].bind(console);
  console[m] = (...a) => { if (!String(a[0]).match(/^(ok |FAIL)/)) logged.push(a.join(" ")); real(...a); };
}
let storageTouched = false;
globalThis.localStorage = new Proxy({}, { get() { storageTouched = true; return () => {}; } });
globalThis.sessionStorage = globalThis.localStorage;

const ID = "fr_abc123-XYZ";
const JPEG = "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////";
const row = (over = {}) => ({ id: "ap1", action: "browser_form_submit", detail: { picture: ID }, ...over });

function mount(invoke) {
  const box = new El("div");
  box.hidden = true;
  const calls = [];
  const keys = {};
  const page = {
    addEventListener: (t, f) => { keys[t] = f; },
    removeEventListener: (t) => { delete keys[t]; },
  };
  const announced = [];
  const view = mountFormReview(box, {
    invoke: async (command, args) => { calls.push({ command, args }); return invoke(command, args); },
    onChange: () => {},
    announce: (t) => announced.push(t),
    doc: page,
  });
  return { box, view, calls, keys, announced };
}
const ok = async () => ({ ok: true, jpeg: JPEG, width: 800, height: 600 });
const imgOf = (box) => box.children[0].children[0];

await check("the row's picture id is read from an object, JSON text or cut-off text", () => {
  assert.equal(pictureId(row()), ID);
  assert.equal(pictureId({ detail: JSON.stringify({ picture: ID, site: "x" }) }), ID);
  assert.equal(pictureId({ detail: `{"site": "x", "picture": "${ID}", "values": "cut of` }), ID);
  for (const d of [undefined, null, "", "plain text", {}, { picture: 5 }, { picture: "a b" },
    { picture: "../x" }, { picture: "a".repeat(65) }, { picture: "" }]) {
    assert.equal(pictureId({ detail: d }), null, JSON.stringify(d));
  }
  assert.equal(pictureId(null), null);
});

await check("only a row with a picture asks for one, and only once per card", async () => {
  const t = mount(ok);
  await t.view.show({ id: "a", action: "send_email", detail: { to: "x@y.z" } });
  await t.view.show({ id: "b", action: "browser_form_submit", detail: "no picture here" });
  assert.equal(t.calls.length, 0);
  assert.equal(t.box.hidden, true);
  await t.view.show(row());
  await t.view.show(row()); // a resync of the same card
  await t.view.show(row({ detail: JSON.stringify({ picture: ID }) }));
  assert.equal(t.calls.length, 1);
  assert.deepEqual(t.calls[0], { command: "form_review_picture", args: { id: ID } });
  await t.view.show(row({ id: "ap2" })); // a different card asks again
  assert.equal(t.calls.length, 2);
});

await check("the picture shows small, with its plain alt text, and enlarges on a click", async () => {
  const t = mount(ok);
  await t.view.show(row());
  assert.equal(t.box.hidden, false);
  const thumb = t.box.children[0];
  assert.equal(thumb.tag, "button");
  assert.equal(thumb.attrs["aria-label"], WORDS.enlarge);
  const img = imgOf(t.box);
  assert.equal(img.alt, "The form as Jarvis filled it in");
  assert.equal(img.src, `data:image/jpeg;base64,${JPEG}`);
  thumb.click();
  const overlay = t.box.children[1];
  assert.equal(overlay.attrs.role, "dialog");
  assert.equal(overlay.children[0].alt, WORDS.alt);
  assert.ok(t.keys.keydown, "Escape is caught while the picture is big");
  let stopped = false;
  t.keys.keydown({ key: "Escape", preventDefault() {}, stopPropagation() { stopped = true; } });
  assert.equal(stopped, true, "Escape closes the picture, not the whole card");
  assert.equal(t.box.children.length, 1);
  assert.equal(t.keys.keydown, undefined);
  thumb.click();
  t.box.children[1].click(); // a click anywhere closes it
  assert.equal(t.box.children.length, 1);
});

await check("the picture is dropped when the card goes, and a late answer is dropped too", async () => {
  const t = mount(ok);
  await t.view.show(row());
  const img = imgOf(t.box);
  t.box.children[0].click();
  t.view.clear();
  assert.equal(t.box.hidden, true);
  assert.equal(t.box.children.length, 0);
  assert.equal(img.src, `data:image/jpeg;base64,${JPEG}`, "(the old node is simply unreachable)");
  assert.equal(t.view.shownKey(), null);
  assert.equal(t.keys.keydown, undefined);
  let release;
  const slow = mount(() => new Promise((r) => { release = () => r({ ok: true, jpeg: JPEG }); }));
  const pending = slow.view.show(row());
  slow.view.clear();
  release();
  await pending;
  assert.equal(slow.box.children.length, 0, "a picture for a card that is gone is not shown");
  assert.equal(slow.box.hidden, true);
  // A row that loses its picture clears the box as well.
  const t2 = mount(ok);
  await t2.view.show(row());
  await t2.view.show({ id: "ap1", detail: {} });
  assert.equal(t2.box.hidden, true);
  assert.equal(t2.box.children.length, 0);
});

await check("a picture that cannot be loaded says one plain sentence", async () => {
  assert.equal(WORDS.failed,
    "Jarvis could not load the picture of the form. Read the details below before you approve.");
  for (const fn of [
    async () => { throw new Error("offline"); },
    async () => ({ ok: false }),
    async () => ({ ok: true, jpeg: "" }),
    async () => ({ ok: true, jpeg: "<script>alert(1)</script>" }),
    async () => ({ ok: true }),
    async () => null,
  ]) {
    const t = mount(fn);
    await t.view.show(row());
    assert.equal(t.box.hidden, false);
    assert.equal(t.box.children.length, 1);
    assert.equal(t.box.children[0].textContent, WORDS.failed);
    assert.deepEqual(t.announced, [WORDS.failed]);
  }
  // The module knows nothing about Approve or Deny.
  const code = read("src/form-review.js").replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "")
    .replace(/before you approve/g, "");
  assert.ok(!/approve|deny|decide/i.test(code));
});

await check("while App lock is on nothing is shown, and it asks again after the unlock", async () => {
  let locked = true;
  const t = mount(async () => (locked ? { ok: false, locked: true } : { ok: true, jpeg: JPEG }));
  await t.view.show(row());
  assert.equal(t.box.hidden, true);
  assert.equal(t.box.children.length, 0);
  locked = false;
  await t.view.show(row());
  assert.equal(t.calls.length, 2);
  assert.equal(imgOf(t.box).alt, WORDS.alt);
});

await check('"Hide memory lists and chat history": no picture, one plain line, asked again once it is off', async () => {
  assert.equal(WORDS.hidden,
    'The picture of the form is hidden because "Hide memory lists and chat history" is on. ' +
    "Turn that off in Settings to see it, or read the details below before you approve.");
  let hidden = true;
  const t = mount(async () => (hidden ? { ok: false, hidden: true } : { ok: true, jpeg: JPEG }));
  await t.view.show(row());
  assert.equal(t.box.hidden, false);
  assert.equal(t.box.children.length, 1);
  assert.equal(t.box.children[0].textContent, WORDS.hidden);
  hidden = false;
  await t.view.show(row());
  assert.equal(t.calls.length, 2);
  assert.equal(imgOf(t.box).alt, WORDS.alt);
  // Rust decides, before it asks the PC for anything.
  const rs = read("src-tauri/src/brain/form_review.rs");
  const cmd = rs.slice(rs.indexOf("pub async fn form_review_picture"));
  assert.ok(cmd.includes("private_hidden") || rs.includes("crate::lock::private_hidden"));
  assert.ok(cmd.indexOf("hidden(&app)") < cmd.indexOf(".get("), "checked before asking the PC");
  assert.ok(cmd.lastIndexOf("hidden(&app)") > cmd.indexOf(".send()"), "and again after, in case it was turned on meanwhile");
});

await check("neither the id nor the picture is logged or stored", async () => {
  assert.equal(storageTouched, false);
  for (const line of logged) {
    assert.ok(!line.includes(ID) && !line.includes(JPEG), line);
  }
  const src = read("src/form-review.js");
  assert.ok(!/console\.|localStorage|sessionStorage|indexedDB|caches\b/.test(src));
  const main = read("src/main.js");
  const at = main.indexOf("const formReview");
  assert.ok(!/console\./.test(main.slice(at, at + 400)));
});

await check("CONTROL: only the Jarvis bar's full card loads it - not the widget, toasts or the HUD page", () => {
  for (const f of ["src/widget.js", "src/widget.html", "src/widget-board.js", "src/jarvis_hud.html",
    "src-tauri/src/hud_bootstrap.js", "src/brain.js", "src/floating.js"]) {
    assert.ok(!/form[-_]review|approval-picture/.test(read(f)), f);
  }
  const main = read("src/main.js");
  assert.equal((main.match(/formReview\.show\(/g) || []).length, 1);
  assert.equal((main.match(/formReview\.clear\(/g) || []).length, 1);
  // The one show() is in refreshApproval (the full card), not in any toast or digest path.
  const at = main.indexOf("formReview.show(");
  const start = main.lastIndexOf("\nfunction ", at);
  assert.match(main.slice(start, start + 40), /function refreshApproval/);
  const closeAt = main.indexOf("formReview.clear(");
  assert.match(main.slice(main.lastIndexOf("\nfunction ", closeAt), closeAt), /function closeApproval/);
  // Only the quickbar window holds the command.
  for (const f of ["widget", "brain", "settings", "hud", "floating"]) {
    let cap = "";
    try { cap = read(`src-tauri/capabilities/${f}.json`); } catch { continue; }
    assert.ok(!cap.includes("form-review"), f);
  }
  assert.ok(read("src-tauri/capabilities/quickbar.json").includes('"form-review"'));
});

await check("CONTROL: Rust registers the one command, refuses odd ids, checks App lock, never logs", () => {
  const rs = read("src-tauri/src/brain/form_review.rs");
  assert.ok(read("src-tauri/src/lib.rs").includes("brain::form_review::form_review_picture"));
  assert.ok(read("src-tauri/build.rs").includes('"form_review_picture"'));
  assert.ok(read("src-tauri/permissions/surfaces.toml").includes("allow-form-review-picture"));
  assert.ok(!/println!|eprintln!|dbg!|log::|tracing::|std::fs|File::/.test(rs.replace(/\/\/.*$/gm, "")));
  const cmd = rs.slice(rs.indexOf("pub async fn form_review_picture"));
  assert.ok(cmd.indexOf("valid_id(&id)") < cmd.indexOf(".get("), "ids are checked before anything is sent");
  assert.ok(cmd.indexOf("locked(&app)") < cmd.indexOf(".get("), "App lock is checked before asking the PC");
  assert.ok(!/stale\(/.test(cmd), "a read: not held on a stale link");
  assert.ok(rs.includes('PICTURE_PATH: &str = "/api/form-review/picture"'));
});

console.log(fails.length ? `\n${fails.length} failed` : "\nall form-review checks passed");
process.exit(fails.length ? 1 : 0);
