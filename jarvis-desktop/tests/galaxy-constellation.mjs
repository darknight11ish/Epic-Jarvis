/**
 * The Galaxy's constellation: one real button per name.
 *
 *     node tests/galaxy-constellation.mjs
 *
 * No browser. This half is pure by design - it builds elements from a
 * description and never reads the page - so everything below is checked with a
 * small stand-in for the DOM, the same way `tests/heavy-approve.mjs` stands in
 * for a scroll container.
 *
 * The decisive check is `tests/galaxy-button-engine.mjs`, which drives the real
 * thing in real Chromium. This file is what makes a failure there quick to
 * localise: if the tree is wrong, nothing downstream can save it.
 *
 * WHAT THIS HOLDS:
 *  - a NAME is a real HTML `<button>`, not a drawn dot, and its drawing is a
 *    separate SVG shape - the pairing that makes the dot reachable AND themed;
 *  - the button announces the name first, then its kind, then how much is known;
 *  - the five hues and two forms are unchanged, and a ring is stroked INSIDE its
 *    radius so a ring and a disc of the same group read as the same size;
 *  - labels follow the canvas's own rules (focused and neighbours first, none
 *    below the zoom threshold, the best-connected otherwise);
 *  - a hidden group draws nothing, is not focusable and is not announced;
 *  - and each coordinate goes into the syntax its own medium wants: SVG for the
 *    drawing, CSS for the button.
 */
import assert from "node:assert/strict";
import {
  LABELLED_NAMES,
  LABEL_MAX,
  LABEL_MIN_SCALE,
  buttonLabel,
  buildConstellation,
  cssTransform,
  labelFor,
  labelledNodes,
  paintConstellation,
  shapeFor,
  svgTransform,
} from "../src/galaxy-constellation.js";

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.stack || e.message}`); }
};

/* ── A minimal DOM, enough for this module ──────────────────────────────── */

function makeDoc() {
  const doc = { createElementNS: null, createElement: null };
  const node = (ns, tag) => {
    const attrs = new Map();
    const children = [];
    const el = {
      ns, tag, children, ownerDocument: doc, style: {}, hidden: false, textContent: "",
      get firstChild() { return children[0] ?? null; },
      get childNodes() { return children; },
      append(...kids) { for (const k of kids) { k.parent = el; children.push(k); } },
      removeChild(k) { const i = children.indexOf(k); if (i >= 0) children.splice(i, 1); return k; },
      setAttribute(k, v) { attrs.set(k, String(v)); },
      getAttribute(k) { return attrs.has(k) ? attrs.get(k) : null; },
      removeAttribute(k) { attrs.delete(k); },
      hasAttribute(k) { return attrs.has(k); },
      attributes: () => Object.fromEntries(attrs),
      classList: {
        _c: new Set(),
        toggle(c, on) { if (on === undefined) { this._c.has(c) ? this._c.delete(c) : this._c.add(c); } else if (on) this._c.add(c); else this._c.delete(c); },
        contains(c) { return this._c.has(c); },
      },
    };
    return el;
  };
  doc.createElementNS = (ns, tag) => node(ns, tag);
  doc.createElement = (tag) => node("http://www.w3.org/1999/xhtml", tag);
  return doc;
}

/** Every element under `el`, depth first. */
function walk(el, out = []) {
  out.push(el);
  for (const c of el.children ?? []) walk(c, out);
  return out;
}

function node(id, label, group, weight, rank) {
  return { id, label, group, weight, rank, deg: 1 };
}

/** The model `brain.js` passes: world point -> screen point, plus the words. */
function model(nodes, links, opts = {}) {
  const hidden = opts.hidden ?? (() => false);
  const focus = opts.focus ?? null;
  const selected = opts.selected ?? null;
  const near = new Set(opts.near ?? []);
  const toScreen = (n) => ({ x: n.x * 2, y: n.y * 2 });
  return {
    nodes, links, hidden, focus, selected, near,
    labels: opts.labels ?? [],
    describe: (n) => {
      const p = toScreen(n);
      return {
        x: p.x, y: p.y,
        colour: "var(--node-h1)",
        shape: shapeFor(3 + Math.min(9, Math.sqrt(n.weight * 2 + n.deg)), "disc"),
        label: buttonLabel(n, "person", "facts"),
        dim: Boolean(focus && focus !== n && !near.has(n.id)),
        selected: n === selected,
        near: near.has(n.id),
        focusable: !hidden(n),
      };
    },
    translate: toScreen,
  };
}

function host(doc) {
  return { svg: doc.createElementNS("http://www.w3.org/2000/svg", "svg"), overlay: doc.createElement("div") };
}

/* ── The words on the button ────────────────────────────────────────────── */

check("a button announces the name first, then its kind, then how much is known", () => {
  const n = node(1, "Priya", "person", 43, 0);
  assert.equal(buttonLabel(n, "person", "facts"), "Priya, person, 43 facts");
  // A name with no weight yet must not read "0 facts".
  assert.equal(buttonLabel(node(2, "Lisbon", "place", 0, 1), "place", "facts"), "Lisbon, place");
  assert.equal(buttonLabel(n, "", "facts"), "Priya, 43 facts");
  assert.equal(buttonLabel(n, null, "facts"), "Priya, 43 facts");
});

check("an over-long name is clipped, exactly as the canvas clipped it", () => {
  const long = "x".repeat(LABEL_MAX + 20);
  assert.equal(labelFor({ label: long }).length, LABEL_MAX);
  assert.ok(labelFor({ label: long }).endsWith("…"));
  assert.equal(labelFor({ label: "  Miso  " }), "Miso");
  // A name that is only whitespace is no name: nothing to announce, and the
  // caller must not draw a button for it.
  assert.equal(labelFor({ label: "   " }), null);
  assert.equal(labelFor({}), null);
});

/* ── Shape ──────────────────────────────────────────────────────────────── */

check("a ring is stroked inside its radius, so ring and disc read the same size", () => {
  const disc = shapeFor(10, "disc");
  assert.equal(disc.kind, "disc");
  assert.equal(disc.radius, 10);
  const ring = shapeFor(10, "ring");
  assert.equal(ring.kind, "ring");
  assert.ok(ring.strokeWidth > 1, "a ring narrower than a pixel is not a shape");
  assert.ok(ring.radius + ring.strokeWidth / 2 <= 10 + 1e-9, "the ring grew past its radius");
  assert.ok(shapeFor(0.2, "ring").radius >= 1);
});

/* ── The two syntaxes ───────────────────────────────────────────────────── */

check("each coordinate goes into the syntax its own medium wants", () => {
  // SVG attribute form: `translate(1.5 2)`. CSS form: `translate(1.5px, 2px)`.
  // Mixing them up misplaces every dot, silently, in one medium or the other.
  assert.equal(svgTransform(1.5, 2), "translate(1.5 2)");
  assert.equal(cssTransform(1.5, 2), "translate(1.5px, 2px)");
  assert.doesNotMatch(svgTransform(1, 2), /px|,/);
  assert.match(cssTransform(-3, 4.25), /^-?translate\(-3px, 4\.3px\)$/);
});

/* ── The tree ───────────────────────────────────────────────────────────── */

check("every shown name is a real HTML button, and every button names its node", () => {
  const doc = makeDoc();
  const h = host(doc);
  const a = { ...node(1, "Priya", "person", 43, 0), x: 1, y: 2 };
  const b = { ...node(2, "Lisbon", "place", 3, 1), x: 3, y: 4 };
  const built = buildConstellation(h, model([a, b], [{ s: a, t: b }]), doc);

  const buttons = walk(h.overlay).filter((el) => el.tag === "button");
  assert.equal(buttons.length, 2, `expected one button per name, got ${buttons.length}`);
  for (const el of buttons) {
    // HTML, not SVG: an SVG `<button>` is not focusable in Chromium, which
    // `tests/galaxy-button-engine.mjs` measured.
    assert.equal(el.ns, "http://www.w3.org/1999/xhtml", "the control must be an HTML button");
    assert.equal(el.getAttribute("type"), "button");
    assert.ok(el.getAttribute("aria-label").length > 0, "a button with no name announces nothing");
    assert.equal(el.getAttribute("tabindex"), "0");
    assert.ok(/^-?translate\(/.test(el.style.transform), "the button is not placed");
  }
  assert.equal(built.buttons.get(1).button.getAttribute("aria-label"), "Priya, person, 43 facts");
  // The drawing is a separate SVG shape, and there is exactly one per name.
  const shapes = walk(h.svg).filter((el) => el.tag === "circle");
  assert.equal(shapes.length, 2, "each name needs exactly one drawn dot");
  assert.equal(shapes[0].ns, "http://www.w3.org/2000/svg");
});

check("the shape carries the group's colour and form", () => {
  const doc = makeDoc();
  const h = host(doc);
  const round = { ...node(1, "Priya", "person", 10, 0), x: 0, y: 0 };
  const hollow = { ...node(2, "Miso", "pet", 10, 1), x: 1, y: 1 };
  const m = model([round, hollow], []);
  m.describe = ((base) => (n) => {
    const v = base(n);
    if (n.group === "pet") v.shape = shapeFor(9, "ring");
    return v;
  })(m.describe);
  const built = buildConstellation(h, m, doc);

  const petShape = built.buttons.get(2).shape;
  assert.equal(petShape.getAttribute("data-form"), "ring");
  assert.equal(petShape.getAttribute("fill"), "none");
  assert.ok(Number(petShape.getAttribute("stroke-width")) > 0);
  const personShape = built.buttons.get(1).shape;
  assert.equal(personShape.getAttribute("data-form"), "disc");
  assert.equal(personShape.getAttribute("stroke"), "none");
  // The group rides on BOTH halves, so a forced-colors or CSS rule can reach
  // either the drawing or the control.
  assert.equal(built.buttons.get(2).button.getAttribute("data-group"), "pet");
});

check("the dot is placed in the picture and its button is placed over it, at the same point", () => {
  const doc = makeDoc();
  const h = host(doc);
  const a = { ...node(1, "Priya", "person", 5, 0), x: 10, y: 20 };
  const built = buildConstellation(h, model([a], []), doc);
  // `model`'s screen transform is x2, so world (10,20) is screen (20,40).
  assert.equal(built.buttons.get(1).group.getAttribute("transform"), "translate(20 40)");
  assert.equal(built.buttons.get(1).button.style.transform, "translate(20px, 40px)");
});

check("a hidden group draws nothing, is not focusable and is not announced", () => {
  const doc = makeDoc();
  const h = host(doc);
  const shown = { ...node(1, "Priya", "person", 5, 0), x: 0, y: 0 };
  const gone = { ...node(2, "Miso", "pet", 5, 1), x: 1, y: 1 };
  const built = buildConstellation(h, model([shown, gone], [], { hidden: (n) => n.group === "pet" }), doc);
  assert.equal(built.buttons.size, 1, "a hidden name got a button");
  const names = walk(h.overlay).filter((e) => e.tag === "button").map((e) => e.getAttribute("aria-label"));
  assert.deepEqual(names, ["Priya, person, 5 facts"]);
  assert.equal(walk(h.svg).filter((e) => e.tag === "circle").length, 1);
});

check("links are drawn once each, and never for a hidden end", () => {
  const doc = makeDoc();
  const h = host(doc);
  const a = { ...node(1, "Priya", "person", 5, 0), x: 0, y: 0 };
  const b = { ...node(2, "Lisbon", "place", 5, 1), x: 10, y: 0 };
  const c = { ...node(3, "Miso", "pet", 5, 2), x: 0, y: 10 };
  const links = [{ s: a, t: b }, { s: a, t: c }];
  const built = buildConstellation(h, model([a, b, c], links, { hidden: (n) => n.group === "pet" }), doc);
  const lineEls = walk(h.svg).filter((e) => e.tag === "line");
  assert.equal(lineEls.length, 1, "a link to a hidden name was drawn");
  assert.equal(lineEls[0].getAttribute("data-link"), "1~2");
  // `model`'s screen transform is x2, so this is 0 -> 20.
  assert.equal(lineEls[0].getAttribute("x1"), "0");
  assert.equal(lineEls[0].getAttribute("x2"), "20");
});

/* ── Labels ─────────────────────────────────────────────────────────────── */

check("labels follow the canvas's rules: the focused name and its neighbours first", () => {
  const nodes = Array.from({ length: 40 }, (_, i) => node(i + 1, `Name ${i}`, "person", 5, i));
  const focus = nodes[30];
  const near = new Set([nodes[31].id]);
  const out = labelledNodes(nodes, { scale: 1, focus, near, hidden: () => false });
  const labelled = out.map((l) => l.node.id);
  assert.ok(labelled.includes(focus.id), "the focused name is not labelled");
  assert.ok(labelled.includes(nodes[31].id), "a neighbour is not labelled");
  assert.equal(labelled[0], focus.id, "the focused name does not sort first");
  assert.ok(labelled.length <= LABELLED_NAMES + 2, `labelled ${labelled.length} names`);
});

check("nothing is labelled when zoomed too far out, except what is focused", () => {
  const nodes = Array.from({ length: 40 }, (_, i) => node(i + 1, `Name ${i}`, "person", 5, i));
  const bare = labelledNodes(nodes, { scale: LABEL_MIN_SCALE / 2, focus: null, near: new Set(), hidden: () => false });
  assert.ok(bare.every((l) => l.node.rank < 6), "an unremarkable name was labelled while zoomed out");
  const withFocus = labelledNodes(nodes, { scale: LABEL_MIN_SCALE / 2, focus: nodes[35], near: new Set(), hidden: () => false });
  assert.ok(withFocus.some((l) => l.node.id === nodes[35].id), "the focused name lost its label when zoomed out");
});

check("a hidden name is never labelled", () => {
  const nodes = [node(1, "Priya", "person", 5, 0), node(2, "Miso", "pet", 5, 1)];
  const out = labelledNodes(nodes, { scale: 2, focus: null, near: new Set(), hidden: (n) => n.group === "pet" });
  assert.deepEqual(out.map((l) => l.node.label), ["Priya"]);
});

/* ── Repaint ────────────────────────────────────────────────────────────── */

check("a repaint moves the dot, its button and the link together", () => {
  const doc = makeDoc();
  const h = host(doc);
  const a = { ...node(1, "Priya", "person", 5, 0), x: 0, y: 0 };
  const b = { ...node(2, "Lisbon", "place", 5, 1), x: 5, y: 0 };
  const m = model([a, b], [{ s: a, t: b }], { selected: a, focus: a, near: [b.id] });
  const built = buildConstellation(h, m, doc);

  a.x = 7;
  paintConstellation(h, m, built);
  assert.equal(built.buttons.get(1).group.getAttribute("transform"), "translate(14 0)");
  assert.equal(built.buttons.get(1).button.style.transform, "translate(14px, 0px)");
  const line = walk(h.svg).find((e) => e.tag === "line");
  assert.equal(line.getAttribute("x1"), "14", "a link did not follow the node it joins");

  assert.equal(built.buttons.get(1).button.classList.contains("is-selected"), true);
  assert.equal(built.buttons.get(1).button.getAttribute("aria-pressed"), "true");
  assert.equal(built.buttons.get(2).button.getAttribute("aria-pressed"), "false");
  assert.equal(line.classList.contains("is-lit"), true, "the link to the focused node is not lit");
});

check("a repaint hides a node that has just been filtered out, and its links", () => {
  const doc = makeDoc();
  const h = host(doc);
  const a = { ...node(1, "Priya", "person", 5, 0), x: 0, y: 0 };
  const b = { ...node(2, "Miso", "pet", 5, 1), x: 3, y: 0 };
  let hide = () => false;
  const m = model([a, b], [{ s: a, t: b }], { hidden: (n) => hide(n) });
  const built = buildConstellation(h, m, doc);
  const line = walk(h.svg).find((e) => e.tag === "line");
  assert.equal(line.hasAttribute("hidden"), false);

  hide = (n) => n.group === "pet";
  paintConstellation(h, m, built);
  assert.equal(built.buttons.get(2).group.hasAttribute("hidden"), true, "the filtered-out dot is still drawn");
  assert.equal(built.buttons.get(2).button.hidden, true, "the filtered-out button is still reachable");
  assert.equal(line.hasAttribute("hidden"), true, "a link to a filtered-out dot is still drawn");
});

check("labels are added, moved and removed as the view changes, and never stacked twice", () => {
  const doc = makeDoc();
  const h = host(doc);
  const a = { ...node(1, "Priya", "person", 5, 0), x: 0, y: 0 };
  const b = { ...node(2, "Lisbon", "place", 5, 1), x: 5, y: 0 };
  const m = model([a, b], []);
  const built = buildConstellation(h, m, doc);
  const labelsLayer = built.layers.labels;

  m.labels = [{ node: a, text: "Priya" }];
  paintConstellation(h, m, built);
  assert.equal(labelsLayer.children.length, 1);
  assert.equal(labelsLayer.children[0].textContent, "Priya");

  // Repainting the same view must not add a second copy.
  paintConstellation(h, m, built);
  assert.equal(labelsLayer.children.length, 1, "a label was duplicated by a repaint");

  m.labels = [{ node: a, text: "Priya" }, { node: b, text: "Lisbon" }];
  paintConstellation(h, m, built);
  assert.equal(labelsLayer.children.length, 2);

  // A name that is no longer labelled has its label taken away.
  m.labels = [{ node: b, text: "Lisbon" }];
  paintConstellation(h, m, built);
  assert.equal(labelsLayer.children.length, 1);
  assert.equal(labelsLayer.children[0].textContent, "Lisbon");
});

check("a name with no name at all is skipped rather than drawn as an anonymous dot", () => {
  const doc = makeDoc();
  const h = host(doc);
  const blank = { ...node(1, "", "person", 0, 0), x: 0, y: 0 };
  const named = { ...node(2, "Priya", "person", 5, 1), x: 1, y: 1 };
  const base = model([blank, named], []);
  const m = { ...base, describe: (n) => (n.label ? base.describe(n) : null) };
  const built = buildConstellation(h, m, doc);
  assert.equal(built.buttons.size, 1);
  assert.equal(built.buttons.has(2), true);
  for (const el of walk(h.overlay).filter((e) => e.tag === "button")) {
    assert.ok(el.getAttribute("aria-label").trim().length > 0);
  }
});

console.log(fails.length
  ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nevery name is a real HTML button, and the constellation keeps the canvas's own rules");
process.exit(fails.length ? 1 : 0);
