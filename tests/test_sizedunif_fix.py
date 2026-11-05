"""Regression test: nested sized-literal unification (fix track).

`[[1, 2], [3, 4]]` against `[[int; 2]; 2]` was rejected with
"declared [[int; 2]; 2] but initialised with [[int]]": the
checker's sized-literal check only compared each element's
inferred type against the sized element type, so an inner
literal checked as dynamic `[int]` and never matched
`[int; 2]`. The fix recurses the sized-literal check into
nested literals (at any depth, and under a dynamic outer
array), and infer's fill_lit now assigns the sized type to
inner literals instead of the dynamic type a plain walk
would give. Sized arrays stay native-only: big32 and WASM
still reject sized programs with their named errors.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PROG = """
struct Grid { cells: [[int; 2]; 2]; }
fn colsum(g: [[int; 2]; 2]) -> int {
  return g[0][0] + g[1][0];
}
fn make() -> [[int; 2]; 2] {
  return [[7, 8], [9, 10]];
}
fn main() {
  let m: [[int; 2]; 2] = [[1, 2], [3, 4]];
  println(m[0][1]);
  println(m[1][0]);
  println(m[1][1]);
  println(len(m));
  println(len(m[0]));
  println(colsum(m));
  println(colsum(make()));
  let g: Grid = Grid { cells: [[5, 6], [7, 8]] };
  println(g.cells[1][1]);
  let d: [[int; 2]] = [[1, 2], [3, 4]];
  println(d[1][0]);
  println(len(d));
  let t: [[[int; 2]; 2]; 1] = [[[1, 2], [3, 4]]];
  println(t[0][1][1]);
  let mut w: [[int; 2]; 2] = [[1, 2], [3, 4]];
  w[1][1] = 40;
  println(w[1][1]);
  let z: [[int; 0]; 2] = [[], []];
  println(len(z));
  println(len(z[0]));
}
"""

EXPECTED = "2\n3\n4\n2\n2\n4\n16\n8\n3\n2\n4\n40\n2\n0\n"

CASES = [
    ("outer count mismatch",
     "fn main() {\n  let m: [[int; 2]; 2] = [[1, 2]];\n  println(m[0][0]);\n}\n",
     "needs 2 elements, got 1"),
    ("inner count mismatch",
     "fn main() {\n  let m: [[int; 2]; 2] = [[1, 2], [3]];\n  println(m[0][0]);\n}\n",
     "needs 2 elements, got 1"),
    ("wrong inner size is a different type",
     "fn main() {\n  let m: [[int; 2]; 2] = [[1, 2], [3, 4]];\n"
     "  let n: [[int; 3]; 2] = m;\n  println(n[0][0]);\n}\n",
     "declared [[int; 3]; 2] but initialised with [[int; 2]; 2]"),
    ("inner element type mismatch still rejected",
     "fn main() {\n  let m: [[int; 2]; 2] = [[1, 2], [3, \"x\"]];\n"
     "  println(m[0][0]);\n}\n",
     "array literal elements must all have the same type"),
    ("dynamic outer with sized inner count mismatch",
     "fn main() {\n  let d: [[int; 2]] = [[1, 2], [3]];\n  println(d[0][0]);\n}\n",
     "needs 2 elements, got 1"),
    ("return position nested sized literal",
     "fn make() -> [[int; 2]; 2] {\n  return [[1, 2]];\n}\n"
     "fn main() {\n  println(make()[0][0]);\n}\n",
     "needs 2 elements, got 1"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          timeout=60)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    forge = [sys.executable, os.path.join(ROOT, "forge.py")]
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "s.fg")
        with open(src, "w") as f:
            f.write(PROG)
        r = run(forge + ["run", src], ROOT)
        if not check("nested sized program runs",
                     r.returncode == 0 and r.stdout == EXPECTED,
                     repr(r.stdout) + " " + r.stderr.strip()[-200:]):
            failures.append("nested sized program runs")
        for name, prog, frag in CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            rr = run(forge + ["run", p], ROOT)
            ok = rr.returncode != 0 and frag in (rr.stderr + rr.stdout)
            if not check(f"{name} rejected", ok,
                         (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(name)
        fmt = os.path.join(td, "f.fg")
        with open(fmt, "w") as f:
            f.write(PROG)
        rf = run(forge + ["fmt", fmt], ROOT)
        if not check("fmt runs", rf.returncode == 0, rf.stderr.strip()):
            failures.append("fmt runs")
        else:
            rf2 = run(forge + ["fmt", "--check", fmt], ROOT)
            if not check("fmt idempotent", rf2.returncode == 0,
                         rf2.stderr.strip()):
                failures.append("fmt idempotent")
        bsrc = os.path.join(td, "bk.fg")
        with open(bsrc, "w") as f:
            f.write("fn main() {\n  let m: [[int; 2]; 2] = [[1, 2], [3, 4]];\n}\n")
        rb = run(forge + ["build", "--target", "big32", "--freestanding",
                          "-o", os.path.join(td, "b"), bsrc], ROOT)
        ok = rb.returncode != 0 and "big32: sized arrays are not supported" in (
            rb.stderr + rb.stdout)
        if not check("big32 rejects nested sized", ok, rb.stderr.strip()[-120:]):
            failures.append("big32 rejects nested sized")
        rw = run(forge + ["emit-wasm", "-o", os.path.join(td, "w.wasm"), src],
                 ROOT)
        ok = rw.returncode != 0 and "wasm: sized arrays are not supported" in (
            rw.stderr + rw.stdout)
        if not check("wasm rejects nested sized", ok, rw.stderr.strip()[-120:]):
            failures.append("wasm rejects nested sized")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
