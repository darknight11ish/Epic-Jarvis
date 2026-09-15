# Working with the owner of this repo

The Android session has its own copy of this file on
`claude/android-apk-build-q435fi`. If the branches ever merge, reconcile them
rather than picking one — the guidance is the same, this half adds the
question rule below.

## Keep multiple-choice questions SHORT

This is the rule that gets broken most. Asking four questions with four
paragraph-length options each is not a question, it is a document with radio
buttons. It makes a decision harder to make, not easier.

- **One or two questions at a time.** Three is a lot. Four is too many.
- **Two or three options each.** Not four.
- **One or two sentences per option.** Not a paragraph.
- **No jargon in the question itself.** If the question cannot be asked in
  plain words, explain the thing first in a sentence, then ask.
- Lead with the recommendation and say it is the recommendation.
- Put the long reasoning in the reply *around* the question, or in a document.
  Not inside the options.

Bad:

> Should the KV cache use q8_0 quantisation given that llama.cpp reaches the
> quantised path only through fused attention, and Ollama's `ml/device.go`
> gate admits compute capability 7.5 while excluding 7.2, which means…

Good:

> Jarvis can squeeze more conversation into the graphics card's memory by
> storing it in a smaller format. Slight risk it is not supported on your
> card, in which case things get much slower and nothing warns you.
>
> - **Do it, and check it worked** (recommended)
> - **Leave it alone**

## PowerShell: ONE line, ready to copy

The owner runs these by pasting into a terminal. A multi-line block is a
multi-line paste, and a multi-line paste into PowerShell goes wrong in ways
that look like the command is broken rather than like the paste was.

- **One line.** Statements joined with `;`. However long it ends up.
- **No `.ps1` file to run**, unless the point IS the file. A script file means
  being in the right folder, and it means the execution policy, and both of
  those produce errors that read as "your command is wrong".
- Say where any output file lands, in plain words, at the end of the command.

The trap, written down because it has already been shipped once: inside
`catch`, `$_` is the ERROR, not the pipeline item. In
`... | ForEach-Object { try { ... } catch { $o[$_] = ... } }` the catch writes
under an ErrorRecord instead of the name. Capture it first — `$n = $_` — or
use a plain `foreach` loop, where the variable is real.

## Explain things simply

The owner is a **beginner developer**. Write for someone who is smart and is
learning, not for someone who already knows the words.

- Say what a thing *is* before using its name.
- Short sentences, plain words.
- Say what to actually do — which file, which command, in order.
- Lead with the answer; reasoning after it.

This is about clarity, not about hiding things. Do not soften bad news or skip
caveats. Say them in plain words instead. If something is broken, uncertain,
or was my mistake, say so directly and early.

## Do not claim more than the evidence supports

This has caused real damage in this project more than once: a stack frame read
as a cause and relayed as "confirmed", and a bug invented by grepping my own
draft and mistaking it for the source file.

- Verify against the actual file before stating anything about it. Especially
  before stating it to the other session.
- Quote the evidence. Let the side that owns the code do the diagnosing.
- "I checked X and it says Y" beats "Y". "I have not checked" beats a guess
  delivered confidently.

## Checking the Rust without waiting for CI

`cargo clippy` fails in the dev container: the product is a Windows app, the
Linux dependency graph pulls `gdk-sys`, and GTK is not installed. For a long
time that meant every Rust change was pushed unverified and checked by CI five
minutes later.

**It does not have to be.** The `x86_64-pc-windows-msvc` target is installed,
and checking against it selects the *Windows* dependency graph, which has no
GTK in it. Nothing is linked, so no MSVC toolchain is needed:

```
cd jarvis-desktop/src-tauri
cargo fmt --check
cargo check  --target x86_64-pc-windows-msvc --all-targets
cargo clippy --target x86_64-pc-windows-msvc --all-targets -- -D warnings
```

That is two of the three things CI runs, on the same code CI compiles,
including every `#[cfg(windows)]` block — which a Linux check would have
skipped entirely, and which is where the unsafe FFI lives. It takes about
twenty seconds warm.

The third, `cargo test`, still needs a Windows host. Write the Rust tests
anyway; they are compiled by `--all-targets` above, so at least they are known
to build. A "GNU compiler is not supported for this target" warning in the
output is expected and harmless.

## Where everything is written down

- `docs/ARCHITECTURE.md` — **read first.** The invariants, the one permission
  model every feature must use, memory, events, and what does not exist yet.
- `docs/MODEL-TOPOLOGY.md` — what runs on the graphics card and why.
- `backend/README.md` — the patches and what each one fixes.

The Python backend lives on the owner's machine, not in this repo. `backend/`
holds patches against it plus tests that prove the patches work.
