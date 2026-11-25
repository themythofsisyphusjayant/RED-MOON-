"""Top-500 #494: shadowing (tests/test_shadowing_v1.py).

`let x: int = 1; let x: int = x + 1;` — same-scope shadowing:
the RHS still reads the OLD binding and the new binding takes
over from here. Same type only in v1 (the C variable keeps its
declared type); a different type is rejected with a named error.
The old value is dropped at the rebind point (the Assign path:
temp-first, free the old value, take the new one), so owned
values (str, arrays, structs) neither leak nor double-free.

Shapes covered in BOTH compilers:
- int / str / array / struct rebinds, chained rebinds, rebind
  inside a loop body and inside a nested block (fresh shadow
  there — the outer value survives), rebind of a `let mut`,
  rebind to immutable after `let mut`, annotation equal to the
  old type, empty-array-literal rebind (takes the old type).
- Errors (same message in both compilers): type change,
  shadowing a pinned variable.
- A `let` with a loop variable's name inside a `for` body keeps
  the OLD duplicate error in the Python compiler (the C
  initializer would read the new variable, not the loop var).

Known limits / divergences (NOT asserted here, documented):
- A nested-block shadow whose RHS reads the shadowed name
  (`{ let x = x + 1; }`) miscompiles in BOTH compilers today
  (C scoping: the initializer reads the new variable itself —
  prints garbage instead of the incremented value). Pre-existing,
  needs its own slice (temp-first evaluation for shadowing lets).
- The hosted checker ACCEPTS a loop-var shadow (its loop var is
  declared before the body's scope mark) while Python rejects
  it — the same C trap, pre-existing divergence.
- Type-changing shadowing (`let x: int` then `let x: str`) is
  rejected in v1; declare it in a nested block instead.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# (name, program, expected stdout).
OK_CASES = [
    ("1 int rebind reads old value",
     r"""fn main() -> int {
  let x: int = 1;
  let x: int = x + 1;
  println(x);
  return 0;
}
""",
     "2\n"),
    ("2 chained int rebinds",
     r"""fn main() -> int {
  let x: int = 1;
  let x: int = x + 1;
  let x = x * 10;
  println(x);
  return 0;
}
""",
     "20\n"),
    ("3 str rebind",
     r"""fn main() -> int {
  let s: str = "a";
  let s: str = s + "b";
  println(s);
  return 0;
}
""",
     "ab\n"),
    ("4 array rebind",
     r"""fn main() -> int {
  let xs: [int] = [1, 2];
  let xs: [int] = [3, 4, 5];
  println(xs[2]);
  return 0;
}
""",
     "5\n"),
    ("5 struct rebind",
     r"""struct Point {
  x: int,
  y: int,
}
fn main() -> int {
  let p: Point = Point { x: 1, y: 2 };
  let p: Point = Point { x: 5, y: 6 };
  println(p.x + p.y);
  return 0;
}
""",
     "11\n"),
    ("6 rebind inside a loop body",
     r"""fn main() -> int {
  let mut total: int = 0;
  let mut i: int = 0;
  while i < 3 {
    let v: int = i;
    let v: int = v + 100;
    total = total + v;
    i = i + 1;
  }
  println(total);
  return 0;
}
""",
     "303\n"),
    ("7 nested-block shadow leaves the outer value alone",
     r"""fn main() -> int {
  let x: int = 1;
  {
    let x: int = 2;
    println(x);
  }
  println(x);
  return 0;
}
""",
     "2\n1\n"),
    ("8 rebind of a let mut, then to immutable",
     r"""fn main() -> int {
  let mut x: int = 1;
  let x: int = x + 1;
  println(x);
  return 0;
}
""",
     "2\n"),
    ("9 rebind with matching annotation",
     r"""fn main() -> int {
  let x: int = 1;
  let x: int = x + 1;
  println(x);
  return 0;
}
""",
     "2\n"),
    ("10 annotated empty-array-literal rebind",
     r"""fn main() -> int {
  let xs: [int] = [1, 2];
  let xs: [int] = [];
  println(len(xs));
  return 0;
}
""",
     "0\n"),
    ("11 rebind inside an if branch",
     r"""fn main() -> int {
  let x: int = 1;
  if true {
    let y: int = 10;
    let y: int = y + 5;
    println(y);
  }
  println(x);
  return 0;
}
""",
     "15\n1\n"),
    ("12 rebind of a moved-then-revived str",
     r"""fn f(s: str) -> str {
  return s;
}
fn main() -> int {
  let s: str = "a";
  let s: str = f(s);
  println(s);
  return 0;
}
""",
     "a\n"),
]

# (name, program, error fragment in stderr — same in both compilers).
ERR_CASES = [
    ("E1 type-changing shadow",
     r"""fn main() -> int {
  let x: int = 1;
  let x: str = "a";
  println(x);
  return 0;
}
""",
     "cannot shadow 'x' with a different type in v1 (was int, now str)"),
    ("E2 type-changing shadow, annotated the other way",
     r"""fn main() -> int {
  let x: str = "a";
  let x: int = 1;
  println(x);
  return 0;
}
""",
     "cannot shadow 'x' with a different type in v1 (was str, now int)"),
    ("E3 shadowing a pinned variable",
     r"""fn main() -> int {
  let mut s: str = "a";
  pin(s);
  let s: str = "b";
  println(s);
  return 0;
}
""",
     "cannot shadow pinned variable 's'"),
    ("E4 empty-literal rebind without an annotation",
     r"""fn main() -> int {
  let xs: [int] = [1, 2];
  let xs = [];
  println(len(xs));
  return 0;
}
""",
     "cannot infer the element type of an empty array literal; add an annotation"),
]

# Python-only errors (pre-existing hosted divergence: the hosted
# checker accepts a loop-var shadow; see module docstring).
PY_ONLY_ERR_CASES = [
    ("E4 loop-var shadow keeps the duplicate error (python only)",
     r"""fn main() -> int {
  for i in 0..3 {
    let i: int = i + 10;
    println(i);
  }
  return 0;
}
""",
     "variable 'i' is already defined in this scope"),
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
    total = 0
    with tempfile.TemporaryDirectory() as td:
        for name, prog, want in OK_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                total += 1
                rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                         prefix + ["run", p], ROOT)
                if not check(f"{name} ({mode})", rr.returncode == 0 and rr.stdout == want,
                             f"rc={rr.returncode} out={rr.stdout!r} err={rr.stderr[:200]!r}"):
                    failures.append(f"{name} ({mode})")
        for name, prog, frag in ERR_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                total += 1
                rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                         prefix + ["run", p], ROOT)
                ok = rr.returncode != 0 and frag in rr.stderr
                if not check(f"{name} ({mode})", ok,
                             f"rc={rr.returncode} err={rr.stderr[:200]!r}"):
                    failures.append(f"{name} ({mode})")
        for name, prog, frag in PY_ONLY_ERR_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            total += 1
            rr = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python", "run", p], ROOT)
            ok = rr.returncode != 0 and frag in rr.stderr
            if not check(f"{name} (python)", ok,
                         f"rc={rr.returncode} err={rr.stderr[:200]!r}"):
                failures.append(f"{name} (python)")
    # fmt idempotent on the demo.
    demo = os.path.join(ROOT, "examples", "shadowing_demo.fg")
    total += 1
    rr = run([sys.executable, os.path.join(ROOT, "forge.py"), "fmt", "--check", demo], ROOT)
    if not check("fmt demo idempotent", rr.returncode == 0,
                 f"rc={rr.returncode} out={rr.stdout[:200]!r} err={rr.stderr[:200]!r}"):
        failures.append("fmt demo idempotent")
    print(f"TOTAL: {total - len(failures)}/{total} checks passed")
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
