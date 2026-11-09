package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put

/**
 * "Forget a time frame" - the owner's decision of 2026-09-28, and
 * docs/JARVIS-API.md section 64 (`/api/memory/forget_range`).
 *
 * The owner picks some days; the PC lists what Jarvis learned and the chats
 * from then, each ticked, and the pinned chats it is KEEPING beside them
 * (never tickable, owner 2026-11-04); the owner unticks any to keep and taps
 * "Forget these"; the PC raises ONE approval card listing every item, decided
 * by a tap - never by voice. The card is the FIRST yes and changes nothing:
 * approving it makes the PC HOLD the checked items for 120 seconds, and the
 * SECOND yes - a literal `yes: true` carrying the held id - forgets the facts
 * (as Forget does) and deletes the chats, with 10 minutes to Undo (one tap,
 * no card).
 *
 * What asks first is the PC's to decide, never this app's. The phone keeps
 * nothing of the list: it reads it from the PC each time.
 *
 * The desktop says the same words (jarvis-desktop/src/forget-range.js); both
 * are checked against `contract/forget-range-cases.json`, made by
 * tools/gen_forget_range_cases.py from the real backend.
 *
 * Pure Kotlin, no Android types, so `ForgetRangeTest` runs it on a plain JVM.
 */
object ForgetRange {
    const val PATH = "/api/memory/forget_range"
    const val PREVIEW_PATH = "/api/memory/forget_range/preview"
    const val UNDO_PATH = "/api/memory/forget_range/undo"

    /** The SECOND yes (owner, 2026-11-04): the held id and a literal `yes: true`. */
    const val CONFIRM_PATH = "/api/memory/forget_range/confirm"

    /** The Brain item "forget what you learned last week" opens (`open_brain`). */
    const val PLACE = "forget-range"

    /** The screens' own words, both apps, word for word (the contract's `words`). */
    val WORDS: Map<String, String> = mapOf(
        "asked" to "You asked Jarvis to forget {said}. Check the list below.",
        "bad_date" to "Type the dates like 2026-09-01.",
        "between_us" to "Between us",
        "chats_head" to "Chats from then",
        "custom" to "Choose the dates",
        "date_hint" to "A date like 2026-09-01",
        "erase_note" to "Facts are forgotten, as Forget does: they stop being used and stay in the history. To wipe a fact's words for good, use Erase the words on that fact.",
        "facts_head" to "What Jarvis learned then",
        "forget" to "Forget these",
        "from" to "From",
        "kind_chats" to "Chats",
        "kind_chatbot" to "Chat with an AI",
        "kind_compare" to "Comparison",
        "kind_facts" to "What Jarvis learned",
        "kind_live" to "Live",
        "kind_support" to "Support chat",
        "kinds" to "What to look for",
        "locked" to "Unlock Jarvis to see this list.",
        "missing" to "Your PC's Jarvis cannot forget a time frame yet - run apply-patches.ps1 on the PC.",
        "none_ticked" to "Tick at least one thing to forget.",
        "pinned" to "Always kept in mind",
        "show" to "Show the list",
        "spills" to "Also has messages from outside these days. Tick it only if the whole chat should go.",
        "stale" to "The connection to Jarvis is catching up, so nothing can be sent until it does.",
        "support" to "A customer-support chat record - kept unless you tick it.",
        "title" to "Forget a time frame",
        "to" to "To",
        "under" to "Choose some days. Jarvis lists what it learned and your chats from then - untick anything you want to keep, then tap Forget these. Nothing is removed until you approve the card, and for 10 minutes one tap on Undo puts it all back.",
        "undo" to "Undo",
        "undo_left" to "{minutes} min left to undo",
        "waiting" to "Waiting for your yes on the approval card. Nothing is removed until you approve it - saying yes out loud does not.",
    )

    /** One of [WORDS]. */
    fun w(key: String): String = WORDS.getValue(key)

    /**
     * The words this screen needs on top of the contract's [WORDS], and why
     * they are not in that map: `words` is generated from the backend's own
     * `WORDS`, key for key, and the desktop checks it key for key - adding one
     * there would mean changing the contract and the generator from the apps
     * lane.
     *
     * Five are the PC's own sentences, word for word, from
     * `backend/jarvis_forget_range.py`: the pinned chats it is keeping
     * (`PINNED_ONE`, `PINNED_MANY`, `PINNED_WHY`) and the second yes
     * (`CONFIRM_TEXT`, `CONFIRM_YES`). The sixth is the one line this screen
     * needs and the PC has no use for: how long the second yes has left, in
     * the same shape as `undo_left`. The desktop says all six word for word
     * (src/forget-range.js EXTRA), and its tests pin them to the backend.
     *
     * `{n}` is the count of pinned chats kept; `{minutes}` a whole number.
     */
    val EXTRA: Map<String, String> = mapOf(
        "confirm_text" to "Say yes again to finish. Undo stays available for 10 minutes.",
        "confirm_yes" to "Yes, forget them",
        "hold_left" to "{minutes} min left to say yes",
        "pinned_one" to "1 pinned chat is kept",
        "pinned_many" to "{n} pinned chats are kept",
        "pinned_why" to "Pinning a chat keeps it out of this list and away from this Forget.",
    )

    /** One of [EXTRA]. */
    fun x(key: String): String = EXTRA.getValue(key)

    /** `{said}` and friends filled in. */
    fun fill(template: String, vararg values: Pair<String, Any>): String {
        var out = template
        for ((k, v) in values) out = out.replace("{$k}", v.toString())
        return out
    }

    val MISSING: String get() = w("missing")

    data class Preset(val id: String, val label: String)

    /** The PC's quick choices, in its order, for before it has said them. */
    val PRESETS: List<Preset> = listOf(
        Preset("today", "Today"),
        Preset("yesterday", "Yesterday"),
        Preset("this_week", "This week"),
        Preset("last_week", "Last week"),
        Preset("last_7_days", "The last 7 days"),
        Preset("this_month", "This month"),
        Preset("last_month", "Last month"),
    )

    // ------------------------------------------------------------ shapes ----

    data class Undo(val secondsLeft: Int, val minutesLeft: Int, val facts: Int, val chats: Int, val said: String)

    data class Asked(val id: String, val from: String, val to: String, val said: String, val kinds: List<String>)

    /** [at]: when the PC ended it, by the PC's clock (0 when it did not say). */
    data class Last(val outcome: String, val message: String, val at: Double = 0.0)

    /**
     * The SECOND yes the PC is holding (owner, 2026-11-04): the id it gave,
     * what is left of the 120 seconds, and its own sentence. Nothing is
     * deleted until this is answered - and only with [confirmBody]'s literal
     * `true`.
     */
    data class Confirm(val id: String, val expiresIn: Int, val text: String,
        /** True when the PC calls this selection a large wipe (owner's 2026-11-08 ruling). */
        val largeWipe: Boolean = false)

    data class Status(
        val available: Boolean,
        val why: String,
        val waiting: Boolean,
        val undo: Undo?,
        val last: Last?,
        val asked: Asked?,
        /** There is no item cap (owner's 2026-11-08 ruling): this is only the size
         *  at which the PC calls a wipe LARGE, never a limit. */
        val largeWipe: Boolean,
        val largeWipeItems: Int,
        val largeWords: String,
        val presets: List<Preset>,
        /** Null unless a card has been approved and the PC is holding items. */
        val confirm: Confirm? = null,
        /** How many pinned chats the range keeps (0 when nothing is held). */
        val pinnedKeptCount: Int = 0,
    )

    data class Fact(val id: Long, val text: String, val label: String, val pinned: Boolean, val betweenUs: Boolean)

    /**
     * One chat in the list. [kind]: what kind of chat (the chat audit,
     * 2026-09-28); [startsTicked] false for a customer-support record, which
     * goes only when the owner ticks it (the owner: "Forget a time frame"
     * asks before removing a support chat).
     */
    data class Chat(
        val id: String,
        val title: String,
        val label: String,
        val spills: Boolean,
        val kind: String = "chat",
        val startsTicked: Boolean = true,
    )

    /**
     * A pinned chat the range is KEEPING (owner, 2026-11-04). Never on the
     * tickable list, never deleted: drawn as kept, with its title and how many
     * messages stay. [title] is a chat title, so it is hidden with the other
     * private words ([redact]).
     */
    data class PinnedChat(val id: String, val title: String, val messages: Int)

    /**
     * The PC's measured "how long would that take", from the counts it just
     * read. [text] is its own sentence, said before the owner is asked.
     */
    data class Estimate(
        val facts: Int = 0,
        val chats: Int = 0,
        val messages: Int = 0,
        val seconds: Int = 0,
        val text: String = "",
    )

    /** The tag beside a chat of a kind that is not an ordinary chat, or null. */
    fun chatKindTag(kind: String): String? =
        if (kind == "chat") null else WORDS["kind_$kind"]

    data class Preview(
        val available: Boolean,
        val why: String,
        val from: String,
        val to: String,
        val frameSaid: String,
        val kinds: List<String>,
        val facts: List<Fact>,
        val chats: List<Chat>,
        val factsCount: Int,
        val chatsCount: Int,
        /** No item cap: the list is exact at any size; [largeWipe] only names a big one. */
        val largeWipe: Boolean,
        val largeWipeItems: Int,
        val largeWords: String,
        val empty: Boolean,
        val said: String,
        val chatsWhy: String,
        val pinnedKept: List<PinnedChat> = emptyList(),
        val pinnedKeptCount: Int = 0,
        val estimate: Estimate = Estimate(),
        /** True when the PC sent a hidden list: no words at all, counts only. */
        val hidden: Boolean = false,
    )

    /**
     * The list with every fact's words and every chat's title - tickable AND
     * pinned-kept - taken out, for while the private lists are hidden. The
     * same rule the desktop's Rust `redact()` applies: `pinned_kept` carries
     * chat TITLES, so a hidden list that still named the pinned chats would
     * leak the one thing hiding it is for. The counts, the days and the
     * estimate (numbers) stay.
     */
    fun redact(p: Preview): Preview = p.copy(
        facts = p.facts.map { it.copy(text = "") },
        chats = p.chats.map { it.copy(title = "") },
        pinnedKept = p.pinnedKept.map { it.copy(title = "") },
        hidden = true,
    )

    // ------------------------------------------------------------ reading ---

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject.flag(key: String): Boolean =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull == true

    private fun JsonObject.whole(key: String): Int =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString && it !is JsonNull }?.intOrNull ?: 0

    private fun JsonObject.obj(key: String): JsonObject? = this[key] as? JsonObject

    private fun JsonObject.list(key: String): List<JsonObject> =
        (this[key] as? JsonArray)?.mapNotNull { it as? JsonObject }.orEmpty()

    private fun JsonObject.words(key: String): List<String> =
        (this[key] as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.contentOrNull }
            .orEmpty()

    private val WHEN = Regex("""\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?""")

    /** "2026-09-01" or "2026-09-28T09:30" - what the PC reads and writes. */
    fun isWhen(s: String?): Boolean = s != null && WHEN.matches(s)

    private val HOLD_ID = Regex("""[A-Za-z0-9_-]{1,128}""")

    /**
     * Whether [s] could be the id of the second yes the PC is holding - the
     * same shape `is_hold_id` checks in the desktop's Rust. The id is never
     * made here: the status carries it and this hands it straight back. Which
     * hold it is, and whether it is still the right one, is the PC's to
     * decide, and its 409 says so.
     */
    fun isHoldId(s: String?): Boolean = s != null && HOLD_ID.matches(s)

    private fun unavailable(why: String?) = Status(false, why ?: MISSING, false, null, null, null,
        false, 200, "", PRESETS)

    /** `GET /api/memory/forget_range`. */
    fun parseStatus(o: JsonObject?): Status {
        if (o == null) return unavailable(null)
        if ((o["available"] as? JsonPrimitive)?.booleanOrNull == false) return unavailable(o.text("why"))
        val u = o.obj("undo")
        val a = o.obj("asked")
        val l = o.obj("last")
        val presets = o.list("presets").mapNotNull { p ->
            p.text("id")?.let { Preset(it, p.text("label").orEmpty()) }
        }
        // The SECOND yes (owner, 2026-11-04): only a real hold, with an id
        // this screen can hand back, is one. A mistyped block is not.
        val c = o.obj("confirm")
        val cid = c?.text("id")
        return Status(
            available = true,
            why = "",
            waiting = o.flag("waiting"),
            undo = u?.let {
                Undo(it.whole("seconds_left"), it.whole("minutes_left"), it.whole("facts"), it.whole("chats"),
                    it.text("said").orEmpty())
            },
            last = l?.let {
                Last(
                    it.text("outcome").orEmpty(),
                    it.text("message").orEmpty(),
                    (it["at"] as? JsonPrimitive)?.takeIf { p -> !p.isString }?.doubleOrNull ?: 0.0,
                )
            },
            asked = a?.takeIf { isWhen(it.text("from")) && isWhen(it.text("to")) }?.let {
                Asked(it.text("id").orEmpty(), it.text("from")!!, it.text("to")!!, it.text("said").orEmpty(),
                    it.words("kinds").filter { k -> k == "facts" || k == "chats" })
            },
            largeWipe = o.flag("large_wipe"),
            largeWipeItems = o.whole("large_wipe_items").takeIf { it > 0 } ?: 200,
            largeWords = o.text("large_wipe_words").orEmpty(),
            presets = presets.ifEmpty { PRESETS },
            confirm = if (c != null && isHoldId(cid)) {
                Confirm(cid!!, c.whole("expires_in"), c.text("text").orEmpty().ifEmpty { x("confirm_text") },
                     c.flag("large_wipe"))
            } else {
                null
            },
            pinnedKeptCount = o.whole("pinned_kept_count"),
        )
    }

    /** `GET /api/memory/forget_range/preview`. */
    fun parsePreview(o: JsonObject?): Preview {
        if (o == null || (o["available"] as? JsonPrimitive)?.booleanOrNull == false) {
            return Preview(false, o?.text("why") ?: MISSING, "", "", "", emptyList(), emptyList(), emptyList(),
                0, 0, false, 200, "", false, "", "")
        }
        val f = o.obj("frame")
        val counts = o.obj("counts")
        val facts = o.list("facts").mapNotNull { x ->
            val id = (x["id"] as? JsonPrimitive)?.takeIf { !it.isString }?.longOrNull ?: return@mapNotNull null
            Fact(id, x.text("text").orEmpty(), x.text("label").orEmpty(), x.flag("pinned"), x.flag("between_us"))
        }
        val chats = o.list("chats").mapNotNull { x ->
            val id = x.text("id") ?: return@mapNotNull null
            val kind = x.text("kind")?.takeIf { it in ChatLog.KINDS } ?: "chat"
            // A support record, or a chat with messages from outside the
            // days, starts unticked even from a PC that sent no `ticked`; an
            // ordinary chat starts ticked unless the PC says not.
            val spills = x.flag("spills")
            val ticked = (x["ticked"] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull != false &&
                kind != "support" && !spills
            Chat(id, x.text("title").orEmpty(), x.text("label").orEmpty(), spills, kind, ticked)
        }
        // The pinned chats the PC is KEEPING (owner, 2026-11-04): they are not
        // in `chats` at all, so they can never be ticked, counted or sent.
        val pinned = o.list("pinned_kept").mapNotNull { x ->
            val id = x.text("id") ?: return@mapNotNull null
            PinnedChat(id, x.text("title").orEmpty(), x.whole("messages"))
        }
        val est = o.obj("estimate")
        return Preview(
            available = true,
            why = "",
            from = f?.text("from").orEmpty(),
            to = f?.text("to").orEmpty(),
            frameSaid = f?.text("said").orEmpty(),
            kinds = o.words("kinds").ifEmpty { listOf("facts", "chats") },
            facts = facts,
            chats = chats,
            factsCount = counts?.whole("facts") ?: 0,
            chatsCount = counts?.whole("chats") ?: 0,
            largeWipe = o.flag("large_wipe"),
            largeWipeItems = o.whole("large_wipe_items").takeIf { it > 0 } ?: 200,
            largeWords = o.text("large_wipe_words").orEmpty(),
            empty = o.flag("empty"),
            said = o.text("said").orEmpty(),
            chatsWhy = o.text("chats_why").orEmpty(),
            pinnedKept = pinned,
            pinnedKeptCount = o.whole("pinned_kept_count").takeIf { it > 0 } ?: pinned.size,
            estimate = Estimate(
                est?.whole("facts") ?: 0,
                est?.whole("chats") ?: 0,
                est?.whole("messages") ?: 0,
                est?.whole("seconds") ?: 0,
                est?.text("text").orEmpty(),
            ),
            hidden = o.flag("hidden"),
        )
    }

    // ----------------------------------------------------------- asking ----

    private val PRESET_IDS = PRESETS.map { it.id }.toSet()

    /**
     * The preview's path for a quick choice (`preset`) or two typed dates;
     * null when a date is not written like 2026-09-01, or no kind is chosen.
     */
    fun previewPath(preset: String?, from: String?, to: String?, kinds: Set<String>): String? {
        val k = listOf("facts", "chats").filter { it in kinds }
        if (k.isEmpty()) return null
        val kq = k.joinToString(",")
        if (preset != null) {
            return if (preset in PRESET_IDS) "$PREVIEW_PATH?preset=$preset&kinds=$kq" else null
        }
        if (!isWhen(from) || !isWhen(to)) return null
        return "$PREVIEW_PATH?from=$from&to=$to&kinds=$kq"
    }

    /** Every item ticked: "fact:<id>" and "chat:<id>" - how a fresh list starts - except a
     *  customer-support chat's record, which goes only when the owner ticks it, and except any
     *  pinned chat the PC is keeping. */
    fun allTicked(p: Preview): Set<String> {
        val kept = keptKeys(p)
        return p.facts.map { "fact:${it.id}" }.toSet() +
            p.chats.filter { it.startsTicked && "chat:${it.id}" !in kept }.map { "chat:${it.id}" }.toSet()
    }

    /** The kept chats' ids as tick keys - the ones nothing here may ever send. */
    private fun keptKeys(p: Preview): Set<String> = p.pinnedKept.map { "chat:${it.id}" }.toSet()

    fun tickedCount(p: Preview, ticked: Set<String>): Int =
        p.facts.count { "fact:${it.id}" in ticked } + p.chats.count { "chat:${it.id}" in ticked }

    /** "Forget these": the ids still ticked, in the list's order, and the PC's own two dates.
     *  A pinned chat is dropped even if something ticked one: the PC would refuse the request
     *  (409), and this app never asks it to delete what the owner pinned. */
    fun forgetBody(p: Preview, ticked: Set<String>): String {
        val kept = keptKeys(p)
        return buildJsonObject {
            put("from", p.from)
            put("to", p.to)
            put("facts", JsonArray(p.facts.filter { "fact:${it.id}" in ticked }.map { JsonPrimitive(it.id) }))
            put("chats", JsonArray(p.chats
                .filter { "chat:${it.id}" in ticked && "chat:${it.id}" !in kept }
                .map { JsonPrimitive(it.id) }))
        }.toString()
    }

    /** The SECOND yes: the id the PC is holding and the literal `true` - never a string, never
     *  a number (the PC answers 400 to anything else, and the hold stays). */
    fun confirmBody(id: String): String = buildJsonObject {
        put("id", id)
        put("yes", true)
    }.toString()

    /** "1 pinned chat is kept" / "3 pinned chats are kept" - the PC's own words for the chats
     *  this list leaves out. */
    fun pinnedKeptLine(n: Int): String = if (n == 1) x("pinned_one") else fill(x("pinned_many"), "n" to n)

    /** "2 min left to say yes", from the status's own `expires_in` seconds. */
    fun holdLeftLine(c: Confirm): String =
        fill(x("hold_left"), "minutes" to maxOf(1, (c.expiresIn + 59) / 60))

    /** One pinned chat's meta line: "12 messages", as the estimate says it. */
    fun messagesLine(n: Int): String = "$n message" + (if (n == 1) "" else "s")

    /** "Forget these (3)". */
    fun forgetLabel(n: Int): String = "${w("forget")} ($n)"

    /** The Undo line: what was done, and how long is left. */
    fun undoLine(u: Undo): String =
        "${u.said} ${fill(w("undo_left"), "minutes" to (if (u.minutesLeft > 0) u.minutesLeft else 1))}."

    /** "Forget these" waits for a live link (rule 4); Undo never does - it only puts back.
     *  The second yes deletes, so it waits for a live link too, exactly like the card it
     *  follows. */
    fun heldOnStale(action: String): Boolean = action == "forget" || action == "confirm"

    /**
     * "forget what you learned last week", said or typed: [PLACE] when the
     * answer's `X-Jarvis-Route` says `open_brain: "forget-range"`, else
     * null. Pure navigation - nothing is removed by opening the list.
     */
    fun openFromRoute(header: String?): String? {
        if (header.isNullOrBlank()) return null
        val o = runCatching { JarvisJson.parseToJsonElement(header.trim()) as? JsonObject }.getOrNull()
            ?: return null
        return o.text("open_brain")?.takeIf { it == PLACE }
    }

    // --------------------------------------------------------- answers ----

    data class Reply(val code: Int, val body: JsonObject?)

    /** How a change went: [waiting] a card is up; [done] something changed (Undo). */
    data class Outcome(val done: Boolean, val waiting: Boolean, val said: String, val listChanged: Boolean = false)

    /** A PC without the routes: a 404 that jarvis_forget_range did not send. */
    fun isMissing(reply: Reply): Boolean =
        (reply.code == 404 && (reply.body?.get("ok") as? JsonPrimitive)?.booleanOrNull != false) || reply.code == 501

    private fun sentence(s: String): String =
        s.replaceFirstChar { it.uppercase() }.let { if (it.isEmpty() || it.last() in ".!?") it else "$it." }

    /**
     * The chat ids a "forget" body names (`{"facts": [...], "chats": [...]}`,
     * [forgetBody]) - kept by the runtime until the card is decided, so Home
     * can leave a chat that went (the chat audit, 2026-09-28). Ids only.
     */
    fun chatsIn(json: String): List<String> = runCatching {
        ((JarvisJson.parseToJsonElement(json) as? JsonObject)?.get("chats") as? JsonArray)
            ?.mapNotNull { (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.content }
            .orEmpty()
    }.getOrDefault(emptyList())

    /**
     * From a status read ([parseStatus]): null while a card is still waiting
     * (or the answer was not a status), else how the last one ended -
     * `last.outcome` ("done" when approved and carried out).
     */
    fun decided(reply: Reply, since: Double = 0.0): String? {
        if (reply.code !in 200..299) return null
        val s = parseStatus(reply.body)
        if (!s.available || s.waiting) return null
        val last = s.last ?: return null
        // An ending older than the card being waited for is an earlier
        // "forget" (the second chat audit, phone B7): not this one's answer.
        if (since > 0.0 && last.at <= since) return null
        return last.outcome.takeIf { it.isNotEmpty() }
    }

    /** The PC-clock time of the last ending in this status read, 0 when none. */
    fun lastEndedAt(reply: Reply): Double =
        if (reply.code in 200..299) parseStatus(reply.body).last?.at ?: 0.0 else 0.0

    /** Reads a "forget" or "undo" answer: the PC's own sentence either way. */
    fun said(reply: Reply, done: String): Outcome {
        val b = reply.body
        val error = b?.text("error")?.let { sentence(it) }
        return when {
            isMissing(reply) -> Outcome(false, false, MISSING)
            reply.code in 200..299 -> Outcome(
                done = true,
                waiting = reply.code == 202 || b?.flag("waiting") == true,
                said = b?.text("message") ?: done,
            )
            else -> Outcome(false, false, error ?: "Not done. Your PC said no (HTTP ${reply.code}).",
                listChanged = b?.flag("changed") == true)
        }
    }
}
