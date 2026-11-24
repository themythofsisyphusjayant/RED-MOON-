"""Top-500 #68: repeat-while loops (tests/test_repeatwhile_v1.py).

Run-once-then-check loops as pure library helpers in
forge_lang/stdlib/repeatwhile.fg: rw_run(body, cond) runs the
body once and then while cond() is true, returning the total
iteration count; rw_until(body, cond) repeats until cond() is
true. Body and cond close over a shared [int] buffer the
caller owns — a body closure CANNOT mutate an outer scalar
counter (checker error: closures capture by value; captured
variables are read-only in v1), so shared-buffer state
threading is the v1 pattern.

v1 limits (named in the catalog): no repeat-while syntax —
helpers over fn values only; state must live in a
caller-owned [int] buffer; the body's int return value is
ignored by the loop; no break/continue out of the helpers;
cond is evaluated after every body call, including the first.
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

DEMO_EXPECTED = """3
2
1
3
1
2
3
3
"""

# (name, program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("rw_run countdown 3->0, count 3",
     r"""import "repeatwhile.fg";
fn main() -> int {
  let buf: [int] = [3];
  let body = fn() -> int {
    println(buf[0]);
    buf[0] = buf[0] - 1;
    return buf[0];
  };
  let cond = fn() -> bool { return buf[0] > 0; };
  println(rw_run(body, cond));
  return 0;
}
""",
     """3
2
1
3
""",
     ""),
    ("rw_run runs the body once even when cond is false at once",
     r"""import "repeatwhile.fg";
fn main() -> int {
  let buf: [int] = [0];
  let body = fn() -> int {
    println(7);
    return 0;
  };
  let cond = fn() -> bool { return buf[0] > 0; };
  println(rw_run(body, cond));
  return 0;
}
""",
     """7
1
""",
     ""),
    ("rw_run buffer state is visible after the loop",
     r"""import "repeatwhile.fg";
fn main() -> int {
  let buf: [int] = [5];
  let body = fn() -> int {
    buf[0] = buf[0] - 2;
    return buf[0];
  };
  let cond = fn() -> bool { return buf[0] > 0; };
  println(rw_run(body, cond));
  println(buf[0]);
  return 0;
}
""",
     """3
-1
""",
     ""),
    ("rw_until increments to 3, count 3",
     r"""import "repeatwhile.fg";
fn main() -> int {
  let buf: [int] = [0];
  let body = fn() -> int {
    buf[0] = buf[0] + 1;
    println(buf[0]);
    return buf[0];
  };
  let cond = fn() -> bool { return buf[0] >= 3; };
  println(rw_until(body, cond));
  return 0;
}
""",
     """1
2
3
3
""",
     ""),
    ("rw_until stops after the first body when cond is already true",
     r"""import "repeatwhile.fg";
fn main() -> int {
  let buf: [int] = [0];
  let body = fn() -> int {
    println(9);
    return 0;
  };
  let cond = fn() -> bool { return true; };
  println(rw_until(body, cond));
  return 0;
}
""",
     """9
1
""",
     ""),
    ("rw_until body return value is ignored, count still tracks runs",
     r"""import "repeatwhile.fg";
fn main() -> int {
  let buf: [int] = [0];
  let body = fn() -> int {
    buf[0] = buf[0] + 1;
    return 100 - buf[0];
  };
  let cond = fn() -> bool { return buf[0] >= 2; };
  println(rw_until(body, cond));
  println(buf[0]);
  return 0;
}
""",
     """2
2
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
    demo = os.path.join(ROOT, "examples", "repeatwhile_demo.fg")
    lib = os.path.join(ROOT, "forge_lang", "stdlib", "repeatwhile.fg")
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
