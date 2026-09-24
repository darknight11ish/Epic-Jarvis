package com.jarvis.client.voice

import kotlinx.coroutines.Deferred
import kotlinx.coroutines.async
import kotlinx.coroutines.channels.ReceiveChannel
import kotlinx.coroutines.coroutineScope

/**
 * Speaks a voice answer sentence by sentence, and makes the NEXT sentence's
 * sound while the current one plays.
 *
 * Before, the phone asked the PC for a sentence's sound (`/api/voice/say`)
 * only once the sentence before it had finished playing, so between any two
 * sentences there was a silence as long as the PC took to make the second
 * one - about 1-4 s on the PC's processor (the voice research of 2026-09-24
 * measured 3.5 s of silence in a three-sentence answer, and 0 s with this).
 *
 * The rules, in order:
 *
 *  - **One ahead, never more.** The next sentence's sound is asked for only
 *    once the current one's has arrived and is about to play, so the PC is
 *    making at most one sentence's sound at a time for this answer.
 *  - **The private-answer rule is asked twice** ([mayRead], the phone's
 *    [PrivateAloud.mayRead] with the tool watch as it is at that moment):
 *    before the sound is asked for, and again right before it is PLAYED. A
 *    tool can start, or the event stream drop, while the sound is being made;
 *    then that sound is thrown away unplayed and the one fixed line
 *    ([privateLine]) is said instead, once, and nothing more of the answer.
 *  - **"Stop" wins** ([stopped], the turn's own `silenced` flag): nothing is
 *    asked for after it, and a sound that arrives after it is never played.
 *    A cancelled turn (the "hey Jarvis" interruption, slide-away) cancels
 *    this too, and a sound made ahead is dropped with it.
 *
 * Generic in the sound ([C]) so it has no Android in it: `SpeechAheadTest`.
 */
class SpeechAhead<C>(
    /** May this answer be read aloud, as far as the phone knows right now? */
    private val mayRead: () -> Boolean,
    /** "Stop" was said this turn: nothing more is asked for or played. */
    private val stopped: () -> Boolean,
    /** Asks the PC for one sentence's sound. */
    private val fetch: suspend (String) -> C,
    /** Plays one sentence's sound, returning once it has finished (or was stopped). */
    private val play: suspend (String, C) -> Unit,
    /** What is said instead of a private answer. */
    private val privateLine: String = PrivateAloud.ON_SCREEN,
) {

    /** One sentence with its sound already made; [isPrivateLine] when it is [privateLine]. */
    private class Line<C>(val text: String, val clip: C, val isPrivateLine: Boolean)

    /**
     * Speaks what arrives on [sentences], in order, until it is closed and
     * empty, "stop" is said, or the answer turns out to be private.
     */
    suspend fun speak(sentences: ReceiveChannel<String>) {
        coroutineScope {
            // The sentence about to play. Nothing is playing yet, so asking
            // for the first one's sound now is still only one request.
            var ahead: Deferred<Line<C>?> = async { next(sentences) }
            try {
                while (true) {
                    val line = ahead.await() ?: break
                    // Asked again right before playing: "stop" may have been
                    // said while this sound was being made.
                    if (stopped()) break
                    if (line.isPrivateLine) {
                        play(line.text, line.clip)
                        break
                    }
                    // ...and the private-answer rule, too: a tool may have
                    // started, or the event stream dropped, since this
                    // sentence's sound was asked for. Its sound is dropped.
                    if (!mayRead()) {
                        sayPrivateLine()
                        break
                    }
                    // One ahead: the next sentence's sound is made while this
                    // one plays - and only now, so there is never a second
                    // request in flight.
                    ahead = async { next(sentences) }
                    play(line.text, line.clip)
                    if (stopped()) break
                }
            } finally {
                // Whatever was being made ahead is not wanted any more: the
                // answer ended, turned private, or "stop" was said.
                ahead.cancel()
            }
        }
    }

    /**
     * Waits for the next sentence and makes its sound. Null when nothing more
     * is to be said: the answer is over, or "stop" was said. The private line
     * instead of the sentence when the answer may not be read aloud.
     */
    private suspend fun next(sentences: ReceiveChannel<String>): Line<C>? {
        val sentence = sentences.receiveCatching().getOrNull() ?: return null
        if (stopped()) return null
        if (!mayRead()) return Line(privateLine, fetch(privateLine), isPrivateLine = true)
        return Line(sentence, fetch(sentence), isPrivateLine = false)
    }

    private suspend fun sayPrivateLine() {
        if (stopped()) return
        val clip = fetch(privateLine)
        if (stopped()) return
        play(privateLine, clip)
    }
}
