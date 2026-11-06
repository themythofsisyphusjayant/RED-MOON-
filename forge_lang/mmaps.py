"""Memory-mapped files (Top-500 #31) in a program,
for backend gates. A program uses mmap when any call
is to mmap_open, mmap_get, mmap_set, mmap_close,
mmap_grow, mmap_get32, or mmap_set32.
The native backend lowers them to the runtime mmap
table; big32 and WASM reject mmap programs in v1
with a named error.
"""

import forge_lang.ast_nodes as A

_MMAP = ("mmap_open", "mmap_get", "mmap_set", "mmap_close",
         "mmap_grow", "mmap_get32", "mmap_set32")


def _walk(node):
    if isinstance(node, A.Call) and node.name in _MMAP:
        return True
    if isinstance(node, (list, tuple)):
        return any(_walk(x) for x in node)
    if hasattr(node, "__dict__"):
        return any(_walk(v) for v in vars(node).values())
    return False


def uses_mmap(program):
    """True when any function body calls an mmap builtin."""
    for fn in getattr(program, "funcs", []) or []:
        if getattr(fn, "type_params", None):
            continue
        if getattr(fn, "body", None) is not None and _walk(fn.body):
            return True
    return False
