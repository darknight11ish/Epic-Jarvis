package com.jarvis.client

import com.jarvis.client.net.ScreenLook
import com.jarvis.client.net.ScreenWatch
import com.jarvis.client.net.ScreenWatch.UsageEvent
import com.jarvis.client.net.ScreenWatch.Verdict
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Watch with me" on the phone, without a phone: when a picture may be kept,
 * how the app in front is worked out, how long a session lives, and that a
 * picture is taken only for a question and used up by it
 * (docs/SCREEN-DESIGN.md section 4; the service that does the real screen
 * sharing is not here and is unverified until it runs on a phone).
 */
class ScreenWatchTest {

    @After
    fun tidy() {
        ScreenWatch.resetForTests()
        ScreenLook.resetForTests()
    }

    private fun ev(at: Long, type: Int, pkg: String) = UsageEvent(at, type, pkg)

    @Test
    fun `the apps on screen are those that came forward and did not go back, newest last`() {
        val log = listOf(
            ev(1, ScreenWatch.EVENT_RESUMED, "com.a.app"),
            ev(2, ScreenWatch.EVENT_PAUSED, "com.a.app"),
            ev(3, ScreenWatch.EVENT_RESUMED, "com.b.app"),
        )
        assertEquals(listOf("com.b.app"), ScreenWatch.visibleApps(log))
        assertEquals("com.b.app", ScreenWatch.frontApp(log))
        // The same log out of order is read in time order.
        assertEquals(listOf("com.b.app"), ScreenWatch.visibleApps(log.reversed()))
        // The front app went away and nothing came forward: unknown.
        assertTrue(ScreenWatch.visibleApps(log + ev(4, ScreenWatch.EVENT_STOPPED, "com.b.app")).isEmpty())
        assertTrue(ScreenWatch.visibleApps(log + ev(4, ScreenWatch.EVENT_DESTROYED, "com.b.app")).isEmpty())
        // A different app pausing does not unseat the front one.
        assertEquals(
            listOf("com.b.app"),
            ScreenWatch.visibleApps(log + ev(4, ScreenWatch.EVENT_PAUSED, "com.a.app")),
        )
        assertTrue("no log, no guess", ScreenWatch.visibleApps(emptyList()).isEmpty())
        assertNull(ScreenWatch.frontApp(emptyList()))
    }

    @Test
    fun `split-screen keeps both apps, the screen going off keeps none`() {
        val split = listOf(
            ev(1, ScreenWatch.EVENT_RESUMED, "com.a.app"),
            ev(2, ScreenWatch.EVENT_RESUMED, "com.b.app"),
        )
        assertEquals(listOf("com.a.app", "com.b.app"), ScreenWatch.visibleApps(split))
        // Coming forward again moves an app to the newest place, not twice into the list.
        assertEquals(
            listOf("com.b.app", "com.a.app"),
            ScreenWatch.visibleApps(split + ev(3, ScreenWatch.EVENT_RESUMED, "com.a.app")),
        )
        assertTrue(ScreenWatch.visibleApps(split + ev(3, ScreenWatch.EVENT_SCREEN_OFF, "")).isEmpty())
        assertTrue(ScreenWatch.visibleApps(split + ev(3, ScreenWatch.EVENT_SHUTDOWN, "")).isEmpty())
        assertEquals(
            listOf("com.c.app"),
            ScreenWatch.visibleApps(
                split + ev(3, ScreenWatch.EVENT_SCREEN_OFF, "") + ev(4, ScreenWatch.EVENT_RESUMED, "com.c.app"),
            ),
        )
        assertTrue("every event type read is one the log can carry", ScreenWatch.EVENT_TYPES.size == 6)
    }

    @Test
    fun `a nearly all-black picture is a secure app, and an empty sample is too`() {
        assertTrue(ScreenWatch.looksBlack(IntArray(1000) { 0 }))
        assertTrue(ScreenWatch.looksBlack(IntArray(1000) { if (it < 3) 200 else 5 }))
        assertFalse(ScreenWatch.looksBlack(IntArray(1000) { if (it < 100) 200 else 5 }))
        assertTrue(ScreenWatch.looksBlack(IntArray(0)))
        assertEquals(0, ScreenWatch.lumaOf(0xFF000000.toInt()))
        assertEquals(255, ScreenWatch.lumaOf(0xFFFFFFFF.toInt()))
        assertTrue(ScreenWatch.lumaOf(0xFF00FF00.toInt()) > ScreenWatch.lumaOf(0xFF0000FF.toInt()))
    }

    @Test
    fun `the picture is made small on its long side, keeping its shape`() {
        assertEquals(1000 to 800, ScreenWatch.scaledSize(1000, 800))
        assertEquals(ScreenWatch.LONG_EDGE to 640, ScreenWatch.scaledSize(2560, 1280))
        val (w, h) = ScreenWatch.scaledSize(1080, 2400)
        assertEquals(ScreenWatch.LONG_EDGE, h)
        assertEquals(576, w)
        assertEquals(0 to 0, ScreenWatch.scaledSize(0, 100))
    }

    @Test
    fun `nothing is kept from a private app, an unknown one, a dark screen or a black picture`() {
        val none = emptySet<String>()
        val noCategory = { _: String -> null as Int? }
        fun d(vararg apps: String, never: Set<String> = none, on: Boolean = true, black: Boolean? = false) =
            ScreenWatch.decide(apps.toList(), never, noCategory, on, black)
        assertEquals(Verdict.Take, d("com.android.chrome"))
        assertTrue(d("com.jarvis.client") is Verdict.Refuse)
        assertTrue(d("com.x8bit.bitwarden") is Verdict.Refuse)
        assertTrue(d("com.chase.sig.android") is Verdict.Refuse)
        assertTrue(d("com.somechat.example", never = setOf("com.somechat.example")) is Verdict.Refuse)
        assertTrue("cannot tell is a refusal", d() is Verdict.Refuse)
        assertEquals(Verdict.Refuse(ScreenWatch.DARK_SCREEN), d("com.android.chrome", on = false))
        assertEquals(Verdict.Refuse(ScreenWatch.PRIVATE_SCREEN), d("com.android.chrome", black = true))
        // Before any picture exists the black check is not asked yet: still a take.
        assertEquals(Verdict.Take, d("com.android.chrome", black = null))
        // A private app in the OTHER half of a split screen is on the picture too.
        assertTrue(d("com.android.chrome", "com.x8bit.bitwarden") is Verdict.Refuse)
        assertTrue(d("com.chase.sig.android", "com.android.chrome") is Verdict.Refuse)
        // An app the phone's own category says is a bank, even with an ordinary name.
        val bankish = { p: String -> if (p == "com.ordinary.name") 6 else null }
        assertTrue(ScreenWatch.decide(listOf("com.ordinary.name"), none, bankish, true, false) is Verdict.Refuse)
    }

    @Test
    fun `a session shows its sign and counts down, and ends`() {
        var now = 1_000_000L
        ScreenWatch.clock = { now }
        assertNull(ScreenWatch.sign())
        ScreenWatch.started()
        val s = ScreenWatch.sign()!!
        assertTrue(s.on)
        assertEquals(ScreenWatch.SIGN_TITLE, s.title)
        assertEquals(ScreenWatch.STOP_LABEL, s.stop)
        assertEquals("30 min left", s.detail)
        now += 20 * 60_000L
        assertEquals("10 min left", ScreenWatch.leftLine())
        now += 9 * 60_000L + 30_000L
        assertEquals("under a minute left", ScreenWatch.leftLine())
        ScreenWatch.ended()
        assertNull(ScreenWatch.sign())
        assertEquals("", ScreenWatch.leftLine())
    }

    @Test
    fun `a picture is taken for a question only while watching, and used up by it`() = runBlocking {
        var taken = 0
        ScreenWatch.grabber = {
            taken += 1
            ScreenWatch.Grab("Chrome", "data:image/jpeg;base64,AAAA", null)
        }
        // Not watching: nothing is taken, nothing is held.
        ScreenWatch.beforeQuestion()
        assertEquals(0, taken)
        assertNull(ScreenLook.forQuestion())
        // Watching: one picture per question.
        ScreenWatch.started()
        ScreenWatch.beforeQuestion()
        assertEquals(1, taken)
        val used = ScreenLook.forQuestion()
        assertNotNull(used)
        assertEquals("data:image/jpeg;base64,AAAA", used!!.picture)
        assertEquals("", used.words)
        assertNull("used up by the one question", ScreenLook.forQuestion())
        ScreenWatch.beforeQuestion()
        assertEquals("the next question takes its own", 2, taken)
        Unit
    }

    @Test
    fun `a refusal is said, and the question goes without a picture`() = runBlocking {
        val said = mutableListOf<String>()
        ScreenWatch.say = { said += it }
        ScreenWatch.grabber = { ScreenWatch.Grab("", null, ScreenWatch.PRIVATE_SCREEN) }
        ScreenWatch.started()
        ScreenWatch.beforeQuestion()
        assertEquals(listOf(ScreenWatch.PRIVATE_SCREEN), said)
        assertNull(ScreenLook.forQuestion())
        Unit
    }

    @Test
    fun `the same refusal is not said again on every question for a minute`() = runBlocking {
        var now = 5_000_000L
        ScreenWatch.clock = { now }
        val said = mutableListOf<String>()
        ScreenWatch.say = { said += it }
        ScreenWatch.grabber = { ScreenWatch.Grab("", null, "That's one of Jarvis's own screens, so I'm not looking.") }
        ScreenWatch.started()
        repeat(3) { ScreenWatch.beforeQuestion() }
        assertEquals(1, said.size)
        now += 61_000L
        ScreenWatch.beforeQuestion()
        assertEquals(2, said.size)
        // A different reason is always said.
        ScreenWatch.grabber = { ScreenWatch.Grab("", null, ScreenWatch.DARK_SCREEN) }
        ScreenWatch.beforeQuestion()
        assertEquals(3, said.size)
        Unit
    }

    @Test
    fun `a grab that fails or takes too long is a question without a picture, never a crash`() = runBlocking {
        ScreenWatch.started()
        ScreenWatch.grabber = { error("the capture broke") }
        ScreenWatch.beforeQuestion()
        assertNull(ScreenLook.forQuestion())
        ScreenWatch.grabber = {
            delay(60_000)
            ScreenWatch.Grab("Chrome", "data:image/jpeg;base64,BBBB", null)
        }
        val began = System.nanoTime()
        ScreenWatch.beforeQuestion()
        val tookMs = (System.nanoTime() - began) / 1_000_000L
        assertNull(ScreenLook.forQuestion())
        assertTrue("waited about the limit, not a minute: $tookMs ms", tookMs < ScreenWatch.GRAB_TIMEOUT_MS + 2_000)
        Unit
    }

    @Test
    fun `a link that is down or stale is not healthy and Watch gives up after ten seconds`() {
        assertTrue(ScreenWatch.linkHealthy(connected = true, stale = false))
        assertFalse(ScreenWatch.linkHealthy(connected = false, stale = false))
        assertFalse(ScreenWatch.linkHealthy(connected = true, stale = true))
        assertFalse(ScreenWatch.linkHealthy(connected = false, stale = true))
        assertEquals(10_000L, ScreenWatch.LINK_LOST_MS)
        assertTrue(ScreenWatch.ENDED_LINK.startsWith("Stopped watching"))
    }

    @Test
    fun `the words say plainly that password boxes cannot be seen`() {
        assertTrue(ScreenWatch.HOW.contains("password box"))
        assertTrue(ScreenWatch.NOTIFICATION_TEXT.contains("password boxes"))
        assertTrue(ScreenWatch.NOTIFICATION_TEXT.contains("cannot pause"))
    }
}
