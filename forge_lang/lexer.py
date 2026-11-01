"""Lexer for The Jal Pari Language. Tokens carry line/column for readable errors."""

from dataclasses import dataclass
from .errors import ForgeError

KEYWORDS = {"fn", "let", "mut", "if", "else", "while", "for", "in",
            "return", "true", "false", "import", "as", "struct",
            "enum", "match", "spawn", "extern", "break", "continue",
            "trait", "impl", "type", "newtype", "opaque", "readonly",
            "defer"}
TWO_CHAR = {"==", "!=", "<=", ">=", "&&", "||", "->", "=>", "<<", ">>", ".."}
ONE_CHAR = set("+-*/%<>=!;,:(){}[].?&|^~")


@dataclass
class Token:
    kind: str
    value: object
    line: int
    col: int


def tokenize(source):
    tokens = []
    i = 0
    line = 1
    col = 1
    n = len(source)

    def advance(k=1):
        nonlocal i, line, col
        for _ in range(k):
            if i < n and source[i] == "\n":
                line += 1
                col = 1
            else:
                col += 1
            i += 1

    while i < n:
        ch = source[i]
        if ch in " \t\r\n":
            advance()
            continue
        if source.startswith("//", i):
            while i < n and source[i] != "\n":
                advance()
            continue
        if source.startswith("/*", i):
            sl, sc = line, col
            advance(2)
            closed = False
            while i < n:
                if source.startswith("*/", i):
                    advance(2)
                    closed = True
                    break
                advance()
            if not closed:
                raise ForgeError("unterminated block comment", sl, sc)
            continue

        sl, sc = line, col
        if ch.isdigit():
            prefix = source[i:i + 2]
            if prefix in ("0x", "0X", "0b", "0B", "0o", "0O"):
                # Prefixed integer literals: 0xFF hex, 0b1010 binary,
                # 0o777 octal. Integers only (no prefixed floats).
                # Underscores may separate digits (0xFF_FF, 1_000
                # below) but never lead, trail, or double up.
                kind = {"0x": "hex", "0X": "hex", "0b": "binary",
                        "0B": "binary", "0o": "octal",
                        "0O": "octal"}[prefix]
                digits = {"hex": "0123456789abcdefABCDEF",
                          "binary": "01", "octal": "01234567"}[kind]
                base = {"hex": 16, "binary": 2, "octal": 8}[kind]
                j = i + 2
                while j < n and (source[j] in digits or source[j] == "_"):
                    j += 1
                text = source[i:j]
                parts = text[2:].split("_")
                if not parts or any(p == "" for p in parts):
                    raise ForgeError(
                        f"{kind} literal needs at least one {kind} digit "
                        f"and no leading, trailing, or doubled underscore",
                        sl, sc)
                advance(j - i)
                tokens.append(Token("INT", int(text[2:].replace("_", ""),
                                               base), sl, sc))
                continue
            j = i
            while j < n and (source[j].isdigit() or source[j] == "_"):
                j += 1
            if any(p == "" for p in source[i:j].split("_")):
                raise ForgeError("integer literal has a leading, trailing, "
                                 "or doubled underscore", sl, sc)
            is_float = False
            # A number right after a dot is a tuple index, not the
            # fraction of a float: `t.0.0` must lex as t . 0 . 0,
            # not t . 0.0. (A float literal's own dot is scanned
            # with its integer part, where the previous token is
            # never a dot.)
            after_dot = (tokens and tokens[-1].kind == "OP"
                         and tokens[-1].value == ".")
            if (not after_dot and j < n and source[j] == "."
                    and j + 1 < n and source[j + 1].isdigit()):
                is_float = True
                j += 1
                while j < n and source[j].isdigit():
                    j += 1
            if j < n and source[j] in "eE":
                k = j + 1
                if k < n and source[k] in "+-":
                    k += 1
                if k < n and source[k].isdigit():
                    is_float = True
                    j = k
                    while j < n and source[j].isdigit():
                        j += 1
            text = source[i:j]
            advance(j - i)
            tokens.append(Token("FLOAT" if is_float else "INT",
                                float(text) if is_float else
                                int(text.replace("_", "")), sl, sc))
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (source[j].isalnum() or source[j] == "_"):
                j += 1
            text = source[i:j]
            advance(j - i)
            tokens.append(Token("KEYWORD" if text in KEYWORDS else "IDENT", text, sl, sc))
            continue
        if ch == '"':
            advance()
            out = []
            closed = False
            while i < n:
                c = source[i]
                if c == '"':
                    advance()
                    closed = True
                    break
                if c == "\n":
                    break
                if c == "\\":
                    el, ec = line, col
                    advance()
                    if i >= n:
                        break
                    e = source[i]
                    mapping = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "0": "\0"}
                    if e not in mapping:
                        raise ForgeError(f"unknown escape \\{e}", el, ec)
                    out.append(mapping[e])
                    advance()
                    continue
                out.append(c)
                advance()
            if not closed:
                raise ForgeError("unterminated string literal", sl, sc)
            tokens.append(Token("STR", "".join(out), sl, sc))
            continue
        two = source[i:i + 2]
        if two in TWO_CHAR:
            advance(2)
            tokens.append(Token("OP", two, sl, sc))
            continue
        if ch in ONE_CHAR:
            advance()
            tokens.append(Token("OP", ch, sl, sc))
            continue
        raise ForgeError(f"unexpected character {ch!r}", sl, sc)
    tokens.append(Token("EOF", None, line, col))
    return tokens
