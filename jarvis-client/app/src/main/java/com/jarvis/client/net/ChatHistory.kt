package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * The conversation so far, which the phone sends along with each new question.
 *
 * WHY THIS EXISTS. The phone used to send only the newest question. Nothing
 * in this repository shows the desktop keeping a conversation of its own:
 * requests carry no conversation id, and every backend patch that touches
 * `/api/chat` works on the `messages` array the client sent. So every
 * follow-up ("and what about Tuesday?") reached the model with nothing before
 * it. The backend was written for clients that send the history - its
 * cloud-lane filter, the recalled-facts placement and the learner all talk
 * about the "client transcript" - and the desktop HUD page already sends one
 * (`jarvis_hud.html`, `S.messages.slice(-12)`).
 *
 * WHAT IS KEPT. Only pairs of (what the owner asked, what Jarvis answered),
 * as plain text, and only for answers that finished. No system messages, no
 * tool results, no approvals, no ids. A past answer that says "I have
 * proposed sending that email" is just words: nothing in `/api/chat` treats
 * text in the transcript as a decision. Approvals are made by id on
 * `/api/approve`, one at a time, and nowhere else.
 *
 * WHERE EACH QUESTION CAME FROM (added 2026-09-24, docs/JARVIS-API.md
 * section 18). Each user message carries a `provenance` tag ([Provenance]):
 * typed, pasted, voice, shared or picture_caption. The tag is KEPT with the
 * turn here and sent again with it on every later request - when this kept
 * plain strings, a tag would have fallen off one turn later. One "question"
 * can be two user messages: text shared from another app goes as its own
 * message, tagged "shared", right before the owner's typed one, so the two
 * are never mixed. Both are kept, in that order.
 *
 * WHICH CONVERSATION. Every request also carries a `conversation_id` the
 * phone makes up ([newConversationId]) - a new one when the app starts and
 * on "New conversation" - and `device: "phone"`. The PC uses them to keep
 * each chat as one conversation in its History. The PC strips all three
 * fields before anything reaches a model, local or cloud.
 *
 * WHERE IT LIVES. In memory, in [ChatSession], and nowhere else. Never written
 * to disk: a question can be about email, files or memory, and rule 1 keeps
 * those on this phone and the desktop. Gone when the app process is, or when
 * the owner taps "New conversation".
 *
 * CLOUD LANES. The earlier turns go to the desktop, not past it. If the
 * desktop ever sends a turn to a cloud model, `backend/cloud-one-turn.patch`
 * cuts the request down to the newest question alone first, so an earlier
 * private question cannot ride along on a later one that looked harmless.
 *
 * HOW MUCH. The model on the desktop has 16,384 tokens of room in total
 * (`backend/jarvis-primary.Modelfile`, `num_ctx 16384`). Set aside first:
 *
 *     2,048  the answer itself - generous: every window now gets 1,024
 *            (the Modelfile's `num_predict`; the HUD page used to ask 2,048)
 *       250  the Modelfile's SYSTEM prompt and the chat template
 *       400  the recalled-facts block (~100 at the default 5 facts, ~320 at
 *            16 - docs/MODEL-TOPOLOGY.md)
 *     2,600  the tool list, when tools are on (13 tools, 7,851 characters of
 *            JSON, measured from backend/jarvis_agent.py)
 *     3,000  the new question, including anything pasted into it
 *     -----
 *     8,298  leaving about 8,000 tokens
 *
 * History gets at most [MAX_CHARS] = 18,000 characters, which is 6,000 tokens
 * even at a pessimistic 3 characters per token (ordinary English is nearer 4,
 * so ~4,500), leaving ~2,000 tokens spare. And at most [MAX_EXCHANGES] = 10
 * question-and-answer pairs, whatever their size.
 *
 * WHY IT DROPS SEVERAL AT ONCE. The model keeps what it has already read
 * (Ollama's prompt cache) as long as the start of the prompt has not changed.
 * Dropping the single oldest pair on every turn would change the start every
 * turn, and the whole history would be re-read each time - about 3 seconds
 * for 6,000 tokens on this card (MODEL-TOPOLOGY.md). So when the history
 * outgrows either limit, the oldest pairs are dropped until it is back down to
 * [KEEP_EXCHANGES] pairs and [KEEP_CHARS] characters, and it then only grows
 * at the end again for several turns. A message is never cut in the middle:
 * a pair is kept whole or dropped whole.
 *
 * These are an UPPER bound. The model really loaded may have far less room
 * (4,096 tokens unless jarvis-primary is the one loaded - a model switched to
 * from this phone, say), so the desktop asks Ollama what it has and trims the
 * oldest turns to fit before sending (`backend/jarvis_agent.py`
 * `fit_messages`, `chat-stream.patch`). Only the desktop can know that number.
 *
 * The same numbers, and the same rule, are in the desktop quickbar's
 * `jarvis-desktop/src/chat-history.js`. Change one, change both.
 */
object ChatHistory {

    /** One user message as it was sent: its words, and where they came from ([Provenance]). */
    data class UserTurn(val text: String, val provenance: String)

    /**
     * One finished turn: what was asked - usually one message, two when text
     * shared from another app went with it - and the whole answer.
     */
    data class Exchange(val asked: List<UserTurn>, val answer: String) {
        /** A typed question and its answer - the common case, and the old shape. */
        constructor(question: String, answer: String, provenance: String = Provenance.TYPED) :
            this(listOf(UserTurn(question, provenance)), answer)

        /** The owner's own question: the last message of the turn. */
        val question: String get() = asked.lastOrNull()?.text.orEmpty()

        val chars: Int get() = asked.sumOf { it.text.length } + answer.length
    }

    const val MAX_EXCHANGES = 10
    const val MAX_CHARS = 18_000
    const val KEEP_EXCHANGES = 6
    const val KEEP_CHARS = 12_000

    /** What this app calls itself in `device`. Shown in the PC's History list; trusted for nothing. */
    const val DEVICE = "phone"

    private val CONVERSATION_ID = Regex("[A-Za-z0-9_-]{8,64}")

    /** Whether the PC will accept [id] as a `conversation_id` (8-64 of `A-Z a-z 0-9 _ -`). */
    fun validConversationId(id: String): Boolean = CONVERSATION_ID.matches(id)

    /** A new conversation's id: a random UUID - 36 characters, every one of them allowed. */
    fun newConversationId(): String = java.util.UUID.randomUUID().toString()

    /**
     * The user messages for one question, in the order they are sent:
     * [shared] text first, as its own message tagged "shared", then the
     * owner's [question] tagged [provenance]. With nothing typed and no
     * picture, the shared text goes alone.
     *
     * With a picture, only the owner's OWN words - typed or voice - become
     * "picture_caption". Pasted, clipboard or shared words sent with a
     * picture keep their less-trusted tag: the picture does not make them
     * the owner's. The PC does the same when it keeps the turn
     * (backend/jarvis_chat_log.py, `record_turn`), so both ends agree.
     */
    fun asking(
        question: String,
        provenance: String = Provenance.TYPED,
        shared: String? = null,
        picture: Boolean = false,
    ): List<UserTurn> = buildList {
        if (!shared.isNullOrBlank()) add(UserTurn(shared, Provenance.SHARED))
        if (question.isNotBlank() || picture || isEmpty()) {
            val own = provenance == Provenance.TYPED || provenance == Provenance.VOICE
            add(UserTurn(question, if (picture && own) Provenance.PICTURE_CAPTION else provenance))
        }
    }

    fun chars(window: List<Exchange>): Int = window.sumOf { it.chars }

    private fun fits(window: List<Exchange>, maxExchanges: Int, maxChars: Int): Boolean =
        window.size <= maxExchanges && chars(window) <= maxChars

    /** [commit] for one typed question. */
    fun commit(window: List<Exchange>, question: String, answer: String): List<Exchange> =
        commit(window, listOf(UserTurn(question, Provenance.TYPED)), answer)

    /**
     * [window] with one more finished turn on the end, trimmed if it has
     * grown past the limits. A blank message is not worth replaying, so it is
     * left out; with no words asked at all, or a blank answer, the window
     * comes back unchanged.
     *
     * When trimming, the newest pair is always the last to go: it is kept
     * alone if it is bigger than [KEEP_CHARS] but still inside [MAX_CHARS],
     * and dropped only when it is too big to send at all.
     */
    fun commit(window: List<Exchange>, asked: List<UserTurn>, answer: String): List<Exchange> {
        val kept = asked.filter { it.text.isNotBlank() }
        if (kept.isEmpty() || answer.isBlank()) return window
        val next = ArrayDeque(window)
        next.addLast(Exchange(kept, answer))
        if (fits(next, MAX_EXCHANGES, MAX_CHARS)) return next.toList()
        while (next.size > 1 && !fits(next, KEEP_EXCHANGES, KEEP_CHARS)) next.removeFirst()
        return if (fits(next, MAX_EXCHANGES, MAX_CHARS)) next.toList() else emptyList()
    }

    /**
     * The OpenAI-shaped `messages` array: each earlier turn as its user
     * message(s) and an assistant message, oldest first, then the new
     * question's messages ([asking]) last. Only those two roles. An assistant
     * message has only `role` and `content`; a user message has `provenance`
     * too - the tag it was first sent with, every time it is sent again.
     *
     * With a [picture] (a `data:image/jpeg;base64,` URI), the LAST new
     * message's `content` is the words and then the picture
     * ([ChatPicture.userContent]), the shape the desktop sends. Earlier turns
     * are always words only.
     */
    fun messages(window: List<Exchange>, asking: List<UserTurn>, picture: String? = null): JsonArray =
        buildJsonArray {
            for (ex in window) {
                for (u in ex.asked) add(userTurn(u))
                add(turn("assistant", ex.answer))
            }
            asking.forEachIndexed { i, u ->
                if (picture != null && i == asking.lastIndex) {
                    add(
                        buildJsonObject {
                            put("role", "user")
                            put("content", ChatPicture.userContent(u.text, picture))
                            put("provenance", u.provenance)
                        },
                    )
                } else {
                    add(userTurn(u))
                }
            }
        }

    /**
     * The whole `/api/chat` body. Built as JSON rather than by gluing strings,
     * so a quote, a newline or an emoji in any turn cannot break out of its
     * field. `has_image` is true only when a [picture] rides in the newest
     * message - the PC routes on it and keeps the turn local. `auto` mirrors
     * the desktop's own `true`. `conversation_id` goes only when it is one
     * the PC will accept; `device` always.
     */
    fun requestBody(
        window: List<Exchange>,
        asking: List<UserTurn>,
        picture: String? = null,
        conversationId: String? = null,
    ): String =
        buildJsonObject {
            put("messages", messages(window, asking, picture))
            put("has_image", picture != null)
            put("stream", true)
            put("auto", true)
            if (conversationId != null && validConversationId(conversationId)) {
                put("conversation_id", conversationId)
            }
            put("device", DEVICE)
        }.toString()

    private fun userTurn(u: UserTurn): JsonObject = buildJsonObject {
        put("role", "user")
        put("content", u.text)
        put("provenance", u.provenance)
    }

    private fun turn(role: String, content: String): JsonObject = buildJsonObject {
        put("role", role)
        put("content", content)
    }
}
