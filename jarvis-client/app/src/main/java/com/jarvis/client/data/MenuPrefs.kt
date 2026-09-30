package com.jarvis.client.data

import android.content.Context
import androidx.core.content.edit
import com.jarvis.client.net.MenuCatalog
import com.jarvis.client.net.MenuLogic
import com.jarvis.client.net.MenuResult
import com.jarvis.client.net.MenuState
import com.jarvis.client.net.MenuView
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Which menus are hidden or folded, remembered on THIS phone
 * (docs/MENU-VISIBILITY-DESIGN.md, docs/JARVIS-API.md section 109). Per device: the desktop
 * keeps its own set, and nothing here is ever sent anywhere - no request, no card. Modelled on
 * [HistoryViewPrefs]: ids only, never a word of a chat or a memory.
 *
 * Reads and writes are guarded: a preference file that cannot be opened leaves everything
 * showing and never crashes a screen. A stored id that no longer exists, is the desktop's, or
 * is never-hideable is ignored and is dropped the next time something is saved. A stored
 * version other than [MenuCatalog.VERSION] reads as empty and is left alone until the owner
 * changes something.
 *
 * [view] is what the screens draw from: the stored choice plus the ids a link opened "for now"
 * (memory only, never stored - [showForVisit], [endVisit]).
 */
class MenuPrefs(context: Context) {

    private val prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    private val _view = MutableStateFlow(MenuView(load(), emptySet()))

    /** The list the screens draw from. */
    val view: StateFlow<MenuView> = _view.asStateFlow()

    /** The stored choice. */
    val state: MenuState get() = _view.value.state

    /**
     * Applies one change (from the list, or from "hide the finance menu" by voice). The result
     * says whether it took: [MenuResult.NEVER] for a never-hideable menu, [MenuResult.UNKNOWN]
     * for an id this phone does not have.
     */
    @Synchronized
    fun apply(action: String, target: String): MenuResult {
        val (next, result) = MenuLogic.apply(_view.value.state, action, target, MenuLogic.PHONE)
        if (result == MenuResult.OK && next != _view.value.state) {
            val visit = if (action == MenuLogic.ACTION_RESET) emptySet() else _view.value.visit
            _view.value = MenuView(next, visit)
            save(next)
        }
        return result
    }

    fun hide(id: String): MenuResult = apply(MenuLogic.ACTION_HIDE, id)
    fun show(id: String): MenuResult = apply(MenuLogic.ACTION_SHOW, id)
    fun reset(): MenuResult = apply(MenuLogic.ACTION_RESET, "all")

    /**
     * A link ("open the second graphics card") to a hidden menu: show that menu, and what holds
     * it, for this visit only. Not stored; its group stays hidden. Ends with [endVisit] (leaving
     * the screen) or [hideAgain].
     */
    @Synchronized
    fun showForVisit(id: String) {
        val visit = MenuLogic.visitSet(id)
        if (visit.isEmpty()) return
        _view.value = _view.value.copy(visit = _view.value.visit + visit)
    }

    /** "Keep it visible": the visit becomes a real change. */
    @Synchronized
    fun keep(id: String) {
        show(id)
        val gone = MenuLogic.visitSet(id)
        _view.value = _view.value.copy(visit = _view.value.visit - gone)
    }

    /** "Hide again": the visit ends now. */
    @Synchronized
    fun hideAgain(id: String) {
        val gone = MenuLogic.visitSet(id)
        _view.value = _view.value.copy(visit = _view.value.visit - gone)
    }

    /** Leaving the screen the link opened. */
    @Synchronized
    fun endVisit() {
        if (_view.value.visit.isEmpty()) return
        _view.value = _view.value.copy(visit = emptySet())
    }

    private fun load(): MenuState = runCatching {
        val v = prefs.getInt(KEY_VERSION, MenuCatalog.VERSION)
        if (v != MenuCatalog.VERSION) {
            MenuState()
        } else {
            MenuLogic.sanitize(
                MenuState(
                    hidden = prefs.getStringSet(KEY_HIDDEN, emptySet()).orEmpty().toSet(),
                    collapsed = prefs.getStringSet(KEY_COLLAPSED, emptySet()).orEmpty().toSet(),
                ),
                MenuLogic.PHONE,
            )
        }
    }.getOrDefault(MenuState())

    private fun save(state: MenuState) {
        runCatching {
            prefs.edit {
                putInt(KEY_VERSION, MenuCatalog.VERSION)
                putStringSet(KEY_HIDDEN, state.hidden)
                putStringSet(KEY_COLLAPSED, state.collapsed)
            }
        }
    }

    private companion object {
        const val PREFS = "jarvis_menus"
        const val KEY_VERSION = "v"
        const val KEY_HIDDEN = "hidden"
        const val KEY_COLLAPSED = "collapsed"
    }
}
