package com.jarvis.client

import com.jarvis.client.voice.PrivateAloud
import com.jarvis.client.voice.SpeechAhead
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Making the next sentence's sound while the current one plays
 * (SpeechAhead, used by VoiceSession): the next one is asked for before the
 * current one ends, only one ahead, and a sound made ahead is dropped - never
 * played - when "stop" is said, the turn is cancelled, or the answer turns
 * private while that sound was being made.
 *
 * Every test runs on one thread (runBlocking), and every wait is a `delay`
 * of a different length, so the order of what happens is fixed: coroutines'
 * timers fire in deadline order however busy the machine is.
 */
class SpeechAheadTest {

    private val on = PrivateAloud.ON_SCREEN

    /** A pretend PC and speaker that write down what happened, in order. */
    private class Fake(val askMs: Long = 30, val playMs: Long = 100) {
        val log = mutableListOf<String>()
        var asking = 0
        var mostAskingAtOnce = 0
        var private = false
        var stopped = false

        /** Runs when a sentence's sound has been made, before it is handed back. */
        var afterAsk: (String) -> Unit = {}

        /** Runs part-way through playing a sentence. */
        var whilePlaying: (String) -> Unit = {}

        fun ahead() = SpeechAhead<String>(
            mayRead = { !private },
            stopped = { stopped },
            fetch = { text ->
                log += "ask $text"
                asking += 1
                mostAskingAtOnce = maxOf(mostAskingAtOnce, asking)
                try {
                    delay(askMs)
                } finally {
                    asking -= 1
                }
                afterAsk(text)
                "sound of $text"
            },
            play = { text, clip ->
                assertEquals("sound of $text", clip)
                log += "play $text"
                delay(playMs / 2)
                whilePlaying(text)
                delay(playMs / 2)
                log += "end $text"
            },
        )

        fun played(): List<String> = log.filter { it.startsWith("play ") }.map { it.removePrefix("play ") }
        fun asked(): List<String> = log.filter { it.startsWith("ask ") }.map { it.removePrefix("ask ") }
    }

    private fun speakAll(fake: Fake, vararg sentences: String) = runBlocking {
        val queue = Channel<String>(Channel.UNLIMITED)
        sentences.forEach { queue.trySend(it) }
        queue.close()
        fake.ahead().speak(queue)
    }

    @Test
    fun `CONTROL - every sentence is played, in order`() {
        val fake = Fake()
        speakAll(fake, "One.", "Two.", "Three.")
        assertEquals(listOf("One.", "Two.", "Three."), fake.played())
        assertEquals(listOf("One.", "Two.", "Three."), fake.asked())
    }

    @Test
    fun `the next sentence's sound is asked for before the current one ends`() {
        val fake = Fake()
        speakAll(fake, "One.", "Two.", "Three.")
        val log = fake.log
        assertTrue(log.toString(), log.indexOf("ask Two.") < log.indexOf("end One."))
        assertTrue(log.toString(), log.indexOf("ask Two.") > log.indexOf("play One."))
        assertTrue(log.toString(), log.indexOf("ask Three.") < log.indexOf("end Two."))
        // No gap: Two starts the moment One ends, its sound already made.
        assertEquals(log.indexOf("end One.") + 1, log.indexOf("play Two."))
    }

    @Test
    fun `only one ahead - never two sounds being made at once`() {
        val fake = Fake(askMs = 30, playMs = 200)
        speakAll(fake, "One.", "Two.", "Three.", "Four.")
        assertEquals(1, fake.mostAskingAtOnce)
        val log = fake.log
        // Three is asked for only once Two is playing, not while One plays.
        assertTrue(log.toString(), log.indexOf("ask Three.") > log.indexOf("play Two."))
        assertTrue(log.toString(), log.indexOf("ask Four.") > log.indexOf("play Three."))
    }

    @Test
    fun `sentences still being written are asked for as they arrive, while one plays`() {
        val fake = Fake(askMs = 30, playMs = 200)
        runBlocking {
            val queue = Channel<String>(Channel.UNLIMITED)
            launch {
                queue.send("One.")
                delay(60) // the model writes the second sentence while One plays
                queue.send("Two.")
                queue.close()
            }
            fake.ahead().speak(queue)
        }
        assertEquals(listOf("One.", "Two."), fake.played())
        assertTrue(fake.log.toString(), fake.log.indexOf("ask Two.") < fake.log.indexOf("end One."))
    }

    @Test
    fun `stop while one plays - the sound made ahead is dropped, nothing more is asked for`() {
        val fake = Fake()
        fake.whilePlaying = { if (it == "One.") fake.stopped = true }
        speakAll(fake, "One.", "Two.", "Three.")
        assertEquals(listOf("One."), fake.played())
        assertFalse(fake.asked().toString(), "Three." in fake.asked())
    }

    @Test
    fun `stop while the next sound is being made - it arrives and is not played`() {
        val fake = Fake(askMs = 30, playMs = 20)
        fake.afterAsk = { if (it == "Two.") fake.stopped = true }
        speakAll(fake, "One.", "Two.", "Three.")
        assertEquals(listOf("One."), fake.played())
        assertTrue("Two." in fake.asked())
        assertFalse("Three." in fake.asked())
    }

    @Test
    fun `stop before anything is asked - nothing is asked for at all`() {
        val fake = Fake()
        fake.stopped = true
        speakAll(fake, "One.", "Two.")
        assertEquals(emptyList<String>(), fake.log)
    }

    @Test
    fun `the answer turns private while the next sound is made - checked again before playing, dropped`() {
        val fake = Fake()
        // A tool starts while Two's sound is being made: Two was allowed when
        // it was asked for, and is not by the time it would play.
        fake.afterAsk = { if (it == "Two.") fake.private = true }
        speakAll(fake, "One.", "Two.", "Three.")
        assertEquals(listOf("One.", on), fake.played())
        assertFalse("Three." in fake.asked())
    }

    @Test
    fun `private from the start - only the fixed line, once`() {
        val fake = Fake()
        fake.private = true
        speakAll(fake, "Your dentist is on Tuesday.", "At ten.")
        assertEquals(listOf(on), fake.played())
        assertEquals(listOf(on), fake.asked())
    }

    @Test
    fun `turns private while one plays - the fixed line is made ahead, and said after it`() {
        val fake = Fake()
        fake.whilePlaying = { if (it == "One.") fake.private = true }
        runBlocking {
            val queue = Channel<String>(Channel.UNLIMITED)
            launch {
                queue.send("One.")
                delay(100) // Two arrives after the tool started (at 80 ms), while One still plays
                queue.send("Two.")
                queue.send("Three.")
                queue.close()
            }
            fake.ahead().speak(queue)
        }
        assertEquals(listOf("One.", on), fake.played())
        assertFalse("Two." in fake.asked())
    }

    @Test
    fun `cancelling the turn drops the sound being made ahead`() {
        val fake = Fake(askMs = 80, playMs = 100)
        runBlocking {
            val queue = Channel<String>(Channel.UNLIMITED)
            listOf("One.", "Two.", "Three.").forEach { queue.trySend(it) }
            val job = launch { fake.ahead().speak(queue) }
            delay(150) // One is playing, Two's sound is being made
            job.cancel()
            job.join()
            delay(300)
        }
        assertEquals(listOf("One."), fake.played())
        assertFalse("Three." in fake.asked())
    }
}
