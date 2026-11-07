# Qasida — Book

Dedicated to Tejaswini — Qasida. See DEDICATION.md.
Formerly Forge v2; commands are still `forge.py`, files are `.fg`.

New to programming? Read [HIGH_SCHOOL_GUIDE.md](HIGH_SCHOOL_GUIDE.md)
first — it is the same language, explained in simple school-level
words, with steps to run it and real-life uses. For a 10-step
guided path, see [TOUR.md](TOUR.md); for the terse reference,
see `SPEC_V2.md`. Every program output quoted here was produced
by running the program.

## 1. What this language is

Qasida is a small compiled language with a
Python-like surface and native speed: source compiles to C,
then to a native binary. It was built problem-first — the
problems it fixes are memory unsafety, null, runtime type and
coercion bugs, silent arithmetic, ignorable errors, and the
complexity tax — with a Go-like safety model: safe by default,
no borrow checker, no null, no implicit conversion. It is
aimed at safe, simple, fast tools, CLIs, and servers, not at
kernels, browsers, or ML ecosystems.

Run a program:

```
python3 forge.py run prog.fg
```

Build a binary:

```
python3 forge.py build prog.fg -o prog
```

Two modes: **safe** (default, `-O2`, checked arithmetic,
bounds-checked indexing, readable aborts) and **fast**
(`--mode fast`, `-O3 -march=native`, unchecked). Use fast only
for hot code you already validated in safe mode. The C
compiler is selectable with `QASIDA_CC` (default `cc`).

## 2. Types and values

- `int` (64-bit native, 32-bit on big32), `float` (64-bit),
  `bool`, `str`, arrays `[T]`, structs, enums.
- `let` is immutable; `let mut` is mutable. Function
  parameters are immutable — copy one into a `let mut` local
  before assigning to it.
- No null. No implicit conversion: write `x as float` and
  `x as int` explicitly. Floats print with 6 significant
  digits (`%g`).
- A non-void function must end its body with a `return`. If
  it does not, the compiler says so and tells you the fix:
  "add a return statement of type int at the end of the
  function".

```qasida
let name: str = "teju";
let mut count: int = 0;
count = count + 5;
```

## 3. Control flow

`if` / `else if` / `else`, `while`, `for v in array`,
`break` (innermost loop), `return`, bare blocks. Conditions
must be `bool`. There is no `continue`.

`examples/break_demo.fg` output:

```
while total = 3
for sum = 6
nested count = 6
```

`break` works on native, WASM, and big32, and the checker
rejects it outside a loop — including inside a function called
from a loop.

## 4. Functions and generics

```qasida
fn twice(n: int) -> int {
    return n * 2;
}
```

Generics work by monomorphisation: write `Pair<int, str>` and
the compiler generates the concrete copy. `examples/generics_demo.fg`
output:

```
42 hi 1.5 7 seven
```

Do not name a function, variable, parameter, struct, or field
after a C keyword (`double`, `float`, `int`, `char`, ...).
The checker rejects it — "'double' is a C keyword and cannot
be used as a function name; rename it" — instead of letting
the C compiler fail cryptically.

## 5. Arrays

Arrays are `[T]`, indexed from 0, bounds-checked in safe mode.
`len` gives the length; `push` appends. Index assignment into
an array parameter or struct field mutates the caller's buffer,
but pushing to a plain array parameter does not reach the
caller natively (it does on WASM — a documented divergence).

Arrays of structs and nested arrays both work natively:

`examples/struct_array_demo.fg` output:

```
count = 2
second = 3 4 b
sums = 4 6
after push = 3 c
after set = 10 z
copy = 3 4 b
```

`examples/nested_array_demo.fg` output:

```
rows = 2 cols = 3
m01 = 2 m12 = 6
total = 21
after push rows = 3 m20 = 7
after set = 20
shared row = 40
after row set = 10 20
```

Struct arrays and nested arrays are rejected with clear errors
on WASM and big32; string indexing is rejected on big32.

## 6. Strings

`s[i]` is a 1-character string (byte indexing), bounds-checked
in safe mode. Strings are immutable: `s[i] = ...` is a compile
error. Builtins: `split`, `join`, `substr`, `trim`,
`starts_with`, `ends_with`. Strings support `==`/`!=` only —
no `<` ordering, no int-to-string builtin.

`examples/str_index_demo.fg` output:

```
first = h third = l last = o
exclaim = h!
found l at 2
```

`examples/strings_demo.fg` output:

```
parts = 3 b
joined = a-b-c
sub = world
trim = hi
starts = true
ends = true
```

## 7. Structs

Field definitions end with `;`. A struct containing another
struct must be defined in the same file, after the inner one.

`examples/structs_point.fg` output:

```
distance = 5
q.x = 6 q.y = 4
distance = 7.2111
```

## 8. Enums, match, Option, Result

`match` is exhaustive: miss a variant and the compiler lists
exactly which ones are missing. Arms are triples — pattern,
optional binding, body. `Option`/`Result` and the `?`
operator work the same way.

`examples/enums_match.fg` output:

```
green
other
```

`examples/option_result_demo.fg` output:

```
opt = 42
none = 99
div = 5
error = division by zero
```

`examples/try_demo.fg` output:

```
opt ok = 43
opt none present = false
calc error = div by zero
```

## 9. Concurrency: spawn and scope

`spawn` starts a thread for a void function taking 0 or 1 int
argument. Threads spawned outside any scope are joined when
`main` returns. A `scope` block joins every task spawned inside
it — directly or by functions called from inside it — at the
closing brace, and on any `return` or `break` that leaves it,
so no task outlives its block. Scopes nest; a thread is never
joined twice.

`examples/scope_demo.fg` output:

```
worker done 1
worker done 2
after scope
```

What a scope does not do: it returns no results (spawned
functions are void), it does not cancel a hung task (a scope
waiting on a task that never finishes waits forever, like any
join), and it does not add channels or futures. `scope` is not
a reserved word: it is recognised only as `scope` followed by
`{` at statement position, so `scope` still works as an
ordinary variable name. On WASM and big32, where threads are
not supported, a scope block runs as a plain block and a
`spawn` inside it fails as before.

## 10. Files, CLI, HTTP

File I/O: `read_file` / `write_file` / `file_exists` /
`read_bytes` / `write_bytes`. CLI: `args()` (excludes the
program name). HTTP client: `http_get`. The HTTP server
builtins (`http_listen` / `http_accept` / `http_read_request` /
`http_respond` / `http_respond_status` / `http_close`) build a
sequential server: one request per connection, single reads up
to 8191 bytes per call (call `http_read_request` repeatedly to
read more), IPv4 only, no TLS, no chunked bodies. The registry
server in `examples/apps/registry_server.fg` is written in the
language itself and speaks the package registry's HTTP API.

`examples/apps/todo.fg` is a todo CLI: add/list/done, stored
in `todo.txt`. It needed a new builtin, `file_exists()`,
because `read_file()` aborts on a missing file — a real
language gap, found by building a real app, and fixed in the
compiler.

## 11. Packages

```
qasida pkg init        # forge.toml + src/main.fg + tests/smoke.fg
qasida pkg publish     # into $FORGE_REGISTRY/<name>/<version>/
qasida pkg add name@ver
qasida pkg serve --dir D --port P [--token T]
qasida pkg publish-remote <url> [--token T]
qasida pkg add-remote <url> name@ver
qasida pkg list-remote <url>
```

Packages are self-contained (no stdlib imports, no cross-package
imports). The registry is seeded with 30 small packages
(units, money, geometry, interest, roman, bases, dice,
percentages, loans, bmi, colors, sorting, search, primes,
factors, statistics, grades, tax, cooking, budget, checks,
morse, textstats, speed, data, angle, fractions, vectors,
matrices, polynomials). Public hosting is not live yet — it
needs a host account, a domain, and HTTPS.

## 12. Testing and diagnostics

`forge.py test` runs the language's own test suite. Package
smoke tests live in `tests/smoke.fg` and run like any program.

Diagnostics end with fixes where a fix is mechanical:

```
undefined variable 'coutn'. Did you mean 'count'?
undefined function 'prnitln'. Did you mean 'println'?
variable 'x' is declared float but initialised with int; convert the value with 'value as float'
function 'main' returns int but its body does not end with a return; add a return statement of type int at the end of the function
```

Suggestions use edit distance over in-scope names, functions,
builtins, types, and enum variants, and appear only when
something is close. The language server (`forge.py lsp`) serves
the same diagnostics plus completions from the checker's own
keyword and builtin sets, so completions cannot drift stale;
see `tests/lsp_smoke.py` for the end-to-end LSP test.

## 13. WebAssembly and WIT

The WASM backend writes a real `.wasm` binary directly (no
toolchain needed) for int, float, bool, str, arrays, functions,
recursion, and print. It wraps on integer overflow and traps
on division by zero and out-of-bounds indexing — the documented
trade-off versus safe mode's readable aborts. There is no free
and no GC: allocations in a loop grow memory. String output
goes to an exported stdout buffer (length at address 0, bytes
at 8..8+len); see `docs/WASM_STRINGS.md`.

WIT-first: write the interface first, then build with
`--wit prog.wit`. The compiler checks every non-`main`
function against the world's exports (arity, parameter types in
order, return type) before generating the module. Mapping:
int -> s64, float -> f64, bool -> bool, str -> string,
[T] -> list<T>. World imports are rejected (the module is
self-contained). This is interface-contract checking, not
component-model binary encoding — see `docs/WIT.md` for the
boundary.

## 14. big32 RISC-V

The big32 backend targets a small RISC-V core: 32-bit ints,
single-cycle and 5-stage pipelined cores, S/U modes with an
Sv32 MMU, interrupts, and an OS boot that runs a kernel in
S-mode dropping to U-mode with syscalls. It is not Linux and
not xv6. String indexing, struct arrays, spawn, enums, match,
and extern/FFI are rejected with clear errors there. Float
division, ordered comparisons, printing, and casts are not done
on big32, and subnormal fidelity is not claimed.

## 15. Machine learning

The stdlib ML stack (`tensor.fg`, `autograd.fg`, `gpt.fg`,
...) trains small models in the language itself. A 2-2-1
sigmoid MLP learns XOR by backprop: loss 0.558973 down to
0.000267766 over 10000 epochs, final outputs 0/1/1/0. GPU
training is verified separately (a Kaggle T4 run learned the
same MLP). This is small-model territory, not LLM training.
`forge` emits CUDA dot/matmul kernels for CPU-thread
comparison, and `parallel_dot` / `parallel_matmul` run them on
CPU threads.

## 16. Safety, and what it costs

Safe mode is the default for a reason, and its cost is
measured, not asserted — see `docs/BENCHMARKS_SAFETY.md`. The
pure cost of checks (same C flags, safe versus fast): overflow
checks on recursion 2.7–3.7x, string bounds ~1.7x, double bounds
~1.4x, bounds on float work ~free, counter checks ~free. The
shipped fast mode's bigger wins come mostly from `-O3
-march=native` auto-vectorisation, not from check removal.
Safe mode also eliminates checks it can prove cannot fire
(duplicate checks within one statement, guard-proven overflow
checks, allocation-free string-index comparisons) — see
SPEC §6b — with no observable change: aborts and results are
identical.

## 17. What is not done

Honestly, and in one place: fluent generation; 1B or
distributed training; torch `.pt` import; full self-hosting;
big32 float division, ordered comparisons, printing, and
casts; PNG/JPEG loading; float printing beyond 6 significant
digits; regex groups and alternation; HTTP server beyond v1
limits (TLS, chunked bodies, keep-alive); macOS/Windows
binaries (investigated, not built); struct arrays and nested
arrays on WASM; struct arrays and string indexing on big32;
futures, results, and channels for concurrency; component-model
binary encoding for WASM; a public registry host; a debugger;
fuzzing.

## Appendix: example index

- `examples/tour/step*.fg` — the guided tour (see
  `docs/TOUR.md`).
- `examples/break_demo.fg`, `examples/break_gc_demo.fg` —
  break, including GC behaviour.
- `examples/str_index_demo.fg` — string indexing.
- `examples/struct_array_demo.fg`,
  `examples/struct_array_gc.fg` — arrays of structs.
- `examples/nested_array_demo.fg`,
  `examples/nested_array_gc.fg` — nested arrays.
- `examples/scope_demo.fg`, `examples/spawn_demo.fg` —
  concurrency.
- `examples/wasm/*.fg` — WASM programs, including
  `wit_add.fg` / `wit_list.fg` (WIT worlds beside them).
- `examples/apps/registry_server.fg` — the registry server
  in the language itself.
- `examples/apps/todo.fg` — a real todo CLI app.
- `examples/ml_train_xor.fg` — the learning MLP.
