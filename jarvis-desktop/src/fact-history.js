/**
 * "History of this fact" - the Brain's Memory tab (the owner's choice of
 * 2026-09-28; JARVIS-API.md section 71, `GET /api/memory/fact-history`).
 *
 * A fact that was reworded or corrected keeps its earlier wordings as
 * history (ARCHITECTURE.md section 5). Until now the list only said
 * "replaced by #N". This draws every version, oldest first, and marks the
 * words that changed from one version to the next: removed words struck
 * through (`<del>`), added words underlined (`<ins>`) - never by colour
 * alone, and a screen reader says "deleted" / "inserted".
 *
 * An ERASED version is drawn as the date it was erased and nothing else:
 * the PC sends no words for it (and the Rust blanks them again), and no
 * diff is drawn against it - so erased words can never come back here,
 * not even as the "removed" half of a change.
 *
 * Read by brain_fact_history (src-tauri/src/brain/fact_history.rs), hidden
 * like every memory list under "Windows Hello for memory lists and chat
 * history". A read: nothing here changes a fact. Desktop only - the phone
 * keeps no list of every fact (ARCHITECTURE.md section 8).
 *
 * Everything the PC sends goes in as text (`el()` sets `textContent`).
 *
 * @module fact-history
 */

export const HISTORY_BUTTON = "History";
export const HISTORY_BUTTON_TITLE =
  "See every earlier wording of this fact, with the words that changed marked. Nothing changes.";
export const HISTORY_HEADING = "History of this fact";
export const HISTORY_NOTE =
  "Oldest first. Struck-through words were taken out; underlined words were added.";
export const REPLACED_MARK = "replaced by a newer wording";
export const HISTORY_ONE = "This fact has no other wording.";
export const HISTORY_MORE = "Only the newest 50 wordings are shown.";

const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
const text = (v) => (typeof v === "string" ? v : "");

/**
 * Word-level difference between two wordings, as parts: `{type: "same" |
 * "removed" | "added", text}`. Whitespace is kept as its own parts, so the
 * joined "same" + "added" parts are exactly `b`, and "same" + "removed"
 * exactly `a`.
 *
 * Copied from Hindsight's `diffWords`
 * (hindsight-control-plane/src/components/observation-history-view.tsx,
 * read 2026-09-28), MIT License, Copyright (c) 2025 Vectorize AI, Inc. -
 * the full notice is in THIRD-PARTY-NOTICES.txt. Changed only to plain
 * JavaScript (no TypeScript types), `String()` round its two inputs, and
 * dropping the empty pieces `split` leaves at either end. A longest-
 * common-subsequence table: fine for a fact's few dozen words.
 */
export function diffWords(a, b) {
  const aWords = String(a).split(/(\s+)/);
  const bWords = String(b).split(/(\s+)/);
  const m = aWords.length;
  const n = bWords.length;
  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] =
        aWords[i - 1] === bWords[j - 1]
          ? dp[i - 1][j - 1] + 1
          : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }
  let i = m;
  let j = n;
  const ops = [];
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && aWords[i - 1] === bWords[j - 1]) {
      ops.push({ type: "same", text: aWords[i - 1] });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      ops.push({ type: "added", text: bWords[j - 1] });
      j--;
    } else {
      ops.push({ type: "removed", text: aWords[i - 1] });
      i--;
    }
  }
  return ops.reverse().filter((p) => p.text !== "");
}

/**
 * The PC's answer, read defensively: `{available, why, hidden, hiddenCount,
 * more, versions: [{id, text, isThis, current, forgotten, erasedAt,
 * created, validFrom, validTo, retiredAt, source}]}`. An erased version's
 * words are blanked here too - the third place that rule is kept (the PC,
 * the Rust, this).
 */
export function readFactHistory(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  if (a.available === false) {
    return { available: false, why: text(a.why).trim(), hidden: false, hiddenCount: 0,
             more: false, versions: [] };
  }
  if (a.hidden === true) {
    return { available: true, why: "", hidden: true, hiddenCount: num(a.hidden_count) ?? 0,
             more: false, versions: [] };
  }
  const list = Array.isArray(a.versions) ? a.versions : [];
  return {
    available: true,
    why: "",
    hidden: false,
    hiddenCount: 0,
    more: a.more === true,
    versions: list
      .filter((v) => v && Number.isInteger(v.id) && v.id > 0)
      .map((v) => {
        const erasedAt = num(v.erased_at);
        return {
          id: v.id,
          text: erasedAt === null ? text(v.text) : "",
          isThis: v.this === true,
          current: v.current === true && erasedAt === null,
          forgotten: v.forgotten === true,
          erasedAt,
          created: num(v.created),
          validFrom: num(v.valid_from),
          validTo: num(v.valid_to),
          retiredAt: num(v.retired_at),
          source: text(v.source),
        };
      }),
  };
}

/** A date in plain words: "12 September 2026". */
export function dayWords(epochSeconds) {
  const t = num(epochSeconds);
  if (t === null || t <= 0) return "";
  return new Date(t * 1000).toLocaleDateString("en-GB",
    { day: "numeric", month: "long", year: "numeric" });
}

/** The small line above one version: when, and what became of it. */
export function versionLine(v, index) {
  const parts = [`Version ${index + 1}`];
  const saved = dayWords(v.created);
  if (saved) parts.push(`saved ${saved}`);
  if (v.erasedAt !== null) parts.push(`words erased ${dayWords(v.erasedAt)}`);
  else if (v.current) parts.push("in use now");
  else if (v.forgotten) parts.push("forgotten");
  else if (v.validTo !== null) parts.push(`true until ${dayWords(v.validTo)}`);
  if (v.isThis) parts.push("the one you opened");
  return parts.join(" · ");
}

/**
 * Draws the versions into `box`: each with its line, then its words - the
 * first (and any after an erased one) plain, every other one marked
 * against the version before it.
 */
export function renderFactHistory(box, view, { el }) {
  box.replaceChildren();
  box.append(el("h3", "fact-history-title", HISTORY_HEADING));
  if (view.versions.length <= 1) {
    box.append(el("p", "empty", HISTORY_ONE));
    return;
  }
  box.append(el("p", "note fact-history-note", HISTORY_NOTE));
  const list = el("ol", "fact-history-list");
  let before = null;
  view.versions.forEach((v, index) => {
    const item = el("li", "fact-history-item");
    if (v.isThis) item.dataset.this = "true";
    item.append(el("span", "row-meta fact-history-line", versionLine(v, index)));
    const words = el("p", "fact-history-words");
    if (v.erasedAt !== null) {
      words.textContent = "The words were erased.";
      words.classList.add("fact-history-erased");
    } else if (before === null || before.erasedAt !== null) {
      words.textContent = v.text;
    } else {
      for (const part of diffWords(before.text, v.text)) {
        if (part.type === "same") words.append(document.createTextNode(part.text));
        else words.append(el(part.type === "removed" ? "del" : "ins", "fact-diff", part.text));
      }
    }
    item.append(words);
    list.append(item);
    before = v;
  });
  box.append(list);
  if (view.more) box.append(el("p", "empty", HISTORY_MORE));
}

/**
 * Whether a fact on the loaded list has another wording: it was replaced
 * (`retired_by`), or a loaded fact names it as what replaced it. The list
 * holds the newest 500 facts, so a very old earlier wording may not be on
 * it - then the History button is simply not offered, and nothing wrong is
 * shown.
 */
export function hasOtherVersions(fact, facts) {
  if (!fact) return false;
  if (fact.retired_by) return true;
  const id = Number(fact.id);
  return Array.isArray(facts) && facts.some((f) => f && Number(f.retired_by) === id);
}
