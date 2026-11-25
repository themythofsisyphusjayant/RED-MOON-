"""Top-500 #496: underscore for unused bindings (tests/test_underscore_unused_v1.py).

`let _unused: int = 5;` — the `_` prefix marks a binding as
deliberately unused. Probes on 25 Nov 2026 showed this is already
satisfied, and the catalog entry was stale at [GAP]:

- `_`-prefixed bindings compile and run in BOTH compilers, read
  or unread, in nested scopes, as fn parameters, and as multiple
  unused bindings in one function.
- There is NO unused-variable warning to silence in either
  compiler: zero occurrences of "warning" in forge_lang/checker.py
  and examples/selfhost_check.fg, and a plain unused non-underscore
  `let unused: int = 5;` also compiles and runs clean with no
  warning text on stderr. So the observable requirement of #496 —
  `_` bindings never produce a complaint — holds, vacuously for
  the silencing half and directly for the acceptance half.

Both compilers (Python + hosted) for every case. fmt idempotent
on the demo.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# (name, program, expected stdout).
OK_CASES = [
    ("1 unused _-prefixed let",
     r"""fn main() -> int {
  let _unused: int = 5;
  println(1);
  return 0;
}
""",
     "1\n"),
    ("2 _-prefixed let read back",
     r"""fn main() -> int {
  let _x: int = 3;
  println(_x);
  return 0;
}
""",
     "3\n"),
    ("3 several unused _-prefixed lets",
     r"""fn main() -> int {
  let _a: int = 1;
  let _b: str = "hi";
  let _c: bool = true;
  println(7);
  return 0;
}
""",
     "7\n"),
    ("4 _-prefixed let in a nested scope",
     r"""fn main() -> int {
  let x: int = 1;
  {
    let _tmp: int = x + 1;
    println(x);
  }
  println(x);
  return 0;
}
""",
     "1\n1\n"),
    ("5 _-prefixed fn parameter unused",
     r"""fn f(_p: int, q: int) -> int {
  return q;
}
fn main() -> int {
  println(f(1, 2));
  return 0;
}
""",
     "2\n"),
    ("6 plain unused let also warns nothing",
     r"""fn main() -> int {
  let unused: int = 5;
  println(1);
  return 0;
}
""",
     "1\n"),
    ("7 _-prefixed let in a loop body",
     r"""fn main() -> int {
  let mut total: int = 0;
  let mut i: int = 0;
  while i < 3 {
    let _step: int = i * 10;
    total = total + i;
    i = i + 1;
  }
  println(total);
  return 0;
}
""",
     "3\n"),
]


def run(args, cwd, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    # The #50 slice found forge.py honors ambient
    # QASIDA_COMPILER; scrub it so "hosted" runs are hosted.
    e.pop("QASIDA_COMPILER", None)
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=e)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    with tempfile.TemporaryDirectory() as td:
        for name, prog, want in OK_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                         prefix + ["run", p], ROOT)
                ok = (rr.returncode == 0 and rr.stdout == want
                      and "unused" not in rr.stderr.lower()
                      and "warning" not in rr.stderr.lower())
                if not check(f"{name} ({mode})", ok,
                             f"rc={rr.returncode} out={rr.stdout!r} err={rr.stderr[:200]!r}"):
                    failures.append(f"{name} ({mode})")
    # fmt idempotent on the demo.
    demo = os.path.join(ROOT, "examples", "underscore_demo.fg")
    rr = run([sys.executable, os.path.join(ROOT, "forge.py"), "fmt", "--check", demo], ROOT)
    if not check("fmt demo idempotent", rr.returncode == 0,
                 f"rc={rr.returncode} out={rr.stdout[:200]!r} err={rr.stderr[:200]!r}"):
        failures.append("fmt demo idempotent")
    print(f"TOTAL: {len(OK_CASES) * 2 + 1 - len(failures)}/{len(OK_CASES) * 2 + 1} checks passed")
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
