package com.jarvis.client

import com.jarvis.client.net.NoteCapture
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * `#log`, `#obs`, `#joplin` ... at the start of a chat line file a note
 * instead of asking Jarvis - the same prefixes, and the same decisions, as the
 * desktop's quickbar (`jarvis-desktop/src/main.js`, `NOTE_PREFIXES`,
 * `parseNotePrefix`, `fileFromBar`).
 */
class NotePrefixTest {

    private val all = NoteCapture.Targets.Known(listOf("logseq", "joplin", "obsidian"))
    private val logseqOnly = NoteCapture.Targets.Known(listOf("logseq"))

    @Test
    fun eachPrefixFilesInTheDesktopsApp() {
        assertEquals(NoteCapture.Prefixed("logseq", "buy milk"), NoteCapture.prefixed("#log buy milk"))
        assertEquals("logseq", NoteCapture.prefixed("#journal x")!!.target)
        assertEquals("joplin", NoteCapture.prefixed("#jop x")!!.target)
        assertEquals("joplin", NoteCapture.prefixed("#joplin x")!!.target)
        // "#vault" is Obsidian's since 2026-09-24, on the desktop and in the backend.
        assertEquals("obsidian", NoteCapture.prefixed("#vault x")!!.target)
        assertEquals("obsidian", NoteCapture.prefixed("#obs x")!!.target)
        assertEquals("obsidian", NoteCapture.prefixed("#daily x")!!.target)
    }

    @Test
    fun casesAndLeadingSpaceDoNotMatterButTheWordMust() {
        assertEquals(NoteCapture.Prefixed("obsidian", "Idea"), NoteCapture.prefixed("  #OBS Idea"))
        // The prefix must be a word of its own: "#logbook" is a question.
        assertNull(NoteCapture.prefixed("#logbook entry"))
        // Not at the start: a question that mentions a tag.
        assertNull(NoteCapture.prefixed("what is #log for?"))
        // An unknown tag is a question too.
        assertNull(NoteCapture.prefixed("#todo call mum"))
        assertNull(NoteCapture.prefixed("plain question"))
    }

    @Test
    fun theBodyKeepsItsLinesAndAPrefixAloneIsEmpty() {
        assertEquals("line one\nline two", NoteCapture.prefixed("#log line one\nline two")!!.body)
        assertEquals("", NoteCapture.prefixed("#joplin")!!.body)
    }

    @Test
    fun aSetUpAppGetsTheNoteTrimmed() {
        val p = NoteCapture.prefixed("#log   buy milk  ")!!
        assertEquals(NoteCapture.ChatNote.File("logseq", "buy milk"), NoteCapture.chatNote(p, all))
    }

    @Test
    fun anAppThePcSaidIsNotSetUpIsRefusedWithTheDesktopsWords() {
        val p = NoteCapture.prefixed("#obs idea")!!
        val said = NoteCapture.chatNote(p, logseqOnly) as NoteCapture.ChatNote.NotFiled
        assertEquals(
            "Obsidian isn't set up on your PC, so nothing was filed. " +
                "Set [notes.obsidian] vault_directory in jarvis-framework.toml (docs/INSTALL.md, Notes).",
            said.why,
        )
    }

    @Test
    fun whenThePcCouldNotBeAskedTheNoteIsSentAndThePcDecides() {
        val p = NoteCapture.prefixed("#joplin hello")!!
        assertEquals(
            NoteCapture.ChatNote.File("joplin", "hello"),
            NoteCapture.chatNote(p, NoteCapture.Targets.Unknown("timed out")),
        )
    }

    @Test
    fun anEmptyNoteIsRefused() {
        val p = NoteCapture.prefixed("#log   ")!!
        assertEquals(
            NoteCapture.ChatNote.NotFiled(NoteCapture.NOTHING_TO_FILE),
            NoteCapture.chatNote(p, all),
        )
    }

    @Test
    fun theChipSaysWhereItGoesAndOnlySaysNotSetUpWhenThePcSaidSo() {
        assertNull(NoteCapture.chip("a question", all))
        assertTrue(NoteCapture.chip("#log x", all)!!.startsWith("Logseq Journal:"))
        assertTrue(NoteCapture.chip("#obs x", logseqOnly)!!.contains("not set up"))
        assertTrue(!NoteCapture.chip("#obs x", null)!!.contains("not set up"))
    }

    @Test
    fun onlyAppsThatAreSetUpAreOffered() {
        assertEquals(listOf("#log"), NoteCapture.primer(logseqOnly).map { it.first })
        assertEquals(listOf("#log", "#joplin", "#obs"), NoteCapture.primer(all).map { it.first })
        assertTrue(NoteCapture.primer(NoteCapture.Targets.Unknown("no")).isEmpty())
        assertTrue(NoteCapture.primer(null).isEmpty())
        assertTrue(NoteCapture.primer(NoteCapture.Targets.Known(emptyList())).isEmpty())
    }

    /** Walks up from Gradle's working folder (`jarvis-client/app`) to the repository. */
    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    /** The phone's table is the desktop's table - read from main.js, not copied into this test. */
    @Test
    fun thePrefixesAreTheDesktopsExactly() {
        val js = repoFile("jarvis-desktop/src/main.js").readText()
        val block = js.substringAfter("const NOTE_PREFIXES = {").substringBefore("};")
        val desktop = Regex(""""(#[a-z]+)":\s*\{\s*target:\s*"([a-z]+)"""")
            .findAll(block).associate { it.groupValues[1] to it.groupValues[2] }
        assertTrue("found the desktop's table", desktop.size >= 9)
        assertEquals(desktop, NoteCapture.PREFIXES)
    }

    /** And every prefix lands where the backend itself would send its name. */
    @Test
    fun theBackendAgreesWithEveryAlias() {
        val py = repoFile("backend/jarvis_note_capture.py").readText()
        val block = py.substringAfter("_ALIASES = {").substringBefore("}")
        val aliases = Regex(""""([a-z]+)":\s*"([a-z]+)"""").findAll(block)
            .associate { it.groupValues[1] to it.groupValues[2] }
        assertTrue("found the backend's aliases", aliases.isNotEmpty())
        for ((prefix, target) in NoteCapture.PREFIXES) {
            val word = prefix.removePrefix("#")
            assertEquals("$prefix", target, aliases[word] ?: word)
        }
    }
}
