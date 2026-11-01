package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.AsksFirst
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PendingItem
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Mind's "What asks first" (the owner's decisions of 2026-09-26), read from
 * what the PC REALLY answers.
 *
 * `contract/asks-first-cases.json` is the real `GET /api/asks_first` answer
 * (jarvis_asks_first.view()), written by tools/gen_asks_first_cases.py -
 * byte for byte the file the desktop builds against.
 */
class AsksFirstTest {

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/asks-first-cases.json")) {
            "contract/asks-first-cases.json is missing - run tools/gen_asks_first_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }
    private val cases = doc["cases"]!!.jsonObject
    private val words = doc["words"]!!.jsonObject

    private fun view(case: String): AsksFirst.View =
        requireNotNull(AsksFirst.parse(cases[case]!!.jsonObject)) { "$case did not parse" }

    private fun word(key: String) = words[key]!!.jsonPrimitive.content

    private fun row(v: AsksFirst.View, id: String) = v.groups.flatMap { it.rows }.first { it.id == id }

    @Test
    fun `the words are the PC's own`() {
        assertEquals(word("title"), AsksFirst.TITLE)
        assertEquals(word("detail"), AsksFirst.DETAIL)
        assertEquals(word("missing"), AsksFirst.MISSING)
        assertEquals(word("switch_label"), AsksFirst.SWITCH_LABEL)
        assertEquals(word("waiting"), AsksFirst.WAITING)
        assertEquals(word("phone_loosen"), AsksFirst.PHONE_LOOSEN)
        assertEquals(word("lights_label"), AsksFirst.LIGHTS_LABEL)
        assertEquals(word("lights_detail"), AsksFirst.LIGHTS_DETAIL)
        assertEquals(word("lights_waiting"), AsksFirst.LIGHTS_WAITING)
        assertEquals(doc["switchable"]!!.jsonArray.map { it.jsonPrimitive.content }, AsksFirst.SWITCHABLE)
    }

    @Test
    fun `every real view is read, every group and row in the PC's order`() {
        for (name in cases.keys) {
            val v = view(name)
            val raw = cases[name]!!.jsonObject["groups"]!!.jsonArray
            assertEquals(name, raw.map { it.jsonObject["title"]!!.jsonPrimitive.content }, v.groups.map { it.title })
            assertEquals(
                name,
                raw.flatMap { g -> g.jsonObject["rows"]!!.jsonArray.map { it.jsonObject["id"]!!.jsonPrimitive.content } },
                v.groups.flatMap { g -> g.rows.map { it.id } },
            )
            assertTrue(name, v.groups.flatMap { it.rows }.filter { it.switch != null }.all { it.action in AsksFirst.SWITCHABLE })
        }
    }

    @Test
    fun `the phone makes things stricter and never looser`() {
        val phone = view("phone_shipped")
        assertFalse(phone.canLoosen)
        val cal = row(phone, "calendar_read")
        val sw = requireNotNull(AsksFirst.switchView(cal, phone))
        assertFalse("shipped: it goes ahead without asking", sw.checked)
        assertTrue("turning it ON (stricter) is offered", sw.enabled)
        val strict = view("pc_stricter_lights_on")
        val cal2 = requireNotNull(AsksFirst.switchView(row(strict, "calendar_read"), strict))
        assertTrue(cal2.checked)
        assertFalse("once it asks, the phone cannot turn it off", cal2.enabled)
        assertTrue(AsksFirst.stricterBody("calendar_read")!!.contains("\"ask\":true"))
        assertNull("nothing off the list is ever sent", AsksFirst.stricterBody("send_email"))
        assertNull("sending email has no switch", AsksFirst.switchView(row(phone, "send_email"), phone))
        val note = row(view("phone_cards_waiting"), "calendar_read").note
        assertTrue("the row says where to loosen it", note.contains(AsksFirst.PHONE_LOOSEN))
    }

    @Test
    fun `a waiting card and the lights setting`() {
        val v = view("phone_cards_waiting")
        val sw = requireNotNull(AsksFirst.switchView(row(v, "calendar_read"), v))
        assertTrue(sw.checked)
        assertEquals(listOf(AsksFirst.WAITING), sw.lines)
        val lights = AsksFirst.lightsView(v.lights, live = true)
        assertTrue(lights.checked)
        assertEquals(listOf(AsksFirst.LIGHTS_WAITING), lights.lines)
        val off = AsksFirst.lightsView(view("pc_shipped").lights, live = false)
        assertFalse("ON is held on a stale link", off.canChange)
        val on = AsksFirst.lightsView(view("pc_stricter_lights_on").lights, live = false)
        assertTrue("OFF is never held", on.canChange)
        assertEquals("{\"enabled\":false}", AsksFirst.lightsBody(false))
    }

    @Test
    fun `a loosening card cannot be approved on the phone`() {
        val card = PendingItem(id = "r1", action = AsksFirst.LOOSEN_ACTION)
        assertTrue(card.pcOnly)
        assertFalse(PendingItem(id = "r2", action = "send_email").pcOnly)
        assertTrue(AsksFirst.APPROVE_ON_PC.contains("Deny still works"))
    }

    @Test
    fun `Lockdown - the PC's words, on from the phone, never off`() {
        assertEquals(word("lockdown_action"), AsksFirst.LOCKDOWN_ACTION)
        assertEquals(word("lockdown_label"), AsksFirst.LOCKDOWN_LABEL)
        assertEquals(word("lockdown_detail"), AsksFirst.LOCKDOWN_DETAIL)
        assertEquals(word("lockdown_on_says"), AsksFirst.LOCKDOWN_ON_SAYS)
        assertEquals(word("lockdown_off_says"), AsksFirst.LOCKDOWN_OFF_SAYS)
        assertEquals(word("lockdown_on_label"), AsksFirst.LOCKDOWN_ON_LABEL)
        assertEquals(word("lockdown_pc_only"), AsksFirst.LOCKDOWN_PC_ONLY)
        assertEquals(word("lockdown_waiting"), AsksFirst.LOCKDOWN_WAITING)
        val off = AsksFirst.lockdownView(view("phone_shipped").lockdown)
        assertTrue(off.show)
        assertFalse(off.on)
        assertTrue("off: the phone may turn it on", off.canTurnOn)
        assertEquals(listOf(AsksFirst.LOCKDOWN_OFF_SAYS), off.lines)
        val on = AsksFirst.lockdownView(view("phone_lockdown_on").lockdown)
        assertTrue(on.on)
        assertFalse("on: the phone can never turn it off", on.canTurnOn)
        assertEquals(AsksFirst.LOCKDOWN_ON_SAYS, on.lines.first())
        assertTrue(on.lines.contains(AsksFirst.LOCKDOWN_PC_ONLY))
        val waiting = AsksFirst.lockdownView(view("pc_lockdown_off_card_waiting").lockdown)
        assertTrue(waiting.lines.contains(AsksFirst.LOCKDOWN_WAITING))
        assertEquals("{\"action\":\"lockdown\",\"ask\":true}", AsksFirst.lockdownBody())
        // While it is on, a read asks first and the phone's switch cannot loosen it.
        val cal = row(view("phone_lockdown_on"), "calendar_read")
        assertEquals("Asks you first, every time", cal.says)
        assertEquals(AsksFirst.lockdownView(null), AsksFirst.LockdownView(false, false, emptyList(), false))
        assertEquals(true, AsksFirst.lockdownFrom(buildJsonObject { put("on", true) }))
        assertEquals(false, AsksFirst.lockdownFrom(buildJsonObject { put("on", false) }))
        assertNull(AsksFirst.lockdownFrom(null))
        assertNull(AsksFirst.lockdownFrom(buildJsonObject { put("on", "yes") }))
    }


    @Test
    fun `the switchable tools are read-only on the phone, in the PC's own groups and labels`() {
        val v = view("phone_shipped")
        val t = requireNotNull(v.tools) { "the phone's real view gained no tools payload" }
        val raw = cases["phone_shipped"]!!.jsonObject["tools"]!!.jsonObject
        assertEquals(word("tools_label"), t.label)
        assertEquals(word("tools_detail"), t.detail)
        assertEquals(word("tools_pc_only"), AsksFirst.TOOLS_PC_ONLY)
        assertFalse("the phone cannot enable tools - the PC is where they change", t.canEnable)
        val rawItems = raw["items"]!!.jsonArray.map { it.jsonObject }
        val rawIds = rawItems.map { it["id"]!!.jsonPrimitive.content }
        assertEquals("21 one-tool switches", 21, rawIds.size)
        assertEquals("every tool, in the PC's own order",
            rawIds, t.groups.flatMap { g -> g.rows.map { it.id } })
        assertEquals("the PC's four group titles, in order",
            raw["groups"]!!.jsonArray.map { it.jsonObject["title"]!!.jsonPrimitive.content },
            t.groups.map { it.title })
        assertEquals("a label is the backend's human label, not the id",
            rawItems.first()["title"]!!.jsonPrimitive.content,
            t.groups.first().rows.first().title)
        val first = t.groups.first().rows.first()
        assertTrue(AsksFirst.toolState(first) == AsksFirst.TOOLS_OFF ||
            AsksFirst.toolState(first) == AsksFirst.TOOLS_ON ||
            AsksFirst.toolState(first) == AsksFirst.WAITING)
        // The same payload from the PC says the PC may change them.
        val pc = requireNotNull(view("pc_shipped").tools)
        assertTrue("from the PC the same payload is switchable", pc.canEnable)
    }

    @Test
    fun `the vault organizer is its own row and the TOML-only note says what is left out`() {
        val t = requireNotNull(view("phone_shipped").tools)
        val vault = requireNotNull(t.vault) { "the vault organizer's own switch is missing" }
        assertEquals("Organize an Obsidian vault", vault.title)
        assertTrue("its own words explain what it does", vault.what.contains("tidy-up"))
        assertTrue("its state is in words", AsksFirst.vaultState(vault).isNotEmpty())
        val no = requireNotNull(t.notOffered) { "the not-offered list is missing" }
        assertEquals("16 tools stay a settings-file choice", 16, no.labels.size)
        assertTrue("the note says where they really live", no.why.contains("jarvis-framework.toml"))
        assertTrue("it names the raw ones it never offers", no.why.contains("shell"))
        assertEquals("the phone shows the PC's own sentence",
            word("tools_pc_only"), AsksFirst.TOOLS_PC_ONLY)
    }

    @Test
    fun `the phone's plate draws the tools read-only and writes nothing`() {
        val plate = java.io.File(
            "src/main/java/com/jarvis/client/ui/screens/AsksFirstPlate.kt"
        ).readText()
        assertTrue("no tool section drawn", plate.contains("v.tools?.let"))
        assertTrue("no plain PC-only sentence", plate.contains("AsksFirst.TOOLS_PC_ONLY"))
        assertTrue("no vault organizer row", plate.contains("t.vault?.let"))
        assertTrue("no TOML-only note", plate.contains("AsksFirst.TOOLS_TOML_ONLY_TITLE"))
        val block = plate.substringAfter("v.tools?.let").substringBefore("(if (busy)")
        assertFalse("a switch was drawn inside the read-only tools block", block.contains("SwitchRow("))
        for (banned in listOf("JarvisRuntime.makeAskFirst", "JarvisRuntime.setLightsWithoutCard",
                              "JarvisRuntime.enableTool", "JarvisRuntime.setTool")) {
            assertFalse("the tools block must not write: $banned", block.contains(banned))
        }
    }

    @Test
    fun `an older PC says so`() {
        assertNull(AsksFirst.parse(buildJsonObject { put("available", false) }))
        assertTrue(AsksFirst.missing(ApiError.NotFound))
        assertTrue(AsksFirst.missing(ApiError.NotAvailable))
    }
}
