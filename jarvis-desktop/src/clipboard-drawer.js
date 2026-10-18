/**
 * Clipboard history drawer (Pillar 14B) — the Quickbar half.
 *
 * WHAT THIS DRAWS, AND WHAT IT NEVER DOES
 *
 * The owner copies things all day: a link to clean up, a small table to turn
 * into Markdown, a JSON blob to read. This drawer offers exactly three
 * deterministic transforms over a kept copy — a Markdown table, pretty JSON,
 * and a link with its tracking parameters removed — and the switch that decides
 * whether anything is kept at all.
 *
 * The ring itself lives in Rust (`src-tauri/src/clipboard_time_machine.rs`),
 * in memory, and only while the owner has turned it on. This module is a thin
 * view over six Tauri commands:
 *
 *   clipboard_tm_state      the switch, the copies newest first, the bounds
 *   clipboard_tm_enable     the owner's explicit press is the permission
 *   clipboard_tm_disable    stop keeping new copies; the old ones stay
 *   clipboard_tm_clear      forget every kept copy, leave the switch as it was
 *   clipboard_tm_lock       forget everything AND stop capturing (what a lock does)
 *   clipboard_tm_transform  one copy (by its place in the list) through one kind
 *
 * Deliberately absent: any request, any network call, any storage, any log of a
 * copied word. The only things this file writes are the page's own text nodes.
 * The copied words are cleared from the DOM the moment the drawer closes or
 * the window loses focus, so a hidden bar does not keep them lying on screen;
 * Rust wipes the ring itself when App lock or Windows' lock screen comes up.
 *
 * The whole file also runs outside Tauri (a plain browser tab) for styling:
 * with no bridge the drawer says so and does nothing.
 */

/** The three transforms, exactly the Rust module's `TRANSFORMS`. */
export const TRANSFORMS = [
  {
    kind: "markdown_table",
    label: "Table",
    title: "Turn a CSV or TSV table into a Markdown table",
  },
  {
    kind: "pretty_json",
    label: "Pretty JSON",
    title: "Indent a JSON blob so it can be read",
  },
  {
    kind: "strip_tracking_params",
    label: "Clean link",
    title: "Remove utm_* and the other click-tracking parameters from a link",
  },
];

/**
 * Every sentence this drawer says. Plain words, no jargon: the owner is a
 * beginner and this is the one surface that can show a private copy.
 */
export const WORDS = {
  title: "Clipboard history",
  close: "Close",
  off: "Off",
  on: "On",
  lockedStatus: "Locked",
  offLine:
    "Off. Nothing you copy is being kept. Turning this on keeps what you copy from now on — in this window's memory only, never on disk — until you turn it off, forget everything, or Jarvis locks.",
  onLine:
    "On. Copies from now on are kept in this window's memory only. Nothing is written to disk, and the lot is forgotten when Jarvis locks.",
  empty: "Nothing kept yet. Copy something after turning it on, and it will appear here.",
  locked:
    "Jarvis is locked. It forgot every kept copy when the lock began; unlock it and open clipboard history again.",
  unreadable: "The clipboard history is not available in this window.",
  turnOn: "Turn on",
  turnOff: "Turn off",
  forget: "Forget everything",
  lock: "Forget and turn off",
  privacy:
    "Password managers, one-time codes, private keys, card numbers and empty copies are never kept. Nothing here leaves this PC.",
  keys: "Tab moves · Esc closes",
  copyResult: "Copy the result",
  resultCopied: "Copied",
  copyFailed: "The clipboard would not take that copy.",
  transformUnavailable: "That copy could not be transformed.",
  staleCopy: "That copy is no longer in the list.",
  noBridge: "Clipboard history needs the Jarvis desktop app.",
};

/** Collapse one copied text into a single short preview line. */
export function previewText(text, limit = 140) {
  const flat = String(text == null ? "" : text)
    .replace(/\s+/g, " ")
    .trim();
  const characters = [...flat];
  if (characters.length <= limit) return flat;
  return characters.slice(0, limit - 1).join("") + "…";
}

/** The window a copy came from, as one line, or "". */
export function fromLine(item) {
  if (!item || typeof item !== "object") return "";
  const app = String(item.app || "").trim();
  const title = String(item.title || "").trim();
  if (app && title) return `${app} · ${title}`;
  return app || title;
}

/** A row for one kept copy: its preview, where it came from, and its index. */
export function rowFor(item, index) {
  return {
    index,
    preview: previewText(item && item.text),
    from: fromLine(item),
  };
}

/**
 * The drawer's whole screen, worked out from Rust's answer.
 *
 * Fails closed: while locked, or with no readable state at all, no row is
 * drawn — a page that outlived the lock cannot show a copy that the ring has
 * already forgotten.
 */
export function view(state) {
  const readable = Boolean(state && typeof state === "object");
  const locked = readable && Boolean(state.locked);
  const enabled = readable && Boolean(state.enabled);
  const items = readable && Array.isArray(state.items) ? state.items : [];
  const rows = locked ? [] : items.map((item, index) => rowFor(item, index));
  return {
    readable,
    locked,
    enabled,
    rows,
    status: locked ? WORDS.lockedStatus : enabled ? WORDS.on : WORDS.off,
    line: !readable
      ? WORDS.unreadable
      : locked
        ? WORDS.locked
        : enabled
          ? rows.length
            ? WORDS.onLine
            : WORDS.empty
          : WORDS.offLine,
    canEnable: readable && !locked && !enabled,
    canDisable: readable && !locked && enabled,
    canForget: readable && rows.length > 0,
    canLock: readable && !locked && (enabled || rows.length > 0),
  };
}

/** The label for a transform kind, or the kind itself when it is unknown. */
export function kindLabel(kind) {
  const found = TRANSFORMS.find((entry) => entry.kind === kind);
  return found ? found.label : String(kind || "");
}

/**
 * What to say about one transform's answer, and whether it can be copied.
 *
 * `result` is the Rust command's `{ok, kind, text, reason}`. A refusal is the
 * Rust reason verbatim (plain words already, e.g. "a table needs at least 2
 * rows"); nothing is ever half-transformed, so `canCopy` is only true on ok.
 */
export function transformWords(result) {
  if (!result || typeof result !== "object") {
    return { line: WORDS.transformUnavailable, canCopy: false, text: "" };
  }
  if (!result.ok) {
    return {
      line: String(result.reason || WORDS.transformUnavailable),
      canCopy: false,
      text: "",
    };
  }
  return { line: "", canCopy: true, text: String(result.text || "") };
}

/* ==========================================================================
   The live drawer (only used inside the app; the functions above are pure)
   ========================================================================== */

/**
 * Mounts the drawer on the Quickbar page.
 *
 * `invoke` is main.js's guarded bridge call (resolves `null` when there is no
 * Tauri backend); `listen` is its guarded event subscription. Everything this
 * function adds to the page is text: a copied word never goes near innerHTML.
 */
export function mountClipboardDrawer({ dom, invoke, listen, onOpen, onClose }) {
  if (!dom || !dom.section) return null;

  let open = false;
  let resultShown = null;
  let busy = false;

  const shell = dom.shell || null;

  function clearResult() {
    resultShown = null;
    if (dom.result) dom.result.hidden = true;
    if (dom.resultText) dom.resultText.textContent = "";
    if (dom.resultKind) dom.resultKind.textContent = "";
    if (dom.resultCopy) dom.resultCopy.hidden = true;
  }

  /** Hides the drawer and throws away every copied word it was holding. */
  function close() {
    if (!open) return;
    open = false;
    dom.section.hidden = true;
    if (dom.list) dom.list.replaceChildren();
    clearResult();
    if (shell) delete shell.dataset.clipboard;
    if (typeof onClose === "function") onClose();
  }

  /** Draw one state from Rust. Copies are shown as previews, never as HTML. */
  function render(state, failure) {
    const shown = view(failure ? null : state);
    dom.section.hidden = false;
    open = true;
    dom.section.dataset.state = shown.locked ? "locked" : shown.enabled ? "on" : "off";
    if (shell) shell.dataset.clipboard = "open";
    if (dom.status) dom.status.textContent = shown.status;
    if (dom.line) dom.line.textContent = shown.line;
    if (dom.privacy) dom.privacy.textContent = WORDS.privacy;
    if (dom.keys) dom.keys.textContent = WORDS.keys;
    if (dom.enable) {
      dom.enable.hidden = !shown.canEnable;
      dom.enable.textContent = WORDS.turnOn;
    }
    if (dom.disable) {
      dom.disable.hidden = !shown.canDisable;
      dom.disable.textContent = WORDS.turnOff;
    }
    if (dom.forget) {
      dom.forget.hidden = !shown.canForget;
      dom.forget.textContent = WORDS.forget;
    }
    if (dom.lock) {
      dom.lock.hidden = !shown.canLock;
      dom.lock.textContent = WORDS.lock;
    }
    drawRows(shown.rows);
    // The drawer changed the page's height; the bar sizes itself from what is
    // on it (main.js syncWindowHeight), so tell it before the next frame.
    if (typeof onOpen === "function") onOpen();
  }

  function drawRows(rows) {
    if (!dom.list) return;
    const nodes = rows.map((row) => {
      const item = document.createElement("li");
      item.className = "clipboard-row";

      const head = document.createElement("div");
      head.className = "clipboard-row-head";
      const preview = document.createElement("span");
      preview.className = "clipboard-row-preview";
      preview.textContent = row.preview;
      head.append(preview);
      if (row.from) {
        const from = document.createElement("span");
        from.className = "clipboard-row-from";
        from.textContent = row.from;
        head.append(from);
      }
      item.append(head);

      const buttons = document.createElement("div");
      buttons.className = "clipboard-row-actions";
      for (const step of TRANSFORMS) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "text-button clipboard-transform";
        button.dataset.kind = step.kind;
        button.title = step.title;
        button.textContent = step.label;
        button.addEventListener("click", () => runTransform(row.index, step.kind));
        buttons.append(button);
      }
      item.append(buttons);
      return item;
    });
    dom.list.replaceChildren(...nodes);
  }

  async function refresh() {
    const state = await invoke("clipboard_tm_state");
    render(state, state === null);
    if (dom.close && !dom.section.hidden) dom.close.focus();
  }

  async function runTransform(index, kind) {
    if (busy) return;
    busy = true;
    try {
      const answer = await invoke("clipboard_tm_transform", { index, kind });
      if (answer === null && open) {
        showResult({
          line: WORDS.transformUnavailable,
          canCopy: false,
          text: "",
        }, kind);
        return;
      }
      showResult(transformWords(answer), kind);
    } finally {
      busy = false;
    }
  }

  function showResult(shown, kind) {
    if (!dom.result) return;
    resultShown = shown;
    dom.result.hidden = false;
    if (dom.resultKind) {
      dom.resultKind.textContent = kindLabel(kind) + (shown.canCopy ? "" : " — not changed");
    }
    if (dom.resultLine) dom.resultLine.textContent = shown.line;
    if (dom.resultText) dom.resultText.textContent = shown.text;
    if (dom.resultCopy) {
      dom.resultCopy.hidden = !shown.canCopy;
      dom.resultCopy.textContent = WORDS.copyResult;
    }
    if (typeof onOpen === "function") onOpen();
  }

  async function copyResult() {
    if (!resultShown || !resultShown.canCopy) return;
    // "Private copy" first, exactly as the answer card's Copy button does: a
    // transformed table or a cleaned link must not be added to Windows
    // Clipboard History by the act of taking it out of this drawer.
    const privateCopy = await invoke("write_clipboard_private", {
      text: resultShown.text,
    });
    if (privateCopy === null) await invoke("write_clipboard", { text: resultShown.text });
    if (dom.resultCopy) {
      dom.resultCopy.textContent = WORDS.resultCopied;
      setTimeout(() => {
        if (dom.resultCopy) dom.resultCopy.textContent = WORDS.copyResult;
      }, 1200);
    }
  }

  function wire(button, action) {
    if (button) button.addEventListener("click", action);
  }

  wire(dom.close, close);
  wire(dom.closeResult, () => clearResult());
  wire(dom.resultCopy, copyResult);
  wire(dom.enable, async () => render(await invoke("clipboard_tm_enable"), false));
  wire(dom.disable, async () => render(await invoke("clipboard_tm_disable"), false));
  wire(dom.forget, async () => {
    clearResult();
    render(await invoke("clipboard_tm_clear"), false);
  });
  wire(dom.lock, async () => {
    clearResult();
    render(await invoke("clipboard_tm_lock"), false);
  });

  // The hotkey: Rust opens the bar and says so; this reads the ring and draws.
  listen("clipboard-tm-open", () => {
    refresh();
  });
  // A kept copy, or the lock's wipe. Nothing about the copied words is in the
  // event; the drawer re-reads through the command, which fails closed.
  listen("clipboard-tm-changed", () => {
    if (open) refresh();
  });

  // Esc closes the drawer and goes no further: the bar's own Esc (dismiss,
  // park the approval, stop the stream) must not run on the same press.
  // Capture phase, like palette-ui.js, so this wins over the document handler.
  document.addEventListener(
    "keydown",
    (event) => {
      if (!open) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        close();
        return;
      }
      if (event.key === "Tab") {
        const focusable = [...dom.section.querySelectorAll("button:not([hidden])")];
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    },
    true,
  );

  // The bar hides itself when it loses focus (the spotlight's own rule). The
  // copied words must not stay lying in a hidden page: close and clear.
  window.addEventListener("blur", close);

  return { open: refresh, close, isOpen: () => open };
}
