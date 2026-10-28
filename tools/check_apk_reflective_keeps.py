#!/usr/bin/env python3
"""The release APK must still contain the classes and constructors R8 cannot
see being created: the ones created by NAME, through reflection.

    python3 tools/check_apk_reflective_keeps.py [APK] [-v] [--list] [--self-test]

THE FAILURE THIS EXISTS TO CATCH, measured on the owner's phone 2026-10-27.

The release build (R8, `isMinifyEnabled = true`) stripped the no-arg
constructor of `androidx.work.OverwritingInputMerger`. WorkManager does not
call that constructor from any code R8 can follow: it stores the class NAME in
the work request and later runs

    Class.forName(className).newInstance()

So R8 read the constructor as unreachable and removed it. Nothing failed at
build time. Nothing failed in the unit tests. The debug build, which is not
shrunk, was perfect. On the phone the only sign was a log line -

    E/WM-WorkerWrapper: Could not create Input Merger \
        androidx.work.OverwritingInputMerger

- and every job WorkManager ran failed. A Glance home-screen widget draws its
whole composition inside one of those jobs (`androidx.glance.session.
SessionWorker`), so all five Jarvis widgets sat on the launcher's spinner for
ever while the app itself worked. PR #908 kept those constructors.

THE SAME CLASS OF BUG, EARLIER. `androidx.room.RoomDatabase` has the identical
hole: Room builds its generated `<Database>_Impl` class by name and calls a
no-arg constructor. That one crashed the app at launch and is why
`jarvis-client/app/proguard-rules.pro` carries the RoomDatabase keep rule
(line 76). It was fixed by hand and nothing stopped the next one.

THE RULE, WHICH IS WHY THIS IS A CHECK AND NOT A COMMENT. When a class is
created by name, its name and its constructor are part of the app's runtime
interface; R8 cannot see either. A missing one is not a build error, so the
only thing that can catch the next one is looking at the built ARTIFACT.

WHAT IT READS: the `classes*.dex` entries inside the APK, parsed here in plain
Python - no `dexdump`, no Android SDK, no device, no emulator. The dex is the
artifact that actually ships; it is the only answer that cannot be argued
with. (The keep rules are an input, not the truth: a library's own consumer
rules, a version bump, or an R8 change can move what survives without anyone
editing this repository's proguard file.)

WHAT IS CHECKED.

  1. An explicit table of reflective-instantiation targets below - each one a
     class this app needs at runtime together with the exact method (usually a
     constructor) that reflection calls. The table is the project's memory of
     every reflective hole found so far. Adding a new one is one entry, with a
     comment saying what creates it.

  2. Two family sweeps, so a subclass nobody has listed yet still fails:
     every CONCRETE class whose name ends in `InputMerger` must have a no-arg
     constructor (that is the only way WorkManager can build a merger it names
     in a request), and every concrete class ending in `Database_Impl` must
     have one too (that is Room's generated-database naming convention).

HOW IT FAILS. Every missing class or constructor is printed as

    FAIL: reflective instantiation hole - <class>
          missing: its constructor <init>()V is missing

with the reason and the fix, and the process exits 1. The words "reflective
instantiation hole - see proguard-rules.pro" appear in the summary, so the next
engineer meets the explanation rather than a bare red job.

IT DELIBERATELY DOES NOT FALL BACK TO THE DEBUG APK. A debug build is not
shrunk, so R8 cannot strip anything from it and the check could never fail
there - a pass against it would be a pass that proves nothing. With no APK
named it looks only at `jarvis-client/app/build/outputs/apk/release/
app-release.apk`; nothing there is an error that says how to build it.

LOCAL RUN, and how to prove it can fail (both were done when this was added):

    cd jarvis-client
    ./gradlew assembleRelease
    cd ..
    python3 tools/check_apk_reflective_keeps.py

    # prove the fail path: remove the InputMerger keep rule from
    # jarvis-client/app/proguard-rules.pro, rebuild, and run it again. A tree
    # without PR #908 is exactly that case: the release dex carries the class
    # and no constructor, and this script names it.
    # Restore proguard-rules.pro afterwards.

`--self-test` proves the decision logic and the failure message without
building anything: it feeds fabricated class inventories through the same
code path, including a missing constructor, a missing class, a concrete
`*InputMerger` nobody listed, and an abstract one that must NOT be reported.

WHERE IT RUNS. `.github/workflows/jarvis-client.yml`, in the `build` job,
immediately after the release APK is assembled - so every pull request that
touches the client gets it, not only main. It is a few seconds.
"""

from __future__ import annotations

import contextlib
import io
import os
import struct
import sys
import zipfile
import zlib

# The one artifact this check is about. No debug fallback on purpose - see the
# docstring: an unshrunk build cannot fail this check, so passing on it would
# be a vacuous pass, the failure mode tools/check_vacuous_checks.py exists for.
DEFAULT_APK = "jarvis-client/app/build/outputs/apk/release/app-release.apk"

NO_INDEX = 0xFFFFFFFF
ACC_ABSTRACT = 0x0400


class DexError(Exception):
    """A dex file that could not be read. Never a pass."""


class Target:
    """One class this app creates by name, and the method reflection calls."""

    __slots__ = ("descriptor", "method", "method_descriptor", "why")

    def __init__(self, descriptor: str, method: str, method_descriptor: str, why: str):
        self.descriptor = descriptor
        self.method = method
        self.method_descriptor = method_descriptor
        self.why = why

    @property
    def java_name(self) -> str:
        return descriptor_to_java(self.descriptor)

    @property
    def signature(self) -> str:
        return f"{self.method}{self.method_descriptor}"


def descriptor_to_java(descriptor: str) -> str:
    return descriptor.removeprefix("L").removesuffix(";").replace("/", ".")


# Every entry here is a place where the app (or a library inside it) hands R8 a
# STRING and creates the class later, so R8 cannot see the constructor being
# called. Keep the comments: they are what makes the next entry obvious.
TARGETS = (
    Target(
        "Landroidx/work/OverwritingInputMerger;",
        "<init>",
        "()V",
        "WorkManager's default InputMerger, and the 2026-10-27 failure (PR #908). "
        "WorkRequest.Builder stores this class's NAME, and WorkerWrapper creates it "
        "with Class.forName(...).newInstance(). With the constructor stripped, "
        "WorkerWrapper logs 'Could not create Input Merger' and EVERY WorkManager "
        "job fails - and a Glance widget draws inside one of those jobs, so every "
        "home-screen widget sat on its spinner for ever while the app worked.",
    ),
    Target(
        "Landroidx/work/ArrayCreatingInputMerger;",
        "<init>",
        "()V",
        "The other InputMerger WorkManager ships and can name in a work request. "
        "Same reflective newInstance() as OverwritingInputMerger; it is in the APK "
        "today because WorkManager's own `-keep class * extends InputMerger` keeps "
        "the class, and that rule keeps the NAME, not the constructor.",
    ),
    Target(
        "Landroidx/glance/session/SessionWorker;",
        "<init>",
        "(Landroid/content/Context;Landroidx/work/WorkerParameters;)V",
        "Glance runs each widget session in this Worker, and WorkManager's "
        "WorkerFactory builds a Worker subclass from the class NAME stored in the "
        "work request, through the (Context, WorkerParameters) constructor. The "
        "same reflection as the mergers, one layer up: losing this constructor is "
        "every widget silently never drawing.",
    ),
    Target(
        "Landroidx/work/impl/WorkDatabase_Impl;",
        "<init>",
        "()V",
        "The earlier instance of this exact class of bug. Room looks its generated "
        "<Database>_Impl class up by NAME and calls the no-arg constructor, so R8 "
        "stripped it and the app crashed at launch inside "
        "androidx.startup.InitializationProvider. Kept by the RoomDatabase rule at "
        "jarvis-client/app/proguard-rules.pro:76 - this asserts the result, not "
        "the rule.",
    ),
)

# Families where a class's NAME + a no-arg constructor ARE the contract, so a
# subclass nobody listed above is still caught. (descriptor suffix, why)
FAMILIES = (
    (
        "InputMerger;",
        "any concrete class named *InputMerger is something a work request can "
        "name and WorkManager builds with newInstance(), so it must have a no-arg "
        "constructor",
    ),
    (
        "Database_Impl;",
        "Room's generated database implementation is loaded by name and built with "
        "a no-arg constructor; that is the <Database>_Impl naming convention",
    ),
)


class Dex:
    """Just enough of the dex format to list classes and their methods."""

    def __init__(self, blob: bytes, label: str):
        self.blob = blob
        self.label = label
        self._strings: dict[int, str] = {}
        self._types: dict[int, str] = {}
        self._protos: dict[int, str] = {}
        self._parse_header()

    def _fail(self, message: str) -> None:
        raise DexError(f"{self.label}: {message}")

    def _parse_header(self) -> None:
        b = self.blob
        if len(b) < 0x70 or b[:4] != b"dex\n":
            self._fail("not a dex file (no `dex\\n` magic)")
        endian_tag = struct.unpack_from("<I", b, 0x28)[0]
        if endian_tag == 0x12345678:
            self.e = "<"
        elif endian_tag == 0x78563412:
            self.e = ">"
        else:
            self._fail(f"unknown endian tag 0x{endian_tag:08x}")
        (file_size,) = struct.unpack_from(self.e + "I", b, 0x20)
        (header_size,) = struct.unpack_from(self.e + "I", b, 0x24)
        if header_size != 0x70:
            self._fail(f"header_size is 0x{header_size:x}, not 0x70")
        if file_size != len(b):
            self._fail(f"header says {file_size} bytes but the entry is {len(b)}")
        # A checksum mismatch means this is not the dex R8 wrote. Refuse to
        # judge classes in a file that cannot be read reliably.
        (declared,) = struct.unpack_from("<I", b, 0x08)
        actual = zlib.adler32(b[12:]) & 0xFFFFFFFF
        if declared != actual:
            self._fail(
                f"checksum 0x{declared:08x} does not match the bytes "
                f"(0x{actual:08x}); the APK's classes.dex is corrupt"
            )
        (
            self.string_ids_size,
            self.string_ids_off,
            self.type_ids_size,
            self.type_ids_off,
            self.proto_ids_size,
            self.proto_ids_off,
            _field_ids_size,
            _field_ids_off,
            self.method_ids_size,
            self.method_ids_off,
            self.class_defs_size,
            self.class_defs_off,
        ) = struct.unpack_from(self.e + "12I", b, 0x38)
        for size, off, name in (
            (self.string_ids_size, self.string_ids_off, "string_ids"),
            (self.type_ids_size, self.type_ids_off, "type_ids"),
            (self.proto_ids_size, self.proto_ids_off, "proto_ids"),
            (self.method_ids_size, self.method_ids_off, "method_ids"),
            (self.class_defs_size, self.class_defs_off, "class_defs"),
        ):
            if size and not 0 <= off <= len(b):
                self._fail(f"{name}_off 0x{off:x} is outside the file")

    def string(self, idx: int) -> str:
        if idx not in self._strings:
            if idx >= self.string_ids_size:
                self._fail(f"string index {idx} out of range")
            (off,) = struct.unpack_from(
                self.e + "I", self.blob, self.string_ids_off + 4 * idx
            )
            _declared_length, pos = uleb128(self.blob, off, self.label)
            end = self.blob.find(b"\x00", pos)
            if end < 0:
                self._fail(f"string at 0x{off:x} has no terminator")
            # MUTF-8: the only difference from UTF-8 that can appear in what we
            # read here (class descriptors and method names) cannot, so a plain
            # forgiving decode is exact for our purpose.
            self._strings[idx] = self.blob[pos:end].decode("utf-8", "replace")
        return self._strings[idx]

    def type(self, idx: int) -> str:
        if idx not in self._types:
            if idx >= self.type_ids_size:
                self._fail(f"type index {idx} out of range")
            (str_idx,) = struct.unpack_from(
                self.e + "I", self.blob, self.type_ids_off + 4 * idx
            )
            self._types[idx] = self.string(str_idx)
        return self._types[idx]

    def proto(self, idx: int) -> str:
        """The method descriptor `(params)return` for a proto_id."""
        if idx not in self._protos:
            if idx >= self.proto_ids_size:
                self._fail(f"proto index {idx} out of range")
            _shorty, return_type, params_off = struct.unpack_from(
                self.e + "III", self.blob, self.proto_ids_off + 12 * idx
            )
            params = []
            if params_off:
                if params_off + 4 > len(self.blob):
                    self._fail(
                        f"parameter list at 0x{params_off:x} is outside the file"
                    )
                (count,) = struct.unpack_from(self.e + "I", self.blob, params_off)
                if count > 255:
                    self._fail(
                        f"parameter list at 0x{params_off:x} claims {count} params"
                    )
                for i in range(count):
                    (type_idx,) = struct.unpack_from(
                        self.e + "H", self.blob, params_off + 4 + 2 * i
                    )
                    params.append(self.type(type_idx))
            self._protos[idx] = "(" + "".join(params) + ")" + self.type(return_type)
        return self._protos[idx]

    def method(self, idx: int) -> tuple[str, str]:
        """(name, descriptor) of a method_id."""
        if idx >= self.method_ids_size:
            self._fail(f"method index {idx} out of range")
        _class_idx, proto_idx, name_idx = struct.unpack_from(
            self.e + "HHI", self.blob, self.method_ids_off + 8 * idx
        )
        return self.string(name_idx), self.proto(proto_idx)

    def _class_data_methods(self, off: int) -> list[int]:
        blob = self.blob
        sizes = []
        for _ in range(4):
            n, off = uleb128(blob, off, self.label)
            sizes.append(n)
        static_fields, instance_fields, direct_methods, virtual_methods = sizes
        for _ in range(static_fields + instance_fields):
            _idx, off = uleb128(blob, off, self.label)
            _flags, off = uleb128(blob, off, self.label)
        out = []
        for count in (direct_methods, virtual_methods):
            idx = 0
            for _ in range(count):
                diff, off = uleb128(blob, off, self.label)
                idx += diff
                _flags, off = uleb128(blob, off, self.label)
                _code_off, off = uleb128(blob, off, self.label)
                out.append(idx)
        return out

    def classes(self) -> dict[str, "ClassInfo"]:
        """descriptor -> ClassInfo, for every class defined in this dex."""
        out: dict[str, ClassInfo] = {}
        for i in range(self.class_defs_size):
            base = self.class_defs_off + 32 * i
            if base + 32 > len(self.blob):
                self._fail(f"class_def {i} is outside the file")
            (
                class_idx,
                access_flags,
                superclass_idx,
                _interfaces_off,
                _source_file_idx,
                _annotations_off,
                class_data_off,
                _static_values_off,
            ) = struct.unpack_from(self.e + "8I", self.blob, base)
            descriptor = self.type(class_idx)
            if not descriptor.startswith("L"):
                self._fail(f"class_def {i} is not a class: {descriptor}")
            superclass = (
                self.type(superclass_idx) if superclass_idx != NO_INDEX else None
            )
            methods = set()
            if class_data_off:
                for method_idx in self._class_data_methods(class_data_off):
                    methods.add(self.method(method_idx))
            if descriptor in out:
                self._fail(f"class {descriptor} is defined twice")
            out[descriptor] = ClassInfo(
                descriptor, access_flags, superclass, methods
            )
        return out


class ClassInfo:
    __slots__ = ("descriptor", "access_flags", "superclass", "methods")

    def __init__(
        self,
        descriptor: str,
        access_flags: int,
        superclass: str | None,
        methods: set[tuple[str, str]],
    ):
        self.descriptor = descriptor
        self.access_flags = access_flags
        self.superclass = superclass
        self.methods = methods

    @property
    def abstract(self) -> bool:
        return bool(self.access_flags & ACC_ABSTRACT)


def uleb128(blob: bytes, off: int, label: str) -> tuple[int, int]:
    result = 0
    shift = 0
    start = off
    while True:
        if off >= len(blob):
            raise DexError(f"{label}: uleb128 at 0x{start:x} runs past the end")
        byte = blob[off]
        off += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, off
        shift += 7
        if shift > 35:
            raise DexError(
                f"{label}: uleb128 at 0x{start:x} is more than 5 bytes"
            )


def problems(classes: dict[str, ClassInfo]) -> list[tuple[str, str, str]]:
    """(descriptor, what is missing, why) for everything wrong. Pure: no I/O.

    Kept separate from the reading so `--self-test` exercises exactly the code
    that judges the real APK.
    """
    found: list[tuple[str, str, str]] = []
    listed = set()
    for target in TARGETS:
        listed.add(target.descriptor)
        info = classes.get(target.descriptor)
        if info is None:
            found.append((target.descriptor, "the whole class is missing", target.why))
        elif (target.method, target.method_descriptor) not in info.methods:
            found.append(
                (
                    target.descriptor,
                    f"its constructor {target.method}{target.method_descriptor} "
                    f"is missing (the class itself is there)",
                    target.why,
                )
            )
    for descriptor in sorted(classes):
        if descriptor in listed:
            continue
        info = classes[descriptor]
        for suffix, why in FAMILIES:
            if descriptor.endswith(suffix) and not info.abstract:
                if ("<init>", "()V") not in info.methods:
                    found.append(
                        (
                            descriptor,
                            "its no-arg constructor <init>()V is missing "
                            "(the class is concrete, so something can name it)",
                            why,
                        )
                    )
                break
    return found


def report(classes: dict[str, ClassInfo], verbose: bool) -> int:
    found = problems(classes)

    print(f"classes parsed: {len(classes)}")
    for target in TARGETS:
        info = classes.get(target.descriptor)
        ok = info is not None and (target.method, target.method_descriptor) in info.methods
        print(f"  {'OK  ' if ok else 'FAIL'} {target.java_name}  {target.signature}")
        if verbose and info is not None:
            print(f"       methods: {len(info.methods)}, abstract: {info.abstract}")
    for suffix, _why in FAMILIES:
        family = [d for d, i in classes.items() if d.endswith(suffix) and not i.abstract]
        missing = sorted(d for d in family if ("<init>", "()V") not in classes[d].methods)
        print(
            f"  {'OK  ' if not missing else 'FAIL'} {len(family)} concrete class(es) "
            f"named *{suffix} all constructible with no args"
            + (
                f" - missing: {', '.join(descriptor_to_java(x) for x in missing)}"
                if missing
                else ""
            )
        )

    if not found:
        print(
            f"\nAll {len(TARGETS)} reflective-instantiation targets are in the "
            f"release dex, and every *InputMerger / *Database_Impl class in it "
            f"can still be constructed."
        )
        return 0

    print()
    for descriptor, missing, why in found:
        print(
            f"FAIL: reflective instantiation hole - "
            f"{descriptor_to_java(descriptor)}"
        )
        print(f"      missing: {missing}")
        print("      why this is here:")
        for line in why.split(". "):
            print(f"        {line.strip()}")
        print(
            "      on a phone this is a silent dead feature or a launch crash, "
            "not a build error."
        )
        print(
            "      fix: keep this class and this constructor in "
            "jarvis-client/app/proguard-rules.pro"
        )
        print()
    print(
        f"{len(found)} reflective instantiation hole(s) - see proguard-rules.pro. "
        f"R8 removed something the app creates by name."
    )
    return 1


def self_test() -> int:
    """Prove the judgement and the message, with no APK and no build."""
    def full_inventory() -> dict[str, ClassInfo]:
        classes = {}
        for target in TARGETS:
            classes[target.descriptor] = ClassInfo(
                target.descriptor,
                0x11,
                None,
                {(target.method, target.method_descriptor)},
            )
        return classes

    cases: list[tuple[str, dict[str, ClassInfo], int]] = []

    cases.append(("a good inventory passes", full_inventory(), 0))

    broken = full_inventory()
    broken["Landroidx/work/OverwritingInputMerger;"] = ClassInfo(
        "Landroidx/work/OverwritingInputMerger;", 0x11, None, {("a", "()V")}
    )
    cases.append(("a stripped InputMerger constructor is caught", broken, 1))

    gone = full_inventory()
    del gone["Landroidx/work/impl/WorkDatabase_Impl;"]
    cases.append(("a missing Room database class is caught", gone, 1))

    custom = full_inventory()
    custom["Lcom/example/FancyInputMerger;"] = ClassInfo(
        "Lcom/example/FancyInputMerger;", 0x11, None, {("<init>", "(I)V")}
    )
    cases.append(
        (
            "an unlisted concrete *InputMerger with no no-arg constructor is "
            "caught",
            custom,
            1,
        )
    )

    abstract = full_inventory()
    abstract["Landroidx/work/InputMerger;"] = ClassInfo(
        "Landroidx/work/InputMerger;", 0x0401, None, {("a", "()V")}
    )
    cases.append(
        ("an abstract *InputMerger without a constructor is NOT reported", abstract, 0)
    )

    cases.append(("an empty inventory fails for every target", {}, len(TARGETS)))

    failures = 0
    for name, classes, want in cases:
        got = problems(classes)
        if len(got) == want:
            print(f"self-test ok: {name} ({len(got)} problem(s))")
        else:
            failures += 1
            print(
                f"self-test FAIL: {name}: expected {want} problem(s), got {len(got)}"
            )

    # The message is part of the contract: it names the class in Java form and
    # tells the next engineer what happened. A failure that does not say this is
    # a failure, so this runs the real report() and reads what it printed.
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = report(broken, verbose=False)
    message = buffer.getvalue()
    if code != 1:
        failures += 1
        print(f"self-test FAIL: a broken APK reported exit {code}, not 1")
    for required in (
        "androidx.work.OverwritingInputMerger",
        "reflective instantiation hole",
        "proguard-rules.pro",
    ):
        if required not in message:
            failures += 1
            print(f"self-test FAIL: the report does not mention {required!r}")
    if failures:
        print(f"\nself-test: {failures} failure(s)")
        return 1
    print(
        f"\nself-test: all {len(cases)} cases pass, and the report names the "
        f"class, the hole and the fix."
    )
    return 0


def debug_apk_warning(path: str) -> str | None:
    normalised = path.replace("\\", "/").lower()
    if "/debug/" in normalised or normalised.endswith("-debug.apk"):
        return (
            f"{path} looks like the DEBUG build. R8 does not run on a debug "
            f"build, so it cannot strip anything and this check could never "
            f"fail - a pass here would prove nothing. Point it at the release "
            f"APK."
        )
    return None


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()

    verbose = "-v" in argv or "--verbose" in argv
    listing = "--list" in argv
    rest = [a for a in argv if a not in ("-v", "--verbose", "--list")]
    explicit = rest[0] if rest else None

    apk = explicit or DEFAULT_APK
    if not os.path.isfile(apk):
        if explicit:
            print(f"error: {apk} does not exist, so nothing was checked.")
        else:
            print(
                f"error: no release APK at {DEFAULT_APK}, so nothing was checked. "
                f"Build it first: cd jarvis-client && ./gradlew assembleRelease",
            )
        return 1
    warning = debug_apk_warning(apk)
    if warning:
        print(f"error: {warning}")
        return 1

    try:
        with zipfile.ZipFile(apk) as archive:
            names = sorted(
                (
                    name
                    for name in archive.namelist()
                    if name.startswith("classes") and name.endswith(".dex")
                ),
                key=lambda name: int("".join(c for c in name if c.isdigit()) or 0),
            )
            if not names:
                print(f"error: {apk} carries no classes*.dex, so nothing was checked.")
                return 1
            print(f"APK: {apk}")
            print(f"dex: {', '.join(names)}")
            classes: dict[str, ClassInfo] = {}
            for name in names:
                dex = Dex(archive.read(name), name)
                for descriptor, info in dex.classes().items():
                    if descriptor in classes:
                        print(
                            f"error: {name} defines {descriptor} again; this dex "
                            f"set is not the one R8 wrote."
                        )
                        return 1
                    classes[descriptor] = info
    except (OSError, zipfile.BadZipFile) as exc:
        print(f"error: could not read {apk} as an APK: {exc}")
        return 1
    except DexError as exc:
        print(f"error: {exc}")
        return 1

    if not classes:
        print(f"error: {apk} defines no classes at all, so nothing was checked.")
        return 1

    if listing:
        print("\nreflective families in this APK:")
        for descriptor in sorted(classes):
            if any(descriptor.endswith(suffix) for suffix, _ in FAMILIES):
                info = classes[descriptor]
                ctors = sorted(f"{n}{d}" for n, d in info.methods if n == "<init>")
                print(
                    f"  {'abstract' if info.abstract else 'concrete'}  "
                    f"{descriptor_to_java(descriptor)}  "
                    f"constructors: {', '.join(ctors) or '(none)'}"
                )
        print()

    return report(classes, verbose)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
