package com.jarvis.client

import com.jarvis.client.net.AutoLearn
import com.jarvis.client.net.ChatHistoryRow
import com.jarvis.client.net.ChatLog
import com.jarvis.client.net.Handsfree
import com.jarvis.client.net.HandsfreeRow
import com.jarvis.client.net.LearningRow
import com.jarvis.client.net.MemoryCounts
import com.jarvis.client.net.RowView
import com.jarvis.client.net.StateRow
import com.jarvis.client.net.StateRow.Said
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * THE ONE TEST SHAPE that catches "a ticked switch beside its own off
 * sentence" (the 2026-11-18 settings audit, `.dsh-scratch/wave21/settings-audit/
 * PHONE-STATE-DRIFT.md`), for every family that had the shape:
 *
 *  - background learning and the automatic-learning switches ([LearningRow]),
 *  - hands-free ([HandsfreeRow]),
 *  - chat history ([ChatHistoryRow]).
 *
 * The rule held here, once, for all of them: `StateRow.agrees(row)` says the
 * switch's position and the sentence beside it can never contradict - ON and
 * OFF name the position, WAITING names the position that was asked for, and
 * UNKNOWN is `checked == null`, never a painted-off switch.
 *
 * WHAT THIS FILE CANNOT COVER, said plainly: there is no Compose UI test host
 * in this repository (`R8SourcePinTest.kt` records why - `androidTestImplementation`
 * has no `ui-test-junit4`), so no JVM test here renders a `SwitchRow`. The
 * wiring half - that each plate hands ONE row's `checked` AND `words` to the
 * same switch call - is held by source pins at the bottom, reading the shipped
 * Kotlin like the audit did. The emulator smoke job draws the real screen.
 */
class StateRowTest {

    // ---------------------------------------------------------------------
    // The classifier, and the invariant it feeds
    // ---------------------------------------------------------------------

    @Test
    fun `a sentence is read as the state it names`() {
        // ON and OFF come from the mappers' own words; the setting is named or
        // the sentence opens with On./Off. (the auto-learning and chat rows).
        assertEquals(Said.ON, StateRow.says(MemoryCounts.learningLine(true)))
        assertEquals(Said.OFF, StateRow.says(MemoryCounts.learningLine(false)))
        assertEquals(Said.ON, StateRow.says(Handsfree.ON_DONE))
        assertEquals(Said.OFF, StateRow.says(Handsfree.OFF_DONE))
        assertEquals(Said.ON, StateRow.says("On. New chats are kept on your PC, encrypted."))
        assertEquals(Said.OFF, StateRow.says("Off. Every fact Jarvis learns waits for your yes, as a card."))
        assertEquals(Said.ON, StateRow.says("On, but nothing new is being kept right now."))
    }

    @Test
    fun `waiting and unknown are read before on or off, because they contain the same words`() {
        // "Couldn't tell whether background learning is on." contains " is on".
        // If the classifier read on/off first, the audit's own fixture would
        // pass as ON - which is the bug wearing a test's clothes.
        assertEquals(Said.UNKNOWN, StateRow.says(MemoryCounts.learningLine(null)))
        assertEquals(Said.UNKNOWN, StateRow.says(Handsfree.UNKNOWN))
        assertEquals(Said.UNKNOWN, StateRow.says("Couldn't tell whether chat history is on."))
        assertEquals(Said.WAITING, StateRow.says(MemoryCounts.waitingLine()))
        assertEquals(Said.WAITING, StateRow.says(AutoLearn.waitingLine(AutoLearn.Which.AUTO)))
        assertEquals(Said.WAITING, StateRow.says(ChatLog.WAITING))
        // "Hands-free is not available on this PC yet." claims no state at all.
        assertEquals(Said.NO_CLAIM, StateRow.says(Handsfree.NOT_HERE))
        // The opening word is the row's OWN state claim, read before the
        // contains-checks: an ON auto-learning sentence carries the caveat
        // "Background learning is off, so nothing is saved automatically...",
        // and reading the caveat as the row's state would draw ON as OFF.
        assertEquals(
            Said.ON,
            StateRow.says(
                AutoLearn.stateLine(
                    AutoLearn.Which.AUTO,
                    AutoLearn.Switch.ON,
                    learningOn = false,
                    autoOn = true,
                ),
            ),
        )
    }

    @Test
    fun `the invariant fails the old shape of the audit's worst finding`() {
        // Finding A, drawn before this fix: the ON card is waiting, so the
        // ticked switch showed `learning == true || cardWaiting` and the row's
        // own detail showed `learningLine(learning)` - ticked over its own
        // "Background learning is off". That pair is exactly what the invariant
        // rejects, so this shape can never come back unseen.
        assertFalse(
            "a ticked switch over the off sentence must fail the invariant",
            StateRow.agrees(
                RowView(
                    checked = true,
                    words = MemoryCounts.learningLine(false),
                    enabled = true,
                ),
            ),
        )
    }

    // ---------------------------------------------------------------------
    // ON / OFF / WAITING / UNKNOWN, one table per family
    // ---------------------------------------------------------------------

    private data class Case(
        val name: String,
        val row: RowView,
        val said: Said,
        val checked: Boolean?,
        val enabled: Boolean,
    )

    @Test
    fun `every family draws ON OFF WAITING and UNKNOWN without ever contradicting itself`() {
        val chatStatusOn = ChatLog.Status(
            enabled = true, recording = true, whyNot = null,
            waiting = false, keepDays = 30, encrypted = true,
        )
        val chatStatusOff = chatStatusOn.copy(enabled = false, recording = false)
        val handsfreeOn = Handsfree.Read(available = true, enabled = true)
        val handsfreeOff = Handsfree.Read(available = true, enabled = false)

        val cases = listOf(
            // Background learning: `learning` is the PC's answer, the second
            // reader is the approval queue.
            Case("learning on", LearningRow.background(true, false, canAct = true), Said.ON, true, true),
            Case("learning off", LearningRow.background(false, false, canAct = true), Said.OFF, false, true),
            Case(
                "learning waiting",
                LearningRow.background(false, cardWaiting = true, canAct = true),
                Said.WAITING, true, true,
            ),
            Case(
                "learning unknown",
                LearningRow.background(null, false, canAct = true),
                Said.UNKNOWN, null, false,
            ),
            // The three automatic-learning switches: AutoLearn's four-state
            // read, projected with its own sentence.
            Case(
                "auto on",
                LearningRow.auto(
                    AutoLearn.Which.AUTO, AutoLearn.Switch.ON,
                    learningOn = true, autoOn = true, canAct = true,
                ),
                Said.ON, true, true,
            ),
            Case(
                "auto off",
                LearningRow.auto(
                    AutoLearn.Which.AUTO, AutoLearn.Switch.OFF,
                    learningOn = true, autoOn = false, canAct = true,
                ),
                Said.OFF, false, true,
            ),
            Case(
                "auto waiting",
                LearningRow.auto(
                    AutoLearn.Which.SENSITIVE, AutoLearn.Switch.WAITING,
                    learningOn = true, autoOn = true, canAct = true,
                ),
                Said.WAITING, true, true,
            ),
            Case(
                "auto unknown",
                LearningRow.auto(
                    AutoLearn.Which.PARAPHRASE, AutoLearn.Switch.UNKNOWN,
                    learningOn = true, autoOn = true, canAct = true,
                ),
                Said.UNKNOWN, null, false,
            ),
            // Hands-free: the read is the whole state; null is no answer.
            Case("handsfree on", HandsfreeRow.of(handsfreeOn, canAct = true), Said.ON, true, true),
            Case("handsfree off", HandsfreeRow.of(handsfreeOff, canAct = true), Said.OFF, false, true),
            Case("handsfree unknown", HandsfreeRow.of(null, canAct = true), Said.UNKNOWN, null, false),
            Case(
                "handsfree not on this PC",
                HandsfreeRow.of(Handsfree.Read(available = false, enabled = false), canAct = true),
                Said.NO_CLAIM, null, false,
            ),
            // Chat history: the PC's answer plus the ON card in the queue.
            Case("chat on", ChatHistoryRow.of(ChatLog.Switch.ON, chatStatusOn, canAct = true), Said.ON, true, true),
            Case("chat off", ChatHistoryRow.of(ChatLog.Switch.OFF, chatStatusOff, canAct = true), Said.OFF, false, true),
            Case(
                "chat waiting",
                ChatHistoryRow.of(ChatLog.Switch.WAITING, chatStatusOff, canAct = true),
                Said.WAITING, true, false,
            ),
            Case("chat unknown", ChatHistoryRow.of(ChatLog.Switch.UNKNOWN, null, canAct = true), Said.UNKNOWN, null, false),
        )

        for (c in cases) {
            assertEquals("${c.name}: what the sentence says", c.said, StateRow.says(c.row.words))
            assertEquals("${c.name}: the switch's position", c.checked, c.row.checked)
            assertEquals("${c.name}: whether it can be pressed", c.enabled, c.row.enabled)
            assertTrue(
                "${c.name}: the switch and its own sentence disagree - checked=${c.row.checked} " +
                    "words=\"${c.row.words}\"",
                StateRow.agrees(c.row),
            )
            // The audit's rule in one line: a row in a waiting or unknown state
            // is never drawn as a plain off.
            if (c.said == Said.WAITING || c.said == Said.UNKNOWN) {
                assertFalse(
                    "${c.name}: a ${c.said} row was drawn as a plain off",
                    c.row.checked == false,
                )
            }
        }
    }

    // ---------------------------------------------------------------------
    // The audit's own failing fixtures
    // ---------------------------------------------------------------------

    @Test
    fun `finding A - learning off while its ON card waits is WAITING, not a tick beside its off line`() {
        // The measured fixture: (learning = false, cardWaiting = true).
        val row = LearningRow.background(false, cardWaiting = true, canAct = true)
        assertEquals("the switch shows the position that was asked for", true, row.checked)
        assertEquals(MemoryCounts.waitingLine(), row.words)
        assertEquals(Said.WAITING, StateRow.says(row.words))
        assertFalse(
            "the row's detail fell back to the off sentence - finding A is back",
            row.words.contains("Background learning is off"),
        )
        assertFalse("a waiting row must never be a plain off", row.checked == false)
        assertTrue(StateRow.agrees(row))
    }

    @Test
    fun `finding A - a failed learning read is UNKNOWN, not an unticked off`() {
        val row = LearningRow.background(null, cardWaiting = false, canAct = true)
        assertNull("a read that did not arrive must draw no position", row.checked)
        assertFalse("and it must not be pressable", row.enabled)
        assertEquals(Said.UNKNOWN, StateRow.says(row.words))
        assertEquals(MemoryCounts.learningLine(null), row.words)
        assertTrue(StateRow.agrees(row))
    }

    @Test
    fun `finding C - a hands-free read that never arrived is UNKNOWN, not off`() {
        val row = HandsfreeRow.of(null, canAct = true)
        assertNull("a read that did not arrive must draw no position", row.checked)
        assertFalse("and it must not be pressable", row.enabled)
        assertEquals(Handsfree.UNKNOWN, row.words)
        assertFalse(
            "the words claimed the mode is off - finding C is back",
            row.words.contains("Hands-free is off"),
        )
        assertFalse("a read that did not arrive must not say ' is off'", row.words.contains(" is off"))
        assertEquals(Said.UNKNOWN, StateRow.says(row.words))
        assertTrue(StateRow.agrees(row))
    }

    @Test
    fun `a known state still says on and off in the project's own sentences`() {
        val on = HandsfreeRow.of(Handsfree.Read(available = true, enabled = true), canAct = true)
        assertEquals(true, on.checked)
        assertEquals(Handsfree.ON_DONE, on.words)
        assertTrue(StateRow.agrees(on))

        val off = HandsfreeRow.of(Handsfree.Read(available = true, enabled = false), canAct = true)
        assertEquals(false, off.checked)
        assertEquals(Handsfree.OFF_DONE, off.words)
        assertTrue(StateRow.agrees(off))

        // The PC's own sentence about its state wins over the app's fallback,
        // exactly as the plate drew it before.
        val said = HandsfreeRow.of(
            Handsfree.Read(available = true, enabled = true, why = "Hands-free is on for this phone."),
            canAct = true,
        )
        assertEquals("Hands-free is on for this phone.", said.words)
        assertTrue(StateRow.agrees(said))
    }

    // ---------------------------------------------------------------------
    // The class, not just the fixtures: no input combination can disagree
    // ---------------------------------------------------------------------

    @Test
    fun `no combination of readings can produce a row that contradicts itself`() {
        val chatOn = ChatLog.Status(
            enabled = true, recording = true, whyNot = null,
            waiting = false, keepDays = 30, encrypted = true,
        )
        val chatOff = chatOn.copy(enabled = false, recording = false)
        val chatWaiting = chatOff.copy(waiting = true)
        val chatNotRecording = chatOn.copy(recording = false, whyNot = "the store is read-only")

        val rows = buildList {
            for (learning in listOf<Boolean?>(true, false, null)) {
                for (waiting in listOf(true, false)) {
                    for (canAct in listOf(true, false)) {
                        for (busy in listOf(true, false)) {
                            add(
                                "learning/$learning/$waiting/$canAct/$busy" to
                                    LearningRow.background(learning, waiting, canAct, busy),
                            )
                        }
                    }
                }
            }
            for (which in AutoLearn.Which.entries) {
                for (switch in AutoLearn.Switch.entries) {
                    for (learningOn in listOf<Boolean?>(true, false, null)) {
                        for (autoOn in listOf<Boolean?>(true, false, null)) {
                            for (canAct in listOf(true, false)) {
                                for (busy in listOf(true, false)) {
                                    add(
                                        "auto/${which.name}/${switch.name}/$learningOn/$autoOn/$canAct/$busy" to
                                            LearningRow.auto(which, switch, learningOn, autoOn, canAct, busy),
                                    )
                                }
                            }
                        }
                    }
                }
            }
            for (read in listOf(
                null,
                Handsfree.Read(available = true, enabled = true),
                Handsfree.Read(available = true, enabled = false),
                Handsfree.Read(available = false, enabled = false),
            )) {
                for (canAct in listOf(true, false)) {
                    for (busy in listOf(true, false)) {
                        add("handsfree/$read/$canAct/$busy" to HandsfreeRow.of(read, canAct, busy))
                    }
                }
            }
            for (switch in ChatLog.Switch.entries) {
                for (status in listOf(null, chatOn, chatOff, chatWaiting, chatNotRecording)) {
                    for (canAct in listOf(true, false)) {
                        for (busy in listOf(true, false)) {
                            add(
                                "chat/${switch.name}/$status/$canAct/$busy" to
                                    ChatHistoryRow.of(switch, status, canAct, busy),
                            )
                        }
                    }
                }
            }
        }

        assertTrue("the table built no rows, so it checks nothing", rows.size > 500)
        for ((name, row) in rows) {
            assertTrue(
                "$name: the switch and its own sentence disagree - checked=${row.checked} " +
                    "words=\"${row.words}\"",
                StateRow.agrees(row),
            )
            if (row.checked == null) {
                assertFalse("$name: a row with no known position must not be pressable", row.enabled)
                val said = StateRow.says(row.words)
                assertTrue(
                    "$name: a row with no known position must say so in words (said $said): " +
                        "\"${row.words}\"",
                    said == Said.UNKNOWN || said == Said.NO_CLAIM,
                )
            }
        }
    }

    // ---------------------------------------------------------------------
    // The wiring half - a source pin, because there is no Compose UI test host
    // ---------------------------------------------------------------------

    /** Walks up from Gradle's working folder (`jarvis-client/app`) to the repository. */
    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private fun text(rel: String): String = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/$rel").readText()

    @Test
    fun `learning plate draws ONE row - the mapper's position and the mapper's sentence`() {
        val plate = text("ui/screens/LearningSettingsPlate.kt")
        assertTrue(
            "the background row no longer comes from its mapper",
            "val row = LearningRow.background(" in plate,
        )
        assertTrue("the tick is not the mapper's position", "checked = row.checked," in plate)
        assertTrue("the sentence is not the mapper's sentence", "detail = row.words," in plate)
        assertFalse(
            "the old two-reader expression is back: the tick came from the state read OR the queue",
            "learning == true || cardWaiting" in plate,
        )
    }

    @Test
    fun `hands-free plate draws ONE row - the mapper's position and the mapper's sentence`() {
        val plate = text("ui/screens/HandsfreeSection.kt")
        assertTrue("val row = HandsfreeRow.of(" in plate)
        assertTrue("the tick is not the mapper's position", "checked = row.checked," in plate)
        assertTrue("the sentence is not the mapper's sentence", "detail = row.words," in plate)
        assertFalse(
            "the plate claims off whenever the mode is not armed - the read that never arrived " +
                "was drawn as a definite off (finding C)",
            "if (armed) Handsfree.ON else Handsfree.OFF" in plate,
        )
    }

    @Test
    fun `automatic-learning rows draw ONE row - the mapper's position and the mapper's sentence`() {
        val plate = text("ui/screens/AutoLearnPlate.kt")
        assertTrue("val row = LearningRow.auto(" in plate)
        assertTrue("the tick is not the mapper's position", "checked = row.checked," in plate)
        assertTrue("the sentence is not the mapper's sentence", "row.words" in plate)
        assertFalse(
            "the old projection is back: UNKNOWN was drawn as an unticked off",
            "checked = switch == AutoLearn.Switch.ON || switch == AutoLearn.Switch.WAITING" in plate,
        )
    }

    @Test
    fun `chat-history row draws ONE row - the mapper's position and the mapper's sentence`() {
        val plate = text("ui/screens/HistoryScreen.kt")
        assertTrue("val row = ChatHistoryRow.of(" in plate)
        assertTrue("the tick is not the mapper's position", "checked = row.checked," in plate)
        assertTrue("the sentence is not the mapper's sentence", "row.words" in plate)
        assertFalse(
            "the old projection is back: an UNKNOWN was drawn as an unticked off",
            "checked = switch == ChatLog.Switch.ON" in plate,
        )
    }

    @Test
    fun `the shared switch draws nothing at all when the position is not known`() {
        val row = repoFile(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/AppearanceScreen.kt",
        ).readText()
        assertTrue(
            "SwitchRow no longer takes a NULLABLE position: a null state would have to be " +
                "painted as on or off",
            "checked: Boolean?" in row,
        )
        assertTrue(
            "the row is not gated on a known position - an unknown state could be drawn as a switch",
            "if (checked != null)" in row,
        )
        assertTrue(
            "the switch is not drawn only when the position is known",
            "checked?.let { position ->" in row,
        )
    }
}
