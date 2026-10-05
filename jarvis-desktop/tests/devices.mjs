/**
 * Settings -> Devices (docs/PAIRING-DESIGN.md, phase 1, sections 7.1 and
 * 10): pairing a phone by QR code, with a key per device.
 *
 * What must hold:
 * - a PC whose backend has no pairing says so, and the old "Show the token
 *   for my phone" stays where it always was;
 * - the device list: This PC with no Remove, each phone with Remove, which
 *   asks the design's "are you sure?" first and removes ONE device;
 * - the old shared key's row in its three states, the warning naming the
 *   address that still uses it, Retire at once, Bring it back as a card;
 *   the old reveal moves under that row, renamed, and hides once retired;
 * - the pairing panel: the QR picture exactly as Rust drew it, the typed
 *   code, the countdown, the PC's own sentence for each state, the four
 *   words as given; the code leaves the page when the session ends;
 *   Cancel; the address remembered or found;
 * - rule 4: Pair a phone and Bring it back wait for a live link; Remove and
 *   Retire only take access away and never wait;
 * - CONTROL (the Rust): settings window only; the window hidden from
 *   screen capture before the code is handed over; the QR text never
 *   handed over at all.
 *
 * The approval card itself is not tested here: it is an ordinary card,
 * answered in the Jarvis bar or the widget (decide.mjs, card-words.mjs).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  countdown,
  removeQuestion,
  sessionLine,
  SHARED_FIRST_PAIR_ROW,
  SHARED_PROMPT_RETIRE,
  sharedSignedLine,
  sharedView,
  signedLine,
  wordsLine,
} from "../src/devices-words.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const NOW = Math.floor(Date.now() / 1000);

/** GET /api/devices as the design (6.4) gives it. */
function list({ shared = {}, pairing = {}, extra = [] } = {}) {
  return {
    you: "pc",
    devices: [
      { id: "pc", name: "This PC", kind: "pc", removable: false },
      { id: "d3f9a1c2e", name: "Pixel 9", kind: "phone", created: 1790000000,
        last_seen: NOW - 120, this_device: false, removable: true, approval_key: false },
      ...extra,
    ],
    shared: { retired: false, retired_at: null, last_other_seen: null,
              last_other_address: null, can_bring_back_here: true, ...shared },
    pairing: { available: true, why_not: null, ...pairing },
  };
}

// A tiny, real SVG picture standing in for the one Rust draws.
const SVG = "data:image/svg+xml;base64," + Buffer.from(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" fill="#ffffff"/></svg>',
).toString("base64");
const START = { ok: true, qr_svg: SVG, code: "K7QM-4TXD", expires_in: 600, tries_left: 3 };
const WORDS = ["tulip", "anchor", "mellow", "crane"];

/* ── The words, without a page ─────────────────────────────────────────── */

await check("the words: the PC's own sentence wins, the design's otherwise", async () => {
  assert.equal(sessionLine({ state: "burnt", message: "Three wrong tries - this code no longer works. Start again." }),
    "Three wrong tries - this code no longer works. Start again.");
  assert.equal(sessionLine({ state: "waiting_for_phone" }), "Waiting for your phone…");
  assert.equal(sessionLine({ state: "done", device_name: "Pixel 9" }), "Pixel 9 is connected.");
  assert.equal(sessionLine({ state: "something_new" }), "");
  assert.equal(countdown(581), "Works for 9:41 more");
  assert.equal(countdown(600), "Works for 10:00 more");
  assert.equal(countdown(0), "This code has run out of time.");
  assert.equal(wordsLine(WORDS), "tulip · anchor · mellow · crane");
  assert.equal(removeQuestion("Pixel 9"),
    "Remove Pixel 9? It stops reaching Jarvis at once. To use it again, pair it again with the QR code.");
  const recent = sharedView({ retired: false, last_other_seen: NOW - 7200, last_other_address: "100.101.2.3" });
  assert.match(recent.line, /^Last used from another device \(100\.101\.2\.3\) 2 hours ago\. Pair that device first\.$/);
  assert.match(recent.retireQuestion, /100\.101\.2\.3/);
  assert.equal(recent.retire, true);
  const unused = sharedView({ retired: false, last_other_seen: null });
  assert.equal(unused.line, "No other device has used it.");
  assert.equal(unused.retireQuestion, null);
  const old = sharedView({ retired: false, last_other_seen: NOW - 40 * 86400 });
  assert.match(old.line, /^No other device has used it since \d{1,2} \w{3}\.$/);
  const retired = sharedView({ retired: true, retired_at: 1790000000, can_bring_back_here: true });
  assert.match(retired.line, /^Retired on \d{1,2} \w{3} - it now works on this PC only\.$/);
  assert.equal(retired.retire, false);
  assert.equal(retired.bringBack, true);
  assert.equal(sharedView({ retired: true, can_bring_back_here: false }).bringBack, false);
  // The first pairing is done: a device holds a key of its own, so the shared
  // key now works from this PC only - even though nobody pressed Retire
  // (backend, 2026-10-05). Neither button is offered: Retire would change
  // nothing, and Bring it back could not work.
  const firstOnly = sharedView({ retired: false, first_pair_only: true, can_bring_back_here: true });
  assert.equal(firstOnly.line, SHARED_FIRST_PAIR_ROW);
  assert.equal(firstOnly.retire, false);
  assert.equal(firstOnly.retireQuestion, null);
  assert.equal(firstOnly.bringBack, false);
});

await check("a device key is taken out of an error's Details (design 8.6)", async () => {
  const { scrubDetails } = await import("../src/plain-errors.js");
  const key = `jdk1.d3f9a1c2e.${"Ab9_-".repeat(8)}xyz`;
  assert.equal(key.length, 58);
  const out = scrubDetails(`HTTP 401 for ${key} at 100.101.2.3`);
  assert.ok(!out.includes("Ab9_-"), out);
  assert.ok(out.includes("100.101.2.3"), "an address stays - a bug report needs it");
});

await check("signed approvals: the words for on, waiting, off and absent; nothing on the PC row or an older backend", async () => {
  assert.equal(signedLine({ kind: "phone", approval_key: true }, true), "Signed approvals: on");
  assert.equal(signedLine({ kind: "phone", approval_key: "waiting" }, true),
    "Signed approvals: waiting for your yes (approve the card)");
  const off = "Signed approvals: off - risky approvals from this phone are refused until it turns them on";
  assert.equal(signedLine({ kind: "phone", approval_key: false }, true), off);
  assert.equal(signedLine({ kind: "phone" }, true), off, "absent counts as off");
  assert.equal(signedLine({ kind: "pc" }, true), "");
  assert.equal(signedLine({ kind: "phone", approval_key: true }, false), "");
  const seen = { retired: false, last_other_seen: NOW - 60 };
  assert.equal(sharedSignedLine(seen, true),
    "Risky approvals from this device are not yet signed - pair it and turn on signed approvals.");
  assert.equal(sharedSignedLine(seen, true, true), SHARED_PROMPT_RETIRE);
  assert.equal(sharedSignedLine(seen, false), "");
  assert.equal(sharedSignedLine({ retired: true, last_other_seen: NOW }, true), "");
  assert.equal(sharedSignedLine({ retired: true, last_other_seen: NOW }, true, true), "");
  assert.equal(sharedSignedLine({ retired: false, last_other_seen: null }, true), "");
  // Nothing left to retire once the first device has its own key: the prompt
  // would ask the owner to press a button that changes nothing.
  assert.equal(sharedSignedLine({ retired: false, first_pair_only: true }, true, true), "");
});

/* ── The page ─────────────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const VIEW = { width: 760, height: 1600 };
const open = (data = {}) => K.open(browser, base, "settings.html", data, VIEW);
const calls = (page, name) =>
  page.evaluate((n) => window.__calls.filter((c) => c[0] === n).map((c) => c[1] || null), name);

await check("a PC without pairing says so, and the old token stays in Connection", async () => {
  const page = await open();
  await page.waitForTimeout(400);
  const state = await page.locator("#dv-state").innerText();
  const bodyHidden = await page.locator("#dv-body").isHidden();
  const home = await page.evaluate(() => document.getElementById("pairing").closest("section").id);
  const button = await page.locator("#reveal-token").innerText();
  const errors = page.__errors;
  await page.close();
  assert.match(state, /cannot pair phones by QR code yet/);
  assert.ok(bodyHidden);
  assert.equal(home, "connection");
  assert.equal(button, "Show the token for my phone");
  assert.deepEqual(errors || [], []);
});

await check("the list: This PC cannot be removed, a phone can, with its dates", async () => {
  const page = await open({ devices: { list: list() } });
  await page.waitForTimeout(400);
  const rows = await page.locator("#dv-list li").allInnerTexts();
  const removes = await page.locator("#dv-list li button").count();
  const html = await page.content();
  await page.close();
  assert.equal(rows.length, 2);
  assert.match(rows[0], /This PC/);
  assert.match(rows[0], /cannot be removed/);
  assert.match(rows[1], /Pixel 9/);
  assert.match(rows[1], /paired \d{1,2} \w{3}/);
  assert.match(rows[1], /last used 2 minutes ago/);
  assert.equal(removes, 1, "only the phone has Remove");
  assert.ok(!/jdk1\.|token_sha256/.test(html), "no key on the page");
});

await check("Devices page: each phone's signed-approvals state, the shared-key sentence, and nothing on an older backend", async () => {
  const extra = [
    { id: "aaa111111", name: "Tablet", kind: "phone", created: 1790000000, last_seen: NOW - 60,
      removable: true, approval_key: true },
    { id: "bbb222222", name: "Fold", kind: "phone", created: 1790000000, last_seen: NOW - 60,
      removable: true, approval_key: "waiting" },
  ];
  const seen = { last_other_seen: NOW - 7200, last_other_address: "100.101.2.3" };
  const page = await open({ devices: { list: { ...list({ extra, shared: seen }), signed_approvals: true } } });
  await page.waitForTimeout(400);
  const rows = await page.locator("#dv-list li").allInnerTexts();
  const shared = await page.locator("#dv-shared-signed").innerText();
  const sharedShown = await page.locator("#dv-shared-signed").isVisible();
  await page.close();
  assert.ok(!/Signed approvals/.test(rows[0]), "the PC's own row says nothing");
  assert.match(rows[1], /Signed approvals: off - risky approvals from this phone are refused until it turns them on/);
  assert.match(rows[2], /Signed approvals: on/);
  assert.match(rows[3], /Signed approvals: waiting for your yes \(approve the card\)/);
  assert.ok(sharedShown);
  assert.equal(shared, SHARED_PROMPT_RETIRE);

  const unsignedPage = await open({
    devices: {
      list: {
        ...list({
          extra: [
            { id: "bbb222222", name: "Fold", kind: "phone", created: 1790000000, last_seen: NOW - 60,
              removable: true, approval_key: false },
          ],
          shared: seen,
        }),
        signed_approvals: true,
      },
    },
  });
  await unsignedPage.waitForTimeout(400);
  const unsignedShared = await unsignedPage.locator("#dv-shared-signed").innerText();
  await unsignedPage.close();
  assert.equal(unsignedShared, "Risky approvals from this device are not yet signed - pair it and turn on signed approvals.");

  const older = await open({ devices: { list: list({ extra, shared: seen }) } });
  await older.waitForTimeout(400);
  const oldRows = await older.locator("#dv-list li").allInnerTexts();
  const oldShared = await older.locator("#dv-shared-signed").isVisible();
  await older.close();
  assert.ok(oldRows.every((r) => !/Signed approvals/.test(r)), "an older backend shows nothing extra");
  assert.equal(oldShared, false);
});

await check("Remove asks the design's question first; No changes nothing, Yes removes one", async () => {
  const page = await open({ devices: { list: list() } });
  await page.waitForTimeout(400);
  const asked = [];
  page.once("dialog", (d) => { asked.push(d.message()); d.dismiss(); });
  await page.locator("#dv-list li button").click();
  await page.waitForTimeout(250);
  const none = await calls(page, "devices_remove");
  page.once("dialog", (d) => { asked.push(d.message()); d.accept(); });
  await page.locator("#dv-list li button").click();
  await page.waitForTimeout(400);
  const sent = await calls(page, "devices_remove");
  const rows = await page.locator("#dv-list li").count();
  const said = await page.locator("#dv-status").innerText();
  await page.close();
  assert.equal(asked[0], removeQuestion("Pixel 9"));
  assert.equal(none.length, 0, "a No still removed it");
  assert.deepEqual(sent, [{ id: "d3f9a1c2e" }], "exactly one id, never a list");
  assert.equal(rows, 1);
  assert.equal(said, "Pixel 9 was removed.");
});

await check("the old key: used elsewhere lately - named, Retire asks, then it is retired", async () => {
  const page = await open({ devices: { list: list({ shared: {
    last_other_seen: NOW - 7200, last_other_address: "100.101.2.3" } }) } });
  await page.waitForTimeout(400);
  const line = await page.locator("#dv-shared-line").innerText();
  const slot = await page.evaluate(() => document.getElementById("pairing").parentElement.id);
  const button = await page.locator("#reveal-token").innerText();
  const asked = [];
  page.once("dialog", (d) => { asked.push(d.message()); d.accept(); });
  await page.locator("#dv-retire").click();
  await page.waitForTimeout(400);
  const sent = await calls(page, "devices_shared");
  const after = await page.locator("#dv-shared-line").innerText();
  const oldKeyHidden = await page.locator("#pairing").isHidden();
  const bringBack = await page.locator("#dv-bring-back").isVisible();
  await page.close();
  assert.match(line, /100\.101\.2\.3/);
  assert.match(line, /Pair that device first\./);
  assert.equal(slot, "dv-old-key-slot", "the old reveal moved under the shared key");
  assert.equal(button, "Show the old shared key (not needed with QR pairing)");
  assert.match(asked[0] || "", /100\.101\.2\.3/, "the confirm names the address");
  assert.deepEqual(sent, [{ retired: true }]);
  assert.match(after, /^Retired on .* - it now works on this PC only\.$/);
  assert.ok(oldKeyHidden, "the old reveal is hidden once retired");
  assert.ok(bringBack);
});

await check("the old key: unused elsewhere - Retire needs no second question", async () => {
  const page = await open({ devices: { list: list() } });
  await page.waitForTimeout(400);
  const line = await page.locator("#dv-shared-line").innerText();
  let dialogs = 0;
  page.on("dialog", (d) => { dialogs += 1; d.dismiss(); });
  await page.locator("#dv-retire").click();
  await page.waitForTimeout(400);
  const sent = await calls(page, "devices_shared");
  await page.close();
  assert.equal(line, "No other device has used it.");
  assert.equal(dialogs, 0);
  assert.deepEqual(sent, [{ retired: true }]);
});

await check("the old key: retired - Bring it back raises a card, and says so", async () => {
  const page = await open({ devices: { list: list({ shared: { retired: true, retired_at: 1790000000 } }) } });
  await page.waitForTimeout(400);
  const retireShown = await page.locator("#dv-retire").isVisible();
  await page.locator("#dv-bring-back").click();
  await page.waitForTimeout(400);
  const sent = await calls(page, "devices_shared");
  const said = await page.locator("#dv-shared-status").innerText();
  await page.close();
  assert.ok(!retireShown);
  assert.deepEqual(sent, [{ retired: false }]);
  assert.match(said, /Waiting for your approval on the card, with Windows Hello/);
});

await check("rule 4: on a stale link Pair and Bring it back wait; Remove and Retire do not", async () => {
  const page = await open({ link: { stale: true },
                            devices: { list: list({ shared: { retired: true, retired_at: 1790000000 } }) } });
  await page.waitForTimeout(400);
  const pair = await page.locator("#dv-pair").isEnabled();
  const why = await page.locator("#dv-pair-why").innerText();
  const back = await page.locator("#dv-bring-back").isEnabled();
  const remove = await page.locator("#dv-list li button").isEnabled();
  await page.close();
  assert.ok(!pair, "Pair a phone offered on a stale link");
  assert.match(why, /catching up/);
  assert.ok(!back, "Bring it back offered on a stale link");
  assert.ok(remove, "Remove held on a stale link - it only takes access away");
  const page2 = await open({ link: { stale: true }, devices: { list: list() } });
  await page2.waitForTimeout(400);
  const retire = await page2.locator("#dv-retire").isEnabled();
  await page2.close();
  assert.ok(retire, "Retire held on a stale link - it only takes access away");
});

await check("pairing not possible on this PC: Pair is off, with the PC's reason", async () => {
  const why = "Windows Hello is not set up on this PC, so a new device cannot be approved. Set it up in Windows Settings, Accounts, Sign-in options.";
  const page = await open({ devices: { list: list({ pairing: { available: false, why_not: why } }) } });
  await page.waitForTimeout(400);
  const pair = await page.locator("#dv-pair").isEnabled();
  const said = await page.locator("#dv-pair-why").innerText();
  await page.close();
  assert.ok(!pair);
  assert.equal(said, why);
});

await check("Pair a phone: the picture as drawn, the code, the countdown, then the words, then connected", async () => {
  const page = await open({ devices: {
    list: list(),
    address: { address: "jarvis-pc.tail1234.ts.net", source: "tailscale" },
    start: START,
    sessions: [
      { state: "waiting_for_phone", expires_in: 598, tries_left: 3, device_name: null, words: null,
        wrong_tries_from: [], message: "Waiting for your phone..." },
      { state: "waiting_for_card", expires_in: 590, tries_left: 3, device_name: "Pixel 9", words: WORDS,
        wrong_tries_from: [], message: "Your phone asked. Check the card - the words must match: tulip · anchor · mellow · crane" },
      { state: "done", expires_in: 0, tries_left: 3, device_name: "Pixel 9", words: WORDS,
        wrong_tries_from: [], message: "Pixel 9 is connected." },
    ],
  } });
  await page.waitForTimeout(500);
  const prefilled = await page.locator("#dv-address").inputValue();
  await page.locator("#dv-pair").click();
  await page.waitForTimeout(300);
  const sent = await calls(page, "pair_start");
  const src = await page.locator("#dv-qr").getAttribute("src");
  const code = await page.locator("#dv-code").innerText();
  const count = await page.locator("#dv-countdown").innerText();
  const first = await page.locator("#dv-session").innerText();
  const pairOff = await page.locator("#dv-pair").isDisabled();
  await page.waitForTimeout(4300); // two reads, 2 s apart
  const words = await page.locator("#dv-words").innerText();
  const second = await page.locator("#dv-session").innerText();
  await page.waitForTimeout(2200);
  const last = await page.locator("#dv-session").innerText();
  const srcAfter = await page.locator("#dv-qr").getAttribute("src");
  const codeAfter = await page.locator("#dv-code").textContent();
  const boxHidden = await page.locator("#dv-code-box").isHidden();
  const closeShown = await page.locator("#dv-close").isVisible();
  const reads = await calls(page, "devices_list");
  const html = await page.content();
  const errors = page.__errors;
  await page.close();
  assert.equal(prefilled, "jarvis-pc.tail1234.ts.net", "the Tailscale name is offered");
  assert.deepEqual(sent, [{ address: "jarvis-pc.tail1234.ts.net" }]);
  assert.equal(src, SVG, "the picture exactly as Rust drew it");
  assert.equal(code, "K7QM-4TXD");
  assert.match(count, /^Works for (10:00|9:5\d) more$/);
  assert.match(first, /^Waiting for your phone/);
  assert.ok(pairOff, "a second Pair while a code is on screen");
  assert.equal(words, "tulip · anchor · mellow · crane", "the words as given");
  assert.match(second, /the words must match/);
  assert.equal(last, "Pixel 9 is connected.");
  assert.equal(srcAfter, null, "the picture left the page");
  assert.equal(codeAfter, "", "the code left the page");
  assert.ok(boxHidden && closeShown);
  assert.ok(reads.length >= 2, "the list was read again after connecting");
  assert.ok(!html.includes("jarvis-pair:"), "the QR text is never on the page");
  assert.deepEqual(errors || [], []);
});

await check("a burnt code: the PC's sentence, and where the wrong tries came from", async () => {
  const page = await open({ devices: {
    list: list(), address: { address: "jarvis-pc.tail1234.ts.net", source: "remembered" }, start: START,
    sessions: [{ state: "burnt", expires_in: 0, tries_left: 0, device_name: null, words: null,
                 wrong_tries_from: ["100.88.1.2"],
                 message: "Three wrong tries - this code no longer works. Start again." }],
  } });
  await page.waitForTimeout(400);
  const known = await page.locator("#dv-address-known").innerText();
  await page.locator("#dv-pair").click();
  await page.waitForTimeout(2600);
  const said = await page.locator("#dv-session").innerText();
  const from = await page.locator("#dv-wrong-tries").innerText();
  const code = await page.locator("#dv-code").textContent();
  const sent = await calls(page, "pair_start");
  await page.close();
  assert.match(known, /jarvis-pc\.tail1234\.ts\.net/, "a remembered name is shown, not asked again");
  assert.deepEqual(sent, [{ address: "jarvis-pc.tail1234.ts.net" }]);
  assert.equal(said, "Three wrong tries - this code no longer works. Start again.");
  assert.match(from, /100\.88\.1\.2/);
  assert.equal(code, "");
});

await check("Cancel ends it on the PC and takes the code away", async () => {
  const page = await open({ devices: {
    list: list(), address: { address: "jarvis-pc.tail1234.ts.net", source: "remembered" }, start: START,
  } });
  await page.waitForTimeout(400);
  await page.locator("#dv-pair").click();
  await page.waitForTimeout(300);
  await page.locator("#dv-cancel").click();
  await page.waitForTimeout(300);
  const cancelled = await page.evaluate(() => window.__devices.cancelled);
  const panelHidden = await page.locator("#dv-panel").isHidden();
  const code = await page.locator("#dv-code").textContent();
  const pairOn = await page.locator("#dv-pair").isEnabled();
  await page.close();
  assert.equal(cancelled, 1);
  assert.ok(panelHidden);
  assert.equal(code, "");
  assert.ok(pairOn);
});

await check("no name yet: it is asked for, and a refusal is shown in the PC's words", async () => {
  const refusal = "Pairing only works over Tailscale (a name ending in .ts.net) or NordVPN Meshnet (a name ending in .nord).";
  const page = await open({ devices: { list: list(), startFails: refusal } });
  await page.waitForTimeout(400);
  const fieldShown = await page.locator("#dv-address").isVisible();
  await page.locator("#dv-pair").click();
  await page.waitForTimeout(200);
  const first = await page.locator("#dv-pair-status").innerText();
  const none = await calls(page, "pair_start");
  await page.locator("#dv-address").fill("192.168.1.10");
  await page.locator("#dv-pair").click();
  await page.waitForTimeout(300);
  const second = await page.locator("#dv-pair-status").innerText();
  const panelHidden = await page.locator("#dv-panel").isHidden();
  await page.close();
  assert.ok(fieldShown);
  assert.match(first, /Type the name your phone reaches this PC at first/);
  assert.equal(none.length, 0);
  assert.equal(second, refusal);
  assert.ok(panelHidden);
});

await check("a devices event from the other app re-reads the list", async () => {
  const page = await open({ devices: { list: list() } });
  await page.waitForTimeout(400);
  const before = (await calls(page, "devices_list")).length;
  await page.evaluate(() => window.__emit("jarvis-event", { kind: "devices", id: 9, data: {} }));
  await page.waitForTimeout(300);
  const after = (await calls(page, "devices_list")).length;
  await page.close();
  assert.equal(after, before + 1);
});

await check("a reloaded window with a pairing open shows its state, never its code", async () => {
  const page = await open({ devices: {
    list: list(), openAtLoad: true,
    sessions: [{ state: "waiting_for_phone", expires_in: 400, tries_left: 3, words: null,
                 wrong_tries_from: [], message: "Waiting for your phone..." }],
  } });
  await page.waitForTimeout(600);
  const panel = await page.locator("#dv-panel").isVisible();
  const box = await page.locator("#dv-code-box").isHidden();
  const said = await page.locator("#dv-session").innerText();
  await page.close();
  assert.ok(panel && box);
  assert.match(said, /no longer shown here/);
});

await browser.close();
close();

/* ── CONTROL: the Rust ────────────────────────────────────────────────── */

const RUST = read("src-tauri/src/devices.rs");
const SURFACES = read("src-tauri/permissions/surfaces.toml");

function fnBody(src, name) {
  const at = src.indexOf(`pub async fn ${name}(`);
  assert.ok(at >= 0, `${name} not found`);
  const end = src.indexOf("\n}\n", at);
  return src.slice(at, end);
}

await check("CONTROL: the Devices commands are in the settings window's set only", async () => {
  const sets = SURFACES.split("[[set]]");
  for (const cmd of ["pair-phone-address", "pair-start", "pair-session", "pair-cancel",
    "devices-list", "devices-remove", "devices-shared"]) {
    const holders = sets.filter((s) => s.includes(`"allow-${cmd}"`));
    assert.equal(holders.length, 1, `${cmd} is in ${holders.length} sets`);
    assert.match(holders[0], /identifier = "settings-surface"/, cmd);
  }
});

await check("CONTROL: the window is hidden from capture BEFORE the code is handed over", async () => {
  const start = fnBody(RUST, "pair_start");
  const guard = start.indexOf("guard_capture(&app, true)");
  const answer = start.indexOf('"code": started.code');
  assert.ok(guard > 0 && answer > guard, "guard_capture(true) must come before the answer");
  assert.ok(!/"qr"\s*:/.test(start), "the QR text must never be in the answer");
  assert.match(start, /if stale\(&app\)/, "starting a pairing is held on a stale link");
  assert.match(fnBody(RUST, "pair_cancel"), /guard_capture\(&app, false\)/);
  assert.match(fnBody(RUST, "pair_session"), /guard_capture\(&app, false\)/);
  assert.match(RUST, /set_content_protected\(on\)/);
});

await check("CONTROL: only a loosening waits for a live link", async () => {
  assert.match(fnBody(RUST, "devices_shared"), /if !retired && stale\(&app\)/);
  assert.ok(!/stale/.test(fnBody(RUST, "devices_remove")), "Remove must not wait");
  assert.ok(!/stale/.test(fnBody(RUST, "pair_cancel")), "Cancel must not wait");
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("\nDevices hold");
