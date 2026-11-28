"""Top-500 #54: cliparse v1 (tests/test_cliparse_v1.py).
Command-line flag/subcommand parser, pure Qasida in
forge_lang/stdlib/cliparse.fg: a Cli struct wraps the raw
args; the subcommand is the first positional; flags are
--long / -s short forms (clusters like -abc count as -a -b
-c); options take values as --name value, --name=value, or
-n value; "--" stops flag parsing. A bare long flag consumes
the following non-dash arg as its value, so that value is
not a positional; short flags never consume a following arg
for positional purposes (their -n value is still honoured by
cli_opt). cli_opt returns "" when the option is absent or
present without a value; cli_has_opt tells those apart.
No tuples anywhere, so big32 and WASM accept this file and
there are no named-rejection checks.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

IMP = 'import "cliparse.fg";\n'

DEMO_EXPECTED = ("subcommand: build\nrelease: true\njobs: 4\n"
                 "verbose: true\npos_count: 2\npos0: build\n"
                 "output: out.bin\n")

# (name, program, expected stdout) — must run clean.
OK_CASES = [
    ("--opt=value form; value not a positional",
     IMP + "fn main() {\n"
     "  let c: Cli = cli_parse([\"run\", \"--jobs=8\", \"--mode=fast\", \"x.fg\"]);\n"
     "  println(cli_sub(c));\n"
     "  println(cli_opt(c, \"jobs\"));\n"
     "  println(cli_opt(c, \"mode\"));\n"
     "  println(cli_has_opt(c, \"jobs\"));\n"
     "  println(cli_pos_count(c));\n"
     "  println(cli_pos(c, 1));\n}\n",
     "run\n8\nfast\ntrue\n2\nx.fg\n"),
    ("short-flag cluster -abc counts as -a -b -c",
     IMP + "fn main() {\n"
     "  let c: Cli = cli_parse([\"-abc\", \"prog\", \"--quiet\"]);\n"
     "  println(cli_flag(c, \"a\"));\n"
     "  println(cli_flag(c, \"b\"));\n"
     "  println(cli_flag(c, \"c\"));\n"
     "  println(cli_flag(c, \"d\"));\n"
     "  println(cli_sub(c));\n"
     "  println(cli_flag(c, \"quiet\"));\n}\n",
     "true\ntrue\ntrue\nfalse\nprog\ntrue\n"),
    ("missing opt returns \"\" and has_opt false; opt_or default",
     IMP + "fn main() {\n"
     "  let c: Cli = cli_parse([\"build\", \"--release\"]);\n"
     "  println(cli_opt(c, \"jobs\"));\n"
     "  println(cli_has_opt(c, \"jobs\"));\n"
     "  println(cli_opt_or(c, \"jobs\", \"1\"));\n"
     "  println(cli_opt_or(c, \"release\", \"x\"));\n}\n",
     "\nfalse\n1\n\n"),
    ("subcommand absent returns \"\"; no positionals",
     IMP + "fn main() {\n"
     "  let c: Cli = cli_parse([\"--verbose\", \"-q\"]);\n"
     "  println(cli_sub(c));\n"
     "  println(cli_pos_count(c));\n"
     "  println(cli_pos(c, 0));\n"
     "  println(cli_flag(c, \"verbose\"));\n"
     "  println(cli_flag(c, \"q\"));\n}\n",
     "\n0\n\ntrue\ntrue\n"),
    ("positional indexing incl. out-of-range \"\"",
     IMP + "fn main() {\n"
     "  let c: Cli = cli_parse([\"a\", \"b\", \"c\"]);\n"
     "  println(cli_pos(c, 0));\n"
     "  println(cli_pos(c, 2));\n"
     "  println(cli_pos(c, 3));\n"
     "  println(cli_pos(c, 99));\n"
     "  println(cli_pos(c, -1));\n"
     "  println(cli_pos_count(c));\n}\n",
     "a\nc\n\n\n\n3\n"),
    ("\"--\" separator stops flag parsing",
     IMP + "fn main() {\n"
     "  let c: Cli = cli_parse([\"run\", \"--\", \"--not-a-flag\", \"-x\", \"file.txt\"]);\n"
     "  println(cli_sub(c));\n"
     "  println(cli_flag(c, \"not-a-flag\"));\n"
     "  println(cli_flag(c, \"x\"));\n"
     "  println(cli_pos_count(c));\n"
     "  println(cli_pos(c, 1));\n"
     "  println(cli_pos(c, 2));\n"
     "  println(cli_pos(c, 3));\n}\n",
     "run\nfalse\nfalse\n4\n--not-a-flag\n-x\nfile.txt\n"),
    ("short -n value and long space form; -n value still positional in v1",
     IMP + "fn main() {\n"
     "  let c: Cli = cli_parse([\"prog\", \"-j\", \"2\", \"--out\", \"a.txt\"]);\n"
     "  println(cli_opt(c, \"j\"));\n"
     "  println(cli_opt(c, \"out\"));\n"
     "  println(cli_sub(c));\n"
     "  println(cli_pos_count(c));\n"
     "  println(cli_has_opt(c, \"j\"));\n"
     "  println(cli_pos(c, 1));\n}\n",
     "2\na.txt\nprog\n2\ntrue\n2\n"),
    ("--name= empty value; bare long flag consumes next arg",
     IMP + "fn main() {\n"
     "  let c: Cli = cli_parse([\"--out=\", \"--mode\", \"run\"]);\n"
     "  println(cli_opt(c, \"out\"));\n"
     "  println(cli_has_opt(c, \"out\"));\n"
     "  println(cli_opt(c, \"mode\"));\n"
     "  println(cli_sub(c));\n"
     "  println(cli_pos_count(c));\n}\n",
     "\ntrue\nrun\n\n0\n"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "cliparse_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("cliparse demo", r.returncode == 0 and r.stdout == DEMO_EXPECTED,
                 f"(rc={r.returncode} out={r.stdout!r} err={r.stderr[:200]!r})"):
        failures.append("cliparse demo")
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
    # fmt idempotent on both new files.
    for rel in ("forge_lang/stdlib/cliparse.fg", "examples/cliparse_demo.fg"):
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
    # No big32/WASM named-rejection checks: cliparse uses no
    # tuples, so both targets accept it.
    # ASan: the demo runs clean.
    with tempfile.TemporaryDirectory() as td:
        c_path = os.path.join(td, "cliparse.c")
        bin_path = os.path.join(td, "cliparse_asan")
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
    print(f"ALL PASS ({1 + len(OK_CASES) + 4 + 1} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
