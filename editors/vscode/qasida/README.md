# Qasida — VS Code extension

Full VS Code support for Qasida (`.fg` files). This is
a fresh, complete extension — it replaces the old grammar-only
`forge` extension in `../forge/`. If you still have that one
installed, uninstall or disable it first: both register `.fg` files,
and only one should own them.

## What you get

- **Syntax highlighting** for the whole language: keywords (`fn`,
  `let`, `mut`, `struct`, `enum`, `match`, `spawn`, `break`, …),
  types (`int`, `float`, `bool`, `str`, `void`, `Option`, `Result`),
  all 48 builtins, `//` and `/* */` comments, strings with escapes,
  numbers, and `=>` match arms.
- **Snippets**: `main`, `fn`, `fnvoid`, `let`, `letmut`, `if`,
  `ifelse`, `while`, `for`, `match`, `struct`, `enum`, `scope`,
  `import`, `println`, `assert`.
- **Real diagnostics + completion** from the language server
  (`forge.py lsp`): checker errors appear as red squiggles, and
  completion offers keywords, builtins, and the file's own functions
  and structs. No extra setup beyond installing Qasida itself.
- **Commands** (Command Palette, with a `.fg` file open):
  - `Qasida: Run Current File` — `qasida run <file>`
  - `Qasida: Check Current File` — `qasida check <file>`
  - `Qasida: Format Current File` — `qasida fmt <file>` (rewrites
    the file; VS Code reloads it)
  - `Qasida: Build Current File` — `qasida build <file>`
  - `Qasida: Restart Language Server`

## Requirements

The `qasida` command must be on your PATH (that is how the language
server starts and how the commands run). Install it from the repo
root, e.g. `./install.sh`, or `pip install .` — see the main repo
README. If the server cannot start, the extension shows one warning
and the terminal commands still work once `qasida` is installed.

## Settings

- `qasida.executable` (default `"qasida"`): command used by the
  Run / Check / Format / Build commands.
- `qasida.serverCommand` (default `["qasida", "lsp"]`): full command
  used to start the language server. Repo developers can point it at
  Python instead, e.g.
  `["python3", "/path/to/RED-MOON-/forge.py", "lsp"]`.

## Install from the .vsix

`Extensions → … → Install from VSIX`, then pick
`qasida-1.0.0.vsix` from this folder. Or, without packaging, copy
this folder to `~/.vscode/extensions/qasida-1.0.0/` and restart
VS Code.

## Notes and limits (honest)

- The language server itself is intentionally small: diagnostics and
  completion only — no hover, rename, or refactor yet (that is a
  `forge.py lsp` limit, not this extension's).
- The extension has no bundled dependencies: the LSP client is plain
  Node in `lsp-client.js`, so there is nothing to `npm install`.
- Marketplace publishing is not done: the publisher here (`qasida`)
  is a placeholder, and publishing is the repo owner's click.
- Full activation inside the VS Code GUI (squiggles, completion
  popup, commands) is verified by hand after install; what is
  verified in this repo is the JSON/JS syntax, every grammar regex,
  and the client's wire protocol against the real `forge.py lsp`
  (see the checks below).

## Verifying the client without VS Code

The client (`lsp-client.js`) has no VS Code dependency, so it can be
driven headlessly against the real server:

```js
const { LspClient } = require("./lsp-client");
const c = new LspClient(["python3", "../forge.py", "lsp"], {
  onDiagnostics: (uri, diags) => console.log(uri, diags),
});
await c.start();
c.didOpen("file:///tmp/t.fg", "fn main() -> int {\n  return true;\n}\n");
// -> one diagnostic: return-type error, severity 1
console.log(await c.completion("file:///tmp/t.fg", 0, 0));
// -> items include "println", "fn", "main"
await c.stop();
```
