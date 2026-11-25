"""Top-500 #490: trailing commas (tests/test_trailing_commas_v1.py).

`[1, 2, 3,]`, `foo(1, 2,)`, `Point { x: 1, y: 2, }`, `(1, "a",)`,
`fn add(a: int, b: int,)`, tuple/fn/generic types with a trailing
comma, method calls and indirect calls — all parse and run in BOTH
compilers. Enum/struct declarations and match arms already accepted
an optional trailing separator (loop-until-`}` shape); they are
covered here as regressions.

Edges (both compilers reject, same message class):
- `[1, 2,, 3]` and `foo(1,, 2)` — a double comma still errors
  ("expected an expression").
- `foo(,)` — a leading comma still errors.
- `(1,)` — a 1-tuple literal is rejected with the clear message
  "tuple literals need at least two elements" (tuples need >= 2
  elements, per forge_lang/tuples.py; without the guard the program
  fell through to a confusing checker message).

fmt normalises trailing commas away: the demo is canonical (no
trailing commas, fmt --check green) and a trailing-comma file
formats to exactly the canonical file.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# (name, program, expected stdout).
OK_CASES = [
    ("1 array literal trailing comma",
     r"""fn main() -> int {
  let xs: [int] = [1, 2, 3,];
  println(xs[2]);
  return 0;
}
""",
     "3\n"),
    ("2 call args trailing comma",
     r"""fn add(a: int, b: int) -> int {
  return a + b;
}
fn main() -> int {
  println(add(1, 2,));
  return 0;
}
""",
     "3\n"),
    ("3 struct literal trailing comma",
     r"""struct Point {
  x: int,
  y: int,
}
fn main() -> int {
  let p: Point = Point { x: 1, y: 2, };
  println(p.x + p.y);
  return 0;
}
""",
     "3\n"),
    ("4 tuple literal trailing comma",
     r"""fn main() -> int {
  let t: (int, str,) = (1, "a",);
  println(t.0);
  return 0;
}
""",
     "1\n"),
    ("5 fn params trailing comma",
     r"""fn add(a: int, b: int,) -> int {
  return a + b;
}
fn main() -> int {
  println(add(3, 4,));
  return 0;
}
""",
     "7\n"),
    ("6 fn type + lambda params trailing comma",
     r"""fn main() -> int {
  let f: fn(int, int,) -> int = fn(a: int, b: int,) -> int {
    return a * b;
  };
  println(f(3, 4,));
  return 0;
}
""",
     "12\n"),
    ("7 generic type args trailing comma",
     r"""fn main() -> int {
  let xs: [int] = [5,];
  println(xs[0]);
  return 0;
}
""",
     "5\n"),
    ("8 method call trailing comma",
     r"""struct Point {
  x: int,
  y: int,
}
impl Point {
  fn add(self: Point, n: int) -> int {
    return self.x + self.y + n;
  }
}
fn main() -> int {
  let p: Point = Point { x: 3, y: 4, };
  println(p.add(5,));
  return 0;
}
""",
     "12\n"),
    ("9 nested trailing commas",
     r"""fn add(a: int, b: int) -> int {
  return a + b;
}
fn main() -> int {
  let xs: [int] = [add(1, 2,), add(3, 4,),];
  println(xs[0] + xs[1]);
  return 0;
}
""",
     "10\n"),
    ("10 enum + struct decl trailing commas (regression)",
     r"""enum Color { Red, Green, Blue, }
struct Point {
  x: int,
  y: int,
}
fn main() -> int {
  let c: Color = Green;
  match c {
    Red => {
      println(1);
    }
    Green => {
      println(2);
    }
    _ => {
      println(3);
    }
  }
  let p: Point = Point { x: 1, y: 2, };
  println(p.x);
  return 0;
}
""",
     "2\n1\n"),
]

# (name, program, error fragment in stderr — same in both compilers).
ERR_CASES = [
    ("E1 double comma in array literal",
     r"""fn main() -> int {
  let xs: [int] = [1, 2,, 3];
  println(xs[0]);
  return 0;
}
""",
     "expected an expression"),
    ("E2 double comma in call args",
     r"""fn add(a: int, b: int) -> int {
  return a + b;
}
fn main() -> int {
  println(add(1,, 2));
  return 0;
}
""",
     "expected an expression"),
    ("E3 leading comma in call args",
     r"""fn foo(a: int) -> int {
  return a;
}
fn main() -> int {
  println(foo(,));
  return 0;
}
""",
     "expected an expression"),
    ("E4 one-element tuple literal",
     r"""fn main() -> int {
  let t = (1,);
  println(t.0);
  return 0;
}
""",
     "tuple literals need at least two elements"),
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
        # fmt normalises trailing commas away: format a canonical
        # 4-space program that carries one trailing comma and
        # compare against the same text without it.
        src = os.path.join(td, "fmt_in.fg")
        with open(src, "w") as f:
            f.write("fn add(a: int, b: int) -> int {\n"
                    "    return a + b;\n"
                    "}\n"
                    "fn main() -> int {\n"
                    "    println(add(1, 2,));\n"
                    "    return 0;\n"
                    "}\n")
        rr = run([sys.executable, os.path.join(ROOT, "forge.py"), "fmt", src], ROOT)
        total += 1
        got = open(src).read()
        want_fmt = ("fn add(a: int, b: int) -> int {\n"
                    "    return a + b;\n"
                    "}\n"
                    "\n"
                    "fn main() -> int {\n"
                    "    println(add(1, 2));\n"
                    "    return 0;\n"
                    "}\n")
        if not check("fmt strips trailing comma", rr.returncode == 0 and got == want_fmt,
                     f"rc={rr.returncode} got={got!r}"):
            failures.append("fmt strips trailing comma")
    # fmt idempotent on the demo.
    demo = os.path.join(ROOT, "examples", "trailing_commas_demo.fg")
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
