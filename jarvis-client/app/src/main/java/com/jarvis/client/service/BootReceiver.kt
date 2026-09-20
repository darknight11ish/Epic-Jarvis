package com.jarvis.client.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.jarvis.client.JarvisRuntime

/**
 * Restarts the link after a reboot or an app update.
 *
 * The service is otherwise only ever started by the button on the readiness
 * screen, so a phone rebooted overnight had no connection in the morning and
 * nothing on the device said so.
 *
 * `BOOT_COMPLETED` is a documented exemption to the background
 * foreground-service start restriction, which is why this works where the sticky
 * restart the system performs on its own does not.
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED,
            Intent.ACTION_MY_PACKAGE_REPLACED,
            -> {
                // Only a paired phone has a link to restart. Unpaired, this
                // posted a foreground notification and looped on 401s until
                // the owner noticed - on a phone that had never been told a
                // desktop address. `isPaired()` needs the runtime, which is
                // not necessarily up in a receiver-only process start, so it
                // is initialised here first; it is cheap and idempotent.
                runCatching { JarvisRuntime.initialize(context) }
                if (!JarvisRuntime.isPaired()) {
                    Log.i(TAG, "not paired; nothing to restart after ${intent.action}")
                    return
                }
                Log.i(TAG, "restarting link after ${intent.action}")
                EventService.start(context)
            }
        }
    }

    private companion object {
        const val TAG = "JarvisClientBoot"
    }
}
