/*
 * Tests for the plugin's pure template helpers (`src/templates.ts`).
 *
 * The rule these encode: a template name Jarvis knows but the vault folder
 * cannot see is shown, and is NOT offered for creation - there is no route
 * that sends template text back and the plugin never invents note bodies.
 *
 * No build step: Node (22.18+) strips the TypeScript types directly, so this
 * file imports `src/templates.ts` as-is.
 * Run:          node --test tests/templates.test.mjs
 */
import { describe, test } from "node:test";
import assert from "node:assert/strict";

import * as templates from "../src/templates.ts";

const {
  DEFAULT_TEMPLATES_FOLDER,
  TEMPLATE_PREVIEW_CHARS,
  canCreateFromTemplate,
  mergeTemplateChoices,
  normalizeTemplatesFolder,
  templateFilePath,
  templateLabel,
  templateNotePath,
  templateSourceLabel,
} = templates;

describe("normalizeTemplatesFolder", () => {
  test("empty means the default Templates folder", () => {
    assert.equal(DEFAULT_TEMPLATES_FOLDER, "Templates");
    assert.equal(normalizeTemplatesFolder(""), "Templates");
    assert.equal(normalizeTemplatesFolder("   "), "Templates");
    assert.equal(normalizeTemplatesFolder(undefined), "Templates");
  });

  test("strips leading and trailing slashes", () => {
    assert.equal(normalizeTemplatesFolder("/Templates/"), "Templates");
    assert.equal(normalizeTemplatesFolder("///Templates///"), "Templates");
    assert.equal(normalizeTemplatesFolder("/Notes/Templates/"), "Notes/Templates");
    assert.equal(normalizeTemplatesFolder("/"), "Templates");
  });

  test("converts backslashes to forward slashes", () => {
    assert.equal(normalizeTemplatesFolder("Templates"), "Templates");
    assert.equal(normalizeTemplatesFolder("Notes\\Templates"), "Notes/Templates");
    assert.equal(normalizeTemplatesFolder("\\Notes\\Templates\\"), "Notes/Templates");
    assert.equal(normalizeTemplatesFolder("  Notes\\Templates  "), "Notes/Templates");
  });
});

describe("mergeTemplateChoices", () => {
  test("a backend-only name is jarvis", () => {
    assert.deepEqual(mergeTemplateChoices(["project"], []), [{ name: "project", source: "jarvis" }]);
  });

  test("a vault-only name is vault", () => {
    assert.deepEqual(mergeTemplateChoices([], ["project"]), [{ name: "project", source: "vault" }]);
  });

  test("the same name in both places is one both entry, spelled the vault's way", () => {
    const merged = mergeTemplateChoices(["Project"], ["project"]);
    assert.equal(merged.length, 1);
    assert.deepEqual(merged[0], { name: "project", source: "both" });
    assert.equal(merged[0].name, "project", "the vault's spelling is the one that can be opened");
  });

  test("a .md suffix is stripped on both sides", () => {
    const merged = mergeTemplateChoices(["project.md"], ["Project.MD"]);
    assert.equal(merged.length, 1);
    assert.deepEqual(merged[0], { name: "Project", source: "both" });
    assert.deepEqual(
      mergeTemplateChoices(["alpha.md"], []).map((choice) => choice.name),
      ["alpha"],
    );
  });

  test("duplicates collapse and the list is sorted by name", () => {
    const merged = mergeTemplateChoices(["zeta", "alpha", "alpha"], ["beta", "alpha"]);
    assert.deepEqual(
      merged.map((choice) => choice.name),
      ["alpha", "beta", "zeta"],
    );
    assert.equal(merged.length, 3);
    assert.equal(merged[0].source, "both", "alpha was in both places");
    assert.equal(merged[1].source, "vault");
    assert.equal(merged[2].source, "jarvis");
  });

  test("blank names are dropped", () => {
    assert.deepEqual(mergeTemplateChoices(["", "  ", "real"], ["", "vault-real"]), [
      { name: "real", source: "jarvis" },
      { name: "vault-real", source: "vault" },
    ]);
  });
});

describe("template source labels", () => {
  test("templateSourceLabel says where each name came from", () => {
    assert.equal(templateSourceLabel("both"), "vault + Jarvis");
    assert.equal(templateSourceLabel("vault"), "vault");
    assert.equal(templateSourceLabel("jarvis"), "Jarvis only - text not readable here");
  });

  test("templateLabel includes the source marker", () => {
    assert.equal(templateLabel({ name: "project", source: "vault" }), "project (vault)");
    assert.equal(templateLabel({ name: "project", source: "both" }), "project (vault + Jarvis)");
    const jarvisOnly = templateLabel({ name: "project", source: "jarvis" });
    assert.ok(jarvisOnly.startsWith("project ("));
    assert.ok(jarvisOnly.includes("Jarvis only"));
  });
});

describe("canCreateFromTemplate", () => {
  test("false only for jarvis", () => {
    assert.equal(canCreateFromTemplate({ name: "project", source: "jarvis" }), false);
    assert.equal(canCreateFromTemplate({ name: "project", source: "vault" }), true);
    assert.equal(canCreateFromTemplate({ name: "project", source: "both" }), true);
  });
});

describe("templateFilePath", () => {
  test("a template lives under the Templates folder with a .md suffix", () => {
    assert.equal(templateFilePath("Templates", "project"), "Templates/project.md");
    assert.equal(templateFilePath("Templates", "project.md"), "Templates/project.md");
    assert.equal(templateFilePath("/Templates/", "project.md"), "Templates/project.md");
    assert.equal(templateFilePath("", "project"), "Templates/project.md");
    assert.equal(templateFilePath("Notes\\Templates", "project"), "Notes/Templates/project.md");
    assert.equal(templateFilePath("Notes/Templates", "/project/"), "Notes/Templates/project.md");
  });
});

describe("templateNotePath", () => {
  test("the default is name.md at the vault root", () => {
    assert.equal(templateNotePath("project"), "project.md");
    assert.equal(templateNotePath("project.md"), "project.md");
    assert.equal(templateNotePath("project", ""), "project.md");
    assert.equal(templateNotePath("project", "   "), "project.md");
  });

  test("a parent folder is used when given", () => {
    assert.equal(templateNotePath("project", "Notes"), "Notes/project.md");
    assert.equal(templateNotePath("project", "Notes/"), "Notes/project.md");
    assert.equal(templateNotePath("project", "/Notes/"), "Notes/project.md");
  });

  test("no double slash and no leading slash", () => {
    const path = templateNotePath("project", "Notes//");
    assert.ok(!path.includes("//"), "path must not contain a double slash: " + path);
    assert.ok(!path.startsWith("/"), "path must be vault-relative: " + path);
    assert.equal(path, "Notes/project.md");
  });
});

describe("preview size", () => {
  test("TEMPLATE_PREVIEW_CHARS is 600", () => {
    assert.equal(TEMPLATE_PREVIEW_CHARS, 600);
  });
});
