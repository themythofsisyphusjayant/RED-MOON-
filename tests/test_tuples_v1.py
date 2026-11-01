"""Top-500 #19: tuple types v1 (tests/test_tuples_v1.py).

`(T1, T2, ...)` is a fixed-arity heterogeneous type; values
are written `(v1, v2, ...)` and read as `t.0`, `t.1`, ... .
Tuples are owned values (str elements copied, array
elements refcounted, nested elements made independent).
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PROG = """
struct Point { x: int; y: int; }
struct Wrap { pair: (int, str); }
fn sum_pair(p: (int, int)) -> int {
  return p.0 + p.1;
}
fn first_of(p: (int, str)) -> int {
  return p.0;
}
fn main() {
  let t: (int, str) = (42, "hi");
  println(t.0);
  println(t.1);
  println(sum_pair((3, 4)));
  println(first_of(t));
  let u = t;
  println(u.0);
  println(u.1);
  let mut v: (int, int) = (1, 2);
  v = (10, 20);
  println(v.0 + v.1);
  v = (v.0 + 1, v.1 + 1);
  println(v.0);
  println(v.1);
  let nested: ((int, int), str) = ((5, 6), "yo");
  println(nested.0.0 + nested.0.1);
  println(nested.1);
  let arr: ([int], int) = ([7, 8], 2);
  println(arr.0[1]);
  println(arr.1);
  let pt: (Point, int) = (Point { x: 3, y: 4 }, 9);
  println(pt.0.x + pt.0.y);
  println(pt.1);
  let w: Wrap = Wrap { pair: (11, "w") };
  println(w.pair.0);
  println(w.pair.1);
  let s: str = "keep";
  let st: (str, int) = (s, 1);
  println(st.0);
  println(s);
}
"""

EXPECTED = "42\nhi\n7\n42\n42\nhi\n30\n11\n21\n11\nyo\n8\n2\n7\n9\n11\nw\nkeep\nkeep\n"

CASES = [
    ("tuple index out of range",
     "fn main() {\n  let t: (int, int) = (1, 2);\n  println(t.2);\n}\n",
     "tuple index .2 out of range"),
    ("tuple index on a non-tuple",
     "fn main() {\n  let x: int = 5;\n  println(x.0);\n}\n",
     "tuple index .0 needs a tuple value"),
    ("tuple element type mismatch",
     "fn main() {\n  let t: (int, str) = (1, 2);\n  println(t.0);\n}\n",
     "declared (int, str) but initialised with (int, int)"),
    ("tuple arity mismatch",
     "fn main() {\n  let t: (int, int) = (1, 2, 3);\n  println(t.0);\n}\n",
     "declared (int, int) but initialised with (int, int, int)"),
    ("tuple element assignment",
     "fn main() {\n  let mut t: (int, int) = (1, 2);\n  t.0 = 9;\n  println(t.0);\n}\n",
     "assignment target must be a variable, an index, or a field"),
    ("single-element tuple type",
     "fn main() {\n  let t: (int) = (1);\n  println(t.0);\n}\n",
     "tuple types need at least two elements"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "t.fg")
        with open(src, "w") as f:
            f.write(PROG)
        exe = os.path.join(td, "t")
        r = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                 "-o", exe, src], ROOT)
        if not check("tuple program builds", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append("tuple program builds")
        else:
            r2 = run([exe], td)
            if not check("tuple results", r2.stdout == EXPECTED,
                         repr(r2.stdout)):
                failures.append("tuple results")
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
            f.write("fn main() {\n  let t: (int, int) = (1, 2);\n}\n")
        rb = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                  "--target", "big32", "--freestanding", "-o",
                  os.path.join(td, "b"), bsrc], ROOT)
        ok = rb.returncode != 0 and "big32: tuples are not supported" in (
            rb.stderr + rb.stdout)
        if not check("big32 rejects tuples", ok, rb.stderr.strip()[-120:]):
            failures.append("big32 rejects tuples")
        rw = run([sys.executable, os.path.join(ROOT, "forge.py"), "emit-wasm",
                  "-o", os.path.join(td, "w.wasm"), bsrc], ROOT)
        ok = rw.returncode != 0 and "wasm: tuples are not supported" in (
            rw.stderr + rw.stdout)
        if not check("wasm rejects tuples", ok, rw.stderr.strip()[-120:]):
            failures.append("wasm rejects tuples")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
