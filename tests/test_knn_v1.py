"""Top-500 #92: k-nearest neighbours classifier v1 (tests/test_knn_v1.py).
Pure Qasida in forge_lang/stdlib/knn.fg over nested [[float]] rows:
Euclidean distance, majority-vote prediction (ties: smallest label,
then smallest distance), predicted-label confidence, and held-out
accuracy. All expected values were hand-computed with an independent
Python replica before the first Qasida run; nothing was copied from
Qasida output. No tuples are used, so the big32/WASM named-rejection
checks do not apply.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

IMP = 'import "knn.fg";\n'

DEMO_EXPECTED = ("dist (0,0)-(3,4) = 5\npred (0.5,0.5) = 0\n"
                 "pred (5.5,5.5) = 1\npred (3,3) = 0\n"
                 "proba (3,3) = 0.666667\naccuracy = 0.75\n")

# (name, program, expected stdout) — must run clean.
OK_CASES = [
    ("k=1 picks the nearest neighbour",
     IMP + "fn main() {\n"
     "  let tx: [[float]] = [[0.0], [10.0]];\n"
     "  let ty: [int] = [0, 1];\n"
     "  println(knn_predict(tx, ty, [1.0], 1));\n"
     "  println(knn_predict(tx, ty, [9.0], 1));\n}\n",
     "0\n1\n"),
    ("tie broken by smallest label",
     IMP + "fn main() {\n"
     "  let tx: [[float]] = [[0.0], [2.0]];\n"
     "  let ty: [int] = [1, 0];\n"
     "  println(knn_predict(tx, ty, [1.0], 2));\n}\n",
     "0\n"),
    ("proba 1.0 when all k neighbours agree",
     IMP + "fn main() {\n"
     "  let tx: [[float]] = [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0], [5.0, 5.0], [6.0, 5.0], [5.0, 6.0], [6.0, 6.0]];\n"
     "  let ty: [int] = [0, 0, 0, 0, 1, 1, 1, 1];\n"
     "  println(knn_predict_proba(tx, ty, [0.5, 0.5], 3));\n"
     "  println(knn_predict_proba(tx, ty, [5.5, 5.5], 3));\n}\n",
     "1\n1\n"),
    ("proba 0.5 on a 1-1 split with k=2",
     IMP + "fn main() {\n"
     "  let tx: [[float]] = [[0.0], [2.0]];\n"
     "  let ty: [int] = [0, 1];\n"
     "  println(knn_predict_proba(tx, ty, [1.0], 2));\n}\n",
     "0.5\n"),
    ("accuracy 1.0 on a separable set",
     IMP + "fn main() {\n"
     "  let tx: [[float]] = [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0], [5.0, 5.0], [6.0, 5.0], [5.0, 6.0], [6.0, 6.0]];\n"
     "  let ty: [int] = [0, 0, 0, 0, 1, 1, 1, 1];\n"
     "  let ex: [[float]] = [[0.0, 0.0], [5.0, 5.0]];\n"
     "  let ey: [int] = [0, 1];\n"
     "  println(knn_accuracy(tx, ty, ex, ey, 3));\n}\n",
     "1\n"),
    ("accuracy 0.75 on 4 held-out points",
     IMP + "fn main() {\n"
     "  let tx: [[float]] = [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0], [5.0, 5.0], [6.0, 5.0], [5.0, 6.0], [6.0, 6.0]];\n"
     "  let ty: [int] = [0, 0, 0, 0, 1, 1, 1, 1];\n"
     "  let ex: [[float]] = [[0.0, 0.0], [6.0, 6.0], [3.0, 3.0], [4.0, 4.0]];\n"
     "  let ey: [int] = [0, 1, 0, 0];\n"
     "  println(knn_accuracy(tx, ty, ex, ey, 3));\n}\n",
     "0.75\n"),
    ("distance of identical points is 0",
     IMP + "fn main() {\n"
     "  println(knn_dist([1.0, 2.0], [1.0, 2.0]));\n"
     "  println(knn_dist([0.0, 0.0], [3.0, 4.0]));\n}\n",
     "0\n5\n"),
    ("1-D data with k=3",
     IMP + "fn main() {\n"
     "  let tx: [[float]] = [[0.0], [1.0], [2.0], [10.0]];\n"
     "  let ty: [int] = [0, 0, 0, 1];\n"
     "  println(knn_predict(tx, ty, [1.5], 3));\n"
     "  println(knn_predict(tx, ty, [9.0], 3));\n}\n",
     "0\n0\n"),
]

# (name, program) — must exit nonzero.
FAIL_CASES = [
    ("k larger than the training set fails",
     IMP + "fn main() {\n"
     "  let tx: [[float]] = [[0.0], [2.0]];\n"
     "  let ty: [int] = [0, 1];\n"
     "  println(knn_predict(tx, ty, [1.0], 5));\n}\n"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "knn_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("knn demo", r.returncode == 0 and r.stdout == DEMO_EXPECTED,
                 f"(rc={r.returncode} out={r.stdout!r} err={r.stderr[:200]!r})"):
        failures.append("knn demo")
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
    for name, prog in FAIL_CASES:
        with tempfile.NamedTemporaryFile("w", suffix=".fg", delete=False,
                                        dir=ROOT) as f:
            f.write(prog)
            path = f.name
        try:
            r = run([sys.executable, os.path.join(ROOT, "forge.py"),
                     "run", path], ROOT)
            ok = r.returncode != 0
            if not check(name, ok,
                         f"(rc={r.returncode} out={r.stdout!r} "
                         f"err={r.stderr[:200]!r})"):
                failures.append(name)
        finally:
            os.unlink(path)
    # fmt idempotent on both new files.
    for rel in ("forge_lang/stdlib/knn.fg", "examples/knn_demo.fg"):
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
        c_path = os.path.join(td, "knn.c")
        bin_path = os.path.join(td, "knn_asan")
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
