package com.jarvis.client

import com.jarvis.client.net.PlainErrors
import com.jarvis.client.net.ScreenPlateText
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.io.IOException
import java.net.ConnectException
import java.net.NoRouteToHostException
import java.net.SocketTimeoutException
import java.net.UnknownHostException

/**
 * The composer and the status line on Home, found on the owner's real phone
 * by a feature sweep (2026-10-10). Two faults, both about words the owner
 * reads and neither about anything the app was doing wrong underneath:
 *
 * 1. With the link down, Send was greyed and nothing anywhere said why. The
 *    owner typed a message, pressed Send and nothing happened. The runtime's
 *    own blocker cannot explain that one: a disabled button never reaches the
 *    runtime, so its sentence is never said. The composer now shows the line
 *    every other plate already shows under a control it greyed for the link.
 *
 * 2. Home's status line, and the "Details" under a notice, printed the
 *    platform's own text. An OkHttp connect failure's message carries the
 *    address it tried and both ports, and the owner's Home screen showed it
 *    word for word - "failed to connect to
 *    marioirelan11-alps.nord/100.75.21.228 (port 4719) from
 *    /100.124.30.77 (port 42892) after 10000ms": a mesh address, a port and
 *    this phone's own address, on the line the owner reads at a glance.
 *    Every transport failure now says the app's own plain sentence
 *    ([PlainErrors.networkSays]), and the classification still reaches
 *    "Details" for a bug report.
 *
 * The composer needs a real Compose host, so the two places that render one of
 * these lines are held by reading the source, as [LinkWordsTest] does for
 * Home's "Catching up…".
 */
class HomeLinkWordingTest {

    // -------------------------------------------------- the composer's line ---

    @Test
    fun `the composer says why Send is greyed while the link is down`() {
        assertNull("a live link has nothing to explain", LinkWords.composerHeldLine(LinkState.CONNECTED))
        for (link in listOf(LinkState.OFFLINE, LinkState.RECONNECTING)) {
            assertEquals(
                "the app's own line, the one the other plates already show",
                ScreenPlateText.WAITING_LINK,
                LinkWords.composerHeldLine(link),
            )
        }
        // A state line, not a fault report: nothing in it to parse.
        val line = requireNotNull(LinkWords.composerHeldLine(LinkState.OFFLINE))
        assertFalse("no number in it: $line", line.any { it.isDigit() })
        assertFalse("it must not call a down link \"catching up\": $line", line.contains("catching up"))
    }

    /**
     * The render itself. Deleting it - exactly the fault the owner hit - fails
     * this, and nothing else in the suite would notice.
     */
    @Test
    fun `the composer draws that line from the link it greys Send on`() {
        val composer = composer()
        // The condition Send is greyed on, and the line that explains it: both
        // hang off the same `state.link`, so they cannot disagree.
        assertTrue(
            "the composer no longer greys Send on the link",
            composer.contains("state.link == LinkState.CONNECTED"),
        )
        assertTrue(
            "the composer greys Send and says nothing about why",
            composer.contains("LinkWords.composerHeldLine(state.link)"),
        )
    }

    // ------------------------------------------ a failure's own sentence ---

    /** The failure the owner's Home screen printed, exactly as OkHttp writes it. */
    private val connectTimeout = SocketTimeoutException(
        "failed to connect to marioirelan11-alps.nord/100.75.21.228 (port 4719) from " +
            "/100.124.30.77 (port 42892) after 10000ms",
    )

    /** Every shape a transport failure takes on a phone, and its kind. */
    private val failures = linkedMapOf(
        connectTimeout to "connect_timeout",
        NoRouteToHostException("No route to host") to "no_route",
        SocketTimeoutException("timeout") to "read_timeout",
        UnknownHostException(
            "Unable to resolve host \"marioirelan11-alps.nord\": No address associated with hostname",
        ) to "unknown_host",
        ConnectException(
            "failed to connect to /100.64.1.2 (port 8765) from /100.64.1.9 (port 40000) after 10000ms: " +
                "isConnected failed: ECONNREFUSED (Connection refused)",
        ) to "refused",
        IOException("unexpected end of stream") to "dropped",
    )

    @Test
    fun `the OkHttp failure the owner saw becomes the app's own sentence`() {
        val said = PlainErrors.networkSays(connectTimeout)
        assertEquals(PlainErrors.KINDS.getValue("pc_unreachable").says, said)
        assertEquals("Your PC isn't answering.", said)
        assertFalse("no address: $said", Regex("""\d+\.\d+\.\d+\.\d+""").containsMatchIn(said))
        assertFalse("no :port: $said", Regex(""":\d""").containsMatchIn(said))
        assertFalse("no mesh name: $said", said.contains("marioirelan11-alps.nord"))
        assertFalse("not one digit in it: $said", said.any { it.isDigit() })
        assertFalse("not one slash in it: $said", said.contains("/"))
    }

    @Test
    fun `every shape of transport failure says a plain sentence, never the platform's`() {
        val own = PlainErrors.KINDS.values.map { it.says }.toSet()
        for ((failure, kind) in failures) {
            assertEquals("$failure", kind, PlainErrors.networkKind(failure))
            val said = PlainErrors.networkSays(failure)
            assertTrue("not the app's own wording: $said", said in own)
            assertFalse("$failure -> $said", said.any { it.isDigit() })
            assertFalse("$failure -> $said", said.contains("/"))
            assertFalse("$failure -> $said", said.contains("Exception"))
        }
    }

    // --------------------------------------------------- what reaches a screen ---

    /**
     * The line Home's status bar prints while the link is down is
     * `JarvisRuntime.linkDetail`, which is the stream's own `Signal.Down`
     * reason word for word. That is the path the owner's screenshot came
     * down - never mind "Details".
     */
    @Test
    fun `the link reason Home prints is the app's own sentence`() {
        val stream = repoFile(NET + "EventStream.kt").readText()
        assertFalse(
            "the platform's message is what Home prints",
            stream.contains("Signal.Down(t.message"),
        )
        assertTrue(
            "a failed stream must say it in the app's words",
            stream.contains("PlainErrors.networkSays(t)"),
        )
    }

    /**
     * Two "Details" paths reach a screen, and neither may print the platform's
     * text: a request's failure ([com.jarvis.client.net.JarvisApi], behind
     * Home's notice) and a failed question ([com.jarvis.client.net.ChatSession],
     * whose problem Home's notice shows too).
     */
    @Test
    fun `nothing behind Details is the platform's own message`() {
        val api = repoFile(NET + "JarvisApi.kt").readText()
        assertTrue("the failure's detail must be the app's sentence", api.contains("PlainErrors.networkSays(this)"))
        assertFalse("the platform's message is the detail", api.contains("message ?: this::class.java.simpleName"))
        val chat = repoFile(NET + "ChatSession.kt").readText()
        assertTrue("a failed question must say it in the app's words", chat.contains("PlainErrors.networkSays(t)"))
        assertFalse("the platform's message is the detail", chat.contains("t.message.orEmpty()"))
    }

    // ------------------------------------------------------------- plumbing ---

    /**
     * [com.jarvis.client.ui.screens.HomeScreen]'s `Composer`, from its
     * declaration to the next composable after it.
     */
    private fun composer(): String =
        repoFile(HOME).readText().substringAfter("private fun Composer(").substringBefore("\n@Composable")

    /** Walks up from Gradle's working folder (`jarvis-client/app`) to the repository. */
    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private companion object {
        const val BASE = "jarvis-client/app/src/main/java/com/jarvis/client/"
        const val NET = BASE + "net/"
        const val HOME = BASE + "ui/screens/HomeScreen.kt"
    }
}
