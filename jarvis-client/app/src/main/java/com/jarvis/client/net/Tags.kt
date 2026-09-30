package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put
import java.text.Normalizer

/**
 * Chat tags and sections in History - the phone's side of
 * docs/CHAT-TAGS-DESIGN.md (the owner's answers of 2026-09-30; the exact
 * shapes are the frozen "Slice contract", section 10).
 *
 * A tag is the owner's own label for a chat (Work, Learning...). One tag per
 * chat. The PC keeps the tag list (sealed, like a chat's title) and each
 * chat's opaque `tag_id`; THE PHONE STORES NO TAG. The only thing kept on
 * this phone is whether each section is folded open or shut, a harmless view
 * preference (data/HistoryViewPrefs.kt) - never a name, never a chat.
 *
 * The routes, all with the pairing token and `X-Jarvis-Client: hud` like
 * every other (JarvisApi adds both):
 * - `GET /api/history/tags` - the tags with a count each, and the untagged count.
 * - `POST /api/history/tags` - `{"op": "add" | "rename" | "style" | "move" | "delete", ...}`.
 * - `POST /api/history/tag` - `{"id": chat_id, "tag_id": int | null}`: file or unfile one chat.
 * - `GET /api/history?tag=<id>|none` - the list narrowed to one tag ([ChatLog.listPath]).
 *
 * No approval card anywhere (the owner's own organising; nothing leaves the
 * PC). Every write is held on a stale link (rule 4) by the caller.
 *
 * Pure Kotlin, no Android types, so `TagsTest` runs it on a plain JVM.
 */
object ChatTags {
    const val TAGS_PATH = "/api/history/tags"
    const val TAG_PATH = "/api/history/tag"

    /** At most this many tags (section 10). */
    const val MAX_TAGS = 12

    /** A tag's name is 1-24 characters once trimmed. */
    const val NAME_MAX = 24

    // ------------------------------------------------------- the look ---

    /** The eight colour slots, in slot order (section 10). */
    val COLOUR_NAMES = listOf("blue", "green", "amber", "violet", "teal", "rose", "slate", "orange")

    /** Text ink on a tinted header, light theme, as 0xRRGGBB (section 10's table). */
    val INK_LIGHT = listOf(0x1D4ED8, 0x146C36, 0x8A5300, 0x6D28D9, 0x0F766E, 0xBE123C, 0x475569, 0xB43A00)

    /** Text ink on a tinted header, dark theme, as 0xRRGGBB. */
    val INK_DARK = listOf(0x93B4FF, 0x86E0A6, 0xF5C26B, 0xC4A8FF, 0x7ADFD3, 0xFF9AB5, 0xB6C2D1, 0xFFB385)

    /** The header's tint is the ink at 12% (light) or 16% (dark) over the surface. */
    const val TINT_LIGHT = 0.12f
    const val TINT_DARK = 0.16f

    /** The shared icon names; each app draws them with its own icon set. */
    val ICONS = listOf("briefcase", "book", "home", "folder", "lightbulb", "star", "flag", "wrench", "leaf", "music")

    /** A slot out of range (an odd answer) is shown as slate rather than crashing. */
    fun slot(colour: Int): Int = if (colour in INK_LIGHT.indices) colour else 6

    fun ink(colour: Int, dark: Boolean): Int = (if (dark) INK_DARK else INK_LIGHT)[slot(colour)]

    fun colourName(colour: Int): String = COLOUR_NAMES[slot(colour)]

    /** The starter tags (ids 1-5), which the PC writes the first time the list is read. */
    val STARTER = listOf(
        Tag(1, "Work", 0, "briefcase", 0),
        Tag(2, "Learning", 1, "book", 1),
        Tag(3, "Personal", 2, "home", 2),
        Tag(4, "Projects", 3, "folder", 3),
        Tag(5, "Ideas", 4, "lightbulb", 4),
    )

    // ----------------------------------------------------------- words ---

    const val UNTAGGED = "Untagged"
    const val ALL = "All"
    const val EDITOR_TITLE = "Tags"
    const val ADD = "Add a tag"
    const val RENAME = "Rename"
    const val DELETE = "Delete this tag"
    const val MOVE_TO = "Move to"
    const val NO_TAG = "No tag"

    /** The visible header: `Work (12)`. */
    fun header(name: String, count: Int): String = "$name ($count)"

    /** TalkBack's form: `Work, 12 chats, collapsed`. */
    fun headerSpoken(name: String, count: Int, expanded: Boolean): String =
        "$name, $count chats, ${if (expanded) "expanded" else "collapsed"}"

    /** The confirm before a tag goes; its chats become untagged. */
    fun deleteConfirm(name: String, count: Int): String =
        "Delete the tag $name? Its $count chats become untagged."

    /** The status line after filing one chat, or taking its tag off. */
    fun filed(name: String): String = "Filed under $name."
    const val UNFILED = "Tag taken off."

    /** The banner's button on a row while an older chat is being found. */
    fun fileUnder(name: String): String = "File under $name"

    /** The placeholder of the move list on the desktop; here the button reads [MOVE_TO]. */
    const val MOVE_PLACEHOLDER = "Move to\u2026"

    /** The banner while History waits for a tap on an older chat. */
    fun banner(name: String): String = "Tap the chat to file it under $name."

    /** Editor extras, phone-only wording (not in the shared list). */
    const val CANCEL = "Cancel"
    const val EDIT = "Edit"
    const val NONE_LOADED = "None loaded yet. \"Load older\" may bring in more."
    const val OLD_PC =
        "This PC's Jarvis has no chat tags yet. Update it by running apply-patches.ps1 on the PC."
    const val COLOUR = "Colour"
    const val ICON = "Icon"
    const val SAVE = "Save"
    const val MOVE_UP = "Move up"
    const val MOVE_DOWN = "Move down"
    const val NAME_PLACEHOLDER = "Tag name"
    const val FILED_HIDDEN = "Show your chats first, then tap the one you mean."

    /** Said when the PC named no code this app knows and sent no sentence. */
    const val ERROR_FALLBACK = "Your PC did not make that change."

    /** One plain sentence per error code (section 10). */
    val ERRORS = mapOf(
        "bad_name" to "A tag name needs 1 to 24 characters, with at least one letter, number or symbol it can show.",
        "name_taken" to "You already have a tag with that name.",
        "too_many_tags" to "You can have up to 12 tags. Delete one to make room.",
        "bad_colour" to "That colour is not one of the eight.",
        "bad_icon" to "That icon is not on the list.",
        "tag_not_found" to "That tag is gone. Reload History to see your tags.",
        "not_found" to "That chat is gone - it may have been deleted.",
        "bad_request" to "That request was not understood.",
    )

    // ---------------------------------------------------------- reading ---

    /** One tag. [count] is the PC's number of chats filed under it (0 when the PC did not say). */
    data class Tag(
        val id: Int,
        val name: String,
        val colour: Int,
        val icon: String,
        val order: Int,
        val count: Int = 0,
    )

    /** `GET /api/history/tags`: the tags in the owner's order, and how many chats have none. */
    data class View(val tags: List<Tag>, val untagged: Int)

    private fun JsonObject.prim(key: String): JsonPrimitive? = this[key] as? JsonPrimitive

    private fun JsonObject.str(key: String): String? =
        prim(key)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.whole(key: String): Long? = prim(key)?.takeIf { !it.isString }?.longOrNull

    private fun JsonObject.flag(key: String): Boolean? = prim(key)?.takeIf { !it.isString }?.booleanOrNull

    /** One tag from the wire, or null when it has no usable id or name. Extra fields are ignored. */
    fun tag(o: JsonObject): Tag? {
        val id = o.whole("id")?.toInt()?.takeIf { it > 0 } ?: return null
        val name = o.str("name") ?: return null
        return Tag(
            id = id,
            name = name,
            colour = slot(o.whole("colour")?.toInt() ?: 6),
            icon = o.str("icon")?.takeIf { it in ICONS } ?: "folder",
            order = o.whole("order")?.toInt() ?: 0,
            count = (o.whole("count")?.toInt() ?: 0).coerceAtLeast(0),
        )
    }

    /** The tags of an answer in the owner's order (their `order`, then id), ids unique. */
    fun tagList(arr: Any?): List<Tag> {
        val seen = HashSet<Int>()
        return (arr as? JsonArray).orEmpty()
            .mapNotNull { (it as? JsonObject)?.let(::tag) }
            .filter { seen.add(it.id) }
            .sortedWith(compareBy({ it.order }, { it.id }))
    }

    /** `GET /api/history/tags`, or null when the body is not one (an older PC, or `ok: false`). */
    fun view(body: JsonObject): View? {
        if (body.flag("ok") == false) return null
        val arr = body["tags"] as? JsonArray ?: return null
        return View(tagList(arr), (body.whole("untagged")?.toInt() ?: 0).coerceAtLeast(0))
    }

    /** What a write came to: [said] is the plain sentence to show when it did not work. */
    data class Write(val ok: Boolean, val said: String? = null, val tag: Tag? = null, val tags: List<Tag>? = null)

    /**
     * A POST's answer: [code] and [body] as the PC sent them. `ok: true` is
     * success (the changed tag and the new list ride along when sent);
     * `ok: false` carries the code in `error` and, usually, the PC's own
     * sentence in `message` - which wins, since the PC wrote it for the
     * owner. With no sentence, this app's own one for that code.
     */
    fun write(code: Int, body: JsonObject?): Write {
        val ok = body?.flag("ok")
        if (body != null && ok == true) {
            return Write(
                ok = true,
                tag = (body["tag"] as? JsonObject)?.let(::tag),
                tags = (body["tags"] as? JsonArray)?.let(::tagList),
            )
        }
        if (body == null && code in 200..299) return Write(ok = true)
        return Write(ok = false, said = errorSentence(body?.str("error"), body?.str("message")))
    }

    /**
     * The sentence for an error [code] the PC named - the same rule as the
     * desktop's `errorWords`: a code this app has a sentence for wins, except
     * `bad_request`, a catch-all whose real reason ("Chat history is off...")
     * is in the PC's own [message]; then that message; then `bad_request`'s
     * sentence; then [ERROR_FALLBACK].
     */
    fun errorSentence(code: String?, message: String? = null): String {
        if (code != null && code != "bad_request") ERRORS[code]?.let { return it }
        message?.trim()?.takeIf { it.isNotEmpty() }?.let { return it }
        return if (code == "bad_request") ERRORS.getValue("bad_request") else ERROR_FALLBACK
    }

    // --------------------------------------------------------- requests ---

    private fun name(raw: String): String = Normalizer.normalize(raw, Normalizer.Form.NFC).trim()

    /** Blank fillers that take room but show nothing (Hangul fillers, Braille blank). */
    private val BLANKS = setOf(0x3164, 0x115F, 0x1160, 0xFFA0, 0x2800)

    /** Character types a person can see: letters, marks, numbers, punctuation, symbols. */
    private val VISIBLE_TYPES = setOf(
        Character.UPPERCASE_LETTER, Character.LOWERCASE_LETTER, Character.TITLECASE_LETTER,
        Character.MODIFIER_LETTER, Character.OTHER_LETTER, Character.NON_SPACING_MARK,
        Character.ENCLOSING_MARK, Character.COMBINING_SPACING_MARK, Character.DECIMAL_DIGIT_NUMBER,
        Character.LETTER_NUMBER, Character.OTHER_NUMBER, Character.CONNECTOR_PUNCTUATION,
        Character.DASH_PUNCTUATION, Character.START_PUNCTUATION, Character.END_PUNCTUATION,
        Character.INITIAL_QUOTE_PUNCTUATION, Character.FINAL_QUOTE_PUNCTUATION,
        Character.OTHER_PUNCTUATION, Character.MATH_SYMBOL, Character.CURRENCY_SYMBOL,
        Character.MODIFIER_SYMBOL, Character.OTHER_SYMBOL,
    ).map { it.toInt() }.toSet()

    private fun shows(cp: Int): Boolean = cp !in BLANKS && Character.getType(cp) in VISIBLE_TYPES

    /** How many characters (code points, not UTF-16 units: an emoji is one) a name has. */
    fun nameLength(s: String): Int = s.codePointCount(0, s.length)

    /**
     * [raw] cut to [NAME_MAX] code points, never inside a surrogate pair -
     * for the text box, so a 25th character is not typed in.
     */
    fun clipName(raw: String): String {
        if (nameLength(raw) <= NAME_MAX) return raw
        return raw.substring(0, raw.offsetByCodePoints(0, NAME_MAX))
    }

    /**
     * A name the PC would take, or null: nothing is sent. Normalised (NFC),
     * trimmed, 1-24 code points, and at least one character it can show.
     */
    fun validName(raw: String): String? {
        val n = name(raw)
        if (nameLength(n) !in 1..NAME_MAX) return null
        var i = 0
        while (i < n.length) {
            val cp = n.codePointAt(i)
            if (shows(cp)) return n
            i += Character.charCount(cp)
        }
        return null
    }

    fun addBody(rawName: String, colour: Int? = null, icon: String? = null): String? {
        val n = validName(rawName) ?: return null
        return buildJsonObject {
            put("op", "add")
            put("name", n)
            if (colour != null && colour in COLOUR_NAMES.indices) put("colour", colour)
            if (icon != null && icon in ICONS) put("icon", icon)
        }.toString()
    }

    fun renameBody(id: Int, rawName: String): String? {
        val n = validName(rawName) ?: return null
        return buildJsonObject {
            put("op", "rename")
            put("id", id)
            put("name", n)
        }.toString()
    }

    fun styleBody(id: Int, colour: Int? = null, icon: String? = null): String? {
        if (colour == null && icon == null) return null
        if (colour != null && colour !in COLOUR_NAMES.indices) return null
        if (icon != null && icon !in ICONS) return null
        return buildJsonObject {
            put("op", "style")
            put("id", id)
            if (colour != null) put("colour", colour)
            if (icon != null) put("icon", icon)
        }.toString()
    }

    /** `before` null moves the tag to the end of the list. */
    fun moveBody(id: Int, before: Int?): String = buildJsonObject {
        put("op", "move")
        put("id", id)
        if (before == null) put("before", JsonNull) else put("before", before)
    }.toString()

    /** "Move up": before the tag above it, or null when it is already first. */
    fun moveUpBody(tags: List<Tag>, id: Int): String? {
        val i = tags.indexOfFirst { it.id == id }
        return if (i <= 0) null else moveBody(id, tags[i - 1].id)
    }

    /** "Move down": before the tag two below it, or to the end; null when it is already last. */
    fun moveDownBody(tags: List<Tag>, id: Int): String? {
        val i = tags.indexOfFirst { it.id == id }
        if (i < 0 || i >= tags.lastIndex) return null
        return moveBody(id, tags.getOrNull(i + 2)?.id)
    }

    fun deleteBody(id: Int): String = buildJsonObject {
        put("op", "delete")
        put("id", id)
    }.toString()

    /** File one chat under [tagId], or unfile it with null. */
    fun fileBody(chatId: String, tagId: Int?): String = buildJsonObject {
        put("id", chatId)
        if (tagId == null) put("tag_id", JsonNull) else put("tag_id", tagId)
    }.toString()

    // ---------------------------------------------------------- grouping ---

    /**
     * One section of the grouped list: a tag ([tag] null = Untagged), its
     * loaded rows and the [count] its header shows.
     */
    data class Section(val tag: Tag?, val rows: List<ChatLog.Summary>, val count: Int) {
        /** The key open/closed is remembered under: the tag id, or [UNTAGGED_KEY]. */
        val key: Int get() = tag?.id ?: UNTAGGED_KEY
    }

    /** The filter chip's value for "Untagged" (`GET /api/history?tag=none`). */
    const val NONE_FILTER = "none"

    /**
     * A filter chip's value as the key [group] narrows to: null for All (""),
     * [UNTAGGED_KEY] for "none", else the tag id (null when it is not a number).
     */
    fun filterKey(filter: String): Int? = when {
        filter.isEmpty() -> null
        filter == NONE_FILTER -> UNTAGGED_KEY
        else -> filter.toIntOrNull()
    }

    /**
     * Whether a chat filed under [tagId] still belongs in the list the chip
     * [filter] shows (so a chat filed elsewhere leaves a filtered list at once).
     */
    fun matchesFilter(filter: String, tagId: Int?): Boolean = when (val key = filterKey(filter)) {
        null -> true
        UNTAGGED_KEY -> tagId == null
        else -> tagId == key
    }

    /** The open/closed flag key of the Untagged section (a tag id is never negative). */
    const val UNTAGGED_KEY = -1

    /**
     * [rows] in sections, the same as the desktop's `groupRows`: one per tag
     * in the owner's order, newest chat first inside each, and Untagged LAST.
     * A row whose tag is not in the list (deleted elsewhere) counts as
     * untagged. With no tags at all there are no sections (the caller draws a
     * flat list).
     *
     * A section's header count is the PC's own when nothing narrows the list
     * ([exact]) and never less than the rows loaded; when a "Show" kind or the
     * title words narrow it ([exact] false) it is the rows shown. A section
     * with no rows shown and no count is left out - an empty header says
     * nothing. [only] narrows to one tag id, or to [UNTAGGED_KEY].
     */
    fun group(
        rows: List<ChatLog.Summary>,
        tags: List<Tag>,
        untagged: Int,
        only: Int? = null,
        exact: Boolean = true,
    ): List<Section> {
        if (tags.isEmpty()) return emptyList()
        val known = tags.mapTo(HashSet()) { it.id }
        fun newest(list: List<ChatLog.Summary>) = list.sortedByDescending { it.updated ?: 0L }
        val out = ArrayList<Section>()
        for (t in tags) {
            if (only != null && only != t.id) continue
            val mine = newest(rows.filter { it.tagId == t.id })
            val count = if (exact) maxOf(t.count, mine.size) else mine.size
            if (mine.isNotEmpty() || count > 0) out += Section(t, mine, count)
        }
        if (only == null || only == UNTAGGED_KEY) {
            val loose = newest(
                rows.filter { r ->
                    val t = r.tagId
                    t == null || t !in known
                },
            )
            val count = if (exact) maxOf(untagged, loose.size) else loose.size
            if (loose.isNotEmpty() || count > 0) out += Section(null, loose, count)
        }
        return out
    }

    // ------------------------------------------------- "file it" flow ---

    /** An older chat to file: the tag to file it under and the words to search for. */
    data class FileUnder(val tagId: Int, val query: String)

    /**
     * "label my chat about the boiler as Home": the answer's `X-Jarvis-Route`
     * says `open_brain: "history"`, `file_under: <tag id>` and
     * `history_q: "<search words>"`. Null unless all three are usable.
     * Pure navigation - nothing is filed until the owner taps a chat.
     */
    fun fileUnderFromRoute(header: String?): FileUnder? {
        if (header.isNullOrBlank()) return null
        val o = runCatching { JarvisJson.parseToJsonElement(header.trim()) as? JsonObject }.getOrNull()
            ?: return null
        if (o.str("open_brain") != "history") return null
        val id = o.whole("file_under")?.toInt()?.takeIf { it > 0 } ?: return null
        val q = o.str("history_q")?.take(ChatLog.SEARCH_MAX_CHARS) ?: return null
        return FileUnder(id, q)
    }
}
