/**
 * Q13 (2026-11-09): the first fixes in the Brain window and Settings for the
 * same problems the HUD redesign fixes.
 *
 *   node tests/brain-settings-q13.mjs
 *
 * WHAT IS PROVEN, and why each half exists:
 *
 *   1. One authoritative control surface (Q13.1). Switches stay in Settings and
 *      records/receipts stay in the Brain - EXCEPT Brain -> Model, which keeps
 *      model switching and preset changes beside the "Loaded now / Resources"
 *      and "Measured results" cards. The source half pins the structure; the
 *      DOM half opens the real page and proves the Model pane really shows both
 *      switching controls and both record cards at once (a source pin alone
 *      would pass on a read-only pane).
 *   2. Plain-words empty states (Q13.2). No raw "—" in Brain -> Memory or
 *      Brain -> Model: a zero count says "0", an unread card says why in words,
 *      and the memory map's empty stat says "0 names".
 *   3. One chosen convention (Q13.3). The chosen row wears the `.is-chosen`
 *      rectangle - the HUD's own class - plus `aria-current="true"`, in BOTH
 *      windows; no "(current)" or "Applied" suffix is ever printed. The rule
 *      lives in brain.css / settings.css, in the page's own stylesheet, never
 *      built at run time: the packaged CSP refuses a run-time <style>
 *      (tests/csp.mjs). The DOM half proves the rectangle really paints.
 *
 * WHAT THIS SLICE DOES NOT OWN: the HUD's own visible "(current)"/"Applied"
 * wording lives in hud-presets.js and hud-edit.js, and the HUD's chips are
 * rebuilt by the wave15-presets slice. This suite pins the class and its
 * stylesheet rule - the contract all three windows share - and leaves the HUD
 * copy to the lane that owns it; it must not go red for that lane's work.
 *
 * The DOM half needs Playwright (the harness in tests/uikit.mjs explains why it
 * is not an app dependency). Without it the checks are skipped LOUDLY - a
 * skipped check is never a pass here.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

let passed = 0;
const fails = [];
const check = async (name, fn) => {
  try {
    await fn();
    passed += 1;
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

const brain = read("src/brain.js");
const settings = read("src/settings.js");
const brainCss = read("src/brain.css");
const settingsCss = read("src/settings.css");
const brainHtml = read("src/brain.html");
const hud = read("src/jarvis_hud.html");

/** The body of `function NAME(` up to the next top-level `\n}`. */
function functionBody(source, name) {
  const start = source.indexOf(`function ${name}(`);
  assert.ok(start >= 0, `no function ${name} in the source`);
  const end = source.indexOf("\n}", start);
  assert.ok(end > start, `function ${name} is never closed`);
  return source.slice(start, end);
}

/** The declarations of one CSS rule, normalised: `["border-color:...", ...]`. */
function declarations(rule) {
  return [...rule.matchAll(/([a-z-]+)\s*:\s*([^;]+)/g)]
    .map(([, key, value]) => `${key}:${value.trim().replace(/\s+/g, " ")}`)
    .sort();
}

/** The body of the FIRST `selector { ... }` rule in a stylesheet. The exact
 *  selector is matched (so `.chosen:hover` can never be read as `.chosen`). */
function ruleBody(source, selector) {
  const at = source.includes(`${selector}{`)
    ? source.indexOf(`${selector}{`)
    : source.indexOf(`${selector} {`);
  assert.ok(at >= 0, `no ${selector} rule in the source`);
  const open = source.indexOf("{", at);
  const close = source.indexOf("}", open);
  assert.ok(close > open, `the ${selector} rule is never closed`);
  return source.slice(open + 1, close);
}

/** Running code only: comment lines dropped, so a comment that NAMES the old
 *  suffix is not mistaken for the window still printing it. */
function codeLines(source) {
  return source.split("\n")
    .filter((line) => !/^\s*(\*|\/\*|\/\/)/.test(line))
    .join("\n");
}

/** A line that is nothing but the raw em dash - the empty state Q13 forbids.
 *  An em dash inside a sentence is ordinary prose and stays. */
function hasRawDash(text) {
  return text.split("\n").some((line) => line.trim() === "\u2014");
}

/* ── 1. One chosen convention across the three windows ──────────────────── */

/** The rule the desktop windows carry, exactly as it appears in the page's
 *  own stylesheet. The HUD's version names its accent `--ice`, so the DOM
 *  comparison below resolves that alias before the two are compared. */
const CHOSEN_DECLARATIONS = [
  "background:rgb(var(--accent-rgb) / .10)",
  "border-color:var(--accent)",
  "color:var(--accent)",
].sort();

await check("Brain and Settings carry the SAME chosen rectangle, under one class, in their stylesheets", () => {
  for (const [name, css] of [["brain.css", brainCss], ["settings.css", settingsCss]]) {
    assert.deepEqual(declarations(ruleBody(css, ".is-chosen")), CHOSEN_DECLARATIONS,
      `${name} does not carry the shared .is-chosen rule (or someone edited one copy)`);
  }
});

await check("that rectangle is the HUD's own .hud-presets-item.is-chosen rule", () => {
  assert.match(hud, /--ice:var\(--accent\);/, "the HUD's --ice is no longer the accent");
  const hudRule = declarations(ruleBody(hud, ".hud-presets-item.is-chosen"))
    .map((d) => d.replaceAll("var(--ice)", "var(--accent)"));
  // `--ice` is the HUD's name for the accent (jarvis_hud.html). Resolve it and
  // the HUD's rule is the same three declarations as the one both windows
  // carry - so "the same highlighted rectangle" is literal, not a lookalike.
  assert.deepEqual(hudRule, CHOSEN_DECLARATIONS,
    "the HUD's chosen rectangle and the desktop windows' copy have drifted apart");
});

await check("the row, chip and theme rules are the one shared shape", () => {
  const row = declarations(ruleBody(brainCss, ".row-item.is-chosen"));
  assert.ok(row.includes("border:1px solid var(--accent)"), "the chosen row has no accent border");
  assert.ok(row.includes("border-radius:8px") && row.includes("padding:8px 10px"),
    "the chosen row is not the rectangle the model row needs (a row is only a top hairline otherwise)");
  const chip = declarations(ruleBody(brainCss, ".preset-chip.is-chosen"));
  assert.ok(chip.includes("border-color:var(--accent)") && chip.includes("background:rgb(var(--accent-rgb) / .10)"),
    "a chosen Galaxy preset chip is not painted with the shared rectangle");
  const theme = declarations(ruleBody(settingsCss, "#theme-list .theme-row.is-chosen"));
  assert.ok(theme.includes("border-color:var(--accent)") && theme.includes("background:rgb(var(--accent-rgb) / .10)"),
    "the chosen theme row is not painted with the shared rectangle");
});

await check("neither window builds a stylesheet at run time (the packaged CSP refuses one)", () => {
  const CSP_BAD = /createElement\(\s*["'`]style["'`]\s*\)|setAttribute\(\s*["'`]style["'`]/;
  for (const [name, source] of [["brain.js", brain], ["settings.js", settings]]) {
    assert.doesNotMatch(codeLines(source), CSP_BAD,
      `${name} builds a run-time <style>; put the rule in the page's stylesheet (tests/csp.mjs)`);
  }
});

await check("the chosen row says aria-current, never a suffix on its label", () => {
  const row = functionBody(brain, "row");
  assert.match(row, /item\.classList\.add\("is-chosen"\)/, "row() does not add the class");
  assert.match(row, /item\.setAttribute\("aria-current", "true"\)/,
    "row() does not say aria-current");
  assert.doesNotMatch(codeLines(brain), /" \(current\)"|"\(current\)"/,
    "brain.js still prints a (current) suffix");
  assert.doesNotMatch(codeLines(settings), /" \(current\)"|"\(current\)"/,
    "settings.js still prints a (current) suffix");
  // "Applied" as a CHOSEN-item label is what Q13 forbids. (settings.js does
  // say "Applied, but not proven." about an update - a verdict sentence, not a
  // selection - so only the selection renderers are checked for the word.)
  assert.doesNotMatch(codeLines(functionBody(brain, "renderModels")), /"Applied"/,
    "the Models card still labels its chosen row Applied");
  assert.doesNotMatch(codeLines(functionBody(settings, "paintThemeRows")), /"Applied"/,
    "the theme rows still label the chosen one Applied");
});

/* ── 2. Brain -> Model: switching beside the two record cards ───────────── */

await check("Brain -> Model is the pane that holds the two record cards AND the switches", () => {
  // The cards, in the order the owner reads them: Models (the switching card),
  // then Loaded now / Resources, then Measured results.
  const models = brainHtml.indexOf('id="models-card"');
  const resources = brainHtml.indexOf('id="resources-card"');
  const measured = brainHtml.indexOf('id="measured-card"');
  assert.ok(models > 0 && resources > models && measured > resources,
    "the Model pane no longer holds Models, Loaded now / Resources and Measured results in order");

  const render = functionBody(brain, "renderModels");
  assert.match(render, /modelAction\("switch", ref\)/,
    "the Models card has lost its model switching");
  assert.match(render, /dom\.models\.append\(advisorPanel\(\)\)/,
    "the Models card no longer carries the panel that asks for preset changes");
  assert.match(functionBody(brain, "advisorPresetBlock"), /Approve changes to /,
    "the preset block has no way to approve a preset change");
  assert.match(functionBody(brain, "approvePresetChanges"), /applyPreset\(preset\)/,
    "the preset approval no longer goes through the carded applyPreset");
});

await check("the current model row is the one chosen row, with the class and one word", () => {
  const render = functionBody(brain, "renderModels");
  assert.match(render, /chosen: showAsLiveCurrent/, "the current model row is not marked chosen");
  assert.match(render, /tag: showAsLiveCurrent \? "current" : "installed"/,
    'the current model row does not say "current" (it used to say "active")');
  assert.doesNotMatch(render, /"active"/, "the model row still says active");
});

/* ── 3. Plain-words empty states in Brain -> Memory and Brain -> Model ──── */

await check("no raw em dash survives in the Memory or Model renderers", () => {
  for (const name of ["renderModels", "renderResources", "renderMeasured", "renderCompute",
                      "renderMemory", "renderLearning", "renderProposals", "renderFacts"]) {
    const body = functionBody(brain, name);
    // `"\u2014"` - a literal that IS the empty state. Prose em dashes inside a
    // sentence are ordinary English and are not what Q13 forbids.
    assert.ok(!body.includes('"\u2014"'), `${name} still prints a raw em dash as an empty state`);
  }
  assert.match(functionBody(brain, "graphEmptyWith"), /graphStat\.textContent = "0 names"/,
    "an empty memory map still prints a raw em dash instead of 0 names");
  assert.ok(brain.includes("0 names"), "the memory map has no plain-words zero count");
});

/* ── 4. Settings: the chosen theme is the shared rectangle ──────────────── */

await check("Settings paints the chosen theme row with the shared class and aria-current", () => {
  const paint = functionBody(settings, "paintThemeRows");
  assert.match(paint, /row\.classList\.toggle\("is-chosen", picked\)/,
    "the chosen theme row never gets the .is-chosen class");
  assert.match(paint, /row\.setAttribute\("aria-current", "true"\)/,
    "the chosen theme row does not say aria-current");
  // The tick stays: it is the non-colour sign the colour-alone audit asked for.
  assert.match(functionBody(settings, "buildThemeRows"), /check\.textContent = "✓"/,
    "the chosen row's non-colour sign (the tick) was removed");
});

/* ── 5. The DOM, when a browser is available ───────────────────────────── */

let playwright = null;
try {
  playwright = await import("playwright");
} catch {
  playwright = null;
}

if (playwright) {
  const K = await import("./uikit.mjs");
  const { base, close } = await K.serve();
  const browser = await K.launch();
  const SIZE = { width: 1180, height: 900 };

  /** The PC's last recommendation answer: no newer model, one preset change. */
  const RECOMMENDED = {
    available: true,
    checked_at: Math.floor(Date.now() / 1000) - 600,
    gpus: [],
    candidates: [],
    recommendations: [{ preset: "Fastest answers", changes: [], evidence: "" }],
    benchmarked: false,
  };

  const EMPTY_MODEL = {
    ...K.BRAIN,
    models: {
      available: true,
      current: "qwen3:8b",
      previous: "",
      installed: [
        { ref: "qwen3:8b", size: 5_100_000_000, family: "qwen3" },
        { ref: "llama3.1:8b", size: 4_900_000_000, family: "llama" },
      ],
    },
    model_recommendations: RECOMMENDED,
    model_resources: { available: false, why: "This PC has not said what is loaded right now." },
    model_measured: { available: false, why: "No benchmark has been stored on this PC yet." },
    memory: { ...K.BRAIN.memory, current: 0, retired: 0 },
  };

  const EMPTY_MEMORY = {
    ...EMPTY_MODEL,
    memory_facts: { available: true, learning: false, pending: 0, facts: [] },
    memory_pending: { available: true, setup: {}, pending: [] },
  };

  await check("Brain -> Model, on the real page: both record cards and both switches together", async () => {
    const page = await K.open(browser, base, "brain.html", { brain: EMPTY_MODEL }, SIZE);
    await page.locator("#tab-faculties").click();
    await page.waitForSelector("#models .row-item");
    await page.waitForSelector("#model-advisor");

    const cards = await page.evaluate(() => {
      const ids = ["models-card", "resources-card", "measured-card"];
      const nodes = ids.map((id) => document.getElementById(id));
      return {
        shown: nodes.map((n) => Boolean(n && n.offsetParent)),
        samePane: nodes.every((n) => n && n.parentElement === nodes[0].parentElement),
        order: nodes.every((n, i) => i === 0
          || (nodes[i - 1].compareDocumentPosition(n) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0),
      };
    });
    assert.deepEqual(cards.shown, [true, true, true],
      "one of the three Model cards is not on screen");
    assert.equal(cards.samePane, true, "the three cards are no longer in one pane");
    assert.equal(cards.order, true, "the two record cards no longer follow the Models card");

    // Model switching: a "Use" on the model that is not running.
    const use = await page.locator("#models .row-item .row-actions button").allTextContents();
    assert.ok(use.some((t) => t.trim() === "Use"), `no model switch ("Use") in the Models card: ${use}`);

    // Preset switching: the carded approval of a recommended preset.
    const approve = await page.locator("#model-advisor button").allTextContents();
    assert.ok(approve.some((t) => /^Approve changes to Fastest answers$/.test(t.trim())),
      `no preset-change door in the Models card: ${approve}`);

    // The record cards are read-only and honest when they have nothing.
    const resources = await page.locator("#resources").innerText();
    const measured = await page.locator("#measured").innerText();
    const modelPane = await page.locator("#models").innerText();
    for (const [where, text] of [["#resources", resources], ["#measured", measured], ["#models", modelPane]]) {
      assert.ok(!hasRawDash(text), `${where} still prints a raw em dash: ${text}`);
    }
    assert.match(resources, /This PC has not said what is loaded right now\./);
    assert.match(measured, /No benchmark has been stored on this PC yet\./);

    await page.close();
  });

  await check("Brain -> Model, on the real page: one chosen row, the class, the word and the paint", async () => {
    const page = await K.open(browser, base, "brain.html", { brain: EMPTY_MODEL }, SIZE);
    await page.locator("#tab-faculties").click();
    await page.waitForSelector("#models .row-item.is-chosen");
    const chosen = page.locator("#models .row-item.is-chosen");
    assert.equal(await chosen.count(), 1, "more than one model row claims to be chosen");
    assert.equal(await chosen.getAttribute("aria-current"), "true",
      "the chosen model row does not say aria-current");
    assert.equal((await chosen.locator(".row-tag").textContent()).trim(), "current",
      "the chosen model row does not say the one word 'current'");
    const visible = await page.locator("#models-card").innerText();
    assert.doesNotMatch(visible, /\(current\)|Applied/,
      "the Models card prints a (current)/Applied suffix instead of the rectangle");
    // The class is not enough: the stylesheet must really paint the rectangle
    // (Q13.3 asks for a highlighted selection, not a name in the DOM).
    const paint = await page.evaluate(() => {
      const rows = [...document.querySelectorAll("#models .row-item")];
      const on = rows.find((r) => r.classList.contains("is-chosen"));
      const off = rows.find((r) => !r.classList.contains("is-chosen"));
      const style = (row) => {
        const s = getComputedStyle(row);
        return { border: s.borderTopColor, background: s.backgroundColor };
      };
      return { on: style(on), off: style(off) };
    });
    assert.notEqual(paint.on.border, paint.off.border,
      `the chosen model row is not drawn with the accent border (${paint.on.border} vs ${paint.off.border})`);
    assert.notEqual(paint.on.background, paint.off.background,
      "the chosen model row has no chosen background");
    assert.deepEqual(page.__errors, [], "the Brain page logged an error");
    await page.close();
  });

  await check("Brain -> Model, on the real page: its Memory card counts zero in words, not a raw em dash", async () => {
    const page = await K.open(browser, base, "brain.html", { brain: EMPTY_MODEL }, SIZE);
    await page.locator("#tab-faculties").click();
    await page.waitForSelector("#memory .kv");
    const memory = await page.locator("#memory").innerText();
    assert.match(memory, /Facts in use\s+0/, `a zero count does not say 0: ${memory}`);
    assert.match(memory, /No longer used\s+0/, `a zero count does not say 0: ${memory}`);
    assert.ok(!hasRawDash(memory), `the Memory card still prints a raw em dash: ${memory}`);
    assert.deepEqual(page.__errors, [], "the Brain page logged an error");
    await page.close();
  });

  await check("Brain -> Memory, on the real page: learning's state and its zero count, no raw em dash", async () => {
    const page = await K.open(browser, base, "brain.html", { brain: EMPTY_MEMORY }, SIZE);
    // The Memory view is the Brain's default; wait for the card to be painted.
    await page.waitForSelector("#memory-learning .kv");
    const learning = await page.locator("#memory-learning").innerText();
    assert.match(learning, /Background learning\s+off/, `the learning state is not in words: ${learning}`);
    assert.match(learning, /Waiting\s+0/, `a zero waiting count does not say 0: ${learning}`);
    const memoryTab = await page.locator("#view-memory").innerText();
    assert.ok(!hasRawDash(memoryTab), `the Memory view still prints a raw em dash: ${memoryTab}`);
    assert.deepEqual(page.__errors, [], "the Brain page logged an error");
    await page.close();
  });

  await check("the memory map's empty stat says 0 names, not a raw em dash", async () => {
    const page = await K.open(browser, base, "brain.html", {
      brain: {
        ...K.BRAIN,
        memory_entities: { available: false, read: "failed", error: "the people list could not be read" },
      },
    }, SIZE);
    await page.locator("#rail-advanced-toggle").click();
    await page.locator("#tab-galaxy").click();
    await page.waitForFunction(() => document.querySelector("#graph-stat")?.textContent === "0 names",
      null, { timeout: 6000 });
    assert.equal(await page.locator("#graph-stat").textContent(), "0 names");
    assert.deepEqual(page.__errors, [], "the Brain page logged an error");
    await page.close();
  });

  await check("Brain -> Galaxy: one chosen preset chip, and choosing another moves the rectangle", async () => {
    const page = await K.open(browser, base, "brain.html", { brain: K.BRAIN }, { width: 1400, height: 1000 });
    await page.locator("#rail-advanced-toggle").click();
    await page.locator("#tab-galaxy").click();
    await page.waitForSelector("#graph-presets .preset-chip.is-chosen");
    const readChips = () => page.evaluate(() => [...document.querySelectorAll("#graph-presets .preset-chip")]
      .map((c) => ({
        preset: c.dataset.preset,
        chosen: c.classList.contains("is-chosen"),
        pressed: c.getAttribute("aria-pressed"),
        border: getComputedStyle(c).borderTopColor,
      })));
    const before = await readChips();
    const chosenBefore = before.filter((c) => c.chosen);
    assert.equal(chosenBefore.length, 1, "more than one Galaxy preset chip is chosen");
    assert.equal(chosenBefore[0].pressed, "true", "the chosen chip does not say aria-pressed");
    assert.ok(before.filter((c) => !c.chosen).every((c) => c.pressed === "false"),
      "an unchosen chip still claims aria-pressed");
    assert.notEqual(chosenBefore[0].border, before.find((c) => !c.chosen).border,
      "the chosen chip is not painted with the shared rectangle");

    await page.locator('#graph-presets .preset-chip[data-preset="planetary-orbit"]').click();
    await page.waitForFunction(() => document.querySelector("#graph-presets .preset-chip.is-chosen")
      ?.dataset.preset === "planetary-orbit", null, { timeout: 6000 });
    const after = await readChips();
    const chosenAfter = after.filter((c) => c.chosen);
    assert.equal(chosenAfter.length, 1, "choosing a layout left more than one chip chosen");
    assert.equal(chosenAfter[0].preset, "planetary-orbit");
    assert.equal(chosenAfter[0].pressed, "true");
    assert.deepEqual(page.__errors, [], "the Brain page logged an error");
    await page.close();
  });

  await check("Settings, on the real page: the chosen theme is the shared rectangle", async () => {
    const page = await K.open(browser, base, "settings.html", {}, { width: 760, height: 1400 });
    await page.waitForSelector("#theme-list .theme-row.is-chosen");
    const chosen = page.locator("#theme-list .theme-row.is-chosen");
    assert.equal(await chosen.count(), 1, "more than one theme row claims to be chosen");
    assert.equal(await chosen.getAttribute("data-choice"), "deep-space",
      "the chosen row is not the theme the PC reported");
    assert.equal(await chosen.getAttribute("aria-current"), "true",
      "the chosen theme row does not say aria-current");
    const others = await page.evaluate(() => [...document.querySelectorAll("#theme-list .theme-row:not(.is-chosen)")]
      .map((row) => row.getAttribute("aria-current")));
    assert.deepEqual(others, others.map(() => null), "an unchosen theme row claims to be current");
    // The tick stays visible: the state is not carried by colour alone.
    assert.equal(await page.locator("#theme-list .theme-row.is-chosen .theme-check").isVisible(), true,
      "the chosen row's non-colour sign (the tick) is gone");
    // And the rectangle really paints: the chosen row's border differs from a
    // row that is not chosen (a class that changed nothing would fail here).
    const colours = await page.evaluate(() => [...document.querySelectorAll("#theme-list .theme-row")]
      .map((row) => [row.dataset.choice, getComputedStyle(row).borderTopColor]));
    const on = colours.find(([id]) => id === "deep-space")[1];
    const off = colours.find(([id]) => id === "paper")[1];
    assert.notEqual(on, off, `the chosen row is not drawn differently (${on} vs ${off})`);
    const text = await page.locator("#theme-list").innerText();
    assert.doesNotMatch(text, /\(current\)|Applied/, "the theme list prints a suffix instead of the rectangle");
    assert.deepEqual(page.__errors, [], "the Settings page logged an error");
    await page.close();
  });

  await browser.close();
  close();
} else {
  // A skipped check is never a pass: say so, and count it, rather than letting
  // the green summary below stand for work this machine could not do.
  console.log("\nSKIP  the DOM checks - Playwright is not installed on this machine");
  console.log("      (they are NOT a pass here; CI installs Playwright and runs them)");
}

if (fails.length) {
  console.log(`\n${passed} passed, ${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
if (!playwright) {
  console.log(`\n${passed} passed, 0 failed, the DOM half SKIPPED (a skip is not a pass)`);
  console.log("Q13: the source checks hold; the DOM half did NOT run on this machine");
} else {
  console.log(`\n${passed} passed, 0 failed`);
  console.log("Q13: the chosen rectangle, the plain-words empty states, and the Model pane's own switches all hold");
}
