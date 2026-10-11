/**
 * "Animal options" - every animal option in one place, shared with the
 * phone where it should be, and Jarvis changing them when asked (the owner's
 * decisions of 2026-09-28).
 *
 * The first part needs no browser (CI runs it with the backend job):
 *  - animal-shared.js's fallback words are the PC's own, word for word
 *    (tests/fixtures/animal-cases.json, written by jarvis_animal.py);
 *  - stepTuning makes the same change as the PC's step_device for every
 *    `face_tuning` value from every starting point in the fixture;
 *  - the sharpness and frame-rate words are face-tuning.js's.
 *
 * With Playwright, Settings' "Animal options" section:
 *  - draws every switch the PC lists, with the "coming in the next update"
 *    line on the behaviours not built yet, and the shared and serious notes;
 *  - sends ONE change per tap; turning one ON waits for a live link, OFF
 *    never does;
 *  - holds the sun, moon and weather and the per-computer sharpness and
 *    frame rate, each labelled with where it is kept, and a way to the
 *    animal's voice;
 * and the Jarvis bar applies "make the animal sharper" (X-Jarvis-Route
 * `face_tuning`) to this computer only, which Settings then shows.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIX = JSON.parse(fs.readFileSync(path.join(HERE, "fixtures", "animal-cases.json"), "utf8"));
const A = await import("../src/animal-shared.js");
const T = await import("../src/face-tuning.js");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

await check("the fallback switches are the PC's, word for word, in its order", () => {
  const pc = FIX.view.switches.map(({ id, label, detail, default: d, built }) => ({ id, label, default: d, built, detail }));
  const here = A.SWITCHES.map(({ id, label, detail, default: d, built }) => ({ id, label, default: d, built, detail }));
  assert.deepEqual(here, pc);
  assert.deepEqual({ ...A.DEFAULTS }, FIX.defaults);
});

await check("the words around them are the PC's", () => {
  for (const k of ["title", "intro", "shared_title", "shared_note", "serious_note", "coming"]) {
    assert.equal(A.WORDS[k], FIX.view[k], k);
  }
  assert.equal(A.WORDS.missing, FIX.missing);
});

await check("the owner's defaults: nods, focus buddy, acks, petting and cute moments on; Still and seasonal off", () => {
  assert.deepEqual({ ...A.DEFAULTS }, { still: false, nods: true, focus_buddy: true, acks: true, petting: true, cute_moments: true, seasonal: false });
});

await check("stepTuning makes the PC's change for every face_tuning value, from every start", () => {
  assert.deepEqual(A.DEVICE_CHANGES, FIX.device_changes);
  for (const c of FIX.steps) {
    const got = A.stepTuning({ ...c.from, speed: 0.5 }, c.change);
    const three = { quality: got.tuning.quality, frameRate: got.tuning.frameRate, autoAdjust: got.tuning.autoAdjust };
    assert.deepEqual(three, c.tuning, `${JSON.stringify(c.from)} + ${c.change}`);
    assert.equal(got.changed, c.changed, `${c.change} changed`);
    assert.equal(got.line, c.line, `${c.change} line`);
    assert.equal(got.tuning.speed, 0.5, "the speed was lost");
  }
  assert.equal(A.stepTuning({}, "sparkles").changed, false, "an unknown change changed something");
});

await check("the sharpness and frame-rate words are face-tuning.js's", () => {
  assert.deepEqual(FIX.view.device.sharpness, T.QUALITIES.map(({ id, label }) => ({ id, label })));
  assert.deepEqual(FIX.view.device.frame_rates, T.FRAME_RATES.map(({ id, label }) => ({ id, label })));
});

await check("Still: the PC's value, and an old 'on' until it has moved", () => {
  const off = { still: false }, on = { still: true };
  assert.equal(A.effectiveStill(null, on, false), true, "an older PC keeps this computer's own");
  assert.equal(A.effectiveStill(null, null, false), false);
  assert.equal(A.effectiveStill(off, on, false), true, "an old 'on' lost before it moved");
  assert.equal(A.effectiveStill(off, on, true), false, "after the move, the PC rules");
  assert.equal(A.effectiveStill(on, off, true), true);
  assert.deepEqual(A.normaliseAnimal({ still: "yes", nods: false, extra: 1 }),
    { ...A.DEFAULTS, nods: false });
});

let K = null;
try { await import("playwright"); K = await import("./uikit.mjs"); } catch { K = null; }
if (!K) {
  console.log("SKIP  the Settings part - Playwright is not installed (npm i -D playwright)");
} else {
  const { base, close } = await K.serve();
  const browser = await K.launch();

  await check("Settings: one Animal options section, every switch the PC lists, in its words", async () => {
    const page = await K.open(browser, base, "settings.html", {}, { width: 820, height: 1400 });
    await page.waitForSelector("#animal-still", { timeout: 15000 });
    const rows = await page.$$eval("#animal-switches [data-animal]", (els) =>
      els.map((e) => ({ id: e.dataset.animal, text: e.textContent, on: e.querySelector("input").checked })));
    const errors = page.__errors;
    const inside = await page.evaluate(() => {
      const sec = document.getElementById("animal-options");
      return {
        sky: sec.contains(document.getElementById("sky")),
        tuning: sec.contains(document.getElementById("face-tuning")),
        voice: !!document.getElementById("animal-voice-go"),
        stillInAppearance: !!document.querySelector("#appearance-card #face-still, #appearance-card [data-animal]"),
        jump: !!document.querySelector('#settings-jump a[href="#animal-options"]'),
        summary: document.querySelector("#face-tuning > summary").textContent,
        tuningOpen: document.getElementById("face-tuning").open,
        shared: document.getElementById("animal-shared-note").textContent,
        serious: document.getElementById("animal-serious-note").textContent,
        sharpLabel: document.getElementById("face-quality-label").textContent,
      };
    });
    await page.close();
    assert.deepEqual(rows.map((r) => r.id), FIX.view.switches.map((s) => s.id));
    for (const r of rows) {
      const sw = FIX.view.switches.find((s) => s.id === r.id);
      assert.ok(r.text.includes(sw.label) && r.text.includes(sw.detail), r.id);
      assert.equal(r.on, sw.on, `${r.id} shows the PC's value`);
      assert.equal(r.text.includes(FIX.view.coming), !sw.built, `${r.id}: the 'coming' line`);
    }
    assert.ok(inside.sky, "the sun, moon and weather are not in the section");
    assert.ok(inside.tuning, "sharpness and frame rate are not in the section");
    assert.ok(inside.voice, "no way to the animal's voice");
    assert.ok(!inside.stillInAppearance, "Still is still in Appearance as well");
    assert.ok(inside.jump, "the jump list does not name the section");
    assert.match(inside.summary, /on this computer/);
    // The current value is readable with the fold CLOSED (2026-10-08): the
    // summary carries it, and a computer that has never been set shows the
    // default (FACE_TUNING_DEFAULT: Auto adjust on) before anything is opened.
    assert.equal(inside.tuningOpen, false,
      "the fold starts open, so the summary was not proved readable while closed");
    assert.match(inside.summary, /Now: Auto adjust is choosing\./);
    assert.equal(inside.sharpLabel, "Sharpness");
    assert.equal(inside.shared, FIX.view.shared_note);
    assert.equal(inside.serious, FIX.view.serious_note);
    assert.deepEqual(errors, []);
  });

  await check("one change per tap; turning one on waits for a live link, turning one off never does", async () => {
    const page = await K.open(browser, base, "settings.html", { link: { stale: true } }, { width: 820, height: 1400 });
    await page.waitForSelector("#animal-seasonal", { timeout: 15000 });
    const stale = await page.evaluate(() => ({
      seasonalOn: document.getElementById("animal-seasonal").disabled,
      nodsOff: document.getElementById("animal-nods").disabled,
    }));
    assert.equal(stale.seasonalOn, true, "turning seasonal ON was allowed on a stale link");
    assert.equal(stale.nodsOff, false, "turning nods OFF was held on a stale link");
    await page.locator("#animal-nods").uncheck();
    await page.waitForFunction(() => /nods/.test(document.getElementById("animal-status").textContent));
    const sent = await page.evaluate(() => window.__calls.filter(([c]) => c === "set_animal").map(([, a]) => a.change));
    const kept = await page.evaluate(() => JSON.parse(localStorage.getItem("jarvis.animal.v1")));
    await page.close();
    assert.deepEqual(sent, [{ nods: false }]);
    assert.equal(kept.nods, false, "the faces' copy was not kept");
  });

  await check("a change on the phone shows here at once (the appearance doorbell)", async () => {
    const page = await K.open(browser, base, "settings.html", {}, { width: 820, height: 1400 });
    await page.waitForSelector("#animal-petting", { timeout: 15000 });
    await page.evaluate(() => {
      window.__animal.values.petting = false;
      for (const s of window.__animal.switches) if (s.id === "petting") s.on = false;
      window.__emit("appearance-changed", null);
    });
    await page.waitForFunction(() => document.getElementById("animal-petting").checked === false, null, { timeout: 5000 });
    await page.close();
  });

  await check("'Go to the face's voice' lands on Jarvis's voice", async () => {
    const page = await K.open(browser, base, "settings.html", {}, { width: 820, height: 900 });
    await page.click("#animal-voice-go");
    await page.waitForTimeout(300);
    const where = await page.evaluate(() => {
      const a = document.activeElement;
      return a && (a.id === "voices" || a.id === "cv-face-switch" || (a.closest && !!a.closest("#voices")));
    });
    await page.close();
    assert.ok(where, "focus did not land in Jarvis's voice");
  });

  await check("'make the animal sharper' in the Jarvis bar changes this computer only, and Settings shows it", async () => {
    const route = (r) => "\u001fjarvis-route:" + JSON.stringify(r);
    const page = await K.open(browser, base, "index.html", {
      chatReplies: [[route({ lane: "no AI model", where: "local", quick: "animal_device", face_tuning: "sharper" }),
        "Done - one step sharper, on this device only."]],
    }, { width: 520, height: 640 });
    await page.locator("#prompt").fill("make the animal sharper");
    await page.locator("#prompt").press("Enter");
    await page.waitForFunction(() => {
      try { return JSON.parse(localStorage.getItem("jarvis.faceTuning")).quality === "max"; } catch { return false; }
    }, null, { timeout: 10000 });
    const saved = await page.evaluate(() => JSON.parse(localStorage.getItem("jarvis.faceTuning")));
    const sentToPc = await page.evaluate(() => window.__calls.filter(([c]) => c === "set_animal").length);
    await page.close();
    assert.equal(saved.autoAdjust, false, "a step picks a value, so Auto adjust goes off");
    assert.equal(sentToPc, 0, "a per-device change went to the PC");

    // Settings, open meanwhile, shows the new pick (another window's save).
    const settings = await K.open(browser, base, "settings.html", {}, { width: 820, height: 1400 });
    await settings.evaluate((v) => {
      // What another window's save looks like to this one.
      localStorage.setItem("jarvis.faceTuning", v);
      window.dispatchEvent(new StorageEvent("storage", { key: "jarvis.faceTuning", newValue: v }));
    }, JSON.stringify(saved));
    await settings.waitForFunction(() =>
      document.querySelector('#face-quality button[data-value="max"]').getAttribute("aria-pressed") === "true",
    null, { timeout: 5000 });
    // ...and the fold's own summary line follows it, still closed (2026-10-08).
    const nowLine = await settings.evaluate(() => ({
      text: document.querySelector("#face-tuning > summary").textContent,
      open: document.getElementById("face-tuning").open,
    }));
    await settings.close();
    assert.equal(nowLine.open, false, "the fold was opened to read the value");
    assert.match(nowLine.text, /Now: Maximum, frame rate Auto\./);

    const odd = await K.open(browser, base, "index.html", {
      chatReplies: [[route({ lane: "x", where: "local", face_tuning: "rm -rf" }), "x"]],
      storage: { "jarvis.faceTuning": JSON.stringify({ quality: "low", frameRate: "30", autoAdjust: false, speed: 1 }) },
    }, { width: 520, height: 640 });
    await odd.locator("#prompt").fill("hi");
    await odd.locator("#prompt").press("Enter");
    await odd.waitForTimeout(800);
    const same = await odd.evaluate(() => JSON.parse(localStorage.getItem("jarvis.faceTuning")));
    await odd.close();
    assert.equal(same.quality, "low", "an unknown face_tuning changed something");
  });

  await browser.close();
  close();
}

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nall animal-settings checks passed");
process.exit(fails.length ? 1 : 0);
