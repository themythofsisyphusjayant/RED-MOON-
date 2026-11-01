"""Shared trait helpers: method name mangling.

An impl method `m` on struct `S` compiles as an ordinary function
named `S__m`, with the receiver as its first parameter. A method
call `value.m(args)` becomes a call to `S__m(value, args)`.
"""


def mangle(struct, method):
    return f"{struct}__{method}"
