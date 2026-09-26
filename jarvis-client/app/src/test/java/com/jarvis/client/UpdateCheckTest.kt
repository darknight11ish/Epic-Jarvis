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
    }
}
