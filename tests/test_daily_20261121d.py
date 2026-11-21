#!/usr/bin/env python3
"""Daily-ten 21 Nov 2026 — library sprint batch 4 (20 items: 12
verification flips + icalparse + 7 new libraries).

Runs each demo under `forge.py run` with BOTH compilers (hosted
default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly. Expected values were hand-computed
BEFORE the first run (independent Python replica;
~/workspace/blackmoon-iso/daily-20261121-batch4/replica_20261121d.py),
including the bloom double hash, FIFO LRU eviction, heapq, the
regexfull alternation/group matcher, the csv module, json.loads
plus the j2_num_str truncation rule, greedy word wrap, the
token-bucket simulation, iCalendar line parsing, the template
if/each/escape rules, the Markdown AST + HTML render, sentence
splitting with abbreviations, posixpath normalization, XML path
search, test-kit counting, and REST request/response construction.

Usage:
  python3 tests/test_daily_20261121d.py
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
    "bitset_demo": "37\ntrue\nfalse\n3\n33\n2\n",
    "bloom_demo": "true\ntrue\nfalse\nfalse\n",
    "lru_demo": "10\n-1\n20\n30\n99\n",
    "deque_demo": "0\n2\n3\n1\n1\n1\n",
    "heap_demo": "1\n3\n5\n2\n",
    "rss_demo": ("3\nFirst post\nSecond post\nThird post\n3\n"
                 "https://a.example/1\nhttps://a.example/2\n"
                 "https://a.example/3\n"),
    "regexfull_demo": "4\ndog\n0\n4\n",
    "csv2_demo": "4\na\nb,c\nd\"e\nf\na,\"b,c\",\"d\"\"e\",f\n",
    "json2_demo": ("5\nAda\n36\n3.14\ntrue\n2\nb\n2.5\n0\n"
                   "{\"name\":\"Ada\",\"age\":36,\"pi\":3.14,\"ok\":true,"
                   "\"tags\":[\"a\",\"b\"],\"nested\":{\"x\":2.5},\"none\":null}\n"
                   "4\nx\nfalse\n[1,2.5,\"x\",false]\n"),
    "textwrap_demo": ("lines = 3\n> The quick brown fox\n> jumps over the lazy\n"
                      "> dog\nfill =\nhello\nworld from\nqasida\n  a\n  b\n"),
    "tempfile_demo": "build_tmp_7\n/tmp/job_tmp_3\n",
    "ratelimit_demo": "1\n1\n1\n0\n1\n1\n",
    "icalparse_demo": ("true\nevt-1\nTeam sync\n20261121T103000Z\n"
                       "20261121T113000Z\nfalse\n\n"),
    "template2_demo": ("Hello Ada!\nVisible\n\n<li>a</li><li>b</li>\n"
                        "&lt;a &amp; &quot;b&quot;&gt;\nHi Bo\n\n"),
    "mdast_demo": ("1\n2\n1\n1\n<h1>Guide</h1>\n<p>Intro text here</p>\n"
                   "<li>alpha</li>\n<li>beta</li>\n<blockquote>quoted</blockquote>\n"
                   "<pre>code line</pre>\nGuide\n"),
    "sentenc_demo": ("4\nDr. Smith went to Washington.\n"
                     "He met Mr. Jones there!\n"
                     "Dr. Smith went to Washington.\n1\n0\n"),
    "pathnorm_demo": "/a/c\na/b\n../b\n/a/b\n.\na/c\ntrue\nfalse\n",
    "xmlpath_demo": "News\nFirst\n2\n<title>Second</title>\n3\nSecond\n",
    "testkit_demo": "6\n1\n7\n6 passed, 1 failed\nfailed: bad\n60\n3\n",
    "rest_demo": ("https://api.example.com/v1/langs?q=qasida\ntrue\nfalse\n"
                  "2.0.0\nqasida\n\nNot Found\nOK\n"
                  "POST /users HTTP/1.1\nHost: api.example\n"
                  "Content-Type: application/json\nContent-Length: 14\n\n"
                  "{\"name\":\"Ada\"}\n201\ntrue\nAda\n7\n"
                  "{\"id\": 7, \"name\": \"Ada\"}\n"
                  "GET /users?page=2 HTTP/1.1\nHost: api.example\n\n\n"
                  "404\nfalse\n"),
}


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def run_one(name, expected, env_extra):
    path = os.path.join(ROOT, "examples", name + ".fg")
    env = dict(os.environ)
    env.update(env_extra)
    try:
        r = subprocess.run(FORGE + ["run", path], capture_output=True,
                           text=True, cwd=ROOT, env=env, timeout=180)
    except subprocess.TimeoutExpired:
        check(f"{name} runs", False, "TIMEOUT after 180s")
        return
    check(f"{name} runs rc=0", r.returncode == 0, r.stderr[-300:])
    check(f"{name} exact stdout", r.stdout == expected,
          "" if r.stdout == expected else f"got: {r.stdout!r}")


def main():
    print("daily-ten 21 Nov 2026 — library sprint batch 4 (20 items x 2 compilers)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
