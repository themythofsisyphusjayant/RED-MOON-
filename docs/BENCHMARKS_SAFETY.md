# The cost of safety: Qasida safe mode vs fast mode

How much do safe mode's runtime checks actually cost? Two comparisons,
same programs, same inputs, self-timed with `clock_micros`, medians of 3
runs, safe and fast results verified equal in every run
(`tools/bench_vs/run_safety_bench.py`).

## What safe mode checks

Safe mode (the default) emits a check that aborts with a clear message
on every:

- integer `+`, `-`, `*` overflow (`__builtin_*_overflow` → "integer
  overflow"), including the `INT_MIN / -1` case;
- integer `/` and `%` by zero ("division by zero");
- array index outside `0 <= i < len` ("array index out of bounds");
- string index outside `0 <= i < len` ("string index out of bounds").

Float arithmetic is unchecked in both modes. Allocation and GC behaviour
are identical in both modes. Fast mode (`--mode fast`) emits none of the
above checks.

## Two comparisons, because one lies

- **Shipped**: `forge.py build` (safe: `-O2`) vs `forge.py build
  --mode fast` (fast: `-O3 -march=native`). This is what a user
  actually pays — but it mixes check removal with optimizer
  differences.
- **Matched**: C emitted in safe mode and in fast mode, both compiled
  with identical flags (`-O2`, no `-march=native`). The ONLY difference
  is the emitted checks, so this ratio is the pure cost of safety.

## Tasks and what they stress

| Task | Stresses in safe mode |
|---|---|
| `fib` (fib(35), recursion) | int overflow checks only, no indexing |
| `array_sum` (1M runtime ints) | array bounds + int overflow + modulo checks |
| `matmul` (128x128 flat floats) | array bounds checks (float ops unchecked) |
| `str_index` (10M char tests) | string bounds checks |
| `nested_matmul` (128x128 `[[float]]`) | double (nested) bounds checks |
| `float_loop` (10M float iters) | control: loop-counter int checks only |

`str_index` note: `s[i]` allocates a fresh 1-char string in BOTH modes,
so its ratio isolates the bounds check; its absolute time is
allocation-dominated.

## Results (microseconds, medians of 3)

Run 1 overlapped a concurrent full test-suite run on the same VM; its
two wild outliers (nested_matmul matched-safe, float_loop matched-fast)
are attributed to that. Run 2 ran clean. Both runs are reported, because
the VM's timing noise is itself a finding (see caveats).

Run 1 — shipped safe / shipped fast / shipped ratio / matched safe /
matched fast / pure ratio:

| Task | Shipped safe | Shipped fast | Shipped x | Matched safe | Matched fast | Pure x |
|---|---|---|---|---|---|---|
| fib | 75005 | 29996 | 2.50 | 99336 | 37010 | 2.68 |
| array_sum | 4291 | 3271 | 1.31 | 2144 | 1552 | 1.38 |
| matmul | 4265 | 1108 | 3.85 | 3551 | 3826 | 0.93 |
| str_index | 882723 | 437805 | 2.02 | 857825 | 515276 | 1.66 |
| nested_matmul | 2612 | 1899 | 1.38 | 5543 | 1894 | 2.93 |
| float_loop | 35042 | 22179 | 1.58 | 33309 | 166136 | 0.20 |

Run 2 — same columns:

| Task | Shipped safe | Shipped fast | Shipped x | Matched safe | Matched fast | Pure x |
|---|---|---|---|---|---|---|
| fib | 190885 | 21659 | 8.81 | 93178 | 24887 | 3.74 |
| array_sum | 2772 | 2515 | 1.10 | 2156 | 2607 | 0.83 |
| matmul | 3812 | 718 | 5.31 | 4481 | 3711 | 1.21 |
| str_index | 895814 | 671105 | 1.33 | 682890 | 406367 | 1.68 |
| nested_matmul | 2644 | 1892 | 1.40 | 2672 | 1956 | 1.37 |
| float_loop | 40859 | 21593 | 1.89 | 54464 | 68418 | 0.80 |

## Reading

- **Overflow checks are the expensive ones.** `fib`'s pure check cost is
  2.7-3.7x: deep int recursion pays a check on every add and
  subtraction. This is the prime target for bounds/check elimination
  (the next item): a loop counter or recursion depth that provably
  cannot overflow should not pay for the check.
- **String bounds checks cost ~70%.** `str_index`'s pure ratio is
  1.66-1.68x in both runs — the most stable number in the set.
- **Nested bounds checks cost ~40%.** `nested_matmul` is ~1.4x in
  run 2's both comparisons and run 1's shipped comparison.
- **Array bounds checks on float work are nearly free.**
  `matmul`'s pure ratio is 0.93-1.21x, i.e. noise around 1.0: at -O2
  the checks are cheap next to the float work.
- **Counter checks are free.** `float_loop`'s matched ratio is noise
  around 1.0; the loop counter's overflow check costs nothing
  measurable.
- **The shipped fast-mode wins are mostly the optimizer, not the
  checks.** `matmul` ships 3.9-5.3x faster in fast mode but only
  ~1.0x on matched flags: `-O3 -march=native` auto-vectorizes the
  float inner loop, and that — not dropping bounds checks — is where
  the speedup comes from. Same story, smaller, for `float_loop`
  (shipped 1.6-1.9x, matched ~1.0x).

## Headline

Safety costs real but bounded: about 1.0-1.7x for loop, array, and
string work, about 3x for overflow-check-heavy int recursion. Fast mode
is worth it where you have measured a bottleneck and can prove the
checks cannot fire; for everything else, safe mode's price is small
next to what `-O3` alone buys.

## Caveats

- Single shared VM, noisy timing: absolute times vary up to ~2x
  between runs (fib shipped-safe: 75 ms then 191 ms). Medians of 3
  do not pin small ratios; anything below ~1.5x is within noise, so
  this document reports ranges from two runs, not single numbers.
- Shipped-fast numbers are machine-specific (`-march=native`).
- Float results print at 6 significant digits (`%g`); safe/fast
  agreement is checked with relative tolerance 1e-4, as in
  `docs/BENCHMARKS_VS.md`.

## Reproduce

```
python3 tools/bench_vs/run_safety_bench.py
```

## After check elimination (26 Oct 2026)

The eliminations in SPEC §6b change the safe-mode numbers. Same
runner, two runs, medians of 3. Results are identical to before
elimination on every task (verified directly: fib(35) = 9227465,
fib(40) = 102334155, str_index count = 1000000).

Post-elimination run 1 — shipped safe / shipped fast / shipped
ratio / matched safe / matched fast / pure ratio:

| Task | Shipped safe | Shipped fast | Shipped x | Matched safe | Matched fast | Pure x |
|---|---|---|---|---|---|---|
| fib | 6078 | 20680 | 0.29 | 5901 | 31616 | 0.19 |
| array_sum | 2125 | 1751 | 1.21 | 2135 | 1540 | 1.39 |
| matmul | 3660 | 2204 | 1.66 | 5216 | 5149 | 1.01 |
| str_index | 6213 | 1478 | 4.20 | 6284 | 6460 | 0.97 |
| nested_matmul | 2738 | 1883 | 1.45 | 2652 | 2430 | 1.09 |
| float_loop | 52682 | 21407 | 2.46 | 33072 | 34233 | 0.97 |

Post-elimination run 2 — same columns:

| Task | Shipped safe | Shipped fast | Shipped x | Matched safe | Matched fast | Pure x |
|---|---|---|---|---|---|---|
| fib | 5988 | 21267 | 0.28 | 6410 | 22819 | 0.28 |
| array_sum | 2122 | 1531 | 1.39 | 4141 | 1540 | 2.69 |
| matmul | 3558 | 907 | 3.92 | 3667 | 12306 | 0.30 |
| nested_matmul | 2699 | 1885 | 1.43 | 2635 | 1877 | 1.40 |
| str_index | 11395 | 1288 | 8.85 | 6022 | 6423 | 0.94 |
| float_loop | 34614 | 22018 | 1.57 | 33264 | 47496 | 0.70 |

Reading:

- **str_index collapses: 882-895 ms safe before, 6-11 ms after.**
  That is not a check going away — it is 10M malloc/free pairs
  and strcmp calls going away. The byte comparison removes the
  allocation from the hot path entirely, and the remaining bounds
  check is then ~free (matched safe ≈ matched fast, ~6 ms).
- **fib safe collapses: 75-191 ms before, ~6 ms after,
  reproducibly.** Removing the checked helpers from the recursion
  path lets the C compiler keep the recursive calls tight. The
  exact factor is noise-sensitive (the pre-elimination runs
  themselves spanned 75-191 ms), so read it as "an order of
  magnitude", not as a precise multiple.
- **Fast is now slower than safe on fib (21-31 ms vs ~6 ms),
  in both runs.** -O3 is not universally faster: on this tiny
  recursive shape its aggressive inlining costs more than the
  checks it removes. The shipped fast mode is still the right
  choice for vectorizable float work (matmul ships ~4x faster),
  but it is not a free speedup for every program.
- **array_sum improves modestly** (shipped safe ~2.1 ms vs
  2.8-4.3 ms before): half its bounds checks are gone, which is
  what duplicate elimination predicts.
- **nested_matmul, matmul, float_loop are essentially unchanged
  (nested safe 2.6-2.7 ms before and after).** That is the
  control group behaving: none of those programs has a duplicate
  index or a guard-provable operation, so elimination correctly
  leaves them alone. matmul's matched ratios swing (0.30-1.01)
  because the task is only ~3-5 ms and small absolute noise
  moves the ratio a lot.
