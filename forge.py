#!/usr/bin/env python3
"""The Jal Pari Language compiler CLI (formerly Forge v2).

Version: 0.4.0 — TinyStories word GPT (see CHANGELOG.md).

Usage:
    jalpari run examples/jal_pari_demo.fg
    jalpari --version
    python3 forge.py check <file.fg> [--mode safe|fast]
    python3 forge.py build <file.fg> [-o out] [--mode safe|fast] [--keep-c out.c]
    python3 forge.py run   <file.fg> [--mode safe|fast] [-- program args...]
    python3 forge.py emit  <file.fg> [--mode safe|fast]
    python3 forge.py test
    python3 forge.py fmt <file.fg> [--check]
    python3 forge.py lsp
    python3 forge.py repl
    python3 forge.py pkg <init|add|build|run|test|list> ...
Safe mode (default): checked int arithmetic + bounds-checked indexing.
Fast mode: unchecked, -O3 -march=native, for microsecond-latency work.
"""

import argparse
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from forge_lang.errors import ForgeError  # noqa: E402
from forge_lang.compiler import compile_file, build  # noqa: E402
from forge_lang import __version__ as VERSION  # noqa: E402
# Single source of truth: forge_lang/__init__.py:__version__.
# (It read "2.0.0" there before this change — stale; the current
# release is 1.5.0 per forge.py, CHANGELOG.md, and the tree.)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv in (["--version"], ["-V"], ["version"]):
        print(f"The Jal Pari Language {VERSION}")
        return 0
    parser = argparse.ArgumentParser(prog="jalpari", description="The Jal Pari Language compiler")
    parser.add_argument("--version", action="version", version=f"The Jal Pari Language {VERSION}")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("check", "emit"):
        p = sub.add_parser(name)
        p.add_argument("file")
        p.add_argument("--mode", choices=["safe", "fast"], default="safe")
        p.add_argument("--freestanding", action="store_true",
                       help="build without libc/OS: no files, sockets, threads, "
                            "clock, print, or strings/arrays (freestanding v1)")
    p = sub.add_parser("run")
    p.add_argument("file")
    p.add_argument("--mode", choices=["safe", "fast"], default="safe")
    p.add_argument("program_args", nargs=argparse.REMAINDER, default=[])
    sub.add_parser("test")
    p = sub.add_parser("fmt")
    p.add_argument("file")
    p.add_argument("--check", action="store_true")
    p = sub.add_parser("doc")
    p.add_argument("file")
    sub.add_parser("lsp")
    sub.add_parser("repl")
    p = sub.add_parser("pkg")
    p.add_argument("pkg_args", nargs=argparse.REMAINDER, default=[])
    p = sub.add_parser("build")
    p.add_argument("file")
    p.add_argument("--mode", choices=["safe", "fast"], default="safe")
    p.add_argument("--freestanding", action="store_true",
                   help="build without libc/OS: no files, sockets, threads, "
                        "clock, print, or strings/arrays (freestanding v1)")
    p.add_argument("--target", choices=["native", "big32", "wasm"], default="native")
    p.add_argument("--stack-top", default=None,
                   help="big32 only: initial sp value (decimal or 0x hex); "
                        "default 65532, the model flat-memory top. SOC2 "
                        "builds pass a RAM address such as 0x800F0000.")
    p.add_argument("-o", "--output", default=None)
    p.add_argument("--keep-c", default=None)
    p.add_argument("--wit", default=None,
                   help="WIT world file to check against (requires --target wasm)")
    p.add_argument("--debug", action="store_true",
                   help="emit #line directives + compile with -g so gdb steps through .fg source")
    p.add_argument("--shared", action="store_true",
                   help="build a shared library (.so) for Python ctypes, no main required")
    p = sub.add_parser("emit-big32")
    p.add_argument("file")
    p = sub.add_parser("emit-cuda")
    p.add_argument("file")
    p.add_argument("-o", "--output", default=None)
    p = sub.add_parser("emit-wasm")
    p.add_argument("file")
    p.add_argument("-o", "--output", default=None)
    p.add_argument("--wit", default=None,
                   help="WIT world file to check against")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "fmt":
            from forge_lang.pretty import format_file
            formatted = format_file(args.file)
            with open(args.file, encoding="utf-8") as f:
                original = f.read()
            if args.check:
                if formatted == original:
                    print(f"ok: {args.file} is formatted")
                    return 0
                print(f"would reformat: {args.file}")
                return 1
            with open(args.file, "w", encoding="utf-8") as f:
                f.write(formatted)
            print(f"formatted: {args.file}")
            return 0
        if args.cmd == "doc":
            from forge_lang.docgen import docs_for_file
            print(docs_for_file(args.file), end="")
            return 0
        if args.cmd == "lsp":
            from forge_lang.lsp import serve
            return serve()
        if args.cmd == "repl":
            from forge_lang.repl import repl_loop
            return repl_loop()
        if args.cmd == "pkg":
            from forge_lang.pkg import dispatch
            root = os.path.dirname(os.path.abspath(__file__))
            return dispatch(list(args.pkg_args), os.path.abspath(__file__), os.getcwd())
        if args.cmd == "check":
            compile_file(args.file, mode=args.mode, freestanding=args.freestanding)
            print("ok: no errors")
            return 0
        if args.cmd == "emit":
            c_source, _ = compile_file(args.file, mode=args.mode, freestanding=args.freestanding)
            print(c_source)
            return 0
        if args.cmd == "emit-big32":
            from forge_lang.compiler import compile_file_rv
            asm, _ = compile_file_rv(args.file)
            print(asm, end="")
            return 0
        if args.cmd == "emit-cuda":
            from forge_lang.codegen_cuda import generate_cuda
            with open(args.file, encoding="utf-8") as f:
                src = f.read()
            cuda = generate_cuda(src)
            out = args.output or (os.path.splitext(args.file)[0] + ".cu")
            with open(out, "w", encoding="utf-8") as f:
                f.write(cuda)
            print(f"built cuda: {out} ({len(cuda)} bytes) — needs a CUDA GPU + nvcc to run")
            return 0
        if args.cmd == "emit-wasm":
            from forge_lang.compiler import compile_file_wasm
            wasm, _ = compile_file_wasm(args.file, wit_path=args.wit)
            out = args.output or (os.path.splitext(args.file)[0] + ".wasm")
            with open(out, "wb") as f:
                f.write(wasm)
            print(f"built wasm: {out} ({len(wasm)} bytes)")
            return 0
        if args.cmd == "build" and getattr(args, "wit", None) \
                and args.target != "wasm":
            raise ForgeError("--wit requires --target wasm")
        if args.cmd == "build" and args.target == "big32":
            from forge_lang.compiler import compile_file_rv
            stack_top = (int(args.stack_top, 0)
                         if getattr(args, "stack_top", None) else None)
            asm, _ = compile_file_rv(args.file, freestanding=args.freestanding,
                                     stack_top=stack_top)
            out = args.output or os.path.splitext(args.file)[0]
            if out.endswith(".hex"):
                out = out[:-4]
            elif out.endswith(".s"):
                out = out[:-2]
            s_path = out + ".s"
            hex_path = out + ".hex"
            with open(s_path, "w", encoding="utf-8") as f:
                f.write(asm)
            # Assemble with big32's assembler if a checkout is available.
            candidates = []
            if os.environ.get("BIG32_DIR"):
                candidates.append(os.path.join(os.environ["BIG32_DIR"], "tools", "asm.py"))
            root = os.path.dirname(os.path.abspath(__file__))
            candidates.append(os.path.join(os.path.dirname(root), "big32", "tools", "asm.py"))
            candidates.append(os.path.expanduser("~/workspace/big32/tools/asm.py"))
            asm_tool = next((c for c in candidates if os.path.exists(c)), None)
            if asm_tool is None:
                print(f"built big32 assembly: {s_path} (big32 assembler not found; "
                      "set BIG32_DIR to assemble to .hex)")
                return 0
            proc = subprocess.run([sys.executable, asm_tool, s_path, hex_path],
                                  capture_output=True, text=True)
            if proc.returncode != 0:
                raise ForgeError(f"big32 assembler failed:\n{proc.stdout}{proc.stderr}")
            print(f"built big32: {s_path} + {hex_path}")
            return 0
        if args.cmd == "build" and args.target == "wasm":
            if args.freestanding:
                raise ForgeError("freestanding is not supported for wasm "
                                 "(WASM is always hosted)")
            from forge_lang.compiler import compile_file_wasm
            wasm, _ = compile_file_wasm(args.file, wit_path=args.wit)
            out = args.output or (os.path.splitext(args.file)[0] + ".wasm")
            with open(out, "wb") as f:
                f.write(wasm)
            print(f"built wasm: {out} ({len(wasm)} bytes)")
            return 0
        if args.cmd == "build" and args.shared:
            from forge_lang.compiler import build_shared
            out = args.output or (os.path.splitext(args.file)[0] + ".so")
            build_shared(args.file, out, mode=args.mode)
            print(f"built shared library: {out}")
            return 0
        if args.cmd == "build":
            out = args.output or os.path.splitext(args.file)[0]
            build(args.file, out, mode=args.mode, keep_c=args.keep_c,
                  debug=args.debug, freestanding=args.freestanding)
            print(f"built: {out} (mode={args.mode}"
                  f"{', freestanding' if args.freestanding else ''})")
            return 0
        if args.cmd == "test":
            root = os.path.dirname(os.path.abspath(__file__))
            suite = os.path.join(root, "tests", "run_tests.py")
            proc = subprocess.run([sys.executable, suite], cwd=root)
            return proc.returncode
        if args.cmd == "run":
            c_source, _ = compile_file(args.file, mode=args.mode)
            with tempfile.TemporaryDirectory(prefix="forge2_run_") as td:
                c_path = os.path.join(td, "prog.c")
                exe = os.path.join(td, "prog")
                with open(c_path, "w", encoding="utf-8") as f:
                    f.write(c_source)
                cc_bin = os.environ.get("JALPARI_CC", "cc")
                mingw = "mingw" in cc_bin
                flags = ([cc_bin, "-O3", "-std=gnu11", "-pthread"] if args.mode == "fast" and mingw
                         else [cc_bin, "-O3", "-march=native", "-std=gnu11", "-pthread"] if args.mode == "fast"
                         else [cc_bin, "-O2", "-std=gnu11", "-pthread"])
                if os.environ.get("JALPARI_HAVE_OPENSSL") == "1" and mingw:
                    flags = flags + ["-DFORGE_HAVE_OPENSSL"]
                if os.environ.get("JALPARI_NO_OPENSSL") == "1":
                    flags = flags + ["-DFORGE_NO_OPENSSL"]
                libs = ["-lm", "-lws2_32"] if mingw else ["-lm"]
                if os.environ.get("JALPARI_NO_OPENSSL") == "1":
                    cc = subprocess.run(flags + ["-o", exe, c_path] + libs,
                                        capture_output=True, text=True)
                else:
                    cc = subprocess.run(flags + ["-o", exe, c_path] + libs + ["-lssl", "-lcrypto"],
                                        capture_output=True, text=True)
                    if cc.returncode != 0 and "cannot find -lssl" in cc.stderr:
                        cc = subprocess.run(flags + ["-o", exe, c_path] + libs,
                                            capture_output=True, text=True)
                if cc.returncode != 0:
                    raise ForgeError(f"C compiler failed:\n{cc.stderr}")
                prog_args = list(args.program_args)
                if prog_args and prog_args[0] == "--":
                    prog_args = prog_args[1:]
                proc = subprocess.run([exe] + prog_args)
                return proc.returncode
    except ForgeError as e:
        print(f"jalpari: error: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print(f"jalpari: error: file not found: {args.file}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"jalpari: error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
