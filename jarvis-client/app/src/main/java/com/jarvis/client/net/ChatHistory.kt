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

    /** One finished turn: the question as sent and the whole answer. */
    data class Exchange(val question: String, val answer: String) {
        val chars: Int get() = question.length + answer.length
    }

    const val MAX_EXCHANGES = 10
    const val MAX_CHARS = 18_000
    const val KEEP_EXCHANGES = 6
    const val KEEP_CHARS = 12_000

    fun chars(window: List<Exchange>): Int = window.sumOf { it.chars }

    private fun fits(window: List<Exchange>, maxExchanges: Int, maxChars: Int): Boolean =
        window.size <= maxExchanges && chars(window) <= maxChars

    /**
     * [window] with one more finished turn on the end, trimmed if it has
     * grown past the limits. A blank question or answer is not a turn worth
     * replaying, so the window comes back unchanged.
     *
     * When trimming, the newest pair is always the last to go: it is kept
     * alone if it is bigger than [KEEP_CHARS] but still inside [MAX_CHARS],
     * and dropped only when it is too big to send at all.
     */
    fun commit(window: List<Exchange>, question: String, answer: String): List<Exchange> {
        if (question.isBlank() || answer.isBlank()) return window
        val next = ArrayDeque(window)
        next.addLast(Exchange(question, answer))
        if (fits(next, MAX_EXCHANGES, MAX_CHARS)) return next.toList()
        while (next.size > 1 && !fits(next, KEEP_EXCHANGES, KEEP_CHARS)) next.removeFirst()
        return if (fits(next, MAX_EXCHANGES, MAX_CHARS)) next.toList() else emptyList()
    }

    /**
     * The OpenAI-shaped `messages` array: each earlier pair as a user turn and
     * an assistant turn, oldest first, then the new question last. Only those
     * two roles, and only `role` and `content` on each.
     */
    fun messages(window: List<Exchange>, question: String): JsonArray = buildJsonArray {
        for (ex in window) {
            add(turn("user", ex.question))
            add(turn("assistant", ex.answer))
        }
        add(turn("user", question))
    }

    /**
     * The whole `/api/chat` body. Built as JSON rather than by gluing strings,
     * so a quote, a newline or an emoji in any turn cannot break out of its
     * field. `has_image` is always false: this client has no screenshot
     * capture. `auto` mirrors the desktop's own `true`.
     */
    fun requestBody(window: List<Exchange>, question: String): String = buildJsonObject {
        put("messages", messages(window, question))
        put("has_image", false)
        put("stream", true)
        put("auto", true)
    }.toString()

    private fun turn(role: String, content: String): JsonObject = buildJsonObject {
        put("role", role)
        put("content", content)
    }
}
