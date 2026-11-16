/**
 * The types `tsc` sees for the import map's one entry.
 *
 * At runtime that specifier resolves to `./tauri-api-core.js` (see
 * `settings.html`'s import map). This declares the same thing for the checker.
 * Kept deliberately loose, and loose in one deliberate place: `invoke` returns
 * `Promise<any>` because the REAL `invoke` is generic (`invoke<T>`) and the
 * generated wrappers call it without a type argument, declaring their result in
 * their own JSDoc instead. A `Promise<unknown>` here made the generated
 * `@returns {Promise<Bound_Serialize[]>}` a type error that says nothing about
 * the argument names this pilot is testing.
 *
 * @param {string} command
 * @param {Record<string, unknown>} [args]
 * @param {InvokeOptions} [options]
 * @returns {Promise<any>}
 */
export declare function invoke(
  command: string,
  args?: Record<string, unknown>,
  options?: InvokeOptions
): Promise<any>;

export type InvokeOptions = Record<string, unknown> | undefined;
