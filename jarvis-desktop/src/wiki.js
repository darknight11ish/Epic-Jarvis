/**
 * The wiki builder's plate in the Brain window - backend/wiki.patch and
 * backend/jarvis_wiki.py.
 *
 * Documents the owner drops in their Obsidian vault's `Jarvis Wiki/Sources`
 * folder are turned into linked pages by the model on the second graphics
 * card. This plate shows whether that can run (and why not), each document
 * with its state, an "Add to wiki" button for a new or changed one, the last
 * few log lines, and a way to open the folder.
 *
 * "Add to wiki" only asks. The backend's model reads the document, then ONE
 * approval card is raised; nothing is written until it is answered. The job
 * the backend answers with has a `state`:
 *
 *   reading   the model is reading it; no card yet
 *   waiting   the card is up, in the Jarvis bar, on the widget and on the phone
 *   writing   approved, writing the pages
 *   done      written                              (the server's sentence)
 *   refused   said no, nobody answered, or the plan was refused - and why
 *   failed    could not be written, saying what was and was not
 *
 * Every sentence shown comes from the backend. Nothing here decides on its
 * own that something was added.
 *
 * @module wiki
 */

import { APPROVE_WHERE } from "./jarvis-link.js";

/** How often to ask while a job runs, and for how long before giving up. */
export const POLL_MS = 3000;
/** Reading a long document on the second card, then the card's own wait. */
export const GIVE_UP_MS = 30 * 60 * 1000;
/** Failed polls in a row before the follow stops. One blip - a restart, a
 *  timeout while the second card is busy - used to end it for good. */
export const MAX_FAILED_POLLS = 3;

/** A source state, in words and a tag colour. */
export const STATES = {
  new: { tag: "new", tone: "present", add: true },
  changed: { tag: "changed", tone: "warn", add: true },
  in_wiki: { tag: "in wiki", tone: "ok", add: false },
  too_big: { tag: "too big", tone: "bad", add: false },
  unreadable: { tag: "can't read", tone: "bad", add: false },
};

/**
 * `GET /api/wiki`'s answer, read. Unknown source states are shown as they
 * are and never offered for adding.
 */
export function readWiki(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  const sources = Array.isArray(a.sources) ? a.sources : [];
  return {
    available: a.available === true,
    why: typeof a.why === "string" ? a.why : "",
    folderOk: a.vault_folder_ok === true,
    folderWhy: typeof a.folder_why === "string" ? a.folder_why : "",
    folder: typeof a.folder === "string" && a.folder ? a.folder : null,
    pages: Number.isFinite(a.pages) ? a.pages : 0,
    recent: Array.isArray(a.recent) ? a.recent.map(String) : [],
    running: a.running && typeof a.running === "object" ? a.running : null,
    sources: sources
      .filter((s) => s && typeof s.name === "string")
      .map((s) => ({ name: s.name, state: String(s.state || ""), why: String(s.why || "") })),
  };
}

/** Whether "Add to wiki" is offered for this source, in this view. */
export function canAdd(view, source) {
  const st = STATES[source.state];
  return Boolean(view.available && view.folderOk && !view.running && st && st.add);
}

/** Words for one answer about a job, as `{ text, tone, final }`. */
export function describeJob(job) {
  const state = job && job.state;
  const said = (job && typeof job.message === "string" && job.message.trim()) || "";
  const error = (job && typeof job.error === "string" && job.error.trim()) || "";
  switch (state) {
    case "reading":
      return { text: said || "The model on the second card is reading it. No card yet.",
               tone: null, final: false };
    case "waiting":
      return { text: said || `Waiting for your approval. Approve it ${APPROVE_WHERE} — nothing is written until you do.`,
               tone: null, final: false };
    case "writing":
      return { text: said || "Writing the pages.", tone: null, final: false };
    case "done":
      return { text: said || "Added to the wiki.", tone: "ok", final: true };
    case "refused":
    case "failed":
      return { text: said || error || "Not added. Nothing was written.", tone: "bad", final: true };
    default:
      return { text: "The PC answered, but did not say how it went. Look in the wiki folder.",
               tone: "bad", final: true };
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * "Add to wiki" for one source: asks, then follows the job until it ends,
 * calling `onSay` with each `describeJob` answer. Resolves to the last one.
 *
 * The follow survives a bad moment: up to `MAX_FAILED_POLLS - 1` failed
 * polls in a row are said and retried, and only the next one ends it. While
 * `linkDown()` says the link to the PC is down, no poll is sent at all -
 * and that neither counts as a failure nor ends the follow; the job goes on
 * on the PC either way.
 */
export async function addToWiki(invoke, source, onSay,
                                { pollMs = POLL_MS, giveUpMs = GIVE_UP_MS,
                                  maxFailedPolls = MAX_FAILED_POLLS,
                                  linkDown = () => false } = {}) {
  let said;
  let job;
  try {
    job = await invoke("wiki_ingest", { source });
  } catch (error) {
    said = { text: String((error && error.message) || error), tone: "bad", final: true };
    onSay(said);
    return said;
  }
  said = describeJob(job);
  onSay(said);
  const id = job && job.id;
  const started = Date.now();
  let failed = 0;
  let skipping = false;
  while (!said.final && id) {
    await sleep(pollMs);
    if (Date.now() - started > giveUpMs) {
      said = { text: "Still going on the PC. Nothing is written until you approve its card.",
               tone: null, final: true };
      onSay(said);
      break;
    }
    let down = false;
    try { down = Boolean(linkDown()); } catch { down = false; }
    if (down) {
      // Said once, not every tick; the last real answer is kept as is.
      if (!skipping) {
        skipping = true;
        onSay({ text: "Waiting for the link to the PC to come back. The job carries on there.",
                tone: null, final: false });
      }
      continue;
    }
    skipping = false;
    try {
      said = describeJob(await invoke("wiki_ingest_status", { id }));
      failed = 0;
    } catch (error) {
      failed += 1;
      const why = String((error && error.message) || error);
      said = failed >= maxFailedPolls
        ? { text: `Lost track of it (${why}). Check the approval card and the wiki folder.`,
            tone: "bad", final: true }
        : { text: `Could not ask the PC how it is going (${why}). Trying again.`,
            tone: null, final: false };
    }
    onSay(said);
  }
  return said;
}

/**
 * Paints the plate into `container`.
 *
 * `plate` is `{ view, error, job }`: the last read (from `readWiki`), the
 * reason the last read failed, and the job this window started, as
 * `{ source, said }`. `ui` is the Brain's own `el`, `row` and `button`
 * helpers, so an Add button is greyed on a stale link exactly like every
 * other Brain button (rule 4), and `onAdd(source)` / `onOpen()` are the
 * two actions.
 */
export function renderWiki(container, plate, ui) {
  const { el, row, button } = ui;
  container.replaceChildren();
  if (!plate.view) {
    container.append(el("p", "empty", plate.error
      ? `Could not read the wiki builder: ${plate.error}`
      : "Reading…"));
    return;
  }
  const v = plate.view;
  const lead = el("p", "wiki-state", v.available ? v.why || "Ready." : v.why
    || "The wiki builder is not ready.");
  lead.dataset.ready = String(v.available);
  container.append(lead);
  if (plate.error) container.append(el("p", "empty failed", `Could not read it again: ${plate.error}`));
  if (!v.folderOk) {
    container.append(el("p", "empty", v.folderWhy || "The wiki folder is not set up."));
    return;
  }

  const job = plate.job;
  if (job && job.said) {
    const line = el("p", "wiki-job", `${job.source}: ${job.said.text}`);
    if (job.said.tone) line.dataset.tone = job.said.tone;
    line.setAttribute("role", "status");
    container.append(line);
  } else if (v.running) {
    container.append(el("p", "wiki-job",
      `Working on ${v.running.source} (${String(v.running.state)}).`));
  }

  const list = el("div", "rows");
  for (const s of v.sources) {
    const st = STATES[s.state] || { tag: s.state || "?", tone: "", add: false };
    const actions = [];
    if (canAdd(v, s) && !(job && job.said && !job.said.final)) {
      actions.push(button("Add to wiki", () => plate.onAdd(s.name), {
        live: true,
        title: "The model on the second card reads it and proposes pages; one approval "
          + "card asks you before anything is written. Nothing leaves this PC.",
      }));
    }
    list.append(row({ tag: st.tag, state: st.tone, title: s.name, meta: [s.why], actions }));
  }
  if (!v.sources.length) {
    list.append(el("p", "empty",
      "Sources is empty. Put .md or .txt files in Jarvis Wiki/Sources in your vault. "
      + "Other kinds of file are not read yet."));
  }
  container.append(list);

  const foot = el("div", "wiki-foot");
  foot.append(el("p", "note", `${v.pages} page${v.pages === 1 ? "" : "s"} in the wiki.`));
  if (v.recent.length) {
    foot.append(el("h3", "wiki-sub", "Recently added"));
    const ul = el("ul", "wiki-recent");
    for (const line of v.recent) ul.append(el("li", "", line.replace(/^## /, "")));
    foot.append(ul);
  }
  if (v.folder && plate.onOpen) {
    foot.append(button("Open the wiki folder", () => plate.onOpen(), {
      title: "Opens Jarvis Wiki in Explorer. Only when Jarvis runs on this PC.",
    }));
  }
  container.append(foot);
}
