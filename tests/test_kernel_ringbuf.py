#!/usr/bin/env python3
"""Ring-buffer IPC driver kernel test (big32 model)."""
import importlib.util
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
MODEL = os.path.expanduser("~/workspace/big32/tools/model.py")
FAILURES = []
EXPECTED = 'RING\n2\n20\nDONE'

def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)

def word(dmem, a):
    return (dmem[a] | (dmem[a + 1] << 8) |
            (dmem[a + 2] << 16) | (dmem[a + 3] << 24))

def main():
    print("Ring-buffer IPC driver (big32 model)")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "kern_ringbuf")
        r = subprocess.run(FORGE + ["build", "--target", "big32",
                                    "--freestanding", "-o", out,
                                    "examples/os/kernel_ringbuf.fg"],
                           capture_output=True, text=True, cwd=ROOT)
        check("builds freestanding big32", r.returncode == 0, r.stderr[-200:])
        spec = importlib.util.spec_from_file_location("big32model", MODEL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        res = mod.run(out + ".hex")
        uart = res["uart"].decode("utf-8", "replace")
        check("exact transcript", uart == EXPECTED, repr(uart))
        check("halts", res["halted"] is True)
        check("final count 2", word(res["dmem"], 32768) == 2, word(res["dmem"], 32768))
        check("final head 20", word(res["dmem"], 32772) == 20, word(res["dmem"], 32772))
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0

if __name__ == "__main__":
    sys.exit(main())
