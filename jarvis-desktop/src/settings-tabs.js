/**
 * Tabs for a Settings card that holds one service per row.
 *
 * WHY THIS EXISTS (the owner, 2026-10-11): *"the menus that are similar to
 * chatbot api keys need to be compressed into a tab version in the specific
 * menu, with each tab being a header and being a main topic (in this case a tab
 * for chatgpt, a tab for deepseek, etc) and opening the tabs gives their
 * specific menu."* Six services was a long scroll; he wants to open the one he
 * means.
 *
 * EVERY TAB IS A REAL BUTTON, so Tab reaches it - the app's own habit
 * (`src/index.html`: "A button, so Tab reaches it."). Arrow keys move between
 * tabs, Home and End jump to the ends, and only the open tab's panel is shown.
 * A tab strip that only answered the mouse would be a regression on a page full
 * of switches.
 *
 * NO PANEL IS EVER REMOVED, only hidden. `tests/settings-failures.mjs` exists
 * because four controls once failed in silence, and a control that cannot reach
 * the PC must always be able to say so: a failure raised from a panel is on
 * screen when it happens (the panel had to be open for the control to be
 * pressed), and each card's own status line stays OUTSIDE the strip. On top of
 * that, `markFailing` marks the tab that holds a failure AND opens it, so a
 * failure can never sit behind a closed tab.
 */
(function () {
  "use strict";

  /**
   * Build a strip inside `mount`.
   *
   *   items    - whatever the card's own rows are built from
   *   idOf     - a unique id per item (the tab and panel ids are built from it)
   *   labelOf  - the tab's words (the app's own name for the service)
   *   panelOf  - the nodes that item's panel holds
   *   label    - the strip's own name, read out by a screen reader
   *
   * Returns { select, markFailing, buttons }, or null when there is nothing to
   * build (an empty list keeps the card exactly as it was).
   */
  function build({ mount, items, idOf, labelOf, panelOf, label = "" }) {
    if (!mount || !items || !items.length) return null;

    const strip = document.createElement("div");
    strip.className = "tabstrip";
    strip.setAttribute("role", "tablist");
    if (label) strip.setAttribute("aria-label", label);

    const panelBox = document.createElement("div");
    panelBox.className = "tabpanels";

    const buttons = [];
    const panels = [];

    const select = (index, { focus = false } = {}) => {
      const at = Math.max(0, Math.min(index, buttons.length - 1));
      buttons.forEach((button, i) => {
        const on = i === at;
        button.setAttribute("aria-selected", on ? "true" : "false");
        button.tabIndex = on ? 0 : -1;
        button.classList.toggle("tab-open", on);
        panels[i].hidden = !on;
      });
      if (focus && buttons[at]) buttons[at].focus();
    };

    items.forEach((item, index) => {
      const id = idOf(item);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "tab";
      button.id = `tab-${id}`;
      button.setAttribute("role", "tab");
      button.setAttribute("aria-controls", `panel-${id}`);
      button.setAttribute("aria-selected", index === 0 ? "true" : "false");
      button.tabIndex = index === 0 ? 0 : -1;
      button.append(document.createTextNode(labelOf(item)));
      button.addEventListener("click", () => select(index));
      button.addEventListener("keydown", (event) => {
        const last = buttons.length - 1;
        if (event.key === "ArrowRight") select(index === last ? 0 : index + 1, { focus: true });
        else if (event.key === "ArrowLeft") select(index === 0 ? last : index - 1, { focus: true });
        else if (event.key === "Home") select(0, { focus: true });
        else if (event.key === "End") select(last, { focus: true });
        else return;
        event.preventDefault();
      });

      const panel = document.createElement("div");
      panel.className = "tabpanel";
      panel.id = `panel-${id}`;
      panel.setAttribute("role", "tabpanel");
      panel.setAttribute("aria-labelledby", `tab-${id}`);
      panel.hidden = index !== 0;
      panel.append(...panelOf(item));

      buttons.push(button);
      panels.push(panel);
      strip.append(button);
      panelBox.append(panel);
    });

    mount.replaceChildren(strip, panelBox);
    select(0);

    return { select, buttons };
  }

  window.JarvisSettingsTabs = { build };
})();
