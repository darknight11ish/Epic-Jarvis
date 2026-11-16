/**
 * `@tauri-apps/api/core`, for a page with no bundler.
 *
 * WHY THIS EXISTS. The generated `bindings.js` imports `invoke` from
 * `@tauri-apps/api/core`, which is what the crate's own docs assume: a
 * TypeScript app with npm packages. This page has neither - it is loaded
 * straight off disk by the webview, with no bundler and no `node_modules` - so
 * the generator (`hotkeys.rs`'s `bindings_js`) rewrites that specifier to this
 * file. `tauri.conf.json` already sets `withGlobalTauri`, which means Tauri
 * injects the very same API as `window.__TAURI__`, so this re-exports it under
 * the name the generated code calls.
 *
 * Only what a binding needs is exported, and the call is made fresh each time
 * rather than captured at module load, so it does not matter which runs first:
 * this module or Tauri's own bootstrap.
 */

/**
 * @param {string} command
 * @param {Record<string, unknown>} [args]
 * @param {unknown} [options]
 * @returns {Promise<unknown>}
 */
export function invoke(command, args, options) {
  return globalThis.__TAURI__.core.invoke(command, args, options);
}
