package com.jarvis.client

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
        // The facts come from the SAME watch the voice path uses.
        assertTrue("the route is not read the voice path's way", runtime.contains("PrivateAloud.route(header)"))
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
}
