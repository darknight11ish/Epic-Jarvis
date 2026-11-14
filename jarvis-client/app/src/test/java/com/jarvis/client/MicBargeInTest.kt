package com.jarvis.client

import com.jarvis.client.ui.SettingsSearch
import com.jarvis.client.voice.MicBargeIn
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Stop speaking when I press the mic" - the owner's ask of 2026-11-13:
 *
 *   *"when I use the top mic button in the android app and jarvis is still
 *   speaking out from a previous response, I want it to interrupt its response
 *   and process the new thing I said. also add this to the settings as a
 *   changeable Default"*
 *
 * WHAT TODAY DID, measured on the code this branch changes (and the reason the
 * tests are shaped this way):
 *
 *  - while the reply was still STREAMING both mic buttons were DISABLED
 *    (`HomeScreen`, `enabled = ... && !state.streaming`), so the press did
 *    literally nothing;
 *  - after the stream ended but sentences were still playing, the press was
 *    REFUSED by `VoiceSession.begin`'s "still finishing" guard with "Still
 *    finishing the last one.";
 *  - either way no speech was stopped.
 *
 * So the OWN half is the setting's rule (default ON, OFF = today), and the
 * ANDROID half - a composable's enabled state and an Android TTS object a JVM
 * test cannot build - is pinned by reading the shipped source, the precedent
 * `MemoryAloudWiringTest`, `CallRecordSourcePinTest` and `R8SourcePinTest`
 * already set in this module.
 */
class MicBargeInTest {

    private val root = "jarvis-client/app/src/main/java/com/jarvis/client/"

    private fun text(rel: String): String = SourceFile.read(root + rel)

    /** The file's code only: its own docs explain the old behaviour in words. */
    private fun code(raw: String): String = raw.lines().joinToString("\n") { line ->
        val t = line.trimStart()
        when {
            t.startsWith("//") || t.startsWith("*") || t.startsWith("/*") -> ""
            else -> line.substringBefore(" //")
        }
    }

    private fun body(src: String, from: String, to: String): String {
        val a = src.indexOf(from)
        assertTrue("$from is gone", a >= 0)
        val b = src.indexOf(to, a)
        assertTrue("$to is gone after $from", b > a)
        return src.substring(a, b)
    }

    // ---------------------------------------------------------------- the default

    @Test
    fun `the default is on, and it is stored as this phone's own setting`() {
        // The owner asked for the barge-in AND for it to be the default.
        assertTrue("the barge-in is not the default any more", MicBargeIn.DEFAULT)
        val settings = code(text("data/ClientSettings.kt"))
        // Read with the switch's own DEFAULT as the fallback - so an install
        // that has never seen the switch gets the behaviour he asked for.
        assertTrue(
            "the stored default is not MicBargeIn.DEFAULT",
            "prefs.getBoolean(KEY_MIC_BARGE_IN, MicBargeIn.DEFAULT)" in settings,
        )
        // ...and it persists in the same preferences file as its neighbours.
        assertTrue(
            "the switch is not written to the preferences store",
            "putBoolean(KEY_MIC_BARGE_IN, value)" in settings,
        )
        assertTrue(settings, "const val KEY_MIC_BARGE_IN = \"mic_barge_in\"" in settings)
        // NOT the retired "Interrupting Jarvis" key, which is still read once to
        // carry an old choice over - reusing it would make this switch change
        // that one on an upgrade.
        assertFalse(
            "the new switch reuses the retired barge_in key",
            "KEY_MIC_BARGE_IN = \"barge_in\"" in settings,
        )
        assertTrue("the retired key is gone", "const val KEY_BARGE_IN = \"barge_in\"" in settings)
    }

    // ------------------------------------------------------- the press itself

    @Test
    fun `ON - a press during speech stops the speaker first, then starts listening`() {
        val calls = mutableListOf<String>()
        val result = MicBargeIn.press(
            on = true,
            speaking = true,
            stopSpeech = { calls += "stop" },
            dropOldTurn = { calls += "drop" },
        )
        assertEquals(MicBargeIn.Press.INTERRUPT, result)
        // Silence before the old turn is dropped - and both before the new turn
        // is started (which `begin` does after this call, below).
        assertEquals(listOf("stop", "drop"), calls)

        // THE ANDROID HALF: `VoiceSession.begin` is where the press lands, and
        // it must go on to start the ordinary turn instead of returning.
        val voice = code(text("voice/VoiceSession.kt"))
        val begin = body(voice, "fun begin(", "fun release(")
        val guard = begin.indexOf("if (previous != null && !previous.isCompleted) {")
        val bargeAt = begin.indexOf("MicBargeIn.press(")
        val launchAt = begin.indexOf("job = scope.launch {")
        assertTrue("the press is not decided inside the still-finishing guard", guard in 0 until bargeAt)
        assertTrue("the new turn is not started after the barge-in decision", launchAt > bargeAt)
        // The one silence is the STOP WORD's own function - not a second path
        // to the speaker that could drift from it.
        val barge = begin.substring(bargeAt, begin.indexOf(") == MicBargeIn.Press.REFUSED"))
        assertTrue(barge, "on = micBargeInOn()," in barge)
        assertTrue(barge, "speaking = _phase.value == Phase.SPEAKING," in barge)
        assertTrue(barge, "stopSpeech = ::stopSpeaking," in barge)
        assertTrue(barge, "dropOldTurn = { previous.cancel() }," in barge)
        // The stop is SYNCHRONOUS, on the thread that got the press: were it
        // deferred into a coroutine it could land after the new turn's
        // `Speaker.arm()`, and the stale stop flag would silently mute the NEW
        // reply (the "sticky cancel" the review of 2026-11-13 warned about).
        val firstLaunch = begin.indexOf("scope.launch")
        assertTrue("the barge-in stop is deferred into a coroutine", firstLaunch > bargeAt)
        // A barge-in must NOT return on the way to the new turn: that is the
        // race the owner would feel as an intermittent button. The ONLY return
        // between the guard and the new turn is the refused branch's own.
        val refused = body(begin, ") == MicBargeIn.Press.REFUSED", "val turn = Turn()")
        assertEquals("the refused branch returns more than once", 1, Regex("return").findAll(refused).count())
        val afterRefused = begin.substring(begin.indexOf("val turn = Turn()"), launchAt)
        assertFalse("a barge-in press still returns before the new turn", "return" in afterRefused)
        // ...and the new turn is the ordinary one, microphone and all.
        assertTrue("the barge-in does not start an ordinary capture", "recorder.record(" in begin)
        // The refused branch is what keeps today's words, and only it.
        assertTrue(refused, "\"Still finishing the last one.\"" in refused)
        // OFF cannot silence: the only `stopSpeaking` in begin is the barge-in
        // call, so a refused press cannot stop the reply.
        assertEquals(
            "a second stop path was added to begin",
            1,
            Regex("stopSpeaking").findAll(begin).count(),
        )
    }

    @Test
    fun `OFF - a press during speech stops nothing - today's behaviour, unchanged`() {
        var stopped = false
        var dropped = false
        val result = MicBargeIn.press(
            on = false,
            speaking = true,
            stopSpeech = { stopped = true },
            dropOldTurn = { dropped = true },
        )
        assertEquals(MicBargeIn.Press.REFUSED, result)
        assertFalse("the speaker was stopped with the switch OFF", stopped)
        assertFalse("the old turn was dropped with the switch OFF", dropped)
        // And the enabled rule agrees: with the switch off, an answer that is
        // streaming greys the microphone exactly as it did before this branch.
        assertFalse(MicBargeIn.interrupts(on = false, speaking = true))
    }

    @Test
    fun `a press while nothing is being said keeps today's behaviour too`() {
        // THINKING and VERIFYING make no sound: there is nothing to interrupt,
        // and the reported behaviour the owner asked to keep is the old one.
        assertFalse(MicBargeIn.interrupts(on = true, speaking = false))
        assertFalse(MicBargeIn.interrupts(on = false, speaking = false))
        assertTrue(MicBargeIn.interrupts(on = true, speaking = true))
        var stopped = false
        assertEquals(
            MicBargeIn.Press.REFUSED,
            MicBargeIn.press(on = true, speaking = false, stopSpeech = { stopped = true }, dropOldTurn = {}),
        )
        assertFalse("silence with nothing playing", stopped)
    }

    // ------------------------------------------- nothing of it is spoken again

    @Test
    fun `the rest of an interrupted reply is never spoken, and nothing resumes it`() {
        val voice = code(text("voice/VoiceSession.kt"))
        // 1. The stop latches the turn, so SpeechAhead asks for no more sound
        //    and plays no more of it (SpeechAhead's own tests drive that rule).
        val stop = body(voice, "fun stopSpeaking()", "fun interruptForWake()")
        assertTrue("the stop no longer latches the turn", "current?.silenced = true" in stop)
        assertTrue("the stop no longer silences the speaker", "speaker.stop()" in stop)
        // ...and the drain really is handed that latch.
        assertTrue("the drain is no longer stopped by the turn", "stopped = { turn.silenced }" in voice)
        // 2. The resume timer of the by-voice barge-in cannot bring it back.
        assertTrue("a pause timer can still resume the stopped reply", "pauseTimer?.cancel()" in stop)
        // 3. The speaker's own stop clears the pause, so a paused reply cannot
        //    carry on - and its flag stops the write loop.
        val speaker = code(text("audio/Speaker.kt"))
        val speakerStop = body(speaker, "fun stop() {", "fun release()")
        assertTrue(speakerStop, "cancelled = true" in speakerStop)
        assertTrue("a paused reply would carry on", "paused = false" in speakerStop)
        assertTrue(speakerStop, "runCatching { track?.pause() }" in speakerStop)
        assertTrue("the phone's own voice is not stopped", "runCatching { tts?.stop() }" in speakerStop)
        // 4. The old turn's job is cancelled with the stop, so its chat stream
        //    (a reply still arriving from the PC) is dropped on this phone.
        assertTrue(
            "the old turn is not cancelled, so its reply can still arrive and speak",
            "dropOldTurn = { previous.cancel() }" in voice,
        )
    }

    // -------------------------------------------------------- the row's words

    @Test
    fun `the switch says what it does, in plain words, in both states`() {
        assertEquals("Stop speaking when I press the mic", MicBargeIn.NAME)
        assertTrue("the default is not said on the row", "On by default" in MicBargeIn.SUBTITLE)
        val on = MicBargeIn.describe(true)
        assertTrue(on, "stops" in on.lowercase())
        assertTrue(on, "listens" in on.lowercase())
        assertTrue("ON does not say the answer stays", "screen" in on.lowercase())
        val off = MicBargeIn.describe(false)
        assertTrue("OFF does not say what happens instead", "wait" in off.lowercase())
        assertTrue("OFF claims the old press does something", "does nothing" in off.lowercase())
        assertTrue(off.isNotBlank() && off != on)
        // The buttons say their outcome; they are not the same word twice.
        assertTrue(MicBargeIn.TURN_ON.isNotBlank() && MicBargeIn.TURN_OFF.isNotBlank())
        assertTrue(MicBargeIn.TURN_ON != MicBargeIn.TURN_OFF)
        // The note says whose switch it is, and which one it is NOT: the
        // "Interrupting Jarvis" choice beside it is about the phone listening
        // by itself, not about the microphone button.
        assertTrue("the note does not separate it from Interrupting Jarvis", "Interrupting Jarvis" in MicBargeIn.NOTE)
        assertTrue("the note does not say it is this phone's", "phone" in MicBargeIn.NOTE.lowercase())
    }

    @Test
    fun `the switch is findable by the words printed on it`() {
        // The 2026-10-13 rule for every control: typing what is on it must find
        // the section that draws it, or the owner sees "Nothing here matches".
        for (query in listOf(
            MicBargeIn.NAME,
            "stop speaking",
            "stop speaking when i press the mic",
            "press the mic",
        )) {
            assertTrue(
                "\"$query\" finds nowhere in Settings",
                SettingsSearch.matching(query).contains("voice"),
            )
        }
    }

    // ------------------------------------------------------------- the wiring

    @Test
    fun `the row is drawn in Voice settings and the screen really passes the switch`() {
        val plate = text("ui/screens/VoiceSwitchesPlate.kt")
        for (line in listOf(
            "MicBargeIn.NAME",
            "MicBargeIn.SUBTITLE",
            "MicBargeIn.describe(micBargeIn)",
            "MicBargeIn.TURN_ON",
            "MicBargeIn.TURN_OFF",
            "MicBargeIn.NOTE",
        )) {
            assertTrue("the row no longer draws $line", line in plate)
        }
        // Only where the screen owns the setting (the same shape as its
        // neighbours), and it is on the Voice card.
        assertTrue(plate, "micBargeIn != null && onMicBargeIn != null" in plate)

        val activity = code(text("MainActivity.kt"))
        assertTrue(activity, "JarvisRuntime.settings.micBargeIn.collectAsState()" in activity)
        assertTrue(activity, "micBargeIn = micBargeInOn," in activity)
        assertTrue(activity, "onMicBargeIn = { on -> JarvisRuntime.settings.setMicBargeIn(on) }" in activity)
        // The live value the press reads, read at the press.
        val runtime = code(text("JarvisRuntime.kt"))
        assertTrue(runtime, "micBargeInOn = { clientSettings.micBargeIn.value }" in runtime)
        val voice = code(text("voice/VoiceSession.kt"))
        assertTrue(voice, "micBargeInOn: () -> Boolean = { MicBargeIn.DEFAULT }" in voice)
    }

    @Test
    fun `the microphone stays usable while the answer streams, for exactly that press`() {
        val home = text("ui/screens/HomeScreen.kt")
        val codeOnly = code(home)
        // One rule, used twice: the chat bar's microphone and the full-screen
        // face bar's. Both used to go grey for the whole stream, which is what
        // made the owner's press do nothing.
        assertEquals(
            "the two mic buttons no longer share the barge-in rule",
            2,
            Regex("""\(!state\.streaming \|\| state\.micPressStopsSpeech\(\)\)""").findAll(codeOnly).count(),
        )
        // And the rule itself is the one the press uses.
        val state = body(codeOnly, "internal fun HomeState.micPressStopsSpeech()", "private fun HomeNotice(")
        assertTrue(state, "MicBargeIn.interrupts(" in state)
        assertTrue(state, "voicePhase == VoiceSession.Phase.SPEAKING" in state)
        // The "Jarvis is answering" line is dropped for exactly that press -
        // on both surfaces - because the reason it gives no longer holds.
        assertEquals(
            "a surface still says why the microphone is greyed for a dead reason",
            2,
            Regex("""bargeIn = state\.micPressStopsSpeech\(\),""").findAll(codeOnly).count(),
        )
        // A press with the switch OFF still waits: `MicWords` keeps the old
        // sentence for it.
        val words = code(text("MicWords.kt"))
        assertTrue("the ANSWERING line no longer has its condition", "streaming && !bargeIn -> ANSWERING" in words)
    }

    @Test
    fun `it neither owns the microphone nor transcribes anything on this phone`() {
        // The microphone-owner ledger is not bypassed: the barge-in is a press
        // through `begin`, which opens the ordinary Recorder (`MicOwner.TALK`).
        val bargeIn = code(text("voice/MicBargeIn.kt"))
        for (never in listOf("MicOwner", "MicNow", "Recorder", "recorder", "SpeechRecognizer", "transcri")) {
            assertFalse("the barge-in touches $never", never in bargeIn)
        }
        val voice = code(text("voice/VoiceSession.kt"))
        assertTrue("the ordinary capture path is gone", "recorder.record(" in voice)
        // The clip is sent to the PC's own voice route like any other press:
        // nothing in this rule reaches the network or a model.
        for (never in listOf("api.", "utterance", "chat(")) {
            assertFalse("the barge-in rule does $never", never in bargeIn)
        }
    }

    @Test
    fun `a refused press says the same sentence it always did`() {
        // Pinned as a literal so a reword is a deliberate change: it is the one
        // line the owner sees when the switch is OFF and he presses too soon.
        val voice = text("voice/VoiceSession.kt")
        assertTrue("\"Still finishing the last one.\"" in voice)
        assertNotNull(MicBargeIn.describe(false))
        assertNull(com.jarvis.client.MicWords.heldLine(
            link = LinkState.CONNECTED,
            streaming = true,
            micAllowed = true,
            voiceOffered = true,
            bargeIn = true,
        ))
    }
}
