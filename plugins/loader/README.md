# The plug-in loader

`jarvis_plugins.py` lives in `backend/` and is copied beside `jarvis_hud.py`
by `scripts/apply-patches.ps1`, like every other module this repository
ships.

On its own it does nothing. It needs **one** call in the core, added once by
`backend/plugin-loader.patch`. After that, a feature whose only wiring was a
startup call is a folder you can add, switch off or take out.

## What the loader does

At start-up it looks in `jarvis_plugins\` beside `jarvis_hud.py`. Each
subfolder has a `plugin.json` naming a module:

```json
{
  "name": "news",
  "module": "jarvis_news",
  "install": "handler",
  "stack_order": 57,
  "summary": "News headlines in the morning briefing."
}
```

The loader imports that module and calls its own `install()`, handing it the
same three callbacks the patch used to:

```python
jarvis_news.install(Handler, origin_ok=_origin_ok,
                    token_ok=_token_ok, read_body=_read_body)
```

Then it prints one banner line per module. That is the whole mechanism: it
replaces a patch that added exactly that call.

**What it deliberately does not do**

- It does not read, move or edit any module file, and it does not edit
  `jarvis_hud.py`.
- It does not approve anything, reach the network, start a program or write
  a file. Imports are the standard library only.
- It does not invent approval-gate entries. A feature that also adds a
  `_RISK` row still needs its patch, because a missing row would let an
  action skip Windows Hello. Those features are listed as core in
  [`../registry.json`](../registry.json), each with the reason.

**Loading order** is `stack_order` - the position the feature had in the old
patch stack - so a route's precedence is unchanged.

**Failure is isolated.** A folder with no manifest, a manifest that will not
parse, a module that is not there, a module whose `install()` raises: each is
named in the banner and skipped. Jarvis still starts, and every other module
still loads.

**Two folders are ignored on purpose:** any starting with `.` or `_`. To
switch one off without deleting it, put an empty file called `disabled`
beside its `plugin.json` (`scripts\add-plugin.ps1 -Name news -Disable`).

## Installing the hook

### The normal way

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\apply-patches.ps1
```

`apply-patches.ps1` applies `plugin-loader.patch` last, with everything
else. It rehearses the whole stack on a copy first and changes nothing at
all if anything would fail, so a tree this patch does not fit is refused
rather than half-applied.

### If your tree differs on purpose

The patch's context is `tutorials.patch`'s install block - the last one in
the core file. A tree that does not have the standard stack can skip the
patch and add the call by hand, in the same startup block as the other
features (the block that reads `try: import jarvis_news` and so on):

```python
    try:
        import jarvis_plugins
        print(jarvis_plugins.install(Handler, origin_ok=_origin_ok,
                                     token_ok=_token_ok, read_body=_read_body))
    except Exception as exc:
        print(f"  plugins    NOT ON ({type(exc).__name__}) - drop-in modules are off")
        print("             until jarvis_plugins.py is back: run apply-patches.ps1 again")
```

Four lines, and the same shape as every sibling block. Nothing else in the
core changes.

## Checking it

```powershell
py -3 tools\check_plugins.py
```

Twenty checks: the catalogue matches the stack, every patch is in exactly
one bucket, every drop-in module exists with an `install()`, the hook patch
is well formed and anchors where it says, it is last in `$PATCHES`, the
module is in both shipped-modules lists - and the loader's own 36 checks run
in the same command.

## The tests

`backend/test_jarvis_plugins.py` builds a stand-in for the two things the
core hands a module's `install()` - a `Handler` class and the three
callbacks - and proves, without the owner's PC: a folder becomes a live
route, the order is the stack's order, one broken module does not stop the
others, a disabled folder is skipped, and an absent folder changes nothing.
