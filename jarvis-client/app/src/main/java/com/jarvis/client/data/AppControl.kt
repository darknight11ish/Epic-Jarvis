package com.jarvis.client.data

import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

/**
 * The phone's half of app control: the allow-list, the masked screen read, the
 * ONE step, and the plain sentences - with no Android in this file, so the JVM
 * tests can hold every rule.
 *
 * The architecture (the owner's decision of 2026-10-19, "enable accessibility
 * service with control by jarvis as an option in the android app"): **the PC is
 * the brain and the gate; the phone is the hands.** This file never decides
 * what to do. It can read the screen into a masked snapshot, hand that snapshot
 * and ONE proposed step to the PC's `/api/app-control/run` route (which raises
 * ONE approval card and returns a run id), and then ask `/api/app-control/step`
 * for the ONE approved step. The phone executes exactly what the route returns
 * - never a step of its own - and a changed screen ends the run instead of
 * being retried.
 *
 * PATTERNS RE-IMPLEMENTED, NOT COPIED (MIT; credited in THIRD-PARTY-NOTICES.txt
 * and recorded in .dsh-scratch/RESEARCH-APP-AUTOMATION-REPOS-2026-10-19.md):
 * the AccessibilityService action set and plan/act/check loop from
 * GiggleWang/MobileAgent-Android, and the accessibility UI-tree contract from
 * droidrun/mobilerun. No source code from either project is used.
 *
 * NOTHING about a screen is logged: [Snapshot] is built, sent to the owner's
 * own PC and dropped. The PC's audit records the app and the verb only.
 */
object AppControl {

    /** `POST /api/app-control/run` - one plan and ONE approval card on the PC. */
    const val RUN_PATH = "/api/app-control/run"

    /** `POST /api/app-control/step` - the ONE approved step, or why there is none. */
    const val STEP_PATH = "/api/app-control/step"

    /** `POST /api/app-control/plan` - the owner's words -> the PC's LOCAL model's ONE step. */
    const val PLAN_PATH = "/api/app-control/plan"

    /** The owner's own words are the planning request: 1..200 characters. */
    const val WANT_MAX = 200
    const val ASK_PLACEHOLDER = "What should Jarvis do in this app?"
    const val ASK_LABEL = "Ask Jarvis"
    /** After one step has run, the next step needs a fresh tap and a fresh card. */
    const val ASK_AGAIN_LABEL = "Ask Jarvis for the next step"
    const val ASK_OLDER_PC =
        "Your PC's Jarvis is older than this screen, so it cannot plan a step yet. " +
            "Update Jarvis on the PC, then come back."

    /** At most this many apps on the owner's list (the PC refuses more). */
    const val MAX_APPS = 64

    /** Typed text is capped on both sides; the PC refuses anything longer. */
    const val MAX_TEXT = 200

    /** A snapshot holds at most this many controls, so one screen cannot flood the link. */
    const val MAX_CONTROLS = 120

    /** Long labels are truncated; a 500-word paragraph is not needed to find a button. */
    const val MAX_CONTROL_TEXT = 80

    /** The stored allow-list's shape. Missing or unreadable reads as EMPTY, never as everything. */
    const val STORE_VERSION = 1

    /** The only actions the phone will ever perform for a step. */
    val ACTIONS = listOf("tap", "swipe", "type", "back", "home")

    // ------------------------------------------------------- plain words ----

    const val OPTION_TITLE = "Let Jarvis control this phone"

    const val OPTION_DETAIL =
        "Off by default. Jarvis can only act while this is on, only in the apps " +
            "you add below, and only after you approve ONE step on your PC. " +
            "Android's own Accessibility switch is separate and must be on too."

    /** The option is stored on THIS phone and never synced, like the notification list. */
    const val OPTION_STORED = "Saved on this phone only. Your PC is asked before every single step."

    const val ANDROID_TITLE = "Android accessibility service"

    const val ANDROID_DETAIL =
        "Android needs its own switch as well: Settings -> Accessibility -> Jarvis. " +
            "Nothing below works until that is on, and turning it off there stops app " +
            "control immediately. This switch and Android's are separate on purpose."

    const val ANDROID_ON = "Android's Accessibility switch is on."

    const val ANDROID_OFF = "Android's Accessibility switch is off - turn it on in Android's own settings."

    const val ANDROID_UNKNOWN =
        "Could not read Android's Accessibility switch on this phone. Open Android's " +
            "settings and check by hand - this screen will not guess."

    const val SNAPSHOT_EMPTY =
        "No readable controls on this screen right now. Nothing was sent and nothing ran."

    /**
     * A window with nothing on it Jarvis could read or act on, or no window at
     * all. Refused with [CODE_BLANK_TREE] instead of sending an empty screen -
     * and never "fixed" by taking a picture or tapping a guessed pixel: the
     * PC's action set has no screenshot action, and raw pixel tapping was
     * declined.
     */
    const val BLANK_TREE =
        "Android gave Jarvis no readable screen just now - there is nothing on it " +
            "Jarvis can read or act on. Nothing was sent and nothing ran."

    /** Android's own `ACTION_SET_TEXT` said yes, but the field did not keep the words. */
    const val TEXT_NOT_TAKEN =
        "Android said it took the words, but the field did not keep them, so this is " +
            "not counted as typed."

    /** Stable names for the two honest failures; they are carried, never shown as words. */
    const val CODE_BLANK_TREE = "ui_tree_blank"
    const val CODE_TEXT_NOT_TAKEN = "text_not_taken"

    const val NO_ROUTE =
        "Your PC's Jarvis does not have app control yet (its backend is older). " +
            "Update Jarvis on the PC, then come back to this screen."

    const val ROUTE_READY = "Your PC has app control. It still asks you before every step."

    const val NO_ANSWER = "Your PC did not answer, so nothing was read and nothing ran."

    const val NOT_YET_SLICE =
        "This screen and the phone's service are ready. The PC link that asks Jarvis " +
            "to act - its chat tool - is the next slice, so no step is sent today."

    const val PLAN_LINE =
        "One step at a time. Jarvis reads the screen, proposes ONE step, and your PC " +
            "asks you to approve that exact step. A screen that changes after you " +
            "approve stops the run rather than guessing."

    const val ALLOW_TITLE = "Apps Jarvis may act in"

    const val ALLOW_EMPTY =
        "None, until you add one. Nothing can be read or done in an app that is not listed."

    const val ALLOW_ONE_AT_A_TIME = "Add one app at a time. Taking one off is instant."

    const val ADD = "Add an app"

    const val CLOSE_LIST = "Close the list"

    const val SEARCH = "Search apps"

    const val LOOKING = "Looking for apps..."

    const val NO_APPS = "No other apps found to add."

    const val NO_MATCH = "No app matches that."

    const val NO_APPS_ADDED = "No apps added yet."

    const val REMOVE = "Remove"

    /** Adding one of these is refused outright, in words, before anything is saved. */
    const val REFUSE_JARVIS = "Jarvis itself is not an app it may act in, so nothing was added."

    const val REFUSE_PASSWORD_MANAGER =
        "That looks like a password manager, so nothing was added."

    const val REFUSE_BANKING =
        "That looks like a bank or payment app, so nothing was added."

    /** The five things a step can be, in the owner's words. */
    val VERB_WORDS = mapOf(
        "tap" to "tap a button or a control",
        "swipe" to "swipe across a control",
        "type" to "type into the field you approved",
        "back" to "go back",
        "home" to "go to the home screen",
    )

    // ----------------------------------------------------------- refusals --

    /** Why a request may not start. Every one is a plain sentence on screen. */
    enum class Why {
        OPTION_OFF,
        ANDROID_OFF,
        ANDROID_UNKNOWN,
        EMPTY,
        NOT_LISTED,
        STALE,
        NO_SERVICE,
        VERB,
        PASSWORD,
        NOT_PLANNED,
        TARGET_CHANGED,
    }

    fun said(why: Why): String = when (why) {
        Why.OPTION_OFF ->
            "App control is off on this phone. Nothing was read and nothing ran."
        Why.ANDROID_OFF ->
            "Android's Accessibility switch for Jarvis is off, so nothing can be read " +
                "or done. Turn it on in Android's own settings first."
        Why.ANDROID_UNKNOWN ->
            "Could not read Android's Accessibility switch, so this phone will not act. " +
                "Check Android's own settings by hand."
        Why.EMPTY ->
            "No apps are allowed on this phone yet, so nothing can be read or done. " +
                "Add an app first."
        Why.NOT_LISTED ->
            "That app is not on your list of apps Jarvis may act in, so nothing was read " +
                "and nothing ran. Add it in Settings first."
        Why.STALE ->
            "The link to your PC is stale, so nothing was read and nothing ran."
        Why.NO_SERVICE ->
            "The phone's accessibility service is not connected right now, so nothing " +
                "can be read or done."
        Why.VERB ->
            "That is not one of the actions Jarvis may take (tap, swipe, type, back, home), " +
                "so nothing ran."
        Why.PASSWORD ->
            "That looks like a password or credential field, so Jarvis will not touch it. " +
                "Nothing was typed."
        Why.NOT_PLANNED ->
            "The step that came back is not the one you approved, so Jarvis stopped and " +
                "did nothing."
        Why.TARGET_CHANGED ->
            "The screen changed after you approved it, so Jarvis stopped rather than guess. " +
                "Nothing ran."
    }

    // ---------------------------------------------------------- allow-list --

    data class AppEntry(val packageName: String, val label: String)

    data class AddResult(val entries: List<AppEntry>, val error: String?)

    /** A package name: at least two dot-separated parts, letters/digits/underscore, starts with a letter. */
    fun validPackage(packageName: String?): Boolean {
        val pkg = packageName?.trim().orEmpty()
        if (pkg.isEmpty() || pkg.length > 255) return false
        val parts = pkg.split('.')
        if (parts.size < 2) return false
        return parts.all { part ->
            part.isNotEmpty() && part[0].isLetter() &&
                part.all { it.isLetterOrDigit() || it == '_' }
        }
    }

    fun labelFor(packageName: String, label: String?): String =
        label?.trim()?.takeIf { it.isNotEmpty() } ?: packageName

    /**
     * Reads the stored list. Tolerant on purpose: a missing file, bad JSON, a
     * wrong version or a malformed row reads as the rows that ARE valid, and
     * anything else is simply not allowed. It never throws and never widens.
     */
    fun parseStored(raw: String?): List<AppEntry> {
        if (raw.isNullOrBlank()) return emptyList()
        val root = runCatching { JarvisJson.parseToJsonElement(raw) }.getOrNull() as? JsonObject
            ?: return emptyList()
        val version = runCatching { root["version"]?.jsonPrimitive?.contentOrNull?.toInt() }
            .getOrNull() ?: return emptyList()
        if (version != STORE_VERSION) return emptyList()
        val apps = runCatching { root["apps"]?.jsonArray }.getOrNull() ?: return emptyList()
        val seen = LinkedHashMap<String, AppEntry>()
        for (element in apps) {
            val row = runCatching { element.jsonObject }.getOrNull() ?: continue
            val pkg = runCatching { row["package"]?.jsonPrimitive?.contentOrNull }.getOrNull()
            if (!validPackage(pkg)) continue
            val label = runCatching { row["label"]?.jsonPrimitive?.contentOrNull }.getOrNull()
            val clean = pkg!!.trim()
            seen[clean] = AppEntry(clean, labelFor(clean, label))
            if (seen.size >= MAX_APPS) break
        }
        return seen.values.toList()
    }

    /** Saves in the one shape [parseStored] reads; sorted, so the file is stable. */
    fun storeJson(entries: List<AppEntry>): String = buildJsonObject {
        put("version", STORE_VERSION)
        put("apps", buildJsonArray {
            entries.sortedBy { it.packageName }.forEach { entry ->
                add(buildJsonObject {
                    put("package", entry.packageName)
                    put("label", entry.label)
                })
            }
        })
    }.toString()

    /**
     * Adds one app. The JDK-free half: the caller has already checked the
     * phone's own Android category and passed its refusal ([refusedApp]).
     */
    fun add(entries: List<AppEntry>, packageName: String, label: String?, refusedApp: String? = null): AddResult {
        val pkg = packageName.trim()
        if (!validPackage(pkg)) {
            return AddResult(entries, "That is not an app package name, so nothing was added.")
        }
        if (refusedApp != null) return AddResult(entries, refusedApp)
        if (entries.any { it.packageName == pkg }) {
            return AddResult(entries, "That app is already on the list.")
        }
        if (entries.size >= MAX_APPS) {
            return AddResult(entries, "The list is full ($MAX_APPS apps). Take one off first.")
        }
        val next = (entries + AppEntry(pkg, labelFor(pkg, label))).sortedBy { it.packageName }
        return AddResult(next, null)
    }

    /** Taking one off is instant and needs nothing: it only ever lets Jarvis do less. */
    fun remove(entries: List<AppEntry>, packageName: String): List<AppEntry> =
        entries.filterNot { it.packageName == packageName.trim() }

    // ------------------------------------------------------------ snapshot --

    /** One control the screen would show. NEVER a password field. */
    data class Control(
        val id: String,
        val text: String,
        val cls: String,
        val bounds: List<Int>,
        /** Optional hints for the planner; never private data. */
        val clickable: Boolean = false,
        val editable: Boolean = false,
        val scrollable: Boolean = false,
    )

    /** What the phone read, one window at a time. The title is the window's own class name. */
    data class Snapshot(
        val app: String,
        val title: String,
        val controls: List<Control>,
    )

    /**
     * The mask, in one place: null means the control is NEVER read. Password
     * fields are skipped whole (and their children with them in the service),
     * invisible controls are skipped, and long words are truncated.
     */
    fun mask(
        id: String?,
        text: String?,
        cls: String?,
        bounds: List<Int>,
        password: Boolean,
        invisible: Boolean,
        hint: String? = null,
        clickable: Boolean = false,
        editable: Boolean = false,
        scrollable: Boolean = false,
    ): Control? {
        if (password || invisible) return null
        val cleanId = id?.trim().orEmpty()
        // A Compose/Material icon button has no text and no id - its human
        // label is the contentDescription, and an empty text field's is its
        // hint/placeholder. Dropping those made "+", Search, Play, More and
        // empty fields vanish from the snapshot (Gemini's review, 2026-10-20).
        val label = listOfNotNull(
            text?.trim()?.takeIf { it.isNotEmpty() },
            hint?.trim()?.takeIf { it.isNotEmpty() },
        ).firstOrNull()?.take(MAX_CONTROL_TEXT).orEmpty()
        if (cleanId.isEmpty() && label.isEmpty()) return null
        return Control(cleanId, label, cls?.trim().orEmpty(), bounds.take(4),
            clickable = clickable, editable = editable, scrollable = scrollable)
    }

    // ------------------------------------------- screen mechanics (pure) --
    // Everything a real device cannot tell the mocked unit tests lives here as
    // pure rules, so a JVM test holds each one (Gemini's review, 2026-10-20).

    /** Android `isPassword` is not enough: a "show password" eye keeps the inputType. */
    fun passwordInputType(inputType: Int): Boolean {
        val variation = inputType and 0xFF0
        return variation == 0x80 ||   // TEXT_VARIATION_PASSWORD
            variation == 0x90 ||      // TEXT_VARIATION_VISIBLE_PASSWORD
            variation == 0xE0 ||      // TEXT_VARIATION_WEB_PASSWORD
            variation == 0x10        // NUMBER_VARIATION_PASSWORD
    }

    /**
     * True when a node must be skipped WHOLE, children and all: Android's own
     * `isPassword`, a password `inputType` variation, or the API 34+ "sensitive
     * data" flag. A refusal to be sure is the safe direction.
     */
    fun sensitiveInput(
        isPassword: Boolean,
        inputType: Int,
        isDataSensitive: Boolean,
        sdk: Int,
    ): Boolean = isPassword || passwordInputType(inputType) ||
        (sdk >= 34 && isDataSensitive)

    /**
     * The tap ladder: 0 = click this node; 1..3 = click that many parents up;
     * -1 = no clickable ancestor, use the guarded coordinate gesture. A parent
     * only counts when it is the same package and not inside a password node.
     */
    fun tapRung(nodeClickable: Boolean, parents: List<Pair<Boolean, Boolean>>): Int {
        if (nodeClickable) return 0
        var passwordSubtree = false
        parents.take(3).forEachIndexed { index, (clickable, password) ->
            if (password) passwordSubtree = true
            if (!passwordSubtree && clickable) return index + 1
        }
        return -1
    }

    /**
     * The `type` rung: the matched node if it is editable, else the index of
     * exactly ONE editable, non-password child (a TextInputLayout label's
     * EditText is one level down); -1 when the answer is not unambiguous.
     */
    fun editableChild(children: List<Pair<Boolean, Boolean>>): Int {
        if (children.isEmpty()) return -1
        val editable = children.withIndex().filter { (_, child) ->
            child.first && !child.second
        }
        return if (editable.size == 1) editable[0].index else -1
    }

    /**
     * A swipe's two points, clamped strictly inside the target's own bounds AND
     * the screen's central 15%-85% band, so an edge swipe can never trigger
     * Android's Back or notification-shade gesture. Null when there is no room.
     */
    fun swipePoints(bounds: List<Int>, screenW: Int, screenH: Int): Pair<Float, Float>? {
        if (bounds.size != 4 || screenW <= 0 || screenH <= 0) return null
        val left = maxOf(bounds[0].toFloat(), screenW * 0.15f)
        val right = minOf(bounds[2].toFloat(), screenW * 0.85f)
        val top = maxOf(bounds[1].toFloat(), screenH * 0.15f)
        val bottom = minOf(bounds[3].toFloat(), screenH * 0.85f)
        if (right - left < 8f || bottom - top < 8f) return null
        val y = (top + bottom) / 2f
        val startX = right - (right - left) * 0.1f
        val endX = left + (right - left) * 0.1f
        return if (startX - endX < 4f) null else startX to endX
    }

    /**
     * The blank-tree rule, in one place so a JVM test holds it: a window must be
     * in front AND carry at least ONE node Jarvis could read or act on. True
     * means the phone refuses with [CODE_BLANK_TREE] - it never sends an empty
     * screen or quietly returns nothing, because either reads as "nothing here"
     * rather than as "Jarvis could not read it".
     */
    fun blankTree(hasWindow: Boolean, usableNodes: Int): Boolean =
        !hasWindow || usableNodes <= 0

    /**
     * The `type` read-back rule: Android's own action answering true is NOT
     * proof the field kept the words. Only the field's own text, read back and
     * equal to exactly what was set, counts as typed; anything else is
     * [CODE_TEXT_NOT_TAKEN], never Done.
     */
    fun textTook(expected: String, readBack: String?): Boolean = readBack == expected

    // ------------------------------------------------------ planning wire --

    /** `POST /api/app-control/plan`s body: the owner's words + the masked screen. */
    fun planBody(allowed: List<AppEntry>, want: String, snapshot: Snapshot): String =
        buildJsonObject {
            put("allowed", buildJsonArray { allowed.forEach { add(JsonPrimitive(it.packageName)) } })
            put("want", want.trim().take(WANT_MAX))
            put("snapshot", snapshotJson(snapshot))
        }.toString()

    /** The probe: an empty want is a 400 on a PC with the route, 404 on an older one. */
    fun planProbeBody(): String = buildJsonObject {
        put("allowed", buildJsonArray { })
        put("want", "")
        put("snapshot", buildJsonObject {
            put("app", "")
            put("title", "")
            put("controls", buildJsonArray { })
        })
    }.toString()

    /**
     * The PC's own sentence for "I know app control, but not that run" - the
     * answer a REAL PC gives to the empty-run probe. It must stay equal to
     * `jarvis_app_control.UNKNOWN_RUN` (the backend suite pins that); when a
     * PC answers anything else to the probe, the phone fails closed to OLDER.
     */
    const val NO_SUCH_RUN_MARKER = "That app-control run is not here on this PC any more."

    /** What the run/step probe found: only positive evidence is READY. */
    enum class ProbeRoute { READY, OLDER, UNREACHABLE }

    /**
     * Reads the run/step probe's answer, failing closed: a 404 means the route
     * exists ONLY when its body carries [NO_SUCH_RUN_MARKER] (the empty run id
     * the probe sends). A 404 with any other or absent error - the common older
     * backend answer `{"error": "not found"}` - is OLDER, never READY; 200/202
     * are a real answer to the probe; no answer at all is UNREACHABLE.
     */
    fun probeRoute(status: Int, error: String?): ProbeRoute = when {
        status == 0 -> ProbeRoute.UNREACHABLE
        status == 200 || status == 202 -> ProbeRoute.READY
        status == 404 && error == NO_SUCH_RUN_MARKER -> ProbeRoute.READY
        else -> ProbeRoute.OLDER
    }

    /** What the probe found about the PC's planning capability. */
    enum class PlanCapability { AVAILABLE, OLDER, UNREACHABLE }

    /**
     * Reads the probe's answer: a 404 is the PC's "no such route" (an older
     * backend); anything else means the route exists - a 400 (bad want), a 409
     * (switched off) or a 422 all name a PC that understands `plan`.
     */
    fun planCapability(status: Int, body: JsonObject?): PlanCapability = when {
        status == 0 -> PlanCapability.UNREACHABLE
        status == 404 -> PlanCapability.OLDER
        else -> PlanCapability.AVAILABLE
    }

    /** The PC's answer to `plan`. */
    sealed interface PlanReply {
        data class Pending(val runId: String, val step: String, val model: String) : PlanReply
        data class Off(val sentence: String) : PlanReply
        data class Refused(val sentence: String) : PlanReply
        data class Failed(val sentence: String) : PlanReply
        data object RouteMissing : PlanReply
        data object Unknown : PlanReply
    }

    /** The PC's answer to the planning round; 202 means ONE card is up. */
    fun parsePlan(status: Int, body: JsonObject?): PlanReply {
        if (status == 404) return PlanReply.RouteMissing
        if (body == null) return PlanReply.Unknown
        val ok = bodyText(body, "ok")
        val runId = bodyText(body, "run")
        if (status == 202 && ok == "true" && !runId.isNullOrBlank()) {
            return PlanReply.Pending(
                runId = runId,
                step = bodyText(body, "step").orEmpty(),
                model = bodyText(body, "model").orEmpty(),
            )
        }
        if (status == 409) {
            val available = bodyText(body, "available")
            return if (available == "false") PlanReply.Off(errorSentence(body, ""))
            else PlanReply.Refused(errorSentence(body, ""))
        }
        if (status == 400 || status == 422) {
            return PlanReply.Failed(errorSentence(body, ""))
        }
        return PlanReply.Unknown
    }

    /** The waiting line a 202 shows: the ONE step is on the PC's card, nothing ran. */
    fun planWaitingLine(pending: PlanReply.Pending): String =
        "One step is on your PC's approval card: ${pending.step.ifBlank { "(the step your PC chose)" }}. " +
            "Approve or deny it there. Nothing runs until you do." +
            (if (pending.model.isNotBlank()) " Planned locally by ${pending.model}." else "")

    /** The button's own label: after one step, the next one needs a fresh tap. */
    fun askLabel(everPerformed: Boolean): String = if (everPerformed) ASK_AGAIN_LABEL else ASK_LABEL

    /** Whether the ask control is offered and can be pressed right now. */
    fun canAsk(capability: PlanCapability, optionOn: Boolean, busy: Boolean): Boolean =
        capability == PlanCapability.AVAILABLE && optionOn && !busy

    /**
     * The ONE-card rule in miniature: after a step has been performed, the only
     * way to another step is the owner pressing Ask again - there is no state
     * in which this object plans a second step by itself.
     */
    fun afterStep(everPerformed: Boolean, sentence: String): AskState =
        AskState(phase = AskPhase.IDLE, sentence = sentence, everPerformed = true)

    enum class AskPhase { IDLE, ASKING, WAITING, DONE, REFUSED }

    /** The phone's planning state: one request, one card, then a fresh tap. */
    data class AskState(
        val phase: AskPhase = AskPhase.IDLE,
        val sentence: String = "",
        val step: String = "",
        val model: String = "",
        val everPerformed: Boolean = false,
    ) {
        val busy: Boolean get() = phase == AskPhase.ASKING || phase == AskPhase.WAITING
        val label: String get() = askLabel(everPerformed)
    }

    /** The PC's snapshot read: it may only ever be this, never the raw tree. */
    fun snapshotJson(snapshot: Snapshot): JsonObject = buildJsonObject {
        put("app", snapshot.app)
        put("title", snapshot.title)
        put("controls", buildJsonArray {
            snapshot.controls.take(MAX_CONTROLS).forEach { control ->
                add(buildJsonObject {
                    put("id", control.id)
                    put("text", control.text)
                    put("class", control.cls)
                    put("bounds", buildJsonArray { control.bounds.take(4).forEach { add(JsonPrimitive(it)) } })
                    if (control.clickable) put("clickable", true)
                    if (control.editable) put("editable", true)
                    if (control.scrollable) put("scrollable", true)
                })
            }
        })
    }

    // ---------------------------------------------------------------- step --

    /** ONE atomic step. [target] is the control the PC's card names, or null for back/home. */
    data class Step(val action: String, val target: Control?, val text: String? = null)

    /** The step as the PC's card sees it; text only for `type`, and only up to the cap. */
    fun stepJson(step: Step): JsonObject = buildJsonObject {
        put("action", step.action)
        step.target?.let { target ->
            put("target", buildJsonObject {
                put("id", target.id)
                put("text", target.text)
                put("class", target.cls)
                put("bounds", buildJsonArray { target.bounds.take(4).forEach { add(JsonPrimitive(it)) } })
                if (target.clickable) put("clickable", true)
                if (target.editable) put("editable", true)
                if (target.scrollable) put("scrollable", true)
            })
        }
        if (step.action == "type") put("text", step.text.orEmpty().take(MAX_TEXT))
    }

    /** `POST /api/app-control/run`'s body. The allow-list rides with every request. */
    fun runBody(allowed: List<AppEntry>, app: String, appName: String, step: Step, snapshot: Snapshot): String =
        buildJsonObject {
            put("allowed", buildJsonArray { allowed.forEach { add(JsonPrimitive(it.packageName)) } })
            put("app", app)
            put("app_name", appName)
            put("step", stepJson(step))
            put("snapshot", snapshotJson(snapshot))
        }.toString()

    /** `POST /api/app-control/step`'s body with a fresh snapshot. */
    fun stepBody(run: String, snapshot: Snapshot): String = buildJsonObject {
        put("run", run)
        put("snapshot", snapshotJson(snapshot))
    }.toString()

    /** `{"run": id, "stop": true}` - stop is the safe direction and needs no card. */
    fun stopBody(run: String): String = buildJsonObject {
        put("run", run)
        put("stop", true)
    }.toString()

    /** `{"run": id, "result": "done"|"failed"}` after doing the approved step. */
    fun resultBody(run: String, failed: Boolean): String = buildJsonObject {
        put("run", run)
        put("result", if (failed) "failed" else "done")
    }.toString()

    /** The probe that tells an older PC (no route) from a real one, without acting. */
    fun probeBody(): String = buildJsonObject {
        put("run", "")
        put("snapshot", buildJsonObject {
            put("app", "")
            put("title", "")
            put("controls", buildJsonArray { })
        })
    }.toString()

    /**
     * The step the phone posts must be the one the route approved: the same
     * action, the same control, and the same text. Compared field by field
     * because the PC answers in its own JSON, not by identity.
     */
    fun matches(planned: Step, returned: Step): Boolean {
        if (planned.action != returned.action) return false
        if (planned.action == "back" || planned.action == "home") {
            return planned.target == null && returned.target == null
        }
        val a = planned.target ?: return false
        val b = returned.target ?: return false
        if (a.id != b.id) return false
        if (a.text != b.text) return false
        if (planned.action == "type" && planned.text.orEmpty() != returned.text.orEmpty()) return false
        return true
    }

    /** Why this phone may not start a run at all, or null when it may. */
    fun whyNotAllowed(
        optionOn: Boolean,
        android: AndroidState,
        allowed: List<AppEntry>,
        foreground: String?,
        stale: Boolean,
        serviceConnected: Boolean,
    ): Why? = when {
        !optionOn -> Why.OPTION_OFF
        android != AndroidState.ON -> if (android == AndroidState.OFF) Why.ANDROID_OFF else Why.ANDROID_UNKNOWN
        !serviceConnected -> Why.NO_SERVICE
        allowed.isEmpty() -> Why.EMPTY
        stale -> Why.STALE
        foreground.isNullOrBlank() -> Why.NO_SERVICE
        allowed.none { it.packageName == foreground } -> Why.NOT_LISTED
        else -> null
    }

    // ------------------------------------------------------ reply parsing --

    /** The PC's answer to `run`. */
    sealed interface RunReply {
        data class Pending(val runId: String) : RunReply
        data class Off(val sentence: String) : RunReply
        data class Refused(val sentence: String) : RunReply
        data class Failed(val sentence: String) : RunReply
        data object RouteMissing : RunReply
        data object Unknown : RunReply
    }

    /** The PC's answer to `step`. */
    sealed interface StepReply {
        data object Pending : StepReply
        data class Step(val step: AppControl.Step) : StepReply
        data class Stopped(val sentence: String) : StepReply
        data class Ended(val status: String, val sentence: String) : StepReply
        data class Delivered(val sentence: String) : StepReply
        data object RouteMissing : StepReply
        data object Unknown : StepReply
        data class Failed(val sentence: String) : StepReply
    }

    private fun bodyText(body: JsonObject?, key: String): String? =
        body?.let { runCatching { it[key]?.jsonPrimitive?.contentOrNull }.getOrNull() }

    private fun errorSentence(body: JsonObject?, fallback: String): String =
        bodyText(body, "error")?.takeIf { it.isNotBlank() } ?: fallback

    /** The PC's own plain sentence, or this file's fixed words - never a stack trace. */
    fun parseRun(status: Int, body: JsonObject?): RunReply {
        val ok = body?.let { runCatching { it["ok"]?.jsonPrimitive?.contentOrNull }.getOrNull() }
        val runId = bodyText(body, "run")
        if (status == 202 && ok == "true" && !runId.isNullOrBlank()) return RunReply.Pending(runId)
        if (status == 409) {
            val available = body?.let { runCatching { it["available"]?.jsonPrimitive?.contentOrNull }.getOrNull() }
            if (available == "false") return RunReply.Off(errorSentence(body, ""))
            return RunReply.Refused(errorSentence(body, ""))
        }
        if (status == 404) return RunReply.RouteMissing
        if (status == 400 || status == 200) {
            val text = errorSentence(body, "")
            return if (text.isNotBlank()) RunReply.Failed(text) else RunReply.Unknown
        }
        return RunReply.Unknown
    }

    /** The PC's answer to `step`; a 200 with `status: step` carries the ONE approved step. */
    fun parseStep(status: Int, body: JsonObject?): StepReply {
        if (status == 404) return StepReply.RouteMissing
        if (body == null) return StepReply.Unknown
        val statusWord = bodyText(body, "status") ?: return StepReply.Unknown
        return when (statusWord) {
            "pending" -> StepReply.Pending
            "step" -> {
                val obj = body["step"] as? JsonObject ?: return StepReply.Unknown
                val action = bodyText(obj, "action") ?: return StepReply.Unknown
                val target = (obj["target"] as? JsonObject)?.let { t ->
                    Control(
                        id = bodyText(t, "id").orEmpty(),
                        text = bodyText(t, "text").orEmpty(),
                        cls = bodyText(t, "class").orEmpty(),
                        bounds = runCatching {
                            t["bounds"]!!.jsonArray.map { it.jsonPrimitive.content.toInt() }
                        }.getOrDefault(emptyList()),
                        clickable = bodyText(t, "clickable") == "true",
                        editable = bodyText(t, "editable") == "true",
                        scrollable = bodyText(t, "scrollable") == "true",
                    )
                }
                StepReply.Step(Step(action, target, bodyText(obj, "text")))
            }
            "stopped" -> StepReply.Stopped(errorSentence(body, said(Why.TARGET_CHANGED)))
            "denied", "timed_out", "refused", "failed" -> StepReply.Ended(statusWord, errorSentence(body, ""))
            "delivered" -> StepReply.Delivered(errorSentence(body, ""))
            else -> StepReply.Failed(errorSentence(body, ""))
        }
    }

    // ------------------------------------------------- Android's own switch --

    /** What Android's read-only settings answer says, never a guess. */
    enum class AndroidState { ON, OFF, CANNOT_READ }

    /**
     * Reads `Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES`, which is
     * `pkg/cls:pkg/cls:...` (a user suffix may follow each). Read-only. A
     * service is ON when its own component appears; an unreadable answer is
     * [AndroidState.CANNOT_READ], never OFF-guessed.
     */
    fun androidState(raw: String?, component: String): AndroidState {
        val answer = raw ?: return AndroidState.CANNOT_READ
        val wanted = normalizeComponent(component)
        if (wanted.isEmpty()) return AndroidState.CANNOT_READ
        val entries = answer.split(':').map { it.trim() }.filter { it.isNotEmpty() }
        val on = entries.any { entry ->
            // Each entry is pkg/cls; a user suffix may follow it. A class stored
            // with Android's own "." shorthand is expanded before comparing.
            val withoutUser = entry.substringBefore(';').substringBefore(' ')
            normalizeComponent(withoutUser).equals(wanted, ignoreCase = true)
        }
        return if (on) AndroidState.ON else AndroidState.OFF
    }

    /** `pkg/.service.X` becomes `pkg/com.pkg.service.X`, so both spellings compare equal. */
    private fun normalizeComponent(component: String): String {
        val clean = component.trim()
        val slash = clean.indexOf('/')
        if (slash <= 0 || slash == clean.length - 1) return clean
        val pkg = clean.substring(0, slash)
        val cls = clean.substring(slash + 1)
        return if (cls.startsWith(".")) "$pkg/$pkg$cls" else "$pkg/$cls"
    }

    /** The component Android must have enabled, from the app's own package and class names. */
    fun component(packageName: String, serviceClassName: String): String =
        "$packageName/$serviceClassName"
}
