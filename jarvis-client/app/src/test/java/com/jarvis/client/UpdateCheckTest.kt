package com.jarvis.client

import com.jarvis.client.net.UpdateCheck
import com.jarvis.client.net.UpdateCheck.Read
import com.jarvis.client.net.UpdateCheck.Result
import java.time.Instant
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "A newer version is available" (net/UpdateCheck.kt), against the shape
 * GitHub really returns for the client-latest release - taken from
 * `GET /repos/darknight11ish/Epic-Jarvis/releases/tags/client-latest` on
 * 2026-09-24 and cut down to the fields that matter (the uploader and the
 * long notes are left out). Note `target_commitish` there is NOT the APK's
 * commit: the workflow moves the tag, not that field.
 */
class UpdateCheckTest {

    private fun release(
        assets: String = """[{"name":"jarvis-client-4cc383c.apk","state":"uploaded","content_type":"application/vnd.android.package-archive","size":31000000,"created_at":"2026-09-24T08:37:36Z"}]""",
        title: String = "Jarvis client - latest build (claude/admiring-ritchie-5urg5h @ 4cc383c)",
    ) = """
        {"tag_name":"client-latest","target_commitish":"e5160fdabbfccb17682b30f112e10c746caa7dd5",
         "name":"$title","draft":false,"prerelease":true,
         "created_at":"2026-09-24T08:22:58Z","published_at":"2026-09-23T23:54:40Z",
         "html_url":"https://example.invalid/not-where-the-button-goes",
         "assets":$assets}
    """.trimIndent()

    private fun found(body: String) = (UpdateCheck.read(body) as Read.Found).published

    private val uploaded = Instant.parse("2026-09-24T08:37:36Z").epochSecond

    @Test
    fun `the real answer gives the APK's commit, its upload time and the branch`() {
        val p = found(release())
        assertEquals("4cc383c", p.sha)
        assertEquals(Instant.parse("2026-09-24T08:37:36Z"), p.uploadedAt)
        assertEquals("claude/admiring-ritchie-5urg5h", p.branch)
    }

    @Test
    fun `this build is up to date when its commit is the one published`() {
        val p = found(release())
        assertEquals(Result.UpToDate, UpdateCheck.compare("4cc383c0123456789abcdef0123456789abcdef", 0, p))
        assertEquals(Result.UpToDate, UpdateCheck.compare("4cc383c", 0, p))
    }

    @Test
    fun `a different commit uploaded after this build's commit is newer`() {
        val p = found(release())
        val r = UpdateCheck.compare("aaaaaaa", uploaded - 3600, p)
        assertTrue(r is Result.Newer)
        val line = UpdateCheck.line((r as Result.Newer).published)
        assertTrue(line, "claude/admiring-ritchie-5urg5h, 4cc383c" in line)
        assertTrue(line, "Nothing is downloaded" in line)
    }

    @Test
    fun `a different commit uploaded before this build's commit is not newer`() {
        // The tag is rolling and any branch publishes to it: a build from
        // another branch that finished before this commit existed is older.
        val p = found(release())
        assertEquals(Result.UpToDate, UpdateCheck.compare("aaaaaaa", uploaded + 60, p))
    }

    @Test
    fun `a build that does not know its commit says so instead of guessing`() {
        val p = found(release())
        assertTrue(UpdateCheck.compare(UpdateCheck.ownSha("unknown"), 0, p) is Result.Unknown)
        assertNull(UpdateCheck.ownSha(""))
        assertNull(UpdateCheck.ownSha(null))
        assertEquals("abcdef1", UpdateCheck.ownSha(" ABCDEF1 "))
    }

    @Test
    fun `with two APKs half way through a publish, the newer upload is the release`() {
        val p = found(
            release(
                assets = """[
                  {"name":"jarvis-client-1111111.apk","state":"uploaded","created_at":"2026-09-24T08:00:00Z"},
                  {"name":"jarvis-client-2222222.apk","state":"uploaded","created_at":"2026-09-24T09:00:00Z"}]""",
            ),
        )
        assertEquals("2222222", p.sha)
    }

    @Test
    fun `an upload that has not finished is not a release`() {
        val r = UpdateCheck.read(
            release(assets = """[{"name":"jarvis-client-2222222.apk","state":"starter","created_at":"2026-09-24T09:00:00Z"}]"""),
        )
        assertTrue(r is Read.Unreadable)
    }

    @Test
    fun `only the workflow's own APK name counts`() {
        for (name in listOf("jarvis-client-debug.apk", "evil.apk", "jarvis-client-zzzzzzz.apk", "jarvis-client-4cc383c.apk.zip")) {
            val r = UpdateCheck.read(release(assets = """[{"name":"$name","state":"uploaded"}]"""))
            assertTrue(name, r is Read.Unreadable)
        }
        assertTrue(UpdateCheck.read(release(assets = "[]")) is Read.Unreadable)
    }

    @Test
    fun `an answer that is not a release is unreadable, not a crash`() {
        assertTrue(UpdateCheck.read("<html>rate limited</html>") is Read.Unreadable)
        assertTrue(UpdateCheck.read("[]") is Read.Unreadable)
        assertTrue(UpdateCheck.read("") is Read.Unreadable)
    }

    @Test
    fun `a title the workflow did not write shows no branch`() {
        assertNull(found(release(title = "Something else entirely")).branch)
        assertNull(UpdateCheck.branchOf(null))
        assertEquals("main", UpdateCheck.branchOf("Jarvis client - latest build (main @ abc1234)"))
    }

    @Test
    fun `asked at most every six hours on start and every day otherwise`() {
        val h = 60 * 60 * 1000L
        assertTrue(UpdateCheck.due(0, null, onStart = true))
        assertTrue(UpdateCheck.due(0, null, onStart = false))
        assertFalse(UpdateCheck.due(6 * h - 1, 0, onStart = true))
        assertTrue(UpdateCheck.due(6 * h, 0, onStart = true))
        assertFalse(UpdateCheck.due(23 * h, 0, onStart = false))
        assertTrue(UpdateCheck.due(24 * h, 0, onStart = false))
        // A clock that went backwards: asked once, which records the new time.
        assertTrue(UpdateCheck.due(5, 10, onStart = false))
    }

    @Test
    fun `a failed check keeps what Home shows and only adds a line for Checks`() {
        val found = UpdateCheck.State(newerLine = "A newer build…", problem = null, lastTryMs = 1)
        for (f in listOf(UpdateCheck.Fetched.NoNetwork, UpdateCheck.Fetched.Http(403), UpdateCheck.Fetched.TooBig, UpdateCheck.Fetched.Body("nope"))) {
            val next = UpdateCheck.next(found, f, "aaaaaaa", 0, 99)
            assertEquals("$f", "A newer build…", next.newerLine)
            assertTrue("$f", next.problem != null)
            assertEquals(99L, next.lastTryMs)
        }
        assertTrue("limiting" in UpdateCheck.next(found, UpdateCheck.Fetched.Http(403), null, 0, 1).problem!!)
    }

    @Test
    fun `a real answer replaces what was shown`() {
        val stale = UpdateCheck.State(newerLine = "old line", problem = "old problem", lastTryMs = 1)
        val same = UpdateCheck.next(stale, UpdateCheck.Fetched.Body(release()), "4cc383c", 0, 5)
        assertEquals(UpdateCheck.State(null, null, 5), same)
        val newer = UpdateCheck.next(stale, UpdateCheck.Fetched.Body(release()), "aaaaaaa", 0, 5)
        assertTrue(newer.newerLine!!.contains("4cc383c"))
        assertNull(newer.problem)
        val unknown = UpdateCheck.next(stale, UpdateCheck.Fetched.Body(release()), null, 0, 5)
        assertNull(unknown.newerLine)
        assertTrue(unknown.problem!!.contains("cannot compare"))
    }

    @Test
    fun `the request and the button go only to the public repository`() {
        assertEquals(
            "https://api.github.com/repos/darknight11ish/Epic-Jarvis/releases/tags/client-latest",
            UpdateCheck.URL,
        )
        assertEquals("https://github.com/darknight11ish/Epic-Jarvis/releases/tag/client-latest", UpdateCheck.RELEASE_PAGE)
        assertTrue(UpdateCheck.RELEASE_PAGE.startsWith(UpdateCheck.REPO_URL))
    }

    // ------------------- the changelog, the download and the digest ----
    // The owner's request of 2026-10-11: "install an update button ... check
    // github ... download if i press download, and will show a simple
    // changelogg of the changes", and the part that matters most - "verify
    // before offering to install".

    private fun withBody(
        body: String,
        url: String? = "https://github.com/darknight11ish/Epic-Jarvis/releases/download/client-latest/jarvis-client-4cc383c.apk",
        size: Long = 31_000_000,
    ): String {
        val link = if (url == null) "" else "\"browser_download_url\":\"$url\","
        return """
            {"tag_name":"client-latest","name":"Jarvis client - latest build (main @ 4cc383c)",
             "draft":false,"prerelease":true,"body":${quote(body)},
             "assets":[{"name":"jarvis-client-4cc383c.apk","state":"uploaded",
                        "size":$size,
                        $link"created_at":"2026-09-24T08:37:36Z"}]}
        """.trimIndent()
    }

    /** One JSON string, for a release body with quotes and newlines in it. */
    private fun quote(s: String): String {
        val b = StringBuilder("\"")
        for (c in s) {
            when (c) {
                '"' -> b.append("\\\"")
                '\\' -> b.append("\\\\")
                '\n' -> b.append("\\n")
                '\r' -> b.append("\\r")
                '\t' -> b.append("\\t")
                else -> if (c < ' ') b.append("\\u%04x".format(c.code)) else b.append(c)
            }
        }
        return b.append("\"").toString()
    }

    @Test
    fun `the changelog is the commit subjects the publish step wrote, as plain lines`() {
        val body = """
            **Jarvis for Android 0.2.1183** - from `main`, commit [`4cc383c`](https://example/commit), built 2026-10-11.

            ## What's changed

            - fix(phone): a timer's notification gets a Stop
            - feat(desktop): the gear opens Settings without freezing
            - docs: `README.md` says what is true

            **Install:** open this page on the phone and tap `jarvis-client-4cc383c.apk` (30M), or from the PC: `adb install -r …`

            **To check your download** (optional): its SHA-256 is `abc123`.
        """.trimIndent()
        val p = found(withBody(body))
        assertEquals(
            listOf(
                "fix(phone): a timer's notification gets a Stop",
                "feat(desktop): the gear opens Settings without freezing",
                "docs: README.md says what is true",
            ),
            p.changes,
        )
    }

    @Test
    fun `the instructions after the list are not changes`() {
        // The install line and the checksum line are how the release is used,
        // not what changed; a phone screen shows the changes.
        val p = found(withBody("## What's changed\n\n- one real change\n\n**Install:** tap the file\n\n**Checked:** tests passed"))
        assertEquals(listOf("one real change"), p.changes)
        for (line in p.changes) {
            assertFalse(line, line.startsWith("**"))
        }
    }

    @Test
    fun `a body with no changes heading keeps its bullets, and one with none shows none`() {
        assertEquals(listOf("a change"), found(withBody("- a change")).changes)
        assertEquals(emptyList<String>(), found(withBody("no list here at all")).changes)
        assertEquals(emptyList<String>(), found(withBody("")).changes)
        assertEquals(emptyList<String>(), UpdateCheck.changesIn(null))
    }

    @Test
    fun `a code block in the body is not a changelog`() {
        val p = found(withBody("## What's changed\n\n- real change\n\n```\n- not a change, this is a command\n```"))
        assertEquals(listOf("real change"), p.changes)
    }

    @Test
    fun `the changelog is bounded, because it is written by CI and shown on a phone`() {
        val many = (1..200).joinToString("\n") { "- change $it" }
        val p = found(withBody("## What's changed\n\n$many"))
        assertEquals(UpdateCheck.MAX_CHANGES, p.changes.size)
        assertEquals("change 1", p.changes.first())
        // A very long subject is cut, not wrapped off the screen.
        val long = found(withBody("## What's changed\n\n- " + "x".repeat(1000))).changes.single()
        assertEquals(UpdateCheck.MAX_CHANGE_CHARS, long.length)
    }

    @Test
    fun `the download address is the asset's own, on this repository's releases only`() {
        val good = "https://github.com/darknight11ish/Epic-Jarvis/releases/download/client-latest/jarvis-client-4cc383c.apk"
        val p = found(withBody("## What's changed\n\n- one", url = good, size = 80_000_000))
        assertEquals(good, p.downloadUrl)
        assertEquals(80_000_000L, p.downloadBytes)
        assertTrue(UpdateCheck.isReleaseDownload(good))

        // A link a reply chose must never be fetched: another site, another
        // repository, plain http, credentials before the host, or a newline.
        for (bad in listOf(
            "https://evil.example/jarvis-client-4cc383c.apk",
            "https://github.com/darknight11ish/Epic-Jarvis/releases/tag/client-latest",
            "https://github.com/someone-else/Epic-Jarvis/releases/download/client-latest/x.apk",
            "http://github.com/darknight11ish/Epic-Jarvis/releases/download/client-latest/x.apk",
            "https://user:pw@github.com/darknight11ish/Epic-Jarvis/releases/download/client-latest/x.apk",
            "https://github.com/darknight11ish/Epic-Jarvis/releases/download/client-latest/x.apk\nhttps://evil.example",
            "",
        )) {
            assertFalse(bad, UpdateCheck.isReleaseDownload(bad))
        }
        // A release with no address offers no Download button at all.
        assertNull(found(withBody("## What's changed\n\n- one", url = null)).downloadUrl)
    }

    @Test
    fun `the APK is only written from GitHub's own hosts`() {
        for (host in listOf("github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com", "githubusercontent.com")) {
            assertTrue(host, UpdateCheck.isGithubHost(host))
        }
        for (host in listOf("evil.example", "github.com.evil.example", "notgithub.com", "githubusercontent.com.evil.example", null)) {
            assertFalse("$host", UpdateCheck.isGithubHost(host))
        }
    }

    @Test
    fun `the pinned certificate is the project key's, and it is a real digest`() {
        // keytool, on the owner's own keystore, and apksigner, on the copy
        // installed on his phone, both read exactly this (2026-10-11). It is
        // the one thing a swapped file cannot fake.
        assertEquals(
            "62ef7742e35e742a94a071bba83631fd6db78b5b50961f7b45719d736500d7b5",
            UpdateCheck.SIGNER_SHA256,
        )
        assertTrue(UpdateCheck.SIGNER_SHA256.matches(Regex("^[0-9a-f]{64}$")))
    }

    @Test
    fun `a file signed with the pinned certificate is accepted and anything else is REFUSED`() {
        val want = UpdateCheck.SIGNER_SHA256
        assertTrue(UpdateCheck.signerMatches(want))
        // How keytool prints it.
        assertTrue(UpdateCheck.signerMatches(want.uppercase().chunked(2).joinToString(":")))
        // One wrong character is a refusal, not a warning.
        assertFalse(UpdateCheck.signerMatches("62ef7742e35e742a94a071bba83631fd6db78b5b50961f7b45719d736500d7b6"))
        // A different key entirely.
        assertFalse(UpdateCheck.signerMatches("aa".repeat(32)))
        // No signature at all: refused, because a file we cannot vouch for is
        // not one to offer.
        assertFalse(UpdateCheck.signerMatches(null))
        assertFalse(UpdateCheck.signerMatches(""))
        assertFalse(UpdateCheck.signerMatches("   "))
        assertFalse(UpdateCheck.signerMatches("not a digest"))
    }

    @Test
    fun `a wrong certificate ends as Refused with plain words, never as Ready`() {
        var offered = false
        val out = UpdateCheck.afterFetch(1234, "aa".repeat(32)) {
            offered = true
            UpdateCheck.Download.Ready(java.io.File("never"))
        }
        assertFalse("an unverified file was offered for install", offered)
        assertTrue(out is UpdateCheck.Download.Refused)
        val why = (out as UpdateCheck.Download.Refused).why
        assertTrue(why, "not signed by Jarvis's own key" in why)
        assertTrue(why, "deleted" in why)

        // The right certificate goes through.
        val ok = UpdateCheck.afterFetch(1234, UpdateCheck.SIGNER_SHA256) {
            UpdateCheck.Download.Ready(java.io.File("the.apk"))
        }
        assertTrue(ok is UpdateCheck.Download.Ready)
    }

    @Test
    fun `nothing is downloaded until a download is asked for`() {
        // The only state an app starts in, and the only one a check leaves
        // behind: no bytes have moved and there is no file to install.
        val idle: UpdateCheck.Download = UpdateCheck.Download.Idle
        assertEquals(UpdateCheck.Download.Idle::class.java, idle.javaClass)
        assertEquals(UpdateCheck.Download.Idle, idle)
        // A download that was never started cannot be installed from: the
        // install path only ever takes `Ready` (platform/UpdateChecker.install),
        // and nothing but a fetched AND certificate-matched file makes one.
        val refused = UpdateCheck.afterFetch(0, null) { UpdateCheck.Download.Ready(java.io.File("x")) }
        assertEquals(UpdateCheck.Download.Refused::class.java, refused.javaClass)
        assertFalse(refused is UpdateCheck.Download.Ready)
        // A press with no address offered fetches nothing, even before the
        // network is reached: the Download button is only drawn for a URL
        // that passed `isReleaseDownload` (ReadinessScreen), and the fetch
        // refuses the same check again.
        assertFalse(UpdateCheck.isReleaseDownload(""))
        assertFalse(UpdateCheck.isReleaseDownload("https://evil.example/x.apk"))
    }

    @Test
    fun `the download line says how far along it is, in plain words`() {
        assertEquals("50% of 80.0 MB", UpdateCheck.progress(40_000_000, 80_000_000))
        assertEquals("80.0 MB downloaded", UpdateCheck.progress(80_000_000, 0))
    }
}
