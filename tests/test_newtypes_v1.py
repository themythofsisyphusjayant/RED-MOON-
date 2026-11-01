#!/usr/bin/env python3
"""Distinct newtypes tests (#11): newtype UserId = int.

A newtype is its own type, never equal to its underlying type:
values cross only via explicit casts, both directions, to the
newtype's own underlying type. At runtime a newtype value IS its
underlying value, so native and big32 codegen map it directly.
Equality of two values of the SAME newtype is allowed when the
underlying type is itself comparable; arithmetic, ordering, field
access, and indexing through a newtype need a cast out first.
WASM support is a later slice.
"""
import importlib.util
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
MODEL = os.path.expanduser("~/workspace/big32/tools/model.py")
FAILURES = []

PROG = """newtype UserId = int;
newtype OtherId = int;
type A = int;
newtype N = A;

fn make(id: int) -> UserId {
  return id as UserId;
}

fn main() {
  let u = make(42);
  println(u as int);
  let v: UserId = 7 as UserId;
  println(v as int);
  println(u == v);
  let o: OtherId = 3 as OtherId;
  println(o as int);
  let n: N = 9 as N;
  println(n as int);
}
"""

KERNEL = """newtype N = int;

fn put(c: int) {
  poke32(0x10000000, c);
}

fn print_int(v: int) {
  if v < 0 {
    put(45);
    print_int(0 - v);
    return;
  }
  if v >= 10 {
    print_int(v / 10);
  }
  put(48 + v % 10);
}

fn trap_handler(frame: int) {
  let cause = csr_read(834);
  if cause < 0 {
    poke32(0x10000018, 0 - 1);
    poke32(0x1000001C, 0 - 1);
    return;
  }
  csr_write(833, csr_read(833) + 4);
}

fn main() {
  let x: N = 42 as N;
  print_int(x as int);
  put(10);
  put(68);
  put(79);
  put(78);
  put(69);
  put(10);
  csr_write(773, 0);
  let h = ecall(0, 0);
}
"""

CASES = [
    ("int assigned to newtype",
     "newtype UserId = int;\nfn main() {\n  let u: UserId = 5;\n  println(u as int);\n}\n",
     "UserId"),
    ("newtype passed as int",
     "newtype UserId = int;\nfn f(x: int) -> int {\n  return x;\n}\nfn main() {\n  let u: UserId = 5 as UserId;\n  println(f(u));\n}\n",
     "UserId"),
    ("newtype arithmetic",
     "newtype UserId = int;\nfn main() {\n  let u: UserId = 5 as UserId;\n  println(u + 1);\n}\n",
     "UserId"),
    ("cross-newtype cast",
     "newtype UserId = int;\nnewtype OtherId = int;\nfn main() {\n  let u: UserId = 5 as UserId;\n  let o: OtherId = u as OtherId;\n  println(o as int);\n}\n",
     "cannot cast UserId to OtherId"),
    ("duplicate newtype",
     "newtype A = int;\nnewtype A = str;\nfn main() {}\n",
     "duplicate newtype 'A'"),
    ("unknown target",
     "newtype Foo = Bar;\nfn main() {}\n",
     "targets unknown type 'Bar'"),
    ("collision with struct",
     "struct S {\n  x: int\n}\nnewtype S = int;\nfn main() {}\n",
     "collides with an existing type"),
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
    print("distinct newtypes (#11)")
    with tempfile.TemporaryDirectory() as td:
        r, out, _ = build(td, "nt", PROG, ["build"])
        check("newtype program builds", r.returncode == 0, r.stderr[-300:])
        if r.returncode == 0:
            r2 = subprocess.run([out], capture_output=True, text=True)
            check("newtype results", r2.stdout == "42\n7\nfalse\n3\n9\n",
                  repr(r2.stdout))
        for name, src, needle in CASES:
            r, _, _ = build(td, "bad", src, ["build"])
            check(f"{name} rejected", r.returncode != 0 and needle in
                  (r.stdout + r.stderr), r.stderr[-200:])
        r, _, p = build(td, "nt", PROG, ["build"])
        r = subprocess.run(FORGE + ["fmt", p],
                           capture_output=True, text=True, cwd=ROOT)
        check("fmt runs", r.returncode == 0, r.stderr[-200:])
        r = subprocess.run(FORGE + ["fmt", "--check", p],
                           capture_output=True, text=True, cwd=ROOT)
        check("fmt idempotent", r.returncode == 0, r.stdout[-200:])
        r2 = subprocess.run(FORGE + ["build", "-o", os.path.join(td, "nt2"), p],
                            capture_output=True, text=True, cwd=ROOT)
        if r2.returncode == 0:
            r3 = subprocess.run([os.path.join(td, "nt2")],
                                capture_output=True, text=True)
            check("formatted program still runs",
                  r3.stdout == "42\n7\nfalse\n3\n9\n", repr(r3.stdout))
        else:
            check("formatted program still runs", False, r2.stderr[-200:])
        r, kout, _ = build(td, "ntkern", KERNEL,
                           ["build", "--target", "big32", "--freestanding"])
        check("newtype kernel builds big32", r.returncode == 0, r.stderr[-300:])
        if r.returncode == 0:
            spec = importlib.util.spec_from_file_location("big32model", MODEL)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            res = mod.run(kout + ".hex")
            uart = res["uart"].decode("utf-8", "replace")
            check("kernel halts", res["halted"] is True)
            check("kernel transcript", uart == "42\nDONE\n", repr(uart))
    if FAILURES:
        print("FAILED:", FAILURES)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
