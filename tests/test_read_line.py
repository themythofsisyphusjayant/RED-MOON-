#!/usr/bin/env python3
"""End-to-end tests for the read_line builtin (stdin, one line at a time).

Builds small Qasida programs that use read_line, feeds them piped
stdin, and asserts exact outputs. No network, no repo changes.

Tests:
  1. two lines echoed exactly
  2. five lines read in a loop (multi-line input)
  3. EOF returns the empty string (short input, extra read)
  4. empty stdin returns the empty string
  5. CRLF line endings are stripped (\\r and \\n)
  6. read_line() with an argument is a checker error
  7. WASM backend rejects read_line with a clear error
  8. big32 backend rejects read_line with a clear error
  9. lines longer than the 8192-byte buffer split across reads
     (8191 chars, then the remainder)

Exits 0 only if every test passes.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]

FAILURES = []


def run_fg(prog, stdin_text, *extra_args):
    """Write prog to a temp file, run it, return (rc, stdout, stderr)."""
    d = tempfile.mkdtemp(prefix="read-line-test-")
    path = os.path.join(d, "prog.fg")
    with open(path, "w") as f:
        f.write(prog)
    r = subprocess.run(FORGE + ["run", path] + list(extra_args),
                       input=stdin_text, capture_output=True, text=True,
                       timeout=60)
    return r.returncode, r.stdout, r.stderr


def run_cmd(prog, *args):
    """Run a forge.py subcommand on prog, return (rc, stdout, stderr)."""
    d = tempfile.mkdtemp(prefix="read-line-test-")
    path = os.path.join(d, "prog.fg")
    with open(path, "w") as f:
        f.write(prog)
    r = subprocess.run(FORGE + list(args) + [path],
                       capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout, r.stderr


def check(name, cond, detail=""):
    if cond:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name} {detail}")
        FAILURES.append(name)


ECHO2 = """fn main() -> int {
    let a: str = read_line();
    let b: str = read_line();
    println("a=[", a, "]");
    println("b=[", b, "]");
    return 0;
}
"""

LOOP5 = """fn main() -> int {
    for i in range(5) {
        let l: str = read_line();
        println(i, l);
    }
    return 0;
}
"""

LEN2 = """fn main() -> int {
    let a: str = read_line();
    println(len(a));
    let b: str = read_line();
    println(len(b));
    return 0;
}
"""


def main():
    rc, out, err = run_fg(ECHO2, "hello\nworld\n")
    check("1 two-lines", rc == 0 and out == "a=[ hello ]\nb=[ world ]\n",
          f"rc={rc} out={out!r} err={err!r}")

    rc, out, err = run_fg(LOOP5, "one\ntwo\nthree\nfour\nfive\n")
    check("2 five-lines-loop", rc == 0 and out == (
        "0 one\n1 two\n2 three\n3 four\n4 five\n"),
        f"rc={rc} out={out!r} err={err!r}")

    rc, out, err = run_fg(ECHO2, "only\n")
    check("3 eof-empty", rc == 0 and out == "a=[ only ]\nb=[  ]\n",
          f"rc={rc} out={out!r} err={err!r}")

    rc, out, err = run_fg(ECHO2, "")
    check("4 empty-stdin", rc == 0 and out == "a=[  ]\nb=[  ]\n",
          f"rc={rc} out={out!r} err={err!r}")

    rc, out, err = run_fg(ECHO2, "crline\r\nnext\n")
    check("5 crlf-stripped", rc == 0 and out == "a=[ crline ]\nb=[ next ]\n",
          f"rc={rc} out={out!r} err={err!r}")

    bad = "fn main() -> int {\n    let a: str = read_line(\"x\");\n    return 0;\n}\n"
    rc, out, err = run_cmd(bad, "check")
    check("6 arity-error", rc != 0 and "takes no arguments" in err,
          f"rc={rc} out={out!r} err={err!r}")

    rc, out, err = run_cmd(ECHO2, "emit-wasm", "-o",
                           os.path.join(tempfile.mkdtemp(), "o.wasm"))
    check("7 wasm-rejects", rc != 0 and "not supported" in err,
          f"rc={rc} out={out!r} err={err!r}")

    rc, out, err = run_cmd(ECHO2, "emit-big32")
    check("8 big32-rejects", rc != 0 and "not supported" in err,
          f"rc={rc} out={out!r} err={err!r}")

    rc, out, err = run_fg(LEN2, "x" * 9000 + "\n")
    check("9 long-line-splits", rc == 0 and out == "8191\n809\n",
          f"rc={rc} out={out!r} err={err!r}")

    if FAILURES:
        print(f"\n{len(FAILURES)} FAILURES: {', '.join(FAILURES)}")
        return 1
    print("\nALL READ_LINE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
