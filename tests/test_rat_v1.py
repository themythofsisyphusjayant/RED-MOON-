"""Top-500 #7: exact rational arithmetic v1 (tests/test_rat_v1.py).
Exact rationals in forge_lang/stdlib/rat.fg: a Rat is a struct
of two ints, always stored reduced with a positive denominator
(the sign lives on the numerator), so equal values always have
identical fields and rat_eq is a plain field comparison.
rat_new with den=0 and rat_div by a zero rational fail;
everything else is a value. Native-only reasoning in v1 is
not needed: structs with int fields need no tuple support, so
there is no big32/WASM rejection gate here.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

IMP = 'import "rat.fg";\n'

DEMO_EXPECTED = ("1/2 + 1/3 = 5/6\n2/3 * 3/4 = 1/2\n1/2 - 1/3 = 1/6\n"
                 "3/4 / 1/2 = 3/2\n2/4 = 1/2\n-1/-2 = 1/2\n"
                 "1/2 == 1/3:\nfalse\ncmp 1/2 vs 1/3:\n1\n"
                 "cmp 1/3 vs 1/2:\n-1\ncmp 1/2 vs 2/4:\n0\n"
                 "6/3 = 2\n1/2 as float:\n0.5\n")

# (name, program, expected stdout) — must run clean.
# Every expected value was hand-computed with Python's
# fractions.Fraction before the first Qasida run.
OK_CASES = [
    ("negative denominators normalize to the numerator",
     IMP + "fn main() {\n"
     "  println(rat_to_string(rat_new(1, -3)));\n"
     "  println(rat_to_string(rat_new(-2, -3)));\n"
     "  println(rat_to_string(rat_new(3, -6)));\n"
     "  println(rat_to_string(rat_new(-5, 1)));\n}\n",
     "-1/3\n2/3\n-1/2\n-5\n"),
    ("zero numerator is 0, whatever the denominator",
     IMP + "fn main() {\n"
     "  println(rat_to_string(rat_new(0, 5)));\n"
     "  println(rat_to_string(rat_new(0, -7)));\n"
     "  println(rat_to_string(rat_add(rat_new(0, 5), rat_new(1, 2))));\n"
     "  println(rat_to_string(rat_mul(rat_new(0, 3), rat_new(7, 8))));\n}\n",
     "0\n0\n1/2\n0\n"),
    ("large reduction: 100/250 is 2/5, 99/33 is 3",
     IMP + "fn main() {\n"
     "  println(rat_to_string(rat_new(100, 250)));\n"
     "  println(rat_to_string(rat_new(99, 33)));\n"
     "  println(rat_to_string(rat_new(1000, 4000)));\n"
     "  println(rat_to_string(rat_new(17, 34)));\n}\n",
     "2/5\n3\n1/4\n1/2\n"),
    ("cmp of equal values made differently",
     IMP + "fn main() {\n"
     "  println(rat_eq(rat_new(1, 2), rat_new(2, 4)));\n"
     "  println(rat_cmp(rat_new(1, 2), rat_new(2, 4)));\n"
     "  println(rat_eq(rat_new(3, 6), rat_new(1, 2)));\n"
     "  println(rat_eq(rat_new(1, 2), rat_new(1, 3)));\n"
     "  println(rat_cmp(rat_new(3, 4), rat_new(2, 3)));\n"
     "  println(rat_cmp(rat_new(1, 3), rat_new(1, 2)));\n}\n",
     "true\n0\ntrue\nfalse\n1\n-1\n"),
    ("chained arithmetic stays exact",
     IMP + "fn main() {\n"
     "  let s = rat_add(rat_add(rat_new(1, 2), rat_new(1, 3)), rat_new(1, 6));\n"
     "  println(rat_to_string(s));\n"
     "  println(rat_to_string(rat_sub(rat_new(5, 6), rat_new(1, 2))));\n"
     "  println(rat_to_string(rat_mul(rat_new(-2, 3), rat_new(3, 4))));\n"
     "  println(rat_to_string(rat_div(rat_new(1, 2), rat_new(2, 1))));\n"
     "  println(rat_to_string(rat_sub(rat_new(7, 3), rat_new(1, 3))));\n"
     "  println(rat_to_string(rat_mul(rat_new(2, 5), rat_new(5, 2))));\n}\n",
     "1\n1/3\n-1/2\n1/4\n2\n1\n"),
    ("to_float on exact binary fractions",
     IMP + "fn main() {\n"
     "  println(rat_to_float(rat_new(3, 2)));\n"
     "  println(rat_to_float(rat_new(1, 4)));\n"
     "  println(rat_to_float(rat_new(-1, 2)));\n"
     "  println(rat_to_float(rat_new(1, 3)));\n}\n",
     "1.5\n0.25\n-0.5\n0.333333\n"),
]

# (name, program) — must fail with a nonzero exit.
FAIL_CASES = [
    ("rat_div by a zero rational fails",
     IMP + "fn main() {\n"
     "  println(rat_to_string(rat_div(rat_new(1, 2), rat_new(0, 1))));\n}\n"),
    ("rat_new with a zero denominator fails",
     IMP + "fn main() {\n"
     "  println(rat_to_string(rat_new(1, 0)));\n}\n"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "rat_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("rat demo", r.returncode == 0 and r.stdout == DEMO_EXPECTED,
                 f"(rc={r.returncode} out={r.stdout!r} err={r.stderr[:200]!r})"):
        failures.append("rat demo")
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
    for rel in ("forge_lang/stdlib/rat.fg", "examples/rat_demo.fg"):
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
        c_path = os.path.join(td, "rat.c")
        bin_path = os.path.join(td, "rat_asan")
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
