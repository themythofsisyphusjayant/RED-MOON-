"""Top-500 #65: match guards (tests/test_matchguard_v1.py).

Predicate-dispatch over (value, predicate, action) tables in
forge_lang/stdlib/matchguard.fg: mg_match_int walks the
predicate table in order and returns the first matching
action's result; the fallback is returned when no predicate
matches (or when a matching predicate has no paired action).
Tables are [fn(int) -> bool] / [fn(int) -> str] arrays, so a
guard table is built with push and passed as a value.

v1 limits (named in the catalog): no exhaustiveness checking
(the fallback is the catch-all, unchecked), no pattern
bindings (predicates see only the value), no enum/adt
dispatch, int values only. Both compilers (Python +
hosted). Runs use cwd=ROOT (like test_errcode_v1.py): the
hosted binary resolves stdlib imports relative to the repo
root (forge_lang/stdlib/), so a temp cwd would break every
import. Nothing is written to the tree.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO_EXPECTED = """neg -5
zero
big 200
other
"""

# (name, program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("first matching predicate wins when several match",
     r"""import "matchguard.fg";
import "fmtstr.fg";
fn is_pos(x: int) -> bool {
  return x > 0;
}

fn is_big(x: int) -> bool {
  return x > 100;
}

fn say_pos(x: int) -> str {
  return "pos " + fs_int_str(x);
}

fn say_big(x: int) -> str {
  return "big " + fs_int_str(x);
}

fn main() -> int {
  let mut preds: [fn(int) -> bool] = [];
  push(preds, is_pos);
  push(preds, is_big);
  let mut actions: [fn(int) -> str] = [];
  push(actions, say_pos);
  push(actions, say_big);
  println(mg_match_int(200, preds, actions, "other"));
  return 0;
}
""",
     """pos 200
""",
     ""),
    ("fallback when no predicate matches",
     r"""import "matchguard.fg";
fn is_neg(x: int) -> bool {
  return x < 0;
}

fn say_neg(x: int) -> str {
  return "neg";
}

fn main() -> int {
  let mut preds: [fn(int) -> bool] = [];
  push(preds, is_neg);
  let mut actions: [fn(int) -> str] = [];
  push(actions, say_neg);
  println(mg_match_int(7, preds, actions, "other"));
  return 0;
}
""",
     """other
""",
     ""),
    ("empty tables return the fallback",
     r"""import "matchguard.fg";
fn main() -> int {
  let preds: [fn(int) -> bool] = [];
  let actions: [fn(int) -> str] = [];
  println(mg_match_int(42, preds, actions, "none"));
  return 0;
}
""",
     """none
""",
     ""),
    ("a matching predicate with no paired action is skipped",
     r"""import "matchguard.fg";
import "fmtstr.fg";
fn is_big(x: int) -> bool {
  return x > 100;
}

fn is_pos(x: int) -> bool {
  return x > 0;
}

fn say_big(x: int) -> str {
  return "big " + fs_int_str(x);
}

fn main() -> int {
  let mut preds: [fn(int) -> bool] = [];
  push(preds, is_big);
  push(preds, is_pos);
  let mut actions: [fn(int) -> str] = [];
  push(actions, say_big);
  println(mg_match_int(5, preds, actions, "other"));
  return 0;
}
""",
     """other
""",
     ""),
    ("a lambda predicate works in the table",
     r"""import "matchguard.fg";
fn say_42(x: int) -> str {
  return "forty-two";
}

fn main() -> int {
  let mut preds: [fn(int) -> bool] = [];
  let is_42 = fn(x: int) -> bool { return x == 42; };
  push(preds, is_42);
  let mut actions: [fn(int) -> str] = [];
  push(actions, say_42);
  println(mg_match_int(42, preds, actions, "other"));
  println(mg_match_int(43, preds, actions, "other"));
  return 0;
}
""",
     """forty-two
other
""",
     ""),
    ("the action receives the value, not just the match",
     r"""import "matchguard.fg";
import "fmtstr.fg";
fn is_even(x: int) -> bool {
  return x % 2 == 0;
}

fn say_doubled(x: int) -> str {
  return "doubled " + fs_int_str(x * 2);
}

fn main() -> int {
  let mut preds: [fn(int) -> bool] = [];
  push(preds, is_even);
  let mut actions: [fn(int) -> str] = [];
  push(actions, say_doubled);
  println(mg_match_int(10, preds, actions, "odd"));
  return 0;
}
""",
     """doubled 20
""",
     ""),
    ("fall-through reaches the second predicate",
     r"""import "matchguard.fg";
import "fmtstr.fg";
fn is_big(x: int) -> bool {
  return x > 100;
}

fn is_neg(x: int) -> bool {
  return x < 0;
}

fn say_big(x: int) -> str {
  return "big " + fs_int_str(x);
}

fn say_neg(x: int) -> str {
  return "neg " + fs_int_str(x);
}

fn main() -> int {
  let mut preds: [fn(int) -> bool] = [];
  push(preds, is_big);
  push(preds, is_neg);
  let mut actions: [fn(int) -> str] = [];
  push(actions, say_big);
  push(actions, say_neg);
  println(mg_match_int(-3, preds, actions, "other"));
  return 0;
}
""",
     """neg -3
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
    demo = os.path.join(ROOT, "examples", "matchguard_demo.fg")
    lib = os.path.join(ROOT, "forge_lang", "stdlib", "matchguard.fg")
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
