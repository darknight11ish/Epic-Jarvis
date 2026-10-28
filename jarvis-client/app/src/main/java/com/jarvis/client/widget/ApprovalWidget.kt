package com.jarvis.client.widget

import android.content.Context
import android.widget.Toast
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.action.Action
import androidx.glance.action.ActionParameters
import androidx.glance.action.actionParametersOf
import androidx.glance.action.actionStartActivity
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.action.ActionCallback
import androidx.glance.appwidget.action.actionRunCallback
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.background
import androidx.glance.unit.ColorProvider
import androidx.glance.layout.Alignment
import androidx.glance.layout.Box
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.padding
import androidx.glance.layout.width
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import androidx.compose.ui.graphics.Color
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.service.EventService
import com.jarvis.client.LinkState
import com.jarvis.client.MainActivity
import com.jarvis.client.net.CardWords
import com.jarvis.client.net.PendingItem

/**
 * The oldest unresolved approval, on the home screen.
 *
 * Ported from the retired `jarvis-android/`'s own approval widget, with one
 * deliberate change from that original: this one **only ever lets Deny be a
 * one-tap widget action**. The old widget wired both Approve and Deny to the
 * same one-tap `ActionCallback` - which was fine for that app's own rules at
 * the time, but this app's `docs/ARCHITECTURE.md` (via the desktop thread)
 * states the rule this project actually runs on: *"Deny may be a
 * notification action. Approve may not... Approving means opening the
 * app."* `ApprovalNotifier.kt`'s own lock-screen action already only ever
 * wires Deny for exactly this reason. Copying the old widget's Approve
 * button verbatim would have been a real regression against that rule, not
 * a faithful port of it - so Approve here opens [MainActivity] instead,
 * where the real card and its biometric gate (`BiometricGate.kt`) decide
 * whether the tap actually counts.
 *
 * **Which buttons exist is not decided here.** [ApprovalWidgetRules.cardButtons]
 * holds that shape as pure code the JVM tests can execute, because a button's
 * words are a promise about what the tap does and this file can only draw them.
 * Unlocked, it is Deny - the one decision this widget may make directly - and
 * Review. While App lock or "Hide memory lists" is on, it is ONE button,
 * "Unlock to review": that is the only thing a tap can do there, with the
 * card's own words hidden and the decision needing the unlock. It used to draw
 * a button saying "Deny" wired to the app instead, and the owner field-tested
 * exactly that on 2026-10-28 - a label promising a refusal the tap could not
 * perform. The locked phone still never denies an unseen card (the owner kept
 * that rule the same day); the card just stops claiming otherwise.
 *
 * Holds no state of its own, on purpose - the same reasoning
 * `WidgetDataRepository`'s own doc comment gives in the retired app: a
 * second source of truth drifts from [JarvisRuntime] the moment an approval
 * resolves anywhere else, the lock-screen notification included. This reads
 * [JarvisRuntime.pending] fresh every time it draws and nothing more.
 */
class ApprovalWidget : GlanceAppWidget() {

    override val sizeMode: SizeMode = SizeMode.Exact

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        // The whole draw is bounded and its outcome is ONE terminal state
        // (WidgetStates.approval) - never a "loading" one. The spinner the
        // owner saw on 2026-10-27 was not drawn by this class at all: it was
        // the launcher's `initialLayout` (Glance's own bare ProgressBar),
        // because no Glance worker ever ran in the release APK (see
        // proguard-rules.pro). Two things follow from that, and both are here:
        //  * the layout a widget shows before its first draw is now Jarvis's
        //    own sentence (res/layout/widget_initial.xml), not a spinner; and
        //  * nothing this class waits for is open-ended any more
        //    (WidgetRuntime.start), so a slow or wedged startup is a state.
        //
        // `runCatching` lives in WidgetRuntime.start for the reason
        // MainActivity.kt wraps this identical call: the Keystore, the
        // preferences and the HTTP client "can fail on a device in a way it
        // cannot here". Called bare from a Glance worker, that same failure is
        // an uncaught exception in the update coroutine and the launcher
        // replaces the widget with "Problem loading widget".
        val ready = WidgetRuntime.start(context) && JarvisRuntime.isInitialized
        val pending = if (ready) JarvisRuntime.pending.value else emptyList()
        val paired = ready && JarvisRuntime.isPaired()
        // "Do we actually KNOW what is waiting?" - a different question from
        // "is the link up", and the one this widget has to answer honestly.
        //
        // `initialize()` constructs objects and starts collectors; it never
        // fetches. `_stale` starts true and returns to true on every
        // disconnect. So a process the launcher woke only to draw this widget
        // - EventService not running, nothing ever fetched - has an empty
        // `_pending` that means "not looked", not "nothing there". Rendering
        // "Nothing waiting" from that state is an approvals widget claiming
        // there are no approvals, which is the single failure it exists to
        // prevent. WidgetStates.approval encodes that distinction, and the
        // rest of the old `when` order with it:
        //
        //  - a stale-but-CONNECTED link with a last known queue still shows
        //    the card WITH Deny reachable: page 7's "refusing is never held"
        //    (2026-10-17). Only a link that cannot deliver anything at all is
        //    UNREACHABLE, and it says so.
        val state = WidgetStates.approval(
            ready = ready,
            paired = paired,
            connected = ready && JarvisRuntime.link.value == LinkState.CONNECTED,
            stale = !ready || JarvisRuntime.stale.value,
            waiting = pending.size,
        )
        val extra = (pending.size - 1).coerceAtLeast(0)
        // The home screen is public: under App lock (or hidden lists) only a
        // short title shows and the buttons open the locked app.
        val security = if (ready) JarvisRuntime.settings.security.value else null
        val hidden = ApprovalWidgetRules.hidden(
            settingsKnown = security != null,
            appLock = security?.appLock == true,
            privateLists = security?.privateLists == true,
        )

        provideContent {
            Box(
                modifier = GlanceModifier
                    .fillMaxSize()
                    .background(Palette.Background)
                    .cornerRadius(16.dp)
                    .padding(12.dp),
            ) {
                when (state) {
                    // `first()` is safe because CARD is only returned with a
                    // non-empty queue (WidgetStates.approval).
                    WidgetStates.Approval.CARD -> ActiveApproval(pending.first(), extra, hidden)
                    WidgetStates.Approval.EMPTY -> EmptyState()
                    else -> {
                        val words = WidgetStates.approvalWords(state)
                        MessageState(words.first, words.second)
                    }
                }
            }
        }
    }

    /** Only ever reached on a live link - see `live` in provideGlance. That
     *  is what makes "Nothing waiting" a statement this widget is entitled to
     *  make rather than a guess; every not-live case has its own wording. */
    @Composable
    private fun EmptyState() {
        Row(
            modifier = GlanceModifier.fillMaxSize().clickable(actionStartActivity<MainActivity>()),
            verticalAlignment = Alignment.CenterVertically,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = "Nothing waiting",
                style = TextStyle(
                    color = Palette.TextMuted,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                ),
            )
        }
    }

    /** Pairing or connectivity stands between here and a real decision - say
     *  so and open the app, rather than showing buttons that would refuse. */
    @Composable
    private fun MessageState(headline: String, sub: String) {
        Column(
            modifier = GlanceModifier.fillMaxSize().clickable(actionStartActivity<MainActivity>()),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = headline,
                style = TextStyle(color = Palette.StatusBad, fontSize = 12.sp, fontWeight = FontWeight.Bold),
            )
            Spacer(GlanceModifier.height(2.dp))
            Text(sub, style = TextStyle(color = Palette.TextMuted, fontSize = 11.sp))
        }
    }

    @Composable
    private fun ActiveApproval(item: PendingItem, extra: Int, hidden: Boolean) {
        Column(modifier = GlanceModifier.fillMaxSize()) {
            Row(
                modifier = GlanceModifier.fillMaxWidth().clickable(actionStartActivity<MainActivity>()),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                // The same label as every card (CardWords): the headline below
                // already says "Jarvis wants to ...", and the tier word ("ASK")
                // meant nothing to the reader.
                Text(
                    text = CardWords.KICKER,
                    style = TextStyle(color = Palette.Accent, fontSize = 11.sp, fontWeight = FontWeight.Bold),
                )
            }

            Spacer(GlanceModifier.height(4.dp))

            Column(
                modifier = GlanceModifier.defaultWeight().fillMaxWidth()
                    .clickable(actionStartActivity<MainActivity>()),
            ) {
                // `notice` first, `title`/`risk.why` only as the fallback -
                // see ApprovalWidgetRules.cardTitle, which holds the order
                // and the App-lock rule as pure code the JVM tests can check.
                val headline = ApprovalWidgetRules.cardTitle(
                    hidden = hidden,
                    noticeTitle = item.notice?.title,
                    title = item.title,
                )
                // Never `item.summary` as the fallback: it carries the
                // readable part of `detail` now (decodePendingRows), and the
                // home screen is as public as a lock screen. The title is
                // built from the action name alone, so it is safe here.
                val detail = ApprovalWidgetRules.cardDetail(
                    hidden = hidden,
                    noticeBody = item.notice?.body,
                    riskWhy = item.risk.why,
                )
                Text(text = headline, maxLines = 1, style = TextStyle(
                    color = Palette.TextHi, fontSize = 14.sp, fontWeight = FontWeight.Bold,
                ))
                if (detail.isNotBlank()) {
                    Text(
                        text = detail,
                        maxLines = 2,
                        style = TextStyle(color = Palette.TextMuted, fontSize = 11.sp),
                    )
                }
            }

            if (extra > 0) {
                Text(
                    text = "+$extra more waiting",
                    style = TextStyle(color = Palette.Accent, fontSize = 10.sp),
                )
                Spacer(GlanceModifier.height(4.dp))
            }

            // Deny on the left, the way to Approve on the right: the same order
            // as every card on the phone and the desktop (CardWords.BUTTONS).
            //
            // Which buttons exist - and so whether there is a Deny at all - is
            // ApprovalWidgetRules.cardButtons' decision, not this Row's. Under
            // App lock it is ONE button that says what its tap really does
            // (2026-10-28: the owner tapped a "Deny" that only opened the app).
            Row(modifier = GlanceModifier.fillMaxWidth()) {
                // Deny is a direct widget action only when the rule says so.
                // On the same CONDITION as the lock-screen notification, which
                // this widget used to ignore: `ApprovalNotifier` offers its
                // Deny action only `if (item.notice?.denyOk != false)`, so an
                // item the desktop marked `deny_ok: false` had no one-tap Deny
                // in the drawer and a one-tap Deny on the home screen. Two
                // surfaces disagreeing about whether an item is safe to refuse
                // unread is the disagreement mattering most.
                val denyOk = item.notice?.denyOk != false
                ApprovalWidgetRules.cardButtons(hidden, denyOk).forEachIndexed { index, button ->
                    if (index > 0) Spacer(GlanceModifier.width(8.dp))
                    PillButton(
                        label = button.label,
                        // Refusing is always the safe direction, so it stays red;
                        // every other button goes the way forward, into the app.
                        tint = if (button.tap == ApprovalWidgetRules.Tap.DENY_NOW) {
                            Palette.StatusBad
                        } else {
                            Palette.StatusOk
                        },
                        // The one callback this widget owns, carried the item's
                        // id. Everything else opens the app, where the real card
                        // and its biometric gate (BiometricGate.kt) decide.
                        onClick = if (button.tap == ApprovalWidgetRules.Tap.DENY_NOW) {
                            actionRunCallback<DenyActionCallback>(
                                actionParametersOf(DenyActionCallback.PARAM_ID to item.id),
                            )
                        } else {
                            actionStartActivity<MainActivity>()
                        },
                        modifier = GlanceModifier.defaultWeight(),
                    )
                }
            }
        }
    }

    @Composable
    private fun PillButton(
        label: String,
        tint: ColorProvider,
        onClick: Action,
        modifier: GlanceModifier = GlanceModifier,
    ) {
        // `defaultWeight()` is a RowScope/ColumnScope-scoped extension, not a
        // free function - it only resolves where that scope's receiver is
        // implicitly in view. This function's own body is neither, so
        // callers apply it themselves (see the Row above) and pass the
        // result in, the same shape the retired app's own PillButton used.
        Box(
            modifier = modifier
                .background(Palette.Surface1)
                .cornerRadius(10.dp)
                .clickable(onClick)
                .padding(vertical = 8.dp),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = label,
                style = TextStyle(color = tint, fontSize = 12.sp, fontWeight = FontWeight.Bold),
            )
        }
    }
}

/** A flat, static palette for the widget - Glance's own RemoteViews host has
 *  no access to this app's dynamic per-face [com.jarvis.client.ui.theme.Chrome],
 *  so this is deliberately a small, fixed set rather than an attempt to
 *  reach into that system from a different composition entirely. */
private object Palette {
    val Background = ColorProvider(Color(0xFF04070C))
    val Surface1 = ColorProvider(Color(0xFF0E1822))
    val TextHi = ColorProvider(Color(0xFFE6EEF7))
    val TextMuted = ColorProvider(Color(0xFF93A6BA))
    val Accent = ColorProvider(Color(0xFF63F7FF))
    val StatusOk = ColorProvider(Color(0xFF6EE7A8))
    val StatusBad = ColorProvider(Color(0xFFEF6E6E))
}

class ApprovalWidgetReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = ApprovalWidget()
}

/**
 * Denies one approval from the home screen, no confirmation beyond the tap.
 *
 * Deliberately the ONLY decision this widget can make directly - see
 * [ApprovalWidget]'s own doc comment. This does not build a second signing
 * path: it hands the id to [EventService.deny], the same service action the
 * lock-screen notification's own Deny already uses, which ends in the same
 * [JarvisRuntime.decide] as the in-app card.
 */
class DenyActionCallback : ActionCallback {

    override suspend fun onAction(
        context: Context,
        glanceId: GlanceId,
        parameters: ActionParameters,
    ) {
        val id = parameters[PARAM_ID] ?: return
        // Handed to EventService, which answers the notification's Deny the
        // same way: start the stream, wait for the link to be live, re-read
        // the queue, then deny - or say out loud why it could not.
        //
        // This used to decide here, against `JarvisRuntime.pending` as this
        // process held it. After Android had killed the process that list was
        // empty, so a Deny tapped the next morning said "no longer waiting -
        // handled elsewhere" about a request that was still waiting on the
        // desktop; and when the item WAS found, `decideDetached` was refused
        // because the stream had not been started, with nothing said at all.
        if (!EventService.deny(context, id)) {
            val message = "Could not start Jarvis to send the denial. Open the app to deny it."
            runCatching { Toast.makeText(context, message, Toast.LENGTH_LONG).show() }
        }
        // No updateAll() here: the widget redraws when JarvisRuntime's
        // `pending` really changes (its own widgetJob), which is after the
        // desktop has accepted the denial, not before.
    }

    companion object {
        val PARAM_ID = ActionParameters.Key<String>("approval_id")
    }
}
