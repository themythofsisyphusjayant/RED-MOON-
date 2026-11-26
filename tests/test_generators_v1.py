"""Top-500 #74: generator functions / yield (tests/test_generators_v1.py).

`yield expr;` inside `fn name(...) -> Generator<T>` — a lazy
generator object with a per-generator `<name>_next(g) ->
Option<T>` step function, landed 26 Nov 2026 (Sprint Day 6).
The recommended design (DESIGN.md in
blackmoon-iso/generators-slice/): checker-side state-machine
desugar (the #70/#72 precedent, program-level like #70). A
generator fn becomes a CONSTRUCTOR (same name, builds the value,
body never runs) plus a STEP FUNCTION `<name>_next(g)` (the #75
it_next precedent). State lives in ONE shared generic struct
`Generator<T> { kind, cur, slots_i, slots_s, slots_b }`
(forge_lang/stdlib/generators.fg): params/locals are lifted into
slot arrays, slots_i[0] is the state, cur is a type witness
holding the zero value. The step fn is a `while (true)` dispatch
loop over `if (g.slots_i[0] == N)` segments; each segment ends
with a yield-return, a return-none, or a state jump. The Python
transform lives in forge_lang/generators.py; the hosted mirror
is the g_* section of examples/selfhost_check.fg (its G* structs
live in examples/selfhost_infer.fg — the codegen emits array-free
helpers in struct-registration order with no forward
declarations, so a struct holding a Node must be defined in a
file merged after selfhost_parse.fg; see the #47 latent bug).

v1 limits: element/local/param types int/str/bool only; `for x
in g` does not work (manual next() loop is the v1 idiom); no
yield in match arms, comptime branches, for-over-array, scope
blocks, or nested lambdas; no defer and no walrus in a generator
body; native only — big32/wasm/freestanding are named check-time
rejections. A generator fn with no yield is a valid empty
generator (first next() returns none); the body runs lazily, once,
on the first next(). `return` (bare or valued) ends iteration.

The s06b fix (this slice, after the first smoke run hung):
a labeled break/continue targeting a SPLIT loop from inside an
INLINE (real C) loop was emitted as `state = tgt; continue;` —
but that `continue` targets the innermost inline loop, not the
dispatch loop, so it spun forever. The fix: such a jump emits
`state = tgt; break;` (unlabeled, exits the innermost inline
loop) and every inline loop is followed by an unwind guard
`if (state != cur_state) { break|continue; }` that cascades the
unwind outward to the dispatch loop. Both compilers mirror it.

Both compilers (Python + hosted) for the native OK/ERR cases.
Backend cases run under the Python compiler only: the hosted
driver defers non-native emit to Python, so the check-time
rejection strings are the same in both compilers. The fmt case
runs under the Python fmt (fmt is deferred in hosted). ASan
program-side on every OK program under both compilers lives in
the separate gate script asan_74.py in the slice dir.
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# (name, program, expected stdout, stdin).
OK_CASES = [
    ("1 count_up while",
     r"""import "generators.fg";

fn count_up(n: int) -> Generator<int> {
    let i: int = 0;
    while (i < n) {
        yield i;
        i = i + 1;
    }
}

fn main() -> int {
    let g: Generator<int> = count_up(3);
    let mut v: Option<int> = count_up_next(g);
    while (v.present) {
        println(v.value);
        v = count_up_next(g);
    }
    println("end");
    return 0;
}
""",
     "0\n1\n2\nend\n", ""),
    ("2 for-range + str + params + if",
     r"""import "generators.fg";

fn repeat_word(w: str, n: int) -> Generator<str> {
    for i in 0..n {
        yield w;
    }
}

fn evens(n: int) -> Generator<int> {
    let i: int = 0;
    while (i < n) {
        if (i % 2 == 0) {
            yield i;
        }
        i = i + 1;
    }
}

fn main() -> int {
    let g: Generator<str> = repeat_word("hi", 3);
    let mut v: Option<str> = repeat_word_next(g);
    while (v.present) {
        println(v.value);
        v = repeat_word_next(g);
    }
    let e: Generator<int> = evens(6);
    let mut x: Option<int> = evens_next(e);
    while (x.present) {
        println(x.value);
        x = evens_next(e);
    }
    return 0;
}
""",
     "hi\nhi\nhi\n0\n2\n4\n", ""),
    ("3 fib + early return + break",
     r"""import "generators.fg";

fn fib(n: int) -> Generator<int> {
    let a: int = 0;
    let b: int = 1;
    let i: int = 0;
    while (i < n) {
        yield a;
        let t: int = a + b;
        a = b;
        b = t;
        i = i + 1;
    }
}

fn early(n: int) -> Generator<int> {
    let i: int = 0;
    while (i < 10) {
        if (i == n) {
            return;
        }
        yield i;
        i = i + 1;
    }
}

fn with_break(n: int) -> Generator<int> {
    let i: int = 0;
    while (true) {
        if (i >= n) {
            break;
        }
        yield i;
        i = i + 1;
    }
}

fn main() -> int {
    let f: Generator<int> = fib(6);
    let mut v: Option<int> = fib_next(f);
    while (v.present) {
        println(v.value);
        v = fib_next(f);
    }
    let e: Generator<int> = early(2);
    let mut x: Option<int> = early_next(e);
    while (x.present) {
        println(x.value);
        x = early_next(e);
    }
    println("early-end");
    let b: Generator<int> = with_break(3);
    let mut y: Option<int> = with_break_next(b);
    while (y.present) {
        println(y.value);
        y = with_break_next(b);
    }
    println("break-end");
    return 0;
}
""",
     "0\n1\n1\n2\n3\n5\n0\n1\nearly-end\n0\n1\n2\nbreak-end\n", ""),
    ("4 two interleaved + lazy empty",
     r"""import "generators.fg";

fn count_up(n: int) -> Generator<int> {
    let i: int = 0;
    while (i < n) {
        yield i;
        i = i + 1;
    }
}

fn empty() -> Generator<int> {
    let x: int = 5;
    println(x);
}

fn main() -> int {
    let a: Generator<int> = count_up(2);
    let b: Generator<int> = count_up(2);
    let mut va: Option<int> = count_up_next(a);
    println(va.value);
    let mut vb: Option<int> = count_up_next(b);
    println(vb.value);
    va = count_up_next(a);
    println(va.value);
    vb = count_up_next(b);
    println(vb.value);
    va = count_up_next(a);
    println(va.present);
    vb = count_up_next(b);
    println(vb.present);
    let e: Generator<int> = empty();
    let oe: Option<int> = empty_next(e);
    println(oe.present);
    println("done");
    return 0;
}
""",
     "0\n0\n1\n1\nfalse\nfalse\n5\nfalse\ndone\n", ""),
    ("5 lambda inline + match + scope + bool + continue",
     r"""import "generators.fg";

fn apply(f: fn(int) -> int, x: int) -> int {
    return f(x);
}

fn with_lambda(n: int) -> Generator<int> {
    let base: int = 10;
    let i: int = 0;
    while (i < n) {
        yield apply(fn(x: int) -> int { return x * 2 + base; }, i);
        i = i + 1;
    }
}

fn with_match(n: int) -> Generator<str> {
    let i: int = 0;
    while (i < n) {
        let mut w: str = "";
        match i {
            0 => { w = "zero"; }
            1 => { w = "one"; }
            _ => { w = "many"; }
        }
        yield w;
        i = i + 1;
    }
}

fn with_scope(n: int) -> Generator<int> {
    let i: int = 0;
    while (i < n) {
        let mut t: int = 0;
        scope {
            t = i * 10;
        }
        yield t;
        i = i + 1;
    }
}

fn flags(n: int) -> Generator<bool> {
    let i: int = 0;
    while (i < n) {
        if (i % 2 == 0) {
            yield true;
        } else {
            yield false;
        }
        i = i + 1;
    }
}

fn with_continue(n: int) -> Generator<int> {
    let i: int = 0;
    while (i < n) {
        i = i + 1;
        if (i % 2 == 0) {
            continue;
        }
        yield i;
    }
}

fn main() -> int {
    let g: Generator<int> = with_lambda(3);
    let mut v: Option<int> = with_lambda_next(g);
    while (v.present) {
        println(v.value);
        v = with_lambda_next(g);
    }
    let m: Generator<str> = with_match(3);
    let mut w: Option<str> = with_match_next(m);
    while (w.present) {
        println(w.value);
        w = with_match_next(m);
    }
    let s: Generator<int> = with_scope(2);
    let mut x: Option<int> = with_scope_next(s);
    while (x.present) {
        println(x.value);
        x = with_scope_next(s);
    }
    let f: Generator<bool> = flags(3);
    let mut b: Option<bool> = flags_next(f);
    while (b.present) {
        println(b.value);
        b = flags_next(f);
    }
    let c: Generator<int> = with_continue(5);
    let mut y: Option<int> = with_continue_next(c);
    while (y.present) {
        println(y.value);
        y = with_continue_next(c);
    }
    println("done");
    return 0;
}
""",
     "10\n12\n14\nzero\none\nmany\n0\n10\ntrue\nfalse\ntrue\n1\n3\n5\ndone\n", ""),
    ("6 rebind + labeled break/continue + both branches",
     r"""import "generators.fg";

fn rebind(n: int) -> Generator<int> {
    let x: int = 1;
    yield x;
    let x: int = x + 1;
    yield x;
    let x: int = x * 10;
    yield x;
}

fn labeled(n: int) -> Generator<int> {
    let i: int = 0;
    outer: while (i < 10) {
        let j: int = 0;
        while (j < 10) {
            if (j == 2) {
                break outer;
            }
            j = j + 1;
        }
        yield i;
        i = i + 1;
    }
}

fn both_branches(n: int) -> Generator<str> {
    let i: int = 0;
    while (i < n) {
        if (i % 2 == 0) {
            yield "even";
        } else {
            yield "odd";
        }
        i = i + 1;
    }
}

fn labeled_continue(n: int) -> Generator<int> {
    let i: int = 0;
    outer: while (i < n) {
        i = i + 1;
        let j: int = 0;
        while (j < 3) {
            j = j + 1;
            if (j == 2) {
                continue outer;
            }
            yield i * 10 + j;
        }
    }
}

fn main() -> int {
    let r: Generator<int> = rebind(0);
    let mut v: Option<int> = rebind_next(r);
    while (v.present) {
        println(v.value);
        v = rebind_next(r);
    }
    let l: Generator<int> = labeled(5);
    let mut w: Option<int> = labeled_next(l);
    while (w.present) {
        println(w.value);
        w = labeled_next(l);
    }
    println("labeled-end");
    let b: Generator<str> = both_branches(4);
    let mut x: Option<str> = both_branches_next(b);
    while (x.present) {
        println(x.value);
        x = both_branches_next(b);
    }
    let c: Generator<int> = labeled_continue(2);
    let mut y: Option<int> = labeled_continue_next(c);
    while (y.present) {
        println(y.value);
        y = labeled_continue_next(c);
    }
    println("done");
    return 0;
}
""",
     "1\n2\n20\nlabeled-end\neven\nodd\neven\nodd\n11\n21\ndone\n", ""),
    ("7 demo count_up + repeat_word + fib",
     r"""import "generators.fg";

fn count_up(n: int) -> Generator<int> {
    let i: int = 0;
    while (i < n) {
        yield i;
        i = i + 1;
    }
}

fn repeat_word(w: str, n: int) -> Generator<str> {
    for i in 0..n {
        yield w;
    }
}

fn fib(n: int) -> Generator<int> {
    let a: int = 0;
    let b: int = 1;
    let i: int = 0;
    while (i < n) {
        yield a;
        let t: int = a + b;
        a = b;
        b = t;
        i = i + 1;
    }
}

fn main() -> int {
    let g: Generator<int> = count_up(3);
    let mut v: Option<int> = count_up_next(g);
    while (v.present) {
        println(v.value);
        v = count_up_next(g);
    }
    let w: Generator<str> = repeat_word("hi", 2);
    let mut x: Option<str> = repeat_word_next(w);
    while (x.present) {
        println(x.value);
        x = repeat_word_next(w);
    }
    let f: Generator<int> = fib(6);
    let mut y: Option<int> = fib_next(f);
    while (y.present) {
        println(y.value);
        y = fib_next(f);
    }
    println("done");
    return 0;
}
""",
     "0\n1\n2\nhi\nhi\n0\n1\n1\n2\n3\n5\ndone\n", ""),
    ("8 nested inline loops + labeled break (unwind guard)",
     r"""import "generators.fg";

fn nested(n: int) -> Generator<int> {
    let i: int = 0;
    outer: while (i < n) {
        let j: int = 0;
        while (j < 3) {
            let k: int = 0;
            while (k < 3) {
                if (k == 1) {
                    break outer;
                }
                k = k + 1;
            }
            j = j + 1;
        }
        yield i;
        i = i + 1;
    }
}

fn main() -> int {
    let g: Generator<int> = nested(3);
    let mut v: Option<int> = nested_next(g);
    while (v.present) {
        println(v.value);
        v = nested_next(g);
    }
    println("done");
    return 0;
}
""",
     "done\n", ""),
    ("9 labeled break from a match arm in an inline loop",
     r"""import "generators.fg";

fn mb(n: int) -> Generator<int> {
    let i: int = 0;
    outer: while (i < n) {
        let j: int = 0;
        while (j < 3) {
            match j {
                1 => { break outer; }
                _ => { j = j + 1; }
            }
        }
        yield i;
        i = i + 1;
    }
}

fn main() -> int {
    let g: Generator<int> = mb(3);
    let mut v: Option<int> = mb_next(g);
    while (v.present) {
        println(v.value);
        v = mb_next(g);
    }
    println("done");
    return 0;
}
""",
     "done\n", ""),
]

# (name, program, expected stderr fragment).
ERR_CASES = [
    ("E01 yield outside a generator fn",
     r"""import "generators.fg";
fn plain() -> int {
    yield 5;
    return 0;
}
fn main() -> int { return plain(); }
""",
     "yield is only allowed in a function returning Generator<T> in v1"),
    ("E02 yield in a nested lambda",
     r"""import "generators.fg";
fn g(n: int) -> Generator<int> {
    let f = fn(x: int) -> int { yield x; return x; };
    yield 1;
}
fn main() -> int { return 0; }
""",
     "yield cannot appear inside a nested function or closure in v1"),
    ("E03 defer in a generator body",
     r"""import "generators.fg";
fn g(n: int) -> Generator<int> {
    defer println("x");
    yield 1;
}
fn main() -> int { return 0; }
""",
     "defer is not supported inside a generator function in v1"),
    ("E04 yield in a match arm",
     r"""import "generators.fg";
fn g(n: int) -> Generator<int> {
    match n {
        0 => { yield 0; }
        _ => { yield 1; }
    }
}
fn main() -> int { return 0; }
""",
     "yield cannot appear inside a match arm in v1 (use if/else)"),
    ("E05 yield in for over an array",
     r"""import "generators.fg";
fn get() -> [int] {
    return [1, 2];
}
fn g(n: int) -> Generator<int> {
    for x in get() {
        yield x;
    }
}
fn main() -> int { return 0; }
""",
     "for over an array cannot contain yield in v1 (use while, or a for loop over a range)"),
    ("E06 bad element type",
     r"""import "generators.fg";
fn g(n: int) -> Generator<[int]> {
    yield [1];
}
fn main() -> int { return 0; }
""",
     "generator element type must be int, str, or bool in v1, got [int]"),
    ("E07 missing import",
     r"""fn g(n: int) -> Generator<int> {
    yield n;
}
fn main() -> int { return 0; }
""",
     "generator functions need import \"generators.fg\""),
    ("E08 yield type mismatch",
     r"""import "generators.fg";
fn g(n: int) -> Generator<int> {
    yield "hello";
}
fn main() -> int { return 0; }
""",
     "yield value of type str does not match generator element type int"),
    ("E09 generic generator fn",
     r"""import "generators.fg";
fn g<T>(x: int) -> Generator<int> {
    yield x;
}
fn main() -> int { return 0; }
""",
     "generic generator functions are not supported in v1"),
    ("E10 walrus in a generator body",
     r"""import "generators.fg";
fn g(n: int) -> Generator<int> {
    let x: int = 0;
    if ((x := 5) > 0) {
        yield x;
    }
}
fn main() -> int { return 0; }
""",
     "walrus ':=' is not supported inside a generator function in v1"),
    ("E11 yield in a comptime-if branch",
     r"""import "generators.fg";
fn g(n: int) -> Generator<int> {
    comptime if (debug) {
        yield 1;
    }
    yield 2;
}
fn main() -> int { return 0; }
""",
     "yield cannot appear inside a comptime if branch in v1"),
    ("E12 yield in a scope block",
     r"""import "generators.fg";
fn g(n: int) -> Generator<int> {
    scope {
        yield 1;
    }
}
fn main() -> int { return 0; }
""",
     "yield cannot appear inside a scope block in v1"),
    ("E13 non-liftable array local",
     r"""import "generators.fg";
fn g(n: int) -> Generator<int> {
    let a: [int] = [1, 2];
    yield a[0];
}
fn main() -> int { return 0; }
""",
     "generator local 'a' has type [int]; only int, str, and bool locals are supported in v1"),
    ("E14 step-fn name collision",
     r"""import "generators.fg";
fn g_next(g: Generator<int>) -> Option<int> {
    return Option { present: false, value: 0 };
}
fn g(n: int) -> Generator<int> {
    yield n;
}
fn main() -> int { return 0; }
""",
     "generator 'g' needs a step function named 'g_next' but one already exists; rename it"),
    ("E15 non-liftable array param",
     r"""import "generators.fg";
fn g(a: [int]) -> Generator<int> {
    yield 1;
}
fn main() -> int { return 0; }
""",
     "generator parameter 'a' has type [int]; only int, str, and bool parameters are supported in v1"),
    ("E16 lambda-valued local",
     r"""import "generators.fg";
fn g(n: int) -> Generator<int> {
    let f = fn(x: int) -> int { return x; };
    yield 1;
}
fn main() -> int { return 0; }
""",
     "generator local 'f' has type fn(int) -> int; only int, str, and bool locals are supported in v1"),
    ("E17 for over a range expression",
     r"""import "generators.fg";
fn get() -> range {
    return 0..3;
}
fn g(n: int) -> Generator<int> {
    for x in get() {
        yield x;
    }
}
fn main() -> int { return 0; }
""",
     "for over a range expression is not supported in v1 (use a literal lo..hi range or a while loop)"),
]

# Backend rejections (Python compiler only): a program that
# DEFINES a generator fails the check on these targets even if
# main never uses it.
BACKEND_PROG = r"""import "generators.fg";
fn count_up(n: int) -> Generator<int> {
    let i: int = 0;
    while (i < n) {
        yield i;
        i = i + 1;
    }
}
fn main() -> int { return 0; }
"""

# fmt: yield round-trips, spacing normalises, second fmt is a no-op.
FMT_PROG = """import "generators.fg";
fn count_up(n:int)->Generator<int>{
let i:int=0;
while(i<n){
yield i;
i=i+1;
}
}
fn main()->int{
let g:Generator<int> =count_up(3);
let mut v:Option<int> =count_up_next(g);
while(v.present){
println(v.value);
v=count_up_next(g);
}
println("end");
return 0;
}
"""
FMT_WANT = """import "generators.fg";

fn count_up(n: int) -> Generator<int> {
    let i: int = 0;
    while i < n {
        yield i;
        i = i + 1;
    }
}

fn main() -> int {
    let g: Generator<int> = count_up(3);
    let mut v: Option<int> = count_up_next(g);
    while v.present {
        println(v.value);
        v = count_up_next(g);
    }
    println("end");
    return 0;
}
"""


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
        # Backend rejections (Python compiler only): check with
        # the target flag fails with the named generator error.
        p = os.path.join(td, "b.fg")
        with open(p, "w") as f:
            f.write(BACKEND_PROG)
        for name, args, frag in (
            ("big32", ["check", p, "--target", "big32"],
             "generators are not supported on big32 in v1"),
            ("wasm", ["check", p, "--target", "wasm"],
             "generators are not supported on wasm in v1"),
            ("freestanding", ["check", p, "--freestanding"],
             "generators are not supported in freestanding mode in v1"),
        ):
            shutil.rmtree("/tmp/qasida_cache", ignore_errors=True)
            rr = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python"] +
                     args, ROOT)
            ok = rr.returncode != 0 and frag in rr.stderr
            if not check(f"backend rejection {name}", ok,
                         f"rc={rr.returncode} err={rr.stderr[:200]!r}"):
                failures.append(f"backend rejection {name}")
        # fmt round-trips yield, normalises spacing, idempotent.
        p = os.path.join(td, "f.fg")
        with open(p, "w") as f:
            f.write(FMT_PROG)
        rf1 = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                   "fmt", p], ROOT)
        with open(p) as f:
            got = f.read()
        if not check("fmt normalises yield program",
                     rf1.returncode == 0 and got == FMT_WANT,
                     f"rc={rf1.returncode} got={got!r}"):
            failures.append("fmt normalises yield program")
        rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                   "fmt", p], ROOT)
        with open(p) as f:
            got2 = f.read()
        if not check("fmt idempotent on yield program",
                     rf2.returncode == 0 and got2 == FMT_WANT,
                     f"rc={rf2.returncode} got={got2!r}"):
            failures.append("fmt idempotent on yield program")
    if failures:
        print(f"FAILURES ({len(failures)}): {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
