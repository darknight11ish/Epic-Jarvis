/**
 * "What asks first" - the words and the reading of the PC's answer (the
 * owner's decisions of 2026-09-26, after the approvals audit; JARVIS-API.md
 * section 32; backend jarvis_asks_first.py). asks-first-settings.js draws it
 * in Settings; the phone says the same words (net/AsksFirst.kt), and both
 * are checked against tests/fixtures/asks-first-cases.json, made by the real
 * backend.
 *
 * What the owner can do here:
 *  - see every action Jarvis can take and whether it asks first, grouped,
 *    in the PC's own words;
 *  - "Ask me first" on the short safe list: ON makes it stricter, at once,
 *    never held on a stale link; OFF lets it go ahead without asking - on the
 *    PC only, one approval card that needs Windows Hello, held on a stale
 *    link. The PC refuses anything off the list, and so does Rust;
 *  - "Lights, plugs and fans without a card": ON is one approval card (held
 *    on a stale link), OFF is at once.
 *  - Lockdown (2026-09-28): one tap makes every way out of the PC ask first,
 *    or stop. ON is at once, never held (set_asks_first with the action
 *    "lockdown" and ask: true - it only makes Jarvis ask more); OFF is the
 *    PC only, ONE loosening card that needs Windows Hello, held on a stale
 *    link. The phone can turn it on, never off.
 *
 * @module asks-first
 */

/** The page, the PC's words (jarvis_asks_first.py). */
export const TITLE = "What asks first";
export const DETAIL =
  "Everything Jarvis can do that might need your OK, and whether it asks you first. " +
  "The PC writes this list from its own settings - the AI model does not write it. " +
  "\"Ask me first\" makes one ask every time, at once, from either app. Letting one " +
  "go ahead without asking is only for the short list below, only on the PC, and " +
  "takes an approval card and Windows Hello.";
export const MISSING =
  "Your PC's Jarvis cannot show what asks first yet - run apply-patches.ps1 on the PC.";
export const SWITCH_LABEL = "Ask me first";
export const WAITING =
  "Waiting for your yes on the approval card, and Windows Hello, on your PC.";
export const PHONE_LOOSEN =
  "To let this go ahead without asking, use the PC: Settings, What asks first. " +
  "It takes an approval card and Windows Hello.";
export const LIGHTS_LABEL = "Lights, plugs and fans without a card";
export const LIGHTS_DETAIL =
  "When you name a light, plug or fan yourself - \"turn off the kitchen light\" - Jarvis " +
  "switches it without an approval card. Locks, doors, alarms, covers and garage doors " +
  "always ask, each with a card of its own, and so does everything after Jarvis has " +
  "read outside text in the chat. Turning this on shows you an approval card first; " +
  "turning it off happens at once.";
export const LIGHTS_WAITING = "Waiting for your yes on the approval card, on your PC or phone.";

/** The desktop's own line when the PC did not see this request come from itself. */
export const NOT_HERE =
  "Jarvis did not see this request come from the PC itself, so it will not let this go " +
  "ahead without asking from here.";
/** While another loosening card waits: one at a time. */
export const ONE_AT_A_TIME = "Answer the card that is waiting first.";
export const STALE = "Waiting for the link to catch up. Nothing can be sent until it does.";

/** The actions the apps may switch - jarvis_asks_first.SWITCHABLE. */
export const SWITCHABLE = Object.freeze([
  "calendar_read", "email_read", "notes_search", "home_read",
  "append_obsidian_daily", "append_logseq_journal", "create_joplin_note",
  // 2026-10-08: the five rows the audit found running without asking and
  // switchable nowhere. browse_model_catalog (leaves this PC) and
  // rollback_model (the undo for a switch must never wait) stay off the list.
  "read_files_readonly", "read_joplin_note", "read_logseq_page",
  "create_logseq_page", "power_manage",
]);

/**
 * The four reading tools that may be OFFERED to the AI model at all, from
 * the desktop only - jarvis_asks_first.TOOLS_SWITCHABLE. A DIFFERENT thing
 * from SWITCHABLE (above): that is whether an offered tool asks first; this
 * is whether it is offered at all ([tools].enabled). The owner's answer of
 * 2026-09-27: "Reading tools ... can be switched on from the PC app, each
 * with a card plus Windows Hello; other tools stay in the settings file."
 */
export const TOOLS_SWITCHABLE = Object.freeze([
  // Tier A + Tier B (jarvis_asks_first.TOOLS_SWITCHABLE, 2026-10-31 tiered ruling)
  "calendar_read", "notes_search", "append_obsidian_daily", "create_joplin_note",
  "append_logseq_journal", "set_timer", "set_reminder", "todo_add", "todo_done",
  "coming_up", "protect_from_jarvis", "github_search", "send_file_to_phone",
  "email_check", "send_email", "draft_email", "tidy_inbox", "home_read",
  "home_control", "my_spending", "retirement_whatif",
]);
export const TOOLS_LABEL = "Let the AI use this";
export const TOOLS_DETAIL =
  "Whether the AI model is offered each ability at all - a separate thing from whether it " +
  "asks you first, above. Some tools have a switch here; the raw ones and the ones this " +
  "slice leaves alone stay a settings-file choice, listed below. Turning one on shows ONE " +
  "approval card and asks Windows Hello on this PC; turning it off is instant, from either " +
  "app. Nothing here switches two tools at once.";
export const TOOLS_PC_ONLY =
  "Offering a tool to the AI model can only be turned on from the PC (Settings, What asks " +
  "first). It takes one approval card and Windows Hello.";

/** Lockdown (2026-09-28): the PC's words (jarvis_asks_first.py LOCKDOWN_*). */
export const LOCKDOWN_ACTION = "lockdown";
export const LOCKDOWN_LABEL = "Lockdown";
export const LOCKDOWN_DETAIL =
  "One tap makes every way out of this PC ask you first, or stop: web search and research, " +
  "sending or saving email, reading your calendar, email and Home Assistant, your smart " +
  "home, news feeds and \"tell me when\" watches, plug-in programs, cloud AI models, chatbot " +
  "conversations, the online weather behind the animal and checking for tool updates. " +
  "Turning it on is instant, from either app. Turning it off is " +
  "on the PC only, with an approval card and Windows Hello.";
export const LOCKDOWN_ON_SAYS =
  "Lockdown is on: everything that would leave this PC asks you first, and anything that " +
  "runs by itself (\"tell me when\", news, the briefing's calendar and email, chatbot " +
  "conversations, the online weather) has stopped.";
export const LOCKDOWN_OFF_SAYS = "Lockdown is off: everything asks first as your settings say.";
export const LOCKDOWN_ON_LABEL = "Turn on Lockdown";
export const LOCKDOWN_OFF_LABEL = "Turn off Lockdown";
export const LOCKDOWN_PC_ONLY =
  "Lockdown can only be turned off on the PC (Settings, What asks first), with an approval " +
  "card and Windows Hello.";
export const LOCKDOWN_WAITING =
  "Waiting for your yes on the approval card, and Windows Hello, on your PC.";
/** The Jarvis bar's strip while Lockdown is on (index.html #lockdown-strip). */
export const LOCKDOWN_BAR_LABEL = "Lockdown is on";
export const LOCKDOWN_BAR_LINE =
  "Everything that would leave this PC asks you first, and anything that runs by itself has " +
  "stopped. To turn it off: Settings, What asks first.";
export const LOCKDOWN_ROW_NOTE =
  "Lockdown is on, so this asks you first - or stops, if it runs by itself.";

const text = (v) => (typeof v === "string" ? v : "");

function readSwitch(s) {
  if (!s || typeof s !== "object" || typeof s.asks !== "boolean") return null;
  return { asks: s.asks, canLoosen: s.can_loosen === true };
}

function readRow(r) {
  return {
    id: text(r.id),
    action: text(r.action),
    title: text(r.title),
    says: text(r.says),
    note: text(r.note),
    fixed: r.fixed === true,
    lights: r.lights === true,
    lockdown: r.lockdown === true,
    switch: SWITCHABLE.includes(text(r.action)) ? readSwitch(r.switch) : null,
  };
}

function readLights(l) {
  if (!l || typeof l !== "object" || typeof l.on !== "boolean") return null;
  const last = l.last && typeof l.last === "object" ? l.last : null;
  return {
    on: l.on,
    waiting: l.waiting === true,
    last: last ? text(last.message) : "",
    lastOutcome: last ? text(last.outcome) : "",
    why: text(l.why),
  };
}

function readToolItem(i) {
  const last = i.last && typeof i.last === "object" ? i.last : null;
  return {
    id: text(i.id),
    title: text(i.title),
    group: text(i.group),
    on: i.on === true,
    waiting: i.waiting === true,
    last: last ? text(last.message) : "",
    lastOutcome: last ? text(last.outcome) : "",
  };
}

/** `view.lockdown` - Lockdown's state; null from a PC without it. */
function readLockdown(k) {
  if (!k || typeof k !== "object" || typeof k.on !== "boolean") return null;
  const last = k.last && typeof k.last === "object" ? k.last : null;
  return {
    on: k.on,
    waiting: k.waiting === true,
    last: last ? text(last.message) : "",
    lastOutcome: last ? text(last.outcome) : "",
    why: text(k.why),
    says: text(k.says) || (k.on ? LOCKDOWN_ON_SAYS : LOCKDOWN_OFF_SAYS),
    canTurnOff: k.can_turn_off === true,
  };
}

/** `view.tools` - the tiered "Let the AI use this" switches, desktop only. */
function readTools(t) {
  if (!t || typeof t !== "object" || !Array.isArray(t.items)) {
    return { canEnable: false, items: [], groups: [], vault: null, notOffered: null };
  }
  const items = t.items.filter((i) => i && typeof i === "object").map(readToolItem);
  const groups = Array.isArray(t.groups)
    ? t.groups.filter((g) => g && typeof g === "object")
      .map((g) => ({ title: text(g.title), ids: Array.isArray(g.ids) ? g.ids.map(text) : [] }))
    : [];
  const v = t.vault && typeof t.vault === "object" ? t.vault : null;
  const vault = v ? {
    id: text(v.id) || "vault_organizer",
    kind: text(v.kind) || "switch",
    title: text(v.title),
    group: text(v.group),
    what: text(v.what),
    on: v.on === true,
    waiting: v.waiting === true,
    canEnable: v.can_enable === true,
    last: v.last && typeof v.last === "object" ? text(v.last.message) : "",
    lastOutcome: v.last && typeof v.last === "object" ? text(v.last.outcome) : "",
  } : null;
  const n = t.not_offered && typeof t.not_offered === "object" ? t.not_offered : null;
  const labels = n && n.labels && typeof n.labels === "object" ? n.labels : {};
  const notOffered = n ? {
    tierC: Array.isArray(n.tier_c) ? n.tier_c.map(text) : [],
    notThisSlice: Array.isArray(n.not_this_slice) ? n.not_this_slice.map(text) : [],
    labels: Object.fromEntries(Object.entries(labels).map(([k, v]) => [k, text(v)])),
    why: text(n.why),
  } : null;
  return { canEnable: t.can_enable === true, items, groups, vault, notOffered };
}

/**
 * `get_asks_first`'s answer, read. `available: false` with `why` from a PC
 * without it. A row whose switch names an action off the short list gets no
 * switch - the PC would refuse it anyway.
 */
export function readAsksFirst(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  if (a.available === false || !Array.isArray(a.groups)) {
    return { available: false, why: text(a.why) || MISSING, groups: [] };
  }
  const groups = a.groups
    .filter((g) => g && typeof g === "object" && Array.isArray(g.rows))
    .map((g) => ({ title: text(g.title), rows: g.rows.filter((r) => r && typeof r === "object").map(readRow) }));
  const w = a.waiting && typeof a.waiting === "object" ? a.waiting : null;
  const last = a.last && typeof a.last === "object" ? a.last : null;
  return {
    available: true,
    why: "",
    title: text(a.title) || TITLE,
    detail: text(a.detail) || DETAIL,
    groups,
    canLoosen: a.can_loosen === true,
    waiting: w ? { action: text(w.action), title: text(w.title), said: text(w.said) || WAITING } : null,
    last: last ? { outcome: text(last.outcome), action: text(last.action), message: text(last.message) } : null,
    lights: readLights(a.lights),
    tools: readTools(a.tools),
    lockdown: readLockdown(a.lockdown),
  };
}

/**
 * Lockdown's box: {show, on, lines, button: {label, ask, disabled} | null}.
 * `ask` is what set_asks_first sends: true turns it on (never held - it only
 * makes Jarvis ask more), false asks for the ONE card that turns it off -
 * only when the PC says this app may, on a live link, and not while that
 * card already waits.
 */
export function lockdownView(k, live) {
  if (!k) return { show: false, on: false, lines: [], button: null };
  const lines = [k.says];
  if (k.why) lines.push(k.why.charAt(0).toUpperCase() + k.why.slice(1) + ".");
  if (k.waiting) lines.push(LOCKDOWN_WAITING);
  else if (k.last && k.lastOutcome !== "off") lines.push(k.last);
  if (!k.on) {
    return { show: true, on: false, lines, button: { label: LOCKDOWN_ON_LABEL, ask: true,
      disabled: false } };
  }
  if (!k.canTurnOff) {
    lines.push(LOCKDOWN_PC_ONLY);
    return { show: true, on: true, lines, button: null };
  }
  if (!live && !k.waiting) lines.push(STALE);
  return { show: true, on: true, lines, button: { label: LOCKDOWN_OFF_LABEL, ask: false,
    disabled: k.waiting || !live } };
}

/** A row's first line: "Read your calendar - Does it without asking". */
export function rowLine(row) {
  return `${row.title} - ${row.says}`;
}

/**
 * One "Ask me first" switch: {checked, disabled, lines, loosens}. Checked
 * while it asks, and while a card to loosen it waits (nothing has changed
 * yet). Checking it (stricter) is never held. Unchecking it (looser) needs
 * the PC to say this app may loosen, a live link, and no other loosening
 * card waiting.
 */
export function switchView(row, view, live) {
  const s = row && row.switch;
  if (!s) return null;
  const waitingHere = Boolean(view.waiting && view.waiting.action === row.action);
  const checked = s.asks || waitingHere;
  const lines = [];
  let disabled = false;
  if (waitingHere) {
    lines.push(view.waiting.said || WAITING);
    disabled = true;
  } else if (checked) {
    if (!s.canLoosen) {
      // Lockdown says why on the row itself (its note); otherwise, not the PC.
      if (!row.lockdown) lines.push(NOT_HERE);
      disabled = true;
    } else if (view.waiting) {
      lines.push(ONE_AT_A_TIME);
      disabled = true;
    } else if (!live) {
      lines.push(STALE);
      disabled = true;
    }
  }
  if (view.last && view.last.action === row.action && view.last.message
      && view.last.outcome !== "loosened" && !waitingHere) {
    lines.push(view.last.message);
  }
  return { checked, disabled, lines, loosens: checked };
}

/**
 * One "Let the AI use this" switch, on every Tier A/Tier B tool: {checked,
 * disabled, lines}. Checked while offered, and while a card to offer it waits.
 * Unchecking it (OFF) is never held. Checking it (ON) needs the PC to say this
 * app may enable (so the phone is read-only), a live link, and no other tool's
 * card waiting.
 */
export function toolSwitchView(item, tools, live) {
  if (!item) return null;
  const waitingHere = Boolean(item.waiting);
  const anyWaiting = tools.items.some((i) => i.waiting);
  const checked = item.on || waitingHere;
  const lines = [];
  let disabled = false;
  if (waitingHere) {
    lines.push(WAITING);
    disabled = true;
  } else if (!item.on) {
    // Turning it ON: needs the PC, a live link, and no other tool's card
    // waiting. Turning it OFF (item.on true) is always allowed, never held.
    if (!tools.canEnable) {
      lines.push(TOOLS_PC_ONLY);
      disabled = true;
    } else if (anyWaiting) {
      lines.push(ONE_AT_A_TIME);
      disabled = true;
    } else if (!live) {
      lines.push(STALE);
      disabled = true;
    }
  }
  if (item.last && item.lastOutcome !== "enabled" && !waitingHere) lines.push(item.last);
  return { checked, disabled, lines };
}

/**
 * One "Let the AI use this" row's own switch for a tool item. The item carries
 * its group, so the page can draw the tiered groups (Tier A + Tier B).
 */
export function toolGroupsView(tools) {
  if (!tools || !Array.isArray(tools.items)) return [];
  const byId = new Map(tools.items.map((i) => [i.id, i]));
  const out = [];
  for (const g of tools.groups || []) {
    const items = g.ids.map((id) => byId.get(id)).filter(Boolean);
    if (items.length) out.push({ title: g.title, items });
  }
  // Fall back to item.group when an older PC sends no groups: nothing is lost.
  if (!out.length) {
    const seen = new Map();
    for (const item of tools.items) {
      const title = item.group || "Tools";
      if (!seen.has(title)) seen.set(title, { title, items: [] });
      seen.get(title).items.push(item);
    }
    out.push(...seen.values());
  }
  return out;
}

/** The vault organizer's own switch: a separate row, not a [tools].enabled tool. */
export function vaultSwitchView(vault, live) {
  if (!vault) return null;
  const waitingHere = vault.waiting === true;
  const checked = vault.on || waitingHere;
  const lines = [vault.what];
  let disabled = false;
  if (waitingHere) {
    lines.push(WAITING);
    disabled = true;
  } else if (!vault.on) {
    if (!vault.canEnable) {
      lines.push(TOOLS_PC_ONLY);
      disabled = true;
    } else if (!live) {
      lines.push(STALE);
      disabled = true;
    }
  }
  if (vault.last && vault.lastOutcome !== "enabled" && !waitingHere) lines.push(vault.last);
  return { checked, disabled, lines };
}

/** The plain note naming every tool this slice does NOT offer in-app. */
export function notOfferedView(tools) {
  const n = tools && tools.notOffered;
  if (!n || (!n.tierC.length && !n.notThisSlice.length)) return null;
  const name = (id) => n.labels[id] || id.replace(/_/g, " ");
  const parts = [];
  if (n.tierC.length) parts.push("Never offered in the app: " + n.tierC.map(name).join(", ") + ".");
  if (n.notThisSlice.length) {
    parts.push("Not offered in-app by this slice: " + n.notThisSlice.map(name).join(", ") + ".");
  }
  if (n.why) parts.push(n.why);
  return parts.join(" ");
}

/**
 * The lights switch: checked while on or while an ON card waits; ON is held
 * on a stale link (rule 4), OFF never.
 */
export function lightsView(lights, live) {
  if (!lights) return { show: false, checked: false, canChange: false, lines: [] };
  const lines = [];
  if (lights.waiting) lines.push(LIGHTS_WAITING);
  else if (lights.last && lights.lastOutcome !== "enabled") lines.push(lights.last);
  if (lights.why) lines.push(lights.why.charAt(0).toUpperCase() + lights.why.slice(1) + ".");
  const checked = lights.on || lights.waiting;
  return { show: true, checked, canChange: checked || Boolean(live), lines };
}
