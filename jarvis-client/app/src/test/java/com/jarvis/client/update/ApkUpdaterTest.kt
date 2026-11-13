package com.jarvis.client.update

import com.jarvis.client.SourceFile
import com.jarvis.client.net.UpdateCheck
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

/**
 * The sha256-pinned update manifest (2026-11-13, the copy-over wave).
 *
 * Adapted from Mobile-Harness's `AppUpdater.kt` + `mobile-harness-update.json`
 * (MIT; see `ApkUpdater.kt`'s header and THIRD-PARTY-NOTICES.txt). The phone
 * ALREADY had a downloader and a certificate pin (`net/UpdateCheck.kt`,
 * `platform/UpdateChecker.kt`); this adds the manifest half and holds it to
 * three rules:
 *
 *  1. THE PARSER IS STRICT. A body missing a field, carrying a bad SHA-256, a
 *     URL off this repository, or a size outside the app's own cap is
 *     unreadable - and an unreadable manifest downloads nothing.
 *  2. A FILE MUST MATCH THE MANIFEST. Size and SHA-256 are both checked; a
 *     mismatch is refused with the reason and the bytes are deleted, which is
 *     pinned in the caller's source as well as here.
 *  3. NOTHING INSTALLS ITSELF. `ApkUpdater` has no installer code at all, and
 *     the screen's Install button is drawn only in the `Ready` state that both
 *     gates produce.
 *
 * The CI side is pinned too: the publish step must write the same field names
 * this parser reads, and its versionCode formula must be the one
 * `build.gradle.kts` uses. A manifest and an app that disagree is a feature
 * that refuses every genuine update.
 */
class ApkUpdaterTest {

    @get:Rule
    val tmp = TemporaryFolder()

    private val apkUrl =
        "https://github.com/darknight11ish/Epic-Jarvis/releases/download/client-latest/" +
            "jarvis-client-abcdef1.apk"

    private fun apk(bytes: ByteArray): File = tmp.newFile().also { it.writeBytes(bytes) }

    private fun manifestJson(
        sha: String,
        size: Long,
        url: String = apkUrl,
        versionCode: Long = 1_000_000_123L,
        versionName: String = "0.2.123",
    ): String = """
        {
          "versionName": "$versionName",
          "versionCode": $versionCode,
          "apkUrl": "$url",
          "sha256": "$sha",
          "sizeBytes": $size,
          "builtAt": "2026-11-13 12:00 UTC",
          "commit": "abcdef1234567890"
        }
    """.trimIndent()

    private fun found(body: String): ApkManifest = when (val read = ApkUpdater.read(body)) {
        is ApkUpdater.Read.Found -> read.manifest
        is ApkUpdater.Read.Unreadable -> throw AssertionError("unreadable: ${read.why}")
    }

    // ------------------------------------------------------------- the parser

    @Test
    fun `the manifest CI writes is read exactly`() {
        val bytes = "not really an apk".toByteArray()
        val file = apk(bytes)
        val sha = ApkUpdater.sha256(file)
        val manifest = found(manifestJson(sha, bytes.size.toLong()))
        assertEquals("0.2.123", manifest.versionName)
        assertEquals(1_000_000_123L, manifest.versionCode)
        assertEquals(apkUrl, manifest.apkUrl)
        assertEquals(sha, manifest.sha256)
        assertEquals(bytes.size.toLong(), manifest.sizeBytes)
        assertEquals("2026-11-13 12:00 UTC", manifest.builtAt)
    }

    @Test
    fun `a manifest missing or lying about a field is unreadable`() {
        val good = found(manifestJson("a".repeat(64), 10))
        val bad = listOf(
            "not json at all",
            "[]",
            """{"versionName":"0.2.1"}""",
            manifestJson("a".repeat(64), 10).replace("\"versionCode\": 1000000123", "\"versionCode\": \"1000000123\""),
            manifestJson("a".repeat(64), 10).replace("\"versionCode\": 1000000123", "\"versionCode\": 0"),
            manifestJson("a".repeat(64), 10).replace("\"sha256\": \"${"a".repeat(64)}\"", "\"sha256\": \"abc\""),
            manifestJson("A".repeat(64), 10), // uppercase is refused; CI writes lowercase
            manifestJson("a".repeat(64), 10).replace("\"sizeBytes\": 10", "\"sizeBytes\": 0"),
            manifestJson("a".repeat(64), 10).replace("\"sizeBytes\": 10", "\"sizeBytes\": 999999999999"),
            manifestJson("a".repeat(64), 10).replace(apkUrl, "http://github.com/darknight11ish/Epic-Jarvis/x.apk"),
            manifestJson("a".repeat(64), 10).replace(
                apkUrl,
                "https://github.com/someone-else/Epic-Jarvis/releases/download/client-latest/x.apk",
            ),
            manifestJson("a".repeat(64), 10).replace("\"versionName\": \"0.2.123\"", "\"versionName\": \"\""),
        )
        for (body in bad) {
            val read = ApkUpdater.read(body)
            assertTrue("this should be unreadable: $body", read is ApkUpdater.Read.Unreadable)
            assertTrue((read as ApkUpdater.Read.Unreadable).why.isNotBlank())
        }
        // ...and the good one still parses, so the list above is not passing
        // because every manifest is refused.
        assertEquals(good.apkUrl, found(manifestJson("a".repeat(64), 10)).apkUrl)
    }

    @Test
    fun `the manifest address must be this repository's live release asset`() {
        assertTrue(ApkUpdater.isManifestUrl(ApkUpdater.MANIFEST_URL))
        assertTrue(ApkUpdater.MANIFEST_URL.startsWith("https://github.com/darknight11ish/Epic-Jarvis/"))
        assertTrue(ApkUpdater.MANIFEST_URL.endsWith("/client-latest.json"))
        for (bad in listOf(
            "http://github.com/darknight11ish/Epic-Jarvis/releases/download/client-latest/client-latest.json",
            "https://evil.example/client-latest.json",
            "https://github.com/someone-else/Epic-Jarvis/releases/download/client-latest/client-latest.json",
            "https://github.com/darknight11ish/Epic-Jarvis/releases/download/client-latest/other.json",
        )) {
            assertFalse(bad, ApkUpdater.isManifestUrl(bad))
        }
        // The APK and the manifest live in the same release folder.
        assertTrue(ApkUpdater.MANIFEST_URL.startsWith(UpdateCheck.REPO_URL + "/releases/download/client-latest/"))
    }

    @Test
    fun `only a newer version is offered`() {
        val manifest = found(manifestJson("a".repeat(64), 10, versionCode = 1_000_000_123L))
        assertTrue(ApkUpdater.isNewer(manifest, 1_000_000_122L))
        assertFalse(ApkUpdater.isNewer(manifest, 1_000_000_123L))
        assertFalse(ApkUpdater.isNewer(manifest, 1_000_000_124L))
    }

    @Test
    fun `a checksum is exactly 64 lowercase hex characters`() {
        assertTrue(ApkUpdater.isSha256("0123456789abcdef".repeat(4)))
        assertFalse(ApkUpdater.isSha256("0123456789ABCDEF".repeat(4)))
        assertFalse(ApkUpdater.isSha256("0123456789abcdef".repeat(4).dropLast(1)))
        assertFalse(ApkUpdater.isSha256("z".repeat(64)))
    }

    @Test
    fun `a non-200 answer is a stated reason, not silence`() {
        val read = ApkUpdater.httpProblem(404)
        assertTrue(read is ApkUpdater.Read.Unreadable)
        assertTrue((read as ApkUpdater.Read.Unreadable).why.contains("HTTP 404"))
        assertTrue(read.why.contains("nothing was downloaded"))
    }

    // ------------------------------------------------------------ the verifier

    @Test
    fun `a file that matches the manifest is accepted`() {
        val bytes = ByteArray(4096) { (it % 251).toByte() }
        val file = apk(bytes)
        val manifest = found(manifestJson(ApkUpdater.sha256(file), file.length()))
        val verdict = ApkUpdater.verify(file, manifest, apkUrl)
        assertTrue(verdict is ApkUpdater.Verdict.Matches)
    }

    @Test
    fun `a size mismatch is refused with both numbers`() {
        val file = apk(ByteArray(100))
        val manifest = found(manifestJson(ApkUpdater.sha256(file), 101))
        val refused = ApkUpdater.verify(file, manifest, apkUrl) as ApkUpdater.Verdict.Refused
        assertTrue(refused.why.contains("size"))
        assertTrue(refused.why.contains("expected 101"))
        assertTrue(refused.why.contains("got 100"))
        assertTrue(refused.why.contains("deleted"))
    }

    @Test
    fun `a sha256 mismatch is refused, and says what was checked`() {
        val file = apk("the file CI did not build".toByteArray())
        val other = apk("the file CI claimed to build".toByteArray())
        val manifest = found(manifestJson(ApkUpdater.sha256(other), file.length()))
        val refused = ApkUpdater.verify(file, manifest, apkUrl) as ApkUpdater.Verdict.Refused
        assertEquals(ApkUpdater.CHECKSUM_MISMATCH, refused.why)
        assertTrue(refused.why.contains("SHA-256"))
        assertTrue(refused.why.contains("deleted"))
    }

    @Test
    fun `a manifest for a different file is refused before hashing`() {
        val file = apk(ByteArray(10))
        val manifest = found(manifestJson(ApkUpdater.sha256(file), file.length()))
        val refused = ApkUpdater.verify(file, manifest, apkUrl.replace("abcdef1", "9999999")) as
            ApkUpdater.Verdict.Refused
        assertEquals(ApkUpdater.WRONG_FILE, refused.why)
    }

    @Test
    fun `the caller deletes a refused file and never keeps a partial download`() {
        val checker = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/platform/UpdateChecker.kt",
        )
        val delete = checker.indexOf("saved.file.delete()")
        val refused = checker.indexOf("UpdateCheck.Download.Refused(verdict.why)")
        assertTrue("a refusal does not delete the downloaded file", delete in 0 until refused)
        // The manifest is fetched BEFORE the APK, so an unreadable manifest
        // never costs a download at all.
        val manifestFetch = checker.indexOf("fetchManifest()")
        val apkFetch = checker.indexOf("fetchApk(context, url")
        assertTrue("the APK is fetched before its checksum is known", manifestFetch in 0 until apkFetch)
        // The broken download of the part file is still deleted on every path.
        assertTrue(checker.contains("part.delete()"))
    }

    // ------------------------------------------------------ no auto-install

    @Test
    fun `the updater has no installer in it`() {
        val src = SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/update/ApkUpdater.kt")
        // Code shapes, not bare words: the file's own header explains what it
        // does NOT do, and that comment names these APIs.
        for (forbidden in listOf("Intent(", "startActivity(", "PackageInstaller(", "FileProvider.", "ACTION_INSTALL")) {
            assertFalse("ApkUpdater must not contain $forbidden", src.contains(forbidden))
        }
        assertFalse("ApkUpdater must not install anything", src.contains("fun install"))
        assertFalse("ApkUpdater must not be an Activity or a service", src.contains(": Activity"))
    }

    @Test
    fun `Install is drawn only for a file both gates accepted`() {
        val screen = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/ReadinessScreen.kt",
        )
        val ready = screen.indexOf("is UpdateCheck.Download.Ready -> {")
        val installText = screen.indexOf("\"Install update\"")
        val refused = screen.indexOf("is UpdateCheck.Download.Refused ->")
        assertTrue("the Ready branch is missing", ready > 0)
        assertTrue("the Install button is not inside the Ready branch", installText in ready until refused)
        // Download is a button too - no call site before a press.
        val downloadText = screen.indexOf("\"Download update\"")
        // Download is offered only after a refusal/empty state, never before a tap.
        assertTrue(downloadText > installText)
        // The install step itself is UpdateChecker.install(), and its only
        // caller is the Install button's own wiring in MainActivity.
        val activity = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt",
        )
        assertEquals(
            "install() must be wired to exactly one control",
            1,
            Regex("updates\\.install\\(").findAll(activity).count(),
        )
        assertTrue(activity.contains("onInstallUpdate = {"))
    }

    // ------------------------------------------------- the CI side of the contract

    @Test
    fun `CI publishes the manifest this parser reads, and keeps it`() {
        val workflow = SourceFile.read(".github/workflows/jarvis-client.yml")
        // The asset and every field the parser requires.
        assertTrue(workflow.contains("client-latest.json"))
        for (field in listOf("versionName", "versionCode", "apkUrl", "sha256", "sizeBytes")) {
            assertTrue("the publish step never writes $field", workflow.contains("\"$field\":"))
        }
        // Uploaded with the APK, on both the "release exists" and "first
        // publish" paths...
        assertTrue(
            workflow.contains(
                "gh release upload \"\$TAG\" \"jarvis-client/artifacts/\$apk\" \"jarvis-client/artifacts/\$manifest\"",
            ),
        )
        assertTrue(
            workflow.contains(
                "gh release create \"\$TAG\" \"jarvis-client/artifacts/\$apk\" \"jarvis-client/artifacts/\$manifest\"",
            ),
        )
        // ...and NOT deleted with the previous build's assets.
        assertTrue(workflow.contains("[ \"\$old\" != \"\$manifest\" ]"))
        // The manifest is checked against the file that was just hashed.
        assertTrue(workflow.contains("grep -q \"\\\"sha256\\\": \\\"\$file_sha\\\"\""))
    }

    @Test
    fun `the workflow's versionCode is build dot gradle's versionCode`() {
        val gradle = SourceFile.read("jarvis-client/app/build.gradle.kts")
        val workflow = SourceFile.read(".github/workflows/jarvis-client.yml")
        val base = Regex("VERSION_CODE_BASE = ([0-9_]+)").find(gradle)?.groupValues?.get(1)
            ?.replace("_", "")?.toLong()
            ?: throw AssertionError("build.gradle.kts has no VERSION_CODE_BASE")
        val inWorkflow = Regex("version_code=\\$\\(\\(([0-9]+) \\+ GITHUB_RUN_NUMBER\\)\\)")
            .find(workflow)?.groupValues?.get(1)?.toLong()
            ?: throw AssertionError("the publish step does not compute version_code from the run number")
        assertEquals(
            "the manifest's versionCode would not be the number the APK carries",
            base,
            inWorkflow,
        )
        // And the app's own check uses BuildConfig.VERSION_CODE, which is that
        // same base plus the run number.
        assertTrue(gradle.contains("fun buildVersionCode(): Int = VERSION_CODE_BASE + (ciRunNumber() ?: 0)"))
    }
}
