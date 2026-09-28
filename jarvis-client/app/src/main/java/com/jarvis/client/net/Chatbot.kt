package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull

/**
 * "Talk to a chatbot for me" (the owner's decisions of 2026-09-27 and
 * 2026-09-28; docs/CHATBOT-DRIVER-DESIGN.md; docs/JARVIS-API.md section 60;
 * backend `jarvis_chatbot.py` and `jarvis_chatbot_routes.py`,
 * `chatbot-routes.patch`).
 *
 * Jarvis asks an AI chatbot (Gemini first) about something for the owner and
 * writes its own follow-ups on the PC, within limits approved on ONE card.
 * This phone starts one (the PC raises the card - nothing is sent before a
 * yes), shows the conversation, Pauses, Resumes (its own card) and Stops it,
 * asks for new limits (a NEW card), and keeps an ongoing notification
 * ("Talking to Gemini, 3 of 5" with Stop) while one is going.
 *
 * The chatbot's words and the end summary are OUTSIDE TEXT: shown, never
 * read aloud, never offered to be remembered. Signing in to the chatbot's
 * account happens on the PC only (ARCHITECTURE section 8).
 *
 * "Ask several and compare" (backend `jarvis_chatbot_compare.py`): the same
 * form asks two or more chatbots the same goal - ONE card listing every one,
 * one conversation each, one after another - and the PC writes ONE summary
 * (where they agree, where they disagree and who said what, the sources each
 * gave, who dropped out and why). Pause / Resume / Stop act on the whole
 * comparison. The summary is outside text too.
 *
 * Start (single or compare), Resume and new limits are held on a stale link
 * (rule 4: they make Jarvis send, or raise a card to); Pause and Stop are
 * let through.
 *
 * Pure Kotlin, no Android types, so `ChatbotTest` runs it on a plain JVM
 * against `contract/chatbot-cases.json` - the PC's real answers, and the
 * PC's own words (`jarvis_chatbot_routes.WORDS`).
 */
object Chatbot {
    const val STATUS_PATH = "/api/chatbot/status"
    const val START_PATH = "/api/chatbot/start"
    const val STOP_PATH = "/api/chatbot/stop"
    const val LIMITS_PATH = "/api/chatbot/limits"
    const val COMPARE_START_PATH = "/api/chatbot/compare/start"
    const val COMPARE_STOP_PATH = "/api/chatbot/compare/stop"

    /** The only routes [com.jarvis.client.net.JarvisApi.chatbotWrite] posts to. */
    val WRITE_PATHS = setOf(START_PATH, STOP_PATH, LIMITS_PATH, COMPARE_START_PATH, COMPARE_STOP_PATH)

    // ---- the words, the PC's own (jarvis_chatbot_routes.WORDS) ----------

    const val TITLE = "Talk to a chatbot for me"
    const val DETAIL =
        "Jarvis asks an AI chatbot about something for you, and writes its own " +
            "follow-up questions on this PC, within limits you set. One approval card " +
            "covers the whole conversation. While it does this, Jarvis knows only your " +
            "goal - not your memory, email, calendar, notes or files."
    const val CHATBOT_LABEL = "Chatbot"
    const val GOAL_LABEL = "What should Jarvis find out?"
    const val GOAL_NOTE = "These words will be sent to the chatbot exactly as you type them."
    const val MESSAGES_LABEL = "Most messages"
    const val MINUTES_LABEL = "Most minutes"
    const val NEVER_LABEL = "Words it must never send (optional, separated by commas)"
    const val START = "Start"
    const val START_NOTE = "Nothing is sent until you approve the card."
    const val PAUSE = "Pause"
    const val RESUME = "Resume"
    const val STOP = "Stop"
    const val CHANGE_LIMITS = "Change limits"
    const val LIMITS_NOTE = "A change to the limits needs a new approval card."
    const val TRANSCRIPT_TITLE = "The conversation"
    const val OUTSIDE_NOTE =
        "The chatbot's words are outside text: shown here, never learned from, " +
            "never read aloud."
    const val SUMMARY_TITLE = "What Jarvis found"
    const val SUMMARY_NOTE =
        "Written on this PC from the chatbot's words, so it is outside text too. Once it ends, th" +
            "e conversation and this summary are kept in History, marked as outside text."
    const val CLAIM_SOURCED = "it gave a source (not checked by Jarvis)"
    const val CLAIM_UNSOURCED = "no source given"
    const val OPEN_TITLE = "Still open"
    const val QUESTION_TITLE = "The chatbot asked about you"
    const val QUESTION_NOTE =
        "Jarvis never answers questions about you. It is shown here for you to " +
            "decide."
    const val NONE_BUILT =
        "No chatbot can be reached from this PC yet. The line beside each one " +
            "says what is missing. Start waits until one can."
    const val SIGN_IN_PC =
        "Signing in to the chatbot's account happens on the PC only, in the " +
            "browser window Jarvis uses."
    const val MISSING =
        "Your PC's Jarvis cannot talk to chatbots yet - run apply-patches.ps1 on " +
            "the PC."
    const val GONE =
        "That conversation is no longer in memory: Jarvis on the PC restarted. A conversation " +
            "that finished is kept in History."
    const val HIDDEN = "The goal and the conversation are hidden until you confirm it is you."
    const val VERSION = "Version"
    const val NOTIFY_RUNNING = "Talking to {name}, {used} of {max}"
    const val NOTIFY_WAITING = "Waiting for your yes to talk to {name}"
    const val NOTIFY_PAUSED = "Paused: talking to {name}, {used} of {max}"
    const val NOTIFY_LOCKED = "Jarvis is talking to a chatbot for you."
    const val COMPARE_TOGGLE = "Ask several and compare"
    const val COMPARE_DETAIL =
        "Jarvis asks two or more chatbots the same goal, one after another, each in its own " +
            "conversation under the same limits. One approval card lists every chatbot it will ask. " +
            "At the end, one summary shows where they agree, where they disagree, and the sources " +
            "each gave."
    const val COMPARE_PICK = "Chatbots to ask (pick {min} to {max})"
    const val COMPARE_LIMITS_NOTE = "Most messages and most minutes apply to each chatbot on its own."
    const val COMPARE_TITLE = "Comparing chatbots"
    const val COMPARE_SUMMARY_TITLE = "Where they agree and disagree"
    const val COMPARE_SUMMARY_NOTE =
        "Written on this PC from the chatbots' words, so it is outside text too. Once it ends, ev" +
            "ery conversation and this summary are kept in History, marked as outside text."
    const val AGREE_TITLE = "They agree"
    const val DISAGREE_TITLE = "They disagree"
    const val SOURCES_TITLE = "Sources each gave (not checked by Jarvis)"
    const val DROPPED_TITLE = "Dropped out"
    const val CONVERSATIONS_TITLE = "Each conversation"
    const val COMPARE_TOO_FEW = "Pick at least {min} chatbots to compare."
    const val COMPARE_TOO_MANY = "Pick at most {max} chatbots in this version."
    const val COMPARE_NOT_ENOUGH =
        "Fewer than two chatbots can be reached from this PC, so there is nothing to compare yet."
    const val COMPARE_GONE =
        "That comparison is no longer in memory: Jarvis on the PC restarted. A comparison " +
            "that finished is kept in History."
    const val NOTIFY_COMPARE_RUNNING = "Comparing {count} chatbots: asking {name}, {at} of {count}"
    const val NOTIFY_COMPARE_WAITING = "Waiting for your yes to ask {count} chatbots"
    const val NOTIFY_COMPARE_PAUSED = "Paused: comparing {count} chatbots"
    const val MEMBER_WAITING = "Waiting its turn."
    const val KIND_WEBSITE = "Websites (a browser window on the PC)"
    const val KIND_API = "With a key (each message costs a little)"
    const val KIND_LOCAL = "On this PC"
    const val USAGE_LINE =
        "Used so far: {requests}, {tokens} word-pieces (tokens), model {model}, about {cost}"
    /** An API service's monthly money limit; the amounts are the PC's own ("$4.02"). */
    const val MONEY_LEFT =
        "About {left} of {limit} left this month for {company} (prices are estimates you can " +
            "correct on the PC)."
    const val MONEY_PC_ONLY =
        "Each service with a key needs a monthly money limit before Jarvis uses it. Limits and " +
            "prices are set on the PC only, like keys; the amounts are estimates."
    /** Under an answer the money limit's answer-length cap cut short (the PC's `cut_off`). */
    const val CUT_OFF =
        "Jarvis asked for a short answer so it stays within your limit; the rest was cut off."

    /** Every sentence above by the PC's own key, for ChatbotTest. */
    val WORDS: Map<String, String> = mapOf(
        "title" to TITLE, "detail" to DETAIL, "chatbot_label" to CHATBOT_LABEL,
        "goal_label" to GOAL_LABEL, "goal_note" to GOAL_NOTE, "messages_label" to MESSAGES_LABEL,
        "minutes_label" to MINUTES_LABEL, "never_label" to NEVER_LABEL, "start" to START,
        "start_note" to START_NOTE, "pause" to PAUSE, "resume" to RESUME, "stop" to STOP,
        "change_limits" to CHANGE_LIMITS, "limits_note" to LIMITS_NOTE,
        "transcript_title" to TRANSCRIPT_TITLE, "outside_note" to OUTSIDE_NOTE,
        "summary_title" to SUMMARY_TITLE, "summary_note" to SUMMARY_NOTE,
        "claim_sourced" to CLAIM_SOURCED, "claim_unsourced" to CLAIM_UNSOURCED,
        "open_title" to OPEN_TITLE, "question_title" to QUESTION_TITLE,
        "question_note" to QUESTION_NOTE, "none_built" to NONE_BUILT, "sign_in_pc" to SIGN_IN_PC,
        "missing" to MISSING, "gone" to GONE, "hidden" to HIDDEN, "version" to VERSION,
        "notify_running" to NOTIFY_RUNNING, "notify_waiting" to NOTIFY_WAITING,
        "notify_paused" to NOTIFY_PAUSED, "notify_locked" to NOTIFY_LOCKED,
        "compare_toggle" to COMPARE_TOGGLE, "compare_detail" to COMPARE_DETAIL,
        "compare_pick" to COMPARE_PICK, "compare_limits_note" to COMPARE_LIMITS_NOTE,
        "compare_title" to COMPARE_TITLE, "compare_summary_title" to COMPARE_SUMMARY_TITLE,
        "compare_summary_note" to COMPARE_SUMMARY_NOTE, "agree_title" to AGREE_TITLE,
        "disagree_title" to DISAGREE_TITLE, "sources_title" to SOURCES_TITLE,
        "dropped_title" to DROPPED_TITLE, "conversations_title" to CONVERSATIONS_TITLE,
        "compare_too_few" to COMPARE_TOO_FEW, "compare_too_many" to COMPARE_TOO_MANY,
        "compare_not_enough" to COMPARE_NOT_ENOUGH, "compare_gone" to COMPARE_GONE,
        "notify_compare_running" to NOTIFY_COMPARE_RUNNING,
        "notify_compare_waiting" to NOTIFY_COMPARE_WAITING,
        "notify_compare_paused" to NOTIFY_COMPARE_PAUSED, "member_waiting" to MEMBER_WAITING,
        "kind_website" to KIND_WEBSITE, "kind_api" to KIND_API, "kind_local" to KIND_LOCAL,
        "usage_line" to USAGE_LINE, "money_left" to MONEY_LEFT, "money_pc_only" to MONEY_PC_ONLY,
        "cut_off" to CUT_OFF,
    )

    /** How each chatbot is reached (`kind`), in the order the chooser groups them. */
    val KINDS = listOf("website", "api", "local")

    /** The states in which a conversation is still going. */
    val LIVE = setOf("asking", "approved", "running", "paused")

    /** Held on a stale link: they make Jarvis send, or raise a card to. */
    val HELD_WHEN_STALE = setOf("start", "resume", "limits")

    /** How often the plate and the notification read again while one is live. */
    const val POLL_MS = 4000L

    /** The longest goal the PC takes, and the never-send limits. */
    const val MAX_GOAL_CHARS = 1000
    const val MAX_NEVER = 50
    const val MAX_NEVER_CHARS = 60

    /** What each state is called on screen (the desktop's chatbot.js STATE_WORDS). */
    val STATE_WORDS = mapOf(
        "asking" to "Waiting for your yes on the approval card.",
        "approved" to "Approved - starting.",
        "running" to "Talking now.",
        "paused" to "Paused.",
        "done" to "Finished.",
        "stopped" to "Stopped.",
        "refused" to "Not started.",
    )

    /**
     * [built] means "can be used now": built AND set up on the PC (`ready`,
     * e.g. Gemini's window signed in). [made] is built at all.
     */
    data class Choice(val id: String, val name: String, val host: String, val built: Boolean,
                      val note: String, val made: Boolean = built,
                      /** "website", "api" or "local"; an older PC sends none (all websites). */
                      val kind: String = "website",
                      /** An API service's money limit this month, or null (none set, or not an API). */
                      val money: Money? = null)

    /**
     * An API service's monthly money limit, as the PC wrote it ("$4.02"). Set
     * on the PC only (its command line, like keys); the phone only shows it.
     */
    data class Money(val company: String, val limit: String, val left: String, val spent: String,
                     val until: String, val reached: Boolean)

    /** One of the chooser's groups: its heading ("" for a kind this app does not know). */
    data class Group(val kind: String, val title: String, val chatbots: List<Choice>)

    /**
     * What an API (or local) conversation has used so far. [cost] is the PC's
     * own estimate as it writes it ("$0.03"); "" from an older PC.
     */
    data class Usage(val requests: Int, val tokens: Long, val model: String, val cost: String = "")

    data class Tier(
        val id: String,
        val name: String,
        val words: String,
        val why: String,
        val turnsDefault: Int,
        val turnsMax: Int,
        val minutesDefault: Int,
        val minutesMax: Int,
        /** How many chatbots one comparison may ask; [compareMax] 0 is an older PC (none). */
        val compareMin: Int = 2,
        val compareMax: Int = 0,
    )

    /** One message. [cutOff]: a chatbot's answer the money limit's cap cut short. */
    data class Turn(
        val who: String,
        val n: Int,
        val text: String,
        val outside: Boolean,
        val cutOff: Boolean = false,
    )

    data class Claim(val claim: String, val sourced: Boolean)

    data class Summary(val answer: String, val claims: List<Claim>, val open: List<String>)

    data class Session(
        val id: String,
        val chatbot: String,
        val name: String,
        val goal: String,
        val state: String,
        val tierName: String,
        val used: Int,
        val max: Int,
        val minutesUsed: Double,
        val maxMinutes: Int,
        val never: List<String>,
        /** The pause's words, only while it is really paused (the PC keeps them after a stop). */
        val paused: String,
        val ended: String,
        val question: String,
        val summary: Summary?,
        val transcript: List<Turn>,
        val usage: Usage? = null,
    ) {
        val live: Boolean get() = state in Chatbot.LIVE
    }

    data class LimitsNote(val waiting: Boolean, val said: String)

    /** One chatbot's view on a point the chatbots disagree about. */
    data class Opinion(val who: String, val said: String)

    data class Disagreement(val point: String, val views: List<Opinion>)

    /** The sources one chatbot gave - never checked by Jarvis. */
    data class Sources(val who: String, val items: List<String>)

    data class Dropped(val who: String, val why: String)

    data class CompareSummary(
        val answer: String,
        val agree: List<String>,
        val disagree: List<Disagreement>,
        val sources: List<Sources>,
        val dropped: List<Dropped>,
        val open: List<String>,
    )

    data class BotName(val id: String, val name: String)

    /** "Ask several and compare": one comparison, with every conversation in it. */
    data class Compare(
        val id: String,
        val goal: String,
        val state: String,
        val tierName: String,
        val chatbots: List<BotName>,
        val count: Int,
        val current: Int,
        val currentName: String,
        val used: Int,
        val max: Int,
        val maxMinutes: Int,
        val never: List<String>,
        /** The pause's words, only while it is really paused. */
        val paused: String,
        val ended: String,
        val summary: CompareSummary?,
        val members: List<Session>,
    ) {
        val live: Boolean get() = state in Chatbot.LIVE
    }

    data class View(
        val chatbots: List<Choice>,
        val tier: Tier,
        val session: Session?,
        val limits: LimitsNote,
        val compare: Compare? = null,
    ) {
        val anyBuilt: Boolean get() = chatbots.any { it.built }

        /** Enough chatbots can be reached now, and the PC knows comparisons. */
        val canCompare: Boolean
            get() = tier.compareMax >= tier.compareMin && chatbots.count { it.built } >= tier.compareMin
    }

    /** `GET /api/chatbot/status`, read - or null when it is not one (an older PC). */
    fun parse(body: JsonObject): View? {
        if (body.flag("available") == false) return null
        val bots = body["chatbots"] as? JsonArray ?: return null
        val t = body["tier"] as? JsonObject ?: return null
        val chatbots = bots.mapNotNull { it as? JsonObject }.mapNotNull { c ->
            val id = c.text("id") ?: return@mapNotNull null
            val made = c.flag("built") == true
            Choice(id, c.text("name") ?: id, c.text("host") ?: "",
                made && c.flag("ready") != false, c.text("note") ?: "", made,
                c.text("kind") ?: "website", parseMoney(c["money"] as? JsonObject))
        }
        val lim = body["limits"] as? JsonObject
        return View(
            chatbots = chatbots,
            tier = Tier(
                id = t.text("id") ?: "",
                name = t.text("name") ?: "",
                words = t.text("words") ?: "",
                why = t.text("why") ?: "",
                turnsDefault = t.num("turns_default")?.toInt() ?: 5,
                turnsMax = t.num("turns_max")?.toInt() ?: 8,
                minutesDefault = t.num("minutes_default")?.toInt() ?: 10,
                minutesMax = t.num("minutes_max")?.toInt() ?: 15,
                compareMin = t.num("compare_min")?.toInt() ?: 2,
                compareMax = t.num("compare_max")?.toInt() ?: 0,
            ),
            session = parseSession(body["session"] as? JsonObject),
            limits = LimitsNote(lim?.flag("waiting") == true, lim?.text("said") ?: ""),
            compare = parseCompare(body["compare"] as? JsonObject),
        )
    }

    private fun JsonObject.texts(key: String): List<String> =
        (this[key] as? JsonArray)?.mapNotNull {
            (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.contentOrNull?.trim()
                ?.takeIf { x -> x.isNotEmpty() }
        } ?: emptyList()

    private fun JsonObject.objects(key: String): List<JsonObject> =
        (this[key] as? JsonArray)?.mapNotNull { it as? JsonObject } ?: emptyList()

    /** A comparison as the PC described it, or null. */
    fun parseCompare(o: JsonObject?): Compare? {
        if (o == null) return null
        val id = o.text("id") ?: return null
        val state = o.text("state") ?: return null
        val sum = (o["summary"] as? JsonObject)?.let { s ->
            CompareSummary(
                answer = s.text("answer") ?: "",
                agree = s.texts("agree"),
                disagree = s.objects("disagree").mapNotNull { d ->
                    val point = d.text("point") ?: return@mapNotNull null
                    val views = d.objects("views").mapNotNull { v ->
                        val who = v.text("who") ?: return@mapNotNull null
                        val said = v.text("said") ?: return@mapNotNull null
                        Opinion(who, said)
                    }
                    if (views.isEmpty()) null else Disagreement(point, views)
                },
                // Every source is the chatbot's own and NOT checked by Jarvis.
                sources = s.objects("sources").mapNotNull { x ->
                    val who = x.text("who") ?: return@mapNotNull null
                    val items = x.texts("items")
                    if (items.isEmpty()) null else Sources(who, items)
                },
                dropped = s.objects("dropped").mapNotNull { x ->
                    x.text("who")?.let { Dropped(it, x.text("why") ?: "") }
                },
                open = s.texts("open"),
            )
        }
        val bots = o.objects("chatbots").mapNotNull { b ->
            val bid = b.text("id") ?: return@mapNotNull null
            BotName(bid, b.text("name") ?: bid)
        }
        return Compare(
            id = id,
            goal = o.raw("goal") ?: "",
            state = state,
            tierName = o.text("tier_name") ?: "",
            chatbots = bots,
            count = o.num("count")?.toInt() ?: bots.size,
            current = o.num("current")?.toInt() ?: 0,
            currentName = o.text("current_name") ?: "",
            used = o.num("messages_used")?.toInt() ?: 0,
            max = o.num("max_messages")?.toInt() ?: 0,
            maxMinutes = o.num("max_minutes")?.toInt() ?: 0,
            never = o.texts("never_send"),
            paused = if (state == "paused") o.text("paused") ?: "" else "",
            ended = o.text("ended") ?: "",
            summary = sum,
            members = o.objects("members").mapNotNull { parseSession(it) },
        )
    }

    fun parseSession(o: JsonObject?): Session? {
        if (o == null) return null
        val id = o.text("id") ?: return null
        val state = o.text("state") ?: return null
        val turns = (o["transcript"] as? JsonArray)?.mapNotNull { it as? JsonObject }?.mapNotNull { t ->
            val who = when (t.text("who")) {
                "chatbot" -> "chatbot"
                "jarvis" -> "jarvis"
                else -> return@mapNotNull null
            }
            // Anything the chatbot said is outside text, whatever the flag says.
            Turn(who, t.num("n")?.toInt() ?: 0, t.raw("text") ?: "",
                who == "chatbot" || t.flag("outside_text") == true,
                cutOff = who == "chatbot" && t.flag("cut_off") == true)
        } ?: emptyList()
        val sum = (o["summary"] as? JsonObject)?.let { s ->
            Summary(
                answer = s.text("answer") ?: "",
                claims = (s["claims"] as? JsonArray)?.mapNotNull { it as? JsonObject }?.mapNotNull { c ->
                    c.text("claim")?.let { Claim(it, c.flag("source_given") == true) }
                } ?: emptyList(),
                open = (s["open"] as? JsonArray)?.mapNotNull {
                    (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.contentOrNull?.trim()
                        ?.takeIf { x -> x.isNotEmpty() }
                } ?: emptyList(),
            )
        }
        return Session(
            id = id,
            chatbot = o.text("chatbot") ?: "",
            name = o.text("name") ?: "the chatbot",
            goal = o.raw("goal") ?: "",
            state = state,
            tierName = o.text("tier_name") ?: "",
            used = o.num("messages_used")?.toInt() ?: 0,
            max = o.num("max_messages")?.toInt() ?: 0,
            minutesUsed = o.num("minutes_used") ?: 0.0,
            maxMinutes = o.num("max_minutes")?.toInt() ?: 0,
            never = (o["never_send"] as? JsonArray)?.mapNotNull {
                (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.contentOrNull?.trim()
                    ?.takeIf { x -> x.isNotEmpty() }
            } ?: emptyList(),
            paused = if (state == "paused") o.text("paused") ?: "" else "",
            ended = o.text("ended") ?: "",
            question = o.text("question") ?: "",
            summary = sum,
            transcript = turns,
            usage = parseUsage(o["usage"] as? JsonObject),
        )
    }

    /** `usage` on a session, or null when it has none (a website conversation). */
    fun parseUsage(o: JsonObject?): Usage? {
        if (o == null) return null
        val requests = o.num("requests")?.toInt() ?: 0
        val total = o.num("total_tokens")?.toLong() ?: 0L
        val tokens = if (total > 0) total
        else (o.num("prompt_tokens")?.toLong() ?: 0L) + (o.num("completion_tokens")?.toLong() ?: 0L)
        if (requests == 0 && tokens == 0L) return null
        return Usage(requests, tokens, o.text("model") ?: "", o.text("cost") ?: "")
    }

    /** `money` on a chatbot, or null when there is none (no limit set, or not an API). */
    fun parseMoney(o: JsonObject?): Money? {
        if (o == null) return null
        val limit = o.text("limit") ?: return null
        val left = o.text("left") ?: return null
        return Money(o.text("company") ?: "", limit, left, o.text("spent") ?: "",
            o.text("until") ?: "", o.flag("reached") == true)
    }

    /** "About $4.55 of $5.00 left this month for OpenAI (...)", or "". */
    fun moneyLine(c: Choice?): String {
        val m = c?.money ?: return ""
        return MONEY_LEFT.replace("{left}", m.left).replace("{limit}", m.limit)
            .replace("{company}", m.company.ifEmpty { c.name })
    }

    /** 4215 as "4,215" - the same on every phone (no locale). */
    fun grouped(n: Long): String {
        val digits = kotlin.math.abs(n).toString()
        val out = StringBuilder()
        digits.forEachIndexed { i, ch ->
            if (i > 0 && (digits.length - i) % 3 == 0) out.append(',')
            out.append(ch)
        }
        return (if (n < 0) "-" else "") + out.toString()
    }

    /** "Used so far: 3 requests, 4,215 word-pieces (tokens), model gpt-5-mini, about $0.01", or "". */
    fun usageLine(u: Usage?): String {
        if (u == null) return ""
        var line = USAGE_LINE
        if (u.model.isEmpty()) line = line.replace(", model {model}", "")
        if (u.cost.isEmpty()) line = line.replace(", about {cost}", "")
        return line.replace("{requests}", "${u.requests} request${if (u.requests == 1) "" else "s"}")
            .replace("{tokens}", grouped(u.tokens)).replace("{model}", u.model)
            .replace("{cost}", u.cost)
    }

    /**
     * The chooser's groups, in [KINDS] order, each with its heading; empty
     * ones left out. A kind this app does not know goes last, with no heading.
     */
    fun groups(v: View): List<Group> {
        val titles = mapOf("website" to KIND_WEBSITE, "api" to KIND_API, "local" to KIND_LOCAL)
        val out = KINDS.map { k -> Group(k, titles.getValue(k), v.chatbots.filter { it.kind == k }) } +
            Group("other", "", v.chatbots.filter { it.kind !in KINDS })
        return out.filter { it.chatbots.isNotEmpty() }
    }

    /** The chatbots in the order the chooser shows them. */
    fun ordered(v: View): List<Choice> = groups(v).flatMap { it.chatbots }

    /** A read that failed because this PC has no chatbot routes. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && error.code == 501)

    /** "Version: the limited version (one graphics card) - shorter conversations; ..." */
    fun versionLine(v: View): String =
        if (v.tier.name.isEmpty()) "" else
            "$VERSION: ${v.tier.name}" + if (v.tier.words.isNotEmpty()) " - ${v.tier.words}" else ""

    /** The never-send words typed, as a list: split on commas, tidied, no repeats. */
    fun neverWords(text: String): List<String> {
        val out = mutableListOf<String>()
        for (raw in text.split(",")) {
            val w = raw.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")
            if (w.isNotEmpty() && out.none { it.equals(w, ignoreCase = true) }) out.add(w)
        }
        return out
    }

    /** A limit typed, or null when it is not 1 to [most]. */
    fun limitOf(text: String, most: Int): Int? {
        val s = text.trim()
        if (!Regex("^\\d{1,3}$").matches(s)) return null
        return s.toInt().takeIf { it in 1..most }
    }

    /** What is wrong with the form, in a sentence, or null when it can be sent. */
    fun formProblem(v: View, chatbot: String, goal: String, messages: String, minutes: String): String? {
        val bot = v.chatbots.firstOrNull { it.id == chatbot } ?: return "Choose a chatbot."
        if (!bot.built) {
            if (bot.made && bot.note.isNotEmpty()) {
                return if (bot.note.last() in ".!?") bot.note else bot.note + "."
            }
            return "${bot.name} is not built yet."
        }
        if (goal.isBlank()) return "Say what Jarvis should find out."
        if (goal.trim().length > MAX_GOAL_CHARS) return "The goal is longer than 1000 characters."
        if (limitOf(messages, v.tier.turnsMax) == null) {
            return "Most messages: 1 to ${v.tier.turnsMax} in this version."
        }
        if (limitOf(minutes, v.tier.minutesMax) == null) {
            return "Most minutes: 1 to ${v.tier.minutesMax} in this version."
        }
        return null
    }

    /** What is wrong with the "Ask several and compare" form, or null when it can be sent. */
    fun compareFormProblem(v: View, chatbots: List<String>, goal: String, messages: String,
                           minutes: String): String? {
        if (!v.canCompare) return COMPARE_NOT_ENOUGH
        val picked = chatbots.distinct()
        val usable = picked.filter { id -> v.chatbots.any { it.id == id && it.built } }
        if (usable.size < picked.size) return "Choose only chatbots that can be reached now."
        if (usable.size < v.tier.compareMin) {
            return COMPARE_TOO_FEW.replace("{min}", v.tier.compareMin.toString())
        }
        if (usable.size > v.tier.compareMax) {
            return COMPARE_TOO_MANY.replace("{max}", v.tier.compareMax.toString())
        }
        return formProblem(v, usable.first(), goal, messages, minutes)
    }

    /** "Chatbots to ask (pick 2 to 3)". */
    fun pickLine(v: View): String =
        COMPARE_PICK.replace("{min}", v.tier.compareMin.toString())
            .replace("{max}", v.tier.compareMax.toString())

    /** 10.0 as "10", 0.5 as "0.5" - as the desktop prints them. */
    fun number(d: Double): String =
        if (d == Math.floor(d) && !d.isInfinite()) d.toLong().toString() else d.toString()

    /** "Message 2 of 4 · 1.5 of 10 minutes". */
    fun progressLine(s: Session): String =
        "Message ${s.used} of ${s.max} · ${number(s.minutesUsed)} of ${s.maxMinutes} minutes"

    /** The buttons for a conversation, in order. Stop is always there while it is live. */
    fun actionsOf(s: Session?): List<String> = when {
        s == null || !s.live -> emptyList()
        s.state == "paused" -> listOf("resume", "stop")
        s.state == "running" -> listOf("pause", "stop")
        else -> listOf("stop")
    }

    fun labelOf(action: String): String = when (action) {
        "pause" -> PAUSE
        "resume" -> RESUME
        "stop" -> STOP
        else -> action
    }

    /** One conversation's status line: the PC's own words when it has them. */
    fun statusLine(s: Session): String = when {
        s.state == "paused" && s.paused.isNotEmpty() -> s.paused
        !s.live && s.ended.isNotEmpty() -> s.ended
        else -> STATE_WORDS[s.state] ?: s.state
    }

    /** The ongoing notification's line ("Talking to Gemini, 3 of 5"), or "" when it has ended. */
    fun talkingLine(s: Session?): String {
        if (s == null || !s.live) return ""
        val w = when (s.state) {
            "asking" -> NOTIFY_WAITING
            "paused" -> NOTIFY_PAUSED
            else -> NOTIFY_RUNNING
        }
        return w.replace("{name}", s.name).replace("{used}", s.used.toString())
            .replace("{max}", s.max.toString())
    }

    /** The buttons for a comparison, in order: the same as a single conversation's. */
    fun compareActionsOf(c: Compare?): List<String> = when {
        c == null || !c.live -> emptyList()
        c.state == "paused" -> listOf("resume", "stop")
        c.state == "running" -> listOf("pause", "stop")
        else -> listOf("stop")
    }

    /** A comparison's heading and notification line, or "" when it has ended. */
    fun compareTalkingLine(c: Compare?): String {
        if (c == null || !c.live) return ""
        val w = when (c.state) {
            "asking" -> NOTIFY_COMPARE_WAITING
            "paused" -> NOTIFY_COMPARE_PAUSED
            else -> NOTIFY_COMPARE_RUNNING
        }
        return w.replace("{count}", c.count.toString()).replace("{name}", c.currentName)
            .replace("{at}", (c.current + 1).toString())
    }

    /** A comparison's status line: the PC's own words when it has them. */
    fun compareStatusLine(c: Compare): String = when {
        c.state == "paused" && c.paused.isNotEmpty() -> c.paused
        !c.live && c.ended.isNotEmpty() -> c.ended
        else -> STATE_WORDS[c.state] ?: c.state
    }

    /** "4 messages sent in all · at most 3 messages and 10 minutes with each chatbot". */
    fun compareProgress(c: Compare): String =
        "${c.used} message${if (c.used == 1) "" else "s"} sent in all · at most ${c.max} messages " +
            "and ${c.maxMinutes} minutes with each chatbot"

    /** One chatbot's line inside a comparison. */
    fun memberLine(m: Session, c: Compare): String {
        val waiting = (m.state == "approved" || m.state == "planned") && c.live
        return "${m.name}: ${if (waiting) MEMBER_WAITING else statusLine(m)}"
    }

    /** Whether an activity line may be a conversation's ("Talking to Gemini: message 3 of 5."). */
    fun isChatbotActivity(detail: String?): Boolean {
        val d = detail ?: return false
        // The core's own lines (jarvis_chatbot.run), a comparison's
        // ("Comparing (2 of 3): Talking to ..."), and jarvis_task_control's
        // when a Resume card was approved ("Continuing chatbot_session...",
        // "Continuing chatbot_compare...").
        return d.startsWith("Talking to ") || d.startsWith("Waiting while you chat before asking ") ||
            d.startsWith("Comparing (") || d.startsWith("You paused the comparison") ||
            d.startsWith("Continuing chatbot_session") || d.startsWith("Continuing chatbot_compare")
    }

    private val ID = Regex("^chat_[0-9a-f]{12}$")
    private val COMPARE_ID = Regex("^cmp_[0-9a-f]{12}$")

    fun validId(id: String): Boolean = ID.matches(id)

    fun validCompareId(id: String): Boolean = COMPARE_ID.matches(id)

    private fun quote(s: String): String =
        JarvisJson.encodeToString(kotlinx.serialization.serializer<String>(), s)

    private fun wordsArray(words: List<String>): String =
        words.joinToString(",", prefix = "[", postfix = "]") { quote(it) }

    /** `POST /api/chatbot/start`'s body, or null when something in it cannot be sent. */
    fun startBody(chatbot: String, goal: String, maxMessages: Int?, maxMinutes: Int?,
                  never: List<String>): String? {
        if (!Regex("^[A-Za-z0-9_]{1,40}$").matches(chatbot)) return null
        val g = goal.trim()
        if (g.isEmpty() || g.length > MAX_GOAL_CHARS) return null
        if (never.size > MAX_NEVER || never.any { it.length > MAX_NEVER_CHARS }) return null
        val parts = mutableListOf("\"chatbot\":${quote(chatbot)}", "\"goal\":${quote(g)}",
            "\"never_send\":${wordsArray(never)}")
        if (maxMessages != null) parts.add("\"max_messages\":$maxMessages")
        if (maxMinutes != null) parts.add("\"max_minutes\":$maxMinutes")
        return parts.joinToString(",", prefix = "{", postfix = "}")
    }

    /** The most chatbots one comparison may name (the two-card version's; the PC checks). */
    const val MOST_COMPARED = 4

    /** `POST /api/chatbot/compare/start`'s body, or null when something in it cannot be sent. */
    fun compareBody(chatbots: List<String>, goal: String, maxMessages: Int?, maxMinutes: Int?,
                    never: List<String>): String? {
        val ids = chatbots.distinct()
        if (ids.size < 2 || ids.size > MOST_COMPARED) return null
        if (ids.any { !Regex("^[A-Za-z0-9_]{1,40}$").matches(it) }) return null
        val single = startBody(ids.first(), goal, maxMessages, maxMinutes, never) ?: return null
        val list = ids.joinToString(",", prefix = "[", postfix = "]") { quote(it) }
        // The single body starts {"chatbot":"<id>", ... - swap that for the list.
        return single.replaceFirst("\"chatbot\":${quote(ids.first())}", "\"chatbots\":$list")
    }

    /** `POST /api/chatbot/compare/stop`'s body, or null for an id that is not the PC's shape. */
    fun compareStopBody(id: String): String? =
        if (validCompareId(id)) "{\"id\":${quote(id)}}" else null

    /** `POST /api/chatbot/stop`'s body, or null for an id that is not the PC's shape. */
    fun stopBody(id: String): String? = if (validId(id)) "{\"id\":${quote(id)}}" else null

    /** `POST /api/chatbot/limits`'s body: only what was given. */
    fun limitsBody(id: String, maxMessages: Int?, maxMinutes: Int?, never: List<String>?): String? {
        if (!validId(id)) return null
        if (never != null && (never.size > MAX_NEVER || never.any { it.length > MAX_NEVER_CHARS })) {
            return null
        }
        val parts = mutableListOf("\"id\":${quote(id)}")
        if (maxMessages != null) parts.add("\"max_messages\":$maxMessages")
        if (maxMinutes != null) parts.add("\"max_minutes\":$maxMinutes")
        if (never != null) parts.add("\"never_send\":${wordsArray(never)}")
        return parts.joinToString(",", prefix = "{", postfix = "}")
    }

    /** What the PC answered a change, kept whole. */
    data class Reply(val code: Int, val body: JsonObject?)

    /** Whether it went through, and the PC's sentence to show. */
    fun said(reply: Reply): Pair<Boolean, String> {
        val b = reply.body
        val error = b?.text("error")
        return when {
            reply.code in 200..299 && b?.flag("ok") != false ->
                true to (b?.text("message") ?: "Done.")
            // The route's own "no such conversation" is a 404 with {"ok": false}.
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

    /** A string exactly as sent (a goal or a message keeps its own spacing). */
    private fun JsonObject.raw(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
