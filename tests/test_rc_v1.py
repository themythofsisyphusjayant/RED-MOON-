"""Top-500 #25: reference counting v1
(tests/test_rc_v1.py). The refcount builtin reads an
array's live holder count; the Rc module wraps shared
ownership. Counts verified by hand: after rc_new the
persistent count is 1 (one holder, r); after rc_clone
it is 2 (r and c); mutation through the clone is
visible via the original (99); rc_len is 2.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

EXPECTED = "1\n2\n99\n2\n"

CASES = [
    ("refcount non-array",
     "fn main() {\n  println(refcount(5));\n}\n",
     "refcount() needs an array"),
    ("refcount arity",
     "fn main() {\n  let a = [1];\n  println(refcount(a, a));\n}\n",
     "takes exactly one argument"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "rc_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("rc demo runs", r.returncode == 0,
                 r.stderr.strip().splitlines()[-1] if r.stderr else ""):
        failures.append("rc demo runs")
    elif not check("rc results", r.stdout == EXPECTED,
                   repr(r.stdout)):
        failures.append("rc results")
    with tempfile.TemporaryDirectory() as td:
        for name, prog, frag in CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            rr = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", p],
                     ROOT)
            ok = rr.returncode != 0 and frag in (rr.stderr + rr.stdout)
            if not check(f"{name} rejected", ok,
                         (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(name)
    fmt = os.path.join(ROOT, "stdlib", "rc.fg")
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
