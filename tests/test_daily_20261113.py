#!/usr/bin/env python3
"""Daily-ten 13 Nov 2026 - library demos (forge run).

Ten NEW pure-Qasida stdlib modules (plus demos), each for a roadmap
item that had no module. Every demo is run with `forge.py run` under
both compilers and its stdout must match the expected transcript
exactly. All expectations were hand-computed (or computed with an
independent Python model) BEFORE running.
- aes (#67 aes-lite): AES-128 single-block encrypt; FIPS-197 vector
  + all-zero vector, verified against an independent pure-Python
  AES-128 reference (which itself reproduces the FIPS vector).
- async (#69 async-lite): spawn/scope structured concurrency;
  workers write marker files, scope joins, main reads them back.
  Marker files are pre-seeded "pending-*" so a worker that never
  ran would show in the output.
- channels (#70): single-owner FIFO queues (int + string).
- datetime (#21, substituted for #79): ISO date/time format +
  parse + round-trip. #79 property-test already existed
  (stdlib/property.fg + examples/property_demo.fg, both passing
  under both compilers), so datetime fills this slot instead.
- shell (#55 shell-utils): exec-lite over run_command; the echo
  runs first because println output is stdio-buffered when piped
  while the child writes directly.
- canvas (#104): in-memory pixel buffer, rect/line/circle +
  ASCII render; expected rows from an independent Python model
  of the same Bresenham (both step tests are independent ifs).
- font (#105 font-plus): 5x7 glyphs for space, A-Z, 0-9; renders
  "HI 12". Expected rows from the Python glyph table that
  generated font.fg (trailing spaces are significant).
- frames (#14 frames-fast): filter-eq / filter-lt / project /
  head over pandas.fg. (No trailing comma in struct literals:
  the first frames_demo failed to parse on one - fixed.)
- huffman (#58): fixed a=0,b=10,c=110,d=111 codes; round-trip.
- tablestore (#20, the 10th item): file-backed insert/select/
  delete. #72 parallel was probed and SKIPPED for this slot:
  parallel_dot/matmul are real pthread builtins and work under
  both compilers, but they cover only dot/matmul/reduce - no
  parallel map/filter primitive exists to build on, and spawn
  takes only void fns of 0/1 int with no return, so a general
  parallel map cannot be expressed honestly.
Verified 13 Nov 2026: 10/10 under the Python reference compiler,
10/10 under the hosted compiler (bin/qasida-hosted, rebuild4).
No hosted divergences, no skipped hosted checks.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
FAILURES = []

EXPECTED = {
    'aes_demo': '69c4e0d86a7b0430d8cdb78070b4c55a\n66e94bd4ef8a2c3b884cfa59ca342b2e\n',
    'async_demo': 'spawning\njoined\nmarker-1\nmarker-2\n',
    'channels_demo': '10\n20\n2\n30\n40\ntrue\nhello\n',
    'datetime_demo': '2026-11-13\n09:05:07\n2026\n11\n13\ntrue\n9\n5\n7\n',
    'shell_demo': 'hello-shell\n0\n0\n1\ntrue\n',
    'canvas_demo': '##........\n.####..#..\n.########.\n......##..\n........##\n',
    'font_demo': '#   #  ###          #    ### \n#   #   #          ##   #   #\n#   #   #           #       #\n#####   #           #     ## \n#   #   #           #    #   \n#   #   #           #   #    \n#   #  ###         ###  #####\n37\n',
    'frames_demo': '4\n2\n4\n10\n40\n2\n',
    'huffman_demo': '01001100100111\nabacabad\ntrue\n111\nd\n',
    'tablestore_demo': '3\n3\n1,ana,10\n1\n2,bo,20\n2\n',
}


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def run_demo(name, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(FORGE + ["run", os.path.join("examples", name + ".fg")],
                          capture_output=True, text=True, cwd=ROOT, env=env)


def main():
    print("daily-ten 13 Nov 2026 library demos (forge run)")
    for name, expected in EXPECTED.items():
        r = run_demo(name, {"QASIDA_COMPILER": "python"})
        check(name + " runs (python)", r.returncode == 0, r.stderr[-200:])
        check(name + " exact output (python)", r.stdout == expected,
              repr(r.stdout))
    for name, expected in EXPECTED.items():
        r = run_demo(name)
        check(name + " runs (hosted)", r.returncode == 0, r.stderr[-200:])
        check(name + " exact output (hosted)", r.stdout == expected,
              repr(r.stdout))
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
