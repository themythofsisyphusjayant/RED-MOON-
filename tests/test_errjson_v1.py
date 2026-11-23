"""Top-500 #341: structured error output as JSON (tests/test_errjson_v1.py).

Renders a compiler-style error as a JSON object string for editors:
error_to_json(code, message, file, line, col) and the multi-error
errors_to_json over parallel arrays, with ej_escape escaping quotes,
backslashes, newlines, tabs and carriage returns so the output is
real JSON. The escaper case is verified twice: exact stdout match
and a Python-side json.loads of the emitted line.

v1 limits (named in the catalog): this is the RENDERING as a
library only — it does not hook the compiler's own diagnostics (the
checker emits plain text and no E-codes); control characters other
than \\n, \\t and \\r pass through unescaped; errors_to_json
renders up to the shortest array when the parallel arrays disagree
in length. Both compilers (Python + hosted). Runs use cwd=ROOT
(like test_errcode_v1.py): the hosted binary resolves stdlib
imports relative to the repo root (forge_lang/stdlib/), so a temp
cwd would break every import.
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO_EXPECTED = """{"code":"E0001","message":"type mismatch: expected int, got str","file":"main.fg","line":3,"col":5}
{"code":"E0002","message":"undefined variable \\"total\\"","file":"main.fg","line":7,"col":1}
{"code":"E0003","message":"array index out of bounds\\ncheck the length first","file":"lib.fg","line":12,"col":9}
{"errors":[{"code":"E0004","message":"division by zero","file":"main.fg","line":1,"col":1},{"code":"E0005","message":"cannot read file","file":"data.txt","line":0,"col":0}]}
{"errors":[]}
"""

# (name, program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("escaper escapes quote, backslash, newline, tab and CR",
     r"""import "errjson.fg";
fn main() -> int {
  let m: str = "quote \" back \\ nl\n tab\t cr\r end";
  println(error_to_json("E0001", m, "a\"b.fg", -1, -2));
  return 0;
}
""",
     "{\"code\":\"E0001\",\"message\":\"quote \\\" back \\\\ nl\\n tab\\t cr\\r end\",\"file\":\"a\\\"b.fg\",\"line\":-1,\"col\":-2}\n",
     ""),
    ("ej_escape alone renders the escapes",
     r"""import "errjson.fg";
fn main() -> int {
  println(ej_escape("a\"b\\c"));
  println(ej_escape("x\ty"));
  return 0;
}
""",
     "a\\\"b\\\\c\nx\\ty\n",
     ""),
    ("plain message needs no escaping",
     r"""import "errjson.fg";
fn main() -> int {
  println(error_to_json("E0004", "division by zero", "main.fg", 0, 0));
  return 0;
}
""",
     """{"code":"E0004","message":"division by zero","file":"main.fg","line":0,"col":0}
""",
     ""),
    ("negative line and col render with a minus sign",
     r"""import "errjson.fg";
fn main() -> int {
  println(error_to_json("E0001", "m", "f.fg", -12, -345));
  return 0;
}
""",
     """{"code":"E0001","message":"m","file":"f.fg","line":-12,"col":-345}
""",
     ""),
    ("errors_to_json with mismatched lengths renders the shortest",
     r"""import "errjson.fg";
fn main() -> int {
  let codes: [str] = ["E0001", "E0002", "E0003"];
  let msgs: [str] = ["one", "two"];
  let files: [str] = ["a.fg", "b.fg", "c.fg", "d.fg"];
  let lines: [int] = [1, 2, 3];
  let cols: [int] = [1, 2, 3];
  println(errors_to_json(codes, msgs, files, lines, cols));
  return 0;
}
""",
     """{"errors":[{"code":"E0001","message":"one","file":"a.fg","line":1,"col":1},{"code":"E0002","message":"two","file":"b.fg","line":2,"col":2}]}
""",
     ""),
    ("errors_to_json with empty arrays renders an empty list",
     r"""import "errjson.fg";
fn main() -> int {
  println(errors_to_json([], [], [], [], []));
  return 0;
}
""",
     """{"errors":[]}
""",
     ""),
    ("code and file fields are escaped too",
     r"""import "errjson.fg";
fn main() -> int {
  println(error_to_json("E\"1", "m", "dir\\f.fg", 1, 1));
  return 0;
}
""",
     "{\"code\":\"E\\\"1\",\"message\":\"m\",\"file\":\"dir\\\\f.fg\",\"line\":1,\"col\":1}\n",
     ""),
]

# (name, program, error fragment) — must be rejected at check time.
REJECT_CASES = [
    ("error_to_json with too few arguments",
     r"""import "errjson.fg";
fn main() -> int {
  println(error_to_json("E0001", "m", "f.fg", 1));
  return 0;
}
""",
     "takes 5 argument(s), got 4"),
    ("errors_to_json with too few arguments",
     r"""import "errjson.fg";
fn main() -> int {
  let codes: [str] = ["E0001"];
  let msgs: [str] = ["m"];
  let files: [str] = ["f.fg"];
  println(errors_to_json(codes, msgs, files));
  return 0;
}
""",
     "takes 5 argument(s), got 3"),
    ("error_to_json with an int code",
     r"""import "errjson.fg";
fn main() -> int {
  println(error_to_json(42, "m", "f.fg", 1, 1));
  return 0;
}
""",
     "must be str, got int"),
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
    demo = os.path.join(ROOT, "examples", "errjson_demo.fg")
    lib = os.path.join(ROOT, "forge_lang", "stdlib", "errjson.fg")
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
    # The escaper output must be real JSON, not just the right
    # characters: parse the emitted line and check the fields.
    p = os.path.join(td, "c.fg")
    with open(p, "w") as f:
        f.write(OK_CASES[0][1])
    for mode, prefix in (("hosted", []), ("python", ["--python"])):
        rr = run_forge(prefix, ["run", p], ROOT)
        try:
            got = json.loads(rr.stdout.strip())
            ok = (rr.returncode == 0 and got == {
                "code": "E0001",
                "message": "quote \" back \\ nl\n tab\t cr\r end",
                "file": "a\"b.fg", "line": -1, "col": -2})
            detail = repr(got)
        except (ValueError, TypeError) as e:
            ok = False
            detail = f"json.loads failed: {e}: {rr.stdout!r}"
        if not check(f"escaped output parses as JSON ({mode})", ok, detail):
            failures.append(f"escaped output parses as JSON ({mode})")
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
