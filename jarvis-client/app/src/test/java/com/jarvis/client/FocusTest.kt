package com.jarvis.client

import com.jarvis.client.net.Focus
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Mind's "Focus session", read from what the PC REALLY answers.
 *
 * `contract/focus-cases.json` is written by tools/gen_focus_cases.py from the
 * real engine (jarvis_focus.py) - byte for byte the file the desktop builds
 * against. The generator refuses to write it if a made-up program or site
 * name it put "in front" appears anywhere in it.
 */
class FocusTest {

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/focus-cases.json")) {
            "contract/focus-cases.json is missing - run tools/gen_focus_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }

    private fun status(case: String): Focus.View =
        requireNotNull(Focus.parse(doc[case]!!.jsonObject)) { "$case did not parse" }

    private fun answer(case: String): Focus.Reply {
        val o = doc[case]!!.jsonObject
        return Focus.Reply(o["code"]!!.jsonPrimitive.int, o["body"]!!.jsonObject)
    }

    @Test
    fun `the words for the screen are the PC's own`() {
        val w = doc["words"]!!.jsonObject
        assertEquals(w["title"]!!.jsonPrimitive.content, Focus.TITLE)
        assertEquals(w["detail"]!!.jsonPrimitive.content, Focus.DETAIL)
        assertEquals(w["phone_note"]!!.jsonPrimitive.content, Focus.PHONE_NOTE)
        assertEquals(w["missing"]!!.jsonPrimitive.content, Focus.MISSING)
        assertEquals(w["default_minutes"]!!.jsonPrimitive.int, Focus.DEFAULT_MINUTES)
        assertEquals(w["min_minutes"]!!.jsonPrimitive.int, Focus.MIN_MINUTES)
        assertEquals(w["max_minutes"]!!.jsonPrimitive.int, Focus.MAX_MINUTES)
        assertEquals(w["extend_minutes"]!!.jsonPrimitive.int, Focus.EXTEND_MINUTES)
    }

    @Test
    fun `off, with nothing yet, shows no buttons and no report`() {
        val v = status("off_never")
        assertFalse(v.on)
        assertNull(v.report)
        assertTrue(Focus.actionsOf(v).isEmpty())
        assertEquals("No focus session.", v.line)
    }

    @Test
    fun `a running session reads its countdown, its state and its counts`() {
        val s = status("settling")
        assertTrue(s.on && s.deferred)
        assertEquals(30, s.minutes)
        assertEquals(1800L, s.leftS)
        assertEquals("the essay", s.intent)
        val on = status("locked_on_target")
        assertEquals(true, on.onTarget)
        assertFalse(on.drifting)
        val off = status("drifting")
        assertEquals(false, off.onTarget)
        assertTrue(off.drifting)
        assertEquals(1, off.drifts)
        assertTrue(off.line.endsWith("off target."))
        val ex = status("excused")
        assertTrue(ex.excused)
        assertEquals(0, ex.drifts)
        assertTrue(status("snoozed").note.isNotEmpty())
        assertEquals(listOf("pause", "extend", "stop"), Focus.actionsOf(on))
    }

    @Test
    fun `paused, the countdown stands still and Resume replaces Pause`() {
        val p = status("paused")
        assertTrue(p.paused)
        assertEquals(p.leftS, Focus.leftNow(p, 60_000))
        assertEquals(listOf("resume", "extend", "stop"), Focus.actionsOf(p))
        val on = status("locked_on_target")
        assertEquals(on.leftS - 60, Focus.leftNow(on, 60_000))
    }

    @Test
    fun `the report card comes back whole after a session`() {
        val v = status("off_with_report")
        assertNotNull(v.report)
        val r = v.report!!
        assertFalse(v.on)
        assertEquals("Focus session stopped early.", r.title)
        assertTrue(r.lines.first().startsWith("On target: "))
        val done = status("done_clean").report!!
        assertTrue(done.clean && done.completed)
        assertEquals(1, done.streak)
    }

    @Test
    fun `answers are read as the PC's own sentences`() {
        val (ok, said) = Focus.said(answer("start_answer"))
        assertTrue(ok)
        assertTrue(said.startsWith("Focus for 30 minutes"))
        assertTrue(Focus.said(answer("pause_answer")).second.startsWith("Paused with"))
        assertTrue(Focus.said(answer("stop_answer")).second.startsWith("Focus session stopped early."))
        val (ok2, why) = Focus.said(answer("act_without_session"))
        assertFalse(ok2)
        assertEquals("No focus session is running.", why)
    }

    @Test
    fun `bodies - only what the phone may ask, minutes in range`() {
        assertEquals("{\"minutes\":30,\"on\":\"the essay\"}", Focus.startBody(30, "  the   essay "))
        assertNull(Focus.startBody(0, ""))
        assertNull(Focus.startBody(241, ""))
        assertEquals("{\"do\":\"pause\"}", Focus.actBody("pause"))
        assertEquals("{\"do\":\"extend\",\"minutes\":10}", Focus.actBody("extend"))
        assertNull("lock is the desktop's alone", Focus.actBody("lock"))
        assertNull(Focus.actBody("approve"))
        assertEquals(25, Focus.minutesOf(" 25 "))
        assertNull(Focus.minutesOf("abc"))
        assertEquals("24:05", Focus.clock(1445))
        assertEquals("1:02:05", Focus.clock(3725))
        assertFalse("pause is let through on a stale link", "pause" in Focus.HELD_WHEN_STALE)
        assertFalse("stop is let through on a stale link", "stop" in Focus.HELD_WHEN_STALE)
    }
}
