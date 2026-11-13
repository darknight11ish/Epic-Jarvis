package com.jarvis.client.localai

import android.app.ActivityManager
import android.content.Context

/**
 * Reads the three numbers [DeviceTiers] needs from a real phone - total RAM,
 * Android's per-app heap class and the number of processor cores - and hands
 * them to the pure table.
 *
 * Kept apart from [DeviceTiers] so every boundary of the tier table and every
 * refusal sentence can be tested on a JVM, where no `ActivityManager` exists.
 * The only Android call here is a read: nothing is changed on the phone, no
 * permission is needed for `totalMem` or `memoryClass`, and nothing is sent
 * anywhere.
 */
object DeviceTiersAndroid {

    /**
     * This phone's recommendation. A phone that cannot answer (a null
     * `ActivityManager`, which no real phone has) is treated as having an
     * unknown amount of RAM, which [DeviceTiers] handles conservatively.
     */
    fun read(context: Context): DeviceTiers.Tier {
        val manager = context.getSystemService(ActivityManager::class.java)
        var totalRamBytes = 0L
        var memoryClassMb = 0
        if (manager != null) {
            val memory = ActivityManager.MemoryInfo()
            runCatching { manager.getMemoryInfo(memory) }
                .onSuccess { totalRamBytes = memory.totalMem }
            memoryClassMb = manager.memoryClass
        }
        return DeviceTiers.of(
            totalRamBytes = totalRamBytes,
            memoryClassMb = memoryClassMb,
            cores = Runtime.getRuntime().availableProcessors(),
        )
    }
}
