#!/usr/bin/env python3
"""Top-500 #38: stack-usage diagnostics v1 (tests/test_stackusage_v1.py).

`qasida stack <file.fg>` reports the max stack frame size per
Qasida function, measured from the real C compiler
(`cc -fstack-usage` at -O0, so no function is inlined away),
with a warning when a frame exceeds the 2048-byte kernel frame
budget (default limit, `--limit N` overrides it). Generic
instantiations report under their base name with the mangled C
symbol shown (identity_int), methods as Struct::method
(Point__sum), freestanding main as main (qasida_main), and
functions the C compiler never emits (an uninstantiated generic)
as "not emitted". Runtime helpers (forge_*) are summarized, not
listed. Native only in v1: stack frames are a C-backend concept;
big32/WASM have no C to measure.
"""

import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO = os.path.join(ROOT, "examples", "stackusage_demo.fg")
DEMO_EXPECTED = "90\n"

BIG_FRAME_PROG = (
    "fn many_locals() -> int {\n"
    + "".join(f"  let v{i}: int = {i};\n" for i in range(300))
    + "  return " + " + ".join(f"v{i}" for i in range(300)) + ";\n}\n"
    "fn small(x: int) -> int {\n  return x + 1;\n}\n"
    "fn main() {\n  println(small(1) + many_locals());\n}\n"
)
BIG_FRAME_EXPECTED = "44852\n"

METHOD_PROG = (
    "struct Point {\n  x: int,\n  y: int,\n}\n"
    "impl Point {\n  fn sum(p: Point) -> int {\n    return p.x + p.y;\n  }\n}\n"
    "fn main() {\n  let p: Point = Point { x: 3, y: 4 };\n"
    "  println(p.sum());\n}\n"
)

FREESTANDING_PROG = (
    "fn helper(x: int) -> int {\n  let y: int = x + 1;\n  return y;\n}\n"
    "fn main() {\n  let v: int = helper(3);\n  poke32(4096, v);\n}\n"
)

UNUSED_GENERIC_PROG = (
    "fn unused<T>(v: T) -> T {\n  return v;\n}\n"
    "fn used(x: int) -> int {\n  return x + 1;\n}\n"
    "fn main() {\n  println(used(1));\n}\n"
)

BAD_PROG = "fn main() {\n  println(nope);\n}\n"

ROW_RE = re.compile(r"^  (.+?): (\d+) bytes \((.*)\)$")


def run(args, cwd=ROOT):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def stack(args, prog=None):
    """Run `forge.py stack` on prog (written to a temp .fg file)."""
    if prog is None:
        return run([sys.executable, os.path.join(ROOT, "forge.py"),
                    "stack"] + args)
    with tempfile.NamedTemporaryFile("w", suffix=".fg", delete=False,
                                    dir=ROOT) as f:
        f.write(prog)
        path = f.name
    try:
        return run([sys.executable, os.path.join(ROOT, "forge.py"),
                    "stack", path] + args)
    finally:
        os.unlink(path)


def main():
    failures = []
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", DEMO])
    if not check("stackusage demo runs", r.returncode == 0
                 and r.stdout == DEMO_EXPECTED,
                 f"(rc={r.returncode} out={r.stdout!r} "
                 f"err={r.stderr[:200]!r})"):
        failures.append("demo runs")
    r = stack([DEMO])
    ok = (r.returncode == 0 and "add_pair" in r.stdout
          and "main" in r.stdout and "max frame" in r.stdout
          and "warning" not in r.stdout
          and "measured at -O0" in r.stdout)
    if not check("stack demo: small frames, no warning", ok,
                 f"(rc={r.returncode} out={r.stdout[:300]!r} "
                 f"err={r.stderr[:200]!r})"):
        failures.append("stack demo")
    rows = {}
    for line in r.stdout.splitlines():
        m = ROW_RE.match(line)
        if m:
            rows[m.group(1)] = (int(m.group(2)), m.group(3))
    max_line = [ln for ln in r.stdout.splitlines()
                if ln.startswith("max frame: ")]
    ok = ("add_pair" in rows and "main" in rows
          and all(size > 0 for size, _ in rows.values())
          and len(max_line) == 1
          and max_line[0].split(": ")[1].split(",")[0]
          == max(rows, key=lambda k: rows[k][0]))
    if not check("frame table parses; max names the largest", ok,
                 f"(rows={rows!r} max={max_line!r})"):
        failures.append("frame table")
    r = stack([], BIG_FRAME_PROG)
    ok = (r.returncode == 0 and "many_locals" in r.stdout
          and "warning" in r.stdout and "2048" in r.stdout
          and "max frame: many_locals" in r.stdout)
    if not check("big frame: warning over 2048, max is many_locals", ok,
                 f"(rc={r.returncode} out={r.stdout[:400]!r} "
                 f"err={r.stderr[:200]!r})"):
        failures.append("big frame")
    # The big-frame program really runs (its frame is real, not
    # dead code the compiler dropped).
    with tempfile.NamedTemporaryFile("w", suffix=".fg", delete=False,
                                    dir=ROOT) as f:
        f.write(BIG_FRAME_PROG)
        big_path = f.name
    try:
        rb = run([sys.executable, os.path.join(ROOT, "forge.py"),
                  "run", big_path])
        ok = rb.returncode == 0 and rb.stdout == BIG_FRAME_EXPECTED
        if not check("big-frame program runs", ok,
                     f"(rc={rb.returncode} out={rb.stdout!r} "
                     f"err={rb.stderr[:200]!r})"):
            failures.append("big-frame runs")
    finally:
        os.unlink(big_path)
    r = stack(["--limit", "0", DEMO])
    ok = r.returncode == 0 and "warning" in r.stdout
    if not check("--limit 0 warns on every frame", ok,
                 f"(rc={r.returncode} out={r.stdout[:200]!r})"):
        failures.append("limit 0")
    r = stack(["--limit", "100000"], BIG_FRAME_PROG)
    ok = r.returncode == 0 and "warning" not in r.stdout
    if not check("--limit 100000 silences the warning", ok,
                 f"(rc={r.returncode} out={r.stdout[:200]!r})"):
        failures.append("limit high")
    r = stack([DEMO])
    ok = "identity_int" in r.stdout
    if not check("generic instantiation shown (identity_int)", ok,
                 f"(out={r.stdout[:300]!r})"):
        failures.append("generic label")
    r = stack([], METHOD_PROG)
    ok = r.returncode == 0 and "Point::sum" in r.stdout
    if not check("method shown as Point::sum", ok,
                 f"(rc={r.returncode} out={r.stdout[:300]!r} "
                 f"err={r.stderr[:200]!r})"):
        failures.append("method label")
    r = stack(["--freestanding"], FREESTANDING_PROG)
    ok = (r.returncode == 0 and "main:" in r.stdout
          and "helper:" in r.stdout and "qasida_main" not in r.stdout)
    if not check("freestanding: qasida_main reported as main", ok,
                 f"(rc={r.returncode} out={r.stdout[:300]!r} "
                 f"err={r.stderr[:200]!r})"):
        failures.append("freestanding")
    r = stack([], UNUSED_GENERIC_PROG)
    ok = (r.returncode == 0 and "unused: not emitted" in r.stdout
          and "used:" in r.stdout)
    if not check("uninstantiated generic is 'not emitted'", ok,
                 f"(rc={r.returncode} out={r.stdout[:300]!r})"):
        failures.append("not emitted")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "stack",
             os.path.join(ROOT, "examples", "no_such_file.fg")])
    ok = r.returncode != 0 and "error" in r.stderr
    if not check("missing file errors", ok,
                 f"(rc={r.returncode} err={r.stderr[:200]!r})"):
        failures.append("missing file")
    r = stack([], BAD_PROG)
    ok = r.returncode != 0 and "error" in r.stderr
    if not check("checker error fails the stack report", ok,
                 f"(rc={r.returncode} err={r.stderr[:200]!r})"):
        failures.append("checker error")
    rf = run([sys.executable, os.path.join(ROOT, "forge.py"),
              "fmt", "--check", DEMO])
    if not check("fmt idempotent (demo)", rf.returncode == 0,
                 rf.stderr.strip()):
        failures.append("fmt")
    # ASan: the demo runs clean.
    with tempfile.TemporaryDirectory() as td:
        c_path = os.path.join(td, "stackusage.c")
        bin_path = os.path.join(td, "stackusage_asan")
        r = run([sys.executable, os.path.join(ROOT, "forge.py"),
                 "emit", DEMO])
        with open(c_path, "w") as f:
            f.write(r.stdout)
        cc = run(["cc", "-g", "-fsanitize=address", "-o", bin_path,
                  c_path, "-lssl", "-lcrypto", "-lm"])
        if cc.returncode != 0:
            check("ASan build", False, f"(cc err={cc.stderr[:300]!r})")
            failures.append("ASan build")
        else:
            r = run([bin_path])
            ok = r.returncode == 0 and r.stdout == DEMO_EXPECTED
            if not check("ASan run clean", ok,
                         f"(rc={r.returncode} out={r.stdout!r} "
                         f"err={r.stderr[:300]!r})"):
                failures.append("ASan run")
    if failures:
        print(f"FAILURES: {len(failures)}: {failures}")
        return 1
    print("ALL PASS (14 checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
