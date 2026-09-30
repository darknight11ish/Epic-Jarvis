package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.put
import kotlin.math.cos
import kotlin.math.sin

/**
 * "Activity heatmap and balance chart" - the owner's tick of 2026-09-30
 * (docs/BUILD-QUEUE-2026-09-30.md item 7), docs/JARVIS-API.md section 105 and
 * the "Progress contract (frozen)" in docs/GOALS-PROGRESS-DESIGN.md.
 *
 * Two small pictures in Brain -> Projects, drawn from what the PC sends:
 *
 *  - the ACTIVITY grid: about 12 weeks of days, Monday first, one column per
 *    week, each day shaded by how many things were done that day. A quiet day
 *    is a neutral outline - never red, never a cross, never "missed";
 *  - the BALANCE chart: 3 to 8 areas the owner picked, each spoke showing how
 *    far that number or goal is toward its own target. There is no total,
 *    no average and no area read out.
 *
 * The PC works out every shade, column and sentence; this file only reads
 * them, draws them (the geometry below is the shared one in the contract) and
 * builds the one request the phone sends. It never builds a sentence of its
 * own about a day or a value. No streak, no "in a row", no percentage, no
 * "score" - the same words the backend's FORBIDDEN_WORDS keep out.
 *
 * Nothing here is kept: the phone reads the answers when the Projects screen
 * opens and after its own save, and never writes them to disk. Nothing is
 * spoken, put in a notification or sent anywhere else.
 *
 * Checked against `contract/progress-cases.json`, made from the real backend
 * by tools/gen_progress_cases.py (byte-identical with the desktop's copy).
 *
 * Pure Kotlin, no Android types, so `ProgressTest` runs it on a plain JVM.
 */
object Progress {

    /** The screens' own words, both apps, word for word (the contract's `words`). */
    val WORDS: Map<String, String> = mapOf(
        "title" to "Progress",
        "heat_title" to "Activity",
        "heat_under" to "Steps you tick and numbers you log, day by day. A quiet day is just a quiet day.",
        "heat_total" to "Last {weeks} weeks: {things} on {days}.",
        "heat_empty" to "Nothing here yet. A step you tick or a number you log will show on its day.",
        "heat_undated" to "Steps ticked before this was added have no date, so they are not shown.",
        "day_some" to "{things} on {date}",
        "day_none" to "Nothing on {date}",
        "week_of" to "Week of {date}",
        "balance_title" to "Balance",
        "balance_under" to "Pick 3 to 8 of your numbers or goals. Each spoke shows how far you are from your first number to your target. There is no total.",
        "balance_none" to "Nothing picked yet.",
        "balance_few" to "Pick at least 3 to see the chart.",
        "balance_edit" to "Choose what to show",
        "balance_save" to "Save the chart",
        "balance_clear" to "Clear the chart",
        "balance_rename" to "Name on the chart",
        "balance_limit" to "Pick 3 to 8 areas, or none to clear the chart.",
        "no_numbers" to "no numbers yet",
        "no_target" to "no target yet",
        "no_steps" to "no steps yet",
        "gone" to "gone",
        "no_choices" to "Nothing to pick from yet. Give a number a target, or accept a goal.",
        "hidden" to "Hidden while memory lists and chat history are hidden.",
        "private" to "Health or money: kept on screen, never read aloud or sent anywhere.",
        "summary_heat" to "Activity, last {weeks} weeks. {total}",
        "summary_balance" to "Balance chart, {n} areas. {items} No overall score.",
    )

    /** One of [WORDS]. */
    fun w(key: String): String = WORDS.getValue(key)

    // ------------------------------------------------------------- limits ---

    const val WEEKS_DEFAULT = 12
    const val AXES_MIN = 3
    const val AXES_MAX = 8
    const val LABEL_MAX = 24

    /** Written when a choice's name is hidden (the setting is on), in place of the name. */
    const val HIDDEN_NAME = "(hidden)"

    // ----------------------------------------------------- heatmap geometry ---

    const val CELL = 14
    const val GAP = 3
    const val STEP = CELL + GAP

    /** The grid is seven rows tall: 7 * 17 - 3. */
    const val HEAT_HEIGHT = 7 * STEP - GAP

    /**
     * How strongly the accent lies over the surface at each level 0..4
     * (the contract's `shading.alpha`). Level 0 has no fill at all - only the
     * neutral outline - so its 0 is never drawn.
     */
    val ALPHAS: List<Float> = listOf(0.0f, 0.22f, 0.42f, 0.66f, 0.92f)

    /** The alpha for a level, kept to 0..4. */
    fun alphaFor(level: Int): Float = ALPHAS[level.coerceIn(0, ALPHAS.size - 1)]

    /** Total drawn width of a grid [weeks] wide. */
    fun heatWidth(weeks: Int): Int = weeks.coerceAtLeast(1) * STEP - GAP

    /** One day's square: its top-left corner and size in dp (a dp is a px in the fixture). */
    data class Rect(val date: String, val x: Int, val y: Int, val size: Int, val level: Int)

    /** Every day's square: `x = col * 17`, `y = row * 17`, size 14, in the answer's order. */
    fun heatRects(days: List<Day>): List<Rect> =
        days.map { Rect(it.date, it.col * STEP, it.row * STEP, CELL, it.level) }

    // ------------------------------------------------------ radar geometry ---

    const val RADAR_SIZE = 260
    const val RADAR_RADIUS = 80.0
    const val RADAR_LABEL_OFFSET = 14.0

    /** The rings, as a share of the radius; the outer one (1.0) is the target. */
    val RINGS: List<Double> = listOf(0.25, 0.5, 0.75, 1.0)

    /** A point in the 260 square. [dot] marks a spoke with nothing to measure yet. */
    data class Pt(val x: Double, val y: Double, val dot: Boolean = false)

    /** Where a spoke's label sits; [anchor] is "start", "middle" or "end". */
    data class LabelSpot(val x: Double, val y: Double, val anchor: String)

    data class Radar(
        val size: Int,
        val center: Pt,
        val radius: Double,
        val rings: List<Double>,
        val spokes: List<Pt>,
        val polygon: List<Pt>,
        val labels: List<LabelSpot>,
    )

    /**
     * The shared radar geometry (tools/gen_progress_cases.py `radar`). Spoke `i`
     * of `n` points at -90 degrees + i * 360 / n: the first straight up, then
     * clockwise. A vertex sits at `radius * fraction` along its spoke; a null
     * fraction puts it at the centre and marks it a dot. Labels sit 14 past the
     * outer ring, with a small downward nudge (`dy`) and an anchor.
     */
    fun radar(fractions: List<Double?>): Radar {
        val n = fractions.size
        val c = RADAR_SIZE / 2.0
        val spokes = ArrayList<Pt>(n)
        val verts = ArrayList<Pt>(n)
        val labels = ArrayList<LabelSpot>(n)
        for ((i, f) in fractions.withIndex()) {
            val a = -Math.PI / 2 + 2 * Math.PI * i / n
            val cs = cos(a)
            val sn = sin(a)
            spokes.add(Pt(c + RADAR_RADIUS * cs, c + RADAR_RADIUS * sn))
            val fr = (f ?: 0.0).coerceIn(0.0, 1.0)
            verts.add(Pt(c + RADAR_RADIUS * fr * cs, c + RADAR_RADIUS * fr * sn, dot = f == null))
            val anchor = if (Math.abs(cs) < 0.2) "middle" else if (cs > 0) "start" else "end"
            val dy = if (sn > 0.3) 10.0 else if (sn < -0.3) 0.0 else 4.0
            labels.add(
                LabelSpot(
                    c + (RADAR_RADIUS + RADAR_LABEL_OFFSET) * cs,
                    c + (RADAR_RADIUS + RADAR_LABEL_OFFSET) * sn + dy,
                    anchor,
                ),
            )
        }
        return Radar(RADAR_SIZE, Pt(c, c), RADAR_RADIUS, RINGS.map { RADAR_RADIUS * it }, spokes, verts, labels)
    }

    // ------------------------------------------------------------- answers ---

    /** What the PC answered, kept whole: the status and the JSON body. */
    data class Reply(val code: Int, val body: JsonObject?)

    data class Column(val col: Int, val label: String)

    data class Day(
        val date: String,
        val col: Int,
        val row: Int,
        val count: Int,
        val level: Int,
        val words: String,
    )

    /** `GET /api/progress/activity`. */
    data class Heat(
        val weeks: Int,
        val columns: List<Column>,
        val days: List<Day>,
        val empty: Boolean,
        val words: String,
        val note: String,
        val summary: String,
        val keepOnScreen: Boolean,
        val hiddenWords: String,
    )

    data class Axis(
        val label: String,
        val short: String,
        val name: String,
        val kind: String,
        val ref: String,
        val project: String,
        val state: String,
        val valueWords: String,
        /** 0..1, or null = nothing to measure yet (drawn as a dot in the middle). */
        val fraction: Double?,
        val keepOnScreen: Boolean,
    )

    data class Choice(
        val kind: String,
        val ref: String,
        val project: String,
        val projectName: String,
        val name: String,
        val picked: Boolean,
        val keepOnScreen: Boolean,
    )

    /** `GET /api/progress/balance` (and the answer to a saved pick). */
    data class Balance(
        val axes: List<Axis>,
        val drawable: Boolean,
        val min: Int,
        val max: Int,
        val maxLabel: Int,
        val words: String,
        val summary: String,
        val choices: List<Choice>,
        val keepOnScreen: Boolean,
        val hiddenWords: String,
    )

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject.flag(key: String): Boolean? = (this[key] as? JsonPrimitive)?.booleanOrNull

    private fun JsonObject.whole(key: String): Int? = (this[key] as? JsonPrimitive)?.intOrNull

    private fun JsonObject.list(key: String): List<JsonObject> =
        (this[key] as? JsonArray)?.mapNotNull { it as? JsonObject }.orEmpty()

    /**
     * The activity answer, read. Keys it does not know are ignored; a missing
     * key is its empty value. Null when [body] says it is not an answer
     * (`ok` false, or `available` false).
     */
    fun parseHeat(body: JsonObject): Heat? {
        if (body.flag("ok") == false || body.flag("available") == false) return null
        val days = body.list("days").mapNotNull { d ->
            val date = d.text("date") ?: return@mapNotNull null
            Day(
                date = date,
                col = d.whole("col") ?: return@mapNotNull null,
                row = d.whole("row") ?: return@mapNotNull null,
                count = d.whole("count") ?: 0,
                level = (d.whole("level") ?: 0).coerceIn(0, ALPHAS.size - 1),
                words = d.text("words").orEmpty(),
            )
        }
        val columns = body.list("columns").mapNotNull { c ->
            Column(c.whole("col") ?: return@mapNotNull null, c.text("label").orEmpty())
        }
        val weeks = body.whole("weeks") ?: (days.maxOfOrNull { it.col }?.plus(1) ?: WEEKS_DEFAULT)
        return Heat(
            weeks = weeks.coerceAtLeast(1),
            columns = columns,
            days = days,
            empty = body.flag("empty") ?: days.none { it.count > 0 },
            words = body.text("words").orEmpty(),
            note = body.text("note").orEmpty(),
            summary = body.text("summary").orEmpty(),
            keepOnScreen = body.flag("keep_on_screen") ?: false,
            hiddenWords = body.text("hidden_words")?.takeIf { it.isNotBlank() } ?: w("hidden"),
        )
    }

    /** The balance answer, read the same forgiving way. */
    fun parseBalance(body: JsonObject): Balance? {
        if (body.flag("ok") == false || body.flag("available") == false) return null
        val axes = body.list("axes").map { a ->
            val label = a.text("label").orEmpty()
            Axis(
                label = label,
                short = a.text("short") ?: label,
                name = a.text("name") ?: label,
                kind = a.text("kind").orEmpty(),
                ref = a.text("ref").orEmpty(),
                project = a.text("project").orEmpty(),
                state = a.text("state").orEmpty(),
                valueWords = a.text("value_words").orEmpty(),
                fraction = (a["fraction"] as? JsonPrimitive)?.doubleOrNull?.takeIf { it.isFinite() }
                    ?.coerceIn(0.0, 1.0),
                keepOnScreen = a.flag("keep_on_screen") ?: false,
            )
        }
        val choices = body.list("choices").map { c ->
            Choice(
                kind = c.text("kind").orEmpty(),
                ref = c.text("ref").orEmpty(),
                project = c.text("project").orEmpty(),
                projectName = c.text("project_name").orEmpty(),
                name = c.text("name").orEmpty(),
                picked = c.flag("picked") ?: false,
                keepOnScreen = c.flag("keep_on_screen") ?: false,
            )
        }
        return Balance(
            axes = axes,
            drawable = body.flag("drawable") ?: (axes.size >= AXES_MIN),
            min = body.whole("min") ?: AXES_MIN,
            max = body.whole("max") ?: AXES_MAX,
            maxLabel = body.whole("max_label") ?: LABEL_MAX,
            words = body.text("words").orEmpty(),
            summary = body.text("summary").orEmpty(),
            choices = choices,
            keepOnScreen = body.flag("keep_on_screen") ?: false,
            hiddenWords = body.text("hidden_words")?.takeIf { it.isNotBlank() } ?: w("hidden"),
        )
    }

    /**
     * A read from a PC that has no such route: a 404 whose body is not the PC's
     * own refusal (`ok: false`), or a 501. The section is simply not shown.
     */
    fun isMissing(reply: Reply): Boolean {
        val pcOwn = (reply.body?.get("ok") as? JsonPrimitive)?.booleanOrNull == false
        return (reply.code == 404 && !pcOwn) || reply.code == 501
    }

    // ------------------------------------------------- screen-reader text ---

    /** One focusable row per week for TalkBack: "Week of 6 Oct: 1 thing on 6 Oct. Nothing on 7 Oct. ...". */
    data class WeekRow(val label: String, val text: String)

    /**
     * The grid as text, one row per week. The row header is the column's label
     * ("Week of 6 Oct"), then that week's days' own words, Monday to Sunday,
     * joined with ". "; a day after today has no cell, so it has no words.
     */
    fun weekRows(heat: Heat): List<WeekRow> =
        heat.columns.sortedBy { it.col }.map { c ->
            val words = heat.days.filter { it.col == c.col }.sortedBy { it.row }.map { it.words }
            WeekRow(c.label, if (words.isEmpty()) c.label else c.label + ": " + words.joinToString(". "))
        }

    /** The line for one axis in the list under the picture: "Running: 12.5 of 20 km". */
    fun axisLine(a: Axis): String = when {
        a.valueWords.isNotBlank() -> a.label + ": " + a.valueWords
        a.state == "no_numbers" -> a.label + ": " + w("no_numbers")
        a.state == "no_target" -> a.label + ": " + w("no_target")
        a.state == "no_steps" -> a.label + ": " + w("no_steps")
        else -> a.label
    }

    // --------------------------------------------- hide memory lists ---

    /**
     * "Hide memory lists and chat history" on: an answer marked
     * `keep_on_screen` is not drawn at all - only its `hiddenWords` stay. The
     * blanked copy holds no day, area, name or number, so nothing private is
     * even held in memory while the setting is on.
     */
    fun blankedHeat(h: Heat): Heat =
        h.copy(columns = emptyList(), days = emptyList(), empty = true, words = "", note = "", summary = h.hiddenWords)

    /**
     * The same for the balance answer. Also, on a picker row marked
     * `keep_on_screen` the name becomes "(hidden)" and it cannot be ticked
     * ([choiceTickable]).
     */
    fun blankedBalance(b: Balance): Balance {
        val choices = b.choices.map { if (it.keepOnScreen) hideChoice(it) else it }
        return if (b.keepOnScreen) {
            b.copy(axes = emptyList(), drawable = false, words = "", summary = b.hiddenWords, choices = choices)
        } else {
            b.copy(axes = b.axes.filter { !it.keepOnScreen }, choices = choices)
        }
    }

    private fun hideChoice(c: Choice): Choice = c.copy(name = HIDDEN_NAME, projectName = "")

    /** A picker row that is hidden cannot be ticked. */
    fun choiceTickable(c: Choice): Boolean = c.name != HIDDEN_NAME

    // ---------------------------------------------------------- the picker ---

    /** One area the owner has ticked, and the name they gave it on the chart. */
    data class Pick(val kind: String, val ref: String, val label: String)

    /** The picker starts from what is on the chart now, in the chart's order, with its names. */
    fun picksFrom(b: Balance): List<Pick> =
        b.axes.map { Pick(it.kind, it.ref, it.label) }

    /** Save is allowed at 3 to 8 ticked, or at 0 as "Clear the chart". */
    fun canSave(picked: Int): Boolean = picked == 0 || picked in AXES_MIN..AXES_MAX

    /** The 9th tick is not offered. */
    fun canPickMore(picked: Int): Boolean = picked < AXES_MAX

    /** The button's own words: "Clear the chart" at 0, else "Save the chart". */
    fun saveLabel(picked: Int): String = if (picked == 0) w("balance_clear") else w("balance_save")

    /** The typed name, cut to the most the PC takes. */
    fun clipLabel(text: String): String = text.take(LABEL_MAX)

    /**
     * `POST /api/progress/balance` body: `{"axes": [{"kind", "ref", "label"?}]}`.
     * An empty list clears the chart. A blank label is left out (the PC uses the
     * number's or goal's own name).
     */
    fun saveBody(picks: List<Pick>): String = buildJsonObject {
        put(
            "axes",
            JsonArray(
                picks.map { p ->
                    buildJsonObject {
                        put("kind", p.kind)
                        put("ref", p.ref)
                        val label = p.label.trim()
                        if (label.isNotEmpty()) put("label", label)
                    }
                },
            ),
        )
    }.toString()

    /** How a save went: [ok] means the chart changed; [said] is the PC's sentence, as sent. */
    data class Outcome(val ok: Boolean, val said: String, val balance: Balance?)

    /**
     * Reads the PC's answer to a save. A 200 is the new chart; a 400 is a
     * refusal whose `error` sentence is shown exactly as sent and changes
     * nothing. Anything else is a plain "not changed".
     */
    fun saved(reply: Reply): Outcome {
        val body = reply.body
        if (reply.code in 200..299 && body != null) {
            val b = parseBalance(body)
            if (b != null) return Outcome(true, "", b)
        }
        val sent = body?.text("error")?.takeIf { it.isNotBlank() }
        return Outcome(false, sent ?: "Not changed.", null)
    }

    /** What to say when a read did not give a picture. Null = say nothing (route missing). */
    fun readProblem(reply: Reply): String? {
        if (isMissing(reply)) return null
        return reply.body?.text("error")?.takeIf { it.isNotBlank() } ?: "Couldn't read it right now."
    }
}
