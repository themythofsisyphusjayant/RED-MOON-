![Jal Pari header](https://capsule-render.vercel.app/api?type=waving&color=gradient&height=180&section=header&text=The%20Jal%20Pari%20Language&fontSize=42&animation=fadeIn)

![Typing](https://readme-typing-svg.demolab.com?font=Fira+Code&pause=1000&color=F472B6&width=650&lines=Safe.+Simple.+Natively+fast.;No+null.+No+silent+overflow.;Now+building+100%2B+libraries+in+Jal+Pari)

# 🧜‍♀️ The Jal Pari Language — a production-oriented language, rebuilt from research

> **Dedicated to Tejaswini — Jal Pari.**
> See [DEDICATION.md](DEDICATION.md). Formerly called Forge v2;
> technical names (`forge.py`, `forge_lang`, `.fg` files) are unchanged
> for compatibility, so existing programs keep working.

> **Safe. Simple. Natively fast.**
> Static types, no null, immutable by default, checked arithmetic —
> with C++-style latency and Mojo/Python-style ML ease, in one binary.

![Jal Pari](https://img.shields.io/badge/Jal_Pari-v1.4.0-pink)
![Native](https://img.shields.io/badge/compiled-native-blue)
![Safe mode](https://img.shields.io/badge/safe--mode-checked-green)
![Fast mode](https://img.shields.io/badge/fast--mode--O3-orange)
![Tests](https://img.shields.io/badge/tests-passing-brightgreen)

The Jal Pari Language is a statically typed language that compiles to native code.
It was restarted from scratch after a research pass over what people
are actually building in 2025–2026 — Zig, Mojo, Carbon, Gleam, Odin,
Hare, Roc, Vale/Valen, and others — and what developers praise and
complain about in Rust, Go, Zig, and Mojo. The conclusion that drives
it: **no single language has replaced Rust/Go/C, and the ones
gaining real production use have a narrow beachhead, not a promise
to be good at everything.** Its beachhead is safe, simple, fast
tools, CLIs, and small ML programs.

---

## 🌙 The 3D picture: what learning looks like in Forge

This is the loss surface for the linear-regression example in this
repo (`examples/ml_linear_regression.fg`, data `y = 2x + 1`).
Gradient descent walks down this bowl toward the star at `w = 2,
b = 1, loss = 0`. The surface is computed from that exact data;
the walk itself is a real Forge program (see the convergence curve
below).

![3D loss surface](figures/loss_3d.png)

---

## ⚡ Microsecond latency, measured — not claimed

A dot product is the unit of ML work. This is real Forge timing
(`examples/benchmark_scaling.fg`, safe mode, 100 repetitions each,
measured on this machine on 26 Oct 2026 — your numbers will vary):

| Vector size | Average time per dot |
|------------:|---------------------:|
| 1,000       | 1.03 µs |
| 5,000       | 5.98 µs |
| 10,000      | 10.67 µs |
| 20,000      | 21.59 µs |

![Dot-product scaling](figures/benchmark_scaling.png)

That is roughly **1 microsecond per 1,000 elements** — linear, as it
should be for contiguous arrays. A data-dependent loop of 1,000,000
array reads takes about **1.2 milliseconds** in the same run.

```sh
python3 forge.py run examples/benchmark.fg            # safe mode
python3 forge.py run examples/benchmark.fg --mode fast # -O3 -march=native, unchecked
```

Safe mode is the default: checked integer arithmetic and
bounds-checked indexing, aborting with a readable message instead
of wrapping or crashing. Fast mode is an explicit opt-in for hot
code you have already validated in safe mode.

---

## 🤖 ML in Forge: Python-like to write, native to run

### Linear regression, converging for real

`examples/ml_regression_trace.fg` prints `w` and `b` every 100
iterations. The true line is `y = 2x + 1`:

![Regression convergence](figures/regression_convergence.png)

Final result after 500 iterations (`examples/ml_linear_regression.fg`):

```
w = 2.0211  b = 0.923818
prediction for x=6: 13.0504
```

Close to the true `w = 2, b = 1, prediction = 13` — not exact, and
that honesty matters: 500 steps at learning rate 0.01 does not
finish the job, it gets close.

### A tiny MLP doing XOR

`examples/ml_mlp_xor.fg` uses hand-set sigmoid weights (no Python
runtime, no GPU framework) and produces:

```
xor 0 0 = 0 (raw 4.54391e-05)
xor 0 1 = 1 (raw 0.999955)
xor 1 0 = 1 (raw 0.999955)
xor 1 1 = 0 (raw 4.54391e-05)
```

![XOR heatmap](figures/xor_heatmap.png)

### Matrix multiply

```sh
python3 forge.py run examples/matrix.fg
# 58 64 139 154
# dot = 217
```

---

## 🧠 Mojo-level ML stack (0.2.0): tensors, autograd, tiny GPT

Not a promise of LLMs — a small-model stack that actually trains:

- **Tensors** (`stdlib/tensor.fg`): shape + flat data, matmul,
  softmax, GELU. **Autograd** (`stdlib/autograd.fg`): a real
  reverse-mode tape — no hand-written backward code.
- **Transformer blocks** (`stdlib/nn.fg`): Linear, LayerNorm,
  causal attention, MLP, Adam/AdamW, schedules, clipping,
  checkpoints, int8 quantization, sampling.
- **Tiny GPT** (`examples/tiny_gpt.fg`): 1 block, 1 head, 776
  params, trained by autograd on one sentence —
  loss **2.274 → 0.360** in ~5 seconds. Generation loops or
  rambles (honest for this size); the training is the proof.
 - **Inference** (`stdlib/inference.fg`): KV-cache steps match a
  full forward exactly (diff 0). **GPU**: fused attention /
  LayerNorm / embedding / fp16 kernels in `examples/cuda/`,
  verified on Kaggle Tesla T4 (dot 70, attention 0.330/0.670).
- **Scaled GPT** (`examples/gpt_scaled.fg`): 2 blocks, 2 heads,
  5,200 params, held-out perplexity 58.1 → 53.9.
- **TinyStories word GPT** (`examples/gpt_tinystories.fg`): real
  TinyStories data (200 stories, 24,000 words, 500-word vocab),
  12,608 params, held-out perplexity 1078.88 → 247.39. Sampled
  output is real words in salad order — not fluent sentences.
- **0.5.0 engine batch**: tape freeing (loop-body locals now
  freed — the 0.4.0 OOM leak is gone), tensor autograd
  (100 nodes per forward vs 221,844 scalar; gradients
  checked to ~1e-9), KV-cache for the gpt2 layout
  (diff 4.44e-16 vs full forward), scaled TinyStories
  (49,664 params, perplexity 1118.87 → 189.13).
  See CHANGELOG.md and docs/BENCHMARKS.md.

```sh
python3 forge.py run examples/tiny_gpt.fg      # trains + generates
python3 forge.py run examples/inference_demo.fg # KV-cache proof
python3 tools/simulate_cuda.py                  # CUDA mirrors
```

## 🧭 How a Forge program becomes a binary

```mermaid
flowchart LR
    A[Forge source<br/>.fg] --> B[Lexer + Parser<br/>AST]
    B --> C[Type checker<br/>no null, no coercion,<br/>immutable by default]
    C --> D[C codegen<br/>safe or fast mode]
    D --> E[cc -O2 / -O3<br/>native binary]
    E --> F[Run anywhere<br/>no runtime to install]
```

---

## 🚀 Quickstart

**New to programming? Start here, in simple words:**
[docs/HIGH_SCHOOL_GUIDE.md](docs/HIGH_SCHOOL_GUIDE.md) — steps to run
Jal Pari, what each line means, and where it is used in real life.

Requirements: Python 3 and a C compiler (`cc` / `gcc`).

**Install (1.4.0):**

```sh
git clone https://github.com/themythofsisyphusjayant/RED-MOON-
cd RED-MOON-
sh scripts/install.sh   # checks python3 + cc, installs jalpari to ~/.local/bin
jalpari --version       # The Jal Pari Language 1.4.0
```

`jalpari` is the new command name; `python3 forge.py` still works
exactly the same, for compatibility.

```sh
jalpari run examples/hello2.fg
jalpari run examples/matrix.fg
jalpari run examples/ml_linear_regression.fg
jalpari run examples/ml_mlp_xor.fg
jalpari run examples/benchmark_scaling.fg
jalpari build examples/benchmark.fg -o bench
python3 forge.py test   # all tests pass
```

See [CHANGELOG.md](CHANGELOG.md) for what is in 1.2.0 and what
is honestly not done yet.

## 🔴 Forge on big32 — your language, running on your own CPU

Forge now has a second backend: instead of C (x86), it can compile
straight to RISC-V assembly for **big32**, the 32-bit CPU in the
`BIG-32` repo. A Forge program compiled this way runs on big32 in
simulation — no x86, no C compiler in the middle. This is simulation
only, and it is a subset (see below); it is not Linux, and big32 is
not silicon.

```sh
python3 forge.py build --target big32 examples/big32/hello.fg -o out/hello
# -> out/hello.s (big32 assembly) + out/hello.hex (for the simulator)
python3 tests/run_big32_tests.py   # model + Verilog, compared with x86
```

How it works (see `forge_lang/codegen_rv.py` for the full contract):

- **Pipeline:** Forge source → existing lexer/parser → existing
  checker → existing type inference → new RISC-V code generator.
  The language is not rewritten; only the backend is new.
- **Calling convention:** args in a0–a7, return in a0, frame
  pointer s0, locals in a fixed 2048-byte frame addressed via s0
  (so sp may move for call spills). The callee saves ra + s0
  only; the caller spills every live temp register across a call,
  so recursion works (fib(10) is the proof).
- **Stack:** starts at 65532, grows down. Static data (strings,
  array slots) lives at 0x1000 and up, in the 64KB data memory.
- **UART runtime:** `print`/`println` map to UART TX — a store of
  each byte to 0x10000000. Integers go through a decimal routine
  (including the INT_MIN case, printed unsigned after the `-`
  sign); strings are null-terminated static data initialised by
  `_start` before `main`; booleans print as `true`/`false`.
- **Arrays:** a static slot per source site — first word is the
  length, then the elements. An array literal inside a loop
  re-initialises the same slot each iteration (a documented v1
  limitation, not a hidden one).
- **End of program:** `main`'s return (or falling off the end)
  becomes ECALL, which halts big32 (mtvec == 0 by default; with
  a `trap_handler` defined, the ending clears mtvec first, so it
  still halts instead of trapping — see below).
- **Freestanding + traps (27 Oct 2026):** `forge.py build
  --target big32 --freestanding` builds without any host OS, and
  the language now has raw memory (`peek32`/`poke32`), bitwise
  operators (`& | ^ << >> ~`), CSR builtins (`csr_read`/
  `csr_write`/`csr_set`/`csr_clear`, literal CSR numbers only),
  an `ecall` builtin (SBI-call primitive), and a `trap_handler`
  hook: define `fn trap_handler()` and `_start` points mtvec at
  a stub that saves all registers, calls it, restores, and
  `mret`s. The full roadmap is `docs/FREESTANDING.md` — this is
  the path to a bootable Jal Pari kernel, not just programs
  running on big32.

Supported on big32 (v1): `int` (32-bit here, not Forge's 64-bit
x86 int), `bool`, `str` literals/variables, `[int]`/`[bool]`/
`[str]` arrays, `let`/`assign`, `if`/`else`, `while`, `for` over
an array or over `range(n)`, functions/calls (≤ 8 args, recursion),
`return`, `print`/`println` of int/bool/str, `len` of an array or
a string, `assert`/`fail` (print, halt with a0 = 1), bitwise
operators, `peek32`/`poke32`, `csr_read`/`csr_write`/`csr_set`/
`csr_clear`, `ecall`, `trap_handler`, structs as locals/fields,
and `float` `+` `-` `*` only (soft-float v1, IEEE-754 single
precision).

NOT supported on big32 (v1), and the backend rejects them with a
clear error instead of silently miscompiling: `float` division,
ordered comparisons, printing, and int↔float casts; struct
parameters/returns and arrays of structs; enums/`match`,
`spawn`/threads, `extern`/FFI, file I/O, `args()`, HTTP, clock,
string concatenation/comparison, string indexing, `push` (no
dynamic allocation), generics, `Option`/`Result`, GC.
Arithmetic is native RISC-V, not Forge safe mode: it wraps on
overflow, div by zero gives -1, rem by zero gives the dividend.

Verified programs (`examples/big32/`, each run on x86, in the
big32 Python model, and in Icarus Verilog, with identical UART):

| Program | UART output |
|---|---|
| `hello.fg` | `hello from Forge on big32` / `forge + big32` |
| `sum.fg` | `sum = 55` |
| `fib.fg` | `fib = 55` (recursive, the call-spill proof) |
| `muldiv.fg` | `mul = 83810205`, `div = 14 rem = 2`, `neg = -42`, `flag = true false` |
| `loop_call.fg` | `total = 14`, `len = 5 xs[2] = 4` |
| `forge_os.fg` | Forge OS demo (below) |

### Forge OS demo — the full-stack program

`examples/big32/forge_os.fg` is a Forge program that boots on
big32, prints a banner, runs two apps, prints their results, and
halts via ECALL. It is an OS *demo* (a user program acting as an
OS), not a trap handler — the assembly kernel `programs/kernel.s`
in the big32 repo remains the real trap-handling supervisor:

```
forge OS on big32
boot ok
app_sum = 55
app_mul = 42
done
```

## ✍️ Language in 30 seconds

```forge
import "ml.fg";

fn main() -> int {
    let xs: [float] = [1.0, 2.0, 3.0];
    let mut total: float = 0.0;
    for v in xs {
        total = total + v;
    }
    println("mean =", mean(xs), "total =", total);
    let t0: int = clock_micros();
    let c: [float] = matmul(xs, xs, 1, 3, 1);
    println("micros =", clock_micros() - t0);
    return 0;
}
```

Types: `int` (64-bit), `float` (64-bit), `bool`, `str`, `[T]` arrays,
plus user-defined **structs** (see `examples/structs_point.fg`).

```forge
struct Point { x: float; y: float; }
let mut q: Point = Point { x: 3.0, y: 4.0 };
q.x = 6.0;
```

Casts are explicit: `x as float`, `y as int`. There is no null and
no implicit conversion.

Builtins (48): `print` / `println`, `push`, `fail`, `assert`,
`len`, `range`, `clock_micros`, `sqrt`, `exp`, `log`, `pow`,
`abs`, `read_file` / `write_file`, `read_bytes` /
`write_bytes`, `file_exists`, `read_line`, `args()`,
`parse_int`, `parse_float`, `split` / `join` / `substr` /
`trim` / `starts_with` / `ends_with`, `http_get` /
`http_listen` / `http_accept` / `http_read_request` /
`http_respond` / `http_respond_status` / `http_close`,
`parallel_dot` / `parallel_matmul`, `alloc_count` /
`free_count` / `arr_alloc_count` / `arr_free_count`,
`peek32` / `poke32`, `csr_read` / `csr_write` / `csr_set` /
`csr_clear`, `ecall`.
Run a program with arguments: `python3 forge.py run examples/file_and_args.fg -- out.txt`.
Run the test suite the Go way: `python3 forge.py test`.
Standard library (`stdlib/ml.fg`, `import "ml.fg"`): `dot`, `mean`,
`relu`, `sigmoid`, `matmul` (flat row-major matrices).

## 📁 Layout

```
forge.py              CLI: check / build / run / emit / fmt / doc / lsp / repl / test,
                      --mode safe|fast, --target native|big32|wasm, --freestanding
forge_lang/           lexer, parser, checker, inference, C codegen, big32 + WASM codegen, driver
stdlib/ml.fg          dot, mean, relu, sigmoid, matmul
examples/             hello2, matrix, benchmark, benchmark_scaling,
                      ML regression, regression trace, MLP XOR, big32/, os/, cuda/
editors/vscode/jalpari/   VS Code extension (LSP client, snippets, grammar)
packages/             30 registry packages (units, money, geometry, interest, ...)
docs/FREESTANDING.md  the from-scratch OS roadmap (Phases A–D done, kernel next)
figures/              README figures (regenerate: scripts/make_figures.py)
scripts/make_figures.py   figure generator, with data provenance notes
tests/                test suite + programs that must fail safely
SPEC_V2.md            the v2 language specification
RESTART.md            why v2 was restarted, and what the research locked in
```

## 📊 What Forge borrows, and what it refuses

Borrowed from the research: explicit checked arithmetic (Zig-style),
error handling that cannot be silently ignored, Result/no-null
thinking (Rust/Gleam-style, without a borrow checker), a
single-binary toolchain (Gleam-style), and stability over churn
(the Zig pre-1.0 breaking-change warning).

Refused: a full Rust borrow checker as the default, Carbon-style
C++ interop as a goal, exceptions for expected errors, unstructured
spawning, and leaving the package manager and editor support until
later — the most common ways new languages stall.

## 🧩 Ecosystem

The full tooling is documented in `docs/ECOSYSTEM.md`:

- **Package manager:** `forge pkg init/add/build/run/test/list` — vendored dependencies, no registry needed
- **Formatter:** `forge fmt <file.fg> [--check]` — idempotent, canonical style
- **Language server:** `forge lsp` — real-checker diagnostics + completion, with a full VS Code extension in `editors/vscode/jalpari/` (highlighting, snippets, diagnostics + completion via LSP, Run/Check/Format/Build commands; packaged as `jalpari-1.0.0.vsix`). The old grammar-only extension stays in `editors/vscode/forge/`.
- **REPL:** `forge repl` — keep `let` definitions, evaluate expressions
- **Stdlib:** `ml.fg`, `strings.fg`, `stats.fg` — plus string builtins `split/join/substr/trim/starts_with/ends_with`
- **AI/ML libraries (0.6.0):** `tensor_autograd.fg` (21 ops), `rnn.fg` (LSTM/GRU), `cnn.fg` (conv+pool), `ml_classical.fg` (logreg/k-NN/k-means), `preprocess.fg`, `metrics.fg`, `csv.fg` — plus `test.fg`, `log.fg`, `cli.fg`, `collections.fg` for general development. Import dedup means libraries now combine freely (nn + tensor training in one program).
- **0.7.0 additions:** source-level debugger (`build --debug` emits `#line`), binary I/O + image loading (`image.fg`: PPM P3 + BMP), tape-native im2col + stacked convs, curriculum RNN (len-8 wall cracked), big32 structs + soft-float v1 (+ - *, 60/60 fuzz vs Python float32 on model + Verilog), WASM strings + arrays, and a fuzzer (`tools/fuzz.py`). Big TinyStories run: 153,744 params, held-out ppl 2128.55 → 651.44 — better, still not fluent.
- **1.0.0 additions (market-ready release):** a stability promise (`docs/STABILITY.md` — semver for real), a live browser playground (`web/playground.html` — the real compiler under Pyodide, programs run as WebAssembly, no install), an HTTP server (`http_listen/accept/read_request/respond/respond_status/close` builtins + `stdlib/http_server.fg` + routing demo, verified live with curl), a regex engine (`stdlib/regex.fg` — literals, `.`, `*` `+` `?`, classes with ranges, `\d \w \s`, `^` `$`; no groups/alternation — those are literal), seven real registry packages (`packages/`: units, money, geometry, interest, roman, bases, dice — remote publish/list/add verified against a local registry), a packaged VS Code extension (`editors/vscode/forge/forge-1.0.0.vsix`), honest benchmarks vs Python/Go/Rust/C (`docs/BENCHMARKS_VS.md`, reproducible script), and the MIT LICENSE in the repo root. Install re-verified on a clean HOME and a clean pip venv.
- **1.1.0 additions (peak-level batch, 27 Oct 2026):** `break`,
  string indexing, arrays of structs, nested arrays, the registry
  grown from 7 to 30 packages, check elimination, structured
  concurrency (`scope`), WIT-first WASM contract checking, and
  the Book/Tour/LSP + diagnostics.
- **1.2.0 additions (27 Oct 2026):** HTTPS proxy (`CONNECT`)
  tunnelling in `http_get`, a Windows port (compile-verified via
  MinGW), the Moon apps (Notes, Gallery, Browser, Code — all in
  Jal Pari, on the new `read_line` builtin), and a brand-new VS
  Code extension (`editors/vscode/jalpari/`, LSP client, 16
  snippets, `jalpari-1.0.0.vsix`).
- **Freestanding track (27 Oct 2026, on main after 1.2.0):** the
  language can now stand without Linux underneath —
  `--freestanding` builds (no libc, own `_start`, raw exit
  syscall, `fail()` halts), raw memory (`peek32`/`poke32`),
  bitwise operators, CSR builtins, an `ecall` builtin, and a
  `trap_handler` hook, all proven on the big32 CPU model. See
  `docs/FREESTANDING.md`: Phases A–D are done, the first kernel
  (Phase E) is next.
- **CI:** `.github/workflows/ci.yml` runs the test suite, formatter check, and ecosystem example

## ⚠️ Honest gaps

Forge v2 is production-*oriented*, not a finished Rust/Go/Mojo
rival. Structs, file I/O, CLI args, `forge test`, the ecosystem,
enums+match, spawn threads, C FFI, HTTP, Map/JSON stdlib, assert,
`forge doc`, a package lockfile, and now generics, `Option`/
`Result`, TLS, a local registry, a tiny KV DB, a big32
backend, `?`, generic enums with payloads, a table DB, a SQL
parser, a self-hosted HTTP registry, a WASM backend, string
GC v1, CPU-thread parallel kernels, Python interop via a
shared library, public registry discovery, array GC v2,
struct GC, Python arrays/structs, CUDA codegen, and a static
GitHub-Pages registry are done (26 Oct 2026), and now also
Python [float]/[str] arrays + nested structs, a CUDA
simulation + ready-to-run package, a dynamic registry
with auth and a Dockerfile, and now CUDA execution verified
on a real Kaggle Tesla T4 GPU (26 Oct 2026). It still has
no registry actually running on a public host yet. That is
the next phase in `SPEC_V2.md`, not a hidden feature.
As of 1.0.0 (26 Oct 2026), also done: a stability
promise, a live browser playground, an HTTP server,
a regex engine, seven registry packages, a packaged
VS Code extension, and benchmarks vs Python/Go/Rust/C.
GPU training on a real T4 is verified (26 Oct 2026,
XOR MLP learns, loss 0.001529). Still not done:
fluent generation, a full self-hosting compiler,
big32 float division/ordered comparisons/printing/casts,
PNG/JPEG loading,
and float printing past 6
significant digits. Freestanding v1 is honest about its own
limits too: no strings/arrays (no allocator yet), no I/O
library (output is `poke32` MMIO + exit codes), native
freestanding is x86_64 Linux only, the big32 model has no
timer or SBI emulation (so the trap checkpoint is
ecall-driven), and full `sbiret` SBI calls are follow-up work.
Still blocked on the user's
accounts and token scope, as before: a public registry
host, CI upload, repo rename, PyPI publish, and VS Code
Marketplace publish. The playground's end-to-end run in
a real browser is not yet verified here (it needs a
browser to open it); its compiler pipeline and JS are
verified, and every example program is verified.

## 🔁 Regenerate the figures

```sh
python3 scripts/make_figures.py
```

The script documents exactly where every number comes from: the
scaling and trace figures are real Forge program outputs, the XOR
heatmap is real MLP outputs, and the 3D surface is computed from
the regression data itself.

---

## 🗺️ Project map

How the pieces fit — compiler, backends, libraries, and the from-scratch OS track, all in this repo.

```mermaid
flowchart TD
    CLI["forge.py — CLI (jalpari)"] --> LANG["forge_lang — lexer, parser, checker"]
    LANG --> NAT["codegen: native C → gcc"]
    LANG --> WASM["codegen_wasm: WebAssembly"]
    LANG --> RV["codegen_rv: big32 RISC-V"]
    LANG --> CUDA["codegen_cuda: GPU emit"]
    NAT --> APPS["examples/apps — Moon Notes, Gallery, Browser, Code"]
    NAT --> ML["stdlib — tensor, autograd, nn, gpt + 16 new libraries"]
    RV --> OS["examples/os — macOS-look desktop, Finder, Terminal, allocator"]
    ML --> LIBS["Library program — 120 items, numpy + pandas first"]
    OS --> DAILY["Daily cadence — 10+ OS items and 10+ library items per day"]
```

## 📊 At a glance (verified 29 Oct 2026)

| Measure | Value |
|---|---|
| Language version | 1.4.0 |
| Tree size | 53,116 lines (.py, .fg, .js, .sh, .toml) |
| Standard libraries added 29 Oct | 16 (numpy, pandas, complex, fractions, statistics, checksum, base64, semver, units, polynomials, optimization, fuzzy, calendar, template, color, money) |
| OS kernels added 29 Oct | 10 (lifetime allocator, terminal UART core, shell v2, page allocator, IPC ring, scheduler, FS v3, net loopback, calculator, clock) |
| Library program | [120-item roadmap](docs/LIBRARY_ROADMAP_100.md) — Mojo / Python / Rust / Go equivalents, 100% in Jal Pari |
| License | MIT |
