package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * "Notification styles you describe" (the owner's ask of 2026-10-30;
 * docs/JARVIS-API.md section 167; backend jarvis_notification_styles.py).
 *
 * A style is a small CHECKED DESCRIPTION the PC keeps - a colour name, a
 * figure, an animation, a speed and which notifications it is for - never
 * code, never a colour value, never a layout, never a URL. The PC's AI model
 * only turns the owner's words into it; the PC checks it with plain code; the
 * phone shows a preview and the owner taps Add.
 *
 * This file holds the words, the wire enums, and the ONE decision every
 * notifier asks: [plan] - "may a notification of this kind use a style right
 * now, and exactly what should be drawn". It is pure Kotlin, no Android
 * types, so the JVM tests run every rule here. [com.jarvis.client.service.StyledNotification]
 * turns a [Plan] into RemoteViews and nothing else.
 *
 * WHY THE ANIMATION IS WHAT IT IS. Android inflates a notification's custom
 * layout inside SystemUI, in another process, from the short list of View
 * classes RemoteViews allows. Two of those animate on their own, with no help
 * from this app: `ViewFlipper` (two or more frames, `autoStart`, a flip
 * interval) and an indeterminate `ProgressBar`. So the animation the owner
 * picks is one SystemUI performs itself: it keeps running when Jarvis' process
 * is dead, it costs this app no wakeups, and it never posts a frame. That is
 * also why an arbitrary animation, a GIF or a Lottie file cannot be offered -
 * those need a custom View class, and RemoteViews refuses every class that is
 * not on its list.
 *
 * The privacy floor lives in [plan]: while the phone is locked, or App lock /
 * "Hide memory lists and chat history" is on, it returns null and the
 * notification is drawn exactly as it was before this feature existed. The
 * pretty layout therefore never handles a redacted body - it is not there.
 */
object NotificationStyle {
    const val LIST_PATH = "/api/notification-styles"
    const val DRAFT_PATH = "/api/notification-styles/draft"
    const val ADD_PATH = "/api/notification-styles/add"
    const val DISCARD_PATH = "/api/notification-styles/discard"
    const val DELETE_PATH = "/api/notification-styles/delete"
    val POST_PATHS = setOf(DRAFT_PATH, ADD_PATH, DISCARD_PATH, DELETE_PATH)

    const val TITLE = "Notification styles"
    const val DETAIL =
        "Describe how Jarvis' notifications should look and Jarvis makes a preview: a colour, " +
            "a figure, an animation and a speed, from a fixed menu. You see the preview first, " +
            "and nothing changes until you tap Add."
    const val PHONE_HINT =
        "For example: \"warm orange, a spark, pulsing, for reminders\". You can also say " +
            "\"make my notifications look like ...\" to Jarvis. A style never changes what a " +
            "notification says, what it offers, or whether it makes a sound - and while your " +
            "phone is locked, or App lock is on, Jarvis uses the plain notification instead."
    const val EMPTY = "No styles yet."
    const val MISSING = "Your PC's Jarvis cannot style notifications yet - run apply-patches.ps1 on the PC."
    const val PREVIEW_TITLE = "Preview - not added yet"
    const val MAKE_LABEL = "Make a preview"
    const val MAKING_LABEL = "Making…"
    const val ADD_LABEL = "Add"
    const val DISCARD_LABEL = "Discard"
    const val DELETE_LABEL = "Delete"
    const val LIVE_TITLE = "Live now"
    const val NO_WORDS =
        "Say how the notifications should look - for example, warm orange, a spark, pulsing."
    const val MAX_WORDS = 300
    const val MAX_NAME = 40
    const val HIDDEN_WORDS = "Hidden - open Jarvis to see it."
    const val STILL = "still"
    const val CARD_NOTE =
        "A style is not an approval card: it shows nothing new, adds no button, and changes " +
            "nothing about what Jarvis may do."

    // ---------------------------------------------------------------- kinds

    /**
     * Which notification a style may be used on. A CLOSED list, and only the
     * two notifiers that were given a custom layout: the approval card and an
     * ordinary reminder/timer. Everything else - the link's own ongoing line,
     * Live, the chatbot line, a hand-off, the alarm that keeps ringing - keeps
     * the plain layout on purpose, because an animation there would be noise
     * (or, for the ringing alarm, a second thing moving on screen).
     */
    enum class Kind(val wire: String) {
        APPROVAL("approval"),
        REMINDER("reminder"),
        ;

        companion object {
            fun fromWire(s: String?): Kind? = entries.firstOrNull { it.wire == s }
        }
    }

    // --------------------------------------------------------------- themes

    /**
     * The accent, and the dark chip drawn behind the figure.
     *
     * Both values are the app's own palette steps (`face/Palette.kt`): the
     * chip is a `-2` step, which is dark in every family, and the glyph is the
     * matching `-4` step, which is bright in every family. That pairing is why
     * the figure stays readable on a notification whatever colour the shade's
     * own background happens to be - the one thing the research note warns
     * about for custom layouts.
     */
    enum class Theme(val wire: String, val accent: Int, val chip: Int) {
        ICE("ice", 0xFF6FE3FF.toInt(), 0xFF12657F.toInt()),
        AZURE("azure", 0xFF62A3FF.toInt(), 0xFF14479A.toInt()),
        INDIGO("indigo", 0xFF7B7BFF.toInt(), 0xFF2B2B8F.toInt()),
        EMBER("ember", 0xFFFF9B52.toInt(), 0xFF8A3A0E.toInt()),
        ROSE("rose", 0xFFFF7B86.toInt(), 0xFF8F1B28.toInt()),
        MONO("mono", 0xFF8FA3B8.toInt(), 0xFF1E2833.toInt()),
        ;

        companion object {
            fun fromWire(s: String?): Theme? = entries.firstOrNull { it.wire == s }
        }
    }

    /**
     * The figure: ONE character from a fixed list, drawn in a TextView.
     *
     * Not the owner's real face. The sea otter, the red panda and the others
     * are GL/Compose drawings, and a View class RemoteViews does not know
     * cannot be inflated inside a notification at all - never mind animated.
     * Putting the real face in a notification would mean pre-rendered PNG
     * frames, which this first slice deliberately leaves out (research note,
     * "what is left out").
     */
    enum class Figure(val wire: String, val glyph: String) {
        SPARK("spark", "\u2726"),
        RING("ring", "\u25CE"),
        DOT("dot", "\u25CF"),
        STAR("star", "\u2727"),
        ARROW("arrow", "\u27A4"),
        NONE("none", ""),
        ;

        companion object {
            fun fromWire(s: String?): Figure? = entries.firstOrNull { it.wire == s }
        }
    }

    /**
     * The animation. Every one of these is performed by SystemUI itself:
     *  - NONE   one frame; nothing moves;
     *  - PULSE  a ViewFlipper over two frames - the glyph bright, then dim;
     *  - FLIP   a ViewFlipper over two frames - the glyph, then a dot;
     *  - SPINNER an indeterminate ProgressBar.
     * `ViewFlipper` and `ProgressBar` are both on RemoteViews' allow-list and
     * both animate without the app, which is the whole reason the menu is
     * this short.
     */
    enum class Motion(val wire: String, val animated: Boolean) {
        NONE("none", false),
        PULSE("pulse", true),
        FLIP("flip", true),
        SPINNER("spinner", true),
        ;

        companion object {
            fun fromWire(s: String?): Motion? = entries.firstOrNull { it.wire == s }
        }
    }

    /** How fast a two-frame animation flips. Buckets, never a raw number. */
    enum class Speed(val wire: String, val intervalMs: Int) {
        SLOW("slow", 1800),
        NORMAL("normal", 900),
        FAST("fast", 450),
        ;

        companion object {
            fun fromWire(s: String?): Speed? = entries.firstOrNull { it.wire == s }
        }
    }

    // ---------------------------------------------------------------- spec

    /** One checked style, exactly as the PC keeps it. */
    data class Spec(
        val name: String,
        val theme: Theme,
        val figure: Figure,
        val motion: Motion,
        val speed: Speed,
        val kinds: List<Kind>,
    )

    /** One saved style or preview, as the Brain lists it. */
    data class Row(val id: String, val name: String, val said: String, val parts: List<String>)

    /** What the PC says is live, plus the menu's own words for the plate. */
    data class Book(
        val active: Map<Kind, Spec>,
        val live: List<String>,
        val styles: List<Row>,
        val drafts: List<Row>,
        val noCard: String,
        val nothingOn: String,
    ) {
        fun forKind(kind: Kind): Spec? = active[kind]

        companion object {
            val EMPTY = Book(emptyMap(), emptyList(), emptyList(), emptyList(), "", "")
        }
    }

    // -------------------------------------------------------------- drawing

    /** One frame of a flipping figure. */
    data class Frame(val glyph: String, val colour: Int)

    /**
     * Exactly what one notification should draw. Produced only by [plan], so
     * there is one place that can say "no".
     */
    data class Plan(
        val theme: Theme,
        val chip: Int,
        val frames: List<Frame>,
        val intervalMs: Int,
        val spinner: Boolean,
        /** Set when nothing moves: the one glyph drawn outside the flipper. */
        val stillGlyph: String?,
    )

    /**
     * THE decision. Null means "draw the plain notification exactly as
     * before":
     *
     *  - no style for this kind;
     *  - [locked] - App lock, "Hide memory lists and chat history", or a phone
     *    with no secure lock screen. This is the privacy floor: the styled
     *    layout is never handed a redacted body, because it is not used at
     *    all while content is being hidden;
     *  - a kind this style does not claim.
     *
     * Never null for a reason that depends on the content: a style is only
     * ever a look.
     */
    fun plan(spec: Spec?, kind: Kind, locked: Boolean): Plan? {
        if (spec == null || locked) return null
        if (kind !in spec.kinds) return null
        val accent = spec.theme.accent
        val dim = blend(accent, spec.theme.chip, 0.45f)
        val frames = when (spec.motion) {
            Motion.NONE, Motion.SPINNER -> emptyList()
            Motion.PULSE -> listOf(
                Frame(spec.figure.glyph, accent),
                Frame(spec.figure.glyph, dim),
            )
            Motion.FLIP -> listOf(
                Frame(spec.figure.glyph, accent),
                Frame(Figure.DOT.glyph, accent),
            )
        }
        return Plan(
            theme = spec.theme,
            chip = spec.theme.chip,
            frames = frames,
            // A style with nothing to flip gets a flip interval far beyond any
            // notification's life, so SystemUI is not asked to run a timer for
            // a picture that never changes.
            intervalMs = if (frames.size < 2) 600_000 else spec.speed.intervalMs,
            spinner = spec.motion == Motion.SPINNER,
            // The figure stays put while a spinner runs beside it; it is only
            // drawn outside the flipper when the flipper is not used at all.
            stillGlyph = if (frames.isEmpty()) spec.figure.glyph else null,
        )
    }

    /** [a] moved [k] of the way to [b]; plain integer maths, no Android. */
    private fun blend(a: Int, b: Int, k: Float): Int {
        fun ch(shift: Int): Int {
            val av = (a shr shift) and 0xFF
            val bv = (b shr shift) and 0xFF
            return (av + (bv - av) * k).toInt().coerceIn(0, 255)
        }
        val alpha = (a ushr 24) and 0xFF
        return (alpha shl 24) or (ch(16) shl 16) or (ch(8) shl 8) or ch(0)
    }

    // ---------------------------------------------------------------- wire

    private fun str(e: JsonElement?): String? = (e as? JsonPrimitive)?.takeIf { it.isString }?.content

    private fun isTrue(e: JsonElement?) =
        (e as? JsonPrimitive)?.let { !it.isString && it.content == "true" } == true

    /**
     * One style from a JSON object, or null.
     *
     * Strict on purpose: every key must be present and every value must be a
     * known wire name. Anything else - a colour value, a layout, a URL, a
     * motion this app does not know - is not "close enough", it is unusable,
     * and the notification falls back to the plain layout. That is the second
     * check of the PC's first one, and it fails closed.
     */
    fun fromJson(o: JsonObject?): Spec? {
        if (o == null) return null
        val name = JarvisWidgets.text(o["name"], MAX_NAME)
        if (name.isEmpty()) return null
        val theme = Theme.fromWire(str(o["theme"])) ?: return null
        val figure = Figure.fromWire(str(o["figure"])) ?: return null
        val motion = Motion.fromWire(str(o["motion"])) ?: return null
        val speed = Speed.fromWire(str(o["speed"])) ?: return null
        val raw = (o["kinds"] as? JsonArray) ?: return null
        val kinds = raw.mapNotNull { Kind.fromWire(str(it)) }.distinct()
        if (kinds.isEmpty()) return null
        if (kinds.size != raw.size) return null
        return Spec(name, theme, figure, motion, speed, kinds)
    }

    /** `GET /api/notification-styles` -> the book the phone draws from. */
    fun bookOf(ans: JsonObject?): Book {
        if (ans == null) return Book.EMPTY
        fun rows(e: JsonElement?): List<Row> =
            ((e as? JsonArray) ?: JsonArray(emptyList())).mapNotNull { el ->
                val o = el as? JsonObject ?: return@mapNotNull null
                val id = str(o["id"]) ?: return@mapNotNull null
                Row(
                    id = id,
                    name = JarvisWidgets.text(o["name"], MAX_NAME),
                    said = JarvisWidgets.text(o["said"], 400),
                    parts = ((o["parts"] as? JsonArray) ?: JsonArray(emptyList()))
                        .map { JarvisWidgets.text(it, 160) }.filter { it.isNotEmpty() },
                )
            }
        val active = LinkedHashMap<Kind, Spec>()
        (ans["active"] as? JsonObject)?.forEach { (k, v) ->
            val kind = Kind.fromWire(k) ?: return@forEach
            fromJson(v as? JsonObject)?.let { active[kind] = it }
        }
        return Book(
            active = active,
            live = ((ans["live"] as? JsonArray) ?: JsonArray(emptyList()))
                .mapNotNull { str(it) }.filter { Kind.fromWire(it) != null },
            styles = rows(ans["styles"]),
            drafts = rows(ans["drafts"]),
            noCard = JarvisWidgets.text(ans["no_card"], 400),
            nothingOn = JarvisWidgets.text(ans["nothing_on"], 200),
        )
    }

    /** A saved style's id: "s" and ten hex digits. */
    fun validId(id: String?): Boolean = id != null && Regex("s[0-9a-f]{10}").matches(id)

    /** A preview's id: "d" and ten hex digits. */
    fun validDraft(id: String?): Boolean = id != null && Regex("d[0-9a-f]{10}").matches(id)

    /** The draft's body: the owner's typed words. */
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
            error != null && obj?.get("ok")?.let { !isTrue(it) } == true -> false to error
            code == 404 || code == 501 -> false to MISSING
            else -> false to "Jarvis could not do that just now."
        }
    }

    /** One line for the plate: "Live for reminders: Ember pulse." */
    fun liveLine(book: Book): String {
        if (book.live.isEmpty()) return book.nothingOn.ifEmpty { "No style is live." }
        val names = book.live.mapNotNull { w ->
            val k = Kind.fromWire(w) ?: return@mapNotNull null
            val n = book.active[k]?.name ?: return@mapNotNull null
            when (k) {
                Kind.APPROVAL -> "approval cards"
                Kind.REMINDER -> "reminders"
            } to n
        }
        if (names.isEmpty()) return book.nothingOn.ifEmpty { "No style is live." }
        return "Live now: " + names.joinToString(", ") { (who, n) -> "$who - $n" } + "."
    }
}
