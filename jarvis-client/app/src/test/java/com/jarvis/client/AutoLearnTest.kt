package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Approvals
import com.jarvis.client.net.AutoLearn
import com.jarvis.client.net.AutoLearn.Switch
import com.jarvis.client.net.AutoLearn.Which
import com.jarvis.client.net.DesktopWrite
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.time.LocalDate
import java.time.ZoneOffset

/**
 * Automatic learning on the phone (docs/JARVIS-API.md section 19, the
 * contract in the 2026-09-24 build spec, sections 1, 4 and 5): the two
 * switches and their waiting state, the "Saved automatically" list with
 * Forget and paging, and the `memory_saved` line.
 */
class AutoLearnTest {

    private fun obj(json: String): JsonObject = JarvisJson.parseToJsonElement(json).jsonObject

    // ------------------------------------------------------------ words ---

    @Test
    fun theSwitchesUseTheSpecsWordsExactly() {
        assertEquals("Learn automatically", Which.AUTO.title)
        assertEquals(
            "Jarvis saves facts about you and your projects from what you type or say to it - never " +
                "from web pages, emails, documents or notes. You can forget any of them here.",
            Which.AUTO.under,
        )
        assertEquals("Also remember sensitive topics automatically", Which.SENSITIVE.title)
        assertEquals(
            "Health, money, passwords and account details, and private details about other people. " +
                "When this is off, Jarvis asks you first.",
            Which.SENSITIVE.under,
        )
        assertEquals("Saved automatically", AutoLearn.TITLE)
        assertEquals("said aloud", AutoLearn.VOICE_MARK)
        assertEquals("Jarvis remembered 2 things", AutoLearn.rememberedLine(2))
        assertEquals("Jarvis remembered 1 thing", AutoLearn.rememberedLine(1))
        assertNull(AutoLearn.rememberedLine(0))
        assertNull(AutoLearn.rememberedLine(-3))
        for (w in Which.entries) {
            assertTrue(AutoLearn.waitingLine(w), AutoLearn.waitingLine(w).startsWith("Waiting for your approval"))
            assertTrue(AutoLearn.waitingLine(w).endsWith(Approvals.WHERE))
        }
    }

    @Test
    fun theRoutesAndCardActionsAreTheContracts() {
        assertEquals("/api/memory/learning/auto", Which.AUTO.path)
        assertEquals("/api/memory/learning/sensitive", Which.SENSITIVE.path)
        assertEquals("learning_auto_enable", Which.AUTO.action)
        assertEquals("learning_sensitive_enable", Which.SENSITIVE.action)
        assertEquals("/api/memory/learning", AutoLearn.SETTINGS_PATH)
        assertEquals("/api/memory/forget", AutoLearn.FORGET_PATH)
        assertEquals("memory_saved", AutoLearn.EVENT)
        assertEquals("{\"enabled\":true}", AutoLearn.enabledBody(true))
        assertEquals("{\"enabled\":false}", AutoLearn.enabledBody(false))
        assertEquals("{\"id\":42}", AutoLearn.forgetBody(42))
    }

    // ----------------------------------------------------------- status ---

    @Test
    fun theSettingsAreReadFieldByField() {
        val s = AutoLearn.status(
            obj(
                """{"auto":true,"auto_sensitive":false,"auto_waiting":false,"sensitive_waiting":true,
                   "auto_last":null,"sensitive_last":{"outcome":"denied","why":"","at":1727180000.5}}""",
            ),
        )
        assertEquals(true, s.auto)
        assertEquals(false, s.autoSensitive)
        assertFalse(s.autoWaiting)
        assertTrue(s.sensitiveWaiting)
        assertNull(s.autoLast)
        assertEquals(AutoLearn.Last("denied", null), s.sensitiveLast)
    }

    @Test
    fun aMissingOrDamagedSwitchIsUnknownNeverOn() {
        val s = AutoLearn.status(obj("""{"auto":"true","auto_sensitive":1,"auto_waiting":"yes"}"""))
        assertNull(s.auto)
        assertNull(s.autoSensitive)
        assertFalse(s.autoWaiting)
        assertEquals(Switch.UNKNOWN, AutoLearn.switchState(s, Which.AUTO, cardInQueue = false))
        assertEquals(Switch.UNKNOWN, AutoLearn.switchState(null, Which.SENSITIVE, cardInQueue = false))
    }

    @Test
    fun onIsShownOnlyWhenThePcSaysOn() {
        val off = AutoLearn.Status(auto = false, autoSensitive = false)
        assertEquals(Switch.OFF, AutoLearn.switchState(off, Which.AUTO, cardInQueue = false))
        // A card in the queue is waiting, not on.
        assertEquals(Switch.WAITING, AutoLearn.switchState(off, Which.AUTO, cardInQueue = true))
        // The PC's own flag, before this phone's queue has caught up.
        val pcWaits = AutoLearn.Status(auto = false, autoSensitive = false, sensitiveWaiting = true)
        assertEquals(Switch.WAITING, AutoLearn.switchState(pcWaits, Which.SENSITIVE, cardInQueue = false))
        assertEquals(Switch.OFF, AutoLearn.switchState(pcWaits, Which.AUTO, cardInQueue = false))
        val on = AutoLearn.Status(auto = true, autoSensitive = true)
        assertEquals(Switch.ON, AutoLearn.switchState(on, Which.AUTO, cardInQueue = false))
        assertEquals(Switch.ON, AutoLearn.switchState(on, Which.SENSITIVE, cardInQueue = false))
    }

    @Test
    fun aCardRaisedOnTheDesktopIsFoundInTheQueueByItsAction() {
        // The queue holds whatever the PC is asking - a card raised from the
        // desktop's Brain is there under the same action as one raised here.
        val queue = listOf(null, "switch_model", "learning_auto_enable")
        assertTrue(AutoLearn.cardWaiting(queue, Which.AUTO))
        assertFalse(AutoLearn.cardWaiting(queue, Which.SENSITIVE))
        assertTrue(AutoLearn.cardWaiting(listOf("learning_sensitive_enable"), Which.SENSITIVE))
        // The background learning card is a different switch.
        assertFalse(AutoLearn.cardWaiting(listOf("learning_enable"), Which.AUTO))
        assertFalse(AutoLearn.cardWaiting(emptyList(), Which.AUTO))
    }

    @Test
    fun theListsAnswerCarriesTheSwitchesToo() {
        val s = AutoLearn.statusFromList(obj("""{"facts":[],"auto":true,"auto_sensitive":false}"""))
        assertEquals(true, s.auto)
        assertEquals(false, s.autoSensitive)
        assertFalse(s.autoWaiting)
    }

    // ------------------------------------------------------------ lines ---

    @Test
    fun theLinesSayWhatIsTrue() {
        assertTrue(AutoLearn.stateLine(Which.AUTO, Switch.ON, true, true).startsWith("On."))
        assertFalse(AutoLearn.stateLine(Which.AUTO, Switch.ON, true, true).contains("Learning is off"))
        // "Learn automatically" means nothing while background learning is off, and says so.
        assertTrue(AutoLearn.stateLine(Which.AUTO, Switch.ON, false, true).contains("Learning is off"))
        // The sensitive switch depends on "Learn automatically".
        assertTrue(
            AutoLearn.stateLine(Which.SENSITIVE, Switch.ON, true, false)
                .contains("Learn automatically is off"),
        )
        val off = AutoLearn.stateLine(Which.AUTO, Switch.OFF, true, false)
        assertTrue(off, off.startsWith("Off.") && off.contains("asks you first"))
        assertEquals(AutoLearn.waitingLine(Which.SENSITIVE), AutoLearn.stateLine(Which.SENSITIVE, Switch.WAITING, true, true))
        assertTrue(AutoLearn.stateLine(Which.AUTO, Switch.UNKNOWN, null, null).startsWith("Couldn't tell"))
    }

    @Test
    fun theLearningLineNoLongerSaysEveryFactNeedsAYes() {
        val on = com.jarvis.client.net.MemoryCounts.learningLine(true)
        assertFalse(on, on.contains("each one still needs your yes"))
        assertTrue(on, on.contains(Which.AUTO.title))
    }

    @Test
    fun theLastCardIsMentionedOnlyWhenItDidNotTurnTheSwitchOn() {
        assertEquals(
            "The last request to turn it on was denied.",
            AutoLearn.lastLine(AutoLearn.Last("denied", null), Switch.OFF),
        )
        assertEquals(
            "The last request to turn it on did not go through: the gate answered at tier 'auto'.",
            AutoLearn.lastLine(AutoLearn.Last("refused", "the gate answered at tier 'auto'"), Switch.OFF),
        )
        assertTrue(AutoLearn.lastLine(AutoLearn.Last("timed_out", null), Switch.OFF)!!.contains("expired"))
        assertNull(AutoLearn.lastLine(AutoLearn.Last("enabled", null), Switch.OFF))
        assertNull(AutoLearn.lastLine(AutoLearn.Last("withdrawn", "you turned it off"), Switch.OFF))
        assertNull(AutoLearn.lastLine(AutoLearn.Last("denied", null), Switch.ON))
        assertNull(AutoLearn.lastLine(AutoLearn.Last("denied", null), Switch.WAITING))
        assertNull(AutoLearn.lastLine(null, Switch.OFF))
    }

    @Test
    fun onWaitsForTheCardAndOffIsDone() {
        // ON: the PC's 202, through the same classifier every switch uses.
        val on = DesktopWrite.classify(202, obj("""{"ok":true,"waiting":true,"auto":false}"""))
        assertTrue(on is ApiResult.Ok && on.value is DesktopWrite.Outcome.Waiting)
        val said = AutoLearn.said(Which.AUTO, true, (on as ApiResult.Ok).value)
        assertEquals(AutoLearn.waitingLine(Which.AUTO), said)
        // OFF: 200 at once.
        val off = DesktopWrite.classify(200, obj("""{"ok":true,"auto":false}"""))
        assertTrue(off is ApiResult.Ok && off.value is DesktopWrite.Outcome.Done)
        assertEquals(
            "Jarvis no longer learns automatically. New facts wait for your yes.",
            AutoLearn.said(Which.AUTO, false, (off as ApiResult.Ok).value),
        )
        assertEquals(
            "Sensitive topics wait for your yes again.",
            AutoLearn.said(Which.SENSITIVE, false, DesktopWrite.Outcome.Done(null)),
        )
        // The PC's own sentence wins.
        assertEquals("Off.", AutoLearn.said(Which.SENSITIVE, false, DesktopWrite.Outcome.Done("off")))
        // Tier other than ask: 503 with a reason is "Not changed", never "on".
        val refused = DesktopWrite.classify(503, obj("""{"ok":false,"error":"learning_auto_enable is tier 'auto'"}"""))
        assertTrue(refused is ApiResult.Ok)
        assertTrue(AutoLearn.said(Which.AUTO, true, (refused as ApiResult.Ok).value).startsWith("Not changed."))
    }

    // ------------------------------------------------------------- list ---

    private val pageJson = """{"facts":[
        {"id":9,"text":"The owner's project is called Jarvis","saved_at":1727180400,"provenance":"typed","device":"desktop"},
        {"id":8,"text":"The owner prefers tea","saved_at":1727180300.25,"provenance":"voice","device":"phone"},
        {"id":"7","text":"an id that is not a number"},
        {"id":6,"text":"   "},
        {"id":5,"text":"No time","saved_at":"yesterday"}
      ],"auto":true,"auto_sensitive":false}"""

    @Test
    fun aPageKeepsOnlyFactsThatCanBeShownAndForgotten() {
        val page = AutoLearn.page(obj(pageJson), asked = 5)
        assertEquals(listOf(9L, 8L, 5L), page.facts.map { it.id })
        assertEquals(1727180300.25, page.facts[1].savedAt!!, 0.0)
        assertNull(page.facts[2].savedAt)
        assertFalse(page.facts[0].aloud)
        assertTrue("voice is said aloud", page.facts[1].aloud)
        // Five came back for a limit of five: there may be more.
        assertTrue(page.mayHaveOlder)
        assertFalse(AutoLearn.page(obj(pageJson), asked = 30).mayHaveOlder)
        assertEquals(true, page.status.auto)
        assertTrue(AutoLearn.page(obj("""{"auto":true}""")).facts.isEmpty())
    }

    @Test
    fun loadOlderAsksBeforeTheOldestShownWrittenOutInFull() {
        val facts = AutoLearn.page(obj(pageJson)).facts
        assertEquals(1727180300.25, AutoLearn.olderThan(facts)!!, 0.0)
        assertEquals("/api/memory/auto?limit=30&before=1727180300.25", AutoLearn.listPath(1727180300.25))
        assertEquals("/api/memory/auto?limit=30&before=1727180300", AutoLearn.listPath(1727180300.0))
        assertEquals("/api/memory/auto?limit=30", AutoLearn.listPath())
        assertEquals("/api/memory/auto?limit=1", AutoLearn.listPath(limit = 1))
        assertEquals("/api/memory/auto?limit=100", AutoLearn.listPath(limit = 500))
        assertEquals("/api/memory/auto?limit=30", AutoLearn.listPath(Double.NaN))
        assertNull(AutoLearn.olderThan(emptyList()))
    }

    @Test
    fun aSecondPageSharingASecondAddsNoFactTwice() {
        val first = AutoLearn.page(obj(pageJson)).facts
        val second = AutoLearn.page(
            obj("""{"facts":[{"id":8,"text":"The owner prefers tea","saved_at":1727180300.25},
                           {"id":4,"text":"The owner lives in Leeds","saved_at":1727180000}]}"""),
        ).facts
        assertEquals(listOf(9L, 8L, 5L, 4L), AutoLearn.append(first, second).map { it.id })
    }

    @Test
    fun eachRowSaysWhenAndWhere() {
        val zone = ZoneOffset.UTC
        val today = LocalDate.of(2024, 9, 24)
        val facts = AutoLearn.page(obj(pageJson)).facts
        assertEquals("Today 12:20 · from the PC", AutoLearn.rowLine(facts[0], zone, today))
        assertEquals("Today 12:18 · from the phone", AutoLearn.rowLine(facts[1], zone, today))
        assertEquals("When unknown", AutoLearn.rowLine(facts[2], zone, today))
        assertNull(AutoLearn.fromWhere("toaster"))
        assertNull(AutoLearn.fromWhere(null))
    }

    // ----------------------------------------------------------- forget ---

    @Test
    fun forgetSaysWhatHappened() {
        val (gone, said) = AutoLearn.forgetSaid(
            obj("""{"ok":true,"id":9,"was":"x","note":"retired, not deleted"}"""),
        )
        assertTrue(gone)
        assertEquals(AutoLearn.FORGOTTEN, said)
        val (kept, no) = AutoLearn.forgetSaid(obj("""{"ok":false,"error":"store busy"}"""))
        assertFalse(kept)
        assertEquals("Not forgotten. Store busy.", no)
        assertTrue(AutoLearn.forgetFailure(ApiError.Server(409, ""))!!.startsWith("Not forgotten."))
        assertNull(AutoLearn.forgetFailure(ApiError.Server(500, "")))
        assertNull(AutoLearn.forgetFailure(ApiError.BadToken))
        assertTrue(AutoLearn.FORGET_CONFIRM.contains("cannot be undone"))
    }

    @Test
    fun anOlderPcSaysSoInsteadOfAnError() {
        assertEquals(
            "Your PC's Jarvis does not have automatic learning yet.",
            AutoLearn.listFailure(ApiError.NotFound),
        )
        assertNull(AutoLearn.listFailure(ApiError.BadToken))
    }

    // ------------------------------------------------------------ event ---

    @Test
    fun theEventIsReadForIdsOnly() {
        assertEquals(listOf(3L, 4L), AutoLearn.savedIds(obj("""{"ids":[3,4,4]}""")))
        assertEquals(listOf(7L), AutoLearn.savedIds(obj("""{"key":"memory","value":{"ids":[7]}}""")))
        assertEquals(listOf(1L), AutoLearn.savedIds(obj("""{"ids":["2",1,null,{"id":5}]}""")))
        assertTrue(AutoLearn.savedIds(obj("""{"text":"The owner prefers tea"}""")).isEmpty())
        assertTrue(AutoLearn.savedIds(null).isEmpty())
    }

    @Test
    fun anEventHeardTwiceIsCountedOnce() {
        val (first, seen) = AutoLearn.fresh(emptyList(), listOf(1, 2))
        assertEquals(listOf(1L, 2L), first)
        val (again, seen2) = AutoLearn.fresh(seen, listOf(2, 3))
        assertEquals(listOf(3L), again)
        assertEquals(listOf(1L, 2L, 3L), seen2)
        val big = (1L..(AutoLearn.SEEN_CAP + 10).toLong()).toList()
        assertEquals(AutoLearn.SEEN_CAP, AutoLearn.fresh(emptyList(), big).second.size)
    }

    // ------------------------------------------ the phone's own wiring ---

    /** Walks up from Gradle's working folder (`jarvis-client/app`) to the repository. */
    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private val main = "jarvis-client/app/src/main/java/com/jarvis/client"

    private fun body(src: String, start: String): String {
        val at = src.indexOf(start)
        assertTrue("$start is missing", at >= 0)
        return src.substring(at, minOf(src.length, at + 900))
    }

    @Test
    fun onIsHeldOnAStaleLinkAndOffNever() {
        val rt = repoFile("$main/JarvisRuntime.kt").readText()
        val set = body(rt, "suspend fun setAutoLearn(")
        // The first thing it does: hold ON only.
        assertTrue(set, set.lineSequence().drop(1).first().trim() == "if (on) actionBlocker()?.let { return it }")
        val forget = body(rt, "suspend fun forgetAutoFact(")
        assertTrue(forget, forget.lineSequence().drop(1).first().trim() == "actionBlocker()?.let { return false to it }")
    }

    @Test
    fun theEventIsHandledAndNeverReachesANotification() {
        val rt = repoFile("$main/JarvisRuntime.kt").readText()
        assertTrue(rt.contains("com.jarvis.client.net.AutoLearn.EVENT -> onMemorySaved(event.data)"))
        for (f in File(repoFile("$main/JarvisRuntime.kt").parentFile, "service").listFiles().orEmpty()) {
            val t = f.readText()
            assertFalse("${f.name} must not notify a saved fact", t.contains("memory_saved") || t.contains("AutoLearn"))
        }
    }

    @Test
    fun theListIsHiddenLikeTheOtherMemoryLists() {
        val plate = repoFile("$main/ui/screens/AutoLearnPlate.kt").readText()
        val section = body(plate, "internal fun SavedAutomaticallySection(")
        assertTrue(section.contains("if (privateHidden) {\n        HiddenSection(AutoLearn.TITLE"))
        val brain = repoFile("$main/ui/screens/BrainScreen.kt").readText()
        val item = body(brain, "item(key = \"memory-auto\")")
        assertTrue(item, item.contains("SavedAutomaticallySection(") && item.contains("privateHidden = privateHidden,"))
        // Forget and switching ON are greyed on a stale link as well as refused.
        assertTrue(plate.contains("enabled = canAct && busyId == null"))
        assertTrue(plate.contains("AutoLearn.Switch.OFF -> canAct"))
    }
}
