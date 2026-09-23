/* Loaded INTO faces.html?mode=display by the HUD window, never by the HUD page
 * itself. See jarvis_hud.html's "Arc reactor" section for the other half.
 *
 * WHY THIS FILE EXISTS
 * The HUD's reactor is now the same kit face the Widget shows, embedded as
 * `faces.html?mode=display`. Display mode was written for the Widget and
 * takes its state from jarvis-link's `onLink` and its face and colours from
 * `invoke("get_appearance")`. Neither reaches it inside the HUD:
 *
 *   - `capabilities/hud.json` grants the HUD window NO app commands, on
 *     purpose, and capabilities are per window, not per frame - so the
 *     iframe's `get_appearance` and `get_link_state` are refused.
 *   - Tauri delivers events by evaluating a script in the webview's MAIN
 *     frame (tauri 2.11 `emit_js_script` -> `webview.eval`), so an iframe's
 *     own `listen()` callbacks are never called.
 *
 * And the brief is that the HUD's OWN state machine (`reactor.set(...)`)
 * drives the face, so the label under the face and the face itself can never
 * disagree. So the HUD posts `{type: "jarvis-hud-face", state, appearance}`
 * to this frame and this file applies it.
 *
 * WHY IT REACHES INTO faces.html's NAMES
 * faces.html is a classic script, so its top-level `let`/`const`/`function`
 * names live in the frame's one global scope, which this classic script
 * shares. It uses four of them: `LIVE_STATE`, `specState`, `mergeBindings`,
 * `drawSurface`, plus `CALM` (the OS reduce-motion query). That is coupling
 * to another file's internals, and it is deliberate and temporary: the right
 * home for all of it is a `message` listener inside faces.html's display
 * mode, and once that exists this file should be deleted. Every name is
 * checked before use, so a faces.html that renames one degrades to "the
 * face keeps drawing, in its own idle state" - never a blank or a throw - and
 * tests/hud.mjs fails loudly instead of the owner finding out.
 *
 * WHAT IT DOES NOT DO
 * Draw anything. Every pixel, and every flash / luminance governor, is still
 * faces.html's own. Nothing here can make a face brighter or faster; the one
 * timing change below only ever draws LESS often.
 */
(function () {
  "use strict";

  var MSG = "jarvis-hud-face";

  // Checked by name rather than assumed. `typeof` on an undeclared name is
  // safe; on a declared global lexical binding it reads the binding.
  var ok =
    typeof LIVE_STATE === "string" &&
    typeof specState === "function" &&
    typeof mergeBindings === "function" &&
    typeof drawSurface === "function";
  if (!ok) {
    console.error(
      "[hud-face] faces.html no longer exposes what this bridge drives; " +
        "the HUD face will stay in its own idle state"
    );
    return;
  }

  /** The state ids this build of the spec knows. Anything else is ignored. */
  var STATES = (function () {
    var spec = window.JARVIS_SPEC;
    var out = {};
    ((spec && spec.states) || []).forEach(function (s) {
      out[s.id] = true;
    });
    return out;
  })();

  var current = LIVE_STATE;

  // The HUD is the one authority on state here. Display mode also subscribes
  // to jarvis-link and assigns `LIVE_STATE = specState(link)` on every frame
  // it hears. Inside the HUD that should never fire (see the top of this
  // file), but "should never" is a reading of Tauri's source, not something
  // tested on Windows - so any link frame that does arrive resolves to the
  // HUD's state instead of fighting it.
  try {
    specState = function () {
      return current;
    };
  } catch (err) {
    /* read-only in some future build: the HUD's own writes below still win */
  }

  // Reduce motion. faces.html's editor paces itself to CALM_HZ (10fps) when
  // the OS asks for less motion; its display-mode loop does not, and the
  // canvas this replaced honoured the setting. So the HUD would otherwise
  // have got LESS calm by swapping faces. Same rule as the editor - draw
  // less often, never faster - with the skipped time handed to the next draw
  // so the face moves at the same speed, just in fewer steps.
  var CALM_MS = 100;
  var realDraw = drawSurface;
  var owed = 0;
  var lastDraw = 0;
  try {
    drawSurface = function (s, dt, state) {
      if (typeof CALM === "undefined" || !CALM.matches) {
        owed = 0;
        return realDraw(s, dt, state);
      }
      owed += dt;
      var now = performance.now();
      if (now - lastDraw < CALM_MS) return undefined;
      lastDraw = now;
      var step = Math.min(0.1, owed); // the same 0.1s cap display mode uses
      owed = 0;
      return realDraw(s, step, state);
    };
  } catch (err) {
    /* could not wrap: the face still draws, just at the display's full rate */
  }

  window.addEventListener("message", function (event) {
    // Only the HUD page that loaded this frame, on this origin.
    if (event.source !== window.parent || event.origin !== location.origin) return;
    var data = event.data;
    if (!data || data.type !== MSG) return;

    if (typeof data.state === "string" && STATES[data.state]) {
      current = data.state;
      LIVE_STATE = current;
    }
    // Colours only. The face itself is picked by the `&face=` the HUD put in
    // this frame's URL - the HUD reloads the frame when the owner changes
    // face, which also drops any binding they have since reset to default.
    if (data.appearance && typeof data.appearance === "object") {
      try {
        mergeBindings(data.appearance);
      } catch (err) {
        console.error("[hud-face] could not apply the owner's colours", err);
      }
    }
  });

  // Marks the frame as driven, for tests/hud.mjs and for anyone debugging.
  document.documentElement.setAttribute("data-hud-face", "ready");
})();
