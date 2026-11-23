"""Top-500 #51: deferred error logging (tests/test_errlog_v1.py).

Go-style log-on-return, pure Qasida over result.fg / errcode.fg /
multierr.fg: an ErrLog wraps a MultiErr and records one
"ERR: <msg>" line per failed Result; the caller drains it later
(stdout via errlog_drain, stderr via errlog_drain_stderr, which
uses the eprintln builtin). The helpers return only the updated
log — the Result itself is never touched. log_on_err_int /
log_on_err_str cover Result<int/str, str>, log_on_err_msg_int /
log_on_err_msg_str add a context prefix, and log_on_err_code_int /
log_on_err_code_str format Result<int/str, ErrCode> with err_name.
The helpers are concrete, not generic: a generic log_on_err<T>
leaks under the hosted compiler (its generic-call assignment emits
an extra unbalanced forge_arr_inc on the returned struct's array
field), so the generic form is withheld until that hosted codegen
bug is fixed.

v1 limits (named in the catalog): the log lives in memory only
(no file sink, no timestamps, no levels — log.fg covers
immediate leveled output); draining to stderr needs the hosted
runtime (eprintln is rejected on freestanding, big32 and WASM);
log_on_err_code logs an Unknown code as "ERR: Unknown", not its
errno. Both compilers (Python + hosted).

No FATAL / REJECT / BACKEND / FREESTANDING sections: the module
adds no new builtins, so there is nothing to reject, and the
backend/freestanding rejections a program importing it meets are
the pre-existing errcode.fg / multierr.fg ones (ErrCode fields in
structs, heap-backed types), not this item's — those are covered
by tests/test_errcode_v1.py. The demo and the cases write no
files, so there is nothing to clean up. Runs use cwd=ROOT (like
test_panic_recover_v1.py): the hosted binary resolves stdlib
imports relative to the repo root (forge_lang/stdlib/), so a temp
cwd would break every import.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO_EXPECTED = """count after ok 0
count after err 1
first ERR: boom
ERR: boom
count after drain 0
count after code err 1
ERR: NotFound
done
"""

# (name, program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("new log is empty",
     r"""import "errlog.fg";
fn main() -> int {
  let log: ErrLog = errlog_new();
  println(errlog_count(log));
  println(errlog_has(log));
  println("first=[" + errlog_first(log) + "]");
  println("last=[" + errlog_last(log) + "]");
  println("render=[" + errlog_render(log) + "]");
  return 0;
}
""",
     """0
false
first=[]
last=[]
render=[]
""",
     ""),
    ("errlog_add prefixes ERR: and grows the log",
     r"""import "errlog.fg";
fn main() -> int {
  let mut log: ErrLog = errlog_new();
  log = errlog_add(log, "disk full");
  log = errlog_add(log, "timeout");
  println(errlog_count(log));
  println(errlog_first(log));
  println(errlog_last(log));
  println(len(errlog_lines(log)));
  println(errlog_lines(log)[1]);
  return 0;
}
""",
     """2
ERR: disk full
ERR: timeout
2
ERR: timeout
""",
     ""),
    ("log_on_err ignores Ok, logs Err, leaves the Result intact",
     r"""import "errlog.fg";
fn main() -> int {
  let mut log: ErrLog = errlog_new();
  let good: Result<int, str> = Result { ok: true, value: 7, error: "" };
  log = log_on_err_int(log, good);
  println("after ok", errlog_count(log));
  let bad: Result<int, str> = Result { ok: false, value: 0, error: "boom" };
  log = log_on_err_int(log, bad);
  println("after err", errlog_count(log));
  println("value", good.value);
  println("error", bad.error);
  println("first", errlog_first(log));
  return 0;
}
""",
     """after ok 0
after err 1
value 7
error boom
first ERR: boom
""",
     ""),
    ("log_on_err_msg adds a context prefix",
     r"""import "errlog.fg";
fn main() -> int {
  let mut log: ErrLog = errlog_new();
  let good: Result<int, str> = Result { ok: true, value: 1, error: "" };
  log = log_on_err_msg_int(log, good, "open config");
  println("after ok", errlog_count(log));
  let bad: Result<int, str> = Result { ok: false, value: 0, error: "boom" };
  log = log_on_err_msg_int(log, bad, "open config");
  println("after err", errlog_count(log));
  println(errlog_first(log));
  return 0;
}
""",
     """after ok 0
after err 1
ERR: open config: boom
""",
     ""),
    ("log_on_err_code logs ErrCode names",
     r"""import "errlog.fg";
fn main() -> int {
  let mut log: ErrLog = errlog_new();
  let ok_r: Result<str, ErrCode> = Result { ok: true, value: "hi", error: Success };
  log = log_on_err_code_str(log, ok_r);
  println("after ok", errlog_count(log));
  let missing = read_file_err("no_such_file_xyz.txt");
  log = log_on_err_code_str(log, missing);
  println("after err", errlog_count(log));
  println(errlog_first(log));
  return 0;
}
""",
     """after ok 0
after err 1
ERR: NotFound
""",
     ""),
    ("log_on_err_code logs Unknown as Unknown, not its errno",
     r"""import "errlog.fg";
fn main() -> int {
  let mut log: ErrLog = errlog_new();
  let r: Result<str, ErrCode> = Result { ok: false, value: "", error: Unknown };
  log = log_on_err_code_str(log, r);
  println(errlog_first(log));
  return 0;
}
""",
     """ERR: Unknown
""",
     ""),
    ("log_on_err_str covers Result<str, str>",
     r"""import "errlog.fg";
fn main() -> int {
  let mut log: ErrLog = errlog_new();
  let good: Result<str, str> = Result { ok: true, value: "ok", error: "" };
  log = log_on_err_str(log, good);
  println("after ok", errlog_count(log));
  let bad: Result<str, str> = Result { ok: false, value: "", error: "boom" };
  log = log_on_err_str(log, bad);
  println("after err", errlog_count(log));
  println(errlog_first(log));
  return 0;
}
""",
     """after ok 0
after err 1
ERR: boom
""",
     ""),
    ("log_on_err_code_int covers Result<int, ErrCode>",
     r"""import "errlog.fg";
fn main() -> int {
  let mut log: ErrLog = errlog_new();
  let ok_r: Result<int, ErrCode> = Result { ok: true, value: 7, error: Success };
  log = log_on_err_code_int(log, ok_r);
  println("after ok", errlog_count(log));
  let bad: Result<int, ErrCode> = Result { ok: false, value: 0, error: NotFound };
  log = log_on_err_code_int(log, bad);
  println("after err", errlog_count(log));
  println(errlog_first(log));
  return 0;
}
""",
     """after ok 0
after err 1
ERR: NotFound
""",
     ""),
    ("log_on_err_msg_str covers Result<str, str> with a prefix",
     r"""import "errlog.fg";
fn main() -> int {
  let mut log: ErrLog = errlog_new();
  let bad: Result<str, str> = Result { ok: false, value: "", error: "boom" };
  log = log_on_err_msg_str(log, bad, "open config");
  println(errlog_count(log));
  println(errlog_first(log));
  return 0;
}
""",
     """1
ERR: open config: boom
""",
     ""),
    ("errlog_render joins lines with newlines",
     r"""import "errlog.fg";
fn main() -> int {
  let mut log: ErrLog = errlog_new();
  log = errlog_add(log, "a");
  log = errlog_add(log, "b");
  println(errlog_render(log));
  return 0;
}
""",
     """ERR: a
ERR: b
""",
     ""),
    ("errlog_clear empties the log",
     r"""import "errlog.fg";
fn main() -> int {
  let mut log: ErrLog = errlog_new();
  log = errlog_add(log, "a");
  log = errlog_clear(log);
  println(errlog_count(log));
  println(errlog_has(log));
  return 0;
}
""",
     """0
false
""",
     ""),
    ("errlog_drain prints to stdout and clears",
     r"""import "errlog.fg";
fn main() -> int {
  let mut log: ErrLog = errlog_new();
  log = errlog_add(log, "first");
  log = errlog_add(log, "second");
  log = errlog_drain(log);
  println("after", errlog_count(log));
  log = errlog_drain(log);
  println("done");
  return 0;
}
""",
     """ERR: first
ERR: second
after 0
done
""",
     ""),
    ("errlog_drain_stderr prints to stderr and clears",
     r"""import "errlog.fg";
fn main() -> int {
  let mut log: ErrLog = errlog_new();
  log = errlog_add(log, "boom");
  log = errlog_add(log, "second");
  println("before");
  let cleared: ErrLog = errlog_drain_stderr(log);
  println("after", errlog_count(cleared));
  return 0;
}
""",
     """before
after 0
""",
     "ERR: boom"),
    ("errlog_lines returns the stored lines",
     r"""import "errlog.fg";
fn main() -> int {
  let mut log: ErrLog = errlog_new();
  log = errlog_add(log, "x");
  log = errlog_add(log, "y");
  let lines: [str] = errlog_lines(log);
  println(len(lines));
  println(lines[0]);
  println(lines[1]);
  return 0;
}
""",
     """2
ERR: x
ERR: y
""",
     ""),
    ("drain on an empty log prints nothing",
     r"""import "errlog.fg";
fn main() -> int {
  let log: ErrLog = errlog_new();
  let cleared: ErrLog = errlog_drain(log);
  println("count", errlog_count(cleared));
  println("done");
  return 0;
}
""",
     """count 0
done
""",
     ""),
]

# .fg files whose formatting must be idempotent.
# fmt strips // comments, so the lib (which keeps its header) is not
# fmt-run here — demo only, same as test_errcode_v1.py.
FMT_FILES = ("examples/errlog_demo.fg",)


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "errlog_demo.fg")
    with tempfile.TemporaryDirectory() as td:
        _run_all(td, failures, demo)
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


def _run_all(td, failures, demo):
    for mode, prefix in (("hosted", []), ("python", ["--python"])):
        r = run([sys.executable, os.path.join(ROOT, "forge.py")] + prefix +
                ["run", demo], ROOT)
        if not check(f"demo runs ({mode})", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append(f"demo runs ({mode})")
        elif not check(f"demo results ({mode})", r.stdout == DEMO_EXPECTED,
                       repr(r.stdout)):
            failures.append(f"demo results ({mode})")
    for name, prog, want, needle in OK_CASES:
        p = os.path.join(td, "c.fg")
        with open(p, "w") as f:
            f.write(prog)
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                     prefix + ["run", p], ROOT)
            ok = (rr.returncode == 0 and rr.stdout == want and
                  (not needle or needle in rr.stderr))
            if not check(f"{name} ({mode})", ok,
                         repr(rr.stdout) + (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(f"{name} ({mode})")
    for rel in FMT_FILES:
        target = os.path.join(ROOT, rel)
        rf = run([sys.executable, os.path.join(ROOT, "forge.py"), "fmt", target],
                 ROOT)
        if not check(f"fmt runs ({rel})", rf.returncode == 0, rf.stderr.strip()):
            failures.append(f"fmt runs ({rel})")
        else:
            rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"),
                       "fmt", "--check", target], ROOT)
            if not check(f"fmt idempotent ({rel})", rf2.returncode == 0,
                         rf2.stderr.strip()):
                failures.append(f"fmt idempotent ({rel})")


if __name__ == "__main__":
    sys.exit(main())
