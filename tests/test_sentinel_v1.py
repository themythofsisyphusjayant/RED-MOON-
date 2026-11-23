"""Top-500 #57: sentinel errors (tests/test_sentinel_v1.py).

Go-style named sentinels over errcode.fg's ErrCode enum: compare
against sent_timeout() / sent_not_found() instead of raw ints,
with is_timeout / is_not_found / is_sentinel predicates and
sentinel_name (short name, falling back to err_name for
non-sentinel codes). EOF has no ErrCode variant — it is not an
errno — so is_eof_read predicates on a Result<str, ErrCode>
instead: an ok read of an empty string is end of input
(read_line() returns "" at EOF).

v1 limits (named in the catalog): an empty file also reads as
ok/empty, so is_eof_read cannot tell a zero-byte file from EOF;
only Timeout and NotFound have ErrCode sentinels so far. Both
compilers (Python + hosted).

No FATAL / REJECT / BACKEND / FREESTANDING sections: the module
adds no new builtins, so there is nothing to reject, and the
backend/freestanding rejections a program importing it meets are
the pre-existing errcode.fg ones (ErrCode fields in structs,
enum returns on WASM), not this item's — those are covered by
tests/test_errcode_v1.py. The demo and the cases write no files,
so there is nothing to clean up. Runs use cwd=ROOT (like
test_panic_recover_v1.py): the hosted binary resolves stdlib
imports relative to the repo root (forge_lang/stdlib/), so a temp
cwd would break every import.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO_EXPECTED = """notfound? true
timeout? true
sentinel? true
sentinel? false
name Timeout
name Unknown
timeout is Timeout
notfound is NotFound
eof? true
eof? false
eof? false
is not found true
"""

# (name, program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("sentinels are the named ErrCode values",
     r"""import "sentinel.fg";
fn main() -> int {
  println(sentinel_name(sent_timeout()));
  println(err_code(sent_timeout()));
  println(sentinel_name(sent_not_found()));
  println(err_code(sent_not_found()));
  return 0;
}
""",
     """Timeout
110
NotFound
2
""",
     ""),
    ("is_timeout matches only TimedOut",
     r"""import "sentinel.fg";
fn main() -> int {
  println(is_timeout(err_from_code(110)));
  println(is_timeout(err_from_code(2)));
  println(is_timeout(err_from_code(999)));
  println(is_timeout(err_from_code(0)));
  return 0;
}
""",
     """true
false
false
false
""",
     ""),
    ("is_not_found matches only NotFound",
     r"""import "sentinel.fg";
fn main() -> int {
  println(is_not_found(err_from_code(2)));
  println(is_not_found(err_from_code(110)));
  println(is_not_found(err_from_code(13)));
  return 0;
}
""",
     """true
false
false
""",
     ""),
    ("is_sentinel is true exactly for the named sentinels",
     r"""import "sentinel.fg";
fn main() -> int {
  println(is_sentinel(err_from_code(2)));
  println(is_sentinel(err_from_code(110)));
  println(is_sentinel(err_from_code(0)));
  println(is_sentinel(err_from_code(13)));
  println(is_sentinel(err_from_code(999)));
  return 0;
}
""",
     """true
true
false
false
false
""",
     ""),
    ("sentinel_name falls back to err_name for non-sentinels",
     r"""import "sentinel.fg";
fn main() -> int {
  println(sentinel_name(err_from_code(110)));
  println(sentinel_name(err_from_code(2)));
  println(sentinel_name(err_from_code(13)));
  println(sentinel_name(err_from_code(999)));
  return 0;
}
""",
     """Timeout
NotFound
PermissionDenied
Unknown
""",
     ""),
    ("is_eof_read is true only for ok empty reads",
     r"""import "sentinel.fg";
fn main() -> int {
  let empty: Result<str, ErrCode> = Result { ok: true, value: "", error: Success };
  println(is_eof_read(empty));
  let some: Result<str, ErrCode> = Result { ok: true, value: "x", error: Success };
  println(is_eof_read(some));
  let bad: Result<str, ErrCode> = Result { ok: false, value: "", error: NotFound };
  println(is_eof_read(bad));
  let missing = read_file_err("no_such_file_xyz.txt");
  println(is_eof_read(missing));
  return 0;
}
""",
     """true
false
false
false
""",
     ""),
    ("a missing file is the NotFound sentinel",
     r"""import "sentinel.fg";
fn main() -> int {
  let r = read_file_err("no_such_file_xyz.txt");
  println(is_not_found(r.error));
  println(is_sentinel(r.error));
  println(is_timeout(r.error));
  println(sentinel_name(r.error));
  return 0;
}
""",
     """true
true
false
NotFound
""",
     ""),
    ("bare ErrCode variants compare equal to sentinels",
     r"""import "sentinel.fg";
fn main() -> int {
  let e: ErrCode = TimedOut;
  println(is_timeout(e));
  println(e == sent_timeout());
  let f: ErrCode = NotFound;
  println(is_not_found(f));
  println(f == sent_not_found());
  return 0;
}
""",
     """true
true
true
true
""",
     ""),
    ("err_from_code round-trips through sentinel_name",
     r"""import "sentinel.fg";
fn main() -> int {
  println(sentinel_name(err_from_code(111)));
  println(sentinel_name(err_from_code(32)));
  println(sentinel_name(err_from_code(28)));
  return 0;
}
""",
     """ConnectionRefused
BrokenPipe
NoSpace
""",
     ""),
    ("Success is not any sentinel",
     r"""import "sentinel.fg";
fn main() -> int {
  let e: ErrCode = Success;
  println(is_sentinel(e));
  println(is_timeout(e));
  println(is_not_found(e));
  println(sentinel_name(e));
  return 0;
}
""",
     """false
false
false
Success
""",
     ""),
]

# .fg files whose formatting must be idempotent.
# fmt strips // comments, so the lib (which keeps its header) is not
# fmt-run here — demo only, same as test_errcode_v1.py.
FMT_FILES = ("examples/sentinel_demo.fg",)


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "sentinel_demo.fg")
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
