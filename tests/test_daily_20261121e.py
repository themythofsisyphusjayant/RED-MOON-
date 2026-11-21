#!/usr/bin/env python3
"""Daily-ten 21 Nov 2026 — library sprint batch 5 (20 items: 11
verification flips + 9 new libraries).

Runs each demo under `forge.py run` with BOTH compilers (hosted
default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly. Expected values were hand-computed
BEFORE the first run (independent Python replica;
~/workspace/blackmoon-iso/daily-20261121-batch5/replica_20261121e.py),
including bench timing arithmetic, eval accuracy/MSE/perplexity,
embedding cosine + nearest neighbour, profiler section totals,
JWT HMAC-SHA256 tokens, the tar header checksum (mirroring
archive.fg), dataset windows/splits/batches, BPE training
(first-seen pair order, first max wins ties), int8 calibration
(round-half-up + clamp), SVG shape strings, plot scaling,
Prometheus text, SBOM JSON, CORS/CSP header text, CSRF LCG
tokens, iterated SHA-256 password hashing, parameterized-query
rendering, input validation rules, and 1-D convolution.

Usage:
  python3 tests/test_daily_20261121e.py
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
    "bench_demo": "250\n4000\n250\n4999950000\ntrue\ntrue\n",
    "evalharness_demo": "0.75\n1\n1\n2\n0.75\n",
    "embeddings_demo": "3\ncat\n1\nfish\n0\n1\n",
    "profiler_demo": "3000\n3000\n-1\nparse: 3000us x2\nemit: 3000us x1\n\n",
    "jwt_demo": ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjMiLCJuYW1lIjoiSmF5YW50In0.7I_PjT5lkV7bmsa02DMO0k8Wv6Sh5PmNXWMvv78wwUc\n"
                 "true\nfalse\nfalse\n"),
    "tarball_demo": "3345\n2048\ntrue\n5\ntrue\ntrue\n2048\n",
    "dataset_demo": "3\n20\n30\n40\n50\n2\n1\n2\n",
    "tokenizer_demo": ("char vocab = helo wrd\nchar ids len = 23\n"
                       "char roundtrip = hello world hello world\n"
                       "bpe merges = 5\nbpe ids len = 13\n"
                       "bpe roundtrip = hello world hello world\n"
                       "windows = 19\ntrain + test = 19\nbatch = 3\n"
                       "shuffled = 19\n"),
    "quant_demo": ("0.00784314 128\n128 192 255 64\n0.00392157\n"
                   "0.00196078 0\n"),
    "svg_demo": ("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"140\" height=\"100\">"
                 "<rect x=\"10\" y=\"10\" width=\"50\" height=\"30\" fill=\"red\"/>"
                 "<circle cx=\"100\" cy=\"40\" r=\"20\" fill=\"blue\"/>"
                 "<line x1=\"0\" y1=\"0\" x2=\"120\" y2=\"60\" stroke=\"green\"/>"
                 "<text x=\"10\" y=\"90\">hi</text></svg>\n"
                 "<polyline points=\"0,0 10,5 20,0\" fill=\"none\" stroke=\"black\"/>\n"),
    "plot_demo": ("9\n70\n"
                  "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"100\" height=\"90\">"
                  "<rect x=\"0\" y=\"60\" width=\"23\" height=\"30\" fill=\"steelblue\"/>"
                  "<rect x=\"25\" y=\"20\" width=\"23\" height=\"70\" fill=\"steelblue\"/>"
                  "<rect x=\"50\" y=\"70\" width=\"23\" height=\"20\" fill=\"steelblue\"/>"
                  "<rect x=\"75\" y=\"0\" width=\"23\" height=\"90\" fill=\"steelblue\"/></svg>\n"
                  "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"40\" height=\"90\">"
                  "<polyline points=\"0,80 10,40 20,60 30,10\" fill=\"none\" stroke=\"black\"/></svg>\n"
                  "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"40\" height=\"90\">"
                  "<circle cx=\"0\" cy=\"80\" r=\"3\" fill=\"red\"/>"
                  "<circle cx=\"10\" cy=\"40\" r=\"3\" fill=\"red\"/>"
                  "<circle cx=\"20\" cy=\"60\" r=\"3\" fill=\"red\"/>"
                  "<circle cx=\"30\" cy=\"10\" r=\"3\" fill=\"red\"/></svg>\n"),
    "promet_demo": ("5\n7\n-1\n# TYPE requests counter\nrequests 5\n"
                    "# TYPE queue gauge\nqueue 7\n\n"),
    "sbom_demo": ("2\n{\"bomFormat\":\"CycloneDX\",\"specVersion\":\"1.5\",\"components\":["
                  "{\"name\":\"qasida\",\"version\":\"2.3.0\",\"licenses\":[{\"license\":{\"id\":\"MIT\"}}]},"
                  "{\"name\":\"zlib\",\"version\":\"1.3.0\",\"licenses\":[{\"license\":{\"id\":\"Zlib\"}}]}]}\n"),
    "cors_demo": ("true\nfalse\nhttps://a.example\n\n"
                  "Access-Control-Allow-Methods: GET, POST\n"
                  "Access-Control-Allow-Origin: https://b.example\n"
                  "Access-Control-Allow-Methods: GET\n"),
    "csp_demo": ("default-src 'self'; script-src 'self' https://cdn.example.com; object-src 'none'\n"
                 "Content-Security-Policy: default-src 'self'; script-src 'self' https://cdn.example.com; object-src 'none'\n"),
    "csrf_demo": "gu5z222nvh5t\ntrue\nfalse\nfalse\n",
    "pwhash_demo": ("dfe06f1885f3657d729b5613d8bdefc0c5852427fd03e76aa33c7dd40b96f037\n"
                    "true\nfalse\n"),
    "paramq_demo": ("2\nSELECT * FROM users WHERE id = 7 AND name = 'O''Brien'\n"
                    "DELETE FROM t WHERE a = 'x'\n"),
    "valid2_demo": ("true\nfalse\nfalse\nfalse\ntrue\nfalse\ntrue\nfalse\n"
                    "true\nfalse\nhello world\n"),
    "conv1d_demo": ("valid 2\n-2\n-2\nstride2 1\n-2\nsame 4\n-2\n-2\n-2\n3\n"),
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
    print("daily-ten 21 Nov 2026 — library sprint batch 5 (20 items x 2 compilers)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
