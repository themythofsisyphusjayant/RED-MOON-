"""Top-500 #2: LU decomposition with partial pivoting (tests/test_lu_v1.py).
LU decomposition over nested [[float]] matrices, pure Qasida in
forge_lang/stdlib/lu.fg: lu_solve solves Ax = b, lu_det returns the
determinant (sign from row swaps), lu_factor returns the combined
LU matrix (L strictly below the diagonal with a unit diagonal
implied, U on and above it). Partial pivoting picks the
largest-magnitude pivot per column, so a zero leading pivot is
fine for a nonsingular matrix. lu_solve fails on singular or
non-square systems; lu_det returns 0.0 for a singular matrix;
lu_factor fails on singular input. Every expected value below was
hand-computed with an independent plain-Python replica (cross-
checked against numpy) before the first Qasida run.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

IMP = 'import "lu.fg";\n'

DEMO_EXPECTED = "1\n3\n2\n3\n-1\n5\n-1\n2\n1\n0.5\n2.5\n"

# (name, program, expected stdout) — must run clean.
OK_CASES = [
    ("solve needs pivoting: first pivot is 0",
     IMP + "fn main() {\n  let a: [[float]] = [[0.0, 2.0], [1.0, 1.0]];\n"
     "  let x: [float] = lu_solve(a, [4.0, 3.0]);\n"
     "  println(x[0]);\n  println(x[1]);\n}\n",
     "1\n2\n"),
    ("det sign flip from a row swap",
     IMP + "fn main() {\n  let a: [[float]] = [[1.0, 2.0], [3.0, 4.0]];\n"
     "  println(lu_det(a));\n}\n",
     "-2\n"),
    ("1x1 system: solve and det",
     IMP + "fn main() {\n  let a: [[float]] = [[5.0]];\n"
     "  let x: [float] = lu_solve(a, [10.0]);\n"
     "  println(x[0]);\n  println(lu_det(a));\n}\n",
     "2\n5\n"),
    ("identity solve returns b unchanged",
     IMP + "fn main() {\n  let a: [[float]] = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]];\n"
     "  let x: [float] = lu_solve(a, [7.0, 8.0, 9.0]);\n"
     "  println(x[0]);\n  println(x[1]);\n  println(x[2]);\n}\n",
     "7\n8\n9\n"),
    ("lu_factor with a row swap: multipliers below the diagonal",
     IMP + "fn main() {\n  let a: [[float]] = [[1.0, 2.0], [3.0, 4.0]];\n"
     "  let f: [[float]] = lu_factor(a);\n"
     "  println(f[0][0]);\n  println(f[0][1]);\n"
     "  println(f[1][0]);\n  println(f[1][1]);\n}\n",
     "3\n4\n0.333333\n0.666667\n"),
    ("det of a 3x3 with no swaps",
     IMP + "fn main() {\n  let a: [[float]] = [[6.0, 1.0, 1.0], [4.0, -2.0, 5.0], [2.0, 8.0, 7.0]];\n"
     "  println(lu_det(a));\n}\n",
     "-306\n"),
    ("3x3 solve with a first-column pivot swap",
     IMP + "fn main() {\n  let a: [[float]] = [[2.0, 1.0, 1.0], [4.0, -6.0, 0.0], [-2.0, 7.0, 2.0]];\n"
     "  let x: [float] = lu_solve(a, [4.0, -2.0, 7.0]);\n"
     "  println(x[0]);\n  println(x[1]);\n  println(x[2]);\n}\n",
     "1\n1\n1\n"),
    ("det of a singular matrix is 0, not a fail",
     IMP + "fn main() {\n  let a: [[float]] = [[1.0, 2.0], [2.0, 4.0]];\n"
     "  println(lu_det(a));\n}\n",
     "0\n"),
]

# (name, program, stderr fragment) — must fail with a nonzero exit.
FAIL_CASES = [
    ("singular solve fails",
     IMP + "fn main() {\n  let a: [[float]] = [[1.0, 2.0], [2.0, 4.0]];\n"
     "  let x: [float] = lu_solve(a, [1.0, 2.0]);\n"
     "  println(x[0]);\n}\n",
     "lu_solve: singular matrix"),
    ("non-square solve fails",
     IMP + "fn main() {\n  let a: [[float]] = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]];\n"
     "  let x: [float] = lu_solve(a, [1.0, 2.0]);\n"
     "  println(x[0]);\n}\n",
     "lu: matrix must be square"),
    ("non-square det fails",
     IMP + "fn main() {\n  let a: [[float]] = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]];\n"
     "  println(lu_det(a));\n}\n",
     "lu: matrix must be square"),
    ("singular factor fails",
     IMP + "fn main() {\n  let a: [[float]] = [[1.0, 2.0], [2.0, 4.0]];\n"
     "  let f: [[float]] = lu_factor(a);\n"
     "  println(f[0][0]);\n}\n",
     "lu_factor: singular matrix"),
    ("b of the wrong length fails",
     IMP + "fn main() {\n  let a: [[float]] = [[1.0, 0.0], [0.0, 1.0]];\n"
     "  let x: [float] = lu_solve(a, [1.0, 2.0, 3.0]);\n"
     "  println(x[0]);\n}\n",
     "lu_solve: b has wrong length"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def run_fg(prog, cwd):
    with tempfile.NamedTemporaryFile("w", suffix=".fg", delete=False,
                                    dir=cwd) as f:
        f.write(prog)
        path = f.name
    try:
        return run([sys.executable, os.path.join(ROOT, "forge.py"),
                    "run", path], ROOT)
    finally:
        os.unlink(path)


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "lu_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("lu demo", r.returncode == 0 and r.stdout == DEMO_EXPECTED,
                 f"(rc={r.returncode} out={r.stdout!r} err={r.stderr[:200]!r})"):
        failures.append("lu demo")
    for name, prog, expected in OK_CASES:
        r = run_fg(prog, ROOT)
        ok = r.returncode == 0 and r.stdout == expected
        if not check(name, ok,
                     f"(rc={r.returncode} out={r.stdout!r} "
                     f"err={r.stderr[:200]!r})"):
            failures.append(name)
    for name, prog, fragment in FAIL_CASES:
        r = run_fg(prog, ROOT)
        ok = r.returncode != 0 and fragment in r.stderr
        if not check(name, ok,
                     f"(rc={r.returncode} out={r.stdout!r} "
                     f"err={r.stderr[:200]!r})"):
            failures.append(name)
    # fmt idempotent on both new files.
    for rel in ("forge_lang/stdlib/lu.fg", "examples/lu_demo.fg"):
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
        c_path = os.path.join(td, "lu.c")
        bin_path = os.path.join(td, "lu_asan")
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
