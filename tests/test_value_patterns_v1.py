"""Top-500 #69: value patterns in match (tests/test_value_patterns_v1.py).

`match x { 2 => { ... } "hi" => { ... } Point { x: 0, y: n } => { ... }
_ => { ... } }` — value patterns in match (Scala shape), landed
25 Nov 2026 (Sprint Day 5). v1 patterns: int literals (incl.
negative, explicit `-` in the grammar), bool literals, string
literals (content equality via `==` / strcmp), and struct patterns
`Point { x: 0, y: n }` (field-wise literal / binding / `_`; all
fields present; field bindings scoped to the arm with the field's
type). OUT of v1: float literals, range patterns, tuple/array
patterns, type patterns, `|` alternation, guards (`pat if cond =>`
is a parse error), bare-variable catch-all (`n => ...` — a bare
identifier still means an enum variant).

Exhaustiveness is a compile error: `_` required for int/string/
struct matches; bool exhaustive iff {true, false} seen or `_`
present. Value matches skip the #50 ES verdict entirely. First-
match-wins, top to bottom; exact duplicate literal / duplicate
struct pattern = compile error; subsumption NOT analysed in v1
(the second arm simply never runs — the first-match-wins case
below documents it). No runtime fallthrough: the checker
guarantee makes it unreachable by construction.

The p10 temp-hoist: value patterns use a temp-based lowering
(scrutinee evaluated once into __forge_match{n}); the same
one-temp hoist is folded into the plain-enum shape, so a
side-effecting enum scrutinee also runs once (the p10 case below
asserts the new behaviour under both compilers).

Two message divergences, NOT #69 gaps (both compilers reject
the program; only the spelling differs):
- Missing-fields: Python says "is missing fields: y" while the
  hosted checker says "is missing field 'y'". The test asserts
  the common fragment "is missing field".
- The hosted checker validates a struct pattern's field literals
  against the field types via the same recursive rule; both agree
  on the "does not match scrutinee of type" message.

Both compilers (Python + hosted) for the native cases. big32/wasm
cases run under the Python compiler only: the hosted driver defers
emit-big32/emit-wasm and routes them to the same backends
(byte-identical emit). big32 lowers int/bool value patterns; it
rejects string/struct patterns with a named error. WASM has no
match support at all (unchanged).
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MODEL_DIR = os.path.expanduser("~/workspace/big32/tools")

# (name, program, expected stdout).
OK_CASES = [
    ("1 int literal hit",
     r"""fn main() -> int {
  let x: int = 2;
  match x {
    2 => {
      println("two");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "two\n"),
    ("2 int literal miss to wildcard",
     r"""fn main() -> int {
  let x: int = 3;
  match x {
    2 => {
      println("two");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "other\n"),
    ("3 negative int literal",
     r"""fn main() -> int {
  let x: int = -1;
  match x {
    -1 => {
      println("neg one");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "neg one\n"),
    ("4 bool exhaustive without wildcard",
     r"""fn main() -> int {
  let b: bool = false;
  match b {
    true => {
      println("yes");
    }
    false => {
      println("no");
    }
  }
  return 0;
}
""",
     "no\n"),
    ("5 string literal hit",
     r"""fn main() -> int {
  let s: str = "hello";
  match s {
    "hello" => {
      println("hello");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "hello\n"),
    ("6 string literal miss to wildcard",
     r"""fn main() -> int {
  let s: str = "bye";
  match s {
    "hello" => {
      println("hello");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "other\n"),
    ("7 string with escape in the pattern",
     r"""fn main() -> int {
  let s: str = "a\nb";
  match s {
    "a\nb" => {
      println("escaped");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "escaped\n"),
    ("8 struct pattern literal-fields hit",
     r"""struct Point { x: int, y: int }
fn main() -> int {
  let p: Point = Point { x: 0, y: 0 };
  match p {
    Point { x: 0, y: 0 } => {
      println("origin");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "origin\n"),
    ("9 struct pattern with a field binding",
     r"""struct Point { x: int, y: int }
fn main() -> int {
  let p: Point = Point { x: 0, y: 7 };
  match p {
    Point { x: 0, y: n } => {
      println(n);
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "7\n"),
    ("10 struct pattern with a _ field",
     r"""struct Point { x: int, y: int }
fn main() -> int {
  let p: Point = Point { x: 5, y: 0 };
  match p {
    Point { x: _, y: 0 } => {
      println("y0");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "y0\n"),
    ("11 side-effecting scrutinee evaluated once (p10)",
     r"""fn next() -> int {
  println("called");
  return 2;
}
fn main() -> int {
  match next() {
    2 => {
      println("two");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "called\ntwo\n"),
    ("12 first-match-wins with overlapping arms",
     r"""struct Point { x: int, y: int }
fn main() -> int {
  let p: Point = Point { x: 0, y: 1 };
  match p {
    Point { x: 0, y: _ } => {
      println("general");
    }
    Point { x: 0, y: 1 } => {
      println("specific");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     # Subsumption is NOT analysed in v1: the first arm wins and
     # the second never runs. Documented in DESIGN.md §3 (Q5).
     "general\n"),
    ("13 int match inside a function returning a value",
     r"""fn describe(x: int) -> str {
  let mut s: str = "";
  match x {
    0 => {
      s = "zero";
    }
    _ => {
      s = "nonzero";
    }
  }
  return s;
}
fn main() -> int {
  println(describe(0));
  println(describe(5));
  return 0;
}
""",
     "zero\nnonzero\n"),
    ("14 nested match (value match inside an enum arm body)",
     r"""enum Color { Red, Green }
fn main() -> int {
  let c: Color = Red;
  let x: int = 2;
  match c {
    Red => {
      match x {
        2 => {
          println("red two");
        }
        _ => {
          println("red other");
        }
      }
    }
    Green => {
      println("green");
    }
  }
  return 0;
}
""",
     "red two\n"),
    ("15 i64 max literal hit",
     r"""fn main() -> int {
  let x: int = 9223372036854775807;
  match x {
    9223372036854775807 => {
      println("max");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "max\n"),
    ("16 i64 min literal hit",
     r"""fn main() -> int {
  let x: int = -9223372036854775808;
  match x {
    -9223372036854775808 => {
      println("min");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "min\n"),
    ("17 hex int literal hit",
     r"""fn main() -> int {
  let x: int = 42;
  match x {
    0x2A => {
      println("hex");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "hex\n"),
]

# (name, program, error fragment in stderr).
ERR_CASES = [
    ("E1 int literal in a str match",
     r"""fn main() -> int {
  let s: str = "hi";
  match s {
    5 => {
      println("five");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "int pattern '5' does not match scrutinee of type str"),
    ("E2 string literal in an int match",
     r"""fn main() -> int {
  let x: int = 2;
  match x {
    "hi" => {
      println("hi");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "string pattern does not match scrutinee of type int"),
    ("E3 int match without _",
     r"""fn main() -> int {
  let x: int = 2;
  match x {
    2 => {
      println("two");
    }
  }
  return 0;
}
""",
     "match on int is not exhaustive; a '_' arm is required"),
    ("E4 string match without _",
     r"""fn main() -> int {
  let s: str = "hi";
  match s {
    "hi" => {
      println("hi");
    }
  }
  return 0;
}
""",
     "match on str is not exhaustive; a '_' arm is required"),
    ("E5 bool match with only true and no _",
     r"""fn main() -> int {
  let b: bool = true;
  match b {
    true => {
      println("yes");
    }
  }
  return 0;
}
""",
     "match on bool is not exhaustive; a '_' arm is required"),
    ("E6 duplicate int literal",
     r"""fn main() -> int {
  let x: int = 2;
  match x {
    2 => {
      println("two");
    }
    2 => {
      println("two again");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "duplicate match arm '2'"),
    ("E7 duplicate string literal",
     r"""fn main() -> int {
  let s: str = "hi";
  match s {
    "hi" => {
      println("hi");
    }
    "hi" => {
      println("hi again");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "duplicate match arm '\"hi\"'"),
    ("E8 struct pattern naming the wrong struct",
     r"""struct Point { x: int, y: int }
struct Other { x: int, y: int }
fn main() -> int {
  let p: Point = Point { x: 0, y: 0 };
  match p {
    Other { x: 0, y: 0 } => {
      println("other");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "struct pattern 'Other' does not match scrutinee of type Point"),
    ("E9 struct pattern with an unknown field",
     r"""struct Point { x: int, y: int }
fn main() -> int {
  let p: Point = Point { x: 0, y: 0 };
  match p {
    Point { x: 0, y: 0, z: 0 } => {
      println("z");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "struct 'Point' has no field 'z'"),
    ("E10 struct pattern missing a field",
     r"""struct Point { x: int, y: int }
fn main() -> int {
  let p: Point = Point { x: 0, y: 0 };
  match p {
    Point { x: 0 } => {
      println("x0");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     # Python: "is missing fields: y"; hosted: "is missing
     # field 'y'". Common fragment asserted for both.
     "is missing field"),
    ("E11 struct pattern with a wrong-typed field literal",
     r"""struct Point { x: int, y: int }
fn main() -> int {
  let p: Point = Point { x: 0, y: 0 };
  match p {
    Point { x: "hi", y: 0 } => {
      println("xhi");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "string pattern does not match scrutinee of type int"),
    ("E12 float literal pattern (parse error)",
     r"""fn main() -> int {
  let x: int = 2;
  match x {
    1.5 => {
      println("one point five");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "float literal patterns are not supported in v1"),
    ("E13 guard syntax (parse error)",
     r"""enum Color { Red, Green }
fn main() -> int {
  let c: Color = Red;
  match c {
    Red if true => {
      println("red");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "expected '=>', got 'if'"),
    ("E14 match on a float scrutinee",
     r"""fn main() -> int {
  let f: float = 1.5;
  match f {
    1 => {
      println("one");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "match needs an enum, union, int, bool, str, or struct value, got float"),
    ("E15 match on an array scrutinee",
     r"""fn main() -> int {
  let a: [int] = [1, 2];
  match a {
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "match needs an enum, union, int, bool, str, or struct value, got [int]"),
    ("E16 i64 max+1 pattern does not fit",
     r"""fn main() -> int {
  let x: int = 2;
  match x {
    9223372036854775808 => {
      println("maxplus");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "does not fit in i64"),
    ("E17 i64 min-1 pattern does not fit",
     r"""fn main() -> int {
  let x: int = 2;
  match x {
    -9223372036854775809 => {
      println("minminus");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "does not fit in i64"),
    ("E18 hex overflow pattern does not fit",
     r"""fn main() -> int {
  let x: int = 2;
  match x {
    0x8000000000000000 => {
      println("hexmaxplus");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "does not fit in i64"),
]

# big32: (name, program, expected UART). Python compiler only.
BIG32_CASES = [
    ("big32 int-literal match hit",
     r"""fn main() -> int {
  let x: int = 2;
  match x {
    2 => {
      println("two");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     b"two\n"),
    ("big32 int-literal match miss to wildcard",
     r"""fn main() -> int {
  let x: int = 3;
  match x {
    2 => {
      println("two");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     b"other\n"),
]

# big32 rejections (named errors, Python compiler only).
BIG32_STR_PROG = r"""fn main() -> int {
  let s: str = "hi";
  match s {
    "hi" => {
      println("hi");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
"""
BIG32_STRUCT_PROG = r"""struct Point { x: int, y: int }
fn main() -> int {
  let p: Point = Point { x: 0, y: 0 };
  match p {
    Point { x: 0, y: 0 } => {
      println("origin");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
"""
WASM_MATCH_PROG = r"""fn main() -> int {
  let x: int = 2;
  match x {
    2 => {
      println("two");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
"""


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
                # The Step-6 cache serves C WITHOUT re-running the
                # checker (#50) — clear before every emit so a
                # rejection is really a rejection.
                import shutil
                shutil.rmtree("/tmp/qasida_cache", ignore_errors=True)
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
                import shutil
                shutil.rmtree("/tmp/qasida_cache", ignore_errors=True)
                rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                         prefix + ["run", p], ROOT)
                ok = rr.returncode != 0 and frag in rr.stderr
                if not check(f"{name} ({mode})", ok,
                             f"rc={rr.returncode} err={rr.stderr[:200]!r}"):
                    failures.append(f"{name} ({mode})")
        # big32 (Python compiler only): build, run under the model.
        sys.path.insert(0, MODEL_DIR)
        import model as big32_model
        for name, prog, uart in BIG32_CASES:
            p = os.path.join(td, "b.fg")
            with open(p, "w") as f:
                f.write(prog)
            hexpath = os.path.join(td, "b.hex")
            import shutil
            shutil.rmtree("/tmp/qasida_cache", ignore_errors=True)
            rb = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                      "build", p, "--target", "big32", "-o", os.path.join(td, "b")],
                     ROOT)
            if rb.returncode != 0:
                check(name, False, f"build rc={rb.returncode} err={rb.stderr[:200]!r}")
                failures.append(f"{name} builds")
                continue
            res = big32_model.run(hexpath)
            ok = res.get("uart", b"") == uart and res.get("halted") and res.get("a0") == 0
            if not check(name, ok, f"uart={res.get('uart', b'')!r} halted={res.get('halted')} a0={res.get('a0')}"):
                failures.append(name)
        # big32 rejects string patterns (named error).
        p = os.path.join(td, "bs.fg")
        with open(p, "w") as f:
            f.write(BIG32_STR_PROG)
        import shutil
        shutil.rmtree("/tmp/qasida_cache", ignore_errors=True)
        rs = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                  "build", p, "--target", "big32", "-o", os.path.join(td, "bs")],
                 ROOT)
        if not check("big32 string pattern rejected",
                     rs.returncode != 0 and "match on str is not supported on big32 (v1)" in rs.stderr,
                     f"rc={rs.returncode} err={rs.stderr[:200]!r}"):
            failures.append("big32 string pattern rejected")
        # big32 rejects struct patterns (named error).
        p = os.path.join(td, "bt.fg")
        with open(p, "w") as f:
            f.write(BIG32_STRUCT_PROG)
        shutil.rmtree("/tmp/qasida_cache", ignore_errors=True)
        rt = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                  "build", p, "--target", "big32", "-o", os.path.join(td, "bt")],
                 ROOT)
        if not check("big32 struct pattern rejected",
                     rt.returncode != 0 and "match on Point is not supported on big32 (v1)" in rt.stderr,
                     f"rc={rt.returncode} err={rt.stderr[:200]!r}"):
            failures.append("big32 struct pattern rejected")
        # WASM has no match support (unchanged).
        p = os.path.join(td, "w.fg")
        with open(p, "w") as f:
            f.write(WASM_MATCH_PROG)
        shutil.rmtree("/tmp/qasida_cache", ignore_errors=True)
        rw = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                  "emit-wasm", p, "-o", os.path.join(td, "w.wasm")], ROOT)
        if not check("wasm rejects match", rw.returncode != 0,
                     f"rc={rw.returncode} err={rw.stderr[:200]!r}"):
            failures.append("wasm rejects match")
    if failures:
        print(f"FAILURES ({len(failures)}): {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
