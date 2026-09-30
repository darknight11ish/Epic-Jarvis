package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.put

/**
 * "My study decks": questions kept from a finished quiz, asked again on a
 * spaced schedule the PC works out (docs/QUIZ-DECKS-DESIGN.md, "Slice contract
 * (frozen)", C1-C6; docs/JARVIS-API.md section 102; backend `jarvis_decks.py`).
 *
 * The PC keeps every deck, sealed. THIS PHONE KEEPS NOTHING: no card text in a
 * file, a preference or a database - what is on screen is held in memory by
 * the screen and [com.jarvis.client.JarvisRuntime] only, and gone with the
 * process. No approval card exists in this slice: the owner's own tap is the
 * yes, and the Keep sheet lists every card word for word first.
 *
 * The owner rates every card. There is no streak, no score, no count of days
 * and no colour that goes red for "late" (C1): a card left for a month is
 * simply ready. A test scans this file's strings for the banned words.
 *
 * Typed only. Everything here is pure (no Android, no network), so DecksTest.kt
 * can run it.
 */
object Decks {
    // ---- The shared words (contract C5), word for word. ----
    const val TITLE = "My study decks"
    const val READY_HEADING = "Cards ready"
    const val NOTHING_READY = "Nothing ready today"
    const val NEW_PER_DAY = "New cards a day"
    const val REVIEW = "Review"
    const val PAUSE = "Pause"
    const val RESUME = "Resume"
    const val DELETE_DECK = "Delete this deck"
    const val DELETE_CARD = "Delete this card"
    const val EDIT = "Edit"
    const val SAVE = "Save"
    const val CARDS = "Cards"
    const val DELETE = "Delete"
    const val CANCEL = "Cancel"
    const val CONFIRM_DELETE = "Are you sure? Deleting is immediate. Copies in older backups stay until they age out."
    const val EMPTY = "Keep questions from a quiz to make your first deck."
    const val HIDDEN_REVIEW = "Turn off Hide memory lists to review"
    const val NEW_DECK = "New deck"
    const val DECK_NAME = "Deck name"
    const val CHOOSE_DECK = "Choose a deck"

    const val SHOW_ANSWER = "Show answer"
    const val TYPE_HINT = "Type your answer (only for you - it is not sent or marked)"
    const val ENOUGH = "That's enough for now"
    const val DO_10_MORE = "Do 10 more"
    const val STOP = "Stop"
    const val ANSWER_HEADING = "Answer"
    const val FROM_TEXT = "From the text"
    const val EXAMPLE_SENTENCE = "Example sentence"

    // ---- This phone's own words. ----
    const val HIDDEN_TEXT = "(hidden)"
    const val READING = "Reading…"
    const val REFRESH = "Refresh"
    const val FRONT_HINT = "Question"
    const val BACK_HINT = "Answer"
    const val PAUSED_TAG = "Paused"
    const val NO_CARDS = "No cards in this deck yet."
    const val CARDS_HIDDEN = "Turn off Hide memory lists to see the cards"
    const val FEWER = "−"
    const val MORE = "+"
    const val FEWER_WORDS = "Fewer new cards a day"
    const val MORE_WORDS = "More new cards a day"
    const val BACK_TO_DECKS = "Back to my decks"
    const val LOADING_CARD = "Getting the next card…"
    const val MISSING = "Your PC's Jarvis does not have study decks yet - run apply-patches.ps1 on the PC."
    const val UNREADABLE = "Your PC sent something this phone could not read."

    const val MAX_NEW_PER_DAY = 20
    const val DEFAULT_MAX_NAME = 60
    const val DEFAULT_MAX_FRONT = 500
    const val DEFAULT_MAX_BACK = 2000

    // Error codes (C4).
    const val E_NOT_FOUND = "deck_not_found"
    const val E_CARD_NOT_FOUND = "card_not_found"
    const val E_UNAVAILABLE = "deck_unavailable"
    const val E_BAD_NAME = "bad_deck_name"
    const val E_TOO_MANY = "too_many_decks"
    const val E_NOT_REVEALED = "not_revealed"
    const val E_PAUSED = "deck_paused"
    const val E_BAD_RATING = "bad_rating"
    const val E_BAD_CARD = "bad_card"
    const val E_BAD_SETTING = "bad_setting"
    const val E_BAD_ACTION = "bad_action"

    /** The four ratings, in the contract's order: the wire id and the owner's words (C5). */
    val RATINGS = listOf(
        "again" to "Didn't remember",
        "hard" to "Remembered, with effort",
        "good" to "Remembered",
        "easy" to "Easy",
    )

    private val ID = Regex("^[A-Za-z0-9_-]{1,64}$")

    /** Whether [id] is safe to put in a URL path. */
    fun validId(id: String?): Boolean = id != null && ID.matches(id)

    fun ratingWords(id: String): String = RATINGS.firstOrNull { it.first == id }?.second.orEmpty()
    fun validRating(id: String): Boolean = RATINGS.any { it.first == id }

    // ------------------------------------------------------------- models ----

    data class Limits(
        val decks: Int = 20,
        val cards: Int = 1000,
        val name: Int = DEFAULT_MAX_NAME,
        val front: Int = DEFAULT_MAX_FRONT,
        val back: Int = DEFAULT_MAX_BACK,
        val newPerDay: Int = MAX_NEW_PER_DAY,
    )

    data class Deck(
        val id: String,
        val name: String,
        val cards: Int,
        val ready: Int,
        val paused: Boolean,
        val kind: String,
    )

    data class DeckList(
        val available: Boolean,
        val why: String,
        val decks: List<Deck>,
        val ready: Int,
        val newPerDay: Int,
        val newLeft: Int,
        val nextReadyDay: String?,
        val line: String,
        val limits: Limits,
    )

    data class CardFull(
        val id: String,
        val front: String,
        val back: String,
        val passage: String,
        val kind: String,
        val level: String?,
        val keySource: String?,
        val keyLabel: String?,
        val isNew: Boolean,
        val dueDay: String?,
    )

    data class DeckCards(val deckId: String, val deckName: String, val cards: List<CardFull>)

    /** The card a review shows the front of. */
    data class CardView(
        val id: String,
        val front: String,
        val kind: String,
        val level: String?,
        val deck: String,
        val isNew: Boolean,
    )

    /**
     * A review's state (C4): [state] is `card`, `empty`, `enough`, `paused` or
     * `no_decks`; [card] is the card to show when it is `card`; [comesBack] is
     * the day the card just rated is asked again (a rate reply only).
     */
    data class Review(
        val ready: Int,
        val newLeft: Int,
        val state: String,
        val line: String,
        val card: CardView?,
        val done: Int,
        val limit: Int,
        val comesBack: String? = null,
    )

    /** A revealed back: the owner's answer words, the passage, and the label for a model-written key. */
    data class Reveal(val answer: String, val passage: String, val keyLabel: String?)

    /** What `act` on a deck answered: the deck, or that it was deleted. */
    data class Acted(val deck: Deck?, val deleted: Boolean)

    /** What the PC answered a call, kept whole: the status and the JSON body, if any. */
    data class Reply(val code: Int, val body: JsonObject?)

    /** One call's outcome. [code] is the PC's error code, when it sent one. */
    data class Outcome<out T>(val ok: Boolean, val value: T?, val said: String, val code: String? = null)

    /** An outcome for a call that was never made (a stale link, a bad id, a bad box). */
    fun <T> blocked(said: String): Outcome<T> = Outcome(false, null, said)

    // ------------------------------------------------------------ parsing ----

    fun parseDeck(el: Any?): Deck? {
        val o = el as? JsonObject ?: return null
        val id = o.text("id")?.takeIf { validId(it) } ?: return null
        return Deck(
            id = id,
            name = o.text("name").orEmpty(),
            cards = o.num("cards")?.toInt()?.coerceAtLeast(0) ?: 0,
            ready = o.num("ready")?.toInt()?.coerceAtLeast(0) ?: 0,
            paused = o.flag("paused") == true,
            kind = o.text("kind").orEmpty(),
        )
    }

    private fun limits(el: Any?): Limits {
        val o = el as? JsonObject ?: return Limits()
        val d = Limits()
        return Limits(
            decks = o.num("decks")?.toInt()?.takeIf { it > 0 } ?: d.decks,
            cards = o.num("cards")?.toInt()?.takeIf { it > 0 } ?: d.cards,
            name = o.num("name")?.toInt()?.takeIf { it > 0 } ?: d.name,
            front = o.num("front")?.toInt()?.takeIf { it > 0 } ?: d.front,
            back = o.num("back")?.toInt()?.takeIf { it > 0 } ?: d.back,
            newPerDay = o.num("new_per_day")?.toInt()?.takeIf { it in 0..MAX_NEW_PER_DAY } ?: d.newPerDay,
        )
    }

    /** `GET /api/decks`. Null when the body is not a deck list at all (no "decks" array and no "available"). */
    fun parseList(body: JsonObject): DeckList? {
        val list = body["decks"] as? JsonArray
        if (list == null && body["available"] == null) return null
        return DeckList(
            // Missing means "not available": nothing is offered on a guess.
            available = body.flag("available") == true,
            why = body.text("why").orEmpty(),
            decks = list?.mapNotNull { parseDeck(it) }.orEmpty(),
            ready = body.num("ready")?.toInt()?.coerceAtLeast(0) ?: 0,
            newPerDay = body.num("new_per_day")?.toInt()?.coerceIn(0, MAX_NEW_PER_DAY) ?: 5,
            newLeft = body.num("new_left")?.toInt()?.coerceAtLeast(0) ?: 0,
            nextReadyDay = body.text("next_ready_day"),
            line = body.text("line").orEmpty(),
            limits = limits(body["limits"]),
        )
    }

    fun parseCard(el: Any?): CardFull? {
        val o = el as? JsonObject ?: return null
        val id = o.text("id")?.takeIf { validId(it) } ?: return null
        return CardFull(
            id = id,
            front = o.text("front").orEmpty(),
            // A back may be empty (the card then shows the passage alone), so it is not trimmed away.
            back = (o["back"] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull.orEmpty(),
            passage = o.text("passage").orEmpty(),
            kind = o.text("kind").orEmpty(),
            level = o.text("level")?.takeIf { it in Quiz.LEVELS },
            keySource = o.text("key_source")?.takeIf { it == "text" || it == "model" },
            keyLabel = o.text("key_label"),
            isNew = o.flag("new") == true,
            dueDay = o.text("due_day"),
        )
    }

    /** `GET /api/decks/{id}/cards`. */
    fun parseCards(body: JsonObject): DeckCards? {
        val d = body["deck"] as? JsonObject ?: return null
        val id = d.text("id")?.takeIf { validId(it) } ?: return null
        val list = body["cards"] as? JsonArray ?: return null
        return DeckCards(id, d.text("name").orEmpty(), list.mapNotNull { parseCard(it) })
    }

    private fun cardView(el: Any?): CardView? {
        val o = el as? JsonObject ?: return null
        val id = o.text("id")?.takeIf { validId(it) } ?: return null
        val front = o.text("front") ?: return null
        return CardView(
            id = id,
            front = front,
            kind = o.text("kind").orEmpty(),
            level = o.text("level")?.takeIf { it in Quiz.LEVELS },
            deck = o.text("deck").orEmpty(),
            isNew = o.flag("new") == true,
        )
    }

    /**
     * A review reply: `GET /api/review` and `POST /api/review/more` carry the
     * card as "card"; `POST /api/review/rate` carries it as "next" ([cardKey]).
     * A missing state is read from the card: one there means `card`, none means `empty`.
     */
    fun parseReview(body: JsonObject, cardKey: String = "card"): Review? {
        val card = cardView(body[cardKey])
        val state = body.text("state") ?: if (card != null) "card" else if (body["ready"] != null) "empty" else return null
        val run = body["run"] as? JsonObject
        return Review(
            ready = body.num("ready")?.toInt()?.coerceAtLeast(0) ?: 0,
            newLeft = body.num("new_left")?.toInt()?.coerceAtLeast(0) ?: 0,
            state = state,
            line = body.text("line").orEmpty(),
            // A card is shown only in the state that says to.
            card = if (state == "card") card else null,
            done = run?.num("done")?.toInt()?.coerceAtLeast(0) ?: 0,
            limit = run?.num("limit")?.toInt()?.coerceAtLeast(0) ?: 0,
            comesBack = body.text("comes_back"),
        )
    }

    /** `POST /api/review/reveal`. */
    fun parseReveal(body: JsonObject): Reveal? {
        val b = body["back"] as? JsonObject ?: return null
        val answer = (b["answer"] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull.orEmpty()
        return Reveal(answer, b.text("passage").orEmpty(), body.text("key_label"))
    }

    // ------------------------------------------------------------- bodies ----

    fun validName(name: String, max: Int = DEFAULT_MAX_NAME): Boolean = name.trim().length in 1..max
    fun validFront(front: String, max: Int = DEFAULT_MAX_FRONT): Boolean = front.trim().length in 1..max
    fun validBack(back: String, max: Int = DEFAULT_MAX_BACK): Boolean = back.length <= max
    fun validPerDay(n: Int): Boolean = n in 0..MAX_NEW_PER_DAY

    fun createBody(name: String): String = buildJsonObject { put("name", name.trim()) }.toString()
    fun settingsBody(perDay: Int): String = buildJsonObject { put("new_per_day", perDay) }.toString()

    /** `pause`, `resume` or `delete` on a deck. */
    fun deckActBody(op: String): String? =
        if (op == "pause" || op == "resume" || op == "delete") buildJsonObject { put("do", op) }.toString() else null

    fun renameBody(name: String): String = buildJsonObject {
        put("do", "rename")
        put("name", name.trim())
    }.toString()

    /** Edit a card: at least one of [front] and [back] (C4). */
    fun cardEditBody(front: String?, back: String?): String? {
        if (front == null && back == null) return null
        return buildJsonObject {
            put("do", "edit")
            if (front != null) put("front", front.trim())
            if (back != null) put("back", back)
        }.toString()
    }

    const val CARD_DELETE_BODY = "{\"do\":\"delete\"}"

    fun revealBody(card: String): String = buildJsonObject { put("card", card) }.toString()

    fun rateBody(card: String, rating: String): String? =
        if (validRating(rating)) buildJsonObject {
            put("card", card)
            put("rating", rating)
        }.toString() else null

    /** `POST /api/review/more`: `{}` for every deck, or one deck. */
    fun moreBody(deck: String?): String =
        if (deck == null) "{}" else buildJsonObject { put("deck", deck) }.toString()

    // -------------------------------------------------------------- paths ----
    // Written out in full, with the id as a `$` placeholder, so the parity tool
    // (tools/check_parity.py) recognises each route.

    fun deckActPath(id: String): String? = if (validId(id)) "/api/decks/$id/act" else null
    fun cardsPath(id: String): String? = if (validId(id)) "/api/decks/$id/cards" else null
    fun cardActPath(id: String, cid: String): String? =
        if (validId(id) && validId(cid)) "/api/decks/$id/cards/$cid/act" else null

    /** `GET /api/review`, for one deck when [deck] is given. */
    fun reviewPath(deck: String?): String? = when {
        deck == null -> "/api/review"
        validId(deck) -> "/api/review?deck=$deck"
        else -> null
    }

    // ------------------------------------------------------------ messages ----

    /** The error code in a refusal body, if it has one. */
    fun errorCode(reply: Reply): String? = reply.body?.text("error")

    /** A read that failed because this PC has no decks: a 404 without a code, or a 501. */
    fun missing(reply: Reply): Boolean =
        reply.code == 501 || (reply.code == 404 && errorCode(reply) == null)

    /** Plain words for each contract error code, used only when the PC sent no message of its own. */
    fun messageFor(code: String?): String? = when (code) {
        E_NOT_FOUND -> "That deck is not there any more."
        E_CARD_NOT_FOUND -> "That card is not there any more."
        E_UNAVAILABLE -> "Study decks are not set up on your PC."
        E_BAD_NAME -> "Give the deck a name of 1 to $DEFAULT_MAX_NAME characters."
        E_TOO_MANY -> "There are already 20 decks. Delete one first."
        E_NOT_REVEALED -> "Show the answer first, then choose how it went."
        E_PAUSED -> "That deck is paused. Resume it to review."
        E_BAD_RATING -> "Choose one of the four buttons."
        E_BAD_CARD -> "A question needs 1 to $DEFAULT_MAX_FRONT characters and an answer up to $DEFAULT_MAX_BACK."
        E_BAD_SETTING -> "New cards a day is a whole number from 0 to $MAX_NEW_PER_DAY."
        E_BAD_ACTION -> "That change is not one this PC knows."
        else -> null
    }

    /**
     * The sentence for a refused or failed call. The PC's own `message` is shown
     * word for word (contract C1/C4); [messageFor] only when it sent none.
     */
    fun refusalSaid(reply: Reply, lead: String): String {
        reply.body?.text("message")?.let { return it.replaceFirstChar { c -> c.uppercase() } }
        messageFor(errorCode(reply))?.let { return it }
        return when {
            missing(reply) -> MISSING
            reply.code == 503 -> "$lead Your PC's Jarvis cannot do this right now."
            else -> "$lead Your PC answered ${reply.code}."
        }
    }

    fun succeeded(reply: Reply): Boolean =
        reply.code in 200..299 && reply.body?.flag("ok") != false

    private fun <T> failed(reply: Reply, lead: String): Outcome<T> =
        Outcome(false, null, refusalSaid(reply, lead), code = errorCode(reply))

    private fun <T> unreadable(lead: String): Outcome<T> = Outcome(false, null, "$lead $UNREADABLE")

    /** `GET /api/decks`. */
    fun listSaid(reply: Reply): Outcome<DeckList> {
        if (succeeded(reply)) {
            val v = reply.body?.let(::parseList)
            return if (v != null) Outcome(true, v, "") else unreadable("Not read.")
        }
        return failed(reply, "Not read.")
    }

    /** A new deck, or any deck change that answers a deck. */
    fun deckSaid(reply: Reply, lead: String): Outcome<Deck> {
        if (succeeded(reply)) {
            val d = parseDeck(reply.body?.get("deck"))
            return if (d != null) Outcome(true, d, "") else unreadable(lead)
        }
        return failed(reply, lead)
    }

    /** `POST /api/decks/{id}/act`: a deck, or "deleted". */
    fun actedSaid(reply: Reply, lead: String): Outcome<Acted> {
        if (succeeded(reply)) {
            if (reply.body?.flag("deleted") == true) return Outcome(true, Acted(null, true), "")
            val d = parseDeck(reply.body?.get("deck"))
            return if (d != null) Outcome(true, Acted(d, false), "") else unreadable(lead)
        }
        return failed(reply, lead)
    }

    /** `POST /api/decks/settings`: the number the PC now holds. */
    fun perDaySaid(reply: Reply): Outcome<Int> {
        if (succeeded(reply)) {
            val n = reply.body?.num("new_per_day")?.toInt()?.takeIf { validPerDay(it) }
            return if (n != null) Outcome(true, n, "") else unreadable("Not changed.")
        }
        return failed(reply, "Not changed.")
    }

    /** `GET /api/decks/{id}/cards`. */
    fun cardsSaid(reply: Reply): Outcome<DeckCards> {
        if (succeeded(reply)) {
            val v = reply.body?.let(::parseCards)
            return if (v != null) Outcome(true, v, "") else unreadable("Not read.")
        }
        return failed(reply, "Not read.")
    }

    /** A card edit answers the card. */
    fun cardSaid(reply: Reply, lead: String): Outcome<CardFull> {
        if (succeeded(reply)) {
            val c = parseCard(reply.body?.get("card"))
            return if (c != null) Outcome(true, c, "") else unreadable(lead)
        }
        return failed(reply, lead)
    }

    /** A card delete: only "ok" matters. */
    fun deletedSaid(reply: Reply, lead: String): Outcome<Unit> {
        if (succeeded(reply)) return Outcome(true, Unit, "")
        return failed(reply, lead)
    }

    /** `GET /api/review` and `POST /api/review/more`. */
    fun reviewSaid(reply: Reply): Outcome<Review> {
        if (succeeded(reply)) {
            val v = reply.body?.let { parseReview(it) }
            return if (v != null) Outcome(true, v, "") else unreadable("Not read.")
        }
        return failed(reply, "Not read.")
    }

    /** `POST /api/review/rate`: the next card sits under "next". */
    fun ratedSaid(reply: Reply): Outcome<Review> {
        if (succeeded(reply)) {
            val v = reply.body?.let { parseReview(it, "next") }
            return if (v != null) Outcome(true, v, "") else unreadable("Not saved.")
        }
        return failed(reply, "Not saved.")
    }

    /** `POST /api/review/reveal`. */
    fun revealSaid(reply: Reply): Outcome<Reveal> {
        if (succeeded(reply)) {
            val v = reply.body?.let(::parseReveal)
            return if (v != null) Outcome(true, v, "") else unreadable("Not shown.")
        }
        return failed(reply, "Not shown.")
    }

    // ------------------------------------------------------------- display ----

    /** "8 cards" / "1 card". */
    fun cardsWords(n: Int): String = if (n == 1) "1 card" else "$n cards"

    /** "3 ready". */
    fun readyWords(n: Int): String = "$n ready"

    /** The deck row's counts: "8 cards · 3 ready". */
    fun countsLine(d: Deck): String = "${cardsWords(d.cards)} · ${readyWords(d.ready)}"

    private val MONTHS = listOf("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

    /** "2026-10-03" -> "3 Oct 2026" for display only; anything else comes back as it was. */
    fun dayLabel(day: String?): String {
        if (day == null) return ""
        val m = Regex("^(\\d{4})-(\\d{2})-(\\d{2})$").matchEntire(day) ?: return day
        val month = m.groupValues[2].toInt()
        if (month !in 1..12) return day
        return "${m.groupValues[3].toInt()} ${MONTHS[month - 1]} ${m.groupValues[1]}"
    }

    /** "Next cards ready on 3 Oct 2026", or "" when the PC gave no day. */
    fun nextReadyLine(day: String?): String =
        if (day.isNullOrEmpty()) "" else "Next cards ready on ${dayLabel(day)}"

    /** "Comes back on 3 Oct 2026", or "" when the PC gave no day. */
    fun comesBackLine(day: String?): String =
        if (day.isNullOrEmpty()) "" else "Comes back on ${dayLabel(day)}"

    /** The heading over a revealed passage: the model's own sentence is said to be one. */
    fun passageHeading(keyLabel: String?): String = if (keyLabel != null) EXAMPLE_SENTENCE else FROM_TEXT

    /** The label under a card's level, "Level B1 (roughly)", or "" when it has none. */
    fun levelLine(level: String?): String = if (level == null) "" else Quiz.levelLine(level)

    /** The deck rows and card words with every owner-written word replaced; counts and `line` stay (C1). */
    fun hide(v: DeckList): DeckList = v.copy(decks = v.decks.map { it.copy(name = HIDDEN_TEXT) })

    fun hide(c: DeckCards): DeckCards = c.copy(
        deckName = HIDDEN_TEXT,
        cards = c.cards.map { it.copy(front = HIDDEN_TEXT, back = "", passage = "") },
    )

    /** The row's own words for a screen reader: "Plants, 8 cards, 3 ready, paused". */
    fun spokenRow(d: Deck, shownName: String): String =
        listOf(shownName, cardsWords(d.cards), readyWords(d.ready), if (d.paused) PAUSED_TAG.lowercase() else "")
            .filter { it.isNotEmpty() }.joinToString(", ")

    // ------------------------------------------------------------- helpers ----

    private fun JsonObject.num(key: String): Double? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.doubleOrNull
            ?.takeIf { it.isFinite() }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
