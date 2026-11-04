package com.jarvis.client

import com.jarvis.client.data.PipLayout
import com.jarvis.client.data.PipWords
import com.jarvis.client.service.WakeListen
import com.jarvis.client.voice.VoiceSession
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "Hey Jarvis" said at the picture-in-picture window (the owner's ask,
 * 2026-11-01 ~21:47 PT): *"whenever jarvis is in picture-in-picture mode ...
 * I would like to be able to say hey jarvis to be able to say something to
 * jarvis and have jarvis process what I said. if it's not in live mode don't
 * have a turn on live mode but comprehend it as a single input."*
 *
 * WHAT WAS ESTABLISHED BEFORE CHANGING ANYTHING (read from the source, this
 * worktree, 2026-11-02; line numbers are from `9a971f3e6`):
 *
 *  - the listener keeps running while the window is up. Its two pause
 *    conditions are the talk button owning the microphone and Jarvis Live
 *    running on this phone (`service/WakeWordService.kt`, the
 *    `voice.phase.value == CAPTURING || JarvisRuntime.liveOnHere()` line and the
 *    `while (running && voice.phase.value == OFF && !liveOnHere())` loop). A
 *    picture-in-picture window is neither, and the service never mentions PiP.
 *  - one heard "hey Jarvis" is one clip, posted to
 *    `/api/voice/utterance?source=wake_word` (`VoiceSession.deliverWakeClip`,
 *    then `deliver`'s single `api.utterance(...)` call) - the SAME route and
 *    path as outside the window. Nothing there starts Live, and nothing starts
 *    an activity.
 *  - the answer is spoken by the existing sentence-streaming path
 *    (`VoiceSession.answer` -> `speakStreamed`), which is runtime state, not an
 *    activity state, so a paused (PiP) activity does not stop it.
 *  - the one thing the window did NOT do was show that it had heard him: mode 1
 *    drew the face alone (the owner's 2026-10-31 revision, "just keep the model
 *    there without the wording"), and a wake turn has no CAPTURING stretch to
 *    change the face. That is what this change adds: the one word
 *    [PipWords.working] answers, drawn only while a turn runs.
 *
 * WHAT THIS FILE IS: the pins. The words as VALUES (every phase and every
 * listener state), the layout rule, and source pins for the three promises that
 * cannot regress silently - a wake clip never starts Live, the window never
 * leaves PiP by itself, and the listener never steps aside for a window.
 *
 * NOT CLAIMED HERE: that any of it happens on a real phone. The PiP mechanics
 * were driven (field test 2026-10-31, pass 10), but a wake-word turn inside the
 * window was not, so that stays a phone step in `docs/PIP-DESIGN.md` §7 - never
 * a pass from a JVM test.
 */
class PipWakeWordTest {

    // ------------------------------------------------------------------
    //   1. The one word a running turn may show
    // ------------------------------------------------------------------

    /** Every listener state, so a future value cannot be quietly unhandled. */
    private val listeners: List<WakeListen> = listOf(
        WakeListen.Off,
        WakeListen.Starting,
        WakeListen.Listening,
        WakeListen.Heard,
        WakeListen.Paused,
        WakeListen.Failed("the microphone stopped"),
    )

    @Test
    fun `a running turn shows Listening, Thinking or Speaking - and nothing else`() {
        val allowed = setOf(PipWords.LISTENING, PipWords.THINKING, PipWords.SPEAKING)
        // An exhaustive sweep, not four examples: every phase against every
        // listener state, and every non-null answer must be one of the three
        // fixed words. There is no input here that could carry a transcript,
        // an answer or a card's words - the signature has no string in it.
        for (phase in VoiceSession.Phase.entries) {
            for (wake in listeners) {
                val word = PipWords.working(phase, wake)
                if (word != null) {
                    assertTrue("phase=$phase wake=$wake produced \"$word\"", word in allowed)
                }
            }
        }
    }

    @Test
    fun `the wake turn says Listening while it records, then Thinking, then Speaking`() {
        // The sequence the owner actually sees in the window. A wake turn never
        // has CAPTURING (the service records before the desktop is asked), so
        // the first word comes from WakeListen.Heard instead.
        assertEquals(PipWords.LISTENING,
            PipWords.working(VoiceSession.Phase.OFF, WakeListen.Heard))
        assertEquals(PipWords.THINKING,
            PipWords.working(VoiceSession.Phase.VERIFYING, WakeListen.Heard))
        assertEquals(PipWords.THINKING,
            PipWords.working(VoiceSession.Phase.THINKING, WakeListen.Heard))
        assertEquals(PipWords.SPEAKING,
            PipWords.working(VoiceSession.Phase.SPEAKING, WakeListen.Heard))
        // The turn is over: nothing is drawn, and the window is the face alone.
        assertNull(PipWords.working(VoiceSession.Phase.OFF, WakeListen.Listening))
        // The talk button keeps its own CAPTURING stretch, and says the same word.
        assertEquals(PipWords.LISTENING,
            PipWords.working(VoiceSession.Phase.CAPTURING, WakeListen.Off))
    }

    @Test
    fun `merely listening for the phrase puts no word in the window`() {
        // The owner's 2026-10-31 revision still holds for the RESTING window:
        // "just keep the model there without the wording". Only a turn that is
        // actually running may add a word - never the always-on listener.
        for (wake in listOf(
            WakeListen.Off,
            WakeListen.Starting,
            WakeListen.Listening,
            WakeListen.Paused,
            WakeListen.Failed("the microphone stopped"),
        )) {
            assertNull("wake=$wake must draw no word while nothing is happening",
                PipWords.working(VoiceSession.Phase.OFF, wake))
        }
    }

    // ------------------------------------------------------------------
    //   2. Which layouts may draw it
    // ------------------------------------------------------------------

    @Test
    fun `only the two layouts that say nothing of their own draw the turn word`() {
        assertTrue("mode 1 has room for the word", PipLayout.FACE.turnWordShown)
        assertTrue("mode 2 has room for the word", PipLayout.THREAD.turnWordShown)
        // Privacy first: the hidden window says its one locked sentence and
        // nothing else, whatever is happening (§4, §9.1).
        assertFalse("the hidden window must never draw the turn word",
            PipLayout.HIDDEN.turnWordShown)
        // Live has its own status line; a second one would say two things.
        assertFalse(PipLayout.LIVE.turnWordShown)
        assertFalse(PipLayout.LIVE_OFF.turnWordShown)
        assertFalse("no window exists", PipLayout.OFF.turnWordShown)
        // ...and the word is not the answer: no layout gained answer text.
        for (layout in PipLayout.entries) {
            assertFalse("$layout must still draw no answer", layout.answerShown)
        }
    }

    @Test
    fun `the window draws the word from its argument, outside every layout branch`() {
        val window = stripComments(file(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/PipWindow.kt"))
        assertTrue("the window does not take the word as a parameter",
            window.contains("word: String?"))
        assertTrue("the word is not gated on the layout's own rule",
            window.contains("if (word != null && layout.turnWordShown)"))
        assertTrue("the word is not drawn as one short line",
            window.contains("PipLine(word, chrome.textHi, maxLines = 1)"))
        // Drawn AFTER the `when`: no layout branch owns it, so a later edit
        // cannot add a second copy to one mode and leave another stale.
        val whenEnds = window.indexOf("PipLayout.LIVE -> PipLive(face)")
        val wordAt = window.indexOf("PipLine(word")
        assertTrue("the word must be drawn after the layout branches",
            whenEnds >= 0 && wordAt > whenEnds)
        // The window itself chooses no word: it cannot invent or reword one.
        assertFalse("the window must not compute the word", window.contains("PipWords.working("))
    }

    @Test
    fun `MainActivity hands the window the word from the voice phase and the listener`() {
        val main = file("jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt")
        assertTrue("the listener's state is not collected where App() can read it",
            main.contains("val wakeListenState by WakeWordService.state.collectAsState()"))
        assertTrue("PipWindow is not handed the one word",
            main.contains("word = PipWords.working(voicePhase, wakeListenState)"))
        // The same call must be inside the PiP branch, not somewhere else.
        val pipBlock = main.substringAfter("if (pipNow.value) {")
        assertTrue("the word is not handed to the window while it is up",
            pipBlock.substringBefore("return@JarvisTheme")
                .contains("word = PipWords.working(voicePhase, wakeListenState)"))
    }

    // ------------------------------------------------------------------
    //   3. One clip, one turn - and never Live
    // ------------------------------------------------------------------

    @Test
    fun `a wake clip is one wake-word utterance and starts no Live session`() {
        val voice = file(
            "jarvis-client/app/src/main/java/com/jarvis/client/voice/VoiceSession.kt")
        val clip = stripComments(body(voice, "suspend fun deliverWakeClip("))
        assertTrue("the clip is not sent as a wake-word clip",
            clip.contains("JarvisApi.SOURCE_WAKE_WORD"))
        assertEquals("one clip must be ONE utterance",
            1, Regex("deliver\\(turn, wav,").findAll(clip).count())
        // Nothing on this path may start, resume or move Live: the owner's
        // "if it's not in live mode don't have a turn on live mode".
        for (banned in listOf(
            "liveStart", "liveStartSoon", "beginLiveHere", "LiveService",
            "ACTION_START_VOICE", "startActivity", "enterPictureInPictureMode",
        )) {
            assertFalse("deliverWakeClip must not reach $banned", clip.contains(banned))
        }
        // ...and the one POST is the ordinary one, on the ordinary route.
        val deliver = stripComments(body(voice, "private suspend fun deliver("))
        assertEquals("a clip must be one POST to /api/voice/utterance",
            1, Regex("api\\.utterance\\(").findAll(deliver).count())
    }

    @Test
    fun `the wake listener starts no Live session and no activity`() {
        val service = file(
            "jarvis-client/app/src/main/java/com/jarvis/client/service/WakeWordService.kt")
        // The two functions that own the capture-and-send turn. (The file
        // elsewhere builds the Bubble notification's shortcut, which is a
        // deliberate ACTION_START_VOICE tap target - not this path.) Comments
        // are stripped: the prose there explains WHY (e.g. naming the Live
        // service it deliberately does not start), and a pin must read code.
        for (name in listOf("private suspend fun listen() {", "private suspend fun answerListening(")) {
            val body = stripComments(body(service, name))
            for (banned in listOf(
                "liveStart", "beginLiveHere", "LiveService",
                "ACTION_START_VOICE", "startActivity", "enterPictureInPictureMode",
            )) {
                assertFalse("$name must not reach $banned", body.contains(banned))
            }
        }
    }

    // ------------------------------------------------------------------
    //   4. The listener does not step aside for the window
    // ------------------------------------------------------------------

    @Test
    fun `the listener keeps listening while the window is up`() {
        val service = file(
            "jarvis-client/app/src/main/java/com/jarvis/client/service/WakeWordService.kt")
        // The pause conditions are the talk button owning the microphone, Live
        // running on this phone, and - since 2026-11-04 - the hands-free answer
        // window holding the microphone through the one ledger
        // (voice/MicOwner.kt). A PiP window must never become one of them: that
        // is the bug this test exists to prevent, and the two assertions below
        // still say so.
        assertTrue("the talk-button / Live pause condition changed",
            service.contains(
                "if (voice.phase.value == VoiceSession.Phase.CAPTURING ||"))
        assertTrue("and Live still pauses it",
            service.contains("JarvisRuntime.liveOnHere() ||"))
        assertTrue("and the hands-free window, through the one ledger",
            service.contains("MicOwner.freeFor(com.jarvis.client.voice.MicOwner.WAKE)"))
        assertFalse("the listener must not know about the PiP window",
            service.contains("PipPresence"))
        assertFalse("the listener must not pause for the PiP window",
            service.contains("isInPictureInPictureMode"))
        // Nor may the activity stop it when it leaves the foreground: PiP is a
        // paused activity, and going home to the window must not end listening.
        val main = file("jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt")
        assertTrue("MainActivity keeps the lifecycle callback this pin reads",
            main.contains("override fun onStop() {"))
        // Every lifecycle callback that exists is checked; `onPause` does not
        // exist today, and a future one is held by the same rule the moment it
        // appears (this loop finds it rather than assuming its absence).
        for (name in listOf("onCreate", "onStart", "onResume", "onPause", "onStop", "onDestroy")) {
            val at = main.indexOf("override fun $name(")
            if (at < 0) continue
            val fn = main.substring(at).substringBefore("\n    }")
            assertFalse("$name must not stop the wake listener",
                fn.contains("WakeWordService.stop"))
        }
    }

    // ------------------------------------------------------------------
    //   5. The window cannot leave picture-in-picture by itself
    // ------------------------------------------------------------------

    @Test
    fun `the PiP window never starts an activity or leaves the window`() {
        val window = stripComments(file(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/PipWindow.kt"))
        for (banned in listOf(
            "startActivity", "enterPictureInPictureMode", "ACTION_START_VOICE",
            "moveTaskToBack", "finish(",
        )) {
            assertFalse("the PiP window must not reach $banned", window.contains(banned))
        }
        // The system callback only records the state and re-arms the params.
        val main = file("jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt")
        val changed = body(main, "override fun onPictureInPictureModeChanged(")
        for (banned in listOf(
            "startActivity", "enterPictureInPictureMode", "moveTaskToBack",
            "WakeWordService.stop",
        )) {
            assertFalse("onPictureInPictureModeChanged must not reach $banned",
                changed.contains(banned))
        }
        // The ONE action the window's chrome carries is still Expand, and this
        // slice added no second way out (`PipTest` holds the count).
        assertTrue("the window still records that it is up",
            changed.contains("pipNow.value = isInPictureInPictureMode"))
    }

    // ------------------------------------------------------------------
    //   Helpers - the same two `PipTest` uses
    // ------------------------------------------------------------------

    /** A repository file, from Gradle's working folder (`jarvis-client/app`). */
    private fun file(rel: String): String {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f.readText()
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    /** One function's source, from its signature to its 4-space closing brace. */
    private fun body(src: String, signature: String): String {
        val from = src.indexOf(signature)
        assertTrue("$signature not found", from >= 0)
        val rest = src.substring(from)
        val end = rest.indexOf("\n    }")
        return if (end >= 0) rest.substring(0, end) else rest
    }

    /** Source with `//` and `/* */` comments removed, so prose cannot trip a code pin. */
    private fun stripComments(src: String): String =
        src.replace(Regex("/\\*[\\s\\S]*?\\*/"), "")
            .replace(Regex("//[^\n]*"), "")
}
