package com.jarvis.client

import com.jarvis.client.face.AnimalFeed
import com.jarvis.client.face.AnimalNow
import com.jarvis.client.face.CritterPose
import kotlinx.serialization.json.Json
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * What the phone feeds the animals for the new behaviours (the owner's
 * decisions of 2026-09-28; docs/CRITTERS.md "What each app feeds them"):
 * [AnimalNow] (the switches and the moments JarvisRuntime hears) and
 * [AnimalFeed] (one face's eased weights, pauses, petting and focus
 * stretch). The pose itself is CritterPoseTest's.
 */
class AnimalFeedTest {

    private val s = 1_000_000_000L

    @Before
    @After
    fun reset() {
        AnimalNow.apply(mapOf("nods" to true, "focus_buddy" to true, "acks" to true, "petting" to true, "cute_moments" to true))
        AnimalNow.factAt = 0L
        AnimalNow.glowAt = 0L
        AnimalNow.focusOn = false
        AnimalNow.focusEndDue = 0L
    }

    private fun json(text: String) = Json.parseToJsonElement(text)

    @Test
    fun theEventsAreRead() {
        assertEquals(true, AnimalNow.focusOf(json("""{"state": "started"}""")))
        assertEquals(true, AnimalNow.focusOf(json("""{"state": "changed"}""")))
        assertEquals(false, AnimalNow.focusOf(json("""{"state": "ended"}""")))
        assertNull(AnimalNow.focusOf(json("""{"state": "callout", "seq": 3}""")))
        assertNull(AnimalNow.focusOf(json("""{"state": true}""")))
        assertTrue(AnimalNow.deepDone(json("""{"id": "d1", "state": "done"}""")))
        assertFalse(AnimalNow.deepDone(json("""{"id": "d1", "state": "failed"}""")))
        assertFalse(AnimalNow.deepDone(null))
    }

    @Test
    fun aNodAndAGlowAreNeverCloserThanThePoseAllows() {
        AnimalNow.factSaved(10 * s)
        AnimalNow.factSaved(10 * s + s / 2)
        assertEquals("a second fact within 1.2 s does not restart the nod", 10 * s, AnimalNow.factAt)
        AnimalNow.factSaved(12 * s)
        assertEquals(12 * s, AnimalNow.factAt)
        AnimalNow.longAnswer(20 * s)
        AnimalNow.longAnswer(21 * s)
        assertEquals(20 * s, AnimalNow.glowAt)
        AnimalNow.longAnswer(22 * s)
        assertEquals(22 * s, AnimalNow.glowAt)
        val o = AnimalFeed().opts(0f, 0f, 0f, now = 22 * s + s / 4)
        assertEquals(10.25f, o.ackNod, 1e-3f)
        assertEquals(0.25f, o.ackGlow, 1e-3f)
    }

    @Test
    fun nothingHappenedIsNever() {
        val o = AnimalFeed().opts(0f, 0f, 0f, now = 5 * s)
        assertEquals(CritterPose.NEVER, o.ackNod)
        assertEquals(CritterPose.NEVER, o.ackGlow)
        assertEquals(CritterPose.NEVER, o.focusEnd)
        assertEquals(-1, o.phraseN)
        assertEquals("the owner decided variety for every face", 1f, o.variety)
        assertEquals(1f, o.hello)
        assertEquals(0f, o.goodbye)
    }

    @Test
    fun aFaceStartedBeforeTheSwitchesWereReadTakesThemAtOnce() {
        // A face opened before the stored switches load (the defaults: on)...
        AnimalNow.reads = 0
        val f = AnimalFeed()
        f.stepWeights(0.1f)
        assertEquals(1f, f.opts(0f, 0f, 0f).nods)
        // ...takes them the frame they arrive, never easing from the defaults
        // (a switched-off behaviour must not play for a moment as it opens).
        AnimalNow.apply(mapOf("nods" to false, "cute_moments" to false))
        f.stepWeights(1f / 60f)
        assertEquals(0f, f.opts(0f, 0f, 0f).nods)
        assertEquals(0f, f.opts(0f, 0f, 0f).cute)
        // A later change still eases.
        AnimalNow.apply(mapOf("nods" to true))
        f.stepWeights(0.5f)
        val half = f.opts(0f, 0f, 0f).nods
        assertTrue("a later change eases: $half", half > 0.2f && half < 0.8f)
    }

    @Test
    fun aSwitchTurnedOffEasesOutOverASecond() {
        val f = AnimalFeed()
        AnimalNow.apply(mapOf("nods" to false))
        f.stepWeights(0.5f)
        val half = f.opts(0f, 0f, 0f).nods
        assertTrue("part way after half a second: $half", half > 0.2f && half < 0.8f)
        f.stepWeights(0.6f)
        assertEquals(0f, f.opts(0f, 0f, 0f).nods)
    }

    @Test
    fun theOwnersPausesAreFoundWhileListeningOnly() {
        val f = AnimalFeed()
        fun run(state: FaceState, level: Float, secs: Float) {
            var left = secs
            while (left > 0f) { f.stepFrame(1f / 60f, state, level, null); left -= 1f / 60f }
        }
        run(FaceState.LISTENING, 0.4f, 1.0f)
        run(FaceState.LISTENING, 0.0f, 0.5f)
        val o = f.opts(0f, 0f, 0f)
        assertEquals(1, o.heardN)
        assertTrue("the pause was a moment ago: ${o.heard}", o.heard in 0.1f..0.4f)
        // The same talk while thinking counts nothing.
        run(FaceState.THINKING, 0.4f, 1.0f)
        run(FaceState.THINKING, 0.0f, 0.5f)
        assertEquals(1, f.opts(0f, 0f, 0f).heardN)
    }

    @Test
    fun phraseEndsOnlyForARealVoiceAndOnlyWithNodsOn() {
        val f = AnimalFeed()
        f.onState(FaceState.SPEAKING, voiced = false)
        assertEquals("a typed or quiet answer keeps the gestures' own timing", -1, f.opts(0f, 0f, 0f).phraseN)
        f.onState(FaceState.SPEAKING, voiced = true)
        assertEquals("never switched in the middle of an answer", -1, f.opts(0f, 0f, 0f).phraseN)
        f.onState(FaceState.IDLE, voiced = false)
        f.onState(FaceState.SPEAKING, voiced = true)
        assertEquals(0, f.opts(0f, 0f, 0f).phraseN)
        repeat(60) { f.stepFrame(1f / 60f, FaceState.SPEAKING, 0f, 0.5f) }
        repeat(20) { f.stepFrame(1f / 60f, FaceState.SPEAKING, 0f, 0f) }
        assertEquals(1, f.opts(0f, 0f, 0f).phraseN)
        AnimalNow.apply(mapOf("nods" to false))
        f.onState(FaceState.IDLE, voiced = false)
        f.onState(FaceState.SPEAKING, voiced = true)
        assertEquals("nods off: the next answer keeps the gestures' own timing", -1, f.opts(0f, 0f, 0f).phraseN)
    }

    @Test
    fun theFocusStretchWaitsForIdle() {
        AnimalNow.focus(true, 1 * s)
        AnimalNow.focus(false, 2 * s)
        assertTrue(AnimalNow.focusEndDue != 0L)
        val f = AnimalFeed()
        f.stepFrame(0.1f, FaceState.SPEAKING, 0f, null, now = 3 * s)
        assertEquals("not while Jarvis is talking", CritterPose.NEVER, f.opts(0f, 0f, 0f).focusEnd)
        f.stepFrame(0.1f, FaceState.IDLE, 0f, null, now = 4 * s)
        f.stepWeights(0.5f)
        assertEquals(0.5f, f.opts(0f, 0f, 0f).focusEnd, 1e-4f)
        assertEquals("handed on once", 0L, AnimalNow.focusEndDue)
        // Too late (a minute of talk after the end): dropped.
        AnimalNow.focus(true, 10 * s)
        AnimalNow.focus(false, 11 * s)
        val g = AnimalFeed()
        g.stepFrame(0.1f, FaceState.IDLE, 0f, null, now = 80 * s)
        assertEquals(CritterPose.NEVER, g.opts(0f, 0f, 0f).focusEnd)
    }

    @Test
    fun aLongPressPetsAndAQuickDragDoesNot() {
        val f = AnimalFeed()
        f.petDown(100f, 400f)
        f.stepWeights(0.2f)
        assertFalse(f.petting())
        // Moved away before the hold: a drag, never a pet.
        assertFalse(f.petMove(140f, 400f, 10f))
        f.stepWeights(0.5f)
        assertFalse(f.petting())
        f.petUp()
        // Held, then stroked.
        f.petDown(200f, 400f)
        f.stepWeights(0.3f)
        f.stepWeights(0.3f)
        assertTrue(f.petting())
        f.stepWeights(0.05f)
        assertTrue(f.petMove(240f, 400f, 10f))
        repeat(12) { f.stepWeights(1f / 60f) }
        val o = f.opts(0f, 0f, 0f)
        assertTrue("eased in: ${o.pet}", o.pet > 0.2f)
        assertTrue("toward the hand's side: ${o.petX}", o.petX > 0f)
        f.petUp()
        repeat(90) { f.stepWeights(1f / 60f) }
        assertEquals("eased out within a second or so", 0f, f.opts(0f, 0f, 0f).pet, 0.02f)
    }
}
