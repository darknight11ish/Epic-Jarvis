/*
 * Adapted for Jarvis from Mobile-Harness:
 *   app/src/main/java/com/jarves/mh/update/AppUpdater.kt
 *   mobile-harness-update.json
 *   Copyright (c) 2026 Mobile Harness Contributors
 *   https://github.com/techjarves/Mobile-Harness  (MIT License)
 *
 * Licensed under the MIT License. The full notice and licence text travel with
 * this app: THIRD-PARTY-NOTICES.txt at the top of the repository, and
 * jarvis-client/app/src/main/assets/licenses/NOTICES.txt inside the APK.
 *
 * WHY THIS IS NOT A SECOND UPDATER. jarvis-client already downloads a new APK
 * from its own `client-latest` release and checks the file's signing
 * certificate against the digest pinned in the app (`net/UpdateCheck.kt`,
 * `platform/UpdateChecker.kt`, added 2026-10-11). Replacing that would throw
 * away a gate that is already audited and pinned by `UpdateSecurityTest`, so
 * what this file adapts from AppUpdater is the MISSING half: the little
 * sha256/size manifest CI publishes next to the APK, and the rule that a
 * download is offered for install only when it matches that manifest. The
 * existing fetch and certificate check stay exactly where they are, and the
 * two gates are ANDed: a file must match the published checksum AND be signed
 * by Jarvis's key before the Install button can appear.
 *
 * WHAT THIS FILE DELIBERATELY DOES NOT DO:
 *  - it never installs anything, and has no `Intent`, `PackageInstaller` or
 *    `startActivity` anywhere: the install step is Android's own installer
 *    prompt, opened by `UpdateChecker.install()` from the owner's tap;
 *  - it never downloads anything by itself: `UpdateChecker.download()` runs
 *    only from the Download button on Platform checks;
 *  - it never trusts the manifest's address beyond `UpdateCheck`'s existing
 *    "an https release asset of THIS repository" rule.
 *
 * Everything here is plain JVM (no `android.*`), so `ApkUpdaterTest` proves the
 * parser, the verifier and the refusal words without an emulator.
 */

package com.jarvis.client.update

import com.jarvis.client.net.UpdateCheck
import java.io.File
import java.security.MessageDigest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.longOrNull

/**
 * The manifest CI publishes as `client-latest.json` beside the APK on the
 * rolling `client-latest` release.
 *
 * The numbers here are the ones the publish step just measured from the file
 * it uploaded - `sha256` is over the APK's bytes, not over the manifest - so a
 * download that matches them is the same file CI built and smoke-tested.
 */
data class ApkManifest(
    val versionCode: Long,
    val versionName: String,
    val apkUrl: String,
    val sha256: String,
    val sizeBytes: Long,
    /** Free text from CI, for the refusal/success line; null when absent. */
    val builtAt: String? = null,
)

object ApkUpdater {

    /**
     * Where the manifest lives. Fixed here, never taken from a reply: the app
     * fetches its own idea of the release's manifest, and [isManifestUrl]
     * re-checks it immediately before the request.
     */
    const val MANIFEST_URL =
        "https://github.com/darknight11ish/Epic-Jarvis/releases/download/client-latest/client-latest.json"

    /** The asset's name on the release. The publish step writes exactly this. */
    const val MANIFEST_ASSET = "client-latest.json"

    /** A manifest is a few hundred bytes. Anything past this is not one. */
    const val MAX_MANIFEST_BYTES = 64 * 1024

    /** The only length a SHA-256 hex digest can be. */
    const val SHA256_CHARS = 64

    // ---------------------------------------------------------- plain words
    // Every refusal ends with the file gone and the reason shown. There is no
    // path here that offers a file it could not verify.

    const val NO_MANIFEST =
        "The checksum file for this build could not be read from GitHub, so nothing was downloaded."

    const val NOT_NEWER =
        "The build GitHub publishes is not newer than the one on this phone, so nothing was downloaded."

    const val WRONG_FILE =
        "The checksum published for this build names a different file, so the download was deleted " +
            "and not offered for install."

    const val SIZE_MISMATCH =
        "The downloaded file is not the size the build published, so it was deleted and not offered " +
            "for install."

    const val CHECKSUM_MISMATCH =
        "The downloaded file does not match the SHA-256 checksum published for this build, so it was " +
            "deleted and not offered for install."

    const val UNREADABLE =
        "The downloaded file could not be checked against the published checksum, so it was deleted " +
            "and not offered for install."

    /** What the parser found, or why it could not use the answer. */
    sealed interface Read {
        data class Found(val manifest: ApkManifest) : Read
        data class Unreadable(val why: String) : Read
    }

    /** The result of checking one downloaded file against one manifest. */
    sealed interface Verdict {
        data class Matches(val manifest: ApkManifest) : Verdict
        data class Refused(val why: String) : Verdict
    }

    /**
     * Whether [url] is this repository's own `client-latest.json` release
     * asset. The same "https, GitHub, this repository's release path" rule as
     * the APK itself ([UpdateCheck.isReleaseDownload]), plus the file name.
     */
    fun isManifestUrl(url: String): Boolean {
        val u = url.trim()
        if (!UpdateCheck.isReleaseDownload(u)) return false
        return u.substringAfterLast('/') == MANIFEST_ASSET
    }

    /**
     * Reads and validates the manifest body. STRICT: every field the verifier
     * uses must be present and sane, or the answer is "unreadable" and nothing
     * is downloaded. A manifest that cannot be trusted is not a manifest.
     */
    fun read(body: String): Read {
        val root = runCatching { Json.parseToJsonElement(body) as? JsonObject }.getOrNull()
            ?: return Read.Unreadable(NO_MANIFEST)
        val versionCode = root.long("versionCode") ?: return Read.Unreadable(NO_MANIFEST)
        // Android's versionCode ceiling, and 0 means "CI did not say".
        if (versionCode !in 1..2_100_000_000L) return Read.Unreadable(NO_MANIFEST)
        val versionName = root.text("versionName")?.trim()?.takeIf { it.isNotEmpty() && it.length <= 40 }
            ?: return Read.Unreadable(NO_MANIFEST)
        val apkUrl = root.text("apkUrl")?.trim()?.takeIf { UpdateCheck.isReleaseDownload(it) }
            ?: return Read.Unreadable(NO_MANIFEST)
        val sha = root.text("sha256")?.trim()?.takeIf { isSha256(it) }
            ?: return Read.Unreadable(NO_MANIFEST)
        val size = root.long("sizeBytes") ?: return Read.Unreadable(NO_MANIFEST)
        if (size !in 1..UpdateCheck.MAX_APK_BYTES) return Read.Unreadable(NO_MANIFEST)
        return Read.Found(
            ApkManifest(
                versionCode = versionCode,
                versionName = versionName,
                apkUrl = apkUrl,
                sha256 = sha,
                sizeBytes = size,
                builtAt = root.text("builtAt")?.trim()?.takeIf { it.isNotEmpty() },
            ),
        )
    }

    /** Whether the published build is newer than the one installed. */
    fun isNewer(manifest: ApkManifest, ownVersionCode: Long): Boolean =
        manifest.versionCode > ownVersionCode

    /**
     * Checks a downloaded file against the manifest: the address it came from,
     * its size, then its SHA-256. Size is checked before the hash because it is
     * free, and the hash is what actually decides.
     */
    fun verify(file: File, manifest: ApkManifest, downloadedFrom: String?): Verdict {
        if (downloadedFrom != null && manifest.apkUrl != downloadedFrom) return Verdict.Refused(WRONG_FILE)
        val actualSize = file.length()
        if (actualSize != manifest.sizeBytes) {
            return Verdict.Refused("$SIZE_MISMATCH (expected ${manifest.sizeBytes} bytes, got $actualSize.)")
        }
        val actual = sha256(file)
        if (!actual.equals(manifest.sha256, ignoreCase = true)) {
            return Verdict.Refused(CHECKSUM_MISMATCH)
        }
        return Verdict.Matches(manifest)
    }

    /** The SHA-256 of a file, lowercase hex - the same shape CI writes. */
    fun sha256(file: File): String = file.inputStream().use { input ->
        val digest = MessageDigest.getInstance("SHA-256")
        val buffer = ByteArray(128 * 1024)
        while (true) {
            val count = input.read(buffer)
            if (count < 0) break
            digest.update(buffer, 0, count)
        }
        digest.digest().joinToString("") { "%02x".format(it) }
    }

    /** Whether [value] is exactly a lowercase 64-character hex digest. */
    fun isSha256(value: String): Boolean =
        value.length == SHA256_CHARS && value.all { it in "0123456789abcdef" }

    /** Plain words for a manifest request GitHub answered with a non-200. */
    fun httpProblem(code: Int): Read = Read.Unreadable(
        "The checksum file for this build is not on GitHub (HTTP $code), so nothing was downloaded.",
    )

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject.long(key: String): Long? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString.not() }?.longOrNull
}
