"""Top-500 #344: long-form error explanations (tests/test_errexplain_v1.py).

explain_error(code) returns a multi-line write-up (what went wrong,
why, the fix, and the exact checker/runtime message it matches) for
a fixed table of 10 codes grounded in the real messages in
forge_lang/checker.py and forge_lang/codegen.py; unknown codes get a
short "no long-form explanation" string. has_explanation reports
table membership; known_codes lists the table.

v1 limits (named in the catalog): the E-codes are a library-side
numbering — the compiler today emits no E-codes
(forge_lang/errors.py carries no code field) and its messages are
plain text; this table labels the real messages, it does not hook
the compiler. Fixed table of 10 codes; no per-error suggestions
beyond the write-up itself. Both compilers (Python + hosted). Runs
use cwd=ROOT (like test_errcode_v1.py): the hosted binary resolves
stdlib imports relative to the repo root (forge_lang/stdlib/), so a
temp cwd would break every import.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO_EXPECTED = """E0002: undefined name
What went wrong: the checker could not find a variable, function, or struct with this name.
Why: Qasida has no implicit declarations; every name must be declared before use, and names are case-sensitive.
Fix: check the spelling, declare the name before using it, or add the missing import.
Compiler says: undefined variable '<name>' / undefined function '<name>' / undefined struct '<name>'
No long-form explanation for code E9999 yet.
true
false
10
"""

# (name, program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("E0001 type mismatch write-up",
     r"""import "errexplain.fg";
fn main() -> int {
  println(explain_error("E0001"));
  return 0;
}
""",
     """E0001: type mismatch
What went wrong: a value of one type was used where another type was expected.
Why: Qasida checks types before running; an int is not a str, and a Result<str, _> is not a plain str.
Fix: convert the value to the expected type, or change the declared type to match the value.
Compiler says: cannot assign <type> to <type> variable '<name>'
""",
     ""),
    ("E0007 integer overflow write-up",
     r"""import "errexplain.fg";
fn main() -> int {
  println(explain_error("E0007"));
  return 0;
}
""",
     """E0007: integer overflow
What went wrong: an int add, subtract, multiply, negate, or divide overflowed 64 bits.
Why: int arithmetic is checked; the result must fit in a signed 64-bit integer.
Fix: check the operands before the operation, or split the work so no intermediate overflows.
Runtime says: integer overflow
""",
     ""),
    ("E0010 unknown type write-up",
     r"""import "errexplain.fg";
fn main() -> int {
  println(explain_error("E0010"));
  return 0;
}
""",
     """E0010: unknown type
What went wrong: a declared type name does not exist.
Why: struct, enum, newtype, and alias names must be declared before use, just like variables.
Fix: check the spelling, declare the type first, or import the file that declares it.
Compiler says: unknown type '<name>' / unknown field type '<name>'
""",
     ""),
    ("unknown code gets the short fallback string",
     r"""import "errexplain.fg";
fn main() -> int {
  println(explain_error("E1234"));
  println(explain_error(""));
  return 0;
}
""",
     """No long-form explanation for code E1234 yet.
No long-form explanation for code  yet.
""",
     ""),
    ("has_explanation is true for all ten codes, false otherwise",
     r"""import "errexplain.fg";
fn main() -> int {
  println(has_explanation("E0001"));
  println(has_explanation("E0002"));
  println(has_explanation("E0003"));
  println(has_explanation("E0004"));
  println(has_explanation("E0005"));
  println(has_explanation("E0006"));
  println(has_explanation("E0007"));
  println(has_explanation("E0008"));
  println(has_explanation("E0009"));
  println(has_explanation("E0010"));
  println(has_explanation("E0011"));
  return 0;
}
""",
     """true
true
true
true
true
true
true
true
true
true
false
""",
     ""),
    ("known_codes lists the ten codes in order",
     r"""import "errexplain.fg";
fn main() -> int {
  let codes: [str] = known_codes();
  println(len(codes));
  println(codes[0]);
  println(codes[9]);
  return 0;
}
""",
     """10
E0001
E0010
""",
     ""),
]

# (name, program, error fragment) — must be rejected at check time.
REJECT_CASES = [
    ("explain_error with no argument",
     r"""import "errexplain.fg";
fn main() -> int {
  println(explain_error());
  return 0;
}
""",
     "takes 1 argument(s), got 0"),
    ("explain_error with an int argument",
     r"""import "errexplain.fg";
fn main() -> int {
  println(explain_error(42));
  return 0;
}
""",
     "must be str, got int"),
    ("has_explanation with two arguments",
     r"""import "errexplain.fg";
fn main() -> int {
  println(has_explanation("E0001", "E0002"));
  return 0;
}
""",
     "takes 1 argument(s), got 2"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def run_forge(prefix, args, cwd):
    cmd = [sys.executable, os.path.join(ROOT, "forge.py")] + prefix + args
    if prefix:
        return run(cmd, cwd)
    # Hosted: raise the stack limit first (the hosted checker
    # segfaults at the default 8 MB stack on deeply nested code).
    return run(["/bin/bash", "-c", "ulimit -s 65536; exec \"$@\"",
                "bash"] + cmd, cwd)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "errexplain_demo.fg")
    lib = os.path.join(ROOT, "forge_lang", "stdlib", "errexplain.fg")
    with tempfile.TemporaryDirectory() as td:
        _run_all(td, failures, demo)
    # fmt strips // comments, so the lib (which keeps its header) is
    # not fmt-run here — demo only, same as test_errcode_v1.py.
    for path in (demo,):
        rf = run([sys.executable, os.path.join(ROOT, "forge.py"), "fmt",
                  path], ROOT)
        if not check(f"fmt runs ({os.path.basename(path)})",
                     rf.returncode == 0, rf.stderr.strip()):
            failures.append(f"fmt runs ({path})")
        else:
            rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"),
                       "fmt", "--check", path], ROOT)
            if not check(f"fmt idempotent ({os.path.basename(path)})",
                         rf2.returncode == 0, rf2.stderr.strip()):
                failures.append(f"fmt idempotent ({path})")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


def _run_all(td, failures, demo):
    for mode, prefix in (("hosted", []), ("python", ["--python"])):
        r = run_forge(prefix, ["run", demo], ROOT)
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
            rr = run_forge(prefix, ["run", p], ROOT)
            ok = (rr.returncode == 0 and rr.stdout == want and
                  (not needle or needle in rr.stderr))
            if not check(f"{name} ({mode})", ok,
                         repr(rr.stdout) + (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(f"{name} ({mode})")
    for name, prog, frag in REJECT_CASES:
        p = os.path.join(td, "c.fg")
        with open(p, "w") as f:
            f.write(prog)
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            rr = run_forge(prefix, ["run", p], ROOT)
            ok = rr.returncode != 0 and frag in (rr.stderr + rr.stdout)
            if not check(f"{name} ({mode})", ok,
                         (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(f"{name} ({mode})")


if __name__ == "__main__":
    sys.exit(main())
