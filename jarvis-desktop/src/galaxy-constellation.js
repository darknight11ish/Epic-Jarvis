/**
 * The Galaxy as a constellation of real buttons - the DOM half.
 *
 * WHY THIS EXISTS. The Galaxy used to be drawn only on a `<canvas>`. The
 * project's own rule is **"nothing drawn only on the canvas"**, and a canvas
 * cannot satisfy it: a dot is pixels, not a control. There is no element for the
 * keyboard to land on, nothing for CSS to theme, nothing for Windows
 * high-contrast to repaint, and no way for a screen reader to list what is
 * there. The search field covered "reach every node by name" - and
 * `tests/galaxy.mjs` holds that - but each DOT remained unreachable.
 *
 * THE ONE DESIGN CHOICE THAT MATTERS, and it was measured rather than assumed:
 * a node's button is an **HTML `<button>`**, positioned over the picture, NOT a
 * `<button>` inside the SVG.
 *
 * The SVG version was written first and looked right. `tests/galaxy-button-engine.mjs`
 * drove it in real Chromium and found that **an SVG `<button>` is not focusable and
 * is never clicked**: Tab skipped straight past it, Enter and Space did nothing,
 * and Playwright reported the element as not visible. A picture of an accessible
 * control is exactly the failure this work exists to prevent, so the shapes go in
 * the SVG (they scale, they take the theme's tokens, forced-colors repaints them)
 * and the buttons go in HTML on top of them (they are in the tab order, they are
 * clickable, a screen reader lists them). The pairing is the point.
 *
 * This file is deliberately PURE: it builds elements from a description and never
 * reads the page. `brain.js` owns the layout, the view transform and the wiring.
 */

/**
 * Below this zoom a node is a dot with no label: every name labelled at any zoom
 * is a grey smear, which is why the canvas had the same rule.
 */
export const LABEL_MIN_SCALE = 0.35;

/** How many of the best-connected names are labelled when nothing is focused.
 *  The rest are still real buttons - they are simply unlabelled until the
 *  pointer or the keyboard reaches them. */
export const LABELLED_NAMES = 24;

/** A name longer than this is clipped in its label. */
export const LABEL_MAX = 34;

const SVG_NS = "http://www.w3.org/2000/svg";

/**
 * The shape a node is drawn as: a filled disc, or a hollow ring that is stroked
 * INSIDE its radius so a ring and a disc of the same group read as the same
 * size. `strokeWidth` is the callers' `drawNode` rule, kept identical.
 */
export function shapeFor(radius, form) {
  const strokeWidth = Math.max(1.4, radius * 0.42);
  if (form === "ring") {
    return { kind: "ring", radius: Math.max(1, radius - strokeWidth / 2), strokeWidth };
  }
  return { kind: "disc", radius, strokeWidth: 0 };
}

/** The label for a node, clipped like the canvas clipped it. `null` when the
 *  name is empty, which would be a dot with nothing to announce. */
export function labelFor(node) {
  const text = String(node?.label ?? "").trim();
  if (!text) return null;
  return text.length > LABEL_MAX ? `${text.slice(0, LABEL_MAX - 1)}…` : text;
}

/**
 * What every node's button announces. A screen reader hears the name first
 * (that is what the owner is looking for), then its kind in the list's own
 * words, then how much Jarvis knows about it.
 */
export function buttonLabel(node, kindWord, factWord) {
  const name = labelFor(node) ?? "";
  const parts = [name];
  if (kindWord) parts.push(kindWord);
  if (Number.isFinite(node?.weight) && node.weight > 0) parts.push(`${node.weight} ${factWord}`);
  return parts.filter(Boolean).join(", ");
}

/** A node's screen point as CSS, for an absolutely-positioned HTML button. */
export function cssTransform(x, y) {
  return `translate(${round(x)}px, ${round(y)}px)`;
}

/** A node's screen point as an SVG `transform` attribute. SVG syntax, not CSS:
 *  `translate(1px, 2px)` in a style attribute is CSS and behaves differently
 *  across engines, while the attribute form is exact. */
export function svgTransform(x, y) {
  return `translate(${round(x)} ${round(y)})`;
}

function round(v) {
  // Sub-pixel precision is wasted on a 6-20px dot and makes every transform
  // string different, which defeats any comparison of two frames.
  return Math.round(Number(v) * 10) / 10;
}

/**
 * Which nodes are labelled at this view.
 *
 * The rules, all inherited from the canvas so the picture stays the same:
 *   - the focused node and everything joined to it are always labelled;
 *   - below `LABEL_MIN_SCALE`, only those, plus the handful of best-connected
 *     names once the labels are dense enough to be worth it;
 *   - otherwise the best-connected `LABELLED_NAMES`.
 */
export function labelledNodes(nodes, { scale, focus, near, hidden }) {
  const isNear = (n) => near.has(n.id);
  const ordered = nodes
    .filter((n) => !hidden(n))
    .filter((n) => n.rank < LABELLED_NAMES || (focus && (n === focus || isNear(n))))
    .sort((a, b) => {
      const pull = (n) => (n === focus ? 4 : 0) + (isNear(n) ? 2 : 0);
      return pull(b) - pull(a) || a.rank - b.rank;
    });
  const out = [];
  for (const n of ordered) {
    if (scale < LABEL_MIN_SCALE && !isNear(n) && (!focus || n !== focus) && n.rank >= 6) continue;
    const text = labelFor(n);
    if (text) out.push({ node: n, text });
  }
  return out;
}

/**
 * Builds the whole constellation into `host`.
 *
 * `host` holds two children the caller already has: the `svg` for the drawing and
 * the `overlay` - a positioned container - for the labels and buttons. Both are
 * emptied first, so a rebuild never stacks two pictures.
 *
 * Returns what the caller needs to keep: the node buttons by id (for focus,
 * selection and the roving tab stop) and the layers.
 */
export function buildConstellation(host, model, doc = host?.svg?.ownerDocument) {
  const { svg, overlay } = host ?? {};
  if (!svg || !overlay || !doc) throw new Error("buildConstellation needs an svg, an overlay and a document");
  const { nodes = [], links = [], hidden = () => false, describe, translate, label } = model;

  while (svg.firstChild) svg.removeChild(svg.firstChild);
  while (overlay.firstChild) overlay.removeChild(overlay.firstChild);

  const layers = {};
  for (const name of ["links", "nodes"]) {
    const g = doc.createElementNS(SVG_NS, "g");
    g.setAttribute("class", `galaxy-layer galaxy-${name}`);
    g.setAttribute("data-layer", name);
    svg.append(g);
    layers[name] = g;
  }
  const labels = doc.createElement("div");
  labels.setAttribute("class", "galaxy-layer galaxy-labels");
  labels.setAttribute("data-layer", "labels");
  overlay.append(labels);
  layers.labels = labels;

  // Links first, so every dot sits on top of the line that reaches it.
  const lines = new Map();
  for (const l of links) {
    if (!l || !l.s || !l.t || hidden(l.s) || hidden(l.t)) continue;
    const line = doc.createElementNS(SVG_NS, "line");
    line.setAttribute("class", "galaxy-link");
    line.setAttribute("data-link", `${l.s.id}~${l.t.id}`);
    layers.links.append(line);
    lines.set(`${l.s.id}~${l.t.id}`, { line, a: l.s, b: l.t });
  }

  const buttons = new Map();
  for (const n of nodes) {
    if (hidden(n)) continue;
    const view = describe(n);
    if (!view) continue;

    // The drawing: an SVG circle, which scales, themes and survives
    // forced-colors.
    const group = doc.createElementNS(SVG_NS, "g");
    group.setAttribute("class", "galaxy-node");
    group.setAttribute("data-node", String(n.id));
    group.setAttribute("transform", svgTransform(view.x, view.y));
    const shape = doc.createElementNS(SVG_NS, "circle");
    shape.setAttribute("class", "galaxy-node-shape");
    shape.setAttribute("data-group", String(n.group ?? "other"));
    shape.setAttribute("data-form", view.shape.kind);
    shape.setAttribute("r", String(round(view.shape.radius)));
    shape.setAttribute("fill", view.shape.kind === "ring" ? "none" : view.colour);
    shape.setAttribute("stroke", view.shape.kind === "ring" ? view.colour : "none");
    if (view.shape.kind === "ring") shape.setAttribute("stroke-width", String(round(view.shape.strokeWidth)));
    group.append(shape);
    layers.nodes.append(group);

    // The control: an HTML button, over the drawing. This is the part that has
    // to be HTML - see the note at the top of this file.
    const button = doc.createElement("button");
    button.setAttribute("type", "button");
    button.setAttribute("class", "galaxy-node-button");
    button.setAttribute("data-node", String(n.id));
    button.setAttribute("data-group", String(n.group ?? "other"));
    button.setAttribute("data-form", view.shape.kind);
    button.setAttribute("aria-label", view.label);
    button.setAttribute("tabindex", view.focusable === false ? "-1" : "0");
    button.style.transform = cssTransform(view.x, view.y);
    const size = Math.max(8, Math.round((view.shape.radius + view.shape.strokeWidth / 2) * 2 + 10));
    button.style.width = `${size}px`;
    button.style.height = `${size}px`;
    overlay.append(button);

    buttons.set(n.id, { group, shape, button, node: n });
  }

  const built = { layers, buttons, lines };

  // Give every dot, link and label its place before returning. Without this a
  // freshly-built picture is a pile of shapes at the origin until something
  // happens to move them - which is what a `<line>` with no `x1` actually is,
  // and the test that reads `x1` is what noticed.
  paintConstellation(host, model, built);

  return built;
}

/**
 * Redraws what moved, without rebuilding the tree: each dot, its button, its
 * link and its label. Called on every pan, zoom and settle tick, so it touches
 * as little as possible.
 */
export function paintConstellation(host, model, built) {
  if (!host || !built) return;
  const { hidden = () => false, describe, translate } = model;
  const { layers, buttons, lines } = built;

  for (const [, entry] of buttons) {
    if (hidden(entry.node)) {
      entry.group.setAttribute("hidden", "");
      entry.button.hidden = true;
      continue;
    }
    entry.group.removeAttribute("hidden");
    entry.button.hidden = false;
    const view = describe(entry.node);
    if (!view) continue;
    entry.group.setAttribute("transform", svgTransform(view.x, view.y));
    entry.button.style.transform = cssTransform(view.x, view.y);
    const shape = entry.shape;
    shape.setAttribute("fill", view.shape.kind === "ring" ? "none" : view.colour);
    shape.setAttribute("stroke", view.shape.kind === "ring" ? view.colour : "none");
    entry.button.classList.toggle("is-dim", view.dim);
    entry.button.classList.toggle("is-selected", view.selected);
    entry.button.classList.toggle("is-near", view.near);
    entry.button.setAttribute("aria-pressed", view.selected ? "true" : "false");
    entry.button.classList.toggle("is-labelled", Boolean(view.labelled));
  }

  const focus = model.focus;
  for (const { line, a, b } of lines.values()) {
    const ea = buttons.get(a.id);
    const eb = buttons.get(b.id);
    if (!ea || !eb || hidden(a) || hidden(b)) {
      line.setAttribute("hidden", "");
      continue;
    }
    line.removeAttribute("hidden");
    const pa = translate(a);
    const pb = translate(b);
    line.setAttribute("x1", String(round(pa.x)));
    line.setAttribute("y1", String(round(pa.y)));
    line.setAttribute("x2", String(round(pb.x)));
    line.setAttribute("y2", String(round(pb.y)));
    line.classList.toggle("is-lit", Boolean(focus && (a === focus || b === focus)));
    line.classList.toggle("is-dim", Boolean(focus && a !== focus && b !== focus));
  }

  // The visible names. One span per labelled node, reusing the buttons' places.
  const want = model.labels ?? [];
  const keep = new Map();
  for (const el of [...layers.labels.childNodes]) {
    const id = el.getAttribute?.("data-label-for");
    if (id === null || !want.some((w) => String(w.node.id) === id)) layers.labels.removeChild(el);
    else keep.set(id, el);
  }
  for (const { node: n, text } of want) {
    const key = String(n.id);
    let el = keep.get(key);
    if (!el) {
      el = layers.labels.ownerDocument.createElement("span");
      el.setAttribute("class", "galaxy-node-label");
      el.setAttribute("data-label-for", key);
      layers.labels.append(el);
    }
    if (el.textContent !== text) el.textContent = text;
    const p = translate(n);
    const entry = buttons.get(n.id);
    const below = entry ? entry.shape.getAttribute("r") : 0;
    el.style.transform = cssTransform(p.x, Number(p.y) + Number(below) + 4);
  }
  return layers;
}
