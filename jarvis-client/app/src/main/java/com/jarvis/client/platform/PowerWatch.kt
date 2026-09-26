package com.jarvis.client.platform

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.PowerManager
import android.util.Log
import androidx.core.content.ContextCompat

/**
 * Listens for the phone's own Battery Saver and for heat, for the face
 * editor's Battery saver and Auto adjust (see `FaceBudget`).
 *
 * Listened for rather than polled, unlike [DisplayRate.constrained]: the face
 * should drop to battery-saver drawing the moment Android's Battery Saver
 * comes on, not a few seconds later. `ACTION_POWER_SAVE_MODE_CHANGED` is a
 * system broadcast, so registering it NOT_EXPORTED still receives it.
 */
object PowerWatch {

    /**
     * Android's thermal status as the face's heat level: 0 cool (up to LIGHT),
     * 1 warm (MODERATE), 2 hot (SEVERE or worse). The same MODERATE line
     * [DisplayRate.constrained] already uses.
     */
    fun heatLevel(status: Int): Int = when {
        status >= PowerManager.THERMAL_STATUS_SEVERE -> 2
        status >= PowerManager.THERMAL_STATUS_MODERATE -> 1
        else -> 0
    }

    /**
     * Calls [onChange] now, and again whenever Battery Saver or the heat level
     * changes, on the main thread. Returns the function that stops listening.
     * Anything that fails reads as "Battery Saver off, cool" - the face then
     * simply draws as it would have without this.
     */
    fun watch(context: Context, onChange: (saver: Boolean, heat: Int) -> Unit): () -> Unit {
        val app = context.applicationContext
        val pm = ContextCompat.getSystemService(app, PowerManager::class.java)
        if (pm == null) {
            onChange(false, 0)
            return {}
        }
        var saver = runCatching { pm.isPowerSaveMode }.getOrDefault(false)
        var heat = heatLevel(runCatching { pm.currentThermalStatus }.getOrDefault(PowerManager.THERMAL_STATUS_NONE))
        onChange(saver, heat)

        val receiver = object : BroadcastReceiver() {
            override fun onReceive(c: Context?, intent: Intent?) {
                saver = runCatching { pm.isPowerSaveMode }.getOrDefault(false)
                onChange(saver, heat)
            }
        }
        val registered = runCatching {
            app.registerReceiver(
                receiver,
                IntentFilter(PowerManager.ACTION_POWER_SAVE_MODE_CHANGED),
                Context.RECEIVER_NOT_EXPORTED,
            )
        }.onFailure { Log.w(TAG, "Battery Saver changes will not be seen", it) }.isSuccess

        val thermal = PowerManager.OnThermalStatusChangedListener { status ->
            heat = heatLevel(status)
            onChange(saver, heat)
        }
        val listening = runCatching {
            pm.addThermalStatusListener(ContextCompat.getMainExecutor(app), thermal)
        }.onFailure { Log.w(TAG, "heat changes will not be seen", it) }.isSuccess

        return {
            if (registered) runCatching { app.unregisterReceiver(receiver) }
            if (listening) runCatching { pm.removeThermalStatusListener(thermal) }
        }
    }

    private const val TAG = "JarvisPowerWatch"
}
