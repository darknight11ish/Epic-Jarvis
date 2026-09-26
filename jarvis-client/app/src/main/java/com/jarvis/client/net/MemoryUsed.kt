package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.longOrNull

/**
 * A temporary chat - the owner's decision of 2026-09-25 (docs/JARVIS-API.md
 * section 18.1).
 *
 * One tap on Home. While it is on, every question - typed or spoken - goes
 * with `"temporary": true`, and the PC recalls no facts (no pinned list
 * either), learns nothing (no "Remember:" either) and keeps nothing in the
 * chat history. Tools, approval cards and the rest are unchanged, so it needs
 * no card: it only makes things stricter. Turning it on or off starts a new
 * conversation ([ChatSession.setTemporary]), so nothing said in one kind of
 * chat is re-sent in the other.
 *
 * Offered only when `/api/version` says the PC has it
 * (`capabilities.temporary_chat`); otherwise the phone says [UNAVAILABLE] and
 * sends nothing as temporary. An answer whose `X-Jarvis-Route` does not say
 * `"temporary": true` gets [NOT_CONFIRMED] rather than a pretence.
 *
 * The desktop says the same words (jarvis-desktop/src/memory-used.js).
 * Pure Kotlin, no Android types, so `MemoryUsedTest` runs it on a plain JVM.
 */
object TemporaryChat {
    /** The capability `/api/version` reports (`jarvis_events._capability_probe`). */
    const val CAPABILITY = "temporary_chat"

    /** The mode's name, and the one line on the empty chat - both apps. */
    const val LABEL = "Temporary chat"
    const val LINE =
        "Temporary chat: Jarvis won't use or learn from your memory, and this chat isn't kept."

    /** The toggle, when off, and what ends it. */
    const val START = "Temporary chat"
    const val END = "End"

    /** Said when the owner turns it on or off (a new conversation each time). */
    const val STARTED = "Temporary chat started. Nothing in it is remembered or kept."
    const val ENDED = "Temporary chat ended. Your next question starts a normal chat."

    /** A PC whose backend has no temporary chat. Nothing is sent. */
    const val UNAVAILABLE =
        "Temporary chat isn't available on this PC's version of Jarvis, so nothing was sent. " +
            "Run apply-patches.ps1 on the PC to update it."

    /** An answer to a temporary question whose route header does not confirm it. */
    const val NOT_CONFIRMED =
        "Your PC did not confirm this was a temporary chat, so this answer may have used your " +
            "memory and the chat may be kept."

    /** A "Remember: ..." in a temporary chat (the route's `remember_off`). */
    const val REMEMBER_OFF = "Remember: is off in a temporary chat."

    /** The `/api/chat` body's flag: present, and true, only for a temporary chat. */
    const val FIELD = "temporary"

    /**
     * The lines to show under an answer, from its `X-Jarvis-Route` header:
     * [NOT_CONFIRMED] when the question went as temporary and the header
     * does not say `"temporary": true`, and [REMEMBER_OFF] when it says
     * `"remember_off": true`. Empty for an ordinary question.
     */
    fun notes(sentTemporary: Boolean, header: String?): List<String> {
        if (!sentTemporary) return emptyList()
        val route = MemoryUsed.route(header)
        return listOfNotNull(
            if (route?.flag("temporary") == true) null else NOT_CONFIRMED,
            if (route?.flag("remember_off") == true) REMEMBER_OFF else null,
        )
    }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}

/**
 * "Used in this answer", and the facts behind "Jarvis remembered N things" -
 * the owner's decisions of 2026-09-25 (docs/JARVIS-API.md sections 4, 6 and
 * 19.5).
 *
 * `X-Jarvis-Route` lists the facts an answer used by id only
 * (`injected_ids`, "mem:<id>"), and the `memory_saved` event lists what
 * automatic learning saved by id only. When the owner opens "Used 2
 * memories" under an answer, or "Jarvis remembered 2 things" in Mind, their
 * words are read from the PC by id - `GET /api/memory/used?ids=12,15` - and
 * each fact still in use gets a Forget, with the same confirm as Mind's
 * Forget. A pinned fact says so. Hidden, like Mind's other memory lists,
 * under "Hide memory lists and chat history".
 *
 * "Erase the words" is not offered here on the phone: on the phone it stays
 * where it is (Mind -> Saved automatically), and a fact used in an answer may
 * be one the phone does not otherwise list (docs/ARCHITECTURE.md section 8).
 * The desktop offers both.
 */
object MemoryUsed {
    const val PATH = "/api/memory/used"

    /** The PC's own limit on one read (`jarvis_memory.USED_MAX`). */
    const val MAX = 100

    /** The list's titles: under an answer, and in Mind. */
    const val USED_TITLE = "Used in this answer"
    const val REMEMBERED_TITLE = "Remembered just now"

    /** Mind's way on from those facts to the whole list, as before. */
    const val SHOW_ALL = "Show everything saved automatically"

    /** What each fact can say beside its words. */
    const val PINNED_MARK = "pinned"
    const val NOT_CURRENT_MARK = "no longer in use"

    /** A PC without the read route (a 404 or a 501). The desktop says the same. */
    const val MISSING =
        "Your PC's Jarvis cannot show which facts these were yet - run apply-patches.ps1 on the PC " +
            "to update it."

    /** While "Hide memory lists and chat history" hides them. */
    const val HIDDEN = "Hidden. Tap Show and confirm it is you."

    /** On a stale link: Forget waits. */
    const val HELD = "Not connected to the desktop, so Forget waits until the link is back."

    /** "Used 1 memory" / "Used 2 memories" - the quiet line under an answer. Null for none. */
    fun usedLine(count: Int): String? = when {
        count <= 0 -> null
        count == 1 -> "Used 1 memory"
        else -> "Used $count memories"
    }

    /** Ids the PC had no fact for at all. Null for none. */
    fun missingLine(count: Int): String? = when {
        count <= 0 -> null
        count == 1 -> "1 of them is no longer on this PC."
        else -> "$count of them are no longer on this PC."
    }

    /** `X-Jarvis-Route` as a JSON object, or null. */
    internal fun route(header: String?): JsonObject? {
        if (header.isNullOrBlank()) return null
        return runCatching { JarvisJson.parseToJsonElement(header.trim()) as? JsonObject }.getOrNull()
    }

    /**
     * The facts an answer used, from its `X-Jarvis-Route`: each "mem:<id>"
     * in `injected_ids` as a whole number above 0, in order, each once, at
     * most [MAX]. "fact:<n>" (the older word list, which has no id) and
     * anything else are left out.
     */
    fun idsFromRouteHeader(header: String?): List<Long> {
        val ids = route(header)?.get("injected_ids") as? JsonArray ?: return emptyList()
        val out = LinkedHashSet<Long>()
        for (el in ids) {
            val s = (el as? JsonPrimitive)?.takeIf { it.isString }?.content ?: continue
            val digits = s.removePrefix("mem:").takeIf { s.startsWith("mem:") } ?: continue
            if (digits.isEmpty() || digits.length > 12 || !digits.all { it in '0'..'9' }) continue
            val n = digits.toLongOrNull()?.takeIf { it > 0 } ?: continue
            out.add(n)
            if (out.size >= MAX) break
        }
        return out.toList()
    }

    /** The read for these ids, or null when there are none (or too many) to ask for. */
    fun path(ids: List<Long>): String? {
        val list = ids.filter { it > 0 }.distinct()
        if (list.isEmpty() || list.size > MAX) return null
        return PATH + "?ids=" + list.joinToString(",")
    }

    data class Fact(
        val id: Long,
        /** The words; "" for an erased fact, whose words are gone. */
        val text: String,
        val current: Boolean,
        val pinned: Boolean,
        val validTo: Double?,
        val erasedAt: Double?,
    ) {
        /** Forget only on a fact still in use: a forgotten one has nothing to forget. */
        val canForget: Boolean get() = current && erasedAt == null
    }

    data class View(val facts: List<Fact>, val missing: List<Long>)

    /** What one read came to. */
    sealed interface Read {
        data class Shown(val view: View) : Read
        /** A PC without the route. */
        data object Missing : Read
        data class Failed(val why: String) : Read
    }

    /**
     * `GET /api/memory/used`, read - or null when it is not that answer (no
     * `facts` array). A fact without a whole-number id is dropped, never
     * guessed. An erased fact never has words here: the PC sends none, and
     * even a stray "[erased]" is not shown.
     */
    fun parse(body: JsonObject): View? {
        val raw = body["facts"] as? JsonArray ?: return null
        val facts = raw.mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val id = o.number("id")?.longOrNull?.takeIf { it > 0 } ?: return@mapNotNull null
            val erasedAt = o.number("erased_at")?.doubleOrNull?.takeIf { it.isFinite() && it > 0 }
            val current = o.flag("current") == true && erasedAt == null
            Fact(
                id = id,
                text = if (erasedAt != null) "" else o.text("text").orEmpty(),
                current = current,
                pinned = current && o.flag("pinned") == true,
                validTo = o.number("valid_to")?.doubleOrNull?.takeIf { it.isFinite() },
                erasedAt = erasedAt,
            )
        }
        val missing = (body["missing"] as? JsonArray).orEmpty().mapNotNull {
            (it as? JsonPrimitive)?.takeIf { p -> p !is JsonNull && !p.isString }?.longOrNull
        }
        return View(facts, missing)
    }

    /** A read that failed because this PC has no such route: a 404 or a 501. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || (error is ApiError.Server && error.code == 501)

    private fun JsonObject.number(key: String): JsonPrimitive? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
