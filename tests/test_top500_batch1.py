#!/usr/bin/env python3
"""Top-500 batch 1 tests: #15 literals + #61 continue.

#15: binary/octal literals and digit separators (lexer-only).
  Native values: 0b1010=10, 0o777=511, 1_000=1000, 0xFF_FF=65535.
  Errors: bare 0b, bad octal digit 0o8, doubled underscore 1__2,
  trailing underscore 1_ — all rejected.
#61: continue, mirroring break on every backend.
  Native: sum of odds 1..10 skipping evens = 25, in while and
  for-range loops. Big32 model kernel: same two sums via UART,
  transcript "25\\n25\\nDONE\\n", halted. The for-range sum proves
  the increment still runs on continue (jumping to the loop head
  instead would loop forever). WASM: emit succeeds. Errors:
  continue outside a loop rejected.
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

LIT_SRC = """fn main() {
  println(0b1010);
  println(0o777);
  println(1_000);
  println(0xFF_FF);
}
"""

CONT_SRC = """fn main() {
  let mut i: int = 0;
  let mut s: int = 0;
  while i < 10 {
    i = i + 1;
    if i % 2 == 0 {
      continue;
    }
    s = s + i;
  }
  println(s);
  let mut t: int = 0;
  for v in range(10) {
    if v % 2 == 0 {
      continue;
    }
    t = t + v;
  }
  println(t);
}
"""

KERNEL_SRC = """fn put(c: int) {
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
  let mut i: int = 0;
  let mut s: int = 0;
  while i < 10 {
    i = i + 1;
    if i % 2 == 0 {
      continue;
    }
    s = s + i;
  }
  print_int(s);
  put(10);
  let mut t: int = 0;
  for v in range(10) {
    if v % 2 == 0 {
      continue;
    }
    t = t + v;
  }
  print_int(t);
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


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def run_src(td, name, src, args):
    p = os.path.join(td, name + ".fg")
    with open(p, "w") as f:
        f.write(src)
    out = os.path.join(td, name)
    r = subprocess.run(FORGE + args + ["-o", out, p],
                       capture_output=True, text=True, cwd=ROOT)
    return r, out


def main():
    print("top-500 batch 1 (#15 literals, #61 continue)")
    with tempfile.TemporaryDirectory() as td:
        r, out = run_src(td, "lit", LIT_SRC, ["build"])
        check("literals build", r.returncode == 0, r.stderr[-300:])
        if r.returncode == 0:
            r2 = subprocess.run([out], capture_output=True, text=True)
            check("literal values", r2.stdout == "10\n511\n1000\n65535\n",
                  repr(r2.stdout))
        for bad, needle in [("0b", "binary"), ("0o8", "octal"),
                            ("1__2", "underscore"), ("1_", "underscore")]:
            p = os.path.join(td, "bad.fg")
            with open(p, "w") as f:
                f.write(f"fn main() {{\n  println({bad});\n}}\n")
            r = subprocess.run(FORGE + ["build", "-o", os.path.join(td, "bad"), p],
                               capture_output=True, text=True, cwd=ROOT)
            check(f"literal {bad} rejected", r.returncode != 0 and needle in
                  (r.stdout + r.stderr), r.stderr[-200:])
        r, out = run_src(td, "cont", CONT_SRC, ["build"])
        check("continue builds native", r.returncode == 0, r.stderr[-300:])
        if r.returncode == 0:
            r2 = subprocess.run([out], capture_output=True, text=True)
            check("continue sums", r2.stdout == "25\n25\n", repr(r2.stdout))
        r, kout = run_src(td, "contkern", KERNEL_SRC,
                          ["build", "--target", "big32", "--freestanding"])
        check("continue kernel builds big32", r.returncode == 0, r.stderr[-300:])
        if r.returncode == 0:
            spec = importlib.util.spec_from_file_location("big32model", MODEL)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            res = mod.run(kout + ".hex")
            uart = res["uart"].decode("utf-8", "replace")
            check("kernel halts", res["halted"] is True)
            check("kernel transcript", uart == "25\n25\nDONE\n", repr(uart))
        p = os.path.join(td, "cont.fg")
        with open(p, "w") as f:
            # While-only: WASM has no For support yet (a separate,
            # pre-existing gap), so the WASM check uses a while loop.
            f.write("""fn main() {
  let mut i: int = 0;
  let mut s: int = 0;
  while i < 10 {
    i = i + 1;
    if i % 2 == 0 {
      continue;
    }
    s = s + i;
  }
  println(s);
}
""")
        r = subprocess.run(FORGE + ["emit-wasm", "-o", os.path.join(td, "cont.wasm"), p],
                           capture_output=True, text=True, cwd=ROOT)
        check("continue emits wasm", r.returncode == 0, r.stderr[-300:])
        p = os.path.join(td, "outside.fg")
        with open(p, "w") as f:
            f.write("fn main() {\n  continue;\n}\n")
        r = subprocess.run(FORGE + ["build", "-o", os.path.join(td, "outside"), p],
                           capture_output=True, text=True, cwd=ROOT)
        check("continue outside loop rejected", r.returncode != 0 and
              "continue outside a loop" in (r.stdout + r.stderr),
              r.stderr[-200:])
    if FAILURES:
        print("FAILED:", FAILURES)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
