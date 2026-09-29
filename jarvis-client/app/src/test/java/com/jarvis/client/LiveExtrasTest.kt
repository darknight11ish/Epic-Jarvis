package com.jarvis.client

import com.jarvis.client.data.LiveEnd
import com.jarvis.client.data.Security
import com.jarvis.client.data.SecurityRules
import com.jarvis.client.voice.LiveExtras
import com.jarvis.client.voice.LiveRules
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The Jarvis Live extras (the owner's decisions of 2026-09-28): the tile,
 * the headset button, "Live ended - Resume", the Bluetooth headset
 * microphone, "End Live when" on the Security screen, and "Talk about this
 * in Live" - their rules, and (reading the source, like the other contract
 * tests) that the headset button and the tile never approve anything.
 */
class LiveExtrasTest {

    private fun on(minutes: Int, device: String = "phone"): JsonObject = buildJsonObject {
        put("state", "on")
        put("on", true)
        put("device", device)
        put("minutes_left", minutes)
    }

    @Test
    fun `the tile - on here with the minutes left, else where it is`() {
        assertEquals(LiveExtras.Tile(true, "12 min left"), LiveExtras.tile(on(12), connected = true))
        assertEquals(LiveExtras.Tile(false, "On your PC"), LiveExtras.tile(on(5, "desktop"), connected = true))
        assertEquals(LiveExtras.Tile(false, "Off"), LiveExtras.tile(null, connected = true))
        assertEquals(LiveExtras.Tile(false, "Offline"), LiveExtras.tile(null, connected = false))
        // On here, even offline: End must stay reachable (it is never held).
        assertTrue(LiveExtras.tile(on(3), connected = false).on)
    }

    @Test
    fun `the headset button - press stops talking, a hold toggles the mic, once`() {
        val k = LiveExtras.HeadsetKeys()
        assertEquals(LiveExtras.Press.NONE, k.onKey(LiveExtras.DOWN, 79, 0, 1000, 1000))
        assertEquals(LiveExtras.Press.STOP_TALKING, k.onKey(LiveExtras.UP, 79, 0, 1000, 1150))
        // Held: the key repeats; the long press fires once, the release does nothing.
        assertEquals(LiveExtras.Press.NONE, k.onKey(LiveExtras.DOWN, 85, 0, 2000, 2000))
        assertEquals(LiveExtras.Press.NONE, k.onKey(LiveExtras.DOWN, 85, 1, 2000, 2300))
        assertEquals(LiveExtras.Press.MIC_TOGGLE, k.onKey(LiveExtras.DOWN, 85, 2, 2000, 2700))
        assertEquals(LiveExtras.Press.NONE, k.onKey(LiveExtras.DOWN, 85, 3, 2000, 2900))
        assertEquals(LiveExtras.Press.NONE, k.onKey(LiveExtras.UP, 85, 0, 2000, 3000))
        // A headset that sends no repeats: a long hold is read on release.
        assertEquals(LiveExtras.Press.NONE, k.onKey(LiveExtras.DOWN, 79, 0, 5000, 5000))
        assertEquals(LiveExtras.Press.MIC_TOGGLE, k.onKey(LiveExtras.UP, 79, 0, 5000, 5800))
        // Any other key: nothing.
        assertEquals(LiveExtras.Press.NONE, k.onKey(LiveExtras.DOWN, 87, 0, 6000, 6000))
        assertEquals(LiveExtras.Press.NONE, k.onKey(LiveExtras.UP, 87, 0, 6000, 6100))
        // An up with no down (a stray event): nothing.
        assertEquals(LiveExtras.Press.NONE, LiveExtras.HeadsetKeys().onKey(LiveExtras.UP, 79, 0, 0, 10))
    }

    @Test
    fun `the headset button and the tile never approve anything`() {
        val root = listOf(File("src/main/java"), File("app/src/main/java"),
            File("jarvis-client/app/src/main/java")).first { it.isDirectory }
        val service = File(root, "com/jarvis/client/service/LiveService.kt").readText()
        val cb = service.substring(service.indexOf("private fun onHeadset("))
        val body = cb.substring(0, cb.indexOf("\n    }\n"))
        for (word in listOf("approve", "decide", "deny", "pending", "Approval")) {
            assertFalse("the headset button's code names '$word'", body.contains(word, ignoreCase = true))
        }
        assertTrue(body.contains("stopSpeaking()"))
        assertTrue(body.contains("liveMute("))
        val tile = File(root, "com/jarvis/client/service/LiveTileService.kt").readText()
        for (word in listOf("approve", "decide(", "deny(", "JarvisRuntime.pending")) {
            assertFalse("the tile names '$word'", tile.contains(word, ignoreCase = true))
        }
        assertTrue("the tile ends Live directly (never held)", tile.contains("liveEndNow(\"owner\")"))
        assertTrue("the tile starts Live through the app (after App lock)", tile.contains("ACTION_START_LIVE"))
    }

    @Test
    fun `Live ended - Resume - only after an end here that the PC can resume, for what is left`() {
        val ended = buildJsonObject {
            put("state", "ended")
            put("on", false)
            put("ended_device", "phone")
            put("resumable", true)
            put("ended_ago_s", 60)
            put("limits", buildJsonObject { put("resume_s", 600) })
        }
        assertEquals(540_000L, LiveExtras.resumeFor(ended))
        val obj = { k: String, v: Any ->
            JsonObject(ended.toMutableMap().apply {
                put(k, if (v is Boolean) JsonPrimitive(v) else if (v is Int) JsonPrimitive(v) else JsonPrimitive(v as String))
            })
        }
        assertNull("not resumable (the owner ended it)", LiveExtras.resumeFor(obj("resumable", false)))
        assertNull("ended on the PC", LiveExtras.resumeFor(obj("ended_device", "desktop")))
        assertNull("the 10 minutes are up", LiveExtras.resumeFor(obj("ended_ago_s", 600)))
        assertNull(LiveExtras.resumeFor(on(3)))
        assertEquals(LiveRules.RESUME_S, 600)
    }

    @Test
    fun `the Bluetooth headset's microphone is preferred, and the screen says which`() {
        val phone = LiveExtras.Mic(15, "")
        val sco = LiveExtras.Mic(7, "Buds")
        val le = LiveExtras.Mic(26, "LE Buds")
        assertNull(LiveExtras.pickHeadset(listOf(phone)))
        assertEquals(sco, LiveExtras.pickHeadset(listOf(phone, sco)))
        assertEquals(le, LiveExtras.pickHeadset(listOf(sco, phone, le)))
        assertEquals(LiveExtras.MIC_PHONE, LiveExtras.micWords(null))
        assertEquals("Microphone: your Bluetooth headset (Buds)", LiveExtras.micWords(sco))
        assertEquals(LiveExtras.MIC_FELL_BACK, LiveExtras.micWords(sco, fellBack = true))
        assertTrue(LiveExtras.HEADSET_HINT.contains("never approves"))
    }

    @Test
    fun `End Live when - strict by default, the looser choice asks, back is instant`() {
        val base = Security(appLock = true)
        assertEquals(LiveEnd.APP_LOCK, base.liveEnd)
        assertTrue(SecurityRules.loosens(base, base.copy(liveEnd = LiveEnd.SCREEN_LOCK)))
        assertFalse(SecurityRules.loosens(base.copy(liveEnd = LiveEnd.SCREEN_LOCK), base))
        // Strict: App lock's clock ends it; the screen lock alone does not.
        assertEquals("app_lock", SecurityRules.liveEndsNow(base, appLockWouldLock = true, screenLocked = false))
        assertNull(SecurityRules.liveEndsNow(base, appLockWouldLock = false, screenLocked = true))
        // Looser: only the phone's own screen lock.
        val loose = base.copy(liveEnd = LiveEnd.SCREEN_LOCK)
        assertNull(SecurityRules.liveEndsNow(loose, appLockWouldLock = true, screenLocked = false))
        assertEquals("screen_lock", SecurityRules.liveEndsNow(loose, appLockWouldLock = true, screenLocked = true))
        // App lock off: neither ends it, as before the setting.
        assertNull(SecurityRules.liveEndsNow(Security(), appLockWouldLock = true, screenLocked = true))
        assertNull(SecurityRules.liveEndsNow(loose.copy(appLock = false), appLockWouldLock = true, screenLocked = true))
        // Stored and read back; anything unreadable is the strict default.
        val stored = SecurityRules.toStored(loose)
        assertEquals(loose, SecurityRules.fromStored { stored[it] })
        assertEquals(LiveEnd.APP_LOCK, SecurityRules.fromStored { if (it == SecurityRules.KEY_LIVE_END) "nonsense" else null }.liveEnd)
        assertTrue(SecurityRules.summary(loose).contains(SecurityRules.LIVE_END_SUMMARY))
        // Both end reasons are ones the PC takes from an app.
        assertTrue("screen_lock" in LiveRules.END_REASONS && "app_lock" in LiveRules.END_REASONS)
        assertTrue(LiveRules.stopBody("screen_lock").contains("\"why\":\"screen_lock\""))
    }

    @Test
    fun `Solve it here blocks screenshots while it shows`() {
        assertTrue(SecurityRules.blockScreenCapture(Security(), handoffShown = true))
        assertFalse(SecurityRules.blockScreenCapture(Security(), handoffShown = false))
    }

    @Test
    fun `the manifest - a tile, and a second share entry for Live, text only`() {
        val manifest = listOf(File("src/main/AndroidManifest.xml"), File("app/src/main/AndroidManifest.xml"),
            File("jarvis-client/app/src/main/AndroidManifest.xml")).first { it.isFile }.readText()
        val tile = manifest.substring(manifest.indexOf("android:name=\".service.LiveTileService\""))
            .substringBefore("</service>")
        assertTrue(tile.contains("android.permission.BIND_QUICK_SETTINGS_TILE"))
        assertTrue(tile.contains("android.service.quicksettings.action.QS_TILE"))
        val alias = manifest.substring(manifest.indexOf("<activity-alias"))
            .substringBefore("</activity-alias>")
        assertTrue(alias.contains("android:name=\".ShareToLive\""))
        assertTrue(alias.contains("android:targetActivity=\".MainActivity\""))
        assertTrue(alias.contains("android.intent.action.SEND"))
        assertTrue(alias.contains("android:mimeType=\"text/plain\""))
        assertFalse("images are not shared into Live", alias.contains("image/"))
        // No new dangerous permission for any of it. (CAMERA is in the manifest
        // for "Scan the code on your PC" - QR pairing, asked for on a tap - and
        // nothing about Live uses it: the Live camera stays off until the 12 GB
        // card passes the photo test.)
        for (p in listOf("BLUETOOTH_CONNECT", "READ_PHONE_STATE", "BLUETOOTH\"")) {
            assertFalse("the manifest asks for $p", manifest.contains("android.permission.$p"))
        }
    }
}
