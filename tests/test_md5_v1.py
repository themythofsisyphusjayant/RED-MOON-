"""Top-500 #61: MD5 message digest, RFC 1321 (tests/test_md5_v1.py).
Pure Qasida in forge_lang/stdlib/md5.fg: all four rounds with the
RFC 1321 K constants and per-round shift amounts, 32-bit wrapping
arithmetic (the hashlib.fg pattern), little-endian message words
and little-endian length padding. md5_hex takes ASCII text in v1
(bytes map through the printable-ASCII table, the base64.fg
idiom); md5_bytes takes raw byte values 0..255 directly.
Every expected digest below was hand-computed with an
independent Python replica (hashlib.md5) before the first
Qasida run — never copied from Qasida output.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

IMP = 'import "md5.fg";\n'

DEMO_EXPECTED = ("d41d8cd98f00b204e9800998ecf8427e\n"
                 "900150983cd24fb0d6963f7d28e17f72\n"
                 "9e107d9d372bb6826bd81d3542a419d6\n"
                 "d43e61e9b5f8c9d22c4dc5db6e6df775\n")

# (name, program, expected stdout) — must run clean.
OK_CASES = [
    ("RFC 1321 vector: message digest",
     IMP + "fn main() {\n  println(md5_hex(\"message digest\"));\n}\n",
     "f96b697d7cb7938d525a2f31aaf161d0\n"),
    ("RFC 1321 vector: lowercase alphabet",
     IMP + "fn main() {\n  println(md5_hex(\"abcdefghijklmnopqrstuvwxyz\"));\n}\n",
     "c3fcd3d76192e4007dfb496cca67e13b\n"),
    ("RFC 1321 vector: 62-byte alphanumeric (two blocks)",
     IMP + "fn main() {\n  println(md5_hex(\"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789\"));\n}\n",
     "d174ab98d277d9f5a5611c2c9f419d9f\n"),
    ("RFC 1321 vector: 1234567890 repeated 8 times (80 bytes)",
     IMP + "fn main() {\n  println(md5_hex(\"12345678901234567890123456789012345678901234567890123456789012345678901234567890\"));\n}\n",
     "57edf4a22be3c955ac49da2e2107b67a\n"),
    ("md5_bytes: 16 bytes out, first byte of abc is 0x90 (144)",
     IMP + "fn main() {\n  let d: [int] = md5_bytes([97, 98, 99]);\n"
     "  println(len(d));\n  println(d[0]);\n}\n",
     "16\n144\n"),
    ("md5_bytes of empty: 16 bytes out, first byte 212",
     IMP + "fn main() {\n  let d: [int] = md5_bytes([]);\n"
     "  println(len(d));\n  println(d[0]);\n}\n",
     "16\n212\n"),
    ("55-byte vs 56-byte boundary pair (one block vs two)",
     IMP + "fn main() {\n  let mut a55: str = \"\";\n"
     "  let mut a56: str = \"\";\n"
     "  let mut i: int = 0;\n"
     "  while i < 55 {\n    a55 = a55 + \"a\";\n    a56 = a56 + \"a\";\n    i = i + 1;\n  }\n"
     "  a56 = a56 + \"a\";\n"
     "  println(md5_hex(a55));\n  println(md5_hex(a56));\n}\n",
     "ef1772b6dff9a122358552954ad0df65\n"
     "3b0c8ac703f828b04c6c197006d17218\n"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "md5_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("md5 demo", r.returncode == 0 and r.stdout == DEMO_EXPECTED,
                 f"(rc={r.returncode} out={r.stdout!r} err={r.stderr[:200]!r})"):
        failures.append("md5 demo")
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
    for rel in ("forge_lang/stdlib/md5.fg", "examples/md5_demo.fg"):
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
    # No big32/WASM rejection checks: md5.fg uses no tuples, so the
    # named-rejection gate does not apply to this library.
    # ASan: the demo runs clean.
    with tempfile.TemporaryDirectory() as td:
        c_path = os.path.join(td, "md5.c")
        bin_path = os.path.join(td, "md5_asan")
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
