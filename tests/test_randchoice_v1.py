"""Top-500 #5: random choice and shuffle v1 (tests/test_randchoice_v1.py).
Random choice, Fisher-Yates shuffle and sampling without
replacement over a seeded RNG, in pure Qasida in
forge_lang/stdlib/randchoice.fg. Every function threads the RNG
state as an int and returns the new state alongside its value,
in the value-returning style of pool.fg. The LCG uses the same
constants as rand.fg (Numerical Recipes, modulus 2^31 - 1 =
2147483647, multiplier 1103515245, increment 12345); the state
IS the output value, so rand_next returns (value, value).
rand_seed normalizes any int into a valid state and maps seed 0
to 12345, so the generator never sticks at zero. All expected
values were hand-computed with an independent Python replica of
the same LCG before the first Qasida run — never copied from
Qasida output. Native-only in v1: big32 and WASM reject tuple
programs.
NOTE (verified 28 Nov 2026): randchoice.fg carries NO header
comment because `forge.py fmt` strips ALL `//` comments — even
committed rand.fg / randdist.fg fail `fmt --check` — so a header
comment cannot coexist with this test's fmt-idempotence check.
The LCG constants are pinned here, in the replica used for the
expectations, and inline in the code (same literals as rand.fg).
NOTE: randchoice.fg is self-contained and defines its own
tuple-returning rand_next; importing rand.fg alongside it makes
rand.fg's int-returning rand_next shadow this file's, and
rand_choice then fails with "tuple index .0 needs a tuple
value, got int" — use one or the other.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

IMP = 'import "randchoice.fg";\n'

DEMO_EXPECTED = "40\n4\n3\n1\n2\n5\n40\n50\n10\n"

# (name, program, expected stdout) — must run clean.
OK_CASES = [
    ("rand_next: value equals new state, in range",
     IMP + "fn main() {\n  let r = rand_next(rand_seed(42));\n"
     "  println(r.0);\n  println(r.1);\n}\n",
     "1250496048\n1250496048\n"),
    ("seed 0 normalizes to 12345, never stuck",
     IMP + "fn main() {\n  println(rand_seed(0));\n"
     "  let r = rand_next(rand_seed(0));\n  println(r.0);\n}\n",
     "12345\n1406938949\n"),
    ("negative seed normalizes into range",
     IMP + "fn main() {\n  println(rand_seed(-5));\n"
     "  let r = rand_next(rand_seed(-5));\n  println(r.0);\n}\n",
     "2147483642\n924887061\n"),
    ("same seed twice gives the same choice",
     IMP + "fn main() {\n  let xs: [int] = [10, 20, 30, 40, 50];\n"
     "  let a = rand_choice(rand_seed(42), xs); println(a.0);\n"
     "  let b = rand_choice(rand_seed(42), xs); println(b.0);\n}\n",
     "40\n40\n"),
    ("same seed twice gives the same shuffle",
     IMP + "fn main() {\n  let xs: [int] = [1, 2, 3, 4, 5];\n"
     "  let a = rand_shuffle(rand_seed(42), xs);\n"
     "  let b = rand_shuffle(rand_seed(42), xs);\n"
     "  let mut i = 0;\n"
     "  while i < len(a.0) { println(a.0[i]); i = i + 1; }\n"
     "  let mut j = 0;\n"
     "  while j < len(b.0) { println(b.0[j]); j = j + 1; }\n}\n",
     "2\n5\n1\n3\n4\n2\n5\n1\n3\n4\n"),
    ("shuffle is a permutation: exact values plus sum",
     IMP + "fn main() {\n  let xs: [int] = [1, 2, 3, 4, 5];\n"
     "  let sh = rand_shuffle(rand_seed(7), xs);\n"
     "  let mut sum = 0;\n  let mut i = 0;\n"
     "  while i < len(sh.0) { println(sh.0[i]); sum = sum + sh.0[i]; i = i + 1; }\n"
     "  println(sum);\n}\n",
     "3\n4\n1\n2\n5\n15\n"),
    ("sample has no duplicates and keeps draw order",
     IMP + "fn main() {\n  let xs: [int] = [10, 20, 30, 40, 50];\n"
     "  let sm = rand_sample(rand_seed(42), xs, 3);\n"
     "  let mut i = 0;\n"
     "  while i < len(sm.0) { println(sm.0[i]); i = i + 1; }\n}\n",
     "20\n50\n10\n"),
    ("sample of n == len is a permutation",
     IMP + "fn main() {\n  let xs: [int] = [10, 20, 30, 40, 50];\n"
     "  let sm = rand_sample(rand_seed(7), xs, 5);\n"
     "  let mut sum = 0;\n  let mut i = 0;\n"
     "  while i < len(sm.0) { println(sm.0[i]); sum = sum + sm.0[i]; i = i + 1; }\n"
     "  println(sum);\n}\n",
     "30\n40\n10\n20\n50\n150\n"),
    ("choice from a 1-element list always returns it",
     IMP + "fn main() {\n  let xs: [int] = [99];\n"
     "  let a = rand_choice(rand_seed(1), xs); println(a.0);\n"
     "  let b = rand_choice(rand_seed(2), xs); println(b.0);\n}\n",
     "99\n99\n"),
    ("different seeds give different first choices",
     IMP + "fn main() {\n  let xs: [int] = [10, 20, 30, 40, 50];\n"
     "  let a = rand_choice(rand_seed(1), xs); println(a.0);\n"
     "  let b = rand_choice(rand_seed(2), xs); println(b.0);\n}\n",
     "10\n40\n"),
    ("sample n=0 returns an empty list",
     IMP + "fn main() {\n  let xs: [int] = [10, 20, 30, 40, 50];\n"
     "  let sm = rand_sample(rand_seed(42), xs, 0);\n"
     "  println(len(sm.0));\n}\n",
     "0\n"),
    ("shuffle of 1 element and of empty list are unchanged",
     IMP + "fn main() {\n  let one: [int] = [7];\n"
     "  let a = rand_shuffle(rand_seed(42), one); println(a.0[0]);\n"
     "  let empty: [int] = [];\n"
     "  let b = rand_shuffle(rand_seed(42), empty); println(len(b.0));\n}\n",
     "7\n0\n"),
]

# (name, program) — must fail (nonzero exit).
FAIL_CASES = [
    ("choice from an empty list fails",
     IMP + "fn main() {\n  let xs: [int] = [];\n"
     "  let c = rand_choice(rand_seed(42), xs); println(c.0);\n}\n"),
    ("sample with n > len fails",
     IMP + "fn main() {\n  let xs: [int] = [10, 20];\n"
     "  let sm = rand_sample(rand_seed(42), xs, 3); println(len(sm.0));\n}\n"),
    ("sample with negative n fails",
     IMP + "fn main() {\n  let xs: [int] = [10, 20];\n"
     "  let sm = rand_sample(rand_seed(42), xs, -1); println(len(sm.0));\n}\n"),
]


def run(args, cwd, env=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          env=env)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "randchoice_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("randchoice demo", r.returncode == 0 and r.stdout == DEMO_EXPECTED,
                 f"(rc={r.returncode} out={r.stdout!r} err={r.stderr[:200]!r})"):
        failures.append("randchoice demo")
    # Same demo under the Python compiler: byte-identical output.
    env = dict(os.environ)
    env["QASIDA_COMPILER"] = "python"
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT, env=env)
    if not check("randchoice demo (python compiler)",
                 r.returncode == 0 and r.stdout == DEMO_EXPECTED,
                 f"(rc={r.returncode} out={r.stdout!r} err={r.stderr[:200]!r})"):
        failures.append("randchoice demo (python compiler)")
    for name, prog, expected in OK_CASES:
        with tempfile.NamedTemporaryFile("w", suffix=".fg", delete=False,
                                        dir=ROOT) as f:
            f.write(prog)
            path = f.name
        try:
            r = run([sys.executable, os.path.join(ROOT, "forge.py"),
                     "run", path], ROOT)
            ok = r.returncode == 0 and r.stdout == expected
            if not check(name, ok,
                         f"(rc={r.returncode} out={r.stdout!r} "
                         f"err={r.stderr[:200]!r})"):
                failures.append(name)
        finally:
            os.unlink(path)
    for name, prog in FAIL_CASES:
        with tempfile.NamedTemporaryFile("w", suffix=".fg", delete=False,
                                        dir=ROOT) as f:
            f.write(prog)
            path = f.name
        try:
            r = run([sys.executable, os.path.join(ROOT, "forge.py"),
                     "run", path], ROOT)
            ok = r.returncode != 0
            if not check(name, ok,
                         f"(rc={r.returncode} out={r.stdout!r} "
                         f"err={r.stderr[:200]!r})"):
                failures.append(name)
        finally:
            os.unlink(path)
    # fmt idempotent on both new files.
    for rel in ("forge_lang/stdlib/randchoice.fg",
                "examples/randchoice_demo.fg"):
        p = os.path.join(ROOT, rel)
        rf = run([sys.executable, os.path.join(ROOT, "forge.py"),
                  "fmt", p], ROOT)
        if not check(f"fmt runs ({rel})", rf.returncode == 0,
                     rf.stderr.strip()):
            failures.append(f"fmt runs ({rel})")
            continue
        rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"),
                   "fmt", "--check", p], ROOT)
        if not check(f"fmt idempotent ({rel})", rf2.returncode == 0,
                     rf2.stderr.strip()):
            failures.append(f"fmt idempotent ({rel})")
    # big32 and WASM reject randchoice programs: tuples are not supported.
    for target in ("big32", "wasm"):
        r = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                 "--target", target, demo], ROOT)
        ok = r.returncode != 0 and "tuples are not supported" in (
            r.stderr + r.stdout)
        if not check(f"{target} rejects randchoice demo", ok,
                     f"(rc={r.returncode} err={r.stderr[:200]!r})"):
            failures.append(f"{target} gate")
    # ASan: the demo runs clean.
    with tempfile.TemporaryDirectory() as td:
        c_path = os.path.join(td, "randchoice.c")
        bin_path = os.path.join(td, "randchoice_asan")
        r = run([sys.executable, os.path.join(ROOT, "forge.py"), "emit",
                 demo], ROOT)
        with open(c_path, "w") as f:
            f.write(r.stdout)
        cc = run(["cc", "-g", "-fsanitize=address", "-o", bin_path, c_path,
                  "-lssl", "-lcrypto", "-lm"], ROOT)
        if cc.returncode != 0:
            check("ASan build", False, f"(cc err={cc.stderr[:300]!r})")
            failures.append("ASan build")
        else:
            r = run([bin_path], ROOT)
            ok = r.returncode == 0 and r.stdout == DEMO_EXPECTED
            if not check("ASan run clean", ok,
                         f"(rc={r.returncode} out={r.stdout!r} "
                         f"err={r.stderr[:300]!r})"):
                failures.append("ASan run")
    if failures:
        print(f"FAILURES: {len(failures)}: {failures}")
        return 1
    print(f"ALL PASS ({2 + len(OK_CASES) + len(FAIL_CASES) + 4 + 2 + 1} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
