# Self-Hosting Plan — Qasida compiles itself (no Python)

Goal (Jayant's word, 7 Nov 2026, "Do it then"): remove Python from Qasida
by rewriting the compiler IN Qasida, so Qasida compiles itself.
The compiler today is ~14,754 lines of Python (forge_lang/*.py).
This is a multi-slice project, not one session. Each slice lands
verified against the Python compiler's behaviour.

## Why Python is there at all
Python let us build a working compiler fast (days, not months).
The compiler is Python, but Qasida programs compile to native C
and run as fast binaries — no Python at runtime. Python is the
bootstrap, not the destination. Self-hosting removes it.

## Current state (7 Nov 2026)
- `examples/selfhost_mini.fg` (234 lines): lexer + expression parser
  IN Qasida (precedence, parens, unary minus, let bindings, eval).
  Evaluates `let x = 2 + 3 * 4; x * 2 + 1` to 29. Prototype only —
  no checker, no codegen, no statements.
- Python compiler sizes: lexer 175, parser 715, checker 2680,
  codegen 4377, cli 277, ast_nodes 345 lines.

## Slices (in order)
1. **Full hosted lexer** (`examples/selfhost_lex.fg`) — DONE first.
   All token types matching forge_lang/lexer.py: keywords (27),
   two-char + one-char operators, INT (decimal/hex/binary/octal,
   underscores), FLOAT, STR (escapes), // and /* */ comments,
   EOF, line/col, lexer errors via fail(). Verified by
   token-for-token comparison against the Python lexer on real
   .fg sources.
2. **Full hosted parser** — statements (fn, let, if/else, while,
   for, return, struct, enum, match, import, extern, spawn,
   trait/impl, type/newtype, break/continue, defer) producing
   the same AST shape as the Python parser. Verified by
   parsing real .fg files and comparing AST structure.
   AST representation: a single recursive `Node` struct
   (kind tag + name/ival/fval/sval/bval + kids + line/col),
   one kind per Python AST node type (~45 kinds). The parser
   is recursive-descent over the hosted lexer's tokens,
   mirroring forge_lang/parser.py's precedence chain
   (|| -> && -> | -> ^ -> & -> == != -> < <= > >= -> << >> ->
   + - -> * / % -> unary -> postfix -> primary, ranges `..`
   loosest). Verification: the hosted parser dumps a
   canonical S-expression of the AST; a Python script dumps
   the same form from the Python parser; the two are diffed.
   Sub-slices: 2a core (expressions + let/if/while/for/
   return/break/continue/assign/expr-stmt + fn/struct/import/
   extern + types) — the constructs in most real code;
   2b the rest (enum, match, spawn, scope, defer, trait,
   impl, type, newtype, readonly, opaque).
3. **Hosted checker** — the big one (2680 lines of Python).
   Type checking, inference, ownership/move rules, pin/alloc
   gates. Split into sub-slices (expressions, then statements,
   then generics/structs, then the rest). Verified by
   check-pass / check-fail agreement with the Python checker
   on the test corpus.
   - Slice 3a DONE 8 Nov 2026: `examples/selfhost_check.fg`
     (expressions: literals, vars, binops, arrays, tuples,
     field/index, calls, casts, ranges, struct literals, try;
     statements: let/if/while/for/return/assign/expr-stmt;
     C-keyword name rejection). Driver
     `examples/selfhost_check_test.fg`; verifier
     `~/workspace/blackmoon-iso/verify_selfhost_check.py`;
     corpus `~/workspace/blackmoon-iso/selfhost_check_tests/`
     (8 valid + 10 invalid). VERIFIED 18/18 pass.
     Gotchas: `trim` and `starts_with` are builtins (cannot
     redefine); no `pop` builtin (rebuild arrays to truncate);
     Assign for a plain variable stores the name in n.name and
     the RHS as the ONLY kid; `int_to_str` is a stdlib fn in
     nn.fg, NOT a compiler builtin. Also moved `main` out of
     selfhost_parse.fg into selfhost_parse_test.fg (the parser
     still verifies 2/2 on spot check) so the check driver can
     define its own main.
   - Slice 3b DONE 8 Nov 2026: `examples/selfhost_check.fg`
     grew to ~2,000 lines: generics (fn + struct type-param
     inference via unify/substitute, generic templates skipped
     until instantiation), move rules (move()/field moves,
     use-after-move, reassignment revives, branch joins),
     pin rules (pin() stmt, pinned whole-value rejection,
     in-place writes + len/for-iteration allowed), try_alloc
     gate (needs Result struct), match (enum, exhaustiveness,
     wildcard, payload bindings), spawn/scope/defer,
     break/continue loop checks, enum variant resolution.
     Corpus now 41 files (18 from 3a + 23 new). VERIFIED
     41/41 pass (hosted vs Python checker agreement).
     Gotchas: find_top() treats "<" as an opening bracket and
     never returns it — generic helpers need a dedicated
     find_lt(); Assign for a plain variable stores the name in
     n.name with the RHS as the ONLY kid; struct copy is DEEP
     (snapshots for branch joins work); no `pop` builtin;
     `mut` is a keyword (cannot be a parameter name).
     Known gaps: generic enum payload substitution; union
     match; method calls; ownership of `?` propagation.
   - Slice 3c DONE 8 Nov 2026: `examples/selfhost_check.fg`
     grew to 2,726 lines: method calls (struct impl methods,
     range builtins, opaque/trait receivers, enum variant
     construction as calls), union match (member-type arms,
     binding required, exhaustiveness), the full builtin set
     (string ops, math, file I/O, range, clock, counts,
     refcount/weak, mmap, http, ecall/csr, wrapping), statement
     builtins (push, poke32, mmap_set/close/set32, csr_write/
     set/clear), accepts() (union member + opaque-impl
     acceptance at all value sites), impl method bodies checked.
     Corpus now 62 files (41 from 3a+3b + 21 new). VERIFIED
     62/62 full corpus (hosted vs Python checker agreement).
     Gotchas: `trait` is a keyword (cannot be a variable name);
     trait methods are written WITHOUT a receiver param (the
     Python checker rejects a trait-typed param); type_matches
     needed union-member + opaque acceptance (accepts()).
     Known gaps: generic enum payload substitution; method
     calls on generic receivers; freestanding restrictions
     (hosted-only builtins not yet gated).
   - Slice 4 next: codegen (4,377 lines) — the biggest slice.
   - Slice 4a DONE 8 Nov 2026: `examples/selfhost_codegen.fg`
     (1,300 lines) + `examples/selfhost_infer.fg` (1,118 lines)
     + driver `examples/selfhost_codegen_test.fg` (34 lines) +
     generated `examples/selfhost_codegen_header.fg` (HEADER
     embedded byte-for-byte, 40,240 bytes, via
     `~/workspace/blackmoon-iso/gen_codegen_header.py`).
     DESIGN DECISION (S1): hosted infer pass — `HInfer` with
     `line:col` → type tables, cross-checked identical to
     Python `infer_types` on all 12 corpus files (248 entries);
     checker/parser untouched. Codegen: `HCodegen`, c_type,
     generate() order, c_sig, gen_func, gen_block/stmt
     (Let/Return/ExprStmt), gen_expr (literals/Var/BinOp/
     UnaryOp/Call), gen_print, c_str_literal (6 escapes).
     VERIFIED 12/12 byte-identical C + identical runtime
     (corpus `~/workspace/blackmoon-iso/selfhost_codegen_tests/`
     v01–v12) + independent spot-check 2/2 (v12, v01).
     Gotchas: `default` is a C keyword; `readonly_inner`
     doesn't exist in the checker; parse_int/parse_float emit
     forge_parse_int/forge_parse_float; checked arithmetic
     always emitted (no elimination — deferred to 4f);
     corpus rule: checked-binop operands must have unknown
     intervals (params/parse_int/call results), never
     literal-known lets. Watch: each hosted driver run takes
     ~85–100s, close to the verifier's 120s timeout — don't
     run CPU-heavy work concurrently with verification.
     Known gaps: structs, payload enums, impls, tuple/union/
     opaque values, if/while/for, method calls, most builtins
     (only print/println/len/parse_int/parse_float), float
     formatter (canonical repr spellings only), u64 range cap.
   - Slice 4b DONE 8 Nov 2026: statements (if/else-if, while,
     for-range/for-array, Assign, IndexAssign, FieldAssign,
     Break/Continue, nested Blocks, Scope, Defer LIFO).
     selfhost_codegen.fg 1,300 -> 2,071 lines (frame stacks for
     owned/defer/scope, _emit_defers machinery mirrored).
     VERIFIED 27/27 byte-identical C + identical runtime (full
     corpus v01–v27; log
     ~/workspace/blackmoon-iso/selfhost_codegen_4b_full2-*.log).
     Two slice-3 checker bugs found + fixed by 4b (IndexAssign
     typed the element instead of the array; check_stmt lacked a
     Block branch) — both proven no-ops for the slice-3 corpus
     (no IndexAssign / bare-block statements in its 62 files);
     slice-3 full-corpus regression re-run DONE 62/62 (no
     regressions). Verifier
     TIMEOUT raised 120 -> 300s: the hosted chain is slow, not
     hung (v23 profile: parse 15.5s, check 55.8s, full 124s;
     Python compile only 2.8s) — bar unchanged. Match is 4c/4d;
     Spawn is a later stage; FieldAssign is implemented but has
     NO corpus test until 4d (needs a struct value).
   - Slice 4c DONE 9 Nov 2026 (~18:00 IST): expressions —
     ArrayLit, TupleLit + TupleIndex, StructLit, Cast, Try (?),
     MethodCall (range / struct static dispatch / opaque trait
     switch), full Call arg conversion + enum variant
     construction, _str_index_cmp, fixed_checked_binop +
     fixed-width unary minus, FieldAccess struct-array fast
     path, Index struct-result/nested cases. Codegen grew
     2,071 -> 5,157 lines. VERIFIED 13/13 new files (v28–v40:
     v28–v38 via verifier, v39/v40 via direct route, same bar)
     + spot re-verification 3/3 (v07/v23/v27 after the
     global-counters fix) + slice-3 regression 62/62 after
     five checker fixes (all proven no-ops for slice 3).
     Verifier TIMEOUT raised 300 -> 600s: under the big32 Step
     29 grind (vvp ~75% CPU) the hosted driver run takes ~294s
     vs ~124s idle — bar unchanged. FULL corpus v01–v40 run
     landed 40/40, 0 fail, across 4 attempts (v01–v21, v22–v24,
     v25–v34, v35–v40) — killed twice by VM reboots, resumed
     each time from the first unpassed file (final resume3 log
     6/6). Known 4d boundaries: generic function calls,
     bare variant of a generic enum, 1-char non-ASCII literal
     in _str_index_cmp, float literals only for canonical repr
     spellings, Match (kind 20) and Spawn statement (kind 21)
     not implemented, newtype casts not accepted by the hosted
     checker.
   - Slice 4d DONE 9 Nov 2026: declarations (structs, enums, generics,
     traits/impls, imports, extern) + Match + Spawn. Codegen 5,157 →
     5,730 lines, infer 1,173 → 1,274 lines, checker 3,007 UNCHANGED.
     New corpus v41–v51 11/11 PASS; FULL corpus v01–v51 51/51 PASS
     (across two VM reboots; one regression found and fixed — v32_try:
     infer-key `line:col` collision between merged-import positions,
     fixed by `"T:"`-prefixed template keys, script fix_v32_tkey.py);
     slice-3 regression 62/62. Spawn verified by direct route
     (spawn_demo.fg, byte-identical C, 987 lines). Known 4e/4f
     boundaries: generic-enum payload substitution, 1-char non-ASCII
     literal in _str_index_cmp, float literals only for canonical
     repr spellings, newtype casts not accepted by the hosted checker,
     latent concrete-vs-concrete infer-key collisions across merged
     imports (principled fix needs file-tagged keys, i.e. parser
     changes). v52 spawn corpus file NOT written — proposal in stage
     log (workers write distinct files via write_file, main prints
     only its own lines).
   - Slice 4e DONE 10 Nov 2026 (~04:33 UTC): builtins. Only two
     real gaps existed — the hosted codegen already emitted every
     other builtin: (1) `push` full implementation (4a stub replaced,
     mirroring codegen.py:3450-3515); (2) `try_alloc` infer type
     (was "void", now "Result<[int], str>"). Plus one checker fix
     found in verification (v65): IndexAssign re-checked the base
     after resetting pinned_write_root, wrongly rejecting `a[0] = 9`
     on a pinned `a` — fixed; backup selfhost_check_4e_backup.fg is
     the first checker backup (diff vs backup shows exactly this
     change). Codegen 5,730 → 5,804 lines, infer 1,274 → 1,282,
     checker 3,007 → 3,016. New corpus v52–v63 + v65–v66 14/14 PASS;
     FULL corpus 65/65 PASS (v64 has no file by design); slice-3
     regression 62/62 (39 + 23 across one reboot). v52 spawn is now
     a permanent corpus case. No corpus coverage: try_alloc full
     emission (probe only), peek32/poke32 runtime (no safe native
     address), csr/ecall family (both Python and hosted reject on
     native, "big32 target only"), http_post (not in checker or
     Python codegen). Full run survived four VM reboots, resumed per
     protocol each time.
   - Slice 4f DONE 10 Nov 2026 (~21:05 IST): ownership/frees + checked-arithmetic elimination. Ownership audit found the hosted codegen already mirrored Python — zero ownership code changed; proof is the v79–v91 corpus. Elimination added the _facts interval table, _check_cache dedup, and Python's exact reset points (per-statement cache reset, facts cleared at loop boundaries, per-arm save/restore in match, hull join on if). Codegen 5,804 → 6,494 lines; infer/checker unchanged (1,282 / 3,016). New corpus v67–v91 25/25 PASS; FULL corpus 90/90 PASS, 0 fail (v64 has no file by design); slice-3 regression 62/62; ASan 11 clean + 2 leak-only (both leaks are Python's own emission — v90 union-binding leak, v91 opaque fresh-copy leak — reproduced byte-for-byte, zero memory-safety violations). One real bug fixed (hosted interval-math overflow on INT_MAX+1; overflow-free range predicates, differential vs Python _binop_safe 21,780/21,780 agree). 5 VM reboots during verification; parallel attempt abandoned (600s timeouts under post-reboot load), serial is the safe bar. Known boundaries carried over: generic-enum payload substitution, 1-char non-ASCII literal in _str_index_cmp, float literals canonical repr() only, newtype casts, latent concrete-vs-concrete infer-key collisions (parser change needed — NOT in 4f).
   - Slice 4g IN PROGRESS 10 Nov 2026 (~21:06 IST): full verification + freestanding. Starting state verified: codegen 6,494 lines, infer 1,282, checker 3,016; corpus 90 files (v64 has no file by design); 4f closing proof re-checked from logs (full 90/90 across master 28 + A/B 4+4 + S 54, the 4 FAILs being the parallel TIMEOUT artifacts v12–v15, all subsequently PASSed serially; regression 62/62; ASan 11 clean + 2 leak-only). FREESTANDING DONE + VERIFIED: checker 3,016 → 3,222 lines (freestanding flag, _heap_backed predicate + exact Python _heap_error wording, 27-name blocklist, print/mmap/push/spawn/scope/drop/extern rejections; backup made FIRST); codegen 6,494 → 6,597 lines (freestanding flag, cg_freestanding_header() via extended generator, union/tuple guards, array-helper skip, _start + qasida_main + exit_group 231, main signature, argv/join/free skips, emit_free_owned early return, gen_expr backstop guard); driver + verifier take --freestanding. Corpus v92 noheap demo (byte-identical C + -nostdlib run exits 42), v93 CRC kernel, v94 allocator kernel (byte-identical C); negatives e92 strlit, e93 println, e94 push (all both-reject). v95 skipped: kernel_clock uses csr_set, rejected even by plain Python check. Slice-3 regression 62/62 (one reboot at 61/62, resumed). v90/v91 leak re-confirmation: both still byte-identical (42,704 / 48,651 bytes); ASan leaks 2 sites each (3+3=6 bytes v90, 5+5=10 bytes v91) — the pinned Python leaks, not hosted-only. FINAL FULL VERIFICATION LAUNCHED ~21:35 IST: serial over the 90 native files against the 4g codegen (runner run_4g_final.sh, persistent + resume-safe, master log selfhost_codegen_4g_full.log, ETA ~9h). Freestanding 6/6 + regression 62/62 already green against this codegen.
4. **Hosted codegen** — the biggest one (4377 lines of Python).
   Native C emission. Split by construct. Verified by
   byte-comparing emitted C (or behaviour-comparing compiled
   programs) against the Python codegen.
   - DESIGN DECISION (8 Nov 2026, slice 4 start): Python's own
     pipeline is check -> infer -> codegen. The `types` map the
     codegen consumes (`expr_type` = `self._types.get(id(expr),
     "int")`, codegen.py:2355) comes from a SEPARATE 391-line
     pass, forge_lang/infer.py — NOT from the checker. The
     hosted port mirrors this exactly: a hosted infer pass
     (`examples/selfhost_infer.fg`) walks the hosted AST and
     produces the type table; the hosted checker stays
     UNTOUCHED (slice 3 verification intact) and the parser
     dump stays untouched (no new Node field). Keys: Qasida
     has no `id()`, so the table is keyed by node position
     ("line:col" -> type string) — every expression node has
     a unique source position. Assumption to verify
     empirically: no two expression nodes share a position
     with different types (parser-created synthetic nodes
     would break it; the byte-compare verifier will catch it).
     Driver chain: lex -> parse -> check -> infer -> codegen.
   - GENERICS (known 4d design point, deferred): Python's
     infer skips generic templates; concrete instantiations
     are appended to program.funcs/structs by the Python
     checker's epilogue. The hosted checker returns bool
     only and appends nothing — stage 4d must decide where
     hosted instantiations come from (most likely a
     `check_program_augmented` entry returning the program
     with instantiated funcs/structs appended, mirroring
     the Python checker epilogue).
   - STAGES: 4a skeleton (driver, c_type, header, main,
     literals, let, arithmetic, println/print, return) ->
     4b statements -> 4c expressions -> 4d declarations
     (structs, enums, generics, traits/impls, imports,
     extern) -> 4e builtins -> 4f ownership -> 4g full
     corpus + freestanding if time permits. Each stage
     verified by `verify_selfhost_codegen.py` (byte-compare
     hosted emit vs `forge.py emit`, plus compile-both and
     compare program output) before the next starts.
     Non-freestanding native path (mode="safe") first;
     freestanding/big32 is a later sub-slice.
   - STATUS 8 Nov 2026: slice 4 AUTHORIZED ("Complete the
     codegen"). Design decided; study subagents fanning out
     over codegen sections; stage log at
     `~/workspace/blackmoon-iso/selfhost_codegen_stage_log.md`.
5. **Hosted driver (cli)** — argument handling, file reading,
   invoking lex -> parse -> check -> codegen -> cc. Then the
   bootstrap: compile the hosted compiler with the Python
   compiler, use the hosted compiler to compile itself, and
   compare outputs. When the hosted compiler can compile
   itself and produce identical binaries, Python is gone.
   - CC-INVOCATION DECISION (10 Nov 2026, Jayant's "Do
     whatever you want" — his discretion, no stop-and-ask):
     the hosted driver invokes cc itself via a NEW builtin,
     `run_command(cmd: str) -> int` (C system(), returns the
     command's exit code, -1 if it could not run or died by
     signal; native-only, rejected in freestanding/big32/WASM).
     Emit-only + shell-compiles was rejected: it cannot match
     Python's `run`/`build` behaviour (exit codes, cc-failure
     text) and would leave the driver half a CLI. Two more
     builtins ride with it because error parity needs them:
     `fail_compile(msg: str)` (statement; stderr
     "qasida: error: <msg>", exit 1 — the hosted
     lexer/parser/checker swap their fail() sites to it, since
     fail() prints "qasida: runtime error: ..." and cannot
     match the CLI's "qasida: error: ..." prefix) and
     `eprintln(msg: str)` (statement; msg + newline to stderr,
     no exit — for argparse-style usage errors, exit 2, and cc
     warnings on successful builds). All three need the
     Python-side (checker/infer/codegen/header) AND the
     hosted-side (checker/infer/codegen) implementations,
     verified by byte-compare like everything else. Gates:
     all three on the freestanding blocklist + big32/WASM
     rejection, same as other OS builtins. Driver scope:
     check, emit, run, build (native + --freestanding +
     --mode + -o + --keep-c) + --version; deferred: fmt, doc,
     lsp, repl, pkg, test, stack, emit-big32, emit-cuda,
     emit-wasm, --debug, --target big32/wasm (each reported
     as deferred, none half-implemented). Temp files for
     run/build use clock_micros() names under /tmp (no
     tempdir builtin exists).

## Rules
- Each slice is verified against the Python compiler before
  the next starts. No slice is "done" on vibes.
- The Python compiler stays the reference and the fallback
  until the bootstrap is proven. We do not delete it early.
- Keep each hosted file runnable with `qasida run` / `forge.py run`
  so every slice is testable in isolation.
