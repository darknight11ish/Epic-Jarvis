package com.jarvis.client.service

import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * A read-aloud carries on when the app is left (the owner, 2026-11-15:
 * *"when i move out of the jarvis android app on my phone ... it should
 * continue the read outloud ... right now it stops it"*, and his answer that a
 * locked phone keeps going too).
 *
 * This is a SOURCE-PIN suite, deliberately: what it guards is a handful of
 * lines whose absence silently restores the old behaviour, and none of them can
 * be reached from a JVM test (a foreground service, a lifecycle observer and a
 * manifest attribute are all Android). The behaviour itself is proved on the
 * phone: start a read, press HOME, lock the screen, and hear it finish.
 *
 * The pins:
 *  * the activity no longer stops a read when it leaves the screen;
 *  * neither read loop stops for a lock landing mid-read;
 *  * a read starts and stops the service that keeps the process awake;
 *  * the service is declared `mediaPlayback`, with the permission Android 14+
 *    requires, and its Stop control goes through the one door that ends a read.
 */
class ReadAloudContinuityTest {

    private fun source(path: String): String = File(path).readText()

    private val activity = "src/main/java/com/jarvis/client/MainActivity.kt"
    private val runtime = "src/main/java/com/jarvis/client/JarvisRuntime.kt"
    private val service = "src/main/java/com/jarvis/client/service/ReadAloudService.kt"
    private val manifest = "src/main/AndroidManifest.xml"

    @Test
    fun `leaving the app does not stop a read`() {
        val text = source(activity)
        assertTrue(
            "MainActivity must not stop a read when the screen leaves",
            !text.contains("JarvisRuntime.stopReadingAloud()"),
        )
        assertTrue(
            "the ON_STOP branch must still refresh the one-off offer",
            text.contains("ON_STOP ->") && text.contains("refreshReadAloudUnlocked()"),
        )
    }

    @Test
    fun `a lock landing mid-read does not stop it`() {
        val text = source(runtime)
        // Both read loops begin with this line; neither loop may ask the lock
        // question again inside itself.
        val loops = text.split("for (sentence in sentences) {").drop(1)
        assertTrue("both read loops must still exist", loops.size == 2)
        loops.forEachIndexed { index, body ->
            val head = body.take(900)
            assertTrue(
                "read loop $index must not stop for a lock mid-read",
                !head.contains("readAloudLockedNow("),
            )
        }
        assertTrue(
            "the old mid-read comment must be gone",
            !text.contains("The lock is asked again before every sentence"),
        )
        // ...while the START of a read still refuses on a locked phone.
        assertTrue(
            "a read must still refuse to START on a locked phone",
            text.contains("if (readAloudLockedNow())"),
        )
    }

    @Test
    fun `a read starts and stops the service that keeps it alive`() {
        val text = source(runtime)
        assertTrue(text.contains("ReadAloudService.start(appContext)"))
        assertTrue(text.contains("ReadAloudService.stop(appContext)"))
        val stops = Regex("ReadAloudService\\.stop\\(appContext\\)").findAll(text).count()
        assertTrue("both reads and the Stop button must stop it", stops >= 3)
    }

    @Test
    fun `the service is a media playback foreground service`() {
        val text = source(service)
        assertTrue(
            "it must go foreground as mediaPlayback",
            text.contains("FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK"),
        )
        assertTrue(
            "it must not be sticky: no read, no service",
            text.contains("START_NOT_STICKY"),
        )
        assertTrue(
            "Stop must end the read through the runtime's one door",
            text.contains("JarvisRuntime.stopReadingAloud()"),
        )
        val manifestText = source(manifest)
        assertTrue(
            "the permission Android 14+ needs for this type",
            manifestText.contains("android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK"),
        )
        assertTrue(
            "the service must be declared with its type",
            manifestText.contains(".service.ReadAloudService")
                && manifestText.contains("foregroundServiceType=\"mediaPlayback\""),
        )
    }

    @Test
    fun `the notification has its own id, out of the shared registry`() {
        val ids = source("src/main/java/com/jarvis/client/service/NotificationIds.kt")
        assertTrue(ids.contains("const val READ_ALOUD ="))
        assertTrue(ids.contains("\"READ_ALOUD\" to READ_ALOUD"))
        assertTrue(source(service).contains("NotificationIds.READ_ALOUD"))
    }
}
