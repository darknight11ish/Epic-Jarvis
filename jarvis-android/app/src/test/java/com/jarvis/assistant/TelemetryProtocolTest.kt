package com.jarvis.assistant

import com.jarvis.assistant.network.DesktopTelemetryEvent
import com.jarvis.assistant.network.InboundEvent
import com.jarvis.assistant.network.JarvisJson
import com.jarvis.assistant.network.OutboundMessage
import com.jarvis.assistant.network.PingMessage
import com.jarvis.assistant.network.PongEvent
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class TelemetryProtocolTest {

    @Test
    fun `desktop_telemetry carries the model route`() {
        val frame = """
            {"type":"desktop_telemetry","cpu_percent":41.7,"gpu_temp_c":78.0,
             "vram_used_mb":5939.2,"vram_total_mb":8192.0,
             "route_lane":"cloud","model":"jarvis-escalate"}
        """.trimIndent()

        val event = JarvisJson.decodeFromString(InboundEvent.serializer(), frame)
            as DesktopTelemetryEvent

        assertEquals("jarvis-escalate", event.model)
        assertTrue(event.isCloudRoute)
        assertEquals(78, event.gpuTempC!!.toInt())
    }

    @Test
    fun `a telemetry frame without a route still decodes`() {
        val frame = """{"type":"desktop_telemetry","cpu_percent":12.0}"""
        val event = JarvisJson.decodeFromString(InboundEvent.serializer(), frame)
            as DesktopTelemetryEvent
        assertNull(event.model)
        assertFalse(event.isCloudRoute)
    }

    @Test
    fun `ping serializes with the timestamp the pong must echo`() {
        val json = JarvisJson.encodeToString(OutboundMessage.serializer(), PingMessage(1234L))
        assertTrue(json, json.contains("\"type\":\"ping\""))
        assertTrue(json, json.contains("\"sent_at_ms\":1234"))
    }

    @Test
    fun `pong round-trips the timestamp`() {
        val event = JarvisJson.decodeFromString(
            InboundEvent.serializer(),
            """{"type":"pong","sent_at_ms":98765}""",
        ) as PongEvent
        assertEquals(98765L, event.sentAtMs)
    }
}
