#!/usr/bin/env python3
"""Qasida compiler CLI — thin shim with hosted-first dispatch.

SWITCH-OVER (11 Nov 2026, SELFHOST_PLAN.md section 6): the hosted
Qasida compiler (bin/qasida-hosted, built from examples/selfhost_cli.fg)
is the DEFAULT compiler. This shim dispatches each invocation to the
hosted binary when the invocation is on the hosted CLI's proven
surface, and to the Python compiler (forge_lang, the reference and
fallback) otherwise. The dispatch decision is made BEFORE importing
forge_lang, so the hosted path never imports Python.

Fallback (Python compiler, end to end):
    python3 forge.py --python <cmd> ...   (--python must come first)
    QASIDA_COMPILER=python python3 forge.py <cmd> ...
Other environment:
    QASIDA_COMPILER=hosted   explicit hosted-first dispatch (the default)
    QASIDA_HOSTED_BIN=<path> use a different hosted binary
    QASIDA_DISPATCH_LOG=<file> append one line per invocation
        ("hosted|python <reason> <argv...>") for verification.

Dispatch rule (decided from a live probe of 60+ argv shapes, Python
forge.py vs the hosted binary; probe script at
~/workspace/blackmoon-iso/switchover/probes/probe_argv.py):
  hosted: [], --version, -V, version, -h, --help (bare forms);
      an unknown subcommand alone or with --help; check/emit/run/build
      using only hosted-supported flags (--mode safe, --freestanding,
      -o/--output, --keep-c, --target native, --stack-top on build,
      -h/--help); program args after the file / "--" for run are
      never inspected.
  python: any -V/--version token inside a core-command argv (the five
      known argparse corners: "-V extra", "-V check", "--bogus" alone,
      "check --version", "stack --limit --help"); --mode fast for
      emit/run/build (the hosted codegen is SAFE-ONLY — fast under
      hosted would silently change checked-arithmetic semantics;
      check --mode fast stays hosted); build --target big32|wasm,
      --debug, --shared, --wit; the deferred subcommands fmt/doc/lsp/
      repl/pkg/test/stack/emit-big32/emit-cuda/emit-wasm (except their
      bare --help forms, which are parity-proven).
  A missing hosted binary warns on stderr and falls back to Python
  (never silently). Temp-.c-path differences in cc stderr are NORM
  (they differ between two Python runs too).
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
HOSTED_DEFAULT = os.path.join(REPO_ROOT, "bin", "qasida-hosted")

CORE_COMMANDS = ("check", "emit", "run", "build")
DEFERRED_COMMANDS = ("fmt", "doc", "lsp", "repl", "pkg", "test", "stack",
                     "emit-big32", "emit-cuda", "emit-wasm")
ALL_COMMANDS = CORE_COMMANDS + DEFERRED_COMMANDS


def _log_dispatch(route, reason, argv):
    path = os.environ.get("QASIDA_DISPATCH_LOG")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write("%s\t%s\t%s\n" % (route, reason, " ".join(argv)))
    except OSError:
        pass


def _mode_value(argv, i):
    """Value of a --mode flag at position i (separate or = form)."""
    tok = argv[i]
    if tok.startswith("--mode="):
        return tok[len("--mode="):], i + 1
    if i + 1 < len(argv):
        return argv[i + 1], i + 2
    return "", i + 1


def _flag_value(argv, i):
    """Index after a value-taking flag at position i (separate or = form)."""
    tok = argv[i]
    if "=" in tok:
        return i + 1
    return i + 2 if i + 1 < len(argv) else i + 1


def _decide_core(argv):
    """Dispatch for argv[0] in check/emit/run/build.

    Scans only the flag region (before "--"; for run, before the first
    positional — everything after the file is a program arg). Returns
    ("hosted", reason) or ("python", reason).
    """
    cmd = argv[0]
    i = 1
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            break
        if cmd == "run" and not tok.startswith("-"):
            break  # first positional: the file; rest are program args
        if tok in ("-V", "--version"):
            return "python", "version flag inside %s" % cmd
        if tok == "--mode" or tok.startswith("--mode="):
            val, i = _mode_value(argv, i)
            if val == "fast" and cmd != "check":
                return "python", "--mode fast (%s is safe-only in hosted)" % cmd
            continue
        if cmd == "build" and (tok == "--target" or
                               tok.startswith("--target=")):
            if tok.startswith("--target="):
                val, i = tok[len("--target="):], i + 1
            else:
                val, i = (argv[i + 1], i + 2) if i + 1 < len(argv) else ("", i + 1)
            if val and val != "native":
                return "python", "--target %s" % val
            continue
        if cmd == "build" and tok in ("--debug", "--shared", "--wit"):
            return "python", "%s (deferred in hosted)" % tok
        if cmd == "build" and tok.startswith("--wit="):
            return "python", "--wit (deferred in hosted)"
        if tok in ("-o", "--output", "--keep-c", "--wit", "--stack-top"):
            i = _flag_value(argv, i)
            continue
        if tok.startswith(("--output=", "--keep-c=", "--wit=", "--stack-top=")):
            i += 1
            continue
        i += 1
    return "hosted", "core %s" % cmd


def _decide(argv):
    """Return ("hosted", reason) or ("python", reason) for argv."""
    if not argv:
        return "hosted", "no-args"
    first = argv[0]
    if first == "--version":
        return "hosted", "--version"
    if first == "-V":
        if len(argv) == 1:
            return "hosted", "bare -V"
        return "python", "-V with trailing args (argparse corner)"
    if first == "version":
        if len(argv) == 1:
            return "hosted", "bare version"
        if len(argv) == 2 and argv[1] in ("-h", "--help"):
            return "hosted", "version --help"
        return "python", "version with trailing args"
    if first in ("-h", "--help"):
        return "hosted", "top-level help"
    if first.startswith("-"):
        return "python", "unknown top-level flag (argparse corner)"
    if first in CORE_COMMANDS:
        return _decide_core(argv)
    if first in DEFERRED_COMMANDS:
        if len(argv) == 2 and argv[1] in ("-h", "--help"):
            return "hosted", "%s --help" % first
        return "python", "%s deferred in hosted" % first
    # Unknown subcommand: hosted reproduces argparse's invalid-choice
    # error for the bare form and with --help; anything longer is
    # unprobed, so stay with Python.
    if len(argv) == 1:
        return "hosted", "unknown subcommand"
    if len(argv) == 2 and argv[1] in ("-h", "--help"):
        return "hosted", "unknown subcommand --help"
    return "python", "unknown subcommand with extra args"


def _hosted_bin():
    return os.environ.get("QASIDA_HOSTED_BIN") or HOSTED_DEFAULT


def main():
    argv = sys.argv[1:]
    # --python must come first: anywhere else it would be a subcommand
    # flag or a program arg, and Python's own argparse owns it there.
    if argv and argv[0] == "--python":
        argv = argv[1:]
        _log_dispatch("python", "--python flag", argv)
        return _run_python(argv, "--python flag")
    if os.environ.get("QASIDA_COMPILER") == "python":
        _log_dispatch("python", "QASIDA_COMPILER=python", argv)
        return _run_python(argv, "QASIDA_COMPILER=python")
    route, reason = _decide(argv)
    _log_dispatch(route, reason, argv)
    if route == "python":
        return _run_python(argv, reason)
    hosted = _hosted_bin()
    if not (os.path.isfile(hosted) and os.access(hosted, os.X_OK)):
        print("qasida: warning: hosted compiler not found at %s; "
              "using Python fallback" % hosted, file=sys.stderr)
        _log_dispatch("python", "hosted binary missing", argv)
        return _run_python(argv, "hosted binary missing")
    os.execv(hosted, [hosted] + argv)
    return 1  # execv only returns on failure


def _run_python(argv, reason):
    sys.path.insert(0, REPO_ROOT)
    from forge_lang.cli import main as py_main  # noqa: E402
    from forge_lang import __version__ as VERSION  # noqa: E402
    # VERSION stays importable from here (forge_lang/__init__.py
    # __version__ is the single source of truth).
    _ = VERSION
    return py_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
