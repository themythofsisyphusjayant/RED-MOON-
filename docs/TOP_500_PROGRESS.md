# Top-500 program tracker

The user ordered (31 Oct 2026) that all 500 items in
docs/TOP_500_FEATURES.md be added to The Jal Pari Language.

## Rules
- Work the catalog in priority order, respecting dependencies
  (closures before higher-order functions, fn values before
  sort_by, and so on). A batch may pull a small item forward when
  it is shippable on its own, but the order is never silently
  abandoned: every batch report names what was built and what is
  next.
- Every item lands only with a real verification: a test in
  tests/, a native run, or a big32 model run. No item is claimed
  from an estimate.
- The full forge test suite must stay green; a batch that breaks
  it is not done.
- Catalog statuses are updated as items land ([GAP]/[PARTIAL] to
  [HAVE], with a date note), so the catalog stays the source of
  truth.
- Nothing is pushed without the user's explicit word; completed
  batches ride the next authorized push.

## Starting counts (31 Oct 2026, verified)
- HAVE: 38 (already in, nothing to build)
- PARTIAL: 66 (thin versions to complete)
- GAP: 396 (missing)
- To build: 462

## Batch log
- Batch 1 (31 Oct 2026): #15 binary/octal literals + digit
  separators (lexer-only; tests/test_top500_batch1.py) and #61
  continue (lexer, AST, parser, checker, native, big32, WASM,
  formatter; same test file). Verified: native values, big32
  model kernel transcript 25/25/DONE halted, WASM emit,
  error cases. Noted during testing: WASM still has no For
  support at all (pre-existing gap, separate from continue).
  Counts after batch 1: HAVE 40, PARTIAL 65, GAP 395,
  to build 460. Full suite later confirmed PASS.
- Batch 2 (31 Oct 2026): #5 traits v1 (tests/test_traits_v1.py).
  trait declarations, impl blocks (trait or inherent), method
  calls with static dispatch, checker-enforced conformance.
  Verified: native run 12/14/rect/10 (incl. a chained
  field-method call), five conformance error cases, fmt
  round-trip still running, big32/WASM rejections named.
  v1 limits are in the catalog entry. Next in priority: #6
  type aliases. Counts after batch 2: HAVE 41, PARTIAL 65,
  GAP 394, to build 459. Full suite for batch 2 later
  confirmed PASS.
- Batch 3 (31 Oct 2026): #6 type aliases v1
  (tests/test_aliases_v1.py). Transparent aliases expanded in
  the checker before other checking; verified native
  (42/7/ada/36/20/bob/5), generic alias (42), enum alias (1),
  six rejection cases (duplicate, cycle, unknown target,
  struct collision, bare-generic target, alias with
  arguments), fmt round-trip, and a big32 model kernel
  transcript 42/DONE halted. Full suite for batch 3 later
  confirmed PASS. Counts after batch 3: HAVE 42,
  PARTIAL 65, GAP 393, to build 458. Next in priority: #7
  union types.
- Batch 4 (31 Oct 2026): #10 wrapping arithmetic and #11
  distinct newtypes (tests/test_wrapping_v1.py,
  tests/test_newtypes_v1.py, both ALL PASS). #10:
  wrapping_add/sub/mul/neg on native (INT_MIN/MAX edges),
  big32 (32-bit edges + wrap-to-MIN equality check), and WASM
  emit. #11: newtype decls, distinctness (assignment, args,
  arithmetic, cross-newtype casts all rejected), same-newtype
  equality, alias-underlying newtypes, fmt round-trip, big32
  kernel 42/DONE. Note: #7 union types, #8 opaque types, and
  #9 fixed-width ints are still ahead in priority order and
  are NOT skipped — they are dedicated designs (tagged values
  + narrowing; trait-hiding; new scalars everywhere), and
  #10/#11 were pulled forward as shippable under the batch
  rule. Counts after batch 4: HAVE 44, PARTIAL 65, GAP 391,
  to build 456. Next: #7 union types (design).
- Batch 4 suite check (31 Oct 2026): full `forge.py test`
  confirmed PASS after batch 4 landed (log
  forge_suite_batch4.log).
- Batch 5 (31 Oct 2026): #7 union types v1
  (tests/test_unions_v1.py, ALL PASS). `int | str` as a
  tagged tag+payload C struct; wrapping at let/assign/arg/
  return/struct-field/cast sites; match narrowing with member
  arms + bindings; str-payload copy/free discipline; big32
  and WASM gates. Full-suite regression check confirmed
  PASS (log forge_suite_unions.log). Counts after
  batch 5: HAVE 45, PARTIAL 65, GAP 390, to build 455.
  Next in priority: #8 opaque types.
- Batch 6 (31 Oct 2026): #8 opaque types v1
  (tests/test_opaques_v1.py, ALL PASS). `opaque Trait` as
  an existential: tagged struct over the implementing
  structs, tag-dispatched method calls/copies/frees, callee
  gets an owned payload copy. Native verified (Rect/Square/
  Named dispatch, copy + param passing, fmt round-trip);
  big32 and WASM gates. Full-suite regression check pending
  at that time (log forge_suite_opaques.log). Counts after
  batch 6: HAVE 46, PARTIAL 65, GAP 389, to build 454.
  Next in priority: #9 fixed-width ints.
- Batch 7 (31 Oct 2026): #9 fixed-width ints v1
  (tests/test_fixedints_v1.py, ALL PASS). i8/i16/i32/u8/
  u16/u32/u64 as distinct scalars, i64 normalised to int;
  fitting literals adapt, checked widened arithmetic,
  checked narrowing casts, struct fields, fmt round-trip;
  big32 and WASM gates. Full-suite regression check pending
  at that time (log forge_suite_fixedints.log). Batch-6
  suite note: its only failure was scope_demo (fast),
  println interleaving under load — rerun 4/4 clean, the
  known flaky concurrency-print class, not a regression
  (opaque changes touch neither scope nor printing).
  Counts after batch 7: HAVE 47, PARTIAL 65, GAP 388, to
  build 453. Next in priority: #12 sized arrays.
- Batch 8 (31 Oct 2026): #12 sized arrays v1
  (tests/test_sizedarrays_v1.py, ALL PASS). `[T; N]` as a
  distinct type: exact-count literals (compile-time,
  including empty literals), push rejected, index/len/for
  like dynamic arrays, params/returns/struct fields;
  big32 and WASM gates. Full-suite regression check pending
  at that time (log forge_suite_sizedarrays.log). Batch-7
  suite CONFIRMED PASS (log forge_suite_fixedints.log).
  Counts after batch 8: HAVE 48, PARTIAL 65, GAP 387, to
  build 452. Next in priority: #13 readonly views.
- Batch 9 (31 Oct 2026): #13 readonly views v1
  (tests/test_readonly_v1.py, ALL PASS). `readonly [T]`
  as a read-only handle: index/len/for work, push and
  index assignment rejected, mutable-to-view coercion
  within the same array kind, views as params/returns/
  struct fields; big32 and WASM gates. Full-suite
  regression check pending at that time (log
  forge_suite_readonly.log). Batch-8 suite CONFIRMED
  PASS (log forge_suite_sizedarrays.log). Counts after
  batch 9: HAVE 49, PARTIAL 65, GAP 386, to build 451.
  Next in priority: #14 never type.
- Batch 10 (31 Oct 2026): #14 never type v1
  (tests/test_never_v1.py, ALL PASS). `never` as the
  bottom type: never functions must diverge and cannot
  return, never values coerce to any expected type at
  value sites, diverging bodies satisfy the return rule;
  big32 and WASM gates. Full-suite regression check
  pending at that time (log forge_suite_never.log).
  Batch-9 suite CONFIRMED PASS (log
  forge_suite_readonly.log). Counts after batch 10:
  HAVE 50, PARTIAL 65, GAP 385, to build 450. Next in
  priority: #17 checked-cast float-to-int overflow
  rules (with #19 tuples and the #16/#18/#20 PARTIALs
  following in numeric order).
- Batch 11 (31 Oct 2026): #17 checked float-to-int
  casts v1 (tests/test_checked_casts_v1.py, ALL PASS).
  Safe mode fails on out-of-range/NaN/infinite floats;
  fast mode keeps the truncating cast; WASM already
  traps, big32 already rejects. Full-suite regression
  check pending at that time (log
  forge_suite_checked_casts.log). Batch-10 suite
  rerun in flight at that time (log
  forge_suite_never.log) after a real regression was
  found and fixed: the batch-10 edit had deleted the
  `_literal_fit_msg` def line, breaking literal-fit
  errors (bad_type.fg, diag_cast.fg). Counts after
  batch 11: HAVE 51, PARTIAL 65, GAP 384, to build
  449. Next in priority: #19 tuples.
- Batch 12 (31 Oct 2026): #19 tuples v1
  (tests/test_tuples_v1.py, ALL PASS). Fixed-arity
  heterogeneous tuples with owned elements, flowing
  through let/assignment/arguments/returns/struct
  fields; big32 and WASM gates. Also landed:
  dependency-ordered composite emission (forward
  struct references now compile) and the lexer
  tuple-index fix. Full-suite regression check
  pending at that time (log forge_suite_tuples.log)
  — this clean run also covers batches 10 and 11,
  whose earlier runs were invalidated by a mid-run
  edit race (two subprocesses imported a half-edited
  checker). Counts after batch 12: HAVE 52,
  PARTIAL 65, GAP 383, to build 448. Next in
  priority: #16 local type inference, #18
  first-class ranges, #20 void/unit consistency
  (the remaining §1 PARTIALs, in numeric order).
- Batch 13 (31 Oct 2026): #16 local type inference v1
  (tests/test_infer_v1.py, ALL PASS). Empty array
  literals infer their element type from a later
  constraining use (push, assignment, annotated let,
  call argument, return, struct field, field
  assignment); no-constraint literals fail clearly
  at the end of the function. Implementation note:
  resolution lives in the checker, not the infer
  pass — the pipeline checks before it infers, so
  infer-side rewrites would have landed too late;
  the checker rewrite is what the later infer pass
  sees. Full-suite regression check pending at that
  time (log forge_suite_infer.log). Counts after
  batch 13: HAVE 53, PARTIAL 64, GAP 383, to build
  447. Next in priority: #18 first-class ranges.
- Batch 14 (31 Oct 2026): #18 first-class ranges v1
  (tests/test_ranges_v1.py, ALL PASS). Half-open
  `a..b` values of type `range`, lazy, with len /
  contains / start / end / sum methods and for-loop
  iteration; big32 and WASM gates. Full-suite
  regression check pending at that time (log
  forge_suite_ranges.log). Counts after batch 14:
  HAVE 54, PARTIAL 63, GAP 383, to build 446. Next
  in priority: #20 void/unit consistency.
- Batch 15 (31 Oct 2026): #20 void/unit consistency
  v1 (tests/test_void_v1.py, ALL PASS). void is no
  value: allowed only as a function or method
  return type; every other use fails in the checker
  with a clear message (previously several of them
  compiled to invalid C). §1 Types/safety is now
  complete: items 1–20 are all HAVE. Full-suite
  regression check pending at that time (log
  forge_suite_void.log). Counts after batch 15:
  HAVE 55, PARTIAL 62, GAP 383, to build 445. Next
  in priority: §2 memory items — #23 defer is
  pulled forward as the next small shippable slice
  (#21 GC is the stated future direction, not one
  batch; #22 allocator-as-value follows).
- Batch 16 (31 Oct 2026): #23 defer v1
  (tests/test_defer_v1.py, ALL PASS). `defer
  call();` runs at the enclosing block's exit,
  LIFO within the block — including early
  returns, breaks, and continues, and loop-body
  defers run each iteration. Deferred calls are
  emitted as statements at the exit point, so
  their arguments evaluate at exit time in v1
  (documented). big32 and WASM reject defer
  programs in v1 with a named error. Full-suite
  regression check pending at that time (log
  forge_suite_defer.log). Counts after batch 16:
  HAVE 56, PARTIAL 61, GAP 383, to build 444. Next
  in priority: #22 allocator-as-value.
- Batch 17 (31 Oct 2026): #22 allocator-as-value
  v1 (stdlib/allocator.fg + examples/
  allocator_demo.fg + tests/test_allocator_v1.py,
  ALL PASS). Pure Jal Pari, no compiler change:
  one Allocator struct passed explicitly to
  functions, never a global, in three kinds
  (bump, freelist with slot reuse, arena with
  reset); out-of-memory returns -1 as a value.
  Full-suite regression check pending at that
  time (log forge_suite_allocator.log). Counts
  after batch 17: HAVE 57, PARTIAL 60, GAP 383,
  to build 443. Next in priority: #24 arena
  allocation.
- Batch 18 (31 Oct 2026): #24 arena allocation
  v1 (stdlib/arena.fg + examples/arena_demo.fg
  + tests/test_arena_v1.py, ALL PASS, plus a
  clean AddressSanitizer run). Pure Jal Pari: a
  growing region with mark/restore; alloc never
  fails; individual frees are no-ops. The batch
  also fixed two real compiler ownership bugs
  the arena exposed: push on a shared array now
  copies-on-write (it used to realloc the shared
  buffer, dangling other holders), and field
  assignment now mirrors plain assignment's
  ownership for array/struct fields. Full-suite
  regression check pending at that time (log
  forge_suite_arena.log). Counts after batch 18:
  HAVE 58, PARTIAL 59, GAP 383, to build 442.
  Next in priority: #25 reference counting.
- Batch 19 (1 Nov 2026): #25 reference
  counting v1 (a `refcount` builtin + stdlib/
  rc.fg + examples/rc_demo.fg + tests/
  test_rc_v1.py, ALL PASS). The builtin reads
  an array's live holder count without gaining
  a holder; Rc wraps shared ownership (clone
  gains one, drops lose one, last drop frees;
  mutation through any holder is visible to
  all). Counts verified by hand: 1 after
  rc_new, 2 after rc_clone. Native-only in v1;
  big32 and WASM reject refcount programs.
  Full-suite regression check pending at that
  time (log forge_suite_rc.log). Counts after
  batch 19: HAVE 59, PARTIAL 58, GAP 383, to
  build 441. Next in priority: #26 weak
  references.
- Batch 20 (1 Nov 2026): #26 weak references
  v1 (runtime weak table for [int] arrays in
  forge_lang/codegen.py + forge_lang/weaks.py
  + examples/weak_demo.fg + tests/
  test_weak_v1.py, ALL PASS, plus a clean
  AddressSanitizer run). weak_new registers
  without gaining a holder; weak_upgrade
  returns (alive, array) — the current buffer
  while any strong holder lives, (false, [])
  after the last strong holder's scope ends.
  Native-only in v1; big32 and WASM reject
  weak programs. Full-suite regression check
  pending at that time (log
  forge_suite_weak.log). Counts after batch
  20: HAVE 60, PARTIAL 58, GAP 382, to build
  440. Next in priority: #27 move semantics.
- Batch 21 (1 Nov 2026): #27 move semantics
  v1 (a move builtin + forge_lang/moves.py +
  examples/move_demo.fg + tests/
  test_move_v1.py, ALL PASS, plus a clean
  AddressSanitizer run). move(a) transfers
  the one hold instead of copying — the
  destination's refcount stays 1, the source
  is dead afterwards, and moves in branches
  or loops are rejected in v1 (the free
  tracking is compile-time). Native-only in
  v1; big32 and WASM reject move programs.
  Full-suite regression check pending at that
  time (log forge_suite_move.log). Counts
  after batch 21: HAVE 61, PARTIAL 58, GAP
  381, to build 439. Next in priority: #28
  copy-on-write arrays (batch 18's push CoW
  is a first piece — the batch must decide
  index-assignment CoW, currently specified
  as shared mutation).
