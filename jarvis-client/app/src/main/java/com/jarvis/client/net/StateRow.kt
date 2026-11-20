package com.jarvis.client.net

/**
 * One settings row, computed as a WHOLE: the switch's position and the
 * sentence drawn beside it. THE ROW CANNOT DISAGREE WITH ITSELF, because both
 * fields come from one read.
 *
 * WHY THIS EXISTS (the 2026-11-18 settings audit, `PHONE-STATE-DRIFT.md`).
 * The audit found phone switches whose TICK and SENTENCE disagree, because two
 * independent readers fed one row: the tick from the state read plus the
 * approval queue, the sentence from the state read alone. Two of the worst are
 * fixed through this type:
 *
 *  - Background learning: `learning == false` with an ON card waiting drew a
 *    TICKED switch over `MemoryCounts.learningLine(false)` - its own sentence
 *    saying "Background learning is off". (PHONE-STATE-DRIFT.md 3.1)
 *  - Hands-free: a read that never arrived (`read == null`) drew title, switch
 *    and sentence as a definite "Hands-free is off". (PHONE-STATE-DRIFT.md 3.3)
 *
 * THE RULE, in one sentence: a row is drawn only in a state it can prove - on
 * and off are a real `checked` position with words that say the same thing,
 * WAITING is the position that was ASKED FOR with words saying it is only
 * waiting, and UNKNOWN is `checked == null` with words saying it could not be
 * told, and no switch drawn at all (a null position is never painted as off).
 *
 * WHAT `checked == null` MEANS. Not false, and not true: the PC has not
 * answered, so no position is known. The UI half is `SwitchRow`'s nullable
 * `checked` (see `ui/screens/AppearanceScreen.kt`): a null position draws no
 * switch and makes the row untappable, so "could not ask" can never read as
 * "off". That is the project's own rule, written in `VoiceSwitchesPlate.kt`:
 * "The desktop has not answered, so this is not known. It is not being
 * reported as off, because \"off\" and \"could not ask\" are not the same thing
 * and only one of them is safe to believe."
 *
 * WHAT IS NOT COVERED. This file is pure Kotlin (no Compose, no Android), so
 * `StateRowTest` can hold the data half on the JVM - which is the half the
 * desktop bug lives in. That the composable passes `row.checked` AND
 * `row.words` to the same `SwitchRow` call is held by a source pin in the same
 * test file: this repository has no Compose UI test host
 * (`R8SourcePinTest.kt` says so), so no JVM test here renders a Compose
 * switch. The emulator smoke job is what draws one.
 *
 * @param checked the switch's position, or null when it is not known.
 * @param words the ONE sentence the owner reads for this row's state.
 * @param enabled whether the control may be pressed here at all. False with a
 *   null [checked] (nothing to press), and false while a write is in flight.
 */
data class RowView(
    val checked: Boolean?,
    val words: String,
    val enabled: Boolean,
) {
    /** Is the switch's position known? Unknown is a state, not a position. */
    val known: Boolean get() = checked != null
}

/**
 * What a row's sentence SAYS its state is - the invariant `StateRow.agrees`
 * holds the data half to, in both directions (see [says]).
 *
 * It is deliberately a reading of the exact strings the screen draws, not a
 * separate field a caller could get out of step with: if a mapper returns
 * `checked = true` with a sentence that reads "off", the test fails.
 */
object StateRow {

    /** The five things a sentence can say about a row's state. */
    enum class Said {
        /** "... is on": the switch is on, and the words say so. */
        ON,

        /** "... is off": the switch is off, and the words say so. */
        OFF,

        /** "Waiting for your approval...": the ON ask is on a card. */
        WAITING,

        /** "Couldn't tell...", "has not answered...": the PC did not answer. */
        UNKNOWN,

        /** A description with no state claim in it (e.g. "Hands-free is not available on this PC yet."). */
        NO_CLAIM,
    }

    /**
     * What [words] says, read from the same strings the screens draw.
     *
     * Order matters, and is the rule: WAITING and UNKNOWN are read BEFORE the
     * on/off phrases, because "Couldn't tell whether background learning is
     * on." contains " is on" and must never be read as on; and a leading
     * "On."/"Off." is read before the contains-checks, because the automatic
     * learning ON sentence carries the caveat "Background learning is off, so
     * nothing is saved automatically..." - the row's own opening word is the
     * state claim, and the caveat is about a different switch.
     */
    fun says(words: String): Said {
        val w = words.trim()
        return when {
            w.startsWith("Waiting for your approval") -> Said.WAITING
            w.startsWith("Couldn't tell") -> Said.UNKNOWN
            w.startsWith("Could not read") -> Said.UNKNOWN
            w.startsWith("Your PC has not answered") -> Said.UNKNOWN
            w.startsWith("The desktop has not answered") -> Said.UNKNOWN
            w.startsWith("On.") || w.startsWith("On,") -> Said.ON
            w.startsWith("Off.") || w.startsWith("Off,") -> Said.OFF
            w.contains(" is off") -> Said.OFF
            w.contains(" is on") -> Said.ON
            else -> Said.NO_CLAIM
        }
    }

    /**
     * Does this row contradict itself? The ONE assertion every family is held
     * to - the same question the desktop bug would have failed:
     *
     *  - ON and OFF say the position the switch shows;
     *  - WAITING says the position that was ASKED for (true), because turning
     *    it off is how the request is taken back - never a plain off;
     *  - UNKNOWN is never a position: checked must be null;
     *  - NO_CLAIM claims nothing, so nothing can contradict it.
     */
    fun agrees(row: RowView): Boolean = when (says(row.words)) {
        Said.ON -> row.checked == true
        Said.OFF -> row.checked == false
        Said.WAITING -> row.checked == true
        Said.UNKNOWN -> row.checked == null
        Said.NO_CLAIM -> true
    }
}

/**
 * The learning family: background learning (the switch that raised the audit's
 * finding A) and the three automatic-learning switches under it. One mapper
 * for the family, because they share the two-reader shape (`AutoLearn`'s four
 * states already say what the PC answered) and one wording rule.
 */
object LearningRow {

    /**
     * Background learning, from the ONE state read plus the approval queue.
     *
     * The queue is the second reader, and it only ever means WAITING: while the
     * ON card is up the row shows the position that was asked for (`true`) and
     * says "waiting" - it does NOT fall back to `learningLine(false)`, which
     * was the audit's "tick beside its own off sentence". A waiting row can
     * still be turned off, which takes the request back.
     *
     * @param learning the PC's own answer (`JarvisRuntime.memoryLearning()`),
     *   null when it did not answer.
     * @param cardWaiting is the ON card in the approval queue.
     * @param canAct whether the link can carry a write now (ON is held on a
     *   stale link, rule 4; OFF is not).
     * @param busy a write for this row is in flight.
     */
    fun background(
        learning: Boolean?,
        cardWaiting: Boolean,
        canAct: Boolean,
        busy: Boolean = false,
    ): RowView {
        val checked = when {
            learning == true -> true
            cardWaiting -> true
            learning == false -> false
            else -> null
        }
        val words = when {
            learning == true -> MemoryCounts.learningLine(true)
            cardWaiting -> MemoryCounts.waitingLine()
            learning == false -> MemoryCounts.learningLine(false)
            else -> MemoryCounts.learningLine(null)
        }
        val enabled = !busy && when {
            checked == true -> true
            checked == false -> canAct
            else -> false
        }
        return RowView(checked, words, enabled)
    }

    /**
     * One of the automatic-learning switches. [switch] is the four-state read
     * `AutoLearn.switchState` already makes from the PC's answer and the queue;
     * this mapper is the projection that cannot pair a tick with the wrong
     * sentence - UNKNOWN draws no position and says "Couldn't tell".
     *
     * @param autoOn the "Learn automatically" state, which the two dependent
     *   switches' sentences name; null when the PC did not answer.
     * @param busy a write for ANY of the three is in flight (the plate holds
     *   all three while one is being written, as before).
     */
    fun auto(
        which: AutoLearn.Which,
        switch: AutoLearn.Switch,
        learningOn: Boolean?,
        autoOn: Boolean?,
        canAct: Boolean,
        busy: Boolean = false,
    ): RowView {
        val checked = when (switch) {
            AutoLearn.Switch.ON -> true
            AutoLearn.Switch.OFF -> false
            AutoLearn.Switch.WAITING -> true
            AutoLearn.Switch.UNKNOWN -> null
        }
        val words = AutoLearn.stateLine(which, switch, learningOn, autoOn)
        val enabled = !busy && when (switch) {
            AutoLearn.Switch.ON, AutoLearn.Switch.WAITING -> true
            AutoLearn.Switch.OFF -> canAct
            AutoLearn.Switch.UNKNOWN -> false
        }
        return RowView(checked, words, enabled)
    }
}

/**
 * The hands-free row (the audit's finding C): a read that never arrived is
 * UNKNOWN, never a definite "Hands-free is off".
 *
 * The words are the PC's own sentence when it sent one (`why`), else this
 * app's state sentence. A 404 is handled before this mapper by
 * `JarvisRuntime.handsfreeMissing` and stays `Handle.NOT_HERE`; a body that
 * says `available: false` is the same "this PC does not have it", and is not
 * drawn as off either.
 */
object HandsfreeRow {

    /**
     * @param read the PC's answer, or null when it has not answered.
     * @param canAct the link can carry a write now (ON waits for that).
     * @param busy a write is in flight.
     */
    fun of(read: Handsfree.Read?, canAct: Boolean, busy: Boolean = false): RowView = when {
        read == null -> RowView(null, Handsfree.UNKNOWN, false)
        !read.available -> RowView(null, Handsfree.NOT_HERE, false)
        read.enabled -> RowView(true, read.why ?: Handsfree.ON_DONE, !busy)
        else -> RowView(false, read.why ?: Handsfree.OFF_DONE, !busy && canAct)
    }
}

/**
 * Chat history (the audit's third MISMATCH-WIDGET row, same two-reader shape as
 * the learning switches): `status` is the PC's answer, the queue carries the ON
 * card. UNKNOWN is `checked == null` with the "Couldn't tell" sentence - it used
 * to be an unticked switch beside the same sentence.
 */
object ChatHistoryRow {

    /**
     * @param switch the four-state read `ChatLog.switchState` already makes.
     * @param status the PC's answer, for the sentence.
     * @param canAct the link can carry a write now (ON waits for that).
     * @param busy a write is in flight.
     */
    fun of(
        switch: ChatLog.Switch,
        status: ChatLog.Status?,
        canAct: Boolean,
        busy: Boolean = false,
    ): RowView {
        val checked = when (switch) {
            ChatLog.Switch.ON -> true
            ChatLog.Switch.OFF -> false
            ChatLog.Switch.WAITING -> true
            ChatLog.Switch.UNKNOWN -> null
        }
        // WAITING keeps its switch where the ask was made, so it can be turned
        // off to take the request back; it is held here only by `busy`, not by
        // the waiting state itself.
        val enabled = !busy && when (switch) {
            ChatLog.Switch.ON -> true
            ChatLog.Switch.OFF -> canAct
            ChatLog.Switch.WAITING, ChatLog.Switch.UNKNOWN -> false
        }
        return RowView(checked, ChatLog.stateLine(switch, status), enabled)
    }
}
