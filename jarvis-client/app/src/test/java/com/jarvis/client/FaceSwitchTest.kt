package com.jarvis.client

import androidx.compose.ui.geometry.Offset
import com.jarvis.client.face.AnimalNow
import com.jarvis.client.face.Arc
import com.jarvis.client.face.Bindings
import com.jarvis.client.face.CritterFace
import com.jarvis.client.face.CritterPose
import com.jarvis.client.face.Face
import com.jarvis.client.face.FaceClock
import com.jarvis.client.face.FaceFrame
import com.jarvis.client.face.FaceHost
import com.jarvis.client.face.FrameRateTarget
import com.jarvis.client.face.RestPace
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The phone host's side of two of the owner's 2026-09-28 decisions:
 * "Goodbye and hello when switching faces" (FaceHost.beginGoodbye /
 * beginHello, FaceFrame.behave and FaceFrame.alpha) and petting's "a long
 * press ... that does not open Brain" - a long press, then a stroke, never
 * turns the face round; a quick drag still does. The animals' own goodbye,
 * hello and petting poses are CritterPoseTest's.
 */
class FaceSwitchTest {

    private class FakeAnimal : CritterFace("fake", "Fake", "") {
        override fun pose(f: FaceFrame) = FloatArray(0)
        override fun uniformsOf(p: FloatArray, mouth: FloatArray?) = emptyMap<String, FloatArray>()
        override fun overlayOf(p: FloatArray, yaw: Float, pitch: Float) = floatArrayOf(0f, 0f, 0f)
        override fun busyAt(state: FaceState, t: Float) = false
    }

    private fun run(host: FaceHost, face: Face, secs: Float, still: Boolean = false, pace: RestPace? = null): Int {
        var drawn = 0
        repeat((secs * 60).toInt()) {
            if (host.advance(1f / 60f, FaceState.IDLE, null, null, Bindings.DEFAULTS, face, still = still, pace = pace)) drawn++
        }
        return drawn
    }

    @Test
    fun `a Still animal opens still, and a Still read late is taken at once`() {
        val before = AnimalNow.reads
        try {
            // Opened with Still already known: still from the first frame.
            AnimalNow.reads = 1
            val a = FakeAnimal()
            val h1 = FaceHost()
            run(h1, a, 0.05f, still = true)
            assertEquals(1f, h1.snapshot().stillW, 1e-4f)
            // Opened before the stored options were read, Still arriving with them.
            AnimalNow.reads = 0
            val h2 = FaceHost()
            run(h2, a, 0.3f, still = false)
            assertEquals(0f, h2.snapshot().stillW, 1e-4f)
            AnimalNow.reads = 1
            run(h2, a, 0.1f, still = true)
            assertEquals("taken at once, not eased in", 1f, h2.snapshot().stillW, 1e-4f)
            // Once settled, turning it off eases as always.
            run(h2, a, 0.6f, still = true)
            run(h2, a, 0.5f, still = false)
            val mid = h2.snapshot().stillW
            assertTrue("eases out: $mid", mid > 0.2f && mid < 0.8f)
        } finally {
            AnimalNow.reads = before
        }
    }

    @Test
    fun `an animal plays its goodbye, then the new one its hello, drawn fully opaque`() {
        val host = FaceHost()
        val a = FakeAnimal()
        run(host, a, 1f)
        assertEquals(0f, host.snapshot().behave.goodbye)
        assertEquals(1f, host.snapshot().behave.hello)
        host.beginGoodbye()
        run(host, a, 0.5f)
        val mid = host.snapshot()
        assertEquals(0.5f, mid.behave.goodbye, 0.03f)
        assertEquals("the animal plays its own goodbye, not a fade", 1f, mid.alpha, 1e-4f)
        assertFalse(host.goodbyeDone())
        run(host, a, 0.6f)
        assertTrue(host.goodbyeDone())
        host.beginHello()
        run(host, a, 0.5f)
        assertEquals(0.5f, host.snapshot().behave.hello, 0.03f)
        assertEquals(0f, host.snapshot().behave.goodbye)
        run(host, a, 0.6f)
        assertTrue(host.helloDone())
        assertEquals(1f, host.snapshot().behave.hello)
        assertEquals(1f, host.snapshot().alpha)
    }

    @Test
    fun `under Still an animal cross-fades instead`() {
        val host = FaceHost()
        val a = FakeAnimal()
        run(host, a, 1.5f, still = true)
        host.beginGoodbye()
        run(host, a, 0.5f, still = true)
        val a1 = host.snapshot().alpha
        assertTrue("half way through the goodbye it is half faded: $a1", a1 in 0.3f..0.7f)
        run(host, a, 0.6f, still = true)
        host.beginHello()
        run(host, a, 0.25f, still = true)
        assertTrue("fading back in: ${host.snapshot().alpha}", host.snapshot().alpha < 0.5f)
    }

    @Test
    fun `a face that is not a character just fades on its side`() {
        val host = FaceHost()
        run(host, Arc, 1f)
        host.beginGoodbye()
        run(host, Arc, 0.25f)
        assertEquals(0.75f, host.snapshot().alpha, 0.03f)
        run(host, Arc, 0.8f)
        host.beginHello()
        run(host, Arc, 0.5f)
        assertEquals(0.5f, host.snapshot().alpha, 0.03f)
    }

    @Test
    fun `a switch is drawn at the full rate`() {
        val host = FaceHost()
        val a = FakeAnimal()
        val pace = RestPace(FrameRateTarget.AUTO, headroom = false)
        run(host, a, 2f, pace = pace)
        assertEquals("resting at 30", 30f, run(host, a, 1f, pace = pace).toFloat(), 1.5f)
        host.beginGoodbye()
        assertEquals("every frame while it plays", 60f, run(host, a, 1f, pace = pace).toFloat(), 1.5f)
    }

    /** An animal whose idle happening is always playing, and which remembers the "since" it was asked with. */
    private class BusyAnimal(id: String = "busy") : CritterFace(id, "Busy", "") {
        var since = -1f
        override fun pose(f: FaceFrame) = FloatArray(0)
        override fun uniformsOf(p: FloatArray, mouth: FloatArray?) = emptyMap<String, FloatArray>()
        override fun overlayOf(p: FloatArray, yaw: Float, pitch: Float) = floatArrayOf(0f, 0f, 0f)
        override fun busyAt(state: FaceState, t: Float) = state == FaceState.IDLE
        override fun busyAt(state: FaceState, t: Float, since: Float, opts: CritterPose.Opts): Boolean {
            this.since = since
            return busyAt(state, t)
        }
    }

    private val pace = RestPace(FrameRateTarget.AUTO, headroom = false)

    private fun runIn(
        host: FaceHost, face: Face, state: FaceState, secs: Float, dt: Float = 1f / 60f,
        serious: Boolean = false, voice: Boolean = false,
    ) {
        repeat((secs / dt).toInt()) {
            host.advance(
                dt, state, null, if (voice) 0.5f else null, Bindings.DEFAULTS, face,
                serious = serious, voiceMouth = if (voice) floatArrayOf(0.5f, 0.3f, 0f, 0f) else null, pace = pace,
            )
        }
    }

    @After
    fun resetAnimalNow() {
        AnimalNow.apply(mapOf("nods" to true, "focus_buddy" to true, "acks" to true, "petting" to true, "cute_moments" to true))
        AnimalNow.factAt = 0L
        AnimalNow.glowAt = 0L
        AnimalNow.focusOn = false
        AnimalNow.focusEndDue = 0L
    }

    @Test
    fun `a hello cut off by the screen going off still ends after a wrap`() {
        val host = FaceHost()
        val a = FakeAnimal()
        // Past the soft wrap point, on screen.
        repeat(((FaceClock.SOFT_S + 4.0) / 0.25).toInt()) {
            host.advance(0.25f, FaceState.IDLE, null, null, Bindings.DEFAULTS, a)
        }
        host.beginHello()
        run(host, a, 0.2f)
        // The screen goes off mid-hello; back on, the loop restarts and the
        // clocks are brought back toward zero.
        host.onLoopStart()
        assertTrue("the clock wrapped", host.clocksForTest()[0] < FaceClock.WRAP_S)
        run(host, a, 0.1f)
        val mid = host.snapshot().behave.hello
        assertTrue("the hello carries on where it was: $mid", mid > 0.2f && mid < 0.6f)
        run(host, a, 1f)
        assertTrue("and ends", host.helloDone())
        assertEquals(1f, host.snapshot().behave.hello)
        // A face that is not a character fades back in fully, too.
        val h2 = FaceHost()
        repeat(((FaceClock.SOFT_S + 4.0) / 0.25).toInt()) { h2.advance(0.25f, FaceState.IDLE, null, null, Bindings.DEFAULTS, Arc) }
        h2.beginHello()
        run(h2, Arc, 0.2f)
        h2.onLoopStart()
        run(h2, Arc, 1f)
        assertEquals("not left invisible", 1f, h2.snapshot().alpha, 1e-4f)
        // And it has not become "just opened" (a switch now plays out).
        assertTrue("on screen for over an hour: ${h2.onScreenS()}", h2.onScreenS() > FaceClock.SOFT_S.toFloat())
    }

    @Test
    fun `a wrap never reopens the Still settling window`() {
        val before = AnimalNow.reads
        try {
            AnimalNow.reads = 0
            val host = FaceHost()
            val a = FakeAnimal()
            // The stored options are read late, an hour in.
            repeat((4000.0 / 0.25).toInt()) { host.advance(0.25f, FaceState.IDLE, null, null, Bindings.DEFAULTS, a) }
            AnimalNow.reads = 1
            repeat((200.0 / 0.25).toInt()) { host.advance(0.25f, FaceState.IDLE, null, null, Bindings.DEFAULTS, a) }
            host.onLoopStart()
            assertTrue("the clock wrapped", host.clocksForTest()[0] < FaceClock.WRAP_S)
            run(host, a, 0.25f, still = true)
            val w = host.snapshot().stillW
            assertTrue("Still eases in as always, not taken at once: $w", w < 0.5f)
        } finally {
            AnimalNow.reads = before
        }
    }

    @Test
    fun `the frame the new face is handed at a switch is its own`() {
        val host = FaceHost()
        val a = FakeAnimal()
        run(host, a, 1.5f)
        assertEquals("fake", host.snapshot().faceId)
        host.beginGoodbye()
        run(host, a, 1.1f)
        assertTrue(host.goodbyeDone())
        assertEquals("the goodbye is the animal's own: drawn opaque", 1f, host.snapshot().alpha, 1e-4f)
        // FaceView: the new face (not a character), its hello, its frame.
        host.beginHello()
        host.wear(Arc)
        val f = host.snapshot()
        assertEquals("arc", f.faceId)
        assertEquals("a face that is not a character starts its fade-in from nothing", 0f, f.alpha, 1e-4f)
        run(host, Arc, 0.5f)
        assertEquals(0.5f, host.snapshot().alpha, 0.03f)
    }

    @Test
    fun `with Petting off a held press then a drag turns the face and is not drawn at the full rate`() {
        AnimalNow.apply(mapOf("petting" to false))
        val host = FaceHost()
        val a = FakeAnimal()
        run(host, a, 2f, pace = pace)
        host.onPetDown(200f, 400f)
        run(host, a, 0.8f, pace = pace)
        assertEquals("resting, not raised for a press that does not pet", 30, host.restFps(a, pace))
        host.onPetMove(260f, 400f, 10f)
        host.onDrag(Offset(60f, 0f))
        host.onDragEnd()
        host.onPetUp()
        run(host, a, 0.3f)
        assertTrue("turned, as before petting existed: ${host.snapshot().yaw}", host.snapshot().yaw != 0f)
    }

    @Test
    fun `happenings that do not play in a focus session or a serious moment do not keep the rate up`() {
        val host = FaceHost()
        val b = BusyAnimal()
        runIn(host, b, FaceState.IDLE, 2f)
        assertEquals("a happening playing: every frame", 0, host.restFps(b, pace))
        AnimalNow.focus(true)
        runIn(host, b, FaceState.IDLE, 1.2f)
        assertEquals("the focus buddy takes the happenings away", 30, host.restFps(b, pace))
        AnimalNow.apply(mapOf("focus_buddy" to false))
        runIn(host, b, FaceState.IDLE, 1.2f)
        assertEquals("the buddy off: they play, drawn at the full rate", 0, host.restFps(b, pace))
        AnimalNow.focus(false)
        AnimalNow.focusEndDue = 0L
        runIn(host, b, FaceState.IDLE, 1.2f)
        assertEquals(0, host.restFps(b, pace))
        runIn(host, b, FaceState.IDLE, 1.2f, serious = true)
        assertEquals("a serious moment takes them away", 30, host.restFps(b, pace))
    }

    @Test
    fun `a nod, a glow and petting are drawn at the full rate while they play`() {
        val host = FaceHost()
        val a = FakeAnimal()
        runIn(host, a, FaceState.IDLE, 2f)
        assertEquals("resting", 30, host.restFps(a, pace))
        AnimalNow.factSaved()
        assertEquals("the nod plays", 0, host.restFps(a, pace))
        AnimalNow.factAt = System.nanoTime() - 2_000_000_000L
        assertEquals(30, host.restFps(a, pace))
        AnimalNow.longAnswer()
        assertEquals("the glow plays", 0, host.restFps(a, pace))
        AnimalNow.glowAt = System.nanoTime() - 3_000_000_000L
        assertEquals(30, host.restFps(a, pace))
        // Stroked, then let go: drawn fully until the lean has eased out.
        host.onPetDown(200f, 400f)
        runIn(host, a, FaceState.IDLE, 0.8f)
        host.onPetMove(240f, 400f, 10f)
        runIn(host, a, FaceState.IDLE, 0.3f)
        host.onPetUp()
        runIn(host, a, FaceState.IDLE, 0.5f)
        assertEquals("easing out", 0, host.restFps(a, pace))
        runIn(host, a, FaceState.IDLE, 1.2f)
        assertEquals(30, host.restFps(a, pace))
    }

    @Test
    fun `a face just opened or switched to has not rested a while`() {
        val host = FaceHost()
        val b = BusyAnimal()
        runIn(host, b, FaceState.IDLE, 5f)
        host.restFps(b, pace)
        assertEquals("opened 5 s ago, not the host's opening -999", 5f, b.since, 0.1f)
        assertEquals(5f, host.snapshot().hitchPhase, 0.1f)
        // An answer, then a long rest.
        runIn(host, b, FaceState.SPEAKING, 2f)
        runIn(host, b, FaceState.IDLE, 200f, dt = 0.25f)
        host.restFps(b, pace)
        assertEquals(200f, b.since, 0.5f)
        assertEquals(FaceState.SPEAKING, host.snapshot().prevState)
        // Switched to another animal after a long rest: it starts afresh.
        val c = BusyAnimal("busy2")
        host.wear(c)
        runIn(host, c, FaceState.IDLE, 2f)
        host.restFps(c, pace)
        assertEquals(2f, c.since, 0.1f)
        val f = host.snapshot()
        assertEquals(2f, f.hitchPhase, 0.1f)
        assertEquals("and does not settle from the last face's changes", FaceState.IDLE, f.prevState)
        assertTrue(f.past.isNullOrEmpty())
    }

    /** The red panda's pose for [f], as CritterFaces works it out. */
    private fun pandaPose(f: FaceFrame) = CritterPose.pose(
        f.state, f.prevState, f.hitchPhase, f.t, f.amp,
        hist = CritterPose.Hist(prev2 = f.prevState2, gap = f.prevGap, prevAmp = f.prevAmp, prevAmp2 = f.prevAmp2, past = f.past),
    )

    /** The same moment, for a face that had been in [f]'s state for ever. */
    private fun settledPose(f: FaceFrame) = CritterPose.pose(f.state, f.state, 1e9f, f.t, f.amp)

    @Test
    fun `opening straight into waiting on you plays no arrival`() {
        for (viaEffect in listOf(false, true)) {
            val host = FaceHost()
            val a = FakeAnimal()
            // FaceView's LaunchedEffect(state) may reach the host before its first frame.
            if (viaEffect) host.onStateChange(FaceState.APPROVAL)
            runIn(host, a, FaceState.APPROVAL, 0.3f)
            val f = host.snapshot()
            assertEquals(FaceState.APPROVAL, f.state)
            assertEquals("not a change from idle", FaceState.APPROVAL, f.prevState)
            assertTrue("no arrival: ${f.hitchPhase}", f.hitchPhase > CritterPose.ARRIVE_S)
            assertTrue(f.past.isNullOrEmpty())
            assertEquals(settledPose(f).toList(), pandaPose(f).toList())
            // A later change is a change as always.
            runIn(host, a, FaceState.IDLE, 0.3f)
            assertEquals(FaceState.APPROVAL, host.snapshot().prevState)
            assertTrue(host.snapshot().hitchPhase < 0.5f)
        }
    }

    @Test
    fun `opening straight into standby is asleep from the first frame`() {
        for (viaEffect in listOf(false, true)) {
            val host = FaceHost()
            val a = FakeAnimal()
            if (viaEffect) host.onStateChange(FaceState.STANDBY)
            host.advance(1f / 60f, FaceState.STANDBY, null, null, Bindings.DEFAULTS, a, pace = pace)
            val first = host.snapshot()
            assertEquals(FaceState.STANDBY, first.prevState)
            assertEquals("no falling asleep: already asleep", settledPose(first).toList(), pandaPose(first).toList())
            runIn(host, a, FaceState.STANDBY, 1f)
            val f = host.snapshot()
            assertEquals(settledPose(f).toList(), pandaPose(f).toList())
        }
    }

    @Test
    fun `a face switched to while waiting on you plays no arrival for it`() {
        val host = FaceHost()
        val a = FakeAnimal()
        runIn(host, a, FaceState.IDLE, 1f)
        runIn(host, a, FaceState.APPROVAL, 30f, dt = 0.25f)
        host.wear(BusyAnimal("other"))
        val f = host.snapshot()
        assertEquals(FaceState.APPROVAL, f.state)
        assertTrue("the approval's own time, not the new face's: ${f.hitchPhase}", f.hitchPhase > 29f)
    }

    @Test
    fun `phrase-end gestures start when the voice arrives after the face turns to speaking`() {
        val host = FaceHost()
        val a = FakeAnimal()
        host.talkingGesture = { _, _ -> false }
        runIn(host, a, FaceState.IDLE, 1f)
        runIn(host, a, FaceState.SPEAKING, 1f)
        assertEquals("no voice yet: the gestures keep their own timing", -1, host.snapshot().behave.phraseN)
        runIn(host, a, FaceState.SPEAKING, 0.2f, voice = true)
        assertEquals("the voice arrives: they follow its phrase ends", 0, host.snapshot().behave.phraseN)
        runIn(host, a, FaceState.IDLE, 3f)
        assertEquals("off after the answer", -1, host.snapshot().behave.phraseN)
        // While the face's own gesture plays, it waits; then it switches.
        val h2 = FaceHost()
        var playing = true
        h2.talkingGesture = { _, _ -> playing }
        runIn(h2, a, FaceState.SPEAKING, 0.5f)
        runIn(h2, a, FaceState.SPEAKING, 0.5f, voice = true)
        assertEquals("a gesture is playing: not yet", -1, h2.snapshot().behave.phraseN)
        playing = false
        runIn(h2, a, FaceState.SPEAKING, 0.2f, voice = true)
        assertEquals("clear: now it follows the phrase ends", 0, h2.snapshot().behave.phraseN)
    }

    @Test
    fun `a long press then a stroke pets the animal and never turns it`() {
        val host = FaceHost()
        val a = FakeAnimal()
        run(host, a, 1f)
        host.onPetDown(200f, 400f)
        run(host, a, 0.6f)
        host.onPetMove(260f, 400f, 10f)
        host.onDrag(Offset(60f, 0f))
        host.onDragEnd()
        run(host, a, 0.3f)
        val f = host.snapshot()
        assertEquals("not turned", 0f, f.yaw, 1e-6f)
        assertTrue("petting: ${f.behave.pet}", f.behave.pet > 0.5f)
        host.onPetUp()
        // A quick drag: turned, and no petting.
        host.onPetDown(200f, 400f)
        run(host, a, 0.05f)
        host.onPetMove(260f, 400f, 10f)
        host.onDrag(Offset(60f, 0f))
        host.onDragEnd()
        run(host, a, 1.2f)
        host.onPetUp()
        val g = host.snapshot()
        assertTrue("turned: ${g.yaw}", g.yaw != 0f)
        assertEquals(0f, g.behave.pet, 0.02f)
    }
}
