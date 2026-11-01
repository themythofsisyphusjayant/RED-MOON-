"""Top-500 #32: allocator-aware collections v1
(tests/test_avec_v1.py). A vector whose elements
live one-per-slot in an Allocator's backing, so
growth behaviour follows the allocator: a bump
pool stays exhausted after a pop, a freelist pool
reuses the freed slot. Out-of-memory is a value
(false), not a crash. Pure Jal Pari — no compiler
change. Maps are the named next slice (their
string keys cannot live in an [int]-backed
allocator), so #32 lands PARTIAL.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

EXPECTED = "false\ntrue\n30\n"

OOB = (
    "import \"avec.fg\";\n"
    "fn main() {\n"
    "  let v = avec_new(allocator_new(0, 2));\n"
    "  let p = avec_push(v, 7);\n"
    "  println(avec_get(p.1, 3));\n"
    "}\n"
)


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "avec_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("avec demo runs", r.returncode == 0,
                 r.stderr.strip().splitlines()[-1] if r.stderr else ""):
        failures.append("avec demo runs")
    elif not check("avec results", r.stdout == EXPECTED,
                   repr(r.stdout)):
        failures.append("avec results")
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "o.fg")
        with open(p, "w") as f:
            f.write(OOB)
        ro = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", p],
                 ROOT)
        if not check("oob fails", ro.returncode != 0
                     and "avec index out of bounds" in ro.stderr,
                     ro.stderr.strip().splitlines()[-1] if ro.stderr else ""):
            failures.append("oob fails")
    fmt = os.path.join(ROOT, "stdlib", "avec.fg")
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
