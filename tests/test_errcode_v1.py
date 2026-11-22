"""Top-500 #46: error codes as enums (tests/test_errcode_v1.py).

Typed errno-style errors for syscalls. The runtime records errno at
every failed write (fopen) into an atomic slot read by the new
zero-arg builtin last_errno() -> int (0 if no write has failed), and
two new fallible builtins return Result instead of failing fatally:
try_read_file(path) -> Result<str, int> and try_read_bytes(path) ->
Result<[int], int>, with the raw POSIX errno as the Err payload.
The stdlib forge_lang/stdlib/errcode.fg maps those codes onto a typed
ErrCode enum (err_from_code / err_code / err_name / err_message) and
wraps the builtins in read_file_err / read_bytes_err / write_file_err
/ write_bytes_err returning Result<..., ErrCode>.

v1 limits (named in the catalog): the mapping covers the common POSIX
codes and maps anything else to Unknown; http_get / mmap failures have
no fallible try_ variant yet, so their errno is not observable here;
the bookkeeping mallocs inside the try_ builtins can still forge_fail
under true OOM (same as try_alloc #36); a read failure is fatal only
via the old read_file/read_bytes — the try_ variants return Err.
big32, WASM and freestanding reject last_errno() and the try_ builtins
with named errors. Both compilers (Python + hosted).

The demo writes a file, so the files it and the file-writing cases
create (errcode_demo_out.txt, roundtrip*.txt/bin, good.txt) are
unlinked before and after the run — nothing is left in the tree.
Runs use cwd=ROOT (like test_panic_recover_v1.py): the hosted
binary resolves stdlib imports relative to the repo root
(forge_lang/stdlib/), so a temp cwd would break every import.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO_EXPECTED = """write ok
write err = NotFound
read err = NotFound
read back = hello errcode
code 2 = NotFound
code 13 = PermissionDenied
code 0 = Success
code 999 = Unknown
"""

# (name, program, expected stdout, expected stderr needle or "").
# Programs that import result.fg / errcode.fg use the stdlib; the
# file-writing cases run with cwd=td so nothing lands in the tree.
OK_CASES = [
    ("last_errno is 0 before any failure",
     r"""fn main() -> int {
  println(last_errno());
  return 0;
}
""",
     """0
""",
     ""),
    ("try_read_file missing file gives Err 2 (ENOENT)",
     r"""import "result.fg";
fn main() -> int {
  let r = try_read_file("no_such_file_xyz.txt");
  if r.ok {
    println("unexpected ok");
  } else {
    println("err", r.error);
  }
  return 0;
}
""",
     """err 2
""",
     ""),
    ("try_read_bytes missing file gives Err 2 (ENOENT)",
     r"""import "result.fg";
fn main() -> int {
  let r = try_read_bytes("no_such_file_xyz.txt");
  if r.ok {
    println("unexpected ok");
  } else {
    println("err", r.error);
  }
  return 0;
}
""",
     """err 2
""",
     ""),
    ("try_read_file reads back what write_file wrote",
     r"""import "result.fg";
fn main() -> int {
  let ok = write_file("roundtrip.txt", "hello errcode");
  if !ok {
    println("write failed");
    return 0;
  }
  let r = try_read_file("roundtrip.txt");
  if r.ok {
    println(r.value);
  } else {
    println("read err", r.error);
  }
  return 0;
}
""",
     """hello errcode
""",
     ""),
    ("try_read_bytes reads back what write_bytes wrote",
     r"""import "result.fg";
fn main() -> int {
  let data: [int] = [72, 105];
  let ok = write_bytes("roundtrip.bin", data);
  if !ok {
    println("write failed");
    return 0;
  }
  let r = try_read_bytes("roundtrip.bin");
  if r.ok {
    println("len", len(r.value));
    println("first", r.value[0]);
  } else {
    println("read err", r.error);
  }
  return 0;
}
""",
     """len 2
first 72
""",
     ""),
    ("failed write records errno, later success does not clear it",
     r"""fn main() -> int {
  println("before", last_errno());
  let ok = write_file("no_such_dir_xyz/out.txt", "hi");
  println("ok", ok);
  println("after fail", last_errno());
  let ok2 = write_file("good.txt", "x");
  println("ok2", ok2);
  println("after success", last_errno());
  return 0;
}
""",
     """before 0
ok false
after fail 2
ok2 true
after success 2
""",
     ""),
    ("failed write_bytes records errno too",
     r"""fn main() -> int {
  let data: [int] = [1, 2];
  let ok = write_bytes("no_such_dir_xyz/out.bin", data);
  println("ok", ok);
  println("errno", last_errno());
  return 0;
}
""",
     """ok false
errno 2
""",
     ""),
    ("errcode mapping round-trips through the enum",
     r"""import "errcode.fg";
fn main() -> int {
  println(err_code(err_from_code(13)));
  println(err_name(err_from_code(110)));
  println(err_message(err_from_code(2)));
  println(err_code(err_from_code(999)));
  println(err_name(err_from_code(999)));
  return 0;
}
""",
     """13
TimedOut
no such file or directory
-1
Unknown
""",
     ""),
    ("errcode wrappers: missing file is Err NotFound, round trip is Ok",
     r"""import "errcode.fg";
fn main() -> int {
  let r = read_file_err("no_such_file_xyz.txt");
  if r.ok {
    println("unexpected read ok");
  } else {
    println("read err", err_name(r.error));
  }
  let w = write_file_err("roundtrip2.txt", "wrap works");
  if w.ok {
    println("write ok");
  } else {
    println("write err", err_name(w.error));
  }
  let back = read_file_err("roundtrip2.txt");
  if back.ok {
    println(back.value);
  } else {
    println("readback err", err_name(back.error));
  }
  let bad = write_file_err("no_such_dir_xyz/out.txt", "hi");
  if bad.ok {
    println("unexpected write ok");
  } else {
    println("bad write err", err_name(bad.error));
  }
  return 0;
}
""",
     """read err NotFound
write ok
wrap works
bad write err NotFound
""",
     ""),
    ("errcode byte wrappers round-trip",
     r"""import "errcode.fg";
fn main() -> int {
  let data: [int] = [65, 66];
  let w = write_bytes_err("roundtrip2.bin", data);
  if w.ok {
    println("write ok");
  } else {
    println("write err", err_name(w.error));
  }
  let r = read_bytes_err("roundtrip2.bin");
  if r.ok {
    println("len", len(r.value));
    println("first", r.value[0]);
  } else {
    println("read err", err_name(r.error));
  }
  let missing = read_bytes_err("no_such_file_xyz.bin");
  if missing.ok {
    println("unexpected ok");
  } else {
    println("missing err", err_name(missing.error));
  }
  return 0;
}
""",
     """write ok
len 2
first 65
missing err NotFound
""",
     ""),
    ("bare ErrCode variant is visible across the import",
     r"""import "errcode.fg";
fn main() -> int {
  let e: ErrCode = NotFound;
  println(err_name(e));
  println(err_code(e));
  return 0;
}
""",
     """NotFound
2
""",
     ""),
]

# (name, program, expected stdout, expected stderr needle).
FATAL_CASES = [
    ("plain read_file on a missing file stays fatal",
     r"""fn main() -> int {
  println("start");
  let s = read_file("no_such_file_xyz.txt");
  println(s);
  return 0;
}
""",
     """start
""",
     "qasida: runtime error: cannot read file"),
]

# (name, program, error fragment) — must be rejected at check time.
REJECT_CASES = [
    ("try_read_file with no argument",
     r"""import "result.fg";
fn main() -> int {
  let r = try_read_file();
  println(r.ok);
  return 0;
}
""",
     "try_read_file() takes exactly one str argument"),
    ("try_read_file with an int argument",
     r"""import "result.fg";
fn main() -> int {
  let r = try_read_file(42);
  println(r.ok);
  return 0;
}
""",
     "try_read_file() takes exactly one str argument"),
    ("try_read_file without importing result.fg",
     r"""fn main() -> int {
  let r = try_read_file("x.txt");
  println(r.ok);
  return 0;
}
""",
     'try_read_file() needs import "result.fg"'),
    ("try_read_bytes with an int argument",
     r"""import "result.fg";
fn main() -> int {
  let r = try_read_bytes(42);
  println(r.ok);
  return 0;
}
""",
     "try_read_bytes() takes exactly one str argument"),
    ("last_errno with an argument",
     r"""fn main() -> int {
  println(last_errno(1));
  return 0;
}
""",
     "last_errno() takes no arguments"),
    ("last_errno as a statement",
     r"""fn main() -> int {
  last_errno();
  return 0;
}
""",
     "is an expression, not a statement"),
]

# (name, program, forge argv after the file, error fragment).
# Small programs (not the demo) so the first builtin the backend
# meets is the one under test.
BACKEND_CASES = [
    ("emit-big32 rejects last_errno",
     r"""fn main() -> int {
  let n: int = last_errno();
  return n;
}
""",
     ["emit-big32"],
     "builtin last_errno() is not supported on big32 (v1)"),
    ("emit-big32 rejects try_read_file",
     r"""import "result.fg";
fn main() -> int {
  let r = try_read_file("x.txt");
  println(r.ok);
  return 0;
}
""",
     ["emit-big32"],
     "builtin try_read_file() is not supported on big32 (v1)"),
    ("emit-wasm rejects last_errno",
     r"""fn main() -> int {
  let n: int = last_errno();
  return n;
}
""",
     ["emit-wasm"],
     "wasm: last_errno() needs errno"),
    ("emit-wasm rejects try_read_file",
     r"""import "result.fg";
fn main() -> int {
  let r = try_read_file("x.txt");
  println(r.ok);
  return 0;
}
""",
     ["emit-wasm"],
     "wasm: try_read_file() needs the hosted filesystem"),
]

# (name, program, error fragment) — freestanding rejections.
# The call is read through a plain int binding: in freestanding mode
# println itself is rejected first, so the builtin must not be the
# only thing in a println.
FREESTANDING_CASES = [
    ("freestanding rejects last_errno",
     r"""fn main() -> int {
  let n: int = last_errno();
  return n;
}
""",
     "needs the hosted runtime"),
    ("freestanding rejects try_read_file",
     r"""import "result.fg";
fn main() -> int {
  let r = try_read_file("x.txt");
  return 0;
}
""",
     "needs the hosted runtime"),
    ("freestanding rejects try_read_bytes",
     r"""import "result.fg";
fn main() -> int {
  let r = try_read_bytes("x.txt");
  return 0;
}
""",
     "needs the hosted runtime"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


# Files the demo / cases write into the cwd (ROOT); unlinked before
# and after the run so nothing is left in the tree.
WRITTEN = ("errcode_demo_out.txt", "roundtrip.txt", "roundtrip.bin",
           "good.txt", "roundtrip2.txt", "roundtrip2.bin")


def _unlink_written():
    for name in WRITTEN:
        try:
            os.unlink(os.path.join(ROOT, name))
        except FileNotFoundError:
            pass

def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "errcode_demo.fg")
    _unlink_written()
    try:
        with tempfile.TemporaryDirectory() as td:
            _run_all(td, failures)
    finally:
        _unlink_written()
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


def _run_all(td, failures):
    demo = os.path.join(ROOT, "examples", "errcode_demo.fg")
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
    for name, prog, frag in FREESTANDING_CASES:
        p = os.path.join(td, "c.fg")
        with open(p, "w") as f:
            f.write(prog)
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                     prefix + ["check", p, "--freestanding"], ROOT)
            ok = (rr.returncode != 0 and
                  frag in (rr.stderr + rr.stdout))
            if not check(f"{name} ({mode})", ok,
                         (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(f"{name} ({mode})")
    for name, prog, cmd, frag in BACKEND_CASES:
        p = os.path.join(td, "c.fg")
        with open(p, "w") as f:
            f.write(prog)
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                     prefix + cmd + [p], ROOT)
            ok = rr.returncode != 0 and frag in (rr.stderr + rr.stdout)
            if not check(f"{name} ({mode})", ok,
                         (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(f"{name} ({mode})")
    rf = run([sys.executable, os.path.join(ROOT, "forge.py"), "fmt", demo],
             ROOT)
    if not check("fmt runs", rf.returncode == 0, rf.stderr.strip()):
        failures.append("fmt runs")
    else:
        rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"),
                   "fmt", "--check", demo], ROOT)
        if not check("fmt idempotent", rf2.returncode == 0, rf2.stderr.strip()):
            failures.append("fmt idempotent")


if __name__ == "__main__":
    sys.exit(main())
