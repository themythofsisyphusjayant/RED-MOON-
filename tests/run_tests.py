#!/usr/bin/env python3
"""Forge v2 test suite. Run from ~/workspace/forge-v2: python3 tests/run_tests.py"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = os.path.join(ROOT, "forge.py")


def run_forge(*args):
    return subprocess.run([sys.executable, FORGE, *args],
                          capture_output=True, text=True, cwd=ROOT)


def main():
    failures = []

    def expect(path, expected, mode="safe"):
        r = run_forge("run", path, "--mode", mode) if mode != "safe" else run_forge("run", path)
        if r.returncode != 0 or r.stdout != expected:
            failures.append(f"{path} ({mode}): expected {expected!r}, got rc={r.returncode} "
                            f"out={r.stdout!r} err={r.stderr!r}")

    expect("examples/hello2.fg",
           "sum = 7.5 len = 3\ni = 0 xs[i] = 1.5\ni = 1 xs[i] = 2.5\ni = 2 xs[i] = 3.5\n"
           "sqrt(2) = 1.41421 exp(1) = 2.71828\n")
    expect("examples/matrix.fg", "58 64 139 154 \ndot = 217\n")
    # Structs: distance 3-4-5, then field assignment to 6-4.
    expect("examples/structs_point.fg",
           "distance = 5\nq.x = 6 q.y = 4\ndistance = 7.2111\n")
    # String builtins + stdlib + ecosystem example.
    expect("examples/strings_demo.fg",
           "parts = 3 b\njoined = a-b-c\nsub = world\ntrim = hi\n"
           "starts = true\nends = true\n")
    # Enums + match + assert.
    expect("examples/enums_match.fg", "green\nother\n")
    # Spawn: both workers must finish (main joins them).
    r = run_forge("run", "examples/spawn_demo.fg")
    for needle in ("main done, waiting for workers", "worker done 1", "worker done 2"):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"spawn_demo: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    # Structured concurrency: a scope joins its tasks before the
    # code after it runs, so ordering (not just presence) is the
    # assertion. Nested scopes, return, break, transitive spawns
    # (a callee spawning inside a scope), and `scope` still working
    # as an ordinary variable name are all covered.
    def check_order(name, path, pairs, absent=(), mode="safe"):
        rr = run_forge("run", path, "--mode", mode) if mode != "safe" else run_forge("run", path)
        if rr.returncode != 0:
            failures.append(f"{name} ({mode}): exit {rr.returncode} err={rr.stderr!r}")
            return
        for first, second in pairs:
            if rr.stdout.find(first) < 0 or rr.stdout.find(second) < 0 \
                    or rr.stdout.find(first) > rr.stdout.find(second):
                failures.append(f"{name} ({mode}): expected {first!r} before {second!r} "
                                f"in {rr.stdout!r}")
        for needle in absent:
            if needle in rr.stdout:
                failures.append(f"{name} ({mode}): unexpected {needle!r} in {rr.stdout!r}")
    check_order("scope_demo", "examples/scope_demo.fg",
                [("worker done 1", "after scope"),
                 ("worker done 2", "after scope")])
    check_order("scope_demo", "examples/scope_demo.fg",
                [("worker done 1", "after scope"),
                 ("worker done 2", "after scope")], mode="fast")
    check_order("scope_nested", "tests/scope_nested.fg",
                [("inner done", "inner joined"),
                 ("inner joined", "outer joined"),
                 ("outer done", "outer joined")])
    check_order("scope_return", "tests/scope_return.fg",
                [("worker done", "v = 42"),
                 ("v = 42", "main after")])
    check_order("scope_break", "tests/scope_break.fg",
                [("worker done", "after loop")],
                absent=("in loop after scope",))
    check_order("scope_transitive", "tests/scope_transitive.fg",
                [("worker done", "after scope")])
    expect("tests/scope_ident.fg", "scope = 5\nscope = 6\n")
    # FFI: puts returns length+newline, system returns 0.
    r = run_forge("run", "examples/ffi_demo.fg")
    for needle in ("puts returned 18", "system returned 0"):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"ffi_demo: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    # Map + JSON stdlib.
    expect("examples/map_json_demo.fg",
           "apples = 7\nhas pears = false\ncity = Gorakhpur\n")
    # Generics + Option/Result + tiny DB.
    expect("examples/generics_demo.fg", "42 hi 1.5 7 seven\n")
    expect("examples/option_result_demo.fg",
           "opt = 42\nnone = 99\ndiv = 5\nerror = division by zero\n")
    expect("examples/db_demo.fg", "user = jayant\nlang = Forge\n")
    # ? operator, generic enums, table DB.
    expect("examples/try_demo.fg",
           "opt ok = 43\nopt none present = false\ncalc error = div by zero\n")
    expect("examples/generic_enums_demo.fg", "some 42\nnone\nerr div by zero\n")
    expect("examples/table_demo.fg",
           "rows = 3\ngorakhpur rows = 2\nfirst = jayant second = teju\n")
    # SQL, WASM is tested separately (node), GC counters.
    expect("examples/sql_demo.fg",
           "gorakhpur = 2 jayant teju\nolder = 2 jayant teju\nall = 3\n")
    expect("examples/gc_demo.fg", "g = hello\nallocs = 103 frees = 101\n")
    expect("examples/gc_array_demo.fg",
           "loop arr = 4 5\narr allocs = 101 arr frees = 100\nshared b = 4 5\nstruct arr = 4 5\n")
    expect("examples/kernel_demo.fg", "parallel dot = 70\nmatmul = 19 22 43 50\n")
    expect("examples/gc_struct_demo.fg",
           "person = b 2 3\nstr allocs = 101 str frees = 100\narr allocs = 101 arr frees = 100\nshared q = b 2 3\n")
    expect("examples/qasida_demo.fg",
           "Qasida\nSafe. Simple. Natively fast.\n")
    expect("examples/dates_rand_demo.fg",
           "epoch = 0\n2026-10-26 minus 2026-01-01 = 298\nleap 2024 = true\nleap 2025 = false\nfeb 2024 = 29\nrand seed = 1250496048\nrand float = 0.610197\n")
    expect("examples/tensor_demo.fg",
           "matmul = 19 22 43 50\ntranspose = 1 3 2 4\nadd sum = 36\n"
           "reshape = 1 4\nget2 = 3\nsoftmax sum = 1\nargmax = 1\n")
    expect("examples/autograd_demo.fg",
           "f = 21.9526\ndfdx = 10.0452\ndfdy = 3\nnumeric dfdx = 10.0452\n")
    expect("examples/nn_demo.fg",
           "linear out len = 2\nlayernorm mean-ish = 0\nadam step = 1 p0 = 0.99\n"
           "lr cosine = 0.01\nlr step = 0.0025\nclip norm = 2.5\n"
           "ckpt saved = true\nckpt = 0.5 -0.25 1.5\n"
           "quant scale = 0.00787402 max err = 0.00590551\ngreedy = 1\ntopk = 1\n"
           "int_to_str = -42\nfloat_to_fixed = -3.141\n")
    expect("examples/tokenizer_demo.fg",
           "char vocab = helo wrd\nchar ids len = 23\n"
           "char roundtrip = hello world hello world\nbpe merges = 5\n"
           "bpe ids len = 13\nbpe roundtrip = hello world hello world\n"
           "windows = 19\ntrain + test = 19\nbatch = 3\nshuffled = 19\n")
    expect("examples/gpt_scaled_forward_demo.fg",
           "params = 5200\nlogits = 464\nloss = 4.1355\ngraph nodes = 183940\n")
    expect("examples/tinystories_load_demo.fg",
           "words = 24000 vocab = 500\nfirst word = the last word = <unk>\n"
           "first id = 22 id 100 = 196\n")
    expect("examples/gpt_forward_demo.fg",
           "params = 776\nlogits = 96\nloss = 2.89085\ngraph nodes = 13886\n")
    expect("examples/imported_demo.fg",
           "tok = 0.5 -0.25 1 0\nln1_g = 1 1\n")
    # Inference: KV-cache must match full forward exactly (diff 0).
    r = run_forge("run", "examples/inference_demo.fg")
    for needle in ("full last =", "kv last =", "kv diff = 0", "cache len = 3",
                   "quant step max diff ="):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"inference_demo: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    # Tensor autograd: gradient checks must pass (the demo
    # fails itself if any analytic-vs-numeric diff > 0.01).
    r = run_forge("run", "examples/tensor_autograd_demo.fg")
    for needle in ("part A nodes = 5", "part B nodes = 9",
                   "max grad diff ="):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"tensor_autograd_demo: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    # KV-cache for the gpt2 layout: must match full forward
    # to 1e-9 (the demo fails itself otherwise).
    r = run_forge("run", "examples/inference_gpt2_demo.fg")
    for needle in ("kv2 diff =", "kv2 cache len = 4"):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"inference_gpt2_demo: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    # Tensor GPT on TinyStories: the full small training run
    # (6.5 s of training inside a ~20 s program run).
    r = run_forge("run", "examples/tgt_tinystories.fg")
    for needle in ("params = 12608", "tensor forward nodes = 100",
                   "test loss after ="):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"tgt_tinystories: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    # 0.6.0 ecosystem: new tensor ops (sigmoid/tanh/
    # mse/maxpool) with gradient checks, import dedup,
    # RNN/CNN/classical/iris/checkpoint/dev demos.
    r = run_forge("run", "examples/tensor_ops2_demo.fg")
    for needle in ("sigmoid max grad diff =", "tanh max grad diff =",
                   "maxpool winner grad sum =", "tensor ops2 ok"):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"tensor_ops2_demo: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    r = run_forge("run", "examples/import_dedup_demo.fg")
    for needle in ("dedup ok loss = 0.693147", "adam first = 0.99"):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"import_dedup_demo: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    r = run_forge("run", "examples/rnn_demo.fg")
    for needle in ("rnn acc after = 1", "rnn ok"):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"rnn_demo: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    r = run_forge("run", "examples/cnn_demo.fg")
    for needle in ("cnn acc after = 1", "cnn ok"):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"cnn_demo: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    r = run_forge("run", "examples/ml_classical_demo.fg")
    for needle in ("kmeans purity = 1", "knn acc = 1", "logreg acc = 1",
                   "classical ok"):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"ml_classical_demo: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    r = run_forge("run", "examples/iris_pipeline_demo.fg")
    for needle in ("iris rows = 150 cols = 4", "iris test acc = 0.933333",
                   "iris ok"):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"iris_pipeline_demo: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    r = run_forge("run", "examples/tensor_checkpoint_demo.fg")
    for needle in ("ckpt saved = true", "ckpt loss diff = 0", "ckpt ok"):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"tensor_checkpoint_demo: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    r = run_forge("run", "examples/dev_demo.fg", "--",
                  "--lr=0.05", "--epochs=40", "input.txt")
    for needle in ("dev ok",):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"dev_demo: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    if "this info is filtered out" in r.stdout:
        failures.append("dev_demo: logger failed to filter info")
    # Fuzzer smoke: 5 fixed seeds, hermetic (temp dir
    # only, no corpus writes). Longer runs are manual
    # (see tools/fuzz.py); ~4 s per seed, so the suite
    # keeps this small on purpose.
    r = subprocess.run([sys.executable, "tools/fuzz.py",
                        "--seeds", "5", "--start", "0"],
                       capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0 or "no failures" not in r.stdout:
        failures.append(f"fuzz smoke failed: {r.stdout!r} {r.stderr!r}")
    # Debugger: --debug must emit #line directives for
    # BOTH the main file and an imported helper file.
    c_path = os.path.join(ROOT, "dbg_demo_test.c")
    bin_path = os.path.join(ROOT, "dbg_demo_test")
    for p in (c_path, bin_path):
        try:
            os.unlink(p)
        except FileNotFoundError:
            pass
    # 0.7.0: image loading (BMP + PPM agree) and the
    # stacked-conv net (im2col grad check + training).
    r = run_forge("run", "examples/image_demo.fg")
    for needle in ("bmp px0 = 255 0 0", "bmp==ppm ? true", "image ok"):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"image_demo: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    r = run_forge("run", "examples/cnn_stacked_demo.fg")
    for needle in ("im2col max grad diff =", "stacked acc after = 1",
                   "stacked cnn ok"):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"cnn_stacked_demo: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    # 0.7.0: curriculum RNN (len-8 wall cracked by
    # staging) and the self-hosting front-end proto.
    r = run_forge("run", "examples/rnn_curriculum_demo.fg")
    for needle in ("curriculum len8 = 1", "curriculum ok"):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"rnn_curriculum_demo: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    r = run_forge("run", "examples/selfhost_mini.fg")
    for needle in ("selfhost result = 29", "selfhost ok"):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"selfhost_mini: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    # 0.7.0: big32 struct + soft-float demos must at
    # least compile to hex (execution is verified
    # manually against the big32 model + Verilog,
    # which live outside this repo).
    import tempfile
    for demo in ("big32_struct_demo", "big32_float_demo"):
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, demo)
            r = run_forge("build", f"examples/{demo}.fg",
                          "--target", "big32", "-o", out)
            if r.returncode != 0 or not os.path.exists(out + ".hex"):
                failures.append(f"{demo} big32 build failed: {r.stdout!r} {r.stderr!r}")
    # 0.7.0: WASM strings demo — build, run under
    # node, read the stdout buffer, compare with the
    # native run. Skipped only when node is absent.
    import shutil
    if shutil.which("node") is not None:
        with tempfile.TemporaryDirectory() as td:
            wasm_path = os.path.join(td, "wasm_strings.wasm")
            r = run_forge("build", "examples/wasm_strings_demo.fg",
                          "--target", "wasm", "-o", wasm_path)
            if r.returncode != 0:
                failures.append(f"wasm_strings build failed: {r.stdout!r} {r.stderr!r}")
            else:
                reader = (
                    "import(\"node:fs\").then(async ({ readFileSync }) => {"
                    " const { instance } = await WebAssembly.instantiate("
                    "readFileSync(process.argv[1]), {});"
                    " instance.exports.main();"
                    " const mem = new Uint8Array(instance.exports.memory.buffer);"
                    " const len = new DataView(mem.buffer).getUint32(0, true);"
                    " process.stdout.write(new TextDecoder().decode("
                    "mem.subarray(8, 8 + len))); });")
                r2 = subprocess.run(["node", "-e", reader, wasm_path],
                                    capture_output=True, text=True, cwd=ROOT)
                r3 = run_forge("run", "examples/wasm_strings_demo.fg")
                if r2.returncode != 0 or r2.stdout != r3.stdout:
                    failures.append(f"wasm_strings output mismatch: wasm={r2.stdout!r} "
                                    f"native={r3.stdout!r} err={r2.stderr!r}")
    r = run_forge("build", "examples/dbg_demo.fg", "--debug",
                  "--keep-c", c_path, "-o", bin_path)
    if r.returncode != 0:
        failures.append(f"dbg build failed: {r.stdout!r} {r.stderr!r}")
    else:
        c_text = open(c_path, encoding="utf-8").read()
        for needle in ('#line', "dbg_demo.fg", "dbg_helper.fg"):
            if needle not in c_text:
                failures.append(f"dbg_demo.c missing {needle!r}")
        r2 = subprocess.run([bin_path], capture_output=True, text=True)
        if r2.returncode != 0 or "dbg = 42" not in r2.stdout:
            failures.append(f"dbg binary failed: {r2.stdout!r} {r2.stderr!r}")
    for p in (c_path, bin_path):
        try:
            os.unlink(p)
        except FileNotFoundError:
            pass
    # CUDA simulation (Python mirror of the .cu kernels).
    r = subprocess.run([sys.executable, "tools/simulate_cuda.py"],
                       capture_output=True, text=True, cwd=ROOT)
    for needle in ("cuda dot = 70.0", "cuda attention =", "cuda layernorm =",
                   "cuda half matmul = 19.0 22.0 43.0 50.0",
                   "cuda simulation ok"):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"simulate_cuda: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    expect("examples/ml_train_xor.fg",
           "epoch 0 loss = 0.558973\nepoch 10000 loss = 0.000267766\nxor 0 0 = 0 (raw 0.0115718 )\nxor 0 1 = 1 (raw 0.986735 )\nxor 1 0 = 1 (raw 0.989128 )\nxor 1 1 = 0 (raw 0.010358 )\n")
    expect("examples/ecosystem/word_stats.fg",
           "words = 8\nlines = 4\nmean line length = 10.25\n"
           "median line length = 12\n")
    # Formatter: every example/stdlib file must format idempotently
    # and the formatted version must still check.
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from forge_lang.pretty import format_source
    import glob
    for path in sorted(glob.glob("examples/**/*.fg", recursive=True)
                       + glob.glob("forge_lang/stdlib/*.fg")):
        try:
            with open(path, encoding="utf-8") as f:
                original = f.read()
            once = format_source(original)
            twice = format_source(once)
            if once != twice:
                failures.append(f"fmt: {path} is not idempotent")
        except Exception as e:
            failures.append(f"fmt: {path} failed to format: {e}")
    # File I/O + args: writes a file, reads it back, reports args.
    for fname in ("forge_output.txt", "forge_test_out.txt", "nn_ckpt.txt"):
        try:
            os.unlink(os.path.join(ROOT, fname))
        except FileNotFoundError:
            pass
    r = run_forge("run", "examples/file_and_args.fg", "--", "forge_test_out.txt")
    out_path = os.path.join(ROOT, "forge_test_out.txt")
    if r.returncode != 0 or "wrote ok" not in r.stdout or "args count = 1" not in r.stdout:
        failures.append(f"file_and_args failed: {r.stdout!r} {r.stderr!r}")
    elif not os.path.exists(out_path) or open(out_path).read() != "hello from Forge\n":
        failures.append("file_and_args: output file missing or wrong content")
    if os.path.exists(out_path):
        os.unlink(out_path)
    # parse_int via a tiny inline program is covered by check only here;
    # the struct literal must be rejected when a field is missing.
    r = run_forge("check", "tests/bad_struct.fg")
    if r.returncode == 0 or "missing field" not in r.stderr:
        failures.append(f"bad_struct: expected missing-field error, got rc={r.returncode} "
                        f"out={r.stdout!r} err={r.stderr!r}")
    # MLP: check the four XOR verdicts, not the raw sigmoid digits.
    r = run_forge("run", "examples/ml_mlp_xor.fg")
    for needle in ("xor 0 0 = 0", "xor 0 1 = 1", "xor 1 0 = 1", "xor 1 1 = 0"):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"ml_mlp_xor: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    # Regression: w/b must head toward 2/1 and prediction toward 13.
    r = run_forge("run", "examples/ml_linear_regression.fg")
    if r.returncode != 0 or "prediction for x=6:" not in r.stdout:
        failures.append(f"regression failed: {r.stdout!r} {r.stderr!r}")
    # Benchmark must run in both modes and report micros.
    for mode in ("safe", "fast"):
        r = run_forge("run", "examples/benchmark.fg", "--mode", mode)
        if r.returncode != 0 or "micros =" not in r.stdout or "acc = 2997000" not in r.stdout:
            failures.append(f"benchmark ({mode}) failed: {r.stdout!r} {r.stderr!r}")
    # Safety: div by zero and overflow must abort cleanly in safe mode.
    for path, needle in (("tests/safety_div_zero.fg", "division by zero"),
                         ("tests/safety_overflow.fg", "integer overflow"),
                         ("tests/safety_oob.fg", "index out of bounds"),
                         ("tests/safety_str_oob.fg", "index out of bounds"),
                         ("tests/safety_struct_arr_oob.fg", "index out of bounds"),
                         ("tests/safety_nested_oob.fg", "index out of bounds")):
        r = run_forge("run", path)
        if r.returncode == 0 or needle not in r.stderr:
            failures.append(f"{path}: expected abort {needle!r}, got rc={r.returncode} "
                            f"out={r.stdout!r} err={r.stderr!r}")
    # Compile rejections.
    for path, needle in (("tests/bad_type.fg", "declared str"),
                         ("tests/bad_immutable.fg", "immutable"),
                         ("tests/bad_str_index_assign.fg", "cannot assign to a string index"),
                         ("tests/bad_ckeyword_fn.fg", "is a C keyword"),
                         ("tests/bad_ckeyword_let.fg", "is a C keyword")):
        r = run_forge("check", path)
        if r.returncode == 0 or needle not in r.stderr:
            failures.append(f"{path}: expected error {needle!r}, got rc={r.returncode} "
                            f"out={r.stdout!r} err={r.stderr!r}")
    # Fix-ending diagnostics: errors end with a suggested fix, not
    # just a complaint (did-you-mean names, int/float conversions,
    # missing returns).
    for path, needle in (("tests/diag_undef_var.fg", "Did you mean 'count'?"),
                         ("tests/diag_undef_fn.fg", "Did you mean 'println'?"),
                         ("tests/diag_cast.fg", "convert the value with 'value as float'"),
                         ("tests/diag_noreturn.fg", "add a return statement of type int")):
        r = run_forge("check", path)
        if r.returncode == 0 or needle not in r.stderr:
            failures.append(f"{path}: expected fix hint {needle!r}, got rc={r.returncode} "
                            f"out={r.stdout!r} err={r.stderr!r}")
    # LSP smoke test: drives `forge.py lsp` over stdio end to end
    # (initialize, diagnostics, completions, clean shutdown).
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "lsp_smoke.py")],
                       capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0:
        failures.append(f"lsp_smoke: rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")
    # break: while, for, nested loops; break outside a loop is rejected,
    # including inside a function called from a loop.
    expect("examples/break_demo.fg",
           "while total = 3\nfor sum = 6\nnested count = 6\n")
    expect("examples/break_gc_demo.fg", "allocs = 4 frees = 4\n")
    # String indexing: s[i] is a 1-char str (byte indexing).
    expect("examples/str_index_demo.fg",
           "first = h third = l last = o\nexclaim = h!\nfound l at 2\n")
    # Arrays of structs: element get owns a copy, field reads on
    # xs[i] go direct (no leaked sibling fields), set frees the old
    # element, and array free frees element str fields.
    expect("examples/struct_array_demo.fg",
           "count = 2\nsecond = 3 4 b\nsums = 4 6\nafter push = 3 c\n"
           "after set = 10 z\ncopy = 3 4 b\n")
    expect("examples/struct_array_gc.fg",
           "inside = 2 a b\narr allocs = 1 arr frees = 1\n"
           "str allocs = 2 str frees = 2\n")
    # Nested arrays: matrices, chained reads/writes, shared rows,
    # row push and row replacement, balanced nested frees.
    expect("examples/nested_array_demo.fg",
           "rows = 2 cols = 3\nm01 = 2 m12 = 6\ntotal = 21\n"
           "after push rows = 3 m20 = 7\nafter set = 20\n"
           "shared row = 40\nafter row set = 10 20\n")
    expect("examples/nested_array_gc.fg",
           "inside = 2 2 3 5\narr allocs = 3 arr frees = 3\n")
    # Check elimination: duplicate checks, guard intervals, and
    # string-index comparisons keep identical results in both modes.
    expect("tests/opt_probe_dedupe.fg", "a = 66\n")
    expect("tests/opt_probe_dedupe.fg", "a = 66\n", "fast")
    expect("tests/opt_probe_guard.fg", "9\n99\n")
    expect("tests/opt_probe_guard.fg", "9\n99\n", "fast")
    expect("tests/opt_guard.fg",
           "s = 9\nt = 1\nd = 5\ne = 0\n")
    expect("tests/opt_guard.fg",
           "s = 9\nt = 1\nd = 5\ne = 0\n", "fast")
    expect("tests/opt_strcmp.fg",
           "a = true\nb = false\nc = true\nd = false\ne = false\nf = false\n")
    expect("tests/opt_strcmp.fg",
           "a = true\nb = false\nc = true\nd = false\ne = false\nf = false\n", "fast")
    # Check elimination must not remove a check that can fire:
    # unproven overflow, reassignment-invalidated guards, guards
    # around loops, out-of-bounds string compares, and duplicate
    # reads must all still abort in safe mode.
    for path, needle in (("tests/opt_guard_overflow.fg", "integer overflow"),
                         ("tests/opt_guard_reassign.fg", "integer overflow"),
                         ("tests/opt_guard_loop.fg", "integer overflow"),
                         ("tests/opt_str_oob.fg", "index out of bounds"),
                         ("tests/opt_dedupe_oob.fg", "index out of bounds")):
        r = run_forge("run", path)
        if r.returncode == 0 or needle not in r.stderr:
            failures.append(f"{path}: expected abort {needle!r}, got rc={r.returncode} "
                            f"out={r.stdout!r} err={r.stderr!r}")
    # The optimizations must actually be present in the emitted C:
    # the duplicate read issues one checked get (the repeat is a
    # direct access), and the guard-proven subtraction issues no
    # forge_sub at all. Only the function bodies are inspected, so
    # the runtime helpers defined in the header do not count.
    import tempfile
    with tempfile.TemporaryDirectory() as _td:
        _c = os.path.join(_td, "probe.c")
        _o = os.path.join(_td, "probe")
        r = run_forge("build", "tests/opt_probe_dedupe.fg", "-o", _o, "--keep-c", _c)
        _src = open(_c).read() if r.returncode == 0 else ""
        _body = _src[_src.index("int main("):] if "int main(" in _src else ""
        if _body.count("forge_int_get(") != 1 or "(xs).data[i]" not in _body:
            failures.append("opt_probe_dedupe: expected 1 checked get + direct repeat, "
                            f"got {_body.count('forge_int_get(')} gets, "
                            f"direct={('(xs).data[i]' in _body)}")
        r = run_forge("build", "tests/opt_probe_guard.fg", "-o", _o, "--keep-c", _c)
        _src = open(_c).read() if r.returncode == 0 else ""
        _start = _src.index("long long h2(") if "long long h2(" in _src else -1
        _body = _src[_start:_src.index("\n}\n", _start)] if _start >= 0 else ""
        if "forge_sub" in _body:
            failures.append("opt_probe_guard: guard-proven subtraction still uses forge_sub")
    for path, needle in (("tests/bad_break.fg", "break outside a loop"),
                         ("tests/bad_break_fn.fg", "break outside a loop")):
        r = run_forge("check", path)
        if r.returncode == 0 or needle not in r.stderr:
            failures.append(f"{path}: expected error {needle!r}, got rc={r.returncode} "
                            f"out={r.stdout!r} err={r.stderr!r}")

    # JalOS: the complete teaching OS demo tour (offline, deterministic).
    expect("examples/os/jalos.fg",
           "JalOS 0.1.0 -- a teaching OS in Qasida\n" +
           "[  OK  ] memory test: 1024 words\n" +
           "created directory: /etc\n" +
           "created directory: /var\n" +
           "created directory: /var/log\n" +
           "created directory: /home\n" +
           "created directory: /home/guest\n" +
           "created directory: /pkg\n" +
           "wrote 0 bytes to /etc/passwd\n" +
           "wrote 0 bytes to /var/log/syslog\n" +
           "wrote 115 bytes to /README\n" +
           "[  OK  ] mounted rootfs\n" +
           "[  OK  ] init: syslogd, cron, netd started\n" +
           "jalos login: root (uid 0)\n" +
           "root@jalos:~# echo Welcome to JalOS\n" +
           "Welcome to JalOS\n" +
           "root@jalos:~# uname\n" +
           "JalOS qasida-kernel 0.1.0 x86_64-sim\n" +
           "root@jalos:~# hostname\n" +
           "jalos\n" +
           "root@jalos:~# whoami\n" +
           "root\n" +
           "root@jalos:~# env\n" +
           "USER=root\n" +
           "HOSTNAME=jalos\n" +
           "SHELL=/bin/jalos\n" +
           "HOME=/root\n" +
           "root@jalos:~# ls /\n" +
           "etc (dir)\n" +
           "var (dir)\n" +
           "home (dir)\n" +
           "pkg (dir)\n" +
           "README\n" +
           "root@jalos:~# ls /etc\n" +
           "passwd\n" +
           "root@jalos:~# cat /etc/passwd\n" +
           "root\n" +
           "guest\n" +
           "\n" +
           "root@jalos:~# cat /README\n" +
           "Welcome to JalOS.\n" +
           "A complete teaching OS written in Qasida.\n" +
           "Try: help, ls, ps, run counter, sched, mem, pkg search\n" +
           "\n" +
           "root@jalos:~# mkdir /home/guest/docs\n" +
           "created directory: /home/guest/docs\n" +
           "root@jalos:~# write /home/guest/docs/note.txt Hello from JalOS\n" +
           "wrote 16 bytes to /home/guest/docs/note.txt\n" +
           "root@jalos:~# ls /home/guest/docs\n" +
           "note.txt\n" +
           "root@jalos:~# cat /home/guest/docs/note.txt\n" +
           "Hello from JalOS\n" +
           "root@jalos:~# cp /home/guest/docs/note.txt /home/guest/docs/copy.txt\n" +
           "copied.\n" +
           "root@jalos:~# ls /home/guest/docs\n" +
           "note.txt\n" +
           "copy.txt\n" +
           "root@jalos:~# mv /home/guest/docs/copy.txt /home/guest/docs/moved.txt\n" +
           "moved.\n" +
           "root@jalos:~# ls /home/guest/docs\n" +
           "note.txt\n" +
           "moved.txt\n" +
           "root@jalos:~# su guest guest\n" +
           "switched to guest\n" +
           "guest@jalos:~# whoami\n" +
           "guest\n" +
           "guest@jalos:~# write /README hacked\n" +
           "write: permission denied\n" +
           "guest@jalos:~# su root root\n" +
           "switched to root\n" +
           "root@jalos:~# whoami\n" +
           "root\n" +
           "root@jalos:~# mem\n" +
           "memory: total = 1024 words, free = 1024 used = 0 blocks = 1\n" +
           "root@jalos:~# malloc 16\n" +
           "malloc: 16 words at 1\n" +
           "root@jalos:~# malloc 32\n" +
           "malloc: 32 words at 18\n" +
           "root@jalos:~# mem\n" +
           "memory: total = 1024 words, free = 974 used = 50 blocks = 3\n" +
           "root@jalos:~# free 1\n" +
           "freed 1\n" +
           "root@jalos:~# mem\n" +
           "memory: total = 1024 words, free = 991 used = 33 blocks = 3\n" +
           "root@jalos:~# run counter\n" +
           "spawned pid 1 counter prio 5\n" +
           "root@jalos:~# run fibber\n" +
           "spawned pid 2 fibber prio 5\n" +
           "root@jalos:~# run sorter\n" +
           "spawned pid 3 sorter prio 3\n" +
           "root@jalos:~# run printer\n" +
           "spawned pid 4 printer prio 8\n" +
           "root@jalos:~# run idler\n" +
           "spawned pid 5 idler prio 1\n" +
           "root@jalos:~# ps\n" +
           "pid 1 counter ready ticks 0 result 0 user root\n" +
           "pid 2 fibber ready ticks 0 result 0 user root\n" +
           "pid 3 sorter ready ticks 0 result 0 user root\n" +
           "pid 4 printer ready ticks 0 result 0 user root\n" +
           "pid 5 idler ready ticks 0 result 0 user root\n" +
           "root@jalos:~# sched\n" +
           "printer: printer says hello 0\n" +
           "tick 1 : pid 4 printer step 1 running\n" +
           "printer: printer says hello 1\n" +
           "tick 2 : pid 4 printer step 2 running\n" +
           "printer: printer says hello 2\n" +
           "tick 3 : pid 4 printer step 3 done\n" +
           "tick 4 : pid 1 counter step 1 running\n" +
           "tick 5 : pid 1 counter step 2 running\n" +
           "tick 6 : pid 1 counter step 3 running\n" +
           "tick 7 : pid 1 counter step 4 running\n" +
           "tick 8 : pid 1 counter step 5 done\n" +
           "tick 9 : pid 2 fibber step 1 running\n" +
           "tick 10 : pid 2 fibber step 2 running\n" +
           "tick 11 : pid 2 fibber step 3 running\n" +
           "tick 12 : pid 2 fibber step 4 running\n" +
           "tick 13 : pid 2 fibber step 5 running\n" +
           "tick 14 : pid 2 fibber step 6 running\n" +
           "tick 15 : pid 2 fibber step 7 running\n" +
           "tick 16 : pid 2 fibber step 8 running\n" +
           "tick 17 : pid 2 fibber step 9 running\n" +
           "tick 18 : pid 2 fibber step 10 running\n" +
           "tick 19 : pid 2 fibber step 11 running\n" +
           "tick 20 : pid 2 fibber step 12 done\n" +
           "tick 21 : pid 3 sorter step 1 running\n" +
           "tick 22 : pid 3 sorter step 2 running\n" +
           "tick 23 : pid 3 sorter step 3 running\n" +
           "tick 24 : pid 3 sorter step 4 running\n" +
           "tick 25 : pid 3 sorter step 5 running\n" +
           "tick 26 : pid 3 sorter step 6 running\n" +
           "tick 27 : pid 3 sorter step 7 done\n" +
           "tick 28 : pid 5 idler step 1 running\n" +
           "tick 29 : pid 5 idler step 2 done\n" +
           "scheduler: all processes finished\n" +
           "root@jalos:~# ps\n" +
           "pid 1 counter done ticks 5 result 5 user root\n" +
           "pid 2 fibber done ticks 12 result 144 user root\n" +
           "pid 3 sorter done ticks 7 result 1 user root\n" +
           "pid 4 printer done ticks 3 result 3 user root\n" +
           "pid 5 idler done ticks 2 result 0 user root\n" +
           "root@jalos:~# top\n" +
           "pid 2 fibber done ticks 12 result 144 user root\n" +
           "pid 3 sorter done ticks 7 result 1 user root\n" +
           "pid 1 counter done ticks 5 result 5 user root\n" +
           "pid 4 printer done ticks 3 result 3 user root\n" +
           "pid 5 idler done ticks 2 result 0 user root\n" +
           "root@jalos:~# df\n" +
           "filesystem: files = 13 content chars = 275\n" +
           "root@jalos:~# ping localhost\n" +
           "reply from 127.0.0.1: bytes=32 time<1ms TTL=64\n" +
           "reply from 127.0.0.1: bytes=32 time<1ms TTL=64\n" +
           "reply from 127.0.0.1: bytes=32 time<1ms TTL=64\n" +
           "reply from 127.0.0.1: bytes=32 time<1ms TTL=64\n" +
           "ping statistics: 4 transmitted, 4 received, 0% loss (loopback, simulated)\n" +
           "root@jalos:~# ifconfig\n" +
           "lo: inet 127.0.0.1 (loopback)\n" +
           "eth0: inet 10.0.2.15 (via host NAT, simulated)\n" +
           "root@jalos:~# pkg search\n" +
           "units 0.1.0\n" +
           "money 0.1.0\n" +
           "geometry 0.1.0\n" +
           "interest 0.1.0\n" +
           "roman 0.1.0\n" +
           "bases 0.1.0\n" +
           "dice 0.1.0\n" +
           "percentages 0.1.0\n" +
           "loans 0.1.0\n" +
           "bmi 0.1.0\n" +
           "colors 0.1.0\n" +
           "sorting 0.1.0\n" +
           "search 0.1.0\n" +
           "primes 0.1.0\n" +
           "factors 0.1.0\n" +
           "statistics 0.1.0\n" +
           "grades 0.1.0\n" +
           "tax 0.1.0\n" +
           "cooking 0.1.0\n" +
           "budget 0.1.0\n" +
           "checks 0.1.0\n" +
           "morse 0.1.0\n" +
           "textstats 0.1.0\n" +
           "speed 0.1.0\n" +
           "data 0.1.0\n" +
           "angle 0.1.0\n" +
           "fractions 0.1.0\n" +
           "vectors 0.1.0\n" +
           "matrices 0.1.0\n" +
           "polynomials 0.1.0\n" +
           "root@jalos:~# pkg list\n" +
           "root@jalos:~# services\n" +
           "cron    running  (system scheduler daemon)\n" +
           "syslog  running  (logging daemon, /var/log/syslog)\n" +
           "netd    running  (network daemon, loopback + host NAT)\n" +
           "pkgd    stopped  (package daemon, starts on pkg install)\n" +
           "root@jalos:~# logger JalOS demo finished\n" +
           "root@jalos:~# cat /var/log/syslog\n" +
           "boot: kernel started\n" +
           "boot: init done\n" +
           "cron: heartbeat\n" +
           "cron: heartbeat\n" +
           "cron: heartbeat\n" +
           "cron: heartbeat\n" +
           "cron: heartbeat\n" +
           "JalOS demo finished\n" +
           "\n" +
           "root@jalos:~# history\n" +
           "0 echo Welcome to JalOS\n" +
           "1 uname\n" +
           "2 hostname\n" +
           "3 whoami\n" +
           "4 env\n" +
           "5 ls /\n" +
           "6 ls /etc\n" +
           "7 cat /etc/passwd\n" +
           "8 cat /README\n" +
           "9 mkdir /home/guest/docs\n" +
           "10 write /home/guest/docs/note.txt Hello from JalOS\n" +
           "11 ls /home/guest/docs\n" +
           "12 cat /home/guest/docs/note.txt\n" +
           "13 cp /home/guest/docs/note.txt /home/guest/docs/copy.txt\n" +
           "14 ls /home/guest/docs\n" +
           "15 mv /home/guest/docs/copy.txt /home/guest/docs/moved.txt\n" +
           "16 ls /home/guest/docs\n" +
           "17 su guest guest\n" +
           "18 whoami\n" +
           "19 write /README hacked\n" +
           "20 su root root\n" +
           "21 whoami\n" +
           "22 mem\n" +
           "23 malloc 16\n" +
           "24 malloc 32\n" +
           "25 mem\n" +
           "26 free 1\n" +
           "27 mem\n" +
           "28 run counter\n" +
           "29 run fibber\n" +
           "30 run sorter\n" +
           "31 run printer\n" +
           "32 run idler\n" +
           "33 ps\n" +
           "34 sched\n" +
           "35 ps\n" +
           "36 top\n" +
           "37 df\n" +
           "38 ping localhost\n" +
           "39 ifconfig\n" +
           "40 pkg search\n" +
           "41 pkg list\n" +
           "42 services\n" +
           "43 logger JalOS demo finished\n" +
           "44 cat /var/log/syslog\n" +
           "45 history\n" +
           "root@jalos:~# shutdown\n" +
           "JalOS halted. Goodbye.\n")

    if failures:
        print(f"FAIL: {len(failures)} failure(s)")
        for f in failures:
            print(" -", f)
        return 1
    print("PASS: all Forge v2 tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
