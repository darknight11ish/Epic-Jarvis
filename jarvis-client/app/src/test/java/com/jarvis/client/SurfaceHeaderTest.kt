package com.jarvis.client

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The owner's requirement of 2026-10-31: Jarvis must know whether the owner is
 * talking from the Android app or the desktop program, and tailor its answers
 * and features accordingly - by default, with no setup.
 *
 * This is the phone's half of the transport. `X-Jarvis-Client: hud` is kept
 * exactly as it was (the PC's origin check and its cloud-escalation rules read
 * it); `X-Jarvis-Surface: phone` is ADDED beside it on every request the phone
 * sends, from the ONE authed builder - so no call site can forget it. The
 * desktop sends `desktop` from its Rust `jarvis_headers` and its HUD page.
 *
 * These are source checks, the suite's usual kind (LimitsTest,
 * MenuVisibilityTest, AttentionSettingsTest): the fact that every authed
 * request carries the header is held to the text that builds it. Nothing here
 * is a field-test pass; the phone build is CI's.
 */
class SurfaceHeaderTest {

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private val apiPath =
        "jarvis-client/app/src/main/java/com/jarvis/client/net/JarvisApi.kt"

    private fun source(): String = repoFile(apiPath).readText()

    @Test
    fun `the phone sends its surface header on every authed request`() {
        val src = source()
        val authed = src.substringAfter("fun Request.Builder.authed()")
            .substringBefore("private fun url(")
        assertTrue(
            "the one authed builder must send the surface header:\n$authed",
            authed.contains("header(SURFACE_HEADER, SURFACE_VALUE)")
        )
        assertTrue(
            "the legacy client header must stay exactly as it was:\n$authed",
            authed.contains("header(CLIENT_HEADER, CLIENT_VALUE)")
        )
    }

    @Test
    fun `the pairing requests carry it too, and still carry the client header`() {
        val src = source()
        val pairPost = src.substringAfter("suspend fun pairPost(")
            .substringBefore("fun close(")
        assertTrue(
            "pairing is a phone request too:\n$pairPost",
            pairPost.contains("header(SURFACE_HEADER, SURFACE_VALUE)")
        )
        assertTrue(
            "the legacy client header must stay exactly as it was:\n$pairPost",
            pairPost.contains("header(CLIENT_HEADER, CLIENT_VALUE)")
        )
    }

    @Test
    fun `the header is the new name and the phone's own value`() {
        val src = source()
        assertEquals(1, Regex("""const val SURFACE_HEADER = "X-Jarvis-Surface"""").findAll(src).count())
        assertEquals(1, Regex("""const val SURFACE_VALUE = "phone"""").findAll(src).count())
        // It is not a secret and not a token: the token header is a different line.
        assertTrue(
            "the surface value must not be built from the token",
            !src.substringAfter("const val SURFACE_VALUE").substringBefore("}").contains("token")
        )
    }

    @Test
    fun `nothing else in the phone is asked to send the surface by hand`() {
        val src = source()
        // ONE place: if a second call site wrote the literal header, it could
        // disagree with the builder (or be forgotten). There are exactly two
        // calls - the authed builder and the pairing post - and both are the
        // shared constant, never a bare "X-Jarvis-Surface" string.
        assertEquals(
            "the header must ride only on the two shared builders",
            2,
            Regex("""header\(SURFACE_HEADER, SURFACE_VALUE\)""").findAll(src).count()
        )
    }
}
