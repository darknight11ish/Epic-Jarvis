/**
 * The update's own progress window (update-window.html; update_window.rs;
 * DEF-098, the owner's request of 2026-11-24: "when i update jarvis there
 * should be a pop up with a progress bar").
 *
 * It listens to the updater's own events and draws ONE line and a bar:
 *
 *   backend-update-progress  the Python tool's progress (`update_progress.rs`)
 *   update-progress          the desktop package's bytes (`update.rs`)
 *   update-step              each half starting/ending, with the tool's words
 *   update-window-note       started / installer next / how the run ended
 *
 * It never invokes a command, never starts, resumes or approves anything, and
 * never moves the bar itself: `viewFor` returns `bar: null` until a real
 * number has arrived, and the bar's width is recomputed only when an event
 * arrives. Closing the window does not stop the run (the page says so in
 * words); the installer phase cannot be drawn here at all, because on Windows
 * the installer ends this process - so the window says what is about to
 * happen instead of pretending to watch it.
 *
 * `viewFor` is pure and self-contained on purpose: `tests/update-window.mjs`
 * extracts it and drives it with the real payload shapes, the same way other
 * page tests pin a drawing function.
 */
const TAURI = globalThis.__TAURI__;
const THEMES = ["deep-space", "paper", "high-contrast"];

const el = {
  root: document.getElementById("uw"),
  headline: document.getElementById("uw-headline"),
  detail: document.getElementById("uw-detail"),
  track: document.getElementById("uw-track"),
  fill: document.getElementById("uw-fill"),
  count: document.getElementById("uw-count"),
  eta: document.getElementById("uw-eta"),
  failedTitle: document.getElementById("uw-failed-title"),
  failed: document.getElementById("uw-failed"),
};

/** A fresh run: what the window says in the moment before its first event. */
function freshState() {
  return {
    startLine: "",
    source: null,
    backend: null,
    download: null,
    steps: { backend: null, desktop: null },
    installing: false,
    installingLine: "",
    ended: null,
  };
}

let state = freshState();

/**
 * What the window should say about `state`. Pure; no DOM, no clock, no event.
 *
 * The order is the order of the run: an ending wins over everything, a half
 * that failed or did not run wins over a bar that would otherwise keep moving,
 * the installer note wins over the download that preceded it, and only then
 * are the two real sources drawn - the desktop package's bytes, or the backend
 * tool's own fraction/counts.
 */
function viewFor(state) {
  const s = state || {};
  const backend = s.backend || null;
  const download = s.download || null;
  const steps = s.steps || {};
  const ended = s.ended || null;
  const failedChecks = [];
  if (backend && Array.isArray(backend.bad)) {
    for (const check of backend.bad) {
      if (!check || typeof check.name !== "string" || !check.name) continue;
      failedChecks.push(check.reason ? check.name + " - " + check.reason : check.name);
    }
  }

  function durationWords(seconds) {
    const value = Math.max(0, Math.round(Number(seconds) || 0));
    if (value < 90) return value + (value === 1 ? " second" : " seconds");
    const minutes = Math.max(1, Math.round(value / 60));
    return minutes + (minutes === 1 ? " minute" : " minutes");
  }

  function etaWords() {
    if (!backend || backend.phase === "done") return "";
    const low = backend.etaLowSeconds;
    const high = backend.etaHighSeconds;
    const hasLow = Number.isFinite(low);
    const hasHigh = Number.isFinite(high);
    if (!hasLow && !hasHigh) return "";
    const span = hasLow && hasHigh && Math.round(low) !== Math.round(high)
      ? durationWords(low) + " to " + durationWords(high)
      : durationWords(hasLow ? low : high);
    const source = backend.measured === true
      ? "from this PC's own times"
      : backend.measured === false ? "not measured for this pace yet" : "";
    return "about " + span + (source ? " · " + source : "") + " left";
  }

  function verdictWords() {
    if (!backend) return "The backend half is done";
    if (backend.verdict === "problems") return "The backend half finished with problems";
    if (backend.verdict === "unproven") return "The backend half patched, but its checks did not prove it";
    return "The backend half is done";
  }

  function phaseWords() {
    if (!backend || typeof backend.phase !== "string") return "";
    switch (backend.phase) {
      case "reading": return "Working out what to update…";
      case "plan": return "Ready to start";
      case "rehearsing":
      case "applying":
      case "patching": return "Patching the backend";
      case "verifying": return "Checking the patched files";
      case "testing": return "Checking the backend";
      case "fallback": return "Quick check hit a problem - re-running the safe way";
      case "done": return verdictWords();
      default: return "";
    }
  }

  function backendCount() {
    if (!backend || typeof backend.phase !== "string") return "";
    const done = Number.isInteger(backend.done) ? backend.done : 0;
    const failed = Number.isInteger(backend.failed) ? backend.failed : 0;
    if (backend.phase === "rehearsing" || backend.phase === "applying" || backend.phase === "patching") {
      return Number.isInteger(backend.total)
        ? done + " of " + backend.total + " items"
        : done + " items done";
    }
    if (backend.phase === "testing") {
      const count = Number.isInteger(backend.total)
        ? done + " of " + backend.total + " checks"
        : done + " checks done";
      return failed ? count + ", " + failed + " failed" : count;
    }
    return "";
  }

  function bytesWords(value) {
    const bytes = Math.max(0, Number(value) || 0);
    if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + " MB";
    if (bytes >= 1024) return Math.round(bytes / 1024) + " KB";
    return Math.round(bytes) + " bytes";
  }

  function plain(headline, detail, tone) {
    return {
      tone: tone || "working",
      headline: headline,
      detail: detail,
      bar: null,
      count: "",
      eta: "",
      failed: failedChecks,
      measured: false,
    };
  }

  /* 1. An ending this process can see. The ending that ends the process never
   *    reaches here, which is exactly why the next launch reconciles the
   *    record instead. */
  if (ended) {
    return {
      tone: ended.bad ? "bad" : "ok",
      headline: ended.bad ? "The update did not finish" : "The update finished",
      detail: typeof ended.line === "string" ? ended.line : "",
      bar: null,
      count: "",
      eta: "",
      failed: failedChecks,
      measured: false,
    };
  }

  /* 2. A half that failed or was skipped: the tool's own sentence, and no bar. */
  let failedStep = null;
  if (steps.desktop && steps.desktop.state !== "ok" && steps.desktop.state !== "running") {
    failedStep = steps.desktop;
  } else if (steps.backend && steps.backend.state !== "ok" && steps.backend.state !== "running") {
    failedStep = steps.backend;
  }
  if (failedStep) {
    const isDesktop = failedStep === steps.desktop;
    const headline = failedStep.state === "partial"
      ? "The backend half patched, but its checks did not prove it"
      : isDesktop ? "Atlas Desktop was not installed" : "The backend half did not finish";
    return plain(
      headline,
      typeof failedStep.detail === "string" ? failedStep.detail : "",
      "bad"
    );
  }

  /* 3. The installer is about to take over. The bar stops here on purpose: the
   *    installer does not report progress to Atlas, and on Windows it ends the
   *    process that owns this page. */
  if (s.installing) {
    return plain(
      "The installer is starting now",
      typeof s.installingLine === "string" && s.installingLine
        ? s.installingLine
        : "Atlas closes and starts again by itself. The next start says whether the " +
          "desktop half finished. The installer does not report its own progress, so " +
          "the bar stops here instead of pretending to move."
    );
  }

  /* 4. The desktop package's bytes, and only those bytes. */
  if (s.source === "desktop" && download) {
    const total = Number.isFinite(download.total) ? download.total : null;
    const downloaded = Number.isFinite(download.downloaded) ? download.downloaded : 0;
    const finished = total !== null && total > 0 && downloaded >= total;
    return {
      tone: "working",
      headline: finished
        ? "Download finished - the installer is next"
        : "Downloading Atlas Desktop",
      detail: finished
        ? "The package was checked against the signing key before anything on this PC " +
          "changed. Atlas closes and starts again when the installer runs; this window " +
          "cannot show the installer's own progress."
        : "The package is checked against the signing key before anything on this PC is changed.",
      bar: total !== null && total > 0
        ? Math.max(0, Math.min(99, (downloaded / total) * 100))
        : null,
      count: total !== null && total > 0
        ? bytesWords(downloaded) + " of " + bytesWords(total)
        : bytesWords(downloaded) + " downloaded - the server did not say the total size",
      eta: "",
      failed: failedChecks,
      measured: total !== null && total > 0,
    };
  }

  /* 5. The backend half, from the update tool's own numbers. */
  if (s.source === "backend" && backend) {
    const done = Number.isInteger(backend.done) ? backend.done : 0;
    const total = Number.isInteger(backend.total) && backend.total > 0 ? backend.total : null;
    const hasFraction = Number.isFinite(backend.fraction);
    const measured = hasFraction || total !== null || done > 0 || backend.phase === "done";
    if (!measured) {
      return plain(
        "Patching the backend",
        "Nothing has been measured yet - the bar stays empty until the update tool " +
          "reports a real number."
      );
    }
    let bar = null;
    if (hasFraction) bar = Math.max(0, Math.min(100, backend.fraction * 100));
    else if (total !== null) bar = Math.max(0, Math.min(100, (done / total) * 100));
    if (backend.phase === "done") {
      if (backend.verdict === "ok" || backend.verdict === "unproven") bar = 100;
      else if (bar !== null) bar = Math.min(99, bar);
    } else if (bar !== null) {
      bar = Math.min(99, bar);
    }
    const problems = backend.verdict === "problems";
    let detail;
    if (backend.phase === "done") {
      if (problems) {
        detail = "The update tool's own verdict is that this run did not pass. " +
          "Do not trust this update yet.";
      } else if (backend.verdict === "unproven") {
        detail = "The backend patched, but its own checks did not prove it, so this is " +
          "not a pass.";
      } else {
        detail = "The backend half is done. The desktop half starts next.";
      }
    } else {
      detail = "The bar is the update tool's own completed work - files carried, then " +
        "checks run. It never moves on a timer.";
    }
    return {
      tone: problems ? "bad" : "working",
      headline: phaseWords(),
      detail: detail,
      bar: bar,
      count: backendCount(),
      eta: etaWords(),
      failed: failedChecks,
      measured: true,
    };
  }

  /* 6. The desktop half has started but the first bytes are not in yet. */
  if (s.source === "desktop") {
    return plain(
      "Preparing the Atlas Desktop download",
      "Checking the newest release and its signature before anything is downloaded. " +
        "Nothing has been measured yet."
    );
  }

  /* 7. Opened, nothing measured yet. */
  return plain(
    "Starting the update…",
    (typeof s.startLine === "string" && s.startLine ? s.startLine + " " : "") +
      "Nothing has been measured yet - the bar stays empty until the update tool " +
      "reports a real number."
  );
}

/** Paint the one line, the bar and the tool's failing checks. */
function paint() {
  const view = viewFor(state);
  if (!el.root) return;
  el.root.dataset.tone = view.tone;
  el.headline.textContent = view.headline;
  el.detail.textContent = view.detail;
  const hasBar = Number.isFinite(view.bar);
  el.track.hidden = !hasBar;
  if (hasBar) {
    const percent = Math.max(0, Math.min(100, view.bar));
    el.fill.style.width = percent + "%";
    el.track.setAttribute("aria-valuenow", String(Math.round(percent)));
  }
  el.count.textContent = view.count;
  el.eta.textContent = view.eta;
  const failing = Array.isArray(view.failed) ? view.failed : [];
  el.failed.hidden = failing.length === 0;
  el.failedTitle.hidden = failing.length === 0;
  el.failed.replaceChildren();
  for (const line of failing) {
    const item = document.createElement("li");
    item.textContent = line;
    el.failed.append(item);
  }
}

/** Listen for one of the updater's events. A broken payload never stops the
 *  window: it is not drawn and the next event is still read. */
function on(name, handle) {
  if (!TAURI || !TAURI.event) return;
  TAURI.event.listen(name, (event) => {
    try {
      handle(event && event.payload);
    } catch (error) {
      /* the next event still paints */
    }
    paint();
  });
}

on("update-window-note", (note) => {
  if (!note || typeof note.kind !== "string") return;
  if (note.kind === "started") {
    state = freshState();
    state.startLine = typeof note.line === "string" ? note.line : "";
  } else if (note.kind === "installing") {
    state.installing = true;
    state.installingLine = typeof note.line === "string" ? note.line : "";
  } else if (note.kind === "ended") {
    state.ended = {
      bad: Boolean(note.bad),
      line: typeof note.line === "string" ? note.line : "",
    };
  }
});

on("update-step", (step) => {
  if (!step || (step.step !== "backend" && step.step !== "desktop")) return;
  state.steps[step.step] = step;
  if (step.state === "running") state.source = step.step;
  if (step.step === "desktop" && step.state !== "running" && step.state === "ok") {
    state.source = "desktop";
  }
});

on("backend-update-progress", (progress) => {
  if (!progress || typeof progress.phase !== "string") return;
  state.backend = progress;
  if (state.source !== "desktop") state.source = "backend";
});

on("update-progress", (download) => {
  if (!download || !Number.isFinite(download.downloaded)) return;
  state.download = download;
  state.source = "desktop";
});

try {
  const theme = localStorage.getItem("jarvis.theme");
  if (THEMES.indexOf(theme) >= 0) {
    document.documentElement.setAttribute("data-theme", theme);
  }
} catch (error) {
  /* the default theme is correct */
}

paint();
