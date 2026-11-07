# Qasida for VS Code

> Legacy grammar-only extension. The full extension (highlighting,
> snippets, diagnostics + completion via LSP, Run/Check/Format/Build
> commands) is now `../qasida/` — if you have that one installed,
> uninstall or disable this one first, since both register `.fg`
> files and only one should own them.

Syntax highlighting for `.fg` files (this folder). Diagnostics
and completion from the Forge language server.

## Language server

Point your LSP client (for example `vscode-languageclient`, or any
editor that can launch a stdio LSP server) at:

```
python3 /path/to/forge-v2/forge.py lsp
```

The server publishes diagnostics from the real Forge checker on
`didOpen`/`didChange`, and completes keywords, builtins, and
function/struct names from the open document.

This extension folder is intentionally client-free: it ships the
grammar and language configuration, and the server is the Forge
compiler itself, so diagnostics can never drift from `qasida check`.
