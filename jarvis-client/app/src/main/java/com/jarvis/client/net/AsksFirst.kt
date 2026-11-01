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
 *  - Lockdown (2026-09-28): one tap makes every way out of the PC ask first,
 *    or stop. The phone can turn it ON - at once, never held on a stale
 *    link, the same route as "Ask me first" ([lockdownBody]) - and never
 *    OFF: that is the PC's alone, one card plus Windows Hello, like
 *    loosening. Home says "Lockdown is on" from the handshake and the
 *    `lockdown` event ([lockdownFrom]).
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

    /** Lockdown (2026-09-28) - the PC's words, `jarvis_asks_first.LOCKDOWN_*`. */
    const val LOCKDOWN_ACTION = "lockdown"
    const val LOCKDOWN_LABEL = "Lockdown"
    const val LOCKDOWN_DETAIL =
        "One tap makes every way out of this PC ask you first, or stop: web search and research, " +
            "sending or saving email, reading your calendar, email and Home Assistant, your smart " +
            "home, news feeds and \"tell me when\" watches, plug-in programs, cloud AI models, chatbot " +
            "conversations, the online weather behind the animal and checking for tool updates. " +
            "Turning it on is instant, from either app. Turning it off is " +
            "on the PC only, with an approval card and Windows Hello."
    const val LOCKDOWN_ON_SAYS =
        "Lockdown is on: everything that would leave this PC asks you first, and anything that " +
            "runs by itself (\"tell me when\", news, the briefing's calendar and email, chatbot " +
            "conversations, the online weather) has stopped."
    const val LOCKDOWN_OFF_SAYS = "Lockdown is off: everything asks first as your settings say."
    const val LOCKDOWN_ON_LABEL = "Turn on Lockdown"
    const val LOCKDOWN_PC_ONLY =
        "Lockdown can only be turned off on the PC (Settings, What asks first), with an approval " +
            "card and Windows Hello."
    const val LOCKDOWN_WAITING =
        "Waiting for your yes on the approval card, and Windows Hello, on your PC."

    /** Home's line while Lockdown is on - the desktop bar's strip, in the phone's place. */
    const val LOCKDOWN_BAR_LABEL = "Lockdown is on"
    const val LOCKDOWN_HOME_LINE =
        "Everything that would leave the PC asks you first, and anything that runs by itself " +
            "has stopped. It can be turned off only on the PC: Settings, What asks first."

    /** On the approval card of [LOOSEN_ACTION], in place of Approve. */
    const val APPROVE_ON_PC =
        "Approve this one on the PC - it needs Windows Hello there. Deny still works here."

    /** The actions the apps may switch - `jarvis_asks_first.SWITCHABLE`. */
    val SWITCHABLE = listOf(
        "calendar_read", "email_read", "notes_search", "home_read",
        "append_obsidian_daily", "append_logseq_journal", "create_joplin_note",
        // 2026-10-08: the five rows the audit found running without asking and
        // switchable nowhere. browse_model_catalog (leaves this PC) and
        // rollback_model (the undo for a switch must never wait) stay off.
        "read_files_readonly", "read_joplin_note", "read_logseq_page",
        "create_logseq_page", "power_manage",
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

    // --- The switchable in-app tools (2026-10-31, the tiered-tools slice) -----
    //
    // The PC now offers 21 one-tool switches in four groups, plus the vault
    // organizer's own switch and the list of tools it deliberately does not
    // offer in-app. The PHONE IS READ-ONLY here (`can_enable` is false for a
    // request that did not come from the PC): it shows every switch and its
    // state in the PC's own labels and says, plainly, that the PC is where they
    // are changed. No new route, no approval, no write.

    /** The PC's own sentence for a switch page opened away from the PC. */
    const val TOOLS_PC_ONLY =
        "Offering a tool to the AI model can only be turned on from the PC (Settings, What asks " +
            "first). It takes one approval card and Windows Hello."

    /** The read-only state lines the phone draws for one tool. */
    const val TOOLS_ON = "On: the AI model is offered this."
    const val TOOLS_OFF = "Off: the AI model is not offered this."
    const val TOOLS_TOML_ONLY_TITLE = "Kept in your settings file on the PC"

    /** The vault organizer's own state lines (it is not a tool switch). */
    const val TOOLS_VAULT_ON = "On: it can plan a tidy-up; the PC writes nothing until its one card."
    const val TOOLS_VAULT_OFF = "Off: nothing is planned or changed."

    data class ToolSwitch(
        val id: String,
        val title: String,
        val group: String,
        val on: Boolean,
        val waiting: Boolean,
        val last: String,
    )

    data class ToolGroup(val title: String, val rows: List<ToolSwitch>)

    /** The vault organizer's own switch, shown beside the tool switches. */
    data class VaultSwitch(
        val title: String,
        val what: String,
        val on: Boolean,
        val waiting: Boolean,
    )

    /** The tools this slice deliberately does not offer in-app. */
    data class ToolsNotOffered(val labels: List<Pair<String, String>>, val why: String)

    data class Tools(
        val label: String,
        val detail: String,
        val canEnable: Boolean,
        val groups: List<ToolGroup>,
        val vault: VaultSwitch?,
        val notOffered: ToolsNotOffered?,
    )

    /** One tool's state in words - the phone shows it, never changes it. */
    fun toolState(r: ToolSwitch): String = when {
        r.waiting -> WAITING
        r.on -> TOOLS_ON
        else -> TOOLS_OFF
    }

    /** The vault organizer's state, in the same shape. */
    fun vaultState(v: VaultSwitch): String = when {
        v.waiting -> WAITING
        v.on -> TOOLS_VAULT_ON
        else -> TOOLS_VAULT_OFF
    }

    /** Lockdown's state, as the PC says it; null from a PC without it. */
    data class Lockdown(
        val on: Boolean,
        val waiting: Boolean,
        val last: String,
        val lastOutcome: String,
        val why: String,
        val says: String,
    )

    data class View(
        val title: String,
        val detail: String,
        val groups: List<Group>,
        val canLoosen: Boolean,
        val waiting: Waiting?,
        val last: Last?,
        val lights: Lights?,
        val lockdown: Lockdown? = null,
        val tools: Tools? = null,
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
            lockdown = (body["lockdown"] as? JsonObject)?.let(::lockdown),
            tools = (body["tools"] as? JsonObject)?.let(::tools),
        )
    }

    private fun lockdown(o: JsonObject): Lockdown? {
        val on = o.flag("on") ?: return null
        val last = o["last"] as? JsonObject
        return Lockdown(
            on = on,
            waiting = o.flag("waiting") == true,
            last = last?.text("message") ?: "",
            lastOutcome = last?.text("outcome") ?: "",
            why = o.text("why") ?: "",
            says = o.text("says") ?: if (on) LOCKDOWN_ON_SAYS else LOCKDOWN_OFF_SAYS,
        )
    }

    /**
     * Lockdown's box on the phone: its lines, and whether "Turn on Lockdown"
     * is offered - only while it is off. Never held on a stale link: it only
     * makes Jarvis ask more. Once on, the phone cannot turn it off; the
     * lines say where to.
     */
    data class LockdownView(val show: Boolean, val on: Boolean, val lines: List<String>, val canTurnOn: Boolean)

    fun lockdownView(k: Lockdown?): LockdownView {
        if (k == null) return LockdownView(false, false, emptyList(), false)
        val lines = buildList {
            add(k.says)
            if (k.why.isNotEmpty()) add(k.why.replaceFirstChar { it.uppercase() } + ".")
            if (k.waiting) add(LOCKDOWN_WAITING)
            else if (k.last.isNotEmpty() && k.lastOutcome != "off") add(k.last)
            if (k.on) add(LOCKDOWN_PC_ONLY)
        }
        return LockdownView(true, k.on, lines, canTurnOn = !k.on)
    }

    /** The one Lockdown body the phone sends: ON. Never OFF. */
    fun lockdownBody(): String = "{\"action\":\"$LOCKDOWN_ACTION\",\"ask\":true}"

    /**
     * Whether Lockdown is on, from `/api/version`'s `capabilities.lockdown`
     * or the `lockdown` event's data (`{"on": bool}`) - null for anything
     * else (an older PC).
     */
    fun lockdownFrom(o: JsonObject?): Boolean? = o?.flag("on")

    private fun tools(o: JsonObject): Tools? {
        val label = o.text("label") ?: return null
        val items = (o["items"] as? JsonArray)?.mapNotNull { el ->
            val it = el as? JsonObject ?: return@mapNotNull null
            val id = it.text("id") ?: return@mapNotNull null
            val last = (it["last"] as? JsonObject)?.text("message") ?: ""
            ToolSwitch(
                id = id,
                title = it.text("title") ?: id,
                group = it.text("group") ?: "",
                on = it.flag("on") == true,
                waiting = it.flag("waiting") == true,
                last = last,
            )
        } ?: emptyList()
        val byId = items.associateBy { it.id }
        val groups = (o["groups"] as? JsonArray)?.mapNotNull { el ->
            val g = el as? JsonObject ?: return@mapNotNull null
            val title = g.text("title") ?: ""
            val ids = (g["ids"] as? JsonArray)?.mapNotNull { id -> (id as? JsonPrimitive)?.contentOrNull } ?: emptyList()
            ToolGroup(title, ids.mapNotNull(byId::get))
        } ?: emptyList()
        val vaultObj = o["vault"] as? JsonObject
        val vault = vaultObj?.let {
            val title = it.text("title") ?: return@let null
            VaultSwitch(
                title = title,
                what = it.text("what") ?: "",
                on = it.flag("on") == true,
                waiting = it.flag("waiting") == true,
            )
        }
        val no = o["not_offered"] as? JsonObject
        val notOffered = no?.let {
            val labelsObj = it["labels"] as? JsonObject
            val labels = labelsObj?.entries?.mapNotNull { e ->
                val title = (e.value as? JsonPrimitive)?.takeIf { p -> p.isString }?.contentOrNull
                if (title.isNullOrEmpty()) null else e.key to title
            } ?: emptyList()
            ToolsNotOffered(labels = labels, why = it.text("why") ?: "")
        }
        return Tools(
            label = label,
            detail = o.text("detail") ?: "",
            canEnable = o.flag("can_enable") == true,
            groups = groups.ifEmpty { listOf(ToolGroup("", items)) },
            vault = vault,
            notOffered = notOffered,
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
