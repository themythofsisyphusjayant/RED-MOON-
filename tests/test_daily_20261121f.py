#!/usr/bin/env python3
"""Daily-ten 21 Nov 2026 — library sprint batch 6 (20 new libraries).

Runs each demo under `forge.py run` with BOTH compilers (hosted
default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly. Expected values were hand-derived
BEFORE the first run (independent Python replica;
~/workspace/blackmoon-iso/daily-20261121-batch6/replica_20261121f.py),
including HTML entity escaping, stdin parsing, structured-log
rendering, rotary position embeddings, AUC / log-loss / top-k /
Brier, z-score and min-max scaling plus k-fold splits, semver
constraints, highest-satisfying-version resolution, dbg lines,
allocation-counter deltas (probed under both compilers),
flame-graph SVG, health JSON, the seeded LCG replay, CRC32
dataset manifests, constant-time comparison, secret redaction /
zeroing, permission prefix checks, lockfile parsing plus
SHA-256, vulnerability matching, and JSON depth limits.

stdio_demo reads two lines from stdin: the harness feeds
"42\\n-7\\n" to that demo only; every other demo runs with
stdin as /dev/null so no demo can block on input.

Usage:
  python3 tests/test_daily_20261121f.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE_PY = os.environ.get(
    "FORGE_PY", os.path.expanduser("~/workspace/forge-v2/forge.py"))
FORGE = [sys.executable, FORGE_PY]
FAILURES = []

EXPECTED = {
    "esc_demo": ("Hello &lt;b&gt;Ada&lt;/b&gt;!\n"
                 "<p>a &amp; b</p>\n"
                 "<li>&lt;x&gt;</li><li>a&amp;b</li>\n"
                 "\n"
                 "Hi &lt;Bo&gt;\n"
                 "a&quot;b\n"),
    "stdio_demo": "42\n42\n-7\n0\ndone\n",
    "logfmt_demo": ("level=INFO msg=\"started\" port=8080\n"
                    "level=WARN msg=\"slow query\" ms=250\n"
                    "level=DEBUG msg=\"cache\" hit=true key=user:7\n"
                    "0\n"
                    "level=ERROR msg=\"boom\" code=500\n"
                    "1\n"
                    "ERROR\n"),
    "rope_demo": ("1\n0.01\n0.02\n0.540302\n0.841471\n-0.00999983\n"
                  "0.99995\n3\n4\n"),
    "metrics2_demo": "0.75\n0.164252\n1\n0\n1\n0.025\n",
    "sklearn2_demo": ("3\n1.41421\n-1.41421\n-0.707107\n0\n0.707107\n"
                      "1.41421\n0\n0.25\n0.5\n0.75\n1\n0\n1\n2\n3\n8\n9\n"),
    "semver2_demo": "true\nfalse\ntrue\nfalse\ntrue\nfalse\ntrue\nfalse\n",
    "resolver_demo": "1.2.0\n2.0.0\n2.0.0\nnone\nnone\ntrue\nfalse\n",
    "dbg_demo": ("count = 5\npi = 3.5\nflag = true\nname = ada\n"
                 "6\n3.5\ntrue\nada\n"),
    "memprof_demo": "1\n1\n0\n1\n1\n0\nxyyyyy\n3\n3\n",
    "flame_demo": ("4000\n300\n100\n"
                   "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"400\" height=\"20\">"
                   "<rect x=\"0\" y=\"0\" width=\"300\" height=\"20\" fill=\"steelblue\"/>"
                   "<text x=\"5\" y=\"15\">parse</text>"
                   "<rect x=\"300\" y=\"0\" width=\"100\" height=\"20\" fill=\"orange\"/>"
                   "<text x=\"305\" y=\"15\">emit</text></svg>\n"),
    "health_demo": ("ok\n"
                    "{\"status\":\"ok\",\"uptime_s\":3600,\"checks\":["
                    "{\"name\":\"db\",\"ok\":true,\"ms\":12},"
                    "{\"name\":\"cache\",\"ok\":true,\"ms\":3}]}\n"
                    "true\nfalse\ndegraded\n"),
    "replay_demo": ("1282168119\n317105233\n60898434\n2088767471\n"
                    "1228256628\ntrue\nfalse\n"),
    "dvc_demo": ("true\ntrue\n907060870\n980881731\n"
                 "a.txt 907060870\nb.txt 980881731\n"
                 "true\n2592524640\n1\nfalse\ntrue\n"),
    "ct_demo": "true\nfalse\nfalse\ntrue\nfalse\nfalse\n",
    "secrets_demo": "7\n***\nfalse\ntrue\n7\n7\n",
    "perms_demo": "true\nfalse\nfalse\ntrue\nfalse\ntrue\nfalse\n",
    "lock_demo": ("zlib==1.3.0 #abc123\nzlib\n1.3.0\nabc123\ntrue\nfalse\n"
                  "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824\n"),
    "vuln_demo": "1\n0\n0\n1\ntrue\nfalse\n",
    "safedeser_demo": "true\n1\nfalse\n6\nfalse\ntrue\n1\nfalse\n",
}

INPUT = {
    "stdio_demo": "42\n-7\n",
}


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def run_one(name, expected, env_extra):
    path = os.path.join(ROOT, "examples", name + ".fg")
    env = dict(os.environ)
    env.update(env_extra)
    kwargs = {"capture_output": True, "text": True, "cwd": ROOT,
              "env": env, "timeout": 180}
    if name in INPUT:
        kwargs["input"] = INPUT[name]
    else:
        kwargs["stdin"] = subprocess.DEVNULL
    try:
        r = subprocess.run(FORGE + ["run", path], **kwargs)
    except subprocess.TimeoutExpired:
        check(f"{name} runs", False, "TIMEOUT after 180s")
        return
    check(f"{name} runs rc=0", r.returncode == 0, r.stderr[-300:])
    check(f"{name} exact stdout", r.stdout == expected,
          "" if r.stdout == expected else f"got: {r.stdout!r}")


def main():
    print("daily-ten 21 Nov 2026 — library sprint batch 6 (20 items x 2 compilers)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
