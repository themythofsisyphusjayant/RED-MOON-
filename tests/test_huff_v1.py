"""Top-500 #58: Huffman-lite coding v1 (tests/test_huff_v1.py).
Frequency-built Huffman codes over byte arrays, pure Qasida in
forge_lang/stdlib/huff.fg: the tree is built from frequencies with
an O(n^2) selection loop, codes are canonical, and the stream is
self-describing (symbol count, symbol + code-length pairs, original
length, packed bitstream). Single-symbol input gets a degenerate
code of length 1; empty input compresses to a header-only stream.
huff_decompress fail()s on a truncated or corrupt stream.
Every expected value below was hand-computed with an independent
Python replica (heapq, same tie-break rule) before the first run;
only round-trip equality, code lengths and compressed lengths are
asserted, never exact compressed bytes. No tuples are used anywhere,
so there is no big32/WASM named-rejection gate for this library.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

IMP = 'import "huff.fg";\n'

DEMO_EXPECTED = "14\ntrue\n16\ntrue\n9\ntrue\n6\ntrue\n1\n2\n"

EQ = ("fn arr_eq(a: [int], b: [int]) -> bool {\n"
      "  if len(a) != len(b) {\n    return false;\n  }\n"
      "  let mut i: int = 0;\n"
      "  while i < len(a) {\n"
      "    if a[i] != b[i] {\n      return false;\n    }\n"
      "    i = i + 1;\n  }\n  return true;\n}\n")

# (name, program, expected stdout) — must run clean.
OK_CASES = [
    ("round-trip on all 256 byte values 0..255",
     IMP + EQ + "fn main() {\n"
     "  let mut d: [int] = [];\n"
     "  let mut i: int = 0;\n"
     "  while i < 256 {\n    push(d, i);\n    i = i + 1;\n  }\n"
     "  println(huff_compressed_len(d));\n"
     "  println(arr_eq(huff_decompress(huff_compress(d)), d));\n"
     "  println(huff_code_len(d, 0));\n"
     "  println(huff_code_len(d, 255));\n}\n",
     "774\ntrue\n8\n8\n"),
    ("round-trip on a longer skewed input",
     IMP + EQ + "fn main() {\n"
     "  let mut d: [int] = [];\n"
     "  let mut i: int = 0;\n"
     "  while i < 100 {\n    push(d, 97);\n    i = i + 1;\n  }\n"
     "  i = 0;\n"
     "  while i < 50 {\n    push(d, 98);\n    i = i + 1;\n  }\n"
     "  i = 0;\n"
     "  while i < 25 {\n    push(d, 99);\n    i = i + 1;\n  }\n"
     "  i = 0;\n"
     "  while i < 12 {\n    push(d, 100);\n    i = i + 1;\n  }\n"
     "  i = 0;\n"
     "  while i < 6 {\n    push(d, 101);\n    i = i + 1;\n  }\n"
     "  i = 0;\n"
     "  while i < 3 {\n    push(d, 102);\n    i = i + 1;\n  }\n"
     "  push(d, 103);\n"
     "  println(huff_compressed_len(d));\n"
     "  println(arr_eq(huff_decompress(huff_compress(d)), d));\n"
     "  println(huff_code_len(d, 97));\n"
     "  println(huff_code_len(d, 103));\n}\n",
     "68\ntrue\n1\n6\n"),
    ("code-length ordering: frequent < rare, absent is 0",
     IMP + "fn main() {\n"
     "  let d: [int] = [97, 97, 97, 97, 97, 98, 98, 98, 99, 99];\n"
     "  println(huff_code_len(d, 97));\n"
     "  println(huff_code_len(d, 99));\n"
     "  println(huff_code_len(d, 97) < huff_code_len(d, 99));\n"
     "  println(huff_code_len(d, 100));\n}\n",
     "1\n2\ntrue\n0\n"),
    ("single-symbol round-trip",
     IMP + EQ + "fn main() {\n"
     "  let d: [int] = [122, 122, 122, 122, 122, 122];\n"
     "  println(huff_compressed_len(d));\n"
     "  println(arr_eq(huff_decompress(huff_compress(d)), d));\n"
     "  println(huff_code_len(d, 122));\n}\n",
     "9\ntrue\n1\n"),
    ("empty round-trip",
     IMP + EQ + "fn main() {\n"
     "  let d: [int] = [];\n"
     "  println(huff_compressed_len(d));\n"
     "  println(arr_eq(huff_decompress(huff_compress(d)), d));\n"
     "  println(huff_code_len(d, 97));\n}\n",
     "6\ntrue\n0\n"),
    ("two-symbol round-trip with equal lengths",
     IMP + EQ + "fn main() {\n"
     "  let d: [int] = [97, 98];\n"
     "  println(huff_compressed_len(d));\n"
     "  println(arr_eq(huff_decompress(huff_compress(d)), d));\n"
     "  println(huff_code_len(d, 97));\n"
     "  println(huff_code_len(d, 98));\n}\n",
     "11\ntrue\n1\n1\n"),
]

# (name, program) — must exit nonzero (fail() on a corrupt stream).
FAIL_CASES = [
    ("truncated bitstream fails",
     IMP + "fn main() {\n"
     "  let d: [int] = [97, 97, 97, 97, 97, 98, 98, 98, 99, 99];\n"
     "  let c: [int] = huff_compress(d);\n"
     "  let mut t: [int] = [];\n"
     "  let mut i: int = 0;\n"
     "  while i < len(c) - 1 {\n    push(t, c[i]);\n    i = i + 1;\n  }\n"
     "  let r: [int] = huff_decompress(t);\n"
     "  println(len(r));\n}\n"),
    ("empty stream fails",
     IMP + "fn main() {\n"
     "  let c: [int] = [];\n"
     "  let r: [int] = huff_decompress(c);\n"
     "  println(len(r));\n}\n"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "huff_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("huff demo", r.returncode == 0 and r.stdout == DEMO_EXPECTED,
                 f"(rc={r.returncode} out={r.stdout!r} err={r.stderr[:200]!r})"):
        failures.append("huff demo")
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
    for rel in ("forge_lang/stdlib/huff.fg", "examples/huff_demo.fg"):
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
    # ASan: the demo runs clean.
    with tempfile.TemporaryDirectory() as td:
        c_path = os.path.join(td, "huff.c")
        bin_path = os.path.join(td, "huff_asan")
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
    print(f"ALL PASS ({1 + len(OK_CASES) + len(FAIL_CASES) + 4 + 1} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
