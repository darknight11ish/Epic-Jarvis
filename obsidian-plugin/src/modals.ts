/*
 * The four small dialogs the commands open.
 *
 * Each one is a thin front end to `JarvisClient`/the plugin's shared write
 * flow: it never writes a note, never approves a card, and never shows "saved"
 * before the backend says saved. The wait for a card that the owner answers in
 * the Jarvis window is done by polling `GET /api/notes/change` / the capture
 * status route, and the dialog says exactly what it is doing.
 */
import { App, Modal, Notice, Setting } from "obsidian";
import type JarvisNotesPlugin from "./main";
import { clip, shortError } from "./protocol";
import type { WriteKind } from "./types";

const CARD_HINT =
  "This plugin cannot approve cards. If a card appears, answer it in the Jarvis window on the PC - nothing is written before you do.";

/** Ask Jarvis a read-only question about the note or the selection. */
export class AskModal extends Modal {
  private question: string;
  private readonly contextText: string;
  private readonly notePath: string;
  private readonly heading: string;

  constructor(
    app: App,
    private plugin: JarvisNotesPlugin,
    contextText: string,
    notePath: string,
    options: { prefill: string; title: string },
  ) {
    super(app);
    this.contextText = contextText;
    this.notePath = notePath;
    this.question = options.prefill;
    this.heading = options.title;
  }

  onOpen(): void {
    this.setTitle(this.heading);
    const { contentEl } = this;
    contentEl.createEl("p", {
      cls: "jarvis-hint",
      text: "Read-only: Jarvis answers here. It cannot change, save or approve anything from this dialog.",
    });
    new Setting(contentEl).setName("Question").addTextArea((text) => {
      text.setValue(this.question).onChange((value) => {
        this.question = value;
      });
      text.inputEl.rows = 4;
      text.inputEl.addClass("jarvis-question");
    });
    const answer = contentEl.createEl("div", { cls: "jarvis-answer" });
    answer.setText("Ask when ready.");
    new Setting(contentEl).addButton((button) =>
      button
        .setButtonText("Ask Jarvis")
        .setCta()
        .onClick(async () => {
          button.setDisabled(true);
          answer.setText("Asking the local Jarvis\u2026");
          try {
            const outcome = await this.plugin.client.askJarvis(
              this.question,
              this.contextText,
              this.notePath,
            );
            answer.setText(
              outcome.kind === "ok" ? outcome.answer : "Could not ask Jarvis: " + outcome.message,
            );
            if (outcome.kind === "error") new Notice(outcome.message, 8000);
          } catch (error) {
            answer.setText("Could not ask Jarvis: " + shortError(error));
          } finally {
            button.setDisabled(false);
          }
        }),
    );
  }
}

/** Capture words to today's note through the existing capture route. */
export class CaptureModal extends Modal {
  private text: string;

  constructor(app: App, private plugin: JarvisNotesPlugin, prefill: string) {
    super(app);
    this.text = prefill;
  }

  onOpen(): void {
    this.setTitle("Capture to today's Obsidian note");
    const { contentEl } = this;
    contentEl.createEl("p", { cls: "jarvis-hint", text: CARD_HINT });
    new Setting(contentEl).setName("What to capture").addTextArea((area) => {
      area.setValue(this.text).onChange((value) => {
        this.text = value;
      });
      area.inputEl.rows = 6;
    });
    const said = contentEl.createEl("div", { cls: "jarvis-answer" });
    new Setting(contentEl).addButton((button) =>
      button
        .setButtonText("Capture")
        .setCta()
        .onClick(async () => {
          button.setDisabled(true);
          said.setText("Sending to the local Jarvis\u2026");
          try {
            const outcome = await this.plugin.client.captureToDaily(this.text);
            said.setText(outcome.message);
            if (outcome.kind === "waiting" && outcome.jobId) {
              said.setText(outcome.message + " Checking\u2026");
              const final = await this.plugin.client.pollCapture(outcome.jobId, (message) =>
                said.setText(message + " Checking\u2026"),
              );
              said.setText(final.message);
            }
          } catch (error) {
            said.setText("Not captured: " + shortError(error));
          } finally {
            button.setDisabled(false);
          }
        }),
    );
  }
}

/** Replace the exact selected words, through the one-card replace route. */
export class ReplaceModal extends Modal {
  private newText = "";
  private resultEl: HTMLElement | null = null;

  constructor(
    app: App,
    private plugin: JarvisNotesPlugin,
    private readonly selection: string,
    private readonly path: string,
  ) {
    super(app);
  }

  onOpen(): void {
    this.setTitle("Replace the selection through Jarvis");
    const { contentEl } = this;
    contentEl.createEl("p", { cls: "jarvis-hint", text: CARD_HINT });
    new Setting(contentEl)
      .setName("Selected words")
      .setDesc("This exact text is what Jarvis will replace (one whole-word occurrence).")
      .addTextArea((area) => {
        area.setValue(clip(this.selection, 400));
        area.setDisabled(true);
        area.inputEl.rows = 2;
      });
    new Setting(contentEl).setName("Replace it with").addTextArea((area) => {
      area.setValue(this.newText).onChange((value) => {
        this.newText = value;
      });
      area.inputEl.rows = 4;
    });
    this.resultEl = contentEl.createEl("div", { cls: "jarvis-answer" });
    new Setting(contentEl).addButton((button) =>
      button
        .setButtonText("Ask Jarvis to replace it")
        .setCta()
        .onClick(async () => {
          if (!this.newText.trim()) {
            new Notice("Type the replacement words first.");
            return;
          }
          button.setDisabled(true);
          const show = (message: string, kind?: WriteKind): void => this.showResult(message, kind);
          try {
            await this.plugin.performWrite(
              "Asking Jarvis to replace the selection in " + this.path,
              (sha) => this.plugin.client.replaceOnce(this.path, this.selection, this.newText, sha),
              show,
            );
          } finally {
            button.setDisabled(false);
          }
        }),
    );
  }

  private showResult(message: string, kind?: WriteKind): void {
    if (!this.resultEl) return;
    this.resultEl.setText(message);
    this.resultEl.setAttribute("data-kind", kind ?? "");
  }
}

/** Add one tag to the active note, through the one-card tag route. */
export class TagModal extends Modal {
  private tag = "";
  private resultEl: HTMLElement | null = null;

  constructor(app: App, private plugin: JarvisNotesPlugin, private readonly path: string) {
    super(app);
  }

  onOpen(): void {
    this.setTitle("Tag this note through Jarvis");
    const { contentEl } = this;
    contentEl.createEl("p", { cls: "jarvis-hint", text: CARD_HINT });
    new Setting(contentEl)
      .setName("Tag")
      .setDesc("One tag, without the #: letters, numbers, _ - or /; at least one letter.")
      .addText((text) =>
        text.setPlaceholder("recipes").onChange((value) => {
          this.tag = value;
        }),
      );
    this.resultEl = contentEl.createEl("div", { cls: "jarvis-answer" });
    new Setting(contentEl).addButton((button) =>
      button
        .setButtonText("Ask Jarvis to add the tag")
        .setCta()
        .onClick(async () => {
          if (!this.tag.trim()) {
            new Notice("Type a tag name first.");
            return;
          }
          button.setDisabled(true);
          try {
            await this.plugin.performWrite(
              "Asking Jarvis to tag " + this.path,
              (sha) => this.plugin.client.addTag(this.path, this.tag, sha),
              (message, kind) => {
                if (!this.resultEl) return;
                this.resultEl.setText(message);
                this.resultEl.setAttribute("data-kind", kind ?? "");
              },
            );
          } finally {
            button.setDisabled(false);
          }
        }),
    );
  }
}
