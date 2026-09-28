package com.jarvis.client.net

import com.jarvis.client.data.TileAction
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.put

/**
 * "Widgets you describe" (the owner's choice of 2026-09-28, the SAFE
 * version; docs/JARVIS-API.md section 86; backend jarvis_widgets.py).
 *
 * A widget is a small CHECKED DESCRIPTION the PC keeps - a heading, numbers,
 * short lists, a bar and up to four buttons from a fixed menu - never code.
 * The PC's AI model only turns the owner's words into it; the PC checks it
 * with plain code; the owner sees a preview and taps Add.
 *
 * This file holds the words (the desktop's widget-board.js has the same)
 * and the ONE rule for drawing a widget the PC filled in ([viewOf], [hide]),
 * held to the desktop's and the PC's by contract/widget-cases.json
 * (tools/gen_widget_cases.py; JarvisWidgetsTest). The app checks again what
 * the PC already checked: an unknown block type or button is left out, and
 * a source this app does not know is treated as private - so a PC answer
 * can never put a button on the home screen this app does not already know
 * is safe. The buttons ARE the Quick Settings tile actions ([TileAction]).
 *
 * Pure Kotlin, no Android types, so the JVM tests run every rule here.
 */
object JarvisWidgets {
    const val LIST_PATH = "/api/widgets"
    const val SHOW_PATH = "/api/widgets/show"
    const val DRAFT_PATH = "/api/widgets/draft"
    const val ADD_PATH = "/api/widgets/add"
    const val DISCARD_PATH = "/api/widgets/discard"
    const val DELETE_PATH = "/api/widgets/delete"
    val POST_PATHS = setOf(DRAFT_PATH, ADD_PATH, DISCARD_PATH, DELETE_PATH)

    const val TITLE = "Widgets"
    const val DETAIL =
        "Describe a small widget and Jarvis makes a preview: a heading, numbers, short lists, a bar " +
            "and up to four buttons, from a fixed menu. You see the preview first, and nothing is added " +
            "until you tap Add. Delete removes one at once."
    const val PHONE_HINT =
        "For example: \"my next 3 reminders, my to-do count and a 10-minute timer button\". You can " +
            "also say \"make me a widget showing ...\" to Jarvis. Then give it a home-screen slot below, " +
            "and add \"Jarvis widget 1\", \"2\" or \"3\" to your home screen (touch and hold the home " +
            "screen, then Widgets, then Jarvis)."
    const val EMPTY = "No widgets yet."
    const val MISSING = "Your PC's Jarvis cannot make widgets yet - run apply-patches.ps1 on the PC."
    const val PREVIEW_TITLE = "Preview - not added yet"
    const val MAKE_LABEL = "Make a preview"
    const val MAKING_LABEL = "Making…"
    const val ADD_LABEL = "Add"
    const val DISCARD_LABEL = "Discard"
    const val DELETE_LABEL = "Delete"
    const val HIDDEN_WORDS = "Hidden - open Jarvis to see it."
    const val NO_WORDS =
        "Say what the widget should show - for example, your next 3 reminders and a timer button."
    const val MAX_WORDS = 300
    const val SLOTS_TITLE = "On your home screen"
    const val NOTHING = "Nothing"
    const val SLOT_NOTE =
        "The home screen can be seen without unlocking Jarvis: with App lock or \"Hide memory lists " +
            "and chat history\" on, a home-screen widget shows counts but not the words of your " +
            "reminders, to-do items or what is playing. With App lock on, its buttons only open " +
            "Jarvis, which asks you to unlock it first - except Stop everything. Nothing but " +
            "Stop everything works while the connection is catching up."

    // The home-screen widget's own lines.
    const val W_NOT_STARTED = "Jarvis could not start"
    const val W_NOT_STARTED_SUB = "Tap to open and see why"
    const val W_NOT_PAIRED = "Not paired"
    const val W_NOT_PAIRED_SUB = "Tap to open Jarvis and pair"
    const val W_NONE = "No widget chosen"
    const val W_NONE_SUB = "Tap, then choose one under Brain, Widgets"
    const val W_STALE = "Not up to date"
    const val W_STALE_SUB = "Tap to open Jarvis and connect"
    const val W_GONE = "This widget was deleted"
    const val W_FAILED = "Could not read this widget"

    const val MAX_BLOCKS = 8
    const val MAX_ITEMS = 5
    const val MAX_NAME = 40
    const val MAX_TEXT = 60
    const val MAX_LABEL = 40
    const val SLOTS = 3

    /** Sources whose words are the owner's own (or another program's). */
    val PRIVATE_SOURCES = listOf("now_playing", "reminders", "timers", "today", "todo")
    private val KNOWN_SOURCES = PRIVATE_SOURCES + listOf(
        "disk_free", "email_count", "events_count", "focus", "reminders_count", "todo_count",
    )

    sealed interface Block {
        data class Title(val text: String) : Block
        data class Button(val action: TileAction) : Block {
            val label: String get() = action.tileLabel
        }
        data class Count(
            val label: String, val value: String, val note: String,
            val private: Boolean, val hidden: Boolean,
        ) : Block
        data class Items(
            val label: String, val items: List<Pair<String, String>>, val more: Int,
            val empty: String, val note: String, val private: Boolean, val hidden: Boolean,
        ) : Block
        data class Progress(
            val label: String, val fraction: Double, val value: String, val note: String,
            val private: Boolean, val hidden: Boolean,
        ) : Block
    }

    data class View(val name: String, val blocks: List<Block>)

    private val WS = Regex("[ \\t\\n\\r\\u000B\\u000C]+")

    private fun str(e: JsonElement?): String? = (e as? JsonPrimitive)?.takeIf { it.isString }?.content

    /** Text as both apps draw it: control and format characters out, ASCII
     *  white space collapsed, at most [cap] characters (code points). */
    fun text(e: JsonElement?, cap: Int): String {
        val s = str(e) ?: return ""
        val sb = StringBuilder()
        var i = 0
        while (i < s.length) {
            val cp = s.codePointAt(i)
            val type = Character.getType(cp)
            val ws = cp == 0x20 || cp == 0x09 || cp == 0x0A || cp == 0x0D || cp == 0x0B || cp == 0x0C
            if (ws || (type != Character.CONTROL.toInt() && type != Character.FORMAT.toInt())) {
                sb.appendCodePoint(cp)
            }
            i += Character.charCount(cp)
        }
        val collapsed = WS.replace(sb, " ").trim(' ')
        val n = collapsed.codePointCount(0, collapsed.length)
        val cut = if (n <= cap) collapsed else collapsed.substring(0, collapsed.offsetByCodePoints(0, cap))
        return cut.trimEnd(' ')
    }

    private fun isTrue(e: JsonElement?) = (e as? JsonPrimitive)?.let { !it.isString && it.content == "true" } == true
    private fun isFalse(e: JsonElement?) = (e as? JsonPrimitive)?.let { !it.isString && it.content == "false" } == true

    private fun count(e: JsonElement?): Int {
        val p = e as? JsonPrimitive ?: return 0
        if (p.isString || !Regex("\\d+").matches(p.content)) return 0
        return p.content.toIntOrNull() ?: 0
    }

    private fun fraction(e: JsonElement?): Double {
        val p = e as? JsonPrimitive ?: return 0.0
        if (p.isString || p.content == "true" || p.content == "false") return 0.0
        val d = p.doubleOrNull ?: return 0.0
        return if (d.isNaN()) 0.0 else d.coerceIn(0.0, 1.0)
    }

    /** The blocks this app draws from one `GET /api/widgets/show` answer, or null. */
    fun viewOf(ans: JsonObject?): View? {
        if (ans == null || !isTrue(ans["ok"])) return null
        val blocks = (ans["blocks"] as? JsonArray) ?: JsonArray(emptyList())
        val out = mutableListOf<Block>()
        for (el in blocks.take(MAX_BLOCKS)) {
            val b = el as? JsonObject ?: continue
            when (str(b["type"])) {
                "title" -> text(b["text"], MAX_TEXT).takeIf { it.isNotEmpty() }?.let { out += Block.Title(it) }
                "button" -> TileAction.fromWire(str(b["action"]))?.let { out += Block.Button(it) }
                "number", "list", "progress" -> {
                    val src = str(b["source"]) ?: ""
                    val private = !isFalse(b["private"]) || src !in KNOWN_SOURCES || src in PRIVATE_SOURCES
                    val label = text(b["label"], MAX_LABEL)
                    val note = text(b["note"], 120)
                    out += when (str(b["type"])) {
                        "number" -> Block.Count(label, text(b["value"], 20), note, private, false)
                        "list" -> {
                            val items = ((b["items"] as? JsonArray) ?: JsonArray(emptyList()))
                                .mapNotNull { it as? JsonObject }
                            Block.Items(
                                label = label,
                                items = items.take(MAX_ITEMS).map { text(it["text"], 120) to text(it["when"], 40) },
                                more = count(b["more"]) + maxOf(0, items.size - MAX_ITEMS),
                                empty = text(b["empty"], 60),
                                note = note, private = private, hidden = false,
                            )
                        }
                        else -> Block.Progress(label, fraction(b["fraction"]), text(b["value"], 60), note, private, false)
                    }
                }
                else -> Unit
            }
        }
        return View(text(ans["name"], MAX_NAME), out)
    }

    /** The same view while private words are hidden: a private block keeps its label only. */
    fun hide(view: View): View = view.copy(
        blocks = view.blocks.map { b ->
            when (b) {
                is Block.Count -> if (b.private) b.copy(value = "", note = HIDDEN_WORDS, hidden = true) else b
                is Block.Items -> if (b.private) {
                    b.copy(items = emptyList(), more = 0, note = HIDDEN_WORDS, hidden = true)
                } else {
                    b
                }
                is Block.Progress -> if (b.private) {
                    b.copy(fraction = 0.0, value = "", note = HIDDEN_WORDS, hidden = true)
                } else {
                    b
                }
                else -> b
            }
        },
    )

    /** One saved widget or preview, as the Brain lists it. */
    data class Row(val id: String, val name: String, val said: String, val parts: List<String>)

    data class Listing(
        val widgets: List<Row>,
        val drafts: List<Row>,
        val noCard: String,
        val hidden: Boolean,
    )

    fun readList(ans: JsonObject?): Listing? {
        if (ans == null || ans["widgets"] !is JsonArray) return null
        fun rows(e: JsonElement?) = ((e as? JsonArray) ?: JsonArray(emptyList())).mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val id = str(o["id"]) ?: return@mapNotNull null
            Row(
                id = id,
                name = text(o["name"], MAX_NAME),
                said = text(o["said"], 400),
                parts = ((o["parts"] as? JsonArray) ?: JsonArray(emptyList())).take(MAX_BLOCKS)
                    .map { text(it, 160) }.filter { it.isNotEmpty() },
            )
        }
        return Listing(rows(ans["widgets"]), rows(ans["drafts"]), text(ans["no_card"], 400), isTrue(ans["hidden"]))
    }

    /** A saved widget's id: "w" and ten hex digits. */
    fun validId(id: String?): Boolean = id != null && Regex("w[0-9a-f]{10}").matches(id)

    /** A preview's id: "d" and ten hex digits. */
    fun validDraft(id: String?): Boolean = id != null && Regex("d[0-9a-f]{10}").matches(id)

    /** The draft's body: the owner's typed words. The phone cannot tell a
     *  paste from typing in a Compose text field, so it always says typed. */
    fun draftBody(words: String): String? {
        val w = words.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")
        if (w.isEmpty() || w.codePointCount(0, w.length) > MAX_WORDS) return null
        return buildJsonObject {
            put("words", w)
            put("provenance", "typed")
        }.toString()
    }

    fun idBody(key: String, id: String): String = buildJsonObject { put(key, id) }.toString()

    /** A POST's answer: (changed, the sentence to show). */
    fun said(code: Int, obj: JsonObject?): Pair<Boolean, String> {
        val error = str(obj?.get("error"))
        return when {
            code in 200..299 -> true to (str(obj?.get("said")) ?: "Done.")
            error != null && obj?.get("ok")?.let { isFalse(it) } == true -> false to error
            code == 404 || code == 501 -> false to MISSING
            else -> false to "Jarvis could not do that just now."
        }
    }
}
