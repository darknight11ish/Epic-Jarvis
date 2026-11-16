package com.jarvis.client.net

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * [DeviceFacts]: the phone's own facts, as the one header value the PC reads
 * to answer "phone specifically" (the owner, 2026-11-15: "be more phone
 * specific in the answers").
 *
 * What is proved here is the *shape*, because the shape is the safety property:
 * this string is put in an HTTP header and then into a system prompt on the PC,
 * so a newline, a `;` or an `=` inside a value would be a way to add a field
 * nobody asked for. [DeviceFacts.line] is pure, so all of it is proved on a
 * plain JVM without a device.
 */
class DeviceFactsTest {

    @Test
    fun `this phone's facts come out in one line`() {
        val value = DeviceFacts.line(
            model = "CPH2419",
            release = "15",
            sdk = 35,
            screen = "1080x2400",
            app = "0.2.4295",
        )
        assertEquals("model=CPH2419;android=15;sdk=35;screen=1080x2400;app=0.2.4295", value)
    }

    @Test
    fun `a value cannot start a new pair`() {
        // A model name with the two characters that build the format, and a
        // quote and a bracket for good measure. None of them survives.
        val value = DeviceFacts.line(
            model = "X;app=evil",
            release = "15",
            sdk = 35,
            screen = "1080x2400",
            app = "0.2.4295",
        )
        val parts = value.split(";")
        assertTrue("every part must be one key=value", parts.all { it.count { c -> c == '=' } == 1 })
        assertFalse("the injected key must not exist", parts.any { it.startsWith("app=evil") })
        assertTrue(value.startsWith("model=Xappevil"))
        assertEquals("app=0.2.4295", parts.last())
    }

    @Test
    fun `a bracket or a newline is dropped, not escaped`() {
        val value = DeviceFacts.line(
            model = "POCO F5\n(Pro)",
            release = "15",
            sdk = 35,
            screen = "1080x2400",
            app = "0.2.4295",
        )
        assertTrue("no newline may reach a header", !value.contains("\n"))
        assertTrue("no bracket may reach a header", !value.contains("(") && !value.contains(")"))
        assertTrue(value.startsWith("model=POCO F5Pro"))
    }

    @Test
    fun `each field is capped so one long name cannot fill the line`() {
        val value = DeviceFacts.line(
            model = "M".repeat(200),
            release = "15",
            sdk = 35,
            screen = "1080x2400",
            app = "0.2.4295",
        )
        val model = value.split(";").first()
        assertEquals("model=" + "M".repeat(28), model)
        assertTrue("the whole value stays under the cap", value.length <= DeviceFacts.MAX_CHARS)
    }

    @Test
    fun `the whole line is capped`() {
        val value = DeviceFacts.line(
            model = "M".repeat(28),
            release = "R".repeat(8),
            sdk = 35,
            screen = "S".repeat(12),
            app = "A".repeat(18),
        )
        assertTrue(value.length <= DeviceFacts.MAX_CHARS)
    }

    @Test
    fun `a missing field is left out rather than sent empty`() {
        val value = DeviceFacts.line(model = null, release = "15", sdk = 0, screen = null, app = null)
        assertEquals("android=15", value)
    }

    @Test
    fun `before startup the request carries nothing at all`() {
        // The object is empty until JarvisApp reads the facts; an empty value is
        // what tells JarvisApi not to send the header, which is exactly what an
        // older build of this app sends.
        assertEquals("", DeviceFacts.headerValue())
    }

    @Test
    fun `the app reads the facts once and sends them from the one builder`() {
        // The wiring itself: one place builds the value, one place puts it on a
        // request. A second sender would be a second truth about this phone.
        val api = File("src/main/java/com/jarvis/client/net/JarvisApi.kt").readText()
        assertTrue(api.contains("const val DEVICE_HEADER = \"X-Jarvis-Device\""))
        assertTrue(
            "authed() must be the one place that sends it",
            api.contains("if (device.isNotEmpty()) header(DEVICE_HEADER, device)"),
        )
        val app = File("src/main/java/com/jarvis/client/JarvisApp.kt").readText()
        assertTrue(
            "the Application must read the facts at startup",
            app.contains("net.DeviceFacts.initialise(this)"),
        )
    }
}
