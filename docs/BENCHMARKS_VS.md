# Benchmarks vs Python, Go, Rust, C — Qasida 1.0

Same algorithm in every language, same inputs, self-timed programs.
Reproduce: `python3 tools/bench_vs/run_bench.py` (needs `go` and
`rustc` on PATH for those rows; missing compilers are skipped, not
faked). Each program runs 3x; the table shows the MEDIAN.

## Machine and flags (26 Oct 2026, this VM)

- Linux VM, 2 cores (shared host — see the noise note below).
- Qasida: `forge.py build` (safe mode, the default; `-O2`, checked
  arithmetic, bounds checks on).
- Python 3.12.3, run as-is. Go 1.23.0 (`go build`). Rust 1.80.0
  (`rustc -O`). C: gcc (`cc -O2`).
- All programs print their own elapsed microseconds and their result;
  the runner checks every language agrees on the result. A benchmark
  that computes different answers is not a benchmark.

## Results (median microseconds, lower is better)

| task | Qasida | Python | Go | Rust | C |
| --- | --- | --- | --- | --- | --- |
| fib(35), recursive | 108,287 | 3,312,991 | 158,958 | 67,177 | 51,607 |
| array_sum, 1M runtime ints | 8,014 | 390,420 | 2,502 | 2,136 | 1,747 |
| matmul 128x128, naive | 3,711 | 959,314 | 4,769 | 9,952 | 1,737 |

Reading it plainly:

- **vs Python:** Qasida is ~31x faster on fib, ~49x on array_sum,
  ~259x on matmul. That is the scripting-language gap, and it is real.
- **vs the compiled languages:** Qasida sits in the same league,
  not 10x away: within ~2x of C on fib and matmul, ~4x on array_sum,
  and trading places with Go and Rust run to run (see noise note).
  C is fastest overall, as expected — it has no checks at all.
- **What Qasida is not claiming:** it does not beat Rust or C.
  Anyone selling a young language as "faster than Rust" on three
  microbenchmarks is selling something. The honest claim is narrower:
  compiled-language performance with safe defaults, 25-260x above
  Python on these tasks.

## Noise note (read before quoting numbers)

This VM is noisy. Across four runs of the same script, fib varied
Qasida 108-143ms, Go 110-193ms, Rust 51-173ms. Treat close numbers
as ties. The Python gap (25x+) is far above the noise; the
Qasida/Go/Rust ordering on any single task is not stable enough
to rank. If you need stable rankings, run on a quiet machine with
more repetitions.

## Two findings worth keeping

1. **The plain-sum trap.** The first version of the loop task was
   `total += i` for i in 1..50,000,000. Rust and C reported 0-1us —
   not because they are infinitely fast, but because their compilers
   replaced the loop with the closed form n(n+1)/2 at compile time.
   Qasida in safe mode did NOT fold it (27ms): the checked
   arithmetic blocks that optimization. Qasida in fast mode
   (`--mode fast`, unchecked, -O3) DID fold it: 0us. So the task was
   replaced with array_sum, where the data is generated at runtime
   (LCG, seed 42, 1M ints) and cannot be folded by any compiler.
   The lesson is general: a benchmark that a compiler can delete
   measures the compiler, not the language.
2. **Float display, not float error.** Qasida prints floats at 6
   significant digits (%g), so its matmul checksum displays as
   4.1943e+06 while the exact value is 4194304. The runner checks
   with relative tolerance (1e-4) for exactly this reason. The
   computation agrees across all five languages; only the display
   is rounded. (Float printing precision is a real, small gap —
   noted in the README's honest-limits list.)

## Older numbers (kept for reference)

docs/BENCHMARKS.md holds the earlier Qasida vs NumPy/Python
numbers (dot 5000: 8us vs NumPy 29us vs Python 788us; matmul 64x64:
NumPy 343us with BLAS beats Qasida 615us). Those still stand;
this page adds the compiled-language comparison.
