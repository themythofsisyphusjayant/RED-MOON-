"""Top-500 #70: comptime if (tests/test_comptime_if_v1.py).

`comptime if <pred> { } else { }` — conditional compilation by
target, landed 25 Nov 2026 (Sprint Day 5). The recommended bundle:
F1 discarded branch SKIPPED (parsed only, never checked/compiled);
F2 syntax `comptime if` (statement, contextual keyword at statement
position, no lexer change); F3 function-body ONLY in v1 (a top-level
`comptime if` is an error); F4 FIXED predicate set only
(`target`/`arch`/`os`/`mode` valued, `debug`/`freestanding` bare,
combined with `&&`/`||`/`!` — no arbitrary expressions, no `feat=`);
F5 `qasida check` gains `--target {native,big32,wasm}` (default
native), all build paths thread their real target; F6 undecidable
impossible by construction — anything outside the fixed set is a
NAMED error listing allowed predicates (§4.5); F7 else-less
allowed; F8 nesting allowed both ways.

Resolution is a checker-side splice: the taken branch's statements
replace the ComptimeIf in place, in the SAME enclosing context —
a `let` in the taken branch is visible after the if, a spliced-in
`return`/`break` satisfies the enclosing checks. infer and all
three codegens see resolved code and need no change. The hosted
checker cannot rewrite the AST in place (nodes are values), so its
splice is a deterministic tree-rebuilding pass (the alias pattern):
resolved once in compile_to_c, shared by check/infer/codegen, and
at check_program entry; with no ComptimeIf the original node is
returned untouched.

v1 limits: function-body only; fixed predicates only; discarded
branch parsed but not checked (syntax errors there still fail);
no import gating; no comptime blocks/vars/params (#462 stays GAP);
no comptime switch; arch/os derive 1:1 from target; `check`
without --target evaluates native; hosted evaluates native only.

Both compilers (Python + hosted) for the native cases. big32/wasm
cases run under the Python compiler only: the hosted driver defers
emit-big32/emit-wasm and routes them to the same backends
(byte-identical emit). The fmt case runs under the Python fmt
(fmt is deferred in hosted).
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MODEL_DIR = os.path.expanduser("~/workspace/big32/tools")

# (name, program, expected stdout).
OK_CASES = [
    ("1 native-taken branch",
     r"""fn main() -> int {
  comptime if target == "native" {
    println("native");
  } else {
    println("other");
  }
  return 0;
}
""",
     "native\n"),
    ("2 big32-predicate else-branch",
     r"""fn main() -> int {
  comptime if target == "big32" {
    println("big32");
  } else {
    println("not big32");
  }
  return 0;
}
""",
     "not big32\n"),
    ("3 mode predicate (safe)",
     r"""fn main() -> int {
  comptime if mode == "safe" {
    println("safe");
  } else {
    println("fast");
  }
  return 0;
}
""",
     "safe\n"),
    ("4 negated debug predicate",
     r"""fn main() -> int {
  comptime if !debug {
    println("not debug");
  } else {
    println("debug");
  }
  return 0;
}
""",
     "not debug\n"),
    ("5 freestanding else-branch (hosted)",
     r"""fn main() -> int {
  comptime if freestanding {
    println("freestanding");
  } else {
    println("hosted");
  }
  return 0;
}
""",
     "hosted\n"),
    ("6 && combo",
     r"""fn main() -> int {
  comptime if target == "native" && !debug {
    println("yes");
  } else {
    println("no");
  }
  return 0;
}
""",
     "yes\n"),
    ("7 || combo",
     r"""fn main() -> int {
  comptime if target == "big32" || mode == "safe" {
    println("yes");
  } else {
    println("no");
  }
  return 0;
}
""",
     "yes\n"),
    ("8 chained else comptime if",
     r"""fn main() -> int {
  comptime if target == "big32" {
    println("big32");
  } else comptime if target == "wasm" {
    println("wasm");
  } else {
    println("native");
  }
  return 0;
}
""",
     "native\n"),
    ("9 else-less false does nothing",
     r"""fn main() -> int {
  comptime if target == "big32" {
    println("big32");
  }
  println("done");
  return 0;
}
""",
     "done\n"),
    ("10 nesting: outer native, inner big32-else",
     r"""fn main() -> int {
  comptime if target == "native" {
    comptime if target == "big32" {
      println("inner big32");
    } else {
      println("inner else");
    }
  } else {
    println("outer else");
  }
  return 0;
}
""",
     "inner else\n"),
    ("11 nesting: outer discarded, inner skipped",
     r"""fn main() -> int {
  comptime if target == "big32" {
    comptime if target == "native" {
      println("inner native");
    } else {
      println("inner else");
    }
  } else {
    println("after");
  }
  return 0;
}
""",
     "after\n"),
    ("12 let in taken branch used after it",
     r"""fn main() -> int {
  comptime if target == "native" {
    let v: int = 7;
  }
  println(v);
  return 0;
}
""",
     "7\n"),
    ("13 defer in taken branch runs",
     r"""fn cleanup() -> void {
  println("cleaned");
}
fn main() -> int {
  comptime if target == "native" {
    defer cleanup();
  }
  println("body");
  return 0;
}
""",
     "body\ncleaned\n"),
    ("14 return in taken branch ends the function",
     r"""fn main() -> int {
  comptime if target == "native" {
    println("early");
    return 0;
  }
  println("late");
  return 0;
}
""",
     "early\n"),
    ("15 arch predicate",
     r"""fn main() -> int {
  comptime if arch == "x86_64" {
    println("x86");
  } else {
    println("other arch");
  }
  return 0;
}
""",
     "x86\n"),
    ("16 os predicate",
     r"""fn main() -> int {
  comptime if os == "linux" {
    println("linux");
  } else {
    println("other os");
  }
  return 0;
}
""",
     "linux\n"),
    ("17 comptime stays a plain identifier (p12)",
     r"""fn main() -> int {
  let comptime: int = 3;
  println(comptime);
  return 0;
}
""",
     "3\n"),
    ("18 comptime if inside a for loop",
     r"""fn main() -> int {
  for i in 0..3 {
    comptime if target == "native" {
      println(i);
    }
  }
  return 0;
}
""",
     "0\n1\n2\n"),
    ("19 generic function with comptime if",
     r"""fn pick<T>(v: T) -> int {
  comptime if target == "native" {
    return 1;
  }
  return 0;
}
fn main() -> int {
  println(pick(5));
  return 0;
}
""",
     "1\n"),
    ("20 parenthesised negation",
     r"""fn main() -> int {
  comptime if !(target == "big32") {
    println("yes");
  } else {
    println("no");
  }
  return 0;
}
""",
     "yes\n"),
    ("21 mode fast else-branch under safe mode",
     r"""fn main() -> int {
  comptime if mode == "fast" {
    println("fast");
  } else {
    println("safe");
  }
  return 0;
}
""",
     "safe\n"),
    ("22 negative control: discarded branch with unknown call "
     "and type error checks clean",
     r"""fn main() -> int {
  comptime if target == "big32" {
    nosuchfn();
    let x: int = "wrong";
  }
  println("ok");
  return 0;
}
""",
     "ok\n"),
]

# (name, program, expected stderr fragment). Both compilers.
ERR_CASES = [
    ("E1 unknown predicate",
     r"""fn main() -> int {
  comptime if feature == "x" {
    println("x");
  }
  return 0;
}
""",
     "unknown predicate 'feature'"),
    ("E2 unknown target value",
     r"""fn main() -> int {
  comptime if target == "windows" {
    println("win");
  }
  return 0;
}
""",
     'is not a target'),
    ("E3 non-predicate condition",
     r"""fn main() -> int {
  comptime if true {
    println("yes");
  }
  return 0;
}
""",
     "needs a target predicate"),
    ("E4 call as condition",
     r"""fn main() -> int {
  comptime if foo() {
    println("yes");
  }
  return 0;
}
""",
     "unknown predicate 'foo'"),
    ("E5 top-level comptime if",
     r"""comptime if target == "native" {
  println("top");
}
fn main() -> int {
  return 0;
}
""",
     "only allowed inside functions in v1"),
    ("E6 name declared only in discarded branch used after it",
     r"""fn main() -> int {
  comptime if target == "big32" {
    let v: int = 7;
  }
  println(v);
  return 0;
}
""",
     "undefined variable 'v'"),
    ("E7 type error in TAKEN branch",
     r"""fn main() -> int {
  comptime if target == "native" {
    let x: int = "wrong";
  }
  return 0;
}
""",
     "declared int but initialised with str"),
    ("E8 unknown arch value",
     r"""fn main() -> int {
  comptime if arch == "arm64" {
    println("arm");
  }
  return 0;
}
""",
     "is not an architecture"),
    ("E9 debug takes no value",
     r"""fn main() -> int {
  comptime if debug == true {
    println("debug");
  }
  return 0;
}
""",
     "takes no value"),
    ("E10 valued predicate needs a comparison",
     r"""fn main() -> int {
  comptime if target {
    println("yes");
  }
  return 0;
}
""",
     "needs a comparison"),
]

# big32: native-only code (spawn) in the discarded branch must build.
BIG32_DISCARD_PROG = r"""fn work() -> void {
  println("work");
}
fn main() -> int {
  comptime if target == "native" {
    spawn work();
  } else {
    println("b32");
  }
  return 0;
}
"""

# big32: the same program with the predicate flipped — the spawn
# branch is taken on big32, so the build must fail with the
# ordinary backend error.
BIG32_FLIPPED_PROG = r"""fn work() -> void {
  println("work");
}
fn main() -> int {
  comptime if target == "big32" {
    spawn work();
  } else {
    println("b32");
  }
  return 0;
}
"""

# wasm: a struct in the discarded (non-wasm) branch; the taken
# wasm branch is struct-free, so emit-wasm must succeed.
WASM_GATED_PROG = r"""struct Point { x: int, y: int }
fn main() -> int {
  comptime if target == "wasm" {
    println("wasm");
  } else {
    let p: Point = Point { x: 1, y: 2 };
    println(p.x);
  }
  return 0;
}
"""

# check --target: the invalid big32 branch fails under big32, but
# plain check (native) passes — the same program both ways.
TARGET_CHECK_PROG = r"""fn main() -> int {
  comptime if target == "big32" {
    nosuchfn();
    let x: int = "wrong";
  }
  println("ok");
  return 0;
}
"""

# fmt: odd spacing must normalise to the canonical form, and the
# `comptime` keyword must survive (never stripped). Canonical fmt
# indents 4 spaces per level.
FMT_PROG = "fn main() -> int {\n  comptime if target==\"native\" {\n    println(\"native\");\n  } else {\n    println(\"other\");\n  }\n  return 0;\n}\n"
FMT_WANT = "fn main() -> int {\n    comptime if target == \"native\" {\n        println(\"native\");\n    } else {\n        println(\"other\");\n    }\n    return 0;\n}\n"


def run(args, cwd, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    # The #50 slice found forge.py honors ambient
    # QASIDA_COMPILER; scrub it so "hosted" runs are hosted.
    e.pop("QASIDA_COMPILER", None)
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=e)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}", flush=True)
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
                shutil.rmtree("/tmp/qasida_cache", ignore_errors=True)
                rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                         prefix + ["run", p], ROOT)
                ok = rr.returncode != 0 and frag in rr.stderr
                if not check(f"{name} ({mode})", ok,
                             f"rc={rr.returncode} err={rr.stderr[:200]!r}"):
                    failures.append(f"{name} ({mode})")
        # big32 (Python compiler only): discarded native-only code
        # must build and print from the taken branch.
        sys.path.insert(0, MODEL_DIR)
        import model as big32_model
        p = os.path.join(td, "b.fg")
        with open(p, "w") as f:
            f.write(BIG32_DISCARD_PROG)
        hexpath = os.path.join(td, "b.hex")
        shutil.rmtree("/tmp/qasida_cache", ignore_errors=True)
        rb = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                  "build", p, "--target", "big32", "-o", os.path.join(td, "b")],
                 ROOT)
        if rb.returncode != 0:
            check("big32 discarded native-only code builds", False,
                  f"build rc={rb.returncode} err={rb.stderr[:200]!r}")
            failures.append("big32 discarded native-only code builds")
        else:
            res = big32_model.run(hexpath)
            ok = res.get("uart", b"") == b"b32\n" and res.get("halted") and res.get("a0") == 0
            if not check("big32 discarded native-only code builds", ok,
                         f"uart={res.get('uart', b'')!r} halted={res.get('halted')} a0={res.get('a0')}"):
                failures.append("big32 discarded native-only code builds")
        # big32 flipped: the spawn branch is taken, so the build
        # must fail with the ordinary backend error.
        p = os.path.join(td, "bf.fg")
        with open(p, "w") as f:
            f.write(BIG32_FLIPPED_PROG)
        shutil.rmtree("/tmp/qasida_cache", ignore_errors=True)
        rf = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                  "build", p, "--target", "big32", "-o", os.path.join(td, "bf")],
                 ROOT)
        if not check("big32 flipped predicate fails with backend error",
                     rf.returncode != 0 and "spawn/threads are not supported on big32 (v1)" in rf.stderr,
                     f"rc={rf.returncode} err={rf.stderr[:200]!r}"):
            failures.append("big32 flipped predicate fails with backend error")
        # wasm struct-gated program must emit.
        p = os.path.join(td, "w.fg")
        with open(p, "w") as f:
            f.write(WASM_GATED_PROG)
        shutil.rmtree("/tmp/qasida_cache", ignore_errors=True)
        rw = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                  "emit-wasm", p, "-o", os.path.join(td, "w.wasm")], ROOT)
        if not check("wasm struct-gated program emits", rw.returncode == 0,
                     f"rc={rw.returncode} err={rw.stderr[:200]!r}"):
            failures.append("wasm struct-gated program emits")
        # check --target big32 on the invalid big32 branch must
        # fail; plain check on the same program must pass.
        p = os.path.join(td, "t.fg")
        with open(p, "w") as f:
            f.write(TARGET_CHECK_PROG)
        shutil.rmtree("/tmp/qasida_cache", ignore_errors=True)
        rt = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                  "check", "--target", "big32", p], ROOT)
        if not check("check --target big32 fails on invalid big32 branch",
                     rt.returncode != 0 and "undefined function 'nosuchfn'" in rt.stderr,
                     f"rc={rt.returncode} err={rt.stderr[:200]!r}"):
            failures.append("check --target big32 fails on invalid big32 branch")
        shutil.rmtree("/tmp/qasida_cache", ignore_errors=True)
        rp = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                  "check", p], ROOT)
        if not check("plain check passes on the same program", rp.returncode == 0,
                     f"rc={rp.returncode} err={rp.stderr[:200]!r}"):
            failures.append("plain check passes on the same program")
        # fmt keeps `comptime`, normalises spacing, and is idempotent.
        p = os.path.join(td, "f.fg")
        with open(p, "w") as f:
            f.write(FMT_PROG)
        rf1 = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                   "fmt", p], ROOT)
        with open(p) as f:
            got = f.read()
        if not check("fmt keeps comptime and normalises spacing",
                     rf1.returncode == 0 and got == FMT_WANT,
                     f"rc={rf1.returncode} got={got!r}"):
            failures.append("fmt keeps comptime and normalises spacing")
        rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                   "fmt", p], ROOT)
        with open(p) as f:
            got2 = f.read()
        if not check("fmt idempotent on comptime if",
                     rf2.returncode == 0 and got2 == FMT_WANT,
                     f"rc={rf2.returncode} got={got2!r}"):
            failures.append("fmt idempotent on comptime if")
    if failures:
        print(f"FAILURES ({len(failures)}): {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
