"""Pinning (Top-500 #34) in a program, for backend
gates. A program uses pin when any call is to pin.
Pinning is compile-time only on native (the checker
enforces immovability, codegen emits nothing for the
statement); big32 and WASM reject pin programs with
a named error.
"""

import forge_lang.ast_nodes as A


def _walk(node):
    if isinstance(node, A.Call) and node.name == "pin":
        return True
    if isinstance(node, (list, tuple)):
        return any(_walk(x) for x in node)
    if hasattr(node, "__dict__"):
        return any(_walk(v) for v in vars(node).values())
    return False


def uses_pin(program):
    """True when any function body calls pin."""
    for fn in getattr(program, "funcs", []) or []:
        if getattr(fn, "type_params", None):
            continue
        if getattr(fn, "body", None) is not None and _walk(fn.body):
            return True
    return False
