# WIT-first WASM components

WIT is the WebAssembly Component Model's interface language. A
`.wit` file declares a *world* — the functions a component
exports — before the implementation is written. Qasida
supports that workflow for its WASM backend: write the world
first, then build with `--wit`, and the compiler checks the
program against the world before generating the module.

```
$ forge.py build prog.fg --target wasm --wit prog.wit
$ forge.py emit-wasm prog.fg --wit prog.wit -o prog.wasm
```

## Example

```wit
package qasida:demo;

world demo {
    export add: func(a: s64, b: s64) -> s64;
    export greet: func(name: string) -> string;
    export shout: func(msg: string);
}
```

```qasida
fn add(a: int, b: int) -> int { return a + b; }
fn greet(name: str) -> str { return "hi " + name; }
fn shout(msg: str) { println(msg); }
fn main() -> int { return add(40, 2); }
```

## Rules

- **The world is the contract.** Every non-`main` function in
  the program must be declared in the world's exports, and every
  world export must match its function exactly: same arity,
  same parameter types in order, same return type. A mismatch
  fails the build with a message naming the function and the
  difference. `main` is exempt: it is the entrypoint, not an
  interface function.
- **Parameter names are not compared.** WIT names and Qasida
  names may differ; positions and types must match.
- **Type mapping:** int -> s64, float -> f64, bool -> bool,
  str -> string, [T] -> list<T>. Structs, enums,
  Option/Result, and WIT types outside this mapping (u32, f32,
  option, result, tuples, ...) fail the check with a message
  naming the function and the type.
- **Imports are rejected.** The WASM backend emits a
  self-contained module with no imports, so a world that
  imports anything cannot be satisfied; the build fails rather
  than silently ignoring the import.
- **Supported WIT subset:** an optional `package` declaration,
  exactly one `world`, and `export`/`import` func declarations
  (with `//` and `/* */` comments). Interface blocks, `use`
  statements, type aliases, and interface references in a world
  fail with a clear message.
- **`--wit` requires `--target wasm`.** Passing it with another
  target fails instead of being silently ignored.

## What this is not

This checks the interface contract; it does not emit a
component-model binary. The generated module is still a core
module (the backend writes core modules directly, with no
component section and no canonical ABI lifting/lowering).
Real component binaries need a component runtime to verify
against, which is future work — the check here is deliberately
scoped to what can be verified today: the interface matches
the implementation, and the module runs.
