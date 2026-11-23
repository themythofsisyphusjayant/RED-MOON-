"""Top-500 #50: inferred error sets (tests/test_errsets_v1.py).

Option A: for every function returning Result<T, E> where E is an
enum, the checker computes the set of E-variants it can produce
(own literal Err-returns, `?`-propagated callee sets, directly
returned callee Results, enum-typed locals), by a second pass with
a worklist fixpoint over the call graph. A match on a value with a
known inferred set is exhaustive over that set, not the whole
enum. Sets are compile-time only and erased at runtime: no codegen
change, no new syntax. Extra match arms are permitted (backward
compatible). The set is always an over-approximation; anything
unprovable widens to TOP (the full enum), never to empty. Empty
means "provably never returns an error" (a function that only
ever fail()s has an empty error-set; a match on an empty set needs
zero arms). Both compilers (Python + hosted).

Two deliberate asymmetries (recorded, not bugs):
- The Python checker records pending matches in phase 1 and
  verdicts them after the fixpoint; the hosted checker RE-DERIVES
  the verdict in the second-pass walk (a record pushed on the
  checker after the arm loop would be lost — join_moved rebuilds
  from a snapshot of `before`). Both verdict logics are identical
  (missing = variants - seen, same message format).
- Generic calls: Python narrows per-instantiation (it rewrites
  generic call names to mangled instantiation names and checks
  the instantiated bodies); the hosted checker never checks
  generic template bodies, so a generic call's summary is TOP in
  hosted (ES-C4). The generic case below asserts exactly that
  split.
- The `?` E-mismatch case is a PRE-EXISTING hosted divergence
  (not this slice's to fix): Python rejects a `?` whose error
  type does not match the enclosing return type; the hosted
  checker accepts it. This slice's walker handles the accepted
  case soundly (the mismatched `?` widens the accumulator to
  TOP), and the test asserts both behaviours per-mode.
- The hosted TOP-case match message is bare ("match is not
  exhaustive", no missing list) — its own pre-slice message,
  preserved exactly. Python's TOP-case message carries the
  sorted missing list. The narrowed-case message carries the
  list in BOTH compilers.
- The struct-field widening rule is asserted under hosted only:
  the Python checker rejects enum-typed (and Result-typed)
  struct fields ("unknown field type"), a pre-existing Python
  limitation. The array-element case covers the same ES-C4
  widening rule under both compilers.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO_EXPECTED = """not found
timed out
42
"""

DEMO_DUMP_LINES = [
    "fn read_maybe -> Result<_, ErrCode>: {NotFound, TimedOut}",
    "fn caller -> Result<_, ErrCode>: {NotFound, TimedOut}",
]

FULL_SET_LINE = ("fn from_code -> Result<_, ErrCode>: {Success, NotFound, "
                 "PermissionDenied, AlreadyExists, IsADirectory, NotADirectory, "
                 "InvalidArgument, Interrupted, NoSpace, ReadOnlyFs, TooManyOpen, "
                 "BrokenPipe, ConnectionRefused, TimedOut, Unknown}")

TWO_ERRS = r"""import "result.fg";
import "errcode.fg";

fn two_errs(x: int) -> Result<int, ErrCode> {
    if x == 0 {
        return Result { ok: false, value: 0, error: NotFound };
    }
    return Result { ok: false, value: 0, error: TimedOut };
}
"""

# Cross-file helper (helper.fg in the temp dir): the caller in the
# main file infers the set across the file boundary (unlike #48's
# try_call boundary, which is a different file by definition).
HELPER_SRC = r"""import "result.fg";
import "errcode.fg";

fn helper_two(x: int) -> Result<int, ErrCode> {
    if x == 0 {
        return Result { ok: false, value: 0, error: NotFound };
    }
    return Result { ok: false, value: 0, error: TimedOut };
}
"""

# (name, program, dump lines that must be present, dump lines that
# must be absent). Run as `check --dump-error-sets`; rc must be 0.
DUMP_CASES = [
    ("1 literal two-variant set",
     TWO_ERRS + r"""
fn main() -> int {
    return 0;
}
""",
     ["fn two_errs -> Result<_, ErrCode>: {NotFound, TimedOut}"],
     []),
    ("2 ?-propagation",
     TWO_ERRS + r"""
fn caller(x: int) -> Result<int, ErrCode> {
    let v: int = two_errs(x)?;
    return Result { ok: true, value: v, error: Success };
}

fn main() -> int {
    return 0;
}
""",
     ["fn caller -> Result<_, ErrCode>: {NotFound, TimedOut}"],
     []),
    ("3 direct return",
     TWO_ERRS + r"""
fn direct(x: int) -> Result<int, ErrCode> {
    return two_errs(x);
}

fn main() -> int {
    return 0;
}
""",
     ["fn direct -> Result<_, ErrCode>: {NotFound, TimedOut}"],
     []),
    ("4 local set",
     TWO_ERRS + r"""
fn via_local(x: int) -> Result<int, ErrCode> {
    let r: Result<int, ErrCode> = two_errs(x);
    return r;
}

fn main() -> int {
    return 0;
}
""",
     ["fn via_local -> Result<_, ErrCode>: {NotFound, TimedOut}"],
     []),
    ("5 empty set",
     TWO_ERRS + r"""
fn fail_only(x: int) -> Result<int, ErrCode> {
    fail("always");
    return Result { ok: true, value: 0, error: Success };
}

fn main() -> int {
    return 0;
}
""",
     ["fn fail_only -> Result<_, ErrCode>: {}"],
     []),
    ("6 bare enum value-set",
     TWO_ERRS + r"""
fn code_of(x: int) -> ErrCode {
    if x == 0 {
        return NotFound;
    }
    return TimedOut;
}

fn main() -> int {
    return 0;
}
""",
     ["fn code_of -> ErrCode: {NotFound, TimedOut}"],
     []),
    ("7 direct recursion",
     TWO_ERRS + r"""
fn rec(n: int) -> Result<int, ErrCode> {
    if n <= 0 {
        return Result { ok: false, value: 0, error: NotFound };
    }
    let r: Result<int, ErrCode> = rec(n - 1);
    if !r.ok {
        return r;
    }
    return Result { ok: true, value: r.value + 1, error: Success };
}

fn main() -> int {
    return 0;
}
""",
     ["fn rec -> Result<_, ErrCode>: {NotFound}"],
     []),
    ("8 mutual recursion",
     TWO_ERRS + r"""
fn f(n: int) -> Result<int, ErrCode> {
    if n <= 0 {
        return Result { ok: false, value: 0, error: NotFound };
    }
    return g(n - 1);
}

fn g(n: int) -> Result<int, ErrCode> {
    if n <= 0 {
        return Result { ok: false, value: 0, error: TimedOut };
    }
    return f(n - 1);
}

fn main() -> int {
    return 0;
}
""",
     ["fn f -> Result<_, ErrCode>: {NotFound, TimedOut}",
      "fn g -> Result<_, ErrCode>: {NotFound, TimedOut}"],
     []),
    ("9 computed error via err_from_code (full set)",
     TWO_ERRS + r"""
fn from_code(x: int) -> Result<int, ErrCode> {
    return Result { ok: false, value: 0, error: err_from_code(x) };
}

fn main() -> int {
    return 0;
}
""",
     [FULL_SET_LINE],
     []),
    ("10 param error -> TOP",
     TWO_ERRS + r"""
fn from_param(e: ErrCode) -> Result<int, ErrCode> {
    return Result { ok: false, value: 0, error: e };
}

fn main() -> int {
    return 0;
}
""",
     ["fn from_param -> Result<_, ErrCode>: TOP"],
     []),
    ("11 array-element flow -> TOP",
     TWO_ERRS + r"""
fn via_index(x: int) -> Result<int, ErrCode> {
    let arr: [ErrCode] = [NotFound, TimedOut];
    return Result { ok: false, value: 0, error: arr[0] };
}

fn main() -> int {
    return 0;
}
""",
     ["fn via_index -> Result<_, ErrCode>: TOP"],
     []),
    ("12 indirect call -> TOP",
     TWO_ERRS + r"""
fn via_fn(f: fn(int) -> Result<int, ErrCode>, x: int) -> Result<int, ErrCode> {
    return f(x);
}

fn main() -> int {
    return 0;
}
""",
     ["fn via_fn -> Result<_, ErrCode>: TOP"],
     []),
    ("13 extern -> TOP",
     TWO_ERRS + r"""
extern fn ext_read(x: int) -> Result<int, ErrCode>;

fn via_extern(x: int) -> Result<int, ErrCode> {
    return ext_read(x);
}

fn main() -> int {
    return 0;
}
""",
     ["fn via_extern -> Result<_, ErrCode>: TOP"],
     []),
    ("14 reassignment unions",
     TWO_ERRS + r"""
fn only_nf(x: int) -> Result<int, ErrCode> {
    return Result { ok: false, value: 0, error: NotFound };
}

fn only_to(x: int) -> Result<int, ErrCode> {
    return Result { ok: false, value: 0, error: TimedOut };
}

fn unioned(x: int) -> Result<int, ErrCode> {
    let mut r: Result<int, ErrCode> = only_nf(x);
    if x == 1 {
        r = only_to(x);
    }
    return r;
}

fn main() -> int {
    return 0;
}
""",
     ["fn only_nf -> Result<_, ErrCode>: {NotFound}",
      "fn only_to -> Result<_, ErrCode>: {TimedOut}",
      "fn unioned -> Result<_, ErrCode>: {NotFound, TimedOut}"],
     []),
    ("15 non-enum E has no dump line",
     r"""import "result.fg";

fn str_err(x: int) -> Result<int, str> {
    if x == 0 {
        return Result { ok: false, value: 0, error: "nope" };
    }
    return Result { ok: true, value: x, error: "" };
}

fn main() -> int {
    return 0;
}
""",
     [],
     ["fn str_err"]),
]

# Hosted-only dump cases (same shape as DUMP_CASES, run under
# hosted only). The struct-field flow needs an enum-typed struct
# field, which the PYTHON checker rejects ("unknown field type
# 'ErrCode' in struct 'Holder'") — a pre-existing Python
# limitation, not a #50 issue: Python's struct field validation
# (checker.py valid_type) does not accept enum types (or Result
# types) as field types, while the hosted checker accepts them.
# The array-element case above covers the same ES-C4 widening
# rule under both compilers.
HOSTED_ONLY_DUMP_CASES = [
    ("11b struct-field flow -> TOP (hosted only)",
     TWO_ERRS + r"""
struct Holder { e: ErrCode; }

fn via_field(x: int) -> Result<int, ErrCode> {
    let h: Holder = Holder { e: NotFound };
    return Result { ok: false, value: 0, error: h.e };
}

fn main() -> int {
    return 0;
}
""",
     ["fn via_field -> Result<_, ErrCode>: TOP"],
     []),
]

# (name, program, expected stdout). Run; rc must be 0 and stdout
# must match exactly.
OK_CASES = [
    ("16 narrowed match runs",
     TWO_ERRS + r"""
fn caller(x: int) -> Result<int, ErrCode> {
    let v: int = two_errs(x)?;
    return Result { ok: true, value: v, error: Success };
}

fn main() -> int {
    let r: Result<int, ErrCode> = caller(0);
    if !r.ok {
        match r.error {
            NotFound => { println("nf"); },
            TimedOut => { println("to"); },
        }
    }
    return 0;
}
""",
     "nf\n"),
    ("17 extra arms permitted",
     TWO_ERRS + r"""
fn main() -> int {
    let r: Result<int, ErrCode> = two_errs(0);
    if !r.ok {
        match r.error {
            NotFound => { println("nf"); },
            TimedOut => { println("to"); },
            PermissionDenied => { println("pd"); },
            AlreadyExists => { println("ae"); },
            IsADirectory => { println("iad"); },
            NotADirectory => { println("nad"); },
            InvalidArgument => { println("ia"); },
            Interrupted => { println("in"); },
            NoSpace => { println("ns"); },
            ReadOnlyFs => { println("ro"); },
            TooManyOpen => { println("tmo"); },
            BrokenPipe => { println("bp"); },
            ConnectionRefused => { println("cr"); },
            Success => { println("ok"); },
            Unknown => { println("unk"); },
        }
    }
    return 0;
}
""",
     "nf\n"),
    ("18 wildcard",
     TWO_ERRS + r"""
fn main() -> int {
    let r: Result<int, ErrCode> = two_errs(0);
    if !r.ok {
        match r.error {
            NotFound => { println("nf"); },
            _ => { println("other"); },
        }
    }
    return 0;
}
""",
     "nf\n"),
    ("19 empty set zero-arm match",
     TWO_ERRS + r"""
fn fail_only(x: int) -> Result<int, ErrCode> {
    if x == 0 {
        fail("boom");
    }
    return Result { ok: true, value: x, error: Success };
}

fn main() -> int {
    let r: Result<int, ErrCode> = fail_only(1);
    if !r.ok {
        match r.error {
        }
    }
    println("done");
    return 0;
}
""",
     "done\n"),
    ("20 non-enum E runs",
     r"""import "result.fg";

fn str_err(x: int) -> Result<int, str> {
    if x == 0 {
        return Result { ok: false, value: 0, error: "nope" };
    }
    return Result { ok: true, value: x, error: "" };
}

fn main() -> int {
    let r: Result<int, str> = str_err(21);
    if r.ok {
        println(r.value);
    } else {
        println(r.error);
    }
    return 0;
}
""",
     "21\n"),
    ("21 recursion runs",
     TWO_ERRS + r"""
fn rec(n: int) -> Result<int, ErrCode> {
    if n <= 0 {
        return Result { ok: false, value: 0, error: NotFound };
    }
    let r: Result<int, ErrCode> = rec(n - 1);
    if !r.ok {
        return r;
    }
    return Result { ok: true, value: r.value + 1, error: Success };
}

fn main() -> int {
    let r: Result<int, ErrCode> = rec(2);
    if !r.ok {
        match r.error {
            NotFound => { println("nf"); },
        }
    } else {
        println(r.value);
    }
    return 0;
}
""",
     "nf\n"),
    ("22 mutual recursion runs",
     TWO_ERRS + r"""
fn f(n: int) -> Result<int, ErrCode> {
    if n <= 0 {
        return Result { ok: false, value: 0, error: NotFound };
    }
    return g(n - 1);
}

fn g(n: int) -> Result<int, ErrCode> {
    if n <= 0 {
        return Result { ok: false, value: 0, error: TimedOut };
    }
    return f(n - 1);
}

fn main() -> int {
    let r: Result<int, ErrCode> = f(1);
    if !r.ok {
        match r.error {
            NotFound => { println("nf"); },
            TimedOut => { println("to"); },
        }
    }
    return 0;
}
""",
     "to\n"),
    ("23 bare enum narrowed match runs",
     TWO_ERRS + r"""
fn code_of(x: int) -> ErrCode {
    if x == 0 {
        return NotFound;
    }
    return TimedOut;
}

fn main() -> int {
    let e: ErrCode = code_of(0);
    match e {
        NotFound => { println("nf"); },
        TimedOut => { println("to"); },
    }
    return 0;
}
""",
     "nf\n"),
    ("24 generic with wildcard runs",
     TWO_ERRS + r"""
fn get_err<T>(x: T) -> Result<T, ErrCode> {
    return Result { ok: false, value: x, error: NotFound };
}

fn caller(x: int) -> Result<int, ErrCode> {
    return get_err(x);
}

fn main() -> int {
    let r: Result<int, ErrCode> = caller(1);
    if !r.ok {
        match r.error {
            _ => { println("wild"); },
        }
    }
    return 0;
}
""",
     "wild\n"),
    ("25 local reassignment runs",
     TWO_ERRS + r"""
fn only_nf(x: int) -> Result<int, ErrCode> {
    return Result { ok: false, value: 0, error: NotFound };
}

fn only_to(x: int) -> Result<int, ErrCode> {
    return Result { ok: false, value: 0, error: TimedOut };
}

fn unioned(x: int) -> Result<int, ErrCode> {
    let mut r: Result<int, ErrCode> = only_nf(x);
    if x == 1 {
        r = only_to(x);
    }
    return r;
}

fn main() -> int {
    let r: Result<int, ErrCode> = unioned(1);
    if !r.ok {
        match r.error {
            NotFound => { println("nf"); },
            TimedOut => { println("to"); },
        }
    }
    return 0;
}
""",
     "to\n"),
]

# (name, program, fragment that must appear in stderr). Run; rc
# must be non-zero. The fragment is shared by both compilers
# (each compiler's own message contains it).
REJECT_CASES = [
    ("26 missing arm in the set",
     TWO_ERRS + r"""
fn main() -> int {
    let r: Result<int, ErrCode> = two_errs(0);
    if !r.ok {
        match r.error {
            NotFound => { println("nf"); },
        }
    }
    return 0;
}
""",
     "match is not exhaustive; missing: TimedOut"),
    ("27 missing arm in a value-set",
     TWO_ERRS + r"""
fn code_of(x: int) -> ErrCode {
    if x == 0 {
        return NotFound;
    }
    return TimedOut;
}

fn main() -> int {
    let e: ErrCode = code_of(0);
    match e {
        NotFound => { println("nf"); },
    }
    return 0;
}
""",
     "match is not exhaustive; missing: TimedOut"),
    ("28 union match not exhaustive (phase-1 verdict intact)",
     r"""
fn f(x: int | str) -> int {
    match x {
        int(v) => { return v; },
    }
    return 0;
}

fn main() -> int {
    return f(1);
}
""",
     "match is not exhaustive"),
]

# TOP scrutinee (error from a parameter): the reject message is
# per-compiler — Python carries the sorted missing list, hosted
# keeps its bare pre-slice message. Asserted separately below.
TOP_PROG = TWO_ERRS + r"""
fn from_param(e: ErrCode) -> Result<int, ErrCode> {
    return Result { ok: false, value: 0, error: e };
}

fn main() -> int {
    let r: Result<int, ErrCode> = from_param(NotFound);
    if !r.ok {
        match r.error {
            NotFound => { println("nf"); },
        }
    }
    return 0;
}
"""

# Generic instantiation split: Python narrows per-instantiation
# (and dumps the mangled instantiation); hosted infers TOP for
# the generic call (and has no instantiation line).
GENERIC_PROG = TWO_ERRS + r"""
fn get_err<T>(x: T) -> Result<T, ErrCode> {
    return Result { ok: false, value: x, error: NotFound };
}

fn caller(x: int) -> Result<int, ErrCode> {
    return get_err(x);
}

fn main() -> int {
    let r: Result<int, ErrCode> = caller(1);
    if !r.ok {
        match r.error {
            _ => { println("wild"); },
        }
    }
    return 0;
}
"""

# `?` E-mismatch split (pre-existing hosted divergence): Python
# rejects; hosted accepts and widens the accumulator to TOP.
QMISMATCH_PROG = TWO_ERRS + r"""
enum Other { A, B }

fn f() -> Result<int, Other> {
    let r: Result<int, ErrCode> = Result { ok: false, value: 0, error: NotFound };
    let v: int = r?;
    return Result { ok: true, value: v, error: A };
}

fn main() -> int {
    return 0;
}
"""

# Cross-file inference: the caller lives in the main file, the
# callee in helper.fg.
CROSSFILE_PROG = r"""import "result.fg";
import "errcode.fg";
import "helper.fg";

fn caller(x: int) -> Result<int, ErrCode> {
    return helper_two(x);
}

fn main() -> int {
    let r: Result<int, ErrCode> = caller(0);
    if !r.ok {
        match r.error {
            NotFound => { println("nf"); },
            TimedOut => { println("to"); },
        }
    }
    return 0;
}
"""


def run(args, cwd):
    # Scrub QASIDA_COMPILER: forge.py dispatches on it, so an ambient
    # QASIDA_COMPILER=python (set by the suite's python mode) would
    # silently route the "hosted" invocations below to the Python
    # compiler. The mode is selected by the --python flag alone.
    env = dict(os.environ)
    env.pop("QASIDA_COMPILER", None)
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "errsets_demo.fg")
    for mode, prefix in (("hosted", []), ("python", ["--python"])):
        r = run([sys.executable, os.path.join(ROOT, "forge.py")] + prefix +
                ["run", demo], ROOT)
        if not check(f"demo runs ({mode})", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append(f"demo runs ({mode})")
        elif not check(f"demo results ({mode})", r.stdout == DEMO_EXPECTED,
                       repr(r.stdout)):
            failures.append(f"demo results ({mode})")
        rd = run([sys.executable, os.path.join(ROOT, "forge.py")] + prefix +
                 ["check", "--dump-error-sets", demo], ROOT)
        ok = (rd.returncode == 0 and
              all(line in rd.stderr for line in DEMO_DUMP_LINES))
        if not check(f"demo dump ({mode})", ok, repr(rd.stderr[:200])):
            failures.append(f"demo dump ({mode})")
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, "helper.fg"), "w") as f:
            f.write(HELPER_SRC)
        for name, prog, present, absent in DUMP_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                         prefix + ["check", "--dump-error-sets", p], ROOT)
                ok = (rr.returncode == 0 and
                      all(line in rr.stderr for line in present) and
                      all(line not in rr.stderr for line in absent))
                if not check(f"{name} ({mode})", ok,
                             repr(rr.stderr[:300])):
                    failures.append(f"{name} ({mode})")
        for name, prog, present, absent in HOSTED_ONLY_DUMP_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            rr = run([sys.executable, os.path.join(ROOT, "forge.py"),
                      "check", "--dump-error-sets", p], ROOT)
            ok = (rr.returncode == 0 and
                  all(line in rr.stderr for line in present) and
                  all(line not in rr.stderr for line in absent))
            if not check(f"{name} (hosted)", ok, repr(rr.stderr[:300])):
                failures.append(f"{name} (hosted)")
        for name, prog, want in OK_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                         prefix + ["run", p], ROOT)
                ok = rr.returncode == 0 and rr.stdout == want
                if not check(f"{name} ({mode})", ok,
                             repr(rr.stdout) +
                             (rr.stderr.strip().splitlines() or [""])[-1]):
                    failures.append(f"{name} ({mode})")
        for name, prog, frag in REJECT_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                         prefix + ["run", p], ROOT)
                ok = rr.returncode != 0 and frag in (rr.stderr + rr.stdout)
                if not check(f"{name} ({mode})", ok,
                             (rr.stderr.strip().splitlines() or [""])[-1]):
                    failures.append(f"{name} ({mode})")
        # TOP case, per-compiler messages.
        p = os.path.join(td, "c.fg")
        with open(p, "w") as f:
            f.write(TOP_PROG)
        rr = run([sys.executable, os.path.join(ROOT, "forge.py"),
                  "--python", "run", p], ROOT)
        ok = (rr.returncode != 0 and
              "match is not exhaustive; missing: AlreadyExists" in rr.stderr)
        if not check("29 TOP missing arms, python list", ok,
                     (rr.stderr.strip().splitlines() or [""])[-1]):
            failures.append("29 TOP missing arms, python list")
        rr = run([sys.executable, os.path.join(ROOT, "forge.py"),
                  "run", p], ROOT)
        ok = (rr.returncode != 0 and
              "match is not exhaustive" in rr.stderr and
              "missing:" not in rr.stderr)
        if not check("29 TOP missing arms, hosted bare message", ok,
                     (rr.stderr.strip().splitlines() or [""])[-1]):
            failures.append("29 TOP missing arms, hosted bare message")
        # Generic instantiation split.
        p = os.path.join(td, "c.fg")
        with open(p, "w") as f:
            f.write(GENERIC_PROG)
        rr = run([sys.executable, os.path.join(ROOT, "forge.py"),
                  "--python", "check", "--dump-error-sets", p], ROOT)
        ok = (rr.returncode == 0 and
              "fn caller -> Result<_, ErrCode>: {NotFound}" in rr.stderr and
              "fn get_err_int -> Result<_, ErrCode>: {NotFound}" in rr.stderr)
        if not check("30 generic narrows per-instantiation (python)", ok,
                     repr(rr.stderr[:300])):
            failures.append("30 generic narrows per-instantiation (python)")
        rr = run([sys.executable, os.path.join(ROOT, "forge.py"),
                  "check", "--dump-error-sets", p], ROOT)
        ok = (rr.returncode == 0 and
              "fn caller -> Result<_, ErrCode>: TOP" in rr.stderr and
              "fn get_err_int" not in rr.stderr)
        if not check("30 generic call is TOP, no instantiation (hosted)", ok,
                     repr(rr.stderr[:300])):
            failures.append("30 generic call is TOP, no instantiation (hosted)")
        # `?` E-mismatch split (pre-existing hosted divergence).
        p = os.path.join(td, "c.fg")
        with open(p, "w") as f:
            f.write(QMISMATCH_PROG)
        rr = run([sys.executable, os.path.join(ROOT, "forge.py"),
                  "--python", "check", p], ROOT)
        ok = (rr.returncode != 0 and
              "? error type mismatch" in rr.stderr)
        if not check("31 ? E-mismatch rejected (python)", ok,
                     (rr.stderr.strip().splitlines() or [""])[-1]):
            failures.append("31 ? E-mismatch rejected (python)")
        rr = run([sys.executable, os.path.join(ROOT, "forge.py"),
                  "check", "--dump-error-sets", p], ROOT)
        ok = (rr.returncode == 0 and
              "fn f -> Result<_, Other>: TOP" in rr.stderr)
        if not check("31 ? E-mismatch accepted, widens to TOP (hosted)", ok,
                     repr(rr.stderr[:300])):
            failures.append("31 ? E-mismatch accepted, widens to TOP (hosted)")
        # Cross-file inference (dump + run).
        p = os.path.join(td, "c.fg")
        with open(p, "w") as f:
            f.write(CROSSFILE_PROG)
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                     prefix + ["check", "--dump-error-sets", p], ROOT)
            ok = (rr.returncode == 0 and
                  "fn caller -> Result<_, ErrCode>: {NotFound, TimedOut}"
                  in rr.stderr)
            if not check(f"32 cross-file inference dump ({mode})", ok,
                         repr(rr.stderr[:300])):
                failures.append(f"32 cross-file inference dump ({mode})")
            rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                     prefix + ["run", p], ROOT)
            ok = rr.returncode == 0 and rr.stdout == "nf\n"
            if not check(f"32 cross-file inference runs ({mode})", ok,
                         repr(rr.stdout)):
                failures.append(f"32 cross-file inference runs ({mode})")
    rf = run([sys.executable, os.path.join(ROOT, "forge.py"), "fmt", demo],
             ROOT)
    if not check("fmt runs", rf.returncode == 0, rf.stderr.strip()):
        failures.append("fmt runs")
    else:
        rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"),
                   "fmt", "--check", demo], ROOT)
        if not check("fmt idempotent", rf2.returncode == 0, rf2.stderr.strip()):
            failures.append("fmt idempotent")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
