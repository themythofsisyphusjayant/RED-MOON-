"""Weak references (Top-500 #26) in a program, for backend
gates and for the (bool, [int]) tuple typedef that
weak_upgrade's return type needs.

A program uses weak references when any call is to
weak_new or weak_upgrade. The native backend lowers
both to the runtime weak table; big32 and WASM reject
weak programs in v1 with a named error.
"""

import forge_lang.ast_nodes as A


def _walk(node):
    if isinstance(node, A.Call) and node.name in ("weak_new", "weak_upgrade"):
        return True
    if isinstance(node, (list, tuple)):
        return any(_walk(x) for x in node)
    if hasattr(node, "__dict__"):
        return any(_walk(v) for v in vars(node).values())
    return False


def uses_weak(program):
    """True when any function body calls weak_new/weak_upgrade."""
    for fn in getattr(program, "funcs", []) or []:
        if getattr(fn, "type_params", None):
            continue
        if getattr(fn, "body", None) is not None and _walk(fn.body):
            return True
    return False
