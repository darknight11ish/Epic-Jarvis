package com.jarvis.client.widget

import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.content.Context
import com.jarvis.client.net.JarvisWidgets

/**
 * "Put it on my home screen" (the owner, 2026-10-30): the phone asks the
 * launcher to place the widget of one slot, instead of only printing the
 * touch-and-hold route. The words are [JarvisWidgets.pinSentence] so only the
 * Android call lives here.
 *
 * Three honest outcomes, and never a fourth:
 *  - the slot's widget is already on the home screen -> say so, ask nothing;
 *  - the launcher took the request -> "was asked ... if it asks you to
 *    confirm, say yes" (Android's API returns whether the REQUEST was sent, not
 *    whether a widget was placed, and a launcher may still say no);
 *  - this launcher cannot add widgets on request (`isRequestPinAppWidgetSupported`
 *    false, or the request returned false/refused) -> say so in words and give
 *    the touch-and-hold route.
 *
 * Nothing is sent to the PC, no card is raised and the pin never changes which
 * saved widget a slot shows - that stays in the slot picker.
 */
internal object WidgetPin {
    /** The provider Android knows for a slot, or null for a slot this app does
     *  not ship (the picker only offers [JarvisWidgets.SLOTS]). */
    fun provider(context: Context, slot: Int): ComponentName? =
        JarvisWidgets.PIN_RECEIVERS.getOrNull(slot)?.let {
            ComponentName(context.packageName, context.packageName + it)
        }

    /** Ask the launcher, and answer with the one sentence that is true after
     *  the call. The caller shows it where it already shows Add/Delete news. */
    fun request(context: Context, slot: Int): String {
        val provider = provider(context, slot)
            ?: return JarvisWidgets.pinSentence(false, false, slot)
        val manager = AppWidgetManager.getInstance(context)
        val alreadyThere = runCatching { manager.getAppWidgetIds(provider).isNotEmpty() }.getOrDefault(false)
        if (alreadyThere) return JarvisWidgets.pinSentence(false, true, slot)
        val supported = runCatching { manager.isRequestPinAppWidgetSupported }.getOrDefault(false)
        if (!supported) return JarvisWidgets.pinSentence(false, false, slot)
        val asked = runCatching { manager.requestPinAppWidget(provider, null, null) }.getOrDefault(false)
        return JarvisWidgets.pinSentence(asked, false, slot)
    }
}
