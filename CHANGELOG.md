# Changelog — The Jal Pari Language

All notable changes are listed here. Version numbers follow
semantic versioning: 1.0.0 (26 Oct 2026) is the first stable
release — the documented language surface will not break
without a major version bump (see docs/STABILITY.md).
0.x releases were pre-stable; breaking changes were possible then.

## Unreleased

- Fix: type aliases inside sized-array spellings
  now expand (the batch-12 gap: "[N; 3]" reached
  later passes unexpanded and failed as an unknown
  field type; expand_aliases now expands the
  element part and keeps the literal length).
- Fix: nested empty array literals now work
  (`let x: [[int]] = [[]];`, mixed `[[], [1]]`,
  call args, assignment, tuples): the checker
  accepts types up to `[?]` holes in
  dynamic-array/tuple positions (never sized),
  and infer fills literal types from context so
  codegen never sees a hole. Bare holes and
  genuine mismatches still error.
- Fix: nested arrays as struct fields now work
  (`[[int]]` and `[Point]` fields): the typedefs
  were collected but emitted after the struct
  bodies, which hold array fields by value — the
  typedef lines now precede composite bodies
  (helpers still follow the bodies). Enum payload
  structs with nested-array payloads remain a
  documented residual.
- Fix: push to a shared nested array now
  copies-on-write (the batch-18 gap: the inline
  nested-array push path realloced the shared
  buffer in place, dangling the other holders and
  double-freeing at scope exit — reproduced as a
  tcache double free; the path now detaches first
  like the scalar push helpers, copying slots and
  gaining an inner reference each, so the free
  counts stay exact. Inner arrays stay shared by
  reference, as elsewhere).
- Top-500 batch 1: binary/octal literals and digit separators
  (0b1010, 0o777, 1_000; malformed literals are compile errors)
  and the `continue` statement (native, big32, WASM, formatter;
  a for-loop continue still runs the increment).
- Top-500 batch 2: traits v1 — trait declarations, impl blocks
  (with or without a trait), method-call syntax with static
  dispatch, and checker-enforced trait conformance. big32 and
  WASM reject trait programs in v1 (no struct parameters /
  structs there yet); generic traits, trait objects, and
  generic bounds are later slices.
- Top-500 batch 3: type aliases v1 — transparent `type` 
  shorthands expanded in the checker before other checking,
  so they work on every backend for already-supported types.
  Chains, arrays, concrete generic instantiations, struct and
  enum aliases, and struct literals via bare-struct aliases
  are in; aliases take no type arguments.
- Top-500 batch 4: wrapping arithmetic (wrapping_add/sub/mul/
  neg, never failing, on native + big32 + WASM) and distinct
  newtypes v1 (`newtype UserId = int;`, cast-only crossings,
  same-newtype equality, native + big32 verified, WASM a
  later slice).
- Top-500 batch 5: union types v1 — `int | str` as a tagged
  value, wrapping at assignment/argument/return/struct-field/
  cast sites, narrowing through match arms named by member
  type, str-payload copy/free discipline; native verified,
  big32/WASM reject union programs in v1. Members are the
  four scalars in v1.
- Top-500 batch 6: opaque types v1 — `opaque Trait` as an
  existential over its implementations, tag-dispatched
  method calls/copies/frees; native verified, big32/WASM
  reject opaque programs in v1.
- Top-500 batch 7: fixed-width integers v1 — i8/i16/i32/
  u8/u16/u32/u64 as distinct scalars (i64 is int), fitting
  literals adapt, checked arithmetic and narrowing casts,
  struct fields; native verified, big32/WASM reject
  fixed-width programs in v1.
- Top-500 batch 8: sized arrays v1 — `[T; N]` as a distinct
  type from `[T]`, exact-count literals, push rejected,
  index/len/iteration like dynamic arrays; native verified,
  big32/WASM reject sized programs in v1.
- Top-500 batch 9: readonly views v1 — `readonly [T]` as a
  read-only handle (index/len/iteration work, push and
  index assignment rejected), mutable-to-view coercion
  within the same array kind; native verified, big32/WASM
  reject readonly programs in v1.
- Top-500 batch 10: never type v1 — `never` as the bottom
  type (never functions must diverge and cannot return,
  never values coerce to any expected type at value
  sites, diverging bodies satisfy the return rule);
  native verified, big32/WASM reject never programs
  in v1.
- Top-500 batch 11: checked float-to-int casts v1 —
  safe mode fails on out-of-range, NaN, or infinite
  floats; fast mode keeps the truncating cast; WASM
  already traps, big32 already rejects.
- Top-500 batch 12: tuple types v1 — `(T1, T2, ...)`
  with owned elements, flowing through let,
  assignment, arguments, returns, and struct fields;
  native verified, big32/WASM reject tuple programs
  in v1. Also: composite structs now emit in
  dependency order (forward struct references work)
  and the lexer treats numbers after a dot as tuple
  indices.
- Top-500 batch 13: local type inference v1 — an
  empty array literal infers its element type from
  a later constraining use (push, assignment,
  annotated let, call argument, return, struct
  field, field assignment); unconstrained literals
  fail with a clear message.
- Top-500 batch 14: first-class ranges v1 — lazy
  half-open `a..b` values of type `range`, with
  len / contains / start / end / sum methods and
  for-loop iteration; big32/WASM reject ranges
  in v1.
- Top-500 batch 15: void/unit consistency v1 —
  void is allowed only as a function or method
  return type; every other use fails in the
  checker with a clear message instead of
  invalid C. §1 Types/safety is now complete.
- Top-500 batch 16: defer v1 — `defer call();`
  runs at the enclosing block's exit, LIFO,
  including early returns, breaks, and
  continues; loop-body defers run each
  iteration. big32/WASM reject defer in v1.
- Top-500 batch 17: allocator-as-value v1 —
  stdlib/allocator.fg, pure Jal Pari: one
  Allocator struct passed explicitly to
  functions, in bump, freelist, and arena
  kinds; out-of-memory returns -1 as a value.
- Top-500 batch 18: arena allocation v1 —
  stdlib/arena.fg, pure Jal Pari: a growing
  region with mark/restore for temporary
  allocations. Also fixed two real ownership
  bugs: copy-on-write push on shared arrays,
  and field-assignment ownership for array and
  struct fields.
- Top-500 batch 19: reference counting v1 —
  a `refcount` builtin plus stdlib/rc.fg:
  shared ownership made observable, clone
  gains a holder, last drop frees.
- Top-500 batch 20: weak references v1 —
  a runtime weak table: weak_new registers
  without gaining a holder, weak_upgrade
  reports the current array while alive and
  (false, []) after the last strong holder
  drops.
- Top-500 batch 21: move semantics v1 —
  move(a) transfers the one hold instead of
  copying; the source is dead afterwards and
  any later use is a checker error.
- Top-500 batch 22: copy-on-write arrays v1,
  opt-in — stdlib/cow.fg: a Cow shares its
  buffer until a write (shared writer gets a
  private copy, sole holder writes in place).
  Marked partial: language-default CoW needs
  an explicit decision (it would break Rc's
  shared mutation).
- Top-500 batch 23: stack-allocated slices v1
  — stdlib/slice.fg: a stack header over an
  existing array's buffer, no copy, writes
  through, slicing composes.
- Top-500 batch 24: lifetime-ordered placement
  v1 — stdlib/lifetime.fg: shorts from the
  front, longs from the back, one reset frees
  all shorts while longs survive.
- Top-500 batch 25: memory-mapped files v1 —
  a runtime mmap table: open/get/set/close,
  writes land in the file itself. Also fixed
  two real leaks the demo exposed (read_bytes
  freshness, write_bytes param consumption).
- Top-500 batch 26: allocator-aware collections
  v1 — AVec over the #22 Allocator (one element
  per slot; bump stays exhausted after a pop,
  freelist reuses the freed slot; OOM is a
  value). Pure Jal Pari. Maps are the next
  slice, so #32 lands PARTIAL.
- Top-500 batch 27: destructor hooks v1 — a
  `drop` method runs when an owned binding dies
  (block/function end, return, break), before
  the free, via an owned copy; the receiver
  parameter itself never hooks (else infinite
  recursion). Native only.

## 1.3.0 — 31 Oct 2026

- Daily batch 31 Oct 2026 (10 OS kernels + 10 libraries, all
  verified by real runs): OS kernels, each a new freestanding
  big32 kernel with a model test (exact UART transcript,
  halted) — rng (LCG driver), beep (note table), rtc (HH:MM:SS
  app), editor (type/backspace), fm (file manager), paint (8x8
  framebuffer), mon (system monitor), bootmenu (app launcher),
  notes (notes app), pipe (byte-stream ring IPC). Libraries,
  each a new pure Jal Pari stdlib file with a demo verified by
  `forge run` — uuid, retry-backoff, cli-table, progress,
  email-parse, tfidf, ical-lite, config, timers, changelog.
  Regression suite `tests/run_tests.py` passed.
- Language upgrade 30 Oct 2026: `ecall3(eid, arg0, arg1) -> int`
  (big32 only) — extension id in `a7`, arguments in `a0`/`a1`,
  result in `a0`. Proved by `examples/os/kernel_ecall3.fg` +
  `tests/test_kernel_ecall3.py` (exact transcript `2 / 141 / -2 /
  DONE`, halted; the 141 proves the second argument arrives in `a1`).
  Scope note: this is the three-register call; real SBI also uses
  `a6` for the function id, so exact firmware-SBI calls remain a
  future slice.
- Language upgrade 30 Oct 2026: hex integer literals (`0xFF`,
  `0x10000000`, uppercase `0X` also accepted) — lexer-only, so
  every backend and the checker see a plain int; a bare `0x` with
  no hex digit is a compile error. Proved by
  `tests/test_hex_literals.py` (native values + a big32 model
  kernel using `0x10000000` as the UART address).
- Daily batch 30 Oct 2026 (15 libraries, all pure Jal Pari with a
  demo each, verified by `forge run`): fft (radix-2 + inverse,
  Taylor-series twiddles), mathex (erf, gamma), textwrap,
  difflib (LCS ratio — documented as not Python's SequenceMatcher
  ratio), slugify, markdown-lite (to text; HTML pending),
  toml (subset), ini, xml-lite, dotenv, pathlib (POSIX), url
  (parse/build/encode of the reserved set), compress (RLE only;
  Huffman/gzip pending), nlp-words (tokenize/stopwords/stem-lite),
  i18n-lite (two-locale catalog, plural-lite). Two bugs caught by
  the demos and fixed before push: mathex `sign` needed `mut`,
  slugify dropped uppercase letters. No kernel sims this day: a
  big32 diagnostic sim (privilege trace, then CSR-write trace)
  was running, so per the daily rules the OS track is reported
  short honestly instead of colliding with it.
- Daily batch 29 Oct 2026 (16 libraries, all pure Jal Pari with a
  demo each, verified by `forge run`): numpy (flat row-major
  arrays, matmul, reductions), pandas (flat DataFrame, filter,
  sort, means), complex, fractions, statistics (mode, quantiles,
  IQR), checksum (crc32/fnv1a/adler32 over byte arrays),
  base64 + hex, semver (struct API — no int-to-string builtin
  exists yet), units, polynomials, optimization (gradient
  descent, least squares), fuzzy (Levenshtein), calendar
  (Zeller weekday), template ({{name}} rendering), color
  (hex/rgb/hsl), money (integer cents). Checksums cross-checked
  against Python; weekdays cross-checked against `date`.
- Daily batch 29 Oct 2026 (10 OS kernels, all freestanding big32
  verified on the Python big32 model with exact UART transcripts
  + memory checks): lifetime-ordered allocator (short pool freed
  by epoch reset, long pool survives), terminal command core
  (prompt/echo/backspace/dispatch over UART RX — the SOC2 window
  draw itself is still pending), shell v2 with digit arguments,
  page bitmap allocator, IPC ring queue, priority scheduler
  policy, filesystem v3 (delete + rename), network loopback
  checksum, calculator app, clock app. No SOC2 vvp sims were run
  this day: the big32 Linux continuation sim was running.
- Traps + firmware calls (Phase D of the freestanding track;
  see docs/FREESTANDING.md): csr_read/csr_write/csr_set/
  csr_clear (literal CSR numbers only), trap_handler hook
  (mtvec + full register save/restore stub + mret), ecall(eid,
  arg) SBI-call primitive; program end clears mtvec before
  halting. Checkpoint is ecall-driven (the model has no timer
  or SBI emulation) with exact UART transcript SCRTK.
- `--freestanding` build mode (Phase C of the freestanding
  track; see docs/FREESTANDING.md): native builds with
  `-nostdlib` and the program's own `_start` (raw exit_group
  syscall, main's return value = exit code); OS needs
  (files, sockets, threads, clock, args, print, libm, extern)
  are clean checker errors and strings/arrays are clean
  codegen errors; big32 runs under the same flag, WASM
  refuses it. `fail()` halts instead of exiting.
- Raw memory builtins `peek32`/`poke32` (Phase B of the
  freestanding track; see docs/FREESTANDING.md): volatile 32-bit
  load/store through a raw address — native via volatile pointer
  helpers, big32 via `lw`/`sw`, WASM rejects loudly. `peek32` is
  an expression, `poke32` is statement-only like `push`; both
  unchecked in every mode, by design. Proven by a big32 model
  run (UART byte write, status/RX reads, RAM round-trip) in
  `tests/test_peek_poke.py`.
- Bitwise operators `& | ^ << >> ~` on ints (first step toward a
  freestanding, bare-metal-capable language; see
  docs/FREESTANDING.md): C-like precedence, two's-complement
  `& | ^`, wrapping `<<`, arithmetic `>>`, shift counts masked
  (0..63 native/WASM, 0..31 big32). Native, WASM, and big32
  backends; `tests/test_bitwise.py` covers all three plus
  checker rejections and formatter stability.

## 1.2.0 — 27 Oct 2026

- HTTPS proxy (CONNECT) support in `http_get` (native backend):
  `https_proxy` / `HTTPS_PROXY` (`http://[user[:pass]@]host[:port]`,
  port defaults to 8080) now tunnels HTTPS through a plain HTTP
  proxy with a `CONNECT host:443` handshake before the TLS
  handshake (SNI, certificate verification, and all existing
  failure messages unchanged); `no_proxy` / `NO_PROXY` bypasses
  the proxy (exact, leading-dot suffix, or `*`). Other proxy
  schemes are ignored and the connection goes direct, as before;
  plain `http://` never uses a proxy. Tested end to end with a
  local CONNECT proxy + local TLS server on a private CA
  (`tests/test_proxy_connect.py`, 6/6): direct, via proxy,
  no_proxy bypass, proxy refusal (clean "proxy CONNECT refused"
  error), proxy auth, and non-http scheme ignored. WASM/big32
  unaffected (native C only).
- Windows port (MinGW-w64, cross-compile verified, not yet
  run-verified): the generated C now has a `#ifdef _WIN32`
  branch — winsock headers, a `forge_sock_t` socket type
  (`SOCKET` on Windows, `int` elsewhere), `closesocket`
  via `forge_sock_close`, lazy `WSAStartup`, link
  `-lws2_32`; fast mode drops `-march=native` for MinGW
  targets. HTTPS is off by default on Windows (no MinGW
  OpenSSL here): `https_get` compiles to a stub that
  fails at runtime with a clear message; plain HTTP and
  non-network programs are unaffected. Opt back in with
  `JALPARI_HAVE_OPENSSL=1` (MSYS2 OpenSSL, untested).
  `JALPARI_NO_OPENSSL=1` builds any platform without
  OpenSSL (same stub). Verified: hello, HTTP registry
  server, scope/threads, struct-array, nested-array,
  break, and https programs all cross-compile with
  `x86_64-w64-mingw32-gcc-posix` 13.2.0. No Wine here,
  so no `.exe` has executed yet — Windows is not
  claimed as supported until one runs.
- Registry deploy files completed (registry/): the server
  now reads `PORT` and `FORGE_REGISTRY_TOKEN` from the
  environment (CLI flags still win), `GET /` and
  `GET /health` answer for health checks, and the
  Dockerfile no longer passes an empty `--token` (which
  used to lock publishing even in open mode). New:
  `render.yaml` (Blueprint), `fly.toml` (with a
  persistent volume for published packages), a systemd
  unit for VPS installs, and a rewritten README with
  exact steps for each. Verified live without Docker
  (no daemon in this VM): health, empty list, publish
  401 without token / ok with token / 409 on republish,
  byte-exact file round-trip, and open-mode publish.
  The Docker image itself is not built here — the
  Dockerfile is a 10-line copy of the verified script.
- JalOS (examples/os/jalos.fg, ~1300 lines): a complete
  teaching OS in Jal Pari — boot, priority scheduler
  (29-tick demo: printer, counter, fibber, sorter,
  idler), first-fit heap allocator with coalescing,
  hierarchical VFS with permissions, users, /proc,
  networking (real HTTP fetch), a package manager
  that really installs registry packages over HTTPS,
  cron/syslog services, and a ~30-command shell with
  script-file and single-command modes. The demo tour
  is offline, deterministic, and wired into the suite
  as an exact-output test. Honest limits (see
  examples/os/README.md): simulated, not bootable;
  text shell, no GUI; plain-string passwords; no
  persistence across shutdown; HTTPS needs direct
  internet (proxied sandboxes break the TLS handshake
  — the language HTTP client has no proxy CONNECT
  yet).

## 1.1.0 — 27 Oct 2026

- Book, Tour, LSP parity, fix-ending diagnostics:
  docs/BOOK.md rewritten as the complete current guide
  (replacing the stale starter: WASM strings/arrays, autograd,
  and GPU training are no longer "not yet"), docs/TOUR.md is a
  10-step guided tour with runnable programs in
  examples/tour/ and verified outputs, the language server now
  completes from the checker's own keyword and builtin sets
  (so `scope`, `break`, `http_listen`, `alloc_count`, and
  friends can no longer drift stale) with an end-to-end stdio
  smoke test in tests/lsp_smoke.py, and checker errors now end
  with fixes where a fix is mechanical — did-you-mean
  suggestions for variables, functions (including builtins),
  types, and enum variants, int/float conversion hints
  ("convert the value with 'value as float'"), missing-return
  and break-outside-loop fix lines, and rejection of C
  keywords as names ("'double' is a C keyword ... rename it")
  instead of cryptic C compiler failures.
- WIT-first WASM components (docs/WIT.md): `forge.py build
  prog.fg --target wasm --wit prog.wit` (and `emit-wasm --wit`)
  checks the program against the WIT world before generating
  the module — every non-`main` function must be declared in
  the world's exports with matching arity, parameter types in
  order, and return type, or the build fails naming the
  difference. Type mapping: int -> s64, float -> f64,
  bool -> bool, str -> string, [T] -> list<T>. World imports
  are rejected (the backend emits a self-contained module with
  no imports), and `--wit` with another target is rejected
  instead of silently ignored. This is interface-contract
  checking, not component-model binary encoding: the emitted
  module is still a core module (see docs/WIT.md for the
  boundary).
- Structured concurrency (`scope`, native backend): a `scope {
  ... }` block joins every task spawned inside it — directly or
  transitively by functions called from inside it — at the
  closing brace, and on any `return` or `break` that leaves the
  scope, so no task outlives its block. Scopes nest (an inner
  join is never repeated by an outer join or by `main`'s
  exit join); tasks spawned outside any scope keep the old
  behaviour (joined at `main`'s return). `scope` is not a
  reserved word — it is recognised only as `scope` followed by
  `{` at statement position, so `scope` still works as an
  ordinary variable name. On WASM and big32 a scope block runs
  as a plain block and `spawn` inside it fails as before.
  No results, cancellation, or channels yet: spawned functions
  are void, and a hung task still hangs the scope that waits
  on it.
- Safe-mode check elimination (native backend only, SPEC §6b):
  duplicate checks within one statement are emitted once (the
  repeat uses the unchecked access; the cache is per-statement
  and cleared by any call); guard intervals skip overflow/div
  checks proven safe by if-guards (e.g. `n - 1` after `if n < 2
  { return n; }`), with hull joins across arms and clearing
  around loops and matches; string-index comparisons (`s[i] ==
  "a"`, `s[i] == s[j]`) compare bytes directly with no
  allocation, keeping the bounds check in safe mode. Nothing
  observable changes: aborts and results are identical, and
  tests pin both the eliminations (emitted-C probes) and the
  checks that must remain (overflow after reassignment, guards
  around loops, out-of-bounds string compares and duplicate
  reads). WASM and big32 keep every check.

- Cost of safety published (docs/BENCHMARKS_SAFETY.md,
  tools/bench_vs/run_safety_bench.py): safe vs fast mode on six
  tasks, compared two ways — shipped flags (safe -O2 vs fast -O3
  -march=native) and matched flags (both -O2, so the only
  difference is the checks). Pure check cost: overflow-check-heavy
  fib 2.7-3.7x, string bounds checks ~1.7x, nested bounds checks
  ~1.4x, array bounds on float work ~1.0x, loop-counter checks
  ~1.0x. The big shipped fast-mode wins (matmul 3.9-5.3x) come
  from -O3/-march=native auto-vectorization, not from dropping
  checks — the matched comparison proves it. Safe and fast compute
  identical results on all six tasks. Caveat, stated in the doc:
  this VM's timing noise moves absolute times up to ~2x between
  runs, so ranges from two runs are reported, not single numbers.

- Registry seeded from 7 to 30 packages (all 0.1.0, each with a
  demo with self-checks and a smoke test): percentages, loans,
  bmi, colors, sorting, search, primes, factors, statistics,
  grades, tax, cooking, budget, checks (Luhn, ISBN-10/13), morse,
  textstats, speed, data, angle, fractions, vectors, matrices
  (built on the new nested arrays), polynomials. All 30 demos
  and 30 smokes pass (60/60); publish of all 30, list, local
  add, and HTTP add-remote verified against a local registry
  server with a fresh consumer. Public hosting still needs the
  maintainer's account.

- Platforms investigated (docs/PLATFORMS.md): Linux x86_64
  remains the verified platform. Windows cross-compilation was
  attempted with MinGW-w64 13.2.0 and fails at the generated
  C's POSIX socket headers — a Windows port needs a winsock
  branch in the runtime, MinGW OpenSSL or conditional HTTPS,
  and the -posix MinGW variant. macOS was not buildable here
  (no SDK/clang/zig); its path is a native build with Xcode
  tools + Homebrew OpenSSL. No macOS or Windows binary is
  claimed. Enabler shipped: `JALPARI_CC` selects the C compiler
  for `run`/`build`/shared-library builds (default `cc`,
  unchanged).

- Killer app: examples/apps/registry_server.fg — a package
  registry server written in Jal Pari itself, speaking the same
  HTTP API as the Python reference server, so the real `forge
  pkg publish-remote` / `add-remote` clients work against it.
  Verified live: publish (incl. 401 unauthorized, 409 version
  already exists), list, versions, files, byte-exact file
  round-trip, and a fresh consumer installing and running two
  packages. One real bug found and fixed along the way: the
  first version read each request with a single recv, which
  fails when a client sends headers and body as separate
  writes — the server now reads until headers plus
  Content-Length body bytes arrive. Flat on-disk layout plus
  an index file (no directory-listing builtin); listings in
  publish order, not sorted; ASCII-only publish bodies.
  HTTP status reasons gained 401 Unauthorized and 409
  Conflict.

- `break` exits the innermost `while`/`for` loop, on all three
  backends (native, WASM, big32). Breaking frees the loop body's
  locals, so the break path does not leak (verified: 4 allocs, 4
  frees in examples/break_gc_demo.fg). `break` outside a loop is a
  compile error, including inside a function called from a loop.
  This is an addition under the stability promise, not a break:
  no existing program used `break` as an identifier.

- String indexing: `s[i]` returns a 1-character string (byte
  indexing), on native and WASM; safe mode aborts out of bounds,
  fast mode skips the check. Strings stay immutable: `s[i] = ...`
  is a compile error. Not yet on big32 (clear error for now:
  big32 has no runtime string allocation).

- Arrays of structs (native): `[Point]` works — literals, `len`,
  `xs[i]` (owned copy), `xs[i].field` (direct read, no leaked
  sibling fields), `for` loops (borrowed element view), `push`,
  index assignment (frees the old element first), and array free
  (frees elements' owned fields: verified 1/1 array and 2/2 str
  allocs/frees). Generic struct arrays work too. Not yet on WASM
  or big32, which report clear errors.

- Nested arrays (native): `[[int]]` matrices — literals, `len`,
  `m[i][j]` reads, chained `m[i][j] = v` writes, `for` loops over
  rows, row `push` and row replacement, shared-row mutation
  (`let row = m[i]; row[j] = v;` mutates the matrix), and
  balanced nested frees (verified 3/3 array allocs/frees for a
  2-row matrix, 3/3 for `[[str]]`). Triple nesting works too.
  big32 reads nested arrays on the Python model (push remains
  unsupported there, as for all arrays); WASM reports a clear
  error.

## 1.0.0 — 26 Oct 2026 — "Market-ready": stability promise, live playground, HTTP server, regex, real packages, packaged extension, honest benchmarks

- Stability promise: docs/STABILITY.md — semver for real. 1.x adds,
  never breaks; breaking changes require a major version; deprecations
  get at least one minor release of warning. The promise covers the
  documented language surface, stdlib APIs, the jalpari CLI, and the
  package format. It does NOT cover missing features (gaps, not breaks),
  experimental backends (CUDA emit, big32 soft-float internals, the
  self-host prototype), performance characteristics, or error wording.
- Front door: the MIT LICENSE now lives in the repo root (it was only
  preserved on GitHub's side before). Landing page updated to 1.0.0
  numbers. Repo rename + hosting + GitHub Pages enable remain the
  maintainer's own clicks.
- Install: re-verified on a clean HOME (install.sh -> jalpari 1.0.0,
  demo runs) and a clean pip venv (jalpari-pip 1.0.0). PyPI publish
  itself still needs the maintainer's account.
- Live playground v2: web/playground.html is now a real editor. The
  actual compiler runs under Pyodide (fetched from the repo's main
  branch via jsDelivr), the user's program compiles to WebAssembly
  in-browser, and output comes from the WASM stdout buffer. Four
  examples (hello, fib, sum, dice-with-stdlib-import), each verified
  end to end through the same pipeline the page uses. JS syntax-checked
  with node --check. End-to-end run in a real browser is NOT verified
  here (no browser run was available); the page needs one open to
  confirm Pyodide loading. WASM-subset limits are stated on the page:
  imports work only for subset-safe stdlib files (rand/dates verified;
  files using split/structs/float-printing fail the whole program
  because the backend compiles every imported function).
- HTTP server: six new builtins (native only) — http_listen,
  http_accept, http_read_request, http_respond, http_respond_status,
  http_close — plus stdlib/http_server.fg (path parsing, serve_n)
  and examples/http_server_demo.fg (routes / -> greeting,
  /health -> ok, else 404). Verified live: curl returned 200/200/404
  with correct bodies and Content-Lengths, server log showed all
  three routes, clean shutdown after 3 requests, 300 bytes total
  (recomputed by hand: 116 + 85 + 99). Limits, stated: one request per
  connection, single read up to 8191 bytes, no TLS, no chunked bodies,
  IPv4 0.0.0.0. Adding a builtin touches FOUR places, not one:
  checker types, infer types, codegen call mapping, and (for str
  results) the fresh-string list — the first build failed on exactly
  this (emitted `void fd`) until infer was updated.
- Regex: stdlib/regex.fg, a backtracking engine in pure Jal Pari —
  literals, `.`, `*` `+` `?` with backtracking, classes with ranges
  (a-z/A-Z/0-9 via alphabet-position lookup, since the language has
  no char-to-int conversion), negation, \d \w \s, literal escapes,
  ^ $ anchors; regex_match / regex_find / regex_full_match.
  examples/regex_demo.fg: 36 checks, all pass, including backtracking
  (a+a on "aaa", a*ab on "aab"). NOT supported, matched literally
  instead: groups (...) and alternation | (no closures/function
  values to represent them). Ranges outside the three alphabets never
  match. Worst case is exponential (classic backtracking).
- Registry packages: packages/ ships seven real packages, each with a
  demo main that checks its own values and a smoke test — units,
  money (integer-paise math, hand-built int-to-string), geometry,
  interest (simple/compound/EMI), roman (1..3999, both directions),
  bases (binary/octal/hex, both directions), dice (on stdlib rand).
  Remote flow verified end to end against a local registry server:
  all seven published, list-remote showed all seven, a fresh consumer
  package add-remote'd units@0.1.0 and ran it (5 km = 3.10685 miles,
  100 F = 37.7778 C). Public hosting still needs the maintainer's
  VPS/Render/Fly account + domain + HTTPS.
- VS Code extension: packaged as editors/vscode/forge/forge-1.0.0.vsix
  (verified contents: displayName "The Jal Pari Language", 1.0.0,
  publisher jalpari, updated grammar). Grammar gained the missing
  keywords (enum, extern, spawn, match) and the new builtins. The
  extension is intentionally client-free (grammar + config); the LSP
  server (forge.py lsp) works with any LSP client. Marketplace publish
  needs the maintainer's publisher account.
- Benchmarks: docs/BENCHMARKS_VS.md + tools/bench_vs/run_bench.py —
  same algorithm in Jal Pari, Python, Go, Rust, C; medians of 3;
  results verified equal across languages. Jal Pari is ~31x Python
  on fib(35), ~49x on array_sum, ~259x on matmul 128; in the compiled
  cluster with Go/Rust/C (within ~2-4x of C, trading places with Go
  and Rust run to run on this noisy VM). Two findings kept: (1) the
  first loop task was deleted by Rust/C compilers (closed form),
  which is why the task is now runtime-array data; Jal Pari safe
  mode does NOT fold it (checks block it), fast mode DOES (0us) —
  mechanism verified both ways. (2) Jal Pari prints floats at 6
  significant digits, so its matmul checksum displays rounded.
- CI: .github/workflows/ci.yml verified current (suite + formatter
  + ecosystem example; node is preinstalled on ubuntu-latest, big32
  checks are compile-only). Upload still blocked: token lacks
  workflow scope (403, as before) — needs a token fix or a web-UI
  upload.
- Gotchas found by this batch (all fixed, all verified after fixing):
  a Jal Pari fn named `close` collides with libc close() in the
  generated C; the INT_MIN literal overflows (9223372036854775808 >
  i64 max — compute it as 0 - 9223372036854775807 - 1); args()
  excludes the program name; the WASM backend compiles every
  imported function, so one unsupported construct fails the import;
  a demo file named rand.fg shadowed its own stdlib import.

## 0.7.0 — 26 Oct 2026 — "Build everything open": debugger, binary I/O + images, stacked convs, curriculum RNN, big32 structs + soft-float, WASM strings/arrays, fuzzer, big TinyStories run

- Source-level debugger: `forge.py build --debug`
  adds `-g` and the code generator emits per-statement
  `#line` directives naming the Jal Pari file (main
  file AND imported helpers — verified with readelf's
  line table). Without `--debug` the C has no `#line`
  at all. Caveat: -O2 inlining merges addresses, and
  main's prologue maps to the C file (docs/DEBUGGING.md).
- Binary I/O + images: new builtins `read_bytes` /
  `write_bytes`; `stdlib/image.fg` loads PPM P3 and
  24-bit uncompressed BMP, grayscales, saves PPM P3.
  Verified: BMP == PPM on the same 2x2 image, gray0 =
  0.299, gray3 = 1. PNG/JPEG NOT supported (they need
  inflate/DCT) — stated, not hidden.
- Tape-native im2col (op 21) + stacked convs:
  `cnn_conv2d_tape` lets conv layers stack. Two-conv
  net on 8x8 cross-vs-border: 0.5 -> 1.0. Found by
  running: lr 0.05 oscillates on the deeper net (loss
  frozen at ln 2 with exact gradients); lr 0.01 trains
  it. The demo documents this.
- Curriculum RNN: `examples/rnn_curriculum_demo.fg`
  stages len 3 -> 5 -> 8 with weight transfer; all
  three reach 100% held-out. The 0.6.0 len-8 wall is
  cracked, not worked around.
- big32 structs: local struct variables as consecutive
  frame slots (int/bool/str fields), field reads/writes,
  struct copies; params/returns still rejected.
  Verified on the Python model AND Icarus Verilog.
- big32 soft-float v1: float literals/vars, [float]
  arrays, + - * via forge_fadd/forge_fmul helpers in
  exact 27-bit integer arithmetic with
  round-to-nearest-even. Verified: 12/12 demo checks
  and a 60-case randomized differential test vs
  Python float32, 60/60 on model AND Verilog. Two
  real bugs found and fixed by that fuzzing (the
  subtraction borrow, and the carry-shift sticky
  fold); one test-generator bug found too (pool
  values must be float32-rounded before computing
  expected values). NOT yet: division, ordered
  comparisons, float printing, int<->float casts,
  subnormal fidelity, NaN/Inf.
- WASM strings + arrays: `str` and flat `[int]` /
  `[float]` / `[bool]` / `[str]` with literals,
  concat, `==`, len, indexing, index-assign, push
  (realloc-by-copy), params/returns, fail/assert.
  One exported memory, bump allocator, no free/GC.
  Verified: demo output byte-identical to native.
  Divergence stated in docs/WASM_STRINGS.md: push
  through a WASM parameter DOES reach the caller
  (native push to a parameter does not).
- Fuzzer: `tools/fuzz.py` — seeded valid-by-
  construction programs, safe-vs-fast differential,
  50/50 OK on the default run, 200/200 OK on a
  longer run (seeds 1000-1199). No compiler bugs
  found; corpus dir stays empty until a failure
  appears.
- Big TinyStories run: 2000 stories, 150,000 words,
  vocab 2000 (UNK 3.7%), 153,744 params, 9000 steps,
  87.7 ms/step. Held-out ppl 2128.55 -> 651.44.
  Honest result: much better, still NOT fluent —
  greedy output loops on "collecting", sampled
  output is word salad with structure. Fluent
  generation needs far more scale, not another
  small-model run.
- Correction, carried from the 0.6.0 notes: earlier
  "wasm + big32 suites passed" claims were wrong —
  `tests/run_tests.py` ignores CLI arguments, so
  those runs executed the NATIVE suite twice. The
  suite now has real checks: big32 build checks for
  both demos and a node-based WASM output comparison
  (skipped only when node is absent). WASM/big32
  execution stays verified manually against node and
  the big32 model + Verilog.

## 0.6.0 — 26 Oct 2026 — Ecosystem batch: import dedup, RNN/CNN/classical ML, preprocessing, metrics, CSV, dev libraries

Fixed (compiler, the ecosystem blocker):
- `forge_lang/compiler.py` `load_program` now keeps a
  true visited set instead of clearing it on return.
  Diamond imports used to include a shared file twice
  and fail with "duplicate struct 'Tensor'", which
  forced every library to avoid shared imports and
  made libraries uncombinable. Now nn.fg +
  tensor_autograd.fg (and any other combination)
  compile together; verified by
  examples/import_dedup_demo.fg (tensor loss 0.693147
  trained one Adam step, 1.0 -> 0.99).

Added (tensor autograd, ops 17-20):
- t_maxpool2d, t_sigmoid, t_tanh, t_mse_loss in
  stdlib/tensor_autograd.fg, each backward rule
  checked against finite differences
  (examples/tensor_ops2_demo.fg: sigmoid 6.3e-13,
  tanh 1.2e-11, maxpool routes exactly to argmax
  cells, other cells 0).

Added (ML libraries, all verified by demos):
- stdlib/rnn.fg: LSTM/GRU/plain-RNN cells on the
  tensor tape (out-parameter idiom: cells return
  the tape and write new state ids into an `out`
  array; the new hidden state is also the tape's
  last node). Demo: first-bit memory over 5 steps,
  0.44 -> 1.0. Honest limit found by running: the
  same task at length 8 stalls at chance from
  random init even with forget-bias init — a known
  LSTM optimisation difficulty, not a library bug
  (all cell ops finite-difference checked; lengths
  3 and 5 reach 100%).
- stdlib/cnn.fg: im2col conv + tape maxpool. Demo:
  8x8 cross-vs-border with noise, 0.5 -> 1.0.
  Limit: conv input must be raw image data (first
  layer); stacking convs needs a tape-native
  im2col op, documented in the file.
- stdlib/ml_classical.fg: logistic regression
  (tape + inline Adam), k-NN, k-means. Demo:
  purity 1.0, knn 1.0, logreg 1.0 on synthetic 2D.
- stdlib/preprocess.fg, metrics.fg, csv.fg:
  standardisation, min-max, one-hot, deterministic
  splits, vocab builder; accuracy, confusion,
  precision/recall/F1, MSE/MAE/R2; plain CSV load
  (no quoted commas). Demo: real UCI Iris
  (data/iris.csv, 150 rows) end to end, test acc
  0.933333, macro F1 0.937322.
- Tensor checkpoint demo: nn checkpoints round-trip
  a tensor model with loss diff 0.

Added (developer libraries):
- stdlib/test.fg, log.fg, cli.fg, collections.fg
  (checks, leveled logging, CLI parsing, stacks
  and sets), exercised in examples/dev_demo.fg.

Docs: docs/ECOSYSTEM.md 0.6.0 section (library
table, first-ML-project walkthrough, honest
limits). README Ecosystem section updated.

Still NOT done: fluent generation, GPU training
run (code only), WASM strings/arrays, big32
floats/structs, source-level debugger, self-hosting
compiler, registry host, CI upload, repo rename,
PyPI publish, image/binary data loading, conv
stacking, long-horizon RNN training.

## 0.5.0 — 26 Oct 2026 — Engine batch: tape freeing, tensor autograd, KV-cache, scaled training

Fixed (compiler, the 0.4.0 leak):
- `forge_lang/codegen.py` now frees a block's variables
  when the block ends (`emit_free_frame`, applied to
  Block, If arms, While and For bodies). Before this,
  every array or struct created inside a loop body leaked
  once per iteration — measured on a tape loop: 1,000
  arrays allocated, 0 freed. After: 1,000 allocated,
  1,000 freed, and the scalar TinyStories program trains
  all 3 epochs in ONE process (previously OOM-killed
  twice). A subtlety found while fixing: Assign re-adds
  its target to the current frame even when declared
  outside it, so a frame frees only names absent from
  outer frames — otherwise the same value is freed twice
  (caught by a double-free in testing, fixed before ship).
- `examples/gpt_tinystories.fg` now trains 3 epochs in one
  process by default (resume still works). Single-process
  run 26 Oct 2026: train losses 4.98375, 4.49469, 4.41384;
  held-out loss 6.98368 -> 5.95341, perplexity 1078.88 ->
  385.06. Note: this differs from 0.4.0's 247.39 because
  the old split-process runs reset Adam's moments every
  epoch — an accidental regulariser. The new number is
  the methodologically cleaner one; both are recorded.

Added (tensor autograd):
- `stdlib/tensor_autograd.fg` — a tensor-level tape: one
  node per tensor op (matmul, add, bias, transpose,
  softmax, causal softmax, GELU, layernorm, mul, scale,
  gather, cross-entropy, ReLU, col-slice, concat-cols,
  reshape), with exact backward rules. Every rule is
  checked against central finite differences in
  `examples/tensor_autograd_demo.fg` (all diffs ~1e-9,
  and the demo fails itself if any diff exceeds 0.01).
- `stdlib/tgt.fg` — the gpt2 transformer rebuilt on
  tensor autograd (fused QKV, tied head, 12,608 params at
  the small size), plus tensor Adam and grad clipping.
- `examples/tgt_tinystories.fg` — same data and sizes as
  the scalar run: forward 100 nodes (scalar: 221,844),
  1500 steps in 6.5 s (4.35 ms/step), held-out loss
  6.30804 -> 5.64615, perplexity 548.97 -> 283.20.
  Sampled generation is still word salad; greedy still
  collapses (now on <unk>). Fluency is NOT claimed.

Added (KV-cache for gpt2):
- `stdlib/inference_gpt2.fg` — plain-float KV-cache step
  for any gpt2 layout (blocks, heads, separate Q/K/V).
  `examples/inference_gpt2_demo.fg` verifies it against
  full-sequence forward: max logit diff 4.44e-16
  (float rounding only). Generation past the trained
  sequence length clamps positions to seq-1 — a
  documented approximation, not a silent model change.

Added (scaled training):
- `tools/prepare_tinystories.py` gains `--out-dir`
  (default `data`); `data_scaled/` holds 500 stories,
  75,000 words, 1000-word vocab, UNK 8.5%.
- `examples/tgt_tinystories_scaled.fg` — 2 blocks,
  4 heads, d=32, hidden=64, seq=16 words, 49,664 params,
  1500 strided windows (stride 8) x 3 epochs: train
  5.45016, 4.94801, 4.86257; held-out (offset 60000)
  loss 7.02007 -> 5.24241, perplexity 1118.87 -> 189.13;
  117.6 s total, 26.1 ms/step, forward 136 nodes.
  Sampled output is still salad order, with more
  plausible fragments than at the small size.

Added (ecosystem, all verified by running):
- `docs/BENCHMARKS.md` — dot(5000): Jal Pari 8 µs,
  NumPy 29 µs, Python loops 788 µs; matmul 64x64:
  Jal Pari 615 µs, NumPy 343 µs (BLAS wins, stated
  plainly), Python 476,501 µs.
- `web/landing/index.html` — static landing page with
  the verified numbers and honest limits.
- `setup.py` + `pyproject.toml` + `bin/jalpari-pip` —
  `pip install .` verified in a clean venv
  (`jalpari-pip --version`, demo runs from another cwd).
  PyPI publication still needs the maintainer's account.
- `docs/DEBUGGING.md` — gdb-on-emitted-C recipe,
  allocation counters, and the missing piece (see below).
- `examples/cuda/mlp_train.cu` — GPU SGD trainer for
  XOR using only the verified square-matmul wrapper.
  CODE ONLY, never compiled or run (no nvcc/GPU here);
  needs a Kaggle session with Jayant's token.
- `examples/cuda/kernel.cu` comment corrected: the
  transformer kernels WERE verified on Kaggle T4 in
  0.3.0 (the old "not yet run" comment was stale).

Still NOT done (stated, not implied):
- Fluent generation; GPU training run (code exists,
  run needs a Kaggle token); WASM strings/arrays (the
  backend is 259 lines with no linear memory at all —
  needs memory + a bump allocator + string/array ops,
  a backend rewrite, not a patch); big32 floats/structs
  (the core is integer-only, no FPU — a core extension);
  a source-level debugger (AST nodes carry line but not
  file, so `#line` mapping would misattribute stdlib
  code — needs file tracking through the parser);
  self-hosting compiler; public registry host, CI upload
  and repo rename (maintainer's clicks/accounts);
  PyPI publication; Mojo/PyTorch benchmark numbers
  (neither installed here).

## 0.4.0 — 26 Oct 2026 — TinyStories word GPT

Added:
- `tools/prepare_tinystories.py` — downloads the first 200
  stories of roneneldan/TinyStories (train split) via the HF
  datasets-server rows API, cleans them (lowercase, apostrophes
  removed, other non-letters become spaces), and writes
  `data/tinystories_vocab.txt` (500 words + <unk>), `data/`
  `tinystories_ids.txt` (24,000 word ids) and a provenance
  README. UNK rate in the kept words: 14.8% (28.5% at 200
  words — the reason vocab went to 500).
- `examples/gpt_tinystories.fg` — word-level GPT on that data,
  reusing stdlib/gpt2.fg: 2 blocks, 2 heads, d=16, hidden=32,
  seq=8 words, 500-word vocab, 12,608 params. Adam lr 0.02,
  clip 1.0, 500 strided windows (stride 4, first ~2000 words)
  x 3 epochs. Held-out test (20 windows from word offset
  20000, later stories never trained on): loss 6.98368 ->
  5.51097, perplexity 1078.88 -> 247.39 (a real 4.4x
  generalisation gain, not a training-set fit). Epoch
  training losses: 4.98375, 4.64674 (the third epoch's
  average was lost when its process was OOM-killed during
  the eval phase — see below — but its checkpoint is the
  one evaluated here).
- `examples/gpt_tinystories_eval.fg` — eval-only companion:
  loads the checkpoint and reports test loss + generation
  in its own process.
- `examples/tinystories_load_demo.fg` — suite check that the
  data files load and parse (words = 24000, vocab = 500).

Generation (from "once upon a time there was a little",
30 words): greedy still loops ("cake cake cake ...");
sampled (temp 0.8, seed 123) gives real TinyStories words
in salad order ("some needed smiled kept lot herself toys
lot careful feel idea ..."). Honest verdict: upgraded from
letter salad to word salad — the perplexity gain is the
solid result; fluent sentences are NOT claimed.

Found by running (the important limitation of this batch):
- The native backend retains each training tape's arrays,
  so one process running 1500 steps x ~221k nodes grows
  until the VM's OOM killer ends it (killed during epoch
  1 of the original single-process run, and again during
  the eval phase of the 3-epoch run). Training is therefore
  split into one-epoch processes with checkpoint resume
  (`forge run examples/gpt_tinystories.fg`,
  `... resume`, `... resume final`), and eval runs as its
  own process. Tape-memory freeing is the open compiler
  fix for 0.5.0, alongside tensor-level autograd.

Not yet done: fluent generation (needs far more data,
params and steps — OpenMythos 44M on the same dataset took
4,850 steps to reach fluent samples), GPU training loop,
tensor-level autograd, KV-cache for the gpt2 layout, public
registry host, CI upload, repo rename.

## 0.3.0 — 26 Oct 2026 — Scaled GPT + GPU-verified kernels

Added:
- `stdlib/gpt2.fg` — generalised transformer: any blocks, any
  head count, any vocab/seq/hidden sizes, with a computed param
  layout (no hard-coded offsets from gpt.fg)
- `examples/gpt_scaled.fg` — 2 blocks, 2 heads, d=16, hidden=32,
  seq=16, 29-char vocab, 5200 params, on a 411-char story:
  training loss 2.559 -> 2.364 over 3 epochs (200 windows each),
  held-out perplexity 58.1 -> 53.9 (test windows 320..327).
  Generation still loops (greedy) / rambles (sampled) — scale
  is in architecture and evaluation now, not in fluent text.
  Checkpoint save/load verified (diff ~8e-07, 6-decimal text).
- GPU kernels VERIFIED on real hardware: Kaggle notebook v4,
  2x Tesla T4, driver 580.178.04, nvcc 12.8.93 — dot 70, matmul
  19 22 43 50, embedding 1 0 0 1 1 0, layernorm ±0.999980,
  attention 1.0/0.0, 0.330238/0.669762, 0.802224/0.197776,
  half matmul 19 22 43 50 — matching simulation to 6 decimals.

Fixed in this batch (both found by running, not by reading):
- Training diverged to NaN at the larger scale: a softmax
  probability can underflow to exactly 0, and log(0) poisons
  the tape. g2_loss now adds 1e-9 before the log.
- The fp16 kernel did not compile on the first GPU run:
  `__half2double` does not exist in CUDA; fixed to
  `(double)__half2float(...)`. Notebook v3 failed to build;
  v4 is the verified run.

Not yet done: fluent generation (needs far more data and
params than 5200 on 411 chars), GPU training loop (kernels
only so far), multi-layer library packaging, public registry
host, CI upload, repo rename.

## 0.2.0 — 26 Oct 2026 — Mojo-level ML stack (tensors, autograd, tiny GPT)

The language gains the pieces that make people use a language for
LLM work, at small-model scale. Everything below is verified by
the test suite or by a recorded run; the limits are listed, not
hidden.

Added:
- `stdlib/tensor.fg` — Tensor (flat row-major + shape), matmul,
  transpose, reshape, softmax, GELU, argmax (demo: 19 22 43 50)
- `stdlib/autograd.fg` — real reverse-mode scalar tape; gradient
  matches a numeric gradient exactly at printed precision
  (df/dx 10.0452 vs numeric 10.0452), plus a sqrt node so
  LayerNorm backward is exact
- `stdlib/nn.fg` — Linear, LayerNorm, single-head causal
  attention, MLP, Adam/AdamW, cosine/step/warmup schedules,
  gradient clipping, checkpoints (float text, 6 decimals),
  int8 quantization, greedy/temperature/top-k/top-p sampling,
  and a new `parse_float` builtin (needed for checkpoint loads)
- `stdlib/tokenizer.fg` — character tokenizer + real BPE
  (23 chars -> 13 tokens on the demo text, round-trips)
- `stdlib/dataset.fg` — sliding-window next-token sequences,
  train/test split, batching, shuffling
- `stdlib/gpt.fg` + `examples/tiny_gpt.fg` — a 1-block, 1-head
  transformer (d=8, hidden=16, tied head, 776 params) trained by
  autograd + Adam on "hello world hello jal pari": loss
  2.274 -> 0.360 over 20 epochs (min 0.199 at epoch 16), in ~5 s.
  Generation is the honest weak point: greedy loops on spaces,
  temperature sampling gives varied gibberish — a 776-param model
  on one sentence is a training proof, not a language model.
- `stdlib/inference.fg` — KV-cache inference step: step-by-step
  output matches a full-sequence forward exactly (diff 0);
  quantized step differs by at most 0.026 on the demo step
- `tools/import_torch_weights.py` — imports weights from a text
  file or (with torch installed elsewhere) a .pt state dict into
  Jal Pari functions; text path verified end to end
- CUDA: fused attention, LayerNorm, embedding and fp16 matmul
  kernels added to `examples/cuda/kernel.cu`, verified by
  `tools/simulate_cuda.py` (attention 1.0/0.0, 0.330/0.670, ...)

Not yet done, and not claimed:
- The new CUDA kernels have NOT run on a real GPU yet (no nvcc
  here; a Kaggle T4 run is the remaining step, as before)
- No torch in this VM, so the .pt branch of the importer is
  provided but not run here; the text branch is verified
- No 1B model, no distributed training, no MLIR compiler — the
  beachhead is small models that train and run natively

## 0.1.0 — 26 Oct 2026 — First Jal Pari market release

Formerly Forge v2. The language itself is unchanged in this
release; this release is about making it installable and usable
by a stranger.

Added:
- `jalpari` command (`bin/jalpari`) — `jalpari run`, `jalpari --version`
- `jalpari --version` / `jalpari version` — prints "The Jal Pari Language 0.1.0"
- `scripts/install.sh` — one-command user install, checks python3
  and cc, symlinks into `~/.local/bin`, verifies with the demo
- This changelog

Included from Forge v2 (all verified by tests, see README.md):
- Types int/float/bool/str/[T], structs, enums + match, generics,
  Option/Result, `?` operator, threads, C FFI, HTTP/HTTPS, file I/O
- Safe mode (checked arithmetic, bounds-checked) and fast mode
- ML: dot/matmul, linear regression training, MLP XOR training
  by backprop (loss 0.558973 -> 0.000267766)
- Backends: native C, big32 RISC-V (simulation), WASM (int/float/bool),
  CUDA kernels (verified on Kaggle Tesla T4, dot 70, matmul 19 22 43 50)
- Tooling: `forge pkg`, `forge fmt`, `forge lsp`, `forge repl`, `forge doc`
- Examples: hello, matrix, todo CLI, Teju special, dates/rand,
  SQL/table/KV demos, high-school guide, web playground, book starter
- Dedicated to Tejaswini — Jal Pari (see DEDICATION.md)

Known limits in 0.1.0 (honest, not hidden):
- No public package registry host yet (server + Dockerfile exist)
- WASM: no strings/arrays yet; big32: no floats/structs yet
- No debugger, no fuzzing, no self-hosting compiler yet
- CI workflow is local only until uploaded via GitHub web UI
  (token lacks workflow scope)
- Repo is still called RED-MOON- on GitHub; renaming it is a
  web-UI step, and the tool file is still `forge.py` for
  compatibility — `jalpari` is the new market name for it.
