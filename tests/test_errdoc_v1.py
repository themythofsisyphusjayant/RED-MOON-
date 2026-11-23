"""Top-500 #56: documented errors in signatures (tests/test_errdoc_v1.py).

A caller-populated registry mapping a function name to the list of
errors its documentation says it may fail with: errdoc_new /
doc_register / doc_errors_for / doc_has_error / doc_count /
doc_render (forge_lang/stdlib/errdoc.fg). This is the catalog's
"Doc-level only, not enforced": the checker does NOT verify that a
function fails only with its documented errors, and nothing in this
module can make it do so — doc_register records a claim, the lookup
functions read it back, and a registry that disagrees with the code
is silently wrong.

v1 limits (named in the file header): the registry is
caller-populated (there is no way to read a function's documentation
from the compiler); a name registered twice keeps its FIRST entry
(no update or remove API); lookup is a linear scan; the error names
are plain strings with no link to the ErrCode enum, so a typo in a
name is invisible to the checker. Both compilers (Python + hosted).

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

DEMO_EXPECTED = """registered: 2
first error: NotFound
second error: PermissionDenied
has NotFound: true
has TimedOut: false
unknown errors: 0
fn read_config may fail with: NotFound, PermissionDenied
fn fetch_url may fail with: TimedOut, ConnectionRefused
fn missing_fn has no documented errors
"""

# (name, program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("empty registry: count 0, no errors, render says none",
     r"""import "errdoc.fg";
fn main() -> int {
  let reg = errdoc_new();
  println("count", doc_count(reg));
  let errs = doc_errors_for(reg, "anything");
  println("len", len(errs));
  println("has", doc_has_error(reg, "anything", "NotFound"));
  println(doc_render(reg, "anything"));
  return 0;
}
""",
     """count 0
len 0
has false
fn anything has no documented errors
""",
     ""),
    ("register one function and read its errors back",
     r"""import "errdoc.fg";
fn main() -> int {
  let reg0 = errdoc_new();
  let errs: [str] = ["NotFound", "PermissionDenied"];
  let reg = doc_register(reg0, "read_config", errs);
  println("count", doc_count(reg));
  let back = doc_errors_for(reg, "read_config");
  println("len", len(back));
  println(back[0]);
  println(back[1]);
  return 0;
}
""",
     """count 1
len 2
NotFound
PermissionDenied
""",
     ""),
    ("two functions stay independent",
     r"""import "errdoc.fg";
fn main() -> int {
  let reg0 = errdoc_new();
  let a: [str] = ["NotFound"];
  let reg1 = doc_register(reg0, "read_config", a);
  let b: [str] = ["TimedOut", "ConnectionRefused"];
  let reg = doc_register(reg1, "fetch_url", b);
  println("count", doc_count(reg));
  let ca = doc_errors_for(reg, "read_config");
  let cb = doc_errors_for(reg, "fetch_url");
  println(len(ca));
  println(ca[0]);
  println(len(cb));
  println(cb[0]);
  println(cb[1]);
  return 0;
}
""",
     """count 2
1
NotFound
2
TimedOut
ConnectionRefused
""",
     ""),
    ("doc_has_error: true, false, and unknown function",
     r"""import "errdoc.fg";
fn main() -> int {
  let reg0 = errdoc_new();
  let errs: [str] = ["NotFound", "PermissionDenied"];
  let reg = doc_register(reg0, "read_config", errs);
  println(doc_has_error(reg, "read_config", "NotFound"));
  println(doc_has_error(reg, "read_config", "PermissionDenied"));
  println(doc_has_error(reg, "read_config", "TimedOut"));
  println(doc_has_error(reg, "missing_fn", "NotFound"));
  return 0;
}
""",
     """true
true
false
false
""",
     ""),
    ("doc_render formats the doc block, or says none",
     r"""import "errdoc.fg";
fn main() -> int {
  let reg0 = errdoc_new();
  let errs: [str] = ["NotFound", "PermissionDenied"];
  let reg = doc_register(reg0, "read_config", errs);
  println(doc_render(reg, "read_config"));
  println(doc_render(reg, "other_fn"));
  return 0;
}
""",
     """fn read_config may fail with: NotFound, PermissionDenied
fn other_fn has no documented errors
""",
     ""),
    ("duplicate registration keeps the first entry",
     r"""import "errdoc.fg";
fn main() -> int {
  let reg0 = errdoc_new();
  let first: [str] = ["NotFound"];
  let reg1 = doc_register(reg0, "read_config", first);
  let second: [str] = ["TimedOut"];
  let reg = doc_register(reg1, "read_config", second);
  println("count", doc_count(reg));
  println(doc_render(reg, "read_config"));
  return 0;
}
""",
     """count 2
fn read_config may fail with: NotFound
""",
     ""),
    ("registering an empty error list renders as none",
     r"""import "errdoc.fg";
fn main() -> int {
  let reg0 = errdoc_new();
  let none: [str] = [];
  let reg = doc_register(reg0, "pure_fn", none);
  println("count", doc_count(reg));
  println(doc_render(reg, "pure_fn"));
  return 0;
}
""",
     """count 1
fn pure_fn has no documented errors
""",
     ""),
    ("register returns a new registry; the original is unchanged",
     r"""import "errdoc.fg";
fn main() -> int {
  let reg0 = errdoc_new();
  let errs: [str] = ["NotFound"];
  let reg1 = doc_register(reg0, "read_config", errs);
  println("before", doc_count(reg0));
  println("after", doc_count(reg1));
  println(doc_render(reg0, "read_config"));
  return 0;
}
""",
     """before 0
after 1
fn read_config has no documented errors
""",
     ""),
    ("three errors join with commas in render order",
     r"""import "errdoc.fg";
fn main() -> int {
  let reg0 = errdoc_new();
  let errs: [str] = ["NotFound", "PermissionDenied", "IsADirectory"];
  let reg = doc_register(reg0, "open_path", errs);
  println(doc_render(reg, "open_path"));
  return 0;
}
""",
     """fn open_path may fail with: NotFound, PermissionDenied, IsADirectory
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
    demo = os.path.join(ROOT, "examples", "errdoc_demo.fg")
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
