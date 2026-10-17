package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.MemoryErase
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "Erased." is only true when the PC says the file was rebuilt (2026-10-16).
 *
 * `POST /api/memory/erase` erases the row, the word index and the vector, and
 * then rebuilds the file (`optimize`, VACUUM, checkpoint). The rebuild needs no
 * other program holding memory.db, and it is that last step which decides
 * whether the words are gone from the DISK rather than merely unreachable:
 * measured 2026-10-16, another connection open across the erase left 21
 * occurrences of the erased words in memory.db and its -wal, and a second
 * erase, once the reader had gone, left none.
 *
 * The backend is honest about that - it answers `file_clean: false` and puts the
 * explanation in `note` - and the phone used to print its own "Erased." and read
 * neither field, so the one case where the promise was not kept was the one case
 * the owner was told nothing about. This is the phone's half of the desktop's
 * `eraseSaid` (`jarvis-desktop/src/auto-learn.js`), and the control cases here
 * are the same ones the desktop's own test asserts
 * (`jarvis-desktop/tests/erase.mjs`): a normal erase must still say the short
 * sentence, or every erase would become alarming.
 *
 * The PC's sentence is read OUT of `backend/rebuilt/jarvis_memory.py` rather
 * than typed here, so the fixture and the server can never drift apart.
 *
 * Nothing in this file can be run in the container it was written in - there is
 * no Kotlin compiler and `dl.google.com` is blocked, so CI's client job is the
 * only compiler this has ever had. It is written to the idioms of the existing
 * `MemoryEraseTest`, which does run there.
 */
class MemoryEraseSaysWhatHappenedTest {

    private fun obj(json: String) = JarvisJson.parseToJsonElement(json) as JsonObject

    /**
     * The PC's own sentence for the case it could not finish, read out of the
     * backend. `jarvis_memory.handle_erase` builds one `note`: the short "Erased.
     * The words are gone..." and, when `file_clean` is false, a second sentence
     * saying an older copy may stay on disk.
     *
     * It is built the way the SERVER builds it, not sliced from the first word to
     * the last: the two literal groups that run when the chat was not asked about
     * (`also` false, so the middle group - "The chat it came from has also been
     * deleted." - does not run), each joined the way Python joins adjacent string
     * literals. Slicing the whole region instead would carry the `if also:` lines
     * of the source into the fixture, and a fixture that is not the sentence the
     * server sends cannot prove the sentence is what the owner is shown.
     */
    private val notCleanNote: String = run {
        val src = repoFile("backend/rebuilt/jarvis_memory.py").readText()
        // Both markers sit INSIDE a string literal, so each slice starts at the
        // OPENING quote before it: starting at the marker itself would leave the
        // literal's own closing quote first in the slice, and the pairs the join
        // reads would come out backwards (measured - it produced whitespace).
        val firstOpen = src.lastIndexOf('"', src.indexOf("Erased. The words are gone from Jarvis's memory"))
        val chat = src.indexOf("if also:", firstOpen)
        val secondOpen = src.lastIndexOf('"', src.indexOf(" Another part of Jarvis was reading", firstOpen))
        val to = src.indexOf("is erased again.", secondOpen)
        check(firstOpen > 0 && chat > firstOpen && secondOpen > chat && to > secondOpen) {
            "the PC's erase note moved - read handle_erase() in jarvis_memory.py again"
        }
        pythonJoined(src.substring(firstOpen, chat)) +
            // +1: the closing quote of that last literal has to be inside the
            // slice, or the join sees an unbalanced quote and silently drops the
            // whole final sentence (measured - the note lost its last clause).
            pythonJoined(src.substring(secondOpen, to + "is erased again.".length + 1))
    }

    /** Every `"..."` literal in `text`, joined - what Python does with adjacent
     *  string literals. */
    private fun pythonJoined(text: String): String =
        Regex("\"([^\"]*)\"").findAll(text).joinToString("") { it.groupValues[1] }

    @Test
    fun thePcsNotCleanSentenceIsTheOneTheBackendReallySends() {
        // Without this the test could pass on a sentence nobody sends.
        assertTrue(
            notCleanNote,
            notCleanNote.startsWith("Erased. The words are gone from Jarvis's memory on this PC;"),
        )
        assertTrue(
            notCleanNote,
            notCleanNote.endsWith(
                "Another part of Jarvis was reading the memory file at that moment, so it could not " +
                    "be rebuilt: an older copy of these words may stay in memory.db or memory.db-wal " +
                    "until the fact is erased again.",
            ),
        )
        // ... and it is the SENTENCE, not a slice of the source: no Python syntax,
        // and no quotes, may have come along with it.
        assertFalse(notCleanNote, notCleanNote.contains("if also"))
        assertFalse(notCleanNote, notCleanNote.contains("note +="))
        assertFalse(notCleanNote, notCleanNote.contains("\""))
        // The chat sentence is the one that must NOT be in it: this note is the
        // reply for an erase that was not asked to delete a chat.
        assertFalse(notCleanNote, notCleanNote.contains("has also been deleted"))
    }

    @Test
    fun aPcThatCouldNotRebuildTheFileSaysSoInsteadOfErased() {
        // The reply the backend really sends for that case (handle_erase).
        val reply = MemoryErase.Reply(
            200,
            obj(
                """{"ok":true,"id":5,"erased_at":1790000000.5,"already_erased":false,
                   "retired_now":true,"file_clean":false,"copies":1,"chat_deleted":false,
                   "note":"$notCleanNote"}""",
            ),
        )
        val (gone, said) = MemoryErase.said(reply)
        // The row still leaves the list: the fact IS erased, only the file could
        // not be rebuilt - the same as the desktop, which removes it either way.
        assertTrue("the fact must still leave the list", gone)
        assertEquals("the PC's own sentence, word for word", notCleanNote, said)
    }

    @Test
    fun theWorryingSentenceWinsOverTheChatSentence() {
        // The desktop's rule, and its reason: "the words may still be on disk" is
        // the more important sentence than "the chat was deleted too", so the PC's
        // note replaces both.
        val alsoChat = MemoryErase.Reply(
            200,
            obj(
                """{"ok":true,"file_clean":false,"chat_deleted":true,
                   "note":"$notCleanNote"}""",
            ),
        )
        assertEquals(notCleanNote, MemoryErase.said(alsoChat).second)
        val askedNoChat = MemoryErase.Reply(
            200,
            obj("""{"ok":true,"file_clean":false,"chat_deleted":false,"note":"$notCleanNote"}"""),
        )
        assertEquals(notCleanNote, MemoryErase.said(askedNoChat, askedChat = true).second)
    }

    @Test
    fun control_aNormalEraseStillSaysTheShortSentence() {
        // The control the whole fix rests on: it must not make every erase
        // alarming. A clean erase says exactly what it said before.
        val clean = MemoryErase.Reply(
            200,
            obj(
                """{"ok":true,"erased_at":1790000000.5,"file_clean":true,"copies":1,
                   "chat_deleted":false,"note":"Erased."}""",
            ),
        )
        assertEquals(true to MemoryErase.ERASED, MemoryErase.said(clean))
        val cleanChatGone = MemoryErase.Reply(
            200,
            obj(
                """{"ok":true,"file_clean":true,"chat_deleted":true,
                   "note":"Erased. The chat it came from has also been deleted."}""",
            ),
        )
        assertEquals(true to MemoryErase.ERASED_AND_CHAT_DELETED, MemoryErase.said(cleanChatGone))
        assertEquals(
            true to MemoryErase.ERASED_NO_CHAT,
            MemoryErase.said(clean, askedChat = true),
        )
    }

    @Test
    fun control_aPcTooOldToSendTheFieldAnswersExactlyAsBefore() {
        // Every fixture in the older test carries file_clean; this one does not,
        // which is what an older PC's reply looks like.
        val old = MemoryErase.Reply(
            200,
            obj("""{"ok":true,"erased_at":1790000000.5,"already_erased":false,"note":"Erased."}"""),
        )
        assertEquals(true to MemoryErase.ERASED, MemoryErase.said(old))
        assertEquals(true to MemoryErase.ERASED_NO_CHAT, MemoryErase.said(old, askedChat = true))
        // No body at all is not a reason to say less.
        assertEquals(true to MemoryErase.ERASED, MemoryErase.said(MemoryErase.Reply(200, null)))
    }

    @Test
    fun aFalseFlagWithNothingToSayMustNotBlankTheMessageOut() {
        for (blank in listOf("", "   ")) {
            val silent = MemoryErase.Reply(
                200,
                obj("""{"ok":true,"file_clean":false,"note":"$blank"}"""),
            )
            assertEquals("blank note: $blank", MemoryErase.ERASED, MemoryErase.said(silent).second)
        }
        // A string is not a flag: "false" in quotes is not the boolean false, the
        // same way the desktop's `reply.file_clean === false` refuses a string.
        val stringy = MemoryErase.Reply(
            200,
            obj("""{"ok":true,"file_clean":"false","note":"$notCleanNote"}"""),
        )
        assertEquals(MemoryErase.ERASED, MemoryErase.said(stringy).second)
    }

    @Test
    fun aFailedEraseStillNeverReadsAsErased() {
        // The neighbouring rule, kept: a 200 that says ok:false is not an erase.
        val refused = MemoryErase.Reply(
            200,
            obj("""{"ok":false,"file_clean":false,"note":"$notCleanNote","error":"something broke"}"""),
        )
        val (gone, said) = MemoryErase.said(refused)
        assertFalse(gone)
        assertEquals("Not erased. Something broke.", said)
    }

    @Test
    fun thePhoneReadsTheTwoFieldsItUsedToIgnore() {
        // A source pin so the wiring cannot be quietly removed again: `said` must
        // go through eraseSaid, and eraseSaid must read `note` and `file_clean`.
        val src = repoFile(
            "jarvis-client/app/src/main/java/com/jarvis/client/net/MemoryErase.kt",
        ).readText()
        assertTrue(src, src.contains("true to eraseSaid(reply, when {"))
        assertTrue(src, src.contains("val note = reply.body?.text(\"note\") ?: \"\""))
        assertTrue(src, src.contains("reply.body?.flag(\"file_clean\") == false"))
        // And the desktop's copy is the one it has to agree with.
        val desktop = repoFile("jarvis-desktop/src/auto-learn.js").readText()
        assertTrue(
            "the desktop's eraseSaid is the rule this mirrors (PR #493)",
            desktop.contains("export function eraseSaid(reply, normal)"),
        )
        assertTrue(
            "the desktop reads the same two fields",
            desktop.contains("reply.file_clean === false && note"),
        )
    }

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }
}
