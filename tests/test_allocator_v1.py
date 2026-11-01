"""Top-500 #22: allocator-as-value v1
(tests/test_allocator_v1.py) — to be moved into tests/ once the
defer suite run lands, together with stdlib/allocator.fg and
examples/allocator_demo.fg. Pure Jal Pari module: bump,
freelist, and arena allocators passed explicitly as values.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

EXPECTED = "0\n1\n2\n3\n-1\n0\n1\n0\n1\n0\n1\n0\n0\n"


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "allocator_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("allocator demo runs", r.returncode == 0,
                 r.stderr.strip().splitlines()[-1] if r.stderr else ""):
        failures.append("allocator demo runs")
    elif not check("allocator results", r.stdout == EXPECTED,
                   repr(r.stdout)):
        failures.append("allocator results")
    fmt = os.path.join(ROOT, "stdlib", "allocator.fg")
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
