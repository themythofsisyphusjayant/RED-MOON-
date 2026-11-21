# Qasida Library Program — 100+ libraries, 100% in Qasida

Goal (user, 29 Oct 2026 ~00:57 IST): build 100+ libraries inspired by
Mojo / Python / Rust / Go, but implemented COMPLETELY in Qasida
(.fg code only — no C, Python, Rust, or Go code inside the libraries,
no bindings). The compiler itself stays Python (compile-time only);
that is a separate question from the libraries, and self-hosting the
compiler is NOT assumed here.

Queue: after the current chain (Finder push -> Terminal). Numpy +
pandas are items 1-2 below, not a separate program.

Rules for every library (from the project's standing rules):
- Numbers and claims come from verified runs, never invented.
- Function-call style (no operator overloading in Qasida): e.g.
  np_add(a, b), df_filter(df, col, value) — never a + b for arrays.
- Native + WASM first; big32/freestanding only where the backend
  allows (no strings/arrays/allocator in freestanding).
- Modest sizes first: the 0.4.0 lesson (one process holding every
  training tape OOM-killed an 8 GB VM) applies to big arrays too.

Status codes: DONE = exists in tree | BUILD = pure Qasida, no new
builtin needed | NEEDS = needs a new language capability first (named).

LANGUAGE EVOLUTION RULE (user, 29 Oct 2026 ~01:01 IST): NEEDS is
NOT a parking lot. When a library cannot be built in Qasida, extend
Qasida until it can — add the builtin or feature, verify it, then
build the library on it. Language and libraries co-evolve; building
things is how the language gets updated. This replaces the earlier
"NEEDS items go last" framing.

## 1. Numerics & math (12)
1.  numpy (py) — BUILD: ndarray struct + flat array, element-wise
    ops, matmul, reductions, reshape, slicing, random.
2.  scipy-lite (py) — BUILD: linalg solve/inverse/det, stats
    distributions, integration-lite. (linalg solve/inverse/det + stats
    distributions + integration-lite landed 21 Nov 2026, sprint day 1:
    linalg.fg, dist.fg, calculus.fg — verified both compilers;
    decompositions/eigenvalues still open.)
3.  math-extra (py/mo) — DONE 30 Oct 2026: forge_lang/stdlib/mathex.fg (erf via Abramowitz-Stegun, gamma via Lanczos g=7 for x >= 0.5; verified vs Python).
4.  statistics (py) — BUILD: mean/median/mode/variance/quantiles.
5.  random (py/rs) — BUILD: extend rand.fg (uniform, normal,
    choice, shuffle, seedable). (uniform/normal/exponential landed
    21 Nov 2026, sprint day 1: randdist.fg; choice/shuffle still open.)
6.  complex (py) — BUILD: complex struct + arithmetic.
7.  fractions-decimal (py) — BUILD: exact rational + fixed-point.
    (fixed-point landed 21 Nov 2026, sprint day 1: fixedpoint.fg Q16.16;
    exact rational still open.)
8.  matrix (mo/rs) — BUILD: dense linalg on top of tensor.fg.
9.  fft (py) — DONE 30 Oct 2026: forge_lang/stdlib/fft.fg (iterative radix-2, Taylor-series twiddles in pure .fg; impulse -> all 1, constant -> 4,0,0,0, round-trip exact).
10. optimization (py) — BUILD: gradient descent, least squares,
    Nelder-Mead-lite.
11. polynomials (py) — BUILD: poly eval, roots-lite, fitting.
12. units (py) — BUILD: physical constants + unit conversion.

## 2. Data (12)
13. pandas (py) — BUILD: DataFrame (per-column typed arrays +
    names), filter, sort, groupby, describe, head, join-lite.
14. frames-fast (rs polars) — BUILD: columnar ops, lazy-lite
    (only after pandas v1 lands).
15. csv (py/go) — BUILD: reader/writer on read_file + split.
16. json (py/go/rs) — BUILD: parser + writer (serde-style).
    (parser + writer landed 21 Nov 2026, sprint day 1: json2.fg;
    verified both compilers.)
17. toml (rs) — DONE 30 Oct 2026: forge_lang/stdlib/toml.fg (sections, string/int/float/bool, '#' comments; no arrays/inline tables/dates in v1).
18. ini (py) — DONE 30 Oct 2026: forge_lang/stdlib/ini.fg (sections, key=value, ';'/'#' comments, first-occurrence wins).
19. xml-lite (py) — DONE 30 Oct 2026: forge_lang/stdlib/xml.fg (first-element tag, attribute lookup, child text, inner markup; no namespaces/entities/validation).
20. table-store (rs sqlite) — BUILD: file-backed tables with
    insert/select/delete (NOT real SQLite — honest name).
21. datetime (py/go/rs chrono) — BUILD: date/time arithmetic,
    formatting, parsing.
22. calendar (py) — BUILD: calendars, weekdays, holidays-lite.
23. datasets (mo) — DONE: loaders (extend with more sets).
24. schema-validate (py) — BUILD: column/type checks for frames.

## 3. Text (12)
25. regex-full (py/rs) — BUILD: upgrade regex stdlib with groups
    + alternation (current: neither).
26. string-utils (go/py) — BUILD: trim/split/join/case/pad
    (extend existing builtins).
27. textwrap (py) — DONE 30 Oct 2026: forge_lang/stdlib/textwrap.fg (greedy wrap, fill, indent).
28. difflib (py) — DONE 30 Oct 2026: forge_lang/stdlib/difflib.fg (LCS length + LCS ratio 2M/(m+n), common prefix/suffix; documented as NOT Python SequenceMatcher ratio).
29. unicode-lite (py) — BUILD: ASCII core + documented limits
    (full Unicode is a later project, not v1).
30. tokenizer (mo) — DONE: char + BPE (extend vocab tools).
31. nlp-words (py) — DONE 30 Oct 2026: forge_lang/stdlib/nlp.fg (ASCII tokenize + lowercase, stopword list, suffix-strip stemmer: studies->study, running->run).
32. markdown-lite (py) — DONE (text) 30 Oct 2026: forge_lang/stdlib/markdown.fg (md_to_text + headings; HTML output still pending).
33. template (py/rs) — BUILD: mustache-style {{name}} rendering.
34. i18n-lite (go) — DONE 30 Oct 2026: forge_lang/stdlib/i18n.fg (two-locale parallel-array catalog, plural one/other, missing-key fallback to key).
35. slugify (py) — DONE 30 Oct 2026: forge_lang/stdlib/slugify.fg (ASCII lowercase, [a-z0-9] kept, runs folded to one '-', trimmed).
36. fuzzy (rs) — BUILD: levenshtein, jaro-lite, matching.

## 4. Web & network (12) — HTTP builtins only; raw sockets NEEDS
37. http-client (py/go) — BUILD: upgrade http_get (headers,
    POST, JSON helpers) on existing builtins.
38. http-server (go/py) — BUILD: routing + handlers on
    http_listen/accept/respond.
39. url (rs/go) — DONE 30 Oct 2026: forge_lang/stdlib/url.fg (parse scheme/host/port/path/query, build round-trip, query get, encode/decode of the reserved set; no ord() so arbitrary bytes pass through in v1).
40. rest-client (py) — BUILD: JSON API wrapper over http-client.
41. rss-feed (py) — BUILD: feed parse over http_get.
42. oauth-client (py) — NEEDS: token flows are HTTP-doable;
    full OAuth needs secure storage rules first.
43. websocket-lite (rs/go) — NEEDS: socket builtins (framing
    is pure, transport is not).
44. dns-lite (go) — NEEDS: socket builtins (UDP).
45. smtp-mail (py) — NEEDS: socket builtins (TCP).
46. ftp-lite (go) — NEEDS: socket builtins (TCP).
47. webhook (py) — BUILD: signed POST receiver over http-server.
48. api-mock (py) — BUILD: stub server for tests.

## 5. System & files (12)
49. pathlib (py) — DONE 30 Oct 2026: forge_lang/stdlib/pathlib.fg (POSIX join/dir/base/ext/stem/is_abs).
50. fs-utils (go) — BUILD: copy/move/list-lite (no readdir yet
    — list-lite NEEDS readdir builtin; copy/move are BUILD).
51. os-info (go) — BUILD: args/env/platform-lite.
52. config (rs) — BUILD: env + file config merge.
53. logging (py/go/rs) — BUILD: levels, files, rotation-lite.
54. cli-parse (rs clap) — BUILD: flags/subcommands over args().
55. shell-utils (go) — BUILD: exec-lite via spawn (no shell-out).
56. archive (py/go) — BUILD: tar writer/reader (uncompressed
    first; compression is item 58).
57. checksum (py/go) — BUILD: crc32, adler32, fnv.
58. compress (go/rs) — RLE DONE 30 Oct 2026: forge_lang/stdlib/compress.fg (count+char pairs, runs split at 9, round-trip verified); Huffman-lite + gzip still BUILD. (gzip reader landed 21 Nov 2026, sprint day 1: gzip2.fg — header parse + CRC32/ISIZE over zl_inflate; single member only, dynamic-Huffman branch unexercised; Huffman-lite still open.)
59. tempfiles (py) — DONE 2 Nov 2026: forge_lang/stdlib/tempfile.fg (deterministic names/paths from a caller counter; names only, no creation/cleanup in v1).
60. dotenv (rs) — DONE 30 Oct 2026: forge_lang/stdlib/dotenv.fg (KEY=VALUE, comments, quotes, '=' kept in values; no $ expansion in v1).

## 6. Crypto & security (8)
61. hashlib (py) — BUILD: sha256/sha1/md5-lite (pure .fg).
62. hmac (py) — BUILD: keyed hashing over hashlib.
63. base64-hex (py/rs) — BUILD: encode/decode (extend split/join).
64. uuid (rs) — BUILD: v4-style ids from seeded random.
65. passwords (py) — DONE 2 Nov 2026 (lite): forge_lang/stdlib/password.fg (salted FNV-1a verify; NOT bcrypt, NOT SHA, demo discipline only — must not protect real passwords).
    bcrypt NEEDS blowfish + cost work — later).
66. jwt-lite (py) — BUILD: header/payload/signature (HMAC).
67. aes-lite (py) — BUILD: AES-128 on word arrays (pure .fg).
68. rsa-lite (rs) — NEEDS: bignum arithmetic (i64 is not enough).

## 7. Concurrency (8)
69. async-lite (py/rs tokio) — BUILD: spawn/scope task helpers.
70. channels (go/rs) — BUILD: single-owner queues over spawn.
71. pool (py) — BUILD: worker pool over scope.
72. parallel (mo/rs rayon) — DONE (partial): parallel_dot/matmul;
    BUILD: parallel-map/reduce/filter.
73. mutex-lite (go/rs) — NEEDS: shared-mutable primitive (the
    language deliberately avoids it; design first, then build).
74. timers (go) — BUILD: sleep/schedule over clock_micros.
75. retry-backoff (py) — BUILD: retry with jitter.
76. task-queue (go) — BUILD: persistent-lite queue over files.

## 8. Testing & dev (10)
77. unittest (py/go) — BUILD: asserts + reporters over qasida test.
78. bench (mo) — BUILD: timing harness over clock_micros
    (BENCHMARKS.md becomes a library, not just a doc).
79. property-test (rs) — DONE 2 Nov 2026 (lite): forge_lang/stdlib/property.fg (hard-coded range checkers: add-commutes, square-nonneg, concat-len; no function values passed in).
80. mock-lite (py) — DONE 2 Nov 2026: forge_lang/stdlib/mock.fg (one canned int return, call counting; no argument matching).
81. docgen (mo) — DONE (partial): extend doc output formats.
82. fmt (go/rs) — DONE (partial): qasida fmt + style checks.
83. lint (rs) — BUILD: checker-diagnostic rules as a library.
84. profiler (py) — BUILD: section timers + report.
85. semver (rs) — BUILD: parse/compare/bump versions.
86. changelog (rs) — BUILD: keep-a-changelog generator-lite.

## 9. ML & AI (14)
87. tensor (mo) — DONE: forge_lang/stdlib/tensor.fg.
88. autograd (mo) — DONE: scalar tape + tensor tape.
89. nn (mo) — DONE: Linear/LayerNorm/attention/MLP/Adam.
90. gpt (mo) — DONE: tiny_gpt + gpt2 + TinyStories variants.
91. inference (mo) — DONE: KV-cache + quant steps.
92. sklearn-lite (py) — BUILD: linear regression, kNN, k-means,
    decision-tree-lite, naive-bayes.
93. vision-lite (py) — DONE 2 Nov 2026: forge_lang/stdlib/vision.fg (flat [float] mean/max/normalize/nearest-resize; no PNG decode).
    normalize) + png-lite encode; png DECODE is item 106.
94. tfidf (py) — BUILD: term vectors + cosine search.
95. rl-lite (py) — DONE 2 Nov 2026: forge_lang/stdlib/rl.fg (Q update, greedy argmax, least-tried explore; deterministic, no randomness).
96. model-export (mo) — BUILD: extend text checkpoints (save/
    load, versioned).
97. embeddings (py) — BUILD: vector store + nearest neighbour.
98. rag-lite (py) — DONE 2 Nov 2026 (retrieve only): forge_lang/stdlib/rag.fg (word-overlap score + best-doc; case-sensitive, no stemming, no chunking/prompt pack yet).
99. eval-harness (py) — BUILD: held-out loss/perplexity reports
    (standardize what gpt_tinystories already does by hand).
100. data-augment (py) — BUILD: text/image augmentation-lite.

## 10. Graphics & media (8)
101. plot-lite (py) — BUILD: SVG line/bar/scatter from arrays.
102. svg-gen (py) — BUILD: shapes + paths as text.
103. color (go) — BUILD: hex/rgb/hsl conversion + palettes.
104. canvas (mo) — BUILD: VRAM wrappers (rect/circle/text) for
    kernels (extend pix_* helpers).
105. font-plus (mo) — BUILD: more glyphs (>, ?, f already added
    for Terminal; extend coverage deliberately, not ad hoc).
106. png-lite (py) — BUILD: encoder first; decoder after
    (needs zlib — item 58 gzip AFTER).
107. wav-lite (py) — BUILD: read/write WAV + tone synthesis.
108. tui-lite (go) — BUILD: boxes/tables/progress/spinners
    (text UI, no GUI toolkit pretence).

## 11. Games, geo & misc (12)
109. gamedev-lite (go) — DONE 2 Nov 2026: forge_lang/stdlib/gamedev.fg (Sprite struct, move, AABB overlap; no rendering).
110. physics2d (py) — BUILD: gravity/collision-lite.
111. ecs-lite (rs) — BUILD: entity/component/store-lite.
112. money (py) — BUILD: fixed-point currency arithmetic.
113. geo-lite (py) — BUILD: haversine, bounding boxes.
114. timezones-lite (py) — DONE 2 Nov 2026: forge_lang/stdlib/timezone.fg (fixed standard offsets in minutes for Delhi/London/New York/Tokyo/Sydney/Dubai; no DST, unknown cities -> UTC).
115. ical-lite (py) — BUILD: calendar event text format.
116. cli-table (go) — BUILD: aligned tables for terminals.
117. progress (py) — BUILD: bars + spinners (with tui-lite).
118. email-parse (py) — BUILD: parse (NOT send — send NEEDS
    sockets, item 45).
119. feed-reader (py) — BUILD: RSS/Atom over http_get.
120. version-info (rs) — BUILD: build stamps + feature flags.

## Count
120 named items (12+12+12+12+12+8+8+10+14+8+12). DONE now: ~10
(tensor, autograd, nn, gpt, inference, tokenizer, datasets,
parallel-partial, docgen-partial, fmt-partial). NEEDS a new
builtin first: sockets (43,44,45,46), bignum (68), shared-
mutable primitive (73), readdir (50-list part). Everything
else is BUILD in pure Qasida with existing builtins.

## Order of work (after current chain)
1. numpy (1) + pandas (13) — the user's named first pair.
2. Text + data formats (csv/json/toml/regex-full) — they unlock
   everything else (configs, datasets, tests).
3. sklearn-lite + eval-harness + rag-lite — the ML shelf that
   makes the Mojo stack usable, not just present.
4. The rest by group. When a NEEDS item's turn comes, do the
   language slice FIRST (e.g. socket builtins before websocket/
   DNS/SMTP/FTP; bignum before rsa-lite; readdir before fs list;
   shared-mutable design before mutex-lite), verify the new
   capability with its own test, then build the library on it.

## Daily batch — 29 Oct 2026 (verified by qasida run demos)
DONE now (new): 1 numpy, 13 pandas, 6 complex, 7 fractions,
4 statistics, 57 checksum, 63 base64-hex, 85 semver, 12 units,
11 polynomials, 10 optimization, 36 fuzzy, 22 calendar,
33 template, 103 color, 112 money. Notes from the build:
pandas uses a flat DataFrame (a [[float]] struct field breaks
the C codegen — unknown ForgeArray_ForgeFloatArray type);
checksum/base64/hex use [int] byte arrays and semver returns
structs, because Qasida has no ord() or int-to-string builtin
yet. Trig-needing items (9 fft, 113 geo) are NOT faked: they
wait for a sin/cos/acos builtin slice, which is the next
language-evolution item when their turn comes.

## Daily batch — 2 Nov 2026 (verified by qasida run demos + big32 model kernels)
DONE now (new): bitset-lite, bloom-lite, lru-lite (stdlib + examples
demos, all qasida run verified), timezones-lite, gamedev-lite,
vision-lite, rl-lite, rag-lite (retrieve only), property-test lite,
mock-lite, tempfiles lite, passwords lite (salted FNV, NOT bcrypt/SHA).
OS kernels (now in MOON-OS — moved 12 Nov 2026 from `examples/os` +
`tests/test_kernel_*.py` here; big32 model exact transcript + halt +
final word): pwm, adc, spi, i2c, ringbuf, sem,
mbox, dma, crc, temp. Full-suite log: forge_suite_daily_20261102_*.log.

## Sprint batch 2 status notes (21 Nov 2026, libs-only sprint)
- Item 7 (fractions-decimal) — decimal.fg landed: fixed-scale-10000
  Dec, add/sub/mul/div + to_string, verified 4/4.
- Item 10 (optimization) — optimizers.fg landed: SGD + Adam with
  state (bias-corrected moments), verified 4/4 in float64.
- Item 1/8 (numpy/matrix) — ndarray.fg (true ndim, strides) and
  vecmath.fg (general [float] vector ops) landed, verified 4/4;
  they compose with day-1 linalg.fg.
- Data formats — structpack.fg (LE u8/u16/u32/i32 struct layouts)
  landed, verified 4/4; composes with day-1 binio/bincode.
- Errors — errwrap.fg (#42 helper-function slice), multierr.fg,
  resultx.fg, valerr.fg landed, verified 4/4.
- Collections — hashmap.fg (real bucket hashing), setops.fg,
  ordmap.fg, persist.fg, ringbuf.fg landed, verified 4/4.
- Text — strbuild.fg, caseconv.fg, utf8.fg, unidiff.fg landed,
  verified 4/4. Testing — junit.fg landed, verified 4/4.

## Sprint batch 3 status notes (21 Nov 2026, libs-only sprint)
- Formats — fmtstr.fg (fixed-decimal float rendering, int rendering,
  padding), protobuf.fg (LEB128 varints + field tags, wire types 0/2),
  sqlbuild.fg (safe SELECT/WHERE/INSERT/DELETE, quotes doubled),
  valid.fg (int_range / str_len / str_nonempty rules over key/value
  records), migrate.fg (migration plan/apply bookkeeping),
  lockfile.fg ("name==version #checksum" parse/render), all verified 4/4.
- Text — lines.fg (line scanner, no trailing empty line), plural.fg
  (full English plurals: irregulars, -es/-ies/-ves), glob.fg
  (`*`, `?`, `[...]` classes with ranges/negation), verified 4/4.
- System/files — bufio.fg (chunked reader + accumulating writer),
  logrot.fg (size-based rotation over a line buffer), checkread.fg
  (CRC32-verified reads, matches Python zlib.crc32), journal.fg
  (append-only journal via fs_append + replay), verified 4/4.
- Config — config2.fg (layered merge over config.fg: defaults <
  file < overrides), verified 4/4.
- Testing/time — snap.fg (golden compare, first-diff line),
  faketime.fg (fake clock), timeout.fg (deadline arithmetic),
  throttle.fg (debounce + throttle over explicit timestamps),
  verified 4/4.
- Observability — trace.fg (named spans + duration report),
  audit.fg ("ts|actor|action|target" trails + actor filter),
  verified 4/4.
- Held extra: icalparse.fg (parse a VEVENT block back out) built +
  verified 4/4 but NOT counted here — item #239 iCalendar already
  reads [HAVE] (ical-lite.fg builds VEVENT text), so the parse slice
  is an extension of a HAVE item; it stays local for a later batch.

- Sprint batch 4 (21 Nov 2026, same day, LIBS ONLY): 12 verification
  flips (bitset.fg, bloom.fg, lru.fg, deque.fg, heap.fg, rss.fg,
  regexfull.fg, csv2.fg, json2.fg, textwrap.fg, tempfile.fg,
  ratelimit.fg — all already in the tree, verified 4/4 under both
  compilers before flipping), the held icalparse.fg slice counted
  (#239 parse), and 7 new libraries: template2.fg ({{#if}} /
  {{#each}} / HTML escaping over template.fg), mdast.fg (Markdown
  AST + HTML render), sentenc.fg (abbreviation-aware sentence
  splitting), pathnorm.fg (lexical . / .. normalization),
  rest.fg extended (GET/POST construction, response status/body,
  typed JSON field lookup), xmlpath.fg (nested path lookup,
  all-children, counting), testkit.fg (named cases, richer asserts,
  data-level fixtures), all verified 4/4.

- Sprint batch 5 (21 Nov 2026, same day, LIBS ONLY): 11 verification
  flips (bench.fg, evalharness.fg, embeddings.fg, plot.fg, svg.fg,
  profiler.fg, jwt.fg, tarball.fg + archive.fg, dataset.fg,
  tokenizer.fg, quant.fg — all already in the tree, verified 4/4
  under both compilers before flipping) and 9 new libraries:
  promet.fg (counters/gauges + Prometheus text render), sbom.fg
  (CycloneDX JSON), cors.fg (origin allow-list + headers), csp.fg
  (CSP header builder), csrf.fg (seed-based tokens), pwhash.fg
  (iterated SHA-256), paramq.fg (parameterized queries), valid2.fg
  (email/URL/enum/range/sanitize), conv1d.fg (1-D convolution, the
  missing nn layer), all verified 4/4.

- Sprint batch 6 (21 Nov 2026, same day, LIBS ONLY): 20 new libraries,
  all verified 4/4: esc.fg (auto-escaping templates, the batch-5
  near-miss fixed), stdio.fg (stdin + stderr), logfmt.fg (structured
  logs), rope.fg (rotary embeddings), metrics2.fg (AUC, log-loss,
  top-k, Brier), sklearn2.fg (scaling + k-fold splits), resolver.fg
  (highest satisfying version), semver2.fg (caret/tilde/range
  constraints), dbg.fg ("name = value" helpers), memprof.fg
  (alloc-counter snapshots), flame.fg (flame-graph SVG), health.fg
  (/health JSON), replay.fg (seeded LCG replay), dvc.fg (CRC32
  dataset manifests), ct.fg (constant-time comparison), secrets.fg
  (redaction + zeroing), perms.fg (sandbox flags + path roots),
  lock.fg (lockfile hashes), vuln.fg (vulnerability feed),
  safedeser.fg (length + depth limits before parse).

- Sprint batch 7 (21 Nov 2026, same day, LIBS ONLY): 20 items,
  all verified 4/4: iter.fg (iterator protocol), fsm.fg (state
  machines), schedpol.fg (priority / EDF / lottery picks), elf.fg
  (ELF64 header parsing), ipv6.fg (parse / expand / compress),
  fmtcrc.fg ("len:payload:crc" records), cancel.fg (cancellation
  tokens), sema.fg (counting permits), deadlock.fg (wait-for-graph
  cycle detection), bpstrat.fg (drop_new / drop_oldest /
  keep_latest), timerwheel.fg (due-tick firing), paramtest.fg
  (table-driven cases), doubles.fg (spy call recording), flaky.fg
  (flaky = both outcomes in history), contract.fg (method/path/
  required-field contracts), depcheck.fg (exact (name, version)
  vulnerability audit), license.fg (allowed-license enforcement),
  tasks.fg (Kahn topological order + ready sets), flags.fg (named
  on/off switches), lint.fg (#351 flip — already in the tree).

- Sprint batch 8 (21 Nov 2026, same day, LIBS ONLY): 20 items,
  all verified 4/4: imporg.fg (import sort + dedupe),
  complexity.fg (cyclomatic complexity), unsafecheck.fg (unchecked
  ops per file), docsym.fg (file outline), callhier.fg (callers /
  callees), wsym.fg (workspace symbol search), doccomment.fg (///
  doc entries), todotrack.fg (TODO/FIXME marks), casestyle.fg
  (snake_case / CamelCase), ffibind.fg (C to extern bindings),
  schemagen.fg (.proto to structs), simd.fg (width-4 vector ops),
  grapheme.fg (cluster segmentation), tensor2.fg (dtype-tagged
  tensors), autograd2.fg (tape freeing + div/exp/log), onnx.fg
  (#436 flip, already in the tree), signrel.fg (keyed signatures),
  docgen2.fg (examples + cross-links), bpstream.fg (backpressured
  streams), typedchan.fg (float + bool channels).

- Sprint batch 9 (21 Nov 2026, same day, LIBS ONLY): 20 flips,
  all verified 4/4 (84/84 checks, 21 demos): srcgen.fg
  (annotation-driven builder generation), genspec.fg (per-type
  specialized names), typemeta.fg (recursive type-level
  evaluator), ccpass.fg (substring + max-length passes),
  astapi.fg (fn/struct/let nodes, whole-word rename),
  typehier.fg ("Trait:Struct" implementor registry),
  extractfn.fg (fn text + call site), cov.fg (line/branch
  coverage), mock.fg (#306 flip, mock-lite since 2 Nov 2026),
  itharness.fg (setup-aware cases), muttest.fg (operator-swap
  mutants), loadtest.fg (users/ramp/duration/rps plan),
  golden.fg (golden vs actual diffs), doctest.fg ("/// >>>"
  extraction + checks), workspace.fg (member registry + edges),
  buildprof.fg (dev vs release), triple.fg (#326 triples landed,
  sysroots still missing — stays PARTIAL, not a flip), incr.fg
  (FNV-1a fingerprints, rebuild list), buildcache.fg (key-list
  cache), vendor.fg (vendor/<name>-<version> paths), unused.fg
  (defined-but-never-used lets). HAVE 230 -> 250 (50% of 500).

- Sprint batch 10 (21 Nov 2026, same day, LIBS ONLY): 20 flips,
  all verified 4/4 (80/80 checks, 20 demos): unreach.fg
  (statements after the first return), godef.fg (definition index,
  first definition wins — closes the #363 PARTIAL), findrefs.fg
  (every use, first-seen order), complete.fg (prefix completions),
  sighelp.fg (signature text + params), semhl.fg (token
  classifier), inlay.fg ("name: type" hints), replhist.fg
  (multiline input + history cursor — closes the #379 PARTIAL),
  notebook.fg (md/code cells, exec numbers), bp.fg (breakpoint
  registry, next-hit scan), clayout.fg (C field offsets),
  marshal.fg (ASCII encode/decode), plugin.fg (plugin registry),
  cheader.fg (C declarations + include guard), hover.fg (hover
  info — closes the known LSP hover gap), dce.fg (BFS reachability,
  dead functions), intern.fg (one id per string), sso.fg (15-char
  inline cutoff), consteval.fg (integer const folds),
  determin.fg (recorded runs are consistent). HAVE 250 -> 270
  (54% of 500).

- Sprint batch 11 (21 Nov 2026, same day, LIBS ONLY): 20 flips,
  all verified 4/4 (80/80 checks, 20 demos): threat.fg
  (threat-model table, worst-risk ranking), reflect.fg (runtime
  type information registry), annot.fg (#[...] metadata rows),
  cfg.fg (target descriptor, os=/arch=/mode=/feat=/not:
  predicates), alias.fg (import x as y, conflicts recorded),
  reexport.fg (pub use table with resolution), strinterp.fg
  ("hello {name}" substitution, {{ and }} escape), mlstr.fg
  (triple-quote blocks: join, dedent, trim blank), rawstr.fg
  (raw/cooked string conversion), memo.fg (named-operation memo
  table, hit/miss counters), recdepth.fg (depth guard, overflow
  counting), naninf.fg (NaN != itself, inf - inf is NaN),
  connpool.fg (named-connection pool, idle eviction), future.fg
  (pending/ready futures), latch.fg (countdown latch),
  evloop.fg (FIFO event loop), observ.fg (topic subscriptions),
  taskgroup.fg (task groups with done tracking), zerocopy.fg
  (shared-buffer views, copies stay 0), covfuzz.fg (LCG
  mutational fuzzer over the ABCD-prefix target; seed 42, 60
  steps, edges 1/0/2/3 found). HAVE 270 -> 290 (58% of 500).
- Sprint batch 12 (21 Nov 2026, same day, LIBS ONLY): 20 flips,
  all verified 4/4 (80/80 checks, 20 demos): cachelay.fg
  (cache-aware field reordering, offsets/total/padding/lines),
  chaincmp.fg (chained comparisons, first-fail index),
  derive.fg ((type, trait) derive registry), cap.fg
  (unforgeable capability tokens from 1000), promise.fg
  (all/race over the future table), units.fg (dimensional
  checking closes #177 PARTIAL), svcdisc.fg (service registry,
  first-healthy lookup), mutex.fg (mutex + rw locks), atomic.fg
  (fetch_add, CAS, inc/dec), threadpool.fg (round-robin pool,
  makespan), worksteal.fg (per-worker deques, LIFO pop, front
  steal), actor.fg (FIFO mailboxes), testpar.fg (LPT sharding,
  makespan, speedup), relbin.fg (per-triple release manifest),
  container.fg (image layer stack), repro.fg (reproducible-
  build log), rename.fg (rename-all symbol table), codeact.fg
  (code-action table), dap.fg (DAP request/response table),
  watchpt.fg (watchpoints, always/eq:N). HAVE 290 -> 310 (62% of 500).
- Sprint batch 13 (21 Nov 2026, same day, LIBS ONLY): 20 flips,
  all verified 4/4 (80/80 checks, 20 demos): triple.fg
  (sysroot registry closes #326 PARTIAL), numtrait.fg
  (numeric-trait registry), mntask.fg (round-robin scheduler
  over the task table, closes #241 PARTIAL), rtimer.fg
  (clock-driven timers, closes #263 PARTIAL), bce.fg
  (bounds-proof analysis, closes #402 PARTIAL), lspfmt.fg
  (LSP formatting as a library, closes #369 PARTIAL),
  condvar.fg (wait/notify), stm.fg (transaction table,
  version-checked commit), rcu.fg (grace-period reclaim),
  racedet.fg (lockset race detection), loom.fg
  (interleaving explorer, distinct finals), select.fg
  (first-ready select), sampleprof.fg (sample aggregation),
  heapdump.fg (reachable walk, leak bytes/count), revdbg.fg
  (clamped step-back/step-forward), crashrep.fg
  (symbolication), repldbg.fg (live variable table, one-op
  eval), publish.fg (publish records, version validation),
  devshell.fg (FNV-1a derivation hash), stdlibfuzz.fg (LCG
  fuzz driver, exact ok-counts). HAVE 310 -> 330 (66% of 500).
- Sprint batch 14 (21 Nov 2026, same day, LIBS ONLY): 15 flips,
  all verified 4/4 (60/60 checks, 15 demos): pariter.fg
  (chunk split + named int-op map, modelled parallelism),
  proptest.fg (LCG cases, halving shrink, smallest failing),
  buildgen.fg ({name} substitution), cigate.fg (fmt gate,
  closes #352 PARTIAL), inlinean.fg (inline-candidate
  analysis), unroll.fg (unroll-factor analysis), loopvec.fg
  (auto-vectorization analysis), escape.fg (escape analysis),
  pgo.fg (profile-guided decisions), regalloc.fg (linear-scan
  register allocation, 4 regs), sched.fg (list scheduling,
  makespan), benchtune.fg (bench verdicts at +/-10%),
  xhover.fg (cross-language hover tables), lto.fg
  (cross-module dead/inline analysis), allocfree.fg
  (alloc-free loop analysis). HAVE 330 -> 345 (69% of 500).
