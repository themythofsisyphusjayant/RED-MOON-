"""Top-500 #24: arena allocation v1
region for temporary allocations, with mark/restore.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

EXPECTED = "0\n1\n2\n3\n3\n4\n3\n0\n1\n2\n0\n"

COW_PROG = """
fn main() {
  let a = [1, 2];
  let b = a;
  push(b, 3);
  println(len(a));
  println(len(b));
  println(a[0]);
  println(b[2]);
}
"""

COW_EXPECTED = "2\n3\n1\n3\n"

FIELD_PROG = """
struct S { mem: [int]; }
struct O { inner: S; }
fn main() {
  let a: S = S { mem: [1, 2] };
  let mut o: O = O { inner: a };
  let b: S = S { mem: [3] };
  o.inner = b;
  println(len(o.inner.mem));
  println(o.inner.mem[0]);
  println(len(a.mem));
}
"""

FIELD_EXPECTED = "1\n3\n2\n"


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "arena_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("arena demo runs", r.returncode == 0,
                 r.stderr.strip().splitlines()[-1] if r.stderr else ""):
        failures.append("arena demo runs")
    elif not check("arena results", r.stdout == EXPECTED,
                   repr(r.stdout)):
        failures.append("arena results")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        cow = os.path.join(td, "cow.fg")
        with open(cow, "w") as f:
            f.write(COW_PROG)
        rc = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", cow],
                 ROOT)
        if not check("shared push copies", rc.returncode == 0
                     and rc.stdout == COW_EXPECTED,
                     repr(rc.stdout) + rc.stderr.strip().splitlines()[-1:]
                     if rc.stderr else repr(rc.stdout)):
            failures.append("shared push copies")
        fld = os.path.join(td, "fld.fg")
        with open(fld, "w") as f:
            f.write(FIELD_PROG)
        rfld = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", fld],
                   ROOT)
        if not check("struct field assignment", rfld.returncode == 0
                     and rfld.stdout == FIELD_EXPECTED,
                     repr(rfld.stdout)):
            failures.append("struct field assignment")
    fmt = os.path.join(ROOT, "stdlib", "arena.fg")
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
