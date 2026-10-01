package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.MenuCatalog
import com.jarvis.client.net.MenuLogic
import com.jarvis.client.net.MenuView
import com.jarvis.client.net.MenuWords
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.LocalMenuFold
import com.jarvis.client.ui.parts.MenuFold
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Rule
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.Toggle
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome

/**
 * "Show or hide menus" (docs/MENU-VISIBILITY-DESIGN.md, docs/JARVIS-API.md section 109; the
 * owner's decision of 2026-09-30). ONE list in Settings: a switch per menu, a feature group as
 * one switch with its members under it, "Show everything" at the bottom.
 *
 * Hiding ONLY tidies: nothing is turned off, no approval card, no fingerprint. It is per
 * device (this phone only), remembered by [com.jarvis.client.data.MenuPrefs]; nothing is sent
 * anywhere. The switch is ON when the menu is SHOWN. Menus that can never be hidden
 * (approvals, Security, What asks first, the connection, ...) are not in the list; one line
 * says so. A group is offered only when this phone has at least one member of it, so "Finance"
 * appears now (Spending and Retirement are built) and "Home" does not.
 *
 * Reads and writes go through [JarvisRuntime.menus] directly, like the other plates.
 */
@Composable
internal fun MenuVisibilitySection() {
    val view by JarvisRuntime.menus.view.collectAsState()
    val chrome = LocalChrome.current
    val state = view.state
    Section(MenuWords.TITLE) {
        Plate {
            Text(
                MenuWords.DEVICE_NOTE,
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            Gap(4)
            Text(MenuWords.HELP, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(4)
            Text(MenuWords.NEVER_NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(8)
            val count = view.hiddenCount
            Text(
                when (count) {
                    0 -> MenuWords.NONE_HIDDEN
                    1 -> MenuWords.HIDDEN_SPEECH_ONE
                    else -> MenuWords.HIDDEN_SPEECH_MANY.replace("{n}", count.toString())
                },
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
                modifier = Modifier.liveStatus(),
            )
            Gap(10)
            Secondary(
                MenuWords.SHOW_EVERYTHING,
                enabled = state.hidden.isNotEmpty() || state.collapsed.isNotEmpty(),
                modifier = Modifier.fillMaxWidth(),
                onClick = { JarvisRuntime.menus.reset() },
            )
        }

        // Feature groups: one switch hides a family.
        for (group in MenuCatalog.GROUPS) {
            val members = MenuLogic.members(group.id)
            if (members.isEmpty()) continue
            Gap(12)
            Plate {
                val shown = group.id !in state.hidden && members.any { !MenuLogic.isHidden(state, it) }
                SwitchRow(
                    title = group.title,
                    about = MenuWords.GROUP_HIDES.replace(
                        "{members}",
                        members.mapNotNull { MenuLogic.menu(it)?.title }.joinToString(", "),
                    ),
                    shown = shown,
                    onChange = { on ->
                        if (on) JarvisRuntime.menus.show(group.id) else JarvisRuntime.menus.hide(group.id)
                    },
                )
                for (id in members) {
                    val m = MenuLogic.menu(id) ?: continue
                    Rule()
                    SwitchRow(
                        title = m.title,
                        about = m.about,
                        shown = !MenuLogic.isHidden(state, id),
                        indent = if (m.parent != null && m.parent in members) 24 else 12,
                        onChange = { on ->
                            if (on) JarvisRuntime.menus.show(id) else JarvisRuntime.menus.hide(id)
                        },
                    )
                }
            }
        }

        // Everything else, by where it lives.
        for ((label, area) in listOf("Settings" to "settings", "Brain" to "brain", "Buttons" to "entry")) {
            val rows = MenuCatalog.MENUS.filter { it.phone && it.hide && it.area == area && it.group == null }
            if (rows.isEmpty()) continue
            Gap(12)
            Section(label) {
                Plate {
                    rows.forEachIndexed { i, m ->
                        if (i > 0) Rule()
                        SwitchRow(
                            title = m.title,
                            about = m.about,
                            shown = !MenuLogic.isHidden(state, m.id),
                            onChange = { on ->
                                if (on) JarvisRuntime.menus.show(m.id) else JarvisRuntime.menus.hide(m.id)
                            },
                        )
                    }
                }
            }
        }
    }
}

/** A title, a one-line description and a switch that is ON while the menu is shown. */
@Composable
private fun SwitchRow(
    title: String,
    about: String,
    shown: Boolean,
    onChange: (Boolean) -> Unit,
    indent: Int = 0,
) {
    val chrome = LocalChrome.current
    Column(Modifier.fillMaxWidth().padding(start = indent.dp, top = 6.dp, bottom = 6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                title,
                style = MaterialTheme.typography.titleSmall,
                color = chrome.textHi,
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(8.dp))
            Toggle(
                checked = shown,
                onCheckedChange = onChange,
                modifier = Modifier.semantics {
                    contentDescription = if (shown) "$title, shown" else "$title, hidden"
                },
            )
        }
        if (about.isNotBlank()) {
            Text(about, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
    }
}

/**
 * Wraps one menu on a screen: the "Shown for now" banner when a link opened it for this visit,
 * and the fold control its head [Section] shows (a menu that can be folded only; see
 * [LocalMenuFold]). The caller decides whether to draw the menu at all
 * (`if (menus.shows(id)) item(key = ...) { MenuFrame(menus, id) { ... } }`), so a hidden menu
 * leaves no gap.
 */
@Composable
internal fun MenuFrame(view: MenuView, id: String, content: @Composable () -> Unit) {
    val canFold = MenuLogic.menu(id)?.collapse == true
    val folded = canFold && view.folded(id)
    val fold = if (canFold) {
        MenuFold(folded) {
            JarvisRuntime.menus.apply(if (folded) MenuLogic.ACTION_EXPAND else MenuLogic.ACTION_COLLAPSE, id)
        }
    } else {
        null
    }
    Column(Modifier.fillMaxWidth()) {
        if (view.onVisit(id)) {
            VisitBanner(id)
            Gap(8)
        }
        CompositionLocalProvider(LocalMenuFold provides fold) { content() }
    }
}

/** "Shown for now. Keep it visible | Hide again" - a link opened a hidden menu for this visit. */
@Composable
private fun VisitBanner(id: String) {
    val chrome = LocalChrome.current
    Plate {
        Text(
            MenuWords.VISIT_BANNER,
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
            modifier = Modifier.liveStatus(),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Quiet(MenuWords.VISIT_KEEP, onClick = { JarvisRuntime.menus.keep(id) })
            Quiet(MenuWords.VISIT_AGAIN, onClick = { JarvisRuntime.menus.hideAgain(id) })
        }
    }
}

/**
 * "3 hidden - Show": where hidden menus used to be. A real button; it reads "3 menus hidden.
 * Show or hide menus." Nothing when nothing is hidden.
 */
@Composable
internal fun HiddenMenusLine(count: Int, onOpen: () -> Unit) {
    if (count <= 0) return
    Quiet(
        if (count == 1) MenuWords.HIDDEN_LINE_ONE else MenuWords.HIDDEN_LINE_MANY.replace("{n}", count.toString()),
        modifier = Modifier.semantics {
            contentDescription =
                if (count == 1) MenuWords.HIDDEN_SPEECH_ONE else MenuWords.HIDDEN_SPEECH_MANY.replace("{n}", count.toString())
        },
        onClick = onOpen,
    )
}
