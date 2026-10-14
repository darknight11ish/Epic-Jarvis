package com.jarvis.client.net

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * "Start the local model" - the button on the standing line the phone already
 * draws (backend/model-lanes.patch, `backend/jarvis_model_lanes.py`; the
 * owner's decision of 2026-10-13; [com.jarvis.client.ModelWords]).
 *
 * THE DEFECT THIS ANSWERS. On 2026-10-13 both of the owner's Ollama lanes died
 * at about 16:30 and nothing said so for about five hours. The standing line
 * now says it - and until this work that line deliberately did NOTHING: the
 * owner started his lanes, and the app told him they were down. He has since
 * decided it should offer one action.
 *
 * WHAT THE ONE ACTION IS. Not `ollama serve`, and not a command line built
 * here. The phone asks the PC to run ITS OWN Windows logon task for the lane
 * the chat uses ([START_PATH]), and the PC looks that task up on itself, by the
 * half of its name a rename does not touch. There is no lane name in
 * [startBody]: the PC starts the lane Jarvis is pointed at (`OLLAMA_URL`'s
 * port - 11436 on his PC), never a guessed one and never both.
 *
 * STARTING IS NOT ARRIVING, and this file is shaped around that. Starting a
 * Windows task returns long before a model is loaded, so [ModelLaneInfo.state]
 * is `starting` while the PC watches the lane, and only the lane really
 * answering `/api/tags` makes it `up`. A start that does not come up settles as
 * `down` with a plain sentence, and the warning stays standing. **The failure
 * this exists to prevent is a button that reports success and changes
 * nothing.**
 *
 * Pure Kotlin (no Android), so ModelLaneTest runs it against the PC's own
 * answers and holds the three states, the words and the rule for clearing the
 * warning without a phone.
 */
object ModelLane {

    /** The read: the lane's state, and whether a press would do anything. */
    const val PATH = "/api/model-lanes"

    /** The one action. Takes an empty body, and that is the whole point. */
    const val START_PATH = "/api/model-lanes/start"

    /** The three states the PC reports. Never invented here. */
    const val UP = "up"
    const val STARTING = "starting"
    const val DOWN = "down"

    /**
     * The button's own words, on the standing line while the lane is down. The
     * desktop's button says the same thing (`jarvis-desktop/src/lane-start.js`
     * `START_WORDS`), because both apps are offering one action on one fact.
     */
    const val START = "Start the local model"

    /** Mid-press, and until the lane answers or runs out of time. */
    const val STARTING_WORDS = "Starting\u2026"

    /**
     * How often this phone asks what became of a start it asked for, in
     * milliseconds. Two seconds, and only while a start is in flight: the PC's
     * own answer already carries how long it has been and how long is left, so
     * this is a display beat and not the thing that decides.
     */
    const val WATCH_MS = 2_000L

    /**
     * The longest this phone will keep asking, in milliseconds. The PC's own
     * limit is ninety seconds; this is a little longer, so the PC's verdict -
     * "it did not come up" - is what the owner sees, rather than this app
     * giving up first and inventing a reason of its own.
     */
    const val WATCH_LIMIT_MS = 100_000L

    /** A start was asked for and has not settled. */
    const val ASKING = "Asking your PC to start it\u2026"

    /** The line under the button while it is starting, when the PC sent none. */
    const val STARTING_DETAIL = "Starting it now; this can take up to a minute."

    /** A read that never reached the PC. */
    const val UNREAD = "Could not read the local model's state."

    /** The PC did not answer when the button was pressed. */
    const val UNREACHED =
        "The PC would not start it just now. The local model is still not running."

    /**
     * The phone stopped asking before the PC gave a verdict. Said plainly, so
     * "we could not tell" is never read as "it is up".
     */
    const val UNSETTLED =
        "It did not come up in time. The local model is still not running."

    /**
     * The PC has no such route (an older backend). The warning stands; there is
     * simply no button to offer.
     */
    const val MISSING =
        "This PC's Jarvis is missing this feature. In PowerShell on the PC, in the Jarvis " +
            "folder, run: .\\scripts\\apply-patches.ps1 . Then restart Jarvis."

    /**
     * Whether the button is offered at all. Only the PC saying a press would
     * really do something ([ModelLaneInfo.canStart]) draws it - so a lane that
     * is up, a PC with no such task, and "the PC did not say" all draw nothing.
     */
    fun offers(info: ModelLaneInfo?): Boolean =
        info != null && info.state != UP && info.state != STARTING && info.canStart

    /**
     * What the button says, given the PC's own answer. Empty when it is not
     * offered.
     */
    fun buttonWords(info: ModelLaneInfo?): String = when {
        info == null -> ""
        info.state == STARTING -> STARTING_WORDS
        offers(info) -> START
        else -> ""
    }

    /** Whether the button can be pressed: offered, and no press already running. */
    fun canPress(info: ModelLaneInfo?, busy: Boolean = false): Boolean =
        !busy && offers(info)

    /**
     * The line under the button: the PC's own sentence, or the seconds it has
     * been, or nothing at all. Never a made-up "nearly there".
     */
    fun detail(info: ModelLaneInfo?): String {
        val said = info?.message.orEmpty().trim()
        if (said.isNotEmpty()) return said
        val elapsed = info?.elapsedS
        if (elapsed != null && elapsed > 0) {
            val whole = Math.round(elapsed)
            return "It has been $whole second${if (whole == 1L) "" else "s"}; " +
                "this can take up to a minute."
        }
        return if (info?.state == STARTING) STARTING_DETAIL else ""
    }

    /**
     * Whether the PC is saying the lane is really back. `up` and nothing else -
     * not `starting`, which is the whole difference between asking and
     * arriving.
     */
    fun isUp(info: ModelLaneInfo?): Boolean = info?.state == UP

    /**
     * Whether a settled start cleared the warning.
     *
     * THE RULE THIS FEATURE TURNS ON, and the one place it is decided: the
     * standing line is cleared by the lane answering ([isUp]), or by the PC's
     * own `ollama` field saying `true` ([ollamaUp]). A start that failed, a
     * start that was refused, a press that never landed and a watch this phone
     * gave up on all leave it standing.
     */
    fun clearsWarning(info: ModelLaneInfo?, ollamaUp: Boolean): Boolean =
        isUp(info) || ollamaUp

    /**
     * What to say when a start did not come up. The PC's own words when it sent
     * any (a refusal names the task it could not find), and otherwise the plain
     * sentence for that kind of failure. Never a softened success.
     */
    fun failureWords(info: ModelLaneInfo?, fell: String = ""): String {
        val said = (info?.error ?: info?.message).orEmpty().trim()
        if (said.isNotEmpty()) return said
        return fell.ifBlank { UNREACHED }
    }

    /**
     * The one body this phone ever sends. Empty, so no tap can name a lane the
     * chat is not on and nothing can start both lanes at once.
     */
    fun startBody(): Map<String, String> = emptyMap()

    /**
     * How long each wait should be, in the order they are taken, for a watch
     * that has `leftMs` of its own limit remaining. Empty when there is none.
     * Kept here so the loop's own beat and ceiling are one number each.
     */
    fun waits(leftMs: Long): List<Long> {
        val out = mutableListOf<Long>()
        var left = leftMs
        while (left > 0) {
            val step = minOf(WATCH_MS, left)
            out += step
            left -= step
        }
        return out
    }
}

/**
 * `GET /api/model-lanes`'s answer - the lane the PC's chat uses, as the PC
 * reports it. Every field has a default, so an older backend cannot make the
 * app crash; every field that matters is nullable where "the PC did not say" is
 * a real answer.
 */
@Serializable
data class ModelLaneInfo(
    val ok: Boolean = true,
    /** "everyday" or "coding"; empty when Jarvis is not pointed at a lane here. */
    val lane: String = "",
    /** What that lane is, in the PC's own words. */
    val words: String = "",
    /** The port the chat talks to. */
    val port: Int? = null,
    /**
     * This PC's OWN Windows task name, as `schtasks` lists it - the exact name
     * the press will start. Empty when this PC has no such task, and then no
     * button is offered.
     */
    val task: String = "",
    /** `up`, `starting` or `down`. Only [ModelLane.UP] clears the warning. */
    val state: String = ModelLane.DOWN,
    /**
     * True only when a press would really start something. This is what the
     * button is drawn from - never the state alone, because a PC with no such
     * task is down and cannot be started from here.
     */
    @SerialName("can_start") val canStart: Boolean = false,
    /** Why not, when a press would do nothing. */
    val why: String = "",
    /** Seconds since the start was asked for, while it is starting. */
    @SerialName("elapsed_s") val elapsedS: Double? = null,
    /** Seconds left of the PC's own wait, while it is starting. */
    @SerialName("left_s") val leftS: Double? = null,
    /** How long it took, once it has settled. */
    @SerialName("waited_s") val waitedS: Double? = null,
    /** A ready-made plain sentence, when the PC has one. */
    val message: String = "",
    /** The PC's own refusal sentence, when it refused. */
    val error: String = "",
    /** True when this answer is the press's own acknowledgement. */
    val changed: Boolean = false,
    /** True while the PC is still watching the lane. */
    val waiting: Boolean = false,
)
