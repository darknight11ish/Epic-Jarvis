package com.jarvis.client

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The device tour's three dead ends stay closed.
 *
 * All three were measured on the owner's own phone on 2026-10-09
 * (`docs/ANDROID-TOUR-2026-10-09.md`):
 *
 *  1. **"Set Jarvis as the assistant app" did nothing.** The screen returned
 *     silently on both failure paths, and the phone answers the request with
 *     "Role is not requestable: android.app.role.ASSISTANT" without drawing
 *     anything at all (logcat, same session).
 *  2. **"Start link" read exactly the same before and after the tap**, so an
 *     owner who tapped twice could not tell the first tap worked.
 *  3. **Help told the owner to tap "Train my voice"** on a card that does not
 *     show that button until the phone is paired.
 *
 * Source-reading, the same shape as [LinkWordsTest]'s screen check: what these
 * three need is that the words and the second route exist at all, and a JVM
 * test has no phone to tap. Nothing here checks Android's own behaviour.
 */
class PhoneDeadEndsTest {

    @Test
    fun `the assistant role button reports what happened instead of returning silently`() {
        val main = repoFile(MAIN_ACTIVITY).readText()
        val request = main
            .substringAfter("private fun requestAssistantRole()")
            .substringBefore("private fun openAssistantSettings()")

        // Both silent paths now say something: the role being unrequestable on
        // this phone, and the request failing to launch.
        assertTrue(
            "requestAssistantRole() must report an outcome, not just return",
            request.contains("assistantRoleNote.value ="),
        )
        assertTrue(
            "a role request that fails to launch must not be swallowed",
            request.contains("isSuccess"),
        )
        assertFalse(
            "requestAssistantRole() is back to `?: return` with nothing said",
            request.contains("getSystemService(RoleManager::class.java) ?: return"),
        )

        // The second route: the one that worked on the owner's phone.
        assertTrue(
            "the assistant-settings fallback is gone",
            main.contains("private fun openAssistantSettings()"),
        )
        assertTrue(
            "ACTION_VOICE_INPUT_SETTINGS is the screen that resolves on the owner's phone",
            main.contains("Settings.ACTION_VOICE_INPUT_SETTINGS"),
        )
        assertTrue(
            "the default-apps list is the first fallback when that screen is absent",
            main.contains("Settings.ACTION_MANAGE_DEFAULT_APPS_SETTINGS"),
        )
        assertTrue(
            "the screen never gets the second route",
            main.contains("onOpenAssistantSettings = ::openAssistantSettings"),
        )
        assertTrue(
            "the outcome never reaches the card",
            main.contains("assistantRoleNote = assistantRoleNote.value"),
        )
        assertTrue(
            "the line shown must name the button that works",
            // The words are one Kotlin string split over two lines, so this
            // checks the half that cannot be split rather than the whole label.
            main.substringAfter("ASSISTANT_ROLE_NOT_DONE =").take(300)
                .contains("Open Android's assistant"),
        )
        // The result callback is where a phone that refuses the request is
        // caught, so it must look at the role again rather than trust the
        // result code.
        assertTrue(
            "the role result callback does not re-read the real state",
            main.contains("if (!PlatformReadiness.assistantRoleHeld(this))"),
        )
    }

    @Test
    fun `Start link leaves a line saying what the tap did`() {
        val main = repoFile(MAIN_ACTIVITY).readText()
        assertTrue(
            "onStartService must set a line the card can show",
            main.contains("linkStartNote.value ="),
        )
        // Unpaired is the case the tour ran in: there is nothing for the link
        // to reach, and the card should say so rather than stay reassuring.
        val setter = main.substringAfter("linkStartNote.value =").take(500)
        assertTrue(
            "the unpaired case must be named",
            setter.contains("not paired"),
        )
        val read = repoFile(READINESS_SCREEN).readText()
        assertTrue("the Start link card does not draw that line", read.contains("note = linkStartNote"))
    }

    @Test
    fun `the assistant and Start link cards can show a second route and a line`() {
        val read = repoFile(READINESS_SCREEN).readText()
        assertTrue(
            "the second route is not built for the assistant card",
            read.contains("CardFix.Alternative("),
        )
        assertTrue(
            "the second route is never drawn",
            read.contains("alternative.label"),
        )
        assertTrue(
            "the outcome line is never drawn",
            read.contains("val note = fix.note"),
        )
        assertTrue(
            "the assistant card does not pass its own line",
            read.contains("note = assistantRoleNote"),
        )
    }

    @Test
    fun `Help names the pairing condition before pointing at Train my voice`() {
        val faq = repoFile(FAQ_SCREEN).readText()
        val answer = faq
            .substringAfter("How do I teach Jarvis my voice? Where is the talk button?")
            .substringBefore("    Faq(")
        assertTrue(
            "the answer must still say where the button is",
            answer.contains("Train my voice"),
        )
        assertTrue(
            "the answer points at a button that is not there when unpaired",
            answer.contains("Pair this phone with your desktop first"),
        )
        assertTrue(
            "the answer must say when the button appears",
            answer.contains("Unknown"),
        )
    }

    /** Walks up from Gradle's working folder (`jarvis-client/app`) to the repository. */
    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private companion object {
        const val BASE = "jarvis-client/app/src/main/java/com/jarvis/client/"
        const val MAIN_ACTIVITY = BASE + "MainActivity.kt"
        const val READINESS_SCREEN = BASE + "ui/screens/ReadinessScreen.kt"
        const val FAQ_SCREEN = BASE + "ui/screens/FaqScreen.kt"
    }
}
