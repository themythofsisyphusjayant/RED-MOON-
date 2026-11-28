"""Top-500 #118: email message parsing v1 (tests/test_emailparse_v1.py).
Parse only, no sending, pure Qasida in forge_lang/stdlib/emailparse.fg:
headers split from the body at the first blank line, header names
match case-insensitively, folded headers unfold (a continuation
line joins the previous value with a single space), and the body is
everything after the blank line, preserved verbatim. A missing
header yields "". No tuples are used, so no big32/WASM gate
applies.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

IMP = 'import "emailparse.fg";\n'

DEMO_EXPECTED = ("from: Ada Lovelace <ada@example.com>\n"
                 "to: charles@example.com\n"
                 "subject: Planning the second meeting\n"
                 "date: Fri, 28 Nov 2026 09:00:00 +0530\n"
                 "body:\n"
                 "Hello Charles,\n"
                 "See you soon.\n")

# (name, program, expected stdout) — must run clean.
OK_CASES = [
    ("lowercase header names match",
     IMP + "fn main() {\n"
     "  let lines: [str] = [\"from: ada@example.com\", \"to: bob@example.com\", \"subject: hi\", \"date: Mon, 01 Jan 2024 00:00:00 +0000\", \"\", \"body text\"];\n"
     "  let raw: str = join(lines, \"\\n\");\n"
     "  let e: Email = email_parse(raw);\n"
     "  println(e.from);\n  println(e.to);\n  println(e.subject);\n"
     "  println(e.date);\n  println(e.body);\n}\n",
     "ada@example.com\nbob@example.com\nhi\n"
     "Mon, 01 Jan 2024 00:00:00 +0000\nbody text\n"),
    ("folded To header unfolds with a single space",
     IMP + "fn main() {\n"
     "  let lines: [str] = [\"From: a@x.com\", \"To: one@example.com,\", \" two@example.com\", \"\", \"b\"];\n"
     "  let raw: str = join(lines, \"\\n\");\n"
     "  let e: Email = email_parse(raw);\n"
     "  println(e.to);\n}\n",
     "one@example.com, two@example.com\n"),
    ("missing Subject yields an empty string",
     IMP + "fn main() {\n"
     "  let lines: [str] = [\"From: a@x.com\", \"To: b@x.com\", \"\", \"hello\"];\n"
     "  let raw: str = join(lines, \"\\n\");\n"
     "  let e: Email = email_parse(raw);\n"
     "  println(e.from);\n  println(\"[\" + e.subject + \"]\");\n}\n",
     "a@x.com\n[]\n"),
    ("a colon inside a header value is kept whole",
     IMP + "fn main() {\n"
     "  let lines: [str] = [\"Subject: Re: hello: world\", \"\", \"x\"];\n"
     "  let raw: str = join(lines, \"\\n\");\n"
     "  let e: Email = email_parse(raw);\n"
     "  println(e.subject);\n}\n",
     "Re: hello: world\n"),
    ("a body containing a blank line is preserved verbatim",
     IMP + "fn main() {\n"
     "  let lines: [str] = [\"From: a@x.com\", \"\", \"line1\", \"\", \"line3\"];\n"
     "  let raw: str = join(lines, \"\\n\");\n"
     "  let e: Email = email_parse(raw);\n"
     "  println(e.body);\n}\n",
     "line1\n\nline3\n"),
    ("email_has_header true and false",
     IMP + "fn main() {\n"
     "  let lines: [str] = [\"From: a@x.com\", \"X-Custom: test\", \"\", \"b\"];\n"
     "  let raw: str = join(lines, \"\\n\");\n"
     "  println(email_has_header(raw, \"From\"));\n"
     "  println(email_has_header(raw, \"x-custom\"));\n"
     "  println(email_has_header(raw, \"Subject\"));\n}\n",
     "true\ntrue\nfalse\n"),
    ("email_header for a missing header returns empty string",
     IMP + "fn main() {\n"
     "  let lines: [str] = [\"From: a@x.com\", \"\", \"b\"];\n"
     "  let raw: str = join(lines, \"\\n\");\n"
     "  println(\"[\" + email_header(raw, \"Subject\") + \"]\");\n"
     "  println(email_header(raw, \"FROM\"));\n}\n",
     "[]\na@x.com\n"),
    ("a header-like line in the body is not a header",
     IMP + "fn main() {\n"
     "  let lines: [str] = [\"From: real@x.com\", \"\", \"Subject: fake subject\", \"more body\"];\n"
     "  let raw: str = join(lines, \"\\n\");\n"
     "  println(\"[\" + email_header(raw, \"Subject\") + \"]\");\n"
     "  println(email_body(raw));\n}\n",
     "[]\nSubject: fake subject\nmore body\n"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "emailparse_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("emailparse demo", r.returncode == 0 and r.stdout == DEMO_EXPECTED,
                 f"(rc={r.returncode} out={r.stdout!r} err={r.stderr[:200]!r})"):
        failures.append("emailparse demo")
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
    for rel in ("forge_lang/stdlib/emailparse.fg",
                "examples/emailparse_demo.fg"):
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
    # ASan: the demo runs clean.
    with tempfile.TemporaryDirectory() as td:
        c_path = os.path.join(td, "emailparse.c")
        bin_path = os.path.join(td, "emailparse_asan")
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
