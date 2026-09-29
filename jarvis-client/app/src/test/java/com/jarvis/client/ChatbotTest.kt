package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.Chatbot
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
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
    fun `a finished conversation says whether it was kept in History, and promises nothing else`() {
        assertEquals("", Chatbot.historyLine(null))
        assertEquals(Chatbot.HISTORY_KEPT, Chatbot.historyLine(Chatbot.HistoryAnswer(true, "")))
        assertEquals(
            "Not kept in your chat history: chat history is off.",
            Chatbot.historyLine(Chatbot.HistoryAnswer(false, "chat history is off")),
        )
        assertEquals(
            "a full stop is not doubled",
            "Not kept in your chat history: chat history is off.",
            Chatbot.historyLine(Chatbot.HistoryAnswer(false, "chat history is off.")),
        )
        val kept = Chatbot.parseHistory(JarvisJson.parseToJsonElement("{\"kept\":true,\"why\":\"\"}") as JsonObject)
        assertEquals(Chatbot.HistoryAnswer(true, ""), kept)
        assertNull(Chatbot.parseHistory(JarvisJson.parseToJsonElement("{\"kept\":\"yes\"}") as JsonObject))
        assertNull(Chatbot.parseHistory(null))
        assertFalse(Chatbot.SUMMARY_NOTE.contains("kept in History"))
        assertFalse(Chatbot.COMPARE_SUMMARY_NOTE.contains("kept in History"))
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
    fun `a comparison - every chatbot, its lines, the buttons and the notification`() {
        val none = view("compare_none")
        assertNull(none.compare)
        assertEquals(2, none.tier.compareMin)
        assertEquals(3, none.tier.compareMax)
        assertTrue(none.canCompare)
        assertEquals("Chatbots to ask (pick 2 to 3)", Chatbot.pickLine(none))
        assertFalse(view("not_ready").canCompare)

        val asking = view("compare_asking").compare!!
        assertEquals("Waiting for your yes to ask 3 chatbots", Chatbot.compareTalkingLine(asking))
        assertEquals(listOf("stop"), Chatbot.compareActionsOf(asking))

        val running = view("compare_running")
        assertNull("a comparison's conversation read as the single one", running.session)
        val run = running.compare!!
        assertEquals("Comparing 3 chatbots: asking ChatGPT, 2 of 3", Chatbot.compareTalkingLine(run))
        assertEquals(listOf("pause", "stop"), Chatbot.compareActionsOf(run))
        assertEquals(
            listOf("Gemini: It used all 3 messages you allowed.", "ChatGPT: Talking now.",
                "Claude: Waiting its turn."),
            run.members.map { Chatbot.memberLine(it, run) },
        )
        assertTrue(run.members.all { m -> m.transcript.filter { it.who == "chatbot" }.all { it.outside } })
        assertTrue(Chatbot.compareProgress(run).startsWith("5 messages sent in all · at most 3 messages"))

        val paused = view("compare_paused").compare!!
        assertEquals(listOf("resume", "stop"), Chatbot.compareActionsOf(paused))
        assertEquals("Paused: comparing 2 chatbots", Chatbot.compareTalkingLine(paused))
        assertTrue(Chatbot.compareStatusLine(paused).startsWith("You paused the comparison."))

        val stopped = view("compare_stopped").compare!!
        assertFalse(stopped.live)
        assertEquals("", stopped.paused)
        assertTrue(Chatbot.compareActionsOf(stopped).isEmpty())
        assertEquals("", Chatbot.compareTalkingLine(stopped))
        assertNull(view("compare_gone").compare)
    }

    @Test
    fun `a comparison's summary - agree, disagree by name, sources, who dropped out`() {
        val done = view("compare_done").compare!!
        assertFalse(done.live)
        val sm = done.summary!!
        assertTrue(sm.answer.isNotEmpty())
        assertEquals(2, sm.agree.size)
        assertEquals(listOf("Gemini", "ChatGPT"), sm.disagree.single().views.map { it.who })
        assertEquals(listOf("Gemini", "ChatGPT"), sm.sources.map { it.who })
        assertEquals(listOf("Claude"), sm.dropped.map { it.who })
        assertTrue(sm.dropped.single().why.contains("captcha"))
        assertEquals(listOf("Which grow lamp to buy"), sm.open)
    }

    @Test
    fun `a comparison's form, bodies and answers`() {
        val v = view("compare_none")
        assertEquals("Pick at least 2 chatbots to compare.",
            Chatbot.compareFormProblem(v, listOf("gemini_web"), "x", "3", "10"))
        assertNull(Chatbot.compareFormProblem(v, listOf("gemini_web", "chatgpt_web"), "x", "3", "10"))
        assertEquals("Say what Jarvis should find out.",
            Chatbot.compareFormProblem(v, listOf("gemini_web", "chatgpt_web"), " ", "3", "10"))
        assertEquals(Chatbot.COMPARE_NOT_ENOUGH,
            Chatbot.compareFormProblem(view("not_ready"), listOf("gemini_web", "x"), "x", "3", "10"))
        val four = v.copy(chatbots = v.chatbots + Chatbot.Choice("grok_web", "Grok", "grok.com", true, ""))
        assertEquals("Pick at most 3 chatbots in this version.",
            Chatbot.compareFormProblem(four, listOf("gemini_web", "chatgpt_web", "claude_web", "grok_web"),
                "x", "3", "10"))

        val body = Chatbot.compareBody(listOf("gemini_web", "claude_web", "gemini_web"), " Ferns ", 3,
            null, listOf("Nimbus"))!!
        val o = JarvisJson.parseToJsonElement(body).jsonObject
        assertEquals(listOf("gemini_web", "claude_web"),
            o["chatbots"]!!.jsonArray.map { it.jsonPrimitive.content })
        assertNull(o["chatbot"])
        assertEquals("Ferns", o["goal"]!!.jsonPrimitive.content)
        assertEquals(3, o["max_messages"]!!.jsonPrimitive.int)
        assertNull(Chatbot.compareBody(listOf("gemini_web"), "g", null, null, emptyList()))
        assertNull(Chatbot.compareBody(listOf("a", "b", "c", "d", "e"), "g", null, null, emptyList()))
        assertNull(Chatbot.compareBody(listOf("a", "../b"), "g", null, null, emptyList()))
        assertEquals("{\"id\":\"cmp_0123456789ab\"}", Chatbot.compareStopBody("cmp_0123456789ab"))
        assertNull(Chatbot.compareStopBody("chat_0123456789ab"))
        assertTrue(Chatbot.COMPARE_START_PATH in Chatbot.WRITE_PATHS)
        assertTrue(Chatbot.COMPARE_STOP_PATH in Chatbot.WRITE_PATHS)

        assertEquals(false to "Pick at least 2 chatbots to compare.", Chatbot.said(reply("compare_too_few")))
        val (started, words) = Chatbot.said(reply("compare_start_asking"))
        assertTrue(started)
        assertTrue(words.contains("An approval card lists every chatbot"))
        val (busy, why) = Chatbot.said(reply("compare_start_while_paused"))
        assertFalse(busy)
        assertTrue(why.startsWith("Another comparison"))
        assertTrue(Chatbot.said(reply("compare_stop_paused")).first)
        assertEquals(false to "That comparison has already ended.", Chatbot.said(reply("compare_stop_ended")))
        assertTrue(Chatbot.isChatbotActivity("Comparing (2 of 3): Talking to ChatGPT: message 1 of 3."))
        assertTrue(Chatbot.isChatbotActivity("Continuing chatbot_compare..."))
    }

    @Test
    fun `a long list is grouped by how each chatbot is reached`() {
        val v = view("long_list")
        assertEquals(
            listOf(
                Triple("website", Chatbot.KIND_WEBSITE, listOf("chatgpt_web", "gemini_web", "perplexity_web")),
                Triple("api", Chatbot.KIND_API, listOf("openai_api", "deepseek_api", "groq_api")),
                Triple("local", Chatbot.KIND_LOCAL, listOf("local_ai")),
            ),
            Chatbot.groups(v).map { g -> Triple(g.kind, g.title, g.chatbots.map { it.id }) },
        )
        assertEquals("gemini_web", Chatbot.ordered(v).first { it.built }.id)
        assertTrue(v.chatbots.filter { !it.built }.all { it.note.isNotEmpty() })
        val old = Chatbot.parse(JarvisJson.parseToJsonElement(
            "{\"chatbots\": [{\"id\": \"x\", \"built\": true}], \"tier\": {}}") as JsonObject)!!
        assertEquals("website", old.chatbots.single().kind)
    }

    @Test
    fun `an API conversation's counts, alone and per chatbot in a comparison`() {
        val line = "Used so far: 3 requests, 4,215 word-pieces (tokens), model gpt-5-mini, about \$0.01"
        assertEquals(line, Chatbot.usageLine(view("usage_done").session!!.usage))
        assertEquals(listOf("", line),
            view("compare_usage").compare!!.members.map { Chatbot.usageLine(it.usage) })
        assertNull(view("running").session!!.usage)
        assertEquals("Used so far: 1 request, 1,234,567 word-pieces (tokens)",
            Chatbot.usageLine(Chatbot.Usage(1, 1234567L, "")))
        // An older PC sends no cost: the line leaves it out.
        assertEquals("Used so far: 2 requests, 10 word-pieces (tokens), model m",
            Chatbot.usageLine(Chatbot.Usage(2, 10L, "m")))
        assertEquals("999", Chatbot.grouped(999L))
        assertEquals("1,000", Chatbot.grouped(1000L))
    }

    @Test
    fun `an API service's money limit reads as the PC wrote it - left, reached, never set`() {
        val openai = view("long_list").chatbots.single { it.id == "openai_api" }
        assertEquals("About \$4.55 of \$5.00 left this month for OpenAI (prices are estimates you can " +
            "correct on the PC).", Chatbot.moneyLine(openai))
        assertTrue(view("long_list").chatbots.filter { it.id != "openai_api" }.all { it.money == null })
        val r = view("money_reached")
        val reached = r.chatbots.single { it.id == "openai_api" }
        assertFalse(reached.built)
        assertTrue(reached.money!!.reached)
        assertEquals("About \$0.00 of \$1.00 left this month for OpenAI (prices are estimates you can " +
            "correct on the PC).", Chatbot.moneyLine(reached))
        assertTrue(reached.note.startsWith("You set \$1.00 a month for OpenAI; about \$1.02 is used"))
        assertEquals(reached.note, Chatbot.formProblem(r, "openai_api", "x", "3", "5"))
        val mistral = r.chatbots.single { it.id == "mistral_api" }
        assertNull(mistral.money)
        assertTrue(mistral.note.startsWith("No monthly money limit is set for Mistral AI"))
        assertEquals(false to reached.note, Chatbot.said(reply("start_money_reached")))
        assertEquals("", Chatbot.moneyLine(null))
    }

    @Test
    fun `an answer the money limit's cap cut short is marked, and only that one`() {
        val turns = view("cut_off").session!!.transcript
        assertEquals(listOf("jarvis" to false, "chatbot" to true, "jarvis" to false,
            "chatbot" to false), turns.map { it.who to it.cutOff })
        assertTrue(view("running").session!!.transcript.none { it.cutOff })
        assertEquals("Jarvis asked for a short answer so it stays within your limit; the rest " +
            "was cut off.", Chatbot.CUT_OFF)
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
