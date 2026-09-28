package com.jarvis.client.face

import com.jarvis.client.FaceState
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlin.math.abs
import kotlin.math.exp
import kotlin.math.max
import kotlin.math.min

/**
 * What the animal faces are told from outside the face, for the new
 * behaviours (the owner's decisions of 2026-09-28; docs/CRITTERS.md "New
 * behaviours" and "What each app feeds them") - the phone's copy of what
 * the desktop's faces.html keeps in FACE_ANIMAL and FACE_MOMENTS.
 *
 *  - The owner's switches, shared with the PC ("Animal options",
 *    [com.jarvis.client.net.AnimalOptions]): JarvisRuntime sets them
 *    whenever the options arrive ([apply]).
 *  - The moments, stamped with [System.nanoTime] when JarvisRuntime hears
 *    them: a fact saved (`memory_saved` - never while App lock or "Hide
 *    memory lists and chat history" is on; the runtime holds it back), a
 *    long answer ready (`deep` done), a focus session on or off (`focus`).
 *
 * Every FaceView reads this each frame, like [SkyNow] and [SeasonNow]. It
 * holds no words: never a fact, never a question, never what a focus
 * session is on - the events carry none either.
 *
 * Pure Kotlin, no Android types, so it runs on a plain JVM (AnimalFeedTest).
 */
object AnimalNow {
    @Volatile var nods: Boolean = true
    @Volatile var focusBuddy: Boolean = true
    @Volatile var acks: Boolean = true
    @Volatile var petting: Boolean = true
    @Volatile var cute: Boolean = true
    /**
     * How many times the switches have been applied. A face that started
     * before the first ([AnimalFeed]) takes them at once when it comes, rather
     * than easing there from the defaults - the desktop's FACE_OPTS_READS.
     */
    @Volatile var reads: Int = 0

    /** When the last fact was saved / long answer was ready ([System.nanoTime]); 0: none yet. */
    @Volatile var factAt: Long = 0L
    @Volatile var glowAt: Long = 0L
    /** A focus session is on, as far as this phone has heard. */
    @Volatile var focusOn: Boolean = false
    /** When a focus session ended, waiting for Jarvis to be idle again; 0: none. */
    @Volatile var focusEndDue: Long = 0L

    /** The closest two nods, and two glows, may come (the pose's own lengths). */
    const val ACK_NOD_GAP_S = 1.2f
    const val ACK_GLOW_GAP_S = 1.8f
    /** A focus stretch that has waited longer than this for Jarvis to be idle is dropped. */
    const val FOCUS_END_WAIT_S = 60f

    /** The shared switches, by their ids in `jarvis_animal.SWITCHES` - anything missing keeps its value. */
    fun apply(values: Map<String, Boolean>) {
        reads++
        values["nods"]?.let { nods = it }
        values["focus_buddy"]?.let { focusBuddy = it }
        values["acks"]?.let { acks = it }
        values["petting"]?.let { petting = it }
        values["cute_moments"]?.let { cute = it }
    }

    /** A fact was saved (the caller has checked App lock and "Hide memory lists"). */
    fun factSaved(now: Long = System.nanoTime()) {
        if (factAt == 0L || (now - factAt) / 1e9f >= ACK_NOD_GAP_S) factAt = now
    }

    /** A long answer is ready. */
    fun longAnswer(now: Long = System.nanoTime()) {
        if (glowAt == 0L || (now - glowAt) / 1e9f >= ACK_GLOW_GAP_S) glowAt = now
    }

    /** A focus session is on, or has ended. */
    fun focus(on: Boolean, now: Long = System.nanoTime()) {
        if (focusOn && !on) focusEndDue = now
        if (on) focusEndDue = 0L
        focusOn = on
    }

    /** Seconds since [at] ([System.nanoTime]), or [CritterPose.NEVER] for none. */
    fun since(at: Long, now: Long): Float =
        if (at == 0L) CritterPose.NEVER else max(0f, (now - at) / 1e9f)

    /**
     * The `focus` event's data (`{"state": "started" | "changed" | "ended"}`,
     * or a callout's number): true on, false ended, null for anything else.
     */
    fun focusOf(data: JsonElement?): Boolean? {
        val state = ((data as? JsonObject)?.get("state") as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
        return when (state) {
            "started", "changed" -> true
            "ended" -> false
            else -> null
        }
    }

    /** Whether the `deep` event says a long answer is ready (`state: "done"`). */
    fun deepDone(data: JsonElement?): Boolean =
        ((data as? JsonObject)?.get("state") as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull == "done"
}

/**
 * One face's side of the new behaviours: the owner's switches and a focus
 * session eased as the options are, the pause finders for the owner's voice
 * and Jarvis's ([CritterPose.pauseStep]), whether this answer's gestures
 * follow its phrase ends, being stroked, and the focus stretch - handed to
 * the pose as [opts]. The desktop's faces.html critterFace `track` and
 * `behaviours`, for [FaceHost]. Its clock is its own, in seconds, from the
 * steps it is given.
 */
class AnimalFeed {
    private var clock = 0f

    private var nodsW = if (AnimalNow.nods) 1f else 0f
    private var focusBuddyW = if (AnimalNow.focusBuddy) 1f else 0f
    private var acksW = if (AnimalNow.acks) 1f else 0f
    private var pettingW = if (AnimalNow.petting) 1f else 0f
    private var cuteW = if (AnimalNow.cute) 1f else 0f
    private var focusW = if (AnimalNow.focusOn) 1f else 0f
    // Whether the weights above began from the stored switches.
    private var switchesRead = AnimalNow.reads > 0

    private var heard: CritterPose.PauseRec? = null
    private var phrase: CritterPose.PauseRec? = null
    /** Gestures follow the phrase ends in this answer (decided as it starts). */
    var phraseOn: Boolean = false
        private set
    /** When the focus stretch was handed on (this clock); negative: none. */
    private var focusEndAt = -1f

    // Petting: the press, held or moving, and the eased weight.
    private var petDown = false
    private var petDownAt = 0f
    private var petX0 = 0f
    private var petLastX = 0f
    private var petLastAt = 0f
    private var petMovedAt = -1f
    private var petVx = 0f
    private var petTouchX = 0f
    private var petW = 0f
    private var petXs = 0f
    private var petDirS = 0f

    /**
     * Every advance, drawn or not: the switches and a focus session eased
     * one full switch per [easeS] seconds, and being stroked (in over
     * [PET_IN_S], out over [PET_OUT_S]).
     */
    fun stepWeights(dt: Float, easeS: Float = 1f) {
        val d = max(0f, dt)
        clock += d
        val k = d / easeS
        // Started before the stored switches were read: take them at once.
        val snap = !switchesRead && AnimalNow.reads > 0
        if (snap) switchesRead = true
        val ks = if (snap) 1f else k
        fun ramp(r: Float, on: Boolean, by: Float = k) = if (on) min(1f, r + by) else max(0f, r - by)
        nodsW = ramp(nodsW, AnimalNow.nods, ks)
        focusBuddyW = ramp(focusBuddyW, AnimalNow.focusBuddy, ks)
        acksW = ramp(acksW, AnimalNow.acks, ks)
        pettingW = ramp(pettingW, AnimalNow.petting, ks)
        cuteW = ramp(cuteW, AnimalNow.cute, ks)
        focusW = ramp(focusW, AnimalNow.focusOn)
        val on = petting()
        petW = if (on) min(1f, petW + d / PET_IN_S) else max(0f, petW - d / PET_OUT_S)
        if (on) {
            petXs += (petTouchX - petXs) * (1f - exp(-d / 0.15f))
            val moving = petMovedAt >= 0f && clock - petMovedAt < 0.15f
            val want = if (moving) (petVx / 1.5f).coerceIn(-1f, 1f) else 0f
            petDirS += (want - petDirS) * (1f - exp(-d / 0.3f))
        } else {
            petDirS *= exp(-d / 0.3f)
        }
    }

    /** The state last handed to [onState]. */
    private var lastState: FaceState? = null

    /**
     * The state shown, every advance (only a change counts). Into speaking,
     * the gestures follow the phrase ends only while the "nods" switch is on
     * and a real voice is heard ([voiced]) - decided as an answer starts,
     * never in the middle.
     */
    fun onState(next: FaceState, voiced: Boolean) {
        if (next == lastState) return
        lastState = next
        if (next == FaceState.SPEAKING) phraseOn = AnimalNow.nods && voiced
    }

    /**
     * On each drawn frame, [dt] seconds after the last: the pauses in the
     * owner's talking ([mic], the smoothed microphone) while listening, and
     * in Jarvis's real voice ([voice], null when none plays) while speaking;
     * and the focus stretch, handed on once Jarvis is idle again.
     */
    fun stepFrame(dt: Float, state: FaceState, mic: Float, voice: Float?, now: Long = System.nanoTime()) {
        fun age(r: CritterPose.PauseRec?) = r?.let { CritterPose.PauseRec(0f, 0f, min(CritterPose.NEVER, it.ago + dt), it.n) }
        heard = if (state == FaceState.LISTENING) {
            CritterPose.pauseStep(heard, dt, mic, CritterPose.Pause.NOD_QUIET, CritterPose.Pause.NOD_GAP)
        } else {
            age(heard)
        }
        phrase = if (state == FaceState.SPEAKING && phraseOn) {
            CritterPose.pauseStep(phrase, dt, voice ?: 0f, CritterPose.Pause.PHRASE_QUIET, CritterPose.Pause.PHRASE_GAP)
        } else {
            age(phrase)
        }
        val due = AnimalNow.focusEndDue
        if (due != 0L && state == FaceState.IDLE) {
            if ((now - due) / 1e9f <= AnimalNow.FOCUS_END_WAIT_S) focusEndAt = clock
            AnimalNow.focusEndDue = 0L
        }
    }

    // ---- Petting: a press held still for PET_HOLD_S, then moved to stroke ----

    /** A finger lands at [x] pixels across a face [width] wide. */
    fun petDown(x: Float, width: Float) {
        petDown = true
        petDownAt = clock
        petX0 = x
        petLastX = x
        petLastAt = clock
        petVx = 0f
        petTouchX = (x / max(1f, width)) * 2f - 1f
    }

    /**
     * The finger moved to [x]. Before the press has been held [PET_HOLD_S],
     * moving more than [slop] pixels makes it a drag (it turns the face, as
     * before) and it never pets. Returns whether it is stroking now - then
     * the caller must not turn the face with it.
     */
    fun petMove(x: Float, width: Float, slop: Float): Boolean {
        if (!petDown) return false
        if (!petting()) {
            if (abs(x - petX0) > slop) petDown = false
            return false
        }
        val half = max(1f, width / 2f)
        val dts = max(0.001f, clock - petLastAt)
        petVx += ((x - petLastX) / half / dts - petVx) * 0.5f
        petTouchX = (x / half - 1f).coerceIn(-1f, 1f)
        petLastX = x
        petLastAt = clock
        petMovedAt = clock
        return true
    }

    fun petUp() {
        petDown = false
    }

    /** Whether the press is petting now: held long enough. */
    fun petting(): Boolean = petDown && clock - petDownAt >= PET_HOLD_S

    /**
     * What the pose is handed besides calm, serious and still (those three
     * are the host's), with [goodbye] and [hello] from a face switch. [now]
     * is [System.nanoTime], for the moments JarvisRuntime stamped.
     */
    fun opts(
        calm: Float, serious: Float, still: Float,
        goodbye: Float = 0f, hello: Float = 1f, now: Long = System.nanoTime(),
    ): CritterPose.Opts {
        fun e(r: Float) = r * r * (3f - 2f * r)
        val ph = phrase
        val hd = heard
        return CritterPose.Opts(
            calm = calm, serious = serious, still = still,
            variety = 1f,
            cute = e(cuteW), nods = e(nodsW), focusBuddy = e(focusBuddyW), acks = e(acksW), petting = e(pettingW),
            focus = e(focusW),
            pet = e(petW), petX = petXs, petDir = petDirS,
            hello = hello, goodbye = goodbye,
            heard = hd?.ago ?: CritterPose.NEVER, heardN = hd?.n ?: -1,
            phraseEnd = if (phraseOn) ph?.ago ?: CritterPose.NEVER else CritterPose.NEVER,
            phraseN = if (phraseOn) ph?.n ?: 0 else -1,
            ackNod = AnimalNow.since(AnimalNow.factAt, now),
            ackGlow = AnimalNow.since(AnimalNow.glowAt, now),
            focusEnd = if (focusEndAt >= 0f) clock - focusEndAt else CritterPose.NEVER,
        )
    }

    companion object {
        /** A press held this long pets (the phone's long press). */
        const val PET_HOLD_S = 0.5f
        const val PET_IN_S = 0.3f
        const val PET_OUT_S = 1f
    }
}
