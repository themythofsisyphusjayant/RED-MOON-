"""Top-500 #75: retry with backoff and jitter (tests/test_retry_v1.py).
Retry policy math, pure Qasida in forge_lang/stdlib/retry.fg:
exponential backoff (delay before attempt N is base_ms *
factor^(N-1), capped at max_ms; attempt >= max_attempts means no
more retries, delay 0), a deterministic LCG jitter in
[-jitter_ms, +jitter_ms] clamped at 0, and a should-retry
predicate. No sleeping, no real attempts — the policy math only,
so every expected value is hand-computed from the same rules.
Native-only in v1 in the sense that no big32/WASM gate applies:
the library uses no tuples, so those checks are not run.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

IMP = 'import "retry.fg";\n'

DEMO_EXPECTED = ("100\n200\n400\n100\n200\n400\n0\ntrue\ntrue\nfalse\n"
                 "103\n182\n")

# (name, program, expected stdout) — must run clean.
OK_CASES = [
    ("cap kicks in: base 100 factor 10 max 500 -> 100, 500, 500",
     IMP + "fn main() {\n"
     "  let p: RetryPolicy = retry_policy(4, 100, 10, 500, 0);\n"
     "  let ds: [int] = retry_delays(p);\n"
     "  for d in ds {\n    println(d);\n  }\n"
     "  println(retry_delay(p, 2));\n  println(retry_delay(p, 3));\n}\n",
     "100\n500\n500\n500\n500\n"),
    ("factor 1 gives constant delays",
     IMP + "fn main() {\n"
     "  let p: RetryPolicy = retry_policy(3, 50, 1, 1000, 0);\n"
     "  let ds: [int] = retry_delays(p);\n"
     "  for d in ds {\n    println(d);\n  }\n}\n",
     "50\n50\n"),
    ("max_attempts 1: empty delay list, no retry, delay 0",
     IMP + "fn main() {\n"
     "  let p: RetryPolicy = retry_policy(1, 100, 2, 1000, 0);\n"
     "  let ds: [int] = retry_delays(p);\n"
     "  println(len(ds));\n"
     "  println(retry_should_retry(p, 1));\n"
     "  println(retry_delay(p, 1));\n}\n",
     "0\nfalse\n0\n"),
    ("jitter is deterministic: same seed twice, other seeds differ",
     IMP + "fn main() {\n"
     "  println(retry_jitter(42, 100, 10));\n"
     "  println(retry_jitter(42, 100, 10));\n"
     "  println(retry_jitter(43, 100, 10));\n}\n",
     "103\n103\n99\n"),
    ("jitter clamps at 0 for a tiny delay and a large negative offset",
     IMP + "fn main() {\n"
     "  println(retry_jitter(0, 5, 100));\n"
     "  println(retry_jitter(0, 100, 10));\n}\n",
     "0\n90\n"),
    ("base 0 gives all-zero delays",
     IMP + "fn main() {\n"
     "  let p: RetryPolicy = retry_policy(3, 0, 2, 1000, 0);\n"
     "  let ds: [int] = retry_delays(p);\n"
     "  for d in ds {\n    println(d);\n  }\n"
     "  println(retry_delay(p, 1));\n"
     "  println(retry_delay(p, 2));\n}\n",
     "0\n0\n0\n0\n"),
    ("jitter 0 is a passthrough; negative seed folds deterministically",
     IMP + "fn main() {\n"
     "  println(retry_jitter(42, 100, 0));\n"
     "  println(retry_jitter(-1, 100, 10));\n}\n",
     "100\n107\n"),
]

# (name, program, expected stderr fragment) — must fail.
FAIL_CASES = [
    ("max_attempts 0 fails",
     IMP + "fn main() {\n"
     "  let p: RetryPolicy = retry_policy(0, 100, 2, 1000, 0);\n"
     "  println(1);\n}\n",
     "retry_policy: max_attempts must be >= 1"),
    ("retry_delay with attempt 0 fails",
     IMP + "fn main() {\n"
     "  let p: RetryPolicy = retry_policy(4, 100, 2, 1000, 0);\n"
     "  println(retry_delay(p, 0));\n}\n",
     "retry_delay: attempt must be >= 1"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "retry_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("retry demo", r.returncode == 0 and r.stdout == DEMO_EXPECTED,
                 f"(rc={r.returncode} out={r.stdout!r} err={r.stderr[:200]!r})"):
        failures.append("retry demo")
    for name, prog, expected in OK_CASES:
        with tempfile.NamedTemporaryFile("w", suffix=".fg", delete=False,
                                        dir=ROOT) as f:
            f.write(prog)
            path = f.name
        try:
            r = run([sys.executable, os.path.join(ROOT, "forge.py"),
                     "run", path], ROOT)
            ok = r.returncode == 0 and r.stdout == expected
            if not check(name, ok,
                         f"(rc={r.returncode} out={r.stdout!r} "
                         f"err={r.stderr[:200]!r})"):
                failures.append(name)
        finally:
            os.unlink(path)
    for name, prog, fragment in FAIL_CASES:
        with tempfile.NamedTemporaryFile("w", suffix=".fg", delete=False,
                                        dir=ROOT) as f:
            f.write(prog)
            path = f.name
        try:
            r = run([sys.executable, os.path.join(ROOT, "forge.py"),
                     "run", path], ROOT)
            ok = r.returncode != 0 and fragment in r.stderr
            if not check(name, ok,
                         f"(rc={r.returncode} out={r.stdout!r} "
                         f"err={r.stderr[:200]!r})"):
                failures.append(name)
        finally:
            os.unlink(path)
    # fmt idempotent on both new files.
    for rel in ("forge_lang/stdlib/retry.fg", "examples/retry_demo.fg"):
        p = os.path.join(ROOT, rel)
        rf = run([sys.executable, os.path.join(ROOT, "forge.py"),
                  "fmt", p], ROOT)
        if not check(f"fmt runs ({rel})", rf.returncode == 0,
                     rf.stderr.strip()):
            failures.append(f"fmt runs ({rel})")
            continue
        rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"),
                   "fmt", "--check", p], ROOT)
        if not check(f"fmt idempotent ({rel})", rf2.returncode == 0,
                     rf2.stderr.strip()):
            failures.append(f"fmt idempotent ({rel})")
    # ASan: the demo runs clean.
    with tempfile.TemporaryDirectory() as td:
        c_path = os.path.join(td, "retry.c")
        bin_path = os.path.join(td, "retry_asan")
        r = run([sys.executable, os.path.join(ROOT, "forge.py"), "emit",
                 demo], ROOT)
        with open(c_path, "w") as f:
            f.write(r.stdout)
        cc = run(["cc", "-g", "-fsanitize=address", "-o", bin_path, c_path,
                  "-lssl", "-lcrypto", "-lm"], ROOT)
        if cc.returncode != 0:
            check("ASan build", False, f"(cc err={cc.stderr[:300]!r})")
            failures.append("ASan build")
        else:
            r = run([bin_path], ROOT)
            ok = r.returncode == 0 and r.stdout == DEMO_EXPECTED
            if not check("ASan run clean", ok,
                         f"(rc={r.returncode} out={r.stdout!r} "
                         f"err={r.stderr[:300]!r})"):
                failures.append("ASan run")
    if failures:
        print(f"FAILURES: {len(failures)}: {failures}")
        return 1
    print(f"ALL PASS ({1 + len(OK_CASES) + len(FAIL_CASES) + 4 + 1} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
