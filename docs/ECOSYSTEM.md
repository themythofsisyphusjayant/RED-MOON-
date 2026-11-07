# Qasida ecosystem (formerly Forge)

This is the complete tooling around the Forge language, in one
place. Everything below is implemented in this repo, not planned.

## Compiler

```
python3 forge.py check <file.fg> [--mode safe|fast]
python3 forge.py build <file.fg> [-o out] [--mode safe|fast]
python3 forge.py run   <file.fg> [--mode safe|fast] [-- args...]
python3 forge.py emit  <file.fg>
python3 forge.py test
```

Safe mode (default) checks integer arithmetic and array bounds;
fast mode is `-O3 -march=native`, unchecked, for hot code you have
already validated in safe mode.

## Package manager — `qasida pkg`

```
qasida pkg init [name]     # forge.toml + src/main.fg + tests/ + README
qasida pkg add <path>      # vendor another package into vendor/<name>/
qasida pkg build           # src/main.fg -> build/<name>
qasida pkg run [-- args]   # build, then run
qasida pkg test            # every tests/*.fg must exit 0
qasida pkg list            # name, version, dependencies
```

Dependencies are vendored (copied), not downloaded, so builds
never need a network or a registry. Import a vendored file with
a path from the package root: `import "vendor/stats/stats.fg";`.

See `examples/ecosystem/word_stats.fg` for a package-style program
that uses the stdlib, file I/O, and CLI args together.

## Formatter — `qasida fmt`

```
qasida fmt <file.fg>          # rewrite in canonical style, in place
qasida fmt <file.fg> --check  # exit 1 if the file would change
```

The formatter parses the file and re-emits it (4-space indent,
`else if` chains kept as chains, right-operand parentheses kept
where they matter for integer division and float rounding). It is
idempotent: formatting formatted code gives the same text.

## Language server — `qasida lsp`

```
python3 forge.py lsp
```

A stdio LSP server: `initialize`, full-sync `didOpen`/`didChange`
diagnostics from the real Forge checker, completion for keywords,
builtins, and function/struct names in the open document,
`shutdown`/`exit`. The full VS Code extension (grammar, snippets,
language configuration, and a dependency-free LSP client) is in
`editors/vscode/qasida/`; the old grammar-only extension stays in
`editors/vscode/forge/`. Point any LSP client at the command above
for diagnostics that can never drift from `qasida check`.

## REPL — `qasida repl`

```
python3 forge.py repl
forge> 1 + 2
3
forge> let x: int = 40;
forge> x + 2
42
```

`let` definitions are kept and reused; a definition that fails
to check is not kept. Commands: `:help`, `:defs`, `:reset`, `:quit`.

## Standard library

- `forge_lang/stdlib/ml.fg` — dot, mean, relu, sigmoid, matmul
- `forge_lang/stdlib/strings.fg` — repeat_str, word_count, csv_fields,
  lines_of, is_blank (on top of the split/join/substr/trim builtins)
- `forge_lang/stdlib/stats.fg` — sum_float, min_float, max_float, variance,
  stddev, median (median sorts a copy, never the caller's array)

Builtins: print/println, push, fail, len, range, clock_micros,
sqrt/exp/log/pow/abs, read_file/write_file, args, parse_int,
split/join/substr/trim/starts_with/ends_with.

## CI

`.github/workflows/ci.yml` runs `qasida test`, a formatter check
over examples and stdlib, and the ecosystem example on every push
and pull request.

## New in the "build everything" pass (26 Oct 2026)

- **Enums + match:** `enum Color { Red, Green, Blue }`, exhaustive
  `match` with a trailing `_` wildcard arm.
- **Concurrency:** `spawn worker(1);` — threads (pthreads) for
  void functions taking 0 or 1 int argument; main joins them at
  the end (and before any return from main). `scope { ... }`
  joins every task spawned inside it (directly or transitively)
  at the closing brace, and on any `return` or `break` that
  leaves the scope — no task outlives its block.
- **C FFI:** `extern fn puts(s: str) -> int;` — call real C
  functions; str is `const char *`, int is C `int` in the
  declaration, so standard-library functions work.
- **HTTP:** `http_get(url) -> str` — HTTP only, no TLS yet; the
  body is returned, headers are stripped. Tested against a local
  HTTP server.
- **Collections + JSON:** `forge_lang/stdlib/map.fg` (str->int map, put
  returns the updated map) and `forge_lang/stdlib/json.fg` (flat string
  objects only, documented as such).
- **Tests:** `assert(condition, "message")` as a statement builtin.
- **Docs:** `qasida doc <file.fg>` — Markdown from // comments
  above structs, enums, and functions.
- **Lockfile:** `qasida pkg lock` writes `forge.lock` with sha256
  of every vendored file; `qasida pkg verify` detects changes
  (tested: tampering a vendored file is reported as MISMATCH).

## New in the "do it then" pass (26 Oct 2026)

- **Generics:** `fn identity<T>(x: T) -> T`, `struct Option<T>`,
  `struct Result<T, E>`, `struct Pair<T, U>` — monomorphised
  (each concrete use gets its own C function/struct, no runtime
  cost). Generic functions are inferred from call arguments;
  generic structs are inferred from literal fields. Limitations:
  no generic enums yet, no `?` sugar (check `.ok`/`.present`
  explicitly), a generic function cannot be called with an
  abstract type from another generic function, and arrays of
  generic structs are not supported.
- **Option/Result stdlib:** `forge_lang/stdlib/option.fg` (`opt_some`,
  `opt_value_or`; none is a literal with a dummy value, because
  Forge has no null) and `forge_lang/stdlib/result.fg` (`result_value_or`).
- **TLS:** `http_get` now handles `https://` too, with
  certificate verification on (OpenSSL, SNI, default verify
  paths). Tested against a local TLS server with a private CA
  (via `SSL_CERT_FILE`): body "hello https world". A real bug
  found in testing: the HTTP/HTTPS helpers only tried the first
  addrinfo result, so `localhost` (which resolves to ::1 first)
  failed against an IPv4-only server — both helpers now loop
  over all addrinfo results. Linking falls back without `-lssl`
  if the machine lacks libssl (programs that never call
  `http_get` still build).
- **TLS via proxy:** `https://` also works through a plain HTTP
  proxy: `https_proxy` / `HTTPS_PROXY` (`http://[user[:pass]@]host[:port]`,
  port defaults to 8080) sends `CONNECT` before the TLS handshake;
  `no_proxy` / `NO_PROXY` bypasses it. Tested end to end with a
  local CONNECT proxy + local TLS server (`tests/test_proxy_connect.py`,
  6/6: direct, via proxy, bypass, refusal, auth, non-http scheme
  ignored). Plain `http://` stays direct; WASM/big32 unaffected.
- **Local registry:** `qasida pkg publish` copies a package into
  `$FORGE_REGISTRY` (default `~/.forge_registry`) as
  `<name>/<version>/`, and `qasida pkg add name@version` vendors
  it. Tested end to end (quad 7 = 28). This is a local registry,
  not a hosted server.
- **Tiny DB stdlib:** `forge_lang/stdlib/db.fg` — a tab-separated text
  key-value store (str -> str) with serialise/parse, to pair
  with `write_file`/`read_file`. NOT SQL, NOT SQLite, and values
  must not contain tabs/newlines (no escaping yet).
- **big32 backend (landed in the workspace 26 Oct 11:53, verified
  here):** `qasida emit-big32` / `qasida build --target big32`
  generate RV32IMAC assembly for the big32 v7 CPU (see
  `forge_lang/codegen_rv.py`, `examples/big32/`). Emit and
  assemble to .hex verified (sum.fg -> .hex); the Verilog
  simulation test needs `iverilog`, which is not installed in
  this VM, so it could not be run here.

## New in the "keep going" pass (26 Oct 2026)

- **`?` operator:** `let v: int = get_opt(ok)?;` unwraps an
  Option/Result, or returns early from the current function
  with the None/error value. Works when the function's return
  type is the same Option/Result type, or a Result/Option with
  the same error type and a scalar value type. Tested:
  `opt ok = 43`, `opt none present = false`,
  `calc error = div by zero` (the second divide fails, and the
  error propagates without an explicit if).
- **Generic enums with payloads:** `enum OptionE<T> { Some(T), None }`,
  `enum ResultE<T, E> { Ok(T), Err(E) }`, matched with bindings
  (`Some(v) => { ... }`). Payload enums compile to a C struct
  with a tag and a union, one struct per concrete type.
  No-payload variants of a generic enum are written `None()`
  and get their type from the annotation/return/argument type;
  a variant with no type context is a clear error, not a
  guess. Old non-payload enums (`enum Color { Red, ... }`)
  still work unchanged, and a no-payload variant of a
  non-generic payload enum can be written bare.
  Limitation: a variant takes at most one payload in v1.
- **Table DB stdlib:** `forge_lang/stdlib/table.fg` — a tiny relational
  table (flattened rows, insert/select by column value).
  NOT SQL (no SQL parser yet), and not SQLite.
  Tested: 3 rows, select city=Gorakhpur -> 2 rows,
  first=jayant, second=teju.

## New in the "then do it" pass (26 Oct 2026)

- **SQL parser:** `forge_lang/stdlib/sql.fg` — `sql_query(table, query)`
  with `SELECT name, city FROM t WHERE city = 'Gorakhpur'`,
  `SELECT * FROM t`, and numeric `WHERE age > '20'`.
  Tested: Gorakhpur = 2 (jayant, teju), older = 2, all = 3.
  A real bug found in testing: the parser forgot the table
  name token after FROM, so WHERE was ignored until the
  indices were fixed. NOT full SQL: no JOIN, ORDER BY,
  INSERT/UPDATE, and string `<`/`>` need integer values
  (Forge has no char codes for string ordering).
- **Hosted registry:** `forge_lang/registry_server.py` — a
  simple HTTP server (`qasida pkg serve --dir D --port P`,
  no auth, run it on your own machine/trusted network) plus
  `qasida pkg publish-remote <url>` and
  `qasida pkg add-remote <url> name@version`.
  Tested end to end on localhost: publish hostlib, add-remote
  into another package, septuple 6 = 42.
- **WASM backend:** `forge_lang/codegen_wasm.py` —
  `qasida emit-wasm` / `qasida build --target wasm` write a
  real .wasm binary directly (no clang/wasm-ld needed),
  run with node (`tools/run_wasm.mjs out.wasm`).
  Subset v1: int (i64), bool (i32), void, functions,
  let/assign, if/else, while, return, calls, recursion.
  Tested: sum 1..10 = 55, fib(10) = 55, both via node.
  Two real bugs found in testing: the i64 comparison opcode
  table was off by one (gt/le/ge were actually gt_u/le_u/ge_u
  neighbours) and integer neg was written as div_u — both
  fixed, and WASM arithmetic wraps (like big32, unlike Forge
  safe mode). NOT supported in v1: float, str, arrays,
  structs, enums, match, spawn, print, file I/O.
- **GC v1 for strings:** copy-on-call for string parameters
  (so a callee owns its parameter), free-on-reassign for
  owned string locals, free-on-return for owned string
  locals, with scope tracking so a return never frees an
  out-of-scope variable, and `alloc_count()`/`free_count()`
  counters. Tested: a 100-iteration reassign loop gives
  allocs = 103, frees = 101, leaving exactly 2 live strings
  (the current value and the greeting) — without this, all
  103 would leak. A real bug found in testing: Assign freed
  the old string before evaluating the new one, so
  `out = out + x` read freed memory — Assign now evaluates
  into a temp first. NOT a full GC yet: arrays, struct
  fields, and array elements are still never freed, and
  string temporaries from concat/helpers are counted only
  through the copy path.

## New in the "do it that also" pass (26 Oct 2026)

- **Parallel kernels:** `parallel_dot(a, b)` and
  `parallel_matmul(a, b, n)` — GPU-style kernels (work split
  into blocks, one pthread per block) that run on CPU threads
  here, because this VM has no GPU, no CUDA, and no OpenCL.
  Verified: dot = 70, matmul = 19 22 43 50, exactly matching
  the serial results. No speedup is claimed on this 2-core
  VM; the kernel shape and correctness are the deliverable,
  and a real GPU backend still needs GPU hardware.
- **Python interop:** `qasida build --shared lib.fg -o lib.so`
  compiles a Forge library with no main required, and
  `tools/forge_py.py` calls it from Python via ctypes
  (int/bool/float/str). Verified: add(40, 2) = 42,
  is_even(42) = True, greet("Jayant") = "hello Jayant".
  A real bug found: Forge frees string parameters on return,
  but ctypes passed a Python-owned buffer — the helper now
  mallocs string arguments so Forge can safely free them.
  Arrays/structs are not passed through this helper in v1.
- **Public registry discovery:** `qasida pkg list-remote <url>`
  lists every package and version on a registry, so a
  registry you run is discoverable, not just add-by-name.
  Verified: published hostlib@0.1.0, list-remote showed
  "hostlib 0.1.0". This is still a self-hosted server,
  not a centrally hosted service — "public" means anyone
  with your URL can discover and pull from it.
- **GC v2 for arrays:** array structs now carry a refcount
  pointer. Assignment shares, function calls gain a
  reference, struct fields gain a reference, and an array
  is freed only when its last owner goes away. Verified:
  a 100-iteration reassign loop gives arr allocs = 101,
  arr frees = 100 (1 live); a shared array survives its
  original variable's reassign (b = 4 5 after a = [9]);
  a struct-held array survives too (s.arr = 4 5 after
  b = [7]). Two real bugs found: array helpers were
  declared before forge_fail/forge_free_str, so forward
  declarations were added. NOT yet freed: struct variables
  themselves (their fields leak, as before, but they hold
  a reference so shared arrays are never freed under them),
  and array elements inside structs are not counted
  separately. Full suite still passes.

## New in the "do it then" pass (26 Oct 2026)

- **Struct GC:** struct variables now own their fields —
  str fields are deep-copied, array fields gain a reference,
  nested structs recurse — on Let, Assign, Call arguments,
  and Return, and are freed on reassign/return. Verified:
  a 100-iteration struct reassign loop gives str allocs =
  101, str frees = 100, arr allocs = 101, arr frees = 100;
  a shared struct survives its original's reassign
  (q = b 2 3 after p = c). Full suite still passes.
- **Python arrays/structs:** `tools/forge_py.py` now passes
  [int] arrays (as a C struct with malloc'd data/ref, which
  Forge frees on return) and simple structs (ctypes Structure,
  same field layout) to Forge shared libraries. Verified:
  sum_arr([1,2,3,4]) = 10, double_arr([1,2,3]) = [2,4,6],
  point_sum(Point(10,32)) = 42, make_point(3,4) = (3,4).
  Str fields in structs must be malloc'd, as for plain str
  arguments, because Forge frees them on return.
- **CUDA codegen:** `qasida emit-cuda` emits a .cu file with
  __global__ dot and matmul kernels, grid/block launches,
  and host code. Verified structurally (kernel signatures,
  <<<grid, block>>> launches, cudaMalloc calls) — NOT run,
  because this VM has no GPU and no nvcc. To run it, copy
  the .cu file to a CUDA GPU machine and compile with nvcc.
- **Centrally hosted static registry:** `tools/make_static_registry.py`
  converts a local registry into a static dir (packages.json
  + packages/<name>/<version>/<file>.fg) that can be pushed
  to GitHub and served by Pages, and `qasida pkg list-static`
  / `add-static <base_url>` discover and pull from it with
  no server code running. Verified end to end via a local
  HTTP server simulating Pages: static registry listed
  "hostlib 0.1.0", add-static vendored it into
  vendor/hostlib/. This is centrally hosted by GitHub
  Pages, but read-only for clients — publishing is via git
  push, not via POST, unlike the dynamic server above.

## New in the "finish the remaining 3" pass (26 Oct 2026)

- **Python [float]/[str] arrays + nested structs:** done.
  Verified: sum_float([1.5,2.5,3.0]) = 7.0,
  double_float([1.0,2.5]) = [2.0,5.0],
  join_str(["jayant","teju"]) = "jayant,teju",
  str-array round-trip = ["a","b"],
  outer_sum(Outer{Inner(10,32)}) = 42,
  make_outer(3,4,"hello") = (3,4,"hello").
  Str-array elements are malloc'd in Python and freed by
  Forge on return, exactly like plain str arguments.
- **CUDA execution:** VERIFIED ON A REAL GPU 26 Oct 2026.
  Kaggle GPU notebook `arshhdubeyy/forge-cuda-kernel` v2,
  2x Tesla T4 (15360 MiB each), driver 580.178.04, nvcc 12.8:
  cuda dot = 70.000000, cuda matmul = 19 22 43 50 — exactly
  matching the CPU-thread kernels, the serial code, and the
  `tools/simulate_cuda.py` simulation. The Kaggle token used
  for this run was supplied transiently for this session
  only and was not stored. This VM itself still has no GPU
  or nvcc, so the .cu file cannot run here — the verified
  run happened on Kaggle, and `examples/cuda/` now records
  it with the GPU, driver, and nvcc versions above.
- **Dynamic centrally hosted registry:** the server is now
  production-shaped — POST publishing with an optional Bearer
  token, immutable versions (re-publishing the same version
  returns 409), and a Dockerfile + deploy README in
  `registry/`. Verified end to end: publish without token
  -> 401, publish with token -> ok, re-publish -> 409,
  list-remote -> "hostlib 0.1.0", add-remote -> vendored.
  What is still not provided: a host. Central hosting means
  running that server on a VPS/Render/Fly host you control
  and sharing its URL — this repo gives the server and the
  deploy files, not the host itself.

## What is still not in the ecosystem

No CUDA execution on real GPU hardware (needs a GPU machine
or a GPU token you supply), no Python interop for generic
arrays/structs beyond the types above, and no registry
actually running on a public host (the server above is
ready to deploy, but no host is provisioned here). Those
are the next phases, in that order.

## 0.6.0 — the AI/ML + developer library layer

### The one unlock: imports dedupe

Before 0.6.0, the compiler included a shared import
once per import branch, so `nn.fg` + `tensor_autograd.fg`
(a Tensor defined twice) failed to compile. Libraries
had to avoid shared imports, which made them
uncombinable. The compiler now keeps a true visited
set (`forge_lang/compiler.py`, `load_program`), so a
file is included once no matter how many libraries
import it. `examples/import_dedup_demo.fg` is the
regression test: tensor training with nn's Adam in
one program.

### ML libraries added in 0.6.0

- `tensor_autograd.fg` gained 4 ops (17–20):
  maxpool2d, sigmoid, tanh, MSE loss. Every backward
  rule checked against finite differences
  (`examples/tensor_ops2_demo.fg`: sigmoid 6e-13,
  tanh 1e-11, maxpool routes exactly to argmax).
- `rnn.fg`: LSTM / GRU / plain RNN cells on the
  tensor tape. Cells return the tape and write new
  state ids into an `out` array by index assignment
  (the language's out-parameter idiom), and the new
  hidden state is also the tape's last node.
  `examples/rnn_demo.fg`: first-bit memory over 5
  steps, 0.44 -> 1.0 with nn's Adam.
- `cnn.fg`: im2col conv (first layer) + tape
  maxpool. `examples/cnn_demo.fg`: 8x8 cross-vs-
  border with noise, 0.5 -> 1.0.
- `ml_classical.fg`: logistic regression (tape +
  inline Adam), k-NN, k-means.
  `examples/ml_classical_demo.fg`: purity 1.0,
  knn 1.0, logreg 1.0.
- `preprocess.fg`: standardisation, min-max
  scaling, one-hot, deterministic splits, word
  vocab builder (split-based: the language has no
  string indexing).
- `metrics.fg`: accuracy, confusion matrix,
  precision/recall/F1, MSE/MAE/R2, perplexity.
- `csv.fg`: plain CSV load (no quoted commas —
  stated, not hidden) + label encoding.
  `examples/iris_pipeline_demo.fg` runs the full
  workflow on the real UCI Iris set (150 rows):
  CSV -> split -> standardise (train stats only)
  -> logreg -> test acc 0.933, macro F1 0.937.
- `tensor_checkpoint_demo.fg`: nn checkpoints
  round-trip a tensor model with loss diff 0.

### Developer libraries added in 0.6.0

- `test.fg`: check / check_eq_int / check_close /
  check_eq_str — print-on-failure, summed by the
  caller, quiet on success.
- `log.fg`: log_debug/info/warn/error + a leveled
  Logger struct.
- `cli.fg`: --flag, --opt value, --opt=value,
  positionals, float/int option parsing.
- `collections.fg`: IntStack, IntSet, StrSet
  (value-returning, so the push-doesn't-reach-
  caller rule never bites).
- All four exercised in `examples/dev_demo.fg`.

### Honest limits of this layer (0.6.0)

- Images/binary data: file I/O is text. No image
  loader, no binary reader — vision work uses
  generated or CSV data, not real photos.
- Conv stacking: `cnn_conv2d` takes raw image
  data; conv-on-conv needs a tape-native im2col
  op that does not exist yet. Weight gradients
  for the conv itself are exact.
- RNN horizon: from random init, the first-bit
  task at length 8 stalls at chance even with
  forget-bias init (lengths 3 and 5 reach 100%).
  Longer horizons need curriculum training.
- GPU training: kernels verified on a real T4
  (0.3.0), but the training loop itself
  (`examples/cuda/mlp_train.cu`) is code only.
- Checkpoints are 6-decimal text: float_to_fixed
  truncates, so save/load is exact only to 1e-6.

## 0.7.0 — "build everything open" (26 Oct 2026)

Every 0.6.0 limit above except GPU training and
text checkpoints is closed in 0.7.0, plus three
backend jumps:

- Images/binary data: CLOSED. `read_bytes` /
  `write_bytes` builtins; `forge_lang/stdlib/image.fg` loads
  PPM P3 and 24-bit BMP, grayscales, saves PPM P3.
  BMP == PPM verified on the same 2x2 image.
  PNG/JPEG still NOT supported (inflate/DCT).
- Conv stacking: CLOSED. Tape-native im2col
  (op 21) + `cnn_conv2d_tape`; two-conv net
  0.5 -> 1.0 at lr 0.01 (lr 0.05 oscillates —
  documented in the demo header).
- RNN horizon: CLOSED. Curriculum staging len 3
  -> 5 -> 8 with weight transfer: all 100%.
- Debugger: `forge.py build --debug` emits
  `#line` directives for main + imported files
  (readelf-verified); see docs/DEBUGGING.md.
- big32 structs: local structs as consecutive
  frame slots; model + Verilog verified.
- big32 soft-float v1: + - * in exact 27-bit
  integer arithmetic, round-to-nearest-even;
  12/12 demo + 60/60 randomized differential
  vs Python float32, model AND Verilog. No
  division, ordered comparisons, float printing,
  casts, or subnormal fidelity yet.
- WASM strings + arrays: see docs/WASM_STRINGS.md
  (byte-identical demo output vs native).
- Fuzzer: `tools/fuzz.py`, 50/50 OK default run,
  200/200 OK longer run (seeds 1000-1199),
  safe-vs-fast differential, no compiler bugs
  found.
- Big TinyStories run: 2000 stories, 150k words,
  vocab 2000, 153,744 params, held-out ppl
  2128.55 -> 651.44 — better, still NOT fluent
  (greedy loops, sampled is word salad).
- Correction: earlier "wasm + big32 suites passed"
  claims were wrong — run_tests.py ignores its
  --target flag, so those runs were native twice.
  The suite now has real big32 build checks and a
  node-based WASM output comparison.

### Honest limits of this layer (0.7.0)

- GPU training: kernels verified on a real T4
  (0.3.0); the training loop itself
  (`examples/cuda/mlp_train.cu`) is VERIFIED on a
  real T4 since 26 Oct 2026 (Kaggle notebook
  arshhdubeyy/forge-mlp-train v3, LR 5.0:
  epoch 1500 loss 0.001529, predictions
  0.028651 0.972222 0.967339 0.027646).
  LR 0.5 does not learn (v2: loss pinned at
  0.25); kernel.cu's own main() must be renamed
  at compile time or the link fails.
- Fluent generation: NOT achieved at 153k params
  / 150k words. Needs far more scale.
- Full self-hosting compiler: the front-end
  prototype (lexer + parser) exists; checker and
  codegen in Qasida do not.
- Public registry host, CI upload, repo rename,
  PyPI publish: all still blocked on the user's
  accounts/token scope, as before.
- Checkpoints are 6-decimal text: float_to_fixed
  truncates, so save/load is exact only to 1e-6.

## 1.0.0 — market-ready layer (26 Oct 2026)

- Stability promise: docs/STABILITY.md. 1.x adds, never breaks.
- Live playground: web/playground.html — real compiler under
  Pyodide, real WebAssembly runs, no install. Four verified
  examples. Browser end-to-end open still pending (needs a browser).
- HTTP server: six builtins + forge_lang/stdlib/http_server.fg + routing demo,
  verified live with curl (200/200/404, correct bodies, clean
  shutdown). Limits: one request per connection, single 8191-byte
  read, no TLS, no chunked bodies, IPv4 only.
- Killer app: examples/apps/registry_server.fg — a package
  registry server written in Qasida itself, speaking the same
  HTTP API as the Python reference server, so the real `forge
  pkg publish-remote` / `add-remote` clients work against it.
  Verified live: publish (incl. 401/409), list, versions, files,
  byte-exact file round-trip, and a fresh consumer installing
  and running two packages. Flat on-disk layout + index file
  (no directory-listing builtin); publish order, not sorted;
  ASCII-only publish bodies. HTTP status reasons gained 401
  Unauthorized and 409 Conflict.
- Regex: forge_lang/stdlib/regex.fg (36-check demo passes). No groups or
  alternation — those characters are literal in v1.
- Packages: packages/ — now 30 boring packages at 0.1.0 each: the
  original seven (units, money, geometry, interest, roman, bases,
  dice) plus percentages, loans, bmi, colors, sorting, search,
  primes, factors, statistics, grades, tax, cooking, budget,
  checks, morse, textstats, speed, data, angle, fractions,
  vectors, matrices, polynomials. Every package has a demo with
  self-checks and a smoke test (60/60 pass); publish of all 30,
  list, local add, and HTTP add-remote verified against a local
  registry server with a fresh consumer. Public hosting still
  needs the maintainer's account.
- VS Code extension: editors/vscode/forge/forge-1.0.0.vsix,
  packaged and contents-verified. Marketplace publish still needs
  the maintainer's publisher account.
- Benchmarks: docs/BENCHMARKS_VS.md — Qasida vs Python/Go/Rust/C
  on identical tasks, results verified equal. ~31x/49x/259x vs
  Python; in the compiled cluster with Go/Rust/C.
  docs/BENCHMARKS_SAFETY.md — the cost of safety: safe vs fast
  mode, pure check cost ~1.0x (bounds/counter) to ~1.7x (string
  bounds) to 2.7-3.7x (overflow-check-heavy recursion); shipped
  fast-mode wins are mostly -O3/-march=native, not check removal.
- Still blocked on accounts/token scope, as before: public registry
  host, CI upload, repo rename, PyPI publish, Marketplace publish.
  Still not done: fluent generation, full self-hosting compiler,
  big32 float division/comparisons/printing/casts, PNG/JPEG.
