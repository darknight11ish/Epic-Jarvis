package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.put

/**
 * "Retirement what-if" (the owner's decision of 2026-09-30, queue item 5;
 * docs/JARVIS-API.md section 103; docs/FINANCE-DESIGN.md part B and its frozen
 * "Retirement contract"). The owner types their own numbers into a form; the
 * PC plays out 10,000 made-up futures and answers with ranges only.
 *
 * On the phone that is a form and an answer, and nothing more:
 *  - the form is drawn from `GET /api/retirement/defaults` ([parseDefaults]):
 *    labels, units, limits and help lines come from the PC, not from here;
 *  - Work it out posts the typed boxes to `POST /api/retirement/run`
 *    ([requestBody]) and draws what the PC sent ([parseResult]).
 *
 * What this file never does, on purpose:
 *  - simulate, add up, round, sort, re-format or re-word a figure or a
 *    sentence. Every string in a result is drawn as the PC sent it. (The
 *    local [check] only mirrors the PC's own bounds so a typing slip is told
 *    at once; the PC's word is final and its messages are the ones shown.)
 *  - keep anything. The typed numbers and the answer are held in memory by
 *    the screen that draws them and are never written to disk, saved state,
 *    a log, a copy or a share; the answer is `private: true`,
 *    `read_aloud: false`, `remember: false`.
 *
 * Pure Kotlin, no Android types, so `RetirementTest` runs it on a plain JVM.
 */
object Retirement {
    // Literal route strings on purpose: tools/check_parity.py reads them.
    const val DEFAULTS_PATH = "/api/retirement/defaults"
    const val RUN_PATH = "/api/retirement/run"

    // Words the apps own (contract R5) and the PC's fixed words, used only
    // when an answer leaves one out. RetirementTest compares them with the
    // contract.
    const val TITLE = "Retirement what-if"
    const val RUN = "Work it out"
    const val WORKING = "Working it out"
    const val ASSUMED = "assumed"
    const val USED_HEADING = "What I used"
    const val HIDDEN = "Retirement what-if hidden"
    const val DISCLAIMER = "This is a simplified what-if, not financial advice."
    const val BUSY = "Another what-if is still being worked out. Try again in a moment."
    const val TOO_SLOW = "That took too long to work out, so it was stopped. Try again."

    /** Brain's plate on a PC too old to have the route. */
    const val MISSING = "Your PC's Jarvis cannot do the retirement what-if yet - run apply-patches.ps1 on the PC."
    const val UNREADABLE = "The desktop sent something this app could not read."
    const val READING = "Reading…"
    const val GENERIC = "The PC could not work that out. Try again."

    /** Said above the form when a box needs a look (the notes are under the boxes). */
    const val CHECK_BOXES = "Some boxes need a look. The notes are under them."

    /** Only these keys ever leave the phone in a run. Anything else is dropped. */
    val KEYS: List<String> = listOf(
        "current_age", "retirement_age", "plan_to_age", "savings", "yearly_saving",
        "yearly_spending", "other_income", "other_income_start_age",
        "expected_return_percent", "volatility_percent", "inflation_percent",
    )

    // ------------------------------------------------------------ the form

    /** One box of the form, from `GET /api/retirement/defaults` -> `fields`. */
    data class Field(
        val key: String,
        val label: String,
        val unit: String,
        /** "age", "money" or "percent". */
        val kind: String,
        val min: Double,
        val max: Double,
        /** The default as text to prefill or show, or null (no default). */
        val default: String?,
        val required: Boolean,
        /** A made-up figure the owner may change: it starts filled in. */
        val placeholder: Boolean,
        val help: String,
    )

    /** The words the PC gives for a hidden, busy or too-slow card. */
    data class Words(
        val hidden: String = HIDDEN,
        val busy: String = BUSY,
        val tooSlow: String = TOO_SLOW,
    )

    data class Defaults(
        val title: String,
        val detail: String,
        val fields: List<Field>,
        val maxYears: Int,
        val disclaimer: String,
        val placeholderNote: String,
        val todaysMoney: String,
        val words: Words,
    )

    /** `GET /api/retirement/defaults`. Null when the answer is not the form. */
    fun parseDefaults(body: JsonObject): Defaults? {
        if (body.flag("available") == false) return null
        val list = body["fields"] as? JsonArray ?: return null
        val fields = list.mapNotNull { e ->
            val o = e as? JsonObject ?: return@mapNotNull null
            val key = o.text("key") ?: return@mapNotNull null
            val kind = o.text("kind") ?: return@mapNotNull null
            val min = o.number("min") ?: return@mapNotNull null
            val max = o.number("max") ?: return@mapNotNull null
            Field(
                key = key,
                label = o.text("label") ?: key,
                unit = o.text("unit") ?: "",
                kind = kind,
                min = min,
                max = max,
                default = o.number("default")?.let { numberText(it) },
                required = o.flag("required") == true,
                placeholder = o.flag("placeholder") == true,
                help = o.text("help") ?: "",
            )
        }
        if (fields.isEmpty()) return null
        val w = body["words"] as? JsonObject
        return Defaults(
            title = body.text("title") ?: TITLE,
            detail = body.text("detail") ?: "",
            fields = fields,
            maxYears = body.number("max_years")?.toInt() ?: 90,
            disclaimer = body.text("disclaimer") ?: DISCLAIMER,
            placeholderNote = body.text("placeholder_note") ?: "",
            todaysMoney = body.text("todays_money") ?: "",
            words = Words(
                hidden = w?.text("hidden") ?: HIDDEN,
                busy = w?.text("busy") ?: BUSY,
                tooSlow = w?.text("too_slow") ?: TOO_SLOW,
            ),
        )
    }

    /** What a box starts with: its placeholder default, else empty (contract R2). */
    fun startingValues(d: Defaults): Map<String, String> =
        d.fields.filter { it.placeholder && it.default != null }.associate { it.key to it.default.orEmpty() }

    /** "18 to 100", "0 to 1,000,000,000", "-5 to 15": the limits, from the PC's numbers. */
    fun limitsText(f: Field): String =
        if (f.kind == "money") "${grouped(f.min)} to ${grouped(f.max)}" else "${numberText(f.min)} to ${numberText(f.max)}"

    /** The unit shown beside a box ("years", "money per year", "percent"). */
    fun unitText(f: Field): String = f.unit

    // ------------------------------------------------------------ the run

    /**
     * The `POST /api/retirement/run` body: a flat object of the typed boxes,
     * as text exactly as typed (trimmed), blank ones left out so the PC takes
     * their default. Only the eleven known keys can go. NEVER logged.
     */
    fun requestBody(values: Map<String, String>): String = buildJsonObject {
        for (k in KEYS) {
            val v = values[k]?.trim().orEmpty()
            if (v.isNotEmpty()) put(k, v)
        }
    }.toString()

    // ------------------------------------------------------------ checking a slip early

    private val INT_RE = Regex("^\\d{1,4}$")
    private val PERCENT_RE = Regex("^[+-]?\\d{1,4}(?:\\.\\d{1,6})?$")
    private val MONEY_RE = Regex("^\\d{1,12}(?:\\.\\d{1,2})?$")
    private val NEG_MONEY_RE = Regex("^-\\d+(?:\\.\\d+)?$")

    /** The PC's own `_range_words`, so a local slip reads the same as the PC's answer. */
    private fun rangeWords(f: Field): String = when (f.kind) {
        "age" -> "a whole number from ${numberText(f.min)} to ${numberText(f.max)}"
        "money" -> "an amount from 0 to ${grouped(f.max)}"
        else -> "a number from ${numberText(f.min)} to ${numberText(f.max)}"
    }

    /**
     * A problem with ONE box that can be told without asking the PC, in the
     * PC's own words, or null. It never rejects something the PC would accept:
     * text it cannot judge (a money amount in an unusual style) is left to
     * the PC. The typed text is never in the message.
     */
    fun problemFor(f: Field, typed: String?): String? {
        val text = typed?.trim().orEmpty()
        if (text.isEmpty()) {
            return if (f.required) "Please type in \"${f.label}\". I will not guess it." else null
        }
        val msg = "${f.label} must be ${rangeWords(f)}."
        return when (f.kind) {
            "age" -> {
                if (!INT_RE.matches(text)) return msg
                val n = text.toInt()
                if (n < f.min || n > f.max) msg else null
            }
            "percent" -> {
                val t = text.trimEnd('%').trim()
                if (!PERCENT_RE.matches(t)) return msg
                val x = t.toDouble()
                if (x < f.min || x > f.max) msg else null
            }
            "money" -> {
                val t = text.replace(",", "")
                when {
                    MONEY_RE.matches(t) -> if (t.toDouble() > f.max) msg else null
                    NEG_MONEY_RE.matches(t) -> if (t.toDouble() < 0) "${f.label} cannot be negative." else null
                    else -> null
                }
            }
            else -> null
        }
    }

    /**
     * Every box the PC would refuse for a reason this app can see by itself:
     * key -> the PC's own sentence. Empty when nothing is wrong (the PC still
     * has the last word). The plan-to age is checked against the retirement
     * age and the age now only when all three are fine on their own.
     */
    fun check(d: Defaults, values: Map<String, String>): Map<String, String> {
        val out = LinkedHashMap<String, String>()
        for (f in d.fields) {
            problemFor(f, values[f.key])?.let { out[f.key] = it }
        }
        val cur = ageOf(d, values, "current_age")
        val ret = ageOf(d, values, "retirement_age")
        val plan = ageOf(d, values, "plan_to_age")
        if (cur != null && ret != null && plan != null &&
            "current_age" !in out && "retirement_age" !in out && "plan_to_age" !in out
        ) {
            if (plan <= maxOf(ret, cur)) {
                out["plan_to_age"] = "The age to plan the money to must be after the age you stop working " +
                    "(and after your age now)."
            } else if (plan - cur > d.maxYears) {
                out["plan_to_age"] = "That is more than ${d.maxYears} years from your age now. Pick a nearer age."
            }
        }
        return out
    }

    /** The whole-number age typed in a box (or its default when blank), or null. */
    private fun ageOf(d: Defaults, values: Map<String, String>, key: String): Int? {
        val typed = values[key]?.trim().orEmpty()
        val text = if (typed.isNotEmpty()) typed else d.fields.firstOrNull { it.key == key }?.default?.substringBefore('.').orEmpty()
        return if (INT_RE.matches(text)) text.toInt() else null
    }

    // ------------------------------------------------------------ the answer

    /** "about 71 of 100"; [per100] is only for a bar, never a headline. */
    data class Share(val per100: Int, val label: String, val all: Boolean, val none: Boolean)

    data class Band(val share: Share, val points: Double)

    data class EndBalance(val age: Int?, val p10: String?, val p50: String?, val p90: String?)

    data class PoorCase(val lasts: Boolean, val age: Int?)

    data class Used(val key: String, val label: String, val value: String, val assumed: Boolean)

    data class Result(
        val title: String,
        /** "mixed", "never_runs_out", "always_runs_out", "not_enough_to_say", or one this app does not know. */
        val state: String,
        val reason: String?,
        val share: Share?,
        val lower: Band?,
        val higher: Band?,
        val endBalance: EndBalance?,
        val poorCase: PoorCase?,
        val runsOutBetween: Pair<Int, Int>?,
        val middleLastsTo: Int?,
        val summary: List<String>,
        val used: List<Used>,
        val todaysMoney: String,
        val placeholderNote: String,
        val disclaimer: String,
    )

    /** The `result` object of a 200 answer. Null when there is no sentence to draw. */
    fun parseResult(o: JsonObject): Result? {
        val summary = (o["summary"] as? JsonArray).orEmpty().mapNotNull { (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.contentOrNull?.trim()?.takeIf { s -> s.isNotEmpty() } }
        if (summary.isEmpty()) return null
        val bands = o["bands"] as? JsonObject
        val eb = o["end_balance"] as? JsonObject
        val ebText = eb?.get("text") as? JsonObject
        val poor = o["poor_case"] as? JsonObject
        val between = (o["runs_out_between"] as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.numberInt() }
        val used = (o["used"] as? JsonArray).orEmpty().mapNotNull { e ->
            val u = e as? JsonObject ?: return@mapNotNull null
            val label = u.text("label") ?: return@mapNotNull null
            val value = u.text("value") ?: return@mapNotNull null
            Used(u.text("key") ?: label, label, value, u.flag("assumed") == true)
        }
        return Result(
            title = o.text("title") ?: TITLE,
            state = o.text("state") ?: "",
            reason = o.text("reason"),
            share = (o["share"] as? JsonObject)?.let(::parseShare),
            lower = (bands?.get("lower") as? JsonObject)?.let(::parseBand),
            higher = (bands?.get("higher") as? JsonObject)?.let(::parseBand),
            endBalance = eb?.let {
                EndBalance(it.int("age"), ebText?.text("p10"), ebText?.text("p50"), ebText?.text("p90"))
            },
            poorCase = poor?.let { PoorCase(it.flag("lasts") == true, it.int("age")) },
            runsOutBetween = if (between != null && between.size == 2) between[0] to between[1] else null,
            middleLastsTo = o.int("middle_lasts_to"),
            summary = summary,
            used = used,
            todaysMoney = o.text("todays_money") ?: "",
            placeholderNote = o.text("placeholder_note") ?: "",
            disclaimer = o.text("disclaimer") ?: DISCLAIMER,
        )
    }

    private fun parseShare(o: JsonObject): Share? {
        val label = o.text("label") ?: return null
        val per = o.int("per_100") ?: return null
        return Share(per.coerceIn(0, 100), label, o.flag("all") == true, o.flag("none") == true)
    }

    private fun parseBand(o: JsonObject): Band? {
        val share = parseShare(o) ?: return null
        return Band(share, o.number("points") ?: 0.0)
    }

    /**
     * What TalkBack says for the whole answer: the sentences, then the
     * disclaimer. The bars and lists are left out of it because these say the
     * same in words.
     */
    fun spoken(r: Result): String = (r.summary + r.disclaimer).joinToString(" ")

    /**
     * The three money-left figures at the plan-to age, as the PC wrote them
     * (`end_balance.text`): caption to text. Captions are fixed words that
     * echo the PC's own ("poor case (1 in 10)"); empty when there is none.
     */
    fun balanceRows(r: Result): List<Pair<String, String>> {
        val e = r.endBalance ?: return emptyList()
        return listOfNotNull(
            e.p10?.let { "Poor case (1 in 10)" to it },
            e.p50?.let { "Middle case" to it },
            e.p90?.let { "Good case (1 in 10)" to it },
        )
    }

    /** The line above the money-left rows ("Money left at age 95"), or null when there is no age. */
    fun balanceHeading(r: Result): String? = r.endBalance?.age?.let { "Money left at age $it" }

    /** The bar rows for the share of futures that last: caption to (share). */
    fun shareRows(r: Result): List<Pair<String, Share>> {
        val mid = r.share ?: return emptyList()
        val lo = r.lower
        val hi = r.higher
        return listOfNotNull(
            lo?.let { "Returns ${pointsText(it.points)} lower" to it.share },
            "As typed" to mid,
            hi?.let { "Returns ${pointsText(it.points)} higher" to it.share },
        )
    }

    /** "1 point", "2 points": the size of the return step, as the PC sent it (absolute value). */
    fun pointsText(points: Double): String {
        val p = kotlin.math.abs(points)
        val n = numberText(p)
        return if (p == 1.0) "$n point" else "$n points"
    }

    /** "assumed" row reading for TalkBack: label, value, and the word when it is made up. */
    fun usedReading(u: Used): String = if (u.assumed) "${u.label}, ${u.value}, $ASSUMED" else "${u.label}, ${u.value}"

    // ------------------------------------------------------------ answers to a run

    /** What the PC answered a run, kept whole: the status and the JSON body, if any. */
    data class Reply(val code: Int, val body: JsonObject?)

    sealed interface Outcome {
        data class Done(val result: Result) : Outcome

        /** A box the PC refused: show [message] under [key]. */
        data class FieldProblem(val key: String, val message: String) : Outcome

        /** Anything else worth a sentence. [busy] means "another run is in progress": try once more. */
        data class Problem(val message: String, val busy: Boolean = false) : Outcome

        /** This PC has no such route (an older backend, or the module missing). */
        data object Missing : Outcome
    }

    /** Reads a run's answer. Messages are the PC's own; fixed words fill in only when it sent none. */
    fun classify(reply: Reply, words: Words = Words()): Outcome {
        val body = reply.body
        return when (reply.code) {
            200 -> {
                val result = (body?.get("result") as? JsonObject)
                    ?: body?.takeIf { it.containsKey("summary") }
                val parsed = result?.let(::parseResult)
                if (parsed != null) Outcome.Done(parsed) else Outcome.Problem(UNREADABLE)
            }
            400 -> {
                val error = body?.text("error").orEmpty()
                val field = body?.text("field").orEmpty()
                val message = body?.text("message") ?: GENERIC
                // unknown_field is an app bug: never pin it on a box.
                if (field.isEmpty() || error == "unknown_field") Outcome.Problem(message)
                else Outcome.FieldProblem(field, message)
            }
            429 -> Outcome.Problem(body?.text("message") ?: words.busy, busy = true)
            503 -> if (body?.text("error") == "too_slow") {
                Outcome.Problem(body.text("message") ?: words.tooSlow)
            } else {
                Outcome.Missing
            }
            404, 501 -> Outcome.Missing
            else -> Outcome.Problem(GENERIC)
        }
    }

    /** A PC without the route: an older backend, or the module missing (503). */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && (error.code == 501 || error.code == 503))

    /**
     * Whether the words "Retirement what-if hidden" stand in place of the form
     * and the answer, with NO fetch and no value kept: "Hide memory lists and
     * chat history" is on, or App lock is locked. (On the phone a locked app
     * draws no screen at all, so the second half is a belt on top of that.)
     */
    fun hiddenNow(hideLists: Boolean, locked: Boolean): Boolean = hideLists || locked

    // ------------------------------------------------------------ small readers

    private fun numberText(d: Double): String =
        if (d == Math.floor(d) && kotlin.math.abs(d) < 1e15) d.toLong().toString() else d.toString()

    private fun grouped(d: Double): String =
        if (d == Math.floor(d) && kotlin.math.abs(d) < 1e15) String.format(java.util.Locale.US, "%,d", d.toLong()) else d.toString()

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull

    private fun JsonObject.number(key: String): Double? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.content?.toDoubleOrNull()

    private fun JsonObject.int(key: String): Int? = (this[key] as? JsonPrimitive)?.numberInt()

    private fun JsonPrimitive.numberInt(): Int? =
        takeIf { it !is JsonNull && !it.isString }?.content?.let { it.toIntOrNull() ?: it.toDoubleOrNull()?.toInt() }
}
