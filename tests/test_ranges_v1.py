"""DRAFT (do not run from here): Top-500 #18 first-class ranges v1
(tests/test_ranges_v1.py) — to be moved into tests/ once the
infer suite run lands. Half-open ranges `a..b` as values of
type `range`, with len/contains/start/end/sum methods and
for-loop iteration, all without materializing an array.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PROG = """
struct Span { r: range; }
fn sum_range(r: range) -> int {
  return r.sum();
}
fn main() {
  let r: range = 0..5;
  println(r.len());
  println(r.start());
  println(r.end());
  if r.contains(3) {
    println(1);
  } else {
    println(0);
  }
  if r.contains(5) {
    println(1);
  } else {
    println(0);
  }
  println(r.sum());
  let mut total: int = 0;
  for x in 1..4 {
    total = total + x;
  }
  println(total);
  let s = 3..3;
  println(s.len());
  println(s.sum());
  let neg = -3..2;
  println(neg.len());
  println(neg.sum());
  println(sum_range(10..13));
  let sp: Span = Span { r: 2..4 };
  println(sp.r.len());
}
"""

EXPECTED = "5\n0\n5\n1\n0\n10\n6\n0\n0\n5\n-5\n33\n2\n"

CASES = [
    ("float endpoint",
     "fn main() {\n  let r = 1.5..5;\n  println(r.len());\n}\n",
     "range endpoints must be int"),
    ("unknown range method",
     "fn main() {\n  let r = 0..5;\n  println(r.foo());\n}\n",
     "range has no method 'foo'"),
    ("contains non-int",
     "fn main() {\n  let r = 0..5;\n  if r.contains(\"hi\") {\n    println(1);\n  }\n}\n",
     "expects int, got str"),
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
        if not check("range program builds", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append("range program builds")
        else:
            r2 = run([exe], td)
            if not check("range results", r2.stdout == EXPECTED,
                         repr(r2.stdout)):
                failures.append("range results")
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
            fexe = os.path.join(td, "f")
            rb = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                      "-o", fexe, fmt], ROOT)
            if rb.returncode == 0:
                r3 = run([fexe], td)
                if not check("formatted program still runs",
                             r3.stdout == EXPECTED, repr(r3.stdout)):
                    failures.append("formatted program still runs")
            else:
                check("formatted program still runs", False, rb.stderr.strip())
                failures.append("formatted program still runs")
        # big32 + wasm gates: a range-only program (no other
        # gated features, and no println, which freestanding
        # rejects before the backend gate) must be rejected
        # with a named error.
        gate = os.path.join(td, "g.fg")
        with open(gate, "w") as f:
            f.write("fn main() {\n  let r: range = 0..5;\n}\n")
        rb = run([sys.executable, os.path.join(ROOT, "forge.py"),
                  "build", "--target", "big32", "--freestanding",
                  "-o", os.path.join(td, "g"), gate], ROOT)
        ok = rb.returncode != 0 and "big32: ranges are not supported in v1" in (rb.stderr + rb.stdout)
        if not check("big32 rejects ranges", ok,
                     (rb.stderr.strip().splitlines() or [""])[-1]):
            failures.append("big32 rejects ranges")
        rw = run([sys.executable, os.path.join(ROOT, "forge.py"),
                  "emit-wasm", gate], ROOT)
        ok = rw.returncode != 0 and "wasm: ranges are not supported in v1" in (rw.stderr + rw.stdout)
        if not check("wasm rejects ranges", ok,
                     (rw.stderr.strip().splitlines() or [""])[-1]):
            failures.append("wasm rejects ranges")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
