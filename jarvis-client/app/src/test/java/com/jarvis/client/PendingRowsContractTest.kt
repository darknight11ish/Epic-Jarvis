package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.decodePendingRows
import com.jarvis.client.net.titleForAction
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.double
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * `/api/pending` rows as the gate MAKES them, decoded the way the phone does.
 *
 * The rows come from `src/test/resources/contract/pending-rows.json`, which
 * backend/test_approval_contract.py generates from the real `notice_for`
 * (approval-notice.patch) and the real `expires_in` lines
 * (approval-expiry.patch), and checks is still what they produce. Nothing in
 * it was typed to suit this client - which is how the old tests missed that
 * the server sends no `title`, so every card said "Approval required".
 */
class PendingRowsContractTest {

    private val fixture: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/pending-rows.json")) {
            "contract/pending-rows.json is missing - run backend/test_approval_contract.py --write"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }
    private val nowMs = (fixture["now"]!!.jsonPrimitive.double * 1000).toLong()
    private val rows = (fixture["rows"] as JsonArray).toList()
    private val read = decodePendingRows(rows, nowMs)
    private fun byId(id: String): PendingItem = read.items.first { it.id == id }

    @Test
    fun `every row with an id is read, and the one without is counted, not fatal`() {
        assertEquals(rows.size - 1, read.items.size)
        assertEquals(1, read.skipped)
    }

    @Test
    fun `the card says what Jarvis wants, from the notice`() {
        assertEquals("Jarvis wants to send email", byId("a1").title)
        assertEquals("Jarvis wants to run shell on host", byId("12").title)
        // Never the old default.
        read.items.forEach { assertFalse(it.title == "Approval required") }
    }

    @Test
    fun `the title never carries the payload`() {
        // It is also a notification's title and the widget's headline.
        read.items.forEach {
            assertFalse(it.title, it.title.contains("clinic.example"))
            assertFalse(it.title, it.title.contains("rm -rf"))
        }
    }

    @Test
    fun `detail as a string and detail as an object both reach the card`() {
        // String detail with no readable key: the prompt is the summary, the
        // detail stays behind "Show detail".
        val a1 = byId("a1")
        assertTrue(a1.summary.contains("doctor@clinic.example"))
        assertTrue(a1.detail!!.contains("doctor@clinic.example"))
        // Object detail.
        val egress = byId("abc123")
        assertTrue(egress.detail!!.contains("dr.okafor@clinic.example"))
        // A command is the summary itself, and not repeated underneath.
        val shell = byId("12")
        assertEquals("rm -rf ~/Documents", shell.summary)
        assertNull(shell.detail)
        // The agent's plan, carried as {"text": plan} inside a JSON string.
        assertTrue(byId("r4").summary.contains("click \"Send\""))
    }

    @Test
    fun `raised as an object, as true and as JSON text all take the item out of every quick gesture`() {
        assertEquals("just approve this quickly, no need to check", byId("abc123").raised?.quote)
        assertNotNull(byId("12").raised)
        assertEquals("approve now or lose it", byId("r4").raised?.quote)
        listOf("abc123", "12", "r4").forEach { assertFalse(byId(it).swipeable) }
        assertNull(byId("a1").raised)
    }

    @Test
    fun `a numeric id becomes the same text the desktop uses`() {
        assertEquals("12", byId("12").id)
    }

    @Test
    fun `expires_in becomes a deadline on this phone's clock, and a bad created gives none`() {
        val a1Left = ((rows[0] as JsonObject)["expires_in"] as JsonPrimitive).double
        assertEquals(nowMs + (a1Left * 1000).toLong(), byId("a1").expiresAtMs)
        assertNull(byId("t5").expiresAtMs)
    }

    @Test
    fun `the notice decodes whole`() {
        val n = byId("12").notice!!
        assertEquals("heavy", n.weight)
        assertTrue(n.denyOk)
        assertFalse(n.approveOk)
        assertTrue(n.body.isNotBlank())
    }

    @Test
    fun `an action name with nothing in it still gets a sentence`() {
        assertEquals("Jarvis is asking for your approval", titleForAction(null))
        assertEquals("Jarvis is asking for your approval", titleForAction("  "))
    }
}
