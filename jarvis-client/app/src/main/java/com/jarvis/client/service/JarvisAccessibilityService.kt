package com.jarvis.client.service

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.graphics.Rect
import android.os.Build
import android.os.Bundle
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.jarvis.client.data.AppControl

/**
 * The phone's hands, and NOTHING ELSE. This is an Android
 * `AccessibilityService`: Android hands it the screen's controls and lets it
 * perform a tap, a swipe, a `type` into a field, and Back/Home.
 *
 * What it will never do, and the reasons are in the code below:
 *  - it never decides anything. [performStep] acts only on a step the PC's
 *    `/api/app-control/step` route returned for a card the owner approved
 *    (the executor, [AppControlExecutor], is the only caller);
 *  - it never reads a password field: a node whose `isPassword` is true is
 *    skipped WHOLE, before its text is ever touched, and so are its children;
 *  - it never reads an invisible control, and it truncates long text
 *    ([AppControl.MAX_CONTROL_TEXT]);
 *  - it never takes a picture of the screen or taps a pixel it guessed: a
 *    screen it cannot read is refused as `ui_tree_blank`, never guessed at;
 *  - it never says Done for a `type` it could not read back - Android's own
 *    "true" is not proof the field kept the words (`text_not_taken`);
 *  - it never reads or performs anything on a screen whose app is not on the
 *    owner's list - the executor checks that before calling here, and this
 *    class checks it again against the plan's app;
 *  - it logs NOTHING about the screen or typed text.
 *
 * The service is ordinary - not a foreground service - and Android manages its
 * lifetime: [connected] is the one honest "is it running" answer.
 */
class JarvisAccessibilityService : AccessibilityService() {

    /** What the one approved action came to, in plain words. */
    sealed interface Outcome {
        /** The step ran. NOT a claim about what the app did with it. */
        data object Done : Outcome

        /**
         * The step did not run, and [sentence] says why, plainly.
         *
         * [code] is a stable name for the failure, empty for the refusals this
         * service already had; the honest ones are
         * [AppControl.CODE_BLANK_TREE] and [AppControl.CODE_TEXT_NOT_TAKEN]. It
         * is carried for the runtime and never shown in place of [sentence].
         */
        data class Refused(val sentence: String, val code: String = "") : Outcome
    }

    /**
     * What one screen read found: the masked screen, or an honest refusal.
     *
     * A refusal is a VALUE, never a null and never an empty snapshot - both of
     * those read as "nothing here" instead of "Jarvis could not read it".
     */
    sealed interface Read {
        /** The screen Android gave, masked and bounded. */
        data class Seen(val snapshot: AppControl.Snapshot) : Read

        /**
         * No readable screen. [code] is stable ([AppControl.CODE_BLANK_TREE]),
         * [sentence] is the plain words to show, and [app] is the app Android
         * named for it, when it named one ("" when it did not).
         */
        data class Unreadable(
            val app: String,
            val code: String,
            val sentence: String,
        ) : Read
    }

    // The window in front, from Android's own events. Never the screen's words.
    private var foregroundPackage: String = ""
    private var foregroundTitle: String = ""

    override fun onServiceConnected() {
        super.onServiceConnected()
        live = this
    }

    override fun onDestroy() {
        if (live === this) live = null
        super.onDestroy()
    }

    override fun onInterrupt() {
        // Android asking this service to stop. Nothing is held, so nothing to drop.
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return
        when (event.eventType) {
            AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED -> {
                foregroundPackage = event.packageName?.toString().orEmpty()
                foregroundTitle = shortClassName(event.packageName?.toString(), event.className?.toString())
            }
            AccessibilityEvent.TYPE_WINDOWS_CHANGED,
            AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED -> {
                if (foregroundPackage.isEmpty()) {
                    foregroundPackage = event.packageName?.toString().orEmpty()
                }
            }
            else -> Unit
        }
    }

    /**
     * The masked screen: the app and window in front, then the controls the PC
     * needs to name ONE step. Bounded ([AppControl.MAX_CONTROLS] controls, a
     * depth and visit limit) and masked by [AppControl.mask] - password and
     * invisible nodes never enter it.
     *
     * It never returns null and never returns an empty screen as if that were a
     * real one: with no window, no app, or not one readable/actionable node, the
     * answer is [Read.Unreadable] carrying `ui_tree_blank` and a plain sentence,
     * which the runtime reports. Nothing is sent to the PC in that case, and no
     * picture or guessed pixel is used to fill the gap.
     */
    fun readScreen(): Read {
        val root = rootInActiveWindow
            ?: return Read.Unreadable(
                foregroundPackage,
                AppControl.CODE_BLANK_TREE,
                AppControl.BLANK_TREE,
            )
        // Compose/RecyclerView update in place without a window-state event, so
        // the cached root can be stale: ask Android for the tree again first.
        runCatching { root.refresh() }
        val app = root.packageName?.toString()?.takeIf { it.isNotBlank() } ?: foregroundPackage
        if (app.isBlank()) {
            return Read.Unreadable("", AppControl.CODE_BLANK_TREE, AppControl.BLANK_TREE)
        }
        val title = foregroundTitle.ifBlank { shortClassName(app, root.className?.toString()) }
        val controls = ArrayList<AppControl.Control>(AppControl.MAX_CONTROLS)
        var usable = 0
        val queue = ArrayDeque<Pair<AccessibilityNodeInfo, Int>>()
        queue.add(root to 0)
        var visited = 0
        while (queue.isNotEmpty() && controls.size < AppControl.MAX_CONTROLS && visited < MAX_VISITED) {
            val (node, depth) = queue.removeFirst()
            visited += 1
            // A sensitive field is skipped WHOLE, before any text is read from
            // it or from anything inside it: Android's isPassword, a password
            // inputType variation (a "show password" eye keeps the inputType),
            // and API 34+'s own accessibility-sensitive flag (Gemini, 2026-10-20).
            if (sensitive(node)) continue
            val rect = Rect()
            val visible = node.isVisibleToUser
            if (visible) {
                val masked = AppControl.mask(
                    id = node.viewIdResourceName,
                    text = node.text?.toString(),
                    cls = node.className?.toString(),
                    bounds = boundsOf(node, rect),
                    password = false, // already skipped above, checked first
                    invisible = false,
                    // text ?: contentDescription ?: hintText - a Compose/Material
                    // icon button has only a contentDescription, and an empty
                    // field only its placeholder (Gemini, 2026-10-20).
                    hint = node.contentDescription?.toString() ?: node.hintText?.toString(),
                    clickable = node.isClickable,
                    editable = node.isEditable,
                    scrollable = node.isScrollable,
                )
                if (masked != null) {
                    controls.add(masked)
                    usable += 1
                } else if (node.isClickable || node.isEditable || node.isScrollable) {
                    // An unlabelled icon button still counts: the screen is not
                    // blank just because this snapshot cannot name the control.
                    usable += 1
                }
            }
            if (depth < MAX_DEPTH) {
                for (index in 0 until node.childCount) {
                    val child = runCatching { node.getChild(index) }.getOrNull() ?: continue
                    queue.add(child to depth + 1)
                }
            }
        }
        if (AppControl.blankTree(hasWindow = true, usableNodes = usable)) {
            return Read.Unreadable(app, AppControl.CODE_BLANK_TREE, AppControl.BLANK_TREE)
        }
        return Read.Seen(AppControl.Snapshot(app, title, controls))
    }

    /**
     * Performs the ONE approved step. Called on the main thread by
     * [AppControlExecutor]; nothing here loops, retries, or picks another
     * control: a step that no longer matches this screen is REFUSED, so the
     * executor reports it and the PC stops the run.
     */
    fun performStep(step: AppControl.Step, planApp: String): Outcome {
        val root = rootInActiveWindow
            ?: return Outcome.Refused(AppControl.BLANK_TREE, AppControl.CODE_BLANK_TREE)
        if (planApp.isNotBlank() && root.packageName?.toString() != planApp) {
            // The wrong app is in front: never act on it.
            return Outcome.Refused(AppControl.said(AppControl.Why.TARGET_CHANGED))
        }
        return when (step.action) {
            "back" -> if (performGlobalAction(GLOBAL_ACTION_BACK)) Outcome.Done else refusedGlobal()
            "home" -> if (performGlobalAction(GLOBAL_ACTION_HOME)) Outcome.Done else refusedGlobal()
            "tap" -> tap(step)
            "type" -> type(step)
            "swipe" -> swipe(step)
            else -> Outcome.Refused(AppControl.said(AppControl.Why.VERB))
        }
    }

    private fun refusedGlobal() =
        Outcome.Refused("Android would not perform that action just now, so nothing ran.")

    private fun tap(step: AppControl.Step): Outcome {
        val target = step.target ?: return Outcome.Refused(AppControl.said(AppControl.Why.VERB))
        val node = find(rootInActiveWindow, target)
        if (node != null) {
            if (sensitive(node)) return Outcome.Refused(AppControl.said(AppControl.Why.PASSWORD))
            // The ladder: click the node itself, then up to three same-package
            // parents (a list row's listener sits on the parent while the words
            // sit on a non-clickable child), then one guarded gesture. Gemini's
            // review, 2026-10-20.
            val parents = ArrayList<Pair<Boolean, Boolean>>()
            var parent = node.parent
            var climbed = 0
            while (climbed < 3) {
                val p = parent ?: break
                parents.add(p.isClickable to sensitive(p))
                parent = p.parent
                climbed += 1
            }
            val rung = AppControl.tapRung(node.isClickable, parents)
            if (rung >= 0) {
                val startNode: AccessibilityNodeInfo = node
                var clicked: AccessibilityNodeInfo = startNode
                repeat(rung) { clicked = clicked.parent ?: clicked }
                if (clicked.isVisibleToUser &&
                    clicked.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                ) {
                    return Outcome.Done
                }
            }
        }
        // No clickable match: the approved target's own area, AND ONLY IT, and
        // only when no other window covers the point.
        if (target.bounds.size == 4) {
            val rect = Rect(target.bounds[0], target.bounds[1], target.bounds[2], target.bounds[3])
            val x = rect.exactCenterX()
            val y = rect.exactCenterY()
            if (coveredByAnotherWindow(x, y)) {
                return Outcome.Refused(
                    "Another window covers that part of the screen, so nothing was tapped.",
                )
            }
            if (dispatchTap(x, y)) return Outcome.Done
        }
        return Outcome.Refused(AppControl.said(AppControl.Why.TARGET_CHANGED))
    }

    /**
     * True when a window other than the active app's covers this point (an IME
     * or an overlay): a coordinate tap there would land on the wrong thing.
     */
    private fun coveredByAnotherWindow(x: Float, y: Float): Boolean {
        val active = rootInActiveWindow ?: return false
        val mine = active.windowId
        val point = Rect(x.toInt(), y.toInt(), x.toInt() + 1, y.toInt() + 1)
        return runCatching {
            windows.any { window ->
                if (window.id == mine) return@any false
                val root = window.root ?: return@any false
                val bounds = Rect()
                root.getBoundsInScreen(bounds)
                bounds.intersect(point) && root.packageName?.toString() != active.packageName?.toString()
            }
        }.getOrDefault(false)
    }

    private fun type(step: AppControl.Step): Outcome {
        val target = step.target ?: return Outcome.Refused(AppControl.said(AppControl.Why.VERB))
        val found = find(rootInActiveWindow, target)
            ?: return Outcome.Refused(AppControl.said(AppControl.Why.TARGET_CHANGED))
        // Checked BEFORE the text is looked at, and before anything is typed.
        if (sensitive(found)) return Outcome.Refused(AppControl.said(AppControl.Why.PASSWORD))
        val node = editableTarget(found)
            ?: return Outcome.Refused("That control is not a text field, so nothing was typed.")
        val text = step.text.orEmpty().take(AppControl.MAX_TEXT)
        node.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        if (!node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)) {
            return Outcome.Refused("Android would not type into that field, so nothing changed.")
        }
        // Android's own "true" is not proof the field kept the words. Read the
        // field back (refreshed, because the cached node can still hold the old
        // text) and only then say Done - a model must never be told "done" for
        // a field that is still empty.
        runCatching { node.refresh() }
        val readBack = runCatching { node.text?.toString() }.getOrNull()
        if (!AppControl.textTook(text, readBack)) {
            return Outcome.Refused(AppControl.TEXT_NOT_TAKEN, AppControl.CODE_TEXT_NOT_TAKEN)
        }
        return Outcome.Done
    }

    /**
     * The node to type into: [found] itself when it is editable, else exactly
     * one editable, non-password child (depth 1-2) - a TextInputLayout's label
     * is the node the words sit on, its EditText is one level down. Gemini's
     * review, 2026-10-20.
     */
    private fun editableTarget(found: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        if (found.isEditable) return found
        if (sensitive(found)) return null
        val candidates = ArrayList<AccessibilityNodeInfo>()
        val queue = ArrayDeque<Pair<AccessibilityNodeInfo, Int>>()
        for (index in 0 until found.childCount) {
            val child = runCatching { found.getChild(index) }.getOrNull() ?: continue
            queue.add(child to 1)
        }
        while (queue.isNotEmpty()) {
            val (node, depth) = queue.removeFirst()
            if (sensitive(node)) continue
            if (node.isEditable) {
                candidates.add(node)
                if (candidates.size > 1) return null
            }
            if (depth < 2) {
                for (index in 0 until node.childCount) {
                    val child = runCatching { node.getChild(index) }.getOrNull() ?: continue
                    queue.add(child to depth + 1)
                }
            }
        }
        return candidates.singleOrNull()
    }

    private fun swipe(step: AppControl.Step): Outcome {
        val target = step.target ?: return Outcome.Refused(AppControl.said(AppControl.Why.VERB))
        if (target.bounds.size != 4) {
            return Outcome.Refused(AppControl.said(AppControl.Why.TARGET_CHANGED))
        }
        val rect = Rect(target.bounds[0], target.bounds[1], target.bounds[2], target.bounds[3])
        if (rect.width() <= 0 || rect.height() <= 0) {
            return Outcome.Refused(AppControl.said(AppControl.Why.TARGET_CHANGED))
        }
        // Semantic scroll first: a small model says "scroll", and the
        // scrollable ancestor is what Android's own action can move.
        val node = find(rootInActiveWindow, target)
        if (node != null && !sensitive(node)) {
            var parent: AccessibilityNodeInfo? = node
            var climbed = 0
            while (climbed < 6) {
                val p = parent ?: break
                if (p.isScrollable &&
                    p.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD)
                ) {
                    return Outcome.Done
                }
                parent = p.parent
                climbed += 1
            }
        }
        // No scrollable ancestor (or its action was refused): a pixel gesture
        // clamped inside the target AND the screen's central 15%-85% band, so
        // an edge swipe can never trigger Back or the notification shade.
        val metrics = resources.displayMetrics
        val points = AppControl.swipePoints(target.bounds, metrics.widthPixels, metrics.heightPixels)
            ?: return Outcome.Refused(AppControl.said(AppControl.Why.TARGET_CHANGED))
        val y = rect.exactCenterY()
        val path = Path().apply {
            moveTo(points.first, y)
            lineTo(points.second, y)
        }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0L, SWIPE_MS))
            .build()
        if (dispatchGesture(gesture, null, null)) return Outcome.Done
        return Outcome.Refused("Android would not perform that swipe, so nothing ran.")
    }

    /** The wider sensitivity rule, in one place for the whole service. */
    private fun sensitive(node: AccessibilityNodeInfo): Boolean =
        AppControl.sensitiveInput(
            isPassword = node.isPassword,
            inputType = node.inputType,
            isDataSensitive = Build.VERSION.SDK_INT >= 34 && node.isAccessibilityDataSensitive,
            sdk = Build.VERSION.SDK_INT,
        )

    private fun dispatchTap(x: Float, y: Float): Boolean {
        val path = Path().apply { moveTo(x, y) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0L, 60L))
            .build()
        return dispatchGesture(gesture, null, null)
    }

    /**
     * Finds the approved control on THIS screen. The PC's target carries the
     * view id and the words the card showed; both must still match, and a
     * password node is never returned.
     */
    private fun find(root: AccessibilityNodeInfo?, target: AppControl.Control): AccessibilityNodeInfo? {
        if (root == null) return null
        val queue = ArrayDeque<Pair<AccessibilityNodeInfo, Int>>()
        queue.add(root to 0)
        var visited = 0
        while (queue.isNotEmpty() && visited < MAX_VISITED) {
            val (node, depth) = queue.removeFirst()
            visited += 1
            if (sensitive(node)) continue
            val id = node.viewIdResourceName.orEmpty()
            val text = node.text?.toString() ?: node.contentDescription?.toString() ?: ""
            val idMatches = target.id.isNotEmpty() && id == target.id
            val textMatches = target.text.isNotEmpty() && text == target.text
            val matches = if (target.id.isNotEmpty()) {
                idMatches && (target.text.isEmpty() || textMatches)
            } else {
                textMatches
            }
            if (matches && node.isVisibleToUser) return node
            if (depth < MAX_DEPTH) {
                for (index in 0 until node.childCount) {
                    val child = runCatching { node.getChild(index) }.getOrNull() ?: continue
                    queue.add(child to depth + 1)
                }
            }
        }
        return null
    }

    private fun boundsOf(node: AccessibilityNodeInfo, rect: Rect): List<Int> {
        node.getBoundsInScreen(rect)
        return listOf(rect.left, rect.top, rect.right, rect.bottom)
    }

    private fun shortClassName(packageName: String?, className: String?): String {
        val name = className?.trim().orEmpty()
        if (name.isEmpty()) return ""
        val pkg = packageName?.trim().orEmpty()
        if (pkg.isNotEmpty() && name.startsWith("$pkg.")) return name.removePrefix("$pkg.")
        return name.substringAfterLast('.')
    }

    companion object {
        @Volatile
        private var live: JarvisAccessibilityService? = null

        /** True only while Android has this service connected. */
        fun connected(): Boolean = live != null

        /** The service, for the executor - null when Android has not connected it. */
        fun instance(): JarvisAccessibilityService? = live

        private const val MAX_VISITED = 400
        private const val MAX_DEPTH = 25
        private const val SWIPE_MS = 300L
    }
}
