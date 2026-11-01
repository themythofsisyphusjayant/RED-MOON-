"""Top-500 #17: checked float-to-int casts v1 (tests/test_checked_casts_v1.py).

Float-to-int casts truncate toward zero and, in safe mode,
fail when the float is outside the target range, or NaN or
infinite. Fast mode keeps the plain truncating C cast.
WASM already traps on out-of-range float-to-int conversion,
and big32 rejects float casts outright, so neither backend
changes in this batch.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PROG = """
fn main() {
  println(42.9 as int);
  println(-42.9 as int);
  println(2147483647.0 as i32);
  println((-2147483648.0) as i32);
  println(255.0 as u8);
  println(9007199254740992.0 as u64);
  println(4611686018427387904.0 as int);
}
"""

EXPECTED = "42\n-42\n2147483647\n-2147483648\n255\n9007199254740992\n4611686018427387904\n"

FAIL_CASES = [
    ("i32 overflow",
     "fn main() {\n  println(2147483648.0 as i32);\n}\n"),
    ("negative to unsigned",
     "fn main() {\n  println((-1.0) as u8);\n}\n"),
    ("NaN to int",
     "fn main() {\n  let nan: float = 0.0 / 0.0;\n  println(nan as int);\n}\n"),
    ("infinity to int",
     "fn main() {\n  let inf: float = 1.0 / 0.0;\n  println(inf as int);\n}\n"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "c.fg")
        with open(src, "w") as f:
            f.write(PROG)
        exe = os.path.join(td, "c")
        r = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                 "-o", exe, src], ROOT)
        if not check("checked-cast program builds", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append("checked-cast program builds")
        else:
            r2 = run([exe], td)
            if not check("checked-cast results", r2.stdout == EXPECTED,
                         repr(r2.stdout)):
                failures.append("checked-cast results")
        # Fast mode: the same valid casts truncate identically.
        fexe = os.path.join(td, "cf")
        rf = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                  "--mode", "fast", "-o", fexe, src], ROOT)
        if not check("fast-mode builds", rf.returncode == 0,
                     rf.stderr.strip().splitlines()[-1] if rf.stderr else ""):
            failures.append("fast-mode builds")
        else:
            r2 = run([fexe], td)
            if not check("fast-mode results", r2.stdout == EXPECTED,
                         repr(r2.stdout)):
                failures.append("fast-mode results")
        for name, prog in FAIL_CASES:
            p = os.path.join(td, "f.fg")
            with open(p, "w") as f:
                f.write(prog)
            fe = os.path.join(td, "f")
            rb = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                      "-o", fe, p], ROOT)
            if rb.returncode != 0:
                check(f"{name} fails", False, rb.stderr.strip())
                failures.append(name)
                continue
            rr = run([fe], td)
            ok = (rr.returncode != 0
                  and "float to int cast out of range" in (rr.stderr + rr.stdout))
            if not check(f"{name} fails", ok,
                         (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(name)
        fmt = os.path.join(td, "fmt.fg")
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
        bsrc = os.path.join(td, "bk.fg")
        with open(bsrc, "w") as f:
            f.write("fn main() {\n  let x: int = 42.9 as int;\n}\n")
        rb = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                  "--target", "big32", "--freestanding", "-o",
                  os.path.join(td, "b"), bsrc], ROOT)
        ok = rb.returncode != 0 and "int<->float casts are not supported" in (
            rb.stderr + rb.stdout)
        if not check("big32 still rejects float casts", ok,
                     rb.stderr.strip()[-120:]):
            failures.append("big32 still rejects float casts")
        wsrc = os.path.join(td, "w.fg")
        with open(wsrc, "w") as f:
            f.write("fn main() {\n  println(42.9 as int);\n}\n")
        rw = run([sys.executable, os.path.join(ROOT, "forge.py"), "emit-wasm",
                  "-o", os.path.join(td, "w.wasm"), wsrc], ROOT)
        if not check("wasm still accepts float casts (trapping)",
                     rw.returncode == 0, rw.stderr.strip()[-120:]):
            failures.append("wasm still accepts float casts (trapping)")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
