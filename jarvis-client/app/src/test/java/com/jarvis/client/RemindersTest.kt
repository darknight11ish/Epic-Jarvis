package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.MenuCatalog
import com.jarvis.client.net.Reminders
import com.jarvis.client.net.Schedule
import com.jarvis.client.ui.MenuPlaces
import com.jarvis.client.ui.Screen
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The phone's own Reminders screen (the owner's ask of 2026-11-02: *"I want a
 * custom reminders screen on the jarvis Android app. right now when I open it
 * it just takes me to a subsection of the brain that has reminders. I also want
 * another option within the reminders that includes a daily to-do list"*).
 *
 * Two halves, the suite's usual pair:
 *
 *  1. **The logic**, through [Reminders] on the real answer `GET /api/schedule`
 *     gives (docs/JARVIS-API.md sections 21 and 179) - the two choices, which
 *     rows each one draws, the PC's own age tags in the rollover list and its own
 *     day headings in the day-by-day one, the named lists staying where they
 *     are, and the two modes being offered only when the PC sent them.
 *  2. **The wiring**, read from the source, because a Compose screen cannot be
 *     composed on a plain JVM (the established shape: `HomeNavRowTest`,
 *     `MenuVisibilityTest`, `ComingUpReachabilityTest`): Home's Reminders button
 *     opens [Screen.REMINDERS], that destination is the new screen, and the
 *     screen only ever speaks the scheduler's existing routes.
 *
 * Nothing here is a device test. The screen has not been drawn on a phone; the
 * Lead's run is what proves the tap.
 */
class RemindersTest {

    private fun obj(s: String) = JarvisJson.parseToJsonElement(s) as JsonObject

    /**
     * One answer from a current PC: three reminders, two to-do items on the
     * to-do list (one from today, one from yesterday), and one item on the named
     * list "shopping" - which is grouped by the PC under today too, exactly as
     * the real `todo_days` does, so the filtering below is proved against the
     * shape the PC really sends.
     */
    private val list = obj(
        """{"available":true,"now":1762128000,
          "todo_mode":"rollover",
          "todo_modes":[
            {"value":"rollover","label":"Daily rollover",
             "detail":"Today's list is everything still open."},
            {"value":"day","label":"Day by day",
             "detail":"Each day keeps its own list."}],
          "jobs":[
            {"id":"s0000000001","kind":"timer","text":"pasta","state":"active","left":600,"duration":600},
            {"id":"s0000000002","kind":"alarm","text":"","state":"active","when":"07:00 tomorrow"},
            {"id":"s0000000003","kind":"reminder","text":"take my pills","state":"active"}],
          "todo":[
            {"id":"s0000000010","kind":"todo","text":"buy milk","state":"active",
             "created_date":"2026-11-02"},
            {"id":"s0000000011","kind":"todo","text":"renew the prescription","state":"active",
             "created_date":"2026-11-01","carry":"from yesterday"},
            {"id":"s0000000012","kind":"todo","text":"milk","state":"active","list":"shopping",
             "created_date":"2026-11-02"}],
          "todo_days":[
            {"date":"2026-11-02","label":"Today","count":2,
             "items":["s0000000010","s0000000012"]},
            {"date":"2026-11-01","label":"Yesterday","count":1,
             "items":["s0000000011"]}],
          "lists":[{"name":"shopping","title":"Shopping","open":1}]}""",
    )

    private val view = Schedule.parse(list)!!

    // ------------------------------------------------------- the two choices ---

    @Test
    fun `the screen draws two choices, and the second is the owner's daily to-do list`() {
        assertEquals(
            "the two choices, in the order they are drawn",
            listOf("Reminders", "Daily to-do list"),
            Reminders.TABS,
        )
        assertEquals("the owner's own words for the second choice", "Daily to-do list", Reminders.TAB_TODO)
        assertEquals(
            "the first choice is the screen's own name, so the row and the screen agree",
            Reminders.TITLE,
            Reminders.TAB_JOBS,
        )
        assertEquals("it opens on the reminders", Reminders.TAB_JOBS, Reminders.DEFAULT_TAB)
        assertEquals("a saved tab comes back", Reminders.TAB_TODO, Reminders.tabOf(Reminders.TAB_TODO))
        assertEquals("no saved tab is the reminders", Reminders.TAB_JOBS, Reminders.tabOf(null))
        assertEquals("an unknown value is never a blank screen", Reminders.TAB_JOBS, Reminders.tabOf("nonsense"))
    }

    // ---------------------------------------------------------- the reminders ---

    @Test
    fun `the reminders tab is the same list the Brain plate draws, and no to-do rows`() {
        assertEquals(
            "the reminders tab must read exactly the rows the Coming up plate reads",
            view.jobs.map { it.id },
            Reminders.jobs(view).map { it.id },
        )
        assertTrue(
            "a to-do item must not be drawn twice: the PC answers those in their own list",
            Reminders.jobs(view).none { it.kind == "todo" },
        )
    }

    @Test
    fun `one row offers the same buttons as before, through the shared row`() {
        // The screen draws ScheduleRow/WentOffRow (asserted below), so the
        // buttons are Schedule.actionsOf's own list - the exact set the Brain
        // plate and the desktop offer. Nothing on this screen names an action of
        // its own, which is what keeps the two surfaces from drifting apart.
        assertEquals(listOf("add_time", "pause", "delete"), Schedule.actionsOf(view.jobs[0]))
        assertEquals(listOf("pause", "delete"), Schedule.actionsOf(view.jobs[1]))
        assertEquals(listOf("done", "delete"), Schedule.actionsOf(view.todo[0]))
        val screen = code(repoFile(REMINDERS_SCREEN).readText())
        for (action in Schedule.ACTIONS) {
            assertFalse(
                "the screen names the \"$action\" action itself instead of using Schedule.actionsOf",
                screen.contains("\"$action\""),
            )
        }
    }

    // ------------------------------------------------------- the to-do list ---

    @Test
    fun `the daily to-do list is the to-do list itself, never a named list's items`() {
        assertEquals(
            "the to-do tab draws the to-do list's own items, in the PC's order",
            listOf("s0000000010", "s0000000011"),
            Reminders.todoItems(view).map { it.id },
        )
        assertFalse(
            "\"shopping\" is a list of its own, drawn in Brain's Coming up",
            Reminders.todoItems(view).any { it.list.isNotEmpty() },
        )
    }

    @Test
    fun `rollover keeps the PC's own age tag, and today's item has none`() {
        val today = Reminders.todoItems(view)[0]
        val older = Reminders.todoItems(view)[1]
        assertEquals("an item written today has no age to show", "", Reminders.itemTag(today, Schedule.MODE_ROLLOVER))
        assertEquals(
            "an older item carries the PC's words, never one this phone worked out",
            "from yesterday",
            Reminders.itemTag(older, Schedule.MODE_ROLLOVER),
        )
        assertEquals(
            "and the row really shows it under the words",
            listOf("from yesterday"),
            Schedule.metaOf(older, 0L, Reminders.itemTag(older, Schedule.MODE_ROLLOVER)),
        )
    }

    @Test
    fun `day by day puts the day on the heading and never on the row`() {
        val older = Reminders.todoItems(view)[1]
        assertEquals("the heading already names the day", "", Reminders.itemTag(older, Schedule.MODE_DAY))
        val groups = Reminders.dayGroups(view)
        assertEquals(
            "the PC's own headings, today first",
            listOf("Today", "Yesterday"),
            groups.map { it.label },
        )
        assertEquals(listOf("s0000000010"), groups[0].items.map { it.id })
        assertEquals(listOf("s0000000011"), groups[1].items.map { it.id })
        // The headings are the PC's words, character for character - this phone
        // never works one out from its own clock.
        assertEquals(view.todoDays.map { it.label }, groups.map { it.label })
        assertEquals(view.todoDays.map { it.date }, groups.map { it.date })
    }

    @Test
    fun `a named list's items are grouped by the PC too, and are not this tab's`() {
        // The PC's own group really does hold the shopping item, or this test
        // would prove nothing about the filtering.
        assertEquals(
            listOf("s0000000010", "s0000000012"),
            view.todoDays.first().items.map { it.id },
        )
        assertEquals(
            "the to-do tab's first day holds only the to-do list's own item",
            listOf("s0000000010"),
            Reminders.dayGroups(view).first().items.map { it.id },
        )
    }

    @Test
    fun `while the words are hidden the day headings go with them`() {
        val hidden = Schedule.hide(view)
        val groups = Reminders.dayGroups(hidden)
        assertEquals("the day labels are the PC's words about the owner's items", 1, groups.size)
        assertEquals("so no heading is shown", "", groups.single().label)
        assertEquals(
            "the same items, with their words blanked",
            listOf("s0000000010", "s0000000011"),
            groups.single().items.map { it.id },
        )
        assertTrue("and their words really are gone", groups.single().items.all { it.hidden })
        assertEquals(
            "an age is a fact about words that are gone",
            "",
            Reminders.itemTag(groups.single().items[1], Schedule.MODE_ROLLOVER),
        )
    }

    @Test
    fun `a PC from before the two ways has one way, and is not offered the other`() {
        val old = Schedule.parse(
            obj(
                """{"jobs":[],
                   "todo":[{"id":"s0000000020","kind":"todo","text":"buy milk","state":"active"}]}""",
            ),
        )!!
        assertEquals("an older PC is rollover, which is what it really does", Schedule.MODE_ROLLOVER, old.todoMode)
        assertEquals("and sends no grouping", 1, Reminders.dayGroups(old).size)
        assertEquals("so the one day holds every open item", "", Reminders.dayGroups(old).single().label)
        assertEquals(
            listOf("s0000000020"),
            Reminders.dayGroups(old).single().items.map { it.id },
        )
        assertFalse("the mode control must not be offered", Reminders.canChangeMode(old))
        assertFalse("nor on no answer at all", Reminders.canChangeMode(null))
    }

    @Test
    fun `the two modes are the PC's own words, with the one in force marked`() {
        assertTrue("a current PC can be asked", Reminders.canChangeMode(view))
        val modes = Reminders.modeChoices(view)
        assertEquals(listOf("Daily rollover", "Day by day"), modes.map { it.label })
        assertEquals(
            "the words come from the PC, never typed here",
            view.todoModes.map { it.label },
            modes.map { it.label },
        )
        assertEquals("the one in force says so", "Daily rollover (now)", Reminders.modeLabel(modes[0], "rollover"))
        assertEquals("the other one does not", "Day by day", Reminders.modeLabel(modes[1], "rollover"))
        // The fallback pair (an older PC that still answered) uses the same two
        // values this phone sends, so the control can never name a third.
        assertEquals(
            listOf(Schedule.MODE_ROLLOVER, Schedule.MODE_DAY),
            Schedule.todoModes(null).map { it.value },
        )
    }

    @Test
    fun `the top line counts the reminders the PC listed`() {
        assertEquals("0 reminders", Reminders.countLine(0))
        assertEquals("1 reminder", Reminders.countLine(1))
        assertEquals("3 reminders", Reminders.countLine(3))
    }

    // ------------------------------------------------------------- the wiring ---

    @Test
    fun `Home's Reminders button opens the new screen instead of jumping into Brain`() {
        val activity = code(repoFile(ACTIVITY).readText())
        val callback = activity.substringAfter("onOpenReminders = {", "").substringBefore("},")
        assertTrue("Home's Reminders callback is not wired up at all", callback.isNotBlank())
        assertTrue(
            "the button must open the phone's own Reminders screen: $callback",
            callback.contains("nav.go(Screen.REMINDERS)"),
        )
        assertFalse(
            "the button still jumps into the Brain's Coming up plate: $callback",
            callback.contains("Screen.BRAIN") || callback.contains("pendingSection"),
        )
        // The screen itself is drawn by its own destination.
        assertTrue(
            "no destination draws RemindersScreen",
            activity.contains("Screen.REMINDERS -> com.jarvis.client.ui.screens.RemindersScreen("),
        )
        // The destination must stay after the screens that already existed when
        // it landed, because a saved back stack restores by name - a screen
        // inserted in the middle would restore as another. It is no longer the
        // LAST entry: "Local AI" was appended after it on 2026-11-13, which is
        // the same append-only rule one screen later. The newest screen is the
        // one that must be last, and that check belongs to the newest screen's
        // own test rather than to Reminders.
        assertTrue(
            "REMINDERS must stay after the screens that predate it",
            Screen.REMINDERS.ordinal > Screen.EDIT_HUD.ordinal,
        )
    }

    @Test
    fun `the Brain's Coming up plate is untouched and still reachable`() {
        assertEquals(
            "the plate the button used to open must still be the Brain's own section",
            "brain.work.coming-up",
            MenuPlaces.menuFor(Screen.BRAIN.name, "coming-up"),
        )
        assertTrue(
            "Coming up must stay never-hideable: a due reminder shows there",
            "brain.work.coming-up" in MenuCatalog.NEVER_HIDE,
        )
        val brain = repoFile(BRAIN_SCREEN).readText()
        assertEquals(
            "Brain must still draw the Coming up plate under its own item key",
            1,
            Regex("""plate\("coming-up", drawn""").findAll(brain).count(),
        )
        assertTrue(
            "and the plate must still be the one that draws ComingUpSection",
            brain.contains("ComingUpSection("),
        )
        // And the plate still draws the to-do list, the named lists and the
        // standby schedule - this change added a screen, it removed nothing.
        val plate = repoFile(COMING_UP_PLATE).readText()
        assertTrue("the plate lost its to-do list", plate.contains("Schedule.TODO_TITLE"))
        assertTrue("the plate lost its named lists", plate.contains("Schedule.namedLists("))
        assertTrue("the plate lost the standby schedule", plate.contains("Schedule.STANDBY_TITLE"))
    }

    @Test
    fun `the screen speaks only the scheduler's own routes, and adds no card or bulk action`() {
        val screen = code(repoFile(REMINDERS_SCREEN).readText())
        // ONE read, which is the same route the Brain plate reads.
        assertEquals(
            "the screen must read the schedule exactly once",
            1,
            Regex("""JarvisRuntime\.schedule\(\)""").findAll(screen).count(),
        )
        assertTrue("the answer is read by Schedule.parse", screen.contains("Schedule.parse("))
        // The three existing writes, through JarvisRuntime - never a body of its
        // own, and never a route literal in a screen (routes live in net/).
        assertTrue("the one-job write is gone", screen.contains("JarvisRuntime.scheduleAct("))
        assertTrue("adding a to-do item is gone", screen.contains("JarvisRuntime.addTodo("))
        assertTrue("changing how the list is shown is gone", screen.contains("JarvisRuntime.setTodoMode("))
        assertFalse(
            "a screen must never name a backend route: routes live in net/",
            screen.contains("\"/api/"),
        )
        assertFalse(
            "the screen builds its own JSON body instead of using net/Schedule",
            screen.contains("JarvisJson") || screen.contains("Request.Builder"),
        )
        // One job per tap, never "all": the Brain plate's one bulk action (Clear
        // list) is deliberately not duplicated here.
        for (bulk in listOf("clearList(", "CLEAR_LIST", "clear_list", "deleteAll", "approveAll")) {
            assertFalse("the screen grew a bulk action: $bulk", screen.contains(bulk))
        }
        // No approval card is raised, answered or bypassed on this screen: the
        // scheduler's writes never raise one, and this surface must not either.
        for (card in listOf("approve", "deny", "Approve", "Deny", "PendingItem", "approval")) {
            assertFalse("the screen touches the approval model: $card", screen.contains(card))
        }
        // The rows are the SHARED ones, so the two surfaces cannot diverge.
        assertTrue("the reminders are not drawn by the shared row", screen.contains("ScheduleRow("))
        assertTrue("a job that went off is not drawn by the shared row", screen.contains("WentOffRow("))
        val plate = repoFile(COMING_UP_PLATE).readText()
        assertTrue(
            "ScheduleRow must be shared with this screen",
            plate.contains("internal fun ScheduleRow("),
        )
        assertTrue(
            "WentOffRow must be shared with this screen",
            plate.contains("internal fun WentOffRow("),
        )
        // Both choices really are drawn, and the to-do one is the owner's words.
        assertTrue("the screen no longer draws the two choices", screen.contains("Reminders.TABS"))
        assertTrue("the to-do choice is not drawn", screen.contains("Reminders.TAB_TODO"))
        // The private lists hide the words through the one rule, and the screen
        // offers the Show that asks for the fingerprint or PIN first.
        assertTrue("the screen stopped hiding the words", screen.contains("Schedule.hide("))
        assertTrue("the Show control is gone", screen.contains("onShowPrivate"))
        // Held on a stale link, said plainly (rule 4).
        assertTrue("the not-connected line is gone", screen.contains("Reminders.NOT_CONNECTED"))
    }

    // ------------------------------------- a routine, part by part (2026-11-03) ---
    //
    // The owner's ask and Gemini's rulings Q8/Q9 gave a reminder PARTS. The phone
    // reads them and answers ONE part's ONE button, and that is all: creating or
    // editing a routine is the PC's alone, because a part's destination can be
    // that PC's Obsidian vault or a goal/habit id (docs/ARCHITECTURE.md section 8,
    // "One-sided on purpose"). These checks pin exactly that division.

    @Test
    fun `the screen answers a part and never creates or edits a routine`() {
        val screen = code(repoFile(REMINDERS_SCREEN).readText())
        // Per-part acting rides the ONE existing write door, with the part's
        // index - no new route, and no body of the screen's own.
        assertTrue(
            "the screen stopped answering a part",
            screen.contains("JarvisRuntime.scheduleAnswer("),
        )
        assertEquals(
            "both the reminders and the \"just went off\" rows must offer a part's buttons",
            2,
            Regex("""onAnswer = \{ p, b -> answer\(job, p, b\) \}""").findAll(screen).count(),
        )
        // Not one line of a routine editor: no `steps` key typed here, no add or
        // edit body, no parts form. A routine is made on the PC and this screen
        // would have nowhere to write a part's destination.
        for (mine in listOf("\"steps\"", "steps =", "addRoutine", "editRoutine",
            "ADD_PATH", "EDIT_KEYS", "action =")) {
            assertFalse("the screen grew a routine editor: $mine", screen.contains(mine))
        }
    }

    @Test
    fun `the parts are drawn by the one shared block, with each part's own buttons`() {
        val plate = code(repoFile(COMING_UP_PLATE).readText())
        assertTrue("the parts block is not shared with the Brain plate",
            plate.contains("internal fun PartsBlock("))
        assertEquals(
            "both shared rows must draw a routine's parts",
            2,
            Regex("""PartsBlock\(job, enabled, onAnswer\)""").findAll(plate).count(),
        )
        assertTrue("the row cannot be handed an answer",
            plate.contains("onAnswer: ((part: Int, button: Int) -> Unit)? = null"))
        // A part's buttons are the PC's own, and a press sends (part, button):
        // never a label, and never "all parts".
        assertTrue("a part's buttons are not drawn from what the PC sent",
            plate.contains("part.buttons.forEachIndexed"))
        assertTrue("a press no longer names its part", plate.contains("onAnswer?.invoke(index, at)"))
        assertTrue("a part that could only be refused is still offered",
            plate.contains("part.canAnswer && part.buttons.isNotEmpty()"))
        // A surface that cannot answer draws them READ-ONLY: never a live button
        // that does nothing.
        assertTrue("a button with no handler is drawn live",
            plate.contains("val canPress = enabled && onAnswer != null"))
        assertTrue(plate.contains("enabled = canPress"))
        // An unreadable routine says so in one line rather than drawing half of it.
        assertTrue(plate.contains("Schedule.PARTS_UNREADABLE"))
        // Its place and its missed count are the PC's words, not this phone's.
        assertTrue(plate.contains("Schedule.partCountLine("))
        assertTrue(plate.contains("Schedule.missedPartsLine("))
        // Nothing here rings anything: still no alarm, no notification, no card.
        for (bulk in listOf("approveAll", "Approve", "deleteAll", "NotificationCompat")) {
            assertFalse("the parts block grew a control it must not have: $bulk", plate.contains(bulk))
        }
    }

    @Test
    fun `a part's own buttons are the notification's actions and the press carries its step`() {
        // The notification and the service it hands a press to. Both are Android
        // classes, so this module holds them to their source text - the same
        // established shape as the screen's own wiring above.
        val notifier = code(repoFile(NOTIFIER).readText())
        val service = code(repoFile(EVENT_SERVICE).readText())
        assertTrue("a part's buttons are not the notification's actions",
            notifier.contains("ask.buttons.forEachIndexed"))
        assertTrue("the action no longer carries WHICH part it is",
            notifier.contains("answerIntent(context, jobId, key, index, step)"))
        assertTrue(notifier.contains("const val EXTRA_STEP"))
        assertTrue("the answer intent does not put the part on the intent",
            notifier.contains("putExtra(EXTRA_STEP, step)"))
        assertTrue("the answer intent does not carry its own tag",
            notifier.contains("putExtra(EXTRA_TAG, key)"))
        // THREE is Android's ceiling and the PC's (MAX_ASK): a part's own
        // buttons REPLACE this notification's Snooze and Stop, so no fourth and
        // no fifth action can ever be drawn, and no Stop is lost to one.
        assertTrue("Snooze is no longer the alternative to a part's buttons",
            notifier.contains("} else if (kind in SNOOZABLE && !openBriefing && !quiet) {"))
        assertTrue("Stop is no longer skipped when a part brings its own buttons",
            notifier.contains("if (!quiet && !openBriefing && ask == null) {"))
        assertEquals("a question's buttons are still capped at Android's three", 3, Schedule.MAX_ASK)
        // The service reads both extras and passes them straight through.
        assertTrue("the service no longer reads WHICH part",
            service.contains("intent.getIntExtra(ScheduleNotifier.EXTRA_STEP, -1)"))
        assertTrue("the service no longer reads the notification's tag",
            service.contains("intent.getStringExtra(ScheduleNotifier.EXTRA_TAG)"))
        assertTrue("the service no longer passes the part on",
            service.contains("JarvisRuntime.scheduleAnswer(id, button, part, tag)"))
    }

    // ------------------------------------------------------------------ kit ---

    /** [src] with whole-line `//` comments and block comments blanked, not dropped. */
    private fun code(src: String): String {
        val out = ArrayList<String>()
        var inBlock = false
        for (line in src.lines()) {
            val t = line.trimStart()
            if (inBlock) {
                if (t.contains("*/")) inBlock = false
                out.add("")
                continue
            }
            if (t.startsWith("/*")) {
                if (!t.contains("*/")) inBlock = true
                out.add("")
                continue
            }
            if (t.startsWith("//")) {
                out.add("")
                continue
            }
            out.add(line.substringBefore(" //"))
        }
        return out.joinToString("\n")
    }

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

    private companion object {
        const val CLIENT = "jarvis-client/app/src/main/java/com/jarvis/client/"
        const val ACTIVITY = CLIENT + "MainActivity.kt"
        const val BRAIN_SCREEN = CLIENT + "ui/screens/BrainScreen.kt"
        const val COMING_UP_PLATE = CLIENT + "ui/screens/ComingUpPlate.kt"
        const val REMINDERS_SCREEN = CLIENT + "ui/screens/RemindersScreen.kt"
        const val NOTIFIER = CLIENT + "service/ScheduleNotifier.kt"
        const val EVENT_SERVICE = CLIENT + "service/EventService.kt"
    }
}
