package com.jarvis.client.net

/**
 * "Show or hide menus" - the pure rules (docs/MENU-VISIBILITY-DESIGN.md,
 * docs/JARVIS-API.md section 109). No Android in here, so MenuVisibilityTest can run
 * them on a plain JVM against the fixture the PC's reference code wrote
 * (`menu-cases.json`, `backend/jarvis_menus.py`) - the desktop's menu-visibility.js does
 * exactly the same, so the two apps cannot disagree about what "hide the finance menu"
 * means.
 *
 * Two independent states per menu: HIDDEN (gone from the list) and FOLDED (its title
 * stays, its body folds to one line). Hiding only tidies: nothing is turned off, no card,
 * no Windows Hello or screen lock. A never-hideable menu (approvals, Security, What asks
 * first, the connection, ...) is never hidden by anything in here: [hide] refuses it,
 * [isHidden] says "visible" even if a stored file lists it, and [sanitize] drops it.
 */
data class MenuState(
    /** Menu ids and `group.<id>` ids that are hidden. A hidden group stores the GROUP id only. */
    val hidden: Set<String> = emptySet(),
    /** Menu ids that are folded. Independent of [hidden]: showing a menu does not unfold it. */
    val collapsed: Set<String> = emptySet(),
)

/** What a change did. [word] is the fixture's `result`. */
enum class MenuResult(val word: String) {
    OK("ok"),
    /** A never-hideable menu. */
    NEVER("never"),
    /** No such menu or group in this app. */
    UNKNOWN("unknown"),
    /** A menu that cannot be folded. */
    CANNOT("cannot"),
}

object MenuLogic {
    const val ACTION_HIDE = "hide"
    const val ACTION_SHOW = "show"
    const val ACTION_COLLAPSE = "collapse"
    const val ACTION_EXPAND = "expand"
    const val ACTION_RESET = "reset"
    val ACTIONS = listOf(ACTION_HIDE, ACTION_SHOW, ACTION_COLLAPSE, ACTION_EXPAND, ACTION_RESET)

    /** This app. The fixture also runs the desktop's cases, so every function takes an app. */
    const val PHONE = "phone"
    const val DESKTOP = "desktop"

    private val byId: Map<String, MenuCatalog.Menu> = MenuCatalog.MENUS.associateBy { it.id }
    private val groupIds: Set<String> = MenuCatalog.GROUPS.map { it.id }.toSet()

    fun menu(id: String): MenuCatalog.Menu? = byId[id]

    fun isGroupId(id: String): Boolean = id in groupIds

    private fun has(m: MenuCatalog.Menu, app: String?): Boolean = when (app) {
        null -> true
        PHONE -> m.phone
        DESKTOP -> m.desktop
        else -> false
    }

    /** The menu ids in a group, for one app (null: both). */
    fun members(group: String, app: String? = PHONE): List<String> =
        MenuCatalog.MENUS.filter { it.group == group && has(it, app) }.map { it.id }

    fun children(id: String): List<String> = MenuCatalog.MENUS.filter { it.parent == id }.map { it.id }

    /** The chain of parents, nearest first (a parent this app does not have still counts). */
    fun ancestors(id: String): List<String> {
        val out = ArrayList<String>()
        var m = byId[id]
        while (m != null && m.parent != null) {
            out.add(m.parent!!)
            m = byId[m.parent!!]
        }
        return out
    }

    /** Is [id] a menu, or a group with at least one member, in this app? */
    fun known(id: String, app: String? = PHONE): Boolean =
        if (isGroupId(id)) members(id, app).isNotEmpty() else byId[id]?.let { has(it, app) } == true

    /** Drops stale ids: unknown, the other app's, never-hideable, empty groups. */
    fun sanitize(state: MenuState, app: String? = PHONE): MenuState {
        val hidden = state.hidden.filter { id ->
            if (isGroupId(id)) {
                members(id, app).isNotEmpty()
            } else {
                byId[id]?.let { it.hide && has(it, app) } == true
            }
        }.toSet()
        val collapsed = state.collapsed.filter { id ->
            byId[id]?.let { it.collapse && has(it, app) } == true
        }.toSet()
        return MenuState(hidden, collapsed)
    }

    /**
     * Is this menu hidden right now? Never for a never-hideable menu; never for a menu in
     * [visit] (opened for one visit by a link); otherwise when its own id, its group's id
     * or a parent's id is hidden.
     */
    fun isHidden(state: MenuState, id: String, visit: Set<String> = emptySet()): Boolean {
        val m = byId[id] ?: return false
        if (!m.hide) return false
        if (id in visit) return false
        if (id in state.hidden) return true
        if (m.group != null && m.group in state.hidden) return true
        return m.parent != null && isHidden(state, m.parent, visit)
    }

    fun isCollapsed(state: MenuState, id: String, visit: Set<String> = emptySet()): Boolean {
        val m = byId[id] ?: return false
        return m.collapse && id in state.collapsed && id !in visit
    }

    /**
     * The N in "N hidden - Show": a hidden group is ONE switch (its members are not counted
     * again), and a menu under a hidden parent is not counted again.
     */
    fun hiddenCount(state: MenuState, app: String = PHONE): Int {
        var n = 0
        for (g in MenuCatalog.GROUPS) {
            if (g.id in state.hidden && members(g.id, app).isNotEmpty()) n++
        }
        for (m in MenuCatalog.MENUS) {
            if (!has(m, app) || !m.hide || m.id !in state.hidden) continue
            if (m.group != null && m.group in state.hidden) continue
            if (m.parent != null && isHidden(state, m.parent)) continue
            n++
        }
        return n
    }

    private fun coverMembers(cover: String): List<String> =
        if (isGroupId(cover)) members(cover, null) else children(cover)

    fun hide(state: MenuState, id: String, app: String? = PHONE): Pair<MenuState, MenuResult> {
        if (isGroupId(id)) {
            if (members(id, app).isEmpty()) return state to MenuResult.UNKNOWN
            val hidden = state.hidden - members(id, null).toSet() + id
            return state.copy(hidden = hidden) to MenuResult.OK
        }
        val m = byId[id]
        if (m == null || !has(m, app)) return state to MenuResult.UNKNOWN
        if (!m.hide) return state to MenuResult.NEVER
        return state.copy(hidden = state.hidden + id) to MenuResult.OK
    }

    /**
     * Showing a group clears the group id and its members. Showing one menu whose group or
     * parent is hidden shows ONLY that menu: the cover's id is cleared and its other
     * members are hidden one by one instead.
     */
    fun show(state: MenuState, id: String, app: String? = PHONE): Pair<MenuState, MenuResult> {
        if (isGroupId(id)) {
            if (members(id, app).isEmpty()) return state to MenuResult.UNKNOWN
            return state.copy(hidden = state.hidden - members(id, null).toSet() - id) to MenuResult.OK
        }
        val m = byId[id]
        if (m == null || !has(m, app)) return state to MenuResult.UNKNOWN
        var hidden = state.hidden - id
        val covers = (if (m.group != null) listOf(m.group) else emptyList()) + ancestors(id)
        val mine = ancestors(id)
        for (cover in covers) {
            if (cover !in hidden) continue
            hidden = hidden - cover
            for (other in coverMembers(cover)) {
                if (other != id && other !in mine && id !in ancestors(other) && byId[other]?.hide == true) {
                    hidden = hidden + other
                }
            }
        }
        return state.copy(hidden = hidden) to MenuResult.OK
    }

    fun collapse(state: MenuState, id: String, app: String? = PHONE): Pair<MenuState, MenuResult> {
        if (isGroupId(id)) {
            val all = members(id, app)
            if (all.isEmpty()) return state to MenuResult.UNKNOWN
            val ids = all.filter { byId[it]?.collapse == true }
            if (ids.isEmpty()) return state to MenuResult.CANNOT
            return state.copy(collapsed = state.collapsed + ids) to MenuResult.OK
        }
        val m = byId[id]
        if (m == null || !has(m, app)) return state to MenuResult.UNKNOWN
        if (!m.collapse) return state to MenuResult.CANNOT
        return state.copy(collapsed = state.collapsed + id) to MenuResult.OK
    }

    fun expand(state: MenuState, id: String, app: String? = PHONE): Pair<MenuState, MenuResult> {
        if (isGroupId(id)) {
            if (members(id, app).isEmpty()) return state to MenuResult.UNKNOWN
            return state.copy(collapsed = state.collapsed - members(id, null).toSet()) to MenuResult.OK
        }
        val m = byId[id]
        if (m == null || !has(m, app)) return state to MenuResult.UNKNOWN
        return state.copy(collapsed = state.collapsed - id) to MenuResult.OK
    }

    fun reset(): Pair<MenuState, MenuResult> = MenuState() to MenuResult.OK

    fun apply(state: MenuState, action: String, id: String, app: String? = PHONE): Pair<MenuState, MenuResult> =
        when (action) {
            ACTION_HIDE -> hide(state, id, app)
            ACTION_SHOW -> show(state, id, app)
            ACTION_COLLAPSE -> collapse(state, id, app)
            ACTION_EXPAND -> expand(state, id, app)
            ACTION_RESET -> reset()
            else -> state to MenuResult.UNKNOWN
        }

    /**
     * A link to a hidden menu shows THAT menu (and what contains it) for the visit only -
     * not stored, and its group stays hidden.
     */
    fun visitSet(id: String): Set<String> =
        if (byId[id] == null) emptySet() else setOf(id) + ancestors(id)
}

/**
 * What a screen reads to draw: the stored [state] plus the ids opened for the current visit
 * (never stored). Pure; the Android holder is data/MenuPrefs.kt.
 */
data class MenuView(
    val state: MenuState = MenuState(),
    val visit: Set<String> = emptySet(),
) {
    /** Draw this menu? */
    fun shows(id: String): Boolean = !MenuLogic.isHidden(state, id, visit)

    /** Draw only its title and a one-line fold? */
    fun folded(id: String): Boolean = MenuLogic.isCollapsed(state, id, visit)

    /** Shown only because a link opened it for this visit (the "Shown for now" banner). */
    fun onVisit(id: String): Boolean = id in visit && MenuLogic.isHidden(state, id)

    val hiddenCount: Int get() = MenuLogic.hiddenCount(state, MenuLogic.PHONE)
}
