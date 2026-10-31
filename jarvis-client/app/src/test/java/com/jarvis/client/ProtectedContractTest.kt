package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.Approvals
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Protected
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
 * "Protected from Jarvis" on the phone, as the contract says the PC answers
 * (`.dsh-scratch/PROTECTED-ITEMS-2026-10-31/CONTRACT.md`), read the way this
 * phone reads it.
 *
 * What this proves, and why each matters to the owner:
 *  - the list is read whole, with the same kind and mode words the PC shows,
 *    and no entry is invented;
 *  - the phone's WIRING IS THE WHOLE PHONE FATAL: list and Remove only. There is
 *    no add route and no file picker in the phone's source - adding is the PC's
 *    pickers or a chat request, and the contract says so;
 *  - Remove is loosening, so it always asks: `waiting` is not removed, the
 *    entry stays until the card is approved, and the phone never decides it;
 *  - an older desktop is told to run apply-patches in plain words.
 *
 * As with the notes editor: there is no shared generated fixture for these
 * routes yet (the backend lane owns `jarvis_protection.py` and its suite), so
 * the answers here are the contract's own shapes. When the backend lane adds a
 * generated fixture, point this file at it so both apps read one copy.
 */
class ProtectedContractTest {

    private fun json(text: String): JsonObject = JarvisJson.parseToJsonElement(text).jsonObject

    // ------------------------------------------------------------ the list ----

    @Test
    fun `the list answer is read as the contract sends it, with its own kind and mode words`() {
        val v = Protected.view(
            json(
                """{"ok": true, "count": 3,
                    "modes": ["blocked", "readonly"],
                    "change_card": "Removing protection asks you for one approval card.",
                    "items": [
                      {"id": "prot_ab12cd34", "kind": "folder",
                       "target": "C:\\Users\\pcadmin\\Documents\\Taxes", "mode": "blocked",
                       "added": "2026-10-31T08:00:00Z", "added_by": "owner"},
                      {"id": "prot_ef56gh78", "kind": "file",
                       "target": "C:\\Users\\pcadmin\\notes\\budget.md", "mode": "readonly",
                       "added": "2026-10-31T08:01:00Z", "added_by": "chat"},
                      {"id": "prot_ij90kl12", "kind": "program", "target": "notepad.exe",
                       "mode": "readonly", "added": "2026-10-31T08:02:00Z", "added_by": "owner"}
                    ]}""",
            ),
        )
        assertEquals(3, v.count)
        assertEquals(listOf("blocked", "readonly"), v.modes)
        assertEquals("Removing protection asks you for one approval card.", v.changeCard)
        assertEquals(
            listOf("C:\\Users\\pcadmin\\Documents\\Taxes", "C:\\Users\\pcadmin\\notes\\budget.md", "notepad.exe"),
            v.items.map { it.target },
        )
        assertEquals(listOf("folder", "file", "program"), v.items.map { it.kind })
        assertEquals(listOf("blocked", "readonly", "readonly"), v.items.map { it.mode })
        assertEquals("owner, chat, owner", v.items.joinToString(", ") { it.addedBy })
        // The owner's words, exactly as the contract fixes them.
        assertEquals("Blocked — no access", Protected.modeWord("blocked"))
        assertEquals("Read-only", Protected.modeWord("readonly"))
        assertEquals("Folder", Protected.kindWord("folder"))
        assertEquals("File", Protected.kindWord("file"))
        assertEquals("Program", Protected.kindWord("program"))
        // ...and what each mode means, including the program's own meaning.
        assertTrue(Protected.modeMeaning("folder", "blocked").contains("may not read"))
        assertTrue(Protected.modeMeaning("program", "readonly").contains("never act"))
        assertTrue(Protected.modeMeaning("file", "readonly").contains("write"))
    }

    @Test
    fun `an entry without an id or a target is skipped, and a missing count falls back to the rows sent`() {
        val v = Protected.view(
            json(
                """{"ok": true, "items": [
                    {"kind": "folder", "target": "C:\\x", "mode": "blocked"},
                    {"id": "prot_1", "kind": "file", "mode": "blocked"},
                    {"id": "prot_2", "kind": "program", "target": "notepad.exe", "mode": "readonly"}
                ]}""",
            ),
        )
        assertEquals(listOf("prot_2"), v.items.map { it.id })
        assertEquals(1, v.count)
        assertEquals(emptyList<String>(), v.modes)
        assertEquals("", v.changeCard)
    }

    @Test
    fun `unknown modes and kinds are shown as the PC sent them, never invented`() {
        assertEquals("quarantined", Protected.modeWord("quarantined"))
        // The three real kinds get the PC's capitalised words; anything else is
        // shown EXACTLY as the PC sent it, not a guessed third kind.
        assertEquals("widget", Protected.kindWord("widget"))
        assertEquals("", Protected.modeMeaning("file", "quarantined"))
        val v = Protected.view(
            json("""{"ok": true, "items": [{"id": "p", "kind": "widget", "target": "x", "mode": "q"}]}"""),
        )
        assertEquals("widget", v.items.single().kind)
    }

    // -------------------------------------------------------------- remove ----

    @Test
    fun `the remove body names one entry and nothing else, and no entry means nothing is sent`() {
        val sent = JarvisJson.parseToJsonElement(Protected.removeBody("prot_ab12cd34")!!).jsonObject
        assertEquals(setOf("id"), sent.keys)
        assertEquals("prot_ab12cd34", sent["id"]!!.jsonPrimitive.content)
        assertNull("nothing named, nothing sent", Protected.removeBody("   "))
    }

    @Test
    fun `waiting is not removed - the entry stays until the card is approved`() {
        val s = Protected.describe(
            json("""{"ok": true, "state": "waiting", "id": "prot_ab12cd34"}"""),
        )
        assertTrue("the phone must keep watching the list", s.removing)
        assertTrue("the owner is told where the card is", s.text.contains(Approvals.WHERE))
        assertTrue("and that nothing changes yet", s.text.contains("stays protected"))
    }

    @Test
    fun `an explained refusal is its sentence, and is never taken as removed`() {
        val s = Protected.describe(
            json("""{"ok": false, "error": "no protected item with that id"}"""),
        )
        assertFalse(s.removing)
        assertEquals("No protected item with that id", s.text)
        // An answer that said nothing usable is never a remove either.
        val odd = Protected.describe(json("""{"ok": true}"""))
        assertFalse(odd.removing)
        assertTrue(odd.text.contains("did not say"))
    }

    @Test
    fun `the waiting, still-there and removed lines say what happened, and the pickers line is the contract's`() {
        assertTrue(Protected.REMOVED.contains("no longer protected"))
        assertTrue(Protected.STILL_THERE.contains("denied"))
        assertTrue(Protected.STALE.contains("Not connected"))
        assertTrue(Protected.PICKERS.contains("on your PC"))
        assertTrue(Protected.PICKERS.contains("chat"))
        assertTrue("adding always raises a card", Protected.PICKERS.contains("raise a card"))
    }

    @Test
    fun `an older desktop is told to run apply-patches, in plain words`() {
        val missing = Protected.failure(ApiError.NotFound)!!
        assertTrue(missing.contains("apply-patches"))
        assertTrue(missing.contains("Nothing was changed"))
        assertNull("a wrong token is the app's own sentence", Protected.failure(ApiError.BadToken))
    }

    // ------------------------------------------------------- the phone's half ----

    @Test
    fun `the phone lists and removes, and has NO add path and NO file picker`() {
        val api = file("jarvis-client/app/src/main/java/com/jarvis/client/net/JarvisApi.kt")
        assertTrue("JarvisApi has no protection list", api.contains("suspend fun protection("))
        assertTrue("JarvisApi has no removal ask", api.contains("suspend fun protectionRemove("))
        assertTrue("the removal goes through postExplained", api.contains("postExplained(Protected.REMOVE_PATH"))

        val runtime = file("jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt")
        assertTrue("the runtime has no removeProtected", runtime.contains("suspend fun removeProtected("))
        assertTrue("the runtime does not watch the list for the removal",
            runtime.contains("api.protection()"))
        val block = runtime.substringAfter("// --------------------------------------------------------- protection ----")
            .substringBefore("// ------------------------------------------------------------ watch ----")
        val code = block.lines()
            .filterNot { it.trim().startsWith("//") || it.trim().startsWith("*") }
            .joinToString("\n")
        assertFalse("the phone must never decide the removal card", code.contains("decide("))
        assertFalse("the phone must never approve anything", code.contains("approve", ignoreCase = true))

        // No add route anywhere in the phone's source - adding is the PC's
        // pickers or a chat request, and this lane must not grow an add path.
        val root = repoDir("jarvis-client/app/src/main/java/com/jarvis/client")
        val offenders = root.walkTopDown()
            .filter { it.isFile && it.extension == "kt" }
            .filter { it.readText().contains("/api/protection/add") }
            .map { it.name }
            .toList()
        assertEquals("adding from the phone is not in this contract: $offenders", emptyList<String>(), offenders)
        // No file picker on this screen: the phone cannot browse the PC's files.
        val plate = file(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/ProtectedPlate.kt",
        )
        for (picker in listOf("GetContent", "OpenDocument", "ACTION_GET_CONTENT", "ActivityResultContracts")) {
            assertFalse("no phone file picker: $picker", plate.contains(picker))
        }
        assertTrue("the plate says where adding happens", plate.contains("Protected.PICKERS"))
        assertTrue("the plate draws the two modes in the PC's words", plate.contains("Protected.modeWord("))
        assertFalse("the plate never decides a card", plate.contains("decide("))
    }

    @Test
    fun `the Settings row, the jump list and the search index are wired to one key`() {
        val screen = file("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SettingsScreen.kt")
        assertTrue("SettingsScreen has no protected row",
            screen.contains("item(key = \"protected\")"))
        assertTrue("the row does not draw the plate", screen.contains("ProtectedSection(canAct = canAct)"))
        // The index map moved: "protection" sits right after the folder allow-list.
        assertTrue("the settings index has no protected entry",
            Regex("\"protected\" to (\\d+),").find(screen) != null)
        val jump = file("jarvis-client/app/src/main/java/com/jarvis/client/ui/SettingsJump.kt")
        assertTrue("the jump list has no entry",
            jump.contains("Entry(\"Protected from Jarvis\", \"protected\")"))
        val search = file("jarvis-client/app/src/main/java/com/jarvis/client/ui/SettingsSearch.kt")
        assertTrue("the search index has no row",
            search.contains("key = \"protected\", title = \"Protected from Jarvis\""))
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

    /** A repository folder, found the same way. */
    private fun repoDir(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isDirectory) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }
}
