package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PendingItem
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The notification contract: what a waiting approval is allowed to say, and
 * what it is allowed to do to the room.
 *
 * Two things are pinned here, and they are pinned because they are the two
 * places this client deliberately does something other than the obvious thing.
 *
 * 1. The notification text comes from the desktop's generated `notice` and is
 *    not composed here. Composing it from row prose is the hole the field was
 *    added to close, and it is the fourth instance of that same mistake in
 *    this project.
 *
 * 2. `heavy` does NOT mean "make a sound" here. The desktop earns heavy by any
 *    of three things, and one of them - outside text tried to rush the reader -
 *    is set by words an attacker wrote. Honouring that one would let anyone who
 *    sends the owner an email decide whether this phone interrupts them.
 */
class NoticeRuleTest {

    private fun item(json: String): PendingItem =
        JarvisJson.decodeFromString(PendingItem.serializer(), json)

    // ------------------------------------------------------ the wire ----

    @Test
    fun `a notice on the row is read as the desktop sends it`() {
        val it = item(
            """
            {"id":"a","title":"row title","summary":"row prose",
             "notice":{"title":"Jarvis wants to send email",
                       "body":"This leaves your machine. Nothing has happened yet.",
                       "weight":"heavy","deny_ok":true,"approve_ok":false}}
            """.trimIndent(),
        )
        val n = requireNotNull(it.notice)
        assertEquals("Jarvis wants to send email", n.title)
        assertEquals("heavy", n.weight)
        assertTrue(n.denyOk)
        assertFalse("approve_ok must never arrive true, and is ignored either way", n.approveOk)
    }

    @Test
    fun `a desktop older than the contract sends no notice and that is not an error`() {
        val it = item("""{"id":"a","title":"t","summary":"s"}""")
        assertNull(it.notice)
        assertTrue("an unknown desktop must not go silent", it.shouldInterrupt)
    }

    @Test
    fun `raised still arrives as an object on a pending row`() {
        // The doorbell flattened `raised` to a boolean. The ROW did not, and
        // the in-app card reads quote and source off it. If this ever fails,
        // the card has lost the text it exists to show.
        val it = item(
            """
            {"id":"a","raised":{"code":"rush","text":"tried to hurry you",
             "quote":"ACT NOW","source":"an email from nobody@example.com"}}
            """.trimIndent(),
        )
        assertEquals("ACT NOW", requireNotNull(it.raised).quote)
    }

    @Test
    fun `an unknown field on a row is ignored rather than fatal`() {
        // The real reason the desktop could add `notice` without breaking a
        // phone that predates it, and the reason it can add the next field
        // too. Worth one test, because the day this config changes is the day
        // every older client stops reading approvals at all.
        val it = item("""{"id":"a","title":"t","a_field_invented_tomorrow":{"x":1}}""")
        assertEquals("a", it.id)
    }

    // --------------------------------------------- what makes a sound ----

    /**
     * One pending row, built by hand rather than with a raw string, because a
     * raw string nested inside a template inside another raw string is a way
     * to lose an afternoon to a quoting bug in a test fixture.
     */
    private fun row(weight: String, reversible: String, reach: String, raised: Boolean): PendingItem {
        // swipe_ok true throughout, so the swipeable assertion below proves
        // that `raised` vetoes it rather than passing on the field's default.
        val risk =
            "\"risk\":{\"reversible\":\"$reversible\",\"reach\":\"$reach\",\"swipe_ok\":true}"
        val raisedField = if (raised) ",\"raised\":{\"code\":\"rush\"}" else ""
        val notice = ",\"notice\":{\"title\":\"t\",\"body\":\"b\",\"weight\":\"$weight\"}"
        return item("{\"id\":\"a\",$risk$raisedField$notice}")
    }

    @Test
    fun `something that cannot be undone interrupts`() {
        assertTrue(row("heavy", reversible = "no", reach = "local", raised = false).shouldInterrupt)
    }

    @Test
    fun `something that leaves the desktop interrupts`() {
        assertTrue(row("heavy", reversible = "yes", reach = "outbound", raised = false).shouldInterrupt)
    }

    @Test
    fun `a raise on its own does not interrupt`() {
        // The owner's rule, and the divergence from the desktop's table. An
        // undoable, local action that is heavy ONLY because a message tried to
        // hurry the reader still posts, still says so, and still refuses every
        // quick gesture - it just does not make a sound.
        val it = row("heavy", reversible = "yes", reach = "local", raised = true)
        assertFalse("an attacker's wording must not reach the phone's volume", it.shouldInterrupt)
        assertFalse("and it is still never swipeable", it.swipeable)
    }

    @Test
    fun `a raise on top of a real reason still interrupts`() {
        // The combination, which is the one a naive "heavy and not raised"
        // check would have silenced - and it is the most dangerous row there
        // is: irreversible AND something is pushing.
        assertTrue(row("heavy", reversible = "no", reach = "outbound", raised = true).shouldInterrupt)
    }

    @Test
    fun `normal never interrupts`() {
        assertFalse(row("normal", reversible = "yes", reach = "local", raised = false).shouldInterrupt)
    }

    @Test
    fun `an unknown weight is treated as normal`() {
        assertFalse(row("URGENT!!", reversible = "yes", reach = "local", raised = false).shouldInterrupt)
    }

    @Test
    fun `weight is matched without case sensitivity`() {
        assertTrue(row("Heavy", reversible = "no", reach = "local", raised = false).shouldInterrupt)
    }
}
