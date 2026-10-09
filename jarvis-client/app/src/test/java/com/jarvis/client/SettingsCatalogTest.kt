package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.SettingsCatalog
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The settings switches' one table, held to `src/test/resources/contract/settings-cases.json`
 * that tools/gen_settings_cases.py makes from backend/jarvis_settings_registry.py.
 * The desktop's tests/settings-catalogue.mjs reads the same file, and the desktop page's own
 * 26 rows are generated from the same table - so this is the phone's end of one source.
 *
 * WHAT THIS PROVES, AND WHAT IT DELIBERATELY DOES NOT
 *
 * It proves the generated [SettingsCatalog] is the fixture, row for row: ids, words, span ids,
 * sections, order, which app owns each row's words, and which rows are really settings.
 *
 * It does NOT prove that the phone's Settings screen is generated from this - it is not, and
 * must not be. SettingsScreen.kt's LazyColumn is hand-written, and for the rows the PC owns
 * (the prompt coach above all) the phone keeps READING THE PC: swapping one for a string from
 * here would fail tools/check_parity.py's rule 2, because /api/prompt/coach is classified
 * `ported` and the phone has to still call it. Only the two rows whose words the PHONE owns
 * read their words from here (WatchNotifyPlate.kt, PhoneNotificationsPlate.kt).
 */
class SettingsCatalogTest {

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/settings-cases.json")) {
            "contract/settings-cases.json is missing - run python3 tools/gen_settings_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }

    private val rows: List<JsonObject> get() = doc["rows"]!!.jsonArray.map { it.jsonObject }

    private fun JsonObject.s(k: String): String = this[k]!!.jsonPrimitive.content
    private fun JsonObject.i(k: String): Int = this[k]!!.jsonPrimitive.int
    private fun JsonObject.b(k: String): Boolean = this[k]!!.jsonPrimitive.boolean
    private fun JsonObject.opt(k: String): String? =
        this[k]?.takeIf { it !is JsonNull }?.jsonPrimitive?.content

    // ---------------------------------------------------------------- the list itself

    @Test
    fun `the catalogue is the fixture, row for row`() {
        assertEquals(rows.size, SettingsCatalog.ROWS.size)
        for ((json, row) in rows.zip(SettingsCatalog.ROWS)) {
            val id = row.id
            assertEquals(id, json.s("id"), id)
            assertEquals(id, json.opt("setting"), row.setting)
            assertEquals(id, json.s("owner"), row.owner)
            assertEquals(id, json.s("section"), row.section)
            assertEquals(id, json.i("order"), row.order)
            assertEquals(id, json.s("label"), row.label)
            assertEquals(id, json.s("detail"), row.detail)
            assertEquals(id, json.opt("label_span"), row.labelSpan)
            assertEquals(id, json.opt("detail_span"), row.detailSpan)
            assertEquals(id, json.b("fallback"), row.fallback)
            assertEquals(id, json.b("setting_row"), row.settingRow)
            assertEquals(id, json.opt("phone_key"), row.phoneKey)
        }
    }

    @Test
    fun `there are 26 desktop toggles and 2 phone rows`() {
        // The number this work was briefed with was 19, which is the count of
        // rows spelled exactly `<label class="toggle">` - it misses the seven
        // that also carry a label id. Pinned here so it cannot quietly move.
        assertEquals(26, rows.count { it.s("owner") == "desktop" })
        assertEquals(2, rows.count { it.s("owner") == "phone" })
        assertEquals(28, rows.size)
        assertEquals(28, doc["counts"]!!.jsonObject.i("all"))
        assertEquals(26, doc["counts"]!!.jsonObject.i("desktop"))
        assertEquals(2, doc["counts"]!!.jsonObject.i("phone"))
    }

    @Test
    fun `every order is unique and the desktop rows run 1 to 26`() {
        val desktop = rows.filter { it.s("owner") == "desktop" }.map { it.i("order") }
        assertEquals((1..26).toList(), desktop)
        assertEquals(rows.size, SettingsCatalog.ROWS.map { it.id }.toSet().size)
    }

    // ---------------------------------------------------------------- the phone's own rows

    @Test
    fun `the two rows the phone owns carry the words both plates show`() {
        // These two are the only rows the phone may read words from HERE for.
        // The plates fall back to the same strings if the row is missing, so
        // this is what keeps the fallback and the catalogue from drifting.
        val watch = requireNotNull(SettingsCatalog.row("watch-notify")) {
            "the catalogue has no watch-notify row - run python3 tools/gen_settings_cases.py"
        }
        assertEquals("Show notifications on a compatible watch", watch.label)
        assertEquals(
            "Off by default: every notification (approval cards, timers, reminders, " +
                "\"tell me when\") stays on this phone only.",
            watch.detail,
        )
        val phone = requireNotNull(SettingsCatalog.row("phone-notify")) {
            "the catalogue has no phone-notify row - run python3 tools/gen_settings_cases.py"
        }
        assertEquals("Let your phone read notifications", phone.label)
        assertEquals(
            "Off by default. Jarvis never sees a phone notification unless you turn " +
                "this on AND add at least one app below.",
            phone.detail,
        )
    }

    @Test
    fun `the phone rows name their Settings key and the setting they are`() {
        assertEquals("watch-notify", SettingsCatalog.row("watch-notify")!!.phoneKey)
        assertEquals("phone-notify", SettingsCatalog.row("phone-notify")!!.phoneKey)
        assertEquals("smartwatch_notifications", SettingsCatalog.row("watch-notify")!!.setting)
        assertEquals("phone_notifications", SettingsCatalog.row("phone-notify")!!.setting)
        assertEquals(SettingsCatalog.row("watch-notify"),
            SettingsCatalog.byPhoneKey("watch-notify"))
        assertNull(SettingsCatalog.byPhoneKey("no-such-row"))
        assertNull(SettingsCatalog.row("no-such-row"))
    }

    @Test
    fun `no phone row claims a desktop DOM id`() {
        // The phone's rows have no desktop toggle, so they must not pretend to
        // describe one - a label span or detail span id here would be a lie.
        // Each still names the Kotlin its words were copied from.
        for (row in SettingsCatalog.ROWS.filter { it.owner == "phone" }) {
            assertNull(row.labelSpan)
            assertNull(row.detailSpan)
            assertTrue("${row.id} must name its source", !row.source.isNullOrBlank())
        }
    }

    // ---------------------------------------------------------------- what the PC owns

    @Test
    fun `the rows the PC words are marked, and the phone must keep reading the PC`() {
        // Eleven rows get their visible words from the PC at read time: the
        // words in the catalogue are a FALLBACK for those, never the words the
        // owner ends up reading. This test names them so that a future change
        // that "helpfully" starts rendering one from here is caught, and it
        // pins the count that was mis-reported as twelve.
        val fallback = SettingsCatalog.FALLBACK_ROWS.map { it.id }
        assertEquals(
            listOf(
                "sky-show", "voice-one-moment", "voice-heard-sound", "mn-humor",
                "coach-enabled", "sec-app-lock", "sec-private", "cv-face-switch",
                "ws-enabled", "ws-ask",
            ),
            fallback,
        )
        // prompt-coach is the one to remember: /api/prompt/coach is classified
        // `ported` in tools/check_parity.py, so the phone must keep calling it.
        assertTrue("coach-enabled" in fallback)
    }

    @Test
    fun `exactly one row is not a setting at all`() {
        val notSettings = SettingsCatalog.ROWS.filter { !it.settingRow }.map { it.id }
        assertEquals(listOf("spd-accept"), notSettings)
        assertEquals(27, SettingsCatalog.SETTING_ROWS.size)
        // ...and it is hidden, because it is the spending screen's accept-all
        // control rather than a preference.
        assertTrue(rows.first { it.s("id") == "spd-accept" }.b("hidden"))
    }

    @Test
    fun `the fixture's own counts agree with the catalogue`() {
        val counts = doc["counts"]!!.jsonObject
        assertEquals(SettingsCatalog.ROWS.size, counts.i("all"))
        assertEquals(SettingsCatalog.FALLBACK_ROWS.size, counts.i("fallback"))
        assertEquals(SettingsCatalog.SETTING_ROWS.size, counts.i("setting"))
    }
}
