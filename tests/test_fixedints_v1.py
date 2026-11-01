"""Top-500 #9: fixed-width integers v1 (tests/test_fixedints_v1.py).

i8, i16, i32, u8, u16, u32, u64 as distinct scalars; i64 is a
spelling for int. Literals adapt to an expected fixed type when
they fit (range-checked at compile time); arithmetic is checked
(widened, range-checked, narrowed); casts between int types are
free when widening and range-checked when narrowing. v1 limits:
no arrays of fixed widths; big32 and WASM reject fixed programs.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PROG = """
struct Point { x: i32; y: i32; }
fn add_pt(p: Point, dx: i32) -> i32 {
  return p.x + dx;
}
fn main() {
  let a: i8 = 100;
  let b: i8 = 27;
  println(a + b);
  let c: i16 = 1000;
  println(c * 30);
  let d: i32 = 10000;
  println(d * d);
  let e: u8 = 200;
  println(e + 55);
  let f: u16 = 60000;
  println(f + 5535);
  let g: u32 = 4000000000;
  println(g + 294967295);
  let h: u64 = 18000000000000000000;
  println(h + 446744073709551615);
  let p: Point = Point { x: 40, y: 2 };
  println(add_pt(p, 2));
  let n: i8 = -5;
  println(n);
  let sh: i32 = 3;
  println(sh << 4);
  println(sh >> 1);
  let w: i32 = 1000;
  println(w as i16);
  println(w as u32);
  let big: i64 = 42;
  println(big);
}
"""

EXPECTED = ("127\n30000\n100000000\n255\n65535\n4294967295\n"
            "18446744073709551615\n42\n-5\n48\n1\n1000\n1000\n42\n")

CASES = [
    ("out-of-range literal",
     "fn main() {\n  let x: i8 = 128;\n  println(x);\n}\n",
     "does not fit"),
    ("negative out-of-range literal",
     "fn main() {\n  let x: u8 = -1;\n  println(x);\n}\n",
     "does not fit"),
    ("general int expression does not adapt",
     "fn main() {\n  let y: int = 5;\n  let x: i32 = y + 1;\n  println(x);\n}\n",
     "declared i32 but initialised with int"),
    ("mixed-width arithmetic",
     "fn main() {\n  let a: i32 = 5;\n  let b: i16 = 6;\n  println(a + b);\n}\n",
     "needs matching"),
    ("mixed-width comparison",
     "fn main() {\n  let a: i32 = 5;\n  let b: i16 = 6;\n  println(a < b);\n}\n",
     "needs matching"),
    ("identity cast still rejected",
     "fn main() {\n  let a: i32 = 5;\n  println(a as i32);\n}\n",
     "cannot cast i32 to i32"),
    ("array of fixed width",
     "fn main() {\n  let xs: [i32] = [];\n  println(1);\n}\n",
     "arrays of i32 are not supported in v1"),
    ("i64 is int, not a separate type",
     "fn main() {\n  let a: i64 = 5;\n  let b: int = a;\n  println(b);\n}\n",
     None),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "f.fg")
        with open(src, "w") as f:
            f.write(PROG)
        exe = os.path.join(td, "f")
        r = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                 "-o", exe, src], ROOT)
        if not check("fixed program builds", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append("fixed program builds")
        else:
            r2 = run([exe], td)
            if not check("fixed results", r2.stdout == EXPECTED,
                         repr(r2.stdout)):
                failures.append("fixed results")
        for name, prog, frag in CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            rr = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", p],
                     ROOT)
            if frag is None:
                ok = rr.returncode == 0
                if not check(f"{name} accepted", ok,
                             rr.stderr.strip().splitlines()[-1:] if rr.stderr else ""):
                    failures.append(name)
            else:
                ok = rr.returncode != 0 and frag in (rr.stderr + rr.stdout)
                if not check(f"{name} rejected", ok,
                             (rr.stderr.strip().splitlines() or [""])[-1]):
                    failures.append(name)
        # Runtime overflow checks: each must fail at runtime with
        # the checked-arithmetic message, not silently wrap.
        rt_cases = [
            ("i8 overflow", "fn main() {\n  let a: i8 = 120;\n  let b: i8 = 10;\n  println(a + b);\n}\n"),
            ("u8 underflow", "fn main() {\n  let a: u8 = 5;\n  let b: u8 = 10;\n  println(a - b);\n}\n"),
            ("narrowing cast overflow", "fn main() {\n  let a: i32 = 100000;\n  println(a as i8);\n}\n"),
            ("negative to unsigned cast", "fn main() {\n  let a: i32 = -1;\n  println(a as u32);\n}\n"),
            ("division by zero", "fn main() {\n  let a: i32 = 10;\n  let b: i32 = 0;\n  println(a / b);\n}\n"),
            ("shift out of range", "fn main() {\n  let a: i32 = 1;\n  println(a << 32);\n}\n"),
            ("negate i8 min", "fn main() {\n  let a: i8 = -128;\n  println(-a);\n}\n"),
        ]
        for name, prog in rt_cases:
            p = os.path.join(td, "r.fg")
            with open(p, "w") as f:
                f.write(prog)
            rr = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", p],
                     ROOT)
            ok = rr.returncode != 0 and ("overflow" in (rr.stderr + rr.stdout)
                                         or "division by zero" in (rr.stderr + rr.stdout)
                                         or "shift count" in (rr.stderr + rr.stdout))
            if not check(f"{name} fails at runtime", ok,
                         (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(name)
        fmt = os.path.join(td, "m.fg")
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
                fexe = os.path.join(td, "m")
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
            f.write("fn main() {\n  let x: i32 = 5;\n}\n")
        rb = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                  "--target", "big32", "--freestanding", "-o",
                  os.path.join(td, "b"), bsrc], ROOT)
        ok = rb.returncode != 0 and "big32: fixed-width integer types are not supported" in (
            rb.stderr + rb.stdout)
        if not check("big32 rejects fixed", ok, rb.stderr.strip()[-120:]):
            failures.append("big32 rejects fixed")
        rw = run([sys.executable, os.path.join(ROOT, "forge.py"), "emit-wasm",
                  "-o", os.path.join(td, "w.wasm"), src], ROOT)
        ok = rw.returncode != 0 and "wasm: fixed-width integer types are not supported" in (
            rw.stderr + rw.stdout)
        if not check("wasm rejects fixed", ok, rw.stderr.strip()[-120:]):
            failures.append("wasm rejects fixed")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
