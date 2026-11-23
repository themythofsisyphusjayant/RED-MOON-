"""Hosted generic-call refcount fix (tests/test_generic_inc_fix_v1.py).

Sprint Day 3 found a hosted-compiler bug and worked around it in
errlog.fg (de-genericized log_on_err to 6 concrete variants): a GENERIC
function call returning a struct with an array field leaked under the
hosted compiler only. Root cause: the hosted checker does NOT rewrite
generic call names to mangled instantiation names (unlike Python's
checker), so the hosted freshness predicates (cg_is_fresh_struct /
cg_is_fresh_array / cg_is_fresh_fn in examples/selfhost_codegen.fg) did
a table lookup on the unmangled template name, missed, returned "not
fresh", and the receiving site emitted an extra unbalanced ownership
inc (forge_arr_inc on the struct's array field, forge_arr_inc on a
returned array, forge_closure_inc on a returned closure's env). The
fix mirrors the cg_is_fresh_str pattern: fall back to the infer map,
which holds the substituted return type. Python needed no change (its
checker rewrites call names, so its lookups hit).

Cases: the generic struct repro (ASan leak-free now), the identical
concrete-call control (still clean), a generic call returning a struct
WITHOUT an array field, a generic call used inline (not assigned), plus
the sibling predicates — a generic [str] return and a generic lambda
return. Each case runs under both compilers; the three leak repros
also run under ASan (emit C + cc -fsanitize=address, leak detection
on) and must print the exact transcript with zero sanitizer output.

errlog.fg is deliberately NOT re-genericized here — the fix is proved
with fresh probes instead, and the de-genericized library stays as is.

Runs use cwd=ROOT (like test_panic_recover_v1.py): the hosted binary
resolves stdlib imports relative to the repo root, so a temp cwd would
break every import. No FATAL / REJECT / BACKEND / FREESTANDING
sections: the fix adds no new builtins, so there is nothing to reject.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HOSTED = os.path.join(ROOT, "bin", "qasida-hosted")

DEMO_EXPECTED = """2
2
2
2
"""

BAG_DEFS = """struct Bag {
    items: [str],
    n: int,
}

fn make_bag<T>(seed: T) -> Bag {
    let mut items: [str] = [];
    push(items, "x");
    push(items, "y");
    return Bag { items: items, n: 2 };
}

fn make_bag_concrete(seed: int) -> Bag {
    let mut items: [str] = [];
    push(items, "x");
    push(items, "y");
    return Bag { items: items, n: 2 };
}
"""

WORDS_DEF = """fn make_words<T>(seed: T) -> [str] {
    let mut out: [str] = [];
    push(out, "x");
    push(out, "y");
    return out;
}
"""

# (name, program, expected stdout).
OK_CASES = [
    ("generic struct repro (assigned)",
     BAG_DEFS + """fn main() -> int {
    let b: Bag = make_bag(7);
    println(b.n);
    println(len(b.items));
    return 0;
}
""",
     "2\n2\n"),
    ("concrete-call control (still clean)",
     BAG_DEFS + """fn main() -> int {
    let c: Bag = make_bag_concrete(7);
    println(c.n);
    println(len(c.items));
    return 0;
}
""",
     "2\n2\n"),
    ("generic struct WITHOUT an array field",
     """struct Point {
    x: int,
    y: int,
}

fn make_point<T>(seed: T) -> Point {
    return Point { x: 3, y: 4 };
}

fn main() -> int {
    let p: Point = make_point(7);
    println(p.x);
    println(p.y);
    return 0;
}
""",
     "3\n4\n"),
    ("generic call used inline (not assigned)",
     BAG_DEFS + WORDS_DEF + """fn main() -> int {
    println(make_bag(7).n);
    println(len(make_words(7)));
    return 0;
}
""",
     "2\n2\n"),
    ("generic array return (assigned)",
     WORDS_DEF + """fn main() -> int {
    let w: [str] = make_words(7);
    println(len(w));
    return 0;
}
""",
     "2\n"),
    ("generic lambda return (assigned)",
     """fn make_adder<T>(seed: T) -> fn(int) -> int {
    return fn(x: int) -> int { return x + seed; };
}

fn main() -> int {
    let f: fn(int) -> int = make_adder(10);
    println(f(32));
    return 0;
}
""",
     "42\n"),
]

# (name, program, expected stdout) — run under ASan, both compilers.
ASAN_CASES = [
    ("generic struct repro",
     BAG_DEFS + """fn main() -> int {
    let b: Bag = make_bag(7);
    println(b.n);
    println(len(b.items));
    return 0;
}
""",
     "2\n2\n"),
    ("generic array return",
     WORDS_DEF + """fn main() -> int {
    let w: [str] = make_words(7);
    println(len(w));
    return 0;
}
""",
     "2\n"),
    ("generic lambda return",
     """fn make_adder<T>(seed: T) -> fn(int) -> int {
    return fn(x: int) -> int { return x + seed; };
}

fn main() -> int {
    let f: fn(int) -> int = make_adder(10);
    println(f(32));
    return 0;
}
""",
     "42\n"),
]

# .fg files whose formatting must be idempotent.
FMT_FILES = ("examples/generic_inc_demo.fg",)


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "generic_inc_demo.fg")
    with tempfile.TemporaryDirectory() as td:
        _run_all(td, failures, demo)
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


def _run_all(td, failures, demo):
    for mode, prefix in (("hosted", []), ("python", ["--python"])):
        r = run([sys.executable, os.path.join(ROOT, "forge.py")] + prefix +
                ["run", demo], ROOT)
        if not check(f"demo runs ({mode})", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append(f"demo runs ({mode})")
        elif not check(f"demo results ({mode})", r.stdout == DEMO_EXPECTED,
                       repr(r.stdout)):
            failures.append(f"demo results ({mode})")
    for name, prog, want in OK_CASES:
        p = os.path.join(td, "c.fg")
        with open(p, "w") as f:
            f.write(prog)
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                     prefix + ["run", p], ROOT)
            ok = rr.returncode == 0 and rr.stdout == want
            if not check(f"{name} ({mode})", ok,
                         repr(rr.stdout) + (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(f"{name} ({mode})")
    for name, prog, want in ASAN_CASES:
        p = os.path.join(td, "a.fg")
        with open(p, "w") as f:
            f.write(prog)
        for mode, cmd in (("hosted", [HOSTED, "emit", p]),
                          ("python", [sys.executable, os.path.join(ROOT, "forge.py"),
                                      "--python", "emit", p])):
            c_path = os.path.join(td, "a.c")
            bin_path = os.path.join(td, "a_bin")
            r = run(cmd, ROOT)
            if r.returncode != 0:
                if not check(f"asan {name} ({mode})", False,
                             f"emit rc={r.returncode}: {r.stderr[:200]}"):
                    failures.append(f"asan {name} ({mode}) emit")
                continue
            with open(c_path, "w") as f:
                f.write(r.stdout)
            cc = run(["cc", "-g", "-O1", "-fsanitize=address",
                      "-o", bin_path, c_path, "-lssl", "-lcrypto",
                      "-lm", "-pthread"], ROOT)
            if cc.returncode != 0:
                if not check(f"asan {name} ({mode})", False,
                             f"cc rc={cc.returncode}: {cc.stderr[:200]}"):
                    failures.append(f"asan {name} ({mode}) cc")
                continue
            run_r = run([bin_path], td)
            ok = (run_r.returncode == 0 and run_r.stdout == want
                  and "AddressSanitizer" not in run_r.stderr
                  and "LeakSanitizer" not in run_r.stderr)
            if not check(f"asan {name} ({mode})", ok,
                         f"rc={run_r.returncode} stdout={run_r.stdout!r} "
                         f"stderr={run_r.stderr[-200:]!r}"):
                failures.append(f"asan {name} ({mode})")
    for rel in FMT_FILES:
        target = os.path.join(ROOT, rel)
        rf = run([sys.executable, os.path.join(ROOT, "forge.py"), "fmt", target],
                 ROOT)
        if not check(f"fmt runs ({rel})", rf.returncode == 0, rf.stderr.strip()):
            failures.append(f"fmt runs ({rel})")
        else:
            rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"),
                       "fmt", "--check", target], ROOT)
            if not check(f"fmt idempotent ({rel})", rf2.returncode == 0,
                         rf2.stderr.strip()):
                failures.append(f"fmt idempotent ({rel})")


if __name__ == "__main__":
    sys.exit(main())
