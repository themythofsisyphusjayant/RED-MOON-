"""Top-500 #29: stack-allocated slices v1
(tests/test_slice_v1.py). A Slice is a stack-
allocated header over an existing array's buffer:
no copy, writes through to the original, bounds
are the slice's own, and slicing a slice composes.
Pure Jal Pari — no compiler change.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

EXPECTED = "20\n30\n2\n99\n99\n30\n"

CASES = [
    ("slice_of out of bounds",
     "import \"slice.fg\";\nfn main() {\n  let a = [1, 2];\n  let s = slice_of(a, 1, 2);\n}\n",
     "slice out of bounds"),
    ("slice_get out of bounds",
     "import \"slice.fg\";\nfn main() {\n  let a = [1, 2];\n  let s = slice_of(a, 0, 2);\n  println(slice_get(s, 2));\n}\n",
     "slice index out of bounds"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "slice_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("slice demo runs", r.returncode == 0,
                 r.stderr.strip().splitlines()[-1] if r.stderr else ""):
        failures.append("slice demo runs")
    elif not check("slice results", r.stdout == EXPECTED,
                   repr(r.stdout)):
        failures.append("slice results")
    with tempfile.TemporaryDirectory() as td:
        for name, prog, frag in CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            rr = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", p],
                     ROOT)
            ok = rr.returncode != 0 and frag in (rr.stderr + rr.stdout)
            if not check(f"{name} fails", ok,
                         (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(name)
    fmt = os.path.join(ROOT, "stdlib", "slice.fg")
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
