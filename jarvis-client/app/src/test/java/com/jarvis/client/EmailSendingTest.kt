package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.EmailSending
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.decodePendingRows
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Sending email on the phone (the owner's decision of 2026-09-25), read from
 * what the PC REALLY answers.
 *
 * `contract/email-sending-cases.json` is the real `GET /api/email/sending`
 * answer (jarvis_email_send.view()) in named situations and one real email
 * card (describe()), written by tools/gen_email_sending_cases.py - byte for
 * byte the file the desktop builds against.
 */
class EmailSendingTest {

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/email-sending-cases.json")) {
            "contract/email-sending-cases.json is missing - run tools/gen_email_sending_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }
    private val cases = doc["cases"]!!.jsonObject
    private val card = doc["example_card"]!!.jsonPrimitive.content

    @Test
    fun `every real answer is shown in the PC's own words`() {
        assertTrue(cases.size >= 5)
        for ((name, body) in cases) {
            val v = requireNotNull(EmailSending.parse(body.jsonObject)) { "$name did not parse" }
            assertEquals(name, body.jsonObject["said"]!!.jsonPrimitive.content, v.said)
            assertEquals(name, body.jsonObject["ready"]!!.jsonPrimitive.content == "true", v.ready)
        }
        assertTrue(EmailSending.parse(cases["ready"]!!.jsonObject)!!.ready)
        assertFalse(EmailSending.parse(cases["tool_off"]!!.jsonObject)!!.ready)
    }

    @Test
    fun `the line never carries a password`() {
        for ((name, body) in cases) {
            val o = body.jsonObject
            assertNull(name, o["password"])
            // Only whether one is set.
            assertTrue(name, o["password_set"] is JsonPrimitive)
        }
    }

    @Test
    fun `a PC without it says so`() {
        val missing = doc["missing"]!!.jsonObject["body"]!!.jsonObject
        assertNull(EmailSending.parse(missing))
        assertTrue(EmailSending.missing(ApiError.NotFound))
        assertTrue(EmailSending.missing(ApiError.NotAvailable))
        assertFalse(EmailSending.missing(ApiError.BadToken))
        assertTrue(EmailSending.MISSING.contains("apply-patches.ps1"))
    }

    @Test
    fun `an email's card is shown in full, and its title names no one`() {
        val row = buildJsonObject {
            put("id", "e1")
            put("action", EmailSending.ACTION)
            put("tier", "ask")
            put("created", 1.0)
            put("detail", buildJsonObject { put("text", card) }.toString())
            put("prompt", "tool send_email {...}")
            put("notice", buildJsonObject {
                put("title", "Jarvis wants to send email")
                put("body", "sends the email shown on the card from your own account, to exactly " +
                    "the people it lists; once sent it cannot be taken back. nothing has happened yet.")
                put("weight", "heavy")
                put("deny_ok", true)
                put("approve_ok", false)
            })
        }
        val item = decodePendingRows(listOf(row), 1_000L).items.single()
        // Every word the PC put on the card - the whole email, To and Cc,
        // the markdown-looking text as written - in what the card shows.
        assertEquals(card, item.summary)
        assertTrue(item.summary.contains(doc["example_body"]!!.jsonPrimitive.content))
        assertTrue(item.summary.contains("To: alex@example.com"))
        // The title - also a notification's - is the notice's, from the
        // action alone: no recipient, subject or word of the email.
        assertEquals("Jarvis wants to send email", item.title)
        val notice = assertNotNullAndGet(item.notice)
        for (secret in listOf("alex@example.com", "sam@example.org", "Dinner", "Friday at 7")) {
            assertFalse(secret, item.title.contains(secret))
            assertFalse(secret, notice.title.contains(secret) || notice.body.contains(secret))
        }
        assertFalse(notice.approveOk)
    }

    private fun <T> assertNotNullAndGet(value: T?): T {
        assertNotNull(value)
        return value!!
    }
}
