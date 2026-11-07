"""Fallible allocation (Top-500 #36) in a program, for backend
gates. A program uses try_alloc when any call is to try_alloc.
try_alloc is native-only in v1 (it uses calloc on the hosted
runtime); big32 and WASM reject try_alloc programs with a
named error.
"""

import forge_lang.ast_nodes as A


def _walk(node):
    if isinstance(node, A.Call) and node.name == "try_alloc":
        return True
    if isinstance(node, (list, tuple)):
        return any(_walk(x) for x in node)
    if hasattr(node, "__dict__"):
        return any(_walk(v) for v in vars(node).values())
    return False


def uses_try_alloc(program):
    """True when any function body calls try_alloc."""
    for fn in getattr(program, "funcs", []) or []:
        if getattr(fn, "type_params", None):
            continue
        if getattr(fn, "body", None) is not None and _walk(fn.body):
            return True
    return False
