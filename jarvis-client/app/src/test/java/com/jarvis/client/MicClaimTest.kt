package com.jarvis.client

import com.jarvis.client.voice.MicClaim
import com.jarvis.client.voice.MicLedger
import com.jarvis.client.voice.MicOwner
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The microphone ledger's TWO participants, held on the JVM.
 *
 * The bug this file exists for (privacy audit, 2026-11-05): [MicOwner.TALK] was
 * defined and never used, `audio/Recorder.kt` - the talk button, the voice check
 * and the training clip - never touched the ledger, and only the hands-free
 * answer window ever took it. So the answer window's refusal could never fire
 * and a second `AudioRecord` could open over a held press.
 *
 * A JVM test cannot build an `AudioRecord` or an Android `Service`, so the
 * decision both of them make is [MicClaim] - the ledger plus the sentence a
 * refusal is shown in - and this file drives that with a fresh [MicLedger]. The
 * last test pins both real files to it, because "the recorder is wired to the
 * ledger" is exactly what was missing.
 */
class MicClaimTest {

    @Test
    fun `with the talk button holding it, the answer window does not open - and says why`() {
        val mic = MicLedger()
        assertEquals(MicClaim.Now.Open, MicClaim.take(MicOwner.TALK, mic))
        assertEquals(MicOwner.TALK, mic.holder())

        val claim = MicClaim.take(MicOwner.HANDSFREE, mic)
        assertTrue("the window opened over a sentence in progress", claim is MicClaim.Now.Busy)
        val why = (claim as MicClaim.Now.Busy).why
        assertEquals(MicClaim.TALKING, why)
        // Nothing was stolen, which is the whole reason a refusal is safe here:
        // cutting the owner's sentence off would lose what he said.
        assertEquals(MicOwner.TALK, mic.holder())
        assertFalse("Live and the wake word stay out too", mic.freeFor(MicOwner.LIVE))
        assertFalse(mic.freeFor(MicOwner.WAKE))
    }

    @Test
    fun `with the answer window open, the talk button does not open a second recorder`() {
        val mic = MicLedger()
        assertEquals(MicClaim.Now.Open, MicClaim.take(MicOwner.HANDSFREE, mic))

        val claim = MicClaim.take(MicOwner.TALK, mic)
        assertTrue("the talk button opened a second recorder", claim is MicClaim.Now.Busy)
        val why = (claim as MicClaim.Now.Busy).why
        assertEquals(MicClaim.LISTENING, why)
        assertEquals("the window still has it", MicOwner.HANDSFREE, mic.holder())
    }

    @Test
    fun `a refusal is never silent, and the two sides do not share one sentence`() {
        // Both sentences are whole sentences that say what happened, and they
        // are different: one is about a sentence being spoken, the other about
        // an answer being heard. One generic line for both would be right about
        // neither.
        for (why in listOf(MicClaim.TALKING, MicClaim.LISTENING, MicClaim.BUSY)) {
            assertTrue("a refusal had no words: '$why'", why.isNotBlank())
            assertTrue("a refusal was not a sentence: '$why'", why.trim().endsWith("."))
            assertFalse("a refusal blamed the card: '$why'", why.contains("expired"))
        }
        assertNotEquals(MicClaim.TALKING, MicClaim.LISTENING)
        // The hands-free side names what the owner was doing, because a card
        // that is never read out needs to say why it was not.
        assertTrue(MicClaim.TALKING.contains("talking"))
        // The talk button's side says how long the wait is, so the button does
        // not read as broken for ten seconds and then start working.
        assertTrue(MicClaim.LISTENING.contains("Try again"))
    }

    @Test
    fun `the microphone comes back when the window closes`() {
        val mic = MicLedger()
        MicClaim.take(MicOwner.HANDSFREE, mic)
        assertTrue(MicClaim.take(MicOwner.TALK, mic) is MicClaim.Now.Busy)

        MicClaim.free(MicOwner.HANDSFREE, mic)
        assertNull("the window gave it back", mic.holder())
        assertEquals(MicClaim.Now.Open, MicClaim.take(MicOwner.TALK, mic))

        // ...and the other way round: the window opens once the press is over.
        MicClaim.free(MicOwner.TALK, mic)
        assertEquals(MicClaim.Now.Open, MicClaim.take(MicOwner.HANDSFREE, mic))
        MicClaim.free(MicOwner.HANDSFREE, mic)
    }

    @Test
    fun `a release from the part that does not hold it frees nothing`() {
        val mic = MicLedger()
        MicClaim.take(MicOwner.HANDSFREE, mic)
        MicClaim.free(MicOwner.TALK, mic)
        MicClaim.free(MicOwner.LIVE, mic)
        assertEquals("another part's microphone was freed", MicOwner.HANDSFREE, mic.holder())
        MicClaim.free(MicOwner.HANDSFREE, mic)
    }

    @Test
    fun `the app's one ledger is the default, so a caller cannot forget it`() {
        // The two real call sites pass no ledger; this is the path they take.
        try {
            assertTrue(MicClaim.take(MicOwner.TALK) is MicClaim.Now.Open)
            assertEquals(MicOwner.TALK, MicOwner.holder())
            assertTrue(MicClaim.take(MicOwner.HANDSFREE) is MicClaim.Now.Busy)
        } finally {
            MicClaim.free(MicOwner.TALK)
        }
        assertNull("the shared ledger is left clean", MicOwner.holder())
    }

    @Test
    fun `the real recorder takes the ledger before it opens its AudioRecord`() {
        // The audit's finding in one sentence: `voice/MicOwner.kt` named TALK
        // and nothing used it. A JVM test cannot open an AudioRecord, so this
        // pins the wiring - the claim comes BEFORE the constructor (a claim
        // after it would already have opened the second recorder), and the
        // release is in the `finally` that every early return goes through.
        val recorder = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/audio/Recorder.kt",
        )
        val take = recorder.indexOf("MicClaim.take(MicOwner.TALK)")
        val open = recorder.indexOf("AudioRecord(")
        val call = recorder.indexOf("capture(maxSeconds")
        val free = recorder.indexOf("MicClaim.free(MicOwner.TALK)")
        assertTrue("the recorder never takes the microphone ledger", take >= 0)
        assertTrue("the recorder no longer opens an AudioRecord at all", open >= 0)
        assertTrue("the capture is not called any more", call >= 0)
        assertTrue("the recorder never gives the microphone back", free >= 0)
        assertTrue(
            "the AudioRecord is opened before the claim, so the ledger cannot stop it",
            take < open,
        )
        assertTrue("the release does not wrap the capture", call < free)
        assertTrue(
            "the release is not in a finally, so an early return can leak the ledger",
            recorder.substring(call, free).contains("finally"),
        )
        assertTrue(
            "a refusal is worded, never a silent return",
            recorder.contains("Failure.MicBusy("),
        )
    }

    @Test
    fun `the answer window takes the same ledger, and names its refusal`() {
        val service = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/service/HandsfreeService.kt",
        )
        assertTrue(
            "the answer window no longer claims the microphone",
            service.contains("MicClaim.take(MicOwner.HANDSFREE)"),
        )
        assertTrue(
            "the answer window no longer gives it back",
            service.contains("MicClaim.free(MicOwner.HANDSFREE)"),
        )
        // The sentence used to be a constant copied from this file; it is
        // MicClaim's now, so both sides cannot drift apart.
        assertFalse(
            "the service still carries its own copy of the sentence",
            service.contains("const val TALKING"),
        )
    }
}
