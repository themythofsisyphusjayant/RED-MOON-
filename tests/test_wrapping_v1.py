#!/usr/bin/env python3
"""Wrapping arithmetic tests (#10): wrapping_add/sub/mul/neg.

Defined wraparound beside the checked default: these never fail.
Native wraps via unsigned arithmetic; big32 and WASM wrap by
nature; all three backends are exercised here.
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

PROG = """fn main() {
  let max: int = 9223372036854775807;
  println(wrapping_add(max, 1));
  let min: int = 0 - 9223372036854775807 - 1;
  println(wrapping_sub(min, 1));
  println(wrapping_mul(max, 2));
  println(wrapping_neg(min));
  println(wrapping_add(5, 7));
}
"""

KERNEL = """fn put(c: int) {
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
  print_int(wrapping_add(2147483647, 2));
  put(10);
  print_int(wrapping_neg(0 - 2147483647));
  put(10);
  let min32: int = 0 - 2147483647 - 1;
  if wrapping_add(2147483647, 1) == min32 {
    put(89);
    put(10);
  }
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
    ("arity add",
     "fn main() {\n  println(wrapping_add(1));\n}\n",
     "takes exactly two arguments"),
    ("float arg",
     "fn main() {\n  println(wrapping_add(1.5, 2));\n}\n",
     "takes int arguments"),
    ("arity neg",
     "fn main() {\n  println(wrapping_neg(1, 2));\n}\n",
     "takes exactly one int argument"),
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
    print("wrapping arithmetic (#10)")
    with tempfile.TemporaryDirectory() as td:
        r, out, _ = build(td, "wrap", PROG, ["build"])
        check("wrapping program builds", r.returncode == 0, r.stderr[-300:])
        if r.returncode == 0:
            r2 = subprocess.run([out], capture_output=True, text=True)
            check("wrapping results",
                  r2.stdout == "-9223372036854775808\n9223372036854775807\n"
                  "-2\n-9223372036854775808\n12\n", repr(r2.stdout))
        for name, src, needle in CASES:
            r, _, _ = build(td, "bad", src, ["build"])
            check(f"{name} rejected", r.returncode != 0 and needle in
                  (r.stdout + r.stderr), r.stderr[-200:])
        r, kout, _ = build(td, "wrapkern", KERNEL,
                           ["build", "--target", "big32", "--freestanding"])
        check("wrapping kernel builds big32", r.returncode == 0, r.stderr[-300:])
        if r.returncode == 0:
            spec = importlib.util.spec_from_file_location("big32model", MODEL)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            res = mod.run(kout + ".hex")
            uart = res["uart"].decode("utf-8", "replace")
            check("kernel halts", res["halted"] is True)
            check("kernel transcript", uart == "-2147483647\n2147483647\nY\nDONE\n",
                  repr(uart))
        r, _, p = build(td, "wrap", PROG, ["build"])
        r = subprocess.run(FORGE + ["emit-wasm", "-o", os.path.join(td, "wrap.wasm"), p],
                           capture_output=True, text=True, cwd=ROOT)
        check("wrapping emits wasm", r.returncode == 0, r.stderr[-300:])
    if FAILURES:
        print("FAILED:", FAILURES)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
