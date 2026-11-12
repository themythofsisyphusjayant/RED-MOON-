#!/usr/bin/env python3
"""End-to-end test for the idle task (Phase F follow-up).

Fixes the known limitation stated in kernel_drivers.fg: with no
idle task, sleep() with no other ready task degraded to an
immediate resume instead of blocking. Here the scheduler runs an
idle task (slot 1, state 5) that waits for the next timer
interrupt whenever no task is ready, so sleep() actually blocks
until its wake tick.

The kernel (examples/os/kernel_idle.fg) spawns the idle task,
then one task A that sleeps 5 ticks with nobody else ready.
Main waits by sleeping 1 tick at a time, so at A's sleep both
main and A are asleep and only the idle task can run. A wakes
at its wake tick, prints 'A' plus the tick count at wake time,
exits, main prints DONE and the kernel halts.

Expects the exact transcript KERNA8DONE (measured 12 Nov 2026,
deterministic for this binary: A wakes at tick 8, >= the 5-tick
sleep; the tick count runs from boot, so pre-sleep setup latency
is included), halted, final states [running, idle, done, free],
idle pid 1, A pid 2, and a final tick count >= 5. Discrimination
against the old behaviour: with immediate resume A would have
printed at tick ~1 and the run would have ended at ~2 ticks, so
the wake tick >= 5 and final ticks >= 5 cannot pass on the old
code. Exits 0 only if every test passes.
"""
import importlib.util
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
MODEL = os.path.expanduser("~/workspace/big32/tools/model.py")
FAILURES = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def word(dmem, a):
    return (dmem[a] | (dmem[a + 1] << 8) |
            (dmem[a + 2] << 16) | (dmem[a + 3] << 24))


def main():
    print("idle task: sleep blocks with nobody ready (big32 model)")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "kern_idle")
        env = dict(os.environ, QASIDA_COMPILER="python")
        r = subprocess.run(FORGE + ["build", "--target", "big32",
                                    "--freestanding", "-o", out,
                                    "examples/os/kernel_idle.fg"],
                           capture_output=True, text=True, cwd=ROOT,
                           env=env)
        check("builds freestanding big32", r.returncode == 0, r.stderr[-200:])
        spec = importlib.util.spec_from_file_location("big32model", MODEL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        res = mod.run(out + ".hex")
        uart = res["uart"].decode("utf-8", "replace")
        check("exact transcript KERNA8DONE", uart == "KERNA8DONE", uart)
        check("halts", res["halted"] is True)
        d = res["dmem"]
        check("final states [running, idle, done, free]",
              [word(d, 0x8000 + 16 * i) for i in range(4)] == [2, 5, 3, 0])
        check("idle pid is slot 1", word(d, 0x8050) == 1,
              str(word(d, 0x8050)))
        check("child A pid is slot 2", word(d, 0x8044) == 2,
              str(word(d, 0x8044)))
        wake_tick = int(uart[5]) if len(uart) == 10 and uart[4] == "A" \
            and uart[5].isdigit() else -1
        check("wake tick >= sleep duration (5)", wake_tick >= 5,
              str(wake_tick))
        check("timer kept ticking to the end", word(d, 0x804C) >= 5,
              str(word(d, 0x804C)))
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
