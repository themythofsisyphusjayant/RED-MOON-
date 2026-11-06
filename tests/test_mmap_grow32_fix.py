"""Fix track: mmap grow + word-width access
(tests/test_mmap_grow32_fix.py). mmap_grow extends
the file (ftruncate) and remaps it under the same
id; mmap_get32/mmap_set32 read and write a 32-bit
little-endian word at a byte offset (zero-extended,
like peek32). Grow-only in v1 (no shrink), 32-bit
words only, native only; big32 and WASM reject mmap
programs with a named error.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

EXPECTED = "305419896\n305419896\n16\n0\n42\n16\n120\n42\n"

DEMO_TMPL = (
    "fn main() {{\n"
    "  let path = \"{path}\";\n"
    "  let ok = write_bytes(path, [120, 86, 52, 18, 1, 0, 0, 0]);\n"
    "  let m = mmap_open(path);\n"
    "  println(mmap_get32(m, 0));\n"
    "  mmap_set32(m, 4, 305419896);\n"
    "  println(mmap_get32(m, 4));\n"
    "  let n = mmap_grow(m, 16);\n"
    "  println(n);\n"
    "  println(mmap_get32(m, 12));\n"
    "  mmap_set32(m, 12, 42);\n"
    "  println(mmap_get32(m, 12));\n"
    "  mmap_close(m);\n"
    "  let back = read_bytes(path);\n"
    "  println(len(back));\n"
    "  println(back[0]);\n"
    "  println(back[12]);\n"
    "}}\n"
)

CASES = [
    ("grow to same size fails",
     "fn main() {\n  let path = \"{path}\";\n"
     "  let ok = write_bytes(path, [1, 2]);\n"
     "  let m = mmap_open(path);\n"
     "  let n = mmap_grow(m, 2);\n}\n",
     "mmap: new size must be larger than current size"),
    ("grow to smaller size fails",
     "fn main() {\n  let path = \"{path}\";\n"
     "  let ok = write_bytes(path, [1, 2, 3, 4]);\n"
     "  let m = mmap_open(path);\n"
     "  let n = mmap_grow(m, 3);\n}\n",
     "mmap: new size must be larger than current size"),
    ("get32 past the end fails",
     "fn main() {\n  let path = \"{path}\";\n"
     "  let ok = write_bytes(path, [1, 2, 3, 4, 5, 6, 7, 8]);\n"
     "  let m = mmap_open(path);\n"
     "  println(mmap_get32(m, 6));\n}\n",
     "mmap index out of bounds"),
    ("set32 past the end fails",
     "fn main() {\n  let path = \"{path}\";\n"
     "  let ok = write_bytes(path, [1, 2, 3, 4, 5, 6, 7, 8]);\n"
     "  let m = mmap_open(path);\n"
     "  mmap_set32(m, 5, 9);\n}\n",
     "mmap index out of bounds"),
    ("get32 on a closed mapping fails",
     "fn main() {\n  let path = \"{path}\";\n"
     "  let ok = write_bytes(path, [1, 2, 3, 4]);\n"
     "  let m = mmap_open(path);\n"
     "  mmap_close(m);\n"
     "  println(mmap_get32(m, 0));\n}\n",
     "mmap: unknown mapping"),
    ("grow on a closed mapping fails",
     "fn main() {\n  let path = \"{path}\";\n"
     "  let ok = write_bytes(path, [1, 2, 3, 4]);\n"
     "  let m = mmap_open(path);\n"
     "  mmap_close(m);\n"
     "  let n = mmap_grow(m, 8);\n}\n",
     "mmap: unknown mapping"),
    ("get32 with one argument is a compile error",
     "fn main() {\n  let path = \"{path}\";\n"
     "  let ok = write_bytes(path, [1, 2, 3, 4]);\n"
     "  let m = mmap_open(path);\n"
     "  println(mmap_get32(m));\n}\n",
     "mmap_get32() takes a mapping id and a byte offset"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "d.fg")
        with open(p, "w") as f:
            f.write(DEMO_TMPL.format(path=os.path.join(td, "d.bin")))
        r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", p],
                ROOT)
        if not check("mmap grow32 demo runs", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append("mmap grow32 demo runs")
        elif not check("mmap grow32 results", r.stdout == EXPECTED,
                       repr(r.stdout)):
            failures.append("mmap grow32 results")
        for name, prog, frag in CASES:
            cp = os.path.join(td, "c.fg")
            with open(cp, "w") as f:
                f.write(prog.replace("{path}", os.path.join(td, "c.bin")))
            rr = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", cp],
                     ROOT)
            ok = rr.returncode != 0 and frag in (rr.stderr + rr.stdout)
            if not check(f"{name}", ok,
                         (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(name)
        # Backend gates: big32 and WASM still reject mmap programs.
        gp = os.path.join(td, "g.fg")
        with open(gp, "w") as f:
            f.write(DEMO_TMPL.format(path=os.path.join(td, "g.bin")))
        for cmd, frag in (("emit-big32", "mmap is not supported"),
                          ("emit-wasm", "mmap is not supported")):
            rr = run([sys.executable, os.path.join(ROOT, "forge.py"),
                      cmd, gp], ROOT)
            ok = rr.returncode != 0 and frag in (rr.stderr + rr.stdout)
            if not check(f"{cmd} rejects mmap", ok,
                         (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(f"{cmd} rejects mmap")
    fmt = os.path.join(ROOT, "examples", "mmap_grow32_demo.fg")
    rf = run([sys.executable, os.path.join(ROOT, "forge.py"), "fmt", fmt],
             ROOT)
    if not check("fmt runs", rf.returncode == 0, rf.stderr.strip()):
        failures.append("fmt runs")
    else:
        rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"),
                   "fmt", "--check", fmt], ROOT)
        if not check("fmt idempotent", rf2.returncode == 0, rf2.stderr.strip()):
            failures.append("fmt idempotent")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
