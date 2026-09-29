package com.jarvis.client.net

import android.os.SystemClock
import android.util.Log
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import okhttp3.Call
import okhttp3.Response

/**
 * One turn of conversation at a time, sent with the conversation so far
 * ([history]; see [ChatHistory]).
 *
 * `POST /api/chat` streams its reply as a **chunked HTTP body** whose framing
 * depends on the upstream model in use: the server copies the upstream
 * `Content-Type` verbatim, so a plain-text upstream produces raw tokens but an
 * OpenAI-style upstream produces `data:`-framed SSE lines on this same route
 * (`docs/API-DISAGREEMENTS.md` §4). [ChatChunkParser] handles both shapes;
 * bytes are decoded to characters, split into lines, and each line is routed
 * through it rather than appended to the reply as-is.
 *
 * Interruption is the cancellation of the HTTP call itself. There is no
 * "stop" endpoint, and inventing one client-side by ignoring the rest of the
 * stream would leave the desktop generating into nothing. The same cancel
 * also runs proactively once a line reports the stream is over, rather than
 * waiting for the socket to close on its own - see [ChatChunkParser.Result.Terminal].
 */
class ChatSession(
    private val api: JarvisApi,
    /**
     * Whether the PC says it can hold a temporary chat
     * (`capabilities.temporary_chat`, [TemporaryChat]). Read before turning
     * it on and again before every temporary question: nothing is ever sent
     * as temporary to a PC that would ignore the flag.
     */
    private val canTemporary: () -> Boolean = { false },
) {

    /**
     * Where the owner last cut Jarvis's spoken answer off (the voice flow,
     * docs/JARVIS-API.md section 17, 6), set by VoiceSession and sent once,
     * with the next question, as `interrupted`.
     */
    val cutOff = com.jarvis.client.voice.CutOff()

    private val _reply = MutableStateFlow("")

    /** The reply so far. Grows as chunks land. */
    val reply: StateFlow<String> = _reply.asStateFlow()

    private val _streaming = MutableStateFlow(false)
    val streaming: StateFlow<Boolean> = _streaming.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val _problem = MutableStateFlow<PlainErrors.Shown?>(null)

    /**
     * The failure on [error], in the plain words both apps use
     * ([PlainErrors]): what happened, what to do, ONE button, and the
     * technical detail - scrubbed - for "Details". [error] is its
     * [PlainErrors.Shown.text]. Null with no failure.
     */
    val problem: StateFlow<PlainErrors.Shown?> = _problem.asStateFlow()

    /** The last question as it was asked, for "Try again" ([retryLast]). Memory only. */
    @Volatile private var lastAsked: Triple<String, String, String?>? = null

    private val _question = MutableStateFlow<String?>(null)

    /**
     * The owner's last question, as sent - null until the first one.
     *
     * Home shows it as a "You" line above [reply]: the composer is cleared on
     * send, so an answer used to sit on screen with nothing to say what it
     * answered. Held in memory only, in this one field, and never written
     * anywhere - a question can be about email, files or memory, and rule 1
     * keeps those on this phone and the desktop and nowhere else. Gone when
     * the process is.
     */
    val question: StateFlow<String?> = _question.asStateFlow()

    private val _turnId = MutableStateFlow<String?>(null)

    /**
     * The id the desktop gave the answer now on screen, or null.
     *
     * Read from the answer's `X-Jarvis-Route` response header, where
     * `feedback.patch` puts it as `turn_id`, so the owner can mark THIS answer
     * right or wrong. Null until the headers of the current answer arrive,
     * and null for good on a backend that does not send one - Home then shows
     * no mark buttons at all. Memory only, like [question]: an id and nothing
     * else, and never written anywhere.
     */
    val turnId: StateFlow<String?> = _turnId.asStateFlow()

    private val _waiting = MutableStateFlow<String?>(null)

    /**
     * What the answer on its way is waiting on, in words, or null.
     *
     * "Waiting for your approval…" while an approval card is up on the
     * desktop - the desktop says so in the stream (`: jarvis-status approval`,
     * `backend/chat-stream.patch`). Before that, a tool turn showed "…" for up
     * to three minutes and then "timeout". Cleared as soon as words arrive.
     */
    val waiting: StateFlow<String?> = _waiting.asStateFlow()

    private val _answerNote = MutableStateFlow<String?>(null)

    /**
     * One line to show under the answer, or null: that it was cut short at
     * the length limit (it used to look finished), and/or that a cloud model
     * wrote it rather than this user's PC, or that the PC's second graphics
     * card did (both read from `X-Jarvis-Route`).
     */
    val answerNote: StateFlow<String?> = _answerNote.asStateFlow()

    private val _history = MutableStateFlow<List<ChatHistory.Exchange>>(emptyList())

    /**
     * The conversation so far - finished questions and their answers, oldest
     * first, already trimmed to what the desktop's model has room for. Sent
     * ahead of every new question, so a follow-up is understood; see
     * [ChatHistory] for the limits and why.
     *
     * Memory only, like [question]: never written anywhere, gone with the
     * process or on [newConversation]. A question that failed, was stopped,
     * or came back empty is not added - replaying half an answer as if it
     * were the whole one would mislead the model on every later turn.
     */
    val history: StateFlow<List<ChatHistory.Exchange>> = _history.asStateFlow()

    /**
     * Which conversation a [send] belongs to. [newConversation] moves it on,
     * so an answer that finishes AFTER the owner started afresh is not
     * written into the new, empty conversation.
     */
    @Volatile private var conversation = 0

    /**
     * The `conversation_id` every request carries (docs/JARVIS-API.md
     * section 18), so the PC keeps this chat as one conversation in its
     * History. A new one when this session is made - that is, when the app
     * starts - and on [newConversation]. Made up here, never read from the
     * PC, and never written anywhere on the phone.
     */
    @Volatile private var conversationId: String = ChatHistory.newConversationId()

    /**
     * When the last answer of this conversation finished (wall clock, ms), for
     * "a new conversation starts after 30 quiet minutes" (the owner's
     * decision, 2026-09-28; [ChatHistory.idleExpired]). 0: none yet.
     */
    @Volatile private var lastTurnAt = 0L

    private val _thread = MutableStateFlow<List<ChatHistory.Exchange>>(emptyList())

    /**
     * What Home SHOWS of this conversation (the owner's decision, 2026-09-28:
     * the whole conversation as a scrollable thread): every finished pair,
     * oldest first - not trimmed to the model's re-send window like
     * [history], only capped ([ChatHistory.THREAD_MAX]). Memory only; emptied
     * wherever [history] starts afresh.
     */
    val thread: StateFlow<List<ChatHistory.Exchange>> = _thread.asStateFlow()

    private val _game = MutableStateFlow(false)

    /**
     * The PC made this conversation temporary by itself, because it is a
     * game or role-play (the route header said so). Nothing of it is kept, so
     * the notes about "the last one is in History" are not said for it. Ends
     * with the conversation (the second chat audit, 2026-09-28, phone B1).
     */
    val game: StateFlow<Boolean> = _game.asStateFlow()

    private val _readOutside = MutableStateFlow(false)

    /**
     * This conversation has read outside text (a chat carried on from History
     * that did, or one that read a page or an email since): the line about it
     * stays on Home for as long as the conversation does, instead of vanishing
     * with the next question (the second chat audit, phone C4). Set by
     * [continueFrom]; cleared by [newConversation].
     */
    val readOutside: StateFlow<Boolean> = _readOutside.asStateFlow()

    /** Is there a chat here that was kept on the PC - so a new one can say where it went? */
    fun hasKeptChat(): Boolean = _history.value.isNotEmpty() && !_temporary.value && !_game.value

    /** Has the chat gone quiet for 30 minutes - so the next question starts a new one? */
    fun idleNow(): Boolean =
        ChatHistory.idleExpired(lastTurnAt, System.currentTimeMillis(), _history.value.isNotEmpty())

    private val _chatNote = MutableStateFlow<String?>(null)

    /**
     * One quiet line about the chat itself, or null (the chat audit,
     * 2026-09-28): a new conversation after 30 quiet minutes, a chat carried
     * on from History ("Continue this chat") or from Live's "Move it here",
     * the chat Home was in deleted elsewhere. The desktop's Jarvis bar shows
     * the same words (tools/gen_history_cases.py). Words only; memory only.
     */
    val chatNote: StateFlow<String?> = _chatNote.asStateFlow()

    /** The conversation id the next question goes with - for Jarvis Live,
     *  which names its chat to the PC so "Move it here" carries it on. */
    fun conversationIdNow(): String = conversationId

    @Volatile private var call: Call? = null

    private val _temporary = MutableStateFlow(false)

    /**
     * A temporary chat is on (the owner's decision, 2026-09-25;
     * [TemporaryChat]): every question - typed or spoken - goes with
     * `"temporary": true`, so the PC uses and learns nothing from memory and
     * keeps nothing of the chat. Memory only; off when the app starts.
     */
    val temporary: StateFlow<Boolean> = _temporary.asStateFlow()

    private val _usedIds = MutableStateFlow<List<Long>>(emptyList())

    /**
     * The facts the answer on screen used, by id, from its `X-Jarvis-Route`
     * ([MemoryUsed.idsFromRouteHeader]) - for "Used 2 memories" under it.
     * Ids only: the words are read from the PC when the owner opens the
     * list. Empty for a temporary answer, and cleared with the answer.
     */
    val usedIds: StateFlow<List<Long>> = _usedIds.asStateFlow()

    private val _crisis = MutableStateFlow(false)

    /**
     * The crisis help line (`jarvis_wellbeing.py`, the owner's decision of
     * 2026-09-27; docs/JARVIS-API.md section 38): true only while the
     * answer on screen is the one Jarvis is showing after the owner
     * mentioned wanting to hurt themselves - so Home can draw it as a
     * calm, plain panel. The word check, the help message and never
     * learning from it all run on the PC regardless of this flag; it only
     * changes how the words already on screen are drawn. Read off the same
     * `X-Jarvis-Route` header as [usedIds] ([Wellbeing.crisisFromHeader]);
     * cleared with the answer, like it.
     */
    val crisis: StateFlow<Boolean> = _crisis.asStateFlow()

    private val _cloudOffer = MutableStateFlow<String?>(null)

    /**
     * "A cloud model could give this one a second look." under the answer
     * on screen - the lane [CloudOffer.laneFromHeader] read off this turn's
     * `X-Jarvis-Route`, or null: no offer, or the owner has already tapped
     * "Try the cloud model" or dismissed it ([tryCloudForLast],
     * [dismissCloudOffer]). Cleared with the answer, like [crisis] and
     * [usedIds] - the moment a newer question is asked, the old turn's
     * offer is gone for good, never replayed on top of a different answer.
     */
    val cloudOffer: StateFlow<String?> = _cloudOffer.asStateFlow()

    private val _openSettings = MutableStateFlow<String?>(null)

    private val _faceTuningChange = MutableStateFlow<String?>(null)

    /**
     * "Make the animal sharper" by voice or chat (docs/JARVIS-API.md section
     * 60): one of [AnimalOptions.DEVICE_CHANGES], read off the same
     * `X-Jarvis-Route` header ([AnimalOptions.fromRoute]), or null. Per
     * device, so the PC changed nothing: `MainActivity` applies it to this
     * phone's own face settings once, then calls [consumeFaceTuningChange].
     */
    val faceTuningChange: StateFlow<String?> = _faceTuningChange.asStateFlow()

    fun consumeFaceTuningChange() {
        _faceTuningChange.value = null
    }

    /**
     * "Open <a settings section>" by voice or chat
     * (`jarvis_settings_registry.py`, docs/JARVIS-API.md section 58.1): the
     * section id the answer on screen named, or null. Read off the same
     * `X-Jarvis-Route` header as [usedIds]/[crisis]
     * ([Schedule.openSettingsFromRoute]); cleared with the answer, like
     * them, so a manual reopen of Settings later does not jump anywhere on
     * its own. Pure navigation - nothing here changes a setting;
     * MainActivity is the only reader, and hands it on to `SettingsScreen`'s
     * own `initialSection`.
     */
    val openSettings: StateFlow<String?> = _openSettings.asStateFlow()

    /**
     * Marks the current [openSettings] target as done. Bug audit
     * 2026-09-27, finding #4: without this, nothing ever cleared the
     * target once `MainActivity` had acted on it, so a rotation (or any
     * other activity rebuild) saw the same non-null value again and jumped
     * back into Settings on its own. `MainActivity` calls this right after
     * navigating, once, so the same answer never fires a second time.
     */
    fun consumeOpenSettings() {
        _openSettings.value = null
    }

    /**
     * Drops [cloudOffer] without asking anything - the offer's own
     * "dismissible" half. Safe to call with no offer showing.
     */
    fun dismissCloudOffer() {
        _cloudOffer.value = null
    }

    /**
     * Turns a temporary chat on or off, and starts a new conversation
     * either way ([newConversation]) - so nothing said in one kind of chat
     * is re-sent in the other. ON only when the PC says it has one.
     * @return the sentence to show, or null when nothing changed.
     */
    fun setTemporary(on: Boolean): String? {
        if (on == _temporary.value) return null
        if (on && !canTemporary()) return TemporaryChat.UNAVAILABLE
        // The chat this ends was kept, unless it was itself temporary: say
        // where it went (the second chat audit, phone C6 - it used to go silently).
        val kept = hasKeptChat()
        newConversation()
        _temporary.value = on
        // Said on Home too (the chat audit, 2026-09-28, phone B5: the phone
        // dropped this sentence, and the chat on screen went without a word).
        val said = (if (on) TemporaryChat.STARTED else TemporaryChat.ENDED) +
            (if (kept) ChatHistory.LAST_IN_HISTORY else "")
        return said.also { _chatNote.value = it }
    }

    /** "New conversation", pressed by the owner: [newConversation], and Home
     *  says so (read out by TalkBack - the chat audit, 2026-09-28). */
    fun newConversationSaid() {
        // Says where the old chat went, as the desktop does ("Chat ended.
        // Kept chats are in Brain > History") - only when it was kept.
        val kept = hasKeptChat()
        newConversation()
        _chatNote.value = if (kept) ChatHistory.NEW_CONVERSATION_KEPT else ChatHistory.NEW_CONVERSATION
    }

    /**
     * Jarvis Live started here with a fresh conversation (a spoken "let's
     * talk", or a session with no chat to carry on): Home's chat goes, and
     * says so - it used to go without a word (the second chat audit,
     * 2026-09-28, phone worst-three #1).
     */
    fun startLiveConversation() {
        val kept = hasKeptChat()
        newConversation()
        if (kept) _chatNote.value = ChatHistory.LIVE_STARTED_NOTE
    }

    /** Jarvis Live ended here: its session is its own chat in History. */
    fun noteLiveEnded() {
        _chatNote.value = ChatHistory.LIVE_ENDED_NOTE
    }

    /** The owner dismissed the line about the chat. */
    fun dismissChatNote() {
        _chatNote.value = null
    }

    /**
     * Sends a turn and returns the reply **this** call produced, or null if it
     * did not finish.
     *
     * The return value exists because the voice loop used to read
     * `chat.reply.value` after `send` came back, and there is only one shared
     * `_reply`. A typed message sent while a spoken one was still streaming
     * cancels the voice call — so the read picked up the *typed* question's
     * half-streamed answer, and Jarvis spoke it aloud as the answer to
     * something else entirely.
     *
     * [onDelta], if given, is called with the reply text accumulated SO FAR
     * every time this call publishes to [reply] - same throttling, same
     * accumulator, just handed to a caller-local callback instead of only the
     * shared flow. This is deliberately NOT "subscribe to `reply`": a second
     * subscriber reading the shared flow is exactly the hazard the paragraph
     * above describes, reopened one layer up. A callback scoped to THIS one
     * call cannot observe a different call's text, whatever else is running
     * concurrently - the voice loop's own sentence-streaming TTS uses this to
     * start speaking before the answer has finished arriving, without ever
     * touching [reply] itself.
     *
     * [onRoute], if given, gets this call's `X-Jarvis-Route` header (or null
     * when the PC sent none) once, as the headers arrive and before the
     * first word - call-local, like [onDelta].
     *
     * [picture], when given, is a `data:image/jpeg;base64,` URI ([ChatPicture])
     * sent inside this one question. It is not kept: only the words join
     * [history], so it is never sent again with a later question.
     *
     * [provenance] says where [message] came from ([Provenance]): the chat
     * box sends "typed" or "pasted", the voice loop "voice". With a
     * [picture], typed or voice words are tagged "picture_caption"; pasted
     * words stay "pasted" ([ChatHistory.asking]).
     * [shared] is text another app handed over through the Share sheet: it
     * goes as its own message, tagged "shared", right before [message] - and
     * alone when [message] is blank. Both join [history] with their tags.
     */
    suspend fun send(
        message: String,
        onDelta: ((String) -> Unit)? = null,
        picture: String? = null,
        onRoute: ((String?) -> Unit)? = null,
        provenance: String = Provenance.TYPED,
        shared: String? = null,
        /**
         * Each `: jarvis-status` word of THIS answer, as it arrives - a
         * call-local callback like [onDelta]. The voice loop uses it to say
         * a card is waiting, and then how it ended (voice/CardVoice.kt).
         */
        onStatus: ((String) -> Unit)? = null,
        /**
         * The owner's yes to [CloudOffer]'s "Try the cloud model" for THIS
         * one question ([tryCloudForLast]) - sent as `cloud_yes: true`.
         * Never set on an ordinary send; the router treats its absence as
         * "no", same as [temporary]'s absence means "not temporary".
         */
        cloudYes: Boolean = false,
        /**
         * Jarvis Live: this spoken question was said in a Live conversation
         * (`live: true` on it - ChatHistory.messages). An answer that is only
         * the side-talk marker ("[not for me]") is then shown as "(not for
         * Jarvis)" and not kept in the conversation.
         */
        live: Boolean = false,
    ): String? {
        cancel()
        // A new conversation after 30 quiet minutes (the owner's decision,
        // 2026-09-28) - never in the middle of Jarvis Live, which ends itself
        // when it goes quiet. The old one stays in History; "Continue this
        // chat" brings it back. Said once, quietly, above the new question.
        _chatNote.value = null
        if (!live && ChatHistory.idleExpired(lastTurnAt, System.currentTimeMillis(), _history.value.isNotEmpty())) {
            // A temporary chat or a game was never kept: no "last one in History".
            val kept = hasKeptChat()
            conversation++
            conversationId = ChatHistory.newConversationId()
            _history.value = emptyList()
            _thread.value = emptyList()
            _game.value = false
            _readOutside.value = false
            lastTurnAt = 0L
            _chatNote.value = if (kept) ChatHistory.IDLE_NEW_LINE else ChatHistory.IDLE_NEW_LINE_TEMPORARY
        }
        _reply.value = ""
        _error.value = null
        _problem.value = null
        // Kept for "Try again" under a failure: the same words, with the same
        // tag (a pasted question stays pasted) and the same shared text. A
        // picture is not kept - it is sent once.
        lastAsked = Triple(message, provenance, shared)
        // Set as the old reply is cleared, before anything can fail below:
        // a question that got no answer is still what the owner asked, and
        // the screen should not go on showing the one before it. Shared text
        // sent on its own is what was asked, so it is what is shown.
        _question.value = if (message.isBlank() && !shared.isNullOrBlank()) shared else message
        // The previous answer's id goes with the previous answer: a mark
        // tapped now must never land on the answer that is being replaced.
        _turnId.value = null
        _waiting.value = null
        _answerNote.value = null
        _usedIds.value = emptyList()
        _crisis.value = false
        _openSettings.value = null
        _cloudOffer.value = null
        // A temporary question goes only to a PC that says it can hold one -
        // asked again now, since the PC may have changed since it was turned on.
        val asTemporary = _temporary.value
        if (asTemporary && !canTemporary()) {
            _problem.value = PlainErrors.shown("pc_said", TemporaryChat.UNAVAILABLE).copy(chat = true)
            _error.value = TemporaryChat.UNAVAILABLE
            return null
        }

        // Captured before the request goes, and the same list that is sent:
        // what this question was asked in the light of.
        val earlier = _history.value
        val askedIn = conversation
        // The look at the phone's own screen, if one is held ("Look at this"
        // from the assistant gesture, or a Watch-with-me picture): it rides
        // with THIS question only, in memory, to the PC - never in Live,
        // never in the history (ScreenLook, docs/JARVIS-API.md section 62).
        // "Watch with me" on this phone: while it runs, the picture for THIS
        // question is taken now (or the reason there is none is said) - never
        // before, never streamed (ScreenWatch). Not in Live.
        if (!live) ScreenWatch.beforeQuestion()
        val look = if (live) null else ScreenLook.forQuestion()
        val screen = look?.let { ScreenLook.attach(it) }
        val sentPicture = picture ?: look?.picture
        val asking = ChatHistory.asking(message, provenance, shared, picture = sentPicture != null)
        // The owner cut the last spoken answer off (VoiceSession): where,
        // for this question only - the PC tells its model, and takes the
        // field off before any model or the relay sees the conversation.
        val interrupted = cutOff.take(SystemClock.elapsedRealtime())
        val c = api.chatCall(
            asking, earlier, sentPicture, conversationId,
            interrupted = interrupted, temporary = asTemporary, cloudYes = cloudYes, live = live,
            screen = screen,
        )
        if (c == null) {
            // No address to send to: none saved, or a saved one off the
            // owner's own networks (OwnNetwork), which says why in its own
            // sentence rather than "not paired".
            val refused = api.baseProblem()
            val p = if (refused != null) {
                PlainErrors.forApiError(ApiError.Unreachable(refused)).copy(chat = true)
            } else {
                PlainErrors.forInput(PlainErrors.Input(notPaired = true)).copy(chat = true)
            }
            _problem.value = p
            _error.value = p.text
            return null
        }
        call = c
        _streaming.value = true

        var mine: String? = null
        // An SSE-framed answer (`data:` lines) says when it has finished -
        // `[DONE]` or a `finish_reason`. One that stops without saying so was
        // cut off: shown as it is, returned as it is, but not added to the
        // conversation, where it would be replayed as a whole answer on every
        // later turn. The HUD page draws the same line. A plain-text upstream
        // has no end marker, so for it the end of the body is the end.
        var cutShort = false
        // This turn is a crisis turn (the PC's own flag in X-Jarvis-Route): its
        // question and help answer stay on screen as the current answer, but
        // never join the thread or what the model is re-sent - the next question
        // takes them off the screen for good (the owner, 2026-09-29). Kept per
        // call: `_crisis` is the shared, screen-facing copy and a newer question
        // clears it.
        var crisisTurn = false
        withContext(Dispatchers.IO) {
            // Cancelling this coroutine has to cancel the HTTP call, and only a
            // coroutine that is NOT parked on the socket can do it.
            //
            // The read loop below is blocking okio/IO with no suspension point,
            // so cancellation alone reached nothing: leaving the screen
            // cancelled the coroutine while the socket kept streaming and
            // `_reply` kept being written for a screen that no longer existed,
            // with the desktop generating into it. This is the same failure
            // [EventStream] fixes with the same shape (see the note on `live`
            // there): `Call.cancel()` is the one OkHttp operation documented as
            // safe from any thread, and it fails an in-flight read at once,
            // where closing the body promises nothing to a read already blocked
            // on it. A child coroutine is cancelled the instant its parent is,
            // whatever the parent's thread is doing, so this one is always free
            // to run that cancel. It is cancelled again in the `finally` below
            // on the normal path, where cancelling a finished call is a no-op.
            val closer = launch {
                try {
                    awaitCancellation()
                } finally {
                    runCatching { c.cancel() }
                }
            }
            // The scope is captured rather than used implicitly, so the
            // `ensureActive()` inside the read loop cannot bind to anything but
            // this coroutine.
            val io = this
            // Every write to the SHARED flows goes through one of these two.
            //
            // The `finally` below already refuses to clear `_streaming` and
            // `call` unless this call is still the current one, and gives the
            // reason: `send` starts by cancelling the previous call, and the
            // loser unwinds through this same block afterwards. The flows the
            // loser writes on its way out needed the identical guard and did
            // not have it. `send` #2 sets `_error.value = null` and
            // `_reply.value = ""`; call #1, failing for a real reason at that
            // same moment, then wrote its error over the clean slate and its
            // last half-line of text over the empty reply - so the new question
            // appeared on screen already carrying the old one's error, or the
            // old one's tail.
            fun failWith(p: PlainErrors.Shown) {
                if (call === c) {
                    _problem.value = p.copy(chat = true)
                    _error.value = p.text
                }
            }
            try {
                c.execute().use { resp ->
                    if (!resp.isSuccessful) {
                        // The server's own words first, when it has any.
                        //
                        // "The desktop answered 503." is true and useless. The
                        // backend returns 503 with a body that says WHICH thing
                        // is not up and usually what to do about it - the model
                        // is still loading, Ollama is not running - and that
                        // sentence was being thrown away in favour of a number,
                        // leaving the owner to go and read a log to learn
                        // something the reply already contained.
                        val detail = serverDetail(resp)
                        // The plain words both apps use (PlainErrors): a 401
                        // or 403 is the pairing key, a 404 or 501 with no
                        // sentence a PC too old for this, and a sentence of
                        // the desktop's own - a model that is not installed,
                        // say - is shown as it is: it says what is wrong and
                        // what to do. A status number is never shown, only
                        // kept behind Details. The token is in the REQUEST,
                        // never in the response, so nothing of it is here.
                        failWith(
                            PlainErrors.forInput(
                                PlainErrors.Input(http = resp.code, said = detail),
                                detail.orEmpty(),
                            ),
                        )
                        return@use
                    }
                    // The answer's id, from the headers, which arrive before
                    // the first word. Same identity guard as every other
                    // write to the shared flows: a cancelled call unwinding
                    // late must not put its id beside the new answer.
                    val routeHeader = resp.header(Feedback.ROUTE_HEADER)
                    val tid = Feedback.turnIdFromRouteHeader(routeHeader)
                    if (call === c) _turnId.value = tid
                    // The whole header, to THIS call's own caller - the voice
                    // loop decides from it whether a private answer may be
                    // read aloud (voice/PrivateAloud.kt). Before any word, and
                    // unguarded like `onDelta`: it belongs to this call alone.
                    onRoute?.invoke(routeHeader)
                    // Where it was made. Only a cloud answer gets a line: an
                    // answer from this user's own PC is the normal case.
                    val cloud = ChatChunkParser.whereFromRouteHeader(routeHeader) == "cloud"
                    // Or the second graphics card (`second_card` in the same
                    // header, second-card.patch): still this PC, but not the
                    // everyday model, so it gets a line of its own.
                    val secondCard = SecondCard.routeFromHeader(routeHeader)
                    // Answered on the PC WITHOUT the model - a timer, a
                    // reminder, the to-do list (`quick` in the same header;
                    // docs/JARVIS-API.md section 21): the small "done" line.
                    val quick = Schedule.quickFromRouteHeader(routeHeader)
                    crisisTurn = Wellbeing.crisisFromHeader(routeHeader)
                    // The facts this answer used, by id, for "Used 2
                    // memories" - none on a temporary one - and what the PC
                    // said about a temporary question (TemporaryChat.notes).
                    if (call === c) {
                        if (TemporaryChat.isGame(asTemporary, routeHeader)) _game.value = true
                        _usedIds.value = if (asTemporary) emptyList() else MemoryUsed.idsFromRouteHeader(routeHeader)
                        // The crisis help line (jarvis_wellbeing.py): the
                        // one flag that says whether the answer arriving is
                        // shown as a calm, plain panel. Not confirmed sent
                        // by every backend yet (see Wellbeing.kt); false
                        // just means an ordinary bubble, as before.
                        _crisis.value = Wellbeing.crisisFromHeader(routeHeader)
                        // "Open <a settings section>" (jarvis_settings_
                        // registry.py, docs/JARVIS-API.md section 58.1):
                        // pure navigation, read the same way.
                        // "Forget what you learned last week" (2026-09-28):
                        // `open_brain` names Brain's "Forget a time frame",
                        // the list already filled in - the same navigation,
                        // through OpenPlace. Nothing is removed by it.
                        _openSettings.value = Schedule.openSettingsFromRoute(routeHeader)
                            ?: ForgetRange.openFromRoute(routeHeader)
                        // Sharpness or frame rate, for this phone only.
                        _faceTuningChange.value = AnimalOptions.fromRoute(routeHeader)
                        // "A cloud model could give this one a second
                        // look." (jarvis_router.choose(), gate "offer"):
                        // read the same way as [crisis] and [usedIds]
                        // above, off the same header.
                        _cloudOffer.value = CloudOffer.laneFromHeader(routeHeader)
                    }
                    val temporaryNotes = TemporaryChat.notes(asTemporary, routeHeader)
                    // Decoded as CHARACTERS, not as whatever bytes happened
                    // to be buffered.
                    //
                    // The old loop read bytes into an okio.Buffer and called
                    // `readUtf8()` on whatever was in it. A UTF-8 character
                    // split across two TCP segments - and every emoji, curly
                    // quote and accented letter is multi-byte - was decoded
                    // half at a time: the first half became U+FFFD and the
                    // continuation bytes were eaten, so the owner saw "?" in
                    // place of the character at every chunk boundary.
                    //
                    // `charStream()` is an InputStreamReader, which keeps the
                    // trailing incomplete byte sequence and finishes decoding
                    // it when the rest of it arrives. It still streams: its
                    // `read` returns as soon as it has at least one character
                    // rather than waiting for the array to fill.
                    val reader = resp.body?.charStream() ?: return@use
                    val chunk = CharArray(CHUNK)
                    // Accumulated in a StringBuilder rather than with
                    // `_reply.value += ...`. That `+=` copied the entire reply
                    // so far for every token that arrived - quadratic in the
                    // length of the answer - and woke a Compose recomposition
                    // on each one. A long reply spent most of its time copying
                    // itself.
                    val acc = StringBuilder()
                    // A partial line carried over between reads - `chunk` is
                    // filled at socket granularity, not line granularity, so a
                    // line almost never ends exactly at its boundary.
                    val lineBuf = StringBuilder()
                    var shownAt = 0L

                    fun publish(force: Boolean) {
                        val now = SystemClock.elapsedRealtime()
                        if (!force && now - shownAt < PUBLISH_MS) return
                        shownAt = now
                        val text = acc.toString()
                        // Same identity guard as `failWith`, for the same
                        // reason. `onDelta` is NOT guarded: it belongs to this
                        // call alone - that is the whole point of it existing
                        // rather than a second subscriber to `reply` - so it
                        // still gets every delta it was promised even once a
                        // newer call owns the shared flow.
                        if (call === c) _reply.value = text
                        onDelta?.invoke(text)
                    }

                    var failed = false
                    var framed = false
                    var ended = false
                    var cutShortAtLimit = false

                    /** @return true when the caller should stop reading. */
                    fun handle(line: String): Boolean {
                        if (line.trimStart().startsWith("data:")) framed = true
                        return when (val result = ChatChunkParser.consume(line)) {
                            is ChatChunkParser.Result.Text -> {
                                if (call === c) _waiting.value = null
                                if (result.cutShort) cutShortAtLimit = true
                                acc.append(result.delta)
                                // Published as it arrives - the whole reason
                                // the body is chunked is so the reply appears
                                // as it is written - but at most every
                                // PUBLISH_MS. Token-by-token that is still
                                // ~20 updates a second, which reads as smooth
                                // typing, while a burst of tiny lines no
                                // longer costs one full string copy and one
                                // recomposition each.
                                publish(force = false)
                                if (result.terminal) ended = true
                                result.terminal
                            }
                            ChatChunkParser.Result.Terminal -> {
                                ended = true
                                true
                            }
                            ChatChunkParser.Result.CutShort -> {
                                ended = true
                                cutShortAtLimit = true
                                true
                            }
                            is ChatChunkParser.Result.Status -> {
                                // Only before the first words: after them, the
                                // words are the progress.
                                if (call === c && acc.isEmpty()) {
                                    _waiting.value = WAITING[result.word]
                                }
                                // Every word, words or not: a card can be raised
                                // after the answer has started. Not guarded, like
                                // `onDelta`: it belongs to this call alone.
                                onStatus?.invoke(result.word)
                                false
                            }
                            is ChatChunkParser.Result.Failed -> {
                                // The PC's own failure, named by its `code`:
                                // the shared plain words and a fix button,
                                // the PC's sentence kept behind Details.
                                failWith(
                                    PlainErrors.forInput(
                                        PlainErrors.Input(code = result.code, said = result.message),
                                        result.message,
                                    ),
                                )
                                failed = true
                                true
                            }
                            ChatChunkParser.Result.Ignored -> false
                        }
                    }

                    readLoop@ while (true) {
                        // Blocking reads never suspend, so nothing here would
                        // otherwise notice that the coroutine is gone. `closer`
                        // above makes the read itself fail on cancellation;
                        // this catches the case where cancellation lands
                        // between two reads, before another byte is written
                        // into a reply nobody is waiting for.
                        io.ensureActive()
                        val n = reader.read(chunk)
                        if (n < 0) {
                            // A final line with no trailing newline is still a
                            // line, and dropping it was not a tail-end nicety:
                            // `main.js`'s own loop ends with
                            // `if (pending.trim()) consumeLine(pending)` and
                            // this port left it out. Against the plain-token
                            // (non-SSE) upstream this file's own header
                            // describes - one that streams words with no
                            // newlines at all - EVERY token landed in
                            // `lineBuf`, `acc` stayed empty, and `send`
                            // returned "" with no error: a blank reply on
                            // screen and a voice loop that said nothing.
                            if (lineBuf.isNotEmpty()) handle(lineBuf.toString())
                            break
                        }
                        if (n == 0) continue
                        var start = 0
                        for (i in 0 until n) {
                            if (chunk[i] != '\n') continue
                            lineBuf.append(chunk, start, i - start)
                            start = i + 1
                            val line = lineBuf.toString()
                            lineBuf.setLength(0)
                            if (handle(line)) break@readLoop
                        }
                        if (start < n) lineBuf.append(chunk, start, n - start)
                    }
                    // The last line is almost always inside the throttle
                    // window, so without this the tail of every reply would be
                    // missing from the screen until the next message.
                    publish(force = true)
                    // Captured before anything else can replace the shared
                    // flow, so the caller gets its own answer rather than
                    // whatever is in there when it happens to look. Not set on
                    // [ChatChunkParser.Result.Failed]: that is an in-band error
                    // from the chunk itself, the same kind of failure the
                    // 401/403/404 branch above reports by leaving `mine` null.
                    if (!failed) {
                        mine = acc.toString()
                        cutShort = framed && !ended
                    }
                    if (call === c) {
                        _waiting.value = null
                        _answerNote.value = listOfNotNull(
                            if (cutShortAtLimit && !failed && acc.isNotBlank()) {
                                "Cut short: it reached the length limit. Ask \"go on\" for the rest."
                            } else {
                                null
                            },
                            if (cloud && !failed) "Answered by a cloud model, not on your PC." else null,
                            if (secondCard != null && !cloud && !failed) SecondCard.routeNote(secondCard) else null,
                            if (quick && !failed) Schedule.DONE_LINE_HERE else null,
                        ).plus(temporaryNotes).joinToString(" ").ifEmpty { null }
                    }
                }
            } catch (ce: CancellationException) {
                throw ce
            } catch (t: Throwable) {
                // A cancelled call lands here too. That is the interrupt
                // working, not a failure, so it is not reported as one.
                if (c.isCanceled()) {
                    Log.d(TAG, "chat interrupted by the user")
                } else {
                    Log.w(TAG, "chat failed", t)
                    failWith(
                        PlainErrors.forInput(
                            PlainErrors.Input(network = PlainErrors.networkKind(t)),
                            "${t::class.java.simpleName}: ${t.message.orEmpty()}",
                        ),
                    )
                }
            } finally {
                // Nothing left to cancel on; the read is over either way.
                closer.cancel()
                // Only when this call is still the current one.
                //
                // `send` begins by cancelling the previous call, and the loser
                // then unwinds into THIS block. Without the identity check it
                // cleared the WINNER's handle and streaming flag on its way
                // out: the new reply streamed in with the composer showing
                // "Send" rather than "Stop", the voice button re-enabled
                // mid-generation, and `cancel()` had a null handle — so the
                // generation could no longer be interrupted at all.
                if (call === c) {
                    _streaming.value = false
                    _waiting.value = null
                    call = null
                }
            }
        }
        // Only a finished, non-empty answer joins the conversation, and only
        // the conversation it was asked in. `update` rather than building
        // on `earlier`: a call that finished in the meantime has already
        // added its own pair, and this one goes after it.
        val answer = mine
        // Jarvis Live's side talk: shown as "(not for Jarvis)", never kept.
        if (live && com.jarvis.client.voice.LiveRules.isSideTalk(answer)) {
            // Only while no newer question has started.
            if (call == null) {
                _reply.value = com.jarvis.client.voice.LiveRules.SEEN.getValue("not_for_me")
            }
            return mine
        }
        if (answer != null && answer.isNotBlank() && !cutShort && conversation == askedIn &&
            ChatHistory.keepsInThread(crisisTurn)
        ) {
            _history.update { ChatHistory.commit(it, asking, answer) }
            _thread.update { ChatHistory.addToThread(it, asking, answer) }
            lastTurnAt = System.currentTimeMillis()
        }
        return mine
    }

    /** Interrupts generation. Safe to call when nothing is in flight. */
    fun cancel() {
        call?.cancel()
        call = null
        _streaming.value = false
    }

    /**
     * Starts afresh: stops any answer still arriving, forgets the
     * conversation, and clears the question and answer on screen. The next
     * question goes to the desktop on its own, as the very first one did.
     *
     * Only the phone's copy is forgotten. The PC's own record of the chat
     * (chat history, docs/JARVIS-API.md section 18) is kept there until it
     * is deleted from History; the next question starts a NEW conversation
     * there, under a new [conversationId]. What the PC has LEARNED (memory,
     * and cards waiting for review) is a different thing again, and this
     * does not touch it.
     */
    fun newConversation() {
        conversation++
        conversationId = ChatHistory.newConversationId()
        lastTurnAt = 0L
        _chatNote.value = null
        _game.value = false
        _readOutside.value = false
        cancel()
        _history.value = emptyList()
        _thread.value = emptyList()
        _reply.value = ""
        _question.value = null
        _turnId.value = null
        _error.value = null
        _problem.value = null
        lastAsked = null
        _waiting.value = null
        _answerNote.value = null
        _usedIds.value = emptyList()
        _crisis.value = false
        _openSettings.value = null
        _cloudOffer.value = null
    }

    /**
     * "Continue this chat" (from History) and Jarvis Live's "Move it here"
     * (the owner's decisions, 2026-09-28): Home carries on a kept
     * conversation - the SAME conversation id, so the PC files what follows
     * with it and its "read outside text" mark carries over (the PC decides
     * that from its own record) - with [window] as the conversation so far
     * ([ChatHistory.continueWindow]: the newest kept messages that fit).
     * What was on screen goes, as with [newConversation]; [note] is said in
     * its place. False for an id the PC could never have made.
     */
    fun continueFrom(
        id: String,
        window: List<ChatHistory.Exchange>,
        note: String?,
        readOutside: Boolean = false,
    ): Boolean {
        if (!ChatHistory.validConversationId(id)) return false
        newConversation()
        conversationId = id
        _history.value = window
        _thread.value = window
        _readOutside.value = readOutside
        lastTurnAt = System.currentTimeMillis()
        _chatNote.value = note
        return true
    }

    /**
     * Chats deleted elsewhere - Delete in History, "Erase the words" with
     * its chat, "Forget a time frame" approved, deleting a chat and the facts
     * it taught (section 79). When Home is IN one of them, its old words
     * must stop going to the model and the PC must not bring the chat back
     * under a new title (the chat audit, 2026-09-28, phone B2): a new
     * conversation, and Home says why. True when that happened.
     */
    fun chatsGone(ids: Collection<String>): Boolean {
        if (conversationId !in ids) return false
        val had = _history.value.isNotEmpty() || _question.value != null
        newConversation()
        if (had) _chatNote.value = ChatHistory.CHAT_GONE
        return had
    }

    /**
     * "Try again" under a failed question: the same words, with the same tag
     * and shared text, as a new [send]. False when there is nothing to ask
     * again (a new conversation was started since).
     */
    suspend fun retryLast(): Boolean {
        val (message, provenance, shared) = lastAsked ?: return false
        send(message, provenance = provenance, shared = shared)
        return true
    }

    /**
     * The owner's yes to [CloudOffer]'s "Try the cloud model" - the same
     * shape as [retryLast]: the same words, tag and shared text, as a new
     * [send], this time with `cloudYes = true`. A genuinely new turn, not a
     * replacement - the old answer stays on screen until this one streams
     * in over it, same as any other question. False when there is nothing
     * to ask again (a new conversation was started since the offer, or the
     * owner already moved on to a different question).
     */
    suspend fun tryCloudForLast(): Boolean {
        val (message, provenance, shared) = lastAsked ?: return false
        send(message, provenance = provenance, shared = shared, cloudYes = true)
        return true
    }

    private companion object {
        const val TAG = "JarvisChat"

        /** What each `: jarvis-status` word means on screen. */
        val WAITING = mapOf(
            "approval" to PlainErrors.STATUSES.getValue("approval"),
            "working" to PlainErrors.STATUSES.getValue("working"),
            // The PC says the model is not in memory yet (after standby):
            // the first words take longer, and the owner is told why.
            "loading" to PlainErrors.STATUSES.getValue("loading"),
        )

        /**
         * How much of a failed response body to look at, in bytes.
         *
         * A backend error is a sentence. Anything larger than this is a stack
         * trace or an HTML error page from something in between, neither of
         * which belongs on a phone screen - and reading it in full would mean
         * buffering an unbounded body to render one line of it.
         */
        const val ERROR_BODY_MAX = 4L * 1024

        /** Longest server sentence shown, in characters. */
        const val ERROR_DETAIL_MAX = 300

        /**
         * The one useful sentence out of a failed response, or null.
         *
         * `peekBody` rather than `body.string()`: it copies out of the buffer
         * and leaves the body itself untouched, so this cannot interfere with
         * anything downstream that still expects to read it.
         *
         * FastAPI's own error shape is `{"detail": "..."}`, so that is tried
         * first; `error` and `message` cover the rest of what this backend and
         * its proxies emit. A body that is not JSON is used as-is, which is
         * what a plain-text 503 from a reverse proxy looks like. HTML is
         * dropped outright - a whole error PAGE has no sentence in it worth
         * pulling out by hand.
         */
        fun serverDetail(resp: Response): String? {
            val raw = runCatching { resp.peekBody(ERROR_BODY_MAX).string() }
                .getOrNull()?.trim().orEmpty()
            if (raw.isEmpty() || raw.startsWith("<")) return null

            val fromJson = runCatching {
                val obj = Json.parseToJsonElement(raw) as? JsonObject
                obj?.let {
                    (it["detail"] as? JsonPrimitive)?.contentOrNull
                        ?: (it["message"] as? JsonPrimitive)?.contentOrNull
                        ?: ((it["error"] as? JsonObject)?.get("message") as? JsonPrimitive)
                            ?.contentOrNull
                        ?: (it["error"] as? JsonPrimitive)?.contentOrNull
                }
            }.getOrNull()

            val text = (fromJson ?: raw).replace(Regex("\\s+"), " ").trim()
            if (text.isEmpty()) return null
            return if (text.length <= ERROR_DETAIL_MAX) {
                text
            } else {
                text.take(ERROR_DETAIL_MAX - 1).trimEnd() + "…"
            }
        }

        /** Characters per read now, not bytes - see the decode note in [send]. */
        const val CHUNK = 8 * 1024

        /**
         * Slowest the reply is allowed to visibly grow, in milliseconds. Small
         * enough that generation still looks like typing; large enough that a
         * fast local model cannot make the UI publish a fresh copy of the whole
         * reply for every token.
         */
        const val PUBLISH_MS = 50L
    }
}
