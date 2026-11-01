"""Top-500 #23: defer v1
(tests/test_defer_v1.py) — to be moved into tests/ once the
void suite run lands. Zig-style block-scoped defer: `defer
call();` runs at the enclosing block's exit, LIFO, including
early returns, breaks, and continues; loop-body defers run
each iteration. Deferred call arguments are evaluated at
exit time in v1 (documented).
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PROG = """
fn say(msg: str) {
  println(msg);
}
fn f() -> int {
  defer say("exit");
  defer say("cleanup");
  if 1 == 1 {
    defer say("inner");
    println("body");
  }
  println("after");
  return 7;
}
fn g() -> int {
  defer say("g-exit");
  if 1 == 1 {
    return 3;
  }
  return 4;
}
fn main() {
  println(f());
  println(g());
  let mut total: int = 0;
  for i in 0..3 {
    defer say("iter");
    total = total + i;
  }
  println(total);
  for i in 0..5 {
    defer say("b");
    if i == 1 {
      break;
    }
  }
}
"""

EXPECTED = "body\ninner\nafter\ncleanup\nexit\n7\ng-exit\n3\niter\niter\niter\n3\nb\nb\n"

CASES = [
    ("defer non-call",
     "fn main() {\n  defer 5;\n}\n",
     "defer needs a call"),
    ("defer bad args",
     "fn say(msg: str) { println(msg); }\nfn main() {\n  defer say(5);\n}\n",
     "must be str, got int"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "d.fg")
        with open(src, "w") as f:
            f.write(PROG)
        exe = os.path.join(td, "d")
        r = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                 "-o", exe, src], ROOT)
        if not check("defer program builds", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append("defer program builds")
        else:
            r2 = run([exe], td)
            if not check("defer results", r2.stdout == EXPECTED,
                         repr(r2.stdout)):
                failures.append("defer results")
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
            fexe = os.path.join(td, "f")
            rb = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                      "-o", fexe, fmt], ROOT)
            if rb.returncode == 0:
                r3 = run([fexe], td)
                if not check("formatted program still runs",
                             r3.stdout == EXPECTED, repr(r3.stdout)):
                    failures.append("formatted program still runs")
            else:
                check("formatted program still runs", False, rb.stderr.strip())
                failures.append("formatted program still runs")
        gate = os.path.join(td, "g.fg")
        with open(gate, "w") as f:
            f.write("fn f(x: int) -> int { return x + 1; }\n"
                    "fn main() {\n  defer f(1);\n}\n")
        rb = run([sys.executable, os.path.join(ROOT, "forge.py"),
                  "build", "--target", "big32", "--freestanding",
                  "-o", os.path.join(td, "g"), gate], ROOT)
        ok = rb.returncode != 0 and "big32: defer is not supported in v1" in (rb.stderr + rb.stdout)
        if not check("big32 rejects defer", ok,
                     (rb.stderr.strip().splitlines() or [""])[-1]):
            failures.append("big32 rejects defer")
        rw = run([sys.executable, os.path.join(ROOT, "forge.py"),
                  "emit-wasm", gate], ROOT)
        ok = rw.returncode != 0 and "wasm: defer is not supported in v1" in (rw.stderr + rw.stdout)
        if not check("wasm rejects defer", ok,
                     (rw.stderr.strip().splitlines() or [""])[-1]):
            failures.append("wasm rejects defer")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
