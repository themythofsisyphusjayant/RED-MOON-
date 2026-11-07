"""Top-500 #30: lifetime-ordered placement v1
(tests/test_lifetime_v1.py). One backing array,
two regions: shorts bump from the front, longs
from the back; one reset frees all shorts while
longs survive. Out-of-memory is a value (-1).
Pure Qasida — no compiler change.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

EXPECTED = "10\n20\n20\n30\n20\n"

OVERFLOW = (
    "import \"lifetime.fg\";\n"
    "fn main() {\n"
    "  let a0 = life_new(2);\n"
    "  let r1 = life_alloc_short(a0, 1);\n"
    "  let a1 = r1.1;\n"
    "  let r2 = life_alloc_short(a1, 2);\n"
    "  let a2 = r2.1;\n"
    "  let r3 = life_alloc_short(a2, 3);\n"
    "  println(r3.0);\n"
    "  let r4 = life_alloc_long(a2, 4);\n"
    "  println(r4.0);\n"
    "}\n"
)
OVERFLOW_EXPECTED = "-1\n-1\n"


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "lifetime_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("lifetime demo runs", r.returncode == 0,
                 r.stderr.strip().splitlines()[-1] if r.stderr else ""):
        failures.append("lifetime demo runs")
    elif not check("lifetime results", r.stdout == EXPECTED,
                   repr(r.stdout)):
        failures.append("lifetime results")
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "o.fg")
        with open(p, "w") as f:
            f.write(OVERFLOW)
        ro = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", p],
                 ROOT)
        if not check("overflow runs", ro.returncode == 0,
                     ro.stderr.strip().splitlines()[-1] if ro.stderr else ""):
            failures.append("overflow runs")
        elif not check("overflow results", ro.stdout == OVERFLOW_EXPECTED,
                       repr(ro.stdout)):
            failures.append("overflow results")
    fmt = os.path.join(ROOT, "forge_lang", "stdlib", "lifetime.fg")
    rf = run([sys.executable, os.path.join(ROOT, "forge.py"), "fmt", fmt],
             ROOT)
    if not check("fmt runs", rf.returncode == 0, rf.stderr.strip()):
        failures.append("fmt runs")
    else:
        rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"),
                   "fmt", "--check", fmt], ROOT)
        if not check("fmt idempotent", rf2.returncode == 0, rf2.stderr.strip()):
            failures.append("fmt idempotent")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
