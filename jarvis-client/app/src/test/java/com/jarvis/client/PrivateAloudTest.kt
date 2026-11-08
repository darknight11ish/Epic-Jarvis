package com.jarvis.client

import com.jarvis.client.net.Heard
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.voice.MemoryAloud
import com.jarvis.client.voice.PrivateAloud
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Private answers stay on screen" when the phone speaks
 * (docs/JARVIS-API.md section 16, "What the apps must do about private
 * answers"). The utterance replies are the PC's REAL ones -
 * jarvis_speech.hear().as_dict() - and the headers start from the real
 * router's decision (jarvis_router.choose().as_dict()), both from
 * `contract/phone-voice-cases.json` (tools/gen_phone_voice_cases.py).
 * `injected_facts` is added to a real header where a test needs it: the
 * PC's chat route adds it, and that route is not in this repository.
 */
class PrivateAloudTest {

    private val answers: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/phone-voice-cases.json")) {
            "contract/phone-voice-cases.json is missing - run tools/gen_phone_voice_cases.py"
        }.readText()
        (JarvisJson.parseToJsonElement(text) as JsonObject)["strict"]!!.jsonObject["answers"]!!.jsonObject
    }

    private fun heard(case: String): Heard =
        JarvisJson.decodeFromJsonElement(Heard.serializer(), answers["heard"]!!.jsonObject[case]!!)

    /**
     * A real router header with `injected_facts` and `injected_sensitive`
     * set as asked. [sensitive] null takes `injected_sensitive` OUT, which is
     * what a PC from before the owner's decision of 2026-09-24 sends.
     */
    private fun header(case: String, injected: Int? = null, sensitive: Int? = null): String {
        val o = answers["route"]!!.jsonObject[case]!!.jsonObject - "injected_sensitive"
        val withFacts = if (injected == null) o else o + ("injected_facts" to JsonPrimitive(injected))
        val withSensitive = if (sensitive == null) withFacts else withFacts + ("injected_sensitive" to JsonPrimitive(sensitive))
        return JsonObject(withSensitive).toString()
    }

    /**
     * A real utterance reply with `sensitive_aloud` set. The phone voice
     * fixture (tools/gen_phone_voice_cases.py) does not carry the field yet
     * - its regeneration is the backend's - so it is written in here.
     */
    private fun heardWith(case: String, sensitiveAloud: Boolean): Heard {
        val o = answers["heard"]!!.jsonObject[case]!!.jsonObject
        return JarvisJson.decodeFromJsonElement(
            Heard.serializer(), JsonObject(o + ("sensitive_aloud" to JsonPrimitive(sensitiveAloud))),
        )
    }

    private val live = PrivateAloud.Watch(runs = 4, drops = 1, live = true)

    /**
     * The rule with the phone's 2026-11-05 setting and the two facts captured
     * at the mic press, all OFF unless a test says otherwise - which is the
     * shipped default.
     */
    private fun may(
        h: Heard,
        route: String?,
        now: PrivateAloud.Watch = live,
        phoneMemoryAloud: Boolean = false,
        talkButton: Boolean = false,
        unlockedAtPress: Boolean = false,
    ) = PrivateAloud.mayRead(
        h,
        PrivateAloud.route(route),
        live,
        now,
        phoneMemoryAloud = phoneMemoryAloud,
        talkButton = talkButton,
        unlockedAtPress = unlockedAtPress,
    )

    @Test
    fun `the real reply carries both fields`() {
        assertTrue(heard("private_question").questionPrivate)
        assertFalse(heard("private_question").privateAloud)
        assertFalse(heard("plain_question").questionPrivate)
        assertTrue(heard("voice_is_enough").privateAloud)
    }

    @Test
    fun `the phone's mic press reads nothing aloud privately`() {
        // The owner, 2026-11-02: the phone's mic press - a short verbal message
        // - is not put to the voice print. The reply says so (`mode:
        // quick_message`, `strictness: ""`), and nothing a real check used to
        // buy is granted: no private, memory or sensitive answer is read
        // aloud. The screen rule never rested on the check, so it stays as it
        // was (the fixture case, tools/gen_phone_voice_cases.py).
        val h = heard("quick_message")
        assertEquals("quick_message", h.mode)
        assertFalse(h.privateAloud)
        assertFalse(h.memoryAloud)
        assertFalse(h.sensitiveAloud)
        assertTrue(h.screenAloud)
        // A plain answer is still spoken; one that uses what Jarvis remembers
        // is not, because the voice was never checked.
        assertTrue(may(h, header("plain")))
        assertFalse(may(h, header("plain", injected = 3, sensitive = 0)))
    }

    @Test
    fun `a plain question with nothing private about it is read aloud`() {
        assertTrue(may(heard("plain_question"), header("plain")))
        assertTrue(may(heard("plain_question"), header("plain", injected = 0)))
        // No header at all (an older PC): nothing says it is private.
        assertTrue(may(heard("plain_question"), null))
    }

    @Test
    fun `a question the PC marked private is not`() {
        assertFalse(may(heard("private_question"), header("no_cloud_lane")))
    }

    @Test
    fun `the router's private gate is not`() {
        assertEquals(PrivateAloud.Route(privateGate = true, injectedFacts = 0), PrivateAloud.route(header("private")))
        assertFalse(may(heard("plain_question"), header("private")))
    }

    @Test
    fun `remembered facts are read aloud by default - the owner's choice`() {
        assertTrue(heard("plain_question").memoryAloud)
        assertTrue(may(heard("plain_question"), header("plain", injected = 3, sensitive = 0)))
        // Asking about memory is not a private question while memory is aloud.
        assertFalse(heard("memory_question").questionPrivate)
        assertTrue(may(heard("memory_question"), header("plain", injected = 2, sensitive = 0)))
    }

    @Test
    fun `with memory kept on screen, remembered facts in the answer are not`() {
        val h = heard("memory_on_screen")
        assertFalse(h.memoryAloud)
        assertFalse(may(h, header("plain", injected = 3)))
        assertTrue(may(h, header("plain")))
        assertTrue(heard("memory_question_on_screen").questionPrivate)
        assertFalse(may(heard("memory_question_on_screen"), header("plain")))
    }

    @Test
    fun `memory aloud never opens email, notes or a tool`() {
        assertFalse(may(heard("private_question"), header("no_cloud_lane")))
        assertFalse(may(heard("plain_question"), header("private", injected = 1)))
        assertFalse(may(heard("plain_question"), header("plain", injected = 1), live.copy(runs = 5, privateRuns = 5)))
    }

    @Test
    fun `a tool that ran while it was written stops the reading`() {
        assertFalse(may(heard("plain_question"), header("plain"), live.copy(runs = 5, privateRuns = 5)))
    }

    @Test
    fun `web search or home status that ran is read aloud - the owner's decision of 2026-09-27`() {
        // Four tools ran, none private: privateRuns did not move.
        assertTrue(may(heard("plain_question"), header("plain"), live.copy(runs = 8)))
        // One of them was private.
        assertFalse(may(heard("plain_question"), header("plain"), live.copy(runs = 8, privateRuns = 5)))
        // Not knowing still keeps it on screen.
        assertFalse(may(heard("plain_question"), header("plain"), live.copy(runs = 8, drops = 2)))
    }

    @Test
    fun `not knowing whether a tool ran counts as a tool having run`() {
        // The stream dropped and came back while the answer was written.
        assertFalse(may(heard("plain_question"), header("plain"), live.copy(drops = 2)))
        // The stream is not live now.
        assertFalse(may(heard("plain_question"), header("plain"), live.copy(live = false)))
        // Nor was it when the question was asked.
        assertFalse(
            PrivateAloud.mayRead(heard("plain_question"), PrivateAloud.route(header("plain")), live.copy(live = false), live),
        )
    }

    @Test
    fun `voice check is enough reads it all`() {
        val h = heard("voice_is_enough")
        assertTrue(may(h, header("private", injected = 5, sensitive = 0), live.copy(runs = 9, privateRuns = 9)))
    }

    @Test
    fun `an older PC's reply - no fields - counts as not allowed aloud`() {
        val o = answers["heard"]!!.jsonObject["plain_question"]!!.jsonObject
        val older = JarvisJson.decodeFromJsonElement(
            Heard.serializer(), JsonObject(o - setOf("private_aloud", "question_private", "memory_aloud")),
        )
        assertFalse(older.privateAloud)
        assertFalse(older.memoryAloud)
        // ...and is then held to the same rule: read only when nothing says private.
        assertFalse(may(older, header("plain", injected = 1)))
        assertTrue(may(older, header("plain")))
    }

    // ------------------------- sensitive saved facts (owner, 2026-09-24) --

    @Test
    fun `the header's sensitive count is read, and fails closed when it is missing`() {
        assertEquals(2, PrivateAloud.route(header("plain", injected = 3, sensitive = 2)).injectedSensitive)
        assertEquals(0, PrivateAloud.route(header("plain", injected = 3, sensitive = 0)).injectedSensitive)
        // Missing, with facts in the answer: every one may be sensitive.
        assertEquals(3, PrivateAloud.route(header("plain", injected = 3)).injectedSensitive)
        // Missing, with no facts: nothing sensitive.
        assertEquals(0, PrivateAloud.route(header("plain", injected = 0)).injectedSensitive)
        assertEquals(0, PrivateAloud.route(header("plain")).injectedSensitive)
        // Not a real count (a string, negative): treated as missing - closed.
        val o = answers["route"]!!.jsonObject["plain"]!!.jsonObject + ("injected_facts" to JsonPrimitive(2))
        assertEquals(2, PrivateAloud.route(JsonObject(o + ("injected_sensitive" to JsonPrimitive("0"))).toString()).injectedSensitive)
        assertEquals(2, PrivateAloud.route(JsonObject(o + ("injected_sensitive" to JsonPrimitive(-1))).toString()).injectedSensitive)
        assertEquals(PrivateAloud.SILENT_ROUTE, PrivateAloud.route(null))
    }

    @Test
    fun `an answer that used a sensitive saved fact stays on screen, even with memories read aloud`() {
        val h = heard("plain_question")
        assertTrue(h.memoryAloud)
        // The fixture predates the field: missing reads as false.
        assertFalse(h.sensitiveAloud)
        assertFalse(may(h, header("plain", injected = 3, sensitive = 1)))
        assertTrue(may(h, header("plain", injected = 3, sensitive = 0)))
        // A PC that does not say which facts were sensitive: on screen.
        assertFalse(may(h, header("plain", injected = 3)))
    }

    @Test
    fun `even voice check is enough keeps a sensitive fact on screen`() {
        val h = heard("voice_is_enough")
        assertTrue(h.privateAloud)
        assertFalse(may(h, header("plain", injected = 2, sensitive = 1)))
        assertFalse(may(h, header("plain", injected = 2)))
        // ...until the owner chose to hear them, and this voice passed a real check.
        assertTrue(may(heardWith("voice_is_enough", sensitiveAloud = true), header("plain", injected = 2, sensitive = 1)))
    }

    @Test
    fun `sensitive aloud opens only the sensitive step, nothing else`() {
        val h = heardWith("plain_question", sensitiveAloud = true)
        assertTrue(h.sensitiveAloud)
        assertTrue(may(h, header("plain", injected = 2, sensitive = 2)))
        // Missing count, facts in it: also allowed - the owner said sensitive ones may be read.
        assertTrue(may(h, header("plain", injected = 2)))
        // Email, notes, the router's private gate and tools still stay on screen.
        assertFalse(may(heardWith("private_question", sensitiveAloud = true), header("no_cloud_lane")))
        assertFalse(may(h, header("private", injected = 2, sensitive = 2)))
        assertFalse(may(h, header("plain", injected = 2, sensitive = 2), live.copy(runs = 5, privateRuns = 5)))
        // With memories kept on screen, facts in the answer still keep it there.
        assertFalse(may(heardWith("memory_on_screen", sensitiveAloud = true), header("plain", injected = 2, sensitive = 2)))
    }

    @Test
    fun `before the header arrives nothing is read`() {
        assertFalse(PrivateAloud.mayRead(heard("plain_question"), null, live, live))
    }

    @Test
    fun `which step events mean a tool ran`() {
        fun step(phase: String) = JsonObject(mapOf("phase" to JsonPrimitive(phase), "tool" to JsonPrimitive("email")))
        assertTrue(PrivateAloud.isToolRun(step("tool_started")))
        assertTrue(PrivateAloud.isToolRun(step("tool_finished")))
        assertFalse(PrivateAloud.isToolRun(step("tool_refused")))
        assertFalse(PrivateAloud.isToolRun(step("model")))
        assertFalse(PrivateAloud.isToolRun(null))
        // Private: every name but web search and home status, and no name.
        assertTrue(PrivateAloud.isPrivateToolRun(step("tool_started")))
        fun ran(tool: String) = JsonObject(mapOf("phase" to JsonPrimitive("tool_finished"), "tool" to JsonPrimitive(tool)))
        assertFalse(PrivateAloud.isPrivateToolRun(ran("web_search")))
        assertFalse(PrivateAloud.isPrivateToolRun(ran("home_read")))
        assertTrue(PrivateAloud.isPrivateToolRun(ran("calendar_read")))
        assertTrue(PrivateAloud.isPrivateToolRun(ran("unknown")))
        assertTrue(PrivateAloud.isPrivateToolRun(JsonObject(mapOf("phase" to JsonPrimitive("tool_started")))))
        val refused = JsonObject(mapOf("phase" to JsonPrimitive("tool_refused"), "tool" to JsonPrimitive("email_check")))
        assertFalse(PrivateAloud.isPrivateToolRun(refused))
    }

    @Test
    fun `an unreadable header says nothing either way`() {
        assertEquals(PrivateAloud.SILENT_ROUTE, PrivateAloud.route("not json"))
        assertEquals(PrivateAloud.SILENT_ROUTE, PrivateAloud.route(""))
        assertEquals("It's on your screen.", PrivateAloud.ON_SCREEN)
    }

    // --------------- the phone's remembered-facts setting (owner, 2026-11-05) --

    @Test
    fun `the phone's memory setting is on by default, and needs an unlocked press`() {
        // The shipped default, said in code: ON since the owner's decision of
        // 2026-11-07 ("i wanted to read everything out loud ... unless it's
        // extremely sensitive information").
        assertTrue(PrivateAloud.MEMORY_ALOUD_DEFAULT)
        val h = heard("quick_message")
        assertEquals("quick_message", h.mode)
        // The PC's reply for this clip: memory_aloud false because the talk
        // button runs no voice check, whatever the PC's own setting says.
        assertFalse(h.memoryAloud)
        val facts = header("plain", injected = 3, sensitive = 0)
        // Off: the answer that used 3 remembered facts stays on screen.
        assertFalse(may(h, facts))
        // The setting alone is NOT enough on a phone that was locked...
        assertFalse(may(h, facts, phoneMemoryAloud = true))
        // ...and it is enough on an unlocked phone - no talk-button condition
        // any more (2026-11-07), so Live and "hey Jarvis" are covered too.
        assertTrue(may(h, facts, phoneMemoryAloud = true, unlockedAtPress = true))
        // A screen read still keeps it on screen even with all of that.
        assertFalse(
            may(
                h, facts, live.copy(screenRuns = 1),
                phoneMemoryAloud = true, unlockedAtPress = true,
            ),
        )
        // An answer with no remembered facts is unaffected either way.
        assertTrue(may(h, header("plain"), phoneMemoryAloud = true, unlockedAtPress = true))
    }

    @Test
    fun `the phone's memory setting never reads a sensitive saved fact, and fails closed without the count`() {
        val h = heard("quick_message")
        val setting = true
        // One of the three facts is sensitive: on screen.
        assertFalse(
            may(h, header("plain", injected = 3, sensitive = 1), phoneMemoryAloud = setting, talkButton = true, unlockedAtPress = true),
        )
        // A PC that does not say which facts were sensitive: every one counts
        // as possibly sensitive - on screen.
        assertFalse(
            may(h, header("plain", injected = 3), phoneMemoryAloud = setting, talkButton = true, unlockedAtPress = true),
        )
        assertEquals(
            PrivateAloud.Refusal.SENSITIVE,
            PrivateAloud.refusal(
                privateAloud = false, questionPrivate = false,
                route = PrivateAloud.route(header("plain", injected = 3, sensitive = 1)),
                toolRan = false, toolsKnown = true,
                phoneMemoryAloud = setting, talkButton = true, unlockedAtPress = true,
            ),
        )
    }

    @Test
    fun `a private question or the router's private gate still keeps it on screen`() {
        val h = heard("quick_message")
        val setting = true
        // The PC's own words were about something private.
        assertFalse(
            may(heard("private_question"), header("plain", injected = 3, sensitive = 0), phoneMemoryAloud = setting, talkButton = true, unlockedAtPress = true),
        )
        // The router's gate.
        assertFalse(
            may(h, header("private", injected = 3, sensitive = 0), phoneMemoryAloud = setting, talkButton = true, unlockedAtPress = true),
        )
    }

    @Test
    fun `a private tool or a stream that could not say still keeps it on screen`() {
        val h = heard("quick_message")
        val facts = header("plain", injected = 3, sensitive = 0)
        val setting = true
        // A private tool ran while the answer was written.
        assertFalse(
            may(h, facts, live.copy(runs = 5, privateRuns = 5), phoneMemoryAloud = setting, talkButton = true, unlockedAtPress = true),
        )
        // The stream dropped, or is not live now: unknown counts as a tool.
        assertFalse(
            may(h, facts, live.copy(drops = 2), phoneMemoryAloud = setting, talkButton = true, unlockedAtPress = true),
        )
        assertFalse(
            may(h, facts, live.copy(live = false), phoneMemoryAloud = setting, talkButton = true, unlockedAtPress = true),
        )
    }

    @Test
    fun `the phone's setting keeps an answer about the screen on screen`() {
        // The PC's own `screen_aloud` for a talk-button clip is true, so the
        // screen rule by itself would let this through. The owner's condition
        // list of 2026-11-05 says the memory setting does not buy a screen
        // answer: no screen read.
        assertEquals(
            PrivateAloud.Refusal.MEMORY,
            PrivateAloud.refusal(
                privateAloud = false, questionPrivate = false,
                route = PrivateAloud.route(header("plain", injected = 3, sensitive = 0)),
                toolRan = false, toolsKnown = true,
                screenRead = true, screenAloud = true,
                phoneMemoryAloud = true, talkButton = true, unlockedAtPress = true,
            ),
        )
        // ...while a memory answer that read nothing on screen still is.
        assertTrue(
            may(
                heard("quick_message"),
                header("plain", injected = 3, sensitive = 0),
                live,
                phoneMemoryAloud = true,
                talkButton = true,
                unlockedAtPress = true,
            ),
        )
    }

    @Test
    fun `the phone's setting covers every voice answer - mic, hey Jarvis and Live`() {
        val facts = header("plain", injected = 3, sensitive = 0)
        // A "hey Jarvis" or Jarvis Live turn carries talkButton = false. Since
        // the owner's decision of 2026-11-07 that is no longer a blocker: on an
        // unlocked phone, the setting lifts the memory rule for it too.
        assertTrue(
            may(heard("quick_message"), facts, phoneMemoryAloud = true, talkButton = false, unlockedAtPress = true),
        )
        // A LOCKED phone is still a hard refusal on every path.
        assertFalse(
            may(heard("quick_message"), facts, phoneMemoryAloud = true, talkButton = false, unlockedAtPress = false),
        )
        // The caller still only sets talkButton for the press itself, which is
        // what the WORDS say about the rule (and what the refusal hints use);
        // the rule no longer depends on it.
        assertEquals("quick_message", PrivateAloud.QUICK_MESSAGE)
        assertEquals("owner", heard("plain_question").mode)
        assertTrue(heard("quick_message").mode == PrivateAloud.QUICK_MESSAGE)
    }

    @Test
    fun `the memory refusal has its own words and every other refusal keeps the one line`() {
        assertEquals("That answer used things I remember, so it's on your screen.", PrivateAloud.MEMORY_ON_SCREEN)
        assertTrue(PrivateAloud.MEMORY_ON_SCREEN != PrivateAloud.ON_SCREEN)
        assertEquals(PrivateAloud.MEMORY_ON_SCREEN, PrivateAloud.refusalLine(PrivateAloud.Refusal.MEMORY))
        for (other in PrivateAloud.Refusal.entries) {
            if (other == PrivateAloud.Refusal.MEMORY) continue
            assertEquals(other.name, PrivateAloud.ON_SCREEN, PrivateAloud.refusalLine(other))
        }
        // It is not a card line and never takes the desktop's fixed line's
        // place: `CardVoice.isCardLine` and the shared `on_screen` are
        // untouched (the fixed-line contract tests).
        assertFalse(com.jarvis.client.voice.CardVoice.isCardLine(PrivateAloud.MEMORY_ON_SCREEN))
        assertFalse(com.jarvis.client.voice.CardVoice.isCardLine(PrivateAloud.ON_SCREEN))
        assertEquals(PrivateAloud.ON_SCREEN, com.jarvis.client.voice.ReadAloud.ON_SCREEN)
    }

    @Test
    fun `the phone's setting never speaks a case the shared table keeps on screen`() {
        // The setting is a switch, not a rule change: with it OFF (the
        // shipped default) every remembered-fact case behaves exactly as the
        // shared table says.
        assertFalse(may(heard("quick_message"), header("plain", injected = 2, sensitive = 0)))
        assertFalse(may(heard("memory_on_screen"), header("plain", injected = 2, sensitive = 0)))
        // And a sensitive fact is still on screen with every other door open.
        assertFalse(
            may(
                heard("quick_message"),
                header("plain", injected = 2, sensitive = 1),
                live,
                phoneMemoryAloud = true,
                talkButton = true,
                unlockedAtPress = true,
            ),
        )
    }

    // ------------- the owner's own okay (his decision of 2026-11-06) --------

    @Test
    fun `the phone's setting still never lifts a screen read on the voice path`() {
        // The 2026-11-06 one-off is a TYPED-answer action (ReadAloud). The
        // voice path's screen rule stays the PC's own `screen_aloud` /
        // `hands_free_screen`, and the phone's memory setting cannot pass it.
        assertEquals(
            PrivateAloud.Refusal.SCREEN,
            PrivateAloud.refusal(
                privateAloud = false, questionPrivate = false,
                route = PrivateAloud.route(header("plain", injected = 3, sensitive = 0)),
                toolRan = false, toolsKnown = true,
                screenRead = true, screenAloud = false,
                phoneMemoryAloud = true, talkButton = true, unlockedAtPress = true,
            ),
        )
        // The same screen read WITHOUT injected facts: still a hard refusal.
        assertEquals(
            PrivateAloud.Refusal.SCREEN,
            PrivateAloud.refusal(
                privateAloud = false, questionPrivate = false,
                route = PrivateAloud.route(header("plain")),
                toolRan = false, toolsKnown = true,
                screenRead = true, screenAloud = false,
                phoneMemoryAloud = true, talkButton = true, unlockedAtPress = true,
            ),
        )
    }

    @Test
    fun `the memory line names the phone switch only while that switch is off`() {
        // The 2026-11-05 sentence stays exactly what he knows, alone.
        assertEquals(PrivateAloud.MEMORY_ON_SCREEN, PrivateAloud.refusalLine(PrivateAloud.Refusal.MEMORY))
        assertEquals(
            PrivateAloud.MEMORY_ON_SCREEN + " " + PrivateAloud.MEMORY_SWITCH_HINT,
            PrivateAloud.refusalLine(PrivateAloud.Refusal.MEMORY, phoneMemoryAloud = false),
        )
        // Switch on: "turn it on" would be wrong, so only the sentence.
        assertEquals(
            PrivateAloud.MEMORY_ON_SCREEN,
            PrivateAloud.refusalLine(PrivateAloud.Refusal.MEMORY, phoneMemoryAloud = true),
        )
        // Never for another refusal - the switch is not why those are refused.
        assertEquals(
            PrivateAloud.ON_SCREEN,
            PrivateAloud.refusalLine(PrivateAloud.Refusal.SCREEN, phoneMemoryAloud = false),
        )
        assertEquals(
            PrivateAloud.ON_SCREEN,
            PrivateAloud.refusalLine(PrivateAloud.Refusal.TOOL, phoneMemoryAloud = false),
        )
        // The hint names the actual button on the settings row, in plain words.
        assertTrue(PrivateAloud.MEMORY_SWITCH_HINT, "Read them out" in PrivateAloud.MEMORY_SWITCH_HINT)
        assertEquals(MemoryAloud.TURN_ON, "Read them out")
    }
}
