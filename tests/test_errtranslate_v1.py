"""Top-500 #58: error translation layers (tests/test_errtranslate_v1.py).

Driver errors (ErrCode, forge_lang/stdlib/errcode.fg) are mapped to
domain strings: a caller-built ErrMap table of (from, to) pairs with
translate(), a built-in default table translate_io() for the common
ErrCode values, and Result mappers for the concrete shape
Result<int, ErrCode> -> Result<int, str>
(forge_lang/stdlib/errtranslate.fg).

v1 limits (named in the file header): translate_io() is one fixed
domain vocabulary (storage / network / auth / input / system) — no
per-module custom domain beyond a caller-built ErrMap table; a code
registered twice in a table keeps its FIRST mapping; an unmapped
code translates to "unknown domain error"; the Result mapper covers
only Result<int, ErrCode> (the generic Result<T, E> has no map
function); the table stores POSIX ints, not ErrCode values, because
[ErrCode] arrays cannot be struct fields or push targets in either
compiler (v1). Both compilers (Python + hosted).

No FATAL or REJECT cases apply: the module is pure stdlib with no
new builtins and no fatal paths. Runs use cwd=ROOT (like
test_errcode_v1.py): the hosted binary resolves stdlib imports
relative to the repo root (forge_lang/stdlib/), so a temp cwd would
break every import. Nothing is written to the tree.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO_EXPECTED = """NotFound -> storage: not found
TimedOut -> network: timed out
PermissionDenied -> auth: permission denied
Unknown -> unknown domain error
custom: storage: gone
custom unknown: unknown domain error
mapped value: 7
mapped error: storage: not found
mapped custom: storage: gone
"""

# (name, program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("translate_io covers every ErrCode value",
     r"""import "errtranslate.fg";
fn main() -> int {
  println(translate_io(Success));
  println(translate_io(NotFound));
  println(translate_io(PermissionDenied));
  println(translate_io(AlreadyExists));
  println(translate_io(IsADirectory));
  println(translate_io(NotADirectory));
  println(translate_io(InvalidArgument));
  println(translate_io(Interrupted));
  println(translate_io(NoSpace));
  println(translate_io(ReadOnlyFs));
  println(translate_io(TooManyOpen));
  println(translate_io(BrokenPipe));
  println(translate_io(ConnectionRefused));
  println(translate_io(TimedOut));
  println(translate_io(Unknown));
  return 0;
}
""",
     """ok
storage: not found
auth: permission denied
storage: already exists
storage: is a directory
storage: not a directory
input: invalid argument
system: interrupted
storage: no space left
storage: read-only file system
system: too many open files
network: broken pipe
network: connection refused
network: timed out
unknown domain error
""",
     ""),
    ("custom table maps, unmapped falls back, empty table falls back",
     r"""import "errtranslate.fg";
fn main() -> int {
  let empty = errmap_new();
  println("empty count", errmap_count(empty));
  println(translate(NotFound, empty));
  let t0 = errmap_new();
  let t1 = errmap_add(t0, NotFound, "storage: gone");
  let t = errmap_add(t1, TimedOut, "network: slow");
  println("count", errmap_count(t));
  println(translate(NotFound, t));
  println(translate(TimedOut, t));
  println(translate(PermissionDenied, t));
  return 0;
}
""",
     """empty count 0
unknown domain error
count 2
storage: gone
network: slow
unknown domain error
""",
     ""),
    ("duplicate table entry keeps the first mapping",
     r"""import "errtranslate.fg";
fn main() -> int {
  let t0 = errmap_new();
  let t1 = errmap_add(t0, NotFound, "first");
  let t = errmap_add(t1, NotFound, "second");
  println("count", errmap_count(t));
  println(translate(NotFound, t));
  return 0;
}
""",
     """count 2
first
""",
     ""),
    ("map_result_int passes an Ok value through untouched",
     r"""import "errtranslate.fg";
fn main() -> int {
  let r: Result<int, ErrCode> = Result { ok: true, value: 42, error: Success };
  let m = map_result_int(r);
  println("ok", m.ok);
  println("value", m.value);
  println("err len", len(m.error));
  return 0;
}
""",
     """ok true
value 42
err len 0
""",
     ""),
    ("map_result_int turns an Err code into a domain string",
     r"""import "errtranslate.fg";
fn main() -> int {
  let r: Result<int, ErrCode> = Result { ok: false, value: 0, error: TimedOut };
  let m = map_result_int(r);
  println("ok", m.ok);
  println("value", m.value);
  println("error", m.error);
  return 0;
}
""",
     """ok false
value 0
error network: timed out
""",
     ""),
    ("map_result_int_with uses the caller table, falls back otherwise",
     r"""import "errtranslate.fg";
fn main() -> int {
  let t0 = errmap_new();
  let t = errmap_add(t0, NotFound, "storage: gone");
  let a: Result<int, ErrCode> = Result { ok: false, value: 0, error: NotFound };
  let ma = map_result_int_with(a, t);
  println(ma.error);
  let b: Result<int, ErrCode> = Result { ok: false, value: 0, error: TimedOut };
  let mb = map_result_int_with(b, t);
  println(mb.error);
  let c: Result<int, ErrCode> = Result { ok: true, value: 9, error: Success };
  let mc = map_result_int_with(c, t);
  println("ok", mc.ok);
  println("value", mc.value);
  return 0;
}
""",
     """storage: gone
unknown domain error
ok true
value 9
""",
     ""),
    ("translate_io composes with read_file_err (str-Result pattern)",
     r"""import "errtranslate.fg";
fn main() -> int {
  let r = read_file_err("no_such_file_xyz.txt");
  let m = map_result_int_str(r);
  if m.ok {
    println("unexpected ok");
  } else {
    println(m.error);
  }
  return 0;
}

fn map_result_int_str(r: Result<str, ErrCode>) -> Result<str, str> {
  if r.ok {
    return Result { ok: true, value: r.value, error: "" };
  }
  return Result { ok: false, value: "", error: translate_io(r.error) };
}
""",
     """storage: not found
""",
     ""),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "errtranslate_demo.fg")
    with tempfile.TemporaryDirectory() as td:
        _run_all(td, failures, demo)
    _fmt_check(failures, demo)
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


def _fmt_check(failures, path):
    rf = run([sys.executable, os.path.join(ROOT, "forge.py"), "fmt", path],
             ROOT)
    if not check(f"fmt runs ({os.path.basename(path)})", rf.returncode == 0,
                 rf.stderr.strip()):
        failures.append(f"fmt runs ({os.path.basename(path)})")
    else:
        rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"),
                   "fmt", "--check", path], ROOT)
        if not check(f"fmt idempotent ({os.path.basename(path)})",
                     rf2.returncode == 0, rf2.stderr.strip()):
            failures.append(f"fmt idempotent ({os.path.basename(path)})")


if __name__ == "__main__":
    sys.exit(main())
