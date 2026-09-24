package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.VoiceStatus
import com.jarvis.client.net.VoiceStrict
import com.jarvis.client.net.VoiceTrainingLast
import com.jarvis.client.voice.StrictVoice
import com.jarvis.client.voice.VoiceTraining
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
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
 * The stricter voice check on the phone: reading `/api/voice/status`, the
 * PC's answers to the two settings and the guided test, and the words.
 *
 * Every status and answer below is the PC's REAL output, from
 * `contract/phone-voice-cases.json` (tools/gen_phone_voice_cases.py runs
 * jarvis_speech.status() and jarvis_voice_enroll.stage() to make it). The
 * one exception is said where it is made: an older PC's status is a real
 * one with the three new flags taken OUT, which is what an older PC sends.
 */
class VoiceStrictTest {

    private val strict: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/phone-voice-cases.json")) {
            "contract/phone-voice-cases.json is missing - run tools/gen_phone_voice_cases.py"
        }.readText()
        (JarvisJson.parseToJsonElement(text) as JsonObject)["strict"]!!.jsonObject
    }

    private fun status(case: String): JsonObject = strict["status"]!!.jsonObject[case]!!.jsonObject

    private fun view(case: String) = VoiceStrict.parse(status(case))

    private fun answer(case: String): VoiceStrict.Answer {
        val a = strict["answers"]!!.jsonObject[case]!!.jsonObject
        return VoiceStrict.answer(a["status"]!!.jsonPrimitive.int, a["body"]!!.jsonObject)
    }

    private fun trainingLast(case: String): VoiceTrainingLast? =
        JarvisJson.decodeFromJsonElement(VoiceStatus.serializer(), status(case)).gate.training.last

    // ------------------------------------------------------------ reading --

    @Test
    fun `every real status reads both halves, and the talk-button half is unchanged`() {
        for (case in strict["status"]!!.jsonObject.keys) {
            val read = VoiceStrict.read(status(case))
            assertTrue(case, read is ApiResult.Ok)
            val (st, v) = (read as ApiResult.Ok).value
            // The same VoiceStatus the old typed read produced.
            assertEquals(case, JarvisJson.decodeFromJsonElement(VoiceStatus.serializer(), status(case)), st)
            assertTrue(case, v.rounds && v.settings && v.measure)
            assertTrue(case, v.strictness in setOf(VoiceStrict.VERY_STRICT, VoiceStrict.BALANCED))
        }
    }

    @Test
    fun `available false is not a status to show`() {
        val body = JsonObject(status("strong_untrained") + ("available" to JsonPrimitive(false)))
        val read = VoiceStrict.read(body)
        assertEquals(ApiResult.Failed(ApiError.NotAvailable), read)
    }

    @Test
    fun `an older PC - the three flags taken out of a real status - offers none of the new modes`() {
        val real = status("strong_untrained")
        val gate = real["gate"]!!.jsonObject
        val training = JsonObject(gate["training"]!!.jsonObject - setOf("rounds", "settings", "measure"))
        val older = JsonObject(real + ("gate" to JsonObject(gate + ("training" to training))))
        val v = VoiceStrict.parse(older)
        assertFalse(v.rounds)
        assertFalse(v.settings)
        assertFalse(v.measure)
        assertNull(StrictVoice.modelLine(v))
        assertEquals(StrictVoice.NOT_ON_THIS_PC, StrictVoice.blocker(VoiceStrict.STRICTNESS, VoiceStrict.BALANCED, v, null))
    }

    @Test
    fun `the settings, the models and the round words come from the PC`() {
        val v = view("trained_three_rounds")
        assertEquals(VoiceStrict.VERY_STRICT, v.strictness)
        assertEquals(VoiceStrict.PRIVATE_ON_SCREEN, v.privacy)
        assertTrue(v.voiceIsEnoughAllowed)
        assertEquals(2.0, v.minCommandSeconds, 0.0)
        assertEquals("strong", v.veryStrictModel)
        assertEquals("further away from the microphone, or quieter", v.roundAsks[2])
        assertEquals(12, v.limits.maxClips)
        assertEquals(20, v.limits.measureMaxClips)
        assertEquals(80.0, v.limits.maxTotalSeconds, 0.0)
        assertEquals(listOf(VoiceStrict.Outlier(2, 5)), v.last!!.outliers)
    }

    @Test
    fun `a held round and a waiting setting card are read`() {
        val held = view("round_held").session!!
        assertEquals(12, held.clips)
        assertEquals(listOf(1), held.rounds.map { it.round })
        assertEquals("close", held.rounds[0].condition)
        val waiting = view("setting_waiting")
        assertEquals("setting", waiting.pendingKind)
        assertEquals(VoiceStrict.PRIVACY, waiting.pendingSetting)
        assertEquals(VoiceStrict.VOICE_IS_ENOUGH, waiting.pendingValue)
        assertEquals(
            "Waiting for your approval to change this to \"Voice check is enough\". " +
                "Approve it on your PC or on this phone's Home screen.",
            StrictVoice.waitingLine(VoiceStrict.PRIVACY, waiting),
        )
        assertNull(StrictVoice.waitingLine(VoiceStrict.STRICTNESS, waiting))
    }

    // ----------------------------------------------------- the two settings --

    @Test
    fun `loosening is held on a stale link, tightening never is`() {
        val v = view("trained_three_rounds")
        val stale = "Not connected to the desktop, so this cannot be delivered."
        assertEquals(stale, StrictVoice.blocker(VoiceStrict.STRICTNESS, VoiceStrict.BALANCED, v, stale))
        assertEquals(stale, StrictVoice.blocker(VoiceStrict.PRIVACY, VoiceStrict.VOICE_IS_ENOUGH, v, stale))
        val b = view("balanced")
        assertNull(StrictVoice.blocker(VoiceStrict.STRICTNESS, VoiceStrict.VERY_STRICT, b, stale))
        val loose = view("voice_is_enough")
        assertNull(StrictVoice.blocker(VoiceStrict.PRIVACY, VoiceStrict.PRIVATE_ON_SCREEN, loose, stale))
    }

    @Test
    fun `voice is enough is only offered while very strict - as the PC itself refuses`() {
        val b = view("balanced")
        assertEquals(
            StrictVoice.PRIVACY_ONLY_VERY_STRICT,
            StrictVoice.blocker(VoiceStrict.PRIVACY, VoiceStrict.VOICE_IS_ENOUGH, b, null),
        )
        // ...and the PC's own answer when asked anyway.
        val refused = answer("privacy_while_balanced")
        assertEquals(409, refused.code)
        assertFalse(refused.accepted)
        assertEquals(
            "Private answers can only be read aloud while the voice check is very strict - make it very strict first.",
            StrictVoice.answerLine(refused),
        )
    }

    @Test
    fun `the setting bodies are the PC's own modes`() {
        assertEquals("{\"mode\":\"strictness\",\"value\":\"balanced\"}",
            VoiceStrict.settingBody(VoiceStrict.STRICTNESS, VoiceStrict.BALANCED))
        assertEquals("{\"mode\":\"privacy\",\"value\":\"voice_is_enough\"}",
            VoiceStrict.settingBody(VoiceStrict.PRIVACY, VoiceStrict.VOICE_IS_ENOUGH))
        assertTrue(VoiceStrict.isLoosening(VoiceStrict.STRICTNESS, VoiceStrict.BALANCED))
        assertTrue(VoiceStrict.isLoosening(VoiceStrict.PRIVACY, VoiceStrict.VOICE_IS_ENOUGH))
        assertFalse(VoiceStrict.isLoosening(VoiceStrict.STRICTNESS, VoiceStrict.VERY_STRICT))
        assertFalse(VoiceStrict.isLoosening(VoiceStrict.PRIVACY, VoiceStrict.PRIVATE_ON_SCREEN))
    }

    @Test
    fun `loosening answers 202 and is shown as waiting, never as done`() {
        for (case in listOf("strictness_loosen", "privacy_loosen")) {
            val a = answer(case)
            assertEquals(case, 202, a.code)
            assertTrue(case, a.pending)
            assertEquals(
                case,
                "Waiting for your approval. Approve it on your PC or on this phone's Home screen. " +
                    "Nothing changes until you do.",
                StrictVoice.answerLine(a),
            )
        }
    }

    @Test
    fun `tightening applies at once, in the PC's words`() {
        val a = answer("strictness_tighten")
        assertEquals(200, a.code)
        assertTrue(a.changed)
        assertFalse(a.pending)
        assertEquals("Done - that applies now.", StrictVoice.answerLine(a))
        assertEquals("It was already set that way.", StrictVoice.answerLine(answer("strictness_same")))
        val busy = answer("setting_card_waiting")
        assertEquals(409, busy.code)
        assertEquals(
            "A voice card is already waiting for approval - approve or deny that one first.",
            StrictVoice.answerLine(busy),
        )
    }

    @Test
    fun `how a setting card ended is said about the setting, not about a training`() {
        val changed = view("balanced").last
        assertEquals("Approved: \"Balanced\" is on now.", StrictVoice.lastLine(changed))
        assertEquals(
            "Approved: \"Balanced\" is on now.",
            VoiceTraining.lastLine(trainingLast("balanced"), changed),
        )
        val denied = view("loosen_denied").last
        // "You said no" names what stays: very strict, read from the view...
        assertEquals(
            "You said no, so \"Very strict\" stays.",
            VoiceTraining.lastLine(trainingLast("loosen_denied"), denied, view("loosen_denied")),
        )
        // ...or, with no view, the other of the two choices.
        assertEquals("You said no, so \"Very strict\" stays.", StrictVoice.lastLine(denied))
        // Without the strict half the old line would have said "Last training".
        assertEquals("Last training was denied on the card. Nothing changed.",
            VoiceTraining.lastLine(trainingLast("loosen_denied")))
    }

    @Test
    fun `the last setting card is said in the desktop's words, memory included`() {
        fun last(setting: String, value: String, outcome: String) =
            VoiceStrict.Last(outcome = outcome, setting = setting, value = value)
        assertEquals(
            "Approved: \"Voice check is enough\" is on now.",
            StrictVoice.lastLine(view("voice_is_enough").last),
        )
        assertEquals(
            "Approved: \"Read aloud\" is on now.",
            StrictVoice.lastLine(last(VoiceStrict.MEMORY, VoiceStrict.MEMORY_ALOUD, "setting_changed")),
        )
        assertEquals(
            "You said no, so \"Stay on screen\" stays.",
            StrictVoice.lastLine(last(VoiceStrict.PRIVACY, VoiceStrict.VOICE_IS_ENOUGH, "denied")),
        )
        assertEquals(
            "You said no, so \"Keep on screen\" stays.",
            StrictVoice.lastLine(last(VoiceStrict.MEMORY, VoiceStrict.MEMORY_ALOUD, "denied")),
        )
        assertEquals(
            "You said no, so \"Keep on screen\" stays.",
            StrictVoice.lastLine(
                last(VoiceStrict.MEMORY, VoiceStrict.MEMORY_ALOUD, "denied"),
                view("trained_three_rounds").copy(memory = VoiceStrict.MEMORY_ON_SCREEN),
            ),
        )
        for (setting in listOf(VoiceStrict.STRICTNESS, VoiceStrict.PRIVACY, VoiceStrict.MEMORY)) {
            assertEquals(
                "Nobody answered the card in time, so nothing changed.",
                StrictVoice.lastLine(last(setting, "x", "timed_out")),
            )
            assertEquals(
                "You made it stricter while the card waited, so approving it changed nothing.",
                StrictVoice.lastLine(last(setting, "x", "withdrawn")),
            )
        }
    }

    @Test
    fun `the settings use the desktop's labels and details`() {
        assertEquals("How strict", StrictVoice.STRICTNESS_TITLE)
        assertEquals("Private answers asked by voice", StrictVoice.PRIVACY_TITLE)
        assertEquals("Answers that use what Jarvis remembers", StrictVoice.MEMORY_TITLE)
        assertEquals(
            listOf("Very strict (recommended)", "Balanced"),
            StrictVoice.STRICTNESS.map { it.label },
        )
        assertEquals(
            "Needs about 2 seconds of speech and a close match. Best at turning other people away; " +
                "now and then it may ask you to say it again. It tells your voice from other people's. " +
                "It cannot tell your voice from a recording or a copy of it.",
            StrictVoice.STRICTNESS[0].detail,
        )
        assertEquals(
            "Takes shorter commands (about 1.5 seconds) at a lower bar. You repeat yourself less, but " +
                "someone whose voice is close to yours gets in more easily. Private answers then always " +
                "stay on screen.",
            StrictVoice.STRICTNESS[1].detail,
        )
        assertEquals(
            listOf("Stay on screen (recommended)", "Voice check is enough"),
            StrictVoice.PRIVACY.map { it.label },
        )
        assertEquals(
            "When you ask by voice, answers from your email, calendar or notes are shown on screen, " +
                "not read aloud. Typing on your own PC or phone is not affected.",
            StrictVoice.PRIVACY[0].detail,
        )
        assertEquals(
            "Jarvis reads those answers aloud when your voice passes the very strict check. Anyone " +
                "near the speaker will hear them.",
            StrictVoice.PRIVACY[1].detail,
        )
        assertEquals(
            "\"Voice check is enough\" can only be chosen while the check is very strict.",
            StrictVoice.PRIVACY_ONLY_VERY_STRICT,
        )
        assertEquals(listOf("Read aloud (recommended)", "Keep on screen"), StrictVoice.MEMORY.map { it.label })
        assertEquals("Stay on screen", StrictVoice.label(VoiceStrict.PRIVACY, VoiceStrict.PRIVATE_ON_SCREEN))
    }

    @Test
    fun `both memory choices wait while voice check is enough`() {
        val loose = view("voice_is_enough")
        assertEquals(VoiceStrict.VOICE_IS_ENOUGH, loose.privacy)
        assertFalse(StrictVoice.settingOpen(VoiceStrict.MEMORY, loose))
        val note = "\"Voice check is enough\" already reads these answers aloud. Choose " +
            "\"Stay on screen\" above to use this setting."
        assertEquals(note, StrictVoice.MEMORY_WHILE_VOICE_IS_ENOUGH)
        // Both choices, tightening included, and whatever the link says.
        for (value in listOf(VoiceStrict.MEMORY_ALOUD, VoiceStrict.MEMORY_ON_SCREEN)) {
            assertEquals(value, note, StrictVoice.blocker(VoiceStrict.MEMORY, value, loose, null))
            assertEquals(value, note, StrictVoice.blocker(VoiceStrict.MEMORY, value, loose, "stale"))
            assertEquals(note, StrictVoice.blocker(VoiceStrict.MEMORY, value, loose.copy(memory = VoiceStrict.MEMORY_ON_SCREEN), null))
        }
        // The other two settings are not touched by it.
        assertTrue(StrictVoice.settingOpen(VoiceStrict.PRIVACY, loose))
        assertTrue(StrictVoice.settingOpen(VoiceStrict.STRICTNESS, loose))
        assertNull(StrictVoice.blocker(VoiceStrict.PRIVACY, VoiceStrict.PRIVATE_ON_SCREEN, loose, null))
        // Back on screen: the memory setting is open again.
        val onScreen = view("trained_three_rounds")
        assertTrue(StrictVoice.settingOpen(VoiceStrict.MEMORY, onScreen))
        assertNull(StrictVoice.blocker(VoiceStrict.MEMORY, VoiceStrict.MEMORY_ON_SCREEN, onScreen, null))
    }

    @Test
    fun `cancelled and extra recordings are named as what they were`() {
        assertEquals(
            "The last training was cancelled. Nothing changed.",
            VoiceTraining.lastLine(trainingLast("cancelled"), view("cancelled").last),
        )
        val more = VoiceTraining.lastLine(trainingLast("trained_more"), view("trained_more").last)!!
        assertTrue(more, more.startsWith("Your extra recordings were approved and added: the voice print now has 38 samples."))
    }

    // ------------------------------------------------------ the model line --

    @Test
    fun `very strict on the small model says plainly it will turn the owner away far more often`() {
        val line = StrictVoice.modelLine(view("small_model_only"))!!
        assertTrue(line, line.contains("very strict will turn you away far more often"))
        assertTrue(line, line.contains("stronger one"))
        val none = StrictVoice.modelLine(view("no_model"))!!
        assertTrue(none, none.contains("far more often"))
        assertTrue(none, none.contains("No voice-ID model is installed"))
        assertNull(StrictVoice.modelLine(view("trained_three_rounds")))
    }

    // ------------------------------------------------ the guided repeat test --

    @Test
    fun `the guided test reads the desktop's twenty sentences, word for word`() {
        // One list for both apps (fit audit, 2026-09-24). Read from the
        // desktop's own file, found by walking up from the test's working
        // folder (Gradle runs unit tests in jarvis-client/app), like
        // WikiContractTest - so there is one copy, not two that drift.
        var dir: java.io.File? = java.io.File(System.getProperty("user.dir") ?: ".").absoluteFile
        var found: java.io.File? = null
        while (dir != null && found == null) {
            val f = java.io.File(dir, "jarvis-desktop/src/voice-training.js")
            if (f.isFile) found = f
            dir = dir.parentFile
        }
        val js = requireNotNull(found) {
            "jarvis-desktop/src/voice-training.js not found above ${System.getProperty("user.dir")}"
        }.readText()
        val list = requireNotNull(
            Regex("""TEST_SENTENCES\s*=\s*Object\.freeze\(\[(.*?)\]\)""", RegexOption.DOT_MATCHES_ALL).find(js),
        ) { "TEST_SENTENCES not found in voice-training.js" }.groupValues[1]
        val desktop = Regex(""""((?:[^"\\]|\\.)*)"""").findAll(list).map { it.groupValues[1] }.toList()
        assertEquals(20, desktop.size)
        assertEquals(desktop, StrictVoice.MEASURE_SENTENCES)
    }

    @Test
    fun `twenty test sentences, none of them a training sentence, each long enough`() {
        val s = StrictVoice.MEASURE_SENTENCES
        assertEquals(20, s.size)
        assertEquals(20, s.toSet().size)
        assertTrue(s.none { it in VoiceTraining.SENTENCES })
        for (line in s) {
            // Two to four seconds read aloud: 7 to 11 words.
            val words = line.split(" ").size
            assertTrue("$words words: $line", words in 7..11)
        }
    }

    @Test
    fun `the test's answer is read and said in plain words`() {
        val a = answer("measure")
        assertEquals(200, a.code)
        val m = a.measured!!
        assertEquals(20, m.clips)
        assertEquals(14, m.veryStrict.passed)
        assertEquals(3, m.veryStrict.tooShort)
        assertEquals(17, m.balanced.passed)
        assertTrue(m.strongModel)
        val lines = StrictVoice.measureLines(m)
        assertEquals("Very strict let 14 of your 20 sentences through; balanced let 17 of 20 through.", lines[0])
        assertEquals("So at very strict you would have to say it again about 3 in 10; at balanced, about 2 in 10.", lines[1])
        assertTrue(lines[2], lines[2].startsWith("3 sentences were too short for very strict"))
        // The same counts come back in the status, for the next visit.
        assertEquals(m, view("measured").measureLast)
    }

    @Test
    fun `the test is sent in parts the PC will take, and the parts add up`() {
        // 20 clips of 5 s: 100 s, more than the 80 s one request may carry.
        val parts = StrictVoice.batches(List(20) { 5f })
        assertEquals(listOf(0..15, 16..19), parts)
        assertTrue(parts.all { r -> r.sumOf { 5.0 } <= 80.0 })
        assertEquals(listOf(0..19), StrictVoice.batches(List(20) { 3f }))
        assertEquals(listOf(0..1, 2..2), StrictVoice.batches(listOf(1f, 2f, 3f), maxClips = 2))
        val one = answer("measure").measured!!
        val both = StrictVoice.combine(listOf(one, one))!!
        assertEquals(28, both.veryStrict.passed)
        assertEquals(40, both.veryStrict.of)
        assertNull(StrictVoice.combine(listOf(one, null)))
        val refused = answer("measure_too_many")
        assertEquals(400, refused.code)
        assertNull(refused.measured)
    }

    @Test
    fun `how often, in words`() {
        assertEquals("never", StrictVoice.howOften(0.0))
        assertEquals("about 3 in 10", StrictVoice.howOften(0.3))
        assertEquals("about 1 in 20", StrictVoice.howOften(0.05))
        assertEquals("almost every time", StrictVoice.howOften(1.0))
    }

    @Test
    fun `the real-use repeat numbers`() {
        // A real status after nothing was said: no line, the PC keeps these in memory only.
        assertTrue(StrictVoice.repeatLines(view("trained_three_rounds")).isEmpty())
        val v = view("trained_three_rounds").copy(
            veryStrict = VoiceStrict.Counts(accepted = 16, refused = 3, tooShort = 1, refusedThenAccepted = 2),
        )
        assertEquals(
            listOf("At very strict: 16 commands let through; you had to say it again about 1 in 8 " +
                "(2 times). Turned away: 4, 1 of them too short."),
            StrictVoice.repeatLines(v),
        )
    }

    /**
     * A real status as a PC from before the sensitive-facts setting sends it
     * (`sensitive_memory` taken out), so these lines do not change when the
     * fixture is regenerated with the new field.
     */
    private fun noSensitive(case: String) = view(case).copy(sensitiveMemory = "")

    @Test
    fun `now line`() {
        val remembers = "; answers using what Jarvis remembers are read aloud."
        assertEquals("Voice check: Very strict; private answers stay on screen$remembers",
            StrictVoice.nowLine(noSensitive("trained_three_rounds")))
        assertEquals("Voice check: Balanced; private answers stay on screen$remembers",
            StrictVoice.nowLine(noSensitive("balanced")))
        assertEquals("Voice check: Very strict; private answers may be read aloud.",
            StrictVoice.nowLine(noSensitive("voice_is_enough")))
        assertEquals("Voice check: Very strict; private answers stay on screen; answers using what " +
            "Jarvis remembers stay on screen.",
            StrictVoice.nowLine(noSensitive("trained_three_rounds").copy(memory = VoiceStrict.MEMORY_ON_SCREEN)))
        // An older PC (no memory setting): the line says nothing about it.
        assertEquals("Voice check: Very strict; private answers stay on screen.",
            StrictVoice.nowLine(noSensitive("trained_three_rounds").copy(memory = "")))
    }

    @Test
    fun `the memory setting - aloud by default, keeping on screen is immediate, back to aloud asks`() {
        val v = view("trained_three_rounds")
        assertEquals(VoiceStrict.MEMORY_ALOUD, v.memory)
        assertTrue(StrictVoice.isCurrent(VoiceStrict.MEMORY, VoiceStrict.MEMORY_ALOUD, v))
        assertFalse(VoiceStrict.isLoosening(VoiceStrict.MEMORY, VoiceStrict.MEMORY_ON_SCREEN))
        assertTrue(VoiceStrict.isLoosening(VoiceStrict.MEMORY, VoiceStrict.MEMORY_ALOUD))
        // Keeping on screen goes even on a stale link; back to aloud is held.
        assertNull(StrictVoice.blocker(VoiceStrict.MEMORY, VoiceStrict.MEMORY_ON_SCREEN, v, "stale"))
        val onScreen = v.copy(memory = VoiceStrict.MEMORY_ON_SCREEN)
        assertEquals("stale", StrictVoice.blocker(VoiceStrict.MEMORY, VoiceStrict.MEMORY_ALOUD, onScreen, "stale"))
        assertNull(StrictVoice.blocker(VoiceStrict.MEMORY, VoiceStrict.MEMORY_ALOUD, onScreen, null))
        // An older PC does not offer it.
        assertEquals(StrictVoice.NOT_ON_THIS_PC,
            StrictVoice.blocker(VoiceStrict.MEMORY, VoiceStrict.MEMORY_ON_SCREEN, v.copy(memory = ""), null))
        assertEquals("{\"mode\":\"memory\",\"value\":\"memory_on_screen\"}",
            VoiceStrict.settingBody(VoiceStrict.MEMORY, VoiceStrict.MEMORY_ON_SCREEN))
        assertEquals("Keep on screen", StrictVoice.label(VoiceStrict.MEMORY, VoiceStrict.MEMORY_ON_SCREEN))
        assertNotNull(StrictVoice.label(VoiceStrict.STRICTNESS, VoiceStrict.VERY_STRICT))
    }

    // ------------------- sensitive saved facts (the owner's decision 13) --
    //
    // The phone voice fixture (tools/gen_phone_voice_cases.py) does not carry
    // `sensitive_memory` yet - the backend regenerates it. So these build the
    // field INTO a real status where they need it, the way an older PC's
    // status is made above by taking fields out.

    /** A real status with `gate.sensitive_memory` (and `gate.settings.sensitive_memory`) set. */
    private fun withSensitive(case: String, value: String, inSettings: Boolean = true): JsonObject {
        val s = status(case) - "gate"
        val gate = status(case)["gate"]!!.jsonObject
        val settings = gate["settings"]?.jsonObject.orEmpty() - "sensitive_memory"
        val newGate = gate - "sensitive_memory" - "settings" +
            ("sensitive_memory" to JsonPrimitive(value)) +
            ("settings" to JsonObject(if (inSettings) settings + ("sensitive_memory" to JsonPrimitive(value)) else settings))
        return JsonObject(s + ("gate" to JsonObject(newGate)))
    }

    /** A real status with no `sensitive_memory` anywhere - an older PC. */
    private fun withoutSensitive(case: String): JsonObject {
        val gate = status(case)["gate"]!!.jsonObject
        val settings = gate["settings"]?.jsonObject.orEmpty() - "sensitive_memory"
        return JsonObject(
            status(case) + ("gate" to JsonObject(gate - "sensitive_memory" + ("settings" to JsonObject(settings)))),
        )
    }

    @Test
    fun `the sensitive setting is read from the gate, and only when the PC reports it`() {
        val v = VoiceStrict.parse(withSensitive("trained_three_rounds", VoiceStrict.SENSITIVE_ON_SCREEN))
        assertEquals(VoiceStrict.SENSITIVE_ON_SCREEN, v.sensitiveMemory)
        assertEquals(
            VoiceStrict.SENSITIVE_ALOUD,
            VoiceStrict.parse(withSensitive("trained_three_rounds", VoiceStrict.SENSITIVE_ALOUD)).sensitiveMemory,
        )
        // An older PC: "" - the screen does not offer it.
        assertEquals("", VoiceStrict.parse(withoutSensitive("trained_three_rounds")).sensitiveMemory)
        assertEquals("", VoiceStrict.parse(withSensitive("trained_three_rounds", "")).sensitiveMemory)
        // A damaged value is the strict one, never "aloud".
        assertEquals(
            VoiceStrict.SENSITIVE_ON_SCREEN,
            VoiceStrict.parse(withSensitive("trained_three_rounds", "SENSITIVE_ALOUD!")).sensitiveMemory,
        )
        // The talk-button half still decodes with the field in it.
        assertTrue(VoiceStrict.read(withSensitive("trained_three_rounds", VoiceStrict.SENSITIVE_ALOUD)) is ApiResult.Ok)
    }

    @Test
    fun `the sensitive setting - on screen by default, on screen is immediate, reading aloud asks`() {
        val v = VoiceStrict.parse(withSensitive("trained_three_rounds", VoiceStrict.SENSITIVE_ON_SCREEN))
        assertTrue(StrictVoice.isCurrent(VoiceStrict.SENSITIVE_MEMORY, VoiceStrict.SENSITIVE_ON_SCREEN, v))
        assertFalse(StrictVoice.isCurrent(VoiceStrict.SENSITIVE_MEMORY, VoiceStrict.SENSITIVE_ALOUD, v))
        assertTrue(VoiceStrict.isLoosening(VoiceStrict.SENSITIVE_MEMORY, VoiceStrict.SENSITIVE_ALOUD))
        assertFalse(VoiceStrict.isLoosening(VoiceStrict.SENSITIVE_MEMORY, VoiceStrict.SENSITIVE_ON_SCREEN))
        // Read aloud is held on a stale link; keeping on screen never is.
        assertEquals("stale", StrictVoice.blocker(VoiceStrict.SENSITIVE_MEMORY, VoiceStrict.SENSITIVE_ALOUD, v, "stale"))
        assertNull(StrictVoice.blocker(VoiceStrict.SENSITIVE_MEMORY, VoiceStrict.SENSITIVE_ALOUD, v, null))
        val aloud = v.copy(sensitiveMemory = VoiceStrict.SENSITIVE_ALOUD)
        assertNull(StrictVoice.blocker(VoiceStrict.SENSITIVE_MEMORY, VoiceStrict.SENSITIVE_ON_SCREEN, aloud, "stale"))
        // It holds even under "voice check is enough", so it is never greyed for that.
        assertTrue(StrictVoice.settingOpen(VoiceStrict.SENSITIVE_MEMORY, aloud.copy(privacy = VoiceStrict.VOICE_IS_ENOUGH)))
        assertNull(
            StrictVoice.blocker(
                VoiceStrict.SENSITIVE_MEMORY, VoiceStrict.SENSITIVE_ON_SCREEN,
                aloud.copy(privacy = VoiceStrict.VOICE_IS_ENOUGH), null,
            ),
        )
        // An older PC does not offer it.
        assertEquals(
            StrictVoice.NOT_ON_THIS_PC,
            StrictVoice.blocker(VoiceStrict.SENSITIVE_MEMORY, VoiceStrict.SENSITIVE_ON_SCREEN, v.copy(sensitiveMemory = ""), null),
        )
        // A card for it already waiting.
        val waiting = v.copy(pendingKind = "setting", pendingSetting = VoiceStrict.SENSITIVE_MEMORY,
            pendingValue = VoiceStrict.SENSITIVE_ALOUD)
        assertEquals(
            "A card for this is already waiting. " + com.jarvis.client.net.Approvals.WHERE,
            StrictVoice.blocker(VoiceStrict.SENSITIVE_MEMORY, VoiceStrict.SENSITIVE_ALOUD, waiting, null),
        )
        assertEquals(
            "Waiting for your approval to change this to \"Read aloud\". " + com.jarvis.client.net.Approvals.WHERE,
            StrictVoice.waitingLine(VoiceStrict.SENSITIVE_MEMORY, waiting),
        )
        // The body is the PC's own mode, and nothing but this setting's two values goes in it.
        assertEquals(
            "{\"mode\":\"sensitive_memory\",\"value\":\"sensitive_aloud\"}",
            VoiceStrict.settingBody(VoiceStrict.SENSITIVE_MEMORY, VoiceStrict.SENSITIVE_ALOUD),
        )
        assertEquals(
            "{\"mode\":\"sensitive_memory\",\"value\":\"sensitive_on_screen\"}",
            VoiceStrict.settingBody(VoiceStrict.SENSITIVE_MEMORY, VoiceStrict.SENSITIVE_ON_SCREEN),
        )
        assertTrue(runCatching { VoiceStrict.settingBody(VoiceStrict.SENSITIVE_MEMORY, VoiceStrict.MEMORY_ALOUD) }.isFailure)
        assertTrue(runCatching { VoiceStrict.settingBody(VoiceStrict.MEMORY, VoiceStrict.SENSITIVE_ALOUD) }.isFailure)
        assertTrue(runCatching { VoiceStrict.settingBody("sensitive", VoiceStrict.SENSITIVE_ALOUD) }.isFailure)
    }

    @Test
    fun `the sensitive plate uses the contract's words`() {
        assertEquals("Answers that use sensitive saved facts", StrictVoice.SENSITIVE_MEMORY_TITLE)
        assertEquals(
            listOf("Keep on screen (recommended)", "Read aloud"),
            StrictVoice.SENSITIVE_MEMORY.map { it.label },
        )
        assertEquals(
            listOf(VoiceStrict.SENSITIVE_ON_SCREEN, VoiceStrict.SENSITIVE_ALOUD),
            StrictVoice.SENSITIVE_MEMORY.map { it.value },
        )
        assertEquals(
            "Answers that use a saved fact about your health, money, passwords or other people are shown, " +
                "not read aloud.",
            StrictVoice.SENSITIVE_MEMORY[0].detail,
        )
        assertEquals(
            "Those answers are read aloud when your voice passes the check. Anyone near the speaker will " +
                "hear them.",
            StrictVoice.SENSITIVE_MEMORY[1].detail,
        )
        assertEquals("Keep on screen", StrictVoice.label(VoiceStrict.SENSITIVE_MEMORY, VoiceStrict.SENSITIVE_ON_SCREEN))
        assertEquals("Read aloud", StrictVoice.label(VoiceStrict.SENSITIVE_MEMORY, VoiceStrict.SENSITIVE_ALOUD))
        // The last setting card, in the same shape as the others.
        fun last(value: String, outcome: String) =
            VoiceStrict.Last(outcome = outcome, setting = VoiceStrict.SENSITIVE_MEMORY, value = value)
        assertEquals("Approved: \"Read aloud\" is on now.",
            StrictVoice.lastLine(last(VoiceStrict.SENSITIVE_ALOUD, "setting_changed")))
        assertEquals("You said no, so \"Keep on screen\" stays.",
            StrictVoice.lastLine(last(VoiceStrict.SENSITIVE_ALOUD, "denied")))
        assertEquals("You made it stricter while the card waited, so approving it changed nothing.",
            StrictVoice.lastLine(last(VoiceStrict.SENSITIVE_ALOUD, "withdrawn")))
    }

    @Test
    fun `memories kept on screen - the sensitive plate says that already covers it`() {
        val note = "\"Keep on screen\" above already keeps these answers on screen."
        assertEquals(note, StrictVoice.SENSITIVE_COVERED_BY_MEMORY)
        val v = VoiceStrict.parse(withSensitive("trained_three_rounds", VoiceStrict.SENSITIVE_ALOUD))
        assertEquals(VoiceStrict.PRIVATE_ON_SCREEN, v.privacy)
        val covered = v.copy(memory = VoiceStrict.MEMORY_ON_SCREEN)
        assertEquals(note, StrictVoice.plateNote(VoiceStrict.SENSITIVE_MEMORY, covered))
        // Still open: it takes over if the memory choice changes.
        assertTrue(StrictVoice.settingOpen(VoiceStrict.SENSITIVE_MEMORY, covered))
        assertNull(StrictVoice.blocker(VoiceStrict.SENSITIVE_MEMORY, VoiceStrict.SENSITIVE_ON_SCREEN, covered, null))
        // Only on the sensitive plate.
        assertNull(StrictVoice.plateNote(VoiceStrict.MEMORY, covered))
        assertNull(StrictVoice.plateNote(VoiceStrict.PRIVACY, covered))
        // CONTROL: memories read aloud - this choice is what holds them back.
        assertNull(StrictVoice.plateNote(VoiceStrict.SENSITIVE_MEMORY, v.copy(memory = VoiceStrict.MEMORY_ALOUD)))
        // CONTROL: "voice check is enough" makes the memory choice moot, so it covers nothing.
        assertNull(
            StrictVoice.plateNote(
                VoiceStrict.SENSITIVE_MEMORY,
                covered.copy(privacy = VoiceStrict.VOICE_IS_ENOUGH),
            ),
        )
        // The memory plate's own note is unchanged.
        assertEquals(
            StrictVoice.MEMORY_WHILE_VOICE_IS_ENOUGH,
            StrictVoice.plateNote(VoiceStrict.MEMORY, covered.copy(privacy = VoiceStrict.VOICE_IS_ENOUGH)),
        )
    }

    @Test
    fun `the now line names the sensitive setting, even under voice check is enough`() {
        val v = VoiceStrict.parse(withSensitive("trained_three_rounds", VoiceStrict.SENSITIVE_ON_SCREEN))
        assertEquals(
            "Voice check: Very strict; private answers stay on screen; answers using what Jarvis remembers " +
                "are read aloud; answers using sensitive saved facts stay on screen.",
            StrictVoice.nowLine(v),
        )
        assertEquals(
            "Voice check: Very strict; private answers may be read aloud; answers using sensitive saved " +
                "facts are read aloud.",
            StrictVoice.nowLine(VoiceStrict.parse(withSensitive("voice_is_enough", VoiceStrict.SENSITIVE_ALOUD))),
        )
    }

    @Test
    fun `the voice check screen shows the fourth plate only when the PC reports it`() {
        var dir: java.io.File? = java.io.File(System.getProperty("user.dir") ?: ".").absoluteFile
        var screen: java.io.File? = null
        while (dir != null && screen == null) {
            screen = java.io.File(dir, "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/VoiceCheckScreen.kt")
                .takeIf { it.isFile }
            dir = dir.parentFile
        }
        val src = requireNotNull(screen).readText()
        val at = src.indexOf("if (strict.sensitiveMemory.isNotBlank()) {")
        assertTrue(at >= 0)
        val block = src.substring(at, at + 500)
        assertTrue(block, block.contains("title = StrictVoice.SENSITIVE_MEMORY_TITLE"))
        assertTrue(block, block.contains("setting = VoiceStrict.SENSITIVE_MEMORY"))
        assertTrue(block, block.contains("choices = StrictVoice.SENSITIVE_MEMORY"))
    }

    // ------------------------------------------ hands-free ("Hey Jarvis") --
    //
    // The owner's decision, 2026-09-24: a question started with "Hey Jarvis"
    // is as trusted as the talk button by default, with a fifth setting to
    // make it stricter. The fixture carries it (the backend's own statuses).

    /** A real status with `hands_free` set to [value] in the gate and its settings, or taken out (null). */
    private fun withHandsFree(case: String, value: String?): JsonObject {
        val gate = status(case)["gate"]!!.jsonObject
        val settings = gate["settings"]?.jsonObject.orEmpty() - "hands_free"
        val add: Map<String, JsonPrimitive> =
            if (value == null) emptyMap() else mapOf("hands_free" to JsonPrimitive(value))
        val newGate = gate - "hands_free" - "settings" + add + ("settings" to JsonObject(settings + add))
        return JsonObject(status(case) + ("gate" to JsonObject(newGate)))
    }

    @Test
    fun `hands-free is read from the PC's real status, and only when the PC reports it`() {
        assertEquals(VoiceStrict.SAME_AS_BUTTON, view("trained_three_rounds").handsFree)
        assertEquals(VoiceStrict.BUTTON_ONLY, view("hands_free_button_only").handsFree)
        assertEquals(VoiceStrict.BUTTON_ONLY, view("hands_free_back_denied").handsFree)
        assertEquals(VoiceStrict.SAME_AS_BUTTON, view("hands_free_back_approved").handsFree)
        // An older PC: "" - the screen does not offer it.
        assertEquals("", VoiceStrict.parse(withHandsFree("trained_three_rounds", null)).handsFree)
        // A damaged value is the strict one, never "same as the button".
        assertEquals(
            VoiceStrict.BUTTON_ONLY,
            VoiceStrict.parse(withHandsFree("trained_three_rounds", "everyone")).handsFree,
        )
        // The talk-button half still decodes with the field in it.
        assertTrue(VoiceStrict.read(status("hands_free_button_only")) is ApiResult.Ok)
    }

    @Test
    fun `hands-free - only the button is at once, going back asks and is held on a stale link`() {
        val same = view("trained_three_rounds")
        val strictOnly = view("hands_free_button_only")
        assertTrue(StrictVoice.isCurrent(VoiceStrict.HANDS_FREE, VoiceStrict.SAME_AS_BUTTON, same))
        assertTrue(StrictVoice.isCurrent(VoiceStrict.HANDS_FREE, VoiceStrict.BUTTON_ONLY, strictOnly))
        assertTrue(VoiceStrict.isLoosening(VoiceStrict.HANDS_FREE, VoiceStrict.SAME_AS_BUTTON))
        assertFalse(VoiceStrict.isLoosening(VoiceStrict.HANDS_FREE, VoiceStrict.BUTTON_ONLY))
        // Only the talk button: never held, even on a stale link.
        assertNull(StrictVoice.blocker(VoiceStrict.HANDS_FREE, VoiceStrict.BUTTON_ONLY, same, "stale"))
        // Back to the default: held on a stale link, sent on a live one.
        assertEquals("stale", StrictVoice.blocker(VoiceStrict.HANDS_FREE, VoiceStrict.SAME_AS_BUTTON, strictOnly, "stale"))
        assertNull(StrictVoice.blocker(VoiceStrict.HANDS_FREE, VoiceStrict.SAME_AS_BUTTON, strictOnly, null))
        // An older PC does not offer it.
        assertEquals(
            StrictVoice.NOT_ON_THIS_PC,
            StrictVoice.blocker(VoiceStrict.HANDS_FREE, VoiceStrict.BUTTON_ONLY, same.copy(handsFree = ""), null),
        )
        // A card for it already waiting.
        val waiting = strictOnly.copy(pendingKind = "setting", pendingSetting = VoiceStrict.HANDS_FREE,
            pendingValue = VoiceStrict.SAME_AS_BUTTON)
        assertEquals(
            "A card for this is already waiting. " + com.jarvis.client.net.Approvals.WHERE,
            StrictVoice.blocker(VoiceStrict.HANDS_FREE, VoiceStrict.SAME_AS_BUTTON, waiting, null),
        )
        assertEquals(
            "Waiting for your approval to change this to \"Same as the talk button\". " +
                com.jarvis.client.net.Approvals.WHERE,
            StrictVoice.waitingLine(VoiceStrict.HANDS_FREE, waiting),
        )
        // The body is the PC's own mode, with only this setting's two values.
        assertEquals(
            "{\"mode\":\"hands_free\",\"value\":\"button_only\"}",
            VoiceStrict.settingBody(VoiceStrict.HANDS_FREE, VoiceStrict.BUTTON_ONLY),
        )
        assertEquals(
            "{\"mode\":\"hands_free\",\"value\":\"same_as_button\"}",
            VoiceStrict.settingBody(VoiceStrict.HANDS_FREE, VoiceStrict.SAME_AS_BUTTON),
        )
        assertTrue(runCatching { VoiceStrict.settingBody(VoiceStrict.HANDS_FREE, VoiceStrict.MEMORY_ALOUD) }.isFailure)
        assertTrue(runCatching { VoiceStrict.settingBody(VoiceStrict.MEMORY, VoiceStrict.BUTTON_ONLY) }.isFailure)
        // The PC's REAL answers: at once, then the card.
        val tightened = answer("hands_free_button_only")
        assertTrue(tightened.accepted && tightened.changed && !tightened.pending)
        assertEquals("Done - that applies now.", StrictVoice.answerLine(tightened))
        val asked = answer("hands_free_back_waiting")
        assertTrue(asked.accepted && asked.pending)
        assertEquals(202, asked.code)
    }

    @Test
    fun `the hands-free plate uses the agreed words, the same as the desktop's`() {
        assertEquals("Hands-free (\"Hey Jarvis\")", StrictVoice.HANDS_FREE_TITLE)
        assertEquals(
            listOf("Same as the talk button (default)", "Only trust the talk button"),
            StrictVoice.HANDS_FREE.map { it.label },
        )
        assertEquals(
            listOf(VoiceStrict.SAME_AS_BUTTON, VoiceStrict.BUTTON_ONLY),
            StrictVoice.HANDS_FREE.map { it.value },
        )
        assertEquals(
            "A question started with \"Hey Jarvis\" is trusted like one where you press the button.",
            StrictVoice.HANDS_FREE[0].detail,
        )
        assertEquals(
            "Hey Jarvis still works, but it cannot teach Jarvis facts without a card, and memory or private " +
                "answers stay on screen. Safer if a recording of your voice could be played near the microphone.",
            StrictVoice.HANDS_FREE[1].detail,
        )
        assertEquals("Same as the talk button", StrictVoice.label(VoiceStrict.HANDS_FREE, VoiceStrict.SAME_AS_BUTTON))
        assertEquals("Only trust the talk button", StrictVoice.label(VoiceStrict.HANDS_FREE, VoiceStrict.BUTTON_ONLY))
        // The last setting card, in the same shape as the others - one from the PC's real status.
        assertEquals(
            "You said no, so \"Only trust the talk button\" stays.",
            StrictVoice.lastLine(view("hands_free_back_denied").last, view("hands_free_back_denied")),
        )
        fun last(outcome: String) =
            VoiceStrict.Last(outcome = outcome, setting = VoiceStrict.HANDS_FREE, value = VoiceStrict.SAME_AS_BUTTON)
        assertEquals("Approved: \"Same as the talk button\" is on now.", StrictVoice.lastLine(last("setting_changed")))
        assertEquals("You said no, so \"Only trust the talk button\" stays.", StrictVoice.lastLine(last("denied")))
        assertEquals("Nobody answered the card in time, so nothing changed.", StrictVoice.lastLine(last("timed_out")))
        assertEquals("You made it stricter while the card waited, so approving it changed nothing.",
            StrictVoice.lastLine(last("withdrawn")))
        // One wording for both apps: the desktop's voice-training.js has the same title, labels and words.
        var dir: java.io.File? = java.io.File(System.getProperty("user.dir") ?: ".").absoluteFile
        var found: java.io.File? = null
        var html: java.io.File? = null
        while (dir != null && found == null) {
            java.io.File(dir, "jarvis-desktop/src/voice-training.js").takeIf { it.isFile }?.let { found = it }
            java.io.File(dir, "jarvis-desktop/src/settings.html").takeIf { it.isFile }?.let { html = it }
            dir = dir.parentFile
        }
        val js = requireNotNull(found).readText().replace("\\\"", "\"")
        val block = requireNotNull(
            Regex("""HANDS_FREE\s*=\s*Object\.freeze\(\[(.*?)\]\);""", RegexOption.DOT_MATCHES_ALL).find(js),
        ) { "HANDS_FREE not found in voice-training.js" }.groupValues[1]
        for (c in StrictVoice.HANDS_FREE) {
            assertTrue(c.detail, block.contains(c.detail))
            assertTrue(c.label, block.contains("label: \"${c.label.removeSuffix(" (default)")}\""))
        }
        assertTrue(requireNotNull(html).readText().contains(">Hands-free (\"Hey Jarvis\")<"))
    }

    @Test
    fun `the voice check screen shows the hands-free plate only when the PC reports it`() {
        var dir: java.io.File? = java.io.File(System.getProperty("user.dir") ?: ".").absoluteFile
        var screen: java.io.File? = null
        while (dir != null && screen == null) {
            screen = java.io.File(dir, "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/VoiceCheckScreen.kt")
                .takeIf { it.isFile }
            dir = dir.parentFile
        }
        val src = requireNotNull(screen).readText()
        val at = src.indexOf("if (strict.handsFree.isNotBlank()) {")
        assertTrue(at >= 0)
        val block = src.substring(at, at + 500)
        assertTrue(block, block.contains("title = StrictVoice.HANDS_FREE_TITLE"))
        assertTrue(block, block.contains("setting = VoiceStrict.HANDS_FREE"))
        assertTrue(block, block.contains("choices = StrictVoice.HANDS_FREE"))
    }
}
