package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Upload
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.InputStream
import java.util.Base64

/**
 * The phone half of "send a document from the phone" (the owner's ask of
 * 2026-11-05; DESIGN.md C0; docs/ARCHITECTURE.md section 8).
 *
 * `net/Upload.kt` is pure on purpose: this suite runs the whole transfer on a
 * plain JVM - the three wire bodies, the 1 MiB boundaries, the SHA-256 and
 * size fields, every refusal the PC can answer, the retry while its ONE card
 * waits, and the 404 that must send NOTHING. No Android, no socket, no
 * Robolectric.
 */
class UploadTest {

    private fun json(text: String): JsonObject =
        JarvisJson.parseToJsonElement(text) as JsonObject

    private fun meta(
        name: String = "taxes.pdf",
        size: Long = 10,
        purpose: Upload.Purpose = Upload.Purpose.DOCUMENT,
    ) = Upload.Meta(
        name = name,
        mime = if (purpose == Upload.Purpose.NOTION) "application/zip" else "application/pdf",
        size = size,
        sha256 = "ab".repeat(32),
        purpose = purpose,
    )

    private fun bytes(n: Int): ByteArray = ByteArray(n) { (it % 251).toByte() }

    // ------------------------------------------------------- the wire paths ---

    @Test
    fun `the three routes are the PC's own`() {
        assertEquals("/api/upload/begin", Upload.BEGIN_PATH)
        assertEquals("/api/upload/chunk", Upload.CHUNK_PATH)
        assertEquals("/api/upload/finish", Upload.FINISH_PATH)
        assertEquals(1_048_576, Upload.CHUNK_BYTES)
        assertEquals(50L * 1024 * 1024, Upload.DOCUMENT_MAX)
        assertEquals(4L * 1024 * 1024 * 1024, Upload.NOTION_MAX)
        assertEquals("document", Upload.Purpose.DOCUMENT.wire)
        assertEquals("notion", Upload.Purpose.NOTION.wire)
    }

    // ---------------------------------------------------------- chunk maths ---

    @Test
    fun `chunk boundaries are exact at every edge`() {
        assertEquals(0, Upload.chunks(0))
        assertEquals(1, Upload.chunks(1))
        assertEquals(1, Upload.chunks(Upload.CHUNK_BYTES.toLong()))
        assertEquals(2, Upload.chunks(Upload.CHUNK_BYTES + 1L))
        assertEquals(50, Upload.chunks(Upload.DOCUMENT_MAX))
        assertEquals(1, Upload.chunkLength(1, 0))
        assertEquals(Upload.CHUNK_BYTES, Upload.chunkLength(Upload.CHUNK_BYTES.toLong(), 0))
        // The last chunk of a file that is not a whole number of chunks.
        val size = 2L * Upload.CHUNK_BYTES + 17
        assertEquals(3, Upload.chunks(size))
        assertEquals(17, Upload.chunkLength(size, 2))
        // Past the end is nothing, never a negative slice.
        assertEquals(0, Upload.chunkLength(size, 3))
        assertEquals(0, Upload.chunkLength(size, -1))
    }

    @Test
    fun `a smaller chunk size from the PC is honoured`() {
        // `begin` answers `chunk_bytes`; a PC asking for 512 KiB must get 512 KiB
        // slices, or its own limit would refuse every 1 MiB one with a 413.
        val half = Upload.CHUNK_BYTES / 2
        assertEquals(4, Upload.chunks(2L * Upload.CHUNK_BYTES, half))
        assertEquals(half, Upload.chunkLength(2L * Upload.CHUNK_BYTES, 0, half))
    }

    // --------------------------------------------------------- wire bodies ---

    @Test
    fun `begin names the file, its size, its sha, its purpose and the folder`() {
        val body = Upload.beginBody(meta(size = 412_345), "C:\\Users\\owner\\Documents")
        val o = json(body)
        assertEquals("taxes.pdf", o["name"]!!.jsonPrimitive.content)
        assertEquals(412_345L, o["size"]!!.jsonPrimitive.content.toLong())
        assertEquals("application/pdf", o["mime"]!!.jsonPrimitive.content)
        assertEquals("ab".repeat(32), o["sha256"]!!.jsonPrimitive.content)
        assertEquals("document", o["purpose"]!!.jsonPrimitive.content)
        assertEquals("C:\\Users\\owner\\Documents", o["into"]!!.jsonPrimitive.content)
        assertEquals(setOf("name", "size", "mime", "sha256", "purpose", "into"), o.keys)
    }

    @Test
    fun `a Notion upload names no folder - its destination is a vault`() {
        val o = json(Upload.beginBody(meta(name = "Export.zip", purpose = Upload.Purpose.NOTION), null))
        assertEquals("notion", o["purpose"]!!.jsonPrimitive.content)
        assertFalse("a Notion export must not name a listed folder", o.containsKey("into"))
        assertEquals(setOf("name", "size", "mime", "sha256", "purpose"), o.keys)
    }

    @Test
    fun `one chunk carries the id, the index and exactly those bytes as base64`() {
        val data = bytes(Upload.CHUNK_BYTES - 3)
        val o = json(Upload.chunkBody("0a1b", 2, data))
        assertEquals("0a1b", o["id"]!!.jsonPrimitive.content)
        assertEquals(2L, o["index"]!!.jsonPrimitive.content.toLong())
        assertEquals(setOf("id", "index", "data"), o.keys)
        assertArrayEqualsBytes(data, Base64.getDecoder().decode(o["data"]!!.jsonPrimitive.content))
    }

    @Test
    fun `finish carries the id alone`() {
        val o = json(Upload.finishBody("0a1b"))
        assertEquals("0a1b", o["id"]!!.jsonPrimitive.content)
        assertEquals(setOf("id"), o.keys)
    }

    // ------------------------------------------------------------- measure ---

    @Test
    fun `measure gives the real size and SHA-256 of the bytes`() {
        val m = Upload.measure(ByteArrayInputStream("abc".toByteArray()), 100) as Upload.Measured.Ok
        assertEquals(3L, m.size)
        assertEquals(
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            m.sha256,
        )
        val hello = Upload.measure(ByteArrayInputStream("hello world".toByteArray()), 100)
            as Upload.Measured.Ok
        assertEquals(
            "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
            hello.sha256,
        )
    }

    @Test
    fun `an empty file is refused before it is sent`() {
        assertTrue(Upload.measure(ByteArrayInputStream(ByteArray(0)), 10) is Upload.Measured.Empty)
    }

    @Test
    fun `a file over the cap is refused without being read in full`() {
        val m = Upload.measure(ByteArrayInputStream(bytes(64 * 1024)), 10)
        assertTrue(m is Upload.Measured.TooBig)
        assertEquals(10L, (m as Upload.Measured.TooBig).limit)
    }

    @Test
    fun `a stream that cannot be read is said, not thrown`() {
        val broken = object : InputStream() {
            override fun read(): Int = throw IllegalStateException("gone")
        }
        assertTrue(Upload.measure(broken, 10) is Upload.Measured.Unreadable)
    }

    // -------------------------------------------------------- the refusals ---

    @Test
    fun `the pick is refused before a byte is read`() {
        assertNull(Upload.refusal("taxes.pdf", "application/pdf", 10, Upload.Purpose.DOCUMENT))
        assertNull(Upload.refusal("Export.zip", "application/octet-stream", 10, Upload.Purpose.NOTION))
        val wrong = Upload.refusal("notes.zip", "application/zip", 10, Upload.Purpose.DOCUMENT)
        assertNotNull(wrong)
        assertTrue(wrong!!.contains("PDF"))
        val notZip = Upload.refusal("Export.txt", "text/plain", 10, Upload.Purpose.NOTION)
        assertNotNull(notZip)
        assertTrue(notZip!!.contains(".zip"))
        val big = Upload.refusal("taxes.pdf", "application/pdf", Upload.DOCUMENT_MAX + 1,
            Upload.Purpose.DOCUMENT)
        assertNotNull(big)
        assertTrue(big!!.contains("50 MB"))
        val bigZip = Upload.refusal("Export.zip", "application/zip", Upload.NOTION_MAX + 1,
            Upload.Purpose.NOTION)
        assertNotNull(bigZip)
        assertTrue(bigZip!!.contains("4 GB"))
    }

    // ------------------------------------------------------- answer mapping ---

    @Test
    fun `begin reads a waiting card, a missing route and every refusal`() {
        val waiting = Upload.readBegin(
            Upload.Reply(
                202,
                json("""{"ok":true,"id":"abc","waiting":true,"chunk_bytes":524288,"max_bytes":52428800,"said":"Waiting for your yes on the approval card."}"""),
            ),
        ) as Upload.Begin.Ok
        assertEquals("abc", waiting.id)
        assertTrue(waiting.waiting)
        assertEquals(524_288, waiting.chunkBytes)
        assertEquals(52_428_800L, waiting.maxBytes)

        // A Notion begin raises no card: 202 with waiting false is NOT a wait.
        val notion = Upload.readBegin(
            Upload.Reply(202, json("""{"ok":true,"id":"abc","waiting":false}""")),
        ) as Upload.Begin.Ok
        assertFalse(notion.waiting)

        assertTrue(Upload.readBegin(Upload.Reply(404, null)) is Upload.Begin.NotHere)
        assertTrue(Upload.readBegin(Upload.Reply(503, json("""{"ok":false,"error":"not running"}"""))) is Upload.Begin.NotHere)

        val refused = Upload.readBegin(
            Upload.Reply(400, json("""{"ok":false,"reason":"It can only go into a folder on the list - add the folder first."}""")),
        ) as Upload.Begin.Refused
        assertEquals("It can only go into a folder on the list - add the folder first.", refused.why)

        val denied = Upload.readBegin(Upload.Reply(403, json("""{"ok":false,"denied":true,"said":"You said no."}""")))
            as Upload.Begin.Refused
        assertEquals("You said no.", denied.why)

        val tooBig = Upload.readBegin(
            Upload.Reply(413, json("""{"ok":false,"said":"That file is bigger than this PC takes."}""")),
        ) as Upload.Begin.Refused
        assertEquals("That file is bigger than this PC takes.", tooBig.why)
    }

    @Test
    fun `chunk maps the card, the no, the expiry and the caps`() {
        val sent = Upload.readChunk(Upload.Reply(200, json("""{"ok":true,"received":1048576}""")))
            as Upload.Chunk.Sent
        assertEquals(1_048_576L, sent.received)
        val waiting = Upload.readChunk(Upload.Reply(409, json("""{"ok":false,"waiting":true,"said":"Waiting for your yes on the approval card."}""")))
            as Upload.Chunk.Waiting
        assertEquals("Waiting for your yes on the approval card.", waiting.said)
        val denied = Upload.readChunk(Upload.Reply(403, json("""{"ok":false,"denied":true,"said":"You said no."}""")))
            as Upload.Chunk.Denied
        assertEquals("You said no.", denied.said)
        // A 403 with no `denied` is not the owner's no - it is a refusal like any other.
        assertTrue(Upload.readChunk(Upload.Reply(403, json("""{"ok":false,"reason":"refused"}"""))) is Upload.Chunk.Refused)
        val expired = Upload.readChunk(Upload.Reply(410, json("""{"ok":false,"expired":true,"said":"That upload expired."}""")))
            as Upload.Chunk.Expired
        assertEquals("That upload expired.", expired.said)
        val capped = Upload.readChunk(Upload.Reply(413, json("""{"ok":false,"said":"That chunk is too big."}""")))
            as Upload.Chunk.Refused
        assertEquals("That chunk is too big.", capped.why)
        // 409 without a waiting flag is an out-of-order slice: a refusal, never a pause.
        assertTrue(
            Upload.readChunk(Upload.Reply(409, json("""{"ok":false,"waiting":false,"reason":"Chunks must arrive in order."}""")))
                is Upload.Chunk.Refused,
        )
        val gone = Upload.readChunk(Upload.Reply(404, null)) as Upload.Chunk.Expired
        assertEquals(Upload.EXPIRED, gone.said)
    }

    @Test
    fun `finish reads a saved file, a staged export, a waiting card and a refusal`() {
        val saved = Upload.readFinish(
            Upload.Reply(200, json("""{"ok":true,"saved":true,"name":"taxes.pdf","folder":"Documents","said":"Saved in \"Documents\". Ask Jarvis about it whenever you like."}""")),
        ) as Upload.Finish.Saved
        assertEquals("taxes.pdf", saved.name)
        assertEquals("Documents", saved.folder)
        assertTrue(saved.said.startsWith("Saved in"))

        val staged = Upload.readFinish(
            Upload.Reply(200, json("""{"ok":true,"plan":{"digest":"abc"},"said":"Here is the plan."}""")),
        ) as Upload.Finish.Staged
        assertEquals("Here is the plan.", staged.said)

        assertTrue(
            Upload.readFinish(Upload.Reply(409, json("""{"ok":false,"waiting":true,"said":"Waiting."}""")))
                is Upload.Finish.Waiting,
        )
        val refused = Upload.readFinish(Upload.Reply(400, json("""{"ok":false,"reason":"The file changed."}""")))
            as Upload.Finish.Refused
        assertEquals("The file changed.", refused.why)
        assertTrue(Upload.readFinish(Upload.Reply(404, null)) is Upload.Finish.NotHere)
    }

    // ------------------------------------------------------------ the send ---

    @Test
    fun `a 404 at begin sends NOTHING - no file is opened, no chunk posted`() = runBlocking {
        var opened = 0
        var chunks = 0
        var finished = 0
        val outcome = Upload.send(
            meta = meta(),
            into = "C:\\Docs",
            open = { opened += 1; ByteArrayInputStream(bytes(10)) },
            begin = { Upload.Reply(404, null) },
            chunk = { chunks += 1; Upload.Reply(500, null) },
            finish = { finished += 1; Upload.Reply(500, null) },
        )
        assertEquals(Upload.Outcome.NotHere, outcome)
        assertEquals("nothing may be opened when the PC has no upload route", 0, opened)
        assertEquals("no chunk may be posted when begin said 404", 0, chunks)
        assertEquals(0, finished)
        assertEquals(Upload.NOT_HERE, Upload.outcomeText(outcome))
    }

    @Test
    fun `a refusal at begin also sends nothing`() = runBlocking {
        var opened = 0
        val outcome = Upload.send(
            meta = meta(),
            into = "C:\\Docs",
            open = { opened += 1; ByteArrayInputStream(bytes(10)) },
            begin = { Upload.Reply(400, json("""{"ok":false,"reason":"It can only go into a folder on the list - add the folder first."}""")) },
            chunk = { Upload.Reply(500, null) },
            finish = { Upload.Reply(500, null) },
        )
        assertTrue(outcome is Upload.Outcome.Refused)
        assertEquals("It can only go into a folder on the list - add the folder first.",
            (outcome as Upload.Outcome.Refused).why)
        assertEquals(0, opened)
    }

    @Test
    fun `every byte arrives in order and finish is the only claim of a saved file`() = runBlocking {
        val file = bytes(2 * Upload.CHUNK_BYTES + 5)
        val got = java.io.ByteArrayOutputStream()
        val indexes = mutableListOf<Int>()
        val progress = mutableListOf<Pair<Int, Int>>()
        var begun = false
        val outcome = Upload.send(
            meta = meta(size = file.size.toLong()),
            into = "C:\\Docs",
            open = { begun = true; ByteArrayInputStream(file) },
            begin = { Upload.Reply(202, json("""{"ok":true,"id":"u1","waiting":true}""")) },
            chunk = { body ->
                val o = json(body)
                indexes += o["index"]!!.jsonPrimitive.content.toInt()
                got.write(Base64.getDecoder().decode(o["data"]!!.jsonPrimitive.content))
                Upload.Reply(200, json("""{"ok":true,"received":1}"""))
            },
            finish = { body ->
                assertEquals(setOf("id"), json(body).keys)
                Upload.Reply(200, json("""{"ok":true,"saved":true,"name":"taxes.pdf","folder":"Documents","said":"Saved in \"Documents\". Ask Jarvis about it whenever you like."}"""))
            },
            onProgress = { sent, total -> progress += sent to total },
            onWaiting = {},
        )
        assertTrue(begun)
        assertEquals(listOf(0, 1, 2), indexes)
        assertArrayEqualsBytes(file, got.toByteArray())
        assertTrue(progress.contains(0 to 3))
        assertTrue(progress.contains(3 to 3))
        val saved = outcome as Upload.Outcome.Saved
        assertEquals("Documents", saved.folder)
        assertEquals("taxes.pdf", saved.name)
        assertEquals(
            "Saved in \"Documents\". Ask Jarvis about it whenever you like.",
            Upload.outcomeText(outcome),
        )
    }

    @Test
    fun `while the card waits the same chunk is posted again - never the next one`() = runBlocking {
        val file = bytes(Upload.CHUNK_BYTES + 1)
        var postings = 0
        var pauses = 0
        val indexes = mutableListOf<Int>()
        val outcome = Upload.send(
            meta = meta(size = file.size.toLong()),
            into = "C:\\Docs",
            open = { ByteArrayInputStream(file) },
            begin = { Upload.Reply(202, json("""{"ok":true,"id":"u1","waiting":true}""")) },
            chunk = { body ->
                postings += 1
                indexes += json(body)["index"]!!.jsonPrimitive.content.toInt()
                if (postings <= 2) {
                    Upload.Reply(409, json("""{"ok":false,"waiting":true,"said":"Waiting for your yes on the approval card."}"""))
                } else {
                    Upload.Reply(200, json("""{"ok":true,"received":1}"""))
                }
            },
            finish = { Upload.Reply(200, json("""{"ok":true,"saved":true,"name":"taxes.pdf","folder":"Documents"}""")) },
            waits = 5,
            pause = { pauses += 1 },
        )
        assertTrue("the transfer must finish once the card is answered", outcome is Upload.Outcome.Saved)
        assertEquals(listOf(0, 0, 0, 1), indexes)
        assertEquals(2, pauses)
    }

    @Test
    fun `a waiting budget that runs out says so instead of hanging or claiming success`() = runBlocking {
        var pauses = 0
        val outcome = Upload.send(
            meta = meta(size = 10),
            into = "C:\\Docs",
            open = { ByteArrayInputStream(bytes(10)) },
            begin = { Upload.Reply(202, json("""{"ok":true,"id":"u1","waiting":true}""")) },
            chunk = { Upload.Reply(409, json("""{"ok":false,"waiting":true,"said":"Waiting for your yes on the approval card."}""")) },
            finish = { Upload.Reply(200, json("""{"ok":true,"saved":true}""")) },
            waits = 1,
            pause = { pauses += 1 },
        )
        assertTrue(outcome is Upload.Outcome.Waiting)
        assertEquals(1, pauses)
        assertEquals(Upload.SENT_WAITING, Upload.outcomeText(outcome))
    }

    @Test
    fun `a denied card stops at once and nothing is finished`() = runBlocking {
        var finished = 0
        val outcome = Upload.send(
            meta = meta(size = 10),
            into = "C:\\Docs",
            open = { ByteArrayInputStream(bytes(10)) },
            begin = { Upload.Reply(202, json("""{"ok":true,"id":"u1","waiting":false}""")) },
            chunk = { Upload.Reply(403, json("""{"ok":false,"denied":true,"said":"You said no."}""")) },
            finish = { finished += 1; Upload.Reply(200, json("""{"ok":true}""")) },
        )
        assertEquals("You said no.", (outcome as Upload.Outcome.Refused).why)
        assertEquals(0, finished)
    }

    @Test
    fun `an expired upload is said in the PC's words`() = runBlocking {
        val outcome = Upload.send(
            meta = meta(size = 10),
            into = "C:\\Docs",
            open = { ByteArrayInputStream(bytes(10)) },
            begin = { Upload.Reply(200, json("""{"ok":true,"id":"u1"}""")) },
            chunk = { Upload.Reply(410, json("""{"ok":false,"expired":true,"said":"That upload expired - pick it again."}""")) },
            finish = { Upload.Reply(200, json("""{"ok":true}""")) },
        )
        assertEquals("That upload expired - pick it again.", (outcome as Upload.Outcome.Refused).why)
    }

    @Test
    fun `a file that changed after it was measured is refused, not half-sent`() = runBlocking {
        // Measured as 1 MiB + 10, but the stream now ends after 1 MiB.
        val short = Upload.send(
            meta = meta(size = Upload.CHUNK_BYTES + 10L),
            into = "C:\\Docs",
            open = { ByteArrayInputStream(bytes(Upload.CHUNK_BYTES)) },
            begin = { Upload.Reply(200, json("""{"ok":true,"id":"u1"}""")) },
            chunk = { Upload.Reply(200, json("""{"ok":true,"received":1}""")) },
            finish = { Upload.Reply(200, json("""{"ok":true,"saved":true}""")) },
        )
        assertEquals(Upload.CHANGED, (short as Upload.Outcome.Refused).why)
        // ...and one that grew by a byte is the same refusal.
        val long = Upload.send(
            meta = meta(size = 10),
            into = "C:\\Docs",
            open = { ByteArrayInputStream(bytes(11)) },
            begin = { Upload.Reply(200, json("""{"ok":true,"id":"u1"}""")) },
            chunk = { Upload.Reply(200, json("""{"ok":true,"received":1}""")) },
            finish = { Upload.Reply(200, json("""{"ok":true,"saved":true}""")) },
        )
        assertEquals(Upload.CHANGED, (long as Upload.Outcome.Refused).why)
    }

    @Test
    fun `a Notion export finish answers the plan and hands back its id`() = runBlocking {
        val outcome = Upload.send(
            meta = meta(name = "Export.zip", size = 10, purpose = Upload.Purpose.NOTION),
            into = null,
            open = { ByteArrayInputStream(bytes(10)) },
            begin = { body ->
                val o = json(body)
                assertFalse("a Notion begin must not name a folder", o.containsKey("into"))
                Upload.Reply(200, json("""{"ok":true,"id":"u9","waiting":false}"""))
            },
            chunk = { Upload.Reply(200, json("""{"ok":true,"received":10}""")) },
            finish = { Upload.Reply(200, json("""{"ok":true,"plan":{"digest":"abc"},"said":"Here is the plan."}""")) },
        )
        val uploaded = outcome as Upload.Outcome.Uploaded
        assertEquals("u9", uploaded.id)
        assertEquals("Here is the plan.", uploaded.said)
    }

    @Test
    fun `an unreadable pick is refused before anything is posted`() = runBlocking {
        var chunks = 0
        val outcome = Upload.send(
            meta = meta(size = 10),
            into = "C:\\Docs",
            open = { null },
            begin = { Upload.Reply(200, json("""{"ok":true,"id":"u1"}""")) },
            chunk = { chunks += 1; Upload.Reply(200, json("""{"ok":true}""")) },
            finish = { Upload.Reply(200, json("""{"ok":true}""")) },
        )
        assertEquals(Upload.UNREADABLE, (outcome as Upload.Outcome.Refused).why)
        assertEquals(0, chunks)
    }

    // ------------------------------------------------------------- the words ---

    @Test
    fun `the outcome is one plain sentence, and the PC's own words win`() {
        assertEquals(
            "Saved in \"Documents\". Ask Jarvis about it whenever you like.",
            Upload.savedText("taxes.pdf", "Documents", "Saved in \"Documents\". Ask Jarvis about it whenever you like."),
        )
        assertEquals(
            "Saved in \"Documents\". Ask Jarvis about it whenever you like.",
            Upload.savedText("taxes.pdf", "Documents", ""),
        )
        assertEquals(Upload.SENT_WAITING, Upload.outcomeText(Upload.Outcome.Waiting("")))
        assertEquals(Upload.NOT_HERE, Upload.outcomeText(Upload.Outcome.NotHere))
        assertEquals(
            "Saved in your PC. Ask Jarvis about it whenever you like.",
            Upload.savedText("taxes.pdf", "", ""),
        )
        assertTrue(Upload.STOPPED.isNotEmpty())
        assertTrue(Upload.EMPTY.isNotEmpty())
    }

    @Test
    fun `progress is real chunks, never a timer`() {
        assertEquals("Sending taxes.pdf - 2 of 4", Upload.progress("taxes.pdf", 2, 4))
        assertEquals("Getting taxes.pdf ready…", Upload.preparing("taxes.pdf"))
        assertTrue(Upload.waitingLine("taxes.pdf").contains("taxes.pdf"))
        assertFalse(Upload.waitingLine("taxes.pdf").contains("2 of 4"))
        assertTrue(Upload.DETAIL.contains("From my phone"))
        assertTrue(Upload.NOT_HERE.contains("not available on this PC"))
        assertTrue(Upload.NO_FOLDERS.contains("Settings, Folders Jarvis may look in"))
    }

    @Test
    fun `a PC without the upload routes is missing in the same way folders are`() {
        assertTrue(Upload.missing(com.jarvis.client.net.ApiError.NotFound))
        assertTrue(Upload.missing(com.jarvis.client.net.ApiError.NotAvailable))
        assertFalse(Upload.missing(com.jarvis.client.net.ApiError.BadToken))
    }

    private fun assertArrayEqualsBytes(want: ByteArray, got: ByteArray) {
        assertEquals("byte count", want.size, got.size)
        for (i in want.indices) assertEquals("byte $i", want[i], got[i])
    }
}
