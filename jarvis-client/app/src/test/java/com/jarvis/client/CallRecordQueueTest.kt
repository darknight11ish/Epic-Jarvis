package com.jarvis.client

import com.jarvis.client.call.CallRecordRules
import com.jarvis.client.call.CallRecordStore
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
 * The durable queue: a recording survives a dropped connection, a killed app
 * and a phone that was restarted mid-call.
 *
 * This is the owner's requirement in his own words - "keep chunks in a
 * durable local queue so a dropped connection loses nothing" - so the tests
 * are about what is ON DISK after each step, read back by a NEW instance of
 * the store (which is what a restart is).
 */
class CallRecordQueueTest {

    @get:Rule
    val temp = TemporaryFolder()

    private fun store(root: File = temp.root) = CallRecordStore(root)

    @Test
    fun `a chunk written is a chunk the next launch finds`() {
        val pcm = ByteArray(CallRecordRules.CHUNK_BYTES) { (it % 251).toByte() }
        val session = store().begin(1_762_375_299_123L)
        assertEquals(1, session.writeChunk(pcm))
        assertEquals(CallRecordRules.CHUNK_BYTES.toLong(), session.bytes())

        // A NEW store, as if the app had been killed and started again.
        val reopened = store().unfinished()
        assertNotNull("the recording must still be found after a restart", reopened)
        assertEquals(1_762_375_299_123L, reopened!!.startedAtMs)
        val chunk = reopened.nextUnsent()
        assertNotNull(chunk)
        assertEquals(1, chunk!!.seq)
        assertTrue("the audio must be the same bytes", pcm.contentEquals(chunk.read()))
    }

    @Test
    fun `sequence numbers climb and are never reused`() {
        val session = store().begin(1L)
        assertEquals(1, session.writeChunk(ByteArray(10)))
        assertEquals(2, session.writeChunk(ByteArray(10)))
        assertEquals(3, session.writeChunk(ByteArray(10)))
        assertEquals(listOf(1, 2, 3), session.chunks().map { it.seq })
        assertEquals(30L, session.bytes())
    }

    @Test
    fun `an acknowledged chunk is not sent again, and a restart remembers`() {
        val session = store().begin(2L)
        session.writeChunk(ByteArray(32_000))
        session.writeChunk(ByteArray(32_000))
        session.markSent(1)

        val reopened = store().unfinished()!!
        assertEquals(setOf(1), reopened.sentSeqs())
        assertEquals(2, reopened.nextUnsent()?.seq)
        reopened.markSent(2)
        assertNull("everything is acknowledged", reopened.nextUnsent())
    }

    @Test
    fun `the audio is written before anything is sent`() {
        // The order is the whole promise: a chunk on disk is a chunk that
        // cannot be lost by the network. This asserts the FILE exists and is
        // complete, not that a request was made.
        val dir = temp.newFolder("call-record-root")
        val session = store(dir).begin(3L)
        val pcm = ByteArray(1_024) { 7 }
        assertEquals(1, session.writeChunk(pcm))
        val onDisk = File(session.dir, "chunk-000001.pcm")
        assertTrue(onDisk.isFile)
        assertEquals(1_024L, onDisk.length())
        assertTrue(pcm.contentEquals(onDisk.readBytes()))
    }

    @Test
    fun `the pc session id survives a restart`() {
        val session = store().begin(4L)
        session.writeChunk(ByteArray(100))
        session.setPcSession("pc-session-abc")
        val reopened = store().unfinished()!!
        assertEquals("pc-session-abc", reopened.pcSession)
    }

    @Test
    fun `finished means the pc has it, and the folder can go`() {
        val session = store().begin(5L)
        session.writeChunk(ByteArray(100))
        session.markFinished("Calls/2026-11-04 13.41.md")
        assertTrue(session.finished())
        assertEquals("Calls/2026-11-04 13.41.md", session.note)
        assertNull("a finished recording is not waiting", store().unfinished())
        session.remove()
        assertFalse(session.dir.exists())
    }

    @Test
    fun `two recordings in a row do not overwrite each other`() {
        val first = store().begin(6L)
        first.writeChunk(ByteArray(10))
        val second = store().begin(7L)
        second.writeChunk(ByteArray(10))
        assertTrue("two folders, not one", first.dir != second.dir)
        assertEquals(2, store().sessions().size)
        // Oldest first: the one that has waited longest is sent first.
        assertEquals(6L, store().unsent().first().startedAtMs)
    }

    @Test
    fun `an unfinished short chunk is discarded rather than sent as audio`() {
        val session = store().begin(8L)
        session.writeChunk(ByteArray(10))
        // A kill halfway through the next write leaves a .part file, and the
        // file is renamed into place only when it is complete.
        File(session.dir, "chunk-000002.pcm.part").writeBytes(ByteArray(5))
        val reopened = store().unfinished()!!
        assertEquals(listOf(1), reopened.chunks().map { it.seq })
        assertEquals(10L, reopened.bytes())
    }

    @Test
    fun `an empty write is refused, not counted`() {
        val session = store().begin(9L)
        assertEquals(-1, session.writeChunk(ByteArray(0)))
        assertTrue(session.chunks().isEmpty())
        assertFalse(session.hasAudio())
    }

    @Test
    fun `the duration reported to the pc is the audio on disk`() {
        val session = store().begin(10L)
        // Three half-chunks at 16 kHz mono: 48,000 bytes is 1.5 s.
        session.writeChunk(ByteArray(16_000))
        session.writeChunk(ByteArray(16_000))
        session.writeChunk(ByteArray(16_000))
        assertEquals(1L, session.durationSec())
        session.writeChunk(ByteArray(32_000))
        assertEquals(2L, session.durationSec())
    }

    @Test
    fun `meta keeps the date the call began`() {
        val ms = 1_762_382_099_000L
        val session = store().begin(ms)
        session.writeChunk(ByteArray(10))
        val meta = File(session.dir, "meta.txt").readText()
        assertTrue("meta must name the call's own date", meta.contains("started_at="))
        assertTrue(meta.contains(CallRecordRules.startedAt(ms)))
    }
}
