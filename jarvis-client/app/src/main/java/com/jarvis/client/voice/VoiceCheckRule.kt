package com.jarvis.client.voice

/**
 * The phone's half of the ONE voice-check rule (the owner, 2026-11-03).
 *
 * The owner's words: *"my voice should only need to be confirmed if i say hi
 * jarvis when the phone is locked ... when i start jarvis live on my unlocked
 * phone i dont want it to need to confirm my voice. make this a setting i can
 * change"*.
 *
 * THE RULE ITSELF IS THE PC'S - `jarvis_live.voice_check_needed()` in
 * `backend/jarvis_live.py`, one function, and the PC runs the speaker model.
 * This object is the phone's copy of the same decision, and it exists for the
 * one thing only the phone knows: whether ITS OWN screen is locked. It is held
 * to the Python side row for row by [VoiceCheckRuleTest], so the two cannot
 * drift apart.
 *
 *  - [MIC_PRESS]: pressing the mic for one verbal input NEVER checks, whatever
 *    the setting says. (The PC's `_is_quick_message` is the enforcement; the
 *    phone only sends `source=push_to_talk`, which it already did.)
 *  - [WAKE_WORD]: "hi Jarvis" on a LOCKED phone checks - the only check left.
 *  - [LIVE_START]: starting Jarvis Live from an UNLOCKED phone does not check.
 *
 * THE SETTING, and which way OFF points. ON is the rule above - the EXEMPTION
 * for an unlocked phone. OFF withdraws the exemption and gives back the OLD,
 * FULL CHECKS: the phone's "I am unlocked" is then IGNORED and every trigger
 * left checks exactly as it did before 2026-11-03. OFF is never "no checks":
 * withdrawing an exemption must not quietly weaken a gate, and a screen-lock
 * reading is a claim by this phone, not a permission the owner granted.
 * [MIC_PRESS] is the one trigger the setting does not touch. The PC is the
 * one that decides, and its copy is `jarvis_live.voice_check_needed()`.
 *
 * WHAT THE PHONE DOES WITH IT. It never decides a check or skips one: the PC
 * does. The phone's job is to SAY whether its screen was locked, so the PC can
 * apply the rule. [lockedField] carries that one fact on the existing Live
 * start route; a phone that cannot read its own lock state sends nothing, and
 * the PC then keeps every check it has today (fail closed on the PC's side,
 * `locked is not False`). An app older than this file sends nothing either, so
 * nothing about an old phone changes.
 *
 * THE SETTING is read and written through the SAME existing route
 * (`POST /api/voice/live` with `{"do":"voice_check"}`), never a new one:
 * [body] with no value reads it, with a value asks. ON is 202 while ONE
 * approval card waits on the PC; OFF is at once.
 */
object VoiceCheckRule {

    const val MIC_PRESS = "mic_press"
    const val WAKE_WORD = "wake_word"
    const val LIVE_START = "live_start"

    /** The route's own command name: `POST /api/voice/live {"do":"voice_check"}`. */
    const val DO = "voice_check"

    /** The setting's default on the PC: ON, the owner's requested rule. */
    const val DEFAULT_ON = true

    /**
     * Does this trigger check the owner's voice print? The PC's answers, in
     * the PC's order.
     *
     * [phoneLocked] is this phone's own screen lock: true/false, or null when
     * it cannot be read. Null is NEVER "unlocked" - it keeps the check, which
     * is both the safe answer and exactly what an older phone gets.
     *
     * [settingOn] is `voice_check_locked`, ON by default. Turning it OFF is
     * the OLD, full checks - see the note on this object: the setting is the
     * exemption, so withdrawing it must not weaken anything.
     */
    fun checks(trigger: String, phoneLocked: Boolean?, settingOn: Boolean = DEFAULT_ON): Boolean =
        when {
            // (a) The press on the paired phone IS the act: never a check, and
            // the setting has nothing to say about it.
            trigger == MIC_PRESS -> false
            // OFF: the old, full checks, with the phone's word ignored.
            !settingOn -> true
            // (c) Live started on an unlocked phone: the unlock is the act.
            trigger == LIVE_START -> phoneLocked != false
            // (b) "hi Jarvis" - a LOCKED phone checks, the only check left.
            trigger == WAKE_WORD -> phoneLocked != false
            // An unknown trigger is not this phone's to exempt: keep the check.
            else -> true
        }

    /**
     * The `"locked":true|false` field for the Live start body, or "" when this
     * phone does not know. Written by hand with no JSON library: the body is
     * the one string [LiveRules.startBody] already builds from fixed words.
     */
    fun lockedField(phoneLocked: Boolean?): String = when (phoneLocked) {
        true -> ",\"locked\":true"
        false -> ",\"locked\":false"
        null -> ""
    }

    /**
     * The `POST /api/voice/live` body for the one setting. A null [enabled]
     * READS it (the PC answers with its value and words); true/false ask.
     */
    fun body(enabled: Boolean?): String = when (enabled) {
        true -> "{\"do\":\"$DO\",\"enabled\":true}"
        false -> "{\"do\":\"$DO\",\"enabled\":false}"
        null -> "{\"do\":\"$DO\"}"
    }

    /** The switch's state out of the PC's answer, or null when it did not say. */
    fun on(answer: kotlinx.serialization.json.JsonObject?): Boolean? =
        (answer?.get("on") as? kotlinx.serialization.json.JsonPrimitive)
            ?.takeIf { it.isString.not() }
            ?.content?.toBooleanStrictOrNull()

    /** The PC's own sentence for the switch, or "" - never invented here. */
    fun words(answer: kotlinx.serialization.json.JsonObject?): String =
        (answer?.get("message") as? kotlinx.serialization.json.JsonPrimitive)
            ?.takeIf { it.isString }?.content
            ?: (answer?.get("error") as? kotlinx.serialization.json.JsonPrimitive)
                ?.takeIf { it.isString }?.content
            ?: ""

    /** True while the PC has a card up waiting for the owner (202). */
    fun waiting(answer: kotlinx.serialization.json.JsonObject?): Boolean =
        (answer?.get("waiting") as? kotlinx.serialization.json.JsonPrimitive)
            ?.content?.toBooleanStrictOrNull() == true
}
