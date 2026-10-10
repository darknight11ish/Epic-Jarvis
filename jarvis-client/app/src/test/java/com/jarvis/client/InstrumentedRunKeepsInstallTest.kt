package com.jarvis.client

import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * A connected test run must not uninstall the app.
 *
 * `connectedDebugAndroidTest` removes both APKs when it finishes, and the app's
 * data goes with them — which is where this phone's pairing key lives. That is
 * not a theory: on 2026-10-10 a run of the six instrumented classes left the
 * owner's phone uninstalled, `adb shell am start` answering "Activity class
 * {com.jarvis.client/com.jarvis.client.MainActivity} does not exist", and the
 * phone had to be paired again from scratch (card, Windows Hello, new key):
 * see `docs/ANDROID-PAIRED-AUDIT-2026-10-10.md`.
 *
 * Android Gradle Plugin reads `android.injected.androidTest.
 * leaveApksInstalledAfterRun` from `gradle.properties`, and with it set the run
 * leaves the phone as it found it. This test exists so the line cannot be lost
 * quietly — the failure it prevents is silent, expensive, and only shows up on
 * a real paired phone, which is exactly the kind of thing a comment does not
 * protect.
 */
class InstrumentedRunKeepsInstallTest {

    @Test
    fun `a connected test run is told to leave the app installed`() {
        val props = repoFile("jarvis-client/gradle.properties").readText()
        val line = props.lineSequence()
            .map { it.trim() }
            .firstOrNull { it.startsWith("android.injected.androidTest.leaveApksInstalledAfterRun") }
        assertTrue(
            "gradle.properties must set " +
                "android.injected.androidTest.leaveApksInstalledAfterRun=true: without it every " +
                "connected test run uninstalls the app and takes the phone's pairing with it " +
                "(docs/ANDROID-PAIRED-AUDIT-2026-10-10.md)",
            line == "android.injected.androidTest.leaveApksInstalledAfterRun=true",
        )
        // A commented-out copy is not the setting: `#` in front changes nothing
        // for Gradle, and this check would read it as present.
        assertTrue(
            "the setting must be live, not commented out",
            !line!!.startsWith("#"),
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
}
