package com.jarvis.client.service

import android.app.Activity
import android.app.AppOpsManager
import android.app.KeyguardManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.os.Process
import android.util.Base64
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.MainActivity
import com.jarvis.client.R
import com.jarvis.client.assistant.LookGate
import com.jarvis.client.net.ScreenWatch
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream

/**
 * "Watch with me" on this phone (the owner's decision of 2026-09-28,
 * docs/SCREEN-DESIGN.md section 4): Android's own screen sharing
 * (MediaProjection), started by the owner, with Android's own question every
 * time, a notification that says "Jarvis is watching this phone" with Stop for
 * as long as it runs, and an end by itself after [ScreenWatch.MAX_MINUTES],
 * when the screen goes off, when Android ends the sharing, or on Stop / Stop
 * everything.
 *
 * NOTHING IS STREAMED, and nothing is written to disk. The screen sharing
 * feeds a small in-memory buffer; only when the owner asks a question does
 * [ScreenWatch.beforeQuestion] call [grab], which checks the app in front and
 * the screen ([ScreenWatch.decide]), makes ONE small JPEG, checks it is not
 * all black (an app that blocks screenshots draws black), and hands it to the
 * question - which sends it to the PC only, where its words are read and
 * nothing is kept.
 *
 * The rules are [ScreenWatch]'s, tested on the JVM. THIS FILE IS UNVERIFIED
 * ON A REAL PHONE: what screen sharing gives on Android 14 and 15, whether a
 * secure app really draws black here, how complete the Usage access log is,
 * and the battery cost are all things only a phone can say
 * (docs/SCREEN-DESIGN.md section 8, step 8). It fails closed: any doubt is a
 * refusal, never a picture.
 *
 * START_NOT_STICKY, never started at boot.
 */
class ScreenWatchService : Service() {

    private val main = Handler(Looper.getMainLooper())
    private var projection: MediaProjection? = null
    private var display: VirtualDisplay? = null
    private var reader: ImageReader? = null
    private var thread: HandlerThread? = null

    /** The newest frame Android gave, still open; replaced (and the old one closed) as new ones arrive. */
    private var latest: Image? = null
    private val lock = Any()

    @Volatile private var running = false
    @Volatile private var ended = false

    private val timeUp = Runnable { end(ScreenWatch.ENDED_TIME) }

    private val screenOff = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            end(ScreenWatch.ENDED_LOCK)
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            end(null)
            return START_NOT_STICKY
        }
        if (running) return START_NOT_STICKY
        val code = intent?.getIntExtra(EXTRA_CODE, Activity.RESULT_CANCELED) ?: Activity.RESULT_CANCELED
        val data = intent?.getParcelableExtra(EXTRA_DATA, Intent::class.java)
        if (code != Activity.RESULT_OK || data == null) {
            stopSelf()
            return START_NOT_STICKY
        }
        // Android 14+: the foreground service (type mediaProjection) must be up
        // BEFORE the projection is fetched - and only after the owner's yes.
        if (!goForeground()) {
            stopSelf()
            return START_NOT_STICKY
        }
        running = true
        if (!begin(code, data)) {
            end(FAILED)
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        if (!ended) end(null)
        super.onDestroy()
    }

    // ---------------------------------------------------------------- starting

    private fun begin(code: Int, data: Intent): Boolean {
        val manager = getSystemService(MediaProjectionManager::class.java) ?: return false
        val p = try {
            manager.getMediaProjection(code, data)
        } catch (e: Exception) {
            Log.w(TAG, "no projection", e)
            null
        } ?: return false
        projection = p
        // Required before a virtual display on Android 14+; also how Android
        // tells us the owner stopped sharing from its own status-bar chip.
        p.registerCallback(
            object : MediaProjection.Callback() {
                override fun onStop() {
                    end(ScreenWatch.ENDED_ANDROID)
                }
            },
            main,
        )
        val metrics = resources.displayMetrics
        val (w, h) = ScreenWatch.scaledSize(metrics.widthPixels, metrics.heightPixels)
        if (w <= 0 || h <= 0) return false
        val worker = HandlerThread("jarvis-watch").also { it.start() }
        thread = worker
        val handler = Handler(worker.looper)
        // Three buffers: one held as "the newest", one being filled, one spare.
        val r = ImageReader.newInstance(w, h, PixelFormat.RGBA_8888, 3)
        reader = r
        r.setOnImageAvailableListener({ source ->
            val next = try {
                source.acquireLatestImage()
            } catch (e: Exception) {
                null
            } ?: return@setOnImageAvailableListener
            synchronized(lock) {
                latest?.close()
                latest = if (ended) { next.close(); null } else next
            }
        }, handler)
        display = try {
            p.createVirtualDisplay(
                "jarvis-watch", w, h, metrics.densityDpi,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, r.surface, null, handler,
            )
        } catch (e: Exception) {
            Log.w(TAG, "no display", e)
            null
        } ?: return false

        // Ends with the screen: a locked phone is not watched (Android 15 QPR1
        // stops the sharing itself; this covers the older ones).
        ContextCompat.registerReceiver(
            this, screenOff, IntentFilter(Intent.ACTION_SCREEN_OFF), ContextCompat.RECEIVER_NOT_EXPORTED,
        )
        main.postDelayed(timeUp, ScreenWatch.MAX_MINUTES * 60_000L)
        ScreenWatch.say = { JarvisRuntime.setNotice(it) }
        ScreenWatch.stopHook = { end(null) }
        ScreenWatch.grabber = { grab() }
        ScreenWatch.started()
        return true
    }

    // ----------------------------------------------------------------- one picture

    /**
     * ONE picture for the question being asked, or the reason there is none.
     * Checked before any is taken (the app in front, the screen) and again
     * after (the picture is not black; the same app is still in front).
     */
    private suspend fun grab(): ScreenWatch.Grab = withContext(Dispatchers.Default) {
        // The owner turned "Let Jarvis read this phone's screen" off while it
        // ran: that ends it, and nothing is taken.
        if (JarvisRuntime.isInitialized && !JarvisRuntime.settings.security.value.screenRead) {
            main.post { end(null) }
            return@withContext ScreenWatch.Grab("", null, ScreenWatch.NEEDS_READ_ON)
        }
        val never = if (JarvisRuntime.isInitialized) JarvisRuntime.settings.security.value.neverApps else emptySet()
        val visible = ScreenWatch.visibleApps(usageEvents())
        val category = { pkg: String -> LookGate.categoryOf(this@ScreenWatchService, pkg) }
        val before = ScreenWatch.decide(visible, never, category, screenIsOn(), null)
        if (before is ScreenWatch.Verdict.Refuse) return@withContext ScreenWatch.Grab("", null, before.said)

        val bitmap = frame() ?: return@withContext ScreenWatch.Grab("", null, NO_PICTURE)
        try {
            val after = ScreenWatch.decide(
                visible, never, category, screenIsOn(), ScreenWatch.looksBlack(sample(bitmap)),
            )
            if (after is ScreenWatch.Verdict.Refuse) return@withContext ScreenWatch.Grab("", null, after.said)
            // The apps on screen must not have changed while the picture was taken.
            if (ScreenWatch.visibleApps(usageEvents()) != visible) {
                return@withContext ScreenWatch.Grab("", null, NO_PICTURE)
            }
            val out = ByteArrayOutputStream()
            if (!bitmap.compress(Bitmap.CompressFormat.JPEG, ScreenWatch.JPEG_QUALITY, out)) {
                return@withContext ScreenWatch.Grab("", null, NO_PICTURE)
            }
            val url = "data:image/jpeg;base64," + Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)
            ScreenWatch.Grab(LookGate.labelOf(this@ScreenWatchService, visible.lastOrNull()), url, null)
        } finally {
            bitmap.recycle()
        }
    }

    /** The newest frame as a bitmap of exactly its own size, or null. */
    private fun frame(): Bitmap? = synchronized(lock) {
        val image = latest ?: return null
        val plane = image.planes.firstOrNull() ?: return null
        val pixelStride = plane.pixelStride
        if (pixelStride <= 0) return null
        val padding = plane.rowStride - pixelStride * image.width
        val wide = try {
            Bitmap.createBitmap(image.width + padding / pixelStride, image.height, Bitmap.Config.ARGB_8888)
        } catch (e: Exception) {
            return null
        }
        wide.copyPixelsFromBuffer(plane.buffer)
        if (wide.width == image.width) return wide
        val exact = Bitmap.createBitmap(wide, 0, 0, image.width, image.height)
        wide.recycle()
        exact
    }

    /** About four thousand pixels spread over the picture, as brightness values. */
    private fun sample(bitmap: Bitmap): IntArray {
        val steps = 64
        val out = IntArray(steps * steps)
        var i = 0
        for (yi in 0 until steps) {
            val y = (yi * (bitmap.height - 1)) / (steps - 1)
            for (xi in 0 until steps) {
                val x = (xi * (bitmap.width - 1)) / (steps - 1)
                out[i++] = ScreenWatch.lumaOf(bitmap.getPixel(x, y))
            }
        }
        return out
    }

    private fun screenIsOn(): Boolean {
        val power = getSystemService(PowerManager::class.java)
        val keys = getSystemService(KeyguardManager::class.java)
        return power?.isInteractive == true && keys?.isKeyguardLocked == false
    }

    /** The recent front-app events. Empty when Usage access is not given - and then nothing is looked at. */
    private fun usageEvents(): List<ScreenWatch.UsageEvent> {
        val stats = getSystemService(UsageStatsManager::class.java) ?: return emptyList()
        val now = System.currentTimeMillis()
        val events = try {
            stats.queryEvents(now - LOG_MS, now)
        } catch (e: Exception) {
            return emptyList()
        }
        val out = ArrayList<ScreenWatch.UsageEvent>()
        val one = UsageEvents.Event()
        while (events.hasNextEvent()) {
            events.getNextEvent(one)
            val t = one.eventType
            if (t in ScreenWatch.EVENT_TYPES) {
                out += ScreenWatch.UsageEvent(one.timeStamp, t, one.packageName.orEmpty())
            }
        }
        return out
    }

    // ------------------------------------------------------------------ ending

    /** Ends the session, whatever the reason; [said] (when there is one) goes to the notice line. */
    private fun end(said: String?) {
        if (ended) return
        ended = true
        running = false
        main.removeCallbacks(timeUp)
        runCatching { unregisterReceiver(screenOff) }
        ScreenWatch.grabber = null
        ScreenWatch.stopHook = null
        ScreenWatch.ended()
        synchronized(lock) {
            latest?.close()
            latest = null
        }
        runCatching { reader?.setOnImageAvailableListener(null, null) }
        runCatching { display?.release() }
        runCatching { reader?.close() }
        runCatching { projection?.stop() } // its own callback comes back here and is ignored: ended is set
        runCatching { thread?.quitSafely() }
        display = null
        reader = null
        projection = null
        thread = null
        said?.let { JarvisRuntime.setNotice(it) }
        runCatching { stopForeground(STOP_FOREGROUND_REMOVE) }
        stopSelf()
    }

    /**
     * The ongoing notification: fixed words only, never anything from the
     * screen. It stays on this phone and has Stop, never held on a stale link.
     */
    private fun goForeground(): Boolean {
        ensureChannel(this)
        val stop = PendingIntent.getService(
            this, 21,
            Intent(this, ScreenWatchService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val open = PendingIntent.getActivity(
            this, 22,
            Intent(this, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setLocalOnly(true)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(ScreenWatch.SIGN_TITLE)
            .setContentText(ScreenWatch.NOTIFICATION_TEXT)
            .setOngoing(true)
            .setSilent(true)
            .setShowWhen(false)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .setContentIntent(open)
            .addAction(0, ScreenWatch.STOP_LABEL, stop)
            .build()
        return try {
            ServiceCompat.startForeground(
                this, NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION,
            )
            true
        } catch (e: Exception) {
            Log.w(TAG, "startForeground refused", e)
            JarvisRuntime.setNotice("Android did not let Jarvis start watching. Open Jarvis and try again.")
            false
        }
    }

    companion object {
        private const val TAG = "JarvisWatch"
        const val CHANNEL_ID = "jarvis_watch"
        private const val NOTIFICATION_ID = 0x4A57
        const val ACTION_STOP = "com.jarvis.client.WATCH_STOP"
        private const val EXTRA_CODE = "com.jarvis.client.extra.WATCH_CODE"
        private const val EXTRA_DATA = "com.jarvis.client.extra.WATCH_DATA"

        /** How far back the front-app log is read: long enough to have seen the app come forward. */
        private const val LOG_MS = 12L * 60L * 60L * 1000L

        private const val NO_PICTURE = "Jarvis could not get a picture of the screen just now."
        private const val FAILED = "Android would not share the screen, so Jarvis is not watching."

        /**
         * Start, with the result of Android's own screen-sharing question
         * (asked by the app's own screen, every time). Nothing here asks it.
         */
        fun start(context: Context, resultCode: Int, data: Intent) {
            runCatching {
                ContextCompat.startForegroundService(
                    context,
                    Intent(context, ScreenWatchService::class.java)
                        .putExtra(EXTRA_CODE, resultCode)
                        .putExtra(EXTRA_DATA, data),
                )
            }.onFailure {
                Log.w(TAG, "could not start", it)
                JarvisRuntime.setNotice("Android did not let Jarvis start watching. Open Jarvis and try again.")
            }
        }

        /** True when the owner has turned on Usage access for Jarvis (Android's own switch). */
        fun usageAccessGranted(context: Context): Boolean {
            val ops = context.getSystemService(AppOpsManager::class.java) ?: return false
            return runCatching {
                ops.unsafeCheckOpNoThrow(
                    AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), context.packageName,
                ) == AppOpsManager.MODE_ALLOWED
            }.getOrDefault(false)
        }

        /**
         * Can the owner SEE the "Jarvis is watching" notification? Watch never
         * starts when it cannot be seen: the sign is the safeguard. False when
         * notifications are off for Jarvis, or this channel is switched off.
         */
        fun signVisible(context: Context): Boolean {
            ensureChannel(context)
            val manager = ContextCompat.getSystemService(context, NotificationManager::class.java) ?: return false
            if (!manager.areNotificationsEnabled()) return false
            val channel = manager.getNotificationChannel(CHANNEL_ID)
            return channel == null || channel.importance != NotificationManager.IMPORTANCE_NONE
        }

        fun ensureChannel(context: Context) {
            val manager = ContextCompat.getSystemService(context, NotificationManager::class.java) ?: return
            manager.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID,
                    "Jarvis is watching",
                    // Low: a status line for as long as the screen is shared, never a sound.
                    NotificationManager.IMPORTANCE_LOW,
                ).apply {
                    description = "Shown for as long as Jarvis is watching this phone's screen with you."
                    setShowBadge(false)
                },
            )
        }
    }
}
