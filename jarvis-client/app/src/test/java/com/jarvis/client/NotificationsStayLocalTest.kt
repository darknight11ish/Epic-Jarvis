package com.jarvis.client

import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Every notification Jarvis posts is local only. Android copies a phone's
 * notifications to a paired smartwatch (and other bridged devices) by
 * default, which would put approval titles, reminders and "tell me when"
 * alerts on a device this app knows nothing about. `setLocalOnly(true)`
 * keeps each one on this phone (2026-09-26).
 *
 * Reads the source, like the other contract tests: every
 * `NotificationCompat.Builder(` in the app must reach `.setLocalOnly(true)`
 * before its `.build()`.
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
                    "${file.name}: a notification is built without setLocalOnly(true)",
                    ".setLocalOnly(true)" in chain,
                )
                at = text.indexOf("NotificationCompat.Builder(", at + 1)
            }
        }
        // The approval, schedule, link and wake-word notifications at least.
        assertTrue("only $builders notification builders found", builders >= 8)
    }
}
