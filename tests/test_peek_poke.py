#!/usr/bin/env python3
"""End-to-end tests for the peek32/poke32 raw-memory builtins.

Phase B of the freestanding track: kernel code must touch device
registers, and the only honest way is volatile 32-bit loads/stores
through a raw address. Semantics, pinned here:

  * peek32(addr: int) -> int: one volatile 32-bit load.
  * poke32(addr: int, val: int): one volatile 32-bit store, as a
    statement only (like push) — a write has no value to return,
    and the checker rejects using it as a value.
  * Both are UNCHECKED in every mode: a raw address is unsafe by
    definition, and safe-mode checks cannot judge whether an
    address is a valid device register.
  * WASM rejects both loudly: WASM has no raw addresses.
  * There is no address-of operator in the language, so a native
    runtime round-trip cannot be addressed from Qasida code
    itself; native coverage is build + generated-C inspection +
    a guarded (never executed) poke, and the real runtime proof
    is the big32 model run below.

big32 addresses used (decimal, since the language has no hex
literals): UART TX 268435456 (0x10000000), RX 268435460
(0x10000004, model returns -1), status 268435464 (0x10000008,
model returns 0), scratch RAM 32768 (0x8000, above any small
program's statics/frame).

Tests:
  1. big32 model: UART byte write + status/RX reads + RAM
     round-trip, exact UART transcript
  2. native: generated C contains volatile helpers
  3. native: guarded (never executed) poke runs fine, safe + fast
  4. checker rejects bad arity and non-int arguments
  5. WASM rejects both builtins with a clear error

Exits 0 only if every test passes.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
MODEL = os.path.expanduser("~/workspace/big32/tools/model.py")
FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILURES.append(name)


def write_prog(d, prog, name="prog.fg"):
    path = os.path.join(d, name)
    with open(path, "w") as f:
        f.write(prog)
    return path


def main():
    print("big32 model run")
    if os.path.exists(MODEL):
        d = tempfile.mkdtemp(prefix="peek-poke-big32-")
        path = write_prog(d, """fn main() {
  poke32(268435456, 65);
  println(peek32(268435464));
  println(peek32(268435460));
  poke32(32768, 123456);
  println(peek32(32768));
}
""")
        out = os.path.join(d, "prog")
        r = subprocess.run(FORGE + ["build", path, "--target", "big32", "-o", out],
                           capture_output=True, text=True, timeout=120)
        hexpath = out + ".hex"
        if r.returncode != 0 or not os.path.exists(hexpath):
            check("big32 build", False, f"rc={r.returncode} err={r.stderr!r}")
        else:
            r2 = subprocess.run([sys.executable, MODEL, hexpath],
                                capture_output=True, text=True, timeout=120)
            uart = ""
            if "uart:\n" in r2.stdout:
                uart = r2.stdout.split("uart:\n", 1)[1]
            check("big32 uart transcript",
                  uart.strip() == "A0\n-1\n123456",
                  f"uart={uart!r} full={r2.stdout!r} err={r2.stderr!r}")
    else:
        print("  SKIP big32 (model.py not found)")

    print("native generated C")
    d = tempfile.mkdtemp(prefix="peek-poke-emit-")
    path = write_prog(d, """fn main() {
  let v: int = peek32(1024);
  poke32(2048, v);
  println(v);
}
""")
    r = subprocess.run(FORGE + ["emit", path], capture_output=True,
                       text=True, timeout=60)
    check("native C has volatile helpers",
          r.returncode == 0
          and "volatile uint32_t" in r.stdout
          and "forge_peek32" in r.stdout
          and "forge_poke32" in r.stdout,
          f"rc={r.returncode} err={r.stderr!r}")

    print("native guarded poke runs (safe + fast)")
    d = tempfile.mkdtemp(prefix="peek-poke-run-")
    path = write_prog(d, """fn main() {
  if false {
    poke32(0, 1);
  }
  println(99);
}
""")
    for mode in ("safe", "fast"):
        r = subprocess.run(FORGE + ["run", "--mode", mode, path],
                           capture_output=True, text=True, timeout=60)
        check(f"native guarded poke ({mode})",
              r.returncode == 0 and r.stdout.strip() == "99",
              f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")

    print("checker rejections")
    for name, bad in [
        ("peek32 arity", "fn main() { println(peek32(1, 2)); }\n"),
        ("peek32 str arg", 'fn main() { println(peek32("x")); }\n'),
        ("peek32 float arg", "fn main() { println(peek32(1.5)); }\n"),
        ("poke32 arity", "fn main() { poke32(1); }\n"),
        ("poke32 str val", 'fn main() { poke32(1, "x"); }\n'),
        ("poke32 as value", "fn main() { let x: int = poke32(1, 2); println(x); }\n"),
    ]:
        d = tempfile.mkdtemp(prefix="peek-poke-check-")
        path = write_prog(d, bad)
        r = subprocess.run(FORGE + ["check", path], capture_output=True,
                           text=True, timeout=60)
        check(f"checker rejects {name}", r.returncode != 0,
              f"rc={r.returncode} out={r.stdout!r}")

    print("wasm rejections")
    for name, prog in [
        ("peek32", "fn main() -> int { return peek32(1024); }\n"),
        ("poke32", "fn main() { poke32(1024, 7); }\n"),
    ]:
        d = tempfile.mkdtemp(prefix="peek-poke-wasm-")
        path = write_prog(d, prog)
        out = os.path.join(d, "prog.wasm")
        r = subprocess.run(FORGE + ["build", path, "--target", "wasm", "-o", out],
                           capture_output=True, text=True, timeout=60)
        check(f"wasm rejects {name}",
              r.returncode != 0 and "raw memory" in (r.stdout + r.stderr),
              f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")

    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
