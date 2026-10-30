package com.jarvis.client.service

import android.content.Context
import android.view.View
import android.widget.RemoteViews
import androidx.core.app.NotificationCompat
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.R
import com.jarvis.client.net.NotificationStyle

/**
 * Draws a notification the owner styled (2026-10-30; see
 * [NotificationStyle] and docs/JARVIS-API.md section 163).
 *
 * This file is the ONLY place that touches RemoteViews, and it does three
 * things: ask [NotificationStyle.plan] whether a style applies (it can say
 * no), put the SAME title and body the notifier already had into a custom
 * layout, and set the one animation's parameters. It adds no text of its own,
 * no button, no intent and no data.
 *
 * THE ANIMATION IS SYSTEMUI'S. The custom layout is inflated and animated in
 * SystemUI's process - `ViewFlipper` with `autoStart` plus a remote flip
 * interval, or an indeterminate `ProgressBar`. Nothing here posts a frame, so
 * a style keeps working when Jarvis' process has been killed, and a two-frame
 * pulse costs the phone no wakeups. A frame posted with `notify()` would need
 * the process alive and would be capped by the platform's enqueue rate
 * (`DEFAULT_MAX_NOTIFICATION_ENQUEUE_RATE = 5f`); that is why the menu has no
 * "many frames" option.
 *
 * THE PRIVACY FLOOR IS THE FIRST LINE OF [apply]. When App lock, "Hide memory
 * lists and chat history" or a phone with no secure lock screen is in force,
 * [NotificationStyle.plan] returns null and this object does nothing at all:
 * the notification is built exactly as it was before this feature existed, so
 * the redacted path never even meets the pretty layout.
 */
object StyledNotification {

    /**
     * Applies the owner's style for [kind] to [b], or leaves it untouched.
     *
     * @param kind which notification this is ([NotificationStyle.Kind]).
     * @param title the title the notifier already decided on, already redacted.
     * @param body the body the notifier already decided on, already redacted.
     * @param locked [com.jarvis.client.data.SecurityRules.notificationsLocked]'s
     *   answer for this phone right now. True: no custom layout, ever.
     */
    fun apply(
        b: NotificationCompat.Builder,
        context: Context,
        kind: NotificationStyle.Kind,
        title: String,
        body: String,
        locked: Boolean,
    ) {
        val plan = NotificationStyle.plan(
            JarvisRuntime.notificationStyles.value.forKind(kind),
            kind,
            locked,
        ) ?: return
        b.setStyle(NotificationCompat.DecoratedCustomViewStyle())
        b.setCustomContentView(content(context, plan, title, body, expanded = false))
        b.setCustomBigContentView(content(context, plan, title, body, expanded = true))
    }

    /**
     * One custom layout. The collapsed and expanded files are the same shape;
     * the expanded one has room for the whole body, so a style never shortens
     * what the notification says.
     */
    private fun content(
        context: Context,
        plan: NotificationStyle.Plan,
        title: String,
        body: String,
        expanded: Boolean,
    ): RemoteViews {
        val layout = if (expanded) R.layout.notification_styled_expanded else R.layout.notification_styled
        val rv = RemoteViews(context.packageName, layout)
        // The chip is a dark palette step and the glyph a bright one, both
        // chosen on the PHONE from the theme's NAME - so the figure stays
        // readable whatever colour the shade's own background has, and the PC
        // never sends a colour value.
        rv.setInt(R.id.style_chip, "setBackgroundColor", plan.chip)
        if (plan.frames.isNotEmpty()) {
            // Two frames, added as nested RemoteViews: ViewFlipper will start
            // itself (autoStart in the layout) and flip at the interval set
            // here. Everything below happens in SystemUI.
            rv.setViewVisibility(R.id.style_still, View.GONE)
            rv.setInt(R.id.style_frames, "setFlipInterval", plan.intervalMs)
            for (frame in plan.frames) {
                val one = RemoteViews(context.packageName, R.layout.notification_style_frame)
                one.setTextViewText(R.id.style_glyph, frame.glyph)
                one.setTextColor(R.id.style_glyph, frame.colour)
                rv.addView(R.id.style_frames, one)
            }
        } else {
            // Nothing to flip: one glyph outside the flipper, and the flipper
            // itself costs nothing (a single frame, a very long interval).
            rv.setViewVisibility(R.id.style_frames, View.GONE)
            val glyph = plan.stillGlyph.orEmpty()
            rv.setTextViewText(R.id.style_still, glyph)
            rv.setTextColor(R.id.style_still, plan.theme.accent)
            rv.setViewVisibility(R.id.style_still, if (glyph.isEmpty()) View.GONE else View.VISIBLE)
        }
        rv.setViewVisibility(R.id.style_spinner, if (plan.spinner) View.VISIBLE else View.GONE)
        rv.setTextViewText(R.id.style_title, title)
        rv.setTextViewText(R.id.style_body, body)
        return rv
    }
}
