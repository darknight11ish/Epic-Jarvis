package com.jarvis.client.net

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * What the phone holds of ONE look at its screen - in memory only, never
 * written anywhere, never synced (the owner's decision of 2026-09-28,
 * docs/SCREEN-DESIGN.md sections 3 and 4).
 *
 * - "Look at this" (the assistant gesture): the words of the screen, held for
 *   [FOLLOW_UP_MS] of follow-up questions, then dropped - or at once when the
 *   owner taps "Forget it". A look that was taken while Jarvis was locked
 *   (App lock) waits for the unlock and is dropped after [LOCKED_WAIT_MS]
 *   if it was never shown.
 * - "Watch with me" (the phone's screen sharing): one picture, held for the
 *   ONE question it was taken for ([Held.consume]), never longer than
 *   [FOLLOW_UP_MS]. The picture goes only to the PC, over the private link,
 *   inside that question.
 *
 * `ChatSession.send` asks [forQuestion] for every question, so the look
 * rides with whatever the owner asks next - typed, said, or after "Hey
 * Jarvis" - and nothing else can put screen words in a message.
 *
 * No Android in this file: the JVM tests hold every rule with a clock they
 * move by hand ([com.jarvis.client.ScreenTextTest]).
 */
object ScreenLook {
    const val FOLLOW_UP_MS = 120_000L
    const val LOCKED_WAIT_MS = 60_000L

    /** Milliseconds, monotonic. The tests replace it; the app leaves it. */
    @Volatile var clock: () -> Long = { System.nanoTime() / 1_000_000L }

    /** What the chip above the chat box says, from the app's name. */
    fun note(app: String, picture: Boolean = false): String =
        "Looked at: $app screen · " + (if (picture) "picture goes to your PC only" else "words only")

    /** The words the phone is holding, or a picture, for one question. */
    data class Held(
        val app: String,
        val words: String,
        val picture: String?,
        val at: Long,
        val shown: Boolean,
        /** A Watch-with-me picture belongs to the ONE question it was taken for. */
        val consume: Boolean,
    )

    /**
     * What one question carries of the held look ([ChatHistory.messages]):
     * the screen's [words] as a `screen_text` part of their own, and whether
     * the picture in the message is the screen's ([pictureIsScreen] - the PC
     * then reads its WORDS and never shows any model the picture).
     */
    data class Attach(val words: String?, val pictureIsScreen: Boolean)

    /** [Held] as what a message carries. Words for a look, the picture for a Watch picture. */
    fun attach(h: Held): Attach =
        Attach(words = h.words.takeIf { h.picture == null }, pictureIsScreen = h.picture != null)

    @Volatile private var held: Held? = null
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private var expiry: Job? = null

    private val _line = MutableStateFlow<String?>(null)

    /** The chip's line while a look is held, else null. Words about the look, never its words. */
    val line: StateFlow<String?> = _line.asStateFlow()

    /** Is [h] still worth holding at [now]? */
    fun alive(h: Held, now: Long): Boolean {
        val age = now - h.at
        if (age < 0 || age > FOLLOW_UP_MS) return false
        return h.shown || age <= LOCKED_WAIT_MS
    }

    /**
     * Holds one look. A new look replaces the last one. [shown]: the chip is
     * already on screen (the app was unlocked).
     */
    @Synchronized
    fun hold(
        app: String,
        words: String,
        picture: String? = null,
        shown: Boolean = true,
        consume: Boolean = picture != null,
    ) {
        val name = app.trim().ifEmpty { "your screen" }
        val h = Held(name, words, picture, clock(), shown, consume)
        held = h
        _line.value = note(name, picture != null)
        arm(h)
    }

    /** Drops [h] when its time is up - a new look or a "shown" re-arms this. */
    private fun arm(h: Held) {
        expiry?.cancel()
        val wait = (if (h.shown) FOLLOW_UP_MS else LOCKED_WAIT_MS) - (clock() - h.at)
        expiry = scope.launch {
            delay(if (wait > 0) wait else 0L)
            synchronized(this@ScreenLook) { if (held === h) drop() }
        }
    }

    /** The chip is on screen (the app is unlocked): the look may live its two minutes. */
    @Synchronized
    fun shown() {
        val h = held ?: return
        if (!alive(h, clock())) {
            drop()
            return
        }
        if (h.shown) return
        val next = h.copy(shown = true)
        held = next
        arm(next)
    }

    /** The held look for the next question, or null. A picture is used up by it. */
    @Synchronized
    fun forQuestion(): Held? {
        val h = held ?: return null
        if (!alive(h, clock())) {
            drop()
            return null
        }
        if (h.consume) drop()
        return h
    }

    /** Is a look held (and still alive) now? */
    @Synchronized
    fun isHeld(): Boolean {
        val h = held ?: return false
        if (!alive(h, clock())) {
            drop()
            return false
        }
        return true
    }

    /** "Forget it", the end of a follow-up window, Stop everything: thrown away now. */
    @Synchronized
    fun drop() {
        held = null
        expiry?.cancel()
        expiry = null
        _line.value = null
    }

    /** For the tests: everything gone, the real clock back. */
    @Synchronized
    fun resetForTests() {
        drop()
        clock = { System.nanoTime() / 1_000_000L }
    }
}
