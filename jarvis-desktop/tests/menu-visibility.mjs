/**
 * menu-visibility.mjs - tests for "Show or hide menus" on desktop
 * (docs/MENU-VISIBILITY-DESIGN.md, docs/JARVIS-API.md section 109).
 *
 * Runs on plain Node with no browser against tests/fixtures/menu-cases.json.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as M from "../src/menu-visibility.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const FIX = JSON.parse(read("tests/fixtures/menu-cases.json"));

const fails = [];
const check = async (name, fn) => {
  try {
    await fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

/* ── 1. Constants, words, and never-hideable list ────────────────────── */

await check("the catalogue and constants match the shared fixture", async () => {
  assert.equal(M.VERSION, FIX.version);
  assert.equal(M.GROUP_PREFIX, FIX.group_prefix);
  assert.deepEqual(M.ACTIONS, FIX.actions);
  assert.equal(M.MENUS.length, FIX.menus.length);
  for (let i = 0; i < FIX.menus.length; i++) {
    const fm = FIX.menus[i];
    const mm = M.MENUS[i];
    assert.equal(mm.id, fm.id);
    assert.equal(mm.title, fm.title);
    assert.equal(mm.about, fm.about);
    assert.equal(mm.hide, fm.hide);
    assert.equal(mm.collapse, fm.collapse);
    assert.equal(mm.why, fm.why);
  }
  assert.deepEqual(
    M.GROUPS.map((g) => g.id),
    FIX.groups.map((g) => g.id)
  );
  assert.deepEqual(
    M.NEVER_HIDE,
    FIX.never_hide.map((n) => n.id)
  );
});

await check("every word both apps show is the fixture's word", async () => {
  for (const [k, v] of Object.entries(FIX.words)) {
    assert.equal(M.WORDS[k], v, `word ${k} mismatch`);
  }
  for (const [k, v] of Object.entries(FIX.replies)) {
    assert.equal(M.REPLIES[k], v, `reply ${k} mismatch`);
  }
});

/* ── 2. The NEVER_HIDE guard ─────────────────────────────────────────── */

await check("no never-hideable id is hideable anywhere", async () => {
  const neverSet = new Set(M.NEVER_HIDE);
  const menusNever = new Set(M.MENUS.filter((m) => !m.hide).map((m) => m.id));
  assert.deepEqual(neverSet, menusNever);

  for (const id of M.NEVER_HIDE) {
    const st = new M.State();
    const res = M.hide(st, id, "desktop");
    assert.notEqual(res, "ok", `${id} must not return ok on hide`);
    assert.ok(!st.hidden.has(id), `${id} must not be added to hidden`);

    // Stored bad data is never considered hidden
    const bad = new M.State(new Set([id]));
    assert.ok(!M.isHidden(bad, id), `${id} must not be hidden even if stored`);
    assert.ok(!M.sanitize(bad, "desktop").hidden.has(id), `${id} must be dropped by sanitize`);
  }

  // No group contains a never-hideable id
  for (const g of M.GROUPS) {
    const mems = M.members(g.id, null);
    for (const mem of mems) {
      assert.ok(!neverSet.has(mem), `${mem} in group ${g.id} must not be in NEVER_HIDE`);
    }
  }
});

await check("thousands of random operations never hide a never-hideable menu", async () => {
  const neverSet = new Set(M.NEVER_HIDE);
  const ids = M.MENUS.map((m) => m.id)
    .concat(M.GROUPS.map((g) => g.id))
    .concat(["nonexistent", "group.none"]);
  const ops = M.ACTIONS;
  const apps = ["desktop", "phone", null];

  let seed = 20260930;
  function rnd(n) {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return seed % n;
  }

  let st = new M.State();
  for (let i = 0; i < 5000; i++) {
    const op = ops[rnd(ops.length)];
    const id = ids[rnd(ids.length)];
    const app = apps[rnd(apps.length)];
    M.apply(st, op, id, app);
    if (rnd(10) === 0) {
      st = M.sanitize(st, app);
    }
    for (const n of neverSet) {
      assert.ok(!M.isHidden(st, n), `never-hideable ${n} became hidden at step ${i}`);
      assert.ok(!st.hidden.has(n), `never-hideable ${n} entered hidden set at step ${i}`);
    }
  }
});

/* ── 3. Replay every worked case of the state machine ─────────────────── */

await check("every state case from menu-cases.json replays identically", async () => {
  for (const c of FIX.state_cases) {
    const name = c.name;
    const app = c.app;
    let st = M.State.of(c.start);
    for (const step of c.steps) {
      const res = M.apply(st, step.op, step.id, app);
      assert.equal(res, step.result, `${name}: step ${step.op} ${step.id} result`);
    }
    assert.deepEqual(st.as_dict(), c.end, `${name}: end state mismatch`);

    const vs = c.visit ? M.visitSet(c.visit) : new Set();
    for (const [id, expectedHidden] of Object.entries(c.hidden)) {
      assert.equal(
        M.isHidden(st, id, vs),
        expectedHidden,
        `${name}: isHidden(${id}) with visit '${c.visit}'`
      );
    }
    for (const [id, expectedCollapsed] of Object.entries(c.collapsed)) {
      assert.equal(
        M.isCollapsed(st, id, vs),
        expectedCollapsed,
        `${name}: isCollapsed(${id}) with visit '${c.visit}'`
      );
    }
    assert.equal(
      M.hiddenCount(st, app),
      c.hidden_count,
      `${name}: hiddenCount mismatch`
    );
  }
});

/* ── 4. Replay sanitize cases ─────────────────────────────────────────── */

await check("stored data is cleaned according to sanitize_cases", async () => {
  for (const c of FIX.sanitize_cases) {
    const start = M.State.of(c.start);
    const end = M.sanitize(start, c.app);
    assert.deepEqual(end.as_dict(), c.end, `sanitize case failed for ${c.app}`);
    // Idempotent
    const twice = M.sanitize(end, c.app);
    assert.deepEqual(twice.as_dict(), c.end, `sanitize not idempotent for ${c.app}`);
  }
});

/* ── 5. Replay route cases ────────────────────────────────────────────── */

await check("route parsing matches route_cases", async () => {
  for (const c of FIX.route_cases) {
    const got = M.parseRoute(c.header);
    assert.deepEqual(got, c.parsed, `route case mismatch for header: ${c.header}`);
  }
});

/* ── 6. Storage load and save ─────────────────────────────────────────── */

await check("loadState and saveState handle storage, versioning and errors cleanly", async () => {
  const store = {};
  const mockStorage = {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => {
      store[k] = String(v);
    },
    removeItem: (k) => {
      delete store[k];
    },
  };

  // Empty storage -> default visible
  let st = M.loadState(mockStorage, "desktop");
  assert.equal(st.hidden.size, 0);
  assert.equal(st.collapsed.size, 0);

  // Save changes
  M.hide(st, "brain.work.quiz", "desktop");
  M.collapse(st, "brain.work.goals", "desktop");
  M.saveState(st, mockStorage, "desktop");

  assert.equal(mockStorage.getItem("jarvis.menus.v"), "1");
  const loaded = M.loadState(mockStorage, "desktop");
  assert.ok(loaded.hidden.has("brain.work.quiz"));
  assert.ok(loaded.collapsed.has("brain.work.goals"));

  // Stale version reads as empty
  mockStorage.setItem("jarvis.menus.v", "2");
  const stale = M.loadState(mockStorage, "desktop");
  assert.equal(stale.hidden.size, 0);

  // Throwing storage does not crash
  const throwingStorage = {
    getItem: () => {
      throw new Error("security sandbox error");
    },
    setItem: () => {
      throw new Error("security sandbox error");
    },
  };
  const safe = M.loadState(throwingStorage, "desktop");
  assert.equal(safe.hidden.size, 0);
  assert.doesNotThrow(() => M.saveState(st, throwingStorage, "desktop"));
});

/* ── 7. Manager visit overrides and event handling ───────────────────── */

await check("createMenuManager manages visits and subscriptions", async () => {
  const store = {};
  const mockStorage = {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => {
      store[k] = String(v);
    },
  };

  const mgr = M.createMenuManager({ storage: mockStorage, app: "desktop" });
  mgr.hide("group.study");
  assert.ok(mgr.isHidden("brain.work.quiz"));
  assert.ok(mgr.isHidden("brain.work.decks"));

  // Show for visit
  mgr.showForVisit("brain.work.quiz");
  assert.ok(!mgr.isHidden("brain.work.quiz"), "quiz shown for visit");
  assert.ok(mgr.onVisit("brain.work.quiz"), "quiz is on visit");
  assert.ok(mgr.isHidden("brain.work.decks"), "decks remains hidden");

  // Keep it visible
  mgr.show("brain.work.quiz");
  mgr.clearVisit("brain.work.quiz");
  assert.ok(!mgr.isHidden("brain.work.quiz"), "quiz remains visible permanently");
  assert.ok(mgr.isHidden("brain.work.decks"), "decks remains hidden");

  // Reset
  mgr.reset();
  assert.ok(!mgr.isHidden("brain.work.decks"), "decks visible after reset");
});

/* ── 8. The way to this card from the Brain ──────────────────────────── */

await check("the Brain's hidden-menus button leaves the place and asks for a place open_fix_place takes", async () => {
  // The button on the Brain's rail ("Show or hide menus") opens Settings at
  // this card. The place travels in storage, not in the call: `open_fix_place`
  // opens the Settings window and accepts only "settings", "brain" and
  // "history" (src-tauri/src/plain_errors.rs), and settings.js's own
  // goToPlace() reads this key on load, on focus and on the storage event.
  // Bug audit 2026-10-05, R5: the button asked for "menu-visibility" as the
  // place and had no grant for this window, so it did nothing at all - and
  // neither failure was visible anywhere.
  const brain = read("src/brain.js");
  const at = brain.indexOf('$("btn-rail-hidden-menus")');
  assert.ok(at > 0, "the button's handler is still in brain.js");
  const body = brain.slice(at, at + 1200);
  // The place is left BEFORE the branch, so the desktop path leaves it too:
  // the old code left it only in the browser branch, and asked the command for
  // "menu-visibility", which the command refuses.
  const branch = body.indexOf("if (IS_TAURI)");
  assert.ok(branch > 0, "the handler still branches on IS_TAURI");
  assert.match(body.slice(0, branch), /localStorage\.setItem\("jarvis\.settings\.place", JSON\.stringify\(\{ place: "menu-visibility"/);
  assert.match(body, /invoke\("open_fix_place", \{ place: "settings" \}\)/);
  assert.doesNotMatch(body, /place: "menu-visibility" \}\)/, "the place must not be the command's argument");
  // The card it aims at is Settings' own, in Settings' own words.
  assert.match(read("src/settings.html"), /id="menu-visibility"/);
  // And the window that draws the button is granted the command it calls.
  const brainCap = JSON.parse(read("src-tauri/capabilities/brain.json"));
  assert.ok(brainCap.permissions.includes("open-fix-place"));
  const surfaces = read("src-tauri/permissions/surfaces.toml");
  assert.match(surfaces, /identifier = "open-fix-place"[\s\S]*?"allow-open-fix-place"/);
});

if (fails.length) {
  console.error(`\n${fails.length} test(s) failed`);
  process.exit(1);
} else {
  console.log("\nAll desktop menu visibility tests passed!");
}
