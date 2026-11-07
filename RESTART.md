# Qasida — full restart (26 Oct 2026)

## Why restart, not patch

v0.1 (preserved untouched at ~/workspace/forge-v01-reference/) proved a
tiny compiler can work, but it was built before the problem-first
research was done properly. The user instruction on 26 Oct 2026 was:
do not stop until Forge is a complete production language like Rust
or Go, restart everything if work stops, and first check what people
are building right now — Reddit and everywhere else, plus papers —
and take what is worth taking from them.

So v2 starts clean. v0.1 is reference only. Nothing from v0.1 is
carried over blindly; every v2 design choice must be justified by
either (a) a named problem in v0.1's PROBLEMS.md, or (b) a finding
from the research pass below.

## Research pass (in progress, 26 Oct 2026)

Questions the research must answer, with sources:

1. What new production-oriented languages are people actually
   building and using as of 2025–2026 (Zig, Mojo, Carbon, Vale,
   Odin, Hare, Gleam, Roc, Austral, Jakt, and others)? What is
   each one's status — shipped, beta, experimental, stalled?
2. What are Reddit / Hacker News / GitHub communities actually
   complaining about and praising in Rust, Go, Zig, and Mojo right
   now (compile times, error handling, async, borrow checker,
   tooling, package ecosystems, hiring, learning curve)?
3. What do recent papers and language-design write-ups say about
   memory safety without a borrow checker, checked arithmetic,
   error handling (Result vs exceptions), effect systems, and
   concurrency models that are safe by construction?
4. What can Forge borrow directly (with credit), what should it
   deliberately NOT borrow, and why?
5. What does a "complete" production language actually require
   beyond a compiler: standard library, package manager, formatter,
   test runner, LSP/editor support, documentation, error messages,
   build system, and a real program written in it as proof?

## v2 build order (phases, not one giant leap)

- Phase A — Core, rebuilt: lexer, parser, checker, codegen, with
  the v0.1 safety rules (static types, no null, no implicit
  conversion, immutable by default, checked arithmetic) plus
  research findings.
- Phase B — Real types and memory: arrays, structs, strings with a
  real memory manager (fixing v0.1's string-copy leaks), floats.
- Phase C — Real programs: modules, file I/O, command-line args,
  `Option`, `Result` + `?` error handling.
- Phase D — Scale: generics, message-passing concurrency, a
  package manager with lockfile, formatter, test command.
- Phase E — Proof and polish: standard library, editor support,
  documentation, and a substantial program written in Forge itself.

## Standing rule for this restart

Do not stop at a demo. A phase is done only when its tests pass
and a real program uses it. If work is interrupted, resume from
this file and the research report — do not restart the research
from scratch, and do not silently drop a phase.

## Status

- 26 Oct 2026: restart created, v0.1 archived as reference,
  research pass DONE. Report: research_notes/forge-new-languages-
  research-20261026-0521/report.md (66KB, with sources). Interactive
  page for it is being built (artifact slug forge-language-research).
- 26 Oct 2026, later: v2 BUILT and tested. Local git commit
  48688df, 26 files, no remote yet. Features: int/float/bool/str/
  [T] arrays, for loops, range, casts, imports, math builtins,
  clock_micros, safe mode (checked arithmetic + bounds checks)
  and fast mode (-O3 -march=native, unchecked). Examples:
  matrix 58 64 139 154, regression w=2.0211 b=0.923818 (500 iters),
  MLP XOR 0/1/1/0, benchmark dot(5000) ~5-6 micros, 1M array-read
  loop ~1.2 ms. Tests: python3 tests/run_tests.py passes.
  GitHub push DONE 26 Oct 2026: user created jayantt1dubeyy/RED-MOON-
  (created 2026-10-26T05:38:10Z, starter LICENSE + README only).
  Pushed 33 files via Git Data API, verified live: commit
  fbf8b14094f3b7a83d527e31859178ca46499789, README sha
  90c06fc5a51e8cad089e9ee73057a70cd191f5b4, with figures/ (3D loss
  surface, scaling, convergence, XOR heatmap) and scripts/
  make_figures.py. Repo: https://github.com/jayantt1dubeyy/RED-MOON-
- Phase C (26 Oct 2026, "keep going to Mojo/Rust/Go level"): structs
  (definition, literal, field access, `let mut` field assignment,
  by-value params/returns, recursive/array-of-structs rejected),
  file I/O (read_file/write_file), CLI args() + `qasida run -- args`,
  parse_int, and `qasida test`. Examples structs_point.fg
  (distance 5, then 7.2111 after q.x=6) and file_and_args.fg.
  Two real bugs caught by the old test suite during this phase
  and fixed: (1) `for v in xs {` was misparsed as a struct
  literal — parser now requires `{ field:` or `{}` lookahead;
  (2) a Forge variable named `argv` collided with C main's argv
  — C main now uses __forge_argc/__forge_argv. Full suite passes
  including new struct/file/missing-field tests. Push Phase C
  next; do not claim generics/Option/Result/concurrency/GPU/
  package manager/LSP yet.
- Ecosystem (26 Oct 2026, "build a complete ecosystem"): qasida pkg
  (init/add/build/run/test/list, vendored deps, forge.toml),
  qasida fmt (AST pretty-printer, idempotent, --check, right-operand
  parens kept for int-division/float-rounding safety),
  qasida lsp (stdio JSON-RPC, checker diagnostics, keyword/builtin/
  fn/struct completion), qasida repl (kept let defs inside main,
  rejected defs not kept), string builtins split/join/substr/trim/
  starts_with/ends_with (C helpers, single evaluation),
  stdlib/strings.fg + stats.fg (word_count fixed twice: first for
  multiple spaces, then for newlines — now 8 for the sample text,
  5 for the 5-word file), VS Code grammar + language config,
  CI workflow, docs/ECOSYSTEM.md, examples/ecosystem/word_stats.fg
  and examples/strings_demo.fg. Test suite now also checks fmt
  idempotency over all examples/stdlib. Push ecosystem next;
  still NOT done: registry, lockfile, HTTP/DB stdlib, generics,
  Option/Result, concurrency, GPU, GC.
- "Build everything" pass (26 Oct 2026): enums + exhaustive match
  (wildcard must be last), spawn threads (void fn, 0/1 int arg,
  auto-join in main, pthread wrappers generated per spawned fn),
  assert builtin, extern C FFI (const char * str, C int, fixes
  puts/system conflicting-type error), http_get (HTTP only, local
  server test passed), stdlib/map.fg + json.fg (flat objects only),
  qasida doc, qasida pkg lock/verify (tamper detected). Two
  supporting fixes that Map needed: index assignment and push
  through a struct field (m.vals[i] = v, push(m.keys, k)), and
  empty array literals in struct literals (map_new). Full suite
  passes including enums/spawn/FFI/map-json tests. Push this pass
  next; still NOT done: generics, Option/Result (needs generic
  enums), GPU, TLS, DB stdlib, registry, GC, WASM backend.
- "Do it then" pass (26 Oct 2026): generics DONE — generic fns
  + generic structs, monomorphised, checker rewrites calls to
  mangled names, save/restore scopes in check_func (nested
  instantiation used to wipe the outer function's scopes).
  Option/Result stdlib, TLS in http_get (OpenSSL, verify on,
  addrinfo loop fix for localhost), local registry publish/add,
  tiny KV db.fg, big32 backend found in workspace (11:53, not
  this pass — emit/build to .hex verified, iverilog sim test
  could not run here). Full suite passes. Push this pass next;
  still NOT done: ? sugar, generic enums, GPU, SQL, hosted
  registry, GC, WASM.
- "Keep going" pass (26 Oct 2026): ? DONE (Option/Result, early
  return, scalar value types only for mismatched value types);
  generic enums DONE (payload variants, match bindings,
  tag+union C structs, None() needs type context);
  table.fg DONE (relational, no SQL parser). Full suite
  passes. Push this pass next; still NOT done: GPU, SQL
  parser, hosted registry, GC, WASM.
- "Then do it" pass (26 Oct 2026): SQL parser DONE
  (sql_query, SELECT/WHERE, bug: FROM table token fixed);
  hosted registry DONE (HTTP server, publish-remote/
  add-remote, septuple 6 = 42); WASM DONE (direct .wasm
  binary, node-tested sum/fib = 55, opcode bugs fixed);
  GC strings DONE (copy-on-call, free-on-reassign/return,
  scope-tracked, allocs 103 frees 101, Assign temp fix).
  Full suite + WASM suite pass. Push this pass next;
  still NOT done: GPU kernels, full GC (arrays/structs),
  Python interop, public hosted registry.
- "Do it that also" pass (26 Oct 2026): parallel kernels
  DONE (parallel_dot/matmul on CPU threads, no GPU in VM,
  dot 70, matmul 19 22 43 50); Python interop DONE
  (build --shared + ctypes helper, add 42, greet hello
  Jayant, FFI param-free bug fixed in helper); public
  registry discovery DONE (list-remote, hostlib 0.1.0
  listed, self-hosted only); array GC DONE v2 (refcount,
  allocs 101 frees 100 in loop, shared/struct arrays
  survive). Full suite passes. Push this pass next;
  still NOT done: real GPU backend, struct-variable GC,
  Python arrays/structs, centrally hosted registry.
- "Do it then" pass (26 Oct 2026): struct GC DONE
  (deep-copy str, refcount array, recurse nested, loop
  allocs 101 frees 100 for both, shared q survives);
  Python arrays/structs DONE (sum 10, double [2,4,6],
  point_sum 42); CUDA codegen DONE (emit-cuda, .cu with
  __global__ kernels, NOT run — no GPU/nvcc here);
  static registry DONE (make_static_registry + list/add-static,
  hostlib vendored via local Pages simulation). Full suite
  passes. Push this pass next; still NOT done: CUDA
  execution on hardware, Python float/str arrays, dynamic
  centrally hosted registry.
- "Finish remaining 3" pass (26 Oct 2026): Python float/str
  arrays + nested structs DONE (sum_float 7.0, join_str,
  outer_sum 42, make_outer 3,4,hello); CUDA simulation DONE
  (dot 70, matmul 19 22 43 50, .cu ready package, NOT run
  — no GPU/nvcc here); dynamic registry DONE as a server
  (auth 401, publish ok, duplicate 409, Dockerfile + deploy
  README, NOT hosted on a public host yet). Full suite
  passes. Push this pass next; still NOT done: CUDA
  execution on hardware, a public registry host.
- CUDA REAL GPU RUN (26 Oct 2026, Kaggle, token transient
  only, not stored): notebook arshhdubeyy/forge-cuda-kernel
  v2, 2x Tesla T4, driver 580.178.04, nvcc 12.8, output
  dot 70.000000, matmul 19 22 43 50. Docs updated to record
  this. Push this verification next; still NOT done: a
  public registry host.

## Research findings that now lock v2's design (26 Oct 2026)

Bottom line from the research: no single language has replaced
Rust/Go/C. The ones gaining real production use have a narrow
beachhead (Zig: C toolchain/cross-compilation; Mojo: AI kernels;
Gleam: BEAM services; Odin: games; Hare: Unix tools), not a promise
to be good at everything. Carbon is still designing safety after
4 years; Vale/Roc are brilliant but still pre-1.0 after 8+ years.

- Zig (pre-1.0, 0.16.0 Apr 2026): explicit allocators, error unions
  that cannot be ignored, checked arithmetic in safe modes, comptime.
  Complaint: pre-1.0 breaking changes (0.15/0.16 std.Io, 0.17 build
  split) break libraries and tooling — Forge must NOT ship breaking
  churn after 1.0, and must stabilise its stdlib/tooling early.
- Mojo (1.0 on 11 Aug 2026, compiler Apache-2.0 18 Aug 2026):
  Python-like syntax, ownership/borrow-like checks, MLIR kernels.
  Caveats: MAX is under a separate licence, Qualcomm acquired
  Modular Jul 2026, and at 1.0 it still lacks mature async, pattern
  matching, and unions — weak for general network services.
- Carbon: experimental, MVP 0.1 at earliest late 2026, 1.0 after
  2028, safety still being designed. Lesson: do NOT promise C++
  interop and safety on the same timeline.
- Gleam (stable 1.0 Mar 2024, 1.18 in 2026): no null, Result errors,
  actors/supervision on BEAM, plus formatter, package manager, test
  runner, LSP from early on — toolchain completeness is why it is
  production-viable despite a small community. Forge must copy the
  toolchain-first lesson, not just the compiler.
- Rust complaints to avoid importing: compile times and huge
  target dirs, borrow-checker fights with graphs/cycles, async
  Pin/Waker and runtime fragmentation. Go complaints: verbose
  error handling, missing enums/nil-safety (91% satisfied in the
  2025 survey, n=5,739, but those gaps recur).
- Papers/ideas to borrow: regions (Tofte & Talpin), Cyclone,
  Verdagon generational references + regions, Vale/Valen group
  borrowing, Austral linear types + capabilities (checker reported
  ~600 lines — linearity need not be huge), structured concurrency
  (Trio/Swift) and actors (BEAM), Zig-style checked-by-default
  arithmetic with explicit wrapping operators, Result/Option with
  exhaustive matching.

### Borrow / do-not-borrow for Forge v2

Borrow: explicit allocators/arenas, comptime-style metaprogramming
(later), error unions + `?`, checked arithmetic, Result/no-null/
exhaustive matching, structured concurrency, actors/supervision
(later), single-binary toolchain, cross-compilation wedge,
stability + codemods.
Do NOT borrow: full Rust borrow checker as the default, Carbon-style
C++ interop as a goal, exceptions for expected errors, unstructured
spawn, package-manager-later, function colouring, a closed compiler.
Most common new-language failures to avoid: package manager late,
LSP late, stdlib churn, tutorial rot, no HTTP/TLS/DB story.

### Uncertainty carried from the research (do not build on these
### as if verified)

Carbon "0.8.2" blog claim contradicts the official roadmap and was
disregarded; MoonBit 1.0 shipment, Zig 0.17 dates, and single-source
benchmarks (Zig 5x, Jai <1s, Goose vs Rust) are unverified; several
roundups were low-quality SEO blogs, with official docs prioritised
where they conflicted. Verify these again before quoting them in
Forge docs.

## Mojo-level ML batch — 26 Oct 2026 (0.2.0)
- Tensor + autograd + nn + tokenizer + dataset + gpt + inference
  stdlibs; tiny GPT trains (loss 2.274 -> 0.360, 20 epochs, ~5 s);
  KV-cache diff 0; CUDA fused kernels simulation-verified only.
- Gotchas found in this batch: (1) a struct containing another
  struct must be defined in the SAME file after the inner struct
  (C emission order) — NodeVec lives in autograd.fg for this
  reason; (2) pushing to a plain array parameter does NOT reach
  the caller — return values, don't fill caller arrays; (3) stdlib
  files must not both import rand.fg (duplicate definitions) —
  leaf files leave rand to the importing program or to nn.fg;
  (4) no `break` statement in the language — use loop conditions;
  (5) GPT training pattern: params must be the FIRST tape nodes
  so param id == param index.

## Scaled GPT + GPU run — 26 Oct 2026 (0.3.0)
- gpt2.fg (generalised blocks/heads) + gpt_scaled.fg (2 blocks,
  2 heads, 5200 params): train 2.559->2.364, held-out ppl
  58.1->53.9; checkpoint round-trip diff ~8e-07.
- Kaggle notebook v4 verified on 2x T4 (driver 580.178.04,
  nvcc 12.8.93): all transformer kernels match simulation.
- Gotchas: log(0) -> NaN at scale (eps fix in g2_loss);
  __half2double does not exist (use __half2float cast).

## TinyStories word GPT — 26 Oct 2026 (0.4.0)
- tools/prepare_tinystories.py + data/tinystories_vocab.txt
  (500 words + <unk>) + data/tinystories_ids.txt (24,000
  words, first 200 TinyStories train stories, UNK 14.8%).
- gpt_tinystories.fg (word GPT, gpt2.fg, 12,608 params,
  seq 8 words): train 4.98375, 4.64674 (epochs 1-2);
  held-out ppl 1078.88 -> 247.39 (eval-only companion
  gpt_tinystories_eval.fg, from the epoch-3 checkpoint).
  Greedy loops on "cake"; sampled = real words, salad order.
- Gotchas: native backend retains training tapes — one
  process OOM-killed at 1500 steps x ~221k nodes. Train
  one epoch per process with checkpoint resume; eval in
  its own process. Tape freeing is the 0.5.0 compiler fix.

## 0.5.0 engine batch — 26 Oct 2026
- Tape freeing FIXED in forge_lang/codegen.py
  (emit_free_frame on Block/If/While/For ends; frame
  frees only names absent from outer frames, or Assign
  targets double-free). Probe: 1000 allocs / 1000 frees.
  gpt_tinystories.fg now trains 3 epochs in ONE process.
- Tensor autograd (stdlib/tensor_autograd.fg) + tensor
  GPT (stdlib/tgt.fg): grad checks ~1e-9; small run
  100 nodes, 4.35 ms/step, ppl 549 -> 283; scaled run
  (data_scaled/, 49,664 params) ppl 1119 -> 189.
- KV-cache for gpt2 (stdlib/inference_gpt2.fg): diff
  4.44e-16 vs full forward. Positions clamp to seq-1
  past the trained length (documented approximation).
- Ecosystem: docs/BENCHMARKS.md, web/landing/index.html,
  pip install . verified in a clean venv, docs/DEBUGGING.md,
  examples/cuda/mlp_train.cu (CODE ONLY, no GPU run yet).
- Still NOT done: fluent generation, GPU training run,
  WASM strings/arrays (no linear memory in backend),
  big32 floats/structs (integer-only core), source-level
  debugger (AST lacks file tracking), self-hosting,
  registry host / CI upload / repo rename / PyPI publish
  (maintainer's clicks/accounts).

## 0.6.0 ecosystem batch — 26 Oct 2026
- Import dedup FIXED in forge_lang/compiler.py
  (visited set no longer cleared on return).
  nn.fg + tensor_autograd.fg now combine;
  import_dedup_demo.fg is the regression test.
- Tensor ops 17-20 (maxpool2d/sigmoid/tanh/mse),
  finite-difference verified (tensor_ops2_demo.fg).
- New stdlib: rnn.fg, cnn.fg, ml_classical.fg,
  preprocess.fg, metrics.fg, csv.fg, test.fg,
  log.fg, cli.fg, collections.fg. Demos: rnn
  (0.44->1.0), cnn (0.5->1.0), classical (all 1.0),
  iris (0.933333), ckpt (diff 0), dev (ok).
- Data: data/iris.csv (real UCI Iris, 150 rows).
- Still NOT done: fluent generation, GPU training
  run, WASM strings/arrays, big32 floats/structs,
  source-level debugger, self-hosting, registry
  host / CI upload / repo rename / PyPI publish,
  image/binary loading, conv stacking, len-8 RNN.

## 0.7.0 "build everything open" batch — 26 Oct 2026
- Debugger: forge.py build --debug emits #line for
  main + imported files (readelf-verified).
- Binary I/O (read_bytes/write_bytes) + image.fg
  (PPM P3 + BMP, BMP == PPM verified). No PNG/JPEG.
- im2col op 21 + cnn_conv2d_tape; two-conv net
  0.5 -> 1.0 at lr 0.01 (0.05 oscillates).
- Curriculum RNN len 3 -> 5 -> 8, all 100%.
- big32 structs (frame slots, model + Verilog) and
  soft-float v1 (+ - *, 27-bit exact arithmetic,
  12/12 demo + 60/60 fuzz vs Python float32,
  model AND Verilog). No div/comparisons/printing.
- WASM strings + arrays (byte-identical demo
  output vs native; docs/WASM_STRINGS.md).
- Fuzzer tools/fuzz.py, 50/50 OK default run.
- Big TinyStories: 2000 stories, 150k words,
  vocab 2000, 153,744 params, ppl 2128.55 -> 651.44
  — better, still NOT fluent (greedy loops).
- Suite now has real big32 build checks + a
  node-based WASM comparison (earlier wasm/big32
  "suite passes" were native runs — corrected).
- Update 26 Oct 2026 (after 0.7.0): GPU training
  run VERIFIED on a real T4 (notebook
  arshhdubeyy/forge-mlp-train v3, LR 5.0 — v1
  failed at link on kernel.cu's duplicate main,
  v2 at LR 0.5 stalled at loss 0.25; v3 loss
  0.001529, predictions ~0, 1, 1, 0).
  mlp_train.cu now carries LR 5.0 + the verified
  header. Still NOT done: fluent generation, full
  self-hosting compiler, registry host / CI upload
  / repo rename / PyPI publish (all blocked on
  user accounts/token scope, as before).
