"""Top-500 #72: assignment expressions (Python walrus) (tests/test_walrus_v1.py).

`name := expr` — bind a value inside a condition, landed 25 Nov 2026
(Sprint Day 5). The recommended bundle: F1 syntax `name := expr`
(new lexer token `:=` in TWO_CHAR — this also fixes the p3 label
collision, where `x:= 5;` was misread as a #62 label prefix); F2
scope/mutability — the binding is declared in the ENCLOSING BLOCK
as `let mut` (fresh name -> new mutable binding; existing `let mut`
same-type -> assign into it; existing immutable -> the Assign
error; NO #494 rebind); F3 targets — plain names only; F4 where
allowed — conditions ONLY (`if`/`while`) at hoistable positions
(whole condition, under `!`, under a comparison, under the LEFT
operand of `&&`/`||` — everything else a named error per DESIGN
section 3.5); F5 mechanism — checker-side desugar (the #70
precedent) with the v1 `continue` ban in walrus-`while` bodies.

The desugar: a walrus in an if/while condition becomes a binding
statement spliced before the statement (Let for a fresh name,
Assign for an existing one), the condition is rewritten with
Var(name), and a while gets its re-read appended to the body end.
The Python checker rewrites in `_check_stmts` (in place, so the
binding lands in the enclosing scope); the hosted checker cannot
rewrite in place (nodes are values), so its desugar is a
deterministic tree-rebuilding resolve pass (the #70 pattern),
run once in compile_to_c on the merged program and at
check_program entry, scope-aware via flat [str] names passed by
value (pass-by-copy gives lexical scoping for free) plus a loop
stack for the v1 `continue` ban. infer and all three codegens see
desugared code and need no change, so big32/WASM inherit walrus
free. `fmt` always parenthesises a walrus (load-bearing: `x :=
f() > 0` would re-parse as `x := (f() > 0)`).

v1 limits: conditions only; name targets only; no nested walrus;
no walrus under `&&`/`||` right; `continue` (labeled or not)
targeting a walrus-`while` is an error; the binding is always
`let mut`, lives in the enclosing block, dies at its end; `elif`
bindings die with the `else` block; a bare walrus condition needs
a `bool` RHS; `?` in a walrus RHS follows the existing `?` rules
(incl. the p15 hosted gap, out of scope); no walrus in
comprehensions (none exist).

Both compilers (Python + hosted) for the native cases. big32/wasm/
freestanding cases run under the Python compiler only: the hosted
driver defers emit-big32/emit-wasm and routes them to the same
backends (byte-identical emit). The fmt case runs under the Python
fmt (fmt is deferred in hosted). ASan program-side on every OK
program under both compilers lives in the separate gate script
asan_72.py in the slice dir (same shape as the #70 asan_70.py).
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MODEL_DIR = os.path.expanduser("~/workspace/big32/tools")

# (name, program, expected stdout, stdin).
OK_CASES = [
    ("1 if-walrus int comparison",
     r"""fn f() -> int {
  return 7;
}
fn main() -> int {
  if ((x := f()) > 5) {
    println(x);
  }
  println(x);
  return 0;
}
""",
     "7\n7\n", ""),
    ("2 if-walrus bare bool",
     r"""fn okb() -> bool {
  return true;
}
fn main() -> int {
  if (ok := okb()) {
    println("yes");
  }
  println(ok);
  return 0;
}
""",
     "yes\ntrue\n", ""),
    ("3 while-walrus countdown (p16 shape)",
     r"""fn main() -> int {
  let mut n: int = 3;
  while ((n := n - 1) >= 0) {
    println(n);
  }
  println("done");
  return 0;
}
""",
     "2\n1\n0\ndone\n", ""),
    ("4 while-walrus str != \"\" (read-line loop)",
     r"""fn main() -> int {
  while ((line := read_line()) != "") {
    println(line);
  }
  println("eof");
  return 0;
}
""",
     "a\nb\neof\n", "a\nb\n\n"),
    ("5 two walruses under one comparison, left-to-right",
     r"""fn main() -> int {
  if ((a := 3) < (b := 5)) {
    println(a);
    println(b);
  }
  println(a);
  println(b);
  return 0;
}
""",
     "3\n5\n3\n5\n", ""),
    ("6 walrus under !",
     r"""fn main() -> int {
  if !(done := false) {
    println("not done");
  }
  println(done);
  return 0;
}
""",
     "not done\nfalse\n", ""),
    ("7 walrus re-assigning an existing let mut",
     r"""fn main() -> int {
  let mut x: int = 1;
  if ((x := 9) > 5) {
    println(x);
  }
  println(x);
  return 0;
}
""",
     "9\n9\n", ""),
    ("8 walrus in an elif chain",
     r"""fn main() -> int {
  if ((v := 2) == 1) {
    println("one");
  } else if ((v := 3) == 3) {
    println("three");
  } else {
    println("other");
  }
  println(v);
  return 0;
}
""",
     "three\n3\n", ""),
    ("9 name visible after the if and in the else",
     r"""fn main() -> int {
  if ((x := 4) > 10) {
    println("big");
  } else {
    println(x);
  }
  println(x);
  return 0;
}
""",
     "4\n4\n", ""),
    ("10 walrus-bound str used after the if",
     r"""fn main() -> int {
  if ((s := "hello") != "") {
    println(s);
  }
  println(s);
  return 0;
}
""",
     "hello\nhello\n", ""),
    ("11 walrus in a function, bound value returned",
     r"""fn get() -> int {
  if ((v := 42) > 0) {
    return v;
  }
  return 0;
}
fn main() -> int {
  println(get());
  return 0;
}
""",
     "42\n", ""),
    ("12 walrus under && left",
     r"""fn main() -> int {
  if ((x := 7) > 5 && x < 10) {
    println(x);
  }
  println(x);
  return 0;
}
""",
     "7\n7\n", ""),
    ("13 walrus in a nested block, dies at its end",
     r"""fn main() -> int {
  let mut n: int = 3;
  {
    while ((n := n - 1) >= 0) {
      println(n);
    }
  }
  println(n);
  return 0;
}
""",
     # The condition is evaluated once more for the exit check,
     # so the re-read assigns n = -1 before the loop exits.
     "2\n1\n0\n-1\n", ""),
    ("14 while-walrus with break (break is allowed)",
     r"""fn main() -> int {
  let mut n: int = 10;
  while ((n := n - 1) >= 0) {
    if n == 7 {
      break;
    }
    println(n);
  }
  println("out");
  return 0;
}
""",
     "9\n8\nout\n", ""),
]

# (name, program, expected stderr fragment).
ERR_CASES = [
    ("E1 non-name target: field",
     r"""struct P { x: int }
fn main() -> int {
  let mut p: P = P { x: 0 };
  if ((p.x := 5) > 0) {
    println(p.x);
  }
  return 0;
}
""",
     "walrus target must be a plain name"),
    ("E2 non-name target: index",
     r"""fn main() -> int {
  let mut a: [int] = [1, 2];
  if ((a[0] := 5) > 0) {
    println(a[0]);
  }
  return 0;
}
""",
     "walrus target must be a plain name"),
    ("E3 walrus in a let initializer",
     r"""fn main() -> int {
  let y: int = (x := 5);
  println(y);
  return 0;
}
""",
     "walrus ':=' is only allowed in if/while conditions in v1"),
    ("E4 walrus in a call argument",
     r"""fn g(v: int) -> int {
  return v;
}
fn main() -> int {
  println(g((x := 5)));
  return 0;
}
""",
     "walrus ':=' is only allowed in if/while conditions in v1"),
    ("E5 walrus in a return",
     r"""fn main() -> int {
  return (x := 5);
}
""",
     "walrus ':=' is only allowed in if/while conditions in v1"),
    ("E6 bare-statement walrus",
     r"""fn main() -> int {
  x := 5;
  println(x);
  return 0;
}
""",
     "walrus cannot be used as a bare statement in v1"),
    ("E7 walrus under && right",
     r"""fn main() -> int {
  if (true && (x := 5) > 0) {
    println(x);
  }
  return 0;
}
""",
     "walrus cannot appear on the right of '&&' or '||' in v1"),
    ("E8 walrus under || right",
     r"""fn main() -> int {
  if (false || (x := 5) > 0) {
    println(x);
  }
  return 0;
}
""",
     "walrus cannot appear on the right of '&&' or '||' in v1"),
    ("E9 nested walrus",
     r"""fn main() -> int {
  if ((x := (y := 5)) > 0) {
    println(x);
  }
  return 0;
}
""",
     "walrus cannot appear inside another walrus in v1"),
    ("E10 walrus on an immutable name",
     r"""fn main() -> int {
  let x: int = 1;
  if ((x := 5) > 0) {
    println(x);
  }
  return 0;
}
""",
     "cannot assign to immutable variable 'x'"),
    ("E11 walrus type change on re-assign",
     r"""fn main() -> int {
  let mut x: int = 1;
  if ((x := "hi") != "") {
    println(x);
  }
  return 0;
}
""",
     "cannot assign str to int variable 'x'"),
    ("E12 continue in a walrus-while body",
     r"""fn main() -> int {
  let mut n: int = 0;
  while ((n := n + 1) < 3) {
    if n == 2 {
      continue;
    }
    println(n);
  }
  return 0;
}
""",
     "continue cannot target a while loop whose condition binds a walrus in v1"),
    ("E13 labeled continue targeting a walrus-while from a nested loop",
     r"""fn main() -> int {
  let mut n: int = 3;
  outer: while ((n := n - 1) >= 0) {
    let mut i: int = 0;
    while i < 2 {
      i = i + 1;
      continue outer;
    }
    println(n);
  }
  return 0;
}
""",
     "continue cannot target a while loop whose condition binds a walrus in v1"),
    ("E14 walrus in a match scrutinee",
     r"""fn main() -> int {
  match (w := 2) {
    1 => { println("one"); },
    2 => { println("two"); },
    _ => { println("other"); },
  }
  return 0;
}
""",
     "walrus ':=' is only allowed in if/while conditions in v1"),
    ("E15 walrus in a for source",
     r"""fn main() -> int {
  for i in (n := 3) {
    println(i);
  }
  return 0;
}
""",
     "walrus ':=' is only allowed in if/while conditions in v1"),
    ("E16 C-keyword target",
     r"""fn main() -> int {
  if ((short := 5) > 0) {
    println(short);
  }
  return 0;
}
""",
     "'short' is a C keyword and cannot be used as a variable name"),
]

# big32: a walrus program must build and print from the model.
BIG32_PROG = r"""fn main() -> int {
  let mut n: int = 3;
  while ((n := n - 1) >= 0) {
    println(n);
  }
  return 0;
}
"""

# WASM: a walrus program must build and run under node (the
# runner prints main's return value — wasm has no println).
WASM_PROG = r"""fn f() -> int {
  return 7;
}
fn main() -> int {
  if ((x := f()) > 5) {
    return x;
  }
  return 0;
}
"""

# Freestanding: a walrus program must build (crash dumps aside,
# the desugar is target-independent).
FREESTANDING_PROG = r"""fn main() -> int {
  if ((x := 7) > 5) {
    return x;
  }
  return 0;
}
"""

# fmt: the walrus stays parenthesised (load-bearing), spacing
# normalises, and a second fmt is a no-op.
FMT_PROG = "fn main() -> int {\n  if((x:=f())>0) {\n    println(x);\n  }\n  return 0;\n}\nfn f() -> int {\n  return 7;\n}\n"
FMT_WANT = "fn main() -> int {\n    if (x := f()) > 0 {\n        println(x);\n    }\n    return 0;\n}\n\nfn f() -> int {\n    return 7;\n}\n"


def run(args, cwd, env=None, stdin=""):
    e = dict(os.environ)
    if env:
        e.update(env)
    # The #50 slice found forge.py honors ambient
    # QASIDA_COMPILER; scrub it so "hosted" runs are hosted.
    e.pop("QASIDA_COMPILER", None)
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          env=e, input=stdin)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}", flush=True)
    return ok


def main():
    failures = []
    with tempfile.TemporaryDirectory() as td:
        for name, prog, want, stdin in OK_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                # The Step-6 cache serves C WITHOUT re-running the
                # checker (#50) — clear before every emit so a
                # rejection is really a rejection.
                shutil.rmtree("/tmp/qasida_cache", ignore_errors=True)
                rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                         prefix + ["run", p], ROOT, stdin=stdin)
                if not check(f"{name} ({mode})", rr.returncode == 0 and rr.stdout == want,
                             f"rc={rr.returncode} out={rr.stdout!r} err={rr.stderr[:200]!r}"):
                    failures.append(f"{name} ({mode})")
        for name, prog, frag in ERR_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                shutil.rmtree("/tmp/qasida_cache", ignore_errors=True)
                rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                         prefix + ["run", p], ROOT)
                ok = rr.returncode != 0 and frag in rr.stderr
                if not check(f"{name} ({mode})", ok,
                             f"rc={rr.returncode} err={rr.stderr[:200]!r}"):
                    failures.append(f"{name} ({mode})")
        # big32 (Python compiler only): a walrus program builds
        # and prints the countdown from the model.
        sys.path.insert(0, MODEL_DIR)
        import model as big32_model
        p = os.path.join(td, "b.fg")
        with open(p, "w") as f:
            f.write(BIG32_PROG)
        hexpath = os.path.join(td, "b.hex")
        shutil.rmtree("/tmp/qasida_cache", ignore_errors=True)
        rb = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                  "build", p, "--target", "big32", "-o", os.path.join(td, "b")],
                 ROOT)
        if rb.returncode != 0:
            check("big32 walrus program builds", False,
                  f"build rc={rb.returncode} err={rb.stderr[:200]!r}")
            failures.append("big32 walrus program builds")
        else:
            res = big32_model.run(hexpath)
            ok = res.get("uart", b"") == b"2\n1\n0\n" and res.get("halted") and res.get("a0") == 0
            if not check("big32 walrus program builds", ok,
                         f"uart={res.get('uart', b'')!r} halted={res.get('halted')} a0={res.get('a0')}"):
                failures.append("big32 walrus program builds")
        # wasm (Python compiler only): a walrus program builds
        # and runs under node (the runner prints main's return
        # value).
        p = os.path.join(td, "w.fg")
        with open(p, "w") as f:
            f.write(WASM_PROG)
        shutil.rmtree("/tmp/qasida_cache", ignore_errors=True)
        rw = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                  "build", p, "--target", "wasm", "-o", os.path.join(td, "w.wasm")], ROOT)
        if rw.returncode != 0:
            check("wasm walrus program builds", False,
                  f"build rc={rw.returncode} err={rw.stderr[:200]!r}")
            failures.append("wasm walrus program builds")
        else:
            rn = run(["node", os.path.join(ROOT, "tools", "run_wasm.mjs"),
                      os.path.join(td, "w.wasm")], ROOT)
            ok = rn.returncode == 0 and rn.stdout == "7\n"
            if not check("wasm walrus program runs under node", ok,
                         f"rc={rn.returncode} out={rn.stdout!r} err={rn.stderr[:200]!r}"):
                failures.append("wasm walrus program runs under node")
        # freestanding (Python compiler only): a walrus program
        # builds in freestanding mode.
        p = os.path.join(td, "fs.fg")
        with open(p, "w") as f:
            f.write(FREESTANDING_PROG)
        shutil.rmtree("/tmp/qasida_cache", ignore_errors=True)
        rf = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                  "build", p, "--freestanding", "-o", os.path.join(td, "fs")],
                 ROOT)
        if not check("freestanding walrus program builds",
                     rf.returncode == 0,
                     f"rc={rf.returncode} err={rf.stderr[:200]!r}"):
            failures.append("freestanding walrus program builds")
        # fmt keeps the walrus parenthesised (load-bearing),
        # normalises spacing, and is idempotent.
        p = os.path.join(td, "f.fg")
        with open(p, "w") as f:
            f.write(FMT_PROG)
        rf1 = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                   "fmt", p], ROOT)
        with open(p) as f:
            got = f.read()
        if not check("fmt keeps walrus parenthesised and normalises spacing",
                     rf1.returncode == 0 and got == FMT_WANT,
                     f"rc={rf1.returncode} got={got!r}"):
            failures.append("fmt keeps walrus parenthesised and normalises spacing")
        rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                   "fmt", p], ROOT)
        with open(p) as f:
            got2 = f.read()
        if not check("fmt idempotent on walrus",
                     rf2.returncode == 0 and got2 == FMT_WANT,
                     f"rc={rf2.returncode} got={got2!r}"):
            failures.append("fmt idempotent on walrus")
    if failures:
        print(f"FAILURES ({len(failures)}): {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
