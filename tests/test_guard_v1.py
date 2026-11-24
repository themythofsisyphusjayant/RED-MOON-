"""Top-500 #64: guard statements (tests/test_guard_v1.py).

Precondition helpers in forge_lang/stdlib/guard.fg that return
Result<int, str> so the CALLER can early-return with `?`:
guard_true / guard_false / guard_positive, plus guard_ok as a
pass-through checkpoint. A library CANNOT early-return from the
caller — the `?` at the call site does the early return; the
helper only produces the Err value. The `?` is used in the
`let _g: int = guard_true(...)?;` form: a bare
`guard_true(...)?;` statement is rejected by the Python compiler
("an expression statement must be a function call"), while the
hosted compiler accepts it, so only the let-form is tested.

v1 limits (named in the catalog): int results only; messages are
plain strings. Both compilers (Python + hosted). Runs use
cwd=ROOT (like test_errrender_v1.py): the hosted binary resolves
stdlib imports relative to the repo root (forge_lang/stdlib/),
so a temp cwd would break every import. Nothing is written to
the tree.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO_EXPECTED = """10
false
x must be positive
x must be positive
false
x must not be zero
10
7
bad
"""

# (name, program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("guard_true passes a true condition",
     r"""import "guard.fg";
fn main() -> int {
  let g: Result<int, str> = guard_true(2 > 1, "nope");
  println(g.ok);
  println(g.value);
  return 0;
}
""",
     """true
0
""",
     ""),
    ("guard_true fails a false condition with the message",
     r"""import "guard.fg";
fn main() -> int {
  let g: Result<int, str> = guard_true(1 > 2, "must hold");
  println(g.ok);
  println(g.error);
  return 0;
}
""",
     """false
must hold
""",
     ""),
    ("guard_false passes when false, fails when true",
     r"""import "guard.fg";
fn main() -> int {
  let a: Result<int, str> = guard_false(false, "was true");
  println(a.ok);
  let b: Result<int, str> = guard_false(true, "was true");
  println(b.ok);
  println(b.error);
  return 0;
}
""",
     """true
false
was true
""",
     ""),
    ("guard_positive returns Ok(n) or Err(msg)",
     r"""import "guard.fg";
fn main() -> int {
  let a: Result<int, str> = guard_positive(5, "not positive");
  println(a.ok);
  println(a.value);
  let b: Result<int, str> = guard_positive(0, "not positive");
  println(b.ok);
  println(b.error);
  let c: Result<int, str> = guard_positive(0 - 3, "not positive");
  println(c.error);
  return 0;
}
""",
     """true
5
false
not positive
not positive
""",
     ""),
    ("guard_ok passes Ok and Err through unchanged",
     r"""import "guard.fg";
fn main() -> int {
  let ok: Result<int, str> = Result { ok: true, value: 7, error: "" };
  let g: Result<int, str> = guard_ok(ok);
  println(g.ok);
  println(g.value);
  let err: Result<int, str> = Result { ok: false, value: 0, error: "bad" };
  let g2: Result<int, str> = guard_ok(err);
  println(g2.ok);
  println(g2.error);
  return 0;
}
""",
     """true
7
false
bad
""",
     ""),
    ("caller early-returns via ? on the success path",
     r"""import "guard.fg";
fn checked(x: int) -> Result<int, str> {
  let _g: int = guard_true(x > 0, "x must be positive")?;
  return Result { ok: true, value: x * 2, error: "" };
}
fn main() -> int {
  let r: Result<int, str> = checked(5);
  println(r.ok);
  println(r.value);
  return 0;
}
""",
     """true
10
""",
     ""),
    ("caller early-returns via ? on the failure path",
     r"""import "guard.fg";
fn checked(x: int) -> Result<int, str> {
  let _g: int = guard_true(x > 0, "x must be positive")?;
  return Result { ok: true, value: x * 2, error: "" };
}
fn main() -> int {
  let r: Result<int, str> = checked(0);
  println(r.ok);
  println(r.error);
  let r2: Result<int, str> = checked(0 - 4);
  println(r2.error);
  return 0;
}
""",
     """false
x must be positive
x must be positive
""",
     ""),
    ("first failing guard wins in a chain",
     r"""import "guard.fg";
fn checked(x: int) -> Result<int, str> {
  let _g: int = guard_true(x > 0, "first: positive")?;
  let _h: int = guard_true(x < 10, "second: under ten")?;
  return Result { ok: true, value: x, error: "" };
}
fn main() -> int {
  let a: Result<int, str> = checked(0);
  println(a.error);
  let b: Result<int, str> = checked(50);
  println(b.error);
  let c: Result<int, str> = checked(5);
  println(c.value);
  return 0;
}
""",
     """first: positive
second: under ten
5
""",
     ""),
    ("guard_false in a caller chain",
     r"""import "guard.fg";
fn checked(x: int) -> Result<int, str> {
  let _g: int = guard_false(x == 0, "x must not be zero")?;
  let _h: int = guard_positive(x, "x must be positive")?;
  return Result { ok: true, value: x + 1, error: "" };
}
fn main() -> int {
  let a: Result<int, str> = checked(0);
  println(a.error);
  let b: Result<int, str> = checked(0 - 2);
  println(b.error);
  let c: Result<int, str> = checked(9);
  println(c.value);
  return 0;
}
""",
     """x must not be zero
x must be positive
10
""",
     ""),
    ("guard_positive value flows through ?",
     r"""import "guard.fg";
fn half(x: int) -> Result<int, str> {
  let n: int = guard_positive(x, "need positive")?;
  return Result { ok: true, value: n / 2, error: "" };
}
fn main() -> int {
  let a: Result<int, str> = half(10);
  println(a.value);
  let b: Result<int, str> = half(0);
  println(b.ok);
  println(b.error);
  return 0;
}
""",
     """5
false
need positive
""",
     ""),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_STACK,
                           (65536 * 1024, resource.RLIM_INFINITY))
    except Exception:
        pass
    with tempfile.TemporaryDirectory() as td:
        _run_all(td, failures)
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


def _run_all(td, failures):
    demo = os.path.join(ROOT, "examples", "guard_demo.fg")
    lib = os.path.join(ROOT, "forge_lang", "stdlib", "guard.fg")
    for mode, prefix in (("hosted", []), ("python", ["--python"])):
        r = run([sys.executable, os.path.join(ROOT, "forge.py")] + prefix +
                ["run", demo], ROOT)
        if not check(f"demo runs ({mode})", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append(f"demo runs ({mode})")
        elif not check(f"demo results ({mode})", r.stdout == DEMO_EXPECTED,
                       repr(r.stdout)):
            failures.append(f"demo results ({mode})")
    for name, prog, want, needle in OK_CASES:
        p = os.path.join(td, "c.fg")
        with open(p, "w") as f:
            f.write(prog)
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                     prefix + ["run", p], ROOT)
            ok = (rr.returncode == 0 and rr.stdout == want and
                  (not needle or needle in rr.stderr))
            if not check(f"{name} ({mode})", ok,
                         repr(rr.stdout) + (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(f"{name} ({mode})")
    # fmt strips // comments, so the lib (which keeps its header) is
    # not fmt-run here — demo only, same as test_errrender_v1.py.
    for target in (demo,):
        rf = run([sys.executable, os.path.join(ROOT, "forge.py"), "fmt", target],
                 ROOT)
        if not check(f"fmt runs ({os.path.basename(target)})",
                     rf.returncode == 0, rf.stderr.strip()):
            failures.append(f"fmt runs ({target})")
        else:
            rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"),
                       "fmt", "--check", target], ROOT)
            if not check(f"fmt idempotent ({os.path.basename(target)})",
                         rf2.returncode == 0, rf2.stderr.strip()):
                failures.append(f"fmt idempotent ({target})")


if __name__ == "__main__":
    sys.exit(main())
