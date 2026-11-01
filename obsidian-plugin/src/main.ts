/*
 * Jarvis notes bridge - the Obsidian plugin entry point.
 *
 * WHAT IT IS
 *   A first-class guest inside Obsidian: a ribbon icon, ten commands, a
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
 *   Read-only direction (the way back to the note):
 *     - copy an `obsidian://open` link to this note - an open link only, never
 *       a URI write action, so the clipboard can only ever show a note.
 *
 * SAFETY - the plugin is a thin front end, never a writer:
 *   - It NEVER writes the vault: no Vault.modify, no editor.replaceSelection, no
 *     file creation. The only thing that writes is the backend, after its card.
 *   - It NEVER approves or denies a card: no /api/approve, no /api/deny. A card
 *     is answered on the PC; the plugin only polls GET /api/notes/change to
 *     learn how it ended.
 *   - The only obsidian:// link it builds is `open`; it never builds `new`,
 *     `daily`, `unique` or `prepend`/`append`, which write a note immediately.
 *   - It never says "saved" before the backend says saved.
 *   - The token is read at request time from Obsidian SecretStorage (preferred)
 *     or the warned fallback setting, and is never logged or put in a URL.
 */
import { Editor, MarkdownView, Notice, Plugin, TFile, WorkspaceLeaf } from "obsidian";
import { liveRegion } from "./a11y";
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
  obsidianOpenUri,
  ProtocolError,
  shortError,
  shouldPoll,
} from "./protocol";
import { JarvisSettingsTab } from "./settings";
import { DEFAULT_TEMPLATES_FOLDER } from "./templates";
import type {
  HeadingRef,
  JarvisSettings,
  NoteContext,
  StatusKind,
  WriteKind,
  WriteOutcome,
} from "./types";

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
  /** The same state as `lastStatus`, as a value the panel can act on. */
  private lastStatusKind: StatusKind = "unknown";
  /** One write at a time: a second card while the first waits is only confusing. */
  private writeBusy = false;

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

    /* Read-only direction: copy the obsidian://open link that returns the owner
       to this note. It builds an OPEN link only - never a URI write action. */
    this.addCommand({
      id: "copy-obsidian-link-to-this-note",
      name: "Copy an Obsidian link to this note (read-only)",
      callback: () => void this.copyObsidianLink(),
    });

    this.addRibbonIcon("message-square", "Open the Jarvis panel", () => {
      void this.activatePanel();
    });

    this.statusEl = this.addStatusBarItem();
    this.statusEl.setText(this.lastStatus);
    // A live region, so a change from "checking" to "connected" (or to a
    // failure) is announced instead of silently changing some tiny text.
    liveRegion(this.statusEl);
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
    // Views, intervals and events registered through this.register* are
    // released by Obsidian automatically; nothing else is held open.
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
      this.explain("Open a note first.");
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
      this.explain("Select some text first.");
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
      this.explain("Select the exact words to replace first.");
      return;
    }
    const path = this.activeFilePath();
    if (!path) {
      this.explain("Open a note first.");
      return;
    }
    new ReplaceModal(this.app, this, selection, path).open();
  }

  openTag(): void {
    const path = this.activeFilePath();
    if (!path) {
      this.explain("Open a note first.");
      return;
    }
    new TagModal(this.app, this, path).open();
  }

  /* ------------------------------------------------------------------ */
  /* The read-only direction: an obsidian://open link to this note       */
  /* ------------------------------------------------------------------ */

  /**
   * Copy the read-only `obsidian://open` link for the active note, so it can be
   * pasted where a person (or Jarvis's own answer) can open that note.
   *
   * This builds an OPEN link only. It never builds `new`, `daily`, `unique` or
   * the `prepend`/`append` actions those take: those write a note immediately,
   * which would bypass Jarvis's one card, the File Guardian copy and Undo.
   */
  async copyObsidianLink(): Promise<void> {
    const path = this.activeFilePath();
    if (!path) {
      this.explain("Open a note first.");
      return;
    }
    const uri = obsidianOpenUri(this.app.vault.getName(), path);
    try {
      await navigator.clipboard.writeText(uri);
      new Notice("Copied the Obsidian link: " + uri, 8000);
    } catch (error) {
      new Notice(
        "Could not copy the link (" + shortError(error) + "). The link is: " + uri,
        12000,
      );
    }
  }

  async formatSelection(editor: Editor, style: "bold" | "italic"): Promise<void> {
    const selection = (editor.getSelection() ?? "").trim();
    if (!selection) {
      this.explain("Select some text first.");
      return;
    }
    const path = this.activeFilePath();
    if (!path) {
      this.explain("Open a note first.");
      return;
    }
    await this.performWrite(
      "Asking Jarvis to make the selection " + style,
      (sha) => this.client.formatSpan(path, selection, style, "add", sha),
      (message, kind) => this.showFromCommand(message, kind),
      path,
    );
  }

  async checklistSelectionLine(editor: Editor): Promise<void> {
    const line = (editor.getLine(editor.getCursor("from").line) ?? "").trim();
    if (!line) {
      this.explain("Put the cursor on a line first.");
      return;
    }
    const path = this.activeFilePath();
    if (!path) {
      this.explain("Open a note first.");
      return;
    }
    await this.performWrite(
      "Asking Jarvis to turn that line into a checklist item",
      (sha) => this.client.customizeLine(path, "checklist", line, sha),
      (message, kind) => this.showFromCommand(message, kind),
      path,
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
   * `targetPath` is the note the edit was started for. Passing it means a note
   * switch between the button press and the confirm cannot make the flow read a
   * different note's hash; the Replace and Tag dialogs pass the path they
   * captured when they opened.
   *
   * Only ONE write runs at a time: a second card while the first is waiting is
   * confusing, so the next attempt is told to answer or dismiss the first card
   * (the backend would refuse the loser anyway, with its own hash check).
   *
   * This method never writes a note, never approves a card, and never turns an
   * error or a "waiting" into a "saved".
   */
  async performWrite(
    label: string,
    start: (expectedSha: string) => Promise<WriteOutcome>,
    show: ShowMessage,
    targetPath?: string,
  ): Promise<void> {
    if (this.writeBusy) {
      show("Another Jarvis edit is already waiting. Answer or dismiss that card first.", "waiting");
      return;
    }
    this.writeBusy = true;
    try {
      show(label + "\u2026", "waiting");
      let outcome: WriteOutcome;
      try {
        const path = targetPath ?? this.activeFilePath();
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
      try {
        const final = await this.client.pollChange(outcome.jobId, (message) =>
          show(message, "waiting"),
        );
        show(final.message, final.kind);
      } catch (error) {
        // The backend can restart while the card waits. Say so honestly: the
        // write may still have happened, so this must not read as "nothing".
        show(
          "Lost contact with Jarvis while checking the card: " +
            shortError(error) +
            " The write may still have happened - check Jarvis on the PC, then reopen the panel.",
          "error",
        );
      }
    } finally {
      this.writeBusy = false;
    }
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
    if (this.writeBusy) {
      show("Another Jarvis edit is already waiting. Answer or dismiss that card first.", "waiting");
      return;
    }
    this.writeBusy = true;
    try {
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
      try {
        const final = await this.client.pollChange(outcome.jobId, (message) =>
          show(message, "waiting"),
        );
        show(final.message, final.kind);
      } catch (error) {
        show(
          "Lost contact with Jarvis while checking the card: " +
            shortError(error) +
            " The write may still have happened - check Jarvis on the PC, then reopen the panel.",
          "error",
        );
      }
    } finally {
      this.writeBusy = false;
    }
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

  /**
   * Put one sentence into an open panel's live result line. Returns false when
   * no panel is open, so the caller can fall back to a Notice.
   *
   * WHY: a toast is not reliably announced, and it disappears. The panel's
   * result line is a live region, so a command that cannot start ("Open a note
   * first.") is both heard and still readable afterwards.
   */
  private tellPanel(message: string, kind: WriteKind = "error"): boolean {
    let told = false;
    for (const leaf of this.app.workspace.getLeavesOfType(VIEW_TYPE_JARVIS_PANEL)) {
      const view = leaf.view;
      if (view instanceof JarvisPanel) {
        view.showResult(message, kind);
        told = true;
      }
    }
    return told;
  }

  /** Explain a failed command in the live panel line when one is open, else a Notice. */
  private explain(message: string, kind: WriteKind = "error"): void {
    if (!this.tellPanel(message, kind)) new Notice(message);
  }

  /** One write update from a command: live panel line when open, else a Notice. */
  private showFromCommand(message: string, kind?: WriteKind): void {
    if (!this.tellPanel(message, kind)) new Notice(message, 8000);
  }

  /* ------------------------------------------------------------------ */
  /* Status bar + Test connection                                        */
  /* ------------------------------------------------------------------ */

  private renderStatus(): void {
    if (this.statusEl) this.statusEl.setText(this.lastStatus);
  }

  /**
   * Publish one honest status sentence. When the STATE changes (not just the
   * wording), the open panel is re-rendered too, so its first-run checklist can
   * disappear as soon as Test connection says Connected - the owner does not
   * have to switch notes to see that they are done.
   */
  private publishStatus(kind: StatusKind): void {
    const changed = kind !== this.lastStatusKind;
    this.lastStatusKind = kind;
    this.renderStatus();
    if (changed) this.refreshPanels();
  }

  statusText(): string {
    return this.lastStatus;
  }

  /** The same honest state as the status sentence, for the panel's first-run checklist. */
  statusKind(): StatusKind {
    return this.lastStatusKind;
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
        this.publishStatus("no-token");
        return;
      }
      try {
        const answer = await this.client.testConnection();
        if (answer.kind === "ok") {
          this.lastStatus = "Jarvis: connected";
          this.publishStatus("connected");
        } else if (answer.httpStatus === 401) {
          this.lastStatus = "Jarvis: token refused";
          this.publishStatus("token-refused");
        } else if (answer.httpStatus === 403) {
          // Not the token: the health check got a refusal it cannot explain.
          this.lastStatus = "Jarvis: HTTP 403";
          this.publishStatus("http");
        } else if (answer.httpStatus === 404) {
          this.lastStatus = "Jarvis: notes routes not deployed";
          this.publishStatus("not-deployed");
        } else {
          this.lastStatus = "Jarvis: HTTP " + answer.httpStatus;
          this.publishStatus("http");
        }
      } catch (error) {
        const said = shortError(error);
        const unreachable = said.includes("Could not reach");
        this.lastStatus = unreachable ? "Jarvis: unreachable" : "Jarvis: " + said.slice(0, 60);
        this.publishStatus(unreachable ? "unreachable" : "http");
      }
    } finally {
      this.statusBusy = false;
    }
  }
}
