package com.jarvis.client.assistant

import android.app.assist.AssistStructure
import android.view.View
import com.jarvis.client.net.ScreenText

/**
 * Android's `AssistStructure` (what the assistant gesture hands over: the
 * text and layout of the screen in front) as plain [ScreenText.Node]s - the
 * rules for what is read and what is left out live in [ScreenText], which has
 * no Android in it and is tested on the JVM. This file only COPIES what the
 * system says about each view; it decides nothing.
 *
 * What is copied, and for what:
 *  - the view's text, hint and id name, its input type and autofill hints
 *    ([ScreenText.isSecretField] drops password, card and one-time-code
 *    fields from those, and the words inside them);
 *  - a web page's own `<input type="password">` (`htmlInfo`): Chrome and
 *    WebView describe a web password box this way and not always by input
 *    type, so it is turned into the same "web password" input type;
 *  - whether the view is visible, and whether its app said it must not be
 *    assisted (`isAssistBlocked`: a secure window gives no text at all).
 *
 * UNVERIFIED on a real phone (docs/SCREEN-DESIGN.md section 3): how complete
 * the structure is on Android 14 and 15, on GrapheneOS, and for Compose,
 * Flutter or web content. An app that draws its own text, or blocks
 * assistance, gives little or nothing - and the answer then says plainly
 * that Jarvis could not read any words there.
 */
object AssistReader {

    /** The window trees of [structure], in order, as plain nodes. */
    fun nodes(structure: AssistStructure?): List<ScreenText.Node> {
        if (structure == null) return emptyList()
        val budget = IntArray(1) { ScreenText.MAX_NODES }
        val out = ArrayList<ScreenText.Node>()
        val windows = runCatching { structure.windowNodeCount }.getOrDefault(0)
        for (i in 0 until windows) {
            val root = runCatching { structure.getWindowNodeAt(i).rootViewNode }.getOrNull() ?: continue
            out += convert(root, 0, budget)
            if (budget[0] <= 0) break
        }
        return out
    }

    /** The package of the app whose screen this is, or null when the system did not say. */
    fun packageOf(structure: AssistStructure?): String? =
        runCatching { structure?.activityComponent?.packageName }.getOrNull()

    private fun convert(n: AssistStructure.ViewNode, depth: Int, budget: IntArray): ScreenText.Node {
        budget[0] -= 1
        val children = ArrayList<ScreenText.Node>()
        if (depth < ScreenText.MAX_DEPTH && budget[0] > 0) {
            val count = runCatching { n.childCount }.getOrDefault(0)
            for (i in 0 until count) {
                if (budget[0] <= 0) break
                val child = runCatching { n.getChildAt(i) }.getOrNull() ?: continue
                children += convert(child, depth + 1, budget)
            }
        }
        return ScreenText.Node(
            text = runCatching { n.text?.toString() }.getOrNull(),
            hint = runCatching { n.hint }.getOrNull(),
            idName = runCatching { n.idEntry }.getOrNull(),
            inputType = inputTypeOf(n),
            autofillHints = runCatching { n.autofillHints?.toList() }.getOrNull().orEmpty(),
            visible = runCatching { n.visibility == View.VISIBLE }.getOrDefault(false),
            blocked = runCatching { n.isAssistBlocked }.getOrDefault(true),
            children = children,
        )
    }

    /** The view's input type, or "web password" for a page's password `<input>`. */
    private fun inputTypeOf(n: AssistStructure.ViewNode): Int {
        val type = runCatching { n.inputType }.getOrDefault(0)
        val html = runCatching { n.htmlInfo }.getOrNull() ?: return type
        val isInput = html.tag?.equals("input", ignoreCase = true) == true
        // The pairs are android.util.Pair (fields first/second), not Kotlin's.
        val passwordBox = html.attributes.orEmpty().any { p ->
            p.first.equals("type", ignoreCase = true) && p.second.equals("password", ignoreCase = true)
        }
        return if (isInput && passwordBox) {
            ScreenText.TYPE_CLASS_TEXT or ScreenText.TEXT_VARIATION_WEB_PASSWORD
        } else {
            type
        }
    }
}
