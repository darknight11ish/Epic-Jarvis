package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * "What asks first" (the owner's decisions of 2026-09-26, after the approvals
 * audit; docs/JARVIS-API.md section 32; backend `jarvis_asks_first.py`,
 * `asks-first.patch`) - the desktop's Settings -> What asks first, in the
 * same words (`asks-first.js`; both are checked against
 * `contract/asks-first-cases.json`, made by the real backend).
 *
 * Every action Jarvis can take and whether it asks first, grouped, in the
 * PC's own words. On the phone:
 *  - "Ask me first" ON (stricter) on the short safe list: at once, never held
 *    on a stale link - it only makes Jarvis ask more;
 *  - "Ask me first" OFF (looser) is NOT offered: it is the PC's alone - one
 *    approval card that needs Windows Hello there - and the PC refuses it
 *    from the phone anyway (ARCHITECTURE section 8, "One-sided on purpose").
 *    The row says where to do it ([PHONE_LOOSEN]);
 *  - the loosening card itself cannot be approved here ([APPROVE_ON_PC]);
 *  - "Lights, plugs and fans without a card": ON is one approval card on the
 *    PC, held on a stale link; OFF is at once.
 *
 * Pure Kotlin, no Android types, so `AsksFirstTest` runs it on a plain JVM.
 */
object AsksFirst {
    const val PATH = "/api/asks_first"
    const val TIER_PATH = "/api/asks_first/tier"
    const val LIGHTS_PATH = "/api/asks_first/lights"

    /** The approval card that loosens one action: approved on the PC only. */
    const val LOOSEN_ACTION = "loosen_what_asks_first"

    const val TITLE = "What asks first"
    const val DETAIL =
        "Everything Jarvis can do that might need your OK, and whether it asks you first. " +
            "The PC writes this list from its own settings - the AI model does not write it. " +
            "\"Ask me first\" makes one ask every time, at once, from either app. Letting one " +
            "go ahead without asking is only for the short list below, only on the PC, and " +
            "takes an approval card and Windows Hello."
    const val MISSING =
        "Your PC's Jarvis cannot show what asks first yet - run apply-patches.ps1 on the PC."
    const val SWITCH_LABEL = "Ask me first"
    const val WAITING =
        "Waiting for your yes on the approval card, and Windows Hello, on your PC."
    const val PHONE_LOOSEN =
        "To let this go ahead without asking, use the PC: Settings, What asks first. " +
            "It takes an approval card and Windows Hello."
    const val LIGHTS_LABEL = "Lights, plugs and fans without a card"
    const val LIGHTS_DETAIL =
        "When you name a light, plug or fan yourself - \"turn off the kitchen light\" - Jarvis " +
            "switches it without an approval card. Locks, doors, alarms, covers and garage doors " +
            "always ask, each with a card of its own, and so does everything after Jarvis has " +
            "read outside text in the chat. Turning this on shows you an approval card first; " +
            "turning it off happens at once."
    const val LIGHTS_WAITING = "Waiting for your yes on the approval card, on your PC or phone."

    /** On the approval card of [LOOSEN_ACTION], in place of Approve. */
    const val APPROVE_ON_PC =
        "Approve this one on the PC - it needs Windows Hello there. Deny still works here."

    /** The actions the apps may switch - `jarvis_asks_first.SWITCHABLE`. */
    val SWITCHABLE = listOf(
        "calendar_read", "email_read", "notes_search", "home_read",
        "append_obsidian_daily", "append_logseq_journal", "create_joplin_note",
    )

    data class Switch(val asks: Boolean, val canLoosen: Boolean)

    data class Row(
        val id: String,
        val action: String,
        val title: String,
        val says: String,
        val note: String,
        val fixed: Boolean,
        val lights: Boolean,
        val switch: Switch?,
    )

    data class Group(val title: String, val rows: List<Row>)

    data class Waiting(val action: String, val title: String, val said: String)

    data class Last(val outcome: String, val action: String, val message: String)

    data class Lights(
        val on: Boolean,
        val waiting: Boolean,
        val last: String,
        val lastOutcome: String,
        val why: String,
    )

    data class View(
        val title: String,
        val detail: String,
        val groups: List<Group>,
        val canLoosen: Boolean,
        val waiting: Waiting?,
        val last: Last?,
        val lights: Lights?,
    )

    /** `GET /api/asks_first`, read - or null when it is not one (an older PC). */
    fun parse(body: JsonObject): View? {
        if (body.flag("available") == false) return null
        val groups = (body["groups"] as? JsonArray)?.mapNotNull { el ->
            val g = el as? JsonObject ?: return@mapNotNull null
            val rows = (g["rows"] as? JsonArray)?.mapNotNull { r ->
                (r as? JsonObject)?.let(::row)
            } ?: return@mapNotNull null
            Group(g.text("title") ?: "", rows)
        } ?: return null
        if (groups.isEmpty()) return null
        val w = body["waiting"] as? JsonObject
        val l = body["last"] as? JsonObject
        return View(
            title = body.text("title") ?: TITLE,
            detail = body.text("detail") ?: DETAIL,
            groups = groups,
            canLoosen = body.flag("can_loosen") == true,
            waiting = w?.let { Waiting(it.text("action") ?: "", it.text("title") ?: "", it.text("said") ?: WAITING) },
            last = l?.let { Last(it.text("outcome") ?: "", it.text("action") ?: "", it.text("message") ?: "") },
            lights = (body["lights"] as? JsonObject)?.let(::lights),
        )
    }

    private fun row(o: JsonObject): Row? {
        val id = o.text("id") ?: return null
        val action = o.text("action") ?: ""
        val sw = (o["switch"] as? JsonObject)?.let { s ->
            s.flag("asks")?.let { Switch(it, s.flag("can_loosen") == true) }
        }
        return Row(
            id = id,
            action = action,
            title = o.text("title") ?: id,
            says = o.text("says") ?: "",
            note = o.text("note") ?: "",
            fixed = o.flag("fixed") == true,
            lights = o.flag("lights") == true,
            // A switch on an action off the list is dropped: the PC refuses it anyway.
            switch = if (action in SWITCHABLE) sw else null,
        )
    }

    private fun lights(o: JsonObject): Lights? {
        val on = o.flag("on") ?: return null
        val last = o["last"] as? JsonObject
        return Lights(
            on = on,
            waiting = o.flag("waiting") == true,
            last = last?.text("message") ?: "",
            lastOutcome = last?.text("outcome") ?: "",
            why = o.text("why") ?: "",
        )
    }

    /** A read that failed because this PC does not have the page. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && error.code == 501)

    /** A row's first line: "Read your calendar - Does it without asking". */
    fun heading(r: Row): String = "${r.title} - ${r.says}"

    /**
     * One "Ask me first" switch on the phone: [SwitchView.enabled] only to
     * turn it ON (stricter) - never held on a stale link. Once it asks, the
     * phone cannot turn it off; the line says where to.
     */
    data class SwitchView(val checked: Boolean, val enabled: Boolean, val lines: List<String>)

    fun switchView(r: Row, v: View): SwitchView? {
        val s = r.switch ?: return null
        val waitingHere = v.waiting?.action == r.action && r.action.isNotEmpty()
        val checked = s.asks || waitingHere
        // Where to loosen it is in the row's own note (the PC adds
        // PHONE_LOOSEN to it for a request that is not from the PC).
        val lines = buildList {
            if (waitingHere) add(v.waiting?.said ?: WAITING)
            val last = v.last
            if (last != null && last.action == r.action && last.message.isNotEmpty() &&
                last.outcome != "loosened" && !waitingHere
            ) add(last.message)
        }
        return SwitchView(checked = checked, enabled = !checked, lines = lines)
    }

    /** The body of a stricter switch: the only kind the phone sends. */
    fun stricterBody(action: String): String? =
        if (action in SWITCHABLE) "{\"action\":\"$action\",\"ask\":true}" else null

    /**
     * The lights switch: checked while on or while an ON card waits; ON is
     * held on a stale link (rule 4), OFF never - the desktop's `lightsView`.
     */
    data class LightsView(val show: Boolean, val checked: Boolean, val canChange: Boolean, val lines: List<String>)

    fun lightsView(l: Lights?, live: Boolean): LightsView {
        if (l == null) return LightsView(false, false, false, emptyList())
        val lines = buildList {
            if (l.waiting) add(LIGHTS_WAITING)
            else if (l.last.isNotEmpty() && l.lastOutcome != "enabled") add(l.last)
            if (l.why.isNotEmpty()) add(l.why.replaceFirstChar { it.uppercase() } + ".")
        }
        val checked = l.on || l.waiting
        return LightsView(true, checked, checked || live, lines)
    }

    fun lightsBody(on: Boolean): String = "{\"enabled\":$on}"

    /** The sentence to show after a change, from the PC's own answer. */
    fun said(outcome: DesktopWrite.Outcome): String = when (outcome) {
        is DesktopWrite.Outcome.Done -> outcome.said ?: "Done."
        is DesktopWrite.Outcome.Waiting -> outcome.said ?: LIGHTS_WAITING
        is DesktopWrite.Outcome.Refused -> "Not changed. " + outcome.why
    }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
