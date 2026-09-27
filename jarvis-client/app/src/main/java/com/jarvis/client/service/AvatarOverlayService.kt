package com.jarvis.client.service

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.os.IBinder
import android.provider.Settings
import android.util.Log
import android.util.TypedValue
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.ImageView
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.LinkState
import com.jarvis.client.MainActivity
import com.jarvis.client.R
import com.jarvis.client.data.Security
import com.jarvis.client.data.floatingAvatarShowsContent
import kotlin.math.abs
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.launch

/**
 * The Overlay path of "Floating Jarvis" (`data/FloatingAvatar.kt`,
 * `docs/JARVIS-API.md` section 56): a small, draggable Jarvis avatar drawn
 * on top of every other app (`TYPE_APPLICATION_OVERLAY`).
 *
 * Voice only, and display only. This window shows two things - a coloured
 * badge for whether the PC is reachable, and, by dimming the whole avatar,
 * whether this phone is actually listening at all right now (see
 * [updateAvatar]) - and does exactly one thing on a tap: bring the real app
 * to the front. It cannot change a setting, approve a card, or read
 * anything out loud by itself - the microphone it answers to is
 * [WakeWordService]'s own "hey Jarvis" listener, started and stopped from
 * the app's own Checks screen, never from here (rule 4, and CLAUDE.md's "a
 * client must not do speech-to-text": nothing here transcribes anything).
 *
 * Started and stopped only from [MainActivity]'s own `LaunchedEffect`, which
 * is the one place that both reads the setting and re-checks the permission
 * (`Settings.canDrawOverlays`, revocable at any time in Android's own
 * settings) - this service re-checks it too, on principle, since nothing
 * stops it being started some other way (`adb`, a stale PendingIntent).
 *
 * App lock: the same rule the class doc of [floatingAvatarShowsContent]
 * explains - this is this app's own drawn surface, so while the owner has
 * App lock on, the badge goes neutral (no colour, nothing about
 * reachability) rather than disappearing. Tapping it still always opens the
 * real app, whose own lock screen decides what happens next; this service
 * does not duplicate that check, only the little it shows beforehand.
 */
class AvatarOverlayService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var watcher: Job? = null

    private lateinit var windowManager: WindowManager
    private var avatarView: View? = null
    private var dot: View? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        JarvisRuntime.initialize(this)
        ensureChannel(this)
        // Checked again here, not only by the caller: nothing stops this
        // service being started some other way, and adding a window without
        // the permission throws rather than failing quietly.
        if (!Settings.canDrawOverlays(this)) {
            Log.w(TAG, "started without the overlay permission; stopping")
            stopSelf()
            return
        }
        if (!goForeground()) {
            stopSelf()
            return
        }
        if (!addAvatarView()) {
            stopSelf()
            return
        }
        _running.value = true
        watcher = scope.launch {
            combine(
                JarvisRuntime.link,
                JarvisRuntime.settings.security,
                WakeWordService.state,
            ) { link, security, listening -> Triple(link, security, listening) }
                .collect { (link, security, listening) -> updateAvatar(link, security, listening) }
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        // No restart of its own - the same choice WakeWordService makes, and
        // for the same reason: [MainActivity]'s `LaunchedEffect` is the one
        // place that decides whether this should be running, and it starts
        // this again on its own the next time the app is opened while the
        // setting and the permission both still say yes.
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        _running.value = false
        watcher?.cancel()
        scope.cancel()
        removeAvatarView()
        super.onDestroy()
    }

    // ------------------------------------------------------------- the window

    private fun addAvatarView(): Boolean {
        // `getSystemService(Class<T>)` directly, not through `ContextCompat`:
        // that overload has been the platform's own since API 23, well
        // under this app's `minSdk` 33, and `WindowManager` is one of the
        // standard services it resolves.
        windowManager = getSystemService(WindowManager::class.java) ?: return false
        val sizePx = dp(AVATAR_SIZE_DP)
        val icon = ImageView(this).apply {
            setImageResource(R.mipmap.ic_launcher_round)
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(Color.parseColor("#04070C"))
            }
        }
        val badge = View(this).apply {
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(NEUTRAL_COLOR)
            }
            visibility = View.INVISIBLE
        }
        val root = FrameLayout(this).apply {
            addView(icon, FrameLayout.LayoutParams(sizePx, sizePx))
            addView(
                badge,
                FrameLayout.LayoutParams(dp(BADGE_SIZE_DP), dp(BADGE_SIZE_DP)).apply {
                    gravity = Gravity.TOP or Gravity.END
                },
            )
        }
        dot = badge

        val layoutParams = WindowManager.LayoutParams(
            sizePx,
            sizePx,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            // NOT_FOCUSABLE: this window never takes key input or steals
            // focus from whatever app is in front. NOT_TOUCH_MODAL: a touch
            // outside this small window passes straight through to the app
            // underneath, rather than this window swallowing the whole
            // screen's touches the way a modal dialog would.
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = dp(16)
            y = dp(120)
        }
        root.setOnTouchListener(DragAndTap(layoutParams))
        return runCatching { windowManager.addView(root, layoutParams) }
            .onFailure { Log.w(TAG, "could not add the overlay window", it) }
            .also { avatarView = root }
            .isSuccess
    }

    private fun removeAvatarView() {
        val view = avatarView ?: return
        avatarView = null
        dot = null
        runCatching { windowManager.removeView(view) }
            .onFailure { Log.w(TAG, "could not remove the overlay window", it) }
    }

    /**
     * The two things this window shows, and only while [floatingAvatarShowsContent]:
     * whether the PC is reachable (the badge) and whether this phone is
     * actually listening at all (the whole avatar dims when it is not) - the
     * brief's own worry, "if the phone can't reach the PC, the avatar should
     * say so plainly ... rather than floating uselessly", applies just as
     * much to "Listen on this phone" being off: with nothing recording,
     * "open a chat" or anything else said to it can never be heard.
     */
    private fun updateAvatar(link: LinkState, security: Security, listening: WakeListen) {
        val view = avatarView
        val badge = dot
        val bg = badge?.background as? GradientDrawable
        val showsContent = floatingAvatarShowsContent(security.appLock)
        view?.alpha = if (showsContent && listening.on) FULL_ALPHA else DIM_ALPHA
        if (badge == null || bg == null) return
        if (!showsContent) {
            bg.setColor(NEUTRAL_COLOR)
            badge.visibility = View.INVISIBLE
            return
        }
        when (link) {
            LinkState.CONNECTED -> badge.visibility = View.INVISIBLE
            LinkState.RECONNECTING -> {
                bg.setColor(WARN_COLOR)
                badge.visibility = View.VISIBLE
            }
            LinkState.OFFLINE -> {
                bg.setColor(BAD_COLOR)
                badge.visibility = View.VISIBLE
            }
        }
    }

    /**
     * Drag to move the window; a short, near-still touch is a tap instead,
     * which brings the real app to the front. The same distinction any
     * floating-icon feature needs, because [WindowManager]'s own touch
     * events give this class both a click and a drag on the same listener,
     * with nothing else to tell them apart.
     */
    private inner class DragAndTap(private val lp: WindowManager.LayoutParams) : View.OnTouchListener {
        private var downX = 0f
        private var downY = 0f
        private var startX = 0
        private var startY = 0
        private var downAt = 0L
        private var dragged = false

        override fun onTouch(v: View, event: MotionEvent): Boolean {
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    downX = event.rawX
                    downY = event.rawY
                    startX = lp.x
                    startY = lp.y
                    downAt = System.currentTimeMillis()
                    dragged = false
                    return true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = (event.rawX - downX).toInt()
                    val dy = (event.rawY - downY).toInt()
                    if (!dragged && (abs(dx) > TAP_SLOP_PX || abs(dy) > TAP_SLOP_PX)) dragged = true
                    if (dragged) {
                        lp.x = startX + dx
                        lp.y = startY + dy
                        // `v` IS the view [addAvatarView] passed to
                        // `addView` (the touch listener is set on that same
                        // `root`, not a child) - `updateViewLayout` must be
                        // called with that exact instance.
                        runCatching { windowManager.updateViewLayout(v, lp) }
                    }
                    return true
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    val quick = System.currentTimeMillis() - downAt < TAP_MAX_MS
                    if (!dragged && quick && event.action == MotionEvent.ACTION_UP) openApp()
                    return true
                }
                else -> return false
            }
        }
    }

    /**
     * Brings [MainActivity] to the front, ready to talk - the same place
     * saying "open a chat" to a floating avatar reaches
     * ([com.jarvis.client.net.OpenChatPhrase]). Whatever the app lock says
     * happens inside the app itself, exactly as it would from any other
     * launch - this never bypasses it.
     */
    private fun openApp() {
        val intent = Intent(this, MainActivity::class.java)
            .setAction(MainActivity.ACTION_START_VOICE)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        runCatching { startActivity(intent) }.onFailure { Log.w(TAG, "could not open the app", it) }
    }

    // ------------------------------------------------------------ foreground

    private fun goForeground(): Boolean {
        val stop = PendingIntent.getService(
            this,
            0,
            Intent(this, AvatarOverlayService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val open = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setLocalOnly(!JarvisRuntime.watchNotificationsAllowed())
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(getString(R.string.avatar_overlay_title))
            .setContentText(getString(R.string.avatar_overlay_text))
            .setStyle(NotificationCompat.BigTextStyle().bigText(getString(R.string.avatar_overlay_text)))
            .setOngoing(true)
            .setSilent(true)
            .setShowWhen(false)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .setContentIntent(open)
            .addAction(0, getString(R.string.avatar_overlay_stop), stop)
            .build()
        return try {
            ServiceCompat.startForeground(
                this,
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE,
            )
            true
        } catch (e: Exception) {
            Log.w(TAG, "startForeground refused", e)
            false
        }
    }

    private fun dp(value: Int): Int = TypedValue.applyDimension(
        TypedValue.COMPLEX_UNIT_DIP,
        value.toFloat(),
        resources.displayMetrics,
    ).toInt()

    companion object {
        private const val TAG = "JarvisAvatarOverlay"
        const val CHANNEL_ID = "jarvis_avatar_overlay"
        private const val NOTIFICATION_ID = 0x4A58
        private const val ACTION_STOP = "com.jarvis.client.STOP_AVATAR_OVERLAY"
        private const val AVATAR_SIZE_DP = 56
        private const val BADGE_SIZE_DP = 16
        private const val TAP_SLOP_PX = 24
        private const val TAP_MAX_MS = 300L
        private const val FULL_ALPHA = 1.0f
        /** Dimmed, not hidden, while nothing is actually listening - still there to tap. */
        private const val DIM_ALPHA = 0.45f

        private val NEUTRAL_COLOR = Color.parseColor("#93A6BA")
        private val WARN_COLOR = Color.parseColor("#E7C76E")
        private val BAD_COLOR = Color.parseColor("#EF6E6E")

        private val _running = MutableStateFlow(false)

        /** Whether the overlay window is up right now. */
        val running: StateFlow<Boolean> = _running.asStateFlow()

        /** Only from [MainActivity]'s own `LaunchedEffect` - see the class doc. */
        fun start(context: Context) {
            if (_running.value) return
            runCatching {
                ContextCompat.startForegroundService(context, Intent(context, AvatarOverlayService::class.java))
            }.onFailure { Log.w(TAG, "could not start", it) }
        }

        /**
         * A no-op when it is not running, rather than starting the service
         * only to stop it again - which would briefly draw the window it is
         * meant to prevent.
         */
        fun stop(context: Context) {
            if (!_running.value) return
            runCatching {
                context.startService(Intent(context, AvatarOverlayService::class.java).setAction(ACTION_STOP))
            }
        }

        fun ensureChannel(context: Context) {
            val manager = ContextCompat.getSystemService(context, NotificationManager::class.java) ?: return
            manager.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID,
                    context.getString(R.string.channel_avatar_name),
                    NotificationManager.IMPORTANCE_LOW,
                ).apply {
                    description = context.getString(R.string.channel_avatar_desc)
                    setShowBadge(false)
                },
            )
        }
    }
}
