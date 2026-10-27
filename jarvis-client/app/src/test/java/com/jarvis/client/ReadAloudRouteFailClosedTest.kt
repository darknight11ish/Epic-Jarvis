package com.jarvis.client

import com.jarvis.client.voice.PrivateAloud
import com.jarvis.client.voice.ReadAloud
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The read-aloud gate must FAIL CLOSED when the PC does not say what the
 * answer touched (the owner's decision recorded in docs/DECISIONS.md,
 * 2026-10-27: "it refuses when the route header is missing").
 *
 * The pure gate has that branch - [com.jarvis.client.voice.ReadAloud.Facts.mayRead]
 * returns false when `!hasRoute` - but #892 handed it
 * `hasRoute = PrivateAloud.route(header) != null`, and
 * [com.jarvis.client.voice.PrivateAloud.route] can never return null: it
 * answers [com.jarvis.client.voice.PrivateAloud.SILENT_ROUTE] for a header
 * that is missing or unreadable. So the fail-closed branch was dead and an
 * answer whose gate and injected-fact counts were simply UNKNOWN could be
 * read aloud.
 *
 * The fix is [com.jarvis.client.voice.PrivateAloud.routeOrNull]: null when
 * there is nothing readable, so `hasRoute` can be false. The last test holds
 * the wiring to it; the first two prove the gate the wiring now feeds.
 *
 * Off-device, the [ReadAloudWiringTest] way: there is no emulator here, so the
 * shipped source is one instrument and the pure objects are the other. The real
 * phone behaviour remains a field-test row, not a pass.
 */
class ReadAloudRouteFailClosedTest {

    private val main = "jarvis-client/app/src/main/java/com/jarvis/client/"

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private fun source(rel: String): String = repoFile(main + rel).readText()

    /** The facts built the way [JarvisRuntime.sendTypedChat] builds them. */
    private fun factsFor(header: String?): ReadAloud.Facts {
        val route = PrivateAloud.routeOrNull(header)
        return ReadAloud.Facts(
            hasRoute = route != null,
            privateGate = route?.privateGate == true,
            injectedFacts = route?.injectedFacts ?: 0,
            injectedSensitive = route?.injectedSensitive ?: 0,
            toolRan = false,
            toolsKnown = true,
            screenRead = false,
            stale = false,
            locked = false,
        )
    }

    @Test
    fun `a missing or unreadable route can never be read aloud`() {
        assertNull("a missing header must read as unknown", PrivateAloud.routeOrNull(null))
        assertNull("a blank header must read as unknown", PrivateAloud.routeOrNull("   "))
        assertNull("a header that is not JSON must read as unknown", PrivateAloud.routeOrNull("not json"))
        assertNull("an array is not the route object", PrivateAloud.routeOrNull("[1,2,3]"))
        assertFalse("a missing route was handed to the gate as readable", factsFor(null).mayRead)
        assertFalse("an unreadable route was handed to the gate as readable", factsFor("not json").mayRead)
    }

    @Test
    fun `a readable route still reads, and a private one still does not`() {
        val plain = """{"gate":"plain","injected_facts":0}"""
        assertTrue("the sentence the PC sends for an ordinary answer no longer reads", factsFor(plain).mayRead)
        assertFalse("a private-gate answer is read aloud", factsFor("""{"gate":"private"}""").mayRead)
        assertFalse("an answer with injected facts is read aloud", factsFor("""{"gate":"plain","injected_facts":2}""").mayRead)
        // The old reader keeps its old meaning for the voice path: silent, not null.
        assertEquals(PrivateAloud.SILENT_ROUTE, PrivateAloud.route(null))
    }

    @Test
    fun `the read-aloud wiring asks for a route that can say it does not know`() {
        val runtime = source("JarvisRuntime.kt")
        assertFalse(
            "a non-null Route is still treated as \"the PC told us\" - the gate cannot fail closed",
            runtime.contains("hasRoute = route != null") && runtime.contains("PrivateAloud.route(header)"),
        )
        assertTrue(
            "the typed send does not read the route fail-closed, so an unknown route can be read aloud",
            runtime.contains("PrivateAloud.routeOrNull(header)"),
        )
    }
}
