"""The never/bottom type (Top-500 #14, v1).

``never`` is the type of expressions that never produce a value:
a call to a function declared ``-> never``. It is the bottom
type: a never value coerces to any expected type (at let,
assignment, argument, return, and field sites), because the code
after it never runs.

v1 rules, all checked:
- A function declared ``-> never`` must diverge: its body must
  contain a top-level diverging statement (fail, or a call to
  a never function, including inside a top-level statement's
  own expressions and conditions), and it must contain no
  return statement anywhere (a return would violate never).
  Divergence inside if/while/for/match bodies does not count:
  control can skip those.
- A non-void function whose body contains a top-level
  diverging statement satisfies the return requirement: control
  can never fall off the end past a diverger.
- Never values flow only through value sites (where codegen
  wraps them with a dummy of the expected C type, since the
  diverging call never returns) and as bare statements. Other
  expression positions reject never through their existing
  type checks.
- Representation: never is never inhabited at runtime, so its
  C placeholder is char and never functions emit void
  signatures (they never return, so no value is needed).
- v1 limits: no loop-non-termination analysis (while true is
  not recognised as diverging); big32 and WASM reject never
  programs with named errors.
"""

import re


def _type_tokens(t):
    return re.findall(r"[A-Za-z_][A-Za-z0-9_]*", t or "")


def find_never(program):
    """Every type spelling mentioning never in a program, sorted.
    Mirrors the union/fixed/sized/readonly walks."""
    from . import ast_nodes as A
    found = set()

    def add(t):
        if isinstance(t, str) and "never" in _type_tokens(t):
            found.add(t)

    def walk_block(block):
        for s in getattr(block, "stmts", []) or []:
            if isinstance(s, A.Let):
                add(s.ann)
            if isinstance(s, A.Cast):
                add(getattr(s, "target", None))
            if isinstance(s, A.Block):
                walk_block(s)
            for attr in ("body", "then", "els"):
                b = getattr(s, attr, None)
                if b is not None:
                    walk_block(b)
            for _pat, _bind, arm_body in getattr(s, "arms", []) or []:
                walk_block(arm_body)
            walk_expr(getattr(s, "expr", None))

    def walk_expr(e):
        if e is None:
            return
        if isinstance(e, A.Cast):
            add(getattr(e, "target", None))
        for v in vars(e).values():
            if isinstance(v, list):
                for item in v:
                    if hasattr(item, "__dict__"):
                        walk_expr(item)
            elif hasattr(v, "__dict__"):
                walk_expr(v)

    for fn in getattr(program, "funcs", []) or []:
        for _n, pt in getattr(fn, "params", []) or []:
            add(pt)
        add(getattr(fn, "ret", None))
        if getattr(fn, "body", None) is not None:
            walk_block(fn.body)
    for sd in getattr(program, "structs", None) or []:
        fields = sd.fields
        pairs = fields.items() if isinstance(fields, dict) else fields
        for _fname, ft in pairs:
            add(ft)
    for ed in getattr(program, "enums", None) or []:
        for pt in (getattr(ed, "variant_payloads", None) or {}).values():
            add(pt)
    for td in getattr(program, "traits", None) or []:
        for _name, params, ret, _line, _col in getattr(td, "methods", []) or []:
            for _pn, pt in params:
                add(pt)
            add(ret)
    for impl in getattr(program, "impls", None) or []:
        for m in getattr(impl, "methods", []) or []:
            for _n, pt in getattr(m, "params", []) or []:
                add(pt)
            add(getattr(m, "ret", None))
            if getattr(m, "body", None) is not None:
                walk_block(m.body)
    return sorted(found)
