package com.jarvis.client

import androidx.compose.ui.geometry.Offset
import com.jarvis.client.face.AnimalNow
import com.jarvis.client.face.Arc
import com.jarvis.client.face.Bindings
import com.jarvis.client.face.CritterFace
import com.jarvis.client.face.Face
import com.jarvis.client.face.FaceFrame
import com.jarvis.client.face.FaceHost
import com.jarvis.client.face.FrameRateTarget
import com.jarvis.client.face.RestPace
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
