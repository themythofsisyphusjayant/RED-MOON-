# Top 500 features for Qasida

Borrowed from the major programming languages, ranked for Qasida's
direction: Go's niche (safe, simple, fast tools/CLIs/servers) with
Rust's lessons (no null, immutable by default), plus a freestanding
OS track on big32. Numbering is priority order: 1 matters most.

Status tags (checked against the tree on 31 Oct 2026):
[HAVE] already in the language or stdlib, [PARTIAL] a thin version
exists, [GAP] missing. The 500 are all adoptable; the short
"Deliberately NOT taking" list at the end is not counted in the 500.

## Deliberately NOT taking (not counted)
Null values; implicit numeric conversions; unchecked arithmetic by
default; a borrow checker as the memory model (the direction is a
future GC, not borrow checking); class inheritance hierarchies;
exceptions as the primary error path; dynamic typing; raw unchecked
pointers as the default (peek32/poke32 stay explicit and
freestanding-flavoured).

## 1. Types and safety (1-20)
1. Non-nullable types by default (Kotlin/Swift/Rust) — [HAVE] No null anywhere; keep it as the core safety bet.
2. Option with ? sugar (Rust/Swift) — [HAVE] Already core; extend ? to every call site shape.
3. Result with ? propagation (Rust) — [HAVE] Already core; add map/and_then/or_else combinators.
4. Exhaustive match on enums (Rust/Swift) — [HAVE] Already core; extend exhaustiveness to nested patterns.
5. Interfaces / traits without inheritance (Go/Rust) — [HAVE] Landed 31 Oct 2026 (batch 2, traits v1): trait declarations (signatures only), impl blocks with or without a trait, method-call syntax with static dispatch (Struct__method, receiver first); checker enforces trait conformance, receiver type, and duplicate methods. v1 limits: no generic traits/structs/methods, no trait objects, no generic bounds; big32 and WASM reject trait programs (they lack struct parameters/structs).
6. Type aliases (TypeScript/Go) — [HAVE] Landed 31 Oct 2026 (batch 3, v1): transparent `type Name = Target;` shorthands, expanded in the checker before any other checking, so they work for already-supported types on every backend (native + big32 kernel verified). Chains, arrays, concrete generic instantiations, struct/enum aliases, struct literals via bare-struct aliases, and fmt round-trip all verified. v1 limits: aliases take no type arguments, struct literals via generic/array aliases are not rewritten, bare-generic targets rejected.
7. Union types (TypeScript) — [HAVE] Landed 31 Oct 2026 (batch 5, v1): `int | str` holds exactly one member value, tagged by member index. Member values wrap into a union at assignment, argument, return, struct-field, and cast (via alias) sites; a union narrows only through match arms named by member type, which bind the narrowed value. Str payloads are deep-copied on wrap/copy and tag-freed on scope end, so sharing never double-frees. Native verified (full program + fmt round-trip); big32 and WASM reject union programs in v1 with named errors. v1 limits: members are the four scalars only; no struct/enum/array/generic members, no subset conversions, no arrays of unions, no == on unions (narrow first).
8. Opaque types (Swift/Rust impl Trait) — [HAVE] Landed 31 Oct 2026 (batch 6, v1): `opaque Trait` hides a concrete implementation behind its trait interface, in the existential reading: any value implementing the trait, mixing freely. At runtime the value is a tagged struct over the implementing structs (impl-block order); method calls, copies, and frees dispatch on the tag, with the callee getting an independently owned copy of the payload. Native verified (three implementations incl. a string-field one, dispatch + copy + param passing + fmt round-trip); big32 and WASM reject opaque programs in v1 with named errors. v1 limits: opaque types in returns, parameters, and let annotations only; no struct fields, no arrays of opaque values, no matching on opaque values (use the methods).
9. Fixed-width ints i8/i16/i32/i64/u8/u16/u32/u64 (Rust/C/Zig) — [HAVE] Landed 31 Oct 2026 (batch 7, v1): i8/i16/i32/u8/u16/u32/u64 as distinct scalars, i64 as a spelling for int (parser-normalised, never a parallel type). Literals adapt to an expected fixed type when they fit (range-checked at compile time, including negative literals, in let/argument/return/field and binary-operand positions); general int expressions do not adapt. Same-type arithmetic/comparison/bitwise only; shifts take an int count or the same width. Arithmetic is checked (widened, range-checked, narrowed; u64 via overflow builtins; division checks zero and signed-min / -1; shifts check the count; fast mode masks shift counts to the width). Casts between int types are free when widening, range-checked when narrowing. Native verified (boundary values for every width, struct fields, fmt round-trip); big32 and WASM reject fixed-width programs in v1 with named errors. v1 limits: no arrays of fixed widths; float↔fixed casts follow the existing truncating C-cast rule.
10. Explicit wrapping arithmetic (Rust/Zig) — [HAVE] Landed 31 Oct 2026 (batch 4): wrapping_add/sub/mul/neg builtins beside the checked default; they never fail. Native wraps via unsigned arithmetic; big32 and WASM wrap by nature (both verified, big32 kernel transcript included).
11. Distinct newtypes (Haskell/Rust) — [HAVE] Landed 31 Oct 2026 (batch 4, v1): `newtype UserId = int;` is its own type, never equal to int; values cross only via explicit casts to the newtype's own underlying type (chains resolve). Same-newtype equality allowed when the underlying type is comparable. Native + big32 verified (big32 kernel 42/DONE); WASM rejects newtype programs in v1 (its type mapping does not know newtypes yet). v1 limits: no arithmetic, ordering, field access, or indexing through a newtype (cast out first).
12. Compile-time sized arrays [T; N] (Rust) — [HAVE] Landed 31 Oct 2026 (batch 8, v1): `[T; N]` is a distinct type from `[T]`; a literal must hold exactly N elements (checked at compile time, including the empty-literal case), push is rejected, indexing/len/iteration work like dynamic arrays, and sized arrays work as function parameters, returns, and struct fields. Native verified; big32 and WASM reject sized programs in v1 with named errors. v1 representation is the existing heap array: the size is a type-level contract enforced at construction and preserved because only sized values flow into sized positions — a stack representation is a later slice. Sized arrays over fixed-width element types are rejected like dynamic fixed arrays. Nested sized literals unify at any depth (fix track, 2 Nov 2026: `[[1, 2], [3, 4]]` against `[[int; 2]; 2]`, including under a dynamic outer array).
13. Readonly collection views (TypeScript) — [HAVE] Landed 31 Oct 2026 (batch 9, v1): `readonly [T]` (and `readonly [T; N]`) is a handle through which an array can be read (index, len, iteration) but not written (push and index assignment rejected). A mutable array coerces to a readonly view of the same array kind (dynamic to dynamic, sized to the same sized type); a view never coerces back, and kinds never mix. Native verified (including aliasing: mutations through the original handle are visible through the view, and views as struct fields and function parameters); big32 and WASM reject readonly programs in v1 with named errors. v1 views are shallow (the restriction is on the handle, not the data; elements of a view of nested arrays are themselves mutable) and apply to array types only — deep immutability and readonly structs are later slices.
14. Never / bottom type (Rust/TypeScript) — [HAVE] Landed 31 Oct 2026 (batch 10, v1): `never` is the type of expressions that never produce a value (a call to a function declared `-> never`). It is the bottom type: a never value coerces to any expected type at let, assignment, argument, return, and field sites (codegen wraps it with a dummy of the expected C type, since the diverging call never returns). A never function must diverge (its body must contain a top-level diverging statement: fail, or a call to a never function, including inside a top-level statement's own expressions and conditions) and cannot return anywhere; a non-void function whose body contains a top-level diverger satisfies the return requirement. Native verified (including a diverging let, assignment, and return); big32 and WASM reject never programs in v1 with named errors. v1 limits: no loop-non-termination analysis (while true is not recognised as diverging); never values in other expression positions are rejected by their existing type checks.
15. Binary/octal literals and digit separators (Rust/C) — [HAVE] Landed 31 Oct 2026 (batch 1): 0b1010, 0o777, 1_000 and 0xFF_FF; bare prefixes and bad underscores are compile errors.
16. Local type inference (Go/Rust) — [HAVE] Landed 31 Oct 2026 (batch 13, v1): an empty array literal `let x = [];` infers its element type from a later constraining use in the same function — push value, assignment, annotated let, call argument, return value, struct field, or field assignment. The checker resolves the binding (rewriting its annotation, so the later infer pass sees an ordinary annotated let); conflicting constraints still fail with the normal type error, and a literal no use constrains fails at the end of the function with a clear "cannot infer the element type" message instead of a leaked '?'. v1 limits: flat empty literals only (nested empty literals are a separate pre-existing gap); generic-call arguments, method arguments, and generic-struct fields do not constrain; loop variables over not-yet-resolved arrays keep '?'.
17. Explicit checked casts (Rust) — [HAVE] Landed 31 Oct 2026 (batch 11, v1): float-to-int casts are checked in safe mode — a float outside the target range, or NaN or infinite, fails with "float to int cast out of range" (the upper bound is exclusive; max+1 is a power of two for every int width, so it is exactly representable as a double). Covers plain int and all fixed widths; truncation toward zero is unchanged for in-range values. Fast mode keeps the plain truncating C cast. WASM already traps on out-of-range float-to-int conversion and big32 rejects float casts outright, so neither backend changes in this batch. int-to-float precision loss is inherent to float64 and is not an error.
18. First-class ranges (Swift/Kotlin) — [HAVE] Landed 31 Oct 2026 (batch 14, v1): half-open ranges `a..b` as values of type `range`, lazy (start/end only, nothing materialized). Methods len, contains, start, end, sum — all O(1); sum uses the arithmetic-series formula in __int128 and fails in safe mode when the result does not fit in int, and len fails the same way for the full int64 span. Ranges flow through let, parameters, returns, and struct fields, and `for x in r` iterates them directly. big32 and WASM reject range programs in v1 with named errors. v1 limits: half-open only (no `..=` inclusive form); no range equality or printing; no indexing into a range.
19. Tuple types (Python/Rust/Go) — [HAVE] Landed 31 Oct 2026 (batch 12, v1): `(T1, T2, ...)` with at least two elements; values `(v1, v2, ...)` read as `t.0`, `t.1`, ... . Tuples are owned values (str elements copied, array elements refcounted, nested struct/tuple elements made independent) flowing through let, assignment (temp-first), arguments, returns, and struct fields. Native verified (including nested tuples, tuples of structs and arrays, shared-tuple copies, and struct fields of tuple type); big32 and WASM reject tuple programs in v1 with named errors. v1 limits: no 1-tuples, no unit `()` value, no destructuring, no tuple equality or printing. Side fix in the same batch: composite C structs (structs, tuples, opaques) are now emitted in dependency order, so forward struct references (A has a B field, B defined later) compile, and a cyclic value definition fails with a clear error instead of a C error. Lexer fix: a number right after a dot lexes as a tuple index, so `t.0.0` parses as chained indices instead of a float.
20. Void/unit consistency (Rust) — [HAVE] Landed 31 Oct 2026 (batch 15, v1): void is no value — it is allowed only as a function or method return type. The checker now rejects void everywhere else with a clear message instead of broken C downstream: binding a void call or method result, struct fields, enum payloads, array/tuple elements, generic arguments, aliases, newtype targets, parameters, and cast targets. The standing rules stay: a void function is called as a statement, and its return takes no expression (`return f();` in a void function is still rejected — write the call, then a bare return).

## 2. Memory and lifetimes (21-40)
21. Garbage collector with pause control (Go/Java) — [GAP] The stated future direction; keep it away from borrow checking.
22. Allocator as a value (Zig) — [HAVE] Landed 31 Oct 2026 (batch 17, v1): forge_lang/stdlib/allocator.fg, pure Qasida with no compiler change — the language support (structs by value, tuple returns, array fields) already exists. One Allocator struct, passed explicitly to functions, never a global, in three kinds over a fixed backing array: bump (next++, free is a no-op), freelist (intrusive free list, freed slots reused first), arena (bump + reset). allocator_alloc returns (-1, a) when full — out-of-memory is a value, not a failure. Single-slot allocation only in v1; contiguous multi-slot blocks and double-free detection are named later slices.
23. defer for scope-exit cleanup (Go/Zig) — [HAVE] Landed 31 Oct 2026 (batch 16, v1): `defer call();` runs at the enclosing block's exit, LIFO within the block — including early returns, breaks, and continues, and loop-body defers run each iteration. Deferred calls are emitted as statements at the exit point, so their arguments evaluate at exit time in v1 (documented). big32 and WASM reject defer programs in v1 with a named error.
24. Arena allocation (Zig/Rust) — [HAVE] Landed 31 Oct 2026 (batch 18, v1): forge_lang/stdlib/arena.fg, pure Qasida. A growing region for temporary allocations, distinct from #22's fixed pools: the backing array grows by push on demand, so alloc never fails with -1; individual frees are no-ops; the whole region is reclaimed by reset, or rewound to a checkpoint by mark/restore — the phase pattern (mark, allocate freely, restore) frees a phase's temporaries at once. Single-slot allocation only in v1. This batch also fixed two real compiler ownership bugs the arena exposed: push on a shared array now copies-on-write instead of reallocating the shared buffer (which left other holders dangling), and field assignment now mirrors plain assignment's ownership (temp-first, own the new value, free the old) for array and struct fields. Follow-up 5 Nov 2026 (fix track): the per-struct forge_<T>_push helper had the same missing-CoW shape the scalar helpers were fixed for — it realloced a shared buffer in place, double-freeing on a two-sided push; it now detaches first with struct_own_code copies of the slots, so struct arrays match the scalar behaviour (the inline nested-array push path was fixed the same way 2 Nov 2026).
25. Reference counting (Swift) — [HAVE] Landed 1 Nov 2026 (batch 19, v1): a `refcount(arr)` builtin that reads an array's live holder count without gaining a holder, plus forge_lang/stdlib/rc.fg — Rc as shared ownership over an array (clone gains a holder, dropping one loses one, the last drop frees; mutation through any holder is visible to all). Counts verified by hand: 1 after rc_new, 2 after rc_clone, shared mutation visible (99), len 2. Native-only in v1; big32 and WASM reject refcount programs.
26. Weak references (Swift/Java) — [HAVE] Landed 1 Nov 2026 (batch 20, v1): runtime weak table for [int] arrays — weak_new registers without gaining a holder, weak_upgrade returns (alive, array) with the current buffer while any strong holder lives (push syncs the moved buffer; copy-on-write push correctly leaves the weak on the original), (false, []) after the last strong holder's scope ends. Native-only in v1; big32 and WASM reject weak programs. V1 limit: the table itself is never freed (one entry per weak_new, no user data).
27. Move semantics (Rust/C++) — [HAVE] Landed 1 Nov 2026 (batch 21, v1); extended 4 Nov 2026 (pipeline, v2): move(a) transfers the one hold instead of copying — the destination's refcount stays 1 and the source is dead afterwards (any later use is a checker error). Fresh + forget in the native codegen: the move is fresh for arrays, str, structs and tuples, and the source's owned entry is forgotten so scope-end frees skip it. V2: moves in branches and loops work via a runtime moved flag per owned variable (the checker joins moved sets over branches/arms/loops, so a use after a conditional move is still a checker error until reassignment revives the variable; a second move in a loop fails at runtime instead of transferring a freed buffer), and field moves work in straight-line code (move(s.field) transfers that field; sibling fields stay usable, the whole struct and the moved field do not, assigning the field revives it, and a struct with a moved field skips its drop hook at scope end). V2 limits: field moves in branches/loops are rejected (they need per-field runtime flags), moves of for-loop variables are rejected (borrowed views — copy into a let first), and match-arm moves of a binding are the only branch moves whose source is not ownership-tracked. Native-only; big32 and WASM reject move programs.
28. Copy-on-write arrays (Swift) — [PARTIAL] Landed 1 Nov 2026 (batch 22, v1, opt-in): forge_lang/stdlib/cow.fg, pure Qasida — a Cow shares its buffer until a write (the writer gets a private copy when shared, writes in place when sole; the sharing test uses refcount before any local copy, since a local copy would inflate the count). Plain arrays keep their specified shared-mutation behavior. What remains (NOT taken): language-default CoW, where every index assignment CoWs — that would break Rc's shared-mutation promise and existing shared-mutation programs, so it needs an explicit decision.
29. Stack-allocated slices (Go/Rust) — [HAVE] Landed 1 Nov 2026 (batch 23, v1): forge_lang/stdlib/slice.fg, pure Qasida — a Slice is a stack-allocated header {arr, off, len} over an existing array's buffer: no new allocation, the slice keeps the buffer alive, reads and writes go through the shared buffer (visible via the original), bounds are the slice's own, and slicing a slice composes. V1 is [int]-only; str slices need a str-view type.
30. Lifetime-ordered placement (QAIRT) — [HAVE] Landed 1 Nov 2026 (batch 24, v1): forge_lang/stdlib/lifetime.fg, pure Qasida — this promotes the kernel's lifetime-ordered allocator to a stdlib API. One backing array, two regions: shorts bump from the front, longs from the back; one reset frees all shorts while longs survive untouched; out-of-memory is a value (-1). Fixed backing, two lifetime classes in v1.
31. Memory-mapped files (Python/C) — [HAVE] Landed 1 Nov 2026 (batch 25, v1): runtime mmap table + mmap_open/mmap_get/mmap_set/mmap_close builtins (bytes, native only, POSIX; Windows stubs fail cleanly). Writes go through MAP_SHARED into the file itself (proven: 'H' -> 'J' in the mapping re-reads as 'J' from the file). This batch also fixed two real pre-existing leaks its demo exposed: read_bytes results were not marked fresh (every let of one leaked a ref) and write_bytes never consumed its param hold (every call leaked its input array). Known follow-up, not hidden: other C helpers taking str/array params have the same unconsumed-param shape — an audit item, not fixed here. Extended 5 Nov 2026 (fix track): mmap_grow extends the file with ftruncate and remaps it under the same id (returns the new length; grow-only, a smaller or equal size fails with a named error), and mmap_get32/mmap_set32 read and write a 32-bit little-endian word at a byte offset (zero-extended, like peek32; a word crossing the end fails with "mmap index out of bounds"). Native only; big32 and WASM still reject mmap programs with a named error.
32. Allocator-aware collections (C++/Zig) — [PARTIAL] Arrays take an allocator argument (AVec over the #22 Allocator: bump vs freelist growth is observable; OOM is a value). Maps are the next slice — their string keys cannot live in an [int]-backed allocator.
33. Destructor hooks (C++/Rust Drop) — [HAVE] Landed 1 Nov 2026 (batch 27, v1): a struct method named `drop` (receiver only, void return) runs automatically when an owned binding dies — block end, function end, return path, break — firing before the free so fields are still live, via an independently owned copy (the call-arg pattern). The drop method's own receiver parameter never hooks (that would recurse forever — caught by the first demo run). V1 limits: per-binding, not per-value (copies drop per binding; use move() for exactly one drop); nested drops (struct fields, array elements) do not run; union/opaque-field structs are not hooked (owning gap); generics skipped; native only (big32/WASM/freestanding reject).
34. Pinning / immovable values (Rust) — [HAVE] Landed 6 Nov 2026 (pipeline, v1): pin(x); marks an owned binding immovable for the rest of its scope — any whole-value use (let, call argument, return, println, condition), move(x), move of one of its fields, reassignment, or push is a checker error; in-place field/index writes, scalar field and element reads (including through owned fields, e.g. b.vals[0]), len/refcount, and for-iteration still work (they move or copy nothing). Pinning joins path-sensitively over branches, loops, and match arms (pinned on any path counts after the join), like move v2; a fresh let shadowing a pinned binding is unpinned. Pinning is compile-time only: native codegen emits nothing for the statement. Native-only; big32 and WASM reject pin programs. V1 limits: pin needs a variable (not a field); pinning a struct with a drop method is rejected (the scope-end drop hook copies the value); indexing a pinned string is rejected (it materializes a new str); pinning a same-named inner binding inside a branch also pins the outer after the join (name-keyed joins, as in move v2).
35. Zeroing on free (Zig) — [HAVE] Landed 6 Nov 2026 (v1, default-on): every heap buffer the native runtime frees is zeroed (memset to 0) before free() — arrays of every element type (int/float/bool/str, nested, struct arrays), strs, the read_bytes temp buffer, the HTTP recv buffer, and spawn thread args. No new syntax and no opt-out in v1: the catalog calls this a security default, and it matches the language's safe-by-default stance. Cost: one memset per free. Verified by tests/test_zero_free_v1.py ALL PASS (demo, 12 run cases, emitted-C memset-before-free assertions at every site, and a C probe built from the actual emitted preamble reading all zeros after a sole-holder free — and NOT zeroing a shared buffer on a refcount dec); demo ASan-clean; full suite PASS. V1 limits: native only — big32/WASM free paths untouched (no syntax to gate, so programs there simply do not get zeroing yet); mmap is munmap, not free; no opt-out (later slice). Probe note: glibc free() writes freelist metadata into the first 16 bytes of a freed chunk, so the probe only observes bytes past 16.
36. Allocation failure as a value (Rust) — [HAVE] Out-of-memory becomes a Result, not a crash. DONE 7 Nov 2026: new builtin try_alloc(n: int) -> Result<[int], str> (native-only v1): Ok with a zero-initialised [int] via calloc, Err("out of memory") when calloc returns NULL (verified with try_alloc(2^60)), Err("bad size") for n < 0, Ok empty for n == 0. Works with `?` propagation. Requires import "result.fg" (the Result struct lives there); checker registers the Result<[int], str> instantiation so codegen emits it. big32/WASM reject it with a named error; freestanding rejects it. v1 limits: [int] only (no other element types, no fallible implicit allocations); the tiny bookkeeping mallocs (refcount, error-string copy) can still forge_fail if the system is truly out of memory — only the big calloc is fallible. ASan cannot test a 2^63-byte calloc (its own maximum-size abort), so the huge path is verified by the non-ASan run.
37. Pool allocators (C) — [HAVE] Fixed-size object pools for drivers.
Landed 7 Nov 2026 (pipeline, v1): forge_lang/stdlib/pool.fg, pure
Qasida, no compiler change. One pool serves one fixed object size
(an int slot in v1): the capacity is fixed at creation and the pool
never grows, so alloc is O(1) and out-of-memory is a value (-1),
never a crash. The free list is a separate stack (free_stack), NOT
intrusive — a freed slot's value is never clobbered by a
next-pointer, unlike #22's freelist. An occupancy bitmap (used)
makes double-free and use-after-free detectable: pool_free /
pool_set / pool_get on a free or out-of-range slot return false
and leave the pool unchanged. Freed slots are zeroed, so a reused
slot never leaks the old object's value. API: pool_new(cap) ->
Pool, pool_alloc(p) -> (int, Pool) (slot or -1 when full),
pool_free(p, slot) -> (bool, Pool), pool_get(p, slot) ->
(bool, int), pool_set(p, slot, val) -> (bool, Pool),
pool_used / pool_cap / pool_free_count / pool_full, pool_reset
(all slots free, values zeroed). Verified by
tests/test_pool_v1.py ALL PASS (18 checks: demo, alloc order,
full -1, double-free, LIFO reuse, reset, cap 0/negative, cap 1,
bad slots, neighbours, set-on-free; fmt idempotent; ASan clean).
Native-only in v1: big32 and WASM reject pool programs with the
named "tuples are not supported" error. V1 limits: [int] slots
only (no other object types, no multi-slot objects); no
pool-to-pool sharing; the pool is a value — copies share the
backing arrays, so always rebind the returned Pool (the
arena/allocator pattern).
38. Stack-usage diagnostics (Rust) — [HAVE] `qasida stack <file.fg>`
reports the max stack frame size per Qasida function, measured
from the real C compiler (`cc -fstack-usage` at -O0, so no
function is inlined away), with a warning when a frame exceeds
the 2048-byte kernel frame budget (default limit, `--limit N`
overrides it). Generic instantiations report under their base
name with the mangled C symbol shown (identity_int), methods as
Struct::method (Point__sum), freestanding main as main
(qasida_main), and functions the C compiler never emits (an
uninstantiated generic, an extern) as "not emitted". Runtime
helpers (forge_*) are summarized, not listed. Qasida arrays and
strings are heap-backed, so frames stay small by default: a
300-int local adds ~24 bytes to the frame, while 300 int locals
make a 2432-byte frame and trip the warning.
Landed 8 Nov 2026 (pipeline, v1): forge_lang/stackusage.py +
cli.py `stack` subcommand + examples/stackusage_demo.fg.
Verified by tests/test_stackusage_v1.py ALL PASS (14 checks:
demo 90, small frames with no warning, frame table parses with
max naming the largest, big frame warns over 2048 with max
many_locals, big-frame program runs 44852, --limit 0 warns on
every frame, --limit 100000 silences it, generic label,
method label, freestanding label, not-emitted label, missing
file errors, checker error fails, fmt idempotent; ASan clean).
Native only in v1: stack frames are a C-backend concept, so
there is no --target flag; big32/WASM have no C to measure.
V1 limits: frames measured at -O0 (an upper bound — optimized
builds may inline and shrink frames); per-function frames only,
not call-chain worst-case depth; the report warns, it never
fails the build.
39. No implicit heap allocation in freestanding mode (Zig) — [HAVE] The
rule is enforced at compile time, in the checker, with a named
error for the first heap value: any expression whose type is
heap-backed — str, any array (dynamic, sized, readonly view), a
struct, enum, or tuple carrying one, transitively — is rejected
("string literal allocates on the heap", "variable 's' has
heap-backed type 'str'", ...), and push() is rejected outright
(it reallocates the heap buffer). The same checker runs for
big32 (compile_file_rv), so the rule holds there too. Plain
structs are stack values: a program using only int fields builds
and runs freestanding, and its emitted C contains no malloc,
free, or memset — the per-struct heap-array helpers
(forge_<T>_array_free/get/set/push) are not emitted in
freestanding mode. The old codegen gen_expr guard stays as a
backstop.
Landed 9 Nov 2026 (pipeline, v1): forge_lang/checker.py
(_heap_backed + check_expr wrapper + push rejection) +
forge_lang/codegen.py (skip per-struct array helpers when
freestanding) + examples/noheap_demo.fg.
Verified by tests/test_noheap_freestanding_v1.py ALL PASS (40
checks: 12 named rejections, 7 freestanding programs build and
run incl. the demo exiting 42, emit has no malloc/free/memset/
array_free, big32 builds to .hex and rejects a string literal,
hosted controls, fmt idempotent; ASan clean). Full suite PASS
(log forge_suite_noheap_10321-6909.log).
V1 limits: declarations that merely name a heap type (an unused
str parameter, a struct field or enum payload of type str, never
given a value) still declare — they generate no heap code, and
any value of such a type is rejected at first use. Sized arrays
stay rejected (their literals malloc in codegen). fail() and
assert() with a string message stay rejected, as before (the
message is a string literal).
40. Use-after-move checking (Rust) — [HAVE] Landed 10 Nov 2026
(pipeline, v1): checker-level only, no borrow checker. Move
semantics (#27 v2) already rejected the direct uses, but five
holes stayed open, each confirmed as a real heap-use-after-free
under AddressSanitizer before the fix: push(a, v) and a[i] = v
through a moved array (those paths only looked the target up,
never checked it); a whole-value use of an intermediate struct
path after a nested field move (let x = o.inner after
move(o.inner.vals)); a while condition that reads a value the
body moves (re-evaluated after the body frees the moved-to
binding); and moving a for loop's iterable inside its body (the
next iteration reads the freed buffer, even if the body
reassigns the variable afterwards — the loop still holds the old
buffer). The fix is checker-only (forge_lang/checker.py):
moved checks on the push/index-assign variable targets, a
descendant-moved-field check on outermost field accesses,
a re-check of the while condition against the post-body moved
set (reassignment in the body revives, so the post-body set is
exactly what is dead at the next evaluation), and a
for-iterable stack consulted by move() (scope-aware, so moving
a shadowing inner binding of the same name stays allowed).
One real bug found by the new tests and fixed in the same run:
assigning a whole intermediate struct (o.inner = ...) did not
revive a moved field under it (FieldAssign discarded only the
exact target path); it now discards descendant paths too.
Verified by tests/test_useaftermove_v1.py ALL PASS (demo, 11
run cases, 14 rejection cases, big32/WASM named rejections,
fmt idempotent; ASan clean). Full suite PASS (sole failure the
known scope_demo println-interleaving flake, 4/4 clean on
direct rerun; log forge_suite_useaftermove_10671.log).
V1 limits: field moves in branches/loops are still rejected
by the v2 rule before the iterable check runs, so a field move
of a for iterable reports that earlier message; match-arm
moves of a binding are still the one branch move whose source
is not ownership-tracked (see #27).

## 3. Errors (41-60)
41. Error values as the default path (Go/Rust) — [HAVE] Result already is; never add exceptions as the main path.
42. Error wrapping with context (Go/Rust anyhow) — [HAVE] Landed 21 Nov 2026 (sprint batch 2): errwrap.fg + errwrap_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: contexts are plain strings, not typed error values; no cause chain across Result types. "while reading X: ..." chains.
43. Multi-error accumulation (Rust/Go validators) — [HAVE] Landed 21 Nov 2026 (sprint batch 2): multierr.fg + multierr_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: error strings only, no typed/field errors (see #53 valerr.fg for field-level lists). Collect every error, not just the first.
44. Panic vs recover boundary (Go) — [GAP] fail() stays fatal; recovery only at task boundaries.
45. Assertions with messages (all) — [HAVE] assert exists; add assert_eq-style diffs.
46. Error codes as enums (C/Zig) — [GAP] Typed errno-style errors for syscalls.
47. Backtraces on fail in debug builds (Rust) — [GAP] Native backtrace, stripped in release builds.
48. try/catch as opt-in only (Java/C++) — [GAP] Deliberately narrow: module boundaries only, never control flow.
49. Result combinators: map/flatMap/orElse (Rust) — [HAVE] Landed 21 Nov 2026 (sprint batch 2): resultx.fg + resultx_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: Result<int, str> only, named transforms (map_add/map_mul/map_err/or_else) — a general map(f) needs closures (#101). Chain Results without nesting.
50. Inferred error sets (Zig) — [GAP] The checker works out which errors a function can return.
51. Deferred error logging (Go) — [GAP] Log-on-return helpers.
52. Timeout errors as values (Go) — [GAP] Deadline-exceeded is data, not a crash.
53. Validation error types (Python pydantic) — [HAVE] Landed 21 Nov 2026 (sprint batch 2): valerr.fg + valerr_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: (field, message) pairs only; no schema-driven validation (see #233). Field-level error lists.
54. Structured error rendering (Rust miette) — [GAP] Snippets and labels in diagnostics.
55. Fail-fast vs collect mode (Rust) — [GAP] A per-call choice of error strategy.
56. Documented errors in signatures (Java checked, softened) — [GAP] Doc-level only, not enforced.
57. Sentinel errors (Go io.EOF) — [GAP] Named EOF/timeout sentinels.
58. Error translation layers (hexagonal) — [GAP] Map driver errors to domain errors.
59. Retryable vs fatal classification (AWS SDKs) — [GAP] For the retry-backoff library that already exists.
60. Crash dumps in freestanding mode (Zig) — [GAP] Register dump on fail in kernels.

## 4. Control flow (61-80)
61. continue (C family) — [HAVE] Landed 31 Oct 2026 (batch 1): mirrors break on native, big32 (with a for-continue label so the increment still runs), WASM and the formatter; rejected outside loops.
62. Labeled break/continue (Java/Rust/Go) — [GAP] Escape nested loops cleanly.
63. if-let / while-let (Rust/Swift) — [GAP] Unwrap an Option inside a condition.
64. guard statements (Swift) — [GAP] Early return without nesting.
65. Match guards (Swift/Rust) — [PARTIAL] match exists; add conditions on arms.
66. for-each over any iterable (all) — [PARTIAL] for over ranges and arrays exists; extend to maps, sets and generators.
67. Range syntax in for loops (Rust/Kotlin) — [PARTIAL] The range builtin exists; add 0..n syntax.
68. repeat-while loops (C/Swift) — [GAP] Run once, then check.
69. Value patterns in match (Scala) — [GAP] Match ints, strings and structs, not just enums.
70. Comptime if (Zig) — [GAP] Conditional compilation by target.
71. if as an expression (Rust) — [GAP] if returns a value.
72. Assignment expressions (Python walrus) — [GAP] Bind a value inside a condition.
73. Loop else (Python) — [GAP] An else that runs when a loop is not broken out of.
74. Generator functions / yield (Python) — [GAP] Lazy sequences.
75. Iterator protocol (Go/Rust) — [HAVE] Landed 21 Nov 2026 (sprint batch 7): iter.fg + iter_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). A standard way to walk collections: has_next / current / next, sum / take / skip / count over [int]. v1 limits: int arrays only; no map/filter (needs function values, item 103, still GAP).
76. Wildcard match arm (Rust _) — [GAP] A default arm for match.
77. Nested function definitions (Python) — [GAP] Helpers scoped inside functions.
78. Tail-call guarantee (Scheme/Erlang) — [GAP] Recursion without stack growth for state machines.
79. State-machine syntax (Erlang/Rust) — [HAVE] Landed 21 Nov 2026 (sprint batch 7): fsm.fg + fsm_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). Explicit states and transitions for drivers: transition table, step() on first match, can(); unmatched events stay put. v1 limits: no entry/exit actions, no hierarchical states.
80. Single-threaded event loops (Node) — [GAP] A loop shape for servers without threads.

## 5. Systems and OS primitives (81-100)
81. Inline assembly blocks (Rust/Zig) — [GAP] asm! for drivers beyond poke32.
82. Volatile 8/16/64-bit access (C/Zig) — [HAVE] peek32/poke32 exist; extend the widths plus volatile memcpy.
83. Memory barriers / fences (C11/Zig) — [GAP] fence() for devices and multicore.
84. Named interrupt handlers (C/Zig) — [PARTIAL] trap_handler exists; add per-source IRQ registration.
85. Supervisor-mode CSRs (RISC-V) — [PARTIAL] CSR builtins exist; cover s-mode once SBI hands over.
86. Page-table helpers (Zig/OSDev) — [GAP] Map, unmap and protect pages.
87. DMA descriptors (C drivers) — [GAP] A safe DMA buffer API.
88. Device-tree parsing (Linux) — [GAP] Read the DTB the firmware already passes in.
89. Sleep with deadlines (all) — [PARTIAL] sleep ecall exists; add sleep_until and timeout primitives.
90. Scheduler policies as libraries (Linux) — [HAVE] Landed 21 Nov 2026 (sprint batch 7): schedpol.fg + schedpol_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). Round-robin exists; this adds priority, EDF and lottery picks over [Task] (ties to the first task; empty list returns -1; lottery is a seeded LCG, seed below 8,000,000,000). v1 limits: picking only — no preemption, no time slices.
91. Typed IPC channels (Unix) — [PARTIAL] A ring IPC kernel exists; raise it to language channels.
92. Signals / software interrupts (Unix) — [GAP] Kill and notify tasks.
93. Capability handles (seL4) — [GAP] Unforgeable handles for devices and files.
94. Full SBI call set (RISC-V) — [PARTIAL] The SBI demo exists; finish with the a6-carrying call after ecall3.
95. ELF loading (Unix) — [HAVE] Landed 21 Nov 2026 (sprint batch 7): elf.fg + elf_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). Load programs from the filesystem: ELF64 header parsing over [int] bytes (magic, class, data, type, machine, entry); out-of-range reads return 0/false, never a trap. v1 limits: header only — no section or program headers, no loading (that is the OS track's job); big-endian files report their data byte but multi-byte fields are not decoded.
96. Syscall table definition (Linux) — [GAP] A numbered syscall ABI for the OS.
97. Driver probe/remove lifecycle (Linux) — [GAP] Device setup and teardown.
98. Power management hooks (Linux) — [GAP] Sleep and wake for devices.
99. Watchdog timers (embedded) — [GAP] Hang detection.
100. Panic handler with register dump (Rust embedded) — [GAP] Freestanding crash output.

## 6. Functions and abstraction (101-120)
101. Closures / lambdas (all) — [GAP] The biggest abstraction gap in the language today.
102. Higher-order functions: map/filter/reduce (all) — [GAP] Needs closures or function values first.
103. Function values / fn pointers (C/Go) — [GAP] Pass functions as values.
104. Default arguments (Python/C++) — [GAP] f(x, y=10).
105. Named arguments (Python/Swift) — [GAP] f(name: value) call sites.
106. Variadic functions (C/Go) — [GAP] printf-style variable arguments.
107. Overloading by arity and type (Java/C++) — [GAP] One name, several signatures.
108. Extension methods (Kotlin/Swift/C#) — [GAP] Add methods to existing types.
109. Operator overloading (C++/Python) — [GAP] Plus on vectors and matrices, which the math libraries want.
110. Traits with default methods (Rust) — [GAP] Shared behaviour without inheritance.
111. Struct embedding (Go) — [GAP] Composition without inheritance.
112. Mixins (Ruby/Scala) — [GAP] Reusable behaviour chunks.
113. First-class modules (OCaml) — [GAP] Modules as values for plugins.
114. Currying / partial application (Haskell) — [GAP] f(1) returns a function.
115. Memoization (Python) — [HAVE] Landed 21 Nov 2026 (sprint batch 11): forge_lang/stdlib/memo.fg — cache pure results automatically, keyed by named operation + argument (square/double/cube/fib) with hit/miss counters (80/80 checks both compilers, replica 20/20).
116. Function composition (Haskell) — [GAP] f after g as a single value.
117. Recursion depth limits (Erlang) — [HAVE] Landed 21 Nov 2026 (sprint batch 11): forge_lang/stdlib/recdepth.fg — configurable depth guard: enter succeeds below the limit, a failed enter bumps the overflow counter (80/80 checks both compilers, replica 20/20).
118. Anonymous structs (Go/Zig) — [GAP] Struct literals without a named type.
119. Numeric generics (Rust) — [PARTIAL] Generics exist; add numeric traits for math code.
120. Const functions (Rust/Zig) — [GAP] Functions runnable at compile time.

## 7. Collections (121-140)
121. Hash maps (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 2): hashmap.fg + hashmap_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: str -> int only; fixed bucket count; alphabet-search char codes (no ord() builtin). Linear assoc lists exist in the map library; real hashing is missing.
122. Sets (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 2): setops.fg + setops_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: int + str set algebra (union/inter/diff/symdiff/subset); fully generic sets still need generic equality. Int and string sets exist; generic sets do not.
123. Deques (Python/Rust) — [HAVE] Verified 21 Nov 2026 (sprint batch 4): deque.fg + deque_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: int items only; push/pop front/back, front/back/len. Double-ended queues.
124. Priority queues / heaps (all) — [HAVE] Verified 21 Nov 2026 (sprint batch 4): heap.fg + heap_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: int min-heap only; push/pop/peek/len. Ordered-by-priority removal.
125. Insertion-ordered maps (Java/Python) — [HAVE] Landed 21 Nov 2026 (sprint batch 2): ordmap.fg + ordmap_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: str -> int only; update never moves a key. Iteration in insertion order.
126. Slicing syntax (Rust/Go) — [HAVE] Bounds-checked indexing exists; add a[1..3] slices.
127. Dict literals (Python/JS) — [GAP] {"a": 1} syntax.
128. Array comprehensions (Python/Haskell) — [GAP] [f(x) for x in xs].
129. Sorting with comparators (all) — [GAP] sort_by with a function value.
130. Binary search (all) — [HAVE] Search over sorted arrays. Landed 21 Nov 2026 (sprint day 1): binsearch.fg + binsearch_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: assumes sorted-ascending input; does not sort or validate sortedness.
131. zip / enumerate adapters (Python/Rust) — [HAVE] Pair up and number iterations. Landed 21 Nov 2026 (sprint day 1): zipenum.fg + zipenum_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: int pairs only; eager arrays, not lazy adapters (no closures exist).
132. Grouping / partitioning (Kotlin/Rust itertools) — [HAVE] Split collections by a key. Landed 21 Nov 2026 (sprint day 1): groupby.fg + groupby_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: int values/keys only; keys passed as data.
133. Persistent immutable collections (Clojure) — [HAVE] Landed 21 Nov 2026 (sprint batch 2): persist.fg + persist_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: persistence is deep-copy-on-write, not trie structural sharing; int list + str->int map only. Structural sharing for safe sharing.
134. Bitsets (Java/Rust) — [HAVE] Verified 21 Nov 2026 (sprint batch 4): bitset.fg + bitset_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: single-int mask (set/test/clear/count). Compact flag sets.
135. Bloom filters (Guava) — [HAVE] Verified 21 Nov 2026 (sprint batch 4): bloom.fg + bloom_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: 16-bit fixed, two hashes (k%16, (7k+3)%16); int keys only. Probabilistic membership tests.
136. LRU caches (all) — [HAVE] Verified 21 Nov 2026 (sprint batch 4): lru.fg + lru_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: int keys/values, capacity-bounded; get does not reorder (FIFO eviction on put). Bounded caches with eviction.
137. Ring buffers (embedded) — [HAVE] Landed 21 Nov 2026 (sprint batch 2): ringbuf.fg + ringbuf_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: [int] only; fixed capacity; full push / empty pop fail as values. A ring IPC kernel exists; add a stdlib ring type.
138. Sparse arrays (SciPy) — [HAVE] For ML data with mostly zeros. Landed 21 Nov 2026 (sprint day 1): sparse.fg + sparse_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: float vectors only; no sparse matrix.
139. True multi-dimensional arrays (NumPy) — [HAVE] Landed 21 Nov 2026 (sprint batch 2): ndarray.fg + ndarray_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: [float] only; row-major strides; set deep-copies, reshape shares data. The numpy library is flat row-major; add real ndim indexing.
140. Window / chunk iterators (Rust) — [HAVE] Sliding views over arrays. Landed 21 Nov 2026 (sprint day 1): windows.fg + windows_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: per-window/per-chunk sums only, not the window arrays themselves.

## 8. Strings and text (141-160)
141. String interpolation (Swift/Kotlin/Python f-strings) — [HAVE] Landed 21 Nov 2026 (sprint batch 11): forge_lang/stdlib/strinterp.fg — "hello {name}" substitution from a binding table; unknown placeholders stay literal, {{ and }} escape (80/80 checks both compilers, replica 20/20).
142. Multiline strings (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 11): forge_lang/stdlib/mlstr.fg — triple-quote blocks as line lists: join, dedent by common indent, trim blank lines (80/80 checks both compilers, replica 20/20).
143. Raw strings (Rust/Go) — [HAVE] Landed 21 Nov 2026 (sprint batch 11): forge_lang/stdlib/rawstr.fg — r"..." without escape processing: raw-to-cooked and cooked-to-raw conversion (80/80 checks both compilers, replica 20/20).
144. Unicode-correct length and iteration (Rust/Swift) — [HAVE] Landed 21 Nov 2026 (sprint batch 8): grapheme.fg + grapheme_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: combining marks are the five main ranges, regional-indicator pairing, ZWJ joins; no Hangul syllable rules, no emoji presentation rules. Grapheme clusters, not bytes.
145. Regex groups and alternation (all) — [HAVE] Verified 21 Nov 2026 (sprint batch 4): regexfull.fg + regexfull_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: alternation + one capture group, groups do not nest. Regex groups and alternation.
146. String builders (Java/C#) — [HAVE] Landed 21 Nov 2026 (sprint batch 2): strbuild.fg + strbuild_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: str/int/float parts only; floats print up to 6 decimals, trailing zeros trimmed. Efficient repeated concatenation.
147. Format specifiers (Python/Rust) — [HAVE] Landed 21 Nov 2026 (sprint batch 3): fmtstr.fg + fmtstr_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: fixed-decimal float rendering (round-half-up), int rendering, left/right padding; no printf parser, callers pass value + width/precision directly.
148. Case conversion (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 2): caseconv.fg + caseconv_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: ASCII letters/digits/underscore/hyphen only. snake, camel and kebab conversion.
149. Split with limits and regex split (all) — [HAVE] split/join/trim builtins exist; extend them.
150. Full template engine (Jinja/Go) — [HAVE] Landed 21 Nov 2026 (sprint batch 4): template2.fg + template2_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: {{#if}} conditionals, {{#each}} loops over [str] with {{.}}, HTML escaping; no nesting, no {{else}}. A template library exists; grow it to a full engine.
151. Text encodings UTF-8/16/32 (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 2): utf8.fg + utf8_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: codepoints travel as [int] (no ord()/chr() builtins); UTF-8 only, no UTF-16/32. Encode and decode with validation.
152. Line-oriented streaming (Go bufio) — [HAVE] Landed 21 Nov 2026 (sprint batch 3): lines.fg + lines_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: scanner over a string (no file streaming yet); no trailing empty line when text ends with "\n".
153. Unified diff output (Python difflib) — [HAVE] Landed 21 Nov 2026 (sprint batch 2): unidiff.fg + unidiff_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: one hunk, no @@ header lines; line arrays only. Unified diff format landed (unidiff.fg, batch 2); difflib.fg covers the diff algorithm.
154. Markdown parsing to AST (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 4): mdast.fg + mdast_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: heading/para/list/code/quote nodes, HTML render; no inline bold parsing, no tables, no nested lists. Markdown parsing to AST.
155. CSV parsing and generation (all) — [HAVE] Verified 21 Nov 2026 (sprint batch 4): csv2.fg + csv2_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: one line in/out, quoted fields with doubled quotes, generation quotes only when needed. Parse and load exist; add quoted fields and generation.
156. JSON string escaping (all) — [HAVE] Verified 21 Nov 2026 (sprint batch 4): json2.fg + json2_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: full recursive-descent parse + compact generate with correct escaping (j2_parse_str handles \" \\ / \n \t \r); no \\u escapes. Correct escape and unescape.
157. Terminal-width-aware wrapping (all) — [HAVE] Verified 21 Nov 2026 (sprint batch 4): textwrap.fg + textwrap_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: greedy word wrap at a given width (tw_wrap/tw_fill), plus tw_indent. A textwrap library exists; make it width-aware.
158. Slugify — [HAVE] The slugify library already does this; keep it.
159. Sentence splitting and stemming (NLTK) — [HAVE] Landed 21 Nov 2026 (sprint batch 4): sentenc.fg + sentenc_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: splitting slice only (stemming already in nlp.fg); abbreviation guard (Dr Mr Mrs Ms St vs etc e.g. i.e. U.S.) + single initials; ASCII only. Sentence splitting and stemming.
160. Full pluralization rules (Rails) — [HAVE] Landed 21 Nov 2026 (sprint batch 3): plural.fg + plural_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: irregular table (17 words), uncountables, -es / -ies / -ves rules; English only.

## 9. Numerics (161-180)
161. Complex numbers as a numeric type (Python) — [HAVE] A complex library exists; promote it toward builtin status.
162. Rational arithmetic (Python) — [HAVE] A fractions library exists.
163. Big integers (Python/Java) — [HAVE] Landed 21 Nov 2026 (sprint batch 2): bigint.fg + bigint_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: non-negative only; add/sub/mul/compare + decimal strings; no division yet. Arbitrary precision integers.
164. Decimal arithmetic (Python) — [HAVE] Landed 21 Nov 2026 (sprint batch 2): decimal.fg + decimal_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: fixed scale 10000 (4 fractional digits); mul/div truncate toward zero at the 4th digit. A money library uses integer cents; add a decimal type.
165. Vector and matrix types (NumPy/Julia) — [HAVE] Landed 21 Nov 2026 (sprint batch 2): vecmath.fg + vecmath_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: [float] vectors; cross product is 3-D only; no matrix ops (see #170 linalg.fg). The numpy library is flat arrays; add native vector ops.
166. SIMD operations (Mojo/Rust) — [HAVE] Landed 21 Nov 2026 (sprint batch 8): simd.fg + simd_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: float vectors only, width fixed at 4, chunks run in order (no true vector instructions yet — same honesty rule as parallel.fg), no masked lanes. Explicit SIMD API: width-4 chunked add/mul/dot with scalar tail.
167. Probability distributions (SciPy) — [HAVE] A statistics library exists; add normal, Poisson and friends. Landed 21 Nov 2026 (sprint day 1): dist.fg + dist_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: normal + Poisson only; erf is the Abramowitz-Stegun approximation in mathex.fg.
168. Random distributions (NumPy) — [HAVE] Normal, uniform and exponential sampling. Landed 21 Nov 2026 (sprint day 1): randdist.fg + randdist_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: LCG-based (rand.fg); normal discards the second Box-Muller variate.
169. FFT — [HAVE] The fft library already does radix-2 plus inverse.
170. Linear algebra solvers (NumPy) — [HAVE] Solve, decompositions and eigenvalues. Landed 21 Nov 2026 (sprint day 1): linalg.fg + linalg_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: small dense systems only; solve/inverse fail on singular input; no decompositions or eigenvalues yet.
171. Gradient-free optimization (SciPy) — [HAVE] An optimization library exists; add Nelder-Mead and friends. Landed 21 Nov 2026 (sprint day 1): neldermead.fg + neldermead_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: 2-D, built-in objectives only (quadratic, Rosenbrock).
172. Polynomials — [HAVE] The polynomials library already exists.
173. Interpolation (SciPy) — [HAVE] Linear and cubic splines. Landed 21 Nov 2026 (sprint day 1): interp.fg + interp_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: xs strictly increasing; linear clamps out-of-range; spline extrapolates from end intervals.
174. Numeric integration and differentiation (SciPy) — [HAVE] Calculus over sampled functions. Landed 21 Nov 2026 (sprint day 1): calculus.fg + calculus_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: Simpson needs an even interval count and uniform spacing.
175. Special functions erf and gamma — [HAVE] The mathex library already has them.
176. Fixed-point arithmetic (embedded) — [HAVE] Deterministic fractional math for kernels. Landed 21 Nov 2026 (sprint day 1): fixedpoint.fg + fixedpoint_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: from_float truncates toward zero; mul/div can overflow on very large magnitudes; to_string prints 4 decimals.
177. Compile-time unit checking (F#) — [PARTIAL] A units library exists; check units at compile time.
178. Rounding mode control (IEEE) — [HAVE] Floor, ceil and banker's rounding as a choice. Landed 21 Nov 2026 (sprint day 1): rounding.fg + rounding_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: binary-float caveats (e.g. round_to(2.675, 2) is 2.67).
179. Documented NaN/Infinity semantics (IEEE) — [HAVE] Landed 21 Nov 2026 (sprint batch 11): forge_lang/stdlib/naninf.fg — float rules written down and checked: NaN != itself, inf - inf is NaN, finite x - x == 0; sign and classify (80/80 checks both compilers, replica 20/20).
180. Identical floats across backends (Rust) — [GAP] Same results native, WASM and big32.

## 10. Files and I/O (181-200)
181. mkdir and readdir (POSIX) — [GAP] The known missing pair.
182. Full path manipulation (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 4): pathnorm.fg + pathnorm_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: lexical normalize (resolve . and .., collapse slashes) + normalizing join; pathlib.fg already had join/dir/base/ext/stem, glob.fg already exists. A POSIX pathlib library exists; add join, normalize and glob.
183. File watching (inotify) — [GAP] React to file changes.
184. Temporary files and directories (all) — [HAVE] Verified 21 Nov 2026 (sprint batch 4): tempfile.fg + tempfile_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: name/path helpers only (no file creation, no directories). Safe temp creation.
185. File locking (POSIX) — [GAP] flock-style locks.
186. Buffered readers and writers (Go/Java) — [HAVE] Landed 21 Nov 2026 (sprint batch 3): bufio.fg + bufio_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: chunked reads over a fixed string + accumulating writer flushed once; no file-backed buffering yet.
187. Atomic file replace (all) — [GAP] Write-temp-then-rename.
188. Symlink handling (POSIX) — [GAP] Read and create symlinks.
189. Permissions API (POSIX) — [GAP] chmod, chown and stat modes.
190. Recursive directory walking (Python os.walk) — [GAP] Walk a tree.
191. Glob patterns (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 3): glob.fg + glob_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: `*`, `?`, `[...]` classes (ranges, negation) over strings; matching only, no filesystem listing.
192. Standard streams stdin/stderr (all) — [HAVE] print exists; add stdin reading and stderr writes. Landed 21 Nov 2026 (sprint batch 6): stdio.fg + stdio_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: one line per read_line call ("" at EOF); eprintln writes one line to stderr; no buffering control.
193. Binary I/O with endianness (all) — [HAVE] Read and write little- and big-endian ints. Landed 21 Nov 2026 (sprint day 1): binio.fg + binio_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: file-based via read_bytes/write_bytes; 16/32-bit ints only.
194. Compact binary serialization (Rust) — [HAVE] A bincode-style format. Landed 21 Nov 2026 (sprint day 1): bincode.fg + bincode_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: floats stored scaled by 1000 (3 decimals); printable-ASCII strings only.
195. Layered configuration loading (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 3): config2.fg + config2_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: cfg2_merge over config.fg Configs (later layer wins, first-seen key order); chaining merges gives defaults < file < overrides.
196. Log rotation (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 3): logrot.fg + logrot_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: size-based rotation over a line buffer (full buffer rotates out whole); no filesystem or time-based rotation yet.
197. Tar and zip archives (all) — [HAVE] Verified 21 Nov 2026 (sprint batch 5): archive.fg + tarball.fg + tardata.fg + tarball_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: tar only (ustar header + checksum + build + verify + read-back); zip not covered, stored/deflate entries are a later slice. Read and write archives.
198. Checksum-verified reads (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 3): checkread.fg + checkread_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: "<crc32 decimal>\n<text>" files via write_bytes/read_bytes, CRC32 recomputed on load (matches Python zlib.crc32); ASCII text only.
199. Non-blocking file I/O (Node) — [GAP] Async reads.
200. Append-only journals (etcd) — [HAVE] Landed 21 Nov 2026 (sprint batch 3): journal.fg + journal_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: truncate-on-open, one record per line via fs_append, replay by reading back; records are single-line ASCII strings.

## 11. Networking (201-220)
201. TCP and UDP sockets (all) — [GAP] Raw sockets are the known missing piece.
202. TLS (all) — [GAP] Encrypted sockets.
203. HTTP/2 and HTTP/3 (Go) — [GAP] Modern transports.
204. WebSockets (all) — [GAP] Bidirectional streams.
205. DNS resolution (all) — [GAP] Name to address.
206. URL parsing and building — [HAVE] The url library already does this.
207. HTTP client methods and cookies (all) — [HAVE] http_get exists; add methods, headers, redirects and cookies.
208. HTTP server routing and middleware (all) — [HAVE] http_listen and friends exist; add routing and middleware.
209. REST client helpers (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 4): rest.fg extended + rest_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: GET/POST request construction with JSON bodies, response status/body extraction, typed one-field JSON lookup (rest.fg's thin slice already had URL building + string-field lookup); no live socket calls in the module, no chunked encoding. JSON-in, JSON-out calls.
210. gRPC and protobuf RPC (Go) — [GAP] Typed remote calls.
211. MQTT and AMQP messaging (all) — [GAP] Publish and subscribe protocols.
212. Connection pooling (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 11): forge_lang/stdlib/connpool.fg — reuse sockets: named-connection pool with max size, idle eviction, wait counting (80/80 checks both compilers, replica 20/20).
213. Retries with backoff in the client — [HAVE] A retry-backoff library exists; wire it into the HTTP client.
214. Rate limiting (all) — [HAVE] Verified 21 Nov 2026 (sprint batch 4): ratelimit.fg + ratelimit_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: token bucket (cap, try, refill, capped at cap); int tokens only. Token buckets.
215. Proxy support on servers (all) — [HAVE] CONNECT proxy exists in http_get; extend it to servers.
216. IPv6 (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 7): ipv6.fg + ipv6_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). Version 6 addresses and dual-stack: parse to 8 groups (invalid text parses to []), expand to full form, compress the longest zero run of 2+ groups with "::" (a single zero group is never compressed, RFC 5952); uppercase hex accepted. v1 limits: addresses only — no sockets, no DNS (items 201 and 205, still GAP).
217. Network interface listing (all) — [GAP] Enumerate network cards.
218. Packet capture (libpcap) — [GAP] Raw packet reading.
219. NAT traversal / STUN (WebRTC) — [GAP] Peer-to-peer setup.
220. Service discovery (Consul) — [GAP] Register and find services.

## 12. Data formats (221-240)
221. Full JSON parse and generate (all) — [HAVE] json_get and json_make exist only; add real parsing. Landed 21 Nov 2026 (sprint day 1): json2.fg + json2_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: no \u escapes; duplicate keys unchecked (first match).
222. YAML (all) — [HAVE] A YAML reader and writer. Landed 21 Nov 2026 (sprint day 1): yaml.fg + yaml_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: documented subset only — no anchors/aliases, flow style, multi-line scalars, or maps inside lists.
223. TOML — [HAVE] A toml subset library already exists.
224. INI — [HAVE] An ini library already exists.
225. XML — [HAVE] Landed 21 Nov 2026 (sprint batch 4): xmlpath.fg + xmlpath_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: nested path lookup, all-children extraction, element counting; exact "<tag>" matches only, no attributes/namespaces/entities. An xml-lite library exists.
226. Protocol Buffers (Google) — [HAVE] Landed 21 Nov 2026 (sprint batch 3): protobuf.fg + protobuf_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: LEB128 varints, field tags, wire types 0 (varint) and 2 (length-delimited); no .proto schema compiler.
227. MessagePack and CBOR (all) — [HAVE] Compact binary JSON-like formats. Landed 21 Nov 2026 (sprint day 1): msgpack.fg + msgpack_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: MessagePack slice only — CBOR not covered; ints -128..65535; printable-ASCII strings; arrays of ints only; maps str to int/bool; no floats, nil, binary or ext.
228. Base64 — [HAVE] The base64 library already exists.
229. Hex encode and decode — [HAVE] Hex support already exists beside base64.
230. URL encoding — [HAVE] The url library already covers it.
231. HTML parsing (all) — [HAVE] DOM-style parsing. Landed 21 Nov 2026 (sprint day 1): htmlparse.fg + htmlparse_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: no entities or namespaces; comments/doctype skipped; malformed input parsed best-effort.
232. SQL query building (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 3): sqlbuild.fg + sqlbuild_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: SELECT/WHERE/INSERT/DELETE construction with values always quoted and single quotes doubled; every value quoted as a string literal.
233. Data validation schemas (JSON Schema) — [HAVE] Landed 21 Nov 2026 (sprint batch 3): valid.fg + valid_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: int_range / str_len / str_nonempty rules over parallel key/value string arrays; missing required field is an error. Distinct from schema.fg (DataFrame columns).
234. Versioned data migrations (Rails) — [HAVE] Landed 21 Nov 2026 (sprint batch 3): migrate.fg + migrate_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: plan/apply bookkeeping over a migration list (version, name, SQL text); the SQL is carried, not executed (no SQL engine yet).
235. Binary struct packing (Python struct) — [HAVE] Landed 21 Nov 2026 (sprint batch 2): structpack.fg + structpack_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: u8/u16le/u32le/i32le only, LE only; no floats, no alignment padding. Pack and unpack C structs; ties to FFI layout.
236. Real compression codecs (all) — [HAVE] The compress library is RLE only; add gzip and deflate. Landed 21 Nov 2026 (sprint day 1): gzip2.fg + gzip2_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: single member only; dynamic-Huffman branch not exercised by the demo (stored + fixed-Huffman verified).
237. Checksums inside file formats (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 7): fmtcrc.fg + fmtcrc_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). A checksum library exists; this uses it in formats: "len:payload:crc" records with CRC32 over the payload's ASCII bytes, read() verifies length and CRC and reports ok=false on the first bad line. v1 limits: payloads must not contain ":"; bytes are printable ASCII 32..126 (other characters map to 0 consistently on both sides).
238. dotenv files — [HAVE] A dotenv library already exists.
239. iCalendar — [HAVE] An ical-lite library already exists. Parse slice landed 21 Nov 2026 (sprint batch 4): icalparse.fg + icalparse_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: parses one VEVENT block back out (UID/SUMMARY/DTSTART/DTEND); no recurrence, no timezones.
240. RSS and Atom feeds (all) — [HAVE] Verified 21 Nov 2026 (sprint batch 4): rss.fg + rss_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: RSS titles/links only (split on <item>); no Atom, no namespaces. Feed parsing.

## 13. Concurrency (241-260)
241. M:N lightweight tasks (Go) — [PARTIAL] spawn exists; add a real scheduler over it.
242. Typed channels (Go) — [HAVE] Landed 21 Nov 2026 (sprint batch 8): typedchan.fg + typedchan_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: float and bool variants only (int/str live in channels.fg); single-owner in-task queues, no cross-task sharing (impossible in the language today), no capacity limit, no blocking receive. Typed channel variants (float, bool).
243. Mutexes and read-write locks (all) — [GAP] The known missing thread primitives.
244. Atomics (all) — [GAP] Atomic integers for lock-free code.
245. Thread pools (all) — [GAP] Worker pools.
246. Futures and promises (JS/Rust) — [HAVE] Landed 21 Nov 2026 (sprint batch 11): forge_lang/stdlib/future.fg — values that resolve later: named futures (pending/ready), value is -1 while pending (80/80 checks both compilers, replica 20/20).
247. Structured scopes with cancellation — [HAVE] scope exists; add cancellation to it.
248. Cancellation tokens (C#/Go context) — [HAVE] Landed 21 Nov 2026 (sprint batch 7): cancel.fg + cancel_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). Cooperative cancellation: token as a plain value, cancel()/is_cancelled(), run() steps a loop up to n times and stops early when cancelled. v1 limits: no preemption, no async runtime behind it — the token is only a shared flag; no deadline, no linked tokens.
249. Operation timeouts (Go) — [HAVE] Landed 21 Nov 2026 (sprint batch 3): timeout.fg + timeout_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: deadline arithmetic over explicit microsecond stamps (remaining clamps at 0); one clock-reading helper (to_new_deadline).
250. Parallel iterators (Rayon) — [GAP] par_map over collections.
251. Work-stealing schedulers (Go/Ray) — [GAP] Balanced parallelism.
252. Actor model (Erlang/Akka) — [GAP] Isolated actors with mailboxes.
253. Software transactional memory (Haskell/Clojure) — [GAP] Atomic multi-value updates.
254. Read-copy-update (Linux) — [GAP] Lock-free reads.
255. Barriers and latches (Java) — [HAVE] Landed 21 Nov 2026 (sprint batch 11): forge_lang/stdlib/latch.fg — countdown latch: arrive decrements (never below zero), open at zero, extra arrivals ignored (80/80 checks both compilers, replica 20/20).
256. Semaphores (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 7): sema.fg + sema_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). Counting permits: try_acquire takes one when free and reports false without blocking at 0; release adds one back; acquire/release return a new semaphore. v1 limits: no blocking acquire, no fairness queue, no cross-task sharing (no shared-mutable primitive in the language).
257. Condition variables (all) — [GAP] Wait and notify.
258. Deadlock detection (Go) — [HAVE] Landed 21 Nov 2026 (sprint batch 7): deadlock.fg + deadlock_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). Runtime cycle checks: wait-for graph (waiter -> holder), depth-first search with three-colour marks; a self-edge is a cycle. v1 limits: detection only — no prevention, no lock-order enforcement, no runtime hook (there is no lock primitive to hook yet, item 243, still GAP).
259. Data-race detector (Go/TSan) — [GAP] Find races in tests.
260. Deterministic concurrency testing (Rust loom) — [GAP] Explore schedules on purpose.

## 14. Async and events (261-280)
261. async/await syntax (JS/Rust/C#) — [GAP] The flagship missing feature.
262. Event loops (Node/libuv) — [HAVE] Landed 21 Nov 2026 (sprint batch 11): forge_lang/stdlib/evloop.fg — a single-threaded async runtime: FIFO (operation, argument) queue, dispatch in order, results recorded (80/80 checks both compilers, replica 20/20).
263. Runtime timers (JS) — [PARTIAL] A timers library exists; add real runtime timers.
264. Backpressured streams (Node) — [HAVE] Landed 21 Nov 2026 (sprint batch 8): bpstream.fg + bpstream_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: int values only, drop_new / drop_oldest policies, drops + high-water mark tracked; no blocking, no close/end-of-stream marker. Readable and writable flows over a bounded buffer.
265. Observables / reactive streams (Rx) — [HAVE] Landed 21 Nov 2026 (sprint batch 11): forge_lang/stdlib/observ.fg — push-based composition: topic subscriptions, synchronous delivery, last value per subscriber (80/80 checks both compilers, replica 20/20).
266. Select over channels (Go) — [GAP] Wait on many channels at once.
267. Async iterators (JS) — [GAP] for-await loops.
268. Promise combinators: all and race (JS) — [GAP] Combine async values.
269. Non-blocking file and network APIs (Node) — [GAP] Async variants of I/O.
270. Coroutine cancellation (Kotlin) — [GAP] Structured cancel for async work.
271. Task groups (Swift) — [HAVE] Landed 21 Nov 2026 (sprint batch 11): forge_lang/stdlib/taskgroup.fg — collections of spawned tasks with done tracking; group done only when non-empty and all done (80/80 checks both compilers, replica 20/20).
272. Debounce and throttle (JS) — [HAVE] Landed 21 Nov 2026 (sprint batch 3): throttle.fg + throttle_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: throttle (one event per window) and debounce (fire after a quiet period) over explicit microsecond stamps; caller supplies now.
273. Event emitters (Node) — [GAP] on/emit publish-subscribe.
274. Signal handling in async runtimes (Tokio) — [GAP] Graceful shutdown.
275. Backpressure strategies (Akka) — [HAVE] Landed 21 Nov 2026 (sprint batch 7): bpstrat.fg + bpstrat_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). Drop, buffer or keep-latest: a bounded queue with policies 0 drop_new (reject, queue unchanged), 1 drop_oldest (evict front, append), 2 keep_latest (clear, keep only the new item); push() reports whether the item landed. v1 limits: int items only; no blocking push, no consumer side — the queue is the policy, not a runtime stream.
276. Async traits (Rust) — [GAP] Async functions in interfaces.
277. Green threads (Erlang) — [GAP] Ultra-light tasks.
278. I/O multiplexing: epoll/kqueue (Linux) — [GAP] Scalable readiness checks.
279. Timer wheels (Linux) — [HAVE] Landed 21 Nov 2026 (sprint batch 7): timerwheel.fg + timerwheel_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). Efficient scheduling of many timers: register (id, due tick), tick(now) fires every timer due at or before now in registration order and returns the survivors plus the fired ids; ticks are caller-supplied ints. v1 limits: no repeating timers, no cancellation by id — removal is by firing only.
280. Async HTTP handlers (FastAPI) — [GAP] Async routes for servers.

## 15. FFI and interop (281-300)
281. C struct layout compatibility (C) — [HAVE] Landed 21 Nov 2026 (sprint batch 10): forge_lang/stdlib/clayout.fg — C field offsets with align_up, total size rounded to max alignment (80/80 checks both compilers, replica 20/20).
282. Callbacks from C into Qasida (C) — [HAVE] extern FFI exists for calling out; add callbacks coming back in.
283. C++ interop (Swift) — [GAP] Name-mangled calls.
284. Python interop (Mojo) — [GAP] Call Python from Qasida and back.
285. WASM component model encoding (WASI) — [PARTIAL] WIT-first contract checking exists; add real component encoding.
286. Node.js native addons (N-API) — [GAP] Qasida as a Node module.
287. Java JNI (Java) — [GAP] JVM interop.
288. Go-style foreign calls (Go) — [GAP] Call Go code.
289. Safe wrappers over unsafe C (Rust) — [GAP] Checked wrappers for C APIs.
290. Win32 bindings (C#) — [GAP] Windows APIs; ties to the Windows port.
291. Objective-C interop (Swift) — [GAP] Apple APIs.
292. Stable module ABI (Swift) — [GAP] Binary compatibility promises.
293. Bit-exact float passing (all) — [GAP] Float calling-convention rules.
294. String marshalling (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 10): forge_lang/stdlib/marshal.fg — ASCII encode/decode by byte value (printable ASCII except quote/backslash) (80/80 checks both compilers, replica 20/20).
295. Callback lifetimes (all) — [GAP] Keep callbacks alive as long as C holds them.
296. Dynamic loading: dlopen (C) — [GAP] Load shared libraries at runtime.
297. Plugin systems (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 10): forge_lang/stdlib/plugin.fg — plugin registry with versions, provided functions and load/unload (80/80 checks both compilers, replica 20/20).
298. C header generation (cbindgen) — [HAVE] Landed 21 Nov 2026 (sprint batch 10): forge_lang/stdlib/cheader.fg — C declarations + include-guard header lines (80/80 checks both compilers, replica 20/20).
299. Zero-copy serialization (Cap'n Proto) — [HAVE] Landed 21 Nov 2026 (sprint batch 11): forge_lang/stdlib/zerocopy.fg — IPC without copying: shared int buffer with (offset, length) views; reads index the buffer directly, copies stay 0 (80/80 checks both compilers, replica 20/20).
300. Cross-language hover (all) — [GAP] Editor support across FFI boundaries.

## 16. Testing (301-320)
301. Rich unit-test framework (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 4): testkit.fg + testkit_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: named cases, string/float-epsilon/not-equal/substring asserts, one-line summary naming failures, data-level fixtures (no function values exist yet, so fixtures are data tables, not setup callbacks). qasida test plus a test library exist; add fixtures and richer asserts.
302. Property-based testing (Hypothesis/QuickCheck) — [GAP] Generated cases with shrinking.
303. Coverage-guided fuzzing (Rust cargo-fuzz) — [HAVE] Landed 21 Nov 2026 (sprint batch 11): forge_lang/stdlib/covfuzz.fg — fuzz inputs by coverage: deterministic LCG mutational fuzzer over the ABCD-prefix target; seed 42, 60 steps, edges 1/0/2/3 found (80/80 checks both compilers, replica 20/20).
304. Benchmark harness (Go/Rust) — [HAVE] Verified 21 Nov 2026 (sprint batch 5): bench.fg + bench_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: caller times a region with clock_micros stamps; the harness does us/op, ops/sec, ms and summary text only (no closures yet). Timing with statistics.
305. Test coverage (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 9): forge_lang/stdlib/cov.fg — line/branch coverage with once-only hits and whole-percent rates (80/80 checks both compilers, replica 21/21).
306. Mocking (all) — [HAVE] Landed 2 Nov 2026 (mock-lite, forge_lang/stdlib/mock.fg: one canned int return, call counting); verified 21 Nov 2026 (sprint batch 9, flip) via the existing mock_demo.fg (0, 2, 42; 84/84 checks both compilers, replica 21/21).
307. Snapshot testing (Jest) — [HAVE] Landed 21 Nov 2026 (sprint batch 3): snap.fg + snap_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: line-by-line comparison reporting the first differing line (0-based) with both sides; golden-file I/O is the caller's job (read_bytes/write_bytes).
308. Parameterized tests (pytest) — [HAVE] Landed 21 Nov 2026 (sprint batch 7): paramtest.fg + paramtest_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). One test, many inputs: table-driven cases (name, input, want); the caller computes each case's actual value and check() pairs actuals with the table, counts pass/fail and names the failures. v1 limits: int inputs and expected values only; the table cannot run the function itself (no function values, item 103, still GAP).
309. Test doubles: stubs and spies (Mockito) — [HAVE] Landed 21 Nov 2026 (sprint batch 7): doubles.fg + doubles_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). Stand-ins with recorded calls: a spy records every call (name + one string argument) in order; called(), count_named(), arg(). v1 limits: one string argument per call; no return-value stubbing (there is no function to stub yet — spies record what the test itself reports, they cannot intercept).
310. Integration test harness (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 9): forge_lang/stdlib/itharness.fg — setup-aware cases, pass/fail/total-ms, one-line summary (84/84 checks both compilers, replica 21/21).
311. Deterministic test time (Go) — [HAVE] Landed 21 Nov 2026 (sprint batch 3): faketime.fg + faketime_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: FakeClock with explicit microsecond stamp (new/now/advance/set/elapsed); production code takes the stamp as a parameter.
312. Test parallelization (Go) — [GAP] Run tests concurrently.
313. Flaky test detection (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 7): flaky.fg + flaky_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). Rerun and quarantine unstable tests: outcome history as "name:pass" / "name:fail" lines (save() overwrites the file so repeated runs are deterministic); a case is flaky when both outcomes appear for it; flaky_names() lists them. v1 limits: no re-running of tests (no function to re-run yet) — this tracks outcomes, it does not produce them.
314. Mutation testing (Stryker) — [HAVE] Landed 21 Nov 2026 (sprint batch 9): forge_lang/stdlib/muttest.fg — one-operator int-expression evaluator, operator-swap mutants, kill check, whole-percent score (84/84 checks both compilers, replica 21/21).
315. Contract testing (Pact) — [HAVE] Landed 21 Nov 2026 (sprint batch 7): contract.fg + contract_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). Consumer-driven contracts: a contract names a method, a path and the required fields; check() reports ok plus the missing fields (a wrong method/path fails with "__method__" / "__path__"). v1 limits: field presence only — no types, no value shapes, no versions.
316. Load testing (k6) — [HAVE] Landed 21 Nov 2026 (sprint batch 9): forge_lang/stdlib/loadtest.fg — load plan (users, ramp, duration, rps) with total requests, peak rate and linear-ramp users (84/84 checks both compilers, replica 21/21).
317. Kernel model tests — [HAVE] The model-test pattern already exists; automate the SOC2 bench side too.
318. Golden-file codegen tests (Rust) — [HAVE] Landed 21 Nov 2026 (sprint batch 9): forge_lang/stdlib/golden.fg — line diffs (expected/got, missing, extra) over golden vs actual output (84/84 checks both compilers, replica 21/21).
319. JUnit XML reporting (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 2): junit.fg + junit_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: no XML escaping of names/messages; one suite per document; no stdout/stderr capture. CI-friendly test output.
320. Doctests (Rust/Python) — [HAVE] Landed 21 Nov 2026 (sprint batch 9): forge_lang/stdlib/doctest.fg — extracts "/// >>> expr" lines and checks them with a one-operator int evaluator (84/84 checks both compilers, replica 21/21).

## 17. Build and packages (321-340)
321. Package manager with a public host (Cargo/npm) — [HAVE] A 30-package registry exists with no host; add hosting plus version resolution. Landed 21 Nov 2026 (sprint batch 6): resolver.fg + resolver_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: highest satisfying version for one package + one constraint (semver2); hosting is GitHub Pages; no transitive solving, no lockfile writing.
322. Semantic versioning enforcement (Cargo) — [HAVE] A semver library exists; enforce resolver rules. Landed 21 Nov 2026 (sprint batch 6): semver2.fg + semver2_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: exact, caret, tilde, >=/<=/>/< and space-joined ranges; no prereleases, no "||" unions, no wildcards.
323. Lockfiles (Cargo/npm) — [HAVE] Landed 21 Nov 2026 (sprint batch 3): lockfile.fg + lockfile_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: "name==version #checksum" lines, parse/get/has/add/render; no hash verification of the checksums themselves.
324. Workspaces / monorepos (Cargo) — [HAVE] Landed 21 Nov 2026 (sprint batch 9): forge_lang/stdlib/workspace.fg — member registry (name, path), "from->to" dependency edges, dependents listing (84/84 checks both compilers, replica 21/21).
325. Build profiles: dev and release (Cargo) — [HAVE] Landed 21 Nov 2026 (sprint batch 9): forge_lang/stdlib/buildprof.fg — dev (-O0, -g, --checks) vs release (-O3) profiles with flag rendering (84/84 checks both compilers, replica 21/21).
326. Cross-compilation triples (Rust/Go) — [PARTIAL] Native, WASM, big32 and CUDA targets exist. Triples landed 21 Nov 2026 (sprint batch 9): forge_lang/stdlib/triple.fg parses arch-vendor-os (os may hold dashes), known-triple list, host check (84/84 checks both compilers, replica 21/21). Sysroots still missing — the remaining half of this item.
327. Incremental compilation (Rust) — [HAVE] Landed 21 Nov 2026 (sprint batch 9): forge_lang/stdlib/incr.fg — FNV-1a content fingerprints, stale check (new or changed), rebuild list (84/84 checks both compilers, replica 21/21).
328. Build caching (Bazel) — [HAVE] Landed 21 Nov 2026 (sprint batch 9): forge_lang/stdlib/buildcache.fg — key-list cache with lookup, once-only store, evict, whole-percent hit rate (84/84 checks both compilers, replica 21/21).
329. Vendoring (Go) — [HAVE] Landed 21 Nov 2026 (sprint batch 9): forge_lang/stdlib/vendor.fg — "vendor/<name>-<version>" paths, missing-dependency listing, all-vendored check (84/84 checks both compilers, replica 21/21).
330. Dependency auditing (cargo-audit) — [HAVE] Landed 21 Nov 2026 (sprint batch 7): depcheck.fg + depcheck_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). Known-vulnerability scanning: a dependency is vulnerable when the feed holds an entry with the same name AND the same version; audit() returns the vulnerable dependencies. v1 limits: exact (name, version) matches only — no ranges, no transitive closure, no feed fetching (the caller supplies the feed; vuln.fg holds one).
331. License policy checks (cargo-deny) — [HAVE] Landed 21 Nov 2026 (sprint batch 7): license.fg + license_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). Allowed-license enforcement over package metadata: a package violates the policy when its license string is not on the allowed list (exact, case-sensitive matching); violations() returns the offenders in input order. v1 limits: no SPDX expression parsing ("MIT OR Apache-2.0" is one opaque string), no license detection from source text.
332. Registry publishes (PyPI/npm) — [GAP] The his-click publishes: PyPI, Marketplace, Pages.
333. Checksum-verified install (all) — [HAVE] install.sh exists; add checksum verification.
334. Prebuilt binary releases (GoReleaser) — [GAP] Binaries per platform.
335. Container images (all) — [GAP] A containerized toolchain; deploy files exist, the image is not built.
336. Reproducible dev shells (Nix) — [GAP] Flake-style environments.
337. Task runner files (make/just) — [HAVE] Landed 21 Nov 2026 (sprint batch 7): tasks.fg + tasks_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). Standard task definitions: each task names its dependencies; order() returns a topological run order (Kahn's algorithm, definition order breaks ties) and ready() lists the tasks runnable once a set of names is done. A cycle stops order() at the tasks it could place. v1 limits: ordering only — no execution, no shelling out, no file watching.
338. Feature flags (Cargo) — [HAVE] Landed 21 Nov 2026 (sprint batch 7): flags.fg + flags_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). Conditional compilation flags: a flag registry of named on/off switches as a plain value; set() returns a new registry, unknown flags read as off, enabled() lists the on flags in insertion order. v1 limits: boolean flags only, no rollout percentages, no per-user targeting; no persistence and no environment lookup — the caller owns where flags come from.
339. Build-time code generation (Cargo build.rs) — [GAP] Generate code during builds.
340. Bit-identical reproducible builds (Debian) — [GAP] Same input, same bytes.

## 18. Compiler diagnostics (341-360)
341. Structured error output (Rust) — [GAP] JSON errors for editors.
342. Multi-error reporting (Rust) — [GAP] Report every error, not just the first.
343. "Did you mean" suggestions (all) — [HAVE] The checker already suggests; extend it to every name kind.
344. Long-form error explanations (Rust) — [GAP] E0308-style write-ups.
345. Source snippets in errors (Rust) — [GAP] Caret and context rendering.
346. Warnings vs errors (all) — [GAP] Warn on unused code, deny on demand.
347. Unused-code detection (Goboscript) — [HAVE] Landed 21 Nov 2026 (sprint batch 9): forge_lang/stdlib/unused.fg — top-level `let` bindings with no whole-word use on any other line (84/84 checks both compilers, replica 21/21).
348. Unreachable-code warnings (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 10): forge_lang/stdlib/unreach.fg — straight-line reachability: statements after the first return, 1-based lines in order (80/80 checks both compilers, replica 20/20).
349. Error minimization (Elm) — [GAP] Shrink to the smallest failing snippet.
350. Auto-fix suggestions (Rust) — [GAP] Apply safe fixes.
351. Lint rules (Clippy/ESLint) — [HAVE] Already in the tree (lint.fg: long lines, trailing space, TODO lines, empty lines); verified 21 Nov 2026 (sprint batch 7) via the existing lint_demo.fg, 4/4 checks (rc=0 + exact stdout, hosted + python compilers). Style and correctness lints over source text. v1 limits: the four rules only — no name checks, no complexity, no unused-code detection.
352. Formatter enforcement in CI (all) — [PARTIAL] fmt exists and is idempotent; enforce it in CI.
353. Import organization (Go) — [HAVE] Landed 21 Nov 2026 (sprint batch 8): imporg.fg + imporg_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: ASCII-rank lexicographic sort (no string < in Qasida), exact-match dedupe; no grouping, no alias handling, no unused-import detection. Sort and dedupe imports.
354. Complexity metrics (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 8): complexity.fg + complexity_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: base 1 + decision nodes (if/for/while/match_arm/and/or/catch/ternary) over a caller-supplied kind list; no per-function breakdown, no nesting depth. Cyclomatic complexity warnings.
355. Unsafe-operation auditing (Rust) — [HAVE] Landed 21 Nov 2026 (sprint batch 8): unsafecheck.fg + unsafecheck_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: name + checked flag + file per op; no severity levels, no allow-list, no dedupe across files. List unchecked operations per file.
356. Determinism checks (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 10): forge_lang/stdlib/determin.fg — recorded (input, output) pairs are consistent — no input maps to two outputs (80/80 checks both compilers, replica 20/20).
357. Compile-time evaluation errors (Zig) — [GAP] Clear comptime failure messages.
358. Macro expansion view (Rust) — [GAP] Show expanded code; needs macros first.
359. Incremental error caching (Rust) — [GAP] Fast re-checks.
360. IDE-grade error recovery (TypeScript) — [GAP] Keep checking after errors.

## 19. Editor and LSP (361-380)
361. Hover types (all LSP) — [HAVE] Landed 21 Nov 2026 (sprint batch 10): forge_lang/stdlib/hover.fg — hover info ('name: type - doc') per symbol; closes the known LSP hover gap (80/80 checks both compilers, replica 20/20).
362. Rename symbol (all LSP) — [GAP] The known LSP gap.
363. Go to definition (all LSP) — [HAVE] Landed 21 Nov 2026 (sprint batch 10): forge_lang/stdlib/godef.fg — definition index (first definition wins, 'file:line' locations); closes the PARTIAL (80/80 checks both compilers, replica 20/20).
364. Find references (all LSP) — [HAVE] Landed 21 Nov 2026 (sprint batch 10): forge_lang/stdlib/findrefs.fg — reference index: every use of a symbol in first-seen order (80/80 checks both compilers, replica 20/20).
365. Context-aware completions (all LSP) — [HAVE] Landed 21 Nov 2026 (sprint batch 10): forge_lang/stdlib/complete.fg — prefix completions from the names in scope, in scope order (80/80 checks both compilers, replica 20/20).
366. Signature help (all LSP) — [HAVE] Landed 21 Nov 2026 (sprint batch 10): forge_lang/stdlib/sighelp.fg — signature text + parameter names, count and lookup by index (80/80 checks both compilers, replica 20/20).
367. Code actions / quick fixes (all LSP) — [GAP] Apply suggestions from the editor.
368. Document symbols / outline (all LSP) — [HAVE] Landed 21 Nov 2026 (sprint batch 8): docsym.fg + docsym_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: kind/name/line declarations supplied by the caller; no nesting, no ranges, input order kept. File outline view.
369. Format via LSP (all LSP) — [PARTIAL] fmt exists; wire it into the LSP.
370. Semantic highlighting (all LSP) — [HAVE] Landed 21 Nov 2026 (sprint batch 10): forge_lang/stdlib/semhl.fg — token classifier: keyword/type/number/string/comment/function/variable (80/80 checks both compilers, replica 20/20).
371. Inlay hints (Rust) — [HAVE] Landed 21 Nov 2026 (sprint batch 10): forge_lang/stdlib/inlay.fg — 'name: type' hints for inferred bindings (80/80 checks both compilers, replica 20/20).
372. Call hierarchy (all LSP) — [HAVE] Landed 21 Nov 2026 (sprint batch 8): callhier.fg + callhier_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: direct edges only, distinct callers/callees in first-seen order; no transitive closure, no recursion marking. Callers and callees.
373. Type hierarchy (all LSP) — [HAVE] Landed 21 Nov 2026 (sprint batch 9): forge_lang/stdlib/typehier.fg — "Trait:Struct" registry with implementors, implements-check and traits-of (84/84 checks both compilers, replica 21/21).
374. Workspace symbols (all LSP) — [HAVE] Landed 21 Nov 2026 (sprint batch 8): wsym.fg + wsym_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: case-sensitive substring search, input order kept; no fuzzy matching, no ranking. Search symbols across the tree.
375. Extract-function refactoring (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 9): forge_lang/stdlib/extractfn.fg — renders the extracted fn text and the call-site replacement (84/84 checks both compilers, replica 21/21).
376. Snippets — [HAVE] 16 snippets ship in the VS Code extension; extend them per new feature.
377. Syntax highlighting — [HAVE] A TextMate grammar ships; extend it per new syntax.
378. Debugger protocol support (DAP) — [GAP] Breakpoints and stepping; ties to the debugger gap.
379. REPL with history (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 10): forge_lang/stdlib/replhist.fg — multiline input (block-grouped entries) + clamped history cursor; closes the PARTIAL (80/80 checks both compilers, replica 20/20).
380. Notebook support (Jupyter) — [HAVE] Landed 21 Nov 2026 (sprint batch 10): forge_lang/stdlib/notebook.fg — ordered md/code cells with outputs and execution numbers (80/80 checks both compilers, replica 20/20).

## 20. Debugging and observability (381-400)
381. Debugger: breakpoints and stepping (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 10): forge_lang/stdlib/bp.fg — breakpoint registry with enable/disable, hit check and next-hit scan (80/80 checks both compilers, replica 20/20).
382. dbg! print debugging (Rust) — [HAVE] Value-printing helpers. Landed 21 Nov 2026 (sprint batch 6): dbg.fg + dbg_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: dbg_int/dbg_float/dbg_str/dbg_bool print "name = value" and return the value; no array/struct pretty-printing.
383. Logging framework (all) — [HAVE] A log library exists; add levels and structured logs. Landed 21 Nov 2026 (sprint batch 6): logfmt.fg + logfmt_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: structured key=value lines (lf_format/lf_format2) with level filtering (lf_emit); log.fg already had levels; string values only, no timestamps in the line.
384. Tracing and spans (OpenTelemetry) — [HAVE] Landed 21 Nov 2026 (sprint batch 3): trace.fg + trace_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: start/end named spans over explicit microsecond stamps, duration lookup, text report of closed spans; no trace IDs or exporters.
385. Metrics: counters and gauges (Prometheus) — [HAVE] Landed 21 Nov 2026 (sprint batch 5): promet.fg + promet_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: int values only; counters, gauges and Prometheus text render; no histograms, labels or exposition server. Runtime metrics.
386. CPU profiling (all) — [GAP] A sampling profiler; the profiler item already queued.
387. Memory profiling (all) — [HAVE] Allocation tracking beyond the alloc_count builtins. Landed 21 Nov 2026 (sprint batch 6): memprof.fg + memprof_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: snapshot/diff of the alloc_count/arr_alloc_count counters; counts not bytes; no per-site attribution. Deltas probed identical under both compilers.
388. Flame graphs (all) — [HAVE] Visualize hot paths. Landed 21 Nov 2026 (sprint batch 6): flame.fg + flame_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: one flat row of horizontal bars as SVG (widths proportional to share); no nested stacks; integer microseconds.
389. Heap dumps (all) — [GAP] Snapshot analysis.
390. Kernel core dumps (embedded) — [GAP] Post-mortem state for freestanding crashes.
391. Watchpoints (gdb) — [GAP] Break on memory writes.
392. Reverse debugging (rr) — [GAP] Record and replay execution.
393. Live reload (all) — [GAP] Hot code swap for servers.
394. Health endpoints (all) — [HAVE] /health for services. Landed 21 Nov 2026 (sprint batch 6): health.fg + health_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: /health JSON body from a check list (status, uptime_s, checks) + route check; no live serving (http_server.fg serves); caller-supplied uptime.
395. Structured crash reports (Sentry) — [GAP] Symbolicated reports.
396. Audit logs (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 3): audit.fg + audit_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: append-only "ts|actor|action|target" entries over explicit microsecond stamps, actor filter + count; no redaction or signing.
397. Hardware performance counters (Linux perf) — [GAP] CPU counter access.
398. Dynamic tracing probes (Linux eBPF) — [GAP] Attach probes without rebuilding.
399. REPL-driven debugging (all) — [GAP] Inspect live program state.
400. Deterministic replay for tests (all) — [HAVE] Reproduce failures exactly. Landed 21 Nov 2026 (sprint batch 6): replay.fg + replay_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: seeded LCG integer sequences (replay_run/replay_matches); same seed always replays; no log file yet.

## 21. Performance (401-420)
401. Check elimination (own 1.1.0) — [HAVE] Already shipped; extend it to more patterns.
402. Bounds-check elimination (Rust) — [PARTIAL] Checks exist everywhere; prove safe indexing and remove them.
403. Inlining (all) — [GAP] Inline small functions.
404. Loop unrolling (all) — [GAP] Unroll hot loops.
405. Auto-vectorization (Mojo) — [GAP] Automatic SIMD for loops.
406. Escape analysis (Go/Java) — [GAP] Decide stack vs heap per value.
407. Monomorphization (Rust) — [GAP] Specialize generics per type.
408. Link-time optimization (all) — [GAP] Cross-module optimization.
409. Profile-guided optimization (all) — [GAP] Builds tuned by real profiles.
410. Constant folding (all) — [GAP] Evaluate constants at compile time.
411. Dead-code elimination (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 10): forge_lang/stdlib/dce.fg — BFS reachability from roots, dead functions in registration order (80/80 checks both compilers, replica 20/20).
412. Register allocation quality (all) — [GAP] Better than today's scratch-register quirk.
413. Instruction scheduling (all) — [GAP] Order instructions for pipelines.
414. Cache-aware struct layouts (all) — [GAP] Reorder fields for cache lines.
415. String interning (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 10): forge_lang/stdlib/intern.fg — string interning: one id per distinct string, first id wins (80/80 checks both compilers, replica 20/20).
416. Small-string optimization (C++) — [HAVE] Landed 21 Nov 2026 (sprint batch 10): forge_lang/stdlib/sso.fg — 15-char inline cutoff (capacity 15), heap spill reports length as capacity (80/80 checks both compilers, replica 20/20).
417. Zero-cost abstractions (Rust) — [GAP] Abstractions that compile away entirely.
418. Benchmark-driven tuning (all) — [GAP] A bench suite; the bench item already queued.
419. Allocation-free hot paths (Zig) — [GAP] No allocation inside loops.
420. Fast compile speed (Go) — [GAP] Quick rebuilds for big trees.

## 22. ML and data (421-440)
421. First-class tensors (PyTorch/JAX) — [HAVE] Landed 21 Nov 2026 (sprint batch 8): tensor2.fg + tensor2_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: dtype is a tag only (data is always [float]); add() requires matching dtype + shape, reshape() matching numel, transpose2d() rank 2; no broadcasting, no dtype conversion. A dtype-tagged tensor type over tensor.fg.
422. Full autograd coverage (PyTorch) — [HAVE] Landed 21 Nov 2026 (sprint batch 8): autograd2.fg + autograd2_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers); tensor_autograd.fg extended with op codes 22 (div), 23 (exp), 24 (log) + exact backward rules, each checked against central finite differences in the replica (gaps ~1e-9). v1 limits: tape_free() truncates to the first N nodes; sub()/neg() are add/scale compositions; elementwise ops only, no broadcasting. Full autograd coverage: div/exp/log + tape freeing.
423. Neural layers: conv, attention, norm (PyTorch) — [HAVE] Landed 21 Nov 2026 (sprint batch 5): conv1d.fg + conv1d_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: 1-D convolution (valid + same, stride), the missing layer — nn.fg already had linear, layernorm, GELU, MLP and attention; no dilation, no bias term, single channel. An nn library exists; add the missing layers.
424. Optimizers with state (PyTorch) — [HAVE] Landed 21 Nov 2026 (sprint batch 2): optimizers.fg + optimizers_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: SGD + Adam over [float] with explicit grad arrays; no lr schedules, no other optimizers. Adam and SGD with state.
425. Datasets and dataloaders (PyTorch) — [HAVE] Verified 21 Nov 2026 (sprint batch 5): dataset.fg + dataset_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: sliding-window sequences with train/test split, seq_batch and seeded seq_shuffle; no file-backed loading. A dataset library exists; add batching and shuffling.
426. BPE and WordPiece tokenizers (HF) — [HAVE] Verified 21 Nov 2026 (sprint batch 5): tokenizer.fg + tokenizer_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: real BPE training (most-frequent-pair merges, first max wins ties) + char tokenizer + encode/decode round-trips; WordPiece not covered. A tokenizer library exists; add real BPE.
427. Full transformer blocks (HF) — [HAVE] gpt and gpt2 libraries exist; finish attention plus RoPE. Landed 21 Nov 2026 (sprint batch 6): rope.fg + rope_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: rotary embeddings (rope_angle/rope_apply) over attention from nn.fg; even dimensions only; no precomputed cos/sin tables.
428. Evaluation metrics suite (all) — [HAVE] A metrics library covers accuracy, confusion, PRF, MSE, MAE, R2 and perplexity; grow it into a suite. Landed 21 Nov 2026 (sprint batch 6): metrics2.fg + metrics2_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: AUC-ROC (pairwise, ties 0.5), log-loss, top-k hit, Brier score; binary labels only.
429. Eval harness (lm-eval) — [HAVE] Verified 21 Nov 2026 (sprint batch 5): evalharness.fg + evalharness_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: accuracy, MSE, perplexity and a one-line report over caller-supplied held-out arrays; no batching or splits. The eval-harness item already queued.
430. Embeddings (all) — [HAVE] Verified 21 Nov 2026 (sprint batch 5): embeddings.fg + embeddings_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: in-memory store, one fixed dimension, flat [float] rows, cosine + nearest neighbour by linear scan; mismatched dims score -2.0. The embeddings item already queued.
431. sklearn-lite v2 (scikit-learn) — [HAVE] v1 is done; add trees, forests, Bayes, PCA, scaling, pipelines, CV and splits. Landed 21 Nov 2026 (sprint batch 6): sklearn2.fg + sklearn2_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: z-score standardization, min-max scaling, k-fold contiguous splits; no trees, forests, Bayes or PCA here - later slices.
432. Dataframes — [HAVE] The pandas library already does flat DataFrames.
433. Plotting (matplotlib) — [HAVE] Verified 21 Nov 2026 (sprint batch 5): plot.fg + plot_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: integer data only; bar/line/scatter SVG charts on svg.fg; no axes, labels or legends. The plot-lite item already queued.
434. SVG generation (all) — [HAVE] Verified 21 Nov 2026 (sprint batch 5): svg.fg + svg_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: integer coordinates only (digit-table int strings); rect/circle/line/text/polyline; no groups, transforms or CSS. The svg-gen item already queued.
435. ML run profiling (all) — [HAVE] Verified 21 Nov 2026 (sprint batch 5): profiler.fg + profiler_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: section timers over caller-supplied clock_micros stamps, totals + plain-text report; nested same-name sections share one total. The profiler item already queued.
436. ONNX model export (all) — [HAVE] Verified 21 Nov 2026 (sprint batch 8): onnx.fg + onnx_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: text-form graph export (MLP params, node counts, op list, attention FLOPs); no binary protobuf writer. Portable models.
437. Weight quantization (all) — [HAVE] Verified 21 Nov 2026 (sprint batch 5): quant.fg + quant_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: per-range int8 calibration (scale + zero point, round-half-up, clamp 0..255), quantize/dequantize + max reconstruction error; extends nn.fg's scalar int8 steps. int8 weights.
438. Distributed training (PyTorch) — [GAP] Long-term only; needs a cluster, honestly not a near-term build.
439. Real GPU codegen (CUDA) — [PARTIAL] codegen_cuda emits only a limited subset today.
440. Dataset versioning (DVC) — [HAVE] Snapshots of datasets. Landed 21 Nov 2026 (sprint batch 6): dvc.fg + dvc_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: manifest of "name crc32" lines + change count via re-read; no restore from snapshot; no directory recursion.

## 23. Security (441-460)
441. Memory safety by default (own) — [HAVE] Checked arithmetic, bounds and no null already; keep extending.
442. Fuzz-tested stdlib (Rust) — [GAP] Fuzz every parser.
443. Constant-time crypto operations (all) — [HAVE] No timing leaks. Landed 21 Nov 2026 (sprint batch 6): ct.fg + ct_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: XOR-accumulated comparison with no early exit (ct_equal over [int], ct_equal_str over strings); length mismatch decided up front.
444. Secrets handling (all) — [HAVE] Zeroing buffers and never logging secrets. Landed 21 Nov 2026 (sprint batch 6): secrets.fg + secrets_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: secret stored as char codes, redacts to fixed "***", secret_zero clears contents (length survives); no secure memory.
445. Sandboxing flags (Deno) — [HAVE] Permission flags for file and network access. Landed 21 Nov 2026 (sprint batch 6): perms.fg + perms_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: read/write/net flags + path-root prefix checks (policy object; enforcement in callers, no runtime sandbox); network is one flag, not per-host.
446. Input validation framework (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 5): valid2.fg + valid2_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: email shape, http(s) URL shape, enum membership, float range, trim + space-collapse sanitize; ASCII only, no DNS or RFC corners. Validators for untrusted data.
447. Injection-safe queries (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 5): paramq.fg + paramq_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: ? placeholders only, int params raw, string params quoted with single quotes doubled; no named parameters, no SQL engine. Parameterized queries only.
448. Auto-escaping templates (all) — [HAVE] XSS-safe output by default. Landed 21 Nov 2026 (sprint batch 6): esc.fg + esc_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: escapes values and {{#each}} items via t2_escape before rendering; same engine limits as template2 (no nesting, no {{else}}); HTML entities only.
449. CSRF tokens (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 5): csrf.fg + csrf_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: seed-based deterministic tokens (rand.fg LCG, 31-char alphabet, no lookalikes), verify re-derives and compares every character; seed must stay server-side, no expiry. Web form protection.
450. Password hashing (bcrypt/argon2) — [HAVE] Landed 21 Nov 2026 (sprint batch 5): pwhash.fg + pwhash_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: iterated SHA-256 only (100 rounds over password + ':' + salt) — NOT bcrypt/argon2 and not memory-hard; caller-supplied salts. Proper password storage.
451. JWT issue and verify (all) — [HAVE] Verified 21 Nov 2026 (sprint batch 5): jwt.fg + jwt_demo.fg already in the tree, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: HS256 sign + verify over HMAC-SHA256 (hashlib.fg), base64url without padding; no expiry or claim validation. Token handling.
452. TLS certificate verification (all) — [GAP] Cert validation; ties to TLS itself.
453. Dependency pinning with hashes (all) — [HAVE] Lockfile hashes. Landed 21 Nov 2026 (sprint batch 6): lock.fg + lock_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: "name==version #hash" lines (format/parse/check); hash caller-supplied (sha256_hex demo over "hello"); no lockfile reading.
454. Signed releases (Sigstore) — [HAVE] Landed 21 Nov 2026 (sprint batch 8): signrel.fg + signrel_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: symmetric key only, FNV-1a checksum rendered as sig-<decimal> (a checksum, not cryptographic proof); no public-key crypto, no transparency log. Signed artifacts.
455. SBOM generation (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 5): sbom.fg + sbom_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: CycloneDX 1.5 JSON from a package list (name/version/license id); no hashes, dependencies or SPDX expressions. Software bill of materials.
456. Vulnerability feeds (all) — [HAVE] Alerts for bad dependencies. Landed 21 Nov 2026 (sprint batch 6): vuln.fg + vuln_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: exact (name, version) feed matches; no version ranges; feed is caller-supplied data, not a live feed.
457. Safe deserialization (all) — [HAVE] Never evaluate data as code. Landed 21 Nov 2026 (sprint batch 6): safedeser.fg + safedeser_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: max-length + max-bracket-depth limits enforced before j2_parse (rejected docs return root -1); genuinely malformed JSON still fails loudly inside j2_parse by design; braces in strings count toward depth.
458. CORS handling (web) — [HAVE] Landed 21 Nov 2026 (sprint batch 5): cors.fg + cors_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: exact origin matches only (no wildcards or suffix patterns); Allow-Origin echo + Allow-Methods preflight text, no credentials flag. Cross-origin rules.
459. Content Security Policy helpers (web) — [HAVE] Landed 21 Nov 2026 (sprint batch 5): csp.fg + csp_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: builds the header from caller-supplied directive/value lists; no validation, no nonce generation. Header generation.
460. Threat-model documentation (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 11): forge_lang/stdlib/threat.fg — threat-model table (feature, threat, mitigation, residual risk), worst-risk ranking (80/80 checks both compilers, replica 20/20).

## 24. Metaprogramming (461-480)
461. Macros (Rust/Goboscript) — [GAP] The named post-OS slice; the Goboscript borrow.
462. Compile-time execution (Zig) — [GAP] comptime blocks.
463. Derive attributes (Rust) — [GAP] Auto-derived traits.
464. Reflection (Java/Go) — [HAVE] Landed 21 Nov 2026 (sprint batch 11): forge_lang/stdlib/reflect.fg — runtime type information registry (kind, comma-joined fields, field count, has_field) (80/80 checks both compilers, replica 20/20).
465. Annotations / attributes (Java/Rust) — [HAVE] Landed 21 Nov 2026 (sprint batch 11): forge_lang/stdlib/annot.fg — #[...] metadata rows (declaration, key, value) with lookup and key listing (80/80 checks both compilers, replica 20/20).
466. Conditional compilation (Rust cfg) — [HAVE] Landed 21 Nov 2026 (sprint batch 11): forge_lang/stdlib/cfg.fg — target descriptor (os, arch, mode) plus feature flags; os=/arch=/mode=/feat=/not: predicates with all/any (80/80 checks both compilers, replica 20/20).
467. Generic specialization (Rust) — [HAVE] Landed 21 Nov 2026 (sprint batch 9): forge_lang/stdlib/genspec.fg — per-type specialized names (`max_int`), registry lookup, specialized-vs-generic path (84/84 checks both compilers, replica 21/21).
468. Source generators (C#) — [HAVE] Landed 21 Nov 2026 (sprint batch 9): forge_lang/stdlib/srcgen.fg — annotation-driven builder generation from Qasida source (`// @gen builder` → Builder struct + with_* setters + build()), distinct from #477 schemagen (which generates structs from .proto schemas) and from #463 derive attributes (not built here) (84/84 checks both compilers, replica 21/21).
469. Type-level metaprogramming (C++) — [HAVE] Landed 21 Nov 2026 (sprint batch 9): forge_lang/stdlib/typemeta.fg — recursive type-level expression evaluator: add/sub/mul on type-level naturals, len of type lists, if by type-level bool, eq (84/84 checks both compilers, replica 21/21).
470. Hygienic macros (Scheme) — [GAP] Capture-free expansion.
471. Procedural macros (Rust) — [GAP] AST-transforming macros.
472. Const evaluation (Rust/Zig) — [HAVE] Landed 21 Nov 2026 (sprint batch 10): forge_lang/stdlib/consteval.fg — integer const folds: binary ops, unary neg, left-to-right chains (div-by-zero folds to 0) (80/80 checks both compilers, replica 20/20).
473. Type-level numbers (Haskell) — [GAP] Sizes carried in types.
474. Custom compiler passes (Rust) — [HAVE] Landed 21 Nov 2026 (sprint batch 9): forge_lang/stdlib/ccpass.fg — user lint/optimization passes as data (substring and max-length kinds, severity, per-line violations) (84/84 checks both compilers, replica 21/21).
475. Rich documentation generation (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 8): docgen2.fg + docgen2_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: single-level [#name] anchors, [[name]] rewritten for known names only (unknown names left visible); no section numbering. Examples and cross-links over docgen.fg.
476. FFI binding generation (bindgen) — [HAVE] Landed 21 Nov 2026 (sprint batch 8): ffibind.fg + ffibind_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: one declarator per line, no pointers except char*, no const/unsigned/struct types, no varargs; output is generated text, not compiled code. Auto-generate bindings from C headers.
477. Schema-first codegen (protobuf) — [HAVE] Landed 21 Nov 2026 (sprint batch 8): schemagen.fg + schemagen_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: flat messages only (no nesting/repeated/enum/oneof), field-number uniqueness check; output is struct text, not compiled code. Generate code from .proto files.
478. Stable AST API for tools (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 9): forge_lang/stdlib/astapi.fg — line-based fn/struct/let nodes (kind, name, line), find by name, format, whole-word rename across lines (84/84 checks both compilers, replica 21/21).
479. User-defined syntax (all) — [GAP] Extend the grammar safely.
480. Staged compilation (MetaOCaml) — [GAP] Multi-stage programs.

## 25. Ergonomics and syntax (481-500)
481. Pipe operator (Elixir/F#) — [GAP] x |> f |> g chains.
482. Optional chaining (JS/Swift) — [GAP] a?.b that stays safe on missing values.
483. Null-coalescing for Option (C#/Swift) — [GAP] a ?? default.
484. Destructuring (JS/Rust) — [GAP] let (x, y) = pair.
485. Spread and rest (JS) — [GAP] ...args in calls and literals.
486. Chained comparisons (Python) — [GAP] 0 < x < 10.
487. Implicit returns (Rust) — [GAP] The last expression is the return value.
488. Block expressions (Rust) — [GAP] { ...; value } used as a value.
489. Semicolon-optional style (Go/Swift) — [GAP] A low-priority style choice; only if it never hides errors.
490. Trailing commas (all) — [GAP] Allow trailing commas in lists and calls.
491. Doc comments (Rust) — [HAVE] Landed 21 Nov 2026 (sprint batch 8): doccomment.fg + doccomment_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: fn lines only, /// runs directly above the fn, multi-line docs join with a single space. /// comments that feed docgen.
492. TODO and FIXME tracking (all) — [HAVE] Landed 21 Nov 2026 (sprint batch 8): todotrack.fg + todotrack_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: TODO/FIXME only, substring match anywhere in the line, first marker wins per line; no assignee/date parsing. Collect markers across the tree.
493. Fluent multi-line chains (Kotlin) — [GAP] Readable chained calls.
494. Shadowing (Rust) — [GAP] let x = x + 1 rebinding; needs a rule change, since same-scope let repeats are rejected today.
495. Inline type ascription (Rust) — [GAP] x: Type annotations where inference needs help.
496. Underscore for unused bindings (all) — [GAP] _ prefix silences unused warnings.
497. Case-style lints (Rust) — [HAVE] Landed 21 Nov 2026 (sprint batch 8): casestyle.fg + casestyle_demo.fg, verified 4/4 checks (rc=0 + exact stdout, hosted + python compilers). v1 limits: ASCII letters only; snake_case = lower/digit/single _; CamelCase = UpperCamelCase with at least one lowercase; no acronym rules, no auto-fix. snake_case and CamelCase enforcement.
498. Import aliasing (Python/Go) — [HAVE] Landed 21 Nov 2026 (sprint batch 11): forge_lang/stdlib/alias.fg — import x as y table; same-target re-add is idempotent, a different target records a conflict (first target wins) (80/80 checks both compilers, replica 20/20).
499. Re-exports (Rust) — [HAVE] Landed 21 Nov 2026 (sprint batch 11): forge_lang/stdlib/reexport.fg — pub use table (module, symbol, origin) with resolution and per-module symbol listing (80/80 checks both compilers, replica 20/20).
500. Tour and Book rewritten for 1.3.0 (own) — [GAP] The docs catch up with ecall3, hex literals and the new libraries.
