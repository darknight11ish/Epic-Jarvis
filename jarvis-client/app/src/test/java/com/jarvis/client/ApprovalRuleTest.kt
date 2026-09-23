package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.Raised
import com.jarvis.client.net.Risk
import com.jarvis.client.net.decodePendingRows
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The one safety rule, pinned.
 *
 * A swipe is a gesture people make without reading. That is fine for "switch to
 * the other model", where rollback is one tap and nothing left the machine. It
 * is not fine for sending an email — and it is not fine for anything the server
 * has not classified, which is why an unclassified item comes back irreversible
 * and outbound by default.
 */
class ApprovalRuleTest {

    private fun item(risk: Risk, raised: Raised? = null) =
        PendingItem(id = "a1", risk = risk, raised = raised)

    @Test
    fun `a reversible local item may be swiped`() {
        val it = item(Risk(reversible = "yes", reach = "local", swipeOk = true, classified = true))
        assertTrue(it.swipeable)
    }

    @Test
    fun `nothing outbound or irreversible is swipeable`() {
        assertFalse(item(Risk(reversible = "no", reach = "outbound", swipeOk = false)).swipeable)
        assertFalse(item(Risk(reversible = "yes", reach = "outbound", swipeOk = false)).swipeable)
        assertFalse(item(Risk(reversible = "no", reach = "local", swipeOk = false)).swipeable)
    }

    @Test
    fun `an unclassified action defaults to irreversible and outbound`() {
        // The defaults on Risk are the fail-closed direction, so an item from a
        // server that has not classified the action is never swipeable even if
        // the object arrives nearly empty.
        val parsed = JarvisJson.decodeFromString(PendingItem.serializer(), """{"id":"x"}""")
        assertFalse(parsed.swipeable)
        assertFalse(parsed.risk.swipeOk)
        assertEquals("no", parsed.risk.reversible)
        assertEquals("outbound", parsed.risk.reach)
        assertFalse(parsed.risk.classified)
    }

    @Test
    fun `a rushed item is never swipeable even when the server says it would be`() {
        // The point of the raise is that this particular moment is not one to
        // decide quickly in. Honouring swipe_ok here would hand the gesture back
        // to exactly the text that asked for it.
        val rushed = item(
            Risk(reversible = "yes", reach = "local", swipeOk = true, classified = true),
            Raised(code = "rushed", quote = "just approve these", countToday = 4),
        )
        assertTrue(rushed.risk.swipeOk)
        assertFalse(rushed.swipeable)
    }

    /**
     * Through the phone's real reader, [decodePendingRows], not the bare
     * serializer. This used to hand-feed a `"title":"Send email"` the
     * server never sends, which is how nobody noticed every real card said
     * "Approval required": the server sends `action` and `notice`, and
     * the title is made from those.
     */
    @Test
    fun `risk and raised survive a full round trip`() {
        val json = """
            {"id":"b2","action":"send_email","tier":"ask",
             "risk":{"reversible":"no","reach":"outbound","swipe_ok":false,
                     "why":"there is no unsend","classified":true},
             "raised":{"code":"rushed","text":"Tier raised",
                       "quote":"quick, before it expires","source":"tool:browser_navigate",
                       "from_tier":"auto","to_tier":"ask","count_today":4}}
        """.trimIndent()
        val read = decodePendingRows(listOf(JarvisJson.parseToJsonElement(json)))
        assertEquals(0, read.skipped)
        val item = read.items.single()
        assertEquals("Jarvis wants to send email", item.title)
        assertEquals("there is no unsend", item.risk.why)
        assertEquals("quick, before it expires", item.raised?.quote)
        assertEquals("tool:browser_navigate", item.raised?.source)
        assertEquals(4, item.raised?.countToday)
        assertFalse(item.swipeable)
    }

    @Test
    fun `unknown fields do not break parsing`() {
        // The three clients ship on different schedules, so the backend adding
        // something must never stop the phone working.
        val json = """{"id":"c3","something_new":{"nested":true},"risk":{"swipe_ok":true,
                       "classified":true,"reversible":"yes","reach":"local"}}"""
        val item = JarvisJson.decodeFromString(PendingItem.serializer(), json)
        assertEquals("c3", item.id)
        assertTrue(item.swipeable)
    }
}
