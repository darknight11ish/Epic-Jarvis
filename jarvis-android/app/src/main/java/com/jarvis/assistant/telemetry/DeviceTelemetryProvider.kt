package com.jarvis.assistant.telemetry

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.media.AudioManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.wifi.WifiManager
import android.os.BatteryManager
import android.os.Build
import android.os.PowerManager
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.util.Log
import androidx.core.content.ContextCompat
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** Result of a hardware action requested by the desktop. */
data class CommandOutcome(val ok: Boolean, val detail: String)

/**
 * Reads phone vitals and performs the hardware actions the desktop can invoke.
 *
 * Every accessor degrades to a null/failed result rather than throwing: the
 * desktop polls this on a timer and one missing sensor must not break the frame.
 */
class DeviceTelemetryProvider(context: Context) {

    private val appContext = context.applicationContext

    private val audioManager: AudioManager? =
        ContextCompat.getSystemService(appContext, AudioManager::class.java)
    private val cameraManager: CameraManager? =
        ContextCompat.getSystemService(appContext, CameraManager::class.java)
    private val connectivityManager: ConnectivityManager? =
        ContextCompat.getSystemService(appContext, ConnectivityManager::class.java)
    private val powerManager: PowerManager? =
        ContextCompat.getSystemService(appContext, PowerManager::class.java)

    @Volatile private var torchOn = false

    // ------------------------------------------------------------- battery ----

    private fun batteryIntent(): Intent? =
        appContext.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))

    fun batteryPercent(): Int? {
        val intent = batteryIntent() ?: return null
        val level = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
        val scale = intent.getIntExtra(BatteryManager.EXTRA_SCALE, -1)
        if (level < 0 || scale <= 0) return null
        return (level * 100f / scale).toInt()
    }

    /** One of: ac, usb, wireless, dock, unplugged. */
    fun chargingSource(): String {
        val intent = batteryIntent() ?: return "unknown"
        return when (intent.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0)) {
            BatteryManager.BATTERY_PLUGGED_AC -> "ac"
            BatteryManager.BATTERY_PLUGGED_USB -> "usb"
            BatteryManager.BATTERY_PLUGGED_WIRELESS -> "wireless"
            else -> "unplugged"
        }
    }

    fun isCharging(): Boolean {
        val status = batteryIntent()?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: return false
        return status == BatteryManager.BATTERY_STATUS_CHARGING ||
            status == BatteryManager.BATTERY_STATUS_FULL
    }

    // ------------------------------------------------------------- network ----

    /** wifi, cellular, ethernet, vpn or none. */
    fun activeTransport(): String {
        val cm = connectivityManager ?: return "unknown"
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return "none"
        return when {
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "wifi"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "cellular"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "ethernet"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN) -> "vpn"
            else -> "other"
        }
    }

    /**
     * The SSID is only readable with a location permission on API 29+. This app
     * does not request one, so expect null off Wi-Fi or on modern releases —
     * the transport type above is the reliable signal.
     */
    @Suppress("DEPRECATION")
    fun wifiSsid(): String? {
        if (activeTransport() != "wifi") return null
        val hasLocation = ContextCompat.checkSelfPermission(
            appContext,
            Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q && !hasLocation) return null

        val wifi = appContext.applicationContext
            .getSystemService(Context.WIFI_SERVICE) as? WifiManager ?: return null
        val ssid = runCatching { wifi.connectionInfo?.ssid }.getOrNull() ?: return null
        val cleaned = ssid.trim('"')
        return cleaned.takeUnless { it.isEmpty() || it == "<unknown ssid>" }
    }

    // ------------------------------------------------------------- actions ----

    private fun torchCameraId(): String? {
        val cm = cameraManager ?: return null
        return runCatching {
            cm.cameraIdList.firstOrNull { id ->
                cm.getCameraCharacteristics(id)
                    .get(CameraCharacteristics.FLASH_INFO_AVAILABLE) == true
            }
        }.getOrNull()
    }

    fun setTorch(enabled: Boolean): CommandOutcome {
        val cm = cameraManager ?: return CommandOutcome(false, "no camera service")
        val id = torchCameraId() ?: return CommandOutcome(false, "no flash unit")
        return runCatching {
            cm.setTorchMode(id, enabled)
            torchOn = enabled
            CommandOutcome(true, "torch ${if (enabled) "on" else "off"}")
        }.getOrElse { CommandOutcome(false, it.message ?: "setTorchMode failed") }
    }

    fun toggleTorch(): CommandOutcome = setTorch(!torchOn)

    fun mediaVolume(): Int =
        audioManager?.getStreamVolume(AudioManager.STREAM_MUSIC) ?: 0

    fun maxMediaVolume(): Int =
        audioManager?.getStreamMaxVolume(AudioManager.STREAM_MUSIC) ?: 0

    /** @param percent 0-100, clamped. */
    fun setMediaVolumePercent(percent: Int): CommandOutcome {
        val am = audioManager ?: return CommandOutcome(false, "no audio service")
        val max = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
        if (max <= 0) return CommandOutcome(false, "no media stream")
        val target = (percent.coerceIn(0, 100) * max + 50) / 100
        return runCatching {
            am.setStreamVolume(AudioManager.STREAM_MUSIC, target, 0)
            CommandOutcome(true, "volume $target/$max")
        }.getOrElse { CommandOutcome(false, it.message ?: "setStreamVolume failed") }
    }

    private fun vibrator(): Vibrator? =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            ContextCompat.getSystemService(appContext, VibratorManager::class.java)?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            ContextCompat.getSystemService(appContext, Vibrator::class.java)
        }

    /** `tick`, `confirm`, `alert` — distinct patterns so taps are identifiable blind. */
    fun vibrate(pattern: String = "tick"): CommandOutcome {
        val v = vibrator() ?: return CommandOutcome(false, "no vibrator")
        if (!v.hasVibrator()) return CommandOutcome(false, "no vibrator")
        val timings = when (pattern) {
            "confirm" -> longArrayOf(0, 40, 80, 40)
            "alert" -> longArrayOf(0, 120, 90, 120, 90, 220)
            else -> longArrayOf(0, 25)
        }
        val amplitudes = IntArray(timings.size) { index ->
            if (index % 2 == 0) 0 else VibrationEffect.DEFAULT_AMPLITUDE
        }
        return runCatching {
            v.vibrate(VibrationEffect.createWaveform(timings, amplitudes, -1))
            CommandOutcome(true, "vibrated $pattern")
        }.getOrElse { CommandOutcome(false, it.message ?: "vibrate failed") }
    }

    fun isIgnoringBatteryOptimizations(): Boolean =
        powerManager?.isIgnoringBatteryOptimizations(appContext.packageName) ?: false

    fun isInteractive(): Boolean = powerManager?.isInteractive ?: false

    // ------------------------------------------------------------ snapshot ----

    fun collectTelemetrySnapshot(): JsonObject = buildJsonObject {
        put("device_model", "${Build.MANUFACTURER} ${Build.MODEL}")
        put("android_release", Build.VERSION.RELEASE)
        put("sdk_int", Build.VERSION.SDK_INT)
        put("captured_at_ms", System.currentTimeMillis())

        batteryPercent()?.let { put("battery_percent", it) }
        put("battery_charging", isCharging())
        put("battery_source", chargingSource())

        put("network_transport", activeTransport())
        wifiSsid()?.let { put("wifi_ssid", it) }

        put("media_volume", mediaVolume())
        put("media_volume_max", maxMediaVolume())
        put("torch_on", torchOn)
        put("screen_on", isInteractive())
        put("battery_optimizations_ignored", isIgnoringBatteryOptimizations())
    }

    companion object {
        private const val TAG = "JarvisTelemetry"

        fun logUnsupported(action: String) {
            Log.w(TAG, "unsupported device action: $action")
        }
    }
}
