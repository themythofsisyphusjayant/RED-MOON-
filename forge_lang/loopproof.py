"""Fix 1 Phase B — bounds-check hoisting proofs (H1, H2, H1-D) plus
range analysis (R1–R5).

Pure analysis pass over the checked AST. Runs after the checker,
before native codegen (called from Codegen.generate), and annotates
nothing on the AST itself: it returns

    covered: set of id(Index node) proven in-bounds
    guards:  dict id(loop node) -> [guard C strings] (in emit order)
    plain:   set of id(BinOp node) whose checked helper may drop
             (R2 '%' with n > 0 proven; R3 '*' and '+' with the
             product/sum proven in range)
    idx_guards: dict id(Index node) -> guard C string, for
             straight-line R5 uses (the guard rides with the use
             as a statement expression; see DESIGN.md in
             quant/fix1/b2/ for why it is not a separate statement)

Codegen consults only these four results, and only in safe mode with
bounds checks on (the fast emission is reused for covered uses — no
third emission path).

DESIGN.md references: H1 §2 (counted while), H2 §2 (for range),
H1-D §2 (descending while), H1-G (sized arrays, folded into H1),
R1–R5 §2 (range analysis), R4 (post-loop counter interval, used
only to prove H1-D-P3 and, via the singleton _cond_fact extension,
to narrow `if j < nlv` for R5).

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
    """Direct child AST nodes of `node` (via dataclass fields).

    Tuple-valued fields hold pairs: StructLit.fields is
    [(field_name, expr)] and Match.arms is [(pattern, Block)].
    The node element of a pair IS a direct child (the expr / the
    arm Block) — yielding only its children skips it entirely,
    which made the R-scan (and _walk) blind to uses inside struct
    literals (B2: check.fg's `args[0]` in `COut { ..., typ:
    args[0] }` was covered by hosted but invisible to Python).
    """
    if isinstance(node, (list, tuple)):
        for item in node:
            if hasattr(item, "__dataclass_fields__"):
                yield item
            elif isinstance(item, (list, tuple)):
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
        # B2 (§4): relational upper bounds — name -> set of VAR
        # names x such that `name < x` is proven (from loop-counter
        # bounds and R2 mod results). Needed by R3-P2.
        self.rel = {}

    def copy(self):
        e = _Env()
        e.types = dict(self.types)
        e.iv = dict(self.iv)
        e.sized = dict(self.sized)
        e.rel = {k: set(v) for k, v in self.rel.items()}
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

    def rel_of(self, name):
        return self.rel.get(name, set())

    def add_rel(self, name, bound):
        self.rel.setdefault(name, set()).add(bound)

    def drop_rel(self, name):
        self.rel.pop(name, None)


def _interval(node, env):
    """(lo, hi) interval of an int expr, None end = unbounded.
    Literals, vars (env), + - * / % on intervals (B3: / and % are
    magnitude bounds — the analysis never divides), unary -,
    len() >= 0."""
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
    if isinstance(node, A.BinOp) and node.op == "%":
        # B3 (O1-S3): magnitude bound — the analysis never divides,
        # so the hosted mirror can never trap its own compiler on
        # a zero divisor. (a) dividend >= 0, divisor >= 1:
        # (0, dhi-1) if dhi known, else (0, None). (b) divisor
        # excludes 0 and both divisor ends known: (-(M-1), M-1)
        # with M = max(|dlo|, |dhi|).
        alo, ahi = _interval(node.left, env)
        dlo, dhi = _interval(node.right, env)
        if alo is not None and alo >= 0 and dlo is not None and dlo >= 1:
            return (0, None if dhi is None else _cap(dhi - 1))
        if ((dlo is not None and dlo >= 1)
                or (dhi is not None and dhi <= -1)) \
                and dlo is not None and dhi is not None:
            m = max(abs(dlo), abs(dhi))
            return (_cap(-(m - 1)), _cap(m - 1))
        return (None, None)
    if isinstance(node, A.BinOp) and node.op == "/":
        # B3 (O1-S5): |quotient| <= |dividend| when |divisor| >= 1.
        alo, ahi = _interval(node.left, env)
        dlo, dhi = _interval(node.right, env)
        if ((dlo is not None and dlo >= 1)
                or (dhi is not None and dhi <= -1)) \
                and alo is not None and ahi is not None:
            m = max(abs(alo), abs(ahi))
            if alo >= 0:
                return (0, _cap(m))
            if ahi <= 0:
                return (_cap(-m), 0)
            return (_cap(-m), _cap(m))
        return (None, None)
    if _is_len_call(node):
        return (0, None)
    return (None, None)


def _is_len_call(node):
    if isinstance(node, A.Call) and node.name == "len" and len(node.args) == 1:
        return True
    if isinstance(node, A.MethodCall) and node.method == "len" and not node.args:
        return True
    return False


# B2: condition facts for If-arm narrowing (mirrors codegen.py
# _cond_fact, extended to var-vs-var where the other side has a
# singleton interval — DESIGN.md §4.3, needed by R4's consumer:
# `if j2 < nlv` with nlv let-bound to 64 narrows j2 to [0, 63]).
# Returns (var, lo, hi) proven when `cond` holds (truth=True) or
# fails (truth=False), or None. Only <, <=, >, >=, == comparisons.
def _cond_fact_lp(cond, env, truth):
    if not isinstance(cond, A.BinOp):
        return None
    if cond.op not in ("<", "<=", ">", ">=", "=="):
        return None
    left, right, op = cond.left, cond.right, cond.op
    lit = None
    if isinstance(left, A.IntLit) and isinstance(right, A.Var):
        left, right = right, left
        op = {"<": ">", "<=": ">=", ">": "<", ">=": "<=", "==": "=="}[op]
        lit = right.value if isinstance(right, A.IntLit) else None
    if isinstance(left, A.Var) and isinstance(right, A.IntLit):
        lit = right.value
    elif isinstance(left, A.Var) and isinstance(right, A.Var):
        # Singleton var-vs-var: the other side's interval must be a
        # single value; that value plays the literal's role.
        _lo, _hi = env.interval_of(right.name)
        if _lo is not None and _lo == _hi:
            lit = _lo
        else:
            # The narrowed var may be on the right instead.
            _lo2, _hi2 = env.interval_of(left.name)
            if _lo2 is not None and _lo2 == _hi2:
                left, right = right, left
                op = {"<": ">", "<=": ">=", ">": "<", ">=": "<=",
                      "==": "=="}[op]
                lit = _lo2
            else:
                return None
    else:
        return None
    if lit is None or not isinstance(left, A.Var):
        return None
    # Only int vars are narrowed (a well-typed `<` against an int
    # literal implies int; a known non-int type must not be narrowed).
    t = env.type_of(left.name)
    if t and t != "int":
        return None
    if not truth:
        if op == "==":
            return None
        op = {"<": ">=", "<=": ">", ">": "<=", ">=": "<"}[op]
    table = {"<": (None, lit - 1), "<=": (None, lit),
             ">": (lit + 1, None), ">=": (lit, None),
             "==": (lit, lit)}
    lo, hi = table[op]
    return (left.name, lo, hi)


def _narrow_env(env, var, lo, hi):
    """Intersect env's interval for `var` with (lo, hi) in place
    (None end = unbounded). Mirrors codegen._narrow's clamping, but
    the analysis keeps None ends (no INT_MIN/INT_MAX clamp: the
    analysis cap is 2^40, applied by _cap at interval build time)."""
    old_lo, old_hi = env.interval_of(var)
    nlo = old_lo if lo is None else (lo if old_lo is None else max(old_lo, lo))
    nhi = old_hi if hi is None else (hi if old_hi is None else min(old_hi, hi))
    if nlo is not None and nhi is not None and nlo > nhi:
        env.drop_interval(var)
        env.drop_rel(var)
        return
    nlo = _cap(nlo)
    nhi = _cap(nhi)
    if nlo is None and nhi is None:
        env.drop_interval(var)
    else:
        env.set_interval(var, (nlo, nhi))


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


def _loop_counter_facts(stmt, stmts, pos, env):
    """B2: the loop-counter interval (+ relational bound, if any)
    that holds at every use inside the body of a counted loop:
    (counter, interval, rel_bound_or_None), or None when the loop
    has no counted shape. H1: [L, B_hi-1] with rel {B} for a var
    bound; H1-D: [L_lo+1, hi_E]; H2: [s, e_hi-1] with rel {bound}.
    The interval is the LOOP-TOP value (the increment/decrement is
    the last statement, so every use sees it). Requires the same
    entry + discipline preconditions as H1/H1-D/H2 — a loop that
    fails them contributes no fact (its counter stays unknown)."""
    if isinstance(stmt, A.While):
        body = stmt.body
        cond = stmt.cond
        if not (isinstance(cond, A.BinOp)
                and isinstance(cond.left, A.Var)):
            return None
        ctr = cond.left.name
        if cond.op == "<":
            _k, w = _nearest_entry(stmts, pos, ctr)
            if w is None or not isinstance(w, (A.Let, A.Assign)):
                return None
            if _entry_stale(stmts, _k, pos, ctr):
                return None
            if not _is_intlit(w.expr) or w.expr.value < 0:
                return None
            if not _counter_discipline(body, ctr, "+"):
                return None
            entry_lit = w.expr.value
            b = cond.right
            if _is_intlit(b):
                return (ctr, (entry_lit, b.value - 1), None)
            if isinstance(b, A.Var):
                if _write_sites(body, b.name):
                    return None
                _lo, hi = env.interval_of(b.name)
                return (ctr, (entry_lit, None if hi is None else hi - 1),
                        b.name)
            return None
        if cond.op == ">":
            lexpr = cond.right
            if _is_intlit(lexpr):
                if lexpr.value < 0:
                    return None
                l_lo = lexpr.value
            elif isinstance(lexpr, A.Var):
                lo, _hi = env.interval_of(lexpr.name)
                if lo is None or lo < 0:
                    return None
                if _write_sites(body, lexpr.name):
                    return None
                l_lo = lo
            else:
                return None
            _k, w = _nearest_entry(stmts, pos, ctr)
            if w is None or not isinstance(w, (A.Let, A.Assign)):
                return None
            if _entry_stale(stmts, _k, pos, ctr):
                return None
            elo, ehi = _interval(w.expr, env)
            if ehi is None:
                return None
            if ehi <= l_lo:
                return None  # never runs; no body fact
            if not _counter_discipline(body, ctr, "-"):
                return None
            return (ctr, (l_lo + 1, ehi), None)
        return None
    if isinstance(stmt, A.For):
        ctr = stmt.name
        it = stmt.expr
        if isinstance(it, A.Call) and it.name == "range" \
                and len(it.args) == 1:
            arg = it.args[0]
            if _is_intlit(arg):
                return (ctr, (0, arg.value - 1), None)
            if isinstance(arg, A.Var):
                _lo, hi = env.interval_of(arg.name)
                if _write_sites(stmt.body, arg.name):
                    return None
                return (ctr, (0, None if hi is None else hi - 1),
                        arg.name)
            if isinstance(arg, (A.Call, A.MethodCall)):
                return (ctr, (0, None), None)
            return None
        if isinstance(it, A.RangeLit):
            if not _is_intlit(it.start) or it.start.value < 0:
                return None
            e = it.end
            if _is_intlit(e):
                return (ctr, (it.start.value, e.value - 1), None)
            if isinstance(e, A.Var):
                _lo, hi = env.interval_of(e.name)
                if _write_sites(stmt.body, e.name):
                    return None
                return (ctr, (it.start.value,
                              None if hi is None else hi - 1), e.name)
            if isinstance(e, (A.Call, A.MethodCall)):
                return (ctr, (it.start.value, None), None)
            return None
        return None
    return None


def _body_env(stmt, stmts, pos, env):
    """B2: the environment at the top of a loop body for the R-scan.
    The outer env with intervals + rel-facts DROPPED for every var
    written anywhere in the body subtree (their values vary across
    iterations), then the counted-loop facts applied. A For loop's
    own variable is dropped first (it is rebound every iteration)
    and only re-established by a counted shape. Types and sized
    lengths are kept (they do not vary)."""
    benv = env.copy()
    for name in {n.name for n in _walk(stmt.body)
                 if isinstance(n, (A.Assign, A.Let, A.For))}:
        benv.drop_interval(name)
        benv.drop_rel(name)
    if isinstance(stmt, A.For):
        benv.drop_interval(stmt.name)
        benv.drop_rel(stmt.name)
    facts = _loop_counter_facts(stmt, stmts, pos, env)
    if facts is not None:
        ctr, iv, relb = facts
        benv.set_interval(ctr, iv)
        if relb is not None:
            benv.add_rel(ctr, relb)
    # B3 (O1-S2): ring-reset facts — idx in [0, w_hi-1] when w_hi
    # is known, INTERSECTED with any interval idx already has in
    # the body env (a counter fact and a ring fact cannot co-occur
    # — _counter_discipline fails when a reset follows the
    # increment — but neither fact may ever widen the other).
    for idx, w_hi, _wc, _pi, _pr in \
            _ring_candidates(stmt, stmts, pos, env):
        if w_hi is None:
            continue
        _lo, _hi = benv.interval_of(idx)
        nlo = 0 if _lo is None else max(_lo, 0)
        nhi = w_hi - 1 if _hi is None else min(_hi, w_hi - 1)
        if nhi < nlo:
            continue
        benv.set_interval(idx, (nlo, nhi))
    return benv


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


def _mod_fact(expr, env):
    """B2 (R3-P2(b)): (rel_bound, interval) for `x % n` assigned to
    a var, when x >= 0 and n > 0 are proven; else None. The
    interval is [0, n_hi-1] (n's upper end, if known)."""
    if not (isinstance(expr, A.BinOp) and expr.op == "%"
            and isinstance(expr.left, A.Var)
            and isinstance(expr.right, A.Var)):
        return None
    xlo, _xhi = env.interval_of(expr.left.name)
    nlo, nhi = env.interval_of(expr.right.name)
    if xlo is None or xlo < 0 or nlo is None or nlo <= 0:
        return None
    iv = None if nhi is None else (0, nhi - 1)
    return (expr.right.name, iv)


def _has_continue(node):
    """B2 (R1): True when `node` holds a `continue` that targets
    the enclosing loop — i.e. a Continue NOT nested inside an inner
    While/For (whose continue targets that inner loop)."""
    if isinstance(node, A.Continue):
        return True
    if isinstance(node, (A.While, A.For)):
        return False
    for c in _children(node):
        if _has_continue(c):
            return True
    return False


def _ring_candidates(stmt, stmts, pos, env):
    """B3 (O1-S2): per ring var (idx, w_hi, wcode, p_inc, p_reset)
    for the ring-reset idiom in `stmt`'s body — same preconditions
    as _try_r1 (R1-P2/P3/P4): exactly one `idx = idx + 1`
    increment, exactly one reset If (== / >= w, no else,
    then-branch exactly one `idx = c` IntLit), w >= 1 and
    invariant, entry literal, no `continue` between increment and
    reset. w_hi is w's interval upper end when known (literal w:
    the literal; var w: env hi), else None; wcode is w's C
    rendering for the guard. _try_r1 and _body_env both consume
    this (the latter for the O1-S2 loop-top ring fact)."""
    body = stmt.body
    incs = {}
    for p, s in enumerate(body.stmts):
        if isinstance(s, A.Assign) and isinstance(s.expr, A.BinOp) \
                and s.expr.op == "+" and _is_var(s.expr.left, s.name) \
                and _is_intlit(s.expr.right, 1):
            incs.setdefault(s.name, []).append(p)
    out = []
    for idx, plist in incs.items():
        if len(plist) != 1:
            continue
        p_inc = plist[0]
        resets = []
        for q, s in enumerate(body.stmts):
            if q <= p_inc or not isinstance(s, A.If):
                continue
            if s.els is not None:
                continue
            cond = s.cond
            if not (isinstance(cond, A.BinOp)
                    and cond.op in ("==", ">=")
                    and _is_var(cond.left, idx)):
                continue
            wnode = cond.right
            if not (isinstance(wnode, A.Var) or _is_intlit(wnode)):
                continue
            if len(s.then.stmts) != 1:
                continue
            rs = s.then.stmts[0]
            if not (isinstance(rs, A.Assign) and rs.name == idx
                    and _is_intlit(rs.expr)):
                continue
            resets.append((q, wnode, rs.expr.value))
        if len(resets) != 1:
            continue
        p_reset, wnode, cval = resets[0]
        # R1-P4: the only writes to idx are the increment and the
        # reset's own assignment.
        if len(_write_sites(body, idx)) != 2:
            continue
        # R1-P2: w invariant and >= 1.
        if isinstance(wnode, A.Var):
            if _write_sites(body, wnode.name):
                continue
            wlo, whi = env.interval_of(wnode.name)
            if wlo is None or wlo < 1:
                continue
            w_hi = whi
            wcode = wnode.name
        else:
            if wnode.value < 1:
                continue
            w_hi = wnode.value
            wcode = str(wnode.value)
        # R1-P3: entry literal.
        _k, w = _nearest_entry(stmts, pos, idx)
        if w is None or not isinstance(w, (A.Let, A.Assign)):
            continue
        if _entry_stale(stmts, _k, pos, idx):
            continue
        if not _is_intlit(w.expr) or w.expr.value < 0:
            continue
        entry_lit = w.expr.value
        if isinstance(wnode, A.Var):
            if entry_lit != 0 or cval != 0:
                continue
        else:
            if entry_lit >= wnode.value or cval < 0 \
                    or cval >= wnode.value:
                continue
        # B2 soundness (DESIGN.md gap): no `continue` between the
        # increment and the reset — it would skip the reset and the
        # next iteration could start with idx == w.
        if any(_has_continue(s)
               for s in body.stmts[p_inc + 1:p_reset]):
            continue
        out.append((idx, w_hi, wcode, p_inc, p_reset))
    return out


def _try_r1(stmt, stmts, pos, env):
    """B2 R1 — ring-buffer reset idiom. Returns a list of
    (covered_ids, guard) triples for the enclosing loop `stmt`
    (While or For). The guard attaches to `stmt` itself.
    Recognition lives in _ring_candidates (B3); this keeps only
    the array/coverage work."""
    body = stmt.body
    triples = []
    for idx, _w_hi, wcode, p_inc, p_reset in \
            _ring_candidates(stmt, stmts, pos, env):
        for arr in _candidate_arrays(body, idx):
            if not _is_array_type(env.type_of(arr)):
                continue
            if not _array_ok(body, arr):
                continue
            ids = []
            for sp, s in enumerate(body.stmts):
                if sp < p_inc or sp > p_reset:
                    uses = _collect_uses(
                        s, arr, lambda ix: _is_var(ix, idx))
                    ids.extend(id(u) for u in uses)
            if ids:
                guard = f"if ({wcode} > ({arr}).len) {FAIL_MSG};"
                triples.append((ids, guard))
    return triples


def _loop_ctx(loops, arr, env):
    """Innermost enclosing loop for an R-use on array `arr`:
    (loop node, body) when the array is a plain local of array type
    with no reassign/shadow/move/push/spawn in that loop's body,
    else None."""
    if not loops:
        return None
    loop = loops[-1]
    body = loop.body
    if not _is_array_type(env.type_of(arr)):
        return None
    if not _array_ok(body, arr):
        return None
    return (loop, body)


def _try_r2(ix, env, loops, covered, guards, plain, idx_guards):
    """B2 R2 — `a[i % n]`. Records coverage + loop guard + the `%`
    in `plain`; returns True when proven."""
    if id(ix) in covered or not isinstance(ix.base, A.Var):
        return False
    arr = ix.base.name
    idx = ix.index
    if not (isinstance(idx, A.BinOp) and idx.op == "%"
            and isinstance(idx.left, A.Var)):
        return False
    i_name = idx.left.name
    nnode = idx.right
    if isinstance(nnode, A.IntLit):
        if nnode.value <= 0:
            return False
        ncode = str(nnode.value)
    elif isinstance(nnode, A.Var):
        nlo, _nhi = env.interval_of(nnode.name)
        if nlo is None or nlo <= 0:
            return False
        ncode = nnode.name
    else:
        return False
    ilo, _ihi = env.interval_of(i_name)
    if ilo is None or ilo < 0:
        return False
    ctx = _loop_ctx(loops, arr, env)
    if ctx is None:
        return False
    loop, body = ctx
    if isinstance(nnode, A.Var) and _write_sites(body, nnode.name):
        return False
    covered.add(id(ix))
    guards.setdefault(id(loop), []).append(
        f"if ({ncode} > ({arr}).len) {FAIL_MSG};")
    plain.add(id(idx))
    return True


def _lt_n(var, nnode, env):
    """B2 (R3-P2): True when `var` is proven < n. For a literal n,
    the var's absolute interval must lie in [0, n). For a var n,
    either a relational fact (var < n) or n's singleton interval
    playing the literal's role."""
    if isinstance(nnode, A.IntLit):
        lo, hi = env.interval_of(var)
        return (lo is not None and lo >= 0 and hi is not None
                and hi < nnode.value)
    if nnode.name in env.rel_of(var):
        return True
    nlo, nhi = env.interval_of(nnode.name)
    if nlo is not None and nlo == nhi:
        lo, hi = env.interval_of(var)
        return (lo is not None and lo >= 0 and hi is not None
                and hi < nlo)
    return False


def _try_r3(ix, env, loops, covered, guards, plain, idx_guards):
    """B2 R3 — `a[i*n+k]` (and the `k+i*n` / `n*i` orders).
    Records coverage + loop guard + the `*` and `+` in `plain`."""
    if id(ix) in covered or not isinstance(ix.base, A.Var):
        return False
    arr = ix.base.name
    idx = ix.index
    if not (isinstance(idx, A.BinOp) and idx.op == "+"):
        return False
    mul = None
    kname = None
    for side_a, side_b in ((idx.left, idx.right),
                           (idx.right, idx.left)):
        if (isinstance(side_a, A.BinOp) and side_a.op == "*"
                and isinstance(side_b, A.Var)):
            mul, kname = side_a, side_b.name
            break
    if mul is None:
        return False
    iname = None
    nnode = None
    for side_a, side_b in ((mul.left, mul.right),
                           (mul.right, mul.left)):
        if isinstance(side_a, A.Var) and (isinstance(side_b, A.Var)
                                          or _is_intlit(side_b)):
            iname, nnode = side_a.name, side_b
            break
    if iname is None:
        return False
    # R3-P3: n in [lo, hi], 1 <= lo, hi*hi <= INT_MAX.
    if isinstance(nnode, A.IntLit):
        nlo = nhi = nnode.value
    else:
        nlo, nhi = env.interval_of(nnode.name)
    if nlo is None or nlo < 1 or nhi is None:
        return False
    if nhi * nhi > 2 ** 63 - 1:
        return False
    if not _lt_n(iname, nnode, env):
        return False
    if not _lt_n(kname, nnode, env):
        return False
    ctx = _loop_ctx(loops, arr, env)
    if ctx is None:
        return False
    loop, body = ctx
    if isinstance(nnode, A.Var) and _write_sites(body, nnode.name):
        return False
    ncode = _c_expr(nnode)
    if ncode is None:
        return False
    covered.add(id(ix))
    guards.setdefault(id(loop), []).append(
        f"if ({ncode} * {ncode} > ({arr}).len) {FAIL_MSG};")
    plain.add(id(mul))
    plain.add(id(idx))
    return True


def _try_r5(ix, env, loops, covered, guards, plain, idx_guards):
    """B2 R5 — `a[e]` with a proven absolute interval [lo, hi],
    lo >= 0. In a loop the guard goes before the innermost loop;
    straight-line it rides with the use (idx_guards)."""
    if id(ix) in covered or not isinstance(ix.base, A.Var):
        return False
    arr = ix.base.name
    lo, hi = _interval(ix.index, env)
    if lo is None or hi is None or lo < 0:
        return False
    if not _is_array_type(env.type_of(arr)):
        return False
    guard = f"if ({hi} >= ({arr}).len) {FAIL_MSG};"
    if loops:
        loop, body = loops[-1], loops[-1].body
        if not _array_ok(body, arr):
            return False
        covered.add(id(ix))
        guards.setdefault(id(loop), []).append(guard)
    else:
        covered.add(id(ix))
        idx_guards[id(ix)] = guard
    return True


INT64_MIN = -(2 ** 63)
INT64_MAX = 2 ** 63 - 1


def _reset_fact(stmt, env):
    """B3 (O1-S2b): post-reset union interval for an If with no
    else whose cond is `idx == w` / `idx >= w` (Var vs Var/IntLit)
    and whose then-branch is exactly one `idx = c` (IntLit).
    Returns (idx, (lo, hi)) — the union of [c, c] with idx's
    pre-If interval — or None. Sound with no R1 proof needed:
    after the If, idx is either c (then taken) or its pre-If
    value."""
    if not isinstance(stmt, A.If) or stmt.els is not None:
        return None
    cond = stmt.cond
    if not (isinstance(cond, A.BinOp) and cond.op in ("==", ">=")
            and _is_var(cond.left)):
        return None
    idx = cond.left.name
    if not (isinstance(cond.right, A.Var) or _is_intlit(cond.right)):
        return None
    if len(stmt.then.stmts) != 1:
        return None
    rs = stmt.then.stmts[0]
    if not (isinstance(rs, A.Assign) and rs.name == idx
            and _is_intlit(rs.expr)):
        return None
    c = rs.expr.value
    pre_lo, pre_hi = env.interval_of(idx)
    if pre_lo is None or pre_hi is None:
        return None
    return (idx, (min(c, pre_lo), max(c, pre_hi)))


def _o1_plain(node, env):
    """B3 (O1): True when a BinOp/UnaryOp's checked helper can be
    dropped — the interval proof shows the operation cannot
    overflow (and, for / %, cannot divide by zero or hit
    INT_MIN / -1). Mirrors codegen._binop_safe on the analysis's
    (loop-aware) intervals."""
    if isinstance(node, A.UnaryOp) and node.op == "-":
        lo, _hi = _interval(node.expr, env)
        # A known lo is >= -2**40 > INT_MIN, so -x cannot overflow.
        return lo is not None
    if not (isinstance(node, A.BinOp)
            and node.op in ("+", "-", "*", "/", "%")):
        return False
    # Type gate (defense in depth): a KNOWN non-int operand type
    # disqualifies the node. Float involvement already yields an
    # unknown interval, except a float Var let-bound from an int
    # literal — the gate catches that case. Codegen independently
    # gates the plain path on int operand types.
    for side in (node.left, node.right):
        if isinstance(side, A.Var):
            t = env.type_of(side.name)
            if t and t != "int":
                return False
    if node.op in ("+", "-", "*"):
        lo, hi = _interval(node, env)
        return (lo is not None and hi is not None
                and lo >= INT64_MIN and hi <= INT64_MAX)
    # / and %: divisor excludes 0, and not (dividend possibly
    # INT_MIN and divisor contains -1).
    dlo, dhi = _interval(node.right, env)
    if not ((dlo is not None and dlo >= 1)
            or (dhi is not None and dhi <= -1)):
        return False
    alo, _ahi = _interval(node.left, env)
    contains_neg1 = (dlo is None or dlo <= -1) \
        and (dhi is None or dhi >= -1)
    if alo is None and contains_neg1:
        return False
    return True


def _scan_o1_uses(node, env, plain):
    """B3: scan a statement's OWN expressions for O1 plain
    BinOp/UnaryOp nodes with the current env. Same traversal
    discipline as _scan_r_uses (stop at Block/While/For; If conds
    scanned; FieldAccess-base Index: scan index/base only), plus
    SKIP Defer/Spawn subtrees entirely — a deferred call's args
    are re-evaluated at block exit (codegen.py:3559-3564) and a
    spawned call runs in another thread, so the current env is
    not valid for either."""
    if isinstance(node, (list, tuple)):
        for item in node:
            _scan_o1_uses(item, env, plain)
        return
    if not hasattr(node, "__dataclass_fields__"):
        return
    if isinstance(node, (A.Block, A.While, A.For, A.Defer, A.Spawn)):
        return
    if isinstance(node, A.FieldAccess) and isinstance(node.base, A.Index):
        _scan_o1_uses(node.base.index, env, plain)
        _scan_o1_uses(node.base.base, env, plain)
        return
    if isinstance(node, (A.BinOp, A.UnaryOp)):
        if _o1_plain(node, env):
            plain.add(id(node))
    for c in _children(node):
        _scan_o1_uses(c, env, plain)


def _scan_r_uses(node, env, loops, covered, guards, plain, idx_guards):
    """B2: scan a statement's OWN expressions for R2/R3/R5 uses
    with the current env. Does not descend into Block subtrees
    (analysed separately, with narrowed / loop-body envs) or
    While/For subtrees (their bodies are analysed as statements;
    their conds are not scanned — a cond is evaluated every
    iteration, so the outer env is not valid there). An If cond IS
    scanned (evaluated once, current env valid). FieldAccess-base
    Indexes are never uses, but their index/base exprs are scanned
    for nested uses. R2 is tried before R3 before R5: R5's interval
    could also cover an R2/R3 index, but only R2/R3 drop the
    arithmetic's checked helpers."""
    if isinstance(node, (list, tuple)):
        for item in node:
            _scan_r_uses(item, env, loops, covered, guards, plain,
                         idx_guards)
        return
    if not hasattr(node, "__dataclass_fields__"):
        return
    if isinstance(node, (A.Block, A.While, A.For)):
        return
    if isinstance(node, A.FieldAccess) and isinstance(node.base, A.Index):
        _scan_r_uses(node.base.index, env, loops, covered, guards,
                     plain, idx_guards)
        _scan_r_uses(node.base.base, env, loops, covered, guards,
                     plain, idx_guards)
        return
    if isinstance(node, A.Index):
        if isinstance(node.base, A.Var):
            if not _try_r2(node, env, loops, covered, guards, plain,
                           idx_guards):
                if not _try_r3(node, env, loops, covered, guards,
                               plain, idx_guards):
                    _try_r5(node, env, loops, covered, guards, plain,
                            idx_guards)
        for c in _children(node):
            _scan_r_uses(c, env, loops, covered, guards, plain,
                         idx_guards)
        return
    for c in _children(node):
        _scan_r_uses(c, env, loops, covered, guards, plain, idx_guards)


# ------------------------------------------------------------------
# block analysis (sequential env threading)
# ------------------------------------------------------------------

def _analyze_block(stmts, env, covered, guards, plain, idx_guards,
                   loops=None):
    """Analyze stmts in order, threading `env` (mutated in place
    for this block's own copy). Nested blocks are analyzed on
    copies; their lets never leak out. `loops` is the stack of
    enclosing loop nodes (innermost last) for the R-scan's guard
    placement. B2: each statement's own expressions are scanned
    for R2/R3/R5 uses with the env at that point (before the
    statement's own env update); loop bodies are entered on the
    loop-body env (body-written intervals dropped, counted-loop
    facts applied); If arms are entered with the condition's facts
    (extended _cond_fact, singleton var-vs-var included)."""
    if loops is None:
        loops = []
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
            # B2 R1 (independent shape — a loop can be H1 and R1).
            try:
                for ids, g in _try_r1(stmt, stmts, pos, env):
                    covered.update(ids)
                    if g is not None:
                        guards.setdefault(id(stmt), []).append(g)
            except Exception:
                pass
            # Recurse into the body on the loop-body env.
            benv = _body_env(stmt, stmts, pos, env)
            _analyze_block(stmt.body.stmts, benv, covered, guards,
                           plain, idx_guards, loops + [stmt])
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
            try:
                for ids, g in _try_r1(stmt, stmts, pos, env):
                    covered.update(ids)
                    if g is not None:
                        guards.setdefault(id(stmt), []).append(g)
            except Exception:
                pass
            benv = _body_env(stmt, stmts, pos, env)
            _analyze_block(stmt.body.stmts, benv, covered, guards,
                           plain, idx_guards, loops + [stmt])
            _drop_written_intervals(stmt.body, env)
            env.drop_interval(stmt.name)
            env.drop_rel(stmt.name)
        elif isinstance(stmt, A.If):
            # B2: scan the condition (evaluated once, current env),
            # then analyse each arm with the condition's facts.
            try:
                _scan_r_uses(stmt.cond, env, loops, covered, guards,
                             plain, idx_guards)
            except Exception:
                pass
            # B3: same site for the O1 scan.
            try:
                _scan_o1_uses(stmt.cond, env, plain)
            except Exception:
                pass
            # B3 (O1-S2b): post-reset union fact, read on the
            # pre-If env; applied after the arms drop idx's
            # interval.
            try:
                reset = _reset_fact(stmt, env)
            except Exception:
                reset = None
            then_env = env.copy()
            fact = _cond_fact_lp(stmt.cond, env, True)
            if fact is not None:
                _narrow_env(then_env, fact[0], fact[1], fact[2])
            _analyze_block(stmt.then.stmts, then_env, covered, guards,
                           plain, idx_guards, loops)
            if stmt.els is not None:
                else_env = env.copy()
                fact = _cond_fact_lp(stmt.cond, env, False)
                if fact is not None:
                    _narrow_env(else_env, fact[0], fact[1], fact[2])
                _analyze_block(stmt.els.stmts, else_env, covered,
                               guards, plain, idx_guards, loops)
            _drop_written_intervals(stmt, env)
            if reset is not None:
                env.set_interval(reset[0], reset[1])
        elif isinstance(stmt, A.Let):
            try:
                _scan_r_uses(stmt, env, loops, covered, guards, plain,
                             idx_guards)
            except Exception:
                pass
            try:
                _scan_o1_uses(stmt, env, plain)
            except Exception:
                pass
            _apply_let(stmt, env)
            # Nested blocks inside the init expr cannot exist
            # (exprs hold no blocks), nothing to recurse into.
        elif isinstance(stmt, A.Assign):
            try:
                _scan_r_uses(stmt, env, loops, covered, guards, plain,
                             idx_guards)
            except Exception:
                pass
            try:
                _scan_o1_uses(stmt, env, plain)
            except Exception:
                pass
            rhs_iv = _interval(stmt.expr, env)
            mf = _mod_fact(stmt.expr, env)
            env.set_interval(stmt.name, rhs_iv)
            env.drop_rel(stmt.name)
            if mf is not None:
                env.add_rel(stmt.name, mf[0])
                if mf[1] is not None:
                    env.set_interval(stmt.name, mf[1])
            env.sized.pop(stmt.name, None)
            if isinstance(stmt.expr, A.Var) and stmt.expr.name in env.sized:
                env.sized[stmt.name] = env.sized[stmt.expr.name]
        else:
            # Any other statement: scan its own expressions, recurse
            # into nested blocks on copies, then drop intervals of
            # vars it writes.
            try:
                _scan_r_uses(stmt, env, loops, covered, guards, plain,
                             idx_guards)
            except Exception:
                pass
            try:
                _scan_o1_uses(stmt, env, plain)
            except Exception:
                pass
            for child in _children(stmt):
                if isinstance(child, A.Block):
                    _analyze_block(child.stmts, env.copy(), covered,
                                   guards, plain, idx_guards, loops)
            _drop_written_intervals(stmt, env)
    return env


def _apply_let(stmt, env):
    name = stmt.name
    ann = stmt.ann or ""
    t = ann if ann else _derive_type(stmt.expr, env)
    env.types[name] = t
    iv = _interval(stmt.expr, env)
    mf = _mod_fact(stmt.expr, env)
    env.set_interval(name, iv)
    env.drop_rel(name)
    if mf is not None:
        env.add_rel(name, mf[0])
        if mf[1] is not None:
            env.set_interval(name, mf[1])
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
            env.drop_rel(n.name)


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
    # B2: H1-D post-loop interval [min(E_lo, L_lo), max(E_hi, L_hi)].
    # Normal exit: k == L; break exit: k in (L, E_hi]; never ran:
    # k in [E_lo, E_hi]. (L's interval is read after the drop above,
    # so an L written in the body yields no fact, as required.)
    if isinstance(cond, A.BinOp) and cond.op == ">" \
            and isinstance(cond.left, A.Var):
        ctr2 = cond.left.name
        lexpr = cond.right
        if _is_intlit(lexpr):
            l_lo = l_hi = lexpr.value
        elif isinstance(lexpr, A.Var):
            l_lo, l_hi = env.interval_of(lexpr.name)
        else:
            l_lo = l_hi = None
        if l_lo is not None and l_hi is not None \
                and _counter_discipline(stmt.body, ctr2, "-"):
            _k2, w2 = _nearest_entry(stmts, pos, ctr2)
            elo = ehi = None
            if w2 is not None and isinstance(w2, (A.Let, A.Assign)) \
                    and not _entry_stale(stmts, _k2, pos, ctr2):
                elo, ehi = _interval(w2.expr, env)
            if elo is not None and ehi is not None:
                env.set_interval(
                    ctr2, (min(elo, l_lo), max(ehi, l_hi)))


# ------------------------------------------------------------------
# entry point
# ------------------------------------------------------------------

def analyze_program(program):
    """Returns (covered_ids, guards, plain_ids, idx_guards) for the
    whole program."""
    covered = set()
    guards = {}
    plain = set()
    idx_guards = {}
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
            _analyze_block(body.stmts, env, covered, guards, plain,
                           idx_guards)
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
    return covered, guards, plain, idx_guards
