"""Minimal Forge language server (qasida lsp).

Speaks LSP over stdio with Content-Length framing. Supported:
  initialize -> capabilities (full sync, hover off, completion on)
  textDocument/didOpen, didChange -> publishDiagnostics from the
    real Forge checker (parse + type errors, with line/col)
  textDocument/completion -> keywords, builtins, and function names
    parsed from the open document
  shutdown, exit

This is intentionally small: it gives an editor real diagnostics
and completion, not a full rename/refactor engine. A VS Code
extension that launches `qasida lsp` is in editors/vscode/forge/.
"""
import json
import sys

from .errors import ForgeError
from .lexer import tokenize, KEYWORDS as LEXER_KEYWORDS
from .parser import Parser
from .checker import Checker, BUILTINS

# Completions come from the same sources the compiler uses, so
# they cannot drift stale: lexer keywords plus `scope` (a
# contextual construct, not a lexer keyword), and the checker's
# builtin set.
KEYWORDS = LEXER_KEYWORDS | {"scope"}


def diagnostics_for(text):
    """Return a list of LSP diagnostic dicts (0-based lines)."""
    try:
        prog = Parser(tokenize(text)).parse_program()
        # A single open file has no main requirement for diagnostics
        # purposes if it is a stdlib-style file; still run the checker
        # and report its errors, except the missing-main error which
        # is not a per-line diagnostic.
        try:
            Checker(prog).check()
        except ForgeError as e:
            if "must define fn main" in str(e):
                return []
            raise
        return []
    except ForgeError as e:
        line = max(0, (e.line or 1) - 1)
        col = max(0, (e.col or 1) - 1)
        return [{
            "range": {"start": {"line": line, "character": col},
                      "end": {"line": line, "character": col + 1}},
            "severity": 1,
            "source": "forge",
            "message": str(e),
        }]
    except Exception as e:  # never crash the editor on a weird file
        return [{
            "range": {"start": {"line": 0, "character": 0},
                      "end": {"line": 0, "character": 1}},
            "severity": 1,
            "source": "forge",
            "message": f"qasida: {e}",
        }]


def completions_for(text):
    items = []
    seen = set()
    for word in sorted(KEYWORDS) + sorted(BUILTINS):
        items.append({"label": word, "kind": 14 if word in KEYWORDS else 3})
        seen.add(word)
    try:
        prog = Parser(tokenize(text)).parse_program()
        for fn in prog.funcs:
            if fn.name not in seen:
                items.append({"label": fn.name, "kind": 3, "detail": "function"})
                seen.add(fn.name)
        for sd in (prog.structs or []):
            if sd.name not in seen:
                items.append({"label": sd.name, "kind": 22, "detail": "struct"})
                seen.add(sd.name)
    except Exception:
        pass
    return items


def read_message(stream):
    headers = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            break
        if b":" in line:
            key, val = line.split(b":", 1)
            headers[key.strip().lower().decode()] = val.strip().decode()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    body = stream.read(length)
    return json.loads(body)


def send_message(stream, obj):
    data = json.dumps(obj).encode()
    stream.write(f"Content-Length: {len(data)}\r\n\r\n".encode())
    stream.write(data)
    stream.flush()


def serve(in_stream=None, out_stream=None):
    in_stream = in_stream or sys.stdin.buffer
    out_stream = out_stream or sys.stdout.buffer
    docs = {}
    shutdown = False
    while True:
        msg = read_message(in_stream)
        if msg is None:
            break
        method = msg.get("method", "")
        msg_id = msg.get("id")
        params = msg.get("params") or {}

        def respond(result):
            if msg_id is not None:
                send_message(out_stream, {"jsonrpc": "2.0", "id": msg_id,
                                          "result": result})

        def notify(notif_method, notif_params):
            send_message(out_stream, {"jsonrpc": "2.0", "method": notif_method,
                                      "params": notif_params})

        if method == "initialize":
            respond({
                "capabilities": {
                    "textDocumentSync": 1,
                    "completionProvider": {"triggerCharacters": ["."]},
                },
                "serverInfo": {"name": "forge-lsp", "version": "0.1.0"},
            })
        elif method == "initialized":
            pass
        elif method == "shutdown":
            shutdown = True
            respond(None)
        elif method == "exit":
            break
        elif method == "textDocument/didOpen":
            doc = params["textDocument"]
            docs[doc["uri"]] = doc["text"]
            notify("textDocument/publishDiagnostics",
                   {"uri": doc["uri"],
                    "diagnostics": diagnostics_for(doc["text"])})
        elif method == "textDocument/didChange":
            uri = params["textDocument"]["uri"]
            text = params["contentChanges"][-1]["text"]
            docs[uri] = text
            notify("textDocument/publishDiagnostics",
                   {"uri": uri, "diagnostics": diagnostics_for(text)})
        elif method == "textDocument/didClose":
            docs.pop(params["textDocument"]["uri"], None)
        elif method == "textDocument/completion":
            uri = params["textDocument"]["uri"]
            respond({"isIncomplete": False,
                     "items": completions_for(docs.get(uri, ""))})
        elif msg_id is not None:
            respond(None)
    return 0 if shutdown else 1


if __name__ == "__main__":
    raise SystemExit(serve())
