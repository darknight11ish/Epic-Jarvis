/**
 * Writes `latest.json`, the small file the desktop's updater reads.
 *
 * Run by .github/workflows/desktop-release.yml after a SIGNED build, never by
 * hand. The app fetches this file from the rolling `desktop-latest` release
 * (tauri.conf.json, plugins.updater.endpoints), compares `version` with its
 * own, and - only when the owner presses Install - downloads the installer
 * named here and checks it against `signature` with the public key built
 * into the app. A download whose signature does not match is refused.
 *
 * Three platform keys point at the installers, because Tauri 2 looks for
 * `windows-x86_64-<installer>` first (the kind the app was installed with)
 * and falls back to `windows-x86_64`. The fallback is the NSIS installer:
 * tauri.conf.json installs per-user with NSIS, which needs no admin prompt.
 *
 *   node scripts/updater-manifest.mjs --version 0.1.42 --commit 0c15f81 \
 *     --base-url https://github.com/<owner>/<repo>/releases/download/desktop-latest \
 *     --nsis dist/jarvis-desktop_0.1.42_x64-setup.exe \
 *     --msi dist/jarvis-desktop_0.1.42_x64_en-US.msi \
 *     --notes "..." --out dist/latest.json
 *
 * `commit` is the source `HEAD` the build came from. The release notes already
 * SAY it in prose ("from commit 0c15f81 on main"); this makes it a field a
 * program can read, which is what Gemini's ruling Q8 (2026-11-15) asked for -
 * three pieces (desktop, phone APK, backend) sat at three commits and nothing
 * said so. It is OPTIONAL and never invented: a run without `--commit` writes
 * a manifest with no `commit` key at all, so a reader can tell "not recorded"
 * from a value, and an invalid one is refused rather than published.
 *
 * Each installer's signature is read from the file beside it with `.sig`
 * appended, which is where `tauri build` writes it.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { basename } from "node:path";
import { fileURLToPath } from "node:url";

const SEMVER = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/;
/** A git commit as this manifest records it: lower-case hex, 7 to 40. */
const COMMIT = /^[0-9a-f]{7,40}$/;

/** The commit as the manifest writes it, or "" when the caller did not say. */
export function commitField(commit) {
  const sha = String(commit || "").trim().toLowerCase();
  if (!sha) return "";
  if (!COMMIT.test(sha)) {
    throw new Error(`commit must be a hex sha of 7 to 40 characters, got ${JSON.stringify(commit)}`);
  }
  return sha;
}

/** The manifest itself, from values already read. Pure, so it can be tested. */
export function buildManifest({ version, notes = "", pubDate, baseUrl, nsis, msi, commit }) {
  if (!SEMVER.test(String(version || ""))) {
    throw new Error(`version must look like 1.2.3, got ${JSON.stringify(version)}`);
  }
  if (!/^https:\/\//.test(String(baseUrl || ""))) {
    throw new Error("base URL must be https");
  }
  if (!nsis || !nsis.name || !nsis.signature) {
    throw new Error("the NSIS installer and its signature are required");
  }
  const base = String(baseUrl).replace(/\/+$/, "");
  const entry = (file) => {
    const signature = String(file.signature).trim();
    if (!signature || /\s/.test(signature)) {
      throw new Error(`signature for ${file.name} is empty or has spaces in it`);
    }
    return { signature, url: `${base}/${encodeURIComponent(file.name)}` };
  };
  const platforms = {
    "windows-x86_64": entry(nsis),
    "windows-x86_64-nsis": entry(nsis),
  };
  if (msi && msi.name && msi.signature) platforms["windows-x86_64-msi"] = entry(msi);
  const date = pubDate instanceof Date ? pubDate : new Date(pubDate || Date.now());
  const manifest = {
    version: String(version),
    notes: String(notes),
    // RFC 3339, without milliseconds.
    pub_date: date.toISOString().replace(/\.\d{3}Z$/, "Z"),
    platforms,
  };
  // Only when the caller named one: an absent key is "not recorded", which a
  // reader can act on, while `"commit": ""` would invite a comparison with
  // nothing. The workflow always passes the commit it is building.
  const sha = commitField(commit);
  if (sha) manifest.commit = sha;
  return manifest;
}

function args(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i];
    if (!key.startsWith("--") || i + 1 >= argv.length) {
      throw new Error(`expected --name value pairs, got ${key}`);
    }
    out[key.slice(2)] = argv[i + 1];
  }
  return out;
}

function installer(path) {
  if (!path) return null;
  return { name: basename(path), signature: readFileSync(`${path}.sig`, "utf8") };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const a = args(process.argv.slice(2));
  const manifest = buildManifest({
    version: a.version,
    notes: a.notes || "",
    baseUrl: a["base-url"],
    nsis: installer(a.nsis),
    msi: installer(a.msi),
    commit: a.commit,
  });
  const text = `${JSON.stringify(manifest, null, 2)}\n`;
  if (a.out) writeFileSync(a.out, text);
  else process.stdout.write(text);
  console.error(`latest.json: version ${manifest.version}, ` +
    `${manifest.commit ? `commit ${manifest.commit}, ` : "no commit recorded, "}` +
    `${Object.keys(manifest.platforms).length} platform entries`);
}
