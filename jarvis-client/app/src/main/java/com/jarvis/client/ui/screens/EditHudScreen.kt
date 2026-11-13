package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGesturesAfterLongPress
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInRoot
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.HudLayout
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Rule
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome

/**
 * The phone's Edit HUD screen (the Android `A3` slice of the editable-HUD
 * design, 2026-11-02) - the owner's own words, 2026-11-01: *"add building the
 * real editor to the queue"*.
 *
 * WHAT IT EDITS. One [HudLayout.Layout]: four ordered sections
 * (`top_strip`, `hero`, `body`, `composer`) and the cards in each, in order.
 * [HudLayout] is pure Kotlin and is where every rule lives; this file is the
 * screen that calls it and nothing else. Since 2026-11-10 the `top_strip`
 * section is drawn in TWO places - its safety cards stay on the Home screen as
 * one compact row, its other cards open from the app's **More menu** (the owner
 * asked for the strip's height back) - so this editor says where each half
 * appears; the other three sections are the Home screen's full-width cards.
 *
 * ONE REDUCER, THREE INPUTS. A card moves by (a) dragging it, (b) the click-only
 * Up / Down / "Move to" buttons, and (c) five TalkBack custom actions on the
 * card. All three produce the SAME [HudLayout.Action] and hand it to
 * [HudEditSession.apply], which calls [HudLayout.apply] - so a drag and a
 * button press cannot disagree about what "move this card" means. That is the
 * WCAG 2.2 SC 2.5.7 (twin-path) claim the desktop's `hud-edit.js` makes
 * (rulings 23-27), mirrored here: every motion has a click-only equivalent, and
 * both reach one function.
 *
 * A DRAFT, THEN ONE WRITE. Motions are never saved as they happen. The session
 * holds a draft and a session-only undo stack; `Done` hands the finished
 * document to [com.jarvis.client.data.MenuPrefs.saveLayout] exactly once. A
 * drag that moved a card through ten positions, an Undo, and a "Move to" are
 * all still ONE write, and nothing is written per frame.
 *
 * EVERYTHING IS VISIBLE WHILE EDITING. A menu the owner has hidden (by voice or
 * in Settings) is not hidden here: the editor draws every card the layout holds
 * and says which ones Home is not drawing at the moment, because a card that
 * cannot be seen cannot be put back. See [HudLayout.visible] and
 * `forcedVisible` - the editor passes every card, so the hide rules cannot take
 * a card out of reach.
 *
 * PROTECTED CARDS. The three safety surfaces (approvals, Live/Stop, the
 * emergency stop) can be moved like any other card, but no edit, preset or
 * pasted document can remove them: [HudLayout.normalize] forces them back in on
 * every path out of [HudLayout.apply]. The always-drawn indicators are never
 * cards at all, so they can neither be moved nor hidden here.
 *
 * NOT ON THE PHONE: no route, no approval card, no pairing token. A layout is a
 * display preference, the same class as the theme, and it is stored on this
 * phone only ([com.jarvis.client.data.MenuPrefs]); nothing is sent to the PC and
 * the desktop's own seven widescreen presets are untouched (docs/ARCHITECTURE.md
 * section 8).
 */
class HudEditSession(initial: HudLayout.Layout) {

    /** What the phone has stored right now - the draft is measured against it. */
    private val saved: HudLayout.Layout = HudLayout.normalize(initial)

    /** The undo stack. In memory for the length of one visit; never stored. */
    private val past = ArrayDeque<HudLayout.Layout>()

    /** The layout being edited. Only [whatDoneSaves] may leave this class. */
    var layout: HudLayout.Layout = saved
        private set

    val canUndo: Boolean get() = past.isNotEmpty()

    /** True while the draft differs from what the phone has stored. */
    val dirty: Boolean get() = layout != saved

    /**
     * THE one path. A drag, an Up / Down / "Move to" button and a TalkBack
     * custom action all call this with the same action, and it is the only
     * place the draft changes by a move. An edit the reducer refuses (an
     * unknown card, a section that does not exist, a card that cannot move
     * further) is not recorded on the undo stack, because nothing happened.
     */
    fun apply(action: HudLayout.Action): HudLayout.Layout = record(HudLayout.apply(layout, action))

    /**
     * A whole document replaces the draft: a custom preset the owner picked, or
     * a pasted one. Normalised first, so a hostile document is closed-world
     * before it is ever drawn - and it is still only a draft until `Done`.
     */
    fun replace(candidate: HudLayout.Layout?): HudLayout.Layout =
        record(candidate?.let { HudLayout.normalize(it) })

    /** One step back. Answers the draft unchanged when there is nothing to undo. */
    fun undo(): HudLayout.Layout {
        if (past.isEmpty()) return layout
        layout = past.removeLast()
        return layout
    }

    /** "Reset": back to the default arrangement. A draft change like any other. */
    fun restart(): HudLayout.Layout = apply(HudLayout.Action.Reset)

    /** What `Done` stores - and the only layout this class ever hands out to be saved. */
    fun whatDoneSaves(): HudLayout.Layout = layout

    private fun record(next: HudLayout.Layout?): HudLayout.Layout {
        if (next == null || next == layout) return layout
        past.addLast(layout)
        while (past.size > UNDO_LIMIT) past.removeFirst()
        layout = next
        return layout
    }

    companion object {
        /** How many steps back one visit can go. More than any plausible edit. */
        const val UNDO_LIMIT = 50
    }
}

/**
 * The four sections in plain words, in the order the editor lists them: the
 * Home screen's full-width cards first, then the top strip (its safety cards are
 * the compact row on Home, its other cards open from More).
 */
internal val HUD_SECTION_WORDS: Map<String, String> = mapOf(
    HudLayout.TOP_STRIP to "Top strip",
    HudLayout.HERO to "Hero",
    HudLayout.BODY to "Body",
    HudLayout.COMPOSER to "Composer",
)

/** What the screen says above the sections. */
internal const val HUD_EDIT_INTRO =
    "Move a card with a drag, with Up and Down, with Move to, or with the " +
        "actions TalkBack offers. Nothing is saved until you press Done."

@Composable
fun EditHudScreen(
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    val menus = JarvisRuntime.menus
    // The layout the phone holds now. Read once to open the session; the
    // session keeps the draft from then on, so a Done cannot restart it.
    val stored by menus.hudLayout.collectAsState()
    val customs by menus.customPresets.collectAsState()
    val view by menus.view.collectAsState()
    val session = remember { HudEditSession(stored) }

    // Two mirrors of the session for Compose: the draft it holds, and whether
    // there is anything to undo. Nothing else about the session is cached, so
    // the reducer stays the only authority.
    var layout by remember { mutableStateOf(session.layout) }
    var canUndo by remember { mutableStateOf(session.canUndo) }

    fun edit(action: HudLayout.Action) {
        layout = session.apply(action)
        canUndo = session.canUndo
    }

    /** One place everything that replaces the whole document goes through. */
    fun replaceWhole(candidate: HudLayout.Layout?) {
        layout = session.replace(candidate)
        canUndo = session.canUndo
    }

    var moveTo by remember { mutableStateOf<String?>(null) }
    var renaming by remember { mutableStateOf<HudLayout.Preset?>(null) }
    var duplicateOpen by remember { mutableStateOf(false) }
    var importNote by remember { mutableStateOf<String?>(null) }
    var pasted by rememberSaveable { mutableStateOf("") }
    val clipboard = LocalClipboardManager.current

    // Where each section and each card is on the glass, measured as they are
    // laid out. A drag reads these once, when the finger comes up - never per
    // frame, and never to decide anything until the drop.
    val sectionBounds = remember { mutableStateMapOf<String, Pair<Float, Float>>() }
    val cardBounds = remember { mutableStateMapOf<String, Pair<Float, Float>>() }
    var draggingId by remember { mutableStateOf<String?>(null) }
    var dragDy by remember { mutableFloatStateOf(0f) }

    /**
     * The drop. One reducer call for the whole gesture: which section the
     * lifted card is over, and which place in that section, worked out from
     * where the cards actually are.
     */
    fun dropCard(id: String) {
        val from = cardBounds[id]
        draggingId = null
        val dy = dragDy
        dragDy = 0f
        if (from == null || dy == 0f) return
        val mid = (from.first + from.second) / 2f + dy
        val section = HudLayout.SECTIONS.firstOrNull { s ->
            val b = sectionBounds[s] ?: return@firstOrNull false
            mid >= b.first && mid <= b.second
        } ?: return
        val ids = layout.items(section)
        // The index a Move takes is the index in the section AS IT IS DRAWN
        // now, the dragged card included - see HudLayout.move.
        val at = ids.indexOfFirst { other ->
            val b = cardBounds[other] ?: return@indexOfFirst false
            mid < (b.first + b.second) / 2f
        }.let { if (it < 0) ids.size else it }
        edit(HudLayout.Action.Move(id, section, at))
    }

    var resetAsked by remember { mutableStateOf(false) }

    Column(modifier.fillMaxSize().background(chrome.surface0)) {
        TopBar(
            title = "Edit HUD",
            onBack = onBack,
            subtitle = "Your Home screen and the More menu, in four sections",
            trailing = {
                Quiet(
                    "Undo",
                    enabled = canUndo,
                    onClick = {
                        layout = session.undo()
                        canUndo = session.canUndo
                    },
                )
            },
        )

        Column(
            Modifier
                .weight(1f)
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp),
        ) {
            Gap(12)
            Text(
                HUD_EDIT_INTRO,
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            Gap(4)
            Text(
                "Everything is shown while you edit, including cards Home is " +
                    "hiding right now.",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )

            // ---- the four sections, in draw order -------------------------
            for (section in HudLayout.SECTIONS) {
                val ids = layout.items(section)
                Column(
                    Modifier
                        .fillMaxWidth()
                        .onGloballyPositioned { c ->
                            val y = c.positionInRoot().y
                            sectionBounds[section] = y to (y + c.size.height)
                        },
                ) {
                    Gap(14)
                    Section(HUD_SECTION_WORDS.getValue(section)) {
                        // The one section that is drawn in two places (2026-11-10):
                        // say where each half appears, so moving a card here is not
                        // a card vanishing from the phone.
                        if (section == HudLayout.TOP_STRIP) {
                            Text(
                                "The safety cards here stay on Home, drawn small. " +
                                    "The other cards here open from the app's More menu.",
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.textMid,
                            )
                        }
                        if (ids.isEmpty()) {
                            Text(
                                "Nothing in this section yet. Add one below, or move a card here.",
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.textLo,
                            )
                        }
                        ids.forEachIndexed { index, id ->
                            EditableCard(
                                id = id,
                                index = index,
                                count = ids.size,
                                hidden = HudLayout.card(id)?.menu?.let { !view.shows(it) } == true &&
                                    !HudLayout.isProtected(id),
                                dragging = draggingId == id,
                                dy = if (draggingId == id) dragDy else 0f,
                                onMeasured = { top, bottom -> cardBounds[id] = top to bottom },
                                onMove = { edit(it) },
                                onOpenMoveTo = { moveTo = id },
                                onDragStart = {
                                    draggingId = id
                                    dragDy = 0f
                                },
                                onDrag = { dragDy += it },
                                onDrop = { dropCard(id) },
                                onDragCancel = {
                                    draggingId = null
                                    dragDy = 0f
                                },
                            )
                        }
                    }
                }
            }

            // ---- cards the layout does not hold ---------------------------
            val missing = HudLayout.missingFrom(layout)
            if (missing.isNotEmpty()) {
                Gap(14)
                Section("Not on your Home screen") {
                    Text(
                        "These exist and this layout does not show them. Add puts " +
                            "one back in the section it belongs to by default.",
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                    for (id in missing) {
                        val card = HudLayout.card(id) ?: continue
                        Row(
                            Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(Modifier.weight(1f)) {
                                Text(
                                    card.title,
                                    style = MaterialTheme.typography.titleSmall,
                                    color = chrome.textHi,
                                )
                                Text(
                                    card.about,
                                    style = MaterialTheme.typography.labelSmall,
                                    color = chrome.textLo,
                                    maxLines = 2,
                                    overflow = TextOverflow.Ellipsis,
                                )
                            }
                            Quiet("Add", onClick = { edit(HudLayout.Action.Add(id, card.section)) })
                        }
                    }
                }
            }

            // ---- presets ---------------------------------------------------
            Gap(14)
            Section("Presets") {
                Text(
                    "The five built-in arrangements are read-only. Duplicate one, " +
                        "then edit your own copy.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
                for (preset in HudLayout.BUILT_IN_PRESETS) {
                    PresetRow(
                        title = preset.title,
                        about = preset.about,
                        builtIn = true,
                        onApply = { edit(HudLayout.Action.ApplyPreset(preset.id)) },
                        onRename = null,
                        onDelete = null,
                    )
                }
                for (preset in customs) {
                    PresetRow(
                        title = preset.title,
                        about = preset.about,
                        builtIn = false,
                        onApply = { replaceWhole(preset.layout) },
                        onRename = { renaming = preset },
                        onDelete = { menus.deleteCustomPreset(preset.id) },
                    )
                }
                Gap(6)
                Secondary(
                    "Duplicate to custom",
                    modifier = Modifier.fillMaxWidth(),
                    onClick = { duplicateOpen = true },
                )
            }

            // ---- JSON in and out -------------------------------------------
            Gap(14)
            Section("Copy it to another phone") {
                Text(
                    "This is the whole layout, and it carries no words of a chat and " +
                        "no memory - four sections and card ids. A pasted document " +
                        "reads through the same safe reader a stored one does, so a " +
                        "hand-edited one can never remove a safety card.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
                Gap(8)
                SelectionContainer {
                    Text(
                        HudLayout.toJson(layout),
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textMid,
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(max = 120.dp),
                        maxLines = 6,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                Gap(8)
                Secondary(
                    "Copy the layout",
                    modifier = Modifier.fillMaxWidth(),
                    onClick = {
                        clipboard.setText(AnnotatedString(HudLayout.toJson(layout)))
                        importNote = "Copied. Paste it into a note to keep it."
                    },
                )
                Gap(10)
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(
                            "Paste a layout",
                            style = MaterialTheme.typography.labelLarge,
                            color = chrome.textHi,
                        )
                        Gap(4)
                        BasicTextField(
                            value = pasted,
                            onValueChange = { pasted = it },
                            textStyle = MaterialTheme.typography.bodySmall.copy(color = chrome.textHi),
                            cursorBrush = SolidColor(chrome.textHi),
                            modifier = Modifier
                                .fillMaxWidth()
                                .heightIn(min = 48.dp)
                                .semantics { contentDescription = "A layout to import" },
                        )
                    }
                    Quiet(
                        "Import",
                        enabled = pasted.isNotBlank(),
                        onClick = {
                            val safe = HudLayout.fromJson(pasted)
                            if (safe == null) {
                                importNote = "That is not a layout this app can read. Nothing changed."
                            } else {
                                replaceWhole(safe)
                                importNote = "Imported. Nothing is saved until you press Done."
                            }
                        },
                    )
                }
                importNote?.let {
                    Gap(6)
                    Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                }
            }

            Gap(30)
        }

        // ---- the bar that is always there --------------------------------
        Column(Modifier.fillMaxWidth().background(chrome.surface1)) {
            Rule()
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Quiet("Reset", onClick = { resetAsked = true })
                Text(
                    if (session.dirty) "Not saved yet" else "Saved",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                    modifier = Modifier.weight(1f),
                )
                Primary(
                    "Done",
                    onClick = {
                        menus.saveLayout(session.whatDoneSaves())
                        onBack()
                    },
                )
            }
        }
    }

    // ---- "Move to": the click-only cross-section path ---------------------
    moveTo?.let { id ->
        val title = HudLayout.card(id)?.title ?: id
        Dialog(onDismissRequest = { moveTo = null }) {
            Plate {
                Kicker("Move $title")
                Gap(4)
                Text(
                    "Pick a section and a place in it.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
                for (section in HudLayout.SECTIONS) {
                    Gap(8)
                    Text(
                        HUD_SECTION_WORDS.getValue(section),
                        style = MaterialTheme.typography.labelLarge,
                        color = chrome.textHi,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Quiet("First", onClick = {
                            edit(HudLayout.Action.First(id, section))
                            moveTo = null
                        })
                        Quiet("Last", onClick = {
                            edit(HudLayout.Action.Last(id, section))
                            moveTo = null
                        })
                    }
                }
                Gap(10)
                Quiet("Cancel", onClick = { moveTo = null })
            }
        }
    }

    // ---- "Duplicate to custom" -------------------------------------------
    if (duplicateOpen) {
        NameDialog(
            title = "Name your copy",
            initial = "My layout",
            confirm = "Save as my preset",
            onDismiss = { duplicateOpen = false },
            onConfirm = { name ->
                duplicateOpen = false
                // The copy is made from what Home shows when the owner presses
                // this, so a draft that has not been saved yet is saved first:
                // "duplicate what I am looking at" has to mean the draft.
                menus.saveLayout(session.whatDoneSaves())
                menus.duplicateToCustom(name)
            },
        )
    }

    // ---- rename one of the owner's copies ---------------------------------
    renaming?.let { preset ->
        NameDialog(
            title = "Rename this preset",
            initial = preset.title,
            confirm = "Rename",
            onDismiss = { renaming = null },
            onConfirm = { name ->
                renaming = null
                menus.renameCustomPreset(preset.id, name)
            },
        )
    }

    // ---- "Reset" asks once ------------------------------------------------
    if (resetAsked) {
        Dialog(onDismissRequest = { resetAsked = false }) {
            Plate {
                Kicker("Back to the default arrangement?")
                Gap(6)
                Text(
                    "Every card goes back to its own section, in the order the app " +
                        "ships. The change is not saved until you press Done.",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                )
                Gap(10)
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Quiet("Cancel", onClick = { resetAsked = false })
                    Quiet("Reset", onClick = {
                        resetAsked = false
                        layout = session.restart()
                        canUndo = session.canUndo
                    })
                }
            }
        }
    }
}

/**
 * One card in one section: its words, its five inputs, and the drag.
 *
 * The five TalkBack actions are the accessible twin of the drag and of the
 * three buttons: they build the same [HudLayout.Action] and call the same
 * [HudEditSession.apply] the finger does.
 */
@Composable
private fun EditableCard(
    id: String,
    index: Int,
    count: Int,
    hidden: Boolean,
    dragging: Boolean,
    dy: Float,
    onMeasured: (Float, Float) -> Unit,
    onMove: (HudLayout.Action) -> Unit,
    onOpenMoveTo: () -> Unit,
    onDragStart: () -> Unit,
    onDrag: (Float) -> Unit,
    onDrop: () -> Unit,
    onDragCancel: () -> Unit,
) {
    val chrome = LocalChrome.current
    val card = HudLayout.card(id)
    val title = card?.title ?: id
    val about = card?.about.orEmpty()
    val protected = HudLayout.isProtected(id)
    val actions = buildList {
        add(CustomAccessibilityAction("Move up") {
            onMove(HudLayout.Action.Earlier(id))
            true
        })
        add(CustomAccessibilityAction("Move down") {
            onMove(HudLayout.Action.Later(id))
            true
        })
        for (section in HudLayout.SECTIONS) {
            val words = HUD_SECTION_WORDS.getValue(section)
            add(CustomAccessibilityAction("Move to the start of $words") {
                onMove(HudLayout.Action.First(id, section))
                true
            })
            add(CustomAccessibilityAction("Move to the end of $words") {
                onMove(HudLayout.Action.Last(id, section))
                true
            })
        }
    }

    Column(
        Modifier
            .fillMaxWidth()
            .onGloballyPositioned { c ->
                val y = c.positionInRoot().y
                onMeasured(y, y + c.size.height)
            }
            .graphicsLayer {
                translationY = if (dragging) dy else 0f
                alpha = if (dragging) 0.85f else 1f
            }
            .pointerInput(id) {
                detectDragGesturesAfterLongPress(
                    onDragStart = { onDragStart() },
                    onDrag = { change, amount ->
                        change.consume()
                        onDrag(amount.y)
                    },
                    onDragEnd = { onDrop() },
                    onDragCancel = { onDragCancel() },
                )
            }
            .semantics {
                contentDescription = "$title. $about" +
                    if (hidden) " Home is hiding this card right now." else ""
                customActions = actions
            },
    ) {
        Gap(8)
        Plate {
            Text(
                title,
                style = MaterialTheme.typography.titleSmall,
                color = chrome.textHi,
            )
            if (about.isNotEmpty()) {
                Text(
                    about,
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            if (protected) {
                Gap(4)
                Text(
                    "Safety surface: it can move, but no edit can remove it.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.warnInk,
                )
            }
            if (hidden) {
                Gap(4)
                Text(
                    "Home is hiding this one right now. It is shown here so you can move it.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
            Gap(6)
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Quiet("Up", enabled = index > 0, onClick = { onMove(HudLayout.Action.Earlier(id)) })
                Quiet("Down", enabled = index < count - 1, onClick = { onMove(HudLayout.Action.Later(id)) })
                Quiet("Move to", onClick = onOpenMoveTo)
                Text(
                    "Hold and drag",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
        }
    }
}

/** A built-in or one of the owner's copies, with the buttons that act on it. */
@Composable
private fun PresetRow(
    title: String,
    about: String,
    builtIn: Boolean,
    onApply: () -> Unit,
    onRename: (() -> Unit)?,
    onDelete: (() -> Unit)?,
) {
    val chrome = LocalChrome.current
    Gap(8)
    Plate {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
                Text(
                    about,
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                if (builtIn) {
                    Text(
                        "Built in - read-only",
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                }
            }
        }
        Gap(6)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Quiet(if (builtIn) "Use it" else "Use mine", onClick = onApply)
            onRename?.let { Quiet("Rename", onClick = it) }
            onDelete?.let { Quiet("Delete", onClick = it) }
        }
    }
}

/** One short name in a box - the duplicate and the rename both use it. */
@Composable
private fun NameDialog(
    title: String,
    initial: String,
    confirm: String,
    onDismiss: () -> Unit,
    onConfirm: (String) -> Unit,
) {
    val chrome = LocalChrome.current
    // Keyed on the name it opens with: the same dialog is reused when the owner
    // renames one copy and then another, and it must not still say the first.
    var name by remember(initial) { mutableStateOf(initial) }
    Dialog(onDismissRequest = onDismiss) {
        Plate {
            Kicker(title)
            Gap(8)
            BasicTextField(
                value = name,
                onValueChange = { name = it.take(40) },
                singleLine = true,
                textStyle = MaterialTheme.typography.bodyLarge.copy(color = chrome.textHi),
                cursorBrush = SolidColor(chrome.textHi),
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 48.dp)
                    .semantics { contentDescription = "The preset's name" },
            )
            Gap(10)
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Quiet("Cancel", onClick = onDismiss)
                Quiet(confirm, enabled = name.isNotBlank(), onClick = { onConfirm(name) })
            }
        }
    }
}
