package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull

/**
 * "Coming up" - timers, alarms, reminders, the repeating ones with their
 * next time, and the to-do list (the owner's decisions of 2026-09-25;
 * docs/JARVIS-API.md section 21; backend `jarvis_schedule.py`).
 *
 * THE PC IS THE CLOCK. Every job lives on the PC and goes off there, by the
 * PC's own clock. The phone shows the list, changes one job at a time, and
 * shows a notification when the `schedule` event says a job went off - which
 * it hears only while it is connected (the foreground service keeps the
 * stream open). A reminder due while the phone is off, or out of reach of
 * the PC, is not shown on the phone until it reconnects and reads the list;
 * nothing here sets a phone alarm of its own (no exact-alarm permission is
 * asked for). Said plainly in JARVIS-API section 21. Since 2026-09-26 the
 * owner can hand an alarm to the phone's own Clock app, or a reminder to its
 * calendar, with a tap ([AlsoOnPhone]) - the Clock app then rings it, even
 * with the PC off.
 *
 * The event carries the job's id and kind only, never its words. The words
 * are read by id from `GET /api/schedule?id=` for the notification, whose
 * lock-screen version says only what KIND of thing is due
 * ([lockScreen]) - and while App lock or "Hide memory lists and chat history"
 * is on, so does the notification itself.
 *
 * Every change names ONE job - pause, resume, delete, done ([ACTIONS]) - or
 * adds ONE to-do item; there is no "delete all". None raises a card: none
 * can make Jarvis do more. Each is held on a stale link
 * ([com.jarvis.client.JarvisRuntime.scheduleAct]). A repeating reminder's
 * card is raised on the PC when it is set, by talking to Jarvis.
 *
 * The desktop says the same words (jarvis-desktop/src/coming-up.js); its
 * tests/coming-up.mjs checks this file for them.
 *
 * THE STANDBY SCHEDULE (backend `jarvis_standby_schedule.py`, 2026-09-25):
 * Standby - the same Standby as the buttons under Doing - on a timetable,
 * every day. Two times and Set up ([standbyBody]); since 2026-09-26 the PC
 * sets it up at once, with no card (the owner's decision after the
 * approvals audit). It sits in the list like any repeating job, kind "standby", where Pause
 * skips it and Delete turns it off. Its going off tells nobody: the event
 * says `"notify": false`, and [firedFrom] then shows no notification.
 *
 * SINCE 2026-09-25 (the creativity audit's everyday quick wins), in the
 * desktop's words: "Just went off" - a timer, alarm or reminder that went off
 * in the last hour, with Snooze ([SNOOZE]: a one-off copy ten minutes later
 * on the PC; a repeating one keeps its usual times; no card) and, since
 * 2026-10-13, Delete ([WENT_OFF_ACTIONS]: DEF-008 - deleting a job that has
 * already gone off works now) - also on the notification
 * ([com.jarvis.client.service.ScheduleNotifier]); and NAMED
 * lists ("shopping"), each with its items, an Add box and "Clear list",
 * which asks "are you sure?" first ([clearListQuestion]) and sends how many
 * items it showed ([clearListBody]), so nothing added since is lost. The
 * to-do list itself has no Clear.
 *
 * "TELL ME WHEN" (backend `jarvis_tellme.py`, 2026-09-25): Jarvis looks
 * every few minutes for an email from someone, or a Home Assistant device
 * doing something, and ONLY tells. Set up by saying or typing it (one card on
 * the PC); a row in the list with Pause and Delete. A match says `"state":
 * "matched"` ([matchedFrom]); the notification is the job's `alert`, made on
 * the PC from the owner's own words ("An email from Alex arrived."). An
 * alarm, and a "tell me when" marked urgent, keep ringing until seen
 * ([rings]; [com.jarvis.client.service.ScheduleNotifier]).
 *
 * Pure Kotlin, no Android types, so `ScheduleTest` runs it on a plain JVM.
 */
object Schedule {
    const val PATH = "/api/schedule"
    const val ACT_PATH = "/api/schedule/act"
    const val ADD_PATH = "/api/schedule/add"

    /** The event kind. */
    const val EVENT = "schedule"

    /** The section, both apps' words. */
    const val TITLE = "Coming up"
    const val UNDER =
        "Timers, alarms and reminders, kept on your PC. They go off on both apps " +
            "while they are connected. A repeating reminder or alarm is set up at once, with no " +
            "card; a repeating briefing or \"tell me when\" waits for your yes on an approval card."
    const val TODO_TITLE = "To-do list"

    /**
     * How the to-do list carries over (2026-11-02; the owner's choice of BOTH
     * ways, full daily rollover as the DEFAULT; Gemini's ruling 8;
     * docs/JARVIS-API.md section 179; backend `jarvis_schedule.py`).
     *
     * EVERY to-do item keeps the day it was written, for good (`created_date`,
     * written once when the item is created and never rewritten). The mode is
     * ONE value on the PC, and only changes how the same rows are drawn:
     *
     *  - [MODE_ROLLOVER] (the default): today's list is every open item written
     *    today or earlier, and each older one carries the PC's own tag:
     *    "from yesterday", "from Friday (3d ago)", "from Oct 26";
     *  - [MODE_DAY]: each item stays on the day it was written, grouped under
     *    that day's heading. Nothing is moved or lost by switching, so the
     *    toggle is lossless in both directions.
     *
     * The PC decides which, and this phone never keeps a second copy: the
     * state rides on GET /api/schedule (`todo_mode`), and the change goes
     * through [ACT_PATH] as [todoModeBody] - the SAME method a typed or spoken
     * sentence runs on the PC, so a tap here and "set the to-do list mode to
     * day by day" cannot disagree.
     */
    const val MODE_ROLLOVER = "rollover"
    const val MODE_DAY = "day"
    const val MODE_TITLE = "To-do list carry-over"
    const val MODE_DETAIL =
        "Whether yesterday's unfinished items join today's list, each one saying how old it " +
            "is, or each day keeps its own list. Nothing is moved or lost by changing it."
    const val MODE_SAVED_ON_PC = "Saved on your PC, so both apps and anything you say to Jarvis agree."

    /** Nothing on a list. */
    const val EMPTY_JOBS =
        "Nothing coming up. Say or type \"set a timer for 10 minutes\" or \"remind me at 6 to call Mum\"."
    const val EMPTY_TODO = "Nothing on your to-do list."

    /** A PC without the scheduler: a 404 or 501 on the read. */
    const val MISSING =
        "Your PC's Jarvis does not have timers and reminders yet - run apply-patches.ps1 on the PC."

    /** The buttons. */
    const val PAUSE = "Pause"
    const val RESUME = "Resume"
    const val DELETE = "Delete"
    const val DONE = "Done"
    const val ADD = "Add"
    const val ADD_HINT = "Add to the to-do list"

    /** A repeating job whose card has not been answered. */
    const val WAITING = "Waiting for your yes on the approval card."

    /** "Just went off" and Snooze - the desktop's coming-up.js, word for word. */
    const val WENT_OFF_TITLE = "Just went off"
    const val WENT_OFF_DETAIL =
        "In the last hour. Snooze sets it to go off again in 10 minutes - a repeating one keeps its " +
            "usual times."
    const val SNOOZE = "Snooze 10 minutes"

    /** How long Snooze sets (jarvis_schedule.SNOOZE_DEFAULT). */
    const val SNOOZE_SECONDS = 600

    /**
     * "+5 minutes" - the desktop HUD's one add-time action
     * (jarvis_hud.html's `{ do: "add_time", label: "+5 minutes" }`, and the
     * body it posts is `seconds: 300`). `jarvis_schedule.act()` accepts
     * add_time for a TIMER only ("Time can only be added to a timer."), in
     * both the active and paused states, so this action is offered on a
     * timer's row and nowhere else - never an action the PC refuses.
     * HUD Reminders, Brain's Coming up and this phone row say the same words
     * for it (Q2/F5, 2026-10-22).
     */
    const val ADD_TIME = "+5 minutes"
    const val ADD_TIME_SECONDS = 300

    /**
     * Under "Just went off", two buttons: Snooze and Delete - ONE job per tap.
     *
     * Delete is the same word and the same `delete` the live rows offer (both
     * the desktop's `WENT_OFF_ACTIONS` and this list feed their own
     * `labelOf`, so neither app invents a second word for one action). It is
     * here because a fired entry is one the owner can SEE: until 2026-10-13
     * the route refused it (DEF-008, `act()`'s own state gate), so the only
     * way off that row was to wait an hour. Since then
     * `jarvis_schedule.act()` routes `do == "delete"` before that gate,
     * exactly as `snooze` already was. Nothing else about the row moved: it
     * still ages out after an hour, Snooze is still 24 hours, and neither
     * asks anything first - no card and no "are you sure?", because clearing
     * an entry that has ALREADY gone off changes nothing about the future
     * (the owner's 2026-09-25 decision: a plain timer or a one-time reminder
     * needs no approval card).
     *
     * "Delete" rather than the register's own phrase "Clear this": this file
     * names this action "Delete" everywhere ([DELETE], [labelOf]), the
     * desktop's rows say the same, and "Clear" is already taken here by
     * "Clear list", which means a whole list.
     */
    val WENT_OFF_ACTIONS = listOf("snooze", "delete")

    /** A snoozed copy's tag ends with this ("alarm, snoozed"). */
    const val SNOOZED_TAG = "snoozed"

    /** Named lists ("add milk to the shopping list"). */
    const val LISTS_NOTE = "To start another list, say or type \"add milk to the shopping list\"."
    const val CLEAR_LIST = "Clear list"

    /** The phone's own two buttons under the "are you sure?" (the desktop uses its OK / Cancel). */
    const val CLEAR_YES = "Yes, clear it"
    const val CLEAR_NO = "Keep it"

    /** A named list's title while "Hide memory lists and chat history" is on. */
    const val HIDDEN_LIST_TITLE = "(hidden) list"

    /** The longest named list's name the PC keeps (jarvis_schedule.MAX_LIST_NAME). */
    const val MAX_LIST_NAME = 30

    /** Stands in for words the private lists hide. */
    const val HIDDEN_TEXT = "(hidden)"

    /**
     * Under an answer made without the model (X-Jarvis-Route `quick`) - the
     * PC's own words, word for word (jarvis_quick.DONE_LINE, coming-up.js).
     * Kept here unchanged because the desktop's tests/coming-up.mjs holds
     * this file to it. The phone shows [DONE_LINE_HERE] instead.
     */
    const val DONE_LINE = "Done - answered on this PC without the AI model."

    /**
     * [DONE_LINE] as the phone shows it. "This PC" is right on the desktop
     * and wrong on a phone, where the owner is holding something that is not
     * a PC at all (phone walk-through, 2026-09-27). Made FROM the shared
     * sentence rather than typed out again, so a change to the PC's words
     * still reaches the phone; ScheduleTest checks the swap really happened.
     */
    val DONE_LINE_HERE: String = DONE_LINE.replace("on this PC", "on your PC")

    /** The phone's line about where reminders go off. */
    const val PC_IS_THE_CLOCK =
        "They go off on your PC. This phone shows them while it is connected to it."

    /** A change the PC could not make at all (no route). */
    const val TOO_OLD = "Not changed: your PC's Jarvis does not have timers and reminders yet."

    /** A 404 that said "no such job". */
    const val ALREADY_GONE = "That is not on the list any more."

    /** The only things one job can be asked to do. Never "all", never a list. */
    val ACTIONS = listOf("pause", "resume", "delete", "done", "snooze", "add_time")

    /** The longest to-do item the PC keeps (jarvis_schedule.MAX_TEXT). */
    const val MAX_TEXT = 300

    /** The standby schedule, both apps' words (coming-up.js). */
    const val STANDBY_TITLE = "Standby schedule"
    const val REVIEW_JOB_TITLE = "Card review"
    const val STANDBY_DETAIL =
        "Jarvis goes on standby at night and wakes in the morning - but it wakes only if the " +
            "schedule put it on standby: if you chose Standby yourself, it stays on until you choose " +
            "Active. Standby unloads its models and frees the graphics card; waking loads the chat " +
            "model again, so the first answer is quick. Timers and reminders still go off. Setting " +
            "it up needs no approval card, and Delete turns it off at once."
    const val STANDBY_START_LABEL = "Standby at"
    const val STANDBY_END_LABEL = "Wake at"
    const val STANDBY_ADD = "Set up"
    const val STANDBY_IS_SET =
        "Your standby schedule is in the list above. Pause skips it and Delete turns it off. " +
            "Neither wakes Jarvis - choose Active for that."
    const val STANDBY_BAD_TIMES = "Write each time as HH:MM, like 01:00, and pick two different times."
    const val STANDBY_DEFAULT_START = "01:00"
    const val STANDBY_DEFAULT_END = "07:00"

    /** "Tell me when" - both apps' words (coming-up.js). */
    const val TELLME = "tellme"
    const val TELLME_TITLE = "Tell me when"
    const val TELLME_HINT =
        "Say or type \"tell me when an email from Alex arrives\", \"tell me when the washing " +
            "machine finishes\", \"tell me when a search for Kokoro voices shows something new\", " +
            "\"tell me when the price on https://example.com/kettle drops below 25\" or \"tell me when " +
            "CI fails on owner/repo\" - add \"urgently\" to make it ring until you look. Setting one up " +
            "asks once with an approval card; when it happens, Jarvis only tells you. If a watch stops " +
            "working, Jarvis tells you once."
    const val TELLME_LOCK_SCREEN = "Jarvis: something you asked to be told about happened."

    /**
     * A "tell me when" that cannot look (2026-09-28): all a notification says
     * while App lock or "Hide memory lists and chat history" is on, and all a
     * locked phone shows. The desktop's `TELLME_BROKEN_LOCK_SCREEN`.
     */
    const val TELLME_BROKEN_LOCK_SCREEN = "Jarvis: a \"tell me when\" cannot look right now."

    /**
     * "Remind me next time I talk about ..." (backend `jarvis_next_time.py`,
     * 2026-09-28): a reminder with no time of its own, brought up in the chat
     * when the owner's own words mention the subject - at most 3 times, a day
     * apart at least, gone after 90 days. Set by saying or typing it, no card;
     * Delete only. Never a notification. Both apps' words (coming-up.js).
     */
    const val NEXT_TIME = "nexttime"
    const val NEXT_TIME_TITLE = "Reminder for next time"
    const val NEXT_TIME_HINT =
        "Say or type \"remind me next time I talk about the dentist to ask about the bill\". " +
            "Jarvis brings it up in the chat when your own words mention it - at most 3 times, a day " +
            "apart at least - and it is gone after 90 days. No card; Delete stops it."

    /**
     * A Today card (backend jarvis_today.py, 2026-09-28): the owner's own
     * words on the Today section of Brain at a time, on chosen days
     * ([Today]). Its row here is like a repeating reminder's: Pause skips it,
     * Delete removes it. It never notifies. Both apps' words (coming-up.js).
     */
    const val TODAY_CARD = "today"
    const val TODAY_CARD_TITLE = "Today card"

    /** The line naming the subject: `When you talk about "the dentist"`. */
    fun nextTimeAbout(about: String): String = "When you talk about \u201c$about\u201d"

    /** A notification's title, by kind. The desktop's toast says the same. */
    fun title(kind: String): String = when (kind) {
        "timer" -> "Timer done"
        "alarm" -> "Alarm"
        "reminder" -> "Reminder"
        "todo" -> "To-do"
        Briefing.KIND -> Briefing.TITLE
        TELLME -> TELLME_TITLE
        else -> "Jarvis"
    }

    /** What a locked screen may show, by kind, when the PC did not say. */
    fun lockScreen(kind: String): String = when (kind) {
        "timer" -> "Jarvis: your timer is done."
        "alarm" -> "Jarvis: alarm."
        "reminder" -> "Jarvis: a reminder is due."
        "todo" -> "Jarvis: a to-do item is due."
        Briefing.KIND -> Briefing.LOCK_SCREEN
        TELLME -> TELLME_LOCK_SCREEN
        else -> "Jarvis: something is due."
    }

    /** The tag on a row, by kind. */
    fun tag(kind: String): String = when (kind) {
        "todo" -> "to-do"
        TELLME -> "tell me when"
        // Goals' own weekly check-in (backend jarvis_goals.KIND) - the
        // literal is repeated rather than imported, so this file (which
        // Goals.kt itself depends on for [job] and [Job]) never depends
        // back on Goals.kt.
        "goal_checkin" -> "goal check-in"
        NEXT_TIME -> "next time"
        TODAY_CARD -> "today card"
        // Review decks' own daily job (backend jarvis_decks.KIND): named plainly.
        "review" -> "card review"
        else -> kind
    }

    /**
     * A row's tag (coming-up.js tagOf): its kind, then "urgent" for an urgent
     * "tell me when", "snoozed" for a snoozed copy, or "repeats":
     * "tell me when, urgent", "alarm, snoozed", "reminder, repeats".
     */
    fun tagOf(job: Job): String = when {
        job.kind == TELLME -> if (job.urgent) "${tag(job.kind)}, urgent" else tag(job.kind)
        job.snoozed -> "${tag(job.kind)}, $SNOOZED_TAG"
        job.repeats -> "${tag(job.kind)}, repeats"
        else -> tag(job.kind)
    }

    /**
     * Whether it keeps ringing until it is seen: an alarm going off, and a
     * "tell me when" the owner marked urgent. The desktop's `rings` says the same.
     */
    fun rings(kind: String, urgent: Boolean): Boolean = kind == "alarm" || (kind == TELLME && urgent)

    private val ID = Regex("s[0-9a-f]{10}")

    /** A job id as the PC makes them. */
    fun validId(id: String?): Boolean = id != null && ID.matches(id)

    data class Job(
        val id: String,
        val kind: String,
        val text: String,
        val state: String,
        val due: Double?,
        val left: Double?,
        val duration: Double?,
        val whenWords: String,
        val repeats: Boolean,
        val repeat: String,
        val missed: String,
        val hidden: Boolean,
        val lockScreen: String,
        val firedAt: Double?,
        /** How a kind's last run went, in the PC's words (the standby schedule's). */
        val note: String = "",
        /** A to-do item's named list ("shopping"); "" is the to-do list itself. */
        val list: String = "",
        /** A snoozed copy of something that went off. */
        val snoozed: Boolean = false,
        /** When it went off, by the PC's clock ("07:00"); "" if it has not. */
        val wentOffAt: String = "",
        /** A "tell me when" marked urgent. */
        val urgent: Boolean = false,
        /** A "tell me when"'s notice, once it happened ("An email from Alex arrived."). */
        val alert: String = "",
        /** When that happened (epoch seconds) - one notification per match. */
        val alertAt: Double? = null,
        /**
         * A "tell me when" that cannot look (2026-09-28): the PC's notice, made
         * from the owner's own words and fixed words about the problem - ""
         * when it is working.
         */
        val broken: String = "",
        /** When the PC told the owner so (epoch seconds) - one notification per telling. */
        val brokenAt: Double? = null,
        /**
         * A repeating job's rule, as the PC keeps it (jarvis_schedule's
         * `rule`): "day", "weekday", "week" or "hours"; its "HH:MM"; and for
         * "week" the days, 0 = Monday. For "Also on my phone" ([AlsoOnPhone]).
         */
        val ruleEvery: String = "",
        val ruleAt: String = "",
        val ruleDays: List<Int> = emptyList(),
        /** A reminder for next time's subject ("the dentist") - the owner's words. */
        val about: String = "",
        /**
         * A Today card (2026-09-28): whether it shows today - "showing",
         * "later" or "" - and from when ("07:00"), by the PC's own clock.
         */
        val today: String = "",
        val showsAt: String = "",
        /** Seconds since it went off, by the PC's clock (backend jarvis_schedule.py). */
        val ageSeconds: Double? = null,
        /**
         * The day a TO-DO item was written, "YYYY-MM-DD" in the PC's local
         * time (2026-11-02). Written once, when the item is created, and never
         * rewritten - so it is the same in both modes and through any number
         * of switches. "" on every other kind and on an older PC.
         */
        val createdDate: String = "",
        /**
         * How old that is, in the PC's OWN words: "from yesterday", "from
         * Friday (3d ago)", "from Oct 26" - "" for an item written today.
         * Computed on the PC (`jarvis_schedule.carry_words`): a phone whose
         * clock is a day out must never decide an item's age for itself.
         */
        val carry: String = "",
        /**
         * The question this reminder asks when it goes off (2026-11-02), or
         * null for every reminder that does not. Drawn on the notification as
         * the body and on the row as its buttons; the PC reads back the answer.
         */
        val ask: Ask? = null,
        /** The answers already given, oldest first - the PC's own log. */
        val answers: List<Answer> = emptyList(),
        /**
         * The PC said it can take an ANSWER for this job (`asks: true`). A
         * backend from before 2026-11-02 never says it and has no `answer`
         * verb, so no button is drawn rather than one that cannot work.
         */
        val asks: Boolean = false,
    )

    /** A named list: its name as the PC keeps it, its title, how many open items. */
    data class NamedList(val name: String, val title: String, val open: Int)

    data class View(
        val jobs: List<Job>,
        val todo: List<Job>,
        val hidden: Boolean,
        /** What went off in the last hour (an older PC sends none). */
        val wentOff: List<Job> = emptyList(),
        val lists: List<NamedList> = emptyList(),
        /**
         * How the to-do list carries over (2026-11-02): [MODE_ROLLOVER] (the
         * default, and what an older PC that sends no key really does) or
         * [MODE_DAY].
         */
        val todoMode: String = MODE_ROLLOVER,
        /** The two modes in the PC's own words, for the Settings switch. */
        val todoModes: List<Mode> = emptyList(),
        /** The open items grouped by the day they were written, today first. */
        val todoDays: List<Day> = emptyList(),
    )

    /** One of the two ways to show the to-do list, in the PC's own words. */
    data class Mode(val value: String, val label: String, val detail: String = "")

    /**
     * A reminder that ASKS (2026-11-02, the owner's request: *"a notification on
     * my Android phone saying 'Did you take your medication?' with a Yes or No
     * button"*, and then *"as much flexibility or options as I want"*).
     *
     * The PC keeps it, this phone draws it: the question as the notification's
     * body and each button as one notification action, in the owner's own words.
     * Pressing one is a LOG, not an approval - no card anywhere, like ticking a
     * to-do item - and the three-button ceiling is Android's own ([MAX_ASK]).
     */
    data class Ask(
        val question: String,
        val buttons: List<AskButton>,
        val record: AskRecord = AskRecord(),
    )

    /**
     * ONE of the owner's buttons: his words, and the one thing it does.
     * [minutes] is set only for [ASK_SNOOZE], because only a snooze has a time.
     */
    data class AskButton(val label: String, val does: String, val minutes: Int = 0)

    /**
     * Where a `record` button writes, as the PC keeps it. Any combination; an
     * empty one is impossible on an `ask` reminder whose buttons include a
     * `record` button, because the PC refuses to save it.
     */
    data class AskRecord(
        val history: Boolean = false,
        val obsidianDaily: Boolean = false,
        val goal: String = "",
        val habit: String = "",
    )

    /**
     * One answer already given, as the PC logged it: its own clock ("10:00"),
     * the label that was pressed, what that button did, and what was written.
     * Never computed here - a phone whose clock is a day out must not date the
     * owner's own answer.
     */
    data class Answer(
        val clock: String,
        val button: String,
        val does: String,
        val wrote: List<String> = emptyList(),
    )

    /**
     * One day of the day-labelled list: its "YYYY-MM-DD", the PC's heading for
     * it ("Today", "Yesterday", "Friday (3d ago)", "Oct 26"), and the open
     * items written that day - the SAME items the rollover list draws, so no
     * item is ever sent or shown twice.
     */
    data class Day(val date: String, val label: String, val items: List<Job>)

    /** One job, read - or null when it has no id the PC makes. */
    fun job(o: JsonObject): Job? {
        val id = o.text("id") ?: return null
        if (!validId(id)) return null
        val rule = o["rule"] as? JsonObject
        return Job(
            id = id,
            kind = o.text("kind") ?: "",
            text = o.text("text") ?: "",
            state = o.text("state") ?: "",
            due = o.num("due"),
            left = o.num("left"),
            duration = o.num("duration"),
            whenWords = o.text("when") ?: "",
            repeats = o.flag("repeats") == true,
            repeat = o.text("repeat") ?: "",
            missed = o.text("missed") ?: "",
            hidden = o.flag("hidden") == true,
            lockScreen = o.text("lock_screen") ?: "",
            firedAt = o.num("fired_at"),
            note = o.text("note") ?: "",
            list = o.text("list") ?: "",
            snoozed = o.flag("snoozed") == true,
            wentOffAt = o.text("went_off_at") ?: "",
            urgent = o.flag("urgent") == true,
            alert = o.text("alert") ?: "",
            alertAt = o.num("alert_at"),
            broken = o.text("broken") ?: "",
            brokenAt = o.num("broken_at"),
            ruleEvery = rule?.text("every") ?: "",
            ruleAt = rule?.text("at") ?: "",
            ruleDays = (rule?.get("days") as? JsonArray)?.mapNotNull { d ->
                (d as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull?.toInt()
            } ?: emptyList(),
            about = o.text("about") ?: "",
            today = o.text("today") ?: "",
            showsAt = o.text("shows_at") ?: "",
            ageSeconds = o.num("age_s"),
            createdDate = o.text("created_date") ?: "",
            carry = o.text("carry") ?: "",
            ask = ask(o["action"] as? JsonObject),
            answers = answers(o["answers"] as? JsonArray),
            asks = o.flag("asks") == true,
        )
    }

    /**
     * The `ask` block a reminder carries, or null for every other kind - and for
     * an `ask` block this phone cannot draw honestly (no question, no usable
     * button). That is the same direction the PC's own read takes: a shape it
     * cannot use is dropped rather than half-drawn.
     */
    fun ask(o: JsonObject?): Ask? {
        if (o?.text("kind") != "ask") return null
        val question = o.text("question").orEmpty()
        if (question.isEmpty()) return null
        val buttons = (o["buttons"] as? JsonArray)?.mapNotNull { el ->
            val b = el as? JsonObject ?: return@mapNotNull null
            val label = b.text("label").orEmpty()
            val does = b.text("does").orEmpty()
            if (label.isEmpty() || does !in ASK_DOES) return@mapNotNull null
            val minutes = b.num("minutes")?.toInt() ?: 0
            if (does == ASK_SNOOZE && minutes !in 1..MAX_ASK_MINUTES) return@mapNotNull null
            AskButton(label, does, if (does == ASK_SNOOZE) minutes else 0)
        }?.take(MAX_ASK) ?: emptyList()
        if (buttons.isEmpty()) return null
        val record = o["record"] as? JsonObject
        return Ask(
            question = question,
            buttons = buttons,
            record = AskRecord(
                history = record?.flag("history") == true,
                obsidianDaily = record?.flag("obsidian_daily") == true,
                goal = record?.text("goal").orEmpty(),
                habit = record?.text("habit").orEmpty(),
            ),
        )
    }

    /** The answers the PC logged, oldest first - never a shape this phone invents. */
    fun answers(list: JsonArray?): List<Answer> =
        list?.mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val button = o.text("button") ?: return@mapNotNull null
            Answer(
                clock = o.text("clock").orEmpty(),
                button = button,
                does = o.text("does").orEmpty(),
                wrote = (o["wrote"] as? JsonArray)?.mapNotNull { w ->
                    (w as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
                } ?: emptyList(),
            )
        } ?: emptyList()

    /**
     * The body of ONE answer: one job id and the button's INDEX - never its
     * label (so a re-worded button cannot be answered by accident) and never a
     * target of any kind. The PC checks everything again. Null when it could not
     * be one button of one job.
     */
    fun answerBody(id: String, index: Int): String? {
        if (!validId(id) || index < 0 || index >= MAX_ASK) return null
        return "{\"id\":\"$id\",\"do\":\"answer\",\"button\":$index}"
    }

    /** `GET /api/schedule`, read - or null when it is not the list. */
    fun parse(body: JsonObject): View? {
        val jobs = body["jobs"] as? JsonArray ?: return null
        val todo = body["todo"] as? JsonArray ?: return null
        val todoJobs = todo.mapNotNull { (it as? JsonObject)?.let(::job) }
        val byId = todoJobs.associateBy { it.id }
        // The day-labelled view is the SAME rows, grouped: its entries name the
        // items by id and this resolves them here, so an item is never held
        // twice and an id this phone cannot see is simply not shown.
        val days = (body["todo_days"] as? JsonArray)?.mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val date = o.text("date") ?: return@mapNotNull null
            val ids = (o["items"] as? JsonArray)?.mapNotNull { x ->
                (x as? JsonPrimitive)?.contentOrNull
            } ?: emptyList()
            val items = ids.mapNotNull { byId[it] }
            if (items.isEmpty()) null else Day(date, o.text("label") ?: date, items)
        } ?: emptyList()
        return View(
            jobs = jobs.mapNotNull { (it as? JsonObject)?.let(::job) },
            todo = todoJobs,
            todoDays = days,
            hidden = body.flag("hidden") == true,
            wentOff = (body["went_off"] as? JsonArray)?.mapNotNull { (it as? JsonObject)?.let(::job) }
                ?: emptyList(),
            todoMode = (body.text("todo_mode") ?: MODE_ROLLOVER).let {
                if (it == MODE_DAY) MODE_DAY else MODE_ROLLOVER
            },
            todoModes = (body["todo_modes"] as? JsonArray)?.mapNotNull { el ->
                val o = el as? JsonObject ?: return@mapNotNull null
                val value = o.text("value") ?: return@mapNotNull null
                if (value != MODE_ROLLOVER && value != MODE_DAY) return@mapNotNull null
                Mode(value, o.text("label") ?: value, o.text("detail") ?: "")
            } ?: emptyList(),
            lists = (body["lists"] as? JsonArray)?.mapNotNull { el ->
                val o = el as? JsonObject ?: return@mapNotNull null
                val name = o.text("name") ?: return@mapNotNull null
                val open = o.num("open")?.toInt() ?: return@mapNotNull null
                if (open <= 0) null else NamedList(name, o.text("title") ?: name, open)
            } ?: emptyList(),
        )
    }

    /** `GET /api/schedule?id=` - the `job` in it. */
    fun parseOne(body: JsonObject): Job? = (body["job"] as? JsonObject)?.let(::job)

    /** A read that failed because this PC has no scheduler: a 404 or a 501. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || (error is ApiError.Server && error.code == 501)

    /**
     * The list with every job's words replaced, for while the lists are
     * hidden. A named list's name is the owner's words too: each becomes
     * "hidden-1", "hidden-2"..., the same on its items, so they still group -
     * the desktop's Rust does the same (brain/schedule.rs redact_list).
     */
    fun hide(v: View): View {
        val names = mutableListOf<String>()
        fun standIn(name: String): String {
            if (name.isEmpty()) return ""
            var i = names.indexOf(name)
            if (i < 0) {
                names += name
                i = names.size - 1
            }
            return "hidden-${i + 1}"
        }
        return View(
            jobs = v.jobs.map { it.copy(text = "", alert = "", broken = "", about = "", hidden = true) },
            todo = v.todo.map {
                it.copy(text = "", alert = "", broken = "", about = "", hidden = true, list = standIn(it.list))
            },
            hidden = true,
            wentOff = v.wentOff.map { it.copy(text = "", alert = "", broken = "", about = "", hidden = true) },
            lists = v.lists.map { it.copy(name = standIn(it.name), title = "") },
            // The day headings are the PC's own words ("Friday (3d ago)"), and
            // an item's words are blanked here: while the lists are hidden there
            // is no age to show, so no tag and no heading is kept.
            todoMode = v.todoMode,
            todoModes = v.todoModes,
        )
    }

    /**
     * The tag under one to-do item, in the PC's words: "from yesterday", "from
     * Friday (3d ago)", "from Oct 26" - or "" for an item written today, for
     * any other kind, and while the private lists are hidden (an age is a fact
     * about words that are gone).
     *
     * This does NOT work an age out from the phone's clock: the PC wrote the
     * item and the PC says how old it is. The desktop's coming-up.js carryOf()
     * says the same thing.
     */
    fun carryOf(job: Job?): String {
        if (job == null || job.hidden || job.kind != "todo") return ""
        return job.carry
    }

    /**
     * The day-labelled list, for [MODE_DAY]: [{date, label, items}] today
     * first, the items themselves (not ids). A PC from before this feature
     * sends no grouping - the rollover list is then ONE day, so the screen
     * still shows every open item rather than an empty list.
     */
    fun todoDays(v: View?): List<Day> {
        if (v == null) return emptyList()
        val byId = v.todo.associateBy { it.id }
        val days = v.todoDays.mapNotNull { d ->
            val items = d.items.mapNotNull { byId[it.id] }
            if (items.isEmpty()) null else Day(d.date, d.label, items)
        }
        if (days.isNotEmpty()) return days
        val all = todoItems(v)
        return if (all.isEmpty()) emptyList() else listOf(Day("", "", all))
    }

    /** The two modes, the PC's words first - a plain fallback if it sent none. */
    fun todoModes(v: View?): List<Mode> {
        val modes = v?.todoModes ?: emptyList()
        if (modes.isNotEmpty()) return modes
        return listOf(
            Mode(MODE_ROLLOVER, "Daily rollover"),
            Mode(MODE_DAY, "Day by day"),
        )
    }

    /**
     * The body that changes the mode: one verb and one mode, nothing else - or
     * null when it is not one of the two. It rides [ACT_PATH] deliberately:
     * that is the scheduler's ONE write door for changes that need no card (the
     * `clear_list` form already lives there), and the PC's `handle_act` takes
     * `{"do": "todo_mode"}` as its second non-job form.
     */
    fun todoModeBody(mode: String): String? {
        if (mode != MODE_ROLLOVER && mode != MODE_DAY) return null
        return "{\"do\":\"todo_mode\",\"mode\":\"$mode\"}"
    }

    /** The to-do list's own items: those on no named list. */
    fun todoItems(v: View?): List<Job> = v?.todo?.filter { it.list.isEmpty() } ?: emptyList()

    /** A named list with its items, as shown. */
    data class ListPart(val name: String, val title: String, val items: List<Job>)

    /** The named lists with their items, in the PC's order; an empty one is not shown. */
    fun namedLists(v: View?): List<ListPart> {
        if (v == null) return emptyList()
        return v.lists.map { l ->
            ListPart(l.name, if (v.hidden) HIDDEN_LIST_TITLE else l.title, v.todo.filter { it.list == l.name })
        }.filter { it.items.isNotEmpty() }
    }

    private fun lowerFirst(s: String) = s.replaceFirstChar { it.lowercaseChar() }

    /** "Add to the shopping list" - the Add box's words under each list. */
    fun addPlaceholder(title: String): String = "Add to the " + lowerFirst(title.ifEmpty { TODO_TITLE })

    /** The "are you sure?" before Clear list - the desktop's words. */
    fun clearListQuestion(title: String, count: Int): String =
        "Clear the ${lowerFirst(title)}? This deletes all $count item" +
            (if (count == 1) "" else "s") + " on it, and cannot be undone."

    /** The line under something that went off: "Went off at 07:00". */
    fun wentOffMeta(job: Job): List<String> {
        val out = mutableListOf<String>()
        if (job.wentOffAt.isNotEmpty()) {
            out += "Went off at ${job.wentOffAt}" +
                if (job.missed.isNotEmpty()) " (late - the PC was off or asleep)" else ""
        }
        if (job.repeats && job.repeat.isNotEmpty()) out += job.repeat
        return out
    }

    /** 600 -> "10 minutes" (jarvis_schedule.length_words). */
    fun lengthWords(seconds: Double): String {
        val s = Math.round(maxOf(0.0, seconds)).toInt()
        val h = s / 3600
        val m = (s % 3600) / 60
        val sec = s % 60
        val parts = mutableListOf<String>()
        if (h > 0) parts += "$h hour" + if (h != 1) "s" else ""
        if (m > 0) parts += "$m minute" + if (m != 1) "s" else ""
        if (sec > 0 && h == 0) parts += "$sec second" + if (sec != 1) "s" else ""
        return if (parts.isEmpty()) "0 seconds" else parts.joinToString(" ")
    }

    /** 598 -> "9:58", 3723 -> "1:02:03". */
    fun countdown(seconds: Double): String {
        val s = Math.ceil(maxOf(0.0, seconds)).toInt()
        val h = s / 3600
        val m = (s % 3600) / 60
        val sec = s % 60
        fun two(n: Int) = n.toString().padStart(2, '0')
        return if (h > 0) "$h:${two(m)}:${two(sec)}" else "$m:${two(sec)}"
    }

    /** Seconds left on a timer now, from what the PC said [sinceMs] ago. */
    fun leftNow(job: Job, sinceMs: Long): Double? {
        val left = job.left ?: return null
        if (job.state != "active") return left
        return maxOf(0.0, left - maxOf(0L, sinceMs) / 1000.0)
    }

    /** A row's title: the owner's words, or what kind of thing it is. */
    fun titleOf(job: Job): String {
        if (job.kind == "standby") return STANDBY_TITLE
        // Review decks' daily job has no words of its own; its note is the meta line.
        if (job.kind == "review") return REVIEW_JOB_TITLE
        val words = if (job.hidden) HIDDEN_TEXT else job.text
        if (job.kind == "timer") {
            return if (words.isNotEmpty()) "$words timer" else lengthWords(job.duration ?: 0.0) + " timer"
        }
        // A morning briefing has no words of its own (Briefing.kt).
        if (job.kind == Briefing.KIND) return Briefing.TITLE
        // "When an email from Alex arrives" - what is watched, in the owner's words.
        if (job.kind == TELLME) return if (job.hidden || words.isEmpty()) TELLME_TITLE else "When $words"
        if (job.kind == NEXT_TIME) return if (job.hidden || words.isEmpty()) NEXT_TIME_TITLE else words
        if (job.kind == TODAY_CARD) return if (job.hidden || words.isEmpty()) TODAY_CARD_TITLE else words
        if (words.isNotEmpty()) return words
        return when (job.kind) {
            "alarm" -> "Alarm"
            "todo" -> "To-do"
            else -> "Reminder"
        }
    }

    /** The lines under a row's title - the desktop's metaOf, word for word. */
    fun metaOf(job: Job, sinceMs: Long = 0L, carry: String = ""): List<String> {
        val out = mutableListOf<String>()
        if (job.state == "waiting") {
            if (job.repeat.isNotEmpty()) out += job.repeat
            out += WAITING
            return out
        }
        if (job.kind == "timer") {
            val left = leftNow(job, sinceMs) ?: 0.0
            out += if (job.state == "paused") "Paused - ${countdown(left)} left" else "${countdown(left)} left"
            return out
        }
        if (job.kind == NEXT_TIME) {
            // The subject (never while hidden), until when, and a count.
            if (!job.hidden && job.about.isNotEmpty()) out += nextTimeAbout(job.about)
            if (job.whenWords.isNotEmpty()) out += job.whenWords
            if (job.note.isNotEmpty()) out += job.note
            return out
        }
        if (job.kind == TELLME) {
            // How often it looks and the PC's line - not the next look's time.
            if (job.repeat.isNotEmpty()) out += "Looks ${job.repeat}"
            if (job.state == "paused") out += "Paused"
            if (job.note.isNotEmpty()) out += job.note
            return out
        }
        if (job.repeats && job.repeat.isNotEmpty()) out += job.repeat
        // A to-do's own age, in the PC's words (2026-11-02). Only in the
        // rollover list: the day-labelled view puts the day on the group's
        // heading instead, so the same fact is not said twice.
        if (carry.isNotEmpty() && job.kind == "todo") out += carry
        if (job.state == "paused") {
            out += "Paused"
        } else if (job.whenWords.isNotEmpty()) {
            out += if (job.repeats) "next: ${job.whenWords}" else job.whenWords
        }
        if (job.missed.isNotEmpty()) out += "Went off late (${job.missed}) - the PC was off or asleep."
        if (job.note.isNotEmpty()) out += job.note
        return out
    }

    /** The standby schedule on the list, or null. There is only ever one. */
    fun standbyOf(v: View?): Job? = v?.jobs?.firstOrNull { it.kind == "standby" }

    private val HHMM = Regex("([01]?\\d|2[0-3]):([0-5]\\d)")

    /**
     * The two times for a new standby schedule, tidied to HH:MM, or null when
     * either is not a time of day or they are the same - coming-up.js
     * standbyTimes, and the PC checks the same.
     */
    fun standbyTimes(start: String, end: String): Pair<String, String>? {
        fun tidy(v: String): String? {
            val m = HHMM.matchEntire(v.trim()) ?: return null
            return m.groupValues[1].padStart(2, '0') + ":" + m.groupValues[2]
        }
        val at = tidy(start) ?: return null
        val until = tidy(end) ?: return null
        return if (at == until) null else at to until
    }

    /** The body of a new standby schedule, or null when the times cannot be one. */
    fun standbyBody(start: String, end: String): String? {
        val (at, until) = standbyTimes(start, end) ?: return null
        return "{\"kind\":\"standby\",\"repeat\":{\"every\":\"day\",\"at\":\"$at\",\"until\":\"$until\"}}"
    }

    /**
     * The buttons one row offers, as action names, in order. Never "all".
     *
     * A goal's own weekly check-in ("goal_checkin") offers NONE: pausing or
     * deleting it here, directly, would leave the goal itself `active` with
     * no way to bring the check-in back (Goals has no route that
     * re-creates one for an existing goal - see net/Goals.kt's own doc
     * comment). Stop tracking, on the goal itself, is the one control that
     * takes both down together.
     */
    fun actionsOf(job: Job): List<String> = when {
        job.kind == "goal_checkin" -> emptyList()
        // The review decks' daily job: Decks owns it and removes it with the last deck.
        job.kind == "review" -> emptyList()
        job.kind == "todo" -> listOf("done", "delete")
        job.state == "waiting" -> listOf("delete")
        // A reminder for next time has no time of its own to pause.
        job.kind == NEXT_TIME -> listOf("delete")
        // add_time is a timer's alone (jarvis_schedule.act), in both
        // its active and paused states - the HUD draws it on the same row.
        job.kind == "timer" -> when (job.state) {
            "paused" -> listOf("add_time", "resume", "delete")
            else -> listOf("add_time", "pause", "delete")
        }
        job.state == "paused" -> listOf("resume", "delete")
        else -> listOf("pause", "delete")
    }

    fun labelOf(action: String): String = when (action) {
        "pause" -> PAUSE
        "resume" -> RESUME
        "delete" -> DELETE
        "done" -> DONE
        "snooze" -> SNOOZE
        "add_time" -> ADD_TIME
        else -> action
    }

    /** Is anything counting down (worth a once-a-second redraw)? */
    fun anyTicking(v: View?): Boolean = v?.jobs?.any { it.kind == "timer" && it.state == "active" } == true

    /**
     * The body of one change: one id, one action - or null when it is not
     * one. Snooze says how long: ten minutes, as the button says; add_time
     * says five minutes, exactly as the HUD's button says.
     */
    fun actBody(id: String, action: String): String? {
        if (!validId(id) || action !in ACTIONS) return null
        if (action == "snooze") return "{\"id\":\"$id\",\"do\":\"snooze\",\"seconds\":$SNOOZE_SECONDS}"
        if (action == "add_time") return "{\"id\":\"$id\",\"do\":\"add_time\",\"seconds\":$ADD_TIME_SECONDS}"
        return "{\"id\":\"$id\",\"do\":\"$action\"}"
    }

    private val LIST_WORD = Regex("[a-z][a-z'-]*")

    /**
     * A named list's name as the PC keeps it ("shopping"): lower case, one to
     * three plain words - or null. The PC checks the same, and says why.
     */
    fun listName(v: String): String? {
        val t = v.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")
        val words = t.split(" ")
        if (t.isEmpty() || t.length > MAX_LIST_NAME || words.size > 3) return null
        return if (words.all { LIST_WORD.matches(it) }) t else null
    }

    /**
     * The body of one new to-do item, tidied - on a named list when [list]
     * says one - or null when it cannot be one.
     */
    fun todoBody(text: String, list: String? = null): String? {
        val t = text.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")
        if (t.isEmpty() || t.length > MAX_TEXT) return null
        val words = JarvisJson.encodeToString(kotlinx.serialization.serializer<String>(), t)
        if (list == null) return "{\"kind\":\"todo\",\"text\":$words}"
        val name = listName(list) ?: return null
        return "{\"kind\":\"todo\",\"text\":$words,\"list\":\"$name\"}"
    }

    /**
     * The body that clears ONE named list: its name and how many items this
     * phone showed (the PC clears nothing if that is no longer right). Never
     * the to-do list, never "all" - or null.
     */
    fun clearListBody(list: String, count: Int): String? {
        val name = listName(list) ?: return null
        if (count <= 0) return null
        return "{\"do\":\"clear_list\",\"list\":\"$name\",\"count\":$count}"
    }

    /** What the PC answered a change, kept whole. */
    data class Reply(val code: Int, val body: JsonObject?)

    /** Whether it changed, and the sentence to show. */
    fun said(reply: Reply): Pair<Boolean, String> {
        val b = reply.body
        val error = b?.text("error")
        return when {
            reply.code in 200..299 -> if (b?.flag("ok") == false) {
                false to (error ?: "Not changed.")
            } else {
                true to (b?.text("said") ?: if ((b?.get("job") as? JsonObject)?.flag("already") == true) {
                    "That is already on your to-do list."
                } else if (b?.get("job") != null) {
                    "Added to your to-do list."
                } else {
                    "Done."
                })
            }
            reply.code == 404 && b?.text("reason") == "no_such_job" -> true to ALREADY_GONE
            reply.code == 404 || reply.code == 501 -> false to TOO_OLD
            else -> false to (error ?: "Not changed. Your PC answered ${reply.code}.")
        }
    }

    /**
     * (title, text) of the notification for a job that went off. [private]:
     * App lock or "Hide memory lists and chat history" is on - then the text
     * is the kind's lock-screen words, never the job's own. The desktop's
     * toast does the same (brain/schedule.rs toast_words).
     */
    fun notification(kind: String, job: Job?, private: Boolean): Pair<String, String> {
        val title = title(kind)
        // A question is what the notice SAYS when the reminder asks one
        // (2026-11-02): the reminder's own text is what it is about, the
        // question is what the owner reads. While the words are hidden the
        // generic line is used, exactly as for every other kind.
        val asking = job?.ask
        // While the words are hidden (App lock or "Hide memory lists"), a
        // question shows this generic line - it names the KIND of thing that is
        // waiting and never a word of the question, which is the owner's own
        // words about his own life. The PC's own lock-screen line would do; this
        // one is truer for a question and leaks exactly as little.
        val fallback = if (asking != null) ASK_ON_LOCK_SCREEN
        else job?.lockScreen?.takeIf { it.isNotEmpty() } ?: lockScreen(kind)
        if (job == null || private) return title to fallback
        if (asking != null) return title to asking.question
        // A "tell me when" says its alert - made on the PC from the owner's
        // words - never its text, which is what is watched.
        val words = (if (kind == TELLME) job.alert else job.text).trim()
        var text = when {
            words.isEmpty() -> fallback
            kind == "timer" -> "The $words timer is done."
            else -> words
        }
        if (job.missed.isNotEmpty()) text += " (${job.missed} - the PC was off or asleep.)"
        return title to text
    }

    /**
     * From a `schedule` event: (id, kind) when a job went off that the owner
     * should hear about, else null. `"notify": false` - the standby schedule
     * at 01:00 - is nothing to show.
     */
    fun firedFrom(data: JsonObject?): Pair<String, String>? {
        if (data == null || data.text("state") != "fired") return null
        if (data.flag("notify") == false) return null
        val id = data.text("id")?.takeIf { validId(it) } ?: return null
        return id to (data.text("kind") ?: "")
    }

    /**
     * From a `schedule` event: (id, urgent) when a "tell me when" matched,
     * else null. It carries no words; the alert is read by id.
     */
    fun matchedFrom(data: JsonObject?): Pair<String, Boolean>? {
        if (data == null || data.text("state") != "matched" || data.text("kind") != TELLME) return null
        val id = data.text("id")?.takeIf { validId(it) } ?: return null
        return id to (data.flag("urgent") == true)
    }

    /**
     * From a `schedule` event: the id when a "tell me when" cannot look
     * (2026-09-28), else null. It carries no words; the notice is read by id.
     */
    fun brokenFrom(data: JsonObject?): String? {
        if (data == null || data.text("state") != "broken" || data.text("kind") != TELLME) return null
        return data.text("id")?.takeIf { validId(it) }
    }

    /**
     * (title, text) of the notification for a "tell me when" that cannot
     * look: the job's `broken` notice, or only [TELLME_BROKEN_LOCK_SCREEN]
     * while [private] or when there is none. The desktop's `broken_words`.
     */
    fun brokenNotification(job: Job?, private: Boolean): Pair<String, String> {
        val words = job?.broken?.trim().orEmpty()
        return TELLME_TITLE to (if (private || words.isEmpty()) TELLME_BROKEN_LOCK_SCREEN else words)
    }

    /**
     * From a `schedule` event: (id, kind) when the PC says a job CHANGED
     * (snoozed, deleted, done, paused - on the PC, by voice, or in Coming
     * up), else null. A ringing notification for it is then taken away (bug
     * audit 2026-09-26, #1): it was answered somewhere else.
     */
    fun changedFrom(data: JsonObject?): Pair<String, String?>? {
        if (data == null || data.text("state") != "changed") return null
        val id = data.text("id")?.takeIf { validId(it) } ?: return null
        return id to data.text("kind")
    }

    /**
     * Whether a changed job's notification should go: a timer, alarm or
     * reminder that went off. Never a "tell me when" match - its job ends
     * (a `changed` event) the moment it matched to tell only once, and its
     * notification must stay until it is seen.
     */
    fun cancelsOnChange(kind: String?): Boolean = kind == null || kind in SNOOZABLE

    /** The kinds a Snooze moves (jarvis_schedule.SNOOZABLE). */
    val SNOOZABLE = setOf("timer", "alarm", "reminder")

    // ---- a reminder that ASKS (2026-11-02) ---------------------------------

    /**
     * The three things one of the owner's buttons may do
     * (`jarvis_schedule.ASK_DOES`). Anything else is dropped from the answer's
     * buttons, so no button that cannot be sent is ever drawn.
     */
    val ASK_DOES = setOf("record", "done", "snooze")

    /** The one verb that carries minutes. */
    const val ASK_SNOOZE = "snooze"

    /**
     * The most buttons one question may have. THREE is Android's own ceiling on
     * a notification's actions, and the PC enforces the same number
     * (`jarvis_schedule.MAX_ASK_BUTTONS`): four buttons would be one the phone
     * silently cannot draw.
     */
    const val MAX_ASK = 3

    /** The longest and shortest a snooze button may be, in minutes. */
    const val MAX_ASK_MINUTES = 1440

    /**
     * The one line a locked phone may show for a question, when the notification
     * privacy setting hides the words. The answer itself writes a personal
     * record, so it is only taken with the phone unlocked - the same rule the
     * approval envelope keeps for Approve, without pretending an answer is an
     * approval.
     */
    const val ASK_ON_LOCK_SCREEN = "Jarvis: something you asked yourself about is due."

    /**
     * How late (seconds after it went off) the phone may still ring for a job
     * it hears about. Later - it was out of reach, or restarted - it shows a
     * silent "Missed at HH:MM." notice instead (the owner's decision of
     * 2026-09-26). The desktop's `LATE_RING_LIMIT_S`.
     */
    const val LATE_RING_LIMIT_S = 10 * 60

    /**
     * Whether a job that went off at [firedAt] (seconds) or with [ageSeconds]
     * is heard too late to ring at [nowS]. When [ageSeconds] is provided by
     * the PC, it is preferred to avoid clock skew.
     */
    fun heardLate(firedAt: Double?, nowS: Double, ageSeconds: Double? = null): Boolean {
        if (ageSeconds != null && ageSeconds >= 0.0) {
            return ageSeconds > LATE_RING_LIMIT_S
        }
        return firedAt != null && firedAt > 0 && nowS - firedAt > LATE_RING_LIMIT_S
    }

    /** The quiet notice's words - both apps' (`missed_words` on the desktop). */
    fun missedWords(wentOffAt: String, body: String): String {
        val at = wentOffAt.trim()
        val head = if (at.isEmpty()) "Missed earlier." else "Missed at $at."
        val b = body.trim()
        return if (b.isEmpty()) head else "$head $b"
    }

    /**
     * The "shown once" key for a job that went off: its id and when it went
     * off - or, when the job could not be read, this event's own id (or,
     * with none, when it arrived), so two failed reads of a repeating job on
     * different days are not taken for the same firing (bug audit #6).
     */
    fun shownKey(id: String, firedAt: Double?, eventId: String?, arrivedMs: Long, sep: String = "@"): String {
        val at = firedAt?.takeIf { it > 0 }?.toLong()
        return when {
            at != null -> "$id$sep$at"
            !eventId.isNullOrBlank() -> "$id${sep}ev$eventId"
            else -> "$id${sep}t$arrivedMs"
        }
    }

    /**
     * Whether a notification tag (ScheduleNotifier tags each by its key) is
     * [jobId]'s own "went off" notice: the key is the id itself. A "tell me
     * when" match's key is `id#match@...` and is not.
     */
    fun isFiredTag(tag: String?, jobId: String): Boolean = tag == jobId

    /**
     * The job id inside a notification KEY - the value
     * [ScheduleNotifier.EXTRA_JOB_ID] carries: the job's own id for a timer,
     * alarm or reminder, and `id#match@<key>` for a "tell me when" match
     * ([shownKey] with its `#match@` separator). Used to ask the PC's own
     * `GET /api/schedule` whether the job behind a still-posted notification
     * exists at all.
     */
    fun jobIdFromTag(key: String): String {
        val cut = key.indexOf("#match@")
        return if (cut > 0) key.substring(0, cut) else key
    }

    /**
     * Every job id the PC's own `GET /api/schedule` still knows about: the
     * active jobs, the open to-do items and the ones that went off in the last
     * hour. A "went off" notification whose job is in none of those lists is
     * for a job the PC no longer has at all.
     */
    fun knownIds(view: View): Set<String> =
        (view.jobs.asSequence() + view.todo.asSequence() + view.wentOff.asSequence())
            .map { it.id }
            .toSet()

    /**
     * The "went off" notifications to take away after a schedule read: those
     * whose job is not in [known], as (tag, job id).
     *
     * This is the owner's report of 2026-10-11 in its worst form - a job
     * DELETED on the PC while the phone still showed it kept ringing for ever,
     * because the PC's `changed` event is the only cancellation this app ever
     * had, and a job that has been deleted sends none.
     *
     * [known] comes ONLY from a read that succeeded: a read that failed
     * returns no set at all (null upstream), and nothing is cancelled then. A
     * notification that is still true must never vanish because the link
     * blipped.
     */
    fun stopsWhenJobGone(posted: List<Pair<String, String>>, known: Set<String>): List<Pair<String, String>> =
        posted.filter { (_, jobId) -> jobId !in known }

    /** Whether an answer's route header says it was made without the model. */
    fun quickFromRouteHeader(header: String?): Boolean {
        if (header.isNullOrBlank()) return false
        val o = runCatching { JarvisJson.parseToJsonElement(header.trim()) as? JsonObject }.getOrNull()
            ?: return false
        return o.text("quick") != null
    }

    /**
     * "Open <a settings section>" by voice or chat
     * (`jarvis_settings_registry.py`, docs/JARVIS-API.md section 58.1): the
     * section id `SettingsScreen.kt`'s own `item(key = ...)` rows already
     * use ("web-search", "manner", ...), or null when this answer named
     * none. Pure navigation - nothing here changes a setting.
     *
     * Since F6 (2026-11-03) the same field can name a WHOLE PLACE rather than
     * only a settings row - the PC's deterministic path answers "open live",
     * "open history", "open memory" the same way it answers "open help"
     * (`OpenPlace` decides per id, including the ids this app has no screen
     * for). The field name for that is not pinned down on this side yet, so
     * the four spellings the backend could reasonably use are all read here
     * rather than silently dropping the request. A backend that keeps sending
     * `open_settings` needs no change at all - the phone resolves its value
     * through the same table.
     */
    fun openSettingsFromRoute(header: String?): String? {
        if (header.isNullOrBlank()) return null
        val o = runCatching { JarvisJson.parseToJsonElement(header.trim()) as? JsonObject }.getOrNull()
            ?: return null
        return o.text("open_settings")
            ?: o.text("open_place")
            ?: o.text("open_area")
            ?: o.text("open_screen")
    }

    private fun JsonObject.num(key: String): Double? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.doubleOrNull
            ?.takeIf { it.isFinite() }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
