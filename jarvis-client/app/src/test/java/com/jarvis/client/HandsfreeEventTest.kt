package com.jarvis.client

import com.jarvis.client.net.Handsfree
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The frozen contract, read from the wire: the two events, the four routes'
 * bodies and answers, every line of plain words, and the honest degradation
 * against a PC that has never heard of hands-free.
 *
 * net/Handsfree.kt is pure, so all of it is held here: a `handsfree_card` with
 * no id is dropped (an answer to it could not be posted), an unknown event kind
 * is silently ignored (the stream carries kinds this app does not know), the
 * 202/200 split of `/api/handsfree/enabled` becomes words, and a 404 becomes
 * "not available on this PC yet" rather than a mode that looks broken.
 */
class HandsfreeEventTest {

    private fun obj(json: String): JsonObject =
        JarvisJson.parseToJsonElement(json) as JsonObject

    // ------------------------------------------------------------- events ----

    @Test
    fun `a handsfree_card is read into the card the flow answers against`() {
        val arrived = Handsfree.arrival(
            Handsfree.EVENT_CARD,
            obj(
                """{"card_id":"card-7","action":"models_switch",
                   "say":"Jarvis wants to switch the model.","expires_in_sec":90}""",
            ),
        )
        assertEquals(
            Handsfree.Arrival.CardArrived(
                Handsfree.Card(
                    cardId = "card-7",
                    action = "models_switch",
                    say = "Jarvis wants to switch the model.",
                    expiresInSec = 90,
                ),
            ),
            arrived,
        )
        assertTrue((arrived as Handsfree.Arrival.CardArrived).card.answerable)
    }

    @Test
    fun `a card with no id is dropped - it could not be answered`() {
        assertNull(Handsfree.arrival(Handsfree.EVENT_CARD, obj("""{"action":"x","say":"y"}""")))
        assertNull(Handsfree.arrival(Handsfree.EVENT_CARD, obj("""{"card_id":"","say":"y"}""")))
        // ...and neither is a card that is not an object at all.
        assertNull(Handsfree.arrival(Handsfree.EVENT_CARD, null))
        assertNull(
            Handsfree.arrival(
                Handsfree.EVENT_CARD,
                JarvisJson.parseToJsonElement("\"just a string\""),
            ),
        )
    }

    @Test
    fun `a phone_command is read, and an unknown kind is KEPT so it can be answered`() {
        val arrived = Handsfree.arrival(
            Handsfree.EVENT_COMMAND,
            obj("""{"id":"cmd-1","kind":"send_sms","contact":"Alex","text":"Running late"}"""),
        )
        assertEquals(
            Handsfree.Arrival.CommandArrived(
                Handsfree.Command(id = "cmd-1", kind = "send_sms", contact = "Alex", text = "Running late"),
            ),
            arrived,
        )
        val unknown = Handsfree.arrival(
            Handsfree.EVENT_COMMAND,
            obj("""{"id":"cmd-2","kind":"make_coffee","contact":"","text":""}"""),
        ) as Handsfree.Arrival.CommandArrived
        assertEquals("make_coffee", unknown.command.kind)
        assertTrue("and it is still answerable, so the PC hears back", unknown.command.answerable)
        // But no id at all means there is nothing to report against.
        assertNull(Handsfree.arrival(Handsfree.EVENT_COMMAND, obj("""{"kind":"send_sms"}""")))
    }

    @Test
    fun `unknown events are ignored, and so is a kind this app has never heard of`() {
        assertNull(Handsfree.arrival("approval", obj("""{"id":"a1"}""")))
        assertNull(Handsfree.arrival("", obj("{}")))
        assertNull(Handsfree.arrival("phone_command", obj("""{"kind":"send_sms"}""")))
        // The two this feature owns, and only those.
        assertEquals(Handsfree.EVENT_CARD, "handsfree_card")
        assertEquals(Handsfree.EVENT_COMMAND, "phone_command")
    }

    // -------------------------------------------------------------- reads ----

    @Test
    fun `the state read accepts the project's own alias for enabled`() {
        assertEquals(true, Handsfree.readOf(obj("""{"enabled":true}""")).enabled)
        assertEquals(true, Handsfree.readOf(obj("""{"on":true}""")).enabled)
        assertEquals(false, Handsfree.readOf(obj("""{"enabled":false}""")).enabled)
        // Nothing said is nothing claimed.
        assertEquals(false, Handsfree.readOf(obj("{}")).enabled)
        assertEquals(true, Handsfree.readOf(obj("{}")).available)
    }

    @Test
    fun `a state that says it is unavailable is believed, and carries the PC's sentence`() {
        val read = Handsfree.readOf(
            obj("""{"available":false,"why":"Hands-free is off on this PC."}"""),
        )
        assertFalse(read.available)
        assertEquals("Hands-free is off on this PC.", read.why)
        // No body at all is the same answer: nothing is available, nothing ran.
        assertFalse(Handsfree.readOf(null).available)
        assertFalse(Handsfree.readOf(null).enabled)
    }

    @Test
    fun `a card already waiting is read out of the state, top-level or nested`() {
        val top = Handsfree.readOf(
            obj("""{"enabled":true,"card_id":"c1","action":"models_switch","say":"Say this"}"""),
        )
        assertEquals("c1", top.card?.cardId)
        val nested = Handsfree.readOf(
            obj("""{"enabled":true,"card":{"card_id":"c2","say":"Nested","expires_in_sec":5}}"""),
        )
        assertEquals("c2", nested.card?.cardId)
        assertEquals(5, nested.card?.expiresInSec)
        assertNull(Handsfree.readOf(obj("""{"enabled":true}""")).card)
    }

    // ------------------------------------------------------------- switch ----

    @Test
    fun `202 is a card waiting, never the mode being on, and 200 with a reason is still an answer`() {
        val waiting = Handsfree.Enabled.of(202, obj("""{"card_id":"c1"}"""))
        assertTrue(waiting.waiting)
        assertEquals("c1", waiting.cardId)

        val immediate = Handsfree.Enabled.of(200, null)
        assertFalse(immediate.waiting)

        val refused = Handsfree.Enabled.of(409, obj("""{"why":"A card is already waiting."}"""))
        assertEquals("A card is already waiting.", refused.why)
    }

    // ------------------------------------------------------------- answer ----

    @Test
    fun `the PC's answer is read, and an absent ok is not a refusal`() {
        val a = Handsfree.answerOf(
            obj("""{"ok":true,"heard":"yes","decision":"approved","card_state":"approved"}"""),
        )
        assertTrue(a.ok)
        assertEquals("yes", a.heard)
        assertEquals("approved", a.decision)
        assertEquals("approved", a.cardState)

        assertTrue("a body with the four fields and no ok still heard something", Handsfree.answerOf(
            obj("""{"heard":"yes","decision":"approved"}"""),
        ).ok)

        val refused = Handsfree.answerOf(obj("""{"ok":false,"why":"Not your voice."}"""))
        assertFalse(refused.ok)
        assertEquals("Not your voice.", refused.why)
    }

    @Test
    fun `every answer becomes one plain sentence, and never an invented decision`() {
        fun words(json: String) = Handsfree.answerWords(Handsfree.answerOf(obj(json)))

        assertEquals(
            "Heard: \"yes, do it\" - approved.",
            words("""{"ok":true,"heard":"yes, do it","decision":"approved"}"""),
        )
        assertEquals("Heard: \"no\" - denied.", words("""{"heard":"no","decision":"denied"}"""))
        // The PC heard words and its voice check did not pass: nothing approved.
        assertEquals(Handsfree.NOT_YOUR_VOICE, words("""{"heard":"yes","decision":"not_you"}"""))
        // Words, and NO decision: the same thing to tell the owner.
        assertEquals(Handsfree.NOT_YOUR_VOICE, words("""{"heard":"yes"}"""))
        // Nothing heard at all.
        assertEquals(Handsfree.NOTHING_HEARD, words("""{"ok":true}"""))
        // A refusal keeps the PC's own sentence.
        assertEquals("Not your voice.", words("""{"ok":false,"why":"Not your voice."}"""))
        // A refusal with no sentence is the card having gone, which is the
        // common cause - and it never claims an approval.
        assertEquals(Handsfree.CARD_GONE, words("""{"ok":false}"""))
        // An unclassified decision is quoted, not interpreted.
        assertEquals(
            "Heard: \"maybe\" - the PC said \"unclear\".",
            words("""{"heard":"maybe","decision":"unclear"}"""),
        )
    }

    @Test
    fun `the answer's own words never claim an approval the PC did not give`() {
        // Every line for a non-approval, walked: none may carry the claim
        // " - approved", which is the half of the sentence the owner acts on.
        // `NOT_YOUR_VOICE` mentions the word ("nothing was approved") and that
        // is the point of it - a denial of the claim, not a claim.
        for (json in listOf(
            """{"ok":true}""",
            """{"heard":"yes"}""",
            """{"heard":"yes","decision":"not_you"}""",
            """{"ok":false,"why":"The card had gone."}""",
        )) {
            val words = Handsfree.answerWords(Handsfree.answerOf(obj(json)))
            assertFalse("$json claims an approval: $words", words.contains(" - approved"))
            assertFalse("$json claims an approval: $words", words.startsWith("Heard:"))
        }
    }

    // ------------------------------------------------------------- bodies ----

    @Test
    fun `the three request bodies are the contract's keys and nothing else`() {
        assertEquals("""{"enabled":true}""", Handsfree.enabledBody(true))
        assertEquals("""{"enabled":false}""", Handsfree.enabledBody(false))

        val body = obj(Handsfree.answerBody("card-7", byteArrayOf(1, 2, 3)))
        assertEquals(setOf("card_id", "data_b64", "sample_rate"), body.keys)
        assertEquals("card-7", body["card_id"]!!.toString().trim('"'))
        assertEquals(16_000, body["sample_rate"].toString().toInt())
        assertEquals("AQID", body["data_b64"]!!.toString().trim('"'))

        val result = obj(Handsfree.resultBody("cmd-1", ok = true, receipt = "sms_sent:RESULT_OK", why = ""))
        assertEquals(setOf("id", "ok", "receipt", "why"), result.keys)
        assertTrue(result["ok"].toString().toBoolean())
        // A quote in the words cannot break out of its field.
        val tricky = obj(Handsfree.resultBody("c", false, "r", "He said \"no\"\nand left"))
        assertTrue(tricky["why"].toString().contains("no"))
    }

    // -------------------------------------------------------------- words ----

    @Test
    fun `one line for Home says armed, or that this PC does not have it, or nothing`() {
        assertEquals(
            Handsfree.ARMED_SHORT,
            Handsfree.oneLine(Handsfree.Read(available = true, enabled = true), missing = false),
        )
        // A PC that answered 404: the one sentence, on every surface.
        assertEquals(Handsfree.NOT_HERE_SHORT, Handsfree.oneLine(null, missing = true))
        // The PC says it is off: nothing to say, because nothing is wrong.
        assertNull(Handsfree.oneLine(Handsfree.Read(available = true, enabled = false), missing = false))
        assertNull(Handsfree.oneLine(null, missing = false))
        // Available:false in words is the same answer as a 404.
        assertEquals(
            Handsfree.NOT_HERE_SHORT,
            Handsfree.oneLine(Handsfree.Read(available = false, enabled = false), missing = false),
        )
    }

    @Test
    fun `the chat and Live command answers on and off and the state, and nothing else`() {
        for (text in listOf(
            "turn on hands-free",
            "Turn on hands free",
            "turn on handsfree",
            "TURN ON HANDS-FREE!",
            "switch on hands-free",
            "hands free on",
        )) {
            assertEquals(text, Handsfree.Asked.ON, Handsfree.command(text))
        }
        for (text in listOf("turn off hands-free", "Turn off hands free.", "set handsfree off")) {
            assertEquals(text, Handsfree.Asked.OFF, Handsfree.command(text))
        }
        for (text in listOf("hands-free?", "is hands free on", "handsfree", "hands free mode")) {
            assertEquals(text, Handsfree.Asked.STATE, Handsfree.command(text))
        }
        // Everything else is an ordinary question and goes to the model.
        for (text in listOf(
            "",
            "   ",
            "turn on the lights",
            "handsfree mode is great",
            "what is hands-free",
            "turn on hands-free mode please now",
        )) {
            assertNull(text, Handsfree.command(text))
        }
    }

    @Test
    fun `the switch's own sentences say what it does and when the microphone opens`() {
        // Both are on the Settings row, so both must be whole sentences the
        // owner can act on - and neither may claim more than the mode does.
        assertTrue(Handsfree.ABOUT.contains("reads each approval card out loud"))
        assertTrue(Handsfree.ABOUT.contains("text message"))
        assertTrue(Handsfree.WHEN_LISTENING.contains("only while a card is being answered"))
        assertTrue(Handsfree.WHEN_LISTENING.contains("ten seconds"))
        // The listening line is the talk button's own words.
        assertEquals("Listening for your confirm/deny", Handsfree.LISTENING)
        // And the three degradation sentences are separate facts.
        assertTrue(Handsfree.NOT_HERE.contains("not available on this PC"))
        assertTrue(Handsfree.IN_CALL.contains("on a call"))
        assertTrue(Handsfree.NO_VOICE.contains("PC could not make the sound"))
    }
}
