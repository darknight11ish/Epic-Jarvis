package com.jarvis.client

import com.jarvis.client.net.UpdateCheck
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The update path's transport is pinned (2026-10-20 Android audit, Area 10D):
 * HTTPS only, GitHub's own hosts only, the app's own pinned signing
 * certificate checked BEFORE the file is offered to Android's installer, and
 * no user-installed CA is ever trusted for it.
 *
 * The download/verify logic itself is `net/UpdateCheck.kt` (pure, tested in
 * `UpdateCheckTest`) and `platform/UpdateChecker.kt` (Android). These checks
 * cover what those two files do NOT: the network security config and the
 * manifest, plus the source pins that the certificate gate cannot be
 * side-stepped.
 */
class UpdateSecurityTest {

    private fun config(): String =
        SourceFile.read("jarvis-client/app/src/main/res/xml/network_security_config.xml")

    private fun manifest(): String =
        SourceFile.read("jarvis-client/app/src/main/AndroidManifest.xml")

    private fun checker(): String =
        SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/platform/UpdateChecker.kt")

    @Test
    fun `the update address and the release page are HTTPS on GitHub`() {
        assertTrue(UpdateCheck.URL.startsWith("https://api.github.com/"))
        assertTrue(UpdateCheck.RELEASE_PAGE.startsWith("https://github.com/"))
        assertTrue(UpdateCheck.REPO_URL.startsWith("https://github.com/"))
        // The signing certificate pin is a real SHA-256, not a placeholder.
        assertEquals(64, UpdateCheck.SIGNER_SHA256.length)
        assertTrue(UpdateCheck.SIGNER_SHA256.all { it in "0123456789abcdef" })
    }

    @Test
    fun `the download URL must be an https GitHub release asset of THIS repository`() {
        assertTrue(
            UpdateCheck.isReleaseDownload(
                "https://github.com/darknight11ish/Epic-Jarvis/releases/download/client-latest/" +
                    "jarvis-client-4cc383c.apk",
            ),
        )
        for (bad in listOf(
            "http://github.com/darknight11ish/Epic-Jarvis/releases/download/client-latest/x.apk",
            "https://evil.example/x.apk",
            "https://github.com/someone-else/Epic-Jarvis/releases/download/client-latest/x.apk",
            "https://user:pw@github.com/darknight11ish/Epic-Jarvis/releases/download/client-latest/x.apk",
            "ftp://github.com/darknight11ish/Epic-Jarvis/releases/download/x.apk",
        )) {
            assertFalse(bad, UpdateCheck.isReleaseDownload(bad))
        }
        // GitHub's asset redirect hosts are the only other hosts accepted, and
        // only for github.com names.
        assertTrue(UpdateCheck.isGithubHost("github.com"))
        assertTrue(UpdateCheck.isGithubHost("objects.githubusercontent.com"))
        for (bad in listOf("evil.example", "github.com.evil.example", "notgithub.com", "github.com.evil")) {
            assertFalse(bad, UpdateCheck.isGithubHost(bad))
        }
    }

    @Test
    fun `the network security config forbids cleartext and trusts no user CA`() {
        val xml = config()
        assertTrue(xml.contains("<base-config cleartextTrafficPermitted=\"false\""))
        // The one cleartext exception is the owner's own mesh hostnames.
        assertTrue(xml.contains("cleartextTrafficPermitted=\"true\""))
        assertTrue(xml.contains("ts.net"))
        assertTrue(xml.contains("nord"))
        // No user-installed certificate may ever be trusted by this app.
        assertFalse("the app must not trust user-installed CAs", xml.contains("src=\"user\""))
        assertFalse(xml.contains("<certificates"))
        // The manifest points at this config and does not override it.
        assertTrue(manifest().contains("android:networkSecurityConfig=\"@xml/network_security_config\""))
        assertFalse(manifest().contains("usesCleartextTraffic"))
    }

    @Test
    fun `the certificate is checked before the installer, and the update check follows no redirect`() {
        val src = checker()
        // The check request itself follows no redirect at all.
        assertTrue(src.contains(".followRedirects(false)"))
        assertTrue(src.contains(".followSslRedirects(false)"))
        // The download URL is re-checked immediately before the fetch.
        assertTrue(src.contains("!UpdateCheck.isReleaseDownload(url)"))
        // Every hop of the redirect chain is checked to be a GitHub host.
        assertTrue(src.contains("UpdateCheck.isGithubHost(response.request.url.host)"))
        // The pinned signing certificate is read out of the file, and the
        // Ready state (the only one `install` accepts) comes only from a match.
        assertTrue(src.contains("UpdateCheck.afterFetch("))
        assertTrue(src.contains("PackageManager.GET_SIGNING_CERTIFICATES"))
        assertTrue(src.contains("_download.value as? UpdateCheck.Download.Ready ?: return false"))
        // No custom trust manager, no cleartext, no second http client config.
        assertFalse(src.contains("X509TrustManager"))
        assertFalse(src.contains("setSslSocketFactory"))
        assertFalse(src.contains("http://"))
    }
}
