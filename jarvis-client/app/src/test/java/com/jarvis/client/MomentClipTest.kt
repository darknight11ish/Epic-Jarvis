package com.jarvis.client

import com.jarvis.client.net.FlowMoment
import com.jarvis.client.net.FlowStatus
import com.jarvis.client.voice.MomentClip
import com.jarvis.client.voice.MomentFlow
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The owner's report, 2026-11-01: in Jarvis Live on the phone the "One
 * moment." clip was in the default MALE voice while the answer was in the
 * female voice they had chosen.
 *
 * The PC cannot make that mistake: `jarvis_voice_flow.moment()` only hands
 * out a clip whose `key` matches the voice in use (`moment_key()` is a hash
 * of the speaker, speed, face voice and engine), and both halves come from
 * the same `_synthesise`. The phone could: it kept the bytes it had fetched
 * earlier under a NEW key (Live never re-read `flow`), and `toolStarted`
 * played them without comparing keys. A failed/503 fetch also left the old
 * bytes in place.
 *
 * The fix is [MomentClip] plus the wiring in `VoiceSession`: bytes leave
 * this class only through `playable`, which demands the key in use now; a
 * refresh drops the held bytes before it asks, so a refused fetch is
 * silence; and a spoken turn (Live's included) re-reads `flow` first.
 *
 * Off-device, as everywhere in this suite: these pin the pure rule and the
 * shipped wiring. Whether the phone's speaker really makes the male sound is
 * a device field test, not a pass here.
 */
class MomentClipTest {

    private val session =
        "jarvis-client/app/src/main/java/com/jarvis/client/voice/VoiceSession.kt"

    private fun voiceSession(): String = SourceFile.read(session)

    @Test
    fun aClipFetchedForAnotherVoiceIsNeverPlayed() {
        val clip = MomentClip()
        val old = byteArrayOf(1, 2, 3)
        clip.store("bm_george-key", old, "bm_george-key")

        assertNull(
            "bytes fetched for the old voice must not play under the new key",
            clip.playable("af_heart-key", usable = true),
        )
        assertArrayEquals(
            "the same bytes still play for the key they were made for",
            old,
            clip.playable("bm_george-key", usable = true),
        )
        assertNull(
            "and never when the PC says the clip is not usable",
            clip.playable("bm_george-key", usable = false),
        )
        assertNull("an empty key can never match a clip", clip.playable("", usable = true))
    }

    @Test
    fun aNewKeyMeansAFetchIsDue() {
        val clip = MomentClip()
        assertTrue("nothing held yet: a fetch is due", clip.missing("voice-a"))
        clip.store("voice-a", byteArrayOf(7), "voice-a")
        assertFalse("the clip for the current key is not fetched again", clip.missing("voice-a"))
        assertTrue("the owner changed the voice: fetch again", clip.missing("voice-b"))
    }

    @Test
    fun aRefusedFetchLeavesSilenceNotTheOldBytes() {
        val clip = MomentClip()
        clip.store("voice-a", byteArrayOf(1, 2), "voice-a")

        // What VoiceSession.refreshMoment does for a key it does not hold:
        // drop first, then ask. The route answered 503, so nothing is stored.
        clip.clear()
        clip.store("voice-b", null, "voice-b")

        assertNull("a 503 must leave silence", clip.playable("voice-b", usable = true))
        assertNull("the old voice must be gone too", clip.playable("voice-a", usable = true))
        assertTrue("and the next turn asks again", clip.missing("voice-b"))

        // An empty body is the same refusal as a 503 (JarvisApi.voiceMoment
        // turns both into ApiResult.Failed, so `got` is null either way).
        clip.store("voice-b", ByteArray(0), "voice-b")
        assertNull(clip.playable("voice-b", usable = true))
    }

    @Test
    fun bytesOvertakenByAnotherVoiceChangeAreDropped() {
        val clip = MomentClip()
        // Requested for voice-b, but the PC had already moved to voice-c when
        // the bytes arrived: they are a third voice's, so they are not kept.
        clip.store("voice-b", byteArrayOf(9), "voice-c")
        assertNull(clip.playable("voice-b", usable = true))
        assertNull(clip.playable("voice-c", usable = true))
    }

    @Test
    fun oneMomentPerQuestionEvenWhenTheFirstClipIsStale() {
        val moment = MomentFlow()
        moment.turnStarted()
        val clip = MomentClip()
        clip.store("old-key", byteArrayOf(1), "old-key")

        val stale = clip.playable("new-key", usable = true)
        assertNull(stale)
        assertFalse(
            "a clip that cannot play must not use up the question's one moment",
            moment.toolStarted(enabled = true, ready = stale != null),
        )

        clip.clear()
        clip.store("new-key", byteArrayOf(2), "new-key")
        val fresh = clip.playable("new-key", usable = true)
        assertTrue(moment.toolStarted(enabled = true, ready = fresh != null))
        assertFalse("once per question", moment.toolStarted(enabled = true, ready = fresh != null))
    }

    @Test
    fun aTurnStartingMayFetchAClipThePcHasNotMadeYet() {
        val notMade = FlowStatus(
            available = true,
            moment = FlowMoment(enabled = true, key = "af_heart-key", ready = false),
        )
        assertTrue("the PC offers the clip; GET makes it", notMade.momentWanted)
        assertFalse("but it is not ready to play without a wait", notMade.momentUsable)

        val made = notMade.copy(moment = notMade.moment.copy(ready = true))
        assertTrue(made.momentWanted)
        assertTrue(made.momentUsable)

        val off = notMade.copy(moment = notMade.moment.copy(enabled = false))
        assertFalse("switched off on the PC: never fetched", off.momentWanted)

        val noFlow = FlowStatus(available = false, moment = notMade.moment.copy(ready = true))
        assertFalse("a PC without the flow module never gets a fetch", noFlow.momentWanted)
    }

    /**
     * The wiring, held to the shipped source because there is no emulator
     * here: a Live question is a spoken turn and refreshes `flow`; the clip
     * is read through the key-checking [MomentClip.playable]; and a refresh
     * drops the held bytes BEFORE the request, so a refusal cannot fall back
     * to them.
     */
    @Test
    fun theShippedWiringKeepsTheKeyRule() {
        val text = voiceSession()

        val live = text.substringAfter("suspend fun deliverLiveClip(")
            .substringBefore("    /** Jarvis Live: the reply being spoken was stopped")
        assertTrue(
            "a Live question must refresh flow and the clip for the voice in use",
            live.contains("refreshFlow()"),
        )

        val deliver = text.substringAfter("private suspend fun deliver(")
            .substringBefore("val result = api.utterance")
        assertTrue(
            "push-to-talk and the wake word already refreshed flow; keep it",
            deliver.contains("refreshFlow()"),
        )

        val tool = text.substringAfter("fun toolStarted() {").substringBefore("\n    }\n")
        assertTrue("toolStarted must ask the key-checking holder", tool.contains("momentClip.playable("))
        assertFalse("and must never play `.second` of an unchecked pair", tool.contains("clip.second"))

        val refresh = text.substringAfter("private suspend fun refreshMoment(")
            .substringBefore("\n    /**\n     * The `flow` block again")
        val clearAt = refresh.indexOf("momentClip.clear()")
        val fetchAt = refresh.indexOf("api.voiceMoment()")
        val storeAt = refresh.indexOf("momentClip.store(")
        assertTrue("a refresh drops the old bytes", clearAt >= 0)
        assertTrue("a refresh asks the PC", fetchAt >= 0)
        assertTrue("it stores what came back for the key it asked for", storeAt >= 0)
        assertTrue("the drop comes before the wait", clearAt < fetchAt)
        assertTrue("the store comes last", fetchAt < storeAt)
    }
}
