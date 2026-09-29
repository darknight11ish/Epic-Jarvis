package com.jarvis.client

import com.jarvis.client.net.Chatbot
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Support
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Brain's "Chat with customer support for me", read from what the PC REALLY
 * answers.
 *
 * `contract/support-cases.json` is written by tools/gen_support_cases.py
 * from the real routes (jarvis_chatbot_routes.py) over the real support loop
 * (jarvis_support.py), with a stand-in chat - byte for byte the file the
 * desktop builds against. Its `words` are the PC's own sentences for this
 * feature (jarvis_support.WORDS), which this phone must say word for word.
 */
class SupportTest {

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/support-cases.json")) {
            "contract/support-cases.json is missing - run tools/gen_support_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }

    private fun view(case: String): Support.View =
        requireNotNull(Support.parse(doc[case]!!.jsonObject)) { "$case did not parse" }

    private fun chat(case: String): Support.Chat =
        requireNotNull(view(case).chat) { "$case has no chat" }

    private fun reply(case: String): Chatbot.Reply {
        val o = doc[case]!!.jsonObject
        return Chatbot.Reply(o["code"]!!.jsonPrimitive.int, o["body"]!!.jsonObject)
    }

    @Test
    fun `the words are the PC's own, every one`() {
        val w = doc["words"]!!.jsonObject
        assertEquals(w.keys, Support.WORDS.keys)
        for ((key, words) in Support.WORDS) {
            assertEquals(key, w[key]!!.jsonPrimitive.content, words)
        }
    }

    @Test
    fun `the companies, their terms risk and the version`() {
        val v = view("nothing")
        assertNull(v.chat)
        assertEquals(listOf("groupon" to false, "other" to true), v.companies.map { it.id to it.typed })
        assertTrue(v.companies.first().terms.contains("REAL Groupon account could be closed"))
        assertTrue(Support.versionLine(v).startsWith("Version: the limited version (one graphics card) - basic chats"))
        assertEquals(15, v.tier.messagesDefault)
        assertEquals(25, v.tier.messagesMax)
        assertEquals(120, v.tier.queueMax)
    }

    @Test
    fun `a chat reads - the card waiting, the queue, the offer, the end`() {
        val asking = chat("asking")
        assertEquals("Waiting for your yes to chat with Groupon", Support.talkingLine(asking))
        assertEquals(listOf("stop"), Support.actionsOf(asking))
        val queue = chat("in_queue")
        assertEquals("In the queue: number 2", Support.statusLine(queue))
        assertEquals(listOf("take_over", "stop"), Support.actionsOf(queue))
        val offer = chat("offer_waiting")
        assertEquals("Chat with Groupon: offer waiting", Support.talkingLine(offer))
        val o = requireNotNull(offer.offer)
        assertEquals("waiting", o.card)
        assertEquals(doc["offer_accept_line"]!!.jsonPrimitive.content, o.reply)
        assertEquals(listOf("decline", "say_else", "take_over"), Support.offerActions(offer))
        assertFalse(Support.offerActions(offer).contains("accept"))
        assertEquals("Talking with Priya", Support.statusLine(offer))
        assertEquals("no", chat("offer_card_no").offer?.card)
        val done = chat("done")
        assertFalse(done.live)
        assertEquals(emptyList<String>(), Support.actionsOf(done))
        assertEquals("GRP48213", done.reference)
        assertEquals(Support.SAVED_YES, Support.savedLine(done))
        assertNotNull(done.summary)
        assertTrue(done.transcript.filter { it.who == "company" || it.who == "system" }.all { it.outside })
        assertTrue(done.transcript.filter { it.who == "jarvis" }.none { it.outside })
        assertEquals(Support.WHO_JARVIS, Support.whoOf(done.transcript.first(), done))
        assertEquals("Groupon", Support.whoOf(done.transcript.first { it.who == "company" }, done))
        assertNull(view("gone").chat)
    }

    @Test
    fun `handed to the owner - a bot question, an identity check, Take over`() {
        val bot = chat("paused_bot_question")
        assertEquals(listOf("resume", "stop"), Support.actionsOf(bot))
        assertTrue(Support.statusLine(bot).contains("never claims to be a person"))
        assertTrue(bot.question.contains("bot or a real person"))
        assertEquals("Paused: chat with Groupon", Support.talkingLine(bot))
        assertEquals("identity", chat("paused_identity").pausedCode)
        assertTrue(chat("paused_takeover").takeOver)
    }

    @Test
    fun `answers from the PC - refused, accepted only on the card, decline`() {
        val (ok, said) = Support.said(reply("start_refused_detail"))
        assertFalse(ok)
        assertTrue(said, said.contains("can never be on the card"))
        assertFalse(Support.said(reply("answer_accept_refused")).first)
        val (yes, why) = Support.said(reply("answer_say_yes_refused"))
        assertFalse(yes)
        assertTrue(why.contains("approve the offer card"))
        assertTrue(Support.said(reply("answer_decline")).first)
        assertTrue(Support.said(reply("start_asking")).second.startsWith("Nothing has been sent yet."))
    }

    @Test
    fun `the bodies - as typed, never an accept, ids of the PC's shape`() {
        val body = Support.startBody("groupon", null, "  Refund my voucher ",
            listOf(Support.Detail(" Order  number ", " 4481902217 "), Support.Detail("", "")),
            15, null, 60)
        assertEquals("{\"company\":\"groupon\",\"goal\":\"Refund my voucher\"," +
            "\"details\":[{\"name\":\"Order number\",\"value\":\"4481902217\"}]," +
            "\"max_messages\":15,\"max_queue_minutes\":60}", body)
        assertNull(Support.startBody("other", "http://x.example", "g", emptyList(), null, null, null))
        assertTrue(Support.startBody("other", "https://help.example.com", "g", emptyList(), null, null,
            null)!!.contains("\"address\":\"https://help.example.com\""))
        assertNull(Support.startBody("groupon", null, "g", listOf(Support.Detail("x", "")), null, null, null))
        assertNull(Support.answerBody("sup_0123456789ab", 1, "accept", null))
        assertEquals("{\"id\":\"sup_0123456789ab\",\"offer\":2,\"choice\":\"say\",\"text\":\"Another option?\"}",
            Support.answerBody("sup_0123456789ab", 2, "say", "  Another   option? "))
        assertNull(Support.answerBody("chat_0123456789ab", 1, "decline", null))
        assertNull(Support.idBody("sup_../../etc"))
        assertTrue(Support.isSupportActivity("Chat with Groupon: message 2 of 15."))
        assertFalse(Support.isSupportActivity("Talking to Gemini: message 1 of 5."))
    }

    @Test
    fun `the form's own checks`() {
        val v = view("nothing")
        assertNull(Support.formProblem(v, "groupon", "", "Refund", emptyList(), "15", "30", "45"))
        assertEquals("Say what Jarvis should get done.",
            Support.formProblem(v, "groupon", "", " ", emptyList(), "15", "30", "45"))
        assertEquals("Type the company's help page, starting with https://",
            Support.formProblem(v, "other", "", "x", emptyList(), "15", "30", "45"))
        assertEquals("Most messages: 1 to 25 in this version.",
            Support.formProblem(v, "groupon", "", "x", emptyList(), "26", "30", "45"))
        assertEquals("The detail \"Email\" has no value.",
            Support.formProblem(v, "groupon", "", "x", listOf(Support.Detail("Email", " ")), "15", "30", "45"))
    }
}
