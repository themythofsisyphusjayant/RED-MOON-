"""Top-500 #27: move semantics v1
(tests/test_move_v1.py). move(a) transfers the one
hold instead of copying: the destination's refcount
stays 1, and the source is dead afterwards — any
later use or second move is a checker error.
Native-only; big32 and WASM reject move programs.
Branch/loop moves and field moves arrived in v2
(tests/test_move_branch_field.py); the v1 branch and
loop rejection cases moved there as success cases.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

EXPECTED = "1\n1\n1\n3\n"

CASES = [
    ("use after move",
     "fn main() {\n  let a = [1];\n  let b = move(a);\n  println(a[0]);\n}\n",
     "use of moved value 'a'"),
    ("double move",
     "fn main() {\n  let a = [1];\n  let b = move(a);\n  let c = move(a);\n}\n",
     "use of moved value 'a'"),
    ("move of int",
     "fn main() {\n  let a = 5;\n  let b = move(a);\n}\n",
     "move needs an owned value"),
    ("move of non-variable",
     "fn main() {\n  let b = move([1, 2]);\n}\n",
     "move needs a variable"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "move_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("move demo runs", r.returncode == 0,
                 r.stderr.strip().splitlines()[-1] if r.stderr else ""):
        failures.append("move demo runs")
    elif not check("move results", r.stdout == EXPECTED,
                   repr(r.stdout)):
        failures.append("move results")
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
    fmt = os.path.join(ROOT, "examples", "move_demo.fg")
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
