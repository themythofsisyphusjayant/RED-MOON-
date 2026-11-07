# Qasida — A Guided Tour

Ten steps, each a runnable program in `examples/tour/`. Run
any step with:

```
python3 forge.py run examples/tour/step01_hello.fg
```

Every output below was produced by running the step.

## 1. Hello

`examples/tour/step01_hello.fg`

```qasida
fn main() -> int {
    println("Hello, Qasida!");
    return 0;
}
```

Output:

```
Hello, Qasida!
```

`main` returns `int` (or nothing). `println` prints its
arguments separated by spaces, then a newline.

## 2. Variables and types

`examples/tour/step02_vars.fg`

```qasida
fn main() -> int {
    let name: str = "teju";
    let mut count: int = 0;
    count = count + 5;
    let pi: float = 3.14159;
    let ok: bool = true;
    println(name, count, pi, ok);
    return 0;
}
```

Output:

```
teju 5 3.14159 true
```

`let` is immutable; `let mut` is mutable. Function parameters
are immutable too — copy one into a `let mut` local before
assigning to it. There is no null and no implicit conversion:
convert explicitly with `x as float` or `x as int`.

## 3. Control flow

`examples/tour/step03_flow.fg`

```qasida
fn main() -> int {
    let mut total: int = 0;
    for v in [1, 2, 3, 4, 5] {
        if v == 4 {
            break;
        }
        total = total + v;
    }
    println("total =", total);
    return 0;
}
```

Output:

```
total = 6
```

`if` / `else if` / `else`, `while`, `for v in array`, and
`break` (innermost loop). There is no `continue` — restructure
with `if`/`break` instead. A non-void function must end its
body with a `return`; the compiler says so and tells you the
fix.

## 4. Functions

`examples/tour/step04_funcs.fg`

```qasida
fn twice(n: int) -> int {
    return n * 2;
}
fn main() -> int {
    println("twice 21 =", twice(21));
    return 0;
}
```

Output:

```
twice 21 = 42
```

One warning from experience: do not name a function `double`
(or `float`, `int`, `char`, ...). Those are C keywords, and
the compiler rejects them with "is a C keyword ... rename it"
rather than letting the C compiler fail cryptically.

## 5. Arrays

`examples/tour/step05_arrays.fg`

```qasida
fn main() -> int {
    let mut xs: [int] = [1, 2, 3];
    push(xs, 4);
    println("len =", len(xs), "last =", xs[3]);
    return 0;
}
```

Output:

```
len = 4 last = 4
```

Arrays are `[T]`, indexed from 0, bounds-checked in safe mode
(the default). `push` appends; `len` gives the length. Arrays
of structs and nested arrays (`[[int]]` matrices) work too —
see `examples/struct_array_demo.fg` and
`examples/nested_array_demo.fg`.

## 6. Strings

`examples/tour/step06_strings.fg`

```qasida
fn main() -> int {
    let s: str = "banana";
    println(s[0], s[1], s[2]);
    println("upper check:", s[1] == "a");
    return 0;
}
```

Output:

```
b a n
upper check: true
```

`s[i]` is a 1-character string (byte indexing), bounds-checked
in safe mode. Strings are immutable: `s[i] = ...` is a compile
error. String builtins: `split`, `join`, `substr`, `trim`,
`starts_with`, `ends_with`; strings support `==`/`!=` only
(no `<` ordering).

## 7. Structs

`examples/tour/step07_structs.fg`

```qasida
struct Point {
    x: int;
    y: int;
}
fn main() -> int {
    let p: Point = Point { x: 3, y: 4 };
    println("p =", p.x, p.y);
    return 0;
}
```

Output:

```
p = 3 4
```

Field definitions end with `;`. A struct containing another
struct must be defined in the same file, after the inner one.

## 8. Enums and match

`examples/tour/step08_enums.fg`

```qasida
enum Color { Red, Green, Blue }
fn name(c: Color) -> str {
    let mut s: str = "";
    match c {
        Red => { s = "red"; },
        Green => { s = "green"; },
        Blue => { s = "blue"; },
        _ => { s = "other"; },
    }
    return s;
}
fn main() -> int {
    println(name(Green));
    return 0;
}
```

Output:

```
green
```

`match` is exhaustive: miss a variant and the compiler lists
exactly which ones are missing. Match arms are triples —
pattern, optional binding, body. `Option`/`Result` and `?`
work the same way; see `examples/option_result_demo.fg`.

## 9. Structured concurrency

`examples/tour/step09_scope.fg`

```qasida
fn worker(n: int) {
    println("worker done", n);
}
fn main() -> int {
    scope {
        spawn worker(1);
        spawn worker(2);
    }
    println("after scope");
    return 0;
}
```

Output:

```
worker done 1
worker done 2
after scope
```

`spawn` starts a thread for a void function taking 0 or 1 int
argument. A `scope` block joins every task spawned inside it —
directly or by functions called from inside it — at the
closing brace, and on any `return` or `break` that leaves it.
So "after scope" always prints after both workers finish. Tasks
spawned outside any scope are joined when `main` returns.

## 10. WebAssembly

`examples/tour/step10_wasm.fg`

```qasida
fn add(a: int, b: int) -> int {
    return a + b;
}
fn main() -> int {
    return add(40, 2);
}
```

```console
$ python3 forge.py emit-wasm examples/tour/step10_wasm.fg -o step10.wasm
built wasm: step10.wasm (1227 bytes)
$ node tools/run_wasm.mjs step10.wasm
42
```

The WASM backend writes a real `.wasm` binary directly (no
toolchain needed) for a subset of the language: int, float,
bool, str, arrays, functions, recursion, print. It wraps on
integer overflow and traps on division by zero and out-of-bounds
indexing — the documented trade-off versus safe mode's readable
aborts. Declare the interface first with WIT
(`--wit prog.wit`); see `docs/WIT.md`.

## Where next

- The full reference: `docs/BOOK.md`, `SPEC_V2.md`.
- Packages: `qasida pkg init / publish / add` — see
  `docs/ECOSYSTEM.md` (30 seed packages).
- The HTTP server, ML stack, and big32 RISC-V backend: also in
  `docs/ECOSYSTEM.md`.
- Safe-mode cost, measured: `docs/BENCHMARKS_SAFETY.md`.
- Errors that end with a fix: try misspelling a variable — the
  compiler suggests the name you meant.
