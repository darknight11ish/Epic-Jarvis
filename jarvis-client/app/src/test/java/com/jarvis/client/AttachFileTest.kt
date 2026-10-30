package com.jarvis.client

import com.jarvis.client.net.AttachFile
import com.jarvis.client.net.ChatHistory
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Base64

/**
 * A document in chat - `net/AttachFile.kt`, and the one request it makes.
 *
 * THE WIRE SHAPE IS THE CONTRACT (REPORT.md section 8, and the brief the
 * desktop/backend half is built from):
 *
 *     newest user message: {"role","content","provenance","attachment":{
 *         "name": "taxes.pdf", "mime": "application/pdf",
 *         "size": 12345, "data": "<base64 of the raw bytes>"}}
 *     request top level  : {"messages", "has_image", "has_file": true, ...}
 *
 * The `attachment` is a SIBLING of `content`, not a part inside it: the PC
 * replaces it with a `text` part after it has read the file. `data` is raw
 * base64 with NO `data:` prefix (unlike a picture's `data:image/jpeg;...`).
 * `has_file` is sent only when a file rides, exactly like `temporary` and
 * `cloud_yes` - an ordinary question is byte for byte the request it was.
 *
 * What cannot be tested here: the system file picker, `ContentResolver`, and
 * `OpenableColumns` - all Android, all in `MainActivity`. This file drives the
 * pure half with bytes a JVM can make, and pins the decisions (cap, kind, name,
 * refusal words) that half owns.
 */
class AttachFileTest {

    private fun ready(name: String = "taxes.pdf", bytes: String = "%PDF-1.4 hello"): AttachFile.Ready {
        val out = AttachFile.picked(bytes.toByteArray(), name)
        assertTrue("$name was refused: $out", out is AttachFile.Picked.Ok)
        return (out as AttachFile.Picked.Ok).file
    }

    private fun refusal(bytes: ByteArray, name: String?, mime: String? = null): String {
        val out = AttachFile.picked(bytes, name, mime)
        assertTrue("expected a refusal, got $out", out is AttachFile.Picked.Refused)
        return (out as AttachFile.Picked.Refused).why
    }

    // --------------------------------------------------------------- caps ---

    @Test
    fun `the cap is 2,500,000 raw bytes and exactly that many is allowed`() {
        assertEquals(2_500_000, AttachFile.MAX_BYTES)
        val atCap = AttachFile.picked(ByteArray(AttachFile.MAX_BYTES), "taxes.pdf")
        assertTrue("$atCap", atCap is AttachFile.Picked.Ok)
        assertEquals(AttachFile.MAX_BYTES, (atCap as AttachFile.Picked.Ok).file.size)
        // One byte over is refused - the "read one byte over" pattern.
        val over = AttachFile.picked(ByteArray(AttachFile.MAX_BYTES + 1), "taxes.pdf")
        assertTrue("$over", over is AttachFile.Picked.Refused)
    }

    @Test
    fun `the refusal names the cap and the folder alternative`() {
        val why = refusal(ByteArray(AttachFile.MAX_BYTES + 1), "taxes.pdf")
        assertTrue(why, why.contains("2.5 MB"))
        assertTrue(why, why.contains("folder Jarvis may look in"))
    }

    @Test
    fun `a stated size says the real number, and the unknown case says 'bigger than'`() {
        assertTrue(AttachFile.tooBig(4_200_000).startsWith("That file is 4.2 MB."))
        assertTrue(AttachFile.tooBig(4_200_000).contains("Files up to 2.5 MB can be attached."))
        assertTrue(AttachFile.tooBig(4_200_000).contains("folder Jarvis may look in"))
        assertTrue(AttachFile.overCap().startsWith("That file is bigger than 2.5 MB."))
        assertTrue(AttachFile.overCap().contains("folder Jarvis may look in"))
    }

    @Test
    fun `the whole request with the biggest allowed file still fits the PC's body cap`() {
        assertEquals(4 * 1024 * 1024, AttachFile.BACKEND_MAX_BODY)
        // The real arithmetic: base64 grows the bytes by a third, then the most
        // conversation this app sends rides beside them, plus the JSON around.
        val biggest = "A".repeat(AttachFile.MAX_BYTES)
        val encoded = AttachFile.base64(biggest.toByteArray()).length
        // base64 length is 4 characters per 3 bytes, rounded up.
        assertEquals(4 * ((AttachFile.MAX_BYTES + 2) / 3), encoded)
        assertTrue(encoded + ChatHistory.MAX_CHARS + 200_000 < AttachFile.BACKEND_MAX_BODY)
    }

    // -------------------------------------------------------------- names ---

    @Test
    fun `the name is the file's own, never a path`() {
        assertEquals("taxes.pdf", AttachFile.shownName("taxes.pdf"))
        assertEquals("taxes.pdf", AttachFile.shownName("C:\\Users\\me\\Documents\\taxes.pdf"))
        assertEquals("taxes.pdf", AttachFile.shownName("/storage/emulated/0/Download/taxes.pdf"))
        // A provider with a name of its own for it, e.g. a download's title.
        assertEquals("taxes.pdf", AttachFile.shownName("  C:\\x/taxes.pdf  "))
        assertEquals(AttachFile.NO_NAME, AttachFile.shownName(null))
        assertEquals(AttachFile.NO_NAME, AttachFile.shownName("   "))
        assertEquals(AttachFile.NO_NAME, AttachFile.shownName("C:\\folder\\"))
    }

    @Test
    fun `control characters and absurd lengths are cleaned off a name`() {
        assertEquals("taxes.pdf", AttachFile.shownName("tax\u0000es.pdf"))
        assertEquals("taxes.pdf", AttachFile.shownName("taxes.pdf\u007f"))
        val long = "a".repeat(500) + ".pdf"
        val capped = AttachFile.shownName(long)
        assertEquals(AttachFile.NAME_MAX, capped.length)
        // The extension survives the cut: the PC decides what a file is by name.
        assertTrue(capped, capped.endsWith(".pdf"))
        assertTrue(capped, AttachFile.kindOf(capped) != null)
    }

    @Test
    fun `round brackets, spaces and unicode survive, because real files have them`() {
        assertEquals("2024 tax return (final).pdf", AttachFile.shownName("2024 tax return (final).pdf"))
        assertEquals("résumé.docx", AttachFile.shownName("résumé.docx"))
    }

    // -------------------------------------------------------------- kinds ---

    @Test
    fun `the seven kinds, by extension, in both cases`() {
        for (ext in listOf("pdf", "docx", "xlsx", "pptx", "md", "markdown", "txt", "csv")) {
            assertTrue(ext, AttachFile.kindOf("taxes.$ext") != null)
            assertTrue("$ext upper", AttachFile.kindOf("TAXES.${ext.uppercase()}") != null)
        }
        assertNull(AttachFile.kindOf("holiday.mp4"))
        assertNull(AttachFile.kindOf("notes.zip"))
        assertNull(AttachFile.kindOf("id_rsa"))
        assertNull(AttachFile.kindOf(".env"))
        assertNull(AttachFile.kindOf("taxes."))
        assertNull(AttachFile.kindOf(null))
    }

    @Test
    fun `the picker offers only the kinds the PC reads, and nothing wild`() {
        assertEquals(AttachFile.KINDS.map { it.mime }.distinct(), AttachFile.MIME_TYPES.toList())
        assertFalse(AttachFile.MIME_TYPES.contains("*/*"))
        assertFalse(AttachFile.MIME_TYPES.contains("image/*"))
        assertFalse(AttachFile.MIME_TYPES.contains("video/*"))
        assertFalse(AttachFile.MIME_TYPES.contains("audio/*"))
    }

    @Test
    fun `the wire type is our own for the extension, not the provider's guess`() {
        val f = AttachFile.picked("%PDF".toByteArray(), "taxes.pdf", "text/plain")
        assertEquals("application/pdf", (f as AttachFile.Picked.Ok).file.mime)
        val docx = AttachFile.picked(byteArrayOf(1), "report.docx", "application/octet-stream")
        assertEquals(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            (docx as AttachFile.Picked.Ok).file.mime,
        )
    }

    @Test
    fun `a name with no extension at all may take the provider's type`() {
        val f = AttachFile.picked("%PDF".toByteArray(), "taxes", "application/pdf")
        assertEquals("application/pdf", (f as AttachFile.Picked.Ok).file.mime)
        // ...but a mislabelled extension never does: the name decides.
        val zip = AttachFile.picked(byteArrayOf(1), "taxes.zip", "application/pdf")
        assertTrue("$zip", zip is AttachFile.Picked.Refused)
        val env = AttachFile.picked(byteArrayOf(1), ".env", "text/plain")
        assertTrue("$env", env is AttachFile.Picked.Refused)
    }

    @Test
    fun `an unreadable name or an empty file is refused in plain words`() {
        val empty = refusal(ByteArray(0), "taxes.pdf")
        assertEquals(AttachFile.UNREADABLE, empty)
        val zip = refusal(byteArrayOf(1, 2, 3), "holiday.zip")
        assertTrue(zip, zip.contains("holiday.zip"))
        assertTrue(zip, zip.contains("folder Jarvis may look in"))
        // ...and it names every kind that IS read, so a kind cannot be added
        // without the refusal (and the menu's own detail line) saying so.
        for (k in AttachFile.KINDS) {
            assertTrue("${k.label} is missing from: $zip", zip.contains(k.label))
        }
    }

    // ------------------------------------------------------------- base64 ---

    @Test
    fun `base64 is the raw bytes, with no data prefix and no text mangling`() {
        assertEquals("aGVsbG8=", AttachFile.base64("hello".toByteArray()))
        assertEquals("", AttachFile.base64(ByteArray(0)))
        // Bytes that are not valid text must survive exactly.
        val raw = byteArrayOf(0, 1, 2, 127, -1, -2, -128)
        val encoded = AttachFile.base64(raw)
        assertTrue(encoded, !encoded.startsWith("data:"))
        assertArrayEquals(raw, Base64.getDecoder().decode(encoded))
        // A tiny real PDF, magic bytes and all.
        val pdf = "%PDF-1.4\n1 0 obj\n".toByteArray()
        val f = (AttachFile.picked(pdf, "taxes.pdf") as AttachFile.Picked.Ok).file
        assertEquals(AttachFile.base64(pdf), f.base64)
        assertArrayEquals(pdf, Base64.getDecoder().decode(f.base64))
    }

    private fun assertArrayEquals(want: ByteArray, got: ByteArray) {
        assertEquals(want.toList(), got.toList())
    }

    // -------------------------------------------------------- wire shape ---

    @Test
    fun `the part is exactly the four fields the PC reads, in order`() {
        val f = (AttachFile.picked("hello".toByteArray(), "taxes.pdf") as AttachFile.Picked.Ok).file
        // This literal is the contract: the backend's fixture must be this.
        assertEquals(
            """{"name":"taxes.pdf","mime":"application/pdf","size":5,"data":"aGVsbG8="}""",
            AttachFile.part(f).toString(),
        )
        assertEquals(
            listOf("name", "mime", "size", "data"),
            AttachFile.part(f).keys.toList(),
        )
    }

    @Test
    fun `the request carries has_file beside has_image, and the part on the newest message`() {
        val f = ready()
        val asking = ChatHistory.asking("what does this say?", file = true)
        val body = Json.parseToJsonElement(
            ChatHistory.requestBody(emptyList(), asking, file = f),
        ).jsonObject
        assertEquals(JsonPrimitive(true), body["has_file"])
        assertEquals(JsonPrimitive(false), body["has_image"])
        // "Beside has_image" is literal: they are adjacent, in this order.
        assertEquals(
            listOf("messages", "has_image", "has_file", "stream", "auto", "device"),
            body.keys.toList(),
        )
        val last = body["messages"]!!.jsonArray.last().jsonObject
        assertEquals("user", last["role"]!!.jsonPrimitive.content)
        assertEquals("what does this say?", last["content"]!!.jsonPrimitive.content)
        assertEquals("typed", last["provenance"]!!.jsonPrimitive.content)
        assertEquals(AttachFile.part(f), last["attachment"]!!.jsonObject)
        // The plain text of the message is NOT where the file went.
        assertFalse(last["content"].toString().contains("base64"))
    }

    @Test
    fun `an ordinary question carries no has_file at all, so it is the request it always was`() {
        val body = Json.parseToJsonElement(
            ChatHistory.requestBody(emptyList(), ChatHistory.asking("hi")),
        ).jsonObject
        assertFalse("has_file must be absent", body.containsKey("has_file"))
        assertEquals(JsonPrimitive(false), body["has_image"])
        assertNull(body["messages"]!!.jsonArray.last().jsonObject["attachment"])
    }

    @Test
    fun `a picture's request is untouched, and a file beside it rides on the same message`() {
        val picture = "data:image/jpeg;base64,AAAA"
        val plain = Json.parseToJsonElement(
            ChatHistory.requestBody(emptyList(), ChatHistory.asking("what is this?", picture = true), picture),
        ).jsonObject
        assertFalse("the picture path must not grow has_file", plain.containsKey("has_file"))
        assertEquals(JsonPrimitive(true), plain["has_image"])

        val both = Json.parseToJsonElement(
            ChatHistory.requestBody(
                emptyList(), ChatHistory.asking("what is this?", picture = true), picture, file = ready(),
            ),
        ).jsonObject
        assertEquals(JsonPrimitive(true), both["has_image"])
        assertEquals(JsonPrimitive(true), both["has_file"])
        val last = both["messages"]!!.jsonArray.last().jsonObject
        assertEquals(2, last["content"]!!.jsonArray.size)
        assertEquals("taxes.pdf", last["attachment"]!!.jsonObject["name"]!!.jsonPrimitive.content)
    }

    @Test
    fun `a file with no words typed still makes one message`() {
        val asking = ChatHistory.asking("", file = true)
        assertEquals(1, asking.size)
        assertEquals("", asking.single().text)
        assertEquals("typed", asking.single().provenance)
        // A picture's caption tag is a picture's own word: a file changes nothing.
        assertEquals("voice", ChatHistory.asking("", "voice", file = true).single().provenance)
    }

    @Test
    fun `a later question never carries the file again`() {
        val window = ChatHistory.commit(
            emptyList(),
            ChatHistory.asking("what does this say?", file = true),
            "It is a tax form.",
        )
        val next = Json.parseToJsonElement(
            ChatHistory.requestBody(window, ChatHistory.asking("and the second page?")),
        ).jsonObject
        assertFalse(next.containsKey("has_file"))
        assertFalse("the bytes must not survive in the conversation", next.toString().contains("aGVsbG8="))
        // The kept pair, then the new question - and the file nowhere.
        assertEquals(3, next["messages"]!!.jsonArray.size)
        assertEquals(1, window.size)
    }

    @Test
    fun `the attachment is only ever on the newest message`() {
        val window = ChatHistory.commit(emptyList(), ChatHistory.asking("first"), "a1")
        val asking = ChatHistory.asking("second", shared = "text from another app", file = true)
        val body = Json.parseToJsonElement(
            ChatHistory.requestBody(window, asking, file = ready()),
        ).jsonObject
        val msgs = body["messages"]!!.jsonArray.map { it.jsonObject }
        assertEquals(4, msgs.size)
        assertNull("the shared message", msgs[2]["attachment"])
        assertEquals("taxes.pdf", msgs[3]["attachment"]!!.jsonObject["name"]!!.jsonPrimitive.content)
        assertEquals(1, msgs.count { it.containsKey("attachment") })
    }

    @Test
    fun `the size on the wire is the raw byte count, which the chip also says`() {
        val f = ready(bytes = "1234567890")
        assertEquals(10L, AttachFile.part(f)["size"]!!.jsonPrimitive.long)
        assertTrue(AttachFile.attachedLine(f).contains("10 bytes"))
    }

    // ------------------------------------------------------------ the chip ---

    @Test
    fun `the chip says the name, the size, read on your PC, and the outside-text rule`() {
        val line = AttachFile.attachedLine(ready(bytes = "123456789012"))
        assertTrue(line, line.startsWith("taxes.pdf \u2014 12 bytes. Read on your PC."))
        assertTrue(line, line.contains(AttachFile.OUTSIDE_TEXT))
        assertTrue(line, line.contains("web search"))
        assertEquals("1.2 MB", AttachFile.sizeWords(1_234_567))
        assertEquals("2.5 MB", AttachFile.sizeWords(AttachFile.MAX_BYTES))
        assertEquals("4.2 MB", AttachFile.sizeWords(4_200_000))
        assertEquals("1 MB", AttachFile.sizeWords(1_000_000))
        assertEquals("12 KB", AttachFile.sizeWords(12_345))
    }

    @Test
    fun `the ready file never prints its bytes`() {
        val f = ready()
        assertFalse(f.toString().contains(f.base64))
        assertTrue(f.toString().contains("taxes.pdf"))
    }

    // ------------------------------------------------------- nothing kept ---

    /**
     * The privacy promises that can be read off the source: no file API, no
     * preferences, no log, no Bundle. `data:` (the one thing that would turn
     * the wire field into a picture-style data URI) is proved by behaviour in
     * the base64 test above, not by a source search - the file's own comments
     * say the word.
     */
    @Test
    fun `the helper has no way to write, log or stash the bytes`() {
        val src = SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/net/AttachFile.kt")
        for (bad in listOf(
            "java.io.File", "FileOutputStream", "openFileOutput", "SharedPreferences",
            "android.util.Log", "putExtra", "getExternalFilesDir",
        )) {
            assertFalse("AttachFile.kt must not contain $bad", src.contains(bad))
        }
    }

    @Test
    fun `the activity never writes the picked bytes anywhere`() {
        val src = SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt")
        assertFalse(src.contains("openFileOutput"))
        assertFalse(src.contains("FileOutputStream"))
        // ...and the picker is the one already used for a WAV: no new contract.
        assertTrue(src.contains("ActivityResultContracts.OpenDocument()"))
        assertTrue(src.contains("AttachFile.MIME_TYPES"))
    }
}
