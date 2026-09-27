package com.jarvis.client.platform

import android.content.ClipData
import android.content.ClipDescription
import android.content.ClipboardManager
import android.content.Context
import android.os.PersistableBundle
import androidx.core.content.ContextCompat

/**
 * "Private copy" (feasibility I114, docs/FEASIBILITY-AUDIT-2026-09-26.md:
 * "Needs a small Rust command (Devil); hide preview on the phone.") - the
 * phone half. The desktop's own half (`clipboard_privacy.rs`, excluding a
 * copied answer from Windows Clipboard History and Cloud Clipboard sync)
 * has nothing to mirror here: Android has no OS-wide clipboard history or
 * cross-device clipboard sync feature for an app to opt a clip out of.
 *
 * What Android DOES have, since API 33 (this app's own `minSdk`, so no
 * version check is needed anywhere below): starting with Android 13, the
 * system shows a small toast previewing whatever text an app just copied -
 * "Answer copied", with the words themselves visible on screen for a moment,
 * to anyone glancing at the phone. [ClipDescription.EXTRA_IS_SENSITIVE] on
 * the `ClipData` tells the system to show a plain "Content copied" toast
 * instead, with no preview of the words - the same reasoning as the
 * desktop's own change: an answer that never left this PC (or phone) over
 * Jarvis's own network should not casually leave it through the platform's
 * own convenience features either.
 *
 * Scope, on purpose: only `HomeScreen.kt`'s own Copy button for a Jarvis
 * answer calls this - the phone's direct parity with the desktop's answer
 * Copy button that [copy] mirrors. `CrashScreen.kt`'s own Copy (a crash
 * report to paste into a bug report, not an answer) is untouched: nothing
 * in the feasibility idea's own wording ("hide preview on the phone") asks
 * for that, and a bug report is written to be read, not kept private.
 */
object PrivateClipboard {

    /** The clip's plain label, shown nowhere the owner sees a preview -
     *  Android's clipboard inspector (Settings > Privacy) shows the label
     *  next to whichever app pastes it, never the system's own copy toast. */
    private const val LABEL = "Jarvis answer"

    /**
     * Copies `text` to the system clipboard, marked
     * [ClipDescription.EXTRA_IS_SENSITIVE] so Android's own copy toast
     * shows no preview of it. Safe to call even where the clipboard
     * service is unavailable (a stripped-down system image): a missing
     * service is treated the same as "nothing to copy to", never a crash.
     */
    fun copy(context: Context, text: String) {
        val manager = ContextCompat.getSystemService(context, ClipboardManager::class.java)
            ?: return
        val clip = ClipData.newPlainText(LABEL, text)
        clip.description.extras = PersistableBundle().apply {
            putBoolean(ClipDescription.EXTRA_IS_SENSITIVE, true)
        }
        manager.setPrimaryClip(clip)
    }
}
