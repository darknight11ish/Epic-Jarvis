package com.jarvis.client

import com.jarvis.client.call.CallRecordRules
import com.jarvis.client.call.CallRecordRules.Effect
import com.jarvis.client.call.CallRecordRules.Event
import com.jarvis.client.call.CallRecordRules.Phase
import com.jarvis.client.call.CallRecordRules.State
import com.jarvis.client.call.Chunker
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.ZoneId

/**
 * The call recorder's rules, on the JVM: every state, every ending, and the
 * arithmetic between a microphone read and a chunk the PC will take.
 *
 * The service (`service/CallRecordService.kt`) only executes these effects, so
 * this file is where the behaviour of a recording actually lives - there is no
 * device in this session and a real call was NOT placed (the field test is the
 * owner's, on his Pixel 9, after both halves land).
 */
class CallRecordRulesTest {

    private val zone: ZoneId = ZoneId.of("America/Los_Angeles")

    // ------------------------------------------------------ the happy path ---

    @Test
    fun `armed waits for a call and claims the microphone`() {
        val step = CallRecordRules.next(State(), Event.ARM)
        assertEquals(Phase.ARMED, step.state.phase)
        assertEquals(
            listOf(Effect.CLAIM_MIC, Effect.START_SERVICE, Effect.SAY_ARMED),
            step.effects,
        )
    }

    @Test
    fun `a call starts the audio and the date is kept`() {
        val armed = CallRecordRules.next(State(), Event.ARM).state.copy(startedAtMs = 1_762_375_299_123L)
        val step = CallRecordRules.next(armed, Event.CALL_START)
        assertEquals(Phase.RECORDING, step.state.phase)
        assertEquals(1_762_375_299_123L, step.state.startedAtMs)
        assertEquals(0L, step.state.bytes)
        assertEquals(listOf(Effect.START_CAPTURE, Effect.SAY_RECORDING), step.effects)
    }

    @Test
    fun `the call ending finishes the recording and keeps the audio`() {
        val step = CallRecordRules.next(recording(bytes = 320_000L), Event.CALL_END)
        assertEquals(Phase.SENDING, step.state.phase)
        assertEquals(listOf(Effect.STOP_CAPTURE, Effect.FINISH), step.effects)
        // Nothing here deletes anything: SENDING is "waiting for the PC".
        assertTrue(step.effects.none { it == Effect.DISCARD || it == Effect.KEEP_QUEUE })
    }

    @Test
    fun `sent closes the whole thing`() {
        val step = CallRecordRules.next(State(phase = Phase.SENDING, session = "s-1"), Event.SENT)
        assertEquals(Phase.OFF, step.state.phase)
        assertEquals(listOf(Effect.RELEASE_MIC, Effect.STOP_SERVICE, Effect.SAY_SENT), step.effects)
    }

    // ---------------------------------------------------------- the endings ---

    @Test
    fun `every way a recording ends goes through sending, with the microphone closed first`() {
        val endings = listOf(
            Event.CALL_END,
            Event.OWNER_STOP,
            Event.LOW_BATTERY,
            Event.HEADSET_UNPLUGGED,
            Event.MIC_REFUSED,
        )
        for (event in endings) {
            val step = CallRecordRules.next(recording(bytes = 160_000L), event)
            assertEquals("$event should end the recording", Phase.SENDING, step.state.phase)
            assertEquals("$event must close the microphone first", Effect.STOP_CAPTURE, step.effects.first())
            assertTrue("$event must finish the upload", step.effects.contains(Effect.FINISH))
            assertTrue("$event must never discard audio", !step.effects.contains(Effect.DISCARD))
        }
    }

    @Test
    fun `a shutdown keeps the queue and asks for no upload`() {
        val step = CallRecordRules.next(recording(bytes = 96_000L), Event.APP_SHUTDOWN)
        assertEquals(Phase.SENDING, step.state.phase)
        assertEquals(listOf(Effect.STOP_CAPTURE, Effect.KEEP_QUEUE), step.effects)
    }

    @Test
    fun `under a second is the one ending that deletes, and it says so`() {
        val step = CallRecordRules.next(recording(bytes = 16_000L), Event.TOO_SHORT)
        assertEquals(Phase.OFF, step.state.phase)
        assertTrue(step.effects.contains(Effect.DISCARD))
        assertTrue(step.effects.contains(Effect.RELEASE_MIC))
        assertTrue(step.effects.contains(Effect.SAY_STOPPED))
    }

    @Test
    fun `the PC being unreachable keeps the audio and says it is waiting`() {
        val sending = State(phase = Phase.SENDING, startedAtMs = 5L)
        val step = CallRecordRules.next(sending, Event.UPLOAD_WAITING)
        assertEquals(Phase.SENDING, step.state.phase)
        assertTrue(step.effects.contains(Effect.KEEP_QUEUE))
        assertTrue(step.effects.contains(Effect.SAY_WAITING))
        // And the microphone is let go: a kept recording must not hold it.
        assertTrue(step.effects.contains(Effect.RELEASE_MIC))
    }

    @Test
    fun `a stop while sending keeps the rest rather than dropping it`() {
        val step = CallRecordRules.next(State(phase = Phase.SENDING), Event.OWNER_STOP)
        assertEquals(Phase.SENDING, step.state.phase)
        assertTrue(step.effects.contains(Effect.KEEP_QUEUE))
        assertTrue(!step.effects.contains(Effect.DISCARD))
    }

    @Test
    fun `disarming before a call releases the microphone and starts nothing`() {
        val step = CallRecordRules.next(State(phase = Phase.ARMED), Event.DISARM)
        assertEquals(Phase.OFF, step.state.phase)
        assertEquals(listOf(Effect.RELEASE_MIC, Effect.STOP_SERVICE, Effect.SAY_STOPPED), step.effects)
        assertTrue(step.effects.none { it == Effect.START_CAPTURE })
    }

    // --------------------------------------------------------- the no-ops ---

    @Test
    fun `nothing happens when nothing is armed`() {
        for (event in Event.values()) {
            val step = CallRecordRules.next(State(), event)
            if (event == Event.ARM) continue
            assertEquals("$event on an idle recorder must do nothing", State(), step.state)
            assertTrue("$event on an idle recorder must start nothing", step.effects.isEmpty())
        }
    }

    @Test
    fun `a second arm does not open a second recording`() {
        val armed = State(phase = Phase.ARMED)
        val step = CallRecordRules.next(armed, Event.ARM)
        assertEquals(armed, step.state)
        assertTrue(step.effects.isEmpty())
    }

    @Test
    fun `a second call-start during a recording changes nothing`() {
        val state = recording(bytes = 1_000L)
        val step = CallRecordRules.next(state, Event.CALL_START)
        assertEquals(state, step.state)
        assertTrue(step.effects.isEmpty())
    }

    @Test
    fun `a disarm during a recording is refused - Stop is the way out`() {
        val state = recording(bytes = 1_000L)
        val step = CallRecordRules.next(state, Event.DISARM)
        assertEquals(state, step.state)
        assertTrue(step.effects.isEmpty())
    }

    @Test
    fun `the whole life is armed then recording then sending then off`() {
        var state = State()
        state = CallRecordRules.next(state, Event.ARM).state
        state = CallRecordRules.next(state, Event.CALL_START).state
        assertEquals(Phase.RECORDING, state.phase)
        state = CallRecordRules.next(state.copy(bytes = 480_000L), Event.CALL_END).state
        assertEquals(Phase.SENDING, state.phase)
        state = CallRecordRules.next(state, Event.SENT).state
        assertEquals(Phase.OFF, state.phase)
    }

    // --------------------------------------------------------- the numbers ---

    @Test
    fun `a chunk is a whole number of samples and of milliseconds`() {
        assertEquals(65_536, CallRecordRules.CHUNK_BYTES)
        assertEquals(32_768, CallRecordRules.CHUNK_SAMPLES)
        // 32,768 samples at 16 kHz is exactly 2.048 s: a boundary never splits
        // a sample, and the duration always converts to whole seconds.
        assertEquals(2_048.0, CallRecordRules.CHUNK_SAMPLES * 1000.0 / CallRecordRules.SAMPLE_RATE, 0.0001)
    }

    @Test
    fun `duration is whole seconds of the audio that was cut`() {
        // One second of 16 kHz mono PCM16 is 32,000 bytes.
        assertEquals(1L, CallRecordRules.durationSec(32_000L))
        assertEquals(0L, CallRecordRules.durationSec(31_999L))
        assertEquals(60L, CallRecordRules.durationSec(32_000L * 60))
        assertEquals(0L, CallRecordRules.durationSec(0L))
    }

    @Test
    fun `the clock is hours minutes seconds`() {
        assertEquals("00:00:00", CallRecordRules.clock(0))
        assertEquals("00:00:59", CallRecordRules.clock(59_999))
        assertEquals("00:04:12", CallRecordRules.clock(252_000))
        assertEquals("01:00:00", CallRecordRules.clock(3_600_000))
        assertEquals("00:00:00", CallRecordRules.clock(-5))
    }

    @Test
    fun `the date carries the phone's own offset, not UTC's day`() {
        // 2026-11-04 13:41:39 in Los Angeles is 21:41:39 UTC - the day is the
        // same here, and the offset is what keeps a late-evening call from
        // being filed tomorrow.
        val ms = java.time.ZonedDateTime.of(2026, 11, 4, 13, 41, 39, 0, zone).toInstant().toEpochMilli()
        assertEquals("2026-11-04T13:41:39-08:00", CallRecordRules.startedAt(ms, zone))
        assertEquals("Call - 2026-11-04 13:41", CallRecordRules.title(ms, zone))
    }

    @Test
    fun `a call just before midnight is dated by the owner's clock`() {
        val ms = java.time.ZonedDateTime.of(2026, 11, 4, 23, 58, 0, 0, zone).toInstant().toEpochMilli()
        assertEquals("2026-11-04T23:58:00-08:00", CallRecordRules.startedAt(ms, zone))
        assertTrue(CallRecordRules.title(ms, zone).endsWith("2026-11-04 23:58"))
    }

    @Test
    fun `samples for a duration`() {
        assertEquals(16_000, CallRecordRules.samplesForMs(1_000))
        assertEquals(800, CallRecordRules.samplesForMs(50))
        assertEquals(0, CallRecordRules.samplesForMs(0))
    }

    // ------------------------------------------------------------ chunker ---

    @Test
    fun `the chunker emits exact chunks and keeps the remainder`() {
        val chunker = Chunker(chunkBytes = 10)
        assertTrue(chunker.push(ByteArray(4) { 1 }).isEmpty())
        assertEquals(4, chunker.buffered)
        // 4 held + 6 = one chunk of 10.
        val one = chunker.push(ByteArray(6) { 2 })
        assertEquals(1, one.size)
        assertEquals(10, one[0].size)
        assertEquals(0, chunker.buffered)
    }

    @Test
    fun `a big read comes out as several exact chunks and a tail`() {
        val chunker = Chunker(chunkBytes = 10)
        val chunks = chunker.push(ByteArray(23))
        assertEquals(2, chunks.size)
        assertEquals(10, chunks[0].size)
        assertEquals(10, chunks[1].size)
        assertEquals(3, chunker.buffered)
        val tail = chunker.flush()
        assertEquals(3, tail?.size)
        assertNull(chunker.flush())
    }

    @Test
    fun `an exact multiple leaves no tail`() {
        val chunker = Chunker(chunkBytes = 8)
        assertEquals(2, chunker.push(ByteArray(16)).size)
        assertNull(chunker.flush())
    }

    @Test
    fun `nothing is lost and nothing is duplicated across awkward reads`() {
        val chunker = Chunker(chunkBytes = 7)
        val input = ByteArray(101) { (it % 100).toByte() }
        val out = ArrayList<Byte>()
        var at = 0
        // Sizes chosen to straddle boundaries: 1, 6, 7, 8, 3, 13, 63.
        for (size in listOf(1, 6, 7, 8, 3, 13, 63)) {
            val piece = input.copyOfRange(at, at + size)
            at += size
            for (chunk in chunker.push(piece)) out.addAll(chunk.toList())
        }
        chunker.flush()?.let { out.addAll(it.toList()) }
        assertEquals(input.size, out.size)
        assertTrue("the bytes must be the same ones, in order", input.contentEquals(out.toByteArray()))
    }

    @Test
    fun `the real chunk size holds 32768 samples`() {
        val chunker = Chunker()
        val pcm = ByteArray(CallRecordRules.CHUNK_BYTES + 2)
        val chunks = chunker.push(pcm)
        assertEquals(1, chunks.size)
        assertEquals(CallRecordRules.CHUNK_BYTES, chunks[0].size)
        assertEquals("two bytes past a whole chunk are held, not dropped", 2, chunker.buffered)
    }

    // --------------------------------------------------------- the words ---

    @Test
    fun `the conversation reminders are the contract's words`() {
        assertEquals("Recording - tell the other person", CallRecordRules.CONSENT_LINE)
        assertEquals("on", CallRecordRules.CONSENT_NOTICE)
        assertEquals("Turn the call on speaker so Jarvis can hear both sides", CallRecordRules.SPEAKER_ASK)
    }

    @Test
    fun `the one line a screen shows`() {
        assertEquals("Call recording armed", CallRecordRules.line(Phase.ARMED))
        assertEquals("Recording call 00:04:12", CallRecordRules.line(Phase.RECORDING, 252_000))
        assertEquals("Off", CallRecordRules.line(Phase.OFF))
    }

    @Test
    fun `a locked phone shows the app name and one fixed line`() {
        val words = CallRecordRules.noticeWords(
            locked = true,
            appName = "Jarvis",
            title = CallRecordRules.RECORDING_TITLE,
            text = CallRecordRules.CONSENT_LINE,
        )
        assertEquals(listOf("Jarvis", CallRecordRules.LOCK_LINE), words)
        val open = CallRecordRules.noticeWords(
            locked = false,
            appName = "Jarvis",
            title = CallRecordRules.RECORDING_TITLE,
            text = CallRecordRules.CONSENT_LINE,
        )
        assertEquals(listOf("Recording call", "Recording - tell the other person"), open)
    }

    @Test
    fun `the directive names two actions and nothing else`() {
        assertEquals("arm", CallRecordRules.actionOf("ARM"))
        assertEquals("stop", CallRecordRules.actionOf(" stop "))
        assertNull(CallRecordRules.actionOf(null))
        assertNull(CallRecordRules.actionOf("record"))
        assertNull(CallRecordRules.actionOf(""))
        assertEquals(Event.ARM, CallRecordRules.eventOf("arm"))
        assertEquals(Event.OWNER_STOP, CallRecordRules.eventOf("stop"))
        assertNull(CallRecordRules.eventOf("pause"))
    }
}

/** A recording in progress with [bytes] already cut, for the endings above. */
private fun recording(bytes: Long) = State(
    phase = Phase.RECORDING,
    startedAtMs = 1_762_375_299_123L,
    session = "s-1",
    bytes = bytes,
)
