"""Drop-in modules: the loader that replaces a feature's one startup patch
(jarvis_plugins.py, plugins/loader/plugin-loader.patch, plugins/registry.json,
tools/gen_plugin_catalogue.py).

What this proves, without the owner's PC and without the real jarvis_hud.py:

  - the core's calling convention, exactly: `install(Handler, origin_ok=...,
    token_ok=..., read_body=...)` - the same three callbacks every module's
    own install() already takes - and a string back for the start-up banner;
  - a folder in `jarvis_plugins/` really does become a live module: its own
    install() is called, and the route it wraps answers through the Handler
    it was handed;
  - the loading ORDER is the old patch stack's own order (`stack_order`), so
    a route's precedence is what it was when the feature was a patch;
  - one bad module does not stop the others and does not stop Jarvis: a
    folder with no manifest, a manifest that will not parse, a module that
    is not there, a module whose install() raises - each is named in the
    banner and in `status()`, and every other module still loads;
  - a folder with a `disabled` marker is skipped, and is named;
  - nothing happens when the folder is absent, which is the state every
    existing install is in;
  - the loader imports nothing outside the standard library, defines no
    network or child-process call, and writes no file: its whole job is to
    make the call the patch made.

    python3 test_jarvis_plugins.py
"""
import ast
import json
import os
import shutil
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jarvis_plugins  # noqa: E402

FAILED, PASSED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
# A stand-in for the two things the core hands a module's install(): its
# Handler class, and the three callbacks. Same shape as jarvis_news.install().
# --------------------------------------------------------------------------

class Core:
    def __init__(self):
        self.calls = []
        self.sent = []
        core = self

        class Handler:
            def __init__(self, path="/"):
                self.path = path

            def do_GET(self):
                core.calls.append(("core-GET", self.path))

            def do_POST(self):
                core.calls.append(("core-POST", self.path))

            def _send(self, code, payload):
                core.sent.append((code, payload))
                return payload

        self.Handler = Handler

    def origin_ok(self, req):
        return True

    def token_ok(self, req):
        return True

    def read_body(self, req):
        return b"{}"

    def ctx(self):
        return {"origin_ok": self.origin_ok, "token_ok": self.token_ok,
                "read_body": self.read_body}

    def request(self, method, path):
        req = self.Handler(path)
        getattr(req, "do_" + method)()
        return req


MODULE_TEMPLATE = '''
"""A stand-in drop-in module for the loader's own tests."""
INSTALLED = []
ROUTE = "{route}"

def install(handler_cls, *, origin_ok, token_ok, read_body):
    get0 = handler_cls.do_GET
    if getattr(get0, "_plug_{name}", False):
        INSTALLED.append("twice")
        return "already on"
    def do_GET(self):
        if self.path.rstrip("/") != ROUTE:
            return get0(self)
        return self._send(200, {{"from": "{name}"}})
    do_GET._plug_{name} = True
    handler_cls.do_GET = do_GET
    INSTALLED.append("once")
    return "on"
'''

BAD_MODULE = '''
"""A drop-in module whose install() raises: the loader must survive it."""
def install(handler_cls, *, origin_ok, token_ok, read_body):
    raise RuntimeError("this module is broken")
'''


# --------------------------------------------------------------------------
# scaffolding
# --------------------------------------------------------------------------

class Sandbox:
    """A throwaway root holding `jarvis_plugins/` and the stand-in modules it
    names, with that root on sys.path - the way the backend folder really is.

    Under the backend folder rather than the system temp directory: this
    repository's own suites run in sandboxes that allow writes inside the
    checkout and refuse them elsewhere. Removed on the way out; Windows
    refuses to delete a file another handle still holds (see test_manner.py's
    _cleanup), so a folder that cannot be removed this moment is not a
    failure."""

    ROOT = HERE / "_plugin_test_tmp"
    _n = 0

    def __init__(self):
        self.ROOT.mkdir(parents=True, exist_ok=True)
        Sandbox._n += 1
        # Plain mkdir, not tempfile.mkdtemp: a directory made by mkdtemp does
        # not inherit this checkout's write permission on Windows, and making
        # anything inside it is then refused.
        self.root = self.ROOT / f"box-{os.getpid()}-{Sandbox._n}"
        self.root.mkdir(parents=True, exist_ok=True)
        self.folder = self.root / "jarvis_plugins"
        self.folder.mkdir(parents=True, exist_ok=True)
        self._saved = None

    def __enter__(self):
        sys.path.insert(0, str(self.root))
        self._saved = jarvis_plugins.plugins_dir
        jarvis_plugins.plugins_dir = lambda here=None: self.folder
        return self

    def __exit__(self, *exc):
        jarvis_plugins.plugins_dir = self._saved
        try:
            sys.path.remove(str(self.root))
        except ValueError:
            pass
        for name in [n for n in sys.modules if n.startswith("_plugintest_")]:
            sys.modules.pop(name, None)
        shutil.rmtree(self.root, ignore_errors=True)
        return False

    def plugin(self, name, *, module, order=1, body=None, manifest=None,
               manifest_text=None, disabled=False, folder_only=False):
        d = self.folder / name
        d.mkdir(parents=True, exist_ok=True)
        if not folder_only:
            if manifest_text is None:
                data = {"name": name, "module": module, "install": "handler",
                        "stack_order": order, "summary": f"the {name} module"}
                if manifest:
                    data.update(manifest)
                (d / "plugin.json").write_text(json.dumps(data), encoding="utf-8")
            else:
                (d / "plugin.json").write_text(manifest_text, encoding="utf-8")
        if disabled:
            (d / "disabled").write_text("", encoding="utf-8")
        if body is not None:
            (self.root / f"{module}.py").write_text(body, encoding="utf-8")
        return d


def mod_body(name, route):
    return MODULE_TEMPLATE.format(name=name, route=route)


# --------------------------------------------------------------------------
# tests
# --------------------------------------------------------------------------

def t_no_folder_is_silent():
    """The state every existing install is in: no folder, nothing changes."""
    jarvis_plugins._reset_for_tests()
    core = Core()
    with Sandbox() as box:
        shutil.rmtree(box.folder)                      # the folder is not there
        line = jarvis_plugins.install(core.Handler, **core.ctx())
    check("no folder: install() returns a line for the banner, not an error",
          isinstance(line, str) and "plugins" in line, line)
    check("no folder: nothing is recorded as loaded or failed",
          jarvis_plugins.status()["loaded"] == []
          and jarvis_plugins.status()["failed"] == [],
          str(jarvis_plugins.status()))
    core.request("GET", "/api/anything")
    check("no folder: the core answers exactly as it did",
          core.calls == [("core-GET", "/api/anything")] and core.sent == [],
          f"{core.calls} {core.sent}")


def t_a_folder_becomes_a_live_module():
    jarvis_plugins._reset_for_tests()
    core = Core()
    with Sandbox() as box:
        box.plugin("news", module="_plugintest_news", order=5,
                   body=mod_body("news", "/api/news"))
        line = jarvis_plugins.install(core.Handler, **core.ctx())
        check("a folder loads: its install() ran",
              "_plugintest_news" in sys.modules)
        check("a folder loads: the banner names it and says how many are on",
              "news" in line and "1 on" in line, line)
        core.request("GET", "/api/news")
        check("a folder loads: its route answers through the Handler",
              core.sent and core.sent[-1] == (200, {"from": "news"}), str(core.sent))
        before = len(core.sent)
        core.request("GET", "/api/other")
        check("a folder loads: every other path still reaches the core",
              core.calls[-1] == ("core-GET", "/api/other")
              and len(core.sent) == before,
              f"{core.calls} {core.sent}")
        check("a folder loads: status() agrees",
              jarvis_plugins.status()["loaded"] == ["news"],
              str(jarvis_plugins.status()))
        check("a folder loads: a second install() does not double-wrap",
              "_plugintest_news" in sys.modules
              and sys.modules["_plugintest_news"].INSTALLED == ["once"])


def t_order_is_the_patch_stack_order():
    jarvis_plugins._reset_for_tests()
    core = Core()
    with Sandbox() as box:
        # written in the wrong order on disk on purpose
        box.plugin("aaa", module="_plugintest_a", order=90,
                   body=mod_body("aaa", "/api/aaa"))
        box.plugin("zzz", module="_plugintest_c", order=1,
                   body=mod_body("zzz", "/api/zzz"))
        box.plugin("mmm", module="_plugintest_b", order=50,
                   body=mod_body("mmm", "/api/mmm"))
        jarvis_plugins.install(core.Handler, **core.ctx())
        check("order: modules install in stack_order, not folder-name order",
              jarvis_plugins.status()["loaded"] == ["zzz", "mmm", "aaa"],
              str(jarvis_plugins.status()["loaded"]))
        core.request("GET", "/api/zzz")
        check("order: a route from the first-loaded module still answers",
              core.sent[-1] == (200, {"from": "zzz"}), str(core.sent))
        core.request("GET", "/api/aaa")
        check("order: a route from the last-loaded module also answers",
              core.sent[-1] == (200, {"from": "aaa"}), str(core.sent))


def t_one_bad_module_does_not_stop_the_rest():
    jarvis_plugins._reset_for_tests()
    core = Core()
    with Sandbox() as box:
        box.plugin("good", module="_plugintest_good", order=1,
                   body=mod_body("good", "/api/good"))
        box.plugin("broken", module="_plugintest_bad", order=2, body=BAD_MODULE)
        box.plugin("missing", module="_plugintest_absent", order=3)   # no file written
        box.plugin("nom", module="_plugintest_good", order=4,
                   manifest_text="{not json")
        box.plugin("bare", module="_plugintest_good", order=5, folder_only=True)
        (box.folder / ".hidden").mkdir()
        (box.folder / "_private").mkdir()
        line = jarvis_plugins.install(core.Handler, **core.ctx())
        st = jarvis_plugins.status()
        check("isolation: the good module still loaded", st["loaded"] == ["good"], str(st))
        core.request("GET", "/api/good")
        check("isolation: the good module's route still answers",
              core.sent[-1] == (200, {"from": "good"}), str(core.sent))
        failed = {f["name"] for f in st["failed"]}
        check("isolation: the module whose install() raised is named",
              "broken" in failed, str(st["failed"]))
        check("isolation: a folder naming a module that is not there is named",
              "missing" in failed, str(st["failed"]))
        check("isolation: a manifest that will not parse is named",
              "nom" in failed, str(st["failed"]))
        check("isolation: a folder with no manifest is named",
              "bare" in failed, str(st["failed"]))
        check("isolation: folders starting with '.' or '_' are left alone",
              not any(n.startswith((".", "_")) for n in failed), str(st["failed"]))
        check("isolation: the banner says how many are on and how many are not",
              "1 on" in line and "4 not" in line, line)


def t_a_disabled_folder_is_off_not_failed():
    jarvis_plugins._reset_for_tests()
    core = Core()
    with Sandbox() as box:
        box.plugin("off", module="_plugintest_off", order=1, disabled=True,
                   body=mod_body("off", "/api/off"))
        line = jarvis_plugins.install(core.Handler, **core.ctx())
        st = jarvis_plugins.status()
        check("disabled: it is skipped, not failed",
              st["skipped"] == ["off"] and st["failed"] == [], str(st))
        check("disabled: it is NOT installed", "_plugintest_off" not in sys.modules)
        before = len(core.sent)
        core.request("GET", "/api/off")
        check("disabled: its route does not answer",
              len(core.sent) == before
              and core.calls[-1] == ("core-GET", "/api/off"),
              f"{core.calls} {core.sent}")
        check("disabled: the banner says it is off", "off -" in line, line)


def t_available_lists_without_installing():
    jarvis_plugins._reset_for_tests()
    with Sandbox() as box:
        box.plugin("thing", module="_plugintest_list", order=3,
                   body=mod_body("thing", "/api/thing"),
                   manifest={"summary": "a thing"})
        box.plugin("broken", module="_plugintest_x", order=1,
                   manifest_text="{not json")
        rows = jarvis_plugins.available(box.folder)
        check("available(): lists every folder without importing anything",
              "_plugintest_list" not in sys.modules)
        check("available(): names both rows",
              {r["name"] for r in rows} == {"thing", "broken"}, str(rows))
        thing = [r for r in rows if r["name"] == "thing"][0]
        check("available(): gives the module, the summary and the ok flag",
              thing["module"] == "_plugintest_list" and thing["summary"] == "a thing"
              and thing["ok"] is True, str(thing))
        bad = [r for r in rows if r["name"] == "broken"][0]
        check("available(): a broken one is reported, not raised",
              bad["ok"] is False, str(bad))


def t_the_real_catalogue_is_sound():
    """Every drop-in module the catalogue promises must exist, and its
    install() must take the shape the loader calls with."""
    repo = HERE.parent
    registry = repo / "plugins" / "registry.json"
    if not registry.is_file():
        SKIPPED.append("catalogue")
        print("skip  the catalogue has not been generated here")
        return
    data = json.loads(registry.read_text(encoding="utf-8"))
    ready = [e for e in data["entries"] if e["bucket"] == "plug-in"]
    check("catalogue: it has drop-in modules", len(ready) > 0)
    bad = []
    for entry in ready:
        module = HERE / f"{entry['module']}.py"
        if not module.is_file():
            bad.append(f"{entry['name']}: {entry['module']}.py is not in backend/")
            continue
        if "def install(" not in module.read_text(encoding="utf-8", errors="replace"):
            bad.append(f"{entry['name']}: {entry['module']} has no install()")
        if not (repo / "plugins" / "ready" / entry["name"] / "plugin.json").is_file():
            bad.append(f"{entry['name']}: plugins/ready/{entry['name']}/plugin.json is missing")
    check("catalogue: every drop-in module and folder is really there",
          not bad, "\n        ".join(bad))
    check("catalogue: nothing is counted twice",
          len({e["name"] for e in ready}) == len(ready))
    check("catalogue: every patch appears once",
          len({e["patch"] for e in data["entries"]}) == data["patch_count"],
          f'{len({e["patch"] for e in data["entries"]})} vs {data["patch_count"]}')
    check("catalogue: every patch is in exactly one bucket",
          all(e["bucket"] in ("plug-in", "core", "missing") for e in data["entries"]))


def t_no_core_change_beyond_the_one_call():
    """The loader must import nothing outside the standard library and must
    define no network, child-process or file-writing call. Read from the
    parse tree, not from the text: the docstring says those words too."""
    source = (HERE / "jarvis_plugins.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    allowed = {"__future__", "importlib", "json", "os", "sys", "pathlib"}
    check("loader: imports only the standard library modules it needs",
          imported <= allowed, str(sorted(imported - allowed)))

    banned_calls = {"system", "popen", "Popen", "run", "call", "check_output",
                    "urlopen", "socket", "connect", "exec", "eval", "compile"}
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = getattr(f, "id", None) or getattr(f, "attr", None)
            if name:
                called.add(name)
    hits = sorted(banned_calls & called)
    check("loader: no network, no child process, no eval", not hits, str(hits))

    writes = [n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and n.func.attr in {"write_text", "write_bytes", "mkdir", "unlink",
                                  "rename", "replace", "remove", "rmtree"}]
    check("loader: it creates, writes and deletes nothing", not writes, str(writes))


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("t_") and callable(fn):
            try:
                fn()
            except Exception:
                FAILED.append(name)
                print(f"FAIL {name} raised")
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
