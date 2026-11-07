# Benchmarks — Qasida (0.5.0)

Measured 26 Oct 2026 in this VM (Linux x86_64, compiled C
via `cc`, safe mode unless noted). All numbers are from
runs actually executed that day — no projections, no
other-machine figures. Reproduce with:

```sh
python3 forge.py run examples/benchmark.fg
python3 forge.py run examples/tgt_tinystories.fg  # prints train micros
```

## Headline table

| Workload | Qasida | NumPy | Pure Python loops |
|---|---|---|---|
| dot(5000) | **8 µs** | 29 µs | 788 µs |
| matmul 64×64 | 615 µs | **343 µs** | 476,501 µs |
| loop, 1M array reads | 3,802 µs | — | — |

Notes, stated plainly:

- Qasida beats pure Python loops by ~100x on dot and
  ~775x on matmul, because it compiles to C. That is the
  honest comparison for "Python-like code, C-like speed".
- NumPy wins matmul (343 vs 615 µs) because it calls BLAS;
  Qasida's `tensor_matmul` is plain triple loops. At
  dot(5000) Qasida wins only because NumPy's call
  overhead dominates at that size — do not read that as
  "Qasida beats NumPy in general". A BLAS-backed matmul
  is future work, not a claim.
- Dot result agrees across all three: 83308.335 (Qasida
  prints 83308.3 — same value, shorter float printing).

## ML training (the numbers that motivated 0.5.0)

| Model | Forward nodes | Train time, 1500 steps |
|---|---|---|
| Scalar GPT, TinyStories (0.4.0) | 221,844 | single process OOM-killed pre-0.5.0; after the tape-freeing fix, one process completes (see CHANGELOG) |
| Tensor GPT, TinyStories (0.5.0) | 100 | **6.5 s total, 4.35 ms/step** |

The tensor model is the same architecture and data as the
scalar one (12,608 params, seq 8, vocab 500) with a
different init, so the comparison is structural (nodes,
time), not a perplexity race. Held-out perplexities:
scalar single-process 1079 → 385; tensor 549 → 283.

## What is NOT benchmarked here

- Mojo: not installed in this VM, so no Mojo numbers are
  claimed. Any Mojo comparison needs a machine with Mojo.
- PyTorch: not installed in this VM, so no PyTorch
  numbers are claimed either. The `.pt` weight-import
  branch is likewise unrun (see ML_STACK.md).
- GPU: kernel outputs are verified on Kaggle T4 (see
  examples/cuda/README.md), but no GPU training timing is
  claimed — the GPU training loop is code, not a run, in
  0.5.0 (see CHANGELOG).
