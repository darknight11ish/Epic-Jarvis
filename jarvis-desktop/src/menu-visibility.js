/**
 * menu-visibility.js - "Show or hide menus": pure module for desktop menu
 * visibility (docs/MENU-VISIBILITY-DESIGN.md, docs/JARVIS-API.md section 109).
 *
 * Holds the menu registry, NEVER_HIDE list, feature groups, and the state
 * machine (hide, show, collapse, expand, reset, sanitize, isHidden, isCollapsed,
 * hiddenCount, visit overrides). Unit-testable in Node with no DOM dependencies.
 */

import {
  VERSION,
  GROUP_PREFIX,
  WORDS,
  REPLIES,
  ACTIONS,
  GROUPS,
  MENUS,
  NEVER_HIDE,
  DEFAULTS,
} from "./menu-catalog.js";

export {
  VERSION,
  GROUP_PREFIX,
  WORDS,
  REPLIES,
  ACTIONS,
  GROUPS,
  MENUS,
  NEVER_HIDE,
  DEFAULTS,
};

const _BY_ID = new Map(MENUS.map((m) => [m.id, m]));
const _GROUP_BY_ID = new Map(
  GROUPS.map((g) => [g.id.startsWith(GROUP_PREFIX) ? g.id.slice(GROUP_PREFIX.length) : g.id, g])
);

export function menu(id) {
  return _BY_ID.get(id) || null;
}

export function isGroupId(id) {
  if (typeof id !== "string") return false;
  if (id.startsWith(GROUP_PREFIX)) {
    return _GROUP_BY_ID.has(id.slice(GROUP_PREFIX.length));
  }
  return false;
}

export function has(m, app = null) {
  if (!m) return false;
  if (app === null) return true;
  return Array.isArray(m.apps) ? m.apps.includes(app) : false;
}

export function members(groupOrId, app = null) {
  if (typeof groupOrId !== "string") return [];
  const gid = groupOrId.startsWith(GROUP_PREFIX)
    ? groupOrId.slice(GROUP_PREFIX.length)
    : groupOrId;
  const full = GROUP_PREFIX + gid;
  return MENUS.filter(
    (m) => (m.group === gid || m.group === full) && has(m, app)
  ).map((m) => m.id);
}

export function children(id) {
  return MENUS.filter((m) => m.parent === id).map((m) => m.id);
}

export function ancestors(id) {
  const out = [];
  let m = _BY_ID.get(id);
  while (m && m.parent) {
    out.push(m.parent);
    m = _BY_ID.get(m.parent);
  }
  return out;
}

export function coverMembers(cover) {
  return isGroupId(cover) ? members(cover, null) : children(cover);
}

export function known(id, app = null) {
  if (isGroupId(id)) return members(id, app).length > 0;
  const m = _BY_ID.get(id);
  return m !== undefined && has(m, app);
}

export function titleOf(id) {
  if (isGroupId(id)) {
    const gid = id.startsWith(GROUP_PREFIX) ? id.slice(GROUP_PREFIX.length) : id;
    const g = _GROUP_BY_ID.get(gid);
    return g ? g.title : id;
  }
  const m = _BY_ID.get(id);
  return m ? m.title : id;
}

export class State {
  constructor(hidden = new Set(), collapsed = new Set()) {
    this.hidden = new Set(hidden);
    this.collapsed = new Set(collapsed);
  }

  as_dict() {
    return {
      hidden: [...this.hidden].sort(),
      collapsed: [...this.collapsed].sort(),
    };
  }

  static of(d) {
    if (!d) return new State();
    return new State(d.hidden || [], d.collapsed || []);
  }
}

export function sanitize(state, app = null) {
  const hidden = new Set();
  for (const i of state.hidden) {
    if (isGroupId(i)) {
      if (members(i, app).length > 0) hidden.add(i);
    } else {
      const m = _BY_ID.get(i);
      if (m && m.hide && has(m, app)) hidden.add(i);
    }
  }
  const collapsed = new Set();
  for (const i of state.collapsed) {
    const m = _BY_ID.get(i);
    if (m && m.collapse && has(m, app)) collapsed.add(i);
  }
  return new State(hidden, collapsed);
}

export function isHidden(state, id, visit = new Set()) {
  const m = _BY_ID.get(id);
  if (!m || !m.hide) return false;
  if (visit && (visit.has ? visit.has(id) : visit.includes(id))) return false;
  if (state.hidden.has(id)) return true;
  if (m.group) {
    const gid = m.group.startsWith(GROUP_PREFIX) ? m.group : GROUP_PREFIX + m.group;
    if (state.hidden.has(gid)) return true;
  }
  if (m.parent) {
    return isHidden(state, m.parent, visit);
  }
  return false;
}

export function isCollapsed(state, id, visit = new Set()) {
  const m = _BY_ID.get(id);
  const onVisit = visit && (visit.has ? visit.has(id) : visit.includes(id));
  return Boolean(m && m.collapse && state.collapsed.has(id) && !onVisit);
}

export function hiddenCount(state, app = "desktop") {
  let n = 0;
  for (const g of GROUPS) {
    const gid = g.id.startsWith(GROUP_PREFIX) ? g.id : GROUP_PREFIX + g.id;
    if (state.hidden.has(gid) && members(g.id, app).length > 0) {
      n += 1;
    }
  }
  for (const m of MENUS) {
    if (!has(m, app) || !m.hide) continue;
    if (!state.hidden.has(m.id)) continue;
    if (m.group) {
      const gid = m.group.startsWith(GROUP_PREFIX) ? m.group : GROUP_PREFIX + m.group;
      if (state.hidden.has(gid)) continue;
    }
    if (m.parent && isHidden(state, m.parent)) continue;
    n += 1;
  }
  return n;
}

export function hide(state, id, app = null) {
  if (isGroupId(id)) {
    if (members(id, app).length === 0) return "unknown";
    state.hidden.add(id);
    for (const mem of members(id, null)) {
      state.hidden.delete(mem);
    }
    return "ok";
  }
  const m = _BY_ID.get(id);
  if (!m || !has(m, app)) return "unknown";
  if (!m.hide) return "never";
  state.hidden.add(id);
  return "ok";
}

export function show(state, id, app = null) {
  if (isGroupId(id)) {
    if (members(id, app).length === 0) return "unknown";
    state.hidden.delete(id);
    for (const mem of members(id, null)) {
      state.hidden.delete(mem);
    }
    return "ok";
  }
  const m = _BY_ID.get(id);
  if (!m || !has(m, app)) return "unknown";
  state.hidden.delete(id);
  const covers = (m.group ? [m.group.startsWith(GROUP_PREFIX) ? m.group : GROUP_PREFIX + m.group] : []).concat(
    ancestors(id)
  );
  const mine = ancestors(id);
  for (const cover of covers) {
    if (state.hidden.has(cover)) {
      state.hidden.delete(cover);
      for (const other of coverMembers(cover)) {
        if (
          other !== id &&
          !mine.includes(other) &&
          !ancestors(other).includes(id) &&
          _BY_ID.get(other)?.hide
        ) {
          state.hidden.add(other);
        }
      }
    }
  }
  return "ok";
}

export function collapse(state, id, app = null) {
  if (isGroupId(id)) {
    const all = members(id, app);
    if (all.length === 0) return "unknown";
    const ids = all.filter((i) => _BY_ID.get(i)?.collapse);
    if (ids.length === 0) return "cannot";
    for (const i of ids) state.collapsed.add(i);
    return "ok";
  }
  const m = _BY_ID.get(id);
  if (!m || !has(m, app)) return "unknown";
  if (!m.collapse) return "cannot";
  state.collapsed.add(id);
  return "ok";
}

export function expand(state, id, app = null) {
  if (isGroupId(id)) {
    if (members(id, app).length === 0) return "unknown";
    for (const mem of members(id, null)) {
      state.collapsed.delete(mem);
    }
    return "ok";
  }
  const m = _BY_ID.get(id);
  if (!m || !has(m, app)) return "unknown";
  state.collapsed.delete(id);
  return "ok";
}

export function reset(state) {
  state.hidden.clear();
  state.collapsed.clear();
  return "ok";
}

export function apply(state, action, id = "", app = null) {
  switch (action) {
    case "hide":
      return hide(state, id, app);
    case "show":
      return show(state, id, app);
    case "collapse":
      return collapse(state, id, app);
    case "expand":
      return expand(state, id, app);
    case "reset":
      return reset(state);
    default:
      return "unknown";
  }
}

export function visitSet(id) {
  if (!_BY_ID.has(id)) return new Set();
  return new Set([id, ...ancestors(id)]);
}

export function loadState(storage = (typeof localStorage !== "undefined" ? localStorage : null), app = "desktop") {
  if (!storage) return new State();
  try {
    const v = storage.getItem(DEFAULTS.storage.desktop.version_key);
    if (v !== null && parseInt(v, 10) !== VERSION) {
      return new State();
    }
    const hRaw = storage.getItem(DEFAULTS.storage.desktop.hidden_key);
    const cRaw = storage.getItem(DEFAULTS.storage.desktop.collapsed_key);
    const hArr = hRaw ? JSON.parse(hRaw) : [];
    const cArr = cRaw ? JSON.parse(cRaw) : [];
    const raw = new State(Array.isArray(hArr) ? hArr : [], Array.isArray(cArr) ? cArr : []);
    return sanitize(raw, app);
  } catch {
    return new State();
  }
}

export function saveState(state, storage = (typeof localStorage !== "undefined" ? localStorage : null), app = "desktop") {
  if (!storage) return;
  try {
    const clean = sanitize(state, app);
    storage.setItem(DEFAULTS.storage.desktop.version_key, String(VERSION));
    storage.setItem(DEFAULTS.storage.desktop.hidden_key, JSON.stringify([...clean.hidden].sort()));
    storage.setItem(DEFAULTS.storage.desktop.collapsed_key, JSON.stringify([...clean.collapsed].sort()));
  } catch {
    /* storage failure, ignore */
  }
}

export function parseRoute(header) {
  let obj = null;
  if (typeof header === "string") {
    try {
      obj = JSON.parse(header);
    } catch {
      return null;
    }
  } else if (header && typeof header === "object") {
    obj = header;
  }
  if (!obj || typeof obj !== "object") return null;
  const r = obj.menu_visibility;
  if (!r || typeof r !== "object" || Array.isArray(r)) return null;
  const { action, target } = r;
  if (!ACTIONS.includes(action) || typeof target !== "string" || !target) {
    return null;
  }
  return { action, target };
}

/**
 * High-level state manager with visit overrides and subscriptions for browser UI.
 */
export function createMenuManager(deps = {}) {
  const storage = deps.storage || (typeof localStorage !== "undefined" ? localStorage : null);
  const app = deps.app || "desktop";
  let state = loadState(storage, app);
  let visit = new Set();
  const listeners = new Set();

  function notify() {
    for (const fn of listeners) {
      try {
        fn(state, visit);
      } catch (err) {
        console.error("menu-visibility listener error", err);
      }
    }
  }

  return {
    getState() {
      return state;
    },
    getVisit() {
      return visit;
    },
    isHidden(id) {
      return isHidden(state, id, visit);
    },
    isCollapsed(id) {
      return isCollapsed(state, id, visit);
    },
    hiddenCount() {
      return hiddenCount(state, app);
    },
    onVisit(id) {
      return visit.has(id) && isHidden(state, id);
    },
    showForVisit(id) {
      const v = visitSet(id);
      for (const item of v) visit.add(item);
      notify();
    },
    clearVisit(id) {
      if (id) {
        const v = visitSet(id);
        for (const item of v) visit.delete(item);
      } else {
        visit.clear();
      }
      notify();
    },
    hide(id) {
      const res = hide(state, id, app);
      saveState(state, storage, app);
      notify();
      return res;
    },
    show(id) {
      const res = show(state, id, app);
      saveState(state, storage, app);
      notify();
      return res;
    },
    collapse(id) {
      const res = collapse(state, id, app);
      saveState(state, storage, app);
      notify();
      return res;
    },
    expand(id) {
      const res = expand(state, id, app);
      saveState(state, storage, app);
      notify();
      return res;
    },
    reset() {
      const res = reset(state);
      visit.clear();
      saveState(state, storage, app);
      notify();
      return res;
    },
    applyRoute(header) {
      const parsed = parseRoute(header);
      if (!parsed) return false;
      const res = apply(state, parsed.action, parsed.target, app);
      saveState(state, storage, app);
      notify();
      return res === "ok";
    },
    reload() {
      state = loadState(storage, app);
      notify();
    },
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
  };
}
