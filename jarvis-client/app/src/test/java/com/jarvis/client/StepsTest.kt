package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Steps
import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.ZoneOffset

/**
 * `step` events in words - the desktop's `stepText` (`brain.js`), for every
 * phase `jarvis_agent._step_event` can send.
 */
class StepsTest {

    private fun said(json: String): String = Steps.text(JarvisJson.parseToJsonElement(json))

    @Test
    fun everyPhaseSaysWhatTheDesktopSays() {
        assertEquals("asking the model", said("""{"phase":"model","round":1}"""))
        assertEquals("asking the model", said("""{"phase":"model"}"""))
        assertEquals("asking the model again (round 3)", said("""{"phase":"model","round":3}"""))
        assertEquals("using calculator", said("""{"phase":"tool_started","tool":"calculator"}"""))
        assertEquals("calculator done", said("""{"phase":"tool_finished","tool":"calculator","ok":true}"""))
        assertEquals("calculator done", said("""{"phase":"tool_finished","tool":"calculator"}"""))
        assertEquals("calculator failed", said("""{"phase":"tool_finished","tool":"calculator","ok":false}"""))
        assertEquals("send_email not allowed", said("""{"phase":"tool_refused","tool":"send_email"}"""))
        assertEquals("writing the answer", said("""{"phase":"answer"}"""))
    }

    @Test
    fun anUnknownToolIsNamedAsOneJarvisDoesNotHave() {
        assertEquals("using a tool Jarvis does not have", said("""{"phase":"tool_started","tool":"unknown"}"""))
        assertEquals(
            "the model asked for a tool Jarvis does not have",
            said("""{"phase":"tool_refused","tool":"unknown"}"""),
        )
        assertEquals("using a tool", said("""{"phase":"tool_started"}"""))
    }

    @Test
    fun anythingElseIsJustWorking() {
        assertEquals("working", said("""{"phase":"unknown"}"""))
        assertEquals("working", said("""{}"""))
        assertEquals("working", Steps.text(null))
        // A round sent as text is not a round.
        assertEquals("asking the model", said("""{"phase":"model","round":"4"}"""))
    }

    @Test
    fun theListKeepsTheNewestLast() {
        var lines = emptyList<Steps.Line>()
        for (i in 1..5) lines = Steps.append(lines, Steps.Line("t$i", "s$i"), keep = 3)
        assertEquals(listOf("s3", "s4", "s5"), lines.map { it.text })
    }

    @Test
    fun theClockIsHoursMinutesSeconds() {
        assertEquals("01:02:03", Steps.clock(3_723_000L, ZoneOffset.UTC))
    }
}
