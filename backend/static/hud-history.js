/* hud-history.js - the History sidebar in the HUD's left column.
 *
 * THE OWNER'S ASK (2026-10-27, with a screenshot of the DeepSeek Harness
 * sidebar): "Id like a history tab with a column icon that opens up a menu
 * that looks like all the coversations in the deepseek harness on desktop
 * for the jarvis HUD, like the screenshot. ... both should have pinnable
 * chats, project organization by chat, and more".
 *
 * So this is ONE column icon in the HUD's own left rail (`#rail-toolbar`,
 * beside Presets and Live) that opens a panel shaped like that screenshot:
 *
 *   History                                  [sort] [+]
 *   [ Search chats                                    ]
 *   v  Pinned                              3
 *        ~ What is the capital of France?       7d
 *        ~ Fix the patio light wiring          11d
 *   v  [briefcase] Work                    12
 *        # Standup notes                        25min
 *        ...
 *        Show 7 more sessions
 *   v  [folder] Projects                    4
 *   v  Untagged                             9
 *
 * Pinned chats sit at the top, then ONE section per tag (the owner's own
 * "project organisation": docs/CHAT-TAGS-DESIGN.md, JARVIS-API section 99),
 * then the chats with no tag. Each section collapses and says how many
 * chats it holds; a long one shows its first five and a "Show N more
 * sessions" row. A click on a row opens that chat in this window's chat
 * view; a right-click (or the row's "...") offers Open, Pin/Unpin, Move to
 * project and Delete chat. The current chat is marked.
 *
 * WHAT IT MAY DO, AND WHAT IT MAY NOT
 * The page holds NO pairing token (apps security audit M2), so in the
 * desktop shell every read goes through `hud_proxy.rs::hud_get` (three
 * History reads on its fixed list) and the three writes go through ONE Rust
 * command, `hud_history_act` (brain/history.rs): pin, file under a tag, or
 * delete ONE chat. In a plain browser the page talks to the backend
 * directly, exactly as the rest of this page already does. Nothing here
 * approves anything, raises a card, deletes in bulk, or sends a chat's words
 * anywhere: the search box filters the list this window already loaded, and
 * its text is never sent to the PC.
 *
 * PINNING is the PC's own record: a `pinned` column in the same encrypted
 * history file, set by `POST /api/history/pin` (JARVIS-API section 18.3), so
 * a pin made here survives a restart and the phone reads the same flag. This
 * window keeps no list of its own.
 *
 * The pure half (ages, grouping, search, sort, the "show more" count and the
 * three write bodies) is exported on `window.hudHistory` so
 * tests/hud-history.mjs can hold it without a browser; the DOM half is
 * `mount(host)`, where `host` is the page's own three functions:
 *
 *   host.current()      -> the conversation id this window is in
 *   host.open(conv)     -> draw one kept chat in this window's chat view
 *   host.newChat()      -> start a fresh chat here
 *
 * The page supplies them (`window.hudHistoryHost`, at the end of its own
 * script). With no host the panel still lists, searches, sorts, pins, files
 * and deletes; only Open and New chat do nothing, and they say so.
 *
 * AN ES MODULE, so it can read `history-actions.js` - the row-action table and
 * the words both windows use (Gemini ruling, 2026-10-27: share them with
 * brain.js like the Reminders `hud-actions.js`, so pin/file/delete cannot
 * drift). It is loaded with `<script type="module">`: still ONE external file,
 * so the page's inline-script count and every CSP hash are untouched.
 */
import {
  ACTION_LABELS,
  DELETE_KEEPS_FACTS,
  DELETE_QUESTION,
  DELETE_REMOVES,
  actArgs,
  actBody,
  labelFor,
} from "./history-actions.js";

(function (root) {
  "use strict";

  /** Rows shown in a section before its "Show N more sessions" row. */
  var CAP = 5;
  /** The most one History read may ask for (the PC's own LIST_MAX). */
  var MAX_ROWS = 100;
  /** Where the owner's collapsed sections and sort order are remembered. */
  var LS_COLLAPSED = "jarvis.history.collapsed";
  var LS_SORT = "jarvis.history.sort";
  /** The word for the section that holds chats with no tag. The same word
   *  both apps already use (docs/CHAT-TAGS-DESIGN.md: "Untagged"). */
  var UNTAGGED = "Untagged";
  var PINNED = "Pinned";

  /* ------------------------------------------------------------------ *
   * Small helpers
   * ------------------------------------------------------------------ */

  function text(v) {
    return typeof v === "string" ? v : v === null || v === undefined ? "" : String(v);
  }

  function num(v, fallback) {
    var n = typeof v === "number" ? v : Number(v);
    return isFinite(n) ? n : fallback === undefined ? 0 : fallback;
  }

  function norm(v) {
    return text(v).trim().toLowerCase();
  }

  function lsGet(key) {
    try {
      return root.localStorage ? root.localStorage.getItem(key) : null;
    } catch (e) {
      return null;
    }
  }

  function lsSet(key, value) {
    try {
      if (root.localStorage) root.localStorage.setItem(key, value);
    } catch (e) {
      /* private mode, or full: remembering is a convenience, never required */
    }
  }

  function lsJson(key) {
    try {
      var raw = lsGet(key);
      var parsed = raw ? JSON.parse(raw) : null;
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (e) {
      return {};
    }
  }

  /* ------------------------------------------------------------------ *
   * Ages - "7d", "11d", "25min", as the screenshot has them
   * ------------------------------------------------------------------ */

  /** One chat's age, short: "now", "25min", "3h", "7d", "2mo", "1y".
   *  `now` and `updated` are unix SECONDS (the History list's own unit). */
  function ageWords(updated, now) {
    var u = num(updated, 0);
    var at = num(now, Math.floor(Date.now() / 1000));
    if (u <= 0) return "";
    var s = Math.floor(at - u);
    if (!isFinite(s)) return "";
    if (s < 0) s = 0;
    if (s < 45) return "now";
    if (s < 3600) return Math.max(1, Math.floor(s / 60)) + "min";
    if (s < 86400) return Math.floor(s / 3600) + "h";
    var days = Math.floor(s / 86400);
    if (days < 30) return days + "d";
    if (days < 365) return Math.floor(days / 30) + "mo";
    return Math.floor(days / 365) + "y";
  }

  /** The same age in words, for the row's accessible name: "just now",
   *  "25 minutes ago", "7 days ago". */
  function ageTitle(updated, now) {
    var u = num(updated, 0);
    var at = num(now, Math.floor(Date.now() / 1000));
    if (u <= 0) return "";
    var s = Math.max(0, Math.floor(at - u));
    var one = function (n, word) {
      return n + " " + word + (n === 1 ? "" : "s") + " ago";
    };
    if (s < 45) return "just now";
    if (s < 3600) return one(Math.max(1, Math.floor(s / 60)), "minute");
    if (s < 86400) return one(Math.floor(s / 3600), "hour");
    var days = Math.floor(s / 86400);
    if (days < 30) return one(days, "day");
    if (days < 365) return one(Math.floor(days / 30), "month");
    return one(Math.floor(days / 365), "year");
  }

  /* ------------------------------------------------------------------ *
   * The list, as sections
   * ------------------------------------------------------------------ */

  /** One History row, with what this panel draws added. */
  function rowOf(conv, now, current) {
    var c = conv && typeof conv === "object" ? conv : {};
    var id = text(c.id);
    var kind = text(c.kind);
    return {
      id: id,
      title: text(c.title) || "(no title)",
      updated: num(c.updated, 0),
      kind: ICON_KINDS.indexOf(kind) >= 0 ? kind : "chat",
      tag_id: num(c.tag_id, 0) > 0 ? num(c.tag_id) : null,
      pinned: c.pinned === true,
      // WHEN it was pinned (unix seconds, the PC's own record). The Pinned
      // group is ordered by this and not by the chat's time, or a chat
      // pinned last week would jump above one pinned this morning as soon as
      // a message arrived in it (the Gemini ruling's `pinned_at DESC,
      // updated_at DESC`).
      pinned_at: num(c.pinned_at, 0),
      turns: num(c.turns, 0),
      voice: c.has_voice === true,
      tainted: c.tainted === true,
      age: ageWords(c.updated, now),
      ageLong: ageTitle(c.updated, now),
      current: !!id && id === text(current),
    };
  }

  /** Does this History row survive a search for `query`? The owner's own
   *  words in the title, nothing else - the PC is never asked, so what was
   *  SAID in a chat is not searched from this window (the Brain's History
   *  tab does that, section 71). */
  function matches(row, query) {
    var q = norm(query);
    if (!q) return true;
    return norm(row && row.title).indexOf(q) >= 0;
  }

  /** Newest first (the PC's own order), A to Z when the owner sorts, or the
   *  Pinned group's own order: `pinned_at DESC, updated DESC` (the newest pin
   *  first; two pins in the same second newest-chat first). The Pinned group
   *  keeps that order whatever the sort button says - it is what a pin MEANS
   *  - and every other group follows the button. */
  function sortRows(rows, mode) {
    var copy = rows.slice();
    if (mode === "pinned") {
      copy.sort(function (a, b) {
        return (
          num(b.pinned_at, 0) - num(a.pinned_at, 0) ||
          b.updated - a.updated ||
          a.title.localeCompare(b.title)
        );
      });
      return copy;
    }
    if (mode === "name") {
      copy.sort(function (a, b) {
        return (
          a.title.localeCompare(b.title, undefined, { sensitivity: "base" }) ||
          b.updated - a.updated
        );
      });
    } else {
      copy.sort(function (a, b) {
        return b.updated - a.updated || a.title.localeCompare(b.title);
      });
    }
    return copy;
  }

  /**
   * The panel's whole list, from the PC's two answers.
   *
   * `list` is GET /api/history's `conversations`; `tags` is GET
   * /api/history/tags's `tags`. `opts`:
   *
   *   now       unix seconds (tests pass a fixed clock)
   *   current   the conversation this window is in, marked
   *   query     the search box's text
   *   sort      "recent" (default) or "name"
   *   expanded  {sectionKey: true} for a section the owner opened again
   *   cap       rows per section before "Show N more sessions"
   *
   * Sections, in order: Pinned, one per tag (the tag registry's own order),
   * then Untagged. A section with no chats is left out; while searching,
   * every section is open and uncapped and the empty ones go too.
   */
  function buildSections(list, tags, opts) {
    opts = opts || {};
    var now = num(opts.now, Math.floor(Date.now() / 1000));
    var cap = num(opts.cap, CAP) > 0 ? num(opts.cap, CAP) : CAP;
    var sort = opts.sort === "name" ? "name" : "recent";
    var query = norm(opts.query);
    var expanded = opts.expanded && typeof opts.expanded === "object" ? opts.expanded : {};
    var current = text(opts.current);

    var rows = [];
    (Array.isArray(list) ? list : []).forEach(function (c) {
      if (!c || typeof c !== "object" || !text(c.id)) return;
      var row = rowOf(c, now, current);
      if (!matches(row, query)) return;
      rows.push(row);
    });

    var registry = [];
    var known = {};
    (Array.isArray(tags) ? tags : []).forEach(function (t) {
      if (!t || typeof t !== "object") return;
      var id = num(t.id, 0);
      if (id <= 0 || known[id]) return;
      known[id] = true;
      registry.push({
        id: id,
        name: text(t.name) || "Tag " + id,
        colour: num(t.colour, 0),
        icon: text(t.icon) || "folder",
        order: num(t.order, id),
      });
    });
    registry.sort(function (a, b) {
      return a.order - b.order || a.id - b.id;
    });
    var byId = {};
    registry.forEach(function (t) {
      byId[t.id] = t;
    });

    var pinned = [];
    var byTag = {};
    var loose = [];
    rows.forEach(function (row) {
      if (row.pinned) {
        pinned.push(row);
      } else if (row.tag_id && byId[row.tag_id]) {
        (byTag[row.tag_id] = byTag[row.tag_id] || []).push(row);
      } else {
        // A chat whose tag is gone from the registry (a tag deleted on the
        // phone mid-read) is shown unfiled rather than lost.
        loose.push(row);
      }
    });

    var sections = [];
    function add(key, title, icon, kind, colour, group, tagId) {
      if (!group.length) return;
      // The Pinned group is ordered by the pin itself, never by the button.
      var sorted = sortRows(group, key === "pinned" ? "pinned" : sort);
      var open = query ? true : expanded[key] !== false;
      // "Show N more sessions" is a one-off expansion (the `!` key), so a
      // section the owner opened once does not quietly stay unbounded.
      var uncapped = query || expanded["!" + key] === true;
      var shown = open ? (uncapped ? sorted : sorted.slice(0, cap)) : [];
      sections.push({
        key: key,
        title: title,
        icon: icon,
        kind: kind,
        colour: colour,
        tag_id: tagId === undefined ? null : tagId,
        count: group.length,
        open: open,
        rows: shown,
        more: open && !uncapped ? Math.max(0, sorted.length - shown.length) : 0,
      });
    }

    add("pinned", PINNED, "pin", "pinned", 0, pinned);
    registry.forEach(function (t) {
      add("tag:" + t.id, t.name, t.icon, "tag", t.colour, byTag[t.id] || [], t.id);
    });
    add("none", UNTAGGED, "inbox", "none", 0, loose);
    return sections;
  }

  /** How many chats the panel is showing, across every section. */
  function countRows(sections) {
    var n = 0;
    (Array.isArray(sections) ? sections : []).forEach(function (s) {
      n += num(s && s.count, 0);
    });
    return n;
  }

  /* ------------------------------------------------------------------ *
   * The glyphs - the page's own 24-unit grid, stroke=currentColor
   * ------------------------------------------------------------------ */

  /** The ten tag icons of docs/CHAT-TAGS-DESIGN.md, plus this panel's own
   *  four: a pin, an inbox (untagged), a clock (the rail button) and the
   *  kind marks. Each value is the `d` of one 24-unit stroke path. */
  var PATHS = {
    briefcase: "M3 8h18v11H3zM9 8V6h6v2",
    book: "M5 4h9a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM17 7h2v13",
    home: "M4 11 12 4l8 7M6 10v10h12V10",
    folder: "M4 6h6l2 2h8v10H4z",
    lightbulb: "M9 18h6M10 21h4M12 3a6 6 0 0 0-3 11v2h6v-2a6 6 0 0 0-3-11z",
    star: "M12 3.5l2.7 5.6 6 .8-4.4 4.2 1.1 6-5.4-2.9-5.4 2.9 1.1-6L3.3 9.9l6-.8z",
    flag: "M6 3v18M6 4h11l-1.6 3.5L17 11H6",
    wrench: "M14.5 4a5 5 0 0 0-4 7.6L4 18.1 5.9 20l6.5-6.5A5 5 0 0 0 20 9.5l-3 1.2-1.7-1.7z",
    leaf: "M5 19c0-8 6-13 14-13 0 8-5 14-13 14M5 19c2-4 5-6 9-7",
    music: "M9 18V6l10-2v12M9 18a3 3 0 1 1-3-3 3 3 0 0 1 3 3zM19 16a3 3 0 1 1-3-3 3 3 0 0 1 3 3z",
    pin: "M14 3l7 7-4 1-1 4-6-6 1-1-1-4zM9 15l-6 6",
    inbox: "M4 6h16v12H4zM4 13h4l1 2h6l1-2h4",
    clock: "M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18zM12 7v5l3 2",
    chat: "M4 5h16v11H9l-5 4z",
    live: "M4 10v4M8 7v10M12 4v16M16 7v10M20 10v4",
    support: "M4 13a8 8 0 0 1 16 0M4 13v4a2 2 0 0 0 2 2h1v-6H6a2 2 0 0 0-2 2zM20 13v4a2 2 0 0 1-2 2h-1v-6h1a2 2 0 0 1 2 2z",
    chatbot: "M5 8h14v9H5zM9 12h.01M15 12h.01M12 4v4",
    compare: "M4 5h7v14H4zM13 5h7v14h-7z",
    more: "M6 12h.01M12 12h.01M18 12h.01",
    search: "M11 19a8 8 0 1 1 0-16 8 8 0 0 1 0 16zM21 21l-4.5-4.5",
    sort: "M4 7h16M4 12h10M4 17h6",
    plus: "M12 5v14M5 12h14",
    close: "M6 6l12 12M18 6L6 18",
    chevron: "M9 6l6 6-6 6",
  };

  /** The ten tag icons the shared contract names, in its order. */
  var TAG_ICONS = ["briefcase", "book", "home", "folder", "lightbulb", "star", "flag",
    "wrench", "leaf", "music"];
  /** The conversation kinds the PC keeps (jarvis_chat_log.KINDS). */
  var ICON_KINDS = ["chat", "live", "support", "chatbot", "compare"];

  /** The `d` for one glyph, or the chat bubble for a name this build does
   *  not know (a newer PC's tag icon lands on a safe shape, never a hole). */
  function glyphPath(name) {
    var key = text(name);
    return PATHS[key] || PATHS.chat;
  }

  /* ------------------------------------------------------------------ *
   * The panel
   * ------------------------------------------------------------------ */

  var mounted = null;

  function el(tag, cls, words) {
    var node = root.document.createElement(tag);
    if (cls) node.className = cls;
    if (words !== undefined && words !== null) node.textContent = text(words);
    return node;
  }

  function icon(name, cls) {
    var ns = "http://www.w3.org/2000/svg";
    var svg = root.document.createElementNS(ns, "svg");
    svg.setAttribute("class", "glyph" + (cls ? " " + cls : ""));
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "1.8");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    var path = root.document.createElementNS(ns, "path");
    path.setAttribute("d", glyphPath(name));
    svg.appendChild(path);
    return svg;
  }

  var STYLE_ID = "hud-history-style";
  var CSS = [
    "html.hh-open, html.hh-open body{overflow:hidden;}",
    "#hh-backdrop{position:fixed;inset:0;z-index:88;background:rgba(4,6,9,.44);opacity:0;",
    " pointer-events:none;transition:opacity .16s ease;}",
    "#hh-backdrop.hh-on{opacity:1;pointer-events:auto;}",
    ".hh-panel{position:fixed;top:0;left:0;bottom:0;z-index:89;width:304px;max-width:86vw;",
    " display:flex;flex-direction:column;background:#14161b;color:#e6e8ec;",
    " border-right:1px solid rgba(255,255,255,.09);box-shadow:18px 0 40px rgba(0,0,0,.45);",
    " font-family:var(--font-ui,\"Segoe UI\",system-ui,sans-serif);",
    " font-size:13px;line-height:1.35;transform:translateX(-104%);",
    " transition:transform .18s var(--ease, ease);visibility:hidden;}",
    ".hh-panel.hh-on{transform:none;visibility:visible;}",
    "#hh-head{display:flex;align-items:center;gap:6px;padding:12px 12px 6px;}",
    "#hh-title{flex:1 1 auto;margin:0;font-size:15px;font-weight:600;letter-spacing:.01em;}",
    ".hh-ico{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;",
    " padding:0;border:0;border-radius:7px;background:transparent;color:#aab0ba;cursor:pointer;}",
    ".hh-ico:hover,.hh-ico:focus-visible{background:rgba(255,255,255,.08);color:#fff;outline:none;}",
    ".hh-ico[aria-pressed=\"true\"]{color:#7fe9ff;background:rgba(56,240,255,.12);}",
    "#hh-search{margin:2px 12px 8px;display:flex;align-items:center;gap:7px;",
    " padding:0 9px;height:32px;border-radius:8px;background:rgba(255,255,255,.055);",
    " border:1px solid rgba(255,255,255,.06);}",
    "#hh-search svg{width:15px;height:15px;color:#7c838e;flex:0 0 auto;}",
    "#hh-search input{flex:1 1 auto;min-width:0;border:0;background:transparent;color:#e6e8ec;",
    " font:inherit;font-size:12.5px;outline:none;}",
    "#hh-search input::placeholder{color:#7c838e;}",
    "#hh-body{flex:1 1 auto;overflow-y:auto;overflow-x:hidden;padding:2px 8px 14px;",
    " scrollbar-width:thin;}",
    ".hh-sec{margin-top:6px;}",
    ".hh-head{display:flex;align-items:center;gap:7px;width:100%;height:26px;padding:0 6px;",
    " border:0;border-radius:6px;background:transparent;color:#9aa1ac;font:inherit;",
    " font-size:11.5px;font-weight:600;letter-spacing:.02em;text-transform:none;cursor:pointer;",
    " text-align:left;}",
    ".hh-head:hover,.hh-head:focus-visible{background:rgba(255,255,255,.06);color:#d3d8df;outline:none;}",
    ".hh-head .glyph{width:13px;height:13px;flex:0 0 auto;transition:transform .14s ease;}",
    ".hh-sec[data-open=\"0\"] .hh-head .glyph.hh-caret{transform:rotate(-90deg);}",
    ".hh-name{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}",
    ".hh-count{flex:0 0 auto;color:#6f7681;font-weight:500;}",
    ".hh-rows{margin:1px 0 0;padding:0;list-style:none;}",
    ".hh-item{position:relative;display:flex;align-items:center;gap:1px;}",
    ".hh-open{display:flex;align-items:center;gap:7px;flex:1 1 auto;min-width:0;padding:5px 2px 5px 7px;",
    " margin:0;border:0;border-radius:7px;background:transparent;color:#cfd4dc;font:inherit;",
    " font-size:12.5px;cursor:pointer;text-align:left;}",
    ".hh-open:hover,.hh-open:focus-visible{background:rgba(255,255,255,.07);color:#fff;outline:none;}",
    ".hh-open[aria-current=\"true\"]{background:rgba(56,240,255,.11);color:#eafcff;}",
    ".hh-open[aria-current=\"true\"] .hh-t{font-weight:600;}",
    ".hh-open .glyph{width:13px;height:13px;flex:0 0 auto;color:#8b929d;}",
    ".hh-open[aria-current=\"true\"] .glyph{color:#7fe9ff;}",
    ".hh-t{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}",
    ".hh-age{flex:0 0 auto;color:#767d88;font-size:11px;font-variant-numeric:tabular-nums;}",
    ".hh-dots{flex:0 0 auto;width:20px;height:20px;padding:0;border:0;border-radius:5px;",
    " background:transparent;color:#8b929d;cursor:pointer;opacity:0;}",
    ".hh-item:hover .hh-dots,.hh-item:focus-within .hh-dots{opacity:1;}",
    ".hh-dots:hover,.hh-dots:focus-visible,.hh-dots[aria-expanded=\"true\"]{",
    " background:rgba(255,255,255,.12);color:#fff;outline:none;opacity:1;}",
    ".hh-more{display:block;width:100%;margin:0;padding:4px 7px;border:0;border-radius:7px;",
    " background:transparent;color:#8a919c;font:inherit;font-size:11.5px;text-align:left;cursor:pointer;}",
    ".hh-more:hover,.hh-more:focus-visible{background:rgba(255,255,255,.06);color:#e6e8ec;outline:none;}",
    "#hh-foot{flex:0 0 auto;border-top:1px solid rgba(255,255,255,.07);padding:8px 12px 10px;",
    " display:flex;flex-direction:column;gap:6px;}",
    "#hh-say{margin:0;color:#8a919c;font-size:11.5px;min-height:0;}",
    "#hh-say:empty{display:none;}",
    "#hh-new{display:flex;align-items:center;gap:7px;width:100%;padding:7px 9px;border:0;",
    " border-radius:8px;background:rgba(56,240,255,.13);color:#bff6ff;font:inherit;font-size:12.5px;",
    " cursor:pointer;}",
    "#hh-new:hover,#hh-new:focus-visible{background:rgba(56,240,255,.2);outline:none;}",
    ".hh-menu{position:fixed;z-index:90;min-width:186px;padding:5px;border-radius:9px;",
    " background:#1b1e24;border:1px solid rgba(255,255,255,.1);box-shadow:0 14px 32px rgba(0,0,0,.5);",
    " display:flex;flex-direction:column;}",
    ".hh-menu[hidden]{display:none;}",
    ".hh-menu button{display:flex;align-items:center;gap:8px;width:100%;padding:7px 9px;border:0;",
    " border-radius:6px;background:transparent;color:#dfe3e9;font:inherit;font-size:12.5px;",
    " text-align:left;cursor:pointer;}",
    ".hh-menu button:hover,.hh-menu button:focus-visible{background:rgba(255,255,255,.09);outline:none;}",
    ".hh-menu button[data-danger=\"1\"]{color:#ff9aa6;}",
    ".hh-menu .hh-sep{height:1px;margin:4px 6px;background:rgba(255,255,255,.09);}",
    ".hh-menu .hh-mtext{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;",
    " white-space:nowrap;}",
    ".hh-menu .hh-note{padding:2px 9px 6px;color:#8a919c;font-size:11px;}",
    ".hh-tagdot{width:8px;height:8px;border-radius:50%;flex:0 0 auto;}",
  ].join("");

  function ensureStyle() {
    var doc = root.document;
    if (doc.getElementById(STYLE_ID)) return;
    var style = doc.createElement("style");
    style.id = STYLE_ID;
    style.textContent = CSS;
    (doc.head || doc.documentElement).appendChild(style);
  }

  function tagDots(colour) {
    var palette = ["#5aa9ff", "#5ad2a0", "#ffd166", "#ff8fa3", "#b48cff", "#7fe9ff",
      "#ffa95a", "#9aa1ac"];
    var i = num(colour, 0) % palette.length;
    return palette[i < 0 ? 0 : i];
  }

  /**
   * Draw the panel, and wire it. `host` is the page's own three functions
   * (see the top of this file); without one, Open and New chat explain
   * themselves instead of doing nothing.
   */
  function mount(host) {
    if (mounted) return mounted;
    var doc = root.document;
    if (!doc || !doc.getElementById) return null;
    var bar = doc.getElementById("rail-toolbar");
    if (!bar) return null;
    ensureStyle();

    var talk = host && typeof host === "object" ? host : {};
    var state = {
      open: false,
      sort: lsGet(LS_SORT) === "name" ? "name" : "recent",
      query: "",
      expanded: lsJson(LS_COLLAPSED),
      list: [],
      tags: [],
      meta: null,
      error: "",
      busy: false,
      current: "",
      menu: null,
      // The `...` button that opened the row menu: focus goes back to it when
      // the menu is closed with Escape.
      menuAnchor: null,
    };

    /* The column icon, beside Presets and Live. */
    var railBtn = el("button", "rail-toolbar-btn");
    railBtn.type = "button";
    railBtn.id = "rail-history";
    railBtn.title = "History: every conversation kept on this PC";
    railBtn.setAttribute("aria-label", "History: your conversations on this PC");
    railBtn.setAttribute("aria-haspopup", "dialog");
    railBtn.setAttribute("aria-expanded", "false");
    railBtn.appendChild(icon("clock"));
    railBtn.appendChild(el("span", "rt-label", "History"));
    bar.insertBefore(railBtn, bar.firstChild);

    var backdrop = el("div");
    backdrop.id = "hh-backdrop";
    backdrop.hidden = false;

    var panel = el("section", "hh-panel");
    // `#history-sidebar` is the id the page's Space push-to-talk guard names
    // (the Gemini ruling of 2026-10-27): while the sidebar is up, Space belongs
    // to it and must never start the microphone.
    panel.id = "history-sidebar";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-labelledby", "hh-title");
    panel.setAttribute("aria-modal", "false");

    var head = el("div");
    head.id = "hh-head";
    var title = el("h2", null, "History");
    title.id = "hh-title";
    var sortBtn = el("button", "hh-ico");
    sortBtn.type = "button";
    sortBtn.id = "hh-sort";
    sortBtn.appendChild(icon("sort"));
    var newBtn = el("button", "hh-ico");
    newBtn.type = "button";
    newBtn.id = "hh-new-top";
    newBtn.title = "New chat";
    newBtn.setAttribute("aria-label", "New chat");
    newBtn.appendChild(icon("plus"));
    var closeBtn = el("button", "hh-ico");
    closeBtn.type = "button";
    closeBtn.id = "hh-close";
    closeBtn.title = "Close History";
    closeBtn.setAttribute("aria-label", "Close History");
    closeBtn.appendChild(icon("close"));
    head.appendChild(title);
    head.appendChild(sortBtn);
    head.appendChild(newBtn);
    head.appendChild(closeBtn);

    var search = el("div");
    search.id = "hh-search";
    search.appendChild(icon("search"));
    var box = el("input");
    box.type = "search";
    box.id = "hh-query";
    box.placeholder = "Search chats";
    box.setAttribute("aria-label", "Search chats by name");
    box.setAttribute("autocomplete", "off");
    search.appendChild(box);

    var body = el("div");
    body.id = "hh-body";
    var foot = el("div");
    foot.id = "hh-foot";
    var say = el("p");
    say.id = "hh-say";
    say.setAttribute("role", "status");
    say.setAttribute("aria-live", "polite");
    var newRow = el("button", null);
    newRow.type = "button";
    newRow.id = "hh-new";
    newRow.appendChild(icon("plus"));
    newRow.appendChild(el("span", null, "New chat"));
    foot.appendChild(say);
    foot.appendChild(newRow);

    panel.appendChild(head);
    panel.appendChild(search);
    panel.appendChild(body);
    panel.appendChild(foot);
    (doc.body || doc.documentElement).appendChild(backdrop);
    (doc.body || doc.documentElement).appendChild(panel);

    var menu = el("div");
    menu.className = "hh-menu";
    menu.hidden = true;
    menu.setAttribute("role", "menu");
    (doc.body || doc.documentElement).appendChild(menu);

    function announce(words) {
      say.textContent = text(words);
    }

    function paintSort() {
      var name = state.sort === "name";
      sortBtn.setAttribute("aria-pressed", name ? "true" : "false");
      sortBtn.title = name ? "Sorted A to Z (click for newest first)"
        : "Newest first (click for A to Z)";
      sortBtn.setAttribute("aria-label", sortBtn.title);
    }

    function setOpen(on) {
      state.open = !!on;
      panel.classList.toggle("hh-on", state.open);
      backdrop.classList.toggle("hh-on", state.open);
      doc.documentElement.classList.toggle("hh-open", state.open);
      railBtn.setAttribute("aria-expanded", state.open ? "true" : "false");
      if (!state.open) {
        closeMenu(false);
        // Closing leaves the keyboard on the rail icon that opened the panel:
        // Escape from anywhere in it comes back here, not to the top of the
        // page (the Gemini ruling of 2026-10-27).
        var active = doc.activeElement;
        if (!active || active === doc.body || active === doc.documentElement ||
            panel.contains(active)) {
          railBtn.focus();
        }
        return;
      }
      refresh();
      box.focus();
    }

    /* ---- the reads ---- */

    function readJson(path) {
      // In the desktop shell `window.fetch` is hud_bootstrap's shim: a GET
      // goes to Rust's `hud_get`, which adds the token and allows only the
      // reads on its list. In a browser this is an ordinary same-origin GET
      // with this page's own token/cookie. One code path, either way.
      return root.fetch(path, {
        cache: "no-store",
        headers: { "X-Jarvis-Client": "hud" },
      }).then(function (res) {
        if (!res || !res.ok) {
          throw new Error("the PC answered " + ((res && res.status) || "nothing"));
        }
        return res.json();
      });
    }

    function load() {
      state.error = "";
      announce("Reading your chats…");
      return Promise.all([
        readJson("/api/history?limit=" + MAX_ROWS),
        readJson("/api/history/tags").catch(function () {
          // Tags are a newer route than History (2026-09-30): a PC that
          // cannot answer it still lists chats, just with no sections.
          return { tags: [] };
        }),
      ]).then(function (answers) {
        var list = answers[0] && typeof answers[0] === "object" ? answers[0] : {};
        var tags = answers[1] && typeof answers[1] === "object" ? answers[1] : {};
        state.list = Array.isArray(list.conversations) ? list.conversations : [];
        state.meta = list;
        state.tags = Array.isArray(tags.tags) ? tags.tags : [];
        paint();
      }, function (error) {
        state.list = [];
        state.tags = [];
        state.error = String((error && error.message) || error);
        paint();
      });
    }

    function refresh() {
      if (state.busy) return Promise.resolve();
      state.busy = true;
      return load().then(function () {
        state.busy = false;
      }, function () {
        state.busy = false;
      });
    }

    /* ---- the paint ---- */

    function sections() {
      return buildSections(state.list, state.tags, {
        now: Math.floor(Date.now() / 1000),
        current: state.current || (typeof talk.current === "function" ? talk.current() : ""),
        query: state.query,
        sort: state.sort,
        expanded: state.expanded,
        cap: CAP,
      });
    }

    /** One chat's time as the `datetime` a `<time>` wants (ISO 8601), or ""
     *  for a chat with no time of its own - a `<time>` with no datetime would
     *  be a date invented by the page. */
    function isoOf(seconds) {
      var n = num(seconds, 0);
      if (!(n > 0)) return "";
      var d = new Date(n * 1000);
      return isFinite(d.getTime()) ? d.toISOString() : "";
    }

    /**
     * ONE row: a `<div role="listitem">` holding TWO SIBLING buttons - the chat
     * and its `...` - never a button inside a button (the Gemini ruling of
     * 2026-10-27): a nested button is invalid, a keyboard cannot reach it the
     * way a button should be reached, and a click on it reads as a click on the
     * row. Two siblings means Tab stops on the chat and then on its menu, and
     * Space on either is that button's own Space - which is what lets the
     * page's push-to-talk key bail out for `#history-sidebar` safely.
     */
    function rowItem(row) {
      var item = el("div", "hh-item");
      item.setAttribute("role", "listitem");
      var button = el("button", "hh-open");
      button.type = "button";
      button.setAttribute("data-id", row.id);
      var label = row.title + (row.ageLong ? ", " + row.ageLong : "");
      if (row.pinned) label += ", pinned";
      button.setAttribute("aria-label", label);
      button.appendChild(icon(ICON_KINDS.indexOf(row.kind) >= 0 ? row.kind : "chat"));
      button.appendChild(el("span", "hh-t", row.title));
      // A real <time>: the short words for the eye ("7d"), the ISO moment for
      // anything reading the markup, the long words on hover. Hidden from a
      // screen reader because the row's own name already says the age, and a
      // clock that is ahead of the PC is clamped by `ageWords`, so no row can
      // say "in 3 minutes".
      var age = el("time", "hh-age", row.age);
      var when = isoOf(row.updated);
      if (when) age.setAttribute("datetime", when);
      if (row.ageLong) age.setAttribute("title", row.ageLong);
      age.setAttribute("aria-hidden", "true");
      button.appendChild(age);
      if (row.current) button.setAttribute("aria-current", "true");
      button.addEventListener("click", function () {
        openChat(row);
      });
      button.addEventListener("contextmenu", function (event) {
        event.preventDefault();
        openMenu(row, dots);
      });
      var dots = el("button", "hh-dots");
      dots.type = "button";
      dots.setAttribute("aria-label", "More for " + row.title);
      dots.setAttribute("aria-haspopup", "menu");
      dots.setAttribute("aria-expanded", "false");
      dots.appendChild(icon("more"));
      dots.addEventListener("click", function (event) {
        event.stopPropagation();
        openMenu(row, dots);
      });
      item.appendChild(button);
      item.appendChild(dots);
      return item;
    }

    function paint() {
      paintSort();
      body.textContent = "";
      var groups = sections();
      var total = countRows(groups);

      if (state.error) {
        announce("Your chats could not be read: " + state.error);
      } else if (state.meta && state.meta.hidden === true) {
        // The PC's own redaction: Windows Hello has not been given, so there
        // is nothing here to show and the panel says so rather than a blank.
        announce(
          "Your chat history is hidden. Press Show on the Brain's History tab and confirm it is " +
            "you with Windows Hello first."
        );
      } else if (state.meta && (state.meta.enabled === false || state.meta.recording === false)) {
        announce(
          text(state.meta.why_not) ||
            "Chat history is off on this PC, so nothing new is being kept. What is already kept is " +
              "listed here."
        );
      } else if (!groups.length) {
        announce(state.query ? "No chat has that in its name." : "No chats are kept on this PC yet.");
      } else {
        announce(total + (total === 1 ? " chat" : " chats") + " on this PC.");
      }

      groups.forEach(function (section) {
        var wrap = el("div", "hh-sec");
        wrap.setAttribute("data-open", section.open ? "1" : "0");
        wrap.setAttribute("data-key", section.key);
        var headBtn = el("button", "hh-head");
        headBtn.type = "button";
        headBtn.setAttribute("aria-expanded", section.open ? "true" : "false");
        headBtn.setAttribute(
          "aria-label",
          section.title + ", " + section.count + (section.count === 1 ? " chat" : " chats") +
            (section.open ? "" : ", collapsed")
        );
        var caret = icon("chevron", "hh-caret");
        headBtn.appendChild(caret);
        if (section.kind === "tag") {
          var dot = el("span", "hh-tagdot");
          dot.style.background = tagDots(section.colour);
          dot.setAttribute("aria-hidden", "true");
          headBtn.appendChild(dot);
        } else {
          headBtn.appendChild(icon(section.icon));
        }
        headBtn.appendChild(el("span", "hh-name", section.title));
        headBtn.appendChild(el("span", "hh-count", String(section.count)));
        headBtn.addEventListener("click", function () {
          var open = section.open;
          if (open) state.expanded[section.key] = false;
          else delete state.expanded[section.key];
          lsSet(LS_COLLAPSED, JSON.stringify(state.expanded));
          paint();
          // paint() empties #hh-body, so the header that was just pressed no
          // longer exists and the keyboard would drop to the top of the page.
          // Put it back on the SAME section's header (the Gemini ruling of
          // 2026-10-27: this panel's own repaint never loses the keyboard).
          var again = body.querySelector(
            '.hh-sec[data-key="' + section.key + '"] .hh-head'
          );
          if (again && again.focus) again.focus();
        });
        wrap.appendChild(headBtn);

        // A list of `div[role="listitem"]` rows, not an <ul> of buttons: the
        // listitem is what a screen reader announces, and it holds the chat's
        // own button beside its menu button (see `rowItem`).
        var rows = el("div", "hh-rows");
        rows.setAttribute("role", "list");
        section.rows.forEach(function (row) {
          rows.appendChild(rowItem(row));
        });
        wrap.appendChild(rows);
        // "Show N more sessions" is a CONTROL beside the list, not a row in
        // it: a `role="list"` may hold only listitems, so a button inside one
        // is both invalid markup and read out as if it were a chat.
        if (section.more > 0) {
          var more = el("button", "hh-more");
          more.type = "button";
          more.textContent = "Show " + section.more + " more session" + (section.more === 1 ? "" : "s");
          // How many rows this section is showing now: the first NEW one is at
          // that index after the repaint, and it is where focus goes.
          var shownBefore = section.rows.length;
          more.addEventListener("click", function () {
            state.expanded[section.key] = true;
            // "Show more" is a one-off expansion: it is remembered only for
            // this visit, so a section does not quietly become unbounded on
            // every open. Collapsing and expanding again restores the cap.
            state.expanded["!" + section.key] = true;
            lsSet(LS_COLLAPSED, JSON.stringify(pickRemembered(state.expanded)));
            paint();
            // Focus the FIRST chat the click revealed, so a keyboard user lands
            // where the new rows begin instead of back at the top of them (the
            // Gemini ruling of 2026-10-27).
            var sec = body.querySelector('.hh-sec[data-key="' + section.key + '"]');
            var items = sec ? sec.querySelectorAll(".hh-item .hh-open") : [];
            var target = items[shownBefore] || items[items.length - 1];
            if (target && target.focus) target.focus();
          });
          wrap.appendChild(more);
        }
        body.appendChild(wrap);
      });
    }

    /** Only the COLLAPSED flags are remembered across restarts; a one-off
     *  "Show N more" expansion is not. */
    function pickRemembered(expanded) {
      var out = {};
      Object.keys(expanded).forEach(function (key) {
        if (key.charAt(0) === "!") return;
        out[key] = expanded[key];
      });
      return out;
    }

    /* ---- the writes ---- */

    /** The ONE command this window may call. Its name is a LITERAL, never
     *  built at runtime: `tools/check_invoke_grants.py` reads every page's
     *  invoke calls and holds the name against `lib.rs`, `build.rs` and the
     *  window's capability, so a name assembled from pieces would be a call
     *  nobody can check. What varies - which action, which chat - is in the
     *  args, and the Rust command refuses anything outside its three actions. */
    function invoke(args) {
      var tauri = root.__TAURI__;
      if (tauri && tauri.core && typeof tauri.core.invoke === "function") {
        return tauri.core.invoke("hud_history_act", args);
      }
      // A browser: the page talks to the backend itself, exactly as the rest
      // of this page does. The route each action is the one the PC documents,
      // and the body comes from `history-actions.js` - the same module the
      // Brain's window reads its words from, so the two cannot drift.
      var paths = {
        pin: "/api/history/pin",
        tag: "/api/history/tag",
        delete: "/api/history/delete",
      };
      var body = actBody(args.action, args.id,
        args.action === "pin" ? args.pinned : args.action === "tag" ? args.tag : null);
      if (!body || !paths[args.action]) {
        return Promise.reject(new Error("That was not a change this window can send."));
      }
      return root.fetch(paths[args.action], {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json", "X-Jarvis-Client": "hud" },
        body: JSON.stringify(body),
      }).then(function (res) {
        if (!res || !res.ok) throw new Error("the PC answered " + ((res && res.status) || "nothing"));
        return res.json();
      });
    }

    function act(action, id, value) {
      var args = actArgs(action, id, value);
      if (!args) {
        announce("That was not a change this window can send.");
        return Promise.resolve(false);
      }
      announce("Saving…");
      return invoke(args).then(function () {
        announce(action === "pin" ? (value ? "Pinned." : "Unpinned.") : "Saved.");
        return refresh().then(function () {
          return true;
        });
      }, function (error) {
        announce(String((error && error.message) || error));
        return false;
      });
    }

    function openChat(row) {
      if (typeof talk.open !== "function") {
        announce("This window cannot open a chat on its own - open the Brain's History tab.");
        return;
      }
      announce("Opening…");
      readJson("/api/history/conversation?id=" + encodeURIComponent(row.id)).then(function (conv) {
        if (!conv || typeof conv !== "object") throw new Error("that chat could not be read");
        if (conv.hidden === true || conv.available === false) {
          announce(
            "Your chat history is hidden. Press Show on the Brain's History tab first."
          );
          return;
        }
        state.current = text(conv.id) || row.id;
        talk.open(conv);
        setOpen(false);
      }, function (error) {
        announce("That chat could not be opened: " + String((error && error.message) || error));
      });
    }

    function newChat() {
      if (typeof talk.newChat !== "function") {
        announce("This window cannot start a new chat on its own - open the Brain's History tab.");
        return;
      }
      talk.newChat();
      state.current = typeof talk.current === "function" ? talk.current() : "";
      setOpen(false);
    }

    /* ---- the row menu ---- */

    /** Shut the row menu. `focusBack` puts the keyboard back on the `...` that
     *  opened it - which is what Escape does (the Gemini ruling of 2026-10-27):
     *  a menu that closes and drops focus at the top of the document loses a
     *  keyboard user's place. A close by clicking elsewhere leaves focus where
     *  the click went. */
    function closeMenu(focusBack) {
      menu.hidden = true;
      if (state.menuAnchor) state.menuAnchor.setAttribute("aria-expanded", "false");
      var anchor = state.menuAnchor;
      state.menu = null;
      state.menuAnchor = null;
      if (focusBack && anchor && anchor.focus) anchor.focus();
    }

    function menuItem(words, glyph, danger) {
      var item = el("button");
      item.type = "button";
      item.setAttribute("role", "menuitem");
      if (danger) item.setAttribute("data-danger", "1");
      item.appendChild(icon(glyph));
      item.appendChild(el("span", "hh-mtext", words));
      return item;
    }

    /** Beside the row it belongs to, kept on screen. The panel is 304px and
     *  the menu 190px, so it opens to the RIGHT of the row and is pulled
     *  back in on a narrow window. */
    function place(box, anchor) {
      var rect = anchor && anchor.getBoundingClientRect
        ? anchor.getBoundingClientRect()
        : { right: 300, top: 80 };
      var width = 190;
      var left = Math.min(rect.right + 4, (root.innerWidth || 1280) - width - 8);
      var top = Math.min(rect.top, (root.innerHeight || 800) - 280);
      box.style.left = Math.max(4, left) + "px";
      box.style.top = Math.max(4, top) + "px";
      box.hidden = false;
    }

    function openMenu(row, anchor) {
      // One menu at a time: a second `...` closes the first before opening its
      // own, and the first one's button forgets it was expanded.
      if (state.menuAnchor) state.menuAnchor.setAttribute("aria-expanded", "false");
      menu.textContent = "";
      var open = menuItem(ACTION_LABELS.open, "chat");
      open.addEventListener("click", function () {
        closeMenu(false);
        openChat(row);
      });
      var pin = menuItem(labelFor("pin", row.pinned), "pin");
      pin.addEventListener("click", function () {
        closeMenu(false);
        act("pin", row.id, !row.pinned);
      });
      var move = menuItem(ACTION_LABELS.move, "folder");
      move.setAttribute("aria-haspopup", "menu");
      move.setAttribute("aria-expanded", "false");
      var sub = el("div");
      sub.className = "hh-menu";
      sub.hidden = true;
      sub.setAttribute("role", "menu");
      var subNote = el("div", "hh-note", state.tags.length ? "One project per chat." : "No projects yet.");
      sub.appendChild(subNote);
      state.tags.forEach(function (t) {
        var pick = el("button");
        pick.type = "button";
        pick.setAttribute("role", "menuitem");
        var dot = el("span", "hh-tagdot");
        dot.style.background = tagDots(t.colour);
        pick.appendChild(dot);
        pick.appendChild(el("span", "hh-mtext", text(t.name) || "Tag " + t.id));
        if (row.tag_id === num(t.id)) pick.setAttribute("aria-current", "true");
        pick.addEventListener("click", function () {
          closeMenu(false);
          act("tag", row.id, num(t.id));
        });
        sub.appendChild(pick);
      });
      var none = el("button");
      none.type = "button";
      none.setAttribute("role", "menuitem");
      none.appendChild(icon("inbox"));
      none.appendChild(el("span", "hh-mtext", ACTION_LABELS.noTag));
      none.addEventListener("click", function () {
        closeMenu(false);
        act("tag", row.id, null);
      });
      sub.appendChild(none);
      move.addEventListener("click", function () {
        sub.hidden = !sub.hidden;
        move.setAttribute("aria-expanded", sub.hidden ? "false" : "true");
      });
      var del = menuItem(ACTION_LABELS.delete, "close", true);
      del.addEventListener("click", function () {
        askDelete(row, anchor);
      });
      var sep = el("div", "hh-sep");
      var add = menuItem(ACTION_LABELS.newChat, "plus");
      add.addEventListener("click", function () {
        closeMenu(false);
        newChat();
      });

      menu.appendChild(open);
      menu.appendChild(pin);
      menu.appendChild(move);
      menu.appendChild(sub);
      menu.appendChild(sep);
      menu.appendChild(del);
      menu.appendChild(add);
      place(menu, anchor);
      state.menu = row.id;
      state.menuAnchor = anchor;
      if (anchor && anchor.setAttribute) anchor.setAttribute("aria-expanded", "true");
      var first = menu.querySelector("button");
      if (first) first.focus();
    }

    /* ---- delete, with the page's own are-you-sure ---- */

    /** The delete confirm, in the menu's own box. The three sentences are the
     *  Brain's own, word for word and in its order (`history-actions.js`: the
     *  Gemini ruling of 2026-10-27 - one confirmation, both windows), only laid
     *  out for this box: there is no `window.confirm` here, because a webview
     *  may not draw one, and a dialog the page cannot see is a delete with no
     *  question at all. */
    function askDelete(row, anchor) {
      menu.textContent = "";
      var note = el(
        "div",
        "hh-note",
        DELETE_QUESTION + " " + DELETE_REMOVES + " " + DELETE_KEEPS_FACTS
      );
      note.setAttribute("id", "hh-del-note");
      var keep = menuItem(ACTION_LABELS.keep, "chat");
      keep.addEventListener("click", function () {
        closeMenu(true);
      });
      var yes = menuItem(ACTION_LABELS.delete, "close", true);
      yes.setAttribute("aria-describedby", "hh-del-note");
      yes.addEventListener("click", function () {
        closeMenu(false);
        act("delete", row.id, null).then(function (ok) {
          if (ok && state.current === row.id) {
            // The chat on screen has just gone: start a fresh one rather than
            // keep a dead id that the next message would be filed under.
            newChat();
          }
        });
      });
      menu.appendChild(note);
      menu.appendChild(yes);
      menu.appendChild(keep);
      place(menu, anchor);
      var first = menu.querySelector("button");
      if (first) first.focus();
    }

    /* ---- wiring ---- */

    railBtn.addEventListener("click", function () {
      setOpen(!state.open);
    });
    closeBtn.addEventListener("click", function () {
      setOpen(false);
    });
    backdrop.addEventListener("click", function () {
      setOpen(false);
    });
    newBtn.addEventListener("click", newChat);
    newRow.addEventListener("click", newChat);
    sortBtn.addEventListener("click", function () {
      state.sort = state.sort === "name" ? "recent" : "name";
      lsSet(LS_SORT, state.sort);
      paint();
    });
    var typing = 0;
    box.addEventListener("input", function () {
      state.query = box.value;
      if (typing) root.clearTimeout(typing);
      typing = root.setTimeout(function () {
        typing = 0;
        paint();
      }, 90);
    });
    panel.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") return;
      event.stopPropagation();
      // Escape in the panel: the row menu first, then the panel itself - and
      // the second Escape puts the keyboard back on the left column's History
      // icon (the Gemini ruling of 2026-10-27).
      if (state.menu) closeMenu(true);
      else setOpen(false);
    });
    // The menu is appended to <body>, not to the panel, so its own Escape does
    // not reach the handler above: this one closes it and returns focus to the
    // `...` that opened it.
    doc.addEventListener("keydown", function (event) {
      if (event.key !== "Escape" || !state.menu) return;
      event.stopPropagation();
      closeMenu(true);
    });
    doc.addEventListener("click", function (event) {
      if (state.menu && menu.contains(event.target)) return;
      if (state.menu) closeMenu(false);
    });

    mounted = {
      el: panel,
      open: function () {
        setOpen(true);
      },
      close: function () {
        setOpen(false);
      },
      isOpen: function () {
        return state.open;
      },
      /** Re-read the PC's list. Called when the window opens and after a
       *  write; also on the page's own beat if it asks. */
      refresh: refresh,
      /** What the panel thinks this window is in, for a test. */
      current: function () {
        return state.current;
      },
    };
    paintSort();
    return mounted;
  }

  /* ------------------------------------------------------------------ *
   * The exported half
   * ------------------------------------------------------------------ */

  var API = {
    CAP: CAP,
    MAX_ROWS: MAX_ROWS,
    UNTAGGED: UNTAGGED,
    PINNED: PINNED,
    // The words and shapes are `history-actions.js`'s (shared with the Brain);
    // passed through so a test - and the page's own push-to-talk guard - can
    // read one table instead of two.
    ACTION_LABELS: ACTION_LABELS,
    DELETE_QUESTION: DELETE_QUESTION,
    DELETE_REMOVES: DELETE_REMOVES,
    DELETE_KEEPS_FACTS: DELETE_KEEPS_FACTS,
    TAG_ICONS: TAG_ICONS,
    ICON_KINDS: ICON_KINDS,
    ageWords: ageWords,
    ageTitle: ageTitle,
    rowOf: rowOf,
    matches: matches,
    sortRows: sortRows,
    buildSections: buildSections,
    countRows: countRows,
    actArgs: actArgs,
    actBody: actBody,
    labelFor: labelFor,
    glyphPath: glyphPath,
    tagDots: tagDots,
    mount: mount,
    /** Is the sidebar on screen? The page's Space push-to-talk asks this: while
     *  it is open, Space belongs to the panel and must never start the mic. */
    isOpen: function () {
      return !!(mounted && mounted.isOpen && mounted.isOpen());
    },
  };
  root.hudHistory = API;

  /* In the page, mount on the first moment the rail exists. The page's own
   * host (`window.hudHistoryHost`) is defined by its last script, which runs
   * before DOMContentLoaded - so by the time this fires, Open and New chat
   * are wired. Without a host the panel still lists and tidies. */
  function autoMount() {
    if (!root.document || !root.document.getElementById) return;
    if (!root.document.getElementById("rail-toolbar")) return;
    mount(root.hudHistoryHost || null);
  }

  if (typeof root.document !== "undefined" && root.document && root.document.getElementById) {
    if (root.document.readyState === "loading") {
      root.document.addEventListener("DOMContentLoaded", autoMount, { once: true });
    } else {
      autoMount();
    }
  }
})(typeof window !== "undefined" ? window : globalThis);
