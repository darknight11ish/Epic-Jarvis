/**
 * The fixed words and the reads the skills menu's Settings card shares with its
 * tests (the owner's decision of 2026-11-02, scope B; `skills-menu-settings.js`,
 * `skills_menu.rs`, `backend/jarvis_skill_menu.py`,
 * `plugins/ready/skill-menu/`, JARVIS-API.md section 178).
 *
 * Pure: no page, no Tauri, so `tests/skills-menu.mjs` runs it with no browser.
 *
 * EVERY sentence the owner reads about a skill comes from the PC: its name, its
 * description, its verdict, and the sentence about its `scripts/` folder. The
 * words here are the card's own labels and the "could not read it" sentences -
 * nothing here decides what a skill is or whether it may go in.
 *
 * @module skills-menu-rules
 */

/**
 * The owner's own sentence, word for word (Gemini's ruling 6, 2026-11-02):
 * a skill is instructions, and a `scripts/` folder inside one is kept and
 * never run. The PC builds the same sentence for the card and the row; this is
 * the copy the page uses when it has only a count.
 */
export const INERT_SENTENCE =
  "Imported SKILL.md instructions ({n} file(s) in scripts/ are kept inert and never run " +
  "automatically).";

/** The PC's answer when it has no skills module, or no drop-in folder. */
export const MISSING =
  "This PC's Jarvis cannot show the skills menu yet. On the PC, in the Jarvis folder, run " +
  "apply-patches.ps1 (and .\\scripts\\add-plugin.ps1 -Name skill-menu if the card still says " +
  "so), then restart Jarvis.";

export const WAITING_LINK = "Waiting for the connection to your PC.";
export const ASKING = "Asking your PC…";
export const CHOOSING = "Choose a folder, or a .zip…";

/** Every action the Rust command answers, so a typo is a test failure. */
export const ACTIONS = [
  "read",
  "pick_folder",
  "pick_zip",
  "scan",
  "install",
  "import_scan",
  "enable",
  "disable",
  "remove_off",
  "edit",
  "creator_read",
  "creator_install",
];

/** The actions that raise a card on the PC, and so wait for a live link. */
export const CARD_ACTIONS = ["install", "enable", "edit", "creator_install"];

/** The PC's answer when it has no Creator mode module yet. */
export const CREATOR_MISSING =
  "This PC's Jarvis cannot show Creator mode yet. On the PC, in the Jarvis folder, run " +
  "apply-patches.ps1, then restart Jarvis.";

/** The sentence for `n` files in scripts/, or "" when there are none. */
export function inertLine(n) {
  const count = Number.isFinite(Number(n)) ? Math.max(0, Math.trunc(Number(n))) : 0;
  if (!count) return "";
  return INERT_SENTENCE.replace("{n}", String(count));
}

/** The reason in plain words: never a raw "HTTP 404" or a piece of JSON. */
export function refusedWords(error) {
  let text =
    typeof error === "string"
      ? error
      : error && error.message
        ? String(error.message)
        : "";
  text = text.trim();
  if (/^HTTP (404|501)\b/i.test(text)) return MISSING;
  const start = text.indexOf("{");
  if (start >= 0) {
    try {
      const parsed = JSON.parse(text.slice(start));
      const said = parsed && (parsed.error || parsed.message || parsed.reason);
      text = typeof said === "string" ? said.trim() : "";
    } catch {
      text = "";
    }
  }
  if (/^HTTP \d+/i.test(text)) text = "";
  if (!text || /^(undefined|null|nan|\[object Object\])$/i.test(text) || /::/.test(text)) {
    return "Try again in a moment, or restart Jarvis Desktop.";
  }
  return text;
}

function row(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const name = typeof raw.name === "string" ? raw.name.trim() : "";
  if (!name) return null;
  const scripts = Number.isFinite(Number(raw.scripts)) ? Math.max(0, Math.trunc(Number(raw.scripts))) : 0;
  return {
    name,
    description: typeof raw.description === "string" ? raw.description : "",
    trust: typeof raw.trust === "string" ? raw.trust : "",
    verdict: typeof raw.verdict === "string" ? raw.verdict : "",
    uses: Number.isFinite(Number(raw.uses)) ? Math.max(0, Math.trunc(Number(raw.uses))) : 0,
    enabled: raw.enabled === true,
    scripts,
    // The PC's own sentence when it sends one; the same words built here from
    // the count when it does not. Never a sentence about scripts/ on a skill
    // that has none.
    inert: typeof raw.inert === "string" && raw.inert ? raw.inert : inertLine(scripts),
    text: typeof raw.text === "string" ? raw.text : "",
  };
}

/**
 * The PC's `GET /api/skills/menu`, made safe for the page: a list of skills, a
 * list of turned-off skills, and the Hermes folder's availability. `null` when
 * the answer is not the shape this page can honestly show.
 */
export function menuView(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  if (raw.ok === false) {
    return {
      available: false,
      why: typeof raw.reason === "string" && raw.reason ? raw.reason : MISSING,
      skills: [],
      off: [],
      hermes: { available: false, root: "", why: "" },
      note: "",
      counts: {},
    };
  }
  if (!Array.isArray(raw.skills)) return null;
  const hermes = raw.hermes && typeof raw.hermes === "object" ? raw.hermes : {};
  return {
    available: true,
    why: "",
    skills: raw.skills.map(row).filter(Boolean),
    off: (Array.isArray(raw.off) ? raw.off : []).map(row).filter(Boolean),
    hermes: {
      available: hermes.available === true,
      root: typeof hermes.root === "string" ? hermes.root : "",
      why: typeof hermes.why === "string" ? hermes.why : "",
    },
    note: typeof raw.note === "string" ? raw.note : "",
    counts: raw.counts && typeof raw.counts === "object" ? raw.counts : {},
  };
}

/** One skill from an answered scan (`dry_run`), made safe for the page. */
export function scanView(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  if (raw.ok !== true) {
    return {
      ok: false,
      name: "",
      reason: typeof raw.reason === "string" && raw.reason ? raw.reason : "",
      verdict: typeof raw.verdict === "string" ? raw.verdict : "malformed",
      warnings: [],
      blocking: [],
      needsWarnings: false,
      inert: typeof raw.inert === "string" ? raw.inert : "",
    };
  }
  const findings = Array.isArray(raw.findings) ? raw.findings : [];
  const pick = (severity) =>
    findings
      .filter((f) => f && f.severity === severity && typeof f.message === "string")
      .map((f) => ({ message: f.message, where: typeof f.where === "string" ? f.where : "" }));
  const scripts = Number.isFinite(Number(raw.scripts)) ? Math.max(0, Math.trunc(Number(raw.scripts))) : 0;
  return {
    ok: true,
    name: typeof raw.name === "string" ? raw.name : "",
    reason: typeof raw.summary === "string" ? raw.summary : "",
    verdict: typeof raw.verdict === "string" ? raw.verdict : "",
    warnings: pick("warn"),
    blocking: pick("block"),
    needsWarnings: raw.needs_warnings === true,
    scripts,
    inert: typeof raw.inert === "string" && raw.inert ? raw.inert : inertLine(scripts),
  };
}

/** The Hermes scan's answer, made safe for the page. `folders` is what may be
 *  offered; a refused or malformed one is listed and can NOT be imported. */
export function importView(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  if (raw.ok !== true) {
    return {
      ok: false,
      available: false,
      why: typeof raw.reason === "string" && raw.reason ? raw.reason : MISSING,
      root: "",
      folders: [],
      counts: {},
      note: "",
    };
  }
  const folders = (Array.isArray(raw.found) ? raw.found : [])
    .map((f) => {
      if (!f || typeof f !== "object") return null;
      const folder = typeof f.folder === "string" ? f.folder : "";
      if (!folder) return null;
      const scripts = Number.isFinite(Number(f.scripts)) ? Math.max(0, Math.trunc(Number(f.scripts))) : 0;
      return {
        folder,
        name: typeof f.name === "string" ? f.name : folder,
        verdict: typeof f.verdict === "string" ? f.verdict : "",
        summary: typeof f.summary === "string" ? f.summary : "",
        installed: f.installed === true,
        scripts,
        inert: typeof f.inert === "string" && f.inert ? f.inert : inertLine(scripts),
        needsWarnings: f.needs_warnings === true,
        // A skill the scanner refuses cannot be imported at all, so the page
        // does not offer a button it knows the PC will refuse.
        canImport: f.verdict === "clean" || f.verdict === "review",
      };
    })
    .filter(Boolean);
  return {
    ok: true,
    available: raw.available !== false,
    why: typeof raw.why === "string" ? raw.why : "",
    root: typeof raw.root === "string" ? raw.root : "",
    folders,
    counts: raw.counts && typeof raw.counts === "object" ? raw.counts : {},
    note: typeof raw.note === "string" ? raw.note : "",
  };
}

/** What one answer said, in the card's own status line. */
export function answerWords(raw) {
  if (!raw || typeof raw !== "object") return "";
  if (raw.cancelled === true) return "";
  for (const key of ["message", "said", "reason", "error"]) {
    if (typeof raw[key] === "string" && raw[key].trim()) return raw[key].trim();
  }
  if (raw.ok === true) return "Done.";
  return "";
}

/* ── Creator mode (2026-11-09, Wave 13; JARVIS-API section 209) ──────────── */

/**
 * One item in the waiting folder, made safe for the page.
 *
 * The PC decides all of it: the kind, the scanner's verdict, the findings and
 * whether it may be installed at all. The page only decides what a refused row
 * LOOKS like - and a refused row never gets a button, because the PC would not
 * draw a card for it anyway.
 */
function creatorRow(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const name = typeof raw.name === "string" ? raw.name.trim() : "";
  if (!name) return null;
  const kind = raw.kind === "skill" ? "skill" : raw.kind === "plugin" ? "plugin" : "";
  const verdict = typeof raw.verdict === "string" ? raw.verdict : "";
  const findings = Array.isArray(raw.findings) ? raw.findings : [];
  const pick = (severity) =>
    findings
      .filter((f) => f && f.severity === severity && typeof f.message === "string")
      .map((f) => ({
        message: f.message,
        where: typeof f.where === "string" ? f.where : "",
      }));
  return {
    name,
    kind,
    kindWords:
      kind === "skill" ? "skill" : kind === "plugin" ? "plug-in" : "not a skill or a plug-in",
    verdict,
    refused: raw.refused === true || verdict === "refuse" || verdict === "malformed",
    // The PC's own answer, never re-derived here: a plug-in and a blocked skill
    // both come back with can_install false, and the page must not invent a
    // button the PC would refuse.
    canInstall: raw.can_install === true,
    needsWarnings: raw.needs_warnings === true,
    summary: typeof raw.summary === "string" ? raw.summary : "",
    reason: typeof raw.reason === "string" ? raw.reason : "",
    blocking: pick("block"),
    warnings: pick("warn"),
    installed: raw.installed === true,
    where: typeof raw.where === "string" ? raw.where : "",
    sentence: typeof raw.sentence === "string" ? raw.sentence : "",
  };
}

/**
 * The PC's `GET /api/creator/incoming`, made safe for the page: the waiting
 * folder and every item in it. `null` when the answer is not the shape this
 * page can honestly show - "nothing waiting" must never be shown for "I could
 * not ask".
 */
export function creatorView(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  if (raw.ok === false) {
    return {
      available: false,
      why:
        (typeof raw.reason === "string" && raw.reason) ||
        (typeof raw.error === "string" && raw.error) ||
        (typeof raw.why === "string" && raw.why) ||
        CREATOR_MISSING,
      folder: typeof raw.folder === "string" ? raw.folder : "",
      items: [],
      counts: {},
      note: "",
    };
  }
  if (!Array.isArray(raw.items)) return null;
  return {
    available: true,
    why: "",
    folder: typeof raw.folder === "string" ? raw.folder : "",
    items: raw.items.map(creatorRow).filter(Boolean),
    counts: raw.counts && typeof raw.counts === "object" ? raw.counts : {},
    note: typeof raw.note === "string" ? raw.note : "",
  };
}
