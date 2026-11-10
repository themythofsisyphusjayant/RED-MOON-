#!/usr/bin/env python3
"""Native OS apps test (forge run, no kernel simulation).

Covers the 9 Nov 2026 daily-ten OS track: ten standalone native
OS subsystem demos under examples/os/app_*.fg, plus the 10 Nov 2026
daily-ten OS track (app_net, app_uptime, app_mount, app_kill,
app_nice, app_top, app_jobs, app_history, app_alias, app_chmod).
Each is run with `forge.py run` and its stdout must match the
hand-computed expected transcript exactly. No freestanding build,
no big32 model, no Verilog sim — these run on the native backend
only, so they are safe to run while a big32 diagnostic sim is
running.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
FAILURES = []

EXPECTED = {
    "app_shell": "help: h f c\nfiles: a.txt b.txt\ncleared\n?\n(empty)\n",
    "app_ps": "1 init run\n2 sh sleep\n3 http run\n1 init run\n3 http run\n",
    "app_fs": "a.txt b.txt c.txt\nworld\nb.txt c.txt\n",
    "app_sched": "A\nB\nC\nA\nB\nA\n",
    "app_ipc": "3\nhi\nyo\nbye\n0\n",
    "app_mem": "0\n16\n48\n968\n-1\n",
    "app_clock": "100\n1000\n1\n1\n1\n1\n",
    "app_users": "true\nfalse\ntrue\nfalse\n3\n",
    "app_log": "3\nlogin\nhttp\nshutdown\n",
    "app_disk": "42\n7\n0\n99\n0\n",
    "app_net": "lo up 127.0.0.1\neth0 up 10.0.0.2\nping 127.0.0.1: 0ms\nping 10.0.0.2: 1ms\n",
    "app_uptime": "1\n1\n1\n1\n90061\n",
    "app_mount": "/dev/sda1 on / ext4\n/dev/sda2 on /home ext4\ntmpfs on /tmp tmpfs\n3\n",
    "app_kill": "15\n9\nTERM\nKILL\nterminated\nkilled\nunknown\n",
    "app_nice": "-20\n19\n5\n10\n",
    "app_top": "sh 40\nhttp 25\ninit 5\n",
    "app_jobs": "1 running sleep\n2 stopped vim\n1\n",
    "app_history": "1 ls\n2 ps\n3 df\nps\n",
    "app_alias": "ls -l\ncd ..\nps\n",
    "app_chmod": "rwxr-xr-x\nrw-r--r--\nrw-------\n",
}


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def main():
    print("native OS apps (forge run)")
    for name, expected in EXPECTED.items():
        path = os.path.join("examples", "os", name + ".fg")
        r = subprocess.run(FORGE + ["run", path],
                           capture_output=True, text=True, cwd=ROOT)
        check(name + " runs", r.returncode == 0, r.stderr[-200:])
        check(name + " exact output", r.stdout == expected,
              repr(r.stdout))
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
