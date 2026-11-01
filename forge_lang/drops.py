"""Destructor hooks (Top-500 #33) in a program, for backend
gates. A program uses drop hooks when any impl block defines
a method named `drop` (the native backend then calls
Struct__drop automatically when an owned binding dies).
big32 and WASM reject drop programs in v1 with a named error.
"""


def uses_drop(program):
    """True when any impl block defines a drop method, or any
    (checker-expanded) function is a mangled Struct__drop."""
    for idf in getattr(program, "impls", None) or []:
        for m in getattr(idf, "methods", None) or []:
            if getattr(m, "name", None) == "drop":
                return True
    for fn in getattr(program, "funcs", None) or []:
        if getattr(fn, "name", "").endswith("__drop"):
            return True
    return False
