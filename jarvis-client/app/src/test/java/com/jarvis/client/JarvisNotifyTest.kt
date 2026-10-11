package com.jarvis.client

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "Notifications from Jarvis" - the phone row the owner chose on 2026-10-09,
 * after `docs/SETTINGS-COVERAGE-AUDIT-2026-10-09.md` (GAP 1) found the PC's
 * Notifications card had no phone counterpart.
 *
 * The decision, in the owner's words: **one row that opens Android's own
 * per-app notification screen**, not a second copy of the PC's four switches
 * and quiet hours (which would have to agree with Android's own settings, and
 * could drift from them).
 *
 * What this holds in place:
 *  - the row exists on Settings, is in the jump list, and is NOT a hideable
 *    menu (there is no phone menu id for it - the registry's own
 *    "notifications" Section is desktop-only, because the four switches and
 *    quiet hours really are the PC's);
 *  - the button opens `Settings.ACTION_APP_NOTIFICATION_SETTINGS` under
 *    Jarvis's own package, with Android's Settings as the fallback;
 *  - the words name which app owns which half, because that is the confusing
 *    part of two notification screens on one phone.
 *
 * Source-reading, like [LinkWordsTest]'s screen check - no phone is needed to
 * hold a row and its route in place.
 */
class JarvisNotifyTest {

    @Test
    fun `the Settings row exists, is in the jump list, and is not a hideable menu`() {
        val settings = repoFile(SETTINGS).readText()
        assertTrue(
            "SettingsScreen has no item(key = \"jarvis-notify\")",
            settings.contains("item(key = \"jarvis-notify\")"),
        )
        assertTrue(
            "the row does not draw the section",
            settings.contains("NotificationsFromJarvisSection(onOpen = onOpenNotificationSettings)"),
        )
        assertFalse(
            "the row must not be behind a menu guard: there is no phone menu id for it",
            settings.contains("settings.jarvis-notify"),
        )
        assertTrue(
            "the jump list has no entry for the row (SettingsJumpTest would also fail)",
            repoFile(JUMP).readText()
                .contains("Entry(\"Notifications from Jarvis\", \"jarvis-notify\")"),
        )
    }

    @Test
    fun `the row opens Android's own per-app notification screen`() {
        val plate = repoFile(PLATE).readText()
        assertTrue("the section does not say what the button opens", plate.contains("Open Android's notification settings"))
        assertTrue("the button is not wired to its callback", plate.contains("onClick = onOpen"))
        val main = repoFile(MAIN).readText()
        assertTrue(
            "MainActivity never hands the row its route",
            main.contains("onOpenNotificationSettings = { openAppNotificationSettings() }"),
        )
        val helper = main
            .substringAfter("private fun openAppNotificationSettings()")
            .substringBefore("private fun requestBatteryExemption()")
        assertTrue(
            "the helper does not open Android's per-app notification screen",
            helper.contains("Settings.ACTION_APP_NOTIFICATION_SETTINGS"),
        )
        assertTrue("the screen is not aimed at Jarvis's own entry", helper.contains("Settings.EXTRA_APP_PACKAGE"))
        assertTrue(
            "the helper must fall back to Android's Settings rather than open nothing",
            helper.contains("Settings.ACTION_SETTINGS"),
        )
    }

    @Test
    fun `the words say which app owns which half`() {
        val plate = repoFile(PLATE).readText()
        assertTrue("the section must say Android owns the phone's switches", plate.contains("Android decides"))
        assertTrue(
            "the section must say the PC still owns what gets sent",
            plate.contains("PC's own Notifications card"),
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
        const val MAIN = BASE + "MainActivity.kt"
        const val SETTINGS = BASE + "ui/screens/SettingsScreen.kt"
        const val PLATE = BASE + "ui/screens/JarvisNotifyPlate.kt"
        const val JUMP = BASE + "ui/SettingsJump.kt"
    }
}
