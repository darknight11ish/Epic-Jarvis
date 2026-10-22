package com.jarvis.client.data

import android.content.Context
import androidx.core.content.edit
import com.jarvis.client.net.HudLayout
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.MenuCatalog
import com.jarvis.client.net.MenuLogic
import com.jarvis.client.net.MenuResult
import com.jarvis.client.net.MenuState
import com.jarvis.client.net.MenuView
import kotlinx.serialization.json.put
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


    // ------------------------------------------------------------- Home HUD ----
    // The editable Home HUD (the Android A1-A4 slice, 2026-10-22). ONE versioned
    // layout document and the owner's own preset copies, in the SAME
    // SharedPreferences file as the menu visibility above - ids only, per
    // device, never sent anywhere, no card, no pairing token (docs section 8's
    // editable-HUD rules, applied to the phone).

    /** The layout the Home screen draws from, and the owner's preset copies. */
    private val _hud = MutableStateFlow(loadHud())
    val hudLayout: StateFlow<HudLayout.Layout> = _hud.asStateFlow()

    /** The owner's copies ("Duplicate to custom"); always after the built-ins. */
    private val _presets = MutableStateFlow(loadPresets())
    val customPresets: StateFlow<List<HudLayout.Preset>> = _presets.asStateFlow()

    /** The layout held in memory (for the edit screen's own draft/undo). */
    val layout: HudLayout.Layout get() = _hud.value

    /**
     * Applies ONE edit - the same [HudLayout.Action] a drag, a button or a
     * TalkBack custom action makes - and saves it at once (autosave). A
     * protected card is present after every edit because [HudLayout.normalize]
     * is what the reducer returns.
     */
    @Synchronized
    fun applyLayout(action: HudLayout.Action): HudLayout.Layout {
        val next = HudLayout.apply(_hud.value, action)
        if (next != _hud.value) {
            _hud.value = next
            saveHud(next)
        }
        return next
    }

    /** Back to the Default preset's arrangement. */
    fun resetLayout(): HudLayout.Layout = applyLayout(HudLayout.Action.Reset)

    /** One of the five built-in presets, read-only. */
    fun applyPreset(presetId: String): HudLayout.Layout =
        applyLayout(HudLayout.Action.ApplyPreset(presetId))

    /**
     * "Duplicate to custom": a copy of the CURRENT layout (or any built-in)
     * that later edits go into. The built-in itself is never changed.
     */
    @Synchronized
    fun duplicateToCustom(title: String): HudLayout.Preset {
        val copy = HudLayout.copyAs(title, _hud.value)
        val mine = _presets.value.filterNot { it.id == copy.id }
        _presets.value = mine + copy
        savePresets(_presets.value)
        return copy
    }

    /** Renames one of the owner's copies; the built-ins are never touched. */
    @Synchronized
    fun renameCustomPreset(id: String, title: String): HudLayout.Preset? {
        val clean = title.trim().replace(Regex("\\s+"), " ").take(40)
        if (clean.isEmpty()) return null
        val preset = _presets.value.firstOrNull { it.id == id } ?: return null
        val renamed = preset.copy(title = clean)
        _presets.value = _presets.value.map { if (it.id == id) renamed else it }
        savePresets(_presets.value)
        return renamed
    }

    /** Deletes one of the owner's copies; the layout itself stays as it is. */
    @Synchronized
    fun deleteCustomPreset(id: String): Boolean {
        val gone = _presets.value.filterNot { it.id == id }
        if (gone.size == _presets.value.size) return false
        _presets.value = gone
        savePresets(gone)
        return true
    }

    /** Reads one of the owner's copies, never a built-in. */
    fun customPreset(id: String): HudLayout.Preset? = _presets.value.firstOrNull { it.id == id }

    /**
     * The JSON a person can copy out (and paste back on another phone or into
     * a note): the layout only, sanitized by [HudLayout.normalize]. It is not a
     * backup of the phone and never carries words of a chat or a memory.
     */
    fun layoutJson(): String = HudLayout.toJson(_hud.value)

    /**
     * A pasted document, made safe by [HudLayout.fromJson] + normalize. An
     * invalid one changes nothing and answers false - the built-in preset
     * list is never rewritten by an import.
     */
    @Synchronized
    fun importLayoutJson(json: String?): Boolean {
        val safe = HudLayout.fromJson(json) ?: return false
        if (safe == _hud.value) return false
        _hud.value = safe
        saveHud(safe)
        return true
    }

    private fun loadHud(): HudLayout.Layout = runCatching {
        val text = prefs.getString(KEY_HUD_LAYOUT, null)
        val stored = HudLayout.fromJson(text)
        if (stored != null) {
            stored
        } else {
            // Migration from the menu visibility that already exists: the same
            // cards this phone already hides are not put on the Home screen by
            // a first-run layout (a personal choice made before the layout
            // existed is not silently undone).
            val hidden = load()
            val base = HudLayout.defaults()
            HudLayout.normalize(
                base.copy(sections = base.sections.mapValues { (section, ids) ->
                    ids.filter { id ->
                        val menu = HudLayout.card(id)?.menu ?: return@filter true
                        !MenuLogic.isHidden(hidden, menu)
                    }
                }),
            )
        }
    }.getOrDefault(HudLayout.defaults())

    private fun saveHud(layout: HudLayout.Layout) {
        runCatching {
            prefs.edit {
                putString(KEY_HUD_LAYOUT, HudLayout.toJson(layout))
                putInt(KEY_HUD_VERSION, HudLayout.VERSION)
            }
        }
    }

    private fun loadPresets(): List<HudLayout.Preset> = runCatching {
        val raw = prefs.getString(KEY_HUD_PRESETS, null) ?: return@runCatching emptyList()
        val arr = JarvisJson.parseToJsonElement(raw) as? kotlinx.serialization.json.JsonArray
            ?: return@runCatching emptyList()
        arr.mapNotNull { el ->
            val obj = el as? kotlinx.serialization.json.JsonObject ?: return@mapNotNull null
            val title = (obj["title"] as? kotlinx.serialization.json.JsonPrimitive)
                ?.takeIf { it.isString }?.content ?: return@mapNotNull null
            val layout = HudLayout.fromJson(
                (obj["layout"] as? kotlinx.serialization.json.JsonPrimitive)
                    ?.takeIf { it.isString }?.content ?: return@mapNotNull null,
            ) ?: return@mapNotNull null
            HudLayout.copyAs(title, layout).copy(id = (obj["id"] as? kotlinx.serialization.json.JsonPrimitive)
                ?.takeIf { it.isString }?.content ?: HudLayout.copyAs(title, layout).id)
        }
    }.getOrDefault(emptyList())

    private fun savePresets(presets: List<HudLayout.Preset>) {
        runCatching {
            val arr = presets.map { p ->
                kotlinx.serialization.json.buildJsonObject {
                    put("id", p.id)
                    put("title", p.title)
                    put("layout", HudLayout.toJson(p.layout))
                }
            }
            prefs.edit {
                putString(KEY_HUD_PRESETS, kotlinx.serialization.json.JsonArray(arr).toString())
                putInt(KEY_HUD_VERSION, HudLayout.VERSION)
            }
        }
    }

    private companion object {
        const val PREFS = "jarvis_menus"
        const val KEY_VERSION = "v"
        const val KEY_HIDDEN = "hidden"
        const val KEY_COLLAPSED = "collapsed"
        // The Home HUD (A1): its own keys, so the menu catalogue's own version
        // and the layout's version can never be confused for one another.
        const val KEY_HUD_VERSION = "hud_v"
        const val KEY_HUD_LAYOUT = "hud_layout"
        const val KEY_HUD_PRESETS = "hud_presets"
    }
}
