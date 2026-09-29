package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull

/**
 * "Chat with customer support for me" (the owner's decisions of 2026-09-28;
 * docs/CHATBOT-DRIVER-DESIGN.md "Customer-support chats"; docs/JARVIS-API.md
 * section 65; backend `jarvis_support.py` through `jarvis_chatbot_routes.py`).
 *
 * Jarvis chats with a company's customer support (Groupon first) in the
 * owner's name, in a browser window on the PC. ONE approval card lists
 * exactly which details it may give; EVERY offer gets its own card, and
 * nothing is accepted before the owner approves it; "are you a bot?" and
 * identity checks are handed to the owner, who answers in the window on the
 * PC. This phone starts one (the PC raises the card), shows the chat, Takes
 * over, Resumes (the task's own card) and Stops it, and answers a waiting
 * offer with Decline or "Say something else" - never Accept: accepting is
 * only ever the offer's own approval card. It keeps an ongoing notification
 * ("Chat with Groupon: offer waiting", with Stop) while one is going.
 *
 * The company's words and the summary are OUTSIDE TEXT: shown, never read
 * aloud, never offered to be remembered. Signing in, opening the company's
 * chat, and "Export transcript" happen on the PC only (ARCHITECTURE section
 * 8).
 *
 * Start, Decline and "Say something else" are held on a stale link (rule 4:
 * they make Jarvis send, or raise a card to); Stop and Take over are let
 * through.
 *
 * Pure Kotlin, no Android types, so `SupportTest` runs it on a plain JVM
 * against `contract/support-cases.json` - the PC's real answers, and the
 * PC's own words (`jarvis_support.WORDS`).
 */
object Support {
    const val STATUS_PATH = "/api/chatbot/status"
    const val START_PATH = "/api/chatbot/support/start"
    const val STOP_PATH = "/api/chatbot/support/stop"
    const val TAKEOVER_PATH = "/api/chatbot/support/takeover"
    const val ANSWER_PATH = "/api/chatbot/support/answer"

    /** The only routes [com.jarvis.client.net.JarvisApi.supportWrite] posts to. */
    val WRITE_PATHS = setOf(START_PATH, STOP_PATH, TAKEOVER_PATH, ANSWER_PATH)

    // ---- the words, the PC's own (jarvis_support.WORDS) -------------------

    const val TITLE = "Chat with customer support for me"
    const val DETAIL =
        "Jarvis chats with a company's customer support for you (Groupon first), in your name, " +
            "in a browser window on the PC. One approval card lists exactly which of your details " +
            "it may give. Every offer - a refund, a credit, a cancellation - gets its own card, and " +
            "nothing is accepted before you approve it."
    const val COMPANY_LABEL = "Company"
    const val ADDRESS_LABEL = "The company's help page (https://...)"
    const val GOAL_LABEL = "What should Jarvis get done?"
    const val GOAL_NOTE = "Jarvis writes its own messages from these words, in your name."
    const val DETAILS_LABEL = "Details Jarvis may give (one per row: a name and its exact value)"
    const val DETAILS_NOTE =
        "Never a password, PIN, security answer, card number or ID number: those are refused, " +
            "and if the agent asks, Jarvis hands it to you."
    const val DETAIL_NAME = "Name (like Order number)"
    const val DETAIL_VALUE = "Exact value"
    const val ADD_DETAIL = "Add a detail"
    const val REMOVE_DETAIL = "Remove"
    const val MESSAGES_LABEL = "Most messages"
    const val MINUTES_LABEL = "Most minutes of chat"
    const val QUEUE_LABEL = "Most minutes in the queue"
    const val START = "Start"
    const val START_NOTE = "Nothing is sent until you approve the card."
    const val TERMS_TITLE = "Terms risk"
    const val SIGN_IN_PC =
        "You sign in to your own account by hand in the window on the PC, and open the " +
            "company's chat there yourself (its Chat or Help button). Jarvis never types, sees or " +
            "keeps a password."
    const val TAKE_OVER = "Take over"
    const val TAKE_OVER_NOTE = "Jarvis stops sending; you type in the chat window on the PC."
    const val RESUME = "Resume"
    const val STOP = "Stop"
    const val OFFER_TITLE = "An offer is waiting for your answer"
    const val OFFER_NOTE =
        "Accepting is done only on the approval card, which shows the exact reply. Nothing is " +
            "accepted before you approve it."
    const val OFFER_CARD_NO = "The card was not approved: nothing was accepted. Choose what to do next."
    const val DECLINE = "Decline"
    const val SAY_ELSE = "Say something else"
    const val SAY_SEND = "Send"
    const val SAY_NOTE =
        "Your words go through the same check as Jarvis's. To accept, approve the card instead."
    const val HOLDING = "Jarvis told the agent \"One moment please\" {holds} of {most} times."
    const val QUEUE_LINE = "In the queue: number {position}"
    const val QUEUE_WAITING = "Waiting in the queue"
    const val WAITING_FOR_CHAT =
        "Open the chat on the company's help page in the window on the PC (its Chat or Help " +
            "button). Jarvis starts once it shows."
    const val AGENT_LINE = "Talking with {agent}"
    const val QUESTION_TITLE = "Handed to you"
    const val QUESTION_NOTE =
        "Jarvis never answers this. Answer it yourself in the chat window on the PC, then press " +
            "Resume - or Stop."
    const val TRANSCRIPT_TITLE = "The chat"
    const val OUTSIDE_NOTE =
        "The company's words are outside text: shown here, never learned from, never read aloud."
    const val WHO_JARVIS = "You (sent by Jarvis)"
    const val WHO_OWNER = "You"
    const val WHO_BUTTON = "You pressed"
    const val SUMMARY_TITLE = "What happened"
    const val SUMMARY_NOTE = "Written on this PC from the chat, so it is outside text too."
    const val AGREED_TITLE = "What they agreed to"
    const val OPEN_TITLE = "Still open"
    const val REFERENCE_LINE = "Reference number: {reference}"
    const val SAVED_YES = "Kept in your encrypted chat history on the PC."
    const val SAVED_NO = "Not kept in your chat history: {why}"
    const val EXPORT = "Export transcript"
    const val EXPORT_NOTE =
        "This file is NOT encrypted: anyone who can open it can read the whole chat, with the " +
            "details you allowed. Keep it somewhere safe, or delete it when you no longer need it."
    const val EXPORT_PC_ONLY = "Export transcript is on the PC only."
    const val HIDDEN = "The chat and your details are hidden until you confirm it is you."
    const val GONE =
        "That chat is gone from the screen: Jarvis on the PC restarted. The encrypted chat " +
            "history keeps a copy."
    const val MISSING =
        "Your PC's Jarvis cannot chat with customer support yet - run apply-patches.ps1 on the PC."
    const val VERSION = "Version"
    const val NOTIFY_RUNNING = "Chat with {company}: {used} of {max} messages"
    const val NOTIFY_OFFER = "Chat with {company}: offer waiting"
    const val NOTIFY_WAITING = "Waiting for your yes to chat with {company}"
    const val NOTIFY_PAUSED = "Paused: chat with {company}"
    const val NOTIFY_LOCKED = "Jarvis is chatting with customer support for you."

    /** Every sentence by the PC's own key, for `SupportTest`. */
    val WORDS: Map<String, String> = mapOf(
        "title" to TITLE, "detail" to DETAIL, "company_label" to COMPANY_LABEL,
        "address_label" to ADDRESS_LABEL, "goal_label" to GOAL_LABEL, "goal_note" to GOAL_NOTE,
        "details_label" to DETAILS_LABEL, "details_note" to DETAILS_NOTE,
        "detail_name" to DETAIL_NAME, "detail_value" to DETAIL_VALUE, "add_detail" to ADD_DETAIL,
        "remove_detail" to REMOVE_DETAIL, "messages_label" to MESSAGES_LABEL,
        "minutes_label" to MINUTES_LABEL, "queue_label" to QUEUE_LABEL, "start" to START,
        "start_note" to START_NOTE, "terms_title" to TERMS_TITLE, "sign_in_pc" to SIGN_IN_PC,
        "take_over" to TAKE_OVER, "take_over_note" to TAKE_OVER_NOTE, "resume" to RESUME,
        "stop" to STOP, "offer_title" to OFFER_TITLE, "offer_note" to OFFER_NOTE,
        "offer_card_no" to OFFER_CARD_NO, "decline" to DECLINE, "say_else" to SAY_ELSE,
        "say_send" to SAY_SEND, "say_note" to SAY_NOTE, "holding" to HOLDING,
        "queue_line" to QUEUE_LINE, "queue_waiting" to QUEUE_WAITING,
        "waiting_for_chat" to WAITING_FOR_CHAT, "agent_line" to AGENT_LINE,
        "question_title" to QUESTION_TITLE, "question_note" to QUESTION_NOTE,
        "transcript_title" to TRANSCRIPT_TITLE, "outside_note" to OUTSIDE_NOTE,
        "who_jarvis" to WHO_JARVIS, "who_owner" to WHO_OWNER, "who_button" to WHO_BUTTON,
        "summary_title" to SUMMARY_TITLE, "summary_note" to SUMMARY_NOTE,
        "agreed_title" to AGREED_TITLE, "open_title" to OPEN_TITLE,
        "reference_line" to REFERENCE_LINE, "saved_yes" to SAVED_YES, "saved_no" to SAVED_NO,
        "export" to EXPORT, "export_note" to EXPORT_NOTE, "export_pc_only" to EXPORT_PC_ONLY,
        "hidden" to HIDDEN, "gone" to GONE, "missing" to MISSING, "version" to VERSION,
        "notify_running" to NOTIFY_RUNNING, "notify_offer" to NOTIFY_OFFER,
        "notify_waiting" to NOTIFY_WAITING, "notify_paused" to NOTIFY_PAUSED,
        "notify_locked" to NOTIFY_LOCKED,
    )

    /** The PC's limits (jarvis_support.py); the PC checks them again. */
    const val MAX_GOAL_CHARS = 1000
    const val MAX_DETAILS = 12
    const val MAX_DETAIL_NAME = 40
    const val MAX_DETAIL_VALUE = 200
    const val MAX_SAY_CHARS = 1200

    /** How often Brain's card and the notification read again while a chat is going. */
    const val POLL_MS = 4000L

    val LIVE = setOf("asking", "approved", "running", "paused")

    val STATE_WORDS = mapOf(
        "asking" to "Waiting for your yes on the approval card.",
        "approved" to "Approved - starting.",
        "running" to "Chatting now.",
        "paused" to "Paused.",
        "done" to "Finished.",
        "stopped" to "Stopped.",
        "refused" to "Not started.",
    )

    /** A company the PC offers; [typed] is "another company", whose help page the owner types. */
    data class Company(val id: String, val name: String, val host: String, val helpUrl: String,
                       val terms: String) {
        val typed: Boolean get() = id == "other"
    }

    data class Tier(
        val id: String,
        val name: String,
        val words: String,
        val messagesDefault: Int,
        val messagesMax: Int,
        val minutesDefault: Int,
        val minutesMax: Int,
        val queueDefault: Int,
        val queueMax: Int,
    )

    /** One line of the chat. [outside]: the company's words (always, whatever the flag). */
    data class Turn(val who: String, val text: String, val outside: Boolean,
                    val button: Boolean = false)

    /** A waiting offer. [card]: "waiting" (its card is up), "no" (not approved), "yes". */
    data class Offer(val id: Int, val words: String, val reply: String, val state: String,
                     val card: String, val holds: Int, val holdsMost: Int, val said: String)

    data class Summary(val answer: String, val agreed: List<String>, val open: List<String>)

    data class Detail(val name: String, val value: String)

    data class Chat(
        val id: String,
        val companyName: String,
        val goal: String,
        val details: List<Detail>,
        val state: String,
        val tierName: String,
        val used: Int,
        val max: Int,
        val minutesUsed: Double,
        val maxMinutes: Int,
        val queueMinutes: Double,
        val maxQueue: Int,
        val inQueue: Boolean,
        val queuePosition: Int?,
        val agent: String,
        val waitingForChat: Boolean,
        /** The pause's words, only while it is really paused. */
        val paused: String,
        val pausedCode: String,
        val takeOver: Boolean,
        val ended: String,
        val question: String,
        val offer: Offer?,
        val reference: String,
        val summary: Summary?,
        val saved: String,
        val transcript: List<Turn>,
        val hidden: Boolean,
    ) {
        val live: Boolean get() = state in LIVE
    }

    data class View(val companies: List<Company>, val tier: Tier, val chat: Chat?)

    /** `GET /api/chatbot/status`, read - or null for a PC without support chats. */
    fun parse(body: JsonObject): View? {
        if (body.flag("available") == false) return null
        val cos = body["companies"] as? JsonArray ?: return null
        val t = body["support_tier"] as? JsonObject ?: return null
        val companies = cos.mapNotNull { it as? JsonObject }.mapNotNull { c ->
            val id = c.text("id") ?: return@mapNotNull null
            Company(id, c.text("name") ?: id, c.text("host") ?: "", c.text("help_url") ?: "",
                c.text("terms") ?: "")
        }
        val tier = Tier(
            id = t.text("id") ?: "",
            name = t.text("name") ?: "",
            words = t.text("words") ?: "",
            messagesDefault = t.num("messages_default")?.toInt() ?: 15,
            messagesMax = t.num("messages_max")?.toInt() ?: 25,
            minutesDefault = t.num("minutes_default")?.toInt() ?: 30,
            minutesMax = t.num("minutes_max")?.toInt() ?: 45,
            queueDefault = t.num("queue_default")?.toInt() ?: 45,
            queueMax = t.num("queue_max")?.toInt() ?: 120,
        )
        return View(companies, tier, parseChat(body["support"] as? JsonObject))
    }

    private fun JsonObject.objects(key: String): List<JsonObject> =
        (this[key] as? JsonArray).orEmpty().mapNotNull { it as? JsonObject }

    private fun JsonObject.texts(key: String): List<String> =
        (this[key] as? JsonArray).orEmpty().mapNotNull {
            (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.contentOrNull?.trim()
                ?.takeIf { s -> s.isNotEmpty() }
        }

    fun parseChat(o: JsonObject?): Chat? {
        if (o == null) return null
        val id = o.text("id") ?: return null
        val state = o.text("state") ?: return null
        val turns = o.objects("transcript").mapNotNull { t ->
            val who = t.text("who")?.takeIf { it in setOf("jarvis", "owner", "company", "system", "note") }
                ?: return@mapNotNull null
            Turn(who, t.raw("text") ?: "",
                who == "company" || who == "system" || t.flag("outside_text") == true,
                t.flag("button") == true)
        }
        val offer = if (state == "running") {
            (o["offer"] as? JsonObject)?.let { x ->
                val oid = x.num("id")?.toInt() ?: return@let null
                Offer(oid, x.raw("words") ?: "", x.raw("reply") ?: "", x.text("state") ?: "",
                    x.text("card") ?: "waiting", x.num("holds")?.toInt() ?: 0,
                    x.num("holds_most")?.toInt() ?: 3, x.text("said") ?: "")
            }
        } else {
            null
        }
        val summary = (o["summary"] as? JsonObject)?.let { s ->
            Summary(s.text("answer") ?: "", s.texts("agreed"), s.texts("open"))
        }
        return Chat(
            id = id,
            companyName = o.text("company_name") ?: "the company",
            goal = o.raw("goal") ?: "",
            details = o.objects("details").mapNotNull { d ->
                val n = d.text("name") ?: return@mapNotNull null
                Detail(n, d.raw("value") ?: "")
            },
            state = state,
            tierName = o.text("tier_name") ?: "",
            used = o.num("messages_used")?.toInt() ?: 0,
            max = o.num("max_messages")?.toInt() ?: 0,
            minutesUsed = o.num("minutes_used") ?: 0.0,
            maxMinutes = o.num("max_minutes")?.toInt() ?: 0,
            queueMinutes = o.num("queue_minutes") ?: 0.0,
            maxQueue = o.num("max_queue_minutes")?.toInt() ?: 0,
            inQueue = o.flag("in_queue") == true,
            queuePosition = o.num("queue_position")?.toInt(),
            agent = o.text("agent") ?: "",
            waitingForChat = o.flag("waiting_for_chat") == true,
            paused = if (state == "paused") o.text("paused") ?: "" else "",
            pausedCode = if (state == "paused") o.text("paused_code") ?: "" else "",
            takeOver = o.flag("take_over") == true,
            ended = o.text("ended") ?: "",
            question = o.text("question") ?: "",
            offer = offer,
            reference = o.text("reference") ?: "",
            summary = summary,
            saved = o.text("saved") ?: "",
            transcript = turns,
            hidden = o.flag("hidden") == true,
        )
    }

    fun versionLine(v: View): String =
        if (v.tier.name.isEmpty()) "" else "$VERSION: ${v.tier.name}" +
            (if (v.tier.words.isNotEmpty()) " - ${v.tier.words}" else "")

    /** A limit typed, or null when it is not 1 to [most]. */
    fun limitOf(text: String, most: Int): Int? {
        val s = text.trim()
        if (!Regex("^\\d{1,3}$").matches(s)) return null
        val n = s.toInt()
        return if (n in 1..most) n else null
    }

    /** The rows typed, tidied: blank rows dropped, names' spaces collapsed. */
    fun detailRows(rows: List<Detail>): List<Detail> =
        rows.map { Detail(it.name.split(Regex("\\s+")).filter { w -> w.isNotEmpty() }.joinToString(" "),
            it.value.trim()) }.filter { it.name.isNotEmpty() || it.value.isNotEmpty() }

    /** What is wrong with the form, in a sentence, or null when it can be sent. */
    fun formProblem(v: View, company: String, address: String, goal: String, rows: List<Detail>,
                    messages: String, minutes: String, queue: String): String? {
        val co = v.companies.firstOrNull { it.id == company } ?: return "Choose a company."
        if (co.typed && !Regex("^https://[^\\s/]+\\.[^\\s/]+", RegexOption.IGNORE_CASE)
                .containsMatchIn(address.trim())) {
            return "Type the company's help page, starting with https://"
        }
        val g = goal.trim()
        if (g.isEmpty()) return "Say what Jarvis should get done."
        if (g.length > MAX_GOAL_CHARS) return "The goal is longer than $MAX_GOAL_CHARS characters."
        val d = detailRows(rows)
        if (d.size > MAX_DETAILS) return "At most $MAX_DETAILS details."
        for (r in d) {
            if (r.name.isEmpty()) return "Every detail needs a name, like \"Order number\"."
            if (r.value.isEmpty()) return "The detail \"${r.name}\" has no value."
            if (r.name.length > MAX_DETAIL_NAME) return "A detail's name is longer than $MAX_DETAIL_NAME characters."
            if (r.value.length > MAX_DETAIL_VALUE) return "The detail \"${r.name}\" is longer than $MAX_DETAIL_VALUE characters."
        }
        if (limitOf(messages, v.tier.messagesMax) == null) {
            return "Most messages: 1 to ${v.tier.messagesMax} in this version."
        }
        if (limitOf(minutes, v.tier.minutesMax) == null) {
            return "Most minutes of chat: 1 to ${v.tier.minutesMax} in this version."
        }
        if (limitOf(queue, v.tier.queueMax) == null) {
            return "Most minutes in the queue: 1 to ${v.tier.queueMax}."
        }
        return null
    }

    /** The buttons for a chat, in order. Stop is always there while it is going. */
    fun actionsOf(c: Chat?): List<String> = when {
        c == null || !c.live -> emptyList()
        c.state == "paused" -> listOf("resume", "stop")
        c.state == "running" -> listOf("take_over", "stop")
        else -> listOf("stop")
    }

    /** The waiting offer's buttons - never an Accept (that is only the card). */
    fun offerActions(c: Chat?): List<String> =
        if (c?.offer?.state == "waiting") listOf("decline", "say_else", "take_over") else emptyList()

    fun labelOf(action: String): String = when (action) {
        "take_over" -> TAKE_OVER
        "resume" -> RESUME
        "stop" -> STOP
        "decline" -> DECLINE
        "say_else" -> SAY_ELSE
        else -> action
    }

    fun statusLine(c: Chat): String = when {
        c.state == "paused" && c.paused.isNotEmpty() -> c.paused
        !c.live && c.ended.isNotEmpty() -> c.ended
        c.state == "running" && c.waitingForChat -> WAITING_FOR_CHAT
        c.state == "running" && c.inQueue ->
            c.queuePosition?.let { QUEUE_LINE.replace("{position}", it.toString()) } ?: QUEUE_WAITING
        c.state == "running" && c.agent.isNotEmpty() -> AGENT_LINE.replace("{agent}", c.agent)
        else -> STATE_WORDS[c.state] ?: c.state
    }

    /** The ongoing notification's line ("Chat with Groupon: offer waiting"), or "". */
    fun talkingLine(c: Chat?): String {
        if (c == null || !c.live) return ""
        fun fill(w: String) = w.replace("{company}", c.companyName).replace("{used}", c.used.toString())
            .replace("{max}", c.max.toString())
        return when {
            c.state == "asking" -> fill(NOTIFY_WAITING)
            c.state == "paused" -> fill(NOTIFY_PAUSED)
            c.offer != null -> fill(NOTIFY_OFFER)
            else -> fill(NOTIFY_RUNNING)
        }
    }

    private fun number(d: Double): String =
        if (d == Math.floor(d)) d.toLong().toString() else d.toString()

    fun progressLine(c: Chat): String =
        "Message ${c.used} of ${c.max} · ${number(c.minutesUsed)} of ${c.maxMinutes} minutes · " +
            "${number(c.queueMinutes)} of ${c.maxQueue} minutes in the queue"

    fun holdingLine(c: Chat?): String {
        val o = c?.offer ?: return ""
        if (o.holds == 0) return ""
        return HOLDING.replace("{holds}", o.holds.toString()).replace("{most}", o.holdsMost.toString())
    }

    /** Who a line is from, as shown. */
    fun whoOf(t: Turn, c: Chat): String = when (t.who) {
        "jarvis" -> if (t.button) WHO_BUTTON else WHO_JARVIS
        "owner" -> WHO_OWNER
        "note" -> "Note"
        else -> c.companyName
    }

    fun savedLine(c: Chat): String = when {
        c.saved.isEmpty() -> ""
        c.saved == "yes" -> SAVED_YES
        else -> SAVED_NO.replace("{why}", c.saved)
    }

    /** Whether an activity line may be a support chat's ("Chat with Groupon: message 2 of 15."). */
    fun isSupportActivity(detail: String?): Boolean {
        val d = detail ?: return false
        return d.startsWith("Chat with ") || d.startsWith("Open the chat on ") ||
            d.startsWith("Continuing support_chat")
    }

    private val ID = Regex("^sup_[0-9a-f]{12}$")

    fun validId(id: String): Boolean = ID.matches(id)

    private fun quote(s: String): String =
        JarvisJson.encodeToString(kotlinx.serialization.serializer<String>(), s)

    /** `POST /api/chatbot/support/start`'s body, or null when something in it cannot be sent. */
    fun startBody(company: String, address: String?, goal: String, rows: List<Detail>,
                  maxMessages: Int?, maxMinutes: Int?, maxQueueMinutes: Int?): String? {
        if (!Regex("^[a-z0-9_]{1,40}$").matches(company)) return null
        val g = goal.trim()
        if (g.isEmpty() || g.length > MAX_GOAL_CHARS) return null
        val d = detailRows(rows)
        if (d.size > MAX_DETAILS || d.any {
                it.name.isEmpty() || it.value.isEmpty() || it.name.length > MAX_DETAIL_NAME ||
                    it.value.length > MAX_DETAIL_VALUE || it.value.contains('\n')
            }) {
            return null
        }
        val details = d.joinToString(",", prefix = "[", postfix = "]") {
            "{\"name\":${quote(it.name)},\"value\":${quote(it.value)}}"
        }
        val parts = mutableListOf("\"company\":${quote(company)}", "\"goal\":${quote(g)}",
            "\"details\":$details")
        if (company == "other") {
            val a = address?.trim().orEmpty()
            if (!a.startsWith("https://") || a.length > 500) return null
            parts.add("\"address\":${quote(a)}")
        }
        if (maxMessages != null) parts.add("\"max_messages\":$maxMessages")
        if (maxMinutes != null) parts.add("\"max_minutes\":$maxMinutes")
        if (maxQueueMinutes != null) parts.add("\"max_queue_minutes\":$maxQueueMinutes")
        return parts.joinToString(",", prefix = "{", postfix = "}")
    }

    /** `POST .../stop` or `.../takeover`'s body, or null for an id that is not the PC's shape. */
    fun idBody(id: String): String? = if (validId(id)) "{\"id\":${quote(id)}}" else null

    /**
     * `POST /api/chatbot/support/answer`'s body: decline, say or takeover -
     * never accept (that is only ever the offer's own card).
     */
    fun answerBody(id: String, offer: Int, choice: String, text: String?): String? {
        if (!validId(id)) return null
        val parts = mutableListOf("\"id\":${quote(id)}", "\"offer\":$offer", "\"choice\":${quote(choice)}")
        when (choice) {
            "decline", "takeover" -> {}
            "say" -> {
                val t = text.orEmpty().split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")
                if (t.isEmpty() || t.length > MAX_SAY_CHARS) return null
                parts.add("\"text\":${quote(t)}")
            }
            else -> return null
        }
        return parts.joinToString(",", prefix = "{", postfix = "}")
    }

    /** Whether it went through, and the PC's sentence to show. */
    fun said(reply: Chatbot.Reply): Pair<Boolean, String> {
        val b = reply.body
        val error = b?.text("error")
        return when {
            reply.code in 200..299 && b?.flag("ok") != false ->
                true to (b?.text("message") ?: "Done.")
            reply.code == 404 && b?.flag("ok") == false && error != null -> false to error
            reply.code == 404 || reply.code == 501 -> false to MISSING
            error != null -> false to error
            else -> false to "Not changed (HTTP ${reply.code})."
        }
    }

    private fun JsonObject.num(key: String): Double? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.doubleOrNull
            ?.takeIf { it.isFinite() }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.raw(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
