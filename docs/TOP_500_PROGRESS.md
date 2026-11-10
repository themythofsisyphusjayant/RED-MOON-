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
