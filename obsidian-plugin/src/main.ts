/*
 * Jarvis notes bridge - the Obsidian plugin entry point.
 *
 * WHAT IT IS
 *   A first-class guest inside Obsidian: a ribbon icon, four commands, a
 *   right-side panel and an editor selection menu, all talking to the local
 *   Jarvis backend on this PC (http://127.0.0.1:4719 by default).
 *
 * WHAT IT CAN DO
 *   Wave 1 (read-only + capture):
 *     - ask Jarvis about the active note or the selected text (POST /api/chat);
 *     - capture words to today's daily note (POST /api/notes/capture);
 *     - show the note's headings, links, backlinks, unresolved links and
 *       frontmatter keys from Obsidian's own metadata cache, bounded.
 *   Wave 2 (structured edits - every one through Jarvis's ONE-card routes):
 *     - insert one line under a chosen heading (POST /api/notes/insert);
 *     - make the selection bold or italic (POST /api/notes/format);
 *     - replace the selection (POST /api/notes/replace);
 *     - turn the selection's line into a checklist item (POST /api/notes/customize);
 *     - tag the note (POST /api/notes/tag);
 *     - create a note from a template (POST /api/notes/create).
 *
 * SAFETY - the plugin is a thin front end, never a writer:
 *   - It NEVER writes the vault: no Vault.modify, no editor.replaceSelection, no
 *     file creation. The only thing that writes is the backend, after its card.
 *   - It NEVER approves or denies a card: no /api/approve, no /api/deny. A card
 *     is answered on the PC; the plugin only polls GET /api/notes/change to
 *     learn how it ended.
 *   - It never says "saved" before the backend says saved.
 *   - The token is read at request time from Obsidian SecretStorage (preferred)
 *     or the warned fallback setting, and is never logged or put in a URL.
 */
import { Editor, MarkdownView, Notice, Plugin, TFile, WorkspaceLeaf } from "obsidian";
import { JarvisClient } from "./client";
import { AskModal, CaptureModal, ReplaceModal, TagModal } from "./modals";
import { JarvisPanel, VIEW_TYPE_JARVIS_PANEL } from "./panel";
import {
  boundedText,
  buildContextText,
  clip,
  DEFAULT_BACKEND,
  MAX_CONTEXT_CHARS,
  MAX_FRONTMATTER_KEYS,
  MAX_HEADINGS,
  MAX_LINKS,
  MAX_SELECTION_CHARS,
  normalizeBackendUrl,
  ProtocolError,
  shortError,
  shouldPoll,
} from "./protocol";
import { JarvisSettingsTab } from "./settings";
import { DEFAULT_TEMPLATES_FOLDER } from "./templates";
import type { HeadingRef, JarvisSettings, NoteContext, WriteKind, WriteOutcome } from "./types";

const DEFAULT_SETTINGS: JarvisSettings = {
  backendUrl: DEFAULT_BACKEND,
  secretName: "",
  fallbackToken: "",
  templatesFolder: DEFAULT_TEMPLATES_FOLDER,
};

/** A panel's result line: the backend's sentence plus which kind it is. */
export type ShowMessage = (message: string, kind?: WriteKind) => void;

export default class JarvisNotesPlugin extends Plugin {
  settings: JarvisSettings = { ...DEFAULT_SETTINGS };
  client!: JarvisClient;
  statusEl: HTMLElement | null = null;
  private statusBusy = false;
  private lastStatus = "Jarvis: checking\u2026";
  private refreshTimer: number | null = null;

  async onload(): Promise<void> {
    await this.loadSettings();
    this.client = new JarvisClient(
      () => this.settings.backendUrl,
      () => this.getToken(),
    );

    this.registerView(VIEW_TYPE_JARVIS_PANEL, (leaf) => new JarvisPanel(leaf, this));
    this.addSettingTab(new JarvisSettingsTab(this.app, this));

    /* Wave 1 commands - four, each with no default hotkey (the user assigns one). */
    this.addCommand({
      id: "ask-jarvis-about-this-note",
      name: "Ask Jarvis about this note",
      callback: () => void this.askAboutActiveNote(),
    });
    this.addCommand({
      id: "ask-jarvis-about-selection",
      name: "Ask Jarvis about the selection",
      editorCallback: (editor: Editor) => this.askAboutSelection(editor),
    });
    this.addCommand({
      id: "capture-to-todays-note",
      name: "Capture to today's note",
      callback: () => {
        const view = this.app.workspace.getActiveViewOfType(MarkdownView);
        this.openCapture(view?.editor?.getSelection() ?? "");
      },
    });
    this.addCommand({
      id: "open-jarvis-panel",
      name: "Open the Jarvis panel",
      callback: () => void this.activatePanel(),
    });

    /* Wave 2 commands: the same structured edits the panel offers, reachable from the palette. */
    this.addCommand({
      id: "jarvis-make-selection-bold",
      name: "Through Jarvis: make the selection bold",
      editorCallback: (editor: Editor) => void this.formatSelection(editor, "bold"),
    });
    this.addCommand({
      id: "jarvis-make-selection-italic",
      name: "Through Jarvis: make the selection italic",
      editorCallback: (editor: Editor) => void this.formatSelection(editor, "italic"),
    });
    this.addCommand({
      id: "jarvis-checklist-selection-line",
      name: "Through Jarvis: turn the selection's line into a checklist item",
      editorCallback: (editor: Editor) => void this.checklistSelectionLine(editor),
    });
    this.addCommand({
      id: "jarvis-replace-selection",
      name: "Through Jarvis: replace the selection\u2026",
      editorCallback: (editor: Editor) => this.openReplace(editor),
    });
    this.addCommand({
      id: "jarvis-tag-this-note",
      name: "Through Jarvis: tag this note\u2026",
      callback: () => this.openTag(),
    });

    this.addRibbonIcon("message-square", "Open the Jarvis panel", () => {
      void this.activatePanel();
    });

    this.statusEl = this.addStatusBarItem();
    this.statusEl.setText(this.lastStatus);
    this.statusEl.setAttribute("aria-label", "Jarvis connection");
    this.registerInterval(
      window.setInterval(() => void this.refreshStatus(), 60000),
    );
    void this.refreshStatus();

    this.registerEvent(
      this.app.workspace.on("active-leaf-change", () => {
        this.refreshPanels();
        void this.refreshStatus();
      }),
    );
    this.registerEvent(
      this.app.metadataCache.on("changed", (file: TFile) => {
        if (this.activeFilePath() === file.path) this.refreshPanels();
      }),
    );
  }

  onunload(): void {
    if (this.refreshTimer !== null) window.clearTimeout(this.refreshTimer);
  }

  /* ------------------------------------------------------------------ */
  /* Settings and token                                                  */
  /* ------------------------------------------------------------------ */

  async loadSettings(): Promise<void> {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
    await this.refreshStatus();
  }

  /**
   * The token, read fresh at request time.
   *
   * Preferred: Obsidian's SecretStorage (the plugin stores only the secret's
   * NAME in data.json). Fallback: the plain setting, which is stored in this
   * plugin's data.json on this PC - the settings tab warns about that.
   */
  getToken(): string {
    const store = (this.app as unknown as {
      secretStorage?: { getSecret?: (name: string) => string | null };
    }).secretStorage;
    if (this.settings.secretName && store?.getSecret) {
      try {
        const value = store.getSecret(this.settings.secretName);
        if (value) return value;
      } catch {
        /* fall through to the warned fallback setting */
      }
    }
    return this.settings.fallbackToken;
  }

  hasToken(): boolean {
    return (this.getToken() ?? "").trim().length > 0;
  }

  baseUrl(): string {
    return normalizeBackendUrl(this.settings.backendUrl);
  }

  /* ------------------------------------------------------------------ */
  /* The active note's bounded, read-only context                        */
  /* ------------------------------------------------------------------ */

  activeFilePath(): string {
    return this.app.workspace.getActiveViewOfType(MarkdownView)?.file?.path ?? "";
  }

  /**
   * A bounded read-only context pack, from Obsidian's own metadata cache plus
   * the editor's current text. Nothing here writes anything.
   */
  async readNoteContext(): Promise<NoteContext | null> {
    const view = this.app.workspace.getActiveViewOfType(MarkdownView);
    const file: TFile | null = view?.file ?? null;
    if (!file) return null;
    const cache = this.app.metadataCache.getFileCache(file);
    const headings: HeadingRef[] =
      cache?.headings
        ?.map((heading) => ({ level: heading.level, text: heading.heading }))
        .slice(0, MAX_HEADINGS) ?? [];

    const outgoing: string[] = [];
    const backlinks: string[] = [];
    const resolved = this.app.metadataCache.resolvedLinks;
    for (const [source, targets] of Object.entries(resolved)) {
      if (source === file.path) {
        for (const target of Object.keys(targets)) {
          if (outgoing.length < MAX_LINKS) outgoing.push(target);
        }
      }
      if (Object.prototype.hasOwnProperty.call(targets, file.path) && backlinks.length < MAX_LINKS) {
        backlinks.push(source);
      }
    }

    const unresolved: string[] = [];
    for (const link of cache?.links ?? []) {
      if (unresolved.length >= MAX_LINKS) break;
      if (!this.app.metadataCache.getFirstLinkpathDest(link.link, file.path)) {
        unresolved.push(link.link);
      }
    }

    let text = "";
    let truncated = false;
    try {
      text = view?.editor?.getValue() ?? (await this.app.vault.cachedRead(file));
      if (text.length > MAX_CONTEXT_CHARS) {
        text = text.slice(0, MAX_CONTEXT_CHARS);
        truncated = true;
      }
    } catch {
      text = "";
    }

    return {
      path: file.path,
      title: file.basename,
      headings,
      links: outgoing,
      backlinks,
      unresolved,
      frontmatterKeys: Object.keys(cache?.frontmatter ?? {}).slice(0, MAX_FRONTMATTER_KEYS),
      text,
      truncated,
    };
  }

  /* ------------------------------------------------------------------ */
  /* Read-only asks                                                      */
  /* ------------------------------------------------------------------ */

  async askAboutActiveNote(): Promise<void> {
    const context = await this.readNoteContext();
    if (!context) {
      new Notice("Open a note first.");
      return;
    }
    const selection = this.app.workspace.getActiveViewOfType(MarkdownView)?.editor?.getSelection() ?? "";
    const bounded = boundedText(selection.trim(), MAX_SELECTION_CHARS);
    const contextText =
      buildContextText(context) +
      (bounded.text
        ? "\n\nSelected text:" +
          (bounded.truncated
            ? " (first " + MAX_SELECTION_CHARS + " characters only)"
            : "") +
          "\n" +
          bounded.text
        : "");
    new AskModal(this.app, this, contextText, context.path, {
      prefill: bounded.text
        ? "Explain this part of the note and suggest a clearer version:\n" + clip(bounded.text, 2000)
        : "What is this note about, and what could be clearer?",
      title: "Ask Jarvis about " + context.path,
    }).open();
  }

  askAboutSelection(editor: Editor): void {
    const selection = (editor.getSelection() ?? "").trim();
    if (!selection) {
      new Notice("Select some text first.");
      return;
    }
    const path = this.activeFilePath() || "this note";
    const bounded = boundedText(selection, MAX_SELECTION_CHARS);
    new AskModal(
      this.app,
      this,
      "Selected text from " +
        path +
        (bounded.truncated ? " (first " + MAX_SELECTION_CHARS + " characters only)" : "") +
        ":\n" +
        bounded.text,
      path,
      {
        prefill: "Explain this and suggest a clearer version:",
        title: "Ask Jarvis about the selection",
      },
    ).open();
  }

  /* ------------------------------------------------------------------ */
  /* Capture                                                             */
  /* ------------------------------------------------------------------ */

  openCapture(prefill: string): void {
    new CaptureModal(this.app, this, prefill).open();
  }

  /* ------------------------------------------------------------------ */
  /* Wave 2 structured edits                                             */
  /* ------------------------------------------------------------------ */

  openReplace(editor: Editor): void {
    const selection = (editor.getSelection() ?? "").trim();
    if (!selection) {
      new Notice("Select the exact words to replace first.");
      return;
    }
    const path = this.activeFilePath();
    if (!path) {
      new Notice("Open a note first.");
      return;
    }
    new ReplaceModal(this.app, this, selection, path).open();
  }

  openTag(): void {
    const path = this.activeFilePath();
    if (!path) {
      new Notice("Open a note first.");
      return;
    }
    new TagModal(this.app, this, path).open();
  }

  async formatSelection(editor: Editor, style: "bold" | "italic"): Promise<void> {
    const selection = (editor.getSelection() ?? "").trim();
    if (!selection) {
      new Notice("Select some text first.");
      return;
    }
    const path = this.activeFilePath();
    if (!path) {
      new Notice("Open a note first.");
      return;
    }
    await this.performWrite(
      "Asking Jarvis to make the selection " + style,
      (sha) => this.client.formatSpan(path, selection, style, "add", sha),
      (message) => new Notice(message, 8000),
    );
  }

  async checklistSelectionLine(editor: Editor): Promise<void> {
    const line = (editor.getLine(editor.getCursor("from").line) ?? "").trim();
    if (!line) {
      new Notice("Put the cursor on a line first.");
      return;
    }
    const path = this.activeFilePath();
    if (!path) {
      new Notice("Open a note first.");
      return;
    }
    await this.performWrite(
      "Asking Jarvis to turn that line into a checklist item",
      (sha) => this.client.customizeLine(path, "checklist", line, sha),
      (message) => new Notice(message, 8000),
    );
  }

  /* ------------------------------------------------------------------ */
  /* One shared write flow: read the hash, call the route, wait honestly */
  /* ------------------------------------------------------------------ */

  /**
   * The ONE write flow every edit uses.
   *
   *  1. read the note's current sha256 from the backend (so the edit can carry
   *     the hash it started from, and the backend can refuse a raced edit);
   *  2. call the chosen route; the backend raises its OWN one card;
   *  3. show the backend's own sentence;
   *  4. if a card is waiting, poll GET /api/notes/change until the owner
   *     answers it on the PC, and show the backend's final sentence.
   *
   * This method never writes a note, never approves a card, and never turns an
   * error or a "waiting" into a "saved".
   */
  async performWrite(
    label: string,
    start: (expectedSha: string) => Promise<WriteOutcome>,
    show: ShowMessage,
  ): Promise<void> {
    show(label + "\u2026", "waiting");
    let outcome: WriteOutcome;
    try {
      const path = this.activeFilePath();
      if (!path) throw new ProtocolError("Open a note first.", "invalid");
      const read = await this.client.readNote(path);
      if (read.kind !== "ok") throw new ProtocolError(read.message);
      outcome = await start(read.sha256);
    } catch (error) {
      show("Could not ask Jarvis: " + shortError(error), "error");
      return;
    }
    show(outcome.message, outcome.kind);
    if (!shouldPoll(outcome)) return;
    const final = await this.client.pollChange(outcome.jobId, (message) => show(message, "waiting"));
    show(final.message, final.kind);
  }

  /**
   * The same honest flow for a write that needs no starting hash: creating ONE
   * new note from a template. Nothing is overwritten, so there is no hash to
   * carry; the backend still raises its own one card, keeps collision refusal
   * and records the Undo receipt.
   */
  async performWriteUnhashed(
    label: string,
    start: () => Promise<WriteOutcome>,
    show: ShowMessage,
  ): Promise<void> {
    show(label + "\u2026", "waiting");
    let outcome: WriteOutcome;
    try {
      outcome = await start();
    } catch (error) {
      show("Could not ask Jarvis: " + shortError(error), "error");
      return;
    }
    show(outcome.message, outcome.kind);
    if (!shouldPoll(outcome)) return;
    const final = await this.client.pollChange(outcome.jobId, (message) => show(message, "waiting"));
    show(final.message, final.kind);
  }

  /* ------------------------------------------------------------------ */
  /* Panel                                                               */
  /* ------------------------------------------------------------------ */

  async activatePanel(): Promise<void> {
    let leaf: WorkspaceLeaf | null =
      this.app.workspace.getLeavesOfType(VIEW_TYPE_JARVIS_PANEL)[0] ?? null;
    if (!leaf) {
      leaf = this.app.workspace.getRightLeaf(false);
      if (!leaf) return;
      await leaf.setViewState({ type: VIEW_TYPE_JARVIS_PANEL, active: true });
    }
    this.app.workspace.revealLeaf(leaf);
    this.refreshPanels();
  }

  refreshPanels(): void {
    for (const leaf of this.app.workspace.getLeavesOfType(VIEW_TYPE_JARVIS_PANEL)) {
      const view = leaf.view;
      if (view instanceof JarvisPanel) void view.render();
    }
  }

  /* ------------------------------------------------------------------ */
  /* Status bar + Test connection                                        */
  /* ------------------------------------------------------------------ */

  private renderStatus(): void {
    if (this.statusEl) this.statusEl.setText(this.lastStatus);
  }

  statusText(): string {
    return this.lastStatus;
  }

  /**
   * The status bar is an honest health check: a read-only GET that exists on
   * the notes route family. It never calls a write route and never needs a model.
   */
  async refreshStatus(): Promise<void> {
    if (this.statusBusy) return;
    this.statusBusy = true;
    try {
      if (!this.hasToken()) {
        this.lastStatus = "Jarvis: no token (Settings)";
        this.renderStatus();
        return;
      }
      try {
        const answer = await this.client.testConnection();
        if (answer.kind === "ok") {
          this.lastStatus = "Jarvis: connected";
        } else if (answer.httpStatus === 401 || answer.httpStatus === 403) {
          this.lastStatus = "Jarvis: token refused";
        } else if (answer.httpStatus === 404) {
          this.lastStatus = "Jarvis: notes routes not deployed";
        } else {
          this.lastStatus = "Jarvis: HTTP " + answer.httpStatus;
        }
      } catch (error) {
        const said = shortError(error);
        this.lastStatus = said.includes("Could not reach")
          ? "Jarvis: unreachable"
          : "Jarvis: " + said.slice(0, 60);
      }
      this.renderStatus();
    } finally {
      this.statusBusy = false;
    }
  }
}
