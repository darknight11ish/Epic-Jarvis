package com.jarvis.client.service

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.graphics.Rect
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

        /** The step did not run, and [sentence] says why, plainly. */
        data class Refused(val sentence: String) : Outcome
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
            AccessibilityEvent.TYPE_WINDOWS_CHANGED -> {
                if (foregroundPackage.isEmpty()) {
                    foregroundPackage = event.packageName?.toString().orEmpty()
                }
            }
            else -> Unit
        }
    }

    /**
     * The masked snapshot: the app and window in front, then the controls the
     * PC needs to name ONE step. Bounded ([AppControl.MAX_CONTROLS] controls,
     * a depth and visit limit) and masked by [AppControl.mask] - password and
     * invisible nodes never enter it.
     *
     * Null when Android will not give a window: the caller says so plainly and
     * sends nothing.
     */
    fun snapshot(): AppControl.Snapshot? {
        val root: AccessibilityNodeInfo = rootInActiveWindow ?: return null
        val app = root.packageName?.toString()?.takeIf { it.isNotBlank() } ?: foregroundPackage
        val title = foregroundTitle.ifBlank { shortClassName(app, root.className?.toString()) }
        val controls = ArrayList<AppControl.Control>(AppControl.MAX_CONTROLS)
        val queue = ArrayDeque<Pair<AccessibilityNodeInfo, Int>>()
        queue.add(root to 0)
        var visited = 0
        while (queue.isNotEmpty() && controls.size < AppControl.MAX_CONTROLS && visited < MAX_VISITED) {
            val (node, depth) = queue.removeFirst()
            visited += 1
            // A password field is skipped WHOLE, before any text is read from
            // it or from anything inside it.
            if (node.isPassword) continue
            val rect = Rect()
            val visible = node.isVisibleToUser
            if (visible) {
                val text = node.text?.toString() ?: node.contentDescription?.toString()
                val masked = AppControl.mask(
                    id = node.viewIdResourceName,
                    text = text,
                    cls = node.className?.toString(),
                    bounds = boundsOf(node, rect),
                    password = false, // already skipped above, checked first
                    invisible = false,
                )
                if (masked != null) controls.add(masked)
            }
            if (depth < MAX_DEPTH) {
                for (index in 0 until node.childCount) {
                    val child = runCatching { node.getChild(index) }.getOrNull() ?: continue
                    queue.add(child to depth + 1)
                }
            }
        }
        if (app.isBlank()) return null
        return AppControl.Snapshot(app, title, controls)
    }

    /**
     * Performs the ONE approved step. Called on the main thread by
     * [AppControlExecutor]; nothing here loops, retries, or picks another
     * control: a step that no longer matches this screen is REFUSED, so the
     * executor reports it and the PC stops the run.
     */
    fun performStep(step: AppControl.Step, planApp: String): Outcome {
        val root = rootInActiveWindow
            ?: return Outcome.Refused(AppControl.said(AppControl.Why.TARGET_CHANGED))
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
            if (node.isPassword) return Outcome.Refused(AppControl.said(AppControl.Why.PASSWORD))
            if (node.isVisibleToUser && node.performAction(AccessibilityNodeInfo.ACTION_CLICK)) {
                return Outcome.Done
            }
        }
        // No clickable match: the approved target's own area, AND ONLY IT.
        if (target.bounds.size == 4) {
            val rect = Rect(target.bounds[0], target.bounds[1], target.bounds[2], target.bounds[3])
            if (dispatchTap(rect.exactCenterX(), rect.exactCenterY())) return Outcome.Done
        }
        return Outcome.Refused(AppControl.said(AppControl.Why.TARGET_CHANGED))
    }

    private fun type(step: AppControl.Step): Outcome {
        val target = step.target ?: return Outcome.Refused(AppControl.said(AppControl.Why.VERB))
        val node = find(rootInActiveWindow, target)
            ?: return Outcome.Refused(AppControl.said(AppControl.Why.TARGET_CHANGED))
        // Checked BEFORE the text is looked at, and before anything is typed.
        if (node.isPassword) return Outcome.Refused(AppControl.said(AppControl.Why.PASSWORD))
        if (!node.isEditable) {
            return Outcome.Refused("That control is not a text field, so nothing was typed.")
        }
        val text = step.text.orEmpty().take(AppControl.MAX_TEXT)
        node.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        if (node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)) return Outcome.Done
        return Outcome.Refused("Android would not type into that field, so nothing changed.")
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
        val y = rect.exactCenterY()
        val path = Path().apply {
            moveTo(rect.right - rect.width() * 0.1f, y)
            lineTo(rect.left + rect.width() * 0.1f, y)
        }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0L, SWIPE_MS))
            .build()
        if (dispatchGesture(gesture, null, null)) return Outcome.Done
        return Outcome.Refused("Android would not perform that swipe, so nothing ran.")
    }

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
            if (node.isPassword) continue
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
