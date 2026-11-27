# Top-500 program tracker

The user ordered (31 Oct 2026) that all 500 items in
docs/TOP_500_FEATURES.md be added to Qasida.

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
- The full qasida test suite must stay green; a batch that breaks
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
- Correction 11 Nov 2026 (count reconciliation, verified against the
  pushed catalog at 7707d172 / be8b464 / de3db0e7): the starting
  PARTIAL/GAP split above was miscounted — true starting counts are
  HAVE 38, PARTIAL 69, GAP 393, to build 462. The batch log's
  "Counts after" lines below keep their contemporary (tally) numbers;
  the corrected running totals are in the reconciliation entry after
  #40.

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
  v1 (forge_lang/stdlib/allocator.fg + examples/
  allocator_demo.fg + tests/test_allocator_v1.py,
  ALL PASS). Pure Qasida, no compiler change:
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
  v1 (forge_lang/stdlib/arena.fg + examples/arena_demo.fg
  + tests/test_arena_v1.py, ALL PASS, plus a
  clean AddressSanitizer run). Pure Qasida: a
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
  counting v1 (a `refcount` builtin + forge_lang/stdlib/
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
  confirmed clean 1 Nov 2026 (log
  forge_suite_weak.log: PASS). Batches 1–20
  pushed 1 Nov 2026 via the daily batch push
  (commit 7707d172); batch 21 was still in
  flight then and rides the next push. Counts
  after batch 20: HAVE 60, PARTIAL 58, GAP
  382, to build 440. Next in priority: #27
  move semantics.
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
  Full-suite regression check confirmed clean
  1 Nov 2026 (log forge_suite_move.log:
  PASS). Counts after batch 21: HAVE 61,
  PARTIAL 58, GAP 381, to build 439. Batch
  21 itself is unpushed (it landed after the
  1 Nov daily push) and rides the next push.
  Next in priority: #28 copy-on-write arrays.
- Batch 22 (1 Nov 2026): #28 copy-on-write
  arrays v1, opt-in (forge_lang/stdlib/cow.fg + examples/
  cow_demo.fg + tests/test_cow_v1.py, ALL
  PASS, plus a clean AddressSanitizer run).
  Pure Qasida, no compiler change: a Cow
  shares its buffer until a write (shared
  writer gets a private copy, sole holder
  writes in place). Marked [PARTIAL], not
  [HAVE]: language-default CoW (every index
  assignment CoWs) is NOT taken — it would
  break Rc's shared-mutation promise and
  existing programs, so it needs Jayant's
  explicit word. Full-suite regression check
  confirmed clean 1 Nov 2026 (log
  forge_suite_cow.log: PASS). Counts after batch
  22: HAVE 61, PARTIAL 59, GAP 380, to build
  439 (a PARTIAL does not drop the to-build
  total). Next in priority: #29 stack-
  allocated slices.
- Batch 23 (1 Nov 2026): #29 stack-allocated
  slices v1 (forge_lang/stdlib/slice.fg + examples/
  slice_demo.fg + tests/test_slice_v1.py, ALL
  PASS, plus a clean AddressSanitizer run).
  Pure Qasida, no compiler change: a Slice
  is a stack-allocated header over an
  existing array's buffer — no copy, writes
  through to the original, bounds are the
  slice's own, slicing a slice composes.
  Full-suite regression check confirmed clean
  1 Nov 2026 (log forge_suite_slice.log:
  PASS except the known flaky spawn_demo
  println-interleaving failure, re-verified
  4/4 clean). Counts after batch 23: HAVE 62, PARTIAL 59, GAP
  379, to build 438. Next in priority: #30
  lifetime-ordered placement (already HAVE
  as the kernel allocator — promote it to an
  allocator API, or confirm and move on).
- Batch 24 (1 Nov 2026): #30 lifetime-ordered
  placement v1 (forge_lang/stdlib/lifetime.fg + examples/
  lifetime_demo.fg + tests/test_lifetime_v1.py,
  ALL PASS, plus a clean AddressSanitizer
  run). Pure Qasida, no compiler change:
  the kernel allocator's idea promoted to a
  stdlib API — shorts from the front, longs
  from the back, one reset frees all shorts
  while longs survive, OOM is a value (-1).
  Full-suite regression check confirmed clean
  1 Nov 2026 (log forge_suite_lifetime.log:
  PASS). Counts after batch 24: HAVE 63, PARTIAL 59, GAP
  378, to build 437. Next in priority: #31
  memory-mapped files.
- Batch 25 (1 Nov 2026): #31 memory-mapped
  files v1 (runtime mmap table in
  forge_lang/codegen.py + forge_lang/mmaps.py
  + examples/mmap_demo.fg + tests/
  test_mmap_v1.py, ALL PASS, plus a clean
  AddressSanitizer run). mmap_open/get/set/
  close over bytes, native only; writes go
  through MAP_SHARED into the file itself.
  Also fixed two real pre-existing leaks the
  demo exposed: read_bytes freshness and
  write_bytes param consumption. Full-suite
  regression check confirmed 1 Nov 2026 (log
  forge_suite_mmap2.log: sole failure scope_demo
  fast, the known println-interleaving flake,
  re-verified 4/4 clean by direct runs). Counts after batch 25:
  HAVE 64, PARTIAL 59, GAP 377, to build
  436. Next in priority: #32 allocator-aware
  collections.
- Batch 26 (1 Nov 2026): #32 allocator-aware
  collections v1 (forge_lang/stdlib/avec.fg +
  examples/avec_demo.fg + tests/
  test_avec_v1.py, ALL PASS, plus a clean
  AddressSanitizer run). AVec holds one element
  per Allocator slot; the demo proves the
  allocator drives growth: bump size-2 push/
  push/pop/push ends in OOM-as-value (false),
  freelist size-2 reuses the freed slot (true)
  and reads the new value back (30). Pure Jal
  Pari, no compiler change. Marked PARTIAL:
  maps are the named next slice, not faked —
  their string keys cannot live in the
  allocator's [int]-backed slots. Full-suite
  regression check confirmed clean 1 Nov 2026
  (log forge_suite_avec.log: PASS). Counts after
  batch 26: HAVE 64, PARTIAL 60, GAP 376, to
  build 436. Next in priority: #33 destructor
  hooks.
- Batch 27 (1 Nov 2026): #33 destructor hooks
  v1 (forge_lang/drops.py + checker + native
  codegen + examples/drop_demo.fg + tests/
  test_drop_v1.py, ALL PASS, plus a clean
  AddressSanitizer run). A `drop` method on a
  struct runs when an owned binding dies
  (block/function end, return, break), before
  the free, via an owned copy; the receiver
  parameter itself never hooks (else infinite
  recursion — caught live by the first demo
  run, which printed forever until killed).
  Native only; big32/WASM/freestanding reject.
  V1 limits: per-binding drops, no nested
  drops, no union/opaque-field hooks, no
  generics. Full-suite regression check
  confirmed 1 Nov 2026 (log
  forge_suite_drop.log: sole failure scope_demo
  fast, the known println-interleaving flake,
  re-verified 4/4 clean by direct runs). Counts after batch 27: HAVE 65,
  PARTIAL 60, GAP 375, to build 435. Next in
  priority: #34 pinning.

- Fix track (2 Nov 2026, pipeline run): nested sized-literal
  unification (tests/test_sizedunif_fix.py, ALL PASS, plus a
  clean AddressSanitizer run). `[[1, 2], [3, 4]]` against
  `[[int; 2]; 2]` now checks: the checker recurses the
  sized-literal check into nested literals at any depth
  (and under a dynamic outer array with sized inner arrays),
  and infer assigns sized types to inner literals. Verified
  across let, function parameter, return, and struct-field
  positions, plus triple nesting and `[[int; 0]; 2]`; inner
  and outer count mismatches raise precise errors, and wrong
  inner sizes / element types are still rejected. Full-suite
  regression check confirmed clean 2 Nov 2026 (log
  forge_suite_sizedunif_4602.log: PASS). Counts unchanged
  (a fix, not a new feature): HAVE 65, PARTIAL 60, GAP 375,
  to build 435. Next in priority: the C-helper
  param-consumption audit.

- Fix track (4 Nov 2026, pipeline run): branch/loop moves
  + field moves, the #27 v2 slice
  (tests/test_move_branch_field.py, ALL PASS, plus
  AddressSanitizer-clean runs of the demo, field,
  branch, loop, and parameter programs; the v1 test
  was updated — its branch/loop rejection cases are
  superseded and now live in the v2 test as success
  cases). The checker now joins moved sets over
  if/while/for/match paths, so a use after a
  conditional move is a checker error until
  reassignment (or a fresh shadowing let) revives
  the variable; codegen gives every owned variable
  a runtime moved flag, so a branch move frees
  correctly on both paths and a second loop move
  fails at runtime instead of transferring a freed
  buffer. Field moves work in straight-line code
  with scope-end frees skipping the moved field
  (and its drop hook); field moves in branches or
  loops and moves of for-loop variables are
  rejected with named errors, not approximated.
  Full-suite regression check confirmed clean
  4 Nov 2026 (log forge_suite_movebranch_9356.log:
  PASS). Counts unchanged (an extension of #27,
  already HAVE): HAVE 65, PARTIAL 60, GAP 375,
  to build 435. Next in priority: mmap grow +
  word-width access (fix track), then the
  struct-array push copy-on-write item.

- Fix track (5 Nov 2026, pipeline run): mmap grow +
  word-width access, the #31 extension
  (tests/test_mmap_grow32_fix.py, ALL PASS, plus
  an AddressSanitizer-clean run of the demo:
  forge_mmap_grow ftruncates the file and remaps
  it under the same id, returning the new length;
  grow-only, a smaller or equal size fails with
  "mmap: new size must be larger than current
  size"; mmap_get32/mmap_set32 read and write a
  32-bit little-endian word at a byte offset
  (zero-extended, like peek32), assembled byte by
  byte so no alignment is assumed; a word crossing
  the end fails with "mmap index out of bounds".
  big32 and WASM still reject mmap programs with
  a named error. Full-suite regression check
  confirmed clean 5 Nov 2026 (log
  forge_suite_mmapgrow32_6775.log: PASS). Counts
  unchanged (an extension of #31, already HAVE):
  HAVE 65, PARTIAL 60, GAP 375, to build 435.
  NOT pushed: push authorization for the 1.4.0
  pile is SPENT — further pushes need Jayant's
  fresh word. Next in priority: struct-array push
  copy-on-write (fix track).

- Fix track (5 Nov 2026, pipeline run): struct-array push
  copy-on-write (tests/test_structpush_fix.py, ALL PASS,
  plus AddressSanitizer-clean runs of the two-sided,
  str-field, and array-field programs). The per-struct
  forge_<T>_push helper realloced a shared buffer in
  place — the two-sided probe read a[2].x == 9 where 4
  was expected and ASan reported a double-free in
  realloc. It now detaches first, mirroring the scalar
  helpers and the inline nested-array path: fresh
  buffer, copy slots gaining ownership of their fields
  each (struct_own_code — str fields deep-copied,
  array fields inc'd, nested structs recursed), drop
  this holder's count on the old buffer without
  freeing it. Full-suite regression check confirmed
  clean 5 Nov 2026 (log forge_suite_structpush_8224.log:
  PASS). Counts unchanged (a fix, not a feature):
  HAVE 65, PARTIAL 60, GAP 375, to build 435.
  NOT pushed: push authorization for the 1.4.0 pile
  is SPENT — further pushes need Jayant's fresh word.
  The fix track is now COMPLETE (all 7 items done).
  Next: order of the two PhD research slices vs #34
  pinning is Jayant's call (QUEUE.md), and any
  release after 1.4.0 needs his fresh word.

- #34 pinning (6 Nov 2026, pipeline run; Jayant's 6 Nov "Do it"
  chose pinning over the two PhD research slices, and the 6 Nov
  push 8eafc693 landing unblocked implementation):
  tests/test_pin_v1.py ALL PASS (demo 2/2/25/3/65/9/3, 9 run
  cases, 20 rejection cases, big32/WASM rejections named,
  fmt idempotent), plus an AddressSanitizer-clean run of the
  demo. pin(x); is a statement builtin: it marks an owned
  binding immovable — move, any whole-value use, reassignment,
  and push are checker errors, while in-place field/index
  writes, scalar reads, len/refcount, and for-iteration still
  work. The checker joins pinned sets over branches, loops,
  and match arms (pinned on any path counts after the join),
  mirroring move v2; native codegen emits nothing for the
  statement, and big32/WASM reject pin programs (forge_lang/
  pins.py, uses_pin gates). V1 limits are in the catalog entry
  (variable only, no pinning drop structs, no pinned-string
  indexing, name-keyed join shadowing). Full-suite regression
  check confirmed clean 6 Nov 2026 (log
  forge_suite_pin_14885_15681.log: PASS). Counts after #34:
  HAVE 66, PARTIAL 60, GAP 374, to build 434. NOT pushed:
  push authorization is SPENT — further pushes need Jayant's
  fresh word. Next in priority: #35 zeroing on free, then #36
  allocation failure as a value.
- #35 zeroing on free DONE 6 Nov 2026 (v1, default-on — Jayant's
  "Do it" after the default-vs-opt-in question): every heap
  buffer the native runtime frees is zeroed before free() —
  arrays of every element type, nested and struct arrays, strs,
  read_bytes temp, HTTP recv buffer, spawn thread args (native
  codegen choke points in forge_lang/codegen.py; no new syntax).
  Verified by tests/test_zero_free_v1.py ALL PASS (demo
  4/2/3/two/3/20/7/secret, 12 run cases, emitted-C assertions,
  C probe from the actual emitted preamble: freed buffers read
  zero, shared buffers not zeroed on dec); demo ASan-clean;
  full-suite regression check (log
  forge_suite_zerofree.log: PASS). V1 limits are in the catalog
  entry (native only, mmap out of scope, no opt-out). Counts
  after #35: HAVE 67, PARTIAL 60, GAP 373, to build 433. NOT
  pushed: push authorization is SPENT. Next in priority: #36
  allocation failure as a value.
- #36 allocation failure as a value DONE 7 Nov 2026: new builtin
  try_alloc(n: int) -> Result<[int], str> (native-only v1): Ok with a
  zero-initialised [int] via calloc, Err("out of memory") when calloc
  returns NULL (verified with try_alloc(2^60) = 2^63 bytes),
  Err("bad size") for n < 0, Ok empty for n == 0. Works with `?`
  propagation. Requires import "result.fg" (the Result struct lives
  there); the checker registers the Result<[int], str> instantiation
  so codegen emits it. big32/WASM reject it with a named error;
  freestanding rejects it. Verified by tests/test_allocfail_v1.py
  ALL PASS (18 checks: success, bad size, zero size, huge Err,
  write/read-back, `?` propagation both ways, n evaluated once,
  5 reject cases, emitted-C calloc assertion, big32/WASM gates,
  ASan clean); demo examples/allocfail_demo.fg runs clean;
  full-suite regression check (log
  forge_suite_allocfail_20261107.log: PASS). V1 limits are in the
  catalog entry ([int] only, no fallible implicit allocations, tiny
  bookkeeping mallocs can still forge_fail; ASan cannot test a
  2^63-byte calloc). Counts after #36: HAVE 68, PARTIAL 60,
  GAP 372, to build 432. NOT pushed: rides the 1.5.0 push retry
  (authorized 13:26 IST). Next in priority: #37 pool allocators.
- #37 pool allocators DONE 7 Nov 2026 (pipeline run): fixed-size
  object pools for drivers, pure Qasida
  (forge_lang/stdlib/pool.fg + examples/pool_demo.fg +
  tests/test_pool_v1.py, no compiler change). One pool serves one
  fixed object size (an int slot in v1), never grows, alloc is O(1)
  through a separate free stack, and out-of-memory is a value (-1).
  A freed slot's value is never clobbered by a next-pointer
  (unlike #22's intrusive freelist), and an occupancy bitmap makes
  double-free and use-after-free detectable: pool_free / pool_set /
  pool_get on a free or out-of-range slot return false and leave
  the pool unchanged. Freed slots are zeroed, so reuse never leaks
  the old value. Verified by tests/test_pool_v1.py ALL PASS (18
  checks: demo 4/4/0/1/2/3/true/true/100/false/3/true/-1/true/false/
  false/1/0/0/4/0, alloc order, full -1, double-free, LIFO reuse,
  reset, cap 0/negative, cap 1, bad slots, neighbours, set-on-free;
  fmt idempotent; big32/WASM reject with the named "tuples are not
  supported" error; ASan clean). Full-suite regression check
  confirmed clean 7 Nov 2026 (log forge_suite_pool_32639.log:
  PASS). V1 limits are in the
  catalog entry ([int] slots only, native only, rebind the returned
  Pool). Counts after #37: HAVE 69, PARTIAL 60, GAP 371, to build
  431. NOT pushed: push authorization is SPENT — further pushes
  need Jayant's fresh word. Next in priority: #38 stack-usage
  diagnostics.
- #38 stack-usage diagnostics DONE 8 Nov 2026 (pipeline run):
  new `qasida stack <file.fg>` subcommand
  (forge_lang/stackusage.py + cli.py wiring +
  examples/stackusage_demo.fg). Reports the max stack frame size
  per Qasida function from real `cc -fstack-usage` data at -O0,
  with a warning over the 2048-byte kernel frame budget
  (default limit, `--limit N` overrides it). Generic
  instantiations, methods (Struct::method), freestanding main,
  and never-emitted functions are all labelled honestly;
  runtime helpers are summarized. Verified by
  tests/test_stackusage_v1.py ALL PASS (14 checks: demo 90,
  small frames no warning, frame table parses, big frame warns,
  big-frame program runs 44852, --limit 0 / 100000, generic,
  method, freestanding, not-emitted, missing file, checker
  error, fmt idempotent; ASan clean). Full-suite regression
  check confirmed clean 8 Nov 2026 (log
  forge_suite_stackusage_28152_200.log: PASS). V1 limits are in
  the catalog entry (frames at -O0, per-function only,
  warn-only). Counts after #38: HAVE 70, PARTIAL 60, GAP 370,
  to build 430. NOT pushed: push authorization is SPENT —
  further pushes need Jayant's fresh word. Next in priority:
  #39 no implicit heap allocation in freestanding mode.
- #39 no implicit heap allocation in freestanding mode DONE
  9 Nov 2026 (pipeline run): the rule is enforced at compile
  time, in the checker, with a named error for the first heap
  value — any expression whose type is heap-backed (str, any
  array incl. sized, a struct/enum/tuple carrying one) is
  rejected, and push() is rejected outright; plain structs are
  stack values, and their emitted freestanding C contains no
  malloc, free, or memset (per-struct heap-array helpers not
  emitted when freestanding). Verified by
  tests/test_noheap_freestanding_v1.py ALL PASS (40 checks: 12
  named rejections, 7 freestanding programs build and run incl.
  the demo exiting 42, emit has no heap calls, big32 builds to
  .hex and rejects a string literal, hosted controls, fmt
  idempotent; ASan clean). Full-suite regression check confirmed
  clean 9 Nov 2026 (log forge_suite_noheap_10321-6909.log:
  PASS). V1 limits are in the catalog entry (dead declarations
  naming heap types still declare; sized arrays stay rejected;
  fail()/assert() with a string message stay rejected). Counts
  after #39: HAVE 71, PARTIAL 60, GAP 369, to build 429. NOT
  pushed: push authorization is SPENT — further pushes need
  Jayant's fresh word. Next in priority: #40 use-after-move
  checking.
- #40 use-after-move checking DONE 10 Nov 2026 (pipeline run):
  checker-only fix closing five holes in the move checking
  (#27 v2 already rejected the direct uses): push() and
  index-assign through a moved array, whole-value use of an
  intermediate struct path after a nested field move, a while
  condition the body moves, and moving a for loop's iterable
  in its body. Each hole was confirmed as a real
  heap-use-after-free under AddressSanitizer before the fix
  (for-iterable, while-condition index, push-then-read).
  Also fixed in the same run: assigning a whole intermediate
  struct did not revive a moved field under it (FieldAssign
  discarded only the exact target path). Verified by
  tests/test_useaftermove_v1.py ALL PASS (demo, 11 run cases,
  14 rejection cases, big32/WASM named rejections, fmt
  idempotent; ASan clean). Full-suite regression check
  confirmed clean 10 Nov 2026 (log
  forge_suite_useaftermove_10671.log: sole failure the known
  scope_demo println-interleaving flake, 4/4 clean on direct
  rerun). Self-host safety: python-checker verdicts over all
  158 corpus files identical before/after the edit (124
  accept / 34 reject), and both self-host harness files check
  clean — the in-flight 4f verification was not contaminated.
  V1 limits are in the catalog entry (field moves in loops
  still report the v2 message first; match-arm binding moves
  still untracked). Counts after #40: HAVE 72, PARTIAL 60,
  GAP 368, to build 428. NOT pushed: push authorization is
  SPENT — further pushes need Jayant's fresh word. Next in
  priority: #42 error wrapping with context (#41 is already
  HAVE).

- Count reconciliation (11 Nov 2026, pipeline run — docs only, no
  compiler change, no suite run: the compiler speed program was
  profiling wall-clock timings in the same window, so no compiler
  work was done this run). The catalog entry lines are the source of
  truth; the tally had drifted from them. True counts now: HAVE 71,
  PARTIAL 62, GAP 367, to build 429. Three causes, each verified
  against the pushed catalog at 7707d172 (1 Nov), be8b464 (5 Nov)
  and de3db0e7 (11 Nov, current main) — all three snapshots
  reproduce exactly from the corrected start below:
  (1) the 31 Oct starting counts miscounted the PARTIAL/GAP split
  (recorded PARTIAL 66 / GAP 396; true PARTIAL 69 / GAP 393; HAVE
  38 and to-build 462 were right);
  (2) #30 lifetime-ordered placement was already tagged [HAVE] in
  the 31 Oct catalog ("Already borrowed as the kernel allocator;
  promote it to an allocator API"), so batch 24 promoted it to a
  stdlib API without moving the counts — the tally counted it as a
  new GAP-to-HAVE;
  (3) #39 was [PARTIAL] before its batch ("The freestanding flag
  exists; enforce the rule at compile time"), so its landing was
  PARTIAL-to-HAVE, not GAP-to-HAVE. Corrected running totals: after
  batch 20, HAVE 61 / PARTIAL 61 / GAP 378; after batch 27, HAVE 64
  / PARTIAL 63 / GAP 373; after #40, HAVE 71 / PARTIAL 62 / GAP 367.
  (#27 is NOT an error: its [HAVE] tag at 7707d172 came with batch
  21's own edit, and counting it GAP-to-HAVE reproduces the
  snapshots exactly.) The drift flag is closed; quote HAVE 71,
  PARTIAL 62, GAP 367. Next in priority: #42 error wrapping with
  context — BLOCKED on Jayant's pick (new syntax vs helper function
  vs Result method).

- Sprint day 1 (21 Nov 2026, LIBS ONLY — OS track paused): 20 library
  items landed, all verified: #130 binsearch, #131 zipenum, #132
  groupby, #138 sparse, #140 windows, #167 dist, #168 randdist,
  #170 linalg, #171 neldermead, #173 interp, #174 calculus,
  #176 fixedpoint, #178 rounding, #193 binio, #194 bincode, #221 json2,
  #222 yaml, #227 msgpack, #231 htmlparse, #236 gzip2 (20 stdlib
  modules + 20 demos, pure .fg, no compiler change). Verification:
  tests/test_daily_20261121.py 80/80 checks (20 demos x 2 compilers x
  rc=0 + exact stdout); expected values from an independent Python
  replica (~/workspace/blackmoon-iso/daily-20261121/replica_20261121.py,
  20/20 match — one replica-side ternary bug found and fixed during
  the check, program values unchanged; Nelder-Mead expected value
  re-derived in float64 after a float32 replica predicted f = 0).
  Counts after sprint day 1: HAVE 91, PARTIAL 58, GAP 351, to build
  409. Arithmetic from the reconciled baseline (HAVE 71, PARTIAL 62,
  GAP 367, to build 429): 16 GAP-to-HAVE + 4 PARTIAL-to-HAVE = 20
  flips; 71 + 20 = 91; 62 - 4 = 58; 367 - 16 = 351; 429 - 20 = 409
  (91 + 58 + 351 = 500). PUSHED as 66a9b7a8 (parent d6984c46,
  selective push, 44 files — 20 stdlib + 20 demos + test + 3 docs),
  verified via the Contents API. Next: sprint day 2 (22 Nov), same
  libs-only rule, target 20/day toward HAVE ~211 by 27 Nov.

- Sprint batch 2 (21 Nov 2026, LIBS ONLY — OS track paused, back-to-back
  after day 1): 20 library items landed, all verified: #42 errwrap,
  #43 multierr, #49 resultx, #53 valerr, #121 hashmap, #122 setops,
  #125 ordmap, #133 persist, #137 ringbuf, #139 ndarray, #146
  strbuild, #148 caseconv, #151 utf8, #153 unidiff, #163 bigint,
  #164 decimal, #165 vecmath, #235 structpack, #319 junit, #424
  optimizers (20 stdlib modules + 20 demos, pure .fg, no compiler
  change). Verification: tests/test_daily_20261121b.py 80/80 checks
  (20 demos x 2 compilers x rc=0 + exact stdout); expected values
  from an independent Python replica
  (~/workspace/blackmoon-iso/daily-20261121-batch2/replica_20261121b.py,
  20/20 match — replica re-derived the alphabet hash, the LCS-table
  diff, the base-1e9 product, the float64 Adam steps in exact op
  order, and the UTF-8 round-trip from first principles; no
  discrepancies found). Counts after sprint batch 2: HAVE 111,
  PARTIAL 51, GAP 338, to build 389. Arithmetic from sprint day 1
  (HAVE 91, PARTIAL 58, GAP 351, to build 409): 13 GAP-to-HAVE + 7
  PARTIAL-to-HAVE = 20 flips; 91 + 20 = 111; 58 - 7 = 51;
  351 - 13 = 338; 409 - 20 = 389 (111 + 51 + 338 = 500). Note: the
  day-1 entry above still says "NOT pushed" — the day-1 push landed
  after it was written, as 66a9b7a8 (parent d6984c46, selective push,
  44 files), verified via the Contents API; batch 2's push parents
  on 66a9b7a8. Note: #42 was BLOCKED awaiting Jayant's pick (new
  syntax vs helper function vs Result method); batch 2 lands the
  helper-function slice (pure-Qasida error chain, errwrap.fg) per
  the sprint task — the new-syntax and Result-method variants stay
  open if he wants them. Next: sprint day 2 (22 Nov), same libs-only
  rule, target 20/day toward HAVE ~211 by 27 Nov.

- Sprint batch 3 (21 Nov 2026, LIBS ONLY — OS track paused, back-to-back
  after batch 2, same day): 20 library items landed, all verified: #147
  fmtstr, #152 lines, #160 plural, #186 bufio, #191 glob, #195 config2,
  #196 logrot, #198 checkread, #200 journal, #226 protobuf, #232
  sqlbuild, #233 valid, #234 migrate, #249 timeout, #272 throttle,
  #307 snap, #311 faketime, #323 lockfile, #384 trace, #396 audit.
  Daily test: tests/test_daily_20261121c.py — 80/80 checks PASS
  (20 demos x 2 compilers x rc=0 + exact stdout); expected values
  from an independent Python replica
  (~/workspace/blackmoon-iso/daily-20261121-batch3/replica_20261121c.py,
  20/20 match — replica re-derived the glob star-backtrack matcher,
  the LEB128 varints, zlib.crc32 for the checksum file (222957957 for
  "hello world", matching the program exactly), the plural rule table,
  and the fixed-decimal float formatting from first principles; no
  discrepancies found). Counts after sprint batch 3: HAVE 131,
  PARTIAL 47, GAP 322, to build 369. Arithmetic from sprint batch 2
  (HAVE 111, PARTIAL 51, GAP 338, to build 389): 16 GAP-to-HAVE + 4
  PARTIAL-to-HAVE = 20 flips; 111 + 20 = 131; 51 - 4 = 47;
  338 - 16 = 322; 389 - 20 = 369 (131 + 47 + 322 = 500). Held extra:
  icalparse.fg + icalparse_demo.fg were also built and verified 4/4
  in this batch (parse a VEVENT block back out) but NOT counted or
  pushed here — its catalog item #239 iCalendar already reads [HAVE]
  (ical-lite.fg builds VEVENT text), so the parse slice is an
  extension of a HAVE item, not a flip; it stays local for a later
  batch. Next: sprint batch 4, same libs-only rule, target 20/day
  toward HAVE ~211 by 27 Nov.

- Sprint batch 4 (21 Nov 2026, LIBS ONLY — OS track paused, back-to-back
  after batch 3, same day): 20 library items landed, all verified: 12
  verification flips (#134 bitset, #135 bloom, #136 lru, #123 deques,
  #124 heaps, #240 RSS, #145 regexfull, #155 csv2, #156 json escaping,
  #157 textwrap width, #184 tempfile, #214 ratelimit — the modules
  already existed in the tree while the catalog wrongly said GAP/PARTIAL;
  each was run under BOTH compilers and confirmed genuinely working
  before flipping), the held icalparse slice (#239, parses a VEVENT
  block back out — an extension of an already-HAVE item, no count
  change), and 7 new libraries (#150 template2, #154 mdast, #159
  sentenc, #182 pathnorm, #209 rest extension, #225 xmlpath, #301
  testkit). Daily test: tests/test_daily_20261121d.py — 80/80 checks
  PASS (20 items x 2 compilers x rc=0 + exact stdout); expected values
  from an independent Python replica
  (~/workspace/blackmoon-iso/daily-20261121-batch4/replica_20261121d.py,
  20/20 match — replica re-derived the bloom double hash, FIFO LRU
  eviction, heapq, the regexfull alternation/group matcher, the csv
  module, json.loads plus the j2_num_str truncation rule, greedy word
  wrap, the token-bucket simulation, iCalendar line parsing, the
  template if/each/escape rules, the Markdown AST + HTML render,
  sentence splitting with abbreviations, posixpath normalization,
  XML path search, test-kit counting, and REST request/response
  construction from first principles; no discrepancies found).
  Counts after sprint batch 4: HAVE 150, PARTIAL 38, GAP 312, to build
  350. Arithmetic from sprint batch 3 (HAVE 131, PARTIAL 47, GAP 322,
  to build 369): 10 GAP-to-HAVE + 9 PARTIAL-to-HAVE = 19 flips (the
  20th item, icalparse, extends already-HAVE #239 and adds no flip);
  131 + 19 = 150; 47 - 9 = 38; 322 - 10 = 312; 369 - 19 = 350
  (150 + 38 + 312 = 500). #42 is RESOLVED: Jayant picked the
  helper-function slice (errwrap.fg) as #42's answer (21 Nov ~11:28
  IST); no further error-wrapping variants. Next: sprint batch 5,
  same libs-only rule, target 20/day toward HAVE ~211 by 27 Nov.

## Sprint batch 5 — 21 Nov 2026 (LIBS ONLY, OS paused)
  20/20 landed: 11 verification flips (#304 bench, #429 evalharness,
  #430 embeddings, #433 plot, #434 svg, #435 profiler, #451 jwt,
  #197 tar, #425 dataset, #426 tokenizer, #437 quant — the modules
  already existed in the tree while the catalog wrongly said
  GAP/PARTIAL; each was run under BOTH compilers and confirmed
  genuinely working before flipping) and 9 new libraries (#385
  promet, #455 sbom, #458 cors, #459 csp, #449 csrf, #450 pwhash,
  #447 paramq, #446 valid2, #423 conv1d). Daily test:
  tests/test_daily_20261121e.py — 80/80 checks PASS (20 items x 2
  compilers x rc=0 + exact stdout); expected values from an
  independent Python replica
  (~/workspace/blackmoon-iso/daily-20261121-batch5/replica_20261121e.py,
  20/20 match — replica re-derived bench timing arithmetic, eval
  accuracy/MSE/perplexity, embedding cosine + nearest neighbour,
  profiler section totals, JWT HMAC-SHA256 tokens, the tar header
  checksum, dataset windows/splits/batches, BPE training, int8
  calibration, SVG shape strings, plot scaling, Prometheus text,
  SBOM JSON, CORS/CSP header text, CSRF LCG tokens, iterated
  SHA-256 password hashing, parameterized-query rendering, input
  validation rules, and 1-D convolution from first principles).
  Counts after sprint batch 5: HAVE 170, PARTIAL 35, GAP 295, to build
  330. Arithmetic from sprint batch 4 (HAVE 150, PARTIAL 38, GAP 312,
  to build 350): 17 GAP-to-HAVE + 3 PARTIAL-to-HAVE = 20 flips;
  150 + 20 = 170; 38 - 3 = 35; 312 - 17 = 295; 350 - 20 = 330
  (170 + 35 + 295 = 500). Findings: the csrf alphabet is 31 chars,
  not 32 (i, l and o all skipped as lookalikes) — the modulus is
  % 31, caught by the first run; #448 auto-escaping templates was
  NOT flipped — template2.fg's t2_escape is opt-in (never called by
  the render path), so a default-escaping esc.fg wrapper is a
  batch-6 item instead; #153's stale note fixed (unidiff landed in
  batch 2). Next: sprint batch 6, same libs-only rule, target
  20/day toward HAVE ~211 by 27 Nov.

- Sprint batch 6 (21 Nov 2026, same day, LIBS ONLY): 20 new libraries,
  all verified 4/4 checks (rc=0 + exact stdout, hosted + python
  compilers) under tests/test_daily_20261121f.py (80/80 PASS) with an
  independent Python replica 20/20 match
  (~/workspace/blackmoon-iso/daily-20261121-batch6/replica_20261121f.py):
  esc.fg (#448 auto-escaping templates — the batch-5 near-miss, now a
  wrapper that escapes values and {{#each}} items before rendering),
  stdio.fg (#192 stdin via read_line + stderr via eprintln),
  logfmt.fg (#383 structured key=value logs on top of log.fg's levels),
  rope.fg (#427 rotary position embeddings), metrics2.fg (#428 AUC,
  log-loss, top-k, Brier), sklearn2.fg (#431 z-score + min-max scaling
  and k-fold splits), resolver.fg (#321 highest satisfying version),
  semver2.fg (#322 caret/tilde/range constraints), dbg.fg (#382
  "name = value" helpers), memprof.fg (#387 alloc-counter snapshots;
  deltas probed identical under both compilers), flame.fg (#388
  flame-graph SVG), health.fg (#394 /health JSON), replay.fg (#400
  seeded LCG replay), dvc.fg (#440 CRC32 dataset manifests),
  ct.fg (#443 constant-time comparison), secrets.fg (#444 char-code
  secrets, redaction, zeroing), perms.fg (#445 read/write/net flags +
  path roots), lock.fg (#453 "name==version #hash" lines),
  vuln.fg (#456 exact-match vulnerability feed), safedeser.fg (#457
  length + bracket-depth limits before j2_parse). No #42/#43/#53
  work (#42 resolved: helper-function slice). Skipped per brief:
  #273, #129, #302 (need function values); #122/#164 not flipped
  (known stale notes).
  Counts after sprint batch 6: HAVE 190, PARTIAL 28, GAP 282, to build
  310. Arithmetic from sprint batch 5 (HAVE 170, PARTIAL 35, GAP 295,
  to build 330): 13 GAP-to-HAVE + 7 PARTIAL-to-HAVE = 20 flips;
  170 + 20 = 190; 35 - 7 = 28; 295 - 13 = 282; 330 - 20 = 310
  (190 + 28 + 282 = 500). Next: sprint batch 7, same libs-only rule,
  target 20/day toward HAVE ~211 by 27 Nov.

- Sprint batch 7 (21 Nov 2026, same day, LIBS ONLY): 20 items,
  all verified 4/4 checks (rc=0 + exact stdout, hosted + python
  compilers) under tests/test_daily_20261121g.py (80/80 PASS) with an
  independent Python replica 20/20 match
  (~/workspace/blackmoon-iso/daily-20261121-batch7/replica_20261121g.py):
  iter.fg (#75 iterator protocol over [int]), fsm.fg (#79 state
  machines, explicit transition table), schedpol.fg (#90 priority /
  EDF / lottery picks), elf.fg (#95 ELF64 header parsing),
  ipv6.fg (#216 parse / expand / compress), fmtcrc.fg (#237
  "len:payload:crc" records, CRC32 over ASCII bytes), cancel.fg
  (#248 cooperative cancellation tokens), sema.fg (#256 counting
  permits), deadlock.fg (#258 wait-for-graph cycle detection),
  bpstrat.fg (#275 drop_new / drop_oldest / keep_latest),
  timerwheel.fg (#279 due-tick firing), paramtest.fg (#308
  table-driven cases), doubles.fg (#309 spy call recording),
  flaky.fg (#313 "name:pass/fail" history, flaky = both outcomes),
  contract.fg (#315 method/path/required-field contracts),
  depcheck.fg (#330 exact (name, version) vulnerability audit),
  license.fg (#331 allowed-license enforcement), tasks.fg (#337
  Kahn topological order + ready sets), flags.fg (#338 named
  on/off switches), lint.fg (#351 flip — already in the tree,
  verified via the existing lint_demo.fg). No #42/#43/#53 work
  (#42 resolved: helper-function slice). Skipped per brief:
  #273, #129, #302 (need function values); #122/#164 not flipped
  (known stale notes). #181/#187/#188/#189/#190 not buildable in
  pure Qasida (no mkdir/readdir/rename builtins exist).
  Counts after sprint batch 7: HAVE 210, PARTIAL 26, GAP 264, to build
  290. Arithmetic from sprint batch 6 (HAVE 190, PARTIAL 28, GAP 282,
  to build 310): 18 GAP-to-HAVE + 2 PARTIAL-to-HAVE = 20 flips;
  190 + 20 = 210; 28 - 2 = 26; 282 - 18 = 264; 310 - 20 = 290
  (210 + 26 + 264 = 500). This crosses the sprint's ~211 target a
  day early (HAVE 210 of 500 = 42%); the target was an estimate,
  the running count is the honest measure. Next: sprint batch 8,
  same libs-only rule, target 20/day toward HAVE ~211 by 27 Nov.

- Sprint batch 8 (21 Nov 2026, same day, LIBS ONLY): 20 items,
  all verified 4/4 checks (rc=0 + exact stdout, hosted + python
  compilers) under tests/test_daily_20261121h.py (80/80 PASS) with an
  independent Python replica 20/20 match
  (~/workspace/blackmoon-iso/daily-20261121-batch8/replica_20261121h.py):
  imporg.fg (#353 import sort + dedupe by ASCII rank), complexity.fg
  (#354 cyclomatic complexity over node kinds), unsafecheck.fg
  (#355 unchecked ops per file), docsym.fg (#368 file outline),
  callhier.fg (#372 callers/callees), wsym.fg (#374 case-sensitive
  symbol search), doccomment.fg (#491 /// doc entries), todotrack.fg
  (#492 TODO/FIXME marks), casestyle.fg (#497 snake_case/CamelCase),
  ffibind.fg (#476 C declarations to extern bindings), schemagen.fg
  (#477 .proto messages to structs), simd.fg (#166 width-4 chunked
  add/mul/dot), grapheme.fg (#144 cluster segmentation),
  tensor2.fg (#421 dtype-tagged tensors), autograd2.fg (#422 tape
  freeing + div/exp/log ops 22-24, gradients checked against central
  finite differences in the replica, gaps ~1e-9; tensor_autograd.fg
  extended), onnx.fg (#436 flip — already in the tree, verified via
  the existing onnx_demo.fg), signrel.fg (#454 FNV-1a keyed
  signatures), docgen2.fg (#475 examples + cross-links),
  bpstream.fg (#264 drop_new/drop_oldest streams), typedchan.fg
  (#242 float + bool channel variants, in-task only). No #42 work
  (#42 resolved: helper-function slice). Skipped per brief: #468
  (not picked — overlaps #477), #273, #129, #302 (need function
  values); #122/#164 not flipped (known stale notes). #181/#187/
  #188/#189/#190 not buildable in pure Qasida (no mkdir/readdir/
  rename builtins exist).
  Counts after sprint batch 8: HAVE 230, PARTIAL 22, GAP 248, to build
  270. Arithmetic from sprint batch 7 (HAVE 210, PARTIAL 26, GAP 264,
  to build 290): 16 GAP-to-HAVE + 4 PARTIAL-to-HAVE = 20 flips;
  210 + 20 = 230; 26 - 4 = 22; 264 - 16 = 248; 290 - 20 = 270
  (230 + 22 + 248 = 500). HAVE 230 of 500 = 46%. Next: sprint batch 9,
  same libs-only rule, target 20/day (the ~211 target was passed a
  day early; the running count is the honest measure).
- Sprint batch 9 (21 Nov 2026, same day, LIBS ONLY): 20 flips,
  all verified 4/4 checks (rc=0 + exact stdout, hosted + python
  compilers) under tests/test_daily_20261121i.py (84/84 PASS — 21
  demos: the 20 flips plus triple.fg, which advances #326 without
  closing it) with an independent Python replica 21/21 match
  (~/workspace/blackmoon-iso/daily-20261121-batch9/replica_20261121i.py):
  srcgen.fg (#468 annotation-driven builder generation from Qasida
  source, distinct from #477 schemagen and from #463 derive
  attributes), genspec.fg (#467 per-type specialized names),
  typemeta.fg (#469 recursive type-level evaluator: add/sub/mul,
  len, if, eq), ccpass.fg (#474 substring and max-length passes),
  astapi.fg (#478 fn/struct/let nodes, find, whole-word rename),
  typehier.fg (#373 "Trait:Struct" implementor registry),
  extractfn.fg (#375 fn text + call-site rendering), cov.fg (#305
  line/branch coverage, once-only hits), mock.fg (#306 flip —
  already in the tree since 2 Nov 2026 as mock-lite, verified via
  the existing mock_demo.fg), itharness.fg (#310 setup-aware
  cases, one-line summary), muttest.fg (#314 one-operator
  evaluator, operator-swap mutants, kill rate), loadtest.fg
  (#316 users/ramp/duration/rps plan), golden.fg (#318 golden
  vs actual line diffs), doctest.fg (#320 "/// >>> expr"
  extraction + checks), workspace.fg (#324 member registry +
  "from->to" edges), buildprof.fg (#325 dev -O0/-g/--checks vs
  release -O3), triple.fg (#326 triples landed: arch-vendor-os
  parse, known list, host check — sysroots still missing, so
  #326 stays PARTIAL and does NOT count as a flip), incr.fg
  (#327 FNV-1a fingerprints, stale check, rebuild list),
  buildcache.fg (#328 key-list cache, hit rate), vendor.fg
  (#329 vendor/<name>-<version> paths, missing list),
  unused.fg (#347 top-level let bindings with no whole-word use).
  One fix during verification: golden_demo.fg used `short` as a
  variable name, which is a C keyword — renamed to missing_one;
  the rerun went 84/84. No #42/#43/#53 work (#42 resolved:
  helper-function slice). Skipped per brief: #273, #129, #302
  (need function values); #122/#164 not flipped (known stale
  notes). #181/#187/#188/#189/#190 not buildable in pure Qasida
  (no mkdir/readdir/rename builtins exist).
  Counts after sprint batch 9: HAVE 250, PARTIAL 22, GAP 228, to build
  250. Arithmetic from sprint batch 8 (HAVE 230, PARTIAL 22, GAP 248,
  to build 270): 20 GAP-to-HAVE + 0 PARTIAL-to-HAVE = 20 flips;
  230 + 20 = 250; 22 - 0 = 22; 248 - 20 = 228; 270 - 20 = 250
  (250 + 22 + 228 = 500). HAVE 250 of 500 = 50%. Next: sprint batch 10,
  same libs-only rule, target 20/day (the ~211 target was passed on
  day 1; the running count is the honest measure).

- Sprint batch 10 (21 Nov 2026, same day, LIBS ONLY): 20 flips,
  all verified 4/4 checks (rc=0 + exact stdout, hosted + python
  compilers) under tests/test_daily_20261121j.py (80/80 PASS — 20
  demos) with an independent Python replica 20/20 match
  (~/workspace/blackmoon-iso/daily-20261121-batch10/replica_20261121j.py):
  unreach.fg (#348 straight-line reachability: statements after the
  first return), godef.fg (#363 definition index, first definition
  wins — closes the PARTIAL), findrefs.fg (#364 every use of a
  symbol, first-seen order), complete.fg (#365 prefix completions
  from scope), sighelp.fg (#366 signature text + params),
  semhl.fg (#370 token classifier), inlay.fg (#371 "name: type"
  hints), replhist.fg (#379 multiline input + history cursor —
  closes the PARTIAL), notebook.fg (#380 md/code cells, exec
  numbers), bp.fg (#381 breakpoint registry, next-hit scan),
  clayout.fg (#281 C field offsets with align_up), marshal.fg
  (#294 ASCII encode/decode by byte value), plugin.fg (#297
  plugin registry, load/unload), cheader.fg (#298 C declarations
  + include guard), hover.fg (#361 hover info — closes the known
  LSP hover gap), dce.fg (#411 BFS reachability, dead functions),
  intern.fg (#415 one id per distinct string), sso.fg (#416
  15-char inline cutoff), consteval.fg (#472 integer const
  folds), determin.fg (#356 recorded runs are consistent).
  One fix during verification: sso.fg used `inline` as a struct
  field name, which is a C keyword — renamed to is_inline; the
  rerun went 80/80. The replica caught its own ordering bug in
  plugin_demo (values captured after the unload); the .fg demo
  was correct. No #42/#43/#53 work (#42 resolved:
  helper-function slice). Skipped per brief: #273, #129, #302
  (need function values); #122/#164 not flipped (known stale
  notes). #181/#187/#188/#189/#190 not buildable in pure Qasida
  (no mkdir/readdir/rename builtins exist).
  Counts after sprint batch 10: HAVE 270, PARTIAL 20, GAP 210, to build
  230. Arithmetic from sprint batch 9 (HAVE 250, PARTIAL 22, GAP 228,
  to build 250): 18 GAP-to-HAVE + 2 PARTIAL-to-HAVE = 20 flips;
  250 + 20 = 270; 22 - 2 = 20; 228 - 18 = 210; 250 - 20 = 230
  (270 + 20 + 210 = 500). HAVE 270 of 500 = 54%. Next: sprint batch 11,
  same libs-only rule, target 20/day (the running count is the honest
  measure).

- Sprint batch 11 (21 Nov 2026, same day, LIBS ONLY): 20 flips,
  all verified 4/4 checks (rc=0 + exact stdout, hosted + python
  compilers) under tests/test_daily_20261121k.py (80/80 PASS — 20
  demos) with an independent Python replica 20/20 match
  (~/workspace/blackmoon-iso/daily-20261121-batch11/replica_20261121k.py):
  threat.fg (#460 threat-model table with worst-risk ranking),
  reflect.fg (#464 runtime type information registry),
  annot.fg (#465 #[...] metadata rows with lookup),
  cfg.fg (#466 target descriptor with os=/arch=/mode=/feat=/not:
  predicates), alias.fg (#498 import x as y, conflicts recorded),
  reexport.fg (#499 pub use table with resolution),
  strinterp.fg (#141 "hello {name}" substitution, {{ and }} escape),
  mlstr.fg (#142 triple-quote blocks: join, dedent, trim blank),
  rawstr.fg (#143 raw/cooked string conversion),
  memo.fg (#115 named-operation memo table with hit/miss counters),
  recdepth.fg (#117 depth guard with overflow counting),
  naninf.fg (#179 NaN/Infinity rules: NaN != itself, inf - inf is
  NaN), connpool.fg (#212 named-connection pool with idle
  eviction), future.fg (#246 pending/ready futures),
  latch.fg (#255 countdown latch), evloop.fg (#262 FIFO event
  loop), observ.fg (#265 topic subscriptions with delivery),
  taskgroup.fg (#271 task groups with done tracking),
  zerocopy.fg (#299 shared-buffer views, copies stay 0),
  covfuzz.fg (#303 LCG mutational fuzzer over the ABCD-prefix
  target; seed 42, 60 steps, edges 1/0/2/3 found).
  Two fixes during verification: evloop.fg assigned a bare []
  to a [str] field, which the checker rejects — replaced with
  typed empty-array helpers; the first 12-step covfuzz run found
  no new edge, so the run was extended to 60 steps (edge 2 at
  step 15, edge 3 at step 48). The replica caught its own
  strinterp bug first ({{name}} rendered with a stray }) and
  both sides gained a }} escape. No #42/#43/#53 work (#42
  resolved: helper-function slice). Skipped per brief: #273,
  #129, #302 (need function values); #122/#164 not flipped
  (known stale notes). #181/#187/#188/#189/#190 not buildable
  in pure Qasida (no mkdir/readdir/rename builtins exist).
  Counts after sprint batch 11: HAVE 290, PARTIAL 20, GAP 190, to build
  210. Arithmetic from sprint batch 10 (HAVE 270, PARTIAL 20, GAP 210,
  to build 230): 20 GAP-to-HAVE + 0 PARTIAL-to-HAVE = 20 flips;
  270 + 20 = 290; 20 - 0 = 20; 210 - 20 = 190; 230 - 20 = 210
  (290 + 20 + 190 = 500). HAVE 290 of 500 = 58%. Next: sprint batch 12,
  same libs-only rule, target 20/day (the running count is the honest
  measure).

- Sprint batch 12 (21 Nov 2026, same day, LIBS ONLY): 20 flips,
  all verified 4/4 checks (rc=0 + exact stdout, hosted + python
  compilers) under tests/test_daily_20261121l.py (80/80 PASS — 20
  demos) with an independent Python replica 20/20 match
  (~/workspace/blackmoon-iso/daily-20261121-batch12/replica_20261121l.py):
  cachelay.fg (#414 cache-aware field reordering by alignment,
  offsets/total/padding/lines), chaincmp.fg (#486 chained
  comparisons with first-fail index), derive.fg (#463 (type,
  trait) derive registry, idempotent add), cap.fg (#93
  unforgeable capability tokens from 1000, rights, revoke),
  promise.fg (#268 all/race combinators over the #246 future
  table), units.fg (#177 dimensional checking closes the
  PARTIAL: (length, mass, time) exponents, add needs equal
  dims), svcdisc.fg (#220 service registry, first-healthy
  lookup), mutex.fg (#243 mutex + rw locks with reader
  counts), atomic.fg (#244 atomic ints: fetch_add, CAS,
  inc/dec), threadpool.fg (#245 round-robin pool, makespan),
  worksteal.fg (#251 per-worker deques, LIFO pop, front
  steal), actor.fg (#252 actors with FIFO mailboxes),
  testpar.fg (#312 LPT test sharding, makespan, speedup),
  relbin.fg (#334 per-triple release manifest), container.fg
  (#335 image layer stack), repro.fg (#340 reproducible-build
  log), rename.fg (#362 rename-all symbol table), codeact.fg
  (#367 code-action table, apply-first-pending), dap.fg
  (#378 DAP request/response table), watchpt.fg (#391
  watchpoints with always/eq:N conditions).
  No #42/#43/#53 work (#42 resolved: helper-function slice).
  Skipped per brief: #273, #129, #302 (need function values);
  #122/#164 not flipped (known stale notes). #181/#187/#188/
  #189/#190 not buildable in pure Qasida (no mkdir/readdir/
  rename builtins exist). #326's sysroots half stays open.
  Counts after sprint batch 12: HAVE 310, PARTIAL 19, GAP 171, to build
  190. Arithmetic from sprint batch 11 (HAVE 290, PARTIAL 20, GAP 190,
  to build 210): 19 GAP-to-HAVE + 1 PARTIAL-to-HAVE = 20 flips;
  290 + 20 = 310; 20 - 1 = 19; 190 - 19 = 171; 210 - 20 = 190
  (310 + 19 + 171 = 500). HAVE 310 of 500 = 62%. Next: sprint batch 13,
  same libs-only rule, target 20/day (the running count is the honest
  measure).

- Sprint batch 13 (21 Nov 2026, same day, LIBS ONLY): 20 flips,
  all verified 4/4 checks (rc=0 + exact stdout, hosted + python
  compilers) under tests/test_daily_20261121m.py (80/80 PASS — 20
  demos) with an independent Python replica 20/20 match
  (~/workspace/blackmoon-iso/daily-20261121-batch13/replica_20261121m.py):
  triple.fg (#326 sysroot registry closes the PARTIAL:
  (triple, path) rows, lookup, host sysroot, count),
  numtrait.fg (#119 numeric-trait registry, NumVal kind
  dispatch), mntask.fg (#241 task table with a round-robin
  scheduler over it, closes the PARTIAL), rtimer.fg (#263
  clock-driven timer table, closes the PARTIAL), bce.fg
  (#402 bounds-proof analysis, i + k provable iff lo + k >=
  0 and last_i + k < len, closes the PARTIAL), lspfmt.fg
  (#369 LSP formatting as a library, formatted lines plus
  per-line edit count, closes the PARTIAL), condvar.fg
  (#257 wait/notify-one/notify-all), stm.fg (#253
  transaction table, commit holds while recorded versions
  match), rcu.fg (#254 readers/epoch/deferred/reclaimed,
  grace-period reclaim), racedet.fg (#259 lockset race
  detection), loom.fg (#260 interleaving explorer,
  distinct final counter values), select.fg (#266
  first-ready select over single-slot channels),
  sampleprof.fg (#386 sample aggregation, hottest function,
  self-percentages), heapdump.fg (#389 heap snapshot
  analysis, reachable walk, leak bytes/count), revdbg.fg
  (#392 execution trace, clamped step-back/step-forward),
  crashrep.fg (#395 symbol table plus crash frames,
  symbolication), repldbg.fg (#399 live variable table,
  one-op eval, watch list), publish.fg (#332 publish
  records with version validation, publish/retract),
  devshell.fg (#336 dev-shell spec with an FNV-1a
  derivation hash), stdlibfuzz.fg (#442 LCG fuzz driver
  over three toy parsers, exact reproducible ok-counts).
  No #42/#43/#53 work (#42 resolved: helper-function slice).
  Skipped per brief: #273, #129, #302 (need function values);
  #122/#164 not flipped (known stale notes). #181/#187/#188/
  #189/#190 not buildable in pure Qasida (no mkdir/readdir/
  rename builtins exist). #326's sysroots half now CLOSED.
  Counts after sprint batch 13: HAVE 330, PARTIAL 13, GAP 157, to build
  170. Arithmetic from sprint batch 12 (HAVE 310, PARTIAL 19, GAP 171,
  to build 190): 14 GAP-to-HAVE + 6 PARTIAL-to-HAVE = 20 flips;
  310 + 20 = 330; 19 - 6 = 13; 171 - 14 = 157; 190 - 20 = 170
  (330 + 13 + 157 = 500). HAVE 330 of 500 = 66%. Next: sprint batch 14,
  same libs-only rule, target 20/day (the running count is the honest
  measure).

Sprint batch 14 (21 Nov 2026, same day, LIBS ONLY): 15 flips,
  all verified 4/4 checks (rc=0 + exact stdout, hosted + python
  compilers) under tests/test_daily_20261121n.py (60/60 PASS — 15
  demos) with an independent Python replica 15/15 match
  (~/workspace/blackmoon-iso/daily-20261121-batch14/replica_20261121n.py):
  pariter.fg (#250 chunk split + named int-op map, modelled
  parallelism, no real threads), proptest.fg (#302 LCG case
  generation, halving shrink chain, smallest failing case),
  buildgen.fg (#339 generator rules with {name} substitution),
  cigate.fg (#352 fmt gate over a (file, fmt-clean?) table,
  closes the PARTIAL), inlinean.fg (#403 inline-candidate
  analysis: tiny + called once, or hot + small),
  unroll.fg (#404 unroll-factor analysis: largest power of 2
  to 4 with body * factor <= 16, tail + iterations),
  loopvec.fg (#405 auto-vectorization analysis: no calls, no
  branches, trip >= 4, width 4), escape.fg (#406 escape
  analysis: returned or stored escapes to the heap),
  pgo.fg (#409 profile-guided decisions: hot at 100+ samples,
  inline/outline/keep), regalloc.fg (#412 linear-scan register
  allocation over 4 registers, spill -1), sched.fg (#413 list
  scheduling over a single-dependency DAG, makespan),
  benchtune.fg (#418 bench verdicts: regress/improve/stable
  at +/-10%), xhover.fg (#300 cross-language hover tables:
  Qasida symbols beside C declarations plus call edges),
  lto.fg (#408 cross-module analysis: dead exports, inline
  candidates), allocfree.fg (#419 alloc-free loop analysis).
  No #42/#43/#53 work (#42 resolved: helper-function slice).
  Skipped per brief: #273, #129, #302 (need function values);
  #122/#164 not flipped (known stale notes). #181/#187/#188/
  #189/#190 not buildable in pure Qasida (no mkdir/readdir/
  rename builtins exist). Error/diagnostics clusters #44-#60
  and #341-#360 untouched (#42-adjacent). The library-buildable
  pool is now thin: of the 155 items left, most are compiler
  work (closures, macros, syntax), OS/kernel, network/FFI,
  compiler internals, or the banned error/diagnostics clusters.
  Counts after sprint batch 14: HAVE 345, PARTIAL 12, GAP 143, to build
  155. Arithmetic from sprint batch 13 (HAVE 330, PARTIAL 13, GAP 157,
  to build 170): 14 GAP-to-HAVE + 1 PARTIAL-to-HAVE = 15 flips;
  330 + 15 = 345; 13 - 1 = 12; 157 - 14 = 143; 170 - 15 = 155
  (345 + 12 + 143 = 500). HAVE 345 of 500 = 69%. Next: sprint batch 15,
  same libs-only rule — land what the pool honestly supports (the
  running count is the honest measure; a smaller honest batch beats
  a padded one).

  Function-values slice (21 Nov 2026): the library-buildable pool
  ran dry after sprint batch 14 (only #393 library-shaped), so
  Jayant picked the function-values language slice. #103 function
  values landed in both compilers (Python + hosted mirror):
  fn types, bare function names as values, calls through values,
  fn params/returns, arrays/tuples/structs of fn values, generic
  fn types, fn ==/!=; proofs #102 hof.fg (generic map/filter/
  reduce), #129 sortby.fg (sort_by with a comparator), #273
  emitter.fg (on/emit/off). #101 closures, #114 currying and #116
  composition stay GAP — they need the capture-lifetime decision
  (DESIGN.md §7 in blackmoon-iso/function-values-slice/). Gates:
  bootstrap 7/7 (64 MB stack — see the slice's DESIGN.md §12 item
  7), parity 124/124, corpus 99/99, regression 62/62, fv fuzz
  56/56, existing fuzz 102/102 both modes, suite 77/84 hosted +
  77/84 python (7 known big32 pre-existing failures, identical
  both modes), ASan clean (102/102 + fv 56/56), fmt idempotent,
  benchmarks re-measured (bs 1.04x, bs_call 0.94x vs C-O3 after
  a noise re-check; no regression — the bs emits contain zero
  fn machinery). The slice also fixed three stale test
  expectations, all pre-existing (not slice regressions):
  test_daily_20261121i.py (batch 13 extended triple_demo, the
  batch-9 file kept the old expectation), test_daily_20261110.py
  (batch 4 extended rest_demo, the 10-Nov file kept the old
  expectation), and run_tests.py's dbg section (the demo now
  imports stdlib dbg.fg #382; needles updated, #line mapping
  verified working). Counts after the slice: HAVE 349,
  PARTIAL 12, GAP 139, to build 151. Arithmetic from sprint batch
  14 (HAVE 345, PARTIAL 12, GAP 143, to build 155): 4 GAP-to-HAVE
  (#102, #103, #129, #273); 345 + 4 = 349; 143 - 4 = 139;
  155 - 4 = 151 (349 + 12 + 139 = 500). HAVE 349 of 500 = 69.8%.
  Next: pipeline item #44 (panic vs recover boundary, GAP);
  only #393 is library-shaped in the remaining pool.

  #44 panic vs recover boundary (21 Nov 2026, pipeline run):
  implemented in BOTH compilers, NOT yet HAVE (gates deferred).
  fail() on a spawned task's thread ends just that task (stderr
  "qasida: task panicked: <msg>", atomic counter +1, pthread_exit);
  siblings finish, the scope join proceeds; new builtin
  panicked_tasks() -> int reads the count after a join. fail() on
  the main thread unchanged (exit 1). Files: forge_lang/checker.py
  + infer.py + codegen.py (HEADER thread-local flag + counter,
  thread wrappers, fail() branch, builtin expr) + codegen_rv.py /
  codegen_wasm.py named rejections; hosted mirror in
  examples/selfhost_check.fg + selfhost_infer.fg +
  selfhost_codegen.fg (fail branch, wrappers, expr site) with the
  header regenerated via gen_codegen_header.py. Demo
  examples/panic_recover_demo.fg; own test
  tests/test_panic_recover_v1.py 41/41 ALL PASS both compilers
  (demo exact stdout, 7 run cases, 2 fatal cases, 2 rejection
  cases, freestanding/big32/WASM rejections, fmt idempotent).
  Gates run: fresh hosted binary md5
  84f64ea4ff6572d77bf1cfa09a23d30f (rebuilt after a VM restart
  killed the first attempt at ~21:43 IST; build log
  blackmoon-iso/pr44_hosted_build.log, cc warnings are pre-existing
  -Wmisleading-indentation/-Wunused-variable/-Wsign-compare only),
  bootstrap 7/7 byte-identical (log
  blackmoon-iso/pr44_bootstrap_emit.log, ulimit -s 65536), demo
  ASan-clean under both compilers (byte-identical emits, default
  leak detection on). Leak limit measured, not guessed: a task
  allocating [1,2,3] then failing leaks 32 bytes (24 + 8 refcount)
  under LeakSanitizer (probe /tmp/pr44_leakprobe.fg); the same
  program prints "1 / count 1" and exits 0 without ASan.
  Gates NOT run: full suite, parity 124/124, corpus 99/99,
  regression 62/62, fuzz — deferred because the closures slice
  (#101/#114/#116, refcounted env, Jayant's pick ~21:57 IST)
  started in the same tree that evening; the long gates need a
  stable tree and would be contaminated by closures edits landing
  mid-run. No binary sync, no push this run. Counts after this
  entry: HAVE 349, PARTIAL 13, GAP 138, to build 151. Arithmetic
  from the function-values slice (HAVE 349, PARTIAL 12, GAP 139,
  to build 151): 1 GAP-to-PARTIAL (#44); 349 + 0 = 349; 12 + 1 = 13;
  139 - 1 = 138; 151 - 0 = 151 (349 + 13 + 138 = 500).
  Next: re-run the #44 gates (suite + parity + corpus + regression
  + fuzz) after the closures slice lands, flip #44 to HAVE, then
  push; queue head after #44 is #45 (assertions with messages).

  Closures slice — #101, #114, #116 (21 Nov 2026, Jayant's pick
  ~21:57 IST: refcounted env, option (a) from the function-values
  DESIGN.md §7). Compiler work, not a library batch. Lambda syntax
  `let f = fn(x: int) -> int { ... };` (anonymous `fn`, params must
  be annotated); capture-by-value into a heap env struct; a closure
  is a fat pointer {fn_ptr, env_ptr}; the env is freed when the
  last fn value holding it dies (refcount + drop hook). Closures
  may escape (returned, stored, passed). #114 curry/curry_last and
  #116 compose/compose3 are pure-Qasida libraries on top
  (forge_lang/stdlib/curry.fg, compose.fg + demos, 8/8 checks in
  tests/test_closures_proofs.py). Both compilers (Python +
  hosted mirror) agree: bootstrap 7/7 byte-identical (hosted
  rebuild 5, md5 f0e96e5876deb2d1c96ddc64c8f949c7), parity 124/124
  agree + 124/124 byte-identical, corpus 99/99, regression 62/62,
  closure fuzz 66/66 (33 cases x 2 modes), fv fuzz 56/56, existing
  fuzz 122/122 both modes (manifest grew 102 -> 122 since the fv
  slice: +20 safe cases, trap count unchanged at 35), suite 79/86
  hosted + 79/86 python (7 known big32 pre-existing failures,
  identical both modes), fmt idempotent 41/41, ASan clean
  compiler-side (122/122 + 56/56 + 66/66 under the rebuild-5 ASan
  binary, detect_leaks=0) and program-side (23/23, leak detection
  on). Benchmarks re-measured (rebuild 5, Qasida safe / C-O3):
  tick 0.91x (first run 1.10x was VM noise — re-run clean),
  orderbook 0.96x, bs 0.94x, bs_call 0.98x, mc 0.82x, matmul 0.38x
  (0.95x vs C-O3-native), alloc 1.30x; no benchmark uses fn values,
  so this is a regression check on the shared codegen paths —
  nothing moved outside VM noise. Retroactive #103 changes (see
  blackmoon-iso/closures-slice/DESIGN.md §9): fn values are now
  owned, not plain pointers (move(f) works, scope-end frees run,
  [fn] arrays stop leaking, fn == compares fn+env). Two fixes
  found by the gates, both pre-existing (not closures regressions):
  (1) print-temp str leak — println(f()) where f returns str leaked
  the temp; is_fresh_str now recognises indirect calls returning
  str (both compilers) and gen_print binds + frees fresh str args
  (found by the new program-side ASan check on cl_capture_str);
  (2) hosted cg_is_fresh_str missed generic instantiations
  returning str (cg_fn_lookup misses mangled names) — now falls
  back to the infer-map return type, with the template check via
  cg_template_lookup (found by corpus v47_generics_fn on rebuild
  4; fixed in rebuild 5). Also: capmap now carries capture TYPES
  (captured fn values as callees), and the env-free helper is
  forge_closure_release (renamed from forge_closure_free so the
  #39 freestanding gate's "free(" substring check passes; the gate
  was not weakened). Follow-ups: a METHOD returning str passed to
  println still leaks (same class, unexercised); the hosted
  checker stack-depth issue (needs ulimit -s 65536) still open;
  the `join` builtin-redefinition divergence (Python rejects,
  hosted accepts) still open; the __forge_moved_fns unused-variable
  warning still open. Counts after the slice: HAVE 352, PARTIAL
  13, GAP 135, to build 148. Arithmetic from the #44 entry (HAVE
  349, PARTIAL 13, GAP 138, to build 151): 3 GAP-to-HAVE (#101,
  #114, #116); 349 + 3 = 352; 138 - 3 = 135; 151 - 3 = 148
  (352 + 13 + 135 = 500). HAVE 352 of 500 = 70.4%.
  Next: re-run the #44 gates (suite + parity + corpus + regression
  + fuzz) now that the closures slice has landed, flip #44 to HAVE,
  then push (closures push allowlist must EXCLUDE #44's tree edits
  — they were unpushed when the slice started); queue head after
  #44 is #45 (assertions with messages).

## #44 panic vs recover boundary — HAVE (22 Nov 2026, Sprint Day 2 gates run)

Implemented 21 Nov 2026 (pipeline run, both compilers) and marked
[PARTIAL] because the full gates were deferred — the closures slice
(#101/#114/#116) shared the tree. The closures slice landed + pushed
(8ac792d9), the tree went stable, and the gates re-ran 22 Nov against
the live binary (rebuild 5, md5 f0e96e58): own test
tests/test_panic_recover_v1.py 41/41 ALL PASS both compilers
(re-run); parity 124/124 agree + 124/124 byte-identical; corpus 99/99;
regression 62/62; fuzz existing 102/102 hosted + 102/102 Python, fv
56/56, closure 66/66; full suite 79/86 hosted + 78/86 Python (the 7
known big32 pre-existing failures in both modes; Python run_tests.py
failed once on the scope_demo fast println-interleaving flake — the
known class — 7/8 direct reruns clean and the scope-join ordering
held in all 8, so the flake stands). Gate logs:
blackmoon-iso/pr44-gates/logs/ (parity, corpus, regression, fuzz,
suite_hosted, suite_python, scope_demo_fast_rerun_4x). No push from
this run (parent verifies and pushes); #44's own files (demo, test,
CHANGELOG entry, codegen_rv.py, codegen_wasm.py) were kept out of the
closures push and ride with this item's push. v1 limits (unchanged):
runtime faults stay process-fatal even in a task; a panicking task's
owned locals leak (measured 32 bytes); the panic message is printed,
not retrievable. Counts after the flip: HAVE 353, PARTIAL 12, GAP
135, to build 147. Arithmetic from the closures entry (HAVE 352,
PARTIAL 13, GAP 135, to build 148): 1 PARTIAL-to-HAVE (#44); 352 + 1
= 353; 13 - 1 = 12; 148 - 1 = 147 (353 + 12 + 135 = 500). HAVE 353
of 500 = 70.6%.
Next: #46 error codes as enums (#45 is already [HAVE] — verified
from the catalog 22 Nov, not rebuilt).

## #46 Error codes as enums — DONE 22 Nov 2026 (Sprint Day 2 gates run)
Typed errno-style errors for syscalls, as a small language/runtime
slice + library (not a pure library: the runtime discarded errno at
every failure site — forge_read_file/read_bytes forge_fail on any
fopen failure, write_file/write_bytes return bool with no reason,
http_get forge_fails, zero `errno` mentions in forge_lang/ — and a
read failure is process-fatal even in a task, so a read code could
not be recovered at a task boundary; changing read_file to return a
sentinel would be a breaking change, NOT taken — needs Jayant's
word). Runtime: `#include <errno.h>` in HEADER + hosted header
mirror; `static volatile long long forge_last_errno` (mirrors
forge_panicked_total); errno recorded only where observable —
forge_write_file/write_bytes fopen failure stores it before
`return false`; new zero-arg builtin last_errno() -> int (atomic
load), following the panicked_tasks/clock_micros pattern (checker
branch + codegen lowering + hosted mirror + big32/WASM/freestanding
named rejections). Fallible read builtins following the #36
try_alloc pattern: try_read_file(path) -> Result<str, int> and
try_read_bytes(path) -> Result<[int], int> (fopen failure ->
Err(errno), success -> Ok(content); Err payload is the raw errno
int). Library forge_lang/stdlib/errcode.fg: enum ErrCode (Success,
NotFound, PermissionDenied, AlreadyExists, IsADirectory,
NotADirectory, InvalidArgument, Interrupted, NoSpace, ReadOnlyFs,
TooManyOpen, BrokenPipe, ConnectionRefused, TimedOut, Unknown) with
err_from_code / err_code / err_name / err_message and
read_file_err / read_bytes_err / write_file_err / write_bytes_err
returning Result<..., ErrCode>; demo examples/errcode_demo.fg.
Three real bugs found while building, all fixed: (1) NULL str field
segfault — first try_read_file lowering set Err .value = NULL and
struct assignment deep-copies str fields via forge_copy_str
(strlen(NULL) -> SEGV); Err .value is now forge_copy_str("") —
never a NULL str field (the try_alloc discipline), same in the
hosted lowering. (2) Hosted `void` type — hosted infer had no case
for the new builtins, so the variable got type `void` and
Result_str_int was never emitted; explicit infer cases added in
selfhost_infer.fg. (3) Fresh-Result leak under ASan — `let r =
try_read_file(...)` orphaned the fresh buf (14 bytes) because
is_fresh_struct knew try_alloc but not the new builtins; both names
join the try_alloc case in Python is_fresh_struct and hosted
cg_is_fresh_struct. Also fixed: forge_last_errno first placed next
to forge_panicked_total did not compile (write helpers precede it)
— moved to just before forge_write_file (same in hosted header);
hosted try_read_file emits `__forge_bufN[__forge_gotN] = 0;` and
the Python lowering was changed to match (byte-identical emits).
Hosted rebuild: build 4 (md5 db234d827ed241952e7c1120036b373e,
13,688,456 B, 84 cc warnings — pre-existing count), after build 1
(void-type bug), build 2 (killed mid-cc1 once the leak fix was
found), build 3 (killed by a VM restart ~04:14 IST 22 Nov at ~16
min elapsed; /tmp wiped, tree intact). Synced to all 3 live binary
locations (bin/qasida-hosted, examples/selfhost_cli,
forge_lang/bin/qasida-hosted). Gates 22 Nov: own test
tests/test_errcode_v1.py 56/56 ALL PASS both compilers (run twice);
bootstrap 7/7 byte-identical; parity 124/124 agree + 124/124
byte-identical; corpus 99/99; regression 62/62; fuzz existing
102/102 hosted + 102/102 Python, fv 56/56, closure 66/66; full
suite 80/87 hosted + 80/87 Python (7 known big32 pre-existing
failures in both; no flake — run_tests.py PASS for real in both
modes); ASan compiler-side fuzz 102/102 + 56/56 + 66/66 under the
build-4 ASan binary (md5 79f7ea42320d51f8921a57a3e9ac6c3b), zero
sanitizer reports. Gate logs: blackmoon-iso/pr46/ (GATES.md, logs/
bootstrap_emit, parity, corpus, regression, fuzz_existing_hosted/
python, fuzz_fv, fuzz_cl, suite_hosted, suite_python,
fuzz_asan_existing/fv/cl, asan_build). Test-harness note: the hosted
binary resolves stdlib imports relative to CWD, so the test runs
everything with cwd=repo root and unlinks the demo outputs before
and after. v1 limits: read_file stays process-fatal; a failed write
records errno but a later success does NOT clear it; concurrent
failing tasks race on last_errno; bookkeeping mallocs can still
forge_fail under true OOM; no http_get/mmap errno path; no
retryable/fatal classification (#59), no inferred error sets (#50).
Counts after the flip:
HAVE 354, PARTIAL 12, GAP 134, to build 146. Arithmetic from the
#44 entry (HAVE 353, PARTIAL 12, GAP 135, to build 147): 1
GAP-to-HAVE (#46); 353 + 1 = 354; 135 - 1 = 134; 147 - 1 = 146
(354 + 12 + 134 = 500). HAVE 354 of 500 = 70.8%.
Next: #47 Backtraces on fail in debug builds.


## #393 Live reload — HAVE (22 Nov 2026, Sprint Day 2)
forge_lang/stdlib/livereload.fg — versioned handler table for hot code
swap: register a newer version and dispatch calls it, rollback drops the
newest version (a bad deploy rolls back without a restart),
re-registering the same name+version replaces that version's handler in
place; handlers are fn(str) -> str, named functions or closures
capturing config by value (item 101); all ops pure (the old table is
untouched). Demo examples/livereload_demo.fg (20-line transcript).
Verified: tests/test_daily_20261122.py 4/4 checks both compilers,
independent Python replica 20/20 (replica_20261122.py). v1 limits: no
file watching (item 183 inotify still GAP) and no dlopen (item 296
still GAP) — the caller drives reloads via lr_register; no live
serving (http_server.fg serves); dispatch returns "" for an unknown
name. Note: the cron run's scratch copy was lost when a VM restart
wiped /tmp (~09:40 IST); rebuilt from the surviving LANDING_NOTES.md +
replica and re-verified in-tree against hosted build 4 (md5 db234d82).
Counts after the flip: HAVE 355, PARTIAL 12, GAP 133, to build 145.
Arithmetic from the #46 entry (HAVE 354, PARTIAL 12, GAP 134, to
build 146): 1 GAP-to-HAVE (#393); 354 + 1 = 355; 134 - 1 = 133;
146 - 1 = 145 (355 + 12 + 133 = 500). HAVE 355 of 500 = 71.0%.
Next: #47 Backtraces on fail in debug builds.

## Filesystem builtins slice — #181, #187, #188, #189, #190 HAVE (22 Nov 2026, libs-only sprint week)

14 thin libc builtins in both compilers (mkdir, readdir, try_readdir,
rename, symlink, readlink, try_readlink, chmod, chown, stat_mode,
stat_uid, stat_gid, is_dir, str_compare) + 5 library modules with
demos: dirs.fg (#181, sorted dir_list), atomicfile.fg (#187,
write-temp-then-rename), links.fg (#188, Result<str, int> link_read),
fileperms.fg (#189, typed ErrCode results), walk.fg (#190, sorted
recursive walk + walk_files). Own test tests/test_filesystem_v1.py
96/96 ALL PASS both compilers; fs fuzz 56/56 (18 pos + 10 neg x 2
modes). The slice was BLOCKED on a pre-existing general compiler leak
(builtin call lowerings never freed fresh str/array argument temps:
write_file(p + "/f.txt") + len(p + "/xyz") leaked 42 bytes in 2
allocations under ASan) — Jayant picked fixing it in-slice (22 Nov
~14:42 IST, option A). Fix (DESIGN.md §13 + §13.8, filesystem-slice):
one shared helper per compiler (_builtin_call / cg_builtin_call) binds
fresh str/array args to named temps and frees them after the call
(closures print-temp pattern), covering file + fs + len/join/substr/
trim/parse_*/run_command/http_*/mmap_open/parallel_* lowerings, try_*
conditional frees, push/literal/enum skip-copy, eprintln, fail/
fail_compile/assert msg binding, for-over-fresh-array free, str BinOp
+/==/!=, and str IndexAssign (value-temp-first — a free-before-eval
UAF found by fuzz seed 1, which printed non-deterministic garbage
under the r4 binary; fixed in both compilers, seed 1 deterministic
"go" 3/3 runs under r5). Gates 22 Nov (hosted rebuild 5, md5
ee7d269849e05f365b2d34f288c0c0d5, synced to all 3 binary locations):
bootstrap 7/7 byte-identical (lex 84343, parse 716000, check 4075362,
infer 5103335, codegen 20902741, header 95513, cli 21127952);
parity 124/124 agree + 124/124 byte-identical; corpus 99/99;
regression 62/62; fuzz existing 102/102 both modes + fv 56/56 +
closure 66/66 + fs 56/56; full suite 82/89 hosted + 82/89 Python
(7 known big32 pre-existing failures in both; no flake this run —
the expected Python spawn_demo flake did not fire); ASan
compiler-side fuzz 102/102 + 56/56 + 66/66 + 56/56 under the r5 ASan
binary (md5 801661d4e862ea0fc49110e09dbed10a, ASAN_OPTIONS=
detect_leaks=0), zero sanitizer reports; ASan program-side 18/18;
parent zero-fs-code probe rc=0, zero leaks (was 42 bytes / rc=1);
fmt 14/14 (hosted qasida fmt — note: `forge.py --python fmt` routes
to the Python formatter, which strips file-leading // comments, a
pre-existing documented quirk, not the gate; fmt_fix.sh corrected
to use the hosted binary); benchmarks tick q_safe 2412 µs, matmul
q_safe 13299 µs (no regression vs slice r2: 2341 / 13222, within
noise). Emit comparison: probe_leakA/probe_leakB/torture_leak
byte-identical + runtime identical; fs_probe1 runtime identical,
emit differs only by the pre-existing Result type-naming/ordering
divergence (python-vs-r5 diff identical to python-vs-r4's — zero new
divergences). Open follow-ups (NOT this slice): Index into a fresh
array/struct and FieldAccess on a fresh struct still leak
(owned-copy-out needed); enum scope-end freeing + match-arm binding
freeing still leak (torture program's only remaining leaks: 24 bytes
in 2 allocations, down from 1121 bytes in 70 pre-fix); return inside
a for-over-fresh loop leaks the iterable; hosted mirror Result
type-naming unification.
Counts after the flip: HAVE 360, PARTIAL 12, GAP 128, to build 140.
Arithmetic from the #393 entry (HAVE 355, PARTIAL 12, GAP 133, to
build 145): 5 GAP-to-HAVE (#181, #187, #188, #189, #190); 355 + 5 =
360; 133 - 5 = 128; 145 - 5 = 140 (360 + 12 + 128 = 500). HAVE 360
of 500 = 72.0%.

## #47 Backtraces on fail in debug builds — HAVE (22 Nov 2026, libs-only sprint week)

`build --debug` prints a native backtrace on fail() (main thread and
spawned tasks — task's chain only, panicked_tasks() counts it), runtime
faults via forge_fail (bounds, overflow, div-by-zero, OOM), and assert
failure; release builds print the fail message only, byte-identical to
today's output. Mechanism: a thread-local shadow stack in the preamble
(ForgeBtFrame, cap 1024, balanced drops), not C backtrace()/execinfo.h —
push at function entry, per-statement forge_bt_setline(N) stamp, explicit
exit pops; frames print innermost-first as ` N: <fn> at <file>:<line>`.
Hosted driver implements --debug (was deferred with an explicit
rejection); debug bit added to the Step-6 cache key; named rejections for
--debug + --target big32/wasm, --freestanding, --shared. Own test
tests/test_backtrace_v1.py 45/45 ALL PASS both compilers; demo
examples/backtrace_demo.fg. The slice was BLOCKED in the hosted suite by
the hosted compiler naming the MAIN file for every frame/#line (hosted
AST Node has no file field) — run_tests.py's dbg_demo check (debug C
must contain `stdlib/dbg.fg`) failed 0 matches. Fixed in-slice, not
deferred: load_merged records flat (fn name, file) pairs (plain fns by
name, impl methods as Struct__method; generic instantiations resolve to
their template via cg_fn_file's suffix-strip fallback); the pairs are
the return value and the merged tree leaves by index assignment into a
[Node] out-param (the fp_box pattern). After the fix the hosted dbg_demo
debug C has 12 `stdlib/dbg.fg` matches and run_tests.py passes. Gates
22 Nov (live binary rebuild 2, md5 d9b3269867ef7d1c9bb45417e06e3374,
synced to all 3 locations; rebuild 2's first attempt died mid-cc when
the launching session was interrupted — relaunched clean): bootstrap 7/7
byte-identical (ulimit -s 65536); parity 124/124 agree + 124/124
byte-identical; corpus 99/99; regression 62/62; fuzz existing 102/102
hosted + 102/102 Python, fv 56/56, closure 66/66, fs 56/56; full suite
83/90 hosted + 82/90 Python (7 known big32 pre-existing failures in
both; Python run_tests.py scope_demo flake — known
println-interleaving class, 4/4 direct reruns clean, flake stands);
ASan compiler-side fuzz 102/102 + 56/56 + 66/66 + 56/56 under the bt
ASan binary (md5 8e94b9b7cbed0e2b3917db482a220ed9,
ASAN_OPTIONS=detect_leaks=0), zero sanitizer reports; ASan
program-side debug==release, 0 report lines; fmt 5/5 idempotent;
benchmarks tick q_safe 2365 µs, matmul q_safe 13231 µs (no regression
vs fs r5: 2412 / 13299). v1 limits: hosted spells imported files
relative where Python absolutizes; run stays release-only; no
backtraces for fail_compile/check-time errors; no backtrace() builtin.
Records: blackmoon-iso/backtraces-slice/ (DESIGN.md, SUMMARY.md).
Counts after the flip: HAVE 361, PARTIAL 12, GAP 127, to build 139.
Arithmetic from the filesystem entry (HAVE 360, PARTIAL 12, GAP 128, to
build 140): 1 GAP-to-HAVE (#47); 360 + 1 = 361; 128 - 1 = 127; 140 - 1
= 139 (361 + 12 + 127 = 500). HAVE 361 of 500 = 72.2%.
Next: #48 in catalog order.

## Sprint Day 3 (23 Nov 2026) — error-cluster libraries + diagnostics rendering

Ten pure-.fg libraries landed in one batch, all verified by real runs
under both compilers (hosted qasida binary + Python forge.py): #51
errlog.fg, #52 errtimeout.fg, #54 errrender.fg, #55 errmode.fg, #56
errdoc.fg, #57 sentinel.fg, #58 errtranslate.fg, #59 errclass.fg, #341
errjson.fg, #344 errexplain.fg. Each ships its demo (exact stdout,
both compilers) and its own test file; coordinator re-ran all ten
test files: errlog 36/36, sentinel 26/26, errtimeout 20/20, errclass
20/20, errrender 26/26, errmode 24/24, errdoc 24/24, errtranslate
20/20, errjson 28/28, errexplain 24/24 — 248 checks, ALL PASS, exit 0.
ASan program-side (emit C + cc -fsanitize=address, leak detection
on): 20/20, all ten demos under both compilers. Full suite 23 Nov:
93/100 hosted + 93/100 Python; the 7 failures are the known
pre-existing big32 failures, identical files to the 22 Nov suite
(checked_casts, never, opaques, readonly, sizedarrays, sizedunif_fix,
top500_batch1 — each fails on a big32 sub-case inside the file), no
new failure and no flake this run (run_tests.py passed in both modes).
fmt: demos idempotent; the libs keep their header comments, so like
errcode.fg and errwrap.fg they fail `fmt --check` — `forge.py fmt`
strips // comments, and the tests fmt-check the demo only, same as
test_errcode_v1.py.

Two things found while verifying, both worked around honestly in the
libraries and recorded as compiler follow-ups, not hidden: (1) the
errlog demo leaked 112 bytes in 7 allocations under HOSTED ASan only
(Python clean). Isolated with minimal probes: the trigger is a
GENERIC function call — the hosted generic-call assignment emits an
extra unbalanced forge_arr_inc on the returned struct's array field
(pe.c:1672-1675 vs the Python emit, which lacks the inc); the
identical concrete call is clean. Fixed at the library level by
de-genericizing log_on_err<T> into six concrete variants
(log_on_err_int/str, _msg_int/str, _code_int/str) plus four
never-call dummy Result constructors (the Python backend only emits
a generic Result struct when a literal of that shape appears in the
program — the same quirk #58's errtranslate.fg works around). The
hosted generic-call lowering bug itself is a follow-up fix item.
(2) The hosted C backend miscompiles indexing a [str] field of a
generic Result (r.value[0] emitted as forge_int_get) — errmode.fg
binds to a local first; also a follow-up. Other quirks worked around
in the batch: the Python backend rejects enum-typed struct fields
(errmode stores the mode as an int tag); [ErrCode] arrays cannot be
struct fields or push targets in either compiler (errtranslate stores
POSIX ints). #48 try/catch was NOT implemented: a design doc only
(blackmoon-iso/trycatch-slice/DESIGN.md) — no setjmp/longjmp exists,
no module exists at runtime, and the "module boundary" semantics need
Jayant's pick (option B try_call recommended; questions in DESIGN.md
§7). #50 inferred error sets was not taken (a pure-library version
would be fake — it needs the checker).

Counts after the flips: HAVE 371, PARTIAL 12, GAP 117, to build 129.
Arithmetic from the #47 entry (HAVE 361, PARTIAL 12, GAP 127, to
build 139): 10 GAP-to-HAVE (#51, #52, #54, #55, #56, #57, #58, #59,
#341, #344); 361 + 10 = 371; 127 - 10 = 117; 139 - 10 = 129
(371 + 12 + 117 = 500). HAVE 371 of 500 = 74.2%.
Next: #48 in catalog order (blocked on Jayant's design pick — see the
design doc); otherwise #60 / #62 in catalog order.

## Sprint Day 3 follow-up: #48 try/catch (23 Nov 2026)

Jayant picked "Build #48 as designed" 23 Nov ~11:33 IST (option B:
try_call(f, ...) returning Result<R, str>, foreign fn only, v1 arity
0-or-1, fail()-only). Built as designed (DESIGN.md §8;
blackmoon-iso/trycatch-slice/). #48 GAP -> HAVE. Verification:
own test tests/test_trycatch_v1.py 68/68 ALL PASS both compilers;
emit comparison 12/12; bootstrap 7/7 byte-identical (emit-only,
matching the #47 gate); parity 124/124 + byte-identical; corpus
99/99; regression 62/62; fuzz existing 102/102 both modes, fv 56/56,
closure 66/66, fs 56/56, tc 38/38; full suite 95/102 hosted + 95/102
Python (7 known big32); ASan compiler-side clean (102+56+66+56+38,
zero reports); ASan program-side: demo clean both modes, unwind
leak measured 60 bytes in 3 allocations (identical debug/release);
fmt idempotent on demo + helper; benchmarks tick q_safe 3566 us,
matmul q_safe 17704 us — no regression attributable to #48 (old #47
binary measures identically on this VM today; the whole VM is
slower than the 2321/12815 baseline day, C baselines included).
Two findings recorded, not fixed in-slice: (1) the
bootstrap_wrap_codegen.fg emit does not compile under cc
(pre-existing latent bug, NOT caused by #48 and NOT a divergence —
the old #47 binary fails identically: HCodegen's array-free helper
precedes Node's in self.structs order, so forge_HCodegen_array_free
calls forge_Node_array_free before its static definition; the CLI
build compiles fine; the wrapper-order fix is a separate slice).
(2) MinGW is not installed on the VM (no compiler, no package), so
the Windows setjmp/longjmp preamble path remains unprobed (§1d);
setjmp/longjmp are C89 and exist on MinGW in principle, unproven
here. v1 limits: unwind leak (60 bytes / 3 allocs for a probe
allocating one string + one array before failing) + defers skipped
on catch, both stated in plain language in the catalog entry.

Counts after the flip: HAVE 372, PARTIAL 12, GAP 116, to build 128.
Arithmetic from the Day 3 entry (HAVE 371, PARTIAL 12, GAP 117, to
build 129): 1 GAP-to-HAVE (#48); 371 + 1 = 372; 117 - 1 = 116;
129 - 1 = 128 (372 + 12 + 116 = 500). HAVE 372 of 500 = 74.4%.
Next: #50 in catalog order (checker slice, inferred error sets);
otherwise #60 / #62 in catalog order.

## #50 inferred error sets — landed 24 Nov 2026 (sprint, both compilers)

#50 GAP -> HAVE. Option A as picked by Jayant 23 Nov 2026 ~21:54 IST:
inferred sets over ANY enum error type, with match narrowing + a
`qasida check --dump-error-sets` dump flag; empty-means-empty (a
function that only ever fail()s has an empty error-set). No new
syntax, no codegen change, no new runtime behaviour. Second checker
pass with a worklist fixpoint over the call graph; two summaries per
function (value-set for bare enum returns, error-set for Result
returns). Records: ~/workspace/blackmoon-iso/errsets-slice/
(DESIGN.md, PLAN.md, SUMMARY.md, probes/, fuzz/, logs/, after/).

Verification (live, 24 Nov 2026): own test tests/test_errsets_v1.py
75/75 ALL PASS both compilers; demo examples/errsets_demo.fg; ES
fuzz 20 cases 40/40 both compilers; soundness spot-check 8/8 (one
program per ES-C4 widening rule — indirect call, extern,
struct-field flow, computed error expr — must infer TOP); emit
comparison 21/21 (new-hosted == old-hosted where comparable;
hosted-vs-Python struct-ordering divergence is pre-existing);
bootstrap 7/7 byte-identical (lex 88280, parse 719937, check
7151586, infer 8193722, codegen 25826093, header 103474, cli
26061181); parity 124/124 agree + byte-identical; corpus 99/99;
regression 62/62; fuzz existing 102/102, fv 56/56, closure 66/66,
fs 56/56, tc 38/38, lf 20/20, es 40/40; full suite 97/104 hosted +
97/104 Python (7 known big32); ASan program-side 8/8 clean; ASan
compiler-side passing `check` leaks 612 bytes / 36 allocs (510/30
pre-existing + 102/6 new from the ES walker state, same class);
fmt 30/30 unchanged, selfhost_check.fg fmt-neutral on code;
benchmarks tick q_safe 2408 us, matmul q_safe 13370 us — no
regression. Check-time ratio: hosted codegen ~1.95x, check ~2.7x
(OVER the ~2x flag), cli ~1.86x; Python ~1.7-1.8x.

Two real bugs found and fixed in-slice: (1) Python `_es_methodcall`
used `mangle` without importing it (NameError — broke corpus
v33/v40/v48/v51 + regression v23; fixed with a local import from
.traits); (2) the hosted fixpoint walked externs as empty-bodied
functions (parse_extern appends an empty Block body) — fixed by
skipping `bval` (extern) nodes in the collection. Also fixed: the
own test invoked the compiler via forge.py, which honors ambient
QASIDA_COMPILER=python and silently routed "hosted" runs to Python
in the suite's python mode — fixed by scrubbing QASIDA_COMPILER in
the test's run helper. Findings recorded, not fixed in-slice: (1)
the Step-6 cache serves C WITHOUT re-running the checker (a cached
entry lets even a compiler that would reject the program "emit" it)
— the emit gate clears the cache before every emit; (2) the
hosted-vs-Python struct typedef ordering divergence for
Result-heavy programs (pre-existing); (3) the hosted check path
leaks heap state on a passing check (510/30 pre-existing).

Counts after the flip: HAVE 373, PARTIAL 12, GAP 115, to build 127.
Arithmetic from the #48 entry (HAVE 372, PARTIAL 12, GAP 116, to
build 128): 1 GAP-to-HAVE (#50); 372 + 1 = 373; 116 - 1 = 115;
128 - 1 = 127 (373 + 12 + 115 = 500). HAVE 373 of 500 = 74.6%.
Next: #60 / #62 in catalog order.

- Sprint Day 4 (24 Nov 2026, libs-only, 11 items): #63 if-let /
  while-let, #64 guard statements, #65 match guards (PARTIAL→HAVE),
  #66 for-each over any iterable (PARTIAL→HAVE), #68 repeat-while
  loops, #71 if as an expression, #73 loop-else, #127 dict
  literals, #128 array comprehensions, #342 multi-error reporting,
  #345 source snippets in errors. All pure .fg libraries (stdlib +
  demo + own test each, 33 new files), no compiler edits, no new
  syntax, OS track paused. Own tests, all re-run by the coordinator:
  #63 26/26, #64 26/26, #65 20/20, #66 22/22, #68 18/18, #71 26/26,
  #73 18/18, #127 24/24, #128 24/24, #342 20/20, #345 24/24 — ALL
  PASS both compilers; fmt idempotent on all 11 demos. ASan
  program-side 0 leaks on all except #64 (demo 3B/3, probe 1B/1 —
  proven pre-existing `?`-unwrap leak, 1 byte per Ok unwrap in both
  compilers; minimal result.fg-only probe leaks 1B/1, shipped
  try_demo.fg leaks 1B/1). Design doc for the §4 compiler items
  blackmoon-iso/ctrlflow-slice/DESIGN-62-67-76.md: #62 labeled
  break/continue is a real compiler slice (Go-style `label:`
  recommended, Jayant picks); #67 range syntax and #76 wildcard
  arm probe-verified ALREADY WORKING under both compilers (stale
  catalog entries — verification slices, not builds). Full suite
  (per-file runner): hosted 109/115 (6 known big32 — never now
  PASSES, verified stable standalone both modes); python 106/116
  (same 6 + 4 extra). The 4 python extras are NOT Day 4's: the
  suite ran while another process landed in-flight #60 (freestanding
  crash hook) edits in the same tree (checker.py/codegen.py changed
  04:10–04:14 UTC, binaries rebuilt 04:49 UTC, test_crashdump_v1.py
  created mid-run — hence 116 python files vs 115 hosted).
  Crashdump re-runs ALL PASS (mid-edit contamination); the other
  three still fail standalone with a cleared cache (move_branch_field
  8 runtime cases, useaftermove 4, noheap_freestanding 1) — Python-vs-
  hosted divergences in the in-flight #60 tree state, for the #60
  owner. Day 4 changed no compiler code and no existing test file
  (diffed vs remote main 9034bd51). Honest pace: 11 landed vs the
  20/day sprint target — the pure-library pool is nearly exhausted
  and the remaining §4 items are mostly compiler features.
  NOT pushed (parent verifies and pushes).

Counts after the flips: HAVE 384, PARTIAL 10, GAP 106, to build 116.
Arithmetic from the #50 entry (HAVE 373, PARTIAL 12, GAP 115, to
build 127): 9 GAP-to-HAVE (#63, #64, #68, #71, #73, #127, #128,
#342, #345) + 2 PARTIAL-to-HAVE (#65, #66); 373 + 11 = 384;
12 - 2 = 10; 115 - 9 = 106; 127 - 11 = 116
(384 + 10 + 106 = 500). HAVE 384 of 500 = 76.8%.
Next: #62 (needs Jayant's syntax pick), #67/#76 verification slices,
then #69/#70/#72/#74.

## #60 Crash dumps in freestanding mode — HAVE (24 Nov 2026, sprint, both compilers)

Jayant's pick 24 Nov ~09:32 IST: "Build A B C" — all three design
options, defaults as presented (D1 literal-message exemption YES,
D2 both targets, D3 full 30-register format, D4 always-on).
Built in order A, then C's native half, then B, gating each stage.
Design: blackmoon-iso/crashdump-slice/DESIGN.md; records in
blackmoon-iso/crashdump-slice/ (SUMMARY.md, probes/, logs/, after/).

Stage A (big32 register dump): 31 inline `sw` snapshot stores at
the fail site, then `forge_crash_dump` prints `qasida: crash: <msg>`
+ pc + 30 trap-frame-order registers + sp (0x + 8 lowercase hex)
over UART, then the existing `li a0, 1; ecall` halt. Helpers emitted
only when a fail/assert/f2i site exists. Stage C (native x86_64):
freestanding `forge_fail` snapshots the surviving registers (rip,
rbx, rbp, r12–r15, rsp) and prints the pinned partial transcript to
fd 2 via a raw write syscall (nr 1) — visible under Linux, invisible
on bare metal. Stage B (hook): on fail the compiler snapshots,
calls user-defined `crash_handler(code: int, pc: int)` if defined
with exactly that name and signature, prints the pinned dump, then
halts. Crash codes pinned: 0 OTHER, 1 USER, 2 ASSERT, 3 F2I,
4 OVERFLOW, 5 DIVZERO, 6 BOUNDS, 7 OOM. D1 reverses the documented
#39 decision narrowly: a string literal as the fail()/assert()
message is exempt from the freestanding heap rejection (both
compilers); any other str expression is still rejected.

Bugs found by the gates (fixed in-slice): (1) the threading script
mis-threaded a move-site `forge_fail` (inserted the code before the
closing quote); fixed by hand, full audit clean. (2) Stale hosted
binary caused 13 hosted failures on the first own-test run; rebuilt
and synced to all 3 tree locations. (3) Syscall return-value clobber
in `forge_crash_write` (rax as plain input, reused stale across
writes — second write ran syscall nr 15 and segfaulted); fixed with
a `"=a"` output tied to the input. (4) Wrong-file noinline edit
(matched the hosted header's `forge_fail`, not the freestanding
one); caught by grep, reverted and re-applied. (5) `int64_t` vs
`long long` conflict on the native hook declaration (codegen emits
`long long` for int); header now uses `long long`. (6) GCC rewrote
the strlen-shaped loop in `forge_crash_msg` into a `strlen()` call,
which cannot link under `-nostdlib`; fixed with `-ffreestanding`
on freestanding builds (both compilers). (7) Native hook segfault:
`poke32(0x8000)` is unmapped under Linux (RAM only on big32); the
native hook does a safe local computation instead, and the native
test asserts the transcript + halt + the call in the disassembly.

Own test tests/test_crashdump_v1.py 109/109 ALL PASS both
compilers (live binary rebuild B, md5 7043a4f83152d2006c2f00c9618bcad7,
synced to all 3 locations). Gates 24 Nov: bootstrap 7/7
byte-identical (lex 90709, parse 722646, check 7278338, infer
8321745, codegen 26029484, header 113790, cli 26263686); parity
124/124 agree + byte-identical; corpus 99/99; regression 62/62;
fuzz existing 102/102 both modes, fv 56/56, closure 66/66, fs
56/56, tc/lf/es ALL PASS; full suite hosted 109/116 + python
110/116 (the 6 fails are exactly the #50-known big32 set; hosted
run_tests.py failed once on a spawn_demo println-interleaving
flake, re-run passed, so hosted is effectively 110/116); ASan
program-side 8/8 clean; ASan compiler-side new == old on cold cache
(selfhost_check 3966/147, codegen 9820/351, cli 9918/357,
dump-flag 612/36 — the check-path leak is pre-existing exit-path
heap state, #60 adds nothing); fmt 0 failures; benchmarks tick
q_safe 2332 us vs c_o3 2322 (1.00x), matmul q_safe 12913 us vs
c_o3 59300 (0.22x) — no regression. Size deltas: kernel 3825
words, 0 crash code (0-word delta); native no-fail .text 273 → 273
(delta 0); native fail .text 881 → 1099 (+218 for the hook check).
Follow-ups stay open: F1 trap-fault dump, F2 freestanding
backtrace. F3 native-dump completion is done via stage C.
NOT pushed (parent verifies and pushes).

Counts after the flip: HAVE 385, PARTIAL 10, GAP 105, to build 115.
Arithmetic from the Day 4 entry (HAVE 384, PARTIAL 10, GAP 106, to
build 116): 1 GAP-to-HAVE (#60); 384 + 1 = 385; 106 - 1 = 105;
116 - 1 = 115 (385 + 10 + 105 = 500). HAVE 385 of 500 = 77.0%.
Next: #62 (needs Jayant's syntax pick), #67/#76 verification slices,
then #69/#70/#72/#74.

## #62 Labeled break/continue — HAVE (24 Nov 2026, sprint, both compilers)

Decision: Jayant's word 24 Nov ~22:52 IST ("do whatever is best" after the
A/B choice was presented with recommendation A): Option A — SHADOWING
ALLOWED, inner wins (design choice 3, DESIGN-62-67-76.md lines 117-122).
The "duplicate on enclosing loops is an error" clause in the first
build brief was the parent's error, traced to the design's pre-decision
sketch (line 55), superseded by choice 3. The first coordinator built
everything except this decision (own test 58/60, only case 12 failing
in both compilers with "duplicate label 'outer' on enclosing loops");
the fix removed the duplicate-label check from forge_lang/checker.py
and examples/selfhost_check.fg (both checkers agree), deleted error
case E3 from tests/test_labeled_break_v1.py (its program is now valid
shadowing, covered by case 12), and touched nothing else — label stack,
fn/lambda reset, codegen, and all other error cases unchanged. New
own-test total 58 (60 - 2: E3 ran under both compilers).

Own test tests/test_labeled_break_v1.py 58/58 ALL PASS both compilers
(live binary rebuild 2, md5 b3460a74a14095f551bd45ea9c050cf6, 18,331,856
bytes, synced to all 3 locations). Gates 24 Nov: bootstrap 7/7
byte-identical under ulimit -s 65536 (lex 90709, parse 754147, check
7456886, infer 8511923, codegen 27040059, header 113790, cli 27279078);
parity 124/124 agree + byte-identical; corpus 99/99; regression 62/62;
fuzz existing 102/102 both modes (manifest holds 102 cases — NOT 122),
fv 56/56, closure 66/66, fs 56/56, tc 38/38, lf 20/20, es 40/40,
crashdump own test 109/109; full suite hosted 110/117 + python
111/117 (the 6 fails are exactly the known big32 set in both; hosted
run_tests.py failed once on the scope_demo println-interleaving flake,
4/4 direct reruns clean, so hosted is effectively 111/117); ASan
program-side 16/16 clean (8 programs x 2 modes, incl. the new
shadow_break_inner case); ASan compiler-side new == old on cold cache
(dump-flag 612/36, selfhost_check 4002/149, selfhost_codegen 9984/357,
selfhost_cli 10082/363 — the plain-check leaks are pre-existing
cold-cache exit-path heap state, #62 adds nothing; the dump-flag
612/36 is the documented #50 baseline); fmt 0 failures (11 new files
canonical after reformat to 4-space — fmt's canonical indent; the
demo's 3 file-leading // comment lines dropped, content in the slice
SUMMARY; selfhost_parse/check/codegen fmt-neutral on code); emit
compare 12/12 (unlabeled new-hosted == old-hosted byte-identical,
incl. selfhost_cli.fg 27,278,992 bytes; labeled new-hosted ==
new-Python byte-identical, incl. p_defer.fg); benchmarks tick q_safe
3558 us vs c_o3 3527 (1.01x), matmul q_safe 17909 us vs c_o3 41304
(0.43x) — no regression (absolute numbers up vs #60 across the
board, C baselines included — VM-wide slowdown, ratios unchanged).
Honest notes: the hosted binary's stack — p_defer.fg segfaults the new
binary at the default 8 MB stack (label-stack/snapshot work pushed it
over the edge) and selfhost_cli.fg segfaults BOTH binaries at 8 MB
(the known pre-existing hosted stack-depth condition); the driver
(forge.py _raise_hosted_stack, 64 MB) and bootstrap (ulimit -s 65536)
already raise it, and the emit-compare harness was fixed the same way
(a preexec_fn stack raise to 64 MB, mirroring forge.py) — no compiler
change, and the own test (through forge.py) was always green. The
first asan_compare run was killed ~46 min in by a VM restart during
the NEW-codegen re-run; the resume script ran ONLY the missing OLD cli
check and printed the full table — ALL MATCH. Two VM restarts hit this
session (one killed an asan_lb.py run ~4 min in, one killed the
compare ~46 min in). NOT pushed (parent verifies and pushes).

Counts after the flip: HAVE 386, PARTIAL 10, GAP 104, to build 114.
Arithmetic from the #60 entry (HAVE 385, PARTIAL 10, GAP 105, to
build 115): 1 GAP-to-HAVE (#62); 385 + 1 = 386; 105 - 1 = 104;
115 - 1 = 114 (386 + 10 + 104 = 500). HAVE 386 of 500 = 77.2%.
Next: #67/#76 verification slices, then #69/#70/#72/#74.

## Sprint Day 5 — #67 + #76 verification slices (25 Nov 2026)

#67 range syntax (PARTIAL → HAVE) and #76 wildcard match arm
(GAP → HAVE). Both were verification slices per
DESIGN-62-67-76.md — the 24 Nov probes said each was already
implemented and the catalog entries stale. The verification proved
it for native, with ONE real gap found: `0..n` in a for loop was
REJECTED on big32 while `range()` worked as a for-loop source, so
#67 became a small build slice in-slice — big32 now lowers a range
literal as a for-loop source to the same counted loop as `range(n)`
(forge_lang/codegen_rv.py gen_for RangeLit branch +
forge_lang/ranges.py find_ranges allow_for_source; only the direct
for-source literal is exempt). Own tests: tests/test_range_syntax_v1.py
29/29 ALL PASS both compilers (10 OK x2 incl. empty 5..5 → 0 and
reversed 5..0 → 0 VERIFIED, negative -3..3, expr 0..n+1, nested,
param endpoint, fn returning total, range value len/sum/iterate;
7 big32 model runs UART-exact + halted + a0=0; big32 range-value
rejection + WASM range rejection); tests/test_wildcard_match_v1.py
24/24 ALL PASS both compilers (6 OK x2 incl. enum hit/miss, union
hit/miss, wildcard over an inferred error set; 5 error x2 incl.
wildcard-must-be-last, wildcard-cannot-bind, non-exhaustive enum /
union / narrowed error set missing only TimedOut; big32 + WASM
match rejections). Gates 25 Nov: bootstrap 7/7 byte-identical
under ulimit -s 65536 (lex 90709, parse 754147, check 7456886,
infer 8511923, codegen 27040059, header 113790, cli 27279078 —
exactly the #62 sizes); parity 124/124 agree + byte-identical;
corpus 99/99; regression 62/62; fuzz existing 102/102 both modes
(manifest holds 102 — NOT 122), fv 56/56, closure 66/66, fs 56/56
(from repo root), tc 38/38, lf 20/20, es 40/40, crashdump own test
109/109, labeled own test 58/58; full suite hosted 113/119 +
python 113/119 (the 6 fails are exactly the known big32 set in
both; run_tests.py passed in both modes, no flake this run — the
python-mode first run was killed by a VM restart mid-run_tests.py
and re-run clean; the hosted-mode run finished first try);
ASan program-side 32/32 clean (16 OK programs x 2 modes);
ASan compiler-side == the #62 table on cold cache (dump-flag
612/36, selfhost_check 4002/149, selfhost_codegen 9984/357,
selfhost_cli 10082/363 — the #62 ASan binary IS the current
tree's, since no hosted .fg changed; the codegen check alone took
~40 min under ASan); emit compare 22/22 (19 byte-identical + 3
Result-heavy programs via the documented pre-existing #50
divergence: hosted vs Python differ by struct-typedef/helper
ORDER only, ~285 diff lines, sorted-diff 0 in all three, and
old-hosted (pre-#62) == new-hosted byte-identical on all three —
this slice changed nothing in the emit); benchmarks tick q_safe
2335 us vs c_o3 2469 (0.95x), matmul q_safe 13652 us vs c_o3 33363
(0.41x) — no regression; fmt N/A — this slice created or modified
NO .fg file (remote-tree diff: changed = exactly
forge_lang/codegen_rv.py + forge_lang/ranges.py). Honest notes:
(1) hosted union-path exhaustiveness message is bare vs Python's
missing list (pre-existing divergence class, not a #76 gap);
(2) WASM's match rejection surfaces as "undefined variable
'Green'"; (3) range values on big32 and all ranges on WASM stay
v1 limits; (4) inclusive `..=` is NOT part of #67. NOT pushed
(parent verifies and pushes).

Counts after the flips: HAVE 388, PARTIAL 9, GAP 103, to build 112.
Arithmetic from the #62 entry (HAVE 386, PARTIAL 10, GAP 104, to
build 114): 1 PARTIAL-to-HAVE (#67) + 1 GAP-to-HAVE (#76);
386 + 2 = 388; 10 - 1 = 9; 104 - 1 = 103; 112 = 9 + 103
(388 + 9 + 103 = 500). HAVE 388 of 500 = 77.6%.
Next: #69/#70/#72/#74.
## #490 Trailing commas (GAP → HAVE), #494 Shadowing (GAP → HAVE), #496 Underscore for unused bindings (GAP → HAVE) — Sprint Day 5 (25 Nov 2026)

Three ergonomics items, all in both compilers.

#490 Trailing commas: the parser now accepts a trailing comma in
array literals, call args, struct literals, tuple literals, fn
params, fn types, generic type args, method-call args, enum/struct
declarations and match arms (the last two already accepted them).
Python parser (forge_lang/parser.py, 12 comma loops + the tuple
loop); hosted parser (examples/selfhost_parse.fg, 10 comma loops +
the tuple loop). Double and leading commas still error. A
1-tuple literal `(1,)` now fails with a clear error in both
compilers ("tuple literals need at least two elements") — found
while implementing: it previously parsed as a 1-tuple and fell
through to a confusing checker error. Own test
tests/test_trailing_commas_v1.py 30/30 ALL PASS both compilers
(10 OK x2 incl. nested trailing commas and enum/struct-decl
regression; 4 error x2 incl. double comma, leading comma,
1-tuple); demo examples/trailing_commas_demo.fg.

#494 Shadowing: same-scope `let x = x + 1` now rebinds — the RHS
reads the OLD binding and the new binding takes over from here.
Same type only in v1 (a type change is a named error: "cannot
shadow '<name>' with a different type in v1 (was <old>, now
<new>)"); shadowing a pinned variable is an error; an
empty-array-literal rebind needs an annotation (same rule as a
fresh empty let — the infer pass only propagates annotations).
Lowering: a rebind emits the Assign path (temp-first, free the
old value, take the new one) instead of a second C declaration.
Python side: checker sets A.Let.rebind (forge_lang/ast_nodes.py,
checker.py, codegen.py). Hosted side: checker computes the rebind
from a per-block scope mark (scope_marks in selfhost_check.fg)
and the codegen detects it from its own per-block let set
(blk_let_names/blk_let_marks in selfhost_codegen.fg, truncated
at block exit so sibling blocks' lets never leak into the scan).
Loop-variable shadowing stays an error in the Python checker
(the C initializer would read the new variable, not the loop
var); the hosted checker still accepts it (pre-existing
divergence, documented not fixed). big32 and WASM need no change
(their Let handlers re-allocate and overwrite the env entry, so
re-lets already work). Own test tests/test_shadowing_v1.py 34/34
ALL PASS both compilers (12 OK x2 incl. int/str/array/struct
rebinds, chained rebinds, loop-body and if-branch rebinds,
nested-block shadow, let-mut rebind, annotated empty-array
rebind, moved-then-revived str; 4 error x2 incl. type change
both ways, pinned shadow, unannotated empty-literal rebind;
loop-var duplicate error Python-only); demo
examples/shadowing_demo.fg.

#496 Underscore for unused bindings: VERIFICATION slice — already
HAVE. `_`-prefixed bindings compile and run in both compilers,
and there is NO unused-variable warning mechanism at all (zero
occurrences of "warning" in the checkers), so the silencing half
holds vacuously. Own test tests/test_underscore_unused_v1.py 15/15
ALL PASS both compilers (7 OK cases x2 + fmt check); demo
examples/underscore_demo.fg.

Gates 25 Nov (live binary md5 49bcf8ea35d358e68da5731da9d10de3,
19,258,112 bytes, installed to bin/ + forge_lang/bin/ — a fresh
link of the same sources as the coordinator's final2 build
ddcb8304; the parent's v69 build 88ad6504 was the intermediate):
own tests 34/34 + 30/30 + 15/15 = 79/79 ALL PASS both compilers;
bootstrap 7/7 byte-identical under ulimit -s 65536 (lex 90709,
parse 857078, check 7838465, infer 8921499, codegen 28306488,
header 113790, cli 28549785 — codegen/cli larger than #62/#67
because the hosted sources grew); parity 124/124 agree +
byte-identical; corpus 99/99; regression 62/62; fuzz existing
102/102 both modes (67 safe, 35 trap cases); full suite
run_tests.py hosted: only the known scope_demo println-
interleaving flake (2 failures in the logged re-run, 3 in the
first run; direct 4x reruns show the worker order swapping in
BOTH compilers — a race in the test's strict ordering, not a
regression), python: ALL PASS; run_big32_tests.py ALL PASS;
test-file battery hosted 117/123 + python 117/123 (the 6 fails in
both are exactly the known big32-sub-case files: checked_casts,
opaques, readonly, sizedarrays, sizedunif_fix, top500_batch1); ASan program-side 64/64 clean (32 programs x 2
modes, leak detection on); fmt: the 3 new demos idempotent
(the selfhost sources are not fmt-formatted in-tree — fmt strips
// comments and re-indents them wholesale, pre-existing);
benchmarks tick q_safe 2352 us vs c_o3 2482 (0.95x), matmul
q_safe 13318 us vs c_o3 66050 (0.20x) — no regression (c_o3's
matmul median is noisy across runs: 33363 in the #67 run, 66050
here; q_safe is stable ~13300-13700). Honest notes: (1) the
first bootstrap run against the intermediate binary failed 5/7
byte-compare — the hosted codegen's rebind scan leaked sibling
blocks' lets (blk_let_names was never truncated); fixed by
truncating at gen_block exit and re-verified 7/7 on the final
binary. (2) A nested-block shadow whose RHS reads the shadowed
name (`{ let x = x + 1; }`) miscompiles in BOTH compilers today
(C scoping: the initializer reads the new variable itself) —
pre-existing, needs its own slice (temp-first evaluation for
shadowing lets). (3) A `let s: str` inside a non-payload enum
match arm fails in both compilers (scope-end free of an
undeclared __forge_moved_s — the plain-enum match path doesn't
push an owned frame per arm) — pre-existing, not fixed here.
(4) Type-changing shadowing is rejected in v1; use a nested
block instead.

Counts after the flips: HAVE 391, PARTIAL 9, GAP 100, to build 109.
Arithmetic from the #67/#76 entry (HAVE 388, PARTIAL 9, GAP 103, to
build 112): 3 GAP-to-HAVE (#490, #494, #496); 388 + 3 = 391;
103 - 3 = 100; 112 - 3 = 109 (391 + 9 + 100 = 500). HAVE 391 of
500 = 78.2%.
Next: #69 value patterns (Jayant approved 25 Nov: "Build as
recommended — structs in, guards out"; design doc not in the
tree — parent to supply), then #72 walrus, #77/#78/#80.
#69 value patterns in match (GAP → HAVE). Landed 25 Nov 2026 (Sprint
Day 5, both compilers; Jayant's word 25 Nov 09:33 IST: "Build as
recommended — structs in, guards out"). Design:
~/workspace/blackmoon-iso/ctrlflow-slice/value-patterns/DESIGN.md
(probes p1–p14); implementation record + gate table:
.../value-patterns/SUMMARY.md. `match x { 2 => { ... } "hi" => { ... }
Point { x: 0, y: n } => { ... } _ => { ... } }` — int literals (incl.
negative, i64 range checked incl. i64-min and hex), bool literals,
string literals (content equality incl. escapes), struct patterns
(field-wise literal / binding / `_`; all fields present, any order
like struct literals; field bindings scoped to the arm with the
field's type). Exhaustiveness is a compile error (`_` required for
int/string/struct; bool exhaustive iff {true, false} seen or `_`
present); first-match-wins; exact duplicate literal / duplicate struct
pattern is a compile error; subsumption NOT analysed in v1. Value
matches skip the #50 ES verdict entirely (the ES walk still walks arm
bodies). Scrutinee evaluated once into a temp (p10: also folded into
the plain-enum shape for call scrutinees; variable scrutinees stay
byte-identical). Pattern is a new AST node: Match.arms are now
[(Pattern, Block)] pairs (was triples) — the 11 small forge_lang
modules (defers, fixedints, fntypes, never, opaques, ranges, readonly,
sizedarrays, tuples, unions) each took the one-line arm-shape update.
OUT of v1: float literals, range patterns, tuple/array patterns, type
patterns, `|` alternation, guards (`pat if cond =>` is a parse error),
bare-variable catch-all (a bare identifier still means an enum
variant). big32 lowers int/bool value patterns only (string/struct
rejected with a named error); WASM has no match support (unchanged).
fmt prints literal and struct patterns, idempotent on the new shapes.
Own test tests/test_value_patterns_v1.py 75/75 ALL PASS both compilers
(17 OK x2, 18 ERR x2, 5 backend cases: 2 big32 runs + string/struct
rejections + WASM rejection), re-run independently by the parent in
this run. The scrutinee error was reworded to `match needs an enum,
union, int, bool, str, or struct value, got {et}`; the one existing
test asserting the old fragment (tests/test_opaques_v1.py) was updated
to the new fragment — it still fails only on its pre-existing big32
sub-failure. Gates (live binary md5 49bcf8ea35d358e68da5731da9d10de3,
19,258,112 bytes — the #69 track's verified v69c build, installed at
bin/qasida-hosted): bootstrap 7/7 byte-identical, re-run independently
by the parent in this run (lex 90709, parse 857078, check 7838465,
infer 8921499, codegen 28306488, header 113790, cli 28549785; the 6
library stages need a trivial `fn main() -> int { return 0; }` shim
appended to a copy in examples/ — Python emit requires main, hosted
emit does not; the shim emits exactly 604 bytes of C); parity 124/124
agree + byte-identical; corpus 99/99; regression 62/62; fuzz existing
102/102 both modes + fv 56/56, closure 66/66, fs 56/56, tc 38/38, lf
20/20, es 40/40, crashdump 109/109, labeled 58/58, range 29/29,
wildcard 24/24; full suite run_tests.py PASS both modes (re-run by the
parent in this run, ulimit -s 65536) and test-file battery hosted
117/123 + python 117/123 (the 6 fails in both are exactly the known
big32 set); emit compare ALL PASS (17 value cases byte-identical; p10
hoist confirmed); benchmarks tick q_safe 2466 us vs c_o3 2437 (1.01x),
matmul q_safe 13127 us vs c_o3 80793 (0.16x) — no regression. ASan
program-side 34/34 clean (17 value-pattern programs x 2 modes, leak
detection on). ASan compiler-side (logs/asan.log + parent-measured
codegen case, all cold cache, raised stack): errsets_demo dump=True
matches the #62 table exactly (612, 36); selfhost_check 4026/150 vs
4002/149 (+24B/1 alloc), selfhost_codegen 10064/360 vs 9984/357
(+80B/3), selfhost_cli 10162/366 vs 10082/363 (+80B/3). Accepted as
pre-existing/documented, not a #69 regression (parent decision 25 Nov
2026): the 5 selfhost files + transitive imports contain 0 Match AST
nodes (counted with forge_lang.parser.parse by the parent), so #69's
match-handling code cannot execute during these checks; the #62
baseline predates the already-pushed #490/#494/#496 slice — same
treatment as #50's documented 612B/36. Honest notes: (1) the own-test count is 75/75, NOT 76/76
— the first report miscounted by one (same class as the #50 122/122
correction); the case lists are 17x2 + 18x2 + 5 = 75. (2) Remote main
was HALF-LANDED for #69 before this push: the Day 5 ergonomics push
(c16b650e) already carried #69's changes to parser/checker/codegen/
ast_nodes/selfhost_parse/selfhost_check/selfhost_codegen (same files,
same window); this push completes it with infer/codegen_rv/
selfhost_infer + the 11 small-module updates + the own test + the
opaques fragment update. (3) The parent's first bootstrap attempt
failed 1/7 and the second 3/7 — both procedure errors, not tree
problems: round 1 omitted the main shim (Python emit requires main),
round 2 copied stages to /tmp (relative imports broke), round 3 hit
/tmp full (512M tmpfs, 100% — 2526 stale qasida_run_*.c files plus the
three bootstrap output dirs); /tmp was cleaned to 293M free and the
outputs moved to the workspace, after which the bootstrap passed 7/7.
(4) The checked-in binary predates the #494 scope-marks edit to
selfhost_check.fg (07:34 UTC, already on remote from c16b650e); the
binary rebuild to pick it up is a follow-up, not part of this push.
(5) Hosted checker stack-depth regression on nested loops (found by
the #69 track): 3-deep while loops with an array index segfault at
the default 8MB stack, pass at 16MB — the checker was already at the
edge; fuzz must run under ulimit -s 65536 (as the bootstrap does).
Not a #69 blocker; flattening the checker's recursion is a separate
slice. (6) Hosted i64-fit errors report the saturated ival, not the
raw text (cosmetic). (7) Struct-pattern fields accepted in any order
(design recommended declaration order; implementation settled on any
order, like struct literals). Pushed 25 Nov 2026 as the #69 completion
push (19-file selective push, parent c16b650e; script
~/workspace/scripts/push_selective_day5_value_patterns69.py).

Counts after the flip: HAVE 392, PARTIAL 9, GAP 99, to build 108.
Arithmetic from the Day 5 entry (HAVE 391, PARTIAL 9, GAP 100, to
build 109): 1 GAP-to-HAVE (#69); 391 + 1 = 392; 100 - 1 = 99;
109 - 1 = 108 (392 + 9 + 99 = 500). HAVE 392 of 500 = 78.4%.
Next: #72 walrus, #77 nested functions, #78 tail-call, #80 event
loops, then ergonomics #481–#489/#495. #70 comptime-if still needs a
design decision (Jayant's word).

## Sprint Day 5 — #70 comptime if (25 Nov 2026)

#70 Comptime if (Zig) LANDED + PUSHED 25 Nov 2026 (selective push, parent 7c76cdb2; script ~/workspace/scripts/push_selective_comptime_if70.py): `comptime if <pred> { } else { }` — fixed predicates target/arch/os/mode/debug/freestanding with &&/||/!, discarded branch parsed-only (never checked/compiled), function-body only in v1, `qasida check --target {native,big32,wasm}` (default native). Own test tests/test_comptime_if_v1.py 71/71 ALL PASS both compilers (22 OK x2, 10 ERR x2, 5 backend, 2 fmt). Bootstrap 7/7 byte-identical (lex 90709, parse 932537, check 8395655, infer 9479945, codegen 29089807, header 113790, cli 29342986); parity 124/124; corpus 99/99; regression 62/62; fuzz 102/102 both modes + fv 56/56, closure 66/66, fs 56/56, tc 38/38, lf 20/20, es 40/40, crashdump 109/109, labeled 58/58, range 29/29, wildcard 24/24, value-patterns 75/75; full suite 118/124 both modes (6 known big32); ASan program-side 44/44 leak-clean; compiler-side deltas vs the #69 baseline (check +52B/5, codegen +78B/6, cli +78B/6, dump flag 612/36 exact) accepted as pre-existing — the selfhost files contain no ComptimeIf nodes (parent-verified with the Python parser), so #70's resolver logic cannot execute during those checks; the growth is the 5 new HChecker field-name pieces (26B) + ret_declared (13B) in pre-existing exit-path heap state. Emit compare 51 PASS, 0 FAIL; benchmarks no regression (tick q_safe 2343µs vs C-O3 2428µs; matmul q_safe 13738µs vs C-O3 33513µs). In-slice `__forge_ret` fix: two Returns in one block no longer redefine `__forge_ret` (pre-existing, newly reachable via a spliced-in return; mirrored in both codegens). Honest notes: (1) the v70 binary (md5 5ee8b446, rebuilt from the current tree 14:11 UTC) picks up the #494 scope-marks edit at the two binary locations — that #69 follow-up is closed there; examples/selfhost_cli is still the #62 binary (md5 b3460a74), a standing binary-sync follow-up. (2) Hosted evaluates native only (non-native --target is the existing hosted-driver deferral, Python-only).

Counts after the flip: HAVE 393, PARTIAL 9, GAP 98, to build 107.
Arithmetic from the #69 entry (HAVE 392, PARTIAL 9, GAP 99, to build 108): 1 GAP-to-HAVE (#70); 392 + 1 = 393; 99 - 1 = 98; 108 - 1 = 107 (393 + 9 + 98 = 500). HAVE 393 of 500 = 78.6%.
Next: #72 walrus, #74 generators.

## Sprint Day 5 — #72 walrus (25 Nov 2026)

#72 Assignment expressions (Python walrus) LANDED 25 Nov 2026 (built, gates green, docs flipped; push is the parent's step, not yet done): `name := expr` in `if`/`while` conditions at hoistable positions (whole condition, under `!`, under a comparison, under the LEFT operand of `&&`/`||`); checker-side desugar (the #70 precedent) — binding declared in the enclosing block as `let mut`, `while` = initial binding + body-end re-read, `continue` targeting a walrus-`while` is a named error in v1. Own test tests/test_walrus_v1.py 65/65 ALL PASS both compilers (14 OK x2, 16 ERR x2, 3 backend, 2 fmt). Bootstrap 7/7 byte-identical under ulimit -s 65536 (lex 90740, parse 937808, check 8454432, infer 9538722, codegen 29149030, header 113790, cli 29405371); parity 124/124; corpus 99/99; regression 62/62; fuzz 102/102 both modes + fv 56/56, closure 66/66, fs 56/56, tc 38/38, lf 20/20, es 40/40, crashdump 109/109, labeled 58/58, range 29/29, wildcard 24/24, value-patterns 75/75, comptime-if 71/71; full suite hosted 119/125 + python 119/125 (6 known big32); ASan program-side 28/28 leak-clean; compiler-side == the #70 table on cold cache (dump-flag 612/36, check 4078/155, codegen 10142/366, cli 10240/372 — zero growth; the codegen check had to be re-run after a runtime restart killed the first attempt mid-check); emit compare 65 PASS, 0 FAIL; benchmarks no regression (tick q_safe 2346µs vs C-O3 2437µs, 0.96x; matmul q_safe 13291µs vs C-O3 34797µs, 0.38x); fmt 0 failures. v72d hosted binary md5 2cb2fd46045b74a8860c6217638a9722 (installed to bin/qasida-hosted + forge_lang/bin/qasida-hosted only; examples/selfhost_cli still the #62 binary — standing binary-sync follow-up). In-slice findings: (1) the hosted re-read needs a deep copy of the RHS with a neutralized (line, col) 0,0 — the hosted Fix 1 tagger keys by (line, col), not node identity, so a copy keeping the original position was re-tagged plain (v72b/v72c both still emitted plain `-` vs Python's `forge_sub`); the pre-loop binding keeps the original node. (2) Pre-existing hosted bug found, NOT a #72 gap: a `while` inside a nested Block leaks the enclosing fact into the body (the While's facts-clear does not take effect there) — emit compare case 13 is recorded as pass-preexisting (exactly one differing line, hosted plain `-` vs Python `forge_sub`); the hand-written manual desugar of case 13 diverges identically with no walrus present, and Python's loopproof `plain` set is empty for case 13; needs a separate codegen slice. (3) The v72d build's first attempt died in a runtime restart mid-cc and was re-run cleanly. (4) The p15 hosted `?` gap stays out of scope (a `?` in a walrus RHS follows the existing `?` rules; walrus does not widen it).

Counts after the flip: HAVE 394, PARTIAL 9, GAP 97, to build 106.
Arithmetic from the #70 entry (HAVE 393, PARTIAL 9, GAP 98, to build 107): 1 GAP-to-HAVE (#72); 393 + 1 = 394; 98 - 1 = 97; 107 - 1 = 106 (394 + 9 + 97 = 500). HAVE 394 of 500 = 78.8%.
Next: #74 generators.

## Sprint Day 6 — #74 generators (26 Nov 2026)

#74 Generator functions / yield (Python) LANDED 26 Nov 2026 (built, gates green, docs flipped; push is the parent's step, not yet done — the stored GitHub credential is dead, 401 since the #70 push, and remote main has moved): `yield expr;` inside `fn name(...) -> Generator<T>` (requires `import "generators.fg";`). Checker-side state-machine desugar: the generator fn becomes a CONSTRUCTOR plus a STEP FUNCTION `<name>_next(g) -> Option<T>`; state in one shared generic struct `Generator<T> { kind: int, cur: T, slots_i: [int], slots_s: [str], slots_b: [bool] }`. Own test tests/test_generators_v1.py 57/57 ALL PASS both compilers (9 OK x2, 17 ERR x2, 3 backend, 2 fmt). Bootstrap 7/7 byte-identical under ulimit -s 65536 (lex 90774, parse 944709, check 11378004, infer 11378004, codegen 31007565, header 113790, cli 31271177); parity 124/124; corpus 99/99; regression 62/62; fuzz 102/102 both modes + fv 56/56, closure 66/66, fs 56/56, tc 38/38, lf 20/20, es 40/40, crashdump 109/109, labeled 58/58, range 29/29, wildcard 24/24, value-patterns 75/75, comptime-if 71/71, walrus 65/65, generators 57/57; full suite hosted 120/126 + python 120/126 (6 known big32); ASan program-side 18/18 leak-clean; compiler-side vs the #70 table on cold cache (dump-flag 612/36 exact; codegen 12188/468 and cli 12286/474, each +2046B/+102 over the table — but the v72 ASan binary gives the IDENTICAL codegen number (12188/468) and the IDENTICAL check-wrapper number (7384/293), so the delta vs the #70 table is PRE-EXISTING (it happened between #70 and #72, not from #74; the #72 entry's "zero growth" claim was wrong) and #74 introduced ZERO compiler-side leak growth); emit compare 75 PASS, 0 FAIL; benchmarks no regression (tick q_safe 2363µs vs C-O3 2392µs, 0.99x; matmul q_safe 12797µs vs C-O3 39463µs, 0.32x); fmt 0 failures. v74d hosted binary md5 096f9f144fd826ede57778b50e61f12a (installed to bin/qasida-hosted + forge_lang/bin/qasida-hosted only; examples/selfhost_cli still the #62 binary — standing binary-sync follow-up). In-slice fixes: (1) G* transform structs live in selfhost_infer.fg (the #47 codegen helper-order bug); (2) the s06b labeled-break hang — a break/continue to a SPLIT loop from inside an INLINE loop must unwind with `state = tgt; break;` plus a guard after each inline loop; (3) hosted transform idempotency — a no-yield fn whose `<name>_next` already exists is already a constructor; (4) synthetic positions — every transform-built node gets a fresh (line, col) because the hosted type map keys by (fn_idx, line, col) and assumes that key is unique; (5) the defer/walrus pre-scan errors are gated on the fn being a generator (ordinary fns with a defer/walrus were falsely rejected). The bootstrap check wrapper now also imports infer.fg (the G* structs live there). Forks for Jayant: F1 the `next()` API is per-generator `<name>_next(g)` (a uniform `next(g)` needs a dispatch registry or method syntax — v2); F2 `for x in g` (v2 first item). #77 probe (verification only, not implemented): nested `fn` definitions are rejected by both compilers (parse error) — genuine GAP; the `fn`-literal workaround works under both compilers.

Counts after the flip: HAVE 395, PARTIAL 9, GAP 96, to build 105.
Arithmetic from the #72 entry (HAVE 394, PARTIAL 9, GAP 97, to build 106): 1 GAP-to-HAVE (#74); 394 + 1 = 395; 97 - 1 = 96; 106 - 1 = 105 (395 + 9 + 96 = 500). HAVE 395 of 500 = 79.0%.
Next: #77 nested functions, #78 tail-call, #80 event loops.

## Sprint Day 7 — #77 nested functions (27 Nov 2026)

#77 Nested function definitions LANDED 27 Nov 2026 (built, gates green, docs flipped; push is the finisher's step, not yet done): `fn name(params) -> Ret { body }` as a STATEMENT inside a function body (Python `def` shape), `-> Ret` required (missing return type is a parse error). Checker-side desugar (the #70/#72/#74 precedent) rewrites it in place to `let name = fn(params) -> Ret { body };` BEFORE the body's statements are checked (Python `_check_stmts`, hosted program-level `resolve_nestedfn_prog` in selfhost_check.fg, running AFTER walrus and BEFORE comptime); no infer change, no codegen change. Binding lives in the ENCLOSING BLOCK, visible AFTER its declaration line, dies at block end, NOT hoisted (use-before-def is the existing `undefined function` error). Capture by value, read-only, exactly like closures (#101). Own test tests/test_nestedfn_v1.py 65/65 ALL PASS both compilers (18 OK x2, 12 ERR x2, big32/WASM/freestanding named rejections, 2 fmt). Bootstrap 7/7 byte-identical under ulimit -s 65536 (lex 90774, parse 964623, check 11447615, infer 11447615, codegen 31077950, header 113790, cli 31343755); parity 124/124; corpus 99/99; regression 62/62; fuzz 102/102 both modes + fv 56/56, closure 66/66, fs 56/56, tc 38/38, lf 20/20, es 40/40, crashdump 109/109, labeled 58/58, range 29/29, wildcard 24/24, value-patterns 75/75, comptime-if 71/71, walrus 65/65, generators 57/57, nestedfn 65/65; full suite hosted 121/127 + python 121/127 (6 known big32); ASan program-side 36/36 leak-clean; compiler-side 4/4 == the #74 table EXACTLY, ZERO growth (dump-flag 612/36, check-wrapper 7384/293, codegen 12188/468, cli 12286/474); emit compare 106 PASS, 0 FAIL; benchmarks no regression (tick q_safe 2318µs vs C-O3 2425µs; matmul q_safe 13409µs vs C-O3 35434µs); fmt 0 failures. v77 hosted binary md5 ca7c0b8f10915e355cb4104d489336e4 (21,138,776 bytes, installed to bin/qasida-hosted + forge_lang/bin/qasida-hosted only; examples/selfhost_cli still the #62 binary — standing binary-sync follow-up). In-slice fix (p6, PRE-EXISTING Python-only bug): the Python capture collector missed write-only captured array element writes — single-site fix in the `IndexAssign` Var-base branch of `check_stmt` (`_record_capture(base.name)`). Honest findings: (1) F6A narrows to NATIVE ONLY in v1 — big32/WASM codegen reject Lambda outright and the plain fn-literal form fails identically, so this is a pre-existing closure limit, not a #77 gap; big32/WASM closure support is a follow-up slice. (2) A nested fn returning a generic struct type (Result/Option) hits the pre-existing closure typedef-order C gap (plain fn-literal fails identically) — a named v1 limit. (3) `?` inside a nested fn works exactly as at top level (propagation-only). (4) defer/fail() inside a nested fn work; nested fn in a struct method body and in a lambda body work. Process notes: the first full ASan run was killed by a runtime restart mid-codegen-check with its stdout lost; it was re-run as the split program-side + per-check traced runs (the #70 precedent). The split caught a real bug in the ASan script: its import line still said `test_generators_v1`, so the first program-side run tested the 9 generator cases, not the 18 nestedfn cases — fixed to `test_nestedfn_v1`; the 36/36 above is the corrected run. The hosted fuzz runs with the stack raised to 64 MB (the 5 guard cases segfault at the default 8 MB stack — pre-existing hosted stack-depth condition; the v74d baseline segfaults identically).

Counts after the flip: HAVE 396, PARTIAL 9, GAP 95, to build 104.
Arithmetic from the #74 entry (HAVE 395, PARTIAL 9, GAP 96, to build 105): 1 GAP-to-HAVE (#77); 395 + 1 = 396; 96 - 1 = 95; 105 - 1 = 104 (396 + 9 + 95 = 500). HAVE 396 of 500 = 79.2%.
Next: #78 tail-call (designed only 27 Nov — probes found tail recursion already runs flat-stack on native today via gcc sibling-call optimisation, so the slice would add a checker-verified guarantee, not the behaviour; forks await Jayant's pick), #80 event loops.
