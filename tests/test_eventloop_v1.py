"""Top-500 #80: single-threaded event loops (tests/test_eventloop_v1.py).

A Node-style loop shape for servers without threads, as a pure
library in forge_lang/stdlib/eventloop.fg: fn-value callbacks,
one-shot + repeating timers, run-until-empty/stop, re-entrant
posting from callbacks via a pre-allocated shared outbox (push on a
captured array copy-on-writes — probe p4 — so callbacks MUST use
el_post_now/el_post_at/el_post_every, never the value API).
el_tick(l, now_us) drives the loop on a caller-supplied virtual
clock (exact, deterministic); el_run(l) is the live driver on
clock_micros(). Callback return code: 0 = continue, 1 = stop the
loop. Due order in el_tick (ties in posting order); a repeating
timer fires at most once per tick and re-arms at due + interval.

OK cases run under BOTH compilers via `forge.py run` with cwd=ROOT
(like test_loopelse_v1.py): the hosted binary resolves stdlib
imports relative to the repo root, so a temp cwd would break every
import. Backend cases assert NAMED build/check rejections (big32 and
WASM reject at build, not check — probe p8). fmt: the demo is
fmt-stable; the lib keeps its // header (fmt strips // comments),
so the lib check asserts all non-blank code lines are fmt-identical
(the one blank line after the header is the same delta fmt makes to
evloop.fg). Nothing is written to the tree.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FORGE = os.path.join(ROOT, "forge.py")
DEMO = os.path.join(ROOT, "examples", "eventloop_demo.fg")
LIB = os.path.join(ROOT, "forge_lang", "stdlib", "eventloop.fg")

DEMO_EXPECTED = "1\n6\n3\n4\n2\n5\n6\n0\n1\n"

# (name, program, expected stdout). All programs use a virtual
# clock (now = 1000 base) except the two live el_run cases, whose
# ORDER is timing-independent (immediate tasks are due 0).
OK_CASES = [
    ("immediate FIFO order",
     """import "eventloop.fg";
fn a() -> int {
    println(1);
    return 0;
}
fn b() -> int {
    println(2);
    return 0;
}
fn c() -> int {
    println(3);
    return 0;
}
fn main() -> int {
    let mut l: EventLoop = el_new();
    l = el_post(l, a);
    l = el_post(l, b);
    l = el_post(l, c);
    println(el_pending(l));
    l = el_tick(l, 1000);
    println(el_ran(l));
    println(el_pending(l));
    return 0;
}
""",
     "3\n1\n2\n3\n3\n0\n"),
    ("one-shot timer fires once",
     """import "eventloop.fg";
fn cb() -> int {
    println(7);
    return 0;
}
fn main() -> int {
    let mut l: EventLoop = el_new();
    l = el_after(l, 1000, 500, cb);
    l = el_tick(l, 1200);
    println(el_ran(l));
    println(el_pending(l));
    l = el_tick(l, 1500);
    println(el_ran(l));
    println(el_pending(l));
    l = el_tick(l, 2000);
    println(el_ran(l));
    println(el_pending(l));
    return 0;
}
""",
     "0\n1\n7\n1\n0\n1\n0\n"),
    ("repeating fires N times in order",
     """import "eventloop.fg";
fn main() -> int {
    let buf: [int] = [0];
    let tick = fn() -> int {
        buf[0] = buf[0] + 1;
        println(buf[0]);
        return 0;
    };
    let mut l: EventLoop = el_new();
    l = el_every(l, 1000, 100, tick);
    l = el_tick(l, 1100);
    l = el_tick(l, 1200);
    l = el_tick(l, 1300);
    println(el_ran(l));
    println(el_pending(l));
    return 0;
}
""",
     "1\n2\n3\n3\n1\n"),
    ("mixed immediate+timer due ordering",
     """import "eventloop.fg";
fn one() -> int {
    println(1);
    return 0;
}
fn two() -> int {
    println(2);
    return 0;
}
fn three() -> int {
    println(3);
    return 0;
}
fn main() -> int {
    let mut l: EventLoop = el_new();
    l = el_post(l, one);
    l = el_after(l, 1000, 100, two);
    l = el_after(l, 1000, 50, three);
    l = el_tick(l, 2000);
    println(el_ran(l));
    println(el_pending(l));
    return 0;
}
""",
     "1\n3\n2\n3\n0\n"),
    ("callback return 1 stops the loop",
     """import "eventloop.fg";
fn stop() -> int {
    println(1);
    return 1;
}
fn never() -> int {
    println(2);
    return 0;
}
fn main() -> int {
    let mut l: EventLoop = el_new();
    l = el_post(l, stop);
    l = el_post(l, never);
    l = el_tick(l, 1000);
    println(el_ran(l));
    println(el_pending(l));
    if el_stopped(l) {
        println(1);
    } else {
        println(0);
    }
    return 0;
}
""",
     "1\n1\n1\n1\n"),
    ("posting from inside a callback runs in the same el_run",
     """import "eventloop.fg";
fn six() -> int {
    println(6);
    return 0;
}
fn main() -> int {
    let mut l: EventLoop = el_new();
    let imm = fn() -> int {
        println(1);
        el_post_now(l, six);
        return 0;
    };
    l = el_post(l, imm);
    l = el_run(l);
    println(el_ran(l));
    println(el_pending(l));
    return 0;
}
""",
     "1\n6\n2\n0\n"),
    ("stop via el_tick virtual clock",
     """import "eventloop.fg";
fn main() -> int {
    let buf: [int] = [0];
    let tick = fn() -> int {
        buf[0] = buf[0] + 1;
        println(buf[0]);
        if buf[0] >= 2 {
            return 1;
        }
        return 0;
    };
    let mut l: EventLoop = el_new();
    l = el_every(l, 1000, 100, tick);
    l = el_tick(l, 1100);
    l = el_tick(l, 1200);
    println(el_ran(l));
    println(el_pending(l));
    if el_stopped(l) {
        println(1);
    } else {
        println(0);
    }
    l = el_tick(l, 1300);
    println(el_ran(l));
    return 0;
}
""",
     "1\n2\n2\n0\n1\n2\n"),
    ("empty loop runs 0",
     """import "eventloop.fg";
fn main() -> int {
    let mut l: EventLoop = el_new();
    l = el_run(l);
    println(el_ran(l));
    println(el_pending(l));
    if el_stopped(l) {
        println(1);
    } else {
        println(0);
    }
    l = el_tick(l, 5000);
    println(el_ran(l));
    println(el_pending(l));
    return 0;
}
""",
     "0\n0\n0\n0\n0\n"),
    ("pending/ran counters",
     """import "eventloop.fg";
fn one() -> int {
    println(1);
    return 0;
}
fn two() -> int {
    println(2);
    return 0;
}
fn main() -> int {
    let mut l: EventLoop = el_new();
    l = el_post(l, one);
    l = el_after(l, 1000, 500, two);
    l = el_tick(l, 1000);
    println(el_ran(l));
    println(el_pending(l));
    l = el_tick(l, 1500);
    println(el_ran(l));
    println(el_pending(l));
    return 0;
}
""",
     "1\n1\n1\n2\n2\n0\n"),
    ("outbox full returns -1",
     """import "eventloop.fg";
fn six() -> int {
    println(6);
    return 0;
}
fn main() -> int {
    let buf: [int] = [0, 0];
    let mut l: EventLoop = el_new_cap(1);
    let imm = fn() -> int {
        println(1);
        let r0: int = el_post_now(l, six);
        let r1: int = el_post_now(l, six);
        buf[0] = r0;
        buf[1] = r1;
        return 0;
    };
    l = el_post(l, imm);
    l = el_tick(l, 1000);
    println(buf[0]);
    println(buf[1]);
    println(el_ran(l));
    return 0;
}
""",
     "1\n6\n0\n-1\n2\n"),
    ("el_post_every from a callback",
     """import "eventloop.fg";
fn main() -> int {
    let buf: [int] = [0];
    let tick = fn() -> int {
        buf[0] = buf[0] + 1;
        println(buf[0]);
        return 0;
    };
    let mut l: EventLoop = el_new();
    let imm = fn() -> int {
        println(1);
        el_post_every(l, 1100, 100, tick);
        return 0;
    };
    l = el_post(l, imm);
    l = el_tick(l, 1000);
    l = el_tick(l, 1100);
    l = el_tick(l, 1200);
    println(el_ran(l));
    println(el_pending(l));
    return 0;
}
""",
     "1\n1\n2\n3\n1\n"),
    ("tie order is posting order",
     """import "eventloop.fg";
fn two() -> int {
    println(2);
    return 0;
}
fn three() -> int {
    println(3);
    return 0;
}
fn main() -> int {
    let mut l: EventLoop = el_new();
    l = el_after(l, 1000, 500, two);
    l = el_after(l, 1000, 500, three);
    l = el_tick(l, 1500);
    println(el_ran(l));
    println(el_pending(l));
    return 0;
}
""",
     "2\n3\n2\n0\n"),
    ("el_after due boundary",
     """import "eventloop.fg";
fn cb() -> int {
    println(7);
    return 0;
}
fn main() -> int {
    let mut l: EventLoop = el_new();
    l = el_after(l, 1000, 500, cb);
    l = el_tick(l, 1499);
    println(el_ran(l));
    l = el_tick(l, 1500);
    println(el_ran(l));
    return 0;
}
""",
     "0\n7\n1\n"),
    ("interval 0 clamped to 1",
     """import "eventloop.fg";
fn main() -> int {
    let buf: [int] = [0];
    let tick = fn() -> int {
        buf[0] = buf[0] + 1;
        println(buf[0]);
        return 0;
    };
    let mut l: EventLoop = el_new();
    l = el_every(l, 1000, 0, tick);
    l = el_tick(l, 1001);
    l = el_tick(l, 1001);
    println(el_ran(l));
    println(el_pending(l));
    return 0;
}
""",
     "1\n1\n1\n"),
    ("el_post from a callback loses the post (sharp edge)",
     """import "eventloop.fg";
fn six() -> int {
    println(6);
    return 0;
}
fn main() -> int {
    let mut l: EventLoop = el_new();
    let imm = fn() -> int {
        println(1);
        let dropped: EventLoop = el_post(l, six);
        println(el_pending(dropped));
        return 0;
    };
    l = el_post(l, imm);
    l = el_tick(l, 1000);
    println(el_ran(l));
    println(el_pending(l));
    return 0;
}
""",
     "1\n1\n1\n0\n"),
    ("no catch-up in one tick",
     """import "eventloop.fg";
fn main() -> int {
    let buf: [int] = [0];
    let tick = fn() -> int {
        buf[0] = buf[0] + 1;
        println(buf[0]);
        return 0;
    };
    let mut l: EventLoop = el_new();
    l = el_every(l, 1000, 100, tick);
    l = el_tick(l, 10000);
    println(el_ran(l));
    println(el_pending(l));
    l = el_tick(l, 10000);
    println(el_ran(l));
    return 0;
}
""",
     "1\n1\n1\n2\n2\n"),
]

# (name, program, mode, needle) — build/check must FAIL (rc != 0)
# with stderr containing needle. big32/WASM assert on `build`
# (check passes; the rejection is at codegen — probe p8).
# The wasm needle names the first struct-returning lib function;
# a bare-closure program instead hits `wasm: expression Lambda is
# not supported in v1` (probe p8).
BACKEND_PROG = """import "eventloop.fg";
fn main() -> int {
    let buf: [int] = [0];
    let c = fn() -> int {
        buf[0] = buf[0] + 1;
        return 0;
    };
    let mut l: EventLoop = el_new();
    l = el_post(l, c);
    l = el_tick(l, 1000);
    println(buf[0]);
    return 0;
}
"""

BACKEND_CASES = [
    ("big32", "build", ["--target", "big32"],
     "big32 structs support int/bool/str fields only, not fn() -> int in struct EvTask (v1)"),
    ("wasm", "build", ["--target", "wasm"],
     "wasm: function 'el_new_cap' returns EventLoop, not supported in v2"),
    ("freestanding", "check", ["--freestanding"],
     "array literal allocates on the heap (not in freestanding v1"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          timeout=300)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    total = [0]

    def tally(name, ok, detail=""):
        total[0] += 1
        if not check(name, ok, detail):
            failures.append(name)

    with tempfile.TemporaryDirectory() as td:
        # --- Demo, both compilers ---
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            r = run([sys.executable, FORGE] + prefix + ["run", DEMO], ROOT)
            tally(f"demo/{mode}",
                  r.returncode == 0 and r.stdout == DEMO_EXPECTED,
                  f"(rc={r.returncode} out={r.stdout!r})")

        # --- OK cases, both compilers ---
        for name, program, expected in OK_CASES:
            prog = os.path.join(td, "ok.fg")
            with open(prog, "w") as f:
                f.write(program)
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                r = run([sys.executable, FORGE] + prefix + ["run", prog],
                        ROOT)
                tally(f"ok/{name}/{mode}",
                      r.returncode == 0 and r.stdout == expected,
                      f"(rc={r.returncode} out={r.stdout!r} "
                      f"exp={expected!r} err={r.stderr[-200:]!r})")

        # --- Backend cases, both compilers ---
        prog = os.path.join(td, "backend.fg")
        with open(prog, "w") as f:
            f.write(BACKEND_PROG)
        for name, sub, extra, needle in BACKEND_CASES:
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                cmd = [sys.executable, FORGE] + prefix + [sub] + extra
                if sub == "build":
                    cmd += ["-o", os.path.join(td, "backend_" + name)]
                cmd.append(prog)
                r = run(cmd, ROOT)
                tally(f"backend/{name}/{mode}",
                      r.returncode != 0 and needle in r.stderr,
                      f"(rc={r.returncode} err={r.stderr[-300:]!r})")

        # --- fmt: demo stable, lib code lines fmt-neutral ---
        r = run([sys.executable, FORGE, "fmt", DEMO], ROOT)
        tally("fmt/demo runs", r.returncode == 0,
              f"(rc={r.returncode} err={r.stderr[-200:]!r})")
        r = run([sys.executable, FORGE, "fmt", "--check", DEMO], ROOT)
        tally("fmt/demo idempotent", r.returncode == 0,
              f"(rc={r.returncode} out={r.stdout!r} err={r.stderr[-200:]!r})")
        libcopy = os.path.join(td, "eventloop_fmt.fg")
        with open(LIB) as f:
            orig = f.read()
        with open(libcopy, "w") as f:
            f.write(orig)
        r = run([sys.executable, FORGE, "fmt", libcopy], ROOT)
        ok_fmt = False
        if r.returncode == 0:
            with open(libcopy) as f:
                formatted = f.read()
            strip = lambda s: [ln for ln in s.splitlines()
                               if ln.strip() and
                               not ln.lstrip().startswith("//")]
            ok_fmt = strip(orig) == strip(formatted)
        tally("fmt/lib code lines fmt-neutral", ok_fmt,
              "(fmt changed a non-blank, non-comment line)")

    print(f"eventloop: {total[0] - len(failures)}/{total[0]} PASS")
    if failures:
        print("FAILURES: %s" % ", ".join(failures))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
