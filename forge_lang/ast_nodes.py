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
class Match:
    expr: object
    arms: list  # [(pattern, Block)]; pattern is a variant name or "_"
    line: int
    col: int


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


@dataclass
class For:
    name: str
    expr: object
    body: object
    line: int
    col: int


@dataclass
class Break:
    line: int
    col: int


@dataclass
class Continue:
    line: int
    col: int


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


@dataclass
class Call:
    name: str
    args: list
    line: int
    col: int
    concrete_type: str = None  # set by checker for enum constructions


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
