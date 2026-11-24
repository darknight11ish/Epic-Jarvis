package com.jarvis.client

import com.jarvis.client.net.Upload
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayInputStream

/**
 * Several files sent from the phone at once (2026-11-23, the owner's "I should
 * be able to send as many files of different kinds as I want to my PC").
 *
 * The batch is [Upload.sendMany]'s, and it is pure: this suite runs the whole
 * order on a plain JVM - one whole transfer after another, a refusal that does
 * not stop the rest, the card that does, and the sentence the screen ends on.
 * The picker itself is pinned by the source check at the bottom: the folder
 * door asks Android for SEVERAL documents, and the runtime still hands each
 * one to its own `begin`/`chunk`/`finish`.
 */
class SendManyTest {

    private fun queued(name: String, mime: String? = "application/pdf"): Upload.Queued =
        Upload.Queued(name, mime) { ByteArrayInputStream(ByteArray(4)) }

    private fun saved(name: String) = Upload.Outcome.Saved(name, "From my phone", "")

    @Test
    fun `files go one at a time, in the order the owner picked them`() = runBlocking {
        val order = mutableListOf<String>()
        var inFlight = 0
        var mostAtOnce = 0
        val batch = Upload.sendMany(
            files = listOf(queued("first.pdf"), queued("second.png"), queued("third.zip")),
            upload = { f ->
                order += f.name
                inFlight += 1
                mostAtOnce = maxOf(mostAtOnce, inFlight)
                inFlight -= 1
                saved(f.name)
            },
        )
        assertEquals(listOf("first.pdf", "second.png", "third.zip"), order)
        assertEquals("two transfers must never overlap", 1, mostAtOnce)
        assertEquals(3, batch.total)
        assertEquals(3, batch.saved)
        assertNull(batch.stopped)
        assertEquals("Sent 3 files to your PC.", Upload.batchSaid(batch))
    }

    @Test
    fun `the screen is told which file it is on before that file starts`() = runBlocking {
        val announced = mutableListOf<String>()
        Upload.sendMany(
            files = listOf(queued("a.pdf"), queued("b.pdf")),
            upload = { f -> saved(f.name) },
            onEach = { i, f -> announced += "${i + 1}:${f.name}" },
        )
        assertEquals(listOf("1:a.pdf", "2:b.pdf"), announced)
    }

    @Test
    fun `one file the PC refused does not stop the rest`() = runBlocking {
        val batch = Upload.sendMany(
            files = listOf(queued("no.pdf"), queued("yes.pdf"), queued("also.pdf")),
            upload = { f ->
                if (f.name == "no.pdf") Upload.Outcome.Refused(Upload.DENIED) else saved(f.name)
            },
        )
        assertEquals(3, batch.total)
        assertEquals(2, batch.saved)
        assertNull("a refusal is that file's own, so the batch goes on", batch.stopped)
        assertEquals(
            "Sent 2 of 3 files to your PC. ${Upload.DENIED} The rest stay on your phone.",
            Upload.batchSaid(batch),
        )
    }

    @Test
    fun `a card nobody answered stops the batch, and the rest are named`() = runBlocking {
        val tried = mutableListOf<String>()
        val batch = Upload.sendMany(
            files = listOf(queued("a.pdf"), queued("b.pdf"), queued("c.pdf")),
            upload = { f ->
                tried += f.name
                if (f.name == "a.pdf") Upload.Outcome.Waiting("Waiting for your yes on the PC.")
                else saved(f.name)
            },
        )
        assertEquals("the next file must not raise a second card", listOf("a.pdf"), tried)
        assertEquals(3, batch.total)
        assertEquals(0, batch.saved)
        assertEquals("Waiting for your yes on the PC.", batch.stopped)
        assertEquals(
            "Nothing is saved yet. Waiting for your yes on the PC. The rest stay on your phone.",
            Upload.batchSaid(batch),
        )
    }

    @Test
    fun `a PC without the upload routes stops the batch at the first file`() = runBlocking {
        var calls = 0
        val batch = Upload.sendMany(
            files = listOf(queued("a.pdf"), queued("b.pdf")),
            upload = {
                calls += 1
                Upload.Outcome.NotHere
            },
        )
        assertEquals(1, calls)
        assertEquals(
            "Nothing was sent. ${Upload.NOT_HERE}",
            Upload.batchSaid(batch),
        )
    }

    @Test
    fun `one file keeps the single-file sentence it always had`() = runBlocking {
        val batch = Upload.sendMany(listOf(queued("taxes.pdf")), upload = { saved(it.name) })
        assertEquals(1, batch.total)
        assertEquals(Upload.outcomeText(saved("taxes.pdf")), Upload.batchSaid(batch))
        assertFalse(Upload.batchSaid(batch).contains("1 files"))
    }

    @Test
    fun `picks refused before a byte was read are counted, and the first reason is said`() = runBlocking {
        val tooBig = Upload.tooBig(9L * 1024 * 1024 * 1024, Upload.Purpose.DOCUMENT)
        val batch = Upload.sendMany(
            files = listOf(queued("a.pdf"), queued("b.pdf")),
            upload = { f -> saved(f.name) },
        )
        assertEquals(
            "Sent 2 of 3 files to your PC. $tooBig The rest stay on your phone.",
            Upload.batchSaid(batch, skipped = 1, firstSkip = tooBig),
        )
        // Every pick refused before a byte was read: nothing was sent, and the
        // reason is the same cap sentence a single pick gives.
        assertEquals(
            "Nothing was sent. $tooBig",
            Upload.batchSaid(Upload.Batch(emptyList(), 0, null, 0), skipped = 2, firstSkip = tooBig),
        )
    }

    @Test
    fun `the progress label names the place in the batch`() {
        assertEquals("taxes.pdf (file 2 of 5)", Upload.batchName(2, 5, "taxes.pdf"))
        assertEquals("taxes.pdf", Upload.batchName(1, 1, "taxes.pdf"))
        assertEquals("taxes.pdf", Upload.batchName(0, 0, "taxes.pdf"))
    }

    @Test
    fun `the folder door asks for several documents, and the runtime sends each one whole`() {
        val activity = SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt")
        assertTrue(
            "the folder door must let the owner pick many files at once",
            activity.contains("ActivityResultContracts.OpenMultipleDocuments()"),
        )
        assertTrue(activity.contains("JarvisRuntime.startSendDocuments("))
        // The batch is a queue of whole transfers, not a second wire shape.
        assertTrue(activity.contains("Upload.Queued("))
        // The chat row is untouched: one file rides with one question.
        assertTrue(activity.contains("AttachFile.mimeTypes("))
        assertFalse(activity.contains("PickVisualMedia"))
        val runtime = SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt")
        assertTrue(runtime.contains("Upload.sendMany("))
        assertTrue(runtime.contains("private suspend fun uploadOne("))
    }
}
