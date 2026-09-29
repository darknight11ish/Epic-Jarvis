package com.jarvis.client

import com.jarvis.client.net.ChatHistory
import com.jarvis.client.net.ScreenLook
import com.jarvis.client.net.ScreenRules
import com.jarvis.client.net.ScreenText
import com.jarvis.client.net.ScreenText.Node
import com.jarvis.client.net.Provenance
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.Json
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Look at this" on the phone: what the assistant gesture reads, what it
 * leaves out, how long the phone holds it, and what rides with a question
 * (the owner's decision of 2026-09-28, docs/SCREEN-DESIGN.md section 3).
 * A made-up screen and a clock moved by hand - no Android, no phone.
 */
class ScreenTextTest {

    @After
    fun tidy() = ScreenLook.resetForTests()

    private fun text(s: String) = Node(text = s)

    // THE MADE-UP NAMES: nobody writes these in fixed text, so finding one
    // anywhere but the words sent to the PC can only be a leak.
    private val secretWords = "hunter2-vlorpt"

    @Test
    fun `the words are read in order, and a password field is skipped with everything in it`() {
        val screen = Node(
            children = listOf(
                text("Sign in to Zqxwarblefonk"),
                Node(text = "alice-plimberton", hint = "User name"),
                Node(
                    text = secretWords, inputType = ScreenText.TYPE_CLASS_TEXT or ScreenText.TEXT_VARIATION_PASSWORD,
                    children = listOf(text("hunter2-inside")),
                ),
                text("Sign in"),
            ),
        )
        val got = ScreenText.flatten(screen)
        assertEquals("Sign in to Zqxwarblefonk\nalice-plimberton\nSign in", got.text)
        assertEquals(1, got.skippedPasswordBoxes)
        assertFalse(got.text.contains("hunter2"))
    }

    @Test
    fun `every kind of secret field is dropped, and a doubt drops it`() {
        val kinds = listOf(
            Node(text = "a", inputType = ScreenText.TYPE_CLASS_TEXT or ScreenText.TEXT_VARIATION_VISIBLE_PASSWORD),
            Node(text = "b", inputType = ScreenText.TYPE_CLASS_TEXT or ScreenText.TEXT_VARIATION_WEB_PASSWORD),
            Node(text = "c", inputType = ScreenText.TYPE_CLASS_NUMBER or ScreenText.NUMBER_VARIATION_PASSWORD),
            Node(text = "d", autofillHints = listOf("password")),
            Node(text = "e", autofillHints = listOf("newPassword")),
            Node(text = "f", autofillHints = listOf("creditCardNumber")),
            Node(text = "g", autofillHints = listOf("creditCardSecurityCode")),
            Node(text = "h", autofillHints = listOf("smsOTPCode")),
            Node(text = "i", idName = "login_password_field"),
            Node(text = "j", hint = "Enter your passcode"),
            Node(text = "k", hint = "CVV"),
            Node(text = "l", hint = "Your PIN"),
            Node(text = "m", hint = "One-time code"),
        )
        for ((i, k) in kinds.withIndex()) {
            assertTrue("kind $i is not dropped", ScreenText.isSecretField(k))
            assertEquals("kind $i leaked", "", ScreenText.flatten(k).text)
        }
        // CONTROL: ordinary fields stay.
        val fine = listOf(
            Node(text = "x", inputType = ScreenText.TYPE_CLASS_TEXT),
            Node(text = "y", hint = "Search", idName = "search_box"),
            Node(text = "z", hint = "Pinterest boards", autofillHints = listOf("username")),
        )
        for (f in fine) assertFalse(f.toString(), ScreenText.isSecretField(f))
    }

    @Test
    fun `masked text, hidden views and a view that blocks assistance give nothing`() {
        val screen = Node(
            children = listOf(
                text("••••••"),
                text("****"),
                Node(text = "hidden words", visible = false, children = listOf(text("under hidden"))),
                Node(text = "blocked words", blocked = true, children = listOf(text("under blocked"))),
                text("plain words"),
            ),
        )
        assertEquals("plain words", ScreenText.flatten(screen).text)
    }

    @Test
    fun `the same line twice in a row is once, and blank space is tidied`() {
        val screen = Node(children = listOf(text("  Total   12  "), text("Total 12"), text("Pay"), text("Total 12")))
        assertEquals("Total 12\nPay\nTotal 12", ScreenText.flatten(screen).text)
    }

    @Test
    fun `nothing readable is empty words, not a guess`() {
        assertEquals(ScreenText.Words("", 0, 0), ScreenText.flatten(null))
        assertEquals("", ScreenText.flatten(Node()).text)
        assertEquals("", ScreenText.flattenAll(emptyList()).text)
    }

    @Test
    fun `the words are capped and it says how much was left out`() {
        val long = "word ".repeat(2000).trim()
        val got = ScreenText.flatten(text(long))
        assertTrue(got.text.length <= ScreenText.MAX_CHARS)
        assertEquals(long.length - ScreenText.MAX_CHARS, got.leftOut)
        val both = ScreenText.flattenAll(listOf(text("a".repeat(2000)), text("b".repeat(2000))))
        assertTrue(both.text.length <= ScreenText.MAX_CHARS)
        assertEquals(4001 - ScreenText.MAX_CHARS, both.leftOut)
    }

    @Test
    fun `a giant tree and a deep one stop, and never overflow`() {
        val wide = Node(children = (1..5000).map { text("line $it") })
        val got = ScreenText.flatten(wide)
        assertTrue(got.text.isNotEmpty())
        assertTrue(got.text.lines().size <= ScreenText.MAX_NODES)
        var deep: Node = text("bottom")
        repeat(500) { deep = Node(text = "level", children = listOf(deep)) }
        assertFalse(ScreenText.flatten(deep).text.contains("bottom"))
    }

    // ------------------------------------------------------------ holding it

    private var now = 1_000_000L

    private fun clockAt(t: Long) {
        now = t
        ScreenLook.clock = { now }
    }

    @Test
    fun `a look is held for two minutes of follow-ups, then it is gone`() {
        clockAt(1_000_000L)
        ScreenLook.hold("Chrome", "Zqxwarblefonk quarterly words")
        assertTrue(ScreenLook.isHeld())
        assertEquals("Looked at: Chrome screen · words only", ScreenLook.line.value)
        clockAt(1_000_000L + 60_000)
        val first = ScreenLook.forQuestion()
        assertNotNull(first)
        assertEquals("Zqxwarblefonk quarterly words", first!!.words)
        assertTrue("a follow-up gets it too", ScreenLook.isHeld())
        clockAt(1_000_000L + ScreenLook.FOLLOW_UP_MS + 1)
        assertNull(ScreenLook.forQuestion())
        assertFalse(ScreenLook.isHeld())
        assertNull("the chip goes with it", ScreenLook.line.value)
    }

    @Test
    fun `a look taken while locked waits for the unlock and is dropped after a minute`() {
        clockAt(2_000_000L)
        ScreenLook.hold("Chrome", "words", shown = false)
        clockAt(2_000_000L + 30_000)
        ScreenLook.shown()
        clockAt(2_000_000L + 90_000)
        assertTrue("shown in time: it lives its two minutes", ScreenLook.isHeld())
        ScreenLook.drop()
        clockAt(3_000_000L)
        ScreenLook.hold("Chrome", "words", shown = false)
        clockAt(3_000_000L + ScreenLook.LOCKED_WAIT_MS + 1)
        assertFalse("never shown: dropped after 60 seconds", ScreenLook.isHeld())
        assertNull(ScreenLook.forQuestion())
    }

    @Test
    fun `a Watch picture is used up by the one question it was taken for`() {
        clockAt(4_000_000L)
        ScreenLook.hold("Chrome", "", picture = "data:image/jpeg;base64,AAAA")
        assertEquals("Looked at: Chrome screen · picture goes to your PC only", ScreenLook.line.value)
        val used = ScreenLook.forQuestion()
        assertNotNull(used)
        assertEquals("data:image/jpeg;base64,AAAA", used!!.picture)
        assertNull("used up", ScreenLook.forQuestion())
        assertNull(ScreenLook.line.value)
    }

    @Test
    fun `forget it and a new look replace what was held`() {
        clockAt(5_000_000L)
        ScreenLook.hold("Chrome", "one")
        ScreenLook.hold("Maps", "two")
        assertEquals("two", ScreenLook.forQuestion()!!.words)
        ScreenLook.drop()
        assertNull(ScreenLook.forQuestion())
    }

    // ------------------------------------------------- what rides with a question

    private fun body(screen: ScreenLook.Attach?, picture: String? = null): JsonObject =
        Json.parseToJsonElement(
            ChatHistory.requestBody(
                emptyList(), ChatHistory.asking("what does this say?", Provenance.TYPED), picture, "c" + "1".repeat(31),
                screen = screen,
            ),
        ).jsonObject

    private fun newest(o: JsonObject): JsonObject = o["messages"]!!.jsonArray.last().jsonObject

    @Test
    fun `a look rides as a part of its own, after the owner's words, and nothing else changes`() {
        val h = ScreenLook.Held("Chrome", "Snorvelquist balance owed", null, 0, true, false)
        val msg = newest(body(ScreenLook.attach(h)))
        val parts: JsonArray = msg["content"]!!.jsonArray
        assertEquals(2, parts.size)
        assertEquals("text", parts[0].jsonObject["type"]!!.jsonPrimitive.content)
        assertEquals("what does this say?", parts[0].jsonObject["text"]!!.jsonPrimitive.content)
        assertEquals("screen_text", parts[1].jsonObject["type"]!!.jsonPrimitive.content)
        assertEquals("Snorvelquist balance owed", parts[1].jsonObject["text"]!!.jsonPrimitive.content)
        assertEquals("typed", msg["provenance"]!!.jsonPrimitive.content)
        assertNull("no mark on a words-only look", msg["screen"])
        assertEquals("false", body(ScreenLook.attach(h))["has_image"]!!.jsonPrimitive.content)
    }

    @Test
    fun `a Watch picture is marked as the screen's, and only its message`() {
        val h = ScreenLook.Held("Chrome", "", "data:image/jpeg;base64,AAAA", 0, true, true)
        val o = body(ScreenLook.attach(h), picture = h.picture)
        val msg = newest(o)
        assertEquals(ScreenRules.SCREEN_PHONE, msg["screen"]!!.jsonPrimitive.content)
        val parts = msg["content"]!!.jsonArray
        assertEquals("image_url", parts.last().jsonObject["type"]!!.jsonPrimitive.content)
        assertEquals("true", o["has_image"]!!.jsonPrimitive.content)
    }

    @Test
    fun `with no look the body is exactly what it was`() {
        val plain = body(null)
        val msg = newest(plain)
        assertEquals("what does this say?", msg["content"]!!.jsonPrimitive.contentOrNull)
        assertNull(msg["screen"])
    }

    @Test
    fun `a look that read nothing still says so - an empty part, not silence`() {
        val h = ScreenLook.Held("Chrome", "", null, 0, true, false)
        val parts = newest(body(ScreenLook.attach(h)))["content"]!!.jsonArray
        assertEquals("screen_text", parts[1].jsonObject["type"]!!.jsonPrimitive.content)
        assertEquals("", parts[1].jsonObject["text"]!!.jsonPrimitive.content)
    }
}
