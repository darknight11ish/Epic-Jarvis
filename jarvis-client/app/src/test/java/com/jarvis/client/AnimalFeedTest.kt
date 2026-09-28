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
        assertEquals(0, f.opts(0f, 0f, 0f).phraseN)
        repeat(60) { f.stepFrame(1f / 60f, FaceState.SPEAKING, 0f, 0.5f) }
        repeat(20) { f.stepFrame(1f / 60f, FaceState.SPEAKING, 0f, 0f) }
        assertEquals(1, f.opts(0f, 0f, 0f).phraseN)
        f.onState(FaceState.IDLE, voiced = false)
        assertEquals("off when the speaking stretch ends", -1, f.opts(0f, 0f, 0f).phraseN)
        AnimalNow.apply(mapOf("nods" to false))
        f.onState(FaceState.SPEAKING, voiced = false)
        f.onState(FaceState.SPEAKING, voiced = true)
        assertEquals("nods off: the next answer keeps the gestures' own timing", -1, f.opts(0f, 0f, 0f).phraseN)
    }

    @Test
    fun phraseEndsStartWhenTheVoiceArrivesAfterTheFaceTurnsToSpeaking() {
        // The real order: the PC says "speaking" as the answer's words start
        // to stream, and the voice is heard a moment later (made sentence by
        // sentence). The gestures must still follow its phrase ends.
        val f = AnimalFeed()
        f.onState(FaceState.THINKING, voiced = false)
        repeat(90) {
            f.onState(FaceState.SPEAKING, voiced = false)
            f.stepFrame(1f / 60f, FaceState.SPEAKING, 0f, null)
        }
        assertFalse("no voice yet", f.phraseOn)
        f.onState(FaceState.SPEAKING, voiced = true)
        assertTrue("on as the voice is first heard", f.phraseOn)
        assertEquals(0, f.opts(0f, 0f, 0f).phraseN)
        // A pause between two sentences, the voice quiet: still on.
        repeat(30) {
            f.onState(FaceState.SPEAKING, voiced = false)
            f.stepFrame(1f / 60f, FaceState.SPEAKING, 0f, null)
        }
        assertTrue(f.phraseOn)
    }

    @Test
    fun phraseEndsWaitForAGestureToFinish() {
        val f = AnimalFeed()
        var asked = 0
        f.onState(FaceState.SPEAKING, voiced = false) { asked++; false }
        assertEquals("asked only once a voice is heard", 0, asked)
        f.onState(FaceState.SPEAKING, voiced = true) { asked++; true }
        assertFalse("a gesture of its own is playing: switching now would cut it off", f.phraseOn)
        f.onState(FaceState.SPEAKING, voiced = true) { asked++; false }
        assertTrue("on at the first clear frame (the desktop's rule)", f.phraseOn)
        f.onState(FaceState.SPEAKING, voiced = true) { asked++; true }
        assertTrue("once on, it stays on for the answer", f.phraseOn)
        assertEquals("not asked again once on", 2, asked)
        f.onState(FaceState.IDLE, voiced = false)
        assertFalse("off after the answer", f.phraseOn)
        f.onState(FaceState.SPEAKING, voiced = true) { false }
        assertTrue("the next answer decides afresh", f.phraseOn)
    }

    @Test
    fun theFactNodNeverShowsWhileAppLockOrHiddenListsAreOn() {
        assertFalse(AnimalNow.factSavedIf(appLock = true, privateLists = false, now = 10 * s))
        assertEquals("no nod under App lock", 0L, AnimalNow.factAt)
        assertFalse(AnimalNow.factSavedIf(appLock = false, privateLists = true, now = 10 * s))
        assertEquals("no nod under Hide memory lists", 0L, AnimalNow.factAt)
        assertFalse(AnimalNow.factSavedIf(appLock = true, privateLists = true, now = 10 * s))
        assertEquals(0L, AnimalNow.factAt)
        assertFalse(AnimalNow.factSavedIf(appLock = false, privateLists = false, replayed = true, now = 10 * s))
        assertEquals("no nod for a replayed event", 0L, AnimalNow.factAt)
        assertTrue(AnimalNow.factSavedIf(appLock = false, privateLists = false, now = 10 * s))
        assertEquals(10 * s, AnimalNow.factAt)
    }

    @Test
    fun aReplayedEventIsToldApartByTheHellosLatestId() {
        assertFalse("no hello yet: nothing counts as replayed", AnimalNow.isReplay("5", -1L))
        assertTrue(AnimalNow.isReplay("5", 7L))
        assertTrue(AnimalNow.isReplay("7", 7L))
        assertFalse("above the hello's latest: live", AnimalNow.isReplay("8", 7L))
        assertFalse(AnimalNow.isReplay(null, 7L))
        assertFalse(AnimalNow.isReplay("abc", 7L))
    }

    @Test
    fun replayedMomentsDoNotPlayAgain() {
        // A long answer's glow: only live.
        AnimalNow.deepEvent(json("""{"id": "d1", "state": "done"}"""), replayed = true, now = 10 * s)
        assertEquals(0L, AnimalNow.glowAt)
        AnimalNow.deepEvent(json("""{"id": "d1", "state": "done"}"""), replayed = false, now = 10 * s)
        assertEquals(10 * s, AnimalNow.glowAt)
        // A session that started and ended while the phone was away: the pair
        // replays on reconnect - no buddy left on, and no stretch.
        AnimalNow.focusEvent(json("""{"state": "started"}"""), replayed = true, now = 20 * s)
        AnimalNow.focusEvent(json("""{"state": "ended"}"""), replayed = true, now = 20 * s)
        assertFalse(AnimalNow.focusOn)
        assertEquals("no stretch for a replayed end", 0L, AnimalNow.focusEndDue)
        // A replayed start still says a session is on (it may still be running).
        AnimalNow.focusEvent(json("""{"state": "started"}"""), replayed = true, now = 30 * s)
        assertTrue(AnimalNow.focusOn)
        // A live end: the stretch.
        AnimalNow.focusEvent(json("""{"state": "ended"}"""), replayed = false, now = 40 * s)
        assertEquals(40 * s, AnimalNow.focusEndDue)
    }

    @Test
    fun aStaleResumeStopsTheFocusBuddy() {
        AnimalNow.focus(true, 1 * s)
        AnimalNow.focusUnknown()
        assertFalse("an 'ended' may have been missed", AnimalNow.focusOn)
        assertEquals(0L, AnimalNow.focusEndDue)
        AnimalNow.focus(true, 1 * s)
        AnimalNow.focus(false, 2 * s)
        AnimalNow.focusUnknown()
        assertEquals("nor a stretch waiting from before", 0L, AnimalNow.focusEndDue)
    }

    @Test
    fun thePCsDefaultsBeforeAnythingIsHeardAreNotARead() {
        val before = AnimalNow.reads
        AnimalNow.apply(mapOf("nods" to true), stored = false)
        assertEquals("the defaults handed over before anything is heard", before, AnimalNow.reads)
        AnimalNow.apply(mapOf("nods" to false))
        assertEquals(before + 1, AnimalNow.reads)
        // So a face opened on a first pairing still takes the real ones at once.
        AnimalNow.reads = 0
        val f = AnimalFeed()
        AnimalNow.apply(mapOf("nods" to true), stored = false)
        f.stepWeights(0.3f)
        AnimalNow.apply(mapOf("nods" to false))
        f.stepWeights(1f / 60f)
        assertEquals(0f, f.opts(0f, 0f, 0f).nods)
    }

    @Test
    fun aLongPressOpensTheBrainUnlessItPetsAnAnimal() {
        val hold = (AnimalFeed.PET_HOLD_S * 1000f).toLong()
        assertTrue("a short tap opens it", AnimalNow.pressOpensBrain(120L, character = true, petting = true))
        assertTrue("just under the petting hold", AnimalNow.pressOpensBrain(hold - 1, character = true, petting = true))
        assertFalse("held as long as petting takes: it pets", AnimalNow.pressOpensBrain(hold, character = true, petting = true))
        assertTrue("Petting off: a long press opens it, as before", AnimalNow.pressOpensBrain(2_000L, character = true, petting = false))
        assertTrue("not a character: as before", AnimalNow.pressOpensBrain(2_000L, character = false, petting = true))
        AnimalNow.apply(mapOf("petting" to false))
        assertTrue("reads the switch", AnimalNow.pressOpensBrain(2_000L, character = true))
    }

    @Test
    fun withPettingOffAHeldPressIsAnOrdinaryPress() {
        AnimalNow.apply(mapOf("petting" to false))
        val f = AnimalFeed()
        f.petDown(200f, 400f)
        f.stepWeights(0.8f)
        assertFalse(f.petting())
        assertFalse("a drag after the hold turns the face", f.petMove(260f, 400f, 10f))
        repeat(30) { f.stepWeights(1f / 60f) }
        assertEquals(0f, f.opts(0f, 0f, 0f).pet, 0f)
        assertFalse(f.momentPlaying(0L))
    }

    @Test
    fun pettingStillWorksAfterDaysOnScreen() {
        // Four days of 120 Hz frames, then a press: a Float clock stopped
        // moving at about three, and the hold never came.
        val f = AnimalFeed()
        repeat(96) { f.stepWeights(3600f) }
        f.petDown(200f, 400f)
        repeat(70) { f.stepWeights(1f / 120f) }
        assertTrue("held 0.58 s at 120 Hz", f.petting())
    }

    @Test
    fun theMomentsAreDrawnAtTheFullRateWhilePlaying() {
        val f = AnimalFeed()
        f.stepWeights(0.1f)
        assertFalse(f.momentPlaying(100 * s))
        AnimalNow.factSaved(100 * s)
        assertTrue("the nod", f.momentPlaying(100 * s + s / 2))
        assertFalse("over", f.momentPlaying(102 * s))
        AnimalNow.longAnswer(200 * s)
        assertTrue("the glow", f.momentPlaying(200 * s + s))
        assertFalse(f.momentPlaying(202 * s))
        AnimalNow.apply(mapOf("acks" to false))
        f.stepWeights(1.1f)
        AnimalNow.longAnswer(300 * s)
        assertFalse("acknowledgements off: nothing plays", f.momentPlaying(300 * s + s / 2))
        // The focus stretch.
        AnimalNow.focus(true, 400 * s)
        AnimalNow.focus(false, 401 * s)
        f.stepFrame(0.1f, FaceState.IDLE, 0f, null, now = 402 * s)
        assertTrue("the stretch", f.momentPlaying(402 * s))
        f.stepWeights(3.3f)
        assertFalse(f.momentPlaying(402 * s))
    }

    @Test
    fun aFocusSessionQuietensTheHappeningsOnlyWithTheBuddyOn() {
        val f = AnimalFeed()
        AnimalNow.focus(true, 1 * s)
        f.stepWeights(0.5f)
        assertFalse("still easing in", f.focusQuiet())
        f.stepWeights(0.6f)
        assertTrue(f.focusQuiet())
        AnimalNow.apply(mapOf("focus_buddy" to false))
        f.stepWeights(1.1f)
        assertFalse("the buddy off: the happenings play on", f.focusQuiet())
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
