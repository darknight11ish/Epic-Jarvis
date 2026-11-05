package com.jarvis.client

import com.jarvis.client.call.CallRecordChunks
import com.jarvis.client.call.CallRecordStore
import com.jarvis.client.net.JarvisJson
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

/**
 * The retry loop, on a plain JVM - including the exact sequence that used to
 * brick a recording for ever (the privacy audit of 2026-11-05, D3).
 *
 * The scenario is a CRASH BETWEEN the PC's 200 and the phone's own bookkeeping:
 *
 *   1. the phone posts chunk 1 and the PC writes it, answering 200;
 *   2. the app dies before it appends "1" to `sent.txt`;
 *   3. it restarts, asks for the first unsent chunk, and gets 1 again;
 *   4. the PC already has it, so it answers 409 `{expected: 3}` (it has 1 and
 *      2, and it wants 3).
 *
 * The old loop retried 1 for ever: nothing was ever sent, the plate only
 * offered "Send it now" (the same seq), and the audio was stuck. These tests
 * hold the recovery: the 409's `expected` is read, every chunk below it is
 * marked sent, and the loop sends the REAL next chunk and finishes.
 */
class CallRecordChunksTest {

    @get:Rule
    val temp = TemporaryFolder()

    private fun store(root: File = temp.root) = CallRecordStore(root)

    private fun obj(json: String): JsonObject = JarvisJson.parseToJsonElement(json).jsonObject

    private fun ack(bytes: Int = 300): JsonObject = obj("""{"ok":true,"bytes":$bytes}""")

    private fun gap(expected: Int): JsonObject = obj("""{"ok":false,"expected":$expected}""")

    @Test
    fun `a crash after the pc answered 200 recovers instead of retrying the same seq for ever`() =
        runBlocking {
            val session = store().begin(1L)
            repeat(3) { session.writeChunk(ByteArray(100) { (it + 1).toByte() }) }
            // THE CRASH: the PC has chunks 1 and 2 (it answered 200 to both),
            // and this phone's sent.txt never got those two lines.
            val pcHas = 2
            val posted = mutableListOf<Int>()
            var finished = false
            val ok = CallRecordChunks.send(
                session = session,
                attempts = 3,
                post = { seq, _ ->
                    posted += seq
                    when {
                        seq == pcHas + 1 -> {
                            finished = true
                            ack()
                        }
                        seq <= pcHas -> gap(pcHas + 1)
                        else -> obj("""{"ok":false}""")
                    }
                },
                pause = { },
            )
            assertTrue("the retry must finish, not fail for ever", ok)
            assertEquals("seq 1 once (refused, already held), then the real gap", listOf(1, 3), posted)
            assertEquals("every chunk is recorded as sent", setOf(1, 2, 3), session.sentSeqs())
            assertNull("nothing is left unsent", session.nextUnsent())
            assertTrue("the real next chunk really went", finished)
        }

    @Test
    fun `the crash recovery writes nothing twice and sends nothing early`() = runBlocking {
        val session = store().begin(2L)
        session.writeChunk(ByteArray(50) { 7 })
        session.writeChunk(ByteArray(50) { 9 })
        val reads = mutableListOf<Int>()
        val ok = CallRecordChunks.send(
            session = session,
            attempts = 2,
            post = { seq, pcm ->
                reads += pcm.size
                // The PC holds both chunks already, so it wants 3 - a seq this
                // phone has not cut, so the loop has nothing left to send.
                if (seq <= 2) gap(3) else obj("""{"ok":false}""")
            },
            pause = { },
        )
        assertTrue("nothing left unsent means it finished", ok)
        assertEquals("each retry is for a real chunk on disk", listOf(50), reads)
        assertEquals(setOf(1, 2), session.sentSeqs())
    }

    @Test
    fun `a card still waiting is retried with the same seq and marks nothing sent`() = runBlocking {
        val session = store().begin(3L)
        session.writeChunk(ByteArray(100) { 1 })
        val posted = mutableListOf<Int>()
        val pauses = mutableListOf<Int>()
        val ok = CallRecordChunks.send(
            session = session,
            attempts = 3,
            post = { seq, _ ->
                posted += seq
                obj("""{"ok":false,"state":"waiting","error":"the card is up"}""")
            },
            pause = { pauses += it },
        )
        assertFalse("a waiting card means not yet, never a false success", ok)
        assertEquals("the SAME seq is retried, exactly as the contract says", listOf(1, 1, 1), posted)
        assertEquals("with a backoff between tries", listOf(1, 2), pauses)
        assertTrue("nothing is marked sent on a refusal with no expected", session.sentSeqs().isEmpty())
        assertNotNull("the audio is still here", session.nextUnsent())
    }

    @Test
    fun `a dropped connection is retried with the same seq and nothing is lost`() = runBlocking {
        val session = store().begin(4L)
        session.writeChunk(ByteArray(100) { 2 })
        val posted = mutableListOf<Int>()
        val ok = CallRecordChunks.send(
            session = session,
            attempts = 3,
            post = { seq, _ ->
                posted += seq
                if (posted.size == 1) null else ack()
            },
            pause = { },
        )
        assertTrue(ok)
        assertEquals(listOf(1, 1), posted)
        assertEquals(setOf(1), session.sentSeqs())
    }

    @Test
    fun `an expected we already hold cannot spin the loop or invent numbers`() = runBlocking {
        val session = store().begin(5L)
        session.writeChunk(ByteArray(100) { 3 })
        val posted = mutableListOf<Int>()
        val ok = CallRecordChunks.send(
            session = session,
            attempts = 2,
            post = { seq, _ ->
                posted += seq
                // Nonsense from the PC: it asks for the very seq this phone is
                // sending. Nothing below it is unsent, so nothing is marked and
                // the same seq is retried; the loop always ends.
                gap(seq)
            },
            pause = { },
        )
        assertFalse(ok)
        assertEquals(listOf(1, 1), posted)
        assertTrue(session.sentSeqs().isEmpty())
    }

    @Test
    fun `two recordings in the queue are sent in order, oldest first`() = runBlocking {
        val older = store().begin(6L)
        older.writeChunk(ByteArray(10) { 1 })
        val newer = store().begin(7L)
        newer.writeChunk(ByteArray(10) { 2 })
        val order = mutableListOf<Long>()
        for (session in store().unsent()) {
            order += session.startedAtMs
            CallRecordChunks.send(
                session = session,
                attempts = 1,
                post = { _, _ -> ack(10) },
                pause = { },
            )
        }
        assertEquals("the one that waited longest goes first", listOf(6L, 7L), order)
        assertNull(older.nextUnsent())
        assertNull(newer.nextUnsent())
    }
}
