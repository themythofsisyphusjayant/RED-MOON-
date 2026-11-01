"""Defer statements (Top-500 #23) in a program, for backend gates.

A program uses defer when any statement is a `defer` call.
The native backend lowers defer to code emitted at block
exits; big32 and WASM reject defer programs in v1 with a
named error.
"""

import forge_lang.ast_nodes as A


def find_defers(program):
    """True when any function body contains a defer statement."""
    def walk_block(block):
        for s in getattr(block, "stmts", []) or []:
            if isinstance(s, A.Defer):
                return True
            if isinstance(s, A.Block):
                if walk_block(s):
                    return True
            for attr in ("body", "then", "els"):
                b = getattr(s, attr, None)
                if b is not None and walk_block(b):
                    return True
            for _pat, _bind, arm_body in getattr(s, "arms", []) or []:
                if walk_block(arm_body):
                    return True
        return False

    for fn in getattr(program, "funcs", []) or []:
        if getattr(fn, "type_params", None):
            continue
        if getattr(fn, "body", None) is not None:
            if walk_block(fn.body):
                return True
    return False
