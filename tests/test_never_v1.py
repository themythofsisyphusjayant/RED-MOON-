"""Top-500 #14: never/bottom type v1 (tests/test_never_v1.py).

`never` is the type of expressions that never produce a value
(a call to a function declared `-> never`). It coerces to any
expected type at value sites, and a function body containing a
top-level diverging statement satisfies the return requirement.
A never function must diverge and cannot return.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PROG = """
fn die(msg: str) -> never {
  fail(msg);
}
fn die2() -> never {
  die("boom");
}
fn get(cond: int) -> int {
  if cond == 1 {
    return 5;
  }
  die("no value");
}
fn use_never() -> int {
  let x: int = die("x");
  return x;
}
fn main() {
  println(get(1));
  println(use_never());
  println(1);
  let mut y: int = 0;
  y = die("y");
  println(y);
}
"""

# get(1) = 5. use_never() never returns (die diverges), so the
# prints after it never run: the program's only output is 5,
# then fail("x") aborts. The trailing prints exist to prove the
# program COMPILES with never values in let/assign/return
# positions; they are unreachable at runtime.
EXPECTED = "5\n"

CASES = [
    ("never function that falls off the end",
     "fn die() -> never {\n  println(1);\n}\nfn main() {\n  die();\n}\n",
     "must end with a diverging statement"),
    ("never function that returns",
     "fn die() -> never {\n  return die();\n}\nfn main() {\n  die();\n}\n",
     "cannot return"),
    ("never function diverging only inside a branch",
     "fn die(c: int) -> never {\n  if c == 1 {\n    fail(\"x\");\n  }\n  println(1);\n}\nfn main() {\n  die(1);\n}\n",
     "must end with a diverging statement"),
    ("non-void function with no return and no diverger",
     "fn get() -> int {\n  println(1);\n}\nfn main() {\n  println(get());\n}\n",
     "does not end with a return"),
    ("never value in a binary operation",
     "fn die() -> never {\n  fail(\"x\");\n}\nfn main() {\n  println(die() + 1);\n}\n",
     "needs matching int or float operands"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "n.fg")
        with open(src, "w") as f:
            f.write(PROG)
        exe = os.path.join(td, "n")
        r = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                 "-o", exe, src], ROOT)
        if not check("never program builds", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append("never program builds")
        else:
            r2 = run([exe], td)
            # fail() aborts with a nonzero exit; stdout must be
            # exactly the value produced before the divergence.
            if not check("never results", r2.stdout == EXPECTED
                         and r2.returncode != 0, repr(r2.stdout)):
                failures.append("never results")
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
        bsrc = os.path.join(td, "bk.fg")
        with open(bsrc, "w") as f:
            f.write("fn die() -> never {\n  fail(\"x\");\n}\nfn main() {\n  die();\n}\n")
        rb = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                  "--target", "big32", "--freestanding", "-o",
                  os.path.join(td, "b"), bsrc], ROOT)
        ok = rb.returncode != 0 and "big32: never types are not supported" in (
            rb.stderr + rb.stdout)
        if not check("big32 rejects never", ok, rb.stderr.strip()[-120:]):
            failures.append("big32 rejects never")
        rw = run([sys.executable, os.path.join(ROOT, "forge.py"), "emit-wasm",
                  "-o", os.path.join(td, "w.wasm"), bsrc], ROOT)
        ok = rw.returncode != 0 and "wasm: never types are not supported" in (
            rw.stderr + rw.stdout)
        if not check("wasm rejects never", ok, rw.stderr.strip()[-120:]):
            failures.append("wasm rejects never")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
