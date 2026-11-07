"""Qasida compiler driver: source -> imports -> checked AST -> C -> binary."""

import os
import subprocess
import sys
import tempfile

from .errors import ForgeError
from .parser import parse
from .checker import check
from .infer import infer_types
from .codegen import generate
from . import ast_nodes as A


def _cc():
    """C compiler binary for native builds. Override with QASIDA_CC
    (e.g. a cross compiler); the default is "cc" and is unchanged."""
    return os.environ.get("QASIDA_CC", "cc")


def load_program(path, seen=None):
    """Parse a file and recursively resolve its imports into one Program.

    `seen` is a true visited set, not just the current path:
    a file already included through another import branch is
    skipped instead of included twice. Before this change the
    set was cleared on return (`seen.remove`), so diamond
    imports (nn.fg + tensor_autograd.fg both pulling in
    tensor.fg) duplicated every struct and function and
    failed with "duplicate struct 'Tensor'". That forced
    every library to avoid shared imports and made libraries
    uncombinable — the single biggest ecosystem blocker.
    Circular imports now resolve to an empty contribution
    for the repeated file; the checker's duplicate-name
    errors still catch two DIFFERENT files defining the
    same name, which is a real conflict, not dedup's job.
    """
    if seen is None:
        seen = set()
    real = os.path.realpath(path)
    if real in seen:
        return A.Program([], [], [], [])
    seen.add(real)
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    prog = parse(source)
    # Stamp this file's own functions with their source
    # file (imports are merged below, after stamping,
    # so each function keeps its own file). This is
    # what makes --debug #line directives correct
    # across files instead of misattributing stdlib
    # code to the main file.
    for fn in prog.funcs:
        fn.file = real
    for idf in (prog.impls or []):
        for m in idf.methods:
            m.file = real
    base = os.path.dirname(real)
    all_funcs = list(prog.funcs)
    all_structs = list(prog.structs or [])
    all_enums = list(prog.enums or [])
    all_traits = list(prog.traits or [])
    all_impls = list(prog.impls or [])
    all_aliases = list(prog.aliases or [])
    all_newtypes = list(prog.newtypes or [])
    for imp in prog.imports:
        # Stdlib lookup: in-package first (forge_lang/stdlib/ — works
        # both from a checkout and from an installed wheel), then the
        # legacy repo-root stdlib/ as a fallback for old checkouts.
        candidates = [
            os.path.join(base, imp),
            os.path.join(os.getcwd(), imp),
            os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "stdlib", os.path.basename(imp)),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "stdlib", os.path.basename(imp)),
        ]
        found = next((c for c in candidates if os.path.exists(c)), None)
        if found is None:
            raise ForgeError(f"import not found: {imp} (looked in {base} and stdlib)")
        sub = load_program(found, seen)
        all_funcs.extend(sub.funcs)
        all_structs.extend(sub.structs or [])
        all_enums.extend(sub.enums or [])
        all_traits.extend(sub.traits or [])
        all_impls.extend(sub.impls or [])
        all_aliases.extend(sub.aliases or [])
        all_newtypes.extend(sub.newtypes or [])
    return A.Program([], all_funcs, all_structs, all_enums,
                     all_traits, all_impls, all_aliases, all_newtypes)


def compile_source(source, mode="safe", freestanding=False):
    program = parse(source)
    check(program, freestanding=freestanding)
    types = infer_types(program)
    return generate(program, types, mode=mode, freestanding=freestanding), program


def compile_file(path, mode="safe", require_main=True, debug=False, freestanding=False):
    program = load_program(path)
    check(program, require_main=require_main, freestanding=freestanding)
    types = infer_types(program)
    return generate(program, types, mode=mode, debug=debug, freestanding=freestanding), program


def build_shared(source_path, output_path, mode="safe"):
    """Compile a Forge library (no main required) to a .so for Python ctypes."""
    c_source, _ = compile_file(source_path, mode=mode, require_main=False)
    fd, c_path = tempfile.mkstemp(suffix=".c", prefix="forge2_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(c_source)
        flags = [_cc(), "-shared", "-fPIC", "-O2", "-std=gnu11", "-Wall",
                 "-Wno-unused-function", "-pthread"]
        result = subprocess.run(flags + ["-o", output_path, c_path, "-lm", "-lssl", "-lcrypto"],
                                capture_output=True, text=True)
        if result.returncode != 0 and "cannot find -lssl" in result.stderr:
            result = subprocess.run(flags + ["-o", output_path, c_path, "-lm"],
                                    capture_output=True, text=True)
        if result.returncode != 0:
            raise ForgeError(f"C compiler failed:\n{result.stderr}")
    finally:
        try:
            os.unlink(c_path)
        except OSError:
            pass
    return output_path


def compile_file_rv(path, freestanding=False, stack_top=None):
    """Forge source -> big32 RISC-V assembly (no C, no x86)."""
    from .codegen_rv import generate_rv
    program = load_program(path)
    check(program, freestanding=freestanding)
    types = infer_types(program)
    return generate_rv(program, types, stack_top=stack_top), program


def compile_file_wasm(path, wit_path=None):
    """Forge source -> WebAssembly binary (subset, see codegen_wasm).

    With wit_path, the program is checked against the WIT world in
    that file before code generation: the world is the interface
    contract, and any mismatch fails the build.
    """
    from .codegen_wasm import generate_wasm
    program = load_program(path)
    check(program)
    types = infer_types(program)
    if wit_path is not None:
        from .wit import parse_wit, check_world
        with open(wit_path, encoding="utf-8") as f:
            world = parse_wit(f.read())
        check_world(world, program.funcs)
    return generate_wasm(program, types), program


def _is_mingw():
    """True when the selected C compiler targets Windows (MinGW)."""
    return "mingw" in _cc()


def _cc_flags(mode):
    # The generated header defines every builtin helper; unused ones
    # are expected, so silence that one warning (other -Wall warnings
    # still show).
    if mode == "fast":
        if _is_mingw():
            # -march=native is wrong for a cross-compiled binary: it
            # describes the build machine, not the target.
            return [_cc(), "-O3", "-std=gnu11", "-Wall", "-Wno-unused-function", "-pthread"]
        return [_cc(), "-O3", "-march=native", "-std=gnu11", "-Wall", "-Wno-unused-function", "-pthread"]
    return [_cc(), "-O2", "-std=gnu11", "-Wall", "-Wextra", "-Wno-unused-function", "-pthread"]


def build(source_path, output_path, mode="safe", keep_c=None, debug=False, freestanding=False):
    c_source, _ = compile_file(source_path, mode=mode, debug=debug, freestanding=freestanding)
    if keep_c:
        with open(keep_c, "w", encoding="utf-8") as f:
            f.write(c_source)
        c_path = keep_c
        cleanup = False
    else:
        fd, c_path = tempfile.mkstemp(suffix=".c", prefix="forge2_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(c_source)
        cleanup = True
    try:
        # HTTPS needs OpenSSL; if the machine lacks libssl, retry
        # without it (programs that never call http_get still link,
        # because the unused SSL helper is optimised away). On MinGW,
        # Winsock needs -lws2_32, and OpenSSL is off by default in the
        # generated C (QASIDA_HAVE_OPENSSL=1 opts back in).
        # Freestanding: no libc at all, so no -pthread, no -lm, no
        # SSL libs — just -nostdlib. The _start asm is x86_64 Linux
        # only, so freestanding native refuses MinGW outright.
        if freestanding and _is_mingw():
            raise ForgeError("freestanding native is only supported for x86_64 Linux "
                             "(the _start entry uses the Linux exit_group syscall)")
        flags = _cc_flags(mode) + (["-g"] if debug else [])
        if freestanding:
            flags = [f for f in flags if f != "-pthread"] + ["-nostdlib"]
        have_ssl = os.environ.get("QASIDA_HAVE_OPENSSL") == "1"
        no_ssl = os.environ.get("QASIDA_NO_OPENSSL") == "1"
        if no_ssl:
            flags = flags + ["-DFORGE_NO_OPENSSL"]
        elif have_ssl and _is_mingw():
            flags = flags + ["-DFORGE_HAVE_OPENSSL"]
        libs = ["-lm", "-lws2_32"] if _is_mingw() else ["-lm"]
        if freestanding:
            result = subprocess.run(flags + ["-o", output_path, c_path],
                                    capture_output=True, text=True)
        elif no_ssl:
            result = subprocess.run(flags + ["-o", output_path, c_path] + libs,
                                    capture_output=True, text=True)
        else:
            result = subprocess.run(flags + ["-o", output_path, c_path] + libs + ["-lssl", "-lcrypto"],
                                    capture_output=True, text=True)
            if result.returncode != 0 and not have_ssl and "cannot find -lssl" in result.stderr:
                result = subprocess.run(flags + ["-o", output_path, c_path] + libs,
                                        capture_output=True, text=True)
        if result.returncode != 0:
            raise ForgeError(f"C compiler failed:\n{result.stderr}")
        if result.stderr.strip():
            print(result.stderr, file=sys.stderr)
    finally:
        if cleanup:
            try:
                os.unlink(c_path)
            except OSError:
                pass
    return output_path
