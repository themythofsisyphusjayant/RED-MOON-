"""Top-500 #13: readonly collection views v1 (tests/test_readonly_v1.py).

`readonly [T]` is a handle through which an array can be read
(index, len, iteration) but not written (no push, no index
assignment). A mutable array coerces to a readonly view of the
same array kind; a view never coerces back, and kinds never
mix. Views are shallow: the underlying buffer is shared.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PROG = """
struct Bag { items: readonly [int]; }
fn sum_view(v: readonly [int]) -> int {
  let mut s: int = 0;
  for x in v {
    s = s + x;
  }
  return s;
}
fn first(v: readonly [int]) -> int {
  return v[0];
}
fn sum_sized(v: readonly [int; 3]) -> int {
  return v[0] + v[1] + v[2];
}
fn main() {
  let mut a: [int] = [1, 2, 3];
  println(sum_view(a));
  println(first(a));
  let v: readonly [int] = a;
  println(v[1]);
  println(len(v));
  println(sum_view(v));
  println(first(v));
  a[0] = 10;
  println(v[0]);
  let s: [int; 3] = [4, 5, 6];
  println(sum_sized(s));
  let sv: readonly [int; 3] = s;
  println(sv[2]);
  let b: Bag = Bag { items: a };
  println(b.items[0]);
  println(sum_view(b.items));
}
"""

EXPECTED = "6\n1\n2\n3\n6\n1\n10\n15\n6\n10\n15\n"

CASES = [
    ("push through a view",
     "fn main() {\n  let a: [int] = [1, 2];\n  let v: readonly [int] = a;\n  push(v, 3);\n  println(1);\n}\n",
     "cannot push to a readonly view"),
    ("index assignment through a view",
     "fn main() {\n  let a: [int] = [1, 2];\n  let v: readonly [int] = a;\n  v[0] = 9;\n  println(1);\n}\n",
     "cannot assign through a readonly view"),
    ("view back to mutable",
     "fn main() {\n  let a: [int] = [1, 2];\n  let v: readonly [int] = a;\n  let b: [int] = v;\n  println(b[0]);\n}\n",
     "declared [int] but initialised with readonly [int]"),
    ("sized into dynamic view",
     "fn main() {\n  let s: [int; 3] = [1, 2, 3];\n  let v: readonly [int] = s;\n  println(v[0]);\n}\n",
     "declared readonly [int] but initialised with [int; 3]"),
    ("dynamic into sized view",
     "fn main() {\n  let a: [int] = [1, 2, 3];\n  let v: readonly [int; 3] = a;\n  println(v[0]);\n}\n",
     "declared readonly [int; 3] but initialised with [int]"),
    ("readonly of a non-array",
     "fn main() {\n  let x: readonly int = 5;\n  println(x);\n}\n",
     "readonly only applies to array types"),
    ("nested readonly",
     "fn main() {\n  let a: [int] = [1];\n  let v: readonly readonly [int] = a;\n  println(v[0]);\n}\n",
     "readonly cannot be nested"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "r.fg")
        with open(src, "w") as f:
            f.write(PROG)
        exe = os.path.join(td, "r")
        r = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                 "-o", exe, src], ROOT)
        if not check("readonly program builds", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append("readonly program builds")
        else:
            r2 = run([exe], td)
            if not check("readonly results", r2.stdout == EXPECTED,
                         repr(r2.stdout)):
                failures.append("readonly results")
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
            f.write("fn main() {\n  let a: [int] = [1, 2];\n  let v: readonly [int] = a;\n}\n")
        rb = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                  "--target", "big32", "--freestanding", "-o",
                  os.path.join(td, "b"), bsrc], ROOT)
        ok = rb.returncode != 0 and "big32: readonly views are not supported" in (
            rb.stderr + rb.stdout)
        if not check("big32 rejects readonly", ok, rb.stderr.strip()[-120:]):
            failures.append("big32 rejects readonly")
        rw = run([sys.executable, os.path.join(ROOT, "forge.py"), "emit-wasm",
                  "-o", os.path.join(td, "w.wasm"), bsrc], ROOT)
        ok = rw.returncode != 0 and "wasm: readonly views are not supported" in (
            rw.stderr + rw.stdout)
        if not check("wasm rejects readonly", ok, rw.stderr.strip()[-120:]):
            failures.append("wasm rejects readonly")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
