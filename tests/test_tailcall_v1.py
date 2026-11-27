#!/usr/bin/env python3
"""Own test for Top-500 #78 (tail-call guarantee).

The guarantee (DESIGN.md §3): every call in tail position runs in
constant stack space on native. The behaviour is gcc's sibling-call
optimisation; this test pins it two ways: depth runs on built
binaries under a 64 KB stack (F5-A), and the objdump assertion (0
recursive call sites in a self-tail fn).

Structure (mirrors test_nestedfn_v1.py's harness, but the depth
cases build binaries and run them DIRECTLY — never via `forge.py
run` until F6 lands, because `run` used to give programs a 64 MB
stack):
- OK_CASES: shallow correctness for every shape, via `forge.py run`
  (both compilers). Each depth shape has a shallow twin here so the
  ASan gate (asan_78.py) covers every shape's memory behaviour at
  small depth.
- DEPTH_CASES: the same shapes at 10M depth (100k for the string
  arg, which mallocs per call), as BUILT binaries run directly
  under a 64 KB stack (preexec_fn pins RLIMIT_STACK soft to 64 KB).
  Both compilers. rc must be 0 with the exact expected stdout.
- NEG_CONTROL: p2 (non-tail recursion) at 10M as a built binary
  under an 8 MB stack — it MUST segfault (rc -11, empty stdout).
  This is the control that proves the depth test can detect a
  regression: if a codegen change ever broke TCO, a depth case
  would fail exactly this way.
- F6_CASE: p2 at 10M via `forge.py run` (hosted route, parent stack
  pinned to 8 MB) — it MUST segfault exactly as the built binary
  does (rc != 0, empty stdout). This is the F6-A assertion: the
  shim's 64 MB raise no longer leaks into the program.
- OBJDUMP_CASE: the p1 binary (both compilers) must contain ZERO
  recursive call sites in count() — gcc turned it into a loop.
- DUMP_CASES: `check --dump-tail-calls` output must match exactly
  (both compilers). The classifier records return calls, void
  last-statement calls, if/else branches, blocks, match arms, and
  lambda bodies; it records NOTHING for BinOp-wrapped calls,
  let/assign/argument/condition/scrutinee calls, `?`-wrapped calls,
  builtins, or enum-variant constructions.
- BACKEND_CASES: p1 checks clean under --target big32 and --target
  wasm (Python only — the hosted driver is native-only for
  --target). The guarantee is native-only in v1; big32/WASM check
  clean and run, but with growing stacks (documented in the catalog
  entry, not asserted here).

Depth runs are slow under ASan, so asan_78.py runs the OK_CASES
(shallow) only. Run: python3 tests/test_tailcall_v1.py
Exit 0 iff every case passes. Log: logs/test_tailcall.log (when run
via the gate scripts).
"""
import os
import resource
import subprocess
import sys
import tempfile

REPO = os.path.expanduser("~/workspace/forge-v2")
FORGE = os.path.join(REPO, "forge.py")
HOSTED = os.path.join(REPO, "bin", "qasida-hosted")

DEPTH = 10000000
SHALLOW = 100

# ------------------------------------------------------------------
# Programs (depth is a literal so the runner needs no argv).
# ------------------------------------------------------------------

SELF_TAIL = """fn count(n: int, acc: int) -> int {
    if n <= 0 { return acc; }
    return count(n - 1, acc + 1);
}
fn main() -> int {
    println(count(%d, 0));
    return 0;
}
"""

MUTUAL = """fn is_even(n: int) -> bool {
    if n == 0 { return true; }
    return is_odd(n - 1);
}
fn is_odd(n: int) -> bool {
    if n == 0 { return false; }
    return is_even(n - 1);
}
fn main() -> int {
    if is_even(%d) { println("even"); } else { println("odd"); }
    return 0;
}
"""

FNVALUE_ENTRY = """fn count(n: int, acc: int) -> int {
    if n <= 0 { return acc; }
    return count(n - 1, acc + 1);
}
fn apply(f: fn(int, int) -> int, n: int, acc: int) -> int {
    return f(n, acc);
}
fn main() -> int {
    println(apply(count, %d, 0));
    return 0;
}
"""

STATE_MACHINE = """fn idle(steps: int) -> int {
    if steps <= 0 { return 0; }
    return work(steps - 1);
}
fn work(steps: int) -> int {
    if steps <= 0 { return 1; }
    return done(steps - 1);
}
fn done(steps: int) -> int {
    if steps <= 0 { return 2; }
    return idle(steps - 1);
}
fn main() -> int {
    println(idle(%d));
    return 0;
}
"""

MATCH_ARMS = """enum State { A, B, C }
fn step(s: State, n: int) -> int {
    if n <= 0 {
        match s {
            A => { return 0; }
            B => { return 1; }
            _ => { return 2; }
        }
        return -1;
    }
    match s {
        A => { return step(B, n - 1); }
        B => { return step(C, n - 1); }
        _ => { return step(A, n - 1); }
    }
    return -1;
}
fn main() -> int {
    println(step(A, %d));
    return 0;
}
"""

CROSS_FN = """fn count(n: int, acc: int) -> int {
    if n <= 0 { return acc; }
    return count(n - 1, acc + 1);
}
fn start(n: int) -> int {
    return count(n, 0);
}
fn main() -> int {
    println(start(%d));
    return 0;
}
"""

STRING_ARG = """fn repeat(s: str, n: int, acc: int) -> int {
    if n <= 0 { return acc; }
    return repeat(s, n - 1, acc + len(s));
}
fn main() -> int {
    println(repeat("abc", %d, 0));
    return 0;
}
"""

NESTEDFN_TAIL = """fn count(n: int, acc: int) -> int {
    if n <= 0 { return acc; }
    return count(n - 1, acc + 1);
}
fn main() -> int {
    fn step(m: int) -> int {
        return count(m, 0);
    }
    println(step(%d));
    return 0;
}
"""

VOID_TAIL = """fn tick(n: int) -> void {
    if n <= 0 { return; }
    tick(n - 1);
}
fn main() -> int {
    tick(%d);
    println("done");
    return 0;
}
"""

FREES_SELF = """fn count(n: int, acc: int) -> int {
    if n <= 0 { return acc; }
    let s: str = "abc";
    return count(n - 1, acc + len(s));
}
fn main() -> int {
    println(count(%d, 0));
    return 0;
}
"""

FREES_ARG = """fn repeat(s: str, n: int, acc: int) -> int {
    if n <= 0 { return acc; }
    return repeat(s, n - 1, acc + len(s));
}
fn main() -> int {
    println(repeat("abc", %d, 0));
    return 0;
}
"""

INDIRECT_MUTUAL = """fn even(n: int) -> str {
    if n == 0 { return "even"; }
    let f: fn(int) -> str = odd;
    return f(n - 1);
}
fn odd(n: int) -> str {
    if n == 0 { return "odd"; }
    let f: fn(int) -> str = even;
    return f(n - 1);
}
fn main() -> int {
    println(even(%d));
    return 0;
}
"""

# Generic tail call: the recursive call is a generic instantiation
# (T=str here) and the frame holds an owned string local, so the
# Return temp-split must fire in BOTH compilers — Python via the
# mangled name, hosted via the replicated template resolution.
# Pins the generic parity (the v78 split handles generic calls in
# both compilers, unlike the original plan to exclude them).
GENERIC_TAIL = """fn gtail<T>(n: int, acc: int, x: T) -> int {
    if n <= 0 {
        return acc;
    }
    let s: str = "abc";
    return gtail(n - 1, acc + len(s), x);
}
fn main() -> int {
    println(gtail(%d, 0, "seed"));
    return 0;
}
"""

NONTAIL = """fn bad(n: int) -> int {
    if n <= 0 { return 0; }
    return 1 + bad(n - 1);
}
fn main() -> int {
    println(bad(%d));
    return 0;
}
"""

DUMP_PROG = """fn count(n: int, acc: int) -> int {
    if n <= 0 {
        return acc;
    }
    return count(n - 1, acc + 1);
}
fn bad(n: int) -> int {
    if n <= 0 {
        return 0;
    }
    return 1 + bad(n - 1);
}
fn helper() -> int {
    return count(5, 0);
}
fn do_work() -> void {
    count(5, 0);
}
enum Color { Red, Green }
fn pick(c: Color) -> int {
    match c {
        Red => { return count(3, 0); }
        Green => { return 7; }
    }
    return -1;
}
fn use_let() -> int {
    let x: int = count(5, 0);
    return x;
}
fn main() -> int {
    println(count(10, 0));
    println(bad(3));
    println(helper());
    do_work();
    println(pick(Red));
    println(use_let());
    return 0;
}
"""

# Expected dump lines for DUMP_PROG (line:col of each tail call).
DUMP_EXPECTED = [
    "tail call: fn count 5:12 count",
    "tail call: fn helper 14:12 count",
    "tail call: fn do_work 17:5 count",
    "tail call: fn pick 22:25 count",
]

# (name, program_template, expected_stdout, mode)
# Shallow twins of every depth shape (depth = SHALLOW), run via
# `forge.py run` under both compilers. Expected outputs are the
# SHALLOW-depth values.
OK_CASES = [
    ("self_tail", SELF_TAIL % SHALLOW, "%d\n" % SHALLOW, "safe"),
    ("mutual", MUTUAL % SHALLOW, "even\n", "safe"),
    ("fnvalue_entry", FNVALUE_ENTRY % SHALLOW, "%d\n" % SHALLOW, "safe"),
    ("state_machine", STATE_MACHINE % 10, "1\n", "safe"),
    ("match_arms", MATCH_ARMS % 10, "1\n", "safe"),
    ("cross_fn", CROSS_FN % SHALLOW, "%d\n" % SHALLOW, "safe"),
    ("string_arg", STRING_ARG % SHALLOW, "%d\n" % (3 * SHALLOW), "safe"),
    ("nestedfn_tail", NESTEDFN_TAIL % SHALLOW, "%d\n" % SHALLOW, "safe"),
    ("void_tail", VOID_TAIL % SHALLOW, "done\n", "safe"),
    ("frees_self", FREES_SELF % SHALLOW, "%d\n" % (3 * SHALLOW), "safe"),
    ("frees_arg", FREES_ARG % SHALLOW, "%d\n" % (3 * SHALLOW), "safe"),
    ("indirect_mutual", INDIRECT_MUTUAL % SHALLOW, "even\n", "safe"),
    ("generic_tail", GENERIC_TAIL % SHALLOW, "%d\n" % (3 * SHALLOW), "safe"),
    ("fast_mode", SELF_TAIL % SHALLOW, "%d\n" % SHALLOW, "fast"),
]

# (name, program, expected_stdout, mode, stack_kb)
# Depth runs: built binaries, run directly under a 64 KB stack.
# string_arg runs at 100k (it mallocs per call; 10M is the same
# shape, just slower). idle(10M): 10M mod 3 == 1. step(A, 10M):
# 10M mod 3 == 1 -> state B -> 1.
DEPTH_CASES = [
    ("self_tail", SELF_TAIL % DEPTH, "%d\n" % DEPTH, "safe", 64),
    ("mutual", MUTUAL % DEPTH, "even\n", "safe", 64),
    ("fnvalue_entry", FNVALUE_ENTRY % DEPTH, "%d\n" % DEPTH, "safe", 64),
    ("state_machine", STATE_MACHINE % DEPTH, "1\n", "safe", 64),
    ("match_arms", MATCH_ARMS % DEPTH, "1\n", "safe", 64),
    ("cross_fn", CROSS_FN % DEPTH, "%d\n" % DEPTH, "safe", 64),
    ("string_arg", STRING_ARG % 100000, "300000\n", "safe", 64),
    ("nestedfn_tail", NESTEDFN_TAIL % DEPTH, "%d\n" % DEPTH, "safe", 64),
    ("void_tail", VOID_TAIL % DEPTH, "done\n", "safe", 64),
    ("frees_self", FREES_SELF % DEPTH, "%d\n" % (3 * DEPTH), "safe", 64),
    ("frees_arg", FREES_ARG % DEPTH, "%d\n" % (3 * DEPTH), "safe", 64),
    ("indirect_mutual", INDIRECT_MUTUAL % DEPTH, "even\n", "safe", 64),
    ("generic_tail", GENERIC_TAIL % DEPTH, "%d\n" % (3 * DEPTH), "safe", 64),
    ("fast_mode", SELF_TAIL % DEPTH, "%d\n" % DEPTH, "fast", 64),
]

# (name, program, target) — check clean (Python only; the hosted
# driver is native-only for --target). The guarantee is native-only
# in v1; big32/WASM check clean and run, but with growing stacks.
BACKEND_CASES = [
    ("big32_check", SELF_TAIL % SHALLOW, "big32"),
    ("wasm_check", SELF_TAIL % SHALLOW, "wasm"),
]


def _clear_cache():
    subprocess.run(["rm", "-rf", "/tmp/qasida_cache"],
                   capture_output=True)


def _stack_pin(kb):
    """preexec_fn: pin the child's RLIMIT_STACK soft limit to kb
    KB (hard limit untouched)."""
    def _pin():
        _soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
        resource.setrlimit(resource.RLIMIT_STACK, (kb * 1024, hard))
    return _pin


def _run(cmd, cwd, stack_kb=None):
    kw = {}
    if stack_kb is not None:
        kw["preexec_fn"] = _stack_pin(stack_kb)
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=600, **kw)


def _write_prog(tmpdir, name, program):
    path = os.path.join(tmpdir, name + ".fg")
    with open(path, "w") as f:
        f.write(program)
    return path


def _build(prog_path, out_path, compiler, mode):
    """Build prog_path with the given compiler ('hosted' or
    'python'); returns (rc, stderr)."""
    _clear_cache()
    cmd = ["python3", FORGE]
    if compiler == "python":
        cmd.append("--python")
    cmd += ["build", "--mode", mode, prog_path, "-o", out_path]
    r = _run(cmd, REPO)
    return r.returncode, r.stderr


def _objdump_recursive_calls(bin_path, fn_name):
    """Count `call` sites targeting <fn_name> inside fn_name's own
    objdump block. Returns the count, or -1 when objdump fails."""
    r = subprocess.run(["objdump", "-d", bin_path], capture_output=True,
                       text=True, timeout=120)
    if r.returncode != 0:
        return -1
    lines = r.stdout.splitlines()
    in_fn = False
    count = 0
    for line in lines:
        if "<%s>:" % fn_name in line:
            in_fn = True
            continue
        if in_fn:
            if line.strip() == "":
                break
            if "call" in line and "<%s>" % fn_name in line:
                count += 1
    return count


def main():
    failures = []
    total = 0

    def check(name, ok, detail=""):
        nonlocal total
        total += 1
        if ok:
            print("PASS %s" % name)
        else:
            print("FAIL %s %s" % (name, detail))
            failures.append(name)

    with tempfile.TemporaryDirectory(prefix="tc78_test_") as tmpdir:
        # --- OK cases (shallow, via forge.py run, both compilers) ---
        for name, program, expected, mode in OK_CASES:
            for compiler in ("hosted", "python"):
                prog = _write_prog(tmpdir, "ok_" + name, program)
                _clear_cache()
                cmd = ["python3", FORGE]
                if compiler == "python":
                    cmd.append("--python")
                cmd += ["run", "--mode", mode, prog]
                try:
                    r = _run(cmd, REPO)
                except subprocess.TimeoutExpired:
                    check("ok/%s/%s" % (name, compiler), False,
                          "(timeout)")
                    continue
                check("ok/%s/%s" % (name, compiler),
                      r.returncode == 0 and r.stdout == expected,
                      "(rc=%s stdout=%r expected=%r stderr=%r)"
                      % (r.returncode, r.stdout, expected,
                         r.stderr[-300:]))

        # --- Depth cases (built binaries, 64 KB stack) ---
        for name, program, expected, mode, stack_kb in DEPTH_CASES:
            for compiler in ("hosted", "python"):
                prog = _write_prog(tmpdir, "depth_" + name, program)
                out = os.path.join(tmpdir, "bin_%s_%s" % (name, compiler))
                rc, err = _build(prog, out, compiler, mode)
                if rc != 0:
                    check("depth/%s/%s" % (name, compiler), False,
                          "(build rc=%s stderr=%r)" % (rc, err[-300:]))
                    continue
                try:
                    r = _run([out], tmpdir, stack_kb=stack_kb)
                except subprocess.TimeoutExpired:
                    check("depth/%s/%s" % (name, compiler), False,
                          "(timeout)")
                    continue
                check("depth/%s/%s" % (name, compiler),
                      r.returncode == 0 and r.stdout == expected,
                      "(rc=%s stdout=%r expected=%r stderr=%r)"
                      % (r.returncode, r.stdout, expected,
                         r.stderr[-300:]))

        # --- Negative control: p2 at 10M, built binary, 8 MB stack ---
        for compiler in ("hosted", "python"):
            prog = _write_prog(tmpdir, "neg_p2", NONTAIL % DEPTH)
            out = os.path.join(tmpdir, "bin_neg_%s" % compiler)
            rc, err = _build(prog, out, compiler, "safe")
            if rc != 0:
                check("neg/%s" % compiler, False,
                      "(build rc=%s stderr=%r)" % (rc, err[-300:]))
                continue
            r = _run([out], tmpdir, stack_kb=8 * 1024)
            check("neg/%s" % compiler,
                  r.returncode == -11 and r.stdout == "",
                  "(expected SIGSEGV rc=-11 with no output, got "
                  "rc=%s stdout=%r)" % (r.returncode, r.stdout))

        # --- F6: p2 at 10M via `forge.py run` (hosted route) ---
        # The parent stack is pinned to 8 MB so the assertion holds
        # no matter what stack this test process itself runs under:
        # the shim raises to 64 MB for the compiler, then the driver
        # must reset the program to 8 MB — and p2 must segfault.
        prog = _write_prog(tmpdir, "f6_p2", NONTAIL % DEPTH)
        _clear_cache()
        try:
            r = _run(["python3", FORGE, "run", prog], REPO,
                     stack_kb=8 * 1024)
        except subprocess.TimeoutExpired:
            check("f6/hosted_run", False, "(timeout)")
            r = None
        if r is not None:
            check("f6/hosted_run",
                  r.returncode != 0 and r.stdout == "",
                  "(expected a segfault with no output, got rc=%s "
                  "stdout=%r stderr=%r)"
                  % (r.returncode, r.stdout, r.stderr[-300:]))
        # The Python route never raised the stack, so it must
        # segfault identically.
        _clear_cache()
        try:
            r = _run(["python3", FORGE, "--python", "run", prog], REPO,
                     stack_kb=8 * 1024)
        except subprocess.TimeoutExpired:
            check("f6/python_run", False, "(timeout)")
            r = None
        if r is not None:
            check("f6/python_run",
                  r.returncode != 0 and r.stdout == "",
                  "(expected a segfault with no output, got rc=%s "
                  "stdout=%r stderr=%r)"
                  % (r.returncode, r.stdout, r.stderr[-300:]))

        # --- Objdump: 0 recursive call sites in count() ---
        for compiler in ("hosted", "python"):
            prog = _write_prog(tmpdir, "obj_p1", SELF_TAIL % DEPTH)
            out = os.path.join(tmpdir, "bin_obj_%s" % compiler)
            rc, err = _build(prog, out, compiler, "safe")
            if rc != 0:
                check("objdump/%s" % compiler, False,
                      "(build rc=%s stderr=%r)" % (rc, err[-300:]))
                continue
            n = _objdump_recursive_calls(out, "count")
            check("objdump/%s" % compiler, n == 0,
                  "(expected 0 recursive call sites, got %s)" % n)

        # --- Dump cases: check --dump-tail-calls ---
        prog = _write_prog(tmpdir, "dump_prog", DUMP_PROG)
        for compiler in ("hosted", "python"):
            _clear_cache()
            cmd = ["python3", FORGE]
            if compiler == "python":
                cmd.append("--python")
            cmd += ["check", "--dump-tail-calls", prog]
            r = _run(cmd, REPO)
            got = [ln for ln in r.stderr.splitlines()
                   if ln.startswith("tail call:")]
            check("dump/%s" % compiler,
                  r.returncode == 0 and got == DUMP_EXPECTED,
                  "(rc=%s got=%r expected=%r)"
                  % (r.returncode, got, DUMP_EXPECTED))

        # --- Backend cases: check clean under big32/wasm (Python) ---
        for name, program, target in BACKEND_CASES:
            prog = _write_prog(tmpdir, "backend_" + name, program)
            _clear_cache()
            r = _run(["python3", FORGE, "--python", "check",
                      "--target", target, prog], REPO)
            check("backend/%s" % name,
                  r.returncode == 0 and r.stdout.strip() == "ok: no errors",
                  "(rc=%s stdout=%r stderr=%r)"
                  % (r.returncode, r.stdout, r.stderr[-300:]))

    print("tailcall: %d/%d PASS"
          % (total - len(failures), total))
    if failures:
        print("FAILURES: %s" % ", ".join(failures))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
