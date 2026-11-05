package com.jarvis.client

import com.jarvis.client.net.SmsSend
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Writing a text message for the owner: the name lookup, the refusals, and the
 * one rule that cannot be taken back - never to the wrong person.
 *
 * The owner's own words (2026-11-04): "in hands-free mode ... Jarvis to WRITE
 * TEXT MESSAGES to contacts for me." The PC names the person; THIS phone turns
 * that into a number. Every branch below is a case where that could go to the
 * wrong place, and every one of them refuses instead.
 */
class SmsSendTest {

    private fun book(vararg rows: Pair<String, String>) =
        rows.map { SmsSend.Contact(it.first, it.second) }

    @Test
    fun `an exact name with one number resolves to that number`() {
        val resolved = SmsSend.resolve(
            "Alex",
            book("Alex" to "07700 900123", "Sam" to "07700 900456"),
        )
        assertEquals(SmsSend.Resolved.One("07700900123", "Alex"), resolved)
    }

    @Test
    fun `case and spacing are folded, and nothing else is`() {
        val rows = book("Alex  Smith" to "+44 7700 900123")
        assertEquals(
            SmsSend.Resolved.One("+447700900123", "Alex  Smith"),
            SmsSend.resolve("  alex smith ", rows),
        )
        // Not a prefix match, and not a substring match: "Alex" must not find
        // "Alexandra", which is a different person with a different phone.
        assertEquals(
            SmsSend.Resolved.NotFound,
            SmsSend.resolve("Alex", book("Alexandra" to "07700 900123")),
        )
    }

    @Test
    fun `two numbers for one name is a refusal, and says how many`() {
        val rows = book("Alex" to "07700 900123", "Alex" to "07700 900999")
        assertEquals(SmsSend.Resolved.Ambiguous(2), SmsSend.resolve("Alex", rows))
        assertEquals(SmsSend.AMBIGUOUS, SmsSend.refusedSentence(SmsSend.resolve("Alex", rows)))
    }

    @Test
    fun `the same number twice is one match - one place to send to`() {
        val rows = book("Alex" to "07700 900123", "Alex" to "07700900123")
        assertEquals(SmsSend.Resolved.One("07700900123", "Alex"), SmsSend.resolve("Alex", rows))
    }

    @Test
    fun `a name nobody has is a refusal, and so is no name at all`() {
        val rows = book("Sam" to "07700 900456")
        assertEquals(SmsSend.Resolved.NotFound, SmsSend.resolve("Alex", rows))
        assertEquals(SmsSend.NOT_FOUND, SmsSend.refusedSentence(SmsSend.Resolved.NotFound))
        assertEquals(SmsSend.Resolved.NoName, SmsSend.resolve("   ", rows))
        assertEquals(SmsSend.NO_NAME, SmsSend.refusedSentence(SmsSend.Resolved.NoName))
    }

    @Test
    fun `a row with no number is not a number to send to`() {
        val rows = book("Alex" to "", "Alex" to "  ")
        assertEquals(SmsSend.Resolved.NotFound, SmsSend.resolve("Alex", rows))
    }

    @Test
    fun `a number the owner said is used as it is, with no address book at all`() {
        assertEquals(
            SmsSend.Resolved.One("07700900321", "07700 900321"),
            SmsSend.resolve("07700 900321", emptyList()),
        )
        assertEquals(
            SmsSend.Resolved.One("+447700900321", "+44 7700 900321"),
            SmsSend.resolve("+44 7700 900321", emptyList()),
        )
        // "00" is the other way of writing "+", and only that prefix changes.
        assertEquals(
            SmsSend.Resolved.One("+447700900321", "0044 7700 900321"),
            SmsSend.resolve("0044 7700 900321", emptyList()),
        )
        assertFalse("a number needs no address book", SmsSend.needsContacts("07700 900321"))
        assertTrue("a name does", SmsSend.needsContacts("Alex"))
    }

    @Test
    fun `a short run of digits is still a name, not a number`() {
        // "Room 12" and "Alex 2" are names: five digits is the floor, which is
        // also what keeps "911" from being dialled by accident.
        assertTrue(SmsSend.needsContacts("Room 12"))
        assertTrue(SmsSend.needsContacts("Alex 2"))
        assertTrue(SmsSend.needsContacts("911"))
        assertEquals(SmsSend.Resolved.NoName, SmsSend.resolve("", book("Alex" to "07700 900123")))
    }

    @Test
    fun `nothing is sent without the link, the SMS permission or the address book`() {
        assertNull("all present", SmsSend.gate(hasSmsPermission = true, hasContactsPermission = true, connected = true))
        // The PC is unreachable: a message with no PC behind it is not
        // hands-free mode, and its result could not be reported either.
        assertEquals(
            SmsSend.NO_LINK,
            SmsSend.gate(hasSmsPermission = true, hasContactsPermission = true, connected = false),
        )
        assertEquals(
            SmsSend.NO_PERMISSION,
            SmsSend.gate(hasSmsPermission = false, hasContactsPermission = true, connected = true),
        )
        assertEquals(
            SmsSend.NO_CONTACTS_PERMISSION,
            SmsSend.gate(hasSmsPermission = true, hasContactsPermission = false, connected = true),
        )
        // The link is checked FIRST: "is your PC reachable" is the question the
        // owner can act on, and the permissions are this phone's own.
        assertEquals(
            SmsSend.NO_LINK,
            SmsSend.gate(hasSmsPermission = false, hasContactsPermission = false, connected = false),
        )
    }

    @Test
    fun `never claims sent without the platform's own result`() {
        assertEquals("sms_sent:RESULT_OK", SmsSend.RECEIPT_SENT)
        assertEquals("sms_sent:not_attempted", SmsSend.RECEIPT_REFUSED)
        assertEquals("sms_sent:RESULT_1", SmsSend.receiptFailed(1))
        assertFalse("a refused send is not a success token", SmsSend.RECEIPT_REFUSED.contains("OK"))
        // Every failure sentence is a sentence, and none of them says "sent".
        for (code in listOf(1, 2, 3, 4, -2, 99)) {
            val why = SmsSend.sendFailure(code)
            assertTrue(why.isNotBlank())
            assertFalse("code $code claims a send: $why", why.contains("was sent", ignoreCase = false))
        }
    }

    @Test
    fun `the notification names the contact and a short version of the words`() {
        val long = "Hello Alex, I am running about ten minutes late, see you at the cafe on the corner"
        val short = SmsSend.shortText(long, max = 30)
        assertTrue(short.length <= 30)
        assertTrue("it says it was cut", short.endsWith("…"))
        // The line names the person and the words, and is one line.
        val line = SmsSend.sentLine("Alex", long)
        assertTrue(line.startsWith("Sent to Alex: \""))
        assertFalse(line.contains("\n"))
        val failed = SmsSend.failedLine("Alex", SmsSend.AMBIGUOUS)
        assertTrue(failed.startsWith("Not sent to Alex: "))
        assertFalse("a refusal never claims a send", failed.startsWith("Sent"))
    }
}
