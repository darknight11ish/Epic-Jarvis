package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.VoiceStatus
import com.jarvis.client.voice.BargeVerdict
import com.jarvis.client.voice.HeardSound
import com.jarvis.client.voice.InterruptFlow
import com.jarvis.client.voice.MomentFlow
import com.jarvis.client.voice.OneMoment
import com.jarvis.client.voice.SpeechRun
import com.jarvis.client.voice.VoiceFlow
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.double
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The voice flow's rules on the phone (voice/VoiceFlow.kt): interrupting by
 * talking, "One moment.", "I heard you" and `waited_ms`. The cases are
 * `jarvis-desktop/tests/fixtures/voice-flow-cases.json`, the same file the
 * desktop's tests/voice-flow.mjs reads - one copy, so the two apps cannot
 * drift apart.
 */
class VoiceFlowTest {

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private val cases: JsonObject by lazy {
        JarvisJson.parseToJsonElement(
            repoFile("jarvis-desktop/tests/fixtures/voice-flow-cases.json").readText(),
        ).jsonObject
    }

    @Test
    fun theNumbersAreTheSharedOnes() {
        val n = cases["numbers"]!!.jsonObject
        assertEquals(n["grace_ms"]!!.jsonPrimitive.long, VoiceFlow.GRACE_MS)
        assertEquals(n["onset_ms"]!!.jsonPrimitive.long, VoiceFlow.ONSET_MS)
        assertEquals(n["clip_ms"]!!.jsonPrimitive.long, VoiceFlow.CLIP_MS)
        assertEquals(n["end_quiet_ms"]!!.jsonPrimitive.long, VoiceFlow.END_QUIET_MS)
        assertEquals(n["wait_max_ms"]!!.jsonPrimitive.long, VoiceFlow.WAIT_MAX_MS)
    }

    @Test
    fun interruptingFollowsEverySharedCase() {
        for (c in cases["interrupt"]!!.jsonArray) {
            val name = c.jsonObject["name"]!!.jsonPrimitive.content
            val flow = InterruptFlow()
            c.jsonObject["steps"]!!.jsonArray.forEachIndexed { i, el ->
                val s = el.jsonObject
                val at = s["at"]?.jsonPrimitive?.long ?: 0L
                val got: VoiceFlow.Action? = when (val what = s["do"]!!.jsonPrimitive.content) {
                    "reply_started" -> { flow.replyStarted(at); null }
                    "reply_ended" -> { flow.replyEnded(); null }
                    "onset" -> flow.onset(at, s["id"]!!.jsonPrimitive.long, s["allowed"]!!.jsonPrimitive.boolean)
                    "verdict" -> flow.verdict(s["id"]!!.jsonPrimitive.long, s["stop"]!!.jsonPrimitive.boolean)
                    "tick" -> flow.tick(at)
                    else -> error("unknown step $what")
                }
                s["expect"]?.let { want ->
                    assertEquals("$name, step ${i + 1}", want.jsonPrimitive.content, got?.name?.lowercase())
                }
            }
        }
    }

    @Test
    fun oneMomentFollowsEverySharedCase() {
        for (c in cases["moment"]!!.jsonArray) {
            val name = c.jsonObject["name"]!!.jsonPrimitive.content
            val flow = MomentFlow()
            c.jsonObject["steps"]!!.jsonArray.forEachIndexed { i, el ->
                val s = el.jsonObject
                var got: Boolean? = null
                when (val what = s["do"]!!.jsonPrimitive.content) {
                    "turn_started" -> flow.turnStarted()
                    "turn_ended" -> flow.turnEnded()
                    "reply_started" -> flow.replyStarted()
                    "stopped" -> flow.stopped()
                    "tool_started" -> got = flow.toolStarted(
                        s["enabled"]!!.jsonPrimitive.boolean,
                        s["ready"]!!.jsonPrimitive.boolean,
                    )
                    else -> error("unknown step $what")
                }
                s["expect"]?.let { assertEquals("$name, step ${i + 1}", it.jsonPrimitive.boolean, got) }
            }
        }
        assertTrue(VoiceFlow.isToolStart(buildJsonObject { put("phase", "tool_started"); put("tool", "email_read") }))
        assertFalse(VoiceFlow.isToolStart(buildJsonObject { put("phase", "tool_finished") }))
        assertFalse(VoiceFlow.isToolStart(null))
    }

    @Test
    fun heardSoundIsTheDesktopsSound() {
        val h = cases["heard_sound"]!!.jsonObject
        assertEquals(h["rate"]!!.jsonPrimitive.int, HeardSound.RATE)
        val tones = h["tones"]!!.jsonArray.map { it.jsonObject["hz"]!!.jsonPrimitive.int to it.jsonObject["ms"]!!.jsonPrimitive.int }
        assertEquals(tones, HeardSound.TONES)
        assertEquals(h["gap_ms"]!!.jsonPrimitive.int, HeardSound.GAP_MS)
        assertEquals(h["fade_ms"]!!.jsonPrimitive.int, HeardSound.FADE_MS)
        assertEquals(h["gain"]!!.jsonPrimitive.double, HeardSound.GAIN, 0.0)
        val s = HeardSound.samples()
        assertEquals(h["samples"]!!.jsonPrimitive.int, s.size)
        val peak = HeardSound.peak(s)
        val most = h["peak_at_most"]!!.jsonPrimitive.int
        assertTrue("peak $peak", peak <= most && peak > most * 0.9)
        assertEquals(0, s.first().toInt())
        assertEquals(0, s.last().toInt())
    }

    @Test
    fun oneMomentSwitchUsesTheDesktopsWords() {
        val js = repoFile("jarvis-desktop/src/voice-flow.js").readText()
        for (on in listOf(true, false)) {
            val line = "\"" + OneMoment.describe(on).replace("\"", "\\\"") + "\""
            assertTrue("voice-flow.js says $line", js.contains(line))
        }
        assertTrue(js.contains("\"Say \\\"One moment\\\" if I'm kept waiting\""))
        assertEquals("Say \"One moment\" if I'm kept waiting", OneMoment.NAME)
    }

    @Test
    fun heardSoundSwitchUsesTheDesktopsWords() {
        val js = repoFile("jarvis-desktop/src/voice-flow.js").readText()
        for (on in listOf(true, false)) {
            val line = "\"" + HeardSound.describe(on).replace("\"", "\\\"") + "\""
            assertTrue("voice-flow.js says $line", js.contains(line))
        }
        assertEquals("Play a short sound when I finish speaking", HeardSound.NAME)
        assertTrue(js.contains("\"" + HeardSound.NAME + "\""))
        assertTrue(HeardSound.describe(true).startsWith("On:"))
        assertTrue(HeardSound.describe(false).startsWith("Off:"))
    }

    /**
     * The switch's plumbing, read from the source (it needs Android to run):
     * on by default, stored apart from "One moment", and [VoiceSession.heardYou]
     * - the one place every "I heard you" goes through - asks it first.
     */
    @Test
    fun heardSoundSwitchIsOffByDefaultAndGatesTheSound() {
        val settings = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/data/ClientSettings.kt").readText()
        assertTrue(settings.contains("prefs.getBoolean(KEY_HEARD_SOUND, false)"))
        assertTrue(settings.contains("const val KEY_HEARD_SOUND = \"heard_sound\""))
        val session = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/voice/VoiceSession.kt").readText()
        val body = session.substringAfter("fun heardYou() {").substringBefore("\n    }")
        assertTrue(body, body.trimStart().startsWith("if (!heardSoundOn()) return"))
        assertTrue(body, body.contains("speaker.playTone("))
        assertEquals("the sound is played in one place only", 1, Regex("speaker\\.playTone\\(").findAll(session).count())
        val runtime = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt").readText()
        assertTrue(runtime.contains("heardSoundOn = { clientSettings.heardSound.value }"))
    }

    // -- Keep listening after a question, and the cut-off note ---------------

    @Test
    fun aQuestionIsTheSharedCasesQuestion() {
        val marks = cases["question_marks"]!!.jsonArray.map { it.jsonPrimitive.content.single() }
        assertEquals(marks, VoiceFlow.QUESTION_MARKS)
        for (c in cases["question_cases"]!!.jsonArray) {
            val text = c.jsonObject["text"]!!.jsonPrimitive.content
            val want = c.jsonObject["question"]!!.jsonPrimitive.boolean
            assertEquals("\"$text\"", want, VoiceFlow.endsWithQuestion(text))
        }
        assertFalse(VoiceFlow.endsWithQuestion(null))
    }

    @Test
    fun theCutOffSentenceGoesOnceWithTheNextQuestionOnly() {
        val cut = com.jarvis.client.voice.CutOff()
        assertNull(cut.take(0))
        cut.cut("  Tomorrow looks mild, with light rain.  ", 1_000)
        assertEquals("Tomorrow looks mild, with light rain.", cut.take(5_000))
        assertNull("once only", cut.take(6_000))
        cut.cut("It clears by noon.", 1_000)
        assertNull("not a reply two minutes later", cut.take(1_000 + com.jarvis.client.voice.CutOff.KEEP_MS + 1))
        cut.cut("", 1_000)
        cut.cut(null, 1_000)
        assertNull(cut.take(1_001))

        // On the newest user message only, never on the history it replays.
        val window = listOf(com.jarvis.client.net.ChatHistory.Exchange("what is the weather", "Mild. Rain later. Coat."))
        val asking = com.jarvis.client.net.ChatHistory.asking("and the weekend", "voice")
        val body = JarvisJson.parseToJsonElement(
            com.jarvis.client.net.ChatHistory.requestBody(window, asking, interrupted = "Mild."),
        ).jsonObject
        val msgs = body["messages"]!!.jsonArray.map { it.jsonObject }
        assertEquals("Mild.", msgs.last()["interrupted"]!!.jsonPrimitive.content)
        assertEquals("voice", msgs.last()["provenance"]!!.jsonPrimitive.content)
        assertEquals(1, msgs.count { it.containsKey("interrupted") })
        val plain = JarvisJson.parseToJsonElement(
            com.jarvis.client.net.ChatHistory.requestBody(window, asking),
        ).jsonObject["messages"]!!.jsonArray
        assertTrue(plain.none { it.jsonObject.containsKey("interrupted") })
    }

    // -- The speech detector over a reply (loudness only) --------------------

    private fun run(levels: List<Float>, stepMs: Long = 80): List<Pair<Long, SpeechRun.Event>> {
        val r = SpeechRun()
        val out = mutableListOf<Pair<Long, SpeechRun.Event>>()
        levels.forEachIndexed { i, level ->
            val now = (i + 1) * stepMs
            val e = r.step(now, level, stepMs)
            if (e != SpeechRun.Event.NONE) out.add(now to e)
        }
        return out
    }

    private val quiet = 0.002f
    private val loud = 0.2f

    @Test
    fun halfASecondOfSpeechIsAnOnsetAndTwoSecondsAClip() {
        val events = run(List(10) { quiet } + List(40) { loud })
        assertEquals(2, events.size)
        val (onsetAt, onset) = events[0]
        val (clipAt, clip) = events[1]
        assertEquals(SpeechRun.Event.ONSET, onset)
        assertEquals(SpeechRun.Event.CLIP_DUE, clip)
        // Speech began with step 11 (80 ms each): 880 ms in, from 800.
        assertEquals(800L + 560L, onsetAt) // 7 steps = 560 ms >= 500
        assertEquals(800L + 2000L, clipAt)
    }

    @Test
    fun speechThatStopsEarlyIsSentWhenItEnds() {
        val events = run(List(5) { quiet } + List(8) { loud } + List(12) { quiet })
        assertEquals(listOf(SpeechRun.Event.ONSET, SpeechRun.Event.CLIP_DUE), events.map { it.second })
        val lastLoudAt = (5 + 8) * 80L
        assertTrue("sent ${events[1].first}", events[1].first >= lastLoudAt + VoiceFlow.END_QUIET_MS)
        assertTrue(events[1].first < lastLoudAt + VoiceFlow.END_QUIET_MS + 80)
    }

    @Test
    fun aCoughIsForgottenAndNeverAnOnset() {
        assertEquals(emptyList<Pair<Long, SpeechRun.Event>>(), run(List(3) { loud } + List(20) { quiet } + List(3) { loud } + List(20) { quiet }))
    }

    // -- waited_ms ---------------------------------------------------------

    @Test
    fun theQuietAtTheEndOfAClipIsWaitedMs() {
        val loudPart = ShortArray(16_000) { (if (it % 2 == 0) 8000 else -8000).toShort() }
        val clip = ShortArray(4_800) { 20.toShort() } + loudPart + ShortArray(9_600) { 20.toShort() }
        val q = VoiceFlow.trailingQuietMs(clip)!!
        assertTrue("$q", q in 570L..630L)
        assertNull(VoiceFlow.trailingQuietMs(ShortArray(16_000)))
        assertNull(VoiceFlow.trailingQuietMs(ShortArray(0)))
        assertEquals(0L, VoiceFlow.trailingQuietMs(ShortArray(4_800) { 20.toShort() } + loudPart))
    }

    // -- The PC's answers --------------------------------------------------

    private fun obj(text: String) = JarvisJson.parseToJsonElement(text).jsonObject

    @Test
    fun theBargeInAnswerIsReadAndAnythingElseCarriesOn() {
        val yes = BargeVerdict.read(obj("""{"stop": true, "available": true, "source": "barge_in", "why": "owner_voice", "reason": "your voice"}"""))
        assertEquals(BargeVerdict(stop = true, available = true, why = "owner_voice"), yes)
        val off = BargeVerdict.read(obj("""{"stop": false, "available": false, "why": "off"}"""))
        assertFalse(off.stop)
        assertFalse(off.available)
        // A route without voice-flow.patch: the usual utterance reply.
        assertTrue(BargeVerdict.read(obj("""{"ok": false, "text": "", "stop": true}""")).stop)
        assertEquals(BargeVerdict.FAILED, BargeVerdict.read(null))
        assertFalse(BargeVerdict.read(obj("""{"stop": "true"}""")).stop)
    }

    @Test
    fun anOlderPcHasNoFlowAndAllowsNothing() {
        val old = JarvisJson.decodeFromString(VoiceStatus.serializer(), """{"available": true, "listening": {"push_to_talk": true}}""")
        assertFalse(old.flow.available)
        assertFalse(old.flow.bargeIn.available)
        assertFalse(old.flow.moment.enabled)
        assertFalse(old.bargeInUsable)
        val now = JarvisJson.decodeFromString(
            VoiceStatus.serializer(),
            """{"available": true, "flow": {"available": true,
               "barge_in": {"enabled": true, "available": true, "why": "", "min_seconds": 1.0, "bar": "balanced", "stop_word": true},
               "moment": {"enabled": true, "text": "One moment.", "key": "k1", "ready": true, "voice": "builtin",
                          "engine": "kokoro", "seconds": 0.8, "after_ms": 1000, "why": ""},
               "warm": {"enabled": true, "state": "ready"}, "timings": [], "summary": [],
               "after_question": true, "cut_off": true}}""",
        )
        assertTrue(now.flow.afterQuestion)
        assertTrue(now.flow.cutOff)
        assertFalse(old.flow.afterQuestion)
        assertFalse(old.flow.cutOff)
        assertTrue(now.bargeInUsable)
        assertTrue(now.momentUsable)
        assertEquals("k1", now.flow.moment.key)
        val cannot = now.copy(flow = now.flow.copy(bargeIn = now.flow.bargeIn.copy(available = false)))
        assertFalse(cannot.bargeInUsable)
        val offPc = now.copy(flow = now.flow.copy(available = false))
        assertFalse(offPc.bargeInUsable)
        assertFalse(offPc.momentUsable)
    }
}
