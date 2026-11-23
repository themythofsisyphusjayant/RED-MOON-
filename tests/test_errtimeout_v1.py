"""Top-500 #52: timeout errors as values (tests/test_errtimeout_v1.py).

Deadline-exceeded is data, not a crash. forge_lang/stdlib/errtimeout.fg
builds on timeout.fg (to_deadline / to_remaining / to_expired over
explicit microsecond stamps) and errcode.fg (ErrCode.TimedOut):
check_deadline(deadline_us, now_us) -> Result<int, ErrCode> returns
Err(TimedOut) when expired and Ok(remaining_us) otherwise, err_timeout()
produces the timeout error value, err_new_deadline(ms) constructs a
deadline from the live clock, and err_check_now(deadline_us) checks
one against clock_micros().

v1 limits (named in the catalog): a deadline that only reports expiry
— no async cancellation, no interrupting a running call; the caller
must poll check_deadline itself. Verification is deterministic fake
timestamps (pure functions over explicit stamps, like timeout.fg)
plus two live clock_micros() smoke cases that assert only the
branch taken, never an exact clock value. Both compilers (Python +
hosted). The demo writes no files. Hosted runs raise the stack
limit (ulimit -s 65536) the way the task specifies.
"""

import os
import resource
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO_EXPECTED = """remaining 300000
expired TimedOut
expired TimedOut
timeout TimedOut
is timeout true
is timeout false
"""

# (name, program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("check_deadline before the deadline returns Ok remaining",
     r"""import "errtimeout.fg";
fn main() -> int {
  let d = to_deadline(1000000, 500);
  let r = check_deadline(d, 1200000);
  if r.ok {
    println("remaining", r.value);
  } else {
    println("expired", err_name(r.error));
  }
  return 0;
}
""",
     """remaining 300000
""",
     ""),
    ("check_deadline exactly at the deadline is expired (boundary)",
     r"""import "errtimeout.fg";
fn main() -> int {
  let d = to_deadline(1000000, 500);
  let r = check_deadline(d, 1500000);
  if r.ok {
    println("remaining", r.value);
  } else {
    println("expired", err_name(r.error));
  }
  return 0;
}
""",
     """expired TimedOut
""",
     ""),
    ("check_deadline after the deadline is Err TimedOut, code 110",
     r"""import "errtimeout.fg";
fn main() -> int {
  let d = to_deadline(1000000, 500);
  let r = check_deadline(d, 2000000);
  if r.ok {
    println("unexpected ok");
  } else {
    println("expired", err_name(r.error));
    println("code", err_code(r.error));
    println("message", err_message(r.error));
  }
  return 0;
}
""",
     """expired TimedOut
code 110
message connection timed out
""",
     ""),
    ("deadline built from ms by to_deadline, remaining clamps the same way",
     r"""import "errtimeout.fg";
fn main() -> int {
  let d = to_deadline(500000, 250);
  let r = check_deadline(d, 600000);
  if r.ok {
    println("remaining", r.value);
  } else {
    println("expired", err_name(r.error));
  }
  let zero = to_deadline(0, 0);
  let z = check_deadline(zero, 0);
  if z.ok {
    println("unexpected ok");
  } else {
    println("zero expired", err_name(z.error));
  }
  return 0;
}
""",
     """remaining 150000
zero expired TimedOut
""",
     ""),
    ("err_timeout produces TimedOut; err_is_timeout recognises it",
     r"""import "errtimeout.fg";
fn main() -> int {
  println(err_name(err_timeout()));
  println(err_code(err_timeout()));
  println(err_is_timeout(err_timeout()));
  println(err_is_timeout(NotFound));
  println(err_is_timeout(Success));
  return 0;
}
""",
     """TimedOut
110
true
false
false
""",
     ""),
    ("live clock smoke: 5000ms deadline is not yet expired",
     r"""import "errtimeout.fg";
fn main() -> int {
  let d = err_new_deadline(5000);
  let r = err_check_now(d);
  if r.ok {
    println("live ok");
  } else {
    println("live expired");
  }
  return 0;
}
""",
     """live ok
""",
     ""),
    ("live clock smoke: 0ms deadline is already expired",
     r"""import "errtimeout.fg";
fn main() -> int {
  let d = err_new_deadline(0);
  let r = err_check_now(d);
  if r.ok {
    println("live ok");
  } else {
    println("live expired", err_name(r.error));
  }
  return 0;
}
""",
     """live expired TimedOut
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
    demo = os.path.join(ROOT, "examples", "errtimeout_demo.fg")
    lib = os.path.join(ROOT, "forge_lang", "stdlib", "errtimeout.fg")
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
