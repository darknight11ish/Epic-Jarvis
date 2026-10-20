package com.jarvis.client

import com.jarvis.client.data.AppControl
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The phone's half of app control, held to its rules (the owner's decision of
 * 2026-10-19: the accessibility service as an OPTION in this app, with an EMPTY
 * allow-list he fills in by hand, and every step ONE card on the PC).
 *
 * What is NOT tested here, and must never be counted as tested: the Android
 * AccessibilityService itself (reading a real window, performing a gesture,
 * Android's own switch) needs a real phone and the emulator; nothing in this
 * file runs on a device, and a JVM test passing is not a claim that the service
 * works. The compile happens in CI only (no local Android SDK).
 */
class AppControlTest {

    private val settings = AppControl.AppEntry("com.android.settings", "Settings")
    private val chrome = AppControl.AppEntry("com.android.chrome", "Chrome")

    private fun control(
        id: String = "com.android.settings:id/search",
        text: String = "Search",
    ) = AppControl.Control(id, text, "android.widget.TextView", listOf(0, 100, 1080, 200))

    // ------------------------------------------------------- the refusals --

    @Test
    fun `an empty allow-list refuses everything`() {
        assertEquals(
            AppControl.Why.EMPTY,
            AppControl.whyNotAllowed(
                optionOn = true,
                android = AppControl.AndroidState.ON,
                allowed = emptyList(),
                foreground = "com.android.settings",
                stale = false,
                serviceConnected = true,
            ),
        )
    }

    @Test
    fun `the option, Android's switch and a stale link each refuse first`() {
        assertEquals(
            AppControl.Why.OPTION_OFF,
            AppControl.whyNotAllowed(false, AppControl.AndroidState.ON, listOf(settings), "com.android.settings", false, true),
        )
        assertEquals(
            AppControl.Why.ANDROID_OFF,
            AppControl.whyNotAllowed(true, AppControl.AndroidState.OFF, listOf(settings), "com.android.settings", false, true),
        )
        assertEquals(
            AppControl.Why.ANDROID_UNKNOWN,
            AppControl.whyNotAllowed(true, AppControl.AndroidState.CANNOT_READ, listOf(settings), "com.android.settings", false, true),
        )
        assertEquals(
            AppControl.Why.STALE,
            AppControl.whyNotAllowed(true, AppControl.AndroidState.ON, listOf(settings), "com.android.settings", true, true),
        )
        assertEquals(
            AppControl.Why.NO_SERVICE,
            AppControl.whyNotAllowed(true, AppControl.AndroidState.ON, listOf(settings), "com.android.settings", false, false),
        )
    }

    @Test
    fun `an app that is not on the list is refused, and one that is is allowed`() {
        assertEquals(
            AppControl.Why.NOT_LISTED,
            AppControl.whyNotAllowed(true, AppControl.AndroidState.ON, listOf(chrome), "com.android.settings", false, true),
        )
        assertNull(
            AppControl.whyNotAllowed(true, AppControl.AndroidState.ON, listOf(settings), "com.android.settings", false, true),
        )
    }

    @Test
    fun `every refusal is a plain sentence that never names an app`() {
        for (why in AppControl.Why.entries) {
            val said = AppControl.said(why)
            assertTrue(said.endsWith("."))
            assertFalse("$why names a package", said.contains("com."))
        }
    }

    // ------------------------------------------------------- the allow-list --

    @Test
    fun `the allow-list is empty until it is given one, and only valid packages are read`() {
        assertTrue(AppControl.parseStored(null).isEmpty())
        assertTrue(AppControl.parseStored("").isEmpty())
        assertTrue(AppControl.parseStored("not json").isEmpty())
        assertTrue(AppControl.validPackage("com.android.settings"))
        assertFalse(AppControl.validPackage("settings"))
        assertFalse(AppControl.validPackage("com..settings"))
        assertFalse(AppControl.validPackage("com.1settings"))
        assertFalse(AppControl.validPackage("com.android.settings;rm -rf"))
    }

    @Test
    fun `adding one app refuses banks, duplicates and rubbish, and removing one is instant`() {
        var result = AppControl.add(emptyList(), "com.example.chat", "Chat")
        assertNull(result.error)
        assertEquals(1, result.entries.size)
        assertEquals("com.example.chat", result.entries[0].packageName)
        // The app's own name is used; the package name is a fallback only.
        assertEquals("Chat", result.entries[0].label)

        assertNotNull(AppControl.add(result.entries, "com.example.chat", "Chat").error)
        assertNotNull(AppControl.add(result.entries, "nonsense", "X").error)
        assertNotNull(
            AppControl.add(result.entries, "com.example.bank", "Bank", refusedApp = AppControl.REFUSE_BANKING).error,
        )
        assertEquals(
            emptyList<AppControl.AppEntry>(),
            AppControl.remove(result.entries, "com.example.chat"),
        )
    }

    @Test
    fun `the list is stored as JSON and read back exactly, sorted, with no secrets`() {
        val entries = listOf(
            AppControl.AppEntry("com.z.app", "Zed"),
            AppControl.AppEntry("com.a.app", "Ay"),
        )
        val raw = AppControl.storeJson(entries)
        val back = AppControl.parseStored(raw)
        assertEquals(listOf("com.a.app", "com.z.app"), back.map { it.packageName })
        assertEquals("Ay", back[0].label)
        assertEquals(raw, AppControl.storeJson(back))
        assertFalse(raw.contains("password"))
    }

    @Test
    fun `a malformed stored row never widens the list`() {
        val raw = """{"version":1,"apps":[{"package":"com.good.app","label":"Good"},"""
        assertTrue(AppControl.parseStored(raw).isEmpty())
        val wrongVersion = """{"version":99,"apps":[{"package":"com.good.app","label":"Good"}]}"""
        assertTrue(AppControl.parseStored(wrongVersion).isEmpty())
        val badRows = """
            {"version":1,"apps":[
              {"package":"com.good.app","label":"Good"},
              {"package":"com.2bad.app","label":"Bad"},
              {"label":"No package"}
            ]}
        """.trimIndent()
        assertEquals(listOf("com.good.app"), AppControl.parseStored(badRows).map { it.packageName })
    }

    // --------------------------------------------------------- the snapshot --

    @Test
    fun `a password field and an invisible control never enter a snapshot`() {
        assertNull(AppControl.mask("id", "Password", "android.widget.EditText", listOf(0, 0, 1, 1), password = true, invisible = false))
        assertNull(AppControl.mask("id", "Hidden", "android.widget.Button", listOf(0, 0, 1, 1), password = false, invisible = true))
        assertNull(AppControl.mask("", "", "", listOf(0, 0, 1, 1), password = false, invisible = false))
        // A password field is skipped BEFORE its text is looked at, so the text
        // argument here would not matter - and there is no branch that keeps it.
        assertNull(AppControl.mask(null, null, null, emptyList(), password = true, invisible = false))
    }

    @Test
    fun `long words are truncated and a control keeps its own id and bounds`() {
        val long = "x".repeat(AppControl.MAX_CONTROL_TEXT + 40)
        val masked = AppControl.mask("com.app:id/x", long, "android.widget.TextView", listOf(1, 2, 3, 4, 5, 6), false, false)
        assertNotNull(masked)
        assertEquals(AppControl.MAX_CONTROL_TEXT, masked!!.text.length)
        assertEquals("com.app:id/x", masked.id)
        assertEquals(listOf(1, 2, 3, 4), masked.bounds)
        assertEquals("android.widget.TextView", masked.cls)
    }

    @Test
    fun `the snapshot sent to the PC is only app, title and masked controls`() {
        val snapshot = AppControl.Snapshot(
            app = "com.android.settings",
            title = "Settings",
            controls = listOf(control()),
        )
        val json = AppControl.snapshotJson(snapshot).toString()
        assertTrue(json.contains("\"app\":\"com.android.settings\""))
        assertTrue(json.contains("\"title\":\"Settings\""))
        assertTrue(json.contains("com.android.settings:id/search"))
        assertFalse(json.contains("password"))
        assertFalse(json.contains("image"))
    }

    // ------------------------------------------------------------- the step --

    @Test
    fun `only the five actions exist, and a type step carries its text`() {
        assertEquals(listOf("tap", "swipe", "type", "back", "home"), AppControl.ACTIONS)
        val typed = AppControl.Step("type", control(), "hello")
        val json = AppControl.stepJson(typed)
        assertEquals("type", json["action"]?.jsonPrimitive?.content)
        // The step's OWN text - the target's own label is a different "text".
        assertEquals("hello", json["text"]?.jsonPrimitive?.content)
        val tap = AppControl.Step("tap", control())
        assertNull("a tap step carries no typed words", AppControl.stepJson(tap)["text"])
        // Typed text is capped on the phone too; the PC refuses anything longer.
        val tooLong = AppControl.Step("type", control(), "y".repeat(AppControl.MAX_TEXT + 20))
        assertEquals(AppControl.MAX_TEXT, AppControl.stepJson(tooLong)["text"]?.jsonPrimitive?.content?.length)
    }

    @Test
    fun `the approved step must be the one asked for`() {
        val planned = AppControl.Step("tap", control())
        assertTrue(AppControl.matches(planned, AppControl.Step("tap", control())))
        assertFalse(AppControl.matches(planned, AppControl.Step("tap", control(text = "Other"))))
        assertFalse(AppControl.matches(planned, AppControl.Step("type", control(), "hello")))
        assertFalse(AppControl.matches(planned, AppControl.Step("tap", control(id = "com.other:id/x"))))
        // Back and home carry no target, and a target smuggled in is not the plan.
        val back = AppControl.Step("back", null)
        assertTrue(AppControl.matches(back, AppControl.Step("back", null)))
        assertFalse(AppControl.matches(back, AppControl.Step("back", control())))
        // A type step's words are part of what the owner approved.
        val plannedType = AppControl.Step("type", control(), "hello")
        assertFalse(AppControl.matches(plannedType, AppControl.Step("type", control(), "goodbye")))
    }

    @Test
    fun `the run body carries the allow-list, the app, the ONE step and the masked snapshot`() {
        val body = AppControl.runBody(listOf(settings), "com.android.settings", "Settings", AppControl.Step("tap", control()), AppControl.Snapshot("com.android.settings", "Settings", listOf(control())))
        assertTrue(body.contains("\"allowed\":[\"com.android.settings\"]"))
        assertTrue(body.contains("\"app\":\"com.android.settings\""))
        assertTrue(body.contains("\"app_name\":\"Settings\""))
        assertTrue(body.contains("\"step\""))
        assertTrue(body.contains("\"snapshot\""))
        assertFalse(body.contains("password"))
    }

    @Test
    fun `a stop and a result carry only the run id and their own word`() {
        assertTrue(AppControl.stopBody("run-1").contains("\"stop\":true"))
        assertTrue(AppControl.stopBody("run-1").contains("\"run\":\"run-1\""))
        assertTrue(AppControl.resultBody("run-1", failed = false).contains("\"result\":\"done\""))
        assertTrue(AppControl.resultBody("run-1", failed = true).contains("\"result\":\"failed\""))
    }

    // ------------------------------------------------------------ the PC's answers --

    @Test
    fun `the PC's run answers are read, and a route that is not there is not a card`() {
        val pending = AppControl.parseRun(
            202,
            com.jarvis.client.net.JarvisJson.parseToJsonElement(
                "{\"ok\":true,\"run\":\"abc\",\"status\":\"pending\"}",
            ) as kotlinx.serialization.json.JsonObject,
        )
        assertTrue(pending is AppControl.RunReply.Pending)
        assertEquals("abc", (pending as AppControl.RunReply.Pending).runId)

        val off = AppControl.parseRun(
            409,
            com.jarvis.client.net.JarvisJson.parseToJsonElement(
                "{\"ok\":false,\"available\":false,\"error\":\"App control is switched off on this PC.\"}",
            ) as kotlinx.serialization.json.JsonObject,
        )
        assertTrue(off is AppControl.RunReply.Off)

        val refused = AppControl.parseRun(
            409,
            com.jarvis.client.net.JarvisJson.parseToJsonElement(
                "{\"ok\":false,\"error\":\"That app is not on the list.\"}",
            ) as kotlinx.serialization.json.JsonObject,
        )
        assertTrue(refused is AppControl.RunReply.Refused)

        assertEquals(
            AppControl.RunReply.RouteMissing,
            AppControl.parseRun(
                404,
                com.jarvis.client.net.JarvisJson.parseToJsonElement(
                    "{\"error\":\"no such route\"}",
                ) as kotlinx.serialization.json.JsonObject,
            ),
        )
    }

    @Test
    fun `the PC's step answers are read, including the ONE returned step`() {
        fun body(text: String) = com.jarvis.client.net.JarvisJson.parseToJsonElement(text) as kotlinx.serialization.json.JsonObject

        assertEquals(AppControl.StepReply.Pending, AppControl.parseStep(202, body("{\"ok\":true,\"status\":\"pending\"}")))
        val step = AppControl.parseStep(
            200,
            body(
                "{\"ok\":true,\"status\":\"step\",\"step\":{\"action\":\"tap\"," +
                    "\"target\":{\"id\":\"com.app:id/x\",\"text\":\"Go\",\"class\":\"android.widget.Button\"," +
                    "\"bounds\":[0,1,2,3]}}}",
            ),
        )
        assertTrue(step is AppControl.StepReply.Step)
        val returned = (step as AppControl.StepReply.Step).step
        assertEquals("tap", returned.action)
        assertEquals("com.app:id/x", returned.target?.id)
        assertEquals(listOf(0, 1, 2, 3), returned.target?.bounds)

        assertTrue(AppControl.parseStep(200, body("{\"ok\":false,\"status\":\"stopped\",\"error\":\"The screen changed.\"}")) is AppControl.StepReply.Stopped)
        assertTrue(AppControl.parseStep(200, body("{\"ok\":false,\"status\":\"denied\"}")) is AppControl.StepReply.Ended)
        assertTrue(AppControl.parseStep(409, body("{\"ok\":false,\"status\":\"delivered\"}")) is AppControl.StepReply.Delivered)
        assertEquals(AppControl.StepReply.RouteMissing, AppControl.parseStep(404, body("{\"error\":\"no such route\"}")))
        // The 404 an older PC gives and the 404 of an unknown run are told
        // apart by the caller's probe word, never by guessing here.
        assertTrue(AppControl.parseStep(200, body("{\"status\":\"unexpected\"}")) is AppControl.StepReply.Failed)
    }

    // -------------------------------------------- Android's own switch, read-only --

    @Test
    fun `Android's accessibility list is read by component, and unreadable is not off`() {
        val component = AppControl.component("com.jarvis.client", "com.jarvis.client.service.JarvisAccessibilityService")
        assertEquals(
            AppControl.AndroidState.ON,
            AppControl.androidState(
                "com.example.other/com.example.other.Thing:com.jarvis.client/.service.JarvisAccessibilityService",
                component,
            ),
        )
        assertEquals(
            AppControl.AndroidState.ON,
            AppControl.androidState(
                "com.jarvis.client/com.jarvis.client.service.JarvisAccessibilityService",
                component,
            ),
        )
        assertEquals(AppControl.AndroidState.OFF, AppControl.androidState("com.example.other/com.example.other.Thing", component))
        assertEquals(AppControl.AndroidState.OFF, AppControl.androidState("", component))
        assertEquals(AppControl.AndroidState.CANNOT_READ, AppControl.androidState(null, component))
    }

    @Test
    fun `the probe asks about a run the PC cannot have, so it can raise no card`() {
        val body = AppControl.probeBody()
        assertTrue(body.contains("\"run\":\"\""))
        assertTrue(body.contains("\"snapshot\""))
        // A probe is not a step: it has no action and no text to send.
        assertFalse(body.contains("\"action\""))
        assertFalse(body.contains("\"text\""))
    }
}
