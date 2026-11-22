"""Top-500 filesystem slice: mkdir/readdir/rename/symlink/readlink/
chmod/chown/stat/is_dir/str_compare builtins + the five library
proofs #181 (dirs.fg), #187 (atomicfile.fg), #188 (links.fg),
#189 (fileperms.fg), #190 (walk.fg). Both compilers (Python + hosted).

The demos write under /tmp/fs_demo_* and the inline cases under
/tmp/fs_test_*; both are removed before and after the run so
nothing is left behind. Runs use cwd=ROOT (like
test_errcode_v1.py): the hosted binary resolves stdlib imports
relative to the repo root (forge_lang/stdlib/), so a temp cwd
would break every import.
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO_EXPECTED = {
    "dirs": """true
false
17
AlreadyExists
true
true
true
a.txt, b.txt, c.txt
true
true
true
true
""",
    "atomicfile": """true
true
v1
true
v2
false
false
""",
    "links": """true
true
true
true
/tmp/fs_demo_links/real.txt
hello link
false
2
NotFound
""",
    "fileperms": """true
true
Success
33152
Success
33188
Success
true
true
NotFound
true
false
-1
""",
    "walk": """true
true
true
true
true
true
/tmp/fs_demo_walk/root.txt, /tmp/fs_demo_walk/sub, /tmp/fs_demo_walk/sub/deep, /tmp/fs_demo_walk/sub/deep/leaf.txt, /tmp/fs_demo_walk/sub/mid.txt
/tmp/fs_demo_walk/root.txt, /tmp/fs_demo_walk/sub/deep/leaf.txt, /tmp/fs_demo_walk/sub/mid.txt
0
""",
}

DEMOS = ("dirs", "atomicfile", "links", "fileperms", "walk")

# (name, program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("mkdir fresh, again, and EEXIST",
     r"""fn main() -> int {
  let base = "/tmp/fs_test_mkdir";
  println(mkdir(base));
  println(mkdir(base));
  println(last_errno());
  return 0;
}
""",
     """true
false
17
""",
     ""),
    ("readdir names, len, try_readdir ok and missing",
     r"""import "result.fg";
fn main() -> int {
  let base = "/tmp/fs_test_readdir";
  println(mkdir(base));
  let w1 = write_file(base + "/b.txt", "b");
  let w2 = write_file(base + "/a.txt", "a");
  println(w1);
  println(w2);
  let names = readdir(base);
  println(len(names));
  let t = try_readdir(base);
  println(t.ok);
  println(len(t.value));
  let t2 = try_readdir(base + "/nope");
  println(t2.ok);
  println(t2.error);
  return 0;
}
""",
     """true
true
true
2
true
2
false
2
""",
     ""),
    ("rename basic, missing, and errno",
     r"""fn main() -> int {
  let base = "/tmp/fs_test_rename";
  println(mkdir(base));
  let w = write_file(base + "/old.txt", "x");
  println(w);
  println(rename(base + "/old.txt", base + "/new.txt"));
  println(file_exists(base + "/old.txt"));
  println(file_exists(base + "/new.txt"));
  println(rename(base + "/gone.txt", base + "/x.txt"));
  println(last_errno());
  return 0;
}
""",
     """true
true
true
false
true
false
2
""",
     ""),
    ("symlink, readlink, try_readlink, read through link",
     r"""import "result.fg";
fn main() -> int {
  let base = "/tmp/fs_test_links";
  println(mkdir(base));
  let w = write_file(base + "/real.txt", "content");
  println(w);
  println(symlink(base + "/real.txt", base + "/link.txt"));
  println(readlink(base + "/link.txt"));
  println(read_file(base + "/link.txt"));
  let r = try_readlink(base + "/link.txt");
  println(r.ok);
  println(r.value);
  let r2 = try_readlink(base + "/gone.txt");
  println(r2.ok);
  println(r2.error);
  return 0;
}
""",
     """true
true
true
/tmp/fs_test_links/real.txt
content
true
/tmp/fs_test_links/real.txt
false
2
""",
     ""),
    ("chmod and stat_mode exact values, missing is -1",
     r"""fn main() -> int {
  let base = "/tmp/fs_test_chmod";
  println(mkdir(base));
  let w = write_file(base + "/f.txt", "d");
  println(w);
  println(chmod(base + "/f.txt", 384));
  println(stat_mode(base + "/f.txt"));
  println(chmod(base + "/f.txt", 420));
  println(stat_mode(base + "/f.txt"));
  println(stat_mode(base + "/gone.txt"));
  println(last_errno());
  return 0;
}
""",
     """true
true
true
33152
true
33188
-1
2
""",
     ""),
    ("chown to own uid/gid, missing fails with errno",
     r"""fn main() -> int {
  let base = "/tmp/fs_test_chown";
  println(mkdir(base));
  let w = write_file(base + "/f.txt", "d");
  println(w);
  let uid = stat_uid(base + "/f.txt");
  let gid = stat_gid(base + "/f.txt");
  println(chown(base + "/f.txt", uid, gid));
  println(stat_uid(base + "/f.txt") == uid);
  println(stat_gid(base + "/f.txt") == gid);
  println(chown(base + "/gone.txt", 0, 0));
  println(last_errno());
  return 0;
}
""",
     """true
true
true
true
true
false
2
""",
     ""),
    ("is_dir on dir, file, and missing path",
     r"""fn main() -> int {
  let base = "/tmp/fs_test_isdir";
  println(mkdir(base));
  let w = write_file(base + "/f.txt", "d");
  println(w);
  println(is_dir(base));
  println(is_dir(base + "/f.txt"));
  println(is_dir(base + "/gone"));
  return 0;
}
""",
     """true
true
true
false
false
""",
     ""),
    ("str_compare signs only (magnitudes are libc-defined)",
     r"""fn main() -> int {
  println(str_compare("a", "b") < 0);
  println(str_compare("b", "a") > 0);
  println(str_compare("a", "a") == 0);
  println(str_compare("", "a") < 0);
  println(str_compare("a", "") > 0);
  println(str_compare("abc", "abd") < 0);
  println(str_compare("abc", "abc") == 0);
  return 0;
}
""",
     """true
true
true
true
true
true
true
""",
     ""),
    ("dirs.fg: create, sorted list, create_all nested",
     r"""import "dirs.fg";
fn main() -> int {
  let base = "/tmp/fs_test_dirs";
  println(dir_create(base));
  let w1 = write_file(base + "/b.txt", "b");
  let w2 = write_file(base + "/a.txt", "a");
  println(w1);
  println(w2);
  println(join(dir_list(base), ","));
  println(dir_create_all(base + "/x/y/z"));
  println(is_dir(base + "/x/y/z"));
  return 0;
}
""",
     """true
true
true
a.txt,b.txt
true
true
""",
     ""),
    ("atomicfile.fg: replace twice, temp gone, missing dir",
     r"""import "atomicfile.fg";
fn main() -> int {
  let base = "/tmp/fs_test_atomic";
  println(mkdir(base));
  println(atomic_write(base + "/f.txt", "v1"));
  println(read_file(base + "/f.txt"));
  println(atomic_write(base + "/f.txt", "v2"));
  println(read_file(base + "/f.txt"));
  println(file_exists(base + "/f.txt.tmp"));
  println(atomic_write(base + "/gone/f.txt", "x"));
  return 0;
}
""",
     """true
true
v1
true
v2
false
false
""",
     ""),
    ("links.fg: create, read back, missing is Err 2",
     r"""import "links.fg";
import "errcode.fg";
fn main() -> int {
  let base = "/tmp/fs_test_linkslib";
  println(mkdir(base));
  let w = write_file(base + "/real.txt", "hi");
  println(w);
  println(link_create(base + "/real.txt", base + "/l.txt"));
  let r = link_read(base + "/l.txt");
  println(r.ok);
  println(r.value);
  let r2 = link_read(base + "/gone.txt");
  println(r2.ok);
  println(err_name(err_from_code(r2.error)));
  return 0;
}
""",
     """true
true
true
true
/tmp/fs_test_linkslib/real.txt
false
NotFound
""",
     ""),
    ("fileperms.fg: set, mode, chown self, missing",
     r"""import "fileperms.fg";
import "errcode.fg";
fn main() -> int {
  let base = "/tmp/fs_test_perms";
  println(mkdir(base));
  let w = write_file(base + "/f.txt", "d");
  println(w);
  println(err_name(perm_set(base + "/f.txt", 384)));
  println(perm_mode(base + "/f.txt"));
  let uid = perm_uid(base + "/f.txt");
  let gid = perm_gid(base + "/f.txt");
  println(err_name(perm_chown(base + "/f.txt", uid, gid)));
  println(err_name(perm_chown(base + "/gone.txt", 0, 0)));
  println(perm_is_dir(base));
  return 0;
}
""",
     """true
true
Success
33152
Success
NotFound
true
""",
     ""),
    ("walk.fg: full walk, files only, missing root is empty",
     r"""import "walk.fg";
fn main() -> int {
  let base = "/tmp/fs_test_walk";
  println(mkdir(base));
  println(mkdir(base + "/sub"));
  let w1 = write_file(base + "/a.txt", "a");
  let w2 = write_file(base + "/sub/b.txt", "b");
  println(w1);
  println(w2);
  println(join(walk(base), ","));
  println(join(walk_files(base), ","));
  println(len(walk(base + "/gone")));
  return 0;
}
""",
     """true
true
true
true
/tmp/fs_test_walk/a.txt,/tmp/fs_test_walk/sub,/tmp/fs_test_walk/sub/b.txt
/tmp/fs_test_walk/a.txt,/tmp/fs_test_walk/sub/b.txt
0
""",
     ""),
]

# (name, program, expected stdout, expected stderr needle).
FATAL_CASES = [
    ("readdir on a missing directory stays fatal",
     r"""fn main() -> int {
  println("start");
  let names = readdir("/tmp/fs_test_fatal_nope");
  println(len(names));
  return 0;
}
""",
     """start
""",
     "qasida: runtime error: cannot read directory"),
    ("readlink on a missing path stays fatal",
     r"""fn main() -> int {
  println("start");
  let t = readlink("/tmp/fs_test_fatal_nope");
  println(t);
  return 0;
}
""",
     """start
""",
     "qasida: runtime error: cannot read link"),
]

# (name, program, error fragment) — must be rejected at check time.
REJECT_CASES = [
    ("mkdir with no argument",
     r"""fn main() -> int {
  println(mkdir());
  return 0;
}
""",
     "mkdir() takes exactly one str argument"),
    ("mkdir with an int argument",
     r"""fn main() -> int {
  println(mkdir(42));
  return 0;
}
""",
     "mkdir() takes exactly one str argument"),
    ("readdir with an int argument",
     r"""fn main() -> int {
  let names = readdir(42);
  println(len(names));
  return 0;
}
""",
     "readdir() takes exactly one str argument"),
    ("rename with one argument",
     r"""fn main() -> int {
  println(rename("/tmp/x"));
  return 0;
}
""",
     "rename() takes exactly two arguments"),
    ("chmod with a str mode",
     r"""fn main() -> int {
  println(chmod("/tmp/x", "0600"));
  return 0;
}
""",
     "chmod() takes an int mode"),
    ("chown with two arguments",
     r"""fn main() -> int {
  println(chown("/tmp/x", 0));
  return 0;
}
""",
     "chown() takes exactly three arguments"),
    ("stat_mode with an int argument",
     r"""fn main() -> int {
  println(stat_mode(42));
  return 0;
}
""",
     "stat_mode() takes exactly one str argument"),
    ("str_compare with one argument",
     r"""fn main() -> int {
  println(str_compare("a"));
  return 0;
}
""",
     "str_compare() takes exactly two arguments"),
    ("try_readdir without importing result.fg",
     r"""fn main() -> int {
  let r = try_readdir("/tmp/x");
  println(r.ok);
  return 0;
}
""",
     'try_readdir() needs import "result.fg"'),
    ("try_readlink without importing result.fg",
     r"""fn main() -> int {
  let r = try_readlink("/tmp/x");
  println(r.ok);
  return 0;
}
""",
     'try_readlink() needs import "result.fg"'),
]

# (name, program, forge argv after the file, error fragment).
BACKEND_CASES = [
    ("emit-big32 rejects mkdir",
     r"""fn main() -> int {
  println(mkdir("/tmp/x"));
  return 0;
}
""",
     ["emit-big32"],
     "builtin mkdir() is not supported on big32 (v1)"),
    ("emit-big32 rejects readdir",
     r"""fn main() -> int {
  let names = readdir("/tmp/x");
  println(len(names));
  return 0;
}
""",
     ["emit-big32"],
     "builtin readdir() is not supported on big32 (v1)"),
    ("emit-big32 rejects str_compare",
     r"""fn main() -> int {
  println(str_compare("a", "b"));
  return 0;
}
""",
     ["emit-big32"],
     "builtin str_compare() is not supported on big32 (v1)"),
    ("emit-wasm rejects mkdir",
     r"""fn main() -> int {
  println(mkdir("/tmp/x"));
  return 0;
}
""",
     ["emit-wasm"],
     "wasm: mkdir() needs the hosted filesystem"),
    ("emit-wasm rejects str_compare",
     r"""fn main() -> int {
  println(str_compare("a", "b"));
  return 0;
}
""",
     ["emit-wasm"],
     "wasm: str_compare() needs strcmp"),
]

# (name, program, error fragment) — freestanding rejections.
FREESTANDING_CASES = [
    ("freestanding rejects mkdir",
     r"""fn main() -> int {
  let ok: bool = mkdir("/tmp/x");
  return 0;
}
""",
     "needs the hosted runtime"),
    ("freestanding rejects try_readdir",
     r"""import "result.fg";
fn main() -> int {
  let r = try_readdir("/tmp/x");
  return 0;
}
""",
     "needs the hosted runtime"),
    ("freestanding rejects str_compare",
     r"""fn main() -> int {
  let n: int = str_compare("a", "b");
  return n;
}
""",
     "needs the hosted runtime"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def _clean_scratch():
    for name in os.listdir("/tmp"):
        if name.startswith("fs_demo_") or name.startswith("fs_test_"):
            path = os.path.join("/tmp", name)
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)


def main():
    failures = []
    _clean_scratch()
    try:
        with tempfile.TemporaryDirectory() as td:
            _run_all(td, failures)
    finally:
        _clean_scratch()
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


def _run_all(td, failures):
    for demo in DEMOS:
        path = os.path.join(ROOT, "examples", demo + "_demo.fg")
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            r = run([sys.executable, os.path.join(ROOT, "forge.py")] + prefix +
                    ["run", path], ROOT)
            if not check(f"demo {demo} runs ({mode})", r.returncode == 0,
                         r.stderr.strip().splitlines()[-1] if r.stderr else ""):
                failures.append(f"demo {demo} runs ({mode})")
            elif not check(f"demo {demo} results ({mode})",
                           r.stdout == DEMO_EXPECTED[demo], repr(r.stdout)):
                failures.append(f"demo {demo} results ({mode})")
            _clean_scratch()
    for name, prog, want, needle in OK_CASES:
        p = os.path.join(td, "c.fg")
        with open(p, "w") as f:
            f.write(prog)
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            # Clean BEFORE each mode: the hosted run creates the
            # /tmp scratch dirs, and mkdir is not idempotent —
            # without this the python run sees the hosted run's
            # directories and mkdir returns false.
            _clean_scratch()
            rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                     prefix + ["run", p], ROOT)
            ok = (rr.returncode == 0 and rr.stdout == want and
                  (not needle or needle in rr.stderr))
            if not check(f"{name} ({mode})", ok,
                         repr(rr.stdout) + (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(f"{name} ({mode})")
        _clean_scratch()
    for name, prog, want, needle in FATAL_CASES:
        p = os.path.join(td, "c.fg")
        with open(p, "w") as f:
            f.write(prog)
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                     prefix + ["run", p], ROOT)
            ok = (rr.returncode != 0 and rr.stdout == want and
                  needle in rr.stderr)
            if not check(f"{name} ({mode})", ok,
                         repr(rr.stdout) + (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(f"{name} ({mode})")
    for name, prog, frag in REJECT_CASES:
        p = os.path.join(td, "c.fg")
        with open(p, "w") as f:
            f.write(prog)
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                     prefix + ["run", p], ROOT)
            ok = rr.returncode != 0 and frag in (rr.stderr + rr.stdout)
            if not check(f"{name} ({mode})", ok,
                         (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(f"{name} ({mode})")
    for name, prog, frag in FREESTANDING_CASES:
        p = os.path.join(td, "c.fg")
        with open(p, "w") as f:
            f.write(prog)
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                     prefix + ["check", p, "--freestanding"], ROOT)
            ok = (rr.returncode != 0 and
                  frag in (rr.stderr + rr.stdout))
            if not check(f"{name} ({mode})", ok,
                         (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(f"{name} ({mode})")
    for name, prog, cmd, frag in BACKEND_CASES:
        p = os.path.join(td, "c.fg")
        with open(p, "w") as f:
            f.write(prog)
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                     prefix + cmd + [p], ROOT)
            ok = rr.returncode != 0 and frag in (rr.stderr + rr.stdout)
            if not check(f"{name} ({mode})", ok,
                         (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(f"{name} ({mode})")
    for demo in DEMOS:
        path = os.path.join(ROOT, "examples", demo + "_demo.fg")
        rf = run([sys.executable, os.path.join(ROOT, "forge.py"),
                  "fmt", path], ROOT)
        if not check(f"fmt runs ({demo})", rf.returncode == 0,
                     rf.stderr.strip()):
            failures.append(f"fmt runs ({demo})")
        else:
            rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"),
                       "fmt", "--check", path], ROOT)
            if not check(f"fmt idempotent ({demo})", rf2.returncode == 0,
                         rf2.stderr.strip()):
                failures.append(f"fmt idempotent ({demo})")


if __name__ == "__main__":
    sys.exit(main())
