package com.jarvis.client

import com.jarvis.client.face.Arc
import com.jarvis.client.face.Bindings
import com.jarvis.client.face.CritterFace
import com.jarvis.client.face.Face
import com.jarvis.client.face.FaceFrame
import com.jarvis.client.face.FaceHost
import com.jarvis.client.face.FrameRateTarget
import com.jarvis.client.face.RestPace
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * How often a resting face is drawn (FaceHost.restFps and advance's own
 * pacing), the owner's "sharp animals on capable hardware" (2026-09-28):
 * an animal rests at 60 with headroom and 30 without, is drawn at the full
 * rate while one of its idle happenings plays, and a picked rate lifts its
 * rest to that; standby stays 15 and banked 2. Every other face keeps the
 * spec's state_fps, and so does any caller that passes no pace.
 */
class FaceRestPaceTest {

    /** An animal whose happenings are switched by hand; nothing is drawn. */
    private class FakeAnimal(var playing: Boolean = false) : CritterFace("fake", "Fake", "") {
        override fun pose(f: FaceFrame) = FloatArray(0)
        override fun uniformsOf(p: FloatArray, mouth: FloatArray?) = emptyMap<String, FloatArray>()
        override fun overlayOf(p: FloatArray, yaw: Float, pitch: Float) = floatArrayOf(0f, 0f, 0f)
        override fun busyAt(state: FaceState, t: Float) = playing && state == FaceState.IDLE
    }

    /** Frames drawn a second on a [hz] panel, after the full-rate window has passed. */
    private fun drawsPerSecond(
        face: Face,
        pace: RestPace?,
        state: FaceState = FaceState.IDLE,
        hz: Int = 120,
        still: Boolean = false,
    ): Float {
        val host = FaceHost()
        val dt = 1f / hz
        repeat(hz) { host.advance(dt, state, null, null, Bindings.DEFAULTS, face, still = still, pace = pace) }
        var drawn = 0
        repeat(hz * 2) {
            if (host.advance(dt, state, null, null, Bindings.DEFAULTS, face, still = still, pace = pace)) drawn++
        }
        return drawn / 2f
    }

    @Test
    fun `an animal rests at 60 with headroom and 30 without`() {
        val a = FakeAnimal()
        assertEquals(60f, drawsPerSecond(a, RestPace(FrameRateTarget.AUTO, headroom = true)), 1f)
        assertEquals(30f, drawsPerSecond(a, RestPace(FrameRateTarget.AUTO, headroom = false)), 1f)
        assertEquals(60f, drawsPerSecond(a, RestPace(FrameRateTarget.AUTO, true), FaceState.APPROVAL), 1f)
    }

    @Test
    fun `a playing happening is drawn at the full rate, unless Still has taken it away`() {
        val a = FakeAnimal(playing = true)
        assertEquals(120f, drawsPerSecond(a, RestPace(FrameRateTarget.AUTO, false)), 1f)
        assertEquals(30f, drawsPerSecond(a, RestPace(FrameRateTarget.AUTO, false), still = true), 1f)
    }

    @Test
    fun `a picked rate lifts an animal's rest, and standby and banked stay put`() {
        val a = FakeAnimal()
        assertEquals(90f, drawsPerSecond(a, RestPace(FrameRateTarget.FPS_90, false), hz = 180), 1f)
        // On whole shares of the panel: 90 on a 120 Hz panel is 60 (the pick rule).
        assertEquals(60f, drawsPerSecond(a, RestPace(FrameRateTarget.FPS_90, false)), 1f)
        assertEquals(120f, drawsPerSecond(a, RestPace(FrameRateTarget.MAX, false)), 1f)
        assertEquals(30f, drawsPerSecond(a, RestPace(FrameRateTarget.FPS_30, true)), 1f)
        for (t in FrameRateTarget.entries) {
            assertEquals(15f, drawsPerSecond(a, RestPace(t, true), FaceState.STANDBY), 1f)
            assertEquals(2f, drawsPerSecond(a, RestPace(t, true), FaceState.BANKED), 0.6f)
        }
        // Busy states are never held back.
        assertEquals(120f, drawsPerSecond(a, RestPace(FrameRateTarget.AUTO, false), FaceState.THINKING), 1f)
    }

    @Test
    fun `other faces and callers with no pace keep the spec's rates`() {
        assertEquals(30f, drawsPerSecond(Arc, RestPace(FrameRateTarget.MAX, true)), 1f)
        assertEquals(30f, drawsPerSecond(FakeAnimal(), null), 1f)
        assertEquals(15f, drawsPerSecond(Arc, null, FaceState.STANDBY), 1f)
    }

    /** The loop's branch choice reads the same rule, and the full-rate window after a change. */
    @Test
    fun `the frame loop reads the same resting rate`() {
        val host = FaceHost()
        val a = FakeAnimal()
        val pace = RestPace(FrameRateTarget.AUTO, headroom = true)
        repeat(60) { host.advance(1f / 60f, FaceState.THINKING, null, null, Bindings.DEFAULTS, a, pace = pace) }
        host.advance(1f / 60f, FaceState.IDLE, null, null, Bindings.DEFAULTS, a, pace = pace)
        assertEquals("the first 600 ms after a change run at the full rate", 0, host.restFps(a, pace))
        repeat(60) { host.advance(1f / 60f, FaceState.IDLE, null, null, Bindings.DEFAULTS, a, pace = pace) }
        assertEquals(60, host.restFps(a, pace))
        assertTrue(host.restFps(Arc, pace) == 30)
    }
}
