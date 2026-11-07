# WASM strings and arrays (0.7.0)

The WASM backend (`forge_lang/codegen_wasm.py`) now
supports `str` and flat arrays (`[int]`, `[float]`,
`[bool]`, `[str]`) alongside the older int/float/bool
subset. This note documents the design and the
limits. Nothing here is planned — it is all built
and verified by the commands below.

## What works

- String literals, concatenation (`+`), `==` / `!=`,
  `len()`, and `print` / `println` of strings.
- Array literals, indexing, index assignment,
  `len()`, and `push()` with growth (realloc-by-copy).
- Strings and arrays as function parameters and
  return values, and `fail` / `assert` (they append
  the message to the stdout buffer, then trap).
- `print` / `println` of `int` (decimal) and `bool`
  (`"true"` / `"false"`), with one space between
  arguments, matching native output shape.

## Memory layout and representations

One memory (min 1 page, exported as `"memory"`),
growing on demand through a bump allocator (a
mutable i32 global holds the heap pointer, aligned
to 8 bytes). There is NO free and NO GC: allocations
inside a loop grow memory. That is the v2 trade-off.

- Stdout buffer: length (u32) at address 0, bytes at
  8..8199 (capacity 8192). Output past that is
  TRUNCATED — a documented limit, not a silent
  success.
- Static string blobs start at 8320, 8-aligned,
  each `[u32 length][utf-8 bytes]`. The heap follows
  the last blob.
- `str` is an i32 pointer to a length-prefixed blob.
  Literals live in the static area; concatenation
  allocates a new blob.
- An array is an i32 HANDLE: a pointer to a 4-byte
  cell holding the data pointer. The data block is
  `[u32 len][u32 cap][elements...]`. The handle is
  what makes `push` with growth work: on growth the
  helper allocates a bigger block, copies the
  elements, and rewrites the handle's cell, so the
  caller's variable sees the new block. Element
  sizes: int/float 8 bytes, bool/str 4 bytes.

## Semantic divergences from native (stated, not hidden)

- Because the handle is shared, `push` through a
  function parameter DOES reach the caller in WASM,
  while native `push` to a parameter does not.
  In-place index assignment behaves the same in
  both backends.
- Integer arithmetic wraps and division by zero
  traps, as before (same trade-off as big32).
- Array index out of bounds traps (`unreachable`)
  instead of aborting with a message, because the
  module has no host print for errors.
- No float printing and no array printing: both are
  compile errors. No structs, enums, match, spawn,
  extern, file I/O, `args`, http, or clock — same
  as the rest of the WASM subset.

## How to run and verify

The stock runner prints only `main()`'s return
value, so string output is read from the exported
memory. The demo's expected output is printed in
its header comment.

```sh
# Stock runner: prints main()'s return value (23).
python3 forge.py build --target wasm examples/wasm_strings_demo.fg -o /tmp/wasm_strings.wasm
node tools/run_wasm.mjs /tmp/wasm_strings.wasm
```

```sh
# Full output: instantiate in node, call main(),
# then read the stdout buffer (u32 length at 0,
# bytes at 8..8+len) from instance.exports.memory.
node -e '
import("node:fs").then(async ({ readFileSync }) => {
  const { instance } = await WebAssembly.instantiate(readFileSync("/tmp/wasm_strings.wasm"), {});
  const ret = instance.exports.main();
  const mem = new Uint8Array(instance.exports.memory.buffer);
  const len = new DataView(mem.buffer).getUint32(0, true);
  console.log(new TextDecoder().decode(mem.subarray(8, 8 + len)));
  console.log("returned:", ret.toString());
});'
```

Expected stdout buffer for the demo:

```text
hello qasida
len = 14
xs len = 5
xs[2] = 4
after push len = 6
xs[5] = 9
lily
true
sum = 23
```

## Why there is no needle in tests/run_tests.py

That suite has no WASM execution path at all (it
runs the native backend; its `--target` flag does
not exist there). Adding a needle would mean
building a new node-based harness inside the suite,
which is out of scope for this change. The demo is
verified manually with the commands above, and the
suite's formatter check still covers the demo file
(it must format idempotently like every example).
