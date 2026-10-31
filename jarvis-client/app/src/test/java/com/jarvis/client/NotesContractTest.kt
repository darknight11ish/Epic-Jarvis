package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.Approvals
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.JarvisApi
import com.jarvis.client.net.Notes
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The notes editor's four routes, as the CONTRACT says the PC answers them
 * (`.dsh-scratch/NOTES-EDITOR-2026-10-31/CONTRACT.md`), read the way the phone
 * reads them.
 *
 * There is no shared generated fixture for these routes yet - the backend lane
 * owns `jarvis_notes_edit.py` and its own suite - so the answers here are the
 * contract's own examples, spelled as the PC will send them. That is a real
 * gap the Lead should know about (named in the report): when the backend lane
 * adds a generated fixture, this file should read that instead, so one copy
 * of the shapes serves both apps.
 *
 * What this proves, and why each matters to the owner:
 *  - the list carries NO note text, and the phone never invents a note;
 *  - the save body carries the path, the WHOLE text and the hash the edit
 *    started from, and an empty note is a real note (savable);
 *  - waiting is not saved, denied/failed/conflict are never saved, and only
 *    the PC's `saved` says saved;
 *  - a conflict says the note changed and nothing was written;
 *  - a desktop without the routes, or with no vault, is told to set itself up
 *    in plain words instead of showing a bare status code.
 */
class NotesContractTest {

    private fun json(text: String): JsonObject = JarvisJson.parseToJsonElement(text).jsonObject

    private fun said(text: String) = Notes.describe(json(text))

    // ------------------------------------------------------------ the list ----

    @Test
    fun `the list answer is read as the contract sends it, and carries no text`() {
        val v = Notes.view(
            json(
                """{"ok": true, "root": "C:\\Users\\pcadmin\\Vault", "count": 2,
                    "notes": [
                      {"path": "Inbox/idea.md", "title": "idea", "size": 812, "mtime": 1761900000.0},
                      {"path": "Journal/today.txt", "title": "today", "size": 20, "mtime": 1761900100.5}
                    ],
                    "truncated": false}""",
            ),
        )
        assertEquals("C:\\Users\\pcadmin\\Vault", v.root)
        assertEquals(2, v.count)
        assertFalse(v.truncated)
        assertEquals(listOf("Inbox/idea.md", "Journal/today.txt"), v.notes.map { it.path })
        assertEquals(listOf("idea", "today"), v.notes.map { it.title })
        assertEquals(812L, v.notes.first().size)
        assertEquals(1761900100.5, v.notes[1].mtime, 0.0)
        // The list answer's own rule: nothing here is a note's words.
        assertFalse(Notes.view(json("""{"ok": true, "notes": []}""")).notes.isNotEmpty())
    }

    @Test
    fun `a note row without a path is skipped, a title falls back to the file name, and truncation is read`() {
        val v = Notes.view(
            json(
                """{"ok": true, "count": 3, "truncated": true, "notes": [
                    {"title": "no path here", "size": 1},
                    {"path": "a/b/c.md", "size": 5, "mtime": 1.0}
                ]}""",
            ),
        )
        assertEquals(1, v.notes.size)
        assertEquals("a/b/c.md", v.notes.single().path)
        assertEquals("c", v.notes.single().title)
        assertTrue(v.truncated)
        // The contract's answer carries `count` for the rows it sends.
        assertEquals(3, v.count)
    }

    @Test
    fun `a missing count falls back to the rows really sent, never to zero`() {
        val v = Notes.view(json("""{"ok": true, "notes": [{"path": "x.md"}, {"path": "y.md"}]}"""))
        assertEquals(2, v.count)
        assertEquals(0L, v.notes.first().size)
    }

    // ------------------------------------------------------------ the paths ----

    @Test
    fun `the list and read paths encode the search and the vault path`() {
        assertEquals("/api/notes/list", Notes.listPath(""))
        assertEquals("/api/notes/list", Notes.listPath("   "))
        assertEquals("/api/notes/list?q=spring+meeting", Notes.listPath(" spring meeting "))
        assertEquals("/api/notes/read?path=folder%2Fa+note.md", Notes.readPath("folder/a note.md"))
        assertEquals("/api/notes/save?id=notes%2Fjob+1", Notes.statusPath("notes/job 1"))
        // The search text is bounded, so a pasted essay cannot become a URL.
        assertEquals(Notes.LIST_PATH + "?q=" + "a".repeat(Notes.MAX_QUERY), Notes.listPath("a".repeat(500)))
    }

    // ------------------------------------------------------------- the save ----

    @Test
    fun `the save carries the path, the whole text and the hash the edit started from - and nothing else`() {
        val text = "line one\nline \"two\" \\ backslash"
        val body = Notes.saveBody("Inbox/idea.md", text, "abc123")!!
        val sent = JarvisJson.parseToJsonElement(body).jsonObject
        assertEquals(setOf("path", "text", "expected_sha256"), sent.keys)
        assertEquals("Inbox/idea.md", sent["path"]!!.jsonPrimitive.content)
        assertEquals(text, sent["text"]!!.jsonPrimitive.content)
        assertEquals("abc123", sent["expected_sha256"]!!.jsonPrimitive.content)
        // An empty note is a real note: it must be savable, or the editor
        // could not create a blank one in the vault.
        assertTrue(Notes.saveBody("Inbox/idea.md", "", "abc")!!.contains("\"text\":\"\""))
        assertNull("no note named, nothing sent", Notes.saveBody("   ", "text", "abc"))
    }

    // ------------------------------------------------------------- the read ----

    @Test
    fun `a note's text and hash are read whole, and an answer missing either is not a note`() {
        val n = Notes.readNote(
            json(
                """{"ok": true, "path": "Inbox/idea.md", "text": "hello #tag\nsecond line",
                    "sha256": "d1e2f3", "size": 22, "mtime": 1761900000.0}""",
            ),
        )!!
        assertEquals("Inbox/idea.md", n.path)
        assertEquals("hello #tag\nsecond line", n.text)
        assertEquals("d1e2f3", n.sha256)
        assertEquals(22L, n.size)
        assertNull(Notes.readNote(json("""{"ok": true, "path": "x.md", "sha256": "aa"}""")))
        assertNull(Notes.readNote(json("""{"ok": true, "path": "x.md", "text": "hi"}""")))
        assertNull(Notes.readNote(json("""{"ok": true, "text": "hi", "sha256": "aa"}""")))
    }

    // ------------------------------------------------------------ the states ----

    @Test
    fun `waiting is not saved, and says where the card can be answered`() {
        val s = said("""{"ok": true, "state": "waiting", "id": "notes_1", "path": "Inbox/idea.md"}""")
        assertFalse(s.final)
        assertFalse(s.saved)
        assertFalse(s.conflict)
        assertTrue(s.text.contains(Approvals.WHERE))
        assertEquals("notes_1", Notes.jobId(json("""{"ok": true, "state": "waiting", "id": "notes_1"}""")))
    }

    @Test
    fun `only the PC's saved says saved, and it brings the new hash`() {
        val s = said("""{"ok": true, "state": "saved", "path": "Inbox/idea.md", "sha256": "new123"}""")
        assertTrue(s.final)
        assertTrue(s.saved)
        assertEquals("new123", s.sha256)
        // The PC's own message wins, in its own words.
        val own = said("""{"ok": true, "state": "saved", "message": "Saved to idea.md.", "sha256": "x"}""")
        assertEquals("Saved to idea.md.", own.text)
    }

    @Test
    fun `denied, failed and conflict are final and never saved`() {
        val denied = said("""{"ok": true, "state": "denied", "path": "a.md"}""")
        assertTrue(denied.final)
        assertFalse(denied.saved)
        assertTrue("says the note is unchanged", denied.text.contains("unchanged"))
        val failed = said("""{"ok": false, "state": "failed", "error": "the vault folder moved"}""")
        assertTrue(failed.final)
        assertFalse(failed.saved)
        assertEquals("The vault folder moved.", failed.text)
        val conflict = said(
            """{"ok": false, "state": "conflict", "path": "a.md", "current_sha256": "aaa"}""",
        )
        assertTrue(conflict.final)
        assertFalse(conflict.saved)
        assertTrue(conflict.conflict)
        assertEquals("aaa", conflict.sha256)
        assertTrue("says nothing was written", conflict.text.contains("nothing was written"))
    }

    @Test
    fun `an explained refusal with no state is its sentence, never a bare code`() {
        val r = said("""{"ok": false, "error": "no obsidian vault is set up"}""")
        assertTrue(r.final)
        assertFalse(r.saved)
        assertEquals("No obsidian vault is set up.", r.text)
    }

    @Test
    fun `an answer that did not say how it went is never taken as saved`() {
        val s = said("""{"ok": true, "path": "a.md"}""")
        assertTrue(s.final)
        assertFalse(s.saved)
        assertTrue(s.text.contains("did not say"))
    }

    // ------------------------------------------------------------ failures ----

    @Test
    fun `an older desktop or one with no vault is told to set itself up, in plain words`() {
        val missing = Notes.failure(ApiError.NotFound)!!
        assertTrue(missing.contains("apply-patches"))
        assertTrue(missing.contains("Nothing was changed"))
        val noVault = Notes.failure(ApiError.NotAvailable)!!
        assertTrue(noVault.contains("vault_directory"))
        assertTrue(noVault.contains("docs/INSTALL.md"))
        assertNull("a wrong token is the app's own sentence", Notes.failure(ApiError.BadToken))
    }

    @Test
    fun `the contract's own bounds are the ones sent`() {
        assertEquals(2L * 1024L * 1024L, Notes.MAX_BYTES)
        assertEquals(2_000, Notes.MAX_LISTED)
        assertEquals(2_000L, Notes.POLL_MS)
        assertTrue("the follow outlives the PC's 180s card", Notes.GIVE_UP_MS > 180_000L)
        assertTrue(Notes.STALE.contains("Not connected"))
    }

    @Test
    fun `a list row's size and a path's fallback name read plainly`() {
        assertEquals("812 B", Notes.sizeLabel(812))
        assertEquals("12 KB", Notes.sizeLabel(12 * 1024))
        assertEquals("3 MB", Notes.sizeLabel(3L * 1024 * 1024))
        assertEquals("idea", Notes.titleOf("Inbox/idea.md"))
        assertEquals("today", Notes.titleOf("Journal/today.txt"))
        assertEquals("plain", Notes.titleOf("plain"))
        assertEquals("note", Notes.titleOf("dir\\note.md"))
    }

    // ------------------------------------------------------- wiring pins ----

    @Test
    fun `the four routes are wired on this phone, and the save cannot approve anything`() {
        val api = file("jarvis-client/app/src/main/java/com/jarvis/client/net/JarvisApi.kt")
        for (name in listOf("notesList", "notesRead", "notesSave", "notesSaveStatus")) {
            assertTrue("JarvisApi has no $name", api.contains("suspend fun $name("))
        }
        assertTrue("the list route is read through the explaining reader",
            api.contains("Notes.listPath(query)"))
        assertTrue("a save goes through postExplained", api.contains("postExplained(Notes.SAVE_PATH, body)"))
        val runtime = file("jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt")
        assertTrue("the runtime has no saveNote", runtime.contains("suspend fun saveNote("))
        assertTrue("the runtime does not follow the save's job",
            runtime.contains("api.notesSaveStatus(id)"))
        // The phone never decides the card: the gate's decision call is not in
        // the notes CODE at all (its comments say "approval card" on purpose -
        // the words are the promise, not the mechanism), and the only path that
        // writes is the PC's.
        val notesBlock = runtime.substringAfter("// ------------------------------------------------------------ notes ----")
            .substringBefore("// ------------------------------------------------------------ watch ----")
        val code = notesBlock.lines()
            .filterNot { it.trim().startsWith("//") || it.trim().startsWith("*") }
            .joinToString("\n")
        assertFalse("the notes code calls decide()", code.contains("decide("))
        assertFalse("the notes code approves anything", code.contains("approve", ignoreCase = true))
        // The plate exists and says what save does.
        val plate = file("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/NotesPlate.kt")
        assertTrue("the Notes plate is missing", plate.contains("NotesSection(canAct"))
        assertTrue("the plate's own words do not name the approval card",
            plate.contains("one approval card on the PC"))
        val screen = file("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/BrainScreen.kt")
        assertTrue("BrainScreen does not draw the Notes plate", screen.contains("plateDrawn(\"notes\")"))
        val sections = file("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/BrainSections.kt")
        assertTrue("BrainSections does not declare the Notes pair",
            sections.contains("Plate(\"notes\""))
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
