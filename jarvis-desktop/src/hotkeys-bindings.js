// @ts-check
/**
 * The one command that reads Rust's own signature instead of a hand-written
 * `invoke(...)` call. THE PILOT, 2026-11-16: `set_hotkeys` and nothing else.
 *
 * WHY THIS FILE EXISTS AT ALL. `src/bindings.js` is generated from the Rust
 * command by `specta`, so the argument's name (`bindings`) and the shape of the
 * answer come from `hotkeys.rs` rather than from a page author's memory. But a
 * generated file only prevents drift if something TYPE-CHECKS the call that
 * uses it: the page is plain JavaScript, so nothing would read the generated
 * JSDoc types. This module is the checked seam - `npm run typecheck:bindings`
 * runs `tsc` over this file and the generated one, and it fails if the call
 * below disagrees with the Rust signature.
 *
 * `settings.js` calls this instead of `invoke("set_hotkeys", { bindings })`,
 * so the real call site is the one being checked. Everything else on the page
 * still calls `invoke` by hand, on purpose.
 */
import { commands } from "./bindings.js";

/**
 * Saves a new set of shortcuts and re-registers them immediately.
 *
 * @param {Record<string, string>} bindings accelerator, by action id
 * @returns {Promise<import("./bindings.js").Bound_Serialize[]>} the bindings and their verdicts
 */
export async function saveHotkeys(bindings) {
  return await commands.setHotkeys(bindings);
}
