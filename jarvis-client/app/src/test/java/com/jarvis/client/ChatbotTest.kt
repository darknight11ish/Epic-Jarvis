package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.Chatbot
import com.jarvis.client.net.JarvisJson
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
 * Brain's "Talk to a chatbot for me", read from what the PC REALLY answers.
 *
 * `contract/chatbot-cases.json` is written by tools/gen_chatbot_cases.py from
 * the real routes (jarvis_chatbot_routes.py) over the real driver loop, with
 * a stand-in chatbot - byte for byte the file the desktop builds against. Its
 * `words` are the PC's own sentences for this feature (WORDS there), which
 * this phone must say word for word.
 */
class ChatbotTest {

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/chatbot-cases.json")) {
            "contract/chatbot-cases.json is missing - run tools/gen_chatbot_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }

    private fun view(case: String): Chatbot.View =
        requireNotNull(Chatbot.parse(doc[case]!!.jsonObject)) { "$case did not parse" }

    private fun reply(case: String): Chatbot.Reply {
        val o = doc[case]!!.jsonObject
        return Chatbot.Reply(o["code"]!!.jsonPrimitive.int, o["body"]!!.jsonObject)
    }

    @Test
    fun `the words are the PC's own, every one`() {
        val w = doc["words"]!!.jsonObject
        assertEquals(w.keys, Chatbot.WORDS.keys)
        for ((key, words) in Chatbot.WORDS) {
            assertEquals(key, w[key]!!.jsonPrimitive.content, words)
        }
    }

    @Test
    fun `not set up - Gemini is built but not signed in on this PC, and nothing can start`() {
        val v = view("not_ready")
        assertFalse(v.anyBuilt)
        assertNull(v.session)
        val bot = v.chatbots.single()
        assertTrue(bot.made)
        assertFalse(bot.built)
        assertTrue(bot.note.contains("never been signed in"))
        assertTrue(Chatbot.versionLine(v).startsWith("Version: the limited version (one graphics card) - "))
        assertEquals(bot.note + ".", Chatbot.formProblem(v, "gemini_web", "x", "5", "10"))
        val (ok, said) = Chatbot.said(reply("start_not_ready"))
        assertFalse(ok)
        assertTrue(said.contains("never been signed in"))
    }

    @Test
    fun `a refused start says why, in the PC's words`() {
        val (ok, said) = Chatbot.said(reply("start_goal_refused"))
        assertFalse(ok)
        assertTrue(said, said.contains("email address"))
        assertEquals(false to "At most 8 messages in this version.", Chatbot.said(reply("start_too_many")))
        val (busy, why) = Chatbot.said(reply("start_while_paused"))
        assertFalse(busy)
        assertTrue(why.startsWith("Another chatbot conversation"))
        val (started, words) = Chatbot.said(reply("start_asking"))
        assertTrue(started)
        assertTrue(words.startsWith("Nothing has been sent yet."))
    }

    @Test
    fun `the card waiting, running, paused - lines, buttons and the notification`() {
        val asking = view("asking").session!!
        assertEquals("asking", asking.state)
        assertEquals(listOf("stop"), Chatbot.actionsOf(asking))
        assertEquals("Waiting for your yes to talk to Gemini", Chatbot.talkingLine(asking))

        val run = view("running").session!!
        assertTrue(run.live)
        assertEquals(listOf("pause", "stop"), Chatbot.actionsOf(run))
        assertEquals("Talking to Gemini, 2 of 4", Chatbot.talkingLine(run))
        assertTrue(Chatbot.progressLine(run).startsWith("Message 2 of 4 · "))
        assertTrue(Chatbot.progressLine(run).endsWith(" of 10 minutes"))
        assertEquals(3, run.transcript.size)
        assertTrue(run.transcript.filter { it.who == "chatbot" }.all { it.outside })
        assertTrue(run.transcript.filter { it.who == "jarvis" }.none { it.outside })
        assertEquals(run.goal, run.transcript.first().text)

        val paused = view("paused_captcha").session!!
        assertEquals(listOf("resume", "stop"), Chatbot.actionsOf(paused))
        assertTrue(Chatbot.statusLine(paused).contains("captcha"))
        assertEquals("Paused: talking to Gemini, 2 of 4", Chatbot.talkingLine(paused))
        assertTrue("resume" in Chatbot.HELD_WHEN_STALE)
        assertFalse("stop" in Chatbot.HELD_WHEN_STALE)
        assertFalse("pause" in Chatbot.HELD_WHEN_STALE)
    }

    @Test
    fun `after it ends - no buttons, no notification, the summary kept`() {
        val stopped = view("stopped").session!!
        assertFalse(stopped.live)
        assertEquals("", stopped.paused)
        assertEquals("", Chatbot.talkingLine(stopped))
        assertTrue(Chatbot.actionsOf(stopped).isEmpty())
        assertEquals("You stopped it. Nothing more is sent.", Chatbot.statusLine(stopped))

        val done = view("done_goal_met")
        val s = done.session!!
        assertNotNull(s.summary)
        val summary = s.summary!!
        assertTrue(summary.answer.isNotEmpty())
        assertEquals(2, summary.claims.size)
        assertTrue(summary.claims.first().sourced)
        assertEquals("The new limits apply from the next message.", done.limits.said)

        assertTrue(view("asked_about_you").session!!.question.isNotEmpty())
        assertEquals("refused", view("card_denied").session!!.state)
        assertNull(view("gone").session)
    }

    @Test
    fun `stop and limits answers`() {
        assertEquals(true, Chatbot.said(reply("stop_paused")).first)
        assertEquals(false to "That conversation has already ended.", Chatbot.said(reply("stop_ended")))
        val (ok, said) = Chatbot.said(reply("limits_answer"))
        assertTrue(ok)
        assertTrue(said.startsWith("Nothing has changed yet."))
        assertFalse(Chatbot.said(reply("limits_after_end")).first)
        assertEquals(false to Chatbot.MISSING, Chatbot.said(Chatbot.Reply(404, null)))
        assertEquals(false to "No such conversation.",
            Chatbot.said(Chatbot.Reply(404, JarvisJson.parseToJsonElement(
                "{\"ok\": false, \"error\": \"No such conversation.\"}") as JsonObject)))
    }

    @Test
    fun `bodies carry only what can be sent`() {
        val body = Chatbot.startBody("gemini_web", "  Ferns for a \"dark\" room ", 5, null,
            listOf("Project Nimbus"))!!
        val o = JarvisJson.parseToJsonElement(body).jsonObject
        assertEquals("Ferns for a \"dark\" room", o["goal"]!!.jsonPrimitive.content)
        assertEquals(5, o["max_messages"]!!.jsonPrimitive.int)
        assertNull(o["max_minutes"])
        assertNull(Chatbot.startBody("../x", "goal", null, null, emptyList()))
        assertNull(Chatbot.startBody("gemini_web", "   ", null, null, emptyList()))
        assertNull(Chatbot.startBody("gemini_web", "x".repeat(1001), null, null, emptyList()))
        assertNull(Chatbot.startBody("gemini_web", "g", null, null, listOf("y".repeat(61))))
        assertEquals("{\"id\":\"chat_0123456789ab\"}", Chatbot.stopBody("chat_0123456789ab"))
        assertNull(Chatbot.stopBody("chat_../../x"))
        assertEquals("{\"id\":\"chat_0123456789ab\",\"max_messages\":6}",
            Chatbot.limitsBody("chat_0123456789ab", 6, null, null))
    }

    @Test
    fun `the form and the typed words`() {
        val v = view("latest_none")
        assertTrue(v.anyBuilt)
        assertNull(Chatbot.formProblem(v, "gemini_web", "Find out about ferns", "5", "10"))
        assertEquals("Say what Jarvis should find out.", Chatbot.formProblem(v, "gemini_web", " ", "5", "10"))
        assertEquals("Most messages: 1 to 8 in this version.",
            Chatbot.formProblem(v, "gemini_web", "x", "9", "10"))
        assertEquals("Choose a chatbot.", Chatbot.formProblem(v, "nope", "x", "5", "10"))
        assertEquals(listOf("Project Nimbus", "Aunt Rosa"),
            Chatbot.neverWords(" Project  Nimbus, , project nimbus,Aunt Rosa "))
        assertEquals(5, Chatbot.limitOf("5", 8))
        assertNull(Chatbot.limitOf("0", 8))
        assertNull(Chatbot.limitOf("x", 8))
        assertEquals("10", Chatbot.number(10.0))
        assertEquals("0.5", Chatbot.number(0.5))
    }

    @Test
    fun `an activity line about a conversation starts the watcher, others do not`() {
        assertTrue(Chatbot.isChatbotActivity("Talking to Gemini: message 3 of 5."))
        assertTrue(Chatbot.isChatbotActivity("Waiting while you chat before asking Gemini more."))
        assertTrue(Chatbot.isChatbotActivity("Continuing chatbot_session..."))
        assertFalse(Chatbot.isChatbotActivity("Thinking..."))
        assertFalse(Chatbot.isChatbotActivity("Asked the chatbot question in chat"))
        assertFalse(Chatbot.isChatbotActivity(null))
    }

    @Test
    fun `an older PC is not a chatbot view`() {
        assertNull(Chatbot.parse(JarvisJson.parseToJsonElement("{\"available\": false}") as JsonObject))
        assertNull(Chatbot.parse(JarvisJson.parseToJsonElement("{}") as JsonObject))
        assertTrue(Chatbot.missing(ApiError.NotFound))
        assertTrue(Chatbot.missing(ApiError.Server(501, "")))
        assertFalse(Chatbot.missing(ApiError.Server(500, "")))
    }
}
