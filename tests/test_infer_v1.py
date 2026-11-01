"""Top-500 #16: local type inference v1
(tests/test_infer_v1.py) — to be moved into tests/ once the clean
suite run lands. Empty array literals infer their element type
from a later constraining use in the same function; with no
constraining use, the checker reports a clear error at the let.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PROG = """
struct Bag { items: [int]; }
fn sum_arr(a: [int]) -> int {
  let mut s: int = 0;
  for x in a {
    s = s + x;
  }
  return s;
}
fn get_first() -> [int] {
  let q = [];
  return q;
}
fn main() {
  let x = [];
  push(x, 1);
  push(x, 2);
  println(x[0] + x[1]);
  let mut y = [];
  y = [10, 20];
  println(y[1]);
  let z = [];
  let w: [int] = z;
  println(len(z));
  let a = [];
  println(sum_arr(a));
  println(len(get_first()));
  let b = [];
  let mut bag: Bag = Bag { items: b };
  println(len(bag.items));
  let f = [];
  bag.items = f;
  println(len(f));
}
"""

EXPECTED = "3\n20\n0\n0\n0\n0\n0\n"

CASES = [
    ("no constraining use",
     "fn main() {\n  let u = [];\n  println(len(u));\n}\n",
     "cannot infer the element type"),
    ("conflicting constraints",
     "fn main() {\n  let c = [];\n  push(c, 1);\n  push(c, \"hi\");\n}\n",
     "push() value must be int, got str"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "i.fg")
        with open(src, "w") as f:
            f.write(PROG)
        exe = os.path.join(td, "i")
        r = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                 "-o", exe, src], ROOT)
        if not check("infer program builds", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append("infer program builds")
        else:
            r2 = run([exe], td)
            if not check("infer results", r2.stdout == EXPECTED,
                         repr(r2.stdout)):
                failures.append("infer results")
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
        fmt = os.path.join(td, "f.fg")
        with open(fmt, "w") as f:
            f.write(PROG)
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
