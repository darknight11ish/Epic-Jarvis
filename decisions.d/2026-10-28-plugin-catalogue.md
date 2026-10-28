- **2026-10-28 — The plug-in catalogue lists every `plugins/ready/` folder:** The
  catalogue was built from `$PATCHES` alone, so a drop-in that was born as a
  folder - no patch to mirror it from - was left out of `plugins/registry.json`
  and `plugins/README.md`. Ten were: receipts, skill-hub, vault, voiceprint,
  notion-obsidian, media-index, sandbox, self-improve, auto-router and
  vault-organizer, so the README said 27 drop-in modules while the folder held
  37. The generator now reads each no-patch folder's own `plugin.json` into a
  `folders` list (27 patch-backed + 10 no-patch = 37) and refuses a folder it
  cannot account for instead of skipping it. Measured at `origin/main`
  `8b0c4d125`, `plugins/registry.json` held 27 drop-in entries, not the audit's
  28; the ten folder-only names are the audit's and were right. What this
  deliberately does not do: make the ten into patches, change the loader, or
  move any module file - they were always real drop-ins, and only the catalogue
  failed to say so.
