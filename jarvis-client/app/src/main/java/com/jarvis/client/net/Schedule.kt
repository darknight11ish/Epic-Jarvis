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
 * asked for). Said plainly in JARVIS-API section 21.
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
 * every day. Two times and Set up ([standbyBody]); the PC raises ONE
 * approval card (it repeats) and sets nothing up until it is approved. It
 * then sits in the list like any repeating job, kind "standby", where Pause
 * skips it and Delete turns it off. Its going off tells nobody: the event
 * says `"notify": false`, and [firedFrom] then shows no notification.
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
            "while they are connected. Anything that repeats waits for your yes on an approval card."
    const val TODO_TITLE = "To-do list"

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

    /** Stands in for words the private lists hide. */
    const val HIDDEN_TEXT = "(hidden)"

    /** Under an answer made without the model (X-Jarvis-Route `quick`). */
    const val DONE_LINE = "Done - answered on this PC without the AI model."

    /** The phone's line about where reminders go off. */
    const val PC_IS_THE_CLOCK =
        "They go off on your PC. This phone shows them while it is connected to it."

    /** A change the PC could not make at all (no route). */
    const val TOO_OLD = "Not changed: your PC's Jarvis does not have timers and reminders yet."

    /** A 404 that said "no such job". */
    const val ALREADY_GONE = "That is not on the list any more."

    /** The only things one job can be asked to do. Never "all", never a list. */
    val ACTIONS = listOf("pause", "resume", "delete", "done")

    /** The longest to-do item the PC keeps (jarvis_schedule.MAX_TEXT). */
    const val MAX_TEXT = 300

    /** The standby schedule, both apps' words (coming-up.js). */
    const val STANDBY_TITLE = "Standby schedule"
    const val STANDBY_DETAIL =
        "Jarvis goes on standby at night and wakes in the morning - but it wakes only if the " +
            "schedule put it on standby: if you chose Standby yourself, it stays on until you choose " +
            "Active. Standby unloads its models and frees the graphics card; waking loads the chat " +
            "model again, so the first answer is quick. Timers and reminders still go off. Setting " +
            "it up asks once with an approval card."
    const val STANDBY_START_LABEL = "Standby at"
    const val STANDBY_END_LABEL = "Wake at"
    const val STANDBY_ADD = "Set up"
    const val STANDBY_IS_SET =
        "Your standby schedule is in the list above. Pause skips it and Delete turns it off. " +
            "Neither wakes Jarvis - choose Active for that."
    const val STANDBY_BAD_TIMES = "Write each time as HH:MM, like 01:00, and pick two different times."
    const val STANDBY_DEFAULT_START = "01:00"
    const val STANDBY_DEFAULT_END = "07:00"

    /** A notification's title, by kind. The desktop's toast says the same. */
    fun title(kind: String): String = when (kind) {
        "timer" -> "Timer done"
        "alarm" -> "Alarm"
        "reminder" -> "Reminder"
        "todo" -> "To-do"
        Briefing.KIND -> Briefing.TITLE
        else -> "Jarvis"
    }

    /** What a locked screen may show, by kind, when the PC did not say. */
    fun lockScreen(kind: String): String = when (kind) {
        "timer" -> "Jarvis: your timer is done."
        "alarm" -> "Jarvis: alarm."
        "reminder" -> "Jarvis: a reminder is due."
        "todo" -> "Jarvis: a to-do item is due."
        Briefing.KIND -> Briefing.LOCK_SCREEN
        else -> "Jarvis: something is due."
    }

    /** The tag on a row, by kind. */
    fun tag(kind: String): String = when (kind) {
        "todo" -> "to-do"
        else -> kind
    }

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
    )

    data class View(val jobs: List<Job>, val todo: List<Job>, val hidden: Boolean)

    /** One job, read - or null when it has no id the PC makes. */
    fun job(o: JsonObject): Job? {
        val id = o.text("id") ?: return null
        if (!validId(id)) return null
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
        )
    }

    /** `GET /api/schedule`, read - or null when it is not the list. */
    fun parse(body: JsonObject): View? {
        val jobs = body["jobs"] as? JsonArray ?: return null
        val todo = body["todo"] as? JsonArray ?: return null
        return View(
            jobs = jobs.mapNotNull { (it as? JsonObject)?.let(::job) },
            todo = todo.mapNotNull { (it as? JsonObject)?.let(::job) },
            hidden = body.flag("hidden") == true,
        )
    }

    /** `GET /api/schedule?id=` - the `job` in it. */
    fun parseOne(body: JsonObject): Job? = (body["job"] as? JsonObject)?.let(::job)

    /** A read that failed because this PC has no scheduler: a 404 or a 501. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || (error is ApiError.Server && error.code == 501)

    /** The list with every job's words replaced, for while the lists are hidden. */
    fun hide(v: View): View = View(
        jobs = v.jobs.map { it.copy(text = "", hidden = true) },
        todo = v.todo.map { it.copy(text = "", hidden = true) },
        hidden = true,
    )

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
        val words = if (job.hidden) HIDDEN_TEXT else job.text
        if (job.kind == "timer") {
            return if (words.isNotEmpty()) "$words timer" else lengthWords(job.duration ?: 0.0) + " timer"
        }
        // A morning briefing has no words of its own (Briefing.kt).
        if (job.kind == Briefing.KIND) return Briefing.TITLE
        if (words.isNotEmpty()) return words
        return when (job.kind) {
            "alarm" -> "Alarm"
            "todo" -> "To-do"
            else -> "Reminder"
        }
    }

    /** The lines under a row's title - the desktop's metaOf, word for word. */
    fun metaOf(job: Job, sinceMs: Long = 0L): List<String> {
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
        if (job.repeats && job.repeat.isNotEmpty()) out += job.repeat
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

    /** The buttons one row offers, as action names, in order. Never "all". */
    fun actionsOf(job: Job): List<String> = when {
        job.kind == "todo" -> listOf("done", "delete")
        job.state == "waiting" -> listOf("delete")
        job.state == "paused" -> listOf("resume", "delete")
        else -> listOf("pause", "delete")
    }

    fun labelOf(action: String): String = when (action) {
        "pause" -> PAUSE
        "resume" -> RESUME
        "delete" -> DELETE
        "done" -> DONE
        else -> action
    }

    /** Is anything counting down (worth a once-a-second redraw)? */
    fun anyTicking(v: View?): Boolean = v?.jobs?.any { it.kind == "timer" && it.state == "active" } == true

    /** The body of one change: one id, one action - or null when it is not one. */
    fun actBody(id: String, action: String): String? {
        if (!validId(id) || action !in ACTIONS) return null
        return "{\"id\":\"$id\",\"do\":\"$action\"}"
    }

    /** The body of one new to-do item, tidied - or null when it cannot be one. */
    fun todoBody(text: String): String? {
        val t = text.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")
        if (t.isEmpty() || t.length > MAX_TEXT) return null
        return "{\"kind\":\"todo\",\"text\":" + JarvisJson.encodeToString(
            kotlinx.serialization.serializer<String>(), t) + "}"
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
        val fallback = job?.lockScreen?.takeIf { it.isNotEmpty() } ?: lockScreen(kind)
        if (job == null || private) return title to fallback
        val words = job.text.trim()
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

    /** Whether an answer's route header says it was made without the model. */
    fun quickFromRouteHeader(header: String?): Boolean {
        if (header.isNullOrBlank()) return false
        val o = runCatching { JarvisJson.parseToJsonElement(header.trim()) as? JsonObject }.getOrNull()
            ?: return false
        return o.text("quick") != null
    }

    private fun JsonObject.num(key: String): Double? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.doubleOrNull
            ?.takeIf { it.isFinite() }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
