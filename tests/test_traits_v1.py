#!/usr/bin/env python3
"""Traits v1 tests (#5): trait decl + impl blocks + method calls.

A trait is a contract of method signatures; an impl block supplies
the methods for one struct, each with the receiver as its first
parameter. Calls use static dispatch (Rect__area). Inherent impls
(no trait) work too. big32 and WASM reject method calls plainly
in v1: big32 lacks struct parameters, WASM lacks structs.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
FAILURES = []

PROG = """struct Rect {
  w: int,
  h: int
}

struct Canvas {
  r: Rect
}

trait Shape {
  fn area() -> int;
  fn name() -> str;
}

impl Shape for Rect {
  fn area(r: Rect) -> int {
    return r.w * r.h;
  }
  fn name(r: Rect) -> str {
    return "rect";
  }
}

impl Rect {
  fn perim(r: Rect) -> int {
    return 2 * (r.w + r.h);
  }
}

fn main() {
  let r = Rect { w: 3, h: 4 };
  println(r.area());
  println(r.perim());
  println(r.name());
  let c = Canvas { r: Rect { w: 2, h: 5 } };
  println(c.r.area());
}
"""

CASES = [
    ("missing method",
     PROG.replace('  fn name(r: Rect) -> str {\n    return "rect";\n  }\n', ""),
     "missing method 'name'"),
    ("signature mismatch",
     PROG.replace("fn area(r: Rect) -> int {\n    return r.w * r.h;",
                  "fn area(r: Rect) -> str {\n    return \"rect\";"),
     "does not match the trait signature"),
    ("unknown method",
     PROG.replace("println(r.area());", "println(r.volume());"),
     "has no method 'volume'"),
    ("wrong receiver",
     PROG.replace("fn area(r: Rect) -> int", "fn area(r: int) -> int"),
     "must be the struct 'Rect'"),
    ("call on non-struct",
     "struct Rect {\n  w: int,\n  h: int\n}\nfn main() {\n  let x = 5;\n  println(x.area());\n}\n",
     "no methods on type 'int'"),
]


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def build(td, name, src, args):
    p = os.path.join(td, name + ".fg")
    with open(p, "w") as f:
        f.write(src)
    out = os.path.join(td, name)
    r = subprocess.run(FORGE + args + ["-o", out, p],
                       capture_output=True, text=True, cwd=ROOT)
    return r, out, p


def main():
    print("traits v1 (#5)")
    with tempfile.TemporaryDirectory() as td:
        r, out, _ = build(td, "shape", PROG, ["build"])
        check("trait program builds", r.returncode == 0, r.stderr[-300:])
        if r.returncode == 0:
            r2 = subprocess.run([out], capture_output=True, text=True)
            check("method results", r2.stdout == "12\n14\nrect\n10\n",
                  repr(r2.stdout))
        for name, src, needle in CASES:
            r, _, _ = build(td, "bad", src, ["build"])
            check(f"{name} rejected", r.returncode != 0 and needle in
                  (r.stdout + r.stderr), r.stderr[-200:])
        r, _, p = build(td, "shape", PROG, ["build"])
        r = subprocess.run(FORGE + ["fmt", p],
                           capture_output=True, text=True, cwd=ROOT)
        check("fmt runs", r.returncode == 0, r.stderr[-200:])
        r = subprocess.run(FORGE + ["fmt", "--check", p],
                           capture_output=True, text=True, cwd=ROOT)
        check("fmt idempotent", r.returncode == 0, r.stdout[-200:])
        r2 = subprocess.run(FORGE + ["build", "-o", os.path.join(td, "shape2"), p],
                            capture_output=True, text=True, cwd=ROOT)
        if r2.returncode == 0:
            r3 = subprocess.run([os.path.join(td, "shape2")],
                                capture_output=True, text=True)
            check("formatted program still runs",
                  r3.stdout == "12\n14\nrect\n10\n", repr(r3.stdout))
        else:
            check("formatted program still runs", False, r2.stderr[-200:])
        # big32: a freestanding-clean kernel (poke32 output, no
        # println) so the failure is a genuine big32 codegen gap,
        # not the hosted-I/O check. v1 cannot run trait programs
        # there at all: no struct literals/params, no method calls.
        kern = """struct Rect {
  w: int,
  h: int
}

trait Shape {
  fn area() -> int;
}

impl Shape for Rect {
  fn area(r: Rect) -> int {
    return r.w * r.h;
  }
}

fn put(c: int) {
  poke32(0x10000000, c);
}

fn trap_handler(frame: int) {
  csr_write(833, csr_read(833) + 4);
}

fn main() {
  let r = Rect { w: 3, h: 4 };
  put(r.area());
  csr_write(773, 0);
  let h = ecall(0, 0);
}
"""
        r, _, _ = build(td, "shapekern", kern,
                         ["build", "--target", "big32", "--freestanding"])
        check("big32 rejects trait programs", r.returncode != 0 and
              "big32" in (r.stdout + r.stderr),
              r.stderr[-200:])
        r, _, p = build(td, "shape", PROG, ["build"])
        r = subprocess.run(FORGE + ["emit-wasm", "-o", os.path.join(td, "shape.wasm"), p],
                           capture_output=True, text=True, cwd=ROOT)
        check("wasm rejects trait programs", r.returncode != 0 and
              "wasm" in (r.stdout + r.stderr),
              r.stderr[-200:])
    if FAILURES:
        print("FAILED:", FAILURES)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
