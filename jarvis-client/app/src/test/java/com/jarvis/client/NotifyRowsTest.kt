package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Limits
import com.jarvis.client.net.NotifyRows
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The PC's Notifications card, on the phone (the parity audit of 2026-10-10,
 * GAP 1-6). Three files have to agree for the card to be real, and this holds
 * all three to each other:
 *
 *  * `jarvis-desktop/src/settings.html` - the desktop card the audit named, its
 *    eight control ids, its note, its three subheadings and its Test button;
 *  * `jarvis-desktop/src/notifications-prefs.js` - the seven rows the desktop's
 *    card really reads and writes (`NOTIF_ROWS`);
 *  * `backend/jarvis_limits.py` - the PC's own table those seven rows live in
 *    (`_NOTIFY_ROWS`), which is what both apps' controls are wired to.
 *
 * A change to any one of them that the phone did not follow fails here, which
 * is the only way this class of drift gets caught: the value rows are not in
 * any settings registry, so nothing else reads them (the audit says so, §6.4).
 *
 * Pure JVM, like every test in this module: the Compose plate and the Android
 * notification are held to their source text, because there is no Android SDK
 * here and CI's Gradle build is the first compiler.
 */
class NotifyRowsTest {

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private val settingsHtml: String =
        repoFile("jarvis-desktop/src/settings.html").readText().replace(Regex("\\s+"), " ")

    private val notifPrefsJs: String = repoFile("jarvis-desktop/src/notifications-prefs.js").readText()

    private val limitsPy: String = repoFile("backend/jarvis_limits.py").readText()

    private val screen: String =
        repoFile("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/PcNotifyPlate.kt").readText()

    private fun obj(json: String): JsonObject = JarvisJson.parseToJsonElement(json).jsonObject

    /** The seven keys the desktop's own card drives, in its own order. */
    private val desktopKeys: List<String> =
        Regex("\\{\\s*key:\\s*\"(notif_[a-z_]+)\"").findAll(notifPrefsJs)
            .map { it.groupValues[1] }.toList()

    /** The PC's table's own rows: the pref name and the title it shows. */
    private val tableRows: List<Pair<String, String>> = run {
        val block = limitsPy.substringAfter("_NOTIFY_ROWS: tuple = (").substringBefore("\n)")
        Regex("""\("([a-z_]+)",\s*(?:"bool"|KIND_TIME),\s*"([^"]+)"""")
            .findAll(block).map { it.groupValues[1] to it.groupValues[2] }.toList()
    }

    // ------------------------------------------------------- the wiring ----

    @Test
    fun `the phone's seven rows are the desktop card's own seven, in its order`() {
        assertEquals(
            "notifications-prefs.js's NOTIF_ROWS was not found, or moved",
            NotifyRows.KEYS.size,
            desktopKeys.size,
        )
        assertEquals(desktopKeys, NotifyRows.KEYS)
    }

    @Test
    fun `the same seven are rows in the PC's own limits table`() {
        assertEquals(7, tableRows.size)
        assertEquals(
            "the phone's keys are the PC's table keys with its own notif_ prefix",
            tableRows.map { "notif_${it.first}" },
            NotifyRows.KEYS,
        )
    }

    @Test
    fun `every row the PC sends a phone says it is the PC's own`() {
        // The PC's own comment (jarvis_limits.py :416-419) says these four
        // titles carry "(on your PC)" so a phone reader can never take them for
        // this phone's notification settings. If that qualifier goes, the phone
        // card starts lying about whose switch it is - so it fails here.
        for ((pref, title) in tableRows) {
            assertTrue("$pref's title lost its \"(on your PC)\": \"$title\"", title.contains("(on your PC)"))
        }
    }

    @Test
    fun `the desktop card the audit named is really there, control for control`() {
        for (id in listOf(
            "notif-alarms", "notif-reminders", "notif-briefing", "notif-handoff",
            "notif-quiet-enabled", "notif-quiet-start", "notif-quiet-end", "notif-send-test",
        )) {
            assertTrue("settings.html has no id=\"$id\"", settingsHtml.contains("id=\"$id\""))
        }
    }

    @Test
    fun `the phone's words are the desktop card's own words`() {
        // The note, with the one word a phone reader needs changed: the desktop
        // says "on this PC" because it is sitting on it.
        assertTrue(
            "the desktop card's own note moved",
            settingsHtml.contains(NotifyRows.NOTE.replace("on your PC", "on this PC")),
        )
        assertTrue(settingsHtml.contains(NotifyRows.SUBHEAD_KINDS))
        assertTrue(settingsHtml.contains(NotifyRows.SUBHEAD_QUIET))
        assertTrue(settingsHtml.contains(NotifyRows.SUBHEAD_TEST))
        assertTrue(settingsHtml.contains(NotifyRows.TEST_LABEL))
        // The date the card was written is the reason the phone has one at all.
        assertTrue(settingsHtml.contains(">Notifications<"))
    }

    // -------------------------------------------------------- the rows ----

    /** The PC's answer, in the shape `GET /api/limits` really sends. */
    private val answer: JsonObject = obj(
        """
        {"limits":[
          {"key":"notif_alarms","title":"Speak up when an alarm rings (on your PC)","kind":"bool",
           "value":true,"words":"on","note":"","pc_only":false,"app":"both","quiet_on":true},
          {"key":"notif_reminders","title":"Chime when a reminder is due (on your PC)","kind":"bool",
           "value":true,"words":"on","note":"","pc_only":false,"app":"both","quiet_on":true},
          {"key":"notif_briefing","title":"Say when the morning briefing is ready (on your PC)","kind":"bool",
           "value":true,"words":"on","note":"","pc_only":false,"app":"both","quiet_on":true},
          {"key":"notif_handoff","title":"Say when a website needs you (on your PC)","kind":"bool",
           "value":true,"words":"on","note":"","pc_only":false,"app":"both","quiet_on":true},
          {"key":"notif_quiet_enabled","title":"Be quiet during quiet hours (on your PC)","kind":"bool",
           "value":false,"words":"off","note":"","pc_only":false,"app":"both","quiet_on":false},
          {"key":"notif_quiet_start","title":"Quiet hours start (on your PC)","kind":"time",
           "value":"22:00","words":"22:00","note":"","pc_only":false,"app":"both","quiet_on":false},
          {"key":"notif_quiet_end","title":"Quiet hours end (on your PC)","kind":"time",
           "value":"07:00","words":"07:00","note":"","pc_only":false,"app":"both","quiet_on":false},
          {"key":"jobs_per_tick","title":"Jobs at once","kind":"int","value":4,
           "words":"4 jobs","note":"","pc_only":true,"app":"desktop","quiet_on":true}
        ]}
        """.trimIndent(),
    )

    @Test
    fun `the card draws exactly the seven rows, in the desktop's order`() {
        val rows = NotifyRows.rows(answer)
        assertEquals(NotifyRows.KEYS, rows.map { it.key })
        // The PC's own words are shown as they arrived: the phone invents no
        // title and drops the "(on your PC)" mark from none of them.
        assertEquals("Speak up when an alarm rings (on your PC)", rows.first().title)
        // The values are the PC's, so the controls start where the PC is.
        assertTrue(rows.first().on)
        assertFalse(rows.first { it.key == "notif_quiet_enabled" }.on)
        assertEquals("22:00", rows.first { it.key == "notif_quiet_start" }.clock)
    }

    @Test
    fun `the four kinds and the quiet group are the same seven, split once`() {
        val rows = NotifyRows.rows(answer)
        assertEquals(listOf("notif_alarms", "notif_reminders", "notif_briefing", "notif_handoff"),
            NotifyRows.kindRows(rows).map { it.key })
        assertEquals(listOf("notif_quiet_enabled", "notif_quiet_start", "notif_quiet_end"),
            NotifyRows.quietRows(rows).map { it.key })
        assertEquals(rows.size, NotifyRows.kindRows(rows).size + NotifyRows.quietRows(rows).size)
    }

    @Test
    fun `a row the PC keeps to itself is never drawn, and a missing one is not invented`() {
        // The PC-only row is in the answer and must not appear...
        assertFalse(NotifyRows.rows(answer).any { it.key == "jobs_per_tick" })
        // ...and an older PC that sends only some of the seven shows only what
        // it sent: no switch is drawn for a value the PC never gave.
        val partial = obj("""{"limits":[{"key":"notif_alarms","title":"Alarms (on your PC)","kind":"bool",
            "value":true,"words":"on","note":"","pc_only":false,"app":"both","quiet_on":true}]}""")
        assertEquals(listOf("notif_alarms"), NotifyRows.rows(partial).map { it.key })
        assertTrue(NotifyRows.rows(obj("""{"limits":[]}""")).isEmpty())
        // The same filter the limits screen uses decides it, so a `pc_only` row
        // cannot reach this card by another route.
        assertEquals(
            Limits.offered(answer).filter { it.key.startsWith("notif_") }.map { it.key },
            NotifyRows.rows(answer).map { it.key },
        )
    }

    @Test
    fun `the quiet group reads its two times whether or not quiet hours are on`() {
        // The PC says the hours decide nothing while quiet hours are off, and
        // the control says so ([Limits.TIME_QUIET_OFF]) - but the VALUES are
        // still the PC's own and still drawn, because a hidden value is how a
        // setting silently changes under the owner.
        val quiet = NotifyRows.rows(answer).first { it.key == "notif_quiet_start" }
        assertFalse(quiet.quietOn)
        assertTrue(quiet.isTime)
        assertEquals("22:00", quiet.clock)
    }

    // --------------------------------------------------------- the plate ----

    @Test
    fun `every control on the card is wired to the same route the desktop uses`() {
        // Read: the one limits read. Write: the one limits write, per row, with
        // the row's own key - never a second path, and never a local copy.
        assertTrue("the card does not read the limits route", screen.contains("JarvisRuntime.limits()"))
        assertTrue("the card does not write through setLimit", screen.contains("JarvisRuntime.setLimit("))
        assertTrue("a control is not wired to its own row's key", screen.contains("change(r.key, value)"))
        // The controls themselves are the limits screen's own, not copies: a
        // change to a switch, a step or the clock cannot reach one and miss the
        // other.
        assertTrue(screen.contains("LimitRow("))
        assertTrue(screen.contains("TimeRowDialog("))
        // The PC's own sentence is what the owner reads back, and it comes from
        // the one place that classifies a limits answer.
        assertTrue(screen.contains("said = JarvisRuntime.setLimit(key, value)"))
        val runtime = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt").readText()
        assertTrue(runtime.contains("suspend fun setLimit("))
        assertTrue("the PC's own sentence is no longer what a change reports",
            runtime.contains("Limits.answer("))
    }

    @Test
    fun `the test control is the desktop's words, and says what it cannot do`() {
        assertEquals("Send test notification", NotifyRows.TEST_LABEL)
        assertTrue(screen.contains("NotifyRows.TEST_LABEL"))
        // It really posts on the phone, and reports what really happened.
        assertTrue(screen.contains("ScheduleNotifier.post("))
        assertTrue(screen.contains("PhoneNotifications.testWords(posted)"))
        // And it says plainly that it cannot raise a Windows notification -
        // which is why the control is the phone's own test and not the PC's.
        assertTrue(NotifyRows.TEST_LINE.contains("Windows"))
        assertTrue(NotifyRows.TEST_LINE.contains("this phone's notifications"))
    }

    @Test
    fun `the card is drawn in Settings, under the row that promises it`() {
        val settings =
            repoFile("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SettingsScreen.kt").readText()
        // The "Notifications from Jarvis" row's own paragraph ends by naming
        // the PC's card; this plate is drawn inside that same row, so the two
        // cannot drift apart into different screens.
        val item = settings.substringAfter("item(key = \"jarvis-notify\")").substringBefore("item(key = \"screen-look\")")
        assertTrue(item.contains("NotificationsFromJarvisSection("))
        assertTrue(item.contains("PcNotifySection(canAct = canAct)"))
        assertTrue("the pointer row's own promise moved",
            repoFile("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/JarvisNotifyPlate.kt")
                .readText().contains("the PC's own Notifications card"))
    }
}
