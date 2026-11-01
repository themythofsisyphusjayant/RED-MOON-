"""Top-500 #31: memory-mapped files v1
(tests/test_mmap_v1.py). A runtime mmap table:
mmap_open maps a file, mmap_get reads bytes through
the mapping, mmap_set writes through into the file
itself, mmap_close munmaps. Native-only in v1;
big32 and WASM reject mmap programs.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

EXPECTED = "72\n111\n74\n"

DEMO_TMPL = (
    "fn main() {{\n"
    "  let path = \"{path}\";\n"
    "  let ok = write_bytes(path, [72, 101, 108, 108, 111]);\n"
    "  let m = mmap_open(path);\n"
    "  println(mmap_get(m, 0));\n"
    "  println(mmap_get(m, 4));\n"
    "  mmap_set(m, 0, 74);\n"
    "  mmap_close(m);\n"
    "  let back = read_bytes(path);\n"
    "  println(back[0]);\n"
    "}}\n"
)

CASES = [
    ("mmap_open missing file",
     "fn main() {\n  let m = mmap_open(\"/tmp/jalpari_mmap_nope.bin\");\n}\n",
     "mmap: cannot open file"),
    ("mmap_get out of bounds",
     "fn main() {\n  let path = \"{path}\";\n"
     "  let ok = write_bytes(path, [1, 2]);\n"
     "  let m = mmap_open(path);\n"
     "  println(mmap_get(m, 5));\n}\n",
     "mmap index out of bounds"),
    ("mmap_close twice",
     "fn main() {\n  let path = \"{path}\";\n"
     "  let ok = write_bytes(path, [1, 2]);\n"
     "  let m = mmap_open(path);\n"
     "  mmap_close(m);\n"
     "  mmap_close(m);\n}\n",
     "mmap: already closed"),
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
        if not check("mmap demo runs", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append("mmap demo runs")
        elif not check("mmap results", r.stdout == EXPECTED,
                       repr(r.stdout)):
            failures.append("mmap results")
        for name, prog, frag in CASES:
            cp = os.path.join(td, "c.fg")
            with open(cp, "w") as f:
                f.write(prog.replace("{path}", os.path.join(td, "c.bin")))
            rr = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", cp],
                     ROOT)
            ok = rr.returncode != 0 and frag in (rr.stderr + rr.stdout)
            if not check(f"{name} fails", ok,
                         (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(name)
    fmt = os.path.join(ROOT, "examples", "mmap_demo.fg")
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
