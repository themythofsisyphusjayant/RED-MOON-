"""Fix 1 Phase B1 — bounds-check hoisting proofs (H1, H2, H1-D).

Pure analysis pass over the checked AST. Runs after the checker,
before native codegen (called from Codegen.generate), and annotates
nothing on the AST itself: it returns

    covered: set of id(Index node) proven in-bounds
    guards:  dict id(loop node) -> [guard C strings] (in emit order)

Codegen consults only these two results, and only in safe mode with
bounds checks on (the fast emission is reused for covered uses — no
third emission path).

DESIGN.md references: H1 §2 (counted while), H2 §2 (for range),
H1-D §2 (descending while), H1-G (sized arrays, folded into H1),
R4 (post-loop counter interval, used only to prove H1-D-P3).

Soundness notes (deviations from the DESIGN.md guard text, all in
the direction of *fewer* traps, never more):
  * H1b var bound: the guard carries the loop-entry condition
    ``L < B`` — without it a loop that never runs (entry i >= B)
    would newly trap when B > len(a). Same for H2 RangeLit with a
    var end (``s < e``).
  * H1-D: the guard re-evaluates the *entry expression* E (only when
    E is stable: its vars are not written between the entry write
    and the loop), not its interval upper bound hi_E. A hi_E guard
    would falsely trap when the interval is loose (entry k < len(a)
    <= hi_E). The guard's bound comparison also depends on which
    index forms are covered: ``E >= len`` when an ``a[k]`` use is
    covered, ``E > len`` when only ``a[k-1]`` uses are covered.
  * H1b literal bound: if the entry literal L >= B the loop never
    runs, so no proof is recorded at all (no guard, checks stay).

The analysis is total: unprovable code yields no proof (checks
stay). It never raises on user code; generate() additionally
treats any unexpected failure as "no proofs".
"""

import re

from . import ast_nodes as A

FAIL_MSG = 'forge_fail("array index out of bounds")'

# Interval magnitudes are capped so the Python analysis and the
# hosted Qasida mirror agree exactly (Qasida ints are 64-bit).
_CAP = 1 << 40


# ------------------------------------------------------------------
# small helpers
# ------------------------------------------------------------------

def _is_var(node, name=None):
    return isinstance(node, A.Var) and (name is None or node.name == name)


def _is_intlit(node, value=None):
    return isinstance(node, A.IntLit) and (value is None or node.value == value)


def _is_len_of(node, arr):
    """len(a) in either spelling: len(a) or a.len()."""
    if isinstance(node, A.Call) and node.name == "len" and len(node.args) == 1:
        return _is_var(node.args[0], arr)
    if isinstance(node, A.MethodCall) and node.method == "len" \
            and not node.args and _is_var(node.base, arr):
        return True
    return False


def _c_expr(node):
    """C rendering of a pure int expr (literal / var / + - * binop /
    unary minus). Returns None for anything else."""
    if isinstance(node, A.IntLit):
        return str(node.value)
    if isinstance(node, A.Var):
        return node.name
    if isinstance(node, A.UnaryOp) and node.op == "-":
        inner = _c_expr(node.expr)
        return None if inner is None else "(-" + inner + ")"
    if isinstance(node, A.BinOp) and node.op in ("+", "-", "*"):
        l = _c_expr(node.left)
        r = _c_expr(node.right)
        if l is None or r is None:
            return None
        return "(" + l + " " + node.op + " " + r + ")"
    if isinstance(node, A.Call) and node.name == "len" and len(node.args) == 1:
        inner = _c_expr(node.args[0])
        return None if inner is None else "(" + inner + ").len"
    return None


def _sized_len(type_str):
    """N for a sized array type spelling '[T; N]', else None."""
    if not type_str:
        return None
    m = re.match(r"^\s*(?:readonly\s+)?\[.*;\s*(\d+)\s*\]\s*$", type_str)
    return int(m.group(1)) if m else None


def _is_array_type(type_str):
    if not type_str:
        return False
    t = type_str.strip()
    if t.startswith("readonly "):
        t = t[len("readonly "):].strip()
    return t.startswith("[")


def _cap(v):
    if v is None:
        return None
    if v > _CAP or v < -_CAP:
        return None
    return v


# ------------------------------------------------------------------
# generic AST walking (dataclass nodes)
# ------------------------------------------------------------------

def _children(node):
    """Direct child AST nodes of `node` (via dataclass fields)."""
    if isinstance(node, (list, tuple)):
        for item in node:
            yield from _children(item)
        return
    if not hasattr(node, "__dataclass_fields__"):
        return
    for f in node.__dataclass_fields__:
        v = getattr(node, f, None)
        if isinstance(v, (list, tuple)):
            for item in v:
                if hasattr(item, "__dataclass_fields__"):
                    yield item
                elif isinstance(item, (list, tuple)):
                    yield from _children(item)
        elif hasattr(v, "__dataclass_fields__"):
            yield v


def _walk(node):
    yield node
    for c in _children(node):
        yield from _walk(c)


def _subtree_has_kind(node, kinds):
    return any(isinstance(n, kinds) for n in _walk(node))


def _has_push(node):
    for n in _walk(node):
        if isinstance(n, A.Call) and n.name == "push":
            return True
        if isinstance(n, A.MethodCall) and n.method == "push":
            return True
    return False


def _has_spawn_or_defer(node):
    return _subtree_has_kind(node, (A.Spawn, A.Defer))


def _write_sites(node, name):
    """Assign/Let/For nodes in `node`'s subtree that bind `name`."""
    out = []
    for n in _walk(node):
        if isinstance(n, A.Assign) and n.name == name:
            out.append(n)
        elif isinstance(n, A.Let) and n.name == name:
            out.append(n)
        elif isinstance(n, A.For) and n.name == name:
            out.append(n)
    return out


def _has_move_of(node, name):
    for n in _walk(node):
        if isinstance(n, A.Call) and n.name == "move" and n.args \
                and _is_var(n.args[0], name):
            return True
    return False


def _has_field_assign_to(node, name):
    for n in _walk(node):
        if isinstance(n, A.FieldAssign) and _is_var(n.target.base, name):
            return True
    return False


def _vars_in(node):
    return [n.name for n in _walk(node) if isinstance(n, A.Var)]


def _collect_uses(body, arr, pred):
    """Index nodes in `body` with base Var(arr) whose index satisfies
    pred(index-node). Excludes an Index that is the base of a
    FieldAccess (its check lives in the FieldAccess emitter)."""
    out = []

    def rec(node, field_base=False):
        if isinstance(node, A.FieldAccess) and isinstance(node.base, A.Index):
            # Walk the field-access base's *index* expr normally
            # (it may hold a nested covered use), but not the
            # Index node itself.
            rec(node.base.index, False)
            rec(node.base.base, False)
            return
        if isinstance(node, A.Index) and not field_base:
            if _is_var(node.base, arr) and pred(node.index):
                out.append(node)
        for c in _children(node):
            rec(c, False)

    rec(body)
    return out


# ------------------------------------------------------------------
# environment: per-name type / interval / sized length, threaded
# sequentially through a block; nested blocks get a copy.
# ------------------------------------------------------------------

class _Env:
    def __init__(self):
        self.types = {}    # name -> type spelling ("" = unknown)
        self.iv = {}       # name -> (lo, hi); None end = unbounded
        self.sized = {}    # name -> N for sized arrays

    def copy(self):
        e = _Env()
        e.types = dict(self.types)
        e.iv = dict(self.iv)
        e.sized = dict(self.sized)
        return e

    def type_of(self, name):
        return self.types.get(name, "")

    def interval_of(self, name):
        return self.iv.get(name, (None, None))

    def set_interval(self, name, iv):
        if iv is None:
            self.iv.pop(name, None)
        else:
            self.iv[name] = iv

    def drop_interval(self, name):
        self.iv.pop(name, None)


def _interval(node, env):
    """(lo, hi) interval of an int expr, None end = unbounded.
    Literals, vars (env), + - * on intervals, unary -, len() >= 0."""
    if isinstance(node, A.IntLit):
        return (_cap(node.value), _cap(node.value))
    if isinstance(node, A.Var):
        return env.interval_of(node.name)
    if isinstance(node, A.UnaryOp) and node.op == "-":
        inner = _interval(node.expr, env)
        lo, hi = inner
        return (_cap(-hi) if hi is not None else None,
                _cap(-lo) if lo is not None else None)
    if isinstance(node, A.BinOp) and node.op in ("+", "-", "*"):
        llo, lhi = _interval(node.left, env)
        rlo, rhi = _interval(node.right, env)
        if node.op == "+":
            lo = None if llo is None or rlo is None else _cap(llo + rlo)
            hi = None if lhi is None or rhi is None else _cap(lhi + rhi)
            return (lo, hi)
        if node.op == "-":
            lo = None if llo is None or rhi is None else _cap(llo - rhi)
            hi = None if lhi is None or rlo is None else _cap(lhi - rlo)
            return (lo, hi)
        # *: unknown if any end unbounded (conservative; B1 needs
        # only + / - , e.g. nlv - 1). Also unknown when any |end|
        # exceeds 10**6: the hosted mirror must not multiply large
        # ends (its checked * would trap the compiler itself), so
        # both sides apply the same threshold.
        if None in (llo, lhi, rlo, rhi):
            return (None, None)
        if max(abs(llo), abs(lhi), abs(rlo), abs(rhi)) > 10 ** 6:
            return (None, None)
        ps = [llo * rlo, llo * rhi, lhi * rlo, lhi * rhi]
        return (_cap(min(ps)), _cap(max(ps)))
    if _is_len_call(node):
        return (0, None)
    return (None, None)


def _is_len_call(node):
    if isinstance(node, A.Call) and node.name == "len" and len(node.args) == 1:
        return True
    if isinstance(node, A.MethodCall) and node.method == "len" and not node.args:
        return True
    return False


def _derive_type(expr, env):
    """Best-effort array type of an init expr: annotation is handled
    by the caller; here ArrayLit / Var-copy / sized passthrough."""
    if isinstance(expr, A.ArrayLit) and expr.elems:
        first = expr.elems[0]
        if isinstance(first, A.IntLit):
            et = "int"
        elif isinstance(first, A.FloatLit):
            et = "float"
        elif isinstance(first, A.StrLit):
            et = "str"
        elif isinstance(first, A.BoolLit):
            et = "bool"
        elif isinstance(first, A.ArrayLit):
            inner = _derive_type(first, env)
            et = inner if inner else "?"
        elif isinstance(first, A.Var):
            et = env.type_of(first.name)
            if not et:
                return ""
            return et if et.startswith("[") else "[" + et + "]"
        else:
            return ""
        return "[" + et + "]"
    if isinstance(expr, A.Var):
        return env.type_of(expr.name)
    return ""


# ------------------------------------------------------------------
# proof attempts (each returns a list of (covered_ids, guard|None)
# triples, or [] when nothing is proven)
# ------------------------------------------------------------------

def _nearest_entry(stmts, pos, name):
    """Nearest preceding write of `name` before stmts[pos] in the
    same block: (stmt_index, stmt) or (None, None)."""
    for k in range(pos - 1, -1, -1):
        s = stmts[k]
        if isinstance(s, (A.Let, A.Assign)) and s.name == name:
            return (k, s)
        if isinstance(s, A.For) and s.name == name:
            return (k, s)
    return (None, None)


def _entry_stale(stmts, k, pos, name):
    """B1-FIX (stale entry): True when `name` is written by any
    statement between the entry write at stmts[k] and the loop at
    stmts[pos]. Writes inside an intervening if/loop/block count:
    the entry value is unknowable there, so the nearest literal is
    stale — a negative runtime entry would turn a "proven" a[i]
    into an unchecked OOB access. Callers treat a stale entry as
    no entry."""
    for s in stmts[k + 1:pos]:
        if _write_sites(s, name):
            return True
    return False


def _counter_discipline(body, name, step):
    """H1-P4/P5 / H1D-P5: exactly one write to `name` in the body,
    and it is the last direct child, `name = name <step> 1`."""
    if not body.stmts:
        return False
    sites = _write_sites(body, name)
    if len(sites) != 1 or sites[0] is not body.stmts[-1]:
        return False
    last = body.stmts[-1]
    if not isinstance(last, A.Assign) or last.name != name:
        return False
    e = last.expr
    return (isinstance(e, A.BinOp) and e.op == step
            and _is_var(e.left, name) and _is_intlit(e.right, 1))


def _array_ok(body, arr):
    """Shared H1-P6/P7/H2-P2/P4/H1D-P1/P6 guards for one array:
    no reassign/shadow/move of `arr`, no push, no spawn/defer."""
    if _write_sites(body, arr):
        return False
    if _has_move_of(body, arr):
        return False
    if _has_field_assign_to(body, arr):
        return False
    if _has_push(body):
        return False
    if _has_spawn_or_defer(body):
        return False
    return True


def _guard_for_bound(kind, arr, bound, entry_lit, env):
    """H1b/H2 guard text, or None when no guard is needed, or the
    sentinel "FAIL" when the bound provably exceeds a sized len.
    `bound` is ("len",) / ("lit", v) / ("var", name).
    `entry_lit` is the entry literal L (H1) or start literal s (H2
    RangeLit), used for the loop-entry condition."""
    sized_n = env.sized.get(arr)
    if bound[0] == "len":
        return None
    if bound[0] == "lit":
        v = bound[1]
        if sized_n is not None:
            return None if v <= sized_n else "FAIL"
        if entry_lit is not None and entry_lit >= v:
            return "NEVER"  # loop never runs; no proof at all
        return f"if ({v} > ({arr}).len) {FAIL_MSG};"
    # var bound
    bname = bound[1]
    if sized_n is not None:
        _lo, hi = env.interval_of(bname)
        if hi is not None and hi <= sized_n:
            return None
        if _lo is not None and _lo > sized_n and entry_lit is not None \
                and entry_lit < _lo:
            return "FAIL"
    if entry_lit is not None:
        return (f"if ({entry_lit} < {bname} && {bname} > ({arr}).len) "
                f"{FAIL_MSG};")
    return f"if ({bname} > ({arr}).len) {FAIL_MSG};"


def _try_h1(stmt, stmts, pos, env):
    body = stmt.body
    cond = stmt.cond
    if not (isinstance(cond, A.BinOp) and cond.op == "<"
            and isinstance(cond.left, A.Var)):
        return []
    ctr = cond.left.name
    bound_expr = cond.right
    # H1-P2: entry literal.
    _k, w = _nearest_entry(stmts, pos, ctr)
    if w is None or not isinstance(w, (A.Let, A.Assign)):
        return []
    if _entry_stale(stmts, _k, pos, ctr):
        return []
    if not _is_intlit(w.expr) or w.expr.value < 0:
        return []
    entry_lit = w.expr.value
    # H1-P4/P5: counter discipline.
    if not _counter_discipline(body, ctr, "+"):
        return []
    # Bound form.
    if isinstance(bound_expr, A.Call) or isinstance(bound_expr, A.MethodCall):
        bound_kind = "len"
    elif _is_intlit(bound_expr):
        bound_kind = "lit"
        bound = ("lit", bound_expr.value)
    elif isinstance(bound_expr, A.Var):
        bound_kind = "var"
        bound = ("var", bound_expr.name)
        if _write_sites(body, bound_expr.name):
            return []
    else:
        return []
    if bound_kind == "len":
        # Candidate arrays: bases of a[ctr] uses in the body.
        triples = []
        for arr in _candidate_arrays(body, ctr):
            if not _is_array_type(env.type_of(arr)):
                continue
            if not _array_ok(body, arr):
                continue
            if not _is_len_of(bound_expr, arr):
                continue
            uses = _collect_uses(body, arr, lambda ix: _is_var(ix, ctr))
            if uses:
                triples.append(([id(u) for u in uses], None))
        return triples
    triples = []
    for arr in _candidate_arrays(body, ctr):
        if not _is_array_type(env.type_of(arr)):
            continue
        if not _array_ok(body, arr):
            continue
        g = _guard_for_bound(bound_kind, arr, bound, entry_lit, env)
        if g in ("FAIL", "NEVER"):
            continue
        uses = _collect_uses(body, arr, lambda ix: _is_var(ix, ctr))
        if uses:
            triples.append(([id(u) for u in uses], g))
    return triples


def _candidate_arrays(body, ctr):
    """Distinct Var bases of Index nodes in `body` whose index is
    exactly Var(ctr). (FieldAccess-base Indexes excluded.)"""
    out = []

    def rec(node):
        if isinstance(node, A.FieldAccess) and isinstance(node.base, A.Index):
            rec(node.base.index)
            rec(node.base.base)
            return
        if isinstance(node, A.Index) and isinstance(node.base, A.Var) \
                and _is_var(node.index, ctr):
            if node.base.name not in out:
                out.append(node.base.name)
        for c in _children(node):
            rec(c)

    rec(body)
    return out


def _try_h1d(stmt, stmts, pos, env):
    body = stmt.body
    cond = stmt.cond
    if not (isinstance(cond, A.BinOp) and cond.op == ">"
            and isinstance(cond.left, A.Var)):
        return []
    ctr = cond.left.name
    lexpr = cond.right
    # H1D-P2/P3: L literal >= 0, or var with proven lo >= 0, invariant.
    if _is_intlit(lexpr):
        if lexpr.value < 0:
            return []
        l_iv = (lexpr.value, lexpr.value)
        l_code = str(lexpr.value)
    elif isinstance(lexpr, A.Var):
        lo, _hi = env.interval_of(lexpr.name)
        if lo is None or lo < 0:
            return []
        if _write_sites(body, lexpr.name):
            return []
        l_iv = env.interval_of(lexpr.name)
        l_code = lexpr.name
    else:
        return []
    # H1D-P4: entry write with a compile-time interval.
    _k, w = _nearest_entry(stmts, pos, ctr)
    if w is None or not isinstance(w, (A.Let, A.Assign)):
        return []
    if _entry_stale(stmts, _k, pos, ctr):
        return []
    entry_expr = w.expr
    elo, ehi = _interval(entry_expr, env)
    if ehi is None:
        return []
    # Never runs: entry hi <= L lo.
    if l_iv[0] is not None and ehi <= l_iv[0]:
        return []
    # H1D-P5: decrement discipline.
    if not _counter_discipline(body, ctr, "-"):
        return []
    # Guard needs the entry *value*, not the interval bound: E must
    # be stable (its vars unwritten between the entry write and the
    # loop) or a singleton interval.
    e_code = _c_expr(entry_expr)
    stable = e_code is not None
    if stable:
        for v in _vars_in(entry_expr):
            for s in stmts[_k + 1:pos]:
                if _write_sites(s, v):
                    stable = False
    singleton = (elo is not None and elo == ehi)
    if not stable and not singleton:
        return []
    if singleton:
        e_val = str(elo)
    else:
        e_val = e_code
    triples = []
    for arr in _candidate_arrays_h1d(body, ctr):
        if not _is_array_type(env.type_of(arr)):
            continue
        if not _array_ok(body, arr):
            continue
        uses_k = _collect_uses(body, arr, lambda ix: _is_var(ix, ctr))
        uses_km1 = _collect_uses(
            body, arr,
            lambda ix: isinstance(ix, A.BinOp) and ix.op == "-"
            and _is_var(ix.left, ctr) and _is_intlit(ix.right, 1))
        uses = uses_k + uses_km1
        if not uses:
            continue
        if uses_k:
            cmp = ">="  # entry k >= len(a) traps the a[k] use
        else:
            cmp = ">"   # only a[k-1]: entry k > len(a) traps it
        if singleton:
            guard = (f"if ({e_val} > ({l_code}) && {e_val} {cmp} ({arr}).len) "
                     f"{FAIL_MSG};")
            # Static entry check for a literal L.
            if _is_intlit(lexpr) and elo <= lexpr.value:
                continue
        else:
            guard = (f"if (({e_val}) > ({l_code}) && ({e_val}) {cmp} ({arr}).len) "
                     f"{FAIL_MSG};")
        triples.append(([id(u) for u in uses], guard))
    return triples


def _candidate_arrays_h1d(body, ctr):
    out = []

    def rec(node):
        if isinstance(node, A.FieldAccess) and isinstance(node.base, A.Index):
            rec(node.base.index)
            rec(node.base.base)
            return
        if isinstance(node, A.Index) and isinstance(node.base, A.Var):
            ix = node.index
            ok = _is_var(ix, ctr) or (
                isinstance(ix, A.BinOp) and ix.op == "-"
                and _is_var(ix.left, ctr) and _is_intlit(ix.right, 1))
            if ok and node.base.name not in out:
                out.append(node.base.name)
        for c in _children(node):
            rec(c)

    rec(body)
    return out


def _try_h2(stmt, env):
    body = stmt.body
    ctr = stmt.name
    it = stmt.expr
    bound = None       # ("len",) / ("lit", v) / ("var", name)
    guard_kind = None  # "range" | "rangelit"
    start_lit = None
    if isinstance(it, A.Call) and it.name == "range" and len(it.args) == 1:
        arg = it.args[0]
        guard_kind = "range"
        if _is_intlit(arg):
            bound = ("lit", arg.value)
        elif isinstance(arg, A.Var):
            bound = ("var", arg.name)
            if _write_sites(body, arg.name):
                return []
        elif isinstance(arg, (A.Call, A.MethodCall)):
            bound = ("len", arg)  # resolved per-array below
        else:
            return []
    elif isinstance(it, A.RangeLit):
        guard_kind = "rangelit"
        if not _is_intlit(it.start) or it.start.value < 0:
            return []
        start_lit = it.start.value
        e = it.end
        if _is_intlit(e):
            bound = ("lit", e.value)
            if start_lit >= e.value:
                return []
        elif isinstance(e, A.Var):
            bound = ("var", e.name)
            if _write_sites(body, e.name):
                return []
        elif isinstance(e, (A.Call, A.MethodCall)):
            bound = ("len", e)
        else:
            return []
    else:
        return []
    # H2-P3 (belt & braces on top of the checker rule): no write to
    # the loop variable anywhere in the body.
    if _write_sites(body, ctr):
        return []
    triples = []
    for arr in _candidate_arrays(body, ctr):
        if not _is_array_type(env.type_of(arr)):
            continue
        if not _array_ok(body, arr):
            continue
        if bound[0] == "len":
            if not _is_len_of(bound[1], arr):
                continue
            g = None
        elif guard_kind == "range":
            g = _guard_for_bound("range", arr, bound, None, env)
            if g in ("FAIL", "NEVER"):
                continue
            # range(n) guard needs no entry condition: n > len(a)
            # already implies n >= 1, i.e. the loop runs.
            if bound[0] == "lit" and bound[1] <= 0:
                continue
        else:  # rangelit with lit/var end
            g = _guard_for_bound("rangelit", arr, bound, start_lit, env)
            if g in ("FAIL", "NEVER"):
                continue
        uses = _collect_uses(body, arr, lambda ix: _is_var(ix, ctr))
        if uses:
            triples.append(([id(u) for u in uses], g))
    return triples


# ------------------------------------------------------------------
# block analysis (sequential env threading)
# ------------------------------------------------------------------

def _analyze_block(stmts, env, covered, guards):
    """Analyze stmts in order, threading `env` (mutated in place
    for this block's own copy). Nested blocks are analyzed on
    copies; their lets never leak out."""
    for pos, stmt in enumerate(stmts):
        if isinstance(stmt, A.While):
            triples = []
            try:
                triples = _try_h1(stmt, stmts, pos, env)
                if not triples:
                    triples = _try_h1d(stmt, stmts, pos, env)
            except Exception:
                triples = []
            for ids, g in triples:
                covered.update(ids)
                if g is not None:
                    guards.setdefault(id(stmt), []).append(g)
            # Recurse into the body on a copy (nested loops inside).
            _analyze_block(stmt.body.stmts, env.copy(), covered, guards)
            # Post-loop counter fact (R4) + stale intervals.
            _apply_loop_exit(stmt, stmts, pos, env)
        elif isinstance(stmt, A.For):
            triples = []
            try:
                triples = _try_h2(stmt, env)
            except Exception:
                triples = []
            for ids, g in triples:
                covered.update(ids)
                if g is not None:
                    guards.setdefault(id(stmt), []).append(g)
            _analyze_block(stmt.body.stmts, env.copy(), covered, guards)
            _drop_written_intervals(stmt.body, env)
            env.drop_interval(stmt.name)
        elif isinstance(stmt, A.Let):
            _apply_let(stmt, env)
            # Nested blocks inside the init expr cannot exist
            # (exprs hold no blocks), nothing to recurse into.
        elif isinstance(stmt, A.Assign):
            env.set_interval(stmt.name, _interval(stmt.expr, env))
            env.sized.pop(stmt.name, None)
            if isinstance(stmt.expr, A.Var) and stmt.expr.name in env.sized:
                env.sized[stmt.name] = env.sized[stmt.expr.name]
        else:
            # Any other statement: recurse into nested blocks on
            # copies, then drop intervals of vars it writes.
            for child in _children(stmt):
                if isinstance(child, A.Block):
                    _analyze_block(child.stmts, env.copy(), covered, guards)
            _drop_written_intervals(stmt, env)
    return env


def _apply_let(stmt, env):
    name = stmt.name
    ann = stmt.ann or ""
    t = ann if ann else _derive_type(stmt.expr, env)
    env.types[name] = t
    env.set_interval(name, _interval(stmt.expr, env))
    n = _sized_len(ann)
    if n is not None:
        env.sized[name] = n
    elif isinstance(stmt.expr, A.Var) and stmt.expr.name in env.sized:
        env.sized[name] = env.sized[stmt.expr.name]
    else:
        env.sized.pop(name, None)


def _drop_written_intervals(node, env):
    for n in _walk(node):
        if isinstance(n, (A.Assign, A.Let, A.For)):
            env.drop_interval(n.name)


def _apply_loop_exit(stmt, stmts, pos, env):
    """After a While: drop intervals of vars written in the body,
    then (R4) record the counter interval when the counted-loop
    discipline holds."""
    cond = stmt.cond
    ctr = None
    entry_lit = None
    bound_hi = None
    if isinstance(cond, A.BinOp) and cond.op == "<" \
            and isinstance(cond.left, A.Var):
        ctr = cond.left.name
        _k, w = _nearest_entry(stmts, pos, ctr)
        if w is not None and isinstance(w, (A.Let, A.Assign)) \
                and _is_intlit(w.expr):
            entry_lit = w.expr.value
        # B1-FIX: a stale entry must not feed the R4 post-loop
        # interval (it would poison later H1-D proofs).
        if _k is not None and _entry_stale(stmts, _k, pos, ctr):
            entry_lit = None
        b = cond.right
        if _is_intlit(b):
            bound_hi = b.value
        elif isinstance(b, A.Var):
            _lo, hi = env.interval_of(b.name)
            bound_hi = hi
        # len(a) bound: hi unbounded (None).
    _drop_written_intervals(stmt.body, env)
    if ctr is not None and entry_lit is not None and entry_lit >= 0 \
            and _counter_discipline(stmt.body, ctr, "+"):
        # Bound var must be invariant in the body for max(B, L).
        b = cond.right
        bound_ok = True
        if isinstance(b, A.Var) and _write_sites(stmt.body, b.name):
            bound_ok = False
        if bound_ok:
            hi = None
            if bound_hi is not None:
                hi = max(bound_hi, entry_lit)
            env.set_interval(ctr, (entry_lit, hi))


# ------------------------------------------------------------------
# entry point
# ------------------------------------------------------------------

def analyze_program(program):
    """Returns (covered_ids, guards) for the whole program."""
    covered = set()
    guards = {}
    funcs = list(getattr(program, "funcs", None) or [])
    for impl in (getattr(program, "impls", None) or []):
        funcs.extend(getattr(impl, "methods", None) or [])
    for fn in funcs:
        if getattr(fn, "is_extern", False):
            continue
        body = getattr(fn, "body", None)
        if body is None:
            continue
        try:
            env = _Env()
            for pname, ptype in (getattr(fn, "params", None) or []):
                env.types[pname] = ptype
                n = _sized_len(ptype)
                if n is not None:
                    env.sized[pname] = n
            _analyze_block(body.stmts, env, covered, guards)
        except Exception:
            # Totality: a failure in one function must never break
            # compilation of the rest (its loops simply keep checks).
            continue
    # De-dup guard lists, preserving order.
    for k in guards:
        seen = []
        for g in guards[k]:
            if g not in seen:
                seen.append(g)
        guards[k] = seen
    return covered, guards
