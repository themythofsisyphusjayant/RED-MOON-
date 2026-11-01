"""Top-500 #8: opaque types v1 (tests/test_opaques_v1.py).

`opaque Trait` hides a concrete implementation behind its trait
interface: the caller calls trait methods and passes the value
around, but cannot see, name, or construct the concrete type, and
cannot match on it. At runtime the value is a tagged struct over
the implementing structs, in impl-block order; method calls,
copies, and frees dispatch on the tag. v1 limits: opaque types in
returns, parameters, and let annotations only (no struct fields,
no arrays of opaque values); big32 and WASM reject opaque
programs.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PROG = """
trait Shape { fn area() -> int; fn name() -> str; }
struct Rect { w: int; h: int; }
struct Square { s: int; }
struct Named { label: str; side: int; }
impl Shape for Rect {
  fn area(r: Rect) -> int { return r.w * r.h; }
  fn name(r: Rect) -> str { return "rect"; }
}
impl Rect {
  fn perim(r: Rect) -> int { return 2 * (r.w + r.h); }
}
impl Shape for Square {
  fn area(s: Square) -> int { return s.s * s.s; }
  fn name(s: Square) -> str { return "square"; }
}
impl Shape for Named {
  fn area(n: Named) -> int { return n.side * n.side; }
  fn name(n: Named) -> str { return n.label; }
}
fn make_rect() -> opaque Shape {
  return Rect { w: 3, h: 4 };
}
fn make_square() -> opaque Shape {
  return Square { s: 5 };
}
fn make_named() -> opaque Shape {
  return Named { label: "nm", side: 3 };
}
fn use_shape(s: opaque Shape) -> int {
  return s.area();
}
fn main() {
  let a: opaque Shape = make_rect();
  let b: opaque Shape = make_square();
  println(use_shape(a));
  println(use_shape(b));
  println(a.name());
  println(b.name());
  let c: opaque Shape = a;
  println(c.area());
  println(a.area());
  let d: opaque Shape = Rect { w: 2, h: 6 };
  println(d.area());
  let e: opaque Shape = make_named();
  println(e.area());
  println(e.name());
}
"""

EXPECTED = "12\n25\nrect\nsquare\n12\n12\n12\n9\nnm\n"

TRAIT = ("trait Shape { fn area() -> int; fn name() -> str; }\n"
         "struct Rect { w: int; h: int; }\n"
         "impl Shape for Rect {\n"
         "  fn area(r: Rect) -> int { return r.w * r.h; }\n"
         "  fn name(r: Rect) -> str { return \"rect\"; }\n}\n")

CASES = [
    ("non-implementing struct as opaque",
     TRAIT + "struct Other { x: int; }\n"
     "fn bad() -> opaque Shape {\n  return Other { x: 1 };\n}\n"
     "fn main() { println(1); }\n",
     "function returns opaque Shape"),
    ("method not in trait on opaque",
     TRAIT + "fn make() -> opaque Shape {\n  return Rect { w: 3, h: 4 };\n}\n"
     "fn main() {\n  let a: opaque Shape = make();\n  println(a.perim());\n}\n",
     "has no method"),
    ("opaque struct field",
     TRAIT + "struct Holder { s: opaque Shape; }\n"
     "fn main() { println(1); }\n",
     "opaque struct fields are not supported"),
    ("opaque trait with no implementations",
     "trait Empty { fn f() -> int; }\n"
     "fn use(x: opaque Empty) -> int { return 1; }\n"
     "fn main() { println(1); }\n",
     "opaque Empty"),
    ("match on opaque",
     TRAIT + "fn make() -> opaque Shape {\n  return Rect { w: 3, h: 4 };\n}\n"
     "fn main() {\n  let a: opaque Shape = make();\n"
     "  match a {\n    _ => { println(1); }\n  }\n}\n",
     "needs an enum value"),
    ("print opaque",
     TRAIT + "fn make() -> opaque Shape {\n  return Rect { w: 3, h: 4 };\n}\n"
     "fn main() {\n  let a: opaque Shape = make();\n  println(a);\n}\n",
     "cannot print a value of type opaque Shape"),
    ("opaque revealed as concrete",
     TRAIT + "fn make() -> opaque Shape {\n  return Rect { w: 3, h: 4 };\n}\n"
     "fn main() {\n  let a: opaque Shape = make();\n  let r: Rect = a;\n  println(r.w);\n}\n",
     "declared Rect but initialised with opaque Shape"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "o.fg")
        with open(src, "w") as f:
            f.write(PROG)
        exe = os.path.join(td, "o")
        r = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                 "-o", exe, src], ROOT)
        if not check("opaque program builds", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append("opaque program builds")
        else:
            r2 = run([exe], td)
            if not check("opaque results", r2.stdout == EXPECTED,
                         repr(r2.stdout)):
                failures.append("opaque results")
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
            f.write(TRAIT + "fn make() -> opaque Shape {\n"
                    "  return Rect { w: 3, h: 4 };\n}\n"
                    "fn main() {\n  let u: opaque Shape = make();\n}\n")
        rb = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                  "--target", "big32", "--freestanding", "-o",
                  os.path.join(td, "b"), bsrc], ROOT)
        ok = rb.returncode != 0 and "big32: opaque types are not supported" in (
            rb.stderr + rb.stdout)
        if not check("big32 rejects opaques", ok, rb.stderr.strip()[-120:]):
            failures.append("big32 rejects opaques")
        rw = run([sys.executable, os.path.join(ROOT, "forge.py"), "emit-wasm",
                  "-o", os.path.join(td, "w.wasm"), src], ROOT)
        ok = rw.returncode != 0 and "wasm: opaque types are not supported" in (
            rw.stderr + rw.stdout)
        if not check("wasm rejects opaques", ok, rw.stderr.strip()[-120:]):
            failures.append("wasm rejects opaques")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
