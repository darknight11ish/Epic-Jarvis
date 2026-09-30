/**
 * "Facts behind this dot": the panel under a picked dot in the Galaxy
 * (docs/GALAXY-PANEL-DESIGN.md; JARVIS-API.md section 106). Read-only.
 *
 * It lists the saved facts that name the dot, in their own words, newest
 * first, 20 at a time. The ids come from the dot (`GET /api/memory/entities`,
 * already read); the words come from `memory_used` (`GET /api/memory/used`),
 * one call per page. No other route, no library, no model, nothing saved.
 * While Windows Hello hides the memory lists Rust empties that read; if the
 * lists become hidden while the panel is open, `clear()` removes every word
 * from the page at once. Words are never kept anywhere but this list's rows.
 *
 * @module galaxy-panel
 */
import { PANEL_PAGE, factPage, factRow, panelWords, sortRows } from "./galaxy-view.js";
import { readUsed } from "./memory-used.js";
import { erasedLine } from "./auto-learn.js";

function make(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined && text !== null) n.textContent = String(text);
  return n;
}

function dateText(seconds) {
  return new Date(seconds * 1000).toLocaleDateString(undefined,
    { day: "numeric", month: "long", year: "numeric" });
}

/**
 * @param {object} o
 * @param {(cmd: string, args: object) => Promise<any>} o.invoke  the Tauri bridge (null: no panel)
 * @param {{root, title, note, list, count, live, foot}} o.dom     the section's elements
 * @param {(entityId: number) => any} o.onOpen                    opens "About <name>"
 */
export function createGalaxyPanel({ invoke, dom, onOpen }) {
  let node = null;
  let token = 0;
  let page = 0; // pages read so far
  let topicsHidden = 0;
  let busy = false;

  const words = (key, vars) => panelWords(key, vars);

  function wipe() {
    dom.list.replaceChildren();
    dom.foot.replaceChildren();
    dom.count.textContent = "";
    dom.live.textContent = "";
    dom.note.replaceChildren();
    dom.note.hidden = true;
  }

  function say(text, retry = false) {
    dom.note.replaceChildren(make("span", "", text));
    if (retry) {
      const b = make("button", "btn small", words("galaxy_panel_retry"));
      b.type = "button";
      b.addEventListener("click", () => load(page));
      dom.note.append(" ", b);
    }
    dom.note.hidden = false;
  }

  function rowNode(r) {
    const li = make("li", "galaxy-fact");
    li.tabIndex = -1;
    li.append(make("p", `galaxy-fact-text${r.erased ? " erased" : ""}`, r.text));
    const meta = make("p", "galaxy-fact-meta");
    const bits = [];
    if (r.created) bits.push(dateText(r.created));
    if (r.erasedAt) bits.push(erasedLine(r.erasedAt));
    if (bits.length) meta.append(make("span", "", bits.join(" · ")));
    for (const [on, key] of [[r.pinned, "galaxy_panel_pinned"], [r.forgotten, "galaxy_panel_forgotten"]]) {
      if (on) meta.append(make("span", "galaxy-fact-mark", words(key)));
    }
    li.append(meta);
    const open = make("button", "btn small", words("galaxy_panel_open"));
    open.type = "button";
    open.addEventListener("click", () => { if (node) onOpen(node.entityId); });
    li.append(open);
    return li;
  }

  function paintFoot() {
    dom.foot.replaceChildren();
    const total = node.factIds.length;
    const read = Math.min(total, page * PANEL_PAGE);
    dom.count.textContent = words("galaxy_panel_showing", { n: read, total });
    if (read < total) {
      const b = make("button", "btn small", words("galaxy_panel_more"));
      b.type = "button";
      b.addEventListener("click", () => load(page, true));
      dom.foot.append(b);
    }
  }

  async function load(at, moreClicked = false) {
    if (!node || busy) return;
    const mine = ++token;
    const mineNode = node;
    busy = true;
    dom.note.hidden = true;
    const firstNew = dom.list.children.length;
    const ids = factPage(mineNode, at);
    if (!ids.length) {
      busy = false;
      if (!dom.list.children.length) say(words("galaxy_panel_empty"));
      return;
    }
    if (!dom.list.children.length) say(words("galaxy_panel_reading"));
    let view;
    try {
      view = readUsed(await invoke("memory_used", { ids }));
    } catch {
      view = null;
    }
    busy = false;
    if (mine !== token || node !== mineNode) return; // another dot, or cleared
    if (view && view.hidden) return clear(true);
    if (!view || !view.available) {
      dom.foot.replaceChildren();
      return say(words("galaxy_panel_failed"), true);
    }
    page = at + 1;
    const shown = sortRows(view.facts.map(factRow).filter((r) => {
      if (r.skip) topicsHidden += 1;
      return !r.skip;
    }));
    dom.note.replaceChildren();
    dom.note.hidden = true;
    for (const r of shown) dom.list.append(rowNode(r));
    if (topicsHidden) say(words("galaxy_panel_topics_hidden", { n: topicsHidden }));
    else if (!dom.list.children.length && page * PANEL_PAGE >= mineNode.factIds.length) {
      say(words("galaxy_panel_empty"));
    }
    paintFoot();
    if (moreClicked) {
      dom.live.textContent = dom.count.textContent;
      const target = dom.list.children[firstNew];
      if (target) target.focus({ preventScroll: false });
    }
  }

  function heading() {
    dom.title.textContent = words("galaxy_panel", { count: node.factIds.length });
  }

  /** The dot was unpicked, or the lists were hidden: no word stays on the page. */
  function clear(hidden = false) {
    token += 1;
    busy = false;
    const had = node;
    node = null;
    page = 0;
    topicsHidden = 0;
    wipe();
    dom.title.textContent = "";
    if (hidden && had) {
      dom.root.hidden = false;
      say(words("galaxy_panel_hidden"));
    } else {
      dom.root.hidden = true;
    }
  }

  return {
    /** A dot was picked: reset and read the newest page. */
    show(picked) {
      token += 1;
      busy = false;
      node = picked && Array.isArray(picked.factIds) ? picked : null;
      page = 0;
      topicsHidden = 0;
      wipe();
      if (!node || !invoke) {
        dom.root.hidden = true;
        return;
      }
      dom.root.hidden = false;
      heading();
      load(0);
    },
    clear,
  };

}
