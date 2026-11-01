/*
 * The right-side Jarvis panel: the persistent "Jarvis lives in Obsidian" home.
 *
 * Wave 1 (read-only): the active note's title/path, headings, links, backlinks,
 * unresolved links and frontmatter keys from Obsidian's metadata cache (bounded),
 * an Ask box, and a Capture button.
 *
 * Wave 2 (structured edits): insert under a chosen heading, selection actions
 * (Bold / Italic / Checklist / Replace / Set tag), and "new note from a
 * template". Every edit calls a Jarvis route that raises Jarvis's own ONE card
 * and takes its own File Guardian copy and Undo. This panel NEVER writes the
 * vault, NEVER approves a card, and NEVER shows "saved" before the backend does.
 */
import { ItemView, MarkdownView, TFile, WorkspaceLeaf } from "obsidian";
import type JarvisNotesPlugin from "./main";
import { accessibleName, busy, group, hint, liveRegion } from "./a11y";
import {
  boundedText,
  buildContextText,
  clip,
  firstRunChecklist,
  headingLabel,
  isRefusalKind,
  MAX_SELECTION_CHARS,
  shortError,
} from "./protocol";
import {
  canCreateFromTemplate,
  mergeTemplateChoices,
  normalizeTemplatesFolder,
  TEMPLATE_PREVIEW_CHARS,
  templateFilePath,
  templateLabel,
  templateNotePath,
} from "./templates";
import type { NoteContext, WriteKind } from "./types";

export const VIEW_TYPE_JARVIS_PANEL = "jarvis-notes-panel";

const READY_MESSAGE =
  "Ready. Every edit below goes through Jarvis's own one card; this panel never writes the note.";

export class JarvisPanel extends ItemView {
  private bodyEl: HTMLElement | null = null;
  private resultEl: HTMLElement | null = null;
  private question = "";
  /**
   * The insert draft, its heading and the note it was typed for. They are kept
   * together so a line typed for one note can never be sent for another: when
   * the active note changes, this panel clears the draft instead of carrying it.
   */
  private insertDraft = "";
  private insertHeading = "";
  private insertNotePath = "";
  /** The template picker's choice and the new-note path, kept across re-renders. */
  private templateChoice = "";
  private templateNotePathValue = "";
  private templatePathTouched = false;
  /** The last read-only answer, kept across re-renders so the panel does not lose it. */
  private askAnswer = "Read-only: Jarvis answers here.";
  /** The last write result, kept across re-renders so the PC's sentence is not wiped. */
  private lastResultMessage = READY_MESSAGE;
  private lastResultKind: WriteKind | undefined = undefined;

  constructor(leaf: WorkspaceLeaf, private plugin: JarvisNotesPlugin) {
    super(leaf);
  }

  getViewType(): string {
    return VIEW_TYPE_JARVIS_PANEL;
  }

  getDisplayText(): string {
    return "Jarvis";
  }

  getIcon(): string {
    return "message-square";
  }

  async onOpen(): Promise<void> {
    this.bodyEl = this.containerEl.children[1] as HTMLElement;
    await this.render();
  }

  async render(): Promise<void> {
    const el = this.bodyEl;
    if (!el) return;
    // Do not rebuild the panel under the owner's hands. A metadata change while
    // a field (or a button) in this panel has focus would drop the caret, the
    // screen reader's place and anything typed since the last render. The next
    // change after focus leaves rebuilds it.
    if (el.contains(document.activeElement)) return;
    el.empty();
    el.addClass("jarvis-panel");
    this.resultEl = null;

    el.createEl("h4", { text: "Jarvis" });
    const statusLine = el.createEl("p", { cls: "jarvis-status", text: this.plugin.statusText() });
    liveRegion(statusLine);

    // The write result is created even when no note is open, so a command that
    // cannot run ("Open a note first.") can explain itself in this live line
    // instead of only in a toast - see main.ts's tellPanel.
    this.resultEl = el.createDiv({ cls: "jarvis-result" });
    liveRegion(this.resultEl);
    this.applyResult();

    // The first-run checklist is shown until the backend answers Connected, so a
    // beginner always has exactly one next step in front of them. It is the same
    // pure data every state test covers (src/protocol.ts, firstRunChecklist).
    const checklist = firstRunChecklist(this.plugin.hasToken(), this.plugin.statusKind());
    if (checklist.next) {
      el.createEl("h5", { text: checklist.heading });
      const steps = el.createEl("ol", { cls: "jarvis-checklist" });
      for (const step of checklist.steps) steps.createEl("li", { text: step });
      const next = el.createEl("p", { cls: "jarvis-warning", text: checklist.next });
      liveRegion(next);
    }

    const context = await this.plugin.readNoteContext();
    if (!context) {
      el.createEl("p", {
        cls: "jarvis-hint",
        text: "Open a note to see its context and to ask Jarvis about it.",
      });
      return;
    }

    el.createEl("h4", { text: context.title });
    el.createEl("p", { cls: "jarvis-path", text: context.path });

    this.section(el, "Headings", context.headings.map((heading) => headingLabel(heading)), 30);
    this.section(el, "Links", context.links, 30);
    this.section(el, "Linked from", context.backlinks, 30);
    this.section(el, "Unresolved links", context.unresolved, 30);
    this.section(el, "Frontmatter keys", context.frontmatterKeys, 30);
    if (context.truncated) {
      el.createEl("p", {
        cls: "jarvis-hint",
        text: "A very long note: only its first 12,000 characters are sent when you ask.",
      });
    }

    this.renderAskBox(el, context);
    this.renderEditControls(el, context);

    el.createEl("p", {
      cls: "jarvis-hint",
      text:
        "The structured edit routes arrive with the notes-editor backend deploy. Before that deploy the edit buttons " +
        "answer honestly that this backend does not have the route yet. Ask and Capture work on the shipped backend.",
    });
  }

  /* ------------------------------------------------------------------ */
  /* Small builders                                                      */
  /* ------------------------------------------------------------------ */

  private section(el: HTMLElement, title: string, items: string[], cap: number): void {
    if (!items.length) return;
    el.createEl("h5", { text: title + " (" + items.length + ")" });
    const list = el.createEl("ul", { cls: "jarvis-list" });
    for (const item of items.slice(0, cap)) list.createEl("li", { text: item });
    if (items.length > cap) {
      // "…" alone is read out as "ellipsis" and hides that the list is cut.
      list.createEl("li", { text: "\u2026 and " + (items.length - cap) + " more, not shown" });
    }
  }

  private currentSelection(): string {
    const view = this.app.workspace.getActiveViewOfType(MarkdownView);
    return (view?.editor?.getSelection() ?? "").trim();
  }

  /**
   * Put one sentence into the panel's live result line. Public because the
   * plugin entry point uses it to explain a command that could not start (for
   * example "Open a note first.") inside a live region, not only in a toast.
   */
  showResult(message: string, kind?: WriteKind): void {
    this.lastResultMessage = message;
    this.lastResultKind = kind;
    this.applyResult();
  }

  private applyResult(): void {
    if (!this.resultEl) return;
    this.resultEl.setText(this.lastResultMessage);
    this.resultEl.setAttribute("data-kind", this.lastResultKind ?? "");
    // A refusal is announced assertively (role="alert"); a saved/waiting line is
    // ordinary polite status. Tone is not the only difference any more: the same
    // sentence also carries the backend's own words.
    liveRegion(this.resultEl, isRefusalKind(this.lastResultKind) ? "assertive" : "polite");
  }

  /* ------------------------------------------------------------------ */
  /* Wave 1: ask and capture                                             */
  /* ------------------------------------------------------------------ */

  private renderAskBox(el: HTMLElement, context: NoteContext): void {
    el.createEl("h5", { text: "Ask about this note" });
    const input = el.createEl("textarea", { cls: "jarvis-panel-question" });
    input.rows = 3;
    input.value = this.question;
    input.placeholder = "What is unclear here? What should I link?";
    accessibleName(input, "Ask a question about this note");
    input.addEventListener("input", () => {
      this.question = input.value;
    });
    const row = el.createDiv({ cls: "jarvis-row" });
    group(row, "Ask and capture");
    const ask = row.createEl("button", { text: "Ask", cls: "mod-cta" });
    const capture = row.createEl("button", { text: "Capture selection" });
    const answer = el.createDiv({ cls: "jarvis-answer" });
    liveRegion(answer);
    answer.setText(this.askAnswer);

    ask.addEventListener("click", () => {
      void (async () => {
        ask.disabled = true;
        busy(answer, true);
        answer.setText("Asking the local Jarvis\u2026");
        try {
          const selection = boundedText(this.currentSelection(), MAX_SELECTION_CHARS);
          const contextText =
            buildContextText(context) +
            (selection.text
              ? "\n\nSelected text:" +
                (selection.truncated
                  ? " (first " + MAX_SELECTION_CHARS + " characters only)"
                  : "") +
                "\n" +
                selection.text
              : "");
          const outcome = await this.plugin.client.askJarvis(
            this.question || "What is this note about, and what could be clearer?",
            contextText,
            context.path,
          );
          this.askAnswer =
            outcome.kind === "ok" ? outcome.answer : "Could not ask Jarvis: " + outcome.message;
          answer.setText(this.askAnswer);
          liveRegion(answer, outcome.kind === "ok" ? "polite" : "assertive");
        } catch (error) {
          this.askAnswer = "Could not ask Jarvis: " + shortError(error);
          answer.setText(this.askAnswer);
          liveRegion(answer, "assertive");
        } finally {
          ask.disabled = false;
          busy(answer, false);
          // Give focus back: a disabled button drops it, and Tab would otherwise
          // start again from the top of the Obsidian window.
          if (ask.isConnected) ask.focus();
        }
      })();
    });

    capture.addEventListener("click", () => {
      this.plugin.openCapture(this.currentSelection());
    });
  }

  /* ------------------------------------------------------------------ */
  /* Wave 2: structured edits                                            */
  /* ------------------------------------------------------------------ */

  private renderEditControls(el: HTMLElement, context: NoteContext): void {
    el.createEl("h5", { text: "Edit this note through Jarvis" });
    el.createEl("p", {
      cls: "jarvis-hint",
      text:
        "Each edit raises Jarvis's own one card. Answer it in the Jarvis window on the PC; this panel only waits and reports.",
    });

    /* Insert one line under one of the note's own headings. */
    // The draft, the chosen heading and the note belong together. If the active
    // note changed, start clean for the new note - never carry a line typed for
    // one note into another.
    if (this.insertNotePath !== context.path) {
      this.insertNotePath = context.path;
      this.insertDraft = "";
      this.insertHeading = "";
    }
    el.createEl("p", { cls: "jarvis-label", text: "Insert under a heading" });
    const headingSelect = el.createEl("select", { cls: "dropdown jarvis-select" });
    accessibleName(headingSelect, "Insert under which heading");
    if (context.headings.length) {
      for (const heading of context.headings) {
        const option = document.createElement("option");
        option.value = heading.text;
        option.text = headingLabel(heading);
        headingSelect.appendChild(option);
      }
      const remembered = context.headings.some((heading) => heading.text === this.insertHeading);
      headingSelect.value = remembered ? this.insertHeading : context.headings[0].text;
      this.insertHeading = headingSelect.value;
      headingSelect.addEventListener("change", () => {
        this.insertHeading = headingSelect.value;
      });
    } else {
      const option = document.createElement("option");
      option.value = "";
      option.text = "This note has no headings";
      option.disabled = true;
      headingSelect.appendChild(option);
    }
    const insertInput = el.createEl("textarea", { cls: "jarvis-panel-question" });
    insertInput.rows = 2;
    insertInput.value = this.insertDraft;
    insertInput.placeholder = "One line to add at the end of that section";
    accessibleName(insertInput, "Line to insert under the heading");
    insertInput.addEventListener("input", () => {
      this.insertDraft = insertInput.value;
    });
    const insertRow = el.createDiv({ cls: "jarvis-row" });
    const insertButton = insertRow.createEl("button", { text: "Insert under heading", cls: "mod-cta" });
    insertButton.disabled = context.headings.length === 0;
    if (insertButton.disabled) hint(insertButton, "This note has no headings to insert under.");
    insertButton.addEventListener("click", () => {
      void this.insertUnderHeading(insertButton, headingSelect, insertInput);
    });

    /* Selection actions. */
    const selection = this.currentSelection();
    const view = this.app.workspace.getActiveViewOfType(MarkdownView);
    const editor = view?.editor ?? null;
    el.createEl("p", {
      cls: "jarvis-label",
      text: selection ? "Selection: " + clip(selection, 160) : "Selection actions",
    });
    if (!selection) {
      el.createEl("p", {
        cls: "jarvis-hint",
        text: "Select text in the note to use Bold / Italic / Checklist / Replace. Set tag works on the whole note.",
      });
    }
    const selectionRow = el.createDiv({ cls: "jarvis-row jarvis-row-wrap" });
    group(selectionRow, "Edit the selection through Jarvis");
    const bold = selectionRow.createEl("button", { text: "Bold" });
    const italic = selectionRow.createEl("button", { text: "Italic" });
    const checklist = selectionRow.createEl("button", { text: "Checklist" });
    const replace = selectionRow.createEl("button", { text: "Replace\u2026" });
    const tag = selectionRow.createEl("button", { text: "Set tag\u2026" });
    accessibleName(bold, "Make the selection bold through Jarvis");
    accessibleName(italic, "Make the selection italic through Jarvis");
    accessibleName(checklist, "Turn the selection's line into a checklist item through Jarvis");
    accessibleName(replace, "Replace the selection through Jarvis");
    accessibleName(tag, "Set a tag on this note through Jarvis");
    // Deliberately NOT disabled when nothing is selected: selecting text does
    // not re-render the panel, so a disabled state computed here would stay
    // wrong after the owner drags a selection. Each handler re-reads the
    // selection and refuses in the live result line with the same words.
    bold.addEventListener("click", () => void this.formatSelection(bold, "bold"));
    italic.addEventListener("click", () => void this.formatSelection(italic, "italic"));
    checklist.addEventListener("click", () => void this.checklistLine(checklist));
    replace.addEventListener("click", () => {
      if (!editor) {
        this.showResult("Open a note with an editor first.", "error");
        return;
      }
      this.plugin.openReplace(editor);
    });
    tag.addEventListener("click", () => this.plugin.openTag());

    /* New note from a template. */
    el.createEl("h5", { text: "New note from a template" });
    el.createEl("p", {
      cls: "jarvis-hint",
      text:
        "Names come from Jarvis (read-only) and from the vault Templates folder. The note is created by Jarvis's create route, one card.",
    });
    const templateSelect = el.createEl("select", { cls: "dropdown jarvis-select" });
    accessibleName(templateSelect, "Template for a new note");
    const templatePreview = el.createDiv({ cls: "jarvis-template-preview" });
    // The preview is filled after an async read and changes on every template
    // choice, so it is a live region; tabIndex 0 lets a keyboard user scroll it
    // (max-height + overflow, styles.css).
    liveRegion(templatePreview);
    accessibleName(templatePreview, "Template preview (read only)");
    templatePreview.tabIndex = 0;
    const templatePath = document.createElement("input");
    templatePath.type = "text";
    templatePath.className = "jarvis-text";
    templatePath.placeholder = "New note path, vault-relative (for example project.md)";
    accessibleName(templatePath, "New note path in the vault");
    templatePath.value = this.templateNotePathValue;
    templatePath.addEventListener("input", () => {
      this.templateNotePathValue = templatePath.value;
      this.templatePathTouched = true;
    });
    el.appendChild(templatePath);
    const createRow = el.createDiv({ cls: "jarvis-row" });
    const createButton = createRow.createEl("button", { text: "Create note from template", cls: "mod-cta" });
    createButton.addEventListener("click", () => {
      void this.createFromTemplate(createButton, templateSelect, templatePath);
    });
    void this.fillTemplates(templateSelect, templatePreview, templatePath, createButton);
  }

  private async insertUnderHeading(
    button: HTMLButtonElement,
    headingSelect: HTMLSelectElement,
    insertInput: HTMLTextAreaElement,
  ): Promise<void> {
    const text = insertInput.value.trim();
    const heading = headingSelect.value;
    // The draft belongs to the note recorded when it was typed. Refuse loudly if
    // the active note has moved on, rather than send the line to a different note.
    const path = this.insertNotePath || this.plugin.activeFilePath();
    if (!text) {
      this.showResult("Type the line to add first.", "error");
      return;
    }
    if (!heading || !path) {
      this.showResult("Pick a heading and open a note first.", "error");
      return;
    }
    if (this.plugin.activeFilePath() !== path) {
      this.showResult(
        "The active note changed, so nothing was sent. The line still belongs to " +
          path +
          " - open that note again and retry.",
        "error",
      );
      return;
    }
    button.disabled = true;
    try {
      await this.plugin.performWrite(
        'Asking Jarvis to add a line under "' + heading + '"',
        (sha) => this.plugin.client.insertUnderHeading(path, text, heading, sha),
        (message, kind) => this.showResult(message, kind),
        path,
      );
    } finally {
      button.disabled = false;
      if (button.isConnected) button.focus();
    }
  }

  private async formatSelection(button: HTMLButtonElement, style: "bold" | "italic"): Promise<void> {
    const selection = this.currentSelection();
    const path = this.plugin.activeFilePath();
    if (!selection) {
      this.showResult("Select some text first.", "error");
      return;
    }
    if (!path) {
      this.showResult("Open a note first.", "error");
      return;
    }
    button.disabled = true;
    try {
      await this.plugin.performWrite(
        "Asking Jarvis to make the selection " + style,
        (sha) => this.plugin.client.formatSpan(path, selection, style, "add", sha),
        (message, kind) => this.showResult(message, kind),
        path,
      );
    } finally {
      button.disabled = false;
      if (button.isConnected) button.focus();
    }
  }

  private async checklistLine(button: HTMLButtonElement): Promise<void> {
    const view = this.app.workspace.getActiveViewOfType(MarkdownView);
    const editor = view?.editor ?? null;
    const path = this.plugin.activeFilePath();
    const line = editor ? (editor.getLine(editor.getCursor("from").line) ?? "").trim() : "";
    if (!line || !path) {
      this.showResult("Put the cursor on a line in a note first.", "error");
      return;
    }
    button.disabled = true;
    try {
      await this.plugin.performWrite(
        "Asking Jarvis to turn that line into a checklist item",
        (sha) => this.plugin.client.customizeLine(path, "checklist", line, sha),
        (message, kind) => this.showResult(message, kind),
        path,
      );
    } finally {
      button.disabled = false;
      if (button.isConnected) button.focus();
    }
  }

  /* ------------------------------------------------------------------ */
  /* Templates (read-only outside the backend's create route)            */
  /* ------------------------------------------------------------------ */

  private vaultTemplateNames(): string[] {
    const folder = normalizeTemplatesFolder(this.plugin.settings.templatesFolder).toLowerCase();
    return this.app.vault
      .getFiles()
      .filter(
        (file) =>
          file.extension === "md" && (file.parent?.path ?? "").toLowerCase() === folder,
      )
      .map((file) => file.basename);
  }

  private async readVaultTemplate(filePath: string): Promise<string> {
    const file = this.app.vault.getAbstractFileByPath(filePath);
    if (!(file instanceof TFile)) {
      throw new Error("There is no template file at " + filePath + " in this vault.");
    }
    return await this.app.vault.cachedRead(file);
  }

  private async fillTemplates(
    select: HTMLSelectElement,
    preview: HTMLElement,
    pathInput: HTMLInputElement,
    createButton: HTMLButtonElement,
  ): Promise<void> {
    if (!select.isConnected) return;
    let backendNames: string[] = [];
    let backendWhy = "";
    try {
      const answer = await this.plugin.client.listTemplates();
      if (answer.kind === "ok") {
        backendNames = answer.names;
        backendWhy = answer.why;
      }
    } catch {
      backendNames = [];
    }
    if (!select.isConnected) return;
    const choices = mergeTemplateChoices(backendNames, this.vaultTemplateNames());
    select.replaceChildren();
    if (!choices.length) {
      const option = document.createElement("option");
      option.value = "";
      option.text = "No templates found (Jarvis has none, and the Templates folder is empty)";
      option.disabled = true;
      select.appendChild(option);
      preview.setText(backendWhy ? "Jarvis said: " + backendWhy : "");
      createButton.disabled = true;
      hint(createButton, "No template can be read from this vault yet, so there is nothing to create.");
      return;
    }
    for (const choice of choices) {
      const option = document.createElement("option");
      option.value = choice.name;
      option.text = templateLabel(choice);
      // Deliberately NOT `option.disabled`: browsers skip a disabled option when
      // arrowing through a select, so a keyboard user could never reach - or
      // hear - the "Jarvis only - text not readable here" label. Create is held
      // back below, and the preview explains why.
      select.appendChild(option);
    }
    const firstUsable = choices.find((choice) => canCreateFromTemplate(choice));
    // Restore the remembered template when it is still offered and usable, so a
    // re-render does not silently switch which template "Create" would use.
    const remembered = choices.find(
      (choice) => choice.name === this.templateChoice && canCreateFromTemplate(choice),
    );
    const initial = remembered ?? firstUsable;
    select.value = initial ? initial.name : "";
    if (initial) this.templateChoice = initial.name;
    // "Jarvis only" names are listed but cannot be created from: no route sends
    // template text back, and the plugin will not invent a body.
    createButton.disabled = select.value === "";
    const refresh = (): void => {
      void (async () => {
        const name = select.value;
        this.templateChoice = name;
        if (!name) {
          preview.setText("");
          createButton.disabled = true;
          hint(createButton, "Pick a template first.");
          return;
        }
        const choice = choices.find((candidate) => candidate.name === name);
        createButton.disabled = !choice || !canCreateFromTemplate(choice);
        hint(
          createButton,
          createButton.disabled
            ? "That template's text cannot be read from this vault, so this plugin will not invent a body."
            : "Create this note through Jarvis's one card.",
        );
        const filePath = templateFilePath(this.plugin.settings.templatesFolder, name);
        try {
          const body = await this.readVaultTemplate(filePath);
          preview.setText("Preview (read-only):\n" + clip(body, TEMPLATE_PREVIEW_CHARS));
          // The offered path follows the chosen template until the owner types
          // one; both survive a re-render.
          if (!this.templatePathTouched) {
            pathInput.value = templateNotePath(name);
            this.templateNotePathValue = pathInput.value;
          }
        } catch (error) {
          preview.setText(
            "This template's text cannot be read from the vault (" +
              shortError(error) +
              "). Jarvis knows the name, but no route sends template text back, so this plugin will not invent a body.",
          );
        }
      })();
    };
    select.onchange = refresh;
    refresh();
  }

  private async createFromTemplate(
    button: HTMLButtonElement,
    select: HTMLSelectElement,
    pathInput: HTMLInputElement,
  ): Promise<void> {
    const name = select.value;
    if (!name) {
      this.showResult("Pick a template first.", "error");
      return;
    }
    let body: string;
    try {
      body = await this.readVaultTemplate(
        templateFilePath(this.plugin.settings.templatesFolder, name),
      );
    } catch (error) {
      this.showResult("Cannot read that template: " + shortError(error), "error");
      return;
    }
    const target = pathInput.value.trim() || templateNotePath(name);
    button.disabled = true;
    try {
      await this.plugin.performWriteUnhashed(
        "Asking Jarvis to create " + target,
        () => this.plugin.client.createNote(target, body),
        (message, kind) => this.showResult(message, kind),
      );
    } finally {
      button.disabled = false;
      if (button.isConnected) button.focus();
    }
  }
}
