"""Top-500 #77: nested function definitions (tests/test_nestedfn_v1.py).

`fn name(params) -> Ret { body }` as a STATEMENT inside a function
body (Python `def` shape). Checker-side desugar rewrites it in place
to `let name = fn(params) -> Ret { body };` before the body's
statements are checked, so infer/codegen see only ordinary closures.
v1 rules (DESIGN.md §3.5): `-> Ret` required; NO recursion (named
error); may NOT shadow a top-level fn or a parameter (named errors);
allowed in any block directly inside a function/method body incl.
loop/if blocks, NOT in match arms or comptime-if branches (named
errors); a nested fn itself is NOT generic (named error); a
non-generic nested fn inside a generic outer fn IS allowed; capture
by value, read-only, exactly like closures (#101); binding lives in
the enclosing block, visible after its declaration line, dies at
block end (use-before-def is the existing `undefined function`
error); second nested fn of the same name in one block is a named
error. Backends inherit closures: native only in v1 — big32 and WASM
codegen reject Lambda expressions outright (named errors, and the
plain fn-literal form fails identically, so this is a pre-existing
closure limit, not a #77 gap); freestanding keeps the existing named
lambda error. A nested fn returning a
generic struct type (Result/Option) hits the PRE-EXISTING closure
typedef-order C gap (the plain fn-literal form fails identically) —
a named v1 limit, inherited from closures, NOT a #77 gap; `?` inside
a nested fn works exactly as at top level (propagation-only — it
requires the enclosing fn to return Option/Result).
Both compilers (Python + hosted) for the native cases. big32/wasm/
freestanding are Python-compiler only (the hosted driver defers
emit-big32/emit-wasm and freestanding is a check-time gate).
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def run(cmd, cwd, stdin=None):
    return subprocess.run(cmd, cwd=cwd, input=stdin,
                          capture_output=True, text=True, timeout=300)


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    return cond


# (name, program, expected stdout, stdin)
OK_CASES = [
    ("1 basic decl + call",
     "fn outer(x: int) -> int {\n"
     "    fn helper(y: int) -> int { return y * 2; }\n"
     "    return helper(x);\n"
     "}\n"
     "fn main() -> int { println(outer(21)); return 0; }\n",
     "42\n", None),
    ("2 capture read",
     "fn outer() -> int {\n"
     "    let base: int = 10;\n"
     "    fn helper(y: int) -> int { return y + base; }\n"
     "    return helper(5);\n"
     "}\n"
     "fn main() -> int { println(outer()); return 0; }\n",
     "15\n", None),
    ("3 nested fn in if-block",
     "fn main() -> int {\n"
     "    let x: int = 3;\n"
     "    if (x > 0) {\n"
     "        fn helper(y: int) -> int { return y * 10; }\n"
     "        println(helper(x));\n"
     "    }\n"
     "    return 0;\n"
     "}\n",
     "30\n", None),
    ("4 sibling calls",
     "fn main() -> int {\n"
     "    fn dbl(y: int) -> int { return y * 2; }\n"
     "    fn quad(y: int) -> int { return dbl(dbl(y)); }\n"
     "    println(dbl(21));\n"
     "    println(quad(5));\n"
     "    return 0;\n"
     "}\n",
     "42\n20\n", None),
    ("5 per-iteration capture",
     "fn main() -> int {\n"
     "    let mut total: int = 0;\n"
     "    let mut i: int = 0;\n"
     "    while (i < 3) {\n"
     "        fn get() -> int { return 10 + i; }\n"
     "        total = total + get();\n"
     "        i = i + 1;\n"
     "    }\n"
     "    println(total);\n"
     "    return 0;\n"
     "}\n",
     "33\n", None),
    ("6 generic outer fn",
     "fn apply<T>(x: T, y: int) -> int {\n"
     "    fn helper(z: int) -> int { return z + y; }\n"
     "    return helper(40);\n"
     "}\n"
     "fn main() -> int { println(apply(1, 3)); return 0; }\n",
     "43\n", None),
    ("7 sibling branch blocks",
     "fn main() -> int {\n"
     "    if (true) {\n"
     "        fn h(y: int) -> int { return y + 1; }\n"
     "        println(h(1));\n"
     "    }\n"
     "    if (true) {\n"
     "        fn h(y: int) -> int { return y + 10; }\n"
     "        println(h(1));\n"
     "    }\n"
     "    return 0;\n"
     "}\n",
     "2\n11\n", None),
    ("8 pass as arg (map)",
     "fn map(f: fn(int) -> int, xs: [int]) -> [int] {\n"
     "    let mut out: [int] = [];\n"
     "    let mut i: int = 0;\n"
     "    while (i < len(xs)) {\n"
     "        push(out, f(xs[i]));\n"
     "        i = i + 1;\n"
     "    }\n"
     "    return out;\n"
     "}\n"
     "fn main() -> int {\n"
     "    fn dbl(y: int) -> int { return y * 2; }\n"
     "    let r: [int] = map(dbl, [1, 2, 3]);\n"
     "    println(r[0]);\n"
     "    println(r[1]);\n"
     "    println(r[2]);\n"
     "    return 0;\n"
     "}\n",
     "2\n4\n6\n", None),
    ("9 return nested fn",
     "fn make(n: int) -> fn(int) -> int {\n"
     "    fn helper(y: int) -> int { return y + n; }\n"
     "    return helper;\n"
     "}\n"
     "fn main() -> int {\n"
     "    let f: fn(int) -> int = make(10);\n"
     "    println(f(5));\n"
     "    return 0;\n"
     "}\n",
     "15\n", None),
    ("10a p6 write-only capture (literal form)",
     "fn main() -> int {\n"
     "    let mut buf: [int] = [0, 0, 0];\n"
     "    let f = fn(i: int) -> int { buf[i] = 7; return buf[i]; };\n"
     "    println(f(1));\n"
     "    return 0;\n"
     "}\n",
     "7\n", None),
    ("10b p6 write-only capture (nested-fn form)",
     "fn main() -> int {\n"
     "    let mut buf: [int] = [0, 0, 0];\n"
     "    fn set(i: int) -> int { buf[i] = 7; return buf[i]; }\n"
     "    println(set(1));\n"
     "    return 0;\n"
     "}\n",
     "7\n", None),
    ("11 defer in nested fn",
     "fn cleanup() -> int { println(\"clean\"); return 0; }\n"
     "fn main() -> int {\n"
     "    fn work(y: int) -> int {\n"
     "        defer cleanup();\n"
     "        return y * 2;\n"
     "    }\n"
     "    println(work(21));\n"
     "    return 0;\n"
     "}\n",
     "clean\n42\n", None),
    ("12 fail in nested fn",
     "fn main() -> int {\n"
     "    fn guarded(y: int) -> int {\n"
     "        if (y < 0) { fail(\"neg\"); }\n"
     "        return y * 2;\n"
     "    }\n"
     "    println(guarded(21));\n"
     "    return 0;\n"
     "}\n",
     "42\n", None),
    ("13 shadow plain local let (inner block)",
     "fn main() -> int {\n"
     "    let dbl: int = 5;\n"
     "    if (true) {\n"
     "        fn dbl(y: int) -> int { return y * 2; }\n"
     "        println(dbl(21));\n"
     "    }\n"
     "    println(dbl);\n"
     "    return 0;\n"
     "}\n",
     "42\n5\n", None),
    ("14 nested fn in struct method",
     "struct Rect { w: int, h: int }\n"
     "impl Rect {\n"
     "    fn perim(r: Rect) -> int {\n"
     "        fn dbl(y: int) -> int { return y * 2; }\n"
     "        return dbl(r.w + r.h);\n"
     "    }\n"
     "}\n"
     "fn main() -> int {\n"
     "    let r: Rect = Rect { w: 10, h: 11 };\n"
     "    println(r.perim());\n"
     "    return 0;\n"
     "}\n",
     "42\n", None),
    ("15 nested fn in lambda body",
     "fn outer() -> int {\n"
     "    let f = fn(x: int) -> int {\n"
     "        fn h(y: int) -> int { return y + x; }\n"
     "        return h(x);\n"
     "    };\n"
     "    return f(3);\n"
     "}\n"
     "fn main() -> int { println(outer()); return 0; }\n",
     "6\n", None),
    ("16 void nested fn",
     "fn main() -> int {\n"
     "    fn say() -> void { println(\"hi\"); }\n"
     "    say();\n"
     "    return 0;\n"
     "}\n",
     "hi\n", None),
    ("17 self-call shadowed by inner let is not recursion",
     "fn main() -> int {\n"
     "    fn fact(n: int) -> int {\n"
     "        let fact: int = 5;\n"
     "        return fact;\n"
     "    }\n"
     "    println(fact(3));\n"
     "    return 0;\n"
     "}\n",
     "5\n", None),
]

# (name, program, expected stderr fragment)
ERR_CASES = [
    ("E01 self-call direct",
     "fn main() -> int {\n"
     "    fn fact(n: int) -> int {\n"
     "        if (n <= 1) { return 1; }\n"
     "        return n * fact(n - 1);\n"
     "    }\n"
     "    println(fact(5));\n"
     "    return 0;\n"
     "}\n",
     "nested function 'fact' cannot call itself in v1 (use a top-level function or a loop)"),
    ("E02 self-call via nested lambda",
     "fn main() -> int {\n"
     "    fn fact(n: int) -> int {\n"
     "        let g = fn(x: int) -> int { return fact(x); };\n"
     "        return g(n);\n"
     "    }\n"
     "    println(fact(5));\n"
     "    return 0;\n"
     "}\n",
     "nested function 'fact' cannot call itself in v1 (use a top-level function or a loop)"),
    ("E03 self-reference as value",
     "fn main() -> int {\n"
     "    fn fact(n: int) -> int {\n"
     "        return fact;\n"
     "    }\n"
     "    println(fact(3));\n"
     "    return 0;\n"
     "}\n",
     "nested function 'fact' cannot call itself in v1 (use a top-level function or a loop)"),
    ("E04 shadow top-level fn",
     "fn f(x: int) -> int { return x; }\n"
     "fn main() -> int {\n"
     "    fn f(y: int) -> int { return y * 2; }\n"
     "    return f(1);\n"
     "}\n",
     "nested function 'f' shadows top-level function 'f'"),
    ("E05 shadow parameter",
     "fn outer(f: int) -> int {\n"
     "    fn f(y: int) -> int { return y; }\n"
     "    return f(1);\n"
     "}\n"
     "fn main() -> int { return outer(1); }\n",
     "nested function 'f' shadows parameter 'f'"),
    ("E06 generic nested fn",
     "fn main() -> int {\n"
     "    fn id<T>(x: T) -> T { return x; }\n"
     "    println(id(1));\n"
     "    return 0;\n"
     "}\n",
     "generic nested functions are not supported in v1"),
    ("E07 duplicate in one block",
     "fn main() -> int {\n"
     "    fn h(y: int) -> int { return y; }\n"
     "    fn h(y: int) -> int { return y * 2; }\n"
     "    println(h(1));\n"
     "    return 0;\n"
     "}\n",
     "nested function 'h' is already defined in this block"),
    ("E08 nested fn in match arm",
     "enum Color { Red, Blue }\n"
     "fn main() -> int {\n"
     "    let c: Color = Red;\n"
     "    match c {\n"
     "        Red => {\n"
     "            fn h(y: int) -> int { return y; }\n"
     "            println(h(1));\n"
     "        }\n"
     "        _ => { println(0); }\n"
     "    }\n"
     "    return 0;\n"
     "}\n",
     "nested functions are not allowed in match arms in v1"),
    ("E09 nested fn in comptime-if branch",
     "fn main() -> int {\n"
     "    comptime if target == \"native\" {\n"
     "        fn h(y: int) -> int { return y; }\n"
     "        println(h(1));\n"
     "    } else {\n"
     "        println(0);\n"
     "    }\n"
     "    return 0;\n"
     "}\n",
     "nested functions are not allowed in comptime-if branches in v1"),
    ("E10 missing return type",
     "fn main() -> int {\n"
     "    fn h(y: int) { return y; }\n"
     "    return h(1);\n"
     "}\n",
     "nested function 'h' must declare a return type (-> Ret)"),
    ("E11 use-before-def",
     "fn main() -> int {\n"
     "    println(h(1));\n"
     "    fn h(y: int) -> int { return y; }\n"
     "    return 0;\n"
     "}\n",
     "undefined function 'h'"),
    ("E12 same-block let shadow (different type)",
     "fn main() -> int {\n"
     "    let dbl: int = 5;\n"
     "    fn dbl(y: int) -> int { return y * 2; }\n"
     "    println(dbl(21));\n"
     "    return 0;\n"
     "}\n",
     "cannot shadow 'dbl' with a different type in v1"),
]

BIG32_PROG = (
    "fn main() -> int {\n"
    "    fn step(n: int) -> int { return n - 1; }\n"
    "    let mut n: int = 2;\n"
    "    while (n >= 0) {\n"
    "        println(n);\n"
    "        n = step(n);\n"
    "    }\n"
    "    return 0;\n"
    "}\n"
)

WASM_PROG = (
    "fn main() -> int {\n"
    "    fn get() -> int { return 7; }\n"
    "    return get();\n"
    "}\n"
)

FREESTANDING_PROG = (
    "fn main() -> int {\n"
    "    fn h(y: int) -> int { return y; }\n"
    "    return h(1);\n"
    "}\n"
)

FMT_PROG = "fn main() -> int {\n  fn helper(y:int)->int { return y*2; }\n  fn say()->void { println(\"hi\"); }\n  println(helper(21));\n  say();\n  return 0;\n}\n"
FMT_WANT = "fn main() -> int {\n    fn helper(y: int) -> int {\n        return y * 2;\n    }\n    fn say() -> void {\n        println(\"hi\");\n    }\n    println(helper(21));\n    say();\n    return 0;\n}\n"


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
        # big32 (Python compiler only): a nested-fn program does NOT
        # build — the big32 codegen rejects Lambda expressions
        # outright ("unsupported expression Lambda on big32"), and
        # the plain fn-literal form fails identically, so this is a
        # PRE-EXISTING closure limit, not a #77 gap. F6A narrows to
        # native-only in v1; big32 closure support is a follow-up.
        p = os.path.join(td, "b.fg")
        with open(p, "w") as f:
            f.write(BIG32_PROG)
        shutil.rmtree("/tmp/qasida_cache", ignore_errors=True)
        rb = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                  "build", p, "--target", "big32", "-o", os.path.join(td, "b")],
                 ROOT)
        if not check("big32 nested-fn rejected with named Lambda error",
                     rb.returncode != 0 and "unsupported expression Lambda on big32" in rb.stderr,
                     f"build rc={rb.returncode} err={rb.stderr[:200]!r}"):
            failures.append("big32 nested-fn rejected with named Lambda error")
        # wasm (Python compiler only): same story — the WASM codegen
        # rejects Lambda expressions ("wasm: expression Lambda is not
        # supported in v1"), and the plain fn-literal form fails
        # identically. WASM closure support is a follow-up.
        p = os.path.join(td, "w.fg")
        with open(p, "w") as f:
            f.write(WASM_PROG)
        shutil.rmtree("/tmp/qasida_cache", ignore_errors=True)
        rw = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                  "build", p, "--target", "wasm", "-o", os.path.join(td, "w.wasm")], ROOT)
        if not check("wasm nested-fn rejected with named Lambda error",
                     rw.returncode != 0 and "wasm: expression Lambda is not supported in v1" in rw.stderr,
                     f"build rc={rw.returncode} err={rw.stderr[:200]!r}"):
            failures.append("wasm nested-fn rejected with named Lambda error")
        # freestanding (Python compiler only): a nested-fn program
        # must FAIL with the existing named lambda error (closures
        # need the heap allocator, which freestanding has not got).
        p = os.path.join(td, "fs.fg")
        with open(p, "w") as f:
            f.write(FREESTANDING_PROG)
        shutil.rmtree("/tmp/qasida_cache", ignore_errors=True)
        rf = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                  "build", p, "--freestanding", "-o", os.path.join(td, "fs")],
                 ROOT)
        frag = "lambda expressions need the heap allocator (not in freestanding v1; use a named function instead)"
        if not check("freestanding nested-fn rejected with named lambda error",
                     rf.returncode != 0 and frag in rf.stderr,
                     f"rc={rf.returncode} err={rf.stderr[:200]!r}"):
            failures.append("freestanding nested-fn rejected with named lambda error")
        # fmt prints the statement form, normalises spacing, and is
        # idempotent (fmt is Python-only; the hosted driver defers
        # it).
        p = os.path.join(td, "f.fg")
        with open(p, "w") as f:
            f.write(FMT_PROG)
        rf1 = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                   "fmt", p], ROOT)
        with open(p) as f:
            got = f.read()
        if not check("fmt prints statement form and normalises spacing",
                     rf1.returncode == 0 and got == FMT_WANT,
                     f"rc={rf1.returncode} got={got!r}"):
            failures.append("fmt prints statement form and normalises spacing")
        rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                   "fmt", p], ROOT)
        with open(p) as f:
            got2 = f.read()
        if not check("fmt idempotent on nested fn",
                     rf2.returncode == 0 and got2 == FMT_WANT,
                     f"rc={rf2.returncode} got={got2!r}"):
            failures.append("fmt idempotent on nested fn")
    if failures:
        print(f"FAILURES ({len(failures)}): {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
