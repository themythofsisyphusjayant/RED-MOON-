"""Top-500 #11: polynomial least-squares fitting v1
(tests/test_polyfit_v1.py).
Least-squares fit of a degree-deg polynomial to sampled
points, pure Qasida in forge_lang/stdlib/polyfit.fg: the
normal equations are solved in-file by Gaussian
elimination with partial pivoting (no lu.fg import, the
library is self-contained). Coefficients come back in
ascending order (c0 + c1*x + c2*x^2 + ...); poly_eval uses
Horner, poly_fit_err reports the worst absolute residual.
Expected values were hand-computed with an independent
plain-Python normal-equations replica (cross-checked
against numpy.polyfit) before the first Qasida run, never
copied from Qasida output. Floats print %.6g-style, so
the demo and cases use fits whose printed forms are exact
and stable (the quadratic demo's near-1 coefficients are
within 1e-14 of 1/2/1). No tuples are used, so there is no
big32/WASM named-rejection gate.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

IMP = 'import "polyfit.fg";\n'

DEMO_EXPECTED = "1\n2\n1\n2\n1\n0\n0\n3\n0\n"

# (name, program, expected stdout) — must run clean.
OK_CASES = [
    ("deg-0 constant fit is the mean",
     IMP + "fn main() {\n"
     "  let c: [float] = polyfit([0.0, 1.0, 2.0, 3.0],"
     " [4.0, 4.0, 4.0, 4.0], 0);\n"
     "  println(c[0]);\n}\n",
     "4\n"),
    ("overdetermined exact line through 4 points",
     IMP + "fn main() {\n"
     "  let c: [float] = polyfit([0.0, 1.0, 2.0, 3.0],"
     " [1.0, 3.0, 5.0, 7.0], 1);\n"
     "  println(c[0]);\n  println(c[1]);\n}\n",
     "1\n2\n"),
    ("poly_eval at several x, incl. negative",
     IMP + "fn main() {\n"
     "  println(poly_eval([1.0, 2.0, 1.0], -1.0));\n"
     "  println(poly_eval([1.0, 2.0, 1.0], 0.0));\n"
     "  println(poly_eval([1.0, 2.0, 1.0], 3.0));\n}\n",
     "0\n1\n16\n"),
    ("poly_fit_err on a deliberately wrong coefficient set",
     IMP + "fn main() {\n"
     "  println(poly_fit_err([0.0, 1.0, 2.0], [1.0, 4.0, 9.0],"
     " [1.0, 2.0, 0.0]));\n}\n",
     "4\n"),
    ("1-point deg-0 fit is the point itself",
     IMP + "fn main() {\n"
     "  let c: [float] = polyfit([5.0], [7.0], 0);\n"
     "  println(c[0]);\n}\n",
     "7\n"),
    ("non-integer fit: slope 3/2, intercept -1/6",
     IMP + "fn main() {\n"
     "  let c: [float] = polyfit([0.0, 1.0, 2.0],"
     " [0.0, 1.0, 3.0], 1);\n"
     "  println(c[0]);\n  println(c[1]);\n}\n",
     "-0.166667\n1.5\n"),
]

# (name, program, stderr fragment) — must fail.
FAIL_CASES = [
    ("mismatched xs/ys lengths fail",
     IMP + "fn main() {\n"
     "  let c: [float] = polyfit([0.0, 1.0], [1.0, 2.0, 3.0], 1);\n"
     "  println(c[0]);\n}\n",
     "polyfit: xs and ys lengths differ"),
    ("fewer than deg+1 points fail",
     IMP + "fn main() {\n"
     "  let c: [float] = polyfit([0.0, 1.0], [1.0, 3.0], 2);\n"
     "  println(c[0]);\n}\n",
     "polyfit: need deg+1 points"),
    ("negative deg fails",
     IMP + "fn main() {\n"
     "  let c: [float] = polyfit([0.0, 1.0], [1.0, 3.0], -1);\n"
     "  println(c[0]);\n}\n",
     "polyfit: deg must be >= 0"),
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
    demo = os.path.join(ROOT, "examples", "polyfit_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("polyfit demo",
                 r.returncode == 0 and r.stdout == DEMO_EXPECTED,
                 f"(rc={r.returncode} out={r.stdout!r} err={r.stderr[:200]!r})"):
        failures.append("polyfit demo")
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
    for rel in ("forge_lang/stdlib/polyfit.fg", "examples/polyfit_demo.fg"):
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
        c_path = os.path.join(td, "polyfit.c")
        bin_path = os.path.join(td, "polyfit_asan")
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
