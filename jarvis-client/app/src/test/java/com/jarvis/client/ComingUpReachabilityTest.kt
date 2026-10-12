package com.jarvis.client

import com.jarvis.client.net.MenuCatalog
import com.jarvis.client.net.MenuLogic
import com.jarvis.client.net.MenuState
import com.jarvis.client.net.MenuView
import com.jarvis.client.ui.FindAnything
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The device's fourth jump defect (2026-10-11, lead's run on `a34a6372`): Find
 * offered "Coming up", the tap did nothing, and the walk's own log said
 * `found=false rows=11` - so `brain-plate:coming-up` was not in Brain's list at
 * that moment.
 *
 * The first hypothesis was that `menus.shows("brain.work.coming-up")` was false,
 * i.e. the owner had hidden that menu. **That is impossible, and these tests are
 * what says so** - it is in [MenuCatalog.NEVER_HIDE], and the stored state is
 * sanitized on the way in. Written down as tests rather than as a claim because
 * the hypothesis is attractive and wrong, and the next reader will have it too.
 */
class ComingUpReachabilityTest {

    @Test
    fun `Coming up can never be hidden, so its plate is always composed`() {
        assertTrue(
            "Coming up must be in NEVER_HIDE: its own why-line says a due reminder " +
                "shows here and it must stay reachable",
            "brain.work.coming-up" in MenuCatalog.NEVER_HIDE,
        )
        // A stored file that lists it hidden anyway - exactly what a bug or an
        // old file could produce - is sanitized away before anything reads it.
        val stored = MenuState(hidden = setOf("brain.work.coming-up"))
        assertEquals(
            "MenuLogic must drop a never-hideable id out of a stored file",
            emptySet<String>(),
            MenuLogic.sanitize(stored, MenuLogic.PHONE).hidden,
        )
        assertTrue(
            "so shows() is true and BrainScreen always composes brain-plate:coming-up",
            MenuView(state = stored).shows("brain.work.coming-up"),
        )
    }

    @Test
    fun `Find offers Coming up, and does so through the same rule the screens use`() {
        val menus = MenuView(state = MenuState())
        val found = FindAnything.results("coming", menus, privateHidden = false)
            .firstOrNull { it.id == "brain.work.coming-up" }
        assertTrue("Coming up must be findable - the lead's run searched for it", found != null)
        // Its row reads `shows`, not a hardcoded list, so it cannot disagree with
        // BrainScreen about what is hidden.
        assertTrue("its row is guarded like every other menu row", found!!.menu)
        assertEquals("and it is guarded by its OWN menu id", "brain.work.coming-up", found.shownBy)
        // The section it names is the section BrainScreen holds.
        assertEquals("coming-up", found.section)
    }

    @Test
    fun `a menu that IS hideable disappears from Find, which is the rule coming-up is exempt from`() {
        // The contrast, so the two tests above are not an accident of "everything
        // is findable": goals is hideable and goes when hidden.
        val menus = MenuView(state = MenuState())
        assertTrue(
            "goals must be findable when shown, or this proves nothing",
            FindAnything.results("goals", menus, privateHidden = false).any { it.id == "brain.work.goals" },
        )
        val hidden = MenuView(state = MenuState(hidden = setOf("brain.work.goals")))
        assertFalse(
            "a hideable menu's row leaves Find - the mechanism the first hypothesis " +
                "assumed was failing for coming-up",
            FindAnything.results("goals", hidden, privateHidden = false).any { it.id == "brain.work.goals" },
        )
    }
}
