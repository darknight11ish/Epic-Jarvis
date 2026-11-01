/*
 * Settings tab for the Jarvis notes bridge.
 *
 * Two things are deliberately careful here:
 *  - the token: the preferred path is Obsidian's SecretStorage (this plugin
 *    stores only the secret's NAME in data.json); the fallback field is for
 *    older Obsidian versions and says plainly that it is stored on this PC;
 *  - the backend URL: the default is the local machine, and a non-loopback
 *    address gets a visible warning because the token would travel there.
 */
import { App, PluginSettingTab, SecretComponent, Setting } from "obsidian";
import type JarvisNotesPlugin from "./main";
import { DEFAULT_BACKEND, isLoopbackUrl } from "./protocol";
import { DEFAULT_TEMPLATES_FOLDER } from "./templates";

export class JarvisSettingsTab extends PluginSettingTab {
  constructor(app: App, private plugin: JarvisNotesPlugin) {
    super(app, plugin);
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    containerEl.createEl("p", {
      text:
        "The Jarvis notes bridge talks to the Jarvis backend running on this PC. " +
        "It never writes a note itself and it never approves a card: every edit goes through Jarvis's own one-card routes.",
    });

    new Setting(containerEl)
      .setName("Jarvis backend URL")
      .setDesc("The local backend only - usually http://127.0.0.1:4719.")
      .addText((text) =>
        text
          .setPlaceholder(DEFAULT_BACKEND)
          .setValue(this.plugin.settings.backendUrl)
          .onChange(async (value) => {
            this.plugin.settings.backendUrl = value.trim();
            await this.plugin.saveSettings();
            refreshLoopbackWarning();
          }),
      );

    const loopbackWarning = containerEl.createEl("p", { cls: "jarvis-warning" });
    const refreshLoopbackWarning = (): void => {
      const url = this.plugin.settings.backendUrl || DEFAULT_BACKEND;
      loopbackWarning.setText(
        isLoopbackUrl(url)
          ? ""
          : "This address is not on this PC. The Jarvis token would be sent to that host - only do this if you mean it.",
      );
    };
    refreshLoopbackWarning();

    let pickerShown = false;
    try {
      new Setting(containerEl)
        .setName("Token in SecretStorage (preferred)")
        .setDesc(
          "Pick the Obsidian secret that holds the Jarvis pairing token. The token itself is not stored in this plugin's data.json.",
        )
        .addComponent(
          (el) =>
            new SecretComponent(this.app, el)
              .setValue(this.plugin.settings.secretName)
              .onChange(async (value) => {
                this.plugin.settings.secretName = value ?? "";
                await this.plugin.saveSettings();
              }),
        );
      pickerShown = true;
    } catch {
      pickerShown = false;
    }

    if (!pickerShown) {
      containerEl.createEl("p", {
        cls: "jarvis-warning",
        text:
          "SecretStorage is not available in this Obsidian version; use the fallback token field below, " +
          "or type the secret's name if your Obsidian stores secrets but cannot show the picker.",
      });
      new Setting(containerEl)
        .setName("Token in SecretStorage - the secret's name")
        .setDesc("The name only (not the token). Leave empty to use the fallback token below.")
        .addText((text) =>
          text
            .setPlaceholder("Jarvis token")
            .setValue(this.plugin.settings.secretName)
            .onChange(async (value) => {
              this.plugin.settings.secretName = value.trim();
              await this.plugin.saveSettings();
            }),
        );
    }

    new Setting(containerEl)
      .setName("Fallback token (stored on this PC, not encrypted by Obsidian)")
      .setDesc(
        "Only when SecretStorage is not used. This value is saved in this plugin's data.json in the vault's .obsidian folder. " +
          "Fine for a test vault; prefer SecretStorage for your real vault. Never paste this token into a note.",
      )
      .addText((text) => {
        text.inputEl.type = "password";
        return text
          .setPlaceholder("paste the Jarvis pairing token")
          .setValue(this.plugin.settings.fallbackToken)
          .onChange(async (value) => {
            this.plugin.settings.fallbackToken = value.trim();
            await this.plugin.saveSettings();
          });
      });

    new Setting(containerEl)
      .setName("Templates folder")
      .setDesc(
        "The vault folder this plugin lists templates from (read-only). Default: " + DEFAULT_TEMPLATES_FOLDER + ".",
      )
      .addText((text) =>
        text
          .setPlaceholder(DEFAULT_TEMPLATES_FOLDER)
          .setValue(this.plugin.settings.templatesFolder)
          .onChange(async (value) => {
            this.plugin.settings.templatesFolder = value.trim();
            await this.plugin.saveSettings();
          }),
      );

    containerEl.createEl("h3", { text: "Connection" });
    const result = containerEl.createEl("p", { cls: "jarvis-hint" });
    new Setting(containerEl)
      .setName("Test connection")
      .setDesc("Checks the token against a read-only Jarvis route (it does not call the model).")
      .addButton((button) =>
        button.setButtonText("Test connection").onClick(async () => {
          result.setText("Testing\u2026");
          button.setDisabled(true);
          try {
            const answer = await this.plugin.client.testConnection();
            if (answer.kind === "ok") {
              result.setText(
                "Connected. This Jarvis knows " +
                  answer.names.length +
                  " template name(s)." +
                  (answer.why ? " It said: " + answer.why : ""),
              );
            } else {
              result.setText("Not connected: " + answer.message);
            }
          } catch (error) {
            result.setText(
              "Not connected: " + (error instanceof Error ? error.message : String(error)),
            );
          } finally {
            button.setDisabled(false);
            await this.plugin.refreshStatus();
          }
        }),
      );

    containerEl.createEl("p", {
      cls: "jarvis-hint",
      text:
        "The token is read fresh from SecretStorage (or the fallback field) each time a request is sent. " +
        "It is never written to a note, never put in a URL and never logged.",
    });
  }
}
