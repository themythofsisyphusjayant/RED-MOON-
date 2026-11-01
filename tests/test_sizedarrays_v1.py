"""Top-500 #12: compile-time sized arrays v1 (tests/test_sizedarrays_v1.py).

`[T; N]` is a distinct type from `[T]`: a literal must hold
exactly N elements, push is rejected, indexing/len/iteration
work like dynamic arrays. v1 representation is the existing
heap array; the size is a type-level contract.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PROG = """
struct Scores { vals: [int; 3]; }
fn total(s: [int; 3]) -> int {
  let mut sum: int = 0;
  for x in s {
    sum = sum + x;
  }
  return sum;
}
fn make() -> [int; 3] {
  return [10, 20, 30];
}
fn main() {
  let a: [int; 3] = [1, 2, 3];
  println(a[0]);
  println(a[2]);
  println(len(a));
  println(total(a));
  println(total(make()));
  let sc: Scores = Scores { vals: [4, 5, 6] };
  println(sc.vals[1]);
  sc.vals[2] = 60;
  println(sc.vals[2]);
  let mut b: [int; 2] = [7, 8];
  b[0] = 70;
  println(b[0]);
  let empty: [int; 0] = [];
  println(len(empty));
  let words: [str; 2] = ["hi", "yo"];
  println(words[1]);
}
"""

EXPECTED = "1\n3\n3\n6\n60\n5\n60\n70\n0\nyo\n"

CASES = [
    ("wrong element count",
     "fn main() {\n  let a: [int; 3] = [1, 2];\n  println(a[0]);\n}\n",
     "needs 3 elements, got 2"),
    ("empty literal for nonzero size",
     "fn main() {\n  let a: [int; 2] = [];\n  println(1);\n}\n",
     "needs 2 elements, got 0"),
    ("push to sized array",
     "fn main() {\n  let mut a: [int; 2] = [1, 2];\n  push(a, 3);\n  println(a[0]);\n}\n",
     "cannot push to a sized array"),
    ("sized vs dynamic mismatch",
     "fn main() {\n  let a: [int; 3] = [1, 2, 3];\n  let b: [int] = a;\n  println(b[0]);\n}\n",
     "declared [int] but initialised with [int; 3]"),
    ("dynamic vs sized mismatch",
     "fn main() {\n  let a: [int] = [1, 2, 3];\n  let b: [int; 3] = a;\n  println(b[0]);\n}\n",
     "declared [int; 3] but initialised with [int]"),
    ("wrong size is a different type",
     "fn main() {\n  let a: [int; 3] = [1, 2, 3];\n  let b: [int; 2] = a;\n  println(b[0]);\n}\n",
     "declared [int; 2] but initialised with [int; 3]"),
    ("sized array of fixed width",
     "fn main() {\n  let a: [i32; 2] = [1, 2];\n  println(a[0]);\n}\n",
     "arrays of i32 are not supported in v1"),
    ("non-literal size",
     "fn main() {\n  let a: [int; n] = [1, 2];\n  println(a[0]);\n}\n",
     "sized array size must be an integer literal"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "s.fg")
        with open(src, "w") as f:
            f.write(PROG)
        exe = os.path.join(td, "s")
        r = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                 "-o", exe, src], ROOT)
        if not check("sized program builds", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append("sized program builds")
        else:
            r2 = run([exe], td)
            if not check("sized results", r2.stdout == EXPECTED,
                         repr(r2.stdout)):
                failures.append("sized results")
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
            else:
                fexe = os.path.join(td, "f")
                rb = run([sys.executable, os.path.join(ROOT, "forge.py"),
                          "build", "-o", fexe, fmt], ROOT)
                if rb.returncode == 0:
                    r2 = run([fexe], td)
                    if not check("formatted program still runs",
                                 r2.stdout == EXPECTED, repr(r2.stdout)):
                        failures.append("formatted program still runs")
                else:
                    check("formatted program still runs", False, rb.stderr.strip())
                    failures.append("formatted program still runs")
        bsrc = os.path.join(td, "bk.fg")
        with open(bsrc, "w") as f:
            f.write("fn main() {\n  let a: [int; 2] = [1, 2];\n}\n")
        rb = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                  "--target", "big32", "--freestanding", "-o",
                  os.path.join(td, "b"), bsrc], ROOT)
        ok = rb.returncode != 0 and "big32: sized arrays are not supported" in (
            rb.stderr + rb.stdout)
        if not check("big32 rejects sized", ok, rb.stderr.strip()[-120:]):
            failures.append("big32 rejects sized")
        rw = run([sys.executable, os.path.join(ROOT, "forge.py"), "emit-wasm",
                  "-o", os.path.join(td, "w.wasm"), src], ROOT)
        ok = rw.returncode != 0 and "wasm: sized arrays are not supported" in (
            rw.stderr + rw.stdout)
        if not check("wasm rejects sized", ok, rw.stderr.strip()[-120:]):
            failures.append("wasm rejects sized")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
