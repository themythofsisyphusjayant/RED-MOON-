"""Top-500 #73: loop else (tests/test_loopelse_v1.py).

A Python-style loop-else as a pure library helper in
forge_lang/stdlib/loopelse.fg: le_run(body, on_else) where the
body returns 0 = continue, 1 = break, 2 = done-cleanly.
on_else runs ONLY on clean completion (code 2); on break it
is skipped. le_run returns 0 if the else-branch ran (clean
completion) and 1 if the loop broke out. The else-branch's
own result is observed via shared state or its own println —
it is NOT returned, because any sentinel could collide with
a legitimate else value. Body and on_else close over a
shared [int] buffer the caller owns — a body closure CANNOT
mutate an outer scalar counter (checker error: closures
capture by value; captured variables are read-only in v1),
so shared-buffer state threading is the v1 pattern.

v1 limits (named in the catalog): no loop-else syntax —
helper over fn values only; state must live in a
caller-owned [int] buffer; the else-branch result flows
through shared state or side effects, not the return value;
body codes other than 0/1/2 are treated as continue (0).
Both compilers (Python + hosted). Runs use cwd=ROOT (like
test_errcode_v1.py): the hosted binary resolves stdlib
imports relative to the repo root (forge_lang/stdlib/), so a
temp cwd would break every import. Nothing is written to
the tree.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO_EXPECTED = """1
2
1
1
2
3
99
0
"""

# (name, program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("break path: status 1, else skipped",
     r"""import "loopelse.fg";
fn main() -> int {
  let buf: [int] = [0];
  let body = fn() -> int {
    buf[0] = buf[0] + 1;
    println(buf[0]);
    if buf[0] >= 2 {
      return 1;
    }
    return 0;
  };
  let els = fn() -> int {
    println(99);
    return 0;
  };
  println(le_run(body, els));
  return 0;
}
""",
     """1
2
1
""",
     ""),
    ("clean path: status 0, else runs",
     r"""import "loopelse.fg";
fn main() -> int {
  let buf: [int] = [0];
  let body = fn() -> int {
    buf[0] = buf[0] + 1;
    println(buf[0]);
    if buf[0] >= 3 {
      return 2;
    }
    return 0;
  };
  let els = fn() -> int {
    println(99);
    return 0;
  };
  println(le_run(body, els));
  return 0;
}
""",
     """1
2
3
99
0
""",
     ""),
    ("break on the first call: body runs once, else skipped",
     r"""import "loopelse.fg";
fn main() -> int {
  let body = fn() -> int {
    println(5);
    return 1;
  };
  let els = fn() -> int {
    println(99);
    return 0;
  };
  println(le_run(body, els));
  return 0;
}
""",
     """5
1
""",
     ""),
    ("done-cleanly on the first call: else runs once",
     r"""import "loopelse.fg";
fn main() -> int {
  let body = fn() -> int {
    println(5);
    return 2;
  };
  let els = fn() -> int {
    println(99);
    return 0;
  };
  println(le_run(body, els));
  return 0;
}
""",
     """5
99
0
""",
     ""),
    ("else-branch result observed via the shared buffer",
     r"""import "loopelse.fg";
fn main() -> int {
  let buf: [int] = [0];
  let body = fn() -> int {
    return 2;
  };
  let els = fn() -> int {
    buf[0] = buf[0] + 7;
    return 0;
  };
  println(le_run(body, els));
  println(buf[0]);
  return 0;
}
""",
     """0
7
""",
     ""),
    ("unknown body code is treated as continue",
     r"""import "loopelse.fg";
fn main() -> int {
  let buf: [int] = [0];
  let body = fn() -> int {
    buf[0] = buf[0] + 1;
    println(buf[0]);
    if buf[0] >= 2 {
      return 2;
    }
    return 42;
  };
  let els = fn() -> int {
    println(99);
    return 0;
  };
  println(le_run(body, els));
  return 0;
}
""",
     """1
2
99
0
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
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_STACK,
                           (65536 * 1024, resource.RLIM_INFINITY))
    except Exception:
        pass
    with tempfile.TemporaryDirectory() as td:
        _run_all(td, failures)
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


def _run_all(td, failures):
    demo = os.path.join(ROOT, "examples", "loopelse_demo.fg")
    lib = os.path.join(ROOT, "forge_lang", "stdlib", "loopelse.fg")
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
    # fmt strips // comments, so the lib (which keeps its header) is
    # not fmt-run here — demo only, same as test_errcode_v1.py.
    for target in (demo,):
        rf = run([sys.executable, os.path.join(ROOT, "forge.py"), "fmt", target],
                 ROOT)
        if not check(f"fmt runs ({os.path.basename(target)})",
                     rf.returncode == 0, rf.stderr.strip()):
            failures.append(f"fmt runs ({target})")
        else:
            rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"),
                       "fmt", "--check", target], ROOT)
            if not check(f"fmt idempotent ({os.path.basename(target)})",
                         rf2.returncode == 0, rf2.stderr.strip()):
                failures.append(f"fmt idempotent ({target})")


if __name__ == "__main__":
    sys.exit(main())
