"""Top-500 #48: try/catch across a module boundary (tests/test_trycatch_v1.py).

try_call(f, ...) guards a call to a FOREIGN function f (defined in a
different .fg file from the caller) and returns Result<R, str>: Ok
with f's return value, or Err(message) when f fail()s. Only fail()
is caught in v1: runtime faults (bounds, overflow, div-by-zero) and
assert stay fatal via forge_fail, untouched. In a --debug build a
caught failure still prints its backtrace; the catch path truncates
the backtrace stack, so a later failure's trace shows only its own
frames. v1 limits (named in the catalog): on the Err path the
callee's owned locals and fresh argument temps leak (the unwind
never runs their frees), and defers in the guarded call do not run
— the defer pin below asserts the defer does NOT run, and the
unwind-leak number is measured by asan_tc.py (recorded, not
asserted zero). Both compilers (Python + hosted).
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO_EXPECTED = """42
helper boom
helper boom
44
helper boom
boundary ok
"""

# Foreign helpers (written to helper.fg in the temp dir): every
# try_call target in the cases below lives here, in a different
# file from the caller. helper2.fg holds the inner target for the
# nesting case (a different file from helper.fg itself).
HELPER_SRC = r"""import "result.fg";
import "helper2.fg";

fn helper_ok(x: int) -> int {
    return x + 1;
}

fn helper_boom(x: int) -> int {
    fail("helper boom");
    return 0;
}

fn helper_deep(x: int) -> int {
    return helper_boom(x);
}

fn helper_deeper(x: int) -> int {
    return helper_deep(x);
}

fn helper_zero() -> int {
    return 7;
}

fn helper_str(x: int) -> str {
    if x == 0 {
        fail("str boom");
    }
    return "hello";
}

fn helper_arr(x: int) -> [int] {
    if x == 0 {
        fail("arr boom");
    }
    return [1, 2, 3];
}

fn note_defer() {
    println("defer ran");
}

fn helper_with_defer(x: int) -> int {
    defer note_defer();
    fail("defer boom");
    return 0;
}

fn outer_guarded(x: int) -> int {
    let r: Result<int, str> = try_call(inner_boom, x);
    if r.ok {
        return r.value;
    }
    fail("outer boom");
    return 0;
}

fn flaky_task(n: int) {
    fail("task boom");
}

fn helper_spawns_task(x: int) -> int {
    scope {
        spawn flaky_task(1);
    }
    return 99;
}

fn helper_oob(x: int) -> int {
    let a: [int] = [1, 2, 3];
    return a[x];
}

fn helper_div(x: int) -> int {
    return 10 / x;
}

fn helper_overflow(x: int) -> int {
    return x + 9223372036854775807;
}

fn helper_assert(x: int) -> int {
    assert(x > 0, "x must be positive");
    return x;
}

fn helper_void(x: int) {
    println("v");
}
"""

HELPER2_SRC = r"""fn inner_boom(x: int) -> int {
    fail("inner boom");
    return 0;
}

fn inner_ok(x: int) -> int {
    return x * 2;
}
"""

# Minimal helper (helper_min.fg): no imports at all, so no file in
# the program imports result.fg. Case 13 (no import) and the
# backend cases (18a/18b) use it: the shared HELPER_SRC imports
# result.fg (so the program-wide Result check would pass) and
# contains a defer (which big32/wasm reject before try_call).
HELPER_MIN_SRC = r"""fn helper_ok(x: int) -> int {
    return x + 1;
}
"""

# (name, caller program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("1 ok path",
     r"""import "result.fg";
import "helper.fg";
fn main() -> int {
    let r: Result<int, str> = try_call(helper_ok, 41);
    if r.ok {
        println(r.value);
    } else {
        println("unexpected err");
    }
    println("after");
    return 0;
}
""",
     """42
after
""",
     ""),
    ("2 err with exact message, program continues",
     r"""import "result.fg";
import "helper.fg";
fn main() -> int {
    let r: Result<int, str> = try_call(helper_boom, 7);
    if r.ok {
        println("unexpected ok");
    } else {
        println(r.error);
    }
    println("after");
    return 0;
}
""",
     """helper boom
after
""",
     ""),
    ("3 fail in foreign helper caught",
     r"""import "result.fg";
import "helper.fg";
fn main() -> int {
    let r: Result<int, str> = try_call(helper_deep, 7);
    if r.ok {
        println("unexpected ok");
    } else {
        println(r.error);
    }
    println("after");
    return 0;
}
""",
     """helper boom
after
""",
     ""),
    ("4 fail in further foreign fn caught",
     r"""import "result.fg";
import "helper.fg";
fn main() -> int {
    let r: Result<int, str> = try_call(helper_deeper, 7);
    if r.ok {
        println("unexpected ok");
    } else {
        println(r.error);
    }
    println("after");
    return 0;
}
""",
     """helper boom
after
""",
     ""),
    ("5 ? propagation",
     r"""import "result.fg";
import "helper.fg";
fn guarded_double(x: int) -> Result<int, str> {
    let r: Result<int, str> = try_call(helper_ok, x);
    let v: int = r?;
    return Result { ok: true, value: v * 2, error: "" };
}
fn guarded_boom(x: int) -> Result<int, str> {
    let r: Result<int, str> = try_call(helper_boom, x);
    let v: int = r?;
    return Result { ok: true, value: v * 2, error: "" };
}
fn main() -> int {
    let d1: Result<int, str> = guarded_double(21);
    if d1.ok {
        println(d1.value);
    } else {
        println("unexpected err");
    }
    let d2: Result<int, str> = guarded_boom(3);
    if d2.ok {
        println("unexpected ok");
    } else {
        println(d2.error);
    }
    return 0;
}
""",
     """44
helper boom
""",
     ""),
    ("6 zero-arg call",
     r"""import "result.fg";
import "helper.fg";
fn main() -> int {
    let r: Result<int, str> = try_call(helper_zero);
    if r.ok {
        println(r.value);
    } else {
        println("unexpected err");
    }
    return 0;
}
""",
     """7
""",
     ""),
    ("7 nested try_call",
     r"""import "result.fg";
import "helper.fg";
import "helper2.fg";
fn main() -> int {
    let r: Result<int, str> = try_call(outer_guarded, 5);
    if r.ok {
        println("unexpected ok");
    } else {
        println(r.error);
    }
    println("after");
    return 0;
}
""",
     """outer boom
after
""",
     ""),
    ("8 try_call inside a task, panicked_tasks stays 0",
     r"""import "result.fg";
import "helper.fg";
fn worker(n: int) {
    let r: Result<int, str> = try_call(helper_boom, n);
    if r.ok {
        println("unexpected ok");
    } else {
        println("caught in task:", r.error);
    }
}
fn main() -> int {
    scope {
        spawn worker(1);
    }
    println("panicked", panicked_tasks());
    return 0;
}
""",
     """caught in task: helper boom
panicked 0
""",
     ""),
    ("17 task spawned inside a guarded call is not caught",
     r"""import "result.fg";
import "helper.fg";
fn main() -> int {
    let r: Result<int, str> = try_call(helper_spawns_task, 1);
    if r.ok {
        println(r.value);
    } else {
        println("unexpected err");
    }
    println("panicked", panicked_tasks());
    return 0;
}
""",
     """99
panicked 1
""",
     "qasida: task panicked: task boom"),
    ("str return, ok and err",
     r"""import "result.fg";
import "helper.fg";
fn main() -> int {
    let a: Result<str, str> = try_call(helper_str, 1);
    if a.ok {
        println(a.value);
    } else {
        println("unexpected err");
    }
    let b: Result<str, str> = try_call(helper_str, 0);
    if b.ok {
        println("unexpected ok");
    } else {
        println(b.error);
    }
    return 0;
}
""",
     """hello
str boom
""",
     ""),
    ("array return, ok and err",
     r"""import "result.fg";
import "helper.fg";
fn main() -> int {
    let a: Result<[int], str> = try_call(helper_arr, 1);
    if a.ok {
        println(len(a.value));
        println(a.value[2]);
    } else {
        println("unexpected err");
    }
    let b: Result<[int], str> = try_call(helper_arr, 0);
    if b.ok {
        println("unexpected ok");
    } else {
        println(b.error);
    }
    return 0;
}
""",
     """3
3
arr boom
""",
     ""),
]

# (name, caller program, expected stdout, expected stderr needle) —
# must exit non-zero: the fault is fatal, never control flow.
FATAL_CASES = [
    ("10 fail outside try_call stays fatal",
     r"""import "helper.fg";
fn main() -> int {
    println("start");
    let x: int = helper_boom(1);
    println("unreached");
    return 0;
}
""",
     """start
""",
     "qasida: helper boom"),
    ("15a bounds fault inside try_call stays fatal",
     r"""import "result.fg";
import "helper.fg";
fn main() -> int {
    println("start");
    let r: Result<int, str> = try_call(helper_oob, 5);
    println("unreached");
    return 0;
}
""",
     """start
""",
     "qasida: runtime error: array index out of bounds"),
    ("15b div-by-zero inside try_call stays fatal",
     r"""import "result.fg";
import "helper.fg";
fn main() -> int {
    println("start");
    let r: Result<int, str> = try_call(helper_div, 0);
    println("unreached");
    return 0;
}
""",
     """start
""",
     "qasida: runtime error: division by zero"),
    ("15c overflow inside try_call stays fatal",
     r"""import "result.fg";
import "helper.fg";
fn main() -> int {
    println("start");
    let r: Result<int, str> = try_call(helper_overflow, 1);
    println("unreached");
    return 0;
}
""",
     """start
""",
     "qasida: runtime error: integer overflow"),
    ("16 assert inside try_call stays fatal",
     r"""import "result.fg";
import "helper.fg";
fn main() -> int {
    println("start");
    let r: Result<int, str> = try_call(helper_assert, 0);
    println("unreached");
    return 0;
}
""",
     """start
""",
     "qasida: assertion failed:"),
]

# (name, caller program, error fragment) — must be rejected at check time.
REJECT_CASES = [
    ("11 same-file callee",
     r"""import "result.fg";
fn boom() -> int {
    fail("boom");
    return 0;
}
fn main() -> int {
    let r: Result<int, str> = try_call(boom);
    println(r.ok);
    return 0;
}
""",
     "defined in this file"),
    ("12a closure literal callee",
     r"""import "result.fg";
import "helper.fg";
fn main() -> int {
    let f = fn(x: int) -> int { return x + 1; };
    let r: Result<int, str> = try_call(f, 1);
    println(r.ok);
    return 0;
}
""",
     "bare function name"),
    ("12b fn-typed variable callee",
     r"""import "result.fg";
import "helper.fg";
fn main() -> int {
    let f = helper_ok;
    let r: Result<int, str> = try_call(f, 1);
    println(r.ok);
    return 0;
}
""",
     "bare function name"),
    ("12c method callee",
     r"""import "result.fg";
struct Box {
    v: int;
}
impl Box {
    fn get(self: Box) -> int {
        return self.v;
    }
}
fn main() -> int {
    let b: Box = Box { v: 5 };
    let r: Result<int, str> = try_call(b.get);
    println(r.ok);
    return 0;
}
""",
     "bare function name"),
    ("13 no import of result.fg",
     r"""import "helper_min.fg";
fn main() -> int {
    let r = try_call(helper_ok, 1);
    println(r.ok);
    return 0;
}
""",
     "needs import"),
    ("14a arity too few",
     r"""import "result.fg";
import "helper.fg";
fn main() -> int {
    let r: Result<int, str> = try_call(helper_ok);
    println(r.ok);
    return 0;
}
""",
     "takes 1 argument(s), got 0"),
    ("14b arity too many",
     r"""import "result.fg";
import "helper.fg";
fn main() -> int {
    let r: Result<int, str> = try_call(helper_ok, 1, 2);
    println(r.ok);
    return 0;
}
""",
     "0 or 1 arguments"),
    ("generic callee",
     r"""import "result.fg";
import "helper.fg";
fn id_gen<T>(x: T) -> T {
    return x;
}
fn main() -> int {
    let r: Result<int, str> = try_call(id_gen, 1);
    println(r.ok);
    return 0;
}
""",
     "generic function"),
    ("void callee",
     r"""import "result.fg";
import "helper.fg";
fn main() -> int {
    let r = try_call(helper_void, 1);
    println("unreached");
    return 0;
}
""",
     "returns void"),
]

# (name, forge argv after the file, error fragment) — backend rejections.
# Backend cases (18a/18b) use the minimal helper: the shared
# HELPER_SRC contains a defer, which big32/wasm reject before
# reaching try_call, masking the try_call rejection.
BACKEND_PROG = r"""import "result.fg";
import "helper_min.fg";
fn main() -> int {
    let r: Result<int, str> = try_call(helper_ok, 41);
    println(r.value);
    return 0;
}
"""

BACKEND_CASES = [
    ("18a emit-big32 rejects try_call",
     ["emit-big32"],
     "big32: try_call is not supported"),
    ("18b emit-wasm rejects try_call",
     ["emit-wasm"],
     "wasm: try_call is not supported"),
]

# Case 9 (debug) + case 18c (defer pin) programs.
DEBUG_PROG = r"""import "result.fg";
import "helper.fg";
fn main() -> int {
    let r: Result<int, str> = try_call(helper_boom, 7);
    println(r.error);
    fail("second boom");
    return 0;
}
"""

DEFER_PROG = r"""import "result.fg";
import "helper.fg";
fn main() -> int {
    let r: Result<int, str> = try_call(helper_with_defer, 1);
    if r.ok {
        println("unexpected ok");
    } else {
        println(r.error);
    }
    println("after");
    return 0;
}
"""


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def build(prog_path, out_path, debug, prefix):
    args = [sys.executable, os.path.join(ROOT, "forge.py")] + prefix + ["build"]
    if debug:
        args.append("--debug")
    args += [prog_path, "-o", out_path]
    return run(args, ROOT)


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "trycatch_demo.fg")
    for mode, prefix in (("hosted", []), ("python", ["--python"])):
        r = run([sys.executable, os.path.join(ROOT, "forge.py")] + prefix +
                ["run", demo], ROOT)
        if not check(f"demo runs ({mode})", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append(f"demo runs ({mode})")
        elif not check(f"demo results ({mode})", r.stdout == DEMO_EXPECTED,
                       repr(r.stdout)):
            failures.append(f"demo results ({mode})")
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, "helper.fg"), "w") as f:
            f.write(HELPER_SRC)
        with open(os.path.join(td, "helper2.fg"), "w") as f:
            f.write(HELPER2_SRC)
        with open(os.path.join(td, "helper_min.fg"), "w") as f:
            f.write(HELPER_MIN_SRC)
        for name, prog, want, needle in OK_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                         prefix + ["run", p], ROOT)
                ok = (rr.returncode == 0 and rr.stdout == want and
                      (not needle or needle in rr.stderr))
                if not check(f"{name} ({mode})", ok,
                             repr(rr.stdout) + (rr.stderr.strip().splitlines() or [""])[-1]):
                    failures.append(f"{name} ({mode})")
        for name, prog, want, needle in FATAL_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                         prefix + ["run", p], ROOT)
                ok = (rr.returncode != 0 and rr.stdout == want and
                      needle in rr.stderr)
                if not check(f"{name} ({mode})", ok,
                             repr(rr.stdout) + (rr.stderr.strip().splitlines() or [""])[-1]):
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
        # Case 9 (debug): the caught failure prints its backtrace,
        # and the second failure's trace shows only its own frames.
        p = os.path.join(td, "dbg.fg")
        with open(p, "w") as f:
            f.write(DEBUG_PROG)
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            out = os.path.join(td, "dbg_bin_" + mode)
            rb = build(p, out, True, prefix)
            if not check(f"9 debug builds ({mode})", rb.returncode == 0,
                         rb.stderr.strip().splitlines()[-1] if rb.stderr else ""):
                failures.append(f"9 debug builds ({mode})")
                continue
            rr = run([out], td)
            parts = rr.stderr.split("stack backtrace:")
            ok = (rr.returncode == 1 and rr.stdout == "helper boom\n" and
                  "qasida: second boom" in rr.stderr and len(parts) == 3 and
                  "helper_boom" in parts[1] and
                  "main at" in parts[2] and "helper_boom" not in parts[2])
            if not check(f"9 debug catch-then-second-failure trace ({mode})", ok,
                         repr(rr.stderr)):
                failures.append(f"9 debug catch-then-second-failure trace ({mode})")
        # Case 18c (defer pin): the guarded call's defer does NOT run
        # on catch — "defer ran" must be absent from stdout.
        p = os.path.join(td, "defer.fg")
        with open(p, "w") as f:
            f.write(DEFER_PROG)
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                     prefix + ["run", p], ROOT)
            ok = (rr.returncode == 0 and
                  rr.stdout == "defer boom\nafter\n" and
                  "defer ran" not in rr.stdout)
            if not check(f"18c defer not run on catch ({mode})", ok,
                         repr(rr.stdout)):
                failures.append(f"18c defer not run on catch ({mode})")
        # Case 18a/b (backends) + freestanding reject try_call.
        p = os.path.join(td, "c.fg")
        with open(p, "w") as f:
            f.write(BACKEND_PROG)
        for name, cmd, frag in BACKEND_CASES:
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                         prefix + cmd + [p], ROOT)
                ok = rr.returncode != 0 and frag in (rr.stderr + rr.stdout)
                if not check(f"{name} ({mode})", ok,
                             (rr.stderr.strip().splitlines() or [""])[-1]):
                    failures.append(f"{name} ({mode})")
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                     prefix + ["check", p, "--freestanding"], ROOT)
            ok = (rr.returncode != 0 and
                  "needs the hosted runtime" in (rr.stderr + rr.stdout))
            if not check(f"18 freestanding rejects try_call ({mode})", ok,
                         (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(f"18 freestanding rejects try_call ({mode})")
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
