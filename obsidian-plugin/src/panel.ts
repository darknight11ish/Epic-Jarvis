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
import { ItemView, MarkdownView, Notice, TFile, WorkspaceLeaf } from "obsidian";
import type JarvisNotesPlugin from "./main";
import { boundedText, buildContextText, clip, headingLabel, MAX_SELECTION_CHARS, shortError } from "./protocol";
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
  private insertDraft = "";
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
    el.empty();
    el.addClass("jarvis-panel");
    this.resultEl = null;

    el.createEl("h4", { text: "Jarvis" });
    el.createEl("p", { cls: "jarvis-status", text: this.plugin.statusText() });

    if (!this.plugin.hasToken()) {
      el.createEl("p", {
        cls: "jarvis-warning",
        text:
          "No Jarvis token yet. Open Settings -> Jarvis notes bridge, pick a SecretStorage secret (or paste the token in the fallback field), then press Test connection.",
      });
    }

    const context = await this.plugin.readNoteContext();
    if (!context) {
      el.createEl("p", {
        cls: "jarvis-hint",
        text: "Open a note to see its context and to ask Jarvis about it.",
      });
      return;
    }

    this.resultEl = el.createDiv({ cls: "jarvis-result" });
    this.applyResult();

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
    if (items.length > cap) list.createEl("li", { text: "\u2026" });
  }

  private currentSelection(): string {
    const view = this.app.workspace.getActiveViewOfType(MarkdownView);
    return (view?.editor?.getSelection() ?? "").trim();
  }

  private showResult(message: string, kind?: WriteKind): void {
    this.lastResultMessage = message;
    this.lastResultKind = kind;
    this.applyResult();
  }

  private applyResult(): void {
    if (!this.resultEl) return;
    this.resultEl.setText(this.lastResultMessage);
    this.resultEl.setAttribute("data-kind", this.lastResultKind ?? "");
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
    input.addEventListener("input", () => {
      this.question = input.value;
    });
    const row = el.createDiv({ cls: "jarvis-row" });
    const ask = row.createEl("button", { text: "Ask", cls: "mod-cta" });
    const capture = row.createEl("button", { text: "Capture selection" });
    const answer = el.createDiv({ cls: "jarvis-answer" });
    answer.setText("Read-only: Jarvis answers here.");

    ask.addEventListener("click", () => {
      void (async () => {
        ask.disabled = true;
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
          answer.setText(
            outcome.kind === "ok" ? outcome.answer : "Could not ask Jarvis: " + outcome.message,
          );
        } catch (error) {
          answer.setText("Could not ask Jarvis: " + shortError(error));
        } finally {
          ask.disabled = false;
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
    el.createEl("p", { cls: "jarvis-label", text: "Insert under a heading" });
    const headingSelect = el.createEl("select", { cls: "dropdown jarvis-select" });
    if (context.headings.length) {
      for (const heading of context.headings) {
        const option = document.createElement("option");
        option.value = heading.text;
        option.text = headingLabel(heading);
        headingSelect.appendChild(option);
      }
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
    insertInput.addEventListener("input", () => {
      this.insertDraft = insertInput.value;
    });
    const insertRow = el.createDiv({ cls: "jarvis-row" });
    const insertButton = insertRow.createEl("button", { text: "Insert under heading", cls: "mod-cta" });
    insertButton.disabled = context.headings.length === 0;
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
    const bold = selectionRow.createEl("button", { text: "Bold" });
    const italic = selectionRow.createEl("button", { text: "Italic" });
    const checklist = selectionRow.createEl("button", { text: "Checklist" });
    const replace = selectionRow.createEl("button", { text: "Replace\u2026" });
    const tag = selectionRow.createEl("button", { text: "Set tag\u2026" });
    for (const button of [bold, italic, checklist, replace]) {
      button.disabled = !selection && button !== replace;
    }
    replace.disabled = !selection;
    bold.addEventListener("click", () => void this.formatSelection(bold, "bold"));
    italic.addEventListener("click", () => void this.formatSelection(italic, "italic"));
    checklist.addEventListener("click", () => void this.checklistLine(checklist));
    replace.addEventListener("click", () => {
      if (!editor) {
        new Notice("Open a note with an editor first.");
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
    const templatePreview = el.createDiv({ cls: "jarvis-template-preview" });
    const templatePath = document.createElement("input");
    templatePath.type = "text";
    templatePath.className = "jarvis-text";
    templatePath.placeholder = "New note path, vault-relative (for example project.md)";
    el.appendChild(templatePath);
    const createRow = el.createDiv({ cls: "jarvis-row" });
    const createButton = createRow.createEl("button", { text: "Create note from template", cls: "mod-cta" });
    createButton.addEventListener("click", () => {
      void this.createFromTemplate(createButton, templateSelect, templatePath);
    });
    void this.fillTemplates(templateSelect, templatePreview, templatePath);
  }

  private async insertUnderHeading(
    button: HTMLButtonElement,
    headingSelect: HTMLSelectElement,
    insertInput: HTMLTextAreaElement,
  ): Promise<void> {
    const text = insertInput.value.trim();
    const heading = headingSelect.value;
    const path = this.plugin.activeFilePath();
    if (!text) {
      new Notice("Type the line to add first.");
      return;
    }
    if (!heading || !path) {
      new Notice("Pick a heading and open a note first.");
      return;
    }
    button.disabled = true;
    try {
      await this.plugin.performWrite(
        'Asking Jarvis to add a line under "' + heading + '"',
        (sha) => this.plugin.client.insertUnderHeading(path, text, heading, sha),
        (message, kind) => this.showResult(message, kind),
      );
    } finally {
      button.disabled = false;
    }
  }

  private async formatSelection(button: HTMLButtonElement, style: "bold" | "italic"): Promise<void> {
    const selection = this.currentSelection();
    const path = this.plugin.activeFilePath();
    if (!selection) {
      new Notice("Select some text first.");
      return;
    }
    if (!path) {
      new Notice("Open a note first.");
      return;
    }
    button.disabled = true;
    try {
      await this.plugin.performWrite(
        "Asking Jarvis to make the selection " + style,
        (sha) => this.plugin.client.formatSpan(path, selection, style, "add", sha),
        (message, kind) => this.showResult(message, kind),
      );
    } finally {
      button.disabled = false;
    }
  }

  private async checklistLine(button: HTMLButtonElement): Promise<void> {
    const view = this.app.workspace.getActiveViewOfType(MarkdownView);
    const editor = view?.editor ?? null;
    const path = this.plugin.activeFilePath();
    const line = editor ? (editor.getLine(editor.getCursor("from").line) ?? "").trim() : "";
    if (!line || !path) {
      new Notice("Put the cursor on a line in a note first.");
      return;
    }
    button.disabled = true;
    try {
      await this.plugin.performWrite(
        "Asking Jarvis to turn that line into a checklist item",
        (sha) => this.plugin.client.customizeLine(path, "checklist", line, sha),
        (message, kind) => this.showResult(message, kind),
      );
    } finally {
      button.disabled = false;
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
      return;
    }
    for (const choice of choices) {
      const option = document.createElement("option");
      option.value = choice.name;
      option.text = templateLabel(choice);
      option.disabled = !canCreateFromTemplate(choice);
      select.appendChild(option);
    }
    const firstUsable = choices.find((choice) => canCreateFromTemplate(choice));
    if (firstUsable) select.value = firstUsable.name;
    // The offered path follows the chosen template until the owner types one.
    let pathTouched = false;
    pathInput.addEventListener("input", () => {
      pathTouched = true;
    });
    const refresh = (): void => {
      void (async () => {
        const name = select.value;
        if (!name) {
          preview.setText("");
          return;
        }
        const filePath = templateFilePath(this.plugin.settings.templatesFolder, name);
        try {
          const body = await this.readVaultTemplate(filePath);
          preview.setText("Preview (read-only):\n" + clip(body, TEMPLATE_PREVIEW_CHARS));
          if (!pathTouched) pathInput.value = templateNotePath(name);
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
      new Notice("Pick a template first.");
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
    }
  }
}
