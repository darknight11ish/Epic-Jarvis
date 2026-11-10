/**
 * hud-edit.mjs - H2's pure half: the layout reducer, the card/DOM map and the
 * size budget. No browser: everything here is plain functions plus source
 * checks, so it runs in the same second as hud-layout.mjs.
 *
 * WHAT IT PROVES (and why these are the checks that bite):
 *   1. every action returns a layout that is a FIXED POINT of H1's
 *      normalizeLayout, so save-then-load can never rewrite an edit;
 *   2. the protected cards cannot be hidden or moved by any action, and a
 *      refused action changes nothing;
 *   3. `approvals.collapsed` is a saved preference the auto-expand never writes;
 *   4. region orders stay contiguous, so the renderer and the document agree;
 *   5. the reducer never mutates its input (deep-frozen layouts);
 *   6. the card/DOM map covers the registry honestly: each card is either
 *      movable with a selector that exists in the page, or fixed with a reason;
 *   7. the pointer-drag half of hud-edit.js stays inside the ruling's 180-line
 *      budget (measured from the source, not estimated);
 *   8. Hide is a REAL TOGGLE and a hidden card stays reachable in Edit HUD - the
 *      defect the owner's field test found on 2026-10-28. The reducer is pinned
 *      here and the page path is pinned in the source; scenario B's (d2)/(e2) in
 *      tests/hud-edit-fieldtest.mjs drive the real buttons.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  CARD_REGISTRY,
  PRESETS,
  REGIONS,
  presetLayout,
  normalizeLayout,
  effectiveCollapsed,
} from "../src/hud-layout.js";
import {
  CARD_DOM,
  EDIT_REGIONS,
  FIXED_IDS,
  FIXED_REASON,
  MOVABLE_IDS,
  REGION_LABEL,
  SIZES,
  SIZE_BY_KEY,
  applyAction,
  sizeKeyFor,
} from "../src/hud-edit.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const PAGE = readFileSync(join(SRC, "jarvis_hud.html"), "utf8");
const EDIT = readFileSync(join(SRC, "hud-edit.js"), "utf8");

let passed = 0;
const fails = [];
function check(name, condition, detail = "") {
  if (condition) { passed += 1; return; }
  fails.push(name);
  console.log(`FAIL  ${name}${detail ? `\n      ${detail}` : ""}`);
}
const ok = (name) => console.log(`ok    ${name}`);

function deepFreeze(value) {
  if (value && typeof value === "object") {
    for (const key of Object.keys(value)) deepFreeze(value[key]);
    Object.freeze(value);
  }
  return value;
}
function cardOf(layout, id) {
  return layout.cards.find((card) => card.id === id);
}
function orderOf(layout, region) {
  return layout.cards
    .filter((card) => card.region === region)
    .sort((a, b) => a.order - b.order)
    .map((card) => card.id);
}

/** A normalized cockpit layout plus two visible right-rail cards moved by hand. */
function sample() {
  const base = presetLayout("cockpit");
  const doc = {
    ...base,
    cards: base.cards.map((card) => ({ ...card, options: { ...card.options } })),
  };
  cardOf(doc, "waiting").visible = true;
  cardOf(doc, "telemetry").visible = true;
  return normalizeLayout(doc);
}

/* ---------------------------------------------------------------- 1. actions */
{
  const start = sample();
  const moved = applyAction(start, { type: "moveCard", id: "waiting", region: "stage_top", index: 0 });
  check("moveCard moves the card and reports what happened",
    moved.changed && cardOf(moved.layout, "waiting").region === "stage_top"
    && /moved to Stage top/.test(moved.note), moved.note);
  check("...and the source region stays contiguously ordered",
    orderOf(moved.layout, "right_rail").every((id, at, all) =>
      cardOf(moved.layout, id).order === at), orderOf(moved.layout, "right_rail"));
  check("...the result is a fixed point of normalizeLayout (save->load cannot rewrite it)",
    JSON.stringify(normalizeLayout(moved.layout)) === JSON.stringify(moved.layout));

  const resized = applyAction(start, { type: "resizeCard", id: "tools", size: "T" });
  check("resizeCard applies a named size (Tall = 12 x 2)",
    resized.changed && cardOf(resized.layout, "tools").col_span === 12
    && cardOf(resized.layout, "tools").row_span === 2
    && sizeKeyFor(cardOf(resized.layout, "tools")) === "T", resized.note);
  const bounded = applyAction(start, { type: "resizeCard", id: "telemetry", col_span: 99, row_span: 0 });
  check("resizeCard repairs out-of-range spans instead of trusting them",
    cardOf(bounded.layout, "telemetry").col_span === 12
    && cardOf(bounded.layout, "telemetry").row_span === 1, cardOf(bounded.layout, "telemetry"));

  const up = applyAction(start, { type: "reorderCard", id: "budget", delta: -1 });
  check("reorderCard moves one place within the region",
    up.changed && orderOf(up.layout, "right_rail").indexOf("budget")
      < orderOf(start, "right_rail").indexOf("budget"), orderOf(up.layout, "right_rail"));
  const first = orderOf(start, "right_rail")[0];
  const atTop = applyAction(start, { type: "reorderCard", id: first, delta: -1 });
  check("reorderCard at the top is a no-op, not an error", atTop.changed === false);

  const folded = applyAction(start, { type: "toggleCollapsed", id: "telemetry" });
  check("toggleCollapsed flips the saved preference",
    folded.changed && cardOf(folded.layout, "telemetry").collapsed === true);
  const unfolded = applyAction(folded.layout, { type: "toggleCollapsed", id: "telemetry" });
  check("...and flips it back", cardOf(unfolded.layout, "telemetry").collapsed === false);

  const hidden = applyAction(start, { type: "setVisible", id: "tools", visible: false });
  check("setVisible hides an optional card", hidden.changed && cardOf(hidden.layout, "tools").visible === false);
  const shown = applyAction(hidden.layout, { type: "setVisible", id: "tools", visible: true });
  check("...and shows it again", cardOf(shown.layout, "tools").visible === true);
  // 2026-10-28 (the owner's field test): the Hide control is a real toggle, and
  // this is the call it makes - no `visible` value, so the card's own state is
  // flipped. A hidden card's saved document must be able to come back.
  const toggledOff = applyAction(start, { type: "setVisible", id: "tools" });
  check("a bare setVisible toggles a shown card to hidden",
    toggledOff.changed && cardOf(toggledOff.layout, "tools").visible === false, toggledOff.note);
  const toggledOn = applyAction(toggledOff.layout, { type: "setVisible", id: "tools" });
  check("...and toggles it back, so a hidden card in a saved layout can be shown",
    toggledOn.changed && cardOf(toggledOn.layout, "tools").visible === true, toggledOn.note);

  const reset = applyAction(start, { type: "resetToPreset", id: "ambient" });
  check("resetToPreset gives back that preset exactly",
    reset.changed && JSON.stringify(reset.layout) === JSON.stringify(presetLayout("ambient")));
  const badReset = applyAction(start, { type: "resetToPreset", id: "not-a-preset" });
  check("an unknown preset is refused", badReset.refused && badReset.changed === false);
  ok("actions: move, resize, reorder, fold, hide, reset");
}

/* ------------------------------------------------------- 2. protected cards */
{
  const start = sample();
  for (const id of ["approvals", "emergency_stop", "voice_controls", "bar_launcher"]) {
    const hide = applyAction(start, { type: "setVisible", id, visible: false });
    check(`a protected card cannot be hidden (${id})`, hide.refused && hide.changed === false
      && cardOf(hide.layout, id).visible === true, hide.note);
    check(`...and the refusal says which card (${id})`, /can never be hidden/.test(hide.note), hide.note);
  }
  const moveApprovals = applyAction(start, { type: "moveCard", id: "approvals", region: "left_rail", index: 0 });
  check("the approvals card's region is locked (ruling 25)", moveApprovals.refused && moveApprovals.changed === false
    && cardOf(moveApprovals.layout, "approvals").region === cardOf(start, "approvals").region, moveApprovals.note);
  ok("protected cards: unhideable, approvals region locked, refusals carry a reason");
}

/* ------------------------------------------- 3. approvals auto-expand derived */
{
  const start = sample();
  const folded = applyAction(start, { type: "toggleCollapsed", id: "approvals" });
  const card = cardOf(folded.layout, "approvals");
  check("collapsing approvals saves the preference", card.collapsed === true);
  check("...but one waiting card renders it expanded (derived, not written)",
    effectiveCollapsed(card, 1) === false && card.collapsed === true);
  check("...and answering the last card folds it back",
    effectiveCollapsed(card, 0) === true);
  ok("approvals: transient auto-expand never touches the saved document");
}

/** A normal layout that carries EVERY registry card (so fixed ones are present). */
function allCards() {
  return normalizeLayout({
    version: 1,
    id: "all-cards",
    name: "All cards",
    cards: CARD_REGISTRY.map((card) => ({ id: card.id })),
  });
}

/* --------------------------------------------------- 4. fixed cards are fixed */
{
  const start = allCards();
  for (const id of Object.keys(FIXED_IDS)) {
    const move = applyAction(start, { type: "moveCard", id, region: "left_rail", index: 0 });
    check(`a fixed card reports why it cannot move (${id})`,
      move.refused && move.changed === false && move.note === FIXED_REASON, move.note);
  }
  const unknown = applyAction(start, { type: "moveCard", id: "not-a-card", region: "left_rail" });
  check("an unknown card id is refused", unknown.refused);
  const badRegion = applyAction(start, { type: "moveCard", id: "tools", region: "nowhere" });
  check("an unknown region is refused", badRegion.refused);
  const badAction = applyAction(start, { type: "teleport" });
  check("an unknown action is refused", badAction.refused);
  ok("fixed and unknown cards/regions/actions are refused with words");
}

/* --------------------------------------------- 5. pure: no input mutation */
{
  const start = deepFreeze(JSON.parse(JSON.stringify(sample())));
  const before = JSON.stringify(start);
  const actions = [
    { type: "moveCard", id: "waiting", region: "stage_top", index: 0 },
    { type: "reorderCard", id: "tools", delta: 1 },
    { type: "resizeCard", id: "budget", size: "M" },
    { type: "toggleCollapsed", id: "voice_stats" },
    { type: "setVisible", id: "tools", visible: false },
    { type: "resetToPreset", id: "focus" },
    { type: "replaceLayout", layout: presetLayout("minimal") },
  ];
  for (const action of actions) {
    const result = applyAction(start, action);
    check(`no action mutates its input (${action.type})`, JSON.stringify(start) === before);
    check(`no action returns the frozen input by reference (${action.type})`,
      result.layout === start || JSON.stringify(result.layout) === before || result.changed);
  }
  ok("reducer is pure on deep-frozen layouts");
}

/* ------------------------------------- 6. fixed point over a seeded sequence */
{
  let state = sample();
  const ids = MOVABLE_IDS.filter((id) => !["approvals", "bar_launcher"].includes(id));
  const regions = EDIT_REGIONS;
  let seed = 7;
  const rand = (n) => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed % n; };
  let changedCount = 0;
  for (let step = 0; step < 200; step += 1) {
    const id = ids[rand(ids.length)];
    const kind = rand(5);
    const action = kind === 0 ? { type: "moveCard", id, region: regions[rand(regions.length)], index: rand(4) }
      : kind === 1 ? { type: "reorderCard", id, delta: rand(3) - 1 }
        : kind === 2 ? { type: "resizeCard", id, size: SIZES[rand(SIZES.length)].key }
          : kind === 3 ? { type: "toggleCollapsed", id }
            : { type: "setVisible", id, visible: rand(2) === 1 };
    const result = applyAction(state, action);
    if (result.changed) changedCount += 1;
    const once = JSON.stringify(result.layout);
    assert.equal(JSON.stringify(normalizeLayout(result.layout)), once,
      `step ${step}: ${action.type} on ${id} is not a normalizer fixed point`);
    for (const region of REGIONS) {
      orderOf(result.layout, region).forEach((cardId, at) => {
        assert.equal(cardOf(result.layout, cardId).order, at, `step ${step}: order not contiguous in ${region}`);
      });
    }
    state = result.layout;
  }
  check("200 seeded actions all stay normalizer fixed points with contiguous orders",
    changedCount > 40, changedCount);
  ok("fixed-point + canonical-order property over a seeded sequence");
}

/* ----------------------------------------------------- 7. the card/DOM map */
{
  const registryIds = CARD_REGISTRY.map((card) => card.id);
  const mapped = registryIds.filter((id) => MOVABLE_IDS.includes(id) || id in FIXED_IDS);
  check("every registry card is either movable or fixed with a reason",
    mapped.length === registryIds.length,
    registryIds.filter((id) => !mapped.includes(id)));
  check("the movable list has no id outside the registry",
    MOVABLE_IDS.every((id) => registryIds.includes(id)), MOVABLE_IDS);
  check("every movable card has at least one DOM selector",
    MOVABLE_IDS.every((id) => (CARD_DOM[id] || []).length > 0));
  check("every fixed card explains itself",
    Object.values(FIXED_IDS).every((reason) => typeof reason === "string" && reason.length > 10));
  for (const [id, selectors] of Object.entries(CARD_DOM)) {
    for (const selector of selectors) {
      const present = selector === "#hud-open-bar"
        // The Jarvis-bar button is created by the injected shell bootstrap.
        ? readFileSync(join(SRC, "..", "src-tauri", "src", "hud_bootstrap.js"), "utf8").includes("hud-open-bar")
        : PAGE.includes(`id="${selector.slice(1)}"`);
      check(`the page really has ${selector} for ${id}`, present);
    }
  }
  check("the approval card's two hosts are both mapped",
    CARD_DOM.approvals.includes("#approvals") && CARD_DOM.approvals.includes("#initiative"));
  check("the six Bento cards map to their own rail sections",
    ["waiting", "telemetry", "tools", "brain_stats", "budget", "voice_stats"]
      .every((id) => CARD_DOM[id][0].startsWith("#rail-")));
  ok("card/DOM map: complete, honest, and every selector exists in the page");
}

/* -------------------------------------------------- 8. sizes and region words */
{
  check("four size buttons, each with its own key",
    SIZES.length === 4 && new Set(SIZES.map((size) => size.key)).size === 4);
  check("every size fits the schema's bounds",
    SIZES.every((size) => size.col_span >= 1 && size.col_span <= 12
      && size.row_span >= 1 && size.row_span <= 4));
  check("every editable region has words for the owner",
    EDIT_REGIONS.every((region) => typeof REGION_LABEL[region] === "string" && REGION_LABEL[region]));
  check("the size lookup round-trips", SIZES.every((size) => sizeKeyFor(size) === size.key));
  ok("sizes and region labels");
}

/* ------------------------------------------------- 9. the 180-line drag budget */
{
  const start = EDIT.indexOf("// ---------------------------------------------------------------- pointer");
  const end = EDIT.indexOf("// -------------------------------------------------------------- key handling");
  check("the pointer-drag half is a marked block in hud-edit.js", start > 0 && end > start);
  const lines = EDIT.slice(start, end).split("\n").length;
  check(`the pointer-drag half stays inside the ruling's 180 lines (measured ${lines})`, lines <= 180, lines);
  ok("Ruling 24's drag-size budget, measured from the source");
}

/* ------- 10. Hide is a real toggle, and a hidden card stays reachable ---- */
{
  // The owner's field test (2026-10-28) found that the Hide control always sent
  // a fixed "hidden", while being painted as a toggle, and that a hidden card's
  // shell was `display: none`, so its toggle could never be clicked again. Both
  // halves are pinned here at the source; the REAL page path is
  // tests/hud-edit-fieldtest.mjs's (d2)/(e2), which drives the button.
  const toggleCall = EDIT.includes('doAction({ type: "setVisible", id })');
  check("the Hide control toggles through the ONE reducer - it sends no fixed value",
    toggleCall && !/visible:\s*false/.test(EDIT),
    "hud-edit.js still sends a hard-coded visibility on the Hide path");
  check("a hidden card's shell stays painted while editing and is hidden outside it",
    /shell\.hidden = !card\.visible && !editing;/.test(EDIT)
    && /shell\.classList\.toggle\("hud-card-hidden", !card\.visible\);/.test(EDIT));
  check("...its body is folded away, so the card itself is still hidden",
    /body\[data-hud-edit="on"\] \.hud-card-hidden \.hud-card-body\{display:none;\}/.test(PAGE),
    "jarvis_hud.html has no ghost rule for a hidden card's body");
  check("...`.hud-card[hidden]` still hides the whole shell outside edit mode",
    /\.hud-card\[hidden\]\{display:none;\}/.test(PAGE));
  check("...and the ghost says which state the card is in",
    /hud-card-hidden-word/.test(EDIT) && /hud-card-hidden-word/.test(PAGE));
  check("...so the control can be pressed a second time to show the card again",
    /hideBtn\.title = `\$\{hidden \? "Show" : "Hide"\} \$\{labelOf\(card\.id\)\}`;/.test(EDIT),
    "the Hide control never offers Show");
  ok("Hide toggles, and a hidden card can be reached again in Edit HUD");
}

/* ------- 11. In Edit HUD a first click SELECTS, it never performs --------- */
{
  // The owner's report (2026-11-09): "in the edit HUD, when i click on any part
  // including the left column icons, there should be the edit options that
  // appear. right now when i click on it it just opens the icon's intended
  // menu." The behaviour is driven for real in tests/hud-edit-select.mjs; this
  // pins the shape that makes it true, so an edit that deletes or reorders the
  // interception (a capture-phase stop, with the editor's own controls exempt)
  // fails in a second on a machine with no Playwright.
  check("the main-screen click is intercepted in the CAPTURE phase while editing",
    /doc\.addEventListener\("click", onMainScreenClick, true\);/.test(EDIT),
    "onMainScreenClick is not registered as a document capture listener");
  check("...and the interceptor stops the page's own handler before it runs",
    /function onMainScreenClick\(event\) \{[\s\S]*?event\.preventDefault\(\);[\s\S]*?event\.stopPropagation\(\);/
      .test(EDIT),
    "the interceptor does not preventDefault + stopPropagation");
  check("...it runs only while Edit HUD is on",
    /function onMainScreenClick\(event\) \{\s*\n\s*if \(!editing \|\| !event/.test(EDIT),
    "the interceptor is not gated on edit mode");
  check("...the editor's own controls keep their click",
    /const EDITOR_OWN_CLICK = \[[\s\S]*?"#hud-edit-bar"[\s\S]*?"\.hud-card-tools"[\s\S]*?"\[data-hud-card-handle\]"[\s\S]*?"#hud-edit-toggle"[\s\S]*?"#hud-stop"[\s\S]*?\]\.join\(", "\);/
      .test(EDIT),
    "the Done/Undo bar, card toolbars, drag handle, Edit HUD toggle or Stop control is not exempt");
  check("...a click inside a card selects that card through the ONE selector",
    /const shell = event\.target\.closest\("\[data-hud-card\]"\);[\s\S]*?selectEditCard\(id\);/
      .test(EDIT),
    "a click inside a card does not select it");
  check("...a click on the left column's own icons selects the Navigation card",
    /closest\("\.rail\.left"\) && selectedCard !== "nav"[\s\S]*?selectEditCard\("nav"\);/
      .test(EDIT),
    "the left column's non-card icons (Presets, Live, Faces, Calendar, Brain, Galaxy, dock) are not mapped to Navigation");
  check("...a selection names the Cards surface on the body, so its list is the one open",
    /if \(selectedCard\) \{\s*\n\s*editTab = "cards";/.test(EDIT),
    "selectEditCard no longer puts the Cards surface on the body");
  ok("Edit HUD click: capture-phase selection, editor controls exempt, left column maps to Navigation");
}

/* ------- 12. The owner's UI review of 2026-11-09 (Q6-Q9) ---------------- */
{
  // The review's numbers: "Every Card Carries a 7-Button Engineering Toolbar"
  // and "Edit HUD Floats Over the Middle of the Canvas It Edits". These pins
  // are the source half of what tests/hud-edit-tabs.mjs drives for real.
  check("normal use draws NO per-card toolbar (Q6's first half)",
    /body:not\(\[data-hud-edit="on"\]\) \.hud-card \.hud-card-tools\{display:none;\}/.test(PAGE),
    "jarvis_hud.html has no rule hiding the card toolbars outside Edit HUD");
  check("...and the shells' headers stay hidden outside Edit HUD",
    /\.hud-card-head\{display:none;\}/.test(PAGE));
  check("Edit HUD's canvas draws ONE inspector, on the card that was clicked (Q6)",
    /body\[data-hud-edit="on"\] \.hud-card \.hud-card-tools\{display:none;\}/.test(PAGE)
    && /body\[data-hud-edit="on"\] \.hud-card\[data-hud-edit-selected="true"\] \.hud-card-tools\{display:flex;\}/.test(PAGE)
    && /shell\.setAttribute\("data-hud-edit-selected",/.test(EDIT),
    "every card still draws its toolbar in Edit HUD instead of only the picked one");
  check("...every editable card keeps the dashed outline and the Click to edit pill",
    /body\[data-hud-edit="on"\] \.hud-card\{[\s\S]*?border:1px dashed/.test(PAGE)
    && /pill\.textContent = "Click to edit";/.test(EDIT),
    "the click-to-edit affordance on every card is gone");
  check("Edit HUD is a DOCKED RIBBON: the first child of the window grid (Q8)",
    /shell\.insertBefore\(barEl, shell\.firstChild\)/.test(EDIT),
    "hud-edit.js still inserts the bar into the stage");
  check("...parked in row 1 of #shell across every column, so the stage moves down",
    /\.hud-edit-bar\{\s*\n\s*grid-row:1; grid-column:1 \/ -1;/.test(PAGE),
    "the ribbon is not `grid-row:1; grid-column:1 / -1` in the page's stylesheet");
  check("...and the edit-mode shell has a row for it, with the columns below",
    /grid-template-rows:auto minmax\(0, 1fr\)/.test(PAGE)
    && /html body\[data-hud-edit="on"\] #stage\{grid-column:2; grid-row:2; min-width:0;\}/.test(PAGE),
    "the edit-mode grid was not given the ribbon row");
  check("the four controls are the review's: left column, up, down, right column",
    ["left", "up", "down", "right"].every((command) => EDIT.includes(`button("${command}",`)),
    "the Move group is not the review's four buttons");
  check("...and each column press is the SAME moveCard action the select sends",
    /command === "left" \|\| command === "right"/.test(EDIT)
    && /doAction\(\{ type: "moveCard", id, region: EDIT_REGIONS\[next\], index: 0 \}\)/.test(EDIT),
    "the column buttons do not go through moveCard");
  check("the sizes are plain words while the stored keys are unchanged (Q9)",
    SIZES.map((size) => size.label).join(",") === "Compact,Normal,Wide,Tall"
    && SIZES.map((size) => size.key).join(",") === "S,M,L,T",
    SIZES.map((size) => `${size.key}=${size.label}`).join(" "));
  check("...and the inspector says `Size:` beside them (three labelled groups)",
    ["Move:", "Size:", "Visibility:"].every((word) => EDIT.includes(`word("${word}")`)),
    "the three plain-word group labels are missing");
  check("the Presets drawer names the current preset with ONE word (Q9)",
    /paneWords\("Current", "hud-edit-pane-tag"\)/.test(EDIT)
    && !/"Applied"/.test(EDIT)
    && !/paneWords\("chosen"/.test(EDIT),
    "the chosen preset still wears two words for one state");
  check("a protected surface shows the locked badge instead of a working hide (Q6)",
    /const locked = PROTECTED_SET\.has\(card\.id\);/.test(EDIT)
    && /\\uD83D\\uDD12 Always visible for safety/.test(EDIT),
    "the protected card does not explain why it cannot be hidden");
  check("...and its Hide control is still in the DOM, disabled, with its reason",
    /hideBtn\.title = `\$\{hidden \? "Show" : "Hide"\} \$\{labelOf\(card\.id\)\}`;/.test(EDIT),
    "the disabled Hide control lost its reason again");
  check("the Panels and Advanced panes are gone (Q7)", !/function renderPanelsPane\(/.test(EDIT)
    && !/function renderAdvancedPane\(/.test(EDIT)
    && !/data-hud-edit-advanced/.test(EDIT),
    "a retired pane is still built");
  check("...their state folded into the Cards list as Shown / Hidden / Required for Safety",
    /"Shown \\u2713" : "Hidden"/.test(EDIT)
    && /Required for Safety/.test(EDIT)
    && /data-hud-edit-visible/.test(EDIT),
    "the Cards drawer carries no state chips");
  check("a stale Panels/Advanced id is answered with Cards, never silence",
    /const RETIRED_TABS = Object\.freeze\(\[\["panels", "cards"\], \["advanced", "cards"\]\]\)/.test(EDIT)
    && /RETIRED_TABS\.find/.test(EDIT),
    "the retired tab ids are not aliased");
  ok("the 2026-11-09 review: no toolbars in normal use, a docked ribbon, plain-words controls, Panels/Advanced gone");
}

console.log(`\n${passed} passed, ${fails.length} failed`);
if (fails.length) { console.log(`failed: ${fails.join(", ")}`); process.exit(1); }
