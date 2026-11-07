package com.jarvis.client

import com.jarvis.client.voice.MemoryAloud
import com.jarvis.client.voice.PrivateAloud
import com.jarvis.client.voice.ReadAloud
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The wiring half of "Read aloud" for typed answers (the owner's ask,
 * 2026-10-27). The decision and sentence splitting are proved for real in
 * [ReadAloudTest]; there is no emulator here, so the Compose/runtime wiring is
 * held the [ModelDoorTest] way - by reading the shipped source for the exact
 * lines. The on-phone look and the real `/api/voice/say` round trip remain a
 * field-test row, not a pass.
 */
class ReadAloudWiringTest {

    private val main = "jarvis-client/app/src/main/java/com/jarvis/client/"

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private fun source(rel: String): String = repoFile(main + rel).readText()

    private val runtime: String by lazy { source("JarvisRuntime.kt") }

    /**
     * The text of one function, from its signature to the brace that closes it.
     * The pins below are about WHERE a line sits inside a function - before an
     * early return, before the question is sent - and a plain `contains` cannot
     * see that.
     */
    private fun body(text: String, signature: String): String {
        val start = text.indexOf(signature)
        assertTrue("$signature is gone; re-anchor this test", start >= 0)
        var depth = 0
        var opened = false
        val out = StringBuilder()
        for (ch in text.substring(start)) {
            out.append(ch)
            if (ch == '{') {
                depth++
                opened = true
            } else if (ch == '}') {
                depth--
                if (opened && depth == 0) return out.toString()
            }
        }
        error("$signature has no closing brace")
    }

    @Test
    fun `one typed answer is remembered with its facts, and a new question clears it`() {
        assertTrue(
            "no typed-send wrapper records the answer",
            runtime.contains("suspend fun sendTypedChat("),
        )
        assertTrue("the wrapper does not clear the offer first", runtime.contains("_readAloud.value = null"))
        assertTrue("the wrapper does not pass onRoute", runtime.contains("onRoute = { route -> header = route }"))
        assertTrue("the offer state is not exposed", runtime.contains("val readAloud: StateFlow<com.jarvis.client.voice.ReadAloud.Offer?>"))
        assertTrue("the reading state is not exposed", runtime.contains("val readingAloud: StateFlow<Boolean>"))
        // The facts come from the SAME watch the voice path uses - but the route
        // is read the FAIL-CLOSED way: a missing header is unknown, and unknown
        // must never be spoken (2026-10-27 ruling; see
        // [ReadAloudRouteFailClosedTest]).
        assertTrue(
            "the route is not read fail-closed",
            runtime.contains("PrivateAloud.routeOrNull(header)"),
        )
        assertTrue("tool runs are not measured", runtime.contains("PrivateAloud.toolRan(start, now)"))
        assertTrue("unknown tool state is not measured", runtime.contains("PrivateAloud.toolsKnown(start, now)"))
        assertTrue("screen reads are not measured", runtime.contains("PrivateAloud.screenRead(start, now)"))
        assertTrue("the locked phone is not checked", runtime.contains("appLockWouldLock("))
    }

    @Test
    fun `the clip is the PC's voice, one sentence at a time, capped`() {
        assertTrue("read-aloud does not use the PC's say route", runtime.contains("api.say(sentence)"))
        assertTrue("the cap is not applied", runtime.contains("ReadAloud.sentences(offer.text)"))
        assertTrue("the speaker is not armed before playing", runtime.contains("voice.speaker.arm()"))
        assertTrue("the clip is not played through the one speaker", runtime.contains("voice.speaker.play(clip.wav)"))
        assertTrue("the voice path's busy guard is not used", runtime.contains("voice.speakerBusy()"))
        assertTrue("there is no stop path", runtime.contains("fun stopReadingAloud()"))
        assertTrue("stop does not stop the speaker", runtime.contains("voice.speaker.stop()"))
        // No new route: the say route already exists in JarvisApi only.
        assertFalse("the runtime invented a new route literal", runtime.contains("/api/voice/say"))
    }

    @Test
    fun `the control sits beside Copy and Share on the answer on screen`() {
        val home = source("ui/screens/HomeScreen.kt")
        val copyAt = home.indexOf("Quiet(\"Copy\"")
        val readAt = home.indexOf("com.jarvis.client.voice.ReadAloud.LABEL")
        assertTrue("the Copy/Share row is gone", copyAt > 0)
        assertTrue("Home has no Read aloud control", readAt > copyAt)
        assertTrue("the control does not say Stop while reading", home.contains("com.jarvis.client.voice.ReadAloud.STOP"))
        assertTrue("the control does not call the runtime", home.contains("JarvisRuntime.readAloudLastAnswer()"))
        assertTrue("the control cannot be stopped", home.contains("JarvisRuntime.stopReadingAloud()"))
        assertTrue("a refusal is not shown to the owner", home.contains("JarvisRuntime.setNotice(said)"))
        assertTrue("the control is drawn without its facts", home.contains("readAloudOffer?.takeIf"))
        assertEquals(
            "the text on screen must be the answer the runtime holds",
            1,
            home.split("it.text == text.trim()").size - 1,
        )
        assertFalse("the UI file invented a say route", home.contains("/api/voice/say"))
    }

    @Test
    fun `every typed send goes through the wrapper, so no answer escapes the facts`() {
        val activity = source("MainActivity.kt")
        assertEquals(
            "a typed send still calls the session directly",
            3,
            activity.split("JarvisRuntime.sendTypedChat(").size - 1,
        )
        assertEquals(
            "a direct typed send remains in MainActivity",
            0,
            activity.split("chat.send(").size - 1,
        )
    }

    @Test
    fun `the speaker guard exists and the wording matches the voice path`() {
        val voice = source("voice/VoiceSession.kt")
        assertTrue(
            "VoiceSession exposes no busy guard for the one outside caller",
            voice.contains("fun speakerBusy(): Boolean = voiceBusy()"),
        )
        val readAloud = source("voice/ReadAloud.kt")
        val privateAloud = source("voice/PrivateAloud.kt")
        // Code only: the KDoc may NAME the existing route; a constant may not exist.
        val readAloudCode = readAloud.lines()
            .filterNot { it.trimStart().startsWith("*") || it.trimStart().startsWith("//") }
            .joinToString("\n")
        assertTrue(
            "the read-aloud object does not keep the named 24-sentence cap",
            readAloudCode.contains("const val READ_ALOUD_SENTENCE_CAP = 24"),
        )
        assertTrue(
            "the two on-screen sentences have drifted apart",
            readAloudCode.contains("const val ON_SCREEN = \"It's on your screen.\"") &&
                privateAloud.contains("const val ON_SCREEN = \"It's on your screen.\""),
        )
        assertFalse("the pure gate invented a route", readAloudCode.contains("/api/"))
    }

    @Test
    fun `a locked or backgrounded phone stops the read`() {
        // The `locked` fact is a snapshot of when the answer came in, so the read
        // asks the live question again before every sentence; leaving the screen
        // stops it outright (the Lead's ruling of 2026-10-27: privacy first).
        assertTrue("the read never re-checks the lock", runtime.contains("readAloudLockedNow()"))
        assertTrue("a lock found mid-read does not stop it", runtime.contains("if (readAloudLockedNow())"))
        assertTrue("a lock found mid-read does not call the stop path", runtime.contains("stopReadingAloud()"))
        val activity = source("MainActivity.kt")
        assertTrue(
            "leaving the screen does not stop the read",
            activity.contains("JarvisRuntime.stopReadingAloud()"),
        )
        assertTrue(
            "the screen leaving is not observed",
            activity.contains("Lifecycle.Event.ON_STOP"),
        )
    }

    @Test
    fun `a withheld read shows the one sentence instead of a dead control`() {
        val home = source("ui/screens/HomeScreen.kt")
        assertTrue("the withheld sentence is not drawn", home.contains("offer.withheld"))
        assertTrue(
            "the Read aloud control is not drawn once its facts allow it",
            home.contains("if (offer.mayRead)"),
        )
        assertTrue(
            "the refused answer's one sentence is not in the read path",
            runtime.contains("ReadAloud.ON_SCREEN"),
        )
    }

    // ------------- the owner's own okay (his decision of 2026-11-06) --------

    @Test
    fun `the typed path hands the phone's memory switch to the facts`() {
        val send = body(runtime, "suspend fun sendTypedChat(")
        assertTrue(
            "the typed answer's facts do not carry the phone's own memory setting",
            send.contains("phoneMemoryAloud = settings.readMemoriesAloud.value"),
        )
        // The facts are built with the live lock, and the one-off is drawn
        // against THE SAME read - never a second one that could disagree.
        assertTrue(
            "the answer's lock snapshot does not refresh the one-off's drawing",
            send.contains("_readAloudUnlocked.value = !facts.locked"),
        )
    }

    @Test
    fun `the one-off action is drawn only where the rule allows it, and reads once`() {
        val home = source("ui/screens/HomeScreen.kt")
        assertTrue(
            "the one-off action is not drawn at all",
            home.contains("offer.oneOffLabel(readAloudUnlocked)"),
        )
        assertTrue(
            "the one-off action does not go through the runtime",
            home.contains("readAloudLastAnswer(oneOff = true)"),
        )
        assertTrue(
            "the one-off action is drawn without the lock the runtime refreshed",
            home.contains("JarvisRuntime.readAloudUnlocked.collectAsState()"),
        )
        // It is the REFUSAL STRIP's control: it sits with the withheld
        // sentence, never in place of Read aloud on a readable answer.
        val withheldAt = home.indexOf("offer.withheld")
        val oneOffAt = home.indexOf("offer.oneOffLabel(readAloudUnlocked)")
        assertTrue("the one-off is not on the refusal strip", withheldAt > 0 && oneOffAt > withheldAt)
        // No auto-speak: the runtime has the one function and never starts a
        // read by itself - both calls are the owner's own taps in the UI.
        assertEquals(
            "the runtime starts a read on its own",
            1,
            runtime.split("readAloudLastAnswer(").size - 1,
        )
        // The tap asks the live questions again, and each hard refusal wins.
        val read = body(runtime, "suspend fun readAloudLastAnswer(oneOff: Boolean = false)")
        assertTrue("the one-off path does not ask the live lock", read.contains("readAloudLockedNow()"))
        assertTrue("a locked tap is not refused", read.contains("ReadAloud.LOCKED"))
        assertTrue("the one-off path does not ask the live link", read.contains("readAloudStaleNow()"))
        assertTrue("a stale tap is not refused", read.contains("ReadAloud.OFFLINE"))
        assertTrue(
            "the one-off is not limited to a memory-only or screen-only refusal",
            read.contains("offer.facts.oneOffAt(unlockedNow = true)"),
        )
        // Nothing about it is stored afterwards: no setting, no flow, no field.
        assertFalse("the one-off became a stored grant", runtime.contains("oneOff.value"))
        assertFalse("the one-off became a setting", runtime.contains("setOneOff"))
        assertFalse("a new route was invented for the one-off", runtime.contains("/api/voice/oneoff"))
    }

    @Test
    fun `the lock the one-off is drawn against is refreshed by the screen and the tap`() {
        val activity = source("MainActivity.kt")
        assertEquals(
            "the screen does not refresh the lock on the way in and out",
            2,
            activity.split("JarvisRuntime.refreshReadAloudUnlocked()").size - 1,
        )
        val read = body(runtime, "suspend fun readAloudLastAnswer(oneOff: Boolean = false)")
        assertTrue(
            "the tap does not refresh the drawing's lock",
            read.contains("_readAloudUnlocked.value = !lockedNow"),
        )
        assertTrue(
            "a lock found during a read does not clear the drawing's lock",
            runtime.contains("_readAloudUnlocked.value = false"),
        )
    }

    @Test
    fun `the memory refusal still says what happened, and names the switch`() {
        // The owner's report of 2026-11-06: "it said it was on my screen ...
        // even though it's okay to read these ones out loud". A memory-only
        // block must still say what happened, on both paths, with the switch
        // named while it is OFF.
        assertEquals(
            "the two memory sentences have drifted apart",
            ReadAloud.MEMORY_ON_SCREEN,
            PrivateAloud.MEMORY_ON_SCREEN,
        )
        assertEquals(
            "the two switch hints have drifted apart",
            ReadAloud.MEMORY_SWITCH_HINT,
            PrivateAloud.MEMORY_SWITCH_HINT,
        )
        assertTrue(
            "the hint does not name the button on the settings row",
            MemoryAloud.TURN_ON in ReadAloud.MEMORY_SWITCH_HINT,
        )
        assertEquals("Read them out", MemoryAloud.TURN_ON)
        // The strip says the memory sentence (ReadAloud.Facts.withheld), and
        // the voice path passes the live switch into its line so the hint is
        // said only while it is OFF.
        val voice = source("voice/VoiceSession.kt")
        assertTrue(
            "the voice path's memory line does not know the phone's setting",
            voice.contains("PrivateAloud.refusalLine(refusalNow(), memoryAloudOn())"),
        )
        val readAloud = source("voice/ReadAloud.kt")
        assertTrue(
            "the typed strip no longer says the memory sentence",
            readAloud.contains("MEMORY_ON_SCREEN"),
        )
        assertTrue(
            "the refusal strip stopped drawing the one sentence",
            source("ui/screens/HomeScreen.kt").contains("offer.withheld"),
        )
    }

    @Test
    fun `a voice question starting stops a read-aloud still playing`() {
        // The review's F1 (2026-10-27): the read refused to START over a voice
        // turn, but nothing stopped one already playing - and the talk button's
        // recorder takes its clip on VOICE_RECOGNITION with no echo canceller
        // (audio/Recorder.kt), so Jarvis's own reading could be recorded as the
        // owner's question. Pinned: the stop runs on EVERY turn (not only one
        // that has a "Try it" clip), the runtime installs it, it is guarded so
        // it cannot cut a spoken answer, the old KDoc is gone, and leaving the
        // Voices screen is not a question.
        val voice = source("voice/VoiceSession.kt")
        val turn = body(voice, "fun turnStarting() {")
        val hook = turn.indexOf("onQuestionStarting?.invoke()")
        assertTrue("a question starting does not stop a read-aloud", hook > 0)
        assertFalse(
            "the read's stop sits after the try-clip early return, so an ordinary turn never reaches it",
            turn.substring(0, hook).contains("if (!tryPlaying)"),
        )
        val install = runtime.lines()
            .firstOrNull { it.contains("onQuestionStarting =") }
            .orEmpty()
        assertTrue("nothing installs the read's stop on the voice path", install.isNotEmpty())
        assertTrue("the installed hook does not call the stop", install.contains("stopReadingAloud()"))
        assertTrue(
            "the installed hook is not guarded, so it would cut a spoken answer too",
            install.contains("readingAloud.value"),
        )
        assertFalse(
            "the KDoc still claims no answer can be playing when a turn starts",
            voice.contains("Stops nothing else: no answer is playing"),
        )
        val samples = body(voice, "fun stopSamples() {")
        assertFalse(
            "leaving the Voices screen stops a read-aloud that Home started",
            samples.contains("onQuestionStarting"),
        )
    }

    @Test
    fun `a new typed question stops the read before the answer is asked for`() {
        // The review's F2 (2026-10-27): `_readAloud.value = null` alone left the
        // OLD answer being read. From Send until the new answer finished there
        // was no control on screen (Home draws it only for the answer the
        // runtime holds, and only when nothing is streaming), and the control
        // then said "Stop" for the answer before it.
        val send = body(runtime, "suspend fun sendTypedChat(")
        val stop = send.indexOf("stopReadingAloud()")
        val clear = send.indexOf("_readAloud.value = null")
        val ask = send.indexOf("val answer = chat.send(")
        assertTrue("a new typed question does not stop the read-aloud", stop > 0)
        assertTrue("the offer is not cleared by the new question", clear > 0)
        assertTrue("this wrapper no longer asks the question; re-anchor this test", ask > 0)
        assertTrue("the read is stopped after the offer is already cleared", stop < clear)
        assertTrue("the read is stopped after the new question is sent", stop < ask)
        assertTrue(
            "the stop is not guarded on a read actually playing, so a typed question " +
                "sent over a spoken answer would cut the voice path's own speech",
            send.contains("if (readingAloud.value) stopReadingAloud()") ||
                send.contains("if (_readingAloud.value) stopReadingAloud()"),
        )
    }

    @Test
    fun `a typed question on the Live screen stops the read too`() {
        // F2b: the Live screen's box is a SECOND typed funnel - it
        // calls chat.send itself, so the wrapper above does not cover it.
        val live = body(runtime, "fun liveType(words: String, shared: String? = null) {")
        assertTrue(
            "the Live screen's typed question leaves a read-aloud playing",
            live.contains("stopReadingAloud()"),
        )
    }

    @Test
    fun `a rotation does not stop a read that is still on screen`() {
        // F3 is MANDATED (the Lead's 2026-10-27 ruling): rotation is not "away":
        // ON_STOP also fires for a configuration change - there is no
        // `configChanges` on MainActivity in AndroidManifest.xml - so turning
        // the phone sideways used to cut a read still in front of the owner.
        val activity = source("MainActivity.kt")
        val from = activity.indexOf("LifecycleEventObserver")
        val to = activity.indexOf("activity.lifecycle.addObserver(observer)")
        assertTrue("the ON_STOP observer is gone", from > 0 && to > from)
        val observer = activity.substring(from, to)
        assertTrue(
            "the observer no longer stops the read at all",
            observer.contains("JarvisRuntime.stopReadingAloud()"),
        )
        assertTrue(
            "a configuration change (a rotation) stops a read that is still on screen",
            observer.contains("isChangingConfigurations"),
        )
    }
}
