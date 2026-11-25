from dataclasses import dataclass


@dataclass
class Program:
    imports: list  # [path string]
    funcs: list
    structs: list = None  # [StructDef]; None for old call sites
    enums: list = None  # [EnumDef]
    traits: list = None  # [TraitDef]
    impls: list = None  # [ImplDef]
    aliases: list = None  # [AliasDef]
    newtypes: list = None  # [NewtypeDef]


@dataclass
class StructDef:
    name: str
    fields: list  # [(name, type)]
    line: int
    col: int
    type_params: list = None  # [param name] for generic structs


@dataclass
class EnumDef:
    name: str
    variants: list  # [variant name]
    line: int
    col: int
    type_params: list = None
    variant_payloads: dict = None  # variant -> payload type or None


@dataclass
class FuncDef:
    name: str
    params: list
    ret: str
    body: object
    line: int
    col: int
    is_extern: bool = False
    type_params: list = None  # [param name] for generic functions
    # Source file this function was defined in, stamped
    # by compiler.load_program ("" for compile_source,
    # which has no file). Powers --debug #line output.
    file: str = ""


@dataclass
class Pattern:
    """One match-arm pattern (Top-500 #69: value patterns).

    kind: "variant" (enum variant or union member name), "lit_int",
    "lit_bool", "lit_str", "struct", "wildcard", "binding" (a
    struct-field binding, field patterns only). value: the int for
    lit_int, the bool for lit_bool, the string for lit_str, the
    struct name for struct, the member name for variant, the
    binding name for binding, "" for wildcard. fields: for kind
    "struct", the (field_name, Pattern) list in written order.
    binding: the payload binding for variant patterns, ""
    otherwise.
    """
    kind: str
    value: object = None
    fields: list = None
    binding: str = None  # payload binding for variant patterns, None when absent
    line: int = 0
    col: int = 0


@dataclass
class Match:
    expr: object
    arms: list  # [(Pattern, Block)]; pattern is a Pattern node (#69)
    line: int
    col: int


def pattern_text(pat):
    """Render a Pattern for error messages and fmt (Top-500 #69)."""
    if pat.kind == "lit_int":
        return str(pat.value)
    if pat.kind == "lit_bool":
        return "true" if pat.value else "false"
    if pat.kind == "lit_str":
        return f'"{pat.value}"'
    if pat.kind == "struct":
        inner = ", ".join(f"{fn}: {pattern_text(fp)}" for fn, fp in (pat.fields or []))
        return f"{pat.value} {{ {inner} }}"
    if pat.kind == "binding":
        return str(pat.value)
    if pat.kind == "wildcard":
        return "_"
    return str(pat.value or "")


@dataclass
class Spawn:
    call: object  # Call node
    line: int
    col: int


@dataclass
class Scope:
    body: object  # Block node: tasks spawned inside are joined at its end
    line: int
    col: int


@dataclass
class Try:
    expr: object
    line: int
    col: int
    kind: str = None  # "Option" or "Result", set by checker
    value_type: str = None
    ret_type: str = None
    error_type: str = None


@dataclass
class Block:
    stmts: list


@dataclass
class Let:
    name: str
    mutable: bool
    ann: object
    expr: object
    line: int
    col: int
    # Top-500 #494: True when the checker proved this let rebinds
    # a name already declared in the same scope (same-type only
    # in v1); codegen then lowers it to the Assign path instead
    # of emitting a second C declaration.
    rebind: bool = False


@dataclass
class Assign:
    name: str
    expr: object
    line: int
    col: int


@dataclass
class IndexAssign:
    base: object  # Index node whose base is a Var, a field, or another index
    expr: object
    line: int
    col: int


@dataclass
class If:
    cond: object
    then: object
    els: object
    line: int
    col: int


@dataclass
class While:
    cond: object
    body: object
    line: int
    col: int
    label: object = None


@dataclass
class For:
    name: str
    expr: object
    body: object
    line: int
    col: int
    label: object = None


@dataclass
class Break:
    line: int
    col: int
    label: object = None


@dataclass
class Continue:
    line: int
    col: int
    label: object = None


@dataclass
class TraitDef:
    name: str
    methods: list  # [(name, params, ret, line, col)]; signatures only
    line: int
    col: int


@dataclass
class ImplDef:
    trait: object  # trait name, or None for an inherent impl
    struct: str
    methods: list  # [FuncDef], each with the receiver as first param
    line: int
    col: int


@dataclass
class AliasDef:
    name: str
    target: str  # a type spelling, e.g. "int", "[int]", "Stack<int>"
    line: int
    col: int


@dataclass
class NewtypeDef:
    name: str
    target: str  # the underlying type; the newtype is DISTINCT from it
    line: int
    col: int


@dataclass
class Return:
    expr: object
    line: int
    col: int


@dataclass
class ExprStmt:
    expr: object
    line: int
    col: int


@dataclass
class IntLit:
    value: int
    line: int
    col: int


@dataclass
class FloatLit:
    value: float
    line: int
    col: int


@dataclass
class StrLit:
    value: str
    line: int
    col: int


@dataclass
class BoolLit:
    value: bool
    line: int
    col: int


@dataclass
class ArrayLit:
    elems: list
    line: int
    col: int


@dataclass
class TupleLit:
    elems: list
    line: int
    col: int


@dataclass
class StructLit:
    name: str
    fields: list  # [(field_name, expr)]
    line: int
    col: int
    concrete_type: str = None  # set by checker: base name or "Base<args>"


@dataclass
class FieldAccess:
    base: object
    field: str
    line: int
    col: int


@dataclass
class MethodCall:
    base: object
    method: str
    args: list
    line: int
    col: int


@dataclass
class FieldAssign:
    target: object  # FieldAccess node
    expr: object
    line: int
    col: int


@dataclass
class Var:
    name: str
    line: int
    col: int
    # Set by the checker (Top-500 #103, FN-C1): True when this Var
    # is a bare function name used as a fn value (not a local).
    # Codegen reads it to collect wrapper functions.
    is_fn_value: bool = False


@dataclass
class Lambda:
    # A closure literal (Top-500 #101): fn(params) -> ret { body }.
    # params is [(name, type)] like FuncDef; ret is "void" when the
    # `-> R` is omitted. Stamped by the checker: captures is the
    # first-use-ordered [(name, type)] of captured variables, and
    # fn_type is the fn-type string of the lambda.
    params: list
    ret: str
    body: object
    line: int
    col: int
    captures: list = None
    fn_type: str = None


@dataclass
class Call:
    name: str
    args: list
    line: int
    col: int
    concrete_type: str = None  # set by checker for enum constructions
    fn_type: str = None  # set by checker for indirect calls through
    # a fn-typed variable (Top-500 #103): the callee's fn type,
    # which codegen uses for the argument-ownership loop.
    trycall_fn_type: str = None  # set by checker for try_call
    # (Top-500 #48): the callee's fn type. Deliberately NOT
    # fn_type — is_fresh_str/is_fresh_fn read fn_type and would
    # wrongly treat try_call as returning R instead of Result.


@dataclass
class IndirectCall:
    # Calling through a computed fn value: handlers[i](x),
    # make()(x), (f)(x). The callee is any expression whose type
    # is a fn type (Top-500 #103). fn_type is stamped by the
    # checker: the callee's fn type, for codegen's ownership loop.
    callee: object
    args: list
    line: int
    col: int
    fn_type: str = None


@dataclass
class Index:
    base: object
    index: object
    line: int
    col: int


@dataclass
class TupleIndex:
    base: object
    index: int
    line: int
    col: int


@dataclass
class RangeLit:
    start: object
    end: object
    line: int
    col: int


@dataclass
class Defer:
    call: object
    line: int
    col: int


@dataclass
class Cast:
    expr: object
    target: str
    line: int
    col: int


@dataclass
class BinOp:
    op: str
    left: object
    right: object
    line: int
    col: int


@dataclass
class UnaryOp:
    op: str
    expr: object
    line: int
    col: int
