package com.jarvis.client

import com.jarvis.client.net.Handsfree
import com.jarvis.client.voice.MemoryAloud
import com.jarvis.client.voice.PrivateAloud
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The wiring pins for the owner's setting of 2026-11-05 (the phone may read
 * out an answer that uses what Jarvis remembers). It is ON by default since
 * the owner's decision of 2026-11-07, it covers every voice answer on this
 * phone, and the PC now has its own separate read-aloud switch (Wave 9).
 *
 * The decision itself is pure and lives in `PrivateAloud` (`PrivateAloudTest`
 * and `MemoryAloudTest` hold every branch and every sentence). What cannot be
 * run on the JVM is the Android half, and this repository's own precedent
 * (`CallRecordSourcePinTest`, `R8SourcePinTest`) is to hold each fact that
 * would otherwise rest on a promise by reading the shipped source for the
 * exact line - or for the line that must never appear.
 *
 * The two facts that matter most here, and why they are pinned:
 *
 *  - **the lock state is read at the PRESS and never again.** The owner's
 *    instruction of 2026-11-05 was explicit: capture `isDeviceLocked` when he
 *    presses the mic, do not re-read it later. So `MainActivity.beginVoice`
 *    must read it, hand it to `VoiceSession.begin`, and `VoiceSession` must
 *    not ask Android anything about the keyguard at all.
 *  - **the setting cannot reach "hey Jarvis" or Jarvis Live.** It applies only
 *    when the request's `source` is `push_to_talk` AND the PC's own reply says
 *    `mode: "quick_message"` - the one clip that runs no voice check. Both are
 *    pinned in one expression, so removing either half fails here.
 */
class MemoryAloudWiringTest {

    private val main = "jarvis-client/app/src/main/java/com/jarvis/client/"

    private fun text(rel: String): String = SourceFile.read(main + rel)

    /** The file's code only: KDoc lines that explain a rule must not trip a "never" pin. */
    private fun code(raw: String): String = raw.lines().joinToString("\n") { line ->
        val t = line.trimStart()
        when {
            t.startsWith("//") || t.startsWith("*") || t.startsWith("/*") -> ""
            else -> line.substringBefore(" //")
        }
    }

    private fun body(src: String, marker: String, chars: Int = 1_200): String {
        val at = src.indexOf(marker)
        assertTrue("$marker is gone", at >= 0)
        return src.substring(at, minOf(src.length, at + chars))
    }

    // ------------------------------------------------- the press, once ------

    @Test
    fun `the lock state is read at the press, before the microphone opens`() {
        val activity = code(text("MainActivity.kt"))
        val press = body(activity, "private fun beginVoice()", 1_400)
        // Read once, here, and only here.
        assertTrue(press, "DeviceSecure.isLocked(this)" in press)
        // Both ways into the capture carry that one answer: the direct path
        // and the permission-grant callback.
        assertEquals(
            "the captured state must reach both voice.begin calls",
            2,
            Regex("voice\\.begin\\(unlockedAtPress = unlockedAtPress\\)").findAll(press).count(),
        )
        // Nothing may open the microphone without it.
        assertFalse(activity, "voice.begin()" in activity)
        // The press is the act: the permission dialog does not re-read it.
        assertTrue(press, press.indexOf("DeviceSecure.isLocked(this)") < press.indexOf("micPermission.launch"))
    }

    @Test
    fun `the voice session never reads the keyguard itself`() {
        val voice = code(text("voice/VoiceSession.kt"))
        for (never in listOf("KeyguardManager", "isDeviceLocked", "isKeyguardLocked", "DeviceSecure")) {
            assertFalse("VoiceSession must not read $never", never in voice)
        }
        // ...it carries the answer the press captured, on the turn.
        assertTrue(voice, "fun begin(source: String = JarvisApi.SOURCE_PUSH_TO_TALK, unlockedAtPress: Boolean = false)" in voice)
        assertTrue(voice, "turn.unlockedAtPress = unlockedAtPress" in voice)
    }

    @Test
    fun `the device helper fails closed as locked`() {
        val helper = code(text("platform/DeviceSecure.kt"))
        assertTrue(helper, "fun isLocked(context: Context): Boolean" in helper)
        // A phone that cannot say counts as locked (keeps the answer on screen).
        assertTrue(helper, "keyguard?.isDeviceLocked ?: true" in helper)
        assertTrue(helper, ".getOrDefault(true)" in helper)
    }

    // ------------------------------------- the talk button, and only it -----

    @Test
    fun `only the phone's mic press, as the PC's quick message, may use the setting`() {
        val voice = code(text("voice/VoiceSession.kt"))
        assertTrue(
            voice,
            "turn.talkButton = source == JarvisApi.SOURCE_PUSH_TO_TALK &&" in voice,
        )
        assertTrue(voice, "heard.mode == PrivateAloud.QUICK_MESSAGE" in voice)
        assertEquals("quick_message", PrivateAloud.QUICK_MESSAGE)
        // The rule is asked once per sentence, through the reason: the
        // decision and the line said about it come from the same read.
        assertTrue(voice, "mayRead = { refusalNow() == PrivateAloud.Refusal.NONE }" in voice)
        // The line knows the phone's own memory setting (the owner's decision
        // of 2026-11-06): a remembered-facts refusal names "Read them out" while
        // that switch is OFF, and says only the sentence while it is on.
        assertTrue(
            voice,
            "privateLine = { PrivateAloud.refusalLine(refusalNow(), memoryAloudOn()) }" in voice,
        )
        // All three facts of the setting reach the rule.
        assertTrue(voice, "phoneMemoryAloud = memoryAloudOn()" in voice)
        assertTrue(voice, "talkButton = turn.talkButton" in voice)
        assertTrue(voice, "unlockedAtPress = turn.unlockedAtPress" in voice)
    }

    @Test
    fun `the phone's setting is read live and is the off-by-default one`() {
        val runtime = code(text("JarvisRuntime.kt"))
        assertTrue(runtime, "memoryAloudOn = { clientSettings.readMemoriesAloud.value }" in runtime)
        val settings = code(text("data/ClientSettings.kt"))
        assertTrue(settings, "KEY_READ_MEMORIES_ALOUD = \"read_memories_aloud\"" in settings)
        assertTrue(settings, "prefs.getBoolean(KEY_READ_MEMORIES_ALOUD, PrivateAloud.MEMORY_ALOUD_DEFAULT)" in settings)
        // The owner's decision of 2026-11-07: ON by default.
        assertTrue(PrivateAloud.MEMORY_ALOUD_DEFAULT)
    }

    // ----------------------------------------------- the row on the screen ---

    @Test
    fun `the settings row draws the setting's own words and says it is off by default`() {
        val plate = text("ui/screens/VoiceSwitchesPlate.kt")
        for (line in listOf(
            "com.jarvis.client.voice.MemoryAloud.NAME",
            "com.jarvis.client.voice.MemoryAloud.describe(memoryAloud)",
            "com.jarvis.client.voice.MemoryAloud.TURN_ON",
            "com.jarvis.client.voice.MemoryAloud.TURN_OFF",
            "com.jarvis.client.voice.MemoryAloud.NOTE",
        )) {
            assertTrue("the row no longer draws $line", line in plate)
        }
        // The switch is drawn only where the screen owns it.
        assertTrue(plate, "memoryAloud != null && onMemoryAloud != null" in plate)
        // ...and the real screen passes it, with its own setter.
        val activity = code(text("MainActivity.kt"))
        assertTrue(activity, "memoryAloud = memoryAloudOn," in activity)
        assertTrue(activity, "onMemoryAloud = { on -> JarvisRuntime.settings.setReadMemoriesAloud(on) }" in activity)
        assertTrue(activity, "JarvisRuntime.settings.readMemoriesAloud.collectAsState()" in activity)
    }

    // ------------------------------------- the hands-free status line (C) ---

    @Test
    fun `Home draws no hands-free line for a PC that does not have it`() {
        // The rule's own words: a missing or unavailable feature answers null.
        assertNull(Handsfree.oneLine(null, missing = true))
        assertNull(Handsfree.oneLine(Handsfree.Read(available = false, enabled = false), missing = false))
        assertEquals(Handsfree.ARMED_SHORT, Handsfree.oneLine(Handsfree.Read(available = true, enabled = true), missing = false))
        // The engine must not reach for the "not on this PC" sentence at all:
        // it lives in the Settings row, where the switch would be.
        val handsfree = code(text("net/Handsfree.kt"))
        assertFalse("NOT_HERE_SHORT" in handsfree)
        val line = body(handsfree, "fun oneLine(read: Read?, missing: Boolean): String?", 400)
        assertFalse(line, "NOT_HERE" in line)
        assertTrue(line, "ARMED_SHORT" in line)
        // Settings still says it plainly (the sentence itself lives in
        // Handsfree.NOT_HERE; the section row is where it is drawn).
        assertTrue(Handsfree.NOT_HERE in text("net/Handsfree.kt"))
        assertTrue("Handsfree.NOT_HERE" in text("ui/screens/HandsfreeSection.kt"))
    }

    @Test
    fun `the memory sentence is not a card line and the shared line is untouched`() {
        assertEquals("It's on your screen.", PrivateAloud.ON_SCREEN)
        assertFalse(com.jarvis.client.voice.CardVoice.isCardLine(PrivateAloud.MEMORY_ON_SCREEN))
        assertFalse(com.jarvis.client.voice.CardVoice.isCardLine(PrivateAloud.ON_SCREEN))
        assertEquals(PrivateAloud.MEMORY_ON_SCREEN, PrivateAloud.refusalLine(PrivateAloud.Refusal.MEMORY))
        assertEquals(PrivateAloud.ON_SCREEN, PrivateAloud.refusalLine(PrivateAloud.Refusal.TOOL))
        assertEquals(MemoryAloud.NAME, "Read out answers that use what Jarvis remembers")
    }

    @Test
    fun `the settings row draws the one-line default subtitle, and no banner (Q7)`() {
        val plate = code(text("ui/screens/VoiceSwitchesPlate.kt"))
        assertTrue("the row's name is gone", "MemoryAloud.NAME" in plate)
        assertTrue("Q7's subtitle is not drawn", "MemoryAloud.SUBTITLE" in plate)
        // One line under the name - not a card/banner with its own controls.
        assertFalse("a banner was added instead of a subtitle", "Banner" in plate)
        assertTrue(MemoryAloud.SUBTITLE, "On by default" in MemoryAloud.SUBTITLE)
    }
}
