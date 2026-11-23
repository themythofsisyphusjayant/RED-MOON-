"""Top-500 #59: retryable vs fatal classification (tests/test_errclass_v1.py).

For the retry-backoff library that already exists.
forge_lang/stdlib/errclass.fg builds on errcode.fg and
retry-backoff.fg (retry_delay_ms / retry_delays / retry_total_ms):
classify(code: ErrCode) -> ErrClass maps each error code onto
Retryable or Fatal, err_is_retryable is the predicate form, and
retryable_delay(code, attempt, base_ms, cap_ms) -> int returns the
retry-backoff delay for retryable errors or -1 for fatal ones, so
a retry loop never sleeps before a call that cannot succeed.

Mapping (documented in the library): Retryable — Interrupted,
TimedOut, TooManyOpen, ConnectionRefused, BrokenPipe (retryable
only by re-establishing the connection, never by resending on the
same pipe). Fatal — everything else: Success (not an error, so
nothing to retry), NotFound, PermissionDenied, AlreadyExists,
IsADirectory, NotADirectory, InvalidArgument, NoSpace, ReadOnlyFs,
and Unknown (an error we cannot name is not one to blindly retry).

v1 limits (named in the catalog): classification is a static table,
not observed behaviour — it cannot learn that a code which is
usually transient is permanent for a particular service; there is
no jitter in the delays (retry-backoff.fg is deterministic by
design). Both compilers (Python + hosted). The demo writes no
files. Hosted runs raise the stack limit (ulimit -s 65536) the way
the task specifies.
"""

import os
import resource
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO_EXPECTED = """TimedOut Retryable
Interrupted Retryable
ConnectionRefused Retryable
NotFound Fatal
PermissionDenied Fatal
Unknown Fatal
delay TimedOut 0 100
delay TimedOut 2 400
delay ConnectionRefused 3 800
delay NotFound 0 -1
"""

# (name, program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("classify maps the transient codes to Retryable",
     r"""import "errclass.fg";
fn main() -> int {
  println(err_class_name(classify(Interrupted)));
  println(err_class_name(classify(TimedOut)));
  println(err_class_name(classify(TooManyOpen)));
  println(err_class_name(classify(ConnectionRefused)));
  println(err_class_name(classify(BrokenPipe)));
  return 0;
}
""",
     """Retryable
Retryable
Retryable
Retryable
Retryable
""",
     ""),
    ("classify maps the permanent codes to Fatal",
     r"""import "errclass.fg";
fn main() -> int {
  println(err_class_name(classify(NotFound)));
  println(err_class_name(classify(PermissionDenied)));
  println(err_class_name(classify(InvalidArgument)));
  println(err_class_name(classify(AlreadyExists)));
  println(err_class_name(classify(IsADirectory)));
  println(err_class_name(classify(NotADirectory)));
  println(err_class_name(classify(NoSpace)));
  println(err_class_name(classify(ReadOnlyFs)));
  return 0;
}
""",
     """Fatal
Fatal
Fatal
Fatal
Fatal
Fatal
Fatal
Fatal
""",
     ""),
    ("Success and Unknown classify Fatal, never Retryable",
     r"""import "errclass.fg";
fn main() -> int {
  println(err_class_name(classify(Success)));
  println(err_class_name(classify(Unknown)));
  println(err_is_retryable(Success));
  println(err_is_retryable(Unknown));
  return 0;
}
""",
     """Fatal
Fatal
false
false
""",
     ""),
    ("err_class_name round-trips both variants",
     r"""import "errclass.fg";
fn main() -> int {
  let r: ErrClass = Retryable;
  let f: ErrClass = Fatal;
  println(err_class_name(r));
  println(err_class_name(f));
  return 0;
}
""",
     """Retryable
Fatal
""",
     ""),
    ("retryable_delay doubles with the attempt and caps, fatal is -1",
     r"""import "errclass.fg";
fn main() -> int {
  println(retryable_delay(TimedOut, 0, 100, 1000));
  println(retryable_delay(TimedOut, 1, 100, 1000));
  println(retryable_delay(TimedOut, 2, 100, 1000));
  println(retryable_delay(TimedOut, 3, 100, 1000));
  println(retryable_delay(TimedOut, 5, 100, 1000));
  println(retryable_delay(Interrupted, 2, 50, 500));
  println(retryable_delay(NotFound, 0, 100, 1000));
  println(retryable_delay(NotFound, 3, 100, 1000));
  println(retryable_delay(Unknown, 1, 100, 1000));
  println(retryable_delay(PermissionDenied, 0, 100, 1000));
  return 0;
}
""",
     """100
200
400
800
1000
200
-1
-1
-1
-1
""",
     ""),
    ("err_is_retryable predicate matches classify",
     r"""import "errclass.fg";
fn main() -> int {
  println(err_is_retryable(TimedOut));
  println(err_is_retryable(ConnectionRefused));
  println(err_is_retryable(NotFound));
  println(err_is_retryable(AlreadyExists));
  return 0;
}
""",
     """true
true
false
false
""",
     ""),
    ("classify composes with err_from_code over raw errno values",
     r"""import "errclass.fg";
fn main() -> int {
  println(err_class_name(classify(err_from_code(110))));
  println(err_class_name(classify(err_from_code(111))));
  println(err_class_name(classify(err_from_code(4))));
  println(err_class_name(classify(err_from_code(2))));
  println(err_class_name(classify(err_from_code(999))));
  println(retryable_delay(err_from_code(110), 1, 100, 1000));
  println(retryable_delay(err_from_code(2), 1, 100, 1000));
  return 0;
}
""",
     """Retryable
Retryable
Retryable
Fatal
Fatal
200
-1
""",
     ""),
]


def _big_stack():
    resource.setrlimit(resource.RLIMIT_STACK,
                       (65536 * 1024, resource.RLIM_INFINITY))


def run(args, cwd, hosted=False):
    if hosted:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                              preexec_fn=_big_stack)
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    with tempfile.TemporaryDirectory() as td:
        _run_all(td, failures)
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


def _run_all(td, failures):
    demo = os.path.join(ROOT, "examples", "errclass_demo.fg")
    lib = os.path.join(ROOT, "forge_lang", "stdlib", "errclass.fg")
    for mode, prefix, hosted in (("hosted", [], True),
                                 ("python", ["--python"], False)):
        r = run([sys.executable, os.path.join(ROOT, "forge.py")] + prefix +
                ["run", demo], ROOT, hosted=hosted)
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
        for mode, prefix, hosted in (("hosted", [], True),
                                     ("python", ["--python"], False)):
            rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                     prefix + ["run", p], ROOT, hosted=hosted)
            ok = (rr.returncode == 0 and rr.stdout == want and
                  (not needle or needle in rr.stderr))
            if not check(f"{name} ({mode})", ok,
                         repr(rr.stdout) + (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(f"{name} ({mode})")
    # fmt strips // comments, so the lib (which keeps its header) is
    # not fmt-run here — demo only, same as test_errcode_v1.py.
    for target in (demo,):
        rf = run([sys.executable, os.path.join(ROOT, "forge.py"), "fmt", target],
                 ROOT)
        if not check(f"fmt runs {os.path.basename(target)}",
                     rf.returncode == 0, rf.stderr.strip()):
            failures.append(f"fmt runs {target}")
        else:
            rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"),
                       "fmt", "--check", target], ROOT)
            if not check(f"fmt idempotent {os.path.basename(target)}",
                         rf2.returncode == 0, rf2.stderr.strip()):
                failures.append(f"fmt idempotent {target}")


if __name__ == "__main__":
    sys.exit(main())
