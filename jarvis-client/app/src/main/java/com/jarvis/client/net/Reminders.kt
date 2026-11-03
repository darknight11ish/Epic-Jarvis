package com.jarvis.client.net

/**
 * The phone's own Reminders screen - the owner's ask of 2026-11-02: *"I want a
 * custom reminders screen on the jarvis Android app. right now when I open it
 * it just takes me to a subsection of the brain that has reminders. I also want
 * another option within the reminders that includes a daily to-do list"*.
 *
 * Before this, Home's Reminders button opened Brain -> Coming up
 * (`brain.work.coming-up`, the plate `ComingUpPlate.kt` draws). That plate is
 * still there and is still the way into the named lists, the standby schedule
 * and "a file from your PC"; this screen is a second, dedicated way in to the
 * same data, drawn as a screen of its own with TWO choices:
 *
 *  - [TAB_JOBS] - the reminders themselves: the timers counting down, the
 *    alarms, the reminders and the repeating ones, in the PC's own order, with
 *    "Just went off" at the top. Exactly the rows the Brain plate draws, from
 *    exactly the same read ([Schedule.PATH]), with the same one-job buttons
 *    ([Schedule.actionsOf]) and the same "Also on my phone" hand-over.
 *  - [TAB_TODO] - the "daily to-do list": the scheduler's to-do list in the
 *    PC's own two ways of showing it (2026-11-02; docs/JARVIS-API.md section
 *    179) - daily rollover, where each older item carries the PC's own age tag
 *    ("from yesterday", "from Friday (3d ago)"), and day by day, where the same
 *    items are grouped under the day the PC says each was written. Nothing is
 *    worked out from this phone's clock: the PC wrote the item and the PC says
 *    how old it is, so a phone a day out cannot mislabel one.
 *
 * NOTHING NEW IS PERMITTED HERE. Every read is [Schedule.PATH]; every change is
 * one of the existing scheduler writes ([Schedule.ADD_PATH], [Schedule.ACT_PATH])
 * through [com.jarvis.client.JarvisRuntime] - one job per tap, or one new to-do
 * item, or the one cardless "how the list is drawn" value. There is no
 * delete-all, no bulk anything, no approval card added or removed, and no new
 * route (tools/check_parity.py has nothing new to classify). A repeating job's
 * card is still raised on the PC when it is set up by talking to Jarvis, exactly
 * as before.
 *
 * THE NAMED LISTS STAY IN BRAIN. "shopping" and the like are their own lists with
 * their own item counts, their own Add box and their one "Clear list" (which
 * deletes every item on a list after an "are you sure?"). This screen's to-do
 * tab is the to-do list itself, so it neither shows them nor grows a second bulk
 * delete; [NAMED_LISTS_WHERE] says where they are, so nothing looks lost.
 *
 * Pure Kotlin, no Android types, so `RemindersTest` runs it on a plain JVM.
 * The Compose half is `ui/screens/RemindersScreen.kt`.
 */
object Reminders {

    /** The screen's title, and the word Home's row already uses. */
    const val TITLE = "Reminders"

    /** The two choices inside the screen, in the order they are drawn. */
    const val TAB_JOBS = "Reminders"
    const val TAB_TODO = "Daily to-do list"

    /** Both choices, in order - the one place the screen's shape is written down. */
    val TABS = listOf(TAB_JOBS, TAB_TODO)

    /** What the screen opens on: the reminders themselves. */
    const val DEFAULT_TAB = TAB_JOBS

    /**
     * A tab's name as a saved value (the screen keeps it across a rotation with
     * `rememberSaveable`, which restores by value). Anything unknown is the
     * reminders tab, never a blank screen.
     */
    fun tabOf(name: String?): String = if (name == TAB_TODO) TAB_TODO else TAB_JOBS

    /**
     * The line under the Reminders tab's heading: the same sentence the Brain
     * plate shows ([Schedule.PC_IS_THE_CLOCK]), so the two cannot drift apart.
     */
    const val JOBS_UNDER = Schedule.PC_IS_THE_CLOCK

    /** The Daily to-do list tab's own line, in plain words. */
    const val TODO_UNDER =
        "The to-do list your PC keeps. Done ticks one off and it leaves the list; " +
            "Delete removes it."

    /**
     * Where the named lists are, since this tab is the to-do list itself. The
     * Brain plate already draws them, with their own Add box and their own
     * "Clear list", so this screen does not grow a second copy of that surface.
     */
    const val NAMED_LISTS_WHERE =
        "Your other lists - \"shopping\" and the like - are in Brain, Work, Coming up."

    /**
     * How the list is shown: the PC's own name for the setting
     * ([Schedule.MODE_TITLE]) and its own line about where it is saved, so the
     * two controls (here and Settings) use the same words for the same value.
     */
    const val SHOWING_TITLE = Schedule.MODE_TITLE
    const val SHOWING_ON_PC = Schedule.MODE_SAVED_ON_PC

    /**
     * A PC from before the two ways existed (no `todo_modes` in its answer) has
     * ONE real behaviour, daily rollover, and no route to change it - so the
     * control is not offered at all rather than drawn as a button that cannot
     * work. The desktop hides its own control the same way, on the same marker.
     */
    const val SHOWING_FIXED = "Your PC decides how this list is shown."

    /**
     * What a screen reader is told about the choice on show - the same word
     * Home's navigation toggle uses for the same fact.
     */
    const val SHOWN = "Shown"

    /** The phone's line while the link is down or stale: rule 4, said plainly. */
    const val NOT_CONNECTED = "Not connected to the desktop, so changes wait until the link is back."

    /** The one line while App lock or "Hide memory lists and chat history" is on. */
    const val HIDDEN_WORDS = "Words hidden. Tap Show and confirm it is you."

    /**
     * The Reminders tab's rows: every job the PC lists, in the PC's order.
     *
     * The to-do items are NOT here even though they are jobs on the same
     * scheduler: the PC answers them in its own `todo` list (jarvis_schedule's
     * `listed()` leaves `kind = 'todo'` out), and they have their own tab.
     */
    fun jobs(v: Schedule.View?): List<Schedule.Job> = v?.jobs ?: emptyList()

    /**
     * The Daily to-do list tab's rows: the to-do list's own items - the ones on
     * no named list - in the PC's order. The same rows in both modes: the mode
     * changes how they are drawn, never which ones they are.
     */
    fun todoItems(v: Schedule.View?): List<Schedule.Job> = Schedule.todoItems(v)

    /** Whether the PC is showing the list day by day ([Schedule.MODE_DAY]). */
    fun isDayMode(v: Schedule.View?): Boolean = v?.todoMode == Schedule.MODE_DAY

    /**
     * The day-labelled list for the to-do list itself: the PC's own headings
     * ("Today", "Yesterday", "Friday (3d ago)", "Oct 26") over the same open
     * items, today first.
     *
     * A named list's items are grouped by the PC under their day too, and they
     * are NOT this tab's (they live in Brain), so they are filtered out here -
     * a day left with nothing is dropped rather than drawn as an empty heading.
     * While the words are hidden the headings go with them (a day label is the
     * PC's words about the owner's own items), so the visible list is one
     * unlabelled group. A PC from before the day labels sends no grouping: the
     * rollover list is then one day, so the tab still shows every item rather
     * than an empty list.
     */
    fun dayGroups(v: Schedule.View?): List<Schedule.Day> {
        if (v == null) return emptyList()
        val mine = todoItems(v)
        if (mine.isEmpty()) return emptyList()
        if (v.hidden) return listOf(Schedule.Day("", "", mine))
        val fromPc = v.todoDays.mapNotNull { day ->
            val items = day.items.filter { it.list.isEmpty() }
            if (items.isEmpty()) null else Schedule.Day(day.date, day.label, items)
        }
        return fromPc.ifEmpty { listOf(Schedule.Day("", "", mine)) }
    }

    /**
     * What a to-do row says under its words. In the rollover list that is the
     * PC's own age tag ([Schedule.carryOf]: "from yesterday", "from Friday
     * (3d ago)"), and in the day-by-day list it is "" - the heading already
     * names the day, so the same fact is not said twice.
     */
    fun itemTag(job: Schedule.Job, mode: String): String =
        if (mode == Schedule.MODE_DAY) "" else Schedule.carryOf(job)

    /**
     * The two ways of showing the list, in the PC's own words ([Schedule.todoModes]).
     * The PC sends them, so this screen cannot invent a third or rename one.
     */
    fun modeChoices(v: Schedule.View?): List<Schedule.Mode> = Schedule.todoModes(v)

    /** One choice's label, with the one in force marked - the Settings card's own words. */
    fun modeLabel(mode: Schedule.Mode, current: String): String =
        if (mode.value == current) "${mode.label} (now)" else mode.label

    /**
     * Whether the PC can be asked to change how the list is shown: true only
     * once its answer carries the two modes. On an older PC the tab says
     * [SHOWING_FIXED] and offers no button, because the one honest behaviour
     * there is rollover and there is no route to change it.
     */
    fun canChangeMode(v: Schedule.View?): Boolean = v != null && v.todoModes.isNotEmpty()

    /** The top bar's second line: how many reminders the PC listed. */
    fun countLine(n: Int): String = if (n == 1) "1 reminder" else "$n reminders"
}
