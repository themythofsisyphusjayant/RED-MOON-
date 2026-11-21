"""Helpers for generic types, e.g. Option<int>, Result<int, str>.

A generic type is stored as a string: "Option<int>", "Result<int, str>",
"[Option<int>]" is rejected elsewhere (arrays of structs), but the
parser here handles nested brackets and angles correctly.
"""

SCALARS = ("int", "float", "bool", "str")


def parse_generic(t):
    """Return (base, [args]) if t is a generic type, else None."""
    if not isinstance(t, str) or "<" not in t:
        return None
    depth = 0
    base_end = None
    i = 0
    while i < len(t):
        ch = t[i]
        if ch == "-" and i + 1 < len(t) and t[i + 1] == ">":
            # Fn-type arrow, not a generic close (Top-500 #103).
            i += 2
            continue
        if ch == "<":
            if depth == 0:
                base_end = i
            depth += 1
        elif ch == ">":
            depth -= 1
            if depth == 0 and i == len(t) - 1:
                base = t[:base_end]
                inner = t[base_end + 1:-1]
                return base, split_top_level(inner)
        i += 1
    return None


def split_top_level(s):
    """Split s on top-level commas (ignoring nested <>, []).

    The fn-type arrow `->` is a single token: its `>` must not
    count as an angle-bracket close, or a generic holding a fn
    type mis-splits (Top-500 #103).
    """
    out = []
    depth_a = depth_b = 0
    cur = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "-" and i + 1 < len(s) and s[i + 1] == ">":
            cur.append("->")
            i += 2
            continue
        if ch == "<":
            depth_a += 1
        elif ch == ">":
            depth_a -= 1
        elif ch == "[":
            depth_b += 1
        elif ch == "]":
            depth_b -= 1
        if ch == "," and depth_a == 0 and depth_b == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    out.append("".join(cur).strip())
    return [o for o in out if o]


def mangle_type(t):
    """Map a Forge type string to a valid C identifier fragment."""
    from .fntypes import is_fn_type, fn_mangle
    if is_fn_type(t):
        # A fn type inside a generic instantiation (Box<fn(int) ->
        # int>) mangles to its typedef name (Top-500 #103).
        return fn_mangle(t)
    g = parse_generic(t)
    if g is not None:
        base, args = g
        return base + "_" + "_".join(mangle_type(a) for a in args)
    if t.startswith("[") and t.endswith("]"):
        return "Array_" + mangle_type(t[1:-1])
    return t


def substitute_type(t, bindings):
    """Replace type parameters in t using bindings {param: concrete}."""
    if t in bindings:
        return bindings[t]
    from .fntypes import is_fn_type, fn_parts
    if is_fn_type(t):
        # A fn type may mention type params (generic map needs
        # fn(T) -> T); substitute inside each param and the ret.
        params, ret = fn_parts(t)
        return ("fn(" + ", ".join(substitute_type(p, bindings) for p in params)
                + ") -> " + substitute_type(ret, bindings))
    g = parse_generic(t)
    if g is not None:
        base, args = g
        return base + "<" + ", ".join(substitute_type(a, bindings) for a in args) + ">"
    if t.startswith("[") and t.endswith("]"):
        return "[" + substitute_type(t[1:-1], bindings) + "]"
    return t


def unify(pattern, actual, bindings, type_params):
    """Bind type params in pattern from actual; return False on clash.

    pattern may contain type params (names in type_params); actual
    must be concrete (no type params of the caller — callers check
    that before calling unify).
    """
    if pattern in type_params:
        if pattern in bindings:
            return bindings[pattern] == actual
        bindings[pattern] = actual
        return True
    from .fntypes import is_fn_type, fn_parts
    if is_fn_type(pattern) or is_fn_type(actual):
        # Fn types unify structurally: same arity, each param and
        # the ret unify in turn. A fn type never unifies with a
        # non-fn type.
        if not (is_fn_type(pattern) and is_fn_type(actual)):
            return False
        p_params, p_ret = fn_parts(pattern)
        a_params, a_ret = fn_parts(actual)
        if len(p_params) != len(a_params):
            return False
        return (all(unify(pp, ap, bindings, type_params)
                    for pp, ap in zip(p_params, a_params))
                and unify(p_ret, a_ret, bindings, type_params))
    g1 = parse_generic(pattern)
    g2 = parse_generic(actual)
    if g1 is not None or g2 is not None:
        if g1 is None or g2 is None or g1[0] != g2[0] or len(g1[1]) != len(g2[1]):
            return False
        return all(unify(a, b, bindings, type_params) for a, b in zip(g1[1], g2[1]))
    if pattern.startswith("[") and actual.startswith("["):
        return unify(pattern[1:-1], actual[1:-1], bindings, type_params)
    return pattern == actual


def contains_type_param(t, type_params):
    if t in type_params:
        return True
    from .fntypes import is_fn_type, fn_parts
    if is_fn_type(t):
        params, ret = fn_parts(t)
        return (any(contains_type_param(p, type_params) for p in params)
                or contains_type_param(ret, type_params))
    g = parse_generic(t)
    if g is not None:
        return any(contains_type_param(a, type_params) for a in g[1])
    if t.startswith("[") and t.endswith("]"):
        return contains_type_param(t[1:-1], type_params)
    return False
