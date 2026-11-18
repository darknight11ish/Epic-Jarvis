package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.SendFile
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.yield
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import kotlin.io.encoding.Base64
import kotlin.io.encoding.ExperimentalEncodingApi

/**
 * "Send one file from the PC to the phone" (the owner's ask of 2026-10-31;
 * Gemini Q7, plus Q1-Q3 of 2026-11-14; docs/JARVIS-API.md section 172;
 * backend `jarvis_send_file.py`) - the phone's half of the contract as it is
 * after 2026-11-14: **2 GiB, fetched in 1 MiB pieces**, one completed
 * transfer, receipted to the PC once the whole file verifies.
 *
 * What this proves, and why each matters to the owner:
 *  - the cap is 2 GiB and a piece is 1 MiB, both written once and read from
 *    the PC's own list answer (`cap_bytes`, `chunk_bytes`);
 *  - a request carries only an id of the PC's shape and integer offsets - no
 *    filename, no path, and no length over one piece;
 *  - a slice's own sha256 is checked before it is written, and the OLD
 *    whole-file answer (no offset) is refused instead of saved at the wrong
 *    place;
 *  - a dropped link retries the SAME offset and the bytes never shift: that is
 *    what makes a 2 GiB transfer survive a VPN hiccup;
 *  - a refusal from the PC is final, a broken slice is retried, the retry
 *    budget is real, and a cancelled download stops asking;
 *  - the whole-file sha256 is the gate before anything is kept, and the file
 *    hash is read from disk the same way the runtime reads it back;
 *  - the receipt (`POST /api/files/ack`) carries the id alone, and a receipt
 *    that fails is ignored: the PC's grace expires the id and the verified
 *    file stays on the phone (Q1);
 *  - the save's room is **2.1x** the file, checked before the first slice, and
 *    a tight phone gets a plain sentence instead of a half-written 2 GiB file
 *    (Q2);
 *  - View is offered only at or under **200 MiB**, with "Use Save for files
 *    over 200 MiB" above it, and the cache copies are cleaned up promptly
 *    (Q3);
 *  - the words are the app's plain ones: the 2 GiB ceiling, bytes/percent
 *    progress, and "one completed transfer" instead of the old "works once";
 *  - the wiring keeps View (FileProvider + ACTION_VIEW) and Save
 *    (MediaStore.Downloads) as the phone's own steps, draws nothing while the
 *    private lists are hidden, and never approves anything here.
 */
class SendFileTest {

    @get:Rule
    val tmp = TemporaryFolder()

    private fun json(text: String): JsonObject = JarvisJson.parseToJsonElement(text).jsonObject

    private val id = "file_0123456789abcdef"

    // --------------------------------------------------------------- routes ----

    @Test
    fun `the cap is 2 GiB, a piece is 1 MiB, and only an id and legal numbers can be asked for`() {
        assertEquals("/api/files/send", SendFile.LIST_PATH)
        assertEquals("/api/files/download", SendFile.DOWNLOAD_PATH)
        assertEquals("/api/files/ack", SendFile.ACK_PATH)
        assertEquals(2_147_483_648L, SendFile.MAX_BYTES)
        assertEquals(1_048_576, SendFile.CHUNK_BYTES)
        assertEquals(600, SendFile.TTL_SECONDS)
        assertEquals(4, SendFile.CHUNK_TRIES)
        assertEquals(209_715_200L, SendFile.VIEW_MAX_BYTES)
        assertEquals(21L, SendFile.SPACE_TENTHS)

        assertEquals(
            "/api/files/download?id=$id&offset=0&length=1048576",
            SendFile.downloadPath(id, 0L, SendFile.CHUNK_BYTES),
        )
        assertEquals(
            "/api/files/download?id=$id&offset=1048576&length=1048576",
            SendFile.downloadPath(id, 1_048_576L, SendFile.CHUNK_BYTES),
        )
        // The last piece is the bytes that remain, never a whole piece.
        assertEquals(
            "/api/files/download?id=$id&offset=10&length=2",
            SendFile.downloadPath(id, 10L, 2),
        )
        // A request names an id and two numbers, never a file.
        val path = SendFile.downloadPath(id, 0L, SendFile.CHUNK_BYTES)!!
        assertFalse(path.contains("name="))
        assertFalse(path.contains("path="))
        assertFalse(path.contains("file="))
        assertFalse(path.contains("C:"))

        assertNull("a filename is not an id", SendFile.downloadPath("invoice.pdf", 0L, 4))
        assertNull("a path is not an id", SendFile.downloadPath("C:\\Users\\me\\invoice.pdf", 0L, 4))
        assertNull("too short", SendFile.downloadPath("file_abc", 0L, 4))
        assertNull("too long", SendFile.downloadPath("file_" + "a".repeat(65), 0L, 4))
        assertNull("blank", SendFile.downloadPath("  ", 0L, 4))
        assertNull("a negative offset", SendFile.downloadPath(id, -1L, 4))
        assertNull("no bytes", SendFile.downloadPath(id, 0L, 0))
        assertNull("more than one piece", SendFile.downloadPath(id, 0L, SendFile.CHUNK_BYTES + 1))
    }

    // ----------------------------------------------------------- the list ----

    @Test
    fun `the list answer carries the PC's own cap and piece size, and both are read`() {
        val reply = SendFile.readList(
            200,
            json(
                """{"ok": true, "count": 1, "cap_bytes": 2147483648, "chunk_bytes": 1048576,
                    "ttl_seconds": 600, "single_use": true,
                    "said": "A file appears here only after the owner approved its card; it can be downloaded once, within ten minutes.",
                    "files": [{"id": "$id", "name": "invoice.pdf",
                               "folder": "C:\\Users\\me\\Documents", "size_bytes": 1482331,
                               "mime": "application/pdf", "expires_in": 540}]}""",
            ),
        )
        val ready = reply as SendFile.ListReply.Ready
        assertEquals(1, ready.files.size)
        val file = ready.files.single()
        assertEquals(id, file.id)
        assertEquals("invoice.pdf", file.name)
        assertEquals("C:\\Users\\me\\Documents", file.folder)
        assertEquals(1482331L, file.sizeBytes)
        assertEquals("application/pdf", file.mime)
        assertEquals(540, file.expiresIn)
        assertEquals(2_147_483_648L, ready.capBytes)
        assertEquals(1_048_576, ready.chunkBytes)
        assertEquals(600, ready.ttlSeconds)
        assertTrue(ready.singleUse)
        assertTrue("the PC's own sentence is kept", ready.said.contains("only after the owner approved"))
    }

    @Test
    fun `a list without the chunk fields falls back to this phone's numbers, and an older PC is Missing`() {
        assertEquals(SendFile.ListReply.Missing, SendFile.readList(404, null))
        assertEquals(SendFile.ListReply.Missing, SendFile.readList(501, null))
        val failed = SendFile.readList(500, json("""{"ok": false, "error": "the list broke"}"""))
        assertEquals("the list broke", (failed as SendFile.ListReply.Refused).said)

        // A PC that predates the chunking change: no cap_bytes/chunk_bytes.
        val old = SendFile.readList(200, json("""{"ok": true, "files": []}"""))
            as SendFile.ListReply.Ready
        assertEquals(SendFile.MAX_BYTES, old.capBytes)
        assertEquals(SendFile.CHUNK_BYTES, old.chunkBytes)
        // A PC that takes smaller pieces says so, and its number is what is used.
        val small = SendFile.readList(200, json("""{"ok": true, "chunk_bytes": 4096, "files": []}"""))
            as SendFile.ListReply.Ready
        assertEquals(4096, small.chunkBytes)
        // A nonsense cap or piece size is never taken as the PC's word.
        val odd = SendFile.readList(
            200,
            json("""{"ok": true, "cap_bytes": 0, "chunk_bytes": 999999999, "files": []}"""),
        ) as SendFile.ListReply.Ready
        assertEquals(SendFile.MAX_BYTES, odd.capBytes)
        assertEquals(SendFile.CHUNK_BYTES, odd.chunkBytes)

        // A row without an id or a name cannot be asked for, so it is not drawn.
        val rows = SendFile.readList(
            200,
            json("""{"ok": true, "files": [
                {"name": "no id.pdf"}, {"id": "$id"}]}"""),
        ) as SendFile.ListReply.Ready
        assertTrue(rows.files.isEmpty())
    }

    // ------------------------------------------------------- the pieces ----

    private val whole = "Jarvis sent this file.".encodeToByteArray()
    private val wholeSha = SendFile.sha256(whole)

    @OptIn(ExperimentalEncodingApi::class)
    private fun chunkJson(
        offset: Long = 0,
        data: ByteArray = "hello".encodeToByteArray(),
        size: Long = 5,
        sha: String = SendFile.sha256("hello".encodeToByteArray()),
        chunkSha: String = SendFile.sha256(data),
        name: String = "invoice.pdf",
        mime: String = "application/pdf",
        length: Int = data.size,
    ): JsonObject = json(
        """{"ok": true, "id": "$id", "name": "$name", "size_bytes": $size,
            "mime": "$mime", "offset": $offset, "length": $length,
            "data": "${Base64.encode(data)}", "sha256": "$sha",
            "chunk_sha256": "$chunkSha"}""",
    )

    @OptIn(ExperimentalEncodingApi::class)
    @Test
    fun `one piece is read whole, and its own sha256 is checked before it is used`() {
        val got = SendFile.readChunk(200, chunkJson()) as SendFile.Chunk.Got
        assertEquals(0L, got.offset)
        assertEquals(5, got.length)
        assertEquals("hello", got.data.decodeToString())
        assertEquals("invoice.pdf", got.name)
        assertEquals("application/pdf", got.mime)
        assertEquals(5L, got.sizeBytes)
        assertEquals(SendFile.sha256("hello".encodeToByteArray()), got.chunkSha256)

        // A piece whose slice hash disagrees with its bytes is not used.
        val bad = SendFile.readChunk(200, chunkJson(chunkSha = "0".repeat(64)))
        assertEquals(SendFile.NOT_WHAT_WAS_SENT, (bad as SendFile.Chunk.Broken).said)
        // A declared length that disagrees with the bytes is not this piece.
        val wrongLength = SendFile.readChunk(200, chunkJson(length = 3))
        assertEquals(SendFile.WRONG_SLICE, (wrongLength as SendFile.Chunk.Broken).said)
        // No data at all is not a file.
        val empty = SendFile.readChunk(
            200,
            json(
                """{"ok": true, "offset": 0, "length": 1, "chunk_sha256": "x",
                    "sha256": "y", "size_bytes": 1}""",
            ),
        )
        assertEquals(SendFile.UNREADABLE, (empty as SendFile.Chunk.Broken).said)
        // Not base64 either.
        val garbage = SendFile.readChunk(
            200,
            json(
                """{"ok": true, "offset": 0, "length": 3, "data": "!!!!",
                    "chunk_sha256": "x", "sha256": "y", "size_bytes": 3}""",
            ),
        )
        assertEquals(SendFile.UNREADABLE, (garbage as SendFile.Chunk.Broken).said)
        val noBody = SendFile.readChunk(200, null)
        assertEquals(SendFile.UNREADABLE, (noBody as SendFile.Chunk.Broken).said)
    }

    @Test
    fun `the old whole-file answer is refused, not saved at the wrong offset`() {
        // Exactly what an old PC answered: all the bytes, no offset/length/slice hash.
        val old = SendFile.readChunk(
            200,
            json(
                """{"ok": true, "name": "invoice.pdf", "size_bytes": 5,
                    "mime": "application/pdf", "sha256": "$wholeSha",
                    "data": "aGVsbG8="}""",
            ),
        )
        assertEquals(SendFile.NOT_PIECES, (old as SendFile.Chunk.Broken).said)
        assertTrue("the sentence tells the owner what to do", SendFile.NOT_PIECES.contains("Update Jarvis"))
    }

    @Test
    fun `a 404, a 409, a 416 and a 400 keep the PC's own sentence and are final`() {
        val gone = SendFile.readChunk(
            404,
            json("""{"ok": false, "error": "That file is not waiting for your phone any more - the ten-minute window passed or it was already downloaded."}"""),
        )
        assertTrue((gone as SendFile.Chunk.Refused).said.contains("ten-minute window passed"))
        val changed = SendFile.readChunk(
            409,
            json("""{"ok": false, "error": "That file changed since the card was approved, so nothing was sent."}"""),
        )
        assertTrue((changed as SendFile.Chunk.Refused).said.contains("changed since the card"))
        val past = SendFile.readChunk(
            416,
            json("""{"ok": false, "error": "That offset is past the end of the file."}"""),
        )
        assertTrue((past as SendFile.Chunk.Refused).said.contains("past the end"))
        val badNumbers = SendFile.readChunk(
            400,
            json("""{"ok": false, "error": "offset and length must be whole numbers."}"""),
        )
        assertTrue((badNumbers as SendFile.Chunk.Refused).said.contains("whole numbers"))
        // A 5xx is the PC saying "not right now", not a final no: it comes back
        // as a broken piece, so a 2 GiB transfer may retry the same offset.
        val hiccup = SendFile.readChunk(
            503,
            json("""{"ok": false, "error": "That file could not be read just now, so nothing was sent."}"""),
        )
        assertTrue((hiccup as SendFile.Chunk.Broken).said.contains("could not be read just now"))
        // A 5xx with no sentence still says something plain, never a code.
        val bare = SendFile.readChunk(500, null)
        assertTrue((bare as SendFile.Chunk.Broken).said.isNotBlank())
    }

    @Test
    fun `the slice rule is checked directly - offset, length, whole size and whole hash`() {
        val piece = SendFile.Chunk.Got(
            offset = 4L,
            length = 2,
            data = byteArrayOf(4, 5),
            sha256 = wholeSha,
            chunkSha256 = SendFile.sha256(byteArrayOf(4, 5)),
            sizeBytes = 10L,
            name = "invoice.pdf",
            mime = "application/pdf",
        )
        assertNull(SendFile.sliceProblem(piece, 4L, 4, 0L, ""))
        assertEquals(
            SendFile.WRONG_SLICE,
            SendFile.sliceProblem(piece.copy(offset = 0L), 4L, 4, 0L, ""),
        )
        assertEquals(
            SendFile.WRONG_SLICE,
            SendFile.sliceProblem(piece.copy(data = ByteArray(0), length = 0), 4L, 4, 0L, ""),
        )
        assertEquals(
            SendFile.WRONG_SLICE,
            SendFile.sliceProblem(piece, 4L, 1, 0L, ""),
        )
        assertEquals(
            SendFile.CHANGED,
            SendFile.sliceProblem(piece.copy(sizeBytes = 12L), 4L, 4, 10L, wholeSha),
        )
        assertEquals(
            SendFile.CHANGED,
            SendFile.sliceProblem(piece.copy(sha256 = "0".repeat(64)), 4L, 4, 10L, wholeSha),
        )
        // The last piece may be shorter than a whole piece; it is still right.
        assertNull(SendFile.sliceProblem(piece.copy(length = 1, data = byteArrayOf(4)), 4L, 2, 10L, wholeSha))
    }

    // --------------------------------------------------- the whole download ----

    /** A fake PC that serves [bytes] in pieces, records every ask, and can misbehave. */
    private class FakePc(val bytes: ByteArray) {
        val asked = mutableListOf<Pair<Long, Int>>()
        var dropNext = 0
        var brokenNext = 0

        /** How many times the first asks for EACH offset fail before it is served. */
        var dropsPerOffset = 0
        private val dropped = mutableMapOf<Long, Int>()

        fun fetch(offset: Long, length: Int): ApiResult<SendFile.Chunk> {
            asked += offset to length
            if (dropNext > 0) {
                dropNext -= 1
                return ApiResult.Failed(ApiError.Unreachable("the link dropped"))
            }
            val already = dropped[offset] ?: 0
            if (already < dropsPerOffset) {
                dropped[offset] = already + 1
                return ApiResult.Failed(ApiError.Unreachable("the link dropped"))
            }
            if (brokenNext > 0) {
                brokenNext -= 1
                return ApiResult.Ok(SendFile.Chunk.Broken(SendFile.UNREADABLE))
            }
            if (offset >= bytes.size) {
                return ApiResult.Ok(SendFile.Chunk.Refused("That file is not waiting any more."))
            }
            val end = minOf(offset + length, bytes.size.toLong()).toInt()
            val slice = bytes.copyOfRange(offset.toInt(), end)
            return ApiResult.Ok(
                SendFile.Chunk.Got(
                    offset = offset,
                    length = slice.size,
                    data = slice,
                    sha256 = SendFile.sha256(bytes),
                    chunkSha256 = SendFile.sha256(slice),
                    sizeBytes = bytes.size.toLong(),
                    name = "invoice.pdf",
                    mime = "application/pdf",
                ),
            )
        }
    }

    @Test
    fun `a file is assembled from pieces, the last is clamped, and progress ends at the whole size`() =
        runBlocking {
            val bytes = ByteArray(10) { it.toByte() }
            val pc = FakePc(bytes)
            val written = ByteArray(bytes.size)
            val progress = mutableListOf<SendFile.Progress>()
            val outcome = SendFile.receive(
                fetch = { offset, length -> pc.fetch(offset, length) },
                write = { offset, data -> data.copyInto(written, offset.toInt()) },
                chunkBytes = 4,
                onProgress = { progress += it },
            )
            assertTrue("the whole file must arrive", outcome is SendFile.Outcome.Done)
            val done = outcome as SendFile.Outcome.Done
            assertEquals(10L, done.sizeBytes)
            assertEquals(SendFile.sha256(bytes), done.sha256)
            assertEquals("invoice.pdf", done.name)
            assertEquals("application/pdf", done.mime)
            assertArrayEquals(bytes, written)
            // Three asks, the last only the two bytes that remain.
            assertEquals(listOf(0L to 4, 4L to 4, 8L to 2), pc.asked)
            assertEquals(
                listOf(4L to 10L, 8L to 10L, 10L to 10L),
                progress.map { it.received to it.total },
            )
            assertEquals(
                "10 bytes received of 10 (100.0%)",
                SendFile.progressWords(progress.last().received, progress.last().total),
            )
        }

    @Test
    fun `a dropped link retries the same offset, so the bytes are never shifted`() = runBlocking {
        val bytes = ByteArray(10) { it.toByte() }
        val pc = FakePc(bytes).apply { dropNext = 2 }
        val written = ByteArray(bytes.size)
        val outcome = SendFile.receive(
            fetch = { offset, length -> pc.fetch(offset, length) },
            write = { offset, data -> data.copyInto(written, offset.toInt()) },
            chunkBytes = 4,
            pause = {},
        )
        assertTrue(outcome is SendFile.Outcome.Done)
        assertArrayEquals(bytes, written)
        // The first offset is asked for three times before the link comes back.
        assertEquals(listOf(0L to 4, 0L to 4, 0L to 4, 4L to 4, 8L to 2), pc.asked)
    }

    @Test
    fun `a broken piece is asked for again, and a real refusal stops at once`() = runBlocking {
        val bytes = ByteArray(10) { it.toByte() }
        val pc = FakePc(bytes).apply { brokenNext = 1 }
        val outcome = SendFile.receive(
            fetch = { offset, length -> pc.fetch(offset, length) },
            write = { _, _ -> },
            chunkBytes = 4,
            pause = {},
        )
        assertTrue(outcome is SendFile.Outcome.Done)
        assertEquals(listOf(0L to 4, 0L to 4, 4L to 4, 8L to 2), pc.asked)

        var asks = 0
        val refused = SendFile.receive(
            fetch = { _, _ ->
                asks += 1
                ApiResult.Ok(SendFile.Chunk.Refused("That file is not waiting any more."))
            },
            write = { _, _ -> },
            chunkBytes = 4,
            pause = {},
        )
        assertEquals("a refusal is final, not retried", 1, asks)
        assertEquals(
            "That file is not waiting any more.",
            (refused as SendFile.Outcome.Refused).said,
        )
    }

    @Test
    fun `the retry budget is per piece, so a long file is not killed by many small hiccups`() =
        runBlocking {
            val bytes = ByteArray(10) { it.toByte() }
            // Every slice loses its first two answers: two separate hiccups, not
            // one cumulative count that a 2 GiB transfer would run out of at
            // piece 4 of 2048.
            val pc = FakePc(bytes).apply { dropsPerOffset = 2 }
            val written = ByteArray(bytes.size)
            val outcome = SendFile.receive(
                fetch = { offset, length -> pc.fetch(offset, length) },
                write = { offset, data -> data.copyInto(written, offset.toInt()) },
                chunkBytes = 4,
                tries = 3,
                pause = {},
            )
            assertTrue(outcome is SendFile.Outcome.Done)
            assertArrayEquals(bytes, written)
            assertEquals(
                listOf(
                    0L to 4, 0L to 4, 0L to 4,
                    4L to 4, 4L to 4, 4L to 4,
                    8L to 2, 8L to 2, 8L to 2,
                ),
                pc.asked,
            )
        }

    @Test
    fun `the retry budget runs out and the download says the link failed, not that it worked`() =
        runBlocking {
            val pc = FakePc(ByteArray(10)).apply { dropNext = 99 }
            var wrote = false
            val outcome = SendFile.receive(
                fetch = { offset, length -> pc.fetch(offset, length) },
                write = { _, _ -> wrote = true },
                chunkBytes = 4,
                tries = 3,
                pause = {},
            )
            assertTrue(outcome is SendFile.Outcome.Failed)
            assertEquals(3, pc.asked.size)
            assertTrue("every retry is the SAME offset", pc.asked.all { it.first == 0L })
            assertFalse("nothing was written from a failed transfer", wrote)
        }

    @Test
    fun `a file that changes under the download is refused, never stitched together`() = runBlocking {
        var asks = 0
        val outcome = SendFile.receive(
            fetch = { offset, _ ->
                asks += 1
                val total = if (asks == 1) 8L else 12L
                ApiResult.Ok(
                    SendFile.Chunk.Got(
                        offset = offset,
                        length = 4,
                        data = byteArrayOf(1, 2, 3, 4),
                        sha256 = wholeSha,
                        chunkSha256 = SendFile.sha256(byteArrayOf(1, 2, 3, 4)),
                        sizeBytes = total,
                        name = "invoice.pdf",
                        mime = "application/pdf",
                    ),
                )
            },
            write = { _, _ -> },
            chunkBytes = 4,
            tries = 2,
            pause = {},
        )
        assertEquals(SendFile.CHANGED, (outcome as SendFile.Outcome.Refused).said)
    }

    @Test
    fun `a file over the phone's 2 GiB ceiling is refused before a byte is written`() = runBlocking {
        var wrote = false
        val outcome = SendFile.receive(
            fetch = { offset, _ ->
                ApiResult.Ok(
                    SendFile.Chunk.Got(
                        offset = offset,
                        length = 4,
                        data = byteArrayOf(1, 2, 3, 4),
                        sha256 = wholeSha,
                        chunkSha256 = SendFile.sha256(byteArrayOf(1, 2, 3, 4)),
                        sizeBytes = SendFile.MAX_BYTES + 1,
                        name = "huge.bin",
                        mime = "application/octet-stream",
                    ),
                )
            },
            write = { _, _ -> wrote = true },
            chunkBytes = 4,
        )
        assertTrue(outcome is SendFile.Outcome.Refused)
        assertTrue((outcome as SendFile.Outcome.Refused).said.contains("2 GiB"))
        assertFalse(wrote)
    }

    @Test
    fun `a cancelled download stops asking the PC and never claims the file arrived`() = runBlocking {
        var asked = 0
        var finished = false
        val job = launch {
            SendFile.receive(
                fetch = { offset, _ ->
                    asked += 1
                    if (asked == 1) {
                        ApiResult.Ok(
                            SendFile.Chunk.Got(
                                offset = offset,
                                length = 2,
                                data = byteArrayOf(1, 2),
                                sha256 = wholeSha,
                                chunkSha256 = SendFile.sha256(byteArrayOf(1, 2)),
                                sizeBytes = 4,
                                name = "invoice.pdf",
                                mime = "application/pdf",
                            ),
                        )
                    } else {
                        // The screen went away: nothing will answer this ask.
                        awaitCancellation()
                    }
                },
                write = { _, _ -> },
                chunkBytes = 2,
            )
            finished = true
        }
        while (asked < 2) yield()
        job.cancelAndJoin()
        assertTrue(job.isCancelled)
        assertFalse("a cancelled download must not report a finished file", finished)
    }

    // ---------------------------------------------------------- the hashes ----

    @Test
    fun `sha256 is lower-case hex as the PC spells it, in memory and read back from disk`() {
        // A fixed, independently known vector: "hello".
        assertEquals(
            "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
            SendFile.sha256("hello".encodeToByteArray()),
        )
        val file = tmp.newFile("whole.bin")
        file.writeBytes("hello".encodeToByteArray())
        assertEquals(
            "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
            SendFile.sha256(file),
        )
        // An empty file hashes too - the runtime never trusts a size alone.
        val empty = tmp.newFile("empty.bin")
        assertEquals(SendFile.sha256(ByteArray(0)), SendFile.sha256(empty))
    }

    // ------------------------------------------------------ the phone's words ----

    @Test
    fun `the limits say 2 GiB and one completed transfer, and no old phrase is left`() {
        assertTrue(SendFile.LIMITS.contains("2 GiB"))
        assertTrue(SendFile.LIMITS.contains("one completed transfer"))
        assertEquals("2 GiB", SendFile.capWords(SendFile.MAX_BYTES))
        assertEquals("10 MiB", SendFile.capWords(10L * 1024L * 1024L))
        assertEquals("2 KiB", SendFile.capWords(2048L))
        assertEquals("1536 bytes", SendFile.capWords(1536L))

        // Every sentence this phone shows about the transfer: none may promise
        // the old "works once", and none may say "completed download" now that
        // the receipt is what finishes it.
        val words = listOf(
            SendFile.LIMITS,
            SendFile.VIEW_USE_SAVE,
            SendFile.spaceWords(1_000_000L, 10_000_000L),
        )
        for (w in words) {
            assertFalse("no 'works once' in: $w", w.contains("works once"))
            assertFalse("no 'completed download' in: $w", w.contains("completed download"))
        }
    }

    @Test
    fun `a big size reads as GB, progress is bytes and percent, and the pre-check is the smaller cap`() {
        assertEquals("2,147,483,648 bytes (2.0 GB large)", SendFile.sizeWords(SendFile.MAX_BYTES))
        assertEquals("812 bytes", SendFile.sizeWords(812))
        assertEquals("1,482,331 bytes (1.4 MB large)", SendFile.sizeWords(1482331))
        assertEquals("2,048 bytes (2 KB large)", SendFile.sizeWords(2048))

        assertEquals("0 bytes received", SendFile.progressWords(0, 0))
        assertEquals("0 bytes received of 10 (0.0%)", SendFile.progressWords(-5, 10))
        assertEquals("1,024 bytes received of 2,048 (50.0%)", SendFile.progressWords(1024, 2048))
        assertEquals("31 bytes received of 100 (31.0%)", SendFile.progressWords(31, 100))
        assertEquals(
            "1,048,576 bytes received of 2,147,483,648 (0.0%)",
            SendFile.progressWords(1_048_576L, SendFile.MAX_BYTES),
        )
        assertEquals(
            "2,147,483,648 bytes received of 2,147,483,648 (100.0%)",
            SendFile.progressWords(SendFile.MAX_BYTES, SendFile.MAX_BYTES),
        )

        // At the ceiling fits; one byte over does not; the PC's smaller cap wins;
        // neither can lift this phone above its own 2 GiB.
        assertTrue(SendFile.fitsCap(SendFile.MAX_BYTES, SendFile.MAX_BYTES))
        assertFalse(SendFile.fitsCap(SendFile.MAX_BYTES + 1, SendFile.MAX_BYTES))
        assertFalse(SendFile.fitsCap(11L * 1024L * 1024L, 10L * 1024L * 1024L))
        assertTrue(SendFile.fitsCap(5L, 0L))
        assertFalse(SendFile.fitsCap(SendFile.MAX_BYTES + 1, 4L * 1024L * 1024L * 1024L))
        assertTrue(SendFile.overCapWords(3L * 1024L * 1024L * 1024L, 4L * 1024L * 1024L * 1024L)
            .contains("2 GiB"))
    }

    @Test
    fun `a filename is made safe to write, and the PC's other numbers are said plainly`() {
        assertEquals("invoice.pdf", SendFile.nameForDisk("invoice.pdf"))
        assertEquals("invoice.pdf", SendFile.nameForDisk("C:\\Users\\me\\invoice.pdf"))
        assertEquals("invoice.pdf", SendFile.nameForDisk("../../invoice.pdf"))
        assertEquals("invoice.pdf", SendFile.nameForDisk("in<v>oice.pdf"))
        assertEquals("file", SendFile.nameForDisk("   "))
        assertEquals("file", SendFile.nameForDisk("..."))
        assertEquals("expires in 9 min", SendFile.expiryWords(540))
        assertEquals("expires in 2 min", SendFile.expiryWords(61))
        assertEquals("expires in under a minute", SendFile.expiryWords(30))
        assertEquals("expired", SendFile.expiryWords(0))
        assertEquals("application/octet-stream", SendFile.mimeOr(""))
        assertEquals("application/pdf", SendFile.mimeOr("application/pdf"))
    }

    // ----------------------------------- the phone's own limits and receipt ----

    @Test
    fun `View is allowed at exactly 200 MiB and refused one byte over`() {
        assertEquals(209_715_200L, SendFile.VIEW_MAX_BYTES)
        assertTrue("exactly 200 MiB may be opened", SendFile.canView(SendFile.VIEW_MAX_BYTES))
        assertFalse(
            "one byte over 200 MiB must not be opened",
            SendFile.canView(SendFile.VIEW_MAX_BYTES + 1),
        )
        assertTrue(SendFile.canView(1L))
        assertFalse("a size the list did not give is not viewable", SendFile.canView(0L))
        assertFalse(SendFile.canView(-5L))
        assertEquals("Use Save for files over 200 MiB", SendFile.VIEW_USE_SAVE)
    }

    @Test
    fun `the safe two-step save needs 2_1 times the file, to the byte`() {
        // ceil(size x 2.1), in whole numbers: 10 -> 21, 1 -> 3, 20 -> 42.
        assertEquals(21L, SendFile.bytesNeeded(10L))
        assertEquals(3L, SendFile.bytesNeeded(1L))
        assertEquals(42L, SendFile.bytesNeeded(20L))
        assertEquals(0L, SendFile.bytesNeeded(0L))
        assertEquals(0L, SendFile.bytesNeeded(-9L))
        // 2 GiB is exactly 4,509,715,660.8 bytes of room, so the ceiling is
        // 4,509,715,661 - the number the space sentence quotes.
        assertEquals(4_509_715_661L, SendFile.bytesNeeded(SendFile.MAX_BYTES))

        val size = 1_482_331L
        val needed = SendFile.bytesNeeded(size)
        assertTrue("exactly the room needed is allowed", SendFile.hasRoomFor(size, needed))
        assertTrue("a byte over is allowed", SendFile.hasRoomFor(size, needed + 1))
        assertFalse("a byte short is refused", SendFile.hasRoomFor(size, needed - 1))
        // 2.1x, not 2x: twice the file alone would still be a byte short.
        assertTrue(needed > size * 2L)
        assertFalse(SendFile.hasRoomFor(size, size * 2L))
    }

    @Test
    fun `a tight phone gets a plain space sentence, not a broken transfer`() {
        val size = 300_000_000L
        val free = 100_000_000L
        val said = SendFile.spaceWords(size, free)
        assertTrue("it says what is wrong", said.contains("not enough free space"))
        assertTrue("it names the file's size", said.contains(SendFile.sizeWords(size)))
        assertTrue(
            "it names the room the save needs",
            said.contains(SendFile.sizeWords(SendFile.bytesNeeded(size))),
        )
        assertTrue("it names what is free", said.contains(SendFile.sizeWords(free)))
        assertTrue("it says nothing was fetched", said.contains("nothing was fetched"))
        assertTrue("it says what to do next", said.contains("Free some space"))
        assertFalse(said.contains("works once"))
        assertFalse(said.contains("completed download"))
        // A negative reading can only be zero, never a negative amount.
        assertTrue(SendFile.spaceWords(size, -1L).contains(SendFile.sizeWords(0L)))
    }

    @Test
    fun `the receipt carries the id alone, and every failure is ignored`() {
        assertEquals("/api/files/ack", SendFile.ACK_PATH)
        assertEquals("""{"id":"$id"}""", SendFile.ackBody(id))
        // Only the PC's own id shape may go on the wire - never a name or path.
        assertNull(SendFile.ackBody("invoice.pdf"))
        assertNull(SendFile.ackBody("C:\\Users\\me\\invoice.pdf"))
        assertNull(SendFile.ackBody("  "))

        val accepted = SendFile.readAck(200, json("""{"ok": true, "said": "Received."}"""))
        assertEquals("Received.", (accepted as SendFile.Ack.Accepted).said)
        // A failed receipt is never an alarm: 404 (a PC older than the route),
        // 409 (sent before the last piece), 5xx and a body-less answer are all
        // ignored, and the verified file was already kept when it was fired.
        for (status in listOf(400, 401, 403, 404, 409, 500, 503)) {
            val ignored = SendFile.readAck(status, null)
            assertEquals(status, (ignored as SendFile.Ack.Ignored).status)
        }
    }

    @Test
    fun `the cache sweep deletes every received copy except one a viewer holds`() {
        val dir = tmp.newFolder("received")
        val kept = File(dir, "watching.mp4").apply { writeText("v") }
        val orphan = File(dir, "orphan.bin").apply { writeText("o") }
        val part = File(dir, "send-123.part").apply { writeText("p") }
        assertEquals(2, SendFile.sweepReceived(dir, setOf(kept.absolutePath)))
        assertTrue("the file a viewer holds must survive", kept.exists())
        assertFalse(orphan.exists())
        assertFalse("a cancelled download's part goes too", part.exists())
        // Nothing left: a second sweep deletes nothing and does not throw.
        assertEquals(0, SendFile.sweepReceived(dir, setOf(kept.absolutePath)))
        // A folder that does not exist is not a failure.
        assertEquals(0, SendFile.sweepReceived(File(dir, "gone"), emptySet()))
    }

    // ------------------------------------------------------------ the wiring ----

    @Test
    fun `the phone lists and fetches pieces, keeps the PC's status and body, and never asks for a path`() {
        val api = file("jarvis-client/app/src/main/java/com/jarvis/client/net/JarvisApi.kt")
        assertTrue("JarvisApi has no list", api.contains("suspend fun sendFiles("))
        assertTrue("JarvisApi has no slice fetch", api.contains("suspend fun downloadChunk("))
        assertTrue("JarvisApi still reads a whole file", !api.contains("suspend fun downloadFile("))
        // The whole status and body come back, so a 404's own sentence survives.
        assertTrue("the file routes do not keep the body", api.contains("private suspend fun filesCall("))
        assertTrue(api.contains("if (resp.code == 401 || resp.code == 403)"))
        // A 1 MiB slice gets the looser client, not shortCall's 20 s whole call.
        assertTrue("a slice is fetched on the looser client", api.contains("filesCall(path, client)"))
        // The receipt (Q1) goes through the same call, id checked first.
        assertTrue("JarvisApi has no receipt", api.contains("suspend fun ackFile("))
        assertTrue("the receipt does not check the id", api.contains("SendFile.ackBody("))
        assertTrue("the receipt's answer is not read", api.contains("SendFile.readAck("))
        assertTrue(
            "the receipt does not use the send-file call shape",
            api.contains("filesCall(SendFile.ACK_PATH, json = body)"),
        )
        // ...and the same call can now POST as well as GET.
        assertTrue(api.contains(".post(json.toRequestBody(\"application/json\".toMediaType()))"))

        val runtime = file("jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt")
        assertTrue("the runtime has no list", runtime.contains("suspend fun sendFiles("))
        assertTrue("the runtime has no chunked download", runtime.contains("suspend fun downloadFile("))
        assertTrue("the runtime never refuses to ask while hidden",
            runtime.contains("if (privateListsHidden)"))
        // The loop, the retry at the same offset, and the temp file it assembles.
        assertTrue("the runtime does not run the slice loop", runtime.contains("SendFile.receive("))
        assertTrue("the runtime has no stale-link refusal", runtime.contains("actionBlocker()?.let"))
        assertTrue("no app-private temp file", runtime.contains("File.createTempFile("))
        assertTrue("a retried piece must seek", runtime.contains("out.seek(offset)"))
        assertTrue("the whole-file sha is checked", runtime.contains("SendFile.sha256(part)"))
        assertTrue("a failed download must delete its part", runtime.contains("if (!kept) part.delete()"))
        // Q2: the room is measured before the first slice, and a tight phone is
        // refused in the app's own words - never after half a file is written.
        assertTrue("no free-space rule in the runtime", runtime.contains("SendFile.hasRoomFor("))
        assertTrue("no plain space sentence", runtime.contains("SendFile.spaceWords("))
        assertTrue(
            "the free-space check must come before the first slice",
            runtime.indexOf("SendFile.hasRoomFor(") < runtime.indexOf("SendFile.receive("),
        )
        assertTrue("the cache dir is not the volume measured", runtime.contains("cacheDir.usableSpace"))
        // Q1: the receipt is fired once the hash verified, and a failure must
        // not throw the kept file away.
        assertTrue("no receipt after the hash", runtime.contains("api.ackFile(id)"))
        assertTrue(
            "a failed receipt must not throw the file away",
            runtime.contains("runCatching { api.ackFile(id) }"),
        )
        // Q3: cache cleanup, and the file a viewer holds is never swept.
        assertTrue("no viewer record", runtime.contains("fun noteOpenedForViewer("))
        assertTrue("no cache sweep", runtime.contains("fun sweepReceivedCopies("))

        val plate = file("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SendFilePlate.kt")
        assertTrue("View is not a FileProvider hand-off",
            plate.contains("FileProvider.getUriForFile("))
        assertTrue("View is not an ACTION_VIEW", plate.contains("Intent.ACTION_VIEW"))
        assertTrue("Save does not use the Downloads collection",
            plate.contains("MediaStore.Downloads.EXTERNAL_CONTENT_URI"))
        assertTrue("a hidden list draws only the withholding line", plate.contains("SendFile.HIDDEN_NAMES"))
        // CODE, not prose: this screen's comments say "approved" on purpose
        // (the card was the PC's); what must not exist is a decision call.
        val plateCode = plate.lines()
            .filterNot { it.trim().startsWith("//") || it.trim().startsWith("*") }
            .joinToString("\n")
        assertTrue("no file is approved from this phone",
            !plateCode.contains("approve(") && !plateCode.contains("decide("))
        assertTrue("the limits line is stated", plate.contains("SendFile.LIMITS"))
        // The 2 GiB download shows bytes and percent while it runs.
        assertTrue("no progress line", plate.contains("SendFile.progressWords("))
        assertTrue("progress is read off the flow", plate.contains("collectAsState()"))
        assertTrue("the PC's cap is the pre-check", plate.contains("SendFile.fitsCap("))
        assertTrue("an over-cap row says why", plate.contains("SendFile.overCapWords("))
        // The old whole-file fetch is gone from the screen.
        assertTrue("the plate still reads whole files", !plate.contains("readDownload"))
        // Q3: the listed size decides whether View is drawn at all, the row
        // says what to use instead, and the sweep runs when the plate goes.
        assertTrue("View is not gated at 200 MiB", plate.contains("SendFile.canView("))
        assertTrue("above 200 MiB the row does not say to Save",
            plate.contains("SendFile.VIEW_USE_SAVE"))
        assertTrue("the listed size is not given to the space check",
            plate.contains("sizeBytes = file.sizeBytes"))
        assertTrue("no cache sweep when the plate leaves",
            plate.contains("JarvisRuntime.sweepReceivedCopies()"))
        assertTrue("a file handed to the viewer is not recorded",
            plate.contains("JarvisRuntime.noteOpenedForViewer("))
        // A save that landed deletes the cache copy; a failed one does not.
        assertTrue("a saved file must leave the cache", plate.contains("if (saved) runCatching"))
        assertTrue("a failed save must not delete the copy", plate.contains("if (!saved) uri?.let"))

        // The model plate's 2026-11-09 truth: picking an installed model
        // raises no approval card. The 2026-11-18 wording audit removed
        // "switches at once" from that sentence - "at once" reads as instant,
        // while the measured cold load is 12 s to about a minute - so this
        // pins the no-card fact instead of the phrase that was corrected.
        val brain = file("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/BrainScreen.kt")
        assertFalse("the stale model-switch card promise is back",
            brain.contains("raises a card on Home"))
        assertTrue("the plate does not say a model pick needs no approval card",
            brain.contains("switches with no approval card"))
        assertTrue("the previous model is not offered one line above",
            brain.contains("Roll back to…"))

        // The manifest shares only the private cache, by its own authority.
        val manifest = file("jarvis-client/app/src/main/AndroidManifest.xml")
        assertTrue("no send-file FileProvider", manifest.contains("\${applicationId}.sendfile"))
        assertTrue("no send-file paths", manifest.contains("@xml/send_file_paths"))
        val paths = file("jarvis-client/app/src/main/res/xml/send_file_paths.xml")
        assertTrue(paths.contains("<cache-path name=\"received\" path=\"received/\" />"))

        // Where it lives: a Settings row, its jump entry, its search row, and
        // the Coming up block that makes a waiting file noticed.
        val settings = file("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SettingsScreen.kt")
        assertTrue(settings.contains("item(key = \"files\")"))
        assertTrue(settings.contains("SendFileSection(canAct = canAct, privateHidden = privateHidden)"))
        assertTrue(file("jarvis-client/app/src/main/java/com/jarvis/client/ui/SettingsJump.kt")
            .contains("Entry(\"File from your PC\", \"files\")"))
        assertTrue(file("jarvis-client/app/src/main/java/com/jarvis/client/ui/SettingsSearch.kt")
            .contains("key = \"files\", title = \"File from your PC\""))
        assertTrue(file("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/ComingUpPlate.kt")
            .contains("SendFileWaitingBlock(canAct = canAct, privateHidden = privateHidden)"))
        // ...and the hidden rule really is wired to the screen that lists names.
        assertTrue(file("jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt")
            .contains("privateHidden = privateHidden"))
    }

    /** A repository file, from Gradle's working folder (`jarvis-client/app`). */
    private fun file(rel: String): String {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f.readText()
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }
}
