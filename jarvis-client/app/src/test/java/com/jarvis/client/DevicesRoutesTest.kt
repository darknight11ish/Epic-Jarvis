package com.jarvis.client

import com.jarvis.client.net.Devices
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Every device route the app posts to must be on the one list its sender checks.
 *
 * "Name this device…" did not work on 2026-10-10, and the reason was one line:
 * `Devices.LABEL_PATH` existed, `JarvisRuntime.renameDevice` called
 * `api.devicesPost` with it, and `devicesPost`'s guard still listed only
 * `REMOVE_PATH` and `SHARED_PATH` - so the call was refused *inside the phone*
 * and the UI reported "Your PC answered in a way this app can't read", which
 * sent the owner to update a PC that was already up to date. The route never
 * left the device.
 *
 * Two checks, because either one alone would let the same mistake back in:
 * the list must name every route, and the sender must read that list rather
 * than a pair written out by hand.
 */
class DevicesRoutesTest {

    @Test
    fun `the one list names every device route the app posts to`() {
        val devices = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/net/Devices.kt").readText()
        val list = Regex("val POST_PATHS[^=]*=\\s*setOf\\(([^)]*)\\)")
            .find(devices)?.groupValues?.get(1)
            ?: error("Devices.POST_PATHS is no longer a `setOf(...)` - this check cannot read it")
        for (name in listOf("REMOVE_PATH", "LABEL_PATH", "SHARED_PATH")) {
            assertTrue(
                "$name must be on Devices.POST_PATHS, or the route it names is refused inside " +
                    "the phone and reported as the PC's fault",
                list.contains(name),
            )
        }
    }

    @Test
    fun `the sender checks that list, not a pair written out by hand`() {
        val api = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/net/JarvisApi.kt").readText()
        assertTrue(
            "devicesPost must gate on Devices.POST_PATHS",
            api.contains("path !in Devices.POST_PATHS"),
        )
    }

    @Test
    fun `the label route is one the app may post to`() {
        assertTrue(
            "the label route is what \"Name this device…\" sends",
            Devices.LABEL_PATH in Devices.POST_PATHS,
        )
        assertEquals("/api/devices/label", Devices.LABEL_PATH)
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
