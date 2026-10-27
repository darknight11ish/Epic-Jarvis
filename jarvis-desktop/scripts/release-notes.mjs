/**
 * "What changed?" for a desktop release, in plain words, from the record this
 * repository already keeps.
 *
 * Run by .github/workflows/desktop-release.yml when it writes `latest.json`,
 * and again when it writes the release body - never by hand. The manifest's
 * `notes` field is what the app shows under Settings -> Updates, and it is what
 * `backend/jarvis_quick.py` reads to answer "what changed in the update?" in
 * chat. Before this, that field was one sentence naming the commit, which
 * answers nothing.
 *
 * WHERE THE WORDS COME FROM, and why there and not the git log:
 *
 *   * `changelog.d/*.md` - one bullet per merged pull request, written for the
 *     owner. These are the changes NOT YET rolled into `CHANGELOG.md`, so they
 *     are the closest thing the repository has to "the changes in this build".
 *   * `CHANGELOG.md`'s "Not in a numbered version yet" section - used only when
 *     there is no fragment at all (a release right after a deliberate roll,
 *     which empties the folder). Reading BOTH at once would mix six weeks of
 *     already-shipped changes into one build's notes: the section holds every
 *     change since the last NUMBERED changelog version, which has nothing to do
 *     with the desktop's `major.minor.<run number>` builds.
 *
 * Both are the repository's own record of changes in plain words; the git log
 * is a record of commits, which is not the same thing. Each bullet's own FIRST
 * SENTENCE is quoted - the fragment format is "**Title (date).** details", so
 * that sentence is the summary its author wrote - never rewritten, and a
 * release that has nothing to quote says so rather than inventing a list.
 * Without the trim, two long bullets fill the whole cap and "what changed"
 * becomes two paragraphs.
 *
 * WHAT IT DELIBERATELY DOES NOT CLAIM. The desktop version is
 * `major.minor.<run number>`, so it moves far more often than the changelog's
 * numbered versions, and a bullet already in an earlier desktop build can
 * appear again here after a roll. The wording is therefore "from the
 * changelog", and the chat answer says which release the notes are for and how
 * far behind the caller is (`jarvis_quick.py` `_range_note`). It is a list of
 * real recorded changes, labelled with where it came from - not a promise that
 * it is the exact delta between two builds.
 *
 *   node scripts/release-notes.mjs --version 0.2.320 --commit 0c15f81 \
 *     --branch main
 *
 * Prints the notes to stdout. Exit 1 only for a version/commit it cannot use.
 */
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/** The repository root, from this file's own place (scripts -> app -> root). */
export const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

export const DEFAULT_MAX_ENTRIES = 20;
export const DEFAULT_MAX_CHARS = 2000;
const FRAGMENT = /^\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md$/;

/** One bullet, as the owner should read it: no markdown punctuation. */
export function plainWords(text) {
  return String(text || "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1") // [label](url) -> label
    .replace(/\*\*|__|`/g, "")
    .replace(/^[\s-]+/, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** A fragment file's whole content as one bullet ("" when it is not one). */
export function bulletOf(text) {
  const words = plainWords(text);
  return words ? `- ${words}` : "";
}

/**
 * The bullet's own summary sentence, for a list someone can scan.
 *
 * The fragment format is `- **The thing that changed (date).** How and why.`,
 * so the author already wrote a summary: the first sentence. A sentence that
 * is still too long is cut at a word and marked with "...", never paraphrased.
 */
export function summaryOf(bullet, max = 200) {
  // `plainWords` first: the record's markdown bold and backticks are notation,
  // not words, and the owner reads this line on a card and in a chat reply.
  const words = plainWords(bullet).replace(/^[\s-]+/, "").trim();
  if (!words) return "";
  const first = words.match(/^(.+?[.!?])(?:\s|$)/);
  let line = (first ? first[1] : words).trim();
  if (line.length > max) {
    const cut = line.slice(0, max - 3);
    const space = cut.lastIndexOf(" ");
    line = `${space > 40 ? cut.slice(0, space) : cut}...`;
  }
  return line ? `- ${line}` : "";
}

/** The bullets under "Not in a numbered version yet", newest first as written. */
export function rolledBullets(changelog) {
  const out = [];
  let inside = false;
  for (const line of String(changelog || "").split(/\r?\n/)) {
    if (/^##\s+/.test(line)) {
      inside = /^##\s+Not in a numbered version yet\s*$/i.test(line);
      continue;
    }
    if (!inside) continue;
    if (/^-\s+/.test(line)) out.push(bulletOf(line));
  }
  return out;
}

/**
 * Every recorded change for this build, newest first: the unrolled fragments,
 * or - only when there are none - the newest rolled bullets.
 */
export function readEntries(root = ROOT) {
  const fragments = [];
  try {
    const names = readdirSync(join(root, "changelog.d")).filter((n) => FRAGMENT.test(n));
    // The name's date decides the order; within a day the slug does.
    names.sort();
    for (const name of names.reverse()) {
      try {
        const bullet = summaryOf(readFileSync(join(root, "changelog.d", name), "utf8"));
        if (bullet) fragments.push(bullet);
      } catch {
        /* one unreadable fragment must not lose the rest */
      }
    }
  } catch {
    /* no fragments folder: fall back to the rolled list only */
  }
  let rolled = [];
  try {
    rolled = rolledBullets(readFileSync(join(root, "CHANGELOG.md"), "utf8"))
      .map((b) => summaryOf(b));
  } catch {
    /* no changelog: the fragments are still worth saying */
  }
  const seen = new Set();
  // Fragments when there are any: they are the changes since the last roll.
  // The rolled list is the fallback for a release straight after a roll, and
  // is never mixed in - see the header for why.
  const pool = fragments.length ? fragments : rolled;
  return pool.filter((b) => {
    if (seen.has(b)) return false;
    seen.add(b);
    return true;
  });
}

/**
 * The notes text for one release. Pure, so the test drives it directly.
 *
 * `entries` is already-bulleted lines. The cap keeps `latest.json` small (it is
 * fetched on every check) and keeps a chat answer readable; the count is said
 * out loud when it bites, so a trimmed list never reads as the whole list.
 */
export function buildNotes({
  version,
  commit,
  branch,
  entries = [],
  maxEntries = DEFAULT_MAX_ENTRIES,
  maxChars = DEFAULT_MAX_CHARS,
} = {}) {
  if (!/^\d+\.\d+\.\d+$/.test(String(version || ""))) {
    throw new Error(`version must look like 1.2.3, got ${JSON.stringify(version)}`);
  }
  if (!/^[0-9a-f]{7,40}$/.test(String(commit || ""))) {
    throw new Error(`commit must be a hex sha, got ${JSON.stringify(commit)}`);
  }
  const where = String(branch || "").trim() || "main";
  const head = `Jarvis Desktop ${version}, from commit ${String(commit).slice(0, 7)} ` +
    `on ${where}.`;
  if (!entries.length) {
    return `${head}\n\nWhat changed: the changelog has no unreleased entries for ` +
      `this build, so this release cannot list its changes.`;
  }
  const kept = [];
  let used = 0;
  for (const line of entries) {
    if (kept.length >= maxEntries) break;
    if (used + line.length + 1 > maxChars) break;
    kept.push(line);
    used += line.length + 1;
  }
  const more = entries.length - kept.length;
  return [
    head,
    "",
    "What changed (from the changelog, newest first):",
    ...kept,
    ...(more > 0
      ? [`- ...and ${more} more change${more === 1 ? "" : "s"} in the changelog.`]
      : []),
  ].join("\n");
}

function args(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i];
    if (!key.startsWith("--") || i + 1 >= argv.length) {
      throw new Error(`expected --name value pairs, got ${key}`);
    }
    out[key.slice(2)] = argv[i + 1];
  }
  return out;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const a = args(process.argv.slice(2));
  const notes = buildNotes({
    version: a.version,
    commit: a.commit,
    branch: a.branch,
    entries: readEntries(a.root || ROOT),
    maxEntries: a.max ? Number(a.max) : DEFAULT_MAX_ENTRIES,
  });
  process.stdout.write(`${notes}\n`);
  console.error(`release notes: ${notes.split("\n").length} lines, ` +
    `${notes.length} characters`);
}
