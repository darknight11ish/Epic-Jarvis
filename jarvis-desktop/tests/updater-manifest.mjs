/**
 * The desktop updater's `latest.json`, as the release workflow writes it.
 *
 * No browser. The shape is Tauri 2's static updater manifest: `version`,
 * `notes`, `pub_date`, and one `{signature, url}` per platform key. Getting
 * a key or a URL wrong fails quietly on the owner's machine - the check just
 * says there is nothing newer - so it is pinned here instead.
 *
 * It also pins the `commit` field (Gemini's ruling Q8, 2026-11-15): the
 * commit the build came from, a program-readable copy of the "from commit
 * ..." line the notes already carry, and absent - never empty - when the
 * caller did not say, so a reader cannot mistake "not recorded" for a value.
 */
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { buildManifest } from "../scripts/updater-manifest.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const BASE = "https://github.com/darknight11ish/Epic-Jarvis/releases/download/desktop-latest";
const NSIS = { name: "jarvis-desktop_0.1.42_x64-setup.exe", signature: "dW50cnVzdGVkIGNvbW1lbnQ=\n" };
const MSI = { name: "jarvis-desktop_0.1.42_x64_en-US.msi", signature: "bXNpc2ln" };

check("the three Windows keys point at the right installers, on the release the app reads", () => {
  const m = buildManifest({ version: "0.1.42", notes: "n", pubDate: "2026-09-23T10:00:00.123Z",
    baseUrl: `${BASE}/`, nsis: NSIS, msi: MSI });
  assert.equal(m.version, "0.1.42");
  assert.equal(m.pub_date, "2026-09-23T10:00:00Z");
  assert.deepEqual(Object.keys(m.platforms).sort(),
    ["windows-x86_64", "windows-x86_64-msi", "windows-x86_64-nsis"]);
  assert.equal(m.platforms["windows-x86_64"].url, `${BASE}/jarvis-desktop_0.1.42_x64-setup.exe`);
  assert.equal(m.platforms["windows-x86_64-msi"].url, `${BASE}/jarvis-desktop_0.1.42_x64_en-US.msi`);
  assert.equal(m.platforms["windows-x86_64"].signature, "dW50cnVzdGVkIGNvbW1lbnQ=",
    "the signature is the .sig file's content, trimmed");
  const conf = JSON.parse(readFileSync(join(HERE, "..", "src-tauri", "tauri.conf.json"), "utf8"));
  assert.equal(conf.plugins.updater.endpoints[0], `${BASE}/latest.json`,
    "the manifest's release and the app's endpoint must be the same release");
});

check("a bad version, a missing signature or an http URL is refused, not written", () => {
  assert.throws(() => buildManifest({ version: "v0.1", baseUrl: BASE, nsis: NSIS }), /version/);
  assert.throws(() => buildManifest({ version: "0.1.1", baseUrl: BASE, nsis: { name: "a.exe", signature: "" } }),
    /signature/);
  assert.throws(() => buildManifest({ version: "0.1.1", baseUrl: "http://example.com", nsis: NSIS }), /https/);
});

check("the commit is a first-class field, and is absent rather than empty when not given", () => {
  // Gemini's ruling Q8 (2026-11-15): the notes already SAY "from commit ...",
  // but a program cannot read prose. The field is what the preflight compares.
  const withCommit = buildManifest({ version: "0.1.42", baseUrl: BASE, nsis: NSIS,
    commit: "7A8FE7D0123456789ABCDEF0123456789ABCDE" });
  assert.equal(withCommit.commit, "7a8fe7d0123456789abcdef0123456789abcde",
    "the commit is kept as lower-case hex, as git writes it");
  assert.deepEqual(Object.keys(withCommit.platforms).sort(),
    ["windows-x86_64", "windows-x86_64-nsis"], "the commit changes nothing else");
  const without = buildManifest({ version: "0.1.42", baseUrl: BASE, nsis: NSIS });
  assert.ok(!("commit" in without), "not given: no key, so a reader knows it was not recorded");
  assert.throws(() => buildManifest({ version: "0.1.42", baseUrl: BASE, nsis: NSIS,
    commit: "not-a-sha" }), /commit/, "a value that is not a commit is refused, never published");
  assert.throws(() => buildManifest({ version: "0.1.42", baseUrl: BASE, nsis: NSIS,
    commit: "7a8fe7d\n7a8fe7e" }), /commit/, "two values in one field are refused");
});

check("the command line reads each .sig beside its installer and writes latest.json", () => {
  const dir = mkdtempSync(join(tmpdir(), "manifest-"));
  const exe = join(dir, NSIS.name);
  writeFileSync(exe, "x");
  writeFileSync(`${exe}.sig`, "c2lnbmVk\n");
  const out = join(dir, "latest.json");
  execFileSync(process.execPath, [join(HERE, "..", "scripts", "updater-manifest.mjs"),
    "--version", "0.1.42", "--commit", "7a8fe7d", "--base-url", BASE, "--nsis", exe,
    "--notes", "hello", "--out", out],
    { stdio: "pipe" });
  const m = JSON.parse(readFileSync(out, "utf8"));
  assert.equal(m.platforms["windows-x86_64-nsis"].signature, "c2lnbmVk");
  assert.equal(m.notes, "hello");
  assert.equal(m.commit, "7a8fe7d", "--commit reaches the file");
  assert.ok(!("windows-x86_64-msi" in m.platforms), "no MSI given, so no MSI entry");
  // And the workflow really passes it: the release notes and the manifest must
  // name the same commit, and one of them is prose.
  const workflow = readFileSync(join(HERE, "..", "..", ".github", "workflows",
    "desktop-release.yml"), "utf8");
  assert.match(workflow, /updater-manifest\.mjs \\\s*\n\s*--version "\$VERSION" \\\s*\n\s*--commit "\$GITHUB_SHA"/,
    "the release workflow hands the build's own commit to the manifest");
  assert.match(workflow, /--commit "\$GITHUB_SHA" --branch "\$GITHUB_REF_NAME"/,
    "and the notes are written from the same commit");
});

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nlatest.json is the shape the updater reads");
process.exit(fails.length ? 1 : 0);
