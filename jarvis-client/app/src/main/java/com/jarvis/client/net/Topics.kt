package com.jarvis.client.net

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put
import java.net.URLEncoder

/**
 * Topic controls - the phone's side of docs/TOPIC-CONTROLS-DESIGN.md (its
 * "Slice contract (frozen)", C1-C10) and docs/JARVIS-API.md section 107.
 *
 * The owner asked (2026-09-30) to include or exclude topics in Jarvis's
 * brain. Every saved fact sits under ONE topic; each topic has a mode:
 * Learn and use / Use, but don't learn / Learn, but don't use / Off. The PC
 * keeps everything (`memory.db`) and enforces it - "don't learn" before a
 * fact is saved, "don't use" inside the memory search. THE PHONE STORES
 * NOTHING: the topic list, the review batch and every name are read from the
 * PC when Brain shows them and dropped when it is left.
 *
 * The routes (all with the pairing token and `X-Jarvis-Client: hud`, which
 * JarvisApi adds; the token is never logged):
 * - `GET /api/topics`, `POST /api/topics` `{"op": add|rename|style|move|private|delete}`
 *   (`op: "words"` is the desktop's - keywords are set on the PC).
 * - `POST /api/topics/mode` `{"id", "mode"}` - 200, or 202 `{"waiting": true}`
 *   when ONE approval card (`topic_loosen`) was raised.
 * - `GET /api/topics/preview?id=&mode=`, `GET /api/topics/review`,
 *   `GET /api/topics/hidden`, `POST /api/topics/file`, `POST /api/topics/settings`.
 *
 * Rules kept here (C8): the PC decides what asks first - this file only
 * computes the LABEL "This will ask for your OK first." ([loosens],
 * [needsCard]) and the tests hold it to the same worked cases as the PC.
 * Every write is held on a stale link by the caller; names and fact words
 * are memory lists, hidden as [hiddenRow] says; a count is not.
 *
 * Pure Kotlin, no Android types, so `TopicsTest` runs it on a plain JVM.
 */
object Topics {
    const val TOPICS_PATH = "/api/topics"
    const val MODE_PATH = "/api/topics/mode"
    const val FILE_PATH = "/api/topics/file"
    const val SETTINGS_PATH = "/api/topics/settings"
    const val PREVIEW_PATH = "/api/topics/preview"
    const val REVIEW_PATH = "/api/topics/review"
    const val HIDDEN_PATH = "/api/topics/hidden"

    /** The `open_brain` value of "switch off my work topic", and Brain's item key for the section. */
    const val PLACE = "topics"

    /** Unsorted, always the first row; never renamed, deleted or made private. */
    const val UNSORTED_ID = 1

    /** The wire fallbacks when the PC sends no limits. */
    const val MAX_TOPICS = 16
    const val NAME_MAX = 24
    const val BATCH = 10
    const val FILE_MAX = 200

    /** After a 202 the plate reads the list this often until the card is decided (C2). */
    const val POLL_MS = 2_000L

    /** About five minutes of polling; then the plate stops asking and says it is still waiting. */
    const val MAX_POLLS = 150

    // ------------------------------------------------------------ words ---

    /** Every word of the shared fixture (`words`), in this app's source. `TopicsTest` holds them equal. */
    val WORDS: Map<String, String> = mapOf(
        "title" to "Topics",
        "intro" to "A topic is a folder for things Jarvis knows. Pick what Jarvis may do with each folder.",
        "sorted_guess" to "Jarvis sorted {n} of your {total} facts by guessing from the words. Check them so switching a topic off works as you expect.",
        "sorted_guess_one" to "Jarvis sorted 1 fact by guessing from the words. Check it so switching a topic off works as you expect.",
        "check_button" to "Check these ({n})",
        "check_right" to "These are right",
        "check_held" to "Held back: might be about {name}",
        "check_guessed" to "Jarvis guessed",
        "add_button" to "Add a topic",
        "private_tag" to "Private",
        "private_asks" to "This will ask for your OK first.",
        "unsorted_name" to "Unsorted",
        "kept_hidden" to "{n} facts kept, hidden",
        "kept_hidden_one" to "1 fact kept, hidden",
        "show_them" to "Show them",
        "not_used_tag" to "not used in answers",
        "skipped" to "{n} new things not saved this week",
        "skipped_one" to "1 new thing not saved this week",
        "left_out" to "Left out {n} facts because of your topic settings",
        "left_out_one" to "Left out 1 fact because of your topic settings",
        "preview_left_out" to "{n} things Jarvis knows about {name} will be left out of answers.",
        "preview_left_out_one" to "1 thing Jarvis knows about {name} will be left out of answers.",
        "preview_none" to "Nothing Jarvis knows about {name} will change in answers.",
        "preview_stop_learning" to "Jarvis will stop saving new things about {name}.",
        "preview_pinned" to "{n} pinned facts about {name} will pause until you switch it back on.",
        "preview_pinned_one" to "1 pinned fact about {name} will pause until you switch it back on.",
        "help_plain" to "Topic names and facts are stored in the same plain file on this PC. Jarvis's sorting is a guess from the words, in English only; check it.",
        "model_help" to "Let Jarvis's local model help sort",
        "model_help_note" to "Uses the model on this PC, never a cloud one, on up to 20 facts a night. It only suggests; you check.",
        "confirm_delete" to "Delete this topic? Its facts are kept; pick where they go.",
        "screen_reader" to "{name}, {n} facts, {mode}, button: change mode",
        "screen_reader_one" to "{name}, 1 fact, {mode}, button: change mode",
        "hidden_row" to "Topic {index}, {n} facts, {mode}",
        "hidden_row_one" to "Topic {index}, 1 fact, {mode}",
        "moved_line" to "Done: {name} is {mode}. You can change it in Brain.",
        "pick_line" to "Pick what Jarvis may do with {name}.",
        "no_such_topic" to "I do not have a topic called {name}.",
        "topics_are" to "Your topics are: {names}.",
        "outside" to "I do not change your topics after I have read outside text, like an email or a web page. Use Brain, then Memory, then Topics.",
        "missing" to "Your PC's Jarvis does not have topic controls yet - run apply-patches.ps1 on the PC.",
        "waiting" to "Waiting for your approval.",
        "sorting_now" to "Jarvis is still sorting {n} of your facts.",
        "pin_paused" to "Paused: {name} is off",
        "pin_paused_learn" to "Paused: {name} is set to Learn, but don't use",
        "used_left_out" to "A memory from a topic you have since switched off.",
        "ask_save" to "Save under Unsorted",
        "ask_skip" to "Skip it",
        "add_title" to "Add a topic",
        "name_label" to "Name",
        "words_label" to "Keywords (optional)",
        "words_pc_only" to "Keywords are set on your PC.",
        "delete_where" to "Where should its facts go?",
        "delete_looser" to "That home is more open than {name}: Jarvis may learn about or use these facts more than it does now.",
    )

    val ERRORS: Map<String, String> = mapOf(
        "bad_request" to "Jarvis could not understand that request.",
        "bad_name" to "A topic needs a name of 1 to 24 letters or numbers.",
        "name_taken" to "You already have a topic with that name.",
        "too_many_topics" to "You can have up to 16 topics of your own. Delete one first.",
        "bad_colour" to "That colour is not one of the eight to pick from.",
        "bad_icon" to "That picture is not one of the ones to pick from.",
        "bad_words" to "Keywords are short words or phrases, up to 20 of them.",
        "topic_not_found" to "That topic is not there any more.",
        "bad_mode" to "That is not one of the four choices.",
        "no_delete_unsorted" to "Unsorted cannot be deleted.",
        "no_rename_unsorted" to "Unsorted cannot be renamed.",
        "needs_destination" to "Pick a topic for its facts to move to first.",
        "bad_destination" to "Pick a different topic for its facts to move to.",
        "no_such_fact" to "One of those facts is not there any more.",
        "unavailable" to "Topics are not available on this PC yet.",
    )

    val LAST_WORDS: Map<String, String> = mapOf(
        "applied" to "You approved the card, so the change was made.",
        "denied" to "The card was turned down, so nothing about your topics changed.",
        "timed_out" to "Nobody answered the card in time, so nothing about your topics changed.",
        "refused" to "Your PC's settings do not let this be approved, so nothing changed.",
        "withdrawn" to "You changed this again while the card waited, so approving it changed nothing.",
        "failed" to "It was approved, but the change could not be saved, so nothing changed.",
    )

    const val GATE_FAILED = "The approval card could not be raised, so nothing changed."

    /** The four modes, exactly (C6). The picker always lists all four, in this order. */
    data class Mode(val id: String, val name: String, val sentence: String) {
        /** Whether new facts about a topic in this mode are saved. */
        val learns: Boolean get() = id == "both" || id == "learn_only"

        /** Whether facts about a topic in this mode are read into answers. */
        val uses: Boolean get() = id == "both" || id == "use_only"
    }

    val MODES: List<Mode> = listOf(
        Mode("both", "Learn and use", "Jarvis remembers new things about this and uses them in answers."),
        Mode("use_only", "Use, but don't learn", "Jarvis keeps what it knows and uses it, but saves nothing new."),
        Mode("learn_only", "Learn, but don't use", "Jarvis keeps learning quietly, but leaves this out of its answers."),
        Mode(
            "off",
            "Off",
            "Jarvis neither learns nor uses this. What it knows is kept, not deleted, and comes back when you switch it on.",
        ),
    )

    fun mode(id: String?): Mode? = MODES.firstOrNull { it.id == id }

    /** The mode's plain name; an id this app does not know is shown as it came. */
    fun modeName(id: String?): String = mode(id)?.name ?: (id ?: "")

    /** The words for [key] with `{name}` placeholders filled in. An unknown key is "". */
    fun w(key: String, vararg fill: Pair<String, Any>): String {
        var s = WORDS[key] ?: return ""
        for ((k, v) in fill) s = s.replace("{$k}", v.toString())
        return s
    }

    /** Said when the PC named no code this app knows and sent no sentence. */
    const val ERROR_FALLBACK = "Your PC did not make that change."

    /**
     * The sentence for a failed write: the PC's own [message] first (it wrote
     * it for the owner), then the fixture's sentence for the [code], then the
     * card sentence for the two card failures, then [ERROR_FALLBACK].
     */
    fun errorSentence(code: String?, message: String? = null): String {
        message?.trim()?.takeIf { it.isNotEmpty() }?.let { return it }
        if (code != null) {
            ERRORS[code]?.let { return it }
            if (code == "gate_not_ask" || code == "no_card") return GATE_FAILED
        }
        return ERROR_FALLBACK
    }

    // ------------------------------------------------ this app's words ---
    // Not in the shared fixture: wording only the phone's screens need.

    const val CHANGE = "Change"
    const val CANCEL = "Cancel"
    const val DONE = "Done"
    const val EDIT = "Edit"
    const val SAVE = "Save"
    const val RENAME = "Rename"
    const val COLOUR = "Colour"
    const val ICON = "Icon"
    const val MOVE_UP = "Move up"
    const val MOVE_DOWN = "Move down"
    const val MARK_PRIVATE = "Mark private"
    const val NOT_PRIVATE = "Not private"
    const val DELETE = "Delete this topic"
    const val DELETE_YES = "Yes, delete it"
    const val KEEP_IT = "Keep it"
    const val FILE_UNDER = "File under..."
    const val NEXT_BATCH = "Next batch"
    const val NOTHING_TO_CHECK = "Nothing to check."
    const val HIDDEN_FROM_ANSWERS = "Hidden from answers"
    const val NAME_PLACEHOLDER = "Topic name"
    const val READING = "Reading\u2026"
    /** Said when the PC answered something that is not a topics list. */
    const val READ_ODD = "Your PC sent an answer Jarvis could not read."
    const val NOT_HELD = "Not connected to the desktop, so changes wait until the link is back."

    /** Said when a write is refused because the memory lists are hidden (names and fact words are not on screen). */
    const val LISTS_HIDDEN_REFUSAL =
        "Your memory lists are hidden, so this waits. Show them first, then try again."

    /** What one raw answer came to: the status code and the JSON body, if any. */
    data class Reply(val code: Int, val body: JsonObject?)

    // ------------------------------------------------------------- data ---

    /** One topic (a row of the PC's `topics` table). */
    data class Topic(
        val id: Int,
        val name: String,
        val colour: Int,
        val icon: String,
        val mode: String,
        val isPrivate: Boolean,
        val ord: Int,
        val system: Boolean,
        val facts: Int,
        val unchecked: Int,
        val hidden: Boolean,
        val skippedWeek: Int,
    ) {
        val isOff: Boolean get() = mode == "off"
    }

    /** A card is up: the topic and what kind of change it is (`mode`, `private_clear`, `delete`, `file`). */
    data class Waiting(val topic: Int, val kind: String)

    /** How the most recent card ended. [message] is the PC's own sentence. */
    data class Last(val outcome: String, val why: String?, val at: Double, val message: String)

    /** `GET /api/topics`, and the body of every successful write. */
    data class View(
        val topics: List<Topic>,
        val unchecked: Int,
        val facts: Int,
        val sorted: Int,
        val modelHelp: Boolean,
        val sortingRemaining: Int,
        val waiting: Waiting?,
        val last: Last?,
        val maxTopics: Int,
        val nameMax: Int,
        val batch: Int,
        val icons: List<String>,
    ) {
        /** The owner's own topics in the PC's order (Unsorted is not one of them). */
        val own: List<Topic> get() = topics.filter { !it.system }

        fun byId(id: Int?): Topic? = topics.firstOrNull { it.id == id }

        /** The "Add a topic" button is off at [maxTopics] topics of the owner's own. */
        val canAdd: Boolean get() = own.size < maxTopics
    }

    private val JSON = Json { ignoreUnknownKeys = true; isLenient = true }

    private fun JsonObject.prim(key: String): JsonPrimitive? = (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull }

    private fun JsonObject.str(key: String): String? =
        prim(key)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.whole(key: String): Long? = prim(key)?.takeIf { !it.isString }?.longOrNull

    private fun JsonObject.flag(key: String): Boolean? = prim(key)?.takeIf { !it.isString }?.booleanOrNull

    private fun JsonObject.num(key: String): Double? =
        prim(key)?.takeIf { !it.isString }?.doubleOrNull?.takeIf { it.isFinite() }

    private fun JsonObject.count(key: String): Int = (whole(key) ?: 0L).coerceIn(0L, Int.MAX_VALUE.toLong()).toInt()

    /** One topic from the wire, or null without a usable id or name. Missing or extra fields are fine. */
    fun topic(o: JsonObject): Topic? {
        val id = o.whole("id")?.takeIf { it in 1..Int.MAX_VALUE }?.toInt() ?: return null
        val name = o.str("name") ?: return null
        val modeId = o.str("mode") ?: "both"
        return Topic(
            id = id,
            name = name,
            colour = o.whole("colour")?.toInt() ?: 6,
            icon = o.str("icon") ?: "folder",
            mode = modeId,
            isPrivate = o.flag("private") == true,
            ord = o.whole("ord")?.toInt() ?: 0,
            system = o.flag("system") == true || id == UNSORTED_ID,
            facts = o.count("facts"),
            unchecked = o.count("unchecked"),
            hidden = o.flag("hidden") ?: (modeId == "off"),
            skippedWeek = o.count("skipped_week"),
        )
    }

    /**
     * `GET /api/topics` (or a write's body), or null when it is not one (no
     * `topics` array, or `ok: false`). Unsorted first, then the owner's order;
     * a topic id twice is kept once.
     */
    fun view(body: JsonObject?): View? {
        if (body == null || body.flag("ok") == false) return null
        val arr = body["topics"] as? JsonArray ?: return null
        val seen = HashSet<Int>()
        val topics = arr.mapNotNull { (it as? JsonObject)?.let(::topic) }
            .filter { seen.add(it.id) }
            .sortedWith(compareBy<Topic>({ !it.system }, { it.ord }, { it.id }))
        val limits = body["limits"] as? JsonObject
        val waiting = (body["waiting"] as? JsonObject)?.let { w ->
            val t = w.whole("topic")?.toInt()
            if (t == null) null else Waiting(t, w.str("kind") ?: "mode")
        }
        val last = (body["last"] as? JsonObject)?.let { l ->
            val outcome = l.str("outcome") ?: return@let null
            Last(outcome, l.str("why"), l.num("at") ?: 0.0, l.str("message") ?: "")
        }
        return View(
            topics = topics,
            unchecked = body.count("unchecked"),
            facts = body.count("facts"),
            sorted = body.count("sorted"),
            modelHelp = body.flag("model_help") == true,
            sortingRemaining = (body["backfill"] as? JsonObject)?.count("remaining") ?: 0,
            waiting = waiting,
            last = last,
            maxTopics = limits?.whole("max_topics")?.toInt()?.takeIf { it > 0 } ?: MAX_TOPICS,
            nameMax = limits?.whole("name_max")?.toInt()?.takeIf { it > 0 } ?: NAME_MAX,
            batch = limits?.whole("batch")?.toInt()?.takeIf { it > 0 } ?: BATCH,
            icons = (limits?.get("icons") as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }
                ?.takeIf { it.isNotEmpty() } ?: ICONS,
        )
    }

    /** The chat-tag icons plus the three topics add (C2 `limits.icons`). */
    val ICONS: List<String> = listOf(
        "briefcase", "book", "home", "folder", "lightbulb", "star", "flag", "wrench", "leaf", "music",
        "heart", "coin", "people",
    )

    /** The eight colour slots are the chat tags' ([ChatTags]); a slot out of range is slate. */
    const val COLOURS = 8

    fun slot(colour: Int): Int = if (colour in 0 until COLOURS) colour else 6

    // ------------------------------------------------------ preview etc ---

    /** `GET /api/topics/preview`. [line] and [cardLine] are the PC's own words. */
    data class Preview(
        val affected: Int,
        val pinned: Int,
        val stopsLearning: Boolean,
        val loosens: Boolean,
        val needsCard: Boolean,
        val isPrivate: Boolean,
        val line: String,
        val cardLine: String,
    )

    fun preview(body: JsonObject?): Preview? {
        if (body == null || body.flag("ok") == false) return null
        if (body["line"] == null && body["affected"] == null) return null
        return Preview(
            affected = body.count("affected"),
            pinned = body.count("pinned"),
            stopsLearning = body.flag("stops_learning") == true,
            loosens = body.flag("loosens") == true,
            needsCard = body.flag("needs_card") == true,
            isPrivate = body.flag("private") == true,
            line = body.prim("line")?.takeIf { it.isString }?.contentOrNull?.trim().orEmpty(),
            cardLine = body.prim("card_line")?.takeIf { it.isString }?.contentOrNull?.trim().orEmpty(),
        )
    }

    /** The preview's first sentence built here (the PC sends it too): "12 things Jarvis knows about Work will be left out of answers." */
    fun previewLeftOut(name: String, n: Int): String = when {
        n <= 0 -> w("preview_none", "name" to name)
        n == 1 -> w("preview_left_out_one", "name" to name)
        else -> w("preview_left_out", "n" to n, "name" to name)
    }

    /**
     * [text] with the topic's real [name] swapped for [label]. The PC's preview
     * sentence names the topic; while the memory lists are hidden the picker
     * shows "Topic 1" instead (C5), never the owner's word.
     */
    fun maskName(text: String, name: String, label: String): String =
        if (name.isEmpty()) text else text.replace(name, label)

    fun previewPath(id: Int, modeId: String): String? =
        if (id < 1 || mode(modeId) == null) null else "$PREVIEW_PATH?id=$id&mode=$modeId"

    /** One fact in the review list or "Show them". A memory list: its words hide with the others. */
    data class ReviewFact(
        val id: Long,
        val text: String,
        val savedAt: Double?,
        val topic: Int,
        val alt: Int?,
        val how: String,
        val checked: Boolean,
        val heldBack: Boolean,
    ) {
        /** Jarvis's model guessed it (the "Jarvis guessed" tag). */
        val guessed: Boolean get() = how == "model"
    }

    private fun reviewFact(o: JsonObject): ReviewFact? {
        val id = o.whole("id")?.takeIf { it > 0 } ?: return null
        val text = o.prim("text")?.takeIf { it.isString }?.contentOrNull ?: return null
        return ReviewFact(
            id = id,
            text = text,
            savedAt = o.num("saved_at"),
            topic = o.whole("topic")?.toInt() ?: UNSORTED_ID,
            alt = o.whole("alt")?.toInt(),
            how = o.str("how") ?: "rule",
            checked = o.flag("checked") == true,
            heldBack = o.flag("held_back") == true,
        )
    }

    /** `GET /api/topics/review`: one batch, the total left, and the cursor for the next. */
    data class Review(val facts: List<ReviewFact>, val next: String?, val total: Int)

    fun review(body: JsonObject?): Review? {
        if (body == null || body.flag("ok") == false) return null
        val arr = body["facts"] as? JsonArray ?: return null
        val facts = arr.mapNotNull { (it as? JsonObject)?.let(::reviewFact) }
        return Review(facts, cursor(body["next"]), body.count("total"))
    }

    /** `GET /api/topics/hidden`: the facts of one topic ("Show them"). */
    data class Hidden(val id: Int, val mode: String, val facts: List<ReviewFact>, val next: String?)

    fun hidden(body: JsonObject?): Hidden? {
        if (body == null || body.flag("ok") == false) return null
        val arr = body["facts"] as? JsonArray ?: return null
        return Hidden(
            id = body.whole("id")?.toInt() ?: 0,
            mode = body.str("mode") ?: "off",
            facts = arr.mapNotNull { (it as? JsonObject)?.let(::reviewFact) },
            next = cursor(body["next"]),
        )
    }

    private fun cursor(e: Any?): String? = (e as? JsonPrimitive)?.takeIf { it !is JsonNull }?.contentOrNull
        ?.takeIf { it.isNotBlank() && it != "null" }

    private fun enc(s: String): String = URLEncoder.encode(s, "UTF-8")

    fun reviewPath(after: String? = null, limit: Int = BATCH): String =
        "$REVIEW_PATH?limit=${limit.coerceIn(1, 50)}" + (after?.let { "&after=" + enc(it) } ?: "")

    fun hiddenPath(id: Int, after: String? = null, limit: Int = 100): String =
        "$HIDDEN_PATH?id=$id&limit=${limit.coerceIn(1, 100)}" + (after?.let { "&after=" + enc(it) } ?: "")

    /**
     * Groups a batch by consecutive suggested topic (the PC orders it by
     * `topic` then `id`): the header id and its facts, in order.
     */
    fun groups(facts: List<ReviewFact>): List<Pair<Int, List<ReviewFact>>> {
        val out = ArrayList<Pair<Int, MutableList<ReviewFact>>>()
        for (f in facts) {
            val last = out.lastOrNull()
            if (last != null && last.first == f.topic) last.second.add(f) else out.add(f.topic to mutableListOf(f))
        }
        return out
    }

    // --------------------------------------------------------- outcomes ---

    /** What a write came to. */
    sealed interface Outcome {
        /** 200: the change is made. [view] is the new list when the body carried it; [id] the topic touched. */
        data class Done(val view: View?, val id: Int?, val filed: Int = 0, val confirmed: Int = 0) : Outcome

        /** 202: ONE card is up; nothing has changed yet. [message] is [WORDS] `waiting`. */
        data class Waiting(val id: Int?, val kind: String?, val message: String) : Outcome

        /** Anything else: [said] is one plain sentence. [missing] when the PC has no topic controls at all. */
        data class Failed(val said: String, val missing: Boolean = false) : Outcome
    }

    /**
     * The route is not on this PC (an older Jarvis, or `503 unavailable`): a
     * 404 that is not a topic/fact 404, a 501, or `unavailable`. Shown as
     * `words.missing`, with no rows (C3 "Not available").
     */
    fun isMissing(code: Int, body: JsonObject?): Boolean {
        val error = body?.str("error")
        if (error == "unavailable") return true
        if (code == 501) return true
        if (code == 404) return error != "topic_not_found" && error != "no_such_fact"
        return false
    }

    /**
     * A POST's answer as [code] and [body] came. 202 (or `waiting: true`) is
     * [Outcome.Waiting]; a 2xx with `ok` not false is [Outcome.Done]; else
     * the PC's `message` wins, then the fixture's sentence for the `error`.
     */
    fun outcome(code: Int, body: JsonObject?): Outcome {
        if (isMissing(code, body)) return Outcome.Failed(w("missing"), missing = true)
        val ok = body?.flag("ok")
        if (code == 202 || (code in 200..299 && body?.flag("waiting") == true && ok != false)) {
            return Outcome.Waiting(body?.whole("id")?.toInt(), body?.str("kind"), w("waiting"))
        }
        if (code in 200..299 && ok != false) {
            return Outcome.Done(
                view = view(body),
                id = body?.whole("id")?.toInt(),
                filed = body?.count("filed") ?: 0,
                confirmed = body?.count("confirmed") ?: 0,
            )
        }
        return Outcome.Failed(errorSentence(body?.str("error"), body?.str("message")))
    }

    // ------------------------------------------------------ card polling ---

    /** What the plate does after a 202, each time it reads `GET /api/topics`. */
    sealed interface Poll {
        /** The card is still up (or the read failed): show `words.waiting` and read again in [POLL_MS]. */
        data object Waiting : Poll

        /** No card any more. [message] is `last.message` (the PC's sentence) when there is one for THIS card. */
        data class Done(val message: String?) : Poll
    }

    /** The PC's sentence for how a card ended; the fixture's `last_words` when it sent none. */
    fun lastMessage(last: Last): String = last.message.ifBlank { LAST_WORDS[last.outcome].orEmpty() }

    /**
     * One step of the polling. [view] is the latest read (null when it
     * failed: keep waiting). [baseAt] is the `last.at` seen BEFORE the write,
     * so an ending older than this card is an earlier card's, not its answer.
     */
    fun pollStep(view: View?, baseAt: Double): Poll {
        if (view == null || view.waiting != null) return Poll.Waiting
        val last = view.last
        if (last == null || last.at <= baseAt) return Poll.Done(null)
        return Poll.Done(lastMessage(last).takeIf { it.isNotBlank() })
    }

    // -------------------------------------------------- rows and reading ---

    /** "41 facts" - the fixture's own wording (`{n} facts`). */
    fun factsText(n: Int): String = if (n == 1) "1 fact" else "$n facts"

    /** TalkBack's line for a row's mode button: "Work, 41 facts, Use, but don't learn, button: change mode". */
    fun screenReader(name: String, facts: Int, modeId: String): String =
        if (facts == 1) w("screen_reader_one", "name" to name, "mode" to modeName(modeId))
        else w("screen_reader", "name" to name, "n" to facts, "mode" to modeName(modeId))

    /** The row while the memory lists are hidden: "Topic 1, 41 facts, Use, but don't learn". */
    fun hiddenRow(index: Int, facts: Int, modeId: String): String =
        if (facts == 1) w("hidden_row_one", "index" to index, "mode" to modeName(modeId))
        else w("hidden_row", "index" to index, "n" to facts, "mode" to modeName(modeId))

    /** A topic's 1-based position among the owner's own topics (Unsorted is none); 0 for an unknown id. */
    fun ownerIndex(view: View, id: Int): Int = view.own.indexOfFirst { it.id == id } + 1

    /** The name to show: the topic's own, or "Topic N" while the lists are hidden (Unsorted keeps its name). */
    fun shownName(view: View, topic: Topic, listsHidden: Boolean): String = when {
        topic.system -> w("unsorted_name")
        !listsHidden -> topic.name
        else -> "Topic " + ownerIndex(view, topic.id)
    }

    /** The lines a row adds under its name, in order (C3). Empty while the lists are hidden. */
    fun rowNotes(topic: Topic, listsHidden: Boolean): List<String> {
        if (listsHidden) return emptyList()
        val out = ArrayList<String>()
        if (topic.isPrivate) out.add(w("private_tag"))
        if (topic.mode == "learn_only") out.add(w("not_used_tag"))
        if (topic.isOff || topic.hidden) out.add(keptHiddenLine(topic.facts))
        if (topic.skippedWeek == 1) out.add(w("skipped_one"))
        else if (topic.skippedWeek > 1) out.add(w("skipped", "n" to topic.skippedWeek))
        return out
    }

    /** The line above the rows while the PC is still labelling old facts, or null. */
    fun sortingLine(view: View): String? =
        if (view.sortingRemaining > 0) w("sorting_now", "n" to view.sortingRemaining) else null

    /** "Jarvis sorted N of your M facts by guessing..." and the button, or null when nothing needs checking. */
    fun guessLine(view: View): String? =
        when {
            view.unchecked == 1 -> w("sorted_guess_one")
            view.unchecked > 1 -> w("sorted_guess", "n" to view.unchecked, "total" to view.facts)
            else -> null
        }

    /** "3 facts kept, hidden" / "1 fact kept, hidden". */
    fun keptHiddenLine(n: Int): String =
        if (n == 1) w("kept_hidden_one") else w("kept_hidden", "n" to n)

    fun checkButton(view: View): String? =
        if (view.unchecked > 0) w("check_button", "n" to view.unchecked) else null

    /** "Held back: might be about Work" for a review fact. */
    fun heldLine(name: String): String = w("check_held", "name" to name)

    /** "Left out 2 facts because of your topic settings" under an answer, or null when none. */
    fun leftOutLine(n: Int): String? = when {
        n <= 0 -> null
        n == 1 -> w("left_out_one")
        else -> w("left_out", "n" to n)
    }

    /** "Paused: Work is off" on a pin the PC marked `paused`. */
    fun pinPausedLine(name: String, modeId: String? = null): String =
        w(if (modeId == "learn_only") "pin_paused_learn" else "pin_paused", "name" to name)

    /** Said on a paused pin when the phone cannot tell which topic it is (several are not used, or none could be read). */
    const val PIN_PAUSED_GENERIC = "Paused: its topic is not used in answers"

    /**
     * The line on a pin the PC marked `paused`. The PC sends the pin's `topic` id, so the
     * name (and whether it is Off or "Learn, but don't use") comes from that topic. An older
     * PC sends no id: then the name is used only when exactly ONE topic is not used in
     * answers; otherwise [PIN_PAUSED_GENERIC].
     */
    fun pinPausedFor(view: View?, topicId: Int? = null): String {
        val named = topicId?.let { view?.byId(it) }
        if (named != null) return pinPausedLine(named.name, named.mode)
        val blocked = view?.topics.orEmpty().filter { t -> mode(t.mode)?.uses == false }
        return if (blocked.size == 1) pinPausedLine(blocked.single().name, blocked.single().mode) else PIN_PAUSED_GENERIC
    }

    /** The tag on a fact whose topic is "Learn, but don't use" (looked up by its `topic` id), else null. */
    fun notUsedTag(topicId: Int?, view: View?): String? =
        if (topicId != null && view?.byId(topicId)?.mode == "learn_only") w("not_used_tag") else null

    /** `words.ask_save` / `words.ask_skip` for a pending row with `topic_ask: true`, else null. */
    fun askLabels(row: JsonObject): Pair<String, String>? =
        if (row.flag("topic_ask") == true) w("ask_save") to w("ask_skip") else null

    // -------------------------------------------------- mode arithmetic ---

    /**
     * Whether [new] lets Jarvis do more than [old] - learn or use something it
     * did not. Used only for the LABELS (the delete destination's warning and
     * "This will ask for your OK first."); the PC decides what really asks.
     */
    fun loosens(old: String, new: String): Boolean {
        val a = mode(old) ?: return false
        val b = mode(new) ?: return false
        return (b.learns && !a.learns) || (b.uses && !a.uses)
    }

    /** The label only: a loosening of a private topic (the PC's `needs_card` decides for real). */
    fun needsCard(old: String, new: String, isPrivate: Boolean): Boolean = isPrivate && loosens(old, new)

    /** `words.delete_looser` for a delete whose home is more open than the topic going, else null. */
    fun deleteLooser(deleted: Topic, home: Topic): String? =
        if (loosens(deleted.mode, home.mode)) w("delete_looser", "name" to deleted.name) else null

    /**
     * Where a deleted topic's facts may go: every OTHER topic, Unsorted included, in list order.
     */
    fun homes(view: View, deleting: Int): List<Topic> = view.topics.filter { it.id != deleting }

    // ---------------------------------------------------------- requests ---

    /** Blank fillers that take room but show nothing. */
    private val WHITESPACE = Regex("\\s+")

    fun nameLength(s: String): Int = s.codePointCount(0, s.length)

    /**
     * [raw] cut to [max] code points (never inside a surrogate pair) - for the
     * text box, so a 25th character is not typed in.
     */
    fun clipName(raw: String, max: Int = NAME_MAX): String {
        if (nameLength(raw) <= max) return raw
        return raw.substring(0, raw.offsetByCodePoints(0, max))
    }

    /**
     * A name the PC would take, or null and nothing is sent: runs of white
     * space become one space, trimmed, 1-[max] code points (the fixture's
     * `name_cases`). "Unsorted" is allowed here; the PC answers `name_taken`.
     */
    fun cleanName(raw: String, max: Int = NAME_MAX): String? {
        val n = WHITESPACE.replace(raw, " ").trim()
        return n.takeIf { nameLength(it) in 1..max }
    }

    fun addBody(rawName: String, colour: Int? = null, icon: String? = null, makePrivate: Boolean = false): String? {
        val n = cleanName(rawName) ?: return null
        return buildJsonObject {
            put("op", "add")
            put("name", n)
            if (colour != null && colour in 0 until COLOURS) put("colour", colour)
            if (icon != null && icon in ICONS) put("icon", icon)
            if (makePrivate) put("private", true)
        }.toString()
    }

    fun renameBody(id: Int, rawName: String): String? {
        if (id == UNSORTED_ID) return null
        val n = cleanName(rawName) ?: return null
        return buildJsonObject {
            put("op", "rename")
            put("id", id)
            put("name", n)
        }.toString()
    }

    fun styleBody(id: Int, colour: Int? = null, icon: String? = null): String? {
        if (colour == null && icon == null) return null
        if (colour != null && colour !in 0 until COLOURS) return null
        if (icon != null && icon !in ICONS) return null
        return buildJsonObject {
            put("op", "style")
            put("id", id)
            if (colour != null) put("colour", colour)
            if (icon != null) put("icon", icon)
        }.toString()
    }

    /** `before` null moves the topic to the end. */
    fun moveBody(id: Int, before: Int?): String = buildJsonObject {
        put("op", "move")
        put("id", id)
        if (before == null) put("before", JsonNull) else put("before", before)
    }.toString()

    /** "Move up": before the owner's topic above it; null when it is already first (or is Unsorted). */
    fun moveUpBody(view: View, id: Int): String? {
        val own = view.own
        val i = own.indexOfFirst { it.id == id }
        return if (i <= 0) null else moveBody(id, own[i - 1].id)
    }

    /** "Move down": before the topic two below it, or last; null when already last. */
    fun moveDownBody(view: View, id: Int): String? {
        val own = view.own
        val i = own.indexOfFirst { it.id == id }
        if (i < 0 || i >= own.lastIndex) return null
        return moveBody(id, own.getOrNull(i + 2)?.id)
    }

    /** Mark private is at once; Not private raises ONE card (a 202). */
    fun privateBody(id: Int, makePrivate: Boolean): String? = if (id == UNSORTED_ID) null else buildJsonObject {
        put("op", "private")
        put("id", id)
        put("private", makePrivate)
    }.toString()

    /** A delete needs a home for its facts (`move_to`); none, or itself, or Unsorted as the topic, sends nothing. */
    fun deleteBody(id: Int, moveTo: Int?): String? {
        if (id == UNSORTED_ID || moveTo == null || moveTo == id || moveTo < 1) return null
        return buildJsonObject {
            put("op", "delete")
            put("id", id)
            put("move_to", moveTo)
        }.toString()
    }

    /** `POST /api/topics/mode`: one topic, one of the four modes; anything else sends nothing. */
    fun modeBody(id: Int, modeId: String): String? = if (id < 1 || mode(modeId) == null) null else buildJsonObject {
        put("id", id)
        put("mode", modeId)
    }.toString()

    private fun idsArray(ids: List<Long>): JsonArray = JsonArray(ids.map { JsonPrimitive(it) })

    private fun okIds(ids: List<Long>): List<Long>? =
        ids.filter { it > 0 }.distinct().takeIf { it.isNotEmpty() && it.size <= FILE_MAX }

    /** "File under...": these facts, that topic. 1..200 ids. */
    fun fileBody(ids: List<Long>, topicId: Int): String? {
        val list = okIds(ids) ?: return null
        if (topicId < 1) return null
        return buildJsonObject {
            put("ids", idsArray(list))
            put("topic_id", topicId)
        }.toString()
    }

    /** "These are right": the batch shown, confirmed as it is filed. */
    fun confirmBody(ids: List<Long>): String? {
        val list = okIds(ids) ?: return null
        return buildJsonObject {
            put("ids", idsArray(list))
            put("confirm", true)
        }.toString()
    }

    fun settingsBody(modelHelp: Boolean): String = buildJsonObject { put("model_help", modelHelp) }.toString()

    /**
     * Whether a request body writes something the phone must refuse while the
     * memory lists are hidden (C5, the runtime's second half): everything
     * except a mode change and the model switch - names and fact words are
     * not on screen then, so nothing that needs them is sent.
     */
    fun refusedWhileHidden(path: String): Boolean = path != MODE_PATH && path != SETTINGS_PATH

    // ------------------------------------------------- the chat's route ---

    /** "switch off my work topic" (ambiguous): open Brain -> Memory -> Topics, and that topic's picker when [topicId] is set. */
    data class Open(val topicId: Int?)

    private fun route(header: String?): JsonObject? {
        if (header.isNullOrBlank()) return null
        return runCatching { JSON.parseToJsonElement(header.trim()) as? JsonObject }.getOrNull()
    }

    /** The answer's `X-Jarvis-Route` `open_brain: "topics"` (and `topic_id`), else null. Pure navigation - nothing changes. */
    fun openFromRoute(header: String?): Open? {
        val o = route(header) ?: return null
        if (o.str("open_brain") != PLACE) return null
        return Open(o.whole("topic_id")?.toInt()?.takeIf { it > 0 })
    }

    /** `topics_left_out` from the route header: a count, 0 when absent or odd. */
    fun leftOutFromRoute(header: String?): Int = route(header)?.count("topics_left_out") ?: 0

    /** A `GET /api/memory/used` fact with `left_out: true` reads [WORDS] `used_left_out`, never words. */
    fun usedLeftOutLine(): String = w("used_left_out")
}
