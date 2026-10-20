package com.jarvis.client

import com.jarvis.client.data.AppControl
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
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

    // ------------------------------------------ the screen mechanics (F16) --

    @Test
    fun `a label falls back to contentDescription and then hintText`() {
        val byDescription = AppControl.mask(
            id = null, text = null, cls = "android.widget.ImageButton",
            bounds = listOf(0, 0, 100, 100), password = false, invisible = false,
            hint = "Search",
        )
        assertNotNull(byDescription)
        assertEquals("Search", byDescription!!.text)
        val byHint = AppControl.mask(
            id = null, text = "", cls = "android.widget.EditText",
            bounds = listOf(0, 0, 100, 100), password = false, invisible = false,
            hint = "Search messages",
        )
        assertEquals("Search messages", byHint!!.text)
        assertNull(
            AppControl.mask(
                id = null, text = null, cls = "android.widget.TextView",
                bounds = emptyList(), password = false, invisible = false,
            ),
        )
        val flagged = AppControl.mask(
            id = "x", text = "Play", cls = "android.widget.Button",
            bounds = listOf(0, 0, 10, 10), password = false, invisible = false,
            clickable = true, editable = false, scrollable = false,
        )!!
        assertTrue(flagged.clickable)
        assertFalse(flagged.editable)
    }

    @Test
    fun `password inputType variations are all treated as password fields`() {
        assertFalse(AppControl.passwordInputType(0x00000001)) // TYPE_CLASS_TEXT
        assertTrue(AppControl.passwordInputType(0x00000081))  // text password
        assertTrue(AppControl.passwordInputType(0x00000091))  // text visible password
        assertTrue(AppControl.passwordInputType(0x000000e1))  // web password
        assertTrue(AppControl.passwordInputType(0x00000012))  // number password
        assertTrue(
            AppControl.sensitiveInput(isPassword = false, inputType = 0x91, isDataSensitive = false, sdk = 33),
        )
        assertTrue(
            AppControl.sensitiveInput(isPassword = false, inputType = 0x1, isDataSensitive = true, sdk = 34),
        )
        assertFalse(
            AppControl.sensitiveInput(isPassword = false, inputType = 0x1, isDataSensitive = true, sdk = 33),
        )
    }

    @Test
    fun `the tap ladder climbs at most three parents and stops at a password subtree`() {
        assertEquals(0, AppControl.tapRung(nodeClickable = true, emptyList()))
        assertEquals(2, AppControl.tapRung(false, listOf(false to false, true to false, true to false)))
        assertEquals(-1, AppControl.tapRung(false, listOf(false to false)))
        // A password ancestor makes everything above it unusable too.
        assertEquals(-1, AppControl.tapRung(false, listOf(false to true, false to true, true to false)))
        // Only three parents are looked at.
        assertEquals(-1, AppControl.tapRung(false, List(4) { false to false }))
    }

    @Test
    fun `the type ladder descends only into exactly one editable child`() {
        assertEquals(-1, AppControl.editableChild(emptyList()))
        assertEquals(1, AppControl.editableChild(listOf(false to false, true to false)))
        assertEquals(-1, AppControl.editableChild(listOf(true to false, true to false)))
        assertEquals(-1, AppControl.editableChild(listOf(true to true)))
        assertEquals(0, AppControl.editableChild(listOf(true to false)))
    }

    @Test
    fun `a swipe is clamped inside the target and the central screen band`() {
        val points = AppControl.swipePoints(listOf(0, 0, 1080, 1920), 1080, 1920)
        assertNotNull(points)
        val (startX, endX) = points!!
        assertTrue(startX in 162f..918f)
        assertTrue(endX in 162f..918f)
        assertTrue(startX > endX)
        // An edge strip has no room: refused rather than risking Android's Back gesture.
        assertNull(AppControl.swipePoints(listOf(0, 0, 20, 2000), 1080, 1920))
        assertNull(AppControl.swipePoints(listOf(0, 0, 1080, 1920), 0, 0))
    }

    // --------------------------------------------- the planning round (F16) --

    @Test
    fun `the planning body carries the owner's words and the masked screen`() {
        val snapshot = AppControl.Snapshot("com.android.chrome", "Chrome", listOf(control()))
        val body = AppControl.planBody(listOf(chrome), "  open search  ", snapshot)
        val obj = Json.parseToJsonElement(body).jsonObject
        assertEquals("open search", obj["want"]!!.jsonPrimitive.content)
        assertEquals("com.android.chrome", obj["app"]?.jsonPrimitive?.content ?: obj["snapshot"]!!.jsonObject["app"]!!.jsonPrimitive.content)
        assertTrue(body.contains("\"controls\""))
        // The probe asks nothing and cannot act: no card can come from it.
        val probe = Json.parseToJsonElement(AppControl.planProbeBody()).jsonObject
        assertEquals("", probe["want"]!!.jsonPrimitive.content)
    }

    @Test
    fun `the capability probe reads an older PC from a 404 and a real one from any answer`() {
        assertEquals(AppControl.PlanCapability.UNREACHABLE, AppControl.planCapability(0, null))
        assertEquals(AppControl.PlanCapability.OLDER, AppControl.planCapability(404, null))
        assertEquals(AppControl.PlanCapability.AVAILABLE, AppControl.planCapability(400, null))
        assertEquals(AppControl.PlanCapability.AVAILABLE, AppControl.planCapability(409, null))
        assertEquals(AppControl.PlanCapability.AVAILABLE, AppControl.planCapability(202, null))
    }

    @Test
    fun `a 202 means ONE card waits and the line names the step and local model`() {
        val body = Json.parseToJsonElement(
            "{\"ok\":true,\"run\":\"abc\",\"step\":\"tap \\\"Search\\\"\"," +
                "\"model\":\"qwen3.5:9b\",\"lane\":\"main\"}",
        ).jsonObject
        val reply = AppControl.parsePlan(202, body)
        assertTrue(reply is AppControl.PlanReply.Pending)
        val pending = reply as AppControl.PlanReply.Pending
        assertEquals("abc", pending.runId)
        assertEquals("qwen3.5:9b", pending.model)
        val line = AppControl.planWaitingLine(pending)
        assertTrue(line.contains("approval card"))
        assertTrue(line.contains("qwen3.5:9b"))
        assertTrue(line.contains("Nothing runs until you do"))
    }

    @Test
    fun `a switched-off PC is its own answer, and a refusal is the PC's own words`() {
        val off = Json.parseToJsonElement(
            "{\"ok\":false,\"available\":false,\"error\":\"App control is switched off on this PC.\"}",
        ).jsonObject
        assertTrue(AppControl.parsePlan(409, off) is AppControl.PlanReply.Off)
        val refused = Json.parseToJsonElement(
            "{\"ok\":false,\"pending\":true,\"error\":\"another run is waiting\"}",
        ).jsonObject
        val r = AppControl.parsePlan(409, refused)
        assertTrue(r is AppControl.PlanReply.Refused && r.sentence.contains("another run"))
        val failed = Json.parseToJsonElement(
            "{\"ok\":false,\"error\":\"I could not work out one safe step from that screen.\"}",
        ).jsonObject
        assertTrue(AppControl.parsePlan(422, failed) is AppControl.PlanReply.Failed)
        assertTrue(AppControl.parsePlan(404, null) is AppControl.PlanReply.RouteMissing)
        assertTrue(AppControl.parsePlan(500, null) is AppControl.PlanReply.Unknown)
    }

    @Test
    fun `after one step the only way to another is a fresh ask tap`() {
        assertFalse(AppControl.canAsk(AppControl.PlanCapability.OLDER, optionOn = true, busy = false))
        assertFalse(AppControl.canAsk(AppControl.PlanCapability.AVAILABLE, optionOn = false, busy = false))
        assertFalse(AppControl.canAsk(AppControl.PlanCapability.AVAILABLE, optionOn = true, busy = true))
        assertTrue(AppControl.canAsk(AppControl.PlanCapability.AVAILABLE, optionOn = true, busy = false))
        assertEquals(AppControl.ASK_LABEL, AppControl.askLabel(everPerformed = false))
        assertEquals(AppControl.ASK_AGAIN_LABEL, AppControl.askLabel(everPerformed = true))
        val after = AppControl.afterStep(everPerformed = false, sentence = "Done.")
        assertEquals("Done.", after.sentence)
        assertTrue(after.everPerformed)
        assertFalse(after.busy)
        assertEquals(AppControl.ASK_AGAIN_LABEL, after.label)
    }

    @Test
    fun `the snapshot and step JSON carry the optional flags and the same wire keys`() {
        val flagged = AppControl.Control(
            "id", "Search", "android.widget.EditText", listOf(0, 0, 10, 10),
            clickable = true, editable = true, scrollable = true,
        )
        val snapshot = AppControl.Snapshot("com.android.chrome", "Chrome", listOf(flagged))
        val snapJson = AppControl.snapshotJson(snapshot)
        val row = snapJson["controls"]!!.jsonArray[0].jsonObject
        assertEquals("true", row["clickable"]!!.jsonPrimitive.content)
        assertEquals("true", row["editable"]!!.jsonPrimitive.content)
        assertEquals("true", row["scrollable"]!!.jsonPrimitive.content)
        assertEquals("Search", row["text"]!!.jsonPrimitive.content)
        val stepJson = AppControl.stepJson(AppControl.Step("tap", flagged, null))
        val target = stepJson["target"]!!.jsonObject
        assertEquals("id", target["id"]!!.jsonPrimitive.content)
        assertEquals("true", target["clickable"]!!.jsonPrimitive.content)
    }

    // ----------------------------------- the field-test probe finding (F16) --

    @Test
    fun `an old PC answering not-found to a 404 is never read as ready`() {
        // The field test (2026-10-20): the live, older backend answers a step
        // probe with 404 {"error": "not found"} - that must show "no app control
        // yet", never ROUTE_READY.
        assertEquals(AppControl.ProbeRoute.OLDER, AppControl.probeRoute(404, "not found"))
        assertEquals(AppControl.ProbeRoute.OLDER, AppControl.probeRoute(404, null))
        assertEquals(AppControl.ProbeRoute.OLDER, AppControl.probeRoute(404, ""))
        // A 404 with an unrelated error is still not positive evidence.
        assertEquals(AppControl.ProbeRoute.OLDER, AppControl.probeRoute(404, "unknown run"))
        // 5xx is not positive evidence either: fail closed rather than guess.
        assertEquals(AppControl.ProbeRoute.OLDER, AppControl.probeRoute(500, "boom"))
        assertEquals(AppControl.ProbeRoute.OLDER, AppControl.probeRoute(400, "bad body"))
    }

    @Test
    fun `a real PC's own not-here sentence is the only ready 404`() {
        assertEquals(
            AppControl.ProbeRoute.READY,
            AppControl.probeRoute(404, AppControl.NO_SUCH_RUN_MARKER),
        )
        // A 200/202 answer to the probe is positive evidence too.
        assertEquals(AppControl.ProbeRoute.READY, AppControl.probeRoute(200, null))
        assertEquals(AppControl.ProbeRoute.READY, AppControl.probeRoute(202, null))
        // Nothing answered is "cannot tell", not older and not ready.
        assertEquals(AppControl.ProbeRoute.UNREACHABLE, AppControl.probeRoute(0, null))
    }

    @Test
    fun `the plan probe stays fail-closed on every 404`() {
        // /plan on a real PC answers 400 to the empty-want probe; an older PC
        // answers 404, whatever its body says - that is always OLDER.
        assertEquals(AppControl.PlanCapability.OLDER, AppControl.planCapability(404, null))
        assertEquals(AppControl.PlanCapability.OLDER, AppControl.planCapability(404, Json.parseToJsonElement("{\"error\":\"not found\"}").jsonObject))
        assertEquals(AppControl.PlanCapability.AVAILABLE, AppControl.planCapability(400, null))
        assertEquals(AppControl.PlanCapability.AVAILABLE, AppControl.planCapability(202, null))
        assertEquals(AppControl.PlanCapability.UNREACHABLE, AppControl.planCapability(0, null))
    }

    @Test
    fun `the old probe is still the run route's non-acting probe`() {
        val body = AppControl.probeBody()
        assertTrue(body.contains("\"run\":\"\""))
        assertTrue(body.contains("\"snapshot\""))
        assertFalse(body.contains("\"action\""))
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
