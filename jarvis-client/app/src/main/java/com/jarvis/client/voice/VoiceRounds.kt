package com.jarvis.client.voice

import com.jarvis.client.net.Approvals
import com.jarvis.client.net.VoiceStrict

/**
 * "Train my voice" in rounds: which rounds to record, what to send for each,
 * and what to say - with no Android in it, so `VoiceRoundsTest` checks every
 * decision against the PC's real answers.
 *
 * THE OWNER'S DECISION (2026-09-24). Balanced keeps today's training: one
 * round of the 12 sentences. Very strict gets "extended training": the same
 * 12 sentences three times, in three conditions - close and normal; further
 * away or quieter; another time or another room - because very strict holds
 * the voice to a higher bar, and a print made in one place turns the owner
 * away in the others. Each round goes to the PC as it is finished and is
 * HELD there, in memory, with no card; the last one is sent with `finish`,
 * and ONE approval card covers them all. Cancel drops everything, here and
 * on the PC.
 *
 * "Train more" adds recordings to the print already there (`add: true`) -
 * one round, in whichever condition Jarvis struggles with. And when the PC
 * leaves some recordings out because they did not sound like the rest, it
 * says which (round, clip); "record them again" records exactly those,
 * added to the print.
 *
 * An older PC (no `gate.training.rounds`) gets today's single round, sent
 * the old way - it would not understand anything else.
 */
object VoiceRounds {

    /** What kind of training this is. It decides the words and the body. */
    enum class Kind {
        /** An older PC: one round, `{"clips": [...]}`, as before. */
        SINGLE_OLD,

        /** Balanced: one round, replacing the print. */
        SINGLE,

        /** Very strict: three rounds, replacing the print. */
        EXTENDED,

        /** "Train more": one round added to the print. */
        MORE,

        /** "Record them again": the clips the PC left out, added to the print. */
        REDO,
    }

    /**
     * One round: its number on the wire (1..the PC's condition count, which
     * is also the condition the PC files it under) and which of [Plan.phrases]
     * to read, by index, in order. Clip n of the round is `phrases[n - 1]` -
     * which is how the PC's "round 2, clip 5" is turned back into a sentence.
     */
    data class Round(val number: Int, val sentences: List<Int>)

    /**
     * What sending one round came to. [accepted]: the PC took it (holding
     * it, or with a card up). [finished]: that was the last round and the
     * card is up. [heldElsewhere]: the PC is holding another training, which
     * Cancel can delete.
     */
    data class Result(
        val accepted: Boolean,
        val message: String,
        val finished: Boolean = false,
        val heldElsewhere: Boolean = false,
    )

    data class Plan(
        val kind: Kind,
        val rounds: List<Round>,
        /** The PC's balanced read phrases, word for word; the old 12 when it sent none. */
        val phrases: List<String> = VoiceTraining.SENTENCES,
    ) {
        val add: Boolean get() = kind == Kind.MORE || kind == Kind.REDO
        val total: Int get() = rounds.sumOf { it.sentences.size }
    }

    /** The condition each round is recorded in, in the PC's words when the PC gave them. */
    val DEFAULT_ASKS: Map<Int, String> = mapOf(
        1 to "normal, close to the microphone",
        2 to "about two to three metres away, on a table",
        3 to "with the fan or the TV on, as it usually is",
        4 to "in another room, or at a different time of day",
    )

    /** The PC's balanced phrases, or today's twelve when the PC sent none (an older PC). */
    fun phrases(view: VoiceStrict.View): List<String> =
        view.readPhrases.ifEmpty { VoiceTraining.SENTENCES }

    /** How many condition rounds this PC asks for (four in the merged contract; 3 on an older one). */
    fun roundCount(view: VoiceStrict.View): Int =
        view.conditions.size.takeIf { it > 0 }
            ?: view.limits.rounds.coerceIn(1, 8).takeIf { it > 0 }
            ?: 3

    /**
     * The first training (or a fresh one, replacing the print): one round per
     * condition the PC asks for (four in the merged contract) when the PC is
     * very strict and understands rounds, one otherwise.
     */
    fun plan(view: VoiceStrict.View): Plan {
        val phrases = phrases(view)
        val all = phrases.indices.toList()
        val count = roundCount(view)
        return when {
            !view.rounds -> Plan(Kind.SINGLE_OLD, listOf(Round(1, all)), phrases)
            view.isVeryStrict -> Plan(Kind.EXTENDED, (1..count).map { Round(it, all) }, phrases)
            else -> Plan(Kind.SINGLE, listOf(Round(1, all)), phrases)
        }
    }

    /** "Train more", in condition [round] (1..the PC's condition count). Null on a PC that cannot add. */
    fun more(view: VoiceStrict.View, round: Int): Plan? {
        val phrases = phrases(view)
        val all = phrases.indices.toList()
        return if (view.rounds && round in 1..roundCount(view)) {
            Plan(Kind.MORE, listOf(Round(round, all)), phrases)
        } else {
            null
        }
    }

    /**
     * "Record them again": exactly the clips the PC left out of an approved
     * training ([last]'s outliers), turned back into sentences through
     * [sent] - the plan this phone last sent - and added to the print.
     *
     * A round needs at least [minClips] clips (the PC refuses fewer), so a
     * round with one or two left-out clips is topped up with the sentences
     * that follow them. Null when there is nothing to redo, when the PC
     * cannot add, or when this phone does not know what it sent (the app
     * was restarted, or the training came from elsewhere): then "which
     * sentence was clip 5?" has no honest answer.
     */
    fun redo(
        view: VoiceStrict.View,
        last: VoiceStrict.Last?,
        sent: Plan?,
        minClips: Int = view.limits.minClips,
    ): Plan? {
        // Only after an approved training: a failed one saved nothing to add to.
        val outliers = last?.takeIf { it.outcome == "enrolled" }?.outliers.orEmpty()
        if (!view.rounds || sent == null || outliers.isEmpty()) return null
        val rounds = outliers.groupBy { it.round }.toSortedMap().mapNotNull { (number, rows) ->
            val round = sent.rounds.firstOrNull { it.number == number } ?: return null
            val picked = rows.mapNotNull { round.sentences.getOrNull(it.clip - 1) }.distinct()
            if (picked.size != rows.map { it.clip }.distinct().size) return null
            val topped = picked.toMutableList()
            // Topped up from the same round's own sentences, in order after
            // the last picked one, wrapping round.
            val order = round.sentences.let { s ->
                val from = s.indexOf(picked.last()) + 1
                s.drop(from) + s.take(from)
            }
            for (i in order) {
                if (topped.size >= minClips.coerceAtLeast(1)) break
                if (i !in topped) topped += i
            }
            Round(number, topped)
        }
        return if (rounds.isEmpty()) null else Plan(Kind.REDO, rounds, sent.phrases)
    }

    /**
     * The body for round number [index] (0-based) of [plan]: `finish` on the
     * last, so the PC raises its ONE card then. An older PC gets the old
     * one-shot body.
     */
    fun body(plan: Plan, index: Int, clips: List<ByteArray>, mic: String): String {
        val round = plan.rounds[index]
        return if (plan.kind == Kind.SINGLE_OLD) {
            com.jarvis.client.net.enrollRequestBody(clips, mic = mic)
        } else {
            VoiceStrict.trainBody(round.number, clips, mic, add = plan.add, finish = index == plan.rounds.lastIndex)
        }
    }

    fun isLast(plan: Plan, index: Int): Boolean = index == plan.rounds.lastIndex

    /**
     * Whether sending round [index] of [plan] raises the approval card: the
     * last round of the plan (it carries `finish`), which for a one-round
     * plan - balanced, "train more", an older PC's one-shot [Kind.SINGLE_OLD]
     * - is its only round. Only that round is held on a stale link (rule 4:
     * a card raised against a stream this phone cannot confirm is live).
     * The rounds before it are only held in memory on the PC, raise no card
     * and change nothing, so they always go - the same as the desktop, which
     * holds only `finish` and the old one-shot body
     * (voice_training.rs, `send_voice_training`).
     */
    fun raisesCard(plan: Plan, index: Int): Boolean = isLast(plan, index)

    /**
     * Before sending round [index] (> 0) of [plan]: are the rounds before it
     * still held on the PC ([session], just read)? It drops them 15 minutes
     * after the last one arrived - and a round sent after that would start a
     * NEW training with only itself in it, so the card would cover one round
     * while the owner thinks it covers three. Null when all is well, or the
     * sentence saying what happened.
     */
    fun lostRounds(plan: Plan, index: Int, session: VoiceStrict.Session?): String? {
        if (index <= 0 || plan.kind == Kind.SINGLE_OLD) return null
        val want = plan.rounds.take(index).map { it.number }.toSet()
        val have = session?.takeIf { it.add == plan.add }?.rounds?.map { it.round }?.toSet().orEmpty()
        return if (have.containsAll(want)) {
            null
        } else {
            "Your PC is no longer holding the earlier rounds - it deletes them 15 minutes after " +
                "the last one arrives. Nothing changed. Start the training again."
        }
    }

    /**
     * An unfinished training the PC is holding that this screen can pick up:
     * the plan to continue, and which round index is next. Only an ordinary
     * three-round training from this phone - "train more" and "record
     * again" hold sentences this screen cannot know after a restart.
     */
    fun resume(view: VoiceStrict.View, mic: String): Pair<Plan, Int>? {
        val s = view.session ?: return null
        if (!view.rounds || s.add || s.mic != mic) return null
        val held = s.rounds.map { it.round }.toSet()
        val count = roundCount(view)
        val next = (1..count).firstOrNull { it !in held } ?: return null
        val phrases = phrases(view)
        return Plan(Kind.EXTENDED, (1..count).map { Round(it, phrases.indices.toList()) }, phrases) to (next - 1)
    }

    /** The unfinished training the PC holds, in words, or null. */
    fun unfinishedLine(view: VoiceStrict.View): String? {
        val s = view.session ?: return null
        val rounds = s.rounds.map { it.round }.sorted()
        if (rounds.isEmpty()) return null
        val which = if (rounds.size == 1) "round ${rounds[0]}" else "rounds " + rounds.joinToString(" and ")
        return "Your PC is holding an unfinished training ($which, ${s.clips} recordings) in its " +
            "memory. It deletes them by itself 15 minutes after the last round arrived."
    }

    // -------------------------------------------------------------- words --

    fun ask(view: VoiceStrict.View, round: Int): String =
        view.conditions.getOrNull(round - 1)?.ask?.takeIf { it.isNotBlank() }
            ?: view.roundAsks[round]
            ?: DEFAULT_ASKS[round].orEmpty()

    /** The heading over a round's sentences. */
    fun roundTitle(plan: Plan, index: Int, view: VoiceStrict.View): String {
        val r = plan.rounds[index]
        return when (plan.kind) {
            Kind.EXTENDED -> "Round ${index + 1} of ${plan.rounds.size}: ${ask(view, r.number)}"
            Kind.MORE -> "More recordings: ${ask(view, r.number)}"
            Kind.REDO -> "Record again: " + ask(view, r.number)
            Kind.SINGLE, Kind.SINGLE_OLD -> "Read each sentence in your normal voice"
        }
    }

    /** The first screen's words, for [plan]. [view] gives the PC's own condition words. */
    fun intro(plan: Plan, view: VoiceStrict.View? = null): String = when (plan.kind) {
        Kind.EXTENDED -> {
            val count = plan.rounds.size
            val places = view?.conditions.orEmpty().mapNotNull {
                it.ask.ifBlank { it.label }.takeIf { w -> w.isNotBlank() }
            }
            val where = if (places.size == count) {
                " in ${count} places: " + places.joinToString("; ") + "."
            } else {
                " in $count places, each in a different condition."
            }
            "Your voice check is very strict, so Jarvis needs to hear you in more than one " +
                "place. Read the same ${plan.phrases.size} short sentences $count times$where " +
                "It takes about ${count * 2} minutes, and you can do the rounds at different " +
                "times within 15 minutes of each other."
        }
        Kind.MORE ->
            "Add recordings to the voice Jarvis already knows, in one place it struggles " +
                "with. Nothing it has now is deleted."
        Kind.REDO ->
            "Your PC left some recordings out because they did not sound like the rest. " +
                "Record those sentences again and they are added to your voice."
        Kind.SINGLE, Kind.SINGLE_OLD -> VoiceTraining.INTRO
    }

    /** What happens to the recordings, for [plan]. */
    fun introDetail(plan: Plan): String = when (plan.kind) {
        Kind.EXTENDED ->
            "Each round is kept in your PC's memory until the last one is sent, then ONE " +
                "approval card asks you to finish. Nothing changes until you approve it. The " +
                "recordings are deleted from this phone as soon as each round is sent, and " +
                "from the PC once the card is answered. Cancel deletes them everywhere."
        Kind.MORE, Kind.REDO ->
            "Sending raises one approval card. Nothing changes until you approve it, and " +
                "the recordings are deleted from this phone as soon as they are sent."
        Kind.SINGLE, Kind.SINGLE_OLD -> VoiceTraining.INTRO_DETAIL
    }

    /** The send button's label for round [index]. */
    fun sendLabel(plan: Plan, index: Int): String = when {
        plan.kind == Kind.EXTENDED && !isLast(plan, index) -> "Send round ${index + 1} to your PC"
        plan.kind == Kind.EXTENDED -> "Send the last round and finish"
        else -> "Send to your PC"
    }

    /** What to show after a round was held (no card yet). The PC's own sentence first. */
    fun heldLine(answer: VoiceStrict.Answer, plan: Plan, index: Int): String {
        val next = index + 2
        val left = plan.rounds.size - index - 1
        return answer.message.ifBlank {
            "Round ${index + 1} is kept on your PC, in memory only. " +
                (if (left > 0) "Next: round $next. " else "") +
                "Nothing changes until you finish and approve the card."
        }
    }

    /** After the last round: a card is up. */
    fun finishedLine(answer: VoiceStrict.Answer): String =
        answer.message.ifBlank { "Sent. A card is waiting to finish it." }.let {
            if (it.contains("Approve", ignoreCase = true)) it else "$it " + Approvals.WHERE
        }

    /**
     * The left-out recordings, in plain words, with the sentences named -
     * or null when there are none. [sent] turns clip numbers back into
     * sentences; without it the line says only how many.
     */
    fun outliersLine(last: VoiceStrict.Last?, sent: Plan?): String? {
        val rows = last?.outliers.orEmpty()
        // A failed training saved nothing: there is nothing to add to, and
        // the last-training line already gives the PC's reason and advice.
        if (rows.isEmpty() || last?.outcome != "enrolled") return null
        val n = rows.size
        val head = (if (n == 1) "Your PC left out 1 recording" else "Your PC left out $n recordings") +
            " because ${if (n == 1) "it" else "they"} did not sound like the rest"
        val named = rows.mapNotNull { o ->
            val idx = sent?.rounds?.firstOrNull { it.number == o.round }?.sentences?.getOrNull(o.clip - 1)
                ?: return@mapNotNull null
            val round = if ((sent.rounds.size) > 1) "round ${o.round}, " else ""
            "$round\"${sent.phrases[idx]}\""
        }
        return if (named.size == n) "$head: ${named.joinToString("; ")}." else "$head."
    }

    /**
     * Why "Send" cannot be pressed for a round, or null. [linkBlocker] (the
     * runtime's `actionBlocker()`) holds only the round that raises the card
     * ([raisesCard]); an earlier round of a three-round training goes on a
     * stale link, since the PC only keeps it in memory.
     */
    fun sendBlocker(
        plan: Plan,
        index: Int,
        recorded: Int,
        seconds: Float,
        linkBlocker: String?,
        limits: VoiceStrict.Limits = VoiceStrict.Limits(),
    ): String? {
        val need = plan.rounds[index].sentences.size
        return when {
            linkBlocker != null && raisesCard(plan, index) -> linkBlocker
            recorded < need -> "Record all $need sentences first ($recorded done)."
            seconds > limits.maxTotalSeconds ->
                "The recordings are ${seconds.toInt()} seconds in all; the most is " +
                    "${limits.maxTotalSeconds.toInt()}. Redo the longest ones a little quicker."
            else -> null
        }
    }

    /** What Cancel says it does, before it does it. */
    const val CANCEL_NOTE =
        "Cancel deletes every recording made so far - on this phone, and the rounds your PC " +
            "is holding. Nothing about your voice changes."

    /** After a cancel, from the PC's answer. */
    fun cancelledLine(answer: VoiceStrict.Answer?): String = when {
        answer == null -> "Cancelled. The recordings on this phone were deleted."
        answer.error.isNotBlank() -> "Cancelled on this phone. Your PC said: " + sentence(answer.error)
        else -> "Cancelled. " + answer.message.ifBlank { "The recordings were deleted." }
    }

    /**
     * A 409 because another training is being held on the PC (from another
     * microphone, or with `add` different): the PC's words, plus what can be
     * done here.
     */
    fun otherSessionLine(answer: VoiceStrict.Answer): String? {
        if (answer.code != 409 || answer.session == null) return null
        return sentence(answer.error) + " Tap Cancel to delete what your PC is holding and start again."
    }

    /** The PC's fragment as a sentence: first letter raised, a full stop at the end. */
    fun sentence(s: String): String {
        val t = s.trim()
        if (t.isEmpty()) return t
        val raised = t.replaceFirstChar { it.uppercase() }
        return if (raised.last() in ".!?") raised else "$raised."
    }
}
