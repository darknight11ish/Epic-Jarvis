package com.jarvis.client

import com.jarvis.client.net.CardWords
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.decodePendingRows
import com.jarvis.client.voice.CardVoice
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * One card on every screen: the same words, the same button order and the
 * same spoken lines as the desktop - held to
 * `src/test/resources/contract/card-words-cases.json`, which
 * tools/gen_card_words_cases.py makes from backend/jarvis_card_words.py and
 * the real `notice_for`. The desktop's tests/card-words.mjs reads the same
 * file, so the two apps cannot word a card differently.
 */
class CardWordsContractTest {

    private val cases: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/card-words-cases.json")) {
            "contract/card-words-cases.json is missing - run python3 tools/gen_card_words_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }

    private fun text(key: String) = cases[key]!!.jsonPrimitive.content

    private fun row(id: String, action: String, title: String?): JsonObject {
        val fields = mutableMapOf<String, kotlinx.serialization.json.JsonElement>(
            "id" to JsonPrimitive(id),
            "action" to JsonPrimitive(action),
            "tier" to JsonPrimitive("ask"),
        )
        if (title != null) {
            fields["notice"] = JsonObject(
                mapOf(
                    "title" to JsonPrimitive(title),
                    "body" to JsonPrimitive("Why. Nothing has happened yet."),
                    "weight" to JsonPrimitive("normal"),
                    "deny_ok" to JsonPrimitive(true),
                    "approve_ok" to JsonPrimitive(false),
                ),
            )
        }
        return JsonObject(fields)
    }

    @Test
    fun `the label, the button order and the no-action title are the PC's`() {
        assertEquals(text("kicker"), CardWords.KICKER)
        assertEquals(cases["buttons"]!!.jsonArray.map { it.jsonPrimitive.content }, CardWords.BUTTONS)
        assertEquals(listOf("Deny", "Approve"), CardWords.BUTTONS)
        assertEquals(text("no_action"), CardWords.NO_ACTION)
    }

    @Test
    fun `the spoken card lines are the PC's, word for word`() {
        val voice = cases["voice"]!!.jsonObject.mapValues { it.value.jsonPrimitive.content }
        assertEquals(voice, CardWords.VOICE)
        voice.values.forEach { assertTrue(it, CardVoice.isCardLine(it)) }
        assertFalse(CardVoice.isCardLine("It's on your screen."))
    }

    @Test
    fun `every action's title, as the PC serves it, is the card's title here`() {
        for (c in cases["titles"]!!.jsonArray) {
            val action = c.jsonObject["action"]!!.jsonPrimitive.content
            val title = c.jsonObject["title"]!!.jsonPrimitive.content
            val read = decodePendingRows(listOf(row("x", action, title)))
            assertEquals(action, title, read.items.single().title)
            assertFalse("a code name in $title", title.contains('_'))
        }
    }

    @Test
    fun `a row with no notice gets the PC's own fallback, as on the desktop`() {
        for (c in cases["fallback"]!!.jsonArray) {
            val action = c.jsonObject["action"]!!.jsonPrimitive.content
            val title = c.jsonObject["title"]!!.jsonPrimitive.content
            assertEquals(action, title, CardWords.fallbackTitle(action))
            val read = decodePendingRows(listOf(row("x", action, null)))
            assertEquals(action, title, read.items.single().title)
        }
    }

    @Test
    fun `a spoken question hears the same card lines as on the desktop`() {
        for (c in cases["voice_script"]!!.jsonArray) {
            val words = c.jsonObject["words"]!!.jsonArray.map { it.jsonPrimitive.content }
            val says = c.jsonObject["says"]!!.jsonArray.map { it.jsonPrimitive.content }
            val v = CardVoice()
            assertEquals(words.toString(), says, words.mapNotNull { v.onStatus(it) })
        }
        val v = CardVoice()
        v.onStatus("approval")
        v.reset()
        assertNull("a new question starts with nothing waiting", v.onStatus("approved"))
    }

    @Test
    fun `the Open the card line names the newest card and how many more`() {
        assertNull(CardWords.waiting(emptyList()))
        val read = decodePendingRows(
            listOf(
                row("old", "switch_model", "Jarvis wants to switch to a different AI model"),
                row("new", "learning_auto_enable", "Jarvis wants to turn on automatic learning"),
            ),
        ).items
        val w = CardWords.waiting(read)!!
        assertEquals("new", w.id)
        assertEquals("Jarvis wants to turn on automatic learning", w.title)
        assertEquals("and 1 more waiting", w.more)
        assertEquals("", CardWords.waiting(read.take(1))!!.more)
        assertEquals("Open the card", CardWords.OPEN_CARD)
    }

    @Test
    fun `the phone's card and widget put Deny left of Approve`() {
        // Read as text: they are Compose and Glance, which this JVM test
        // cannot draw. The order in the source IS the order on screen (a Row).
        val card = source("ui/approval/ApprovalCard.kt")
        assertTrue(card.indexOf("Refuse(CardWords.BUTTONS[0]") in 0 until card.indexOf("Affirm(CardWords.BUTTONS[1]"))
        val widget = source("widget/ApprovalWidget.kt")
        val row = widget.substring(widget.indexOf("Row(modifier = GlanceModifier.fillMaxWidth())"))
        assertTrue(row.indexOf("label = \"Deny\"") in 0 until row.indexOf("label = \"Review\""))
    }

    @Test
    fun `nothing on the phone invites a spoken yes for a card`() {
        assertFalse(source("net/Briefing.kt").contains("until you say yes"))
    }

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
}
