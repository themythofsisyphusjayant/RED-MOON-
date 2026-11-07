# Debugging Qasida programs (0.5.0)

There is no source-level debugger yet — this page documents
what exists today, honestly, and what is missing.

## What works today

### 1. Print tracing
`println` is the everyday tool. For training loops, print
loss every N steps; stdout is fully buffered when piped,
so for a crashing binary use
`forge.py build -o bin` + `script -qec "stdbuf -o0 -e0 bin"`.

### 2. Emit C and use gdb
```sh
python3 forge.py emit program.fg -o program.c
cc -g program.c -o program -lm
gdb ./program
```
Generated C locals keep the `.fg` variable names, so
`print myvar` in gdb works. Breakpoints land on C lines,
not `.fg` lines (see the gap below).

### 3. Leak hunting with allocation counters
```fg
println("allocs", arr_alloc_count(), "frees", arr_free_count());
```
If allocs climb across loop iterations while frees stay
flat, something created inside the loop is never freed.
This is exactly how the 0.5.0 tape leak was found: loop
bodies never freed their locals, so each training step's
tape leaked. That specific leak is fixed (block-end
freeing in codegen.py); the counters remain the tool for
the next one.

### 4. Safe-mode checks
Safe mode (the default) aborts on out-of-bounds access,
integer overflow, and division by zero with a message
naming the failure kind. It does not yet name the `.fg`
source line — see below.

## What is missing (not claimed)

A source-level debugger (breakpoints and stepping on
`.fg` lines) needs `#line` directives in the emitted C,
and those need correct file attribution: AST nodes carry
a line number but not a filename, and imports are merged
into one program, so a naive `#line` would misattribute
stdlib code to the main file. The fix is file tracking
through the parser — real work, not a flag flip. Until
then, gdb on the emitted C (above) is the debugger.

## Source-level debugging (0.7.0) — real now

The old limitation is fixed: AST functions now carry
their source file (`FuncDef.file`, stamped by
`compiler.load_program` per file, so imports keep
their own file), and `forge.py build --debug` emits
a `#line` directive before every statement plus
`-g` for the C compiler. gdb therefore steps
through `.fg` source, and `readelf
--debug-dump=decodedline` shows the mapping
(verified 26 Oct 2026 on examples/dbg_demo.fg:
statement starts map to dbg_demo.fg lines 9/10/11
and dbg_helper.fg lines 4/5; without --debug the
generated C has zero #line directives).

Usage:
  forge.py build examples/dbg_demo.fg --debug --keep-c /tmp/dbg.c -o /tmp/dbg
  gdb /tmp/dbg   # breakpoints land on .fg lines

Caveats, stated plainly: with -O2 the optimiser
still merges/inlines small code, so consecutive
statements can share an address and prologue code
(the main args setup, which is not a .fg statement)
maps to the C file, not a .fg line. Statement
starts map correctly; single-stepping through
optimised code is approximate by nature, not by
a bug in the directives. For exact stepping, build
the same command and recompile the kept C with
-O0 -g yourself.

## Fuzzer — tools/fuzz.py

A random-program fuzzer, pure Python stdlib. It
generates small programs that are valid by
construction (typed expressions, tracked array
lengths, bounded loops, no recursion, no division
by zero, no integer overflow in the generated
ranges), then runs each through `forge.py check`
and `forge.py run` in safe and fast mode and
classifies the outcome as OK, CHECK-ERROR,
CRASH, RUNTIME-FAIL, or MISMATCH (safe/fast
output divergence).

  python3 tools/fuzz.py [--seeds N] [--start S]
                        [--timeout T]
                        [--save-corpus DIR]

Defaults: 50 seeds from 0. Failing programs go
to a temp dir (paths printed in the summary)
unless --save-corpus is given. A real compiler
bug found by the fuzzer is saved as a minimal
reproducer under tools/fuzz_corpus/ — never fix
the compiler from a fuzz finding without first
reducing the program by hand.

Generator invariants worth knowing before you
extend it (each was learned from a real fuzz
failure, all generator bugs, not compiler bugs):
- Tracked array length is a LOWER bound on the
  real length: pushes inside if arms are banned
  (they may not execute), pushes inside loops
  are fine (trip counts are >= 1).
- While-loop counters are never visible to loop
  bodies (a body assignment could otherwise
  cancel the increment and loop forever).
- No int multiplication inside loop bodies, and
  outside them at least one side of `*` is a
  small literal — otherwise values walk to i64
  overflow and safe mode aborts.
- substr is always called as substr(s, 0, k):
  start 0 is always in range and over-long
  lengths are clamped by the runtime.
- The suite runs the fuzzer with 5 seeds (see
  tests/run_tests.py); longer runs are manual.
  Measured 26 Oct 2026: 300 seeds in 585 s
  (~2 s per seed, i.e. ~2 min for 50, ~8 min
  for 250 — each seed is check + safe run +
  fast run, mostly C compile time).
