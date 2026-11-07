#!/usr/bin/env python3
"""End-to-end tests for --freestanding mode.

Phase C of the freestanding track: the language stands without
Linux underneath. Freestanding v1 is the integer/bool kernel
subset, and its rules are:

  * No libc: the native build uses -nostdlib, the program's own
    _start entry calls qasida_main and exits via the raw Linux
    exit_group syscall with main's return value. ldd reports
    "statically linked" and nm shows no undefined symbols.
  * No OS at check time: files, sockets, threads (spawn/scope),
    clock, args, print/println, libm builtins (sqrt/exp/log/pow/
    abs), and extern C functions are all clean checker errors.
  * No allocator at codegen time: strings and arrays have no
    values, so any program building one fails with a clear
    error, never a C or link error. fail() halts (infinite loop)
    instead of exiting: there is no OS to exit to.
  * big32 runs under the same flag (its output is already bare
    metal); WASM refuses the flag outright.
  * main may return int (the exit code) or nothing (exit 0).

Tests:
  1. native: exit code from computed value (safe mode)
  2. native: ldd static + nm no-undefined + _start present
  3. native: void main exits 0; fast mode also builds+runs
  4. native: checked overflow halts (timeout, not exit)
  5. big32 model: freestanding OK via poke32 + RAM round-trip
  6. checker rejects print, read_file, http_get, clock_micros,
     args, spawn, scope, sqrt, abs, extern (freestanding only)
  7. codegen rejects a string literal (freestanding only)
  8. wasm + freestanding refused clearly
  9. hosted control: the print program builds WITHOUT the flag

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


def build(d, prog, *extra):
    path = write_prog(d, prog)
    out = os.path.join(d, "prog")
    r = subprocess.run(FORGE + ["build", path, "--freestanding", "-o", out] + list(extra),
                       capture_output=True, text=True, timeout=120)
    return path, out, r


def main():
    print("native exit codes")
    d = tempfile.mkdtemp(prefix="fs-native-")
    _, out, r = build(d, """fn helper(x: int) -> int {
  return (x & 12) + (1 << 4);
}
fn main() -> int {
  let mut v: int = helper(10);
  let mut i: int = 0;
  while i < 3 {
    v = v + 1;
    i = i + 1;
  }
  return v;
}
""")
    check("native freestanding builds", r.returncode == 0, f"err={r.stderr!r}")
    if r.returncode == 0:
        r2 = subprocess.run([out], capture_output=True, text=True, timeout=30)
        check("native exit code 27", r2.returncode == 27, f"rc={r2.returncode}")
        r3 = subprocess.run(["ldd", out], capture_output=True, text=True, timeout=30)
        check("ldd statically linked", "not a dynamic executable" in r3.stdout
              or "statically linked" in r3.stdout, f"ldd={r3.stdout!r}")
        r4 = subprocess.run(["nm", out], capture_output=True, text=True, timeout=30)
        undef = [l for l in r4.stdout.splitlines() if " U " in l]
        check("nm no undefined symbols", not undef, f"undef={undef!r}")
        check("nm _start + qasida_main present",
              " T _start" in r4.stdout and " T qasida_main" in r4.stdout,
              f"nm={r4.stdout!r}")

    print("native void main + fast mode")
    d = tempfile.mkdtemp(prefix="fs-void-")
    _, out, r = build(d, "fn main() { let x: int = 1 + 2; }\n")
    check("void main builds", r.returncode == 0, f"err={r.stderr!r}")
    if r.returncode == 0:
        r2 = subprocess.run([out], capture_output=True, text=True, timeout=30)
        check("void main exits 0", r2.returncode == 0, f"rc={r2.returncode}")
    d = tempfile.mkdtemp(prefix="fs-fast-")
    _, out, r = build(d, "fn main() -> int { return 40 + 2; }\n", "--mode", "fast")
    check("fast freestanding builds", r.returncode == 0, f"err={r.stderr!r}")
    if r.returncode == 0:
        r2 = subprocess.run([out], capture_output=True, text=True, timeout=30)
        check("fast exit code 42", r2.returncode == 42, f"rc={r2.returncode}")

    print("native checked overflow halts")
    d = tempfile.mkdtemp(prefix="fs-halt-")
    _, out, r = build(d, """fn main() -> int {
  let x: int = 9223372036854775807;
  return x + 1;
}
""")
    check("overflow program builds", r.returncode == 0, f"err={r.stderr!r}")
    if r.returncode == 0:
        try:
            subprocess.run([out], capture_output=True, text=True, timeout=5)
            check("overflow halts (timeout)", False, "exited instead of halting")
        except subprocess.TimeoutExpired:
            check("overflow halts (timeout)", True)

    print("big32 model run (freestanding)")
    if os.path.exists(MODEL):
        d = tempfile.mkdtemp(prefix="fs-big32-")
        path = write_prog(d, """fn main() {
  poke32(32768, 24);
  if peek32(32768) == 24 {
    poke32(268435456, 79);
    poke32(268435456, 75);
  }
}
""")
        out = os.path.join(d, "prog")
        r = subprocess.run(FORGE + ["build", path, "--target", "big32",
                                    "--freestanding", "-o", out],
                           capture_output=True, text=True, timeout=120)
        hexpath = out + ".hex"
        if r.returncode != 0 or not os.path.exists(hexpath):
            check("big32 freestanding builds", False, f"rc={r.returncode} err={r.stderr!r}")
        else:
            r2 = subprocess.run([sys.executable, MODEL, hexpath],
                                capture_output=True, text=True, timeout=120)
            uart = ""
            if "uart:\n" in r2.stdout:
                uart = r2.stdout.split("uart:\n", 1)[1]
            check("big32 freestanding uart OK", uart.strip() == "OK",
                  f"uart={uart!r} err={r2.stderr!r}")
    else:
        print("  SKIP big32 (model.py not found)")

    print("freestanding rejections")
    cases = [
        ("println", "fn main() { println(1); }\n", "build"),
        ("read_file", 'fn main() { let s: str = read_file("x"); }\n', "check"),
        ("http_get", 'fn main() { let s: str = http_get("http://x"); }\n', "check"),
        ("clock_micros", "fn main() -> int { return clock_micros(); }\n", "check"),
        ("args", "fn main() { let a: [str] = args(); }\n", "check"),
        ("spawn", "fn worker() { }\nfn main() { spawn worker(); }\n", "check"),
        ("scope", "fn worker() { }\nfn main() { scope { spawn worker(); } }\n", "check"),
        ("sqrt", "fn f() -> float { return sqrt(4.0); }\nfn main() { let x: float = f(); }\n", "check"),
        ("abs", "fn main() -> int { return abs(0 - 5); }\n", "check"),
        ("extern", "extern fn puts(s: str) -> int;\nfn main() { let x: int = puts(\"hi\"); }\n", "check"),
    ]
    for name, prog, cmd in cases:
        d = tempfile.mkdtemp(prefix="fs-reject-")
        path = write_prog(d, prog)
        if cmd == "check":
            r = subprocess.run(FORGE + ["check", path, "--freestanding"],
                               capture_output=True, text=True, timeout=60)
        else:
            r = subprocess.run(FORGE + ["build", path, "--freestanding",
                                        "-o", os.path.join(d, "prog")],
                               capture_output=True, text=True, timeout=60)
        check(f"freestanding rejects {name}",
              r.returncode != 0 and "freestanding" in (r.stdout + r.stderr),
              f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")

    print("freestanding codegen rejects strings")
    d = tempfile.mkdtemp(prefix="fs-str-")
    path = write_prog(d, 'fn main() { let s: str = "hi"; }\n')
    r = subprocess.run(FORGE + ["build", path, "--freestanding",
                                "-o", os.path.join(d, "prog")],
                       capture_output=True, text=True, timeout=60)
    check("freestanding rejects string value",
          r.returncode != 0 and "freestanding" in (r.stdout + r.stderr),
          f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")

    print("wasm refuses freestanding")
    d = tempfile.mkdtemp(prefix="fs-wasm-")
    path = write_prog(d, "fn main() -> int { return 1; }\n")
    r = subprocess.run(FORGE + ["build", path, "--target", "wasm",
                                "--freestanding", "-o", os.path.join(d, "prog.wasm")],
                       capture_output=True, text=True, timeout=60)
    check("wasm + freestanding refused",
          r.returncode != 0 and "freestanding" in (r.stdout + r.stderr),
          f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")

    print("hosted control")
    d = tempfile.mkdtemp(prefix="fs-hosted-")
    path = write_prog(d, "fn main() { println(1); }\n")
    r = subprocess.run(FORGE + ["build", path, "-o", os.path.join(d, "prog")],
                       capture_output=True, text=True, timeout=60)
    check("same print program builds hosted", r.returncode == 0, f"err={r.stderr!r}")

    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
