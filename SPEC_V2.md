# Qasida Specification

## 1. Types

`int` (signed 64-bit), `float` (64-bit double), `bool`, `str`,
`void` (function return only), and `[T]` dynamic arrays where `T`
is `int`, `float`, `bool`, `str`, or a struct type, and arrays
nest: `[[int]]` matrices work on native. There is no null.

## 2. Functions, variables, control flow

```
fn name(a: int, b: [float]) -> float { ... }
let x: int = 5;          // immutable
let mut y = 10;          // mutable, type inferred
let xs: [float] = [];    // empty array needs an annotation
```

Statements: `let`, assignment (`x = ...`, `a[i] = ...`), `if` /
`else if` / `else`, `while`, `for v in array { ... }`, `break`,
`return`, bare blocks, `scope` blocks (below). Conditions must be
`bool`. A non-void function must end its body with a `return`.
`fn main()` takes no arguments and returns `int` or nothing.

### 2b. Structured concurrency: `scope`

`spawn worker(1);` starts a thread for a void function taking 0
or 1 int argument, and `main` joins all spawned threads before
returning. A `scope` block gives that join a lexical boundary:

```
scope {
    spawn worker(1);
    spawn worker(2);
}
println("after scope");   // both workers have finished here
```

At the closing brace the scope joins every task spawned while
it was open — directly, or transitively by functions called from
inside it. A `return` or `break` that leaves the scope joins
first, so no task outlives the block that spawned it. Scopes
nest; an inner scope's tasks are joined by the inner scope, and
the outer scope's join skips threads already joined. Tasks
spawned outside any scope keep the old behaviour: joined at
`main`'s return.

What a scope does NOT do: it returns no results (spawned
functions are void, and their return values are discarded), it
does not cancel a hung task (a scope that waits on a task that
never finishes waits forever, like any join), and it does not
propagate a worker's failure beyond `fail()`'s process abort.
Futures, results, and channels are future work. `scope` is not
a reserved word: it is recognised only as `scope` followed by
`{` at statement position, so `scope` still works as an ordinary
variable name. On WASM and big32, where threads are not
supported, a scope block runs as a plain block and a `spawn`
inside it fails as before.

## 3. Expressions

Precedence: `||` -> `&&` -> `== !=` -> `< <= > >=` -> `+ -` ->
`* / %` -> unary -> postfix (`a[i]`, `x as float`) -> primary.

String indexing: `s[i]` returns a 1-character string (byte `i` of
`s`). Out of bounds aborts in safe mode ("string index out of
bounds"); fast mode skips the check. Strings are immutable:
`s[i] = ...` is a compile error. Not yet on big32, which has no
runtime string allocation and reports a clear error instead.

* Arithmetic: matching `int` or `float` operands, except `str + str`
  (concatenation) and `int % int`. Integer arithmetic is checked
  in safe mode (overflow, division/modulo by zero abort cleanly);
  in fast mode it is unchecked, like C.
* Comparison and equality: matching numeric operands, plus `str`
  equality by contents.
* Logic: `&&`, `||` on `bool`; unary `-` on numeric, `!` on `bool`.
* Casts: `int as float` and `float as int` (truncation) only.
* Array literals: `[1, 2, 3]`, `[1.0, 2.5]`; all elements must
  have the same type. Arrays are shared by reference on assignment,
  like Python lists: assigning an array does not copy its elements.
  Nested arrays share the same way: `m[i]` is a shared row, so
  `let row = m[i]; row[j] = v;` mutates the matrix, and `m[i][j] = v`
  assigns through it.

## 4. Builtins

Statement-only: `print(...)`, `println(...)`, `push(array, value)`,
`fail("message")` (prints to stderr and exits 1).

Expression: `len(str or array) -> int`, `range(n: int) -> [int]`
(0..n-1), `clock_micros() -> int` (monotonic microseconds),
`sqrt/exp/log(float) -> float`, `pow(float, float) -> float`,
`abs(int) -> int`, `read_file(path: str) -> str` (fails if the file
cannot be read), `write_file(path: str, content: str) -> bool`
(true on success), `args() -> [str]` (command-line arguments after
the program name; pass them with `forge.py run file.fg -- a b`),
`parse_int(str) -> int` (fails on non-integer input).

## 4b. Structs (added in Phase C, 26 Oct 2026)

```
struct Point {
    x: float;
    y: float;
}
let p: Point = Point { x: 0.0, y: 0.0 };
let mut q: Point = Point { x: 3.0, y: 4.0 };
q.x = 6.0;
println("distance =", distance(p, q));
```

Rules: every field must be supplied exactly once in a literal,
field types must match, field access requires a struct value,
and field assignment requires the outermost variable to be
`let mut`. Structs can be function parameters and return values
(by value). Arrays of structs work on native: `xs[i]` returns an
owned copy, `xs[i].field` reads the field directly, `push` and
index assignment work, and freeing an array frees its elements'
owned fields. Recursive structs are rejected for now, and struct
arrays are not yet on WASM or big32 (clear errors there). Parser note: `Name { field: value }` is only treated as
a struct literal when the brace is followed by `field:` or `}` —
so `for v in xs {` and `if x {` still parse as blocks.

## 5. Imports and the standard library

```
import "ml.fg";
```

Imports are resolved relative to the importing file, then the
current directory, then `forge_lang/stdlib/`. `forge_lang/stdlib/ml.fg` provides `dot`,
`mean`, `relu`, `sigmoid`, and `matmul` (flat row-major matrices).

## 6. Modes and compilation

Forge -> C -> `cc` -> native binary, with `-lm` linked.

* Safe mode (default): `-O2`, checked int arithmetic, bounds-checked
  indexing, readable runtime errors.
* Fast mode (`--mode fast`): `-O3 -march=native`, unchecked
  arithmetic and indexing. The binary is less portable and can
  wrap, crash, or read out of bounds on bad input. Use it only for
  hot code you have already validated in safe mode.

### 6b. Safe-mode check elimination (native backend only)

Safe mode still emits every check that could fire — but it skips
checks it can prove cannot fire. Nothing observable changes: a
program that aborts in safe mode without elimination aborts with
the same message with elimination, and results are identical.
Three eliminations, all in the native code generator:

* Duplicate checks within one statement: `xs[i] * 3 + xs[i] % 7`
  checks `xs[i]` once; the repeat uses the unchecked access.
  The cache is per-statement and is cleared by any call (a call
  can mutate shared arrays through its parameters) and by any
  statement boundary, and only pure (call-free) index and operand
  expressions are cached. The same rule covers nested arrays,
  struct arrays, string indexes, field reads on struct arrays,
  and repeated identical int operations.
* Guard intervals: after `if n < 2 { return n; }`, the rest of
  the function knows `n >= 2`, so `n - 1` and `n - 2` need no
  overflow check — but `n + 1` still does, and a sum of two
  call results still does. Facts come only from var-vs-literal
  comparisons, are narrowed by later facts on the same path,
  joined across if-arms by hull (never by intersection, which
  would be unsound for assignments on one arm), and are cleared
  around loops (a fact from before a loop may be stale by the
  second iteration) and after matches. Assignments refresh or
  drop the variable's facts; `let` bindings in a branch never
  leak into the join.
* String-index comparisons: `s[i] == "a"` and `s[i] == s[j]`
  compare bytes directly instead of allocating a fresh 1-char
  string and calling strcmp — but the bounds check is still
  emitted in safe mode, so an out-of-bounds index aborts exactly
  as `forge_str_at` would. The literal must be exactly one byte;
  a multi-byte character falls back to the generic path.

WASM and big32 backends keep every check; elimination is a
native-codegen optimization only. Measured cost of the remaining
checks: see docs/BENCHMARKS_SAFETY.md.

## 7. What v2 deliberately lacks (next phases)

Generics (which `Option`/`Result` depend on), concurrency
(channels/actors), GPU kernels, Python interop, a package manager,
a formatter, and an LSP. Array and string values are not yet freed
(GC is the Phase B memory-manager item). Structs, file I/O, CLI
args, and `qasida test` are DONE (Phase C, 26 Oct 2026). Claiming
v2 "combines C++, Mojo, and Python" means it combines their
*approach* — native speed, Python-like ML syntax, Mojo-like
compiled kernels for small models — not their full ecosystems,
libraries, or GPU stacks.
