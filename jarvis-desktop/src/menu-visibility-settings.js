/**
 * menu-visibility-settings.js - renders the "Show or hide menus" card in
 * Settings, handles card hiding and collapsing, jump-link filtering, and
 * deep-link visit banners (docs/MENU-VISIBILITY-DESIGN.md).
 */

import {
  createMenuManager,
  WORDS,
  GROUPS,
  MENUS,
  members,
  isGroupId,
  titleOf,
  menu,
  known,
  has,
} from "./menu-visibility.js";

const $ = (id) => document.getElementById(id);

export const menuManager = createMenuManager();

function createSwitchRow(title, about, checked, onChange, indent = 0) {
  const row = document.createElement("div");
  row.className = "menu-switch-row";
  if (indent) row.style.paddingLeft = `${indent}px`;

  const textCol = document.createElement("div");
  textCol.className = "menu-switch-text";

  const label = document.createElement("label");
  label.className = "menu-switch-label";

  const input = document.createElement("input");
  input.type = "checkbox";
  input.role = "switch";
  input.checked = checked;
  input.setAttribute("aria-checked", String(checked));
  input.addEventListener("change", () => {
    input.setAttribute("aria-checked", String(input.checked));
    onChange(input.checked);
  });

  const span = document.createElement("span");
  span.className = "menu-switch-title";
  span.textContent = title;

  label.appendChild(input);
  label.appendChild(span);
  textCol.appendChild(label);

  if (about) {
    const desc = document.createElement("p");
    desc.className = "note menu-switch-desc";
    desc.textContent = about;
    textCol.appendChild(desc);
  }

  row.appendChild(textCol);
  return row;
}

export function renderMenuList() {
  const container = $("menu-visibility-list");
  if (!container) return;
  container.innerHTML = "";

  const state = menuManager.getState();
  const count = menuManager.hiddenCount();

  // Hidden count line
  const countLine = document.createElement("p");
  countLine.className = "note menu-count-line";
  countLine.setAttribute("aria-live", "polite");
  countLine.textContent =
    count === 0
      ? WORDS.none_hidden
      : count === 1
      ? WORDS.hidden_speech_one
      : WORDS.hidden_speech_many.replace("{n}", count);
  container.appendChild(countLine);

  // 1. Feature groups
  for (const group of GROUPS) {
    const mems = members(group.id, "desktop");
    if (mems.length === 0) continue;

    const groupFieldset = document.createElement("fieldset");
    groupFieldset.className = "menu-visibility-group";

    const legend = document.createElement("legend");
    legend.textContent = group.title;
    groupFieldset.appendChild(legend);

    const groupShown =
      !state.hidden.has(group.id) && mems.some((id) => !menuManager.isHidden(id));
    const groupAbout = WORDS.group_hides.replace(
      "{members}",
      mems.map((id) => menu(id)?.title).filter(Boolean).join(", ")
    );

    const groupRow = createSwitchRow(group.title, groupAbout, groupShown, (on) => {
      if (on) menuManager.show(group.id);
      else menuManager.hide(group.id);
      applyVisibility();
      renderMenuList();
    });
    groupFieldset.appendChild(groupRow);

    for (const memId of mems) {
      const m = menu(memId);
      if (!m) continue;
      const memRow = createSwitchRow(
        m.title,
        m.about,
        !menuManager.isHidden(memId),
        (on) => {
          if (on) menuManager.show(memId);
          else menuManager.hide(memId);
          applyVisibility();
          renderMenuList();
        },
        m.parent && mems.includes(m.parent) ? 24 : 12
      );
      groupFieldset.appendChild(memRow);
    }

    container.appendChild(groupFieldset);
  }

  // 2. Standalone Settings cards
  const settingsRows = MENUS.filter(
    (m) => has(m, "desktop") && m.hide && m.area === "settings" && !m.group
  );
  if (settingsRows.length > 0) {
    const fs = document.createElement("fieldset");
    fs.className = "menu-visibility-group";
    const legend = document.createElement("legend");
    legend.textContent = "Settings";
    fs.appendChild(legend);

    for (const m of settingsRows) {
      const row = createSwitchRow(
        m.title,
        m.about,
        !menuManager.isHidden(m.id),
        (on) => {
          if (on) menuManager.show(m.id);
          else menuManager.hide(m.id);
          applyVisibility();
          renderMenuList();
        }
      );
      fs.appendChild(row);
    }
    container.appendChild(fs);
  }

  // 3. Standalone Brain items
  const brainRows = MENUS.filter(
    (m) => has(m, "desktop") && m.hide && m.area === "brain" && !m.group
  );
  if (brainRows.length > 0) {
    const fs = document.createElement("fieldset");
    fs.className = "menu-visibility-group";
    const legend = document.createElement("legend");
    legend.textContent = "Brain";
    fs.appendChild(legend);

    for (const m of brainRows) {
      const row = createSwitchRow(
        m.title,
        m.about,
        !menuManager.isHidden(m.id),
        (on) => {
          if (on) menuManager.show(m.id);
          else menuManager.hide(m.id);
          applyVisibility();
          renderMenuList();
        }
      );
      fs.appendChild(row);
    }
    container.appendChild(fs);
  }
}

export function applyVisibility() {
  const cards = document.querySelectorAll("section.card");
  for (const card of cards) {
    const mid = card.dataset.menuId || (card.id ? `settings.${card.id}` : null);
    if (!mid || !known(mid, "desktop")) continue;

    const hidden = menuManager.isHidden(mid);
    card.hidden = hidden;

    const m = menu(mid);
    if (m && m.collapse) {
      if (menuManager.isCollapsed(mid)) {
        card.classList.add("card-collapsed");
      } else {
        card.classList.remove("card-collapsed");
      }
      updateCollapseButton(card, mid);
    }
  }

  // Filter jump links
  const jumpLinks = document.querySelectorAll("#settings-jump a[href^='#']");
  for (const a of jumpLinks) {
    const targetId = a.getAttribute("href").slice(1);
    const mid = `settings.${targetId}`;
    if (known(mid, "desktop")) {
      a.hidden = menuManager.isHidden(mid);
    }
  }

  // Update "N hidden - Show" bar
  const count = menuManager.hiddenCount();
  const bar = $("menus-hidden-bar");
  const btn = $("btn-show-hidden-menus");
  if (bar && btn) {
    if (count > 0) {
      bar.hidden = false;
      btn.textContent =
        count === 1 ? WORDS.hidden_line_one : WORDS.hidden_line_many.replace("{n}", count);
    } else {
      bar.hidden = true;
    }
  }
}

function updateCollapseButton(card, mid) {
  let btn = card.querySelector(".card-collapse-toggle");
  if (!btn) {
    const h2 = card.querySelector("h2");
    if (!h2) return;
    btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn ghost btn-sm card-collapse-toggle";
    h2.after(btn);
  }
  const isCol = menuManager.isCollapsed(mid);
  btn.textContent = isCol ? WORDS.expand : WORDS.collapse;
  btn.setAttribute("aria-expanded", String(!isCol));
  btn.onclick = () => {
    if (isCol) menuManager.expand(mid);
    else menuManager.collapse(mid);
    applyVisibility();
  };
}

export function showForVisit(menuId, cardElement) {
  menuManager.showForVisit(menuId);
  applyVisibility();

  if (cardElement && !cardElement.querySelector(".menu-visit-banner")) {
    const banner = document.createElement("div");
    banner.className = "menu-visit-banner";
    banner.setAttribute("role", "status");
    banner.setAttribute("aria-live", "polite");

    const text = document.createElement("span");
    text.textContent = WORDS.visit_banner;
    banner.appendChild(text);

    const btnRow = document.createElement("div");
    btnRow.className = "row";
    btnRow.style.gap = "8px";

    const keepBtn = document.createElement("button");
    keepBtn.type = "button";
    keepBtn.className = "btn ghost btn-sm";
    keepBtn.textContent = WORDS.visit_keep;
    keepBtn.onclick = () => {
      menuManager.show(menuId);
      menuManager.clearVisit(menuId);
      banner.remove();
      applyVisibility();
      renderMenuList();
    };

    const hideBtn = document.createElement("button");
    hideBtn.type = "button";
    hideBtn.className = "btn ghost btn-sm";
    hideBtn.textContent = WORDS.visit_again;
    hideBtn.onclick = () => {
      menuManager.clearVisit(menuId);
      banner.remove();
      applyVisibility();
      renderMenuList();
    };

    btnRow.appendChild(keepBtn);
    btnRow.appendChild(hideBtn);
    banner.appendChild(btnRow);

    const h2 = cardElement.querySelector("h2");
    if (h2) h2.before(banner);
    else cardElement.prepend(banner);
  }
}

// Initialise
function init() {
  applyVisibility();
  renderMenuList();

  $("btn-show-hidden-menus")?.addEventListener("click", () => {
    const card = $("menu-visibility");
    if (card) {
      card.scrollIntoView({ block: "start" });
      card.focus();
    }
  });

  $("menu-visibility-reset")?.addEventListener("click", () => {
    menuManager.reset();
    applyVisibility();
    renderMenuList();
  });

  window.addEventListener("storage", (e) => {
    if (e.key && e.key.startsWith("jarvis.menus.")) {
      menuManager.reload();
      applyVisibility();
      renderMenuList();
    }
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
