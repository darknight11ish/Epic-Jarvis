package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
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
    fun messages(
        window: List<Exchange>,
        asking: List<UserTurn>,
        picture: String? = null,
        interrupted: String? = null,
        /**
         * Jarvis Live (docs/LIVE-DESIGN.md): the newest message was SAID in a
         * Live conversation - `live: true` on it, so the PC adds its Live
         * note (short answers, choices in words, side talk answered with the
         * marker only). Never on the history, never on a typed message.
         */
        live: Boolean = false,
    ): JsonArray =
        buildJsonArray {
            for (ex in window) {
                for (u in ex.asked) add(userTurn(u))
                add(turn("assistant", ex.answer))
            }
            asking.forEachIndexed { i, u ->
                // Where the owner cut the last spoken answer off (the
                // voice flow, docs/JARVIS-API.md section 17, 6): on the
                // NEWEST message only, never replayed with the history.
                val cut = interrupted?.takeIf { i == asking.lastIndex && it.isNotBlank() }
                val liveHere = live && i == asking.lastIndex && u.provenance == Provenance.VOICE
                if (liveHere) {
                    val base = userTurn(u) + (if (cut != null) mapOf("interrupted" to JsonPrimitive(cut)) else emptyMap())
                    add(JsonObject(base + ("live" to JsonPrimitive(true))))
                } else if (picture != null && i == asking.lastIndex) {
                    add(
                        buildJsonObject {
                            put("role", "user")
                            put("content", ChatPicture.userContent(u.text, picture))
                            put("provenance", u.provenance)
                            if (cut != null) put("interrupted", cut)
                        },
                    )
                } else if (cut != null) {
                    add(JsonObject(userTurn(u) + ("interrupted" to JsonPrimitive(cut))))
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
     * the PC will accept; `device` always. `temporary: true` only for a
     * temporary chat ([TemporaryChat], docs/JARVIS-API.md section 18.1) -
     * never `false`, so an ordinary request is exactly what it was.
     */
    fun requestBody(
        window: List<Exchange>,
        asking: List<UserTurn>,
        picture: String? = null,
        conversationId: String? = null,
        interrupted: String? = null,
        temporary: Boolean = false,
        /**
         * `true` only when the owner just said yes to [CloudOffer]'s "Try
         * the cloud model" for THIS one question
         * ([ChatSession.tryCloudForLast]) - never sent as `false`, like
         * [temporary]. `cloud_yes` is the real field name
         * `backend/cloud-say-yes.patch` reads, verified against the
         * owner's real `jarvis_hud.py` (2026-09-27) - see [CloudOffer]'s
         * own doc.
         */
        cloudYes: Boolean = false,
        live: Boolean = false,
    ): String =
        buildJsonObject {
            put("messages", messages(window, asking, picture, interrupted, live))
            put("has_image", picture != null)
            put("stream", true)
            put("auto", true)
            if (conversationId != null && validConversationId(conversationId)) {
                put("conversation_id", conversationId)
            }
            put("device", DEVICE)
            if (temporary) put(TemporaryChat.FIELD, true)
            if (cloudYes) put("cloud_yes", true)
        }.toString()

    // ------------------------------------------- the chat audit (2026-09-28) ---
    //
    // "Continue this chat" and a new conversation after 30 quiet minutes (the
    // owner's decisions, CLAUDE.md "Chats, after the chat audit"). The
    // desktop's chat-history.js does the same, and both apps' tests hold
    // them to tools/gen_history_cases.py's worked examples
    // (contract/history-cases.json).

    /** A new conversation starts after this long with nothing said. */
    const val IDLE_NEW_MS = 30L * 60 * 1000

    /** Said, quietly, when it happens. */
    const val IDLE_NEW_LINE = "It's been a while, so this is a new conversation. The last one is in History."

    /** The same for a temporary chat or a game: it was never kept, so there is
     *  no "last one in History" (the second chat audit, 2026-09-28, phone B1). */
    const val IDLE_NEW_LINE_TEMPORARY = "It's been a while, so this is a new conversation."

    /**
     * Under a chat that has gone quiet for [IDLE_NEW_MS]: the next question
     * will start a new one, said BEFORE it is sent (it used to be said only
     * after, and "Your next question follows on from the last 3" stayed on
     * screen the whole time - phone C1).
     */
    const val IDLE_NEXT_LINE =
        "It's been a while, so your next question starts a new conversation. The last one is in History."
    const val IDLE_NEXT_LINE_TEMPORARY = "It's been a while, so your next question starts a new conversation."

    /** Said when the owner starts a new conversation by hand, and the old one was kept. */
    const val NEW_CONVERSATION_KEPT = "New conversation. The last one is in History."

    /** Appended to the words about a temporary chat starting, when the chat before it was kept. */
    const val LAST_IN_HISTORY = " The chat before it is in History."

    /** Jarvis Live started here, and the chat Home was in was kept (phone worst-three #1). */
    const val LIVE_STARTED_NOTE = "Jarvis Live started a new conversation. The one before it is in History."

    /** Jarvis Live ended: its session is its own chat in History. */
    const val LIVE_ENDED_NOTE = "Live ended. If chat history is on, this session is in History."

    /** "Continue this chat" is refused while Live runs here: it would swap the chat under it. */
    const val CONTINUE_LIVE = "Jarvis Live is on here. End Live first, then continue the chat."

    /** An id this PC could never have made. */
    const val CONTINUE_INVALID = "That is not a conversation this PC keeps."

    /** Whether the next question starts a new conversation: there is one going, and nothing
     *  was said in it for [IDLE_NEW_MS]. */
    fun idleExpired(lastAtMs: Long, nowMs: Long, hasConversation: Boolean): Boolean =
        hasConversation && lastAtMs > 0 && nowMs - lastAtMs >= IDLE_NEW_MS

    /* Home's words for the chat it is in - the desktop's Jarvis bar says the same. */
    const val EARLIER_CHATS = "Earlier chats"
    const val EARLIER_CHATS_TITLE = "Your kept chats, in History."
    /** "3 older questions were not loaded - ..." - with the count (the second chat audit, 2026-09-28). */
    fun continuedTrimmed(n: Int): String =
        (if (n == 1) "1 older question was" else "${n.coerceAtLeast(0)} older questions were") +
            " not loaded - Jarvis reads back only the newest ones."

    /** "2 earlier questions were left out: ..." - a pair whose answer was not kept is not carried on. */
    fun continuedSkipped(n: Int): String =
        if (n == 1) {
            "1 earlier question was left out: its answer was not kept."
        } else {
            "${n.coerceAtLeast(0)} earlier questions were left out: their answers were not kept."
        }
    const val CONTINUED_TAINTED =
        "Jarvis read outside text earlier in this chat, so writing notes and some other actions ask you first."
    const val CONTINUED_NOTHING =
        "None of its answers were kept, so Jarvis has nothing to read back. New questions are still " +
            "filed with this chat."
    const val CONTINUED_TEMPORARY_OFF = "Temporary chat is off: a continued chat is kept."

    /**
     * Chat history is off, or cannot keep anything right now: what was said in
     * the chat can be read, but what is said from now on is not filed with it
     * (the owner, 2026-09-29). The desktop's Jarvis bar says the same words
     * (tools/gen_history_cases.py).
     */
    const val CONTINUED_HISTORY_OFF = "Chat history is off, so new messages in this chat will not be kept."
    const val CONTINUED_HISTORY_STUCK =
        "Chat history cannot keep anything right now, so new messages in this chat will not be kept."

    /**
     * The line "Continue this chat" adds when the PC says new messages will
     * not be kept, or null when they will be - or when the PC does not say
     * (an older PC, or an answer that is not a clear yes or no: never a guess).
     */
    fun continuedHistoryLine(keeping: ChatLog.Keeping?): String? = when {
        keeping == null -> null
        keeping.enabled == false -> CONTINUED_HISTORY_OFF
        keeping.enabled == true && keeping.recording == false -> CONTINUED_HISTORY_STUCK
        else -> null
    }

    /**
     * Does a finished question and answer join Home's scrollable thread, and
     * what the model is re-sent? Not a crisis turn (the owner, 2026-09-29): the
     * help answer shows once, on screen, and is gone with the next question.
     * The PC still keeps the chat in History, as "A difficult moment".
     */
    fun keepsInThread(crisis: Boolean): Boolean = !crisis
    const val CONTINUE_BUSY = "Wait for the answer to finish, then continue the chat."
    const val CHAT_GONE =
        "That chat was deleted, so this is a new conversation. Nothing from it is sent to Jarvis again."
    const val MOVED_HERE = "Carrying on the same chat here."
    const val NEW_CONVERSATION = "New conversation."

    fun continuedLine(title: String?): String = "Carrying on \"${title?.trim()?.ifEmpty { null } ?: "(no title)"}\"."

    /** The most finished pairs Home's thread shows (chat-history.js THREAD_MAX). */
    const val THREAD_MAX = 100

    /**
     * [thread] with one more finished pair on the end, capped at
     * [THREAD_MAX]. Unlike [commit], nothing is trimmed to fit the model:
     * this is what Home SHOWS of the conversation (the owner's decision,
     * 2026-09-28: "the whole current conversation as a scrollable thread"),
     * not what is re-sent.
     */
    fun addToThread(thread: List<Exchange>, asked: List<UserTurn>, answer: String): List<Exchange> {
        val kept = asked.filter { it.text.isNotBlank() }
        if (kept.isEmpty() || answer.isBlank()) return thread
        return (thread + Exchange(kept, answer)).takeLast(THREAD_MAX)
    }

    /**
     * The finished pairs above the one on screen: all of [thread], less its
     * last pair when that is the question Home is showing with its answer.
     * A pair joins the thread only once its answer has finished, so while
     * [streaming] the question on screen is not in it yet. (The answer's
     * words are not compared: reading them here would redraw Home on every
     * streamed word.)
     */
    fun threadBefore(
        thread: List<Exchange>,
        question: String?,
        streaming: Boolean,
        // False when the question on screen got no answer (it failed, or came
        // back empty): its pair is not in the thread, so the LAST pair is an
        // older one that happens to have the same words, and must stay
        // (the second chat audit, 2026-09-28, phone B3).
        answered: Boolean = true,
    ): List<Exchange> {
        val last = thread.lastOrNull() ?: return thread
        return if (!streaming && answered && question != null && last.question == question) {
            thread.dropLast(1)
        } else {
            thread
        }
    }

    fun threadSummary(n: Int): String =
        if (n == 1) "Earlier in this chat · 1 question" else "Earlier in this chat · $n questions"

    /**
     * The line drawn in the thread where what Jarvis reads back begins: the
     * thread shows the whole conversation, but only the newest questions go to
     * the model with the next one (the second chat audit, 2026-09-28). The
     * desktop's bar says the same.
     */
    const val THREAD_READS_FROM = "Jarvis reads from here down. What is above stays on screen only."

    /**
     * How many of the thread's first pairs are above that line: the thread
     * holds [threadLen] pairs and the model is re-sent the newest [windowLen]
     * of them. 0: all of it is read, no line is drawn.
     */
    fun pairsAboveReadLine(threadLen: Int, windowLen: Int): Int {
        val t = threadLen.coerceAtLeast(0)
        val w = windowLen.coerceAtLeast(0)
        return (t - minOf(t, w)).coerceAtLeast(0)
    }

    private val KNOWN = setOf("typed", "voice", "shared", "clipboard", "pasted", "picture_caption")

    /**
     * "Continue this chat": the kept messages of a History conversation
     * ([ChatLog.Transcript]) as this chat's window - each question whose
     * answer was kept, with that answer, oldest first; a question whose
     * answer was not kept, or with no answer after it, is skipped, and so is
     * a Live side remark. Then only the newest pairs that fit [MAX_EXCHANGES]
     * and [MAX_CHARS] - a live chat's own limits. [Continued.trimmedCount]:
     * older pairs were left out, and Home says how many; [Continued.skipped]:
     * questions left out because no answer was kept, said the same way. A
     * support or chatbot row is never loaded. A tag this app does not know
     * goes as "unknown" - never the owner's own words.
     */
    fun continueWindow(turns: List<ChatLog.Turn>): Continued {
        val pairs = ArrayDeque<Exchange>()
        var pending: ChatLog.Turn? = null
        var skipped = 0
        // Shared text right before the owner's own question is not a question
        // of its own: outside text goes back only with the answer it got.
        fun unanswered(p: ChatLog.Turn?) = p != null && p.provenance != "shared"
        for (t in turns) {
            when (t.role) {
                "user" -> {
                    if (unanswered(pending)) skipped += 1
                    if (!t.answerKept && t.text.isNotBlank()) skipped += 1
                    pending = t.takeIf { it.answerKept && it.text.isNotBlank() }
                }
                "assistant" -> {
                    val q = pending
                    if (q != null && t.text.isNotBlank() && !sideTalk(t.text)) {
                        val tag = q.provenance?.takeIf { it in KNOWN } ?: "unknown"
                        pairs.addLast(Exchange(listOf(UserTurn(q.text, tag)), t.text))
                    } else if (unanswered(q) && t.text.isBlank()) {
                        skipped += 1
                    }
                    pending = null
                }
                else -> {
                    if (unanswered(pending)) skipped += 1
                    pending = null
                }
            }
        }
        if (unanswered(pending)) skipped += 1
        var trimmedCount = 0
        while (pairs.isNotEmpty() && !fits(pairs, MAX_EXCHANGES, MAX_CHARS)) {
            pairs.removeFirst()
            trimmedCount += 1
        }
        return Continued(pairs.toList(), trimmedCount, skipped)
    }

    /** What "Continue this chat" loads: the [window], and what was left out and why. */
    data class Continued(val window: List<Exchange>, val trimmedCount: Int, val skipped: Int) {
        val trimmed: Boolean get() = trimmedCount > 0
    }

    private fun sideTalk(answer: String): Boolean {
        val a = answer.trim().lowercase().replace(Regex("\\.+$"), "").trim()
        return a == "[not for me]" || a == "(not for jarvis)"
    }

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
