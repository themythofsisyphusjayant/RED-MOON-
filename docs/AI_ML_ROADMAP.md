# Qasida AI/ML Program — every best AI/ML library, 100% in Qasida

Goal (user, 29 Oct 2026 ~20:04 IST): add every best AI/ML library
possible to Qasida, completely written in Qasida
(.fg code only — no bindings, no borrowed code inside the libraries).

This is the AI/ML shelf of the 100+ library program
(docs/LIBRARY_ROADMAP_100.md). numpy + pandas are already done
(29 Oct batch). The AI/ML shelf is now the library priority, worked
through the daily batches (10+ library items per day, counted
separately from the 10+ OS items).

Rules (standing): every library verified by a real run with exact
outputs; numbers from verified runs only; function-call style (no
operator overloading); when a library cannot be built in Qasida,
extend Qasida until it can (language-evolution rule) — never fake
the missing piece.

Status codes: DONE = exists in tree | BUILD = pure Qasida with
existing builtins | NEEDS = needs a new capability first (named).

## A. Core numerics (5)
1.  numpy (py) — DONE: ndarray, matmul, reductions, transpose.
2.  scipy-lite (py) — BUILD: linalg solve/inverse/det, stats
    distributions, signal-lite (filters, windows).
3.  math-extra (py/mo) — BUILD: special functions (erf, gamma-lite).
4.  statistics (py) — DONE: mean/median/mode/variance/quantiles.
5.  random-extended (py/rs) — BUILD: extend rand.fg (normal,
    choice, shuffle, seedable generators).

## B. Classical ML — scikit-learn style (8)
6.  sklearn-lite (py) — v1 DONE 29 Oct 2026 (forge_lang/stdlib/sklearn.fg +
    examples/sklearn_demo.fg, verified first run: linreg w 2.00013
    b 0.999526, logreg prob 2.5 = 0.1146 / 4.5 = 0.922931, kNN
    2.5 -> 0 / 8.5 -> 1, k-means centers 2 / 11, accuracy 0.6,
    P/R/F1 0.666667): linear + logistic regression (GD), binary
    kNN, 1D k-means, accuracy, confusion, precision/recall/F1.
    v2 adds: decision tree, random-forest-lite, naive Bayes, PCA,
    scaling, pipelines, cross-validation, train/test split fn.
7.  metrics (py) — BUILD: accuracy, precision, recall, F1, confusion
    matrix, ROC-lite, log-loss.
8.  xgboost-lite (py) — BUILD: gradient-boosted trees (small depth,
    exact greedy splits).
9.  lightgbm-lite (py) — BUILD: histogram-based GBM-lite.
10. linear-models (py) — BUILD: ridge, lasso, elastic net, SGD
    regressor/classifier.
11. svm-lite (py) — BUILD: linear SVM (SMO-lite); kernel SVM after.
12. clustering-plus (py) — BUILD: DBSCAN-lite, hierarchical-lite,
    GMM-lite (after k-means).
13. model-select (py) — BUILD: train/val/test splits, grid + random
    search, pipelines (with optuna-lite, §G).

## C. Deep learning — PyTorch / Keras style (7)
14. tensor (mo) — DONE: forge_lang/stdlib/tensor.fg.
15. autograd-extended (mo) — BUILD: grow the tensor tape from 20
    ops toward 60 (conv, pooling, gather, scatter-lite, norms).
16. nn-extended (mo) — BUILD: Conv1d/2d-lite, Embedding, Dropout,
    BatchNorm, more activations, SGD+momentum, RMSprop, more
    losses (CE, MSE, Huber, BCE), more schedules.
17. keras-lite (py) — BUILD: Sequential / Functional-style
    high-level API over nn (compile / fit / evaluate / predict).
18. torch-data (py) — BUILD: Dataset / DataLoader-lite, batching,
    shuffling, transforms.
19. torch-distributed (py) — NEEDS: sockets + shared-mutable
    primitives (infra, not a library alone) — later.
20. jax-lite (py) — NEEDS: jit/vmap need compiler transforms
    (research item) — later, not faked.

## D. Transformers & NLP — HuggingFace style (9)
21. tokenizer (mo) — DONE: char + BPE. BUILD: WordPiece +
    SentencePiece-lite.
22. transformers-lite (py) — BUILD: BERT-block, GPT-block,
    LLaMA-block (RMSNorm, SwiGLU, RoPE — nn already has pieces),
    beam search (greedy/temp/top-k/top-p exist).
23. bert-finetune-lite (py) — BUILD: classification head + tiny
    fine-tune loop on a small dataset.
24. embeddings-store (py) — BUILD: vector store + cosine nearest
    neighbour search.
25. rag-lite (py) — BUILD: chunk files + retrieve + prompt pack.
26. nlp-lite (py) — BUILD: tfidf, naive-Bayes text, stemming,
    stopwords, sentence split.
27. ner-lite (py) — BUILD: rule-based entity tagging first;
    model-based after transformers-lite.
28. summarization-lite (py) — BUILD: extractive summarization
    (TextRank-lite); abstractive after transformers-lite.
29. translation-lite (py) — NEEDS: real seq2seq at scale (later);
    phrase-table-lite only in v1.

## E. Vision — OpenCV style (5)
30. vision-lite (py) — BUILD: resize, crop, normalize, flip,
    grayscale, conv2d-lite, threshold.
31. image-io (py) — BUILD: PPM + PNG-lite encode; PNG decode
    after the gzip/zlib slice.
32. augment-lite (py) — BUILD: flips, crops, noise, cutout,
    brightness/contrast.
33. detection-lite (py) — BUILD: template match + tiny
    sliding-window; YOLO-scale NEEDS real backbones + weights
    (later, not claimed).
34. segmentation-lite (py) — BUILD: threshold + region-lite,
    contour-lite.

## F. RL & agents — Gym / Stable-Baselines style (5)
35. gym-lite (py) — BUILD: envs — bandits, gridworld,
    cartpole-lite, mountaincar-lite.
36. agents-lite (py) — BUILD: Q-table, SARSA, DQN-lite on nn,
    policy-gradient-lite.
37. ppo-lite (py) — BUILD: clipped PPO, small, after DQN-lite.
38. bandits (py) — BUILD: epsilon-greedy, UCB, Thompson sampling.
39. multi-agent-lite (py) — BUILD: two-agent gridworld-lite
    (after single-agent items).

## G. Data, eval & tracking (7)
40. datasets-extended (mo) — BUILD: more loaders on top of
    dataset.fg (CSV, text, image-folder-lite).
41. eval-harness (py) — BUILD: held-out loss / perplexity /
    accuracy reports, standardised.
42. metrics-text (py) — BUILD: BLEU-lite, ROUGE-lite, perplexity.
43. tracking-lite (py, mlflow-style) — BUILD: local run logs
    (params, metrics, artifacts) as files.
44. tensorboard-lite (py) — BUILD: local scalar logs + charts
    via plot-lite (SVG).
45. optuna-lite (py) — BUILD: random/grid search + TPE-lite.
46. explain-lite (py) — BUILD: permutation importance, attention
    weight visualisation, SHAP-lite approximations.

## H. Deployment (4)
47. model-export (mo) — BUILD: versioned text checkpoints v2
    (save / load).
48. onnx-lite (py) — BUILD: graph export for MLP / attention-lite;
    full op coverage later.
49. quant-lite (mo) — BUILD: extend existing int8 steps (per-channel,
    calibration-lite).
50. inference-server-lite (py) — BUILD: HTTP predict endpoint over
    the http-server builtin; batch inference alongside.

## Count
50 AI/ML libraries: DONE ~10 (tensor, autograd, nn, tokenizer,
datasets, gpt, inference, numpy, pandas, statistics), BUILD ~35,
NEEDS ~5 (distributed, jax transforms, seq2seq-at-scale, YOLO-scale
detection, full pretrained-weight loading).

## Honestly NOT possible as pure libraries (yet)
- Distributed multi-GPU training (needs sockets + cluster infra).
- GPU-cluster-scale training (CUDA emit is limited; local first).
- Loading 1B+ pretrained weights into the Qasida runtime
  (binary weight formats + memory; safetensors/gguf parsing is a
  language+format slice of its own).
- Real-time video pipelines at scale.
These are not faked and not silently dropped: when their turn comes
they trigger language/infra slices first, per the evolution rule.

## Order of work (library batches, after numpy + pandas)
1. sklearn-lite + metrics + eval-harness (the classical shelf).
2. nn-extended + keras-lite + torch-data (the deep shelf).
3. transformers-lite + rag-lite + embeddings-store (the NLP shelf).
4. vision-lite + gym-lite + agents-lite, then tracking/optuna/
   explain, then deployment items. NEEDS items last within their
   groups, each triggering its capability slice first.
