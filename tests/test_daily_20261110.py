#!/usr/bin/env python3
"""Daily-ten 10 Nov 2026 — library track test (forge run).

Ten new pure-Qasida libraries under forge_lang/stdlib/ plus their
demos under examples/*_demo.fg. Each demo is run with `forge.py
run` and its stdout must match the expected transcript exactly:
- unicode (ASCII classify/case), http_client (query/URL/status/
  headers), rest (URL/ok/field/error), fsutils (copy/append/size),
  osinfo (platform/args flags), archive (tar header + checksum),
  hmac (HMAC-SHA256, RFC 4231 cases 1-2), jwt (HS256 sign/verify),
  taskqueue (file-backed FIFO), modelexport (MYTHOSCKPT v1
  save/parse round-trip).
Crypto/archive expectations were computed with Python's hmac,
hashlib, base64 and tarfile over the identical inputs/layouts.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
FAILURES = []

EXPECTED = {
    "unicode_demo": "5\n3\n1\n1\n1\n4\nhello\nABC\n7\n-1\n",
    "http_client_demo": "q=qasida&page=2\nhttps://example.com/search?q=qasida&page=2\n404\nNot Found\ntrue\nfalse\ntext/html\n42\n49\ntrue\n",
    "rest_demo": "https://api.example.com/v1/langs?q=qasida\ntrue\nfalse\n2.0.0\nqasida\n\nNot Found\nOK\n",
    "fsutils_demo": "true\ntrue\n5\ntrue\nhello world\n-1\nfalse\ntrue\n",
    "osinfo_demo": "linux\n/\n0\nfalse\nnone\ntrue\n0.05\n",
    "archive_demo": "3780\n007304\n104\n48\n53\n48\n117\n",
    "hmac_demo": "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7\n5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843\n32\n",
    "jwt_demo": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjMiLCJuYW1lIjoiSmF5YW50In0.7I_PjT5lkV7bmsa02DMO0k8Wv6Sh5PmNXWMvv78wwUc\ntrue\nfalse\nfalse\n",
    "taskqueue_demo": "true\ntrue\ntrue\ntrue\n3\nbuild\nbuild\n2\ntest\ntest\n1\n",
    "modelexport_demo": "MYTHOSCKPT 1\nname=mlp\nlayers=2\nw=125,-250,375,1000\n1\nmlp\n2\n125\n-250\n375\n1000\n",
}


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def main():
    print("daily-ten 10 Nov 2026 library demos (forge run)")
    for name, expected in EXPECTED.items():
        path = os.path.join("examples", name + ".fg")
        r = subprocess.run(FORGE + ["run", path],
                           capture_output=True, text=True, cwd=ROOT)
        check(name + " runs", r.returncode == 0, r.stderr[-200:])
        check(name + " exact output", r.stdout == expected,
              repr(r.stdout))
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
