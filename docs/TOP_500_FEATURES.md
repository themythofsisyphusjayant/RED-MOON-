# Top 500 features for The Jal Pari Language

Borrowed from the major programming languages, ranked for Jal Pari's
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
12. Compile-time sized arrays [T; N] (Rust) — [HAVE] Landed 31 Oct 2026 (batch 8, v1): `[T; N]` is a distinct type from `[T]`; a literal must hold exactly N elements (checked at compile time, including the empty-literal case), push is rejected, indexing/len/iteration work like dynamic arrays, and sized arrays work as function parameters, returns, and struct fields. Native verified; big32 and WASM reject sized programs in v1 with named errors. v1 representation is the existing heap array: the size is a type-level contract enforced at construction and preserved because only sized values flow into sized positions — a stack representation is a later slice. Sized arrays over fixed-width element types are rejected like dynamic fixed arrays.
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
22. Allocator as a value (Zig) — [HAVE] Landed 31 Oct 2026 (batch 17, v1): stdlib/allocator.fg, pure Jal Pari with no compiler change — the language support (structs by value, tuple returns, array fields) already exists. One Allocator struct, passed explicitly to functions, never a global, in three kinds over a fixed backing array: bump (next++, free is a no-op), freelist (intrusive free list, freed slots reused first), arena (bump + reset). allocator_alloc returns (-1, a) when full — out-of-memory is a value, not a failure. Single-slot allocation only in v1; contiguous multi-slot blocks and double-free detection are named later slices.
23. defer for scope-exit cleanup (Go/Zig) — [HAVE] Landed 31 Oct 2026 (batch 16, v1): `defer call();` runs at the enclosing block's exit, LIFO within the block — including early returns, breaks, and continues, and loop-body defers run each iteration. Deferred calls are emitted as statements at the exit point, so their arguments evaluate at exit time in v1 (documented). big32 and WASM reject defer programs in v1 with a named error.
24. Arena allocation (Zig/Rust) — [HAVE] Landed 31 Oct 2026 (batch 18, v1): stdlib/arena.fg, pure Jal Pari. A growing region for temporary allocations, distinct from #22's fixed pools: the backing array grows by push on demand, so alloc never fails with -1; individual frees are no-ops; the whole region is reclaimed by reset, or rewound to a checkpoint by mark/restore — the phase pattern (mark, allocate freely, restore) frees a phase's temporaries at once. Single-slot allocation only in v1. This batch also fixed two real compiler ownership bugs the arena exposed: push on a shared array now copies-on-write instead of reallocating the shared buffer (which left other holders dangling), and field assignment now mirrors plain assignment's ownership (temp-first, own the new value, free the old) for array and struct fields.
25. Reference counting (Swift) — [HAVE] Landed 1 Nov 2026 (batch 19, v1): a `refcount(arr)` builtin that reads an array's live holder count without gaining a holder, plus stdlib/rc.fg — Rc as shared ownership over an array (clone gains a holder, dropping one loses one, the last drop frees; mutation through any holder is visible to all). Counts verified by hand: 1 after rc_new, 2 after rc_clone, shared mutation visible (99), len 2. Native-only in v1; big32 and WASM reject refcount programs.
26. Weak references (Swift/Java) — [HAVE] Landed 1 Nov 2026 (batch 20, v1): runtime weak table for [int] arrays — weak_new registers without gaining a holder, weak_upgrade returns (alive, array) with the current buffer while any strong holder lives (push syncs the moved buffer; copy-on-write push correctly leaves the weak on the original), (false, []) after the last strong holder's scope ends. Native-only in v1; big32 and WASM reject weak programs. V1 limit: the table itself is never freed (one entry per weak_new, no user data).
27. Move semantics (Rust/C++) — [HAVE] Landed 1 Nov 2026 (batch 21, v1): move(a) transfers the one hold instead of copying — the destination's refcount stays 1 and the source is dead afterwards (any later use is a checker error). Fresh + forget in the native codegen: the move is fresh for arrays, str, structs and tuples, and the source's owned entry is forgotten so scope-end frees skip it. V1 limits: moves only in straight-line code (moves in branches and loops are rejected — the free tracking is compile-time, so a path-dependent move would leak or double-free on the untaken path; runtime moved flags are the later slice that unlocks branch moves); identifiers only, no field moves. Native-only in v1; big32 and WASM reject move programs.
28. Copy-on-write arrays (Swift) — [PARTIAL] Landed 1 Nov 2026 (batch 22, v1, opt-in): stdlib/cow.fg, pure Jal Pari — a Cow shares its buffer until a write (the writer gets a private copy when shared, writes in place when sole; the sharing test uses refcount before any local copy, since a local copy would inflate the count). Plain arrays keep their specified shared-mutation behavior. What remains (NOT taken): language-default CoW, where every index assignment CoWs — that would break Rc's shared-mutation promise and existing shared-mutation programs, so it needs an explicit decision.
29. Stack-allocated slices (Go/Rust) — [HAVE] Landed 1 Nov 2026 (batch 23, v1): stdlib/slice.fg, pure Jal Pari — a Slice is a stack-allocated header {arr, off, len} over an existing array's buffer: no new allocation, the slice keeps the buffer alive, reads and writes go through the shared buffer (visible via the original), bounds are the slice's own, and slicing a slice composes. V1 is [int]-only; str slices need a str-view type.
30. Lifetime-ordered placement (QAIRT) — [HAVE] Landed 1 Nov 2026 (batch 24, v1): stdlib/lifetime.fg, pure Jal Pari — this promotes the kernel's lifetime-ordered allocator to a stdlib API. One backing array, two regions: shorts bump from the front, longs from the back; one reset frees all shorts while longs survive untouched; out-of-memory is a value (-1). Fixed backing, two lifetime classes in v1.
31. Memory-mapped files (Python/C) — [HAVE] Landed 1 Nov 2026 (batch 25, v1): runtime mmap table + mmap_open/mmap_get/mmap_set/mmap_close builtins (bytes, native only, POSIX; Windows stubs fail cleanly). Writes go through MAP_SHARED into the file itself (proven: 'H' -> 'J' in the mapping re-reads as 'J' from the file). This batch also fixed two real pre-existing leaks its demo exposed: read_bytes results were not marked fresh (every let of one leaked a ref) and write_bytes never consumed its param hold (every call leaked its input array). Known follow-up, not hidden: other C helpers taking str/array params have the same unconsumed-param shape — an audit item, not fixed here.
32. Allocator-aware collections (C++/Zig) — [PARTIAL] Arrays take an allocator argument (AVec over the #22 Allocator: bump vs freelist growth is observable; OOM is a value). Maps are the next slice — their string keys cannot live in an [int]-backed allocator.
33. Destructor hooks (C++/Rust Drop) — [HAVE] Landed 1 Nov 2026 (batch 27, v1): a struct method named `drop` (receiver only, void return) runs automatically when an owned binding dies — block end, function end, return path, break — firing before the free so fields are still live, via an independently owned copy (the call-arg pattern). The drop method's own receiver parameter never hooks (that would recurse forever — caught by the first demo run). V1 limits: per-binding, not per-value (copies drop per binding; use move() for exactly one drop); nested drops (struct fields, array elements) do not run; union/opaque-field structs are not hooked (owning gap); generics skipped; native only (big32/WASM/freestanding reject).
34. Pinning / immovable values (Rust) — [GAP] For self-referential kernel structs.
35. Zeroing on free (Zig) — [GAP] Security default for sensitive buffers.
36. Allocation failure as a value (Rust) — [GAP] Out-of-memory becomes a Result, not a crash.
37. Pool allocators (C) — [GAP] Fixed-size object pools for drivers.
38. Stack-usage diagnostics (Rust) — [GAP] Report max frame size per function; kernels care, frames are 2048 bytes today.
39. No implicit heap allocation in freestanding mode (Zig) — [PARTIAL] The freestanding flag exists; enforce the rule at compile time.
40. Use-after-move checking (Rust) — [GAP] Checker-level only, no borrow checker needed.

## 3. Errors (41-60)
41. Error values as the default path (Go/Rust) — [HAVE] Result already is; never add exceptions as the main path.
42. Error wrapping with context (Go/Rust anyhow) — [GAP] "while reading X: ..." chains.
43. Multi-error accumulation (Rust/Go validators) — [GAP] Collect every error, not just the first.
44. Panic vs recover boundary (Go) — [GAP] fail() stays fatal; recovery only at task boundaries.
45. Assertions with messages (all) — [HAVE] assert exists; add assert_eq-style diffs.
46. Error codes as enums (C/Zig) — [GAP] Typed errno-style errors for syscalls.
47. Backtraces on fail in debug builds (Rust) — [GAP] Native backtrace, stripped in release builds.
48. try/catch as opt-in only (Java/C++) — [GAP] Deliberately narrow: module boundaries only, never control flow.
49. Result combinators: map/flatMap/orElse (Rust) — [GAP] Chain Results without nesting.
50. Inferred error sets (Zig) — [GAP] The checker works out which errors a function can return.
51. Deferred error logging (Go) — [GAP] Log-on-return helpers.
52. Timeout errors as values (Go) — [GAP] Deadline-exceeded is data, not a crash.
53. Validation error types (Python pydantic) — [GAP] Field-level error lists.
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
75. Iterator protocol (Go/Rust) — [GAP] A standard way to walk collections.
76. Wildcard match arm (Rust _) — [GAP] A default arm for match.
77. Nested function definitions (Python) — [GAP] Helpers scoped inside functions.
78. Tail-call guarantee (Scheme/Erlang) — [GAP] Recursion without stack growth for state machines.
79. State-machine syntax (Erlang/Rust) — [GAP] Explicit states and transitions for drivers.
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
90. Scheduler policies as libraries (Linux) — [PARTIAL] Round-robin exists; add priority, EDF and lottery policies.
91. Typed IPC channels (Unix) — [PARTIAL] A ring IPC kernel exists; raise it to language channels.
92. Signals / software interrupts (Unix) — [GAP] Kill and notify tasks.
93. Capability handles (seL4) — [GAP] Unforgeable handles for devices and files.
94. Full SBI call set (RISC-V) — [PARTIAL] The SBI demo exists; finish with the a6-carrying call after ecall3.
95. ELF loading (Unix) — [GAP] Load programs from the filesystem.
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
115. Memoization (Python) — [GAP] Cache pure results automatically.
116. Function composition (Haskell) — [GAP] f after g as a single value.
117. Recursion depth limits (Erlang) — [GAP] Configurable stack-safe recursion.
118. Anonymous structs (Go/Zig) — [GAP] Struct literals without a named type.
119. Numeric generics (Rust) — [PARTIAL] Generics exist; add numeric traits for math code.
120. Const functions (Rust/Zig) — [GAP] Functions runnable at compile time.

## 7. Collections (121-140)
121. Hash maps (all) — [PARTIAL] Linear assoc lists exist in the map library; real hashing is missing.
122. Sets (all) — [PARTIAL] Int and string sets exist; generic sets do not.
123. Deques (Python/Rust) — [GAP] Double-ended queues.
124. Priority queues / heaps (all) — [GAP] Ordered-by-priority removal.
125. Insertion-ordered maps (Java/Python) — [GAP] Iteration in insertion order.
126. Slicing syntax (Rust/Go) — [HAVE] Bounds-checked indexing exists; add a[1..3] slices.
127. Dict literals (Python/JS) — [GAP] {"a": 1} syntax.
128. Array comprehensions (Python/Haskell) — [GAP] [f(x) for x in xs].
129. Sorting with comparators (all) — [GAP] sort_by with a function value.
130. Binary search (all) — [GAP] Search over sorted arrays.
131. zip / enumerate adapters (Python/Rust) — [GAP] Pair up and number iterations.
132. Grouping / partitioning (Kotlin/Rust itertools) — [GAP] Split collections by a key.
133. Persistent immutable collections (Clojure) — [GAP] Structural sharing for safe sharing.
134. Bitsets (Java/Rust) — [GAP] Compact flag sets.
135. Bloom filters (Guava) — [GAP] Probabilistic membership tests.
136. LRU caches (all) — [GAP] Bounded caches with eviction.
137. Ring buffers (embedded) — [PARTIAL] A ring IPC kernel exists; add a stdlib ring type.
138. Sparse arrays (SciPy) — [GAP] For ML data with mostly zeros.
139. True multi-dimensional arrays (NumPy) — [PARTIAL] The numpy library is flat row-major; add real ndim indexing.
140. Window / chunk iterators (Rust) — [GAP] Sliding views over arrays.

## 8. Strings and text (141-160)
141. String interpolation (Swift/Kotlin/Python f-strings) — [GAP] "hello {name}".
142. Multiline strings (all) — [GAP] Triple-quote blocks.
143. Raw strings (Rust/Go) — [GAP] r"..." without escape processing.
144. Unicode-correct length and iteration (Rust/Swift) — [GAP] Grapheme clusters, not bytes.
145. Regex groups and alternation (all) — [PARTIAL] The regex library lacks both; the known gap.
146. String builders (Java/C#) — [GAP] Efficient repeated concatenation.
147. Format specifiers (Python/Rust) — [GAP] {x:.2f}, padding and alignment.
148. Case conversion (all) — [GAP] snake, camel and kebab conversion.
149. Split with limits and regex split (all) — [HAVE] split/join/trim builtins exist; extend them.
150. Full template engine (Jinja/Go) — [PARTIAL] A template library exists; grow it to a full engine.
151. Text encodings UTF-8/16/32 (all) — [GAP] Encode and decode with validation.
152. Line-oriented streaming (Go bufio) — [GAP] A scanner for large files.
153. Unified diff output (Python difflib) — [PARTIAL] A difflib library exists; add unified diff format.
154. Markdown parsing to AST (all) — [PARTIAL] markdown-lite renders to text only.
155. CSV parsing and generation (all) — [PARTIAL] Parse and load exist; add quoted fields and generation.
156. JSON string escaping (all) — [GAP] Correct escape and unescape.
157. Terminal-width-aware wrapping (all) — [PARTIAL] A textwrap library exists; make it width-aware.
158. Slugify — [HAVE] The slugify library already does this; keep it.
159. Sentence splitting and stemming (NLTK) — [PARTIAL] An nlp-words library exists; extend it.
160. Full pluralization rules (Rails) — [PARTIAL] i18n-lite has plural-lite only.

## 9. Numerics (161-180)
161. Complex numbers as a numeric type (Python) — [HAVE] A complex library exists; promote it toward builtin status.
162. Rational arithmetic (Python) — [HAVE] A fractions library exists.
163. Big integers (Python/Java) — [GAP] Arbitrary precision integers.
164. Decimal arithmetic (Python) — [PARTIAL] A money library uses integer cents; add a decimal type.
165. Vector and matrix types (NumPy/Julia) — [PARTIAL] The numpy library is flat arrays; add native vector ops.
166. SIMD operations (Mojo/Rust) — [PARTIAL] parallel_dot and parallel_matmul exist; add an explicit SIMD API.
167. Probability distributions (SciPy) — [PARTIAL] A statistics library exists; add normal, Poisson and friends.
168. Random distributions (NumPy) — [GAP] Normal, uniform and exponential sampling.
169. FFT — [HAVE] The fft library already does radix-2 plus inverse.
170. Linear algebra solvers (NumPy) — [GAP] Solve, decompositions and eigenvalues.
171. Gradient-free optimization (SciPy) — [PARTIAL] An optimization library exists; add Nelder-Mead and friends.
172. Polynomials — [HAVE] The polynomials library already exists.
173. Interpolation (SciPy) — [GAP] Linear and cubic splines.
174. Numeric integration and differentiation (SciPy) — [GAP] Calculus over sampled functions.
175. Special functions erf and gamma — [HAVE] The mathex library already has them.
176. Fixed-point arithmetic (embedded) — [GAP] Deterministic fractional math for kernels.
177. Compile-time unit checking (F#) — [PARTIAL] A units library exists; check units at compile time.
178. Rounding mode control (IEEE) — [GAP] Floor, ceil and banker's rounding as a choice.
179. Documented NaN/Infinity semantics (IEEE) — [GAP] Write down the float rules.
180. Identical floats across backends (Rust) — [GAP] Same results native, WASM and big32.

## 10. Files and I/O (181-200)
181. mkdir and readdir (POSIX) — [GAP] The known missing pair.
182. Full path manipulation (all) — [PARTIAL] A POSIX pathlib library exists; add join, normalize and glob.
183. File watching (inotify) — [GAP] React to file changes.
184. Temporary files and directories (all) — [GAP] Safe temp creation.
185. File locking (POSIX) — [GAP] flock-style locks.
186. Buffered readers and writers (Go/Java) — [GAP] Buffered I/O for speed.
187. Atomic file replace (all) — [GAP] Write-temp-then-rename.
188. Symlink handling (POSIX) — [GAP] Read and create symlinks.
189. Permissions API (POSIX) — [GAP] chmod, chown and stat modes.
190. Recursive directory walking (Python os.walk) — [GAP] Walk a tree.
191. Glob patterns (all) — [GAP] *.fg matching.
192. Standard streams stdin/stderr (all) — [PARTIAL] print exists; add stdin reading and stderr writes.
193. Binary I/O with endianness (all) — [GAP] Read and write little- and big-endian ints.
194. Compact binary serialization (Rust) — [GAP] A bincode-style format.
195. Layered configuration loading (all) — [PARTIAL] Config, toml, ini and dotenv libraries exist; layer them.
196. Log rotation (all) — [GAP] Size- and time-based rotation.
197. Tar and zip archives (all) — [GAP] Read and write archives.
198. Checksum-verified reads (all) — [PARTIAL] A checksum library exists; verify on load.
199. Non-blocking file I/O (Node) — [GAP] Async reads.
200. Append-only journals (etcd) — [GAP] Change logs for files.

## 11. Networking (201-220)
201. TCP and UDP sockets (all) — [GAP] Raw sockets are the known missing piece.
202. TLS (all) — [GAP] Encrypted sockets.
203. HTTP/2 and HTTP/3 (Go) — [GAP] Modern transports.
204. WebSockets (all) — [GAP] Bidirectional streams.
205. DNS resolution (all) — [GAP] Name to address.
206. URL parsing and building — [HAVE] The url library already does this.
207. HTTP client methods and cookies (all) — [HAVE] http_get exists; add methods, headers, redirects and cookies.
208. HTTP server routing and middleware (all) — [HAVE] http_listen and friends exist; add routing and middleware.
209. REST client helpers (all) — [GAP] JSON-in, JSON-out calls.
210. gRPC and protobuf RPC (Go) — [GAP] Typed remote calls.
211. MQTT and AMQP messaging (all) — [GAP] Publish and subscribe protocols.
212. Connection pooling (all) — [GAP] Reuse sockets.
213. Retries with backoff in the client — [HAVE] A retry-backoff library exists; wire it into the HTTP client.
214. Rate limiting (all) — [GAP] Token buckets.
215. Proxy support on servers (all) — [HAVE] CONNECT proxy exists in http_get; extend it to servers.
216. IPv6 (all) — [GAP] Version 6 addresses and dual-stack.
217. Network interface listing (all) — [GAP] Enumerate network cards.
218. Packet capture (libpcap) — [GAP] Raw packet reading.
219. NAT traversal / STUN (WebRTC) — [GAP] Peer-to-peer setup.
220. Service discovery (Consul) — [GAP] Register and find services.

## 12. Data formats (221-240)
221. Full JSON parse and generate (all) — [PARTIAL] json_get and json_make exist only; add real parsing.
222. YAML (all) — [GAP] A YAML reader and writer.
223. TOML — [HAVE] A toml subset library already exists.
224. INI — [HAVE] An ini library already exists.
225. XML — [PARTIAL] An xml-lite library exists.
226. Protocol Buffers (Google) — [GAP] Schema-driven binary encoding.
227. MessagePack and CBOR (all) — [GAP] Compact binary JSON-like formats.
228. Base64 — [HAVE] The base64 library already exists.
229. Hex encode and decode — [HAVE] Hex support already exists beside base64.
230. URL encoding — [HAVE] The url library already covers it.
231. HTML parsing (all) — [GAP] DOM-style parsing.
232. SQL query building (all) — [PARTIAL] A mini SQL query library exists; add safe query construction.
233. Data validation schemas (JSON Schema) — [GAP] Validate shapes of data.
234. Versioned data migrations (Rails) — [GAP] Schema migration steps.
235. Binary struct packing (Python struct) — [GAP] Pack and unpack C structs; ties to FFI layout.
236. Real compression codecs (all) — [PARTIAL] The compress library is RLE only; add gzip and deflate.
237. Checksums inside file formats (all) — [PARTIAL] A checksum library exists; use it in formats.
238. dotenv files — [HAVE] A dotenv library already exists.
239. iCalendar — [HAVE] An ical-lite library already exists.
240. RSS and Atom feeds (all) — [GAP] Feed parsing.

## 13. Concurrency (241-260)
241. M:N lightweight tasks (Go) — [PARTIAL] spawn exists; add a real scheduler over it.
242. Typed channels (Go) — [GAP] Message passing between tasks; the kernel ring is not yet a language channel.
243. Mutexes and read-write locks (all) — [GAP] The known missing thread primitives.
244. Atomics (all) — [GAP] Atomic integers for lock-free code.
245. Thread pools (all) — [GAP] Worker pools.
246. Futures and promises (JS/Rust) — [GAP] Values that resolve later.
247. Structured scopes with cancellation — [HAVE] scope exists; add cancellation to it.
248. Cancellation tokens (C#/Go context) — [GAP] Cooperative cancellation.
249. Operation timeouts (Go) — [GAP] Deadline propagation.
250. Parallel iterators (Rayon) — [GAP] par_map over collections.
251. Work-stealing schedulers (Go/Ray) — [GAP] Balanced parallelism.
252. Actor model (Erlang/Akka) — [GAP] Isolated actors with mailboxes.
253. Software transactional memory (Haskell/Clojure) — [GAP] Atomic multi-value updates.
254. Read-copy-update (Linux) — [GAP] Lock-free reads.
255. Barriers and latches (Java) — [GAP] Rendezvous points for tasks.
256. Semaphores (all) — [GAP] Counting permits.
257. Condition variables (all) — [GAP] Wait and notify.
258. Deadlock detection (Go) — [GAP] Runtime cycle checks.
259. Data-race detector (Go/TSan) — [GAP] Find races in tests.
260. Deterministic concurrency testing (Rust loom) — [GAP] Explore schedules on purpose.

## 14. Async and events (261-280)
261. async/await syntax (JS/Rust/C#) — [GAP] The flagship missing feature.
262. Event loops (Node/libuv) — [GAP] A single-threaded async runtime.
263. Runtime timers (JS) — [PARTIAL] A timers library exists; add real runtime timers.
264. Backpressured streams (Node) — [GAP] Readable and writable flows.
265. Observables / reactive streams (Rx) — [GAP] Push-based composition.
266. Select over channels (Go) — [GAP] Wait on many channels at once.
267. Async iterators (JS) — [GAP] for-await loops.
268. Promise combinators: all and race (JS) — [GAP] Combine async values.
269. Non-blocking file and network APIs (Node) — [GAP] Async variants of I/O.
270. Coroutine cancellation (Kotlin) — [GAP] Structured cancel for async work.
271. Task groups (Swift) — [GAP] Collections of spawned tasks.
272. Debounce and throttle (JS) — [GAP] Rate-shaped handlers.
273. Event emitters (Node) — [GAP] on/emit publish-subscribe.
274. Signal handling in async runtimes (Tokio) — [GAP] Graceful shutdown.
275. Backpressure strategies (Akka) — [GAP] Drop, buffer or keep-latest.
276. Async traits (Rust) — [GAP] Async functions in interfaces.
277. Green threads (Erlang) — [GAP] Ultra-light tasks.
278. I/O multiplexing: epoll/kqueue (Linux) — [GAP] Scalable readiness checks.
279. Timer wheels (Linux) — [GAP] Efficient scheduling of many timers.
280. Async HTTP handlers (FastAPI) — [GAP] Async routes for servers.

## 15. FFI and interop (281-300)
281. C struct layout compatibility (C) — [GAP] Match C field offsets; the known packing issue.
282. Callbacks from C into Jal Pari (C) — [HAVE] extern FFI exists for calling out; add callbacks coming back in.
283. C++ interop (Swift) — [GAP] Name-mangled calls.
284. Python interop (Mojo) — [GAP] Call Python from Jal Pari and back.
285. WASM component model encoding (WASI) — [PARTIAL] WIT-first contract checking exists; add real component encoding.
286. Node.js native addons (N-API) — [GAP] Jal Pari as a Node module.
287. Java JNI (Java) — [GAP] JVM interop.
288. Go-style foreign calls (Go) — [GAP] Call Go code.
289. Safe wrappers over unsafe C (Rust) — [GAP] Checked wrappers for C APIs.
290. Win32 bindings (C#) — [GAP] Windows APIs; ties to the Windows port.
291. Objective-C interop (Swift) — [GAP] Apple APIs.
292. Stable module ABI (Swift) — [GAP] Binary compatibility promises.
293. Bit-exact float passing (all) — [GAP] Float calling-convention rules.
294. String marshalling (all) — [GAP] UTF-8 across boundaries.
295. Callback lifetimes (all) — [GAP] Keep callbacks alive as long as C holds them.
296. Dynamic loading: dlopen (C) — [GAP] Load shared libraries at runtime.
297. Plugin systems (all) — [GAP] Loadable extensions.
298. C header generation (cbindgen) — [GAP] Emit C headers for Jal Pari libraries.
299. Zero-copy serialization (Cap'n Proto) — [GAP] IPC without copying.
300. Cross-language hover (all) — [GAP] Editor support across FFI boundaries.

## 16. Testing (301-320)
301. Rich unit-test framework (all) — [PARTIAL] forge test plus a test library exist; add fixtures and richer asserts.
302. Property-based testing (Hypothesis/QuickCheck) — [GAP] Generated cases with shrinking.
303. Coverage-guided fuzzing (Rust cargo-fuzz) — [GAP] Fuzz inputs by coverage.
304. Benchmark harness (Go/Rust) — [GAP] Timing with statistics; the bench item already queued.
305. Test coverage (all) — [GAP] Line and branch coverage.
306. Mocking (all) — [GAP] Fake dependencies.
307. Snapshot testing (Jest) — [GAP] Golden outputs.
308. Parameterized tests (pytest) — [GAP] One test, many inputs.
309. Test doubles: stubs and spies (Mockito) — [GAP] Stand-ins with recorded calls.
310. Integration test harness (all) — [GAP] Multi-process tests.
311. Deterministic test time (Go) — [GAP] Fake clocks for time tests.
312. Test parallelization (Go) — [GAP] Run tests concurrently.
313. Flaky test detection (all) — [GAP] Rerun and quarantine unstable tests.
314. Mutation testing (Stryker) — [GAP] Prove tests by killing mutants.
315. Contract testing (Pact) — [GAP] Consumer-driven contracts.
316. Load testing (k6) — [GAP] HTTP load generation.
317. Kernel model tests — [HAVE] The model-test pattern already exists; automate the SOC2 bench side too.
318. Golden-file codegen tests (Rust) — [GAP] Expected assembly snapshots.
319. JUnit XML reporting (all) — [GAP] CI-friendly test output.
320. Doctests (Rust/Python) — [GAP] Tests inside doc comments.

## 17. Build and packages (321-340)
321. Package manager with a public host (Cargo/npm) — [PARTIAL] A 30-package registry exists with no host; add hosting plus version resolution.
322. Semantic versioning enforcement (Cargo) — [PARTIAL] A semver library exists; enforce resolver rules.
323. Lockfiles (Cargo/npm) — [GAP] Reproducible builds.
324. Workspaces / monorepos (Cargo) — [GAP] Multi-package repositories.
325. Build profiles: dev and release (Cargo) — [GAP] Debug vs optimized builds.
326. Cross-compilation triples (Rust/Go) — [PARTIAL] Native, WASM, big32 and CUDA targets exist; add triples and sysroots.
327. Incremental compilation (Rust) — [GAP] Rebuild only changed modules.
328. Build caching (Bazel) — [GAP] Cached artifacts.
329. Vendoring (Go) — [GAP] Offline dependency copies.
330. Dependency auditing (cargo-audit) — [GAP] Known-vulnerability scanning.
331. License policy checks (cargo-deny) — [GAP] Allowed-license enforcement.
332. Registry publishes (PyPI/npm) — [GAP] The his-click publishes: PyPI, Marketplace, Pages.
333. Checksum-verified install (all) — [HAVE] install.sh exists; add checksum verification.
334. Prebuilt binary releases (GoReleaser) — [GAP] Binaries per platform.
335. Container images (all) — [GAP] A containerized toolchain; deploy files exist, the image is not built.
336. Reproducible dev shells (Nix) — [GAP] Flake-style environments.
337. Task runner files (make/just) — [GAP] Standard task definitions.
338. Feature flags (Cargo) — [GAP] Conditional compilation flags.
339. Build-time code generation (Cargo build.rs) — [GAP] Generate code during builds.
340. Bit-identical reproducible builds (Debian) — [GAP] Same input, same bytes.

## 18. Compiler diagnostics (341-360)
341. Structured error output (Rust) — [GAP] JSON errors for editors.
342. Multi-error reporting (Rust) — [GAP] Report every error, not just the first.
343. "Did you mean" suggestions (all) — [HAVE] The checker already suggests; extend it to every name kind.
344. Long-form error explanations (Rust) — [GAP] E0308-style write-ups.
345. Source snippets in errors (Rust) — [GAP] Caret and context rendering.
346. Warnings vs errors (all) — [GAP] Warn on unused code, deny on demand.
347. Unused-code detection (Goboscript) — [GAP] The named Goboscript borrow, not yet built.
348. Unreachable-code warnings (all) — [GAP] Flag code that can never run.
349. Error minimization (Elm) — [GAP] Shrink to the smallest failing snippet.
350. Auto-fix suggestions (Rust) — [GAP] Apply safe fixes.
351. Lint rules (Clippy/ESLint) — [GAP] Style and correctness lints.
352. Formatter enforcement in CI (all) — [PARTIAL] fmt exists and is idempotent; enforce it in CI.
353. Import organization (Go) — [GAP] Sort and dedupe imports.
354. Complexity metrics (all) — [GAP] Cyclomatic complexity warnings.
355. Unsafe-operation auditing (Rust) — [GAP] List unchecked operations per file.
356. Determinism checks (all) — [GAP] Prove same input gives same output.
357. Compile-time evaluation errors (Zig) — [GAP] Clear comptime failure messages.
358. Macro expansion view (Rust) — [GAP] Show expanded code; needs macros first.
359. Incremental error caching (Rust) — [GAP] Fast re-checks.
360. IDE-grade error recovery (TypeScript) — [GAP] Keep checking after errors.

## 19. Editor and LSP (361-380)
361. Hover types (all LSP) — [GAP] The known LSP gap.
362. Rename symbol (all LSP) — [GAP] The known LSP gap.
363. Go to definition (all LSP) — [PARTIAL] An LSP exists; verify definition coverage.
364. Find references (all LSP) — [GAP] Every use of a symbol.
365. Context-aware completions (all LSP) — [GAP] Suggestions from scope and types.
366. Signature help (all LSP) — [GAP] Parameter hints while typing.
367. Code actions / quick fixes (all LSP) — [GAP] Apply suggestions from the editor.
368. Document symbols / outline (all LSP) — [GAP] File outline view.
369. Format via LSP (all LSP) — [PARTIAL] fmt exists; wire it into the LSP.
370. Semantic highlighting (all LSP) — [GAP] Type-aware colours.
371. Inlay hints (Rust) — [GAP] Inferred types shown inline.
372. Call hierarchy (all LSP) — [GAP] Callers and callees.
373. Type hierarchy (all LSP) — [GAP] Interface implementors.
374. Workspace symbols (all LSP) — [GAP] Search symbols across the tree.
375. Extract-function refactoring (all) — [GAP] Turn a block into a function.
376. Snippets — [HAVE] 16 snippets ship in the VS Code extension; extend them per new feature.
377. Syntax highlighting — [HAVE] A TextMate grammar ships; extend it per new syntax.
378. Debugger protocol support (DAP) — [GAP] Breakpoints and stepping; ties to the debugger gap.
379. REPL with history (all) — [PARTIAL] A repl exists; add multiline input and history.
380. Notebook support (Jupyter) — [GAP] .fg notebooks; ties to the Kaggle work.

## 20. Debugging and observability (381-400)
381. Debugger: breakpoints and stepping (all) — [GAP] The known missing tool.
382. dbg! print debugging (Rust) — [GAP] Value-printing helpers.
383. Logging framework (all) — [PARTIAL] A log library exists; add levels and structured logs.
384. Tracing and spans (OpenTelemetry) — [GAP] Distributed traces.
385. Metrics: counters and gauges (Prometheus) — [GAP] Runtime metrics.
386. CPU profiling (all) — [GAP] A sampling profiler; the profiler item already queued.
387. Memory profiling (all) — [GAP] Allocation tracking beyond the alloc_count builtins.
388. Flame graphs (all) — [GAP] Visualize hot paths.
389. Heap dumps (all) — [GAP] Snapshot analysis.
390. Kernel core dumps (embedded) — [GAP] Post-mortem state for freestanding crashes.
391. Watchpoints (gdb) — [GAP] Break on memory writes.
392. Reverse debugging (rr) — [GAP] Record and replay execution.
393. Live reload (all) — [GAP] Hot code swap for servers.
394. Health endpoints (all) — [GAP] /health for services.
395. Structured crash reports (Sentry) — [GAP] Symbolicated reports.
396. Audit logs (all) — [GAP] Security event trails.
397. Hardware performance counters (Linux perf) — [GAP] CPU counter access.
398. Dynamic tracing probes (Linux eBPF) — [GAP] Attach probes without rebuilding.
399. REPL-driven debugging (all) — [GAP] Inspect live program state.
400. Deterministic replay for tests (all) — [GAP] Reproduce failures exactly.

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
411. Dead-code elimination (all) — [GAP] Remove unreachable functions.
412. Register allocation quality (all) — [GAP] Better than today's scratch-register quirk.
413. Instruction scheduling (all) — [GAP] Order instructions for pipelines.
414. Cache-aware struct layouts (all) — [GAP] Reorder fields for cache lines.
415. String interning (all) — [GAP] Deduplicate constant strings.
416. Small-string optimization (C++) — [GAP] Stack storage for short strings.
417. Zero-cost abstractions (Rust) — [GAP] Abstractions that compile away entirely.
418. Benchmark-driven tuning (all) — [GAP] A bench suite; the bench item already queued.
419. Allocation-free hot paths (Zig) — [GAP] No allocation inside loops.
420. Fast compile speed (Go) — [GAP] Quick rebuilds for big trees.

## 22. ML and data (421-440)
421. First-class tensors (PyTorch/JAX) — [PARTIAL] A tensor library exists; raise it to a real type.
422. Full autograd coverage (PyTorch) — [PARTIAL] tensor_autograd covers 20 ops; finish coverage plus tape freeing, the 0.5.0 unlock.
423. Neural layers: conv, attention, norm (PyTorch) — [PARTIAL] An nn library exists; add the missing layers.
424. Optimizers with state (PyTorch) — [GAP] Adam and SGD with state.
425. Datasets and dataloaders (PyTorch) — [PARTIAL] A dataset library exists; add batching and shuffling.
426. BPE and WordPiece tokenizers (HF) — [PARTIAL] A tokenizer library exists; add real BPE.
427. Full transformer blocks (HF) — [PARTIAL] gpt and gpt2 libraries exist; finish attention plus RoPE.
428. Evaluation metrics suite (all) — [PARTIAL] A metrics library covers accuracy, confusion, PRF, MSE, MAE, R2 and perplexity; grow it into a suite.
429. Eval harness (lm-eval) — [GAP] The eval-harness item already queued.
430. Embeddings (all) — [GAP] The embeddings item already queued.
431. sklearn-lite v2 (scikit-learn) — [PARTIAL] v1 is done; add trees, forests, Bayes, PCA, scaling, pipelines, CV and splits.
432. Dataframes — [HAVE] The pandas library already does flat DataFrames.
433. Plotting (matplotlib) — [GAP] The plot-lite item already queued.
434. SVG generation (all) — [GAP] The svg-gen item already queued.
435. ML run profiling (all) — [GAP] The profiler item already queued.
436. ONNX model export (all) — [GAP] Portable models.
437. Weight quantization (all) — [GAP] int8 weights.
438. Distributed training (PyTorch) — [GAP] Long-term only; needs a cluster, honestly not a near-term build.
439. Real GPU codegen (CUDA) — [PARTIAL] codegen_cuda emits only a limited subset today.
440. Dataset versioning (DVC) — [GAP] Snapshots of datasets.

## 23. Security (441-460)
441. Memory safety by default (own) — [HAVE] Checked arithmetic, bounds and no null already; keep extending.
442. Fuzz-tested stdlib (Rust) — [GAP] Fuzz every parser.
443. Constant-time crypto operations (all) — [GAP] No timing leaks.
444. Secrets handling (all) — [GAP] Zeroing buffers and never logging secrets.
445. Sandboxing flags (Deno) — [GAP] Permission flags for file and network access.
446. Input validation framework (all) — [GAP] Validators for untrusted data.
447. Injection-safe queries (all) — [GAP] Parameterized queries only.
448. Auto-escaping templates (all) — [GAP] XSS-safe output by default.
449. CSRF tokens (all) — [GAP] Web form protection.
450. Password hashing (bcrypt/argon2) — [GAP] Proper password storage.
451. JWT issue and verify (all) — [GAP] Token handling.
452. TLS certificate verification (all) — [GAP] Cert validation; ties to TLS itself.
453. Dependency pinning with hashes (all) — [GAP] Lockfile hashes.
454. Signed releases (Sigstore) — [GAP] Signed artifacts.
455. SBOM generation (all) — [GAP] Software bill of materials.
456. Vulnerability feeds (all) — [GAP] Alerts for bad dependencies.
457. Safe deserialization (all) — [GAP] Never evaluate data as code.
458. CORS handling (web) — [GAP] Cross-origin rules.
459. Content Security Policy helpers (web) — [GAP] Header generation.
460. Threat-model documentation (all) — [GAP] Security notes per feature.

## 24. Metaprogramming (461-480)
461. Macros (Rust/Goboscript) — [GAP] The named post-OS slice; the Goboscript borrow.
462. Compile-time execution (Zig) — [GAP] comptime blocks.
463. Derive attributes (Rust) — [GAP] Auto-derived traits.
464. Reflection (Java/Go) — [GAP] Runtime type information.
465. Annotations / attributes (Java/Rust) — [GAP] #[...] metadata on declarations.
466. Conditional compilation (Rust cfg) — [GAP] Target-gated code.
467. Generic specialization (Rust) — [GAP] Faster paths for specific types.
468. Source generators (C#) — [GAP] Generate code from schemas.
469. Type-level metaprogramming (C++) — [GAP] Computation in the type system.
470. Hygienic macros (Scheme) — [GAP] Capture-free expansion.
471. Procedural macros (Rust) — [GAP] AST-transforming macros.
472. Const evaluation (Rust/Zig) — [GAP] Evaluate expressions at compile time.
473. Type-level numbers (Haskell) — [GAP] Sizes carried in types.
474. Custom compiler passes (Rust) — [GAP] User lints and optimizations.
475. Rich documentation generation (all) — [PARTIAL] docgen exists; add examples and cross-links.
476. FFI binding generation (bindgen) — [GAP] Auto-generate bindings from C headers.
477. Schema-first codegen (protobuf) — [GAP] Generate code from .proto files.
478. Stable AST API for tools (all) — [GAP] Let tools read and rewrite programs.
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
491. Doc comments (Rust) — [GAP] /// comments that feed docgen.
492. TODO and FIXME tracking (all) — [GAP] Collect markers across the tree.
493. Fluent multi-line chains (Kotlin) — [GAP] Readable chained calls.
494. Shadowing (Rust) — [GAP] let x = x + 1 rebinding; needs a rule change, since same-scope let repeats are rejected today.
495. Inline type ascription (Rust) — [GAP] x: Type annotations where inference needs help.
496. Underscore for unused bindings (all) — [GAP] _ prefix silences unused warnings.
497. Case-style lints (Rust) — [GAP] snake_case and CamelCase enforcement.
498. Import aliasing (Python/Go) — [GAP] import x as y.
499. Re-exports (Rust) — [GAP] pub use for clean public APIs.
500. Tour and Book rewritten for 1.3.0 (own) — [GAP] The docs catch up with ecall3, hex literals and the new libraries.
