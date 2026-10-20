/**
 * The quickbar opens compact (owner, 2026-10-19: "the jarvis bar is huge now, i
 * want it back to its compact size").
 *
 * What happened: the primer ("What you can do here / Things you can say") was
 * the empty state shown on every summon. Its served sayable list is ~11 rows,
 * so the bar grew to 577 px instead of its 80 px input row. It is useful help;
 * it is not what the bar should be every time it opens.
 *
 * These checks are structural and behavioural, like bar-chrome.mjs, and for the
 * same reason: there is no browser in CI. They pin the facts that make the
 * compact default real and announce it correctly:
 *   1. the primer starts hidden in the markup;
 *   2. a visible control opens it, and that control is a disclosure: it carries
 *      aria-expanded, never aria-pressed, and its state is the panel's actual
 *      visibility - a card or busy surface that hides the panel also makes the
 *      button say "collapsed", even while primerOpen is still true (the
 *      standing feature audit flagged the old aria-pressed for this);
 *   3. main.js's one visibility function keeps it closed unless the owner
 *      opened it, and every summon resets that.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const read = (p) => readFileSync(p, "utf8");

const indexHtml = read(join(SRC, "index.html"));
const mainJs = read(join(SRC, "main.js"));
const styleCss = read(join(SRC, "style.css"));

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** The text of one function or listener block, by marker. */
function blockFor(source, marker, span = 900) {
  const at = source.indexOf(marker);
  assert.notEqual(at, -1, `${marker} is not in the file`);
  return source.slice(at, at + span);
}

/** The whole source of one named function, closing brace included. */
function functionSource(source, name) {
  const opening = source.match(new RegExp(`function\\s+${name}\\s*\\([^)]*\\)\\s*\\{`));
  assert.ok(opening, `main.js has no function ${name}`);
  const start = opening.index;
  let depth = 0;
  for (let i = start; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    else if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error(`${name} never closes`);
}

/** One `<button>` element, so `aria-pressed` on a neighbour cannot satisfy it. */
function elementFor(html, id) {
  const at = html.indexOf(`id="${id}"`);
  assert.notEqual(at, -1, `#${id} is not in index.html`);
  const start = html.lastIndexOf("<button", at);
  assert.notEqual(start, -1, `#${id} is not a <button>`);
  const end = html.indexOf("</button>", at);
  assert.notEqual(end, -1, `#${id} never closes`);
  return html.slice(start, end + "</button>".length);
}

/** The block that starts with `starter` after `marker`, braces balanced. */
function blockStartingAt(source, marker, starter) {
  const markerAt = source.indexOf(marker);
  assert.notEqual(markerAt, -1, `${marker} is not in the file`);
  const start = source.indexOf(starter, markerAt);
  assert.notEqual(start, -1, `${starter} is not after "${marker}"`);
  let depth = 0;
  for (let i = start; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    else if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error(`${starter} never closes`);
}

check("the primer starts hidden in the markup", () => {
  assert.match(indexHtml, /<section class="primer" id="primer"[^>]*\bhidden\b/,
    "the primer must start hidden, or the bar opens huge on every summon");
});

check("the bar has a named, disclosure-style door to the primer", () => {
  const button = elementFor(indexHtml, "sayable-toggle");
  assert.match(button, /aria-expanded="false"/,
    "the button must start collapsed, because the bar starts compact");
  assert.doesNotMatch(button, /aria-pressed/,
    "a disclosure button must not carry aria-pressed");
  assert.match(button, /aria-controls="primer"/,
    "the button must say which panel it controls");
  assert.match(button, /title="What can I say\?"/,
    "the button's tooltip must keep its visible name");
  assert.match(button, /<span class="sr-only">What can I say\?<\/span>/,
    "the ? button needs a name for a screen reader");
});

check("syncPrimer computes the final visibility once and reports it", () => {
  const block = functionSource(mainJs, "syncPrimer");
  assert.match(block, /const hidden = busy \|\| !primerOpen;/,
    "syncPrimer must combine its busy check with the owner's primerOpen flag once");
  assert.match(block, /dom\.primer\.hidden = hidden;/,
    "the primer's hidden property must be that one computed state");
  assert.match(block, /dom\.sayableToggle\.setAttribute\("aria-expanded", String\(!hidden\)\);/,
    "aria-expanded must follow the computed visibility, not primerOpen alone");
  assert.doesNotMatch(block, /aria-pressed/,
    "the ? button is a disclosure: it must not set aria-pressed");
});

/** A dom stub just wide enough for syncPrimer, with one optional busy surface. */
function primerDom(busySurface) {
  const attrs = {};
  return {
    attrs,
    card: { hidden: busySurface !== "card" },
    attention: { hidden: busySurface !== "attention" },
    approval: { hidden: busySurface !== "approval" },
    parked: { hidden: busySurface !== "parked" },
    attachments: { hidden: busySurface !== "attachments" },
    primer: { hidden: null },
    sayableToggle: { setAttribute(name, value) { attrs[name] = value; } },
  };
}

/** Runs the real syncPrimer, lifted from main.js, against that stub. */
function runSyncPrimer(primerOpen, busySurface = null) {
  const dom = primerDom(busySurface);
  new Function("dom", "primerOpen", `${functionSource(mainJs, "syncPrimer")}
return syncPrimer();`)(dom, primerOpen);
  return dom;
}

check("syncPrimer announces the visibility a screen reader actually gets", () => {
  const closed = runSyncPrimer(false);
  assert.equal(closed.primer.hidden, true, "an unopened primer must be hidden");
  assert.equal(closed.attrs["aria-expanded"], "false",
    "an unopened primer must announce itself collapsed");

  const opened = runSyncPrimer(true);
  assert.equal(opened.primer.hidden, false, "an opened primer must be visible");
  assert.equal(opened.attrs["aria-expanded"], "true",
    "a visible primer must announce itself expanded");

  for (const surface of ["card", "attention", "approval", "parked", "attachments"]) {
    const busied = runSyncPrimer(true, surface);
    assert.equal(busied.primer.hidden, true,
      `a visible ${surface} must keep the primer hidden`);
    assert.equal(busied.attrs["aria-expanded"], "false",
      `a visible ${surface} must announce the primer collapsed even though primerOpen is true`);
  }

  for (const dom of [closed, opened]) {
    assert.ok(!("aria-pressed" in dom.attrs),
      "syncPrimer must never set aria-pressed on the disclosure button");
  }
});

check("the ? button toggles the primer and resizes the bar", () => {
  const block = blockFor(mainJs, '// "What can I say?" - the door to the "Things you can say" primer.');
  assert.match(block, /addEventListener\("click"/,
    "the ? button must have a click handler");
  assert.match(block, /primerOpen = !primerOpen;/,
    "the handler must toggle primerOpen");
  assert.match(block, /syncWindowHeight\(\)/,
    "the bar must re-measure after the panel opens or closes");
  assert.match(functionSource(mainJs, "syncWindowHeight"), /syncPrimer\(\);/,
    "the click's resize path must run syncPrimer, or the announced state goes stale");
});

check("the extracted click handler really toggles and re-measures", () => {
  const handlerSource = blockStartingAt(
    mainJs,
    '// "What can I say?" - the door to the "Things you can say" primer.',
    "if (dom.sayableToggle)",
  );
  let registered = null;
  let resizes = 0;
  const dom = {
    sayableToggle: {
      addEventListener(type, handler) {
        assert.equal(type, "click", "the ? button must listen for clicks");
        registered = handler;
      },
    },
  };
  const state = new Function(
    "dom",
    "syncWindowHeight",
    "primerOpen",
    `${handlerSource}
return { open: () => primerOpen };`,
  )(dom, () => { resizes += 1; }, false);

  assert.equal(typeof registered, "function", "the ? button never registered a click handler");
  registered();
  assert.equal(state.open(), true, "the first click must open the primer");
  registered();
  assert.equal(state.open(), false, "the second click must close it again");
  assert.equal(resizes, 2, "each click must re-measure the bar through syncWindowHeight");
});

check("every summon starts compact", () => {
  const block = blockFor(mainJs, 'listen("focus-input"');
  assert.match(block, /primerOpen = false;/,
    "a new summon must reset the panel, not inherit the last one");
});

check("the ? mark has its own small style", () => {
  assert.match(styleCss, /\.sayable-mark\s*\{[^}]*font-size:\s*13px;/s,
    "the ? needs the compact toolbar size");
});

if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nall passed");
