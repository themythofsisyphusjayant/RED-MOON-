"""Top-500 #26: weak references v1
(tests/test_weak_v1.py). weak_new registers an [int]
array without gaining a holder; weak_upgrade returns
(alive, array) — the current array while any strong
holder lives (pushes and in-place writes visible),
(false, []) after the last strong holder's scope ends.
Native-only in v1; big32 and WASM reject weak programs.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

EXPECTED = "true\n9\n50\nfalse\n0\n"

CASES = [
    ("weak_new non-int-array",
     "fn main() {\n  let a = [1.5];\n  let w = weak_new(a);\n}\n",
     "weak_new() needs an [int] array"),
    ("weak_new non-array",
     "fn main() {\n  let w = weak_new(5);\n}\n",
     "weak_new() needs an [int] array"),
    ("weak_upgrade non-int",
     "fn main() {\n  let a = [1];\n  let up = weak_upgrade(a);\n}\n",
     "weak_upgrade() takes a weak id"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "weak_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("weak demo runs", r.returncode == 0,
                 r.stderr.strip().splitlines()[-1] if r.stderr else ""):
        failures.append("weak demo runs")
    elif not check("weak results", r.stdout == EXPECTED,
                   repr(r.stdout)):
        failures.append("weak results")
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
    fmt = os.path.join(ROOT, "examples", "weak_demo.fg")
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
