/*
 * Template-name helpers for the Jarvis notes bridge plugin (pure, testable).
 *
 * Two places know template names:
 *   - Jarvis: GET /api/notes/templates answers NAMES ONLY (never the text), for
 *     the template folder configured on the PC;
 *   - the vault: the plugin lists `*.md` under the Templates folder setting and
 *     reads those files read-only, so it can send their text to the backend's
 *     create route.
 *
 * A name that Jarvis knows but the vault folder here cannot see is shown as
 * "Jarvis only" and CANNOT be created from in this plugin: there is no route
 * that sends template text back, and this plugin does not invent note bodies.
 */
import type { TemplateChoice, TemplateSource } from "./types";

/** The vault folder this plugin reads templates from, unless Settings says otherwise. */
export const DEFAULT_TEMPLATES_FOLDER = "Templates";

/** Trim slashes off a folder name; an empty setting means the default folder. */
export function normalizeTemplatesFolder(raw: string): string {
  const trimmed = (raw ?? "").trim().replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
  return trimmed || DEFAULT_TEMPLATES_FOLDER;
}

function cleanName(raw: string): string {
  return (raw ?? "").trim().replace(/\.md$/i, "");
}

/**
 * Merge the backend's names with the vault folder's names.
 *
 * - Matching is case-insensitive; the vault's spelling wins because that is the
 *   file this plugin can actually read.
 * - `source` is "both" when the name is in both places, "vault" when only the
 *   vault has it, "jarvis" when only the backend knows it.
 * - Sorted by name, so the dropdown is stable between reloads.
 */
export function mergeTemplateChoices(
  backendNames: string[],
  vaultNames: string[],
): TemplateChoice[] {
  const byKey = new Map<string, TemplateChoice>();
  for (const raw of backendNames ?? []) {
    const name = cleanName(raw);
    if (!name) continue;
    const key = name.toLowerCase();
    const existing = byKey.get(key);
    if (existing) {
      existing.source = "both";
    } else {
      byKey.set(key, { name, source: "jarvis" });
    }
  }
  for (const raw of vaultNames ?? []) {
    const name = cleanName(raw);
    if (!name) continue;
    const key = name.toLowerCase();
    const existing = byKey.get(key);
    if (existing) {
      existing.name = name;
      existing.source = "both";
    } else {
      byKey.set(key, { name, source: "vault" });
    }
  }
  return [...byKey.values()].sort((a, b) => a.name.localeCompare(b.name));
}

/** The short parenthesised source marker used in the dropdown. */
export function templateSourceLabel(source: TemplateSource): string {
  if (source === "both") return "vault + Jarvis";
  if (source === "vault") return "vault";
  return "Jarvis only - text not readable here";
}

/** The full dropdown label for one choice. */
export function templateLabel(choice: TemplateChoice): string {
  return choice.name + " (" + templateSourceLabel(choice.source) + ")";
}

/** True when this choice's text can be read from the vault and sent to the create route. */
export function canCreateFromTemplate(choice: TemplateChoice): boolean {
  return choice.source !== "jarvis";
}

/** Where a template file lives, vault-relative, e.g. "Templates/project.md". */
export function templateFilePath(folder: string, name: string): string {
  const cleanFolder = normalizeTemplatesFolder(folder);
  const clean = cleanName(name).replace(/^\/+|\/+$/g, "");
  return cleanFolder + "/" + clean + ".md";
}

/** The default new-note path offered for a template, e.g. "Templates/project-note.md" is avoided. */
export function templateNotePath(name: string, folder = ""): string {
  const clean = cleanName(name).replace(/^\/+|\/+$/g, "");
  const parent = normalizeTemplatesFolder(folder).replace(/[\\/]+$/, "");
  // A new note goes at the vault root (or the given parent), never back into the
  // templates folder: creating over a template is a collision the backend refuses.
  if (!folder.trim()) return clean + ".md";
  return parent + "/" + clean + ".md";
}

/** How much of a template body the dropdown previews. */
export const TEMPLATE_PREVIEW_CHARS = 600;
