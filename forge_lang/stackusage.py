#!/usr/bin/env python3
"""Stack-usage diagnostics (Top-500 #38, v1).

`qasida stack <file.fg>` reports the max stack frame size per
Qasida function, measured from the real C compiler rather than
estimated from the source: the program is compiled to C exactly
as `qasida emit` does, then compiled with `cc -fstack-usage`
and the `.su` file is parsed. Frames are measured at -O0 (no
inlining) so every Qasida function appears with its own frame;
optimized builds may inline small functions and shrink frames,
and the report says so.

Why it matters: Qasida arrays and strings are heap-backed, so
frames stay small by default — but a function with hundreds of
locals, or a big struct of scalars passed by value, can blow
past the 2048-byte frame budget kernels use. The report warns
on any frame over the limit (default 2048, `--limit N`).

Name mapping (C symbol -> Qasida function): plain functions keep
their name; generic instantiations mangle as name_type
(`generic_id_int`); methods mangle as Struct__method
(`Point__sum`); freestanding main is `qasida_main`. Runtime
helpers (`forge_*`) are summarized, not listed. A function the
C compiler never emits — an uninstantiated generic, or an
extern — is reported as not emitted, never silently dropped.

Native only in v1: stack frames are a C-backend concept.
big32 and WASM have no C to measure, and the `stack` command
takes no --target flag.
"""

import os
import re
import subprocess
import tempfile

from .compiler import _cc, compile_file
from .errors import ForgeError

DEFAULT_LIMIT = 2048

# `.su` line: file:line:col:name<TAB>size<TAB>qualifier
# qualifier is "static" or "dynamic[,bounded|unbounded]".
_SU_RE = re.compile(r"^[^:\t]+:\d+:\d+:([^\t]+)\t(\d+)\t(.*)$")


def parse_su(text):
    """Parse `cc -fstack-usage` output into [(name, size, qualifier)]."""
    entries = []
    for line in text.splitlines():
        m = _SU_RE.match(line)
        if m:
            entries.append((m.group(1), int(m.group(2)), m.group(3)))
    return entries


def _display(name):
    """Qasida-side display for a stored function name.

    Methods are stored mangled (Point__sum); show them as
    Point::sum. Plain names pass through unchanged.
    """
    if "__" in name:
        struct, _, method = name.rpartition("__")
        if struct and method:
            return f"{struct}::{method}"
    return name


def _label(c_name, known_names, templates):
    """Map a C symbol to (display label, kind, Qasida name).

    kind is "function" (a Qasida function), "runtime" (a forge_*
    helper), or "other" (an unmapped C function, reported under
    its C name rather than hidden). The Qasida name is None for
    runtime/other entries. `templates` is the set of generic
    function names (type_params non-empty): monomorphization
    appends a concrete FuncDef named template_type
    (identity_int) next to the template, so an exact match on
    that name reports under the template.
    """
    base = c_name.split(".")[0]  # strip .isra/.part clones
    suffix = f" (as {c_name})" if base != c_name else ""
    if base in ("main", "qasida_main"):
        return "main" + suffix, "function", "main"
    for t in sorted(templates, key=len, reverse=True):
        if base == t or base.startswith(t + "_"):
            return f"{_display(t)} (as {base})" + suffix, "function", t
    if base in known_names:
        return f"{_display(base)} (as {base})" + suffix \
            if "__" in base else base + suffix, "function", base
    # Longest known name that is a prefix followed by "_"
    # (generic instantiation: name_type).
    for name in sorted(known_names, key=len, reverse=True):
        if base.startswith(name + "_"):
            return f"{_display(name)} (as {base})" + suffix, \
                "function", name
    if "__" in base:
        struct, _, method = base.rpartition("__")
        # The method may itself carry a generic suffix (get_int).
        m = method
        while m:
            if m in known_names:
                return (f"{struct}::{m} (as {base})" + suffix,
                        "function", m)
            if "_" not in m:
                break
            m = m.rsplit("_", 1)[0]
    if base.startswith(("forge_", "__forge")):
        return c_name, "runtime", None
    return c_name, "other", None


def measure(path, mode="safe", limit=DEFAULT_LIMIT, freestanding=False):
    """Measure per-function stack frames for a Qasida program.

    Returns a report dict (see format_report). Raises ForgeError
    on a checker error or a C compiler failure.
    """
    if limit < 0:
        raise ForgeError("--limit must be >= 0")
    c_source, program = compile_file(path, mode=mode,
                                     freestanding=freestanding)
    with tempfile.TemporaryDirectory(prefix="qasida_stack_") as td:
        c_path = os.path.join(td, "prog.c")
        with open(c_path, "w", encoding="utf-8") as f:
            f.write(c_source)
        flags = [_cc(), "-O0", "-std=gnu11", "-pthread", "-fstack-usage",
                 "-c", c_path, "-o", os.path.join(td, "prog.o")]
        if os.environ.get("QASIDA_NO_OPENSSL") == "1":
            flags.append("-DFORGE_NO_OPENSSL")
        cc = subprocess.run(flags, capture_output=True, text=True, cwd=td)
        if cc.returncode != 0:
            raise ForgeError(f"C compiler failed:\n{cc.stderr}")
        su_path = os.path.join(td, "prog.su")
        if not os.path.exists(su_path):
            raise ForgeError("C compiler produced no stack-usage data "
                             "(expected prog.su)")
        with open(su_path, encoding="utf-8") as f:
            entries = parse_su(f.read())

    known = {}
    templates = set()
    for fn in program.funcs or []:
        known.setdefault(fn.name, fn)
        if getattr(fn, "type_params", None):
            templates.add(fn.name)
    found = set()
    functions = []
    runtime = []
    other = []
    for c_name, size, qual in entries:
        label, kind, qname = _label(c_name, set(known), templates)
        if kind == "function":
            if qname is not None:
                found.add(qname)
                # A monomorphized FuncDef (identity_int) is the
                # emitted form of its template (identity): the
                # entry above was reported under the template, so
                # mark the instantiated name found too.
                for kname in known:
                    if kname.startswith(qname + "_"):
                        found.add(kname)
            functions.append((label, size, qual))
        elif kind == "runtime":
            runtime.append((c_name, size, qual))
        else:
            other.append((label, size, qual))
    functions.sort(key=lambda row: (-row[1], row[0]))
    other.sort(key=lambda row: (-row[1], row[0]))

    not_emitted = []
    for name, fn in known.items():
        if name in found:
            continue
        if getattr(fn, "is_extern", False):
            not_emitted.append((name, "extern (defined in C)"))
        elif getattr(fn, "type_params", None):
            not_emitted.append((name, "never instantiated"))
        else:
            not_emitted.append((name, "not in emitted C"))

    over = [(label, size) for label, size, _ in functions
            if size > limit]
    over.sort(key=lambda row: (-row[1], row[0]))
    runtime_max = max(runtime, key=lambda row: row[1]) if runtime else None
    return {
        "file": path,
        "mode": mode,
        "limit": limit,
        "functions": functions,
        "other": other,
        "not_emitted": sorted(not_emitted),
        "max": functions[0][:2] if functions else None,
        "warnings": over,
        "runtime": {
            "count": len(runtime),
            "max": (runtime_max[0], runtime_max[1])
            if runtime_max else None,
        },
    }


def format_report(report):
    """Render a measurement as the `qasida stack` text report."""
    lines = [
        f"stack usage for {report['file']}",
        "measured at -O0 (no inlining); optimized builds may inline "
        "small functions and shrink frames",
    ]
    for label, size, qual in report["functions"]:
        lines.append(f"  {label}: {size} bytes ({qual})")
    for name, reason in report["not_emitted"]:
        lines.append(f"  {name}: not emitted ({reason})")
    for label, size, qual in report["other"]:
        lines.append(f"  {label}: {size} bytes ({qual}) [C function]")
    if report["max"] is not None:
        label, size = report["max"]
        lines.append(f"max frame: {label}, {size} bytes")
    for label, size in report["warnings"]:
        lines.append(f"warning: {label} ({size} bytes) exceeds the "
                     f"{report['limit']}-byte limit")
    runtime = report["runtime"]
    if runtime["count"]:
        name, size = runtime["max"]
        lines.append(f"runtime helpers: {runtime['count']} functions, "
                     f"max frame {size} bytes ({name})")
    return "\n".join(lines) + "\n"
