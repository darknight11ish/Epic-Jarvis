package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.ReplaceConfirm
import com.jarvis.client.net.decodePendingRows
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Review ruling 8.2 (2026-10-20) - the PHONE half of the two mechanical guards
 * against blind / stacked approvals.
 *
 * The owner's incident: one "approve all" click approved three backup restores,
 * two imports and a device-key registration. The cards that REPLACE what is
 * already on the PC must therefore be told apart and take a second, explicit
 * press of Approve; a single tap - or a swipe, which is the gesture people make
 * without reading - must not restore a backup (ApprovalCard's own comment says
 * how it draws and gates them).
 *
 * The gate's side is `backend/test_approval_guards.py`: it puts `replaces` on
 * every waiting row. This file holds the phone to that field, and to the
 * fallback for a PC that does not send it yet.
 */
class ReplaceConfirmTest {

    private fun item(action: String?, replaces: Boolean = false) =
        PendingItem(id = "card-1", action = action, replaces = replaces)

    @Test
    fun `the PC's own flag is what the phone reads`() {
        assertTrue(ReplaceConfirm.applies(item("send_email", replaces = true)))
        assertFalse(ReplaceConfirm.applies(item("send_email")))
    }

    @Test
    fun `the REAL action names are the fallback for an older PC`() {
        // Each one is the name the module that raises the card actually sends -
        // not the review's own wording, which had three of the four wrong. The
        // owner extended the guard on 2026-10-21 to the other irreversible
        // data-changing actions; the phone floor holds the same ten names the
        // backend marks.
        for (action in listOf(
            "restore_backup", "register_approval_key", "memory_forget_range",
            "delete_file", "delete_joplin_note", "delete_logseq_page",
            "edit_joplin_note", "edit_logseq_page", "modify_own_code",
            "app_merge_change",
        )) {
            assertTrue("$action must take the second press first", ReplaceConfirm.applies(item(action)))
        }
        assertFalse(ReplaceConfirm.applies(item("backup_restore")))
        assertFalse(ReplaceConfirm.applies(item("forget_range")))
    }

    @Test
    fun `RULING 8_1 the phone draws the PC's category words, and falls back by category`() {
        // The PC sends the category and its honest words; the phone draws them
        // unchanged. A marked row with no words falls back to its category's
        // heading, so a delete never says it overwrites a note.
        val note = item("edit_joplin_note").copy(
            replaces = true,
            replacesKind = "overwrites_note",
            replacesHeading = "OVERWRITES EXISTING NOTE",
            replacesNote = "replaces the note's current text; Jarvis keeps no copy",
        )
        assertTrue(ReplaceConfirm.applies(note))
        assertEquals("OVERWRITES EXISTING NOTE", ReplaceConfirm.heading(note))
        assertTrue(ReplaceConfirm.note(note).contains("keeps no copy"))
        assertFalse(ReplaceConfirm.heading(note).contains("DELETES"))

        val marked = item("delete_file").copy(replaces = true, replacesKind = "deletes_data")
        assertEquals("DELETES OR REPLACES DATA", ReplaceConfirm.heading(marked))

        val ordinary = item("send_email")
        assertEquals("", ReplaceConfirm.heading(ordinary))
        assertEquals("", ReplaceConfirm.note(ordinary))
    }

    @Test
    fun `a SPOOFED or absent field cannot subtract the phone's second press`() {
        // The PC's field may ADD an action; the phone floor may never remove
        // one - an explicit false or a missing field on a listed action still
        // requires the second press (the approve button only arms).
        for (action in listOf(
            "restore_backup", "register_approval_key", "memory_forget_range",
            "delete_file", "delete_joplin_note", "delete_logseq_page",
            "edit_joplin_note", "edit_logseq_page", "modify_own_code",
            "app_merge_change",
        )) {
            assertTrue("$action with explicit false", ReplaceConfirm.applies(item(action)))
            assertTrue("$action with no field", ReplaceConfirm.applies(item(action)))
        }
        assertFalse(ReplaceConfirm.applies(item("send_email")))
        assertFalse(ReplaceConfirm.applies(item("read_web_page")))
    }

    @Test
    fun `the voice-training clear needs the PC's mark, because its action is shared`() {
        // change_own_config is the action of every voice-settings card too, so
        // the name alone MUST NOT flag them.
        assertFalse(ReplaceConfirm.applies(item("change_own_config")))
        assertTrue(ReplaceConfirm.applies(item("change_own_config", replaces = true)))
    }

    @Test
    fun `a missing or unknown card is ORDINARY, never guessed`() {
        assertFalse(ReplaceConfirm.applies(null))
        assertFalse(ReplaceConfirm.applies(item(null)))
        assertFalse(ReplaceConfirm.applies(item("")))
        assertFalse(ReplaceConfirm.applies(item("send_email")))
    }

    /** Reads one production source file, the same way CardWordsContractTest does. */
    private fun source(rel: String): String {
        val candidates = listOf(
            java.io.File("src/main/java/com/jarvis/client/$rel"),
            java.io.File("app/src/main/java/com/jarvis/client/$rel"),
            java.io.File("jarvis-client/app/src/main/java/com/jarvis/client/$rel"),
        )
        val f = candidates.firstOrNull { it.isFile }
            ?: error("cannot find $rel from ${java.io.File(".").absolutePath}")
        return f.readText()
    }

    @Test
    fun `one tap never approves a state-replacing card on the phone`() {
        // The card is Compose, which this JVM test cannot draw, so the press
        // path is read as text - the same rule CardWordsContractTest uses for
        // the button order. What it proves: the approve closure arms the card
        // when it is unarmed and only calls approve() in the else branch, so a
        // single tap of the button cannot send an approval.
        val card = source("ui/approval/ApprovalCard.kt")
        val press = card.indexOf("val approvePress: () -> Unit = {")
        assertTrue("ApprovalCard has no approvePress closure", press >= 0)
        val body = card.substring(press, card.indexOf("}", card.indexOf("approve()", press)))
        assertTrue(
            "the first press must only arm the card",
            body.contains("if (replace && !replaceArmed)") &&
                body.contains("replaceArmed = true"),
        )
        assertTrue(
            "only the confirming press may call approve()",
            body.contains("} else {") && body.contains("approve()"),
        )
    }

    @Test
    fun `the swipe's approve direction is refused on a state-replacing card`() {
        // The owner's incident is a person deciding without reading; a swipe is
        // that gesture. Deny by swipe stays. Read as text because the gesture
        // detector is Compose.
        val card = source("ui/approval/ApprovalCard.kt")
        assertTrue(
            "a right swipe can still approve a state-replacing card",
            card.contains("offset.value > swipeThresholdPx && canApprove && !replace"),
        )
        assertTrue(
            "deny-by-swipe must stay available",
            card.contains("offset.value < -swipeThresholdPx && canDeny"),
        )
    }

    @Test
    fun `the word list is plain text and says the same thing as the desktop`() {
        assertEquals("REPLACES CURRENT DATA", ReplaceConfirm.WARNING)
        assertTrue(ReplaceConfirm.NOTE.length > 20)
        assertTrue(ReplaceConfirm.CONFIRM_LABEL.contains("replace"))
    }

    @Test
    fun `a row carrying replaces decodes with it, one without is ordinary`() {
        val marked = JsonObject(
            mapOf(
                "id" to kotlinx.serialization.json.JsonPrimitive("r1"),
                "action" to kotlinx.serialization.json.JsonPrimitive("restore_backup"),
                "tier" to kotlinx.serialization.json.JsonPrimitive("ask"),
                "replaces" to kotlinx.serialization.json.JsonPrimitive(true),
            )
        )
        val plain = JsonObject(
            mapOf(
                "id" to kotlinx.serialization.json.JsonPrimitive("r2"),
                "action" to kotlinx.serialization.json.JsonPrimitive("send_email"),
                "tier" to kotlinx.serialization.json.JsonPrimitive("ask"),
            )
        )
        val read = decodePendingRows(listOf(marked, plain))
        assertEquals(2, read.items.size)
        assertTrue(read.items.first { it.id == "r1" }.replaces)
        assertFalse(read.items.first { it.id == "r2" }.replaces)
    }
}
