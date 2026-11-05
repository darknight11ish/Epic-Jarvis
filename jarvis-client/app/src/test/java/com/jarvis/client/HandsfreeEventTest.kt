package com.jarvis.client

import com.jarvis.client.net.Handsfree
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The frozen contract, read from the wire: the three events, the four routes'
 * bodies and answers, every line of plain words, and the honest degradation
 * against a PC that has never heard of hands-free.
 *
 * `docs/JARVIS-API.md` section 186 is the contract (PR #1169, the PC half), and
 * this file is the phone half's reading of it. net/Handsfree.kt is pure, so all
 * of it is held here: a `handsfree_card` with no id is dropped (an answer to it
 * could not be posted), an unknown event kind is silently ignored (the stream
 * carries kinds this app does not know), the switch's 200/403/409 bodies become
 * words, `POST /api/handsfree` is the ONE switch path, and a 404 becomes "not
 * available on this PC yet" rather than a mode that looks broken.
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
                   "say":"Jarvis wants to switch the model.","expires_in_sec":60}""",
            ),
        )
        assertEquals(
            Handsfree.Arrival.CardArrived(
                Handsfree.Card(
                    cardId = "card-7",
                    action = "models_switch",
                    say = "Jarvis wants to switch the model.",
                    expiresInSec = 60,
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
    fun `the PC's own phone_result is read, so the app can say what the PC says`() {
        val arrived = Handsfree.arrival(
            Handsfree.EVENT_RESULT,
            obj(
                """{"id":"cmd-1","ok":true,"say":"Your text to Alex went through.",
                   "receipt":"sms_sent:RESULT_OK","why":""}""",
            ),
        )
        assertEquals(
            Handsfree.Arrival.ResultArrived(
                Handsfree.PhoneResult(
                    id = "cmd-1",
                    ok = true,
                    say = "Your text to Alex went through.",
                    receipt = "sms_sent:RESULT_OK",
                    why = "",
                ),
            ),
            arrived,
        )
        // A failed send is carried the same way, and never read as sent.
        val failed = Handsfree.arrival(
            Handsfree.EVENT_RESULT,
            obj("""{"id":"cmd-2","ok":false,"say":"Your text did not send.","why":"no signal"}"""),
        ) as Handsfree.Arrival.ResultArrived
        assertFalse(failed.result.ok)
        assertEquals("no signal", failed.result.why)
        // No id: there is nothing this can be tied to.
        assertNull(Handsfree.arrival(Handsfree.EVENT_RESULT, obj("""{"ok":true}""")))
    }

    @Test
    fun `unknown events are ignored, and so is a kind this app has never heard of`() {
        assertNull(Handsfree.arrival("approval", obj("""{"id":"a1"}""")))
        assertNull(Handsfree.arrival("", obj("{}")))
        assertNull(Handsfree.arrival("phone_command", obj("""{"kind":"send_sms"}""")))
        // The three this feature owns, and only those.
        assertEquals(Handsfree.EVENT_CARD, "handsfree_card")
        assertEquals(Handsfree.EVENT_COMMAND, "phone_command")
        assertEquals(Handsfree.EVENT_RESULT, "phone_result")
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
    fun `the contract's state keys are read - window, vocabulary, print and phone`() {
        val read = Handsfree.readOf(
            obj(
                """{"ok":true,"enabled":false,"window_sec":60,
                   "vocabulary":{"confirm":["yes","yeah","confirm","approve","do it",
                                            "go ahead","okay","ok"],
                                 "deny":["no","nope","deny","cancel","stop","don't","do not"]},
                   "voice_print":"owner-1","phone":{"ready":true,"why":""},
                   "reading":null}""",
            ),
        )
        assertEquals(60, read.windowSec)
        val vocab = requireNotNull(read.vocabulary) { "the closed vocabulary is read" }
        assertEquals(8, vocab.confirm.size)
        assertEquals(7, vocab.deny.size)
        assertTrue(vocab.confirm.contains("do it"))
        assertTrue(vocab.deny.contains("do not"))
        assertEquals("owner-1", read.voicePrint)
        assertTrue(read.phone.ready)
        assertEquals("", read.phone.why)
        assertNull("no read-out is not a card", read.card)
        // A PC with no print says so, and the phone shows the PC's why about a
        // phone that cannot take a text.
        val bare = Handsfree.readOf(
            obj("""{"enabled":true,"voice_print":"","phone":{"ready":false,"why":"no phone paired"}}"""),
        )
        assertEquals("", bare.voicePrint)
        assertFalse(bare.phone.ready)
        assertEquals("no phone paired", bare.phone.why)
    }

    @Test
    fun `the newest read-out is read from reading, which is the contract's key`() {
        val read = Handsfree.readOf(
            obj(
                """{"enabled":true,"window_sec":60,
                   "reading":{"card_id":"c1","action":"models_switch",
                               "say":"Say this","expires_in_sec":45}}""",
            ),
        )
        assertEquals("c1", read.card?.cardId)
        assertEquals("Say this", read.card?.say)
        assertEquals(45, read.card?.expiresInSec)
        assertNull(Handsfree.readOf(obj("""{"enabled":true,"reading":null}""")).card)
    }

    @Test
    fun `an older PC's nested or flattened card is still read, as a fallback only`() {
        val nested = Handsfree.readOf(
            obj("""{"enabled":true,"card":{"card_id":"c2","say":"Nested","expires_in_sec":5}}"""),
        )
        assertEquals("c2", nested.card?.cardId)
        val top = Handsfree.readOf(
            obj("""{"enabled":true,"card_id":"c3","action":"models_switch","say":"Say this"}"""),
        )
        assertEquals("c3", top.card?.cardId)
    }

    // ------------------------------------------------------------- switch ----

    @Test
    fun `the switch is read from the contract's 200, 403 and 409 bodies`() {
        // ON landed: the PC says which state it is in and why.
        val on = Handsfree.Enabled.of(
            obj("""{"ok":true,"enabled":true,"changed":true,"message":"Hands-free mode is on."}"""),
        )
        assertEquals(true, on.on)
        assertEquals(true, on.changed)
        assertEquals("Hands-free mode is on.", on.message)
        assertNull(on.error)

        // ON already on: idempotent, changed false, and it says so.
        val again = Handsfree.Enabled.of(
            obj("""{"ok":true,"enabled":true,"changed":false,"message":"already on"}"""),
        )
        assertEquals(false, again.changed)

        // OFF: immediate and cardless.
        val off = Handsfree.Enabled.of(
            obj("""{"ok":true,"enabled":false,"message":"Hands-free mode is off."}"""),
        )
        assertEquals(false, off.on)
        assertEquals("Hands-free mode is off.", off.message)

        // ON refused by its own card: 403, and the PC's sentence is the answer.
        val refused = Handsfree.Enabled.of(
            obj("""{"ok":false,"enabled":false,"error":"the owner said no"}"""),
        )
        assertEquals(false, refused.on)
        assertEquals("the owner said no", refused.error)
        assertNull(refused.message)

        // A settings file that cannot be written: 409, same shape.
        val conflict = Handsfree.Enabled.of(
            obj("""{"ok":false,"enabled":false,"error":"the settings file could not be written"}"""),
        )
        assertEquals("the settings file could not be written", conflict.error)

        // No body at all claims nothing.
        val bare = Handsfree.Enabled.of(null)
        assertNull(bare.on)
        assertNull(bare.message)
        assertNull(bare.error)
    }

    @Test
    fun `the switch is ONE route - the contract has no separate enabled path`() {
        assertEquals("/api/handsfree", Handsfree.PATH)
        assertEquals("/api/handsfree/answer", Handsfree.ANSWER_PATH)
        assertEquals("/api/phone/result", Handsfree.RESULT_PATH)
        assertEquals("""{"enabled":true}""", Handsfree.enabledBody(true))
        assertEquals("""{"enabled":false}""", Handsfree.enabledBody(false))
    }

    // ------------------------------------------------------------- answer ----

    @Test
    fun `the PC's answer is read, and an absent ok is not a refusal`() {
        val a = Handsfree.answerOf(
            obj(
                """{"ok":true,"heard":"yes","decision":"approved",
                   "card_state":"approved","say":"Approved. Carrying on."}""",
            ),
        )
        assertTrue(a.ok)
        assertEquals("yes", a.heard)
        assertEquals("approved", a.decision)
        assertEquals("approved", a.cardState)
        assertEquals("Approved. Carrying on.", a.say)

        assertTrue(
            "a body with the contract fields and no ok still heard something",
            Handsfree.answerOf(obj("""{"heard":"yes","decision":"approved"}""")).ok,
        )

        // The PC's 403 (not your voice / no print / the mode is off) carries its
        // own sentence, and it is what the owner is shown.
        val refused = Handsfree.answerOf(
            obj(
                """{"ok":false,"heard":"","decision":"refused","card_state":"unchanged",
                   "say":"That was not your voice, so nothing was decided."}""",
            ),
        )
        assertFalse(refused.ok)
        assertEquals(
            "That was not your voice, so nothing was decided.",
            Handsfree.answerWords(refused),
        )
        assertEquals(
            "That was not your voice, so nothing was decided.",
            refused.say,
        )
    }

    @Test
    fun `every answer becomes the PC's own sentence, and never an invented decision`() {
        fun words(json: String) = Handsfree.answerWords(Handsfree.answerOf(obj(json)))

        // 1. The PC's `say` is the answer, verbatim - a decision...
        assertEquals(
            "Approved. Carrying on.",
            words("""{"ok":true,"heard":"yes","decision":"approved","say":"Approved. Carrying on."}"""),
        )
        // ...a refusal...
        assertEquals(
            "Hands-free mode is off, so a spoken answer decides nothing. Turn it on first.",
            words(
                """{"ok":false,"decision":"refused","card_state":"unchanged",
                   "say":"Hands-free mode is off, so a spoken answer decides nothing. Turn it on first."}""",
            ),
        )
        // ...and the question the PC asks when it could not place the words.
        assertEquals(
            "Sorry - was that yes or no?",
            words("""{"ok":false,"heard":"mmm","decision":"again","card_state":"pending",
                      "say":"Sorry - was that yes or no?"}"""),
        )

        // 2. A yes and a no with no `say` (a PC older than the contract) still
        //    read as a decision, and never as an invented one.
        assertEquals(
            "Heard: \"yes, do it\" - approved.",
            words("""{"ok":true,"heard":"yes, do it","decision":"approved"}"""),
        )
        assertEquals("Heard: \"no\" - denied.", words("""{"heard":"no","decision":"denied"}"""))
        // An unclassified decision is quoted, not interpreted.
        assertEquals(
            "Heard: \"maybe\" - the PC said \"unclear\".",
            words("""{"heard":"maybe","decision":"unclear"}"""),
        )
        // Nothing heard at all.
        assertEquals(Handsfree.NOTHING_HEARD, words("""{"ok":true}"""))
        // Words, and NO decision: something was heard and nothing approved.
        assertEquals(Handsfree.NOT_YOUR_VOICE, words("""{"heard":"yes"}"""))
        // A voice check that did not pass.
        assertEquals(Handsfree.NOT_YOUR_VOICE, words("""{"heard":"yes","decision":"not_you"}"""))
        assertNotEquals(
            "a refused voice check was reported as an expiry",
            Handsfree.CARD_GONE,
            words("""{"ok":false,"decision":"not_you"}"""),
        )
        // `again` with no sentence is the phone's own question, never a refusal.
        assertEquals(Handsfree.ASK_AGAIN, words("""{"ok":false,"decision":"again"}"""))
        // A refusal with NO sentence is the general refusal, never a guess that
        // the card expired (an audit finding, 2026-11-05).
        assertEquals(Handsfree.REFUSED, words("""{"ok":false}"""))
        assertFalse(
            "a refusal with no words still claims an expiry",
            Handsfree.REFUSED.contains("expired"),
        )
        // "The card had gone" is said only when the card's OWN state says it.
        assertEquals(Handsfree.CARD_GONE, words("""{"ok":false,"card_state":"expired"}"""))
        assertEquals(Handsfree.CARD_GONE, words("""{"ok":false,"card_state":"gone"}"""))
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
            """{"ok":false,"say":"The card had gone."}""",
            """{"ok":false,"decision":"again"}""",
        )) {
            val words = Handsfree.answerWords(Handsfree.answerOf(obj(json)))
            assertFalse("$json claims an approval: $words", words.contains(" - approved"))
            assertFalse("$json claims an approval: $words", words.startsWith("Heard:"))
        }
    }

    // ------------------------------------------------------------- bodies ----

    @Test
    fun `the three request bodies are the contract's keys and nothing else`() {
        val body = obj(Handsfree.answerBody("card-7", byteArrayOf(1, 2, 3)))
        assertEquals(setOf("card_id", "data_b64", "sample_rate"), body.keys)
        assertEquals("card-7", body["card_id"]!!.toString().trim('"'))
        // The clip is always the 16 kHz WAV HandsfreeClip built, so the
        // declared rate can never disagree with the file (section 186.5).
        assertEquals(16_000, body["sample_rate"].toString().toInt())
        assertEquals(16_000, Handsfree.SAMPLE_RATE)
        assertEquals("AQID", body["data_b64"]!!.toString().trim('"'))

        val result = obj(Handsfree.resultBody("cmd-1", ok = true, receipt = "sms_sent:RESULT_OK", why = ""))
        assertEquals(setOf("id", "ok", "receipt", "why"), result.keys)
        assertTrue(result["ok"].toString().toBoolean())
        // A quote in the words cannot break out of its field.
        val tricky = obj(Handsfree.resultBody("c", false, "r", "He said \"no\"\nand left"))
        assertTrue(tricky["why"].toString().contains("no"))
    }

    // ------------------------------------------------------------- window ----

    @Test
    fun `the answer window is the PC's, and the clip cap is the PC's 30 seconds`() {
        // `expires_in_sec` is the ANSWER window, not the card's own deadline.
        assertEquals(60, Handsfree.windowSec(Handsfree.Card(cardId = "c", expiresInSec = 60)))
        assertEquals(5, Handsfree.windowSec(Handsfree.Card(cardId = "c", expiresInSec = 5)))
        // A PC that sent none falls back to the read's window_sec...
        assertEquals(45, Handsfree.windowSec(Handsfree.Card(cardId = "c"), 45))
        // ...and with no read either, to the contract's minute.
        assertEquals(60, Handsfree.windowSec(Handsfree.Card(cardId = "c")))
        // Never longer than the contract's minute; a nonsense value falls back
        // to the read's window and then to the contract's own minute.
        assertEquals(60, Handsfree.windowSec(Handsfree.Card(cardId = "c", expiresInSec = 3_600)))
        assertEquals(60, Handsfree.windowSec(Handsfree.Card(cardId = "c", expiresInSec = -4)))
        assertEquals(1, Handsfree.windowSec(Handsfree.Card(cardId = "c"), 0))
        // The PC refuses a clip over 30 s rather than truncating it.
        assertEquals(30, Handsfree.MAX_CLIP_SEC)
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
        assertTrue(Handsfree.ABOUT.contains("minute"))
        assertTrue(Handsfree.WHEN_LISTENING.contains("only while a card is being answered"))
        // The window is the PC's minute, not this app's old ten seconds.
        assertTrue(Handsfree.WHEN_LISTENING.contains("minute"))
        assertFalse(Handsfree.WHEN_LISTENING.contains("ten seconds"))
        assertTrue(Handsfree.NO_PRINT.contains("spoken yes"))
        // The listening line is the talk button's own words.
        assertEquals("Listening for your confirm/deny", Handsfree.LISTENING)
        // And the degradation sentences are separate facts.
        assertTrue(Handsfree.NOT_HERE.contains("not available on this PC"))
        assertTrue(Handsfree.IN_CALL.contains("on a call"))
        assertTrue(Handsfree.NO_VOICE.contains("PC could not make the sound"))
    }
}
