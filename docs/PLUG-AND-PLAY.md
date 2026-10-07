# Plug-and-play modules: adding a feature as a file, not a patch

Branch: `feat/plug-and-play-modules`
Written 2026-10-06. Nothing in this document was guessed: the numbers come
from the repository's own patch list, measured by
`tools/gen_plugin_catalogue.py`.

## The problem this solves

Jarvis's backend lives on your PC, not in this repository. This repository
holds **changes** for it: 122 patch files, applied by
`scripts/apply-patches.ps1` in one fixed order.

Every optional feature used to arrive as **two** things:

1. a module, copied beside `jarvis_hud.py` (this is the feature);
2. a patch that adds **one line** to `jarvis_hud.py`, calling that module's
   own `install()`.

That one line is why you cannot simply drop a feature in. The module already
wraps the server and answers its own routes; the patch exists only to make
the call.

## What this branch does

It makes the call for you, from a folder.

```
your backend folder\
    jarvis_hud.py
    jarvis_plugins.py          <- the loader (copied by apply-patches.ps1)
    jarvis_news.py             <- the feature's module, exactly as before
    jarvis_plugins\
        news\
            plugin.json        <- names the module
            README.md
```

Add the folder, restart Jarvis, the feature is on. Take it out, it is off.
No patch, no edit to `jarvis_hud.py`, no change to any module file.

To switch one off without deleting it, put an empty file called `disabled`
beside its `plugin.json`.

### The one core change, made once

`backend/plugin-loader.patch` adds a single startup block to
`jarvis_hud.py`, in the same place and the same shape as every other
feature's block:

```python
    try:
        import jarvis_plugins
        print(jarvis_plugins.install(Handler, origin_ok=_origin_ok,
                                     token_ok=_token_ok, read_body=_read_body))
    except Exception as exc:
        print(f"  plugins    NOT ON ({type(exc).__name__}) - drop-in modules are off")
        print("             until jarvis_plugins.py is back: run apply-patches.ps1 again")
```

It is **one patch, applied once, ever**. After that, every feature that fits
this shape is a folder.

## How many features fit, and why the rest do not

Measured from the 122-patch stack, by reading each patch's own added and
removed lines:

| What the patch does | Count | Can it be a folder? |
|---|---|---|
| Adds **only** the startup call | **18** | **Yes.** The loader replaces it exactly. |
| Adds the startup call **plus** approval-gate entries | 12 | No - see below. |
| Adds the startup call plus other core code | 3 | No. |
| Adds the startup call, gate entries **and** core code | 2 | No. |
| Adds routes or tables straight into the core, no call | 42 | No. |
| Edits lines the core already has | 41 | No - order-dependent by nature. |
| Safety controls and the loader itself, kept core by hand | 4 | No, deliberately. |

The full list, one row per patch with the reason in plain words, is
`plugins/registry.json`, and `scripts\list-plugins.ps1 -Core` prints it.

### Why the gate-entry ones must not become bare folders

A patch like `watch-notifications.patch` does not only call
`jarvis_watch_notify.install()`; it also adds an entry to the approval
gate's own tables, which decide **whether the action needs a card and
whether it needs Windows Hello**.

A missing entry would not make the action silent - the gate's default is
"ask" - but it would drop the action out of the *risky* set, so it would
stop demanding Windows Hello. That is a weakening, and this repository does
not do those by accident. The loader therefore does not invent gate entries:
those features keep their patch, and the catalogue says so for each one.

## What to expect on the install you already have

Every one of the 18 drop-in features **already has its patch applied** on a
current install, so its folder is inert: the loader calls `install()` and
the module itself answers "(already on)". Jarvis stays exactly as it is; the
banner simply lists them.

So the folders matter for:

- **New modules from now on.** This is the point of the branch: write a
  module, drop a folder, done.
- **A core assembled feature by feature.** The folders are the worked
  example of the shape a new module needs.
- **Switching a feature off** on a backend where its patch has not been
  applied - for instance after retiring that patch by hand on your PC.

## What is proven here, and what is not

**Proven, in this repository, without your PC:**

- `backend/test_jarvis_plugins.py` - 36 checks. A folder becomes a live
  route through a stand-in core; loading follows `stack_order`; a broken
  module is isolated and named; a disabled folder is skipped; an absent
  folder changes nothing; the loader imports only the standard library and
  defines no network, child-process or file-writing call.
- `tools/check_plugins.py` - 20 checks, including all of the above. Every
  patch is in exactly one bucket; every drop-in module exists with an
  `install()`; the hook patch is well formed, anchors on the last install
  block the stack leaves in the core, and adds exactly one import and one
  call; it is last in `$PATCHES`; the loader is in both shipped-modules
  lists.
- The hook patch applies, for real, with `git apply` - checked against a
  file built from `tutorials.patch`'s own output (hunk succeeded at offset
  -6491 lines, i.e. found by context, not by line number).

**Not proven here, and it cannot be:** the hook patch has not been applied
to your real `jarvis_hud.py`, because that file is not in this repository.
`apply-patches.ps1` is what settles that: it rehearses the whole stack on a
copy and **changes nothing at all** if the patch does not fit. If your tree
differs, paste the four lines above into the startup block instead - it is
the same four lines the patch adds.

## Adding and removing one

```powershell
# what is available, and what is in your backend now
powershell -ExecutionPolicy Bypass -File .\scripts\list-plugins.ps1

# one
powershell -ExecutionPolicy Bypass -File .\scripts\add-plugin.ps1 -Name news

# every drop-in module this repository ships
powershell -ExecutionPolicy Bypass -File .\scripts\add-plugin.ps1 -All

# off, keeping the folder
powershell -ExecutionPolicy Bypass -File .\scripts\add-plugin.ps1 -Name news -Disable

# out
powershell -ExecutionPolicy Bypass -File .\scripts\add-plugin.ps1 -Name news -Revert
```

`add-plugin.ps1` copies or deletes one folder. It never edits
`jarvis_hud.py`, never touches a module file and never re-runs the patch
script. If the module it needs is not in your backend yet it says so and
skips, rather than adding a folder that cannot load.

## Writing a new drop-in module

1. Write the module as every other one is written: a top-level
   `install(handler_cls, *, origin_ok, token_ok, read_body)` that wraps
   `handler_cls.do_GET` / `do_POST`, answers its own routes after the
   server's own origin and token checks, and returns one short line for the
   banner. `backend/jarvis_news.py` is the smallest complete example.
2. Make it fail safe: if anything it needs is missing, it should raise, and
   the loader will name it and carry on.
3. Put the module in `backend/` and add it to `$SHIPPED` in
   `scripts/apply-patches.ps1` **and** `SHIPPED` in `backend/_where.py`
   (`test_shipped_modules.py` fails if the two lists differ).
4. Make the folder: `plugins/ready/<name>/plugin.json` with `name`,
   `module`, `install` (`"handler"` or `"none"`), a `summary` and a
   `stack_order` (its position among the other drop-ins).
5. Run `py -3 tools/check_plugins.py`.

## Files

| Path | What it is |
|---|---|
| `backend/jarvis_plugins.py` | The loader. Copied to your PC by `apply-patches.ps1`. |
| `backend/plugin-loader.patch` | The one startup call, applied once. |
| `backend/test_jarvis_plugins.py` | The loader's 36 checks, runnable anywhere. |
| `plugins/registry.json` | Every patch, its bucket, and why - generated. |
| `plugins/ready/<name>/` | One folder per drop-in module - generated. |
| `plugins/README.md` | The generated index. |
| `plugins/loader/README.md` | How the loader works and how to install the hook. |
| `tools/gen_plugin_catalogue.py` | Writes the catalogue from the patch stack. |
| `tools/check_plugins.py` | One command: all 20 checks. |
| `scripts/add-plugin.ps1` | Add, switch off, take out. |
| `scripts/list-plugins.ps1` | What is available and what is installed. |
