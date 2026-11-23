"""Top-500 #55: fail-fast vs collect mode (tests/test_errmode_v1.py).

A per-call choice of error strategy in
forge_lang/stdlib/errmode.fg, built on multierr.fg (MultiErr
accumulation) and result.fg (Result). The mode is chosen per
call (collect_or_fail / em_collect) or per collector (em_new),
never global: FailFast stops at the first error, Collect
gathers them all. collect_or_fail(FailFast, errs) returns
Err(errs[0]); collect_or_fail(Collect, errs) returns Ok(errs).
An Err branch still carries the full collected list in its
value, so nothing is lost by failing fast; an empty error list
is Ok([]) under either mode. A FailFast collector ignores
every add after the first error.

v1 limits (named in the catalog): string errors only (like
multierr); no per-error codes or severities yet; the mode
cannot change once a collector is created (make a new one
instead); the collector stores the mode as an int tag because
a struct field cannot be enum-typed in v1. Both compilers
(Python + hosted). Runs use cwd=ROOT (like
test_errcode_v1.py): the hosted binary resolves stdlib
imports relative to the repo root (forge_lang/stdlib/), so a
temp cwd would break every import. Nothing is written to the
tree.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO_EXPECTED = """false
bad age
2
true
2
bad age
bad name
2
bad age; bad name
1
first
false
first
Collect
"""

# (name, program, expected stdout, expected stderr needle or "").
# Result<[str], str> values are bound to a local before indexing:
# indexing the value field of a generic Result directly is
# miscompiled by the hosted backend in v1.
OK_CASES = [
    ("collect_or_fail FailFast returns Err(first), value keeps all",
     r"""import "errmode.fg";
fn main() -> int {
  let errs: [str] = ["a", "b", "c"];
  let r = collect_or_fail(FailFast, errs);
  println(r.ok);
  println(r.error);
  println(len(r.value));
  let v: [str] = r.value;
  println(v[0]);
  println(v[2]);
  return 0;
}
""",
     """false
a
3
a
c
""",
     ""),
    ("collect_or_fail Collect returns Ok(all)",
     r"""import "errmode.fg";
fn main() -> int {
  let errs: [str] = ["a", "b", "c"];
  let r = collect_or_fail(Collect, errs);
  println(r.ok);
  println(r.error);
  println(len(r.value));
  let v: [str] = r.value;
  println(v[1]);
  return 0;
}
""",
     """true

3
b
""",
     ""),
    ("empty errors are Ok under either mode",
     r"""import "errmode.fg";
fn main() -> int {
  let e: [str] = [];
  let ff = collect_or_fail(FailFast, e);
  println(ff.ok);
  println(len(ff.value));
  let cc = collect_or_fail(Collect, e);
  println(cc.ok);
  println(len(cc.value));
  return 0;
}
""",
     """true
0
true
0
""",
     ""),
    ("em_collect reads errors out of a MultiErr",
     r"""import "errmode.fg";
import "multierr.fg";
fn main() -> int {
  let mut m: MultiErr = me_new();
  m = me_add(m, "x");
  m = me_add(m, "y");
  let r = em_collect(FailFast, m);
  println(r.ok);
  println(r.error);
  let r2 = em_collect(Collect, m);
  println(r2.ok);
  println(len(r2.value));
  return 0;
}
""",
     """false
x
true
2
""",
     ""),
    ("FailFast collector keeps only the first error",
     r"""import "errmode.fg";
fn main() -> int {
  let mut f: ErrCollector = em_new(FailFast);
  f = em_add(f, "one");
  f = em_add(f, "two");
  f = em_add(f, "three");
  println(em_count(f));
  println(em_first(f));
  println(em_render(f));
  let r = em_resolve(f);
  println(r.ok);
  println(r.error);
  return 0;
}
""",
     """1
one
one
false
one
""",
     ""),
    ("Collect collector keeps all, in order",
     r"""import "errmode.fg";
fn main() -> int {
  let mut c: ErrCollector = em_new(Collect);
  c = em_add(c, "one");
  c = em_add(c, "two");
  c = em_add(c, "three");
  println(em_count(c));
  println(em_render(c));
  let r = em_resolve(c);
  println(r.ok);
  println(len(r.value));
  let v: [str] = r.value;
  println(v[2]);
  return 0;
}
""",
     """3
one; two; three
true
3
three
""",
     ""),
    ("empty collectors resolve to Ok([]) under either mode",
     r"""import "errmode.fg";
fn main() -> int {
  let f: ErrCollector = em_new(FailFast);
  println(em_has(f));
  println(em_first(f));
  let rf = em_resolve(f);
  println(rf.ok);
  println(len(rf.value));
  let c: ErrCollector = em_new(Collect);
  let rc = em_resolve(c);
  println(rc.ok);
  println(len(rc.value));
  return 0;
}
""",
     """false

true
0
true
0
""",
     ""),
    ("em_mode round-trips and em_mode_name names both modes",
     r"""import "errmode.fg";
fn main() -> int {
  println(em_mode_name(FailFast));
  println(em_mode_name(Collect));
  println(em_mode_name(em_mode(em_new(Collect))));
  println(em_mode_name(em_mode(em_new(FailFast))));
  return 0;
}
""",
     """FailFast
Collect
Collect
FailFast
""",
     ""),
    ("mode is per collector, not global",
     r"""import "errmode.fg";
fn main() -> int {
  let mut f: ErrCollector = em_new(FailFast);
  let mut c: ErrCollector = em_new(Collect);
  f = em_add(f, "a");
  f = em_add(f, "b");
  c = em_add(c, "a");
  c = em_add(c, "b");
  println(em_count(f));
  println(em_count(c));
  println(em_first(f));
  println(em_render(c));
  return 0;
}
""",
     """1
2
a
a; b
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
    demo = os.path.join(ROOT, "examples", "errmode_demo.fg")
    lib = os.path.join(ROOT, "forge_lang", "stdlib", "errmode.fg")
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
