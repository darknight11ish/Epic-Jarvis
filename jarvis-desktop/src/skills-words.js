/**
 * skills-words.js - the Brain's Skills card says what is really on this PC.
 *
 * THE DEFECT THIS REPLACES (the owner's report, fixed 2026-11-07 Wave-9): an
 * empty list drew one sentence,
 *
 *     "No skills installed, or the scanner has quarantined them all."
 *
 * which is two different facts joined by "or". A list that is empty because
 * nothing was installed is not the same as a list emptied by the scanner, and
 * the sentence guessed at the second without ever reading it. On the owner's
 * PC the real answer is measurable: `GET /api/skills` carries `skills` (the
 * installed rows) and `stats` from `jarvis_skills.stats()` - including
 * `installed` and `quarantined`, the scanner's own count of the folders it
 * kept out of the load.
 *
 * WHAT THIS MODULE IS: pure words. No DOM, no fetch, no clock - brain.js draws
 * what these functions return, so every sentence can be proved by a node test
 * without a browser. Nothing here reads the network or writes anything.
 *
 * THE HONESTY RULE, which is the whole point: a count is printed only when the
 * PC reported it. `stats.quarantined` missing means "the PC did not report a
 * quarantine count" - never "0 quarantined". `stats.installed` missing falls
 * back to the installed rows' own length, and says which it used.
 */

/** Plural-safe "1 skill" / "2 skills". */
function skillsWord(n) {
  return `${n} skill${n === 1 ? "" : "s"}`;
}

/**
 * What the PC's answer really measured.
 *
 * @returns {{installed: number|null, quarantined: number|null,
 *            installedFrom: "stats"|"list"|"", unreadable: boolean}}
 *   `installed` is the count's VALUE; `installedFrom` says where it came from
 *   (the PC's own stats, or the length of the list it sent); `quarantined` is
 *   null when the PC did not report it - never guessed.
 */
export function skillCounts(body) {
  const out = { installed: null, quarantined: null, installedFrom: "", unreadable: false };
  if (!body || typeof body !== "object") {
    out.unreadable = true;
    return out;
  }
  const stats = body.stats && typeof body.stats === "object" ? body.stats : null;
  if (stats && Number.isInteger(stats.installed) && stats.installed >= 0) {
    out.installed = stats.installed;
    out.installedFrom = "stats";
  } else if (Array.isArray(body.skills)) {
    out.installed = body.skills.length;
    out.installedFrom = "list";
  }
  if (stats && Number.isInteger(stats.quarantined) && stats.quarantined >= 0) {
    out.quarantined = stats.quarantined;
  }
  out.unreadable = out.installed === null && out.quarantined === null;
  return out;
}

/**
 * The exact one-line state, e.g. "0 skills installed · 0 quarantined by the
 * scanner." Only the parts the PC reported appear; a missing count is said out
 * loud rather than printed as a zero.
 */
export function countLine(body) {
  const got = skillCounts(body);
  const parts = [];
  if (got.installed !== null) {
    parts.push(`${skillsWord(got.installed)} installed`);
  }
  if (got.quarantined !== null) {
    parts.push(`${got.quarantined} quarantined by the scanner`);
  }
  if (!parts.length) {
    return "The PC did not report a skill count, so none is claimed here.";
  }
  const line = parts.join(" · ") + ".";
  if (got.installed !== null && got.installedFrom === "list") {
    return line + " (Counted from the list the PC sent, which did not report its own total.)";
  }
  return line;
}

/**
 * What a quarantine IS, and what it means for this list - the second sentence
 * the empty state needs. It says plainly that quarantined skills are withheld,
 * so an empty list never reads as "the scanner took them all away".
 */
export function meansLine(body) {
  const got = skillCounts(body);
  const head =
    "A quarantined skill is one the scanner refused: it is kept out of the load " +
    "and is not in this list, so it can never act.";
  if (got.quarantined === null) {
    return head + " The PC did not report a quarantine count, so none is claimed here.";
  }
  if (got.quarantined === 0) {
    return head + " Right now the scanner has quarantined none.";
  }
  return (
    head +
    ` Right now ${got.quarantined} ${got.quarantined === 1 ? "skill is" : "skills are"} ` +
    "quarantined on this PC - they stay on disk, out of the load, and are not listed above."
  );
}

/** How a skill arrives, in plain words: there is no marketplace and no download. */
export function arrivalLine() {
  return (
    "How a skill arrives: a folder or a .zip already on this PC, installed from " +
    "Settings, Skills. The scanner runs first and one approval card is asked before " +
    "anything is installed; Jarvis never downloads one and there is no marketplace."
  );
}

/**
 * The whole empty state, as three sentences brain.js draws as three lines.
 * `line` is the measured count, `means` says what a quarantine is, `arrives`
 * says how a skill gets here.
 */
export function emptyWords(body) {
  return {
    line: countLine(body),
    means: meansLine(body),
    arrives: arrivalLine(),
  };
}

/**
 * The one-line summary drawn above a NON-empty list. Empty when the PC
 * reported nothing, because a summary that says "0 of nothing measured" would
 * be worse than silence.
 */
export function summaryLine(body) {
  const got = skillCounts(body);
  if (got.unreadable) return "";
  return countLine(body);
}
