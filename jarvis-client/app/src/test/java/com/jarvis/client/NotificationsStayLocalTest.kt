package com.jarvis.client

import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Every notification Jarvis posts stays on this phone unless the owner
 * turned on "Show notifications on a compatible watch" (Brain, off by
 * default; [com.jarvis.client.net.WatchNotify], the owner's decision,
 * 2026-09-25, reconfirmed 2026-09-27, Q17). Android copies a phone's
 * notifications to a paired smartwatch by default, which would put approval
 * titles, reminders and "tell me when" alerts on a device this app knows
 * nothing about unless something refuses it. `setLocalOnly(true)` refuses
 * it (2026-09-26); since the setting was added, that call reads
 * `!JarvisRuntime.watchNotificationsAllowed()` instead - `true` while the
 * setting is off (the default and every unopened app's starting state),
 * `false` only once the PC has confirmed the owner turned it on.
 *
 * Reads the source, like the other contract tests: every
 * `NotificationCompat.Builder(` in the app must reach a `.setLocalOnly(...)`
 * whose argument is exactly `true` or, since the setting, the negation of
 * [com.jarvis.client.JarvisRuntime.watchNotificationsAllowed] - never a bare
 * variable this test cannot trace back to that one source of truth - before
 * its `.build()`.
 */
class NotificationsStayLocalTest {

    private fun sources(): List<File> {
        val root = listOf(File("src/main/java"), File("app/src/main/java"),
            File("jarvis-client/app/src/main/java")).firstOrNull { it.isDirectory }
            ?: return emptyList()
        return root.walkTopDown().filter { it.isFile && it.extension == "kt" }.toList()
    }

    @Test
    fun everyNotificationIsLocalOnly() {
        val files = sources()
        assertTrue("the app's sources were not found", files.isNotEmpty())
        var builders = 0
        for (file in files) {
            val text = file.readText()
            var at = text.indexOf("NotificationCompat.Builder(")
            while (at >= 0) {
                builders += 1
                val end = text.indexOf(".build()", at).let { if (it < 0) text.length else it }
                val chain = text.substring(at, end)
                assertTrue(
                    "${file.name}: a notification is built without a traceable setLocalOnly",
                    ".setLocalOnly(true)" in chain ||
                        ".setLocalOnly(!JarvisRuntime.watchNotificationsAllowed())" in chain,
                )
                at = text.indexOf("NotificationCompat.Builder(", at + 1)
            }
        }
        // The approval, schedule, link and wake-word notifications at least.
        assertTrue("only $builders notification builders found", builders >= 8)
    }
}
