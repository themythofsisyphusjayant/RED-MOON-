# The Qasida ML stack (0.2.0) — what it is, and what it is not

The Mojo-level batch, in one place. The goal was never "train a
1B model in Qasida" — that needs a cluster and distributed
training, and this document does not claim it. The goal was: a
language a person can use for real small-model LLM work —
tensors, gradients that are actually computed (not hand-written),
a transformer that trains, a tokenizer, data loading, an
inference engine with a cache, and GPU kernels for the hot parts.

## 1. Tensors — `forge_lang/stdlib/tensor.fg`

A `Tensor` is `{ data: [float], shape: [int] }`, flat row-major.
Qasida had no nested arrays when this was built, so this is the honest shape
for multi-dimensional values, and it matches how real frameworks
store tensors underneath. Ops: add/sub/mul/scale, matmul,
transpose, reshape, flatten, sum/mean, ReLU, GELU (sigmoid
approximation — there is no erf builtin yet), softmax (1-D and
row-wise), bias-add for rows, row extraction, argmax, dot.
Demo: `examples/tensor_demo.fg` → matmul 19 22 43 50.

## 2. Autograd — `forge_lang/stdlib/autograd.fg`

A real reverse-mode tape. Nodes are parallel flat arrays
(`vals`, `grads`, `left`, `right`, `op`); the tape predates struct
arrays, and flat arrays keep the hot loop simple. Every op returns an `Ag` (tape + last node
id); `ag_backward` walks the tape in reverse applying the chain
rule. Ops: input, add, sub, mul, div, neg, sigmoid, ReLU, exp,
log, sqrt. The sqrt node exists so LayerNorm backward is exact.
A layer that returns many nodes returns a `NodeVec` (tape +
ids) — defined in autograd.fg itself, because the C backend
must see `Ag`'s full definition before a struct containing it
(see Gotchas). Demo: `examples/autograd_demo.fg` — f = 21.9526,
df/dx = 10.0452, numeric gradient 10.0452 (exact at printed
precision).

## 3. Neural nets — `forge_lang/stdlib/nn.fg`

Linear, LayerNorm, single-head causal attention, MLP (GELU),
Adam and AdamW, cosine / step-decay / warmup-cosine schedules,
gradient clipping by global norm, checkpoints, int8
quantization, and sampling (greedy, temperature, top-k, top-p).
Checkpoints are one float per line, 6 decimal places
(truncation, via `float_to_fixed` — built on a Qasida
`int_to_str`, since there is no int-to-string builtin).
New builtin in this batch: `parse_float(str) -> float`, needed
to load checkpoints and imported weights.
Demo: `examples/nn_demo.fg` — Adam step 1 moves 1.0 → 0.99,
clip norm exactly 2.5, checkpoint round-trips 0.5 / -0.25 / 1.5.

## 4. Tokenizer + data — `forge_lang/stdlib/tokenizer.fg`, `forge_lang/stdlib/dataset.fg`

Character tokenizer (vocab = distinct characters, first-seen
order) and BPE (merge the most frequent adjacent pair, count
>= 2, stored as `"left|right"`; tokens containing `|` are not
supported). Both round-trip. Demo text "hello world hello
world": 23 chars → 13 BPE tokens.
`SeqData` holds sliding next-token windows flat: window i is
input `ids[i..i+seq_len-1]`, target `ids[i+1..i+seq_len]`.
Functions: `make_sequences`, `seq_get_x/y`, `seq_train/test`
(split by percentage), `seq_batch`, `seq_shuffle` (needs
`rand.fg` imported by the program — see Gotchas).

## 5. Tiny GPT — `forge_lang/stdlib/gpt.fg`, `examples/tiny_gpt.fg`

1 block, 1 head, d=8, hidden=16, tied output head, 776 params,
layout documented at the top of `gpt.fg`. Training pattern:
params are the FIRST nodes in a fresh tape, so param node id ==
param index, and the layout offsets double as node ids.
Forward is built entirely from autograd ops (embedding sum,
LayerNorm with sqrt, QKV linears, causal softmax over j <= i
only, GELU, tied head, cross-entropy) — so no backward formula
is hand-written anywhere.
Verified run, 26 Oct 2026, ~5 seconds total:
text "hello world hello qasida", 6 windows of length 8, Adam
lr 0.03, clip 1.0, 20 epochs — average loss 2.274 (epoch 0) →
0.360 (epoch 19), minimum 0.199 (epoch 16). Generation from
"hello wo": greedy loops on spaces, temperature sampling
(seed 123, temp 0.8) gives varied gibberish. That is the honest
result for 776 parameters on one sentence: the training is the
proof, the generation is a loop demo, not fluent text.

## 6. Inference — `forge_lang/stdlib/inference.fg`

`infer_step` runs one transformer block for one new token with
a KV-cache (`Cache { k, v, len }`): it appends the new token's K
and V, attends over the cache, and returns the block output plus
the new cache. Causality is structural — the cache never holds
a future token. Verified: step-by-step output matches a
full-sequence forward over the same weights exactly
(diff 0, `examples/inference_demo.fg`). Int8 quantization of
the same step differs by at most 0.026 on the demo step — a
mechanism demo, not a claim of lossless quantization.

## 7. GPU — `examples/cuda/kernel.cu`

Fused single-head causal attention (QK^T + softmax + PV in one
launch, shared-memory scores/probs), LayerNorm, embedding
lookup, and an fp16 matmul kernel, alongside the earlier
dot/matmul kernels. `tools/simulate_cuda.py` mirrors them:
embedding 1 0 0 1 1 0, layernorm ±0.99998, attention
1.0/0.0, 0.330/0.670, 0.802/0.198, half matmul 19 22 43 50.
**Not yet run on a real GPU.** The earlier dot/matmul kernels
were verified on Kaggle Tesla T4 (driver 580.178.04, nvcc
12.8); these new kernels await the same run. Do not quote them
as GPU-verified until that run exists.

## 8. Weight import — `tools/import_torch_weights.py`

Reads a text weight file (`# name` + whitespace floats) or, on
a machine with torch installed, a `.pt` state dict, and writes
a Qasida file with one function per tensor returning its
`[float]` array. The text path is verified end to end
(`examples/imported_demo.fg`); the `.pt` path is provided but
not run in this VM, because torch is not installed here.

## Gotchas found while building this (for future work)

- A struct containing another struct must be defined in the
  same file, after the inner struct — C emission order breaks
  otherwise. Hence `NodeVec` lives in autograd.fg.
- Pushing to a plain array parameter does not reach the caller;
  return the array (or a struct holding it) instead.
- Two stdlib files must not both import `rand.fg` (or `tensor.fg`)
  in the same program — duplicate definitions. `nn.fg` imports
  both; `dataset.fg` and `gpt.fg` import neither and rely on the
  program (or `nn.fg`) to bring `rand.fg` in. `inference.fg`
  imports `nn.fg`, so import `inference.fg` alone, not `nn.fg`
  alongside it.
- `break` exits the innermost `while`/`for` loop (native, WASM, big32).
- `float_to_fixed` truncates, it does not round.
- Checkpoint format is 6-decimal text; weights with more
  precision lose it on save (load is exact for what was saved).

## Still not done

1B training, distributed training, multi-head / multi-layer
blocks as a library (the GPT code is 1 block, 1 head),
WASM strings/arrays, big32 floats/structs, a public registry
host, CI upload, debugger, fuzzing, self-hosting compiler.
Each needs its own pass; none is half-claimed here.

## 0.3.0 addendum — scaled GPT + GPU-verified kernels
- `gpt2.fg` generalises the transformer (any blocks/heads/sizes);
  `gpt_scaled.fg` is 2 blocks, 2 heads, d=16, hidden=32, seq=16,
  29-char vocab, 5200 params, on a 411-char story. Training
  (200 windows, 3 epochs, Adam lr 0.02, clip 1.0): loss
  2.559 -> 2.364. Held-out test (windows 320..327): loss
  4.063 -> 3.987, perplexity 58.1 -> 53.9 — a small, real
  generalisation gain. An earlier split (20 training windows
  only) made held-out perplexity WORSE (39.2 -> 50.8): with
  almost no training text, the model memorises, it does not
  generalise. Generation still loops/rambles.
- GPU kernels are now GPU-verified, not just simulated: Kaggle
  notebook v4, 2x Tesla T4, driver 580.178.04, nvcc 12.8.93.
  Outputs match `tools/simulate_cuda.py` to 6 decimals on
  every kernel (see CHANGELOG 0.3.0). Two bugs were found
  only by running on GPU: log(0) NaN in training (fixed with
  a 1e-9 epsilon in g2_loss) and `__half2double` not existing
  in CUDA (fixed to `(double)__half2float`); notebook v3
  failed to build, v4 is the verified run.

## 0.4.0 addendum — TinyStories word GPT
- Real data replaces the hand-written story: first 200
  TinyStories train stories (24,000 kept words, 500-word
  vocab + <unk>, 14.8% UNK) via tools/prepare_tinystories.py.
- `examples/gpt_tinystories.fg`: word-level GPT (gpt2.fg,
  2 blocks, 2 heads, d=16, hidden=32, seq=8 words, 12,608
  params), 500 strided windows x 3 epochs, Adam lr 0.02.
  Held-out (later stories, offset 20000): loss 6.98368 ->
  5.51097, perplexity 1078.88 -> 247.39. Training losses
  4.98375, 4.64674 for epochs 1-2. Sampled generation is
  real words in salad order; greedy loops on "cake".
  Not fluent sentences — do not claim them.
- Engineering lesson: the native backend retains training
  tapes, so long runs must checkpoint-and-restart (one
  epoch per process; eval in its own process). Tape
  freeing + tensor-level autograd are the 0.5.0 unlocks.

## 0.5.0 addendum — engine batch
- Tape freeing (codegen.py `emit_free_frame`): block
  variables are freed at block end. The 0.4.0 leak — a
  tape per training step, 0 frees ever — is gone
  (1,000/1,000 freed on the probe). Scalar TinyStories
  now trains 3 epochs in one process: train 4.98375,
  4.49469, 4.41384; held-out ppl 1078.88 -> 385.06
  (differs from 0.4.0's 247.39 because the old runs
  reset Adam moments each epoch).
- Tensor autograd (forge_lang/stdlib/tensor_autograd.fg, 17 ops,
  flat tape) + tensor GPT (forge_lang/stdlib/tgt.fg): forward 100
  nodes vs 221,844 scalar; gradients checked against
  finite differences to ~1e-9; small TinyStories run
  1500 steps in 6.5 s, held-out ppl 548.97 -> 283.20.
- KV-cache for gpt2 (forge_lang/stdlib/inference_gpt2.fg): matches
  full forward to 4.44e-16 on the demo prompt.
- Scaled tensor run (49,664 params, 500 stories,
  75,000 words, vocab 1000): held-out ppl 1118.87 ->
  189.13, 26.1 ms/step, forward 136 nodes. Generation
  still salad order — fluency is NOT claimed.
- GPU training loop VERIFIED on a real T4
  (examples/cuda/mlp_train.cu, XOR MLP, square-matmul
  wrapper; Kaggle notebook arshhdubeyy/forge-mlp-train
  v3, 26 Oct 2026, LR 5.0: loss 0.001529 at epoch
  1500, predictions ~0, 1, 1, 0).

## 0.6.0 addendum — ecosystem layer
- Import dedup (compiler.py): libraries combine
  freely now; nn's Adam trains tensor models.
- New tape ops 17-20 (maxpool2d, sigmoid, tanh,
  mse) with finite-difference checks.
- rnn.fg (LSTM/GRU/RNN): first-bit memory len 5,
  0.44 -> 1.0; len 8 stalls at chance (known LSTM
  optimisation difficulty, documented in the demo).
- cnn.fg: cross-vs-border 0.5 -> 1.0 (first-layer
  conv only; stacking needs tape-native im2col).
- ml_classical + preprocess + metrics + csv:
  synthetic purity/knn/logreg all 1.0; real Iris
  pipeline test acc 0.933333, macro F1 0.937322.
