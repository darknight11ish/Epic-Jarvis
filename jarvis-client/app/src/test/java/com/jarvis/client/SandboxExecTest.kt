package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.DesktopWrite
import com.jarvis.client.net.SandboxExec
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The data and maths sandbox's switch on the phone (LM-1C, 2026-10-18;
 * docs/JARVIS-API.md section 193). It is decided on the PC like every other
 * approval-card switch: OFF by default, ON is one normal approval card, OFF is
 * instant. This phone only reads the PC's answer and shows the PC's own line -
 * it never runs a script and never sees a file or a piece of data.
 *
 * No shared contract fixture: unlike picture mode and the headless browser,
 * every sentence the owner reads here is the PC's `line`/`status` from
 * GET /api/sandbox, so there is no second copy of the state words to hold.
 * What is held here is the READING of that answer - an answer without a real
 * boolean is "not known", never "off" - and what the phone says before and
 * after the switch is pressed.
 */
class SandboxExecTest {

    private fun answer(vararg pairs: Pair<String, Any?>): JsonObject =
        JsonObject(
            pairs.associate { (key, value) ->
                key to when (value) {
                    null -> JsonNull
                    is Boolean -> JsonPrimitive(value)
                    else -> JsonPrimitive(value.toString())
                }
            },
        )

    @Test
    fun `no answer, or one without a real boolean, is not known - never off`() {
        for (body in listOf<JsonObject?>(
            null,
            JsonObject(emptyMap()),
            answer("enabled" to "false"),
            answer("waiting" to true),
        )) {
            val got = SandboxExec.panel(body)
            assertFalse("${body}: available", got.available)
            assertFalse("${body}: enabled", got.enabled)
            assertFalse("${body}: waiting", got.waiting)
            assertFalse("${body}: checked", got.checked)
            assertEquals(SandboxExec.UNREAD, got.line)
        }
    }

    @Test
    fun `OFF, waiting and ON are read the way the PC means them`() {
        val off = SandboxExec.panel(
            answer(
                "enabled" to false,
                "waiting" to false,
                "line" to "Off. The AI model is not offered the data and maths sandbox.",
            ),
        )
        assertTrue(off.available)
        assertFalse(off.enabled)
        assertFalse(off.checked)
        assertTrue(off.line.startsWith("Off."))

        val waiting = SandboxExec.panel(answer("enabled" to false, "waiting" to true, "line" to ""))
        assertFalse(waiting.enabled)
        assertTrue(waiting.waiting)
        assertTrue("a waiting card shows the switch on, so it can be taken back", waiting.checked)
        assertEquals(SandboxExec.WAITING_LINE, waiting.line)

        val on = SandboxExec.panel(
            answer(
                "enabled" to true,
                "waiting" to false,
                "line" to "On. The AI model is offered the data and maths sandbox.",
            ),
        )
        assertTrue(on.enabled)
        assertFalse(on.waiting)
        assertTrue(on.checked)
        assertTrue(on.line.startsWith("On."))
    }

    @Test
    fun `what the last card did is the PC's sentence, passed through unchanged`() {
        val denied = "The card was turned down, so the AI model is still not offered the data sandbox."
        val got = SandboxExec.panel(
            answer(
                "enabled" to false,
                "waiting" to false,
                "line" to denied,
                "status" to denied,
            ),
        )
        assertEquals(denied, got.line)
        assertEquals(denied, got.status)
        assertFalse(got.checked)
    }

    @Test
    fun `an old PC's missing route is named, a wrong token is not`() {
        assertTrue(SandboxExec.missing(ApiError.NotFound))
        assertTrue(SandboxExec.missing(ApiError.NotAvailable))
        assertTrue(SandboxExec.missing(ApiError.Server(501, "")))
        assertFalse(SandboxExec.missing(ApiError.Server(500, "boom")))
        assertFalse(SandboxExec.missing(ApiError.BadToken))
        assertFalse(SandboxExec.missing(ApiError.Unreachable("no address")))
        assertTrue(SandboxExec.MISSING.contains("add-plugin.ps1 -Name sandbox"))
    }

    @Test
    fun `the body carries one boolean and nothing else`() {
        assertEquals("{\"enabled\":true}", SandboxExec.enabledBody(true))
        assertEquals("{\"enabled\":false}", SandboxExec.enabledBody(false))
        assertEquals("/api/sandbox", SandboxExec.PATH)
    }

    @Test
    fun `what the phone says after the switch was pressed`() {
        assertEquals(
            "${SandboxExec.WAITING_LINE} ${com.jarvis.client.net.Approvals.WHERE}",
            SandboxExec.said(true, DesktopWrite.Outcome.Waiting(null)),
        )
        assertEquals(
            SandboxExec.COULD_NOT_TURN_ON + "Your PC is not running.",
            SandboxExec.said(true, DesktopWrite.Outcome.Refused("Your PC is not running.")),
        )
        assertEquals(
            "Not changed. Your PC is not running.",
            SandboxExec.said(false, DesktopWrite.Outcome.Refused("Your PC is not running.")),
        )
        assertEquals(
            "The PC's own sentence.",
            SandboxExec.said(true, DesktopWrite.Outcome.Done("The PC's own sentence.")),
        )
        assertTrue(
            SandboxExec.said(false, DesktopWrite.Outcome.Done(null))
                .startsWith("Off. The AI model is not offered"),
        )
    }
}
