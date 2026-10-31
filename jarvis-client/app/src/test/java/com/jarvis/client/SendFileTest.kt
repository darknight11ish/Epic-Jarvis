package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.SendFile
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import kotlin.io.encoding.Base64
import kotlin.io.encoding.ExperimentalEncodingApi

/**
 * "Send one file from the PC to the phone" (the owner's ask of 2026-10-31;
 * Gemini Q7; docs/JARVIS-API.md section 172; backend `jarvis_send_file.py`) -
 * the phone's half of the contract, as the PC's routes answer it.
 *
 * What this proves, and why each matters to the owner:
 *  - the list is read with every field the PC sends (name, folder, size,
 *    mime, expiry), and a PC without the module (404/501) is NOT a failure;
 *  - a download's bytes are decoded from base64 exactly, and a file whose
 *    sha256 disagrees with the PC's is never kept;
 *  - a 404/409/413 keeps the PC's own sentence (the ten-minute window,
 *    "it changed", "over the cap") instead of a bare code;
 *  - the phone never names a path: only an id of the PC's own shape can be
 *    asked for, and a real filename with folders in it is refused;
 *  - the drawn words are the app's plain ones (size, "expires in", the
 *    limits line), and the plate's wiring keeps the phone's own View
 *    (FileProvider + ACTION_VIEW) and Save to Downloads (MediaStore.Downloads)
 *    steps, with no filename ever fetched while the private lists are hidden.
 */
class SendFileTest {

    private fun json(text: String): JsonObject = JarvisJson.parseToJsonElement(text).jsonObject

    // --------------------------------------------------------------- routes ----

    @Test
    fun `the two routes are the contract's, and only an id of the PC's shape can be asked for`() {
        assertEquals("/api/files/send", SendFile.LIST_PATH)
        assertEquals("/api/files/download", SendFile.DOWNLOAD_PATH)
        assertEquals(10L * 1024L * 1024L, SendFile.MAX_BYTES)
        assertEquals(600, SendFile.TTL_SECONDS)
        // The PC's own id shape: file_ and 16-64 URL-safe characters.
        val id = "file_" + "a".repeat(16)
        assertEquals("/api/files/download?id=$id", SendFile.downloadPath(id))
        assertNull("a filename is not an id", SendFile.downloadPath("invoice.pdf"))
        assertNull("a path is not an id", SendFile.downloadPath("C:\\Users\\me\\invoice.pdf"))
        assertNull("too short", SendFile.downloadPath("file_abc"))
        assertNull("too long", SendFile.downloadPath("file_" + "a".repeat(65)))
        assertNull("blank", SendFile.downloadPath("  "))
    }

    // ----------------------------------------------------------- the list ----

    @Test
    fun `the list answer is read whole, and nothing about it is invented`() {
        val reply = SendFile.readList(
            200,
            json(
                """{"ok": true, "count": 1, "cap_bytes": 10485760, "ttl_seconds": 600,
                    "single_use": true,
                    "said": "A file appears here only after the owner approved its card; it can be downloaded once, within ten minutes.",
                    "files": [{"id": "file_0123456789abcdef", "name": "invoice.pdf",
                               "folder": "C:\\Users\\me\\Documents", "size_bytes": 1482331,
                               "mime": "application/pdf", "expires_in": 540}]}""",
            ),
        )
        val ready = reply as SendFile.ListReply.Ready
        assertEquals(1, ready.files.size)
        val file = ready.files.single()
        assertEquals("file_0123456789abcdef", file.id)
        assertEquals("invoice.pdf", file.name)
        assertEquals("C:\\Users\\me\\Documents", file.folder)
        assertEquals(1482331L, file.sizeBytes)
        assertEquals("application/pdf", file.mime)
        assertEquals(540, file.expiresIn)
        assertEquals(SendFile.MAX_BYTES, ready.capBytes)
        assertEquals(600, ready.ttlSeconds)
        assertTrue(ready.singleUse)
        assertTrue("the PC's own sentence is kept", ready.said.contains("only after the owner approved"))
    }

    @Test
    fun `an older PC is Missing, a failed read is the PC's sentence, and a row without an id is skipped`() {
        assertEquals(SendFile.ListReply.Missing, SendFile.readList(404, null))
        assertEquals(SendFile.ListReply.Missing, SendFile.readList(501, null))
        val failed = SendFile.readList(500, json("""{"ok": false, "error": "the list broke"}"""))
        assertEquals("the list broke", (failed as SendFile.ListReply.Refused).said)
        // A row without an id or a name cannot be asked for, so it is not drawn.
        val ready = SendFile.readList(
            200,
            json("""{"ok": true, "files": [
                {"name": "no id.pdf"}, {"id": "file_0123456789abcdef"}]}"""),
        ) as SendFile.ListReply.Ready
        assertTrue(ready.files.isEmpty())
    }

    // ------------------------------------------------------- the download ----

    @OptIn(ExperimentalEncodingApi::class)
    private fun goodDownload(bytes: ByteArray = "hello".encodeToByteArray()): JsonObject {
        val data = Base64.encode(bytes)
        return json(
            """{"ok": true, "name": "invoice.pdf", "size_bytes": ${bytes.size},
                "mime": "application/pdf", "sha256": "${SendFile.sha256(bytes)}",
                "data": "$data"}""",
        )
    }

    @OptIn(ExperimentalEncodingApi::class)
    @Test
    fun `the bytes are decoded exactly, and a file whose sha does not match is never kept`() {
        val bytes = "Jarvis sent this.".encodeToByteArray()
        val got = SendFile.readDownload(200, goodDownload(bytes)) as SendFile.Fetched.Got
        assertEquals("invoice.pdf", got.name)
        assertEquals("application/pdf", got.mime)
        assertTrue(bytes.contentEquals(got.bytes))
        assertEquals(SendFile.sha256(bytes), got.sha256)
        // A body whose sha disagrees with its bytes: refused, not kept.
        val badSha = SendFile.readDownload(
            200,
            json(
                """{"ok": true, "name": "invoice.pdf", "size_bytes": 1, "mime": "application/pdf",
                    "sha256": "${"0".repeat(64)}", "data": "aGVsbG8="}""",
            ),
        )
        assertEquals(SendFile.NOT_WHAT_WAS_SENT, (badSha as SendFile.Fetched.Refused).said)
        // A body with no bytes at all is not a file.
        val empty = SendFile.readDownload(200, json("""{"ok": true, "name": "x.pdf"}"""))
        assertEquals(SendFile.UNREADABLE, (empty as SendFile.Fetched.Refused).said)
    }

    @Test
    fun `a 404, a 409 and a 413 keep the PC's own sentence`() {
        val gone = SendFile.readDownload(
            404,
            json("""{"ok": false, "error": "That file is not waiting for your phone any more - the ten-minute window passed or it was already downloaded."}"""),
        )
        assertTrue((gone as SendFile.Fetched.Refused).said.contains("ten-minute window passed"))
        val changed = SendFile.readDownload(
            409, json("""{"ok": false, "error": "That file changed since the card was approved, so nothing was sent."}"""),
        )
        assertTrue((changed as SendFile.Fetched.Refused).said.contains("changed since the card"))
        val over = SendFile.readDownload(
            413, json("""{"ok": false, "error": "invoice.pdf is 20,000,000 bytes, over the 10 MiB this slice sends."}"""),
        )
        assertTrue((over as SendFile.Fetched.Refused).said.contains("over the 10 MiB"))
        // A refusal with no sentence still says something plain, never a code.
        val bare = SendFile.readDownload(500, null)
        assertTrue((bare as SendFile.Fetched.Refused).said.isNotBlank())
    }

    // ------------------------------------------------------ the phone's words ----

    @Test
    fun `a filename is made safe to write, and the PC's numbers are said plainly`() {
        assertEquals("invoice.pdf", SendFile.nameForDisk("invoice.pdf"))
        assertEquals("invoice.pdf", SendFile.nameForDisk("C:\\Users\\me\\invoice.pdf"))
        assertEquals("invoice.pdf", SendFile.nameForDisk("../../invoice.pdf"))
        assertEquals("invoice.pdf", SendFile.nameForDisk("in<v>oice.pdf"))
        assertEquals("file", SendFile.nameForDisk("   "))
        assertEquals("file", SendFile.nameForDisk("..."))
        assertEquals("812 bytes", SendFile.sizeWords(812))
        assertEquals("1,482,331 bytes (1.4 MB large)", SendFile.sizeWords(1482331))
        assertEquals("2,048 bytes (2 KB large)", SendFile.sizeWords(2048))
        assertEquals("expires in 9 min", SendFile.expiryWords(540))
        assertEquals("expires in 2 min", SendFile.expiryWords(61))
        assertEquals("expires in under a minute", SendFile.expiryWords(30))
        assertEquals("expired", SendFile.expiryWords(0))
        assertEquals("application/octet-stream", SendFile.mimeOr(""))
        assertEquals("application/pdf", SendFile.mimeOr("application/pdf"))
    }

    // ------------------------------------------------------------ the wiring ----

    @Test
    fun `the phone lists and fetches, keeps the PC's status and body, and never asks for a path`() {
        val api = file("jarvis-client/app/src/main/java/com/jarvis/client/net/JarvisApi.kt")
        assertTrue("JarvisApi has no list", api.contains("suspend fun sendFiles("))
        assertTrue("JarvisApi has no fetch", api.contains("suspend fun downloadFile("))
        // The whole status and body come back, so a 404's own sentence survives.
        assertTrue("the file routes do not keep the body", api.contains("private suspend fun filesCall("))
        assertTrue(api.contains("if (resp.code == 401 || resp.code == 403)"))

        val runtime = file("jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt")
        assertTrue("the runtime has no list", runtime.contains("suspend fun sendFiles("))
        assertTrue("the runtime has no fetch", runtime.contains("suspend fun downloadFile("))
        assertTrue("the runtime never refuses to ask while hidden",
            runtime.contains("if (privateListsHidden)"))

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
